# Checkout gateway rollout — 2026-07-13

**Change:** CHG-4821
**Owners:** Reliability Engineering and Checkout On-call
**Scope:** production edge gateway header-normalization rule



## Outcome

The rule was introduced through the first two rollout stages, then held when one region showed uneven upstream selection. The team disabled the rule, drained the affected gateway pods, and verified normal route distribution before closing the change.

| UTC | Event |
| --- | --- |
| 13:40 | Change window opened and preflight checks passed. |
| 13:52 | Single-zone canary began. |
| 14:06 | Regional stage admitted. |
| 14:28 | Edge dashboard showed route skew above the guardrail. |
| 14:36 | Rollout held; incident channel opened. |
| 14:48 | Rule disabled and replacement pods started. |
| 15:08 | Checkout error ratio returned to its normal band. |



## Notes for the next attempt

- Compare per-region upstream selection before increasing the traffic share.
- Keep the release owner in the incident channel until the post-change dashboard review is complete.
- Exercise the gateway drain procedure during the next weekday maintenance window.
