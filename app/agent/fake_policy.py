"""Deterministic heuristics that stand in for the chat model when LLM_PROVIDER=fake.

It plays the three model tasks (triage, next_action, draft) with simple rules so
the graph, tools, safety gate, approval flow and eval gate can be exercised
offline. Scores produced with it are NOT a measure of model quality.
"""
from __future__ import annotations

import re
from collections import Counter

from app.data_gen.catalog import BY_CODE
from app.models import ESCALATE_MESSAGE

MACHINE_RE = re.compile(r"\b(CP)[-\s]?(\d{1,2})\b", re.I)
CODE_RE = re.compile(r"\bPF[-\s]?(\d{3})\b", re.I)

CONCEPTS = {
    "vibration": r"vibrat|shak(e|ing)",
    "bearing_heat": r"bearing.{0,40}(hot|temperature|overheat|\d{2}\s?c\b)|(hot|overheat).{0,30}bearing",
    "leak": r"leak|drip",
    "cavitation": r"gravel|marbles|crackl|cavitat|suction pressure",
    "low_output": r"low (discharge )?(pressure|flow)|pressure is low|not making pressure|flow has dropped|weak|low head",
    "overload": r"overload|high current|amps|current .{0,15}\d+ ?a\b|tripping",
    "no_flow": r"prime|no flow|nothing coming out|dry",
    "high_pressure": r"pressure (too|very) high|very high|deadhead|high pressure",
    "motor_heat": r"motor.{0,30}(hot|overheat|thermistor)|thermistor",
    "coupling": r"coupling",
    "sensor": r"sensor|signal|transmitter|reading jumping|disagree",
    "noise": r"noise|grinding|rattl|knock|clunk|sound",
}
SCOPE_WORDS = r"pump|motor|seal|bearing|impeller|coupling|casing|valve|strainer|fault|alarm|trip|machine|shaft|controller"

CAUSE_TEXT_TO_CATEGORY = {c.text: c.category for fc in BY_CODE.values() for c in fc.causes}


def _concepts(text: str) -> list[str]:
    t = text.lower()
    return [name for name, pat in CONCEPTS.items() if re.search(pat, t)]


def triage(payload: dict) -> dict:
    text = payload["report"]
    m = MACHINE_RE.search(text)
    c = CODE_RE.search(text)
    concepts = _concepts(text)
    in_scope = bool(m or c or concepts or re.search(SCOPE_WORDS, text, re.I))
    return {
        "in_scope": in_scope,
        "machine_id": f"CP-{int(m.group(2)):02d}" if m else None,
        "fault_code": f"PF-{c.group(1)}" if c else None,
        "symptom_concepts": concepts,
        "symptom_summary": text.strip()[:300],
    }


def _called(obs: list[dict], tool: str, **match) -> bool:
    return any(o["tool"] == tool and all(o["args"].get(k) == v for k, v in match.items()) for o in obs)


def _candidate_code(obs: list[dict]) -> tuple[str | None, float]:
    recs = [r for o in obs if o["tool"] == "find_similar_faults" for r in o["result"].get("records", [])]
    codes = [r["fault_code"] for r in recs if r.get("fault_code")]
    if not codes:
        return None, 0.0
    code, n = Counter(codes).most_common(1)[0]
    return code, n / len(recs)


def next_action(payload: dict) -> dict:
    tri, obs = payload["triage"], payload["observations"]
    code = tri.get("fault_code")
    if code and not _called(obs, "lookup_fault_code", code=code):
        return {"tool": "lookup_fault_code", "args": {"code": code}}
    if not _called(obs, "find_similar_faults"):
        return {"tool": "find_similar_faults", "args": {"symptom_text": payload["report"], "k": 8}}
    if not code:
        cand, share = _candidate_code(obs)
        if cand and share >= 0.5 and not _called(obs, "lookup_fault_code", code=cand):
            return {"tool": "lookup_fault_code", "args": {"code": cand}}
    if not _called(obs, "search_manual"):
        info = _code_info(obs)
        query = payload["report"] + (f" {info['code']} {info['name']}" if info else "")
        return {"tool": "search_manual", "args": {"query": query, "k": 5}}
    if tri.get("machine_id") and not _called(obs, "get_fault_history"):
        return {"tool": "get_fault_history", "args": {"machine_id": tri["machine_id"], "limit": 10}}
    return {"tool": "finish", "args": {}}


def _code_info(obs: list[dict]) -> dict | None:
    for o in reversed(obs):
        if o["tool"] == "lookup_fault_code" and o["result"].get("found"):
            return o["result"]
    return None


def _missing(tri: dict, report: str) -> list[str]:
    out = []
    if not tri.get("machine_id"):
        out.append("Machine ID (for example CP-03)")
    if not tri.get("fault_code"):
        out.append("Fault code shown on the controller, if any")
    if not re.search(r"\d", re.sub(r"(CP|PF)[-\s]?\d+", "", report, flags=re.I)):
        out.append("Measured values (vibration mm/s, temperatures, pressures, motor current)")
    return out


def draft(payload: dict) -> dict:
    tri, obs, report = payload["triage"], payload["observations"], payload["report"]
    info = _code_info(obs)
    explicit = bool(tri.get("fault_code"))
    cand, share = _candidate_code(obs)
    missing = _missing(tri, report)
    thin = info is None or (not explicit and (not tri.get("symptom_concepts") or share < 0.5))
    if thin:
        return {"status": "escalate", "summary": "Evidence is too thin to rank causes.", "causes": [], "checks": [],
                "confidence": "low", "missing_information": missing, "escalation_message": ESCALATE_MESSAGE}

    similar = [r for o in obs if o["tool"] == "find_similar_faults" for r in o["result"]["records"]]
    history = [r for o in obs if o["tool"] == "get_fault_history" for r in o["result"]["records"]]
    support = [r for r in similar + history if r.get("fault_code") == info["code"]]
    scored = []
    for i, text in enumerate(info["likely_causes"]):
        cat = CAUSE_TEXT_TO_CATEGORY.get(text)
        recs = [r for r in support if cat and r.get("root_cause") == cat]
        uniq = list({r["record_id"]: r for r in recs}.values())
        scored.append((len(uniq) + 1.0 / (i + 1), text, cat, uniq))
    scored.sort(key=lambda x: -x[0])
    page = str(info["page"])
    causes = []
    for rank, (_, text, cat, recs) in enumerate(scored[:3], 1):
        cites = [{"source": "manual", "ref": page, "quote": text}]
        cites += [{"source": "record", "ref": r["record_id"], "quote": r["root_cause"]} for r in recs[:2]]
        causes.append({"rank": rank, "cause": text, "category": cat, "citations": cites})
    checks = [{"check": c, "citations": [{"source": "manual", "ref": page, "quote": c}]} for c in info["checks"][:3]]
    top_support = len(scored[0][3]) if scored else 0
    confidence = "high" if explicit and top_support >= 3 else "medium" if top_support >= 1 else "low"
    return {"status": "proposed",
            "summary": f"{info['code']} {info['name']}: {len(causes)} likely causes ranked by manual order and similar past faults.",
            "causes": causes, "checks": checks, "confidence": confidence, "missing_information": missing}


def run(task: str, payload: dict) -> dict:
    return {"triage": triage, "next_action": next_action, "draft": draft}[task](payload)
