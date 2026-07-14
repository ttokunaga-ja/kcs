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

## Second exploratory-audit round (N1-N8, tasks/step3-bughunt2-fixes.md)

45. Tier B online hold + explicit `--send-secrets` approval (N1). A candidate-secret file
    (`secrets_tier_b_warning`: name contains credentials/secret/token/apikey/password) is still
    ingested locally, but its **online** work is now HELD instead of being enqueued like a normal
    file (the leak: `ignored=false` produced ordinary online markdownize/embedding tasks that
    `index --online`/`batch resume` shipped). Hold mechanics: the online markdownize placeholder and
    each Tier B embedding task are written `Paused` with `fallback_reason = "secrets_tier_b_hold"`
    (visible in `kcs status`); `batch resume` does not un-hold them and
    `execute_pending_markdownize_tasks` / the embedding send-partition skip them (defense in depth).
    Release is an explicit, persistent, per-scope approval recorded by the new `index --send-secrets`
    flag (marker `.kcs/secrets-approved.jsonl`, checked by `secrets_send_approved`), distinct from
    `--approve` (scan/network opt-in) because shipping a probable secret needs its own consent. This
    build implements **hold + explicit-flag approval only**; the 10 §1.1 interactive confirmation
    prompt is not implemented. `record_quarantine_candidates` now also records Tier B (reason
    `secrets_tier_b`, `approval_method` `hold`/`send_approved`); the append-only dedup by path means
    a file first recorded as `hold` keeps that first record even after later approval (audit trail,
    not current-state — the live disposition is the task state).
46. Manual snapshot honors the Tier A exclusion set (N2). `kcs snapshot` was `repo.snapshot(msg,
    None)` with no filter, baking `.env`/`*.pem` plaintext into `objects/raw` + the latest tree
    (irreversible, 10 §1.1). The CLI now computes the excluded Tier A set from `build_scan_preview`
    (the same classifier `kcs index` uses) and passes it through a new
    `Repository::snapshot_filtered`; kcs-core still has no notion of secrets (the CLI owns the
    exclusion set), preserving the layer boundary.
47. Observation-log redaction (N3). `append_observation` (events/errors.jsonl) now masks the
    `path`/`query`/`prompt` fields of `context` recursively to `[redacted]` when `redact_logs` is in
    effect (06 §8 default true; read from the device `[adapter.policy]` config, secure-default when
    absent). This fixes `KcsError` contexts writing paths verbatim into `errors.jsonl` and the purge
    scrubber's "path is never recorded" assumption. Only the log files are redacted; the stdout error
    JSON (`to_error_json`) is unchanged.
48. Commit-ref path-traversal guard (N4). `resolve_commit` (and `tag`) validate the operand up front
    via a shared `validate_ref_operand`: a ref is only ever `HEAD`, a hash, or a tag name, so `/`,
    `\`, `.`, `..`, an absolute path, or any `ParentDir`/`RootDir`/`Prefix` component is rejected
    (`KCS-E-CONFIG-USAGE-001`, exit 2) before any `refs/tags`.join. Closes the `kcs diff`/`kcs tag
    <commit>` existence-oracle for out-of-scope files (03 §3).
49. Evidence Pointer generation binding (N5). `resolve_pointer_for_cli` now binds the resolved
    chunk's `gen` to the tree entry's `normalize.gen` on a **non-shallow** commit, rejecting a
    pointer that keeps an old commit but splices in a newer-generation chunk_hash produced by
    `reindex --force`. Scope decision: the gen binding applies **only when the tree entry carries an
    explicit `normalize`** (the reindex-tampering target — the index commit — always does). A tree
    entry with `normalize = None` (e.g. a bare `kcs snapshot` that advanced HEAD without re-recording
    normalize refs, L3) has no gen to bind and keeps the pre-existing chunk (raw, tool) identity
    check; requiring `normalize` there would break `ct3_l3_short_hash_resolves_after_bare_snapshot`.
    This is "the commit's tree-entry gen == chunk gen", never "always the latest gen"
    (`ct3_reindex_002` — an old pointer to a commit whose entry is gen N still resolves its gen-N
    chunk). The `None`-normalize gen gap is pre-existing (M6-era), separate from the N5-cited attack.
50. Chunking is O(N) per unit, not O(N²) (N6). `slice_chars` / `split_range_by_max_chars` now index a
    once-built `Vec<char>` per unit instead of re-running `chars().skip(start)` on every span/split
    (the old dominant cost was the per-single-char whitespace-skip slice during splitting). Output
    bytes are unchanged — the frozen chunk_hash vectors (CT3-CHUNK-001/002/003) and the split tests
    stay green; only wall-time improves.
51. `--online` reaches embedding enrichment (N7). `embedding_online_allowed` gained an `online`
    argument with precedence offline → online (per-invocation, mirrors markdownize's `network_allowed`:
    enabled only when the scope carries an approval record and is not network-revoked) → persistent
    embedding opt-in. Previously `index --online` embedded nothing because only markdownize honored
    the flag.
52. Short-query search short-circuit moved after scope resolution (N8). A `< 2`-char query no longer
    returns before scope enumeration/all-failed detection/index_status aggregation, so it can no
    longer mask a scope failure (exit 4) or pin `index_status` to a fixed `1.0`. `empty_search_response`
    now reports the real searched scopes + aggregated `index_status` and honors partial-failure exit 3.

## Third exploratory-audit round (O1-O7, tasks/step3-bughunt3-fixes.md)

53. Cursor cannot bypass a scope restriction, and cursors are signed (O1). (a) On a cursor replay
    `run_search` now also calls `enumerate_scope_targets` to compute the scopes the caller's
    `--scope`/`--descendants` permit, and **intersects** the cursor's frozen scope set with that
    allowed set; a cursor scope outside it is excluded with reason `scope_restriction_mismatch`
    (not searched). For a plain page-2 replay (no `--scope`) the allowed set is every registered
    scope, so this is a no-op. Previously the cursor branch trusted `resolve_cursor_exec_scopes`
    alone, so `--scope . --cursor <other-scope's cursor>` read straight out of the other scope
    (Agent-API sandbox break, 05 §1.7 / 06 §9). (b) Cursors are now HMAC-SHA256-signed with a
    device-local key at `$XDG_DATA_HOME/kcs/cursor-key` (0600, generated from `/dev/urandom` on
    first use). The wire form is `base64url(JCS(token)).base64url(HMAC)` — the inner payload is the
    exact prior encoding, so it stays URL-safe/pad-free. `encode_cursor_token`/`decode_cursor_token`
    took a `key: &[u8]` parameter (kcs-search stays filesystem-free; the CLI owns the key); decode
    verifies the signature (constant-time) and a forged/tampered token is `KCS-E-SEARCH-CURSOR-001`
    (exit 2) before its scope set is ever trusted. `query_hash` (public inputs only) is no longer the
    sole integrity check. HMAC is implemented over the existing `sha2` dep (no new crate).
54. Query embedding is sent only for a vector-resolving, opted-in search (O2). `compute_query_embedding`
    (a real Gemini send) was called **unconditionally** before mode resolution, so `--text` /
    non-opted-in searches with a live `GEMINI_API_KEY` shipped the query text out (07 §3 opt-in
    violation). It now runs only after `resolve_search_mode`, and only when the resolved mode is
    vector/hybrid. `resolve_vector_availability` gained an `embedding_opt_in` input (persistent
    embedding opt-in, `gemini_embedding_2`) and judges availability from cheap predicates
    (endpoint → per-scope compat → **opt-in** → query length ≥ 2) instead of an eager adapter call;
    a compatible index without the opt-in reports `embedding_opt_in_required`. A live adapter failure
    after the (now-gated) send still degrades vector→text (`--vector` errors, auto/hybrid falls back),
    preserving the pre-O2 fallback. Precedence keeps `embedding_index_missing` ahead of the opt-in
    reason so an unembedded scope's message is unchanged. Test seam: `KCS_TEST_QUERY_EMBED_TRACE`
    marks the send point so `--text` can be proven to never reach it.
55. `batch resume`/`batch retry` hold the store lock; `replace_all` uses a unique temp (O3). `run_batch`
    now acquires `repo.lock_store()` end-to-end (the same M1 lock on index/repair/reindex; reentrant
    with the inner auto-snapshot; losers get `KCS-E-STORE-LOCKED-001` exit 3), so two concurrent
    resumes can no longer interleave `tasks.jsonl` + the device cost-ledger into a double send.
    `TaskStore::replace_all` also stopped using the fixed `tasks.jsonl.tmp`; it now writes through a
    pid+nanos+seq unique temp created `O_CREAT|O_EXCL` (defense in depth for any other caller).
