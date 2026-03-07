"""
PageIndex: hierarchical navigation over a document (section tree).
Enables "navigate then retrieve" before vector search.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SectionNode(BaseModel):
    """One node in the PageIndex tree."""
    title: str = ""
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    child_sections: list["SectionNode"] = Field(default_factory=list)
    key_entities: list[str] = Field(default_factory=list)
    summary: str = ""  # 2-3 sentence LLM-generated or heuristic
    data_types_present: list[str] = Field(default_factory=list)  # e.g. ["tables", "figures"]
    model_config = {"extra": "allow"}


class PageIndex(BaseModel):
    """Root of the section tree for one document."""
    doc_id: str = ""
    file_name: str = ""
    sections: list[SectionNode] = Field(default_factory=list)
    model_config = {"extra": "allow"}


SectionNode.model_rebuild()
