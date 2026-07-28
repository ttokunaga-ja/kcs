```py
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FailureMode:
    process_step: str
    severity: int
    occurrence: int
    detection: int


def priority(mode: FailureMode) -> int:
    """FMEA ワークショップ用の単純な比較値。正式帳票の判定には使用しない。"""
    return mode.severity * mode.occurrence * mode.detection


def needs_review(mode: FailureMode) -> bool:
    return priority(mode) >= 96
```
