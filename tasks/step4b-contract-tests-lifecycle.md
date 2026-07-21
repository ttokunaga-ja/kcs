# Step4b 契約テスト仕様書: tombstone / erase receipt events[] lifecycle

> 本書は **実装より先にテストを固定する** ための契約仕様。Rust 実装コードは含まない。
> 正本は `docs/05-runtime.md` §3.5 (purge の機構 — tombstone/erase receipt lifecycle・purge journal・
> epoch/lifecycle-epoch・resurrection の主源泉)、`docs/10-operations.md` §7.5.1 (fsck の marker validity
> semantic 検証・説明範囲限定・共存修復) と §3 (Scope Registry — 読取系の複合 preflight 順序・
> 返却直前 3 点再検査の固定順、U36 の細部確定に必須)、`docs/08-evidence-pointer-spec.md` §3.1 手順 5
> (canonical final event 正本化と 4 分岐)。各契約は spec の規範文からのみ期待値を導き、実装が
> 「どう書かれそうか」からは導かない。曖昧・spec 沈黙の点は該当契約の「期待」内に `[解釈割れ]` として
> 引用付きで注記し、末尾 §L に一覧化する (勝手に決めない)。

**対象 U 項目 (`tasks/step4b-spec-gap.md`)**: U13, U14, U15, U16, U17, U18, U19, U20, U21, U35, U36, U120
(+ U53 の「判定部」= canonical final event 正本化アルゴリズムと 4 分岐・status 改称 `purged`→`tombstoned`
のみ。U53 のうち evidence verify の 6 値 status union 化・`unverifiable`/`scope_unreachable`/
`registry_duplicate` 等の拡張は別領域 (U48, U54-U58) であり本書スコープ外)。

**対象外 (隣接領域 — 混同注意)**: `kcs open` の object URI/cache 手順 (U22-U24)、restore の退避・隔離・
no-replace publish の具体機構 (U25-U27 — 本書 §I では「barrier 検査の位置」としてのみ触れる)、purge が
削除する object/SQLite/staging の範囲そのもの (U29-U34, U37)、fsck の embedding/manifest/tag 検証拡大
(U39-U42)、`--prune-orphans` (U43)、SQLite schema 変更規約・registry (U45-U47)、evidence pointer 解決の
手順 4/6a/6b/7/8 全体・retarget (U48-U59, 6b は resurrection link の限りで軽く言及)、`rebuild-db` の
publication/introduction 再導出アルゴリズム (U144 — last_lifecycle_epoch 初期化のみ軽く言及)。

## 実装対象ファイルの見込み

- `crates/kcs-core/src/purge.rs` — `TombstoneRecord`/`EraseReceipt` を flat から `events[]` (v2) へ全面
  書換 (v1 読取の正規化含む)、`lifecycle_epoch`/`epoch` field、canonical final event 計算の共有実装、
  `PurgeJournal` の record field 追加 (`purge_id`/`actor`/`target_epoch`/`closure`/`planned_commit`) と
  phase enum の名称・順序変更、`.kcs/purge/epoch` と `.kcs/tombstones/lifecycle-epoch` の読み書き・
  回復ロジック、`retire_erase_receipt` の「物理削除」から「`retired` event append」への転換
- `crates/kcs-core/src/scope.rs` — `ensure_raw_publication_allowed` (2928-2946) の永久ブロック除去、
  `archive_staged_working_tree` (503-570) の retire タイミングをスナップショット finalize 後へ移動
  (現状は raw CAS 書込直後の 554-555 で早すぎる)
- `crates/kcs-cli/src/main.rs` — `ensure_raw_ingest_allowed` (2046-2065、`kcs reindex --force` の
  3591 と incremental indexing pipeline の 11024 から呼ばれる早期ゲート) の同様の転換、
  `enforce_purge_read_barrier` (6639-6647) を 2 点・3 点検査へ拡張、`tombstone_error` (6651-6661) の
  `status` を `"purged"` から `"tombstoned"` へ、`resolve_pointer_for_cli` の手順 5/6b 統合
- `crates/kcs-cli/src/verify_objects.rs` — `validate_tombstone`/`valid_dead_terminal`/
  `validate_erase_receipt`/`check_live_raw_markers` (1441-1560) と coexist 判定 (664-770) を
  canonical final event 基準の 3 分岐修復ロジックへ全面置換
- `crates/kcs-cli/src/restore.rs` — barrier 検査の 2 点固定位置への統合 (深堀りは U26/U27 側)
- `crates/kcs-index/src/fts.rs` — `index_metadata` 表 (新設、`last_lifecycle_epoch` 列) の DDL 追加
- 新規共有モジュールの可能性: canonical final event 計算を `purge.rs` に一本化し、
  `verify_objects.rs`/`main.rs`/`restore.rs` が re-export して使う (U20 の「二用途分離」を実装面で
  裏付けるため、resolver 用 canonical 計算と fsck/re-purge 用の per-marker tail 計算を別関数にする)

## 表記

`### LC<連番> <契約タイトル> [P レベル]` の後に `正本` (§ + 行番号 + 該当規範の 1 文引用) / `前提` /
`操作` / `期待` を置く。P0 = このロットの完了条件、P1 = 推奨 (周辺・堅牢性)、P2 = 参考。
シンボリックな値 (`raw_hash=X`, `commit=Ca` 等) は再現用の実 hash 値ではなく、状態遷移の構造を機械
検証可能な形で固定するための記号。

---

## A. events[] スキーマ (U13 / U14)

### LC1 tombstone events[] の kind enum と交互遷移・active 判定 [P0]
- 正本: 05 §3.5 L907『event は `purged` / `retired` の 2 種で、**active 判定 = 末尾 event が `purged`
  であること** — retire は末尾に `retired` を append し (上書き・削除しない = 退役監査の保全)、
  再 purge はさらに `purged` を append する』
- 前提: raw_hash `X` に対する tombstone レコードが `.kcs/tombstones/ab/cd/<X64>` に存在する。
- 操作: レコードの `events[]` を末尾から走査する。
- 期待: `kind` は `{"purged","retired"}` の閉集合のみ。配列は `purged` で始まり、以後 `purged`/`retired`
  が厳密に交互 (同じ kind が連続しない)。末尾 event の `kind` が `purged` の場合のみ「この tombstone
  単独としては active」と判定してよい (この判定はマーカー単独規則であり、pointer 解決時は §C の
  canonical final event に必ず正本化してから使う — 単独の active 判定で短絡しない)。上書き・削除に
  よる event の消失は許されない (append-only)。

### LC2 erase receipt events[] の kind enum と交互遷移・active 判定 [P0]
- 正本: 05 §3.5 L925-939 (schema_version:2 の JSON 例、events が `erased`→`retired` の順で並ぶ) および
  L907 の tombstone と対称の規則 (10 §7.5.1 L582『tombstone は purged を先頭に purged / retired が交互
  (erased 開始の文法は receipt 専用)』が erase receipt 側の起点を `erased` と定める)。
- 前提: raw_hash `X` に対する erase receipt が `.kcs/purge/erase-receipts/ab/cd/<X64>` に存在し、
  `schema_version: 2` を持つ。
- 操作: `events[]` を末尾から走査する。
- 期待: `kind` は `{"erased","retired"}` の閉集合のみ。配列は `erased` で始まり、以後 `erased`/`retired`
  が厳密に交互。末尾 `kind` が `erased` の場合のみ「この receipt 単独としては active (erase 済み)」と
  判定できる。`schema_version` は `2` (v1 flat との判別は §B)。

### LC3 kind 別必須 field 行列 (base 必須 / 2026-07-19 以降必須 / legacy 許容) [P0]
- 正本: 10 §7.5.1 L557-561『**完全列挙**: purged = `at`・`in_commit`・`reason`・`actor` / erased =
  `at`・`in_commit`・`actor` / retired = `at`・`in_commit`・`actor`・`resurrection_commit`。
  2026-07-19 以降の新規 event は、purged/erased が `epoch` (purge counter)、**erased が `reason`
  (5 値 enum...)**、全種が `lifecycle_epoch` (lifecycle counter — 別系統) も必須 — legacy 欠落行は
  valid だが、各回復の最大値計算には使わない』/ L562『**optional として許可する field = `legacy_reason`**
  (legacy flat 変換で生成された purged / erased event に限る — 新規 purge では禁止)』
- 前提: 任意の marker の任意の event 1 件。
- 操作: kind ごとに required/optional field を突合する。
- 期待: 下表を満たさない event は corruption (§D で判定)。

  | kind | 常に必須 | 新規書込 (legacy 変換以外) でも必須 | legacy 変換由来のみ許容 |
  |---|---|---|---|
  | purged | `at`, `in_commit`, `reason`, `actor` | `epoch`, `lifecycle_epoch` | `legacy_reason` (optional) |
  | erased | `at`, `in_commit`, `actor` | `epoch`, `reason`, `lifecycle_epoch` | `legacy_reason` (optional) |
  | retired | `at`, `in_commit`, `actor`, `resurrection_commit` | `lifecycle_epoch` | (該当なし — retired は legacy 変換からは生まれない) |

  `epoch` は purged/erased のみ (retired には要求されない — 05 §3.5 L942-943 は
  「purged / erased event には...`epoch` として記録する」で retired に触れない)。legacy 変換由来の
  purged/erased event は `epoch`/`lifecycle_epoch` を欠いてもよいが、その場合は §G の各種「最大値」
  計算に算入しない。`legacy_reason` は非 legacy-変換 event に現れたら corruption。

### LC4 lifecycle レコード更新の耐久 primitive と malformed 記録の fail-closed [P0]
- 正本: 05 §3.5 L907『**lifecycle レコードの更新 (retire・再 purge・legacy 変換) は `.kcs/.lock` 下で、
  temp 書込 → file fsync → atomic rename → 親 directory fsync で行う**([04-pipeline.md §1.1] と同じ
  規律)。malformed・途中破損 (torn JSON) の record は `KCS-E-STORE-CORRUPT-001` として fail-closed に
  扱う』
- 前提: tombstone または erase receipt への `retired` append・再 purge の `purged`/`erased` append・
  legacy 変換のいずれかを実行しようとしている。呼び出し元は `.kcs/.lock` を保持している。
- 操作: (a) 正常系でレコードを更新する。(b) レコードファイルを途中で truncate した torn JSON へ
  差し替えてから読み取る。
- 期待: (a) 更新は temp 書込 → fsync → atomic rename → 親 dir fsync の順で行われ、lock 非保持での
  呼び出しは許可されない (呼び出し規約違反)。(b) torn JSON の読み取りは `KCS-E-STORE-CORRUPT-001` を
  返し、他の event へのフォールバックや部分読み取りは行わない。

