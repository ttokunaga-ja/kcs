# Attack-path analysis: Unrecognized binary gaps disappear from durable completeness and path telemetry

- Candidate: `KCS-R23-CAND-014`
- Ledger row: `KCS-R23-CAND-014`
- Instance key: `KCS-R23-CAND-014`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| transient_result | `crates/kcs-cli/src/main.rs` | `656-671` | The unsupported count exists only in the current index result. |
| persistent_status_sink | `crates/kcs-cli/src/main.rs` | `435-450` | status lists the archived file and tasks without an unsupported disposition. |
| completeness_control | `crates/kcs-cli/src/main.rs` | `2417-2506` | Search completeness counts task rows only. |
| root_control | `crates/kcs-cli/src/main.rs` | `9120-9169` | The octet-stream skip creates no task and its event omits input_path. |

## Scope and actor

### Context

Durable completeness and recovery telemetry omit archived-but-unsearchable input.

### In scope

Yes.

### Exposure and identity

An ordinary untrusted direct-child file is processed by the local CLI; no network exposure is required.

A lower-trust content contributor influences trusted operator or automation completeness decisions.

### Boundary crossed

Yes.

### Authorization scope

internal-only: no authorization bypass occurs, but untrusted scope content crosses into trusted completeness decisions.

## Preconditions and attacker control

### Assumptions

- The operator indexes the supplied scope.
- Status or search completeness is later trusted after the immediate index response is unavailable.

### Preconditions

- Unsupported binary input.
- A normal indexing invocation.
- Later reliance on status or search telemetry.

### Attacker control

A content contributor controls the file bytes and format needed to deterministically reach the unsupported branch.

### Vector

none

## Attack path

- An untrusted contributor supplies an unsupported binary in the indexed scope.
- Indexing archives it but creates no task or durable per-path unsupported disposition.
- The immediate response reports only a skipped count and the retained event omits the path.
- Later status and search omit the gap and can report full enrichment with no pending work.

## Impact and reach

- Category: observability and completeness-integrity failure
- Impact: **medium**
- Likelihood: **high**

### Impact surface

data: search completeness, recovery decisions, and automation consuming enrichment status

### Target reach

Any unsupported file in the supplied scope; aggregate scope completeness can be false.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- A one-run skipped counter and INFO event expose the gap class.
- CAS preserves the original bytes.
- Task-based status aggregation is the broken completeness control.

### Mitigations

- Raw bytes remain in CAS.
- The immediate invocation reports the skipped-file count.
- Rerunning index repeats the count.

### Counterevidence

- No data is destroyed.
- No confidentiality, network-consent, or budget boundary is bypassed.
- The immediate count reveals that some input was skipped.

### Blind spots or proof gap

- None.

## Final decision

The lower-trust path is direct and deterministic: an ordinary unsupported file produces durable false completeness and non-actionable status. Impact is bounded to search and workflow integrity. Medium impact plus high likelihood maps mechanically to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
