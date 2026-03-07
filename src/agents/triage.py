"""
Triage Agent: classifies each document (origin type, layout, domain, language)
and produces a DocumentProfile that governs extraction strategy selection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pdfplumber

from src.config import get_triage_config
from src.models.common import doc_id_from_path
from src.models.document_profile import (
    DocumentProfile,
    DomainHint,
    EstimatedExtractionCost,
    LayoutComplexity,
    OriginType,
)


def _page_metrics(page) -> dict[str, Any]:
    """Per-page metrics for triage (aligned with Phase 0 script)."""
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
        "chars": chars,
        "page_width": width,
        "page_height": height,
    }


def _classify_origin_type(
    pages_metrics: list[dict],
    config: dict[str, Any],
) -> OriginType:
    """Classify origin from character density, image ratio, and font metadata."""
    scanned_ratio_min = config.get("scanned_image_ratio_min", 0.5)
    low_text_char_max = config.get("low_text_page_char_max", 100)
    low_text_majority = config.get("low_text_pages_majority", True)

    if not pages_metrics:
        return OriginType.SCANNED_IMAGE

    n = len(pages_metrics)
    avg_density = sum(p.get("char_density_per_1k_pt2", 0) for p in pages_metrics) / n
    avg_image_ratio = sum(p.get("image_area_ratio", 0) for p in pages_metrics) / n
    low_text_count = sum(1 for p in pages_metrics if (p.get("char_count") or 0) < low_text_char_max)
    pages_with_font = sum(1 for p in pages_metrics if p.get("has_font_metadata"))

    if avg_image_ratio >= scanned_ratio_min and (low_text_majority and low_text_count > n // 2):
        return OriginType.SCANNED_IMAGE
    if low_text_count > 0 and low_text_count < n and (pages_with_font < n):
        return OriginType.MIXED
    if pages_with_font == n and avg_density > 0 and avg_image_ratio < scanned_ratio_min:
        return OriginType.NATIVE_DIGITAL
    # Default: if mostly no text and image-dominated, scanned
    if avg_image_ratio >= scanned_ratio_min or low_text_count >= n // 2:
        return OriginType.SCANNED_IMAGE
    return OriginType.NATIVE_DIGITAL


def _classify_layout_complexity(pages_metrics: list[dict]) -> LayoutComplexity:
    """
    Heuristic layout: column count from char bbox X clustering; table/figure density.
    """
    if not pages_metrics:
        return LayoutComplexity.MIXED

    # Use first few pages with enough chars to infer layout
    sample_pages = [p for p in pages_metrics if (p.get("char_count") or 0) >= 50][:5]
    if not sample_pages:
        return LayoutComplexity.MIXED

    multi_column_indicators = 0
    table_indicators = 0
    figure_indicators = 0

    for p in sample_pages:
        chars = p.get("chars") or []
        if len(chars) < 20:
            continue
        xs = [c.get("x0", 0) + (c.get("x1", 0) - c.get("x0", 0)) / 2 for c in chars]
        width = p.get("page_width") or 1
        # Simple clustering: divide page into vertical bands; if text in 2+ bands -> multi-column
        band_width = width / 3
        bands_with_text = set(int(x / band_width) for x in xs if 0 <= x < width)
        if len(bands_with_text) >= 2:
            multi_column_indicators += 1
        # High image ratio on a page -> figure heavy
        if (p.get("image_area_ratio") or 0) > 0.3:
            figure_indicators += 1

    n_sample = len(sample_pages)
    if figure_indicators >= max(1, n_sample // 2):
        return LayoutComplexity.FIGURE_HEAVY
    if multi_column_indicators >= max(1, n_sample // 2):
        return LayoutComplexity.MULTI_COLUMN
    # Table-heavy: we don't have table detection here; require at least one indicator (Phase 2 can refine)
    if table_indicators >= max(1, n_sample // 2):
        return LayoutComplexity.TABLE_HEAVY
    if multi_column_indicators > 0 or figure_indicators > 0:
        return LayoutComplexity.MIXED
    return LayoutComplexity.SINGLE_COLUMN


class DomainHintClassifier:
    """Pluggable domain classifier; default is keyword-based over first pages."""

    KEYWORDS: dict[DomainHint, list[str]] = {
        DomainHint.FINANCIAL: [
            "annual report", "financial statement", "balance sheet", "income statement",
            "revenue", "expenditure", "tax", "audit", "fiscal", "profit", "loss",
        ],
        DomainHint.LEGAL: ["auditor", "legal", "contract", "agreement", "court", "compliance", "regulatory"],
        DomainHint.TECHNICAL: ["assessment", "survey", "implementation", "technical", "methodology", "findings"],
        DomainHint.MEDICAL: ["medical", "clinical", "patient", "health", "diagnosis", "treatment"],
    }

    def classify(self, text_sample: str) -> tuple[DomainHint, float]:
        """Return (domain_hint, confidence). Confidence is 0–1 based on keyword match strength."""
        if not (text_sample or text_sample.strip()):
            return DomainHint.GENERAL, 0.0
        lower = text_sample.lower()
        best: DomainHint = DomainHint.GENERAL
        best_count = 0
        for domain, keywords in self.KEYWORDS.items():
            count = sum(1 for k in keywords if k in lower)
            if count > best_count:
                best_count = count
                best = domain
        confidence = min(1.0, 0.3 + 0.2 * best_count) if best_count else 0.2
        return best, confidence


def _detect_language(text_sample: str) -> tuple[str, float]:
    """Detect language and confidence using langdetect."""
    if not (text_sample or text_sample.strip()):
        return "en", 0.0
    try:
        import langdetect
        result = langdetect.detect(text_sample)
        # langdetect doesn't return confidence; we run detect_langs and take top
        langs = langdetect.detect_langs(text_sample)
        conf = float(langs[0].prob) if langs else 0.5
        return result or "en", conf
    except Exception:
        return "en", 0.0


def _estimate_extraction_cost(
    origin_type: OriginType,
    layout_complexity: LayoutComplexity,
) -> EstimatedExtractionCost:
    """Map triage classification to extraction strategy tier."""
    if origin_type == OriginType.SCANNED_IMAGE:
        return EstimatedExtractionCost.NEEDS_VISION_MODEL
    if origin_type == OriginType.MIXED:
        return EstimatedExtractionCost.NEEDS_LAYOUT_MODEL
    if layout_complexity == LayoutComplexity.SINGLE_COLUMN and origin_type == OriginType.NATIVE_DIGITAL:
        return EstimatedExtractionCost.FAST_TEXT_SUFFICIENT
    if layout_complexity in (
        LayoutComplexity.MULTI_COLUMN,
        LayoutComplexity.TABLE_HEAVY,
        LayoutComplexity.FIGURE_HEAVY,
        LayoutComplexity.MIXED,
    ):
        return EstimatedExtractionCost.NEEDS_LAYOUT_MODEL
    return EstimatedExtractionCost.NEEDS_LAYOUT_MODEL


class TriageAgent:
    """Produces a DocumentProfile for a given PDF path."""

    def __init__(
        self,
        config_path: Path | None = None,
        domain_classifier: DomainHintClassifier | None = None,
    ):
        self._config = get_triage_config()
        self._domain_classifier = domain_classifier or DomainHintClassifier()

    def run(self, pdf_path: str | Path) -> DocumentProfile:
        """Analyze the PDF and return a DocumentProfile."""
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")

        doc_id = doc_id_from_path(path)
        pages_metrics: list[dict] = []
        text_samples: list[str] = []

        with pdfplumber.open(path) as pdf:
            num_pages = len(pdf.pages)
            for i, page in enumerate(pdf.pages):
                m = _page_metrics(page)
                pages_metrics.append(m)
                # Sample text from first few pages for domain and language
                if i < 3:
                    text_samples.append((page.extract_text() or "")[: 3000])

        full_text_sample = "\n".join(text_samples)

        origin_type = _classify_origin_type(pages_metrics, self._config)
        layout_complexity = _classify_layout_complexity(pages_metrics)
        domain_hint, _ = self._domain_classifier.classify(full_text_sample)
        language, language_confidence = _detect_language(full_text_sample)
        estimated_extraction_cost = _estimate_extraction_cost(origin_type, layout_complexity)

        return DocumentProfile(
            doc_id=doc_id,
            file_name=path.name,
            num_pages=num_pages,
            origin_type=origin_type,
            layout_complexity=layout_complexity,
            domain_hint=domain_hint,
            estimated_extraction_cost=estimated_extraction_cost,
            language=language,
            language_confidence=language_confidence,
        )
