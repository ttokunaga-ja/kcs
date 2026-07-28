```py
from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path


THEME_ALIASES = {
    "担当が決まらない": "担当未定",
    "オーナー不明": "担当未定",
    "文脈が散る": "前提不足",
    "履歴が見つからない": "前提不足",
    "通知を見逃す": "更新通知",
}


def canonical_theme(value: str) -> str:
    """表現の揺れを、readout 用のテーマ名にまとめる。"""
    label = value.strip()
    return THEME_ALIASES.get(label, label or "未分類")


def summarize(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    counts: Counter[str] = Counter()
    examples: dict[str, list[str]] = defaultdict(list)
    for row in rows:
        theme = canonical_theme(row.get("theme", ""))
        counts[theme] += 1
        quote = row.get("note", "").strip()
        if quote and len(examples[theme]) < 2:
            examples[theme].append(quote)
    return {
        theme: {"mentions": counts[theme], "examples": examples[theme]}
        for theme in counts
    }


def load_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: interview_theme_rollup.py INTERVIEW_EXPORT.csv")
    print(json.dumps(summarize(load_rows(Path(sys.argv[1]))), ensure_ascii=False, indent=2))
```
