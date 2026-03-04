"""Pytest fixtures and test layout."""
from pathlib import Path

import pytest

# Repo root (parent of tests/)
REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def data_dir() -> Path:
    return DATA_DIR


@pytest.fixture
def corpus_pdfs():
    """Paths to the four document-class PDFs if present."""
    data = REPO_ROOT / "data"
    if not data.is_dir():
        return []
    pdfs = list(data.glob("*.pdf"))
    return sorted(pdfs)
