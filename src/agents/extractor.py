"""
ExtractionRouter: selects Strategy A/B/C from DocumentProfile, runs extractor,
applies confidence-gated escalation, and logs to extraction_ledger.jsonl.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.config import get_extraction_config, get_openrouter_api_key
from src.models.document_profile import DocumentProfile, EstimatedExtractionCost
from src.models.extraction import ExtractionResult
from src.strategies.fast_text import FastTextExtractor
from src.strategies.layout import LayoutExtractor
from src.strategies.vision import VisionExtractor


def _append_ledger_entry(ledger_path: Path, entry: dict) -> None:
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with open(ledger_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


class ExtractionRouter:
    """
    Strategy-pattern router: pick extractor from profile, run, escalate on low confidence.
    """

    def __init__(
        self,
        config_path: Path | None = None,
        ledger_path: Path | None = None,
        vision_api_key: str | None = None,
    ):
        self._config = get_extraction_config()
        self._threshold = self._config.get("confidence_escalation_threshold", 0.5)
        self._ledger_path = ledger_path or (Path.cwd() / ".refinery" / "extraction_ledger.jsonl")
        self._fast = FastTextExtractor()
        self._layout = LayoutExtractor()
        api_key = vision_api_key or get_openrouter_api_key()
        self._vision_api_key = api_key
        try:
            self._vision = VisionExtractor(api_key=api_key)
        except ValueError:
            self._vision = None

    def _strategy_for_profile(self, profile: DocumentProfile) -> str:
        """Return initial strategy name from profile.estimated_extraction_cost."""
        cost = profile.estimated_extraction_cost
        if cost == EstimatedExtractionCost.FAST_TEXT_SUFFICIENT:
            return "fast_text"
        if cost == EstimatedExtractionCost.NEEDS_LAYOUT_MODEL:
            return "layout"
        if cost == EstimatedExtractionCost.NEEDS_VISION_MODEL and self._vision is not None:
            return "vision"
        return "layout"  # fallback when vision requested but not available

    def _get_extractor(self, strategy: str):
        if strategy == "fast_text":
            return self._fast
        if strategy == "layout":
            return self._layout
        if strategy == "vision" and self._vision is not None:
            return self._vision
        raise ValueError(f"Unknown or unavailable strategy: {strategy}")

    def _next_strategy(self, strategy: str) -> str | None:
        if strategy == "fast_text":
            return "layout"
        if strategy == "layout":
            return "vision" if self._vision else None
        return None

    def run(
        self,
        pdf_path: Path | str,
        profile: DocumentProfile,
        *,
        allow_escalation: bool = True,
    ) -> ExtractionResult:
        """
        Run extraction: select strategy from profile, run; if confidence < threshold
        and allow_escalation, escalate to next strategy.
        """
        path = Path(pdf_path)
        strategy = self._strategy_for_profile(profile)
        result: ExtractionResult | None = None
        attempts: list[dict] = []

        while True:
            extractor = self._get_extractor(strategy)
            try:
                result = extractor.extract(path, profile)
            except Exception as e:
                attempts.append({"strategy": strategy, "error": str(e)})
                if allow_escalation:
                    next_s = self._next_strategy(strategy)
                    if next_s:
                        strategy = next_s
                        continue
                raise
            attempts.append({
                "strategy": strategy,
                "confidence_score": result.confidence_score,
                "pages_processed": result.pages_processed,
                "cost_estimate": result.cost_estimate,
            })
            if not allow_escalation or result.confidence_score >= self._threshold:
                break
            next_s = self._next_strategy(strategy)
            if not next_s or (next_s == "vision" and self._vision is None):
                break
            strategy = next_s

        assert result is not None
        # Log to ledger
        entry = {
            "doc_id": profile.doc_id,
            "file_name": profile.file_name,
            "strategy_used": result.strategy_used,
            "confidence_score": result.confidence_score,
            "cost_estimate": result.cost_estimate,
            "processing_time_seconds": result.processing_time_seconds,
            "pages_processed": result.pages_processed,
            "num_pages": profile.num_pages,
            "attempts": attempts,
        }
        _append_ledger_entry(self._ledger_path, entry)
        return result
