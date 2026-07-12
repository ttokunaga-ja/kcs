#!/usr/bin/env python3
"""Offline model of KCS-R23-CAND-013.

The model keeps only the fields needed to demonstrate the policy bypass:
`batch retry` leaves AuthError failed, vulnerable embedding reconciliation
revives it anyway, and the task then reaches a mock adapter send.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


AUTH_ERROR = "auth_error"
DONE_REASON = "embedding_adapter_done"


@dataclass
class Task:
    task_type: str
    output_ref: str
    status: str
    fallback_reason: str | None
    attempts: int


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    text: str


def retry_policy(reason: str | None) -> tuple[bool, int | None]:
    if reason == AUTH_ERROR:
        return False, 0
    if reason == "network_error":
        return True, 5
    if reason == "rate_limit":
        return True, None
    return False, 0


def task_retry_allowed(task: Task) -> bool:
    retryable, max_attempts = retry_policy(task.fallback_reason)
    return retryable and (max_attempts is None or task.attempts < max_attempts)


def batch_retry_outer_scheduler(tasks: Iterable[Task]) -> int:
    changed = 0
    for task in tasks:
        if task.status == "Failed" and task_retry_allowed(task):
            task.status = "Pending"
            changed += 1
    return changed


def vulnerable_embedding_reconcile(
    tasks: Iterable[Task], live_ids: set[str], pending_ids: set[str]
) -> int:
    changed = 0
    for task in tasks:
        if task.task_type != "Embedding":
            continue
        chunk_id = task.output_ref.removeprefix("embedding:")
        live = chunk_id in live_ids
        live_embedded = live and chunk_id not in pending_ids
        if live and not live_embedded and task.status == "Failed" and task.fallback_reason == AUTH_ERROR:
            task.status = "Pending"
            task.fallback_reason = None
            task.attempts = 0
            changed += 1
    return changed


def fixed_embedding_reconcile(
    tasks: Iterable[Task],
    live_ids: set[str],
    pending_ids: set[str],
    allow_auth_revive: bool,
) -> int:
    if not allow_auth_revive:
        return 0
    return vulnerable_embedding_reconcile(tasks, live_ids, pending_ids)


def embeddable_task_state(task: Task) -> bool:
    if task.status == "Failed":
        return task_retry_allowed(task)
    return task.status != "Paused"


def filter_embeddable_by_task_state(tasks: list[Task], chunks: list[Chunk]) -> list[Chunk]:
    by_ref = {task.output_ref: task for task in tasks if task.task_type == "Embedding"}
    allowed: list[Chunk] = []
    for chunk in chunks:
        task = by_ref.get(f"embedding:{chunk.chunk_id}")
        if task is None or embeddable_task_state(task):
            allowed.append(chunk)
    return allowed


def send_embed_batch(tasks: list[Task], chunks: list[Chunk]) -> list[str]:
    sent = [chunk.chunk_id for chunk in chunks]
    sent_refs = {f"embedding:{chunk_id}" for chunk_id in sent}
    for task in tasks:
        if task.output_ref in sent_refs:
            task.status = "Done"
            task.fallback_reason = DONE_REASON
    return sent


def initial_state() -> tuple[list[Task], list[Chunk], set[str], set[str]]:
    chunks = [Chunk("approved-chunk-1", "previously approved text")]
    tasks = [
        Task(
            task_type="Embedding",
            output_ref="embedding:approved-chunk-1",
            status="Failed",
            fallback_reason=AUTH_ERROR,
            attempts=1,
        )
    ]
    live_ids = {"approved-chunk-1"}
    pending_ids = {"approved-chunk-1"}  # live chunk has no committed vector yet
    return tasks, chunks, live_ids, pending_ids


def run_vulnerable_retry() -> tuple[int, int, list[str], Task]:
    tasks, chunks, live_ids, pending_ids = initial_state()
    changed = batch_retry_outer_scheduler(tasks)
    revived = vulnerable_embedding_reconcile(tasks, live_ids, pending_ids)
    embeddable = filter_embeddable_by_task_state(tasks, chunks)
    sent = send_embed_batch(tasks, embeddable)
    return changed, revived, sent, tasks[0]


def run_fixed(allow_auth_revive: bool) -> tuple[int, list[str], Task]:
    tasks, chunks, live_ids, pending_ids = initial_state()
    batch_retry_outer_scheduler(tasks)
    revived = fixed_embedding_reconcile(tasks, live_ids, pending_ids, allow_auth_revive)
    embeddable = filter_embeddable_by_task_state(tasks, chunks)
    sent = send_embed_batch(tasks, embeddable)
    return revived, sent, tasks[0]


def main() -> None:
    print("[setup] live embedding task starts as Failed(auth_error), attempts=1")

    changed, revived, sent, task = run_vulnerable_retry()
    print(f"[retry] outer retry scheduler changed {changed} task(s)")
    print(
        f"[vulnerable] reconciliation changed {revived} task(s) "
        "without an auth-revival gate"
    )
    print(f"[vulnerable] adapter mock sent {len(sent)} chunk(s): {', '.join(sent)}")
    print(
        f"[vulnerable] final task: {task.status}({task.fallback_reason}), "
        f"attempts={task.attempts}"
    )

    assert changed == 0
    assert revived == 1
    assert sent == ["approved-chunk-1"]
    assert task.status == "Done"
    assert task.fallback_reason == DONE_REASON
    assert task.attempts == 0

    fixed_retry_revived, fixed_retry_sent, fixed_retry_task = run_fixed(False)
    print(
        "[fixed retry] reconciliation changed "
        f"{fixed_retry_revived} task(s); sent {len(fixed_retry_sent)} chunk(s); "
        f"task stays {fixed_retry_task.status}({fixed_retry_task.fallback_reason})"
    )
    assert fixed_retry_revived == 0
    assert fixed_retry_sent == []
    assert fixed_retry_task.status == "Failed"
    assert fixed_retry_task.fallback_reason == AUTH_ERROR

    fixed_resume_revived, fixed_resume_sent, fixed_resume_task = run_fixed(True)
    print(
        "[fixed resume] reconciliation changed "
        f"{fixed_resume_revived} task(s); sent {len(fixed_resume_sent)} chunk(s); "
        f"task becomes {fixed_resume_task.status}({fixed_resume_task.fallback_reason})"
    )
    assert fixed_resume_revived == 1
    assert fixed_resume_sent == ["approved-chunk-1"]
    assert fixed_resume_task.status == "Done"
    assert fixed_resume_task.fallback_reason == DONE_REASON

    print("[ok] vulnerable retry revival and fixed retry/resume split reproduced offline")


if __name__ == "__main__":
    main()
