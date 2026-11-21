import json

from app.agent.runner import Agent
from app.llm import LLMResult
from app.models import ESCALATE_MESSAGE, OUT_OF_SCOPE_MESSAGE
from app.agent import fake_policy


class ScriptedLLM:
    """Uses the fake policy for triage, but overrides chosen tasks."""

    model = "fake-llm"

    def __init__(self, next_action=None, draft=None):
        self._next, self._draft = next_action, draft
        self.calls = []

    def complete_json(self, task, payload):
        self.calls.append(task)
        if task == "next_action" and self._next:
            data = self._next(payload)
        elif task == "draft" and self._draft:
            data = self._draft(payload)
        else:
            data = fake_policy.run(task, payload)
        return LLMResult(data, 10, 10, 0.1, self.model)


def test_normal_report_produces_cited_draft(agent):
    res = agent.investigate("CP-03 bearing housing too hot to touch, 91 C, controller showed PF-102")
    d = res["draft"]
    assert res["status"] == "awaiting_approval" and d["status"] == "proposed"
    assert 1 <= len(d["causes"]) <= 3
    assert all(c["citations"] for c in d["causes"]) and all(c["citations"] for c in d["checks"])
    assert d["confidence"] in {"low", "medium", "high"}
    assert any(c["category"] == "bearing_wear" for c in d["causes"])


def test_tool_loop_is_capped_at_six(settings, store):
    always_search = lambda p: {"tool": "search_manual", "args": {"query": "vibration", "k": 2}}
    llm = ScriptedLLM(next_action=always_search)
    res = Agent(settings, store, llm=llm, trace_dir=None).investigate("CP-01 PF-101 high vibration 8 mm/s")
    assert len(res["tool_calls"]) == 6
    assert res["totals"]["tool_calls"] == 6
    assert llm.calls.count("next_action") == 6
    assert res["status"] == "awaiting_approval"


def test_empty_evidence_is_refused(settings, store):
    """A draft whose citations point at pages/records no tool returned is stripped and escalated."""
    fabricated = lambda p: {
        "status": "proposed", "summary": "made up", "confidence": "high", "missing_information": [],
        "causes": [{"rank": 1, "cause": "Gremlins", "category": "x",
                    "citations": [{"source": "manual", "ref": "99", "quote": "gremlins"},
                                  {"source": "record", "ref": "FR-9999", "quote": "gremlins"}]}],
        "checks": [{"check": "Look for gremlins", "citations": [{"source": "manual", "ref": "98", "quote": "abc"}]}],
    }
    finish = lambda p: {"tool": "finish", "args": {}}
    res = Agent(settings, store, llm=ScriptedLLM(next_action=finish, draft=fabricated), trace_dir=None).investigate(
        "CP-01 PF-101 high vibration")
    d = res["draft"]
    assert d["status"] == "escalate" and d["causes"] == [] and d["checks"] == []
    assert d["escalation_message"] == ESCALATE_MESSAGE


def test_vague_report_escalates(agent):
    d = agent.investigate("Pump not working right, can someone look at it")["draft"]
    assert d["status"] == "escalate" and d["escalation_message"] == ESCALATE_MESSAGE
    assert d["missing_information"]


def test_invalid_model_output_escalates(settings, store):
    res = Agent(settings, store, llm=ScriptedLLM(draft=lambda p: {"nonsense": True}), trace_dir=None).investigate(
        "CP-01 PF-101 high vibration")
    assert res["draft"]["status"] == "escalate"


def test_out_of_scope_is_refused_politely(agent):
    res = agent.investigate("Write me a poem about autumn")
    assert res["status"] == "out_of_scope" and res["message"] == OUT_OF_SCOPE_MESSAGE and res["draft"] is None


def test_trace_file_written(settings, store, tmp_path):
    res = Agent(settings, store, trace_dir=tmp_path).investigate("CP-07 PF-104 cavitation noise, suction 0.4 bar")
    trace = json.loads(open(res["trace_path"]).read())
    assert trace["inputs"]["report"].startswith("CP-07")
    assert trace["totals"]["tool_calls"] == len([e for e in trace["events"] if e["type"] == "tool_call"]) > 0
    assert trace["totals"]["input_tokens"] > 0 and trace["totals"]["cost_usd"] == 0.0
    assert all("latency_ms" in e for e in trace["events"] if e["type"] in ("tool_call", "llm_call"))

    from scripts.trace_report import summarise

    s = summarise(tmp_path)
    assert s["runs"] == 1 and s["tool_calls_total"] == trace["totals"]["tool_calls"]