---

## B. legacy v1→v2 変換 (U13 / U14)

### LC5 v1 flat tombstone の「purged event 1件」読取とロック下ワンショット変換 [P0]
- 正本: 05 §3.5 L907『events を持たない旧 flat 形式は「purged event 1 件」として読み、**次の
  mutation 時に一回だけ events 形式へ変換する**(legacy)』
- 前提: `.kcs/tombstones/ab/cd/<X64>` が現行 (Step 4a 以前) の flat schema
  (`raw_hash`/`purged_at`/`purged_reason`/`purged_in_commit`、`events` フィールド無し) のまま残っている。
- 操作: (a) 読取専用コマンド (例: `kcs evidence verify`) で resolve する。(b) その後、当該 raw_hash に
  触れる何らかの locked mutation (retire・再 purge・他 raw の purge で journal 経由は対象外、この
  marker 自身に触れる書込) を実行する。
- 期待: (a) の時点ではオンディスク表現は変更されない (読取専用は書き込まない) が、in-memory では
  `events: [{kind:"purged", at:purged_at, in_commit:purged_in_commit, reason:purged_reason,
  actor: <出典無ければ省略可>}]` の 1 要素配列として扱われ、末尾 = purged なので active。(b) の
  mutation 完了後はオンディスクが v2 events[] 形式に置換されており (§A4 の耐久 primitive で)、
  再度読んでも同じ 1 要素からの変換結果になる (二重変換によるイベント重複が起きない — 一回きり)。

### LC6 v1 flat erase receipt (schema_version=1) の「erased event 1件」読取とワンショット変換 [P0]
- 正本: 10 §7.5.1 L574-576『**v1 flat (`erased_at` / `purged_in_commit`)**: 「erased event 1 件」に
  正規化してから同じ検証器に通す (v1 に reason は無い — 変換で `reason: "other"` を合成し legacy 警告
  として報告、[05-runtime.md §3.5] と同一規則)』/ 05 §3.5 L950『v1 に reason は存在しないため変換では
  `reason: "other"` を合成し legacy 警告として報告する』
- 前提: `.kcs/purge/erase-receipts/ab/cd/<X64>` が現行 schema (`schema_version:1`,
  `raw_hash`/`purged_in_commit`/`erased_at`、reason フィールド無し) のまま残っている。
- 操作: LC5 と同様、読取後に locked mutation を経由させる。
- 期待: 変換結果は `events: [{kind:"erased", at:erased_at, in_commit:purged_in_commit, actor:<省略可>,
  reason:"other"}]`。`legacy_reason` は付与されない (v1 receipt には保全すべき自由文原値が元々存在
  しないため — tombstone 側の LC7 と対比)。変換後 `schema_version` は `2` になる。

### LC7 reason マッピングと legacy_reason 制約・legacy 警告の exit 非影響 [P1]
- 正本: 05 §3.5 L907『5 値 enum 外の自由文 reason は `other` へ正規化し、原値を optional
  `legacy_reason` に保全する — 閉 enum は新規書込の規則であり、旧値の読取は other 扱い (表示は原値可・
  fsck は corruption にせず警告)』/ 10 §7.5.1 L527-528『legacy 警告 (path / reason) は exit に影響
  しない — 破損とは別に種別ごとの件数を表示する』(この一文は §7.5.1 全体の一般規則だが、tombstone/
  receipt の legacy reason 警告もこの「exit 非影響」規則の対象に含まれる — 破損検出とは別カウンタ)。
- 前提: v1 tombstone の `purged_reason` が 5 値 enum (`legal|privacy|misingest|copyright|other`) の
  いずれか。別の前提として `purged_reason` がそれら以外の自由文 (例: `"policy-cleanup"`)。
- 操作: LC5 と同じ変換を実行し、続けて `kcs repair --verify-objects` を実行する。
- 期待: enum 内の値はそのまま `reason` にマッピングされ `legacy_reason` は付与されない。enum 外の値は
  `reason:"other"` + `legacy_reason:"policy-cleanup"` となる。いずれの場合も fsck はこの legacy 変換を
  corruption として扱わず、legacy 警告件数として個別に計上するのみで、他に破損が無ければ exit code は
  変化しない (0 のまま)。`legacy_reason` を新規 purge (v1 由来でない purged/erased event) に付けると
  それ自体が corruption (§A3)。

---

## C. canonical final event 正本化と 4 分岐 (U53 の判定部)

### LC8 canonical final event の定義 (全 marker 集約・lifecycle_epoch 最大・tombstone tie-break) [P0]
- 正本: 08 §3.1 手順 5 L179-182『まず、存在する全 marker (tombstone / erase receipt) の最終 event を
  1 つに正本化する — canonical final event = 全 marker 中で `lifecycle_epoch` 最大の最終 event
  ([05-runtime.md §3.5]。legacy の epoch 欠落は 0 とみなし、同値は tombstone 側を優先する決定的
  tie-break。resurrection link も canonical final event のものを採用する)』
- 前提: raw_hash `X` について tombstone と erase receipt の双方 (またはどちらか一方) が存在しうる。
- 操作: 両 marker (存在するものすべて) の末尾 event の `lifecycle_epoch` を比較する。
- 期待: (a) 両方存在し値が異なる場合、大きい方の marker の末尾 event が canonical。(b) 両方存在し
  値が等しい場合 (legacy 欠落同士の 0=0 を含む)、tombstone の末尾 event が canonical (receipt ではない)。
  (c) 一方のみ存在する場合、その末尾 event がそのまま canonical。(d) resurrection_commit 等の付随情報
  も canonical 側の値を採用し、非canonical 側の値と混在させない。

### LC9 正本化に参加できるのは検証通過 marker のみ [P0]
- 正本: 08 §3.1 手順 5 L183-187『正本化の入力は event 検証 (kind 別必須 field・遷移文法・in_commit /
  purged_raws membership / at — 05-runtime.md §3.5 の validity、正本は 10-operations.md §7.5.1) を
  通過した marker のみ — 検証失敗の marker は `KCS-E-STORE-CORRUPT-001` で終端し、canonical 判定に
  参加させない (fsck と resolver で扱いを割らない)』
- 前提: tombstone は §D の検証を通過するが、erase receipt の `in_commit` が指す commit が
  ref-reachable でない (検証失敗)。
- 操作: 当該 raw_hash の pointer を resolve する。
- 期待: 検証失敗した erase receipt は集約対象から除外され、tombstone 側の末尾 event のみが
  canonical final event の候補になる ⇒ そのまま (a) tombstone 有効なら tombstone 応答。ただし
  検証失敗の erase receipt 自体は黙って無視されるのではなく、`KCS-E-STORE-CORRUPT-001` として
  即座に終端する経路も規範上存在する (「終端し」の字義どおり、resolver がこの marker 検証を
  自ら行う場合は corruption を報告して打ち切る。両方の marker が検証失敗なら resolver は
  corruption で終端し、canonical 判定自体に進めない)。この判定不参加規則は fsck (§F) にも
  resolver にも同一に適用される (呼び出し元で寛容さを変えない)。

### LC10 正本化の worked example (spec 記載の tombstone purged@10 / receipt retired@11) [P0]
- 正本: 08 §3.1 手順 5 L187-190『(§3.2 の解決成功条件「raw object が存在」をここで検査する — (i) が
  個別 marker の末尾で先に短絡しない: 例えば tombstone 末尾 purged@epoch10 + receipt 末尾
  retired@epoch11 は canonical = retired であり (iii) 側)』
- 前提: raw_hash `X` に対し、tombstone の末尾 event が `{kind:"purged", lifecycle_epoch:10}`、erase
  receipt の末尾 event が `{kind:"retired", lifecycle_epoch:11}` (両方とも検証通過)。
- 操作: `X` を指す pointer を resolve する。
- 期待: canonical final event は receipt 側の `retired@11` (lifecycle_epoch がより大きい)。したがって
  tombstone の末尾が `purged` であっても resolver は分岐 (i) (tombstone 応答) を選ばない — 「tombstone
  の末尾だけを見て tombstoned と短絡する」実装は本例で誤りと判定される。分岐 (iii) (retired) に進む。

### LC11 分岐 (i): purged → tombstone 応答・status "tombstoned" への改称 [P0]
- 正本: 08 §3.1 手順 5 L191『(i) canonical final event = `purged` (active な tombstone) なら →
  tombstone を返す (§4)』/ 08 §4.1 L307『レスポンス body の `status` は §4.3 の union と同じ語彙
  (`tombstoned`) を使う — purge の事実は `purged_*` フィールドが表す』
- 前提: raw_hash `X` の canonical final event が `purged`。
- 操作: (a) `kcs evidence verify` で resolve する。(b) `kcs open`/`kcs view`/`kcs restore` に `X` を
  指す pointer を渡す。
- 期待: (a)(b) いずれも応答本体の `status` は文字列 `"tombstoned"` (`"purged"` ではない)。purge の
  事実は `purged_at`/`purged_reason`/`purged_in_commit` 等の別フィールドで表現する。
  **現行実装との既知の不整合に注意**: `crates/kcs-cli/src/verify_objects.rs:193` の evidence verify
  経路は既に `"tombstoned"` を返すが、`crates/kcs-cli/src/main.rs:6651-6654` の `tombstone_error`
  (open/view/restore 系の dead-pointer エラー化に使われる) は `object.insert("status".to_owned(),
  json!("purged"))` のままであり、本契約はこの不整合を解消することを要求する (両経路が同じ
  `"tombstoned"` を返すことが期待値)。

### LC12 分岐 (ii): erased かつ raw 不在 → not_found / PURGE-NOT-FOUND [P0]
- 正本: 08 §3.1 手順 5 L192『(ii) canonical final event = `erased` (active な erase receipt) で
  raw object が不在なら not_found — `KCS-E-PURGE-NOT-FOUND-001` (§4.2 の表と同一の終端)』
- 前提: raw_hash `X` の canonical final event が `erased`。raw object `X` は CAS に存在しない。
- 操作: `X` を指す pointer を resolve する。
- 期待: `status:"not_found"`, `error_code:"KCS-E-PURGE-NOT-FOUND-001"`。tombstone 応答 (§4.1 の
  `purged_*` フィールド) は含まれない — erase receipt は非公開 marker であり、この応答からその
  存在・内容を外部に開示しない。

