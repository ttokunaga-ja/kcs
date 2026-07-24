# Kio 検索評価ハーネス (synthetic)

`docs/09-mvp-scope.md` §4.3 の **Recall 評価規約 (ゴールデンクエリ)** を実行するための
合成コーパス + 履歴シナリオ + ゴールデンクエリ + 評価ランナー。設計宿題 #5
(`docs/09-mvp-scope.md` §5.5、**Step 3 着手前ゲート**) の成果物。

- 依存: **Python3 標準ライブラリのみ** (追加インストール不要)。
- 決定論: すべて固定 seed (`corpus_spec.SEED`) + hashlib 由来の seed。2 回実行で byte 同一。
- `crates/` の `kio` バイナリ (Step 1-2 実装済み) を使う。`cargo build --release` 済み前提。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `corpus_spec.py` | **正本**。scope / anchor 文書 / 履歴シナリオ (編集・リネーム・削除) の単一定義。他スクリプトが共有し drift を防ぐ |
| `generate_corpus.py` | 合成コーパス生成 (200-500 ファイル / 複数 scope)。`corpus-manifest.json` を出力 |
| `replay_history.py` | 各 scope で `init → index → snapshot → 編集 → snapshot → リネーム → snapshot → 削除 → snapshot` を決定論再現。`history-manifest.json` を出力 |
| `golden-queries.jsonl` | ゴールデンクエリ (M3-1 / M3-2 / M3-3 各 16+ 件)。**リポジトリ保持の正本** |
| `history-manifest.json` | replay がリネーム/編集/削除したファイルの記録 (`replay_history.py` が生成) |
| `run_eval.py` | 評価ランナー。`kio search --json` で Recall@10 を集計。expected のニーモニック → 実 `section_id` の解決層 (docs/04 §4.1 slug) を持つ。`--dry-run` は expected 実在 + 解決チェック。`--scenario` でシナリオ絞り込み |
| `test_run_eval.py` | `run_eval` の単体テスト (slugify / 解決層 / recall_at_k / exit 分類)。`python3 -m unittest eval.test_run_eval` |
| `scale_fixture_spec.py` | Recall corpus とは独立した性能 fixture の正本。20 scope と tiny/full の形を固定 |
| `generate_scale_corpus.py` | owner marker 付きで 20 scope の性能 corpus を決定論生成。full は 4,000 files / 120,000 expected chunks |
| `prepare_scale_corpus.py` | 各 leaf scope を `init → index` し、隔離 registry と SQLite attestation を作成 |
| `attest_scale_corpus.py` | HEAD・現行 chunk config・FTS coverage を照合し、検索可能 chunk の正確な総数を証明 |
| `run_scale_eval.py` | full fixture に対して既定 `auto` 横断検索を反復。text fallback を確認し、内部/プロセス時間の p50 / p95 / p99 と生の標本を出力 |
| `test_scale_*.py`, `test_run_scale_eval.py` | 性能 fixture の形、所有権、排他、bounded read、registry 復旧、計測契約の単体テスト |

## 使い方

コーパス本体は再生成可能なため **リポジトリにコミットしない** (一時ディレクトリへ生成する)。

```bash
# 0. バイナリ (未ビルドなら)
cargo build --release

# 1. 合成コーパス生成 (決定論的)
python3 eval/generate_corpus.py --out /tmp/kio-eval-corpus

# 2. 履歴シナリオ再現 (kio init/index/snapshot を実行し history-manifest.json を更新)
python3 eval/replay_history.py --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 3a. dry-run: golden-queries の expected {scope,file,section} が
#     corpus-manifest.json / history-manifest.json に実在し、かつ
#     (raw_hash, section_id) へ解決できる (slugify が空でない) か検証 (Step 3 前でも通る)
python3 eval/run_eval.py --dry-run --corpus /tmp/kio-eval-corpus

# 3b. 本評価: Recall@10 をシナリオ別に集計。
#     kio search 未実装の間は全クエリ NOT-IMPLEMENTED → exit 2 (未実装を green にしない)。
python3 eval/run_eval.py --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 3c. シナリオ絞り込み (複数指定可)。最終HEADのCIは3シナリオを個別に実行する。
python3 eval/run_eval.py --scenario M3-1 --corpus /tmp/kio-eval-corpus --bin target/release/kio
```

