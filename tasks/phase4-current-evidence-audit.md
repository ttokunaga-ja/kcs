# Phase 4 current evidence audit (`v0.1.0-rc.1`)

Status: **M1–M8 implementation/automated-evidence audit complete; Kio internal Full not planned; Phase 4 manual acceptance not established** (2026-08-29 JST).

本書は、公開 RC 候補に存在する Phase 4 milestone 1–8 の実装・自動検証証拠と、未成立の手動受入を
対応付ける非規範の監査記録である。仕様の正本は `docs/`、Full gate の外部規範契約は
[manual-full-cold-gates.md](manual-full-cold-gates.md) のままであり、本書はそれらを変更・廃止しない。
この参照は本監査にFull gateを呼び出す予定または権限を与えない。tracked 文書を探索した時点で、現行 RC
に bind した同趣旨の milestone 1–8 evidence matrix は存在しなかったため、本書を新設した。

本書の `implemented` は code/CLI が存在すること、`automated-verified` は固定候補で applicable な
fixture/contract tests が成功したこと、`manual-unverified` は候補または公開 distribution を使う
手動証拠が無いことを表す。`not planned` はoperator policyによりこのRC作業で実行しないことを表し、
`blocked`、`passed`、`accepted`ではない。`blocked` はhistorical audit classificationとして、必要な
実装済みexecution boundary、local input、offline cache、対応 host、容量等の不足で実行を開始または継続
できない場合だけに使う。未実施を `blocked` や `accepted` に読み替えない。

---

## 1. Immutable candidate binding

