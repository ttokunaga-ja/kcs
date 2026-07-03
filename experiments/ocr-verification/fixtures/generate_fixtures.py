#!/usr/bin/env python3
"""Generate synthetic OCR verification fixtures and ground truth."""

from __future__ import annotations

import json
import random
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "fixtures" / "generated"
PDF_PATH = GENERATED_DIR / "kcs_ocr_verification.pdf"
GROUND_TRUTH_PATH = GENERATED_DIR / "ground_truth.json"

PAGE_WIDTH = 595.0
PAGE_HEIGHT = 842.0


TABLE_CELLS = [
    {"row": 0, "col": 0, "rowspan": 2, "colspan": 1, "text": "地域"},
    {"row": 0, "col": 1, "rowspan": 1, "colspan": 2, "text": "売上(千円)"},
    {"row": 0, "col": 3, "rowspan": 2, "colspan": 1, "text": "備考"},
    {"row": 1, "col": 1, "rowspan": 1, "colspan": 1, "text": "2025 Q4"},
    {"row": 1, "col": 2, "rowspan": 1, "colspan": 1, "text": "2026 Q1"},
    {"row": 2, "col": 0, "rowspan": 1, "colspan": 1, "text": "東京"},
    {"row": 2, "col": 1, "rowspan": 1, "colspan": 1, "text": "1,250"},
    {"row": 2, "col": 2, "rowspan": 1, "colspan": 1, "text": "1,430"},
    {"row": 2, "col": 3, "rowspan": 1, "colspan": 1, "text": "前年比+14%"},
    {"row": 3, "col": 0, "rowspan": 1, "colspan": 1, "text": "大阪"},
    {"row": 3, "col": 1, "rowspan": 1, "colspan": 1, "text": "980"},
    {"row": 3, "col": 2, "rowspan": 1, "colspan": 1, "text": "1,020"},
    {"row": 3, "col": 3, "rowspan": 1, "colspan": 1, "text": "新規案件2件"},
    {"row": 4, "col": 0, "rowspan": 1, "colspan": 1, "text": "合計"},
    {"row": 4, "col": 1, "rowspan": 1, "colspan": 1, "text": "2,230"},
    {"row": 4, "col": 2, "rowspan": 1, "colspan": 1, "text": "2,450"},
    {"row": 4, "col": 3, "rowspan": 1, "colspan": 1, "text": "粗利率31.5%"},
]

JAPANESE_TEXT = (
    "横書き日本語OCR評価\n"
    "KCSは、個人の作業フォルダを内容アドレスで保存し、検索結果から原本へ戻れるようにする。\n"
    "このページは句読点、数字12345、英字KCS、括弧(確認)を含む横書き本文である。\n"
    "誤字率を測るため、改行を含めた全文をground truthとして保持する。"
)

FORMULA_TOKENS = ["E=mc^2", "int_0^1 x^2 dx = 1/3"]

# ---------------------------------------------------------------------------
# WS-ocr-figures: raster 図表を「画像内テキスト」として埋め込んだ診断ページ。
# ラベルはすべて ASCII (PIL 同梱の default TrueType のみに依存し、CJK フォント
# 不在でも決定論的・可搬に生成できる)。Mistral OCR がラスタ内テキストを
# markdown 本文へ OCR するか、それとも images[] + placeholder として画像化して
# 検索対象から落とすかを測るための既知ラベル集合。
# ---------------------------------------------------------------------------
FIGURE_CHART_LABELS = [
    "REVENUE BY DEPT 2026Q1",
    "Tokyo",
    "Osaka",
    "Nagoya",
    "1250",
    "980",
    "760",
    "Total 2990",
]
FIGURE_SCAN_LABELS = [
    "KCS SCAN FIXTURE PAGE",
    "ALPHA-7731",
    "BRAVO-2048",
    "CHARLIE-9152",
    "returned only as an image",
]
FIGURE_INFOGRAPHIC_LABELS = [
    "KCS PIPELINE OVERVIEW",
    "Ingest",
    "Markdownize",
    "Embed",
    "Index",
    "Search",
    "42 percent uplift",
]
FIGURE_SCAN_LINES = [
    "KCS SCAN FIXTURE PAGE FIVE",
    "",
    "This entire page is rendered as a single raster image, a",
    "simulated scan of text-native content.",
    "",
    "Anchor tokens for retrieval checks:",
    "  ALPHA-7731   BRAVO-2048   CHARLIE-9152",
    "",
    "If OCR reads this raster, these tokens appear in the markdown",
    "body and stay searchable (FTS / embedding).",
    "",
    "If the page is returned only as an image with a placeholder,",
    "every token is lost to search (north-star M3-1 impact).",
]

# ---------------------------------------------------------------------------
# 系統 A/B/C 拡張 (ユーザー要求): ラスタ化 PDF / 手書き風 / 画像化境界の段階調査。
# いずれも「全面 raster + text layer なし」の PDF ページ (PIL でレンダリングした
# PNG を reportlab に drawImage で全面配置し、テキストを一切描かない)。よって
# メタデータからテキストは抽出できず、OCR が rendered image を読むかどうかを直接
# 測れる。CJK グリフ描画のため PIL に CJK TrueType/TTC が必要 (無ければ A/B/C は
# skip し ground_truth からも省く)。全ページ 200DPI 相当 (A4 = 1654x2339px)。
# 決定論: フォント固定 + seed 固定 Random のみ使用 (グローバル random 非使用)。
# ---------------------------------------------------------------------------
RASTER_PAGE_PX = (1654, 2339)  # A4 @ ~200 DPI

# CJK 対応 TrueType/TTC の候補 (macOS / Linux Noto 等)。最初に存在するものを使う。
CJK_FONT_CANDIDATES = [
    "/System/Library/Fonts/ヒラギノ角ゴシック W4.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Regular.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/Library/Fonts/Arial Unicode.ttf",
]

# 系統 A — メタデータからテキストが取得できない PDF (text-native ページのラスタ化版)。
# ground truth は既存 fixture 0-2 の内容を流用。
RASTER_A_SPECS = [
    {
        "page_index": 7,
        "kind": "raster_table",
        "source_page_index": 0,
        "expected_cell_texts": [cell["text"] for cell in TABLE_CELLS],
        "risk": "Rasterized complex table; no text layer. OCR must re-read cell text from the image.",
    },
    {
        "page_index": 8,
        "kind": "raster_japanese",
        "source_page_index": 1,
        "full_text": JAPANESE_TEXT,
        "risk": "Rasterized Japanese body; no text layer. Metadata text extraction impossible.",
    },
    {
        "page_index": 9,
        "kind": "raster_formula",
        "source_page_index": 2,
        "expected_tokens": FORMULA_TOKENS,
        "risk": "Rasterized ASCII formula; no text layer.",
    },
]

