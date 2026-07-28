```py
#!/usr/bin/env python3
"""監査提出用に受領した ZIP のハッシュ一覧を確認する。

ダウンロード直後の照合だけを目的にし、署名・暗号化・外部送信は担当しない。
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Iterable


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def package_files(root: Path) -> Iterable[Path]:
    for candidate in sorted(root.rglob("*")):
        if candidate.is_file() and candidate.name != "checksums.json":
            yield candidate


def build_manifest(root: Path) -> list[dict[str, str]]:
    return [
        {"path": item.relative_to(root).as_posix(), "sha256": sha256(item)}
        for item in package_files(root)
    ]


def compare(expected: list[dict[str, str]], actual: list[dict[str, str]]) -> list[str]:
    actual_by_path = {item["path"]: item["sha256"] for item in actual}
    differences: list[str] = []
    for item in expected:
        if actual_by_path.get(item["path"]) != item["sha256"]:
            differences.append(item["path"])
    return differences


def main() -> int:
    parser = argparse.ArgumentParser(description="Nami Grid evidence package checksum helper")
    parser.add_argument("package", type=Path)
    parser.add_argument("--verify", type=Path, help="既存の JSON マニフェストと比較する")
    options = parser.parse_args()

    current = build_manifest(options.package)
    if options.verify:
        expected = json.loads(options.verify.read_text(encoding="utf-8"))
        mismatches = compare(expected, current)
        if mismatches:
            print("照合不一致:", ", ".join(mismatches))
            return 2
        print(f"照合済み: {len(current)} ファイル")
        return 0

    print(json.dumps(current, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
