"""
Shared extraction schema: normalized output from Strategy A/B/C.
All extractors produce ExtractedDocument for downstream chunking and indexing.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Bounding box in page coordinates (points)."""
    x0: float = 0
    top: float = 0
    x1: float = 0
    bottom: float = 0


class PageRef(BaseModel):
    """Reference to a page (1-based)."""
    page_no: int = Field(..., ge=1)
    bbox: BoundingBox | None = None


class TextBlock(BaseModel):
    """A contiguous text region with position."""
    text: str = ""
    page_ref: PageRef | None = None
    bbox: BoundingBox | None = None


class TableCell(BaseModel):
    """Single table cell (for structured tables)."""
    value: str = ""
    row_index: int = 0
    col_index: int = 0
    bbox: BoundingBox | None = None


class Table(BaseModel):
    """Structured table with headers and rows."""
    headers: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    cells: list[TableCell] = Field(default_factory=list)  # optional cell-level bbox
    page_ref: PageRef | None = None
    bbox: BoundingBox | None = None


class Figure(BaseModel):
    """Figure or image with optional caption."""
    caption: str = ""
    page_ref: PageRef | None = None
    bbox: BoundingBox | None = None
    raw_ref: str = ""  # e.g. "Figure 3" for cross-refs


class ExtractedPage(BaseModel):
    """One page's extracted content in reading order."""
    page_no: int = Field(..., ge=1)
    text_blocks: list[TextBlock] = Field(default_factory=list)
    tables: list[Table] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)
    raw_text: str = ""  # fallback flat text for the page


class ExtractedDocument(BaseModel):
    """Full document extraction: normalized output from any strategy."""
    doc_id: str = ""
    file_name: str = ""
    pages: list[ExtractedPage] = Field(default_factory=list)
    model_config = {"extra": "allow"}


class ExtractionResult(BaseModel):
    """Result of an extraction run: document + strategy metadata."""
    document: ExtractedDocument
    strategy_used: str = ""  # "fast_text" | "layout" | "vision"
    confidence_score: float = 0.0  # 0-1
    cost_estimate: float = 0.0
    processing_time_seconds: float = 0.0
    pages_processed: int = 0
    model_config = {"extra": "allow"}
