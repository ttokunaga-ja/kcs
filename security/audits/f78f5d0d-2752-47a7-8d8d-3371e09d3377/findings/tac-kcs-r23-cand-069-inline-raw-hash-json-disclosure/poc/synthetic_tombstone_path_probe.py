#!/usr/bin/env python3
"""Safe local probe for KCS-R23-CAND-069.

The probe models the vulnerable tombstone path construction with synthetic
temporary files only. It never invokes KCS, reads user data, uses credentials, or
contacts a network service.
"""

from __future__ import annotations

import json
import re
import tempfile
from pathlib import Path


def vulnerable_tombstone_path(kcs_dir: Path, raw_hash: str) -> Path | None:
    digest = raw_hash.removeprefix("sha256:")
    if len(digest) < 4:
        return None
    return kcs_dir / "tombstones" / digest[0:2] / digest[2:4] / raw_hash


def strict_hash_is_valid(raw_hash: str) -> bool:
    return re.fullmatch(r"sha256:[0-9a-f]{64}", raw_hash) is not None


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kcs-cand-069-") as tmp:
        root = Path(tmp)
        kcs_dir = root / "repo" / ".kcs"
        marker = root / "marker.json"
        marker.write_text(
            json.dumps(
                {
                    "kind": "synthetic-marker",
                    "note": "example-only",
                },
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        raw_hash = str(marker)
        joined = vulnerable_tombstone_path(kcs_dir, raw_hash)
        if joined is None:
            raise AssertionError("synthetic raw_hash should pass the length check")

        contained = Path(kcs_dir / "tombstones") in [joined, *joined.parents]
        data = json.loads(joined.read_text(encoding="utf-8"))
        context = {
            **data,
            "raw_hash": raw_hash,
            "scope_path": str(kcs_dir),
            "status": "purged",
        }

        print(f"[+] synthetic kcs_dir: {kcs_dir}")
        print(f"[+] attacker raw_hash: {raw_hash}")
        print(f"[+] vulnerable join result: {joined}")
        print(f"[+] containment under tombstones: {str(contained).lower()}")
        print(f"[+] reflected JSON context keys: {', '.join(sorted(context))}")
        print(
            "[+] strict sha256 validator rejects attacker raw_hash: "
            f"{str(not strict_hash_is_valid(raw_hash)).lower()}"
        )

        if joined != marker:
            raise AssertionError("absolute raw_hash did not replace the tombstone prefix")
        if contained:
            raise AssertionError("joined path should not remain under tombstones")
        if strict_hash_is_valid(raw_hash):
            raise AssertionError("strict validator should reject path-shaped raw_hash")


if __name__ == "__main__":
    main()