# 系統 B — 手書き風ページ。フォント依存を避け、PIL で文字ごとに回転/ベースライン
# ゆらぎ/字間ゆらぎ/線幅ゆらぎを加えて手書きを模す (seed 固定で決定論)。
HANDWRITING_SPECS = [
    {
        "page_index": 10,
        "kind": "handwriting_shopping",
        "seed": 20260703,
        "lines": [
            "買い物リスト",
            "牛乳 2本",
            "卵 10個",
            "食パン 1斤",
            "コーヒー豆 200g",
            "合計 1580円",
        ],
        "expected_texts": ["買い物リスト", "牛乳", "卵", "食パン", "コーヒー豆", "200g", "10個", "1580円"],
    },
    {
        "page_index": 11,
        "kind": "handwriting_memo",
        "seed": 20260704,
        "lines": [
            "会議メモ 6月30日",
            "出席 田中 佐藤 鈴木",
            "TODO API設計 レビュー",
            "次回 7月7日 14時",
            "予算 案A 3200円",
        ],
        "expected_texts": ["会議メモ", "田中", "佐藤", "鈴木", "API設計", "7月7日", "3200円"],
    },
]

# 系統 C — 画像化境界の段階調査 (最重要)。ラスタ化テキストページに段階的に表・グラフを
# 足す C0..C5。図/表/本文それぞれに一意トークン (例: C3-FIG-AXIS-61) を埋め、evaluate.py が
# 「どのトークンが markdown 本文に出たか / images[] に消えたか」を段階別に判定できるようにする。
# 各トークン文字列はここが単一の真実源: 描画関数もこのリストをそのまま描くので GT と描画が乖離しない。
STAGE_C_SPECS = [
    {
        "page_index": 12,
        "stage": "C0",
        "kind": "raster_text",
        "chart_kind": None,
        "body": ["C0-BODY-01", "C0-BODY-02", "C0-BODY-03", "本文ゼロC0"],
        "table": [],
        "figure": [],
    },
    {
        "page_index": 13,
        "stage": "C1",
        "kind": "text_small_table",
        "chart_kind": None,
        "body": ["C1-BODY-11", "C1-BODY-12", "本文C1"],
        "table": ["C1-TBL-21", "C1-TBL-22", "C1-TBL-23"],
        "figure": [],
    },
    {
        "page_index": 14,
        "stage": "C2",
        "kind": "text_large_table",
        "chart_kind": None,
        "body": ["C2-BODY-31", "C2-BODY-32", "本文C2"],
        "table": ["C2-TBL-41", "C2-TBL-42", "C2-TBL-43", "C2-TBL-44", "C2-TBL-45", "合計C2"],
        "figure": [],
    },
    {
        "page_index": 15,
        "stage": "C3",
        "kind": "text_line_chart",
        "chart_kind": "line",
        "body": ["C3-BODY-51", "C3-BODY-52", "本文C3"],
        "table": [],
        "figure": ["C3-FIG-AXIS-61", "C3-FIG-AXIS-62", "C3-FIG-LEG-63", "C3-FIG-VAL-64", "凡例C3"],
    },
    {
        "page_index": 16,
        "stage": "C4",
        "kind": "dashboard",
        "chart_kind": "bar",
        "body": ["C4-BODY-71", "C4-BODY-72", "本文C4"],
        "table": ["C4-TBL-81", "C4-TBL-82", "C4-TBL-83", "C4-TBL-84"],
        "figure": ["C4-FIG-AXIS-91", "C4-FIG-LEG-92", "C4-FIG-VAL-93", "C4-FIG-VAL-94", "棒C4"],
    },
    {
        "page_index": 17,
        "stage": "C5",
        "kind": "chart_dominant",
        "chart_kind": "bar",
        "body": ["C5-BODY-01", "本文C5"],
        "table": [],
        "figure": ["C5-FIG-AXIS-11", "C5-FIG-AXIS-12", "C5-FIG-LEG-13", "C5-FIG-VAL-14", "C5-FIG-VAL-15", "図C5"],
    },
]


