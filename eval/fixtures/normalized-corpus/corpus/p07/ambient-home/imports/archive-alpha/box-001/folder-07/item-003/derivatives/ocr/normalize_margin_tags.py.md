```py
"""Normalize pencil-mark tags in locally exported transcript sidecars.

The script is intentionally small: it preserves the source text and only
regularizes labels used in the Keller-Roth working folder.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path


TAG_ALIASES = {
    "[marg.?]": "[marginalia uncertain]",
    "[illeg.]": "[illegible]",
    "[sic?]": "[reading uncertain]",
}


def normalize_line(line: str) -> str:
    for source, replacement in TAG_ALIASES.items():
        line = line.replace(source, replacement)
    return re.sub(r"\[\s+", "[", line)


def normalize_file(path: Path) -> None:
    original = path.read_text(encoding="utf-8")
    revised = "".join(normalize_line(line) for line in original.splitlines(keepends=True))
    if revised != original:
        path.write_text(revised, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Normalize transcript margin tags.")
    parser.add_argument("sidecar", type=Path)
    args = parser.parse_args()
    normalize_file(args.sidecar)


if __name__ == "__main__":
    main()
```
