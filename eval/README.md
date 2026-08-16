# Kio 検索評価ハーネス (synthetic)

`docs/09-mvp-scope.md` §4.3 の **Recall 評価規約 (ゴールデンクエリ)** を実行するための
合成コーパス + 履歴シナリオ + ゴールデンクエリ + 評価ランナー。設計宿題 #5
(`docs/09-mvp-scope.md` §5.5、**Step 3 着手前ゲート**) の成果物。

- Push/PR 評価経路は **Rust-only**。残る Python は
  `eval/python-exceptions.toml` と exact-match する manual な
  Python-native ML/SDK/render adapter だけであり、この synthetic lane では実行しない。
- 決定論: 凍結済み `corpus-fixture.json` を Rust generator が materialize する。2 回実行で byte 同一。
- 通常評価は Rust の `kio-eval` と評価対象の `kio` を使う。
  `cargo build --release --locked --all-features` 済み前提。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `corpus-fixture.json` | **生成物の凍結正本**。305 文書の bytes と manifest を保持し、Rust `kio-eval generate-corpus` が検証して materialize する |
| `history-plan.json` | version・Rust generator identity・corpus manifest digestを固定した JCS+LF の closed operation plan。Rust 実装はバンドルした digest と完全一致するplanだけを受理 |
| `kio-eval replay-history` | retained capabilityと隔離device上で、各 scope の `init → offline index → manual snapshot → edit/rename/delete` を決定論再現。48 commitとstrict log evidenceを検証後にmanifestをcreate-only公開 |
| `golden-queries.jsonl` | ゴールデンクエリ (M3-1 / M3-2 / M3-3 各 16+ 件)。**リポジトリ保持の正本** |
| `history-manifest.json` | `kio-eval replay-history/v1` のstrictな出力fixture。plan/corpus digestと、scope別step/message/commit数の実行証拠だけを保持。操作materialの正本は`history-plan.json`に一本化 |
| `golden-queries-crossscope.jsonl` | **横断増補 16 問** (09 §4.3、2026-07-26 凍結)。expected が必ず 2 scope に跨る。正解担体は既存 anchor そのもので、コーパスには手を入れていない |
| `kio-eval crossscope` | 横断増補のRust専用ランナー。full evaluatorのセット全体ゲートを部分集合へ誤適用せず、Recall/latency/Evidenceと診断値`worst_expected_rank`を検証する |
| `crossscope-results.json` | 現行の replica 単独経路で再生成した横断評価結果。per-query の `aggregator` や `aggregator_applied` は出力せず、`counts` に `worst_expected_rank_mean/max` を記録する |
| `crossscope-results-no-replica-2026-07-26.json` | 2026-07-26 の比較対照を保存した**履歴成果物**。移行前 schema の `aggregator_applied` を意図的に含むが、現行 runner の出力や入力には用いない |
| `kio-eval rerank dump --dataset synthetic` | current-tree queryの候補順・3要素key・検証済みChunk CAS textをcreate-only JSONへ固定するRust経路。offline GPU差分のpass 1 |
| `golden-queries-qhard.jsonl` | 実データの raster PDF / 図表・画像を正解担体にする、凍結済み Q_hard 8 問。digest も Rust runner が固定照合する |
| `kio-eval benchmark qhard` | attest済み外部fixtureとsynthetic M3-1を同一実行で再測定する唯一のQ_hard判定経路 |
| `golden-queries-fixture-b.jsonl` | baseline 比較専用の別凍結母集団（24問、hard1/2/3 各8、sha256:bdad3e02c4b70f721e882d7f24c8b5b442621be7c0c03593afde41b8ebca7d45） |
| `kio-eval benchmark baseline` | attest済みfixture-BをSpotlight/rgaと比較する唯一のbaseline判定経路 |
| `kio-eval scale generate` | Rust v2 の決定論的性能 fixture 正本。20 scope と tiny/full の形を固定し、owner marker を含めて materialize する |
| `kio-eval scale prepare` | 各 leaf scope を `init → offline index` し、隔離 registry と Rust prepare report を公開する |
| `kio-eval scale attest` | manifest・HEAD・現行 chunk config・SQLite/FTS・registry binding を独立に照合し、create-only attestation を公開する |
| `kio-eval scale benchmark` | attestation 済み v2 fixture だけを測定し、manifest/prepare/attestation/binary と実測前後の状態を report に束縛する |

