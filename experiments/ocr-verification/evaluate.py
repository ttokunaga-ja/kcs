#!/usr/bin/env python3
"""Evaluate OCR output against the generated ground truth."""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_GROUND_TRUTH = ROOT / "fixtures" / "generated" / "ground_truth.json"
DEFAULT_RUN_RESPONSE = ROOT / "out" / "ocr_response.json"
DEFAULT_OUT_DIR = ROOT / "out"

TABLE_THRESHOLD = 0.95
JAPANESE_CER_THRESHOLD = 0.02


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Assert that the input OCR run was produced with --dry-run.")
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--ocr-response", type=Path, default=DEFAULT_RUN_RESPONSE)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ground_truth = load_json(args.ground_truth, "ground truth")
    run_record = load_json(args.ocr_response, "OCR response")
    if args.dry_run and not run_record.get("dry_run"):
        raise SystemExit(f"{args.ocr_response} was not produced by run_ocr.py --dry-run")

    response = run_record.get("response", run_record)
    table_metric = evaluate_table(response, ground_truth)
    japanese_metric = evaluate_japanese(response, ground_truth)
    image_metric = evaluate_image_count(response, ground_truth)
    formula_metric = evaluate_formula(response, ground_truth)

    passed = (
        table_metric["passed"]
        and japanese_metric["passed"]
        and image_metric["passed"]
    )
    results = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "dry_run": bool(run_record.get("dry_run")),
        "mode": run_record.get("mode"),
        "requested_model": run_record.get("requested_model"),
        "resolved_model": run_record.get("resolved_model"),
        "page_count": run_record.get("page_count"),
        "estimated_cost_usd": run_record.get("estimated_cost_usd"),
        "latency_seconds": run_record.get("latency_seconds"),
        "passed": passed,
        "criteria": {
            "table_cell_match_rate": f">= {TABLE_THRESHOLD}",
            "japanese_cer": f"<= {JAPANESE_CER_THRESHOLD}",
            "image_count_match": "100%",
            "formula": "record textized vs image fallback; no pass threshold",
        },
        "metrics": {
            "table": table_metric,
            "japanese": japanese_metric,
            "images": image_metric,
            "formula": formula_metric,
        },
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.out_dir / "results.json"
    report_path = args.out_dir / "report.md"
    write_json(results_path, results)
    report_path.write_text(render_report(results), encoding="utf-8")
    print(f"wrote {display_path(results_path)}")
    print(f"wrote {display_path(report_path)}")
    print(f"passed={passed}")
    if not passed:
        sys.exit(1)


