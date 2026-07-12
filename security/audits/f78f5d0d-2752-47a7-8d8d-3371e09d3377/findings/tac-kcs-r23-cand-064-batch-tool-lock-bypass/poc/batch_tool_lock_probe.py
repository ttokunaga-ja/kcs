#!/usr/bin/env python3
"""Static regression probe for KCS-R23-CAND-064.

The probe reads source from a local KCS checkout. It does not execute KCS,
create scopes, invoke adapters, use credentials, or contact services.
"""

from __future__ import annotations

import argparse
import pathlib
import re
import sys


def read(repo: pathlib.Path, rel: str) -> str:
    path = repo / rel
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise SystemExit(f"missing source file: {rel}") from None


def find_function(source: str, name: str) -> str:
    marker = re.search(rf"\bfn\s+{re.escape(name)}\s*\(", source)
    if not marker:
        raise SystemExit(f"missing function: {name}")
    start = marker.start()
    brace = source.find("{", marker.end())
    if brace == -1:
        raise SystemExit(f"function has no body: {name}")
    depth = 0
    for idx in range(brace, len(source)):
        char = source[idx]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : idx + 1]
    raise SystemExit(f"unterminated function: {name}")


def has_validation_before_execution(run_batch: str) -> bool:
    first_execution = run_batch.find("execute_pending_tasks")
    first_validation = run_batch.find("validate_repo_tool_lock")
    return first_validation != -1 and (
        first_execution == -1 or first_validation < first_execution
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="path to a KCS source checkout")
    parser.add_argument(
        "--expect",
        choices=("vulnerable", "fixed"),
        default="vulnerable",
        help="expected source state",
    )
    args = parser.parse_args()

    repo = pathlib.Path(args.repo).resolve()
    main_rs = read(repo, "crates/kcs-cli/src/main.rs")
    scope_rs = read(repo, "crates/kcs-core/src/scope.rs")
    tool_lock_rs = read(repo, "crates/kcs-adapter/src/tool_lock.rs")

    run_batch = find_function(main_rs, "run_batch")
    run_index = find_function(main_rs, "run_index")
    run_repair = find_function(main_rs, "run_repair")
    repo_validate = find_function(scope_rs, "validate")

    checks = []

    batch_opens = "Repository::open_current()?" in run_batch
    batch_locks = "repo.lock_store()?" in run_batch
    batch_executes = "execute_pending_tasks" in run_batch
    batch_validates = has_validation_before_execution(run_batch)

    checks.append(batch_opens and batch_locks)
    print("[+] run_batch opens the repository and holds the store lock")
    checks.append(batch_executes)
    print("[+] run_batch can reach execute_pending_tasks")

    vulnerable = batch_executes and not batch_validates
    if vulnerable:
        print("[!] VULNERABLE: run_batch reaches execution without validate_repo_tool_lock")
    else:
        print("[+] FIXED: run_batch validates tool-lock before execution")

    index_validates = "validate_repo_tool_lock(&repo)?" in run_index
    repair_validates = "validate_repo_tool_lock(&repo)?" in run_repair
    checks.append(index_validates)
    print("[+] run_index validates the tool lock")
    checks.append(repair_validates)
    print("[+] run_repair validates the tool lock")

    repo_open_does_not_cover_lock = "tool-lock" not in repo_validate
    checks.append(repo_open_does_not_cover_lock)
    print("[+] Repository::validate does not cover tool-lock.json")

    parser_rejects_future = (
        "unsupported tool-lock spec_version" in tool_lock_rs
        and "spec_version != 1" in tool_lock_rs
    )
    checks.append(parser_rejects_future)
    print("[+] tool-lock parser rejects unsupported spec_version")

    observed = "vulnerable" if vulnerable else "fixed"
    if not all(checks):
        print("[result] source shape probe failed", file=sys.stderr)
        return 2
    if observed != args.expect:
        print(
            f"[result] observed {observed}, expected {args.expect}",
            file=sys.stderr,
        )
        return 1
    print(f"[result] observed expected state: {observed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
