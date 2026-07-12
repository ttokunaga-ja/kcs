# Attack-path analysis: Batch recovery bypasses repository tool-lock validation

- Candidate: `KCS-R23-CAND-064`
- Ledger row: `KCS-R23-CAND-064`
- Instance key: `KCS-R23-CAND-064`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| open_control_gap | `crates/kcs-core/src/scope.rs` | `188-206,235-239` | Repository open validates config, scope, and manifest but not tool-lock.json. |
| batch_control_gap | `crates/kcs-cli/src/main.rs` | `5586-5667` | Both resume and retry acquire the store lock and execute tasks without validate_repo_tool_lock. |
| online_execution | `crates/kcs-cli/src/main.rs` | `5934-5968,6050-6067,6248` | Batch gates and drives markdownize/embedding work without reading the repository tool lock. |
| expected_control | `crates/kcs-cli/src/main.rs` | `10942-10949` | The existing helper parses and validates repository tool-lock.json. |
| schema_validator | `crates/kcs-adapter/src/tool_lock.rs` | `52-57,238-260` | Malformed versions/entries are rejected when the helper is actually invoked. |

## Scope and actor

### Context

KCS has no inbound listener. The meaningful boundary is adoption of lower-trust repository state followed by an operator-mediated outbound adapter operation under a repository identity record that the normal validator rejects.

### In scope

Yes.

### Exposure and identity

Local copied/shared archive and batch-recovery workflow; the only network activity is an approved outbound adapter request.

The KCS OS user supplies the configured adapter identity and budget authority. A shared/archive-state contributor can supply the scope state but does not thereby obtain the user's credential or choose the configured destination.

### Boundary crossed

Yes.

### Authorization scope

operator-mediated local workflow with pre-existing outbound adapter authorization

## Preconditions and attacker control

### Assumptions

- The operator opens a copied, shared, migrated, or preseeded scope rather than an exclusively owner-created live private store.
- The scope contains an otherwise eligible persisted task and matching current file bytes.
- Online adapter use, credentials, and budget were already authorized independently of the malformed tool lock.

### Preconditions

- A copied, shared, preseeded, or fault-affected scope must carry a malformed tool-lock and a recoverable task.
- The operator or automation must explicitly run batch resume or retry.
- All independent network, credential, secret, exact-byte, media, and budget checks must pass.

### Attacker control

plausible: the in-scope shared/archive-state contributor can provide the malformed repository state and persisted task, while the operator retains command, destination, credential, and approval control

### Vector

none

## Attack path

- A lower-trust shared or preseeded scope is adopted with a malformed repository tool-lock and an otherwise eligible persisted recovery task.
- The operator or calling automation invokes batch resume or batch retry with the already configured network approval, adapter credential, and budget authority.
- Repository open validates config, scope, and manifest but does not parse tool-lock.json, and the batch dispatcher does not invoke validate_repo_tool_lock before mutating tasks.
- The recovered task passes the independent path, hash, media, secret, network, and budget checks and reaches online markdownize or embedding execution.
- KCS performs an outbound operation and can persist derived state even though sibling commands reject the same repository identity state as malformed.

## Impact and reach

- Category: repository provenance and online-recovery authorization-control bypass
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

repository identity-policy consistency, bounded adapter execution/cost, and derived-state provenance

### Target reach

eligible recovery tasks in one adopted scope

### Secret references

- The configured adapter credential is used for the already approved outbound request; the defect does not expose or redirect that credential.

## Controls and counterevidence

### Existing controls

- Repository open validates config, scope, and manifest but not tool-lock.json.
- validate_repo_tool_lock parses and validates lock shape when sibling commands invoke it.
- Batch task selection and send-time byte, secret, adapter, network, and budget controls remain present.

### Mitigations

- Persistent network approval, credentials, task eligibility, current path/hash/size/media checks, secret holds, and budget limits remain enforced.
- The adapter reports its actual runtime profile, so false runtime-profile labeling is not established by this candidate.
- The malformed lock can be repaired or removed to restore normal command behavior.

### Counterevidence

- tool-lock.json is normally owner-protected inside a private .kcs store, so unrestricted same-user mutation alone would grant equivalent authority and is not reportable.
- The validator checks schema and modality, not equality with the current effective adapter configuration; its omission therefore proves malformed-state bypass but not destination substitution.
- No isolated batch invocation captured a send under a malformed lock, although the exact branch-to-sink trace and sibling negative control are complete.
- All controls that directly authorize bytes, secrets, network use, credentials, and spend remain in force.

### Blind spots or proof gap

- The frequency with which users batch-resume copied scopes containing recoverable tasks is not measured.
- The evidence does not quantify provider charges or downstream reliance on state produced during the invalid-lock interval.

## Final decision

A realistic lower-trust copied/shared-store source exists in the threat model, so hard suppression does not apply. The consequence is nevertheless bounded because malformed lock state neither chooses a destination nor bypasses byte, secret, credential, or budget authorization. Medium impact with Medium likelihood maps mechanically to Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
