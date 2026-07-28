```py
from __future__ import annotations

import csv
import re
from collections.abc import Iterable


LABELS = {
    "handoff": "担当引継ぎ",
    "owner unknown": "担当未定",
    "missing context": "前提不足",
    "follow up": "要フォロー",
}


def normalize_label(value: str) -> str:
    """会議メモに混ざる旧ラベルを表示用の語彙へ寄せる。"""
    compact = re.sub(r"\s+", " ", value.strip().lower())
    return LABELS.get(compact, value.strip())


def tidy_rows(rows: Iterable[dict[str, str]]) -> list[dict[str, str]]:
    cleaned: list[dict[str, str]] = []
    for row in rows:
        message = re.sub(r"\s+", " ", row.get("message", "").strip())
        if not message:
            continue
        cleaned.append(
            {
                "posted_at": row.get("posted_at", "").strip(),
                "speaker": row.get("speaker", "").strip(),
                "label": normalize_label(row.get("label", "")),
                "message": message,
            }
        )
    return cleaned


def write_csv(rows: Iterable[dict[str, str]], destination: str) -> None:
    fields = ["posted_at", "speaker", "label", "message"]
    with open(destination, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(tidy_rows(rows))
```
