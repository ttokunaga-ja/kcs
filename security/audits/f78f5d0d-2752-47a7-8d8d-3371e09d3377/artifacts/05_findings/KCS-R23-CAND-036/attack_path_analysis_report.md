# Attack-path analysis: Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape

- Candidate: `KCS-R23-CAND-036`
- Ledger row: `KCS-R23-CAND-036`
- Instance key: `KCS-R23-CAND-036:persisted-tree-normalize-path`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| intended_semantic_control | `crates/kcs-core/src/dag.rs` | `40-79` |  |
| root_control | `crates/kcs-core/src/scope.rs` | `742-755` |  |
| path_constructor | `crates/kcs-pipeline/src/markdownize.rs` | `311-329` |  |
| filesystem_sinks | `crates/kcs-cli/src/main.rs` | `5453-5543` |  |

## Scope and actor

### Context

Adoption of lower-trust copied/preseeded stores is explicitly in scope and distinct from arbitrary same-user mutation of a private live store. The explicit reindex confirmation is meaningful interaction but is not consent to filesystem effects outside the selected scope.

### In scope

Yes.

### Exposure and identity

No network surface. Exposure is an operator-invoked local archive adoption and forced reindex workflow consuming attacker-supplied persisted state.

Filesystem operations run with the invoking OS user's permissions. The archive contributor need not already possess that user's arbitrary live-filesystem write authority.

### Boundary crossed

Verified: semantically poisoned but CAS-valid adopted state crosses the trusted-store reader boundary and directs create/write/recursive-remove operations outside .kcs and the selected scope.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- The victim opens a copied, shared, synced, or preseeded store supplied by a lower-trust contributor.
- The contributor can construct content-hash-correct commit/tree objects with semantically invalid path-bearing fields.
- The operator intentionally runs reindex --force --yes on the adopted archive.
- The escaped destination is writable by the invoking OS user.

### Preconditions

- Adoption of a lower-trust copied/preseeded .kcs store.
- A CAS-valid malicious HEAD commit/tree containing parent/path components in tool_profile_hash.
- Operator reindex --force --yes interaction.
- A user-writable escaped destination compatible with the generated .gN suffix and fixed filenames.

### Attacker control

yes — the archive contributor controls the persisted tool_profile_hash and can compute matching CAS hashes; exact target shape is constrained by fanout, .gN suffixes, and fixed manifest/unit names.

### Vector

none

## Attack path

- A lower-trust archive contributor supplies a copied or preseeded .kcs store whose CAS-valid HEAD tree contains a normalize.tool_profile_hash with path separators or parent components.
- Repository::read_commit/read_tree verifies object hashes and JSON shape but does not rerun CommitObject/TreeEntry semantic validation at crates/kcs-core/src/scope.rs:742-755.
- The operator adopts the archive and invokes the documented recovery workflow reindex --force --yes, which passes the poisoned value to normalized_instance_dir.
- Path construction embeds the value verbatim, escaping the normalized-units base; copy_normalized_instance_gen then creates directories, overwrites fixed KCS-shaped files, or recursively removes the escaped .gN destination on error at crates/kcs-cli/src/main.rs:5453-5543.

## Impact and reach

- Category: CWE-22 path traversal from semantically unvalidated persisted DAG state
- Impact: **high**
- Likelihood: **medium**

### Impact surface

data

### Target reach

User-writable filesystem paths reachable through the poisoned path component during one adopted-store reindex; effects include directory creation, fixed-name replacement, or recursive removal of the constructed destination.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- writer-side TreeEntry semantic validation
- CAS kind/hash/content verification
- forced-reindex confirmation
- fixed destination naming and atomic file writes

### Mitigations

- Freshly constructed trees call TreeEntry::validate.
- ObjectStore::read_by_hash verifies requested hashes and object bytes.
- reindex requires explicit --force and --yes.
- Generated .gN suffixes and fixed KCS-shaped filenames constrain exact write/removal targets.

### Counterevidence

- CAS hash verification defeats accidental corruption but not a contributor who intentionally hashes malicious semantic content.
- Writer-side TreeEntry validation protects fresh local stores but is not rerun on read.
- The operator must explicitly run reindex --force --yes.
- Suffix and filename constraints prevent a claim of completely unconstrained arbitrary-file overwrite.

### Blind spots or proof gap

- No full two-root runtime reproduction was performed, although lexical containment and direct filesystem sinks are statically complete.
- The exact set of useful external targets depends on path normalization, permissions, existing directory layout, and generated suffixes.

## Final decision

This is a realistic in-scope supplied-store confused-deputy path, not equivalent same-user private-store tampering, and it crosses scope containment in a real recovery workflow. Impact is high because the KCS user's authority can be redirected to create, replace, or recursively remove data outside the selected store. Likelihood is medium because archive adoption, a crafted CAS-valid tree, explicit forced reindex, and a compatible writable target are all required. The matrix mechanically maps high impact plus medium likelihood to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
