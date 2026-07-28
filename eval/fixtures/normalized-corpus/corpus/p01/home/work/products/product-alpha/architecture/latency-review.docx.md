HUMMINGBIRD PAYMENTS  |  LEDGER PLATFORM  |  ARCHITECTURE
1
HUMMINGBIRD PAYMENTS
Retained-credit latency review
Architecture assessment for the Orchid Ledger release
Review window:
17-18 July 2026
Prepared by:
Ledger Platform Architecture
Release train:
Orchid Ledger 2026.07
Status:
Approved guardrail pending implementation confirmation
Purpose
This review reconciles the settlement-path latency observed in the release candidate with the ledger
retention behavior that becomes visible during recovery and replay. The review is scoped to the
Ledger Platform service boundary; merchant-facing timing and dispute workflows are unchanged.
Observed behavior
The slowest interval appeared after a retry wave rebuilt several settlement aggregates while retained
credits were still resident in the same worker pool. Median confirmation timing stayed within the
release objective, but the upper tail widened when the in-memory credit set crossed the operating
band used in the June soak.
Trace review points to allocator pressure rather than a database lock. The replay queue drains
normally once the retained set falls back through the eviction watermark, which makes admission
control the safer release control than a schema change this late in the train.
Working interpretation
The release needs a predictable residency boundary so retry traffic cannot turn a recoverable replay
into an extended confirmation tail. The guardrail should be enforced before fan-out and should
remain observable through the existing ledger-worker saturation panel.


HUMMINGBIRD PAYMENTS  |  LEDGER PLATFORM  |  ARCHITECTURE
2
Decision record
The Orchid release caps concurrently retained credits at 47,200.
This is a release-control decision for the Ledger Platform and not a customer entitlement change.
When the boundary is reached, newly eligible entries continue through the normal durable path and
are admitted after capacity is released; no settled balance is discarded.
Implementation notes
Enforcement belongs in the retained-credit admission path, immediately before worker fan-out. The
implementation should emit the current resident count, rejection reason, and replay age to the
existing release dashboard so on-call can distinguish normal backpressure from a drain failure.
The configuration will ship behind the Orchid release flag. The rollback path is to disable the guardrail
and drain the affected workers in sequence; it does not require a ledger migration or a customer-
visible maintenance window.
Validation and follow-up
Before promotion, repeat the recovery replay with the boundary enabled and capture p50, p95, and
resident-count traces. Release Engineering will attach the evidence to the 2026.07 promotion note,
and Ledger Platform on-call will review the first production replay window.
Owner:
Ledger Platform Architecture. Review again after the first post-release recovery exercise or if
the resident-count alert holds above its warning band for two consecutive intervals.


HUMMINGBIRD PAYMENTS | LEDGER PLATFORM | ARCHITECTURE



HUMMINGBIRD PAYMENTS | LEDGER PLATFORM | ARCHITECTURE



# HUMMINGBIRD PAYMENTS



## Decision record

The Orchid release caps concurrently retained credits at 47,200.

This is a release-control decision for the Ledger Platform and not a customer entitlement change. When the boundary is reached, newly eligible entries continue through the normal durable path and are admitted after capacity is released; no settled balance is discarded.



# Retained-credit latency review

*Architecture assessment for the Orchid Ledger release*

**Review window:** 17-18 July 2026

**Prepared by:** Ledger Platform Architecture

**Release train:** Orchid Ledger 2026.07

**Status:** Approved guardrail pending implementation confirmation



## Purpose

This review reconciles the settlement-path latency observed in the release candidate with the ledger retention behavior that becomes visible during recovery and replay. The review is scoped to the Ledger Platform service boundary; merchant-facing timing and dispute workflows are unchanged.



## Implementation notes

Enforcement belongs in the retained-credit admission path, immediately before worker fan-out. The implementation should emit the current resident count, rejection reason, and replay age to the existing release dashboard so on-call can distinguish normal backpressure from a drain failure.

The configuration will ship behind the Orchid release flag. The rollback path is to disable the guardrail and drain the affected workers in sequence; it does not require a ledger migration or a customer-visible maintenance window.



## Observed behavior

The slowest interval appeared after a retry wave rebuilt several settlement aggregates while retained credits were still resident in the same worker pool. Median confirmation timing stayed within the release objective, but the upper tail widened when the in-memory credit set crossed the operating band used in the June soak.

Trace review points to allocator pressure rather than a database lock. The replay queue drains normally once the retained set falls back through the eviction watermark, which makes admission control the safer release control than a schema change this late in the train.



## Validation and follow-up

Before promotion, repeat the recovery replay with the boundary enabled and capture p50, p95, and resident-count traces. Release Engineering will attach the evidence to the 2026.07 promotion note, and Ledger Platform on-call will review the first production replay window.

**Owner:** Ledger Platform Architecture. Review again after the first post-release recovery exercise or if the resident-count alert holds above its warning band for two consecutive intervals.

2

## Working interpretation

The release needs a predictable residency boundary so retry traffic cannot turn a recoverable replay into an extended confirmation tail. The guardrail should be enforced before fan-out and should remain observable through the existing ledger-worker saturation panel.

1