### LC13 分岐 (iii): retired → raw 存在の事前必須検査・不在は STORE-CORRUPT [P0]
- 正本: 08 §3.1 手順 5 L194-198『(iii) canonical final event = `retired` なら tombstone 扱いしないが、
  手順 6 へ進む**前に raw object の存在を検査する**(resurrection 後の旧 pointer を alive に戻すための
  必須条件)。**不在なら not_found — `KCS-E-STORE-CORRUPT-001`**(retired 後の再作成分の欠落は
  corruption — 10-operations.md §7.5.1 と整合。chunk object が残存していても本文を返さない)』
- 前提: raw_hash `X` の canonical final event が `retired`。
- 操作: (a) raw object `X` が CAS に存在する状態で resolve する。(b) raw object `X` が (何らかの理由で)
  存在しない状態で resolve する (retire 後に raw が壊れた/消えた異常系)。
- 期待: (a) 手順 6 (tree entry 解決) 以降へ進む。(b) `status` は `"not_found"` 相当だが
  `error_code:"KCS-E-STORE-CORRUPT-001"` (分岐 (ii) の `KCS-E-PURGE-NOT-FOUND-001` とは異なるコード —
  正当な purge 済み欠落ではなく異常な欠落として区別する)。chunk object 自体が偶然残っていても、この
  raw 不在の時点で本文を返さず打ち切る。

### LC14 分岐 (iv) と非該当時の通常 alive 経路 [P0]
- 正本: 08 §3.1 手順 5 L199-204『(iv) marker (tombstone / erase receipt) が無いのに raw object が
  不在なら not_found — code は `KCS-E-STORE-CORRUPT-001`(...)**(i)〜(iv) のいずれにも該当しない場合**
  (marker が無い・または active な erase receipt があっても raw object が存在する場合を含む) は raw
  object が存在する通常状態であり、手順 6 へ進む』
- 前提: (a) raw_hash `X` に marker が一切存在せず、raw object も CAS に存在しない。(b) marker が
  一切存在せず raw object は存在する。(c) canonical final event が `erased` だが raw object が
  (再 ingest 等により) 存在する。
- 操作: それぞれ `X` を指す pointer を resolve する。
- 期待: (a) `KCS-E-STORE-CORRUPT-001` (marker なしの欠落は corruption の疑い、`kcs repair
  --verify-objects` を案内)。(b) どの分岐にも該当しない ⇒ 通常の手順 6 へ進む。(c) `erased` は
  分岐 (ii) の条件 (raw 不在) を満たさないため分岐しない ⇒ 通常の手順 6 へ進む (erase receipt は
  re-ingest barrier ではないため、raw が存在すればそれを alive として扱ってよい — §E15 の resurrection
  とは別に、erase receipt が retire される前でも raw が物理的に存在すれば手順 6 が動く点に注意。
  ただし §E の正規フローでは republication 時に同一 locked mutation で retire も行われるため、この
  「retire 未了なのに raw だけ存在する」状態は主に crash 直後の過渡的窓に限られる)。

---

## D. marker validity の意味論的検証 (U16)

### LC15 schema_version 分岐 (v2 直接 / v1 正規化) と単一 validator [P0]
- 正本: 10 §7.5.1 L556『erase receipt の validation は schema_version で分岐する』/ L574-577『v1 flat
  ...「erased event 1 件」に正規化してから同じ検証器に通す』/ L577『**tombstone lifecycle にも同じ
  event 検証を適用する**』
- 前提: (a) v2 events[] の tombstone/receipt。(b) v1 flat の tombstone/receipt。
- 操作: 両方に同一の validator 関数を通す。
- 期待: (a) はそのまま events[] を検証する。(b) は §B の正規化 (1 要素配列化) を経てから **同じ**
  validator に通る — tombstone と erase receipt とで検証ロジックが分岐実装されていたり、v1/v2 で
  別のチェック関数が使われることは契約違反 (単一 validator + 入力正規化という構造を要求する)。

### LC16 kind 別必須 field 欠落の corruption 判定 [P0]
- 正本: 10 §7.5.1 L556-562 (§A3 と同一引用元)。
- 前提: §A3 の表で必須とされる field を 1 つ欠く event (例: `retired` から `resurrection_commit` を
  除いたもの)。
- 操作: 検証する。
- 期待: `KCS-E-STORE-CORRUPT-001`。「常に必須」列の field 欠落はどのような書込経路 (新規/legacy 変換)
  でも許されない。「新規書込でも必須」列は legacy 変換由来の event でのみ欠落を許容する (§A3)。

### LC17 in_commit の bounded verified CAS・ref-reachable・commit_type=purged・purged_raws membership [P0]
- 正本: 10 §7.5.1 L564-566『`erased` event の `in_commit` が bounded verified CAS で ref-reachable な
  `commit_type=purged` commit を指すこと、当該 commit の `purged_raws` に対象 raw_hash が含まれる
  こと』/ L578-580『purged event の `in_commit` が bounded verified CAS で ref-reachable な
  `commit_type=purged` commit を指すこと・当該 commit の `purged_raws` への raw_hash membership』/
  03 §8 L705『`commit_type=purged` の commit は **`purged_raws`...を必須 field に持つ**』
- 前提: (a) `in_commit` が指す commit が存在しない、または ref から到達不能。(b) commit は存在し
  ref-reachable だが `commit_type` が `"purged"` ではない (例: `"manual"`)。(c) commit は存在し
  `commit_type="purged"` だが `purged_raws` 配列に当該 raw_hash が含まれない (別 raw の purge commit を
  流用した偽装)。(d) 全条件を満たす正常系。
- 操作: purged event / erased event それぞれについて検証する。
- 期待: (a)(b)(c) いずれも corruption (`KCS-E-STORE-CORRUPT-001`) で marker は canonical 正本化に
  不参加 (§C9)。(d) のみ検証通過。この検証は purged・erased の両 kind に同一に適用する
  (`commit_type` は常に `"purged"` — erase モードでも別の commit_type は存在しない)。

### LC18 at の canonical UTC・commit created_at 一致・invocation fixed now 非未来 [P0]
- 正本: 10 §7.5.1 L567-568『各 `at` が canonical UTC でその event の commit `created_at` と一致し
  invocation の fixed now より未来でないこと』/ 12.4 L961-965 (canonical UTC の正誤表記例)
- 前提: (a) `at` が `in_commit` の指す commit の `created_at` と 1 秒でも異なる。(b) `at` が
  `+09:00` 等ローカルオフセット表記 (canonical UTC でない)。(c) `at` がコマンド invocation 時点の
  fixed now より未来。(d) 全条件を満たす正常系。
- 操作: 各 event を検証する。
- 期待: (a)(b)(c) いずれも corruption。「invocation の fixed now」は当該コマンド呼出開始時に 1 回
  だけ固定される時刻であり、検証対象 event ごとに `SystemTime::now()` を再取得して比較してはならない
  (同一 invocation 内で複数 event を検証する場合、比較基準は不変)。

### LC19 events[] 遷移文法 (先頭 kind と交互則) [P0]
- 正本: 10 §7.5.1 L568-569『event 列が有効な遷移 (erased を先頭に erased / retired が交互 — 末尾
  event が現況) であること』/ L582『tombstone は purged を先頭に purged / retired が交互 (erased
  開始の文法は receipt 専用)』
- 前提: (a) tombstone の events[] が `retired` で始まる。(b) tombstone の events[] に `purged` が
  2 回連続する (間に `retired` が無い)。(c) erase receipt の events[] が `purged` で始まる (marker
  種別を跨いだ kind の混入)。
- 操作: それぞれ検証する。
- 期待: (a)(b)(c) いずれも `KCS-E-STORE-CORRUPT-001`。tombstone の events[] に `erased` kind が
  現れること自体が既に corruption (marker 種別ごとに許容 kind の集合が異なる)。

### LC20 terminal retired の resurrection_commit 検証 (ancestry + tree 存置時の leaf 検証) [P0]
- 正本: 10 §7.5.1 L569-573『terminal `retired` の `resurrection_commit` が ref-reachable で、**直前の
  erased / purged event の `in_commit` を ancestor に持つ (= 当該 purge より後の publication である)**
  ことを必須とする (**resurrection_commit の verified tree が同一 raw_hash の leaf を含むことを tree
  存置時に限り検証する** — auto 型 publication commit は shallow 化で tree を失い得るため tree 不在時
  は本検証を省略する。defense-in-depth、08-evidence-pointer-spec.md 手順 8 と同型)』
- 前提: 同一 marker の events[] が `[..., {kind:"purged"|"erased", in_commit:Cp}, {kind:"retired",
  resurrection_commit:Cr}]`。
- 操作: (a) `Cr` が ref-reachable でない。(b) `Cr` は ref-reachable だが `Cp` を ancestor に持たない
  (`Cr` が `Cp` より古い、または無関係な枝)。(c) `Cr` の tree が (shallow 化されず) 存置されており、
  raw_hash `X` を指す leaf を含まない。(d) `Cr` の tree が shallow 化され失われている。(e) 全条件を
  満たす正常系。
- 期待: (a)(b) は corruption。(c) も corruption (defense-in-depth 検証の不一致)。(d) は tree 不在の
  ため leaf 検証を **省略**し、他条件のみで判定する (省略は「検証失敗」ではなく「検証対象外」— このケース
  単独では corruption にしない)。(e) は検証通過。ここでいう「直前の erased/purged event」は **同一
  marker の events[] 内で resurrection_commit を持つ retired event の直前要素** を指し、§C の
  cross-marker canonical final event とは別の、単一 marker 内の構造検証である (§E20 note 参照)。

### LC21 検証失敗 marker は入口非依存で corruption (fsck/resolver/re-purge 統一) [P1]
- 正本: 05 §3.5 L907『**検証失敗の marker は入口を問わず (fsck・resolver・再 purge) 説明能力を持たない
  corruption (`KCS-E-STORE-CORRUPT-001`) とする**』/ 10 §7.5.1 L583-584『検証失敗の marker は説明能力
  を持たず corruption とする — 偽 `in_commit` を持つ構造的に正しい tombstone が genuine missing を
  隠さない』
- 前提: §D の検証を 1 つでも満たさない tombstone または erase receipt。
- 操作: (a) `kcs repair --verify-objects` から検証する。(b) `kcs evidence verify` (resolver) から
  検証する。(c) `kcs purge --raw-hash X` (再 purge、marker 自身の lifecycle 管理) から検証する。
- 期待: (a)(b)(c) すべて同一の corruption 判定・同一の `KCS-E-STORE-CORRUPT-001` を返す。3 つの
  呼び出し元が独立に緩い/厳しい判定基準を持つことは許されない (単一 validator の共有実装を要求する
  構造的契約 — §D15 と対)。

---

## E. U19: tombstone retire (resurrection) — 永久ブロックの廃止と転換

