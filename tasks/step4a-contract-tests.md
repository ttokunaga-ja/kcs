# Step4a 契約テスト仕様書: Step 4 (history completion)

> 本書は実装より先に Step 4 の受け入れ契約を固定する。正本優先順位は
> `docs/01-10` → 既存契約テスト → `tasks/ws1c-decisions.md` → kickoff runbook。
> `docs/11-requirements.md` は deprecated なので根拠にしない。各ケースは合成データと
> `/tmp` のみを使い、実 API・実認証情報・個人データを使わない。
>
> 対象: time-travel search、単発 Evidence verify、`repair --verify-objects`、restore、
> purge 最小形、bbox annotation、online Markdownize promotion、M3-2/M3-3 eval。
> 対象外: `kio gc` 実行、tiered retention、Evidence verify batch、retarget、export/import、
> purge の DAG 書換え、filename 秘匿、定期 fsck。根拠: `09 §3.1`。

## 0. ID と完了規律

| ID | 対象 | 主根拠 |
| --- | --- | --- |
| `CT4-TIMETRAVEL-*` | `--at` / `--all-history` / `--include-deleted` / `--since` | `05 §1.5-1.8` |
| `CT4-VERIFY-*` | `kio evidence verify <pointer> [--strict]` | `08 §3-4.3` |
| `CT4-FSCK-*` | `kio repair --verify-objects` | `10 §7.5` |
| `CT4-RESTORE-*` | destination-only restore | `05 §4` / `06 §5` |
| `CT4-PURGE-*` | tombstone / erase / scrub / purged commit | `05 §3` / `10 §7` |
| `CT4-BBOX-*` | bbox annotation identity / metadata / searchable projection | `07 §5.2` |
| `CT4-PROMOTION-*` | online normalized result → HEAD / SQLite / tool-lock | bughunt8 design F6 |
| `CT4-EVAL-*` | frozen M3-2 / M3-3 evaluation | `09 §4, §4.3` |

- **P0**: MVP completion gate. One failure blocks Step 4 completion.
- **P1**: compatibility, concurrency, or recovery edge. Must be green before PR readiness unless a
  concrete platform-only CI job is the designated executor.
- Every new read is bounded and no-follow/identity checked. Every store mutation holds `.kio/.lock`
  and uses atomic publication or a durable resumable journal. Canonical/legacy conflicts fail closed.
- `eval/golden-queries.jsonl`, `eval/corpus_spec.py`, and history fixtures are frozen.

## A. Frozen deterministic vectors

### A.1 Time-travel query hashes

The following JCS inputs use effective text mode, per-scope current chunking config `sha256:` + 64
`c` digits, default RRF/diversify, and sorted scopes/config mappings. They prove that selector or any
scope's config change invalidates a cursor (`05 §1.8`).

```text
all-history canonical:
{"chunking_configs":[{"chunking_config_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","scope_id":"scope_a"},{"chunking_config_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","scope_id":"scope_b"}],"diversify":{"enabled":true,"max_per_raw_hash":3,"mmr_depth":100,"mmr_lambda":0.7,"strategy":"mmr"},"mode":"text","query":"認証仕様","rrf":{"candidate_depth":200,"k":60,"w_text":1,"w_vector":1},"scope_mode":"all","scopes":["scope_a","scope_b"],"time_travel":{"all_history":true}}
query_hash = sha256:8b3f6fedd0376e1dd0fb02efb0b9ea1f34f1088465a2d9ad4f83e1307b7053f1

--at canonical (`a` repeated 64):
{"chunking_configs":[{"chunking_config_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","scope_id":"scope_a"}],"diversify":{"enabled":true,"max_per_raw_hash":3,"mmr_depth":100,"mmr_lambda":0.7,"strategy":"mmr"},"mode":"text","query":"認証仕様","rrf":{"candidate_depth":200,"k":60,"w_text":1,"w_vector":1},"scope_mode":"scope","scopes":["scope_a"],"time_travel":{"at":"sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}}
query_hash = sha256:8895f616f97776f376cd26d3210f5fa2e00b1f57dc748b115b8e0e0d3670d962

--since 7d canonicalizes to all-history + 604800s:
{"chunking_configs":[{"chunking_config_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","scope_id":"scope_a"},{"chunking_config_hash":"sha256:cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc","scope_id":"scope_b"}],"diversify":{"enabled":true,"max_per_raw_hash":3,"mmr_depth":100,"mmr_lambda":0.7,"strategy":"mmr"},"mode":"text","query":"認証仕様","rrf":{"candidate_depth":200,"k":60,"w_text":1,"w_vector":1},"scope_mode":"all","scopes":["scope_a","scope_b"],"time_travel":{"all_history":true,"since":"604800s"}}
query_hash = sha256:df768d2bc941daab1d43321b3739052905ca148b1bf884b7dc9cd6b5a88144e4
```

The opaque signed cursor additionally stores the page-1 UTC cutoff for `--since`; the moving cutoff
is not recomputed on page 2. `max_rowid` alone freezes neither this lower bound nor later current-config
associations; each per-scope cursor also freezes `max_association_rowid` and that scope's effective
`chunking_config_hash`. The token stores canonical `time_travel` so selector-less replay inherits mode.

### A.2 Bbox annotation profile identity

Enabled annotation transmits the following exact `bbox_annotation_format`. The prompt-template input
is its single-line JCS serialization, so the profile identity covers every transmitted schema
description, strictness rule, field, and required-list order:

