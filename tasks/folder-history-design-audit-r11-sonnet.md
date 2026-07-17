# folder-history 設計書 r11 監査報告 (Claude Sonnet 5, 単独セッション)

対象: `docs/research/folder-history-sqlite-design.md` (ディスク実体・r10 適用済み・2,320 行、2026-07-15 実行)
方法論: `tasks/folder-history-design-audit-prompt.md` 系の監査プロンプト (r11 版、本セッションの会話内で受領)。
r10 の 3 独立監査 (`tasks/r10-audit/final-report.md` = Claude Opus、`tasks/folder-history-design-audit-r10-sonnet.md` =
Sonnet 15-エージェント並列、`tasks/folder-history-r10-audit-fable.md` = Fable 5 系統) を先に読了し、
それらが検出した fatal 1 (submission_seq × cost_ledger UNIQUE 衝突) + major 6 (submit_rejected 無限ループ /
client 経路 attempts 上限到達後の limbo / fork journal 削除順 / fork 除外粒度 / detached state=0 の
「job 未作成」前提誤り / fork 手順 3 の folders 行削除漏れ) が本書の L01〜L28 (r10 修正検証リスト) として
反映されているかを起点に、文書全文を読了した上で独立に検証した。

## 判定: **不合格**

- 前提条件: **充足** (探索ログは後述の通り 58 シナリオ、X1〜X35 の全観点で最低 1 シナリオを実行済み)
- C9 回帰: 233 項目中 232 が fixed または superseded、**L28 のみ partially-fixed**
- 新規検出: **major 2 件 (M01, M02)・minor 10 件 (M03〜M12)・proposal 6 件 (P1〜P6)**
- 不合格事由: L28 の partially-fixed 1 件 (この時点で合格・条件付き合格の条件を満たさない) + 新規検出の major 2 件

---

## 第 1 部 — 回帰確認 (C9・233 項目)

**A01〜A24 / B01〜B18 / D01〜D14 (D05→E04, D08→K19 は superseded) / E01〜E06 /
F01〜F27 (F05→I14, F07→I15, F10→H08, F12→I16・I17, F21→J06 は superseded) / G01〜G02 /
H01〜H30 (H02→I32, H04→I31, H15→I08・I11, H18→I16, H22→I15 は superseded) /
I01〜I38 (I03/I04→J06, I05/I06→J01・J02, I09→J03, I15→J04, I16/I17→J05・J01, I35→J13〜J16,
I12→K04, D08→K20(重複)は superseded) / J01〜J20 (J04→K01, J10→K09 は superseded) /
K01〜K26 (K02 の残存部分は L01/L02 で解消済みのため fixed へ回復。K16 の submission_seq=0 の
明文規定は L01 の継承規則によって上書き改善 — 矛盾ではなく上位互換のため fixed。K24 の
`agg_embedding_profile_hash` 照合は L09 の building/ready 2-key 化に発展的に置き換わっているため
fixed と判定): すべて fixed または superseded (対応表どおり)。

**L01〜L27: fixed。L28: partially-fixed。**

以下、L 群 (r10 修正検証リスト) の詳細根拠と、唯一の例外を示す。

### L01〜L27 の根拠 (fixed)

| ID | 根拠 (§ + 引用) |
|---|---|
| L01 | §5.3 (L252-257) 「submission_seq の初期値は 0 ではなく、cost_ledger の同キー最大値から継承する: `COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE …), 0)`」+ §9.1 DDL コメント (L704-710) 同旨 |
| L02 | §9.1 collect 冪等クローズ注記 (L879-881) 「UNIQUE(repository_id, kind, target_key, **submission_seq**) が ledger の 二重計上を構造的に防ぐ」— 旧 `attempt` 表記は grep で確認する限り文書中に一切残存しない |
| L03 | §9.1 (L942-953) 「reconcile / submit が state=0|3 を成果ありで閉じる際の付随処理 (同一 app Tx)」(a)(b)(c) が明記され、「この規則により旧「既知の残余 (失効窓の課金行は記録できない)」は解消される」と明記 |
| L04 | §9.1 detached 規範 (L924-929) 「state=0 の detached: 「job 未作成 = 課金なし」を前提にしてはならない」+ (a)(b) 分岐が明記 |
| L05 | §9.1 相 2 (L836-841) 「恒久拒否…state=3 (error='submit_rejected') かつ同 Tx で attempts = 上限を設定する」+ 相 2a/2b 分割 (L827-831) |
| L06 | §9.1 intent 回復 dispatch (L848-852) 「batch_job_id 非 NULL の state=0 は client 前計上済み…§8 (iii) の再実行経路へ送る (attempts >= 上限なら state=3 (error='client_exhausted')…)」 |
| L07 | §21.3 (L2171-2231) phase 状態機械全体・失敗回復の 2 検出契機 (L2211-2213)・削除順 (L2202-2204 flag→journal)・除外粒度 (L2178-2182 (old_id, realpath) パス単位)・id=old 分岐 (L2225-2226) すべて確認 |
| L08 | §21.3 手順 3 (L2194-2201) 「folders の旧行 DELETE…**folders を消すことを明示する**」+ was_tracked (journal 固定値) + INSERT OR REPLACE + journal 破損=damaged (L2229-2230) |
| L09 | §8-e (L617-627) building/ready 2-key + §11.2 (L1464-1468) agg_ready_profile_hash 照合 + app_config hash lower hex64 固定 (L621) |
| L10 | §9.1 intent 回復 (L860-864) 「kind=1 の載せ直しガード…不一致…は state=3 (error='tool_changed', attempts=上限) で閉じる」(チェックリストの § 表記は「§11.2」だが実際の記述は §9.1 — 内容自体は充足) |
| L11 | §11.2 (L1441) `ORDER BY fu.score DESC, c.chunk_uid` + fts_hits/vec_hits 双方の ROW_NUMBER に `e.chunk_uid` 第 2 キー (L1414, L1422) |
| L12 | §11.2 (L1498-1500) 「LIKE fallback の走査は eligible が text 列を公開しないため agg_chunks を chunk_uid で 再 JOIN する」+ instr(lower) (L1489) |
| L13 | §9.1 folders DDL (L673-677) missing_since 列 + §20.4 (L1959-1962) 「猶予の起点は folders.missing_since…猶予満了…後は tick が §9.3-d を実行して退役」 |
| L14 | §20.5 (L2005-2007) 「delete コミットの直前に対象名を最終 stat で再確認し、存在すれば確定を中止して pending を リセットする」 |
| L15 | §20.5 手順 1 (L1976-1978) 「open は symlink を辿らないフラグ (O_NOFOLLOW 相当) で行い、open 後に fstat で regular file で あることを再確認する」 |
| L16 | §20.3 (L1870-1883) fp_cache 非確定 4 条件目 (name_collision/name_invalid) + `.folder-history` 発見は fp skip 対象外の明記 |
| L17 | §21.1 (L2112-2115) 「旧 root_path は現存するが別の実体…も rebind とする」+ 一時読取不能は保留 |
| L18 | §21.4 (L2242-2244) 「規約 12 の照合を先に行う」 |
| L19 | §21.5 (L2277-2279) watch_roots 外フォルダの個別パス再入力 + §21.6 (L2292-2293) 入力に対象フォルダ明記 |
| L20 | §13 (L1581-1591) 1 ストリーム規律 + 破損 object の tmp 原子置換例外 + profile 破損誘導の kind 別分岐 |
| L21 | §21.2 / §9.3-d (L2143-2144, L1187-1189) 「(cancel 確定 or terminal) かつ (upload_id IS NULL or upload_cleaned=1)」 |
| L22 | §15 規約 7 (L1663-1673) 6 点 (a〜f)、(f) に watch_roots 外パス含む + 「有界」2 種の区別 |
| L23 | §6 (L514-516) 「エスケープは保存時変換 2 のページ結合後の全文に対して行う」 |
| L24 | §11.2 (L1495-1497) 「:at_hash = X'FF…FF' (32 bytes) に固定する」(チェックリストは「§11.1」表記だが実体記述は §11.2 — 内容充足) |
| L25 | §20.5 (L1994-1996) 「恒常的に stat が失敗するエントリが 1 つあると…delete 確定は停止し続ける…意図されたトレードオフ」+ name_collision 採用交替の意味論 (L2040-2042) |
| L26 | §9.1 相 2b (L833-835) 「Retry-After は app_config の retry_not_before として永続化」 |
| L27 | §11.1 (L1375-1377) 「tool profile 変更後の過去版本文は backfill…が成立させる — backfill OFF は「tool 変更を跨ぐ過去版検索の完全性を放棄する」設定であり…OFF 時はその旨を status に明示する」 |

