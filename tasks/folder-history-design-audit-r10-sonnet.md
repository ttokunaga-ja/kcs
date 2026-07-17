# folder-history-sqlite-design.md r10版 監査結果 (Sonnet 15エージェント並列監査)

対象文書: `docs/research/folder-history-sqlite-design.md` (r10版、2182行)
監査方法論: `tasks/folder-history-design-audit-prompt.md` (r10版監査プロンプト)
実施方法: Claude (Sonnet) 15エージェント並列 — C9回帰チェック6本(A〜K全205項目)、C1/C8原則チェック1本、
SQL静的検証1本、参照整合+状態機械1本、修正相互作用+実装可能性1本、C12探索型監査5本(X1〜X30+自由探索)。
各エージェントは対象文書を全文読了した上で独立に判定し、本レポートはその統合。

---

## 合否判定

# **不合格**

理由:
1. C9 の205項目中 **K02が partially-fixed**(not fixed/superseded以外)であり、「全項目fixedまたはsuperseded」の条件を満たさない
2. 新規検出に **fatal 1件・major 12件** があり、「fatal/major 0件」の条件を満たさない

探索ログは前提条件(35シナリオ以上、X1〜X30全観点実行)を満たしている(**80シナリオ**、全30観点+自由探索4件を実施)ため、本報告は有効である。

---

## サマリ

| 区分 | 件数 |
|---|---|
| C9 総項目数 | 205 |
| うち fixed | 179 |
| うち superseded (対応表どおり) | 25 |
| うち partially-fixed | **1 (K02)** |
| うち not-fixed / regression | 0 |
| 探索シナリオ数 | **80**(要求35以上を充足) |
| 新規検出 fatal | **1 (L01)** |
| 新規検出 major | **12 (L02〜L13)** |
| 新規検出 minor | 14 (L14〜L27) |
| 新規検出 proposal | 2 |

最重要所見: **§9.1(834行付近)の説明文「UNIQUE(repo,kind,target_key,attempt) が ledger の二重計上を構造的に防ぐ」は、実DDL(728行、`UNIQUE (repository_id, kind, target_key, submission_seq)`)および直前の列コメント(「attempts は使わない」)と直接矛盾する r9(K02)の残存修正漏れ**。15エージェント中10エージェントが独立にこの1箇所を検出しており、監査対象文書のうち最も高確度の欠陥。DDL自体は正しいため即座に動作不能になるわけではないが、この一文だけを読んだ実装者はK02が塞いだはずのfatalパターン(attemptsリセット後の正当な再課金がUNIQUE衝突でclose Tx恒久失敗)を再導入しかねない。

---

# 第1部 — 回帰確認 (C9)

## Compressed(fixed / superseded)

- **A01–A24**: fixed except A11 (superseded→I05・I06・I13・I14)
- **B01–B18**: fixed
- **D01–D14**: fixed except D05 (superseded→E04)
- **E01–E06**: fixed
- **F01–F27**: fixed except F05(superseded→I14), F07(superseded→I15), F10(superseded→H08), F12(superseded→I16・I17), F21(superseded→I03・I04)
- **G01–G02**: fixed
- **H01–H30**: fixed except H02(superseded→I32), H04(superseded→I31), H15(superseded→I08・I11), H18(superseded→I16), H22(superseded→I15)
- **I01–I38**: fixed except I03(superseded→J06), I04(superseded→J06), I05(superseded→J01・J02), I06(superseded→J01・J02), I09(superseded→J03), I15(superseded→J04), I16(superseded→J05・J01), I17(superseded→J05・J01), I35(superseded→J13〜J16), I32(superseded→J18)
- **J01–J20**: fixed except J04(superseded→K01), J10(superseded→K09)
- **K01, K03〜K26**: fixed

## Table (partially-fixed / not-fixed / regression のみ)

| ID | 判定 | 根拠 |
|---|---|---|
| **K02** | **partially-fixed** | §9.1 DDL(728行)は `UNIQUE (repository_id, kind, target_key, submission_seq)` に是正済みで、直前の列コメント(719-722行)も「attempts は使わない — リセットで番号が再利用され、正当な再課金の記帳が UNIQUE 衝突で恒久失敗する」と正しく明記している。しかし同じ§9.1内、collectのitem成功分岐の説明文(834行付近)に旧世代の記述「UNIQUE(repo,kind,target_key,**attempt**) が ledger の二重計上を構造的に防ぐ」が残存し、DDLおよび隣接コメントと直接矛盾する。**15エージェント中10エージェントが独立に同一箇所を検出**(C9担当2本(r3/r4班・r7班・r8班・r9班) + SQL班 + 参照整合班 + 相互作用班 + 探索3本)。 |

備考(判定に影響しない process note): C9-r8班(J01-J20担当)は既知supersededマッピング表中の「J13のfork_in_progress(app記録)→K16」が実際のK16本文(§5.3参照修正+初期値の話)と直接結びつかないと指摘した。J13自体は本文を直接確認して fixed と判定しており結論に影響しないが、次回監査プロンプト更新時にこのマッピング行の妥当性を見直すことを推奨する。

---

# 第2部 — 探索ログ (C12、80シナリオ)

### X1〜X10 (担当エージェント1、14シナリオ)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 1 | X1 | OCR submit済み(state=1)の対象ファイルをdelete確定後、collectを実行 | 問題なし — content_hash識別のため正常完了、GC参照集合にも残留 |
| 2 | X1 | 過去版のみに存在する(H1,tool)行にfloor設定→submit | 問題なし — 「floor設定済みはbackfill設定に関わらず候補」どおり投入 |
| 3 | X2 | 攻撃者が自分の画像Xを使い、OCR結果のページN末尾/N+1先頭にimg block参照を分割配置 | **L06へ**(ページ結合後にのみ完全な参照行が非エスケープで出現) |
| 4 | X2 | 0バイトファイルを配置→scan→OCR submit前preflight | 問題なし — マジックバイト不一致でunsupported_format terminal行を1回作成 |
| 5 | X3 | macOS NFD readdir結果→初回commit(NFC保存)→2回目scan(fp生値/scan_cache NFC値) | 問題なし — 変換点はreaddir直後の1箇所に一意に定まる |
| 6 | X4 | 同一ミリ秒created_atの並行コミット2件→selected_files計算 | 問題なし — commit_hashが第2キーのため1件に確定 |
| 7 | X4 | floor設定済み対象で、収集直前に時計がfloor未満へ後退 | 問題なし — max(now,floor+1)によりfloor+1が採用される |
| 8 | X5 | 500ページ級PDF・chunk約2000件でgrammar version bump→一括再materialize→agg全置換 | 問題なし — 規模コストは§19「再考条件」で明示的に先送り済み |
| 9 | X6 | 1リポジトリのOCR対象がJSONL行数/バイト数上限超過→複数job分割 | 問題なし単体では(分割時のtoken粒度はX16でL09関連として検出) |
| 10 | X7 | 画像0件文書とopt-inフィルタ全除外文書混在下でgrammar version bump | 問題なし — v:行の有無で移行要否を一意判定可能 |
| 11 | X8 | 社外秘プロジェクト名を含むfile_nameの原本をOCR投入(相2 upload) | **L16へ**(filenameにintent_token埋め込みのみで元file_name遮断の明記なし) |
| 12 | X9 | ディスク残量僅少下でcollect kind=1のapp Tx実行中にENOSPC | 問題なし — 次tickの冪等スキップが再試行、status監視で可視化 |
| 13 | X10 | 管理フォルダをzip化→解凍(mtime/inode全変化)→段1で全件再hash | 問題なし — 過検知のみ(安全側)、content_hash一致なら再保存なし |
| 14 | X10 | file_versions.content_hashを別実在object hashへ直接改竄→fsck | 問題なし — commit_record再構築・commit_hash再計算照合が改変を検出 |

