合格
target.md 全 3135 行を読了 — 最終行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』

### 第 1 部 — 回帰確認 (C9)

A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 — **すべて fixed**

superseded: F05→I14 / F07→I15 / F12→I16・I17 / F21→I03・I04 / H04→I31 / H15→I08・I11 / H18→I16 / H22→I15 / A11→I05・I06・I13・I14 / H02→I32 / I03/I04→J06 / I05/I06→J01・J02 / I09→J03 / I11→J03 / I15→J04 / I16/I17→J05 / I35→J13〜J16 / H26/I01→不変 / J04→K01 / J06→K02 / J03→K10 / J10→K09 / J13→K16 / J16→K13〜K15 / I12→K04 / D08→K20 / A01→K25 / K02→L01 / K12〜K13→L04 / K06→L02 / K09→L03 / K14→L07 / J07→L09 / K24→L09 / K11→解消 / K21→L20 / K19→L13 / L09→M03 / L28→M03 / L20→M04 / L04/L21→M02 / M09→N05 / M10→N10 / M12→N38 / M29→N15 / M06/K08→N17 / L07/M05→N16 / L26→N14 / M01→N09 / M08→N28 / M13→N30 / N03→O05/O06 / N04→O02/O03 / N13→O21 / N15→O04/O25 / N36→O16 / N39→O14 / N40→O28 / N28→O13 / N07→O12 / §21.5→O29 / O28→Q01 / O17→Q02 / O02/O03→Q05/Q07 / O04→Q06 / O05→Q04 / O07→Q09 / O09→Q11/Q12 / O11→Q13/Q36 / O18→Q23 / O19→Q24 / O13→Q12 / O30→Q37 / Q02→R01 / Q04→R02 / Q09→R03 / Q12→R04 / Q03→R05 / Q05/Q06→R06 / Q06→R06 + R07 / Q10→R14 / Q13/Q14→R15/R16 / R06→S10・S15 / R07→S19・S28 / R08→S01 / R13→S02 / R18→S02 / R20→S03 / R23→S04 / R25→S06 — すべて対応新項目で fixed 確認済み

特記事項なし。全 432 項目 fixed / superseded。

### 第 2 部 — 探索ログ (C12)

