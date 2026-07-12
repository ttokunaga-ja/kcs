#!/usr/bin/env python3
"""Offline model of the KCS secret-hold terminal-failure revival.

The script does not import KCS, call an embedding provider, read credentials, or
touch a real repository. It models only the task fields changed by the vulnerable
state transitions at revision 0e19f3c6489da458e93a982a333c308d92d0a0ae.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Optional


SECRETS_TIER_B_HOLD = "secrets_tier_b_hold"


@dataclass
class Task:
    status: str
    fallback_reason: Optional[str]
    attempts: int
    next_retry_at: Optional[str]
    input_path: str
    output_ref: str = "embedding:chunk:demo"


RETRY_POLICY = {
    "network_error": (True, 5),
    "rate_limit": (True, None),
    "auth_error": (False, 0),
    "quota_exceeded": (True, 3),
    "invalid_input": (False, 0),
    "contract_violation": (False, 0),
    "budget_exceeded": (False, 0),
}


def retry_allowed(task: Task) -> bool:
    retryable, max_attempts = RETRY_POLICY.get(
        task.fallback_reason or "contract_violation",
        RETRY_POLICY["contract_violation"],
    )
    return retryable and (max_attempts is None or task.attempts < max_attempts)


def embeddable_task_state(task: Task) -> bool:
    if task.status == "Paused" and task.fallback_reason == SECRETS_TIER_B_HOLD:
        return False
    if task.status == "Failed":
        return task.next_retry_at is None and retry_allowed(task)
    return True


def vulnerable_secret_hold(task: Task, current_secret_path: str) -> Task:
    # Matches the vulnerable demotion class: non-Done, non-retired, not already held.
    if task.status == "Done" or task.fallback_reason == "retired_non_live":
        return task
    if task.status == "Paused" and task.fallback_reason == SECRETS_TIER_B_HOLD:
        return task
    return replace(
        task,
        status="Paused",
        fallback_reason=SECRETS_TIER_B_HOLD,
        input_path=current_secret_path,
        attempts=0,
        next_retry_at=None,
    )


def vulnerable_unhold(task: Task, current_plain_path: str) -> Task:
    if task.status == "Paused" and task.fallback_reason == SECRETS_TIER_B_HOLD:
        return replace(
            task,
            status="Pending",
            fallback_reason="ready_for_online_adapter",
            input_path=current_plain_path,
            attempts=0,
            next_retry_at=None,
        )
    return task


def fixed_secret_hold_excludes_terminal(task: Task, current_secret_path: str) -> Task:
    # One minimal safe invariant: secret classification must not erase a terminal
    # or exhausted retry decision. A fuller production fix can preserve and restore
    # the pre-hold fields instead.
    if task.status == "Failed" and not retry_allowed(task):
        return task
    return vulnerable_secret_hold(task, current_secret_path)


def summarize(label: str, task: Task) -> None:
    print(
        f"{label}: status={task.status} reason={task.fallback_reason} "
        f"attempts={task.attempts} retry_allowed={retry_allowed(task)} "
        f"sendable={embeddable_task_state(task)} path={task.input_path}"
    )


def main() -> int:
    terminal = Task(
        status="Failed",
        fallback_reason="contract_violation",
        attempts=1,
        next_retry_at=None,
        input_path="notes.md",
    )
    summarize("[setup] terminal failure", terminal)

    held = vulnerable_secret_hold(terminal, "credentials_backup.md")
    summarize("[vulnerable] after secret hold", held)

    revived = vulnerable_unhold(held, "notes.md")
    summarize("[vulnerable] after non-secret unhold", revived)

    synthetic_usd = 0.0000031125
    would_send = embeddable_task_state(revived)
    print(
        "[vulnerable] synthetic adapter path: "
        f"reserve_usd={synthetic_usd:.10f} network_used=False call_would_run={would_send}"
    )

    fixed_held = fixed_secret_hold_excludes_terminal(terminal, "credentials_backup.md")
    fixed_released = vulnerable_unhold(fixed_held, "notes.md")
    summarize("[fixed] after classification cycle", fixed_released)

    assert terminal.status == "Failed" and not embeddable_task_state(terminal)
    assert held.status == "Paused" and held.fallback_reason == SECRETS_TIER_B_HOLD
    assert revived.status == "Pending" and embeddable_task_state(revived)
    assert fixed_released.status == "Failed" and not embeddable_task_state(fixed_released)

    print(
        "[result] vulnerable_revives_terminal_failure=True "
        "fixed_blocks_revival=True"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
