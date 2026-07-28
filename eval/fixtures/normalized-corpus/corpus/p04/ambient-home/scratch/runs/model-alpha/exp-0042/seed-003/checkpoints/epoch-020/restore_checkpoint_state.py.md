```py
"""Local recovery helper retained with an old Cedar checkpoint."""

from __future__ import annotations

from pathlib import Path


def checkpoint_parts(directory: Path) -> list[Path]:
    return sorted(part for part in directory.glob("*.pt") if part.is_file())


def recovery_ready(directory: Path) -> bool:
    return bool(checkpoint_parts(directory)) and (directory / "state.json").exists()
```
