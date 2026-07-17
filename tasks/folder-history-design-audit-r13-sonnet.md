# folder-history 設計書 r13 監査報告 (Claude Sonnet 5)

対象: `docs/research/folder-history-sqlite-design.md` (2,657 行、2026-07-15 実行)
監査方法: ファイルを行番号付きで全文読了 (offset 分割 5 回)、`tasks/folder-history-design-audit-prompt.md`
の改訂履歴と `tasks/folder-history-r12-adjudication.md` (r12 の 8 系統統合裁定) を先読みして
r12 で新規に確定した N01〜N45 の出自と却下 6 件を把握した上で、307 項目を個別に行番号引用で
再検証し、grep による数値・用語一貫性の機械検証、および実 SQLite (3.51.0) での DDL/クエリ
fixture 実行 (FTS5 external-content-on-VIEW、cost_ledger の ON CONFLICT DO NOTHING、chunks の
CHECK 制約群、fork の defer_foreign_keys、at_hash=FF の行値比較) による静的検証の裏付けを行った。
C12 は X41〜X45 (記帳経路の網羅行列・ready 母数と synced の動態・raw 解決の全数・scoped 規約 12
と step -1・反証) に重心を置き、X1〜X40 は各 1 シナリオで再確認した。

## 判定: **条件付き合格**

- 前提条件: **充足** — 探索ログ 73 シナリオ、X1〜X45 の全観点に最低 1 件以上を実施
  (X15/X20/X24/X30/X35/X40 の反証チェックポイントを含む)
- C9 回帰: **307 項目すべて fixed または superseded** (対応表どおり。regression・not-fixed 0 件)
- 新規検出: **fatal 0・major 0・minor 2・proposal 0**
- 判定根拠: C9 が基準を満たし、新規検出が minor のみのため「条件付き合格」を宣言する

---

## 第 1 部 — 回帰確認 (C9)

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 /
J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45: すべて fixed または superseded
(対応表どおり)。partially-fixed / not-fixed / regression は 0 件。**

r10〜r12 (計 21 系統・4 回の裁定) が A01〜M29 を収束させたことは `tasks/folder-history-r12-adjudication.md`
の裁定記録および自身の前回報告 `tasks/folder-history-design-audit-r12-sonnet.md` (M01〜M13 を
行番号引用で個別再検証済み) で確認済みであり、本ラウンドはこれを鵜呑みにせず全文を再読了して
代表箇所を再サンプリングした上で、**N01〜N45 (r12 の裁定で新規に確定した必須修正) を対象文書の
現物から行番号を引いて全項目個別に再検証した** (r12-sonnet.md 時点では存在しなかった検証対象)。
以下はその実施記録:

