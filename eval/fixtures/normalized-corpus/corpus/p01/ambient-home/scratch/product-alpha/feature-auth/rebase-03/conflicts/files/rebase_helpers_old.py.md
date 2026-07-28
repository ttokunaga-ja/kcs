```py
"""一時退避していたリベース用の小さな補助関数。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ConflictMarker:
    path: str
    preferred_side: str


def select_release_side(marker: ConflictMarker) -> str:
    """リリース枝の設定ファイルは upstream を優先する。"""
    if marker.path.endswith(("defaults.ts", "routes.yaml")):
        return "upstream"
    return marker.preferred_side


def summarize(markers: list[ConflictMarker]) -> dict[str, int]:
    result = {"upstream": 0, "local": 0}
    for marker in markers:
        result[select_release_side(marker)] += 1
    return result
```