## 使い方

コーパス本体は再生成可能なため **リポジトリにコミットしない** (一時ディレクトリへ生成する)。

```bash
# 0. バイナリ (未ビルドなら)
cargo build --release --locked --all-features

# 1. 合成コーパス生成
target/release/kio-eval generate-corpus --out /tmp/kio-eval-corpus

# 2. Rust履歴シナリオ再現 (single-link binary copyを使い、manifestはcorpus直下へcreate-only公開)
install -m 0755 target/release/kio /tmp/kio-replay-kio
target/release/kio-eval replay-history \
  --corpus /tmp/kio-eval-corpus --bin /tmp/kio-replay-kio

# 3c. 横断増補 (別ファイル・Rust専用ランナー、09 §4.3)。既存 50 問とは独立に走る
target/release/kio-eval crossscope --corpus /tmp/kio-eval-corpus --bin target/release/kio --dry-run --out /tmp/crossscope-unused.json
target/release/kio-eval crossscope --corpus /tmp/kio-eval-corpus --bin target/release/kio --out /tmp/crossscope-results.json

# 3a. dry-run: Rust の正本 evaluator が golden-queries / manifest を検証する
target/release/kio-eval --dry-run --corpus /tmp/kio-eval-corpus

# 3b. 本評価: Rust の正本 evaluator が Recall@10 をシナリオ別に集計。
#     kio search 未実装の間は全クエリ NOT-IMPLEMENTED → exit 2 (未実装を green にしない)。
target/release/kio-eval --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 3c. シナリオ絞り込み (複数指定可)。最終HEADのCIは3シナリオを個別に実行する。
target/release/kio-eval --scenario M3-1 --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 4. offline rerankerへ渡すcurrent-tree候補を、検証済みChunk CASから固定する。
#    --outは既存fileを上書きしない。
target/release/kio-eval rerank dump --dataset synthetic \
  --corpus /tmp/kio-eval-corpus \
  --bin target/release/kio --out /tmp/rerank-input.json

# 5. GPU が返した JSON を固定dumpへ適用する。--report もcreate-only。
target/release/kio-eval rerank apply --input /tmp/rerank-input.json \
  --output /tmp/rerank-output.json --report /tmp/rerank-report.json
```

`replay-history` は、既に open した executable と HOME/XDG directory を pathname
再解決なしで child process へ渡せる Linux だけで実行する。macOS/Windows では
descriptor-exec 相当の安全な境界がないため、corpus を変更する前に structured error で
fail-closed にする。`--bin` はsingle-link regular executableに限定し、Cargoが
`target/release/kio`を`deps/`とhardlinkした環境では、`install -m 0755`で`/tmp`へ
single-link copyを作ってそのpathを渡す。pathname fallbackやhardlink例外は設けない。

`crossscope` と `rerank dump` の出力は measured corpus 外の既存directoryに置き、
既存fileを上書きしない。再測定は新しい出力名を使い、比較後に採用するartifactだけを
明示的に更新する。

### exit コード (docs/09 §4.3, 2026-07-03 J2 裁定)

| 状況 | exit | 扱い |
| --- | --- | --- |
| 全シナリオ (対象) が Recall@10 >= 0.8 | `0` | PASS |
| `KIO-E-*-NOT-IMPLEMENTED*` 系のクエリが 1 件以上 | `2` | 未実装。Recall 判定は無効 (green にしない) |
| Recall 未達 / 実行失敗 (非 0 かつ非 3 exit・不正レスポンス・解決不能) | `1` | FAIL。当該クエリは recall 0 として集計に残す |

exit `3` (部分成功) は stdout の JSON を採点対象にする (実装後の部分成功や実バグを未実装で握り潰さない)。

## Q_hard の外部 fixture 計測

