```py
#!/usr/bin/env python3
"""インシデント資料の参照可能性を点検するための読み取り専用ツール。

完了済みの事象について、チケット・タイムライン・検知抜粋の参照先がそろっているかを
確認する。資料の削除、移動、外部共有はこのスクリプトでは行わない。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class IncidentRecord:
    incident_id: str
    status: str
    ticket_url: str
    timeline_uri: str
    detection_export_uri: str


def parse_record(raw: dict[str, Any]) -> IncidentRecord:
    required = ("incident_id", "status", "ticket_url", "timeline_uri", "detection_export_uri")
    missing = [field for field in required if not str(raw.get(field, "")).strip()]
    if missing:
        raise ValueError(f"missing fields: {', '.join(missing)}")
    return IncidentRecord(**{field: str(raw[field]).strip() for field in required})


def audit(record: IncidentRecord) -> list[str]:
    issues: list[str] = []
    if record.status not in {"closed", "resolved", "monitoring"}:
        issues.append("状態が完了系ではありません")
    if not record.ticket_url.startswith("https://"):
        issues.append("チケット参照先が HTTPS ではありません")
    if not record.timeline_uri.startswith(("s3://", "https://")):
        issues.append("タイムラインの参照先が不正です")
    if not record.detection_export_uri.startswith(("s3://", "https://")):
        issues.append("検知抜粋の参照先が不正です")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser(description="incident evidence reference audit")
    parser.add_argument("input", type=Path, help="1 行 1 レコードの JSONL")
    options = parser.parse_args()

    failures = 0
    for number, line in enumerate(options.input.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        record = parse_record(json.loads(line))
        issues = audit(record)
        if issues:
            failures += 1
            print(f"{number} {record.incident_id}: {'; '.join(issues)}")

    if failures:
        print(f"要確認: {failures} 件")
        return 1
    print("参照先の点検が完了しました")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
