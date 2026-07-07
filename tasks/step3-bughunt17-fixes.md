# 探索型監査 第17ラウンド (R17) 裁定

- 実施日: 2026-07-08、対象 HEAD: fb951ec (テスト全 green 458・clippy --all-features/fmt clean を起点確認済み)
- エンジン: Claude-Opus / Claude-Sonnet-A / Claude-Sonnet-B / Claude-Sonnet-C / Claude-Sonnet-D /
  GPT-5.5 (read-only 静的) / GPT-5.3-Codex-Spark (範囲限定: R16 fix の新配線が開ける穴 + cost-ledger 会計残余)
- 結果: **新規 3 major + 4 minor (R17-1〜R17-7)**。却下 1 (Spark TOCTOU)、据え置き 1 (month 月跨ぎ)
- ラウンドの骨格: R17 焦点の「R16 fix が開ける穴」が本命的中し、加えて Sonnet-A が別脈で 3 連発。
  (a) **本命 = resolve_pointer_for_cli の best-effort 過剰適用** (R17-1) に **4 エンジン独立収束**
  (Sonnet-B/C/D + GPT-5.5)。R16-1 が `read_commit` 欠落を「真の shallow」と同一視した結果、捏造 commit
  hash で N5 gen 束縛 + tree 所属チェックを迂回でき、evidence-grounded の中核 (view/open) を破る。
  **Opus は「真正 chunk なので検証弱化なし」と healthy 誤判定 → オーケストレータが N5 gen 束縛の実機
  バイパス (Attack A exit 4 vs Attack B exit 0) で反証** (R13/R15 の Opus doc-gap 型の再現)。
  (b) **R16-4 の兄弟穴** (R17-2) — R16-4 が `rebuild_step3_index` に入れた skip-continue が `run_reindex` の
  正規化ループに未移植で、単一破損 unit が scope 全体を停止。しかも repair の guidance が壊れた
  `reindex --force` を案内 (R17-6 と連鎖)。派生で store 破損クラスの exit 非対称 (R17-4)。
  (c) **cost-ledger phantom charge の残り** (R17-3、Opus 単独 major・control 実機) — R15-2 (enqueue supersede) が
  Pending/Paused のみ退役し、R16-7 が「rate_limit は非課金」と確立したことで Failed(rate_limit) の予約が
  明白な phantom に転じ、編集後の正規 OCR を誤 Paused。R15-2 × R16-7 の合流点。
  (d) **R16 fix の隣接取り残し 2 件** — resolve_commit/tag の COMMIT-SHALLOW 未カバー (R17-5、Sonnet-B + Opus)、
  R16-7 embedding charge gate コメントの triple-fault 誤主張 (R17-7、GPT-5.5 + Opus)。
- 全 major はオーケストレータが実機 repro (control 付き) で独立再確認済み。

---

## R17-1 [major] `resolve_pointer_for_cli` の R16-1 best-effort 化が、捏造 (一度も実在しない) commit hash を「真の shallow commit」と同一視し、N5 gen 束縛 + tree 所属チェックを両方迂回させる — evidence-grounded の中核 (view/open) の identity 検証が commit フィールドの偽造だけで無力化される

**収束**: Sonnet-B / Sonnet-C / Sonnet-D / GPT-5.5 の **4 エンジン独立収束** (R16-1 の 4/4 Sonnet に次ぐ強収束)。
Sonnet-C は 3-way 比較 (正しい現行 commit=拒否 / 捏造 commit=通過 / 正しい旧 commit=許容)、Sonnet-D は docs 契約
(docs/08 §3.2:150・docs/03:480) + R16-1 回帰テストの網羅漏れを立証。**Opus は「best-effort が返す chunk は
(raw_hash, tool_profile_hash, chunk_hash) identity を通った真正 chunk なので検証弱化なし」と healthy 誤判定
→ オーケストレータが N5 gen 束縛の実機バイパスで反証** (R13 doc-gap / R15 snapshot orphan の Opus「問題なし」
誤判定を実機で覆す型の 3 例目)。

