"""
Tests for PageIndex: hierarchy, traversal API, topic-based navigation.
"""
from pathlib import Path

import pytest

from src.models.pageindex import (
    PageIndex,
    SectionNode,
    _parse_heading_level,
)
from src.agents.indexer import build_page_index
from src.models.chunking import LDU, ChunkType
from src.models.extraction import ExtractedDocument, ExtractedPage, PageRef
from src.agents.query_tools import load_page_index, pageindex_navigate, pageindex_navigate_with_paths
from src.data.vector_store import pageindex_top_sections


def test_parse_heading_level():
    assert _parse_heading_level("1. Introduction") == 1
    assert _parse_heading_level("1.1 Background") == 2
    assert _parse_heading_level("1.1.1 Details") == 3
    assert _parse_heading_level("2. Methods") == 1
    assert _parse_heading_level("Chapter 1") == 1
    assert _parse_heading_level("Introduction") == 1


def test_build_page_index_nested_sections():
    """Numbered headings (1., 1.1.) produce nested child_sections."""
    doc = ExtractedDocument(
        doc_id="nest",
        file_name="n.pdf",
        pages=[
            ExtractedPage(page_no=1, raw_text=""),
            ExtractedPage(page_no=2, raw_text=""),
            ExtractedPage(page_no=3, raw_text=""),
        ],
    )
    ldus = [
        LDU(ldu_id="h1", content="1. Introduction", chunk_type=ChunkType.SECTION_HEADER, page_refs=[PageRef(page_no=1)], parent_section="1. Introduction", token_count=1, content_hash="a"),
        LDU(ldu_id="p1", content="Intro text.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=1)], parent_section="1. Introduction", token_count=1, content_hash="b"),
        LDU(ldu_id="h2", content="1.1 Background", chunk_type=ChunkType.SECTION_HEADER, page_refs=[PageRef(page_no=2)], parent_section="1.1 Background", token_count=1, content_hash="c"),
        LDU(ldu_id="p2", content="Background text.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=2)], parent_section="1.1 Background", token_count=1, content_hash="d"),
        LDU(ldu_id="h3", content="2. Methods", chunk_type=ChunkType.SECTION_HEADER, page_refs=[PageRef(page_no=3)], parent_section="2. Methods", token_count=1, content_hash="e"),
    ]
    pi = build_page_index(doc, ldus)
    assert pi.doc_id == "nest"
    assert len(pi.sections) == 2  # "1. Introduction" and "2. Methods" at root
    intro = next(s for s in pi.sections if "Introduction" in s.title)
    assert intro.level == 1
    assert intro.section_id == "0"
    assert intro.path == "/1. Introduction"
    assert len(intro.child_sections) == 1
    assert intro.child_sections[0].title == "1.1 Background"
    assert intro.child_sections[0].section_id == "0.0"
    assert intro.child_sections[0].path == "/1. Introduction/1.1 Background"
    methods = next(s for s in pi.sections if "Methods" in s.title)
    assert methods.section_id == "1"
    assert methods.path == "/2. Methods"


def test_traversal_get_by_id_and_path():
    root = SectionNode(title="Root", page_start=1, page_end=2, level=1, section_id="0", path="/Root", child_sections=[
        SectionNode(title="Child", page_start=2, page_end=2, level=2, section_id="0.0", path="/Root/Child", child_sections=[]),
    ])
    pi = PageIndex(doc_id="d", file_name="f", sections=[root])
    assert pi.get_by_id("0").title == "Root"
    assert pi.get_by_id("0.0").title == "Child"
    assert pi.get_by_id("missing") is None
    assert pi.get_by_path("/Root").title == "Root"
    assert pi.get_by_path("/Root/Child").title == "Child"
    assert pi.get_by_path("Root/Child").title == "Child"


def test_flatten_depth_first():
    root = SectionNode(title="A", page_start=1, page_end=3, level=1, section_id="0", path="/A", child_sections=[
        SectionNode(title="B", page_start=2, page_end=2, level=2, section_id="0.0", path="/A/B", child_sections=[]),
    ])
    pi = PageIndex(doc_id="d", file_name="f", sections=[root])
    flat = pi.flatten_depth_first()
    assert len(flat) == 2
    assert flat[0] == (0, root)
    assert flat[1][0] == 1 and flat[1][1].title == "B"
    depths_and_titles = [(d, n.title) for d, n in pi.iter_depth_first()]
    assert depths_and_titles == [(0, "A"), (1, "B")]


def test_find_sections_by_topic():
    pi = PageIndex(
        doc_id="d",
        file_name="f",
        sections=[
            SectionNode(title="Revenue and profit", page_start=1, page_end=2, summary="Financial results and revenue growth.", key_entities=["Revenue"], section_id="0", path="/Revenue and profit"),
            SectionNode(title="Appendix", page_start=3, page_end=3, summary="Extra data.", section_id="1", path="/Appendix"),
        ],
    )
    hits = pi.find_sections_by_topic("revenue profit", top_k=2)
    assert len(hits) >= 1
    assert hits[0][1].title == "Revenue and profit"
    assert "revenue" in hits[0][2].lower() or "profit" in hits[0][2].lower()
    titles = pi.section_titles_for_topic("revenue", top_k=2)
    assert "Revenue and profit" in titles


def test_pageindex_top_sections_uses_tree():
    pi = PageIndex(
        doc_id="d",
        file_name="f",
        sections=[
            SectionNode(title="Financial results", page_start=1, page_end=2, summary="Revenue and costs.", section_id="0", path="/Financial results"),
        ],
    )
    titles = pageindex_top_sections(pi, "revenue financial", top_k=3)
    assert "Financial results" in titles


def test_pageindex_navigate_with_paths(tmp_path):
    """navigate_with_paths returns (title, path) and works when index is on disk."""
    from src.agents.indexer import save_page_index
    pi = PageIndex(
        doc_id="nav_doc",
        file_name="f",
        sections=[
            SectionNode(title="Executive Summary", page_start=1, page_end=1, summary="Revenue and strategy.", section_id="0", path="/Executive Summary"),
        ],
    )
    save_page_index(pi, tmp_path)
    index_dir = tmp_path / ".refinery" / "pageindex"
    path = index_dir / "nav_doc.json"
    assert path.exists()
    loaded = PageIndex.model_validate_json(path.read_text(encoding="utf-8"))
    pairs = loaded.find_sections_by_topic("executive revenue", top_k=2)
    assert len(pairs) >= 1
    assert pairs[0][1].title == "Executive Summary"
    result = pageindex_navigate_with_paths("executive", doc_id="nav_doc", repo_root=tmp_path, top_k=2)
    assert any(t == "Executive Summary" for t, _ in result)
