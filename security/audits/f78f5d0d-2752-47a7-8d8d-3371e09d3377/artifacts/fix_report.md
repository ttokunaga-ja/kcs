# KCS R23 Security Remediation Report

## Outcome

- Remediation outcome: `fixed` in the local working tree.
- Reportable findings addressed: 47 of 47.
- Scan ID: `f78f5d0d-2752-47a7-8d8d-3371e09d3377`.
- Scan target: `/Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kcs`.
- Scan revision and current `HEAD`: `0e19f3c6489da458e93a982a333c308d92d0a0ae`.
- Remediation branch: `codex/security-r23-remediation`.
- Finalized at: `2026-07-12T00:02:24Z`.
- Delivery state: uncommitted and unpushed, as requested.

The target checkout and `HEAD` remained bound to the scanned revision while the fixes were
implemented as working-tree changes. No repository checkout, scan target, scan ID, or scan
workspace was replaced. No new security scan was created.

## Security Invariants Restored

The changes restore the following cross-cutting invariants:

1. External adapter execution is fail-closed: only declared built-in targets are accepted,
   redirects are rejected, authenticated reads are bounded, compressed responses are rejected,
   and response shape, cardinality, geometry, vector domain, and persistence limits are checked.
   Because ureq 2 gives the overall timeout precedence, the effective deadline is explicitly the
   strictest of the overall, read, and write limits.
2. A file is authorized, hashed, parsed, charged, and sent from one verified file identity and
   one bounded byte stream. Pathname reopens cannot substitute outside-scope or replacement data.
3. Durable state is bounded and semantically revalidated. CAS, DAG, task, manifest, unsupported
   input, reservation, normalized-unit, and evidence-pointer records cannot escape their owning
   store or silently adopt preseeded links.
4. Secret, ignore, terminal-failure, retry, and budget states remain terminal-dominant. Content
   twins and legacy duplicate rows cannot bypass holds, revive permanent failures, or mint credit.
5. Unicode glob matching, PDF handling, LCS mapping, directory scans, JSONL framing, archive
   materialization, and CAS reads have symmetric work and size limits.
6. Human-readable output neutralizes terminal controls, while structured JSON retains the
   original message data.
7. CLI integration tests scrub provider credentials and every repository test seam from child
   processes by default. A test must opt in after constructing the hermetic command.
8. Windows path binding uses stable Win32 handle identity (volume serial plus 64-bit file index)
   and fails closed when identity, type, reparse-point, size, timestamp, or link checks fail.
9. Aggregate index status treats a vanished or unopenable scope as incomplete for both task and
   unsupported-input projections and emits a scoped error instead of silently dropping it.

## Finding Disposition

All rows below are `fixed` in this working tree. The verification anchors name the primary
regression boundary; the complete workspace test run exercises their integration.

