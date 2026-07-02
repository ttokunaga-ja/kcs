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
REQUESTED_MODEL = "mistral-ocr-latest"
SYNC_PRICE_PER_1000_PAGES = 4.0
BATCH_PRICE_PER_1000_PAGES = 2.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["sync", "batch"], default="sync", help="OCR execution mode.")
    parser.add_argument("--dry-run", action="store_true", help="Use a mock Mistral-style response. No API key or network.")
    parser.add_argument("--ground-truth", type=Path, default=DEFAULT_GROUND_TRUTH)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--timeout-seconds", type=float, default=900.0)
    return parser.parse_args()


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
        "custom_id": "kcs-ocr-verification",
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
        metadata={"job_type": "kcs-ocr-verification"},
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
    return {
        "model": "mistral-ocr-4-0-dry-run",
        "pages": [
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
        ],
        "document_annotation": None,
        "usage_info": {"pages_processed": ground_truth["page_count"]},
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
