```py
#!/usr/bin/env python3
"""旧Orionエクスポートの科目コードを、監査提出用の並びに寄せる小さな補助スクリプト。

2024年以前の保存ファイル向け。月次締めの正式な取込処理には使わない。
"""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path


ACCOUNT_ALIAS = {
    "610100": "611000",  # 荷役外注費（旧コード）
    "610200": "612000",  # 配送委託費（旧コード）
    "720810": "721100",  # システム利用料（旧コード）
}


def normalize_amount(value: str) -> str:
    """空欄をゼロとして扱い、比較しやすい小数表記へそろえる。"""
    try:
        return format(Decimal(value or "0"), ".2f")
    except InvalidOperation as exc:
        raise ValueError(f"金額が数値ではありません: {value!r}") from exc


def rewrite_export(source: Path, destination: Path) -> int:
    with source.open("r", encoding="utf-8-sig", newline="") as input_file, destination.open(
        "w", encoding="utf-8", newline=""
    ) as output_file:
        reader = csv.DictReader(input_file)
        writer = csv.DictWriter(
            output_file,
            fieldnames=["posting_date", "account_code", "department", "amount_jpy", "memo"],
        )
        writer.writeheader()
        rows = 0
        for row in reader:
            writer.writerow(
                {
                    "posting_date": row["posting_date"],
                    "account_code": ACCOUNT_ALIAS.get(row["account_code"], row["account_code"]),
                    "department": row.get("department", ""),
                    "amount_jpy": normalize_amount(row.get("amount_jpy", "")),
                    "memo": row.get("memo", "").strip(),
                }
            )
            rows += 1
    return rows


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="旧月次エクスポートを整形します")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    print(f"written={rewrite_export(args.source, args.destination)}")
```
