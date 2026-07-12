# Hardening Analysis Context

Scan ID: f78f5d0d-2752-47a7-8d8d-3371e09d3377
Target revision: 0e19f3c6489da458e93a982a333c308d92d0a0ae
Scan directory: /private/var/folders/3l/x2mqg_bx7pv8l8lkw2fqrwf80000gn/T/codex-security-scans-Lgn4Tc/kcs/0e19f3c6489da458e93a982a333c308d92d0a0ae_20260710T104946Z_p2re3yqs

## Evidence Registry

| Evidence | Candidate | Severity | Title | Write-up |
| --- | --- | --- | --- | --- |
| `E001` | `KCS-R23-CAND-069` | high | Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files | `../findings/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure/tac-kcs-r23-cand-069-inline-raw-hash-json-disclosure.md` |
| `E002` | `KCS-R23-CAND-003` | medium | Gemini vectors lack numeric-domain and positive-norm validation | `../findings/tac-kcs-r23-cand-003-gemini-invalid-vector/tac-kcs-r23-cand-003-gemini-invalid-vector.md` |
| `E003` | `KCS-R23-CAND-004` | medium | OCR bounding-box arithmetic can overflow | `../findings/tac-kcs-r23-cand-004-ocr-bounding-box-overflow/tac-kcs-r23-cand-004-ocr-bounding-box-overflow.md` |
| `E004` | `KCS-R23-CAND-005` | medium | byte-oriented question-mark globs bypass Unicode names | `../findings/tac-kcs-r23-cand-005-unicode-question-glob-bypass/tac-kcs-r23-cand-005-unicode-question-glob-bypass.md` |
| `E005` | `KCS-R23-CAND-006` | medium | lexical PDF page markers amplify derived work without a cardinality bound | `../findings/tac-kcs-r23-cand-006-pdf-page-marker-amplification/tac-kcs-r23-cand-006-pdf-page-marker-amplification.md` |
| `E006` | `KCS-R23-CAND-007` | medium | incremental unit mapping allocates a quadratic LCS matrix | `../findings/tac-kcs-r23-cand-007-quadratic-unit-lcs/tac-kcs-r23-cand-007-quadratic-unit-lcs.md` |
| `E007` | `KCS-R23-CAND-008` | medium | A symlinked `.kcs` binds one working root to another scope's live store | `../findings/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store/tac-kcs-r23-cand-008-symlinked-kcs-cross-scope-store.md` |
| `E008` | `KCS-R23-CAND-011` | medium | a new secret content twin is vector-linked before its hold exists | `../findings/secret-twin-prehold-vector-link/secret-twin-prehold-vector-link.md` |
| `E009` | `KCS-R23-CAND-013` | medium | Embedding reconciliation revives AuthError work during batch retry | `../findings/tac-kcs-r23-cand-013-auth-error-retry-revival/tac-kcs-r23-cand-013-auth-error-retry-revival.md` |
| `E010` | `KCS-R23-CAND-014` | medium | Unrecognized binary gaps disappear from durable completeness and path telemetry | `../findings/tac-kcs-r23-cand-014-unrecognized-binary-visibility/tac-kcs-r23-cand-014-unrecognized-binary-visibility.md` |
| `E011` | `KCS-R23-CAND-017` | medium | recursive star matching has exponential backtracking | `../findings/tac-kcs-r23-cand-017-exponential-glob-backtracking/tac-kcs-r23-cand-017-exponential-glob-backtracking.md` |
| `E012` | `KCS-R23-CAND-019` | medium | status and snapshot read unbounded direct-child files before any cap | `../findings/unbounded-direct-child-read/unbounded-direct-child-read.md` |
| `E013` | `KCS-R23-CAND-020` | medium | Mistral OCR responses lack read, body, cardinality, and persistence bounds | `../findings/mistral-ocr-response-bounds/mistral-ocr-response-bounds.md` |
| `E014` | `KCS-R23-CAND-022` | medium | Mistral model resolution lacks response-body and read-time bounds | `../findings/mistral-model-resolution-bounds/mistral-model-resolution-bounds.md` |
| `E015` | `KCS-R23-CAND-023` | medium | Gemini embedding responses lack body and read-time bounds before semantic checks | `../findings/gemini-response-bounds/gemini-response-bounds.md` |
| `E016` | `KCS-R23-CAND-024` | medium | Opening an existing permissive `.kcs` exposes future private archive bytes | `../findings/tac-kcs-r23-cand-024-permissive-existing-store/tac-kcs-r23-cand-024-permissive-existing-store.md` |
| `E017` | `KCS-R23-CAND-025` | medium | Store-local consent records are forgeable or replayable across preseeded or copied scopes | `../findings/forgeable-store-consent/forgeable-store-consent.md` |
| `E018` | `KCS-R23-CAND-027` | medium | Scan-time replacement can authorize an outside-scope file under a benign name | `../findings/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope/tac-kcs-r23-cand-027-scan-time-replacement-outside-scope.md` |
| `E019` | `KCS-R23-CAND-028` | medium | Mistral OCR reopens the path after the final hash check and sends unbound bytes | `../findings/ocr-final-hash-reopen/ocr-final-hash-reopen.md` |
| `E020` | `KCS-R23-CAND-032` | medium | scan hashing allocates the full file before the input-size gate | `../findings/tac-kcs-r23-cand-032-scan-hash-precap-allocation/tac-kcs-r23-cand-032-scan-hash-precap-allocation.md` |
| `E021` | `KCS-R23-CAND-034` | medium | Deterministic PDF handling reparses the whole file once per page | `../findings/tac-kcs-r23-cand-034-pdf-reparse-amplification/tac-kcs-r23-cand-034-pdf-reparse-amplification.md` |
| `E022` | `KCS-R23-CAND-036` | medium | Persisted DAG semantics are not revalidated, enabling poisoned fields and path escape | `../findings/unvalidated-persisted-dag/unvalidated-persisted-dag.md` |
| `E023` | `KCS-R23-CAND-038` | medium | Accepted markdown adapter targets are discarded before fixed Mistral execution | `../findings/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution/tac-kcs-r23-cand-038-markdown-target-discarded-mistral-execution.md` |
| `E024` | `KCS-R23-CAND-039` | medium | Accepted embedding adapter targets are discarded before fixed Gemini execution | `../findings/tac-kcs-r23-cand-039-embedding-target-discarded-gemini/tac-kcs-r23-cand-039-embedding-target-discarded-gemini.md` |
| `E025` | `KCS-R23-CAND-040` | medium | Gemini API keys are retained across cross-origin redirects | `../findings/tac-kcs-r23-cand-040-gemini-redirect-key-retention/tac-kcs-r23-cand-040-gemini-redirect-key-retention.md` |
| `E026` | `KCS-R23-CAND-047` | medium | Persisted task output_ref can escape the scope | `../findings/tac-kcs-r23-cand-047-output-ref-cross-scope/tac-kcs-r23-cand-047-output-ref-cross-scope.md` |
| `E027` | `KCS-R23-CAND-048` | medium | unbound reservation stamps can forge budget-reclaim credits | `../findings/tac-kcs-r23-cand-048-forged-reclaim-credit/tac-kcs-r23-cand-048-forged-reclaim-credit.md` |
| `E028` | `KCS-R23-CAND-049` | medium | Persisted manifest unit_ref can escape its normalized-instance directory | `../findings/manifest-unit-ref-traversal/manifest-unit-ref-traversal.md` |
| `E029` | `KCS-R23-CAND-051` | medium | Duplicate OCR page indices bind one provider page to multiple evidence units | `../findings/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding/tac-kcs-r23-cand-051-duplicate-ocr-page-index-misbinding.md` |
| `E030` | `KCS-R23-CAND-059` | medium | Human-readable CLI output emits untrusted terminal control sequences | `../findings/tac-kcs-r23-cand-059-terminal-control-human-output/tac-kcs-r23-cand-059-terminal-control-human-output.md` |
| `E031` | `KCS-R23-CAND-061` | medium | normalized manifests and unit objects are not rebound to the requested provenance tuple | `../findings/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding/tac-kcs-r23-cand-061-normalized-unit-provenance-rebinding.md` |
| `E032` | `KCS-R23-CAND-067` | medium | Persisted OCR tasks bypass current ignore authorization | `../findings/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass/tac-kcs-r23-cand-067-persisted-ocr-ignore-bypass.md` |
| `E033` | `KCS-R23-CAND-068` | medium | same-batch duplicate embedding identities split authoritative and KNN vectors | `../findings/tac-kcs-r23-cand-068-embedding-identity-split/tac-kcs-r23-cand-068-embedding-identity-split.md` |
| `E034` | `KCS-R23-CAND-001` | low | secret-hold cycles erase terminal embedding failure state | `../findings/tac-kcs-r23-cand-001-secret-hold-terminal-failure/tac-kcs-r23-cand-001-secret-hold-terminal-failure.md` |
| `E035` | `KCS-R23-CAND-012` | low | Content-twin reuse leaves completed budget-paused tasks falsely pending | `../findings/tac-kcs-r23-cand-012-budget-paused-content-twin-pending/tac-kcs-r23-cand-012-budget-paused-content-twin-pending.md` |
| `E036` | `KCS-R23-CAND-018` | low | Snapshot's regular-file check can be raced into archiving an outside-scope symlink target | `../findings/tac-kcs-r23-cand-018-snapshot-symlink-race/tac-kcs-r23-cand-018-snapshot-symlink-race.md` |
| `E037` | `KCS-R23-CAND-029` | low | Deterministic normalization persists a later path read under the earlier raw hash | `../findings/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding/tac-kcs-r23-cand-029-normalization-raw-hash-misbinding.md` |
| `E038` | `KCS-R23-CAND-030` | low | Deterministic PDF normalization repeatedly reopens an unbound pathname | `../findings/tac-kcs-r23-cand-030-pdf-repeated-path-reopen/tac-kcs-r23-cand-030-pdf-repeated-path-reopen.md` |
| `E039` | `KCS-R23-CAND-031` | low | Prepare-stage reopen can poison prepared CAS identity | `../findings/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding/tac-kcs-r23-cand-031-prepare-cas-identity-misbinding.md` |
| `E040` | `KCS-R23-CAND-033` | low | Deferred OCR tasks read replacement files before enforcing the cap | `../findings/tac-kcs-r23-cand-033-deferred-ocr-precap-read/tac-kcs-r23-cand-033-deferred-ocr-precap-read.md` |
| `E041` | `KCS-R23-CAND-041` | low | closing snapshot can ingest a newly introduced Tier-A secret | `../findings/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou/tac-kcs-r23-cand-041-closing-snapshot-secret-toctou.md` |
| `E042` | `KCS-R23-CAND-042` | low | closing snapshot can attach normalization metadata to different bytes | `../findings/tac-kcs-r23-cand-042-stale-normalize-ref/tac-kcs-r23-cand-042-stale-normalize-ref.md` |
| `E043` | `KCS-R23-CAND-043` | low | CAS write accepts a pre-existing corrupt destination as success | `../findings/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot/tac-kcs-r23-cand-043-cas-preexisting-corrupt-slot.md` |
| `E044` | `KCS-R23-CAND-046` | low | CAS reads allocate attacker-sized objects before verification | `../findings/cas-read-before-verification/cas-read-before-verification.md` |
| `E045` | `KCS-R23-CAND-050` | low | Oversized task JSONL records allocate before validation | `../findings/tac-kcs-r23-cand-050-task-jsonl-unbounded-records/tac-kcs-r23-cand-050-task-jsonl-unbounded-records.md` |
| `E046` | `KCS-R23-CAND-057` | low | Raw-hash working-tree resolution reads every direct child without bounds | `../findings/tac-kcs-r23-cand-057-raw-hash-unbounded-scan/tac-kcs-r23-cand-057-raw-hash-unbounded-scan.md` |
| `E047` | `KCS-R23-CAND-064` | low | Batch recovery bypasses repository tool-lock validation | `../findings/tac-kcs-r23-cand-064-batch-tool-lock-bypass/tac-kcs-r23-cand-064-batch-tool-lock-bypass.md` |