def write_ground_truth(pdf_generator: str, include_figures: bool, include_raster: bool = False) -> None:
    page_map = {
        "complex_table": 0,
        "japanese_text": 1,
        "formula": 2,
        "embedded_image": 3,
    }
    data = {
        "schema_version": 3,
        "fixture_pdf": str(PDF_PATH.relative_to(ROOT)),
        "pdf_generator": pdf_generator,
        "page_count": 4,
        "pages": page_map,
        "table": {
            "page_index": 0,
            "cells": TABLE_CELLS,
            "expected_cell_texts": [cell["text"] for cell in TABLE_CELLS],
            "description": "Merged header cells, numeric columns, grid lines.",
        },
        "japanese": {
            "page_index": 1,
            "full_text": JAPANESE_TEXT,
            "orientation": "horizontal",
        },
        "formula": {
            "page_index": 2,
            "expected_tokens": FORMULA_TOKENS,
            "acceptance": "Record whether OCR textizes the formula or falls back to an image; no pass threshold.",
        },
        "images": {
            "page_index": 3,
            "expected_count": 1,
            "description": "One embedded RGB image XObject representing a simple chart.",
        },
    }
    if include_figures:
        page_map.update({"raster_chart": 4, "scan_page": 5, "infographic": 6})
        data["page_count"] = 7
        data["figures"] = {
            "description": (
                "WS-ocr-figures 診断ページ。text-native ではなく raster として埋め込んだ図表・"
                "スキャン風ページ・インフォグラフィックで、画像内テキストが image 化されて "
                "markdown 本文から欠落する (= FTS/embedding の検索対象外になる) 懸念を測る。"
            ),
            "acceptance": (
                "Diagnostic only, no hard pass threshold (human review). 記録する観点: "
                "(a) images[] 数と markdown placeholder 数の対応, "
                "(b) 画像内既知ラベルが markdown 本文に現れる割合 (label recall), "
                "(c) ページ横断の本文テキスト欠落率 (1 - aggregate label recall)。"
            ),
            "pages": [
                {
                    "page_index": 4,
                    "kind": "raster_chart",
                    "expected_label_texts": FIGURE_CHART_LABELS,
                    "risk": "Chart exported as a raster PNG; axis / legend / value text may stay locked inside the image.",
                },
                {
                    "page_index": 5,
                    "kind": "scan_page",
                    "expected_label_texts": FIGURE_SCAN_LABELS,
                    "risk": "Whole page is one raster (simulated scan); body text may be returned as an image, not markdown.",
                },
                {
                    "page_index": 6,
                    "kind": "infographic",
                    "expected_label_texts": FIGURE_INFOGRAPHIC_LABELS,
                    "risk": "Complex infographic layout; text callouts inside shapes may be dropped or image-ized.",
                },
            ],
        }
    if include_raster:
        page_map.update(
            {
                "raster_table": 7,
                "raster_japanese": 8,
                "raster_formula": 9,
                "handwriting_shopping": 10,
                "handwriting_memo": 11,
                "stage_c0": 12,
                "stage_c1": 13,
                "stage_c2": 14,
                "stage_c3": 15,
                "stage_c4": 16,
                "stage_c5": 17,
            }
        )
        data["page_count"] = 18
        data["rasterized_text"] = {
            "description": (
                "系統A: text-native ページを PIL でラスタ画像にし、その画像だけを埋め込んだ PDF ページ "
                "(text layer なし)。メタデータからテキストは抽出できない。OCR が rendered image から "
                "元テキスト (表/日本語/数式) を回収できるかを測る。ground truth は元テキストを流用。"
            ),
            "acceptance": (
                "Diagnostic only (no hard threshold). Reuses source text; per page measures "
                "cell recall / Japanese CER / formula token recall from a full-page raster."
            ),
            "pages": [dict(spec) for spec in RASTER_A_SPECS],
        }
        data["handwriting"] = {
            "description": (
                "系統B: フォント依存を避け、PIL で文字ごとに回転 (±6°)・ベースライン上下ゆらぎ・"
                "字間ゆらぎ・線の太さゆらぎを加えた手書き風レンダリング (seed 固定で決定論)。"
                "日本語+英数字の短いメモ (買い物リスト / 会議メモ)。"
            ),
            "acceptance": "Diagnostic only; measures OCR token recall on simulated handwriting. No threshold.",
            "pages": [
                {
                    "page_index": spec["page_index"],
                    "kind": spec["kind"],
                    "expected_texts": spec["expected_texts"],
                }
                for spec in HANDWRITING_SPECS
            ],
        }
        data["staged_boundary"] = {
            "description": (
                "系統C (最重要): ラスタ化テキストページに段階的に表・グラフを足す C0..C5。"
                "図/表/本文それぞれに一意トークン (例: C3-FIG-AXIS-61) を埋め、どのトークンが "
                "markdown 本文に出たか / images[] に消えたかを段階別に測り、recall が急落する『境界』を機械判定する。"
            ),
            "acceptance": (
                "Boundary study (diagnostic). Per stage: zone (body/table/figure) token recall + images[] "
                "count; evaluate.py detects the stage where recall collapses and writes boundary-report.md."
            ),
            "stages": [
                {
                    "stage": spec["stage"],
                    "page_index": spec["page_index"],
                    "kind": spec["kind"],
                    "tokens": {
                        "body": spec["body"],
                        "table": spec["table"],
                        "figure": spec["figure"],
                    },
                }
                for spec in STAGE_C_SPECS
            ],
        }
    GROUND_TRUTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def try_generate_with_reportlab() -> tuple[bool, bool]:
    """(used_reportlab, raster_cjk_included) を返す。

    raster_cjk_included は「系統 A/B/C (全面 raster + CJK) を PDF に含めたか」。
    reportlab があっても CJK フォントが見つからなければ A/B/C は skip し (False)、
    既存 0-6 のみ生成する。
    """
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except Exception:
        return False, False

    try:
        # invariant=True で CreationDate / doc ID を固定し、PDF をバイト決定論にする
        # (raster 図表の再現性検証 = fixture 生成の決定論性ローカル検証の前提)。
        c = canvas.Canvas(str(PDF_PATH), pagesize=A4, invariant=True)
        width, height = A4
        # CID フォントが無いと日本語グリフが描画されず、OCR 品質評価の fixture として無効になる。
        # Helvetica への silent fallback は行わない (登録失敗 = reportlab 経路の失敗として扱う)。
        pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
        jp_font = "HeiseiKakuGo-W5"

        c.setFont(jp_font, 18)
        c.drawString(54, height - 60, "複雑表OCR評価")
        draw_reportlab_table(c, jp_font, height)
        c.showPage()

        c.setFont(jp_font, 18)
        c.drawString(54, height - 60, "横書き日本語OCR評価")
        c.setFont(jp_font, 12)
        y = height - 96
        for line in JAPANESE_TEXT.splitlines()[1:]:
            c.drawString(54, y, line)
            y -= 28
        c.showPage()

        c.setFont("Helvetica", 18)
        c.drawString(54, height - 60, "Formula OCR Evaluation")
        c.setFont("Helvetica", 20)
        c.drawString(90, height - 150, "E = mc^2")
        c.drawString(90, height - 205, "int_0^1 x^2 dx = 1/3")
        c.setFont("Helvetica", 11)
        c.drawString(
            90,
            height - 250,
            "Record whether the equation is extracted as text or represented as an image fallback.",
        )
        c.showPage()

        c.setFont(jp_font, 18)
        c.drawString(54, height - 60, "埋め込み画像OCR評価")
        image = ImageReader(_ppm_image_bytes())
        c.drawImage(image, 160, height - 330, width=260, height=150, mask="auto")
        c.setFont(jp_font, 11)
        c.drawString(160, height - 350, "図1: 部門別の概略推移を示す埋め込み画像")
        c.showPage()

        draw_figure_pages(c, jp_font, width, height)

        # 系統 A/B/C: 全面 raster + text layer なし。CJK フォントが見つかった時のみ。
        cjk_path = _find_cjk_font()
        raster_cjk = cjk_path is not None
        if raster_cjk:
            draw_rasterized_text_pages(c, cjk_path, width, height)
            draw_handwriting_pages(c, cjk_path, width, height)
            draw_staged_boundary_pages(c, cjk_path, width, height)

        c.save()
        return True, raster_cjk
    except Exception:
        PDF_PATH.unlink(missing_ok=True)
        return False, False


