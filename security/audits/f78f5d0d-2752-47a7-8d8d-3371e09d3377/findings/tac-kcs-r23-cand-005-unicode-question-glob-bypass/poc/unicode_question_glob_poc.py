#!/usr/bin/env python3
"""Offline reproduction of KCS-R23-CAND-005 with synthetic filenames."""

from __future__ import annotations

import sys
import unicodedata


PATTERN = "?.txt"
CASES = [
    ("ascii", "a.txt"),
    ("precomposed", "\u00e9.txt"),
    ("decomposed", "e\u0301.txt"),
    ("emoji", "\U0001f600.txt"),
]


def wildcard_match_bytes(pattern: bytes, value: bytes) -> bool:
    if not pattern:
        return not value
    if pattern.startswith(b"**/"):
        if wildcard_match_bytes(pattern[3:], value):
            return True
        try:
            slash = value.index(b"/")
        except ValueError:
            return False
        return wildcard_match_bytes(pattern, value[slash + 1 :])
    if pattern == b"**":
        return True
    head = pattern[:1]
    if head == b"*":
        return wildcard_match_bytes(pattern[1:], value) or (
            bool(value)
            and value[:1] != b"/"
            and wildcard_match_bytes(pattern, value[1:])
        )
    if head == b"?":
        return bool(value) and value[:1] != b"/" and wildcard_match_bytes(
            pattern[1:], value[1:]
        )
    return bool(value) and head == value[:1] and wildcard_match_bytes(
        pattern[1:], value[1:]
    )


def vulnerable_ignored(pattern: str, value: str) -> bool:
    pattern_nfc = unicodedata.normalize("NFC", pattern)
    value_nfc = unicodedata.normalize("NFC", value)
    return wildcard_match_bytes(pattern_nfc.encode("utf-8"), value_nfc.encode("utf-8"))


def wildcard_match_scalars(pattern: tuple[str, ...], value: tuple[str, ...]) -> bool:
    if not pattern:
        return not value
    if pattern[:3] == ("*", "*", "/"):
        if wildcard_match_scalars(pattern[3:], value):
            return True
        try:
            slash = value.index("/")
        except ValueError:
            return False
        return wildcard_match_scalars(pattern, value[slash + 1 :])
    if pattern == ("*", "*"):
        return True
    head = pattern[0]
    if head == "*":
        return wildcard_match_scalars(pattern[1:], value) or (
            bool(value) and value[0] != "/" and wildcard_match_scalars(pattern, value[1:])
        )
    if head == "?":
        return bool(value) and value[0] != "/" and wildcard_match_scalars(
            pattern[1:], value[1:]
        )
    return bool(value) and head == value[0] and wildcard_match_scalars(
        pattern[1:], value[1:]
    )


def fixed_ignored(pattern: str, value: str) -> bool:
    pattern_nfc = tuple(unicodedata.normalize("NFC", pattern))
    value_nfc = tuple(unicodedata.normalize("NFC", value))
    return wildcard_match_scalars(pattern_nfc, value_nfc)


def hex_bytes(value: str) -> str:
    normalized = unicodedata.normalize("NFC", value)
    return " ".join(f"{byte:02x}" for byte in normalized.encode("utf-8"))


def yn(value: bool) -> str:
    return "yes" if value else "no "


def main() -> int:
    rows = []
    for label, name in CASES:
        rows.append(
            {
                "label": label,
                "name": name,
                "bytes": hex_bytes(name),
                "vulnerable": vulnerable_ignored(PATTERN, name),
                "fixed": fixed_ignored(PATTERN, name),
            }
        )

    print(f"pattern: {PATTERN}")
    for row in rows:
        print(
            "case={label:<12} name={name!r:<10} nfc_bytes={bytes:<28} "
            "vulnerable_ignored={vulnerable} fixed_ignored={fixed}".format(
                label=row["label"],
                name=row["name"],
                bytes=row["bytes"],
                vulnerable=yn(row["vulnerable"]),
                fixed=yn(row["fixed"]),
            )
        )

    expected_vulnerable = {
        "ascii": True,
        "precomposed": False,
        "decomposed": False,
        "emoji": False,
    }
    expected_fixed = {label: True for label, _ in CASES}

    for row in rows:
        if row["vulnerable"] != expected_vulnerable[row["label"]]:
            print(f"[-] unexpected vulnerable result for {row['label']}", file=sys.stderr)
            return 1
        if row["fixed"] != expected_fixed[row["label"]]:
            print(f"[-] unexpected scalar result for {row['label']}", file=sys.stderr)
            return 1

    print("[+] vulnerable matcher reproduces the Unicode '?' bypass")
    print("[+] scalar matcher excludes the same one-character Unicode filenames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
