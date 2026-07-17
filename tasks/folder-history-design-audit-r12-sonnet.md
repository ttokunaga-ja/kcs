# folder-history 設計書 r12 監査報告 (Claude Sonnet 5)

対象: `docs/research/folder-history-sqlite-design.md` (2,476 行、2026-07-15 実行)
監査方法: ファイルを行番号付きで全文読了 (offset 分割 5 回)、grep による数値・用語一貫性の
機械的検証、r10/r11 の全報告 (Sonnet 2 本・Fable 2 本・独立セッション 1 本・裁定 1 本) を先読みして
既知の欠陥クラスタと決着済み事項を把握した上で、C9 262 項目を個別に行番号引用で再検証し、
C12 探索型監査を X36〜X40 に重心を置いて実施した。

## 判定: **不合格**

- 前提条件: **充足** — 探索ログ 68 シナリオ、X1〜X40 の全観点 (X15/X20/X24/X30/X35/X40 の
  反証チェックポイントを含む) に最低 1 件以上を実施
- C9 回帰: **262 項目すべて fixed または superseded** (対応表どおり。regression・not-fixed 0 件)
- 新規検出: **fatal 0・major 4・minor 5・proposal 0**
- 不合格事由: C9 は基準を満たすが、新規検出に major が 4 件あるため「fatal/major 0 件」を満たさない

---

## 第 1 部 — 回帰確認 (C9)

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 /
J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29: すべて fixed または superseded (対応表どおり)。
partially-fixed / not-fixed / regression は 0 件。**

r10 (Sonnet・Fable 各 1 系統) と r11 (6 系統・裁定済み) が A01〜L28 を収束させたことは
`tasks/folder-history-r11-adjudication.md` の裁定記録で確認済みであり、本ラウンドはこれを鵜呑みに
せず M01〜M29 (r11 で新規に確定した必須+推奨修正) を対象文書の現物から行番号を引いて独立に
再検証した。以下はその実施記録 (代表項目。全項目を同水準で確認済み):

| ID | 判定 | 根拠 (§ + 短い引用) |
|---|---|---|
| M01 | fixed | §9.1 L928-931, L961-971, L1010-1011 — 「この記帳、および collect 成功 / reconcile・submit の close / client_exhausted / detached の cost_ledger 追記はすべて冪等に行う」が 5 経路を明示列挙 |
| M02 | fixed | §21.2 L2278-2281 「state=0 も §9.1 の client / server 分岐に従う…「state=0 は即削除」は不可」 |
| M03 | fixed | §9.1 L798-811 app_config DDL コメントが 5-key (tool_profile/embedding_profile/image_filter/retry_not_before/agg_building_profile_hash/agg_ready_profile_hash) を列挙。grep で旧単一キー 0 件 |
| M04 | fixed | §13 L1672-1676, L1694-1697 「profile 破損の誘導は kind 別…「明示再生成(§5.3)」は…embedding の修復には使えない」。L1680-1681 の汎用文は "(Markdown/画像)" と明示的に object 層のみへ限定されており矛盾しない |
| M05 | fixed | §21.3 L2352-2357 (realpath 実体現存要件) / §20.4 L2060-2062 (fork_in_progress 除外) / §21.3 L2363-2367 (commits 非空→手順1) の 3 要件すべて現存 |
| M06 | fixed | §9.1 L989-993 「実在すれば通常の intent 採用と同一の UPDATE (state=1+batch_job_id+attempts+1+submission_seq+1+submitted_at)」 |
| M07 | fixed | §8 L669-675 「投入時 profile の snapshot (kind=2 は profile_hash=現行、kind=1/2 とも profile_record=現行 record)」 |
| M08 | fixed | §20.5 L2120-2125 「§20.4 と同じ lstat + O_NOFOLLOW + regular 判定…「存在すれば中止」の素朴な stat は不可」 |
| M09 | fixed | §8-e L636-647 (building/ready 2-key・§9.3-c 完了判定・missing 除外) / L653-657 (agg_vec 差集合冪等再充填) / §13 L1677-1679 (fsck が agg 差集合検査) |
| M10 | fixed | §5.6 L392-397 (`<metric>` テンプレート) / §8-c L621-623 (次元と距離の両方照合) |
| M11 | fixed | §21.1 L2238-2241 「その旧行を先に §9.3-d で退役してから本 repository_id を INSERT する」 |
| M12 | fixed | §8 L691-697 (app_config 永続化) / §21.5 L2435-2438 (bootstrap 再入力) |
| M13 | fixed | §21.1 L2222-2226 「存在」と「可読性」を分離し一時読取不能は保留 |
| K/L/M16/N/O/S/M15/M17/M26/M35/M30 | fixed | 個別に行引用で確認 (item失敗記帳 L963、collect retry_not_before 永続化 L919-921、§16 文言更新 L1824-1825、chunks CHECK L313-317、agg_file_versions CHECK L1105-1110、journal digest L2310-2313、LIKE fallback 両列 L1576-1587、query_profile_hash 固定 L1550-1559、float32 LE L371-375、:limit 契約 L1598-1600、query embed 失敗→FTS-only L1557-1559) |
| M27/M16c/M25/M19 (任意採用) | fixed | alt エスケープ L502-505、後退検出時の cache 無効化 L1215-1219、invalid_output 区別 L958-960、dirfd 束縛 L2090-2092 |
| G (fork 中二重課金) | fixed (明記のみの解決) | §21.3 L2380-2386 「意図されたコストである」と明記 |
| R1-M01 (unregister tombstone) | fixed (降格・doc明確化) | §21.2 L2287-2291 「再発見の恒久抑止ではない…再 OCR / re-embed は…発生せず」 |

