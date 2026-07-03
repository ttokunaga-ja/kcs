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
# 生成画像 fixture 用の別 ground truth / 別出力先 (run_ocr.py --fixture generated-images と対応)。
GENERATED_IMAGES_GROUND_TRUTH = ROOT / "fixtures" / "generated" / "generated_images_ground_truth.json"
GENERATED_IMAGES_OUT_DIR = ROOT / "out" / "generated-images"

TABLE_THRESHOLD = 0.95
JAPANESE_CER_THRESHOLD = 0.02
# WS-ocr-figures: label recall がこの値未満 & images[] が付くページは
# 「画像内テキストが image 化されて検索対象から落ちた疑い」として警告する
# (診断のみ。overall passed には影響させない)。
FIGURE_TEXT_LOSS_WARN = 0.5
# 系統C 境界調査: 段階間で stage token recall がこの delta 以上落ちたら「境界」とみなす。
BOUNDARY_DROP_DELTA = 0.25
# stage recall がこの床を割った最初の段階を、明確な急落が無いときの境界候補にする。
BOUNDARY_RECALL_FLOOR = 0.5
# 系統A/B: recall がこの値未満なら「ラスタからのテキスト回収に失敗した疑い」を診断表示。
RASTER_RECALL_WARN = 0.5
# 生成画像: visible_text の正規化トークン回収率から観測分類を付ける診断閾値。
GENERATED_TEXT_RECALL_HIGH = 0.7
GENERATED_IMAGE_RECALL_LOW = 0.3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Assert that the input OCR run was produced with --dry-run.")
    parser.add_argument(
        "--fixture",
        choices=["default", "generated-images"],
        default="default",
        help="default = 18-page synthetic fixture; generated-images = 15 delivered ambiguous images "
        "(sets --ground-truth / --ocr-response / --out-dir defaults unless overridden).",
    )
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--ocr-response", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    args = parser.parse_args()
    if args.fixture == "generated-images":
        if args.ground_truth is None:
            args.ground_truth = GENERATED_IMAGES_GROUND_TRUTH
        if args.out_dir is None:
            args.out_dir = GENERATED_IMAGES_OUT_DIR
        if args.ocr_response is None:
            args.ocr_response = GENERATED_IMAGES_OUT_DIR / "ocr_response.json"
    else:
        if args.ground_truth is None:
            args.ground_truth = DEFAULT_GROUND_TRUTH
        if args.out_dir is None:
            args.out_dir = DEFAULT_OUT_DIR
        if args.ocr_response is None:
            args.ocr_response = DEFAULT_RUN_RESPONSE
    return args


def main() -> None:
    args = parse_args()
    ground_truth = load_json(args.ground_truth, "ground truth")
    run_record = load_json(args.ocr_response, "OCR response")
    if args.dry_run and not run_record.get("dry_run"):
        raise SystemExit(f"{args.ocr_response} was not produced by run_ocr.py --dry-run")

    # 生成画像 fixture は別スキーマ・別レポート。既存 18 ページ fixture の評価と混ざらないよう
    # ここで完全に分岐する (out/generated-images/ 配下だけに出力し、overall pass に絡めない)。
    if ground_truth.get("dataset") == "generated-images":
        run_generated_images(args, ground_truth, run_record)
        return

    response = run_record.get("response", run_record)
    table_metric = evaluate_table(response, ground_truth)
    japanese_metric = evaluate_japanese(response, ground_truth)
    image_metric = evaluate_image_count(response, ground_truth)
    formula_metric = evaluate_formula(response, ground_truth)
    figures_metric = evaluate_figures(response, ground_truth)
    rasterized_metric = evaluate_rasterized_text(response, ground_truth)
    handwriting_metric = evaluate_handwriting(response, ground_truth)
    staged_metric = evaluate_staged_boundary(response, ground_truth)

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
    if rasterized_metric is not None:
        criteria["rasterized_text"] = (
            "系統A diagnostic only: whole-page raster (no text layer); per-page text recovery recall"
        )
        metrics["rasterized_text"] = rasterized_metric
    if handwriting_metric is not None:
        criteria["handwriting"] = "系統B diagnostic only: simulated-handwriting token recall"
        metrics["handwriting"] = handwriting_metric
    if staged_metric is not None:
        criteria["staged_boundary"] = (
            "系統C boundary study (diagnostic only): per-stage zone token recall + images[]; "
            "boundary = stage where recall collapses (see boundary-report.md)"
        )
        metrics["staged_boundary"] = staged_metric
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
    if staged_metric is not None:
        boundary_path = args.out_dir / "boundary-report.md"
        boundary_path.write_text(render_boundary_report(staged_metric, results), encoding="utf-8")
        print(f"wrote {display_path(boundary_path)}")
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


