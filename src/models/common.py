"""
Shared utilities for doc identity and refinery artifact paths.
"""
from __future__ import annotations

from pathlib import Path


def doc_id_from_path(path: str | Path) -> str:
    """
    Derive a stable doc_id from a file path (e.g. for profile and ledger keys).
    Uses stem + sanitized name so same file always maps to same id.
    """
    p = Path(path)
    stem = p.stem
    # Replace spaces and problematic chars for filesystem-safe id
    safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in stem)
    return safe or "unknown"


def refinery_profiles_dir(repo_root: str | Path | None = None) -> Path:
    """Return the .refinery/profiles directory, creating if needed."""
    if repo_root is None:
        # Assume we're in repo root or cwd is repo root
        repo_root = Path.cwd()
    root = Path(repo_root)
    profiles = root / ".refinery" / "profiles"
    profiles.mkdir(parents=True, exist_ok=True)
    return profiles


def profile_path_for_doc(doc_id: str, repo_root: str | Path | None = None) -> Path:
    """Path to DocumentProfile JSON for the given doc_id."""
    return refinery_profiles_dir(repo_root) / f"{doc_id}.json"
