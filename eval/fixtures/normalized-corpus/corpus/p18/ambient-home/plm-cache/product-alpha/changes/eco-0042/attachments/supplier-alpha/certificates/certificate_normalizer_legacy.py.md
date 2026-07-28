```py
"""PLM 添付の旧形式証明書を QMS 取込用に整形する暫定ヘルパー。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path


def normalize_certificate(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {
        "supplier": raw["supplier_name"].strip(),
        "certificate": raw["certificate_no"].replace(" ", ""),
        "valid_until": date.fromisoformat(raw["valid_until"]).isoformat(),
        "review_state": "pending_qms_import",
    }
```
