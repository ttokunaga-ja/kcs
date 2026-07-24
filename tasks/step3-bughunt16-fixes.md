# 探索型監査 第16ラウンド (R16) 裁定

- 実施日: 2026-07-08、対象 HEAD: 90d2f79 (テスト全 green・clippy/fmt clean を起点確認済み)
- エンジン: Claude-Opus / Claude-Sonnet-A / Claude-Sonnet-B / Claude-Sonnet-C / Claude-Sonnet-D /
  GPT-5.5 (read-only 静的) / GPT-5.3-Codex-Spark (範囲限定: R15 fix の新配線 + store corruption 契約突合)
- 結果: **新規 6 major + 1 minor (R16-1〜R16-7)**。却下 0 (自己取り下げ 1)、据え置き 1
- ラウンドの骨格: R16 焦点の 2 鉱脈が両方的中。
  (a) **store corruption robustness の契約突合**が本命 — R13-4 (空 HEAD)・R15-4 (tree 欠落) が
  `read_tree` にだけ吸収パターンを適用し、**同じ関数・隣接行の `read_commit` を全箇所素通し**にしていた
  構造的な穴 (R16-1) に **4/4 Sonnet が独立収束** (今ラウンド最強の収束)。そこから search の per-scope
  isolation 破れ (R16-2)、repair の部分回復力ゼロ (R16-4)、diff の契約乖離 (R16-5) が芋づる。
  (b) **R15 fix が開ける穴** (定番脈 6 例目) — R15-4 の shallow 分岐が fresh search で silent 空結果に
  化ける取り残し (R16-3、GPT-5.5 静的のみ検出)、R12-7 の `--flag=value` 受理が確認ゲート bypass に
  波及 (R16-6、GPT-5.5)。(c) **cost-ledger 会計の残り**も直撃 — retry 経路の phantom charge 無制限累積
  (R16-7、Opus 単独・control 付き実機)。
- 全 major はオーケストレータが実機 repro (control 付き) で独立再確認済み。

---

## R16-1 [major] commit object 欠落 (tree ではなく commit 自体) が R13-4/R15-4 の破損耐性網を全箇所素通り — 純読取り (status/log/search/view/open) 全滅・write は生エラー・repair も道連れで CLI 回復手段ゼロ

**収束**: Sonnet-A / Sonnet-B / Sonnet-C / Sonnet-D の 4 本が完全独立に同一根本原因へ収束 (R15 の 3 収束を
超える今ラウンド最強)。オーケストレータが status/log/search/view で実機再確認 (削除→exit 4、復元→exit 0)。

**根本原因**: `is_store_not_found` 吸収パターンが `read_tree` にしか適用されておらず、`read_commit` は
全 call site で無条件 `?`。R15-4 の `run_reindex` では「10 行差で tree は COMMIT-SHALLOW 変換・commit は
素通し」という極端な非対称になっている。call site 一覧 (4 エンジンの合算・裁定時点):
- `crates/kio-core/src/scope.rs:740` `head_tree_state()` — 直後の 741 `read_tree` だけ Shallow 吸収 (R15-4)
- `crates/kio-core/src/scope.rs:509` `log()` — 履歴走査中の**どの祖先** commit が欠けても全滅 (Sonnet-B が
  root commit 欠落で「健全な直近 2 件も返らない」ことを実機確認)
- `crates/kio-core/src/scope.rs:523-524` `diff()` (R16-5 と共通)
- `crates/kio-core/src/scope.rs:420-422` `snapshot_with_type()` の prior-commit 読込 (`.transpose()?`)
- `crates/kio-cli/src/main.rs:2042` / `2045` `ensure_snapshot_tree_entries()` 両分岐 (= 全 search が経由)
- `crates/kio-cli/src/main.rs:2607` `run_reindex()`
- `crates/kio-cli/src/main.rs:2721` `rebuild_step3_index()` (= index/reindex/repair --rebuild-db が共有)
- `crates/kio-cli/src/main.rs:4225` `resolve_pointer_for_cli()` (= view/open の Evidence 解決の唯一の入口)

