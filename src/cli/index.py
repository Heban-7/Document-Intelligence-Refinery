"""
CLI: run ChunkingEngine + PageIndex builder + vector store ingest on an ExtractedDocument.
Usage: python -m src.cli.index path/to/extraction.json [--no-vector] [--repo-root]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agents.chunker import ChunkingEngine
from src.agents.indexer import build_page_index, save_page_index
from src.data.vector_store import VectorStore
from src.data.fact_table import FactTableStore
from src.models.extraction import ExtractedDocument


def main() -> int:
    parser = argparse.ArgumentParser(description="Chunk extraction, build PageIndex, ingest into vector store and fact table.")
    parser.add_argument("extraction_path", type=Path, help="Path to ExtractedDocument JSON (e.g. .refinery/extractions/doc_id.json)")
    parser.add_argument("--no-vector", action="store_true", help="Skip vector store ingest")
    parser.add_argument("--no-facts", action="store_true", help="Skip fact table ingest")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root (default: cwd)")
    parser.add_argument("--vector-path", type=Path, default=None, help="ChromaDB persist path (default: .refinery/vector_db)")
    args = parser.parse_args()

    repo_root = args.repo_root or Path.cwd()
    if not args.extraction_path.exists():
        print(f"Error: file not found: {args.extraction_path}", file=sys.stderr)
        return 1

    try:
        doc = ExtractedDocument.model_validate_json(args.extraction_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"Error loading extraction: {e}", file=sys.stderr)
        return 1

    engine = ChunkingEngine()
    ldus = engine.run(doc)
    print(f"Chunked into {len(ldus)} LDUs", file=sys.stderr)

    pi = build_page_index(doc, ldus)
    pi_path = save_page_index(pi, repo_root)
    print(f"PageIndex saved to {pi_path}", file=sys.stderr)

    if not args.no_vector:
        vector_path = args.vector_path or (repo_root / ".refinery" / "vector_db")
        store = VectorStore(persist_path=vector_path)
        n = store.ingest_ldus(ldus, doc.doc_id)
        print(f"Ingested {n} LDUs into vector store at {vector_path}", file=sys.stderr)
    if not args.no_facts:
        fact_store = FactTableStore(repo_root / ".refinery" / "facts.db")
        n_facts = fact_store.ingest_document(doc)
        print(f"Ingested {n_facts} fact rows into SQLite", file=sys.stderr)

    # Write LDUs JSON for inspection
    out_ldus = repo_root / ".refinery" / "ldus" / f"{doc.doc_id}.json"
    out_ldus.parent.mkdir(parents=True, exist_ok=True)
    out_ldus.write_text(
        json.dumps([l.model_dump(mode="json") for l in ldus], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"LDUs written to {out_ldus}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
