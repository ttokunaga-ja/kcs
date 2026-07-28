```py
#!/usr/bin/env python3
"""Render the small production plan used for the Atlas gateway follow-up."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date


@dataclass(frozen=True)
class GatewayChange:
    environment: str
    module: str
    target_group: str
    canary_weight: int
    owner: str
    change_date: str


def build_change() -> GatewayChange:
    return GatewayChange(
        environment="prod",
        module="atlas_gateway",
        target_group="checkout-edge",
        canary_weight=5,
        owner="reliability-engineering",
        change_date=date(2026, 7, 14).isoformat(),
    )


if __name__ == "__main__":
    change = build_change()
    print(json.dumps(asdict(change), indent=2, sort_keys=True))
    print()
    print(
        "Review only: apply remains gated on a healthy checkout canary and "
        "the incident follow-up checklist."
    )
```
