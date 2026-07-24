# 探索型 4 エンジン監査 (第 9 ラウンド) の裁定 (2026-07-05、main = 97eff37)

4 エンジン (Claude-Opus / Claude-Sonnet / GPT-5.5 / GPT-5.3-Codex-Spark) + オーケストレータ自身の
独立検証で探索。HEAD=97eff37・**全 327 テスト green** に対して実施。焦点は R9 ヒント
「パス/ファイル名の照合 / task lifecycle (Partial 等) / リソース残留 / Agent JSON 契約」。
新規 **8 件** (5 major + 3 minor)。既知 (K/L/M/N/O/P/Q/R6/R7/F、docs で Step4/Phase4+/v2+ 明記) との
重複ゼロ、エンジン間の重複もゼロ (4 エンジンが 4 方向に散った)。**全 major はオーケストレータが実機再現済み**。

**本ラウンドの鉱脈**: (1) ルーティングの意味論 — 「そもそもこのタスクを作ってよいのか」(R9-2)、
(2) path/key の照合 (R9-1、R8 F2 検索"内容"の対になる ignore パターン側)、(3) Partial という
行き止まり状態 (R9-4)、(4) 読み手の余剰 entry 堅牢性 (R9-5、Spark の R9-8 からオーケストレータが
エスカレーションして確定 — P10 と同じ派生発見パターン)。

エンジン別の主な貢献:
- **Claude-Sonnet**: R9-1 (.kioignore の NFC/NFD バイパス、対照実験 + online 送信/検索露出まで実機追跡)
- **Claude-Opus**: R9-2 (text-native → OCR ルーティング違反、実機再現)、R9-6、R9-7
- **GPT-5.5**: R9-3 (open cache permission)、R9-4 (Partial 行き止まり) — 静的立証、実機確定はオーケストレータ
- **Spark**: R9-8 (temp 残留 5 箇所) + R9-5 の種。検証1 (パス正規化) は canonicalize 系経路の健全性確認
- **オーケストレータ**: R9-5 の発見・実機確定、全 major の独立再現、R9-4 の「text 層なし PDF では内容恒久欠落」補強

**却下 / 偽陽性**: 今回ゼロ。ただし GPT-5.5 の「resume は Paused のみ」は不正確
(execute_pending_tasks は Pending を駆動する — R9-7 の根拠)。Partial が全経路の対象外という結論は実機確認どおり。
Spark 検証1 の「問題なし」と Sonnet R9-1 は矛盾しない (Spark の範囲は Repository::open/canonicalize 系で
ignore 照合は範囲外 — 範囲限定の盲点をフルスコープエンジンが補完)。

---

## 必須修正 R9-1〜R9-8

### R9-1 [major] `.kioignore` / `[scope] ignore` の Unicode 正規化不一致で除外が silent 無効化 → 索引・online 送信・検索露出
発見: Claude-Sonnet (完全再現) / 対照実験で再確認: オーケストレータ

- **根本**: `crates/kio-pipeline/src/scan.rs:107-111` が candidate 名 (`input_path`) を生バイトのまま生成、
  `scan.rs:156-210` が `.kioignore` / `config.toml [scope] ignore` パターンも非正規化のまま読み、
  `scan.rs:256-329` (`matches_ignore_pattern` / `wildcard_match_bytes`) がバイト単位比較。
  kio-pipeline は `unicode-normalization` に非依存 (他 4 クレートは依存済み) で正規化手段自体がない。
  macOS (APFS) はファイル名を作成時のバイト列のまま保持し、Finder/iCloud/zip/IME 由来で NFD 名は日常的に発生。
- **再現** (隔離 tmp、実機): NFD 実ファイル `café-notes.md` + NFC パターンの `.kioignore` → `index --offline --yes`
  → `status` で当該ファイルが `unchanged` (= コミット済み・除外失敗)。対照 (同一正規形) は `new` (= 未追跡・除外成功)。
  Sonnet はさらに online mock で markdownize/embedding が Done (= 実送信経路通過)、`search` で本文 snippet 露出まで確認。
