# Attack-path analysis: CAS write accepts a pre-existing corrupt destination as success

- Candidate: `KCS-R23-CAND-043`
- Ledger row: `KCS-R23-CAND-043`
- Instance key: `KCS-R23-CAND-043`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high (0.99)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| unverified early success | `crates/kcs-core/src/cas.rs` | `155-163` |  |
| later read verification | `crates/kcs-core/src/cas.rs` | `78-100` |  |
| snapshot publication | `crates/kcs-core/src/scope.rs` | `413-520` |  |

## Scope and actor

### Context

CAS and archive history are real product surfaces. Direct arbitrary same-user tampering with an already private live store is excluded, but adoption of attacker-supplied archive state is an explicit trust boundary.

### In scope

yes for adopted/shared state under I7 and I9; same-user arbitrary mutation of a private live store is excluded

### Exposure and identity

no network listener; malicious state arrives through copied, shared, synced, or preseeded scope adoption

An untrusted archive-state contributor supplies the occupied CAS slot; KCS later consumes it under the operator identity.

### Boundary crossed

yes: lower-trust persisted state is accepted as a successful authoritative CAS write and published into trusted refs

### Authorization scope

internal-only (archive adoption and local snapshot workflow)

## Preconditions and attacker control

### Assumptions

- The attacker can supply a copied, shared, synced, or preseeded store without already having unrestricted write access to the operator's private live store.
- The attacker knows or supplies content whose hash selects the poisoned slot.
- The operator performs a snapshot after adopting that state.

### Preconditions

- Adoption of a lower-trust .kcs store
- A corrupt entry at an exact predictable CAS fanout path
- Snapshot of content selecting that hash

### Attacker control

yes over preseeded/shared archive state and potentially the matching scope content; ordinary private-live-store tampering is not relied upon

### Vector

none

## Attack path

- A shared, copied, or preseeded scope contains a wrong-byte or wrong-type entry at the exact CAS fanout path for a known raw hash.
- The operator adopts the lower-trust store and snapshots content whose expected hash maps to that occupied path.
- atomic_write at crates/kcs-core/src/cas.rs:155-163 sees the destination exists and returns success without verifying type, bytes, or digest.
- Snapshot publishes tree, commit, and refs naming the expected hash even though the durable slot is corrupt.
- Later reads detect the mismatch and fail, while future legitimate writes continue accepting the occupied slot as successful.

## Impact and reach

- Category: persisted-state poisoning and CAS write integrity failure
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

one adopted store and each object hash whose slot is preseeded corrupt

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- When a destination exists, verify regular-file type and exact digest before returning success.
- Atomically reject or quarantine mismatched occupied slots so later valid writes can recover.

### Mitigations

- CAS paths are derived from lowercase SHA-256 hashes.
- Read paths verify content digest and detect the corrupt slot.
- The normal live store is intended to be owner-only.
- Impact is recoverable local archive integrity/availability rather than external overwrite.

### Counterevidence

- Read-time digest verification prevents silent return of wrong bytes.
- An attacker with unrestricted write access to the private live store already has equivalent authority and is out of scope.
- The exact CAS slot must match content the operator later snapshots.
- The corruption can be detected and manually repaired.

### Blind spots or proof gap

- No end-to-end adopted-store runtime was recorded in the saved validation.
- The prevalence of copied or preseeded untrusted stores is unknown.

## Final decision

The attack relies on the explicitly in-scope adopted/shared-state contributor, not equivalent private-store authority, and crosses into authoritative archive publication. Exact-slot and adoption prerequisites constrain likelihood while impact is recoverable local corruption. The matrix maps medium impact and medium likelihood to low.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
