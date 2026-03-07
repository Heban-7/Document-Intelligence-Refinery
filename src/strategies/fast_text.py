"""
Strategy A: Fast text extraction via pdfplumber with confidence scoring.
Use when DocumentProfile indicates native_digital + single_column; escalate on low confidence.
"""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pdfplumber

from src.config import get_fast_text_config
from src.models.common import doc_id_from_path
from src.models.document_profile import DocumentProfile
from src.models.extraction import (
    BoundingBox,
    ExtractedDocument,
    ExtractedPage,
    ExtractionResult,
    PageRef,
    TextBlock,
    Table,
    TableCell,
)


def _page_metrics(page) -> dict[str, Any]:
    """Per-page metrics for confidence (aligned with triage)."""
    width = float(page.width or 0)
    height = float(page.height or 0)
    page_area = width * height
    if page_area <= 0:
        return {"char_count": 0, "char_density_per_1k_pt2": 0.0, "image_area_ratio": 0.0, "has_font_metadata": False}
    chars = page.chars or []
    text = (page.extract_text() or "") or ""
    char_count = len(text)
    density = (len(text.replace("\n", "").replace(" ", "")) / page_area) * 1000 if page_area else 0
    images = page.images or []
    image_area = sum(
        (im.get("x1", 0) - im.get("x0", 0)) * (im.get("bottom", 0) - im.get("top", 0)) for im in images
    )
    image_ratio = image_area / page_area if page_area else 0
    return {
        "char_count": char_count,
        "char_density_per_1k_pt2": density,
        "image_area_ratio": image_ratio,
        "has_font_metadata": any(c.get("fontname") for c in chars) if chars else False,
    }


def _confidence_for_page(metrics: dict, config: dict) -> float:
    """Multi-signal confidence 0-1: density, image ratio, font, char count."""
    density = metrics.get("char_density_per_1k_pt2", 0)
    image_ratio = metrics.get("image_area_ratio", 1.0)
    has_font = metrics.get("has_font_metadata", False)
    char_count = metrics.get("char_count", 0)
    min_density = config.get("min_char_density_per_1k_pt2", 0.5)
    max_image = config.get("max_image_ratio", 0.5)
    require_font = config.get("require_font_metadata", True)
    low_text_max = config.get("low_text_page_char_max", 100)
    score = 0.0
    if density >= min_density:
        score += 0.35
    elif density > 0:
        score += 0.15
    if image_ratio <= max_image:
        score += 0.35
    if has_font or not require_font:
        score += 0.2
    if char_count >= low_text_max:
        score += 0.1
    return min(1.0, score)


def _bbox_from_char_list(chars: list) -> BoundingBox | None:
    if not chars:
        return None
    x0 = min(c.get("x0", 0) for c in chars)
    x1 = max(c.get("x1", 0) for c in chars)
    top = min(c.get("top", 0) for c in chars)
    bottom = max(c.get("bottom", 0) for c in chars)
    return BoundingBox(x0=x0, top=top, x1=x1, bottom=bottom)


class FastTextExtractor:
    """Strategy A: pdfplumber-based extraction with per-page confidence."""

    name = "fast_text"

    def __init__(self, config_path: Path | None = None):
        self._config = get_fast_text_config()

    def extract(self, pdf_path: Path | str, profile: DocumentProfile) -> ExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        doc_id = doc_id_from_path(path)
        start = time.perf_counter()
        pages_out: list[ExtractedPage] = []
        page_confidences: list[float] = []

        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_no = i + 1
                metrics = _page_metrics(page)
                page_confidences.append(_confidence_for_page(metrics, self._config))

                text = (page.extract_text() or "") or ""
                chars = page.chars or []
                bbox = _bbox_from_char_list(chars) if chars else None
                text_blocks = [
                    TextBlock(
                        text=text,
                        page_ref=PageRef(page_no=page_no, bbox=bbox),
                        bbox=bbox,
                    )
                ] if text.strip() else []

                tables_out: list[Table] = []
                for t in page.find_tables() or []:
                    try:
                        rows = t.extract()
                        if rows:
                            headers = rows[0] if rows else []
                            data_rows = rows[1:] if len(rows) > 1 else []
                            tables_out.append(
                                Table(
                                    headers=[str(h) for h in headers],
                                    rows=[[str(c) for c in row] for row in data_rows],
                                    page_ref=PageRef(page_no=page_no),
                                )
                            )
                    except Exception:
                        pass

                pages_out.append(
                    ExtractedPage(
                        page_no=page_no,
                        text_blocks=text_blocks,
                        tables=tables_out,
                        raw_text=text,
                    )
                )

        elapsed = time.perf_counter() - start
        avg_confidence = sum(page_confidences) / len(page_confidences) if page_confidences else 0.0

        doc = ExtractedDocument(
            doc_id=doc_id,
            file_name=path.name,
            pages=pages_out,
        )
        return ExtractionResult(
            document=doc,
            strategy_used=self.name,
            confidence_score=avg_confidence,
            cost_estimate=0.0,
            processing_time_seconds=elapsed,
            pages_processed=len(pages_out),
        )
