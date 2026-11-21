"""Compare keyword-only, vector-only and hybrid manual search on the 25 normal
eval cases: is the expected page in the top k? Prints one table.

Usage: python -m scripts.compare_retrieval [--k 5] [--fresh]
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from app.config import get_settings
from app.llm import get_embedder
from app.retrieval.search import hybrid_search
from app.store import get_store
from evals.run_eval import fresh_store, load_cases


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--fresh", action="store_true")
    args = ap.parse_args(argv)
    settings = get_settings()
    tmp = tempfile.TemporaryDirectory() if args.fresh else None
    store = fresh_store(settings, Path(tmp.name)) if tmp else get_store(settings)
    emb = get_embedder(settings)
    cases = [c for c in load_cases() if c["type"] == "normal"]
    modes = [("keyword", "none"), ("vector", "none"), ("hybrid", "none"), ("hybrid", "overlap")]
    hits = {m: 0 for m in modes}
    print(f"Expected page in top {args.k} | {len(cases)} SYNTHETIC normal cases | embedder={emb.model if hasattr(emb, 'model') else emb}")
    print(f"{'case':<6}{'page':>5}  " + "  ".join(f"{m[0] + '+' + m[1]:>16}" for m in modes))
    for c in cases:
        cells = []
        for mode, rr in modes:
            pages = [r["page"] for r, _ in hybrid_search(store, emb, "chunks", c["report"], args.k, mode=mode, reranker=rr)]
            ok = c["expected_page"] in pages
            hits[(mode, rr)] += ok
            cells.append(f"{'hit' if ok else 'MISS':>16}")
        print(f"{c['id']:<6}{c['expected_page']:>5}  " + "  ".join(cells))
    print(f"{'total':<11}  " + "  ".join(f"{hits[m]:>13}/{len(cases)}" for m in modes))
    if tmp:
        store.db.close()
        tmp.cleanup()
    return 0


if __name__ == "__main__":
    sys.exit(main())
