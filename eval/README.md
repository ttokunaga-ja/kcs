# Kio 検索評価ハーネス (synthetic)

`docs/09-mvp-scope.md` §4.3 の **Recall 評価規約 (ゴールデンクエリ)** を実行するための
合成コーパス + 履歴シナリオ + ゴールデンクエリ + 評価ランナー。設計宿題 #5
(`docs/09-mvp-scope.md` §5.5、**Step 3 着手前ゲート**) の成果物。

- Python 補助スクリプトの依存: **Python3 標準ライブラリのみ** (追加インストール不要)。
- 決定論: 凍結済み `corpus-fixture.json` を Rust generator が materialize する。2 回実行で byte 同一。
- 通常評価は Rust の `kio-eval` と評価対象の `kio` を使う。
  `cargo build --release --locked --all-features` 済み前提。

## ファイル構成

| ファイル | 役割 |
| --- | --- |
| `corpus-fixture.json` | **生成物の凍結正本**。305 文書の bytes と manifest を保持し、Rust `kio-eval generate-corpus` が検証して materialize する |
| `corpus_spec.py` | Python replay/oracle 用の薄い metadata view。fixture と checked-in `history-manifest.json` を読むだけで、文書を render しない |
| `generate_corpus.py` | 旧 CLI 互換 shim。`kio-eval generate-corpus` を exec するだけで、Python/Cargo fallback は持たない |
| `replay_history.py` | 各 scope で `init → index → snapshot → 編集 → snapshot → リネーム → snapshot → 削除 → snapshot` を決定論再現。`history-manifest.json` を出力 |
| `golden-queries.jsonl` | ゴールデンクエリ (M3-1 / M3-2 / M3-3 各 16+ 件)。**リポジトリ保持の正本** |
| `history-manifest.json` | replay がリネーム/編集/削除したファイルの記録 (`replay_history.py` が生成) |
| `run_eval.py` | 互換 CLI shim。リポジトリ内の Rust `kio-eval` をそのまま起動する。評価・report・exit code の正本は Rust であり、Python へ暗黙に fallback しない。`KIO_EVAL_BIN` で明示的に evaluator binary を差し替えられる |
| `python_eval_oracle.py` | Python の独立 differential/security oracle。共有 golden vectors、pointer CAS attestation、crossscope/reranker の限定的な補助だけを持つ。通常の full evaluator・履歴ゲート・report 生成は持たない |
| `golden-queries-crossscope.jsonl` | **横断増補 16 問** (09 §4.3、2026-07-26 凍結)。expected が必ず 2 scope に跨る。正解担体は既存 anchor そのもので、コーパスには手を入れていない |
| `run_crossscope.py` | 横断増補の専用ランナー。`python_eval_oracle.py` の限定的な補助を明示利用する。full Rust evaluator のセット全体ゲートは部分集合に当てられないため別立て。診断値 `worst_expected_rank` を併記する |
| `crossscope-results.json` | 現行の replica 単独経路で再生成した横断評価結果。per-query の `aggregator` や `aggregator_applied` は出力せず、`counts` に `worst_expected_rank_mean/max` を記録する |
| `crossscope-results-no-replica-2026-07-26.json` | 2026-07-26 の比較対照を保存した**履歴成果物**。移行前 schema の `aggregator_applied` を意図的に含むが、現行 runner の出力や入力には用いない |
| `test_run_eval.py` | Python oracle の独立テストと Rust evaluator/generator shim の透過転送テスト。`python3 -m unittest eval.test_run_eval` |
| `golden-queries-qhard.jsonl` | 実データの raster PDF / 図表・画像を正解担体にする、凍結済み Q_hard 8 問。digest も Rust runner が固定照合する |
| `run_qhard.py` | 歴史的な専用 runner。現在の Done 判定用の新規計測には使わない |
| `golden-queries-fixture-b.jsonl` | baseline 比較専用の別凍結母集団（24問、hard1/2/3 各8、sha256:bdad3e02c4b70f721e882d7f24c8b5b442621be7c0c03593afde41b8ebca7d45） |
| `run_baseline.py` | 歴史的/reference runner。新規の baseline 判定は Rust `kio-eval benchmark baseline` が正本 |
| `test_run_crossscope.py` | 横断評価の生成物 schema（replica 専用、`worst_expected_rank` 集計、UTF-8/LF）を検証する単体テスト。`python3 -m unittest eval.test_run_crossscope` |
| `scale_fixture_spec.py` | Recall corpus とは独立した性能 fixture の正本。20 scope と tiny/full の形を固定 |
| `generate_scale_corpus.py` | owner marker 付きで 20 scope の性能 corpus を決定論生成。full は 4,000 files / 120,000 expected chunks |
| `prepare_scale_corpus.py` | 各 leaf scope を `init → index` し、隔離 registry と SQLite attestation を作成 |
| `attest_scale_corpus.py` | HEAD・現行 chunk config・FTS coverage を照合し、検索可能 chunk の正確な総数を証明 |
| `run_scale_eval.py` | Rust lane 移行前の legacy/reference 実装。fixture 生成・attestation 契約の参照用であり、新規の性能判定の正本ではない |
| `test_scale_*.py`, `test_run_scale_eval.py` | 性能 fixture の形、所有権、排他、bounded read、registry 復旧、計測契約の単体テスト |

