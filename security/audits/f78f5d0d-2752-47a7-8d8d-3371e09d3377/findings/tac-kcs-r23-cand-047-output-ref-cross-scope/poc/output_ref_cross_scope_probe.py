#!/usr/bin/env python3
"""Local, synthetic model for KCS-R23-CAND-047.

The script creates two temporary KCS-like scopes. It demonstrates that a raw
persisted output_ref can select a foreign normalized instance, and that a fixed
scope-contained resolver rejects the same reference before reading manifest.json.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path


def write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def vulnerable_load_previous_instance(output_ref: str) -> dict:
    directory = Path(output_ref)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    units = []
    for entry in manifest["units"]:
        if entry["status"] != "done":
            continue
        units.append(json.loads((directory / f"{entry['unit_ref']}.json").read_text(encoding="utf-8")))
    return {"manifest": manifest, "units": {unit["unit_key"]: unit for unit in units}}


def fixed_resolve_output_ref(victim_kcs: Path, output_ref: str) -> Path:
    normalized_root = (victim_kcs / "objects" / "normalized").resolve()
    candidate = Path(output_ref)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("output_ref escapes the current normalized root")
    resolved = (normalized_root / candidate).resolve()
    if not resolved.is_relative_to(normalized_root):
        raise ValueError("output_ref escapes the current normalized root")
    return resolved


def reuse_unchanged_unit(previous: dict, current_raw_hash: str, unit_key: str) -> dict:
    previous_unit = previous["units"][unit_key]
    return {
        "unit_key": unit_key,
        "raw_hash": current_raw_hash,
        "prepared_hash": "sha256:current-prepared",
        "tool_profile_hash": previous["manifest"]["tool_profile_hash"],
        "markdown": previous_unit["markdown"],
        "reused_from": {
            "raw_hash": previous_unit["raw_hash"],
            "gen": previous_unit["gen"],
            "unit_key": previous_unit["unit_key"],
        },
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="kcs-cand047-") as tmp:
        root = Path(tmp)
        victim_kcs = root / "victim" / ".kcs"
        foreign_instance = root / "foreign" / ".kcs" / "objects" / "normalized" / "sha256-foreign-profile" / "run_foreign"
        unit_ref = "unit-page-1"
        write_json(
            foreign_instance / "manifest.json",
            {
                "raw_hash": "sha256:foreign-raw",
                "tool_profile_hash": "sha256:compatible-profile",
                "gen": 7,
                "run_id": "run_foreign",
                "units": [
                    {
                        "unit_ref": unit_ref,
                        "unit_key": "page-1",
                        "status": "done",
                        "order": 0,
                        "unit_type": "page",
                        "prepared_hash": "sha256:foreign-prepared",
                    }
                ],
            },
        )
        write_json(
            foreign_instance / f"{unit_ref}.json",
            {
                "unit_key": "page-1",
                "raw_hash": "sha256:foreign-raw",
                "gen": 7,
                "markdown": "FOREIGN MARKDOWN COPIED INTO CURRENT SCOPE",
            },
        )
        supplied_task = {
            "input_path": "current.pdf",
            "input_hash": "sha256:current-raw",
            "status": "done",
            "fallback_reason": "online_adapter_done",
            "output_ref": str(foreign_instance),
        }
        print("[+] built victim and foreign fixture under a disposable temp root")
        previous = vulnerable_load_previous_instance(supplied_task["output_ref"])
        print("[+] vulnerable loader accepted foreign output_ref")
        rebound = reuse_unchanged_unit(previous, supplied_task["input_hash"], "page-1")
        assert rebound["raw_hash"] == "sha256:current-raw"
        assert rebound["markdown"] == "FOREIGN MARKDOWN COPIED INTO CURRENT SCOPE"
        assert rebound["reused_from"]["raw_hash"] == "sha256:foreign-raw"
        print("[+] unchanged reuse copied foreign markdown into current raw identity")
        try:
            fixed_resolve_output_ref(victim_kcs, supplied_task["output_ref"])
        except ValueError:
            print("[+] fixed guard rejected cross-scope output_ref before reading manifest")
        else:
            raise AssertionError("fixed resolver unexpectedly accepted foreign output_ref")


if __name__ == "__main__":
    main()