def evaluate_rasterized_text(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any] | None:
    """系統A 診断: 全面 raster ページ (text layer なし) から元テキストを OCR が回収できるか。

    ページ種別ごとに既存の正規化を再利用: 表=cell recall, 日本語=CER→recall, 数式=token recall。
    `rasterized_text` セクションが無い fixture では None。
    """
    section = ground_truth.get("rasterized_text")
    if not section:
        return None

    pages: list[dict[str, Any]] = []
    recalls: list[float] = []
    for spec in section["pages"]:
        page = page_by_index(response, spec["page_index"])
        markdown = page.get("markdown", "")
        images_count = images_list_count(page)
        kind = spec["kind"]
        entry: dict[str, Any] = {"page_index": spec["page_index"], "kind": kind, "images_count": images_count}
        if kind == "raster_table":
            expected = spec["expected_cell_texts"]
            haystack = normalize_cell(markdown)
            matched = [cell for cell in expected if normalize_cell(cell) in haystack]
            recall = len(matched) / len(expected) if expected else 1.0
            entry.update(
                {
                    "metric": "cell_recall",
                    "recall": round(recall, 6),
                    "matched": len(matched),
                    "total": len(expected),
                    "missing": [cell for cell in expected if cell not in matched],
                }
            )
        elif kind == "raster_japanese":
            expected = normalize_japanese(spec["full_text"])
            observed = normalize_japanese(markdown)
            distance = best_window_distance(expected, observed)
            cer = distance / len(expected) if expected else 0.0
            recall = max(0.0, 1.0 - cer)
            entry.update(
                {
                    "metric": "japanese_cer",
                    "recall": round(recall, 6),
                    "cer": round(cer, 6),
                    "edit_distance": distance,
                    "expected_chars": len(expected),
                }
            )
        else:  # raster_formula
            expected_tokens = spec["expected_tokens"]
            normalized = normalize_formula(markdown)
            matched = [token for token in expected_tokens if normalize_formula(token) in normalized]
            recall = len(matched) / len(expected_tokens) if expected_tokens else 1.0
            entry.update(
                {
                    "metric": "formula_token_recall",
                    "recall": round(recall, 6),
                    "matched": len(matched),
                    "total": len(expected_tokens),
                    "missing": [token for token in expected_tokens if token not in matched],
                }
            )
        entry["text_recovery_suspected_loss"] = recall < RASTER_RECALL_WARN
        recalls.append(recall)
        pages.append(entry)

    aggregate = sum(recalls) / len(recalls) if recalls else 1.0
    return {
        "page_count": len(pages),
        "aggregate_recall": round(aggregate, 6),
        "pages_with_suspected_loss": sum(1 for entry in pages if entry["text_recovery_suspected_loss"]),
        "pages": pages,
        "passed": None,
        "note": "Diagnostic only; measures whether OCR recovers text from a full-page raster (no text layer).",
    }