### exit コード (docs/09 §4.3, 2026-07-03 J2 裁定)

| 状況 | exit | 扱い |
| --- | --- | --- |
| 全シナリオ (対象) が Recall@10 >= 0.8 | `0` | PASS |
| `KIO-E-*-NOT-IMPLEMENTED*` 系のクエリが 1 件以上 | `2` | 未実装。Recall 判定は無効 (green にしない) |
| Recall 未達 / 実行失敗 (非 0 かつ非 3 exit・不正レスポンス・解決不能) | `1` | FAIL。当該クエリは recall 0 として集計に残す |

exit `3` (部分成功) は stdout の JSON を採点対象にする (実装後の部分成功や実バグを未実装で握り潰さない)。

## シナリオと評価コーパスの対応 (docs/09 §4)

| シナリオ | フラグ | コーパス上の対象 | 判定 |
| --- | --- | --- | --- |
| **M3-1** 現行検索 | (なし) | 編集/リネーム/削除しない安定 anchor。本文の数値・用語の部分記憶で引く | 現行 tree の該当 file がヒット |
| **M3-2** リネーム追跡 | `--all-history` | リネームされた anchor (旧名で記憶) + 編集された anchor (旧値は履歴のみ) | 旧 raw_hash の chunk が両方ヒット |
| **M3-3** 削除再発見 | `--include-deleted` | 削除された anchor の数値を再発見 | 削除済み file の chunk がヒット |

`expected` は `{scope, file, section}` の分離形式 (docs/09 §4.3、`03-data-model.md` §3
「直下のみ」規則)。`section` は **英語ニーモニック** (例 `"recall"`) であり、実 `section_id` ではない。

### expected → (raw_hash, section_id) の解決 (J2 裁定, 2026-07-03)

Recall の突き合わせ単位は `(raw_hash, section_id)` (docs/09 §4.3)。`expected` はニーモニックと
`{scope, file}` の分離形式なので、ハーネスが以下の手順で実値へ解決する:

1. **section (ニーモニック) → heading (実見出しテキスト)**
   `corpus-manifest.json` / `history-manifest.json` の anchor `sections[]` が
   `{slug: ニーモニック, heading: 実見出し}` を持つ (正本は `corpus_spec.ANCHORS`)。
   例: `"recall"` → 見出し `"回収率と精度"`。
2. **heading → section_id** … `docs/04-pipeline.md §4.1` の slug 規則で `slugify(heading)`。
   例: `slugify("回収率と精度")` = `"回収率と精度"` (日本語は保持。英語ニーモニックとは一致しない)。
   これが J2 の核心: `"recall"` を実 `section_id` として突き合わせると必ずミスする。
3. **{scope, file} → raw_hash** … manifest が記録する `raw_sha256` (ファイル bytes の sha256) から
   `raw_hash = "sha256:" + raw_sha256`。M3-2 (編集/リネーム) / M3-3 (削除) は
   `history-manifest.json` が **旧内容** の `raw_sha256` と heading を記録し、そちらを優先する。

突き合わせ時、`evidence_pointer.section_id` (docs/08 §2 では heading_path を "/" 連結した slug) は
最深 (leaf) セグメントを取り、`slugify(heading)` と比較する (見出し「回収率と精度」→ `"回収率と精度"`)。

### Recall 実測の gate タイミング

- Step 3 当時の gate は M3-1 のみだった。`--all-history` / `--include-deleted` が揃った現在は、
  **最終HEADのCIで M3-1 / M3-2 / M3-3 をすべて個別実行**する。

## dogfood との関係 (docs/09 §4.3)

評価コーパスは 2 種:

- **synthetic** (本ハーネス): 公開可能な生成文書。CI / Done 判定の**正本**。数値を公開してよい。
- **dogfood**: 開発者自身の実フォルダ (非公開)。数値は公開せず、3 シナリオの**主観成功確認**に使う。
  本ハーネスは dogfood の数値を扱わない。dogfood は同じ `golden-queries` 形式を各自ローカルで用意する。

Done 条件 = **synthetic で各シナリオ Recall@10 >= 0.8** + **dogfood で 3 シナリオの手動成功確認**。

