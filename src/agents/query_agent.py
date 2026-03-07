"""
Query agent: answer natural language questions over indexed documents
using pageindex_navigate, semantic_search, structured_query; every answer includes ProvenanceChain.
"""
from __future__ import annotations

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


class QueryAgent:
    """
    Answer questions over the refinery corpus (vector store + optional fact store).
    Returns answer text and ProvenanceChain.
    """

    def __init__(
        self,
        vector_store: VectorStore | None = None,
        fact_store: FactTableStore | None = None,
        repo_root: Path | None = None,
    ):
        self._vector = vector_store or VectorStore(persist_path=(repo_root or Path.cwd()) / ".refinery" / "vector_db")
        self._facts = fact_store
        self._repo_root = repo_root or Path.cwd()

    def query(
        self,
        question: str,
        doc_id: str | None = None,
        use_pageindex: bool = True,
        n_results: int = 5,
    ) -> tuple[str, ProvenanceChain]:
        """
        Answer the question using semantic search (and optional PageIndex + structured query).
        Returns (answer_text, provenance_chain).
        """
        section_titles = []
        if use_pageindex:
            section_titles = pageindex_navigate(question, doc_id=doc_id, repo_root=self._repo_root, top_k=3)

        hits, chain = semantic_search(
            question,
            self._vector,
            doc_id=doc_id,
            section_titles=section_titles if section_titles else None,
            n_results=n_results,
        )

        # Build answer from top hits
        parts = []
        for h in hits[:3]:
            content = (h.get("content") or "").strip()
            if content:
                parts.append(content[:500])
        answer = "\n\n".join(parts) if parts else "No relevant passages found."
        if not chain.items and self._facts:
            rows, fact_chain = structured_query(question, self._facts, doc_id)
            if rows:
                answer += "\n\n[Structured data]\n" + "\n".join(str(r) for r in rows[:5])
                chain.items.extend(fact_chain.items)
        return answer, chain
