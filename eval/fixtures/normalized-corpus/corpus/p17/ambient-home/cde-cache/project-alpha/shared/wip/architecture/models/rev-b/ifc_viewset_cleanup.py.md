```py
#!/usr/bin/env python3
"""Remove disposable IFC view-set exports after the CDE package is published."""

from __future__ import annotations

import argparse
from pathlib import Path


def collect_disposable_views(root: Path) -> list[Path]:
    return sorted(
        candidate
        for candidate in root.glob("*.ifcview")
        if candidate.name.startswith(("tmp_", "review_"))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit temporary IFC view-set files")
    parser.add_argument("directory", type=Path)
    parser.add_argument("--remove", action="store_true", help="delete only temporary exports")
    args = parser.parse_args()
    candidates = collect_disposable_views(args.directory)
    for candidate in candidates:
        print(f"candidate: {candidate.name}")
        if args.remove:
            candidate.unlink()
    print(f"view-set cleanup complete: {len(candidates)} item(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
