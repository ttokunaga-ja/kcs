```py
"""Small local helper for preparing a concise customer follow-up email."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage


@dataclass(frozen=True)
class FollowUp:
    customer: str
    recipient: str
    summary: str
    next_step: str
    send_on: date


def build_follow_up(item: FollowUp) -> EmailMessage:
    if "@" not in item.recipient:
        raise ValueError("recipient must be an email address")
    if not item.summary.strip() or not item.next_step.strip():
        raise ValueError("summary and next_step are required")

    message = EmailMessage()
    message["From"] = "Maya Chen <maya.chen@sablesignal.example>"
    message["To"] = item.recipient
    message["Subject"] = f"Follow-up from SableSignal — {item.customer}"
    message.set_content(
        f"Hello,\n\n{item.summary.strip()}\n\n"
        f"Next step: {item.next_step.strip()}\n\n"
        f"Best,\nMaya\nSent {item.send_on.isoformat()}"
    )
    return message


if __name__ == "__main__":
    sample = FollowUp(
        customer="Lark Logistics",
        recipient="procurement@larklogistics.example",
        summary="Thank you for reviewing the commercial packet.",
        next_step="Please share the preferred time for the procurement check-in.",
        send_on=date.today(),
    )
    print(build_follow_up(sample).as_string())
```