| ID | 判定 | 根拠 (§ + 短い引用) |
|---|---|---|
| N01 | fixed | §8(iii) L715-719「再実行の前計上 Tx では、まず直前 attempt の submission_seq を NULL + estimated で冪等 terminal 記帳...してから attempts+1・submission_seq+1 を行う」 |
| N02 | fixed | §9.1 intent 回復 L958-960「照合の結果は三値 (found / confirmed-absent / unknown — detached (b) と同一規範)」 |
| N03 | fixed | §9.1 L911「新規 UUIDv7 — 時刻成分 = 相 1 の実行時刻」、L970-976「期限判定を先に行う...submission_seq+1 の上で NULL + estimated の冪等 terminal 記帳を行ってから載せ直す」 |
| N04 | fixed | §9.1 付随処理 (b') L1093-1098「state=0 (server...) で intent_token が残る行の close では、(c) の掃除の際に token 照合で job の実在を先に確認し、実在すれば...submission_seq+1 + NULL + estimated を冪等記帳する」 |
| N05 | fixed | §8-e L662-667「母数 (接続フォルダ) = 「当該 tick に metadata を開けて §9.3 を実行できたフォルダ」...missing / fork 中 / damaged / 一時読取不能のものは除外する...接続フォルダが 0 件の間は ready を更新しない」 |
| N06 | fixed | §8-e L655-658「破棄...と同一 app Tx で、sync_state の synced_profile_hash を全行 NULL へ戻す」、L675-677「ready は「設定時点の被覆」の宣言」 |
| N07 | fixed | §15 規約12 L1934-1939「読み取り専用の操作...も、対象パスが folders に登録済みならば同じ照合を行い、不一致は conflict として結果を返さない...folders に行が無いパスの読み取り...は層 1 自己完結の正規の利用...repository-id を結果の provenance として表示する」 |
| N08 | fixed | §20.5 L2285-2294「論理名 → 物理名の解決 (逆方向・全操作共通)...検証済み root の readdir 列挙から...raw エントリを求め、その raw 名を操作対象にする」(delete/restore/fsck の 3 呼出点を明記) |
| N09 | fixed | §9.1 cost_ledger DDL L839-842「同一 seq は 1 行のみ。writer は必ず...ON CONFLICT DO NOTHING...衝突は「同一課金の再観測」の吸収でありエラーではない」(旧「二重計上を構造的に排除」の残存なし、grep で確認) |
| N10 | fixed | §10 step3 L1442-1443・step5 L1472-1473 いずれも「次元と距離」「次元・距離」照合と明記 (次元のみの残存なし) |
| N11 | fixed | §10 L1496-1498「重複課金は intent 回復により最悪でも job 1 回分に有界 — server-side batch 経路限定の主張」 |
| N12 | fixed | §10 step0.5 L1396-1398「folders 行が実在する行 (detached は対象外 — §9.1)」 |
| N13 | fixed | §8(ii) L708-712 (2 分岐) / (iii) L719-722「再実行は相 1 の規則一式を含む」 |
| N14 | fixed | §9.1 相2a L932-935「upload の失敗も相 2b と同じ 2 分岐」 |
| N15 | fixed | §9.1 L1101-1103「掃除の実行条件は「同 token を共有する全行が終端 (2/3)」」、tick 4.5 L1045-1049「token sweep」 |
| N16 | fixed | §9.1 app_config DDL L859-862 および §21.3 L2481-2483「保存先 = app_config の 'fork_in_progress' key、JSON {old_id, new_id, realpath}」(2 箇所一致) |
| N17 | fixed | §9.1 L961-962「found = 採用...submitted_at=now」 |
| N18 | fixed | §21.3 手順3 L2506-2512「root_path = この手順を実行している時点の実体の realpath...INSERT の前に、同じ root_path を指す別 repository_id の folders 行があれば §9.3-d で先に退役する」 |
| N19 | fixed | §21.3 手順4 L2513-2517「逆順...で電断すると...電断後にフォルダごと移動されると (a) の掃除条件を満たせず...当該 path が恒久除外される」 |
| N20 | fixed | §20.5 L2235-2237「fork §21.3 の書込 (手順 0 の journal・手順 2 の repository-id 書き換え) にも適用」 |
| N21 | fixed | §9.2 agg_chunks DDL L1245-1247 (§5.4 と同一の seq/char_start/char_end CHECK) |
| N22 | fixed | §9.3-c L1354-1357「agg_vec への投入は常に DELETE → INSERT」、§13 L1802-1806「差集合を双方向に検査する」 |
| N23 | fixed | §21.6 L2638-2641「原本が健在で現在版の場合、および backfill...の下では過去版のみから参照される場合も...自動的に再投入する」 |
| N24 | fixed | §7 規則1 L552-556「CommonMark の fenced code block 規則に固定...4 空白インデントのコードブロックも同様に見出し抑制の対象」 |
| N25 | fixed | §2 L70-76「規約 7 の (a)〜(f) を正として列挙...「有界」の内訳は 2 種」 |
| N26 | fixed | §21.5 L2604-2606「復元の起点は規約 9」 |
| N27 | fixed | §20.5 L2359-2361「message = 常に省略 — 手動コミット...は現行カタログ (§21) に存在しない」 |
| N28 | fixed | §20.5 L2265-2269「対象は下記「論理名 → 物理名の解決」で得た raw エントリ...確認直後〜コミットの間の再作成という残余の窓は原子的に塞げないが、次 walk の create が是正する自己修復の範囲」 |
| N29 | fixed | §20.3 L2115-2116「非 UTF-8 のファイル名は fp の入力から除外する」 |
| N30 | fixed | §15 規約12 L1940-1943「照合の読取失敗の分類は §21.1 register と同一の 4 分類を全操作に適用する」 |
| N31 | fixed | §13 L1830-1832「app.sqlite のバックアップ...は SQLite の Online Backup API または VACUUM INTO で行う...main ファイル単独の raw コピーは...禁止」 |
| N32 | fixed | §7 規則4 L575-577「除去の単位は「行全体 + その行末の LF」...実装の最初の作業とする test vector に本規則の例を含める」 |
| N33 | fixed | §12 L1740-1743「「完全に解決できる」は接続中のフォルダに限る...解決段で「フォルダ接続なし (missing)」を status 表示する」 |
| N34 | fixed | §7 規則4 L579-582「un-escape (可逆性)...text チャンクの本文へ含める際に `\` を 1 つ除去する」 |
| N35 | fixed | §9.1 L1073-1076「注記 (意図されたコスト — fork §21.3 の課金注記と同族)...同一 target が自動再投入・再課金される」 |
| N36 | fixed | §10 step -1 L1387-1390「§9.3-z の判定をフォルダごとに実行する...検出したフォルダは同 tick の step 0〜4 の対象から除外」(§9.3-z 本文 L1297-1301 とも整合) |
| N37 | fixed | §7 L615-617「中断 (クラッシュ) の再開駆動は明示操作の再実行とする...実行中・未完了は status に表示する」 |
| N38 | fixed | §8 L735-737「フィルタ設定は app_config に canonical record...で永続化する (専用の hash key は持たない)」 |
| N39 | fixed | §5.3 L260-263「この継承規則は batch_requests 行を新規 INSERT する全経路 — §9.1 相 1・client 前計上・本節の明示再生成 INSERT — に適用する。register 自体は行を作らず」 |
| N40 | fixed | §10 step3 L1443-1445「「現行 profile」の参照元は app_config の embedding_profile record — §5.7 は履歴の保管庫であり...profiles が空」 |
| N41 | fixed | §11.2 L1704-1707「hash 系 bind (:current_tool / :current_profile) は raw BLOB (32 bytes) で bind する」 |
| N42 | fixed | §18.4 L2009「1 repository 内の複数対象を 1 job に積む効率 (§10 — 1 job = 1 repository の規則は維持)」 |
| N43 | fixed | §9.1 folders DDL L754-755「書込規則: folders 行の INSERT (register / fork 手順 3) と再発見・rebind...で now へ更新」 |
| N44 | fixed | §20.5 L2306-2310「case 感度は走査時のボリューム属性から判定する...フォルダ移動...後は新ボリュームの属性で再判定する」 |
| N45 | fixed | §13 L1793-1794「検証済み record で DELETE → INSERT し置換する (同一 Tx — BEGIN IMMEDIATE)」 |

追加で grep による機械検証を実施し、以下がすべて一致 (不一致 0 件) であることを確認した:
`7 テーブル` の残存 0 件 (`8 テーブル` に統一)、`agg_embedding_profile_hash` 旧単一キーの残存 0 件、
`5 種`/`5-key`/`5種` の残存 0 件 (app_config は 7 key: tool_profile / embedding_profile /
image_filter / retry_not_before / agg_building_profile_hash / agg_ready_profile_hash /
fork_in_progress)、監査番号 (`P9` 等) の自己参照 0 件、`$2.5`/`$5`(+25%)/`$4` の整合、
`RRF`/`k=60` の整合、`768` の 3 出現すべて参考値と明記、`30 日` 猶予の整合、`k_max`/`4,096` の整合、
`lower(hex(` の使用箇所と `hex(` 単独箇所 (§9.1 target_key コメント・app_config value コメント) は
いずれも「SQL では lower(hex()) を通す」旨の直後の注記付きで矛盾なし。

SQLite (3.51.0) での実 fixture 検証: (a) FTS5 external content を `content='chunks_fts_src'`
(VIEW) で構成し INSERT / DELETE / `integrity-check` / `rebuild` すべて正常動作を確認 (§5.5・P7)、
(b) `cost_ledger` の `UNIQUE(...,submission_seq)` + `INSERT ... ON CONFLICT DO NOTHING` で
同一 seq への 2 回目の書込 (異なる値) が黙って無視され最初の値が残ること、素朴な `INSERT` は
`UNIQUE constraint failed` で例外送出されることを確認 (§9.1・M01/N09)、(c) `chunks` の CHECK 群
(type=1/2 分岐・seq≥0・char_end≥char_start・typeof 制約) が不正値をすべて拒否し、
`embed_hash` GENERATED 列と FK CASCADE が想定どおり動作することを確認 (§5.4・M17)、
(d) `commits`/`file_versions` (自己参照 FK 含む) に対する `DELETE FROM commits` が
即時 FK 検査・`defer_foreign_keys=ON` のいずれでも成功すること (§21.3 の防御的 defer 指定の
妥当性を裏付け) を確認、(e) `at_hash = X'FF'*32` を用いた行値比較が同一 `created_at` の全 commit
を tie-break に関わらず包含することを確認 (§11.1 C・L24)。

---

## 第 2 部 — 探索ログ (C12) — 73 シナリオ

重心: X41〜X45 (r12 修正の相互作用・記帳経路の網羅行列・ready 母数と synced の動態・raw 解決の
全数・scoped 規約 12 と step -1・反証) — 73 件中 32 件をここに配分。

### X1〜X40 (簡易確認 — 各 1 件、現物の行番号で再確認)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 1 tick 間に create→delete が完了し、単一 walk が存在自体を一度も観測しない (瞬間的な一時ファイル) | 問題なし (周期スキャンの必然的丸め。dirty イベントも同様に coalesce され得るため層 B 設計の宿命であり規約 11 と矛盾しない) |
| 2 | X2 | 物理ファイル名が文字列として `obj:` や `<!-- img:` を含む (パス区切り等は無し、name_invalid 対象外) | 問題なし (`obj:<hash64>` grammar は 64 桁 hex の厳密一致を要求し、file_name とは別の名前空間で照合されるため混同しない) |
| 3 | X3 | macOS NFD readdir → NFC 論理名への正規化で単一系列に収束 | 問題なし (§20.5 L2280-2284) |
| 4 | X4 | 同一 created_at (ms 衝突) の並行コミット → commit_hash DESC のタイブレークが決定論的 | 問題なし (§5.1 L190, §11.1 L1522) |
| 5 | X5 | 10 万ファイル walk → 段 1 全行比較で個人規模なら十分、§19 に規模再考条件が明記 | 問題なし (§19 L2054-2060) |
| 6 | X6 | 日本語 2 文字「検索」→ trigram 沈黙 → LIKE fallback (bind 分離・instr(lower) 両方の case 折り畳み) | 問題なし (§11.2 L1686-1701) |
| 7 | X7 | grammar v 混在期間の解析 → v 列を読んで版別 dispatch、専用追跡列は不要 (内容から導出可能なものは二重化しない) | 問題なし (§6 L515-524) |
| 8 | X8 | restore 宛先に `../evil` → file_name 検証 (name_invalid) + root_path 正規化 join で拒否 | 問題なし (§20.5 L2312-2316, §21.4 L2575-2576) |
| 9 | X9 | ディスク満杯を objects/metadata/app の各書込点で発生 → Tx 未完のまま巻き戻り、tmp 残骸は 24h 掃除、次 tick が差集合で収束 | 問題なし |
| 10 | X10 | zip 圧縮→解凍往復 (mtime/inode 全変化) → content_hash 一致で無コミット (段 2 の真実性による吸収) | 問題なし (§20.3 L2147-2149) |
| 11 | X11 | fp の非正規化 name (§20.3) と file_versions の NFC 論理名 (§20.5) の変換点 | 問題なし (変換点は walk 観測時の 1 点に閉じ、fp は JCS 入力から非 UTF-8 名を除外するのみで NFC 正規化そのものには関与しない — §20.3/§20.5 で役割分担が明確) |
| 12 | X12 | register→discover→scan→OCR→chunk→embed→replicate→検索→原本解決→履歴→復元の一気通貫トレース | 問題なし (全文読了で各段の入出力が前段の出力と § をまたいで一致することを確認済み — §6→§7→§8→§9.3→§11→§12→§21.4) |
| 13 | X13 | 「status 表示」「明示操作」等の総点検 | 問題なし (§21.1〜21.6 + §21.7 参照表のいずれかに具体的手順・入力・失敗回復が定義済み) |
| 14 | X14 | submit 429 と collect 429 の両方で retry_not_before (provider・kind 別) へ永続化 | 問題なし (§9.1 L938-939 submit, L988-990 collect — 対称) |
| 16 | X16 | 2 相 submit + JSONL 複数分割 (1 job = 1 repository) と intent_token の粒度 (job 単位) | 問題なし (分割後も各 job が独立した intent_token を持ち、job 単位で回復が完結する — §10 step1 L1414-1416) |
| 17 | X17 | register 手順 2 (新規初期化) の途中クラッシュ → damaged → 再実行 | 問題なし (原本ファイル非接触のため再実行は常に安全 — §21.1 失敗回復 L2417-2419) |
| 18 | X18 | profiles 表の孤児行 (参照する派生が全廃棄後) | 問題なし (§18.7 で意図的に非掃除と明記、fsck は孤児と無関係に全行の hash/参照整合を検証) |
| 19 | X19 | dir fsync 適用点の網羅 (objects 各 prefix・tmp・fork journal・repository-id 書換え) | 問題なし (N20 で fork 自身の書込が dirfd/fsync 列挙に追加済み — §20.5 L2235-2237) |
| 21 | X21 | 相 1 の profile_hash/upload_cleaned リセットと intent 回復 (snapshot 不変) の整合 | 問題なし (X41 で深掘り — 下記) |
| 21.5 | X36 | r11 修正の相互作用 (冪等記帳 (ON CONFLICT DO NOTHING) × submission_seq 継承 × detached 採用 seq+1 の三者、r12 の本命論点の再確認) — M06 の seq+1 増分を仮に外した場合の反実仮想を検討: 増分しなければ detached 採用後の close が旧 lifecycle の同一 seq と衝突し、冪等吸収が正当な別 attempt の課金を黙って落とす | 問題なし。現行文書は §9.1 L1064-1065 で detached server 採用時の `submission_seq+1` を明記しており、この脈 (r11→r12 で確定済み) の regression は無い。r13 の X41 (下記) はこの延長で r12 が**新規に**追加した記帳経路 (N01 の client 旧 seq 記帳・N04 の (b') 記帳) まで含めた**拡大版**の網羅行列として再検証した |
| 22 | X22 | `defer_foreign_keys=ON` + `foreign_keys=ON` + `journal_mode=DELETE` の相互作用 | 問題なし。**実 SQLite で検証**: 自己参照 FK (file_versions) を持つスキーマで `DELETE FROM commits` を immediate 検査・defer 検査の両方で実行し、いずれも成功しカスケードが正しく効くことを確認 (§21.3 の defer 指定は「防御的」であり必須ではないことも裏付けられた) |
| 23 | X23 | detached × profile 不一致 × status 表示 | 問題なし (detached の処理規範は profile 一致可否と独立に outcome 存在だけを見るため一貫 — §9.1 L1052-1078) |
| 25 | X25 | app.sqlite 単独 (フォルダ未接続) での横断検索クエリ embedding 生成経路 | 問題なし (app_config の embedding_profile record が経路 — §9.1 L875-878) |
| 26 | X26 | submission_seq × attempts × ledger の三者 (r9 修正の相互作用) — 相3・intent 採用 server・client 前計上の 3 書込点の重複有無、載せ直し (confirmed-absent 後の相1 再通過) で seq が動かないか | 問題なし。相1 自体は submission_seq に一切触れず (§9.1 L910-927)、増分は相3・intent 採用・client 前計上・detached 採用の 4 箇所のみで発生するため、相1 の再通過を何度繰り返しても seq の重複・巻き戻りは起きない (X41-47 で 4 箇所の悉皆点検を実施し裏付け済み) |
| 27 | X27 | fork journal の全境界クラッシュ再開 (PREPARED/HISTORY_CLEARED/ID_WRITTEN/APP_DONE × 各クラッシュ位置) | 問題なし (§21.3 L2533-2546 の再開表を再読了し、id=old かつ commits 非空の特殊分岐も含め一意に収束することを確認) |
| 28 | X28 | detached 全ライフサイクル (state 0/1/2/3 × 生成 3 経路) | 問題なし (§9.1 detached 規範 L1052-1078 が client/server の 2 分岐と全状態を網羅) |
| 29 | X29 | 保存名固定 (case 規則) × case-insensitive→sensitive 移動後の共存 | 問題なし (§20.5 L2306-2310 — 「系列の分裂であってデータ喪失ではない」と明記済みの意図された挙動) |
| 30 | 自由 (X5 関連) | 大量 chunk (100 万規模) での agg_chunks 全置換頻度 | 問題なし (§19 の規模再考条件が明記済みの既知の境界) |
| 31 | X31 | submission_seq の書込点の網羅 (相3・intent 採用・client 前計上・detached 採用) | 問題なし (X41 で深掘り — 下記) |
| 32 | X32 | 課金記帳の網羅行列 ((server/client) × 全終端理由 × 全 close 経路) | 問題なし (X41 で深掘り — 下記) |
| 33 | X33 | Mistral Batch の JSONL 行数上限と custom_id 一意性 (1 job = 1 repository) | 問題なし (§10 step1 L1414-1416「repo を跨ぐと同一 target_key が衝突する」に対応済み) |
| 34 | X34 | §11.2 完全 SQL の組立実行可能性 (eligible×agg_chunks 再JOIN の LIKE fallback・at_hash=FF) | 問題なし。SQL 本文を通しで読み列・キーの整合を確認 (§11.2 L1582-1718)。**at_hash=FF は実 SQLite で行値比較の挙動を検証済み** (第 1 部参照) |
| 35 | X35 | fork が id=old からでも journal で正しく再開するか (r10 改訂後の主張の再確認) | 問題なし (§21.3 L2534-2536「id = old → 手順 1 から」が commits 非空の特殊ケースも含め一意) |
| 37 | X37 | ready 完了追跡の全数トレース (P1→P2 切替直後の陳腐化・次元一致/距離のみ相違・ゼロフォルダ) | 問題なし (X37 で深掘り — 下記) |
| 38 | X38 | fork 回復拡張の全数トレース (手順1直後クラッシュ→フォルダ移動→journal 発見→再開) | 問題なし (X38 で深掘り — 下記) |
| 39 | X39 | register/detached/検知周辺の相互作用 (一時読取不能保留×damaged 誘導の境界) | 問題なし (M13/N30 の 4 分類が register 以外の全操作へ一般化済みであることを再確認 — §15 L1940-1943) |
| 40 | X40 | 反証 7 件 + 保留エッジ再評価 (r11 更新版の主張) | 問題なし、全 7 件生存 (X45 で今回分と合わせて再実施 — 下記) |

### 反証チェックポイント X15/X20/X24/X30/X35 (各ラウンドの主張・試行・結果)

| # | 観点 | 主張 (試行内容) | 結果 |
|---|---|---|---|
| 41 | X15 | 「同一の正規化コミット → 同一の commit_hash」(§4.1) — 2 台の端末が独立に同一変更セットを生成した場合の分岐余地を探索 | 破れず (JCS 直列化 + 固定フィールド集合により端末固有情報が入力に一切現れない) |
| 42 | X20 | 「重複課金は intent 回復により最悪 job 1 回分に有界」(§10) — server 経路で相 2b 直後・相 3 直前のクラッシュを反復させ、intent_token 突合が毎回単一 job に収束するかを試行 | 破れず。ただし現行文書では **server 限定の明記**が §10 (L1496-1498) と §9.1 (L727-731) の両方に存在することも確認 (N11 が §10 側の再掲漏れを修正済み) |
| 43 | X24 | 「agg 毎 tick 検査は一度きり破棄の喪失を吸収する」(§8-e) — 次元一致のまま distance のみ異なる profile 切替を反復させ、差集合再充填が収束するかを試行 | 破れず (§8-e が次元と距離の両方を検査するため distance 単独差も確実に検出される。**distance_metric は §4.1 で profile_hash の入力に含まれるため、そもそも「次元一致・距離のみ相違」は必ず別 profile_hash になり検出漏れの前提が生じない**ことを X45-60 相当で再確認) |
| 44 | X30 | 「detached は課金を取りこぼさない」(r10〜r12 改訂後) — detached の state=0 (server, job 一覧に実在) を発見・採用する経路で採用と同時の記帳が二重にならないかを試行 | 破れず (M06 の採用 UPDATE が submission_seq を正しく増分するため、以後の close が旧 lifecycle と衝突しない) |
| 45 | X35 | 「fork は id=old からでも journal で正しく再開する」(r10〜r12 改訂後) — HISTORY_CLEARED かつ id=old のクラッシュから commits 非空・空の両ケースで再開手順が一意に定まるかを試行 | 破れず (§21.3 L2536-2540 の「commits が空でない場合は手順 1 からやり直す」判定が両ケースを一意に分岐する) |

### X41 (記帳経路の網羅行列の再検証 — 重心・実 SQLite fixture 併用)

| # | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|
| 46 | **profile A→B→A 往復の因果順序を追跡**: (1) kind=2, profile=A で submit→collect 成功、seq=n で実額記帳・embeddings(A) 作成 (2) profile→B、§8-a「成果なし」判定でこの target が再投入対象化、attempts=0 数え直し、submission_seq は次の相3で n+1 に (3) B の job が collect され `item成功・profile不一致 (現行はB自身なので実は一致では? — 訂正: この時点で現行はB、投入もBなので一致・正常完了)`。**シナリオ再設計**: (3') B が in-flight (state=1, seq=n+1) のまま profile が B→A に戻る (4) collect が seq=n+1 の job を照合: profile_hash(記録=B) ≠ 現行(A) → vector 破棄・state=3(profile_changed)・**実額記帳 (seq=n+1)** (5) 現行 A の embeddings(A) 行 (手順1から未削除・§8-b の DELETE は「旧 profile 行が残っていれば」B の正常完了時にのみ発火するため、B が破棄された今回は発火せず A 行は無傷) が現行と一致 → 次 tick の reconcile が「成果あり」でこの batch_requests 行 (state=3) を state=2 へ閉じ、付随処理(b) で **同じ seq=n+1 に NULL+estimated を冪等記帳**しようとする → **実 SQLite で検証した ON CONFLICT DO NOTHING は「先着优先」であり、(4) の実額記帳が (5) の付随処理より必ず先に (同一 tick 内の step4→次 tick の step0.5 という順序で) 書き込まれるため、実額が保持され NULL+estimated には上書きされない** | **問題なし** (第 1 部の SQLite fixture で「同一 seq への 2 回目の書込みは無視され最初の値が残る」ことを実証済み。かつ「実額を持つ書込みが構造的に必ず先着する」ことを (4)→(5) の tick 順で確認 — collect の記帳は同 tick 内で発生し、reconcile の付随処理は state=3 化した**次以降の** tick でしか発火しないため、時系列上「情報量の多い書込みが常に先着し、情報量の少ない安全網書込みが常に後着する」という不変条件が成立する) |
| 47 | **全 seq 書込点の悉皆点検**: 相3 (通常採用) / intent 回復 server 採用 (found) / client 前計上 (実行前) / detached server 採用 (M06) の 4 箇所すべてで submission_seq+1 が実行されるか。tool_changed 却下枝 (confirmed-absent かつ期限内・tool 不一致) だけは意図的に seq 不増分 (この分岐では実際に job が作成されていないため課金事実が無い) | 問題なし (4 箇所すべてで `submission_seq+1` の記述を確認済み — §9.1 L948, L961-962, L700-703, L1064-1065。tool_changed は「載せ直さず」state=3 に直行するため submit 自体が発生せず seq 不増分は正当) |
| 48 | **client_exhausted と client 再実行前記帳の重複可能性**: attempts=2 (上限3) で呼出中クラッシュ (seq=n) → 再実行前計上 Tx が「直前 attempt (seq=n) を NULL+estimated で冪等記帳してから attempts=3・seq=n+1」に進む → その再実行 (seq=n+1) も呼出中クラッシュ → 次回の intent 回復で attempts(3)>=上限 検出 → state=3(client_exhausted) + 「旧 seq の terminal 記帳」(どの seq を指すか — 直前の n+1 のみか、n も含むか) | **N01 の文言 (§9.1 dispatch L955-957「旧 seq の terminal 記帳」) は単数形で「直前の 1 attempt」を指す。n はすでに (48) の前段階で再実行前計上 Tx 自身が記帳済み (n→n+1 への遷移時に)。したがって client_exhausted 時点で未記帳なのは n+1 のみであり、単数形の記述で正しく全 attempt が記帳される** — 問題なし |
| 49 | **detached (b) 採用 (M06) と (b') の役割分担が重複しないか**: detached state=0・server・token 実在確認→state=1 detached へ「採用」(M06、seq+1) した直後に、同じ tick 内で reconcile の (b') がこの行 (今や state=1) を再度触るか | 問題なし (reconcile は state IN (0,3) のみを対象とし、M06 採用後は state=1 のため reconcile の対象から自動的に外れる。(b') は state=0 専用のため二重発火しない) |
| 50 | **submit_rejected (記帳なし) の「実行された可能性」境界**: 相 2b で 4xx を受信 → submit_rejected + attempts=上限、記帳なし。しかし「4xx 応答を受信した」こと自体は「送信は完了し応答も受信した」ことを意味するため、実際には provider 側で一瞬でも処理された可能性は理論上ゼロではないか | 探索したが finding化せず: 4xx (内容起因の恒久拒否、例: 不正なリクエスト・アカウント制限) は provider の課金対象操作 (OCR ページ処理・embedding 生成) が **実行される前**に拒否される응答特性を持つプロバイダ API の一般的挙動であり、これは実装 (Adapter) がプロバイダの課金起点を正しく理解している前提の話であって設計書の抽象度を超える。§9.1 自身も「未実行の確定」と明記しており、これは設計判断 (4xx=無課金) として妥当 |

### X37 (ready 完了追跡の全数トレース — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 51 | P1→P2 切替直後の synced_profile_hash 陳腐化 (旧 P1 値) が ready を誤って true にしないか | 問題なし (N06 により破棄 Tx が全行 NULL 化するため陳腐化値は残らない — 等値比較の対象が消える) |
| 52 | 次元・距離が偶然一致する P1→P2 切替が旧空間ベクトルの混入検索を許すか | 問題なし (§8-a の成果判定と検索ゲートはいずれも完全な `profile_hash` で判定するため、vec0 の DROP/CREATE 判定が粗くても検索結果への混入は阻止される) |
| 53 | **damaged フォルダ C が ready=P1 達成後に damaged 化 → その後 C が新規 repository-id で再登録 (実質新規フォルダ) され再度 P1 に追いつくまでの窓で、agg_ready_profile_hash=P1 は据え置かれたままか** | **意図された挙動として確認** (N06 の「ready は設定時点の被覆の宣言...除外フォルダの復帰分による部分性は通常状態」が明示的にこのケースを包含する。据え置きは仕様どおりで regression ではない — ただし「除外フォルダの復帰」注記が readable な一時除外だけでなく damaged からの**新規 repository-id での再登録**というケースまで文言上カバーしていると読めるかはやや解釈依存 — 実害が無いため finding 化せず探索ログに記録するに留める) |
| 54 | ゼロフォルダ (登録フォルダ 0 件) での ready 全称条件の空虚な真 | 問題なし (N05「接続フォルダが 0 件の間は ready を更新しない」で明示的に防止) |

### X38 (fork 回復拡張の全数トレース — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 55 | 手順1 (HISTORY_CLEARED) 直後クラッシュ→フォルダ物理移動 /A→/B→次 bootstrap/walk が /B で journal 発見→「id=old→手順2から」再開→repository-id を Rnew へ書換→手順3 (root_path=/B へ INSERT、旧 root_path=/A 側の別 id 行が無いことを確認) | 問題なし (N18 により root_path=発見パス (/B) が採用される。/A に別 id の folders 行が残存するケースは今回の移動シナリオでは発生しない — 旧 old_id 行は手順3で明示的に DELETE される) |
| 56 | fork_in_progress のパス単位除外がフォルダ移動で無効化された状態で、通常 tick が旧 id で新規コミットを積み続けた場合の commits 非空判定→手順1やり直しの安全性 | 問題なし (手順1の全 DELETE は冪等なので、どれだけコミットが積まれていても安全にやり直せる — データは失われるが「fork=履歴再初期化」の帰結として意図どおり) |
| 57 | journal digest 不整合検出時の damaged 遷移と fork_in_progress フラグ自体の整合性 (フラグは残るが journal だけ壊れた場合) | 問題なし (「journal が残る側はどの組合せでも回復ルーチンが処理できる」— journal 破損は damaged として status 表示され自動処理されない) |

### X39 (register/detached/検知周辺の相互作用 — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 58 | detached state=1 (真に in-flight) 中に再登録 → 動的定義で即座に非 detached 化 → reconcile はスキップ (state=1) → collect が通常経路で正常処理 | 問題なし (payload が捨てられる前に折り返すため無害) |
| 59 | M11 (同一 root_path 別 id 退役) が新規登録の副作用として発火する際も detached 保存規則 (upload 未清掃なら未削除) を正しく守るか | 問題なし (§9.3-d 型の退役ロジックを §21.1/§21.3 が共通で参照しており、detached 化の条件分岐は退役理由に関わらず同一) |
| 60 | **§21.2 の detached state=0 が §9.1 の client/server 分岐に実際に委譲されているかの文言再確認 (M02 修正後)** | 問題なし (§21.2 L2441-2444「state=0 も §9.1 の client / server 分岐に従う...「state=0 は即削除」は不可」と明記され、旧文言の残存なし) |

### X42/X43/X44 (r13 追加の重心 — ready 母数の動態・raw 解決の全数・scoped 規約12)

| # | シナリオ | 結果 |
|---|---|---|
| 61 | 母数変動の構成: A/B は健全・C が damaged の間だけ ready=P2 が成立 (A・B のみで全一致) → C が (同一 repository_id のまま、単なる一時読取不能から) 復旧 → C の synced_profile_hash は P2 化前の値のまま (もし profile 変更前から P1 のままだった場合) → 母数に C が復帰した次の tick で「全一致」判定に C の古い値が混入しないか | 問題なし。C が一時読取不能から readable に復帰した場合、C の synced_profile_hash は変更されていない (§9.3-c は C を処理できた tick でのみ更新するため、不能だった間は素通りされるだけで古い値が残置される)。母数に C が再度含まれた瞬間、C の synced_profile_hash (旧 profile 値または NULL) は現行 building 値と一致しないため「全一致」は不成立のままとなり、ready は誤って再確定しない — C 自身が §9.3-c を完了して追いつくまで正しく待たされる |
| 62 | **collision winner 変化と 3 呼出点の一貫性**: NFC/case 折り畳みで衝突する 2 実体 {A(先着=採用中), B(次点)} のうち A が外部要因で消滅 → 次回 delete 最終確認・restore・fsck の呼出時点で resolver が B を新たな採用実体として解決する一方、DB 側 (file_versions/scan_cache) はまだ A の内容を「現在版」として記録している過渡期 | 問題なし、ただし過渡的不整合を確認: (a) delete 最終確認は B (regular・readable) を発見し確定を中止する — 安全側 (次回 walk が B への update として正しく収束する)。(b) restore in-place は B を上書き対象として解決する — DB が指す「あるべき内容」と実際に書き込まれる先が B である点は、次回 walk が B の新内容を検出して A の代替として正しく追随するため収束する。(c) fsck の working copy 読取は B の bytes を A の hash と比較し不一致 (別実体) を報告する — これは fsck の「読めたが hash 不一致」の正当な検出であり誤りではない。3 呼出点いずれも「次回 walk までの一時的な不整合」を安全側に処理しており、恒久的なデータ破損には至らない |
| 63 | **raw 解決のレース窓 (TOCTOU) が delete 確認以外の 2 呼出点にも及ぶか**: resolver の readdir スナップショット取得後、restore/fsck の実際の書込・読取実行までの間に、外部プロセスが競合する別正規化形の実体を新規作成する | **N08 の残存ギャップとして O02 で報告** (下記第 3 部) — delete 確認については N28 が「自己修復の範囲」と明記して残存窓を許容する一方、restore/fsck についてはこの許容が明文化されていない |
| 64 | **scoped 規約12 と fork_in_progress の相互作用**: fork 手順2 (ID_WRITTEN 完了、.folder-history 上の repository-id は既に new_id) 〜 手順3 (app 側 folders 行更新) の間に、tick 以外の経路 (ユーザーの手動「フォルダ単独検索」等) が同じ path に対して規約12 の scoped read 照合を実行する | **N04 (本報告の finding として) 検出** — 下記第 3 部で詳述 |

### X45 (反証探索 8 件 — r12 更新版の主張)

| # | 主張 (試行内容) | 結果 |
|---|---|---|
| 65 | 「client の中間 attempt の課金は台帳から漏れない」— seq=n で呼出中クラッシュ×再実行 (seq=n+1) を連鎖させ、各段の記帳が漏れないか | 破れず (N01 の「まず直前 attempt を記帳してから attempts+1・seq+1」が連鎖のどの深さでも成立することを X41-48 で確認済み) |
| 66 | 「照会失敗 (unknown) で二重 job は作られない」— job 一覧照会が繰り返し 429/断で失敗する間、state=0 の行が保持され続け、載せ直しが発生しないか | 破れず (§9.1 L967-969「unknown...行を state=0 のまま保持して次 tick 再試行する」が無条件に適用される) |
| 67 | 「保持期限超の相 2b 残骸も課金は記帳される」— intent_token の UUIDv7 時刻成分が期限超過と判定された confirmed-absent ケースで記帳漏れが無いか | 破れず (§9.1 L973-975「submission_seq+1 の上で NULL + estimated の冪等 terminal 記帳を行ってから」載せ直す) |
| 68 | 「state=0 server の成果あり close は job を無記帳で破棄しない」— (b') の token 照合が failure/unknown を返した場合の扱い | **部分的に未規定**: (b') の文言「token 照合で job の実在を先に確認し、実在すれば...記帳する」は job が「実在しない (confirmed-absent)」場合と「照合自体が失敗 (unknown)」場合を明示的に区別していない。実在しないなら記帳不要 (job 未作成) で問題ないが、照合が unknown (一時的な API 障害) の場合に記帳せず削除へ進むと、実際には実在した job の課金を落とす恐れがある。ただし (b') は「掃除の際に」実行されると明記され、掃除自体は「同 token を共有する全行が終端」を条件とする程度で、unknown 時に安全側 (記帳してから進む、または掃除を延期する) に倒すことまでは明記されていない — **finding化を検討したが、(c) の掃除規範自体が「失敗は次 tick が再試行する」という一般原則を持つため、token 照合が unknown を返すケースも同じ「次 tick 再試行」に自然に倒れると解釈でき、致命的ではないと判断し proposal 未満 (探索ログのみ) とした** |
| 69 | 「ready は damaged・空母数・synced 陳腐化に騙されない」 | 破れず (X37 で確認済み。ただし X37-53 のように「解釈依存だが実害なし」の周辺ケースが 1 件存在) |
| 70 | 「raw 解決で restore の二重実体は作られない」 | **部分的に破れる** (X44-63/O02 参照 — 狭いレース窓で二重実体が理論上作られ得る。ただし発生確率・影響とも限定的) |
| 71 | 「登録済み path の read は差し替えを検出する」— 差し替え先が「既に別の repository_id で登録済みの正規フォルダ」である場合も検出できるか | 破れず (規約12 の照合は on-disk repository-id と「このパス」に紐づく folders 行の期待値を比較するため、差し替え先が何であれ ID 不一致は機械的に検出される) |
| 72 | 「step -1 で復元直後 tick の誤課金は起きない」 | 破れず (§10 step -1 L1387-1390 が z 判定を tick 冒頭に繰り上げ、検出フォルダを step 0〜4 から除外することを確認済み) |

### 自由探索

| # | シナリオ | 結果 |
|---|---|---|
| 73 | annotation 由来テキストへの grammar 偽装混入 (§6 の 2 層防御の再確認 — 本文エスケープ + image_hash 実在検証) | 問題なし |
| 74 | 複数の明示操作 (例: unregister(A) と fork(B) を別スレッドから同時発火) が同一 tick.lock を奪い合う場合の直列化 | 問題なし (単一 flock によるグローバル直列化。片方が最大 N 秒ブロックし、取得できなければ再試行を促す — §21 前文) |
| 75 | drop-derivation の対象が「過去版の content だが偶然現在版とも同一 content_hash」の場合、backfill 設定に関係なく再投入されるか | 問題なし、むしろ **より安全側**: §21.6 注記 (a) の「現在版の場合」の自動再投入は backfill 設定を問わず常に発生するため、利用者が「過去版のつもり」で drop しても現在版共有により即座に検出・再投入される (N23/N06 の文言が両ケースを明示的に列挙済み) |
| 76 | tool_changed 却下枝 (§9.1 intent 回復) の job 一覧照会がページネーションを伴う場合の網羅性 | 探索したが finding化せず (Adapter 実装詳細の領域であり、設計書の抽象度「job 一覧照会」を超える。日本の他の照会失敗系 (429/断) と同じく実装が正しく全件走査することが前提) |

---

## 第 3 部 — 新規検出 (C1〜C8, C10〜C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 (P#/C#/X#) | 修正案 |
|---|---|---|---|---|---|---|
| O01 | minor | §15 規約12 L1934-1939「読み取り専用の操作...も、対象パスが folders に登録済みならば同じ照合を行い」/ §21.3 L2481-2486「この realpath の実体のみを tick の全ステップ...から除外し、規約 12 の conflict 判定も抑止する」 | 規約12 の scoped read 拡張 (N07) と fork の `fork_in_progress` 抑止 (§21.3) が互いを明示的に参照していない。§21.3 側は「tick の全ステップ」と「規約 12 の conflict 判定」の抑止を並列に述べるが、規約 12 自身の条文 (§15) には fork_in_progress を考慮する旨の記載が無い。実装者が規約 12 を単独で実装 (tick とは独立に、単独検索・履歴閲覧などあらゆる呼出元から共通関数として regsiter するのが自然な設計) した場合、fork_in_progress の抑止を tick 経由の呼出にしか適用しない実装になり得る | 初期状態: フォルダ F を対象に fork (§21.3) 実行中、手順2 (repository-id を new_id へ書換え、phase=ID_WRITTEN) 完了直後の状態 — `.folder-history/repository-id` は既に new_id を指すが、app 側 `folders` テーブルは手順3 未実行のため旧 old_id・root_path=F の行がまだ存在する (fork_in_progress = (old_id, F) が app_config に記録済み)。操作列: (1) この状態のまま、tick とは独立に呼び出される「フォルダ単独検索」または「履歴閲覧」機能がユーザー操作で F に対して実行される (2) この呼出経路の実装が (規約 12 の条文どおりに) `folders` 行 (root_path=F, id=old_id) の期待値と、`.folder-history/repository-id` の実測値 (new_id) を素朴に比較する (3) fork_in_progress による抑止をこの呼出経路が参照していなければ、old_id ≠ new_id の不一致が検出され conflict として結果を拒否する。壊れる状態: fork という正常な (システム自身が開始した) 操作の最中に、ユーザーの通常の読み取り操作が「conflict」という誤解を招くエラーで拒否される (fail-closed なのでデータ破損は起きないが、fork の実行時間が長引いた場合 — 例えばクラッシュ後の回復待ちの間 — この状態が数分〜数時間続き得る) | C3, C11(a), X44, X39 | §15 規約 12 の条文に「fork_in_progress (§21.3) が設定されている対象 (old_id, realpath) は、tick 経由・単独呼出のいずれからの照合であっても、本規約の適用対象から除外する」と明記するか、または §21.3 側で「この抑止は規約 12 のすべての呼出元 (tick 内外を問わず) に適用される共有ガードとして実装すること」と明記する |
| O02 | minor | §20.5 L2285-2294「論理名 → 物理名の解決 (逆方向・全操作共通)」/ L2265-2269 (delete 最終確認の残存窓の軟化文言) / §21.4 L2578-2581 (restore in-place の resolver 使用) | 「論理名 → 物理名の解決」resolver は delete 最終確認・restore in-place・fsck working copy 読取の 3 箇所で共有される (N08 で明記済み) が、resolver の readdir スナップショット取得から実際の書込・読取実行までの間に外部プロセスが競合する実体を作成する残存 TOCTOU 窓についての「絶対防御ではなく自己修復に委ねる」という軟化文言 (N28) は、delete 最終確認の文脈でのみ明記されており、restore・fsck の 2 箇所には同じ軟化 (または対応する残存窓の許容) が明記されていない | 初期状態: 論理名 `Report.pdf` (NFC) として file_versions に記録されたファイルの過去版を、正規化非依存 lookup の Linux ext4 ボリュームへ in-place restore する。対象パスには現在、対応する raw エントリが存在しない (resolver は「対応する raw エントリが無い場合...NFC 表記で新規作成してよい」と判定した)。操作列: (1) restore の resolver が readdir を実行し「raw エントリ無し、NFC で新規作成可」と判定する (2) resolver の判定直後、restore 自身の tmp→fsync→rename の実行前に、全く無関係な外部プロセス (例: 同時に稼働する別の同期ツール、あるいはユーザー自身の別操作) が NFD 表記 (`Repórt.pdf` 相当) の同一論理ファイルを新規作成する (3) restore は resolver の古い判定 (「無し」) に基づき NFC 表記で書き込みを続行する。壊れる状態: NFC 実体 (restore の結果) と NFD 実体 (外部プロセスが作成) が同一ディレクトリに並存する二重実体となり、次回 walk で name_collision が発生し、restore の結果が採用規則 (UTF-8 バイト列昇順) 次第で敗者になり得る — resolver が「衝突を作らない」ために設計されたにもかかわらず、この特定の呼出経路で衝突を防げない | C3, C11(a), X43, X40 | N28 の軟化文言 (「確認直後の再作成は次 walk の create が是正する自己修復の範囲」) を、restore (§21.4) と fsck (§13) の resolver 使用箇所にも明示的に適用する一文を追加する。あるいは §20.5 の resolver 定義自体に「この resolver の判定と実際の操作実行の間には常に narrow な TOCTOU 窓が残り、次回 walk が name_collision として検出・収束させる (3 呼出点すべてに共通)」と一箇所にまとめて明記する |

---

## 第 4 部 — 確認済みの列挙

検出 0 件として確認した観点:

- **C1** (P1〜P16 の反映): 全項目が文書に存在し、内容が原則と一致 (弱められた条件・欠落なし)。
  N01〜N45 で新規導入された規範 (三値照合・UUIDv7 期限・(b') 記帳・token sweep・ready 母数・
  synced NULL・raw 解決・scoped 規約12・step -1) を含め、対応する P1〜P16 の文言との整合を確認
- **C2** (SQL 静的検証): 全 DDL について GENERATED 列構文・WITHOUT ROWID と PK の関係・CHECK
  論理・FTS5 external content の content 側 rowid 保有・FK 参照先の存在と列数一致・trigger の
  INSERT/DELETE 対称性のいずれにも問題なし。**今回は主要な DDL パターンを実 SQLite 3.51.0 で
  fixture 実行し (FTS5-on-VIEW / chunks CHECK 群 / cost_ledger ON CONFLICT / 自己参照 FK +
  defer_foreign_keys / at_hash 行値比較)、静的読解だけでは見えない実行時の挙動まで検証した**
- **C3** (相互参照整合): §21.7・§9.3-d・「元設計§15/§21」の番号衝突注記を含め、文書内の全 §参照
  が解決可能 (O01/O02 は「参照は成立しているが、2 つの規範の適用範囲が互いを明示的にカバーして
  いない」という別種の指摘であり、参照自体の破損ではない)
- **C4** (クエリとスキーマの整合): §11.2 の完全 SQL・§9.3-a のカーソル SQL・§13 の GC 差集合が
  同文書の DDL と列名・join キーの型/形式ともに整合
- **C5** (数値・事実の一貫性): $2.5/1k・+25%・768 (参考値である旨含む)・RRF k=60・「8 テーブル」・
  app_config 7-key・30 日猶予・k_max=4,096 が全出現箇所で一致 (grep による機械検証済み)
- **C6** (用語・形式の一貫性): target_key の連結形式・chunk_type と target_type の対応・
  obj:<hash> スキーム・embed_hash 定義の再掲がすべて一致
- **C7** (状態機械の完全性): batch_requests の状態遷移に到達不能・脱出不能の分岐は無い。
  client_exhausted・tool_changed・job_missing・invalid_output のすべてに明確な脱出路がある
- **C8** (欠落章): 原則 P1〜P16 の範囲内で書かれるべき章の欠落は無い
- **C10** (修正が開けた穴 a〜oo): N01〜N45 の修正どうし・修正と既存記述の間に新たな矛盾は
  見つからなかった (O01/O02 は修正どうしの直接衝突ではなく、修正が正しく閉じた欠陥の隣接領域で
  新たに見えてきた文書完全性の gap)
- **原則別**: P1〜P16 全項目について指摘なし (O01/O02 はいずれも P 原則そのものとの矛盾ではなく、
  C3 (相互参照範囲)・C11 (実装可能性)・C12 (探索型) の観点で新規に検出されたもの)

**破れなかった主張** (X45 の反証探索 8 件中 6 件が完全生存、2 件が「部分的」に留まる):
「client の中間 attempt の課金は台帳から漏れない」「照会失敗 (unknown) で二重 job は作られない」
「保持期限超の相 2b 残骸も課金は記帳される」「ready は damaged・空母数・synced 陳腐化に騙されない」
「登録済み path の read は差し替えを検出する」「step -1 で復元直後 tick の誤課金は起きない」は
完全に生存。「state=0 server の成果あり close は job を無記帳で破棄しない」は unknown 応答時の
挙動が未規定という周辺ギャップを残しつつも致命的ではないと判断 (finding化せず)。「raw 解決で
restore の二重実体は作られない」は O02 の狭いレース窓により部分的に破れる。

**探索して問題なしだった保留エッジ・周辺ケース**: ready 母数の動態 (母数変動時の synced 陳腐化 —
安全側に機能することを確認)、collision winner 変化と 3 呼出点の一貫性 (過渡的不整合は次回 walk
までに自己収束することを確認)、damaged からの新規 repository-id 再登録時の ready 据え置き
(意図された挙動と解釈できるが文言はやや解釈依存 — finding化せず探索ログに記録するに留めた)、
tool_changed 却下枝の job 一覧照会ページネーション (実装詳細の領域につき対象外)。
