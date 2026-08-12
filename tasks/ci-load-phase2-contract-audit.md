# CI・テスト負荷調査 Phase 2: 契約・言語境界・旧仕様監査

Status: **完了 (2026-08-12)**

Phase 1 の実測を、正本仕様、製品実装、Rust test、Python oracle、CI jobへ対応付けた。
このPhaseではCI定義、製品コード、テストを変更していない。全29 jobの機械可読な判定は
[`artifacts/ci-contract-matrix-2026-08-12.json`](artifacts/ci-contract-matrix-2026-08-12.json)
に固定した。

## 結論

現在の最大の問題は、Pythonの速度そのものではない。push/PR CIの大部分が、現在のMVP製品経路に
接続されていない`persona-v2`実験体系を毎push/PRで完全再生していることである。

- 29 job中23 jobが`persona-v2-*`で、Python testだけを実行する。
- 23 jobの成功中央値合計は993.52分で、全job中央値合計1,052.18分の94.4%を占める。
- 現在の推定median critical pathは
  `closure-contract-fast -> history-presolve-input-closure-cold`の223.06分である。
- `persona-v2`は185 file、178,785行、849 testを持つ。全Pythonの78.8%であり、
  全Rust 135,273行の1.32倍である。
- しかしこの体系は自ら`non-authorizing`、未発行namespace、Kio実行不能、formal publication
  falseと定義し、`crates/`の製品symbolや実CLIを呼ばない。正本`docs/01`〜`10`にも
  `persona_v2`は現れない。

したがって、178,785行をRustへ逐語移植することは勧めない。製品要求として採用する内容だけを
短い正本へ抽出し、この実験体系をpush/PR CIから外したうえでarchiveまたは削除する。一方、現行の
M3 evaluatorにあるRecall、percentile、manifest、exit分類、corpus生成、pointer検証など、
製品評価に接続された決定論的処理はRustへ移す。この二つを区別することが、ユーザー方針
「PythonでしかできないものだけPythonに残す」の実行形である。

もう一つの重要な発見は、正本
[`docs/10-operations.md`](../docs/10-operations.md) §12.5が「未公開の間は後方互換分岐を
置かない」と確定しているのに、SQLite、cost ledger、approval、task、normalized object、
store version、CAS pathに旧shapeの読取り・in-place migrationが残っていることである。
一部のstatic testはそれを削除しないよう明示的に固定している。Phase 3ではテストだけを消さず、
旧production path、旧fixture、旧testを同じ変更で除去し、現行formatの成功・fail-closed・
rebuild契約へ置き換える必要がある。

## 1. 判定基準

### 1.1 仕様のauthority

[`docs/README.md`](../docs/README.md)に従い、`docs/01`〜`10`を正本とした。
`docs/11-requirements.md`はdeprecated archiveなので判断根拠に使っていない。Rustの現在挙動は
実装状況を示す証拠であって、正本と矛盾したときに仕様を上書きするauthorityではない。

現在のMVPはCAS、normalized Markdown、chunk/embedding/FTS/hybrid search、Evidence Pointer、
snapshot DAG、restore、time travel、最小purge、単発evidence verifyである
([`docs/09-mvp-scope.md`](../docs/09-mvp-scope.md) §1.1)。GC、move、export/import、
batch evidence、public Agent API、GUI、syncはPhase 4以降であり、現在のDone判定には含めない。

### 1.2 旧仕様の分類

`docs/10` §12.5に従い、次の三者を分離した。

| 分類 | 扱い |
|---|---|
| 旧development storeを読む後方互換 | production branchと旧testを除去する |
| future versionをread-onlyで扱う前方互換 | 維持する |
| torn write、欠損counter等のcorruption recovery | 現行仕様なら維持する |
| Windows、digest-only、Unicode等のportability | 維持する。ただし旧物理名fallbackとは分離する |

### 1.3 テスト削除の規律

「テストを消してproductionの旧分岐だけ残す」変更を禁止する。逆に、旧分岐を消したのに
static testがその関数名や`ALTER TABLE`を要求し続ける状態も禁止する。

削除bundleは常に次を含む。

1. 旧production symbol/branch。
2. 旧shapeのfixtureと旧behavior test。
3. 現行shapeの成功、incompatible cacheのrebuild誘導、またはcorruptionのfail-closed test。
4. 正本仕様と運用runbookの同時更新。

## 2. 製品目標との対応

### 2.1 実装済みのMVP経路

監査範囲では、製品の中核はRust実装とbehavior testに接続されている。