Q_hard は raster PDF / PPTX 図表 / 画像を正解担体とするため、合成 corpus とは別の
**明示的に attest された外部 fixture** でのみ計測する。fixture がない、attestation が
ない、または tree / environment / golden digest / scope 一覧が一致しない場合、
`kio-eval benchmark qhard` は失敗する。checked-in の `qhard-results.json` は歴史成果物であり、
入力にも Done 判定にも用いない。

```bash
target/release/kio-eval benchmark qhard \
  --fixture-root /private/tmp/kio-fixture-run \
  --tree qhard --env-name qhard \
  --attestation /private/tmp/kio-fixture-run/qhard-attestation.json \
  --bin target/release/kio --out /tmp/kio-qhard.json
```

attestation は strict JSON の `{schema_version:1, fixture_id:"kio-qhard-v1", tree,
env_name, golden_sha256, fixture_content_sha256, scopes}` である。`fixture_content_sha256` は
fixture root の regular files/directories を名前・型・content digest で順序付きに列挙して
hash した値で、root の `qhard-attestation.json` 自身は除外する（自己参照を避ける）。`scopes` は fixture root からの正規化相対 path
で、実際に見つかる `.kio` scope と完全一致しなければならない。探索は symlink を辿らず、
directory / scope 数に上限を設ける。検索 subprocess は fixture XDG state だけを使う。
`--online-query` 時だけ `GEMINI_API_KEY` / `MISTRAL_API_KEY` を名前指定で転送し、値は report
に出力しない。

`--synthetic-corpus <generated-corpus>` を添えると、同じ `kio-eval` 呼出し内で frozen
synthetic M3-1 18 問を再測定し、Q_hard 8 問と合算した 26 問 / 21 hit gate を report に
記録する。外部の結果 artifact は受け付けない。指定なしの Q_hard-only 実行は evidence-only
であり、acceptance success にはならない。

## fixture-B baseline 比較

fixture-B の24問は Q_hard 8問 + synthetic M3-1 18問の26/21 gateとは別の、Spotlight/rga
比較だけの凍結母集団である。まず `.kio` を除く indexed/pristine source が p01..p20 で等価な
ことを安全に束縛し、その attestation を測定に渡す。

```bash
target/release/kio-eval benchmark baseline-attest \
  --fixture-root /private/tmp/kio-fixture-run --baseline-corpus /path/to/pristine \
  --out /tmp/kio-fixture-b-attestation.json
target/release/kio-eval benchmark baseline \
  --fixture-root /private/tmp/kio-fixture-run --baseline-corpus /path/to/pristine \
  --attestation /tmp/kio-fixture-b-attestation.json --bin target/release/kio \
  --comparator-runtime /Library/KioComparatorRuntime/v1 --out /tmp/kio-baseline.json
```

Rust 以外のbaseline runnerは保持しない。歴史的 JSON は証拠ではなく、新たな合格計測を成立させない。
`mdfind` または `rga` が無ければ `blocked-unmeasured` であり、pass にはならない。
baseline report の `configuration` は `online_query` と、Kio subprocess に実際に転送した
credential の**環境変数名だけ**を `forwarded_credential_names` として記録する。値は report に
書き出さない。`--online-query` を指定しない限りこの配列は空である。比較器欠落などで Kio lane
の起動前に block された場合は credential を転送していないため配列は空のままとし、
`online_query` だけで online mode の要求を監査可能にする。

### macOS 比較器 runtime の管理者構築

正式 baseline 用 runtime は既存の Homebrew tree を変更せず、専用 read-only image として一度だけ構築する。
管理者実行前に script digest を照合する。この revision の digest は
`d1413269957a3cad2836f4d159fbc47fb3bbd4224fee1dbb72b29400bc1efe85` である。

builder は固定された `/usr/local/bin/kio-eval` を root-owned、group/other 非 writable、かつ extended ACL なしとして要求する。
先に監査済み release binary をこの場所へ provision してから、checkout の script を root-private copy にして
一度だけ実行する。`build` / `verify` 引数は存在しない。