56. PDF page-count lookahead is char-boundary safe and unified (O4). `pdf_page_count`'s
    `&text[index..index+N]` windows around `/Type`/`/Page` panicked (`char boundary`, exit 101, body
    dumped to stderr) when a multibyte char straddled the window. The four sites (prepare.rs +
    deterministic.rs) collapse onto one shared `kcs_adapter::deterministic::pdf_page_count_in_text`,
    which clamps each window back to the nearest char boundary (`bounded_str_window`). prepare.rs now
    delegates to the adapter copy (pipeline already depends on adapter), removing the duplication.
57. `rebuild_sqlite_index` creates the index dir unconditionally (O5). A 0-chunk scope (empty folder /
    secrets-only / text-less PDF) skipped `append_stored_chunks` and never created `.kcs/index/`, but
    the auto-snapshot advanced HEAD; the rebuild then failed opening a missing `sqlite.db` (exit 2)
    and re-index stayed stuck at "commit but no index". The rebuild now `create_dir_all`s the index
    dir first, so an empty scope indexes cleanly (exit 0).
58. Short `sha256:` operand is validated (O6). `open`/`view` sent a `sha256:` operand straight into
    `cas_object_path`'s `digest[0..2]`/`[2..4]` slices, so `sha256:a` panicked out of range. A new
    `validate_short_hash_operand` at the entry of `classify_short_hash` requires a lowercase-hex
    digest ≥ 4 chars, rejecting malformed operands with `KCS-E-CONFIG-USAGE-001` (exit 2).
59. Cursor scope resolution detects scope_id collisions like Evidence (O7). `resolve_cursor_exec_scopes`
    took `lookup_scope_id().next()` unconditionally, silently pinning a `.kcs`-copy collision to one
    winner. It now shares `resolve_scope_id_in_registry` with the Evidence path (`resolve_scope_target`),
    so two distinct `.kcs` at the newest `last_seen_at` are ambiguous
    (`KCS-E-EVIDENCE-SCOPE-AMBIGUOUS-001`, exit 4); an unresolvable scope stays `unreachable`
    (partial failure), unchanged.

## Windows portability closure (2026-07-13)

60. Windows user-directory fallback. Absolute `XDG_*` overrides remain highest priority and relative
    values remain invalid. An absolute `HOME` is next. On Windows only, missing/invalid `HOME` falls
    back to `SHGetKnownFolderPath(FOLDERID_Profile)` and keeps the documented `.config`,
    `.local/share`, and `.cache` suffixes. Unix keeps the existing fail-closed contract. A registry
    path that has no absolute base is now an error even through the library API; it never degrades
    to the current directory.
61. Open/view cache leaves are derived, not copied. The physical leaf is fixed ASCII
    `open-<sha256(logical basename)>` with only a separately validated short ASCII extension kept for
    OS association. This handles reserved devices, ADS colon, forbidden punctuation, and trailing
    dot/space without placing the logical basename on disk.
62. New tags require one host-independent portable logical-leaf rule and use
    `refs/tags-v1/tag-<sha256(NFC + Unicode lowercase)>` as the canonical physical ref. The
    versioned directory is disjoint from legacy `refs/tags/<logical-name>`, so an old raw tag that
    looks like `tag-<digest64>` cannot alias another tag's canonical ref. Case/normalization variants
    collide on every OS and `HEAD` case variants remain reserved. Existing raw-name Unix refs remain
    a bounded, validated read fallback; multiple canonical/legacy representations must agree or the
    store fails closed.
63. Persisted tree-entry paths are validated as logical direct-child names independently of the
    reader OS. New snapshots and future restore destinations apply the current filesystem's stricter
    materialization rule before constructing a path. This preserves Windows reads of Unix history
    containing names such as `CON`, `?`, `:`, trailing dot/space, or a literal backslash without
    permitting those names to escape or materialize unsafely. Read-only status/diff retains the
    logical `relative_path` but omits the absolute physical `path` when the host cannot materialize it.

## Step 4 contract freeze (2026-07-13)

64. Canonical phase boundaries win over stale kickoff prose. Step 4 implements single-pointer
    `evidence verify`; verify batch, retarget, export/import, `kcs move`, `kcs gc`, retention, and full
    purge DAG rewriting remain Phase 4+/v2. `docs/11-requirements.md` is not a current source.
65. Time-travel has one effective selector. `--since` implies all-history and freezes its page-1 UTC
    cutoff inside the signed cursor; duration grammar is positive `s/m/h/d/w`. `--at` resolves per
    selected scope and uses existing partial/all-failed multi-scope behavior. Explicit-at shallow is
    always `KCS-E-COMMIT-SHALLOW-001`, even if cached tree rows survive. The cursor carries canonical
    `time_travel`; selector-less replay inherits it and repeated selector flags must match exactly.
66. Historical path reporting preserves the frozen M3-2 alias criterion without changing chunk
    identity. All-history/since expands one chunk to each distinct historical path binding, collapsing
    repeated `(chunk,path)` appearances across every commit reachable from the page-1 snapshot HEAD via
    all parent edges. The backing commit is the ancestor-most introduction; incomparable introductions
    tie-break by full commit hash. Each alias carries sorted page-1 snapshot `current_paths`; singular
    `current_path` is emitted only for exactly one live snapshot path, so twins are unambiguous. An unchanged rename therefore
    returns old/new path hits backed by one path-independent chunk row.
67. Historical reindex is enrichment-only. `reindex --at` never bumps normalized gen or moves HEAD;
    it fills missing current-chunk-config chunks/embeddings for the selected snapshot under normal
    consent/budget rules. `--force --at` is invalid; existing HEAD `--force` keeps gen+1 semantics.
68. Evidence verify has exactly three completed states (`alive`, `tombstoned`, `not_found`). Non-strict
    returns exit 0 for every completed inspection; strict keeps the state payload but exits 4 for dead
    states. Scope resolution failure is an error, not a fourth state. Verify is bounded, no-follow,
    lock-free, content-free, and never materializes/open-caches data.
69. Chunk CAS becomes durable truth for Step 4 verify/fsck. SQLite and `chunks.jsonl` remain acceleration
    and rebuild inputs but cannot independently make a pointer alive. Repair verifies bounded raw,
    chunk, tree, commit objects and normalized reference integrity; identical working bytes may heal a
    raw object and force a `commit_type=repaired` commit. The repaired commit remains unprotected /
    shallow-eligible per 05 §2.1; the recovered raw object itself stays GC-ineligible.
70. Restore syntax is `restore <evidence|path|commit> --to <dir>`; raw-hash shorthand is excluded.
    URI/JSON/stdin selects evidence, HEAD/full hash selects commit, and other operands resolve tag
    before logical direct-child path. Path selects the newest matching entry on HEAD's first-parent
    ancestry (merge side parents require evidence/commit) and fails on incomplete shallow ancestry.
    Every restore source rejects shallow/purged content, all source bytes
    come from verified CAS, and `.kcs` remains lock-free/read-only. Destination publication is private,
    no-clobber by default, force-confirmed, per-file atomic, and reparse/symlink safe.
71. Purge-by-path means every raw ever bound to that logical path; incomplete shallow history fails.
    Raw-hash purge remains available. KCS never deletes user originals and refuses purge while target
    bytes remain in the working tree. Default tombstones gate all read/ingest paths; erase mode leaves
    no resurrection barrier and reports that limitation.
72. Purge is a resumable monotonic transaction under the store lock. An owner-only journal is written
    before a tombstone/in-progress visibility barrier; after it, all reads are dead even if physical
    cleanup is incomplete. Post-barrier failure returns `KCS-E-PURGE-INCOMPLETE-001` exit 3 and rerun
    resumes. Identical default repeat is idempotent; converting an existing tombstone to erase is
    deferred/rejected. Shared derived objects survive only while referenced by non-target raws; images
    are purgeable content. Logs are serialized and scrubbed before a sanitized reason/actor/count event.
73. Bbox annotation is default-on at `markdownize.bbox_annotation.enabled`. Enabled identity uses
    `kcs-markdown+bbox-annotation-v1` plus fixed prompt id/hash; disabled identity stays the existing
    profile. Bounded `short_description`/`transcribed_text` metadata is bound to image order/bbox and
    projected beside the image URI for chunk search without changing required Evidence fields.
