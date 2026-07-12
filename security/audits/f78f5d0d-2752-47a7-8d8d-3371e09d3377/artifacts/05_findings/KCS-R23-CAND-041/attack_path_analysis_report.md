# Attack-path analysis: closing snapshot can ingest a newly introduced Tier-A secret

- Candidate: `KCS-R23-CAND-041`
- Ledger row: `KCS-R23-CAND-041`
- Instance key: `KCS-R23-CAND-041`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high (0.96) for the interleaving trace; medium for occurrence frequency**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| manual preview | `crates/kcs-cli/src/main.rs` | `456-472` |  |
| index preview/closing snapshot | `crates/kcs-cli/src/main.rs` | `575-580,623-635` |  |
| path-only rescan | `crates/kcs-core/src/scope.rs` | `254-299` |  |

## Scope and actor

### Context

Manual snapshot and index are real product workflows. The defect crosses the current secret-classification control into authoritative archive history, but the immediate sink is the operator's owner-only local store.

### In scope

yes; mutable-path stable-byte use, secret policy, and archive provenance are explicit I2, I3, and I7 concerns

### Exposure and identity

no network listener; local or synced scope mutation during a normal snapshot/index operation

An untrusted local content or shared/synced contributor changes scope contents while KCS runs under the operator identity.

### Boundary crossed

yes: a name that should be excluded as Tier-A crosses from the untrusted scope into trusted plaintext CAS and commit history

### Authorization scope

internal-only (local scope contributor versus KCS operator/store boundary)

## Preconditions and attacker control

### Assumptions

- A lower-trust local or synced contributor can change direct-child names during the preview-to-snapshot interval.
- The newly introduced file is readable by KCS and its name would be Tier-A if classified at last use.
- The owner-only archive may later be retained, copied, or consumed even though immediate third-party disclosure is not shown.

### Preconditions

- Concurrent write or rename access to the selected scope
- A Tier-A file introduced after preview but before closing enumeration
- A manual snapshot or index operation covering that interval

### Attacker control

yes over direct-child name and bytes for an in-scope local or synced content contributor; control of the precise interleaving is plausible but was not dynamically measured

### Vector

none

## Attack path

- KCS previews a scope and converts only the names currently classified as ignored or Tier-A secret into an exclusion set.
- During the interval before the closing snapshot, a local or synced content contributor creates or renames a direct child to .env, a PEM name, or another Tier-A secret name.
- The closing snapshot re-enumerates the root but excludes only names in the stale set and does not rerun Tier-A classification.
- KCS reads the newly introduced secret, writes its plaintext raw object, and publishes it in local commit history.

## Impact and reach

- Category: TOCTOU secret-classification bypass and unintended archival
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data

### Target reach

one scope and each newly introduced Tier-A file caught by the interleaving

### Secret references

- Tier-A secret-bearing direct-child file
- Plaintext raw CAS object and commit-history reference

## Controls and counterevidence

### Existing controls

- Classify every closing-snapshot entry at last use before raw persistence.
- Alternatively bind each preview candidate to an expected name and byte identity and reject drift before publication.

### Mitigations

- Tier-A files present during preview are classified and added to the exclusion set.
- The snapshot excludes exact names in that set.
- The .kcs store is intended to be owner-only.
- No automatic remote send from this archived object was established.

### Counterevidence

- Stable files and secrets present during preview are excluded correctly.
- Immediate disclosure outside the owner-only local archive was not shown.
- No barrier-controlled race measured practical timing.

### Blind spots or proof gap

- The practical width and frequency of the preview-to-closing-snapshot interleaving were not measured.
- Downstream sharing or online processing of the archived secret was not traced.

## Final decision

The in-scope local/synced contributor crosses a real secret-classification boundary in a production workflow, so internal exposure alone does not suppress it. Impact is bounded to local archive inclusion and the race was not measured, supporting medium likelihood. The matrix maps medium impact and medium likelihood to low.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
