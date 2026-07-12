# Attack-path analysis: unbound reservation stamps can forge budget-reclaim credits

- Candidate: `KCS-R23-CAND-048`
- Ledger row: `KCS-R23-CAND-048`
- Instance key: `KCS-R23-CAND-048`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.96)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| task reservation fields | `crates/kcs-pipeline/src/task.rs` | `41-74,129-186` |  |
| reclaim trigger | `crates/kcs-cli/src/main.rs` | `8987-9037` |  |
| credit construction | `crates/kcs-cli/src/main.rs` | `9977-9996` |  |
| accounting sink | `crates/kcs-cli/src/main.rs` | `10226-10261` |  |

## Scope and actor

### Context

The boundary is untrusted scope-local persisted state being converted into device-global monetary authority during an ordinary adopted-store workflow.

### In scope

yes; authentic accounting and supplied-state provenance are covered by I4 and I5

### Exposure and identity

not public; local adopted-store processing followed by separately authorized outbound adapter operations

The contributor controls supplied task records but not the victim device ledger, credentials, provider, or commands; KCS mints the reclaim and later spends as the victim user.

### Boundary crossed

yes: scope-local untrusted task fields alter device-global enforced budget state

### Authorization scope

internal-only adopted-store workflow followed by operator-authorized online execution

## Preconditions and attacker control

### Assumptions

- The victim adopts lower-trust copied, shared, or preseeded task state.
- Current-month gross spend exists against which the forged credit can be netted.
- The forged task satisfies a reclaimable orphan/failure path.
- The operator later performs otherwise-authorized paid adapter work.

### Preconditions

- Adopted poisoned task state with a reclaimable failure
- Enough matching or device-wide gross spend to avoid the over-reclaim fallback
- An orphan-reconciliation command and later authorized online workload

### Attacker control

yes over the supplied task's reserved amount, month, failure/status, and orphan-trigger fields; not over later credentials or destinations

### Vector

none

## Attack path

- A lower-trust contributor supplies an adopted store whose schema-valid tasks.jsonl contains a reclaimable failed task with forged reserved_usd and reserved_month values.
- TaskStore::all validates path/hash shape but not reservation provenance or charge identity at crates/kcs-pipeline/src/task.rs:129-186.
- The orphan sweep at crates/kcs-cli/src/main.rs:8987-9037 selects the task, and reclaim_entry_for at lines 9977-9996 copies the forged stamp into the device-global reclaim ledger.
- Effective spend at crates/kcs-cli/src/main.rs:10226-10261 subtracts the credit when it does not exceed applicable gross spend, reopening capacity for later otherwise-authorized billable calls.

## Impact and reach

- Category: budget-accounting authenticity failure and monetary-cap bypass
- Impact: **high**
- Likelihood: **medium**

### Impact surface

device/folder budget integrity, user funds, and outbound adapter execution

### Target reach

current-month spend on one device, bounded per forged credit by applicable existing gross spend

### Secret references

- Later calls can use configured adapter credentials, but the finding neither discloses nor redirects them.

## Controls and counterevidence

### Existing controls

- Bind each reclaim to one authentic, unique, previously unmatched reservation or charge identity.
- Enforce once-only idempotent consumption under the device cost lock.
- Reject reservation-bearing task stamps that cannot be authenticated against the ledger.

### Mitigations

- Task paths and hash-shaped fields are validated.
- Only selected reservation-bearing failures are reclaimable.
- Retirement clears a task stamp and limits direct same-row replay.
- A meaningfully negative net total falls back to gross spend.
- Network, secret, credential, destination, and per-send checks remain enforced.

### Counterevidence

- Direct arbitrary mutation of an already-private live store is excluded; reportability relies on supplied-store adoption.
- A reclaim greater than gross spend for a queried filter is ignored by the anomaly fallback.
- The forged credit does not itself send a request; later authorized billable work is required.
- Independent folder or per-adapter caps can remain restrictive.

### Blind spots or proof gap

- No end-to-end paid-call reproduction was retained.
- The contributor's knowledge of current gross spend and hostile-store adoption frequency are unmeasured.

## Final decision

Hard suppression does not apply because supplied-store contributors are explicitly lower trust and do not need equivalent control over the victim's device ledger. Reopening a configured monetary cap is High impact, while adoption, existing gross spend, predicate shaping, and later online work constrain likelihood to Medium. The matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
