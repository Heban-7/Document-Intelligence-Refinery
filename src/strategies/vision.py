"""
Strategy C: Vision-augmented extraction via OpenRouter (VLM).
Use for scanned documents or when Strategy A/B confidence is below threshold.
Budget guard: cap cost per document via config (extraction_rules.yaml or REFINERY_VISION_BUDGET_USD).
"""
from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import fitz  # pymupdf

from src.config import (
    get_openrouter_api_key,
    get_openrouter_vlm_model,
    get_vision_budget_max_usd,
)
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
)


def _page_to_base64_image(path: Path, page_index: int, dpi: int = 150) -> str:
    """Render one PDF page to PNG and return base64 data URL."""
    doc = fitz.open(path)
    page = doc[page_index]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    png_bytes = pix.tobytes("png")
    doc.close()
    b64 = base64.standard_b64encode(png_bytes).decode("ascii")
    return f"data:image/png;base64,{b64}"


def _call_openrouter_vision(image_data_url: str, page_no: int, api_key: str, model: str) -> str:
    """Send one page image to OpenRouter VLM and return extracted text/JSON."""
    import urllib.request
    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Extract all text from this document page in reading order. Return only the raw text, no JSON. Preserve paragraphs as separate blocks.",
                    },
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
        "max_tokens": 4096,
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/document-intelligence-refinery",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.loads(resp.read().decode())
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message", {})
    return (message.get("content") or "").strip()


class VisionExtractor:
    """Strategy C: VLM-based extraction with budget guard."""

    name = "vision"

    def __init__(self, config_path: Path | None = None, api_key: str | None = None):
        self._api_key = api_key or get_openrouter_api_key()
        if not self._api_key:
            raise ValueError("OPENROUTER_API_KEY must be set for VisionExtractor")

    def extract(self, pdf_path: Path | str, profile: DocumentProfile) -> ExtractionResult:
        path = Path(pdf_path)
        if not path.exists():
            raise FileNotFoundError(f"PDF not found: {path}")
        doc_id = doc_id_from_path(path)
        start = time.perf_counter()
        budget_max = get_vision_budget_max_usd()
        model = get_openrouter_vlm_model()

        doc = fitz.open(path)
        num_pages = len(doc)
        doc.close()

        pages_out: list[ExtractedPage] = []
        # Simple cost proxy: ~$0.001 per page for flash models (adjust if needed)
        estimated_cost = 0.0
        cost_per_page = 0.001
        if estimated_cost + num_pages * cost_per_page > budget_max:
            raise RuntimeError(
                f"Estimated cost {estimated_cost + num_pages * cost_per_page:.2f} USD exceeds budget {budget_max} USD"
            )

        for i in range(num_pages):
            try:
                img_url = _page_to_base64_image(path, i)
                text = _call_openrouter_vision(img_url, i + 1, self._api_key, model)
                pages_out.append(
                    ExtractedPage(
                        page_no=i + 1,
                        text_blocks=[TextBlock(text=text, page_ref=PageRef(page_no=i + 1))],
                        raw_text=text,
                    )
                )
                estimated_cost += cost_per_page
            except Exception as e:
                pages_out.append(
                    ExtractedPage(page_no=i + 1, raw_text=f"[Extraction error: {e}]")
                )

        elapsed = time.perf_counter() - start
        doc_out = ExtractedDocument(doc_id=doc_id, file_name=path.name, pages=pages_out)
        return ExtractionResult(
            document=doc_out,
            strategy_used=self.name,
            confidence_score=0.9,
            cost_estimate=estimated_cost,
            processing_time_seconds=elapsed,
            pages_processed=len(pages_out),
        )
