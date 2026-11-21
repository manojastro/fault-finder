"""`make ingest`: parse the manual, chunk it, embed it, store it, and extract the
fault-code table so lookup_fault_code can answer from the manual itself."""
from __future__ import annotations

import re

from app.config import Settings
from app.data_gen.manual_gen import write_manual
from app.llm import get_embedder
from app.retrieval.chunk import chunk_pages
from app.retrieval.parse import Page, find_manual_files, load_manual
from app.store import Store

CODE = r"[A-Z]{1,4}-\d{2,4}"
TABLE_ROW = re.compile(rf"^({CODE})\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*$", re.M)
ENTRY_HEAD = re.compile(rf"^\d+(?:\.\d+)*\s+({CODE})\s+(.+)$")


def extract_fault_codes(pages: list[Page]) -> list[dict]:
    """Codes from the fault table plus causes/checks from troubleshooting entries."""
    codes: dict[str, dict] = {}
    for p in pages:
        for m in TABLE_ROW.finditer(p.text):
            codes.setdefault(m.group(1), {}).update(
                code=m.group(1), name=m.group(2), trigger=m.group(3), table_page=p.number
            )
    for p in pages:
        current, mode = None, None
        for line in p.text.splitlines():
            line = line.strip()
            head = ENTRY_HEAD.match(line)
            if head:
                current = codes.setdefault(head.group(1), {"code": head.group(1), "name": head.group(2)})
                current.update(page=p.number, likely_causes=[], checks=[])
                mode = None
            elif current is None:
                continue
            elif line.lower().startswith("likely causes"):
                mode = "likely_causes"
            elif line.lower().startswith("checks to run"):
                mode = "checks"
            elif line.startswith("- ") and mode:
                current[mode].append(line[2:].strip())
            elif line and not line.startswith("- ") and mode and not line.lower().startswith("trigger"):
                mode = None
    for c in codes.values():
        c.setdefault("page", c.get("table_page"))
        c.setdefault("likely_causes", [])
        c.setdefault("checks", [])
    return sorted(codes.values(), key=lambda c: c["code"])


def ingest(settings: Settings, store: Store) -> dict:
    generated = False
    if not find_manual_files(settings.manual_path):
        folder = settings.manual_path if settings.manual_path.suffix == "" else settings.manual_path.parent
        write_manual(folder)
        generated = True
    pages = load_manual(settings.manual_path)
    if not pages:
        raise RuntimeError(f"No pages parsed from {settings.manual_path}")
    chunks = chunk_pages(pages)
    embeddings = get_embedder(settings).embed([c.search_text for c in chunks])
    codes = extract_fault_codes(pages)
    store.replace_manual(pages, chunks, embeddings, codes)
    return {"pages": len(pages), "chunks": len(chunks), "fault_codes": len(codes), "generated_synthetic_manual": generated}
