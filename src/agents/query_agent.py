"""
Query Interface Agent: multi-tool orchestration for end-to-end question answering with provenance.
Tools: pageindex_navigate, semantic_search, structured_query. Every run produces a verifiable tool_trace.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.agents.query_tools import (
    load_page_index,
    pageindex_navigate,
    semantic_search,
    structured_query,
)
from src.data.vector_store import VectorStore
from src.data.fact_table import FactTableStore
from src.models.provenance import ProvenanceChain, ProvenanceItem
from src.models.query_result import QueryResult, ToolCallRecord


# Keywords that suggest the user may benefit from structured/fact-table query
_STRUCTURED_QUERY_HINTS = re.compile(
    r"\b(total|sum|revenue|expenditure|amount|figure|number|percent|table|row|column|metric|value)\b",
    re.I,
)


def _suggests_structured_query(question: str) -> bool:
    """Heuristic: question mentions numbers, tables, or aggregate concepts."""
    return bool(_STRUCTURED_QUERY_HINTS.search(question))


class QueryAgent:
    """
    Multi-tool Query Interface Agent. Orchestration order:
    1. pageindex_navigate (optional) → section titles to narrow retrieval
    2. semantic_search → vector search (with optional section filter)
    3. structured_query (optional) → fact table when available and question is numerical/tabular or vector hits weak
    Every invocation is recorded in tool_trace for verification.
    """

    TOOL_PAGEINDEX = "pageindex_navigate"
    TOOL_SEMANTIC = "semantic_search"
    TOOL_STRUCTURED = "structured_query"

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        fact_store: FactTableStore | None = None,
        repo_root: Path | None = None,
    ):
        self._vector = vector_store or VectorStore(
            persist_path=(repo_root or Path.cwd()) / ".refinery" / "vector_db"
        )
        self._facts = fact_store
        self._repo_root = Path(repo_root or Path.cwd())

    def query(
        self,
        question: str,
        doc_id: str | None = None,
        use_pageindex: bool = True,
        n_results: int = 5,
    ) -> tuple[str, ProvenanceChain]:
        """
        Answer the question; returns (answer_text, provenance_chain).
        Backward-compatible entry point; use query_with_trace() for tool_trace.
        """
        result = self.query_with_trace(
            question, doc_id=doc_id, use_pageindex=use_pageindex, n_results=n_results
        )
        return result.answer, result.provenance

    def query_with_trace(
        self,
        question: str,
        doc_id: str | None = None,
        use_pageindex: bool = True,
        n_results: int = 5,
    ) -> QueryResult:
        """
        Run the multi-tool orchestration and return answer, provenance, and verifiable tool_trace.
        Orchestration:
          Step 1: If use_pageindex, call pageindex_navigate(question) → section_titles.
          Step 2: semantic_search(question, section_titles=...) → hits, chain.
          Step 3: If fact_store and (no hits or suggests_structured_query(question)), call structured_query → rows, merge.
        """
        tool_trace: list[ToolCallRecord] = []
        chain = ProvenanceChain()
        answer_parts: list[str] = []
        section_titles: list[str] = []

        # --- Step 1: PageIndex navigation (topic-based section scoping)
        if use_pageindex:
            section_titles = pageindex_navigate(
                question, doc_id=doc_id, repo_root=self._repo_root, top_k=3
            )
            tool_trace.append(
                ToolCallRecord(
                    tool=self.TOOL_PAGEINDEX,
                    args={"topic": question[:200], "doc_id": doc_id, "top_k": 3},
                    result_summary=f"{len(section_titles)} sections" if section_titles else "0 sections",
                    n_provenance_items=0,
                )
            )

        # --- Step 2: Semantic search (vector store)
        section_filter = section_titles if section_titles else None
        hits, search_chain = semantic_search(
            question,
            self._vector,
            doc_id=doc_id,
            section_titles=section_filter,
            n_results=n_results,
        )
        chain.items.extend(search_chain.items)
        tool_trace.append(
            ToolCallRecord(
                tool=self.TOOL_SEMANTIC,
                args={
                    "query": question[:200],
                    "doc_id": doc_id,
                    "section_titles": section_filter,
                    "n_results": n_results,
                },
                result_summary=f"{len(hits)} hits",
                n_provenance_items=len(search_chain.items),
            )
        )

        # Build answer from vector hits
        for h in hits[:3]:
            content = (h.get("content") or "").strip()
            if content:
                answer_parts.append(content[:500])
        answer_text = "\n\n".join(answer_parts) if answer_parts else ""

        # --- Step 3: Structured query (fact table) when useful
        use_structured = (
            self._facts is not None
            and (
                not hits
                or _suggests_structured_query(question)
            )
        )
        if use_structured:
            rows, fact_chain = structured_query(question, self._facts, doc_id=doc_id)
            tool_trace.append(
                ToolCallRecord(
                    tool=self.TOOL_STRUCTURED,
                    args={"query": question[:200], "doc_id": doc_id},
                    result_summary=f"{len(rows)} rows",
                    n_provenance_items=len(fact_chain.items),
                )
            )
            chain.items.extend(fact_chain.items)
            if rows:
                answer_text += "\n\n[Structured data]\n" + "\n".join(
                    str(r) for r in rows[:5]
                )

        if not answer_text.strip():
            answer_text = "No relevant passages or structured data found."

        return QueryResult(
            answer=answer_text.strip(),
            provenance=chain,
            tool_trace=tool_trace,
        )
