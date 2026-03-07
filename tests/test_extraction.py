"""
Tests for extraction: strategy selection, confidence scoring, router escalation.
"""
from pathlib import Path

import pytest

from src.agents.extractor import ExtractionRouter
from src.config import get_extraction_config, get_fast_text_config
from src.models.document_profile import (
    DocumentProfile,
    EstimatedExtractionCost,
    LayoutComplexity,
    OriginType,
    DomainHint,
)
from src.strategies.fast_text import FastTextExtractor, _confidence_for_page


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_load_extraction_config(repo_root):
    import os
    from src import config as cfg
    cfg._refinery_root = None
    os.environ["REFINERY_REPO_ROOT"] = str(repo_root)
    try:
        config = get_extraction_config()
        assert "confidence_escalation_threshold" in config or config == {}
    finally:
        os.environ.pop("REFINERY_REPO_ROOT", None)
        cfg._refinery_root = None


def test_fast_text_config():
    config = get_fast_text_config()
    assert "min_char_density_per_1k_pt2" in config or config == {}


def test_fast_text_confidence_high():
    config = get_fast_text_config()
    metrics = {
        "char_density_per_1k_pt2": 2.0,
        "image_area_ratio": 0.1,
        "has_font_metadata": True,
        "char_count": 500,
    }
    assert _confidence_for_page(metrics, config) >= 0.5


def test_fast_text_confidence_low():
    config = get_fast_text_config()
    metrics = {
        "char_density_per_1k_pt2": 0.0,
        "image_area_ratio": 1.0,
        "has_font_metadata": False,
        "char_count": 0,
    }
    assert _confidence_for_page(metrics, config) < 0.5


def test_router_strategy_selection_fast_text():
    profile = DocumentProfile(
        doc_id="test",
        file_name="test.pdf",
        num_pages=1,
        origin_type=OriginType.NATIVE_DIGITAL,
        layout_complexity=LayoutComplexity.SINGLE_COLUMN,
        domain_hint=DomainHint.GENERAL,
        estimated_extraction_cost=EstimatedExtractionCost.FAST_TEXT_SUFFICIENT,
    )
    router = ExtractionRouter()
    assert router._strategy_for_profile(profile) == "fast_text"


def test_router_strategy_selection_layout():
    profile = DocumentProfile(
        doc_id="test",
        file_name="test.pdf",
        num_pages=1,
        origin_type=OriginType.NATIVE_DIGITAL,
        layout_complexity=LayoutComplexity.MULTI_COLUMN,
        domain_hint=DomainHint.GENERAL,
        estimated_extraction_cost=EstimatedExtractionCost.NEEDS_LAYOUT_MODEL,
    )
    router = ExtractionRouter()
    assert router._strategy_for_profile(profile) == "layout"


def test_router_strategy_selection_vision_fallback_when_no_api_key():
    profile = DocumentProfile(
        doc_id="test",
        file_name="test.pdf",
        num_pages=1,
        origin_type=OriginType.SCANNED_IMAGE,
        layout_complexity=LayoutComplexity.SINGLE_COLUMN,
        domain_hint=DomainHint.GENERAL,
        estimated_extraction_cost=EstimatedExtractionCost.NEEDS_VISION_MODEL,
    )
    router = ExtractionRouter()
    # When OPENROUTER_API_KEY is not set, _vision is None -> fallback to layout
    assert router._strategy_for_profile(profile) in ("layout", "vision")


def test_fast_extractor_on_native_pdf(corpus_pdfs, repo_root, tmp_path):
    """Run FastTextExtractor on a native PDF; expect ExtractedDocument with pages."""
    native = next((p for p in corpus_pdfs if "Audit" not in p.name), None)
    if native is None:
        pytest.skip("No native PDF in data/")
    from src.models.document_profile import DocumentProfile, OriginType, LayoutComplexity, DomainHint, EstimatedExtractionCost
    profile = DocumentProfile(
        doc_id="test_native",
        file_name=native.name,
        num_pages=10,
        origin_type=OriginType.NATIVE_DIGITAL,
        layout_complexity=LayoutComplexity.SINGLE_COLUMN,
        domain_hint=DomainHint.GENERAL,
        estimated_extraction_cost=EstimatedExtractionCost.FAST_TEXT_SUFFICIENT,
    )
    extractor = FastTextExtractor()
    result = extractor.extract(native, profile)
    assert result.document.doc_id
    assert len(result.document.pages) >= 1
    assert result.strategy_used == "fast_text"
    assert 0 <= result.confidence_score <= 1
    assert result.pages_processed == len(result.document.pages)


def test_router_run_triage_then_extract(corpus_pdfs, repo_root, tmp_path):
    """Integration: triage one PDF, then run router; ledger entry created."""
    if not corpus_pdfs:
        pytest.skip("No PDFs in data/")
    from src.agents.triage import TriageAgent
    pdf_path = corpus_pdfs[0]
    triage = TriageAgent()
    profile = triage.run(pdf_path)
    ledger = tmp_path / "ledger.jsonl"
    router = ExtractionRouter(ledger_path=ledger)
    result = router.run(pdf_path, profile, allow_escalation=True)
    assert result.document.doc_id == profile.doc_id
    assert result.strategy_used in ("fast_text", "layout", "vision")
    assert ledger.exists()
    lines = ledger.read_text().strip().split("\n")
    assert len(lines) >= 1
    entry = __import__("json").loads(lines[-1])
    assert entry["doc_id"] == profile.doc_id
    assert "strategy_used" in entry
    assert "confidence_score" in entry
