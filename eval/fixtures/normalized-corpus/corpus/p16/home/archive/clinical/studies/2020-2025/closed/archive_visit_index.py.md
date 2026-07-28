```py
#!/usr/bin/env python3
"""Build a small, de-identified lookup index for completed renal-study visits.

This helper was retained with the 2020–2025 closeout material so the archive
coordinator can locate a visit packet without reopening the retired EDC export.
It deliberately accepts study tokens only; names, medical record numbers, and
free-text notes are excluded from the archive index.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


REQUIRED_COLUMNS = {
    "study_code",
    "site_code",
    "subject_token",
    "visit_label",
    "visit_date",
    "packet_status",
}


@dataclass(frozen=True)
class ArchivedVisit:
    study_code: str
    site_code: str
    subject_token: str
    visit_label: str
    visit_date: str
    packet_status: str

    @classmethod
    def from_row(cls, row: dict[str, str]) -> "ArchivedVisit":
        missing = [column for column in REQUIRED_COLUMNS if not row.get(column, "").strip()]
        if missing:
            raise ValueError(f"row is missing required values: {', '.join(sorted(missing))}")
        return cls(**{column: row[column].strip() for column in REQUIRED_COLUMNS})


def read_visits(source: Path) -> Iterable[ArchivedVisit]:
    with source.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not REQUIRED_COLUMNS.issubset(reader.fieldnames):
            raise ValueError("source is not a completed-visit register")
        for row in reader:
            yield ArchivedVisit.from_row(row)


def build_index(visits: Iterable[ArchivedVisit]) -> dict[str, object]:
    by_study: dict[str, list[dict[str, str]]] = defaultdict(list)
    for visit in visits:
        by_study[visit.study_code].append(
            {
                "site": visit.site_code,
                "subject_token": visit.subject_token,
                "visit": visit.visit_label,
                "date": visit.visit_date,
                "packet": visit.packet_status,
            }
        )

    for records in by_study.values():
        records.sort(key=lambda record: (record["date"], record["site"], record["subject_token"]))

    return {
        "index_purpose": "closed-study visit packet lookup",
        "data_classification": "de-identified operational index",
        "studies": dict(sorted(by_study.items())),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="CSV completed-visit register")
    parser.add_argument("target", type=Path, help="JSON path for the archive index")
    args = parser.parse_args()

    payload = build_index(read_visits(args.source))
    args.target.parent.mkdir(parents=True, exist_ok=True)
    args.target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