**実機 (オーケストレータ再確認分)**: HEAD commit object を 1 個 `rm` →
`status`/`log`/`search`/`view <有効URI>` 全て `KIO-E-STORE-NOT-FOUND-001` exit 4。復元で全て exit 0。
Sonnet-D の対照実験: sqlite.db 欠落は `Excluded("index_missing")` exit 3 で正しく part-failure するのに
commit 欠落だけ素通り。Sonnet-B の対照: raw CAS object 欠落は status/search/view とも exit 0 (正規化
キャッシュ経由で本文復元) — **commit object だけがガード漏れ**という切り分け。

**契約**: R14-3/R15-1/R15-4 で確立した「純読取りは破損を生き延びる・write は明確なエラーコードで拒否」。
特に `view` は docs/05:345「shallow commit を指す Evidence Pointer の解決は失敗しない (raw_hash/chunk_hash
による直接解決)」の明文保証があり、解決前段の `read_commit` 無条件 `?` はこの保証を直接破る
(evidence-grounded という中核価値の破れ)。docs/05:329「commit object の削除操作は Kio に存在しない」は
Kio 自身の操作の話であり、外部破損 (disk error/誤操作/部分復元) は R13-4/R15-4 と同じ防御対象クラス。

**fix 方針**: commit object 欠落を tree 欠落と同格の「shallow 相当」として系統適用する。
- read 系: `head_tree_state()` の `read_commit` を `read_tree` と同じ `is_store_not_found` 吸収で
  Shallow 側に畳む (status は既存の degrade 表示)。`log()` は欠落地点で走査を打ち切り、取得済み prefix +
  truncated 明示 (silent 全滅にしない)。`resolve_pointer_for_cli` は commit 読込を best-effort 化し
  raw_hash/chunk_hash 直接解決を継続 (docs/05:345 / docs/08 §3.1 準拠)。
- write 系 (snapshot/index/reindex/repair): `KIO-E-COMMIT-SHALLOW-001` + 復旧ガイダンスへ変換
  (新エラーコードは増やさない — 回復手段・意味論が tree 欠落と同一のため。rationale をコードコメントに残す)。
- search 系は R16-2/R16-3 と一体で設計 (下記)。**重要**: `ensure_snapshot_tree_entries` の commit 欠落を
  単純に `Ok(false)` に畳むと、fresh search が R16-3 の silent 空結果に合流して「loud 死→silent 偽陰性」の
  改悪になる。必ず R16-3 の tri-state 化とセットで実装すること (fix が次の穴を開ける定番を先回りで封じる)。
- 回帰テスト: commit object 欠落下で (a) status/log/search/view が exit 0 degrade、(b) snapshot/index/
  reindex/repair が COMMIT-SHALLOW、(c) 復元後に全て正常、の 3 点セット。

## R16-2 [major] multi-scope search の Fatal 増幅 — 1 scope の store 破損が健全 scope の結果ごと全体を exit 4 で道連れ (docs/05 §1.8 part-failure 契約違反、R10-1(a) の未全称化)

**発見**: Sonnet-A (単独発見・2 scope 実機)。Sonnet-D の対照実験 (index_missing は exit 3 + excluded で
正しく part-failure) が裏付け。オーケストレータが 2 scope 実機で再確認: 健全時 results 2/searched 2 →
scope B の commit object 削除後、全体が exit 4 で scope A の結果も全喪失。`--scope .` 限定なら A は正常。

**根拠**: `crates/kio-cli/src/main.rs:1360` — per-scope ループの `Err(ScopeSearchError::Fatal(error)) =>
return Err(error)` が収集済み candidates/searched を破棄して全体 abort。同関数内で `index_corrupt`
(1626-1628)・`index_rebuilding` (1659-1663)・vector 容量超過 (1707-1709、R10-1(a)) は Excluded に
畳まれているのに、store 破損系の Fatal だけ増幅経路が残る。docs/05 §1.8「一部 scope 失敗 → 結果を返し
excluded_scopes に記録 (exit 3)、全 scope 失敗 → エラー」。

**fix 方針**: `search_one_scope` の Fatal のうち **store 破損クラス (KIO-E-STORE-NOT-FOUND-001 /
KIO-E-STORE-CORRUPT-001 / KIO-E-STORE-IO-001 / KIO-E-COMMIT-SHALLOW-001)** を
`Excluded(reason="store_corrupt")` に降格し、既存の「全 scope 失敗 → SCOPE-ALL-FAILED exit 4」集約に
乗せる。**Fatal 全般の一般化はしない** (真のプログラミングエラー/予期しないエラーは fail-fast が正 —
Sonnet-A の「Fatal 全般を格下げ」案は過剰適用として絞る)。cursor 経路の Shallow hard-fail (05 §2.2) は不変。
回帰テスト: 2 scope 中 1 scope の commit object 欠落で exit 3 + 健全 scope の結果 + excluded reason。

