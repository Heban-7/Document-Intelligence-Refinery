"""
CLI: run query or audit. Usage: python -m src.cli.query "question" [--doc-id] [--audit]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from src.agents.query_agent import QueryAgent
from src.agents.audit import audit_claim
from src.data.vector_store import VectorStore
from src.data.fact_table import FactTableStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Query the refinery or audit a claim.")
    parser.add_argument("query", type=str, help="Natural language question or claim to verify")
    parser.add_argument("--doc-id", type=str, default=None, help="Restrict to this document")
    parser.add_argument("--audit", action="store_true", help="Audit mode: verify claim, return provenance or not_found")
    parser.add_argument("--repo-root", type=Path, default=None, help="Repo root (default: cwd)")
    parser.add_argument("--no-pageindex", action="store_true", help="Skip PageIndex navigation")
    parser.add_argument("--trace", action="store_true", help="Include tool_trace in output (verifiable orchestration)")
    args = parser.parse_args()

    repo_root = args.repo_root or Path.cwd()
    vector_path = repo_root / ".refinery" / "vector_db"
    if not vector_path.exists():
        print("Vector store not found. Run: uv run index .refinery/extractions/<doc_id>.json", file=sys.stderr)
        return 1

    store = VectorStore(persist_path=vector_path)
    fact_path = repo_root / ".refinery" / "facts.db"
    fact_store = FactTableStore(fact_path) if fact_path.exists() else None

    if args.audit:
        status, chain = audit_claim(args.query, store, fact_store, doc_id=args.doc_id)
        out = {"status": status, "provenance": chain.model_dump(mode="json")}
        print(json.dumps(out, indent=2))
        return 0 if status == "verified" else 1

    agent = QueryAgent(vector_store=store, fact_store=fact_store, repo_root=repo_root)
    if args.trace:
        result = agent.query_with_trace(
            args.query, doc_id=args.doc_id, use_pageindex=not args.no_pageindex
        )
        out = {
            "answer": result.answer,
            "provenance": result.provenance.model_dump(mode="json"),
            "tool_trace": [t.model_dump(mode="json") for t in result.tool_trace],
        }
    else:
        answer, chain = agent.query(
            args.query, doc_id=args.doc_id, use_pageindex=not args.no_pageindex
        )
        out = {"answer": answer, "provenance": chain.model_dump(mode="json")}
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