| authority | fixed value | audit observation |
| --- | --- | --- |
| product candidate commit | `b95efd86d1ee738378edb7171509ae7ca81e8661` | local object、live `origin/main`、tag peeled target が一致 |
| candidate Git tree | `a4183c874799ab55d2471b726f9b5dc4dd3eb8d8` | `git rev-parse b95efd86^{tree}` |
| candidate `Cargo.lock` SHA-256 | `74059079ef8e69ce3e35c31214c0587616bd4eb6c3199553d5339389fc9ece21` | candidate object bytes から導出 |
| annotated tag object | `8895d0e8eece48b3a99e4d67f2c8d3098edee531` (`type=tag`) | `v0.1.0-rc.1`、object field は candidate commit |
| tag peeled target | `b95efd86d1ee738378edb7171509ae7ca81e8661` | live `refs/tags/v0.1.0-rc.1^{}` と一致 |
| GitHub Release | [`v0.1.0-rc.1`](https://github.com/ttokunaga-ja/kio/releases/tag/v0.1.0-rc.1) | `draft=false`、`prerelease=true`、3 target × archive/sidecar の6 assets |
| tag-push CI | [run `33186969773`](https://github.com/ttokunaga-ja/kio/actions/runs/33186969773) | `event=push`、`head_branch=v0.1.0-rc.1`、`head_sha=b95efd86…`、attempt 1、success |
| post-release docs commit | `cd14e4c312ef315326e0c8ed337f9e48f68f3c4c` | parent は candidate。差分は `README.md` と `docs/10-operations.md` だけ |
| product-code equivalence | `crates/` tree `e8f7c6f300adb67ba7af4d0ac063898d0b24fac4` | candidate と docs commit で同一。docs commit は product code/workflow を変更しない |

checkpoint 1で照合したmacOS distribution evidenceの固定値は以下である。binary は sidecar の
`binary_sha256` と一致し、archive/sidecarとは別に再計算済みである。

| object | bytes | SHA-256 |
| --- | ---: | --- |
| `kio-0.1.0-rc.1-aarch64-apple-darwin.tar.gz` | 8,083,094 | `590c41518b83eac8b3ba5dba4006ca5afdffd014ebc521817e804f3e77ddfd8c` |
| `kio-0.1.0-rc.1-aarch64-apple-darwin.checksums.json` | 509 | `0ea4bbf4e26ac587653c59408dda65a704c6d075582a0f0eef2730eae20ec45b` |
| extracted `bin/kio` | 20,603,712 | `4bdc913150ecf839f05bac1237360ea2bc1cd48757009e077ead3689c806d02c` |

監査時 host は macOS 26.6.2 (25G83) / arm64、Rust/Cargo 1.98.0 である。この観測はcheckpoint 1の
consumer smoke環境をbindするが、Linux-only Full gateの実行hostには適格でなく、Full gate evidenceでもない。

---

## 2. Public RC automated evidence and boundary

Tag-push CI run `33186969773` では次の5 jobsが成功した。

- `rust`: workflow action ref、format、workspace/all-target clippy、workspace/all-target tests
- `macos-security-r23`: native macOS workspace/all-target tests
- `windows-security-r23`: native Windows workspace/all-target tests
- `persona-w0-integration`: Tiny create-only persona lifecycle/lease/attestation
- `synthetic-history-eval`: release/all-features build、Tiny current/history prepare/attest、synthetic gates

Milestone matrix の `automated-verified` は、候補treeに存在する下記の test と、上記の
`cargo test --workspace --all-targets --locked` 成功を組み合わせた判定である。platform cfg により
applicable な test 集合は異なり、GitHub run に個別 test receipt は無い。Actions artifacts APIも
この run について0件を返すため、job command の成功を個別手動証拠へ昇格させない。

`synthetic-history-eval` は `tiny` の current/historyを `1` warmup / `1` sampleで実行する contract
smokeである。Full 20-scope / 120,000-current-chunk / 5-warmup / 100-sample acceptance、公開macOS
binary replay、real dogfood、actual D1を証明しない。

---

## 3. Milestone 1–8 evidence matrix

| M | normative contract / current implementation | automated evidence at candidate | manual evidence / gap | judgment |
| --- | --- | --- | --- | --- |
| 1 | Retention planner: [06 §6.1](../docs/06-cli-spec.md) / [05 §2.2–2.4](../docs/05-runtime.md); `kio gc --dry-run`; `gc.rs::run` → `GcSweepSession::plan_at` | deterministic/read-only CLI、strict syntax、capability binding、tier boundary、protected tips、raw/chunk/commit exclusionをfixtureで検証。tag-push CI success | public RC binaryまたはlive candidate scopeでのmanual dry-run receiptなし。Full scale gateはこのCLIを実行しない | `implemented`; `automated-verified`; `manual-unverified` |
| 2 | On-demand tree-only shallow sweep: [06 §6.1](../docs/06-cli-spec.md) / [05 §2.2–2.3](../docs/05-runtime.md); `kio gc [--yes]`; `GcSweepSession` | receipt-before-removal、bounded convergence/checkpoint、fault/crash/race recovery、index attestation、writer/search barrier、shared-tree receiptsをfixtureで検証。tag-push CI success | immutable RCに対するisolated manual sweepなし。既存/user scopeを対象にしてはならない | `implemented`; `automated-verified`; `manual-unverified` |
| 3 | Opt-in `gc.mode="after_index"`: [06 §6.1](../docs/06-cli-spec.md) / [05 §2.3–2.5](../docs/05-runtime.md); index/manual snapshot publication後の `attach_after_success` → `run_after_success` | no-candidate、real stale tree、timeout/crash recovery、failed/preview/partial non-trigger、protected shared treeをfixtureで検証。tag-push CI success | public RC/manual isolated after-index runなし。Full measurementとは別のtrigger contract | `implemented`; `automated-verified`; `manual-unverified` |
| 4 | Scheduled auto snapshot: [05 §8.2](../docs/05-runtime.md); `kio snapshot auto`; `run_snapshot_auto` / `observe_scheduled_auto` | first-run、interval/threshold、add/edit/delete/rename、ignore/Tier-A、checkpoint crash、writer/race/scope replacementをfixtureで検証。tag-push CI success | OS schedulerからのcurrent RC invocationとpublic distribution replayなし。Kioはschedulerをinstallしない | `implemented`; `automated-verified`; `manual-unverified` |
| 5 | Rust-only `on_idle`: [05 §2.3](../docs/05-runtime.md); `ScheduledIdleObservation` → `run_on_idle_after_snapshot_bound` | enable/index/idle gate、real stale sweep、timeout resume、manual/index non-trigger、parent-child isolation、state/clock/platform fail-closedをfixtureで検証。tag-push CI success | OS scheduler integrationとcurrent RC manual idle interval evidenceなし。Full measurementとは別 | `implemented`; `automated-verified`; `manual-unverified` |
| 6 | Batch Evidence verify: [08 §4.3](../docs/08-evidence-pointer-spec.md); `kio evidence verify --batch`; `run_evidence_batch` | exactly-one、JSONL/size/scope limits、single-link regular file、deterministic single parity、multiscope order、strict/status exit parityをfixtureで検証。tag-push CI success | public RC batch file replayとcandidate-bound manual receiptなし | `implemented`; `automated-verified`; `manual-unverified` |
| 7 | Exact-only retarget: [08 §5](../docs/08-evidence-pointer-spec.md); `kio evidence retarget <pointer> --at <commit>`; `run_evidence_retarget_bound` | exact deterministic/read-only、direct commit not ref、not-found/ambiguous、shallow retry、purge/read-only、linked/nonregular victim safetyをfixtureで検証。tag-push CI success | public RC distribution-bound retarget replayなし。Full measurementはretargetを実行しない | `implemented`; `automated-verified`; `manual-unverified` |
| 8 | Read-only unreachable inventory: [06 §6.2](../docs/06-cli-spec.md) / [05 §2.7](../docs/05-runtime.md); `kio gc --dry-run --prune-unreachable`; `UnreachableObjectInventory` | deterministic/read-only、syntax、candidate/protected closure、shallow receipt、malformed/missing/race/link/limit fail-closedをfixtureで検証。tag-push CI success | public RC inventory replayなし。physical prune、non-tree sweep、CoW GCは意図的に範囲外 | `implemented`; `automated-verified`; `manual-unverified` |

current implementation のcompact anchorsは次のとおり。

1. M1–M2: `crates/kio-cli/src/main.rs:317-329` のstrict GC args、
   `crates/kio-cli/src/gc.rs:455-490` のCLI dispatch、`crates/kio-core/src/gc.rs:701-1917`
   の `GcSweepSession`、同 `:3290-3339` のplanner。
2. M3: `crates/kio-cli/src/main.rs:2534-2555` のsuccessful publication attach、
   `crates/kio-cli/src/gc.rs:196-251` の `attach_after_success`、同 `:253-327` の
   `run_after_success`。
3. M4: `crates/kio-cli/src/main.rs:265-271` の `SnapshotAction::Auto`、同 `:1433-1804` の
   `run_snapshot_auto`、同 `:1876` 以降の `observe_scheduled_auto`。
4. M5: `crates/kio-cli/src/main.rs:1345-1375` の `ScheduledIdleObservation` と、
   `crates/kio-cli/src/gc.rs:333-380` の `run_on_idle_after_snapshot_bound`。
5. M6: `crates/kio-cli/src/main.rs:526-570` のexactly-one CLI、
   `crates/kio-cli/src/verify_objects.rs:137-163,653-760` のbatch implementation。
6. M7: `crates/kio-cli/src/verify_objects.rs:262-555`、特に `:291-555` の
   `run_evidence_retarget_bound`。
7. M8: `crates/kio-cli/src/gc.rs:455-464` の独立dispatch、
   `crates/kio-core/src/gc/unreachable_inventory.rs:360-415` のbind/inventory entry。

代表的な automated anchors（全 test 名の転記ではない）は次のとおり。

1. M1: `phase4_gc_dry_run.rs:64-184` の
   `gc_dry_run_is_deterministic_and_does_not_change_the_store`、および
   `gc_planner.rs:122-1234` の binding/retention/protected/deterministic vectors。
2. M2: `phase4_gc_sweep.rs:250-1255` の
   `real_candidate_sweep_receipts_before_tree_removal_and_preserves_other_objects`、fault-point
   resumability、active marker barrier、shared-tree、malformed state vectors。
3. M3: `phase4_gc_after_index.rs:80-664` の
   `after_index_sweeps_a_real_stale_tree_after_successful_index`、timeout/crash/non-trigger vectors。
4. M4: `phase4_snapshot_auto.rs:343-1490` の
   `first_run_noop_advances_canonical_state_and_json_and_human_agree`、checkpoint/race/platform vectors。
5. M5: `phase4_gc_on_idle.rs:121-642` の
   `idle_threshold_sweeps_a_real_stale_candidate`、idle reset/resume/isolation/platform vectors。
6. M6: `step4b_p2b_contract.rs:1503-1735` の
   `pb62_batch_success_is_versioned_deterministic_and_single_parity` とclosed batch contract。
7. M7: `step4c_retarget.rs:210-709` の
   `retarget_is_exact_deterministic_and_preserves_scope_bytes` とexact/fail-closed vectors。
8. M8: `phase4_gc_unreachable_inventory.rs:42-145` の
   `inventory_is_deterministic_read_only_and_prune_requires_dry_run`、および
   `unreachable_inventory_vectors.rs:278-853` のclosure/fail-closed vectors。

現時点で観測済み失敗による `blocked` milestone は無い。M1–M8は `implemented` /
`automated-verified` / `manual-unverified` のままであり、8件ともmanual evidenceが無いため、Phase 4全体
または各milestoneをmanual-acceptedとは判定しない。

---

## 4. Historical evidence is non-substituting

[phase3-acceptance-record.md](phase3-acceptance-record.md) は product HEAD
`4fac253fd1fd5dea8308c4bc2d0dafdd8c56fc5c` に対するPhase 3のhistorical evidenceである。そこには
過去のFull 120,000-chunk / 5-warmup / 100-sample reportもあるが、現RC candidate、現行
`kio-eval`、公開binaryのdigestにbindしていない。同記録自身がPhase 4/5実装を含まないと明記するため、
現RCのPhase 4 automated/manual evidence、Full acceptance、distribution replayの代用にしない。

[persona-pc-eval-contract.md](persona-pc-eval-contract.md) も historical/non-authorizing snapshotであり、
persona profile/materialization単独はKio indexingやFull acceptanceを証明しない。PersonaCorpus repository側の
Full evidenceもKio internal Fullの代替ではなく、Kio FullまたはKio Phase 4 acceptanceを承認・置換しない。

---

## 5. Kio internal Full gate contract (normative reference; not planned for this RC work)

Kio internal Full gate正本は [manual-full-cold-gates.md §3](manual-full-cold-gates.md)、数値・lane契約は
[09-mvp-scope.md §4.3](../docs/09-mvp-scope.md) とする。本節は、このRC作業で何を実行しないと決めたかを
示すhistorical/current normative referenceであり、正本runbookを廃止・変更するものではない。operator policyに
よりKio internal FullはこのRC作業では `not planned` である。

| fixture | scopes / files | required attestation |
| --- | --- | --- |
| `current` (`current-text`) | 20 / 4,000 | current 120,000、historical-only 0、deleted 0、physical 120,000 |
| `history` (`history-overlay`) | 20 / 4,000 | 20 edits + 20 renames + 20 deletes、current 119,400、historical-only 1,200、deleted 600、physical 120,600 |

Formal eligibilityと成功条件は次の全てである。

- Full profile、exactly 5 warmups / 100 samples。
- exactly five lanes: `current-text`、`vector`、`hybrid`、`history`、`deleted`。
- 全laneで requested mode == resolved mode、fallback=false、fallback_reason=null、Recall@10=1.0、
  `pointer_attestations > 0`。
- populations は current-text/vector/hybrid=120,000、history=1,200、deleted=600。
- deleted laneはrestored raw hash一致かつfixture working tree不変。
- `measurement_class="full_manual_p4_gate"`、`full_formal_manual_gate=true`、
  `acceptance_failed=false`、`passed_p95_thresholds=true`。
- current-textのproduct/process p95は5秒未満、history/deletedは7秒未満。vector/hybridに新しい
  thresholdを発明しない。
- prepare/attestation/binary bindingとreportをrequired evidenceとして扱う。

Scale benchmarkはD1を実行せず、D1 fieldsをtyped `not-measured` とする。Full gate自体もM1–M8の
GC/scheduler/batch/retarget/inventory CLIを手動実行しないため、Full passを各milestoneのmanual evidenceへ
転用しない。

### 5.1 Non-execution boundary and distribution distinction

このRC作業ではsource/evaluator Fullとdistribution-bound replayのいずれも `not planned` であり、
`manual-unverified` のままである。checkpoint 1のmacOS consumer smokeはFull acceptanceに昇格しない。
現行evaluatorはmacOSでFull処理のmutation前にfail-closedし、Linuxは公開Mach-O binaryを実行できないため、
両者のevidenceは区別する。PersonaCorpus repository側のFullはKio internal Full、Kio Phase 4 acceptance、
またはKio distribution replayの代用ではない。

---

## 6. Non-execution decision record and read-only preflight

**Decision.** Kio internal Full is `not planned` for this RC work under operator policy. This is a
non-execution decision, not a `blocked`, `passed`, or `accepted` result. It establishes neither
Phase 4 Full acceptance nor M1–M8 manual acceptance. Earlier working drafts contained runnable Full
material; that material was removed before this final audit and is intentionally excluded from the
integrated main history. This current audit contains no runnable Full procedure.

**Read-only Docker preflight.** The existing local image
`kio-rust:1.98.0-ci-local` (ID
`sha256:fff9e2ac8f71ad2ddae9c26c4892da5bab5dbfbfad136b912f53b5bc942fcc0d`) was inspected in an
isolated Linux/aarch64 Debian 12 container using `--rm`、`--pull=never`、`--network none`、
`--read-only`、`--cap-drop ALL`、`--security-opt no-new-privileges:true`、`--user 65534:65534` and
equivalent resource limits. No external-facing interface, assigned address, or route was present;
Rust and Cargo were both 1.98.0; Cargo credential files were absent; and the candidate `Cargo.lock`
SHA-256 matched `74059079ef8e69ce3e35c31214c0587616bd4eb6c3199553d5339389fc9ece21`. The Cargo registry
`index`, `cache`, and `src` directories were absent, and archive/source inputs for all 241
lock-resolved registry dependencies were absent. The toolchain directory chain had mode `0777`,
which does not meet the historical hardening contract. The overlay free-space display is not evidence
of writable evidence-parent capacity. No build, fetch, generation, benchmark, or evidence-root
creation occurred, and `--rm` left no container behind.

**Scope boundary.** Repository integration or publication, additional manual-evidence collection, and
changes to the Kio internal Full policy are outside this audit. PersonaCorpus Full evidence remains
non-substituting.

---

## 7. Conclusion and operations not performed

Kio internal FullはこのRC作業では実行しない。M1–M8は `implemented`、`automated-verified`、
`manual-unverified` のままであり、Phase 4 Full/manual acceptanceは未成立である。本auditでは120k Full gate、
distribution Full replay、real dogfood、D1、paid API、GPU、OCR、physical prune、non-tree CAS reclamation、
CoW GC、M9、push/PR、tag/Release変更、workflow操作、main統合、PersonaCorpus操作を実行していない。
read-only repository/GitHub探索と安価なtargeted validationだけを許容し、current candidate/publication
stateは変更していない。
