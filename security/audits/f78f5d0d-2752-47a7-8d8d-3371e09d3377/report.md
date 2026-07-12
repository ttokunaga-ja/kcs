# Security Review: kcs

## Scope

Deep repository scan of KCS at the fixed target revision.

- Scan mode: deep_repository
- Target kind: git_revision
- Target ID: target_sha256_5f564eafaec7c5be5962c948120cedc6ff55c83a742cfdd830d07cbe62ee69a2
- Revision: 0e19f3c6489da458e93a982a333c308d92d0a0ae
- Inventory strategy: repository
- Included paths: .
- Excluded paths: none
- Runtime or test status: No live third-party targets were exercised during final reporting; local and synthetic PoCs are linked from write-ups.
- Artifacts reviewed: 420/420 coverage rows, 69 validation decisions, 47 final reportable findings, 47 accepted detailed write-ups
- Scan context: The scan was resumed from reporting artifacts only; no new scan, discovery, validation, or attack-path adjudication was run.

Limitations and exclusions:
- Hardening proposals are design guidance and are not implemented fixes.
- Some legacy accepted receipts retain pending coordinator fields; the later provenance audit records formal acceptance and matching hashes.

### Scan Summary

| Field | Value |
| --- | --- |
| Reportable DSS findings | 47 |
| Report instances | 47 |
| Report severity mix | high: 1, medium: 32, low: 14 |
| Report confidence mix | high: 33, medium: 14 |
| Coverage | complete |
| Validation mode | Saved validation and attack-path evidence plus local artifact integrity checks. |

Canonical artifacts: `scan-manifest.json`, `findings.json`, and `coverage.json`. This report is a deterministic projection of those files.

## Threat Model

KCS processes lower-trust repository content, provider responses, persisted task state, and local stores. The main objectives are preserving repository scope isolation, secret handling, provenance integrity, bounded resource use, and credential confinement.

### Assets

- repository contents and derived normalized units
- local .kcs store and CAS objects
- provider API credentials and responses
- embedding, OCR, and search indexes
- scan provenance and audit reports

### Trust Boundaries

- repository-controlled paths and file bytes entering KCS
- external OCR and embedding provider responses
- persisted task and budget state replayed across runs
- human-readable terminal output
- local store adoption and scope validation

### Attacker Capabilities

- commit or place crafted files in a repository processed by KCS
- preseed or race local paths in a working tree under review
- control oversized or malformed provider-like response data in tests or adapters
- replay or tamper with persisted KCS task records when local store integrity is not enforced

### Security Objectives

- bind authorized scope to the final bytes consumed
- bound reads, allocations, provider responses, and derived work before materialization
- keep provider credentials and adapter targets scoped to their intended origin
- make persisted workflow state replay-safe and auditable

### Assumptions

- The attacker is local to repository content or scan inputs, not a live third-party service attacker in final reporting.

## Findings

