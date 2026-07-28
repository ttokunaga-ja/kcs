```txt
Reliability Engineering stand-up — 2026-07-14

Attendees: Mara, Jules, Sora, Priya

The Atlas Checkout gateway event from Sunday remains the top follow-up. The release procedure worked as intended, but the regional route signal was discovered only after the second rollout stage began. Priya will add a pre-stage comparison to the production dashboard, and Jules will make the route-skew alert page both Checkout On-call and Reliability Engineering.

Capacity review: the Q3 model is acceptable with the extra gateway pool reserved for promotion weeks. Sora will confirm the reservation with Platform Capacity.

Open items:
- Capture a clean trace bundle from a normal gateway pod for comparison.
- Review retry-budget observations at Wednesday's operations review.
- Publish the revised incident handoff checklist before the next maintenance window.
```
