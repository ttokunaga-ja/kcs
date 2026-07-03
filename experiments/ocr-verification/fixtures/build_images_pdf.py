#!/usr/bin/env python3
"""Build a deterministic 1-image-per-page PDF from the delivered ambiguous images.

Codex APP delivered 15 ambiguous images (fixtures/generated-images/g1_*.png .. g5_*.png)
plus a source ground-truth.json (file / family / tokens / visible_text / expect). This
script wraps those PNGs into a single PDF (fixtures/generated/generated_images.pdf),
one image per page, so the real-API OCR harness (run_ocr.py / evaluate.py) can score them.

Determinism:
  - page order is the source filenames sorted ascending (stable page_index <-> PNG mapping);
  - reportlab Canvas(invariant=True) freezes CreationDate / doc ID;
  - only the delivered PNG bytes are embedded (no random, no timestamps),
    so two builds are byte-identical.

It also emits a harness-compatible ground truth (generated_images_ground_truth.json,
schema_version 1) mapping page index <-> source PNG <-> family <-> tokens <-> visible_text
<-> expect. The evaluate.py generated-images section reads that file.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "fixtures" / "generated-images"
SOURCE_GROUND_TRUTH = SOURCE_DIR / "ground-truth.json"
GENERATED_DIR = ROOT / "fixtures" / "generated"
PDF_PATH = GENERATED_DIR / "generated_images.pdf"
GROUND_TRUTH_PATH = GENERATED_DIR / "generated_images_ground_truth.json"

# 全ページ共通の固定ページ幅 (pt)。高さは各画像のアスペクト比から決定論的に算出する。
# US Letter 幅 612pt。~1600px 幅の画像で実効 ~190DPI となり OCR に十分。
PAGE_WIDTH_PT = 612.0
SCHEMA_VERSION = 1


def load_source_entries() -> list[dict[str, Any]]:
    if not SOURCE_GROUND_TRUTH.exists():
        raise SystemExit(f"source ground truth not found: {SOURCE_GROUND_TRUTH}")
    data = json.loads(SOURCE_GROUND_TRUTH.read_text(encoding="utf-8"))
    if not isinstance(data, list) or not data:
        raise SystemExit(f"source ground truth must be a non-empty JSON array: {SOURCE_GROUND_TRUTH}")
    required = {"file", "family", "tokens", "visible_text", "expect"}
    for entry in data:
        missing = required - set(entry)
        if missing:
            raise SystemExit(f"source entry missing keys {sorted(missing)}: {entry.get('file')}")
        png = SOURCE_DIR / entry["file"]
        if not png.exists():
            raise SystemExit(f"source image not found: {png}")
    # ページ順 = ファイル名昇順 (page_index <-> PNG を安定させる)。
    return sorted(data, key=lambda entry: entry["file"])


def build() -> list[dict[str, Any]]:
    try:
        from PIL import Image
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover - dependency guard
        raise SystemExit(
            "reportlab と Pillow が必要です。`python -m pip install -e .` (または uv sync) で依存を入れてください。"
        ) from exc

    entries = load_source_entries()
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)

    # invariant=True で CreationDate / doc ID を固定し、PDF をバイト決定論にする
    # (build の 2 回 byte 一致 = ローカル検証の前提)。
    c = canvas.Canvas(str(PDF_PATH), invariant=True)
    pages: list[dict[str, Any]] = []
    for index, entry in enumerate(entries):
        png_path = SOURCE_DIR / entry["file"]
        with Image.open(png_path) as image:
            px_w, px_h = image.size
        page_w = PAGE_WIDTH_PT
        page_h = round(PAGE_WIDTH_PT * px_h / px_w, 3)
        c.setPageSize((page_w, page_h))
        # PNG をページ全面 (0,0)-(page_w,page_h) に配置。mask=None (レンダリング画像は透過なし)。
        c.drawImage(ImageReader(str(png_path)), 0, 0, width=page_w, height=page_h, mask=None)
        c.showPage()
        pages.append(
            {
                "page_index": index,
                "file": entry["file"],
                "family": entry["family"],
                "tokens": list(entry["tokens"]),
                "visible_text": entry["visible_text"],
                "expect": entry["expect"],
                "image_px": [px_w, px_h],
                "page_pt": [page_w, page_h],
            }
        )
    c.save()
    return pages


def write_ground_truth(pages: list[dict[str, Any]]) -> None:
    families = sorted({page["family"] for page in pages})
    data = {
        "schema_version": SCHEMA_VERSION,
        "dataset": "generated-images",
        "fixture_pdf": str(PDF_PATH.relative_to(ROOT)),
        "generator": "build_images_pdf.py",
        "source_ground_truth": str(SOURCE_GROUND_TRUTH.relative_to(ROOT)),
        "page_count": len(pages),
        "families": families,
        "description": (
            "Codex APP 納品の曖昧画像 15 枚 (g1_*..g5_*) を 1 ページ 1 画像で束ねた PDF の "
            "ハーネス互換 ground truth。ページ順はファイル名昇順。各ページは family / tokens / "
            "visible_text / expect (text-dominant | mixed | image-dominant) を持つ。"
        ),
        "acceptance": (
            "Diagnostic only (no hard pass threshold). Per page measures: (i) 埋め込みトークンが "
            "markdown 本文に出たか, (ii) visible_text の正規化トークン回収率, (iii) images[] として返ったか。"
            "family 別集計と expect との突合を out/generated-images/report.md に出力。"
        ),
        "pages": pages,
    }
    GROUND_TRUTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    pages = build()
    write_ground_truth(pages)
    print(f"wrote {PDF_PATH.relative_to(ROOT)} ({len(pages)} pages, 1 image/page)")
    print(f"wrote {GROUND_TRUTH_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
