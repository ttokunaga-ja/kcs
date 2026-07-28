```py
#!/usr/bin/env python3
"""Orion ERPの総勘定元帳CSVを月次レビュー用に正規化する。"""

from __future__ import annotations

import csv
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path


REQUIRED_COLUMNS = {"伝票日付", "伝票番号", "勘定科目", "部門", "借方", "貸方", "摘要"}


def parse_jpy(value: str) -> int:
    return int((value or "0").replace(",", "").strip() or "0")


def normalize(rows: Iterable[dict[str, str]]) -> Iterable[dict[str, str | int]]:
    for row in rows:
        if not REQUIRED_COLUMNS.issubset(row):
            missing = ", ".join(sorted(REQUIRED_COLUMNS - set(row)))
            raise ValueError(f"必須列がありません: {missing}")
        debit = parse_jpy(row["借方"])
        credit = parse_jpy(row["貸方"])
        yield {
            "posting_date": datetime.strptime(row["伝票日付"], "%Y/%m/%d").date().isoformat(),
            "journal_id": row["伝票番号"].strip(),
            "account": row["勘定科目"].strip(),
            "department": row["部門"].strip(),
            "amount_jpy": debit - credit,
            "description": " ".join(row["摘要"].split()),
        }


def convert(source: Path, destination: Path) -> None:
    with source.open(encoding="cp932", newline="") as input_file, destination.open(
        "w", encoding="utf-8", newline=""
    ) as output_file:
        reader = csv.DictReader(input_file)
        writer = csv.DictWriter(
            output_file,
            fieldnames=["posting_date", "journal_id", "account", "department", "amount_jpy", "description"],
        )
        writer.writeheader()
        writer.writerows(normalize(reader))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    options = parser.parse_args()
    convert(options.source, options.destination)
```
