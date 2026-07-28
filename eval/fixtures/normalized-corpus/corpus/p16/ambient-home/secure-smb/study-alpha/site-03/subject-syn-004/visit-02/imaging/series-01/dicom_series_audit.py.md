```py
#!/usr/bin/env python3
"""Local header audit helper for a de-identified imaging receipt."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pydicom


IDENTIFIER_KEYWORDS = (
    "PatientName",
    "PatientID",
    "PatientBirthDate",
    "PatientAddress",
    "InstitutionAddress",
)


def audit_series(series_dir: Path) -> list[dict[str, object]]:
    """Report populated identifier fields without returning their values."""
    findings: list[dict[str, object]] = []
    for dicom_path in sorted(series_dir.glob("*.dcm")):
        dataset = pydicom.dcmread(dicom_path, stop_before_pixels=True, force=True)
        populated = [
            keyword
            for keyword in IDENTIFIER_KEYWORDS
            if str(getattr(dataset, keyword, "")).strip()
        ]
        findings.append(
            {
                "instance": dicom_path.name,
                "identifier_fields_present": populated,
                "series_description_present": bool(
                    str(getattr(dataset, "SeriesDescription", "")).strip()
                ),
            }
        )
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check a de-identified DICOM series header without exporting values."
    )
    parser.add_argument("series_dir", type=Path)
    args = parser.parse_args()

    findings = audit_series(args.series_dir)
    report = {
        "instances_checked": len(findings),
        "instances_with_identifier_fields": sum(
            bool(item["identifier_fields_present"]) for item in findings
        ),
        "findings": findings,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
