"""
Strategy B: Layout-aware extraction via Docling. Converts DoclingDocument to ExtractedDocument.
Use for multi-column, table-heavy, or when Strategy A confidence is low.
"""
from __future__ import annotations

import time
from pathlib import Path

from src.models.common import doc_id_from_path
from src.models.document_profile import DocumentProfile
from src.models.extraction import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractionResult,
    Figure,
    PageRef,
    Table,
    TextBlock,
)


def _docling_doc_to_extracted(doc, doc_id: str, file_name: str) -> ExtractedDocument:
    """
    Adapt Docling document to our ExtractedDocument schema.
    Docling 2.x: .export_to_markdown(), .export_to_dict(), .tables, .pictures (if available).
    """
    pages: list[ExtractedPage] = []
    try:
        md = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else ""
    except Exception:
        md = ""
    # Build a single logical "page" from full markdown if we can't get per-page from Docling
    # Docling document may not expose per-page easily; we use export_to_dict() if available
    try:
        d = doc.export_to_dict() if hasattr(doc, "export_to_dict") else None
    except Exception:
        d = None

    if d and isinstance(d, dict):
        # Try to walk structure for pages/sections
        body = d.get("body", d)
        if isinstance(body, list):
            page_no = 1
            for item in body:
                if isinstance(item, dict):
                    text = item.get("text", "")
                    if text:
                        pages.append(
                            ExtractedPage(
                                page_no=page_no,
                                text_blocks=[TextBlock(text=text, page_ref=PageRef(page_no=page_no))],
                                raw_text=text,
                            )
                        )
                        page_no += 1
        if not pages and md:
            pages.append(
                ExtractedPage(page_no=1, text_blocks=[TextBlock(text=md, page_ref=PageRef(page_no=1))], raw_text=md)
            )
    else:
        if md:
            pages.append(
                ExtractedPage(page_no=1, text_blocks=[TextBlock(text=md, page_ref=PageRef(page_no=1))], raw_text=md)
            )

    if hasattr(doc, "tables") and doc.tables:
        for i, tbl in enumerate(doc.tables):
            try:
                if hasattr(tbl, "data") and tbl.data:
                    rows = tbl.data
                    headers = list(rows[0]) if rows else []
                    data_rows = [list(r) for r in rows[1:]] if len(rows) > 1 else []
                    t = Table(headers=[str(h) for h in headers], rows=[[str(c) for c in row] for row in data_rows])
                    if not pages:
                        pages.append(ExtractedPage(page_no=1, tables=[t]))
                    else:
                        pages[0].tables.append(t)
            except Exception:
                pass

    if hasattr(doc, "pictures") and doc.pictures:
        for pic in doc.pictures:
            try:
                cap = getattr(pic, "caption", "") or ""
                fig = Figure(caption=cap)
                if pages:
                    pages[0].figures.append(fig)
            except Exception:
                pass

    if not pages:
        pages = [ExtractedPage(page_no=1, raw_text=md or "")]

    return ExtractedDocument(doc_id=doc_id, file_name=file_name, pages=pages)


class LayoutExtractor:
    """Strategy B: Docling layout-aware extraction."""

    name = "layout"

    def extract(self, pdf_path: Path | str, profile: DocumentProfile) -> ExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        doc_id = doc_id_from_path(path)
        start = time.perf_counter()
        try:
            from docling.document_converter import DocumentConverter
        except ImportError:
            raise RuntimeError("Docling not installed. Run: uv sync")

        converter = DocumentConverter()
        conv_result = converter.convert(str(path))
        doc = conv_result.document
        extracted = _docling_doc_to_extracted(doc, doc_id, path.name)
        elapsed = time.perf_counter() - start
        # Layout strategy gets fixed medium confidence when it succeeds (no per-page signal here)
        return ExtractionResult(
            document=extracted,
            strategy_used=self.name,
            confidence_score=0.75,
            cost_estimate=0.0,
            processing_time_seconds=elapsed,
            pages_processed=len(extracted.pages),
        )