```text
{"json_schema":{"name":"kio_bbox_annotation_v1","schema":{"additionalProperties":false,"properties":{"short_description":{"description":"Describe the figure briefly in plain text. Do not use Markdown or HTML.","type":"string"},"transcribed_text":{"description":"Transcribe all visible text verbatim in plain text. Do not use Markdown or HTML.","type":"string"}},"required":["short_description","transcribed_text"],"type":"object"},"strict":true},"type":"json_schema"}
prompt_template_hash = sha256:9404f8ffe2983113f082d255a61817ad0798e74aeb82cb5063a391fbcbea9ca8
```

For frozen model `mistral-ocr-2505`, the canonical profile and hash are:

```text
{"adapter_kind":"markdownize","adapter_role":"multimodal","model_or_tool_family":"mistral-ocr","model_version_pin":"mistral-ocr-2505","output_schema":"kio-markdown+bbox-annotation-v1","prompt_template_hash":"sha256:9404f8ffe2983113f082d255a61817ad0798e74aeb82cb5063a391fbcbea9ca8","prompt_template_id":"kio-mistral-bbox-annotation-v1","runtime_kind":"cloud","spec_version":1}
tool_profile_hash = sha256:830c45cada7e9ea8c6f6816579fa0493645208626201181f3763b4bc6bddda3e
```

Disabling annotation preserves the existing `kio-markdown-v1` profile identity. Enabled/disabled
outputs can never share a normalized instance.

### A.3 Tombstone schema

Keys are exact and values are canonical logical hashes; the physical leaf is digest-only:

```json
{
  "raw_hash": "sha256:<64 lowercase hex>",
  "purged_at": "2026-07-13T00:00:00Z",
  "purged_reason": "legal",
  "purged_in_commit": "sha256:<64 lowercase hex>"
}
```

The record is bounded, identity checked, atomically published, and not a CAS object.

### A.4 Internal erase-receipt schema

`--erase-tombstone` publishes no public tombstone. It atomically retains exactly this fsck-only,
non-content record at `.kio/purge/erase-receipts/ab/cd/<raw64>`:

```json
{
  "schema_version": 1,
  "raw_hash": "sha256:<64 lowercase hex>",
  "purged_in_commit": "sha256:<64 lowercase hex>",
  "erased_at": "2026-07-13T00:00:00Z"
}
```

The schema is strict and bounded, and the digest leaf and `raw_hash` agree. `purged_in_commit` must
resolve through bounded verified CAS to a ref-reachable `commit_type=purged` commit; `erased_at` must
be canonical UTC, equal that commit's `created_at`, and not be later than fsck's fixed invocation time.
It contains no path, reason, actor, content, query, or prompt. Only fsck reads it; it is not a tombstone
or resurrection barrier. A verified raw object wins over a stale receipt, and successful later
publication of that raw retires the receipt under the store lock.

## B. Time-travel search

### Selector contract

- One effective selector is allowed. `--at` conflicts with all history selectors.
- `--include-deleted` conflicts with `--all-history` and `--since`.
- `--since <duration>` implies `--all-history`; redundant explicit `--all-history` is accepted and
  canonicalizes to the same query hash.
- Duration grammar is positive integer plus `s|m|h|d|w`, overflow checked; `0d`, bare integers,
  dates, decimals, and unknown units are usage errors (exit 2).
- `--at` resolves the operand independently in every selected scope. Missing/tag-unknown scopes are
  normal multi-scope exclusions (partial exit 3); if all fail, the existing all-failed exit 4 applies.
- `reindex --at` performs historical enrichment only: it does not bump normalized `gen`, write HEAD,
  or alter refs. `--force --at` is rejected. Existing `reindex --force` remains HEAD gen+1.
- A cursor stores the canonical effective selector. `search QUERY --cursor TOKEN` inherits it; if any
  selector flag is repeated, the repeated canonical selector must match exactly or replay is rejected.

### Candidate and pointer contract

```text
default / --at: chunks JOIN tree_entries(selected commit) on (raw, profile, gen)
--all-history:  chunks with a binding in any commit reachable from page-1 snapshot HEAD via all parents,
                with current chunking_config_hash
--since:        all-history plus created_at >= frozen page-1 cutoff
--include-deleted:
  page-1 snapshot live set UNION, for each path absent at that snapshot, its newest exact binding on
  snapshot HEAD's first-parent ancestry
```

Only rows with non-null `first_seen_commit`, `rowid <= max_rowid`, and a current-config association
whose `association_rowid <= max_association_rowid` are eligible. Both maxima are frozen on page 1.
FTS and vector post-KNN filtering use the same eligible relation.

For historical results, all-history expands each chunk to one result per distinct historical path
binding across the snapshot HEAD's full reachable parent DAG. A binding's introduction commits are
those where it is present and absent from every available parent. Remove any introduction that is a
descendant of another introduction; use the sole ancestor-most candidate, or the lexicographically
smallest full commit hash when multiple incomparable candidates remain. Duplicate appearances of the
same `(chunk,path)` are collapsed. A side-parent-only binding remains eligible even when the merge
result drops it. An unchanged rename therefore yields old-path and new-path hits for the same
content-addressed chunk, preserving the frozen M3-2 criterion.

Each alias optionally carries `current_paths`: every distinct page-1 snapshot HEAD path with the same
raw hash, UTF-8-bytewise sorted. It is omitted when empty. `current_path` is emitted only as a compatibility
alias when that array has exactly one element and is omitted for identical-byte twins; raw identity
never implies rename lineage.

