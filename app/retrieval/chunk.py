"""Heading-aware chunking: a chunk never spans two sections or two pages, and
every chunk carries its section heading (also prepended to the text it is
searched by), so a hit on 'PF-104' also knows it sits under 'Cavitation detected'."""
from __future__ import annotations

from dataclasses import dataclass

from app.retrieval.parse import Page, is_heading

MAX_CHARS = 900


@dataclass
class Chunk:
    chunk_id: str
    page: int
    section: str
    text: str
    source: str

    @property
    def search_text(self) -> str:
        return f"{self.section}\n{self.text}"


def chunk_pages(pages: list[Page], max_chars: int = MAX_CHARS) -> list[Chunk]:
    chunks: list[Chunk] = []
    section = "Front matter"
    for page in pages:
        buf: list[str] = []

        def flush():
            body = "\n".join(buf).strip()
            if body:
                chunks.append(Chunk(f"{page.source}:p{page.number}:c{len(chunks)}", page.number, section, body, page.source))
            buf.clear()

        for line in page.text.splitlines():
            if line.startswith("SYNTHETIC DOCUMENT -"):  # per-page banner, not content
                continue
            if is_heading(line):
                flush()
                section = line.strip()
                continue
            if sum(len(x) + 1 for x in buf) + len(line) > max_chars:
                flush()
            buf.append(line)
        flush()
    return chunks
