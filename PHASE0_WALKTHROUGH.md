# Phase 0 Walkthrough — Domain Onboarding

This guide walks you through Phase 0 from the plan and project documentation: **what to do**, **how to run the scripts** on the provided PDFs, and **how to prepare DOMAIN_NOTES.md**.

---

## What Phase 0 Is For (from the plan and project doc)

**Goal:** Understand document science and your corpus *before* building the pipeline. You learn:

- The difference between **native PDFs** (text layer) and **scanned PDFs** (images only).
- How **character density**, **image area ratio**, and **font metadata** distinguish them.
- How to choose extraction strategy (fast text vs layout vs vision) from data, not guesswork.

**Deliverable:** `DOMAIN_NOTES.md` with:

1. **Extraction strategy decision tree** (when to use Strategy A / B / C).
2. **Failure modes** observed per document class (A–D).
3. **Pipeline diagram** (Mermaid or hand-drawn).

---

## Step 1 — Environment and corpus

### 1.1 Create environment and install dependencies

From the **repo root** (the folder that contains `pyproject.toml`):

```bash
uv sync
```

If you don’t use `uv`:

```bash
pip install -e .
# or: pip install pydantic pdfplumber pymupdf docling langdetect pyyaml
```

### 1.2 Put the provided PDFs in `data/`

Place the four example PDFs from the project in a folder named `data/` at the repo root:

| Class | Example file | Role |
|-------|----------------|------|
| **A** | `CBE ANNUAL REPORT 2023-24.pdf` | Native digital, multi-column, financial |
| **B** | `Audit Report - 2023.pdf` | Scanned, image-based |
| **C** | `fta_performance_survey_final_report_2022.pdf` | Mixed: text + tables + findings |
| **D** | `tax_expenditure_ethiopia_2021_22.pdf` | Table-heavy, numerical |

Your layout should look like:

```
Document-Intelligence-Refinery/
  data/
    Audit Report - 2023.pdf
    CBE ANNUAL REPORT 2023-24.pdf
    fta_performance_survey_final_report_2022.pdf
    tax_expenditure_ethiopia_2021_22.pdf
  scripts/
  ...
```

### 1.3 Confirm PDFs are readable

From repo root:

```bash
uv run python -c "import pdfplumber; from pathlib import Path; p = list(Path('data').glob('*.pdf')); print(len(p), 'PDFs'); print([x.name for x in p])"
```

You should see 4 PDFs (or however many you added). If you see `0 PDFs`, fix the `data/` path and file names.

---

## Step 2 — Run the pdfplumber analysis script

This script computes **per-page and per-document** metrics for every PDF in `data/`.

### 2.1 Run it

From **repo root**:

```bash
uv run python scripts/phase0_pdfplumber_analysis.py
```

- It reads all `*.pdf` in `data/`.
- It writes one combined JSON file and also prints it to stdout.

### 2.2 Where the result is

- **File:** `.refinery/phase0_pdfplumber_analysis.json`
- The script also prints the same JSON; you can redirect to a file if you prefer:
  ```bash
  uv run python scripts/phase0_pdfplumber_analysis.py > analysis_output.json
  ```
  The file under `.refinery/` is still created.

### 2.3 How to read the result

Open `.refinery/phase0_pdfplumber_analysis.json`. For **each document** you have:

- **Per page:**  
  `char_count`, `char_density_per_1k_pt2`, `image_area_ratio`, `has_font_metadata`, etc.
- **Summary (per document):**
  - `num_pages`
  - `avg_char_density` — higher = more text per page area (typical for native PDFs).
  - `avg_image_ratio` — higher = page is mostly image (typical for scanned).
  - `total_chars`
  - `pages_with_font_metadata` — native PDFs usually have font info on most pages.
  - `low_text_pages` — count of pages with `char_count < 100`.

**What to look for:**

- **Class B (Audit Report):**  
  Very low `avg_char_density`, `avg_image_ratio` near 1, most pages with few or no chars → **scanned**.
- **Classes A, C, D:**  
  Higher `avg_char_density`, lower `avg_image_ratio`, most pages with font metadata → **native** (or mixed).

Use these numbers to set thresholds (e.g. “treat as scanned when `avg_image_ratio > 0.5`” or “low-text when `char_count < 100` per page”). You’ll put those into `DOMAIN_NOTES.md` and later into `rubric/extraction_rules.yaml`.

---

## Step 3 — (Optional) Run Docling on sample documents

Docling gives layout-aware extraction (tables, figures, reading order). Phase 0 asks you to run it on the same documents and compare.

### 3.1 Run it

From **repo root**:

```bash
uv run python scripts/phase0_docling_sample.py
```

- By default it runs on all PDFs in `data/` (native ones first).
- First run can download OCR models; large or scanned PDFs may be slow or run out of memory.

**Quick run (one document only):**

```bash
uv run python scripts/phase0_docling_sample.py --max-docs 1
```

### 3.2 Where the result is

- **File:** `.refinery/phase0_docling_sample.json`
- Contains, per document: `markdown_length`, `markdown_preview`, and optionally `num_tables`, `num_pictures`, or an `error` if conversion failed.

### 3.3 What to note for DOMAIN_NOTES

- Which documents converted successfully and what the structure looks like (tables, pictures).
- Any errors (e.g. `std::bad_alloc`, timeouts) and on which document type (scanned vs native, size).
- A short note for Phase 2: “Docling works well for …; for … we may need Strategy C or batching.”

---

## Step 4 — Derive decision rules and thresholds

