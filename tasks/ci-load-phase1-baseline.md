# CI・テスト負荷調査 Phase 1: 実測ベースライン

Status: **完了 (2026-08-12)**

この文書は `.github/workflows/ci.yml` の負荷、重複、critical path を測った
Phase 1 の記録である。この Phase では CI 定義、製品コード、テスト契約を変更していない。
機械可読な測定値は
[`artifacts/ci-cost-baseline-2026-08-12.json`](artifacts/ci-cost-baseline-2026-08-12.json)
に固定した。

## 結論

問題の中心は「Pythonだから遅い」ことではない。29ジョブのうち20ジョブが初期fan-outし、
残る9ジョブも3つの`needs`系統から後続する。その中で、同じ203,000行級の inventory や
113/253 receipt の projectionをfull/coldで何度も独立生成する構造が支配的である。

- 成功run 10件のwall-clock中央値は252.5分、最大275.75分だった。
- 成功run 1件のjob実行時間合計は中央値1,035.1分、つまり17.25 runner-hoursだった。
- critical pathは全10件で
  `closure-contract-fast -> history-presolve-input-closure-cold` だった。
- `history-presolve-input-closure-cold` 単体の中央値は199.75分、最大206.32分だった。
- 直近完了10runは合計155.94 runner-hoursを消費した。そのうち、supersedeされた
  3runで少なくとも11.75 runner-hoursがキャンセルまでに使われた。
- 過去の代表runではhistory coldのcheckoutは約2秒、テスト本体は12,160.851秒だった。
  checkoutやPython起動の最適化だけでは桁は変わらない。

直近5runの`rust` jobは既知の`cargo fmt --check`差分で早期失敗していたのに、
高価なpersona jobは独立に走り続けた。現行HEADではformat問題は修復され、進行中run
`31557993561` のrust jobも成功しているが、「cheap gateが失敗してもfull/coldが走る」
workflow構造は残っている。

## 測定方法と限界

GitHub Actions RESTデータを`gh`で取得し、全ページのjobについて
`completed_at - started_at`を実行時間とした。job時間の総和をrunner時間としているが、
GitHub内部のqueue時間と課金時間は取得できないため、請求額の断定には使わない。

成功runの分布には直近10件の成功runを使った。失敗・キャンセルの実損を見落とさないため、
別に直近完了10run（成功5、失敗2、キャンセル3）も集計した。過去runは各commit時点の
workflowであり、`actions/checkout@v4`を使っていた。現行HEADの`@v7`と混同しない。

ローカル計測はmacOS 26.6.1、Apple M4 Pro (14 logical CPU)、51.5 GB RAM、
Python 3.14.6、Rust 1.97.0で`/usr/bin/time -lp`を使った。runnerとの絶対速度比較ではなく、
contract/full/coldの倍率と実行構造を確認するための標本である。

| 種別 | 代表テスト | wall | 最大RSS |
|---|---|---:|---:|
| contract | projection derivation contract (3 tests) | 0.50秒 | 54.4 MB |
| full | capacity fact policy full (1 test) | 5.45秒 | 65.2 MB |
| cold | capacity fact policy cold (2 hash seeds) | 11.01秒 | 55.5 MB* |

\* coldのRSSは親Pythonプロセスの値で、子プロセスの合算ではない。

小さい同一契約でもcoldはfullのおよそ2倍だった。実際のhistory coldも、seed 0が
6,067.38秒、seed 1が6,092.47秒で、合計12,160.85秒である。各seedは253 receiptと
506 projection body callを新規生成し、最大RSSは約700 MBだった。

## 29ジョブの信号とコスト

### Fast/contract gate

| ジョブ群 | 固有の信号 | 成功中央値 |
|---|---|---:|
| nonauthorizing core | schema、topology、renderer、catalogの境界 | 12.27分 |
| nonauthorizing inputs | bounded input、receipt、closure、scale不変条件 | 20.19分 |
| closure contract fast | namespace、history/device、resolution、capacity契約 | 23.31分 |
| projection derivation/complete contract | providerを開く前のshape/tamper境界 | 各0.12分 |
| rust | fmt、clippy、全Rust testと27 Python module | 19.77分 |
| MSRV | Rust 1.86でのcompile compatibility | 0.86分 |

名前がfastでもclosure contractは20分超であり、さらに中身のfixture importとvalidator
呼出しを分解して測る必要がある。それでも200分のcoldより先に失敗判定できる信号である。

### Full materialization

| ジョブ | 主な固有信号 | 成功中央値 |
|---|---|---:|
| projection complete full | 253 receiptの全再生 | 96.43分 |
| history closure full | 全dependency closure | 95.41分 |
| projection derivation full | 113 receiptの全再生 | 76.52分 |
| source semantic membership full | 203,000行＋compact membership | 65.72分 |
| lifecycle effective membership full | 203,000行のsecond-pass reconciliation | 65.69分 |
| concrete overlay membership full | overlay全membershipとtamper matrix | 46.31分 |
| projection complete content | content/catalogの独立再構成 | 41.17分 |
| source parameter assignment full | 203,000行のintent mapping | 29.81分 |
| source matched lifecycle full | lifecycle/event全inventory | 21.98分 |
| lifecycle coverage/source inventory | coverage、203,000行inventory | 8.99 / 5.38分 |

