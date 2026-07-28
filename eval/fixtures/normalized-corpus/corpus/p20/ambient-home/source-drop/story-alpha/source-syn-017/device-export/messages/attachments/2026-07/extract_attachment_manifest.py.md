```py
from __future__ import annotations

from pathlib import Path
import json


def attachment_rows(folder: Path) -> list[dict[str, object]]:
    rows = []
    for item in sorted(folder.iterdir()):
        if item.is_file() and not item.name.startswith('.'):
            rows.append({"name": item.name, "bytes": item.stat().st_size})
    return rows


def write_manifest(folder: Path, destination: Path) -> None:
    destination.write_text(json.dumps(attachment_rows(folder), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    print("Use from the local evidence workstation.")
```
