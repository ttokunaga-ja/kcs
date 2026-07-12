# Validation: Opening an existing permissive `.kcs` exposes future private archive bytes

- Candidate: `KCS-R23-CAND-024`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-core/src/scope.rs:126-158,188-200`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.97)**
- Method: **V7 isolated target-binary permission control + V10 exact write-path trace**

## Rubric

- [x] Repository policy explicitly requires owner-only protection for `.kcs` archive state.
- [x] The existing-store init path returns through `open` before owner hardening runs.
- [x] `open` validates store contents but does not reject or repair unsafe owner/mode/type state.
- [x] An isolated target-binary control confirmed that re-init leaves a valid 0755 store permissive.
- [x] A snapshot of a 0600 source created a readable 0644 raw object under that traversable store.

## Evidence

New-store creation explicitly treats the parent mode as the archive confidentiality boundary. `Repository::init` creates the store and calls `restrict_dir_to_owner` at `crates/kcs-core/src/scope.rs:141-158`; its comment states that raw objects contain verbatim document bytes and that none of the tree should be group/world-readable on a multi-user host. The helper sets Unix mode 0700 at `crates/kcs-core/src/scope.rs:1650-1660`. The focused contract test independently asserts this mode for a newly initialized store at `crates/kcs-cli/tests/step3_p0_contract.rs:3096-3116`.

Existing stores bypass that control. Once `root/.kcs` exists, `init` returns `Self::open(root)` at `crates/kcs-core/src/scope.rs:135-139`, before the hardening call. `Repository::open` checks only link-following `is_dir`, builds the repository, and validates logical store files at `crates/kcs-core/src/scope.rs:188-205,235-239`; it does not use `symlink_metadata`, inspect owner UID or permission bits, call `restrict_dir_to_owner`, or reject a store controlled by another local principal.

The write path makes the omission consequential. Snapshot reads direct-child bytes and calls `ObjectStore::write_raw` at `crates/kcs-core/src/scope.rs:254-303`. The object store creates fanout directories and publishes the raw bytes at `crates/kcs-core/src/cas.rs:60-75,155-176`. `File::create` inherits the process umask; there is no per-object chmod because the implementation deliberately relies on the 0700 parent.

An isolated `/tmp` target-binary control used private HOME/XDG directories and no network:

- fresh `kcs --json init` created `.kcs` mode 0700;
- after changing it to 0755, a second `init` returned `status="already initialized"` and left mode 0755;
- a mode-0600 `notes.txt` containing `victim-only bytes` was snapshotted;
- the resulting raw CAS object contained those exact bytes and had mode 0644 under the traversable 0755 store.

The fixture was deleted after the check. This demonstrates new disclosure caused by continuing to use the permissive store: the source file itself remained unavailable to group/other while KCS created a readable archive copy.

## Counterevidence and preconditions

- The mode proof is Unix-specific; `restrict_dir_to_owner` is intentionally a no-op on non-Unix systems, whose ACL semantics were not assessed.
- A lower-trust participant must precreate/supply a structurally valid writable store, or an existing store's mode must become permissive, and the victim must later archive private direct-child content.
- A process umask of 0077 can make newly created raw files owner-only even under a traversable parent. That is not an invariant KCS enforces, and an attacker-owned/writable store still creates integrity and metadata risks.
- If a permissive store already contains secrets, some exposure predates KCS's next open. The reportable behavior is that open accepts the unsafe boundary and subsequent normal commands add new private bytes to it.
- A read-only trusted archive is a supported operational case, so remediation should distinguish safe read-only access from mutating adoption rather than blindly chmod every path.

Severity is high because a lower-trust precreated store can convert victim-only direct-child files into attacker-readable authoritative raw objects through an ordinary snapshot/index workflow. It is not critical because it requires local filesystem setup, a valid store, victim invocation, and a multi-principal permission boundary.

## Tests and remaining uncertainty

The isolated control reproduced both the retained unsafe mode and the new readable raw copy. No second OS account was created; Unix DAC behavior after observing modes 0600/0755/0644 is deterministic.

Proof gap: non-Unix ACL/ownership behavior was not tested. There is no material Unix proof gap for the validated path.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-024 | `crates/kcs-core/src/scope.rs:126-158,188-200` | valid permissive/precreated `.kcs` adopted by `init`/`open` | raw CAS creation at `scope.rs:254-303`, `cas.rs:60-75,155-176` | reportable | Unix-specific; valid writable store and victim mutation required | yes |

Validation artifacts: none (ephemeral `/tmp` fixture was removed).