def evaluate_handwriting(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any] | None:
    """系統B 診断: 手書き風ページの既知トークン recall。`handwriting` セクションが無ければ None。"""
    section = ground_truth.get("handwriting")
    if not section:
        return None

    pages: list[dict[str, Any]] = []
    total_tokens = 0
    total_matched = 0
    for spec in section["pages"]:
        page = page_by_index(response, spec["page_index"])
        markdown = page.get("markdown", "")
        haystack = normalize_token(markdown)
        expected = spec["expected_texts"]
        matched = [token for token in expected if normalize_token(token) in haystack]
        recall = len(matched) / len(expected) if expected else 1.0
        total_tokens += len(expected)
        total_matched += len(matched)
        pages.append(
            {
                "page_index": spec["page_index"],
                "kind": spec["kind"],
                "images_count": images_list_count(page),
                "expected_count": len(expected),
                "matched_count": len(matched),
                "token_recall": round(recall, 6),
                "missing_tokens": [token for token in expected if token not in matched],
            }
        )
    aggregate = total_matched / total_tokens if total_tokens else 1.0
    return {
        "page_count": len(pages),
        "aggregate_token_recall": round(aggregate, 6),
        "pages": pages,
        "passed": None,
        "note": "Diagnostic only; measures OCR token recall on simulated handwriting.",
    }


def evaluate_staged_boundary(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any] | None:
    """系統C 境界調査: 段階 C0..C5 で zone (body/table/figure) 別 token recall と images[] を測り、
    recall が急落する『境界』を機械判定する。`staged_boundary` セクションが無ければ None。
    """
    section = ground_truth.get("staged_boundary")
    if not section:
        return None

    stages: list[dict[str, Any]] = []
    for spec in section["stages"]:
        page = page_by_index(response, spec["page_index"])
        markdown = page.get("markdown", "")
        haystack = normalize_token(markdown)
        zones: dict[str, Any] = {}
        stage_total = 0
        stage_matched = 0
        for zone in ("body", "table", "figure"):
            tokens = spec["tokens"].get(zone, [])
            matched = [token for token in tokens if normalize_token(token) in haystack]
            stage_total += len(tokens)
            stage_matched += len(matched)
            zones[zone] = {
                "total": len(tokens),
                "matched": len(matched),
                "recall": round(len(matched) / len(tokens), 6) if tokens else None,
                "missing": [token for token in tokens if token not in matched],
            }
        stage_recall = stage_matched / stage_total if stage_total else 1.0
        stages.append(
            {
                "stage": spec["stage"],
                "page_index": spec["page_index"],
                "kind": spec["kind"],
                "images_count": images_list_count(page),
                "placeholder_count": markdown_placeholder_count(markdown),
                "total_tokens": stage_total,
                "matched_tokens": stage_matched,
                "stage_recall": round(stage_recall, 6),
                "zones": zones,
            }
        )

    boundary = detect_boundary(stages)
    return {
        "stage_count": len(stages),
        "stages": stages,
        "boundary": boundary,
        "passed": None,
        "note": "Boundary study (diagnostic only); detects the stage where in-figure/table text stops being OCR'd to markdown.",
    }


def detect_boundary(stages: list[dict[str, Any]]) -> dict[str, Any]:
    """段階別 stage_recall から境界 (急落段階) を機械判定する。

    優先1: 前段からの低下量が BOUNDARY_DROP_DELTA 以上で最大の段階 (reason=sharp_drop)。
    優先2: 急落が無ければ stage_recall が BOUNDARY_RECALL_FLOOR を最初に割った段階 (reason=below_floor)。
    どちらも無ければ detected=None (reason=none)。
    """
    drops: list[dict[str, Any]] = []
    for index in range(1, len(stages)):
        previous = stages[index - 1]["stage_recall"]
        current = stages[index]["stage_recall"]
        drops.append(
            {
                "from_stage": stages[index - 1]["stage"],
                "to_stage": stages[index]["stage"],
                "from_recall": previous,
                "to_recall": current,
                "delta": round(previous - current, 6),
            }
        )
    sharpest = max(drops, key=lambda drop: drop["delta"]) if drops else None
    below = [stage["stage"] for stage in stages if stage["stage_recall"] < BOUNDARY_RECALL_FLOOR]
    first_below = below[0] if below else None

    if sharpest is not None and sharpest["delta"] >= BOUNDARY_DROP_DELTA:
        detected = sharpest["to_stage"]
        reason = "sharp_drop"
    elif first_below is not None:
        detected = first_below
        reason = "below_floor"
    else:
        detected = None
        reason = "none"
    return {
        "detected_stage": detected,
        "reason": reason,
        "drop_delta_threshold": BOUNDARY_DROP_DELTA,
        "recall_floor": BOUNDARY_RECALL_FLOOR,
        "sharpest_drop": sharpest,
        "first_below_floor": first_below,
        "drops": drops,
    }


