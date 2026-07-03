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
# WS-ocr-figures: label recall がこの値未満 & images[] が付くページは
# 「画像内テキストが image 化されて検索対象から落ちた疑い」として警告する
# (診断のみ。overall passed には影響させない)。
FIGURE_TEXT_LOSS_WARN = 0.5


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
    figures_metric = evaluate_figures(response, ground_truth)

    passed = (
        table_metric["passed"]
        and japanese_metric["passed"]
        and image_metric["passed"]
    )
    criteria = {
        "table_cell_match_rate": f">= {TABLE_THRESHOLD}",
        "japanese_cer": f"<= {JAPANESE_CER_THRESHOLD}",
        "image_count_match": "100%",
        "formula": "record textized vs image fallback; no pass threshold",
    }
    metrics: dict[str, Any] = {
        "table": table_metric,
        "japanese": japanese_metric,
        "images": image_metric,
        "formula": formula_metric,
    }
    if figures_metric is not None:
        criteria["figures"] = (
            "diagnostic only (no pass threshold): images[]/placeholder correspondence, "
            "in-figure label recall, aggregate body-text loss rate"
        )
        metrics["figures"] = figures_metric
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
        "criteria": criteria,
        "metrics": metrics,
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


def evaluate_figures(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any] | None:
    """WS-ocr-figures 診断: raster 図表の画像内テキストが検索対象から落ちていないか測る。

    ground_truth に `figures` が無い fixture (minimal writer フォールバック等) では None を返す。
    """
    figures_truth = ground_truth.get("figures")
    if not figures_truth:
        return None

    per_page: list[dict[str, Any]] = []
    total_labels = 0
    total_matched = 0
    for spec in figures_truth["pages"]:
        page = page_by_index(response, spec["page_index"])
        markdown = page.get("markdown", "")
        images_count = images_list_count(page)
        placeholder_count = markdown_placeholder_count(markdown)
        labels = spec.get("expected_label_texts", [])
        haystack = normalize_label(markdown)
        matched = [label for label in labels if normalize_label(label) in haystack]
        missing = [label for label in labels if label not in matched]
        recall = len(matched) / len(labels) if labels else 1.0
        total_labels += len(labels)
        total_matched += len(matched)
        # 画像化疑い: label をほぼ拾えていないのに images[] が付いている
        # (= 本文へ OCR されず placeholder + image に押し込まれた兆候)。
        loss_suspected = recall < FIGURE_TEXT_LOSS_WARN and images_count > 0
        per_page.append(
            {
                "page_index": spec["page_index"],
                "kind": spec.get("kind"),
                "images_count": images_count,
                "placeholder_count": placeholder_count,
                "placeholder_matches_images": placeholder_count == images_count,
                "expected_label_count": len(labels),
                "matched_label_count": len(matched),
                "label_recall": round(recall, 6),
                "missing_labels": missing,
                "text_loss_suspected": loss_suspected,
                "risk": spec.get("risk"),
            }
        )

    aggregate_recall = total_matched / total_labels if total_labels else 1.0
    return {
        "page_count": len(per_page),
        "aggregate_label_recall": round(aggregate_recall, 6),
        "body_text_loss_rate": round(1.0 - aggregate_recall, 6),
        "pages_with_text_loss_suspected": sum(1 for entry in per_page if entry["text_loss_suspected"]),
        "pages": per_page,
        "passed": None,
        "note": "Diagnostic only; human review required. Measures whether in-figure text stays searchable.",
    }


def images_list_count(page: dict[str, Any]) -> int:
    images = page.get("images")
    return len(images) if isinstance(images, list) else 0


def markdown_placeholder_count(markdown: str) -> int:
    return len(re.findall(r"!\[[^\]]*]\([^)]+\)", markdown))


def normalize_label(text: str) -> str:
    # ASCII ラベルの緩い一致: NFKC, 小文字化, markdown 記号除去, 空白全除去。
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[#*_`>|!\[\]()]", "", normalized)
    return re.sub(r"\s+", "", normalized)


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

    figures = results["metrics"].get("figures")
    if figures is not None:
        lines.extend(
            [
                "",
                "## Figures (WS-ocr-figures diagnostic)",
                "",
                "Diagnostic only; no pass/fail. Measures whether raster in-figure text stays searchable.",
                "",
                f"- Aggregate in-figure label recall: `{figures['aggregate_label_recall']}`",
                f"- Body-text loss rate: `{figures['body_text_loss_rate']}`",
                f"- Pages with text-loss suspected: `{figures['pages_with_text_loss_suspected']}/{figures['page_count']}`",
                "",
                "| page | kind | images[] | placeholders | match | label recall | loss? |",
                "| ---: | --- | ---: | ---: | :---: | ---: | :---: |",
            ]
        )
        for entry in figures["pages"]:
            lines.append(
                "| {page_index} | {kind} | {images_count} | {placeholder_count} | {match} | "
                "{recall} ({matched}/{total}) | {loss} |".format(
                    page_index=entry["page_index"],
                    kind=entry["kind"],
                    images_count=entry["images_count"],
                    placeholder_count=entry["placeholder_count"],
                    match="yes" if entry["placeholder_matches_images"] else "NO",
                    recall=entry["label_recall"],
                    matched=entry["matched_label_count"],
                    total=entry["expected_label_count"],
                    loss="YES" if entry["text_loss_suspected"] else "no",
                )
            )
        missing_any = [
            (entry["page_index"], entry["missing_labels"])
            for entry in figures["pages"]
            if entry["missing_labels"]
        ]
        if missing_any:
            lines.extend(["", "### Missing in-figure labels", ""])
            for page_index, missing in missing_any:
                lines.append(f"- page {page_index}: " + ", ".join(f"`{label}`" for label in missing))
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
