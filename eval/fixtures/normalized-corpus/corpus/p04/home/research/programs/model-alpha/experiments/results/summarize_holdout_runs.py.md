```py
"""Summarize Cedar holdout rows without changing raw evaluator exports."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable


def mean_by_slice(rows: Iterable[dict[str, object]]) -> dict[str, float]:
    totals: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        totals[str(row["slice"])].append(float(row["value"]))
    return {name: sum(values) / len(values) for name, values in totals.items()}
```
