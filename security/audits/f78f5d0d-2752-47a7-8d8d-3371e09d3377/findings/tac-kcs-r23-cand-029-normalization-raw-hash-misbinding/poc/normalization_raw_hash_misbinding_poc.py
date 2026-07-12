#!/usr/bin/env python3
"""Local model of KCS deterministic normalization raw-hash misbinding.

The script uses only temporary synthetic files. It does not invoke KCS, touch
real repositories, use credentials, or contact any service.
"""

from __future__ import annotations

import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path


BENIGN_A = b"# Approved note\n\nstatus: safe-for-index\n"
REPLACEMENT_B = b"# Replacement note\n\nstatus: attacker-controlled\n"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class PreparedUnit:
    unit_key: str
    prepared_hash: str


@dataclass
class MarkdownUnit:
    unit_key: str
    markdown: str


@dataclass
class NormalizedUnit:
    unit_key: str
    raw_hash: str
    prepared_hash: str
    markdown: str


def prepare_units(input_path: Path) -> PreparedUnit:
    # Mirrors the vulnerable shape: preparation reopens the path instead of
    # consuming the caller-verified bytes.
    prepared_bytes = input_path.read_bytes()
    return PreparedUnit(unit_key="doc:1", prepared_hash=sha256(prepared_bytes))


def deterministic_markdownize(raw_hash: str, input_path: Path, hint: PreparedUnit) -> MarkdownUnit:
    # Mirrors the deterministic adapter's trust boundary. raw_hash is an
    # identity hint; the normalized text is read from the current path.
    del raw_hash
    return MarkdownUnit(unit_key=hint.unit_key, markdown=input_path.read_text())


def persist_normalized_unit(raw_hash: str, hint: PreparedUnit, unit: MarkdownUnit) -> NormalizedUnit:
    return NormalizedUnit(
        unit_key=unit.unit_key,
        raw_hash=raw_hash,
        prepared_hash=hint.prepared_hash,
        markdown=unit.markdown,
    )


def fixed_final_binding_check(raw_hash: str, input_path: Path) -> None:
    current = sha256(input_path.read_bytes())
    if current != raw_hash:
        raise RuntimeError("final read hash does not match request raw_hash")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kcs-normalization-misbinding-") as tmp:
        input_path = Path(tmp) / "notes.md"
        input_path.write_bytes(BENIGN_A)

        scan_hash = sha256(BENIGN_A)
        caller_bytes = input_path.read_bytes()
        current_hash = sha256(caller_bytes)
        if current_hash != scan_hash:
            raise SystemExit("unexpected mismatch before replacement")
        raw_hash = current_hash
        print(f"[+] scan hash for version A: {scan_hash[:16]}")
        print("[+] caller verified current read equals scan hash")

        prepared = prepare_units(input_path)
        print(f"[+] prepare derived prepared hash: {prepared.prepared_hash[:16]}")

        input_path.write_bytes(REPLACEMENT_B)
        print("[+] attacker replaced the path after prepare and before markdownize")

        markdown = deterministic_markdownize(raw_hash, input_path, prepared)
        normalized = persist_normalized_unit(raw_hash, prepared, markdown)
        replacement_hash = sha256(REPLACEMENT_B)

        if "attacker-controlled" not in normalized.markdown:
            raise SystemExit("replacement text was not normalized")
        if normalized.raw_hash != scan_hash:
            raise SystemExit("raw identity was not retained")
        if replacement_hash == normalized.raw_hash:
            raise SystemExit("replacement unexpectedly has the same hash as version A")

        print(f"[+] adapter markdown came from version B: {replacement_hash[:16]}")
        print(f"[+] persisted normalized raw_hash: {normalized.raw_hash[:16]}")
        print("[+] primitive reached: version B text is stored under H(version A)")

        try:
            fixed_final_binding_check(raw_hash, input_path)
        except RuntimeError as err:
            print(f"[+] fixed final binding check would reject: {err}")
        else:
            raise SystemExit("fixed binding check unexpectedly accepted replacement")


if __name__ == "__main__":
    main()