**根本原因**: `resolve_pointer_for_cli` (`crates/kcs-cli/src/main.rs:4435-4439`) が `read_commit(&pointer.commit)`
の `KCS-E-STORE-NOT-FOUND-001` を `None` に潰し (R16-1)、`main.rs:4482-4486` で「真の shallow (`read_tree` が
STORE-NOT-FOUND = commit 実在・tree GC)」と「commit object 欠落 (`read_commit` 自体が STORE-NOT-FOUND)」を
**同一の `(commit_shallow=true, entry_gen=None)` に合流**させる。`entry_gen=None` により:
- N5 gen 束縛 (`main.rs:4531-4535`、`if let Some(entry_gen)`) が丸ごとスキップ
- tree 所属チェック (`main.rs:4448-4461`、raw_hash が commit.tree の entry にあるか) がスキップ

残る検証は chunk の (raw_hash, tool_profile_hash) 一致 (4520-4523) のみ。`pointer.commit` は `view`/`open` の
引数 (`kcs://` URI か inline JSON) で完全にユーザー入力可能なため、実在の (raw_hash, chunk_hash, tool) 3 つ組を
握った上で commit だけを捏造 hash に差し替えると、両検証を迂回して `commit_shallow:true` / exit 0 で解決成功する。

**実機 (オーケストレータ独立再現)**:
- basic: genuine pointer → `commit_shallow:false` exit 0 / commit を `sha256:<全0>` 等の捏造 hash に差替 →
  `commit_shallow:true` exit 0 で本文を返す。
- **N5 対照 (実害の核心)**: `reindex --force` で gen 0→1 に更新 (chunk_id は gen を含むため gen0/gen1 で異なる)。
  - Attack A (実在旧 commit C0 + gen1 chunk): `KCS-E-EVIDENCE-POINTER-INVALID-001` exit 4 — N5 が正しく拒否
  - Attack B (捏造 commit + gen1 chunk): `commit_shallow:true` exit 0 で gen1 本文を返す — **N5 迂回成立**
  唯一の差は commit フィールドの真偽。tool_profile 変更で内容が変わる gen 間 (例: OCR エンジン更新) では、
  「古い commit の時点の証拠」として新世代の内容を偽装できる = evidence-grounded の時点保証の破れ。

**契約**: docs/08 §3.2:150「解決成功条件: commit object が存在 (**shallow でもよい。commit object は GC で
削除されない**)」— commit object の**存在**が明文の解決前提。docs/03:480「不変性保証は gen 保全により成立」。
docs/05:345 (view は shallow commit を指す pointer 解決に失敗しない) の保証は **shallow commit (commit 実在・
tree GC)** に限定され、commit object 欠落は対象外。R16-1 が resolve_pointer に best-effort を適用した際、この
「commit 実在」前提を「commit 欠落」に無断拡張し、真の破損と捏造を `is_store_not_found` 一本で同一視した。
R16-1 の回帰テスト `r16_1_missing_commit_object_degrades_reads_and_rejects_writes` (step3_p0_contract.rs:4785-4790)
は「実在した HEAD commit を後から削除」ケースしか view で検証しておらず、捏造 commit を素通しした。

**fix 方針**: resolve_pointer_for_cli の best-effort を「`read_commit` **成功** + `read_tree` STORE-NOT-FOUND
(真の shallow)」に限定する。`read_commit` 自体の STORE-NOT-FOUND は Evidence 解決失敗
(`KCS-E-EVIDENCE-POINTER-INVALID-001`: 参照 commit が解決できない = pointer 無効) に分離し、tree 所属/N5 gen
の検証迂回を封じる。**R16-1 の status/log/search の commit 欠落 degrade は真正性の問題がないため維持**
(resolve_pointer_for_cli だけが Evidence 真正性の入口)。r16_1 回帰テストの view 部分 (4785-4790) を「commit
欠落時の view/open はエラー」に変更し、status/log/search の degrade 検証 (4763-4784) は温存。R16-1 の裁定文が
resolve_pointer を best-effort 化した根拠 (docs/05:345) は shallow 限定であり commit 欠落には及ばない旨を
コードコメントに残す (後続ラウンドの再検証高速化)。回帰テスト: (a) 捏造 commit の view/open が
EVIDENCE-POINTER-INVALID exit 4、(b) 真の shallow (tree GC・commit 実在) の view が commit_shallow:true exit 0、
(c) N5 対照 (gen1 chunk + 捏造 commit は拒否) の 3 点。

