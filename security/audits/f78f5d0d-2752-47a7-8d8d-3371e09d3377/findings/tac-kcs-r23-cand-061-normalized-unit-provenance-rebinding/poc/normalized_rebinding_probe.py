#!/usr/bin/env python3
"""Local regression probe for normalized-unit provenance rebinding."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path


REQUESTED_RAW = "sha256:" + "a" * 64
REQUESTED_TOOL = "sha256:" + "1" * 64
REQUESTED_GEN = 7

FORGED_RAW = "sha256:" + "b" * 64
FORGED_TOOL = "sha256:" + "2" * 64
FORGED_GEN = 99


def unit_ref(unit_key: str) -> str:
    return hashlib.sha256(unit_key.encode("utf-8")).hexdigest()[:16]


def vulnerable_reader(instance_dir: Path) -> list[dict[str, object]]:
    manifest = json.loads((instance_dir / "manifest.json").read_text())
    units = []
    for entry in manifest["units"]:
        if entry["status"] != "done":
            continue
        unit = json.loads((instance_dir / f"{entry['unit_ref']}.json").read_text())
        units.append(
            {
                "raw_hash": unit["raw_hash"],
                "tool_profile_hash": unit["tool_profile_hash"],
                "gen": unit["gen"],
                "unit_key": unit["unit_key"],
                "markdown": unit["markdown"],
            }
        )
    return units


def strict_rebinding_errors(instance_dir: Path) -> list[str]:
    manifest = json.loads((instance_dir / "manifest.json").read_text())
    errors: list[str] = []
    if manifest["raw_hash"] != REQUESTED_RAW:
        errors.append("manifest.raw_hash does not match requested raw_hash")
    if manifest["tool_profile_hash"] != REQUESTED_TOOL:
        errors.append("manifest.tool_profile_hash does not match requested tool_profile_hash")
    if manifest["gen"] != REQUESTED_GEN:
        errors.append("manifest.gen does not match requested gen")

    for entry in manifest["units"]:
        if entry["status"] != "done":
            continue
        unit = json.loads((instance_dir / f"{entry['unit_ref']}.json").read_text())
        if entry["unit_ref"] != unit_ref(entry["unit_key"]):
            errors.append("manifest entry unit_ref is not derived from entry.unit_key")
        if entry["unit_ref"] != unit_ref(unit["unit_key"]):
            errors.append("unit_ref filename is not derived from unit.unit_key")
        if unit["raw_hash"] != REQUESTED_RAW:
            errors.append("unit.raw_hash does not match requested raw_hash")
        if unit["tool_profile_hash"] != REQUESTED_TOOL:
            errors.append("unit.tool_profile_hash does not match requested tool_profile_hash")
        if unit["gen"] != REQUESTED_GEN:
            errors.append("unit.gen does not match requested gen")
        if unit["unit_key"] != entry["unit_key"]:
            errors.append("unit.unit_key does not match manifest entry")
        if unit["unit_type"] != entry["unit_type"]:
            errors.append("unit.unit_type does not match manifest entry")
        if unit["prepared_hash"] != entry["prepared_hash"]:
            errors.append("unit.prepared_hash does not match manifest entry")
    return errors


def build_synthetic_instance(instance_dir: Path) -> None:
    entry_key = "page:1"
    forged_key = "page:99"
    entry_ref = unit_ref(entry_key)
    manifest = {
        "raw_hash": "sha256:" + "c" * 64,
        "tool_profile_hash": "sha256:" + "3" * 64,
        "gen": 123,
        "parent_gen": None,
        "run_id": "synthetic-run",
        "units": [
            {
                "order": 0,
                "unit_key": entry_key,
                "unit_ref": entry_ref,
                "unit_type": "page",
                "status": "done",
                "prepared_hash": "sha256:" + "4" * 64,
                "error_kind": None,
            }
        ],
        "generated_at": "2026-07-12T00:00:00Z",
    }
    unit = {
        "unit_key": forged_key,
        "unit_type": "page",
        "raw_hash": FORGED_RAW,
        "prepared_hash": "sha256:" + "5" * 64,
        "tool_profile_hash": FORGED_TOOL,
        "gen": FORGED_GEN,
        "mode": "full",
        "markdown": "# Synthetic injected markdown\n\nThis text did not come from the requested tuple.\n",
        "reused_from": None,
        "generated_at": "2026-07-12T00:00:00Z",
    }
    instance_dir.mkdir(parents=True, exist_ok=True)
    (instance_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (instance_dir / f"{entry_ref}.json").write_text(json.dumps(unit, indent=2) + "\n")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="kcs-normalized-rebind-") as temp:
        instance_dir = Path(temp) / "instance"
        build_synthetic_instance(instance_dir)
        units = vulnerable_reader(instance_dir)
        errors = strict_rebinding_errors(instance_dir)

    print(
        "[+] built synthetic normalized instance for requested tuple "
        f"{REQUESTED_RAW} / {REQUESTED_TOOL} / g{REQUESTED_GEN}"
    )
    print(f"[+] vulnerable reader accepted {len(units)} done unit(s)")
    accepted = units[0]
    print(
        "[+] accepted unit identity: "
        f"raw_hash={accepted['raw_hash']} "
        f"tool_profile_hash={accepted['tool_profile_hash']} "
        f"gen={accepted['gen']} "
        f"unit_key={accepted['unit_key']}"
    )
    if not errors:
        print("[-] strict rebinding unexpectedly accepted the poisoned files")
        return 1
    print("[+] strict rebinding rejected the same files:")
    for error in errors:
        print(f"    - {error}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
