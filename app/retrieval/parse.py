"""Parse a manual into pages, keeping the page number and section heading."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PAGE_MARKER = re.compile(r"^=== PAGE (\d+) ===\s*$", re.M)
# Numbered headings such as "4", "4.3 Suction piping and NPSH", "8.1 PF-101 High vibration".
HEADING = re.compile(r"^(\d{1,2}(?:\.\d{1,2})*)\s+([A-Z][^\n]{2,70})$")


@dataclass
class Page:
    number: int
    text: str
    source: str


def is_heading(line: str) -> bool:
    line = line.strip()
    return bool(HEADING.match(line)) and not line.endswith(".") and "|" not in line


def parse_text(text: str, source: str) -> list[Page]:
    marks = list(PAGE_MARKER.finditer(text))
    if not marks:  # no markers: treat the whole file as page 1
        return [Page(1, text.strip(), source)]
    pages = []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        pages.append(Page(int(m.group(1)), text[m.end() : end].strip(), source))
    return pages


def parse_pdf(path: Path) -> list[Page]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return [Page(i + 1, (p.extract_text() or "").strip(), path.name) for i, p in enumerate(reader.pages)]


def find_manual_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.exists():
        return []
    return sorted(p for p in path.iterdir() if p.suffix.lower() in {".pdf", ".txt"})


def load_manual(path: Path) -> list[Page]:
    pages: list[Page] = []
    for f in find_manual_files(path):
        if f.suffix.lower() == ".pdf":
            pages += parse_pdf(f)
        else:
            pages += parse_text(f.read_text(encoding="utf-8"), f.name)
    return pages