## R17-2 [major] `reindex --force` の正規化ループが単一破損 normalized-unit で scope 全体停止 — R16-4 が `rebuild_step3_index` に入れた skip-continue が `run_reindex` に未移植。しかも `repair --rebuild-db` の guidance がこの壊れた `reindex --force` を「回復手段」として案内する

**発見**: Sonnet-A (実機 + R16-4 の適用範囲を git 対照で特定)。オーケストレータが 2 文書実機で再確認。

**根本原因**: `run_reindex` の正規化ループ (`main.rs:2695-2715`) が `copy_normalized_instance_gen(...)?` を
無条件 `?` で呼ぶ。破損/欠落 unit は `KCS-E-STORE-CORRUPT-001`/`STORE-IO-001` を返し、この `?` で scope 全体が
即死する。対照的に **R16-4 が追加した `rebuild_step3_index` (`main.rs:2844-2865`)** は同じ種別を
`is_rebuild_skippable_unit_error` で捕捉して該当文書だけ skip + continue する。この耐性パターンが
`run_reindex` の正規化ループ (rebuild より前段) には移植されていない (R16-4 が repair/index/reindex の **tree 読み**は
`read_head_tree_for_rebuild` で共通化したが、reindex 固有の **unit コピー**ループは適用範囲外だった)。

**実機**: 2 文書 (healthy.md + corrupt.md)、corrupt.md の manifest.json を破損 → `reindex --force --yes` が
`KCS-E-STORE-CORRUPT-001` exit 4 で全体停止 (`reindexed_files` すら出ない)。healthy.md も再正規化されない。
既存 index は無傷 (`search healthydoc` は 1 件) なので、reindex 操作だけが道連れ。

**契約**: docs/10 §7.2「1 文書の破損が他の健全文書の回復まで拒否権を持たない」。R16-4 の設計原則が reindex に
未適用。かつ `attach_skipped_units` の guidance (`main.rs:2944-2955`) が「`kcs reindex --force` で再正規化せよ」と
案内するため、repair が唯一案内する回復手段そのものが破損で死ぬ (R16-4 が repair について指摘した
「回復コマンドが回復対象の破損で死ぬ」の未修正の兄弟)。

**fix 方針**: `run_reindex` の正規化ループで `copy_normalized_instance_gen(...)` の失敗を
`is_rebuild_skippable_unit_error` で捕捉し、失敗した raw_hash は前世代 (`normalize.gen`) を維持したまま
`skipped_units` に記録して残りの文書の再正規化を継続 (rebuild_step3_index と同じ耐性・exit 0 + loud 開示)。
回帰テスト: 2 文書中 1 文書の unit 破損で reindex --force が healthy を再正規化 + skipped_units 報告。

## R17-3 [major] rate_limit で Failed になった online markdownize task の F8 予約が phantom として device-global ledger に残り、per-adapter markdown cap を枯渇させて編集後の正規タスクを誤 Paused — R15-2 (enqueue supersede) が Pending/Paused のみ退役し、R16-7 (rate_limit=非課金) が確立した「予約は phantom」を Failed 経路で放置

**発見**: Opus (単独・control 付き実機で cap 枯渇→誤 Paused まで)。オーケストレータが exp9.sh を隔離環境で
独立再現 (control vs phantom を 2 回とも決定的)。

