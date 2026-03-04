# Document Intelligence Refinery

Multi-stage document intelligence pipeline: triage → extraction (multi-strategy) → semantic chunking → PageIndex → query agent, with full provenance.

## Setup

```bash
uv sync
```

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
