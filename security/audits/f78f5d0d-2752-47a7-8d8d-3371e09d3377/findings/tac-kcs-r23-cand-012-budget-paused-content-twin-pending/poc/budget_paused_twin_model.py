#!/usr/bin/env python3
"""Model KCS budget-paused content-twin task reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Dict, Iterable, Set


DONE = "Done"
PAUSED = "Paused"
BUDGET_EXCEEDED = "budget_exceeded"
SECRETS_HOLD = "secrets_tier_b_hold"


@dataclass
class Chunk:
    name: str
    raw_bytes: bytes

    @property
    def normalized_text(self) -> str:
        text = self.raw_bytes.decode("utf-8")
        return text.removeprefix("\ufeff").strip()

    @property
    def text_hash(self) -> str:
        return sha256(self.normalized_text.encode("utf-8")).hexdigest()


@dataclass
class Task:
    chunk_name: str
    status: str
    fallback_reason: str | None


def held_secret_embedding_chunk_ids(tasks: Iterable[Task]) -> Set[str]:
    return {
        task.chunk_name
        for task in tasks
        if task.status == PAUSED and task.fallback_reason == SECRETS_HOLD
    }


def rebuild_chunk_vec(
    chunks: Dict[str, Chunk],
    embeddings_by_text_hash: Set[str],
    held_chunk_ids: Set[str],
) -> Set[str]:
    linked: Set[str] = set()
    for chunk in chunks.values():
        if chunk.name in held_chunk_ids:
            continue
        if chunk.text_hash in embeddings_by_text_hash:
            linked.add(chunk.name)
    return linked


def pending_chunk_ids(chunks: Dict[str, Chunk], chunk_vec: Set[str], embeddings_by_text_hash: Set[str]) -> Set[str]:
    pending: Set[str] = set()
    for chunk in chunks.values():
        has_current_profile = chunk.text_hash in embeddings_by_text_hash
        if has_current_profile and chunk.name in chunk_vec:
            continue
        pending.add(chunk.name)
    return pending


def reconcile_vulnerable(tasks: Iterable[Task], live_ids: Set[str], pending_ids: Set[str]) -> Dict[str, Task]:
    result: Dict[str, Task] = {}
    for task in tasks:
        next_task = Task(task.chunk_name, task.status, task.fallback_reason)
        if task.status not in {PAUSED, "Pending", "Running"}:
            result[task.chunk_name] = next_task
            continue
        if task.chunk_name in pending_ids:
            result[task.chunk_name] = next_task
            continue
        if task.chunk_name not in live_ids:
            next_task.status = DONE
            next_task.fallback_reason = "retired_non_live"
        elif task.status == PAUSED:
            # Vulnerable behavior: all pause reasons are treated like secrets holds.
            pass
        else:
            next_task.status = DONE
            next_task.fallback_reason = "embedding_adapter_done"
        result[task.chunk_name] = next_task
    return result


def reconcile_fixed(tasks: Iterable[Task], live_ids: Set[str], pending_ids: Set[str]) -> Dict[str, Task]:
    result: Dict[str, Task] = {}
    for task in tasks:
        next_task = Task(task.chunk_name, task.status, task.fallback_reason)
        if task.status not in {PAUSED, "Pending", "Running"}:
            result[task.chunk_name] = next_task
            continue
        if task.chunk_name in pending_ids:
            result[task.chunk_name] = next_task
            continue
        if task.chunk_name not in live_ids:
            next_task.status = DONE
            next_task.fallback_reason = "retired_non_live"
        elif task.status == PAUSED and task.fallback_reason == SECRETS_HOLD:
            # Correct negative control: a secrets hold was never approved for sending.
            pass
        else:
            next_task.status = DONE
            next_task.fallback_reason = "embedding_adapter_done"
        result[task.chunk_name] = next_task
    return result


def index_status(tasks: Iterable[Task]) -> tuple[float, int, bool]:
    total = 0
    done = 0
    pending = 0
    budget_paused = False
    for task in tasks:
        total += 1
        if task.status == DONE:
            done += 1
        elif task.status == PAUSED:
            pending += 1
            if task.fallback_reason == BUDGET_EXCEEDED:
                budget_paused = True
        else:
            pending += 1
    return done / total if total else 1.0, pending, budget_paused


def main() -> None:
    chunks = {
        "alpha.md": Chunk("alpha.md", b"\xef\xbb\xbfhello\n"),
        "beta.md": Chunk("beta.md", b"hello\n"),
    }
    assert chunks["alpha.md"].raw_bytes != chunks["beta.md"].raw_bytes
    assert chunks["alpha.md"].text_hash == chunks["beta.md"].text_hash

    first_pass_tasks = [
        Task("alpha.md", PAUSED, BUDGET_EXCEEDED),
        Task("beta.md", DONE, "embedding_adapter_done"),
    ]

    embeddings_by_text_hash = {chunks["beta.md"].text_hash}
    held = held_secret_embedding_chunk_ids(first_pass_tasks)
    chunk_vec = rebuild_chunk_vec(chunks, embeddings_by_text_hash, held)
    pending = pending_chunk_ids(chunks, chunk_vec, embeddings_by_text_hash)
    live_ids = set(chunks)

    vulnerable = reconcile_vulnerable(first_pass_tasks, live_ids, pending)
    fixed = reconcile_fixed(first_pass_tasks, live_ids, pending)

    vulnerable_status = index_status(vulnerable.values())
    fixed_status = index_status(fixed.values())

    assert "alpha.md" in chunk_vec
    assert "beta.md" in chunk_vec
    assert vulnerable["alpha.md"].status == PAUSED
    assert vulnerable_status == (0.5, 1, True)
    assert fixed["alpha.md"].status == DONE
    assert fixed_status == (1.0, 0, False)

    secret_task = Task("alpha.md", PAUSED, SECRETS_HOLD)
    secret_fixed = reconcile_fixed([secret_task], live_ids, set())
    assert secret_fixed["alpha.md"].status == PAUSED

    short_hash = chunks["alpha.md"].text_hash[:12]
    print("[+] first twin paused: alpha.md -> Paused(budget_exceeded)")
    print(f"[+] second twin embedded: beta.md shares text_hash {short_hash}...")
    print(f"[+] rebuild linked chunk_vec for: {', '.join(sorted(chunk_vec))}")
    print(
        "[+] vulnerable index_status: "
        f"enriched_ratio={vulnerable_status[0]:.2f} "
        f"pending_enrichment_tasks={vulnerable_status[1]} "
        f"budget_paused={vulnerable_status[2]}"
    )
    print(
        "[+] fixed index_status: "
        f"enriched_ratio={fixed_status[0]:.2f} "
        f"pending_enrichment_tasks={fixed_status[1]} "
        f"budget_paused={fixed_status[2]}"
    )
    print("[+] secrets hold negative control remains Paused(secrets_tier_b_hold)")


if __name__ == "__main__":
    main()