> **この節が本書で最も重要 (発注側の明示指示)**。旧 spec / 現行実装は「public tombstone が付いた
> raw_hash への同一バイト再 ingest を恒久的に拒否する」だったが、新 spec はこれを **完全に反転**し、
> 「再 publication を許可し、その publication と同一の locked mutation 内で tombstone を retire する」
> 方式へ転換する。以下の全 LC は 05-runtime.md §3.5 L747-786 の単一の長い段落から導出する。

### LC22 [転換] 同一バイト再 ingest の恒久拒否を廃止 [P0]
- 正本: 05 §3.5 L747-749『同一 raw_hash の raw object が再 publication された場合、その publication
  と同一の locked mutation 内で active tombstone を**退役 (retire) させる**』(= 拒否ではなく許可し
  た上で退役させる、という前提そのものが「拒否しない」ことを含意する)。対比: 08 §4.2 L336-338
  『同一 bytes が後日再 ingest され...同じ identity の chunk が再生成された場合、既存 pointer は
  再び alive として解決される (このとき active tombstone は raw の再 publication と**同時に退役**する
  — resurrection 規則。**退役なしには「tombstone 最優先」の解決と両立しない**)』
- 前提: raw_hash `X` に active tombstone (canonical final event = `purged`) がある。working tree に
  `X` と同一バイト列のファイルが (再度) 存在する。
- 操作: `kcs index` (通常スキャン経由の再取り込み) または明示的な再 ingest 操作を実行する。
- 期待: 取り込みは **成功する** (エラーで止まらない)。**現行実装との既知の矛盾**:
  `crates/kcs-core/src/scope.rs:2937-2944` の `ensure_raw_publication_allowed` は
  `purge.read_tombstone(raw_hash)?.is_some()` の場合に `KCS-E-PURGE-TOMBSTONED-001`/
  `ExitCode::PermanentFailure` で即座に拒否しており、これは本契約に反する (廃止対象)。
  `crates/kcs-cli/src/main.rs:2043-2065` の `ensure_raw_ingest_allowed` (doc comment:
  「Public tombstones permanently reject identical-byte re-ingest」— `kcs reindex --force` (main.rs:3591)
  と incremental indexing pipeline (main.rs:11024) の早期ゲートとして使われる) も同型の恒久拒否を
  行っており、同様に取り込みを継続させる方向へ転換が必要。**barrier_blocks (active journal による
  一時ブロック、`KCS-E-PURGE-INCOMPLETE-001`) は本契約と無関係で維持される** — 廃止対象は
  tombstone の存在そのものによる恒久拒否のみ。

### LC23 retire append は再 publication の snapshot finalize 完了後・同一 locked mutation 内 [P0]
- 正本: 05 §3.5 L749-751『**耐久順序**: retire の append は再 publication の snapshot finalize (§8.1
  — chunks.jsonl → SQLite → commit / ref publish) の**完了後**に行う』
- 前提: LC22 の取り込みが raw CAS への書込・normalize・chunk 生成を経て snapshot finalize (chunks.jsonl
  追記 → SQLite Tx → commit 作成 → ref (HEAD) publish) に至る。
- 操作: retire (`retired` event の append) が実行されるタイミングを観測する。
- 期待: retire append は commit/ref publish が完了した **後** に実行され、同一の locked mutation
  (同じ `.kcs/.lock` 保持区間) 内で完結する。raw CAS 書込の直後 (finalize 前) に retire するのは契約
  違反 — **現行実装との既知の不整合**: `crates/kcs-core/src/scope.rs:554-555` は raw CAS 書込
  (`write_raw_reader`) 直後に `purge.retire_erase_receipt(&published_hash)` を呼んでおり、これは
  snapshot finalize (commit/ref publish) より **前** の時点であるため、本契約に合わせて finalize 後
  へ移動する必要がある。

### LC24 crash-safe: finalize〜retire 間の crash は tombstone active 維持 [P0]
- 正本: 05 §3.5 L751『間で crash した場合は tombstone が active のまま残る (安全側 — 解決は
  tombstoned)』
- 前提: LC23 の finalize が完了した直後 (commit/ref は publish 済み) に、retire append が実行される
  前にプロセスが crash する。
- 操作: プロセス再起動後、`kcs evidence verify` で raw_hash `X` を resolve する。
- 期待: tombstone はまだ retire されていない (events[] 末尾は依然 `purged`) ため canonical final event
  は `purged` のまま ⇒ `status:"tombstoned"` を返す (raw が物理的には alive でも安全側に倒れる)。
  これは実装バグではなく仕様上の意図した挙動であり、この状態を「バグとして自動修復しようとする」
  実装 (例: 読取コマンドが自ら retire を試みる) は契約違反 — 補完は §E27 の locked mutation/fsck
  経由でのみ行う。

### LC25 retire 直後・同一 mutation 内での index_generation 回転 [P0]
- 正本: 05 §3.5 L752-753『retire append の完了時に index_generation を新規採番する (§1.5 —
  finalize〜retire 間に発行された cursor の replay が、退役後の可視集合で別 stream を再計算すること
  を拒否で防ぐ)。回転は retire append と同一 locked mutation 内で直後に行う』/ 05 §1.5 L180-184
  『tombstone lifecycle の更新 (retire・再 purge — ...)...のいずれでも新規採番する ULID』
- 前提: LC23 の retire append が成功する。finalize 完了〜retire 完了の間に (別プロセスの読取で)
  1 ページ目の検索 cursor が発行されていたとする。
- 操作: retire append 完了後、その cursor で `kcs search --cursor <token>` の 2 ページ目を要求する。
- 期待: `index_metadata.index_generation` は retire append と同一 locked mutation 内で新しい ULID
  に回転済み。cursor の `index_generation` は古い値のままのため `KCS-E-SEARCH-CURSOR-001` で拒否される
  (再検索が正)。

### LC26 lifecycle-epoch counter の書込順序と回復 (counter 先行 fsync → event 記録、write 系起動時補完) [P0]
- 正本: 05 §3.5 L758-761『append と回転の間で crash した場合は、書き込み系コマンド冒頭の回復が
  **counter > last_lifecycle_epoch** を検出して回転を補完する』/ L761-764『**counter の耐久順序と
  回復**: counter の +1 (fsync) を event append より先に行い、**全ての新規 lifecycle event...に、
  その時点の counter 値を `lifecycle_epoch` として必須記録する**』
- 前提: retire (または再 purge・legacy 変換) を実行しようとしている。
- 操作: 正常系の書込順序を観測する。crash 注入: lifecycle-epoch counter の fsync 完了直後、
  index_metadata.last_lifecycle_epoch を反映する SQLite Tx が完了する前に crash させる。
- 期待: 正常系では (1) `.kcs/tombstones/lifecycle-epoch` を +1 して fsync、(2) その incremented 値を
  当該 event の `lifecycle_epoch` field として書き込む、の順で行われる (逆順は禁止)。crash 注入後、
  次に起動される **書込系**コマンドの冒頭回復が `counter > last_lifecycle_epoch` を検出し、
  index_generation の回転を補完してから処理を続行する (§G7 と対)。

### LC27 backfill の 3 要件充足で retired 補完 (canonical=purged のまま × verified raw × ancestor-respecting republication commit) [P0]
- 正本: 05 §3.5 L772-776『次回の locked mutation または fsck が「canonical final event が `purged`
  のままの tombstone × **verified raw (content hash 検証済み) の存在** × 同一 raw の ref 到達可能な
  再 publication commit **であって、canonical final purged event の `in_commit` を ancestor に持つ
  もの (= 当該 purge より後の publication)**」を検出したら retired event を補完する』
- 前提: LC24 の crash 後、後続の別 locked mutation (例: 他ファイルの `kcs index`) または
  `kcs repair --verify-objects` が実行される。raw_hash `X` は content hash 検証済みで CAS に存在
  (verified raw)。ref 到達可能な commit `C2` が存在し、`C2` は canonical final purged event の
  `in_commit` (= `Cp1`) を ancestor に持つ (= `Cp1` より後の publication)。
- 操作: その locked mutation / fsck を実行する。
- 期待: tombstone の events[] へ `{kind:"retired", in_commit:C2, resurrection_commit:C2, ...}` が
  append される。以後の resolve は canonical final event = `retired` となり alive を返す (§C13, §E31)。

### LC28 backfill 非実施: raw 未検証 [P0]
- 正本: 05 §3.5 L775-776『raw が欠落・破損のままの補完は不可 — tombstone を誤って退役させない』
- 前提: LC27 と同じ状況だが、raw_hash `X` の CAS object が欠落しているか、content hash 再計算が
  一致しない (verified でない)。
- 操作: locked mutation / fsck を実行する。
- 期待: retired は append **されない**。tombstone は `purged` のまま (active) を維持する。

### LC29 backfill 非実施: 有効 commit 無し → incomplete purge exit 3 [P0]
- 正本: 05 §3.5 L777-778『**この因果条件を満たす再 publication commit が無い共存は incomplete purge
  (exit 3) であり補完しない**』
- 前提: raw_hash `X` は verified (content hash 検証済み) だが、canonical final purged event の
  `in_commit` を ancestor に持つ ref 到達可能な republication commit が **存在しない** (例: raw が
  purge とは無関係な経路で store 外から直接置かれた、または republication commit がまだ finalize
  されていない)。
- 操作: `kcs repair --verify-objects` を実行する。
- 期待: retired は append されない。fsck は当該 raw_hash を **incomplete purge** として report し
  (finding または専用フィールド)、コマンド全体の exit code は **3** (他に corruption が無くても)。
  回復手段として `kcs purge --raw-hash X` の再実行 (冪等) を案内する (§F16, §J58 と一貫)。

### LC30 回帰シナリオ: 旧 resurrection commit が新 purge の backfill を誤って満たさない [P1]
- 正本: 05 §3.5 L778-779『**この因果条件が無いと、再 purge 後も ref に残る過去の resurrection commit
  を誤検出して、新しい tombstone を退役させてしまう**』
- 前提: 以下の DAG を構築する: `C1` (raw `X` を publish) → `Cp1` (purge `X`, `commit_type=purged`,
  parent=`C1`) → tombstone events = `[{purged, in_commit:Cp1}]` → `C2` (`X` を再 publish, parent は
  `Cp1` を祖先に持つ, 同一 locked mutation で retire) → tombstone events = `[{purged,in_commit:Cp1},
  {retired,in_commit:C2,resurrection_commit:C2}]` → `Cp2` (`X` を再度 purge, `commit_type=purged`,
  parent は `C2` を祖先に持つ) → tombstone events = `[..., {purged,in_commit:Cp2}]` (canonical final
  event は再び `purged`, in_commit=`Cp2`)。`C2` は ref (HEAD 系譜) から引き続き到達可能 (履歴は
  書き換えない — 05 §3.5 の DAG 非書換原則)。
