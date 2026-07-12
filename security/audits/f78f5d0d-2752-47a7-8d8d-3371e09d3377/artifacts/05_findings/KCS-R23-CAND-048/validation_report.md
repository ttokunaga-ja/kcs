# Validation: unbound reservation stamps can forge budget-reclaim credits

- Candidate: `KCS-R23-CAND-048`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.96)**
- Method: **V6 poisoned-state provenance + V10 complete accounting trace**

Imported/shared task records carry mutable `reserved_usd` and `reserved_month` fields at `crates/kcs-pipeline/src/task.rs:41-74`. Task loading validates path/hash shape but not reservation provenance, uniqueness, or state coherence at `task.rs:129-186`. Orphan reconciliation reaches reclaim construction at `crates/kcs-cli/src/main.rs:8987-9037`; `reclaim_entry_for` copies the task-supplied amount/month into a positive credit at `main.rs:9977-9996`. Effective spend subtracts those credits at `main.rs:10226-10261`.

The cost ledger checks finite/nonnegative amounts and rejects only aggregate over-reclaim at `crates/kcs-pipeline/src/budget.rs:96-180`. No charge identity, reservation ID, or once-only relation binds a reclaim to an authentic prior charge. A forged credit smaller than unrelated gross spend passes the aggregate check, erases genuine spend, and reopens capacity for further billable calls.

Counterevidence: a direct arbitrary writer to a private live store has equivalent local authority, but copied/preseeded task state is an accepted lower-trust adoption boundary. The credit must not drive net spend negative, limiting one row but not the bypass. The exact source/control/sink trace is complete without an external call.

Closure: reportable High monetary-cap bypass. Bind every reclaim idempotently to one authentic prior reservation/charge and reject unsupported task stamps.

