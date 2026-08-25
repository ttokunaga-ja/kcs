# Replication aggregator decision record

Status: **historical, non-authorizing**. This compact record preserves the
2026-07-25 decision and Stage 1 measurements. The former Stage 2/3 work order is
obsolete: candidate selection, publication ordering, repair, and fail-closed
replica behavior are now specified by [03-data-model.md](../docs/03-data-model.md)
and [05-runtime.md](../docs/05-runtime.md) and implemented in the current tree.

The user decision changed cross-scope search from per-scope scatter-gather to a
device-level read replica. Each scope's `.kio` remains truth; the aggregator is
rebuildable cache. The retained design invariants are:

1. The aggregator never becomes authority for scope state or approvals.
2. Writers publish scope truth before the replica projection.
3. Replica rows use scope-resolved eligibility/bindings rather than reimplementing
   liveness or secrecy policy.
4. Missing or incomplete replica state fails closed and is repaired by a writer
   or repair command, not by a search-time source-index fallback.

The Stage 1 experiment replicated 428 scopes, 3,851 chunks, and 3,851 vectors in
a 24.6 MB database, including 11.8 MB of vectors. Hybrid rank-1 improved from 7
to 8 and top-5 from 22 to 24; text/vector results were unchanged. End-to-end
latency remained about 1.2 seconds because per-scope candidate fan-out still
dominated that intermediate implementation. A previously reported 0.02-second
fan-out result was invalid: it timed an error response outside a Kio scope.

During Stage 1, narrowed search initially pruned an unsearched scope from the
replica. Restricting prune to all-scope refreshes fixed it, and
`ct3_multi_012` captured the regression. These measurements and the incident
describe that historical stage only; they do not define current schema or
behavior.
