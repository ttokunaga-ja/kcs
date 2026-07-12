# Validation: Snapshot's regular-file check can be raced into archiving an outside-scope symlink target

- Candidate: `KCS-R23-CAND-018`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-core/src/scope.rs:261-290`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.88)**
- Method: **V10 exact static interleaving trace with the existing stable-symlink test as a negative control**

## Rubric

- [x] Normal `status` and `snapshot` entrypoints reach the affected working-tree builder.
- [x] A stable symlink is intentionally rejected by an initial no-follow file-type observation.
- [x] A concurrently writable direct-child name can change after that observation and before the read.
- [x] The later read follows the replacement path and snapshot persists those bytes in raw CAS/tree state.
- [x] No descriptor, no-follow open, inode comparison, or working-directory writer exclusion closes the interleaving.

## Evidence

The working-tree loop obtains a `DirEntry`, calls `entry.file_type()`, and skips the entry when that observed type is not a regular file at `crates/kcs-core/src/scope.rs:261-277`. That is the intended stable-symlink control: the existing CLI contract test creates a symlink and verifies it is warned about and omitted from both status and snapshot at `crates/kcs-cli/tests/contract_cli.rs:588-623`.

The control is not bound to the later read. After the type decision, the code derives the filename and applies the exclusion set, then calls `fs::read(&path)` at `crates/kcs-core/src/scope.rs:278-290`. `fs::read` opens the pathname again and follows a symlink that replaced the checked regular file. There is no `OpenOptionsExt::custom_flags(O_NOFOLLOW)`, `openat`, descriptor `fstat`, inode comparison, or post-open containment/type check on this path.

For `status`, the bytes reached through that second open are hashed into the current tree at `crates/kcs-core/src/scope.rs:290-309`. For `snapshot`, the same buffer is passed to `ObjectStore::write_raw` and bound into a `TreeEntry` at `crates/kcs-core/src/scope.rs:290-299`; `write_raw` writes the exact buffer below `.kcs/objects/raw` at `crates/kcs-core/src/cas.rs:60-75`. Snapshot reaches the builder while holding only the `.kcs` store lock at `crates/kcs-core/src/scope.rs:413-430`. That lock serializes cooperating store writers but cannot stop a lower-trust process from renaming a direct child in the working root.

The CLI exposes the path through an ordinary manual snapshot: it opens the current repository, computes a name-only exclusion set, and calls `snapshot_filtered` at `crates/kcs-cli/src/main.rs:452-472`. The source/control/sink interleaving is therefore:

1. attacker presents a regular direct child;
2. KCS observes `file_type.is_file()`;
3. attacker atomically replaces that name with a symlink to a victim-readable outside file;
4. `fs::read` follows the new target;
5. snapshot stores those bytes under the benign direct-child name.

## Counterevidence and preconditions

- A symlink already present when `entry.file_type()` runs is skipped; the issue requires a concurrent replacement after that observation.
- The attacker needs write/rename authority in the selected working directory, the victim process must be able to read the target, and the operator must invoke `status` or `snapshot`.
- Losing interleavings commonly yield a skipped entry, the benign file, or an I/O error. Exploit reliability depends on filesystem scheduling and repeated attempts.
- Raw CAS is normally protected by the owner-only `.kcs` parent, so this instance's clearest standalone impact is out-of-scope archival, misleading history, or a blocking/special-file availability effect. Separate permission or store-alias defects can amplify disclosure but are not needed to prove the correctness failure.
- The stable-symlink test proves expected behavior only for an unchanged directory entry; it is not a race control.

These constraints calibrate the issue to medium rather than high. It is still a real folder-boundary defect because the documented regular-file exclusion can be bypassed and outside bytes can enter authoritative archive state.

## Tests and remaining uncertainty

No timing stress harness was run. The task permits a complete V10 trace, and the vulnerable interleaving follows directly from two distinct pathname operations with no identity binding. Existing preserved worker validation receipts independently reached the same source-to-sink conclusion.

Proof gap: exploit reliability was not measured on a live filesystem. A minimal regression should repeatedly exchange a checked regular file with an outside symlink and assert that neither status nor snapshot ever reads the target.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-018 | `crates/kcs-core/src/scope.rs:261-290` | concurrent direct-child rename during `status`/`snapshot` | raw CAS/tree binding at `scope.rs:290-299`, `cas.rs:60-75` | reportable | stable symlinks are skipped; live race reliability not measured | yes |

Validation artifacts: none (V10 trace only).
