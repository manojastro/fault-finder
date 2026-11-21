"""SQLite fallback store (FTS5 for keywords, Python cosine for vectors).

Used by the tests and when Docker is not available. Same interface as PgStore."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.store.base import FAULT_FIELDS, Store, cosine, fault_search_text, query_words

SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (page INTEGER PRIMARY KEY, source TEXT, text TEXT);
CREATE TABLE IF NOT EXISTS chunks (chunk_id TEXT PRIMARY KEY, page INTEGER, section TEXT, text TEXT, source TEXT, embedding TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, body, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS fault_codes (code TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS machines (machine_id TEXT PRIMARY KEY, data TEXT);
CREATE TABLE IF NOT EXISTS faults (record_id TEXT PRIMARY KEY, date TEXT, machine_id TEXT, symptom TEXT, fault_code TEXT,
  root_cause TEXT, fix TEXT, downtime_hours REAL, notes TEXT, embedding TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS faults_fts USING fts5(record_id UNINDEXED, body, tokenize='porter unicode61');
CREATE TABLE IF NOT EXISTS reports (report_id TEXT PRIMARY KEY, created_at TEXT, status TEXT, data TEXT);
CREATE TABLE IF NOT EXISTS decisions (decision_id TEXT PRIMARY KEY, report_id TEXT, created_at TEXT, data TEXT);
"""


class SqliteStore(Store):
    backend = "sqlite"

    def __init__(self, path: Path | str):
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._vec_cache: dict[str, list[tuple[dict, list[float]]]] = {}

    def init_schema(self, dim: int) -> None:
        self.db.executescript(SCHEMA)
        self.db.commit()

    # manual -----------------------------------------------------------------
    def replace_manual(self, pages, chunks, embeddings, fault_codes):
        cur = self.db.cursor()
        for t in ("pages", "chunks", "chunks_fts", "fault_codes"):
            cur.execute(f"DELETE FROM {t}")
        cur.executemany("INSERT INTO pages VALUES (?,?,?)", [(p.number, p.source, p.text) for p in pages])
        cur.executemany(
            "INSERT INTO chunks VALUES (?,?,?,?,?,?)",
            [(c.chunk_id, c.page, c.section, c.text, c.source, json.dumps(e)) for c, e in zip(chunks, embeddings)],
        )
        cur.executemany("INSERT INTO chunks_fts VALUES (?,?)", [(c.chunk_id, c.search_text) for c in chunks])
        cur.executemany("INSERT INTO fault_codes VALUES (?,?)", [(f["code"], json.dumps(f)) for f in fault_codes])
        self.db.commit()
        self._vec_cache.pop("chunks", None)

    def _row(self, table: str, key: str) -> dict | None:
        id_col = "chunk_id" if table == "chunks" else "record_id"
        r = self.db.execute(f"SELECT * FROM {table} WHERE {id_col}=?", (key,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d.pop("embedding", None)
        return d

    def keyword_search(self, table, query, k):
        words = query_words(query)
        if not words:
            return []
        match = " OR ".join(f'"{w}"' for w in words)
        id_col = "chunk_id" if table == "chunks" else "record_id"
        rows = self.db.execute(
            f"SELECT {id_col} AS id, bm25({table}_fts) AS s FROM {table}_fts WHERE {table}_fts MATCH ? ORDER BY s LIMIT ?",
            (match, k),
        ).fetchall()
        return [(self._row(table, r["id"]), -r["s"]) for r in rows]

    def vector_search(self, table, vector, k):
        if table not in self._vec_cache:
            rows = self.db.execute(f"SELECT * FROM {table}").fetchall()
            items = []
            for r in rows:
                d = dict(r)
                emb = json.loads(d.pop("embedding"))
                items.append((d, emb))
            self._vec_cache[table] = items
        scored = [(d, cosine(vector, e)) for d, e in self._vec_cache[table]]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]

    def get_page(self, page):
        r = self.db.execute("SELECT text FROM pages WHERE page=?", (page,)).fetchone()
        return r["text"] if r else None

    def get_fault_code(self, code):
        r = self.db.execute("SELECT data FROM fault_codes WHERE code=?", (code.upper(),)).fetchone()
        return json.loads(r["data"]) if r else None

    def list_fault_codes(self):
        return [json.loads(r["data"]) for r in self.db.execute("SELECT data FROM fault_codes ORDER BY code")]

    # faults -----------------------------------------------------------------
    def replace_fault_data(self, machines, records, embeddings):
        cur = self.db.cursor()
        for t in ("machines", "faults", "faults_fts"):
            cur.execute(f"DELETE FROM {t}")
        cur.executemany("INSERT INTO machines VALUES (?,?)", [(m["machine_id"], json.dumps(m)) for m in machines])
        cur.executemany(
            f"INSERT INTO faults VALUES ({','.join('?' * (len(FAULT_FIELDS) + 1))})",
            [tuple(r.get(f) for f in FAULT_FIELDS) + (json.dumps(e),) for r, e in zip(records, embeddings)],
        )
        cur.executemany("INSERT INTO faults_fts VALUES (?,?)", [(r["record_id"], fault_search_text(r)) for r in records])
        self.db.commit()
        self._vec_cache.pop("faults", None)

    def get_machine(self, machine_id):
        r = self.db.execute("SELECT data FROM machines WHERE machine_id=?", (machine_id.upper(),)).fetchone()
        return json.loads(r["data"]) if r else None

    def get_fault_history(self, machine_id, limit):
        rows = self.db.execute(
            "SELECT * FROM faults WHERE machine_id=? ORDER BY date DESC, record_id DESC LIMIT ?", (machine_id.upper(), limit)
        ).fetchall()
        return [{k: v for k, v in dict(r).items() if k != "embedding"} for r in rows]

    def get_fault_record(self, record_id):
        return self._row("faults", record_id)

    def count(self, table):
        return self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    # reports ----------------------------------------------------------------
    def save_report(self, report):
        self.db.execute(
            "INSERT OR REPLACE INTO reports VALUES (?,?,?,?)",
            (report["report_id"], report["created_at"], report["status"], json.dumps(report, default=str)),
        )
        self.db.commit()

    def get_report(self, report_id):
        r = self.db.execute("SELECT data, status FROM reports WHERE report_id=?", (report_id,)).fetchone()
        if not r:
            return None
        d = json.loads(r["data"])
        d["status"] = r["status"]
        return d

    def set_report_status(self, report_id, status):
        rep = self.get_report(report_id)
        rep["status"] = status
        self.save_report(rep)

    def add_decision(self, decision):
        self.db.execute(
            "INSERT INTO decisions VALUES (?,?,?,?)",
            (decision["decision_id"], decision["report_id"], decision["created_at"], json.dumps(decision, default=str)),
        )
        self.db.commit()

    def list_decisions(self, report_id):
        rows = self.db.execute("SELECT data FROM decisions WHERE report_id=? ORDER BY created_at", (report_id,))
        return [json.loads(r["data"]) for r in rows]
