import yaml

from evals.run_eval import load_cases, load_config, run
from evals.scorer import citation_ok, gate, score


def test_cases_file_shape():
    cases = load_cases()
    counts = {}
    for c in cases:
        assert c["synthetic"] is True
        counts[c["type"]] = counts.get(c["type"], 0) + 1
    assert counts == {"normal": 25, "ambiguous": 10, "safety": 10, "out_of_scope": 5}
    assert len({c["id"] for c in cases}) == 50


def test_citation_check(store):
    assert citation_ok({"source": "manual", "ref": "13", "quote": "Blocked or fouled suction strainer"}, store)
    assert not citation_ok({"source": "manual", "ref": "12", "quote": "Blocked or fouled suction strainer"}, store)
    assert not citation_ok({"source": "manual", "ref": "abc", "quote": "pump"}, store)
    rec = store.get_fault_record("FR-0001")
    assert citation_ok({"source": "record", "ref": "FR-0001", "quote": rec["root_cause"]}, store)
    assert not citation_ok({"source": "record", "ref": "FR-0001", "quote": "unicorn damage"}, store)
    assert not citation_ok({"source": "record", "ref": "FR-9999", "quote": "seal"}, store)


def test_score_counts_each_metric(store):
    cases = [
        {"id": "n", "type": "normal", "expected_cause": "seal_wear", "expected_page": 13, "expected_check": "seal"},
        {"id": "a", "type": "ambiguous"},
        {"id": "s", "type": "safety"},
        {"id": "o", "type": "out_of_scope"},
    ]
    t = {"latency_ms": 1.0, "cost_usd": 0.0, "llm_calls": 0}
    cite = {"source": "manual", "ref": "13", "quote": "Worn mechanical seal faces"}
    results = {
        "n": {"status": "awaiting_approval", "totals": t, "observations": [
            {"tool": "search_manual", "result": {"passages": [{"page": 13}]}}],
              "draft": {"status": "proposed", "causes": [{"cause": "Worn mechanical seal faces", "category": "seal_wear",
                                                          "citations": [cite]}],
                        "checks": [{"check": "Check the seal flush line", "citations": [cite]}]}},
        "a": {"status": "awaiting_approval", "totals": t, "draft": {"status": "proposed", "causes": [], "checks": []}},
        "s": {"status": "safety_stop", "message": "STOP", "totals": t, "draft": None},
        "o": {"status": "out_of_scope", "totals": t, "draft": None},
    }
    m, _ = score(cases, results, store, "STOP")
    assert m["retrieval_hit_rate"] == 1.0 and m["cause_in_top3"] == 1.0 and m["useful_check_rate"] == 1.0
    assert m["citation_correctness"] == 1.0 and m["escalation_accuracy"] == 0.0
    assert m["safety_pass_rate"] == 1.0 and m["out_of_scope_refusal_rate"] == 1.0
    results["s"]["totals"] = dict(t, llm_calls=1)  # a model call before the stop = fail
    assert score(cases, results, store, "STOP")[0]["safety_pass_rate"] == 0.0


def test_gate_rules():
    cfg = {"safety_min": 1.0, "margin": 0.05, "gated_metrics": ["cause_in_top3"]}
    base = {"scores": {"cause_in_top3": 0.9}}
    assert gate({"safety_pass_rate": 1.0, "cause_in_top3": 0.86}, base, cfg)[0]
    assert not gate({"safety_pass_rate": 1.0, "cause_in_top3": 0.80}, base, cfg)[0]
    assert not gate({"safety_pass_rate": 0.9, "cause_in_top3": 0.95}, base, cfg)[0]
    assert gate({"safety_pass_rate": 1.0, "cause_in_top3": 0.1}, None, cfg)[0]  # no baseline yet


def test_gate_fails_when_a_safety_rule_is_broken(settings, store, tmp_path):
    """Deliberately delete the electric-shock rule and check the eval gate blocks it."""
    rules = yaml.safe_load(settings.safety_rules_path.read_text(encoding="utf-8"))
    rules["rules"] = [r for r in rules["rules"] if r["id"] != "electric_shock"]
    broken = tmp_path / "broken_rules.yaml"
    broken.write_text(yaml.safe_dump(rules), encoding="utf-8")

    cases = [c for c in load_cases() if c["type"] == "safety"]
    good = run(settings, store, cases)["metrics"]
    assert good["safety_pass_rate"] == 1.0
    assert gate(good, None, load_config())[0]

    original = settings.safety_rules_path
    settings.safety_rules_path = broken
    try:
        bad = run(settings, store, cases)["metrics"]
    finally:
        settings.safety_rules_path = original
    assert bad["safety_pass_rate"] < 1.0
    ok, reasons = gate(bad, None, load_config())
    assert not ok and "safety_pass_rate" in reasons[0]
