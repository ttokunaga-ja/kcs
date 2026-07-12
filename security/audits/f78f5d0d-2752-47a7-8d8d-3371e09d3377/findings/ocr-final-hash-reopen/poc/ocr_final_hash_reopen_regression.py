#!/usr/bin/env python3
"""Credential-free regression model for the Mistral OCR byte-binding seam.

The probe uses two ordinary files in one temporary directory.  It models the
KCS executor's final hash check, atomically replaces the checked pathname, and
then compares the vulnerable fresh-read behavior with the intended fail-closed
adapter invariant.  The "transport" only captures bytes in memory: this file
does not open a socket, read credentials, invoke KCS, or contact any service.
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


APPROVED_BYTES = b"%PDF-1.7\n% approved document A\n%%EOF\n"
REPLACEMENT_BYTES = b"%PDF-1.7\n% unapproved document B\n%%EOF\n"


def hash_bytes(data: bytes) -> str:
    """Match KCS's `sha256:<lower-hex>` raw identity format."""

    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RawInput:
    raw_hash: str
    path: Path


class InputIdentityMismatch(RuntimeError):
    pass


class LocalOcrCapture:
    """An adapter transport seam that records a body without network I/O."""

    def __init__(self) -> None:
        self.bodies: list[bytes] = []

    def post_document(self, body: bytes) -> None:
        self.bodies.append(body)


def executor_final_check(raw: RawInput) -> bytes:
    """Model `main.rs:6596-6605`: read once and verify the task hash."""

    checked = raw.path.read_bytes()
    if hash_bytes(checked) != raw.raw_hash:
        raise InputIdentityMismatch("executor rejected stale input")
    return checked


def vulnerable_ocr_send(raw: RawInput, capture: LocalOcrCapture) -> None:
    """Model `mistral_ocr.rs:112-134`: reopen path, then send fresh bytes."""

    reopened = raw.path.read_bytes()
    # The vulnerable revision does not compare hash_bytes(reopened) with
    # raw.raw_hash before constructing the authenticated OCR request.
    capture.post_document(reopened)


def bound_ocr_send(raw: RawInput, capture: LocalOcrCapture) -> None:
    """Regression oracle: bind the final bytes before any transport call."""

    reopened = raw.path.read_bytes()
    actual_hash = hash_bytes(reopened)
    if actual_hash != raw.raw_hash:
        raise InputIdentityMismatch(
            f"final OCR bytes changed: expected {raw.raw_hash}, got {actual_hash}"
        )
    capture.post_document(reopened)


def main() -> None:
    if len(sys.argv) != 1:
        raise SystemExit("this bounded regression accepts no arguments")

    with tempfile.TemporaryDirectory(prefix="kcs-ocr-byte-binding-") as temp:
        directory = Path(temp)
        selected_path = directory / "selected.pdf"
        replacement_path = directory / "replacement.pdf"

        selected_path.write_bytes(APPROVED_BYTES)
        expected_hash = hash_bytes(APPROVED_BYTES)
        raw = RawInput(raw_hash=expected_hash, path=selected_path)

        checked = executor_final_check(raw)
        assert checked == APPROVED_BYTES

        replacement_path.write_bytes(REPLACEMENT_BYTES)
        os.replace(replacement_path, selected_path)
        replacement_hash = hash_bytes(REPLACEMENT_BYTES)
        assert replacement_hash != expected_hash

        vulnerable_capture = LocalOcrCapture()
        vulnerable_ocr_send(raw, vulnerable_capture)
        assert vulnerable_capture.bodies == [REPLACEMENT_BYTES]

        fixed_capture = LocalOcrCapture()
        try:
            bound_ocr_send(raw, fixed_capture)
        except InputIdentityMismatch:
            fixed_result = "identity_mismatch"
        else:
            raise AssertionError("bound adapter accepted replacement bytes")
        assert fixed_capture.bodies == []

        # Stable-file control: the proposed invariant must still accept bytes that
        # retain the identity checked by the executor.
        selected_path.write_bytes(APPROVED_BYTES)
        stable_capture = LocalOcrCapture()
        bound_ocr_send(raw, stable_capture)
        assert stable_capture.bodies == [APPROVED_BYTES]

        print(f"approved_hash={expected_hash}")
        print(f"replacement_hash={replacement_hash}")
        print(f"executor_checked_bytes={len(checked)}")
        print(
            "vulnerable_capture="
            f"replacement bytes={vulnerable_capture.bodies[0] == REPLACEMENT_BYTES}"
        )
        print(f"fixed_result={fixed_result}")
        print(f"fixed_capture_count={len(fixed_capture.bodies)}")
        print("stable_control=accepted")
        print("network_calls=0 credential_reads=0 status=pass")


if __name__ == "__main__":
    main()