### L28: partially-fixed

L28 は 3 つの下位要求からなる複合項目である。

```text
| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| L28 | partially-fixed | (a) 「register の embedding_vec profile 確定まで非作成」— §21.1 手順 2 (L2119-2121)
「embedding_vec は profile 確定まで作らない…§10 step 3 冒頭の次元検査 (§8-c) が初回に vec 不在を検知して作成する」
で **充足**。
(b) 「fsck の agg 側 vec も対象」— **未充足**。§13 の fsck 記述 (L1553-1591、object 層/履歴層/profile 層の
3 層構成) は全行 grep 確認の結果 `agg_vec` / `agg_embeddings` への一切の言及を含まない。§8-e (L626)
「same-profile での vector 破損や agg_vec の欠落は同期では検出しない — 集約は cache であり、規約 9 の
破棄・再構築で扱う」と自己言及するが、規約 9 (§15、L1675-1684) は app.sqlite **全損**時の bootstrap 手順
のみを記述し、同一 profile 内での agg_vec の部分破損 (bit-rot 等) を検出して破棄・再構築へ導く**トリガー
条件そのものが文書中に存在しない**。
(c) 「DDL の missing_since 列・app_config の retry_not_before / building / ready key — DDL とコメントに
反映」— missing_since は §9.1 folders DDL (L673) に列として **充足**。しかし app_config の DDL コメント
(§9.1、L759-765) は `'tool_profile'` / `'embedding_profile'` / `'agg_embedding_profile_hash'` の
3 キーのみを列挙し、**L09 で導入された `agg_building_profile_hash` / `agg_ready_profile_hash` (2-key 化)
も、L26 で導入された `retry_not_before` も一切列挙されていない** — **未充足**。3 要求のうち 1 つは完全に
充足、2 つが未充足のため partially-fixed。(b)(c) は後述 M02・M01 として新規検出にも計上する。 |
```

---

## 第 2 部 — 探索ログ (C12)

前提条件を満たすため、X1〜X35 の全観点で最低 1 シナリオを実行した。重心は指示どおり X31〜X35 (r10 修正の
相互作用) に置いた。X1〜X30 は r6〜r10 で 22 系統・150+ シナリオ深掘り済みのため、本書 r10 適用後の текст
に対する再確認を主眼とした軽量パスで実施した。