```bash
sudo /usr/bin/install -o root -g wheel -m 0755 target/release/kio-eval /usr/local/bin/kio-eval
readonly admin_dir=$(sudo /usr/bin/mktemp -d /private/tmp/kio-comparator-runtime-v1-admin.XXXXXX)
sudo /bin/chmod 0700 "$admin_dir"
sudo /usr/bin/install -o root -g wheel -m 0500 \
  /absolute/path/to/kio/eval/build_macos_comparator_runtime.sh "$admin_dir/build-script"
sudo /bin/zsh -f "$admin_dir/build-script"
```

Rust が reviewed pin の nofollow copy、Mach-O closure/rewrite、payload re-walk、固定 config、mount admission、
DMG/manifest ACL・xattr policy、digest と create-only manifest publication を fail-closed で行う。DMG は
`FinderInfo`/`provenance` だけを許容し、attach が生成する `com.apple.diskimages.recentcksum` だけを削除してから
hash へ束縛する。runtime/manifest は `provenance` 以外の xattr と extended ACL を拒否する。

対象の `/Library/KioComparatorRuntime/v1`、image、manifest、一時 build root のいずれかが既に存在すれば停止する。
成功後に廃止する場合も、detach、image/manifest の削除、空ディレクトリの `rmdir` に限定する。

比較器プロセスは retained descriptor に束縛した pristine persona directory を CWD とし、相対 `.` を
入力に使うため、可変な public corpus path を再オープンしない。`kio` は検査済み regular executable
の private snapshot に束縛する。`rga` lane は、ユーザー所有の Homebrew tree を比較器 runtime として
受け付けない。代わりに `--comparator-runtime` で、管理者が提供した専用の **canonical absolute** runtime root を
明示する。root とその path component、runtime 内の file/directory、runtime 内 symlink の最終 target はすべて
root 所有かつ group/other 非書込みで、symlink target は root の外へ出てはならない。root には少なくとも次を
含める。

```text
bin/rga
bin/rga-preproc
bin/pandoc
bin/pdftotext
bin/rg
config/rga-config.json
```

macOS では evaluator が固定された sealed system `otool` を使って、この5 executable の Mach-O load command
closure を再帰的に解決する。`@loader_path`、`@executable_path`、`@rpath`、runtime 内 symlink を解決した後、
すべての runtime image が当該 root 内に残ることを要求する。terminal として許す root 外 dependency は、
root 所有・非書込みで再確認した `/usr/lib` または `/System/Library` 下の macOS sealed-system library、
または Apple-signed `dyld_info` の strict catalog で UUID と全依存 edge を束縛した dyld shared-cache image
だけである。catalog の形式不整合、途中切断、未解決 edge は fail-closed にする。ただし catalog と sealed
filesystem の双方に存在しない edge は、dyld が明示する `weak-link` に限って不在を許可し、親 image の
edge に加えて `missing_weak_dylibs` として closure provenance へ記録する。通常 link、`delay-init` 単独、
未知 attribute、または NotFound 以外の検査失敗は引き続き fail-closed である。不在 weak image が後から
catalog または filesystem に現れた場合は closure digest が変化し、計測を block する。
実行ファイルの dynamic loader は sealed `/usr/lib/dyld` のみ、`LC_DYLD_ENVIRONMENT` は禁止する。
未解決の `@rpath`、runtime 外への escape、非sealed component、closure の変更は fail-closed にする。
report は runtime root、固定 inspector、各 closure image の canonical path・trust class・SHA-256 と closure digest を
記録する。従って runtime verification failure や comparator 欠落は `blocked-unmeasured` であり、pass にはならない。
各 rga subprocess の実行前後と計測 finalization では load command から closure を再帰的に再解決し、初期 binding の
canonical path・trust class・SHA-256・closure digest と完全一致させる。途中で高優先度の `@rpath` 候補が追加された場合を
含め、entry の追加・削除、解決先または内容の変化は `blocked-unmeasured` とする。
runtime root は macOS `MNT_RDONLY` の read-only mount でなければならない。bind時、各 rga subprocess の直前・直後、
計測 finalization で public canonical path と retained root descriptor の mount identity を再確認し、writable filesystem、
unmount/remount、mount replacement、または確認不能は `blocked-unmeasured` とする。report には canonical runtime path、
read-only 判定、filesystem ID・mount point・mount source・filesystem type・flags、および closure digest を保存する。
`config/rga-config.json` は `{"custom_adapters":[]}` だけを含む root-owned sealed regular file とし、rga の
ユーザー設定・任意 custom adapter を取り込ませない。helper lookup の `PATH` も private temporary directory ではなく
sealed runtime の `bin/` だけに固定する。