def draw_figure_pages(c, jp_font: str, width: float, height: float) -> None:
    """WS-ocr-figures: 画像内テキストを持つ raster 図表ページ (index 4-6) を描く。"""
    from io import BytesIO

    from reportlab.lib.utils import ImageReader

    def place(png_bytes: bytes, heading: str, caption: str | None) -> None:
        reader = ImageReader(BytesIO(png_bytes))
        px_w, px_h = reader.getSize()
        draw_w = 487.0
        draw_h = draw_w * px_h / px_w
        c.setFont(jp_font, 18)
        c.drawString(54, height - 60, heading)
        # レンダリング画像なので mask/透過は無効化 (mask=None)。
        c.drawImage(reader, 54, height - 90 - draw_h, width=draw_w, height=draw_h, mask=None)
        if caption:
            c.setFont(jp_font, 11)
            c.drawString(54, height - 110 - draw_h, caption)
        c.showPage()

    place(
        render_bar_chart_png(),
        "ラスタ図表OCR評価",
        "図2: ラスタ画像として埋め込んだ棒グラフ。軸・凡例・数値ラベルは画像内テキスト。",
    )
    place(
        render_scan_page_png(),
        "スキャン風ページOCR評価",
        None,
    )
    place(
        render_infographic_png(),
        "インフォグラフィックOCR評価",
        "図3: パイプライン概要のインフォグラフィック。ボックス内テキストは画像内テキスト。",
    )


def _figure_font(size: int):
    from PIL import ImageFont

    try:
        return ImageFont.load_default(size=size)
    except TypeError:  # 古い Pillow は size 引数非対応 (bitmap 固定)
        return ImageFont.load_default()