| Candidate | Severity | Remediation and primary verification anchor |
|---|---:|---|
| KCS-R23-CAND-001 | Low | Terminal embedding failures dominate secret-hold duplicates; legacy releasable holds are removed. `r23_cand_001_*` regressions. |
| KCS-R23-CAND-003 | Medium | Gemini vectors require finite values, valid dimension, and positive finite norm. `embedding_numeric_domain_is_validated_after_f32_conversion` and vector boundary tests. |
| KCS-R23-CAND-004 | Medium | OCR bounding-box arithmetic and geometry use checked operations and reject invalid values. `bbox_arithmetic_and_geometry_are_checked`. |
| KCS-R23-CAND-005 | Medium | `?` matches one Unicode scalar and matching is applied consistently in scan preview. `r23_cand_005_*`. |
| KCS-R23-CAND-006 | Medium | PDF page discovery is structural and page cardinality is bounded before derived work. `r23_cand_006_prepare_rejects_pdf_page_count_over_limit`. |
| KCS-R23-CAND-007 | Medium | LCS cell counts use checked arithmetic and oversized mappings fail to a full-change path. `r23_cand_007_*`. |
| KCS-R23-CAND-008 | Medium | Existing `.kcs` roots must be real, contained directories; symlinked stores are rejected. `cand_008_symlinked_kcs_store_is_rejected`. |
| KCS-R23-CAND-011 | Medium | Secret classification and hold state are established before content-twin vector publication. Existing N1/R21/R22 secret-twin contracts. |
| KCS-R23-CAND-012 | Low | Materialized twin output converges eligible paused/failed legacy tasks without resending or recharging. Task recovery and materialized-output regressions. |
| KCS-R23-CAND-013 | Medium | `AuthError` remains terminal during batch retry and cannot be revived by reconciliation. Existing auth retry contracts and task recovery tests. |
| KCS-R23-CAND-014 | Medium | Unsupported inputs are durably disclosed in a bounded, fail-loud, no-follow store; shallow status remains explicitly incomplete. `r23_cand_014_*`. |
| KCS-R23-CAND-017 | Medium | Glob matching uses a bounded state space instead of recursive exponential backtracking. `r23_cand_017_*`. |
| KCS-R23-CAND-018 | Low | Snapshot reads remain bound to a verified regular-file handle and reject replacements. `cand_018_*`. |
| KCS-R23-CAND-019 | Medium | Direct-child reads, archive bytes, individual files, aggregate bytes, and tree entries are bounded before publication. `cand_019_*` and `cand_046_snapshot_rejects_tree_entry_overflow_before_publication`. |
| KCS-R23-CAND-020 | Medium | OCR HTTP reads, decoded body, pages, images, text, and persisted output are bounded. OCR cardinality, content, and image-quota tests. |
| KCS-R23-CAND-022 | Medium | Mistral model resolution uses bounded authenticated reads and rejects redirects/compression. `http_policy::*` tests. |
| KCS-R23-CAND-023 | Medium | Gemini embedding responses use the same bounded authenticated response policy before JSON allocation. `http_policy::*` and embedding response tests. |
| KCS-R23-CAND-024 | Medium | Existing `.kcs` stores require the current owner and private mode before use. `cand_024_existing_store_requires_private_owner_mode`. |
| KCS-R23-CAND-025 | Medium | Consent is device-local and bound to canonical root, scope, tool, and operation. `cand_025_portable_approvals_do_not_grant_new_root_but_local_approval_does`. |
| KCS-R23-CAND-027 | Medium | Scan authorization, identity, hash, and bytes come from one no-follow, scope-contained handle. `r23_cand_027_*`. |
| KCS-R23-CAND-028 | Medium | OCR sends the exact bytes whose identity and digest were verified; later pathname replacement is irrelevant. `exact_verified_bytes_cross_the_ocr_client_boundary`. |
| KCS-R23-CAND-029 | Low | Deterministic normalization persists bytes bound to the declared raw hash. Verified-byte deterministic tests. |
| KCS-R23-CAND-030 | Low | Deterministic PDF processing parses one verified byte buffer rather than reopening per page. Verified PDF reuse tests. |
| KCS-R23-CAND-031 | Low | Prepare and markdown charge/send share one verified input; CAS slots must match exact bytes. `r23_cand_031_*` and `r23_markdown_charge_and_send_share_one_verified_input`. |
| KCS-R23-CAND-032 | Medium | Scan and prepare hashes stream from bounded verified handles rather than allocating the full file. `r23_cand_032_*`. |
| KCS-R23-CAND-033 | Low | Deferred OCR inputs are size-checked and identity-bound before materialization; retry unit subsets are validated. Bounded task input and current-policy tests. |
| KCS-R23-CAND-034 | Medium | Deterministic PDF structure is parsed once and reused across page normalization. Structural PDF tests. |
| KCS-R23-CAND-036 | Medium | Persisted tree and commit objects receive bounded semantic validation, including tag, hash, sort, duplicate, and platform-safe path rules. `cand_036_*` and DAG semantic tests. |
| KCS-R23-CAND-038 | Medium | Markdown adapter declarations must match the built-in Mistral runtime; discarded or alternate targets are rejected. `declared_targets_must_match_builtin_runtime`. |
| KCS-R23-CAND-039 | Medium | Embedding adapter declarations must match the built-in Gemini runtime. Catalog and tool-lock target tests. |
| KCS-R23-CAND-040 | Medium | Authenticated adapter clients reject redirects, preventing credential forwarding across origins. `authenticated_agent_rejects_redirect_responses`. |
| KCS-R23-CAND-041 | Low | Closing snapshot reclassifies current names and excludes newly introduced Tier-A secrets. `cand_041_closing_snapshot_reclassifies_new_tier_a_names`. |
| KCS-R23-CAND-042 | Low | A normalization reference is attached only to its expected current raw hash. `cand_042_normalize_ref_attaches_only_to_its_expected_raw_hash`. |
| KCS-R23-CAND-043 | Low | CAS publication verifies pre-existing bytes and rejects directories, symlinks, hardlinks, and corrupt occupied slots. `cand_043_*`. |
| KCS-R23-CAND-046 | Low | CAS reads are bounded before materialization; streamed inspection still validates size and digest. `cand_046_*`. |
| KCS-R23-CAND-047 | Medium | Task `output_ref` is typed, hash-bound, and confined below a real normalized-store root with safe ancestors. `cand_047_*`. |
| KCS-R23-CAND-048 | Medium | Reservation claims are fully bound, consumed once, and reclaim only eligible known outcomes; stale locks recover without fabricated credit. `cand_048_*`. |
| KCS-R23-CAND-049 | Medium | Manifest unit references are validated as local typed names and rebound to the owning instance and file identity. `cand_049_*`. |
| KCS-R23-CAND-050 | Low | Task JSONL files and records use matching framed read/write bounds before allocation or parsing. `cand_050_*`. |
| KCS-R23-CAND-051 | Medium | OCR page indices must be unique, complete, and cardinality-consistent before evidence units are bound. `duplicate_or_incomplete_ocr_page_indices_are_rejected`. |
| KCS-R23-CAND-057 | Low | Working-tree raw resolution reserves worst-case work, charges failures, and caps direct children at 100,000. `r23_cand_057_scan_budget_charges_failures_and_caps_empty_entries`. |
| KCS-R23-CAND-059 | Medium | Human output escapes C0/C1, ESC, DEL, and all bidi controls; JSON preserves the original message. `r23_cand_059_*`. |
| KCS-R23-CAND-061 | Medium | Normalized manifests and units are rebound to the complete provenance tuple, exact identity, size, and safe writer roots. `cand_061_*`. |
| KCS-R23-CAND-064 | Low | Batch recovery validates the repository tool lock before any persisted task mutation. `cand_064_malformed_tool_lock_blocks_batch_before_task_mutation`. |
| KCS-R23-CAND-067 | Medium | Durable OCR work is reauthorized against the current bounded ignore policy before send. `r23_cand_067_current_ignore_policy_reauthorizes_durable_input`. |
| KCS-R23-CAND-068 | Medium | Same-identity embedding requests are grouped and fan out one canonical vector to authoritative and KNN stores. Duplicate identity vector tests. |
| KCS-R23-CAND-069 | High | Every EvidencePointer hash is parsed as a canonical digest before storage resolution; traversal and absolute values are rejected. `r23_cand_069_*`. |

