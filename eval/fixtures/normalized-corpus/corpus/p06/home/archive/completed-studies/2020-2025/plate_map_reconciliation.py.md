```py
from __future__ import annotations
import csv
from collections import defaultdict
from pathlib import Path

def collect_positions(path: Path) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = defaultdict(list)
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            grouped[row["sample_id"]].append(row["well"])
    return dict(grouped)

def reconcile(expected: dict[str, list[str]], observed: dict[str, list[str]]) -> list[str]:
    return [sample for sample, wells in expected.items() if observed.get(sample, []) != wells]
```