- 操作: `Cp2` が canonical final purged event である状態で `kcs repair --verify-objects` (または
  次の locked mutation) を実行する。
- 期待: `C2` は `Cp2` の **ancestor** であって descendant ではない (`C2` が先, `Cp2` が後) ため、
  「`Cp2` (canonical final purged event の in_commit) を ancestor に持つ ref 到達可能な republication
  commit」の条件を `C2` は満たさない。したがって `C2` を resurrection_commit として retired を誤って
  append することはない。verified raw `X` が存在するとしても、`Cp2` より後の正当な republication
  commit が (まだ) 無ければ LC29 と同じ incomplete purge exit 3 になる。

### LC31 retire/backfill 後の解決は alive・resurrection_commit リンクが旧 pointer 復活の唯一経路 [P0]
- 正本: 05 §3.5 L779-781『以後の open / view / verify / 解決は alive を返す(退役なしには
  「tombstone 最優先」の解決規則と上記の「再び alive」が両立しない)。**retired event には
  `resurrection_commit`...を記録する** — purge 前 commit を指す旧 pointer の解決は、このリンクを
  介してのみ新 publication を参照できる (08 §3.1 手順 6b。検索の時点条件には影響せず、旧時点への
  遡及混入は起きない)』/ 08 §3.1 手順 6b L230-232『retired event に `resurrection_commit` があれば、
  そのリンク先 commit の publication を参照して本文を解決し alive を返してよい』
- 前提: LC23 (同一 mutation) または LC27 (backfill) のいずれかで tombstone が retire 済み。pointer
  `P` は purge **前** の古い commit `C1` を指している (purge により `C1` の manifest は欠落済み)。
- 操作: `P` を resolve する。
- 期待: canonical final event = `retired` ⇒ raw 存在確認 (§C13) を経て手順 6 へ進み、manifest 欠落は
  6b で `resurrection_commit` (= `C2`) 経由の直接解決へ降格し `alive` を返す (`manifest_missing:true`
  を伴う — 深い挙動は 08 §3.1 手順 6b 自体の管轄で本書は概要のみ確認)。この resurrection link は
  **pointer 解決専用**であり、search の時点条件 (`--at`/time-travel の可視集合計算) には一切影響
  しない — 古い commit `C1` の時点で検索した場合に `X` が「purge 済みなのに見える」ようになることは
  ない。

### LC32 復活後本文の byte 非保証 (raw 同一・normalized 非同一) [P1]
- 正本: 05 §3.5 L781-784 (「復活後に解決される本文は再生成 instance のものであり、purge 前と byte
  同一である保証はない」相当の文が続く。厳密には L169 の 08 §3.1 手順 5 直下注記との整合として
  05 §3.5 全体の帰結) — 直接一次引用は 08 §4.2 L340-342『ただし **復活後に解決される本文は再生成
  instance のものであり、purge 前と byte 同一である保証はない**(Markdown content hash 不採用の帰結
  — 03-data-model.md §5)』
- 前提: purge 前に raw `X` を Markdownize した normalized instance `gen=0` が存在した。resurrection
  後、`X` は再度 Markdownize され `gen=N` (N>0) の新しい normalized instance を持つ。
- 操作: resurrection 後に `X` の chunk 本文を open/view で取得する。
- 期待: raw bytes (`raw_hash`) は purge 前と完全に同一であることが保証される (同一 raw_hash なら
  同一バイト列 — content-addressed の定義上必然)。しかし Markdown/chunk のテキストは `gen=0` 時点の
  ものと byte 一致する保証は **無い** (LLM 生成の非決定性、`normalized_hash` 不採用の帰結)。この
  非保証はドキュメント化された仕様であり、実装がテキスト差分を「バグ」として扱うことは誤り。

### LC33 erase receipt の対称 resurrection・非除去の恒久化 [P0]
- 正本: 05 §3.5 L956『erase receipt も tombstone と同じ lifecycle 形式 (events[]) を持ち、raw object
  の再 publication 成功時は除去せず `retired` event を append する — 除去すると erase 済み raw の旧
  commit が参照する manifest 欠落を説明するものが消え、fsck の corruption 誤判定と手順 6b の不達を
  生むため』
- 前提: raw_hash `Y` に active erase receipt (canonical final event = `erased`) がある。`Y` と同一
  バイト列が working tree に再出現し取り込まれる。
- 操作: LC22-LC25 と同じ一連の手順 (再 publication → snapshot finalize → 同一 mutation 内 retire)
  を erase receipt に対して実行する。
- 期待: LC22-LC25 の全契約 (拒否しない・finalize 後 retire・crash-safe・同一 mutation 内 index_generation
  回転) が tombstone と同一に erase receipt にも成立する。**現行実装との既知の不整合**:
  `crates/kcs-core/src/purge.rs` の `retire_erase_receipt` (523-530) は
  `quarantine_then_unlink` で receipt **ファイルを物理削除**しており (`crates/kcs-core/src/scope.rs:
  554-555` から raw CAS 書込直後に呼ばれる — LC23 のタイミング不整合も併発)、本契約 (除去せず
  `retired` を append) に反する。転換後は同じファイルパスに events[] を追記し続け、ファイル自体は
  存在し続ける。

---

## F. verified raw × marker 共存の修復ロジック (U18)

### LC34 canonical=retired は正常共存 (無処置) [P0]
- 正本: 10 §7.5.1 L541-542『共存が**正常**なのは canonical final event が `retired` の場合
  (resurrection — 05-runtime.md §3.5)』
- 前提: `kcs repair --verify-objects` 実行時、raw_hash `X` の verified raw が存在し、marker
  (tombstone または receipt) の canonical final event が `retired`。
- 操作: fsck を実行する。
- 期待: この raw_hash について finding は生成されない (`purge_marker_conflict` も
  `tombstone_conflict` も出さない)。dead-by-tombstone/dead-by-erase-receipt のいずれのカウンタにも
  加算しない (raw は alive)。

### LC35 canonical=erased/purged + verified raw + 因果条件充足 → retired 補完 (marker 種別共通) [P0]
- 正本: 10 §7.5.1 L542-548『canonical final event が `erased` のまま verified raw が存在する場合は
  raw を正とし、**その再 publication commit (canonical final event の `in_commit` を ancestor に持つ
  ref 到達可能な commit) が存在するときに**、locked repair / 次の locked mutation で `retired` event
  を append して整合させる。**canonical final event が `purged` (tombstone) なのに verified raw が
  存在する場合**: canonical final purged event の `in_commit` を ancestor に持つ ref 到達可能な
  再 publication commit が存在するなら、crash した resurrection の完遂として `retired` を append して
  整合させる』
- 前提: LC27/LC29 と同じ 3 要件 (canonical final event が `erased` または `purged` / verified raw
  存在 / ancestor-respecting ref-reachable republication commit 存在) を、marker_kind を
  tombstone・erase receipt それぞれで揃える。
- 操作: `kcs repair --verify-objects` (確認プロンプト付き locked repair) を実行する。
- 期待: marker_kind (tombstone/receipt) を問わず同一の retired 補完が行われる。§E27 の locked
  mutation 経路と本 fsck 経路は同じ判定条件・同じ結果を生成する (経路依存で異なる挙動をしない —
  §D21 の「単一 validator」原則の repair 版)。

### LC36 因果条件不充足 → incomplete purge exit 3・補完しない・再 purge 誘導 [P0]
- 正本: 10 §7.5.1 L548-551『**存在しなければ incomplete purge として exit 3 で報告する**(retired を
  append しない — purge 済み内容を fsck が復活させない。回復は同一対象への `kcs purge --raw-hash` の
  再実行で冪等に完遂できる — 09-mvp-scope.md §5.3 の再 purge 規範。報告にはこの誘導を含める)』
- 前提: LC29/LC30 と同じ (verified raw 存在、但し因果条件を満たす republication commit 無し)。
- 操作: `kcs repair --verify-objects` を実行する。
- 期待: retired は append されない。fsck の応答 (`VerifyObjectsReport` 相当) は当該 raw_hash を
  incomplete purge として明示し、exit code 3。人間可読メッセージ (または構造化フィールド) に
  `kcs purge --raw-hash <X>` の再実行を回復手段として案内する文言を含む。

### LC37 commit 未存在 (未 finalize 進行状態) → incomplete・corruption にしない [P1]
- 正本: 10 §7.5.1 L551-554『(**receipt は除去しない**...**commit がまだ無い場合 — snapshot finalize
  前の crash — は「未 finalize の進行状態」として incomplete (exit 3) とし、append しない** —
  05-runtime.md §3.5 の因果条件と同型)』
- 前提: verified raw が存在するが、canonical final purged/erased event の in_commit が指す commit
  すら ref-reachable に存在しない、かつ再 publication に相当する commit もまだ存在しない (purge
  journal の "committed" 相前に crash した窓、または republication 自体の snapshot finalize がまだ
  commit/ref publish に達していない窓)。
- 操作: `kcs repair --verify-objects` を実行する。
- 期待: これは corruption (`KCS-E-STORE-CORRUPT-001`) として報告してはならない。「未 finalize の
  進行状態」として incomplete 扱い (exit 3) にとどめ、次回の index/batch resume が自然に解消する
  ことを前提に、retired は append しない。

