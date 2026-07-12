#!/usr/bin/env python3
"""Safe local model for KCS-R23-CAND-067.

The real bug is the absence of a current ignore/membership predicate before an
unchanged persisted OCR task is sent. This script uses only synthetic metadata
and bytes; it never calls KCS, reads real user documents, uses credentials, or
opens a network connection.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


SEND = "Send"
RETIRE = "Retire"


@dataclass(frozen=True)
class Task:
    input_path: str
    input_hash: str
    status: str = "Pending"
    task_type: str = "Markdownize"
    output_ref: str = "online:mistral"


def digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def ignored_by_current_policy(path: str, ignore_patterns: set[str]) -> bool:
    return path in ignore_patterns


def classify_secret(path: str) -> bool:
    secret_markers = ("secret", "token", "credential", "private-key")
    lowered = path.lower()
    return any(marker in lowered for marker in secret_markers)


def locally_preparable_for_ocr(media_type: str, data: bytes) -> bool:
    return media_type == "application/pdf" and data.startswith(b"%PDF-")


def vulnerable_gate(
    task: Task,
    current_files: dict[str, bytes],
    media_type: str,
    secrets_approved: bool,
    max_input_bytes: int,
) -> str:
    """Model the vulnerable send gate.

    This intentionally mirrors the missing predicate: it verifies lifecycle,
    type, filename secret status, current bytes, size, and media suitability,
    but it never checks whether the current scan would still include the path.
    """

    if task.status != "Pending" or task.task_type != "Markdownize":
        return RETIRE
    if not secrets_approved and classify_secret(task.input_path):
        return RETIRE
    data = current_files.get(task.input_path)
    if data is None or digest(data) != task.input_hash:
        return RETIRE
    if len(data) > max_input_bytes:
        return RETIRE
    if not locally_preparable_for_ocr(media_type, data):
        return RETIRE
    return SEND


def fixed_gate(
    task: Task,
    current_files: dict[str, bytes],
    media_type: str,
    secrets_approved: bool,
    max_input_bytes: int,
    ignore_patterns: set[str],
) -> str:
    if ignored_by_current_policy(task.input_path, ignore_patterns):
        return RETIRE
    return vulnerable_gate(
        task,
        current_files,
        media_type,
        secrets_approved,
        max_input_bytes,
    )


def main() -> None:
    document_path = "private-plan.pdf"
    document = b"%PDF-1.7\nsynthetic local OCR fixture\n%%EOF\n"
    current_files = {document_path: document}
    task = Task(input_path=document_path, input_hash=digest(document))
    ignore_patterns = {document_path}

    print(f"[+] created synthetic OCR-eligible task for {document_path}")
    print(f"[+] current ignore policy excludes {document_path}")

    vulnerable = vulnerable_gate(
        task,
        current_files,
        media_type="application/pdf",
        secrets_approved=False,
        max_input_bytes=1024 * 1024,
    )
    fixed = fixed_gate(
        task,
        current_files,
        media_type="application/pdf",
        secrets_approved=False,
        max_input_bytes=1024 * 1024,
        ignore_patterns=ignore_patterns,
    )

    print(f"[+] vulnerable gate decision: {vulnerable}")
    print(f"[+] fixed gate decision: {fixed}")

    assert vulnerable == SEND, "model should reproduce the stale authorization send"
    assert fixed == RETIRE, "fixed gate should retire the now-ignored task"
    print("[+] regression expectation satisfied without network or credentials")


if __name__ == "__main__":
    main()
