# Validation: Store-local consent records are forgeable or replayable across preseeded or copied scopes

- Candidate: `KCS-R23-CAND-025`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-cli/src/main.rs:6362-6378` (with store adoption at `crates/kcs-core/src/scope.rs:188-200,889-909`)
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.88)**
- Method: **V10 exact static trace + V1 focused negative control**

## Rubric

- [x] A lower-trust source can supply a self-consistent copied or preseeded `.kcs` store.
- [x] Repository open validates structure and ULID shape but not consent provenance or current-root binding.
- [x] A same-store approval row bypasses the initial approval prompt and enables the matching online adapter.
- [x] Secret-send approval is independently forgeable with the same store-local identity.
- [x] `--offline`/revocation/per-adapter checks were traced and do not authenticate a matching supplied row.

## Evidence

`Repository::open` canonicalizes only the selected working root, accepts `root/.kcs` through `is_dir`, and installs that lexical path as both `Repository.kcs_dir` and the object-store root at `crates/kcs-core/src/scope.rs:188-200`. Scope validation checks schema, a nonempty ULID, and format version at `crates/kcs-core/src/scope.rs:889-909`; `scope_path` is optional in `crates/kcs-core/schemas/scope.schema.json:1-17` and is not compared with the current root.

The writer records `root_path`, actor, timestamp, and method at `crates/kcs-cli/src/main.rs:10718-10779`. The reader at `crates/kcs-cli/src/main.rs:6362-6378` ignores all of those fields. It accepts any parseable row whose attacker-coordinated `scope_id` matches the supplied `scope.json`, whose known `tool_id` matches, and whose `execution_mode/network_opt_in` values are `online_api/true`. Because both `scope.json` and `approvals.jsonl` come from the same supplied store, the scope-ID equality is not an authenticity check.

`approval_exists` delegates to that reader at `crates/kcs-cli/src/main.rs:10418-10419`, and `run_index` skips its approval error when the supplied row exists at `crates/kcs-cli/src/main.rs:586-610`. Persistent markdown and embedding policy consumes the same row at `crates/kcs-cli/src/main.rs:6330-6350,6390-6422,10422-10445`. Embedding then reaches the normal enrichment/send path at `crates/kcs-cli/src/main.rs:7254-7263,7526-7535,7726-7768`.

The secret-release reader is weaker still: `crates/kcs-cli/src/main.rs:10543-10555` accepts any supplied row with the store's `scope_id` and `approval_method="send_secrets"`. That result decides whether secret-classified chunks remain held at `crates/kcs-cli/src/main.rs:7317-7337`.

The focused existing test `r6_foreign_approval_rows_do_not_grant_online_embedding` (`crates/kcs-cli/tests/step3_p0_contract.rs:3698-3729`) was run in isolated temporary XDG directories and passed. It is a useful negative control: copying a row from a different scope is rejected. It also pinpoints the gap, because the test changes only the row while retaining the receiving scope's `scope.json`; a supplied store controls both and can make the IDs match. Command result: 1 passed, 0 failed, 203 filtered out.

## Counterevidence and preconditions

- `--offline` and a scope-local network revocation override approval (`crates/kcs-cli/src/main.rs:6399-6418,10422-10444`).
- Network approval is per adapter `tool_id`, so a row for a different adapter does not authorize another one.
- The operator must adopt/open the supplied state and invoke an indexing, resume, retry, or search path; the machine must have an effective online adapter/provider configuration.
- Repository documentation defines opt-in as `scope x adapter` and treats `.kcs` as authoritative, portable scope state (`docs/07-adapter-spec.md:89-107`; `docs/10-operations.md:223-268,410-424`). That creates an intent ambiguity for trusted moves/backups, but it does not authenticate an untrusted preseeded store or establish that a current operator ever granted the promised explicit opt-in.
- Canonical store/root binding overlaps candidate 008, but it does not close this candidate's independent ability to forge a self-consistent approval in a non-symlinked supplied store.

## Tests and remaining uncertainty

No same-ID forged-store end-to-end send was run. No external network was contacted. The exact reader predicate and bypass are deterministic, and the foreign-ID negative control confirms the only relevant existing identity check.

The next minimal proof would clone a valid temporary store, retain its supplied `scope_id`, replace its approval actor/root fields, attach it to a new root, and use the existing mock embedding hook to show that `index --yes` reports an existing network opt-in and persists vectors without fresh approval.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-025 | `crates/kcs-cli/src/main.rs:6362-6378` | copied/preseeded `.kcs` accepted by `scope.rs:188-200` | prompt/network/secret gates at `main.rs:586-610,10422-10445,10543-10555` | reportable | requires store adoption and online adapter; portable-scope intent ambiguity | yes |

Validation artifacts: none (focused existing test used temporary fixtures and emitted no retained PoC).