- **期待 vs 実際**: 期待 = Unicode 正準等価なパターンは実ファイルを確実に除外。実際 = 正規形不一致で除外が無言で失敗し、
  除外意図のファイルが (a) コミット木へ、(b) online 承認済みなら Mistral OCR / Gemini embedding へ実送信、(c) 検索露出。
- **修正**: `matches_ignore_pattern` の比較直前に両辺を NFC 化 (`.nfc().collect::<String>()`)。
  `kio-pipeline/Cargo.toml` に `unicode-normalization.workspace = true` を追加。
  `ScanCandidate.input_path` の生バイトは不変のまま (R8 F2 と同じ「照合の投影のみ正規化、identity は生バイト」方針)。

### R9-2 [major] text-native (Markdown / plain text / コード) に online Mistral OCR markdownize task が enqueue・実送信・課金 (docs/04 §3・docs/07 §2.1/§5.2 の routing 違反)
発見: Claude-Opus (実機再現) / 再確認: オーケストレータ

- **根本**: `enqueue_online_placeholder_task` (`crates/kio-cli/src/main.rs:6408`) が `candidate.media_type` を
  一切見ずに online OCR task を作る (呼び出し 2 箇所も無条件)。実行側 `execute_online_markdownize_task`
  (`main.rs:4416`) にも media gate なし — `media_type_for_cli_path` が `text/markdown` と判定してもそのまま OCR へ。
- **spec 根拠**: docs/04 §3「非 text-native は文書処理 API 系 Adapter (Mistral OCR、第一候補)」、
  docs/07 §2.1「同梱 deterministic Adapter 対象: plain text / Markdown / コード」、
  docs/07 §5.2「標準 Adapter (**非 text-native**): PDF / DOCX / PPTX / 画像の Markdownize 第一候補は Mistral OCR」。
- **再現** (隔離 tmp、実機): `note.md` + `main.rs` の scope、`[adapter.policy] allow_network = true` (standing opt-in)
  で `kio index --yes` (**--online 不要**) → `online:mistral_ocr_markdownize` Pending ×2 →
  `batch resume` (mock) → `tasks_executed:2`、cost-ledger に `markdown` 課金 2 行。
- **期待 vs 実際**: 期待 = text-native は deterministic で完結し online OCR task を作らない。実際 = 全 text ファイルの
  生バイトが第三者 OCR API へ送信され (privacy 面)、baseline の ~10 倍単価で課金され (cost 面)、
  deterministic 正規化が既に Done なので完全に冗長。しかも F6 (Step 4 保留) により online 成果物は HEAD/search に
  昇格しないため、成果は二重に orphan。routine な `index` + `batch resume` だけで発動する。
- **修正**: `enqueue_online_placeholder_task` 冒頭で text-native media_type (`text/markdown` / `text/plain` /
  `text/x-code` 等、deterministic 対象群) を early-return。実行側にも防御 gate (enqueue 済み既存 task への保険)。
  既存 step2 契約テストが `a.txt` を online-task fixture に使う箇所は `fake_pdf` へ差し替え
  (それらのテストの意図は task lifecycle であり media routing ではない)。
- **design 読みの注記**: docs/07 §2.1 の「online Adapter 承認後の AI 強化」は embedding (全 text 対象) と
  非 text-native の OCR を指し、text-native の online markdownize を意図しない — 07 §5.2 の対象列挙と
  メモリ済み方針 (プロンプト規約は生成 LLM 系限定) に基づく読み。将来 text 向け生成 LLM adapter を導入する場合も
  mistral_ocr へ送る現挙動は正当化されない。

### R9-3 [major] open/view の展開キャッシュが world-readable (dir 755 / file 444) — P2 の 0700 化が cache 側に及んでいない
発見: GPT-5.5 (静的) / 実機確定: オーケストレータ

- **根本**: `open_cas_byte_object` (`crates/kio-cli/src/main.rs:3691-3729`) は `create_dir_all` + `fs::write` +
  `set_readonly(true)` のみ。0700/0600 hardening は `$XDG_DATA_HOME/kio` 側 (P2、`registry.rs:52`) だけで、
  `$XDG_CACHE_HOME/kio/open` subtree は umask 依存。