The execution order is frozen: per-scope text/vector rank → per-scope RRF → rank-based cross-scope
merge → global MMR/`max_per_raw_hash` on unique semantic chunks, using immutable pre-alias tie key
`(scope_id,chunk_hash)`; then expand retained historical/deleted binding aliases, copy the parent
score/rank, order each group by
`(scope_id,chunk_hash,path_at_commit,evidence_pointer.commit)`, and paginate. `scope_path` is a mutable
display hint and never orders results. Aliases do not compete in MMR and do not count again against
`max_per_raw_hash`, so every distinct path alias of a retained chunk survives deterministically.
Cursor `consumed` is the number of final post-expansion hits returned per scope, not semantic chunks;
replay recomputes the grouped stream and skips that many final hits per scope.

Aggregate history-walk limits are exact: an all-parent walk permits at most 100,000 unique commits,
10,000,000 total tree entries, and 4 GiB of verified commit+tree bytes; a first-parent walk has its own
independent counters with the same three maxima. Exceeding any cap fails before consuming the next
item with `KIO-E-COMMIT-HISTORY-LIMIT-001`. Search returns no partial aliases for that scope and uses
normal partial/all-failed scope semantics. Purge-by-path uses the all-parent limits; restore-by-path
uses first-parent limits and both fail before mutation/publication.

### Cases

**CT4-TIMETRAVEL-001 — P0 — parser/exclusivity/duration.** Given each valid selector and every
invalid combination/value; when search is parsed; then valid inputs execute and invalid inputs return
`KIO-E-CONFIG-USAGE-001` exit 2 before registry/DB mutation. (`05 §1.6`, `06 §3`)

**CT4-TIMETRAVEL-002 — P0 — exact `--at`.** Given C1(raw A), C2(raw B), and tag `old=C1`;
when searching by C1 hash/tag and HEAD; then only the selected commit's identity triple is eligible,
non-HEAD tree rows are lazily projected, and `snapshot_at`/pointer commit equal C1. A C1 entry with
`normalize` omitted yields no chunk even if later normalization/cache rows exist. (`03 §8`, `04 §4.5`, `05 §1.6`)

**CT4-TIMETRAVEL-003 — P0 — historical edit and rename.** Given an old value edited away and a
rename with unchanged bytes; when `--all-history`; then both old edited raw and current content can be
found, an unchanged rename produces distinct old/new path alias hits (the old hit also names
the one-element `current_paths` plus compatibility `current_path`), and no HEAD-only shortcut can
satisfy the fixture. If HEAD also contains `copy.md` with the same raw as `new.md`, every alias has
`current_paths=["copy.md","new.md"]`, no singular `current_path`, and stable pagination. (`05 §1.6-1.7`, `09 §4 M3-2`)

**CT4-TIMETRAVEL-004 — P0 — deleted final version only.** Given a path with A→B→deleted and another
live file; when `--include-deleted`; then live snapshot plus B are eligible and A is not, B's pointer
commit tree contains its `path_at_commit`, and mutation/recreation of `manifest.json` after page 1
cannot change page 2. If the same chunk remains live under another path, live wins and its deleted alias
is omitted; if it has no live binding, every distinct final-deleted path expands in bytewise group
order. Live twins use the bytewise-smallest `path_at_commit`. (`05 §1.6`)

**CT4-TIMETRAVEL-005 — P0 — since boundary.** Given chunk timestamps exactly before/equal/after the
cutoff under fixed time; when `--since 7d`; then equality is included, before is excluded, and page 2
uses the signed page-1 cutoff. (`05 §1.5-1.6`)

**CT4-TIMETRAVEL-006 — P0 — cursor binding.** Given otherwise equal searches differing in selector,
duration, or `--at`; when a cursor is replayed; then A.1 hashes differ and replay returns
`KIO-E-SEARCH-CURSOR-001`; same selector preserves snapshot, `max_rowid`,
`max_association_rowid`, cutoff, and order. Given current config C2, page 1 freezes association maximum
Amax while X has only C1; appending `(X,C2)` after page 1 cannot introduce X on page 2, while a fresh
search may include it. Switching the effective config from C2 to an older C1 whose associations are
already below Amax in any selected scope changes A.1's sorted per-scope config mapping and rejects cursor
replay instead of changing candidates. Selector-less replay inherits token mode/duration; a repeated
mismatched selector fails. Tampering either maximum or cutoff fails cursor verification. (`05 §1.5, §1.8`)
Legacy cursor `v=1`, unknown versions, or a missing required v2 binding are rejected with the same
cursor error; current tokens emit `v=2`. A page boundary inside one chunk's multi-alias group resumes
at the next alias exactly once because `consumed` counts expanded hits.

**CT4-TIMETRAVEL-007 — P0 — shallow rules.** Explicit `--at` to a shallow commit and any cursor whose
frozen snapshot becomes shallow return `KIO-E-COMMIT-SHALLOW-001`. All-history/since must not treat
cached `tree_entries` as truth: if a candidate's historical-path tree is shallow, that scope fails
loudly as shallow instead of serving or silently omitting the hit. Include-deleted likewise fails if
its bounded first-parent ancestry is incomplete. (`03 §2`, `04 §4.5`, `05 §2.2`)

**CT4-TIMETRAVEL-008 — P0 — current chunk config.** Given a chunking-config change; when the next index
and time-travel searches run; then every retained normalized history has current-config chunks and old
config rows are excluded. (`04 §4.6`)

