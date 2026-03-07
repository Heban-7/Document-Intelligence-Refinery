"""
Logical Document Unit (LDU): RAG-ready chunk with provenance.
ChunkingEngine produces LDUs from ExtractedDocument; ChunkValidator enforces rules.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from src.models.extraction import BoundingBox, PageRef


class ChunkType(str, Enum):
    """Type of content in this LDU."""
    PARAGRAPH = "paragraph"
    TABLE = "table"
    FIGURE = "figure"
    LIST = "list"
    SECTION_HEADER = "section_header"
    OTHER = "other"


class LDU(BaseModel):
    """
    Logical Document Unit: one semantically coherent chunk for RAG.
    Carries provenance (page_refs, bbox, content_hash) for citation.
    """
    ldu_id: str = ""  # unique within document; set by ChunkingEngine
    content: str = Field(..., description="Text content of the chunk")
    chunk_type: ChunkType = ChunkType.PARAGRAPH
    page_refs: list[PageRef] = Field(default_factory=list)
    bounding_box: BoundingBox | None = None
    parent_section: str = ""  # section title or path for hierarchy
    token_count: int = 0  # approximate
    content_hash: str = ""  # stable hash for provenance verification
    # Optional metadata for rule compliance
    table_id: str = ""
    figure_id: str = ""
    caption: str = ""  # for figure chunks
    cross_refs: list[str] = Field(default_factory=list)  # e.g. ["Table 3"]
    model_config = {"extra": "allow"}