- **再現** (実機、umask 022): working copy を消して `kio open sha256:<raw>` → cache 展開。
  `$XDG_CACHE_HOME/kio` / `kio/open` / `kio/open/<hash12>` = **drwxr-xr-x (755)**、
  `doc.md` = **-r--r--r-- (444)**、本文が group/other から読める。`readonly` は改変防止であり秘匿ではない。
- **期待 vs 実際**: 期待 = raw/prepared/image bytes を展開する cache は owner-only (dir 0700 / file 0600 or 0400)。
  実際 = multi-user ホストで文書本文・画像・OCR 前 raw data が漏れる。CAS 本体 (P2 で 0600) との非対称。
- **修正**: `$XDG_CACHE_HOME/kio` subtree を 0700 に固定、cache file は 0600 で作成してから必要なら 0400。
  既存 cache の再利用時にも permission を検査・補正。

### R9-4 [major] online markdownize の Partial task が回復不能 (retry/resume/再 index 全滅) + `index_status` が完了偽装 (docs/04 §5.2 の `partial → done` 契約違反)
発見: GPT-5.5 (静的) / 実機確定・影響補強: オーケストレータ

- **根本**: `batch retry` は `Failed` のみ選択 (`main.rs:4098` 付近)、`batch resume`/`execute_pending_tasks` の
  駆動対象に `Partial` なし、enqueue dedup は `Done|Partial` を既処理扱い (`main.rs:6442` 付近)、
  `compute_index_status` は `Done|Partial` を done 計上 (`main.rs:1880` 付近)。
  docs/04 §5.2 は `partial → done (失敗 unit の再投入がすべて成功)` と `unit_keys` による unit スコープ再投入を明記。
- **再現** (隔離 tmp、実機): 2 ページ PDF を `index --approve` → `batch resume` (KIO_TEST_MISTRAL_OCR=partial) →
  task `partial`。以後 mock (全成功) で `batch retry` = `tasks_executed:0`、`batch resume` = 0、
  `index --yes` = noop / 新 task なし。task は `partial` のまま、`index_status` = **`enriched_ratio:1.0`,
  `pending_enrichment_tasks:0`** (欠落が完全に不可視)。
- **影響の階調**: text 層のあるドキュメントは local baseline が内容を拾う (今回の fixture)。text 層のない
  scan PDF/画像では **欠落 unit の内容が恒久に検索不可**なのに 100% enriched 表示 — silent data gap。
  課金済み unit の成果は保全される一方、失敗 unit を完了させる手段が仕様に反して存在しない。
- **修正**: `Partial` を `batch retry` の対象に含め、normalized manifest の failed unit_key のみ
  `unit_keys` 付きで再投入 → 全成功で `partial → done` (docs/04 §5.2)。`compute_index_status` は Partial を
  incomplete/pending 側に計上。**F6 (online 成果物の HEAD/search 昇格、Step 4 保留) には踏み込まない** —
  task lifecycle と status 会計のみ直す。
- **注**: GPT-5.5 の「resume は Paused のみ」は不正確 (Pending は駆動される) だが、Partial が全経路の対象外
  という結論は実機確認どおり。

### R9-5 [major] normalized gen dir の余剰 entry 1 個 (crash 残留 `.tmp-*` / `.DS_Store`) で `reindex` が STORE-CORRUPT 恒久失敗、`repair --rebuild-db` 無効、失敗 copy が部分 `.g<N+1>` を二次残留
発見: オーケストレータ (Spark R9-8 の検証からエスカレーション、P10 型の派生発見) / 実機確定済み

- **根本**: `copy_normalized_instance_gen` (`crates/kio-cli/src/main.rs:4019` 付近の loop) が gen dir の
  `manifest.json` 以外の**全 entry** を無条件に `fs::read` + JSON parse し、失敗を `?` で伝播。
  呼び出し元 `run_reindex` (`main.rs:2228`) は normalize ref を持つ全 tree entry でこれを通る。
  writer 側 (`atomic_overwrite_file` `main.rs:3210` / `markdownize.rs:422`) は temp を**同じ gen dir に**作るため、
  crash (kill -9 / 電源断) の残骸 `.{name}.tmp-<pid>-<ulid>` がまさに読まれる場所に残る。`.DS_Store` でも同型。
