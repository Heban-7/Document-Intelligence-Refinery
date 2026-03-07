# Document Intelligence Refinery

Multi-stage document intelligence pipeline: triage → extraction (multi-strategy) → semantic chunking → PageIndex → query agent, with full provenance.

## Deploy in under 10 minutes

1. **Clone and install**: `uv sync`
2. **Optional env** (for Strategy C / vision): set `OPENROUTER_API_KEY`; optionally `OPENROUTER_VLM_MODEL`, `REFINERY_VISION_BUDGET_USD`, `REFINERY_REPO_ROOT`
3. **Run the demo** on one PDF (triage → extraction → PageIndex → query with provenance):

   ```bash
   uv run python scripts/demo_protocol.py data/your.pdf "What are the main findings?"
   ```

4. **Or run steps manually**: `uv run triage data/your.pdf` → `uv run extract data/your.pdf` → `uv run index .refinery/extractions/<doc_id>.json` → `uv run query "Your question"`

**Docker**: build with `docker build -t refinery .`; run with mounted data and artifacts:

```bash
docker run --rm -v "%cd%\data:/app/data" -v "%cd%\.refinery:/app/.refinery" refinery python -m src.cli.triage /app/data/your.pdf
```

(Use `$(pwd)` instead of `%cd%` on Linux/macOS.)

## Setup

```bash
uv sync
```

### Environment variables

| Variable | Purpose |
|----------|---------|
| `OPENROUTER_API_KEY` | Required for Strategy C (vision/VLM); optional otherwise |
| `OPENROUTER_VLM_MODEL` | VLM model for vision extraction (default: `google/gemini-2.0-flash-exp:free`) |
| `REFINERY_VISION_BUDGET_USD` | Max USD per document for vision (default from `extraction_rules.yaml`) |
| `REFINERY_REPO_ROOT` | Root directory for `rubric/extraction_rules.yaml` (default: cwd) |

## Phase 0 (Domain onboarding)

- **PDF analysis (pdfplumber)** — character density, image ratio, font metadata for all PDFs in `data/`:

  ```bash
  uv run python scripts/phase0_pdfplumber_analysis.py
  ```

  Output: `.refinery/phase0_pdfplumber_analysis.json`

- **Docling sample** (optional; first run downloads OCR models; large scanned PDFs may hit memory limits):

  ```bash
  uv run python scripts/phase0_docling_sample.py
  ```

- **Domain notes**: See [DOMAIN_NOTES.md](DOMAIN_NOTES.md) for the extraction strategy decision tree, failure modes by document class, pipeline diagram, and empirical thresholds. Thresholds are codified in [rubric/extraction_rules.yaml](rubric/extraction_rules.yaml).

## Phase 1 (Triage Agent)

- **Run triage** on a PDF (writes `DocumentProfile` to `.refinery/profiles/{doc_id}.json`):

  ```bash
  uv run python -m src.cli.triage data/your.pdf
  ```

  After `uv sync`, you can also run: `uv run triage data/your.pdf`

  Options: `--no-save` (print only), `--repo-root PATH`

- **Tests** (from repo root):

  ```bash
  uv run pytest tests/test_triage.py -v
  ```

  Integration tests require the four corpus PDFs in `data/`; unit tests run without them.

## Phase 2 (Multi-Strategy Extraction)

- **Run triage + extraction** on a PDF or folder (writes profiles, `ExtractedDocument` JSON, and ledger):

  ```bash
  uv run python -m src.cli.extract data/your.pdf
  # or folder: uv run python -m src.cli.extract data/
  # or: uv run extract data/your.pdf
  ```

  Outputs: `.refinery/profiles/{doc_id}.json`, `.refinery/extractions/{doc_id}.json`, `.refinery/extraction_ledger.jsonl`

  Options: `--output-dir`, `--no-save-profile`, `--no-escalation`

- **Strategies**: A (pdfplumber fast text), B (Docling layout), C (OpenRouter VLM). Router selects from `DocumentProfile` and escalates when confidence &lt; threshold (see `rubric/extraction_rules.yaml`). For Strategy C set `OPENROUTER_API_KEY` (and optionally `OPENROUTER_VLM_MODEL`).

- **Tests**:

  ```bash
  uv run pytest tests/test_extraction.py -v
  ```

## Phase 3 (Chunking, PageIndex, Vector Store)

- **Chunk** an extraction and build PageIndex + vector store:

  ```bash
  uv run python -m src.cli.index .refinery/extractions/doc_id.json
  ```

  Outputs: `.refinery/pageindex/{doc_id}.json`, `.refinery/ldus/{doc_id}.json`, and ChromaDB at `.refinery/vector_db` (unless `--no-vector`).

  Options: `--no-vector`, `--repo-root`, `--vector-path`

- **Components**: ChunkingEngine (ExtractedDocument → LDUs with five rules), ChunkValidator, content_hash; **PageIndex** with nested section hierarchy (from numbered headings, e.g. 1., 1.1.) and traversal API (`get_by_path`, `get_by_id`, `flatten_depth_first`, `find_sections_by_topic`); topic-based navigation returns section titles for vector filter. VectorStore (ChromaDB, optional section filter). PageIndex-aware search: `pageindex_navigate(question, doc_id)` then `store.search(query, section_titles=...)`.

- **Tests**:

  ```bash
  uv run pytest tests/test_chunking.py -v
  ```

## Phase 4 (Query Agent & Provenance)

- **Query** the indexed corpus (run Phase 3 first):

  ```bash
  uv run python -m src.cli.query "What is the total revenue?"
  # or: uv run query "Your question"
  ```

  Returns JSON with `answer` and `provenance` (ProvenanceChain: document_name, page_number, content_hash, etc.).

- **Audit** a claim:

  ```bash
  uv run query "The report states revenue was 4.2B in Q3" --audit
  ```

  Returns `verified` with ProvenanceChain or `not_found`.

- **Components**: ProvenanceItem/ProvenanceChain; query tools (pageindex_navigate, semantic_search, structured_query); QueryAgent; FactTableStore (SQLite); audit_claim in audit.py. Fact table is populated when you run `index` on an extraction.

## Phase 5 (Packaging & demo)

- **Config**: All thresholds and escalation rules live in [rubric/extraction_rules.yaml](rubric/extraction_rules.yaml). API keys and cost caps are read from environment (see table above); see [src/config.py](src/config.py).

- **Demo protocol** (one command for the full pipeline on a single PDF):

  ```bash
  uv run python scripts/demo_protocol.py data/your.pdf "Your question?"
  ```

  Runs: triage → extraction → PageIndex + LDUs → query with provenance; prints answer and ProvenanceChain. Verify claims by opening the source PDF at the cited pages.

- **Docker**: `docker build -t refinery .` then run any CLI with mounted `data/` and `.refinery/` (see "Deploy in under 10 minutes" above).