- CAS/DAG、normalized/chunk/embedding、FTS/hybrid search。
- multi-scope、replica、device-wide `repair all` / `repair replica`。
- Evidence Pointerの発行・parse・open/view・object verify。
- `--at`、`--all-history`、`--include-deleted`、restore、purge barrier。
- M3-1/2/3のsynthetic history evaluation。

従って、`persona-v2`の巨大さを製品完成度と見なすことはできない一方、製品本体が未実装という
意味でもない。問題は「MVPに接続された比較的小さい契約」と「未採用の将来projection」が
同じpush/PR CIに混在していることである。

### 2.2 実在する製品gap

次は実験体系ではなく、正本と実装の差である。

- `docs/09` §4が要求する20 scope / 合計100,000 chunkのp95 5秒未満を、現在のpush/PR CIは
  assertionしていない。
- 20問以上の`Q_hard`でRecall@10 >= 0.8、かつSpotlight/ripgrep-allより0.3以上高いという
  acceptance evidenceが閉じていない。現CIのshort synthetic gateは有用だが代替ではない。
- `[scope] index_vcs_repos`の明示opt-inが正本にあるのに、config schemaとchild `.kio`
  生成経路がない。現在のQB15 testはこの欠落を固定しており、恒久契約にしてはいけない。

### 2.3 仕様自体の不整合

- `docs/09`はtest除外11,000〜16,000 Rust LOC、test込み20,000〜30,000 LOCを動かさない
  上限としている。現状はRust 135,273行で、`kio-cli/src/main.rs`単体でも26,848行である。
  数値だけを書き換える前に、Phase 4機能の前倒し、巨大dispatcher、重複contract、生成的実験
  の混入を分解し、上限が現在もrelease gateなのかを正本で再裁定する必要がある。
- `docs/10` §12.5は旧store互換を禁止する一方、`docs/03`と`docs/04`の一部はlegacy tree、
  pre-object-store SQLite、旧物理CAS名を読むと記載している。実装を消す前に正本間の矛盾を
  一つのcommitで解消する。

## 3. 全29 CI jobの契約監査

### 3.1 `persona-v2` 23 job

これらは大きく四系列に分かれる。

| 系列 | 主な再生 | 代表median |
|---|---|---:|
| source / semantic / overlay / lifecycle | 同じ203,000行級source universe | 5.38〜65.72分 |
| derivation contract/full/cold | 113 receipt、coldは2 hash seed | 0.12 / 76.52 / 85.56分 |
| complete content/contract/full/cold | 253 receipt、coldは2 hash seed | 41.17 / 0.12 / 96.43 / 92.49分 |
| closure/capacity/history | full closure、coldは2 fresh build | history 95.41 / 199.75分 |

各validatorの独立性には意味があるが、検証対象はpersona設計内部のschema、digest、publication
receiptである。実Kio CLI、Rust store、Evidence Pointer、search結果を検証していない。
`needs`は順序だけでartifactを渡さないため、同じ入力も毎jobで再生成する。

Phase 3の第一変更として、23 jobをpush/PR workflowから外す。これは単にslow testをnightlyへ
移す提案ではない。製品authorityを持たない未発行設計がrelease gateになっている状態を正す
提案である。まだ設計参照が必要なら、抽出期間中だけ`workflow_dispatch`のexperimental workflow
として残せるが、製品の合否判定には使わない。workflowとrun履歴から分かるのはpush/PR時に
起動することまでであり、GitHub branch protectionのrequired check設定自体は今回監査していない。

履歴中央値からのtopology推定では、これによりjob中央値合計は993.52分減り、最長signalは
Windowsの25.13分、または`rust -> synthetic`の22.69分程度になる。これは未計測の見積りであり、
変更後にPhase 1と同じ10-run形式で再測定する。

### 3.2 維持する6 job

| job | 判定 |
|---|---|
| `rust` | 必須。Rust checkとPython evalを分離し、決定論的evalをRustへ移す |
| `synthetic-history-eval` | 必須。現M3製品経路に接続される。release artifact重複buildは解消候補 |
| `msrv` | 必須。Rust 1.86 compatibility固有signal |
| macOS / Windows | platform/security signalを維持。全workspace再実行の縮小はcoverage mapping後 |
| `persona-w0-integration` | Python generator移行後、Rust corpus contractへ置換または削除 |

cheap gateの失敗前に高価なjobが起動するPhase 1の問題は、persona-v2 quarantineで大部分が消える。
将来高価なscale benchmarkを追加する際は`fmt + clippy + bounded unit`を先行gateにする。

