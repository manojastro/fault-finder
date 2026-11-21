"""Hybrid search: keyword + vector, fused with Reciprocal Rank Fusion, then a
swappable rerank step. Works for manual chunks and for fault records."""
from __future__ import annotations

from typing import Callable, Protocol

from app.llm import tokenize
from app.store import Store

RRF_K = 60


class Reranker(Protocol):
    def __call__(self, query: str, items: list[tuple[dict, float]], text_of: Callable[[dict], str]) -> list[tuple[dict, float]]: ...


def no_rerank(query, items, text_of):
    return items


def overlap_rerank(query, items, text_of):
    """Small, explainable rerank: fused score plus a bonus for query-term coverage.
    Exact fault-code matches get a strong boost because codes are high-precision."""
    q = set(tokenize(query))
    codes = {t for t in q if "-" in t}
    out = []
    for row, score in items:
        toks = set(tokenize(text_of(row)))
        coverage = len(q & toks) / (len(q) or 1)
        bonus = 0.5 if codes and codes & toks else 0.0
        out.append((row, score * (1 + coverage) + bonus * score))
    return sorted(out, key=lambda x: -x[1])


RERANKERS: dict[str, Reranker] = {"none": no_rerank, "overlap": overlap_rerank}


def _key(table: str, row: dict) -> str:
    return row["chunk_id"] if table == "chunks" else row["record_id"]


def hybrid_search(
    store: Store, embedder, table: str, query: str, k: int, mode: str = "hybrid", reranker: str = "overlap",
    text_of: Callable[[dict], str] | None = None,
) -> list[tuple[dict, float]]:
    """mode: 'hybrid' | 'keyword' | 'vector'. Returns (row, score) best first."""
    text_of = text_of or (lambda r: f"{r.get('section', '')} {r.get('text') or r.get('symptom', '')}")
    pool = max(k * 4, 20)
    lists: list[list[tuple[dict, float]]] = []
    if mode in ("hybrid", "keyword"):
        lists.append(store.keyword_search(table, query, pool))
    if mode in ("hybrid", "vector"):
        lists.append(store.vector_search(table, embedder.embed([query])[0], pool))
    fused: dict[str, list] = {}
    for results in lists:
        for rank, (row, _) in enumerate(results):
            entry = fused.setdefault(_key(table, row), [row, 0.0])
            entry[1] += 1.0 / (RRF_K + rank + 1)
    items = sorted(((r, s) for r, s in fused.values()), key=lambda x: -x[1])
    items = RERANKERS[reranker](query, items, text_of)
    return items[:k]
