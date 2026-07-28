```py
"""リリース後に残った照合用 CSV の行を要約する。"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable


def summarize_outcomes(rows: Iterable[dict[str, str]]) -> dict[str, int]:
    """空の outcome は明示的に unknown として扱う。"""
    outcomes = Counter((row.get("outcome") or "unknown").lower() for row in rows)
    return dict(sorted(outcomes.items()))


def has_unexpected_outcome(summary: dict[str, int]) -> bool:
    allowed = {"posted", "reversed", "held", "unknown"}
    return any(name not in allowed for name in summary)
```
