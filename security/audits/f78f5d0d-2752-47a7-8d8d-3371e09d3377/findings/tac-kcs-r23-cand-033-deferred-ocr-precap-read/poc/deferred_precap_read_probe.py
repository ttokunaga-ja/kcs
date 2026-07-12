#!/usr/bin/env python3
"""Safe local probe for the deferred-task read-before-cap ordering.

The probe models the vulnerable control order with tiny synthetic files:
an originally acceptable input is replaced before a later resume, and the
resume path reads the replacement before checking the configured cap.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


CAP_BYTES = 4096
ORIGINAL_BYTES = 1024
REPLACEMENT_BYTES = 16384


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vulnerable_resume_probe(path: Path, expected_hash: str, cap_bytes: int) -> tuple[str, int]:
    current_bytes = path.read_bytes()
    bytes_read_before_control = len(current_bytes)
    if hashlib.sha256(current_bytes).hexdigest() != expected_hash:
        return "retire_hash_mismatch", bytes_read_before_control
    if len(current_bytes) > cap_bytes:
        return "retire_oversize", bytes_read_before_control
    return "send", bytes_read_before_control


def fixed_resume_probe(path: Path, cap_bytes: int) -> tuple[str, int]:
    size = path.stat().st_size
    if size > cap_bytes:
        return "retire_oversize_before_read", 0
    data = path.read_bytes()
    return "would_continue_after_bounded_read", len(data)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kcs-cand-033-") as tmp:
        work = Path(tmp)
        target = work / "queued-ocr-input.bin"

        target.write_bytes(b"A" * ORIGINAL_BYTES)
        queued_hash = sha256_file(target)
        print(f"[+] queued small task: size={target.stat().st_size} cap={CAP_BYTES}")

        os.replace(work / "queued-ocr-input.bin", work / "old-name.bin")
        target.write_bytes(b"B" * REPLACEMENT_BYTES)
        print(f"[+] replacement before resume: size={target.stat().st_size}")

        decision, read_before_control = vulnerable_resume_probe(target, queued_hash, CAP_BYTES)
        print(f"[vulnerable-order] decision={decision} bytes_read_before_control={read_before_control}")

        fixed_decision, fixed_read = fixed_resume_probe(target, CAP_BYTES)
        print(f"[fixed-order] decision={fixed_decision} bytes_read_before_control={fixed_read}")

        if decision != "retire_hash_mismatch":
            raise SystemExit("unexpected vulnerable-order decision")
        if read_before_control != REPLACEMENT_BYTES:
            raise SystemExit("probe did not model full replacement read")
        if fixed_decision != "retire_oversize_before_read" or fixed_read != 0:
            raise SystemExit("fixed-order model should reject before reading")

    print("[+] synthetic probe completed without external services or large allocations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
