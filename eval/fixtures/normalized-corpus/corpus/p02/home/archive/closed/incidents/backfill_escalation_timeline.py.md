```py
#!/usr/bin/env python3
"""Render a compact escalation chronology from exported incident events.

This helper was kept with the closed-incident material after Reliability
Engineering backfilled owner changes into the Atlas Checkout incident archive.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Escalation:
    occurred_at: str
    actor: str
    destination: str
    reason: str


def read_events(path: Path) -> Iterable[Escalation]:
    for line_number, raw_line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not raw_line.strip():
            continue
        record = json.loads(raw_line)
        if record.get("event_type") != "escalation":
            continue
        if record.get("service") != "atlas-checkout":
            continue
        try:
            yield Escalation(
                occurred_at=record["occurred_at"],
                actor=record["actor"],
                destination=record["destination"],
                reason=record["reason"],
            )
        except KeyError as exc:
            raise ValueError(f"event {line_number} is missing {exc.args[0]!r}") from exc


def render(events: Iterable[Escalation]) -> str:
    rows = sorted(events, key=lambda event: event.occurred_at)
    lines = ["# Escalation backfill", "", "| UTC | From | To | Reason |", "| --- | --- | --- | --- |"]
    lines.extend(
        f"| {event.occurred_at} | {event.actor} | {event.destination} | {event.reason} |"
        for event in rows
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the incident escalation appendix")
    parser.add_argument("events", type=Path, help="newline-delimited event export")
    parser.add_argument("--output", type=Path, default=Path("escalation-backfill.md"))
    args = parser.parse_args()
    args.output.write_text(render(read_events(args.events)), encoding="utf-8")


if __name__ == "__main__":
    main()
```