74. Online Markdownize promotion occurs only for current, fully accepted Done outputs under the store
    lock. One deterministic batch atomically materializes the resolved immutable profile in tool-lock,
    creates an auto commit with matching normalize refs, and swaps rebuilt SQLite. Stale/partial/failed
    output never promotes; repeated Done processing is idempotent and does not recharge.
75. Chunk CAS uses one exact semantic JSON payload: `spec_version:1`, the eight identity fields
    (`raw_hash`, `tool_profile_hash`, `gen`, `unit_key`, `heading_path`, optional `section_id`, optional
    `char_start`, optional `char_end`), `text_hash`, and exact `text`. It omits its own `chunk_hash`, path,
    first-seen/created timestamps, and `chunking_config_hash`; the latter remains generation metadata in
    the append-only index/ledger and may map multiple config hashes to one chunk identity. Fsck recomputes
    the identity hash against the fan-out key and validates `text_hash` against both text and normalized
    span; it does not content-hash the JSON bytes.
76. Fsck treats validated tombstones and internal non-content erase receipts as healthy dead terminals.
    `--erase-tombstone` leaves no public tombstone and verify stays `not_found`, but atomically retains
    `.kcs/purge/erase-receipts/ab/cd/<raw64>` with exact `{schema_version,raw_hash,purged_in_commit,
    erased_at}` for fsck only. It never blocks re-ingest; verified raw wins and retires a stale receipt.
    A valid receipt binds to a verified ref-reachable purged commit and its exact non-future UTC
    `created_at`; malformed, forged, future, or unreachable bindings are corruption.
    Active journal is incomplete exit 3, receipt-covered bytes are never auto-healed, and unmarked
    missing references remain store corruption. Reports list bounded affected commit hashes and state
    that external self-contained pointers may be affected, never fabricate a pointer registry.
77. Purge log scrub is serialized beyond the scope lock. Device events/errors/metrics appenders and
    scrubbers share `$XDG_DATA_HOME/kcs/logs/scrub.lock`; scope access appenders/scrubbers share
    `.kcs/logs/access.scrub.lock`. Lock order is scope store → reservation ledger → device observability
    → scope access. A final scrub runs before the purge journal/barrier is removed.
78. Bbox annotation follows the Mistral wire format: one `bbox_annotation_format`, instructions inside
    one exact strict JSON Schema whose JCS hash is `sha256:9404f8ff...9ca8`, and one
    `pages[].images[].image_annotation` JSON string per returned image. Bounds are 256 images/page,
    4,096/response, 4 KiB description, 64 KiB transcription, 16 MiB aggregate, and strict
    non-negative/positive-area coordinates ≤1e9. NFC/control-normalized provider text HTML-encodes
    `&<>` and backslash-escapes every other ASCII punctuation before trusted blockquote prefixes; the
    same safe strings are retained in metadata and cannot form provider-created CommonMark links/images/
    HTML. Task identity pins annotation policy/profile, and zero-text prepared inputs still reach OCR;
    old non-bbox Done work cannot suppress it.
79. Fsck walks every commit parent with a visited set and is globally bounded at 1,000,000 objects,
    1 TiB streamed bytes, 1,024 findings, and 4,096 affected commit hashes. Prepared/image/embedding
    content rehash is outside the 10 §7.5 minimum, but referenced prepared/image identities are checked
    through normalized validation. Chunk/tree/commit damage is report-only; automatic recovery is raw-only.
80. `chunking_config_hash` is a many-to-many generation association, not a column in immutable chunk
    CAS identity. SQLite uses append-only `chunk_config_generations(association_rowid,chunk_id,
    chunking_config_hash,created_at)` and the durable chunk ledger may hold one association record per
    `(chunk_id,config)`. Search joins this relation; signed cursors freeze maximum association rowid,
    chunk rowid, each scope's effective config, and the page-1 `--since` cutoff. Query identity binds a
    sorted `{scope_id,chunking_config_hash}` mapping, so later associations, per-scope config changes,
    and moving time cannot silently change page 2.
81. History traversal has explicit aggregate caps in addition to per-object limits. All-parent and
    first-parent walks each have independent maxima of 100,000 commits, 10,000,000 tree entries, and
    4 GiB verified commit+tree bytes. Search fails a scope without partial aliases; purge/restore fail
    before mutation/publication with `KCS-E-COMMIT-HISTORY-LIMIT-001`.
82. Include-deleted is snapshot-derived, not mutable-manifest-derived: for each path absent at page-1
    snapshot, use the newest exact binding on snapshot HEAD's first-parent ancestry. Its pointer commit
    is that binding commit, so `path_at_commit` exists and cursor replay ignores later manifest changes.
    A live binding wins over a same-chunk deleted alias; with no live binding all distinct final-deleted
    paths expand after ranking, and live twins choose the bytewise-smallest path.
83. Search performs per-scope rank/RRF, rank-based cross-scope merge, then global MMR/dedup on unique
    semantic chunks with immutable tie key `(scope_id,chunk_hash)`. It expands retained historical/
    deleted aliases afterward, copies the parent score/rank, orders each group by
    `(scope_id,chunk_hash,path_at_commit,evidence_pointer.commit)`, and paginates.
    Mutable `scope_path` never orders results; aliases neither compete in MMR nor re-count against
    `max_per_raw_hash`; cursor consumed counts final expanded hits per scope, so old/new aliases survive
    and pagination is deterministic even inside one alias group.
84. Step 4 cursor schema is version 2 because selector, per-scope config, and association maxima are
    security-required bindings. Legacy v1 and unknown versions are rejected as cursor misuse; cursors
    are opaque short-lived paging state, not durable artifacts.
85. Multi-scope cursors contain only successfully participating active scope sub-cursors/configs plus
    bounded signed page-1 exclusions. Initial exclusions never enter. Loss/corruption/shallowing of any
    active replay scope hard-fails cause-specifically without a partial page/next cursor because
    shrinking the global MMR input would invalidate consumed offsets; fresh search is required. Config
    drift is cursor misuse. Ordering uses immutable scope_id, so moving a scope changes display hints only.
86. Historical eligibility never fills an omitted tree-entry `normalize` from later instances or cached
    projections. CAS tree omission means zero chunks at that commit for `--at`, all-history, and
    include-deleted; this closes future-normalization leakage into old snapshots.
87. Restore remains read-only with respect to `.kcs` truth and does not acquire `.kcs/.lock`, but purge
    source authorization is linearized by `.kcs/purge-publication.lock`. Purge acquires scope store →
    purge-publication before publishing its visibility barrier and holds both through physical cleanup
    and final journal removal. Restore acquires purge-publication only after interactive confirmation and
    destination-handle opening, then holds it across the final purge-state/raw recheck, private staging,
    and every atomic destination publication. This closes the check-to-publication race without a reverse
    lock order or changing docs/05 §6 read-command store-lock semantics.
88. Raw archive `.ingest-*` files are private transactions, never durable objects. With `.kcs/.lock`
    held, archive and purge entry remove every stale bounded/no-follow regular ingest temp before new
    staging or purge working-copy refusal; unsafe, over-limit, or linked entries fail closed as store
    corruption. This makes a crash before the raw-identity purge gate recover without retaining bytes.
89. Multi-scope search uses a scoped fixed worker pool with at most four workers and a two-second
    per-scope default deadline. Scope config overrides user config per key; queue wait is outside the
    deadline because the clock starts when a worker claims a scope. SQLite connections remain
    worker-local and install a progress handler, while filesystem/history phases check the same
    deadline cooperatively. Workers never publish output or logs: joined outcomes are restored to
    enumeration order before aggregation, and the global result tie key remains immutable
    `(scope_id,chunk_hash)`. A fresh timeout is exclusion reason `timeout` (partial exit 3 when another
    scope succeeds, all-failed exit 4 otherwise); timeout of any signed active cursor scope hard-fails
    replay without a partial page or replacement cursor. Scoped joins prohibit detached timeout work.