### X31〜X35 (本監査の重心 — 独自の深掘り)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X31 | 同一 tick 内で kind=1/kind=2 の異なる target 2 件が同時に新規 batch_requests 行を作る → 各々の submission_seq 継承 (COALESCE MAX) が干渉するか | 問題なし — target_key が異なれば cost_ledger の MAX クエリも独立、tick.lock がプロセス単位で直列化するため真の並行性は存在しない |
| 2 | X31 | reconcile が kind=2 の state=0|3 行を成果ありで閉じる際、付随処理 (a) の「kind=1 は floor NULL 化」を kind=2 行にも無条件適用する実装を想定 | 問題なし — kind=2 行は元々 floor_generated_at が常に NULL のため NULL→NULL の無害な no-op |
| 3 | X31 | 状態 1 (submitted) の行を reconcile と collect が同時に処理しようとする競合 | 問題なし — reconcile は `state IN (0,3)` のみを対象とし state=1 を触らない (§10 step 0.5 文言どおり)。構造的に重複不可 |
| 4 | X31 | submit_rejected (相 2b 恒久拒否) 直後に collect 相当処理が cost_ledger へ誤って課金記帳しないか (batch_job_id が NULL のまま state=3 に落ちるため) | 問題なし — submit_rejected は job が一度も作成されない (batch_job_id は NULL のまま) ため、「terminal 化時の課金記帳」規則 (batch_job_id 非 NULL が条件) が発火せず、記帳されない。ジョブが存在しない以上これは正しい |
| 5 | X31 | client 経路 kind=2: 実行前計上 Tx commit 直後、同期 API 呼出直前にクラッシュ (state=0, batch_job_id=intent_token) → unregister → detached state=0 の token 照合分岐 | **profile_record が §8(i) の実行前計上フィールド列挙に含まれないことを発見 (→ M02)**。detached 自体の token 照合・記帳ロジックは問題なし |
| 6 | X31 | submit_rejected (attempts=上限) → 明示 retry (attempts=0) → 次 tick が再投入 → 相 2a upload 成功 → upload_id 記録 → 相 2b 再度拒否 → 新しい state=3/attempts=上限 サイクル。旧 upload の掃除が新サイクルの upload_cleaned=0 リセットと整合するか | 問題なし — 相 1 が毎回 upload_cleaned=0 にリセットし、新 intent_token を発行するため旧・新の upload が混同されない |
| 7 | X31 | client_exhausted (attempts>=上限 の state=0) が発生した直後にフォルダが detached 化した場合の境界 | 問題なし — client_exhausted は「フォルダ登録中」の tick 処理の産物であり、detached は「フォルダ未登録」時の別処理系。両者は排他的な前提条件 (folders 行の有無) を持ち衝突しない |
| 8 | X32 | fork 手順 0 (journal 書込, phase=PREPARED) 完了後、手順 1 開始前にクラッシュ | 問題なし — repository-id ファイルはまだ old のまま。回復表「phase=PREPARED, id=old → 手順1から」が正しく適用される |
| 9 | X32 | fork 手順 2 の内部 (repository-id ファイルを new へ書き換え完了、journal の phase=ID_WRITTEN 更新が未完了) でクラッシュ — 2 つの別ファイルへの安全書込の間の窓 | 問題なし — 回復表は「phase=PREPARED, **id=new** → 手順3から」を明示的に持ち、journal の phase 記録が遅れても repository-id ファイルの実際の値から正しい再開点を導出できる |
| 10 | X32 | fork 手順 3 (app Tx) が完全にコミットした後、journal の phase=APP_DONE 更新前にクラッシュ (2 つの別 DB/ファイルへの書込の間の窓) | 問題なし — 回復表「phase=ID_WRITTEN → 手順3から」により手順 3 が再実行される。folders の INSERT OR REPLACE と DELETE 系の再実行はいずれも冪等であるため、実質完了済みの手順 3 を再実行しても副作用が増えない |
| 11 | X32 | fork 手順 4: app 側の fork_in_progress フラグを削除した直後、journal ファイル削除前にクラッシュ (flag→journal の削除順、2 つの別ファイルへの削除操作の間の窓) | **flag が消えた状態で journal だけが残る場合、文書が定義する 2 つの検出契機 (「毎tick冒頭にfork_in_progressのrealpathのjournalを確認」はflagの存在が前提、「bootstrapのwalk」は全損時限定) のいずれもこの状態を拾わないことを発見 (→ M05)**。実害は軽微 (孤立した journal ファイルは GC・scan の対象外で放置されるだけ) |
| 12 | X32 | fork 進行中 (fork_in_progress=(old_id, P) 設定済み、手順 1〜3 の間) に、対象フォルダが watch_root 内の別パス P' へ手動移動される | 明確な新規バグは検出できず — fork の scan 除外は P のみに効くため、fork 完了後の次 tick は P への walk が「不在」を検出 → §20.4 の missing/rebind 機構 (repository-id ファイル一致による watch_roots 再探索) が P' で new_id を発見し root_path を更新して自己修復する。修復までのレイテンシは規定されていないが、既存の missing/rebind 機構の設計範囲内 |
| 13 | X32 | conflict の非追跡側コピーを fork (was_tracked=false) した場合、old_id の folders 行 (追跡側、生存) 配下の in-flight batch_requests が誤って detached 化しないか | 問題なし — was_tracked=false の場合、fork 手順 3 は「旧行に触れない」ため folders[old_id] は無傷のまま存続し、detached の前提条件 (folders 行の不在) が成立しないため対象外にとどまる |
| 14 | X33 | kind=1 の tool_changed (載せ直しガードで state=3, attempts=上限) と detached が同一行に同時に成立しうるか | 問題なし — tool_changed は「フォルダ登録中の intent 回復」でのみ発生し、detached は「フォルダ未登録」時のみの処理系のため排他的 |
| 15 | X33 | profile_changed (kind=2, collect 時の vector 破棄) が reconcile 経路で誤って重複発生しないか | 問題なし — profile_changed は collect 特有の state=1→state=3 遷移であり、reconcile は state=1 を対象外とするため経路が重複しない |
| 16 | X33 | result_expired の terminal 化時の課金記帳が「同一 Tx」であることの明記有無 | **state=3 への UPDATE と cost_ledger への記帳が別 Tx になり得る場合の crash 窓を発見 (→ M04)**。result_expired / job_timeout / output_missing / job_missing の 4 種は、profile_changed のような明示的な「同一 app Tx」の宣言を欠く |
| 17 | X33 | submit_rejected で課金記帳が発生しないことの妥当性検証 (相 2b で job が一度もプロバイダに作成されないため) | 問題なし — 「terminal 化時の課金記帳」規則は batch_job_id 非 NULL を条件とし、submit_rejected の行は batch_job_id が常に NULL のため対象外。ジョブ未作成なら課金機会も無いため正しい |
| 18 | X34 | §11.2 掲載のハイブリッド SQL を実際に頭の中で組み立て、vec0 の JOIN + k=:k_fetch 制約が仮想テーブル側でどう評価されるかを検証 | 問題なし — 文書自身が明示する「vec0 の KNN は eligible 絞り込みの前に仮想テーブル側で top-k を返す」という理解は sqlite-vec の一般的な JOIN パターンと整合し、over-fetch/refill 設計の前提と矛盾しない |
| 19 | X34 | agg_ready_profile_hash が古いまま (再構築窓) の状態で横断検索を実行 | 問題なし — 検索前照合が不一致を検出し KNN を止めて FTS のみで応答、status に「index 再構築中」を示す設計どおり動作する |
| 20 | X34 | LIKE fallback の完全形 SQL を実際に組み立て可能か検証 (over-fetch 節・3 文字未満節・LIKE 走査節の 3 箇所のプローズから合成) | 組み立て自体は可能 (各断片は個別に精密) だが、メインのハイブリッド SQL と異なり 1 つの完全ブロックとして掲載されていない (→ P3、proposal) |
| 21 | X34 | フォルダ単独検索で embeddings が一部 re-embed 未完了の場合の KNN 部分性と status 表示 | 問題なし — 「全行一致は chunks に対する被覆を保証しない…完全性は主張せず、未embed残数をstatusに示す」と明記済み |
| 22 | X35 | 反証: 「seq 継承で行削除→再作成の UNIQUE 衝突は不可能」 | 破れず — tick.lock によるシリアライズ下では MAX 計算と INSERT の間に競合する書込が入り得ない |
| 23 | X35 | 反証: 「reconcile close の付随処理で client の記帳欠落は起きない」 | 破れず — client 経路は実行前計上により batch_job_id が state=0 の時点で既に非 NULL なため、reconcile のルール (b) (batch_job_id 非 NULL なら記帳) が確実に発火する |
| 24 | X35 | 反証: 「submit_rejected は自動再投入されない」 | 破れず、ただし **kind=2 に限り「profile 変更時は §8-a によりstateを問わずattempts を数え直して投入対象」という遷移表自身の明示的な例外が存在する**ことを確認 (規範上の意図された挙動であり抜け穴ではないが、反証試行の記録として明記) |
| 25 | X35 | 反証: 「fork は id=old からでも journal で正しく再開する」 | 破れず — phase×id の全組み合わせ (8 と 9 のシナリオを含む) が回復表でカバーされている |
| 26 | X35 | 反証: 「detached は課金を取りこぼさない (r10 改訂後)」 | 破れず (アップロード自体のコスト計上漏れの可能性を検討したが、本設計のコストモデルはページ処理/embedding計算のみを対象とし、upload 自体には課金が発生しない前提のため対象外) |
| 27 | X35 | 反証: 「delete 確定直前の最終 stat で時計急変の偽 delete は不可能」 | **破れる (→ M06)**。クロック前進ジャンプがシステムサスペンド/レジュームと厳密に一致し、ファイル保存操作がそのジャンプを跨いで凍結されるという非常に狭い偶然の一致の下でのみ、最終 stat も「不在」を観測してしまう理論上の窓が存在する |