追加で grep による機械検証を実施し、以下がすべて一致 (不一致 0 件) であることを確認した:
`agg_embedding_profile_hash` 旧単一キーの残存 0 件、監査番号 (P9 等) の自己参照 0 件、
「7 テーブル」の誤記 0 件 (「8 テーブル」で統一)、`$2.5`/`$5`(+25%)/`$4` の整合、RRF k=60 の整合、
`lower(hex(...))` の整合、`image_filter` 既定 OFF の整合、猶予 30 日の整合、`k_max`/4,096 の整合。

---

## 第 2 部 — 探索ログ (C12) — 68 シナリオ

重心: X36〜X40 (r11 修正の相互作用・ready 完了追跡・fork 回復拡張・register/detached 周辺・
反証+保留エッジの再評価) — 68 件中 33 件をここに配分。

### X1〜X35 (簡易確認 — 各 1 件、現物の行番号で個別に再確認)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 1 tick 間に create→edit→delete → 単一 walk は最終状態のみ観測、中間版は不可視のまま pending_deletes 経由で数 tick 後に delete 確定 | 問題なし (周期スキャン設計の必然的丸め。§20.5 L2110-2119) |
| 2 | X2 | ファイル名に "obj:" や "<!--" を含む物理ファイル名 (パス区切り等は無し) → name_invalid 対象外だが Markdown grammar は content_hash ベースで file_name を埋め込まないため無害 | 問題なし |
| 3 | X3 | macOS NFD readdir → NFC 論理名で単一系列 | 問題なし (L2133-2137) |
| 4 | X4 | 同一 created_at の並行コミット → commit_hash DESC でタイブレーク決定論的 | 問題なし (L221, L1409-1411) |
| 5 | X5 | 10 万ファイル walk → 段 1 全行比較で個人規模なら十分、§19 に規模再考条件 | 問題なし |
| 6 | X6 | 日本語 2 文字「検索」→ trigram 沈黙 → LIKE fallback (bind 分離・instr(lower)) | 問題なし (L1572-1587) |
| 7 | X7 | grammar v 混在期間の解析 → v 列読み取りで版別 dispatch、専用列不要 | 問題なし (L509-518) |
| 8 | X8 | restore 宛先に `../evil` → file_name 検証 + 正規化 join で拒否 | 問題なし (L2402-2403) |
| 9 | X9 | ディスク満杯を objects/metadata/app の各書込点で発生 → 差集合駆動で次 tick 収束 | 問題なし |
| 10 | X10 | zip 往復 (mtime/inode 全変化) → content_hash 同一で無コミット | 問題なし (L2098-2099) |
| 11 | X11 (r6相互作用の再確認) | fp の非正規化 name (§20.3) と file_versions の NFC 論理名 (§20.5) の変換点 | 問題なし (walk 観測時の 1 点に閉じる) |
| 12 | X12 | register→discover→scan→OCR→chunk→embed→replicate→検索→原本解決→履歴→復元の一気通貫 | 問題なし (各段の入出力が前段の出力と一致することを§ごとに追跡) |
| 13 | X13 | 「status表示」「明示操作」等の総点検 | 問題なし (§21.x のいずれかに具体的手順が定義済み) |
| 14 | X14 | submit 429 と collect 429 の両方で retry_not_before 永続化 | 問題なし (L880-882, L919-921 — 対称) |
| 15 | X16 | 2 相 submit + JSONL 分割 (1 job = 1 repository) と intent_token 粒度 | 問題なし (job 単位で独立に回復) |
| 16 | X17 | register 手順 2 途中クラッシュ→damaged→再実行 | 問題なし (L2254-2261、原本非接触で再実行安全) |
| 17 | X18 | profiles 孤児行 | 問題なし (§18.7 で意図的に非掃除と明記、fsck は孤児無関係に全行検証) |
| 18 | X19 | dir fsync 適用点の網羅 (objects 各 prefix・tmp・fork journal) | 問題なし (fork 手順 2 の「安全書込」表現は §20.5 の規律を暗黙参照するのみで minor 相当、finding化せず) |
| 19 | X21 | 相 1 の profile_hash/upload_cleaned リセットと intent 回復 (snapshot 不変) の整合 | 問題なし (X36 で深掘り済み) |
| 20 | X22 | defer_foreign_keys と foreign_keys=ON・journal DELETE の相互作用 | 問題なし (L2324-2328 に根拠明記) |
| 21 | X23 | detached×profile 不一致×status 表示 | 問題なし (L998-999 で通常経路から明示的に除外) |
| 22 | X25 | app.sqlite 単独での横断検索クエリ embedding 生成経路 | 問題なし (L822-826 app_config が経路) |
| 23 | X27 | fork journal の全境界クラッシュ再開 | 問題なし (X38 で深掘り、ただし完了時の path 束縛に別 finding あり) |
| 24 | X28/X29 | detached 全ライフサイクル / 保存名固定の case-sensitive 移動後の共存 | 問題なし (X39/X40 で深掘り) |
| 25 | X31〜X33 | submission_seq×attempts×ledger 三者・課金記帳網羅行列 | 問題なし (X36 で深掘り) |
| 26 | X34 | §11.2 完全 SQL の組立実行可能性 (eligible×agg_chunks 再JOIN・at_hash=FF 等) | 問題なし (現物の SQL 断片を通しで読み、列・キーの整合を確認) |
| 27 | 自由 (X9関連) | .folder-history 手動編集中の同時 tick 実行 → tick.lock が排他 | 問題なし |
| 28 | 自由 (X10関連) | 同期ソフトによる .folder-history 内 SHM/WAL 相当ファイルの部分同期 → journal_mode=DELETE で回避 (§14) | 問題なし |
| 29 | 自由 | annotation transcription に Markdown 特殊文字混入 → 1 行正規化+エスケープで無害化 | 問題なし |
| 30 | 自由 | 大量 chunk (100万規模) での agg_chunks 全置換頻度 | 問題なし (§19 に規模再考条件が明記済み) |
| 31 | 自由 | UUIDv7 の時刻依存性と時計後退の相互作用 | 問題なし (repository-id は識別のみに使用、時系列比較には created_at 系列を使う設計のため無関係) |
| 32 | 自由 | Mistral Batch 1 job あたり行数上限と分割時の custom_id 一意性 | 問題なし (L1310-1312 「repo を跨ぐと衝突」に対応し 1 job=1 repo で維持) |
| 33 | 自由 | JCS の i64 超の値 (options 内整数) | 問題なし (L156-157 「2^53 超があり得る整数は 10 進文字列」を profile_record options にも適用と明記) |
| 34 | 自由 | 新旧アプリバージョン混在で同じ DB を開く | 問題なし (L1727-1728 user_version fail-closed) |
| 35 | 自由 | canonical img block grammar 自体の将来変更 (grammar version 無し疑義) | 問題なし (v フィールドが present、L509 で明示) |

