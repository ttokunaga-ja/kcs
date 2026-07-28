```py
#!/usr/bin/env python3
"""完了済み評価の担当者向けエクスポートを整形する。

監査用の正式パッケージを生成するものではなく、四半期レビューで閉じた評価を
Trust Engineering が見返すための CSV を作る用途に限定している。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class ClosedAssessment:
    assessment_id: str
    service: str
    owner: str
    closed_on: str
    disposition: str
    evidence_location: str


def to_record(raw: dict[str, Any]) -> ClosedAssessment:
    required = ("assessment_id", "service", "owner", "closed_on", "disposition")
    missing = [key for key in required if not raw.get(key)]
    if missing:
        raise ValueError(f"assessment record missing: {', '.join(missing)}")
    return ClosedAssessment(
        assessment_id=str(raw["assessment_id"]),
        service=str(raw["service"]),
        owner=str(raw["owner"]),
        closed_on=str(raw["closed_on"]),
        disposition=str(raw["disposition"]),
        evidence_location=str(raw.get("evidence_location", "")),
    )


def load_records(path: Path) -> Iterable[ClosedAssessment]:
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            yield to_record(json.loads(line))
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{line_no}: JSON を読めません") from exc


def write_csv(records: Iterable[ClosedAssessment], output: Path) -> None:
    rows = sorted(records, key=lambda row: (row.closed_on, row.assessment_id))
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ClosedAssessment.__dataclass_fields__))
        writer.writeheader()
        writer.writerows(row.__dict__ for row in rows)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="closed assessment export")
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    options = parser.parse_args()
    write_csv(load_records(options.input), options.output)
```
