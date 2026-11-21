"""Agent tools. Each has a Pydantic input and output schema and returns IDs
(manual page/chunk IDs or fault record IDs) so every claim can be cited."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import BaseModel, Field, ValidationError

from app.config import Settings
from app.retrieval.search import hybrid_search
from app.store import Store
from app.store.base import cosine, fault_search_text


@dataclass
class ToolContext:
    store: Store
    embedder: Any
    settings: Settings


# ----------------------------------------------------------------- schemas
class FaultRecord(BaseModel):
    record_id: str
    date: str
    machine_id: str
    symptom: str
    fault_code: str | None = None
    root_cause: str | None = None
    fix: str | None = None
    downtime_hours: float | None = None
    notes: str | None = None
    similarity: float | None = None


class GetFaultHistoryInput(BaseModel):
    machine_id: str = Field(pattern=r"^[A-Za-z]{1,4}-\d{1,4}$")
    limit: int = Field(default=10, ge=1, le=50)


class GetFaultHistoryOutput(BaseModel):
    machine_id: str
    machine_found: bool
    records: list[FaultRecord]


class FindSimilarFaultsInput(BaseModel):
    symptom_text: str = Field(min_length=3, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class FindSimilarFaultsOutput(BaseModel):
    records: list[FaultRecord]


class SearchManualInput(BaseModel):
    query: str = Field(min_length=2, max_length=2000)
    k: int = Field(default=5, ge=1, le=20)


class ManualPassage(BaseModel):
    chunk_id: str
    page: int
    section: str
    text: str
    score: float


class SearchManualOutput(BaseModel):
    passages: list[ManualPassage]


class LookupFaultCodeInput(BaseModel):
    code: str = Field(pattern=r"^[A-Za-z]{1,4}-\d{2,4}$")


class LookupFaultCodeOutput(BaseModel):
    code: str
    found: bool
    name: str | None = None
    trigger: str | None = None
    page: int | None = None
    likely_causes: list[str] = []
    checks: list[str] = []


# ----------------------------------------------------------------- tools
def get_fault_history(ctx: ToolContext, inp: GetFaultHistoryInput) -> GetFaultHistoryOutput:
    mid = inp.machine_id.upper()
    rows = ctx.store.get_fault_history(mid, inp.limit)
    return GetFaultHistoryOutput(
        machine_id=mid, machine_found=ctx.store.get_machine(mid) is not None, records=[FaultRecord(**r) for r in rows]
    )


def find_similar_faults(ctx: ToolContext, inp: FindSimilarFaultsInput) -> FindSimilarFaultsOutput:
    hits = hybrid_search(ctx.store, ctx.embedder, "faults", inp.symptom_text, inp.k,
                         reranker=ctx.settings.reranker, text_of=fault_search_text)
    # Report plain cosine similarity (0..1) so callers can judge how close a match is.
    qv = ctx.embedder.embed([inp.symptom_text])[0]
    texts = ctx.embedder.embed([fault_search_text(r) for r, _ in hits]) if hits else []
    return FindSimilarFaultsOutput(records=[
        FaultRecord(**row, similarity=round(cosine(qv, tv), 3)) for (row, _), tv in zip(hits, texts)
    ])


def search_manual(ctx: ToolContext, inp: SearchManualInput) -> SearchManualOutput:
    hits = hybrid_search(ctx.store, ctx.embedder, "chunks", inp.query, inp.k, reranker=ctx.settings.reranker)
    return SearchManualOutput(passages=[
        ManualPassage(chunk_id=r["chunk_id"], page=r["page"], section=r["section"], text=r["text"], score=round(s, 4))
        for r, s in hits
    ])


def lookup_fault_code(ctx: ToolContext, inp: LookupFaultCodeInput) -> LookupFaultCodeOutput:
    code = inp.code.upper()
    info = ctx.store.get_fault_code(code)
    if not info:
        return LookupFaultCodeOutput(code=code, found=False)
    return LookupFaultCodeOutput(code=code, found=True, name=info.get("name"), trigger=info.get("trigger"),
                                 page=info.get("page"), likely_causes=info.get("likely_causes", []),
                                 checks=info.get("checks", []))


TOOLS: dict[str, tuple[type[BaseModel], Callable]] = {
    "get_fault_history": (GetFaultHistoryInput, get_fault_history),
    "find_similar_faults": (FindSimilarFaultsInput, find_similar_faults),
    "search_manual": (SearchManualInput, search_manual),
    "lookup_fault_code": (LookupFaultCodeInput, lookup_fault_code),
}

TOOL_DESCRIPTIONS = {
    "get_fault_history": "get_fault_history(machine_id, limit=10): recent fault records for one machine, newest first.",
    "find_similar_faults": "find_similar_faults(symptom_text, k=5): past fault records with similar symptoms.",
    "search_manual": "search_manual(query, k=5): manual passages with page number and section.",
    "lookup_fault_code": "lookup_fault_code(code): the manual's entry for a fault code: trigger, likely causes, checks, page.",
}


def call_tool(ctx: ToolContext, name: str, args: dict) -> dict:
    """Validate input, run the tool, return a plain dict ({'error': ...} on bad input)."""
    if name not in TOOLS:
        return {"error": f"unknown tool '{name}'"}
    in_model, fn = TOOLS[name]
    try:
        inp = in_model(**(args or {}))
    except ValidationError as e:
        return {"error": "invalid input", "details": e.errors(include_url=False, include_context=False)}
    return fn(ctx, inp).model_dump()
