# Cluster health follow-up - 2026-07-14



## Scope

This check covers the Atlas Checkout workloads after the gateway patch incident
on 2026-07-13. Reliability Engineering reviewed the production EKS cluster
before reopening the routine node-maintenance queue.



## Observations

- Checkout API, payment adapter, and event relay pods were evenly distributed
  across the three application node groups.
- The checkout disruption budget allowed one voluntary eviction at a time; no
  pending eviction was left after the audit.
- CoreDNS and the gateway sidecars showed stable restart counts through the
  morning review.
- Two nodes had an older telemetry agent image. That update is unrelated to
  customer traffic and remains in the next maintenance batch.



## Follow-up

The on-call owner should run pod-drain-audit.sh before each node drain and
attach its output to the change ticket. Platform Operations owns the telemetry
agent rollout; Atlas Checkout does not need a separate maintenance window.
