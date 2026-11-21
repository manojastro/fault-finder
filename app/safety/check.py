"""Safety gate. Plain code, runs FIRST, before any model call.

On a match the caller must return the fixed stop message and generate no AI answer.
The rule list lives in config/safety_rules.yaml and is PROVISIONAL."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml


@dataclass
class SafetyResult:
    is_safety_critical: bool
    matched_rules: list[str]
    message: str | None
    rules_status: str


@lru_cache(maxsize=8)
def _load(path: str, mtime: float):
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    rules = [(r["id"], [re.compile(p, re.I) for p in r["patterns"]]) for r in data["rules"]]
    return rules, data["stop_message"].strip(), data.get("status", "")


def load_rules(path: Path):
    return _load(str(path), path.stat().st_mtime)


def check_report(text: str, rules_path: Path) -> SafetyResult:
    rules, message, status = load_rules(rules_path)
    matched = [rid for rid, pats in rules if any(p.search(text) for p in pats)]
    return SafetyResult(bool(matched), matched, message if matched else None, status)