## クエリ凍結規律 (重要)

`docs/09-mvp-scope.md` §4.3 / §4.2 に従う:

- ゴールデンクエリの追加は **Step 3 着手前まで**。
- **Step 3 着手後は `golden-queries.jsonl` の追加・差し替え・削除を禁止** (シナリオ凍結規律に準ずる)。
  悪化を隠すためのクエリ削除は禁止。物理的に実装不可能と判明した場合のみ docs 側で撤回 + 代替採用。
- コーパス定義 (`corpus_spec.py`) と履歴シナリオも同様に凍結対象。変更は Recall 数値の連続性を壊すため、
  Step 3 着手後は原則行わない。

## 決定論の検証

```bash
python3 eval/generate_corpus.py --out /tmp/c1
python3 eval/generate_corpus.py --out /tmp/c2
diff -r /tmp/c1 /tmp/c2   # 差分なし (byte 同一) であること
```

`history-manifest.json` の renamed/edited/deleted と scope 別 commit 件数も、フレッシュな
コーパスに対して 2 回再現すれば同一になる (commit hash / timestamp は非決定なので manifest に含めない)。

## 20 scope / 12 万 chunk 性能 fixture

§4.1 の「20 scopes / 合計 10 万 chunk」性能ゲートは、Recall の凍結済み 305 files / 7 scope
corpus を水増しせず、独立した fixture で測る。最初の層は再現性を優先した
**balanced current-text fixture** であり、`full` の形を次で固定する。

- 20 leaf scopes × 200 Markdown files × 30 ATX sections = **120,000 current chunks**
- 14 の利用者属性、20 の用途を engineering / research / ML-data / product / security / client / inbox に分ける
- 1 section を既定 `[chunking] strategy="heading", max_chars=6000` の 1 chunk 未満に保つ
- Kio は scope 直下だけを対象にするため、collection root 自体は scope にせず、20 leaf folders を個別 scope にする

folder と利用者・用途の対応は manifest にも保存する。

| folder | 主な利用者属性 | ユースケース |
| --- | --- | --- |
| `engineering-architecture` | software engineer | architecture / ADR |
| `engineering-api-specs` | software engineer | API contracts |
| `engineering-incidents` | SRE | incident response |
| `engineering-runbooks` | SRE | operations runbooks |
| `engineering-releases` | release engineer | release / migration notes |
| `research-papers` | academic researcher | paper library |
| `research-lab-notes` | academic researcher | laboratory notebook |
| `research-experiments` | academic researcher | experiment results |
| `research-grants` | principal investigator | grants / budgets |
| `research-literature` | graduate student | literature notes |
| `ml-model-evaluations` | ML engineer | model evaluation |
| `data-dictionaries` | data engineer | data dictionary / lineage |
| `data-dashboard-reports` | data analyst | dashboard reports |
| `ml-notebook-exports` | ML engineer | notebook exports |
| `product-meetings` | product manager | meeting decisions |
| `product-requirements` | product manager | requirements / user research |
| `product-roadmaps` | engineering manager | roadmap / capacity planning |
| `security-compliance` | security engineer | controls / audit / threats |
| `client-deliverables` | consultant | findings / recommendations |
| `downloads-inbox` | knowledge worker | downloaded references / inbox |

full は時間・ディスクを使う明示実行専用であり、通常 CI では生成・index しない。通常の安全確認には
同じ 20 scope 構造の `tiny` (20 files / 60 chunks) を使う。

```bash
# 軽量 smoke (20 scopes / 60 chunks)
python3 eval/generate_scale_corpus.py \
  --out /tmp/kio-scale-tiny --profile tiny
python3 eval/prepare_scale_corpus.py \
  --corpus /tmp/kio-scale-tiny --bin target/release/kio

# 本番規模 (20 scopes / 4,000 files / 120,000 chunks): 手動性能計測時のみ
python3 eval/generate_scale_corpus.py \
  --out /tmp/kio-scale-full --profile full
python3 eval/prepare_scale_corpus.py \
  --corpus /tmp/kio-scale-full --bin target/release/kio

# 任意時点で再検証 (read-only SQLite attestation)
python3 eval/attest_scale_corpus.py --corpus /tmp/kio-scale-full

# current-text 横断検索の手動計測。各scenario 5 warmup + 100標本、nearest-rank p50/p95/p99。
# 既定reportは corpus外の /tmp/kio-scale-full.latency.json。
python3 eval/run_scale_eval.py \
  --corpus /tmp/kio-scale-full --bin target/release/kio \
  --warmups-per-scenario 5 --samples-per-scenario 100
```

