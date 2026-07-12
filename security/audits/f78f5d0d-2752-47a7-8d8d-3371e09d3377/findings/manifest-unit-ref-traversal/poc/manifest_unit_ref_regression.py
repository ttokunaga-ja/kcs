#!/usr/bin/env python3
"""Bounded regression for manifest-controlled normalized-unit paths.

The harness mirrors the vulnerable reader's path construction:

    instance_dir / f"{manifest_entry['unit_ref']}.json"

All files are synthetic, stay below one TemporaryDirectory, and are deleted
on exit.  The script performs no network access and reads no credentials.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any


MARKER = "CROSS_SCOPE_NORMALIZED_TEXT_7f124f62"
CANONICAL_REF = re.compile(r"[0-9a-f]{16}")


def is_beneath(path: Path, root: Path) -> bool:
    """Return whether resolved path is root or one of its descendants."""

    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


def display(path: Path, lab_root: Path) -> str:
    """Render disposable paths without exposing the host's temp directory."""

    resolved = path.resolve()
    try:
        suffix = resolved.relative_to(lab_root.resolve())
    except ValueError:
        return "<outside-lab>"
    return f"<tmp>/{suffix.as_posix()}"


def unit_object() -> dict[str, Any]:
    return {
        "unit_key": "doc:1",
        "unit_type": "file",
        "raw_hash": "sha256:" + "a" * 64,
        "prepared_hash": "sha256:" + "b" * 64,
        "tool_profile_hash": "sha256:" + "c" * 64,
        "gen": 1,
        "mode": "full",
        "markdown": f"# Synthetic victim unit\n\n{MARKER}\n",
        "reused_from": None,
        "generated_at": "2026-01-01T00:00:00Z",
    }


def manifest(unit_ref: str) -> dict[str, Any]:
    return {
        "raw_hash": "sha256:" + "a" * 64,
        "tool_profile_hash": "sha256:" + "c" * 64,
        "gen": 1,
        "parent_gen": None,
        "run_id": "run_synthetic",
        "units": [
            {
                "order": 0,
                "unit_key": "doc:1",
                "unit_ref": unit_ref,
                "unit_type": "file",
                "status": "done",
                "prepared_hash": "sha256:" + "b" * 64,
                "error_kind": None,
            }
        ],
        "generated_at": "2026-01-01T00:00:00Z",
    }


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def validate_unit_shape(value: Any) -> dict[str, Any]:
    """Require the fields and basic types used by NormalizedUnitObject."""

    expected = {
        "unit_key": str,
        "unit_type": str,
        "raw_hash": str,
        "prepared_hash": str,
        "tool_profile_hash": str,
        "gen": int,
        "mode": str,
        "markdown": str,
        "generated_at": str,
    }
    if not isinstance(value, dict):
        raise ValueError("unit JSON is not an object")
    for field, field_type in expected.items():
        if field not in value or not isinstance(value[field], field_type):
            raise ValueError(f"unit JSON has invalid {field}")
    if "reused_from" not in value:
        raise ValueError("unit JSON is missing reused_from")
    return value


def selected_path(instance_dir: Path, unit_ref: str) -> Path:
    """Match Rust PathBuf::join for the absolute and relative cases used here."""

    return instance_dir / f"{unit_ref}.json"


def vulnerable_load(instance_dir: Path, lab_root: Path) -> tuple[Path, dict[str, Any]]:
    loaded_manifest = json.loads(
        (instance_dir / "manifest.json").read_text(encoding="utf-8")
    )
    entry = loaded_manifest["units"][0]
    path = selected_path(instance_dir, entry["unit_ref"])

    # Safety boundary for this demonstration.  The production reader has no
    # equivalent check; this harness refuses to touch anything outside its lab.
    if not is_beneath(path, lab_root):
        raise RuntimeError("harness safety boundary rejected an out-of-lab read")

    unit = validate_unit_shape(json.loads(path.read_text(encoding="utf-8")))
    return path, unit


def derived_unit_ref(unit_key: str) -> str:
    return hashlib.sha256(unit_key.encode("utf-8")).hexdigest()[:16]


def fixed_load(instance_dir: Path, lab_root: Path) -> tuple[Path, dict[str, Any]]:
    loaded_manifest = json.loads(
        (instance_dir / "manifest.json").read_text(encoding="utf-8")
    )
    entry = loaded_manifest["units"][0]
    unit_ref = entry["unit_ref"]
    expected = derived_unit_ref(entry["unit_key"])
    if CANONICAL_REF.fullmatch(unit_ref) is None or unit_ref != expected:
        raise ValueError("non-canonical or mismatched unit_ref")

    path = selected_path(instance_dir, unit_ref)
    if path.is_symlink():
        raise ValueError("normalized unit must not be a symbolic link")
    if path.resolve().parent != instance_dir.resolve():
        raise ValueError("normalized unit escaped its instance directory")
    if not is_beneath(path, lab_root):
        raise RuntimeError("harness safety boundary rejected an out-of-lab read")

    unit = validate_unit_shape(json.loads(path.read_text(encoding="utf-8")))
    return path, unit


def run_case(kind: str, instance_dir: Path, external_stem: Path, lab_root: Path) -> None:
    if kind == "absolute":
        unit_ref = str(external_stem.resolve())
    elif kind == "parent":
        unit_ref = os.path.relpath(external_stem, start=instance_dir)
    else:
        raise ValueError(f"unsupported case: {kind}")

    write_json(instance_dir / "manifest.json", manifest(unit_ref))
    selected, loaded = vulnerable_load(instance_dir, lab_root)
    contained = selected.resolve().parent == instance_dir.resolve()

    shown_ref = display(Path(unit_ref), lab_root) if Path(unit_ref).is_absolute() else unit_ref
    print(f"[{kind}] unit_ref={shown_ref}")
    print(f"[{kind}] selected={display(selected, lab_root)}")
    print(f"[{kind}] contained_in_instance={str(contained).lower()}")
    print(f"[{kind}] vulnerable_loader_marker={MARKER in loaded['markdown']}")

    try:
        fixed_load(instance_dir, lab_root)
    except ValueError as error:
        print(f"[{kind}] fixed_loader_rejected={error}")
    else:
        raise AssertionError("fixed loader accepted the malicious unit_ref")


def run_control(instance_dir: Path, lab_root: Path) -> None:
    canonical = derived_unit_ref("doc:1")
    write_json(instance_dir / f"{canonical}.json", unit_object())
    write_json(instance_dir / "manifest.json", manifest(canonical))
    _, unit = fixed_load(instance_dir, lab_root)
    if MARKER not in unit["markdown"]:
        raise AssertionError("canonical control did not load the expected unit")
    print(f"[control] canonical_unit_ref={canonical}")
    print("[control] fixed_loader_accepted=true")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case",
        choices=("absolute", "parent", "all"),
        default="all",
        help="path form to exercise (default: all)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="kcs-unit-ref-regression-") as tmp:
        lab_root = Path(tmp)
        instance_dir = (
            lab_root
            / "supplied-store"
            / "objects"
            / "normalized_units"
            / "aa"
            / "aa"
            / "synthetic-profile.g1"
        )
        instance_dir.mkdir(parents=True)

        external_stem = lab_root / "other-scope" / "victim-unit"
        write_json(external_stem.with_suffix(".json"), unit_object())

        cases = ("absolute", "parent") if args.case == "all" else (args.case,)
        for kind in cases:
            run_case(kind, instance_dir, external_stem, lab_root)
        run_control(instance_dir, lab_root)

    print("[+] all bounded regression checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