90. The first 100k-plus performance fixture is a balanced current-text baseline, independent from the
    frozen Recall corpus: 20 direct-child scopes map 14 personas to 20 use cases, with 200 deterministic
    Markdown files and 30 heading chunks per file (120,000 current chunks total). Exact source bytes,
    HEAD/current-config eligibility, FTS coverage, and the isolated 20-row registry are attested. Its
    M3-1 result uses high-selectivity deterministic reference tokens as a default-auto current-text
    baseline, not the formal broad-query/hybrid MVP latency gate; its single-HEAD M3-2/M3-3 timings are
    execution-path-only. Formal history latency needs a separately attested edit/rename/delete overlay.
    Broad-query ranking, hybrid vectors, Q_hard baseline comparison, dogfood, and D1 TTFV/cost remain
    separate gates rather than being simulated by inflating the balanced corpus.
91. The persona-PC environmental suite is separate from decision 90's balanced control. It defines
    twenty independent synthetic people, each with its own PC umbrella tree, isolated XDG device
    state/registry, exactly twenty active direct-file scopes (twelve role-primary plus eight common-PC
    secondary scopes), and exactly 120,000 attested contract-contributor chunks at both W0 and W5
    (the more-than-100,000 condition is only an exploratory floor), plus at least 180,000 eligible
    current-plus-historical chunks after W5; additional ambient
    directories and byte-volume noise belong only to the full-PC robustness view. Raw physical-file
    ratios, logical artifacts, searchable chunks, pending conversion,
    unsupported inputs, and history cardinality are separate ledgers. History is produced in place by a
    deterministic W0 baseline followed by W1-W5 edit/rename/move/duplicate/archive/delete/restore/purge
    event waves. Ordinary working-tree changes use each affected scope's normal `index` auto-snapshot as
    the history boundary, so the runner does not add a redundant explicit snapshot. Purge is the exception:
    its own forced `commit_type=purged` commit is the boundary and a following index is expected to be a
    no-op; restore materializes into a distinct destination scope whose following index is the boundary.
    Event scope effects therefore declare `index_auto`, `purged_commit`, `index_noop`, or `none` rather than
    assuming every operation is an index boundary. Reproducibility is tested by replaying the same immutable
    event manifests from W0 into three fresh roots with separately isolated registries, never by copying a
    `.kcs` store or placing checkpoint copies inside the indexed PC. Generation performs only fail-fast
    structural guards; delete and purge waves add planned replacements so current scale remains net-zero,
    and formal Recall, history, and latency evaluation starts after all replay roots exist.
    The suite uses deterministic synthetic data and offline/mock format artifacts only: no personal data,
    ambient credentials, or external API calls.
92. Persona-PC W0 publication is a planned-versus-observed boundary, not a performance attestation.
    The canonical plan expands twenty people into 400 direct-file leaf scopes and source-level 1–72
    contributor quotas; W0 writes deterministic raw sources plus separate physical, logical, and
    pre-index search-plan ledgers.  The tiny physical writer alone is enabled.  It atomically publishes
    a root-bound plan/suite/persona/capacity receipt, counts filesystem allocation overhead rather than
    only payload length, rejects repo output, symlink/reparse/special/hard-linked/unexpected entries,
    rerenders every source on verification, and makes a completed rerun a durability-reconfirmed strict
    no-op.  Two fresh roots must have byte-identical immutable artifacts but disjoint inodes.  Windows
    physical publication remains blocked until directory-handle durability is available; plans remain
    portable.  Pilot/full writes remain blocked until streaming/RSS and pilot-derived rich-file capacity
    gates are approved; the current full canonical expansion peaks near 455 MiB RSS.
93. W1-W5 persona history requires a joint source/quota/event allocation before any mutation.  The
    earlier independent defaults (one percent of raw files in the purge bucket and four percent of
    contributor chunks purged) are infeasible for 16 of 20 full personas and also fail several tiny/
    pilot personas.  The event manifest must jointly bind source ID, gate role, scope, current quota,
    history bucket, before/after state, and replacement source count/format, and must prove exact wave
    chunk deltas plus twenty-scope coverage.  Count-only `history_event_plan()` output is projection
    evidence, not authorization to run W1-W5.  Persona format weights remain stress-design hypotheses;
    role-specific variants, scope-size weights, and rich size/logical-complexity distributions are
    required before pilot/full approval.
94. Decision 93's infeasible exclusive raw-file history buckets are superseded for arithmetic by five
    mutually exclusive whole-source contributor cohorts: P=4%, X=10%, Y=6%, N=4%, and U=76% in full.
    W1 edits P+X+Y, W3 edits X+Y+N, W4 deletes X and replaces it one-for-one with a same-scope,
    same-variant, same-quota X', and W5 corrects N and replaces/purges P.  W5 first indexes distinct P'
    paths while old P remains, producing an explicit 124,800-current/64,800-history transient; it then
    removes and path-purges one old P source at a time.  Each P path has exactly W0 and W1 versions, so
    full purge deletes 9,600 contributor version-chunks (4,800 current plus 4,800 historical), while P'
    returns final C/H to 120,000/60,000.  A following index per purge scope must be noop.  Exact cohort
    sums are person-global, with full P/X positive coverage across all twenty scopes; per-scope exact
    percentages are prohibited because indivisible q/q+1 quotas make many cells infeasible.  Cross-scope
    move/archive/restore, near duplicate, derived format, and create initially use quota-zero raw-only
    sentinels, so they prove structure/lifecycle but not searchable move/restore Recall.  Same-scope rename
    and exact duplicate may use safe U contributors.  This mathematical model remains non-executable until
    a source-ID joint allocator, immutable event manifest, and independent validator land.
95. The P/X/Y/N source-ID allocator and its canonical-regeneration validator are now
    implemented for the existing W0 plans.  All twenty personas in tiny, pilot, and full have exact,
    disjoint whole-source assignments; full P/X/Y/N each covers all twenty scopes, and X'/P'
    replacements preserve source scope, variant, and chunk quota one-for-one.  Full one-replay planning
    yields 2,775 P purge paths, 6,931 X replacements, and 9,706 total contributor replacements; each P
    path binds exactly two raw versions, for 5,550 purge raw targets.  This makes the cohort assignment
    executable.  Canonical W0 source expansion is authenticated before allocation, candidates use a
    deterministic hash-spread order, and every full cohort covers all scopes while no one scope may carry
    more than 20% of a cohort plus one 72-chunk source.  It still does not authorize W1-W5 mutation:
    quota-zero structural sentinels, immutable event
    manifests, replay/preflight/resume, and actual KCS chunk attestation remain required.
96. Persona history structural allocation and the root-independent planned event manifest are now
    independently executable, but replay remains fail-closed.  Tiny/pilot use eleven structural
    events/person; full uses thirty, including one safe U same-scope W2 rename in every scope plus
    one raw-only cross-scope traveler.  Source ID, source version, and materialization ID are distinct:
    rename/move/archive preserve all three, edits advance only the version, exact alias and restore add
    materializations, and near/derived/create add sources.  Near PNG changes exactly one decoded RGB
    channel by one; PNG-derived scan PDF embeds the parent's exact decoded pixels without a text layer.
    Structural final live delta is four files/person, so full final active files are 195,080/replay and
    585,240 for three replays.  The immutable manifest keeps events, wave-scope boundaries, and schedule
    in separate canonical inventories; ordinary indexes coalesce to exactly one per affected wave/scope,
    restore's source command has no commit boundary while its existing active destination is indexed, and
    W5 is regular changes → ordinary indexes → one old-P unlink/path-purge plus forced commit at a time →
    one noop index per purge scope.  Complete rendered before/after hashes, parent-transform witnesses,
    managed-state/event hash chains, dependencies, and leaf-derived chunk/file arithmetic are regenerated
    for validation.  These are planned, not observed, facts.  `HISTORY_ASSIGNMENT_EXECUTABLE` stays false
    until W0 history-ready receipts, a root-wide lock, expected-state safe mutation, immutable progress
    journal, crash resume, and actual KCS attestation are implemented.
97. Persona history planning now has two additional non-authorizing boundaries.  First, exactly twenty
    individually validated persona event manifests are hash-bound into one root-independent suite
    schedule held under one future replay-root lock.  In W1--W4 every person's regular events precede
    every ordinary index in that wave; W5 is all regular events, all ordinary indexes, persona/source-
    ordered unlink/path-purge plus purged-commit pairs, then all post-purge noop indexes.  This prevents
    twenty unrelated per-person dependency chains from being resumed concurrently or in a different
    purge order.  Second, strict W0 exact-tree verification remains unchanged while a separate read-only
    prepare-envelope verifier allows only the canonical 400 `.kcs` directories, 20 isolated
    `.kcs-eval-device` directories, and hash-bound files below
    `.kcs-persona-history/{control,receipts}` after re-verifying all W0 bytes.  Opaque runtime interiors
    require typed directory-identity/content-root callback receipts; without them they are explicitly
    unattested, and even with them this verifier always leaves `history_ready_attested=false`.  Neither
    the suite schedule nor the envelope authorizes mutation.  W0 init/index receipts, the owner-marker
    root lock, handle-relative safe mutation, replay journal/resume, and actual KCS attestation remain
    required before `HISTORY_ASSIGNMENT_EXECUTABLE` can become true.
    The in-memory twenty-manifest composition is tested only with tiny; full additionally requires a
    bounded one-person-at-a-time input/validation path and an RSS gate.