**CT4-TIMETRAVEL-009 — P0 — text/vector parity and purge barrier.** The same eligible relation gates
text, vector, and hybrid. Tombstoned/in-progress/purged raw hashes never appear in any mode. (`05 §1.1, §1.6, §3`)

**CT4-TIMETRAVEL-010 — P1 — multi-scope partial.** The same `--at` operand is resolved per scope;
healthy scopes return results while absent/corrupt scopes are disclosed under existing partial/all-failed rules. Page-1
cursor active scopes/config mappings include successes only; signed exclusions never join later. If an active scope becomes
unreachable/corrupt/shallow on replay, replay hard-fails cause-specifically
(cursor-unavailable/store-corrupt/shallow), with no partial page/next cursor, and instructs a fresh
search because removing it would reorder global MMR. New/recovered registry scopes cannot enter.
A scope move with the same `scope_id` changes only display hints and cannot reorder/duplicate/skip results. (`05 §1.8`)

**CT4-TIMETRAVEL-011 — P1 — historical reindex.** `reindex --at C1` fills missing current-config
chunks/embeddings for C1 within normal consent/budget rules without changing HEAD, gen, existing
pointers, or non-selected history. (`05 §1.6`, `07 §9`)

**CT4-TIMETRAVEL-012 — P0 — full parent DAG.** Given C0; first-parent B1 without X; side-parent A1
introducing `(X,old.md)`; and merge M with parents `[B1,A1]` that drops X; page-1 HEAD=M
`--all-history` still returns X backed by A1. Two incomparable introduction commits choose the
bytewise-smallest full commit hash; cursor replay retains M and the same choice. Any shallow tree
needed to determine the binding fails that scope loudly. At each exact aggregate boundary the walk
succeeds; one commit/entry/byte beyond it fails the scope with the history-limit code and zero partial
aliases. (`05 §1.6-1.7`)

## C. Evidence liveness verify

Stable completed-inspection payloads are:

```json
{"status":"alive","details":{"scope_id":"...","scope_path":"...","commit":"sha256:...","raw_hash":"sha256:...","tool_profile_hash":"sha256:...","chunk_hash":"sha256:...","commit_shallow":false}}
{"status":"tombstoned","error_code":"KIO-E-PURGE-TOMBSTONED-001","details":{"purged_at":"...","purged_reason":"legal","purged_in_commit":"sha256:...","raw_hash":"sha256:...","scope_path":"..."}}
{"status":"not_found","error_code":"KIO-E-PURGE-NOT-FOUND-001","details":{"raw_hash":"sha256:...","scope_path":"..."}}
```

Non-strict returns exit 0 for all three. Strict returns 0 only for alive and preserves the dead-state
payload on stdout with exit 4. Scope unreachable/ambiguous is an error, not a fourth status.

**CT4-VERIFY-001 — P0 — accepted forms.** Exactly one URI, inline JSON, or `-` stdin pointer is
accepted. Short hashes, object URIs, `--batch`, extras, malformed/future schema, and >64 KiB stdin
are usage errors. (`08 §2.3, §4.3`, `09 §3.1`)

**CT4-VERIFY-002 — P0 — alive/strict.** A fully identity-bound raw+chunk returns the alive payload
and exit 0 in both modes, without returning body/snippet/path-at-commit. (`08 §3-4.3`)

**CT4-VERIFY-003 — P0 — tombstone/erased.** A validated tombstone returns tombstoned; missing raw with
no tombstone returns not_found; strict exit is 4 and non-strict exit is 0. (`08 §4.1-4.3`)

**CT4-VERIFY-004 — P0 — identity order.** Scope ID is truth; hint→registry fallback is allowed.
Forged/missing commit or raw/tool/gen/chunk mismatch is pointer-invalid exit 4. Missing target chunk
requiring retarget is exit 8. (`08 §3`)

**CT4-VERIFY-005 — P0 — genuine shallow.** A present commit with missing tree can verify directly
bound raw/chunk and reports `commit_shallow=true`; a missing commit is invalid. (`08 §3.1-3.2`)

**CT4-VERIFY-006 — P0 — read-only/bounded.** Verify takes no store lock, writes no cache/DB/store,
opens no OS viewer, calls no adapter/network, bounds tombstone/chunk/object reads, rejects nonregular
or conflicting dual representations, and emits no content. (`05 §6`, R23 invariants)

**CT4-VERIFY-007 — P1 — concurrent barrier.** Concurrent purge/index yields a coherent alive or
tombstoned/not_found terminal result, never transient content leakage or silent empty success. (`05 §3`, `08 §4`)

## D. Object verification / fsck

`repair --verify-objects` is an explicit store-writing repair command and holds `.kio/.lock` end to
end. It verifies documented raw/chunk/tree/commit CAS content paths plus normalized reference
integrity; SQLite is outside fsck and remains rebuildable.

Historical references intentionally killed by a validated default tombstone or A.4 erase receipt are
healthy dead terminals, not corruption. An active purge journal returns purge-incomplete exit 3.
Fsck never auto-recovers receipt-covered bytes. A missing reference without either marker is ordinary
store corruption; malformed/conflicting receipts are corruption. A verified raw object wins over a
stale receipt, which the locked repair retires.

Traversal follows every commit parent with a visited set (restore-by-path alone is first-parent).
Global bounds are 1,000,000 objects, 1 TiB streamed bytes, 1,024 findings, and 4,096 affected commit
hashes; exceeding an inventory bound is a loud incomplete/corrupt report, never silent truncation.
Prepared/image/embedding CAS are outside the content-rehash minimum in `10 §7.5`, but normalized
reference validation checks every prepared/image hash it actually references. Missing/corrupt
chunk/tree/commit objects are report-only; only raw has a specified automatic recovery path.