def normalize_token(text: str) -> str:
    # 合成 unique トークン (例: C3-FIG-AXIS-61) の OCR ゆらぎ耐性マッチ: NFKC・小文字化・
    # markdown 記号除去・空白/ハイフン/アンダースコア/ドット全除去 (spacing/hyphen 差を吸収)。
    normalized = unicodedata.normalize("NFKC", text).lower()
    normalized = re.sub(r"[#*_`>|!\[\]()]", "", normalized)
    return re.sub(r"[\s\-‐-―._]+", "", normalized)


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

    rasterized = results["metrics"].get("rasterized_text")
    if rasterized is not None:
        lines.extend(
            [
                "",
                "## Rasterized text (系統A diagnostic)",
                "",
                "Whole-page raster with no text layer (metadata text extraction impossible). "
                "Measures whether OCR recovers the original text from the rendered image.",
                "",
                f"- Aggregate recovery recall: `{rasterized['aggregate_recall']}`",
                f"- Pages with suspected loss: `{rasterized['pages_with_suspected_loss']}/{rasterized['page_count']}`",
                "",
                "| page | kind | metric | recall | images[] | suspected loss |",
                "| ---: | --- | --- | ---: | ---: | :---: |",
            ]
        )
        for entry in rasterized["pages"]:
            lines.append(
                "| {page} | {kind} | {metric} | {recall} | {images} | {loss} |".format(
                    page=entry["page_index"],
                    kind=entry["kind"],
                    metric=entry["metric"],
                    recall=entry["recall"],
                    images=entry["images_count"],
                    loss="YES" if entry["text_recovery_suspected_loss"] else "no",
                )
            )

    handwriting = results["metrics"].get("handwriting")
    if handwriting is not None:
        lines.extend(
            [
                "",
                "## Handwriting (系統B diagnostic)",
                "",
                "Simulated handwriting (per-glyph rotation / baseline / spacing / stroke jitter). "
                "Measures OCR token recall.",
                "",
                f"- Aggregate token recall: `{handwriting['aggregate_token_recall']}`",
                "",
                "| page | kind | token recall | images[] |",
                "| ---: | --- | ---: | ---: |",
            ]
        )
        for entry in handwriting["pages"]:
            lines.append(
                "| {page} | {kind} | {recall} ({matched}/{total}) | {images} |".format(
                    page=entry["page_index"],
                    kind=entry["kind"],
                    recall=entry["token_recall"],
                    matched=entry["matched_count"],
                    total=entry["expected_count"],
                    images=entry["images_count"],
                )
            )

    staged = results["metrics"].get("staged_boundary")
    if staged is not None:
        boundary = staged["boundary"]
        lines.extend(
            [
                "",
                "## Image-ization boundary (系統C study)",
                "",
                f"Detected boundary stage: `{boundary['detected_stage']}` (reason: `{boundary['reason']}`). "
                "Full per-stage/zone breakdown in `boundary-report.md`.",
                "",
                "| stage | kind | stage recall | body | table | figure | images[] |",
                "| --- | --- | ---: | ---: | ---: | ---: | ---: |",
            ]
        )
        for stage in staged["stages"]:
            zones = stage["zones"]
            lines.append(
                "| {stage} | {kind} | {recall} | {body} | {table} | {figure} | {images} |".format(
                    stage=stage["stage"],
                    kind=stage["kind"],
                    recall=stage["stage_recall"],
                    body=_zone_cell(zones["body"]),
                    table=_zone_cell(zones["table"]),
                    figure=_zone_cell(zones["figure"]),
                    images=stage["images_count"],
                )
            )
    return "\n".join(lines) + "\n"


