"""
Audit mode: verify a claim against the corpus; return ProvenanceChain or "not found / unverifiable".
"""
from __future__ import annotations

from pathlib import Path

from src.agents.query_tools import semantic_search, structured_query
from src.data.vector_store import VectorStore
from src.data.fact_table import FactTableStore
from src.models.provenance import ProvenanceChain


def audit_claim(
    claim: str,
    vector_store: VectorStore,
    fact_store: FactTableStore | None = None,
    doc_id: str | None = None,
    n_results: int = 5,
) -> tuple[str, ProvenanceChain]:
    """
    Try to find evidence for the claim in vector store (and fact store).
    Returns (status, provenance_chain) where status is "verified" or "not_found".
    """
    hits, chain = semantic_search(claim, vector_store, doc_id=doc_id, n_results=n_results)
    if chain.items:
        chain.verified = True
        return "verified", chain
    if fact_store:
        rows, fact_chain = structured_query(claim, fact_store, doc_id)
        if fact_chain.items:
            fact_chain.verified = True
            return "verified", fact_chain
    return "not_found", ProvenanceChain()