## 4. PythonとRustの所有境界

### 4.1 Rustへ移すもの

次はMLではなく決定論的な製品・評価契約であり、Rustで書けるだけでなくRustを正本にした方が
driftを減らせる。

| 対象 | 現在 | 移行方針 |
|---|---|---|
| slugify | Python `run_eval.py`とRust chunkingに重複 | Rustをcanonical、Pythonはgolden差分のみ |
| canonical JSON / chunk identity | PythonがRust CAS/JCSを再実装 | Rust APIを使用し、Unicode/number/optional omission vectorで独立確認 |
| Recall@k | Pythonだけ | internal Rust evaluatorへ実装 |
| nearest-rank percentile | Python内でも2重実装 | Rustで一つに統合 |
| exit/outcome/report分類 | Python evaluator policy | Rust `ExitCode`と明示policyへ統合 |
| manifest schema/検証 | Python dict処理 | Rust serde型とstrict validationへ移行 |
| deterministic corpus生成 | Python stdlib | byte-identical fixture固定後にRustへ移行 |
| Evidence/CAS attestation | Pythonで本体を再実装 | 完全なRust attestation APIを作り、Pythonはmalformed differentialへ縮小 |

Pythonのsorted JSONとRustのRFC 8785 JCSが現在一致すると確認できるのは、凍結済みの
ASCII-key・integer-only fixtureの範囲だけである。任意JSONを置換する前に、float/large integer、
Unicode key/value、optional fieldのomit/null差をvectorに固定する。

また、`kio-search::EvidencePointer`のschema検証だけではPython `PointerAttestor`と同等ではない。
後者はbounded no-follow read、commit→tree path→chunk object、hash/identity/field整合まで検証する。
現在の完全に近い経路はCLI内のprivate verify処理なので、再利用可能なRust attestation APIを公開するか
CLI経路をそのまま呼べるようにし、malformed、symlink、size bound、field mismatchでparityを
証明するまでPython実装を削除しない。

追加する抽象化は一つのinternal Rust evaluation binaryに限定する。小さなcrateを用途ごとに増やしたり、
製品crateから評価用policyを逆依存させたりしない。既存`kio-core`、`kio-index`、`kio-search`を
再利用し、評価binaryが外側から組み立てる。

移行順は次とする。

1. RFC 8785/JCS、Unicode slug、chunk identity、Recall、percentileのgolden vectorを固定する。
2. Rust evaluatorへmetrics、manifest、exit/report、attestationを実装する。
3. Python evaluatorをthin wrapperまたはdifferential testへ縮める。
4. corpus generatorをbyte-for-byteで移す。
5. history replayはRust runnerがpublic CLI契約を損なわず再利用できる段階で移す。

history coldの約200分はPython起動ではなく、253 receipt/506 provider call相当を2 seedで再構築する
時間である。`replay_history.py`をRustへ翻訳するだけでは解決しないため、言語移行と
materialization回数削減を別のacceptance metricで扱う。

### 4.2 Pythonに残すもの

- PyTorch、Transformers等を使うlocal model runtimeとmodel固有pre/post-processing。
  現在も`eval/u7/u7_same_space.py`にはdynamic importがある。
- Rust outputを別実装で攻撃的に検証する、小さく固定されたdifferential/security oracle。
- 採否判断中の短命なv3/v4実験。ただし製品のpush/PR gateから外し、判断終了後はarchiveする。

「Pythonで書けるから残す」ではなく、Python ML ecosystemまたは実装独立性が具体的なsignalを
持つ場合だけ残す。filesystem、JSON、hash、percentile、Recall、CLI exit分類はこの条件を満たさない。

### 4.3 Rustへ移さず削除するもの

`persona-v2`はここに分類する。非authorizingな将来設計をRustへ移すと、同じ空中楼閣をより強い
型で維持するだけになる。採用するscale axis、fixture dimension、tamper invariantだけを
M3/scale正本とRust evaluatorのtest vectorへ抽出し、残りはgit historyまたは明示的archiveへ送る。

## 5. 旧仕様と不要抽象化の監査

### 5.1 後方互換として除去する候補と前提条件

以下は`docs/10` §12.5から見れば除去候補だが、関数名だけを根拠に即時削除しない。
正本の矛盾を解き、全call pathで旧development dataの読取りなのか現行corruption recoveryなのかを
証明し、右欄の置換契約を先に用意してから除去する。