**根本原因**: `main.rs:5737` で初回送信が F8 満額を予約し、rate_limit 失敗でも予約は残置 (F8 の設計)。R16-7 が
「RateLimit/QuotaExceeded はバックエンドで課金され得ない」と確立したため、この予約は明白な phantom。ところが
R15-2 の enqueue-time supersede (`main.rs:8820-8836`) は `matches!(task.status, TaskStatus::Pending |
TaskStatus::Paused)` のみを退役し、**`Failed` (rate_limit で送信済み) を除外**する。編集で raw_hash が変わった
再 index では stale な v1 (Failed) が退役されず、その phantom 予約が `budget_remaining_for_adapter`
(`main.rs:8886`) の markdown spend を食い、v2 を `Paused(budget_exceeded)` として出生させる。R15-2 のコメント
自身 (`main.rs:8811-8816`) が「stale task が per-adapter markdownize cap を食い正規タスクを誤 Pause する」と
Pending/Paused について認識していたが、Failed(rate_limit) 経路が未接続のまま残った。

**実機**: PDF を `index --approve` → `KCS_TEST_MISTRAL_OCR=rate_limit batch resume` で v1=Failed(rate_limit) +
markdown ledger に満額 phantom 1 行 → PDF 編集 (raw_hash 変化) → `[budget.per_adapter] markdown` を「1 送信超・
2 送信未満」に設定して再 index。control (rate_limit スキップ) では v2 = `pending ready_for_online_adapter`、
phantom では v2 = `paused budget_exceeded`。crash 不要・rate_limit (無制限リトライ設計の常態) + 編集という
通常操作のみで再現。

**契約**: R15-2「陳腐化 task の phantom charge で正規タスクを誤停止しない」を Failed 経路で破る。R16-7
「rate_limit は課金され得ない」。

**fix 方針**: `main.rs:8824` の supersede 条件に **retryable-`Failed`** を追加し (`task_retry_allowed` gate 付きで
stale な Failed task を退役)、併せて**非課金種別 (rate_limit / quota、R16-7 で確立) の phantom 予約を reclaim**
する。F3 (負値補正エントリ禁止) と両立させるため、単純な負値 append ではなく「予約 vs 実課金の照合」または
per-task の予約 release 機構が要る (厳密には 1 行超)。**NetworkError の予約は reclaim しない** (サーバ側課金の
可能性があり、生涯 1 予約は R15-5 の cap silent bypass を開ける — R16-7 の裁定と同じ非対称を維持)。embedding
charge 経路 (`main.rs:6931`) の同型 (chunk が編集で非 live 化 → rate_limit 予約が orphan) も同時に確認する。
裁定理由をコードコメントに残す。回帰テスト: rate_limit Failed → 編集 → 再 index で v1 退役 + v2 が phantom
なしで pending (control と一致)、NetworkError Failed では予約が保守的に残る (cap-safe) の discriminator 2 本。

## R17-4 [minor] store 破損クラス (`store_corrupt` / `snapshot_shallow`) が全 scope を除外したときの exit code / 回復ガイダンスが `index_missing` / `index_corrupt` と非対称 — 単一 scope の store 破損 search が exit 4 + 誘導なしに落ち、Agent が「exit 1 なら repair」を検知できない

**発見**: Sonnet-A (major 主張) + 実機。severity は **minor に裁定** (exit 4 = 手動介入は snapshot_shallow には
妥当・データ安全・「誘導の欠如」が主問題であって exit code が完全に誤りではない)。

**根本原因**: `main.rs:1423-1429` の `index_unusable` 特殊分岐が `Some("index_missing") | Some("index_corrupt")`
のみを見て、R16-2 が新設した `"store_corrupt"` (`main.rs:1388`) と R16-3 の `"snapshot_shallow"`
(`main.rs:1684`) を素通りさせ、汎用の `scope_all_failed_error` (exit 4・誘導なし) に落とす。`is_store_corrupt_class`
(`main.rs:5001`) のコメント自身が「commit/tree 破損は STORE-IO と同じ store 破損クラス」と述べており、
`index_unusable` の意味論 (both backends structurally gone) がこのクラスにも及ぶはずだが実装が追随していない。

**実機**: 単一 scope で HEAD commit object のバイト改ざん (hash mismatch → store_corrupt) → `search` が
`KCS-E-SEARCH-SCOPE-ALL-FAILED-001` exit 4 + 誘導なし。対照: sqlite.db 削除 (index_missing) → exit 1 +
「run kcs repair --rebuild-db」誘導。

