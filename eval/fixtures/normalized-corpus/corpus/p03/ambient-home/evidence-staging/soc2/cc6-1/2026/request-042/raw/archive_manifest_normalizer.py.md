```py
#!/usr/bin/env python3
"""古い証跡マニフェストを保管用の最小スキーマへ寄せる小さな補助スクリプト。

Nami Grid の Trust Engineering では、監査提出前にステージング領域から渡された
JSONL を読みやすいキー名へ整えるときだけ利用する。アップロードや削除は行わない。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ArchiveRecord:
    object_key: str
    collected_at: str
    system: str
    sha256: str
    review_state: str


def utc_timestamp(value: str) -> str:
    """入力時刻を UTC の ISO 8601 表記へそろえる。時刻がなければ失敗させる。"""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"timezone is required: {value}")
    return parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize(row: dict[str, Any]) -> ArchiveRecord:
    # 過去の export では artifact_key / object_key が混在していた。
    object_key = row.get("object_key") or row.get("artifact_key")
    if not isinstance(object_key, str) or not object_key.strip():
        raise ValueError("object_key is missing")

    digest = row.get("sha256") or row.get("checksum")
    if not isinstance(digest, str) or len(digest) != 64:
        raise ValueError(f"invalid checksum for {object_key}")

    return ArchiveRecord(
        object_key=object_key.strip(),
        collected_at=utc_timestamp(str(row["collected_at"])),
        system=str(row.get("system", "unknown")).strip().lower(),
        sha256=digest.lower(),
        review_state=str(row.get("review_state", "unreviewed")).strip().lower(),
    )


def read_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_number}: invalid JSON") from exc


def main() -> int:
    parser = argparse.ArgumentParser(description="Normalize a Nami Grid evidence manifest")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    records = [asdict(normalize(row)) for row in read_jsonl(args.source)]
    records.sort(key=lambda record: (record["system"], record["object_key"]))
    payload = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    args.output.write_text(payload, encoding="utf-8")
    print(f"normalized {len(records)} records to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
