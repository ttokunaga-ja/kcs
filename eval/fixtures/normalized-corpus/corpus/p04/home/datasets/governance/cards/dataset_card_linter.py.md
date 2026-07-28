```py
"""Small checks for Cedar dataset-card handoffs."""

from __future__ import annotations

import json
from pathlib import Path


REQUIRED_FIELDS = {"name", "collection_revision", "owner", "refresh_policy"}


def validate_card(path: Path) -> list[str]:
    card = json.loads(path.read_text(encoding="utf-8"))
    missing = sorted(REQUIRED_FIELDS - card.keys())
    issues = [f"missing field: {field}" for field in missing]
    if card.get("owner") != "Applied Foundations":
        issues.append("owner must be Applied Foundations for Cedar review cards")
    return issues
```