Stable JSON is `{status, checked:{raw,chunks,trees,commits,normalized_instances}, repaired_raw_count,
repaired_commit_hash, dead_by_tombstone_count,dead_by_erase_receipt_count,
remaining_findings:[{kind,object_hash,reason,
affected_commits}], findings_truncated, external_pointers_may_be_affected}`. It never includes object
bytes, normalized text, working paths, or pointer bodies.

**CT4-FSCK-001 — P0 — healthy graph.** Rehash every bounded regular raw/chunk/tree/commit canonical
and verified legacy object; validate object type, semantic schema, fanout path, and all reachable
references. Healthy count exits 0 and changes nothing. (`03 §8.1`, `10 §7.5`)

**CT4-FSCK-002 — P0 — normalized references.** Every normalized manifest/unit is bounded and bound to
its `(raw_hash,tool_profile_hash,gen)`; chunk objects contain exact `spec_version:1`, identity fields,
`text_hash`, and `text`, bind the same tuple, and match the normalized span. Missing/mismatched refs
are reported as corruption, not config schema. (`03 §2.1, §5`, `10 §7.5`)

**CT4-FSCK-003 — P0 — raw recovery.** If a missing/corrupt raw object has an identical verified
working file and is not tombstoned or covered by an erase receipt, repair re-ingests it atomically
and forces one `commit_type=repaired` commit. All repaired and no missing exits 0. (`10 §7.5`, `05 §2.6`)

**CT4-FSCK-004 — P0 — unrecoverable report.** Ordinary missing remains exit 3, is appended to
errors.jsonl as `KIO-E-STORE-CORRUPT-001`, and JSON lists bounded affected commit hashes plus
`external_pointers_may_be_affected=true` (pointers have no registry). It never invents a pointer list
or emits bodies/secrets. (`10 §7.5`)

**CT4-FSCK-005 — P0 — truth boundary.** Chunk CAS is persisted and verified; `chunks.jsonl`/SQLite
alone can never make a pointer alive. The chunk body omits its own `chunk_hash`; a missing/wrong
`spec_version`, extra field, identity-vs-fanout mismatch, text-hash mismatch, or normalized-span
mismatch is corruption. Dual canonical/legacy disagreement, symlink/junction/hardlink, oversize, or
path-race fixtures fail closed. (`03 §2, §8.1`, `08 §3`)

**CT4-FSCK-006 — P1 — lock/fault recovery.** Lock contention exits 3 without mutation; interrupted
recovery leaves no published corrupt slot/temp and rerun converges. (`05 §6`, R23)

**CT4-FSCK-007 — P0 — purge terminals.** Default-tombstoned and valid erase-receipt-covered missing
raw/derived chunks are healthy dead terminals and fsck exits 0 if nothing else is wrong. In-progress
purge returns incomplete exit 3. Receipt-covered bytes are never auto-healed; malformed, wrong-leaf,
future-dated, timestamp-mismatched, missing/wrong-type/unreachable-commit, or conflicting receipts are
corruption. A verified raw plus stale receipt is healthy and repair retires the receipt without a
second content commit. (`05 §3.5`, `08 §4`, `10 §7.5`)

## E. Restore

Canonical executable syntax for this phase (the goal objective resolves the older CLI-summary
conflict) is:

```text
kio restore <evidence|path|commit-ref> --to <dir> [--force] [--yes]
```

Raw-hash shorthand is not a restore source. A commit ref is HEAD/full hash/tag. Evidence is a pointer
URI, inline JSON, or stdin. Any other operand first resolves as a commit tag; if no tag exists, it is
a portable logical direct-child path and resolves to the newest matching entry on HEAD's
**first-parent** ancestry (including a deleted final version). Merge side parents are not searched by
implicit path restore; evidence/commit operands remain available for them. Incomplete shallow
ancestry fails rather than guessing. Restore
reads verified CAS only, never mutable working bytes.

`--to` is an explicit external destination and may be outside the scope, but must not be the scope
root, `.kio`, or a `.kio` descendant. It and all existing ancestors/leaves must be real non-reparse
directories/files. Historical leaf names are validated for the current OS immediately before path
construction. Restore is lock-free with respect to `.kio` and never changes HEAD/manifest/index/CAS.

Stable JSON is `{status:"restored",source_kind,source_commit,destination,restored_count,
overwritten_count,files:[{path,path_at_commit,raw_hash,overwritten}]}`. A late partial publication adds
`error_code:"KIO-E-COMMIT-RESTORE-PARTIAL-001"`, `failed[]`, and exit 3.

**CT4-RESTORE-001 — P0 — CLI/source.** Missing `--to`, raw shorthand, extras, or invalid `--yes`
usage returns exit 2. HEAD/hash/tag, logical path, and pointer forms resolve deterministically; an
existing tag wins over a same-spelled path. (`05 §4`, `06 §5`)

**CT4-RESTORE-002 — P0 — commit bytes/names.** A two-file historical commit restores each verified
raw byte-for-byte under its historical name; an empty commit succeeds with count 0. Working tree and
all `.kio` state remain byte-identical. (`05 §4`)

**CT4-RESTORE-003 — P0 — deleted evidence/path.** A deleted-file pointer or logical path restores
exactly one raw under its safe historical path. Every restore source requiring a shallow commit/tree
returns `KIO-E-COMMIT-SHALLOW-001`; restore deliberately has a stricter rule than `view`/verify.
(`08 §3.2`, `05 §4`)