`prepare_scale_corpus.py` は各 scope を明示的な `kio index --offline --yes` で終える。`index` 自体が snapshot と
HEAD tree projection を公開するので、その直後に別の `kio snapshot` を追加してはならない。
device state は corpus 内の `.kio-eval-device` に隔離され、開発者の実 registry や API key を使わない。

出力の `scale-corpus-manifest.json` は全 source bytes、expected chunk 数、
query契約を版管理する `query_workload_id=exact-reference-v1`、
`scale-attestation.json` は次を証明する。

- manifest と 4,000 source files の完全一致、isolated registry の indexed 20 scopes 完全一致
- 本番検索と同じ `first_seen_commit` + 現行 `chunk_config_generations` + HEAD
  `(raw_hash, tool_profile_hash, gen)` predicate による current eligible chunk 数
- 全 section 共通 sentinel の FTS `MATCH` と FTS5 docsize shadow の双方で同数を確認
- full では current eligible chunks が 120,000、かつ 100,000 を超えること
- 各scopeの検索標本は期待section内に1回だけ現れる決定論reference tokenを使い、共通語によるscope順位tieを避ける。
  これは高選択性queryのlatency probeであり、広いqueryのmulti-scope ranking性能は証明しない

`run_scale_eval.py` は release binary・manifest・保存済み/再計算attestation・platformをreportへ束縛し、
各検索で既定の全scope選択、attested 20 scopes の成功、期待文書の上位10件入りを確認する。検索modeも
明示指定せず、既定 `auto` が `embedding_endpoint_not_configured` により `text` へfallbackしたことを検証する。
主指標は各検索が1行だけ追記する `KIO-M-SEARCH-001 search.latency_ms`、副指標はrunner計測のprocess wall timeで、
両方の生標本とp50/p95/p99を保存する。M3-1の `< 5秒` 判定は
**high-selectivity default-auto current-text baseline** であり、広いqueryやhybridを含む正式なMVP性能gateではない。M3-2
(`--all-history`) とM3-3 (`--include-deleted`) も同じ標本数で実行するが、このfixtureは単一HEADで
編集・rename・deleteを含まないため、結果は **execution-path-only** であり正式な履歴性能値ではない。

### このfixtureで証明しないもの

- 全scopeが6,000 chunks、全ファイルが同じ生成Markdownであり、実フォルダの偏ったscope規模、
  日本語、表、ログ、コード、長短文書の混在は代表しない。
- embeddingを必須化しないため、hybrid/vector p95は証明しない。
- exact reference tokenを使うため、広い共通語queryで20 scopeの候補が競合するranking/latencyは証明しない。
- M3-2/M3-3の正式な10万chunk性能には、同じ20 scopeへ編集・rename・deleteを重ね、
  historical/deleted populationをattestする独立したhistory overlayが必要。
- Q_hardのSpotlight/rga比較、dogfood、D1 (PDF 1,000本/5GB相当、TTFV/AI時間/コスト) は
  性質の異なるゲートなので、このbalanced fixtureへ混ぜない。

次の拡張順は (1) history overlay、(2) scope/chunk長を偏らせたskewed robustness fixture、
(3) Q_hard/D1/dogfood の実データ系ゲートとする。balanced fixtureの再現性は維持する。

生成先は owner marker で保護する。非空の未所有 directory は変更せず、`--reset-owned` も未知の
entry があれば削除前に停止する。ready corpus の再生成と再 prepare は no-op になる。

```bash
python3 -m unittest \
  eval.test_scale_corpus \
  eval.test_scale_attest_bounds \
  eval.test_scale_prepare \
  eval.test_run_scale_eval
```

## 20人の独立persona-PC fixture（設計契約）

