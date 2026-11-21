from app.store.sqlite_store import SqliteStore
from app.tools import ToolContext, call_tool


def test_get_fault_history(ctx):
    out = call_tool(ctx, "get_fault_history", {"machine_id": "cp-03", "limit": 5})
    assert out["machine_found"] and 0 < len(out["records"]) <= 5
    dates = [r["date"] for r in out["records"]]
    assert dates == sorted(dates, reverse=True)
    assert all(r["record_id"].startswith("FR-") and r["machine_id"] == "CP-03" for r in out["records"])


def test_get_fault_history_unknown_machine_is_empty(ctx):
    out = call_tool(ctx, "get_fault_history", {"machine_id": "CP-99"})
    assert out == {"machine_id": "CP-99", "machine_found": False, "records": []}


def test_find_similar_faults(ctx):
    out = call_tool(ctx, "find_similar_faults", {"symptom_text": "mechanical seal dripping at the shaft", "k": 5})
    assert len(out["records"]) == 5
    assert out["records"][0]["fault_code"] == "PF-103"
    assert all(0 <= r["similarity"] <= 1 for r in out["records"])


def test_search_manual(ctx):
    out = call_tool(ctx, "search_manual", {"query": "bearing lubrication interval grease", "k": 3})
    assert len(out["passages"]) == 3
    assert 18 in [p["page"] for p in out["passages"]]
    assert all(p["section"] and p["chunk_id"] for p in out["passages"])


def test_lookup_fault_code(ctx):
    out = call_tool(ctx, "lookup_fault_code", {"code": "pf-104"})
    assert out["found"] and out["page"] == 13 and out["name"] == "Cavitation detected"
    assert "Blocked or fouled suction strainer" in out["likely_causes"]


def test_lookup_unknown_code(ctx):
    assert call_tool(ctx, "lookup_fault_code", {"code": "PF-999"}) == {
        "code": "PF-999", "found": False, "name": None, "trigger": None, "page": None, "likely_causes": [], "checks": []}


def test_bad_input_is_rejected(ctx):
    assert call_tool(ctx, "get_fault_history", {"machine_id": "drop table;"})["error"] == "invalid input"
    assert call_tool(ctx, "get_fault_history", {"machine_id": "CP-01", "limit": 0})["error"] == "invalid input"
    assert call_tool(ctx, "find_similar_faults", {"symptom_text": ""})["error"] == "invalid input"
    assert call_tool(ctx, "search_manual", {})["error"] == "invalid input"
    assert call_tool(ctx, "lookup_fault_code", {"code": "hello"})["error"] == "invalid input"
    assert "unknown tool" in call_tool(ctx, "delete_everything", {})["error"]


def test_tools_on_empty_store(settings, ctx):
    empty = SqliteStore(":memory:")
    empty.init_schema(256)
    c = ToolContext(empty, ctx.embedder, settings)
    assert call_tool(c, "search_manual", {"query": "vibration"})["passages"] == []
    assert call_tool(c, "find_similar_faults", {"symptom_text": "vibration"})["records"] == []
    assert call_tool(c, "lookup_fault_code", {"code": "PF-101"})["found"] is False