**CT4-RESTORE-004 — P0 — preflight/no clobber.** Any existing destination leaf conflicts even when
bytes match. Without force, full preflight writes zero final files. (`06 §5`)

**CT4-RESTORE-005 — P0 — force confirmation.** Force replaces regular leaves only and requires TTY
confirmation or `--yes`; rejection/non-TTY missing confirmation exits 9. Replacement is atomic per
file and final bytes are exact. (`06 §5, §7`)

**CT4-RESTORE-006 — P0 — destination safety.** Unsafe historical names, case-fold collisions,
symlink/junction/hardlink/device leaves, destination scope root/`.kio`, and ancestor replacement fail
before publication and never touch an outside target. (`03 §3`, Stage 0 materialization decision)

**CT4-RESTORE-007 — P0 — dead/corrupt source.** Tombstoned/erased/unreachable sources exit 4;
corrupt/missing raw from a live commit is store corruption; all fail before publication. (`05 §3-4`, `08 §4`)

**CT4-RESTORE-008 — P1 — atomic partial semantics.** Sources stream to private same-filesystem staged
files (0600 on Unix), are hash-verified, synced, then published. Preflight/source failure publishes
nothing; a late multi-file publication failure returns structured partial exit 3 and cleans temps. (R23)

**CT4-RESTORE-009 — P1 — rename/twins.** Old/new commits restore old/new names with identical bytes;
two identical-byte tree entries restore both names; an old pointer retains its historical name. (`03 §8.1`, `09 M3-2`)

**CT4-RESTORE-010 — P1 — ancestry bounds.** Logical-path restore succeeds at each exact independent
first-parent commit/tree-entry/byte maximum and fails one unit beyond with
`KIO-E-COMMIT-HISTORY-LIMIT-001`, publishing no destination file. Explicit evidence/commit restore
does not perform this ancestry walk. (`05 §1.6, §4`)

## F. Purge minimum

Typed CLI:

```text
kio purge <path> --reason <legal|privacy|misingest|copyright|other> [--erase-tombstone] [--yes]
kio purge --raw-hash sha256:<64hex> --reason <...> [--erase-tombstone] [--yes]
```

`path` and `--raw-hash` are exclusive. A path means every distinct raw ever bound to that logical
path in the selected scope. Shallow history makes path resolution incomplete and fails; raw-hash
purge remains possible. KIO never deletes the user's working file, so purge refuses while target bytes
remain anywhere in the current working tree. Default tombstones block future re-ingest. Erase mode
leaves no block and discloses that later explicit reintroduction of identical bytes is possible.

An existing identical tombstone makes default purge idempotent exit 0 without another commit. Turning
an existing tombstone into erase mode is deferred with the unresolved double-purge contract and is
rejected. Missing raw with no tombstone is target-not-found exit 4.

Purge holds the store lock and uses `.kio/purge/in-progress.json` as an owner-only resumable journal.
After the tombstone/in-progress visibility barrier, every read/search/index path rejects target content.
Failure after the barrier keeps the journal and returns retryable incomplete exit 3; rerun resumes.
Device-global observability append/scrub uses `$XDG_DATA_HOME/kio/logs/scrub.lock`; scope access-log
append/scrub uses `.kio/logs/access.scrub.lock`. Fixed acquisition order is scope store → reservation
ledger → device observability → scope access log. Purge performs a final scrub before journal removal.

Stable success JSON is `{status:"purged",purged_in_commit,reason,target_raw_count,
deleted_counts,shared_artifacts_preserved,tombstone_mode,tombstone_count,erase_receipt_count,logs_scrubbed,
log_files_scrubbed,log_rows_removed,log_fields_masked,guarantee,not_covered}`. It contains no target
raw hash/path/query/prompt. Incomplete uses the same bounded counts plus
`error_code:"KIO-E-PURGE-INCOMPLETE-001"` and exit 3.

**CT4-PURGE-001 — P0 — typed args/preview/confirmation.** Operand, exact reason enum, and confirmation
are mandatory. Preview happens before mutation. `no` exits 9 and byte-for-byte state is unchanged. (`06 §6`, `10 §7`)

**CT4-PURGE-002 — P0 — deletion surface.** Successful default purge removes target raw, prepared,
images no longer shared, all normalized profiles/gens, chunk CAS/ledger, SQLite FTS/vector/orphan
embeddings, target tasks/reservations, manifest rows, unsupported/quarantine target rows, and open
cache. Shared derived objects survive while referenced by non-target raws. (`05 §3.5`, `10 §7`)

**CT4-PURGE-003 — P0 — tombstone/dead pointer.** A.3 is written at canonical digest path; consistent
legacy duplicate is handled, conflict fails before barrier. Open/view/restore/object URI are dead;
verify is tombstoned (strict 4/non-strict 0). (`03 §2`, `08 §4.1`)

**CT4-PURGE-004 — P0 — erase.** After all postconditions, no canonical/legacy public tombstone or
journal remains, exactly one valid A.4 receipt per target remains, and old evidence is `not_found`.
The receipt is ignored by verify/open/search/restore and is never an index liveness/block decision;
it does not block explicit later ingest, whose successful re-publication of identical bytes retires it.
(`05 §3.5`, `08 §4.2`)

**CT4-PURGE-005 — P0 — immutable history + forced commit.** All prior commit/tree bytes/hashes remain;
one `commit_type=purged` child is created even when its tree equals the parent. Its message records only
the reason enum. No DAG rewrite occurs. (`05 §3.2, §3.5`)