macOS の `mdfind` はコピー実行を許さない system tool のため、例外として
正確な `/usr/bin/mdfind` のみを直接実行する。その場合も capability preflight、実体 digest の束縛、および
各 query 後の再照合を必須にする。比較器の欠落・preflight failure・予期しない `mdfind` failure、または
`rga` の 0/1 以外の終了は、miss として margin を有利にせず測定を block する。

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
   現行内容は`corpus-manifest.json`、履歴操作対象は凍結`history-plan.json`の
   `sections[]`が`{slug: ニーモニック, heading: 実見出し}`を持つ。
   `history-manifest.json`は操作materialを重複保持せず、実行証拠だけを記録する。
   例: `"recall"` → 見出し `"回収率と精度"`。
2. **heading → section_id** … `docs/04-pipeline.md §4.1` の slug 規則で `slugify(heading)`。
   例: `slugify("回収率と精度")` = `"回収率と精度"` (日本語は保持。英語ニーモニックとは一致しない)。
   これが J2 の核心: `"recall"` を実 `section_id` として突き合わせると必ずミスする。
3. **{scope, file} → raw_hash** … 現行内容は`corpus-manifest.json`、M3-2
   (編集/リネーム) / M3-3 (削除) の旧内容は`history-plan.json`が記録する
   `before_raw_sha256`から`raw_hash = "sha256:" + digest`を得る。

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
- 凍結 corpus fixture (`corpus-fixture.json`) と履歴シナリオも同様に凍結対象。変更は Recall 数値の連続性を壊すため、
  Step 3 着手後は原則行わない。

## 決定論の検証

```bash
target/release/kio-eval generate-corpus --out /tmp/c1
target/release/kio-eval generate-corpus --out /tmp/c2
diff -r /tmp/c1 /tmp/c2   # 差分なし (byte 同一) であること
```

`history-manifest.json` の plan/corpus digestとscope別step/message/commit数も、別のフレッシュ
コーパスに Rust replay すれば byte 同一になる。edit/rename/delete materialは凍結
`history-plan.json`だけが保持し、manifestへ重複させない。commit hash / timestamp は非決定なので
manifestに含めない。同じcorpusでの2回目実行は、半端な履歴へ追記せずfail-closedに拒否する。

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
target/release/kio-eval scale generate \
  --out /tmp/kio-scale-tiny --profile tiny
target/release/kio-eval scale prepare \
  --corpus /tmp/kio-scale-tiny --bin target/release/kio
target/release/kio-eval scale attest --corpus /tmp/kio-scale-tiny
target/release/kio-eval scale benchmark \
  --corpus /tmp/kio-scale-tiny --bin target/release/kio \
  --warmups 1 --samples 1 --out /tmp/kio-scale-tiny.benchmark.json

# 本番規模 (20 scopes / 4,000 files / 120,000 chunks): 手動性能計測時のみ
target/release/kio-eval scale generate \
  --out /tmp/kio-scale-full --profile full
target/release/kio-eval scale prepare \
  --corpus /tmp/kio-scale-full --bin target/release/kio

# 任意時点で再検証 (read-only SQLite attestation)
target/release/kio-eval scale attest --corpus /tmp/kio-scale-full

# Rust measurement lane: full だけが acceptance eligible。5 warmup + 100 samples
# の M3-1 `search.latency_ms` p95 を判定に使う。--out は corpus 外の既存実体
# directory にだけ原子的に書き出せる。
cargo run -p kio-eval -- scale benchmark \
  --corpus /tmp/kio-scale-full --bin target/release/kio \
  --warmups 5 --samples 100 --out /tmp/kio-scale-full.latency.json