### X11〜X20 (担当エージェント2、20シナリオ)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 15 | X11 | profile変更でkind=2行削除→cost_ledger課金履歴の道連れ消失を再現試行 | 問題なし — cost_ledger分離(r8)により経路が構造的に存在しない |
| 16 | X12 | E2E一気通貫: register→scan→OCR submit→collect→embed submit→replicate→横断検索 | **L14へ**(app_config初回投入手順が§21のどの操作にも見当たらない) |
| 17 | X13 | §21.7明示操作カタログの入力・手順・失敗時挙動の総点検 | L14と同一問題を別角度で検出 |
| 18 | X14 | 恒常stat失敗ファイルが1件ある管理フォルダでfp_cache孤児掃除の発火条件を追跡 | **L04へ**(完全walk永久不発火) |
| 19 | X15-a | 主張「floorの先行引き上げはfail-safe、逆順は明示再生成を黙って取り消す」試行 | 破れず |
| 20 | X15-b | 主張「全ステップが差集合クエリ駆動なのでtickは何度実行しても安全」試行(OCR collect metadata Tx後・app Tx前クラッシュ) | K02の残存不整合を検出(文書記述レベル、構造自体は破れず) |
| 21 | X15-c | 主張「GCはtick.lock取得により中間状態を観測しない」試行 | 破れず |
| 22 | X15-d | 主張「migrationは単一Tx、再実行は常に安全」試行 | 破れず |
| 23 | X15-e | 主張「detached行はフォルダへ書込しない」試行(unregister直後の再register競合) | **L19へ**(二重課金の副作用を検出) |
| 24 | X16 | 「2相submitと1job=1repository・JSONL複数分割の整合」— 1万件超規模での分割 | **L18へ**(分割アルゴリズム・token粒度未規定) |
| 25 | X17 | fork後の派生保持とGC・aggの整合(旧版の派生object回収) | **L15へ**(検索到達不能かつ回収不能な永久孤児) |
| 26 | X18 | pending_deletesとdeep-scan・fp確定禁止・walk完全性条件の相互作用 | L04と同一問題(#18)の別角度 |
| 27 | X19-a | ディレクトリfsync適用点の網羅性チェック | 問題なし |
| 28 | X19-b | 相2内「upload成功→job作成呼出前」クラッシュ境界 | 問題なし — job未作成のため課金なし、intent回復が正常回収 |
| 29 | X20-1 | 主張「重複課金はintent回復により最悪job1回分に有界」試行 | 破れず(範囲内) |
| 30 | X20-2 | 主張「attempt単位なので月跨ぎretryも発生月へ正しく配賦」試行 | **L25へ**(表現精度の懸念、構造自体は破れず) |
| 31 | X20-3 | 主張「宣言的に収束する」試行(vec DROP/CREATE/差集合再充填の複数文分割) | **L17へ**(単一Tx明記なしの軽微な曖昧さ) |
| 32 | X20-4 | 主張「forkは派生台帳を保持する」試行 | L15と同一問題(#25)の別角度 |
| 33 | X20-5 | 主張「pending_deletesは削除を見逃さない」試行 | L04と同一問題の別角度(「見逃さない」は成立するが「確定する」保証がない) |
| 34 | X20-6 | 主張「rename後dir fsyncで規約6の存在保証が成立」試行 | 破れず |

### X21〜X25 (担当エージェント3、14シナリオ)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 35 | X21 | kind=2相1直後(state=0)クラッシュ→次tick intent回復→新token再送 | 問題なし |
| 36 | X21 | 相2 upload成功・job作成コール送出後クラッシュ→intent回復でupload残骸発見・削除 | 問題なし |
| 37 | X21 | client側キュー・実行前計上直後にクラッシュ→tick.lock越しにprofile変更 | **L09へ**(実行前計上の項目列挙にprofile_hash更新が含まれず非収束ループの懸念) |
| 38 | X21 | floor引き上げ済み・一括再チャンク交錯でapp Tx成功・metadata Tx前クラッシュ | 問題なし — fail-safe側に倒れる |
| 39 | X22 | 同一repository_idの2物理フォルダ(conflict)、非追跡側をfork→tick除外の粒度 | **L13へ**(id単位除外だと生存側も巻き込まれ得る) |
| 40 | X22 | fork手順1のdefer_foreign_keysと§14 foreign_keys=ONの共存 | 問題なし — SQLite標準機構で両立 |
| 41 | X23 | K02残存箇所の直接検出(DDL・列コメント・collect説明文の突合) | K02残存の追加確証 |
| 42 | X23 | detached行の3経路(unregister/§9.3-d/fork)の規範文言突合 | 問題なし — 3経路とも同一規範を相互参照 |
| 43 | X24 | 主張「差集合再充填はどのクラッシュ位置でも欠落を埋める」試行(profile A→B→A往復+分割commit中crash) | 破れず |
| 44 | X24 | 主張「agg毎tick冪等検査」試行(DROP→CREATE直後・マーカー更新前クラッシュ) | 破れず(文言通り実装した場合) |
| 45 | X24 | 主張「client側キューはstate=1を跨がないのでintent回復不要」試行 | #37(L09)と同根に帰着 |
| 46 | X25 | 新規app.sqlite(app_config未設定)でregister→直後tickのsubmit/embed submit | L14と同一問題の追加確証 |
| 47 | X25 | restore 4入力(in-place/エクスポート/content_hash単独/delete版)の整合 | ほぼ整合(proposal相当の軽微な非対称のみ) |
| 48 | X25 | watch_root解除後もfolders.root_path起点で検知継続→フォルダ移動 | 問題なし — missing/猶予/自動退役ルールがそのまま適用 |

### X26〜X27 (担当エージェント4、13シナリオ、本命)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 49 | X26 | submission_seq書込点3箇所(相3/intent採用/client前計上)の重複・欠落 | 問題なし |
| 50 | X26 | ledger UNIQUE制約と冪等再実行(collect close Tx再実行) | K02残存の追加確証 |
| 51 | X26 | 相2恒久拒否(submit_rejected)と成果ありreconcile・明示retryの順序 | **L02へ**(attempts不消費のterminalが次の通常tickで自動再投入される) |
| 52 | X26 | client前計上とserver intent回復の判別 | **L09へ**(#37と同一問題の追加確証・精密化) |
| 53 | X26 | profile_record snapshotが相1UPDATEで旧値のまま残る経路の有無 | 問題なし |
| 54 | X26 | app_config未設定(bootstrap前)の相1挙動 | L14と同一問題の追加確証 |
| 55 | X26 | floor引き上げのapp先行順序とクラッシュ窓の再検証 | 問題なし — 文書の主張通りfail-safe側に倒れる |
| 56 | X27 | journal書込(層1)とapp側fork_in_progress書込の間のクラッシュ | 問題なし |
| 57 | X27 | 手順1後・2前、手順2後・3前クラッシュの失敗回復表どおりの再開 | 問題なし(文書記載の2ケースは安全) |
| 58 | X27 | **手順3後・4前クラッシュ**(新folders行INSERT済み・journal未削除) | **L07へ**(失敗回復表に欠落、bare INSERTでPK衝突) |
| 59 | X27 | 通常クラッシュ(app全損を伴わない)でfork手順2後に長期放置→ユーザーが再fork手動起動 | **L08へ**(再開トリガーが app全損bootstrap限定、孤児folders行発生) |
| 60 | X27 | 非追跡側コピーforkで生存側の追跡・in-flightが無傷か(tick除外粒度) | L13(#39)と同一問題の追加確証 |
| 61 | X27 | fork中tick除外と§9.3-d猶予の適用対象排他性 | 問題なし |

### X28〜X30 + 自由探索 (担当エージェント5、19シナリオ、本命)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 62 | X28 | 通常のdetachedライフサイクル(unregister→cancel失敗→collect終端→削除) | 問題なし(規範通り収束) |
| 63 | X28 | **client-path実行前計上直後クラッシュ→unregister→cancel対象不明→detached化→state=0即削除** | **L01へ(fatal)** |
| 64 | X28 | #63直後にrepo再register→Embed submitが同一target_key新規INSERT | 問題なし(L01の課金追跡欠落は残存) |
| 65 | X28 | state=1(detached、job未終端)のまま再register | 問題なし — 自動的に通常行へ復帰、PK衝突なし |
| 66 | X28 | detached、同一upload_id共有のkind=1行2つ(state混在)と4.5条件 | 問題なし — uploadはrepository単位のため混在しない |
| 67 | X29 | case-insensitive volumeでcase-onlyリネーム+内容変更同時発生 | 問題なし(手動renameは元々履歴非対象) |
| 68 | X29 | macOS NFD "café.pdf"新規作成→NFC正規化が最初に適用され初出表記として保存 | 問題なし |
| 69 | X29 | **case-insensitive→case-sensitive物理コピー後の大小文字違い2実体共存** | **L10へ**(判定タイミング=キャッシュか毎回再取得か未規定) |
| 70 | X29/X30 | **case-sensitive上で独立系列だった2ファイルがcase-insensitiveへ移動しコピーツールが一方を上書き** | **L11へ**(複数系列fold衝突の優先規則なし) |
| 71 | X30 | 主張「ledger UNIQUEは正当な再課金を一切妨げない」試行 | 破れず(ただしK02残存誤記述を再確認) |
| 72 | X30 | 主張「client経路の重複課金はattempts上限で有界」試行(profile A→B→A→B反復) | **L24へ**(能動的反復操作前提の弱い保証、minor) |
| 73 | X30 | 主張「forkはどの境界のクラッシュからもjournalで一意に再開できる(app全損含む)」試行 | L08(#59)と同一問題の追加確証 |
| 74 | X30 | 主張「保存名固定によりcase-only renameのFK違反は構造的に不可能」試行 | 破れず(FK自体は健全、問題はマッチング前段) |
| 75 | X30 | 主張「最小不在時間30秒でdirty早回しの偽deleteは不可能」試行 | 破れず |
| 76 | X30 | 主張「detachedは課金を取りこぼさない」試行(#63再確認) | 破れる — L01と同一 |
| 77 | free | 破損profile行(参照元batch_requests行は削除済・app_config現行とも不一致)でfsck実行 | 問題なし — 文書の明示フォールバック(報告に留め明示再生成誘導)どおり |
| 78 | free | fork_in_progress抑止ウィンドウ中に第三者が`.folder-history`を丸ごと差し替え | 問題なし — tick除外中は処理が走らず、fork完了後の規約12再有効化時に検出 |
| 79 | free | **name_collision確定後、勝者ファイルをOS上で削除→次scan** | **L12へ**(敗者の物理ファイルが勝者の論理名への「更新」と誤認され得る) |
| 80 | free | unregister→長期放置→再register時のcost_ledger新旧混在 | 問題なし — 「削除しない」仕様通り、tsで新旧判別可能 |

**確認済み(反証を試みたが破れなかった主張)**: X15(5主張)・X20(6主張)・X24(3主張)・X30(6主張)の合計20件の明示的反証試行のうち、K02の残存誤記述に関連するもの以外は全て「破れず」。文書の耐久性設計の大半は主張通り機能することを確認した。

---

# 第3部 — 新規検出

## Fatal

| ID | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|
| **L01** | §9.1「detached 行の処理規範」: 「state=0 の detached: job 未作成 = 課金なし…行を即削除する」 vs §8(iii)「前計上済み (batch_job_id 非 NULL・state=0) の行は『実行された可能性がある』として扱い…再実行する」 | detached規範の「state=0 = job未作成 = 課金なし」という前提は、client側キュー(§8実行前計上)経路には当てはまらない。client経路のstate=0行は「実行された可能性がある」ことを§8自身が明言しているにもかかわらず、detached化した瞬間にこの区別なく即削除される。さらに§10のtickステップ0〜5には"detached"という語が一度も出現せず(grep確認済み)、この削除処理自体を実行するtickステップの割当が存在しない。 | ①kind=2・client側キュー(§8)構成で、実行前計上Tx(attempts+1・submission_seq+1・batch_job_id=intent_token 永続化)がcommitされた直後、同期API呼出中にプロセスがクラッシュ(実際にはプロバイダ側で処理・課金が完了している可能性がある)。②復帰後、tickが走る前にユーザーがunregister(§21.2)を実行→cancel対象の実体ID(intent_token相当)をローカルでcancel試行するも、そもそもこのAPIがclient側キューには存在しないためcancel未確定→detached化。③次のcollect相当処理で§9.1「state=0 の detached: job 未作成 = 課金なし…行を即削除する」が適用され、行(=唯一の課金追跡情報)が即座に削除される。④実際には②以前にプロバイダ側で処理・課金が完了していた場合、その事実を検証する手段(intent_tokenやbatch_job_idを含む行)ごと消滅し、cost_ledgerへの記帳機会も永久に失われる。P1(規約7)が列挙する「有界な損失」のいずれにも該当しない、無条件かつ無期限の課金追跡喪失。 | P1(規約7 f)/P9(detached規範)/C7/X28 | detached化のstate=0削除条件に「batch_job_id が intent_token 由来(client前計上済み)でないこと」を追加し、client前計上済みのstate=0 detached行は state=1 detached同様「結果照会を試行→終端したらpayload破棄+記帳」の経路に振り分ける。あわせて§10のいずれかのtickステップ(例: 4.5直後)に detached行の掃除処理を明示的なステップとして割り当てる。 |

## Major

| ID | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|
| **L02** | §9.1 submit判定表「成果なし・state=3・attempts < 上限 → 投入対象(再投入)」/ 相2「恒久拒否…state=3(error='submit_rejected')、復帰は明示 retry のみ」 | 相2の恒久拒否(submit_rejected)遷移はattemptsを消費しない(相3を経由しないため)。したがって遷移直後はattempts=0<上限のままであり、次の**通常の**tickのsubmit差集合走査は、submit判定表の一般則(「state=3・attempts<上限→再投入」)に従って**自動的に**再投入してしまう。同じ箇所が明記する「復帰は明示 retry のみ」という保証と直接矛盾する。クラッシュや特殊なタイミングを一切必要とせず、通常のtick実行だけで発生する。 | ①新規content_hashのOCR対象を通常投入(相1: state=0)。②相2でプロバイダが内容起因の4xxを返す(恒久拒否)→state=3, error='submit_rejected', attempts=0のまま。③何もクラッシュさせず、次の通常tick(cron等)がstep1のsubmit差集合を評価→「成果なし・state=3・attempts(0) < 上限(3)」に該当→再投入対象と判定され、同一内容が再度uploadされ再度4xxで拒否される。④この無限載せ直しループが、まさに「submit_rejectedをterminal直行させることで防ぐ」はずだった対象に対して発生する。 | P9(submit判定表)/C7/X26 | submit判定表に`error='submit_rejected'`の除外を明記する(例:「state=3・error≠'submit_rejected'・attempts<上限→再投入」)、または相2の恒久拒否遷移時にattemptsを上限値まで進める一文を追加する。 |
| **L03** | §9.2 agg_file_versions DDL(「以下の DDL が省略なしの実定義」と明言) | file_versions(§5.2)が持つ複合CHECK「(event_type=3 AND content_hash IS NULL AND size_bytes IS NULL) OR (event_type IN (1,2) AND content_hash IS NOT NULL AND size_bytes IS NOT NULL AND size_bytes>=0)」が、agg_file_versionsには存在しない(個別列のblob型/長さCHECKのみ)。姉妹テーブルagg_chunks(「§5.4と同一の行CHECK」で複製)・agg_embeddings(dimensions複合CHECKを複製)とは対照的に、このテーブルだけ複合CHECKが欠落しており、直前の「省略なしの実定義」という明言と食い違う。 | §11.1(B)の過去版込みモード`WHERE content_hash IS NOT NULL`は、event_type=3(delete)の行がcontent_hash NULLであるという不変条件(file_versions側のCHECKが保証)に暗黙に依存する。agg側にこの複合CHECKが無いため、レプリケーション実装のバグでevent_type=3かつcontent_hash非NULLの行(または逆)が agg_file_versions に混入した場合、これを検出する手段がスキーマレベルに存在しない。 | C2(a)/C4/P3 | agg_file_versionsのCREATE TABLE末尾に、file_versionsと同一の複合CHECKを追加する。 |
| **L04** | §20.5「(a) そのwalkが完全に成功していること…1件でもエラーを返したフォルダはdelete判定・scan_cache更新・fp_cache更新をすべて見送る」/ §20.3「fp_cacheの孤児行は…完全walkが成功した際に…DELETEして掃除する」/ 規約11「低頻度deep-scanが理論上の見逃しを有界時間で補正する」 | 管理フォルダ(非再帰・単一ディレクトリ)内の1ファイルが恒常的にstat失敗する(AVロック・権限異常・不安定なネットワークマウント等)状態が続くと、そのフォルダ全体のdelete確定(pending_deletes開始)とfp_cache孤児掃除が**無期限に**発火しなくなる。deep-scanも同一walk機構を使うため救済されない。規約11が明示的にカバーする「mtime保存コピー・racy」の範囲外の失敗モードであり、専用statusも存在しないため、削除済みファイルが検索・現在版に残り続ける事実にユーザーが気づく手段がない。 | ①管理フォルダFにa.txt, b.txt, c.txtが存在。②b.txtがAVソフトの排他ロックで恒常的にstat/read失敗する状態になる(または権限異常・不安定なネットワークマウントの一時的挙動が長期化する)。③ユーザーがc.txtを削除。④以降、毎回のscan(通常tick・deep-scan問わず)がb.txtのstat失敗で「1件でもエラー」条件に該当し、フォルダF全体のdelete判定・pending_deletes開始・fp_cache更新がすべて見送られ続ける。⑤c.txtの削除は現在版に永久に反映されず、検索結果にも古い内容が残り続ける。ユーザーへの警告も存在しない。 | 規約11/§20.3/§20.5/X14, X18, X20-5 | delete判定・fp孤児掃除のwalk完全性判定を「エラーを返した個別エントリ」単位に限定するか、N回連続で不完全walkが続いたフォルダには専用status(例: stuck_walk)を出し、当該ファイルを名指しで警告する。 |
| **L05** | §5.3「行が無ければ(app再構築後等) state=2, attempts=0, batch_job_id / intent_token / upload_id = NULL, submission_seq=0 で INSERT する」 | 明示再生成(§5.3)は本来「対象ペアのbatch_requests行にfloor_generated_atを設定する」ことでkind=1の「成果あり」判定を無効化し再OCRを駆動する仕組みだが、対象のbatch_requests行が存在しない場合(app.sqlite再構築後など)のフォールバックINSERT文はfloor_generated_atを設定する列を含んでいない。markdown_documents側に既存行が残っている場合、floor=NULLのままkind=1「成果あり」判定(「行が存在し、かつfloor_generated_atがNULLまたはgenerated_at>floor」)が真になり、ユーザーが要求した明示再生成が黙って不発に終わる。 | ①フォルダRの(H1,tool)についてmarkdown_documents行が存在(既存のOCR結果)。②app.sqliteが全損し再構築される(batch_requests行が消滅、規約7(d)の想定内シナリオ)。③ユーザーが破損を疑い(H1,tool)に対して明示再生成(§5.3)を実行→「行が無ければ」のフォールバックが発火し、state=2,attempts=0,floor_generated_at列は設定されず(NULLのまま)でINSERTされる。④次tickのsubmit判定:「行(markdown_documents)存在 かつ floor NULL」→「成果あり」→submitされない。⑤ユーザーは明示再生成を実行したにもかかわらず再OCRが一切発生しない。 | P9(kind=1成果あり定義)/§5.3/C10(n)/X21 | フォールバックINSERT文に `floor_generated_at = 現在時刻` (または既存markdown_documents.generated_atと同値)を明示的に含める。 |
| **L06** | §6「materialize 時、OCR が返した本文テキスト側に canonical grammar へ適合する行…が含まれる場合、その行頭へ `\` を前置してエスケープする」 | エスケープの適用単位(個々のpages[].markdown単位か、§10 step2で結合した後の全文単位か)が明記されていない。文言上「OCRが返した本文テキスト」は結合前のページ単位を指すと読める。攻撃者が自分のPDFに実在する画像Xを同梱し、image_hash(X)を事前計算した上で `![evil](obj:` をページN末尾に、`<hash(X)>)`+偽meta+`-->` をページN+1先頭に分割配置すると、各ページ単体では完全なgrammarパターンに一致しないためエスケープされないが、ページ結合後にのみ完全な参照行が出現し、非エスケープのまま解析器に渡る。§7規則3の実在検証(image_hashがobjects/に実在するか)も、攻撃者が自分の実在画像を使っているため素通りする。 | ①ユーザーが自分のPDFに任意の画像Xを埋め込み、事前にimage_hash(X)を計算しておく(自分のファイルなので可能)。②OCR結果のページNの本文末尾に`![evil](obj:`という文字列が来るように、ページN+1冒頭に`<hex(X)>)\nv: 1\n...\n-->`が来るように、原稿(PDFレイアウト)を細工する。③§10 step2のpage結合処理が両ページのmarkdownをLF正規化して結合。④§6のエスケープがページ単位で実行されていた場合、結合後の全文には完全なcanonical img block参照行が非エスケープのまま存在し、§7の解析器がこれを正規のimageチャンクとして認識する(実在検証も画像Xが本物のため通過)。 | §6/§7規則3・4/X2 | §6に「エスケープは pages[].markdown 結合後の全文に対して行う(ページ単位のエスケープのみでは不十分)」と明記するか、結合直後に再度エスケープパスを追加する。 |
| **L07** | §21.3 失敗回復表(手順1後・2前/手順2後・3前の2ケースのみ記載) | 失敗回復表は「手順3後・4前」(新folders行INSERT済み・journal未削除)の境界を欠く。bootstrap文言も「app.sqlite全損時は手順3〜4を完了させる」と一括りにしており、手順3が既に完了しているかどうかを区別する条件が与えられていない。§21.3手順3の新folders行INSERTは`OR IGNORE`等が付いていない素のINSERTであり(§5.1/§5.2/§5.7など他の類似INSERTは`INSERT OR IGNORE`を明示)、この境界からの再開(手順3の再実行)を素朴に行うとPRIMARY KEY(new repository_id)衝突を起こす。 | ①fork(§21.3)実行、手順0(journal書込)〜手順3(新folders行INSERT・旧folders行退役)まで完了、手順4(journal削除)の直前でクラッシュ。②app.sqliteは無傷(全損ではない)。③再起動後、失敗回復表に「手順3後・4前」の記載が無いため、実装者は「journalが残っている=fork未完了」と解釈し安全側で手順0からやり直す(または手順3を素朴に再実行する)実装をしがちだが、手順3の素のINSERTが既存のnew repository_id行とPK衝突しエラーになる。 | §21.3/C10(z)/X27 | 失敗回復表に「手順3後・4前クラッシュ: journal存在+新folders行存在→手順4(journal削除)のみ実行して再開」の行を追加し、手順3のfolders INSERTを`INSERT OR IGNORE`にするか実行前にfolders[new_id]の存在チェックを行う。 |
| **L08** | §21.3 bootstrap「app.sqlite 全損を挟む場合: bootstrap の walk が fork-journal を持つフォルダを検出したら…」 | クラッシュ回復のトリガーとして文書が明示するのは「app.sqlite全損後のbootstrap walk」のみ。app.sqliteが無傷のまま単にプロセス・tickが停止した(実運用上最も頻度が高いはずの)通常クラッシュについて、誰が・いつfork再開を駆動するかの記述が無い。fork_in_progressが立っている間、対象repoはtickの全ステップから恒久的に除外され続ける(§21.3手順0)。 | ①fork実行、手順2(repository-id書換え)完了・手順3(folders行操作)未実行の状態でクラッシュ。app.sqliteは無傷。②通常のtick再開では(app全損ではないため)bootstrap経路のfork検出・再開ロジックが発火せず、対象repoはfork_in_progressによりtickから除外されたまま放置される。③ユーザーが「forkが終わっていない」ことに気づき、同一パスに対して手動でfork操作を再度起動する。④§21.3手順0が新しいnew_idを再採番して実行される一方、旧new_id(=前回中断したfork試行のid)は誰にも退役されず、folders表に同一root_pathを指す孤児行として残存する可能性がある。 | §21.3/C10(z)/X27 | 通常tick(step0)にもfork_in_progress行の検出・再開ロジックを持たせるか、明示操作カタログ(§21.7)に「中断したforkの再開」操作を追加する。 |
| **L09** | §8(i)「実行前計上: 同期 API を呼ぶ前に app Tx で attempts+1・submission_seq+1・batch_job_id = intent_token・submitted_at を永続化する(相 1 と相 3 の統合に相当)」/ §10 step3「(iii) state=0 (kind=2) の intent 回復 (いずれも冪等 — §8-c/d, §9.1)」 | §8(i)の実行前計上フィールド列挙にprofile_hash/profile_record更新が明記されていない(相1本体は「profile_hashが現行と異なる行の再投入ではstateを問わずattempts=0にリセットする」を明記するが、(i)は「相当」という間接参照のみ)。加えて§10 step3は kind=2 の state=0 行すべてに §9.1 の「intent回復」(プロバイダのjob一覧照会)を無条件適用すると読めるが、client側キュー構成のプロバイダにはそもそも「job一覧照会」自体が存在しないと§8自身が明言しており、両者をどう出し分けるかの記述が無い。 | ①kind=2、client側キュー(§8)構成。実行前計上Tx(attempts+1, submission_seq+1, batch_job_id=intent_token, profile_hash=OLD時点)がcommitされた直後、同期API呼出前にクラッシュ→state=0, profile_hash=OLDのまま。②復帰前にembedding profileをOLD→NEWへ変更(§8)。③次tickのEmbed submit(step3)がstate=0行に到達し、汎用の「intent回復」ロジック(プロバイダのjob一覧照会)を適用しようとするが、client側プロバイダにはjob一覧APIが存在しないためこの経路が機能しない、または誤って「見つからない→残骸削除して新tokenで相1から」を適用してしまい、実際に実行中/完了済みかもしれない呼出のexec-id痕跡(batch_job_id)を消してしまう。 | §8/§9.1/§10 step3/C10(w)/X21, X26 | §8(i)の実行前計上フィールド列挙に「profile_hash = :current_profile / profile_record = 現行record(相1と同一)」を明記し、§10 step3(iii)に「provider(profile)がserver-side batchかclient側キューかで §9.1 intent回復 と §8(iii)再実行判定 を明示的に分岐する」旨を追記する。 |
| **L10** | §20.5「case 感度はボリューム属性から判定し、フォルダごとに固定する」 | 「フォルダごとに固定する」という表現が、判定を毎回のscanで再取得するのか、一度確定した値をキャッシュし続けるのかを明確にしていない。後者と解釈した実装では、フォルダがcase-insensitiveボリュームからcase-sensitiveボリュームへ物理的に移動(コピー等)された場合も古い判定モードのままfold判定が継続し、実際のボリューム属性と乖離する。 | ①case-insensitiveボリューム上でフォルダRを管理、case感度=insensitiveと判定(キャッシュ実装の場合ここで固定)。②Rを丸ごとcase-sensitiveボリュームへ物理コピー。③§20.4「root_path更新契機は再発見のたび」によりRが再発見されるが、case感度の再判定に関する規定が無いため、キャッシュされたinsensitive判定のままfold処理が継続する可能性がある。④この状態で"Report.pdf"と"report.pdf"という大小文字違いの2実体が新しく作られると、本来は独立系列として扱われるべきところ誤って1系列にfold判定される。 | §20.4/§20.5/X29 | case感度の再判定タイミングを明記する(例: 「register/再発見のたびに再判定し、fp_cache無効化と同様の扱いとする」)。 |
| **L11** | §20.5「walk が readdir 表記と case 違いで一致する既存 file_versions 系列を見つけたら…既存の保存済み論理名をそのまま使い続ける」 | この規則は暗黙に「fold一致する既存系列は高々1つ」を前提にしている。しかしcase-sensitiveボリューム上で独立に育った複数の大小文字違い系列(例: "Report.pdf"と"report.pdf"が別々の履歴を持つ)を含むフォルダがcase-insensitiveボリュームへ移動すると、単一の物理観測が複数の既存系列と同時にfold一致し得るが、その場合にどちらの系列の継続として扱うかの優先規則が無い。 | ①case-sensitiveボリューム上のフォルダRで"Report.pdf"と"report.pdf"がそれぞれ独立した履歴系列(共にLWW生存)として存在。②Rをcase-insensitiveボリュームへ移動するコピー処理が、OS制約により一方の実体で他方を上書きし物理的に1実体のみが残る。③次のscanが単一の物理名を観測し、fold判定によりこれが「どちらの既存系列の継続か」を一意に決定する規則が文書に無い。誤って選ばれなかった系列は、対応する物理ファイルが存在しないにもかかわらず正規のdelete判定(§20.5の三値観測)を経由しないため、検索上「現在も存在する」と誤って扱われ続ける可能性がある。 | §20.5/X29, X30 | 複数系列が同時にfold一致するケースの優先規則(例: LWW上位の系列を優先し、他方は明示的にdelete相当として扱う)を追加する。 |
| **L12** | §20.5 name_collision(「物理名のUTF-8バイト列昇順で最初の1件だけを採用」) | name_collisionで敗れた物理ファイルが存在し続ける状態で、後から勝者ファイルがOS上で削除されると、次回scanは敗者の物理ファイルのみを観測する。fold判定はこの観測を(敗者自身の独立した論理名としてではなく)勝者の論理名への一致として処理し続けるため、「勝者の論理名の下への更新」と誤認され得る。結果、勝者の真の削除が記録されず、敗者も独立した履歴を得られないまま消費される。 | ①case-insensitiveボリューム上で"DATA.txt"と"data.txt"が物理的に共存し、name_collision確定(勝者="DATA.txt"、バイト順による)、敗者"data.txt"はname_collisionステータスのまま追跡対象外。②ユーザーがOS上で"DATA.txt"(勝者)を削除する。③次回scanは物理名"data.txt"(敗者)のみを観測し、fold判定によりこれが引き続き論理名"DATA.txt"の系列への一致として扱われる(regularなreadable観測とみなされる)。④"DATA.txt"の真の削除は検出されず(delete判定はabsent観測を要するため)、代わりに"data.txt"の内容が"DATA.txt"の系列への「更新」として記録される誤り。 | §20.5/X29(free探索) | name_collisionの敗者が唯一の物理実体として残った場合を検出し、勝者の削除確定(delete判定)と敗者の新規独立系列化(create相当)へ正しく振り分ける規則を追加する。 |
| **L13** | §21.3 手順0「app 側には fork_in_progress = (old_id, 対象パス) を軽い印として記録し、この repo は tick の全ステップから除外し」 | 記録形式は(old_id, 対象パス)のタプルだが、除外条件の文言は「この repo」というid中心の表現になっている。手順3の旧行退役ガード(「対象パスが folders[old_id].root_path と一致する場合のみ」)は既にパス限定のロジックを採用しているのに対し、除外条件だけがそれと非対称。conflict解消のため非追跡側コピーをforkする通常運用では、tickのディスパッチ自体がrepository_id単位で行われるため、id一致のみで除外判定を実装すると生存側(追跡中の本来のフォルダ)まで誤って巻き込まれ得る。 | ①同一repository_id(R_OLD)を名乗る2つの物理フォルダ、FolderA(folders.root_path一致・追跡中・in-flightジョブあり)とFolderB(手動コピー由来・conflict状態)が存在。②conflict解消のためFolderBをfork(§21.3)実行、fork_in_progress=(R_OLD, FolderBのパス)を記録。③tickのディスパッチロジックが「fork_in_progress中のrepository_id」でrepository_id単位のフィルタを実装していた場合、R_OLDを共有するFolderA(生存側、fork対象ではない)のscan/submit/collect/replicateもまとめて除外され、L07/L08で記述したforkの停滞と組み合わさるとFolderAの処理が長期間止まり得る。 | §21.3/C10(z)/X22, X27 | 手順0の除外条件を「fork_in_progress の (old_id, 対象パス) タプルに一致する物理フォルダ(journal所在=対象パス)のみ」と明記し、「この repo」という表現を「対象パスのフォルダ」に修正する。 |

## Minor

| ID | 該当箇所 | 問題 | 根拠 | 修正案 |
|---|---|---|---|---|
| L14 | §11.2「横断検索は app_config の embedding_profile record から生成する」/ §21.5(app全損bootstrap限定)/ §21.7カタログ | app_config(tool_profile/embedding_profile)の**初回**投入手順が§21のどの明示操作としても定義されていない(§21.5は全損後bootstrap限定、§8は既存値の更新前提)。register直後、app_config未設定のままtickがOCR/Embed submitへ進んだ場合の挙動(該当ステップのみskip/tick停止/エラー)も未定義。4エージェントが独立に類似シナリオで検出。 | §10または§21.1に「app_config未設定時は該当kindのsubmit/collectをskipしstatusに『profile未設定』を表示、他ステップは継続する」旨を追記する。 |
| L15 | §21.3「派生台帳(markdown_documents/chunks/embeddings/profiles)とobjects/は保持する」 | fork後、非現在版のcontent_hashが持っていた派生は、file_versions側の対応行がCASCADE削除で消滅するため`selected_files`(全3モード共通)に二度と現れず検索から永久に到達不能になる一方、GC参照集合ルール2/3(markdown_hash/image_hash参照)により物理的には永久に保持され続ける。「保持できる」という字義は満たすが、検索不能・回収不能な永久ゴミという実質的価値の無い保持になる。 | fork完了時に非現在版content_hashの派生一覧をstatus報告するか、§21.6 drop-derivationを自動提案する。 |
| L16 | §9.1相2「原本upload(filenameにintent_tokenを埋め込む)」 | uploadファイル名が「元file_name+token」か「合成名+token」か規定されておらず、他の全識別子(chunks/markdown_documents/embeddings/custom_id)がfile_nameを内容アドレス系から意図的に切り離しているのと対照的に、この一文だけは元file_nameの流用を排除していない。社外秘プロジェクト名等を含む元ファイル名が第三者(Mistral)へfilenameとして送信され得る。 | 「upload filenameは合成名(例: hex(target_key)_intent_token)とし、元file_nameを含めない」と明記する。 |
| L17 | §8-c/e「不一致なら DROP → CREATE する」「不一致なら…破棄…してagg構築profileを現行へ更新してから」 | vec表のDROP/CREATE/差集合再充填、およびagg構築profileマーカー更新が単一Txで実行すべきとの明記が無い。文書が示す順序(実体操作→マーカー更新)を守れば安全に自己修復するが、明記が無いため順序を誤る実装(マーカー先行更新)だとハードエラー窓が生じ得る。 | 該当手順を「同一Tx(またはmetadata側の対応する単一Tx)で実行する」旨を明記する。 |
| L18 | §6「複数jobへ分割してよい」/ §9.1相1「job単位のintent_token」 | 1リポジトリのOCR対象がJSONL上限超過で複数jobに分割される場合の、行→job割当アルゴリズムとintent_token発行粒度(いつ・何個発行するか)が未規定。素朴な実装(全体に単一token)だと複数job間でtoken重複が生じ、intent回復の誤結合→output_missing誤判定→不要な再課金を招き得る。 | 「複数jobへ分割する場合は分割単位ごとに個別のintent_tokenを発行する」旨を§9.1相1に明記する。 |
| L19 | §9.1 detached規範(state=0即削除)/ §21.1再発見規則 | unregister直後(cancel未確定・detached化)に同一repository_idが即座に再registerされると、detachedのcollect処理(payload破棄+記帳)が先に完了しているか、通常行への復帰が先かのタイミング競合で、実質的に同一対象へのOCR/Embed二重投入(二重課金)が起こり得る。 | 再register時、直近でdetached化・削除されたtarget_keyの一覧を照合し、既に課金済み・破棄済みの対象があればstatusに明示する。 |
| L20 | §20.3「name はそのまま UTF-8 文字列として使い、Unicode 正規化はしない」/ §20.5「file_name は NFC 正規化した論理名として扱う」 | fp(段0、raw名)とscan_cache/file_versions(段1/2、NFC名)の変換点が、個別記述はあるが「readdir結果からいつ・どこで両表現に分岐するか」を橋渡しする一文が無い(暗黙にreaddir直後と読めるが明記なし)。 | 「readdir結果を取得した直後、fp計算にはraw値を、以降の全処理にはNFC正規化値を用いる」旨を明記する。 |
| L21 | §21「明示操作は最大 N 秒ブロッキングで待つ」 | busy_timeout・最小不在時間・猶予期間・時計閾値など他の全パラメータには既定値が示されるが、Nだけ数値が示されない。 | Nに既定値(例: 既定30秒)を明記する。 |
| L22 | 規約6「書き込み順序: objects/ → metadata.sqlite → app.sqlite」/ §7「floorの同時引き上げ…順序はapp→metadata」 | §7のfloor引き上げは明確に規約6の一般順序(objects→metadata→app)の逆(app→metadata)を取るが、規約6側からこの例外が参照・注記されていない。 | 規約6に「唯一の例外は§7のfloor引き上げ」等の注記を追加する。 |
| L23 | §9.1 batch_requests DDLコメント「target_key TEXT NOT NULL, -- kind=1: hex(content_hash) \|\| ':' \|\| hex(tool_profile_hash)」 | target_keyのhexは「小文字に固定」が全体規範(§11.2等)だが、このDDLコメントの一次提示はlower()なしのhex()表記。直後の注記で補足されるため実害は限定的。 | DDLコメントの一次提示から`lower(hex(...))`表記に統一する。 |
| L24 | §8「重複課金は attempts 上限による有界化に留まる」(client経路) | profile A→B→A→Bのように能動的・反復的にprofile変更を行うと、§8-a「profileが現行と異なる行の再投入はstateを問わずattempts=0にリセット」により、同一対象へのattempts上限が実質「profileごと」にリセットされ、「上限で有界」という保証がグローバルな上限ではなくprofileの往復回数に比例した緩い保証になる。ユーザーの能動的・反復的操作が前提のため実運用リスクは低い。 | 同一profile_hashへの再帰(A→B→Aの2回目のA)時はattemptsを維持する規則を追加する(optional)。 |
| L25 | §16「attempt単位なので月跨ぎretryも発生月へ正しく配賦される」/ §9.1「ts: 課金の確定(collect)時刻」 | 「発生月」という表現が「プロバイダが実際に処理・課金した月」を連想させ得るが、実装はcollect確定時刻(ts)であり、tickの実行間隔が長期間空いた場合(長期未起動等)は実際の処理月と乖離し得る。仕組み自体(1attempt=1台帳行)は正しいが期待値のズレを招く表現。 | 「発生月」を「collect確定月(=ts列の月)」と明記し、プロバイダ側の実処理月とは異なり得る旨を注記する。 |
| L26 | §9.1「detached 行の処理規範」導入文(unregister §21.2 / フォルダ消失 §9.3-d の2経路のみ列挙) | P9は「unregister §21.2 / §9.3-d / fork §21.3 の3経路とも同一規則」と定めるが、§9.1冒頭の規範導入文はfork §21.3を列挙していない(2経路のみ)。実体は§21.3が「§21.2と同一規則」と間接参照するため機能上の欠陥ではないが、列挙の網羅性のみの指摘。 | §9.1冒頭の経路列挙に「fork §21.3」を明示的に追加する。 |
| L27 | §9.1「profile_changed の破棄と記帳は同一 app Tx」/ 同節「terminal 化時の課金記帳」(result_expired/job_timeout/output_missing/job_missing対象) | 成功パス(collect kind=1のd)とprofile_changed破棄は明示的に単一Txとされるが、他4つのterminal理由(result_expired等)は「state=3 UPDATE」の記述と「cost_ledgerへ記帳する」の記述が別パラグラフに分離しており、同一Txであることが明記されていない。別Txの場合、state=3 UPDATE後・記帳前のクラッシュで記帳が永久に失われ得る(collectはstate=1のみ照会するため再訪不能)。 | 「terminal化時の課金記帳」パラグラフに「(state=3 UPDATEと)同一app Tx」の一文を明記する。 |

## Proposal

| 該当箇所 | 内容 |
|---|---|
| §6「1 ファイル 512MB」 | Office文書は変換後PDFがアップロード対象になるが、512MB判定を原本と変換後PDFのどちらに適用するか未規定。「実際にアップロードするバイト列に対して判定する」旨を明記すると親切。 |
| §21.4 restore | in-place復元のdelete版拒否は明記されるが、明示宛先(エクスポート)経由でdelete版キーを指定した場合の拒否がその文脈で独立に再掲されていない(content_hashがNULLのため実質的には自明で実害なし)。 |

---

# 第4部 — 確認済みの列挙

## C1〜C12 (検査観点)

| 観点 | 結果 |
|---|---|
| C1(原則反映) | P1〜P8, P10〜P16 は全箇条が現行文書に完全反映されていることを確認。P9のみ軽微な列挙漏れ(L26)。 |
| C2(SQL静的検証) | DDL構文・GENERATED列・WITHOUT ROWID/PK関係・FTS5 content rowid問題・trigger整合は全て健全。例外: agg_file_versionsの複合CHECK欠落(L03)。 |
| C3(相互参照整合) | 全§参照(§1〜§21.7、規約1〜12、§8 a〜e、§9.3 z/a〜d等)を機械抽出し検証、破損参照・番号混同は検出されなかった。**問題0件**。 |
| C4(クエリ-スキーマ整合) | selected_files/eligible/fts_hits/vec_hitsの列・joinキー整合、CTE定義列と使用箇所の一致を確認。例外: K02の残存誤記述(C9で計上済み)、agg_file_versions(L03)。 |
| C5(数値・事実一貫性) | $2.5/1,000ページ、+25%、768次元(参考値明記)、RRF k=60、8テーブル表記は全出現箇所で一致。**問題0件**。 |
| C6(用語・形式一貫性) | target_key連結形式・chunk_type/target_type対応・obj:スキーム・embed_hash定義は一貫。例外: L23(軽微)。 |
| C7(状態機械の完全性) | コア状態機械(state 0-3×成果あり/なし)は網羅的で収束経路を追跡できたが、detached経路(L01)とsubmit_rejected(L02)に実質的な穴を検出。 |
| C8(欠落チェック) | P1〜P16の範囲で章立てが丸ごと欠けている事項は無い。**問題0件**。 |
| C9(回帰確認) | 第1部参照。205項目中204がfixed/superseded、1件(K02)がpartially-fixed。 |
| C10(修正が開けた穴 a〜z) | 大半の相互作用点は整合。例外: (i)(L20), (m)(v)(K02関連), (n)(L05), (q)(軽微・finding化せず), (w)(L14), (z)(L07/L08)。 |
| C11(実装可能性) | §6/§9.1/§10/§20/§21の大半の手順は追加設計判断なしに実装可能。例外: L01, L09(detached/client-path分岐)、L21(N秒既定値)、L22(規約6例外注記)、proposal 2件。 |
| C12(探索型監査) | 80シナリオ実行、X1〜X30全観点+自由探索4件。fatal 1・major 12・minor 14を検出、20件の明示的反証試行は(K02関連を除き)すべて「破れず」。 |

## P1〜P16 (設計原則)

P1(三層構成)/P2(識別子規範)/P3(8テーブル)/P4(chunks統一)/P5(チャンク分割)/P6(OCR)/P7(FTS)/P8(Embedding必須)/
P10(書込順序と冪等性)/P11(集約)/P12(検索)/P13(GC)/P14(SQLite設定)/P15(不変部分)/P16(変更検知) —
全箇条が現行文書に反映されていることを個別に確認済み(担当エージェントによる逐条照合、C1参照)。

P9(バッチ処理情報の分離)は中核規範(2相submit・状態遷移・cost_ledger分離・app_config・detached規範)は
すべて反映されているが、C7で述べたdetached/submit_rejectedの実装可能性ギャップ(L01, L02)がP9の
「損失は有界」という主張の一部を実質的に破っている。

---

# 付録: 監査プロセスに関する所見

1. 本レポートは監査プロンプト自身の指示に従い、C9のsupersededマッピング表を各C9担当エージェントに
   提供した上で判定させた。うち1件(J13→K16)は担当エージェントが「マッピング表の対応が本文の実際の
   関連性と一致しないのでは」と指摘した(J13自体は直接照合でfixedと判定済みのため結論には影響しない)。
   次回監査プロンプト改訂時に当該マッピング行の妥当性を見直すことを推奨する。
2. C9担当エージェント3本(r5/r6班、r7班)が既知マッピング表に無いsupersede関係を自己特定した
   (F10→H08、I32→J18相当)。両者とも実テキストを直接確認した上での判定であり、根拠は妥当と判断した。
3. 探索型監査(第2部)は80シナリオを実施し、要求される35シナリオを大幅に上回った。X26・X27(fork関連)・
   X28〜X30(detached・case規則・反証探索)の重点領域から特に多くの major 級の新規検出(L01, L02,
   L07〜L13)が得られており、監査プロンプト自身の想定(「r10の重心はX26〜X30、fixが開ける穴の定番パターン」)
   が的中した。
