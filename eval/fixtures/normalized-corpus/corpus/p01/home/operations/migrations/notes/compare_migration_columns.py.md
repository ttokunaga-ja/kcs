```py
"""移行前後のカラム一覧を比べ、説明が必要な差分を返す。"""

from __future__ import annotations

from collections.abc import Iterable


def normalized_columns(columns: Iterable[str]) -> set[str]:
    return {column.strip().lower() for column in columns if column.strip()}


def compare_columns(before: Iterable[str], after: Iterable[str]) -> dict[str, list[str]]:
    old = normalized_columns(before)
    new = normalized_columns(after)
    return {
        "added": sorted(new - old),
        "removed": sorted(old - new),
        "retained": sorted(old & new),
    }


def requires_review(diff: dict[str, list[str]]) -> bool:
    return bool(diff["removed"] or {"amount", "currency"} & set(diff["added"]))
```
