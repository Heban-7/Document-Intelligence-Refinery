"""
Central config: load rubric/extraction_rules.yaml and environment variables.
New document types are onboarded via extraction_rules.yaml, not code.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_refinery_root: Path | None = None
_rules: dict[str, Any] | None = None


def get_repo_root() -> Path:
    """Repo root: REFINERY_REPO_ROOT env or cwd."""
    global _refinery_root
    if _refinery_root is not None:
        return _refinery_root
    _refinery_root = Path(os.environ.get("REFINERY_REPO_ROOT", os.getcwd()))
    return _refinery_root


def get_extraction_rules_path() -> Path:
    return get_repo_root() / "rubric" / "extraction_rules.yaml"


def load_rules() -> dict[str, Any]:
    """Load rubric/extraction_rules.yaml; cache in process."""
    global _rules
    if _rules is not None:
        return _rules
    path = get_extraction_rules_path()
    if not path.exists():
        _rules = {}
        return _rules
    import yaml
    with open(path, encoding="utf-8") as f:
        _rules = yaml.safe_load(f) or {}
    return _rules


def get_triage_config() -> dict[str, Any]:
    return load_rules().get("triage", {})


def get_extraction_config() -> dict[str, Any]:
    return load_rules().get("extraction", {})


def get_chunking_config() -> dict[str, Any]:
    return load_rules().get("chunking", {})


def get_fast_text_config() -> dict[str, Any]:
    """Config for Strategy A (triage.fast_text + triage.low_text_page_char_max)."""
    triage = get_triage_config()
    fast = triage.get("fast_text", {})
    return {
        "min_char_density_per_1k_pt2": fast.get("min_char_density_per_1k_pt2", 0.5),
        "max_image_ratio": fast.get("max_image_ratio", 0.5),
        "require_font_metadata": fast.get("require_font_metadata", True),
        "low_text_page_char_max": triage.get("low_text_page_char_max", 100),
    }


# Environment-based overrides (no secrets in YAML)
def get_openrouter_api_key() -> str:
    return os.environ.get("OPENROUTER_API_KEY", "")


def get_openrouter_vlm_model() -> str:
    return os.environ.get("OPENROUTER_VLM_MODEL", "google/gemini-2.0-flash-exp:free")


def get_vision_budget_max_usd() -> float:
    val = os.environ.get("REFINERY_VISION_BUDGET_USD", "")
    if val:
        try:
            return float(val)
        except ValueError:
            pass
    return get_extraction_config().get("vision_budget_max_usd_per_doc", 2.0)