## 使い方

コーパス本体は再生成可能なため **リポジトリにコミットしない** (一時ディレクトリへ生成する)。

```bash
# 0. バイナリ (未ビルドなら)
cargo build --release --locked --all-features

# 1. 合成コーパス生成 (Rust 正本。Python entry point は互換 shim)
python3 eval/generate_corpus.py --out /tmp/kio-eval-corpus
# 直接実行する場合: target/release/kio-eval generate-corpus --out /tmp/kio-eval-corpus

# 2. 履歴シナリオ再現 (kio init/index/snapshot を実行し history-manifest.json を更新)
python3 eval/replay_history.py --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 3c. 横断増補 (別ファイル・専用ランナー、09 §4.3)。既存 50 問とは独立に走る
python3 eval/run_crossscope.py --corpus /tmp/kio-eval-corpus --bin target/release/kio --dry-run
python3 eval/run_crossscope.py --corpus /tmp/kio-eval-corpus --bin target/release/kio

# 3a. dry-run: Rust の正本 evaluator が golden-queries / manifest を検証する
python3 eval/run_eval.py --dry-run --corpus /tmp/kio-eval-corpus

# 3b. 本評価: Rust の正本 evaluator が Recall@10 をシナリオ別に集計。
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

Rust が計測の正本である。legacy の `run_baseline.py` は参照用に残すが、歴史的 JSON は証拠ではなく
新たな合格計測を成立させない。`mdfind` または `rga` が無ければ `blocked-unmeasured` であり、pass にはならない。

### macOS 比較器 runtime の管理者構築

正式 baseline 用の runtime は、既存の Homebrew tree を変更せず、専用の read-only image として
構築する。checkout 内の script を直接 root 実行してはならない。通常ユーザーがまず commit/worktree の
hash を記録し、管理者が同じ値を独立に照合してから、root-owned 固定コピーを install する。スクリプト
自身は `sudo` を呼ばず、パスワードを読まない。下の SHA-256 はこの revision の script 用であり、更新時は
必ず再記録・再照合する。

```bash
/usr/bin/shasum -a 256 /absolute/path/to/kio/eval/build_macos_comparator_runtime.sh
# Expected for this revision: 4293ef620d2d8ed7cb294bc1dca000e8b552780fde91686bb2c41c97cc0681c7
readonly admin_dir=$(sudo /usr/bin/mktemp -d /private/tmp/kio-comparator-runtime-v1-admin.XXXXXX)
sudo /bin/chmod 0700 "$admin_dir"
sudo /usr/bin/install -o root -g wheel -m 0500 \
  /absolute/path/to/kio/eval/build_macos_comparator_runtime.sh "$admin_dir/build-script"
sudo /bin/chmod -N "$admin_dir" "$admin_dir/build-script"
sudo /usr/bin/env -i HOME=/var/root PATH=/usr/bin:/bin:/usr/sbin:/sbin \
  /bin/zsh -fc 'readonly admin_dir="$1" script="$1/build-script"
    cleanup() { /bin/rm -f "$script"; /bin/rmdir "$admin_dir"; }
    trap cleanup EXIT
    readonly expected=4293ef620d2d8ed7cb294bc1dca000e8b552780fde91686bb2c41c97cc0681c7
    readonly actual=$(/usr/bin/shasum -a 256 "$script")
    [[ "$actual" == "$expected  $script" ]] || { print -u2 -- "fixed script digest mismatch"; exit 1; }
    /bin/zsh -f "$script" build
    exit $?' build-runtime "$admin_dir" &&