## R16-3 [major] fresh search が shallow HEAD (tree 欠落 + tree_entries cache 行なし) で silent 空結果 exit 0 — cursor 経路だけ loud で fresh 経路は `Ok(false)` を黙殺 (P10 と同型の沈黙偽陰性)

**発見**: GPT-5.5 (静的単独)。4 Sonnet は commit 欠落の loud 死に注意が向き、tree 欠落の silent 側は
静的読解のみが捕捉 — mock/実機で気づきにくい型に静的枠が刺さる R14-4/R15-5 パターンの並び。
オーケストレータが実機確定: index → snapshot (HEAD 前進・新 commit の tree_entries は未射影) → tree object
削除 → `search` が **results:[] / excluded_scopes:[] / searched に scope 収載 / exit 0**。tree 復元で 1 件。

**根拠**: `ensure_snapshot_tree_entries` (main.rs:2021-) は tree 欠落で `Ok(false)`。cursor 経路 (1634-1638)
は `Ok(false)` → `ScopeSearchError::Shallow` に変換するが、fresh 経路 (1641-1645) は `Err` しか見ず
`Ok(false)` を捨てて続行 → 当該 commit の tree_entries 0 行に対し全 backend の join が空。
`index_is_rebuilding` (2136-) は tree_entries 0 行を「正当な空 scope」とみなし発火しない (P10 ガードの死角)。

**fix 方針**: `ensure_snapshot_tree_entries` を tri-state 化 (例: `Projected` / `ShallowCachedRows` /
`ShallowNoRows`。R16-1 とセットで `CommitMissing` 相当も区別) し、fresh 経路は
- `ShallowNoRows` / commit 欠落 → `Excluded(reason="snapshot_shallow")` (silent 継続でも Fatal でもなく)
- `ShallowCachedRows` → 検索継続 (read degrade。cache 行があれば結果は真正で、Evidence は raw_hash 直接
  解決が docs/05:345 で保証される)
- cursor 経路は従来通り shallow 全種 hard fail (05 §2.2)。
回帰テスト: 上記実機シナリオ (snapshot 後 tree 削除→fresh search) が excluded reason 付き exit 3 になること。

## R16-4 [major] `repair --rebuild-db` (唯一実装済みの回復コマンド) が回復対象の破損そのもので死ぬ — shallow tree で生 STORE-NOT-FOUND exit 4、normalized unit 1 個欠落で scope 全体 STORE-IO exit 1・部分回復力ゼロ

**収束**: Spark (静的・reindex L2608 との対照つき) + Sonnet-A (実機 + git show 8ddee42 で R15-4 fix が
run_reindex のみと確認 + docs/10:417-418 の復旧保証との乖離) + Sonnet-D (実機 + unit 欠落の補強)。
オーケストレータ再確認: shallow tree で repair exit 4 (raw STORE-NOT-FOUND) / reindex は exit 1
COMMIT-SHALLOW (R15-4 修正済みの対照)。unit 1 個削除で repair exit 1 KIO-E-STORE-IO-001・全体失敗、
復元で exit 0。

**根拠**: `rebuild_step3_index` (main.rs:2716-2722) の `read_commit`/`read_tree` が無条件 `?` で、
`run_repair` (main.rs:734-745) は reindex が持つ前段 shallow ガードなしに直接呼ぶ。R15-4 の裁定文自身が
「repair --rebuild-db も STORE-NOT-FOUND」と問題を名指ししながら、fix と回帰テスト
(`r15_4_shallow_head_degrades_reads_and_rejects_writes`) の適用範囲から repair が漏れた (fix 網羅性の穴)。
unit 欠落側は `load_normalized_units` (main.rs:2871-2909) の無条件 `?` が同ループから伝播し、1 ファイルの
破損が他の健全文書の再構築まで巻き添え。docs/10:417-418「最悪 objects/ と refs/ が保全されていれば復旧
できる」の保証に反する。