**fix 方針**: store 破損クラスが全 scope を除外したとき、回復ガイダンスを付与する。ただし **`index_missing` と
同一化 (exit 1 + repair 誘導) は誤誘導**になる — `snapshot_shallow` は `repair --rebuild-db` では直らず
(R16-4 で COMMIT-SHALLOW を返す)、object 復元 / 再 index が回復手段。したがって store_corrupt → 「repair
--rebuild-db を試し、直らなければ objects/refs から復元」、snapshot_shallow → 「HEAD commit/tree object を復元
するか再 index」の、回復可能性に応じたガイダンスを付ける (安易な exit 同一化はしない)。回帰テスト: 単一 scope
の store_corrupt / snapshot_shallow search が回復ガイダンス付きで返る。

## R17-5 [minor] `resolve_commit` / `tag` の 3 箇所が R16-1/R16-5 の COMMIT-SHALLOW 系統変換の対象漏れ — shallow commit を hash リテラル / tag 名 / 暗黙 HEAD 経由で `diff`/`tag` に渡すと生 `KCS-E-STORE-NOT-FOUND-001` exit 4 (R16-5 が保証した COMMIT-SHALLOW exit 1 + side 明示に到達しない)

**収束**: Sonnet-B + Opus (2 エンジン) + 実機。

**根本原因**: R16-1 が 8 call site の `read_commit` を系統的に COMMIT-SHALLOW 化したが、`resolve_commit` の
hash 直値分岐 (`crates/kcs-core/src/scope.rs:689`) と tag 名解決分岐 (`scope.rs:696`)、および `tag()` 自身の検証読み
(`scope.rs:662`) の `read_commit(...)?` (無条件) を漏らした。`diff` (`scope.rs`) は `resolve_commit(a)?`/
`resolve_commit(b)?` を `diff_side_tree` の R16-5 吸収より**先に**呼ぶため、hash リテラル経由で shallow commit を
渡すと R16-5 の修正コードに到達する前に生エラーで落ちる。`"HEAD"` **文字列**経由は `head_commit_hash()` を返す
だけで read_commit を挟まないため R16-5 に正しく到達する非対称。

**実機**: HEAD 直近 commit の parent (C1) の commit object を削除 → `diff <C1-hash> HEAD` / `diff HEAD <C1-hash>` /
`tag mytag <C1-hash>` の 3 経路すべて `KCS-E-STORE-NOT-FOUND-001` exit 4 (side/復旧文言なし)。`"HEAD"` 文字列
経由の diff は COMMIT-SHALLOW exit 1 + side 明示の対照。

**fix 方針**: `resolve_commit` の 2 箇所 (scope.rs:689,696) と `tag()` の検証読み (scope.rs:662) を、他 8 site と
同じ `is_store_not_found` 捕捉で `KcsError::commit_shallow` に変換 (diff は side a/b、tag は write context を付与)。
回帰テスト: hash リテラル / tag 経由の shallow commit が `diff`/`tag` で COMMIT-SHALLOW exit 1。

## R17-6 [minor] `repair --rebuild-db` の `skipped_units` 報告が、実際には検索可能な (chunks.jsonl のキャッシュ chunk が生存する) 文書まで「要 reindex --force」と誤警告 — false alarm がユーザー/Agent を R17-2 で壊れた reindex --force に誘導する

**発見**: Sonnet-A + 実機。R17-2/R17-4 と同じ「repair/reindex の破損耐性」の縫い目から派生。

**根本原因**: `rebuild_step3_index` (`main.rs:2837-2865`) が normalized-unit 読込失敗を `skipped_units` に記録
するが、`build_sqlite_index_at` (`main.rs:3311`) は chunks.jsonl を無条件に全読みして再インデックスするため、
破損前に既に永続化済みの chunk がそのまま生き残り検索可能なまま。`skipped_units_guidance`「run kcs reindex
--force to re-normalize」は「この文書は現在検索できない」を意味するべきなのに、検索は正常に機能している。しかも
その reindex --force は R17-2 により壊れている (単一破損で scope 全体停止)。

