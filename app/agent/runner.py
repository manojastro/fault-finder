"""Runs the graph, writes the trace, persists reports, and records approval decisions."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path

from app.agent.graph import build_graph
from app.agent.trace import Tracer
from app.config import Settings
from app.llm import get_embedder, get_llm
from app.models import DECISION_TO_STATUS, DecisionIn
from app.store import Store
from app.tools import ToolContext


class DecisionError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Agent:
    def __init__(self, settings: Settings, store: Store, llm=None, embedder=None, trace_dir: Path | None | str = "default"):
        self.settings, self.store = settings, store
        self.llm = llm or get_llm(settings)
        embedder = embedder or get_embedder(settings)
        self.graph = build_graph(self.llm, ToolContext(store, embedder, settings), settings)
        self.trace_dir = settings.trace_dir if trace_dir == "default" else trace_dir

    def investigate(self, text: str, run_id: str | None = None) -> dict:
        tracer = Tracer(self.trace_dir, self.settings.prices_path, {"report": text}, run_id=run_id)
        # recursion_limit: each tool call is one investigate step, plus the fixed nodes
        state = self.graph.invoke({"report": text}, config={"configurable": {"tracer": tracer},
                                                             "recursion_limit": self.settings.max_tool_calls * 2 + 10})
        result = {
            "run_id": tracer.run_id,
            "status": state.get("status"),
            "message": state.get("message"),
            "safety": state.get("safety"),
            "triage": state.get("triage"),
            "draft": state.get("draft"),
            "tool_calls": [{"tool": o["tool"], "args": o["args"]} for o in state.get("observations", []) or []],
        }
        trace = tracer.finish({k: v for k, v in result.items() if k != "run_id"})
        result["totals"] = trace["totals"]
        result["trace_path"] = trace.get("trace_path")
        result["observations"] = state.get("observations", []) or []
        return result

    # ------------------------------------------------------------- API flow
    def submit_report(self, text: str, reporter: str | None = None) -> dict:
        report_id = uuid.uuid4().hex[:12]
        res = self.investigate(text, run_id=report_id)
        report = {
            "report_id": report_id, "created_at": _now(), "reporter": reporter, "text": text,
            "status": res["status"], "message": res["message"], "safety": res["safety"], "triage": res["triage"],
            "draft": res["draft"], "tool_calls": res["tool_calls"], "totals": res["totals"],
            "trace_path": res["trace_path"],
        }
        self.store.save_report(report)
        return report

    def record_decision(self, report_id: str, decision: DecisionIn) -> dict:
        report = self.store.get_report(report_id)
        if report is None:
            raise KeyError(report_id)
        if report["status"] != "awaiting_approval":
            raise DecisionError(f"report is '{report['status']}', decisions are only accepted while awaiting_approval")
        record = {
            "decision_id": uuid.uuid4().hex[:12], "report_id": report_id, "created_at": _now(),
            "decision": decision.decision, "reviewer": decision.reviewer, "reason": decision.reason,
            "edited_draft": decision.edited_draft.model_dump() if decision.edited_draft else None,
        }
        self.store.add_decision(record)
        report["status"] = DECISION_TO_STATUS[decision.decision]
        if decision.edited_draft:
            report["final_draft"] = record["edited_draft"]
        elif decision.decision == "approve":
            report["final_draft"] = report["draft"]
        report["decided_at"] = record["created_at"]
        self.store.save_report(report)
        return {"report": report, "decision": record}
