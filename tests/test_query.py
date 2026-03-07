"""
Tests for Phase 4: provenance, query tools, fact table, query agent, audit.
"""
from pathlib import Path

import pytest

from src.models.provenance import ProvenanceItem, ProvenanceChain
from src.data.fact_table import extract_facts_from_document, FactTableStore
from src.models.extraction import ExtractedDocument, ExtractedPage, Table, PageRef


def test_provenance_chain():
    chain = ProvenanceChain(items=[
        ProvenanceItem(document_name="doc1", doc_id="doc1", page_number=1, content_hash="abc"),
    ], verified=True)
    assert len(chain.items) == 1
    assert chain.items[0].page_number == 1
    assert chain.verified


def test_extract_facts_from_document():
    doc = ExtractedDocument(
        doc_id="test",
        file_name="t.pdf",
        pages=[
            ExtractedPage(
                page_no=1,
                tables=[Table(headers=["A", "B"], rows=[["1", "2"]], page_ref=PageRef(page_no=1))],
            )
        ],
    )
    facts = extract_facts_from_document(doc)
    assert len(facts) == 1
    assert facts[0]["doc_id"] == "test"
    assert facts[0]["page_no"] == 1
    assert "content" in facts[0]


def test_fact_table_store_ingest_and_query(tmp_path):
    doc = ExtractedDocument(
        doc_id="test",
        file_name="t.pdf",
        pages=[
            ExtractedPage(
                page_no=1,
                tables=[Table(headers=["Metric", "Value"], rows=[["Revenue", "100"]], page_ref=PageRef(page_no=1))],
            )
        ],
    )
    store = FactTableStore(db_path=tmp_path / "facts.db")
    n = store.ingest_document(doc)
    assert n == 1
    rows = store.query_sql("SELECT * FROM facts WHERE doc_id = ?", ("test",))
    assert len(rows) == 1
    assert rows[0]["page_no"] == 1
    store.close()


def test_pageindex_navigate():
    from src.agents.query_tools import pageindex_navigate
    titles = pageindex_navigate("revenue", repo_root=Path(__file__).resolve().parent.parent)
    # May be empty if no pageindex exists
    assert isinstance(titles, list)
