# Checkout verification dashboard notes - 2026-07-14

The production dashboard was used during the Atlas Checkout gateway incident
and in the next-day review.



## Panels retained

- Completion rate split by payment method.
- Gateway upstream error count grouped by route.
- Checkout API latency percentile by route.
- Kubernetes ready replicas for checkout workloads.



## Reading order

Start with completion rate, then inspect gateway errors, then compare the
latency split to pod readiness. This prevents a normal API latency panel from
masking a route-specific gateway problem.

The saved query slice is deliberately small so that the on-call engineer can
paste it into an ad hoc verification dashboard without editing the main board.