Using the **pdfplumber** (and optionally Docling) results:

1. **Native vs scanned**
   - e.g. “If `avg_image_ratio > 0.5` and majority of pages have `char_count < 100` → treat as scanned.”
2. **When fast text (Strategy A) is OK**
   - e.g. “Only when `char_density` above X, `image_ratio` below Y, and font metadata present.”
3. **When to use layout (B) or vision (C)**
   - Scanned → C (or Docling with OCR if it runs).
   - Native but multi-column / table-heavy → B.

Write these down in a short list or table; you’ll turn them into **Section 2** of DOMAIN_NOTES and into `rubric/extraction_rules.yaml`.

---

## Step 5 — Prepare DOMAIN_NOTES.md

Use the project’s existing `DOMAIN_NOTES.md` as the template. Fill or adjust these parts using **your** script outputs and observations.

### 5.1 Section 1 — Document science basics

- Keep or lightly edit the explanation of **native vs scanned vs mixed** and why **Strategy A / B / C** exist.
- No need to change this if the template already matches the plan.

### 5.2 Section 2 — Extraction strategy decision tree

- **Decision tree:** Keep or redraw the ASCII/Mermaid tree so it matches your rules (e.g. “origin type → layout complexity → confidence gate → Strategy A/B/C”).
- **Decision rules table:** Keep the condition → strategy mapping; tune the “Suggested thresholds” bullet list using **your** `.refinery/phase0_pdfplumber_analysis.json`:
  - e.g. “Character count per page &lt; 100 → low text”
  - “Character density &lt; 0.5 → low confidence for Strategy A”
  - “Image area ratio &gt; 0.5 → prefer B or C”
- **Link** to `rubric/extraction_rules.yaml` and note that Phase 1/2 will read thresholds from there.

### 5.3 Section 3 — Failure modes by document class

For **each** of the four classes (A–D), fill in:

- **Traits:** native/scanned, layout (single/multi-column, table-heavy, etc.).
- **Failure modes:** e.g. “Strategy A returns empty for Class B”; “naive chunking splits tables for Class A.”
- **Mitigation:** Which strategy and which pipeline choices (chunking, PageIndex, provenance) address them.

Use your **actual** script results (e.g. “Audit Report had 94/95 low-text pages”) to make the failure modes concrete.

### 5.4 Section 4 — Pipeline diagram

- Keep or redraw the **Mermaid** flowchart so it shows: Ingest → Triage → Router → Strategies A/B/C → ExtractedDocument → Chunking → PageIndex / Vector store / FactTable → Query Agent → Answers + Provenance.
- The plan and `DOMAIN_NOTES.md` already have an example; ensure it matches your mental model.

### 5.5 Section 5 — Tooling landscape

- Short notes on **pdfplumber**, **Docling**, **MinerU** (reference), **VLM**: what each is used for in the refinery. No need to run MinerU; reading its docs is enough to summarize.

### 5.6 Section 6 — Phase 0 artifacts

- List the two scripts and the two output files:
  - `scripts/phase0_pdfplumber_analysis.py` → `.refinery/phase0_pdfplumber_analysis.json`
  - `scripts/phase0_docling_sample.py` → `.refinery/phase0_docling_sample.json`
- Mention that thresholds are (or will be) in `rubric/extraction_rules.yaml`.

### 5.7 Section 7 — Empirical notes

- **From phase0_pdfplumber_analysis.json:**  
  Paste or summarize a small table (document name, class, `avg_char_density`, `avg_image_ratio`, `low_text_pages`, etc.) and state the thresholds you chose and why.
- **From phase0_docling_sample.json:**  
  What worked, what failed (e.g. memory on large scanned PDFs), and what you’ll do in Phase 2 (adapter, batching, or fallback to Strategy C).

---

## Quick reference — Commands (run from repo root)

| Step | Command | Output |
|------|---------|--------|
| Install deps | `uv sync` | — |
| Check PDFs | `uv run python -c "from pathlib import Path; print(list(Path('data').glob('*.pdf')))"` | List of PDF paths |
| **pdfplumber analysis** | `uv run python scripts/phase0_pdfplumber_analysis.py` | `.refinery/phase0_pdfplumber_analysis.json` + stdout |
| **Docling sample (all)** | `uv run python scripts/phase0_docling_sample.py` | `.refinery/phase0_docling_sample.json` |
| **Docling sample (1 doc)** | `uv run python scripts/phase0_docling_sample.py --max-docs 1` | Same file, fewer docs |

---

## Checklist before you say “Phase 0 done”

- [ ] `data/` contains at least the four example PDFs (or your chosen subset).
- [ ] `uv sync` (or equivalent) has been run.
- [ ] `phase0_pdfplumber_analysis.py` has been run and `.refinery/phase0_pdfplumber_analysis.json` exists.
- [ ] You have looked at the JSON and noted avg density, image ratio, and low-text pages per document.
- [ ] (Optional) `phase0_docling_sample.py` has been run; you noted success/failure and any OOM/errors.
- [ ] `DOMAIN_NOTES.md` has:
  - [ ] Section 2: decision tree + rules + **your** thresholds from the analysis.
  - [ ] Section 3: failure modes for classes A–D with concrete references to your metrics.
  - [ ] Section 4: pipeline diagram (Mermaid or equivalent).
  - [ ] Section 7: empirical notes from both scripts (pdfplumber summary + Docling).

After that, you’re ready to move to Phase 1 (Triage Agent) with thresholds and rules grounded in your own data.
