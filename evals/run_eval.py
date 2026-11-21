"""`make eval`: run all cases, score them, compare with evals/baseline.json.

Exit code 0 = gate passed, 1 = gate failed.
  --save-baseline   accept the current scores as the new baseline
  --fresh           build a throwaway SQLite store (ingest + seed) instead of the configured one
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.agent.runner import Agent
from app.config import ROOT, Settings, get_settings
from app.safety.check import load_rules
from app.store import get_store
from evals.scorer import gate, score

EVAL_DIR = ROOT / "evals"
FAKE_LABEL = "offline baseline (fake model), not a quality measure"


def load_cases(path: Path = EVAL_DIR / "cases.yaml") -> list[dict]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))["cases"]


def load_config(path: Path = EVAL_DIR / "config.yaml") -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def fresh_store(settings: Settings, folder: Path):
    from app.data_gen.faults_gen import seed_store
    from app.retrieval.ingest import ingest

    settings.store_backend = "sqlite"
    settings.sqlite_path = folder / "eval.db"
    settings.synthetic_dir = folder / "synthetic"  # do not overwrite the committed data files
    store = get_store(settings)
    ingest(settings, store)
    seed_store(settings, store)
    return store


def run(settings: Settings, store, cases: list[dict], trace_dir: Path | None = None) -> dict:
    agent = Agent(settings, store, trace_dir=trace_dir)
    results = {}
    for c in cases:
        results[c["id"]] = agent.investigate(c["report"], run_id=f"eval-{c['id']}")
    _, stop_message, _ = load_rules(settings.safety_rules_path)
    metrics, rows = score(cases, results, store, stop_message)
    return {"metrics": metrics, "rows": rows, "results": results}


def print_table(metrics: dict, baseline: dict | None) -> None:
    base = (baseline or {}).get("scores", {})
    print(f"{'metric':<28}{'current':>12}{'baseline':>12}")
    for k, v in metrics.items():
        print(f"{k:<28}{str(v):>12}{str(base.get(k, '-')):>12}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--save-baseline", action="store_true")
    ap.add_argument("--fresh", action="store_true")
    ap.add_argument("--baseline", default=str(EVAL_DIR / "baseline.json"))
    args = ap.parse_args(argv)

    settings = get_settings()
    out_dir = EVAL_DIR / "results"
    out_dir.mkdir(exist_ok=True)
    tmp = None
    if args.fresh:
        tmp = tempfile.TemporaryDirectory()
        store = fresh_store(settings, Path(tmp.name))
    else:
        store = get_store(settings)
        if store.count("chunks") == 0 or store.count("faults") == 0:
            print("Store is empty. Run `make ingest` and `make seed` first, or use --fresh.", file=sys.stderr)
            return 2

    cases = load_cases()
    report = run(settings, store, cases, trace_dir=out_dir / "traces")
    metrics = report["metrics"]
    baseline_path = Path(args.baseline)
    baseline = json.loads(baseline_path.read_text()) if baseline_path.exists() else None
    config = load_config()

    print(f"FaultFinder eval: {len(cases)} SYNTHETIC cases | llm={settings.llm_provider} | store={store.backend}")
    if settings.llm_provider == "fake":
        print(f"NOTE: {FAKE_LABEL}")
    print_table(metrics, baseline)
    failed_rows = [r for r in report["rows"] if any(v is False for v in r.values())]
    if failed_rows:
        print("\nCases with a failed check:")
        for r in failed_rows:
            print("  ", r)

    (out_dir / "latest.json").write_text(json.dumps({"metrics": metrics, "rows": report["rows"]}, indent=1))

    if args.save_baseline:
        label = FAKE_LABEL if settings.llm_provider == "fake" else f"baseline ({settings.llm_provider} model)"
        baseline_path.write_text(json.dumps({
            "label": label, "created_at": datetime.now(timezone.utc).isoformat(), "llm_provider": settings.llm_provider,
            "store": store.backend, "cases_review_status": "DRAFTED BY BUILD AGENT - needs human review",
            "scores": metrics}, indent=1))
        print(f"\nBaseline saved to {baseline_path} ({label}).")

    ok, reasons = gate(metrics, baseline, config)
    print("\nEVAL GATE:", "PASS" if ok else "FAIL")
    for r in reasons:
        print("  -", r)
    if tmp:
        store_close = getattr(store, "db", None)
        if store_close is not None:
            store_close.close()
        tmp.cleanup()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
