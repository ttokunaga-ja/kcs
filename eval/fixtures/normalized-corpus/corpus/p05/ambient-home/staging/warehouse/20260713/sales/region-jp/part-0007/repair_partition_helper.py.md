```py
"""遅延到着した staging partition を手元で確認する補助。"""

from __future__ import annotations

from pathlib import Path


def listed_parts(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.glob("*.parquet") if path.stat().st_size > 0)


def write_review_note(parts: list[str]) -> str:
    # 本番 publish は行わず、確認したファイル名だけを引き継ぐ。
    if not parts:
        return "no parquet parts found"
    return f"reviewed {len(parts)} late-arriving parts"


if __name__ == "__main__":
    print(write_review_note(listed_parts(Path("."))))
```
