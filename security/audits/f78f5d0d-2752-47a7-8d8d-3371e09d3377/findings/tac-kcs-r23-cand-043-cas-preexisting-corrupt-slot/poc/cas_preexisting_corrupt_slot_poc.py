#!/usr/bin/env python3
"""Safe synthetic PoC for KCS-R23-CAND-043.

This models the KCS CAS fanout and the vulnerable `atomic_write()` early
success branch using only synthetic bytes inside a disposable temporary
directory. It does not touch a real KCS store.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path


GOOD_BYTES = b"trusted document\n"
POISON_BYTES = b"preseeded corrupt bytes\n"


def kcs_hash(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def fanout_path(store: Path, object_hash: str) -> Path:
    digest = object_hash.removeprefix("sha256:")
    return store / "objects" / "raw" / digest[:2] / digest[2:4] / object_hash


def vulnerable_atomic_write(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        return "ok-existing-without-verification"
    tmp = path.parent / ".tmp-poc"
    tmp.write_bytes(data)
    tmp.replace(path)
    return "ok-written"


def fixed_atomic_write_check(path: Path, data: bytes) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if not path.is_file() or path.read_bytes() != data:
            raise RuntimeError("occupied slot does not match expected CAS object")
        return "ok-existing-verified"
    tmp = path.parent / ".tmp-poc-fixed"
    tmp.write_bytes(data)
    tmp.replace(path)
    return "ok-written"


def main() -> None:
    expected_hash = kcs_hash(GOOD_BYTES)
    poison_hash = kcs_hash(POISON_BYTES)

    with tempfile.TemporaryDirectory(prefix="kcs-cas-poc-") as tmpdir:
        store = Path(tmpdir) / ".kcs"
        object_path = fanout_path(store, expected_hash)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        object_path.write_bytes(POISON_BYTES)

        result = vulnerable_atomic_write(object_path, GOOD_BYTES)
        actual_hash = kcs_hash(object_path.read_bytes())

        print(f"[+] expected object hash: {expected_hash}")
        print(f"[+] preseeded slot hash: {poison_hash}")
        print(f"[+] vulnerable write result: {result}")
        still_poisoned = "yes" if object_path.read_bytes() == POISON_BYTES else "no"
        print(f"[+] slot still contains preseeded bytes: {still_poisoned}")
        print(
            "[+] later read detects mismatch: "
            f"expected {expected_hash} actual {actual_hash}"
        )

        try:
            fixed_atomic_write_check(object_path, GOOD_BYTES)
        except RuntimeError as error:
            print(f"[+] fixed write rejects mismatch: {error}")
        else:
            raise SystemExit("fixed check unexpectedly accepted corrupt slot")

    print("[+] synthetic regression check complete")


if __name__ == "__main__":
    main()
