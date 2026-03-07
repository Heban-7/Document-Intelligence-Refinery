"""
PageIndex builder: derive section hierarchy from ExtractedDocument/LDUs,
attach summaries and key entities, serialize to .refinery/pageindex/{doc_id}.json.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.models.chunking import LDU, ChunkType
from src.models.extraction import ExtractedDocument
from src.models.pageindex import PageIndex, SectionNode


def _section_summary_heuristic(ldus: list[LDU], section_title: str, max_chars: int = 300) -> str:
    """Default summary: first N chars of section content (no LLM)."""
    parts = [section_title]
    for ldu in ldus:
        if ldu.parent_section == section_title and ldu.chunk_type == ChunkType.PARAGRAPH:
            parts.append(ldu.content[:500])
            if sum(len(p) for p in parts) >= max_chars:
                break
    text = " ".join(parts)
    return (text[:max_chars] + "…") if len(text) > max_chars else text


def _key_entities_heuristic(ldus: list[LDU], section_title: str) -> list[str]:
    """Simple keyword extraction: capitalized phrases (stub)."""
    entities = []
    for ldu in ldus:
        if ldu.parent_section != section_title:
            continue
        words = ldu.content.split()
        for i, w in enumerate(words):
            if w and w[0].isupper() and len(w) > 2 and w not in ("The", "This", "Section"):
                entities.append(w)
                if len(entities) >= 10:
                    return list(dict.fromkeys(entities))[:10]
    return list(dict.fromkeys(entities))[:10]


def build_page_index(
    doc: ExtractedDocument,
    ldus: list[LDU],
    summary_fn: Callable[[list[LDU], str], str] | None = None,
    entities_fn: Callable[[list[LDU], str], list[str]] | None = None,
) -> PageIndex:
    """
    Build PageIndex from document and its LDUs.
    Sections are derived from SECTION_HEADER LDUs; page range from page_refs of LDUs in that section.
    """
    summary_fn = summary_fn or (lambda l, t: _section_summary_heuristic(l, t))
    entities_fn = entities_fn or _key_entities_heuristic

    section_titles: list[str] = []
    for ldu in ldus:
        if ldu.chunk_type == ChunkType.SECTION_HEADER and ldu.content.strip():
            if ldu.content.strip() not in section_titles:
                section_titles.append(ldu.content.strip())

    nodes: list[SectionNode] = []
    for title in section_titles:
        section_ldus = [l for l in ldus if l.parent_section == title or (l.chunk_type == ChunkType.SECTION_HEADER and l.content.strip() == title)]
        if not section_ldus:
            continue
        page_nos = set()
        for l in section_ldus:
            for pr in l.page_refs:
                page_nos.add(pr.page_no)
        data_types = []
        for l in section_ldus:
            if l.chunk_type == ChunkType.TABLE and "tables" not in data_types:
                data_types.append("tables")
            if l.chunk_type == ChunkType.FIGURE and "figures" not in data_types:
                data_types.append("figures")
        page_start = min(page_nos) if page_nos else 1
        page_end = max(page_nos) if page_nos else 1
        summary = summary_fn(ldus, title)
        key_entities = entities_fn(ldus, title)
        nodes.append(SectionNode(
            title=title,
            page_start=page_start,
            page_end=page_end,
            child_sections=[],
            key_entities=key_entities,
            summary=summary,
            data_types_present=data_types,
        ))

    # If no sections, one root section for whole doc
    if not nodes and doc.pages:
        all_ldus = ldus
        page_nos = set()
        for l in all_ldus:
            for pr in l.page_refs:
                page_nos.add(pr.page_no)
        nodes = [SectionNode(
            title="Document",
            page_start=min(page_nos) if page_nos else 1,
            page_end=max(page_nos) if page_nos else 1,
            summary=_section_summary_heuristic(ldus, ""),
            key_entities=_key_entities_heuristic(ldus, ""),
        )]

    return PageIndex(doc_id=doc.doc_id, file_name=doc.file_name, sections=nodes)


def save_page_index(pi: PageIndex, repo_root: Path | None = None) -> Path:
    """Write PageIndex to .refinery/pageindex/{doc_id}.json."""
    root = Path(repo_root or Path.cwd())
    out_dir = root / ".refinery" / "pageindex"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pi.doc_id}.json"
    path.write_text(pi.model_dump_json(indent=2), encoding="utf-8")
    return path