**CT4-PURGE-006 — P0 — universal exclusion.** Default/at/history/deleted/since text/vector/hybrid,
old cursors, raw/chunk/image object URIs, index/reindex, restore, and fsck cannot reveal or resurrect a
target raw during the purge barrier or from remaining KIO-managed history after success. Default
tombstones bar future re-ingest; erase receipts only stop fsck auto-recovery and ordinary later
explicit ingest remains allowed. (`05 §3`, `10 §7`)

**CT4-PURGE-007 — P0 — scope isolation/aliases.** Same raw aliases in one scope are all affected;
another `.kio` with the same raw remains authoritative/alive/searchable. Global disposable cache may
be evicted but the other store is not mutated. (`05 §3.4`)

**CT4-PURGE-008 — P0 — logs.** Current/rotated scope access and device events/errors/metrics logs are
serialized against appenders and scrub target hash/path plus unredacted query/prompt conservatively.
The new audit event contains actor/reason/commit/counts only, never target identifiers/content. Result
reports rows removed/fields masked/files scrubbed. (`10 §7`)

**CT4-PURGE-009 — P0 — journal/fault injection.** Failure before barrier has no destructive effect.
Failure after each later phase leaks no content, returns `KIO-E-PURGE-INCOMPLETE-001` exit 3, and an
idempotent rerun converges to the exact successful postcondition. (R23, `05 §6`)

**CT4-PURGE-010 — P0 — path/live/shallow.** Path traverses all stored trees and collects all versions;
shallow traversal fails. A live working copy yields `KIO-E-PURGE-WORKING-COPY-001` exit 4 and no
mutation. The full-parent walk succeeds at each exact aggregate limit and fails one unit beyond with
`KIO-E-COMMIT-HISTORY-LIMIT-001` before the journal/barrier or any mutation. (`05 §1.6, §3.1, §3.5`)

**CT4-PURGE-011 — P0 — link/bounds/races.** Symlink, junction, unexpected hardlink, oversized ledger,
and ancestor replacement fail closed without unlinking outside the selected store. (R23)

**CT4-PURGE-012 — P1 — repeat/concurrency.** Identical default repeat is idempotent; store lock
contention exits 3; post-barrier readers see dead content while pre-barrier readers may finish their
already-open verified handle. (`05 §6`)

**CT4-PURGE-013 — P1 — guarantee wording.** Output says “removed from KIO-managed history” and lists
uncovered external backup/export/manual copies; it never claims universal deletion. (`10 §7`)

**CT4-PURGE-GC-001 — P0 — GC remains deferred.** `kio gc` returns the uniform not-implemented error
and deletes nothing; existing `GcPolicy` mappings still never select full commit deletion. (`05 §2`, `09 §3.1`)

## G. Bbox annotation

Configuration is `markdownize.bbox_annotation.enabled` (boolean, default true). The request includes a
fixed JSON schema with required `short_description` and `transcribed_text`; response arrays, strings,
and coordinates use explicit cardinality/byte/geometry bounds. Scope `.kio/config.toml` overrides the
user config value; absence at both levels means true. Tests use the built-in mock only.

Unit metadata records each annotation bound to its image hash, bbox, description, and transcription.
Chunk projection adds normalized annotation text immediately after the corresponding image URI for
search, while Evidence Pointer required fields remain unchanged. Annotation order follows page image
order, not provider object-map order.

The Mistral wire request uses A.2's exact `bbox_annotation_format`; it has no separate bbox prompt
field. The exact JCS request-format bytes, not a detached prose sentence, determine
`prompt_template_hash`. Each returned image must carry one `image_annotation` JSON string with the
exact two fields. Bounds: 256 images/page, 4,096/response,
4 KiB UTF-8 `short_description`, 64 KiB UTF-8 `transcribed_text`, 16 MiB aggregate annotations, and
integer bbox coordinates `0 <= x1 < x2 <= 1_000_000_000` / same for y.
String and aggregate byte bounds are enforced both on decoded provider strings and after canonical
escaping; escape expansion cannot exceed the persisted limits.

Before persisted projection and metadata storage, strings normalize newlines to LF and NFC, remove
non-newline controls, and source-escape each original scalar independently: `&`→`&amp;`, `<`→`&lt;`,
`>`→`&gt;`; every other ASCII punctuation scalar is prefixed with `\`; all other scalars are unchanged.
Every escaped line receives a trusted blockquote prefix. Immediately after the image URI the exact
form is:

```text
> KIO figure description: <line>   # repeated for each description line
> KIO figure text: <line>          # repeated for each transcription line
```

Thus provider headings, fences, links, autolinks, raw HTML, image syntax, controls, or fake `kio://`
text cannot create Markdown structure. The same post-escape strings are stored in structured metadata.
This persisted projection is part of `kio-markdown+bbox-annotation-v1`, so Evidence spans slice the
same bytes that search indexed.

**CT4-BBOX-001 — P0 — identity/default.** Default enabled uses A.2 profile; explicit disabled preserves
the old profile. Config change is `tool_changed`, never instance reuse. (`03 §5.1`, `07 §5.2`)

**CT4-BBOX-002 — P0 — request schema.** Enabled request sends one `bbox_annotation_format` whose
JCS equals A.2 byte-for-byte and whose computed prompt/profile hashes equal A.2; disabled sends no
annotation format. Budget estimate/accounting uses exactly 1.25× the same unannotated estimate and
never double-charges fallback. (`07 §5.2`, `04 §5.6`)