source inventory、semantic membership、parameter assignment、matched/effective lifecycleは
同じ大規模source universeを別々に再構成する。各validatorの独立性には意味がある一方、
入力artifactまで毎回作り直す必要があるかは未証明である。

### Cold determinism

| ジョブ | 固有の信号 | 成功中央値 |
|---|---|---:|
| history closure cold | 2 hash seedsで全closureをfresh build | 199.75分 |
| projection complete cold | 2 hash seedsで253 receiptをfresh build | 92.49分 |
| projection derivation cold | 2 hash seedsで113 receiptをfresh build | 85.56分 |
| capacity axis cold | hash-seed独立性 | 3.65分 |
| capacity fact policy cold | hash-seed独立性 | 0.50分 |

cold laneの目的は「異なるプロセスでもbyte-identical」である。したがって生成済み結果を
両seed間で共有して高速化してはいけない。checkout、toolchain、入力fixtureの共有可能性と、
検証対象であるfresh生成状態を分離して扱う必要がある。

### Integration/evaluation/platform

- `persona-w0-integration`は実filesystem materializationで中央値3.27分。
- `synthetic-history-eval`はM3-1/2/3とRecall gateで中央値2.92分。ただし`rust`後に
  release buildとcorpus生成を改めて行い、artifactは受け取っていない。
- Windowsは中央値25.13分、macOSは6.71分。Linuxと同じworkspace testを再実行するが、
  platform固有のpath/security回帰を持つため、単なる重複とはまだ判定しない。

## PythonとRustについてPhase 1で確定したこと

`eval/`には262 Python file、96 test module、226,857行、1,269 test definitionがある。
CI対象コードからNumPy、pandas、PyTorch、TensorFlow、Transformers、scikit-learn等の
importは検出されなかった。50 test moduleが`subprocess`をimportし、42 moduleが
`ast`または`inspect`を使う。現在の重いpersona laneはML実行ではなく、標準ライブラリでの
決定論的生成、JSON/hash検証、独立validator、子プロセス再生が中心である。

したがって、ユーザー方針「PythonでしかできないものだけPythonに残す」に照らすと、
次はRust移行候補として扱うべきである。

1. `percentile_nearest_rank`、`slugify`、chunk identity hashのような決定論的primitive。
   現在はPython内でも重複し、一部はRust製品実装も再実装している。
2. deterministic corpus/manifest生成 (現行は Rust `kio-eval generate-corpus`)。
3. CLI history replay (`replay_history.py`)。
4. Recall/latency集計、exit分類、manifest検証 (現行は Rust `kio-eval`)。

ただし、Python validatorがRust製品実装から独立したoracleであること自体に価値がある契約も
ある。Rustへ製品ロジックを一本化したあと、Python側は同じ実装を丸ごと再実装するのではなく、
少数のgolden vectorとdifferential checkに縮退させるのが候補である。モデルruntime、
Python専用MLライブラリ連携、探索的notebook相当はPythonに残す。現行CIのpersona laneには
その「PythonでしかできないML処理」は確認できなかった。

## 重複とartifact再利用の境界

workflowにはcache、artifact upload/download、Python version pinがない。`needs`は
順序だけを作り、生成物は渡さない。同じmoduleをcontract/full/coldで最大3回起動する例があり、
大規模fixtureを毎jobで再生成する。

現時点で安全性が高い候補は次である。

- Cargo registry/git/targetをlockfile・toolchain・platformでkey化する。
- full lane間でimmutableな入力corpus/manifestだけをhash付きartifactとして渡す。
- release binaryを`rust`系buildからsynthetic evalへ渡す。
- cold laneは入力の固定artifactを使えても、検証対象の出力は各seedでfresh生成する。

テスト結果そのものやcold出力をcacheして合格扱いすることはしない。

## Phase 1から得た次Phaseの判断基準

実装順序は、単なるPython-to-Rust行数置換ではなく次の効果で評価する。

1. known-red変更で高価なjobを起動しないcheap-gate化。
2. 各jobが持つ固有oracleを保ったまま、重複materializationを除く。
3. Rustで表現できる決定論的契約をRustへ一本化し、Python再実装とのdriftをなくす。
4. coldの独立性を維持しつつ、PRごとの実行範囲とnightly/manualの完全監査を分離する。
5. 変更前後でwall-clock、runner-hours、Recall、hash、tamper検出力を同じbaselineで比較する。

Phase 2ではこの基準を使い、spec -> production symbol -> Rust test -> Python oracle -> CI jobの
対応表を作り、旧仕様、重複契約、静的source check、legacy migrationを削除可能・統合可能・
独立oracleとして維持、のいずれかに分類する。Phase 1ではその作業には着手していない。
