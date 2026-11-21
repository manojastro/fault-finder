"""Run traces: one JSON file per run with inputs, tool calls, model calls,
outputs, tokens, latency and a cost estimate from config/prices.yaml."""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml


def load_prices(path: Path) -> dict:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")).get("models", {})
    except FileNotFoundError:
        return {}


class Tracer:
    def __init__(self, trace_dir: Path | None, prices_path: Path, inputs: dict, run_id: str | None = None):
        self.run_id = run_id or uuid.uuid4().hex[:12]
        self.trace_dir = trace_dir
        self.prices = load_prices(prices_path)
        self.started = time.perf_counter()
        self.data = {
            "run_id": self.run_id,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "inputs": inputs,
            "events": [],
        }

    def event(self, kind: str, **fields) -> None:
        self.data["events"].append({"type": kind, **fields})

    def tool_calls(self) -> list[dict]:
        return [e for e in self.data["events"] if e["type"] == "tool_call"]

    def llm_calls(self) -> list[dict]:
        return [e for e in self.data["events"] if e["type"] == "llm_call"]

    def _cost(self) -> float | None:
        total = 0.0
        for c in self.llm_calls():
            p = self.prices.get(c["model"]) or {}
            if p.get("input_per_1m") is None or p.get("output_per_1m") is None:
                return None
            total += c["input_tokens"] * p["input_per_1m"] / 1e6 + c["output_tokens"] * p["output_per_1m"] / 1e6
        return round(total, 6)

    def finish(self, outputs: dict) -> dict:
        llm = self.llm_calls()
        self.data["outputs"] = outputs
        self.data["totals"] = {
            "latency_ms": round((time.perf_counter() - self.started) * 1000, 2),
            "tool_calls": len(self.tool_calls()),
            "llm_calls": len(llm),
            "input_tokens": sum(c["input_tokens"] for c in llm),
            "output_tokens": sum(c["output_tokens"] for c in llm),
            "cost_usd": self._cost(),
        }
        if self.trace_dir is not None:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            path = self.trace_dir / f"run_{stamp}_{self.run_id}.json"
            path.write_text(json.dumps(self.data, indent=1, default=str), encoding="utf-8")
            self.data["trace_path"] = str(path)
        return self.data