| 対象 | 現在の残存 | 置換契約 |
|---|---|---|
| old `chunks` / missing `context_key` | FTSが`ALTER TABLE`とtable rewriteを実行 | 明示schema fingerprint。fresh/missing DBは初期化し、incompatible既存DBは無変更でrebuild誘導 |
| pre-object-store embedding | rebuildが旧SQLite rowをsnapshotしCASへbackfill | CAS欠損をcorruption扱い。履歴cacheをtruthから再構築してから除去 |
| old cost-ledger JSONL | startup importerが不足fieldを推測し`.migrated`へrename | bytesを保持しstartupはfail closed。変換は明示的なproduct外operator操作のみ |
| approval missing fields | schemaとcleanupが旧pending/rowを許容 | 現required fieldをstrictに検証しfail closed |
| old task shapes | reservation prefix、hold_reason、metadataにdefault/fallback | 現task typeで適用可能なfieldだけrequired化 |
| normalized object missing metadata | empty defaultでdeserialize | current schema rejection |
| missing/legacy store version | versionなし・旧config keyを許容 | current version必須、future version read-onlyだけ維持 |
| old CAS/raw reference/path forms | canonical以外の物理名をfallback検索 | digest-only portabilityを維持し旧fallbackを削除 |
| missing tree/path/pointer fields | 一部default/旧shape reader | current canonical objectを必須化 |
| lifecycle eventのmissing `epoch` | 旧eventをepoch 0として読む | malformed eventはreject。counter file recoveryとは分離 |

`sqlite.db`はrebuildable cacheだが、cost ledger SQLiteはnon-rebuildable truthである。この二つを
同じ「消して再構築」で扱わない。後者の旧development bytesをstartupが黙って破棄・renameしては
ならない。mappingを推測してproductに取り込まず、bytesを保持してactionable errorでfail closedにし、
必要ならユーザーが明示的に起動する一回限りのoperator export/conversionをmain外で提供する。
JSONL importerを消した後も、現SQLite schema用のgeneric marker infrastructureは必要箇所へ移せるが、
存在しないcutoverが完了したように見せるmigration markerは残さない。

旧DB snapshotのtree rowは単純削除できない。現在はhistorical cache保持にも使われているため、
commit/tree/CASの正本からhistorical tree cacheを再構成する経路へ置き換えてからSQLite snapshotを
除去する。acceptanceは、rebuild後も`--at`、`--all-history`、time travel、historical Evidence Pointer
resolutionが成功し、必要なcommit/tree objectが欠損するとcorruptionまたはshallow stateを明示して
失敗し、履歴を黙って落とさないことである。

derived SQLiteの旧schema拒否もfresh DB作成と区別する。空または存在しないDBはcurrent schemaで
初期化できる一方、既存の不一致DBは最初の書込みより前にschema fingerprint/versionで検出し、
無変更のまま`repair rebuild-db`を案内するtestが必要である。

旧CAS colon/raw-name leafは、現行writerが全OSでcanonical digest-only名を書く以上、旧dataを読む
後方互換であって現在のWindows portabilityそのものではない、と本監査では裁定する。ただし
`docs/03`の一部はこれをportability fallbackとしているため、先に正本を統一する。削除時には
canonical/legacyの両方がある場合のconflict detectionをどう置き換えるかを明示し、Windowsと
non-Windowsでcanonical objectのwrite/read/hash mismatch testを残す。

### 5.2 維持するもの

- future `kio_format_version`をread-onlyで扱うforward compatibility。
- purge/lifecycle counter fileの欠損・torn writeからのfail-closed recovery。旧lifecycle eventの
  missing `epoch`許容とは別契約であり、前者を維持し後者を除去候補とする。
- Unicode正規化、canonical digest-only path、Windows portability。
- durability、purge phase、replica HEAD、multi-scope timeout、adapter mockのfault injection seam。
  使用箇所とbehavior testを照合し、今回orphanは確認されなかった。
- keychain未実装をloud errorにするadapter contract。これは旧store互換ではない。

### 5.3 placeholderとdead abstraction

- `kio-index/src/lib.rs`の「types and trait skeletons only」は現状と一致しない。
  `IndexError::NotImplemented`とplaceholder schema testは到達不能なら削除する。
- `SearchError::NotImplemented`もconstructorが見つからず、CLI mappingだけが残る。reachability確認後に
  variantとmappingを同時に削除する。
- `gc`と`move`はPhase 4+なのに現CLIにplaceholder subcommandだけ存在する。将来の仕様記述は残しつつ、
  現在のhelp surfaceから外す方を推奨する。実装開始時に実契約とともに追加し直す。