上のbalanced fixtureは「1 registryの20用途」であり、20人のPC再現ではない。別の
persona-PC suiteでは、1人につき独立したPC root、XDG device state/registry、12個の
職種固有leaf scopeと8個の共通PC leaf scopeを持たせる。20人の各PCがformal fullで
W0/W5とも120,000 contributor chunks、W5後はcurrent+history 180,000 chunks以上を満たす。

- machine-readable matrix: `eval/persona_fixture_spec.py`
- contract and implementation order: `tasks/persona-pc-eval-contract.md`
- readable 20-person/ratio proposal: `tasks/persona-pc-eval-proposal.md`
- W0 plan/writer/strict verifier and read-only prepare-envelope verifier:
  `eval/generate_persona_corpus.py`
- bounded one-person plan API and full planned-count/resource oracle:
  `eval/generate_persona_corpus.py`, `eval/persona_full_scale_limits.py`
- W1-W5 contributor cohort allocator: `eval/persona_history_allocation.py`
- W1-W5 structural allocator: `eval/persona_structural_allocation.py`
- root-independent planned event manifest: `eval/persona_event_manifest.py`
- 20-person root-wide planned schedule: `eval/persona_suite_event_manifest.py`
- bounded per-person event shards and O(20) schedule/locator/MMR composer:
  `eval/persona_suite_event_streaming.py`
- blocked-until-readback capacity projection: `eval/persona_capacity.py`
- non-formal bounded JSONL artifact storage: `eval/persona_streaming_storage.py`
- read-only replay-root lease primitive: `eval/persona_root_lock.py`
- fail-closed Kio command/result boundary: `eval/persona_kio_runner.py`
- canonical non-executing 20-person prepare-receipt composer:
  `eval/persona_prepare_receipt.py`
- partial filesystem/content/quota semantic attestor:
  `eval/persona_history_attestation.py`
- topology/generator tests: `eval/test_persona_fixture.py`,
  `eval/test_persona_history_allocation.py`,
  `eval/test_persona_structural_allocation.py`,
  `eval/test_persona_event_manifest.py`,
  `eval/test_persona_suite_event_manifest.py`,
  `eval/test_persona_suite_event_streaming.py`,
  `eval/test_persona_root_lock.py`,
  `eval/test_generate_persona_corpus.py`

15形式のW0物理ファイル比率、20人×12 primary paths、7,000〜16,000 files/person、
75% primary / 25% common-secondary contributor負荷、W0〜W5操作集合を固定済みである。
比率の分母はW0の物理direct-child filesで、current chunk数とは別台帳にする。
Office、scan PDF、image、media、domain binaryを作成しただけでは120,000の検索可能
chunkへ数えない。

20人それぞれのOS semantics、device class、locale/language、work style、
synthetic export source、sensitivity、nesting、size/domain-binary profileは、共通の
small/medium/large/tail size-complexity bucketとともにmachine-readableな仮説metadataとして
実装済みである。ただし、それらは実ユーザー統計ではなく、
`implemented_by_renderer=false`である。現在のrendererのbytes、サイズ分布、
extension/domain-binary variants、OS動作は従来のままで、検索可能性も主張しない。

`tiny`は200 files/personとする。100 files/personではfinance-controllerの安定
contributorが19件にしかならず、20個すべてのscopeへ非ゼロchunk targetを割り当てられない。
200件なら比率を整数のまま保ちつつ、全scopeへ最低1 contributorを配置できる。

実装順は次で固定する。

1. W0のfolder/fileとphysical/logical/search-plan台帳を生成する。
2. W0をprepare/init/indexし、編集前の履歴境界とactual chunk receiptを作る。
3. mutation前にevent manifest全体をpreflightし、同じrootへW1〜W5を適用する。
4. 同一の不変manifestから3つのfresh rootへ全waveを独立replayする（`.kio`はコピーしない）。
5. 60 registries / 1,200 scopesが完成してからattest、Recall、history、latencyを測る。

W0 indexを省くと編集前のbytesが履歴にならない。これは最終評価を前倒しする手順ではなく、
履歴を成立させるための必須境界である。