- **再現** (実機): gen dir に torn `.tmp-99999-…` を置く → `reindex --force --yes` =
  `KIO-E-STORE-CORRUPT-001` exit 4。`repair --rebuild-db` は成功するが reindex は依然失敗 (治せない)。
  失敗した copy は部分コピー済みの次 gen dir を残す (二次残留)。junk の手動削除でのみ回復
  (削除後 reindex 成功を確認)。
- **期待 vs 実際**: 期待 = 復旧系 (reindex/repair) は自身の crash 残骸や OS 由来 junk に耐える (Q1/R6-2 の教訓)。
  実際 = unit ファイル以外の entry を無差別に「壊れた store ファイル」と解釈して恒久ブリック。
- **修正**: copy loop で unit ファイルの命名規約に一致しない entry (dotfile / `.tmp-*` / 非 regular file) を skip。
  あわせて reindex 時に gen dir の孤児 `.tmp-*` を掃除 (Q1 の torn-tail truncate と同系の自己修復)。

### R9-6 [minor] `KIO-E-CONFIG-NOT-IMPLEMENTED-001` の exit code が経路で 1/2 不一致 (Agent の分類が壊れる)
発見: Claude-Opus / 実機確認: オーケストレータ

- **根本**: 正準 `KioError::not_implemented` = `ExitCode::Failure` (=1) (`crates/kio-core/src/error.rs:127`)。
  手組み 3 箇所が `InvalidUsage` (=2): `repair --verify-objects` (`main.rs:620`)、`reindex --at` (`main.rs:2286`)、
  search time-travel flags (`main.rs:2767`)。
- **再現** (実測): `log --at foo` = exit 1、`reindex --at foo` = exit 2、`repair --verify-objects` = exit 2 —
  同一 error_code で exit class が分岐。
- **修正**: 3 箇所を `KioError::not_implemented(...)` に置換して exit 1 に統一。

### R9-7 [minor] `batch retry`/`resume` が対象外の Pending を裏で駆動・失敗させても `{tasks_executed:0, tasks_updated:0}` (隠れた online 送信試行が JSON 契約に出ない)
発見: Claude-Opus / 実機確認: オーケストレータ

- **根本**: `execute_pending_tasks` (`main.rs:4147`) は retry/resume 共通で全 Pending markdownize/embedding を
  駆動するが、`tasks_executed` は成功のみ計上 (失敗経路 `main.rs:4277-4301` は無計上)。`tasks_updated` は
  retry の `Failed→Pending` 数のみ。
- **再現** (実機): Pending online task がある状態で `batch retry` (auth_error mock) →
  `{"status":"retry scheduled","tasks_executed":0,"tasks_updated":0}` exit 0。実際は task が
  pending → **failed** (attempts=1) に遷移 = API 送信試行済み。orchestrator agent が rate-limit 消費・課金試行を
  検知できない。
- **修正**: `execute_pending_tasks` の戻り値を attempted/failed 込みに拡張し、batch JSON に
  `tasks_attempted`/`tasks_failed` (相当) を追加。

### R9-8 [minor] temp writer 5 箇所がエラー経路で `.tmp-*` を削除せず残留 (掃除する writer 3 箇所と不統一)
発見: GPT-5.3-Codex-Spark / file:line 確認: オーケストレータ

- **箇所** (write_all/sync_all/rename 失敗の `?` で temp が残る):
  `crates/kio-core/src/cas.rs:155` (`atomic_write`) / `cas.rs:175` (`atomic_overwrite`) /
  `crates/kio-pipeline/src/task.rs:171` (`replace_all`) / `crates/kio-adapter/src/mistral_ocr.rs:466`
  (`atomic_write_image_object`) / `crates/kio-cli/src/main.rs:5963` (`atomic_write_cas_object`)。
  対照: `markdownize.rs:430` / `main.rs:2677` / `main.rs:3233` は `let _ = fs::remove_file(&tmp)` で掃除済み。
