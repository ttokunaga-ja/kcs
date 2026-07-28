```py
"""デプロイ完了通知の本文を、読みやすい項目へ分解する。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DeploymentNotice:
    service: str
    revision: str
    region: str
    result: str


def parse_notice(line: str) -> DeploymentNotice:
    fields = dict(item.split("=", 1) for item in line.split() if "=" in item)
    return DeploymentNotice(
        service=fields.get("service", "unknown"),
        revision=fields.get("revision", "unknown"),
        region=fields.get("region", "unknown"),
        result=fields.get("result", "unknown"),
    )


def is_successful(notice: DeploymentNotice) -> bool:
    return notice.result.lower() in {"ok", "passed", "completed"}
```
