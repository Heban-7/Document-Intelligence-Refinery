"""
ChunkingEngine: convert ExtractedDocument into LDUs with five chunking rules.
ChunkValidator verifies rules before emitting.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from src.models.extraction import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    Figure,
    PageRef,
    Table,
    TextBlock,
)
from src.models.chunking import ChunkType, LDU


def _load_chunking_config(config_path: Path | None = None) -> dict[str, Any]:
    if config_path is None:
        config_path = Path.cwd() / "rubric" / "extraction_rules.yaml"
    if not config_path.exists():
        return {}
    import yaml
    with open(config_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("chunking", {})


def _token_count_approx(text: str) -> int:
    """Rough token count (words * 1.3)."""
    if not text or not text.strip():
        return 0
    return max(1, int(len(text.split()) * 1.3))


def _content_hash(content: str, page_refs: list[PageRef], bbox: BoundingBox | None) -> str:
    """Stable hash for provenance (normalized text + page refs + bbox)."""
    parts = [content.strip().lower(), str([(p.page_no, p.bbox) for p in page_refs])]
    if bbox:
        parts.append(f"{bbox.x0},{bbox.top},{bbox.x1},{bbox.bottom}")
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _extract_cross_refs(text: str) -> list[str]:
    """Find references like 'Table 3', 'Figure 2', 'see Section 4'."""
    refs = []
    for m in re.finditer(r"(?:Table|Figure|Section|Appendix)\s*\d+", text, re.I):
        refs.append(m.group(0))
    for m in re.finditer(r"see\s+(\w+\s*\d+)", text, re.I):
        refs.append(m.group(1).strip())
    return list(dict.fromkeys(refs))


def _is_numbered_list(text: str) -> bool:
    """Heuristic: line starts with digit(s). or roman."""
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return False
    pattern = re.compile(r"^(\d+[.)]\s|\d+\.\s|[ivxlcdm]+[.)]\s)", re.I)
    return sum(1 for l in lines if pattern.match(l)) >= len(lines) // 2


class ChunkValidator:
    """Verify chunking rules before emitting LDUs."""

    @staticmethod
    def validate(ldus: list[LDU], max_tokens_per_ldu: int) -> list[str]:
        """Return list of violation messages; empty if valid."""
        violations = []
        for i, ldu in enumerate(ldus):
            if ldu.chunk_type == ChunkType.TABLE and not ldu.content.strip():
                violations.append(f"LDU {i}: table chunk has empty content")
            if ldu.token_count > max_tokens_per_ldu:
                violations.append(
                    f"LDU {i} ({ldu.chunk_type}): token_count {ldu.token_count} > max {max_tokens_per_ldu}"
                )
            if ldu.chunk_type == ChunkType.FIGURE and ldu.caption and ldu.caption not in ldu.content:
                # Caption should be in content or stored; we store in caption field
                pass  # we store caption in metadata, content can be caption text
            if not ldu.content_hash:
                violations.append(f"LDU {i}: missing content_hash")
        return violations


class ChunkingEngine:
    """
    Convert ExtractedDocument to LDUs.
    Rules: (1) table = one LDU with header+rows (2) figure+caption = one LDU (3) numbered list = one LDU
    (4) parent_section on each (5) cross_refs extracted and stored.
    """

    def __init__(self, config_path: Path | None = None):
        self._config = _load_chunking_config(config_path)
        self._max_tokens = self._config.get("max_tokens_per_ldu", 512)

    def run(self, doc: ExtractedDocument) -> list[LDU]:
        """Produce LDUs from ExtractedDocument; validate and return."""
        ldus: list[LDU] = []
        current_section = ""
        ldu_counter = 0

        for page in doc.pages:
            page_ref = PageRef(page_no=page.page_no)
            page_refs = [page_ref]

            # Tables: one LDU per table (header + rows together)
            for ti, table in enumerate(page.tables):
                rows_text = "\n".join(
                    [" | ".join(table.headers)]
                    + [" | ".join(row) for row in table.rows]
                )
                content = rows_text or " "
                tc = _token_count_approx(content)
                bbox = table.bbox if table.bbox else (table.page_ref.bbox if (table.page_ref and hasattr(table.page_ref, "bbox")) else None)
                ldu_counter += 1
                ldu = LDU(
                    ldu_id=f"{doc.doc_id}_t{ldu_counter}",
                    content=content,
                    chunk_type=ChunkType.TABLE,
                    page_refs=page_refs,
                    bounding_box=bbox,
                    parent_section=current_section,
                    token_count=tc,
                    content_hash=_content_hash(content, page_refs, bbox),
                    table_id=f"table_{page.page_no}_{ti}",
                    cross_refs=_extract_cross_refs(content),
                )
                ldus.append(ldu)

            # Figures: one LDU per figure, caption in metadata
            for fi, fig in enumerate(page.figures):
                content = fig.caption or "(figure)"
                tc = _token_count_approx(content)
                bbox = fig.bbox
                ldu_counter += 1
                ldu = LDU(
                    ldu_id=f"{doc.doc_id}_f{ldu_counter}",
                    content=content,
                    chunk_type=ChunkType.FIGURE,
                    page_refs=page_refs,
                    bounding_box=bbox,
                    parent_section=current_section,
                    token_count=tc,
                    content_hash=_content_hash(content, page_refs, bbox),
                    figure_id=f"figure_{page.page_no}_{fi}",
                    caption=fig.caption,
                )
                ldus.append(ldu)

            # Text blocks: split by paragraph or keep as block; detect section headers and lists
            for block in page.text_blocks:
                text = (block.text or "").strip()
                if not text:
                    continue
                # Section header heuristic: short line, often title case or all caps
                if len(text) < 200 and (text.isupper() or (len(text.split()) <= 10 and text[0].isupper())):
                    current_section = text
                    ldu_counter += 1
                    ldus.append(LDU(
                        ldu_id=f"{doc.doc_id}_h{ldu_counter}",
                        content=text,
                        chunk_type=ChunkType.SECTION_HEADER,
                        page_refs=page_refs,
                        bounding_box=block.bbox,
                        parent_section=current_section,
                        token_count=_token_count_approx(text),
                        content_hash=_content_hash(text, page_refs, block.bbox),
                    ))
                    continue
                if _is_numbered_list(text) and _token_count_approx(text) <= self._max_tokens:
                    ldu_counter += 1
                    ldus.append(LDU(
                        ldu_id=f"{doc.doc_id}_l{ldu_counter}",
                        content=text,
                        chunk_type=ChunkType.LIST,
                        page_refs=page_refs,
                        bounding_box=block.bbox,
                        parent_section=current_section,
                        token_count=_token_count_approx(text),
                        content_hash=_content_hash(text, page_refs, block.bbox),
                        cross_refs=_extract_cross_refs(text),
                    ))
                    continue
                # Paragraph(s): split by double newline if over max_tokens
                paras = [p.strip() for p in text.split("\n\n") if p.strip()]
                for p in paras:
                    tc = _token_count_approx(p)
                    if tc > self._max_tokens:
                        # Split by sentence or line
                        parts = re.split(r"(?<=[.!?])\s+", p)
                        acc, cur = [], []
                        for part in parts:
                            cur.append(part)
                            if _token_count_approx(" ".join(cur)) >= self._max_tokens:
                                acc.append(" ".join(cur))
                                cur = []
                        if cur:
                            acc.append(" ".join(cur))
                        for part in acc:
                            ldu_counter += 1
                            ldus.append(LDU(
                                ldu_id=f"{doc.doc_id}_p{ldu_counter}",
                                content=part,
                                chunk_type=ChunkType.PARAGRAPH,
                                page_refs=page_refs,
                                bounding_box=block.bbox,
                                parent_section=current_section,
                                token_count=_token_count_approx(part),
                                content_hash=_content_hash(part, page_refs, block.bbox),
                                cross_refs=_extract_cross_refs(part),
                            ))
                    else:
                        ldu_counter += 1
                        ldus.append(LDU(
                            ldu_id=f"{doc.doc_id}_p{ldu_counter}",
                            content=p,
                            chunk_type=ChunkType.PARAGRAPH,
                            page_refs=page_refs,
                            bounding_box=block.bbox,
                            parent_section=current_section,
                            token_count=tc,
                            content_hash=_content_hash(p, page_refs, block.bbox),
                            cross_refs=_extract_cross_refs(p),
                        ))

            # Fallback: raw_text if no text_blocks
            if not page.text_blocks and page.raw_text.strip():
                text = page.raw_text.strip()
                tc = _token_count_approx(text)
                if tc > self._max_tokens:
                    for chunk in [text[i : i + self._max_tokens * 4] for i in range(0, len(text), self._max_tokens * 4)]:
                        if chunk.strip():
                            ldu_counter += 1
                            ldus.append(LDU(
                                ldu_id=f"{doc.doc_id}_r{ldu_counter}",
                                content=chunk.strip(),
                                chunk_type=ChunkType.PARAGRAPH,
                                page_refs=page_refs,
                                parent_section=current_section,
                                token_count=_token_count_approx(chunk),
                                content_hash=_content_hash(chunk, page_refs, None),
                            ))
                else:
                    ldu_counter += 1
                    ldus.append(LDU(
                        ldu_id=f"{doc.doc_id}_r{ldu_counter}",
                        content=text,
                        chunk_type=ChunkType.PARAGRAPH,
                        page_refs=page_refs,
                        parent_section=current_section,
                        token_count=tc,
                        content_hash=_content_hash(text, page_refs, None),
                    ))

        violations = ChunkValidator.validate(ldus, self._max_tokens)
        if violations:
            for v in violations:
                import warnings
                warnings.warn(f"ChunkValidator: {v}")
        return ldus
