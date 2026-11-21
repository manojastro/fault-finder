"""PostgreSQL store: pgvector for vectors, built-in full-text search for keywords."""
from __future__ import annotations

import json

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.store.base import FAULT_FIELDS, Store, fault_search_text, query_words


def schema(dim: int) -> str:
    return f"""
CREATE EXTENSION IF NOT EXISTS vector;
CREATE TABLE IF NOT EXISTS pages (page INT PRIMARY KEY, source TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id TEXT PRIMARY KEY, page INT, section TEXT, text TEXT, source TEXT,
  search_text TEXT, embedding vector({dim}),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED);
CREATE INDEX IF NOT EXISTS chunks_tsv_idx ON chunks USING GIN (tsv);
CREATE TABLE IF NOT EXISTS fault_codes (code TEXT PRIMARY KEY, data JSONB);
CREATE TABLE IF NOT EXISTS machines (machine_id TEXT PRIMARY KEY, data JSONB);
CREATE TABLE IF NOT EXISTS faults (
  record_id TEXT PRIMARY KEY, date TEXT, machine_id TEXT, symptom TEXT, fault_code TEXT,
  root_cause TEXT, fix TEXT, downtime_hours REAL, notes TEXT, search_text TEXT, embedding vector({dim}),
  tsv tsvector GENERATED ALWAYS AS (to_tsvector('english', search_text)) STORED);
CREATE INDEX IF NOT EXISTS faults_tsv_idx ON faults USING GIN (tsv);
CREATE INDEX IF NOT EXISTS faults_machine_idx ON faults (machine_id, date DESC);
CREATE TABLE IF NOT EXISTS reports (report_id TEXT PRIMARY KEY, created_at TIMESTAMPTZ, status TEXT, data JSONB);
CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, report_id TEXT REFERENCES reports(report_id),
  created_at TIMESTAMPTZ, data JSONB);
"""


def _vec(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.6f}" for x in v) + "]"


class PgStore(Store):
    backend = "postgres"

    def __init__(self, url: str):
        self.conn = psycopg.connect(url, autocommit=True, row_factory=dict_row)

    def init_schema(self, dim: int) -> None:
        self.conn.execute(schema(dim))

    def _strip(self, row: dict) -> dict:
        return {k: v for k, v in row.items() if k not in ("embedding", "tsv", "search_text", "score", "q")}

    # manual -----------------------------------------------------------------
    def replace_manual(self, pages, chunks, embeddings, fault_codes):
        with self.conn.transaction():
            for t in ("pages", "chunks", "fault_codes"):
                self.conn.execute(f"DELETE FROM {t}")
            with self.conn.cursor() as cur:
                cur.executemany("INSERT INTO pages VALUES (%s,%s,%s)", [(p.number, p.source, p.text) for p in pages])
                cur.executemany(
                    "INSERT INTO chunks (chunk_id,page,section,text,source,search_text,embedding) VALUES (%s,%s,%s,%s,%s,%s,%s::vector)",
                    [(c.chunk_id, c.page, c.section, c.text, c.source, c.search_text, _vec(e)) for c, e in zip(chunks, embeddings)],
                )
                cur.executemany("INSERT INTO fault_codes VALUES (%s,%s)", [(f["code"], Jsonb(f)) for f in fault_codes])

    def keyword_search(self, table, query, k):
        words = query_words(query)
        if not words:
            return []
        rows = self.conn.execute(
            f"SELECT *, ts_rank_cd(tsv, q) AS score FROM {table}, to_tsquery('english', %s) q "
            f"WHERE tsv @@ q ORDER BY score DESC LIMIT %s",
            (" | ".join(words), k),
        ).fetchall()
        return [(self._strip(r), float(r["score"])) for r in rows]

    def vector_search(self, table, vector, k):
        rows = self.conn.execute(
            f"SELECT *, 1 - (embedding <=> %s::vector) AS score FROM {table} ORDER BY embedding <=> %s::vector LIMIT %s",
            (_vec(vector), _vec(vector), k),
        ).fetchall()
        return [(self._strip(r), float(r["score"])) for r in rows]

    def get_page(self, page):
        r = self.conn.execute("SELECT text FROM pages WHERE page=%s", (page,)).fetchone()
        return r["text"] if r else None

    def get_fault_code(self, code):
        r = self.conn.execute("SELECT data FROM fault_codes WHERE code=%s", (code.upper(),)).fetchone()
        return r["data"] if r else None

    def list_fault_codes(self):
        return [r["data"] for r in self.conn.execute("SELECT data FROM fault_codes ORDER BY code")]

    # faults -----------------------------------------------------------------
    def replace_fault_data(self, machines, records, embeddings):
        cols = ",".join(FAULT_FIELDS)
        ph = ",".join(["%s"] * len(FAULT_FIELDS))
        with self.conn.transaction():
            self.conn.execute("DELETE FROM faults")
            self.conn.execute("DELETE FROM machines")
            with self.conn.cursor() as cur:
                cur.executemany("INSERT INTO machines VALUES (%s,%s)", [(m["machine_id"], Jsonb(m)) for m in machines])
                cur.executemany(
                    f"INSERT INTO faults ({cols},search_text,embedding) VALUES ({ph},%s,%s::vector)",
                    [tuple(r.get(f) for f in FAULT_FIELDS) + (fault_search_text(r), _vec(e)) for r, e in zip(records, embeddings)],
                )

    def get_machine(self, machine_id):
        r = self.conn.execute("SELECT data FROM machines WHERE machine_id=%s", (machine_id.upper(),)).fetchone()
        return r["data"] if r else None

    def get_fault_history(self, machine_id, limit):
        rows = self.conn.execute(
            "SELECT * FROM faults WHERE machine_id=%s ORDER BY date DESC, record_id DESC LIMIT %s", (machine_id.upper(), limit)
        ).fetchall()
        return [self._strip(r) for r in rows]

    def get_fault_record(self, record_id):
        r = self.conn.execute("SELECT * FROM faults WHERE record_id=%s", (record_id,)).fetchone()
        return self._strip(r) if r else None

    def count(self, table):
        return self.conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"]

    # reports ----------------------------------------------------------------
    def save_report(self, report):
        self.conn.execute(
            "INSERT INTO reports VALUES (%s,%s,%s,%s) ON CONFLICT (report_id) DO UPDATE SET status=EXCLUDED.status, data=EXCLUDED.data",
            (report["report_id"], report["created_at"], report["status"], Jsonb(json.loads(json.dumps(report, default=str)))),
        )

    def get_report(self, report_id):
        r = self.conn.execute("SELECT data, status FROM reports WHERE report_id=%s", (report_id,)).fetchone()
        if not r:
            return None
        d = r["data"]
        d["status"] = r["status"]
        return d

    def set_report_status(self, report_id, status):
        rep = self.get_report(report_id)
        rep["status"] = status
        self.save_report(rep)

    def add_decision(self, decision):
        self.conn.execute(
            "INSERT INTO decisions VALUES (%s,%s,%s,%s)",
            (decision["decision_id"], decision["report_id"], decision["created_at"], Jsonb(json.loads(json.dumps(decision, default=str)))),
        )

    def list_decisions(self, report_id):
        rows = self.conn.execute("SELECT data FROM decisions WHERE report_id=%s ORDER BY created_at", (report_id,))
        return [r["data"] for r in rows]
