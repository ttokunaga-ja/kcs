```py
"""Poppy Gateway のローカル設定を読み、必須キーを検査する。"""

from __future__ import annotations

from collections.abc import Mapping


REQUIRED_KEYS = {"callback_base_url", "request_timeout_seconds", "audit_topic"}


def missing_keys(config: Mapping[str, object]) -> list[str]:
    return sorted(key for key in REQUIRED_KEYS if not config.get(key))


def callback_origin(config: Mapping[str, object]) -> str:
    raw = str(config.get("callback_base_url", "")).rstrip("/")
    if not raw.startswith(("https://", "http://")):
        raise ValueError("callback_base_url must include a scheme")
    return raw
```
