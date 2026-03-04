"""
Phase 0: Run Docling on sample documents to inspect DoclingDocument structure.
Output: Markdown and structure summary for DOMAIN_NOTES (layout, tables, figures).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def get_doc_structure(doc) -> dict:
    """Inspect Docling document structure for DOMAIN_NOTES (high-level)."""
    try:
        # Docling 2.x: document has export_to_markdown(), and internal structure
        md = doc.export_to_markdown() if hasattr(doc, "export_to_markdown") else ""
        structure = {
            "markdown_length": len(md),
            "markdown_preview": md[:1500] + "..." if len(md) > 1500 else md,
        }
        # Try to get tables / pictures if API available
        if hasattr(doc, "tables"):
            structure["num_tables"] = len(doc.tables) if doc.tables else 0
        if hasattr(doc, "pictures"):
            structure["num_pictures"] = len(doc.pictures) if doc.pictures else 0
        return structure
    except Exception as e:
        return {"error": str(e)}


def main():
    try:
        from docling.document_converter import DocumentConverter
    except ImportError:
        print("Docling not installed. Run: uv sync", file=sys.stderr)
        sys.exit(1)

    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    if not data_dir.is_dir():
        print("data/ not found", file=sys.stderr)
        sys.exit(1)

    converter = DocumentConverter()
    all_pdfs = sorted(data_dir.glob("*.pdf"))
    # Process native PDFs first (scanned Audit Report can cause memory issues)
    native_first = [p for p in all_pdfs if "Audit Report" not in p.name]
    scanned = [p for p in all_pdfs if "Audit Report" in p.name]
    pdfs = native_first + scanned
    parser = argparse.ArgumentParser(description="Run Docling on corpus PDFs for Phase 0.")
    parser.add_argument("--max-docs", type=int, default=0, help="Max documents to process (0 = all). Use 1 for a quick native-PDF sample.")
    args = parser.parse_args()
    if args.max_docs:
        pdfs = pdfs[: args.max_docs]
    results = {}

    for pdf_path in pdfs:
        print(f"Converting {pdf_path.name} with Docling...", file=sys.stderr)
        try:
            doc = converter.convert(str(pdf_path)).document
            results[pdf_path.name] = get_doc_structure(doc)
        except Exception as e:
            results[pdf_path.name] = {"error": str(e)}
            print(f"  Error: {e}", file=sys.stderr)

    out_path = repo_root / ".refinery" / "phase0_docling_sample.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}", file=sys.stderr)
    print(json.dumps(results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