### 反証チェックポイント X15/X20/X24/X30/X35 (各ラウンドの主張・試行・結果を明示記録)

これらは r6〜r10 の各監査ラウンドで指定された反証観点であり、対象文書は既にそれ以降の修正
(H〜L, M) を織り込んでいるため、当時の主張を**現行の文書表現**に読み替えて再試行した。

| # | 観点 | 主張 (試行内容) | 結果 |
|---|---|---|---|
| 36 | X15 | 「同一の正規化コミット → 同一の commit_hash」(§4.1) — nonce/device_id を含まない直列化のもとで、2 台の端末が独立に同一変更セットを生成した場合に hash が分岐する余地を探索 | 破れず (JCS 直列化 + 固定フィールド集合により端末固有情報が入力に一切現れない) |
| 37 | X20 | 「重複課金は intent 回復により最悪 job 1 回分に有界」(§10) — server 経路で相 2b 直後・相 3 直前のクラッシュを反復させ、intent_token 突合による採用が毎回正しく単一 job に収束するかを試行 | 破れず (§9.1 intent 回復の dispatch が token 一致を優先し、載せ直しは token 残骸削除後の新規 1 本のみを生む) |
| 38 | X24 | 「agg 毎 tick 検査は一度きり破棄の喪失を吸収する」(§8-e) — 次元一致のまま distance のみ異なる profile 切替を agg 側で反復させ、差集合再充填が半端な破棄状態からも収束するかを試行 | 破れず (§8-e が次元と距離の両方を検査するため distance 単独差も確実に検出され、差集合再充填はクラッシュ位置を問わず次 Replicate で残りを埋める) |
| 39 | X30 | 「detached は課金を取りこぼさない」(r10 改訂後) — detached の state=0 (server, job 一覧に実在) を発見・採用する経路で、採用と同時の記帳が二重にならないかを試行 | 破れず (M06 の採用 UPDATE が submission_seq を正しく増分するため、以後の close が旧 lifecycle と衝突しない。ただし X36 で検出した N01 は「採用」ではなく「終端後・削除猶予中の再登録」という別分岐であり、この主張自体は反証されない) |
| 40 | X35 | 「fork は id=old からでも journal で正しく再開する」(r10 改訂後) — HISTORY_CLEARED かつ id=old のクラッシュから、commits 非空・空の両ケースで再開手順が一意に定まるかを試行 | 破れず、ただし隣接して N02 (完了時の root_path 束縛先未規定) を検出。再開手順自体 (どの手順から始めるか) は一意に定まる |

### X36 (冪等記帳×seq継承×detached採用seq+1の三者相互作用 — 重心)

| # | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|
| 41 | profile A→B→A 往復で同一 target が collect の profile_changed close (seq=n) と後続 reconcile close (同 seq=n) の両方から記帳を受ける (r11 fatal F1 の再現条件) → ON CONFLICT DO NOTHING が「同一課金事実の再観測」として吸収し close Tx が進む | 問題なし (F1 修正が意図どおり機能) |
| 42 | 全 seq 書込点 (相3・intent回復server採用・client前計上・detached server採用) の悉皆点検 → tool_changed 却下枝だけは意図的に seq 不増分 (この分岐では実際に job が作られていないため課金事実が無い) | 問題なし |
| 43 | **unregister→detached(state=1) が cancel 未確定のまま collect で終端 (payload 破棄・state=2・seq=n で記帳) → 削除猶予中 (upload掃除完了+terminal だが「次 tick の collect 冒頭」まで削除されない約1tick窓) に repository を再登録** → 行は動的定義により即座に detached でなくなる → embeddings 行は無い (payload 破棄済み) のに state=2 → 「成果なし・state=2→投入対象」規則で自動再投入 → 新 seq で正当に再度課金 | **N01 検出** (詳細は第3部) |

