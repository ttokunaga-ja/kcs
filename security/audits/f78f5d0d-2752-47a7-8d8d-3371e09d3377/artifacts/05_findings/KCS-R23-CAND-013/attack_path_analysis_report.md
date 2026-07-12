# Attack-path analysis: Embedding reconciliation revives AuthError work during batch retry

- Candidate: `KCS-R23-CAND-013`
- Ledger row: `KCS-R23-CAND-013`
- Instance key: `KCS-R23-CAND-013`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| command_contract | `crates/kcs-cli/src/main.rs` | `5639-5666` | batch retry passes allow_auth_revive=false and excludes non-retryable AuthError. |
| missing_control_propagation | `crates/kcs-cli/src/main.rs` | `5934-5967` | The flag reaches markdownize but is omitted from embedding enrichment. |
| negative_control | `crates/kcs-cli/src/main.rs` | `5992-6022` | Markdownize revival is correctly gated on allow_auth_revive. |
| root_control | `crates/kcs-cli/src/main.rs` | `7997-8043` | Embedding reconciliation unconditionally revives live Failed(AuthError). |
| send_sink | `crates/kcs-cli/src/main.rs` | `7340-7345,7526-7544,7727-7742` | The revived chunk passes task filtering and its text is sent in the same pass. |

## Scope and actor

### Context

Command-scoped task authorization failure in the normal embedding recovery workflow.

### In scope

Yes.

### Exposure and identity

A local CLI recovery path reaches a configured outbound adapter call; KCS has no inbound listener.

A lower-trust remote provider can create the AuthError response state; the trusted operator supplies the later recovery command.

### Boundary crossed

Yes.

### Authorization scope

internal-only: only AuthError revival under batch retry is bypassed; initial adapter consent is not bypassed.

## Preconditions and attacker control

### Assumptions

- Persistent embedding approval remains valid.
- Secret holds and budget checks pass.
- Credentials are usable again.

### Preconditions

- An existing Failed(auth_error) embedding task.
- Repaired credentials.
- The operator invokes batch retry.

### Attacker control

The remote provider controls the failure response; a content contributor may control the already-approved chunk text, but neither controls the later operator command.

### Vector

remote

## Attack path

- An approved embedding attempt leaves a live Failed(auth_error) task.
- The operator repairs credentials and invokes batch retry.
- Embedding reconciliation ignores allow_auth_revive=false and resets the task to Pending.
- The revived task passes filtering and its text is sent to the adapter in the same pass.

## Impact and reach

- Category: task-lifecycle and command-scoped authorization bypass
- Impact: **medium**
- Likelihood: **high**

### Impact surface

network: previously approved content can be resent and bounded online cost incurred contrary to the selected recovery contract

### Target reach

Live AuthError embedding tasks in the selected scope.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- AuthError is non-retryable with max_attempts=0.
- The outer retry path sets allow_auth_revive=false.
- Adapter approval, secret holds, and the budget gate still execute.

### Mitigations

- Initial network approval remains required.
- Secret holds remain effective.
- Budget enforcement remains effective.

### Counterevidence

- The operator requested retry work generally.
- Content was already approved for the same adapter.
- No monetary-cap or secret-hold bypass occurs.

### Blind spots or proof gap

- Validation used the adapter seam rather than a real provider, although the real pre-adapter request path was reached.

## Final decision

A realistic lower-trust provider-response path exists and the revival/send transition is deterministic once ordinary recovery preconditions hold. The wrong command reaches a real send, but existing consent, secret, and budget controls bound impact. Medium impact plus high likelihood maps mechanically to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