98. The replay-root mutual-exclusion carrier is the already-published immutable owner marker,
    reinforced by an advisory lock on the opened root directory; acquiring a lease creates no new
    W0 entry and rewrites no byte.  The POSIX-only primitive opens the root, owner marker, and root
    binding with no-follow semantics, requires stable single-link control-file identities and exact
    canonical bytes, binds profile/replay/plan/root path/filesystem device, rejects same-process
    reentry and nonblocking cross-process contention, binds the lease to the acquiring PID, resets the
    inherited process mutex after `fork`, prevents a child from unlocking the parent's flock, retains
    all descriptors, and repeats namespace and semantic checks before unlock.  Root or control-file
    replacement is a release failure and the
    foreign replacement is never rewritten.  This is an advisory cooperative-writer boundary, not a
    defense against an actor replacing the entire path with a different inode, and it is unavailable
    on Windows.  The lease does not attest KCS internals or make history executable: prepare-runner
    integration, a complete 400-scope semantic receipt, handle-relative expected-state mutation,
    durable journal/resume, and the replay executor remain required, so
    `HISTORY_ASSIGNMENT_EXECUTABLE` stays false.
99. Persona fidelity is now a machine-readable planning hypothesis, not an observed distribution or
    renderer claim.  Each of the twenty synthetic owners has a distinct row for declared OS semantics,
    device class, locale/languages, work style, synthetic snapshot/export sources, sensitivity tiers,
    nesting, size-profile identity, and raw-only domain-binary variants.  A common six-dimension
    small/medium/large/tail size-complexity envelope covers text/code chunks, PDF pages, EML attachments,
    XLSX sheets, PPTX slides, and image/media/domain bytes.  All such rows remain synthetic-only,
    non-live, and `implemented_by_renderer=false`; they neither alter current bytes/extensions/OS
    behavior nor grant raw formats searchable chunks.
100. Full-scale cardinality and resource limits are now derived through one bounded canonical persona
    plan at a time, without constructing a full event manifest.  The frozen oracle yields 43,596 events,
    5,175 boundaries, and 48,771 schedule items/replay, or 130,788 / 15,525 / 146,313 for three replays.
    It caps a persona plan at 8 MiB, 16,000 sources, 20 scopes, 384 MiB worker RSS, 128 MiB composer RSS,
    512 MiB process-tree RSS, one concurrent worker, 512 rows/shard, and 32 MiB/shard.  Worker and suite
    receipts are caller-declared projections only and keep `formal_capacity_gate_satisfied=false` until
    published artifacts are read back and supervisor `wait4` evidence is independently bound.
101. Persona capacity and generic streaming storage are implemented as non-authorizing boundaries.
    Capacity derives exact cardinalities but remains blocked until canonical pilot measurement readback;
    a root-bound check additionally requires read-back filesystem identity, allocation unit, availability,
    caps, and reserves.  No capacity receipt authorizes a write or attests KCS.  Streaming JSONL storage
    enforces bounded canonical shards, no-replace publication, and exact readback, but portable rename
    cannot atomically require that the verified source directory inode remains the rename source.  Every
    result therefore reports `formal_publication_attested=false` with blocker
    `source_directory_inode_not_bound_by_rename` and cannot serve as a formal full-publication receipt.
102. The KCS runner boundary and partial semantic attestor are fail-closed scaffolding, not W0 prepare.
    Strict result validation, isolated environment construction, read-only binary identity, content-root
    walking, canonical persona/scope/quota binding, and typed runtime callback receipts are implemented.
    A validated scope path can still be swapped before `Popen(cwd=...)` resolves it, so
    `HANDLE_RELATIVE_EXECUTION_AVAILABLE`, `PERSONA_FILESYSTEM_MUTATION_AVAILABLE`, and
    `TRUSTED_BINARY_EXECUTION_AVAILABLE` all remain false; init/index/version subprocesses and persona
    mutation are unavailable.  The attestor does not itself prove SQLite/CAS, HEAD/commit, binary/config,
    root, or prepare-intent semantics, and returns `history_ready_attested=false` even for the exact
    20-person/400-scope/20-device projection.  Consequently `HISTORY_ASSIGNMENT_EXECUTABLE` remains false.
103. Persona suite-event streaming is implemented as bounded planning storage, not history execution.
    At most one complete persona event manifest is retained while canonical events, boundaries, and
    schedule-projection rows are published as bounded shards.  The suite composer holds twenty compact
    summaries, performs an O(20) merge, and emits the global schedule, external row locators, and an MMR
    over paired schedule/locator bindings without retaining twenty full manifest objects.  The tiny
    differential is exact: 1,076 events, 908 boundaries, 1,984 schedule items, schedule SHA-256
    `3f64675b1b8b83455b6eb18d9a2592b8e8b882621ad3f1b735cd233b6ef437c0`, and suite-manifest
    SHA-256 `d76ca8d55e92ff77eec98aaac69cab2bc3e35f3cd392c4ae681e5a7972afac3a` match the legacy
    builder.  This does not clear the generic publisher's
    `source_directory_inode_not_bound_by_rename` blocker: person and suite artifacts always report
    `formal_publication_attested=false`.  Full supervisor RSS, artifact readback, and `wait4` receipts
    remain unproven, the layer contains no W1-W5 mutation, and it grants no history-execution authority.
104. Persona W0 prepare-receipt composition is a canonical hash-inventory boundary, not command or
    store attestation.  The all-person generation-plan SHA is regenerated by streaming one independently
    bounded canonical persona projection at a time and must match the declared plan/root/history intent;
    coherent substitution by an arbitrary digest is rejected.  The root/person/device/scope projection is
    exactly 20×20 and binds the root binding plus declared binary, environment, init, and index receipt
    hashes in canonical order, but does not parse or type-check those artifact bodies.  Its only positive
    claim is `canonical_fixture_projection_complete`; every KCS semantic, actual-chunk, opaque-runtime,
    external-API-absence, history-ready, execution, and mutation claim is fixed false.  Root `/`, more than
    4 KiB/64 components/255 bytes per component, duplicate environment/init/index receipt hashes,
    and a person scope list other
    than exactly twenty are rejected before unbounded traversal.
105. A replay-root lease may lend a private non-inheritable duplicate of its already-held root descriptor;
    the consumer never reopens the diagnostic root path.  Persistent close, fresh same-inode reopen,
    foreign rebind, inheritable change, root namespace replacement, and lease expiry are rejected, and a caller-reused foreign fd slot
    is deliberately left open rather than clobbered during cleanup.  The semantic callback can traverse
    scope/device runtime directories from this lease-derived descriptor, closing the prior trusted-root
    check/open seam for cooperating readers.  This remains explicitly non-authoritative: an in-process
    checker can duplicate or transiently rebind a descriptor, and a same-UID writer can perform content
    ABA between equal before/after Merkle roots.  Quiesced immutable snapshots and checker process
    isolation are still required, so the handle transport, trusted binary execution, actual KCS semantics,
    history readiness, and history assignment all remain false.  Checker-local semantic evidence may assert
    success, but its typed receipt fixes `formal_transport_attested=false` and cannot enter the provenance-free
    legacy nine-field history-envelope callback protocol.
106. Complete W0 KCS semantics require separate physical-tree and normalized-index ledgers.  In the
    observed offline store, the HEAD tree and raw CAS contain every physical source, while SQLite
    `tree_entries`, chunk ledger/CAS, and current eligibility contain only normalized sources; raw-only
    DOCX remains in the tree with `normalize=null`, has no SQLite tree row or chunks, and has a pending
    online task.  Scope proof must therefore verify canonical HEAD/ref/single-parentless-auto-commit,
    tree/raw/normalized/chunk CAS, strict task/approval/unsupported JSONL, SQLite/current/FTS projections,
    and per-person registry exact-twenty semantics without equating tree files to SQLite rows.  Python's
    standard SQLite API cannot use a held directory fd as cross-platform authority for main/WAL/SHM and a
    read-only registry open may touch sidecars.  A native fd-bound read-only VFS or writer-excluded
    same-epoch immutable snapshot is required before SQLite/registry, actual chunks, FTS completeness, or
    history-ready claims can become true.  The 20-person/400-scope tiny W0 generation and two-scope offline
    probe are synthetic development evidence only, not a 400-scope attestation or full-scale result.