### X37 (ready 完了追跡の全数トレース — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 44 | P1→P2 切替直後の synced_profile_hash 陳腐化 (旧 P1 値が残存) が ready を誤って true にしないか | 問題なし (等値判定が新 building 値に対してのみ真になるため、陳腐化値は安全側に「未同期」と解釈される) |
| 45 | 次元・距離が偶然一致する P1→P2 モデル切替 (§8-c/§8-e の dim+distance 検査だけでは検出できない) が旧空間ベクトルの混入検索を許すか | 問題なし (§8-a の成果判定と検索時ゲート (agg_ready_profile_hash・単独検索の全行一致) はいずれも **完全な profile_hash** で判定するため、vec0 の DROP/CREATE 判定が粗くても検索結果への混入は阻止される) |
| 46 | ゼロフォルダ (登録フォルダ 0 件) での ready 全称条件の空虚な真 | 問題なし (0 件の index は 0 件を返すのみで実害なし) |

### X38 (fork 回復拡張の全数トレース — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 47 | 手順1 (HISTORY_CLEARED) 直後クラッシュ→フォルダ物理移動 /A→/B→次 bootstrap/walk が /B で journal 発見→「id=old→手順2から」再開→repository-id を Rnew へ書換→手順3 (folders 退役+新規INSERT) | **N02 検出**: 新 folders 行の root_path に journal の凍結 realpath ("/A") を使うか今回の発見場所 ("/B") を使うかが未規定 (詳細は第3部) |
| 48 | fork_in_progress のパス単位除外がフォルダ移動で「無効化」され、通常 tick が旧 id で新規コミットを積み続けた場合の commits非空判定→手順1やり直しの安全性 | 問題なし・ただし網羅性は「walk と回復優先度が Step 0 内で同一パスに対して不可分に処理される」という設計前提に依存 (実装がこの順序を誤ると本来防げるはずの追記が起こり得るため、finding化はせず探索ログにのみ記録) |
| 49 | journal digest 不整合検出時の damaged 遷移と、fork_in_progress フラグ自体の整合性 (フラグは残るが journal だけ壊れた場合) | 問題なし (「journal が残る側は無害」 L2343 によりフラグ孤立は起きない) |

### X39 (register/detached/検知周辺の相互作用 — 重心)

| # | シナリオ | 結果 |
|---|---|---|
| 50 | detached state=1 (真に in-flight、まだ終端していない) 中に再登録 → 動的定義で即座に非 detached 化 → reconcile はスキップ (state=1) → collect が通常経路で正常に処理・書込 | 問題なし (X36 の finding とは異なり、こちらは payload が捨てられる前に折り返すため無害) |
| 51 | M11 (同一 root_path 別 id 退役) が新規登録の副作用として発火する際も detached 保存規則を正しく守るか | 問題なし |
| 52 | **M28 (dirfd 束縛による TOCTOU 対策) の適用範囲が §21.4 restore・§13 fsck の書込にのみ明記され、fork §21.3 自身の書込 (journal tmp書込・repository-id 書換え) には明記が無い** — fork の書込対象は規約12 で検証済みの root であり、同じ TOCTOU 窓 (root 途中成分の swap) に等しく晒される | **N03 検出** (詳細は第3部) |
| 53 | §21.2 の detached state=0 が §9.1 の client/server 分岐に本当に委譲しているか (M02 修正後の文言) | 問題なし (L2278-2281 で明示委譲済み、旧「即削除」の文言残存なし) |

### X40 (反証探索 7 件 + 保留エッジ再評価 6 件 — 重心)