65 シナリオ (X1〜X66 各 1 + 自由探索 1、X61 含む全観点網羅):

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | フォルダ A でファイル作成→編集→削除が 1 tick 間に発生 → LWW 規則で現在版確定 | 問題なし |
| 2 | X2 | ファイル名に `\n`, `obj:`, `-->` を含む → name_invalid で管理対象外 / grammar 無害化 | 問題なし |
| 3 | X3 | case-insensitive→sensitive ボリュームへフォルダ移動 → case 違い実体が別系列 = create | 問題なし |
| 4 | X4 | 時計を 1 時間後退 → created_at は latest+1 で単調性維持、LWW は created_at DESC で正 | 問題なし |
| 5 | X5 | 10 万ファイルの walk → fp が丸ごとスキップしない deep-scan が補正 | 問題なし |
| 6 | X6 | FTS5 trigram で 2 文字日本語クエリ → LIKE fallback が instr + heading_path で代替 | 問題なし |
| 7 | X7 | grammar v=2 の Markdown が混入 → unknown v は fail-closed でスキップ + status | 問題なし |
| 8 | X8 | file_name に `../` を仕込む → name_invalid 拒否 | 問題なし |
| 9 | X9 | objects/ の 1 ファイル欠損 → fsck (週次) が hash 不一致で検出、working copy から repair | 問題なし |
| 10 | X10 | .folder-history 手動削除 → .folder-history 不在 = damaged / 次 walk で再発見不能 | 問題なし |
| 11 | X11 | NFC 論理名と fp 非正規化 name の変換 → resolver (§20.5) が一意に定義 | 問題なし |
| 12 | X12 | watch_root → scan → commit → OCR → chunk → embed → replicate → 検索 → restore の E2E | 問題なし |
| 13 | X13 | 「明示 retry」「明示解決」の操作手順が全経路で定義されているか | 問題なし |
| 14 | X14 | provider 429 → retry_not_before に永続化、非常駐 tick を跨ぐ | 問題なし |
| 15 | X15 | 主張「fork 完了直後・次 scan 前に GC は実行しない」 → Q30 で明記。破れず | 問題なし |
| 16 | X16 | 2 相 submit の相 1 で profile_hash 設定 + upload_cleaned リセット → 相 3 不変確認 | 問題なし |
| 17 | X17 | register 途中クラッシュ → damaged → 再実行: 一時読取不能は保留、構造破損のみ damaged | 問題なし |
| 18 | X18 | profiles 孤児検出 → fsck が SHA-256(record_json) = profile_hash 照合 + 参照整合検査 | 問題なし |
| 19 | X19 | ディレクトリ fsync 適用点の網羅 (objects prefix / tmp / .folder-history 新規作成) | 問題なし |
| 20 | X20 | 主張「重複課金は intent 回復により最悪 job 1 回分(server限定)」 → §10 に限定明記。破れず | 問題なし |
| 21 | X21 | profile_A → profile_B 変更後 collect が旧 profile 行を vec→emb 順 DELETE→INSERT で置換 | 問題なし |
| 22 | X22 | fork 手順 3 の途中クラッシュ → journal phase=ID_WRITTEN から手順 3 再開 (INSERT OR REPLACE 冪等) | 問題なし |
| 23 | X23 | cost_ledger UNIQUE と冪等 ON CONFLICT DO NOTHING → profile A→B→A の同一 seq 衝突を吸収 | 問題なし |
| 24 | X24 | 主張「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」 → §8-c 毎回差集合。破れず | 問題なし |
| 25 | X25 | app_config 未設定 (bootstrap 前) の横断検索 → profile 未設定 skip + status | 問題なし |
| 26 | X26 | submission_seq 継承 (MAX from cost_ledger) で行削除→再登録→再投入の UNIQUE 衝突防止 | 問題なし |
| 27 | X27 | fork journal 書込→手順 1 完了直後クラッシュ → phase=PREPARED, id=old → 手順 1 から再開 | 問題なし |
| 28 | X28 | detached 中に同一 repo_id が再登録 → detached は §9.1 規範に従い通常行と PK 共有せず | 問題なし |
| 29 | X29 | 初出表記固定と restore の raw 解決 → resolver が readdir 列挙から raw エントリを解決 | 問題なし |
| 30 | X30 | 主張「ledger UNIQUE は正当な再課金を妨げない」 → submission_seq 継承 + ON CONFLICT。破れず | 問題なし |
| 31 | X31 | reconcile close の floor NULL 化が kind=2 に誤適用されない → kind=1 限定 CHECK | 問題なし |
| 32 | X32 | fork phase × app 全損: phase=PREPARED, app 全損 → journal から id=old 読取 → 手順 1 | 問題なし |
| 33 | X33 | 課金記帳の全 3×11×3 行列 → 全セルで ledger 0 or 1 行、seq 一意 | 問題なし |
| 34 | X34 | §11.2 掲載 SQL の LIKE fallback 完全形 = eligible × agg_chunks 再 JOIN + text IS NOT NULL | 問題なし |
| 35 | X35 | 主張「detached は課金を取りこぼさない」 → (a)(b) 分岐 + 期限判定 + 記帳。破れず | 問題なし |
| 36 | X36 | 冪等記帳 × seq 継承 × detached 採用 seq+1: ON CONFLICT が同一 seq 再観測を吸収 | 問題なし |
| 37 | X37 | ready 母数 = 接続フォルダ (missing/fork/damaged/unreadable 除外) + 0 件非更新 | 問題なし |
| 38 | X38 | fork 中断中フォルダ移動 → journal ごと移動先で発見 → recovery が先行 | 問題なし |
| 39 | X39 | 一時読取不能 × damaged 誘導: 読取 EIO は保留 + status、破損のみ damaged | 問題なし |
| 40 | X40 | standalone read の規約 12 照合: 未登録 path は実行可 + provenance 表示 / 登録済みは照合必須 | 問題なし |
| 41 | X41 | (b') seq+1 → 載せ直し → 相 3 seq+1 → collect 成功記帳: ledger 3 行が別 attempt で一貫 | 問題なし |
| 42 | X42 | ready が C の damaged 復帰で落ちるか → synced=NULL の C が母数復帰 → ready 再判定で落ちる | 問題なし |
| 43 | X43 | NFD 実体のみ + case-insensitive での resolver → NFC lookup で一致せず → collision | 問題なし |
| 44 | X44 | conflict 中の単独検索 → fork 進行中 status + provenance に conflict 表示 | 問題なし |
| 45 | X45 | 主張「照会失敗 (unknown) で二重 job は作られない」 → unknown は state=0 保持。破れず | 問題なし |
| 46 | X46 | 期限超記帳 (token, k+1) → 載せ直し → 相 3 (job id, k+2) → collect: 3 行とも述語で正しく区別 | 問題なし |
| 47 | X47 | (i)〜(iv) 1 Tx のクラッシュ: (ii) 完了後クラッシュ → 再実行で述語が記帳済みを検出 → skip | 問題なし |
| 48 | X48 | restore 保全コミットと restore 内容が同一 hash → no-op で正しい。保全は §20.5 手順で実施 | 問題なし |
| 49 | X49 | unregister 実行前の fork 回復: 回復完了後、回復結果を入力に unregister が進む | 問題なし |
| 50 | X50 | 主張「§6/§7 の往復は全段可逆」 → G→\G→\\G の test vector、再 materialize 非再適用。破れず | 問題なし |
| 51 | X51 | 期限超 (ii) の行 UPDATE → (iv) 相 1 → 相 3 の +1: 同一 attempt が二重加算されない | 問題なし |
| 52 | X52 | expired 行の intent_token 残存 → sweep が NULL 化. unregister は token NULL 条件で削除せず | 問題なし |
| 53 | X53 | 4 照合点の 8 要素表: 全照合点で三値/期限/未来skew/猶予/述語/seq行UPDATE/batch_job_id値/後続動作が一致 | 問題なし |
| 54 | X54 | ゲート例外 (破損 journal) × 一時読取不能: digest 不一致のみ damaged、EIO は保留 | 問題なし |
| 55 | X55 | :current_tool 同時刻 tie = tool_profile_hash バイト昇順。一括変換逆転の近似注記あり | 問題なし |
| 56 | X56 | decoder 拡張後: 緩い un-escape パターンで `\`+grammar 形全部が 1 個除去 → 可逆成立 | 問題なし |
| 57 | X57 | 自己記述化 × dispatch (batch_job_id 非 NULL = client): state=2/3 の自己記述化行は 相 1 で NULL 化 | 問題なし |
| 58 | X58 | error='detached' 行の再登録 → state=3・attempts<上限 → 投入対象。意図されたコスト注記あり | 問題なし |
| 59 | X59 | submit_rejected 除外 × 課金する provider → 倒す分岐自体で同一 Tx 冪等記帳 (S19) | 問題なし |
| 60 | X60 | escape(G→\G) × un-escape(\G→G) × 認識(行全体厳密一致) の往復: test vector 3 段で可逆確認 | 問題なし |
| 61 | X61 | 伝播猶予 10 分 × Mistral Batch 可視化遅延: 猶予内 CA は unknown 保持。主張破れず | 問題なし |
| 62 | X62 | job_create_started_at: 相 2b 前の小 Tx で記録 → crash 後再試行は上書き。NULL=相 2b 未着手 | 問題なし |
| 63 | X63 | cancelled terminal 行: state=3 + completed_at + 冪等記帳、削除は段階遷移、再登録後は投入対象 | 問題なし |
| 64 | X64 | found IN (発見 job id, 当該 token) の二重条件: 別 attempt 実 job (J2) の found 記帳を誤省略する操作列が構成不能 | 問題なし |
| 65 | X65 | no-replace rename 非対応 FS: 試行→EINVAL→通常 rename+再 lstat の決定規則が必要。文書に「可能なプラットフォームでは」とあり実装判断に委ねられる (proposal) | 問題なし |
| 66 | X66 | 規範↔要約↔掲載 SQL↔DDL コメントの横断: S02/S03/S04 の 3 件とも規範・掲載 SQL・DDL コメントの三者一致 | 問題なし |

自由探索: fork 手順 3 の was_tracked 判定で journal 固定値使用と folders 現状からの再判定禁止が明記 — 再実行安全。問題なし。

### 第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| T01 | minor | §21.3 fork-journal 版付き record {v:1,...} に started_at が含まれていない | fork stalled 猶予 (30 日) の起点は flag (fork_in_progress JSON) の started_at のみ。journal 自身に started_at が無いため、app.sqlite 全損後に journal だけで stalled 判定ができない | bootstrap で journal 発見 → app 全損で flag 喪失 → journal に started_at なし → stalled 判定不能 | C8 | journal の JSON record に started_at フィールドを追加 |
| T02 | proposal | §6 grammar 版検出: img block の v: 行は必ず 1 つ目の img block に存在する前提。画像 0 件文書はスキップでよい | 画像 1 件で v: 行の位置が 1 つ目の img block と暗に仮定されている。最初の img block の v が正である保証は書かれていない | 別 grammar 版の img block を先頭に手書き混入 → v=2 で再解析側 fail-closed 検出 → 正しい v=1 の img block は後続 | C11 | img block ごとに version 検査し、混在時は fail-closed へ倒す旨の明記 |
| T03 | minor | §20.5 resolver の「case 折り畳み + 採用規則」が walk 時の case 規則 (§20.5 初出表記固定) と同一の実装を要求するが、参照が明示的でない | resolver は「walk と同じ規則 (NFC + case 折り畳み + 採用規則)」と書かれるが、採用規則 (初出表記/ UTF-8 昇順 tie-break) の参照先 §が明示されていない | 実装者が resolver の採用規則を walk とは独立に実装 → 食い違いで name_collision の収束が異なる | C3 | resolver の採用規則に walk の case 規則 (§20.5) への明示的相互参照を追加 |

### 第 4 部 — 確認済みの列挙

**原則 (P1〜P16)**: P1(三層構成+規約7) / P2(識別子規範) / P3(8テーブル+profiles) / P4(chunks統一) / P5(チャンク分割) / P6(OCR) / P7(FTS) / P8(Embedding) / P9(batch処理) / P10(書込順序+冪等性) / P11(集約) / P12(検索) / P13(GC+fsck) / P14(SQLite設定) / P15(不変部分) / P16(変更検知) — すべて確認済み、原則との矛盾なし。

**検査観点**: C1(原則反映) / C2(SQL静的検証) / C3(相互参照整合) — T03 の 1 件除き問題なし / C4(クエリ整合) / C5(数値一貫性) / C6(用語・形式一貫性) / C7(状態機械完全性) / C8(欠落) — T01 の 1 件除き問題なし / C10(修正相互作用) / C11(合理性) — T02 の 1 件除き問題なし / C12(探索型監査) — 全 66 シナリオ実行、新規検出は minor 2 件 + proposal 1 件
