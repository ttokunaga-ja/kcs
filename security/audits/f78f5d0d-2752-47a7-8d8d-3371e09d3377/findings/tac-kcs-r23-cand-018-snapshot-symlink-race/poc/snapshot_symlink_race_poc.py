#!/usr/bin/env python3
"""Deterministic local model of the KCS snapshot file-type/read TOCTOU."""

from __future__ import annotations

import hashlib
import os
import pathlib
import sys
import tempfile


OUTSIDE_BYTES = b"OUTSIDE_SCOPE_MARKER=operator-readable\n"


def fail(message: str) -> None:
    print(f"[-] {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kcs-symlink-race-poc-") as tmp:
        base = pathlib.Path(tmp)
        scope = base / "scope"
        scope.mkdir()
        outside = base / "outside-victim.txt"
        outside.write_bytes(OUTSIDE_BYTES)

        candidate = scope / "report.txt"
        candidate.write_text("benign in-scope bytes\n", encoding="utf-8")

        print("[+] built temporary synthetic scope")

        with os.scandir(scope) as entries:
            observed = {entry.name: entry for entry in entries}
            entry = observed.get("report.txt")
            if entry is None:
                fail("synthetic candidate was not enumerated")
            if not entry.is_file(follow_symlinks=False):
                fail("candidate did not start as a no-follow regular file")

        print("[+] observed report.txt as a regular direct child")

        candidate.unlink()
        os.symlink("../outside-victim.txt", candidate)
        print("[+] replaced report.txt with symlink target ../outside-victim.txt")

        followed = candidate.read_bytes()
        if followed != OUTSIDE_BYTES:
            fail("pathname read did not follow the replacement to outside bytes")

        digest = hashlib.sha256(followed).hexdigest()
        print("[+] fs::read-style pathname reopen followed the replacement symlink")
        print("[+] archived tree name: report.txt")
        print(f"[+] followed bytes sha256: sha256:{digest}")
        print("RESULT: OUTSIDE_SCOPE_BYTES_ARCHIVED_UNDER_BENIGN_NAME")


if __name__ == "__main__":
    main()