def render_bar_chart_png() -> bytes:
    """棒グラフ raster (画像内テキスト = タイトル/カテゴリ/数値ラベル)。決定論。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width, height = 1000, 600
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, width - 3, height - 3], outline=(0, 0, 0), width=2)
    draw.text((40, 24), "REVENUE BY DEPT 2026Q1", fill=(0, 0, 0), font=_figure_font(40))

    baseline = 500
    bars = [("Tokyo", 1250), ("Osaka", 980), ("Nagoya", 760)]
    colors = [(40, 90, 170), (200, 110, 40), (60, 150, 90)]
    for index, (label, value) in enumerate(bars):
        bar_h = int(value / 1400 * 360)
        x0 = 120 + index * 280
        x1 = x0 + 170
        top = baseline - bar_h
        draw.rectangle([x0, top, x1, baseline], fill=colors[index])
        draw.text((x0 + 20, baseline + 12), label, fill=(0, 0, 0), font=_figure_font(34))
        draw.text((x0 + 30, top - 44), str(value), fill=(0, 0, 0), font=_figure_font(32))
    draw.text((40, height - 60), "Total 2990 kJPY", fill=(0, 0, 0), font=_figure_font(30))

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def render_scan_page_png() -> bytes:
    """ページ全体を 1 枚の raster にした scan 風テキスト。決定論。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width, height = 1000, 1320
    img = Image.new("RGB", (width, height), (247, 246, 242))
    draw = ImageDraw.Draw(img)
    draw.rectangle([6, 6, width - 7, height - 7], outline=(150, 150, 150), width=2)
    y = 70
    for line in FIGURE_SCAN_LINES:
        size = 46 if line == FIGURE_SCAN_LINES[0] else 34
        if line:
            draw.text((70, y), line, fill=(15, 15, 15), font=_figure_font(size))
        y += 62 if size == 46 else 52
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def render_infographic_png() -> bytes:
    """パイプライン概要のインフォグラフィック raster (ボックス内テキスト)。決定論。"""
    from io import BytesIO

    from PIL import Image, ImageDraw

    width, height = 1000, 560
    img = Image.new("RGB", (width, height), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.rectangle([2, 2, width - 3, height - 3], outline=(0, 0, 0), width=2)
    draw.text((40, 26), "KCS PIPELINE OVERVIEW", fill=(0, 0, 0), font=_figure_font(40))

    stages = ["Ingest", "Markdownize", "Embed", "Index", "Search"]
    box_w, box_h = 150, 90
    y0 = 200
    for index, stage in enumerate(stages):
        x0 = 40 + index * 190
        x1 = x0 + box_w
        draw.rectangle([x0, y0, x1, y0 + box_h], outline=(0, 0, 0), width=3, fill=(230, 238, 250))
        draw.text((x0 + 12, y0 + 32), stage, fill=(0, 0, 0), font=_figure_font(26))
        if index < len(stages) - 1:
            draw.line([x1, y0 + box_h // 2, x1 + 40, y0 + box_h // 2], fill=(0, 0, 0), width=3)
    draw.text((40, 380), "42 percent uplift", fill=(160, 40, 40), font=_figure_font(34))
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


# ===========================================================================
# 系統 A/B/C: 全面 raster ページの PIL レンダリング + reportlab への全面埋め込み。
# ===========================================================================


def _find_cjk_font() -> str | None:
    for candidate in CJK_FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _cjk_font(path: str, size: int):
    from PIL import ImageFont

    return ImageFont.truetype(path, size)


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    """max_width(px) に収まるよう折り返す。CJK は文字単位、空白入りは語単位で分割。"""
    if not text:
        return [""]

    def width_of(segment: str) -> int:
        box = draw.textbbox((0, 0), segment, font=font)
        return box[2] - box[0]

    lines: list[str] = []
    current = ""
    for char in text:
        candidate = current + char
        if width_of(candidate) > max_width and current:
            lines.append(current)
            current = char
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _new_page_image():
    from PIL import Image, ImageDraw

    width, height = RASTER_PAGE_PX
    img = Image.new("RGB", (width, height), (255, 255, 255))
    return img, ImageDraw.Draw(img), width, height


def _png_bytes(img) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return buffer.getvalue()


def render_raster_table_png(cjk_path: str) -> bytes:
    """系統A: 複雑表を全面 raster 化 (text layer なし)。全 expected_cell_texts を描く。決定論。"""
    img, draw, width, _height = _new_page_image()
    title_font = _cjk_font(cjk_path, 60)
    cell_font = _cjk_font(cjk_path, 40)
    draw.text((70, 60), "複雑表OCR評価 (raster / no text layer)", fill=(0, 0, 0), font=title_font)

    grid = [
        ["地域", "売上(千円)", "", "備考"],
        ["", "2025 Q4", "2026 Q1", ""],
        ["東京", "1,250", "1,430", "前年比+14%"],
        ["大阪", "980", "1,020", "新規案件2件"],
        ["合計", "2,230", "2,450", "粗利率31.5%"],
    ]
    x0 = 80
    y0 = 240
    col_w = [360, 300, 300, 500]
    row_h = 130
    x_edges = [x0]
    for cw in col_w:
        x_edges.append(x_edges[-1] + cw)
    for r in range(len(grid) + 1):
        y = y0 + r * row_h
        draw.line([x0, y, x_edges[-1], y], fill=(0, 0, 0), width=3)
    for x in x_edges:
        draw.line([x, y0, x, y0 + len(grid) * row_h], fill=(0, 0, 0), width=3)
    for r, row in enumerate(grid):
        for cindex, cell in enumerate(row):
            if cell:
                draw.text((x_edges[cindex] + 20, y0 + r * row_h + 40), cell, fill=(15, 15, 15), font=cell_font)
    return _png_bytes(img)


def render_raster_japanese_png(cjk_path: str) -> bytes:
    """系統A: 横書き日本語本文を全面 raster 化 (text layer なし)。決定論。"""
    img, draw, width, _height = _new_page_image()
    title_font = _cjk_font(cjk_path, 60)
    body_font = _cjk_font(cjk_path, 44)
    lines = JAPANESE_TEXT.splitlines()
    draw.text((70, 60), lines[0], fill=(0, 0, 0), font=title_font)
    y = 220
    max_width = width - 160
    for line in lines[1:]:
        for wrapped in _wrap_text(draw, line, body_font, max_width):
            draw.text((80, y), wrapped, fill=(15, 15, 15), font=body_font)
            y += 66
        y += 20
    return _png_bytes(img)


def render_raster_formula_png(cjk_path: str) -> bytes:
    """系統A: ASCII 数式を全面 raster 化 (text layer なし)。決定論。"""
    img, draw, _width, _height = _new_page_image()
    title_font = _cjk_font(cjk_path, 60)
    formula_font = _cjk_font(cjk_path, 56)
    note_font = _cjk_font(cjk_path, 36)
    draw.text((70, 60), "Formula OCR Evaluation (raster / no text layer)", fill=(0, 0, 0), font=title_font)
    draw.text((110, 300), "E = mc^2", fill=(0, 0, 0), font=formula_font)
    draw.text((110, 440), "int_0^1 x^2 dx = 1/3", fill=(0, 0, 0), font=formula_font)
    draw.text(
        (110, 600),
        "Record whether the equation is extracted as text or represented as an image fallback.",
        fill=(60, 60, 60),
        font=note_font,
    )
    return _png_bytes(img)


def _glyph_advance(font, char: str) -> float:
    box = font.getbbox(char)
    return max(box[2] - box[0], 40) + 8


def render_handwriting_png(cjk_path: str, lines: list[str], seed: int) -> bytes:
    """系統B: 手書き風。文字ごとに回転/ベースライン/字間/線幅をゆらす。seed 固定で決定論。"""
    from PIL import Image, ImageDraw

    width, height = RASTER_PAGE_PX
    img = Image.new("RGB", (width, height), (252, 251, 247))
    draw = ImageDraw.Draw(img)
    draw.rectangle([10, 10, width - 11, height - 11], outline=(205, 200, 185), width=2)
    rng = random.Random(seed)
    base_font = _cjk_font(cjk_path, 72)
    y = 150
    for line in lines:
        x = 120.0
        for char in line:
            if char == " ":
                x += 44
                continue
            tile = Image.new("RGBA", (150, 150), (0, 0, 0, 0))
            tile_draw = ImageDraw.Draw(tile)
            stroke_width = rng.choice([0, 0, 1, 2])  # 線の太さゆらぎ
            ink = (20, 20, 60, 255)
            tile_draw.text((32, 22), char, font=base_font, fill=ink, stroke_width=stroke_width, stroke_fill=ink)
            angle = rng.uniform(-6.0, 6.0)  # 文字ごとの回転
            rotated = tile.rotate(angle, resample=Image.BICUBIC, expand=True)
            y_jitter = rng.uniform(-9.0, 9.0)  # ベースラインの上下ゆらぎ
            img.paste(rotated, (int(x), int(y + y_jitter)), rotated)
            x += _glyph_advance(base_font, char) + rng.uniform(-4.0, 6.0)  # 字間ゆらぎ
        y += 152
    return _png_bytes(img)


def _draw_grid_table(draw, x: int, y: int, tokens: list[str], font) -> int:
    """table トークンを 3 列グリッドのセルとして描く。新しい y を返す。"""
    headers = ["ITEM", "VALUE", "NOTE"]
    cols = 3
    col_w = 460
    row_h = 96
    rows = [tokens[i : i + cols] for i in range(0, len(tokens), cols)]
    cy = y
    for c in range(cols):
        draw.rectangle([x + c * col_w, cy, x + (c + 1) * col_w, cy + row_h], outline=(0, 0, 0), width=2, fill=(235, 235, 235))
        draw.text((x + c * col_w + 18, cy + 26), headers[c], fill=(0, 0, 0), font=font)
    cy += row_h
    for row in rows:
        for c, value in enumerate(row):
            draw.rectangle([x + c * col_w, cy, x + (c + 1) * col_w, cy + row_h], outline=(0, 0, 0), width=2)
            draw.text((x + c * col_w + 18, cy + 26), value, fill=(15, 15, 15), font=font)
        cy += row_h
    return cy


def _draw_line_chart(draw, x: int, y: int, w: int, h: int, tokens: list[str], font) -> int:
    """折れ線グラフを描き、figure トークンを軸/凡例/値ラベルとして図内に配置。新しい y を返す。"""
    draw.rectangle([x, y, x + w, y + h], outline=(0, 0, 0), width=2)
    ax_x = x + 90
    ax_y_bottom = y + h - 70
    draw.line([ax_x, y + 30, ax_x, ax_y_bottom], fill=(0, 0, 0), width=3)
    draw.line([ax_x, ax_y_bottom, x + w - 40, ax_y_bottom], fill=(0, 0, 0), width=3)
    points = [
        (ax_x + 60, ax_y_bottom - 120),
        (ax_x + 260, ax_y_bottom - 240),
        (ax_x + 460, ax_y_bottom - 170),
        (ax_x + 700, ax_y_bottom - 300),
    ]
    draw.line(points, fill=(40, 90, 170), width=4)
    for px, py in points:
        draw.ellipse([px - 7, py - 7, px + 7, py + 7], fill=(40, 90, 170))
    slots = [
        (ax_x + 40, ax_y_bottom + 16),   # AXIS
        (ax_x + 420, ax_y_bottom + 16),  # AXIS
        (x + w - 360, y + 30),           # LEG
        (ax_x + 240, ax_y_bottom - 300), # VAL
        (x + w - 360, y + 80),           # 凡例 (JP)
    ]
    for token, slot in zip(tokens, slots):
        draw.text(slot, token, fill=(0, 0, 0), font=font)
    return y + h + 24


def _draw_bar_chart(draw, x: int, y: int, w: int, h: int, tokens: list[str], font) -> int:
    """棒グラフを描き、figure トークンを軸/凡例/値ラベルとして図内に配置。新しい y を返す。"""
    draw.rectangle([x, y, x + w, y + h], outline=(0, 0, 0), width=2)
    ax_x = x + 90
    ax_y_bottom = y + h - 70
    draw.line([ax_x, y + 30, ax_x, ax_y_bottom], fill=(0, 0, 0), width=3)
    draw.line([ax_x, ax_y_bottom, x + w - 40, ax_y_bottom], fill=(0, 0, 0), width=3)
    bar_colors = [(40, 90, 170), (200, 110, 40), (60, 150, 90), (150, 60, 150)]
    heights = [220, 320, 160, 280]
    for index, bar_h in enumerate(heights):
        bx0 = ax_x + 40 + index * 200
        bx1 = bx0 + 120
        draw.rectangle([bx0, ax_y_bottom - bar_h, bx1, ax_y_bottom], fill=bar_colors[index % len(bar_colors)])
    slots = [
        (ax_x + 40, ax_y_bottom + 16),
        (ax_x + 440, ax_y_bottom + 16),
        (x + w - 360, y + 30),
        (ax_x + 40, y + 40),
        (ax_x + 440, y + 40),
        (x + w - 360, y + 80),
    ]
    for token, slot in zip(tokens, slots):
        draw.text(slot, token, fill=(0, 0, 0), font=font)
    return y + h + 24


def render_stage_page_png(cjk_path: str, spec: dict) -> bytes:
    """系統C: 段階ページ (本文 + 任意の表 + 任意のグラフ) を全面 raster 化。決定論。

    body/table/figure の各トークンをそのまま描画するので、GT (STAGE_C_SPECS) と描画が乖離しない。
    """
    img, draw, width, _height = _new_page_image()
    title_font = _cjk_font(cjk_path, 58)
    label_font = _cjk_font(cjk_path, 40)
    body_font = _cjk_font(cjk_path, 46)
    draw.rectangle([10, 10, width - 11, RASTER_PAGE_PX[1] - 11], outline=(180, 180, 180), width=2)
    draw.text((70, 60), f"{spec['stage']} raster stage ({spec['kind']})", fill=(0, 0, 0), font=title_font)
    y = 200

    draw.text((70, y), "本文テキスト (body):", fill=(0, 0, 0), font=label_font)
    y += 66
    for token in spec["body"]:
        draw.text((100, y), token, fill=(15, 15, 15), font=body_font)
        y += 70
    y += 40

    if spec["table"]:
        draw.text((70, y), "表 (table):", fill=(0, 0, 0), font=label_font)
        y += 66
        y = _draw_grid_table(draw, 100, y, spec["table"], body_font)
        y += 50

    if spec["figure"]:
        draw.text((70, y), "図 (figure):", fill=(0, 0, 0), font=label_font)
        y += 66
        chart_w = width - 200
        chart_h = 460
        if spec["chart_kind"] == "line":
            y = _draw_line_chart(draw, 100, y, chart_w, chart_h, spec["figure"], label_font)
        else:
            y = _draw_bar_chart(draw, 100, y, chart_w, chart_h, spec["figure"], label_font)
    return _png_bytes(img)


def _place_fullpage(c, png_bytes: bytes, width: float, height: float) -> None:
    """PNG をページ全面 (0,0)-(width,height) に配置し、テキストは一切描かない (text layer なし)。"""
    from io import BytesIO

    from reportlab.lib.utils import ImageReader

    reader = ImageReader(BytesIO(png_bytes))
    c.drawImage(reader, 0, 0, width=width, height=height, mask=None)
    c.showPage()


def draw_rasterized_text_pages(c, cjk_path: str, width: float, height: float) -> None:
    """系統A (index 7-9): text-native ページのラスタ化版 (表/日本語/数式)。"""
    _place_fullpage(c, render_raster_table_png(cjk_path), width, height)
    _place_fullpage(c, render_raster_japanese_png(cjk_path), width, height)
    _place_fullpage(c, render_raster_formula_png(cjk_path), width, height)


def draw_handwriting_pages(c, cjk_path: str, width: float, height: float) -> None:
    """系統B (index 10-11): 手書き風メモ。"""
    for spec in HANDWRITING_SPECS:
        _place_fullpage(c, render_handwriting_png(cjk_path, spec["lines"], spec["seed"]), width, height)


def draw_staged_boundary_pages(c, cjk_path: str, width: float, height: float) -> None:
    """系統C (index 12-17): 画像化境界の段階調査 C0..C5。"""
    for spec in STAGE_C_SPECS:
        _place_fullpage(c, render_stage_page_png(cjk_path, spec), width, height)


def draw_reportlab_table(c, jp_font: str, height: float) -> None:
    from reportlab.lib import colors

    x0 = 54
    y0 = height - 130
    col_widths = [90, 100, 100, 150]
    row_heights = [34, 34, 34, 34, 34]
    x_edges = [x0]
    for width in col_widths:
        x_edges.append(x_edges[-1] + width)
    y_edges = [y0]
    for row_height in row_heights:
        y_edges.append(y_edges[-1] - row_height)

    c.setStrokeColor(colors.black)
    c.setLineWidth(1)
    for index, x in enumerate(x_edges):
        if index == 2:
            c.line(x, y_edges[1], x, y_edges[-1])
        else:
            c.line(x, y_edges[0], x, y_edges[-1])
    for index, y in enumerate(y_edges):
        if index == 1:
            c.line(x_edges[1], y, x_edges[3], y)
        else:
            c.line(x_edges[0], y, x_edges[-1], y)
    c.line(x_edges[1], y_edges[1], x_edges[3], y_edges[1])
    c.setLineWidth(2)
    c.line(x_edges[1], y_edges[0], x_edges[1], y_edges[-1])
    c.line(x_edges[3], y_edges[0], x_edges[3], y_edges[-1])

    c.setFont(jp_font, 10)
    positions = {
        "地域": (x_edges[0] + 28, (y_edges[0] + y_edges[2]) / 2 - 4),
        "売上(千円)": (x_edges[1] + 58, y_edges[0] - 22),
        "備考": (x_edges[3] + 58, (y_edges[0] + y_edges[2]) / 2 - 4),
        "2025 Q4": (x_edges[1] + 30, y_edges[1] - 22),
        "2026 Q1": (x_edges[2] + 30, y_edges[1] - 22),
    }
    for label, pos in positions.items():
        c.drawString(*pos, label)

    rows = [
        ["東京", "1,250", "1,430", "前年比+14%"],
        ["大阪", "980", "1,020", "新規案件2件"],
        ["合計", "2,230", "2,450", "粗利率31.5%"],
    ]
    for row_index, row in enumerate(rows, start=2):
        for col_index, text in enumerate(row):
            c.drawString(x_edges[col_index] + 12, y_edges[row_index] - 22, text)


def _ppm_image_bytes():
    from io import BytesIO

    width, height = 32, 20
    out = BytesIO()
    out.write(f"P6\n{width} {height}\n255\n".encode("ascii"))
    for y in range(height):
        for x in range(width):
            red = int(30 + 170 * x / (width - 1))
            green = int(70 + 130 * y / (height - 1))
            blue = 190 if 6 < x < 25 and 5 < y < 15 else 80
            out.write(bytes([red, green, blue]))
    out.seek(0)
    return out


@dataclass
class PdfObject:
    data: bytes


class MinimalPdf:
    def __init__(self) -> None:
        self.objects: list[PdfObject] = []

    def add(self, data: bytes) -> int:
        self.objects.append(PdfObject(data))
        return len(self.objects)

    def ref(self, object_id: int) -> str:
        return f"{object_id} 0 R"

    def stream(self, dictionary: str, payload: bytes) -> bytes:
        return (
            f"<< {dictionary} /Length {len(payload)} >>\nstream\n".encode("ascii")
            + payload
            + b"\nendstream"
        )

    def write(self, path: Path, root_id: int) -> None:
        chunks = [b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"]
        offsets: list[int] = []
        cursor = len(chunks[0])
        for index, obj in enumerate(self.objects, start=1):
            offsets.append(cursor)
            chunk = f"{index} 0 obj\n".encode("ascii") + obj.data + b"\nendobj\n"
            chunks.append(chunk)
            cursor += len(chunk)
        xref_offset = cursor
        xref = [f"xref\n0 {len(self.objects) + 1}\n0000000000 65535 f \n".encode("ascii")]
        for offset in offsets:
            xref.append(f"{offset:010d} 00000 n \n".encode("ascii"))
        trailer = (
            b"".join(xref)
            + f"trailer\n<< /Size {len(self.objects) + 1} /Root {root_id} 0 R >>\n".encode("ascii")
            + f"startxref\n{xref_offset}\n%%EOF\n".encode("ascii")
        )
        chunks.append(trailer)
        path.write_bytes(b"".join(chunks))


def generate_minimal_pdf() -> None:
    pdf = MinimalPdf()
    catalog_id = pdf.add(b"")
    pages_id = pdf.add(b"")
    font_ascii_id = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
    font_jp_descriptor_id = pdf.add(
        b"<< /Type /FontDescriptor /FontName /HeiseiKakuGo-W5 /Flags 4 "
        b"/FontBBox [0 -200 1000 900] /ItalicAngle 0 /Ascent 880 /Descent -120 "
        b"/CapHeight 700 /StemV 80 >>"
    )
    font_jp_cid_id = pdf.add(
        f"<< /Type /Font /Subtype /CIDFontType0 /BaseFont /HeiseiKakuGo-W5 "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Japan1) /Supplement 5 >> "
        f"/FontDescriptor {pdf.ref(font_jp_descriptor_id)} >>".encode("ascii")
    )
    font_jp_id = pdf.add(
        f"<< /Type /Font /Subtype /Type0 /BaseFont /HeiseiKakuGo-W5 "
        f"/Encoding /UniJIS-UCS2-H /DescendantFonts [{pdf.ref(font_jp_cid_id)}] >>".encode("ascii")
    )
    image_id = pdf.add(make_image_xobject(pdf))

    page_ids: list[int] = []
    page_ids.append(add_page(pdf, pages_id, font_ascii_id, font_jp_id, page1_content(), None))
    page_ids.append(add_page(pdf, pages_id, font_ascii_id, font_jp_id, page2_content(), None))
    page_ids.append(add_page(pdf, pages_id, font_ascii_id, font_jp_id, page3_content(), None))
    page_ids.append(add_page(pdf, pages_id, font_ascii_id, font_jp_id, page4_content(), image_id))

    pdf.objects[catalog_id - 1] = PdfObject(f"<< /Type /Catalog /Pages {pdf.ref(pages_id)} >>".encode("ascii"))
    kids = " ".join(pdf.ref(page_id) for page_id in page_ids)
    pdf.objects[pages_id - 1] = PdfObject(f"<< /Type /Pages /Kids [{kids}] /Count {len(page_ids)} >>".encode("ascii"))
    pdf.write(PDF_PATH, catalog_id)


def add_page(
    pdf: MinimalPdf,
    pages_id: int,
    font_ascii_id: int,
    font_jp_id: int,
    content: bytes,
    image_id: int | None,
) -> int:
    content_id = pdf.add(pdf.stream("", content))
    xobject = f"/XObject << /Im1 {pdf.ref(image_id)} >>" if image_id is not None else ""
    resources = f"<< /Font << /F1 {pdf.ref(font_ascii_id)} /FJ {pdf.ref(font_jp_id)} >> {xobject} >>"
    page = (
        f"<< /Type /Page /Parent {pdf.ref(pages_id)} /MediaBox [0 0 {PAGE_WIDTH:.0f} {PAGE_HEIGHT:.0f}] "
        f"/Resources {resources} /Contents {pdf.ref(content_id)} >>"
    )
    return pdf.add(page.encode("ascii"))


def make_image_xobject(pdf: MinimalPdf) -> bytes:
    width, height = 32, 20
    payload = bytearray()
    for y in range(height):
        for x in range(width):
            red = int(30 + 170 * x / (width - 1))
            green = int(70 + 130 * y / (height - 1))
            blue = 190 if 6 < x < 25 and 5 < y < 15 else 80
            payload.extend([red, green, blue])
    return pdf.stream(
        f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
        "/ColorSpace /DeviceRGB /BitsPerComponent 8",
        bytes(payload),
    )


def page1_content() -> bytes:
    cmds = [
        jp_text("複雑表OCR評価", 54, 782, 18),
        "0 0 0 RG 1 w",
    ]
    x_edges = [54, 144, 244, 344, 494]
    y_edges = [712, 678, 644, 610, 576, 542]
    for index, x in enumerate(x_edges):
        if index == 2:
            cmds.append(f"{x} {y_edges[-1]} m {x} {y_edges[1]} l S")
        else:
            cmds.append(f"{x} {y_edges[-1]} m {x} {y_edges[0]} l S")
    for index, y in enumerate(y_edges):
        if index == 1:
            cmds.append(f"{x_edges[1]} {y} m {x_edges[3]} {y} l S")
        else:
            cmds.append(f"{x_edges[0]} {y} m {x_edges[-1]} {y} l S")
    cmds.extend(
        [
            jp_text("地域", 82, 672, 10),
            jp_text("売上(千円)", 202, 690, 10),
            jp_text("備考", 402, 672, 10),
            ascii_text("2025 Q4", 174, 656, 10),
            ascii_text("2026 Q1", 274, 656, 10),
            jp_text("東京", 66, 622, 10),
            ascii_text("1,250", 174, 622, 10),
            ascii_text("1,430", 274, 622, 10),
            jp_text("前年比+14%", 356, 622, 10),
            jp_text("大阪", 66, 588, 10),
            ascii_text("980", 174, 588, 10),
            ascii_text("1,020", 274, 588, 10),
            jp_text("新規案件2件", 356, 588, 10),
            jp_text("合計", 66, 554, 10),
            ascii_text("2,230", 174, 554, 10),
            ascii_text("2,450", 274, 554, 10),
            jp_text("粗利率31.5%", 356, 554, 10),
        ]
    )
    return "\n".join(cmds).encode("ascii")


def page2_content() -> bytes:
    lines = [
        jp_text("横書き日本語OCR評価", 54, 782, 18),
        jp_text("KCSは、個人の作業フォルダを内容アドレスで保存し、検索結果から原本へ戻れるようにする。", 54, 742, 11),
        jp_text("このページは句読点、数字12345、英字KCS、括弧(確認)を含む横書き本文である。", 54, 710, 11),
        jp_text("誤字率を測るため、改行を含めた全文をground truthとして保持する。", 54, 678, 11),
    ]
    return "\n".join(lines).encode("ascii")


def page3_content() -> bytes:
    lines = [
        ascii_text("Formula OCR Evaluation", 54, 782, 18),
        ascii_text("E = mc^2", 90, 700, 20),
        ascii_text("int_0^1 x^2 dx = 1/3", 90, 645, 20),
        ascii_text("Record whether the equation is extracted as text or represented as an image fallback.", 90, 600, 11),
    ]
    return "\n".join(lines).encode("ascii")


def page4_content() -> bytes:
    lines = [
        jp_text("埋め込み画像OCR評価", 54, 782, 18),
        "q 260 0 0 150 160 512 cm /Im1 Do Q",
        jp_text("図1: 部門別の概略推移を示す埋め込み画像", 160, 492, 11),
    ]
    return "\n".join(lines).encode("ascii")


def ascii_text(text: str, x: float, y: float, size: float) -> str:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return f"BT /F1 {size:g} Tf {x:g} {y:g} Td ({escaped}) Tj ET"


def jp_text(text: str, x: float, y: float, size: float) -> str:
    return f"BT /FJ {size:g} Tf {x:g} {y:g} Td <{text.encode('utf-16-be').hex()}> Tj ET"


def ensure_pdf_has_enough_structure(path: Path) -> None:
    data = path.read_bytes()
    required_markers: Iterable[bytes] = [b"/Type /Page", b"/Subtype /Image", b"/UniJIS-UCS2-H"]
    missing = [marker.decode("ascii", "ignore") for marker in required_markers if marker not in data]
    if missing:
        raise RuntimeError(f"generated PDF is missing expected markers: {', '.join(missing)}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Generate OCR verification fixtures")
    parser.add_argument(
        "--allow-fallback",
        action="store_true",
        help="reportlab 不在時に minimal PDF writer での生成を許可する (dry-run 専用。"
        "日本語グリフが描画されないため OCR 品質評価には使用不可)",
    )
    args = parser.parse_args()

    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    used_reportlab, raster_cjk = try_generate_with_reportlab()
    if not used_reportlab:
        if not args.allow_fallback:
            raise SystemExit(
                "error: reportlab (CID フォント) が必要です。minimal PDF writer の fixture は"
                "日本語グリフを描画できず、OCR 品質評価として無効です。\n"
                "実検証の前に `pip install -e .` (または uv sync) で依存を入れてください。\n"
                "dry-run のパイプライン確認だけなら --allow-fallback を付けてください。"
            )
        print(
            "warning: minimal PDF writer で生成しました。日本語グリフは描画されないため、"
            "この fixture を実 OCR 検証に使わないでください (dry-run 専用)。",
            file=sys.stderr,
        )
        generate_minimal_pdf()
    if used_reportlab and not raster_cjk:
        print(
            "warning: CJK フォントが見つからないため系統 A/B/C (ラスタ化/手書き風/境界調査) を "
            "skip しました。既存 0-6 のみ生成。系統 A/B/C を含めるには CJK TrueType/TTC を"
            "利用可能にしてください。",
            file=sys.stderr,
        )
    ensure_pdf_has_enough_structure(PDF_PATH)
    # 図表診断ページ (index 4-6) と系統 A/B/C (index 7-17) は reportlab 経路でのみ生成する。
    # minimal writer は raster 画像内テキストを描けず懸念を再現できないため。
    write_ground_truth(
        "reportlab" if used_reportlab else "minimal-pdf-writer",
        include_figures=used_reportlab,
        include_raster=raster_cjk,
    )
    print(f"wrote {PDF_PATH.relative_to(ROOT)}")
    print(f"wrote {GROUND_TRUTH_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
