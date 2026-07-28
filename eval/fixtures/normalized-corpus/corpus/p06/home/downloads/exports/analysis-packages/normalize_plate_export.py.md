```py
from __future__ import annotations
import csv
from pathlib import Path

REQUIRED = {"well", "sample_id", "signal_au", "cycle"}

def normalize(source: Path, target: Path) -> int:
    with source.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or not REQUIRED.issubset(rows[0]):
        raise ValueError("missing required assay columns")
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["well", "sample_id", "cycle", "signal_au"])
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)
```
