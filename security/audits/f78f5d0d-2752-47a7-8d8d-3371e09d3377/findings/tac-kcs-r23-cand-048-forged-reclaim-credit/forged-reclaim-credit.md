# Unbound Reservation Stamps Can Forge Budget-Reclaim Credits

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` trusts `reserved_usd` and `reserved_month` fields
that are serialized inside task records and later converts those fields into a
positive reclaim credit. A lower-trust contributor who supplies an adopted or
preseeded task store can place a schema-valid failed online task with a forged
reservation stamp. When the victim later runs ordinary indexing against that
store, the orphan-reclaim path copies the forged amount into the device-global
reclaim ledger. The enforced budget calculation then subtracts that credit from
genuine gross spend, reopening monetary capacity for later operator-authorized
billable calls.

I reviewed the vulnerable revision directly and exercised a local synthetic
accounting probe, but I did not run a live adapter call, use credentials, or
mutate a real KCS store. The final attack-path decision is Medium/P2: impact is
high because the bug can weaken monetary caps and spend controls, while
likelihood is constrained by the need for adopted poisoned state, existing
gross spend, and later authorized online work.

## Background

KCS records online batch work as `TaskDescriptor` values in `tasks.jsonl`. The
same record carries normal scheduling state and the reservation stamp that is
supposed to represent one live, KCS-issued phantom reservation:

```rust
// crates/kcs-pipeline/src/task.rs
pub struct TaskDescriptor {
    pub task_id: String,
    #[serde(rename = "type")]
    pub task_type: TaskType,
    pub input_path: String,
    pub input_hash: String,
    pub output_ref: String,
    pub status: TaskStatus,
    pub fallback_reason: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reserved_usd: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub reserved_month: Option<String>,
}
```

The intended invariant is reasonable: if a non-billable online send fails after
KCS has reserved budget, a later retirement can reclaim exactly that phantom so
it does not consume the cap for the rest of the month. The tricky boundary is
that task records are also persisted scope-local state. In an adopted-store
workflow, we must treat those records as lower trust than the victim device's
budget ledger. Once a task record can mint device-global credit, reservation
amounts need authenticity and one-time-use semantics rather than simple JSON
shape validation.

The charge and reclaim ledgers share `MonthlyCostLedgerEntry`, a positive-only
row type:

```rust
// crates/kcs-pipeline/src/budget.rs
pub struct MonthlyCostLedgerEntry {
    pub month: String,
    pub scope_id: String,
    pub adapter_kind: String,
    pub usd: f64,
}
```

That design prevents negative charge rows from directly lowering spend, but it
also means the separate reclaim ledger must be as trustworthy as the charge
ledger. If we can create a positive reclaim row without tying it to a real prior
reservation, the budget calculation cannot distinguish a true phantom from a
forged credit.

## Vulnerability Details

We first reach the lower-trust boundary when KCS loads `tasks.jsonl` through
`TaskStore::all()`. The loader rejects path traversal and malformed hashes, but
it does not authenticate `task_id`, `reserved_usd`, `reserved_month`, or their
relationship to any charge row:

```rust
// crates/kcs-pipeline/src/task.rs
let descriptor: TaskDescriptor = serde_json::from_str(&line).map_err(|err| {
    PipelineError::corrupt(self.path.display().to_string(), err.to_string())
})?;
if !is_scope_local_file_name(&descriptor.input_path) {
    return Err(PipelineError::path(descriptor.input_path));
}
if !kcs_core::cas::is_hash(&descriptor.input_hash) {
    return Err(PipelineError::corrupt(
        self.path.display().to_string(),
        format!("task input_hash is not a valid hash: {}", descriptor.input_hash),
    ));
}
by_id.insert(descriptor.task_id.clone(), descriptor);
```

If we carry a forged reservation stamp through that loader, the index pipeline
can later retire it as an orphaned online markdown task. The relevant sweep is
intended for deleted or renamed files: it selects failed online markdownize
tasks whose `input_path` no longer appears in the live scan candidates, then
collects reclaim rows before appending them to the sibling reclaim ledger.

```rust
// crates/kcs-cli/src/main.rs
let mut orphan_reclaims: Vec<MonthlyCostLedgerEntry> = Vec::new();
task_store
    .update_matching(|task| {
        let orphaned = task.task_type == TaskType::Markdownize
            && task.output_ref == placeholder_output_ref
            && task.status == TaskStatus::Failed
            && is_reservation_bearing_send_failure(task)
            && !live_paths.contains(task.input_path.as_str());
        if !orphaned {
            return false;
        }
        if let Some(entry) = retire_online_task_reclaiming(
            task,
            &reservation_scope_id,
            markdown_adapter_kind,
        ) {
            orphan_reclaims.push(entry);
        }
        true
    })?;
