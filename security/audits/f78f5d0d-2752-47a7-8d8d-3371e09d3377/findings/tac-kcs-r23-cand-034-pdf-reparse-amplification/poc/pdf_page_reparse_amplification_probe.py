#!/usr/bin/env python3
"""Bounded local probe for KCS-R23-CAND-034.

The script models the source-level relationship only: lexical /Page prefixes
become logical pages, preparation creates one unit per page, and markdownization
performs one initial extraction plus one full extraction per page hint.
"""

from __future__ import annotations

import argparse
import json


MAX_MARKERS = 4096


def bounded_window(text: str, start: int, max_len: int) -> str:
    return text[start : min(len(text), start + max_len)]


def match_indices(text: str, needle: str) -> list[int]:
    out: list[int] = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index < 0:
            return out
        out.append(index)
        start = index + len(needle)


def lexical_page_count(text: str) -> int:
    type_pages = 0
    for index in match_indices(text, "/Type"):
        tail = bounded_window(text, index, 32)
        if "/Page" in tail and "/Pages" not in tail:
            type_pages += 1
    page_tokens = 0
    for index in match_indices(text, "/Page"):
        if not bounded_window(text, index, 8).startswith("/Pages"):
            page_tokens += 1
    return max(type_pages, page_tokens)


def synthetic_pdf(false_markers: int) -> bytes:
    # The base is intentionally 49 bytes so the default attack size matches the
    # validated 490-byte control relation when each false marker is " /PageX".
    base = b"%PDF\n1 0 obj\n<< /Type /Page >>\nBT (safe) Tj ET\n  "
    return base + (b" /PageX" * false_markers)


def summarize(false_markers: int) -> dict[str, int]:
    data = synthetic_pdf(false_markers)
    page_count = max(lexical_page_count(data.decode("utf-8", "replace")), 1)
    units = page_count
    return {
        "false_page_markers": false_markers,
        "input_bytes": len(data),
        "lexical_page_count": page_count,
        "prepared_units": units,
        "markdown_units": units,
        "source_trace_minimum_full_pdf_extractions": units + 1,
        "same_size_revision_lcs_cells": (units + 1) * (units + 1),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markers", type=int, default=63)
    args = parser.parse_args()
    if args.markers < 0 or args.markers > MAX_MARKERS:
        parser.error(f"--markers must be between 0 and {MAX_MARKERS}")
    print(
        json.dumps(
            {
                "attack": summarize(args.markers),
                "control": summarize(0),
                "network": False,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