**CT4-BBOX-003 — P0 — metadata/search.** Mock chart labels absent from base OCR but present in
`transcribed_text` are persisted in unit metadata, projected next to the correct image, chunked, and
found by text search. Image URI and CAS bytes remain unchanged. (`07 §5.2`)

**CT4-BBOX-004 — P0 — validation/bounds.** Missing/extra/wrong-type fields, missing or duplicate
`image_annotation` on a returned image, invalid bbox geometry, or the frozen count/string/aggregate
bounds is contract violation with no partial publication. Annotation/image bijection follows exact
page/image order. Adversarial `[x](kio://...)`, `![x](...)`, `<img>`, `<kio://...>`, entity, backtick,
and multiline inputs round-trip as text; the annotation subtree's CommonMark AST contains no
provider-created link/image/raw-HTML/autolink node, and metadata holds the same escaped strings.
(`07 §5.2`, R23)

**CT4-BBOX-005 — P1 — incremental reuse.** Unchanged page annotations are reused without another
send/cost; changed/added pages alone are annotated; removed pages leave no searchable annotation. (`04 §2.2, §3.1`)

**CT4-BBOX-006 — P0 — persistence/task identity/from-scratch.** Normalized unit objects preserve
structured metadata with a legacy default, online task identity pins the annotation policy/profile so
old non-bbox Done work cannot suppress default-on work, and scanned PDFs/standalone images with no
text-layer prepared units still reach the OCR+bbox path. (`07 §5.2`, `04 §5`)

## H. Online Markdownize promotion

Promotion runs under the existing whole-command store lock after a Done/accepted online task. It
re-verifies current `(path,raw_hash)`, the normalized manifest/unit set, and the resolved immutable
profile. Stale/superseded/partial/failed outputs are never promoted.

One batch of accepted outputs updates tool-lock atomically, creates an auto commit whose matching tree
entries use the resolved `(tool_profile_hash,gen)`, then atomically rebuilds SQLite. HEAD is truth; an
index-swap failure is the existing visible rebuilding state and is recoverable by repair/retry.

**CT4-PROMOTION-001 — P0 — end-to-end mock.** Online mock Done produces normalized units, advances
HEAD once, changes matching tree normalize ref to the resolved profile/gen, materializes that profile
in tool-lock without execution/auth fields, rebuilds SQLite, and makes unique mock text searchable. (F6)

**CT4-PROMOTION-002 — P0 — provenance.** Commit `tool_lock_hash`, tree normalize ref, manifest identity,
chunks, and SQLite rows all name the same resolved immutable profile. Placeholder/alias hashes never
reach durable truth. (`03 §5`, `07 §6`)

**CT4-PROMOTION-003 — P0 — stale/partial/failure.** Edit/delete/path-secret transition after enqueue,
provider partial, acceptance failure, auth/rate/network error, or changed pin does not promote stale
content or charge outside existing reservation rules. (`04 §5`, R23)

**CT4-PROMOTION-004 — P0 — idempotence/atomicity.** Repeated `batch resume` or ordinary `index`
promotion reconciliation of the same Done identity creates no second promotion commit/task/charge;
`reindex --force` retains its separate gen+1 semantics. Fault before HEAD leaves no promoted ref;
fault after HEAD is loudly rebuilding and repair converges without losing old pointers. (`05 §6`, F6)

**CT4-PROMOTION-005 — P1 — multi-file batch.** Multiple Done tasks promote in one deterministic
path-sorted tree/commit and one SQLite swap; unaffected entries retain prior profiles. (F6)

## I. Evaluation and MVP decision

**CT4-EVAL-001 — P0 — harness unit tests.** `python3 -m unittest eval.test_run_eval` is green; golden,
corpus spec, and history fixture hashes are unchanged. (`09 §4.3`)

**CT4-EVAL-002 — P0 — replay proves history.** Fresh generated corpus replay records rename=7,
edit=3, delete=9 and verifies multi-commit histories. Evaluation refuses a missing/stale history
manifest. (`09 §4.3`)

**CT4-EVAL-003 — P0 — M3-2 full scoring.** All 16 frozen queries execute `--all-history`; all are
scored (not unimplemented/skipped), including the three edited-old-value anchors. Recall@10 >= 0.8;
rename fixtures expose both old/new path hits for the same raw chunk and results carry
identity-correct historical pointers/current path. (`09 §4 M3-2`)

**CT4-EVAL-004 — P0 — M3-3 full scoring.** All 16 frozen queries execute `--include-deleted`; all are
scored, Recall@10 >= 0.8, and returned evidence restores without touching the working tree. (`09 §4 M3-3`)

**CT4-EVAL-005 — P0 — false-pass guard.** A HEAD-only implementation cannot pass M3-2 merely because
13/16 happen to remain live: the harness verifies each expected historical raw identity and requires
all frozen queries to execute. (`09 §4.3`)

**CT4-EVAL-006 — P1 — latency/evidence.** Synthetic p95 is <7s for M3-2/M3-3 and required Evidence
fields are present in 100% of scored hits. (`09 §4.1`)

## J. Final gates

Step 4 may be called complete only after all P0 contracts, existing R23 regressions, workspace fmt /
locked clippy / locked tests / release build, M3-2 and M3-3 Recall gates, and Windows/macOS/Linux/MSRV
1.86 CI are green. No merge, tag, release, real API/data validation, R23 re-adjudication, or sealed
audit-export change is part of this phase.
