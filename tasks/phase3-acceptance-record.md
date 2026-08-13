# Phase 3 正式受け入れ記録

Status: **完了 (2026-08-14 JST)**

この記録は [docs/09-mvp-scope.md §4](../docs/09-mvp-scope.md) の Phase 3 Done 条件を、
凍結済み query/threshold/fixture と fresh Rust 計測で確認したものです。製品コードの計測 HEAD は
`4fac253` (`Record baseline online query provenance`) です。この文書の追加は計測後の記録だけで、
query、閾値、fixture、製品コードを変更していません。

## 結論

Phase 3 を正式に受け入れます。

- dogfood 428 scope / 5,013 task は全件 `done` です。
- fresh synthetic Rust 評価は M3-1 18/18、M3-2 16/16、M3-3 16/16 で、
  各 Recall@10 は 1.0 です。M3-2 の pointer CAS と M3-3 の restore も pass です。
- 実dogfood文書を使う手動確認は M3-1/2/3 をすべて完走しました。
- attested Q_hard 8 問と同一実行の frozen synthetic M3-1 18 問は 26/26 hit です。
- full Scale 120,000 chunk、5 warmup、100 sample は M3-1/2/3 の p95 閾値をすべて満たします。
- fresh fixture-B baseline は 24 問を完走し、Kio Recall@10 22/24 = 0.9167、
  Spotlight 0/24、rga 0/24 です。Kio の差は両方に対して 0.9167 で、
  `Kio >= 0.8` および各 `margin >= 0.3` を満たします。
- baseline report の `status` は `pass`、`blocked_reason` は `null`、全 gate は `true` です。

## Fresh fixture-B baseline

実行日時は `2026-08-13T17:56:37.513Z` (`2026-08-14T02:56:37.513+09:00`) です。
platform は macOS 26.6.1 (build 25G76)、arm64、report 表記は `macos-aarch64` です。

| 項目 | 値 |
|---|---|
| report | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/baseline-report.json` |
| report SHA-256 | `a25d936d3a9cadb003b9d0502281d1ef4d817d6f557f3291f30eec6bf2028ad6` |
| fresh attestation | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/baseline-attestation.json` |
| attestation SHA-256 | `7f69a225d0f2fd73861894dbd59cc87b25ab7eaed7bf694922e196703033ad0d` |
| post-run attestation | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/baseline-attestation-after.json` (同一 SHA-256、byte-identical) |
| frozen golden | `eval/golden-queries-fixture-b.jsonl` |
| golden SHA-256 | `bdad3e02c4b70f721e882d7f24c8b5b442621be7c0c03593afde41b8ebca7d45` |
| indexed fixture | `/Users/ttokunaga-ja/kio-dogfood/phase3-baseline-fixture-v2` |
| indexed fixture SHA-256 | `sha256:bc01b1db135b453a398204459fd0a29ee4574c56373233cc026f3c80ad608178` |
| pristine corpus | `/Users/ttokunaga-ja/kio-dogfood/phase3-baseline-pristine-v2` |
| pristine corpus SHA-256 | `sha256:d033ac0a7760a7d8e4d00f73321fe2ddece954cc88815fd433b509602c3335cc` |
| source equivalence SHA-256 | `sha256:002998bbbc87d99425884c612672dd5196e1d8794c272a963d55e1841c9bd491` |
| Kio binary SHA-256 | `sha256:6b88aaf74fa8c4d24a18608ad672a70173fec84cf95215694acdcfa23f38f4fb` |
| kio-eval binary SHA-256 | `bfd4f13ddb46867bc2d4bb579ff35c45c013eae8a8bf3dec6af9c1948c82dbc6` |
| pre/post binding record | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/binding-checks.json` |
| binding record SHA-256 | `47c76a78410b436a631a14be25e8423d7c599d11a713383c262afe47b4e319a6` |

| Comparator | Hits / 24 | Recall@10 | Kioとの差 | Gate |
|---|---:|---:|---:|---|
| Kio | 22 | 0.9167 | — | `>= 0.8`: pass |
| Spotlight (`mdfind`) | 0 | 0.0000 | 0.9167 | `>= 0.3`: pass |
| ripgrep-all (`rga`) | 0 | 0.0000 | 0.9167 | `>= 0.3`: pass |

正本の測定引数は次のとおりです（credential 値は環境から名前限定で受け渡し、引数には含めません）。

```text
target/release/kio-eval benchmark baseline
  --golden /Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kio/eval/golden-queries-fixture-b.jsonl
  --fixture-root /Users/ttokunaga-ja/kio-dogfood/phase3-baseline-fixture-v2
  --baseline-corpus /Users/ttokunaga-ja/kio-dogfood/phase3-baseline-pristine-v2
  --attestation /Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/baseline-attestation.json
  --bin /Users/ttokunaga-ja/dev/github.com/ttokunaga-ja/kio/target/release/kio
  --mdfind /usr/bin/mdfind
  --comparator-runtime /Library/KioComparatorRuntime/v1
  --online-query
  --out /Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/baseline-final-20260814.8INRhw/baseline-report.json
```

