```py
"""Q2 closeout 時に使った sales と ledger の照合補助。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True)
class ReconciliationRow:
    market_code: str
    channel: str
    recognized_sales: Decimal
    ledger_sales: Decimal

    @property
    def difference(self) -> Decimal:
        return self.recognized_sales - self.ledger_sales


def summarize(rows: Iterable[ReconciliationRow]) -> dict[tuple[str, str], Decimal]:
    totals: dict[tuple[str, str], Decimal] = {}
    for row in rows:
        key = (row.market_code, row.channel)
        totals[key] = totals.get(key, Decimal("0")) + row.difference
    return totals


def needs_review(delta: Decimal, tolerance: Decimal = Decimal("50000")) -> bool:
    # 金額は円。月次 readout では差分の根拠を同じ粒度で説明する。
    return abs(delta) > tolerance
```