**fix 方針**: (a) `rebuild_step3_index` 冒頭 (または read_tree 箇所) で R15-4 と同じ
STORE-NOT-FOUND→`KioError::commit_shallow` 変換 (共有関数側に置き repair/index/reindex を一括カバー)。
(b) unit 読込失敗は該当 raw_hash を skip して残りの再構築を続行し、JSON に `skipped_units` (件数 + 対象 +
理由) と「`reindex --force` で raw から再正規化せよ」のガイダンスを明示 (silent 縮小にしない)。
回帰テスト: shallow で COMMIT-SHALLOW、unit 1 個欠落で「他文書は再構築 + skipped_units 報告」の 2 本。

## R16-5 [minor] `kio diff` が shallow commit で生 `KIO-E-STORE-NOT-FOUND-001` (不透明 hash) — docs/05:341「片方が shallow なら全ファイル差分は不能と明示」の契約乖離

**収束**: Spark + Sonnet-A + Sonnet-D + Opus の 4 エンジン (severity は A=major / D=minor / Opus=minor →
loud に倒れる・データ損失なし・到達は corruption 経由のみ、で **minor 裁定**)。オーケストレータ実機確認済み
(exit 4・生 hash のみ)。

**根拠**: `Repository::diff` (`crates/kio-core/src/scope.rs:519-524`) の `read_commit`/`read_tree` 無条件 `?`。

**fix 方針**: R16-1 と同じ吸収で `KIO-E-COMMIT-SHALLOW-001` + どちら側 (a/b) が shallow かを context で明示。

## R16-6 [major] 手書きパーサの no-value flag が `--flag=<値>` の値を黙殺して true 化 — `reindex --force=false --yes=false` (明示否定) が確認ゲートを bypass してフル実行 exit 0 (R12-7 fix が開けた穴=定番脈 7 例目)

**発見**: GPT-5.5 (静的単独)。オーケストレータ実機確定: `reindex` 単体は exit 2「requires --force」なのに
`reindex --force=false --yes=false` は `status:"reindexed"` exit 0 でフル再正規化を実行。

**根拠**: R12-7 の `split_flag_value` (main.rs:3183) 導入時、値を取らない flag の inline 値検査が
3 パーサとも未実装 — `parse_reindex_args` (main.rs:2690: `--force`/`--yes`)、`parse_repair_args`
(main.rs:781: コメントで「boolean は inline を無視する」と明記=意図的だが意味論が逆転する。
`--rebuild-db=false` が rebuild 実行)、`parse_search_args` (main.rs:3218: `--text=false` が text 指定扱い、
`--all-scopes=false` が all-scopes 有効化等)。clap-derive 側の bool flag は `--json=false` を拒否するため、
typed コマンドとの一貫性も破れている。

**fix 方針**: 値を取らない flag は `inline.is_some()` を `KIO-E-CONFIG-USAGE-001`
(`flag --force does not take a value` 形式) で一律拒否 (=true も含めて拒否 — clap の SetTrue と同じ挙動に
揃える)。3 パーサすべて。回帰テスト: `reindex --force=false` / `repair --rebuild-db=false` /
`search q --text=false` が exit 2。

## R16-7 [major] retry 可能失敗 (特に RateLimit=無制限リトライ) が送信試行のたびに満額を再予約 — phantom charge が無制限累積し、device 月次 cap を枯渇させて他の正規タスクを budget_exceeded で誤 Paused (R15-2 の被害を retry/reclaim 経路で再現)

**発見**: Opus (単独・cap 枯渇→誤 Paused まで control 付き実機)。オーケストレータ再確認: PDF 1 文書を
`index --online --approve --yes` → `KIO_TEST_MISTRAL_OCR=rate_limit` で batch resume + retry×2
(KIO_FIXED_NOW で backoff 跨ぎ) → **ledger が 2→3→4 行、毎回同一の満額 0.1331751 USD、送信成功ゼロ**。
RateLimit は `retry_policy` (crates/kio-pipeline/src/task.rs:312-318) で max_attempts=None (無制限) のため
累積に上限がない。embedding 側 (main.rs:6614) も同型 (Opus が 2→6 行を実測)。