### LC38 marker 非除去の原則と fsck の従来「conflict finding」置換 [P0]
- 正本: 10 §7.5.1 L551『(**receipt は除去しない** — 除去すると旧 commit が参照する manifest 欠落を
  説明するものが消える』/ §E33 の tombstone 版と対称。加えて、tombstone と receipt が同一 raw_hash に
  併存すること自体は §C8 (canonical final event 正本化) で解決される通常のケースであり、それ自体を
  fsck が無条件に「conflict」として報告する規範は新 spec に存在しない (05 §3.5 L907, 08 §3.1 手順 5
  はいずれも複数 marker の併存を前提に canonical を計算する設計である)。
- 前提: raw_hash `X` に tombstone と erase receipt の両方が存在する (どちらも検証通過)。
- 操作: `kcs repair --verify-objects` を実行する。
- 期待: 単に両方存在するという理由だけでは finding を出さない。canonical final event の正本化
  (§C1-C10) を経て、その canonical に基づく F34-F37 のいずれかの分岐で判定する。
  **現行実装との既知の不整合**: `crates/kcs-cli/src/verify_objects.rs` の 687-694 および
  748-753・1510-1515 は tombstone と erase receipt の共存を無条件に `"purge_marker_conflict"`
  finding として報告しており、本契約により canonical-final-event 基準の判定へ置き換える必要が
  ある。同様に 697-707・1516-1526 の `"tombstone_conflict"` (verified raw + tombstone 共存を
  無条件に finding とする現行ロジック) も LC35 の条件判定に置き換える。

---

## G. epoch / lifecycle-epoch カウンタ (U15 / U120)

> `.kcs/purge/epoch` (以下「purge epoch」) と `.kcs/tombstones/lifecycle-epoch` (以下
> 「lifecycle-epoch」) は **別系統の 2 つのカウンタ**であり、混同しない。purge epoch は
> **アクティブな purge トランザクションの ABA barrier** (§H・§I が消費)、lifecycle-epoch は
> **lifecycle event (retire/再purge/legacy変換) の回転検出源** (§E の resurrection・search の
> index_generation 回転が消費)。両者は目的も回復元も異なる。

### LC39 `.kcs/purge/epoch` 物理レイアウトと欠落時 fail-closed [P0]
- 正本: 03 §2 L86『`purge/epoch` purge の ABA barrier (単調カウンタ — 05-runtime.md §3.5。欠落 = 読取
  fail-closed)』/ 03 §4.1 L312『`.kcs/purge/epoch` | 単調カウンタ (text) | **truth**...| 欠落 = 読取
  fail-closed』
- 前提: `.kcs` 直下に `purge/epoch` ファイルが存在しない、または内容が数値として不正
  (例: 空ファイル、非数値文字列)。
- 操作: 読取系コマンド (例: `kcs search`) を実行する。
- 期待: `.kcs/purge/epoch` は単調カウンタを保持する単一のテキストファイルという物理レイアウトを持つ。
  欠落・不正値のいずれも fail-closed (§I5 の barrier エラーで拒否)。「epoch=0 とみなして通す」等の
  黙示のデフォルト値補完は行わない。

### LC40 `.kcs/purge/epoch` 再作成の優先順位 [P0]
- 正本: 05 §3.5 L820-823『次の locked mutation が journal の target_epoch、journal も無ければ
  **全 lifecycle event に記録された `epoch` の最大値 + 1** (`epoch` を記録した event が皆無なら 1 —
  event ゼロの store に加え、全行 legacy で epoch 欠落の lifecycle も含む。旧観測値と衝突しない) から
  単調性を回復して再作成する』
- 前提: `.kcs/purge/epoch` が欠落している状態で **書込系**コマンドが実行される。(a) active な purge
  journal が存在し `target_epoch=7` を記録している。(b) journal は無いが、全 tombstone/receipt の
  events[] に記録された `epoch` の最大値が `5` である。(c) journal も無く、全 marker の event が
  legacy で `epoch` を 1 つも記録していない (またはそもそも marker が存在しない)。
- 操作: 書込系コマンドを実行する。
- 期待: (a) `.kcs/purge/epoch` は `7` で再作成される (journal の target_epoch を最優先)。(b) `6`
  (max epoch `5` + 1) で再作成される。(c) `1` で再作成される。読取系コマンド自身はこの再作成を
  行わない (§I5 — fail-closed で拒否するのみ、回復は書込系のみの責務)。

### LC41 `.kcs/tombstones/lifecycle-epoch` 物理レイアウトと event append ごとの +1 [P0]
- 正本: 03 §2 L89-90『`tombstones/lifecycle-epoch` lifecycle 更新 (retire・再 purge・legacy 変換) の
  単調カウンタ (05-runtime.md §3.5 — 回転補完の検出源。event append ごとに +1)』/ 03 §4.1 L313
- 前提: `.kcs/tombstones/lifecycle-epoch` は `.kcs/purge/epoch` とは別ファイル・別カウンタ。
- 操作: retire・再 purge・legacy 変換のいずれかを 3 回連続で実行する。
- 期待: `.kcs/tombstones/lifecycle-epoch` はそれぞれの操作の都度 +1 され (3 回で合計 +3)、
  `.kcs/purge/epoch` の値には一切影響しない (逆方向も同様に独立)。両カウンタが同じファイル・同じ
  変数を共有する実装は契約違反。

### LC42 index_metadata.last_lifecycle_epoch 列契約と rebuild-db 初期化 [P0]
- 正本: 04 §4.1 L413-423『CREATE TABLE index_metadata ( id INTEGER PRIMARY KEY CHECK (id = 1),
  index_generation TEXT NOT NULL, last_lifecycle_epoch INTEGER NOT NULL DEFAULT 0 )』/ 05 §3.5
  L760-761『`kcs repair --rebuild-db` は完了 Tx で現 counter 値に初期化する — DEFAULT 0 のままの
  全件誤検出を防ぐ』/ 04-pipeline.md L913 (rebuild-db 完了 Tx での `last_lifecycle_epoch` 初期化を
  再言及)
- 前提: (a) `.kcs/index/sqlite.db` が新規作成される (`kcs repair --rebuild-db` または初回 `kcs
  index`)。(b) 既存 `.kcs/tombstones/lifecycle-epoch` の値が `9`。
- 操作: rebuild-db を実行する。
- 期待: `index_metadata` は単一行 (`id=1`)。`last_lifecycle_epoch` 列は `INTEGER NOT NULL DEFAULT 0`
  制約を持つが、rebuild-db の完了 Tx (index_generation 新規 ULID 採番と同一 Tx) では DEFAULT の `0`
  ではなく、その時点の `.kcs/tombstones/lifecycle-epoch` 実値 (`9`) に初期化される。これを怠ると
  §G7 の巻き戻り検出が `counter(9) > last_lifecycle_epoch(0)` を毎回検出し続け、不要な全走査・回転が
  発生する (この誤検出の回避が本契約の目的)。

### LC43 巻き戻り検出の機械条件 (時刻を使わない) [P0]
- 正本: 05 §3.5 L765-769『**巻き戻り検出は機械条件のみ**: locked mutation 冒頭で `counter <
  max(last_lifecycle_epoch, 全 lifecycle event の lifecycle_epoch 最大値)` (lifecycle_epoch を
  記録した event が無ければ後者は 0 として評価) なら...**「更新痕跡」の判定はこの比較だけで行い、
  mtime 等の抽象的条件は使わない**』
- 前提: `.kcs/tombstones/lifecycle-epoch` の実値が `3`。`index_metadata.last_lifecycle_epoch` が
  `5`。全 lifecycle event 中の `lifecycle_epoch` 最大値が `4`。
- 操作: locked mutation を開始する (例: 新規 purge)。
- 期待: `max(5, 4) = 5` に対し `counter(3) < 5` ⇒ 巻き戻りと判定する。判定はこの数値比較のみで行い、
  counter ファイルの mtime やその他のファイルシステムメタデータを一切参照しない。

### LC44 巻き戻り回復 (max+1 再作成・無条件 1 回転・同一 mutation) [P0]
- 正本: 05 §3.5 L767-769『**その max + 1 で counter を再作成して無条件で index_generation を 1 回転
  する**(取りこぼした可能性のある更新を回転で潰す fail-safe)』
- 前提: LC43 で巻き戻りが検出された (`max=5`)。
- 操作: 巻き戻り検出直後の回復処理を観測する。
- 期待: `.kcs/tombstones/lifecycle-epoch` は `6` (`5+1`) で再作成される。`index_generation` は
  (実際に取りこぼした更新があったかどうかを問わず) **無条件に** 1 回回転する。この回復は検出した
  locked mutation と同一トランザクション/lock 保持区間内で完結する。

### LC45 読取系冒頭検査 (counter⇔last_lifecycle_epoch 不一致は両方向拒否・自動再試行なし) [P0]
- 正本: 05 §3.5 L769-772『**読取系は冒頭検査で counter と last_lifecycle_epoch を照合し、不一致
  (> だけでなく < も) なら KCS-E-INDEX-REBUILDING-001 と同じ retryable (exit 3) を返す** — 補完回転は
  書き込み系のみが行うため、crash 後最初のコマンドが読取でも旧 cursor を退役後の可視集合へ受理しない
  (この retryable への自動再試行は仕様として約束しない — 再試行は呼出側の判断)』
- 前提: (a) `.kcs/tombstones/lifecycle-epoch` 実値が `last_lifecycle_epoch` より大きい (回転未了)。
  (b) 実値が `last_lifecycle_epoch` より小さい (通常は起きないはずの状態)。
- 操作: 読取系コマンド (`kcs search` 等) を実行する。
- 期待: (a)(b) いずれも `KCS-E-INDEX-REBUILDING-001` と同じ error_code・retryable・exit 3 を返す。
  読取系はこの場で counter や last_lifecycle_epoch を書き換えたり index_generation を回転したり
  しない (回復は書込系のみ — §L44)。KCS 自身はこのエラーに対して内部でリトライループを行わない
  (呼出側 CLI/自動化がリトライするかは呼出側の判断)。**この検査は §I の purge-epoch/journal 2 点
  検査とは別のチェックであり、混同しない** (§G 冒頭の note 参照)。

---

## H. purge journal 機構本体 (U35)

### LC46 journal record 必須 field 一式 [P0]
- 正本: 05 §3.5 L794-802『journal record = { purge_id (ULID), raw_hash 群, reason, actor,
  started_at, target_epoch (完了時の epoch 値), marker_kind (tombstone | erase), closure
  (削除対象の全 object type × hash — 共有派生の live 参照判定の結果を含む), planned_commit
  (purged commit の canonical bytes — prepared 相で確定し...) }』
- 前提: `kcs purge --raw-hash X --reason legal` を実行し、journal (`.kcs/purge/journal` 相当の path)
  が作成される。
- 操作: journal record の構造を検査する。
- 期待: 上記 8 要素すべてが揃っている。**現行実装との既知の不整合**: `crates/kcs-core/src/purge.rs`
  の `PurgeJournal` (178-189) は `schema_version`/`target_raw_hashes`/`reason`/`tombstone_mode`/
  `started_at`/`phase`/`purged_in_commit`/`purged_at` のみを持ち、`purge_id`・`actor`・`target_epoch`・
  `closure` を欠く。`marker_kind` 相当は `tombstone_mode` (`Default`|`Erase`) として既存するが
  フィールド名が異なる。`planned_commit` 相当は `purged_in_commit`+`purged_at` として部分的に既存
  するが、確定タイミングが LC48 の要件 (prepared 相) と異なる (現行は後段の phase で bind される)。

### LC47 phase enum と厳密順序 prepared→tombstoned→deleted→committed→done [P0]
- 正本: 05 §3.5 L803-807『phase 順序 = prepared (closure確定・記帳) → tombstoned (tombstone/erase
  receipt を先に耐久化 — 削除より前) → deleted (objects/SQLite/chunks.jsonl/logs の冪等削除) →
  committed (commit_type=purged の publication) → done: ...』
- 前提: 新規 purge を開始する。
- 操作: phase の遷移順序を観測する。
- 期待: phase は厳密にこの 5 値・この順序で単調に進む (スキップ不可、逆行不可)。**現行実装との
  既知の不整合**: `crates/kcs-core/src/purge.rs` の `PurgePhase` (75-102) は
  `Prepared → BarrierPublished → PurgedCommitCreated → ContentDeleted → DerivedDeleted →
  LogsScrubbed` の 6 値であり、新 spec の 5 phase 名 (`prepared`/`tombstoned`/`deleted`/`committed`/
  `done`) と一致しない。単純なリネームでは済まない意味変化を LC49・LC50 で扱う。

### LC48 prepared 相での closure・planned_commit 確定 [P0]
- 正本: 05 §3.5 L793-794, L798-802『journal record = { ... closure (削除対象の全 object type × hash
  — 共有派生の live 参照判定の結果を含む), planned_commit (purged commit の canonical bytes —
  prepared 相で確定し...) }』/ L803『prepared (closure確定・記帳)』
- 前提: `prepared` phase の journal 書込が完了した直後 (`tombstoned` phase へ進む前)。
- 操作: journal の内容を検査する。
- 期待: `closure` (削除対象の全 object type×hash、共有派生の live 参照判定結果を含む) と
  `planned_commit` (purged commit の確定バイト列/hash) は **この時点で既に確定・記帳済み**。以降の
  phase でこれらの値が再計算されたり変化したりしない (crash-resume 時も同じ値を再利用する — §H50)。

### LC49 phase 順序の周辺効果: marker は削除より先・commit publication は削除より後 [P0]
- 正本: 05 §3.5 L804『tombstoned (tombstone / erase receipt を先に耐久化 — 削除より前)』/ L805-806
  『deleted (objects / SQLite / chunks.jsonl / logs の冪等削除) → committed (commit_type=purged の
  publication)』/ L904-905『tombstone を削除より先に耐久化するのは、「対象 object が消えたのに purge
  の痕跡が無い」状態 (corruption と区別不能な markerless absence) を作らないためである』
- 前提: 新規 purge が `prepared` を終え `tombstoned` phase に入る。
- 操作: 各 phase での実際の副作用 (marker ファイル publish・objects/SQLite/chunks.jsonl/logs 削除・
  commit/ref publish) の発生順序を観測する。
- 期待: tombstone/erase receipt の永続化 (`tombstoned` phase) は、いかなる物理削除 (`deleted` phase)
  よりも **先**に完了している。かつ、purged commit の ref publish (`committed` phase) は物理削除
  よりも **後**に行われる — 「commit を先に作ってから消す」という直感的な順序ではなく、
  「マーク → 削除 → commit 化」の順序が正本であることに注意する (非直感的だが、この間の一貫性は
  §I の読取 barrier (active journal の間は結果を返さない) が担保しており、phase 順序それ自体は
  「観測者に何が見えるか」ではなく「クラッシュ時に何を再開できるか」の設計であるため成立する)。

### LC50 単一 timestamp の固定と crash-resume での再利用 [P1]
- 正本: 05 §3.5 L801-802『marker の purged/erased event の `at` は planned_commit の `created_at`
  と同一値 — prepared 相で確定した単一 timestamp』/ L811-813『クラッシュ回復 = 次回の書き込み系
  コマンド冒頭で journal を検出したら、記録 phase から再開する (各 phase は再実行安全 —
  planned_commit を journal から publish するため同一 hash を再現でき、**時刻の再計算をしない**)』
- 前提: `prepared` phase で timestamp `T0` が確定する。`tombstoned` phase 完了直後に crash する。
- 操作: プロセス再起動後、次の書込系コマンドが journal を検出して `tombstoned` 以降を再開する。
- 期待: 再開後に発行される marker の `at` および `planned_commit` の `created_at` は、再起動後の
  新しい現在時刻ではなく、journal に記録された `T0` のまま (再計算しない)。commit の hash も
  journal の `planned_commit` から再現され、再起動のたびに異なる commit hash が生まれることはない。

### LC51 done 相の順序固定と active journal 中の fsck 拒否 [P0]
- 正本: 05 §3.5 L807-810『done: **順序固定** — (1) `.kcs/purge/epoch` を journal の target_epoch へ
  更新 (temp書込→file fsync→atomic rename→親directory fsync)、(2) その後に journal を除去+directory
  fsync。journal が先に消える実装は、除去〜increment 間の crash で「journal 不在×旧 epoch」の ABA 窓を
  作るため禁止』/ L813-814『journal が active な間の fsck は incomplete (exit 3 — 10-operations.md
  §7.5.1)』
- 前提: `committed` phase まで完了し `done` phase に入る。
- 操作: (a) 正常系で `done` 相の 2 ステップの実行順序を観測する。(b) `.kcs/purge/epoch` 更新完了
  直後・journal 除去前に crash させる。(c) 未完了 (active) の journal が存在する状態で `kcs repair
  --verify-objects` を実行する。
- 期待: (a) 順序は必ず「epoch 更新→fsync」が先、「journal 除去→dir fsync」が後。逆順の実装は
  禁止 (ABA 窓を作るため)。(b) crash 後は epoch が既に新値に更新済みで journal も残っているという
  一貫した状態になり (禁止された「journal 不在×旧 epoch」の ABA 状態にはならない)、次回書込系が
  journal を検出して `done` を再実行 (冪等) できる。(c) fsck 自体が `incomplete` (exit 3) を返し、
  object 検証を実行しない。

---

## I. 読取系 barrier: 2 点検査と 3 点再検査 (U36)

> 本節は `.kcs/purge/epoch` と active journal の可視性についての barrier であり、§G の
> lifecycle-epoch 巻き戻り検出 (KCS-E-INDEX-REBUILDING-001) とは **別の仕組み**。10-operations.md §3
> (Scope Registry) の「複合状態の優先順位」「返却直前の再検査」の記述が U36 の細部を確定する一次
> 情報源であり、05-runtime.md §3.5 だけでは 2 点目が実際には 3 要素比較であることが分からない
> ため必読。

### LC52 対象 8 コマンドの閉 enum と status 除外 [P0]
- 正本: 05 §3.5 L814-816『読み取り系 (status を除く §6 の全読取コマンド — search / log / view /
  inspect / evidence verify / restore / diff / open) は、冒頭と「本文・存在情報を返す直前」の 2 点で
  検査する』
- 前提: KCS の読取系コマンド一覧。
- 操作: 各コマンドが barrier 対象かどうかを分類する。
- 期待: `search`・`log`・`view`・`inspect`・`evidence verify`・`restore`・`diff`・`open` の 8 個が
  対象 (この 8 個以外の読取系コマンドが存在する場合、spec のこの列挙にない限り対象外)。`kcs status`
  は明示的に対象外 (§I54 で別途「表示は継続」)。この 8 個の閉 enum を実装が拡大・縮小しないことを
  要求する契約。

### LC53 チェックポイント 1 (冒頭・複合 preflight 順序の一部としての適用) [P0]
- 正本: 10 §3 L300-311『**複合状態の優先順位 (全コマンド共通の preflight 順序)**: (0)
  `kcs_format_version` 互換判定 → (1) purge journal / epoch 検査 (05-runtime.md §3.5) → (2)
  registry live 重複 (KCS-E-REGISTRY-DUP-001) → (3) index 可用性 (KCS-E-INDEX-REBUILDING-001) → (4)
  command 固有の検査。...同時成立時は先順の error を返し...読取系はこの順序を**冒頭 1 回**適用し、
  その時点の registry / index 状態を線形化点とする』
- 前提: 読取系コマンドを起動する。
- 操作: 起動直後の検査順序を観測する。
- 期待: (0)→(1)→(2)→(3)→(4) の順で検査が行われ、複数が同時に成立する状況でも **最も順位が早い**
  違反の error のみが返る (実装内部の評価順に依存しない決定的な優先順位)。この冒頭 1 回の適用時に、
  `.kcs/purge/epoch` の現在値と lifecycle-epoch の現在値が「開始時の観測値」として保存され、
  チェックポイント 2 (§I54) の比較基準になる。(1) の journal/epoch 検査に違反すれば
  `KCS-E-PURGE-JOURNAL-ACTIVE-001` (exit 3)、(3) の index 可用性に違反すれば
  `KCS-E-INDEX-REBUILDING-001` (exit 3、§G45 と同一機構) が返る — この 2 つは別の error_code である
  ことに注意 (§G 冒頭 note)。

### LC54 チェックポイント 2 (返却直前・固定順 3 点の開始値不変比較) [P0]
- 正本: 10 §3 L311-315『返却直前の再検査は**冒頭で保存した開始値との不変比較**を固定順で行う: (1)
  purge journal 不在 → (2) purge epoch = 開始値 → (3) lifecycle counter = 開始値 (**counter が最終の
  線形化点**)。いずれかの不一致で結果を破棄し retryable (exit 3) — 比較対象は常に開始値であり、
  最新 last_lifecycle_epoch との再照合ではない』
- 前提: チェックポイント 1 (§I53) で journal 不在・purge epoch=`E0`・lifecycle counter=`L0` が
  観測・保存されている。コマンドは本文/存在情報を返す直前まで処理を進めた。
- 操作: (a) 何も変化していない状態で返却直前検査を行う。(b) 検査の間に別プロセスが purge を完了させ
  `.kcs/purge/epoch` が `E0` から `E1` (E1≠E0) に変わっている。(c) 別プロセスが retire/再purge/
  legacy 変換を行い lifecycle counter が `L0` から `L1` (L1≠L0) に変わっている。
- 期待: (a) 検査通過、結果をそのまま返す。(b)(c) いずれも「開始値との不一致」として検出され、
  結果を破棄し `KCS-E-PURGE-JOURNAL-ACTIVE-001` を retryable exit 3 で返す。**比較は常に
  チェックポイント 1 で保存した `E0`/`L0` に対して行い**、その時点の `last_lifecycle_epoch` の
  最新値と再照合する実装 (§G45 のロジックの流用) は契約違反 (別の検査を混同している)。比較順序は
  「journal 不在 → purge epoch 一致 → lifecycle counter 一致」で固定。

### LC55 いずれかの不一致で結果破棄・エラーコード/exit [P0]
- 正本: 05 §3.5 L816-819『「active journal の不在 **かつ** `.kcs/purge/epoch` (単調カウンタ) が
  開始時と不変」でなければ `KCS-E-PURGE-JOURNAL-ACTIVE-001` ([10-operations.md §12.1]) retryable
  (exit 3) で拒否する (2 点目で検出した場合は取得済み結果を破棄する』
- 前提: §I54 (b) または (c) のいずれかで不一致が検出される直前に、コマンドは既に応答本文
  (例: chunk のテキスト、restore 対象のファイルリスト) を組み立て終えている。
- 操作: 不一致検出後の挙動を観測する。
- 期待: 既に組み立てた応答本文は破棄され、呼び出し元には返らない (stdout/戻り値に content が
  漏れない)。代わりに `KCS-E-PURGE-JOURNAL-ACTIVE-001` エラー (retryable, exit 3) のみが返る。

### LC56 registry-dup / index-availability はチェックポイント 2 で再検査しない [P1]
- 正本: 10 §3 L316-317『検査後の DUP / REBUILDING の状態変化は次回実行で拾う (fail-closed の再適用は
  しない)』
- 前提: チェックポイント 1 通過後、コマンド実行中に別の clone が live 登録されて registry 重複状態
  (DUP) が新たに発生する、または index が rebuilding 状態に入る。
- 操作: 当該コマンドの返却直前検査を観測する。
- 期待: チェックポイント 2 は journal/purge-epoch/lifecycle-counter の 3 点のみを再検査し、
  registry-dup や index-availability の状態変化はこの実行では検出しない (今回の応答はそのまま
  返る)。次回の別コマンド実行時にチェックポイント 1 で改めて検出される。

### LC57 restore/open の固定位置 (scope note) [P2]
- 正本: 05 §3.5 L830-834『不可逆な外部副作用を持つ 2 系は検査位置を固定する: restore は private
  temp へ展開し返却直前検査の後に atomic rename で --to へ publish...』/ L887-890『open は OS
  アプリ起動の直前 (一時展開の cache publish 後) に再検査する (起動後は取消不能...)』
- 前提: `restore`・`open` は §I52 の 8 コマンドに含まれる。
- 操作: restore/open の barrier 検査位置を観測する。
- 期待: restore は「private temp への展開完了・返却直前検査通過後」に atomic rename で `--to` へ
  publish する (検査 → publish の順、逆ではない)。open は cache publish 後・OS ビューア起動 **前**
  に再検査する (起動は取消不能なため、検査はそれより前に完了していなければならない)。**この 2 コマンド
  の退避・隔離・no-replace publish・rename 後の再解決といった詳細機構は本書のスコープ外**
  (U26/U27/U22/U23 — 別ドキュメント) であり、本契約は「barrier のチェックポイントがこの 2 点に
  固定されている」という事実のみを確認する。

---

## J. 再 purge (U38)

### LC58 再 purge は events[] へ新規 purged/erased event を追加 append [P0]
- 正本: 05 §3.5 L907『再 purge はさらに `purged` を append する』(tombstone 側の一文。erase receipt
  側も対称に `erased` を append する — 05 §3.5 全体の lifecycle 記述の対称性、および 10 §7.5.1
  L577 の「tombstone lifecycle にも同じ event 検証を適用する」がこの対称性を裏付ける)
- 前提: raw_hash `X` に既に tombstone (canonical final event = `purged`) がある。
- 操作: `kcs purge --raw-hash X --reason privacy` (同一 marker_kind = tombstone) を再実行する。
- 期待: 既存の tombstone ファイルの `events[]` へ新しい `{kind:"purged", reason:"privacy", ...}`
  要素が **append** される (既存 event は変更・削除されない)。新しい別ファイルが作られたり、
  既存レコードが完全に上書きされたりしない。**現行実装との既知の不整合**:
  `crates/kcs-core/src/purge.rs` の `state.begin()` (296-347) は同一 reason での再 purge を
  `BeginOutcome::AlreadyComplete` として無変更で素通りし (333-335)、events[] 自体が無い現行 flat
  schema では新規 event の append という概念そのものが成立しない。転換後は「既に tombstoned でも
  常に新しい purged event を append する」動作に変わる。

### LC59 再 purge 時の「既存 active marker」判定は当該 marker の末尾 event で行う [P0]
- 正本: 05 §3.5 L786『fsck・再 purge (marker lifecycle 管理) は各 marker の末尾 event 規則によるが』
  (U20 の二用途分離規則。再 purge が「この raw_hash には既に active な tombstone があるか」を判定
  する際の基準)
- 前提: raw_hash `X` について、tombstone の末尾 event が `purged`、erase receipt の末尾 event が
  `retired` (canonical final event は §C1 のルールにより tombstone 側の `purged` が勝つとは限らない
  — lifecycle_epoch 次第)。
- 操作: `kcs purge --raw-hash X --reason legal` (marker_kind=tombstone を指定) を実行する。
- 期待: 「この raw_hash に対し tombstone として既に active か」の判定は **tombstone 自身の末尾
  event** (`purged`) で行う — erase receipt の末尾や §C の cross-marker canonical final event を
  参照しない。したがって tombstone へ新規 `purged` event が append される (§L58 の動作)。
  `--erase-tombstone` を指定した場合は同様に erase receipt 自身の末尾 event で判定する。

### LC60 [解釈割れ] 再 purge の reason 一致要件は新 spec で未規定 [P2]
- 正本: `tasks/step4b-spec-gap.md` U38 の統合要約 (05§3.5 由来) は「同一 raw_hash を再度 purge すると
  新たな purged event を追加 append する」とのみ述べ、**新しい purged event の `reason` が直前の
  purged event の `reason` と一致しなければならないという制約を明記していない**。
- 前提: raw_hash `X` の既存 tombstone 末尾 purged event が `reason:"legal"`。再 purge を
  `--reason privacy` (異なる reason) で実行する。
- 操作: 再 purge を実行する。
- 期待: **[解釈割れ]** 新 spec の字面からは、異なる reason での再 purge が拒否されるべきか、それとも
  素直に `{kind:"purged", reason:"privacy", ...}` が append され、tombstone の「事由の履歴」が
  events[] 上に `legal` → `privacy` と複数残ることを許容すべきか、判定できない。
  **現行実装** (`crates/kcs-core/src/purge.rs:325-328`) は reason 不一致を
  `KcsError::invalid_usage("an existing tombstone has a different purge reason")` で拒否している
  が、この制約は旧 flat schema (「1 raw_hash = 1 tombstone = 1 reason」を暗黙に仮定) 由来であり、
  events[] 化 (複数 event が併存できる) によってこの前提自体が崩れている可能性がある。本書は
  どちらか一方を規範として断定せず、実装時に発注側の裁定を要すると注記するにとどめる。

---

## K. 用語・カウンタの相互参照まとめ (実装時の取り違え防止)

| 名前 | パス | 目的 | 消費者 | 参照 LC |
|---|---|---|---|---|
| purge epoch | `.kcs/purge/epoch` | purge トランザクションの ABA barrier | journal の `target_epoch`・§I バリア | LC39-40, LC46, LC51, LC53-55 |
| lifecycle-epoch | `.kcs/tombstones/lifecycle-epoch` | lifecycle event 回転の検出源 | `index_metadata.last_lifecycle_epoch`・§G 巻き戻り検出・§I チェックポイント 2 | LC41, LC43-45, LC54 |
| `epoch` (event field) | tombstone/receipt の各 purged/erased event 内 | 発行時点の purge epoch を記録 | LC40 の再作成優先順位計算の入力 | LC3, LC40 |
| `lifecycle_epoch` (event field) | 各 lifecycle event 内 (全 kind) | canonical final event 正本化の比較キー | §C1-C10 | LC3, LC8-10, LC43 |
| `index_generation` | `index_metadata.index_generation` (ULID) | 検索 cursor の世代不変性 | §E25 (retire 直後回転)・§G44 (巻き戻り回復時回転) | LC25, LC44 |

---

## L. 解釈割れ注記一覧

1. **LC3 / erased event の `reason` 必須性**: 10 §7.5.1 の「完全列挙」(L557-561) は `erased` の
   必須 field に `reason` を含めないが、直後の文で「2026-07-19 以降の新規 event は...erased が
   `reason`...も必須」と述べる。本書は「常に必須の base 集合には reason を含めないが、legacy 変換
   以外の新規 erased event は reason を必須とする」と読んで LC3 の表を構成した。legacy 変換由来の
   erased event は (v1 に reason が無いため) `reason:"other"` を合成する規則 (05§3.5 L950) がある
   ため、実際には「reason を完全に欠く erased event」が構造的に生じる場面は無いはずだが、spec の
   2 文の関係 (base 列挙が先に reason を除外し、後段が「新規は必須」と additive に述べる書き方) は
   厳密には validator の許容度 (reason 欠落を warning にとどめるか、hard reject するか) を一意に
   決めていない。
2. **LC60 / 再 purge の reason 一致要件**: §J60 を参照。新 spec は明記せず、現行実装は不一致を拒否
   する。
3. **LC30 / LC49 の phase 順序の直感性**: 05§3.5 の journal phase 順序 (`tombstoned` が `committed`
   より先) はテキスト上明確だが、他ドキュメント (U29 領域、本書スコープ外) の purge 実行順序記述との
   突き合わせは行っていない。矛盾が無いことは本書の確認範囲外であり、実装着手時に隣接領域の担当と
   すり合わせが必要。

## M. 裁定 (§L の解釈割れ — Phase 1 実装用、2026-07-21 オーケストレータ裁定)

1. **LC3 (erased の reason)**: 実装が書く全 event は新規要件で書く (erased も reason 必須)。「reason を欠く erased event」は v1 legacy 変換の other 合成経由でしか生じ得ないため、変換以外での欠落は **hard reject (corruption)**。日付分岐 (2026-07-19) は実装に入れない — 新 store は全て新規要件、読取の寛容は v1 flat 変換のみ。
2. **LC60 (再 purge の reason 一致)**: **一致要件なし** — 各 purged event が独立の reason を持つ (別の法的根拠での再 purge は正当)。現行実装の不一致拒否は廃止する。
3. **LC30/LC49 (phase 順序の他文書整合)**: 整合確認済み — tombstoned が committed より先なのは U29 の「削除事実の記録を物理削除より先に耐久化」原則そのもの。矛盾なし、このまま実装。

---

**契約数集計**: A=4, B=3, C=7, D=7, E=12, F=5, G=7, H=6, I=6, J=3 — 合計 **60 件**
(P0=51, P1=7, P2=2)。解釈割れ注記 = **3 件** (§L)。
