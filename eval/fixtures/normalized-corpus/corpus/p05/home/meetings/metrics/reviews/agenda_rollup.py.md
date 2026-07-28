```py
"""週次 KPI review の agenda を小さなメモから組み立てる。"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path


def collect_topics(directory: Path) -> dict[str, list[str]]:
    topics: dict[str, list[str]] = defaultdict(list)
    for note in directory.glob("*.md"):
        for line in note.read_text(encoding="utf-8").splitlines():
            if line.startswith("- [ ] "):
                topics[note.stem].append(line.removeprefix("- [ ] "))
    return dict(topics)


def render(topics: dict[str, list[str]]) -> str:
    blocks = ["# Weekly KPI review agenda", "", "1. Sales and demand signals"]
    for owner, items in sorted(topics.items()):
        blocks.append(f"2. {owner}")
        blocks.extend(f"   - {item}" for item in items)
    return chr(10).join(blocks)


if __name__ == "__main__":
    print(render(collect_topics(Path("."))))
```
