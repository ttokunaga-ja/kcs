```py
"""Archive a concise, human-readable Cedar run summary."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunSummary:
    package: str
    collection_revision: str
    status: str


def render(summary: RunSummary) -> str:
    return f"{summary.package} on {summary.collection_revision}: {summary.status}"
```
