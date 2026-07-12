# Attack-path analysis: A symlinked `.kcs` binds one working root to another scope's live store

- Candidate: `KCS-R23-CAND-008`
- Ledger row: `KCS-R23-CAND-008`
- Instance key: `KCS-R23-CAND-008`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-core/src/scope.rs` | `126-139` | Init delegates any existing root/.kcs entry, including a symlink to a valid directory, to Repository::open. |
| root_control | `crates/kcs-core/src/scope.rs` | `188-200` | Only the selected root is canonicalized; lexical root/.kcs is accepted with link-following is_dir and installed as Repository.kcs_dir/ObjectStore root. |
| closest_control | `crates/kcs-core/src/scope.rs` | `889-909` | Scope validation checks schema, ULID syntax, and format version but does not bind the physical store or stored scope_path to Repository.root. |
| working_tree_source | `crates/kcs-core/src/scope.rs` | `254-303` | Snapshot enumeration and raw reads use direct children of self.root while raw objects are written through self.store. |
| mutation_sink | `crates/kcs-core/src/scope.rs` | `421-430,504-520` | Snapshot locks and writes the substituted kcs_dir/ObjectStore, then advances its commit, refs, HEAD, and manifest. |
| product_entrypoints | `crates/kcs-cli/src/main.rs` | `435-472,558-580,622-635` | Status, snapshot, and index reach the mixed root/store repository through normal CLI commands. |

## Scope and actor

### Context

Copied/preseeded/shared store adoption is explicitly in scope. This exact symlink/alias instance crosses the folder-local authoritative-store boundary and was corroborated by preserved same-revision two-scope reproductions.

### In scope

Yes.

### Exposure and identity

Local supplied/shared filesystem root consumed through ordinary CLI commands; no listener or network is involved.

The lower-trust contributor chooses the root/.kcs link, while KCS follows it with the victim user's permissions and mutates the target store as that user.

### Boundary crossed

Yes.

### Authorization scope

local operator command against a lower-trust supplied/shared root

## Preconditions and attacker control

### Assumptions

- A lower-trust contributor can supply a root containing the live .kcs symlink or alias.
- The target is a valid KCS store readable and writable by the victim KCS process.
- The target path resolves in the victim's filesystem namespace and the operator runs a normal command.

### Preconditions

- The supplied root must contain a live .kcs symlink or equivalent alias.
- The link target must be a structurally valid accessible KCS store.
- The operator must invoke a read or mutating KCS command in the supplied root.

### Attacker control

yes: an in-scope shared/archive contributor controls the supplied root and .kcs link target

### Vector

none

## Attack path

- A lower-trust shared/archive contributor supplies a working root whose .kcs entry is a symlink or live alias to another structurally valid KCS store reachable in the victim filesystem namespace.
- The operator invokes status, snapshot, or index in the supplied root.
- Repository::open canonicalizes only the selected root, follows the lexical .kcs path, and does not bind the resolved store to that root.
- KCS reads working files from root A while reading or writing objects and refs through store B.
- A mutating command archives root-A bytes and advances store B's HEAD, refs, and manifest, producing cross-scope false history/evidence.

## Impact and reach

- Category: scope/store confused deputy and cross-scope archive/ref mutation
- Impact: **high**
- Likelihood: **medium**

### Impact surface

authoritative archive history, refs, derived index state, and evidence integrity

### Target reach

one reachable foreign KCS store per crafted root/link; prior history is usually recoverable

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Canonicalization of the selected root.
- Scope schema, scope_id syntax, and format-version validation.
- Owner-only creation for newly initialized .kcs directories.
- Content-addressed objects and generally recoverable prior commits.

### Mitigations

- The target must pass KCS structural validation and be accessible to the victim user.
- New stores are created with owner-only permissions.
- Append-only objects generally leave prior commits recoverable.

### Counterevidence

- This is not arbitrary-directory write: the target must be a valid readable/writable KCS store.
- KCS has no listener and the victim must invoke a command.
- The attacker must know or arrange a target path available in the victim namespace.
- Plain detached copies and supported moves are not part of the proven instance.

### Blind spots or proof gap

- Deployment-specific symlink preservation and target-path availability affect exploit frequency.
- The evidence does not establish an approval-replay extension, which is unnecessary for this decision.

## Final decision

The supplied-root contributor is a realistic lower-trust actor, and normal commands deterministically cross from root A into authoritative store B. Cross-scope false history/evidence is High impact; the valid-target, namespace, and user-invocation prerequisites make likelihood Medium, yielding Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
