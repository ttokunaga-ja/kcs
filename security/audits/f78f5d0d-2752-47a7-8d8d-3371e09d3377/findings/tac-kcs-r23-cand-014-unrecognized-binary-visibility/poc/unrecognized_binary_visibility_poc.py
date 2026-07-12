#!/usr/bin/env python3
"""Offline PoC for KCS unrecognized-binary completeness telemetry."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


EVENT_CODE = "KCS-I-INDEX-INPUT-UNRECOGNIZED-BINARY-001"


def run_json(kcs_bin: str, cwd: Path, env: dict[str, str], args: list[str]) -> Any:
    proc = subprocess.run(
        [kcs_bin, *args],
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"kcs {' '.join(args)} failed with exit {proc.returncode}: {proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"kcs {' '.join(args)} did not return JSON: {proc.stdout}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--kcs-bin", default=os.environ.get("KCS_BIN", "kcs"))
    parser.add_argument("--keep-temp", action="store_true")
    args = parser.parse_args()

    kcs_bin = args.kcs_bin
    if os.sep not in kcs_bin:
        resolved = shutil.which(kcs_bin)
        require(resolved is not None, f"could not find {kcs_bin!r} on PATH")
        kcs_bin = resolved

    temp_dir = Path(tempfile.mkdtemp(prefix="kcs-unrecognized-binary-"))
    try:
        scope = temp_dir / "scope"
        xdg_config = temp_dir / "config"
        xdg_data = temp_dir / "data"
        xdg_cache = temp_dir / "cache"
        for directory in (scope, xdg_config, xdg_data, xdg_cache):
            directory.mkdir(parents=True, exist_ok=True)

        (scope / "photo.bmp").write_bytes(
            b"BM" + bytes(((i * 97) & 0x7F) | 0x80 for i in range(2000))
        )
        (scope / "ok.md").write_text(
            "# OK\n\nplain readable body alpha bravo charlie.\n", encoding="utf-8"
        )

        env = os.environ.copy()
        env.update(
            {
                "XDG_CONFIG_HOME": str(xdg_config),
                "XDG_DATA_HOME": str(xdg_data),
                "XDG_CACHE_HOME": str(xdg_cache),
            }
        )

        run_json(kcs_bin, scope, env, ["init", "--json"])
        index = run_json(kcs_bin, scope, env, ["index", "--yes", "--json"])
        require(
            index.get("skipped_unrecognized_binary_files") == 1,
            f"expected one skipped unrecognized binary, got {index}",
        )
        require(index.get("normalized_files") == 1, f"expected one normalized file, got {index}")
        require(index.get("pending_online_tasks") == 0, f"expected no pending online tasks, got {index}")

        status = run_json(kcs_bin, scope, env, ["status", "--json"])
        files = {row["relative_path"]: row for row in status.get("files", [])}
        require(files.get("photo.bmp", {}).get("status") == "unchanged", f"bad status: {status}")
        tasks = status.get("tasks", [])
        require(
            not any(task.get("input_path") == "photo.bmp" for task in tasks),
            f"unexpected task for photo.bmp: {tasks}",
        )
        require(
            any(task.get("input_path") == "ok.md" and task.get("status") == "done" for task in tasks),
            f"missing completed ok.md markdownize task: {tasks}",
        )

        search = run_json(kcs_bin, scope, env, ["search", "charlie", "--text", "--json"])
        index_status = search.get("index_status", {})
        require(index_status.get("enriched_ratio") == 1.0, f"unexpected search status: {search}")
        require(index_status.get("pending_enrichment_tasks") == 0, f"unexpected pending count: {search}")
        require(index_status.get("budget_paused") is False, f"unexpected budget pause: {search}")
        require(
            any(result.get("title") == "ok.md" for result in search.get("results", [])),
            f"recognized text control was not searchable: {search}",
        )

        events_path = xdg_data / "kcs" / "logs" / "events.jsonl"
        events = [
            json.loads(line)
            for line in events_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        event = next((entry for entry in events if entry.get("code") == EVENT_CODE), None)
        require(event is not None, f"missing {EVENT_CODE} in events log")
        context = event.get("context", {})
        require(context.get("media_type") == "application/octet-stream", f"bad event: {event}")
        require(context.get("size_bytes") == 2002, f"bad event size: {event}")
        serialized_event = json.dumps(event, sort_keys=True)
        require("path" not in context and "input_path" not in context, f"path-bearing event: {event}")
        require("photo.bmp" not in serialized_event, f"event unexpectedly names path: {event}")

        print("[+] created disposable scope with ok.md and photo.bmp")
        print("[+] index: skipped_unrecognized_binary_files=1 normalized_files=1 pending_online_tasks=0")
        print("[+] status: photo.bmp status=unchanged and no task references photo.bmp")
        print(
            "[+] search: ok.md is searchable and "
            "index_status=enriched_ratio=1.0,pending=0,budget_paused=false"
        )
        print(
            "[+] event: "
            f"{EVENT_CODE} has media_type=application/octet-stream,size_bytes=2002 "
            "and no path/input_path"
        )
        print(
            "[+] vulnerable behavior reproduced: archived binary is absent from "
            "durable completeness telemetry"
        )
        return 0
    except Exception as exc:
        print(f"[!] {exc}", file=sys.stderr)
        print(f"[!] temporary directory retained at: {temp_dir}", file=sys.stderr)
        args.keep_temp = True
        return 1
    finally:
        if not args.keep_temp:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
