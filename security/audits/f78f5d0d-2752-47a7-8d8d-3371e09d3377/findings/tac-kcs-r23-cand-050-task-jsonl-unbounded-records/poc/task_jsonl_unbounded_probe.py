#!/usr/bin/env python3
"""Bounded regression probe for oversized KCS task JSONL records."""

from __future__ import annotations

import json
import pathlib
import shutil
import tempfile


def task(task_id: str, input_path: str, key_count: int) -> dict:
    keys = [f"unit-{index:04d}-{'x' * 24}" for index in range(key_count)]
    return {
        "task_id": task_id,
        "type": "markdownize",
        "mode": "full",
        "input_path": input_path,
        "input_hash": f"sha256:{'a' * 64}",
        "previous_raw_hash": None,
        "parent_run_id": None,
        "changed_unit_keys": keys,
        "output_ref": "online:test",
        "unit_keys": list(keys),
        "status": "pending",
        "attempts": 0,
        "next_retry_at": None,
        "deadline": None,
        "heartbeat_at": None,
        "fallback_reason": None,
        "created_at": "2026-07-11T00:00:00Z",
    }


def is_scope_local_file_name(input_path: str) -> bool:
    if not input_path or "/" in input_path or "\\" in input_path:
        return False
    return input_path not in {".", ".."}


def vulnerable_read(path: pathlib.Path) -> list[dict]:
    by_id: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            descriptor = json.loads(line)
            if not is_scope_local_file_name(descriptor["input_path"]):
                raise ValueError(
                    "path guard ran after parsing "
                    f"{len(descriptor['changed_unit_keys'])}+"
                    f"{len(descriptor['unit_keys'])} keys: "
                    f"{descriptor['input_path']}"
                )
            by_id[descriptor["task_id"]] = descriptor
    return list(by_id.values())


def write_jsonl(path: pathlib.Path, rows: list[dict]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, separators=(",", ":")))
            handle.write("\n")
    return path.stat().st_size


def main() -> None:
    root = pathlib.Path(tempfile.mkdtemp(prefix="kcs-cand-050-"))
    try:
        large = root / "large" / "tasks.jsonl"
        line_bytes = write_jsonl(large, [task("task_large", "report.pdf", 512)])
        parsed = vulnerable_read(large)[0]

        records = root / "records" / "tasks.jsonl"
        write_jsonl(
            records,
            [task(f"task_{index:03d}", "report.pdf", 0) for index in range(64)],
        )
        retained = len(vulnerable_read(records))

        poison = root / "poison" / "tasks.jsonl"
        write_jsonl(poison, [task("task_poison", "../escape.pdf", 512)])
        try:
            vulnerable_read(poison)
        except ValueError as err:
            poison_result = str(err)
        else:
            raise AssertionError("poisoned path unexpectedly passed")

        print(f"[ok] large record line bytes: {line_bytes}")
        print(f"[ok] parsed changed_unit_keys: {len(parsed['changed_unit_keys'])}")
        print(f"[ok] parsed unit_keys: {len(parsed['unit_keys'])}")
        print(f"[ok] retained unique records: {retained}")
        print(f"[ok] poisoned path rejected after parsing {poison_result}")
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