`qb01` から `qb24` までをすべて実行しました。Kio lane は `online_query=true` で、
controlled subprocess に転送した credential は `GEMINI_API_KEY` と `MISTRAL_API_KEY` の
**環境変数名だけ**を report に記録しています。値は command line、report、完了記録に保存していません。
既存の enriched fixture をそのまま使用し、OCR と fixture 再生成は行っていません。

## Comparator runtime binding

| 項目 | 値 |
|---|---|
| canonical runtime root | `/Library/KioComparatorRuntime/v1` |
| mount | `/dev/disk5s1` on `/Library/KioComparatorRuntime/v1`, APFS, read-only |
| mount identity | `fsid_t { __fsid_val: [16777239, 26] }` |
| runtime closure SHA-256 | `sha256:169654a6c3a07281537d00c00858e99b0d0b280ac5d1918cbfc0d21f545a83ff` |
| closure entries | 628 (administrator runtime files + sealed macOS/dyld shared-cache bindings) |
| runtime image | `/Library/KioComparatorRuntime/v1.dmg` |
| runtime image SHA-256 | `78ec3d093ea7b5f9e5ab80d599b1a86ce087fcb5ad87d0fdfb5e986a7abbe9f8` |
| runtime manifest SHA-256 | `416e8fd445d55495c7a58e7006ad7b0719bfbfbec811fb05faeda72c57a962ae` |

runtime root は root:wheel、group/other 非書込み、read-only mount です。Rust evaluator は bind 時、
各 rga subprocess の前後、finalization 時に mount identity と recursive Mach-O closure を再解決し、
report の closure digest と完全比較しました。測定後も image、manifest、binary の SHA-256 は不変で、
fresh post-run attestation も pre-run attestation と byte-identical でした。これらのoperator preflight/postflight
観測値は上記 `binding-checks.json` に保存しています。測定中の正式なruntime authorityはDMG sidecarではなく、
reportが各subprocess境界で再検証したmounted read-only root、mount identity、628-entry closureです。

## Fresh synthetic Recall

現行 release binaryで生成、履歴再現、評価を連続して行いました。環境はcredentialを含まない
`env -i`で、ネットワークやpaid APIを使っていません。

