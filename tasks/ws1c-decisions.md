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
26. Step2c G2 test adapter hook: production `kcs index` uses the deterministic markdownize adapter by default. Contract/integration tests may set `KCS_TEST_MARKDOWNIZE_ADAPTER=incremental` or `reject_incremental` to inject a local deterministic adapter that advertises `incremental_update`, allowing CLI-level incremental/fallback validation without external network or mutable production adapter identity.

## Step2c final round (I1-I5) additions (2026-07-03)

27. Cost ledger storage is JSONL, not SQLite (Step2c I5). `docs/10-operations.md` / `04-pipeline.md` describe the cost ledger as a SQLite table, but the MVP persists it as append-only JSONL at `$XDG_DATA_HOME/kcs/cost-ledger.jsonl` (rows `{month, scope_id, adapter_kind, usd}`, decision #22). Rationale: Step 2 has no other SQLite dependency, and append-only JSONL is crash-safe and trivially inspectable for a single-writer CLI. The SQLite migration is deferred to Step 3, where it is introduced together with the search `index/sqlite.db`, so both live databases land in one change rather than two.
28. Hermetic HTTP tests are Step 3 backlog (Step2c I5). The online adapter's HTTP layer (`EnvMistralOcrClient` model-pin resolution + OCR POST) is exercised for real against the live API under `experiments/ocr-verification`, which is where correctness of the wire format is guaranteed. In-process contract/integration tests inject failures and successes through the `KCS_TEST_MISTRAL_OCR` hook (`mock`/`partial`/`mock_link_image`/`auth_error`/`rate_limit`) and never open a socket. A hermetic local HTTP server test (spinning a fake Mistral endpoint) is deferred to Step 3 backlog; it adds a test-server dependency for coverage that the live-API experiment already provides.
29. Retry backoff jitter is omitted (Step2c I2). `RetryPolicy.backoff` descriptors advertise `full_jitter`, but `retry_backoff_seconds` computes the deterministic schedule only — exponential `min(base * 2^(attempts-1), cap)` for `exp(...)`, the parsed fixed duration for `fixed(...)`, and (absent a server `Retry-After` header locally) the same exponential schedule for `retry_after`. Jitter is intentionally dropped so `next_retry_at` is reproducible under `KCS_FIXED_NOW` and testable without flakiness. Real jitter (to avoid thundering-herd on shared endpoints) is a Step 3 concern once concurrent batch execution exists; single-user serial CLI retries do not need it.
30. `MistralOcrMarkdownizeAdapter::profile()` is network-free (Step2c I5). `profile()` no longer calls `resolve_model_pin` (which issues `GET /v1/models` for `*-latest` aliases); the pin is resolved exactly once at execution time in `run_mistral_adapter` and passed in as `configured_model`, so the profile reflects the resolved pin without a second GET. When the adapter still holds an unresolved `*-latest` alias (only the `Default`/unit-test construction), `profile()` derives a deterministic immutable placeholder (`<family>-unresolved`) instead of contacting the network — identical to the prior no-API-key fallback and accepted by the identity layer (a mutable alias is rejected as a `model_version_pin`). tool_profile_hash impact: for the production and mock paths the pin is resolved before construction, so their `tool_profile_hash` is unchanged; only the network-free `Default` adapter (used solely by `placeholder_mistral_profile_declares_ocr`, which asserts capability flags/id, not the hash) sees the same `mistral-ocr-unresolved` pin it already produced when no API key was present. Chosen because it keeps identity stable for real runs while removing the only networked path out of `profile()`.

## Step3c K round additions (2026-07-03)

31. `kcs open` returns resolution JSON instead of launching an OS opener (Step3c 裁定 (c) の記録).
    `docs/06-cli-spec.md` §1 describes `open` as "原本をアプリで開く"; the Step 3 implementation
    resolves the pointer and returns `{path, ...}` JSON (working tree path, or a CAS temporary
    expansion under `$XDG_DATA_HOME/kcs/open/`), leaving the actual OS launch (`open`/`xdg-open`)
    to the caller. Rationale: the OS launch is a final thin layer that is untestable in CI and
    irrelevant to the resolution contract (08 §3); agents consume `--json` anyway. The audit round
    (tasks/step3c-fixes.md) accepted this within Step 3 scope on condition it is recorded here.
    The OS-launch layer is Step 4+.
32. New error codes for the K6 evidence resolver (Step3c). `KCS-E-PURGE-TOMBSTONED-001` (exit 4)
    carries the 08 §4.1 tombstone response (`status="purged"` body in `context`) when `kcs open` /
    `kcs view` hit a tombstoned raw_hash — 08 §4.1 fixes the response shape but names no code, and
    06 §8's code list is explicitly examples ("例:"), so a PURGE-domain code is minted here.
    `KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001` (exit 4) covers 08 §3.1 step 1b "曖昧なら候補一覧 error"
    (multiple registry entries for one scope_id sharing the newest `last_seen_at`); the candidate
    list is returned in `context.candidates`. Both codes follow the 06 §8 DOMAIN namespace; adding
    them to the docs' example list is deferred to the next docs edit window.
33. New error code for the 08 §3.2 retarget contract (Step3c re-audit fix).
    `KCS-E-EVIDENCE-RETARGET-REQUIRED-001` (exit 8, per 06 §7 "tool_profile_hash 不一致で chunk
    解決不能 (retarget 要) は 8") is returned by `kcs open` / `kcs view` when the pointer's scope,
    commit, and raw_hash all resolve (and no tombstone applies) but no chunk row exists for the
    pointer's `chunk_hash` — 08 §3.2: "tool_profile_hash 不一致: chunk が存在しない場合は retarget
    が必要 (§5)". `context` carries `{chunk_hash, tool_profile_hash, raw_hash}`. The check does not
    require tree-entry profile equality (Step-1 raw-only trees carry no `normalize` ref; an
    existing chunk row is self-certifying because `chunk_hash` commits to its `tool_profile_hash`).
    08 §5 names no code and 06 §8's list is examples ("例:"), so an EVIDENCE-domain code is minted
    here; docs sync is deferred to the next docs edit window. `kcs evidence retarget` itself
    remains Step 4.

## Step 4 checkpoint fixes (L1-L8) additions (2026-07-04)

34. Per-adapter network opt-in (L4). `kcs index --approve` / `--yes` records **one approval row
    per configured online adapter**: the markdownize marker `mistral_ocr_markdownize` always, plus
    the embedding adapter `gemini_embedding_2` when an embedding adapter is configured
    (`KCS_TEST_GEMINI_EMBED` / `GEMINI_API_KEY`). Each row's `network_opt_in` mirrors the method
    (`--approve` → true, `--yes` → false), unchanged from before. The embedding network gate reads
    its **own** `tool_id` row (`persistent_network_allowed_for` / `embedding_online_allowed`), not
    the markdownize approval it used to ride on (07 §3: opt-in unit is scope × adapter). The
    index-path embedding online decision now also flows through this per-adapter check rather than
    the transient `network_allowed` (markdownize) result.
35. L4 backward compatibility + revoke scope. A scope approved before per-adapter rows existed
    carries only the `mistral_ocr_markdownize` row, so a later run with an embedding adapter finds
    no embedding opt-in row → embedding stays **enqueue-only** (tasks Pending, surfaced by
    `index_status`), never silently calling the embedding API. Revocation stays **global**:
    `kcs index --revoke-network` writes `allow_network = false` in config.toml, and the per-adapter
    gate checks `network_revoked` first, so a revoke gates *every* online adapter (embedding
    included). Selective per-adapter revoke is intentionally not exposed (no CLI surface for it) and
    deferred; a global network revoke stopping the embedding adapter is the desired conservative
    default.
36. reindex / repair enrichment (L1). `kcs reindex --force` and `kcs repair --rebuild-db` run the
    embedding enrichment pass after the SQLite rebuild (docs/06 "再 normalize / 再 embedding"),
    symmetric with `kcs index`. Online only under the embedding opt-in (#34); offline it enqueues
    Embedding tasks so `index_status` reports them pending instead of the prior false
    enriched_ratio = 1.0 / pending = 0 (the tasks were never created). Note: `rebuild_chunk_vec`
    already re-derives `chunk_vec` from `embeddings` by `text_hash`, so an unchanged-content
    reindex needs no new embedding work (content reuse); only a chunking-config change (new
    `text_hash`) forces real re-embedding — the acceptance test uses a smaller `max_chars` to
    exercise that path.
37. Short-hash resolution unified on SQLite tree_entries (L3). `resolve_short_hash` /
    `load_searchable_chunks` read the live tree_entries from `index/sqlite.db` via
    `ensure_snapshot_tree_entries` (the same lazy HEAD projection search uses), and the JSON
    `index/tree_entries.json` projection is **removed entirely** (`write_tree_entries` /
    `read_tree_entries` / `tree_entries_path` deleted). The JSON went stale right after a bare
    `kcs snapshot` (which advances HEAD without refreshing it), so short-hash `view`/`open` failed
    with KCS-E-CONFIG-USAGE-001 while search succeeded — the asymmetry L3 fixes. SQLite
    tree_entries is now the single projection source.
38. Embedding billing/failure on the sent portion only (L5/L6). `run_embedding_enrichment` splits
    each batch into content-addressed reuse (free, no adapter call) and to-send chunks. Budget
    judgement and the cost-ledger charge use only the actually-sent chars (reuse is never billed).
    Reuse links are written and their tasks completed **before** the send, so an adapter failure on
    the sent portion cannot flip an already-materialized (chunk_vec written) reuse chunk into a
    stuck Failed task. Failed embedding tasks are owned by `batch retry` (L7): a chunk whose
    embedding task is Failed with an unelapsed `next_retry_at` or a non-retryable error is skipped
    by the enrichment target selection, mirroring markdownize.
39. L8 docs sync applied in this round (not deferred): 03 §8.1 embedding identity documents
    `target_hash = <text_hash>` (the content-based-reuse basis, consistent with 04 §4.3/§5.4);
    04 §5.4 adds the resume/retry/reindex enrichment-execution + `--override-budget` symmetry note;
    04 §5.5 adds the sent-only billing / reuse-not-contaminated note; 06's `batch resume`/`retry`
    lines note they drive both markdownize and embedding.

## Exploratory-audit fixes (M1-M8) additions (2026-07-04)

40. New error code `KCS-E-EVIDENCE-POINTER-INVALID-001` (M6). The Evidence Pointer resolver now
    binds identity: the tree entry for `pointer.raw_hash` must carry the same
    `normalize.tool_profile_hash` as the pointer, and the chunk row selected by `chunk_hash` must
    match the pointer's `(raw_hash, tool_profile_hash)`. A pointer that pairs raw_hash B with a
    chunk_hash materialized under raw_hash A ("raw is B, body is A") is a tampered/internally
    inconsistent pointer and is rejected with this code (exit 4, a dead-pointer failure like the
    purge family). The code is **not** in the 06 §8 / 10 §7.5 catalog yet (docs frozen this round);
    it slots beside `KCS-E-EVIDENCE-RETARGET-REQUIRED-001` (also code-only). Distinct from
    RETARGET-REQUIRED, which means "chunk not materialized under this tool_profile_hash" (a
    legitimate retarget), whereas POINTER-INVALID means the pointer's own fields don't mutually bind.
41. `object` URI CAS dispatch by type (M7). `kcs open/view kcs://<scope>/object/<type>/<hash>` now
    routes to the correct CAS directory (03 §2): `raw` → `objects/raw` (working-tree-first, rename
    tolerant), `image` → `objects/images`, `prepared` → `objects/prepared`. Previously every type
    fell through to `objects/raw`, so an image object (which only lives under `objects/images`) was
    never found. `normalized` is intentionally **not** resolvable via a single-hash object URI: the
    full-text view is path-named `<raw_hash>.<tool_profile_hash>.g<gen>.md` (03 §2.1, content hash
    not adopted), so one `sha256:` segment cannot address it — it returns invalid usage (exit 2)
    rather than silently mis-routing.
42. Store lock is now reentrant and wraps whole mutating commands (M1a). `StoreLock` (05 §6) is made
    reentrant within a process/thread via a thread-local depth counter, and `kcs index` / `repair` /
    `reindex` acquire it end-to-end (`Repository::lock_store`) instead of only across the snapshot
    sub-step. The reentrancy is required because the internal auto-snapshot re-acquires the same
    lock; without it the whole-command lock would self-deadlock. Losers of a concurrent acquisition
    still fail fast with `KCS-E-STORE-LOCKED-001` (exit 3), unchanged. search/status/view/open stay
    lock-free (read-only, 05 §6).
43. JSONL append atomicity + corrupt classification (M1b/M1c). Every O_APPEND JSONL writer now frames
    one record (`serde_json::to_string` + `\n`) into a single `write_all`, so concurrent appends
    (notably the device-global `cost-ledger.jsonl` written cross-scope, which no per-`.kcs` lock
    covers) cannot interleave byte-wise. Parse failures reading `tasks.jsonl` /
    `cost-ledger.jsonl` are now `KCS-E-STORE-CORRUPT-001` (exit 4, carrying the file path) via a new
    `PipelineError::Corrupt` variant, instead of being misreported as `KCS-E-CONFIG-SCHEMA-001`
    (exit 2).
44. User config schema validation + budget non-negative guard (M8). The device `config.toml`
    (`$XDG_CONFIG_HOME/kcs/config.toml`) is now validated against `config.schema.json` before
    dispatch (`validate_user_config`), closing the gap where only the folder `.kcs/config.toml`
    (validated on `Repository::open`) and `tools.toml` were checked — a negative user budget cap now
    fails with exit 2. `read_budget_config` also rejects negative `monthly_usd_cap` / per-adapter
    caps as defense-in-depth behind the schema's `minimum: 0`.
