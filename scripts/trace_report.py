"""Summarise run traces: runs, latency, tokens, cost, failures, tool-call counts.

Usage: python -m scripts.trace_report [trace_dir]   (default: TRACE_DIR, i.e. traces/)
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean, median

from app.config import get_settings


def summarise(trace_dir: Path) -> dict:
    files = sorted(trace_dir.glob("run_*.json"))
    traces = [json.loads(f.read_text(encoding="utf-8")) for f in files]
    if not traces:
        return {"runs": 0}
    lat = [t["totals"]["latency_ms"] for t in traces]
    costs = [t["totals"]["cost_usd"] for t in traces]
    statuses = Counter((t.get("outputs") or {}).get("status") or "error" for t in traces)
    tools = Counter(e["tool"] for t in traces for e in t["events"] if e["type"] == "tool_call")
    return {
        "runs": len(traces),
        "statuses": dict(statuses),
        "failed_runs": sum(n for s, n in statuses.items() if s in ("error", None)),
        "latency_ms": {"mean": round(mean(lat), 1), "median": round(median(lat), 1), "max": round(max(lat), 1)},
        "tokens": {"input": sum(t["totals"]["input_tokens"] for t in traces),
                   "output": sum(t["totals"]["output_tokens"] for t in traces)},
        "cost_per_run_usd": None if any(c is None for c in costs) else round(mean(costs), 6),
        "tool_calls_total": sum(tools.values()),
        "tool_calls_by_tool": dict(tools),
        "avg_tool_calls_per_run": round(sum(tools.values()) / len(traces), 2),
    }


def main() -> int:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else get_settings().trace_dir
    print(f"Trace report for {folder}")
    print(json.dumps(summarise(folder), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