- **影響**: ENOSPC/EIO 時に一意名の `.tmp-*` が CAS fanout / tasks dir に累積 (GC は Step 4 で存在せず)。
  ENOSPC 下では残留自体が空き容量をさらに食う。R9-5 の温床の一つ。
- **修正**: 5 箇所に失敗時 `let _ = fs::remove_file(&temp);` guard を追加 (既存 3 箇所と同型に統一)。

---

## 受け入れ条件 (R9 ラウンド)

- 各修正に回帰テストを追加 (R9-1: NFC パターン × NFD ファイル名の除外、R9-2: text-native が online task を
  作らない + PDF は従来どおり、R9-3: cache subtree の permission 検証、R9-4: partial → retry → done と
  index_status の incomplete 計上、R9-5: junk entry 混入 gen dir で reindex が成功、R9-6: exit code 一致、
  R9-7: 失敗駆動が JSON に現れる、R9-8: 書込失敗で temp が残らない)
- `cargo test --workspace` / `cargo clippy --workspace --all-targets --all-features -- -D warnings` /
  `cargo fmt --check` 全 green (**clippy は必ず --all-features** — R8 の教訓)
- docs/ の変更は禁止 (仕様は正、実装を合わせる)
- R9-2 で既存 step2 契約テストの fixture 差し替えが必要な場合、テストの検証意図 (lifecycle) を保つこと
- critical 級はなし。major (R9-1〜R9-5) はコミット前にオーケストレータが実機再確認

## 探索したが問題なしと確認した領域 (複数エンジン収束)

- パス/scope 照合の canonicalize 経路・`/tmp/a` vs `/tmp/abc` 型 prefix 混同 (Spark + GPT-5.5)
- Evidence Pointer の cross-snapshot 解決 — (raw_hash, tool_profile_hash, gen) 束縛・shallow/tombstone (Sonnet + GPT-5.5 + Opus)
- 時刻/TZ 算術 — backoff の saturating_mul/clamp、Hinnant civil algorithm、UTC 固定 (Opus + Sonnet)
- FTS クエリ注入・構文堅牢性、`--limit`/`--cursor` 境界 (Opus + GPT-5.5)
- task 再 enqueue dedup (identity + 状態別 output_ref/fallback_reason)・retry 状態機械の attempts 整合 (Sonnet + Opus)
- `slugify_heading` — NFC 済み + 同一 slug は `#N` で分離、display-only で identity 非関与 (Spark + Sonnet + Opus)
- scope-registry の WAL/tie-break 検出、tag 循環の構造的不可能性 (Sonnet + Opus)
- chunks.jsonl の config 変更蓄積 — `chunking_config_hash` で live filter 済み、correctness 影響なし (Opus)
- StoreLock の Drop 解放 — FD/lock ファイルのリークなし (Spark)
- cost-ledger/budget の F3/F8 後の多重 guard (Opus)

## 総合所感

- 9 ラウンド目も新規 5 major。今回はいずれも「ユーザーの意図と実際の乖離」層 — 除外指定が効かない (R9-1)、
  頼んでいない外部送信 (R9-2)、見えないはずの cache が見える (R9-3)、完了と表示される未完了 (R9-4)、
  復旧コマンドが junk に負ける (R9-5)。plumbing (並行/秘匿 gate/会計/crash-atomicity) は 8 ラウンドで堅牢化済みで、
  その上の「意味論・状態設計・OS 現実 (Finder/crash 残骸) との接触面」が今回の鉱脈だった。
- R9-1/R9-2/R9-3 は privacy を正面に掲げる Kio のポジショニングに直結する露出系。R9-2 は F6 と併せて
  「online markdownize の end-to-end 価値」が Step 4 の宿題であることを再確認させる (課金して orphan を作る経路は
  routing gate で今すぐ止められる)。
- 範囲限定 Spark の「問題なし」領域からフルスコープ Sonnet が R9-1 を出した点は、範囲限定+フルスコープの
  組み合わせ運用の妥当性を示す。オーケストレータの検証起点の派生発見 (R9-5) は P10 に続き 2 例目 —
  「エンジン所見の実機検証」フェーズ自体が発見装置として機能している。
