from app.data_gen.manual_gen import render
from app.retrieval.chunk import chunk_pages
from app.retrieval.ingest import extract_fault_codes
from app.retrieval.parse import parse_text
from app.retrieval.search import hybrid_search
from app.llm import HashEmbedder, tokenize


def test_parse_keeps_page_numbers():
    pages = parse_text(render(), "manual.txt")
    assert [p.number for p in pages] == list(range(1, 21))
    assert all("SYNTHETIC" in p.text for p in pages)


def test_chunks_carry_section_and_never_span_pages():
    pages = parse_text(render(), "manual.txt")
    chunks = chunk_pages(pages)
    entry = [c for c in chunks if c.section.startswith("8.4 PF-104")]
    assert entry and entry[0].page == 13
    assert "Blocked or fouled suction strainer" in entry[0].text
    for c in chunks:
        page_text = next(p.text for p in pages if p.number == c.page)
        assert c.text.splitlines()[0] in page_text


def test_fault_codes_extracted_from_manual():
    codes = {c["code"]: c for c in extract_fault_codes(parse_text(render(), "m.txt"))}
    assert len(codes) == 12
    assert codes["PF-103"]["page"] == 13
    assert codes["PF-103"]["likely_causes"][0] == "Worn mechanical seal faces"
    assert len(codes["PF-101"]["checks"]) == 4


def test_hybrid_search_returns_page_and_section(store, settings):
    hits = hybrid_search(store, HashEmbedder(256), "chunks", "noise like gravel, low suction pressure", 5)
    assert hits and all("page" in r and "section" in r for r, _ in hits)
    assert 13 in [r["page"] for r, _ in hits]


def test_keyword_and_vector_modes_work(store):
    for mode in ("keyword", "vector"):
        hits = hybrid_search(store, HashEmbedder(256), "chunks", "mechanical seal replacement", 3, mode=mode, reranker="none")
        assert hits, mode


def test_embedder_is_deterministic():
    e = HashEmbedder(64)
    assert e.embed(["bearing too hot"]) == e.embed(["bearing too hot"])
    assert tokenize("Vibrating bearings PF-101") == ["vibr", "bear", "pf-101"]
