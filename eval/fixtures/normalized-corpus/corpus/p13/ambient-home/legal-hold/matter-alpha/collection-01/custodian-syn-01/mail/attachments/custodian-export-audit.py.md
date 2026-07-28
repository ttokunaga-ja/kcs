```py
"""Small utility used to review an EML export manifest before upload."""

from __future__ import annotations

import csv
import hashlib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ManifestRow:
    relative_path: str
    byte_count: int
    sha256: str


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def audit_export(root: Path, manifest_csv: Path) -> list[str]:
    warnings: list[str] = []
    with manifest_csv.open(newline="", encoding="utf-8") as handle:
        for raw in csv.DictReader(handle):
            row = ManifestRow(raw["relative_path"], int(raw["byte_count"]), raw["sha256"])
            candidate = root / row.relative_path
            if not candidate.exists():
                warnings.append(f"missing: {row.relative_path}")
                continue
            if candidate.stat().st_size != row.byte_count:
                warnings.append(f"size mismatch: {row.relative_path}")
            if digest(candidate) != row.sha256:
                warnings.append(f"checksum mismatch: {row.relative_path}")
    return warnings


if __name__ == "__main__":
    print("Use audit_export() from the collection notebook after the vendor delivery arrives.")
```
