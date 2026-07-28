HUMMINGBIRD PAYMENTS  |  LEDGER PLATFORM  |  ARCHITECTURE
1
HUMMINGBIRD PAYMENTS
Capacity routing options
Planning alternatives for the Orchid Ledger release
Review window:
17-18 July 2026
Prepared by:
Ledger Platform Architecture
Release train:
Orchid Ledger 2026.07
Status:
Planning note; not a release authorization
Purpose
This note compares operating shapes for retained-credit routing during the Orchid Ledger 2026.07
rollout. It is a planning companion to the architecture review and records the assumptions used for
staging, rather than setting the production release guardrail.
Option A: queue-first spillover
Queue-first spillover preserves a smaller resident set and hands additional eligible entries to the
durable replay path early. It reduces allocator variation during recovery, but adds a modest delay to
the first retry cycle and creates a sharper transition for the operations team to observe.
Option B: worker-pool partitioning
Partitioning isolates recovery traffic from live settlement confirmation, keeping the fast path steadier
when a replay starts. The cost is operational complexity: the recovery pool needs separate saturation
alerts, and capacity can be stranded if demand shifts faster than the pool rebalance interval.
Planning comparison
For the release rehearsal, both options remain viable. Queue-first spillover is easier to revert and
gives the release team a direct view of persistence pressure; worker-pool partitioning provides more
isolation but needs a longer soak before it can be considered the default.


HUMMINGBIRD PAYMENTS  |  LEDGER PLATFORM  |  ARCHITECTURE
2
Recommended staging option
Use queue-first spillover for the final rehearsal with a retained-credit ceiling of 46,800. This is a
staging assumption chosen to leave room for instrumentation and operator intervention; it is not the
production decision for Orchid Ledger.
Operational signals
Track replay age, persisted-entry rate, worker saturation, and confirmation-tail spread together. A
change in only one signal is expected during warm-up; a sustained movement across all four signals
should pause the rehearsal and trigger trace collection before another run.
The runbook should name the handoff from the settlement team to Ledger Platform on-call, including
the condition for draining a worker and the condition for restoring normal routing. The goal is a
repeatable operational move, not a one-time benchmark.
Decision boundary
This note does not approve a customer-facing limit, change entitlement behavior, or replace the
architecture decision record. It only selects a conservative rehearsal shape while the production
admission-path implementation and observability checks are completed.
Next review
Ledger Platform Architecture will compare the final rehearsal traces with the June soak baseline,
then recommend whether the chosen routing shape remains appropriate for the release candidate.
Release Engineering owns the scheduling and evidence attachment.
Owner:
Ledger Platform Architecture. Revisit the operating plan after the first full replay rehearsal or
if queue age exceeds the expected warm-up band.


HUMMINGBIRD PAYMENTS | LEDGER PLATFORM | ARCHITECTURE



HUMMINGBIRD PAYMENTS | LEDGER PLATFORM | ARCHITECTURE



# HUMMINGBIRD PAYMENTS



## Recommended staging option

Use queue-first spillover for the final rehearsal with a retained-credit ceiling of 46,800. This is a staging assumption chosen to leave room for instrumentation and operator intervention; it is not the production decision for Orchid Ledger.



# Capacity routing options

*Planning alternatives for the Orchid Ledger release*

**Review window:** 17-18 July 2026

**Prepared by:** Ledger Platform Architecture

**Release train:** Orchid Ledger 2026.07

**Status:** Planning note; not a release authorization



## Operational signals

Track replay age, persisted-entry rate, worker saturation, and confirmation-tail spread together. A change in only one signal is expected during warm-up; a sustained movement across all four signals should pause the rehearsal and trigger trace collection before another run.

The runbook should name the handoff from the settlement team to Ledger Platform on-call, including the condition for draining a worker and the condition for restoring normal routing. The goal is a repeatable operational move, not a one-time benchmark.



## Purpose

This note compares operating shapes for retained-credit routing during the Orchid Ledger 2026.07 rollout. It is a planning companion to the architecture review and records the assumptions used for staging, rather than setting the production release guardrail.



## Option A: queue-first spillover

Queue-first spillover preserves a smaller resident set and hands additional eligible entries to the durable replay path early. It reduces allocator variation during recovery, but adds a modest delay to the first retry cycle and creates a sharper transition for the operations team to observe.



## Decision boundary

This note does not approve a customer-facing limit, change entitlement behavior, or replace the architecture decision record. It only selects a conservative rehearsal shape while the production admission-path implementation and observability checks are completed.



## Option B: worker-pool partitioning

Partitioning isolates recovery traffic from live settlement confirmation, keeping the fast path steadier when a replay starts. The cost is operational complexity: the recovery pool needs separate saturation alerts, and capacity can be stranded if demand shifts faster than the pool rebalance interval.



## Next review

Ledger Platform Architecture will compare the final rehearsal traces with the June soak baseline, then recommend whether the chosen routing shape remains appropriate for the release candidate. Release Engineering owns the scheduling and evidence attachment.

**Owner:** Ledger Platform Architecture. Revisit the operating plan after the first full replay rehearsal or if queue age exceeds the expected warm-up band.

2

## Planning comparison

For the release rehearsal, both options remain viable. Queue-first spillover is easier to revert and gives the release team a direct view of persistence pressure; worker-pool partitioning provides more isolation but needs a longer soak before it can be considered the default.

1