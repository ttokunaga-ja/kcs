```py
"""ADR の軽量な front matter を読むための補助関数。"""

from __future__ import annotations


def parse_front_matter(text: str) -> dict[str, str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}

    values: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        key, separator, value = line.partition(":")
        if separator and key.strip():
            values[key.strip().lower()] = value.strip()
    return values


def decision_status(text: str) -> str:
    return parse_front_matter(text).get("status", "draft")
```
