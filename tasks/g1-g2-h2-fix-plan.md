# G1/G2/H2 implementation receipt

Status: **historical, non-authorizing**. The superseded implementation plan and
remaining-work instructions were removed; this file retains only the unique
completion evidence from 2026-07-25.

All three accepted items were implemented and verified. The recorded gate was
1,318 tests passed, 0 failed, with `clippy -D warnings --all-features` and
formatting clean.

| Item | Completed behavior | Added regression tests |
| --- | --- | --- |
| G1 | Reconciliation recovers a row stranded between provider job creation and local job-id publication, without claiming a foreign job. | `reconcile_recovers_a_row_stranded_in_the_job_creation_window`; `reconcile_does_not_claim_a_foreign_provider_job` |
| G2 | One unreachable provider row does not abort collection of other rows; submit failure is represented per row. | `a_submit_failure_does_not_abort_the_invocation`; `an_unreachable_row_does_not_block_collection_of_the_others` |
| H2 | Prune applies only the frozen plan and a blocked plan applies nothing; blocked output has a typed code. | `apply_removes_only_what_the_plan_listed`; `a_blocked_plan_applies_nothing` |

The implementation reused the existing display-name intent-token inverse and
the shared adapter failure classifier. `fail_job_names` was added to the mock
because the older all-or-nothing failure seam could not express the G2
head-of-line case. H2 also introduced
`KIO-E-PRUNE-ORPHANS-BLOCKED-001`.

The recorded manual observations were: a stranded G1 row moved from
`unlistable: 1` to `batch_found: 1`; in G2 the reachable row completed while
the unreachable row remained unchanged; and a blocked H2 prune returned the
new typed error. These observations belong to their historical tested tree and
do not establish current RC acceptance.
