```py
"""Build a compact index for exported Cedar review reports."""

from __future__ import annotations

from pathlib import Path


def report_index(report_dir: Path) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for path in sorted(report_dir.glob("*.json")):
        entries.append({"name": path.name, "kind": "metric-export"})
    return entries
```
