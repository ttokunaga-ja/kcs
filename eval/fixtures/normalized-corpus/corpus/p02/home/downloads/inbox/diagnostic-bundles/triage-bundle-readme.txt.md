```txt
Checkout gateway diagnostic bundle
Collected: 2026-07-13 14:30 UTC
Source: production edge diagnostics

Contents
- Edge access sample from the affected regional gateway.
- Current gateway pod inventory and rollout state.
- Per-upstream request share and error ratio snapshot.

Triage notes
The sample was exported while the release was held for uneven upstream selection. Compare the request share with a healthy regional sample before using it in the retrospective. The bundle contains operational evidence only; customer payloads and payment fields were excluded by the collector.

Suggested reviewers: Checkout On-call, Reliability Engineering, and the gateway release owner.
```
