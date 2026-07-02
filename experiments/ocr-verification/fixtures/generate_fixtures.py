#!/usr/bin/env python3
"""Generate synthetic OCR verification fixtures and ground truth."""

from __future__ import annotations

import json
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


def write_ground_truth(pdf_generator: str) -> None:
    data = {
        "schema_version": 1,
        "fixture_pdf": str(PDF_PATH.relative_to(ROOT)),
        "pdf_generator": pdf_generator,
        "page_count": 4,
        "pages": {
            "complex_table": 0,
            "japanese_text": 1,
            "formula": 2,
            "embedded_image": 3,
        },
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
    GROUND_TRUTH_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def try_generate_with_reportlab() -> bool:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.pdfgen import canvas
    except Exception:
        return False

    try:
        c = canvas.Canvas(str(PDF_PATH), pagesize=A4)
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
        c.save()
        return True
    except Exception:
        PDF_PATH.unlink(missing_ok=True)
        return False


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
    used_reportlab = try_generate_with_reportlab()
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
    ensure_pdf_has_enough_structure(PDF_PATH)
    write_ground_truth("reportlab" if used_reportlab else "minimal-pdf-writer")
    print(f"wrote {PDF_PATH.relative_to(ROOT)}")
    print(f"wrote {GROUND_TRUTH_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