| 項目 | 値 |
|---|---|
| results | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/synthetic-current-4fac253-20260814.lPZWBL/results.json` |
| results SHA-256 | `f90ef9115bd3516a974899bc6ad2114fa2a0343d9abd5eb1eaee2e5a9ce3368a` |
| report | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/synthetic-current-4fac253-20260814.lPZWBL/report.md` |
| report SHA-256 | `f3f31c21caaff4a871cf2a454c72931ccf3102d7764c50641dce06cebe6cd13b` |
| execution provenance | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/synthetic-current-4fac253-20260814.lPZWBL/provenance.json` |
| provenance SHA-256 | `bd2f840718e89fdb02210f9f38a8c9f02a15c8302e64a1524f25a431ecf6b60b` |
| corpus manifest SHA-256 | `f53656c023fd13f49fd86bd648f53857d786b8b50ee3c2b13a11e7cbead7f128` |
| history manifest SHA-256 | `028d815176a59093c6aa102461eef4b2049b536f14a595ad6819c8d384bc363d` |

| Scenario | Hits / queries | Recall@10 | p95 | Structural verification |
|---|---:|---:|---:|---|
| M3-1 | 18/18 | 1.0 | 111.64675 ms | pass |
| M3-2 | 16/16 | 1.0 | 115.480875 ms | rename/edit pass、148 pointer CAS attested、failure 0 |
| M3-3 | 16/16 | 1.0 | 100.234292 ms | deleted coverage pass、restore pass、problem 0 |

全50問がscored、failed/unimplementedは0です。生成、履歴再現、評価の全commandを `env -i` と
artifact-local HOME/XDG で実行し、credentialを転送せず、paid API callは0件です。provenanceは
HEAD `4fac253fd1fd5dea8308c4bc2d0dafdd8c56fc5c`、Kio SHA-256
`6b88aaf74fa8c4d24a18608ad672a70173fec84cf95215694acdcfa23f38f4fb`、kio-eval SHA-256
`bfd4f13ddb46867bc2d4bb579ff35c45c013eae8a8bf3dec6af9c1948c82dbc6`、command、入力、出力を束縛します。
旧Python runnerの保存済みJSONを証拠として再利用していません。

## Dogfood manual scenarios

手動確認の集約artifactは
`/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/dogfood-manual-scenarios-20260814/summary.json`
（SHA-256 `c01b6f064b6494807d8ad155db147fc2f07e276d904c11f23bc2b0bc96891d92`）です。

- M3-1: original p01 dogfood scopeで `latency` を検索し、`latency-review.docx` のEvidence Pointerを
  `view` / `evidence verify` / `open`。`open` は `status=opened`、working-tree path使用、temporary=false。
- M3-2: originalの `設計確認メモ.md` とbyte-identicalな隔離dogfood copyを
  `orchid-ledger-review.md` へrename。`--all-history --mode text --offline` で旧
  `path_at_commit=設計確認メモ.md` と `current_path=orchid-ledger-review.md` を同じraw_hashで取得し、
  historical Markdown viewとPointer verifyがpass。
- M3-3: 同じ隔離copyをrecoverableなscope外退避によってworking treeから削除。
  `--include-deleted --mode text --offline` で `current_path=null` の削除済みEvidenceを取得し、view/verify後、
  fresh `restored/`へ非破壊restore。restored SHA-256はoriginalと同じ
  `6eeb22073a7e8f48304a26e6e2407b95e0b51df25a41c0e11d8037a718f6d841`、上書き0件。

M3-2/M3-3は実フォルダを変更せず、その実文書bytesの隔離copyだけをrename/deleteしました。
original SHA-256は前後で同一です。3シナリオともネットワーク/API課金はありません。

## その他の Phase 3 evidence

| Evidence | 結果 | Artifact | SHA-256 |
|---|---|---|---|
| dogfood final status | 428/428 scope、5,013/5,013 task done、nonterminal/read error/stalled batch 0、spent `$1.2008117`、remaining `$8.7991883` | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/status-after-round-5-final/summary.json` | `c0f6baf8fba4a3c93f2f258008de90f08338ed69b1eaf087da787a4f6b584537` |
| Q_hard + synthetic M3-1 | current Kio SHA `6b88aaf…`、attested external fixture、8/8 + 18/18 = 26/26、Recall@10 1.0、acceptance eligible | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/qhard-current-4fac253-20260814.AOde3z/qhard-combined-26-report.json` | `05bcef5131c37e0a45b4a232111d42db2d01275b7350b4aee67181146d683e1a` |
| Q_hard provenance | HEAD、kio/kio-eval、golden、fixture/synthetic binding、credential名、command | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/qhard-current-4fac253-20260814.AOde3z/provenance.json` | `384cbfcc6cb8f161c9572bc8c5aecf9aee31dd7cadb642849c18f32b09190207` |
| full Scale | current Kio SHA `6b88aaf…`、120,000 chunk、5 warmup、100 sample、全 p95 gate pass | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/scale-current-4fac253-20260814.oUUsoI/scale-full-report.json` | `58b0bce4f7222572eb1995fb3ba6f0c499cf2f85540badb729c65fbb865a881d` |
| full Scale provenance | HEAD、kio/kio-eval、manifest、attestation、command | `/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/scale-current-4fac253-20260814.oUUsoI/provenance.json` | `1e0da9ef64bbf47d956ee3fd9e9d139c697c76fbe362e90b2012e5a5577061c6` |

current binaryのScale metric p95 は M3-1 `409.6845 ms` (`< 5,000 ms`)、
M3-2 `508.102291 ms`、M3-3 `513.881541 ms` (ともに `< 7,000 ms`) です。
以前のScale reportも内容を変更せず永続領域
`/Users/ttokunaga-ja/kio-dogfood/phase3-run.nOLqdw/artifacts/scale-full-report-120k-20260813.json`
へ保存しており、元の `/tmp/kio-phase3-scale.qIL9VW/scale-full-report.json` とbyte-identical、指定SHA-256
`86a19b7c3721e878515f1c2de958b1928da90c87d80ef294043c1848fb0eb572` に一致しますが、
formal gateにはcurrent binaryを束縛した上記fresh reportだけを使いました。

## Local validation

正式受け入れHEADに対して次を再実行し、すべて pass しました。

- `cargo fmt --all -- --check`
- `cargo clippy --workspace --all-targets --locked -- -D warnings`
- `cargo test --workspace --all-targets --locked`
- `.github/workflows/ci.yml` の Rust job と同じ Python unittest module 列
- `KIO_RUN_PERSONA_FS_INTEGRATION=1 python3 -m unittest -v eval.test_generate_persona_corpus`
- `git diff --check`

## Non-substitution and phase boundary

過去の baseline JSON、blocked report、offline 4/24 report は正式証拠に使用していません。
query集合、threshold、fixtureは結果に合わせて変更していません。Phase 4/5 の実装はこの正式受け入れと
記録の完了まで開始しておらず、本記録も Phase 4/5 の実装を含みません。
