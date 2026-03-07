"""
Base interface for extraction strategies. All strategies produce ExtractionResult.
"""
from __future__ import annotations

from pathlib import Path
from typing import Protocol

from src.models.document_profile import DocumentProfile
from src.models.extraction import ExtractionResult


class ExtractionStrategy(Protocol):
    """Protocol for Strategy A/B/C: take profile + path, return ExtractionResult."""

    def extract(self, pdf_path: Path | str, profile: DocumentProfile) -> ExtractionResult:
        ...
    
    @property
    def name(self) -> str:
        ...