def _zone_cell(zone: dict[str, Any]) -> str:
    if zone["recall"] is None:
        return "-"
    return f"{zone['recall']} ({zone['matched']}/{zone['total']})"


def render_boundary_report(staged: dict[str, Any], results: dict[str, Any]) -> str:
    """系統C 境界調査レポート (boundary-report.md)。段階別 token recall と images[] を表にし、境界を明示。"""
    boundary = staged["boundary"]
    detected = boundary["detected_stage"]
    lines = [
        "# Image-ization boundary report (系統C)",
        "",
        "ラスタ化 PDF ページに段階的に表・グラフを足し、図/表/本文の既知トークンが markdown 本文に "
        "出るか (= 検索可能) / images[] に消えるかを段階別に測る。recall が急落する段階が『画像化境界』。",
        "",
        "## Run",
        "",
        f"- Mode: `{results.get('mode')}`",
        f"- Dry-run: `{results.get('dry_run')}`",
        f"- Resolved model: `{results.get('resolved_model')}`",
        "",
        "## Detected boundary",
        "",
        (
            f"- **Boundary stage: `{detected}`**"
            if detected is not None
            else "- **Boundary stage: none detected** (recall did not collapse)"
        ),
        f"- Reason: `{boundary['reason']}` "
        f"(sharp-drop delta >= {boundary['drop_delta_threshold']}, recall floor {boundary['recall_floor']})",
    ]
    if boundary["sharpest_drop"] is not None:
        drop = boundary["sharpest_drop"]
        lines.append(
            f"- Sharpest drop: `{drop['from_stage']}` -> `{drop['to_stage']}` "
            f"({drop['from_recall']} -> {drop['to_recall']}, delta {drop['delta']})"
        )
    lines.append(f"- First stage below recall floor: `{boundary['first_below_floor']}`")
    lines.extend(
        [
            "",
            "## Per-stage token recall (body / table / figure)",
            "",
            "Boundary の見方: figure/table zone の recall が落ち、かつ images[] が増える段階が、"
            "「図表領域テキストが本文へ OCR されず画像に押し込まれ始めた」= 検索から落ち始めた点。",
            "",
            "| stage | kind | body | table | figure | stage recall | images[] | placeholders |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for stage in staged["stages"]:
        zones = stage["zones"]
        marker = "  <- boundary" if stage["stage"] == detected else ""
        lines.append(
            "| {stage}{marker} | {kind} | {body} | {table} | {figure} | {recall} | {images} | {ph} |".format(
                stage=stage["stage"],
                marker=marker,
                kind=stage["kind"],
                body=_zone_cell(zones["body"]),
                table=_zone_cell(zones["table"]),
                figure=_zone_cell(zones["figure"]),
                recall=stage["stage_recall"],
                images=stage["images_count"],
                ph=stage["placeholder_count"],
            )
        )
    lines.extend(["", "## Stage-to-stage recall drops", "", "| from | to | delta |", "| --- | --- | ---: |"])
    for drop in boundary["drops"]:
        lines.append(f"| {drop['from_stage']} | {drop['to_stage']} | {drop['delta']} |")

    missing_any = [
        (stage["stage"], zone_name, stage["zones"][zone_name]["missing"])
        for stage in staged["stages"]
        for zone_name in ("body", "table", "figure")
        if stage["zones"][zone_name]["missing"]
    ]
    if missing_any:
        lines.extend(["", "## Missing tokens (dropped from markdown body)", ""])
        for stage_name, zone_name, missing in missing_any:
            lines.append(
                f"- {stage_name} / {zone_name}: " + ", ".join(f"`{token}`" for token in missing)
            )
    return "\n".join(lines) + "\n"


# ===========================================================================
# 生成画像 fixture (Codex APP 納品の曖昧画像 15 枚) の評価。
# 既存 18 ページ fixture とはスキーマ・レポートともに独立。
# ===========================================================================


def run_generated_images(args: argparse.Namespace, ground_truth: dict[str, Any], run_record: dict[str, Any]) -> None:
    response = run_record.get("response", run_record)
    metric = evaluate_generated_images(response, ground_truth)
    results = {
        "schema_version": 1,
        "dataset": "generated-images",
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "dry_run": bool(run_record.get("dry_run")),
        "mode": run_record.get("mode"),
        "requested_model": run_record.get("requested_model"),
        "resolved_model": run_record.get("resolved_model"),
        "page_count": run_record.get("page_count"),
        "estimated_cost_usd": run_record.get("estimated_cost_usd"),
        "latency_seconds": run_record.get("latency_seconds"),
        "passed": None,
        "criteria": {
            "generated_images": (
                "diagnostic only (no pass threshold): per image (i) embedded token in markdown body, "
                "(ii) visible_text normalized-token recall, (iii) returned as images[]; "
                f"observed class = text-dominant if recall>={GENERATED_TEXT_RECALL_HIGH}, "
                f"image-dominant if recall<{GENERATED_IMAGE_RECALL_LOW}, else mixed"
            )
        },
        "metrics": {"generated_images": metric},
    }
    args.out_dir.mkdir(parents=True, exist_ok=True)
    results_path = args.out_dir / "results.json"
    report_path = args.out_dir / "report.md"
    write_json(results_path, results)
    report_path.write_text(render_generated_images_report(results), encoding="utf-8")
    print(f"wrote {display_path(results_path)}")
    print(f"wrote {display_path(report_path)}")
    summary = metric["summary"]
    print(
        f"generated-images pages={metric['page_count']} "
        f"aggregate_visible_recall={summary['aggregate_visible_recall']} "
        f"token_hit={summary['token_hit_pages']}/{metric['page_count']} "
        f"expect_match={summary['expect_match_pages']}/{metric['page_count']}"
    )


def tokenize_visible_text(text: str) -> list[str]:
    """visible_text を正規化トークン列に分解する。

    `;` (segment 区切り) と空白で分割し、normalize_token 後に空になるもの・1 文字のものは
    ノイズ (単一数字/記号) として捨てる。CJK 句 (例: 牛乳) は空白で分かれた語単位で残る。
    """
    tokens: list[str] = []
    for segment in text.split(";"):
        for word in segment.split():
            normalized = normalize_token(word)
            if len(normalized) >= 2:
                tokens.append(word.strip())
    return tokens


def classify_generated_observed(visible_recall: float, images_count: int) -> str:
    if visible_recall >= GENERATED_TEXT_RECALL_HIGH:
        return "text-dominant"
    if visible_recall < GENERATED_IMAGE_RECALL_LOW:
        return "image-dominant"
    return "mixed"


def evaluate_generated_images(response: dict[str, Any], ground_truth: dict[str, Any]) -> dict[str, Any]:
    """画像 (=ページ) ごとに token 本文出現 / visible_text 回収率 / images[] を測り、
    family 別集計と expect (text-dominant/mixed/image-dominant) との突合を返す。
    """
    expect_classes = ["text-dominant", "mixed", "image-dominant"]
    pages: list[dict[str, Any]] = []
    for entry in ground_truth["pages"]:
        page = page_by_index(response, entry["page_index"])
        markdown = page.get("markdown", "")
        haystack = normalize_token(markdown)

        # (i) 埋め込みトークンが markdown 本文に出たか。
        tokens = entry.get("tokens", [])
        token_hits = [tok for tok in tokens if normalize_token(tok) in haystack]
        token_hit = bool(tokens) and len(token_hits) == len(tokens)

        # (ii) visible_text の正規化トークン回収率。
        vis_tokens = tokenize_visible_text(entry.get("visible_text", ""))
        matched = [tok for tok in vis_tokens if normalize_token(tok) in haystack]
        recall = len(matched) / len(vis_tokens) if vis_tokens else 1.0

        # (iii) images[] として返ったか。
        images_count = images_list_count(page)

        observed = classify_generated_observed(recall, images_count)
        pages.append(
            {
                "page_index": entry["page_index"],
                "file": entry["file"],
                "family": entry["family"],
                "expect": entry["expect"],
                "observed": observed,
                "expect_match": observed == entry["expect"],
                "token_count": len(tokens),
                "token_hit_count": len(token_hits),
                "token_hit": token_hit,
                "visible_token_count": len(vis_tokens),
                "visible_matched_count": len(matched),
                "visible_recall": round(recall, 6),
                "images_count": images_count,
                "returned_as_image": images_count > 0,
            }
        )

    families: dict[str, dict[str, Any]] = {}
    for entry in pages:
        fam = families.setdefault(
            entry["family"],
            {"family": entry["family"], "pages": 0, "recall_sum": 0.0, "token_hit": 0, "returned_as_image": 0, "expect_match": 0},
        )
        fam["pages"] += 1
        fam["recall_sum"] += entry["visible_recall"]
        fam["token_hit"] += int(entry["token_hit"])
        fam["returned_as_image"] += int(entry["returned_as_image"])
        fam["expect_match"] += int(entry["expect_match"])
    family_rows = []
    for fam in sorted(families.values(), key=lambda item: item["family"]):
        family_rows.append(
            {
                "family": fam["family"],
                "pages": fam["pages"],
                "mean_visible_recall": round(fam["recall_sum"] / fam["pages"], 6) if fam["pages"] else None,
                "token_hit_pages": fam["token_hit"],
                "returned_as_image_pages": fam["returned_as_image"],
                "expect_match_pages": fam["expect_match"],
            }
        )

    # expect x observed の突合 (crosstab) と expect 別集計。
    crosstab = {exp: {obs: 0 for obs in expect_classes} for exp in expect_classes}
    expect_agg: dict[str, dict[str, Any]] = {
        exp: {"expect": exp, "pages": 0, "recall_sum": 0.0, "returned_as_image": 0, "match": 0} for exp in expect_classes
    }
    for entry in pages:
        exp = entry["expect"]
        obs = entry["observed"]
        if exp in crosstab and obs in crosstab[exp]:
            crosstab[exp][obs] += 1
        bucket = expect_agg.setdefault(
            exp, {"expect": exp, "pages": 0, "recall_sum": 0.0, "returned_as_image": 0, "match": 0}
        )
        bucket["pages"] += 1
        bucket["recall_sum"] += entry["visible_recall"]
        bucket["returned_as_image"] += int(entry["returned_as_image"])
        bucket["match"] += int(entry["expect_match"])
    expect_rows = []
    for exp in expect_classes:
        bucket = expect_agg[exp]
        expect_rows.append(
            {
                "expect": exp,
                "pages": bucket["pages"],
                "mean_visible_recall": round(bucket["recall_sum"] / bucket["pages"], 6) if bucket["pages"] else None,
                "returned_as_image_pages": bucket["returned_as_image"],
                "expect_match_pages": bucket["match"],
            }
        )

    total = len(pages)
    recall_sum = sum(entry["visible_recall"] for entry in pages)
    summary = {
        "aggregate_visible_recall": round(recall_sum / total, 6) if total else None,
        "token_hit_pages": sum(1 for entry in pages if entry["token_hit"]),
        "returned_as_image_pages": sum(1 for entry in pages if entry["returned_as_image"]),
        "expect_match_pages": sum(1 for entry in pages if entry["expect_match"]),
    }
    return {
        "page_count": total,
        "expect_classes": expect_classes,
        "summary": summary,
        "pages": pages,
        "by_family": family_rows,
        "by_expect": expect_rows,
        "expect_vs_observed": crosstab,
        "passed": None,
        "note": (
            "Diagnostic only; no pass/fail. Measures whether ambiguous images stay searchable "
            "(token + visible-text recall in markdown) vs. get returned as images[]."
        ),
    }


def render_generated_images_report(results: dict[str, Any]) -> str:
    metric = results["metrics"]["generated_images"]
    summary = metric["summary"]
    total = metric["page_count"]
    lines = [
        "# Generated-images OCR report",
        "",
        "Codex APP 納品の曖昧画像 15 枚 (g1_*..g5_*) を 1 ページ 1 画像で OCR にかけ、画像内テキストが "
        "markdown 本文として検索可能に残るか (= token / visible_text recall) / images[] に落ちるかを測る。",
        "Diagnostic only (no pass/fail).",
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
        "## Diagnostic classification",
        "",
        f"- Observed class: text-dominant if visible recall >= {GENERATED_TEXT_RECALL_HIGH}, "
        f"image-dominant if < {GENERATED_IMAGE_RECALL_LOW}, else mixed (heuristic; not a pass threshold).",
        "",
        "## Summary",
        "",
        f"- Aggregate visible-text recall: `{summary['aggregate_visible_recall']}`",
        f"- Pages with embedded token in body: `{summary['token_hit_pages']}/{total}`",
        f"- Pages returned as images[]: `{summary['returned_as_image_pages']}/{total}`",
        f"- Pages where observed == expect: `{summary['expect_match_pages']}/{total}`",
        "",
        "## Per image",
        "",
        "| page | file | family | expect | observed | token | visible recall | images[] |",
        "| ---: | --- | --- | --- | --- | :---: | ---: | ---: |",
    ]
    for entry in metric["pages"]:
        lines.append(
            "| {page} | {file} | {family} | {expect} | {observed} | {token} | {recall} ({m}/{t}) | {images} |".format(
                page=entry["page_index"],
                file=entry["file"],
                family=entry["family"],
                expect=entry["expect"],
                observed=entry["observed"],
                token="yes" if entry["token_hit"] else "NO",
                recall=entry["visible_recall"],
                m=entry["visible_matched_count"],
                t=entry["visible_token_count"],
                images=entry["images_count"],
            )
        )

    lines.extend(
        [
            "",
            "## By family",
            "",
            "| family | pages | mean visible recall | token hit | returned as image | expect match |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in metric["by_family"]:
        lines.append(
            "| {family} | {pages} | {recall} | {token}/{pages} | {img}/{pages} | {match}/{pages} |".format(
                family=row["family"],
                pages=row["pages"],
                recall=row["mean_visible_recall"],
                token=row["token_hit_pages"],
                img=row["returned_as_image_pages"],
                match=row["expect_match_pages"],
            )
        )

    lines.extend(
        [
            "",
            "## By expect",
            "",
            "| expect | pages | mean visible recall | returned as image | observed == expect |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for row in metric["by_expect"]:
        lines.append(
            "| {expect} | {pages} | {recall} | {img}/{pages} | {match}/{pages} |".format(
                expect=row["expect"],
                pages=row["pages"],
                recall=row["mean_visible_recall"],
                img=row["returned_as_image_pages"],
                match=row["expect_match_pages"],
            )
        )

    classes = metric["expect_classes"]
    crosstab = metric["expect_vs_observed"]
    lines.extend(
        [
            "",
            "## expect vs observed (counts)",
            "",
            "行 = 納品時の expect、列 = 観測分類。対角線が一致。",
            "",
            "| expect \\ observed | " + " | ".join(classes) + " |",
            "| --- | " + " | ".join("---:" for _ in classes) + " |",
        ]
    )
    for exp in classes:
        row_cells = " | ".join(str(crosstab[exp][obs]) for obs in classes)
        lines.append(f"| {exp} | {row_cells} |")
    return "\n".join(lines) + "\n"


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
