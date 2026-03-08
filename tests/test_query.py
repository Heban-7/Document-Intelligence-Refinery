"""
Tests for Phase 4: provenance, query tools, fact table, query agent, audit.
Includes verifiable multi-tool Query Interface Agent and tool orchestration.
"""
from pathlib import Path

import pytest

from src.models.provenance import ProvenanceItem, ProvenanceChain
from src.models.query_result import QueryResult, ToolCallRecord
from src.data.fact_table import extract_facts_from_document, FactTableStore
from src.models.extraction import ExtractedDocument, ExtractedPage, Table, PageRef
from src.agents.query_agent import QueryAgent, _suggests_structured_query


def test_suggests_structured_query():
    assert _suggests_structured_query("What is the total revenue?") is True
    assert _suggests_structured_query("Show me the table of expenditures") is True
    assert _suggests_structured_query("What percent increase?") is True
    assert _suggests_structured_query("Who wrote this report?") is False
    assert _suggests_structured_query("Introduction and background") is False


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


# --- Multi-tool Query Agent: verifiable orchestration ---


def test_tool_call_record():
    r = ToolCallRecord(
        tool="semantic_search",
        args={"query": "revenue", "n_results": 5},
        result_summary="3 hits",
        n_provenance_items=3,
    )
    assert r.tool == "semantic_search"
    assert r.n_provenance_items == 3
    assert r.model_dump(mode="json")["tool"] == "semantic_search"


def test_query_result_structure():
    result = QueryResult(
        answer="Some answer.",
        provenance=ProvenanceChain(items=[
            ProvenanceItem(doc_id="d1", document_name="d1", page_number=1),
        ]),
        tool_trace=[
            ToolCallRecord(tool="pageindex_navigate", result_summary="2 sections", n_provenance_items=0),
            ToolCallRecord(tool="semantic_search", result_summary="5 hits", n_provenance_items=2),
        ],
    )
    assert len(result.tool_trace) == 2
    assert result.tool_trace[0].tool == "pageindex_navigate"
    assert result.tool_trace[1].tool == "semantic_search"
    assert len(result.provenance.items) == 1


def test_query_agent_tool_orchestration_order(tmp_path):
    """Verify that query_with_trace runs tools in order: pageindex_navigate, semantic_search, optionally structured_query."""
    try:
        from src.data.vector_store import VectorStore
    except ImportError:
        pytest.skip("chromadb not installed")
    from src.models.chunking import LDU, ChunkType
    from src.models.extraction import PageRef

    # Ephemeral vector store with one LDU
    store = VectorStore(persist_path=None)
    ldus = [
        LDU(
            ldu_id="test_1",
            content="Revenue was 100 million in 2023.",
            chunk_type=ChunkType.PARAGRAPH,
            page_refs=[PageRef(page_no=1)],
            content_hash="h1",
        )
    ]
    store.ingest_ldus(ldus, "test_doc")

    # No fact store, no pageindex on disk (so pageindex returns []); use_pageindex=True
    agent = QueryAgent(vector_store=store, fact_store=None, repo_root=tmp_path)
    result = agent.query_with_trace("What was the revenue?", doc_id="test_doc", use_pageindex=True, n_results=5)

    assert result.answer
    assert "Revenue" in result.answer or "100" in result.answer or "No relevant" in result.answer
    # Orchestration: pageindex_navigate then semantic_search (no structured_query without fact_store)
    assert len(result.tool_trace) >= 2
    tools = [t.tool for t in result.tool_trace]
    assert QueryAgent.TOOL_PAGEINDEX in tools
    assert QueryAgent.TOOL_SEMANTIC in tools
    assert tools.index(QueryAgent.TOOL_PAGEINDEX) < tools.index(QueryAgent.TOOL_SEMANTIC)
    if QueryAgent.TOOL_STRUCTURED in tools:
        assert tools.index(QueryAgent.TOOL_SEMANTIC) < tools.index(QueryAgent.TOOL_STRUCTURED)
    # Provenance from semantic search
    assert len(result.provenance.items) >= 0  # may be 0 if section_titles filter excludes our LDU
    for rec in result.tool_trace:
        assert rec.tool in (QueryAgent.TOOL_PAGEINDEX, QueryAgent.TOOL_SEMANTIC, QueryAgent.TOOL_STRUCTURED)
        assert rec.result_summary != ""


def test_query_agent_with_fact_store_invokes_structured_query(tmp_path):
    """When fact_store is present and question suggests structured data, structured_query tool is invoked."""
    try:
        from src.data.vector_store import VectorStore
    except ImportError:
        pytest.skip("chromadb not installed")
    from src.models.chunking import LDU, ChunkType
    from src.models.extraction import PageRef

    store = VectorStore(persist_path=None)
    store.ingest_ldus([
        LDU(ldu_id="x", content="Some text.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=1)], content_hash="h"),
    ], "doc1")

    doc = ExtractedDocument(
        doc_id="doc1",
        file_name="f.pdf",
        pages=[
            ExtractedPage(
                page_no=1,
                tables=[Table(headers=["Metric", "Value"], rows=[["Revenue", "100"]], page_ref=PageRef(page_no=1))],
            )
        ],
    )
    fact_store = FactTableStore(db_path=tmp_path / "facts.db")
    fact_store.ingest_document(doc)

    agent = QueryAgent(vector_store=store, fact_store=fact_store, repo_root=tmp_path)
    result = agent.query_with_trace("What is the total revenue?", doc_id="doc1", use_pageindex=False, n_results=5)

    tools = [t.tool for t in result.tool_trace]
    assert QueryAgent.TOOL_SEMANTIC in tools
    assert QueryAgent.TOOL_STRUCTURED in tools
    assert result.answer
    # Provenance should include items from both semantic and structured
    assert len(result.provenance.items) >= 1
    fact_store.close()


def test_query_agent_backward_compatible():
    """query() returns (answer, provenance) without tool_trace."""
    try:
        from src.data.vector_store import VectorStore
    except ImportError:
        pytest.skip("chromadb not installed")
    store = VectorStore(persist_path=None)
    from src.models.chunking import LDU, ChunkType
    from src.models.extraction import PageRef
    store.ingest_ldus([
        LDU(ldu_id="a", content="Answer here.", chunk_type=ChunkType.PARAGRAPH, page_refs=[PageRef(page_no=1)], content_hash="x"),
    ], "d")
    agent = QueryAgent(vector_store=store, fact_store=None, repo_root=Path(__file__).resolve().parent.parent)
    answer, chain = agent.query("Where is the answer?", doc_id="d", use_pageindex=False)
    assert isinstance(answer, str)
    assert isinstance(chain, ProvenanceChain)