| # | 主張 (試行内容) | 結果 |
|---|---|---|
| 54 | 「冪等記帳で close Tx abort は構造的に不可能」— 同一 seq へ異なる値 (推定 vs 実額) を書く 2 者が競合し ON CONFLICT DO NOTHING が誤った (古い) 値を恒久化する経路を探索 | 破れず (同一 seq を共有するのは常に同一 attempt の再観測のみで、値の食い違いは生じない) |
| 55 | 「ready は空/部分 index を通さない」— 新規フォルダ登録が ready 判定の母数に追いつくタイミングのズレを探索 | 破れず (毎 Replicate で folders を都度クエリするため陳腐化しない) |
| 56 | 「fork 中フォルダ移動でも未完 fork は通常運用へ復帰しない」— 復帰そのものは阻止されるが、完了時の path 束縛に隣接した未規定分岐あり (→ N02) | 破れず (厳密な主張自体は成立、隣接の別問題として N02 を計上) |
| 57 | 「一時読取不能で既存履歴は破壊されない」— 新規初期化が中断された場合の damaged/一時失敗の境界を追加確認 | 破れず (再実行が常に安全という前提でカバーされる) |
| 58 | 「delete 最終確認は対象外型置換を見逃さない」— 最終確認自体が一時 I/O 障害を起こした場合の三値分岐 | 破れず (skipped=保留が明示されている) |
| 59 | 「query_profile_hash 固定で embed 中 profile 変更の TOCTOU は不可能」— P1→P2→P1 の 2 度切替を embed 呼出中に挟む敵対的シナリオ | 破れず (空間の等値性判定であり履歴非依存のため往復後も正しい) |
| 60 | 「vec の距離変更は必ず DROP→CREATE される」— distance_metric のみを profile_hash 不変のまま変える経路の有無 | 破れず (distance_metric は §4.1 で profile_hash の入力に含まれるため単独変更が構造的に不可能) |
| 61 | 保留エッジ: standalone (単独フォルダ) read が規約12 (repository-id 照合) を通るか | **N04 検出** (規約12 の文言が「書き込む・レプリケーションする」操作に限定、read は対象外) |
| 62 | 保留エッジ: restore が論理名 (NFC) から現在の raw 物理名へ逆解決するか | **N05 検出** (非正規化非対応 FS では NFD 実体との不一致で in-place 上書きに失敗し得る) |
| 63 | 保留エッジ: drop-derivation + backfill ON が過去版を再 OCR しないか | **N06 検出** (backfill は現在版限定の注記を無視して過去版参照分も自動再投入する) |
| 64 | 保留エッジ: code fence (```` ``` ```` / `~~~`) 内の `#` の解析仕様 | **N07 検出** (フェンス認識規則自体が未規定) |
| 65 | 保留エッジ: §2 の app 全損要約が規約 7-f を反映するか | **N08 検出** (§2 要約が (f) を欠落) |
| 66 | 保留エッジ: case-insensitive→sensitive のボリューム間移動での系列の扱い | 問題なし・軽微 (発生元 FS が insensitive である以上、真の衝突ペアは構造的に生じ得ないため実害限定的。finding化せず) |

### 自由探索

| # | シナリオ | 結果 |
|---|---|---|
| 67 | annotation 由来テキストへの grammar 偽装混入 (§2 相当の 2 層防御の再確認) | 問題なし |
| 68 | **§9.3-z (後退検出) が tick の最終ステップ (Step 5 Replicate) にあるため、同一 tick の Step 0〜4 (scan・OCR submit/collect・Embed submit/collect) が「後退した metadata」に対して先に実行されてしまう窓** — バックアップからの復元 (§13 が推奨する正規の DR 手順) 直後の最初の tick で、scan_cache が app.sqlite 側 (フォルダ単位の復元では touch されない) に残ったままだと Step 0 が「変更なし」と誤認し、Step 1 (OCR submit) が「巻き戻った current 版」を対象に実課金の再投入を行い得る。Step 5 の z 検出はこの浪費を事後にしか止められない | **N09 検出** (詳細は第3部) |

---

## 第 3 部 — 新規検出 (C1〜C8, C10〜C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| N01 | minor | §9.1 detached 規範 (L977-999) と §21.3 fork の課金注記 (L2380-2386) | fork の in-flight 二重課金は「意図されたコスト」として明記される (L2380-2386) が、構造的に同型の「unregister→detached で state=1 が collect により payload 破棄+終端 (state=2, ledger 記帳) された直後、削除猶予窓 (terminal+upload清掃済みでも次tickのcollect冒頭まで削除実行されない約1tick) の間に再登録される」ケースは同種の二重課金 (再投入による実課金の再発生) を生むにもかかわらず §21.1/§21.2/§9.1 のどこにも意図されたコストとして記載されていない | 初期状態: repo R, target T (kind=2) が state=1 in-flight。操作列: (1) unregister(R) 実行、cancel 未確定のため T は detached として残置 (2) 次 tick の collect (step4 冒頭) が job 完了を検出、payload 破棄+state=2+cost_ledger 記帳 (seq=n) (3) 同ティック内の削除判定は「upload掃除(4.5)完了」を前提とするため T はまだ削除されない (4) この窓で register(R) を再実行、folders(R) が再挿入され T は動的定義により即座に detached でなくなる (5) 次 Embed submit が「成果なし(embeddings行なし)・state=2→投入対象」規則で T を自動再投入し、新 seq=n+1 で正当に(しかし利用者から見れば予期しない形で)再課金する | P9, C7, C11(c), X36, X28 | §21.1/§21.2 に、fork の課金注記 (L2380-2386) と同型の一文を追加する: 「unregister 後 detached のまま終端し削除猶予中に再登録された場合、破棄済み payload の分は自動的に再投入・再課金される。これは detached モデルの意図されたコストであり、fork の in-flight 二重課金と同種のトレードオフである」 |
| N02 | major | §21.3 fork の失敗回復手順 (L2351-2378)、特に手順 3 の folders INSERT (L2334-2340) | fork のクラッシュ回復が「移動先で journal ごと発見する」(L2356-2357) ケースを明示的にサポートするにもかかわらず、回復完了時 (手順 3 の folders(new_id) INSERT) に書き込む root_path の値が未規定。journal の `realpath` フィールドは fork 開始時に一度だけ固定されるスナップショットであり (L2301-2303, L2308-2309)、移動後は物理的に誤った値になっている。実装者は「journal の凍結値」と「今回の発見場所」のどちらを使うべきか、文書からは追加の設計判断なしに一意に導けない | 初期状態: fork 開始、journal={old_id=Rold, new_id=Rnew, realpath="/A", phase}。操作列: (1) 手順1 実行 (commits 全削除)、phase→HISTORY_CLEARED (2) ここでクラッシュ (3) アプリ停止中に利用者がフォルダ全体を /A → /B へ移動 (4) 次回起動時の bootstrap/walk が /B で fork-journal を発見、「id=old→手順2から」再開: repository-id を Rnew へ書換え (5) 手順3: folders(Rnew) を INSERT — この時、実装が journal の realpath="/A" をそのまま書き込むと、直後の folders(Rnew).root_path="/A" は現実に存在しない (フォルダは /B にある) ため、次回の起動時点で即座に missing 状態に陥り、30 日猶予・再発見を経て自己修復するまで無用に retired 経路へ近づく。壊れる状態: 「たった今 /B で発見して回復処理をしている当のフォルダ」が、回復完了直後に「見失った」状態として記録される | C7, C11(a), X38, X27, X32 | 手順 3 の folders INSERT には明示的に「root_path = 今回の回復処理が journal を発見した実際のパス (journal の realpath フィールドではなく、当該 walk/bootstrap が観測した現在の場所)」と明記する。journal の realpath フィールドは識別・除外判定専用であり完了時の root_path 源ではないことを注記する |
| N03 | minor | §20.5 の M28 ハードニング注記 (L2090-2092)「restore §21.4・fsck §13 の書込にも適用」 | 規約12 で検証済みの root に対する dirfd 相対書込 (openat/RESOLVE_BENEATH 相当) の適用範囲列挙が restore と fsck のみで、fork §21.3 自身の書込 (手順0 の journal tmp 書込・手順2 の repository-id 書換え) が明示的に含まれていない。fork の書込対象は同一 repository-id conflict の検出 (規約12 相当の判定) を経て初めて着手されるものであり、restore/fsck と全く同じ「照合〜使用の間に root の途中成分が swap される」TOCTOU 窓に晒される | 該当箇所を読んだ実装者が「列挙されているのは restore と fsck だけだから fork の書込は素朴な O_NOFOLLOW (最終成分のみ) で足りる」と解釈すると、fork 実行中に root の途中パス成分が別実体へ差し替えられた場合に fork の journal/repository-id 書込がフォルダ外を書き換える窓が残る (基本の tmp→fsync→rename→dir fsync 規律自体は保たれるため即座の破損ではないが、防御層が一つ欠ける) | C3, C11(d), X39, X19 | M28 の適用範囲列挙に「fork §21.3 の手順0 (journal 書込) および手順2 (repository-id 書換え)」を明示的に追加する |
| N04 | major | §15 規約12 (L1800-1803)「フォルダ DB を開いて**書き込む・レプリケーションする**全操作は…repository-id を…照合し…」 | 規約12 の文言が明示的に「書き込む・レプリケーションする」操作に限定されており、単独フォルダに対する読み取り専用操作 (§11.2 のフォルダ単独検索マッピング) がこの照合を要求されない。規約12 は文書内で唯一の「管理 identity 差し替え」検出点として位置づけられている (§20.4「この照合が管理 identity 差し替えの検出点になる」) にもかかわらず、読み取りだけがこの検出網から漏れる | 初期状態: 同一 repository-id を持つフォルダの物理コピーが 2 箇所に存在する conflict 状態 (§20.4 で status 表示・fork 待ち)。操作列: (1) 利用者 (またはツール) が conflict 未解決のまま、canonical でない側のコピーに対して直接「フォルダ単独検索」(§11.2 のローカルマッピング) を実行する (2) 規約12 の照合は書込/レプリケーション限定のため作動せず、検索は何の警告も無く実行される (3) 結果は plausible に見えるが、app 側の `folders` テーブルが追跡している「正規の」コピーとは異なる内容 (収束が古い・分岐している等) から返る。壊れる状態: 利用者が conflict の存在を検索結果からは一切知り得ないまま、誤った provenance のデータを正規の履歴だと信じて原本ファイルを開く・共有する等の下流操作に進む | P1, C1, C11, X40, X29 | 規約12 の文言を「フォルダ DB を開いて参照する全操作 (読み取り専用の単独検索・原本解決を含む)」まで拡張するか、少なくとも単独検索の実行手順 (§11.2 の mapping 節) に「実行前に規約12 の照合を行う」旨を明記する |
| N05 | minor | §21.4 restore 手順 (L2396-2410)、§20.5 の NFC 論理名規則 (L2133-2137) | file_versions.file_name は NFC 正規化済みの論理名で保存される。in-place restore (手順 3a) はこの NFC 名で宛先へ書き出す。正規化非依存の lookup を行わない一部のファイルシステム (Windows NTFS・多くの Linux ファイルシステム) では、対象がすでに NFD 形式の物理名で存在する場合、NFC バイト列での書込は既存の NFD 実体を上書きせず、別個の新規エントリを作成し得る (macOS の APFS/HFS+ は API レベルで正規化非依存 lookup を行うためこの不整合は生じない) | 初期状態: cross-platform 同期等により、あるファイルが NFD 形式の物理名 (例: "Repórt.pdf") で Windows/Linux ボリューム上に存在し、file_versions には対応する NFC 論理名 ("Report.pdf") で履歴が記録されている。操作列: (1) 利用者が過去版の in-place restore を実行、file_name="Report.pdf" (NFC) を宛先として書込 (2) NTFS/多くの Linux FS は正規化非依存でないため、この書込は既存の NFD 実体とは別の新規ファイルとして作成される。壊れる状態: 復元後、同一論理ファイルの物理実体が NFC 版と NFD 版の 2 つ並存し、次回スキャンで name_collision または偽の 2 系列化を誘発し得る | C11(a), X40, X29, X3 | restore の in-place 書込時、対象ボリュームが正規化非依存 lookup を行わない場合は書込前に NFD 等価表記の既存エントリの有無を確認し、存在すればそちらを対象にする (または既存エントリを削除してから書込む) 旨を明記する |
| N06 | major | §21.6 drop-derivation の注記 (a) (L2461-2463)「原本が健在で**現在版**なら…自動的に再投入する」、§10 step1 backfill (L1313-1318) | drop-derivation の利用者向け説明は「現在版」の自動再投入のみに言及するが、実際の再投入駆動力である §10 step1 の backfill (既定 ON) は「現在版に無いものを低優先で同様に投入する」 (all_versions 差集合) ため、drop 対象の (content_hash, tool_profile_hash) が **過去版のみ**から参照されている場合でも、backfill が「成果なし」を検出して自動的に再 OCR (実課金) を発火させる。この帰結は drop-derivation の説明のどこにも記載が無く、利用者は「不要な派生を捨てる」つもりの操作から予期しない再課金を受け得る | 初期状態: ファイル F の過去版 v1 (content_hash=H) が存在し、現在版は v2 (別 hash) に進んでいる。H は既に OCR 済みで markdown_documents 行を持つ。backfill は既定 ON。操作列: (1) 利用者が (folder, H, tool_profile_hash) に対して drop-derivation (§21.6) を実行、意図は「このバージョンの派生は要らないので消す」 (2) markdown_documents 行が DELETE される (3) 次 tick の step1: backfill が all_versions の DISTINCT content_hash 差集合から H を「成果なし」として検出 (現在版チェックとは無関係に past-version 由来で候補になる) (4) H が自動的に再 OCR キューに投入され、実際に再課金される。壊れる状態: 利用者は「明示的に捨てた」派生が数分後に何もしていないのに勝手に(有料で)復活するのを目撃する | P6, P9, C10(n), C11(c), X40 | §21.6 の注記 (a) を「現在版**または backfill 設定 ON 下で過去版から参照される場合**、drop 直後から自動的に再投入される」と修正し、意図的に恒久除去したい場合は「対象を unregister するか原本を退避する」に加えて「backfill を OFF にする」または「該当ファイルの過去版を drop 前に削除する」等の代替経路を明記する |
| N07 | minor | §7 チャンク分割規則 1 (L544-545)「コードフェンス内の # は見出しと見なさない」 | コードフェンスの認識規則そのもの (```` ``` ```` と `~~~` のどちらを認識するか・フェンス長のマッチング規則・入れ子や長さ不一致の扱い・4 スペースインデントによる別のコードブロック記法も見出し抑制の対象にするか) が文書内に定義されていない。実装者は本節が言及さえしない外部仕様 (CommonMark) を持ち込んで補うしかない | Markdown 本文に `~~~` フェンス、または長さの異なる ```` ``` ```` の入れ子、または 4 スペースインデントのコードブロックが含まれる場合、実装ごとに「フェンス内」の判定が割れ、フェンス内の `#` を誤って見出し境界として扱うかどうかが実装依存になる (heading_path や char span が実装間で食い違う) | C11(a), X40 | フェンス認識規則を明記する (例: 「CommonMark 4.5 節のフェンスコードブロック規則に準拠し、開始行と同じ文字種・同じ長さ以上の閉じ行までを内部とする。4 スペースインデントのコードブロックも同様に見出し抑制の対象とする」) |
| N08 | minor | §2 (L69-75) の app 全損時の損失要約、§15 規約 7 (L1769-1780) | §2 の本文要約は規約 7 の (a)〜(e) に相当する内容 (未回収 job・cost_ledger・terminal failed 抑制・明示再生成 intent・upload_id/intent_token) のみを列挙し、規約 7 (f) (app_config の現行設定・unregister の退役事実・watch_roots 外の登録フォルダの個別パス — K25 で追加された項目) への言及が無い。§2 は「規約 7 に列挙する」と規約 7 を参照する形を取っているため、実装上の誤りには直結しないが、§2 だけを読んだ読者は損失範囲を過小に認識する | 該当なし (純粋な文書内一貫性の欠落。実装者が §15 を正本として読めば全体像は正しく得られる) | C3, C6, X40 | §2 の要約文に「(f) app_config の現行設定・unregister の退役事実・watch_roots 外の登録フォルダの個別パス」を追加するか、「詳細は規約 7 (a)〜(f) を参照」と明記して二重管理を避ける |
| N09 | major | §9.3-z 後退検出 (L1207-1223) が §10 tick の Step 5 (Replicate) に位置し、Step 0〜4 (Scan・OCR submit/collect・Embed submit/collect) より後に実行される | §13 が推奨する正規のバックアップ復元手順 (「復元後は fsck を実行する」L1699-1702) の直後、最初の tick において、後退検出 (z) が Step 5 まで実行されないため、同一 tick の Step 0 (スキャン) は app.sqlite 側の scan_cache (フォルダ単位の metadata 復元では touch されない、デバイス側の独立したキャッシュ) が実ファイルと整合したまま残っていることで「変更なし」と誤認し得る。この場合 Step 1 (OCR submit) は後退した (巻き戻った) 「現在版」content_hash を対象に差集合判定を行い、その版がまだ OCR 未実施であれば実際に課金を伴う submit を実行してしまう。z による scan_cache/fp_cache 無効化は Step 5 でようやく行われるため、Step 1 の浪費は事後には取り消せない | 初期状態: フォルダ F の metadata.sqlite が実ファイルより古い版まで巻き戻ったバックアップから復元された (working ツリーの実ファイルは復元前の新しい内容のまま)。app.sqlite の scan_cache (F, 各ファイル) は復元前の状態を保持しており、実ファイルの (mtime, size, hash) と一致している。操作列: (1) 復元直後、最初の tick が起動 (2) Step 0: 段 1 (scan_cache 行比較) が「一致」と判定しスキップ、または fp/scan のヒントに従い hash 再計算をスキップ (3) Step 1 (OCR submit): 「現在版」= 巻き戻った metadata の LWW から算出される古い content_hash。この古い版が (巻き戻り先の時点でまだ) OCR 未実施だった場合、§9.1 の差集合判定で「成果なし」となり実際に Batch へ submit される (実課金) (4) Step 5 でようやく z が後退を検出し scan_cache/fp_cache を無効化するが、Step 1 で発生した submit (と、その後の課金) は取り消されない。壊れる状態: 正規の DR 手順 (バックアップ復元) を実行しただけの利用者が、意図しない OCR 再課金を 1 回分負う | P1, P11, C7, C11(c), X40, X9 | 後退検出 (z) の判定を tick の Step 0 の冒頭 (スキャン開始前、かつ OCR/Embed の対象集合を計算する前) へ移動する。またはコストを伴う可能性のある Step 1/3 が、同一 tick 内で Step 5 の z 判定が完了するまで自身の対象フォルダの submit を保留する規範を追加する |

---

## 第 4 部 — 確認済みの列挙

検出 0 件として確認した観点:

- **C1** (P1〜P16 の反映): 全項目が文書に存在し、内容が原則と一致 (弱められた条件・欠落なし)
- **C2** (SQL 静的検証): 全 DDL について GENERATED 列構文・WITHOUT ROWID と PK の関係・CHECK
  論理・FTS5 external content の content 側 rowid 保有 (view 経由で保証)・FK 参照先の存在と列数
  一致・trigger の INSERT/DELETE 対称性のいずれにも問題なし
- **C3** (相互参照整合): §21.7・§9.3-d・「元設計§15/§21」の番号衝突注記を含め、文書内の全 §参照
  が解決可能 (N08 の §2/規約7 は「参照は成立しているが内容が過小」という別種の指摘であり、
  参照自体の破損ではない)
- **C4** (クエリとスキーマの整合): §11.2 の完全 SQL・§9.3-a のカーソル SQL・§13 の GC 差集合が
  同文書の DDL と列名・join キーの型/形式ともに整合
- **C5** (数値・事実の一貫性): $2.5/1k・+25%・768 (参考値である旨含む)・RRF k=60・「8 テーブル」
  が全出現箇所で一致 (grep による機械検証済み)
- **C6** (用語・形式の一貫性): target_key の連結形式・chunk_type と target_type の対応・
  obj:<hash> スキーム・embed_hash 定義の再掲がすべて一致
- **C7** (状態機械の完全性): batch_requests の状態遷移に到達不能・脱出不能の分岐は無い (N01/N09
  は状態機械そのものの欠陥ではなく、状態機械を跨いだ「操作の組み合わせ」が生む未文書化のコスト
  ないし順序依存であり、C7 の観点からは別枠として扱った)
- **C8** (欠落章): 原則 P1〜P16 の範囲内で書かれるべき章の欠落は無い
- **C10** (修正が開けた穴 a〜hh): r11 の M01〜M29 修正どうし・修正と既存記述の間に新たな矛盾は
  見つからなかった (N01〜N09 は修正どうしの直接衝突ではなく、修正が正しく閉じた欠陥の「隣接領域」
  で新たに見えてきた別種の gap)
- **原則別**: P1〜P16 全項目について指摘なし (N01〜N09 はいずれも P 原則そのものとの矛盾ではなく、
  C11 (実装可能性)・C12 (探索型) の観点で新規に検出されたもの)

**破れなかった主張** (X40 の反証探索 7 件、全て生存):
「冪等記帳で close Tx abort は構造的に不可能」「ready は空/部分 index を通さない」
「fork 中フォルダ移動でも未完 fork は通常運用へ復帰しない」「一時読取不能で既存履歴は破壊されない」
「delete 最終確認は対象外型置換を見逃さない」「query_profile_hash 固定で embed 中 profile 変更の
TOCTOU は不可能」「vec の距離変更は必ず DROP→CREATE される」

**探索して問題なしだった保留エッジ**: standalone read の規約12 (→ N04 として別枠指摘)、
restore の NFC 逆解決 (→ N05 として別枠指摘)、drop-derivation + backfill (→ N06 として別枠指摘)、
code fence (→ N07 として別枠指摘)、§2 要約 (→ N08 として別枠指摘)、
cross-volume case-sensitivity 移動 (実害限定的につき finding化せず、探索ログにのみ記録)。
