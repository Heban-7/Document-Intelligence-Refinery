"""
Unit and integration tests for the Triage Agent.
- Classification logic (origin_type, layout_complexity) from synthetic and real corpus.
- Domain hint and language detection on known text.
"""
from pathlib import Path

import pytest

from src.agents.triage import (
    DomainHintClassifier,
    TriageAgent,
    _classify_layout_complexity,
    _classify_origin_type,
    _estimate_extraction_cost,
    _load_triage_config,
)
from src.models.document_profile import (
    DomainHint,
    EstimatedExtractionCost,
    LayoutComplexity,
    OriginType,
)


# ---- Config ----
def test_load_triage_config(repo_root):
    config = _load_triage_config(repo_root / "rubric" / "extraction_rules.yaml")
    assert "fast_text" in config or "scanned_image_ratio_min" in config or config == {}


# ---- Origin type ----
def test_origin_type_scanned():
    config = {"scanned_image_ratio_min": 0.5, "low_text_page_char_max": 100, "low_text_pages_majority": True}
    pages = [
        {"char_count": 0, "char_density_per_1k_pt2": 0, "image_area_ratio": 1.0, "has_font_metadata": False},
        {"char_count": 0, "char_density_per_1k_pt2": 0, "image_area_ratio": 1.0, "has_font_metadata": False},
    ]
    assert _classify_origin_type(pages, config) == OriginType.SCANNED_IMAGE


def test_origin_type_native_digital():
    config = {"scanned_image_ratio_min": 0.5, "low_text_page_char_max": 100, "low_text_pages_majority": True}
    pages = [
        {"char_count": 500, "char_density_per_1k_pt2": 2.5, "image_area_ratio": 0.05, "has_font_metadata": True},
        {"char_count": 600, "char_density_per_1k_pt2": 3.0, "image_area_ratio": 0.08, "has_font_metadata": True},
    ]
    assert _classify_origin_type(pages, config) == OriginType.NATIVE_DIGITAL


# ---- Layout complexity ----
def test_layout_single_column():
    # One band of text (narrow x spread)
    chars = [{"x0": 50 + i % 20, "x1": 70 + i % 20, "top": 100, "bottom": 110} for i in range(50)]
    pages = [
        {"char_count": 200, "chars": chars, "page_width": 600, "page_height": 800, "image_area_ratio": 0},
    ]
    result = _classify_layout_complexity(pages)
    assert result in (LayoutComplexity.SINGLE_COLUMN, LayoutComplexity.MIXED)


# ---- Extraction cost ----
def test_estimate_cost_scanned():
    assert _estimate_extraction_cost(OriginType.SCANNED_IMAGE, LayoutComplexity.SINGLE_COLUMN) == EstimatedExtractionCost.NEEDS_VISION_MODEL


def test_estimate_cost_native_single_column():
    assert _estimate_extraction_cost(OriginType.NATIVE_DIGITAL, LayoutComplexity.SINGLE_COLUMN) == EstimatedExtractionCost.FAST_TEXT_SUFFICIENT


def test_estimate_cost_native_multi_column():
    assert _estimate_extraction_cost(OriginType.NATIVE_DIGITAL, LayoutComplexity.MULTI_COLUMN) == EstimatedExtractionCost.NEEDS_LAYOUT_MODEL


# ---- Domain classifier ----
def test_domain_classifier_financial():
    classifier = DomainHintClassifier()
    hint, conf = classifier.classify("Annual Report 2023. Financial statements and balance sheet. Revenue and expenditure.")
    assert hint == DomainHint.FINANCIAL
    assert 0 <= conf <= 1


def test_domain_classifier_technical():
    classifier = DomainHintClassifier()
    hint, _ = classifier.classify("Assessment of implementation. Survey methodology and findings.")
    assert hint == DomainHint.TECHNICAL


def test_domain_classifier_general():
    classifier = DomainHintClassifier()
    hint, conf = classifier.classify("Hello world. Random text.")
    assert hint == DomainHint.GENERAL
    assert 0 <= conf <= 1


# ---- Integration: real corpus (when data/ present) ----
@pytest.mark.parametrize("filename,expected_origin,expected_cost", [
    ("Audit Report - 2023.pdf", OriginType.SCANNED_IMAGE, EstimatedExtractionCost.NEEDS_VISION_MODEL),
])
def test_triage_audit_report_class_b(corpus_pdfs, filename, expected_origin, expected_cost):
    """Class B: Scanned government/legal -> scanned_image, needs_vision_model."""
    path = next((p for p in corpus_pdfs if p.name == filename), None)
    if path is None:
        pytest.skip(f"{filename} not in data/")
    agent = TriageAgent()
    profile = agent.run(path)
    assert profile.origin_type == expected_origin, f"expected {expected_origin} for {filename}"
    assert profile.estimated_extraction_cost == expected_cost


def test_triage_native_documents_class_a_c_d(corpus_pdfs):
    """Class A, C, D: native PDFs -> native_digital, not needs_vision_model (unless mixed)."""
    native_files = [f for f in ["CBE ANNUAL REPORT 2023-24.pdf", "fta_performance_survey_final_report_2022.pdf", "tax_expenditure_ethiopia_2021_22.pdf"] if any(p.name == f for p in corpus_pdfs)]
    if not native_files:
        pytest.skip("No native corpus PDFs in data/")
    agent = TriageAgent()
    for filename in native_files:
        path = next(p for p in corpus_pdfs if p.name == filename)
        profile = agent.run(path)
        assert profile.origin_type in (OriginType.NATIVE_DIGITAL, OriginType.MIXED), f"{filename} should be native or mixed"
        assert profile.estimated_extraction_cost in (EstimatedExtractionCost.FAST_TEXT_SUFFICIENT, EstimatedExtractionCost.NEEDS_LAYOUT_MODEL), f"{filename} should not require vision"
        assert profile.num_pages >= 1
        assert profile.doc_id
        assert profile.file_name == filename


def test_triage_profile_roundtrip(corpus_pdfs, repo_root, tmp_path):
    """Run triage, save profile to JSON, load and assert key fields."""
    if not corpus_pdfs:
        pytest.skip("No PDFs in data/")
    pdf_path = corpus_pdfs[0]
    agent = TriageAgent()
    profile = agent.run(pdf_path)
    out_path = tmp_path / f"{profile.doc_id}.json"
    out_path.write_text(profile.model_dump_json(indent=2))
    from src.models.document_profile import DocumentProfile
    loaded = DocumentProfile.model_validate_json(out_path.read_text())
    assert loaded.doc_id == profile.doc_id
    assert loaded.origin_type == profile.origin_type
    assert loaded.num_pages == profile.num_pages


def test_doc_id_from_path():
    from src.models.common import doc_id_from_path
    assert doc_id_from_path(Path("data/Audit Report - 2023.pdf")) == "Audit_Report_-_2023"
    assert doc_id_from_path(Path("CBE ANNUAL REPORT 2023-24.pdf")) == "CBE_ANNUAL_REPORT_2023-24"