**既知トレードオフとの境界 (重要)**: F8 (reserve-before-send・失敗でも予約を戻さない) と R11-6/R15-5
(retry の按分課金) は「**1 回の送信試行が課金され得る**から予約は保守的に残す」という裁定で、これは維持する。
本件はその外側 — **429 (RateLimit/QuotaExceeded) はバックエンドで処理前に拒否され課金され得ない**のに、
再送信のたびに新規予約を積むため、同一論理操作 1 つが N 倍課金として cap を食い潰し、被害が他 scope の
正規タスク (誤 Paused) に波及する。R15-2 (supersede の phantom charge) が「実行されないものに課金しない」を
確立した際、adapter まで到達して 429 で弾かれる retry 経路が未接続のまま残った合流点。

**fix 方針**: **error-kind-aware の再予約 gate** — 同一 task instance の再送信時、直前の失敗が
「課金され得ない種別 (RateLimit / QuotaExceeded)」なら charge を skip する (前回の予約が今回の送信を
既にカバーしている)。NetworkError は従来通り試行ごとに予約 (サーバ側で課金済みの可能性があり、
max_attempts=5 で有界 — F8 の保守性を維持)。crash 後の Q3 reclaim も従来通り再予約 (直前結果が不明のため
保守側、attempts policy で有界)。**Opus 提案の「task 生涯で 1 予約 (cost_reserved フラグ)」は不採用** —
NetworkError 再送はサーバ側二重課金があり得るため、生涯 1 予約では実支出 > 予約の cap silent bypass
(R15-5 で major とした型) を逆に開けてしまう。rationale を charge 箇所のコードコメントに残すこと
(R11 の教訓: 後続ラウンドの却下高速化)。markdownize (main.rs:5471 付近) と embedding (main.rs:6614 付近) の
両 charge 経路に適用。回帰テスト: rate_limit×N retry で当該 task の charge 行が 1 のまま (attempts は進む)、
NetworkError retry では従来通り増える、の discriminator 2 本。

---

## 却下・据え置き

- **却下 0**。全エンジン報告が採択に至った初のラウンド (R9 の「却下ゼロ」に並ぶが、今回は自己取り下げ 1 を含む):
  Sonnet-C が「raw object 欠落と registry 列挙の相関」を複数回のクロス Bash 検証で再現不能と判定し
  テストハーネス側 artifact として自己取り下げ (単一シェル内の通し実行では正常を確認済み。
  R11 の「検証リダイレクト先/XDG 共有」型のオーケストレーション罠と同族)。
- **据え置き**: multi-scope 列挙で `registry_entry_is_live` が false の行を excluded_scopes に理由記録せず
  無言 drop する透明性ギャップ (Sonnet-A 発見・自己評価どおり severity 不足)。R16-2 の
  excluded reason 整備と隣接するため、fix 時に低コストで拾えるなら `reason="scope_unreachable"` を
  足してよいが、独立所見としては立てない。
- 参考 (非所見): R15-1/R15-2/R15-3/R15-5/R15-6/R15-7/R15-8 の fix 自体は 7 エンジンの静的+実機で健全確認
  (R15-1 の refs fallback は dangling ref を盲信しない・R15-5 の restrict_to_hint_pages は fresh full send に
  誤伝播しない・R15-6 の reused_from identity 一貫、等)。「fix が開ける穴」は今回 R15 の 8 fix 自体からは
  出ず、**R15-4 が触らなかった隣接行 (read_commit) と R12-7 の残り** から出た — 「fix の新配線」だけでなく
  「fix が適用範囲を絞った際の相似形の隣」も掃く対象という新しい学び。

## エンジン別スコア (参考)

- Sonnet-A/B/C/D: R16-1 に 4 本完全独立収束 (史上最強)。A はさらに R16-2 (増幅経路) を単独で立て、
  repair/diff にも実機収束。B は履歴奥 log 全滅 + raw object 対照。C は view/open Evidence 保証の破れ
  (severity 根拠の核) + 9 call site 網羅。D は sqlite 対照実験 + repair unit 破損の補強。
- GPT-5.5: silent 系 2 件 (R16-3/R16-6) を単独検出 — mock/実機で見えにくい型を静的枠が拾う
  R14-4/R15-5 パターンの 3 ラウンド連続。
- Spark: 範囲限定焦点 (shallow 網羅) が R16-4/R16-5 の初動立証 — R12 以来の「焦点が本命に噛み合う」回。
- Opus: 別脈 (cost-ledger retry 会計) で単独 major — R16-1 クラスタに参加しなかった分、
  唯一の非破損系 major を control 付きで確保。
