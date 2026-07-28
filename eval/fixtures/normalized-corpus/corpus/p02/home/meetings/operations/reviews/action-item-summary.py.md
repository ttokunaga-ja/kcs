```py
#!/usr/bin/env python3
"""Summarize assigned follow-up lines from an operations-review transcript."""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path


ASSIGNMENT = re.compile(r"^-\s+(?P<owner>[A-Z][a-z]+)\s+will\s+(?P<task>.+)$")


def collect_actions(text: str) -> dict[str, list[str]]:
    actions: dict[str, list[str]] = defaultdict(list)
    for line in text.splitlines():
        match = ASSIGNMENT.match(line.strip())
        if match:
            actions[match["owner"]].append(match["task"])
    return dict(actions)


def main(path: Path) -> int:
    actions = collect_actions(path.read_text(encoding="utf-8"))
    if not actions:
        print("No assigned actions found.")
        return 1
    for owner in sorted(actions):
        for task in actions[owner]:
            print(f"{owner}: {task}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(Path(sys.argv[1])))
```
