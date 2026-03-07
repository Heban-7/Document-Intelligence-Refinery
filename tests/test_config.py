"""Tests for central config (src.config)."""
from pathlib import Path

import pytest


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def test_get_repo_root_default(repo_root):
    from src import config
    config._refinery_root = None
    root = config.get_repo_root()
    assert root.is_dir()
    assert (root / "rubric").is_dir()


def test_get_repo_root_from_env(repo_root):
    import os
    from src import config
    config._refinery_root = None
    os.environ["REFINERY_REPO_ROOT"] = str(repo_root)
    try:
        root = config.get_repo_root()
        assert root == repo_root
    finally:
        os.environ.pop("REFINERY_REPO_ROOT", None)
        config._refinery_root = None


def test_load_rules_returns_dict(repo_root):
    import os
    from src import config
    config._rules = None
    config._refinery_root = repo_root
    os.environ["REFINERY_REPO_ROOT"] = str(repo_root)
    try:
        rules = config.load_rules()
        assert isinstance(rules, dict)
        assert "triage" in rules or rules == {}
    finally:
        config._rules = None
        config._refinery_root = None
        os.environ.pop("REFINERY_REPO_ROOT", None)


def test_get_vision_budget_from_env():
    import os
    from src.config import get_vision_budget_max_usd
    os.environ["REFINERY_VISION_BUDGET_USD"] = "1.5"
    try:
        assert get_vision_budget_max_usd() == 1.5
    finally:
        os.environ.pop("REFINERY_VISION_BUDGET_USD", None)