**実機**: 1 文書 index (chunks.jsonl に chunk 永続化) → manifest 破損 + sqlite 削除 → `repair --rebuild-db` が
`skipped_units:[a.md]` + guidance を返すが、直後の `search` は本文を正しく返す (results 1・exit 0)。

**fix 方針**: `attach_skipped_units` で raw_hash ごとに `read_stored_chunks` の生存 chunk を突合し、既存 chunk が
生存している場合は文言を「re-serving cached chunks; normalized source is stale (re-normalize when convenient)」に
弱める (or 別フィールドに分離して「検索は可能・正規化ソースのみ stale」を伝える)。R17-2 の fix と併せ、緊急誘導が
壊れたコマンドを指す連鎖を断つ。回帰テスト: 検索可能な文書は skipped_units の緊急再正規化誘導を出さない。

## R17-7 [minor] R16-7 embedding charge gate のコメント (`main.rs:6822-6828`) が crash-safety を過度に主張 — 「crash-stranded chunk は set に含まれず再予約される」は API 課金後・embeddings commit 前の狭窓では偽 (据え置き triple-fault そのもの)。markdownize は送信前 fallback_reason clear で保護されるのに embedding は非対称に保護漏れ

**収束**: GPT-5.5 (静的) + Opus (静的)。**据え置き済み triple-fault の再評価** (R16 裁定末尾で R17 送り)。

**根本原因**: `reservation_covers_resend` (`main.rs:6848-6860`) は `fallback_reason` が rate_limit/quota の
embedding task を「予約済み」として charge skip する。`batch retry` は task を Pending に戻すが fallback_reason を
消さない。`send_embed_batch` の内部で「API 課金 → embeddings row + chunk_vec の write」の順に進むため、その間
(**課金後・commit 前**) に crash すると embeddings が未 write で、次パスの `plan_embed_batch` は content-addressed
reuse (§5.5) に乗らず to_send に入るが、stale rate_limit reason で charge skip → 再送 (二重課金) だが予約は
据え置き 1x = under-reserve。対照: markdownize は送信前に status=Running + `fallback_reason=None` を**永続化**
(`main.rs:5763-5781`) するため crash 後は再予約する。embedding にはこの pre-send 永続遷移がなく (transition は
`main.rs:6979` でパス末尾に一括 write-back = R11-5 の O(N²) 回避)、保護が欠落。

**位置づけ**: 穴自体は R16 裁定末尾で据え置いた triple-fault (「RateLimit 失敗→retry 送信が server 課金後
commit 前に crash した 1 chunk の有界 under-charge」)。窓は狭く (bill→chunk_vec commit)、被害は per-chunk コスト
小。**コメント 6822-6828 が「crash before the final write は reuse で安全」と自身の安全性を過度に主張している点が
今回の新規指摘** (send_embed_batch **完了後**の crash は reuse で真に安全だが、**内部の課金後・commit 前**の
crash はカバーしない)。通常の crash-safety は content-addressed reuse で正しく担保されている
(オーケストレータが GPT-5.5-1 の当初 major 主張を「通常 crash は reuse で safe」と一旦却下したが、Opus/GPT-5.5 の
「課金後・commit 前」窓の指摘で triple-fault の再評価に統合)。

**fix 方針**: **穴を塞ぐ markdownize 対称化 (embedding 送信前に Running + fallback_reason=None を永続化) は
R11-5 の O(N²) (per-batch tasks.jsonl 全書き) を再導入するため入れない** (per-chunk 永続 marker も同様)。今回は
**コメントの訂正のみ**: 「crash before the final write の reuse 安全性は send_embed_batch 完了後に限る。内部の
課金後・commit 前 crash は R16 で据え置いた triple-fault (有界 under-charge、O(N²) 回避のため per-chunk marker
不使用) に該当する」旨を明記し、markdownize との保護非対称の理由 (embedding は reuse で通常 crash を吸収・
markdownize は送信前 clear で吸収) を残す。据え置き根拠をコードに固定して後続ラウンドの再評価を高速化する。

---

## 却下・据え置き

