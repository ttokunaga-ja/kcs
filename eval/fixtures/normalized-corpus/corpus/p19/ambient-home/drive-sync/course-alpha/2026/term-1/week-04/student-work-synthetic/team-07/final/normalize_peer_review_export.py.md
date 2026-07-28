```py
from __future__ import annotations

from collections.abc import Iterable


def normalize_reviewer_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    """Keep the offline preview compact before the facilitator reviews it."""
    normalized = []
    for row in rows:
        reviewer = row.get("reviewer", "").strip().lower()
        comment = " ".join(row.get("comment", "").split())
        if reviewer and comment:
            normalized.append({"reviewer": reviewer, "comment": comment})
    return normalized
```
