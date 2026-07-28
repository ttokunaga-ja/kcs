```py
from __future__ import annotations
from pathlib import Path

def footer_fields(path: Path) -> dict[str, str]:
    raw = path.read_bytes()[-512:].decode("latin-1", errors="ignore")
    fields: dict[str, str] = {}
    for line in raw.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            if key.strip().isidentifier():
                fields[key.strip()] = value.strip()
    return fields
```