- **却下 (Spark 検証2(a) の enqueue TOCTOU)**: `budget_remaining_for_adapter` の enqueue 時の cap 読み
  (`main.rs:8886`) は task の初期分類 (Pending vs Paused) のみに使われ **ledger を append しない**。権威的な
  cap 執行は送信時の `charge_cost_ledger_under_lock` (`main.rs:9009`) が device-global lock 下で ledger を再読・
  再評価してから append する (F8)。月内 ledger は append-only で残額は単調減少なので、lock 外の stale 読みは
  「実際より多く残って見える」方向にしか外れず、誤 Pending は送信時ゲートが捕捉、cap silent bypass は生じない。
  Spark 自身も「事前判定ズレを許容」と限定しており実害なし。却下。
- **据え置き (month の月跨ぎ誤記帳)**: `month` が pass 開始時に 1 回計算され (`main.rs:5626` markdownize /
  `main.rs:6815` embedding)、ループ内の全 charge に使い回される。月末に開始した長時間バッチが月をまたぐと、
  翌月分の charge が前月 month で記帳される (Sonnet-C=minor 主張・「ループ前 1 回計算」を file:line 立証)。
  **Opus は「pass 開始時 month 固定で保守側 (二重/欠落なし)」と healthy 判定**。両者「ループ前 1 回計算」は一致し、
  争点は severity。実害は「月跨ぎ長時間 pass の翌月分が前月に逃げ、翌月 cap 判定が緩くなる」有界・稀なケースに
  留まり、charge 総額は正しい (二重/欠落なし)。tasks.jsonl/cost-ledger 月跨ぎの据え置き群 (R13〜R15) と同族の
  月次会計マターとして Step 4 gc/月次境界設計へ送る。ただし「charge 直前に `utc_month(&now_utc_seconds())` 再計算」
  の低コスト修正が R17 fix のついでに拾えるなら拾ってよい (独立所見としては立てない)。
- **参考 (非所見・健全確認)**: R16 fix の本体は 7 エンジンの静的+実機で健全確認 — R16-1 の read degrade/write
  reject (status/log/search degrade + snapshot/index/reindex/repair の COMMIT-SHALLOW)、R16-2 の store_corrupt
  降格の限定性 (schema/programming error は fail-fast 維持)、R16-3 tri-state の ShallowCachedRows 継続、R16-4
  skipped_units と chunks.jsonl 独立性、R16-6 reject_inline_value の 3 パーサ網羅、cost-ledger の F8 lock/UTC
  month/baseline usd=0.0/F3 負値ガード。Tier B secrets-approved の scope_id 束縛と再 init リセットも健全
  (GPT-5.5 + Sonnet-A/D + Opus)。

## エンジン別スコア (参考)

- **Sonnet-B/C/D + GPT-5.5**: R17-1 (resolve_pointer) に 4 エンジン独立収束。B は resolve_commit/tag 漏れ
  (R17-5) も単独立証。C は 3-way 比較 + month (据え置き) 指摘。D は docs 契約 (08 §3.2/03 §480) + R16-1 回帰
  テスト網羅漏れの立証。GPT-5.5 は R17-5/R17-7 も静的で拾う。
- **Sonnet-A**: 別脈 (repair/reindex 破損耐性) で R17-2/R17-4/R17-6 の 3 連発。R16-4 の兄弟穴を掘り当て、
  R9-1 パターン (範囲外からフルスコープが major) を再現。
- **Opus**: R17-3 (phantom charge、単独 major・control 実機) + R17-5/R17-7 収束。cost-ledger 4 巡目の残りを
  直撃。R17-1 は「真正 chunk なので検証弱化なし」と healthy 誤判定 (N5 gen 束縛の迂回を見落とし、オーケストレータが
  実機で反証 = R13/R15 の Opus doc-gap/「問題なし」誤判定型の 3 例目)。
- **Spark**: 範囲限定焦点 (R16 fix の新配線 + cost-ledger 残余) は「確定指摘なし」の健全確認に着地 (R14 型)。
  TOCTOU 1 件は却下。同ラウンドでフルスコープ勢が別脈で major 3 = R9-1 パターン 6 回目。