107. Persona-PC fidelity v2 is a side-by-side planning contract, never an in-place reinterpretation of
    `kcs-persona-pc-v1`.  V2 must use a bounded framed header and exact artifact-kind/schema plus fixture ID/
    schema dispatch, and must always write fresh roots.  Pilot must be solved first as an exact Hamilton-
    marginal source/quota/cohort plan; those source rows must be embedded unchanged into full, which adds
    sources to reach its own exact marginals.  Thus pilot must become a true source-ID/byte subset without
    post-hoc re-quota.
    The model is twenty independent synthetic people, not one person with twenty use-case folders.  One
    replay therefore has twenty persona-PC roots, each with twelve primary plus eight persona-specific
    secondary scopes and exactly 120,000 current contract chunks.  Three retained fresh-storage replays
    are still the same twenty logical people, but physically contain sixty roots, 1,200 scopes, and
    609,000 W0 source files (203,000 per replay).  Generation order is frozen plan, W0 folder/file build,
    W0 offline index/attestation, W1--W5 edits and lifecycle operations, fresh-root replay from W0 without
    copying a completed root or `.kcs`, then validation after all replays.  These counts are not a measured
    capacity-feasibility claim.
    Tiny remains a
    separate topology/routing smoke without the formal density distribution.  Variant dictionaries, not
    family labels or source rows, must bind extension, media type, gate role, offline disposition, validator,
    renderer, and feasibility rule.  Full/pilot quota allocation must jointly solve family, variant, scope,
    density bucket, exact 1--70 source quota, and P/X/Y/N/U=4/10/6/4/76 whole-source history cohorts before
    a G0 hash can be frozen.  Text-layer PDF is planned as a local contract contributor; scan PDF alone is
    planned as raw-only/awaiting OCR.  The authoritative joint solver is bounded exact search with a versioned objective and
    lexicographic tie-break; local repair is never the authority.
    The fact/answer oracle must be frozen before rendering, while query templates/text and query seed remain in a
    separately hashed artifact unavailable to the corpus renderer.  G0 grants no renderer, filesystem,
    KCS execution, history mutation, actual-chunk, capacity, or write authority; all such flags stay false
    until their later observed gates.  Until all 400 paths, authored physical/chunk load vectors, their
    explicit rubric and review receipt, the joint solver, source recipes, oracle membership, and bounded canonical hashes exist,
    `g0_contract_frozen=false` is mandatory.
108. The persona-PC v2 exact topology is a separate `kcs.persona.pc-topology/v2` sidecar that binds the
    envelope SHA instead of embedding 400 rows into the envelope.  Its input is 400 literal, authored
    stress-design hypotheses: 20 personas, each 12 primary and eight persona-specific secondary paths.  Only the
    eight secondary functional slots are shared.  Paths and physical/contributor activity units are never
    derived from a hash, seed, persona ID, or runtime order.  The 1--100 activity scale is ordinal planning
    input within one persona and scope kind, not observed or empirically calibrated precision; within-band values are canonical authored
    interpolation.  `per-scope-floor-then-hamilton-residual-v1` gives each scope a 50 bp physical floor or
    25 bp contributor floor before Hamilton-apportioning only the residual, preserves exact persona
    primary/secondary subtotals, and rejects
    duplicate or permutation-clone vectors.  The sidecar proves portable globally unique paths, exact Dmax,
    profile file/chunk projections, and necessary per-scope source bounds only.  Cross-persona path uniqueness
    is an anti-template diversity invariant, while collision safety is enforced within each independent root.
    Its topology completion does
    not prove the later joint allocation, freeze G0, or authorize rendering, writing, or history mutation.
    The authored activity units require a separately bound rubric-review receipt; until then
    `activity_unit_review_receipt_bound=false` remains an explicit G0 blocker.
109. Persona-PC v2 rejects a whole-source history-cohort counterexample before solver construction.
    Pilot cohort chunks P/X/Y/N/U are 480/1,200/720/480/9,120.  With a 70-chunk source cap and
    P/X/Y/N coverage across all twenty scopes, their independent source lower bounds are
    20/20/20/20/131, or 211 total.  The former p17 pilot had only 203 contributors and was impossible;
    p08 had 211 with no headroom.  The final physical `benchmark_stress_mix_v2` correction changes
    p08 md/text-PDF/docx/pptx to 14/16/12/12, p11 to 5/19/11/8, p15
    md/text-PDF/scan-PDF/docx to 7/23/5/17, and p17
    md/text-PDF/scan-PDF/xlsx/domain-binary to 7/24/9/8/12 percent.  P02's domain split is
    PCAP/JSONL.GZ 30/70 and p17's is IFCZIP/CDE-ZIP 40/60.  Pilot/full contributors become
    267/2,672 for p08 and p17, and 268/2,680 for p11 and p15.  Suite family totals are
    md 19,660, txt/log 19,210, code 10,440, structured 15,310, CSV/TSV 18,680, HTML/EML 14,430,
    IPYNB 2,240, text PDF 29,680, scan PDF 11,200, DOCX 16,490, XLSX 15,270, PPTX 10,180,
    image 11,380, media 2,150, and domain 6,680.
    Gate-role totals for pilot/full/residual are respectively
    6,925/69,236/62,311 contract, 6,040/60,414/54,374 incidental, and
    7,335/73,350/66,015 raw-only.  The corresponding four density buckets are
    731/1,707/2,498/1,989; 7,300/17,042/24,995/19,899; and
    6,569/15,335/22,497/17,910.  Minimum global headroom is +27 pilot and +664 full;
    minimum pilot scope lower headroom is p13 +56, while p17 is +76.
    The bound `kcs.persona.pc-joint-problem/v2` artifact materializes pilot, full, and coordinatewise
    full-minus-pilot marginals and necessary feasibility checks.  Its canonical body is 744,137 bytes,
    SHA-256 `8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074`, bound to envelope
    `1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370` and topology
    `204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f`.
    It contains no source rows, route, quota/cohort assignment, canonical allocation solution, or
    certificate, so all G0/write/history authority remains false.  Physical ratios are stress inputs,
    not observed user statistics; persona realism remains separately blocked by
    `persona_fidelity_realism_profile_and_overlay_missing` until a search-participating
    duplicate/revision/conflict/attachment overlay and its ledgers are frozen.
