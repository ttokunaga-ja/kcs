#!/usr/bin/env python3
"""Synthetic model of KCS deterministic PDF pathname reopens.

The vulnerable source path hashes one byte buffer, then later deterministic PDF
normalization reopens the same pathname for aggregate and per-page extraction.
This probe keeps the environment local and disposable while showing the state
transition that matters: markdown derived from later bytes remains labelled by
the earlier raw hash.
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def make_pdf(label: str) -> bytes:
    # The reviewed deterministic extractor accepts simple literal strings inside
    # streams. This is intentionally tiny and synthetic, not a complete PDF.
    text = (
        "%PDF-1.4\n"
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        "3 0 obj << /Type /Page /Parent 2 0 R /Contents 4 0 R >> endobj\n"
        "4 0 obj << /Length 64 >>\n"
        "stream\n"
        f"BT ({label}) Tj ET\n"
        "endstream\n"
        "endobj\n"
        "%%EOF\n"
    )
    return text.encode("utf-8")


def extract_pdf_text_pages(data: bytes) -> list[str]:
    # Small stand-in for the reviewed deterministic PDF stream/literal path.
    text = data.decode("utf-8", errors="replace")
    pages: list[str] = []
    for stream in re.findall(r"stream\r?\n(.*?)\r?\nendstream", text, flags=re.S):
        strings = re.findall(r"\((.*?)\)", stream, flags=re.S)
        if strings:
            pages.append("\n".join(strings))
    if not pages:
        strings = re.findall(r"\((.*?)\)", text, flags=re.S)
        pages = strings or [text]
    return pages


def read_source_text(path: Path) -> str:
    # Mirrors the first deterministic adapter reopen at read_source_text().
    return "\n\n".join(extract_pdf_text_pages(path.read_bytes()))


def read_pdf_page_text(path: Path, page_index: int) -> str:
    # Mirrors the per-page deterministic adapter reopen at read_pdf_page_text().
    pages = extract_pdf_text_pages(path.read_bytes())
    return pages[page_index]


def atomic_replace(path: Path, data: bytes) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main() -> int:
    version_a = make_pdf("VERSION_A_APPROVED_AT_HASH_CHECK")
    version_b = make_pdf("VERSION_B_AFTER_HASH_BEFORE_SOURCE_READ")
    version_c = make_pdf("VERSION_C_BEFORE_PER_PAGE_READ")

    with tempfile.TemporaryDirectory(prefix="kcs-pdf-reopen-poc-") as tmpdir:
        pdf_path = Path(tmpdir) / "report.pdf"
        pdf_path.write_bytes(version_a)

        checked_bytes = pdf_path.read_bytes()
        raw_hash = sha256_hex(checked_bytes)
        print(f"[+] checked read observed A: {extract_pdf_text_pages(checked_bytes)[0]}")
        print(f"[+] checked raw hash H(A): {raw_hash}")

        atomic_replace(pdf_path, version_b)
        current_hash = sha256_hex(pdf_path.read_bytes())
        source_text = read_source_text(pdf_path)
        print(f"[+] aggregate reopen observed: {source_text}")
        print(f"[+] current hash after source reopen H(B): {current_hash}")

        atomic_replace(pdf_path, version_c)
        page_text = read_pdf_page_text(pdf_path, 0)
        page_hash = sha256_hex(pdf_path.read_bytes())
        print(f"[+] per-page reopen observed: {page_text}")
        print(f"[+] current hash before persistence H(C): {page_hash}")

        persisted_unit = {
            "raw_hash": raw_hash,
            "unit_key": "page:1",
            "markdown": page_text + "\n",
        }

        print(f"[+] persisted unit raw_hash: {persisted_unit['raw_hash']}")
        print(f"[+] persisted unit markdown: {persisted_unit['markdown'].strip()}")

        if persisted_unit["raw_hash"] == raw_hash and "VERSION_C" in persisted_unit["markdown"]:
            print("[+] misbinding reproduced in the synthetic control-flow model")
            return 0

        print("[-] model did not reach the expected misbinding")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