| Findings | Reports | Severity | Confidence | Detailed write-up |
| --- | --- | --- | --- | --- |
| Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files | [KCS-R23-CAND-069](#finding-1) | high | high | [Open KCS-R23-CAND-069](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md) |
| a new secret content twin is vector-linked before its hold exists | [KCS-R23-CAND-011](#finding-2) | medium | high | [Open KCS-R23-CAND-011](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md) |
| Human-readable CLI output emits untrusted terminal control sequences | [KCS-R23-CAND-059](#finding-3) | medium | high | [Open KCS-R23-CAND-059](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md) |
| scan hashing allocates the full file before the input-size gate | [KCS-R23-CAND-032](#finding-4) | medium | high | [Open KCS-R23-CAND-032](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md) |
| A symlinked `.kcs` binds one working root to another scope's live store | [KCS-R23-CAND-008](#finding-5) | medium | high | [Open KCS-R23-CAND-008](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md) |
| recursive star matching has exponential backtracking | [KCS-R23-CAND-017](#finding-6) | medium | high | [Open KCS-R23-CAND-017](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md) |
| unbound reservation stamps can forge budget-reclaim credits | [KCS-R23-CAND-048](#finding-7) | medium | high | [Open KCS-R23-CAND-048](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md) |
| Gemini API keys are retained across cross-origin redirects | [KCS-R23-CAND-040](#finding-8) | medium | high | [Open KCS-R23-CAND-040](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md) |
| Store-local consent records are forgeable or replayable across preseeded or copied scopes | [KCS-R23-CAND-025](#finding-9) | medium | high | [Open KCS-R23-CAND-025](findings/forgeable-store-consent/forgeable-store-consent.md) |
| Scan-time replacement can authorize an outside-scope file under a benign name | [KCS-R23-CAND-027](#finding-10) | medium | high | [Open KCS-R23-CAND-027](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md) |
| Opening an existing permissive `.kcs` exposes future private archive bytes | [KCS-R23-CAND-024](#finding-11) | medium | high | [Open KCS-R23-CAND-024](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md) |
| Embedding reconciliation revives AuthError work during batch retry | [KCS-R23-CAND-013](#finding-12) | medium | high | [Open KCS-R23-CAND-013](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md) |
| Accepted embedding adapter targets are discarded before fixed Gemini execution | [KCS-R23-CAND-039](#finding-13) | medium | high | [Open KCS-R23-CAND-039](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md) |
| OCR bounding-box arithmetic can overflow | [KCS-R23-CAND-004](#finding-14) | medium | high | [Open KCS-R23-CAND-004](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md) |
| lexical PDF page markers amplify derived work without a cardinality bound | [KCS-R23-CAND-006](#finding-15) | medium | high | [Open KCS-R23-CAND-006](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md) |
| Gemini embedding responses lack body and read-time bounds before semantic checks | [KCS-R23-CAND-023](#finding-16) | medium | high | [Open KCS-R23-CAND-023](findings/gemini-response-bounds/gemini-response-bounds.md) |
| Mistral OCR reopens the path after the final hash check and sends unbound bytes | [KCS-R23-CAND-028](#finding-17) | medium | high | [Open KCS-R23-CAND-028](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md) |
| same-batch duplicate embedding identities split authoritative and KNN vectors | [KCS-R23-CAND-068](#finding-18) | medium | high | [Open KCS-R23-CAND-068](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md) |
| Gemini vectors lack numeric-domain and positive-norm validation | [KCS-R23-CAND-003](#finding-19) | medium | high | [Open KCS-R23-CAND-003](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md) |
| Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape | [KCS-R23-CAND-036](#finding-20) | medium | high | [Open KCS-R23-CAND-036](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md) |
| normalized manifests and unit objects are not rebound to the requested provenance tuple | [KCS-R23-CAND-061](#finding-21) | medium | high | [Open KCS-R23-CAND-061](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md) |
| Duplicate OCR page indices bind one provider page to multiple evidence units | [KCS-R23-CAND-051](#finding-22) | medium | high | [Open KCS-R23-CAND-051](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md) |
| Persisted OCR tasks bypass current ignore authorization | [KCS-R23-CAND-067](#finding-23) | medium | high | [Open KCS-R23-CAND-067](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md) |
| incremental unit mapping allocates a quadratic LCS matrix | [KCS-R23-CAND-007](#finding-24) | medium | high | [Open KCS-R23-CAND-007](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md) |
| Mistral model resolution lacks response-body and read-time bounds | [KCS-R23-CAND-022](#finding-25) | medium | high | [Open KCS-R23-CAND-022](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md) |
| Mistral OCR responses lack read, body, cardinality, and persistence bounds | [KCS-R23-CAND-020](#finding-26) | medium | high | [Open KCS-R23-CAND-020](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md) |
| Accepted markdown adapter targets are discarded before fixed Mistral execution | [KCS-R23-CAND-038](#finding-27) | medium | high | [Open KCS-R23-CAND-038](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md) |
| Deterministic PDF handling reparses the whole file once per page | [KCS-R23-CAND-034](#finding-28) | medium | high | [Open KCS-R23-CAND-034](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md) |
| byte-oriented question-mark globs bypass Unicode names | [KCS-R23-CAND-005](#finding-29) | medium | high | [Open KCS-R23-CAND-005](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md) |
| Persisted manifest unit_ref can escape its normalized-instance directory | [KCS-R23-CAND-049](#finding-30) | medium | high | [Open KCS-R23-CAND-049](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md) |
| status and snapshot read unbounded direct-child files before any cap | [KCS-R23-CAND-019](#finding-31) | medium | high | [Open KCS-R23-CAND-019](findings/unbounded-direct-child-read/unbounded-direct-child-read.md) |
| Unrecognized binary gaps disappear from durable completeness and path telemetry | [KCS-R23-CAND-014](#finding-32) | medium | high | [Open KCS-R23-CAND-014](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md) |
| Persisted task output_ref can escape the scope | [KCS-R23-CAND-047](#finding-33) | medium | high | [Open KCS-R23-CAND-047](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md) |
| Prepare-stage reopen can poison prepared CAS identity | [KCS-R23-CAND-031](#finding-34) | low | medium | [Open KCS-R23-CAND-031](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md) |
| CAS reads allocate attacker-sized objects before verification | [KCS-R23-CAND-046](#finding-35) | low | medium | [Open KCS-R23-CAND-046](findings/cas-read-before-verification/cas-read-before-verification.md) |
| Batch recovery bypasses repository tool-lock validation | [KCS-R23-CAND-064](#finding-36) | low | medium | [Open KCS-R23-CAND-064](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md) |
| closing snapshot can ingest a newly introduced Tier-A secret | [KCS-R23-CAND-041](#finding-37) | low | medium | [Open KCS-R23-CAND-041](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md) |
| Content-twin reuse leaves completed budget-paused tasks falsely pending | [KCS-R23-CAND-012](#finding-38) | low | medium | [Open KCS-R23-CAND-012](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md) |
| CAS write accepts a pre-existing corrupt destination as success | [KCS-R23-CAND-043](#finding-39) | low | medium | [Open KCS-R23-CAND-043](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md) |
| closing snapshot can attach normalization metadata to different bytes | [KCS-R23-CAND-042](#finding-40) | low | medium | [Open KCS-R23-CAND-042](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md) |
| Deterministic normalization persists a later path read under the earlier raw hash | [KCS-R23-CAND-029](#finding-41) | low | medium | [Open KCS-R23-CAND-029](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md) |
| Snapshot's regular-file check can be raced into archiving an outside-scope symlink target | [KCS-R23-CAND-018](#finding-42) | low | medium | [Open KCS-R23-CAND-018](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md) |
| Raw-hash working-tree resolution reads every direct child without bounds | [KCS-R23-CAND-057](#finding-43) | low | medium | [Open KCS-R23-CAND-057](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md) |
| Deterministic PDF normalization repeatedly reopens an unbound pathname | [KCS-R23-CAND-030](#finding-44) | low | medium | [Open KCS-R23-CAND-030](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md) |
| Oversized task JSONL records allocate before validation | [KCS-R23-CAND-050](#finding-45) | low | medium | [Open KCS-R23-CAND-050](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md) |
| secret-hold cycles erase terminal embedding failure state | [KCS-R23-CAND-001](#finding-46) | low | medium | [Open KCS-R23-CAND-001](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md) |
| Deferred OCR tasks read replacement files before enforcing the cap | [KCS-R23-CAND-033](#finding-47) | low | medium | [Open KCS-R23-CAND-033](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md) |

### Confidence Scale

| Label | Meaning |
| --- | --- |
| high | Direct evidence supports the finding with no material unresolved blocker. |
| medium | Evidence supports a plausible issue, but material runtime or reachability proof remains. |
| low | Evidence is incomplete and the item is retained only for explicit follow-up. |

<a id="finding-1"></a>

### [1] Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files

| Field | Value |
| --- | --- |
| Severity | high |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-search/src/evidence.rs:9-30, crates/kcs-cli/src/main.rs:4576-4586, crates/kcs-cli/src/main.rs:4773-4784, crates/kcs-cli/src/main.rs:5207-5226 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md).

<a id="finding-2"></a>

### [2] a new secret content twin is vector-linked before its hold exists

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Sensitive data exposure |
| CWE | CWE-200 Exposure of Sensitive Information |
| Affected lines | crates/kcs-cli/src/main.rs:620-653, crates/kcs-cli/src/main.rs:3008-3027, crates/kcs-index/src/embedding_store.rs:149-185, crates/kcs-cli/src/main.rs:7848-7936 |

#### Summary

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

#### Validation

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

#### Dataflow

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

#### Reachability

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

#### Severity

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

#### Remediation

See the [detailed technical write-up](findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md).

<a id="finding-3"></a>

### [3] Human-readable CLI output emits untrusted terminal control sequences

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper output encoding |
| CWE | CWE-116 Improper Encoding or Escaping of Output |
| Affected lines | crates/kcs-cli/src/main.rs:2816-2835, crates/kcs-cli/src/main.rs:4823-4859, crates/kcs-cli/src/main.rs:11135-11176, crates/kcs-cli/src/main.rs:11184-11193 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md).

<a id="finding-4"></a>

### [4] scan hashing allocates the full file before the input-size gate

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:558-584, crates/kcs-pipeline/src/scan.rs:90-159, crates/kcs-cli/src/main.rs:9047-9070, crates/kcs-cli/src/main.rs:4425-4444 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md).

<a id="finding-5"></a>

### [5] A symlinked `.kcs` binds one working root to another scope's live store

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-core/src/scope.rs:126-139, crates/kcs-core/src/scope.rs:188-200, crates/kcs-core/src/scope.rs:889-909, crates/kcs-core/src/scope.rs:254-303 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md).

<a id="finding-6"></a>

### [6] recursive star matching has exponential backtracking

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-pipeline/src/scan.rs:178-200, crates/kcs-pipeline/src/scan.rs:90-159, crates/kcs-pipeline/src/scan.rs:383-415, crates/kcs-cli/src/main.rs:452-472 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md).

<a id="finding-7"></a>

### [7] unbound reservation stamps can forge budget-reclaim credits

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-pipeline/src/task.rs:41-74, crates/kcs-cli/src/main.rs:8987-9037, crates/kcs-cli/src/main.rs:9977-9996, crates/kcs-cli/src/main.rs:10226-10261 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md).

<a id="finding-8"></a>

### [8] Gemini API keys are retained across cross-origin redirects

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Sensitive data exposure |
| CWE | CWE-200 Exposure of Sensitive Information |
| Affected lines | crates/kcs-adapter/src/gemini_embedding.rs:71-80, crates/kcs-adapter/src/gemini_embedding.rs:120-148, crates/kcs-adapter/src/gemini_embedding.rs:206-220, Cargo.toml:17-29 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md).

<a id="finding-9"></a>

### [9] Store-local consent records are forgeable or replayable across preseeded or copied scopes

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-core/src/scope.rs:188-200, crates/kcs-core/src/scope.rs:889-909, crates/kcs-cli/src/main.rs:586-610, crates/kcs-cli/src/main.rs:6362-6378 |

#### Summary

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

#### Validation

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

#### Dataflow

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

#### Reachability

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

#### Severity

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

#### Remediation

See the [detailed technical write-up](findings/forgeable-store-consent/forgeable-store-consent.md).

<a id="finding-10"></a>

### [10] Scan-time replacement can authorize an outside-scope file under a benign name

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-cli/src/main.rs:558-580, crates/kcs-pipeline/src/scan.rs:97-149, crates/kcs-cli/src/main.rs:9072-9118, crates/kcs-pipeline/src/prepare.rs:72-103 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md).

<a id="finding-11"></a>

### [11] Opening an existing permissive `.kcs` exposes future private archive bytes

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-core/src/scope.rs:135-158, crates/kcs-core/src/scope.rs:188-200, crates/kcs-core/src/scope.rs:1650-1660, crates/kcs-core/src/scope.rs:254-303 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md).

<a id="finding-12"></a>

### [12] Embedding reconciliation revives AuthError work during batch retry

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-cli/src/main.rs:5639-5666, crates/kcs-cli/src/main.rs:5934-5967, crates/kcs-cli/src/main.rs:5992-6022, crates/kcs-cli/src/main.rs:7997-8043 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md).

<a id="finding-13"></a>

### [13] Accepted embedding adapter targets are discarded before fixed Gemini execution

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-adapter/src/tool_lock.rs:106-231, crates/kcs-adapter/src/tool_lock.rs:376-428, crates/kcs-adapter/src/catalog.rs:313-401, crates/kcs-adapter/src/gemini_embedding.rs:48-149 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md).

<a id="finding-14"></a>

### [14] OCR bounding-box arithmetic can overflow

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/mistral_ocr.rs:434-463, crates/kcs-adapter/src/mistral_ocr.rs:398-422 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md).

<a id="finding-15"></a>

### [15] lexical PDF page markers amplify derived work without a cardinality bound

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/deterministic.rs:415-437, crates/kcs-pipeline/src/prepare.rs:315-349, crates/kcs-pipeline/src/prepare.rs:102-170, crates/kcs-cli/src/main.rs:9047-9061 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md).

<a id="finding-16"></a>

### [16] Gemini embedding responses lack body and read-time bounds before semantic checks

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/gemini_embedding.rs:120-149, crates/kcs-adapter/src/gemini_embedding.rs:153-203, crates/kcs-cli/src/main.rs:7179-7204, crates/kcs-cli/src/main.rs:7420-7423 |

#### Summary

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

#### Validation

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

#### Dataflow

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

#### Reachability

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

#### Severity

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

#### Remediation

See the [detailed technical write-up](findings/gemini-response-bounds/gemini-response-bounds.md).

<a id="finding-17"></a>

### [17] Mistral OCR reopens the path after the final hash check and sends unbound bytes

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:6050-6066, crates/kcs-cli/src/main.rs:6533-6614, crates/kcs-cli/src/main.rs:6615-6691, crates/kcs-adapter/src/catalog.rs:82-101 |

#### Summary

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

#### Validation

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

#### Dataflow

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

#### Reachability

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

#### Severity

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

#### Remediation

See the [detailed technical write-up](findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md).

<a id="finding-18"></a>

### [18] same-batch duplicate embedding identities split authoritative and KNN vectors

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-index/src/embedding_store.rs:10-27, crates/kcs-cli/src/main.rs:7675-7708, crates/kcs-cli/src/main.rs:7726-7769, crates/kcs-index/src/embedding_store.rs:86-145 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md).

<a id="finding-19"></a>

### [19] Gemini vectors lack numeric-domain and positive-norm validation

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-adapter/src/gemini_embedding.rs:153-203, crates/kcs-cli/src/main.rs:7727-7768, crates/kcs-index/src/embedding_store.rs:91-146 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md).

<a id="finding-20"></a>

### [20] Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-core/src/dag.rs:40-79, crates/kcs-core/src/scope.rs:742-755, crates/kcs-pipeline/src/markdownize.rs:311-329, crates/kcs-cli/src/main.rs:5453-5543 |

#### Summary

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

#### Validation

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

#### Dataflow

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

#### Reachability

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

#### Severity

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

#### Remediation

See the [detailed technical write-up](findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md).

<a id="finding-21"></a>

### [21] normalized manifests and unit objects are not rebound to the requested provenance tuple

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:3355-3390, crates/kcs-index/src/chunking.rs:167-185, crates/kcs-cli/src/main.rs:3045-3090, crates/kcs-cli/src/main.rs:2107-2120 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md).

<a id="finding-22"></a>

### [22] Duplicate OCR page indices bind one provider page to multiple evidence units

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-adapter/src/mistral_ocr.rs:356-395, crates/kcs-adapter/src/mistral_ocr.rs:229-276, crates/kcs-pipeline/src/markdownize.rs:476-511, crates/kcs-cli/src/main.rs:6674-6696 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md).

<a id="finding-23"></a>

### [23] Persisted OCR tasks bypass current ignore authorization

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Authorization or policy bypass |
| CWE | CWE-863 Incorrect Authorization |
| Affected lines | crates/kcs-pipeline/src/scan.rs:56-87, crates/kcs-cli/src/main.rs:10015-10039, crates/kcs-pipeline/src/task.rs:41-75, crates/kcs-cli/src/main.rs:6050-6067 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md).

<a id="finding-24"></a>

### [24] incremental unit mapping allocates a quadratic LCS matrix

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-pipeline/src/prepare.rs:208-253, crates/kcs-pipeline/src/prepare.rs:387-416, crates/kcs-cli/src/main.rs:9219-9235 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md).

<a id="finding-25"></a>

### [25] Mistral model resolution lacks response-body and read-time bounds

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/catalog.rs:150-157, crates/kcs-adapter/src/catalog.rs:134-146, crates/kcs-adapter/src/mistral_ocr.rs:83-110, crates/kcs-core/src/scope.rs:1581-1590 |

#### Summary

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

#### Validation

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

#### Dataflow

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

#### Reachability

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

#### Severity

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

#### Remediation

See the [detailed technical write-up](findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md).

<a id="finding-26"></a>

### [26] Mistral OCR responses lack read, body, cardinality, and persistence bounds

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/mistral_ocr.rs:112-138, crates/kcs-adapter/src/mistral_ocr.rs:356-422, crates/kcs-adapter/src/mistral_ocr.rs:229-235, crates/kcs-cli/src/main.rs:6694-6696 |

#### Summary

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

#### Validation

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

#### Dataflow

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

#### Reachability

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

#### Severity

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

#### Remediation

See the [detailed technical write-up](findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md).

<a id="finding-27"></a>

### [27] Accepted markdown adapter targets are discarded before fixed Mistral execution

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-adapter/src/tool_lock.rs:106-231, crates/kcs-adapter/src/tool_lock.rs:376-428, crates/kcs-adapter/src/catalog.rs:82-156, crates/kcs-adapter/src/mistral_ocr.rs:47-138 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md).

<a id="finding-28"></a>

### [28] Deterministic PDF handling reparses the whole file once per page

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-adapter/src/deterministic.rs:415-437, crates/kcs-pipeline/src/prepare.rs:102-170, crates/kcs-adapter/src/deterministic.rs:151-156, crates/kcs-cli/src/main.rs:9047-9118 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md).

<a id="finding-29"></a>

### [29] byte-oriented question-mark globs bypass Unicode names

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-pipeline/src/scan.rs:341-380, crates/kcs-pipeline/src/scan.rs:383-415, crates/kcs-pipeline/src/scan.rs:97-159, crates/kcs-cli/src/main.rs:9044-9118 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md).

<a id="finding-30"></a>

### [30] Persisted manifest unit_ref can escape its normalized-instance directory

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-pipeline/src/markdownize.rs:65-84, crates/kcs-cli/src/main.rs:3355-3383, crates/kcs-cli/src/main.rs:3030-3127, crates/kcs-cli/src/main.rs:9685-9713 |

#### Summary

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

#### Validation

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

#### Dataflow

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

#### Reachability

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

#### Severity

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

#### Remediation

See the [detailed technical write-up](findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md).

<a id="finding-31"></a>

### [31] status and snapshot read unbounded direct-child files before any cap

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:435-442, crates/kcs-core/src/scope.rs:261-309, crates/kcs-core/src/scope.rs:373-386, crates/kcs-cli/src/main.rs:4425-4444 |

#### Summary

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

#### Validation

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

#### Dataflow

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

#### Reachability

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

#### Severity

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

#### Remediation

See the [detailed technical write-up](findings/unbounded-direct-child-read/unbounded-direct-child-read.md).

<a id="finding-32"></a>

### [32] Unrecognized binary gaps disappear from durable completeness and path telemetry

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-cli/src/main.rs:656-671, crates/kcs-cli/src/main.rs:435-450, crates/kcs-cli/src/main.rs:2417-2506, crates/kcs-cli/src/main.rs:9120-9169 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md).

<a id="finding-33"></a>

### [33] Persisted task output_ref can escape the scope

| Field | Value |
| --- | --- |
| Severity | medium |
| Confidence | high |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-pipeline/src/task.rs:129-184, crates/kcs-cli/src/main.rs:9685-9713, crates/kcs-cli/src/main.rs:9863-9885, crates/kcs-cli/src/main.rs:6977-6995 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md).

<a id="finding-34"></a>

### [34] Prepare-stage reopen can poison prepared CAS identity

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-cli/src/main.rs:9077-9118, crates/kcs-pipeline/src/prepare.rs:72-103, crates/kcs-cli/src/main.rs:9505-9541 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md).

<a id="finding-35"></a>

### [35] CAS reads allocate attacker-sized objects before verification

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-core/src/cas.rs:78-100, crates/kcs-core/src/scope.rs:623-637, crates/kcs-core/src/scope.rs:742-755, crates/kcs-cli/src/main.rs:513-530 |

#### Summary

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

#### Validation

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

#### Dataflow

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

#### Reachability

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

#### Severity

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

#### Remediation

See the [detailed technical write-up](findings/cas-read-before-verification/cas-read-before-verification.md).

<a id="finding-36"></a>

### [36] Batch recovery bypasses repository tool-lock validation

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Authorization or policy bypass |
| CWE | CWE-863 Incorrect Authorization |
| Affected lines | crates/kcs-core/src/scope.rs:188-206, crates/kcs-cli/src/main.rs:5586-5667, crates/kcs-cli/src/main.rs:5934-5968, crates/kcs-cli/src/main.rs:10942-10949 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md).

<a id="finding-37"></a>

### [37] closing snapshot can ingest a newly introduced Tier-A secret

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Sensitive data exposure |
| CWE | CWE-200 Exposure of Sensitive Information |
| Affected lines | crates/kcs-cli/src/main.rs:456-472, crates/kcs-cli/src/main.rs:575-580, crates/kcs-core/src/scope.rs:254-299 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md).

<a id="finding-38"></a>

### [38] Content-twin reuse leaves completed budget-paused tasks falsely pending

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-index/src/embedding_store.rs:149-184, crates/kcs-cli/src/main.rs:3008-3027, crates/kcs-cli/src/main.rs:7911-7917, crates/kcs-cli/src/main.rs:8088-8132 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md).

<a id="finding-39"></a>

### [39] CAS write accepts a pre-existing corrupt destination as success

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-core/src/cas.rs:155-163, crates/kcs-core/src/cas.rs:78-100, crates/kcs-core/src/scope.rs:413-520 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md).

<a id="finding-40"></a>

### [40] closing snapshot can attach normalization metadata to different bytes

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Insufficient data integrity validation |
| CWE | CWE-345 Insufficient Verification of Data Authenticity |
| Affected lines | crates/kcs-cli/src/main.rs:9077-9103, crates/kcs-cli/src/main.rs:9390-9426, crates/kcs-core/src/scope.rs:254-299, crates/kcs-cli/src/main.rs:3045-3090 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md).

<a id="finding-41"></a>

### [41] Deterministic normalization persists a later path read under the earlier raw hash

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-cli/src/main.rs:9072-9118, crates/kcs-pipeline/src/prepare.rs:72-103, crates/kcs-cli/src/main.rs:9282-9304, crates/kcs-adapter/src/deterministic.rs:113-118 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md).

<a id="finding-42"></a>

### [42] Snapshot's regular-file check can be raced into archiving an outside-scope symlink target

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Path and scope containment bypass |
| CWE | CWE-22 Improper Limitation of a Pathname to a Restricted Directory |
| Affected lines | crates/kcs-cli/src/main.rs:452-472, crates/kcs-core/src/scope.rs:261-290, crates/kcs-core/src/scope.rs:290-299, crates/kcs-core/src/cas.rs:60-75 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md).

<a id="finding-43"></a>

### [43] Raw-hash working-tree resolution reads every direct child without bounds

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:2796-2825, crates/kcs-cli/src/main.rs:4993-5007, crates/kcs-cli/src/main.rs:5165-5188 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md).

<a id="finding-44"></a>

### [44] Deterministic PDF normalization repeatedly reopens an unbound pathname

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-cli/src/main.rs:9077-9109, crates/kcs-adapter/src/deterministic.rs:225-249, crates/kcs-cli/src/main.rs:9364-9388 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md).

<a id="finding-45"></a>

### [45] Oversized task JSONL records allocate before validation

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Uncontrolled resource consumption |
| CWE | CWE-400 Uncontrolled Resource Consumption |
| Affected lines | crates/kcs-pipeline/src/task.rs:129-150, crates/kcs-pipeline/src/task.rs:151-184, crates/kcs-pipeline/src/task.rs:140-186, crates/kcs-cli/src/main.rs:435-450 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md).

<a id="finding-46"></a>

### [46] secret-hold cycles erase terminal embedding failure state

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper output encoding |
| CWE | CWE-116 Improper Encoding or Escaping of Output |
| Affected lines | crates/kcs-cli/src/main.rs:8221-8231, crates/kcs-cli/src/main.rs:8295-8325, crates/kcs-cli/src/main.rs:8360-8368, crates/kcs-pipeline/src/task.rs:320-378 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md).

<a id="finding-47"></a>

### [47] Deferred OCR tasks read replacement files before enforcing the cap

| Field | Value |
| --- | --- |
| Severity | low |
| Confidence | medium |
| Confidence rationale | The finding is backed by saved validation, attack-path analysis, candidate ledger evidence, and a hash-bound detailed write-up. |
| Category | Improper input validation |
| CWE | CWE-20 Improper Input Validation |
| Affected lines | crates/kcs-cli/src/main.rs:5974-6081, crates/kcs-cli/src/main.rs:6533-6551, crates/kcs-cli/src/main.rs:4425-4445 |

#### Summary

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

#### Validation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

#### Dataflow

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

#### Reachability

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

#### Severity

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

#### Remediation

See the [detailed technical write-up](findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md).

## Structural Hardening

The scan also produced derived, unsealed design guidance based on the complete finding collection. These proposals describe options and tradeoffs; they do not indicate that any finding has been remediated.

[Open the structural hardening portfolio](hardening/hardening.md)

## Reviewed Surfaces

| Surface | Risk Area | Outcome | Notes |
| --- | --- | --- | --- |
| Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-069; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-069/candidate_ledger.jsonl |
| Gemini vectors lack numeric-domain and positive-norm validation | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-003; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-003/candidate_ledger.jsonl |
| OCR bounding-box arithmetic can overflow | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-004; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-004/candidate_ledger.jsonl |
| byte-oriented question-mark globs bypass Unicode names | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-005; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-005/candidate_ledger.jsonl |
| lexical PDF page markers amplify derived work without a cardinality bound | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-006; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-006/candidate_ledger.jsonl |
| incremental unit mapping allocates a quadratic LCS matrix | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-007; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-007/candidate_ledger.jsonl |
| A symlinked `.kcs` binds one working root to another scope's live store | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-008; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-008/candidate_ledger.jsonl |
| a new secret content twin is vector-linked before its hold exists | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-011; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-011/candidate_ledger.jsonl |
| Embedding reconciliation revives AuthError work during batch retry | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-013; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-013/candidate_ledger.jsonl |
| Unrecognized binary gaps disappear from durable completeness and path telemetry | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-014; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-014/candidate_ledger.jsonl |
| recursive star matching has exponential backtracking | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-017; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-017/candidate_ledger.jsonl |
| status and snapshot read unbounded direct-child files before any cap | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-019; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-019/candidate_ledger.jsonl |
| Mistral OCR responses lack read, body, cardinality, and persistence bounds | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-020; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-020/candidate_ledger.jsonl |
| Mistral model resolution lacks response-body and read-time bounds | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-022; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-022/candidate_ledger.jsonl |
| Gemini embedding responses lack body and read-time bounds before semantic checks | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-023; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-023/candidate_ledger.jsonl |
| Opening an existing permissive `.kcs` exposes future private archive bytes | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-024; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-024/candidate_ledger.jsonl |
| Store-local consent records are forgeable or replayable across preseeded or copied scopes | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-025; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-025/candidate_ledger.jsonl |
| Scan-time replacement can authorize an outside-scope file under a benign name | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-027; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-027/candidate_ledger.jsonl |
| Mistral OCR reopens the path after the final hash check and sends unbound bytes | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-028; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-028/candidate_ledger.jsonl |
| scan hashing allocates the full file before the input-size gate | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-032; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-032/candidate_ledger.jsonl |
| Deterministic PDF handling reparses the whole file once per page | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-034; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-034/candidate_ledger.jsonl |
| Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-036; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-036/candidate_ledger.jsonl |
| Accepted markdown adapter targets are discarded before fixed Mistral execution | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-038; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-038/candidate_ledger.jsonl |
| Accepted embedding adapter targets are discarded before fixed Gemini execution | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-039; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-039/candidate_ledger.jsonl |
| Gemini API keys are retained across cross-origin redirects | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-040; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-040/candidate_ledger.jsonl |
| Persisted task output_ref can escape the scope | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-047; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-047/candidate_ledger.jsonl |
| unbound reservation stamps can forge budget-reclaim credits | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-048; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-048/candidate_ledger.jsonl |
| Persisted manifest unit_ref can escape its normalized-instance directory | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-049; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-049/candidate_ledger.jsonl |
| Duplicate OCR page indices bind one provider page to multiple evidence units | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-051; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-051/candidate_ledger.jsonl |
| Human-readable CLI output emits untrusted terminal control sequences | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-059; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-059/candidate_ledger.jsonl |
| normalized manifests and unit objects are not rebound to the requested provenance tuple | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-061; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-061/candidate_ledger.jsonl |
| Persisted OCR tasks bypass current ignore authorization | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-067; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-067/candidate_ledger.jsonl |
| same-batch duplicate embedding identities split authoritative and KNN vectors | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-068; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-068/candidate_ledger.jsonl |
| secret-hold cycles erase terminal embedding failure state | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-001; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-001/candidate_ledger.jsonl |
| Content-twin reuse leaves completed budget-paused tasks falsely pending | Make durable workflow state transitions verifiable and replay-safe | Reported | Reported as KCS-R23-CAND-012; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-012/candidate_ledger.jsonl |
| Snapshot's regular-file check can be raced into archiving an outside-scope symlink target | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-018; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-018/candidate_ledger.jsonl |
| Deterministic normalization persists a later path read under the earlier raw hash | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-029; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-029/candidate_ledger.jsonl |
| Deterministic PDF normalization repeatedly reopens an unbound pathname | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-030; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-030/candidate_ledger.jsonl |
| Prepare-stage reopen can poison prepared CAS identity | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-031; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-031/candidate_ledger.jsonl |
| Deferred OCR tasks read replacement files before enforcing the cap | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-033; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-033/candidate_ledger.jsonl |
| closing snapshot can ingest a newly introduced Tier-A secret | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-041; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-041/candidate_ledger.jsonl |
| closing snapshot can attach normalization metadata to different bytes | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-042; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-042/candidate_ledger.jsonl |
| CAS write accepts a pre-existing corrupt destination as success | Bind content identity to final scope and provenance | Reported | Reported as KCS-R23-CAND-043; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-043/candidate_ledger.jsonl |
| CAS reads allocate attacker-sized objects before verification | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-046; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-046/candidate_ledger.jsonl |
| Oversized task JSONL records allocate before validation | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-050; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-050/candidate_ledger.jsonl |
| Raw-hash working-tree resolution reads every direct child without bounds | Centralize bounds before untrusted work is materialized | Reported | Reported as KCS-R23-CAND-057; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-057/candidate_ledger.jsonl |
| Batch recovery bypasses repository tool-lock validation | Run adapters through scoped capabilities and policy-preserving targets | Reported | Reported as KCS-R23-CAND-064; detailed write-up linked from findings.json. Evidence: artifacts/05_findings/KCS-R23-CAND-064/candidate_ledger.jsonl |

## Open Questions And Follow Up

- Which hardening option should be prioritized first for implementation?
  - Follow-up prompt: Use the hardening portfolio to select one option, then ask Codex to turn that option into an implementation plan without changing scope or target revision.