110. Persona-PC v2 uses a one-way, non-authorizing solver sequence: exact solver-semantics policy
    sidecar; then the reviewed persona-realism overlay, pre-solve source-intent recipe, reviewed route
    matrix, and fact/oracle input closure; then an aggregate plus source-intent-refinement canonical
    solution and either an execution receipt with bounded canonical replay or an independently
    verifiable complete proof; only then the final source plan, writer, and history executor.  A
    solution may not precede the overlay or recipe.  Per persona/profile, physical cells are
    `A[v,s]` and contributor cells are `C[v,s,b,h,q]`.  With contributor source/chunk totals
    `N/T`, scope chunk target `t_s`, bucket-source marginal `D_b`, cohort-chunk marginal `H_h`,
    `n_s=sum C`, `d_b,s=sum C` by bucket/scope, `r_h,s=sum C` by cohort/scope,
    `k_h,s=sum q*C` by cohort/scope, `z_b,s,q=sum C` by bucket/scope/quota,
    number of integer quotas in bucket b `w_b`, and `W=240`, the five exact integer layers are
    `sum_s|T*n_s-N*t_s|`, `sum_b,s|N*d_b,s-D_b*n_s|`,
    `sum_h,s|T*r_h,s-H_h*n_s|`, `sum_h,s|T*k_h,s-H_h*t_s|`, and
    `sum_b,s,q(W/w_b)|w_b*z_b,s,q-d_b,s|`.  Cohort-source and quota-uniform layers are benchmark
    canonicality regularizers, not observed user statistics.  Every marginal and score constant is
    phase-specific; a full score may not reuse pilot constants.  Exact hard constraints bind variant
    and scope A marginals, contributor `A=sum C`, density-source and cohort-chunk marginals, scope
    `sum q*C`, and P/X/Y/N coverage of every scope.  For reviewed
    `R[persona,variant,scope] in 0..4`, phase marginal `M_phi,v`, and
    `V+={v | M_full,v>0}`,
    route loss is exactly
    `sum_v-in-V+ M_phi,v*max_s R - sum_v-in-V+,s A_phi[v,s]*R[v,s]` and counts physical `A` once.
    The strict tuple minimizes the pilot five layers, pilot route loss, dense
    `Flat(A_pilot),Flat(C_pilot)`, then the full-aggregate five layers and route loss, then
    `Flat(deltaA),Flat(deltaC)`; a pilot candidate must have an exact full extension.  Persona is an
    outer solve/serialization order, not a flat cell axis.  Each dense A tensor retains all
    566 bound persona-variant rows (11,320 cells), while route covers only the 541 rows whose full
    variant marginal is positive (10,820 scores); the omitted 25 rows are hard-zero.  Each C tensor
    has 116 contributor rows and 812,000 cells.  The pilot-plus-residual decision therefore has at
    least 22,640 A and 1,624,000 C coordinates before solver auxiliaries.  Joins use persona plus
    variant ID, never display or filtered position.  V1 route hints are unusable for v2 because only 749/10,820 scores are nonzero,
    md/txt_log are all zero, and secondary scopes are biased; the complete 0--4 matrix remains blocked
    on an independent review receipt.
    Aggregate tie-breaking is semantic dense lexicographic order, never hash-spread.  A
    domain-separated hash is reserved for post-solve source/materialization identity.  To avoid a
    cycle, the pre-solve recipe contains immutable `intent_key` values and overlay/fact membership but
    no final IDs; source-intent refinement assigns semantic cells and cell-local ordinals, final IDs
    derive from the input-closure namespace plus persona, immutable `pilot|full-residual` origin,
    `intent_key`, those coordinates, and the ordinal without hashing their enclosing payload/solution/
    plan.  Pilot ordinals remain reserved unchanged in full so residual additions cannot renumber or
    collide with pilot IDs, and the downstream final source plan binds the solution and IDs.
    Aggregate-cell, source-ID, materialization, and rendered-byte pilot subset claims remain four
    separate false claims until independently established.  Warm-start steps, objective values, and
    marginal hashes alone are an execution receipt, not a global-optimality certificate; proof requires
    bounded canonical exact replay or a complete lower-bound/dual proof.  None of these semantics grants
    G0, rendering, write, or history authority.
111. The first v2 solver-policy artifact is frozen only as the generic aggregate core, schema
    `kcs.persona.pc-joint-solver-policy/v2`: 83,004 canonical bytes, SHA-256
    `2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857`.  It binds the envelope,
    topology, and joint necessary problem one-way; defines the A/C axes, hard aggregate equations,
    strict 16-component objective, checked 127-bit arithmetic, and provisional deterministic counters;
    and contains no route matrix, realism/source-intent refinement, source recipe, solution, proof, or
    source rows.  The 512 KiB bound is an in-memory canonical cap, not framed-loader evidence.  Therefore
    `exact_objective_evaluable`, `exact_solver_executable`, `policy_definition_complete_for_bound_problem`,
    `solver_policy_bound`, all four pilot subset proofs, G0, write, and history authority remain false;
    resource limits remain empirically uncalibrated.
112. Persona-PC v2 realism is split into an exact profile/marginal artifact and later intent
    membership so that the hash graph remains one-way.  Schema
    `kcs.persona.pc-realism-profile/v2` binds twenty literal, independently rooted synthetic-owner
    hypotheses for OS/case/device metadata, locale/language weights, pinned timezone offsets,
    retention and mtime buckets, permission and placement weights, account counts, and exact
    duplicate/near/conflict/attachment marginal targets.  Its canonical body is 36,811 bytes,
    SHA-256 `a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05`.
    Full-suite targets are 5,080 exact duplicates, 13,230 near revisions, 1,560 conflict copies,
    5,690 standalone attachments, and 19,870 binary content-relation clusters; pilot is exactly one
    tenth.  Exact/near/conflict are mutually exclusive, binary, physical-member-disjoint relation
    clusters, while attachment is an orthogonal role with an explicit exact-duplicate overlap target.
    These are authored benchmark stress hypotheses, not observed user statistics.  Only profile
    vectors and marginal targets are complete.  Intent membership, placement integer allocation,
    logical-document scoring/search participation, the eight-axis ledger, independent review,
    source-intent refinement, G0, rendering, writing, and history authority all remain false.
113. Persona-PC v2 variant identity/marginal completion is a separate non-authorizing sidecar,
    schema `kcs.persona.pc-variant-catalog/v2`, canonical body 211,733 bytes, SHA-256
    `abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec`.
    It exactly projects all 71 variant identities and all 566 persona/family/variant tiny/pilot/full
    marginals, separates content MIME from current KCS path MIME, and assigns format-specific
    complexity units rather than collapsing EML, notebooks, tabular rows, HTML sections, and
    structured records.  Formal complexity lanes bind text PDF 1--72 pages, scan PDF 1--50 pages,
    EML 0--5 attachments, XLSX 1--20 sheets, PPTX 1--40 slides, and image/media/domain ordinary and
    persona-global tail byte ranges.  A separate W0-only byte-stress lane includes PDF, EML, XLSX,
    PPTX, image, media, and domain binary without changing formal marginals, chunks, or Recall.
    It reuses only format encoding/validator identity, is not a formal variant source row, and is always
    lane-local raw-only with requested/actual chunks zero.  OOXML and archive encodings are bounded
    containers limited to small/medium stress classes; large/tail require a non-container encoding.
    An ID-free text renderer/validator and source-profile catalog now exist only as candidate local
    byte/complexity checks.  Their source recipe profile is not bound, their vertical slice is incomplete,
    and no production cross-language MIME golden or all-variant target-byte/quota feasibility exists.
    Therefore every suite-level parameter-completion claim, source-level feasibility, G0, and execution/
    write/history authority remains false.  The shared upstream binder independently hashes canonical
    bodies, preserves the exact fixture identity tuple, pins the four upstream body sizes/digests,
    requires every authority map and the designated execution/proof denial fields false, and rejects
    unexpected downstream SHA paths; it is still not a bounded framed external loader.
114. The pre-solve source and evaluation inputs are sharded by one synthetic owner, never as one
    203,000-row suite body.  A source profile pre-binds family, variant, gate role, media, renderer,
    and validator; source-intent refinement only validates those values and assigns scope, density
    bucket, history cohort, quota, and cell-local ordinal.  Each immutable intent also carries an
    explicit `pilot|full-residual` origin.  Eligible scope keys may be transitively bound through a
    persona-local scope-set catalog instead of repeated on every row.  Pilot intent bytes are one
    dedicated shard reused unchanged by the full manifest; full only adds residual shards.  With
    maximum 4,096 rows and 4 MiB per shard, the current 203,000 intents require exactly 73 shards:
    twenty pilot and fifty-three residual.  Every intent row is capped at 768 canonical bytes and
    the complete framed persona source-intent package, including manifests and overlay shards, is
    capped at 16 MiB.  Fact, answer, and query information uses a separate one-way chain per persona:
    typed fact graph without intent/query/answer references, semantic answer membership keyed only
    by intent/logical-document keys, query-intent unavailable to the corpus renderer, and a compact
    bundle manifest.  That bundle is capped at 4 MiB/person with 1 MiB fact, 1.5 MiB semantic-oracle,
    1 MiB query-intent, and 128 KiB manifest subcaps.  Rendered query text, compiled final-ID relevance,
    and observed rank/score/latency are later artifacts.  This sharding decision proves neither
    aggregate/source/materialization/rendered-byte pilot subset nor feasibility, G0, solver,
    renderer, filesystem, write, or history authority.
115. The first complete route-affinity candidate is schema
    `kcs.persona.pc-route-affinity/v2`, 70,626 canonical bytes, SHA-256
    `e8a401193fc751ed3d7b2a47e3661202835579df8700392ce9fdfd30ad07c790`.
    It contains exactly the 541 full-active rows and 10,820 scope scores from the solver-policy
    axis, excludes the 25 declared hard-zero rows, and does not create rows for the 854
    persona/global-variant pairs outside the declared axis.  Every row has maximum score four in
    one through eight scopes; all 400 persona/scope positions have at least one active score of two
    or more; same-variant cross-person vector clones and secondary-only maxima are absent.  Score
    zero is a soft absence of preference, never a hard eligibility ban.  The candidate back-binds
    the exact envelope, topology, necessary joint problem, and generic solver policy, and validates
    the policy's 566-row declared axis before construction.  It has no independent human-review
    receipt, so route review, solver, source-plan, G0, write, and history authority remain false.
