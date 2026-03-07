"""
Provenance: source citations for every answer (document, page, bbox, content_hash).
"""
from __future__ import annotations

from pydantic import BaseModel, Field


class ProvenanceItem(BaseModel):
    """One source citation."""
    document_name: str = ""
    doc_id: str = ""
    page_number: int = Field(..., ge=1)
    bbox: str = ""  # e.g. "x0,top,x1,bottom" or serialized
    content_hash: str = ""
    content_snippet: str = ""  # optional preview
    ldu_id: str = ""


class ProvenanceChain(BaseModel):
    """List of source citations attached to an answer."""
    items: list[ProvenanceItem] = Field(default_factory=list)
    verified: bool = False  # True if audit confirmed
