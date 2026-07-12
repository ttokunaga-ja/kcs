#!/usr/bin/env python3
"""Offline regression oracle for persisted-tree semantic validation.

This script reads one bundled synthetic JSON fixture and performs string/path
calculations only. It never creates, overwrites, or removes a filesystem path.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from pathlib import Path
from typing import Any


HASH = re.compile(r"sha256:[0-9a-f]{64}\Z")
SCOPE_ROOT = "synthetic-scope"


def canonical_bytes(value: Any) -> bytes:
    # The fixture uses only ASCII strings and integers, for which this is the
    # same compact, key-sorted representation relevant to its JCS hash.
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def validate_tree_strict(tree: dict[str, Any]) -> None:
    if tree.get("object_type") != "tree":
        raise ValueError("object_type must be tree")
    entries = tree.get("entries")
    if not isinstance(entries, list):
        raise ValueError("entries must be an array")

    previous: bytes | None = None
    for entry in entries:
        path = entry.get("path")
        if not isinstance(path, str) or not path or "/" in path or "\\" in path:
            raise ValueError("tree entry path must be a direct child file name")
        encoded_path = path.encode("utf-8")
        if previous is not None and previous >= encoded_path:
            raise ValueError("tree entries must be strictly sorted and unique")
        previous = encoded_path
        if entry.get("type") != "file":
            raise ValueError("tree entry type must be file")
        if not isinstance(entry.get("raw_hash"), str) or not HASH.fullmatch(
            entry["raw_hash"]
        ):
            raise ValueError("raw_hash must be sha256 lowercase hex")
        normalize = entry.get("normalize")
        if normalize is not None:
            profile = normalize.get("tool_profile_hash")
            if not isinstance(profile, str) or not HASH.fullmatch(profile):
                raise ValueError("tool_profile_hash must be sha256 lowercase hex")
            gen = normalize.get("gen", 0)
            if not isinstance(gen, int) or isinstance(gen, bool) or gen < 0:
                raise ValueError("gen must be a non-negative integer")


def normalized_instance_path(entry: dict[str, Any], gen: int) -> tuple[str, str]:
    raw_hash = entry["raw_hash"]
    profile = entry["normalize"]["tool_profile_hash"]
    digest = raw_hash.removeprefix("sha256:")
    base = posixpath.join(
        SCOPE_ROOT, ".kcs", "objects", "normalized_units", digest[:2], digest[2:4]
    )
    constructed = posixpath.join(base, f"{raw_hash}.{profile}.g{gen}")
    return constructed, posixpath.normpath(constructed)


def main() -> int:
    fixture = Path(__file__).with_name("synthetic-tree.json")
    tree = json.loads(fixture.read_text(encoding="utf-8"))
    payload = canonical_bytes(tree)
    content_hash = "sha256:" + hashlib.sha256(payload).hexdigest()

    # json.loads accepting the object models the shape-only deserialization step.
    shape_accepted = isinstance(tree.get("entries"), list)
    entry = tree["entries"][0]
    new_gen = entry["normalize"]["gen"] + 1
    constructed, normalized = normalized_instance_path(entry, new_gen)
    common = posixpath.commonpath([SCOPE_ROOT, normalized])
    contained = common == SCOPE_ROOT

    strict_error = ""
    try:
        validate_tree_strict(tree)
    except ValueError as error:
        strict_error = str(error)

    print(f"fixture={fixture.name}")
    print(f"canonical_cas_hash={content_hash}")
    print(f"json_shape_deserialization={'accepted' if shape_accepted else 'rejected'}")
    print(f"constructed_destination={constructed}")
    print(f"normalized_destination={normalized}")
    print(f"contained_in_scope={str(contained).lower()}")
    print(f"strict_read_validation=rejected: {strict_error}")
    print("filesystem_operations=none")

    if not shape_accepted or contained or not strict_error:
        print("FAIL: the regression oracle did not observe the expected invariant")
        return 1
    print("PASS: shape-valid content is rejected semantically before path use")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