## Changed Surface

The working-tree changes are intentionally confined to the affected runtime, tests, CI, and
adapter documentation:

- `.github/workflows/ci.yml`: locked Rust 1.86 all-target check plus full-workspace Linux,
  macOS, and Windows jobs.
- `Cargo.toml` and `Cargo.lock`: truthful Rust 1.86 MSRV, compression-disabled workspace HTTP
  defaults, stable Windows API dependency, and dependency resolution.
- `crates/kcs-adapter`: catalog/target validation, bounded HTTP policy, verified deterministic
  input, OCR bounds, vector validation, and tool-lock enforcement.
- `crates/kcs-cli/src/main.rs` and CLI contract tests: state-machine convergence, consent,
  terminal sanitization, bounded lookup, current-policy checks, status completeness, and batch
  lock enforcement.
- `crates/kcs-core`: bounded immutable CAS, semantic DAG validation, secure scope/store
  ownership, no-follow snapshot reads, and write-side cardinality symmetry.
- `crates/kcs-index/src/embedding_store.rs`: validated vectors and canonical duplicate-identity
  publication.
- `crates/kcs-pipeline`: reservation ledger, normalized provenance, verified preparation and
  scanning, bounded task store, safe store roots, and durable unsupported-input state.
- `crates/kcs-search/src/evidence.rs`: canonical hash validation for all pointer forms.
- `docs/03-data-model.md`, `docs/07-adapter-spec.md`, and `docs/10-operations.md`: implemented
  built-in roles are separated from the future external Adapter dispatcher contract.

New source/test files:

- `crates/kcs-adapter/src/http_policy.rs`
- `crates/kcs-pipeline/src/store_path.rs`
- `crates/kcs-pipeline/src/unsupported.rs`
- `crates/kcs-pipeline/src/windows_file.rs`
- `crates/kcs-cli/tests/security_r23.rs`

## Verification

### Complete local test runs

Initial serial baseline:

```text
cargo test --workspace --all-targets -- --test-threads=1
```

Result before the follow-on delivery hardening: `617 passed; 0 failed`.

The normal parallel command was then executed twice in isolation:

