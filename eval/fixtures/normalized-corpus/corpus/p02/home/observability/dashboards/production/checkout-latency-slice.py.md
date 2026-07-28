```py
#!/usr/bin/env python3
"""Emit a small Prometheus query bundle for the checkout verification view."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Slice:
    label: str
    expression: str


SLICES = (
    Slice(
        "checkout p95 by route",
        'histogram_quantile(0.95, sum by (le, route) (rate(http_server_duration_seconds_bucket{service="atlas-checkout"}[5m])))',
    ),
    Slice(
        "gateway upstream errors",
        'sum(rate(gateway_upstream_requests_total{service="atlas-checkout",code=~"5.."}[5m]))',
    ),
    Slice(
        "successful checkout completions",
        'sum(rate(checkout_completed_total{service="atlas-checkout",result="success"}[5m]))',
    ),
)


def main() -> None:
    for item in SLICES:
        print(f"{item.label}\n{item.expression}\n")


if __name__ == "__main__":
    main()
```
