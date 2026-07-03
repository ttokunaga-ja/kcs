# WS1c implementation decisions

Source: `tasks/ws1a-contract-tests.md` §C and WS1c order notes.

These are Step 1 implementation decisions only. `docs/` remains unchanged.

## Decisions

1. Lock contention: writing commands acquire `.kcs/.lock` with `create_new` and fail fast when it is held by a live process. The loser returns `KCS-E-STORE-LOCKED-001` with exit 3. Lock files include `{pid, token, created_at}`; stale recovery is allowed only when the recorded pid is not alive, and unlock removes the file only if its token still matches the owner.
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
