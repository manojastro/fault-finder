"""Storage interface shared by the PostgreSQL (pgvector) and SQLite backends."""
from __future__ import annotations

import math
import re
from abc import ABC, abstractmethod

WORD = re.compile(r"[a-z0-9]+")


def query_words(query: str, limit: int = 24) -> list[str]:
    from app.llm import STOPWORDS

    words = [w for w in WORD.findall(query.lower()) if w not in STOPWORDS and len(w) > 1]
    return list(dict.fromkeys(words))[:limit]


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(y * y for y in b)) or 1.0
    return dot / (na * nb)


class Store(ABC):
    backend = "base"

    # schema ---------------------------------------------------------------
    @abstractmethod
    def init_schema(self, dim: int) -> None: ...

    # manual ---------------------------------------------------------------
    @abstractmethod
    def replace_manual(self, pages: list, chunks: list, embeddings: list[list[float]], fault_codes: list[dict]) -> None: ...

    @abstractmethod
    def keyword_search(self, table: str, query: str, k: int) -> list[tuple[dict, float]]:
        """table is 'chunks' or 'faults'. Returns (row, score) best first."""

    @abstractmethod
    def vector_search(self, table: str, vector: list[float], k: int) -> list[tuple[dict, float]]: ...

    @abstractmethod
    def get_page(self, page: int) -> str | None: ...

    @abstractmethod
    def get_fault_code(self, code: str) -> dict | None: ...

    @abstractmethod
    def list_fault_codes(self) -> list[dict]: ...

    # fault history --------------------------------------------------------
    @abstractmethod
    def replace_fault_data(self, machines: list[dict], records: list[dict], embeddings: list[list[float]]) -> None: ...

    @abstractmethod
    def get_machine(self, machine_id: str) -> dict | None: ...

    @abstractmethod
    def get_fault_history(self, machine_id: str, limit: int) -> list[dict]: ...

    @abstractmethod
    def get_fault_record(self, record_id: str) -> dict | None: ...

    @abstractmethod
    def count(self, table: str) -> int: ...

    # reports and decisions ------------------------------------------------
    @abstractmethod
    def save_report(self, report: dict) -> None: ...

    @abstractmethod
    def get_report(self, report_id: str) -> dict | None: ...

    @abstractmethod
    def set_report_status(self, report_id: str, status: str) -> None: ...

    @abstractmethod
    def add_decision(self, decision: dict) -> None: ...

    @abstractmethod
    def list_decisions(self, report_id: str) -> list[dict]: ...


FAULT_FIELDS = ["record_id", "date", "machine_id", "symptom", "fault_code", "root_cause", "fix", "downtime_hours", "notes"]


def fault_search_text(r: dict) -> str:
    return f"{r['symptom']} {r.get('fault_code') or ''}"
