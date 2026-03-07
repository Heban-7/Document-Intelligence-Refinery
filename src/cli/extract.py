"""
CLI: run Triage + ExtractionRouter on a PDF or folder. Optionally dump ExtractedDocument JSON.
Usage: python -m src.cli.extract path/to.pdf [--output-dir] [--no-save-profile]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agents.triage import TriageAgent
from src.agents.extractor import ExtractionRouter
from src.models.common import profile_path_for_doc


def main() -> int:
    parser = argparse.ArgumentParser(description="Run triage + extraction on a PDF or folder.")
    parser.add_argument("path", type=Path, help="Path to PDF file or directory of PDFs")
    parser.add_argument("--output-dir", type=Path, default=None, help="Dump ExtractedDocument JSON here (default: .refinery/extractions/)")
    parser.add_argument("--no-save-profile", action="store_true", help="Do not save DocumentProfile to .refinery/profiles/")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root (default: cwd)")
    parser.add_argument("--no-escalation", action="store_true", help="Disable confidence-gated escalation")
    args = parser.parse_args()

    repo_root = args.repo_root or Path.cwd()
    if not args.path.exists():
        print(f"Error: path not found: {args.path}", file=sys.stderr)
        return 1

    if args.path.is_file():
        pdfs = [args.path]
    else:
        pdfs = sorted(args.path.glob("*.pdf"))
        if not pdfs:
            print("No PDFs found.", file=sys.stderr)
            return 1

    triage_agent = TriageAgent()
    router = ExtractionRouter(ledger_path=repo_root / ".refinery" / "extraction_ledger.jsonl")
    out_dir = args.output_dir or (repo_root / ".refinery" / "extractions")
    if args.output_dir or not args.no_save_profile:
        out_dir.mkdir(parents=True, exist_ok=True)

    for pdf_path in pdfs:
        print(f"Processing {pdf_path.name}...", file=sys.stderr)
        try:
            profile = triage_agent.run(pdf_path)
            if not args.no_save_profile:
                profile_path = profile_path_for_doc(profile.doc_id, repo_root)
                profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
            result = router.run(pdf_path, profile, allow_escalation=not args.no_escalation)
            print(
                f"  {result.strategy_used} confidence={result.confidence_score:.2f} "
                f"pages={result.pages_processed} time={result.processing_time_seconds:.1f}s",
                file=sys.stderr,
            )
            # Dump ExtractedDocument JSON
            out_path = out_dir / f"{result.document.doc_id}.json"
            out_path.write_text(
                result.document.model_dump_json(indent=2),
                encoding="utf-8",
            )
            print(f"  Wrote {out_path}", file=sys.stderr)
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
