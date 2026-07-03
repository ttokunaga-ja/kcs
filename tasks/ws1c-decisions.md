# WS1c implementation decisions

Source: `tasks/ws1a-contract-tests.md` §C and WS1c order notes.

These are Step 1 implementation decisions only. `docs/` remains unchanged.

## Decisions

1. Lock contention: writing commands acquire `.kcs/.lock` with `create_new` and fail fast when it is held by a live process. The loser returns `KCS-E-STORE-LOCKED-001` with exit 3. Lock files include `{pid, token, created_at}`; stale recovery is allowed only when the recorded pid is not alive (liveness via `ps -p`, chosen over `kill -0` whose EPERM/ESRCH exit codes are indistinguishable; spawn failure counts as alive = no reclaim), and unlock removes the file only if its token still matches the owner. Known limitation (2026-07-03 audit N2): unlink-based reclaim retains a microscopic TOCTOU window between re-validation and `remove_file`; acceptable for Step 1 (single-user, human CLI frequency) — revisit before any multi-writer usage.
2. Step 1 raw-only tree entries omit `normalize`. This follows `docs/03-data-model.md` §8 optional `normalize`; Step 1 generates only `{path,type,raw_hash}` entries.
3. Manual snapshot with unchanged tree is a no-op: no commit is created, HEAD remains unchanged, exit 0.
4. Step 1 status vocabulary is `new`, `modified`, `deleted`, `unchanged`. `up_to_date` is reserved for the normalized-instance meaning in `docs/03-data-model.md` §6.
5. `kcs init` on an existing `.kcs` is a no-op with exit 0 and keeps `scope_id`. `kcs init <path>` for a nonexistent path returns exit 2.
6. `kcs tag <name> [<commit>]`: same-name retag returns exit 2. If `<commit>` is omitted, HEAD is used.
7. `kcs diff <a> <b>` reports `added`, `modified`, `deleted` and exits 0 regardless of whether differences exist.
8. `kcs inspect <hash>` for a missing object returns `KCS-E-STORE-NOT-FOUND-001` with exit 4.
9. `kcs log` walks first-parent history from HEAD, newest first. `--at` and `--since` are parsed but return "not implemented" with exit 1.
10. Generated `created_at` timestamps use second precision UTC ISO8601 with `Z`.
11. Step 1 tree entry `type` is `"file"` only. Other values are schema violations.
12. `status` and `diff` are read-only and do not acquire `.kcs/.lock`. `tag` is treated as a writing command and does acquire the lock.
13. `manifest.json` file rows are generated/updated by `snapshot`. `status` is read-only and computes states from the working tree and HEAD tree.
14. Step 1 implements only the seven commands in scope. Out-of-scope commands are parse-only placeholders and return "not implemented" with exit 1; no pipeline/search/GC/purge behavior is implemented.

## WS1c should-fix round additions (2026-07-03)

15. Non-UTF-8 file names (S6): a scope-directory entry whose name is not valid UTF-8 is **skipped with a stderr warning** (`warning: skipping non-UTF-8 file name: <path>`), not treated as a whole-snapshot failure. It cannot be a tree-entry `path` anyway (paths are UTF-8), and one un-nameable file must not block indexing the rest of the folder. Same warning channel as the symlink skip (S5).
16. HEAD / refs/heads/main two-stage advance (S6): `snapshot` advances `refs/heads/main` then `HEAD` with two separate atomic renames. Each rename is individually crash-safe, but a power loss *between* them can leave `refs/heads/main` ahead of `HEAD`. The commit object is already durable in the CAS, so recovery only re-points HEAD and no data is lost. A single atomic multi-ref transaction is out of scope for single-user Step 1; documented as a known limitation in code (`scope.rs` snapshot ref-update site). No code change.
17. `KCS_FIXED_NOW` (S4): the environment override for the current time is gated behind `#[cfg(debug_assertions)]` (helper `fixed_now_override`), covering both `now_utc_seconds` and the `snapshot` `created_at` path. Release binaries ignore it, so a production `created_at` cannot be forged via the environment. Contract tests build in debug and are unaffected.
18. `created_at` acceptance (S6): validated strictly as `YYYY-MM-DDTHH:MM:SSZ` (digit positions, separators, and month/day/hour/minute/second ranges). An optional fractional-second suffix `.NNN…Z` is also accepted to honor `06 §12`'s microsecond allowance; KCS itself always generates second precision (decision #10).
19. Error-code overload split (S3): usage/operand errors use `KCS-E-CONFIG-USAGE-001` (distinct from schema-violation `KCS-E-CONFIG-SCHEMA-001`); duplicate tree paths use `KCS-E-STORE-DUP-001` (distinct from the `/`-in-path `KCS-E-STORE-PATH-001`). Both keep their prior exit codes (2). JCS is now provided by the `serde_jcs` crate rather than a hand-rolled canonicalizer (S1), with byte-identical hash vectors.

## Step 2 implementation decisions (2026-07-03)

20. Incremental consecutive counter (Step2a C-6): count per file_id. Any full run, including full fallback, resets the counter.
21. `task_id` / `run_id` (Step2a C-7): use ULID-compatible strings with `task_` / `run_` prefixes.
22. Cost ledger schema (Step2a C-8): the minimum monthly ledger row is `{ month TEXT UTC, scope_id TEXT, adapter_kind TEXT, usd REAL }`. Month boundaries use UTC.
23. Quarantine release record (Step2a C-9): append one approval-record-shaped JSONL row with `approval_method` to the same approval log used for initial scan approval.
24. Scanned PDF without text layer (Step2a C-10): deterministic baseline prepare emits no unit and leaves the file pending for AI enhancement.
25. Image placeholder replacement (Step2a C-11): replace Mistral OCR `images[]` placeholders by occurrence order with `![...](kcs://<scope_id>/object/image/<image_hash>)`.