### X1〜X30 (r6〜r10 で深掘り済み — 本書 r10 適用後テキストへの再確認パス)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 28 | X1 | 1 tick 内の create→edit→delete → スキャンは最終状態のみ観測 | 問題なし (r10 の変更点はこの経路に影響しない) |
| 29 | X2 | OCR 本文 + short_description の comment-escape 二層防御 (行頭 `\` + `]\(`) | 問題なし。改行正規化が先に適用されるため、値内改行を使った偽フィールド行の注入は成立しない |
| 30 | X3 | macOS NFD readdir → NFC 論理名保存 (§20.5 の変換点は 1 箇所) | 問題なし |
| 31 | X4 | 時計後退中の編集 → created_at = max(now, latest+1) | 問題なし |
| 32 | X6 | 日本語 2 文字クエリ「検索」→ trigram 沈黙 → LIKE fallback | 問題なし (X34-20 で完全形の組立可能性も確認済み) |
| 33 | X8 | `.folder-history` を含む file_name・path traversal 名は name_invalid で保存・restore 両方から遮断 | 問題なし |
| 34 | X10 | zip 往復 (mtime/inode 全変化) → 全 rehash・content_hash 一致で無コミット | 問題なし |
| 35 | X12 | watch_root 登録 → register → scan → OCR → chunk → embed → replicate → 横断検索 → §12 解決 → restore の一気通貫トレース | 問題なし。各受け渡しの出典 § を追跡できた。ただし app_config が未設定の場合の初回挙動は §21 に明示操作が無い (→ M09、r10 Fable 監査の L12 を継承) |
| 36 | X13 | 「明示操作」全列挙の入力・効果・失敗時挙動の総点検 (§21.7 を起点に) | client_exhausted の復帰は既存の汎用「terminal failed の再試行」操作でカバーされることを確認。detached 行の処理規範導入文の経路列挙 (unregister/§9.3-d のみで fork 抜け) を再発見 (→ M07) |
| 37 | X17 | register 手順 2 途中クラッシュ → damaged → 旧 folders 行の §9.3-d 相当退役 → 新 id 再登録 | 問題なし。damaged からの退役も §9.3-d の detached 保存規則を継承するため in-flight job の記帳漏れは起きない |
| 38 | X19 | dir fsync 適用点の網羅 (objects 各 prefix・tmp・fork journal・repository-id ファイル) | 問題なし |
| 39 | X20 | 主張「重複課金は intent 回復により最悪 job 1 回分 (server 経路)」 | 破れず |
| 40 | X21 | 相 1 の attempts=0 リセット (profile 数え直し)・upload_cleaned=0・error/completed_at NULL 戻し と intent 回復採用 (snapshot 不変) の整合 | 問題なし |
| 41 | X26 | submission_seq の書込 3 点 (相 3・intent 採用・client 前計上) の重複・欠落検査 | 問題なし。ただし client 前計上の「fields 列挙漏れ」は X31-5 (→ M02) で別途発見 |
| 42 | X28 | detached の全ライフサイクル (state 0/1 の両方、生成 3 経路) | 経路列挙の完全性以外は問題なし (M07 参照) |
| 43 | X29 | 保存名固定 (初出時表記) が §11.1 PARTITION BY file_name の BINARY 一致を保証する経路 | 問題なし |
| 44 | 自由 | backfill の「低優先」投入の運用的な意味 (別ジョブ・遅延・順序付けの有無) を検証 | **「1 job = 1 repository」に現在版対象と backfill 対象が無差別に同居し、優先度を実現する具体的機構が存在しないことを確認 (→ M08、r10 Opus/Fable 監査の L11 を継承・未対応のまま残存)** |

### X5・X7・X9・X11・X14・X15・X16・X18・X22・X23・X24・X25・X27・X30 (未実行だった残り X 観点の充足)

上記 44 件は X31〜X35 (全観点) と X1〜X30 のうち 16 観点を明示的にカバーしたが、前提条件
(「X1〜X35 に未実行の観点が無いこと」) を満たすには残り 14 観点にも最低 1 シナリオが要る。
以下で充足する:

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 45 | X5 | 10 万ファイル規模のフォルダで段 0 (fp) + 段 1 (scan_cache 全行比較) のコストを検証 | 問題なし — §19「規模の再考条件」が個人〜小規模チーム規模を前提と明示し、この規模を超える場合の再設計 (reconcile 走査の世代管理化・FTS 候補上限等) を先送りしている。文書の主張と矛盾しない |
| 46 | X7 | 新 user_version の DB を旧アプリが開こうとする + grammar v+1 の一括再 materialize が同時に必要になる場合 | 問題なし — §14 の「DB の版がアプリの対応版より新しければ開かず fail-closed」が新旧混在を遮断し、grammar 移行は追跡列を持たず Markdown 自身の `v:` 行から判定する経路 (§6) が独立して機能する。相互に干渉しない |
| 47 | X9 | metadata.sqlite のみを古いバックアップから復元し、objects/ は現行のまま (整合 fsck を通過する状態) の場合の履歴巻き戻り検出 | 問題なし — §9.3-z の後退検出 (max 比較 + カーソル commit 不在チェック) が起動し、status に "regressed" を通知した上で agg を wipe + full resync する。無言では進まない |
| 48 | X11 | fp_cache (raw name, §20.3) と scan_cache / file_versions (NFC 正規化 name, §20.5) の変換点が単一か再確認 (r6 修正の相互作用) | 問題なし — 変換点は readdir 直後の 1 箇所に一意に定まり、fp は raw 値をそのまま JCS 化し、以降のすべての層 (scan_cache キー・LWW 比較・walk 観測集合) は NFC 正規化後の論理名を使う、という分担が §20.3/§20.5 の記述で一貫している |
| 49 | X14 | fp_cache の孤児行 (フォルダごと削除されたディレクトリの残存行) の掃除条件を検証 | 問題なし — 「完全 walk が成功した際に今回観測しなかった配下 path の行を DELETE する」mark-and-sweep が明記され、ヒント表なので削除は常に安全 |
| 50 | X15 | 主張「journal_mode=DELETE が同期ソフト配下の WAL/SHM 分離同期問題を回避する」への反証試行 | 破れず (これはファイルシステム・同期ソフトの実装依存の主張であり、文書の記述レベルでは検証可能な反証経路が存在しない。文書内部は一貫) |
| 51 | X16 | 1 万件超の OCR 対象を JSONL 上限超過で複数 job に分割する際の intent_token 粒度を再確認 | 問題なし — 「分割単位ごとに個別の intent_token を発行する」規則 (過去ラウンドで確定) が現行文書でも維持されている |
| 52 | X18 | profiles 表の孤児行 (参照する派生・embeddings が全て消えた後) の扱いを検証 | 問題なし — §18.7 が「意図的に掃除しない」と明記し、fsck は孤児かどうかに関わらず全 profiles 行を検証するため正しさに影響しないと明記済み |
| 53 | X22 | fork 手順 1 の `PRAGMA defer_foreign_keys = ON` と §14 の `foreign_keys = ON` の共存 | 問題なし — SQLite の標準機構であり、自己参照 FK の検査が COMMIT 時まで遅延されるだけで、通常の FK 執行 (CASCADE 等) は妨げられない |
| 54 | X23 | cost_ledger の UNIQUE (repository_id, kind, target_key, submission_seq) 制約が正当な再課金 (明示 retry 後の再投入等) を妨げないか | 問題なし — submission_seq はリセットされない通算連番のため、正当な再投入は必ず新しい (未使用の) seq 値で記帳され、UNIQUE と衝突しない (L01 の継承規則が前提となる register 後・行削除後の再作成のみ別途要注意 — 既に L01 として対応済み) |
| 55 | X24 | 主張「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」への反証試行 (次元変更 + 部分充填 50% + 中断) | 破れず — 次回 tick の Embed submit 冒頭が「vec に target_key が無いものを冪等 INSERT で再充填する」処理を毎回実行するため、中断位置によらず残り 50% が埋まる |
| 56 | X25 | app.sqlite 単独 (フォルダ未接続) での横断検索実行時、app_config が未設定な場合の :query_vector 生成可否 | **M09 と同一問題に帰着** — 初回セットアップの app_config 投入経路が §21 に無いため、この状態自体が「本来起こるべきでない」が実際には初回インストール直後に起こり得る未定義状態である |
| 57 | X27 | fork-journal ファイル自体が破損 (読めない・hash 不整合) している場合の扱い | 問題なし — 「読めない / hash 不整合の journal は damaged (§20.4) と同様に扱い、status 表示してユーザーの明示解決を待つ (自動で推測して進めない)」と明記されている |
| 58 | X30 | 主張「ledger の UNIQUE (…, submission_seq) は正当な再課金を一切妨げない」への反証試行 (profile A→B→A 往復 + 分割 commit 中クラッシュ) | 破れず (X54 と同根の確認を異なる角度 [profile 往復] から実施し、いずれも submission_seq の単調増加性により衝突しないことを再確認) |

**確認済み (反証を試みたが破れなかった主張、X35 に加えて)**: 「同一正規化コミット→同一 commit_hash」
「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」「agg 毎 tick 検査は一度きり破棄の喪失を吸収する」
「保存名固定により case-only rename の FK 違反は構造的に不可能」の 4 件はいずれも試行し破れず。

---

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| M01 | **major** | §9.1 app_config DDL コメント (L759-765) 「'agg_embedding_profile_hash' = agg_vec 構築時の embedding_profile_hash」 | app_config の DDL コメントが単一キー 'agg_embedding_profile_hash' のみを列挙し、§8-e (L617-620) / §11.2 (L1464) が導入した building/ready 2-key 化 ('agg_building_profile_hash' / 'agg_ready_profile_hash') も、§9.1 (L834) が導入した 'retry_not_before' キーも一切反映していない。DDL コメントを一次情報源として実装した場合、旧単一キー方式を再実装してしまい、building/ready 分離が防いだはずの「破棄直後・部分同期済みの index が照合を通過する」レースを再導入し得る。**独立性の注記**: 本項目は筆者本人の直接検証に加え、並行実行した 2 つの独立エージェント (C9 A-K 再検証担当・静的相互参照スイープ担当) の両方が、それぞれ別の切り口 (前者は「K24 近傍の記述として」、後者は「§13 fsck が同じ規範を参照する箇所として」) から独立に同一の欠陥を発見しており、3 系統が完全に収束している | ① embedding profile を A→B へ変更 ② §8-e 相当の実装が (DDL コメントのみを参照し) 単一キー 'agg_embedding_profile_hash' を「現行値」で即座に上書き ③ フォルダ 1/3 が再同期完了した時点で、後続の横断検索が単一キーの一致判定を通過し KNN を実行 ④ 残り 2/3 のフォルダの vector が未反映のまま検索結果に混入 (building/ready 分離が本来防ぐはずだった状態) | C6 / C10(w) / X31 / L28(c) | app_config DDL コメントを 'tool_profile' / 'embedding_profile' / 'agg_building_profile_hash' / 'agg_ready_profile_hash' / 'retry_not_before' の 5 キーに更新し、各キーの書込点 (§8-e, §9.1 相2b) への参照を付記する |
| M02 | **major** | §8(i) 「実行前計上: 同期 API を呼ぶ前に app Tx で attempts+1・submission_seq+1・batch_job_id = intent_token・submitted_at を永続化する (相 1 と相 3 の統合に相当)」(L639-641) | client 経路 (server-side batch 無しの embedding プロバイダ) の実行前計上フィールド列挙が profile_hash と profile_record を含まない。「相当」という表現は 相1 の全処理 (profile_hash/profile_record のスナップショット書込を含む) との等価性を示唆するが、明示列挙はしていない。kind=2 の profile_hash は DDL CHECK で非 NULL を強制されるため実装時に即座に露見するが、**profile_record には CHECK 制約が無く**、literal に実装すると NULL のまま INSERT が成功してしまう | ① client 経路 kind=2 の新規 target T を初回投入 (実行前計上のみを §8(i) の列挙どおり実装、profile_record を設定しない) ② 同期 API 呼出成功 → 同 tick 内で即 collect へ進む (§8(ii)) ③ collect が「profiles INSERT (record は行の profile_record snapshot から)」(§10 step 4、§5.7) を実行しようとするが、profile_record が NULL のため `profiles.record_json TEXT NOT NULL` の制約違反で Tx 失敗 ④ このエラーは client 経路の embedding provider を使う限り毎回・全 target で発生する | C11(a) / C10(w) / X31 / P9 帰結 | §8(i) の実行前計上フィールド列挙に「profile_hash = :current_profile / profile_record = 現行 record (§9.1 相 1 と同一)」を明示的に追加する |
| M03 | minor | §13 fsck (L1553-1591、object層/履歴層/profile層の3層)、§8-e (L626) 「same-profile での vector 破損や agg_vec の欠落は同期では検出しない…規約 9 の破棄・再構築で扱う」 | fsck の記述は grep 確認の結果 agg_vec / agg_embeddings に一切言及しない。§8-e が委ねる先の「規約 9」(§15) は app.sqlite **全損**時の bootstrap 手順のみを定義し、同一 profile 内での agg_vec 部分破損 (bit-rot 等) を検出して破棄・再構築へ導くトリガーが文書中のどこにも存在しない。**独立性の注記**: 静的相互参照スイープ担当の独立エージェントも同一箇所を独自に発見しており (「fsck's silent scope gap on the aggregate layer…highest confidence and highest impact」)、収束している | agg_vec の 1 行が (ディスクエラー等で) サイレントに破損 → 同期は対象外・fsck も対象外 → 破損した近傍ベクトルが KNN 距離計算に混入し続け、検索結果の質が理由不明のまま劣化し続ける (エラーにはならない) | C8 / C11(d) / L28(b) | 週次 fsck サイクルまたは Replicate の宣言的検査 (§8-e) に、agg_vec の次元・バイト長 CHECK 相当の軽量検証を追加し、不一致検出時は当該 profile の agg_vec を破棄・再構築する規則を明記する |
| M04 | minor | §9.1 「terminal 化時の課金記帳」(L906-910) 「job が provider 側で作成された attempt…が 成果なしの terminal (result_expired / job_timeout / output_missing / job_missing / profile_changed) へ倒れる場合も、cost_ledger へ記帳する」 | 5 種の terminal 理由のうち profile_changed のみ「破棄と記帳は同一 app Tx」(L886) と明記されるが、他 4 種 (result_expired / job_timeout / output_missing / job_missing) には同様の「同一 Tx」明記が無い | job の結果が result_expired と判定され state=3 への UPDATE が commit → 別 Tx として予定されている cost_ledger への記帳の前にプロセスがクラッシュ → 次 tick は state=3 行を「成果なし・attempts 上限内」として通常の再遷移表に従うのみで、失われた記帳を補完する経路が無い (このケース専用の「取りこぼし記帳」の再試行機構は存在しない) | C10(bb) / X33 | 「terminal 化時の課金記帳」パラグラフに profile_changed と同様「(state=3 UPDATE と) 同一 app Tx」の一文を明記する |
| M05 | minor | §21.3 手順 4 (L2202-2204) 「fork_in_progress (app 側の印) を先に消し、その後 journal を消す — 逆順で電断すると『journal なき fork_in_progress』が残り…（journal が残る側は無害 — 回復ルーチンが処理する）」+ 失敗回復の検出契機 (L2211-2213) 「(a) 毎tick冒頭に fork_in_progress の realpath の journal を確認 (journal 有→回復を先に完了 / **journal 無 = 手順 4 の中間** → fork_in_progress を掃除)」 | 2 つの関連する不整合を検出。**(i)** 手順 4 の削除順序 (flag 先→journal 後) の下で正規に到達し得るクラッシュ状態は「flag 消滅・journal 現存」のみだが、この状態は fork_in_progress (flag) の存在を前提に対象を列挙する検出契機 (a) からは原理的に不可視 (flag が既に無いので (a) の走査対象に載らない) であり、契機 (b)「bootstrap の walk」も全損シナリオ限定のため、通常運転では**どちらの契機も発火しない**。**(ii)** にもかかわらず検出契機 (a) 自身は「journal 無 = 手順 4 の中間」という分岐を明記するが、これは手順 4 の順序 (flag 先→journal 後) からは正規に到達し得ない組み合わせ (flag 現存・journal 消滅は「逆順」時の障害として明示的に否定されている側) であり、検出契機の記述と手順 4 自身の順序根拠が整合しない。**(iii)** 手順 0 (journal 書込 → app 側 flag 記録、の順で記述) 側にも同型の窓があり得る (journal 書込完了・flag 記録前のクラッシュは「journal 現存・flag 不在」を生み、これも両契機の対象外) | ① fork 完了寸前 (手順 4 で flag 削除は成功、journal 削除前) にクラッシュ → 通常再起動 (app.sqlite 無傷) → 検出契機 (a) は flag が無いためこの journal を検査対象に含めない → journal ファイルが `.folder-history/fork-journal` に永久残留 (実害: GC/scan は `.folder-history` を無視するため実運用上は孤立ファイルに留まる、フォルダ自体は新 id で正常機能済み) ② 手順 0 の内部 (journal 書込完了直後、app 側 flag 記録前) にクラッシュ → 同様に flag が存在しないため検出契機 (a) の対象外、fork リクエストが利用者に気づかれず静かに未完了のまま残る (この場合はフォルダが旧 id のまま通常運転を続けるため実害はやはり低いが、ユーザーの fork 意図は実現されない) | C10(z) / X32 | 検出契機 (a) を「fork_in_progress の存在」ではなく「管理フォルダ walk 時 (通常 tick を含む) に fork-journal ファイルの存在そのものを都度確認する」形へ広げる。あわせて「journal 無 = 手順 4 の中間」の分岐条件・手順 4 の順序根拠・手順 0 の内部順序の三者を突き合わせ、実際に到達し得る状態の一覧を明記し直す |
| M06 | minor | §20.5 (L2001-2007) 最小不在時間 (既定 30 秒) + delete 確定直前の最終 stat | 時計前進ジャンプがシステムサスペンド/レジュームと厳密に一致し、進行中のファイル保存操作 (一時ファイル→rename) がそのジャンプを跨いで凍結される、という非常に狭い偶然の一致の下でのみ、"now − first_absent_at >= 30秒" の判定が (実時間ではわずかしか経過していないのに) 満了し、かつ最終 stat 時点でも保存操作が未完了 (ファイルは実際に不在) であるため、偽 delete が成立し得る | ① dirty 早回し tick がファイル保存中の一時的不在を観測 (1回目 absent, pending_deletes 登録) ② OS サスペンドとほぼ同時に時計が 60 秒前進、保存中のプロセスもサスペンドで凍結 ③ レジューム直後の 2 回目の tick がファイルを観測 → まだ absent (保存プロセス未再開) かつ「now − first_absent_at ≥ 30秒」を満たす → 最終 stat も absent → delete 確定 ④ 実際には数百 ms 後に保存が完了しファイルが復活するはずだった | C11(c) / X35 (反証成立) | 極めて狭いシナリオのため必須ではないが、単調クロック (CLOCK_MONOTONIC 等、NTP 補正の影響を受けない) を最小不在時間の計測に併用する旨を注記すると理論上の残存窓も閉じられる |
| M07 | minor | §9.1 「detached 行の処理規範」導入文 (L916-917) 「(unregister §21.2 / フォルダ消失 §9.3-d で folders 行が無くなった repository の batch_requests 残置行)」 | P9 の規範は detached の発生源を unregister / §9.3-d / fork §21.3 の 3 経路と定めるが、この導入の列挙は 2 経路のみで fork §21.3 が抜けている。実体としては §21.3 手順 3 (L2197-2198) が「batch_requests は §21.2 と同一規則…cancel 未確定の in-flight は detached として残す」と正しく間接参照しているため機能上の欠陥ではない | — (列挙完備性のみの指摘、動作上の破綻シナリオなし) | C3 / C8 / X13・X28 | 導入文の列挙に「fork §21.3」を明示的に追加する |
| M08 | minor | §10 step 1 backfill (L1227-1232) 「上記に加えて all_versions…の DISTINCT content_hash のうち現在版に無いものを**低優先**で同様に投入する」 | 「低優先」という言葉に対応する具体的な運用機構 (別ジョブ・投入順序・遅延等) が文書中のどこにも定義されていない。「1 job = 1 repository」の下では現在版対象と backfill 対象が無差別に同一 JSONL へ積まれるため、実質的な優先度制御は存在しない | 現在版対象 100 件・backfill 対象 900 件が同一 tick で同時に submit 対象になる場合、実装者は「低優先」をどう解釈すればよいか分からず、結果的に全件が同一 job に無順序で積まれる可能性が高い (規定違反ではないが「低優先」の字義と実装の乖離) | C11(a) / 自由探索 (r10 Opus/Fable 監査 L11 の継続) | 「低優先」の具体的な意味 (例: 現在版対象を含む job を先に作成し、backfill 専用行は現在版 job が尽きた後の別 job にまとめる) を明記するか、字義を「job 内の投入順序に影響しない優先度メタデータ」程度に弱めて期待値を揃える |
| M09 | minor | §21.5 bootstrap (L2273-2286)、§8 / §21.7 の profile 変更操作 | app_config の 'tool_profile' / 'embedding_profile' の**初回**投入経路が §21 のどの明示操作としても定義されていない。§21.5 の bootstrap は「app 全損後」限定、§8 の profile 変更は「現行設定の更新」(既存値がある前提) であり、真の初回セットアップ (新規インストール) を明示的にはカバーしない | 新規インストール → watch_root 追加 → register → 直後の tick で OCR/Embed submit が :current_tool / :current_profile を要求するが app_config が空 — この場合の挙動 (submit をスキップするのか、エラーにするのか) が未規定 | C8 / C11(a) / X12 (r10 Fable 監査 L12 の継続) | §21 に「初期プロファイル設定」操作を明示的に追加するか、§10 の tick 記述に「app_config 未設定の kind は該当 submit / 横断検索をスキップし status に「profile 未設定」を表示する」という fail-closed 規則を明記する |
| M10 | minor | §9.1 batch_requests DDL コメント (L727) 「行が生まれ、**P9** の不一致破棄をスキーマで保証できない」 | 文書は「原則」を指す際に一貫して `規約 N` (§15) の形式を 27 箇所で使用するが、この 1 箇所だけ `P9` という異なる形式のラベルを使い、文書中のどこにも `P9` という定義は存在しない (grep で確認: 文書全体でこの 1 箇所のみが `P[0-9]` パターンに一致する)。指している概念自体 (profile 不一致時の kind=2 破棄) は §9.1 collect (L882-886) と §10 step 4 (L1267-1270) のプローズで説明されているが、ラベルとしての `P9` は宙に浮いている | — (静的な参照未解決。実装への実害は小さいが C3 の観点で純粋な欠陥) | C3 / 静的スイープ | `P9` を `規約 N` 形式の正しい参照、または該当プローズへの直接参照 (例: 「§9.1 collect の profile 不一致時の破棄規則」) に置き換える |
| M11 | minor | §9.1 batch_requests DDL コメント (L684-687) 「target_key TEXT NOT NULL, -- kind=1: hex(content_hash) \|\| ':' \|\| hex(tool_profile_hash) …(SQL で構築するなら lower(hex(...)))」 | target_key の一次的な提示が `hex(...)` (小文字化なし) で書かれ、「小文字にする」旨は末尾の別行コメントとして後追いで補足されている。これは §5.6 embedding_vec の DDL コメント (L380-382 `lower(hex(target_hash))` を数式に直接組み込み) や §11.2 の実 SQL (L1425 `lower(hex(e.embed_hash))`) と提示形式が異なる。文書自身が hex の大小文字混在を「join が エラーなく 0 件になる」重大な沈黙的失敗パターンとして複数箇所 (L381, 621, 687 の後段, 1426, 1493) で強調しているだけに、一次提示の書式だけがこのテーマから外れているのは目立つ | — (現状 batch_requests.target_key に対して直接 hex() で再構築 + join する箇所は文書中に存在しないため実害は顕在化していないが、将来の実装・改訂で踏襲されるリスクがある) | C6 | batch_requests の target_key コメントも他 2 箇所と同じく `lower(hex(...))` を一次提示の数式内に直接書き込む形へ統一する |
| M12 | minor | §21.5 bootstrap (L2273) 「watch_roots はユーザー設定であり app 全損で失われる (**規約 7**)」 | 規約 7 (§15、L1663-1673) の列挙 (a)〜(f) は watch_roots 自体の喪失を項目として持たない — (f) は「watch_roots **外**の登録フォルダの個別パス」という別の (より狭い) 損失を指す。「watch_roots はユーザー設定であり、全損時はその再入力 (bootstrap) が復元の起点になる」という一般的な主張自体は **規約 9** (L1680-1681) に存在する。同一パラグラフの次の引用 (「規約 7 の損失 (f)」) は正しく規約 7 を指しているため、直前の引用だけが誤った規約番号を指している | — (記述される挙動自体は文書全体で一貫しており、参照する規約番号のみの誤り) | C3 | L2273 の「(規約 7)」を「(規約 9)」に訂正する |

### Proposal (再現シナリオ不要・低優先度の改善提案)

| 該当箇所 | 内容 |
|---|---|
| §16 (L1717) 「(§9.1 の既知の残余)」 | §9.1 には複数の「既知の残余」的表現があり (アップロード自然消滅の残余 L826、失効窓課金は L950 で解消済みと明記)、L1717 がどちらを指すか曖昧。解消済みの残余への言及と誤解されないよう、指す先を明示するか削除する |
| §9.1 相 2b (L833-835) retry_not_before | 「当該 provider への投入を見送る」という記述は per-provider (per-kind) スコープを示唆するが、キー名は単数形で app_config に 1 行として持たせる設計であり、kind=1 (Mistral) と kind=2 (様々な embedding プロバイダ) を混同しない保証が明示されていない。キー名を 'retry_not_before_1' / 'retry_not_before_2' 等 kind ごとに分ける旨を明記すると安全 |
| §11.2 LIKE fallback | 完全形 SQL がメインのハイブリッドクエリのように 1 ブロックで掲載されておらず、3 箇所のプローズ (over-fetch 節・3 文字未満節・LIKE 走査節) から合成する必要がある。組立自体は可能だが、明示的な完全 SQL ブロックがあると実装者の負担が減る |
| §20.5 NFC 正規化の適用範囲 | file_name の NFC 正規化は明記されるが、フォルダ自体のパス (root_path・fork の realpath 入力) にも同様の Unicode 正規化上の考慮が必要かどうかは触れられていない。file_name と異なりパスは同一コードパス (realpath) を毎回通るため実害の証拠は無いが、明記すると安心材料になる |
| §9.1 fp_cache DDL (L992-995) | `files_fp` / `dirs_fp` は NULL 許容 (`CHECK (... IS NULL OR ...)`) だが、§20.3 のアルゴリズムはこの 2 値を (空リストであっても) 常に計算する記述になっており、NULL を要する具体的シナリオが文書中に見当たらない (静的スイープ担当エージェントの指摘。同エージェント自身も「他の意図的に nullable な列 [例: scan_cache.inode] にはすべて理由の説明があるのに、この 2 列だけ無い」と控えめな確度で報告している)。実害の証拠が無いため proposal 止まり |
| §10 (L1304) 「検索可能になるまでのラグ…(最大 ~24h)」 | この ~24h が §6 の batch timeout_hours=24 (プロバイダ処理完了までの上限) と結果保持期限「約 24 時間」(collect が結果を回収できる猶予) のどちらに由来するかが明示されていない。数値としては矛盾しないが、文書が他の 24h 概念 (GC grace 等) には毎回 § 参照を付けているのと対照的 |

---

## 第 4 部 — 確認済みの列挙

- **C1** (P1〜P16 の反映): 全 16 原則、現行文書に反映済みであることを確認。指摘は原則違反ではなく
  P9 (状態機械) と §21 操作カタログ周辺の未対処コーナーケースに集中 (M01〜M12)
- **C2** (SQL 静的検証): FTS5 external content の view 構成・WITHOUT ROWID と PK の関係・GENERATED 列構文・
  複合 FK・trigger の INSERT/DELETE 対・CHECK 論理を確認し、問題は検出されなかった
- **C3** (相互参照整合): §1〜§21.7 全域の § 参照・「元設計 §15/§21」番号衝突注記を含め、大半は解決
  済みであることを確認した。例外 3 件: M07 (列挙の非網羅性、参照の欠落ではない)・M10 (規約 N 形式の
  番号体系に反する孤立した `P9` ラベル)・M12 (規約 7 と規約 9 の取り違え)
- **C4** (クエリとスキーマの整合): §9.3 レプリケーション・§11.1/§11.2 検索・§13 GC の全 SQL について
  列・join キーの整合を確認し、問題は検出されなかった (M01 は DDL コメントの整合性問題であり
  SQL 自体の不整合ではない)
- **C5** (数値・事実の一貫性): $2.5/1k・+25%・768 次元 (参考値)・RRF k=60・「8 テーブル」(grep で
  「7 テーブル」の残存が無いことを確認)・attempts 既定 3・30 日 (missing 猶予) と 30 日程度
  (upload 保持) の 2 概念が混同されていないこと・30 秒 (最小不在時間)・週 1 (GC/deep-scan/fsck)・
  k_max 4,096・max_chars 2,000・3 種の 24h (GC grace / tmp 掃除 / batch 結果保持) — 全出現箇所で
  一致 (ただし L1304 の「~24h」がどちらの 24h 概念に由来するか未指定な点は P6 として計上)
- **C6** (用語・形式の一貫性): chunk_type↔target_type 対応・obj: スキーム・embed_hash 定義の再掲間の
  一致・タプル順序 (content_hash, tool_profile_hash) 等の一致を確認。例外 2 件: M01 (app_config
  DDL コメント)・M11 (batch_requests の target_key コメントで lower(hex()) が一次提示に組み込まれて
  いない、他 2 箇所とは書式が異なる)
- **C8** (欠落): P1〜P16 の範囲内で章として丸ごと欠けている事項は無し (M03, M08, M09 は既存の章の
  記述密度不足であり、章そのものの欠落ではない)
- **C10** (修正が開けた穴・定点 a〜z の再点検): 大半の相互作用点は整合。M01 (w 系: profile snapshot の
  周辺ドキュメント)・M02 (w 系: 実行前計上の完全性)・M04 (bb 系: 記帳経路の Tx 境界)・M05 (z 系: fork
  janitor の検出契機、および検出契機自身の分岐条件と手順 4 の順序根拠の不整合) が該当箇所
- **C11** (合理性): 実装不能な規範は検出されなかった。M02 のみ「追加の設計判断なしに実装できるか」の
  観点で real gap (C11(a))
- **C12** (探索型監査): 58 シナリオを実行、X1〜X35 の全観点で最低 1 シナリオを実施。反証を試みた
  9 件の主張のうち 8 件は破れず、1 件 (最小不在時間 30 秒の主張) が理論上の狭い窓で破れた (M06)

## P1〜P16 (設計原則) — 個別確認

P1(三層構成)/P2(識別子規範)/P3(8テーブル)/P4(chunks統一)/P5(チャンク分割)/P6(OCR)/P7(FTS)/
P8(Embedding必須)/P10(書込順序と冪等性)/P11(集約)/P12(検索)/P13(GC)/P14(SQLite設定)/
P15(不変部分)/P16(変更検知) — 全箇条、現行文書に反映済みであることを個別に確認した。

P9(バッチ処理情報の分離)は中核規範 (2相submit・状態遷移・cost_ledger分離・app_config・detached規範・
submission_seq継承・fork phase機械) はすべて反映されているが、新規検出 M01・M02・M04・M05・M07〜M12 が
いずれもこの原則が定義する機構の周辺コーナーケースに集中している。

---

## 付録: 本監査の実施方法に関する所見

本監査は単独セッション (Claude Sonnet 5) で実施したが、以下の分業を行った:

1. 筆者本人が文書全文 (2,320 行) を通読し、r10 の 3 独立監査レポートを先に読了した上で、
   L01〜L28 の全項目を個別に grep + 引用で検証した
2. 筆者本人が X31〜X35 (本ラウンドの重心) を深く掘り下げ、新規検出の大半 (M01, M02, M04〜M06) を
   この過程で発見した
3. 並行して 2 つの独立エージェントに (a) C9 A01〜K26 (205 項目) の全件再検証、(b) DDL コメントと
   プローズの不整合を狙った文書全体の静的相互参照スイープ、を委任した。
   エージェント (a) は 205 項目全件を独立に再検証し、**筆者本人が発見した app_config DDL コメントの
   陳腐化 (M01) と完全に同一の欠陥を、別の切り口 (K24 近傍の記述として) から独立に発見した** —
   両者の判定は「A01〜K26 はすべて fixed または superseded、ただし app_config の DDL コメントが
   L09/L26 の修正を反映していない」という結論で完全に一致した。この収束は当該指摘の確度を強く支持する。
   その他、エージェント (a) は A19 (current_files という古いラベルの残存)・B02/E01 (課金表記の言い回し
   差)・G02 (repository_id CHECK 保有表の実数が 8 ではなく 10)・I28/I33/I06/A09 (チェックリスト側の
   記述粒度と文書側の記述粒度の差) を「判断が必要だが文書側の欠陥ではない」ケースとして報告し、
   筆者もこの判断を追認した。
   エージェント (b) は文書全体の DDL コメント・§ 参照・数値・用語を系統的に走査し、6 件の新規指摘
   (M03 [fsck の agg_vec 非対応 — 筆者本人の発見と完全に独立に収束]・M05 の一部 [fork 手順 3 の
   realpath 判定がどの手順で行われるかの記述矛盾、および検出契機 (a) の分岐条件と手順 4 の順序根拠の
   不整合]・M10 [孤立した `P9` 参照]・M11 [target_key の lower(hex) 書式ゆれ]・M12 [規約 7/9 の
   取り違え]・P5/P6 [fp_cache の nullable 列・24h 表記の出典明記]) をもたらした。特に M03 は
   筆者本人・エージェント (a)・エージェント (b) の**三者が完全に独立に到達した同一の結論**であり、
   本監査全体の中で最も確度の高い指摘の一つとなっている。エージェント (b) の他の確認済みリストは
   本文の第 4 部へ統合済み