/absolute/path/to/kio/eval/build_macos_comparator_runtime.sh verify
```

過去のbuilder失敗で`/Library/KioComparatorRuntime`だけが残った場合、builderは既存targetを
上書きしない。`v1`、image、manifestが存在せず、管理rootが空でroot所有であることを読み取り確認した後に限り、
`sudo /bin/rmdir /Library/KioComparatorRuntime`で空ディレクトリだけを除去して再実行する。
再帰削除は使わない。

macOS は通常ユーザーの checkout から `install` した固定コピーや新規作成物へ、SIP下で除去できない
`com.apple.provenance` を付与することがある。SIPや他のsecurity controlは変更しない。builderと正式 evaluatorは
xattr列挙失敗をfail-closedとし、属性が無い場合または名前が正確に`com.apple.provenance`だけの場合に限り受理する。
値は実行・path解決に使わず、その他のxattr（`com.apple.quarantine`を含む）は拒否する。管理者固定コピー、
staging、image/manifest、mounted runtimeの全treeで同じpolicyを確認し、manifest/reportにはpolicyを記録する。
ACLは上の`chmod -N`でroot-private固定コピーだけを正規化し、checkoutやHomebrew sourceには触れない。
build script自身はownership、mode、ACL、xattr policy、およびSHA-256を再検証し、不一致なら実行前に停止する。

対象は `/Library/KioComparatorRuntime/v1`、image は
`/Library/KioComparatorRuntime/v1.dmg`、一時 build directory は
`/private/tmp/kio-comparator-runtime-v1-build` に固定される。いずれかが既に存在すれば上書きせず停止する。
`/opt/homebrew` は読み取り専用の入力としてだけ利用し、`rga`、`rga-preproc`、`pandoc`、`pdftotext`、
`rg` と再帰的な非 system Mach-O closure を staging へ複製する。load command は
runtime 内の `@rpath` と `@loader_path` に再束縛され、解決不能、外部 escape、basename collision、
runtime 外 rpath は fail-closed
である。UDRO case-sensitive APFS image を read-only mount してから、canonical path、root ownership、
mode、ACL、限定xattr policy、symlink 不在、payload/source digest、固定 config bytes を静的検証し、
`/Library/KioComparatorRuntime/v1.manifest.json` に記録する。

失敗時は、その invocation が作成した固定 target だけを rollback する。成功後に version を廃止する
場合の手順は script が表示する `hdiutil detach`、image/manifest の削除、空の mountpoint/managed root の
`rmdir` に限定する。既存の `v1` を上書きして更新することはない。

構築後の tool smoke は root で実行してはならない。上の `&&` により、管理者 build が成功した場合だけ
通常ユーザーの `verify` へ進む。`verify` 自身も runtime の必須 file、固定 config、canonical mount point、
retained descriptor と一致する mount identity、および `MNT_RDONLY` を tool 起動前に検証する。これは限定的な
smoke であり、5 executable と PDF/DOCX adapter の helper lookup を sealed runtime の `bin/` だけで
実行する。rga 0.10.10 の PDF adapter は `--rga-no-cache` では失敗するため、verify と正式 evaluator は
ambient cache ではなく evaluator 所有の一時 0700 cache を明示する。smoke は baseline evaluator の
authoritative preflight を置き換えない。

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
だけである。catalog の形式不整合、途中切断、未解決 edge は fail-closed にする。
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
- 凍結 corpus fixture (`corpus-fixture.json`) と履歴シナリオも同様に凍結対象。変更は Recall 数値の連続性を壊すため、
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

# Rust measurement lane: full だけが acceptance eligible。5 warmup + 100 samples
# の M3-1 `search.latency_ms` p95 を判定に使う。--out は corpus 外の既存実体
# directory にだけ原子的に書き出せる。
cargo run -p kio-eval -- benchmark scale \
  --corpus /tmp/kio-scale-full --bin target/release/kio \
  --warmups 5 --samples 100 --out /tmp/kio-scale-full.latency.json
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

Rust の `kio-eval benchmark scale` は release binary・manifest・保存済みと実測前後の live attestation・platformをreportへ束縛し、
各検索で既定の全scope選択、attested 20 scopes の成功、期待文書の上位10件入りを確認する。検索modeも
明示指定せず、既定 `auto` が `embedding_endpoint_not_configured` により `text` へfallbackしたことを検証する。
主指標は各検索が1行だけ追記する `KIO-M-SEARCH-001 search.latency_ms`、副指標はrunner計測のprocess wall timeで、
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
