```py
"""古い ATS エクスポートの照合に残した小さな補助関数。"""

from __future__ import annotations

from collections.abc import Iterable


def normalize_stage(value: str) -> str:
    """ローカル比較の前に旧ステージ表記をそろえる。"""
    aliases = {
        "panel_2": "round-2",
        "r2": "round-2",
        "references": "reference-check",
    }
    return aliases.get(value.strip().lower(), value.strip().lower())


def missing_fields(rows: Iterable[dict[str, str]]) -> list[str]:
    """同意取得時刻がない候補者エイリアスを返す。"""
    return [row.get("candidate_alias", "unknown") for row in rows if not row.get("consent_at")]


if __name__ == "__main__":
    print("保存済みの照合ノートから使う。ネットワーク接続は行わない。")
```
