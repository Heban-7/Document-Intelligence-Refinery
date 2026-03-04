"""
DocumentProfile: classification output of the Triage Agent.
Governs extraction strategy selection and downstream pipeline behavior.
"""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class OriginType(str, Enum):
    NATIVE_DIGITAL = "native_digital"
    SCANNED_IMAGE = "scanned_image"
    MIXED = "mixed"
    FORM_FILLABLE = "form_fillable"


class LayoutComplexity(str, Enum):
    SINGLE_COLUMN = "single_column"
    MULTI_COLUMN = "multi_column"
    TABLE_HEAVY = "table_heavy"
    FIGURE_HEAVY = "figure_heavy"
    MIXED = "mixed"


class DomainHint(str, Enum):
    FINANCIAL = "financial"
    LEGAL = "legal"
    TECHNICAL = "technical"
    MEDICAL = "medical"
    GENERAL = "general"


class EstimatedExtractionCost(str, Enum):
    FAST_TEXT_SUFFICIENT = "fast_text_sufficient"
    NEEDS_LAYOUT_MODEL = "needs_layout_model"
    NEEDS_VISION_MODEL = "needs_vision_model"


class DocumentProfile(BaseModel):
    """Classification result produced by the Triage Agent for one document."""

    doc_id: str = Field(..., description="Stable document identifier (from path stem)")
    file_name: str = Field(..., description="Original file name")
    num_pages: int = Field(..., ge=0, description="Number of pages")

    origin_type: OriginType = Field(..., description="Digital vs scanned vs mixed")
    layout_complexity: LayoutComplexity = Field(..., description="Column/layout structure")
    domain_hint: DomainHint = Field(default=DomainHint.GENERAL, description="Domain for extraction prompts")
    estimated_extraction_cost: EstimatedExtractionCost = Field(
        ..., description="Which extraction strategy tier to use"
    )

    language: str = Field(default="en", description="Detected language code (e.g. en, am)")
    language_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="Language detection confidence")

    model_config = {"frozen": False, "extra": "forbid"}

    def model_dump_json(self, **kwargs: Any) -> str:
        return super().model_dump_json(**kwargs)
