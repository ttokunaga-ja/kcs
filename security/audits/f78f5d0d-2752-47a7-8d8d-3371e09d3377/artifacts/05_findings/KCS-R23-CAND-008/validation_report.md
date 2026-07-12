# Validation: A symlinked `.kcs` binds one working root to another scope's live store

- Candidate: `KCS-R23-CAND-008`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-core/src/scope.rs:188-200`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.96)**
- Method: **V10 exact static trace, corroborated by preserved isolated same-revision reproductions**

## Rubric

- [x] Normal CLI entrypoints open the selected/current directory through `Repository::open`.
- [x] An existing `.kcs` symlink can make the canonical working root and live store resolve to different directories.
- [x] Repository validation has no no-follow, canonical-parent, or equivalent root/store binding check.
- [x] Read commands combine the selected root's working files with the linked store's HEAD and objects.
- [x] Snapshot/index mutation writes selected-root bytes and advances refs in the linked foreign store.

## Evidence

`Repository::init` canonicalizes the selected root, forms `root/.kcs`, and delegates any existing entry to `open` at `crates/kcs-core/src/scope.rs:126-139`. `Repository::open` canonicalizes only the root, retains the lexical `root/.kcs` path, accepts it with link-following `is_dir()`, and installs that same path as both `Repository.kcs_dir` and the `ObjectStore` root at `crates/kcs-core/src/scope.rs:188-200`. There is no `symlink_metadata`, no-follow open, `.kcs` canonicalization, or canonical-parent comparison on this path.

The closest validation does not restore the invariant. `Repository::validate` invokes scope validation at `crates/kcs-core/src/scope.rs:235-238`, but `validate_scope` checks only JSON shape, `scope_id` syntax, and format version at `crates/kcs-core/src/scope.rs:889-909`. Although init records the canonical root in `scope_path` at `crates/kcs-core/src/scope.rs:167-175`, validation never reads or compares that field. The schema itself requires only `scope_id` at `crates/kcs-core/schemas/scope.schema.json:1-16`, so a structurally valid foreign store passes.

The resulting product behavior is concretely inconsistent. `status` builds its current tree from `self.root` and compares it with the HEAD tree read through `self.store` at `crates/kcs-core/src/scope.rs:306-317`. Snapshot enumeration reads direct children from `self.root` and writes their raw bytes through the linked `ObjectStore` at `crates/kcs-core/src/scope.rs:254-303`. The snapshot path then locks the linked `kcs_dir`, writes tree and commit objects, and advances `refs/heads/main`, `HEAD`, and `manifest.json` in that foreign store at `crates/kcs-core/src/scope.rs:421-430,504-520`.

These paths are ordinary product entrypoints: CLI `status` and `snapshot` open the current directory at `crates/kcs-cli/src/main.rs:435-472`; `index` opens it, previews/scans `repo.root()`, and auto-snapshots through the same repository at `crates/kcs-cli/src/main.rs:558-580,622-635`. Repository policy says each `.kcs` manages only files directly under the folder where it is placed (`docs/03-data-model.md:150-158`) and calls the folder-local `.kcs` the authoritative truth and permission unit (`docs/10-operations.md:223-230`). Pairing one root's files with another root's live archive violates that model even without treating it as a privilege escalation.

The preserved validation ledger provides independent same-revision runtime corroboration. Four isolated two-scope checks recorded that a lure/attacker root whose `.kcs` linked to a valid victim store was accepted and that a snapshot from the lure advanced the victim `HEAD` or log: `artifacts/deep_discovery/round-01/worker-01-retry-03/findings/KCS-R01W01D-007/candidate_ledger.jsonl:2`, `artifacts/deep_discovery/round-01/worker-05-retry-01/findings/KCS-R01-W05B-006/candidate_ledger.jsonl:2`, `artifacts/deep_discovery/round-02/worker-05/findings/KCS-R02W05-004/candidate_ledger.jsonl:2`, and `artifacts/deep_discovery/round-04/worker-02/findings/R04-W02-C002/candidate_ledger.jsonl:2`.

Severity is high because a lower-trust supplied root can durably advance another scope's authoritative history and derived index through ordinary commands, creating cross-scope false evidence with downstream reliance. It is not critical: the operator must invoke KCS, the target must be a known/reachable valid store, and prior commits normally remain recoverable from the append-only object graph.

## Counterevidence and scope

- The link target must already be a structurally valid KCS store and must be readable/writable by the user running KCS; validation prevents redirecting the operation to an arbitrary non-KCS directory.
- KCS is a local CLI with no listener. A victim must invoke a read or mutating command in the supplied/shared root, and the link must resolve to a target path available in the victim's filesystem namespace.
- Newly created `.kcs` directories are hardened to owner-only access at `crates/kcs-core/src/scope.rs:152-158`. This limits target access but does not stop a lower-trust shared/archive contributor from supplying a link that the victim process resolves with the victim's permissions.
- Exact equality with stored `scope_path` is not necessarily the correct sole repair: `scope_id` is documented to survive moves/imports, and `scope_path` is optional. The reportable instance is the live symlink/alias that keeps two roots bound to one mutable store; a detached trusted move or copy is not independently adjudicated here.
- `docs/10-operations.md:285-295` lists symlink policy as a boundary that should be specified. That ambiguity reduces severity, but it does not make mixed-root status and foreign-store mutation correct under the folder-local archive model.

## Tests and remaining uncertainty

No fresh runtime fixture was created during this read-only adjudication, and no network or external service was used. The same target revision already has multiple preserved isolated reproductions, and the exact acceptance/read/write path remains present in current source.

Proof gap: none material for the symlink/alias instance. The broader copied-store wording remains intent-sensitive because portable moves/imports are supported; it is not needed for this candidate to survive.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-008 | `crates/kcs-core/src/scope.rs:188-200` | supplied/shared root with `.kcs` symlink; CLI `status`/`snapshot`/`index` | mixed reads at `scope.rs:306-317`; CAS/ref writes at `scope.rs:421-430,504-520` | reportable | valid accessible target and local invocation required; copy-only semantics not adjudicated | yes |

Validation artifacts: none (current-source trace plus preserved same-revision runtime receipts).