```

The decision about whether the task can produce a credit is based on the
failure kind and the presence of the stamp. The decisive point is that
`reclaim_entry_for()` copies the amount and month straight out of the task into
a ledger row. We never prove that the amount came from a prior reservation, that
it is unique, or that it has not already been consumed through another task.

```rust
// crates/kcs-cli/src/main.rs
fn reclaim_entry_for(
    task: &TaskDescriptor,
    reservation_scope_id: &str,
    adapter_kind: &str,
) -> Option<MonthlyCostLedgerEntry> {
    if !matches!(
        retry_kind_from_reason(task.fallback_reason.as_deref()),
        RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded | RetryErrorKind::AuthError
    ) {
        return None;
    }
    match (task.reserved_usd, task.reserved_month.clone()) {
        (Some(usd), Some(month)) => Some(MonthlyCostLedgerEntry {
            month,
            scope_id: reservation_scope_id.to_owned(),
            adapter_kind: adapter_kind.to_owned(),
            usd,
        }),
        _ => None,
    }
}
```

From here, the accounting sink is straightforward. The reclaim ledger enforces
that rows are finite and non-negative, which a forged positive credit satisfies.
Budget enforcement then computes gross spend minus reclaimed spend. The anomaly
fallback only triggers when the credit exceeds gross spend enough to make the
net negative; a smaller forged credit remains effective.

```rust
// crates/kcs-cli/src/main.rs
let gross = cost_ledger
    .monthly_total_for_adapter(month, scope_id, adapter_kind)
    .map_err(pipeline_to_kcs)?;
let reclaimed = cost_ledger
    .reclaim_ledger()
    .monthly_total_for_adapter(month, scope_id, adapter_kind)
    .map_err(pipeline_to_kcs)?;
let net = gross - reclaimed;
if net < -1e-9 {
    return Ok(gross.max(0.0));
}
Ok(net.max(0.0))
```

The vulnerable state is therefore not an arbitrary negative ledger row. It is a
schema-valid, positive reclaim row whose provenance is unsupported. If the
victim already has 12.00 USD of gross current-month spend and the adopted task
claims a 9.75 USD reservation, the device budget logic sees only 2.25 USD of
net spend. That lower net value feeds `budget_remaining_for_adapter()` and can
make a later 3.00 USD paid operation appear allowed under a 10.00 USD cap.

## Exploitability Analysis

The strongest route is a supplied-store attack, not remote code execution and
not credential theft. We start with a contributor who can provide copied,
shared, or preseeded KCS scope state. They do not need access to the victim's
device-global cost ledger or adapter credentials. They need to shape one task
record so it satisfies the orphan-reclaim predicate: markdownize task, failed
status, online placeholder output, a non-billable failure reason such as
`rate_limit`, a deleted or absent `input_path`, and chosen `reserved_usd` /
`reserved_month` values.

We then rely on normal victim behavior. When the victim adopts the store and
runs indexing, KCS loads the task, sees the path and hash as syntactically
valid, retires the orphan, and appends the derived reclaim row. Later online
work is still separately authorized by the victim operator and still uses the
victim's configured adapter controls. The bug is that those controls consult a
net spend value that may now understate real spend.

Several constraints keep the final severity at Medium even though the monetary
impact is high. First, a direct write to an already-private live store would be
equivalent local authority and is not the interesting boundary; the meaningful
case is lower-trust state adoption. Second, the forged credit must be smaller
than applicable gross spend or the `net < -1e-9` fallback ignores the reclaim
and charges gross. Third, the credit does not itself send a request. It opens
capacity for a later otherwise-authorized paid operation. Folder caps,
per-adapter caps, and network or secret gates can still block specific work.

Those constraints also guide reliable exploitation. A contributor who does not
know the victim's current spend can choose a conservative credit to avoid the
over-reclaim fallback, or can aim at environments where current-month paid work
is already expected. Replaying the same task row is less useful after retirement
because `retire_online_task_reclaiming()` clears the stamp in the victim's task
store. The missing invariant is still broader than single-row replay, though:
without a reservation or charge identity, KCS cannot reject a fresh supplied
task that names the same alleged phantom or prove that the claimed amount ever
existed.

## Proof of Concept

The included PoC is a local, synthetic accounting probe. It models only the
validated transition: task shape acceptance, reclaim-row construction,
positive-row acceptance, and net-spend calculation. It does not read a real KCS
store, contact an adapter, use credentials, or send network traffic.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
[+] synthetic probe: no network, no credentials, no KCS store mutation
[+] TaskStore shape checks accept poisoned task: True
[+] reclaim_entry_for output:
{
  "adapter_kind": "markdown",
  "month": "2026-07",
  "scope_id": "victim-scope",
  "usd": 9.75
}
[+] reclaim ledger finite/non-negative check accepts row: True
[+] gross spend before forged credit: $12.00
[+] net spend after forged credit:  $2.25
[+] remaining against $10.00 cap: $7.75
[+] next $3.00 paid call allowed by net accounting: True
[+] over-reclaim fallback keeps gross spend: $12.00
```

