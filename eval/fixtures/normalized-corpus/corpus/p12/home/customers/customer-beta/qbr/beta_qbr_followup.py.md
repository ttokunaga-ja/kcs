```py
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class FollowUp:
    title: str
    owner: str
    due_on: date
    status: str


def read_followups(path: Path) -> list[FollowUp]:
    """QBRで確認した対応一覧を読み込み、日付で扱える形にする。"""
    records = json.loads(path.read_text(encoding="utf-8"))
    return [
        FollowUp(
            title=record["title"],
            owner=record["owner"],
            due_on=date.fromisoformat(record["due_on"]),
            status=record["status"],
        )
        for record in records
    ]


def render_markdown(items: list[FollowUp], today: date) -> str:
    """完了以外の対応を期限順に並べ、定例用の表にする。"""
    remaining = sorted(
        (item for item in items if item.status != "done"),
        key=lambda item: (item.due_on, item.owner, item.title),
    )
    rows = ["| 対応 | 担当 | 期限 | 状態 |", "|---|---|---|---|"]
    for item in remaining:
        marker = "期限確認" if item.due_on <= today else item.status
        rows.append(f"| {item.title} | {item.owner} | {item.due_on.isoformat()} | {marker} |")
    return "\n".join(rows) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Customer Beta QBRの継続対応を整形する")
    parser.add_argument("input", type=Path, help="対応一覧のJSONファイル")
    parser.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = parser.parse_args()

    print(render_markdown(read_followups(args.input), args.as_of), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
