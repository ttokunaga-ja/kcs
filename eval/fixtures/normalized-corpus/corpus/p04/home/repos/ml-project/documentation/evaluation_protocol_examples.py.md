```py
"""Examples used in the Cedar ranking-evaluation protocol."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReviewSlice:
    name: str
    collection_revision: str
    duplicate_suppression: bool


def is_comparable(left: ReviewSlice, right: ReviewSlice) -> bool:
    return (
        left.collection_revision == right.collection_revision
        and left.duplicate_suppression == right.duplicate_suppression
    )
```