現在はtiny W0 generatorに加え、contributor/structural allocatorとplanned event manifestまで
実装済みである。20人×200 files、400 scope、4,131 planned contract chunksを原子的に生成し、
2 fresh rootsのbyte同一性、inode非共有、strict no-op、改ざん拒否を検証する。400 scope中63 scopeは
深さ4以上、10人は深さ5以上、最大深さ6である。
全suiteをメモリに展開せず、1人のcanonical planを最大16,000 sources、8 MiB、
20 scopesに制限して生成・再検算するAPIと、fullの正確なcount oracleも実装済みである。
このoracleは1 replay当たり43,596 events、5,175 boundaries、48,771 schedule items、
3 replayで130,788 / 15,525 / 146,313をcanonical allocationから導出するが、
full event manifestの構築やKio実測は行わない。

構造laneはtiny/pilotで1人11 events、fullで1人30 events。full W2は20 scopesすべてへ
same-scope U renameを置き、cross-scope moveはraw-only travelerを使う。near PNGは親RGBの
1 channelだけを±1し、derived scan PDFは親PNGのdecoded pixelsをそのまま埋め込む。
source/version/materializationを分離し、restoreは削除済みpath/checkpointをsourceにして別の
既存active scopeへ新materializationを作る。final active file数はfull 195,080/replay、
3 replayで585,240である。

`pilot`/`full`はplan生成のみ可能で、物理writeはstreaming/RSS、rich-file size、pilot容量の
承認前なのでblockedである。旧raw-file bucketはfull 20人中16人でpurge quotaを運べず、
正本候補をwhole-source contributor cohort `P=4%, X=10%, Y=6%, N=4%, U=76%`へ変更した。
現行W0 planについてsource-ID allocatorを実装し、tiny/pilot/full全60 persona-profileで
person単位のexact subsetを生成・再検算できる。fullはP/X/Y/Nすべてを全20 scopesへ配置する。
scopeごとのexact割合は多数の
整数cellで不可能なので要求しない。

W5はP'をold Pと並存させてindexし、old Pを1 pathずつremove→path purgeする。これにより
1人あたり4,800 current + 4,800 historical = 9,600 version-chunksをpurgeし、最終の
120,000 current / 60,000 contributor historyへ戻す。event manifestはevents/boundaries/scheduleを
分離し、wave×scopeのordinary indexを1件へcoalesceし、W5の逐次purge順を凍結する。
suite manifestは20人の個人manifestをhashで束縛し、W1--W4の全regular→全index、W5の
全regular→全index→persona/source順purge pair→全noopを、root-wide lock 1本で実行する
単一依存鎖へする。tiny全20人は1,076 events、908 boundaries、1,984 schedule itemsである。
旧in-memory builderと別に、完全なevent manifestは一度に1人分だけ保持し、
events/boundaries/schedule projectionをbounded JSONL shardへpublishするlayerを実装した。
suite composerは20人のcompact summaryだけを持つO(20) mergeで、global schedule、
external row locator、schedule/locator bindingのMMRを構成し、20個のfull manifest objectを同時に保持しない。
tinyは旧builderの1,076 / 908 / 1,984、schedule SHA-256、suite-manifest SHA-256と完全一致する。
ただし、下位のsource-inode rename blockerを引き継ぐためすべてのartifactは
`formal_publication_attested=false`であり、fullのsupervisor実測RSS・artifact readback・`wait4`
receiptも未証明である。このstreaming実装はformal fullまたはW1〜W5の実行を許可しない。
p01/fullのCI回帰は120,000 current、60,000 history、30 structural events、20-scope W2を
一度の構築で検査する。W0 immutable verifierとpost-W0 envelope verifierは分離済みで、
後者はcanonical intent、400 `.kio`、20 `.kio-eval-device`と固定control/receipt namespaceを
外側から検証する。opaque内部はtyped checker observationなしでは明示的にunattestedであり、
history-readyを主張しない。partial semantic attestorはprofile、canonical persona/scope、
contract quota算術、file bytes/content roots、typed runtime observationを束縛できるが、
SQLite/CAS、HEAD/commit、Kio binary/config、root/prepare-intentの統合的検証ではなく、
完全な400-scope入力でも`history_ready_attested=false`のままである。
attestorは各directoryの子entryを名前またはMerkle childとして保持する前に
16,384 direct entriesのhard capを適用する。