116. Typed fact input is a separate per-person upstream leaf, schema
    `kcs.persona.pc-fact-graph/v2`.  The twenty leaves contain exactly four authored synthetic
    project/case graphs each: 80 graphs, 320 entities, 640 typed facts, and 80 revision chains in the
    suite.  Bodies are 23,720--24,010 canonical bytes, 477,082 bytes total, and each is below the
    1 MiB fact-graph subcap.  Revision prior facts are current only at W0 and history-only from W1;
    their replacements are absent at W0 and current from W1, matching the W1 small-edit boundary.
    That is the only currently typed revision boundary.  The future history-intent contract must model
    W3 X/Y/N edits and the W5 N correction as surface/raw lifecycle edits whose events carry
    `changed_fact_ids=[]`.  Their resulting source versions must carry forward the exact prior visible set
    in `present_fact_ids`, so those
    versions may remain semantic expected answers for carried facts.  A semantic change requires a
    new wave-visible typed revision chain, non-empty changed membership, and binding before G0.
    Identifiers are suite-synthetic, email uses `.invalid`, IP uses RFC
    5737 space, and time is a fixed logical reference with non-negative offsets.  Each leaf binds
    the core four artifacts and exact realism profile one-way, but deliberately contains no intent,
    answer, distractor, query, source/materialization/chunk ID, path, rendered prose, rank, score,
    environment, host, network, or runtime-random input.  Fact inventory completion does not imply
    semantic answer membership, query specification, source intent, fact-oracle closure, G0,
    solver, renderer, write, or history authority.
    M3-3 additionally requires at least ten distinct searchable restore logical documents per person,
    at least 200 suite-wide with no cross-person document/intent reuse and one-to-one query mapping,
    each bound through intent key, logical-document key, restore materialization/event, and expected
    source/chunk oracle membership.  Quota-zero/raw-only structural sentinels, multiple paths for one
    logical document, and restored-but-unindexed files do not satisfy that requirement.
117. Persona-PC v2 capacity has two non-interchangeable boundaries.  The source-tree envelope contains
    only managed source files and the authored directories leading to 400 leaf scopes; it excludes every
    `.kcs` object/index/history store, device registry, plan/ledger/receipt, workspace, staging, and
    transient artifact.  The 512 MiB/person and 10 GiB/W0-replay, 25 GiB/W5-final-replay, and
    27 GiB/pre-purge-replay values remain uncalibrated source-tree renderer candidates only.  The former
    88 GiB sum is therefore not a root-bound hard cap or Go result.  Root-bound capacity includes all
    retained replay roots and the in-progress peak on the destination filesystem and has no approved
    fixed full byte or inode cap.  Under the campaign-time-revalidated
    `scope-local-regular-file-per-distinct-chunk-v1` storage assumption, a formal-success-conditioned
    pilot W0 already requires at least
    20,300 source-file, 1,097 authored-directory, and 240,000 current-chunk-CAS inodes: 261,397 total
    before raw/prepared/normalized/tree/commit CAS, chunk fanout directories, SQLite/FTS/WAL, registries,
    ledgers, staging, transient, or history.  Thus the old 250,000 pilot inode cap and the equivalent
    1,000,000-free/750,000-reserve condition are impossible and superseded.  Pilot readback must bind
    per-person `raw/cas/index/history/staging/transient` allocated bytes, additional inodes, basis units,
    plan hash, filesystem device, and allocation unit.  Full projection uses integer rational scaling
    with 5/4 headroom, retains all replay roots, takes the maximum of sequential per-person staging and
    coexisting all-person W5 transient peaks, and adds at least one destination allocation unit per
    projected inode.  If runtime revalidation rejects that storage assumption, these inode floors cannot
    support Go/No-Go and the capacity gate fails closed until the observed model is re-contracted.  A
    separate destination readback binds free bytes/inodes, caps, reserves, and suite
    manifest.  Until both actual readers and v2 bindings exist, caller-declared projections cannot clear
    `formal_capacity_gate_satisfied=false` or authorize a physical write.
118. The current non-authorizing persona-PC v2 planning core is pinned as: envelope 71,979 bytes / SHA-256
    `1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370`; topology
    134,195 / `204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f`;
    joint problem 744,137 / `8551472e4993f21ff71f886b3f80b9b02410c409476d0be91d773db335907074`;
    solver policy 83,004 / `2a6c169a5cd02b01e330abf0f3a828d0d947a2f66b18f19e97a682d2edd50857`;
    realism 36,811 / `a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05`;
    variant catalog 211,733 / `abbe522ff37a9a091f28b7a230928fd598054498eb80cab99f08d21889f26cec`;
    and route candidate 70,626 /
    `e8a401193fc751ed3d7b2a47e3661202835579df8700392ce9fdfd30ad07c790`.
    The candidate `kcs.persona.pc-overlay-contract/v2`, ID-free text renderer/validator, and source-profile
    catalog are deliberately outside this pinned planning core.  They bind no overlay instances or exact
    placement, have `source_recipe_profile_id=not-bound`, do not complete a source-profile vertical slice,
    and grant no renderer, filesystem, KCS, history, capacity, or write authority.  Overlay membership,
    formal profile/upstream binding, source-intent and source-level exact allocation, production MIME
    goldens, semantic oracle/query closure, and the G0 root remain explicit blockers.
    Scenario-specific blockers also remain: searchable cross-scope rename/move for M3-2; text/scan-PDF
    renderer, independent validator, and format anchor minima for M3-1; and a compiled mapping from v2
    logical-document expectations to the formal MVP distinct `(raw_hash, section)` relevance metric.
119. Persona-PC v2 pre-solve identity is split into four one-way layers.  A future
    `kcs.persona.pc-corpus-semantic-namespace/v2` contains only content-affecting semantic payloads and
    is the only namespace eligible to seed solver output and planned source identity.  Review/evidence
    receipts are added only by `kcs.persona.pc-corpus-input-closure-manifest/v2`; query intent and semantic
    oracle are added only by `kcs.persona.pc-evaluation-input-closure-manifest/v2`; and
    `kcs.persona.pc-suite-input-closure-descriptor/v2` binds the corpus and evaluation closures.  Therefore
    a query-only mutation changes evaluation and suite identity but not corpus identity, while substituting
    a review receipt for an unchanged body changes evidence/corpus/evaluation/suite identity but not the
    semantic namespace, solution, planned IDs, or rendered bytes.  A content-affecting route-body mutation
    changes the semantic namespace.  The current upstream candidate bodies mix semantic content with
    authority, completion, and blocker metadata, so a schema-specific allowlisted `semantic_payload`
    projection is required before any semantic namespace is eligible for production source IDs.  The
    current full-body dependency DAG is only a non-authorizing compatibility candidate and must not be
    issued as G0.  Planned source/materialization/event identities may be compiled only after a solution;
    observed materialization/chunk/raw-hash/section identities are bound only after render and index.
    The representative source/fact/history/query/oracle candidates do not complete the 203,000-source
    inventory, 53 residual shards, 62 outstanding variants, solver assignment, or compiled relevance.
    The current fact graph also cannot realize the 1,560 conflict clusters because it lacks unordered
    unequal W0-current facts for the same subject and predicate; revision facts may therefore be assigned
    only to P/X/Y candidates until the graph is extended.  Scan PDF remains raw-only/`awaiting_ocr` and is
    excluded from positive Recall; positive PDF coverage requires a deterministic text-layer renderer, or
    a separately versioned deterministic local-OCR variant and provenance contract.  Bounded canonical
    JSON and JSONL readers, a negative route-review receipt, and the new CI jobs enforce these denials but
    grant no G0, solver, renderer, filesystem, write, KCS, or history authority.
    Known-schema field completeness and cross-field validity remain the responsibility of each injected
    exact provider validator; the closure scanner is defense-in-depth for canonical fields and explicitly
    declared aliases, not an unbounded synonym interpreter.  Validators must return exact true, and the
    provider body must match its pinned bytes, SHA-256, fixture identity, schema, kind, and dependency graph.
