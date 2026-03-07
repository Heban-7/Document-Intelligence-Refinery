"""
Demo protocol: run the four steps required for the submission video.
1. Triage — drop a document, show DocumentProfile, explain strategy selection
2. Extraction — show extraction output and ledger entry with confidence
3. PageIndex — show tree and navigate to a section without vector search
4. Query with provenance — ask a question, show answer + ProvenanceChain, verify against source

Usage: uv run python scripts/demo_protocol.py path/to/document.pdf [question]
If question is omitted, a default is used for step 4.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure repo root on path and config
REPO_ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("REFINERY_REPO_ROOT", str(REPO_ROOT))
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def step1_triage(pdf_path: Path) -> dict:
    """Run triage, print profile, return profile dict."""
    from src.agents.triage import TriageAgent
    from src.models.common import profile_path_for_doc
    agent = TriageAgent()
    profile = agent.run(pdf_path)
    out_path = profile_path_for_doc(profile.doc_id, REPO_ROOT)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    d = profile.model_dump(mode="json")
    print("=== Step 1: Triage ===\nDocumentProfile:")
    print(json.dumps(d, indent=2))
    print(f"\nStrategy selected: {d['estimated_extraction_cost']} (from origin_type={d['origin_type']}, layout_complexity={d['layout_complexity']})")
    return d


def step2_extraction(pdf_path: Path, profile: dict) -> dict:
    """Run extraction, show ledger entry and extraction summary."""
    from src.agents.triage import TriageAgent
    from src.models.document_profile import DocumentProfile
    from src.agents.extractor import ExtractionRouter
    from src.models.common import doc_id_from_path
    profile_obj = DocumentProfile.model_validate(profile)
    router = ExtractionRouter(ledger_path=REPO_ROOT / ".refinery" / "extraction_ledger.jsonl")
    result = router.run(pdf_path, profile_obj, allow_escalation=True)
    doc_id = doc_id_from_path(pdf_path)
    extraction_dir = REPO_ROOT / ".refinery" / "extractions"
    extraction_dir.mkdir(parents=True, exist_ok=True)
    (extraction_dir / f"{doc_id}.json").write_text(result.document.model_dump_json(indent=2), encoding="utf-8")
    print("\n=== Step 2: Extraction ===")
    print(f"Strategy used: {result.strategy_used}, confidence: {result.confidence_score:.2f}, pages: {result.pages_processed}, time: {result.processing_time_seconds:.1f}s")
    print("Ledger entry appended to .refinery/extraction_ledger.jsonl")
    return result.model_dump(mode="json")


def step3_pageindex(doc_id: str) -> dict | None:
    """Build PageIndex from extraction, print section tree."""
    from src.models.extraction import ExtractedDocument
    from src.agents.chunker import ChunkingEngine
    from src.agents.indexer import build_page_index, save_page_index
    extraction_path = REPO_ROOT / ".refinery" / "extractions" / f"{doc_id}.json"
    if not extraction_path.exists():
        print("\n=== Step 3: PageIndex ===\n(No extraction found; run step 2 first.)")
        return None
    doc = ExtractedDocument.model_validate_json(extraction_path.read_text(encoding="utf-8"))
    engine = ChunkingEngine()
    ldus = engine.run(doc)
    pi = build_page_index(doc, ldus)
    save_page_index(pi, REPO_ROOT)
    print("\n=== Step 3: PageIndex ===")
    print("Section tree (nested):")
    def _print_tree(nodes, indent=0):
        for n in nodes:
            print(f"  {'  ' * indent}- {n.title} (pp. {n.page_start}-{n.page_end})" + (f" path={n.path}" if n.path else ""))
            _print_tree(n.child_sections, indent + 1)
    _print_tree(pi.sections)
    return pi.model_dump(mode="json")


def step4_query(doc_id: str, question: str) -> None:
    """Run index (if needed), then query; print answer and ProvenanceChain."""
    from src.data.vector_store import VectorStore
    from src.agents.query_agent import QueryAgent
    from src.models.extraction import ExtractedDocument
    from src.agents.chunker import ChunkingEngine
    from src.agents.indexer import build_page_index, save_page_index
    from src.data.fact_table import FactTableStore
    extraction_path = REPO_ROOT / ".refinery" / "extractions" / f"{doc_id}.json"
    vector_path = REPO_ROOT / ".refinery" / "vector_db"
    if extraction_path.exists() and not vector_path.exists():
        doc = ExtractedDocument.model_validate_json(extraction_path.read_text(encoding="utf-8"))
        engine = ChunkingEngine()
        ldus = engine.run(doc)
        pi = build_page_index(doc, ldus)
        save_page_index(pi, REPO_ROOT)
        store = VectorStore(persist_path=vector_path)
        store.ingest_ldus(ldus, doc_id)
        fact_store = FactTableStore(REPO_ROOT / ".refinery" / "facts.db")
        fact_store.ingest_document(doc)
    store = VectorStore(persist_path=vector_path)
    fact_store = FactTableStore(REPO_ROOT / ".refinery" / "facts.db") if (REPO_ROOT / ".refinery" / "facts.db").exists() else None
    agent = QueryAgent(vector_store=store, fact_store=fact_store, repo_root=REPO_ROOT)
    answer, chain = agent.query(question, doc_id=doc_id)
    print("\n=== Step 4: Query with Provenance ===")
    print(f"Q: {question}\nA: {answer[:500]}{'...' if len(answer) > 500 else ''}")
    print("\nProvenanceChain:")
    print(json.dumps(chain.model_dump(mode="json"), indent=2))
    print("\nVerify: open the source PDF to the cited page(s) and confirm the claim.")


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run python scripts/demo_protocol.py path/to/document.pdf [question]")
        sys.exit(1)
    pdf_path = Path(sys.argv[1])
    question = sys.argv[2] if len(sys.argv) > 2 else "What are the main figures or findings reported?"
    if not pdf_path.exists():
        print(f"File not found: {pdf_path}")
        sys.exit(1)
    profile = step1_triage(pdf_path)
    doc_id = profile["doc_id"]
    step2_extraction(pdf_path, profile)
    step3_pageindex(doc_id)
    step4_query(doc_id, question)
    print("\n=== Demo protocol complete ===")


if __name__ == "__main__":
    main()
