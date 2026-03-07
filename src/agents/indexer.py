"""
PageIndex builder: derive section hierarchy from ExtractedDocument/LDUs,
attach summaries and key entities, serialize to .refinery/pageindex/{doc_id}.json.
Builds nested child_sections from heading levels (e.g. 1., 1.1., 1.1.1).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from src.models.chunking import LDU, ChunkType
from src.models.extraction import ExtractedDocument
from src.models.pageindex import PageIndex, SectionNode, _parse_heading_level


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


def _build_flat_sections(
    doc: ExtractedDocument,
    ldus: list[LDU],
    summary_fn: Callable[[list[LDU], str], str],
    entities_fn: Callable[[list[LDU], str], list[str]],
) -> list[SectionNode]:
    """Produce flat list of SectionNodes with level inferred from title; order by first page."""
    section_titles: list[str] = []
    for ldu in ldus:
        if ldu.chunk_type == ChunkType.SECTION_HEADER and ldu.content.strip():
            if ldu.content.strip() not in section_titles:
                section_titles.append(ldu.content.strip())

    flat: list[SectionNode] = []
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
        level = _parse_heading_level(title)
        summary = summary_fn(ldus, title)
        key_entities = entities_fn(ldus, title)
        flat.append(SectionNode(
            title=title,
            page_start=page_start,
            page_end=page_end,
            level=level,
            section_id="",
            path="",
            child_sections=[],
            key_entities=key_entities,
            summary=summary,
            data_types_present=data_types,
        ))

    # Sort by page_start then by original order (section_titles order)
    order = {t: i for i, t in enumerate(section_titles)}
    flat.sort(key=lambda n: (n.page_start, order.get(n.title, 999)))

    return flat


def _nest_sections(flat: list[SectionNode]) -> list[SectionNode]:
    """
    Build nested tree from flat list using level.
    Stack of (level, node); when we see a new section, pop until stack has parent level < current, then append to parent.
    Assign section_id and path as we go.
    """
    if not flat:
        return []
    root_list: list[SectionNode] = []
    stack: list[tuple[int, SectionNode]] = []  # (level, node)
    for i, node in enumerate(flat):
        level = node.level
        # Pop stack until we have a parent (strictly smaller level)
        while stack and stack[-1][0] >= level:
            stack.pop()
        if not stack:
            # Top-level section
            section_id = str(len(root_list))
            node.section_id = section_id
            node.path = f"/{node.title}"
            root_list.append(node)
            stack.append((level, node))
        else:
            parent_level, parent = stack[-1]
            parent.child_sections.append(node)
            child_index = len(parent.child_sections) - 1
            node.section_id = f"{parent.section_id}.{child_index}"
            node.path = f"{parent.path}/{node.title}"
            stack.append((level, node))
    return root_list


def build_page_index(
    doc: ExtractedDocument,
    ldus: list[LDU],
    summary_fn: Callable[[list[LDU], str], str] | None = None,
    entities_fn: Callable[[list[LDU], str], list[str]] | None = None,
) -> PageIndex:
    """
    Build PageIndex from document and its LDUs.
    Sections are derived from SECTION_HEADER LDUs; hierarchy from heading numbers (1., 1.1., etc.).
    """
    summary_fn = summary_fn or (lambda l, t: _section_summary_heuristic(l, t))
    entities_fn = entities_fn or _key_entities_heuristic

    flat = _build_flat_sections(doc, ldus, summary_fn, entities_fn)

    # If no sections, one root section for whole doc
    if not flat and doc.pages:
        all_ldus = ldus
        page_nos = set()
        for l in all_ldus:
            for pr in l.page_refs:
                page_nos.add(pr.page_no)
        flat = [SectionNode(
            title="Document",
            page_start=min(page_nos) if page_nos else 1,
            page_end=max(page_nos) if page_nos else 1,
            level=1,
            section_id="0",
            path="/Document",
            summary=_section_summary_heuristic(ldus, ""),
            key_entities=_key_entities_heuristic(ldus, ""),
        )]
    else:
        flat = _nest_sections(flat)

    return PageIndex(doc_id=doc.doc_id, file_name=doc.file_name, sections=flat)


def save_page_index(pi: PageIndex, repo_root: Path | None = None) -> Path:
    """Write PageIndex to .refinery/pageindex/{doc_id}.json."""
    root = Path(repo_root or Path.cwd())
    out_dir = root / ".refinery" / "pageindex"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{pi.doc_id}.json"
    path.write_text(pi.model_dump_json(indent=2), encoding="utf-8")
    return path
