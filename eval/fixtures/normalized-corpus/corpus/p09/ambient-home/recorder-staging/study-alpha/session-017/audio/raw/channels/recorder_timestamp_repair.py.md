```py
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def repair_sidecar(path: Path, seconds: float) -> None:
    payload = json.loads(path.read_text(encoding="utf-8"))
    started = datetime.fromisoformat(payload["recorded_at"])
    payload["recorded_at"] = (started + timedelta(seconds=seconds)).isoformat()
    payload["timing_note"] = "Slate offset corrected after recorder import."
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("sidecar", type=Path)
    parser.add_argument("--seconds", type=float, required=True)
    args = parser.parse_args()
    repair_sidecar(args.sidecar, args.seconds)
```
