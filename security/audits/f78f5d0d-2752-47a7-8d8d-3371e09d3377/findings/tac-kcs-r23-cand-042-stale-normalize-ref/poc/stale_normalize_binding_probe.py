#!/usr/bin/env python3
"""
Synthetic regression probe for KCS-R23-CAND-042.

The probe models only the relevant identity transition. It does not invoke KCS,
read repository data, or race the filesystem. It shows why a path-keyed
NormalizeRef without an expected raw hash can be attached to different bytes at
snapshot time, and why carrying expected_raw_hash rejects the drift.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class NormalizeRef:
    tool_profile_hash: str
    gen: int


@dataclass(frozen=True)
class PendingNormalizeRef:
    expected_raw_hash: str
    normalize: NormalizeRef


def vulnerable_publish(path: str, current_bytes: bytes, normalize_by_path: dict[str, NormalizeRef]) -> dict:
    """Model scope.rs: build a tree from current bytes and attach by path only."""
    return {
        "path": path,
        "raw_hash": sha256(current_bytes),
        "normalize": normalize_by_path.get(path),
    }


def fixed_publish(path: str, current_bytes: bytes, normalize_by_path: dict[str, PendingNormalizeRef]) -> dict:
    """Model the remediation: attach only if the expected and current hashes match."""
    current_hash = sha256(current_bytes)
    pending = normalize_by_path.get(path)
    if pending is not None and pending.expected_raw_hash != current_hash:
        return {"path": path, "raw_hash": current_hash, "normalize": None, "drift_rejected": True}
    return {
        "path": path,
        "raw_hash": current_hash,
        "normalize": None if pending is None else pending.normalize,
        "drift_rejected": False,
    }


def main() -> None:
    path = "scope-note.md"
    old_bytes = b"trusted normalized content\n"
    new_bytes = b"changed during close snapshot\n"
    profile = sha256(b"deterministic-markdown-profile")
    old_hash = sha256(old_bytes)
    new_hash = sha256(new_bytes)

    normalized_units = {(old_hash, profile, 0): ["unit-for-old-bytes"]}
    vulnerable_map = {path: NormalizeRef(tool_profile_hash=profile, gen=0)}
    fixed_map = {path: PendingNormalizeRef(expected_raw_hash=old_hash, normalize=vulnerable_map[path])}

    vulnerable_tree_entry = vulnerable_publish(path, new_bytes, vulnerable_map)
    stale_lookup_key = (
        vulnerable_tree_entry["raw_hash"],
        vulnerable_tree_entry["normalize"].tool_profile_hash,
        vulnerable_tree_entry["normalize"].gen,
    )
    fixed_tree_entry = fixed_publish(path, new_bytes, fixed_map)

    print(f"old_hash={old_hash}")
    print(f"new_hash={new_hash}")
    print("vulnerable_tree_has_normalize=", vulnerable_tree_entry["normalize"] is not None)
    print("vulnerable_rebuild_units_found=", stale_lookup_key in normalized_units)
    print("fixed_drift_rejected=", fixed_tree_entry["drift_rejected"])
    print("fixed_tree_has_normalize=", fixed_tree_entry["normalize"] is not None)

    assert old_hash != new_hash
    assert vulnerable_tree_entry["normalize"] is not None
    assert stale_lookup_key not in normalized_units
    assert fixed_tree_entry["drift_rejected"] is True
    assert fixed_tree_entry["normalize"] is None


if __name__ == "__main__":
    main()
