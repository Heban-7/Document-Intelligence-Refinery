"""
Phase 0: Character density and layout analysis using pdfplumber.
Run on corpus PDFs to derive thresholds for native vs scanned and layout complexity.
Output: JSON summary per document and per page for DOMAIN_NOTES and extraction_rules.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pdfplumber


def page_metrics(page) -> dict:
    """Compute per-page metrics for extraction strategy decisions."""
    width = float(page.width or 0)
    height = float(page.height or 0)
    page_area_pt2 = width * height
    if page_area_pt2 <= 0:
        return {"error": "no dimensions"}

    chars = page.chars or []
    text = (page.extract_text() or "") or ""
    char_count = len(text.replace("\n", "").replace(" ", ""))  # exclude spaces for density
    char_count_raw = len(text)

    # Character density: chars per 1000 pt² (normalize so values are readable)
    density = (char_count / page_area_pt2) * 1000 if page_area_pt2 else 0

    # Image area: sum of image bboxes
    images = page.images or []
    image_area = 0.0
    for im in images:
        x0, top, x1, bottom = im.get("x0", 0), im.get("top", 0), im.get("x1", 0), im.get("bottom", 0)
        image_area += (x1 - x0) * (bottom - top)
    image_ratio = image_area / page_area_pt2 if page_area_pt2 else 0

    # Text span area (bbox of all chars) vs page area -> proxy for "whitespace"
    if chars:
        x0_min = min(c.get("x0", 0) for c in chars)
        x1_max = max(c.get("x1", 0) for c in chars)
        top_min = min(c.get("top", 0) for c in chars)
        bottom_max = max(c.get("bottom", 0) for c in chars)
        text_span_area = (x1_max - x0_min) * (bottom_max - top_min)
        text_coverage_ratio = text_span_area / page_area_pt2
    else:
        text_coverage_ratio = 0.0

    # Font metadata presence (digital PDFs usually have font info)
    has_font_metadata = any(c.get("fontname") for c in chars) if chars else False

    return {
        "page_area_pt2": round(page_area_pt2, 1),
        "char_count": char_count_raw,
        "char_count_no_ws": char_count,
        "char_density_per_1k_pt2": round(density, 4),
        "image_area_ratio": round(image_ratio, 4),
        "text_coverage_ratio": round(text_coverage_ratio, 4),
        "has_font_metadata": has_font_metadata,
        "num_chars_objects": len(chars),
        "num_images": len(images),
    }


def analyze_pdf(path: Path) -> dict:
    """Analyze one PDF; return doc-level summary and per-page metrics."""
    result = {
        "path": str(path),
        "name": path.name,
        "pages": [],
        "summary": {},
    }
    try:
        with pdfplumber.open(path) as pdf:
            for i, page in enumerate(pdf.pages):
                m = page_metrics(page)
                m["page_no"] = i + 1
                result["pages"].append(m)
            # Document-level summary
            if result["pages"]:
                result["summary"] = {
                    "num_pages": len(result["pages"]),
                    "avg_char_density": round(
                        sum(p.get("char_density_per_1k_pt2", 0) for p in result["pages"]) / len(result["pages"]), 4
                    ),
                    "avg_image_ratio": round(
                        sum(p.get("image_area_ratio", 0) for p in result["pages"]) / len(result["pages"]), 4
                    ),
                    "total_chars": sum(p.get("char_count", 0) for p in result["pages"]),
                    "pages_with_font_metadata": sum(1 for p in result["pages"] if p.get("has_font_metadata")),
                    "low_text_pages": sum(1 for p in result["pages"] if (p.get("char_count") or 0) < 100),
                }
    except Exception as e:
        result["error"] = str(e)
    return result


def main():
    repo_root = Path(__file__).resolve().parent.parent
    data_dir = repo_root / "data"
    if not data_dir.is_dir():
        print("data/ not found", file=sys.stderr)
        sys.exit(1)

    all_results = {}
    for pdf_path in sorted(data_dir.glob("*.pdf")):
        print(f"Analyzing {pdf_path.name}...", file=sys.stderr)
        all_results[pdf_path.name] = analyze_pdf(pdf_path)

    out_path = repo_root / ".refinery" / "phase0_pdfplumber_analysis.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Wrote {out_path}", file=sys.stderr)
    print(json.dumps(all_results, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