```

`kio-eval scale prepare` は各 scope を明示的な `kio index --offline --yes` で終える。`index` 自体が snapshot と
HEAD tree projection を公開するので、その直後に別の `kio snapshot create` を追加してはならない。
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

Rust の `kio-eval scale benchmark` は release binary・manifest・保存済みと実測前後の live attestation・platformをreportへ束縛し、
各検索で既定の全scope選択、attested 20 scopes の成功、期待文書の上位10件入りを確認する。検索modeも
明示指定せず、既定 `auto` が `embedding_endpoint_not_configured` により `text` へfallbackしたことを検証する。
主指標は各検索が1行だけ追記する `KIO-M-SEARCH-001 search.latency_ms`、独立した上限guardはrunner計測のprocess wall timeで、
両方の生標本とp50/p95/p99を保存する。full の acceptance は M3-1 の `< 5秒` と
M3-2/M3-3 の `< 7秒` を全て判定する（tiny は pass fields を出さない）。M3-1の `< 5秒` 判定は
**high-selectivity default-auto current-text baseline** であり、広いqueryやhybridを含む正式なMVP性能gateではない。M3-2
(`--all-history`) とM3-3 (`--include-deleted`) も同じ標本数で実行するが、このfixtureは単一HEADで
編集・rename・deleteを含まないため、結果は **execution-path-only** であり、履歴データの品質・母集団の
代表性を示す正式な履歴性能値ではない。ただし selected execution path に対する full Scale の合否契約には、
両シナリオの `< 7秒` p95 を含める。

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
cargo test -p kio-eval --all-targets --locked
```

## 20人の独立 persona-PC fixture（Rust-only contract）

persona-PC suite の唯一の semantic authority は Rust の canonical artifacts である。
`plan` は persona、Rust scope ID、home path、allocation、source identity を固定し、
`schedule` と `render` は同一 plan に束縛された deterministic projection である。Python
に semantic parser、generator、renderer、materializer、scaffold、prepare/replay runner はない。

```bash
target/release/kio-eval persona plan --profile tiny \
  --out /private/tmp/kio-persona-tiny-plan.json
target/release/kio-eval persona schedule \
  --plan /private/tmp/kio-persona-tiny-plan.json \
  --out /private/tmp/kio-persona-tiny-schedule.json
target/release/kio-eval persona render \
  --plan /private/tmp/kio-persona-tiny-plan.json \
  --out /private/tmp/kio-persona-tiny-render.json
target/release/kio-eval persona materialize \
  --plan /private/tmp/kio-persona-tiny-plan.json \
  --schedule /private/tmp/kio-persona-tiny-schedule.json \
  --render /private/tmp/kio-persona-tiny-render.json \
  --destination /private/tmp/kio-persona-artifacts --replay-id replay-01
target/release/kio-eval persona scaffold \
  --plan /private/tmp/kio-persona-tiny-plan.json \
  --root /private/tmp/kio-persona-workspaces
```

Both Rust publication commands are create-only. Materialization publishes only
the three canonical artifacts and `persona-materialization.json`; scaffold
publishes workspace topology and `persona-workspace-owner.json`. A plan profile
is planning/materialization evidence only: it is not Kio prepare/index/replay,
chunk, history-readiness, or performance evidence.

Writer coordination and filesystem observation are Rust-only. Acquire the
parent lease, acquire and release each plan-owned scope lease, release the
parent lease, then publish a create-only attestation. Scope calls use the Rust
scope ID, never a home path; the CLI derives all record bindings itself and
accepts no caller-supplied owner or materialization digest:

```bash
kio-eval persona lease scope claim \
  --root /private/tmp/kio-persona-workspaces --persona p01 \
  --scope-id <rust-scope-id> \
  --parent-session parent-01 --worker-session worker-01
kio-eval persona attest \
  --root /private/tmp/kio-persona-artifacts \
  --out /private/tmp/kio-persona-attestation.json
```

`persona attest` is a bounded Rust filesystem observation of the exact
materialized artifacts. It explicitly reports no actual Kio evidence and no
history readiness; it neither establishes replay nor search success.

Push/PR CI は Python を起動しない。tracked Python の閉包は Rust の例外台帳 test が
検証し、manual adapter 自身はネットワーク・GPU・課金なしの通常 CI から除外する。
