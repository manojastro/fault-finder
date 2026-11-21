"""Command line: ingest | seed | ask "question" | investigate "fault report" | tool NAME JSON"""
from __future__ import annotations

import argparse
import json
import sys

from app.config import get_settings
from app.llm import get_embedder
from app.store import get_store


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="faultfinder")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("ingest", help="parse, chunk, embed and store the manual")
    sub.add_parser("seed", help="generate and load the SYNTHETIC fault history")
    a = sub.add_parser("ask", help="search the manual and print passages with page numbers")
    a.add_argument("question")
    a.add_argument("-k", type=int, default=5)
    a.add_argument("--mode", choices=["hybrid", "keyword", "vector"], default="hybrid")
    inv = sub.add_parser("investigate", help="run the agent on a fault report (no approval step)")
    inv.add_argument("report")
    t = sub.add_parser("tool", help="call one tool directly, e.g. tool lookup_fault_code '{\"code\":\"PF-101\"}'")
    t.add_argument("name")
    t.add_argument("args", nargs="?", default="{}")
    args = p.parse_args(argv)

    settings = get_settings()
    store = get_store(settings)

    if args.cmd == "ingest":
        from app.retrieval.ingest import ingest

        print(json.dumps(ingest(settings, store), indent=2))
    elif args.cmd == "seed":
        from app.data_gen.faults_gen import seed_store

        if not store.list_fault_codes():
            print("No fault codes in the store. Run `make ingest` first.", file=sys.stderr)
            return 1
        print(json.dumps(seed_store(settings, store), indent=2))
    elif args.cmd == "ask":
        from app.retrieval.search import hybrid_search

        hits = hybrid_search(store, get_embedder(settings), "chunks", args.question, args.k, mode=args.mode,
                             reranker=settings.reranker)
        if not hits:
            print("No passages found.")
        for i, (row, score) in enumerate(hits, 1):
            print(f"[{i}] page {row['page']} | {row['section']} | score {score:.4f}")
            print("    " + row["text"].replace("\n", "\n    ")[:600])
            print()
    elif args.cmd == "tool":
        from app.tools import ToolContext, call_tool

        ctx = ToolContext(store, get_embedder(settings), settings)
        print(json.dumps(call_tool(ctx, args.name, json.loads(args.args)), indent=2, default=str))
    elif args.cmd == "investigate":
        from app.agent.runner import Agent

        result = Agent(settings, store).investigate(args.report)
        print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
