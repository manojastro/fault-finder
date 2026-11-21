"""LangGraph flow:

    safety_check -> triage -> investigate (loop, max N tool calls) -> draft -> approval_gate -> END
          |            |
          v            v
     END (stop msg)  END (out of scope)

The approval gate pauses the run by persisting the draft with status
'awaiting_approval'. The run resumes when a person posts a decision
(see Agent.record_decision)."""
from __future__ import annotations

import time
from typing import TypedDict

from langgraph.graph import END, StateGraph
from pydantic import ValidationError

from app.models import ESCALATE_MESSAGE, OUT_OF_SCOPE_MESSAGE, Draft
from app.safety.check import check_report
from app.tools import call_tool


class State(TypedDict, total=False):
    report: str
    safety: dict
    triage: dict
    observations: list[dict]
    finished_investigating: bool
    draft: dict
    status: str
    message: str | None


def observed_sources(observations: list[dict]) -> tuple[set[str], set[str]]:
    pages, records = set(), set()
    for o in observations:
        r = o["result"]
        for p in r.get("passages", []) or []:
            pages.add(str(p["page"]))
        if r.get("found") and r.get("page") is not None:
            pages.add(str(r["page"]))
        for rec in r.get("records", []) or []:
            records.add(rec["record_id"])
    return pages, records


def enforce_evidence(draft: Draft, observations: list[dict]) -> Draft:
    """Code-level guard: keep only citations to pages/records the tools actually
    returned; drop claims left without a citation; escalate if no cause survives."""
    pages, records = observed_sources(observations)

    def ok(c) -> bool:
        return (c.source == "manual" and c.ref in pages) or (c.source == "record" and c.ref in records)

    causes = []
    for cause in draft.causes:
        cause.citations = [c for c in cause.citations if ok(c)]
        if cause.citations:
            causes.append(cause)
    for i, cause in enumerate(causes, 1):
        cause.rank = i
    checks = []
    for chk in draft.checks:
        chk.citations = [c for c in chk.citations if ok(c)]
        if chk.citations:
            checks.append(chk)
    draft.causes, draft.checks = causes, checks
    if draft.status == "proposed" and not causes:
        draft.status, draft.confidence = "escalate", "low"
        draft.escalation_message = ESCALATE_MESSAGE
        draft.summary = "No cause could be supported by a citation. " + draft.summary
    return draft


def build_graph(llm, tool_ctx, settings):
    max_calls = settings.max_tool_calls

    def _llm(task: str, payload: dict, config) -> dict:
        tracer = config["configurable"]["tracer"]
        res = llm.complete_json(task, payload)
        tracer.event("llm_call", task=task, model=res.model, input_tokens=res.input_tokens,
                     output_tokens=res.output_tokens, latency_ms=round(res.latency_ms, 2))
        return res.data

    def safety_check(state: State, config) -> State:
        res = check_report(state["report"], settings.safety_rules_path)
        config["configurable"]["tracer"].event("safety_check", matched_rules=res.matched_rules)
        out: State = {"safety": {"critical": res.is_safety_critical, "matched_rules": res.matched_rules,
                                 "rules_status": res.rules_status}}
        if res.is_safety_critical:
            out.update(status="safety_stop", message=res.message)
        return out

    def triage(state: State, config) -> State:
        tri = _llm("triage", {"report": state["report"]}, config)
        if not tri.get("in_scope", True):
            return {"triage": tri, "status": "out_of_scope", "message": OUT_OF_SCOPE_MESSAGE}
        return {"triage": tri, "observations": [], "finished_investigating": False}

    def investigate(state: State, config) -> State:
        obs = list(state.get("observations", []))
        if len(obs) >= max_calls:
            return {"finished_investigating": True}
        action = _llm("next_action", {"report": state["report"], "triage": state["triage"], "observations": obs,
                                      "calls_made": len(obs), "max_calls": max_calls}, config)
        tool = action.get("tool")
        if not tool or tool == "finish":
            return {"finished_investigating": True}
        start = time.perf_counter()
        result = call_tool(tool_ctx, tool, action.get("args") or {})
        ms = round((time.perf_counter() - start) * 1000, 2)
        config["configurable"]["tracer"].event("tool_call", tool=tool, args=action.get("args"), latency_ms=ms,
                                               output=result)
        obs.append({"tool": tool, "args": action.get("args") or {}, "result": result})
        return {"observations": obs, "finished_investigating": len(obs) >= max_calls}

    def draft(state: State, config) -> State:
        raw = _llm("draft", {"report": state["report"], "triage": state["triage"],
                             "observations": state.get("observations", [])}, config)
        try:
            d = Draft.model_validate(raw)
        except ValidationError as e:
            config["configurable"]["tracer"].event("draft_invalid", errors=str(e)[:2000])
            d = Draft(status="escalate", summary="The model's draft did not match the schema.", confidence="low",
                      missing_information=[])
        d = enforce_evidence(d, state.get("observations", []))
        return {"draft": d.model_dump()}

    def approval_gate(state: State, config) -> State:
        return {"status": "awaiting_approval", "message": None}

    g = StateGraph(State)
    for name, fn in [("safety_check", safety_check), ("triage", triage), ("investigate", investigate),
                     ("draft", draft), ("approval_gate", approval_gate)]:
        g.add_node(name, fn)
    g.set_entry_point("safety_check")
    g.add_conditional_edges("safety_check", lambda s: END if s.get("status") == "safety_stop" else "triage")
    g.add_conditional_edges("triage", lambda s: END if s.get("status") == "out_of_scope" else "investigate")
    g.add_conditional_edges("investigate", lambda s: "draft" if s.get("finished_investigating") else "investigate")
    g.add_edge("draft", "approval_gate")
    g.add_edge("approval_gate", END)
    return g.compile()
