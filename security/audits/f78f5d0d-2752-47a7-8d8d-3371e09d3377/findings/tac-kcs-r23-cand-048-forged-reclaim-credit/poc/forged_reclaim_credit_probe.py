#!/usr/bin/env python3
"""Synthetic local probe for the KCS forged reclaim-credit accounting path.

The probe models only the validated accounting transition. It does not contact
adapters, read credentials, mutate a KCS store, or send network traffic.
"""

from __future__ import annotations

import json
import math

VALID_HASH = "sha256:" + "a" * 64


def is_scope_local_file_name(path: str) -> bool:
    return bool(path) and "/" not in path and "\\" not in path and path not in {".", ".."}


def is_hash(value: str) -> bool:
    return value.startswith("sha256:") and len(value) == len("sha256:") + 64


def task_store_all_accepts_shape(task: dict) -> bool:
    # Mirrors the relevant TaskStore::all() checks: path shape and hash shape.
    return is_scope_local_file_name(task["input_path"]) and is_hash(task["input_hash"])


def retry_kind_from_reason(reason: str | None) -> str:
    return {
        "network_error": "NetworkError",
        "rate_limit": "RateLimit",
        "auth_error": "AuthError",
        "quota_exceeded": "QuotaExceeded",
        "invalid_input": "InvalidInput",
        "budget_exceeded": "BudgetExceeded",
    }.get(reason, "ContractViolation")


def reclaim_entry_for(task: dict, reservation_scope_id: str, adapter_kind: str) -> dict | None:
    if retry_kind_from_reason(task.get("fallback_reason")) not in {
        "RateLimit",
        "QuotaExceeded",
        "AuthError",
    }:
        return None
    if task.get("reserved_usd") is None or task.get("reserved_month") is None:
        return None
    return {
        "month": task["reserved_month"],
        "scope_id": reservation_scope_id,
        "adapter_kind": adapter_kind,
        "usd": float(task["reserved_usd"]),
    }


def append_monthly_accepts(entry: dict) -> bool:
    usd = float(entry["usd"])
    return math.isfinite(usd) and usd >= 0.0


def monthly_total(rows: list[dict], month: str, scope_id: str | None, adapter_kind: str | None) -> float:
    total = 0.0
    for row in rows:
        if row["month"] != month:
            continue
        if scope_id is not None and row["scope_id"] != scope_id:
            continue
        if adapter_kind is not None and row["adapter_kind"] != adapter_kind:
            continue
        total += float(row["usd"])
    return total


def net_monthly_spent(gross_rows: list[dict], reclaim_rows: list[dict], month: str) -> float:
    gross = monthly_total(gross_rows, month, None, None)
    reclaimed = monthly_total(reclaim_rows, month, None, None)
    net = gross - reclaimed
    if net < -1e-9:
        return max(gross, 0.0)
    return max(net, 0.0)


def main() -> None:
    month = "2026-07"
    scope = "victim-scope"
    adapter = "markdown"
    device_cap = 10.00
    next_estimate = 3.00
    gross_rows = [
        {"month": month, "scope_id": scope, "adapter_kind": adapter, "usd": 12.00},
    ]
    forged_task = {
        "task_id": "forged-orphan-rate-limit",
        "type": "markdownize",
        "input_path": "deleted.md",
        "input_hash": VALID_HASH,
        "output_ref": "online-placeholder",
        "status": "failed",
        "fallback_reason": "rate_limit",
        "reserved_usd": 9.75,
        "reserved_month": month,
    }

    print("[+] synthetic probe: no network, no credentials, no KCS store mutation")
    print(f"[+] TaskStore shape checks accept poisoned task: {task_store_all_accepts_shape(forged_task)}")
    reclaim = reclaim_entry_for(forged_task, scope, adapter)
    print("[+] reclaim_entry_for output:")
    print(json.dumps(reclaim, indent=2, sort_keys=True))
    print(f"[+] reclaim ledger finite/non-negative check accepts row: {append_monthly_accepts(reclaim)}")

    gross = monthly_total(gross_rows, month, None, None)
    net = net_monthly_spent(gross_rows, [reclaim], month)
    print(f"[+] gross spend before forged credit: ${gross:.2f}")
    print(f"[+] net spend after forged credit:  ${net:.2f}")
    print(f"[+] remaining against ${device_cap:.2f} cap: ${device_cap - net:.2f}")
    print(f"[+] next ${next_estimate:.2f} paid call allowed by net accounting: {net + next_estimate <= device_cap}")

    too_large = dict(reclaim, usd=99.0)
    fallback_net = net_monthly_spent(gross_rows, [too_large], month)
    print(f"[+] over-reclaim fallback keeps gross spend: ${fallback_net:.2f}")


if __name__ == "__main__":
    main()
