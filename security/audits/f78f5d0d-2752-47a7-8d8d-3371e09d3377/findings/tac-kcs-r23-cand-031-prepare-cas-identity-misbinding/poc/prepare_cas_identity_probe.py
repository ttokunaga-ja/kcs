#!/usr/bin/env python3
"""Synthetic regression probe for KCS-R23-CAND-031.

This script does not invoke KCS and does not race the filesystem. It models
the validated bad transition: prepare derives a prepared object name from a
later read, while publication writes the caller-retained earlier bytes.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path


VERSION_A = b"version A: checked by caller\n"
VERSION_B = b"version B: reopened by prepare\n"


def kcs_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def object_path(root: Path, prepared_hash: str) -> Path:
    digest = prepared_hash.removeprefix("sha256:")
    return root / "objects" / "prepared" / digest[:2] / digest[2:4] / prepared_hash


def main() -> int:
    caller_bytes = VERSION_A
    caller_hash = kcs_hash(caller_bytes)
    scan_hash = caller_hash
    if caller_hash != scan_hash:
        raise AssertionError("control setup failed: first read should pass")
    print("[+] first read accepted version A")

    prepare_bytes = VERSION_B
    prepared_hash = kcs_hash(prepare_bytes)
    print(f"[+] prepare-stage reopen derived {prepared_hash} from version B")

    with tempfile.TemporaryDirectory(prefix="kcs-cand031-") as tmp:
        root = Path(tmp)
        destination = object_path(root, prepared_hash)
        destination.parent.mkdir(parents=True, exist_ok=True)

        # This mirrors write_prepared_objects() for a single text-native unit:
        # the destination is selected from prepare's hash, but the body is the
        # caller-retained first-read bytes.
        destination.write_bytes(caller_bytes)
        written_hash = kcs_hash(destination.read_bytes())
        print("[+] publication wrote caller-retained version A under B's prepared hash")

        if written_hash == prepared_hash:
            raise AssertionError("unexpectedly wrote bytes that match the prepared object name")

        print(
            "[+] mismatch reproduced: object name expects "
            f"{prepared_hash.removeprefix('sha256:')[:16]}..., "
            f"body hashes to {written_hash.removeprefix('sha256:')[:16]}..."
        )

    print(
        "[+] fixed invariant would reject before publication or write bytes "
        "that hash to the object name"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
