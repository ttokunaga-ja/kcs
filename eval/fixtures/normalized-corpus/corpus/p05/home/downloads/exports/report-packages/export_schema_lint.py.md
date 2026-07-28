```py
"""配布用 CSV の列順と型を軽く確認する lint。"""

from __future__ import annotations

import csv
from pathlib import Path


REQUIRED = ["business_date", "market_code", "channel", "recognized_net_sales"]


def lint(path: Path) -> list[str]:
    with path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        errors = [f"missing column: {name}" for name in REQUIRED if name not in headers]
        for number, row in enumerate(reader, start=2):
            if row.get("business_date", "").count("-") != 2:
                errors.append(f"line {number}: invalid business_date")
            if row.get("recognized_net_sales", "") == "":
                errors.append(f"line {number}: blank recognized_net_sales")
    return errors


if __name__ == "__main__":
    candidate = Path("commercial_daily_export.csv")
    findings = lint(candidate)
    print("ok" if not findings else " | ".join(findings))
```
