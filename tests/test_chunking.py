"""
Tests for Phase 3: ChunkingEngine, ChunkValidator, PageIndex builder, vector store.
"""
from pathlib import Path

import pytest

from src.agents.chunker import ChunkingEngine, ChunkValidator
from src.agents.indexer import build_page_index, save_page_index
from src.models.chunking import LDU, ChunkType
from src.models.extraction import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    PageRef,
    Table,
    TextBlock,
)
from src.data.vector_store import VectorStore, pageindex_top_sections
from src.models.pageindex import PageIndex, SectionNode


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_chunk_validator_pass():
    ldus = [
        LDU(content="Hello", chunk_type=ChunkType.PARAGRAPH, token_count=1, content_hash="abc"),
    ]
    violations = ChunkValidator.validate(ldus, max_tokens_per_ldu=512)
    assert violations == []


def test_chunk_validator_violation_max_tokens():
    ldus = [
        LDU(content="x" * 1000, chunk_type=ChunkType.PARAGRAPH, token_count=600, content_hash="abc"),
    ]
    violations = ChunkValidator.validate(ldus, max_tokens_per_ldu=512)
    assert len(violations) >= 1 and "token_count" in violations[0]


def test_chunking_engine_single_page():
    doc = ExtractedDocument(
        doc_id="test_doc",
        file_name="test.pdf",
        pages=[
            ExtractedPage(
                page_no=1,
                text_blocks=[TextBlock(text="First paragraph.\n\nSecond paragraph.", page_ref=PageRef(page_no=1))],
                raw_text="First paragraph.\n\nSecond paragraph.",
            )
        ],
    )
    engine = ChunkingEngine()
    ldus = engine.run(doc)
    assert len(ldus) >= 1
    assert all(l.content_hash for l in ldus)
    assert any(l.chunk_type == ChunkType.PARAGRAPH for l in ldus)


def test_chunking_engine_table_one_ldu():
    doc = ExtractedDocument(
        doc_id="test_doc",
        file_name="test.pdf",
        pages=[
            ExtractedPage(
                page_no=1,
                tables=[
                    Table(headers=["A", "B"], rows=[["1", "2"], ["3", "4"]], page_ref=PageRef(page_no=1)),
                ],
                raw_text="",
            )
        ],
    )
    engine = ChunkingEngine()
    ldus = engine.run(doc)
    table_ldus = [l for l in ldus if l.chunk_type == ChunkType.TABLE]
    assert len(table_ldus) == 1
    assert "A" in table_ldus[0].content and "1" in table_ldus[0].content
    assert table_ldus[0].table_id


def test_build_page_index():
    doc = ExtractedDocument(doc_id="test", file_name="t.pdf", pages=[ExtractedPage(page_no=1, raw_text="")])
    ldus = [
        LDU(ldu_id="1", content="Introduction", chunk_type=ChunkType.SECTION_HEADER, page_refs=[PageRef(page_no=1)], parent_section="Introduction", token_count=1, content_hash="h1"),
        LDU(ldu_id="2", content="Some text.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=1)], parent_section="Introduction", token_count=2, content_hash="h2"),
    ]
    pi = build_page_index(doc, ldus)
    assert pi.doc_id == "test"
    assert len(pi.sections) >= 1
    assert pi.sections[0].title == "Introduction"
    assert pi.sections[0].page_start == 1


def test_save_page_index(repo_root, tmp_path):
    pi = PageIndex(doc_id="test", file_name="t.pdf", sections=[SectionNode(title="S1", page_start=1, page_end=1)])
    path = save_page_index(pi, tmp_path)
    assert path.exists()
    assert path.name == "test.json"


def test_vector_store_ingest_and_search(tmp_path):
    try:
        import chromadb
    except ImportError:
        pytest.skip("chromadb not installed")
    ldus = [
        LDU(ldu_id="a", content="Revenue was high.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=1)], token_count=3, content_hash="x"),
        LDU(ldu_id="b", content="Costs increased.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=2)], token_count=2, content_hash="y"),
    ]
    store = VectorStore(persist_path=tmp_path / "chroma")
    n = store.ingest_ldus(ldus, "doc1")
    assert n == 2
    results = store.search("revenue", n_results=2)
    assert len(results) >= 1
    assert results[0]["metadata"]["doc_id"] == "doc1"


def test_pageindex_top_sections():
    pi = PageIndex(
        doc_id="d",
        file_name="f",
        sections=[
            SectionNode(title="Revenue and profit", page_start=1, page_end=2, summary="Financial results."),
            SectionNode(title="Appendix", page_start=3, page_end=3, summary="Extra data."),
        ],
    )
    titles = pageindex_top_sections(pi, "revenue profit", top_k=2)
    assert "Revenue and profit" in titles
