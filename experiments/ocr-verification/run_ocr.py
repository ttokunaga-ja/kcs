#!/usr/bin/env python3
"""Run Mistral OCR against the synthetic fixture or produce a dry-run response."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_GROUND_TRUTH = ROOT / "fixtures" / "generated" / "ground_truth.json"
DEFAULT_OUT_DIR = ROOT / "out"
# 生成画像 (Codex APP 納品の曖昧画像 15 枚) 用の別 fixture / 別出力先。
GENERATED_IMAGES_GROUND_TRUTH = ROOT / "fixtures" / "generated" / "generated_images_ground_truth.json"
GENERATED_IMAGES_OUT_DIR = ROOT / "out" / "generated-images"
REQUESTED_MODEL = "mistral-ocr-latest"
SYNC_PRICE_PER_1000_PAGES = 4.0
BATCH_PRICE_PER_1000_PAGES = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sync", "batch"], default="sync", help="OCR execution mode.")
    parser.add_argument("--dry-run", action="store_true", help="Use a mock Mistral-style response. No API key or network.")
    parser.add_argument(
        "--fixture",
        choices=["default", "generated-images"],
        default="default",
        help="default = 18-page synthetic fixture; generated-images = 15 delivered ambiguous images "
        "(sets --ground-truth / --out-dir defaults unless overridden).",
    )
    parser.add_argument("--ground-truth", type=Path, default=None)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    args = parser.parse_args()
    if args.fixture == "generated-images":
        if args.ground_truth is None:
            args.ground_truth = GENERATED_IMAGES_GROUND_TRUTH
        if args.out_dir is None:
            args.out_dir = GENERATED_IMAGES_OUT_DIR
    else:
        if args.ground_truth is None:
            args.ground_truth = DEFAULT_GROUND_TRUTH
        if args.out_dir is None:
            args.out_dir = DEFAULT_OUT_DIR
    return args


def load_ground_truth(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"ground truth not found: {path}. Run fixtures/generate_fixtures.py first.")
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    ground_truth = load_ground_truth(args.ground_truth)
    fixture_pdf = (ROOT / ground_truth["fixture_pdf"]).resolve()
    if not fixture_pdf.exists():
        raise SystemExit(f"fixture PDF not found: {fixture_pdf}. Run fixtures/generate_fixtures.py first.")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if args.dry_run:
        if ground_truth.get("dataset") == "generated-images":
            response = build_mock_response_generated_images(ground_truth)
        else:
            response = build_mock_response(ground_truth)
        batch_metadata: dict[str, Any] | None = None
    elif args.mode == "sync":
        response = run_sync_ocr(fixture_pdf)
        batch_metadata = None
    else:
        response, batch_metadata = run_batch_ocr(
            fixture_pdf,
            args.out_dir,
            poll_interval_seconds=args.poll_interval_seconds,
            timeout_seconds=args.timeout_seconds,
        )
    latency_seconds = time.perf_counter() - started

    resolved_model = response.get("model") or response.get("model_id") or "unknown"
    page_count = count_pages(response, ground_truth)
    estimated_cost = estimate_cost_usd(page_count, args.mode)
    raw_response_path = args.out_dir / "raw_response.json"
    run_record_path = args.out_dir / "ocr_response.json"

    write_json(raw_response_path, scrub_for_output(response))
    run_record = {
        "schema_version": 1,
        "created_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "dry_run": args.dry_run,
        "mode": args.mode,
        "requested_model": REQUESTED_MODEL,
        "resolved_model": resolved_model,
        "fixture_pdf": str(fixture_pdf.relative_to(ROOT)),
        "ground_truth": display_path(args.ground_truth.resolve()),
        "input_sha256": sha256_file(fixture_pdf),
        "latency_seconds": round(latency_seconds, 6),
        "page_count": page_count,
        "estimated_cost_usd": estimated_cost,
        "pricing": {
            "sync_usd_per_1000_pages": SYNC_PRICE_PER_1000_PAGES,
            "batch_usd_per_1000_pages": BATCH_PRICE_PER_1000_PAGES,
            "unit": "pages",
        },
        "raw_response_path": display_path(raw_response_path),
        "response": scrub_for_output(response),
    }
    if batch_metadata is not None:
        run_record["batch"] = scrub_for_output(batch_metadata)
    write_json(run_record_path, run_record)

    print(f"wrote {display_path(raw_response_path)}")
    print(f"wrote {display_path(run_record_path)}")
    print(f"mode={args.mode} dry_run={args.dry_run} pages={page_count} resolved_model={resolved_model}")
    print(f"estimated_cost_usd={estimated_cost:.6f} latency_seconds={latency_seconds:.3f}")


def run_sync_ocr(pdf_path: Path) -> dict[str, Any]:
    api_key = require_api_key()
    client = create_mistral_client(api_key)
    response = client.ocr.process(
        model=REQUESTED_MODEL,
        document=pdf_document_payload(pdf_path),
        include_image_base64=True,
        table_format=None,
    )
    return to_plain_data(response)


def run_batch_ocr(
    pdf_path: Path,
    out_dir: Path,
    *,
    poll_interval_seconds: float,
    timeout_seconds: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    api_key = require_api_key()
    client = create_mistral_client(api_key)
    batch_request = {
        "custom_id": "kio-ocr-verification",
        "body": {
            "document": pdf_document_payload(pdf_path),
            "include_image_base64": True,
            "table_format": None,
        },
    }
    batch_input_path = out_dir / "batch_input.jsonl"
    batch_input_path.write_text(json.dumps(batch_request, ensure_ascii=False) + "\n", encoding="utf-8")

    created_job = client.batch.jobs.create(
        requests=[batch_request],
        model=REQUESTED_MODEL,
        endpoint="/v1/ocr",
        metadata={"job_type": "kio-ocr-verification"},
    )
    job_data = to_plain_data(created_job)
    deadline = time.monotonic() + timeout_seconds
    status_history = [job_data]
    while normalize_status(job_data.get("status", getattr(created_job, "status", ""))) in {"QUEUED", "RUNNING"}:
        if time.monotonic() >= deadline:
            raise TimeoutError(f"batch job timed out after {timeout_seconds} seconds: {job_data.get('id')}")
        time.sleep(poll_interval_seconds)
        created_job = client.batch.jobs.get(job_id=getattr(created_job, "id", job_data.get("id")))
        job_data = to_plain_data(created_job)
        status_history.append(job_data)

    final_status = normalize_status(job_data.get("status", ""))
    if final_status not in {"SUCCESS", "SUCCEEDED", "COMPLETED"}:
        raise RuntimeError(f"batch job did not succeed: status={final_status} job={json.dumps(job_data, ensure_ascii=False)}")

    output_file_id = job_data.get("output_file") or job_data.get("output_file_id")
    if not output_file_id:
        raise RuntimeError(f"batch job completed without output file id: {json.dumps(job_data, ensure_ascii=False)}")
    batch_results_path = out_dir / "batch_results.jsonl"
    download_file(client, output_file_id, batch_results_path)
    response = parse_batch_results(batch_results_path)
    batch_metadata = {
        "input_path": display_path(batch_input_path),
        "results_path": display_path(batch_results_path),
        "job": job_data,
        "status_history": status_history,
    }
    return response, batch_metadata


def require_api_key() -> str:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        raise SystemExit("MISTRAL_API_KEY is required unless --dry-run is used.")
    return api_key


def create_mistral_client(api_key: str) -> Any:
    try:
        from mistralai.client import Mistral
    except Exception:
        try:
            from mistralai import Mistral
        except Exception as exc:
            raise SystemExit("mistralai SDK is required for non-dry-run execution. Install with `python -m pip install -e .`.") from exc
    return Mistral(api_key=api_key)


def pdf_document_payload(pdf_path: Path) -> dict[str, str]:
    encoded = base64.b64encode(pdf_path.read_bytes()).decode("ascii")
    return {
        "type": "document_url",
        "document_url": f"data:application/pdf;base64,{encoded}",
    }


def download_file(client: Any, file_id: str, output_path: Path) -> None:
    downloaded = client.files.download(file_id=file_id)
    if hasattr(downloaded, "read"):
        output_path.write_bytes(downloaded.read())
        return
    if hasattr(downloaded, "stream"):
        with output_path.open("wb") as handle:
            for chunk in downloaded.stream:
                handle.write(chunk if isinstance(chunk, bytes) else str(chunk).encode("utf-8"))
        return
    data = to_plain_data(downloaded)
    if isinstance(data, str):
        output_path.write_text(data, encoding="utf-8")
    else:
        output_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def parse_batch_results(path: Path) -> dict[str, Any]:
    lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(lines) != 1:
        raise RuntimeError(f"expected one batch result line, got {len(lines)} in {path}")
    row = json.loads(lines[0])
    if row.get("error"):
        raise RuntimeError(f"batch row failed: {json.dumps(row['error'], ensure_ascii=False)}")
    body = row.get("response", {}).get("body")
    if body is None:
        body = row.get("body")
    if body is None:
        body = row.get("output")
    if not isinstance(body, dict):
        raise RuntimeError(f"could not locate OCR response body in batch row: {json.dumps(row, ensure_ascii=False)[:1000]}")
    return body


def build_mock_response(ground_truth: dict[str, Any]) -> dict[str, Any]:
    table = markdown_table(ground_truth["table"]["expected_cell_texts"])
    japanese_text = ground_truth["japanese"]["full_text"]
    formula_tokens = ground_truth["formula"]["expected_tokens"]
    tiny_png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    pages = [
            {
                "index": 0,
                "markdown": "# 複雑表OCR評価\n\n" + table,
                "images": [],
                "tables": [],
                "hyperlinks": [],
                "dimensions": {"width": 595, "height": 842, "unit": "pt"},
                "confidence_scores": {"average_page_confidence_score": 0.99},
                "blocks": [
                    {"type": "table", "top_left_x": 54, "top_left_y": 130, "bottom_right_x": 494, "bottom_right_y": 300}
                ],
            },
            {
                "index": 1,
                "markdown": japanese_text,
                "images": [],
                "tables": [],
                "hyperlinks": [],
                "dimensions": {"width": 595, "height": 842, "unit": "pt"},
                "confidence_scores": {"average_page_confidence_score": 0.995},
                "blocks": [{"type": "text", "content": japanese_text}],
            },
            {
                "index": 2,
                "markdown": "# Formula OCR Evaluation\n\nE=mc^2\n\nint_0^1 x^2 dx = 1/3",
                "images": [],
                "tables": [],
                "hyperlinks": [],
                "dimensions": {"width": 595, "height": 842, "unit": "pt"},
                "confidence_scores": {"average_page_confidence_score": 0.98},
                "blocks": [{"type": "equation", "content": " ; ".join(formula_tokens)}],
            },
            {
                "index": 3,
                "markdown": "# 埋め込み画像OCR評価\n\n![img-0.png](img-0.png)\n\n図1: 部門別の概略推移を示す埋め込み画像",
                "images": [
                    {
                        "id": "img-0.png",
                        "top_left_x": 160,
                        "top_left_y": 180,
                        "bottom_right_x": 420,
                        "bottom_right_y": 330,
                        "image_base64": tiny_png_base64,
                    }
                ],
                "tables": [],
                "hyperlinks": [],
                "dimensions": {"width": 595, "height": 842, "unit": "pt"},
                "confidence_scores": {"average_page_confidence_score": 0.99},
                "blocks": [{"type": "image", "image_id": "img-0.png"}],
            },
        ]
    if ground_truth.get("figures"):
        pages.extend(build_mock_figure_pages(ground_truth, tiny_png_base64))
    if ground_truth.get("rasterized_text"):
        pages.extend(build_mock_rasterized_pages(ground_truth))
    if ground_truth.get("handwriting"):
        pages.extend(build_mock_handwriting_pages(ground_truth))
    if ground_truth.get("staged_boundary"):
        pages.extend(build_mock_staged_pages(ground_truth, tiny_png_base64))
    return {
        "model": "mistral-ocr-4-0-dry-run",
        "pages": pages,
        "document_annotation": None,
        "usage_info": {"pages_processed": ground_truth["page_count"]},
    }


def build_mock_response_generated_images(ground_truth: dict[str, Any]) -> dict[str, Any]:
    """生成画像 fixture 用の合成応答。実 OCR 挙動の主張ではなく、evaluate.py の
    generated-images 評価を dry-run で最後まで走らせるための illustrative なモック。

    expect 別に「本文化の度合い」と images[] を作り分ける:
      - text-dominant : token あり / visible_text 全 segment を本文化 / images[] 無し (高 recall)
      - mixed         : token あり / visible_text の約 6 割を本文化 / images[] 1 (中 recall)
      - image-dominant: token 無し / visible_text の約 15% のみ / images[] 1 (低 recall, 画像落ち想定)
    """
    import math

    tiny_png_base64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
    )
    plan = {
        "text-dominant": (1.0, False, True),
        "mixed": (0.6, True, True),
        "image-dominant": (0.15, True, False),
    }
    pages: list[dict[str, Any]] = []
    for entry in ground_truth["pages"]:
        frac, with_image, include_token = plan.get(entry.get("expect"), (0.6, True, True))
        segments = [seg.strip() for seg in entry.get("visible_text", "").split(";") if seg.strip()]
        keep = max(1, math.ceil(len(segments) * frac)) if segments else 0
        body_parts: list[str] = [f"# {entry['family']} {entry['file']}"]
        if include_token:
            body_parts.extend(entry.get("tokens", []))
        body_parts.extend(segments[:keep])
        images: list[dict[str, Any]] = []
        if with_image:
            image_id = f"img-{entry['page_index']}.png"
            body_parts.append(f"![{image_id}]({image_id})")
            images.append(
                {
                    "id": image_id,
                    "top_left_x": 40,
                    "top_left_y": 60,
                    "bottom_right_x": 560,
                    "bottom_right_y": 720,
                    "image_base64": tiny_png_base64,
                }
            )
        pages.append(
            {
                "index": entry["page_index"],
                "markdown": "\n\n".join(body_parts),
                "images": images,
                "tables": [],
                "hyperlinks": [],
                "dimensions": {"width": 612, "height": 792, "unit": "pt"},
                "confidence_scores": {"average_page_confidence_score": 0.9},
                "blocks": [{"type": "image", "image_id": img["id"]} for img in images] or [{"type": "text"}],
            }
        )
    return {
        "model": "mistral-ocr-4-0-dry-run",
        "pages": pages,
        "document_annotation": None,
        "usage_info": {"pages_processed": ground_truth["page_count"]},
    }


def build_mock_figure_pages(ground_truth: dict[str, Any], tiny_png_base64: str) -> list[dict[str, Any]]:
    """WS-ocr-figures 診断ページの合成応答。

    実 OCR 挙動の主張ではなく、evaluate.py の figures 判定を dry-run で通すための
    illustrative なモック。3 段階 (欠落 / 完全 / 部分) を意図的に作り分けている:
      - raster_chart : placeholder + image のみ、画像内テキストは本文に無し (最悪ケース, recall 0)
      - scan_page    : raster を OCR して本文化、image 無し (最良ケース, recall 1.0)
      - infographic  : placeholder + image + 一部ラベルのみ (部分欠落, recall < 1.0)
    """
    dims = {"width": 595, "height": 842, "unit": "pt"}
    specs = {page["kind"]: page for page in ground_truth["figures"]["pages"]}
    result: list[dict[str, Any]] = []

    chart = specs["raster_chart"]
    result.append(
        {
            "index": chart["page_index"],
            "markdown": "# ラスタ図表OCR評価\n\n![img-1.png](img-1.png)\n\n図2: ラスタ画像として埋め込んだ棒グラフ",
            "images": [
                {
                    "id": "img-1.png",
                    "top_left_x": 54,
                    "top_left_y": 90,
                    "bottom_right_x": 541,
                    "bottom_right_y": 382,
                    "image_base64": tiny_png_base64,
                }
            ],
            "tables": [],
            "hyperlinks": [],
            "dimensions": dims,
            "confidence_scores": {"average_page_confidence_score": 0.83},
            "blocks": [{"type": "image", "image_id": "img-1.png"}],
        }
    )

    scan = specs["scan_page"]
    scan_body = (
        "Kio SCAN FIXTURE PAGE FIVE\n\n"
        "This entire page is rendered as a single raster image, a simulated scan of text-native content.\n\n"
        "Anchor tokens for retrieval checks: ALPHA-7731 BRAVO-2048 CHARLIE-9152\n\n"
        "If the page is returned only as an image with a placeholder, every token is lost to search."
    )
    result.append(
        {
            "index": scan["page_index"],
            "markdown": "# スキャン風ページOCR評価\n\n" + scan_body,
            "images": [],
            "tables": [],
            "hyperlinks": [],
            "dimensions": dims,
            "confidence_scores": {"average_page_confidence_score": 0.9},
            "blocks": [{"type": "text", "content": scan_body}],
        }
    )

    info = specs["infographic"]
    result.append(
        {
            "index": info["page_index"],
            "markdown": (
                "# インフォグラフィックOCR評価\n\n![img-2.png](img-2.png)\n\n"
                "Kio PIPELINE OVERVIEW\n\nIngest Markdownize Embed"
            ),
            "images": [
                {
                    "id": "img-2.png",
                    "top_left_x": 54,
                    "top_left_y": 90,
                    "bottom_right_x": 541,
                    "bottom_right_y": 363,
                    "image_base64": tiny_png_base64,
                }
            ],
            "tables": [],
            "hyperlinks": [],
            "dimensions": dims,
            "confidence_scores": {"average_page_confidence_score": 0.85},
            "blocks": [{"type": "image", "image_id": "img-2.png"}],
        }
    )
    return result


def build_mock_rasterized_pages(ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """系統A の合成応答。実挙動の主張ではなく evaluate.py の rasterized_text 判定を dry-run で通す用。

    3 ページを作り分ける: raster_table=一部セル欠落 (recall<1), raster_japanese=完全, raster_formula=完全。
    いずれも full-page raster が OCR で本文化された想定なので images[] は付けない。
    """
    dims = {"width": 595, "height": 842, "unit": "pt"}
    specs = {spec["kind"]: spec for spec in ground_truth["rasterized_text"]["pages"]}
    result: list[dict[str, Any]] = []

    table = specs["raster_table"]
    # 数値セル 2 つ (1,020 / 2,450) を意図的に欠落させ recall < 1 を作る。
    table_md = (
        "# 複雑表OCR評価 (raster)\n\n"
        "| 地域 | 売上(千円) |  | 備考 |\n"
        "| --- | --- | --- | --- |\n"
        "|  | 2025 Q4 | 2026 Q1 |  |\n"
        "| 東京 | 1,250 | 1,430 | 前年比+14% |\n"
        "| 大阪 | 980 |  | 新規案件2件 |\n"
        "| 合計 | 2,230 |  | 粗利率31.5% |"
    )
    result.append(_mock_text_page(table["page_index"], table_md, dims, confidence=0.9))

    japanese = specs["raster_japanese"]
    result.append(_mock_text_page(japanese["page_index"], japanese["full_text"], dims, confidence=0.95))

    formula = specs["raster_formula"]
    formula_md = "# Formula OCR Evaluation (raster)\n\nE=mc^2\n\nint_0^1 x^2 dx = 1/3"
    result.append(_mock_text_page(formula["page_index"], formula_md, dims, confidence=0.92))
    return result


def build_mock_handwriting_pages(ground_truth: dict[str, Any]) -> list[dict[str, Any]]:
    """系統B の合成応答。手書きは一部トークンを落とす想定 (recall < 1) の illustrative なモック。"""
    dims = {"width": 595, "height": 842, "unit": "pt"}
    result: list[dict[str, Any]] = []
    for spec in ground_truth["handwriting"]["pages"]:
        included = spec["expected_texts"][:5]  # 先頭 5 トークンだけ拾えた想定
        markdown = f"# {spec['kind']}\n\n" + " ".join(included)
        result.append(_mock_text_page(spec["page_index"], markdown, dims, confidence=0.78))
    return result


# 系統C dry-run 用の段階別 (body, table, figure, images) 取り込み数。
# 実挙動の主張ではなく、C2->C3 に明確な急落 (境界) を作って evaluate.py の境界判定を確認する。
MOCK_C_PLAN = {
    "C0": (4, 0, 0, 0),
    "C1": (3, 3, 0, 0),
    "C2": (3, 5, 0, 0),
    "C3": (3, 0, 1, 1),
    "C4": (3, 1, 1, 2),
    "C5": (1, 0, 1, 1),
}


def build_mock_staged_pages(ground_truth: dict[str, Any], tiny_png_base64: str) -> list[dict[str, Any]]:
    """系統C の合成応答。段階が進むほど figure/table トークンを落とし images[] を増やす。"""
    dims = {"width": 595, "height": 842, "unit": "pt"}
    result: list[dict[str, Any]] = []
    for spec in ground_truth["staged_boundary"]["stages"]:
        nb, nt, nf, ni = MOCK_C_PLAN[spec["stage"]]
        tokens = spec["tokens"]
        included = tokens["body"][:nb] + tokens["table"][:nt] + tokens["figure"][:nf]
        parts = [f"# {spec['stage']} raster stage ({spec['kind']})", ""]
        parts.extend(included)
        images: list[dict[str, Any]] = []
        for index in range(ni):
            image_id = f"img-{spec['stage'].lower()}-{index}.png"
            parts.append(f"![{image_id}]({image_id})")
            images.append(
                {
                    "id": image_id,
                    "top_left_x": 90,
                    "top_left_y": 200 + index * 120,
                    "bottom_right_x": 520,
                    "bottom_right_y": 320 + index * 120,
                    "image_base64": tiny_png_base64,
                }
            )
        page = _mock_text_page(spec["page_index"], "\n\n".join(parts), dims, confidence=0.86)
        page["images"] = images
        page["blocks"] = [{"type": "image", "image_id": img["id"]} for img in images] or [{"type": "text"}]
        result.append(page)
    return result


def _mock_text_page(index: int, markdown: str, dims: dict[str, Any], *, confidence: float) -> dict[str, Any]:
    return {
        "index": index,
        "markdown": markdown,
        "images": [],
        "tables": [],
        "hyperlinks": [],
        "dimensions": dims,
        "confidence_scores": {"average_page_confidence_score": confidence},
        "blocks": [{"type": "text", "content": markdown}],
    }


def markdown_table(cell_texts: list[str]) -> str:
    lookup = {text: text for text in cell_texts}
    return "\n".join(
        [
            "| 地域 | 売上(千円) | 売上(千円) | 備考 |",
            "| --- | ---: | ---: | --- |",
            f"| {lookup['地域']} | 2025 Q4 | 2026 Q1 | {lookup['備考']} |",
            f"| {lookup['東京']} | {lookup['1,250']} | {lookup['1,430']} | {lookup['前年比+14%']} |",
            f"| {lookup['大阪']} | {lookup['980']} | {lookup['1,020']} | {lookup['新規案件2件']} |",
            f"| {lookup['合計']} | {lookup['2,230']} | {lookup['2,450']} | {lookup['粗利率31.5%']} |",
        ]
    )


def count_pages(response: dict[str, Any], ground_truth: dict[str, Any]) -> int:
    pages = response.get("pages")
    if isinstance(pages, list):
        return len(pages)
    usage = response.get("usage_info", {})
    for key in ("pages_processed", "num_pages", "page_count"):
        value = usage.get(key)
        if isinstance(value, int):
            return value
    return int(ground_truth["page_count"])


def estimate_cost_usd(page_count: int, mode: str) -> float:
    price = BATCH_PRICE_PER_1000_PAGES if mode == "batch" else SYNC_PRICE_PER_1000_PAGES
    return round((page_count / 1000.0) * price, 6)


def normalize_status(value: Any) -> str:
    text = str(value).upper()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path)


def sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def to_plain_data(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): to_plain_data(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_plain_data(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_plain_data(value.model_dump(mode="json"))
    if hasattr(value, "dict"):
        return to_plain_data(value.dict())
    if hasattr(value, "__dict__"):
        return {
            key: to_plain_data(item)
            for key, item in vars(value).items()
            if not key.startswith("_") and callable(item) is False
        }
    return str(value)


def scrub_for_output(value: Any) -> Any:
    secret_keys = ("api_key", "apikey", "authorization", "auth", "token", "secret")
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if any(secret in key.lower() for secret in secret_keys):
                result[key] = "[REDACTED]"
            else:
                result[key] = scrub_for_output(item)
        return result
    if isinstance(value, list):
        return [scrub_for_output(item) for item in value]
    return value


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