- `Evidence` commandのcommentがplaceholderのままなど、実装済みなのに古いarchitecture語彙が残る。

## 6. 静的testと重複test

静的source scanはすべて悪いわけではない。lock orderingやproducer/validator independenceのように
runtime testだけで安定して証明しにくいarchitecture invariantは価値がある。一方、関数名や
source文字列を固定するtestはrefactorを妨げ、behaviorを証明しない。

| test | 判定 |
|---|---|
| PB20 legacy `ALTER TABLE` count | 旧migrationと同時に削除。current schema rejection/rebuild testへ置換 |
| QB20 symlink source scan | 既存behavioral symlink testを確認後、static重複を削除 |
| QB31/QB37 DDL・legacy table文字列scan | executable schema inspectionへ置換 |
| QB11/QB12 store/purge lock order | 強い代替ができるまで維持 |
| QB15 `index_vcs_repos`不存在 | gap tracker扱い。実装時に正のbehavior contractへ置換 |
| Python AST/`inspect` independence test | 小さい独立oracleでは維持。persona-v2 archive時は体系ごと除去 |

巨大Rust integration suiteもPhase 3以降の計測対象である。`step3_p0_contract.rs`は11,303行、
`step4b_p2c_contract.rs`は2,162行で、workspace全体がLinux/macOS/Windowsで反復される。
ただしファイル分割だけでは実行時間は減らない。production symbol、fixture setup、OS固有signalの
matrixを作り、同じbehaviorを3 OSで走らせる必要がないtestだけをnarrowする。

## 7. Phase 3に提案する実装package

Phase 3は次の順序を提案する。各packageを独立commitにし、local validation後にのみ次へ進む。

### P0: non-authorizing CIの隔離

- push/PR workflowから23 `persona-v2` jobを除く。branch protectionでrequired化されていれば
  required check設定も同時に更新する。
- `rust`、synthetic M3、MSRV、macOS、Windowsを維持する。
- workflow job list、M3 gate存続、YAML parseをtestする。
- 変更後の実測をPhase 1と同じschemaで採取する。

期待値はrunner median合計 -993.52分、critical path約223分から約25分への低下である。
未計測推定なので、達成条件は「数値どおり」ではなく、green runでwall/runner-hoursを再取得し
説明できることとする。

### P1: 正本とpre-release storage contractの一本化

1. `docs/03`、`04`、`10`のlegacy例外矛盾を先に解消する。
2. fresh/current/incompatibleを区別するschema gateとhistory再構築を先に追加し、その後にderived
   SQLiteのin-place migrationとold snapshot sourceを除去する。
3. non-rebuildable cost ledgerの旧importを別commitで除去する。
4. approval/task/normalized/store-version/path/treeの旧shapeをtrust boundaryごとに除去する。
5. corruption recoveryとforward compatibilityが残ることをnegative testで確認する。

storage/security境界に触れるため、これはまとめて機械削除せず、小さなreviewable commitに分ける。

### P1: Rust evaluation core

- golden vector commit。
- internal Rust evaluatorのmetrics/manifest/exit/attestation commit。
- Python wrapper縮小commit。
- deterministic corpus generator commit。

各段階で既存M3-1/2/3のJSON report、Recall、exit、pointer tamper結果が一致することを条件にする。

### P2: experimental code整理と製品gap閉鎖

- 採用requirement抽出後、`persona-v2` 178,785行をarchiveまたは削除する。逐語Rust portはしない。
- `index_vcs_repos`を実装しQB15を正のbehavior testへ変える。
- static source scan、dead error variant、stale comment、Phase 4 placeholderを整理する。
- 20 scope / 100,000 chunk p95と20問以上の`Q_hard`をRust evaluatorで計測する。
- full scale benchmarkはscheduled/manual、bounded smokeはpush/PR gateにする。

## 8. Phase 2の完了条件

- [x] 正本仕様とPhase境界を固定した。
- [x] 全29 CI jobに固有signal、production接続、重複、処置を割り当てた。
- [x] Python処理をRust移行、Python維持、移植せず削除の三つに分類した。
- [x] 旧仕様を後方互換、forward compatibility、corruption recovery、portabilityに裁定した。
- [x] testだけを削除しないreplacement規律を定義した。
- [x] Phase 3 packageに効果、risk、replacement testを付けた。

Phase 2では実装を行っていない。Phase 3はユーザーの明示指示を受けるまで開始しない。