def display_path(path: Path) -> str:
    # 相対 --out-dir (例: out-sync) でも ROOT 外の絶対パスでも落ちない表示用変換。
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def evaluate_table(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    table_truth = ground_truth["table"]
    page = page_by_index(response, table_truth["page_index"])
    markdown = page.get("markdown", "")
    expected = table_truth["expected_cell_texts"]
    haystack = normalize_cell(markdown)
    matched = [cell for cell in expected if normalize_cell(cell) in haystack]
    rate = len(matched) / len(expected) if expected else 1.0
    missing = [cell for cell in expected if cell not in matched]
    return {
        "page_index": table_truth["page_index"],
        "matched_cells": len(matched),
        "total_cells": len(expected),
        "match_rate": round(rate, 6),
        "missing_cells": missing,
        "passed": rate >= TABLE_THRESHOLD,
    }


def evaluate_japanese(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    japanese_truth = ground_truth["japanese"]
    page = page_by_index(response, japanese_truth["page_index"])
    expected = normalize_japanese(japanese_truth["full_text"])
    observed = normalize_japanese(page.get("markdown", ""))
    distance = best_window_distance(expected, observed)
    cer = distance / len(expected) if expected else 0.0
    return {
        "page_index": japanese_truth["page_index"],
        "expected_chars": len(expected),
        "observed_chars": len(observed),
        "edit_distance": distance,
        "cer": round(cer, 6),
        "passed": cer <= JAPANESE_CER_THRESHOLD,
    }


def evaluate_image_count(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    image_truth = ground_truth["images"]
    page = page_by_index(response, image_truth["page_index"])
    expected = int(image_truth["expected_count"])
    observed = count_page_images(page)
    return {
        "page_index": image_truth["page_index"],
        "expected_count": expected,
        "observed_count": observed,
        "passed": observed == expected,
    }


def evaluate_formula(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    formula_truth = ground_truth["formula"]
    page = page_by_index(response, formula_truth["page_index"])
    markdown = page.get("markdown", "")
    normalized = normalize_formula(markdown)
    expected_tokens = formula_truth["expected_tokens"]
    token_matches = [token for token in expected_tokens if normalize_formula(token) in normalized]
    if len(token_matches) == len(expected_tokens):
        status = "textized"
    elif count_page_images(page) > 0 or re.search(r"!\[[^\]]*]\([^)]+\)", markdown):
        status = "image_fallback"
    else:
        status = "missing"
    return {
        "page_index": formula_truth["page_index"],
        "expected_tokens": expected_tokens,
        "matched_tokens": token_matches,
        "status": status,
        "passed": None,
        "note": "No pass threshold; human review required.",
    }


def page_by_index(response: dict[str, Any], index: int) -> dict[str, Any]:
    pages = response.get("pages")
    if not isinstance(pages, list):
        raise ValueError("OCR response does not contain pages[]")
    for offset, page in enumerate(pages):
        if page.get("index", offset) == index:
            return page
    try:
        return pages[index]
    except IndexError as exc:
        raise ValueError(f"OCR response is missing page index {index}") from exc


def count_page_images(page: dict[str, Any]) -> int:
    images = page.get("images")
    if isinstance(images, list):
        return len(images)
    markdown = page.get("markdown", "")
    return len(re.findall(r"!\[[^\]]*]\([^)]+\)", markdown))


def normalize_cell(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = normalized.replace(",", "")
    return re.sub(r"[\s|:：`*_\\-]+", "", normalized).lower()


def normalize_japanese(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text)
    normalized = re.sub(r"[#*_`>|]", "", normalized)
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def normalize_formula(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = normalized.replace("∫", "int")
    normalized = normalized.replace("²", "^2")
    # LaTeX 表記 ($$\int_{0}^{1} 等) と素朴表記 (int_0^1) を同一視する:
    # コマンドのバックスラッシュ、グルーピング braces、数式デリミタ $ を除去。
    normalized = re.sub(r"\\([a-z]+)", r"\1", normalized)
    normalized = normalized.translate(str.maketrans("", "", "{}$"))
    return re.sub(r"\s+", "", normalized)


def best_window_distance(expected: str, observed: str) -> int:
    if not expected:
        return 0
    if len(observed) <= len(expected):
        return levenshtein(expected, observed)
    if expected in observed:
        return 0
    window = len(expected)
    best = levenshtein(expected, observed[:window])
    for start in range(1, len(observed) - window + 1):
        best = min(best, levenshtein(expected, observed[start : start + window]))
    trailing = levenshtein(expected, observed[-window:])
    return min(best, trailing)


def levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (left_char != right_char)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def render_report(results: dict[str, Any]) -> str:
    table = results["metrics"]["table"]
    japanese = results["metrics"]["japanese"]
    images = results["metrics"]["images"]
    formula = results["metrics"]["formula"]
    status = "PASS" if results["passed"] else "FAIL"
    lines = [
        "# OCR verification report",
        "",
        f"Status: **{status}**",
        "",
        "## Run",
        "",
        f"- Mode: `{results.get('mode')}`",
        f"- Dry-run: `{results.get('dry_run')}`",
        f"- Requested model: `{results.get('requested_model')}`",
        f"- Resolved model from response: `{results.get('resolved_model')}`",
        f"- Pages: `{results.get('page_count')}`",
        f"- Latency seconds: `{results.get('latency_seconds')}`",
        f"- Estimated cost USD: `{results.get('estimated_cost_usd')}`",
        "",
        "## Provisional acceptance criteria",
        "",
        f"- Table cell match rate >= {TABLE_THRESHOLD}",
        f"- Japanese CER <= {JAPANESE_CER_THRESHOLD}",
        "- Embedded image extraction count matches 100%",
        "- Formula: record whether textized or image fallback; no pass threshold, human review required",
        "",
        "## Metrics",
        "",
        f"- Table cell match rate: `{table['match_rate']}` ({table['matched_cells']}/{table['total_cells']})",
        f"- Japanese CER: `{japanese['cer']}` (edit distance {japanese['edit_distance']}/{japanese['expected_chars']})",
        f"- Image count: `{images['observed_count']}` expected `{images['expected_count']}`",
        f"- Formula status: `{formula['status']}` matched tokens `{len(formula['matched_tokens'])}/{len(formula['expected_tokens'])}`",
    ]
    if table["missing_cells"]:
        lines.extend(["", "## Missing table cells", ""])
        lines.extend(f"- `{cell}`" for cell in table["missing_cells"])
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