The important line is the allowed future paid call. With 12.00 USD of genuine
gross spend against a 10.00 USD cap, another 3.00 USD operation should not have
capacity. After the forged 9.75 USD reclaim is netted, the synthetic gate sees
2.25 USD of spend and 7.75 USD remaining. The final line also demonstrates the
existing counter-control: a 99.00 USD forged credit is too large, makes net
spend negative, and is ignored in favor of gross spend.

## Remediation

The invariant to restore is simple: a reclaim must consume exactly one
authentic, previously unmatched reservation or charge identity issued by KCS.
The amount and month in task state should be treated as advisory until they are
matched under the device cost lock against a trusted reservation ledger. A task
record supplied from scope state must never be able to mint device-global
credit by carrying only `reserved_usd` and `reserved_month`.

A minimal shape is to stamp a stable `reservation_id` at reservation time,
persist it in both the trusted reservation or charge ledger and the task, and
require the reclaim path to atomically consume that identity:

```rust
fn reclaim_entry_for(
    task: &TaskDescriptor,
    reservations: &mut ReservationLedger,
    reservation_scope_id: &str,
    adapter_kind: &str,
) -> Result<Option<MonthlyCostLedgerEntry>> {
    if !matches!(
        retry_kind_from_reason(task.fallback_reason.as_deref()),
        RetryErrorKind::RateLimit | RetryErrorKind::QuotaExceeded | RetryErrorKind::AuthError
    ) {
        return Ok(None);
    }

    let reservation_id = match task.reservation_id.as_deref() {
        Some(id) => id,
        None => return Ok(None),
    };
    let reservation = reservations.consume_unreclaimed(
        reservation_id,
        reservation_scope_id,
        adapter_kind,
    )?;

    Ok(Some(MonthlyCostLedgerEntry {
        month: reservation.month,
        scope_id: reservation.scope_id,
        adapter_kind: reservation.adapter_kind,
        usd: reservation.usd,
    }))
}
```

The regression tests should cover the real vulnerable path, not only helper
functions. We would add tests that adopt a synthetic `tasks.jsonl` with forged
`reserved_usd` and `reserved_month` but no trusted reservation identity, run the
orphan-reclaim path, and assert that no reclaim row is appended. Neighboring
tests should prove that a valid reservation can be reclaimed once, that a second
row with the same reservation ID is rejected, that cross-scope and cross-adapter
claims fail, and that an over-reclaim still falls back to gross spend.

As a defense-in-depth improvement, KCS can also reject reservation-bearing task
stamps during lower-trust adoption unless the task record is accompanied by a
verifiable device-issued reservation identity. That prevents legacy or copied
state from crossing the scope-to-device accounting boundary with authority it
never earned.

## Summary

We traced a scope-local task field into a device-global monetary credit. The
bug is present because KCS correctly avoided negative charge rows, but then
trusted serialized task reservation stamps as the authority for a separate
positive reclaim ledger. Once an adopted task can supply those stamps, a smaller
than gross forged reclaim underreports spend and can reopen budget capacity for
later paid work.

The local PoC demonstrates the accounting primitive without touching live
services. The most useful future variant work is around other places where
scope-local state is promoted into device-global authority, especially when the
stored value is an amount, identity, or once-only claim that should be backed by
a trusted ledger rather than by JSON shape alone.