non-executing prepare-receipt composerはcanonical all-person plan SHAを1人分ずつ
streaming再構成し、root/person/device/scopeのexact 20×20 projectionへroot binding、
binary identity、environment、init、indexの宣言SHAを束縛する。artifact本文、SQLite/CAS、
HEAD/registryは検査しないため、全semantic/history/execution/mutation claimはfalse固定である。
rootは`/`を許さず、4 KiB/64 components/255 bytes per component、person bindingは20 scopeを
走査前に要求する。

Kio runnerはstrict JSON/result validator、isolated environment recipe、binary snapshot、
unbound receipt形式まで実装した。しかしpathname検証後の`Popen(cwd=...)`には
same-user TOCTOUが残るため、`HANDLE_RELATIVE_EXECUTION_AVAILABLE`、
`PERSONA_FILESYSTEM_MUTATION_AVAILABLE`、`TRUSTED_BINARY_EXECUTION_AVAILABLE`は全てfalseであり、
init/index/version subprocessも物理mutationも許可しない。root/owner inodeへのread-only leaseと、
lease保持済みroot FDのnon-inheritable duplicateを貸すAPIは実装済みである。これにより
trusted-rootのpath-check/open seamは閉じるが、同一プロセスcheckerのFD複製・一時再束縛、
持続的なsame-inode reopenはDarwin/Linux共通のopen-description flag probeで拒否する。
ただしsame-UID ABA、immutable snapshot、process isolationは未解決である。prepare runner統合、
handle-relative safe mutation、journal、replay executorも未実装なので、W1〜W5 mutationは
引き続きfail closedである。

complete W0 semantic checkerには、HEAD/ref/commit/tree/raw/normalize/chunk CAS、strict
JSONL/task/approval/unsupported state、scope SQLite/FTS、person registryのexact 20行を
同一snapshotで検査する必要がある。Python標準`sqlite3`は既存directory FDをauthorityとして
main/WAL/SHMをcross-platformに開けず、registryのread-only openもsidecarへ書く可能性がある。
FD-bound native read-only VFSまたはwriter排除下の同一epoch immutable snapshotが入るまで、
checker-local evidenceは`semantics_attested=true`を要求しても、receiptの
`formal_transport_attested`、suite formal semantic coverage、actual chunks、history readinessは
falseのままで、legacy nine-field callbackへ変換できない。

capacity APIはcardinalityと呼出側宣言値を束縛するが、pilot measurement receiptと
destination-root availabilityの読み戻しがない限りblockedで、receiptはphysical writeを承認しない。
bounded streaming storageはcanonical JSONL shardをno-replace publish/readbackできるが、
verified source directory inodeをrenameのatomic preconditionにできないため、
`formal_publication_attested=false` / `source_directory_inode_not_bound_by_rename`のままである。
これらはformal full実測、W0 prepare、actual Kio chunk/history attestationの証拠ではない。

```bash
python3 eval/generate_persona_corpus.py plan \
  --profile tiny --plan-out /private/tmp/kio-persona-tiny-plan.json
mkdir -p /private/tmp/kio-persona-runs
python3 eval/generate_persona_corpus.py generate \
  --plan /private/tmp/kio-persona-tiny-plan.json \
  --out /private/tmp/kio-persona-runs/replay-01 \
  --replay-id replay-01
```

```bash
python3 -m unittest \
  eval.test_persona_fixture \
  eval.test_persona_person_plan \
  eval.test_persona_full_scale_limits \
  eval.test_persona_allocation \
  eval.test_persona_history_allocation \
  eval.test_persona_structural_allocation \
  eval.test_persona_event_manifest \
  eval.test_persona_suite_event_manifest \
  eval.test_persona_suite_event_streaming \
  eval.test_persona_capacity \
  eval.test_persona_storage \
  eval.test_persona_streaming_storage \
  eval.test_persona_root_lock \
  eval.test_persona_kio_runner \
  eval.test_persona_prepare_receipt \
  eval.test_persona_history_attestation \
  eval.test_persona_renderers \
  eval.test_persona_manifest \
  eval.test_generate_persona_corpus \
  eval.test_eval_env

KIO_RUN_PERSONA_FS_INTEGRATION=1 \
  python3 -m unittest eval.test_generate_persona_corpus
```
