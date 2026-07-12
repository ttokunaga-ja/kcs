# Attack-path analysis: Snapshot's regular-file check can be raced into archiving an outside-scope symlink target

- Candidate: `KCS-R23-CAND-018`
- Ledger row: `KCS-R23-CAND-018`
- Instance key: `KCS-R23-CAND-018`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-cli/src/main.rs` | `452-472` | Manual snapshot opens the current repository, computes filename exclusions, and calls snapshot_filtered. |
| root_control | `crates/kcs-core/src/scope.rs` | `261-290` | DirEntry file_type is observed before a separate pathname-based fs::read with no descriptor/inode binding. |
| archive_sink | `crates/kcs-core/src/scope.rs` | `290-299` | Bytes read through the replacement path are hashed, written to raw CAS, and bound under the benign filename. |
| cas_sink | `crates/kcs-core/src/cas.rs` | `60-75` | ObjectStore persists the supplied buffer under its content hash. |
| closest_control | `crates/kcs-core/src/scope.rs` | `413-430` | Snapshot holds only the .kcs store lock; it does not exclude external working-directory renames. |

## Scope and actor

### Context

Mutable working-directory TOCTOU across the scope filesystem and content-identity boundaries; the .kcs store lock does not serialize external directory writers.

### In scope

Yes.

### Exposure and identity

A local untrusted filesystem contributor races ordinary status or snapshot; there is no network exposure.

A lower-trust local content contributor controls the mutable directory entry, while KCS runs with the operator's broader read authority.

### Boundary crossed

Yes.

### Authorization scope

internal-only: a lower-trust writer in the selected working root can exploit broader operator read authority.

## Preconditions and attacker control

### Assumptions

- A lower-trust process has write and rename authority in the selected working directory.
- The KCS process can read the outside target.
- The operator invokes status or snapshot and the attacker wins the check/read interleaving.

### Preconditions

- Concurrent rename authority in the selected root.
- Victim read permission on an outside target.
- An operator status or snapshot invocation.
- A successful timing interleaving.

### Attacker control

The attacker controls the direct-child replacement and symlink target but not filesystem scheduling; repeated attempts may improve reliability.

### Vector

none

## Attack path

- A lower-trust writer presents a regular direct-child file in the selected working root.
- KCS observes DirEntry.file_type as regular.
- Before the later pathname read, the writer atomically replaces the name with a symlink to a victim-readable file outside the scope.
- fs::read follows the replacement symlink.
- Snapshot hashes and stores the outside bytes in raw CAS and binds them into the authoritative tree under the benign direct-child name.

## Impact and reach

- Category: pathname TOCTOU and out-of-scope archival
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

data: authoritative snapshot integrity and out-of-scope byte ingestion

### Target reach

The current status tree or snapshot and its raw CAS objects within the selected scope.

### Secret references

- The outside target may contain victim-readable sensitive data, but no specific secret or lower-trust CAS-read path is proven.

## Controls and counterevidence

### Existing controls

- The early no-follow file-type observation rejects stable symlinks.
- The later fs::read is a distinct pathname operation without no-follow, descriptor, inode, or containment rebinding.
- The .kcs lock does not exclude external working-root renames.

### Mitigations

- A stable symlink present at the initial file-type check is skipped.
- The owner-only .kcs parent normally limits later CAS disclosure.
- The store lock serializes cooperating KCS store writers.

### Counterevidence

- A symlink present during the initial file-type observation is skipped.
- The attacker requires concurrent directory-write authority and a successful race.
- Losing interleavings archive benign bytes, skip the entry, or return an I/O error.
- Owner-only .kcs permissions normally prevent the lower-trust writer from reading the archived bytes.

### Blind spots or proof gap

- No live stress harness measured scheduling reliability.
- No standalone lower-trust read path from owner-only CAS was established.

## Final decision

A realistic lower-trust filesystem writer can cross the scope boundary and place outside bytes into authoritative archive state. Standalone impact is bounded because CAS is normally owner-only and disclosure is not proven, while exploitation requires winning a race. Medium impact plus medium likelihood maps mechanically to low.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
