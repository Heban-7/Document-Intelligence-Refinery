"""
Query tools: pageindex_navigate, semantic_search, structured_query.
Used by the query agent to answer with ProvenanceChain.
PageIndex supports nested section hierarchy and topic-based navigation (see PageIndex.find_sections_by_topic).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src.data.vector_store import VectorStore, pageindex_top_sections
from src.data.fact_table import FactTableStore
from src.models.pageindex import PageIndex
from src.models.provenance import ProvenanceChain, ProvenanceItem


def load_page_index(doc_id: str, repo_root: Path | None = None) -> PageIndex | None:
    path = (repo_root or Path.cwd()) / ".refinery" / "pageindex" / f"{doc_id}.json"
    if not path.exists():
        return None
    return PageIndex.model_validate_json(path.read_text(encoding="utf-8"))


def pageindex_navigate(
    topic: str,
    doc_id: str | None = None,
    repo_root: Path | None = None,
    top_k: int = 3,
) -> list[str]:
    """
    Navigate PageIndex by topic; return section titles to narrow search.
    Uses the document's section tree and topic-based scoring (title, summary, entities).
    If doc_id given, load that doc's PageIndex; else scan .refinery/pageindex for first match.
    """
    root = repo_root or Path.cwd()
    index_dir = root / ".refinery" / "pageindex"
    if not index_dir.exists():
        return []
    if doc_id:
        pi = load_page_index(doc_id, root)
        if pi:
            return pageindex_top_sections(pi, topic, top_k=top_k)
        return []
    for p in sorted(index_dir.glob("*.json")):
        pi = PageIndex.model_validate_json(p.read_text(encoding="utf-8"))
        titles = pageindex_top_sections(pi, topic, top_k=top_k)
        if titles:
            return titles
    return []


def pageindex_navigate_with_paths(
    topic: str,
    doc_id: str | None = None,
    repo_root: Path | None = None,
    top_k: int = 5,
) -> list[tuple[str, str]]:
    """
    Topic-based navigation returning (section_title, path) for each top section.
    Path is the hierarchical path from root (e.g. "/Introduction/Background").
    Useful for provenance and "see Section X / Y" citations.
    """
    root = repo_root or Path.cwd()
    pi = load_page_index(doc_id, root) if doc_id else None
    if pi is None and not doc_id:
        index_dir = root / ".refinery" / "pageindex"
        if index_dir.exists():
            for p in sorted(index_dir.glob("*.json")):
                pi = PageIndex.model_validate_json(p.read_text(encoding="utf-8"))
                break
    if pi is None:
        return []
    hits = pi.find_sections_by_topic(topic, top_k=top_k)
    return [(node.title, path) for _score, node, path in hits]


def semantic_search(
    query: str,
    vector_store: VectorStore,
    doc_id: str | None = None,
    section_titles: list[str] | None = None,
    n_results: int = 5,
) -> tuple[list[dict], ProvenanceChain]:
    """
    Run vector search; return hit list and ProvenanceChain from metadata.
    """
    doc_ids = [doc_id] if doc_id else None
    hits = vector_store.search(query, n_results=n_results, doc_ids=doc_ids, section_titles=section_titles)
    chain = ProvenanceChain()
    for h in hits:
        meta = h.get("metadata") or {}
        chain.items.append(ProvenanceItem(
            doc_id=meta.get("doc_id", ""),
            document_name=meta.get("doc_id", ""),
            page_number=int(meta.get("page_no", 0)) or 1,
            content_hash=meta.get("content_hash", ""),
            content_snippet=(h.get("content") or "")[:200],
            ldu_id=meta.get("ldu_id", ""),
        ))
    return hits, chain


def structured_query(
    query: str,
    fact_store: FactTableStore,
    doc_id: str | None = None,
) -> tuple[list[dict], ProvenanceChain]:
    """
    Run a safe SELECT over the fact table. If query looks like SQL SELECT, use it; else LIMIT 15.
    Returns rows and ProvenanceChain from doc_id, page_no in facts.
    """
    chain = ProvenanceChain()
    try:
        q = query.strip().upper()
        if q.startswith("SELECT") and "FROM" in q:
            rows = fact_store.query_sql(query)
        else:
            if doc_id:
                rows = fact_store.query_sql("SELECT * FROM facts WHERE doc_id = ? LIMIT 15", (doc_id,))
            else:
                rows = fact_store.query_sql("SELECT * FROM facts LIMIT 15")
        for row in rows[:5]:
            if isinstance(row, dict) and row.get("doc_id") is not None:
                chain.items.append(ProvenanceItem(
                    doc_id=str(row.get("doc_id", "")),
                    document_name=str(row.get("doc_id", "")),
                    page_number=int(row.get("page_no", 0)) or 1,
                    content_snippet=str(row.get("content", ""))[:200],
                ))
        return rows, chain
    except Exception:
        return [], chain
