"""
CLI: run Triage Agent on a PDF and save DocumentProfile to .refinery/profiles/{doc_id}.json
Usage: python -m src.cli.triage path/to.pdf [--no-save]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Add project root so "src" resolves when run as __main__
if __name__ == "__main__" and str(Path(__file__).resolve().parent.parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.agents.triage import TriageAgent
from src.models.common import profile_path_for_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Triage Agent on a PDF and output DocumentProfile.")
    parser.add_argument("pdf_path", type=Path, help="Path to PDF file")
    parser.add_argument("--no-save", action="store_true", help="Do not write profile to .refinery/profiles/")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root (default: cwd)")
    args = parser.parse_args()

    if not args.pdf_path.exists():
        print(f"Error: file not found: {args.pdf_path}", file=sys.stderr)
        return 1

    agent = TriageAgent()
    try:
        profile = agent.run(args.pdf_path)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    out = profile.model_dump(mode="json")
    print(json.dumps(out, indent=2))

    if not args.no_save:
        repo_root = args.repo_root or Path.cwd()
        path = profile_path_for_doc(profile.doc_id, repo_root)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, indent=2)
        print(f"Saved profile to {path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