```text
cargo test --workspace --all-targets
```

Both isolated parallel runs also completed with `617 passed; 0 failed`.

Final locked command after the delivery-gap fixes:

```text
cargo test --workspace --all-targets --locked
```

Final result: `625 passed; 0 failed`.

Suite breakdown:

| Test binary | Passed |
|---|---:|
| kcs-adapter unit tests | 59 |
| kcs-cli unit tests | 37 |
| CLI contract tests | 12 |
| R23 security integration tests | 4 |
| Step 2 contract tests | 104 |
| Step 3 contract tests | 206 |
| kcs-core unit tests | 48 |
| kcs-core contract vectors | 14 |
| kcs-index unit tests | 36 |
| kcs-pipeline unit tests | 82 |
| kcs-search unit tests | 23 |

An earlier invocation, while other Cargo processes were writing the same target directory,
temporarily could not find `target/debug/kcs`. The exact test passed on immediate serial rerun,
and two isolated normal parallel workspace runs passed afterward. No standalone test-fixture race
was reproduced; the observation is classified as concurrent build-process interference rather
than a product or fixture failure.

### Static gates

| Command | Result |
|---|---|
| `cargo fmt --all -- --check` | Pass |
| `cargo clippy --workspace --all-targets --locked -- -D warnings` | Pass |
| `cargo check --workspace --all-targets --locked` | Pass |
| `git diff --check` | Pass |
| `rg -n 'debug online|debug persist|dbg!\(|eprintln!\("debug' crates` | No matches (expected exit 1) |
| Stable-API search for Windows nightly `MetadataExt` identity methods | No matches |
| Synthetic poisoned parent environment against `security_r23` | 4 passed; no trace file created |

### Saved probe and positive-control evidence

- The saved safe synthetic probes for candidates 057, 059, 061, 064, 067, 068, and 069
  completed successfully against the remediated tree.
- Dedicated read-only verification for 019, 020, 022, 023, 024, 025, 027, 028, 029, 030, 031,
  032, 033, and 034 found no remaining reachable path after the fixes.
- Dedicated read-only verification for 036, 038, 039, 040, 041, 042, 043, 046, 047, 048, 049,
  050, and 051 likewise found no remaining reachable path; package and focused regressions passed.
- A final independent diff review found no unresolved actionable blocker after the root-symlink,
  current-policy, task-state, retry-subset, tree-cardinality, platform-path, and missing-object
  classifications were corrected.
- Positive controls remain accepted: exact size limits are accepted while `limit + 1` is rejected;
  real single-link store files append/read normally; in-scope canonical pointers resolve; finite
  normalized vectors persist; and sequential legitimate reservation writers retain their credit.

## Safety Refusal Record

The post-fix verifier assigned to 001, 003, 004, 005, 006, 007, 008, 011, 012, 013, 014, 017,
and 018 returned the following exact message:

```text
Agent errored: This content was flagged for possible cybersecurity risk. If this seems wrong, try rephrasing your request. To get authorized for security work, join the Trusted Access for Cyber program: https://chatgpt.com/cyber

This agent's turn failed. If you still need this agent, use the available collaboration tools to give it another task.
```

The refusal was not retried, rephrased, category-masked, or routed to another provider. The
collaboration result did not expose a model identifier or event timestamp, so neither is guessed.
Those exact 13 candidates were instead closed with focused source-backed regression tests and the
complete local suite above. Historical write-up refusal and invalid-route evidence remains
unchanged in `artifacts/05_findings/writeup_worklist.json` and
`artifacts/05_findings/writeup_provenance_audit.json`.

## Validation Boundaries

- No real provider, credential, external network, third-party system, or production-target test
  was performed. Adapter behavior was validated with local mocks, bounded local servers, synthetic
  input, and source-backed regression tests.
- Windows-only identity and path branches were not executed on this macOS host. They now use stable
  Win32 APIs and have a full-workspace `windows-latest` job configured, but that job remains pending
  because this unpushed branch has not run CI. The macOS full-workspace job is also configured.
- Rust 1.86 is the corrected MSRV. A locked all-target CI check is configured, not yet executed.
  This host has only the default stable toolchain and Rust 1.97 installed, so 1.86 was not run
  locally and no toolchain was downloaded.
- The fixes are present only in the uncommitted local branch. No deployment claim is made.

## Delivery

The repository itself contains only the remediation working-tree changes. This report is stored
under the existing scan directory as an audit artifact. The original generated report and existing
finding/write-up artifacts were not overwritten.
