# folder-history 設計書 監査プロンプト (GPT 投入用)

対象: `docs/research/folder-history-sqlite-design.md` (2026-07-17、r15 修正適用済み版・約 3,039 行)
使い方: 以下の「監査プロンプト」全文を GPT に貼り、末尾の `### 対象文書` の下に設計書全文を貼って実行する。

> 改訂履歴: r1 (24) → r2 (24) → §20 新設 → r3 (7) → r4 監査 (27 件 — うち 4 件は r3 修正適用前の
> 文書に対する監査で現行では修正済み、22 件受理・修正適用、1 件部分却下 = cross-repo fan-out を
> §18.6 に不採用記録) を経た **r5 版**。主要修正: GC 3 本目を Markdown 抽出へ / 削除判定の正本 =
> LWW − walk / reconcile ステップ 0.5 / backfill / media_type を img block へ / fp 確定は処理完了後 /
> コミット入力の決定規範 / batch_requests.profile_hash。
> **注意: 監査は必ず最新の文書に対して実行すること** (r4 は適用前コピーで実行され既済み 4 件を再検出した)。
> r5 は 2 系統の独立監査で実施され、残余は DDL の CHECK 精密化 2 件のみ (受理・適用済み) — **r6 版**。
>
> **r7 版。** r6 は 3 系統の独立した探索型監査で実施され、統合 30 論点 (時計後退 / NFC / grammar
> version / phantom block / trigram 短語 / schema_version / fsck / preflight / profile 移行期間 /
> 複製・後退 等) を検出、全件受理・適用済み (却下 = 複数端末ライブ同期の調停は §19 非対応で対応、
> cross-folder dedup 非発火は注記のみ)。**原則 P と文書が食い違う場合は文書 (r6 修正適用済み) と
> H 検証リストを正とする。**
>
> **r7 も探索型監査 (C12) を主眼とする。** 回帰確認 (C9 — A〜H の 7 リスト、計 121 項目) は
> 実施するが従属的であり、全 fixed なら圧縮報告してよい (下記出力フォーマット)。探索は
> r6 の 3 監査が掘った領域 (X リスト) の**外側**、または r6 修正が新たに開いた穴 (grammar v 行・
> view 化 FTS・NFC 論理名・単調 created_at・preflight などの周辺) を優先的に狙うとよい。
>
> **r8 版。** r7 は 3 系統の独立した探索型監査で実施され、統合 31 論点を検出 — 26 全面採用・
> 3 部分採用・2 は監査プロンプト側の欠陥 (P6/P7 の陳腐化 → 本版で全 P を文書と同期済み)。
> 主要修正: cost_ledger 分離 (課金は追記専用) / 2 相 submit + intent_token (job 作成の
> dual-write ギャップ封鎖) / profile 変更の宣言的再設計 (kind=2 行削除の全廃) / 明示再生成 =
> floor 設定のみ (app 1 Tx) / pending_deletes (absent 2 回の永続化) / lower(hex()) / GC の
> hash 照合 fail-closed / fsck の commit 鎖検証 / rename 後 dir fsync / profiles 表 (§5.7、
> metadata は 8 表) / §21 明示操作カタログ / reconcile の縮小 (state 0,3 のみ — state=1 は
> collect が課金記録と同時に閉じる) / upload filename への intent_token 埋め込み。
> **検証リスト間で期待状態が矛盾する場合は新しいリストを正とする (I > H > G > F > E > D > B > A)。**
> superseded 対応表は C9 に記載。
> **r8 の重心は X16〜X20 (r7 修正の相互作用・§21 E2E・新テーブル・電源断再総当り・更新された
> 主張の反証) と自由探索** — X1〜X15 は各 1 シナリオで可 (r6/r7 で深く採掘済み)。
>
> **r9 版。** r8 は 3 系統 (計 12+ エージェント) の独立探索監査で実施され、統合すると fatal 実体
> 2 件・major 実体 15 件・minor 十数件を検出、**全面採用 (却下 0、3 件のみ minor へ格下げ)**。
> 主要修正: **2 相 submit の相 1 で kind=2 の profile_hash を設定** (これが無いと DDL CHECK 違反で
> embedding 投入が一切開始できない fatal) / **upload_cleaned を相 1 でリセット** (再 submit の
> 新 upload リーク) / **collect に job_missing (404) 分岐** (恒久消滅の脱出路) / **再チャンクが
> floor を追い越す穴を封鎖** (§7 で floor も引き上げ) / **vec 再充填を差集合冪等化** (CREATE 後
> クラッシュの欠落補填) / **agg 破棄を毎 tick 宣言的検査化** (§8-e) / **app_config 新設** (横断検索の
> クエリ embedding source・§8 現行設定の実体) / **cost_ledger の cost_usd NULL 許容 + estimated +
> UNIQUE** / **fork を耐久手続きに全面書き直し** (defer_foreign_keys で自己参照 FK・安全 id 書込・
> 旧 app 行退役・fork_in_progress で規約 12 抑止・失敗回復) / **register の上書き conflict + fp_cache
> 無効化 + embedding_vec 遅延作成** / **unregister の detached in-flight job** / **restore の宛先必須 +
> path traversal 検証 + name_invalid** / **case 折り畳み比較** / **NFC 衝突敗者を name_collision** /
> **fsck に profiles 照合 + object 読取一時失敗の区別** / **walk 対象の重複排除** / **§9.3-z の
> regressed 通知** / **§21.5 watch_root 操作 / §21.6 drop-derivation 新設**。metadata は 8 表のまま、
> app.sqlite に app_config / cost_ledger / pending_deletes を含む。
> **検証リスト間で矛盾する場合は新しいリストを正 (J > I > H > G > F > E > D > B > A)。**
> **r9 の重心は X21〜X25 (r8 修正の相互作用・fork 耐久手続き・app_config/detached の整合・宣言的
> 収束の再反証・client 側キュー写像) と自由探索** — X1〜X20 は各 1 シナリオで可。
>
> **r10 版。** r9 は 6 系統の独立探索監査で実施され、統合すると **J04 = not-fixed** (r8 の裁定
> 報告が「適用済み」と誤記したまま未編集 — 6/6 系統が検出) + fatal 実体 6 クラスタ + major 実体
> 約 20 件。全面採用 (却下 0)。主要修正: **submission_seq** (リセットしない通算投入連番 —
> cost_ledger の UNIQUE を attempts から分離。attempts リセット × ledger UNIQUE 衝突で close Tx が
> 恒久失敗する fatal の根治) / **profile_record snapshot 列** (相 1 で書き相 3・intent 採用で不変 —
> 採用 UPDATE が snapshot を current で上書きして旧空間 vector が照合を素通りする穴、tool 切替中の
> in-flight record 復元) / **client 写像 = 実行前計上** (呼出前に attempts/seq/実行 id を永続化。
> 「state=0 = 未実行として無条件再実行」は呼出中クラッシュで無限重複課金 — 「最悪 1 job」主張を
> server 経路限定に修正) / **相 2 恒久拒否 = submit_rejected terminal** / **detached = 課金追跡
> 専用** (payload 破棄・metadata 書込なし — root_path 不在で書込先が無い。state=0 は掃除して即削除。
> §9.3-d / fork も §21.2 と同一規則に統一) / **fork journal を層 1** (.folder-history/fork-journal、
> 入力 = 対象パス、fork 中は tick 全ステップ除外、非追跡側コピー fork の生存側保護、app 全損でも
> 回復可能) / **case 規則 = 保存論理名を系列の初出時表記に固定** (「判定折り畳み + 保存 readdir
> 表記」は複合 FK / PARTITION を壊す — SQLite 再現済み) / **§7 floor 引き上げ** (J04 の実適用 —
> 順序は app 先行 = fail-safe) / delete 確定に最小不在時間 30 秒 / pending 残留掃除 / 猶予 30 日 →
> 自動退役 (retired) / missing rebind / 再発見時 fp_cache 無効化 / fsck profiles 参照検査 +
> DELETE→INSERT 修復 / FTS 後付け migration の rebuild / FK PRAGMA 接続初期化規範 / job_missing
> 時刻基準 / output_missing 差集合限定 / terminal 課金記帳 / instr lower 統一 / ROW_NUMBER
> tiebreak / ページ結合規範 / image 非境界 / 規約 7 は 6 点 (a〜f) / 規約 9 に「真実 = 履歴・派生・
> 検索の正本」の二層注記。
> **検証リスト間で矛盾する場合は新しいリストを正 (K > J > I > H > G > F > E > D > B > A)。**
> **r10 の重心は X26〜X30 (r9 修正の相互作用 — 特に submission_seq × attempts × ledger の三者・
> fork journal E2E・detached ライフサイクル・保存名固定・更新済み主張の反証) と自由探索** —
> X1〜X25 は各 1 シナリオで可。
>
> **r11 版。** r10 は 7 系統の独立監査 (うち 1 系統は 15 サブエージェント並列、1 系統は 72
> シナリオ) で実施され、統合すると fatal 実体 4・major 実体 約 20・minor 約 15。全面採用 (却下 0 —
> 挙動が正しいと裁定した数件は「意図されたトレードオフ」の明記で対応)。芯は**「可変ガード行
> (削除される) × 追記台帳 (永続) × 行ライフサイクル」の突合点**。主要修正: **submission_seq の
> 初期値 = cost_ledger の同キー MAX から継承** (行削除→再作成で 0 起点だと永続 ledger と UNIQUE
> 衝突し close Tx が恒久失敗 — SQLite 再現済み fatal) / **reconcile / submit の state=0|3 close に
> 付随処理を義務化** (kind=1 floor NULL 化・batch_job_id 非 NULL は NULL+estimated 記帳・
> intent_token 残骸掃除 — client の metadata 後クラッシュの記帳欠落と「失効窓は記録できない」
> 残余を解消) / **detached state=0 の「job 未作成 = 課金なし」前提を禁止** (client 前計上 =
> terminal 記帳、server = token 照合で実在なら state=1 detached へ採用、実行点 = collect 冒頭) /
> **submit_rejected は attempts = 上限を同 Tx 設定** (据え置きだと遷移表が自動再投入して宣言と
> 逆の無限ループ) / **相 2 を 2a (upload 直後に upload_id 記録)・2b (job 作成) に分割** /
> **client_exhausted** (上限到達 state=0 の唯一の出口) + intent 回復の dispatch (batch_job_id
> 非 NULL = client) / **kind=1 tool_changed ガード** (載せ直しの snapshot と key の不整合防止) /
> **fork を phase 状態機械化** (PREPARED→HISTORY_CLEARED→ID_WRITTEN→APP_DONE、journal 安全書込、
> flag→journal の削除順、毎 tick 冒頭 + bootstrap の回復契機、folders 旧行 DELETE 明示、除外粒度 =
> (old_id, realpath)、was_tracked を journal に固定、id=old なら手順 1 から、journal 破損 =
> damaged) / **agg building/ready 2 key** / fsck repair の 1 ストリーム + 破損置換例外 + kind 別
> 誘導 / O_NOFOLLOW / delete 確定直前の最終 stat / fp 確定禁止 4 条件目 + `.folder-history`
> 発見は fp skip 対象外 / missing_since 列 / rebind 拡張 / standalone bootstrap / 規約 7 の
> 有界性 2 種 / RRF tiebreak / LIKE 完全形 / at_hash=FF 固定 / ページ結合後エスケープ / K02
> 叙事文 (15 中 10 エージェント検出) 修正。
> **検証リスト間で矛盾する場合は新しいリストを正 (L > K > J > I > H > G > F > E > D > B > A)。**
> **r11 の重心は X31〜X35 (r10 修正の相互作用・fork phase 機械・課金記帳の網羅行列・検索完全形・
> 更新済み主張の反証) と自由探索** — X1〜X30 は各 1 シナリオで可。
>
> **r12 版。** r11 は 6 系統の独立監査 (5 不合格 / 1 合格。うち 1 系統は 15 サブエージェント並列、
> 1 系統は SQLite 実機再現) で実施され、統合すると fatal 実体 1・major 実体 12・minor 十数件。
> 全面採用 (却下 0 — 係争 1 件 = fork 中 in-flight OCR の二重課金は「有界・追跡済み・§18.6 の
> per-repository 課金モデル整合の意図されたコスト」として §21.3 に明記で対応)。芯は予想どおり
> **「r9/r10 の fix どうしの相互作用」**(「fix が開ける穴」定番脈 12 例目) — 発生源は §9.1 状態機械
> 本体からさらに外周 (close 経路の記帳冪等性・fork 回復・register/detached の周辺) へ移動。
> 主要修正: **close 経路の課金記帳を全て冪等化** (collect 成功 / terminal 化 / reconcile・submit
> close / client_exhausted / detached の cost_ledger 追記を `ON CONFLICT(repository_id, kind,
> target_key, submission_seq) DO NOTHING` に統一 — 素朴 INSERT だと profile A→B→A で collect の
> profile_changed 記帳と reconcile close 記帳が同一 seq 衝突し close Tx が恒久 abort する fatal。
> SQLite 実機再現) / **§21.2 の detached state=0 を §9.1 分岐へ** (「即削除」は課金・upload handle
> 喪失) / **app_config DDL コメントを 6-key 化** (tool/embedding/image_filter/retry_not_before/
> agg_building/agg_ready — 旧単一 key 実装は KNN 恒久停止) / **§13 の embedding 修復を kind 別化**
> (旧「§5.3 一律誘導」は kind=1 専用で embedding に誤適用 = regression) / **fork 回復の flag 掃除に
> 「realpath に .folder-history 実体現存」要件 + commits 非空なら手順 1 から + 再発見の fork id 除外**
> (中断中フォルダ移動で未完 fork が復帰する穴) / **detached server 採用も seq+1/attempts+1**
> (増分なしだと close 記帳が旧 seq 衝突) / **§8(i) client 前計上に profile snapshot** (欠くと
> kind=2 CHECK 違反) / **delete 最終確認を lstat+regular 型判定** (対象外型置換を永久 delete 不能の穴) /
> **ready を接続フォルダ (missing/fork 除外) の synced_profile_hash 全一致条件 + agg_vec 差集合再充填
> + fsck agg 対象化** (sync_state に synced_profile_hash 列追加) / **vec 再作成を次元 + 距離照合**
> (vec0 distance_metric は profile 従属 `<metric>`) / **register 再発見で同 root_path の別 id 旧行を
> 先に退役** / **image_filter を app_config 永続化 + bootstrap 再入力** / **register の一時読取不能を
> damaged (破壊的再初期化) にせず保留** / minor: item 失敗記帳・collect Retry-After 永続化・
> invalid_output terminal・chunks seq/span CHECK・agg_file_versions 複合 CHECK・fork journal 版付き +
> digest・短語 fallback の heading_path・query TOCTOU (query_profile_hash 固定)・query embed 失敗の
> FTS-only・float32 little-endian・LIMIT 契約・§16 参照更新・孤立 P9 除去・alt の `[` `]` escape・
> 後退検出時 cache 無効化・root dirfd 束縛・reconcile close の token 掃除を Tx 外。
> **検証リスト間で矛盾する場合は新しいリストを正 (M > L > K > J > I > H > G > F > E > D > B > A)。**
> **r12 の重心は X36〜X40 (r11 修正の相互作用 — 特に冪等記帳 × seq 継承 × detached 採用の三者・
> ready 完了追跡 synced_profile_hash・fork 回復拡張・register/検知周辺・更新済み主張の反証) と
> 自由探索。保留した単一系統エッジ (standalone read の規約 12・restore の NFC 逆解決・drop+backfill・
> code fence・§2 要約・cross-volume case) の再評価も含む** — X1〜X35 は各 1 シナリオで可。
>
> **r13 版。** r12 は 8 系統の独立監査 (合格 2 / 条件付き 1 / 不合格 5) で実施され、集約 = 不合格
> (合格系統は過小検出)。統合すると major 実体 8・minor 実体 約 38・却下 6。今回の major は既存修正の
> 破壊ではなく**規範の空白** (client 経路の記帳・照合の三値・raw 物理名解決) が主で、r9〜r11 の
> 「close 経路の記帳」脈の regression は 0。**裁定の自己申告 2 件**: ①プロンプト旧版の app_config
> 「5 種」は転記ミス (実 6 key — r12 で 'fork_in_progress' を加え 7 key)、②**r11 裁定の名寄せ落ち
> 8 件** (client 旧 seq 未記帳 / lookup 照会失敗 / 保持期限超 / 共有 token guard / client API 分類 /
> §10 1job 無限定 / step0.5×detached / vec dim 参照元) を r12 の複数系統が再検出 — N 検証リストへ
> 回収済み (該当項目に「回収」と明記。**名寄せ落ちの再発防止のため、r13 の裁定では全系統の全指摘 ID を
> 採用/却下/降格のいずれかに必ず対応付ける**)。主要修正: **client 再実行の前計上 Tx で直前 attempt の
> 旧 seq を冪等 terminal 記帳** (client_exhausted の一般化) / **server intent 照合の三値化**
> (found / confirmed-absent / unknown — 照会失敗は不存在と解釈しない) / **intent_token = UUIDv7**
> (時刻成分 = 相 1 実行時刻。保持期限超の confirmed-absent は seq+1 + NULL+estimated 記帳してから
> 載せ直し) / **付随処理 (b')** (state=0 server の成果あり close は token 照合で job 実在なら掃除前に
> 記帳 — profile A→B→A で単一デバイス再現) / **ready 母数 = 「当該 tick に §9.3 を実行できた
> フォルダ」** (missing/fork/damaged/一時読取不能を除外・接続 0 件中は非更新) / **agg 破棄 Tx で
> synced_profile_hash 全行 NULL** (P2→P3→P2 の空 index ready 防止。ready = 設定時点の被覆宣言と
> 意味論明記) / **規約 12 の scoped read 拡張** (登録済み path の読取も照合・未登録 standalone read は
> repo-id 表示で許可) + 読取失敗の 4 分類を全 open へ一般化 / **論理名 → raw 物理名の共通解決規則**
> (§20.5 — delete 最終確認・restore in-place・fsck に適用。NTFS/ext4 の NFD 実体×NFC 書込の二重実体
> 防止) / tick に **step -1** (§9.3-z の判定を冒頭へ — 復元直後 tick の課金防止) / 4.5 に **token
> sweep** + (c) 掃除の共有 token 全行終端 guard / 相 2a・client 呼出失敗の 2 分岐 / fork 手順 3 の
> root_path = 発見パス + 同 root_path 別 id 退役 / fork_in_progress = app_config key / code fence =
> CommonMark 固定 / img 除去の LF 規則 + un-escape / §2 損失要約の (a)〜(f) 同期 / §21.6 backfill
> 過去版注記 / agg_chunks CHECK / agg_vec DELETE→INSERT / app backup = VACUUM INTO / §12 missing
> ヒット status / §18.4 1repo 文言 / last_seen_at 規則 / case 感度 = 走査時属性 / cost_ledger DDL
> コメント冪等化 / BLOB bind 明記。**却下 6** (tombstone 再却下 = r11 明記済み / upload handle = 既知の
> 残余 / fsck 次元検査 = §8-e が覆う / vec_hits optimizer = vtab 仕様 / fsck 検出のみ = 既記載 /
> 新規 chunk P→NULL = ready 意味論明確化で対応)。
> **検証リスト間で矛盾する場合は新しいリストを正 (N > M > L > K > J > I > H > G > F > E > D > B > A)。**
> **r13 の重心は X41〜X45 (r12 修正の相互作用 — 記帳経路の網羅行列の再検証・ready 母数と synced の
> 動態・raw 解決の全数・scoped 規約 12 と step -1・更新済み主張の反証) と自由探索** — X1〜X40 は
> 各 1 シナリオで可。
>
> **r14 版。** r13 は 9 系統の独立監査 (合格 2 / 条件付き 3 / 不合格 4) で実施され、集約 = 不合格
> (合格系統は過小検出)。裁定は宣言どおり**全 71 指摘 ID を採用/却下/降格に対応付けた** (名寄せ
> 落ち 0 — tasks/folder-history-r13-adjudication.md。この対応付けは r14 以降の裁定でも標準とする)。
> 統合すると fatal 実体 1・major 実体 8・minor 実体 約 20・却下 8 (再々却下 2 = tombstone /
> upload handle、SQL 3 値論理誤解 1、既記載 1 ほか)。芯は X41 の狙いどおり **r12 新設の「無 id
> 課金の記帳」ファミリー**に集中 (「fix が開ける穴」定番脈 13 例目)。破壊型 regression は 3 ラウンド
> 連続 0。**裁定の自己申告 2 件**: ①§10 4.5 の token sweep はプロンプトのみ更新した転記漏れ
> (doc 側は r13 で回収)、②§6/§7 の un-escape 往復可逆は r12 のバグ — §6 の対象が裸の grammar 形
> のみで `\` 前置行が素通りし原文が変質する (r13 で修正)。
> 主要修正: **fatal = 無 id 記帳 × cost_ledger の batch_job_id NOT NULL** (期限超 confirmed-absent に
> 入れる値が無く INSERT が制約違反 → intent 回復恒久停止。4 系統・2 系統 SQLite 再現) →
> **batch_job_id の値規則を明記** (server job id / client 実行 id / **無 id 記帳 = intent_token** /
> (b') = 発見 job id — この列が「記帳済み判別」の突合キーを兼ねる) / **記帳済み判別述語** (無 id・
> (b') 記帳の前に「同 (repo, kind, target_key) × batch_job_id = 当該 token / 発見 job id」の既存
> ledger 行を確認し既存なら省略 — **seq+1 は非冪等**のため ON CONFLICT だけでは再駆動の推定行増殖を
> 止められない) / **token sweep に (b') と同一の前段を義務化** (job 実在かつ未記帳なら記帳 → 掃除 →
> NULL 化。unknown は掃除も NULL 化もせず保持 — close 後の記帳・掃除失敗の唯一の再駆動点) /
> **期限超の処理を同一 app Tx に固定** (述語 → 記帳 → **attempts+1** (作成済みであり得た attempt を
> 消費 — 数えないと相 2b/相 3 境界クラッシュ反復が上限を素通り) → 載せ直し相 1) / **detached (b) にも
> attached と同一の期限判定** (期限超 confirmed-absent は記帳してから削除 — detached は載せ直さない) /
> **UUIDv7 の未来 skew** (時刻成分が now + 5 分超の未来・解釈不能 = 期限超扱い — 未来時計 token が
> 恒久「期限内」で無記帳載せ直しになる穴) / **§6 エスケープを「0 個以上の `\` + grammar 形」へ拡張**
> (G→\G、\G→\\G — §7 の 1 個除去と全段可逆。test vector 3 段) / **in-place restore は書込前に
> 未取り込みの working 変更を履歴化** (現内容 ≠ LWW なら先に §20.5 手順でコミット — 履歴ツール自身の
> 唯一の不可逆喪失経路を閉鎖) / **§5.3 の md 行不在は floor = 0 (sentinel)** (§21.6 drop 後の
> 過去版のみ × backfill OFF で明示再生成が機能する) / **§21 全操作は tick.lock 取得直後に fork 回復を
> 先行** (未完 fork を跨いだ unregister が回復の手順 3 に反転される穴・flag 上書きの排除) /
> **規約 12 × fork_in_progress の共有ガード** (呼出元を問わず除外 — fork 中の読取は conflict でなく
> 「fork 進行中」status) / resolver TOCTOU 軟化の 3 呼出点一般化 (+restore の rename 直前再 lstat は
> 任意) / minor: step -1 の三値 (unreadable = 未検証除外) / z 後 in-flight collect の残骸注記
> (fence 機構は却下 — 課金済み結果を破棄しない) / flag 掃除に marker id = old/new 一致要件 /
> 自動 rebind 条件 (旧パスが別実体で再利用) / sync_state 初回行 + hex↔BLOB 変換契約 / client
> submit_rejected の batch_job_id NULL 戻し (未実行 attempt の誤記帳防止) / profile_record・
> floor kind・upload_cleaned の CHECK 3 種 / §10 step 2/4 の detached 冒頭再掲 / §10 4.5 の
> token sweep 列挙 / 規約 7(a) の server/client 限定 / migration の tick.lock + writer の
> user_version 再確認 / §8 冒頭の参照元 = app_config / watch_root 解除 Tx の配下 fp_cache 明示
> DELETE / mapping 表の bind 給源注記 / preflight marker を seq 継承列挙へ / §13 embedding 修復の
> vec → embeddings 順 + fsck ローカル逆差集合。
> **検証リスト間で矛盾する場合は新しいリストを正 (O > N > M > L > K > J > I > H > G > F > E > D > B > A)。**
> **r14 の重心は X46〜X50 (r13 修正の相互作用 — 記帳済み判別述語 × 冪等記帳 × seq 連番の三者・
> 期限超同一 Tx × token rotation・restore 保全 × scan・回復先行 × 全操作・更新済み主張の反証) と
> 自由探索** — X1〜X45 は各 1 シナリオで可。
>
> **r15 版。** r14 は 8 系統の独立監査 (条件付き合格 1 / 不合格 7) で実施され、集約 = 不合格。裁定は
> 全指摘 ID (約 80) を採用/却下/降格に対応付けた (tasks/folder-history-r14-adjudication.md)。統合結果:
> **fatal 0 (13 件の fatal 主張を全降格** — 基準: 課金の記録喪失 = 有界 = major。fatal は恒久停止・
> データ喪失・SQL 非機能のみ**)・回帰補修 2 (O28 = §5.7/§8-c の「§5.7 record」残存 [4 系統一致]・
> O17 = step -1 の除外一律と collect 注記の矛盾 [単独系統])・major 7・minor 24・見送り 1・却下 13**
> (upload handle は **4 回目却下**。「client 再実行の述語誤作動」は client 記帳が seq キーの
> ON CONFLICT 冪等のため却下 — batch_job_id 述語は server 期限超専用で client に存在しない。
> audit_ddl.sql の CHECK 3 本欠落は監査側スクリプトの不備 — 文書は 3 本とも保持。submission_seq
> DEFAULT 0 の fatal 主張は DDL コメントが MAX 継承を既に明記しており精読不足で却下)。
> 芯は「r13 新設規範の照合点非対称」— **(b')/token sweep 前段の期限判定欠落 (3 系統独立検出 —
> sweep 自身が塞ぐはずの穴を sweep 自身が持つ。「fix が開ける穴」定番脈 15 例目)**。
> 主要修正: 期限判定に**逆側の伝播猶予を新設** (token 時刻から 10 分以内の confirmed-absent は
> unknown 扱い — job 一覧 API の read-after-write 整合を仮定しない) し、期限判定・伝播猶予を
> **4 照合点 (intent 回復・detached (b)・(b')・token sweep 前段) に共通適用** / 無 id・発見記帳
> 3 箇所 (期限超 (ii)・(b')・sweep 前段) に **batch_requests.submission_seq の行 UPDATE を明示**
> (行 seq を進めない「記帳のみ」の読みだと次の正規 close が旧値から同じ +1 を計算し、ON CONFLICT
> DO NOTHING が実課金の記帳を黙って吸収する — 単独系統の検出) / 期限超に **(iii') attempts 上限
> 出口** (state=3 error='expired' — client_exhausted の server 対応物。4 系統) / §21.2・§9.3-d・
> detached の**行削除条件に intent_token IS NULL を追加** (token 残存 = (b')/sweep 未完 — 課金
> 再駆動キーの喪失防止) / 単独検索の **:current_tool 決定規則 = markdown_documents の最新
> generated_at** (embedding の「混在停止」と意図的非対称 — tool 混在は世代選択にすぎず、停止すると
> FTS まで恒久停止して §2 可搬性に反する。テーブル分離設計の伏在穴) / restore の**安定確認失敗 =
> 中止** + **rename 直前の再 lstat を in-place では義務化** (§20.5「任意の強化」の格上げ) /
> **破損 journal の明示解決の実体 = §20.4 damaged 復旧 (journal/flag 除去 → 新 id 再登録) — §21
> 前文の回復先行ゲートの唯一の例外** + §21.1 手順 1 に fork-journal チェック / minor 24 (404 = 削除
> 成功・ts = 確定月配賦・規約 7(a) 全損列挙補正・ローカル vec DELETE→INSERT 統一 + fsck 孤児削除・
> agg 親子整合検査・flag 掃除 id=new 限定・fork 前 rebind・started_at + fork stalled 格上げ・
> standalone read の journal preflight + 重複 provenance・case fold tie-break・grammar v の画像 0
> スキップ + 未知 v fail-closed・§12 提示前 hash 再照合・fork 直後 GC 禁止・「OR IGNORE で黙って
> 欠落」の事実誤認修正・:query_vector 形式・agg_chunk_fts 読み替え規則・profile 未設定 skip ほか)。
> **見送り 1 = §6/§7 エスケープ条件の非対称** (単独系統 — 条件を §7 の行全体一致に狭めると phantom
> 防止の二層目が弱まるため現状維持が安全側と裁定。**X56 で再評価する保留論点**)。
> 破壊型 regression は 4 ラウンド連続 0。
> **検証リスト間で矛盾する場合は新しいリストを正 (Q > O > N > M > L > K > J > I > H > G > F > E >
> D > B > A。P は原則番号のため欠番 — 検証リストの Q = r14 修正、監査報告の新規検出は R 採番)。**
> **r15 の重心は X51〜X56 (r14 修正の相互作用 — seq 行 UPDATE × 連番一貫・expired terminal × 遷移表 ×
> sweep・4 照合点の期限判定対称性・回復ゲート例外 × register journal チェック・単独検索の 2 決定
> 規則・エスケープ非対称の再評価・更新済み主張の反証) と自由探索** — X1〜X50 は各 1 シナリオで可。
>
> **r16 版。** r15 は 7 系統 (条件付き合格 2 / 合格 1 / 不合格 3 + 独立レビュー 1) で実施され、
> 集約 = 不合格 (合格・条件付き系統は回帰 3 件を素通し — 「合格系統は過小検出」4 回目。うち 1 系統は
> found 枝どうしの比較のみで述語の時間差分裂を「対称」と誤棄却)。裁定は全指摘 ID を対応付けた
> (tasks/folder-history-r15-adjudication.md)。**自己申告 4 件 = r14 適用の転記漏れ** (Q02: §9.3-z 側の
> 除外文の直し忘れ / Q04: 「(i)〜(iii') を 1 Tx」と書いて (iv) を列挙から落とす / Q09: §9.3-d と
> fork 手順 3 のパラフレーズがガード 2 条件を落とす / Q12: §20.5 の「任意の強化」残存) — **同一規範の
> 再掲対 (§9.3-z↔§10、§20.5↔§21.4 等) の片側だけを直す転記漏れが回帰の最大源**。統合結果:
> **fatal 0 (6 件の fatal 主張を全降格)・回帰補修 4 + major 8 + minor 17・却下/見送り約 30**
> (upload_id 上書きは **5 回目却下**)。芯 = **found 記帳 (発見 job id) と期限超記帳 (token) の述語の
> 時間差分裂** (SQLite 再現 — found 記帳 → 掃除前クラッシュ → 一覧から消滅 → 期限超が「未記帳」と
> 誤認して同一 job を 2 行計上) と **r14 削除ガード (intent_token IS NULL) が開けた穴** (「fix が
> 開ける穴」定番脈 16 例目 — detached state=0 の「記帳して即削除」とデッドロック / client
> submit_rejected の token が job 一覧の無い client で恒久 unknown → 永久残留)。
> 主要修正: found 記帳の小 Tx に**行の batch_job_id = 発見 job id の UPDATE (自己記述化)** を追加 —
> 以後 sweep 前段 (batch_job_id NULL 対象) から構造的に外れ述語分裂を塞ぐ / sweep 前段から
> **error='submit_rejected' を除外** (照合・記帳なしで掃除 → NULL 化) / detached state=0 は**記帳
> Tx で state=3 (error='detached'/'expired') + completed_at の terminal 化** → 4.5 → 削除条件の
> 段階遷移へ統一 / 期限超は **(i)〜(iv) の DB 書込を 1 Tx** ((iv) の外部 upload 削除のみ Tx 外) /
> **伝播猶予 = 過去側のみ (0 ≤ now−token ≤ 猶予)・未来 skew 優先 + プロバイダ採用条件** (job 一覧の
> 可視化遅延上限 ≤ 猶予 — 保証できない provider では有界化不成立と明記) / 相 1 の旧 upload 削除に
> **共有全行終端ガード** (4.5 と同条件) + 旧 token の未記録残骸掃除 / **§6/§7 エスケープの対称化 —
> X56 の再評価が r14 の見送り裁定を正当に覆した** (見送り時に検討しなかった第三の方向: un-escape の
> 対象判定を §6 と同一の緩いパターンへ拡張 (認識は厳密一致 + 実在検証のままで phantom 防止不変) +
> 再 materialize は本文を再エスケープしない (累積防止)) / :current_tool の**同時刻 tie-break =
> tool_profile_hash バイト昇順** + 一括変換逆転の近似注記 / **journal 検査の三値化** (破損 = 読めたが
> digest 不整合のみ・一時読取不能 = 保留 — §21.1/§21.3 両方) / 明示解決の順序 (journal 除去 →
> flag 残置 → 手順 2 → flag は (a) 規則が回収) / minor: 規約 6 の floor 例外併記・fsck の FTS
> integrity-check + agg_ready 削除・LIKE の text IS NOT NULL・回復表の第三 id 行・ON CONFLICT
> 文言修正・一括変換 operation record・空本文チャンク非生成・profile 未設定 skip の拡張・raw 不在
> 分岐・vec0 受理検証・profiles PK 前提注記・app_config key 別存在条件・auto_vacuum 注記。
> **検証リスト間で矛盾する場合は新しいリストを正 (R > Q > O > N > M > L > K > J > I > H > G >
> F > E > D > B > A。P は原則番号のため欠番 — 検証リストの R = r15 修正、監査報告の新規検出は
> S 採番)。**
> **r16 (2026-07-17 裁定・適用済み — 初の CLI 並列 10 系統)**: fatal 0 (15 件の fatal 主張を全降格)・
> 回帰補修 3 + major 9 + minor 17・却下 17。文書 3,039→3,135 行。回帰 3 (R08/R18/R20) は**全て
> 「規範文は正しいが要約・掲載 SQL・DDL コメント側に非伝播」の同型** (R01〜R04 の再掲対検査は全系統
> 合格 — 検査対象を規範↔要約・SQL 例・DDL コメントへ拡張する必要が判明)。芯: operation record の
> 許可 key 契約 (→S04、6 系統一致・「fix が開けた穴」17 例目) / 破損 journal 明示解決の第三 id
> (→S05、4 系統・18 例目) / sweep found 判別の T/J 非対称二重記帳 (→S10、19 例目 — X57 の勝利) /
> 伝播猶予の起点 = job_create_started_at 列追加 (→S07、唯一の DDL 変更 — X61 の勝利) / restore
> 不在分岐の無痕跡上書き (→S06) / cancel 確定行の terminal 遷移未定義 (→S11)。却下の教訓: 手順
> ラベル「(iii')」を範囲表記の残存と誤認・両側実在の見落とし (grep せず regression 主張) が誤読の
> 最多パターン — **C9 の not-fixed / regression 主張は両側の引用証明を必須とする**。
> **検証リスト間で矛盾する場合は新しいリストを正 (S > R > Q > O > N > M > L > K > J > I > H > G >
> F > E > D > B > A。P は原則番号のため欠番 — 検証リストの S = r16 修正、監査報告の新規検出は
> T 採番)。**
> **r17 (2026-07-17 裁定・適用済み — 初のパス渡し・自律読込 7 系統)**: fatal 0 (8 件の fatal 主張を
> 全降格)・回帰補修 4 + major 5 + minor 8・却下 2。文書 3,135→3,207 行。補修 4 (S19/S20/S24/S25) は
> **全て r16 適用の非伝播 — X66 (規範↔要約/SQL/DDL コメント横断) が設計どおり検出**した (S20 =
> §4.1 共通 record 例 × §5.7 shape 矛盾 + metric/distance_metric 転記ミス、S24 = rebind fp_cache
> DELETE の別実体分岐・§20.4 非伝播、S19 = seq 現値記帳が明示 retry 後の 2 度目拒否と UNIQUE 衝突、
> S25 = 既定 backoff の分岐非伝播)。芯: **相 1 の NULL 戻し列挙に job_create_started_at が無い
> (→T05、5 系統一致・「fix が開けた穴」20 例目 — X62 本命の勝利)** / migration の NULL 意味論
> (→T06) / cancel = attempts 上限 + id 無し token 行の確定禁止 + rotation ガード (→T07/T08、4 系統 —
> X63) / no-replace 非対応 FS の fallback 規範 (→T09、5 系統 — X65) / DOCX 変換 PDF の hash/upload
> 対応 (→T10 — 実装不能級)。却下 = vec 値 bit-rot (r16 前例の再演)。
> **検証リスト間で矛盾する場合は新しいリストを正 (T > S > R > Q > O > N > M > L > K > J > I > H >
> G > F > E > D > B > A。P は原則番号のため欠番 — 検証リストの T = r17 修正、監査報告の新規検出は
> U 採番)。**
> **r18 (2026-07-17 裁定・適用済み — パス渡し 7 系統)**: fatal 0 (11 件の fatal 主張を全降格)・
> 回帰補修 8 + major 6 + minor 10・却下 5。文書 3,207→3,284 行。補修 8 = **r17 適用の非伝播 5 件**
> (T10 = §6/§9.1 の「原本」語が r17 M5 と正面衝突 (5 系統) / T16 = :fts_cap が掲載 SQL 未反映 +
> §19 旧 :k_fts (5 系統) / **T08 = rotation ガードの 3 重欠陥 — state=0 載せ直しとの自己循環・
> 「掃除失敗続行」と両立不能・恒久 unknown の脱出なし (4 系統・X67 = 「fix が開けた穴」21 例目。
> fix = state=3 再投入限定 + 本体は照合・記帳・NULL 化 + 明示 abandon)** / T03 = §8 側 seq+1 非伝播 /
> T11 = 滞留判定が flag のみ) + **旧世代の取りこぼし 3 件** (J09 = completed_at 書込が detached
> 経路のみ / I31 = 「構文的に開けるか」skip が安定破損実体を恒久非保護 / S18 鏡 = step 4 に folders
> 限定なし)。major = 変換失敗分岐 (convert_failed)・GC×未知 grammar v・cancel 約束の「行が存在する
> 間」限定・account/workspace scope・export 新規作成限定・DDL コメント「まだ job が無い」修正。
> 却下 = vec 値 bit-rot (3 回目)・reconcile attempts・JSONL 分割×token (規範既存) 等 5 件。
> **検証リスト間で矛盾する場合は新しいリストを正 (U > T > S > R > Q > O > N > M > L > K > J > I >
> H > G > F > E > D > B > A。P は原則番号のため欠番 — 検証リストの U = r18 修正、監査報告の
> 新規検出は V 採番)。**
> **r19 (2026-07-18 裁定・適用済み — 6 系統。dsv4 は DSML ツール呼び出しのテキスト漏出 ×2 + 起動
> 凍結の 3 連続失敗で打ち切り)**: fatal 0 (9 件全降格)・回帰補修 6 + major 5 + minor 9・却下 6。
> 文書 3,284→3,348 行。**X71/X72/X74/X27 命中 — 「fix が開けた穴」22〜24 例目**: M3 = r18 の
> 有界スキップ「3 回/24h」にカウンタの永続化基盤なし (4 系統・X74 = 22 例目 → scan_cache に
> syntax_fail_count/first_failure_at + EIO 除外 reset) / M1 = r18 ガードの state=2 穴 (floor 明示
> 再生成が再投入経路 — X71 = 23 例目 → state IN (2,3)) / M2 = r18 scope 規範の保存基盤なし
> (24 例目 → batch_requests に scope_id 列)。M4 = abandon の操作実体 (IN 判別 → seq+1 記帳 →
> error='abandoned' + attempts 上限 → NULL 化、state=0 恒久 unknown も対象)。M5 = fp スキップ例外に
> fork-journal 検査 (fp 入力の .folder-history 除外を明記)。補修 6 = U01 (「原本」語 4 箇所 =
> r18 T10 非伝播)・U06 (DDL コメント)・U24 (不可能組合せ行 — r18 統合裁定を撤回)・U11 (§21.2 断定
> 限定)・N23 (退避×backfill)・(P1) 宙吊り参照。却下 = agg 系 3 (cache scope 前例)・vec payload
> (4 回目)・時計 jump 退役 (r13 前例)・resolver 併存。
> **検証リスト間で矛盾する場合は新しいリストを正 (V > U > T > S > R > Q > O > N > M > L > K > J >
> I > H > G > F > E > D > B > A。P は原則番号のため欠番 — 検証リストの V = r19 修正、監査報告の
> 新規検出は W 採番)。**
> **r20 の重心は X75〜X78 (r19 修正の相互作用 — scope_id が開ける穴・abandoned × 遷移表・fp スキップ
> 例外の検査コスト・ガード拡張 × floor 順序) と自由探索、および**補修 6 件の再発検査 (V01〜V06)** —
> X1〜X74 は各 1 シナリオで可。

---

## 監査プロンプト (ここから下をコピーして使う)

あなたは設計文書の監査者である。以下の「設計原則 (正本)」は人間のレビュー会話で確定した決定事項であり、
**対象文書がこの原則を漏れなく・矛盾なく反映しているか**を検査する。原則自体の是非は問わない。

### 前提と禁止事項

- 対象文書は SQLite を正本とするフォルダ単位バージョン管理 + AI 検索の**独立した**設計書である。
  文書外の他プロジェクトの規範・一般的ベストプラクティスを根拠にした指摘は行わない
- **設計選択そのものへの異論は監査対象外**: SQLite 正本 vs 不変オブジェクト正本、ファイル単位 LWW vs
  スナップショット、テーブル分離の是非は文書の §18 (採用しない構成) と §19 (再検討の境界条件) で
  決着済み。これらを蒸し返す指摘は出さない
- 根拠の規則は二本立てとする:
  **回帰確認 (C1〜C11)** — 従来どおり P1〜P16 / C1〜C11 の番号を根拠に付ける。
  **探索型監査 (C12)** — 原則リストへの適合は根拠に**しなくてよい**。代わりに
  (a) 文書の記述の引用 (§ + 引用。想像上の実装ではなく文書に書かれた規範を対象にする) と
  (b) **具体的な再現シナリオ (初期状態 → 操作列 → 壊れる状態)** の両方を必須とする。
  シナリオを構成できない抽象的な懸念は「proposal」に分離する
- 検出 0 件の観点も「確認済み・問題なし」として明示的に列挙する (沈黙を合格とみなさない)。
  探索型監査では「実行したが問題が出なかったシナリオ」も探索ログとして報告する

### 設計原則 (正本 — この通りに文書へ反映されているべき決定事項)

**P1. 三層構成**: 層 1 = 各フォルダの `.folder-history/` (metadata.sqlite + objects/ + repository-id) が
**唯一の真実**。層 2 = アプリ配下 app.sqlite の運用層 (folders / batch_requests / **cost_ledger** /
**app_config** (§8 現行設定の実体) + 検知キャッシュ 4 表 = watch_roots / scan_cache / fp_cache /
pending_deletes) は二重投入ガードと課金台帳であり真実を持たない (喪失 → 差集合から再構築可。
損失は規約 7 が **6 点列挙**する: (a) 未回収 job の再投入 (**全損時は喪失時点の in-flight 全 job が
対象** — 「server = 未追跡 1 job」はアプリ健在時のクラッシュ窓の主張 (§9.1) で、全損はその有界化の
外 (§10)。client = attempts 上限内。クラッシュ窓の主張を全損の損失列挙に流用した旧文言の残存は不備) / (b) cost_ledger の課金履歴 /
(c) terminal failed の抑制 — 恒常失敗対象は再び attempts 上限まで再投入 = 対象ごと有界 /
(d) 未完了の明示再生成 intent — 再操作で回復 / (e) in-flight の upload_id・intent_token —
provider upload の識別不能で保持期限までの機密残留 / (f) **app_config の現行設定 (tool / embedding
profile・画像フィルタ設定 §8)・unregister の退役事実・watch_roots 外の登録フォルダの個別パス** —
bootstrap で再入力・再確認 (§21.5)。「最悪 1 job 分」だけの記述は不正確。**§2 の損失要約も
(a)〜(f) + 有界 2 種に同期済み** (規約 7 を正と明記 — 旧要約 (a〜e 相当のみ) の残存は N25 の
regression)。**app.sqlite のバックアップ (規約 7「課金履歴の保全が要件なら別途取る」の実体) =
SQLite Online Backup API / VACUUM INTO** — WAL 中の main ファイル単独 raw コピーは commit 済み
ledger を失うため禁止 (§13 バックアップ規範)。**「有界」の内訳は 2 種と明記されていること**:
(a)(c)(d)(f) = 対象・操作ごとに有界な再実行コスト / (b)(e) = 運用量に比例する不可逆な記録喪失 —
後者の「有界」は件数上限ではなく「層 1 の真実に波及しない」の意味)。
規約 9 に**「真実」の語の二層注記**があること — 真実 = 履歴・派生・検索の正本。内容 (Evidence) の
正本は原本ファイル自身 (§1) で履歴メタデータは使い捨て可、の二層は矛盾しない。
層 3 = 同 app.sqlite の集約層 (agg_*) は横断検索キャッシュであり真実を持たない (丸ごと喪失 →
全フォルダから再レプリケーションで完全復元)。

**P2. 識別子規範**:
- 原本 identity = content_hash (bytes の SHA-256)。コミット identity = commit_hash
  (正規化レコードの SHA-256。nonce / device_id を含まない。created_at は含む)。
  直列化は **RFC 8785 (JCS)** の commit_record JSON で確定 ("v":1 = hash_format_version、
  created_at は UTC ミリ秒整数、値の無いフィールドは省略 (null リテラル不使用)、hash は
  小文字 hex64 の JSON 文字列、repository_id は小文字・8-4-4-4-12・brace / urn なしに固定、
  changes は NFC 正規化済み file_name の UTF-8 バイト列昇順、
  test vector の作成を実装の最初の作業とする — §4.1 が正本)
- **派生 (Markdown) の同一性判定は `(content_hash, tool_profile_hash)` の行の存在**で行う。
  markdown_hash など派生バイト列の hash は保存アドレスと破損検出のみに使い、
  同一性判定・再生成判定・dedup 判定には**絶対に使わない** (LLM 出力は非決定的なため)
- tool_profile_hash の入力 = 解決済みの**版付き**モデル名 + annotation スキーマ + 呼び出しオプション。
  可変 alias (例 mistral-ocr-latest) での呼び出し・pin は禁止
- embedding_profile_hash は単一 multimodal profile に固定。起動時検査は embeddings 全行一致 +
  **embedding_vec 表の存在・次元一致 (次元の参照元 = app_config の embedding_profile record —
  「§5.7 の record から読む」の残存は誤り: §5.7 は履歴保管庫で新規フォルダでは空。**§8 冒頭・§8-c・
  §10 step 3・§5.7 末尾の全参照点で app_config に統一済み — 1 箇所でも「(§5.7 record)」が残れば
  regression** (r14 で残存 2 箇所を補修した経緯 = Q01)。フォルダ単独は
  §11.2 の決定規則 — :current_profile = 一意 profile 規則 / :current_tool = 最新 generated_at 規則
  (P12))**。変更 = 現行設定の更新のみで宣言的収束 (P8)。
  **vector BLOB は IEEE-754 float32 little-endian 固定** (異 endian 機コピーで黙った誤順位)、
  **vec0 の distance_metric は profile record から展開** (cosine 固定リテラルは profile の距離変更を
  無視する)。なお具体的プロバイダは未確定 (文書中の gemini-embedding-2 / 768 / cosine は参考値) —
  確定値のように断定していたら指摘する
- **JCS の整数規則**: created_at は UTC ミリ秒の数値 (2^53 未満を規範で保証)。**size_bytes は
  10 進文字列** (ファイルサイズは 2^53 超があり得る — 数値のままだと実装が拒否/丸めに分岐)。
  統一規則「2^53 超があり得る整数は 10 進文字列」は profile_record の options 内整数にも適用
- **text_hash = SHA-256 (chunk text の UTF-8 bytes — 追加正規化なし)**、image_hash = SHA-256
  (画像 bytes)。profile_record (tool / embedding 共通 JCS) の embedding 側 options には
  dimensions / distance_metric / L2 正規化の有無を含め、**record そのものを profiles 表 (§5.7)
  へ永続化**する (hash は不可逆 — フォルダ単体からクエリ embedding の作り方を復元するため)

**P2 追補 (r16)**: profile_record の **model は provider / adapter 名前空間を含む解決済み完全修飾名**。
tool / embedding の構造的排他は adapter の**書込前 shape 検証**で強制する (tool = annotation_schema
必須 / embedding = options 内 dimensions・**distance_metric** 必須 — フィールド名は §4.1/§5.6 と同一の
distance_metric で「metric」等の別名不可。他 kind の必須フィールドを持つ record は拒否)。
**P2 追補 (r17)**: §4.1 の record 例は **kind 別 2 形に分離** — embedding 用は annotation_schema を
持たない (共通形は存在しない — 共通例の残存は shape 検証と矛盾し hash を分裂させる)。
**P2 追補 (r18)**: 10 進文字列 (size_bytes 等) の字句形 = **先頭ゼロなしの最短表記**に固定。
heading_path の JSON 直列化 = **raw UTF-8 固定 (\uXXXX escape 禁止)**。

**P3. metadata.sqlite は 8 テーブル**: commits / file_versions (元設計から不変) /
markdown_documents / chunks / chunk_fts / embeddings / embedding_vec / **profiles (§5.7)**。
markdown_documents は「**行の存在 = 生成完了**」であり status / error 列を持たない
(submitted / failed は app.sqlite 側の責務)。profiles は profile_hash (PK, blob 32) / kind (1/2) /
record_json (JCS bytes) — markdown_documents / embeddings を書く同一 Tx で INSERT OR IGNORE、
書込境界で SHA-256(record_json) = profile_hash を検証。**PK が hash 単独で足りるのは tool /
embedding の record が構造的に交わらない (必須フィールドが排他) ため — この前提の注記が必須**
(record 仕様変更時は kind 判別フィールドで hash レベル分離。注記の欠落は minor)。「7 テーブル」の言及が残っていたら誤り。

**P4. chunks 統一テーブル**: text と image を 1 テーブルで管理する。
- chunk_type (1=text, 2=image)、`text` は NULLABLE (type=2 では annotation + キャプション、無ければ NULL)
- CHECK: type=1 → text / text_hash が NOT NULL かつ image_hash / media_type / image_meta が NULL。
  type=2 → image_hash / media_type が NOT NULL かつ (text IS NULL) = (text_hash IS NULL)
- `embed_hash` は GENERATED 列 = COALESCE(image_hash, text_hash)
- **commit_hash 列を持たない** (版対応は file_versions の content_hash 逆引き)。
  **vector 列を持たない** (vector は内容単位で共有、N chunks : 1 vector)
- chunk_id INTEGER PRIMARY KEY (rowid テーブル — FTS external content の content_rowid に必要)。
  UNIQUE (content_hash, tool_profile_hash, seq)。FK → markdown_documents ON DELETE CASCADE。
  **seq / char_start / char_end に CHECK** (typeof='integer' + seq≥0 + char_start≥0 +
  char_end≥char_start — INTEGER affinity だけでは seq=0.5 / span=[7,3) を弾けず §12 preview キーが壊れる)

**P5. チャンク分割**: 入力は **objects/ に保存済みの Markdown 全文** (OCR API 応答ではない。
include_blocks は使用しない。**sidecar は存在せず Markdown が完全自己記述**)。規則 =
(1) ATX 見出し (行頭 1〜6 個の # + 空白) が境界、コードフェンス内の # は見出しでない、
setext 対象外 (2) heading_path = 有効な見出しスタック、最初の見出し前は []
(3) img block (P6) の画像参照行 1 つ = 独立 image チャンク、seq は text/image 通し採番。
image チャンクの text = img block の description + transcription の値のみ (無ければ NULL)。
**image_meta は img block の page / bbox / source_id / image_type から充填** (Markdown から
常に再構築可能) 。**文書由来キャプションは image チャンクへ取り込まず本文に残す**
(4) 画像参照行とその直後の img block は text チャンク本文から**除去** (text_hash の安定化)。
**認識は行全体一致のみ** (値の途中への部分一致は禁止)。**image はチャンク境界ではない** —
セクション途中の画像は前後本文を 1 チャンクに連結、span は除去前位置
(5) max_chars 超過セクションのみ段落境界で補助分割、heading_path 共有
(6) **opt-in フィルタ (P8) ON 時、除外条件該当の画像参照は image チャンクを生成しない**
(規則 4 の除去は行う)。分割規則・フィルタ設定の変更は OCR 再課金なしのローカル再解析だが、
**同一 Tx で markdown_documents.generated_at を単調更新 (max(now, 旧+1)) することが必須**
(集約層 §9.3-b の置換検出が generated_at 比較のため)。
**floor の同時引き上げ (必須)**: generated_at を進める全ローカル変換 (再チャンク・フィルタ変更・
grammar 再 materialize) は、対象の batch_requests 行に floor_generated_at が設定されていれば
**floor も新 generated_at 以上へ引き上げる。順序は app (floor) → metadata (generated_at)** —
逆順・欠落は明示再生成を silent cancel し、in-flight なら課金済みの新 OCR 結果を破棄して成功報告
する (§7 にこの規範が実在しなければ not-fixed — r9 で 6/6 系統が欠落を検出した箇所)。
一括再チャンクは中断後**全量やり直し** (規則版を行に持たない — 冪等・再課金ゼロ。**再開駆動 =
明示操作の再実行**・未完了は status — 自動再開の常駐機構は持たない。**一括変換の開始時に
app_config へ operation record (種別 + 目標規則/フィルタ record or hash + 開始時刻) を書き全量完了で
消す** — 行に規則版を持たないため、これが無いとクラッシュ後に「未完了の一括変換」を status が判定
できない。record は hint (正しさは再実行の全量置換が担う) — 欠落は不備)。
**規則 1 の code fence は CommonMark の fenced code block 規則に固定** (```/~~~・3 個以上・
行頭 0〜3 空白・同種かつ開始以上の長さで閉じ・EOF まで未閉なら残り全文をフェンス内。4 空白
インデントのコードブロックも見出し抑制の対象) — 未固定は実装間で text_hash が分岐する。
**規則 4 の除去単位 = 「行全体 + 行末 LF」・空行圧縮なし** (test vector に例を含める)。
**un-escape**: §6 の phantom 防止で行頭 `\` を前置された行は、チャンク text 生成時に `\` を
1 つ除去する (可逆 — 除去しないと原文と異なる text が FTS に恒久残留。char span は保存済み
Markdown 上の位置のまま)。**un-escape の対象判定は §6 のエスケープ条件と同一の緩いパターン
(1 個以上の `\` + 行頭 `![`+`](obj:` または `<!-- img:`) であり、hash64 の妥当性・行全体の厳密
grammar 一致を要求しない** — decoder を厳密一致に限る読みは `\![diagram](obj:see appendix)` 型
(§6 一致・厳密 grammar 不一致) の `\` を残留させ往復可逆が破れる (= major regression)。**画像
チャンクとしての認識は行全体の厳密一致 + 実在検証のままで不変** (un-escape の拡張は phantom 防止を
弱めない)。**除去・un-escape 後の本文が空白のみになる文書 (画像のみ・フィルタで全画像除外) は
text チャンクを生成しない** (空チャンクの有無の実装分岐は seq / FTS / embed を分岐させる)。

**P5 追補 (r16)**: 一括変換の operation record の保存先 = **app_config key = 'bulk_operation'**
(§9.1 の許可 key 集合の一員、存在条件 = 一括変換実行中のみ・全量完了時に消す)。
**P5 追補 (r17)**: img block の **v 混在 = fail-closed** (先頭 block の v で入口判定 + 全 block の
一致検査 — 混在は未知の v と同様に解析停止 + status)。

**P6. OCR**: Mistral OCR 4。include_image_base64=true、bbox_annotation 既定 ON
(スキーマ: image_type / short_description / transcription)、**OCR はすべて Mistral Batch API**
(JSONL の custom_id = target_key、timeout_hours=24。50% 割引は OCR にのみ確定)。
料金: 標準 $4 / annotation 付き $5 (+25%) / Batch 50% 割引で**実効 $2.5 per 1,000 ページ**。
**課金単位は同一 (content_hash, tool_profile_hash) につき 1 回** (content_hash 単独と書いて
あったら誤り — tool 変更時は同内容でも再 OCR)。保存時変換: 画像 base64 → decode → objects/
(image_hash)、画像参照を **canonical img block** へ置換して materialize する。grammar は固定形 —
参照行 `![<alt>](obj:<image_hash64>)` (単独行。**alt = annotation ON なら short_description、
OFF なら source_id**) + 直後の img block `<!-- img:<image_hash64>` 〜 `-->`。field の順は
**v / page / bbox / source_id / media_type** (meta **5 行** — v = grammar version (現行 1、
将来変更は +1 して一括再 materialize。**版判定は保存済み Markdown の先頭 img block の v: 行 —
img block を 1 つも含まない (画像 0 件の) 文書は grammar version の対象外として常にスキップ**
(「v 不明 = 旧版」扱いは無意味な再構築 + generated_at 更新が agg へ伝播 = 誤り)。**未知の v
(解析器より新しい版) を含む Markdown の再解析は fail-closed でスキップ + status** — テキスト扱い・
推測 dispatch は chunks / text_hash を実装依存に分岐させる)。**annotation の有無に関わらず常に出力**。
media_type は画像 bytes のマジックバイトから決定論的に判定した MIME、判定不能は
application/octet-stream) → image_type / description / transcription (annotation ON のみ)。
各値は 1 行に正規化、エスケープは可逆 (`\`→`\\` の後 `-->`→`--\>`)、LF 改行。
**pages[].markdown の結合は page index 昇順 + 各ページ末尾の改行を 1 つの LF に正規化して join**
(直結だと次ページ先頭の ATX 見出しが行中に埋もれる — 結合規則も決定論的に固定)。
**本文エスケープ (phantom 防止の行頭 `\`) はページ結合後の全文に対して行う** (ページ単位に先へ
掛けると結合が新たに作る行頭を取り逃がす)。**エスケープの対象は「0 個以上の `\` に続いて
grammar 形が現れる行」であり、常に `\` を 1 個前置する** (G→\G、\G→\\G — §7 の un-escape
(1 個除去) と全段往復可逆。**裸の grammar 形のみを対象にする旧規則は誤り** — 元から `\` +
grammar 形だった本文行が素通りし un-escape が原文を変質させる。test vector に 3 段
G / \G / \\G の往復例を含める)。**エスケープは OCR 応答由来の本文への保存時 1 回限りの変換 —
grammar 再 materialize は本文を保存済み Markdown (エスケープ済み) から引き継ぐため再適用しない**
(再適用は「0 個以上の `\` + grammar 形」に再一致して `\` を版ごとに累積させる = 不備)。結果を objects/ へ保存 (markdown_hash)。**sidecar の持ち回りは存在しない** (image_meta は img block の page / bbox /
source_id / image_type から、chunks.media_type は media_type 行から充填する)。
preflight: 対象外形式・512MB 超過は **upload せず terminal marker 行 (error='unsupported_format' /
'oversize'、attempts=上限) を 1 回だけ作る** — 「status 表示のみで行を作らない」記述は毎 tick
再判定の無駄ループになるため誤り。upload 後始末は upload_id 記録 + state 独立の掃除 (P9)。
結果失効 (result_expired) の再投入は **attempts 上限内のみ** (無限の失効 → 再課金ループにしない)。

**P6 追補 (r16)**: Batch 入力 = **JSONL の各行が upload 済み原本の file id を参照** (base64 内嵌は
不使用 — JSONL 膨張と 512MB 判定の乖離防止)。**JSONL 自身の upload も filename への token 埋込の
掃除対象** (upload_id 列は原本用 — JSONL id は列に持たず filename 規約で追跡)。**投入直前に
objects bytes の SHA-256 を再計算して名前と照合** (不一致は投入せず fsck へ — 破損 bytes から派生を
作らない)。
**P6 追補 (r17)**: オフィス文書の**変換 PDF は一時生成物** — objects/ へ保存しない・content_hash /
照合の対象は常に原本 bytes・投入直前再照合は原本 → 照合後に同一コンバータで決定論的に再変換して
upload・**upload_id 列と token 埋込 filename は変換物 (実際に upload した bytes) に適用**・課金入力は
job 応答から。
**P6 追補 (r18)**: Batch 入力の JSONL は「upload 済み**入力** (原本 — Office 文書は変換 PDF) の
file id」を参照 (「原本の file id」ではない)。§9.1 相 2a も「入力 upload」。**変換の失敗分岐**:
決定論的失敗 = state=3 (error='convert_failed', attempts=上限) を 1 回だけ / 環境起因 = 行を作らず
次 tick + 共通 backoff + status。**512MB 上限は変換後の bytes にも適用** (検査は変換してから)。
**P6 追補 (r19)**: upload 対象語は**全所「入力 (原本 — Office 文書は変換 PDF)」に統一** (「列は
原本用」「upload 原本の削除」等の残存 = 非伝播)。例外 = 投入直前の再照合のみ「原本」。alt の
escape = **1 行正規化 + label 置換一度だけ** (field escape との二重適用禁止)。

**P7. FTS**: FTS5 **external content** — content には **view `chunks_fts_src` (SELECT chunk_id,
text, heading_path FROM chunks WHERE text IS NOT NULL)** を指定し content_rowid='chunk_id'。
**content='chunks' の直接指定は誤り** (text=NULL の image 行が content 側にだけ存在し、FTS5 の
integrity-check / rebuild と整合しなくなる)。agg 側も同形 view (agg_chunks_fts_src)。
tokenize は trigram (既定)。trigger は **chunks 表に張り** INSERT / DELETE のみで
**WHEN text IS NOT NULL** の条件付き。
**UPDATE trigger は張らない** — chunks / embeddings の行は UPDATE 禁止、置き換えは DELETE → INSERT。

**P8. Embedding は必須**: type=1 は text を、type=2 は objects/ の画像 bytes を、
**同一 multimodal ベクトル空間**に embed する (text 用と image 用に別モデル・別空間は禁止)。
**既定は全 chunk が対象**。opt-in 画像フィルタ (既定 OFF) の実装は **P5 規則 6 の
「image チャンクを生成しない」方式**であり、「chunks は残して embeddings 行だけ作らない」
記述があれば誤り (FTS / KNN / submit の一貫性が壊れる)。**フィルタ設定は app_config に canonical
record + hash で永続化し、app 全損後の bootstrap で再入力する** (規約 7-f — 未永続だと既存 chunks が
どの設定で作られたか復元できず差分検出不能)。設定変更は P5 の再チャンク経路で反映し、切替前に投入済み
job の残骸は孤児掃除 ((chunk_type, embed_hash) ペアから参照されない embeddings 行の削除) が回収する。embeddings の行キーは**常に** (chunks.chunk_type,
chunks.embed_hash) — それ以外のキーの行は検索 join から到達できないため**禁止**。
embedding_vec は vec0 の導出物 (target_key = target_type || ':' || **lower(hex(target_hash))** —
**小文字固定**、float[<dim>] distance_metric=cosine の **DDL テンプレート** — profile 未確定のため
次元はプレースホルダであり、768 は参考値。L2 正規化済み)。embeddings が正、不整合時は
embeddings → embedding_vec の順に再構築。
**profile 変更 = 「現行 profile 設定の更新」1 操作のみで宣言的に収束する** — 多段の手動手順・
kind=2 batch_requests 行の一括削除の記述は誤り (手順途中クラッシュで壊れる中間状態を作る)。
**設定の適用前に vec0 の受理検証 (新 record の <dim>/<metric> で一時 CREATE 試行 — 拒否は commit
せず status) が必須** (無検証 commit は §8-c/e の DROP → CREATE が毎 tick 失敗し KNN 恒久停止 = 不備):
(a) **成果判定が profile を含む** (kind=2 の成果 = 行の存在 + embedding_profile_hash = 現行。
旧 profile 行は成果なし → 自動再投入。terminal の課金ガードは **profile 内で計数** —
profile_hash ≠ 現行の再投入では **state を問わず** attempts=0 に数え直す。terminal 限定だと
state=2 の旧 profile 行が旧 attempts を引き継ぎ新 profile 初回失敗で即 terminal。
submission_seq はリセットしない — P9)、(b) collect の置換 = 同一 Tx で
embedding_vec → embeddings の順に DELETE → INSERT、(c) vec 表は Embed submit 冒頭で
**次元 + 距離 (distance_metric) を照合 → いずれか不一致なら DROP → CREATE** (距離のみ変更が次元一致で
見逃され旧 metric の順位が残る残存は誤り。vec0 の distance_metric は profile record から展開する
`<metric>` テンプレート — cosine 固定リテラルは誤り。**照合の「現行 profile」参照元 = app_config の
embedding_profile record — 「(§5.7 record)」の残存は regression (Q01)**。**profile hash 自体は照合
しない — §8-e と意図的に非対称**: フォルダ層は「vec を構築した profile」の耐久記録を持たず、次元・
距離同一の切替は b の行単位置換 + §11.2 一意 gate の KNN 縮退が覆う、と文書に注記されていること
(注記の欠落は不備))。**さらに次元・距離一致でも毎回、embeddings の
現行 profile 行のうち vec に無い target_key を差集合で冪等再充填** (「次元照合だけ → DROP/CREATE 後に
再充填」だと CREATE 済み・充填途中クラッシュの半端な vec を検出できず欠落が永久化する — 差集合再充填で
ないなら誤り)、(d) 旧 profile 行の一括掃除は任意 (同順で削除)、(e) **集約側は毎 tick の宣言的検査**
— Replicate 冒頭で agg_vec の次元 + 距離 × app_config の agg 構築 profile を現行と照合し不一致なら破棄→
再作成 (**破棄の実体: agg_embeddings は行 DELETE、agg_vec のみ DROP → CREATE** — 通常表を schema ごと
消す読みを誘発する係り受けは不備。「profile 変更イベント時に一度だけ破棄・クラッシュ位置を問わない」は誤り = 一度破棄が飛ぶと
agg_vec が旧次元で残り §9.3-c の新次元 INSERT が毎 tick 落ちる)。**破棄 (building 書込 + wipe) と
同一 app Tx で sync_state.synced_profile_hash を全行 NULL に戻す** (残すと profile 再訪 P2→P3→P2 で
陳腐化した synced=P2 が即・全一致し wipe 直後の空 index が ready を騙る — 欠落は major regression)。
**building / ready 2 key の ready 更新は「接続フォルダすべてが synced_profile_hash = building」で
判定** — **母数 (接続フォルダ) = 「当該 tick に metadata を開けて §9.3 を実行できたフォルダ」**
(missing / fork 中 / **damaged / 一時読取不能**を除外 — 「missing と fork のみ除外」の残存は major:
damaged は root_path 現存で missing にならず、1 フォルダの破損が横断 KNN を恒久停止させる)。
**接続 0 件中は ready を更新しない** (空虚な真の防止) + status。
各フォルダの synced_profile_hash は §9.3-c が (i) 現行 profile eligible chunk の embeddings 被覆完了
かつ (ii) agg への複製差集合が空 で building へ UPDATE する (被覆条件なしの「全フォルダ完了」判定は
0 行コピーの空 index が ready を騙る)。**ready は「設定時点の被覆」の宣言** — 設定後の新規 content の
embed 遅延・除外フォルダの復帰分による部分性は通常状態 (未 embed 残数は status)、と明記。
**same-profile の agg_vec silent 欠落は §8-c 同型の差集合冪等再充填** (集約は cache だが profile 変更を
伴わない行喪失は破棄・再構築まで KNN から永久欠落。fsck §13 も agg 差集合を**双方向**に検査 —
vec 孤児は §9.3-c の DELETE→INSERT 投入が上書きで無害化)。embeddings は
vector 長 (= 4 × dimensions)・dimensions > 0・**vector BLOB は IEEE-754 float32 little-endian 固定**・
hash の typeof='blob' を CHECK で強制する。
**server-side batch の無いプロバイダ (client 側キュー) の写像は「実行前計上」**: 同期 API を
呼ぶ**前に** app Tx で attempts+1・submission_seq+1・batch_job_id = intent_token (実行 id 流用 —
ledger の記帳キー)・submitted_at・**投入時 profile snapshot (kind=2 は profile_hash = 現行、
kind=1/2 とも profile_record = 現行 — 相 1 と同じ書込)** を永続化 → 成功したら同 tick 内で即 collect
(profile_hash / record を欠くと kind=2 DDL CHECK 違反で前計上不能・§5.7 保存不能)。**呼出失敗は
相 2b と同じ 2 分岐** (一時 = 前計上のまま次 tick + retry_not_before / 恒久 4xx = submit_rejected +
attempts=上限・記帳なし (**「内容起因 4xx = 課金なし」はプロバイダ前提と明文化されていること** —
拒否にも課金する provider ではこの分岐にも記帳を足す、の注記)・**同 Tx で batch_job_id を NULL へ戻す** — 残すと後日の成果あり close の
付随処理 (b) が「未実行と確定した attempt」を誤記帳する。未分岐は client だけ attempts を浪費)。クラッシュ回復は
「前計上済み行 = 実行された可能性あり」として遷移表の attempts 上限に従い再実行するが、
**再実行の前計上 Tx では、まず直前 attempt の submission_seq を NULL + estimated で冪等 terminal
記帳 (ON CONFLICT DO NOTHING) してから attempts+1・seq+1 する** (client_exhausted の一般化 —
上限到達時のみ記帳する旧形の残存は major regression: 中間 attempt の課金が台帳から永久欠落)。
**再実行は相 1 の規則一式を含む** (profile 不一致の attempts=0 数え直し + snapshot 書き直し —
dispatch 経由で相 1 を迂回すると旧 profile の attempts を新 profile が引き継ぐ)。
**「state=0 = 未実行として無条件再実行」の記述は誤り** (呼出中クラッシュを識別できず無限重複
課金)。**「重複課金は最悪 job 1 回分」は server-side batch 経路限定の主張** — client 経路は
attempts 上限 (既定 3) による有界化に留まる、と明記されていること (P9。**§10 側の再掲にも
server 限定の明記が必須** — 無限定の再掲は文書内矛盾)。

**P9. バッチ処理情報は app.sqlite の batch_requests + cost_ledger のみ**:
batch_requests は**可変のガード行** (真実・課金履歴を持たない)。PK (repository_id, kind, target_key)。
kind=1 (OCR) の target_key = hex(content_hash)||':'||hex(tool_profile_hash)、kind=2 (embedding) =
chunk_type||':'||hex(embed_hash) (**hex は小文字固定** — §11.2 の契約と同一)。
**state 0=submit intent / 1=submitted / 2=done / 3=failed**。batch_job_id は nullable +
CHECK (state <> 1 OR batch_job_id IS NOT NULL) (client 経路は前計上で state=0 でも実行 id を持つ)。
列に intent_token / upload_id / upload_cleaned / profile_hash / **profile_record (投入時 snapshot —
kind=1 は tool / kind=2 は embedding の record。collect の §5.7 profiles INSERT はこの snapshot
由来 — current 参照だと tool / profile 切替中の in-flight job の record を復元できない)** /
floor_generated_at / **submission_seq (リセットしない通算投入連番)** を持ち、**cost_usd / pages
列は持たない** (課金は cost_ledger)。**DDL の追加 CHECK 3 種**:
`CHECK (state NOT IN (0,1) OR profile_record IS NOT NULL)` (相 1 / 前計上の必須 snapshot を
スキーマで強制 — terminal marker は対象外) / `CHECK (floor_generated_at IS NULL OR kind = 1)` /
`CHECK (upload_cleaned IN (0, 1))`。
**cost_ledger.batch_job_id (NOT NULL) の値規則**: server job id / client 実行 id (= intent_token
流用) / **無 id 記帳 (期限超 confirmed-absent — intent 回復・detached・(b')/token sweep 前段の
期限超分岐) = intent_token** / **job 発見記帳 ((b')・sweep 前段の found) = 照合で発見した実 job id**
(sweep を intent_token 側へ一括分類した旧 DDL コメントは本文と矛盾 — r14 で正確化済み。分類矛盾の
残存 = 述語キー分裂で二重記帳 = 不備) — **値規則が無いと期限超記帳の INSERT が NOT NULL 違反で intent 回復ごと
恒久停止する (fatal — r13 で 4 系統検出・SQLite 再現)。この列は「記帳済み判別」の突合キーを兼ねる**。
**attempts (リセット可能な再試行ガード) と submission_seq (リセットしない課金記帳キー) は別物** —
attempts = 照会失敗で消費しない再試行カウンタ、上限は app 設定 (既定 3)、明示 retry / profile
数え直しで 0 に戻る。submission_seq は job 作成 / client 実行のたびに +1 し**決して戻さない**。
**行の新規 INSERT 時の seq 初期値は 0 ではなく cost_ledger の同キー MAX から継承する**
(COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE 同キー), 0) — **batch_requests 行を
新規 INSERT する全経路 = 相 1・client 前計上・§5.3 明示再生成 INSERT・§6 preflight terminal
marker INSERT** に適用 (規則の無例外化 — marker は課金を持たないが実装判断を残さない)。「register 後の
全行作成」の旧表現は誤読誘発 — register は行を作らない)。**0 起点の残存は fatal regression** — 行は削除される (unregister /
退役 / fork) が ledger は永続のため、再登録後の再投入が旧 ledger 行と UNIQUE 衝突して close Tx
(state=2 + ledger 同一 Tx) が恒久失敗する (seq の high-watermark の正本は ledger 側)。
**cost_ledger は追記専用** (UPDATE / DELETE 禁止 — profile 変更 §8 でもフォルダ退役 §9.3-d でも
削除しない)。ts / batch_job_id / pages / cost_usd を記録し、**月次コストは ledger の ts で集計** (**ts = 課金の
確定 (collect / close 記帳) 時刻 = 確定月への配賦** — provider 側の請求発生時刻とは長期停止で数か月
ずれ得る。正はプロバイダ側 §16。「発生月へ正しく配賦」の旧文言の残存は不備)。
**cost_usd は NULL 許容** + cost_estimated。**UNIQUE は (repository_id, kind, target_key,
submission_seq)** — **attempt をキーにした UNIQUE は fatal** (attempts リセット後の正当な再課金が
同番号を再利用して close Tx = state=2 + ledger 同一 Tx が UNIQUE 衝突で恒久失敗する。
r9 で SQLite 再現済み)。
**app_config** (key-value) が §8 の「現行設定」の実体 — key 契約は **7 種の許可 key 集合 +
key 別の存在条件** (profile 系 = bootstrap 再入力後は必須 / retry_not_before = 抑止中のみ /
agg 2 key = 構築開始後 / fork_in_progress = fork 中のみ。**「すべて必須」の残存は bootstrap 直後・
非 fork 時の正常状態と矛盾 = 不備**) (r11 時点は 6 種 —
プロンプト旧版の「5 種」は転記ミス): 'tool_profile' /
'embedding_profile' の record、'image_filter' の record (§8。既定 OFF・hash key は持たない)、
'retry_not_before' (submit / collect の provider・kind 別抑止期限 JSON)、'agg_building_profile_hash' /
'agg_ready_profile_hash' (§8-e。hash は lower hex64)、'fork_in_progress' (§21.3 — fork 中のみ存在)。**旧単一 'agg_embedding_profile_hash' が
DDL コメント・本文に残存していたら major** (§11.2 の agg_ready 照合が永久不一致で KNN が恒久停止)。
**横断検索のクエリ embedding はここから生成する** (P12)。
**状態遷移は規範**: 行の INSERT は初回のみ、以降は UPDATE (PK 衝突の構造的排除)。
**profile 未設定 (bootstrap 直後 — app_config に当該 kind の現行 record が無い) の間は、その kind の
submit / client 前計上に加えて **reconcile / collect の成果判定・§8-c の vec 検査 (kind=2)・
§8-e / Replicate の agg 構築 profile 検査も対象選定ごと skip + status「profile 未設定」** (現行
record が無いと成果判定と `<dim>`/`<metric>` 展開が構成できない。**state=1 は不変で保留** — 再入力後の
collect が回収・記帳する。DDL CHECK は fail-closed に
拒否するが、期待挙動は skip であって tick 中断・エラー連発ではない — 明記の欠落は不備)。
**「フォルダ成果あり」の定義は submit / reconcile / collect の全経路で統一** —
kind=1 = markdown_documents 行が存在し、かつ floor_generated_at が NULL または
generated_at > floor (明示再生成 P後の旧行は成果なし)。kind=2 = embeddings に
(target_type, target_hash) 行が存在し、かつ embedding_profile_hash = 現行 (P8-a)。
submit 判定: 成果あり → 投入せず、**state IN (0, 3) は state=2 へ閉じる。state=1 は閉じない**
(collect の冒頭スキップだけが実測課金と同時に閉じる。**reconcile / submit が state=0|3 を閉じる
際は同一 app Tx で付随処理を行う**: (a) kind=1 は floor_generated_at を NULL へ戻す — 残すと
後日のローカル変換 §7 が floor を引き上げて完了済みの明示再生成が不要な再 OCR を点火する /
(b) batch_job_id 非 NULL なら cost_ledger へ NULL + estimated で冪等記帳 — client の「metadata Tx 後・
app Tx 前クラッシュ」は state=0 のまま成果ありになり reconcile が唯一の close 点のため、記帳
しないと実課金が台帳から永久欠落する / **(b') state=0 server (batch_job_id NULL)・intent_token
残存の close は、(c) の掃除の際に token 照合で job 実在を確認し、実在すれば掃除前に小 Tx で
batch_requests.submission_seq を +1 へ UPDATE + その新値で NULL + estimated を冪等記帳し、**同じ
小 Tx で行の batch_job_id へ発見 job id を書く (自己記述化)** (ledger の batch_job_id =
発見 job id)** — **行 UPDATE の明記が必須** (記帳だけで行 seq を進めないと次の正規記帳が旧値から同じ
+1 を計算して UNIQUE 衝突し、ON CONFLICT が実課金を黙って吸収する = major regression)。**自己記述化の
欠落も major regression** — found 記帳 (job id) → 掃除前クラッシュ → 一覧から消滅 → sweep の期限超
記帳 (token) が「未記帳」と誤認し、同一 job を述語の時間差分裂で 2 行計上する。
**confirmed-absent には intent 回復と同一の期限判定・伝播猶予を適用** — 期限超 (未来 skew・解釈不能
含む) は記帳済み判別 → seq 行 UPDATE + 記帳 (batch_job_id = intent_token) で**記帳してから** (c) へ、
期限内は記帳なしで (c) へ (期限分岐の欠落 = 保持期限で消えた課金済み job の無記帳掃除 = major
regression) — 相 2b 完了・相 3 前クラッシュの行は job 実在でも
batch_job_id NULL で (b) から漏れる (kind=2 の profile A→B→A が単一デバイスでこの行を成果あり化する。
detached (b) と同型) / (c) intent_token が残る行の upload / job 残骸の掃除は **close の app Tx の外**で
試みる (掃除条件 = **同 token 共有の全行が終端** — 先に閉じた行が共有 job を掃除すると残る行の回収
不能 = 二重課金。掃除失敗の再駆動は 4.5 の token sweep)。
**この付随処理により旧「既知の残余 (失効窓の課金行は記録できない)」は解消済み** —
残余文の残存は regression) / 成果なし: 行なし・state=2・
(state=3 & attempts<上限) → 投入対象 / state=0 → intent 回復 / state=1 → 回収待ち /
terminal → 明示操作のみ (kind=2 で profile_hash ≠ 現行は P8-a の数え直しで投入対象)。
**submit は 2 相**: 相 1 (app Tx) = 対象行を state=0 + 新 intent_token (**UUIDv7 — 時刻成分 =
相 1 実行時刻を intent 回復の期限判定に使う**。job 単位で共有) +
batch_job_id NULL 化 + **error / completed_at を NULL に戻す** + **投入時 profile snapshot を書く**
(kind=2 は profile_hash = 現行 — DDL CHECK が state 非依存で非 NULL を要求するため、初回 INSERT で
設定しないと embedding 投入が一切開始できない = fatal。kind=1 / 2 とも profile_record = 現行
record) + **profile_hash ≠ 現行の再投入は state を問わず attempts=0 リセット** (P8-a) +
**upload_cleaned を 0 に戻す** (戻さないと再 submit の新 upload が永久リーク) + 未清掃の旧
upload_id は **app Tx 外で**削除試行 — **削除は同 upload を共有する全行が終端 (2/3) の場合のみ
(4.5 と同条件 — 無条件削除は state=1 の同輩と共有する upload を消して回収不能 = 二重課金 = major
regression)**。**旧 intent_token 非 NULL のまま再投入する場合 (sweep 未完 terminal への明示 retry・
profile 変更経由) は、その token の未記録 upload 残骸の削除も先に試みる** (rotation の探索キー喪失
対策 — 期限超 (iv) と同規則) →
相 2a (外部 + app) = upload (**filename に intent_token**) → **成功直後に小さな app Tx で
upload_id を行へ記録** (相 3 まで遅らせると「upload 成功 → job 作成 4xx」で残骸 handle を失い
TTL まで機密残留)。**upload の失敗も相 2b と同じ 2 分岐** (一時 = 見送り + retry_not_before /
恒久 4xx = submit_rejected + attempts=上限 — 未分岐は恒久 4xx が毎 tick 再 upload する無限ループ)
→ 相 2b (外部) = job 作成 (**metadata に intent_token**)。
**失敗は 2 分岐**: 一時 (429 / 断 / 5xx) = state=0 のまま不消費で次 tick (**Retry-After は
app_config の retry_not_before に永続化し submit が期限まで見送る** — 非常駐 tick を跨ぐ抑制) /
**恒久拒否 (内容起因の 4xx) = state=3 (error='submit_rejected') かつ同 Tx で attempts = 上限を
設定** — terminal の実体は「attempts >= 上限」なので、attempts 据え置きの terminal 宣言だけでは
遷移表「state=3・attempts < 上限 → 投入対象」が次 tick に自動再投入して宣言と逆の無限ループに
なる (preflight marker と同じ手法。**据え置き宣言の残存は major regression**) →
相 3 (app Tx) = state=1 + batch_job_id + upload_id + **attempts+1 + submission_seq+1** +
submitted_at。**profile_hash / profile_record には触れない** (相 1 の snapshot 保持)。
**intent 回復** (submit 冒頭、state=0 の行) — **冒頭で dispatch**: batch_job_id 非 NULL =
client 前計上済み → job 一覧照合ではなく §8 (iii) の再実行経路へ (**attempts >= 上限なら
state=3 (error='client_exhausted') + 旧 seq の terminal 記帳 (NULL + estimated)** — client の
上限到達 state=0 は submit / reconcile / collect / 明示 retry / 滞留監視のどの対象にもならず、
この分岐が唯一の出口。**上限未満の再実行は §8(iii) の旧 seq 冪等記帳 + 相 1 規則一式を含む** —
P8)。batch_job_id NULL = server → provider の job 一覧を intent_token で照合 — **結果は三値**
(found / confirmed-absent / unknown。**二値 (見つかれば/見つからなければ) の残存は major
regression** — 照会失敗を不存在と解釈すると実在 job と二重になり「最悪 1 job」が破れる):
**found = 採用** (相 3 と同じ UPDATE = state=1 + batch_job_id + attempts+1 + submission_seq+1 +
**submitted_at=now** (時刻基準 job_missing の入力 — 列挙からの欠落は不備)。**snapshot は不変** —
採用時の current で上書きするとクラッシュと回復の間の profile 変更で旧空間 vector が照合を
素通りする = major) / **unknown = 照会自体の失敗 (429/断/5xx) は state=0 のまま保持**して次 tick
再試行 (Retry-After は retry_not_before へ) / **confirmed-absent = 正常応答に無い**場合のみ
載せ直しへ — ただし**期限判定を先に行う**: intent_token (UUIDv7) の時刻成分から (timeout_hours +
結果保持期限 + 猶予 1 日) を超えていれば「未作成」と断定できない (作成済み job が保持期限で
一覧から消えた可能性 — K08 の時刻基準と同じ枠組み。期限判定なしの載せ直しの残存は regression)。
**時刻成分が now + 許容 skew (既定 5 分) より未来・解釈不能な場合も期限超と同様に扱う** (安全側 —
未来時計 token は時計修正後に恒久「期限内」となり無記帳載せ直しになる)。**逆側の伝播猶予**: 時刻
成分が**過去側で** now から数分以内 (**0 ≤ now − token 時刻 ≤ 猶予 (既定 10 分)。未来側は対象外 —
未来 skew 判定が常に優先**) の confirmed-absent は unknown 扱いで保持 — job 一覧 API の
read-after-write 整合を仮定しない (dirty 早回し直後の照合が作成直後の実在 job を「未作成」と誤認して
載せ直し = 追跡不能の二重 job。猶予の欠落は不備)。**プロバイダ採用条件の明記が必須**: 「job 一覧の
可視化遅延の上限 ≤ 伝播猶予」を provider が満たす場合にのみ有界化が成立する (猶予は provider 別
設定可)。保証できない provider では猶予超の stale 正常一覧が attempts / seq / 記帳の消費なしの
載せ直しを反復させ未追跡 job を累積させる — 採用条件の欠落は不備。**期限判定・伝播猶予は intent_token を job 一覧と
照合する 4 照合点 (intent 回復・detached (b)・(b')・token sweep 前段) に共通適用と明記されている
こと** (照合点ごとの食い違いは major)。**期限超の処理は
すべて同一 app Tx**: (i) **記帳済み判別** — 同 (repo, kind, target_key) × batch_job_id = 当該
intent_token の ledger 行が既存なら記帳省略 (seq+1 もしない — **seq+1 は非冪等**のため、この
述語が無いと再試行のたび別 seq の推定行が増殖する) / (ii) 未記帳なら **同一 Tx で
batch_requests.submission_seq を +1 へ UPDATE し (相 3 / found 採用と同じ行更新 — 行 UPDATE を欠く
「記帳のみ」の残存は major regression: 次の正規 close が旧値から同じ +1 を計算し、この推定行と
UNIQUE 衝突して実課金の記帳が ON CONFLICT に黙って吸収される)、その新値で NULL + estimated
(batch_job_id = 当該 intent_token)** / (iii) **attempts+1** (作成済みであり得た
attempt の消費 — 数えないと相 2b/相 3 境界のクラッシュ反復が上限を素通り) /
(iii') **attempts >= 上限なら載せ直さず state=3 (error='expired') で terminal 化して (iv) を行わない**
(client_exhausted の server 対応物 — 出口が無いと (iii) で数えた上限が (iv) の無条件 rotation で
素通りし、外部 job と estimated 記帳が増殖する = major regression。token は (ii) で記帳済み —
掃除・NULL 化は 4.5 sweep が引継ぎ、復帰は明示 retry のみ) / (iv) 載せ直し相 1
(新 intent_token 書込。**期限内分岐と同じく、旧 token の upload 残骸 — filename の token 埋込で
発見できる未記録 upload を含む — の削除を Tx 外で先に試みる**)。**Tx 境界は「(i)〜(iv) の DB 書込
(載せ直し相 1 の行更新を含む) を 1 Tx」であり、(iv) の外部 upload 削除の呼出だけが Tx 外** —
「(i)〜(iii') を 1 Tx」のように (iv) を列挙から落とす表現の残存は regression (記帳・attempts
確定後・rotation 前のクラッシュ反復が、載せ直しゼロ回のまま attempts を再消費して偽 expired に
到達する)。**記帳と rotation を別 Tx にする
残存は major regression** (間のクラッシュで
述語の効かない別 token 世代が生まれる)。期限内は
同 token の upload 残骸を削除して載せ直し (新 intent_token で相 1 から)。
**kind=1 の載せ直しガード**: target_key の tool_profile_hash ≠ 現行 tool なら載せ直さず
state=3 (error='tool_changed', attempts=上限) — 現行 record で snapshot を書き直すと key の
tool と snapshot が食い違い、collect の §5.7 保存 (hash 検証) が必ず失敗する。新 tool の生成は
新 target_key が別行で通常投入される。
collect: 照会失敗 (429 / ネットワーク断) = **行不変・attempts 不消費・Retry-After を app_config の
retry_not_before に永続化** (submit 側と対称 — 同 tick 打ち切りだけだと非常駐 tick が期限前に再照会) /
**job_missing (404 = 恒久消滅) = state=3 (error='job_missing')** — 判別できないプロバイダは
**時刻基準** (submitted_at から timeout_hours + 結果保持期限 + 猶予 1 日を超えた state=1) で
判定する (「照会失敗が N 回続いたら」の回数基準は不可 — tick 非常駐で連続回数を保持できない) /
item 成功 = 冪等スキップ + kind 分岐 + state=2 + **cost_ledger 追記 (同一 app Tx。kind=1 は
floor を NULL へ戻す)** / kind=2 profile 不一致 = vector 破棄 + state=3 (error='profile_changed')
だが記帳 / item 失敗・job TIMEOUT = state=3 (item 失敗の記帳は「失敗にも課金する provider で欠落
しないため」— **非課金と契約上確定した provider では記帳省略可。「非課金 provider では ON CONFLICT で
無害に skip」の残存は事実誤認 = 不備** (ON CONFLICT は同一 seq の再観測のみ吸収・初回 INSERT は
成立する)) / 結果失効 = state=3 (error='result_expired') /
**output_missing は「provider 出力に custom_id が実在しない item」のみ** — 出力に在るがローカル
処理が**一時**失敗 (SQLITE_BUSY 等) した item は state=1 のまま次 tick 再処理 (これも missing に倒すと
成果取得可能なのに再投入 = 不要な再課金)。**出力に在るが決定論的に不正な payload (base64 / JSON 破損・
次元不一致・非有限 vector) は state=3 (error='invalid_output') + 記帳で閉じる** (一時失敗と同一視すると
state=1 が永久滞留) / **terminal 化時の課金記帳**: batch_job_id 非 NULL の成果なし terminal
(expired / timeout / missing / profile_changed / **invalid_output / item 失敗**) も ledger へ記帳
(実行された可能性のある課金を取りこぼさない。cost 不明は NULL + estimated)。**close 経路 (collect 成功 /
terminal 化 / reconcile・submit close / client_exhausted / detached) の cost_ledger 追記はすべて冪等
= `ON CONFLICT (repository_id, kind, target_key, submission_seq) DO NOTHING`** — 素朴 INSERT だと同一 seq
への 2 回目 (profile A→B→A で collect の profile_changed 記帳と reconcile close 記帳が同一 seq 衝突する
等) が UNIQUE で close Tx を abort させ恒久ループ (**「UNIQUE が二重計上を構造的に防ぐ」を字義どおり
残す = fatal**。防ぐ実体は「同一課金の再観測を黙って吸収」— **cost_ledger の DDL コメントも
この文言に統一済み** (旧「二重計上を構造的に排除」コメントの残存は regression)。
**ただし ON CONFLICT は「同一 seq の再観測」しか吸収しない — 無 id / (b') 記帳は seq+1 を伴う
ため非冪等であり、実行前に「記帳済み判別」述語 (同キー × batch_job_id = 当該 token / 発見
job id の既存 ledger 行なら省略) が必須** (述語なしの残存 = 再駆動のたび別 seq の推定行が増殖 =
major regression)。**(b') は unknown (照合失敗) なら記帳も掃除もせず保持** (次 tick の sweep が
再試行) / upload 後始末 =
「全行終端 (2/3) かつ upload_cleaned=0」を state と独立に掃除・再試行 (**不在応答 (404) = 削除成功** —
失敗扱いは毎 tick の恒久再試行・detached の恒久残留 = 不備) + **token sweep** (同じく
state 独立 — **まず (b') と同一の前段** — **ただし error='submit_rejected' (未作成/未実行の確定) の
行は照合・記帳とも行わず残骸掃除 → NULL 化のみ** (client provider には job 一覧が無く照合が恒久
unknown となり token が永久残留、削除ガードと組み合うと削除不能。server 側も未作成確定への期限超
phantom 記帳を防ぐ — 除外の欠落は major regression)。それ以外の batch_job_id NULL の終端行は
token 照合し、**found (job
実在) かつ未記帳 (述語) なら batch_requests.submission_seq を +1 へ UPDATE + 新値で NULL + estimated
(batch_job_id = 発見 job id) を冪等記帳し、同じ小 Tx で行の batch_job_id へ発見 job id を書く
(自己記述化 — (b') と同じ)**。unknown は掃除も NULL 化もせず保持。**confirmed-absent は
期限判定・伝播猶予を適用 — 期限超は記帳済み判別 → seq 行 UPDATE + 記帳 (batch_job_id = 当該 token)
してから掃除へ、期限内は記帳なしで掃除へ** (期限分岐なしの sweep = 保持期限で消えた課金済み job を
無記帳のまま NULL 化して再駆動キーごと痕跡を消す = major regression — **sweep 自身が塞ぐはずの穴を
sweep が持つ r14 の芯**)。**その後**、同 token 全行終端の残骸を掃除し (404 = 成功)、**成功で
intent_token を
NULL 化** = reconcile close (b')(c) の記帳・掃除失敗の**唯一の再駆動点**。close 後の行はどの経路にも
再訪されないため、**前段なしの「掃除 + NULL 化」だけの sweep は (b') が飛んだ課金済み job を
無記帳のまま掃除して痕跡を消す = major regression**)。completed_at は collect で書く。
**detached 行の処理規範** (folders 行が無い repo の batch_requests 残置行 — unregister §21.2 /
§9.3-d / fork §21.3 の 3 経路とも同一規則): detached は**課金追跡専用** — root_path 不在で成果の
書込先が無いため、state=1 の collect は**結果 payload を破棄**して終端遷移 + ledger 記帳 +
completed_at のみ (metadata 書込をしないことの明示が必須)。**state=0 の detached に「job 未作成 =
課金なし」の前提を置いてはならない** (相 2b 後クラッシュは job 作成済み・client 前計上は実行済み
であり得る): (a) batch_job_id 非 NULL (client) = terminal 記帳 (NULL + estimated) + **同一 Tx で
state=3 (error='detached') + completed_at の terminal 化** (「記帳して即削除」の残存 = 削除ガード
(intent_token IS NULL) とのデッドロック = major regression — ガード遵守なら state=0 のまま sweep の
全行終端条件に入れず token を NULL 化する経路が無い。削除は「全行終端 + upload 掃除 + token NULL」の
段階遷移に委ね、掃除・NULL 化は 4.5 が行う) /
(b) NULL (server) = intent_token で job 一覧を照合し、**実在すれば通常 intent 採用と同一 UPDATE
(state=1 + batch_job_id + attempts+1 + submission_seq+1 + submitted_at。snapshot 不変) で detached へ
採用** (seq 増分なしだと以後の close 記帳が旧 lifecycle の同一 seq と衝突し、冪等吸収がこの別 attempt の
課金を落とす)、**不存在の確認にも attached と同一の期限判定を適用** — 期限超・未来 skew の
confirmed-absent は「未作成」と断定せず、記帳済み判別 → seq+1 + NULL + estimated
(batch_job_id = intent_token) で**記帳し、同一 Tx で state=3 (error='expired') + completed_at の
terminal 化** (detached は載せ直さない — 期限判定なしの
削除は保持期限で一覧から消えた課金済み job を無記帳で消す = major regression)。期限内の
不存在確認も **state=3 (error='detached') で terminal 化** — いずれも削除自体は段階遷移 ((a) と
同じ) に委ねる。**照合不能なら terminal 化せず保持**して次 tick 再試行。行削除の条件は
「全行終端 + upload 掃除完了」に加えて **upload_id IS NULL or upload_cleaned=1、かつ intent_token
IS NULL** (未清掃行を消すと handle 喪失。**token 残存行を消すと (b')/sweep 未完の課金再駆動キーを
失う — intent_token 条件の欠落は major regression**)。
detached の処理の**実行点は tick collect (step 2 / 4) の冒頭**。submit / reconcile / scan の対象外。
削除規則は §21.2 / §9.3-d とも「(cancel 確定 or terminal) かつ (upload 清掃済み or upload 無し)
**かつ intent_token IS NULL**」。
**意図されたコストの注記** (fork §21.3 の課金注記と同族): detached が payload 破棄で終端した後、
削除前の窓で再登録されると attached に戻り「成果なし・state=2 → 投入対象」で自動再投入・再課金
される — 有界・ledger 追跡済みの意図されたコストとして明記されていること。
kind=2 の profile_hash は **kind 連動の表 CHECK ((kind=1 AND IS NULL) OR (kind=2 AND blob 32))**。
repository_id は全表で typeof='blob' AND length=16 の CHECK を持つ。
**file_versions / chunks への状態列の織り込みは禁止** (キー不一致・正本の純度)。
**フォルダ側 metadata.sqlite への配置も禁止** (job_id はデバイス固有 = 可搬性の汚染)。

**P9 追補 (r16)**: ①batch_requests に **job_create_started_at 列** — 相 2b (job 作成呼出) の直前に
単独小 Tx で記録 (再試行は上書き)。**伝播猶予の起点 = max(intent_token 時刻, 同列)** (長い upload が
猶予を食い潰す穴の閉鎖)。**同列 NULL の confirmed-absent は期限判定のみで「未作成」断定可** (相 2b
未着手 = job 不存在)。②**未来側も now < 起点 ≤ now + 許容 skew (5 分) の帯域は unknown 保持**
(期限超扱いは skew 超のみ)。③**「一覧の正常応答」= 全ページ走査完了の応答に限る** (pagination の
部分応答は unknown)。④採用条件は 2 つ — 可視化遅延上限 ≤ 猶予、**terminal 後の一覧保持期間 ≥
timeout_hours + 結果保持期限 + 猶予 1 日**。⑤sweep found の未記帳判別 = **batch_job_id IN
(発見 job id, 当該 token)** (token キーの期限超記帳との二重計上防止)。⑥sweep found・detached
期限超にも **attempts+1**。⑦sweep の掃除・NULL 化は **batch_job_id 非 NULL 行も対象** (照合
スキップのみ — 外すと token 永久残留)。⑧拒否にも課金する provider では **submit_rejected へ倒す
分岐自体で同一 Tx 冪等記帳**。⑨**Retry-After 無し 429/5xx にも既定 backoff** を retry_not_before へ。
⑩detached (b) の期限内 terminal 化は**伝播猶予内なら保持が先**。⑪unregister の cancel 確定 =
**state=3 (error='cancelled') + completed_at + 冪等記帳** (削除は段階遷移 — 「削除対象」直行は不可)。

**P9 追補 (r17)**: ①相 1 の NULL 戻しは **batch_job_id / error / completed_at / job_create_started_at
の 4 列** (job_create_started_at を残すと旧 attempt の残置値を猶予起点の max() が拾う)。②「NULL =
相 2b 未着手の証明」は**列導入後の lifecycle 限定** — §14 の列追加 migration で state=0 かつ token
非 NULL の既存行へ token の時刻成分を backfill (同一 Tx)。③cancel 確定は **attempts = 上限を同時
設定** (遷移表の自動再投入対象にしない — 復帰は明示 retry のみ) / **batch_job_id NULL かつ token
非 NULL の行は cancel 確定禁止** → detached 例外へ。④**rotation ガード** — token 残存行の再投入は
当該 token の sweep 前段完了後に相 1。⑤課金される拒否の記帳は **seq +1 行 UPDATE + 新値で記帳**
(現値は明示 retry 後の 2 度目拒否と UNIQUE 衝突)。⑥Retry-After 無し一時失敗の既定 backoff は
**全分岐共通** (相 2a/2b・client・collect・intent 回復 unknown)。

**P9 追補 (r18)**: ①rotation ガードの**新 3 原則** — 適用 = **state=3 の再投入のみ** (state=0
載せ直し・client dispatch は対象外)、本体 = 照合・記帳・NULL 化 (残骸掃除は best-effort)、恒久
unknown = stalled + **明示 abandon** (estimated 記帳 + NULL 化)。
**P9 追補 (r19)**: ①ガードの適用は **state IN (2, 3)** へ拡張 (floor 明示再生成 = state=2 の再投入
経路を被覆 — sweep の終端定義と一致)。②**scope_id 列** — 相 2b 直前の小 Tx で
job_create_started_at と同時記録・照合の同一 scope 判定は行の scope_id と現照会の比較・NULL は
unknown。③**abandon の操作実体** = 単一 Tx で IN 判別 → seq+1 + token キー estimated 記帳 →
state=3 (error='abandoned') + attempts=上限 + completed_at → token NULL 化 (state=0 の恒久 unknown も
対象)。④completed_at の DDL コメント = 「確定する全 UPDATE で書く」(全終端 error 列挙つき)。②照合の正常応答 = 全ページ **かつ
job 作成時と同一の account/workspace scope** (変更後の一覧は unknown)。③**completed_at は state を
2/3 へ確定する全 UPDATE で同時書込** (detached 限定ではない)。④§8 側の課金される拒否も **seq+1 行
UPDATE + 新値で記帳** (§9.1 との両側)。⑤cancel の「自動再課金しない」は行が存在する間の規範
(削除後の再登録 = 意図されたコスト)。⑥batch_job_id の DDL コメント = 「NULL = 行上は未記録 —
job は存在し得る」(不存在の根拠にしない)。⑦intent_token は job 単位 (JSONL 分割の決定は採番より前)。

**P10. 書き込み順序と冪等性**: objects/ → metadata.sqlite → app.sqlite の順で書く
(objects の「存在」は **rename 後のディレクトリ fsync** まで済んで成立 — P16 / 規約 6)。
**規約 6 には §7 の floor 引き上げ (app → metadata の順が正) の例外併記が必須** — 本規約は参照の
存在保証の順序で、fence 系の意図書込には適用しない (併記なしは、規約 6 に従う実装が明示再生成を
silent cancel し課金済み新結果を破棄する = 不備)。
Batch 回収時は「フォルダ側 1 Tx を先に確定 → app 側 state 更新は後」。**collect の冒頭で
フォルダ側成果の存在を確認し、既にあれば metadata 処理をスキップして app 行を閉じるだけ**
(前回 tick が metadata Tx 後・app 更新前に落ちたケースの冪等吸収。**OCR と Embedding の
両 collect に適用** — 片方だけなら partially-fixed。閉じる app Tx は cost_ledger 追記と同一)。
差集合 SQL の bind 名は文書内で統一されていること (:current_tool / :current_profile)。
OCR submit の差集合は content_hash 単独ではなく **(content_hash, current_tool) ペア +
floor を考慮した「成果なし」判定 (P9)**、Embed submit は **(chunk_type, embed_hash) と
(target_type, target_hash) のペア比較 + embedding_profile_hash = 現行を含む NOT EXISTS** (P8-a)。
派生の置き換えは同一 Tx で「旧 markdown_documents 行 DELETE (CASCADE) → INSERT → chunks INSERT →
**profiles INSERT OR IGNORE**」(UPSERT 禁止 — 親行 UPDATE では CASCADE が発火しない)。
**tick はプロセスとして単一実行ロック (tick.lock / flock) で直列化する** — busy_timeout は
これを代替しない (並行 tick は同じ差集合から外部 job を二重作成し得る)。
tick の構成: ステップ 0 (Scan & Commit) → **0.5 (Reconcile — state IN (0, 3) × 成果照合。
state=1 は対象外 — P9 の分担。**対象は folders 実在行のみ = detached 対象外の明記が必須** —
detached の成果照合先は存在しない)** → 1 (OCR submit — 冒頭 intent 回復 → **DISTINCT content_hash**、
加えて **backfill**: all_versions の DISTINCT content_hash を低優先投入、既定 ON。**floor 設定
済みの対象は backfill 設定に関わらず候補**。preflight 非対象は terminal marker 行 — P6) →
2 (OCR collect — **冒頭で §9.1 detached 処理 (kind=1 分) を再掲実行**。kind=1 の処理 +
cost_ledger + floor の NULL 戻し + job 終端後の
output_missing 掃き) → 3 (Embed submit — 冒頭で vec の**次元と距離**を照合 → DROP/CREATE/再充填。
**照合・作成の「現行 profile」参照元は app_config の embedding_profile record** — §5.7 は履歴
保管庫で新規フォルダでは空 (§5.7 参照の残存は不備)。+ 旧 profile 行掃除 + intent 回復) →
4 (Embed collect — **冒頭で §9.1 detached 処理 (kind=2 分) を再掲実行**。**kind=2 は OCR の
保存・解析処理へ
送らない**。旧 profile 行は vec → embeddings の順の DELETE → INSERT で置換。**「無ければ」分岐の
embedding_vec も DELETE → INSERT — agg §9.3-c と同形** (破損起源の vec 孤児 (embeddings 行なし・
vec 行あり) との PK 衝突無害化。素朴 INSERT の残存は不備)) →
**4.5 (upload 掃除 + token sweep — state 独立。404 = 成功。sweep は (b') 前段 (found 記帳 + 期限超
confirmed-absent 記帳 — 期限判定・伝播猶予を適用) → 掃除 → NULL 化の順 — P9。
§10 の 4.5 行に token sweep の列挙が無い残存は不備)** → 5 (Replicate — 冒頭検査は次元 + 距離 +
synced NULL 化、a〜d)。**tick の先頭には step -1 (後退検出 z の判定)** — §9.3-z の判定を
フォルダごとに冒頭で行い、**判定は三値** (verified = 進む / regressed = step 0〜4 除外・step 5 で
wipe+resync / **unreadable (一時 EIO 等) = 未検証として regressed と同様に除外・保留** —
「開けなかったから進む」は復元 + 一時 EIO の組合せで巻き戻った LWW の課金へ進む)。
**z 判定が step 5 のみ / 二値の残存は regression**。**z 検出時の注記**: 既存 in-flight job の
collect は通常どおり実行してよい (巻き戻り後の履歴に無い content の派生は eligible に現れない —
§11 版フィルタ。fence で課金済み結果を破棄する機構は設けない)。**除外リスト側にも「ただし step 2 / 4
の in-flight collect と detached 処理は除外しない — 除外対象は巻き戻った状態を入力にする scan /
reconcile / submit / replicate」の明記が必須** (「step 0〜4 を一律除外」と本注記の並記は文書内矛盾 =
O17 — r14 で整合済み。矛盾の再残存は regression)。**同じ例外は §9.3-z 側にも鏡写しで明記されている
こと (片側のみの残存 = r15 で補修した転記漏れの再発 = regression — 再掲対の両側を検査する)**。
collect の kind 分岐が無い記述 (「kind=2 も 2-a〜2-c」等) は誤り。
クラッシュ残骸は「未参照 objects / 閉じ忘れ state=1 / state=0 intent」のみで次 tick が収束し、
**重複課金は intent 回復により最悪 job 1 回分に有界 — server-side batch 経路限定の明記が §10 側の
再掲にも必須** (無限定の再掲は文書内矛盾 = 誤り。app.sqlite 全損はこの有界化の外 — P1)。

**P10 追補 (r16)**: §10 step 2/4 の state=1 照会は **folders に現存する repository の行に限る**
(detached は各 step 冒頭の detached 規範のみが扱う)。**(r18)** この限定は step 2 と step 4 の**両方の
本文に明記** (step 4 側の鏡写し欠落は補修済み)。step 5 の破棄 = agg_embeddings (行 DELETE) /
agg_vec (DROP→CREATE) の区別。FTS ラグ = chunk_fts (step 2) と agg_chunk_fts (step 5) の層区別。step -1 の unreadable への collect 非除外例外は
**実質 regressed 側にのみ効く** (unreadable では metadata を開けず collect 実行不能)。§10 の
「最悪 job 1 回分」有界主張は **server-side 限定かつプロバイダ採用条件つき**。

**P11. 集約 (レプリケーション)**: agg_commits / agg_file_versions は append-only ミラーで
(created_at, commit_hash) カーソル (sync_state) による差分コピー — file_versions は created_at
列を持たないため **commits と join** してカーソルを適用し、**初回カーソル (NULL) は
`:cursor_at IS NULL OR (行値比較)` で明示処理する** (NULL との行値比較は UNKNOWN で 0 件になる)。
両集約表への完全な INSERT ... SELECT が文書に掲載されていること。agg_markdown_documents は
generated_at 比較で置換検出し、**派生単位 (content_hash, tool_profile_hash) の全置換**で
agg_chunks を DELETE → INSERT した上で **agg_markdown_documents 自体を同 Tx で UPSERT する**
(怠ると毎 tick 再検出)。**逆差集合が必須**: agg にあるがフォルダ側に無い派生キーの
agg_markdown_documents / agg_chunks 行を DELETE (フォルダ内で消えた派生の伝播経路)。
**embeddings の同期はコピーに加えて profile_hash 不一致行の置換を含み、コピー・置換の
いずれも agg_embeddings と agg_vec を同一 Tx で投入する** (P8。新規コピーで agg_vec を
書かないと KNN に永久に現れない)。**agg_vec への投入は常に DELETE → INSERT** (新規コピーも同形 —
素朴 INSERT は vec 孤児 (embeddings 無し vec 有り) との PK 衝突で replicate が毎 tick abort する)。
**フォルダの現行 profile embeddings を被覆・複製し終えたら
sync_state.synced_profile_hash を building へ UPDATE** (P8-e の ready 判定の入力。**行の作成 =
フォルダの初回 Replicate で INSERT (カーソル・synced NULL・synced_at=now)。building (app_config の
lower hex64 TEXT) との比較は hex を BLOB へ復号して行う** — TEXT 直書きは CHECK 違反・TEXT 比較は
無音不一致)。**agg_vec の
same-profile 欠落は Replicate 冒頭で agg_embeddings からの差集合冪等再充填で埋める** (§8-c の
ローカル版と同型 — profile 変更を伴わない silent 欠落が破棄・再構築まで KNN から欠落するのを防ぐ)。
agg_embeddings は **repository_id を持たない** (内容アドレスでデバイス全体 dedup)。
**後退検出 (z) の判定の実行点は tick 冒頭 (step -1 — P10)**、wipe + resync の実行は step 5。
**z は 2 条件**: (1) フォルダ max (created_at, commit_hash) < カーソル、
(2) **カーソルの commit がフォルダ側 commits に実在しない** (max 比較だけでは「空 DB へ復元 →
新規コミットで max がカーソル超え」がすり抜ける) — いずれかで repo wipe + full resync +
**当該 repository の scan_cache / 配下 fp_cache を無効化して強制 hash scan を課す** (metadata のみ旧版
復元で working が新しいまま fp 一致で skip され、agg=旧 と実ファイル=新 が deep-scan まで乖離する)。
フォルダ削除時の一括 DELETE は **repository-scoped 4 表 + sync_state + batch_requests +
scan_cache + pending_deletes (+ 旧 root_path 配下の fp_cache)**
(sync_state を残すと同 repository_id 再発見時に旧カーソル以前が再同期されない)。
**batch_requests の削除は §21.2 と同一規則: cancel 確定 / terminal (2/3) のみ削除し、cancel
未確定の in-flight は detached として残す** (P9 の detached 規範。「cancel 失敗しても timeout で
自然終端するから削除してよい」は誤り — 終端しても記帳する行が無く、再登録 / fork 後の新 id が
同一対象を再投入して二重課金する)。**cost_ledger は削除しない**。
agg_embeddings / agg_vec は「agg_chunks のどの **(chunk_type, embed_hash) ペア**からも参照されない
(target_type, target_hash) 行」の逆参照掃除で孤児のみ削除する (hash 単独比較は type 違いの
同 hash で孤児を残すため誤り)。

**P12. 検索**: 版フィルタは 3 モードとも**同じ公開名 `selected_files(repository_id, file_name,
content_hash)` を返す実行可能な完全 SQL** として掲載されていること (現在版 = ファイル単位 LWW
`created_at DESC, commit_hash DESC` / 過去版込み = DISTINCT file_versions / 時点指定 =
行値比較で絞った LWW)。§11.2 は (A) 現在版モードの ranked / selected_files を**実際に組み込んだ実行可能な完全 SQL**
であり、B / C への切替は同名 CTE の機械的差し替えと注記する (literal placeholder が SQL 内に
残っていたら誤り)。ハイブリッドは **eligible (版 + 現行 tool) を rank 計算より先に
定義**し、eligible は selected_files への **EXISTS** で引く (JOIN は同一 content_hash の複数
file_name 参照で chunk_uid が重複し rank と RRF を水増しするため誤り)。FTS / KNN 両経路が
eligible の chunk 行に着地してから RRF (Σ 1/(60 + rank)) で融合。vec0 KNN は **over-fetch
(k_fetch 初期値 = min(k_max, max(40, limit×4))) + 不足時の refill (k 倍化再クエリ、上限 k_max は
既定 4,096、それでも不足なら不足のまま返す)** の規則を持つ。**vec_hits の join キーは
e.chunk_type || ':' || lower(hex(e.embed_hash))** — lower() の無い hex() は大文字を返し、
小文字格納 (P8) との混在で join がエラーなく 0 件になる (契約文だけあって実 SQL が hex() の
ままなら partially-fixed)。**LIKE fallback (3 文字未満) の bind は分離**: フレーズ化済み
:query を LIKE に流用したら誤り。生文字列から `\`→`\\`、`%`→`\%`、`_`→`\_` の順で
エスケープした :like_pattern + ESCAPE '\'、rank は instr 昇順 → chunk_uid 昇順で決定論化。
fts_hits は **FTS 表にエイリアスを付けない**
(FTS5 の MATCH / bm25() は表名で参照するため — エイリアス付きで表名参照する SQL は誤り)。
**`:query_vector` の生成源**: 横断検索は **app_config の embedding_profile record (P9)** から
embed する — app 側にこれが無いと横断検索が実行不能。**bind 形式 = float32 (little-endian) の
raw BLOB、長さ = dimensions × 4 バイト** (§5.6 テンプレート・embeddings.vector と同形式 —
形式未固定はバインディング差で KNN が沈黙。形式の明記が無ければ不備)。**生成に使った profile の hash を
`:query_profile_hash` として固定し、KNN 実行直前に `agg_ready_profile_hash` == `:query_profile_hash`
を照合する** (「現行」との照合は embed 中の profile 変更で TOCTOU — P8-e の building / ready 2 key。
**ready は接続フォルダ (= 当該 tick に §9.3 を実行できたフォルダ — P8-e) の再レプリケーション完了時に
のみ更新**。単一 key や
「全フォルダ」無条件の照合は「破棄直後・一部フォルダのみ同期済み」の部分 index を正常扱いする = 誤り)。
**照合と KNN 実行は同一の read Tx (同一接続のスナップショット)** — 別 Tx は照合通過と KNN の間に
tick の再構築が挟まる窓を残す (app.sqlite は WAL で read Tx がスナップショット固定)。
不一致中は KNN を実行せず FTS のみ + status「index 再構築中」。**query embed 呼び出し自体の失敗
(429 / 断 / 認証) も FTS のみ + status** (必須 bind を作れないため — 全失敗にも FTS 沈黙にもしない)。
**フォルダ単独の「現行」決定規則は 2 本**: **:current_profile = embeddings の全行一致検査で得られる
一意な embedding_profile_hash に対応する profiles 行** (embeddings 空 / 移行中の混在は
KNN 停止 + FTS のみ) / **:current_tool = markdown_documents の最新 generated_at を持つ行の
tool_profile_hash — **同時刻 tie は tool_profile_hash のバイト昇順で決定 (tie-break の欠落 =
bind の実装・走査順依存 = 不備)**。**近似の注記も必須**: 一括ローカル変換は旧 tool 派生の
generated_at も進めるため変換直後は旧 tool が「最新」になり得る — 「最後に触れられた世代」の
決定論的選択であり厳密な「最後の OCR 生成 tool」復元は層 1 の目的外 (app 管理下は app_config が正)**
(tool 切替後は旧派生が明示 drop §21.6 まで残り混在が定常 — embedding と同じ
「混在停止」を適用すると eligible の tool gate が FTS 経路まで恒久停止し §2 可搬性に反する。
**非対称は意図的**と明記: embedding 混在 = KNN の空間汚染 (黙った誤順位) / tool 混在 = どの世代の
本文を読むかの選択。**tool 決定規則の欠落 = tool 切替を経たフォルダの単独検索が実装不能 = major
regression**)。**いずれも被覆を保証しない** — re-embed / 再 OCR 進行中の検索は
部分的であり得る (FTS は tool gate 内で全量。完全性は主張せず未 embed 残数を status に示す、と
明記されていること)。
**空クエリ (trim 後空) は 0 件で全経路を実行しない**。
**ROW_NUMBER には第 2 ソートキー chunk_uid** (fts_hits / vec_hits とも)。**最終 SELECT も
ORDER BY fu.score DESC, c.chunk_uid** (RRF 同点 — FTS 単独 1 位と KNN 単独 1 位は同スコア — が
LIMIT 境界に並ぶと実行ごとに結果が揺れる)。**LIKE fallback は text と heading_path の両列を対象** (FTS が両列を索引するため — 片方だけだと
heading のみの短語が 3 文字境界で挙動が変わる)。**rank は両列の instr(lower(…), lower(生クエリ)) の
非 0 最小** — SQLite 既定 LIKE は ASCII case-insensitive、instr は sensitive のため、揃えないと
「LIKE ヒットだが instr=0」が最上位に来る。**LIKE 走査の完全形は eligible × agg_chunks の chunk_uid
再 JOIN** (eligible は text / heading_path 列を公開しない — 裸の text 参照は列不在エラー。
`c.text IS NOT NULL AND (c.text LIKE :p ESCAPE '\' OR c.heading_path LIKE :p ESCAPE '\')` —
**c.text IS NOT NULL は必須** (FTS の対象 (view) は text 非 NULL 行のみ。fallback だけが annotation
なし画像チャンクを heading 経由で返すと対象集合が 3 文字境界で変わる — 欠落は不備))。**`:limit` は正整数・上限付きで
入力境界検証** (SQLite の `LIMIT -1` は無制限)。**hash 系 bind (:current_tool / :current_profile) は
raw BLOB (32 bytes)** — record から SHA-256 を計算した生バイト列を bind する (lower hex TEXT の
bind は BLOB 列との比較が無音 0 件 = 契約の明記が必須)。**時点指定で commit を特定しない
「時刻 t まで」は :at_hash = X'FF…FF' (32 bytes)
固定** (同一 created_at の全 commit を含める意味論の一意化)。
**検索結果は chunk 単位 1 行**で、解決キー (repository_id / content_hash / tool_profile_hash /
chunk_uid / char span) を含む — 最終 SELECT に file join があれば誤り (行が膨れて LIMIT を消費。
file_name / commit / created_at への展開は §12 の file_versions **JOIN commits** で表示段に行う。
created_at は commits 側にしかない)。**§12 の「完全に解決できる」は接続中フォルダ限定と明記** —
missing 猶予中のフォルダへのヒットは除外せず、解決段で「フォルダ接続なし (missing)」を status
表示する (無限定の完全解決主張の残存は不備)。**§12 の解決チェーンは objects/ から読んだ実体の
SHA-256 を再計算して名前と照合してから提示する** (restore §21.4 手順 1 と同じ規律 — 不一致
(silent bit-rot) は fsck 誘導。無検証提示の残存は不備 — 週次 fsck までの窓で破損を「原本」として配る)。フォルダ単独検索への読み替えは**機械的 mapping 表**
(agg_* → ローカル表名、chunk_uid → chunk_id、**bind 給源の行を含む** — 横断 = app_config /
単独 = :current_profile は §5.7 profiles + embeddings の一意 profile 規則・**:current_tool は
markdown_documents の最新 generated_at 規則**。給源注記が無いと mapping 表だけで実装した
単独検索が app_config を誤参照する) として掲載されていること。**単独検索も読取の
規約 12 照合 (P16 — scoped) の対象**。

**P12 追補 (r16)**: LIKE fallback の**差替え用 SQL 例にも `c.text IS NOT NULL AND (...)` を必須の
まま残す** (規範側だけでなく掲載 SQL 側も — 欠くと text=NULL の画像 chunk が heading 短語一致で混入)。
**P12 追補 (r17)**: ①query の **NUL (U+0000) を境界で拒否/除去** (FTS5 MATCH bind の構文エラー防止)。
②fts_hits / KNN k に**内部上限 :fts_cap** (外側 :limit は fusion 後にしか効かない)。③trigram FTS と
LIKE fallback の **case 折り畳みは両側同一が正** — 不能な実装は「短語一致は case 厳密の近似」を明記。
**P12 追補 (r18)**: :fts_cap は**掲載完全 SQL の fts_hits に実装済み** (`ORDER BY bm25 …` +
`LIMIT :fts_cap` — rank 順の決定論的打切り。KNN 側対応物 = :k_fetch)。§19 の旧称 :k_fts は
:fts_cap に統一済み。
**P12 追補 (r19)**: :fts_cap は**サブクエリ内側段**で適用 (window (ROW_NUMBER) と同段の LIMIT は
全一致行を走査してから切る — 一時領域が一致件数に比例)。**未来 generated_at (now+skew 超) は
:current_tool 判定の候補から除外 + status** (全行未来なら最新採用)。

**P13. GC**: objects/ の参照集合は **3 本の和集合** — file_versions.content_hash ∪
markdown_documents.markdown_hash ∪ **保存済み Markdown から抽出した obj:<image_hash64> 参照**。
3 本目を chunks.image_hash (SQL) にした記述は誤り — opt-in フィルタで chunk 化されなかった
画像を GC が誤回収する (フィルタ OFF 復帰時に obj: 参照が宙に浮き再 OCR 課金)。
**GC は tick.lock を取得して実行** (全 objects writer が tick 内のため中間状態を観測しない) +
作成 24h 以内の object は削除しない grace。**fork 完了直後・次 tick の scan 完了前には実行しない**
(file_versions が手順 1 で空になり現在版原本も参照ゼロに見える — 次 scan が working から再保存する
ため喪失はしないが、無駄回収 + §12 解決の一時失敗。GC の実行点 = scan を含む tick の step 5 以降と
明記されていること)。**GC は fail-closed で、中断条件は欠損・読取失敗に
加えて「読めた bytes の SHA-256 ≠ markdown_hash」(silent bit-rot)** — 参照抽出の前提は
「読めること」ではなく hash 一致 (欠損だけの記述なら partially-fixed)。
**fsck は object 層 (bytes の hash 照合) + 履歴層 + profile 層 + 集約層** — object 層は
**読取の一時失敗 (AV/EDR ロック等) と破損を区別**し一時失敗は再生成誘導へ倒さない、履歴層は
PRAGMA integrity_check / foreign_key_check + 全 commit の commit_record 再構築 → commit_hash
再計算照合 + parent / previous 鎖の解決可能性、**profile 層は (a) profiles 全行の
SHA-256(record_json) = profile_hash 照合 + (b) 参照整合 (md / embeddings が指す profile_hash 行の
存在と kind 一致 — LEFT JOIN 欠落検出) + (c) 破損行の修復 = 検証済み record (app_config 現行 /
batch_requests の snapshot) での DELETE → INSERT** — §5.7 の通常書込は INSERT OR IGNORE のため
**破損行は何度書き込んでも直らない** (修復手段の欠落は major)。**repair の DELETE → INSERT は
同一 Tx (BEGIN IMMEDIATE)** — 別 Tx は「間のクラッシュ + app 喪失」の二重障害で復元材料を両側から
失う。**集約層は agg_embeddings と agg_vec の
target_key 差集合を双方向に検査** ((i) embeddings→vec の欠落 = §8-e 再充填が埋める /
(ii) vec→embeddings の孤児 = §9.3-c の DELETE→INSERT が上書きで無害化)。**加えて agg の親子整合
(agg_markdown_documents の各派生行 × agg_chunks 子行の対応) を検査し、不一致は当該派生の
agg_markdown_documents 行 DELETE + 当該フォルダの synced_profile_hash NULL 化で次 Replicate の
全置換を駆動する** (子行だけの部分喪失は §9.3-b の generated_at 比較で再検出されず恒久欠落 —
検査・駆動の欠落は不備)。**FTS 整合の検査も必須**: chunk_fts へ external content 照合つき
integrity-check を実行し、不一致は local = 同 Tx rebuild / agg = synced NULL + 親 DELETE で全置換
駆動 (posting 単独の破損は PRAGMA integrity_check で検出されず MATCH が恒久 0 件 — 欠落は不備)。
**再同期駆動 Tx では agg_ready_profile_hash も削除する** (残すと修復中の部分 index が ready を騙り
KNN が欠落を正常として返す — 欠落は不備)。上記以外は検出・status のみ (agg は真実でないため再同期駆動以外の直接修復は
しない)。
**原本 object の欠損・破損は fsck が repair できる**: working copy を hash して一致すれば
objects/ へ書き戻す (通常スキャンは LWW 一致で再保存しないため fsck の明示経路が必要)。
**repair の読み取りは §20.5 と同じ 1 ストリーム規律** (hash 用と保存用の 2 回 open は fsck 自身が
TOCTOU を再導入する)。**「同一 hash の実体があれば再保存しない」規則の例外**: fsck が破損を検出
した object は既存実体があっても tmp から原子置換する (例外にしないと壊れた実体の存在自体が修復を
永久に妨げる)。**profile 破損の誘導は kind 別** (tool → §21.6 drop-derivation + 現行 tool での
自動再投入 / embedding → 該当行削除 (**同一 Tx で embedding_vec → embeddings の順** — embeddings
だけ消すと vec 孤児が残り re-embed の collect INSERT が PK 衝突で恒久失敗。fsck はローカル側も
vec → embeddings の逆差集合 = vec 孤児を検出対象に含め、**検出した孤児 vec 行は削除する (修復)** —
検出のみだと §10 step 4 の INSERT が衝突し続ける。collect 側の DELETE → INSERT と二重の防御) +
自動 re-embed。「明示再生成 §5.3」は
OCR floor の操作で embedding の修復には使えない — 誤誘導の残存は regression)。
**原本 + 派生の同時喪失で GC が恒久 fail-closed になった場合の回復は §21.6 drop-derivation**。
**§5.3 の明示再生成は md 行不在 (drop 後の過去版のみ等) でも機能する** — INSERT 分岐は
**floor_generated_at = 0 (sentinel — 派生不在・任意の新結果が成果)** を設定し、「floor 設定済み =
backfill 設定に関わらず候補」で回復連鎖が閉じる (floor 基準未定義の残存 = §21.6→§5.3 の
文書化された回復が backfill OFF × 過去版のみで実装不能 = major regression)。
**§21.6 注記 (a) は「現在版、または backfill ON では過去版参照も」自動再投入と明記** (「現在版なら」
限定の残存は N23 の regression — backfill ON の過去版 drop は次 tick に再課金される。回避 =
backfill OFF / unregister 先行 + floor 例外の注意)。
フォルダ側 embeddings の孤児掃除は
(chunk_type, embed_hash) ペア差集合で、**同一 Tx で embedding_vec → embeddings の順に削除**
(vec を残すと再出現時に target_key PK 衝突)。**§13 のバックアップ規範は「復元 (書き戻し) も
tick.lock 下で行う」ことを含む** (lock 外の外部復元は §9.3-z / step -1 が regressed として拾い
step 5 の wipe + full resync が回収する — 検出前提の回収経路であって静止復元が正、と明記)。

**P13 追補 (r16)**: FTS 整合検査は **rank=1 形式** (`INSERT INTO chunk_fts(chunk_fts, rank)
VALUES('integrity-check', 1)` — SQLite 3.42+。引数なしは内部整合のみで posting 単独欠損が偽陰性)。
**agg_chunk_fts の不一致は同 Tx 'rebuild'** (integrity-check は破損箇所を特定しないため「synced
NULL 化 + 親行 DELETE」は実行不能 — agg_chunks 側の内容破損は親子整合検査が駆動)。**folder 側にも
markdown_documents↔chunks の親子件数検査** (不一致 = §7 再解析で再構築 — ローカル・無課金)。
**同一サイクル内は fsck → GC の順**。
**P13 追補 (r17)**: folder 側親子検査は**件数 + 各 text チャンクの SHA-256(text) = text_hash 照合**
(件数のみだと内容破損が素通りし、FTS rebuild が破損内容を固定化する)。
**P13 追補 (r18)**: ①親子検査は**全 field 照合**へ拡張 (image_hash・media_type・image_meta・seq・
chunk_type・heading_path・span — §7 再解析出力との完全一致)。②GC 参照集合は**未知 grammar v に
fail-closed** (未知 v・v 混在文書由来の参照は保守的に全保持 + status)。③dedup 破棄前に**既存 object
の SHA-256 照合** — 不一致は tmp で置換 (自己修復) + fsck 報告。④PRAGMA **incremental_vacuum(N)**
(有界ページ数)。
**P13 追補 (r19)**: §13 に **GC の実行点 = tick の step 5 以降**の明記 (§21.3 と同一)。vector 共有
キーの要約は §18 側も **(chunk_type, embed_hash)** に統一。「99%」の断定は「text_hash が変わらな
かった chunk はそのまま再利用」の限定表現へ。

**P14. SQLite 設定**: metadata.sqlite = foreign_keys ON / synchronous FULL /
**journal_mode DELETE** (同期ソフト配下の WAL/SHM 問題回避)、コミット処理中だけ短時間オープン。
app.sqlite = WAL + busy_timeout (アプリ専有のため)。busy_timeout は SQLite ロック待ちであり、
tick の直列化 (P10 の tick.lock) を代替する記述になっていたら誤り。**空きページ回収の規範が必須**:
新規 DB 作成時に auto_vacuum = INCREMENTAL、fsck の週次サイクルで PRAGMA incremental_vacuum
(GC・派生置換・行削除の DELETE で DB が単調肥大する — 全量 VACUUM は長時間排他のため規範にしない。
欠落は不備)。
**migration は版ごとに単一 Tx、かつ tick.lock 下で実行し、全 writer (常駐スレッドの tick・
明示操作) は lock 取得後・Tx 開始時に user_version を再確認する** (起動時検査だけでは migration 前から
生存する旧版 writer が新版 DB へ旧スキーマ意味論で書く窓が残る):
BEGIN IMMEDIATE → user_version 再確認 → DDL / データ移行 →
PRAGMA user_version = 新版 → COMMIT (version 更新を別 Tx にすると ADD COLUMN 再実行の
duplicate column で恒久起動不能 — 「適用してから version を上げる」だけの記述は不足)。
**既存データを持つ表への FTS 後付け migration は同 Tx で 'rebuild' を実行** (trigger は以後の
変更しか拾わない — rebuild なしは既存行が MATCH silent 0 件)。**PRAGMA 接続初期化規範**:
foreign_keys は connection ごとの設定で既定 OFF — 全接続の open initializer で適用・検証を必須と
する (適用漏れ接続の DELETE は CASCADE 不発火で孤児を作る — fork の commits 全削除が典型)。
**Windows は POSIX mode が無意味** — 継承を遮断した DACL (現在ユーザー + SYSTEM のみ) を
規範とし、起動時・復元後に権限検査。
また hash 列の BLOB 保証: 新規テーブルは typeof + length の CHECK、DDL 不変の
commits / file_versions は書込境界検証を規範とする (SQLite の型親和性により
`length(x)=32` だけでは 32 文字 TEXT を排除できない)。

**P15. 元設計から不変の部分**: commits / file_versions の DDL (WITHOUT ROWID、event_type 1/2/3、
CHECK、インデックス 2 種)、ファイル単位 LWW、並行コミット全保存、Repository ID、
元設計 §21 の不採用リスト (files / file_heads / content_objects / Next ポインタ / device テーブル)。

**P16. 変更検知 (§20)**: 3 層構成 — 層 A = OS イベント (**dirty マーキングのみ**。イベントの種別・
パスからコミット内容を構成する記述があれば誤り) / 層 B = スキャン (正しさの基盤。イベントゼロでも
全機能が成立し、非稼働中の変更は起動時スキャンが吸収) / 層 C = tick (不変)。スキャンは 3 段:
段 0 = 階層 fingerprint (**任意の最適化**。2 成分 files_fp / dirs_fp + dir_fp の再帰 Merkle、
入力は stat メタデータで内容は読まない、JCS + name 昇順)、段 1 = scan_cache 行比較 (**必須**。
(mtime_ns, size [, inode]) のいずれか 1 つの差で hash 再計算 + **racy 規則**: ファイルの mtime が
**その行の verified_at (content_hash を検証した時刻) と同一秒粒度内またはそれ以降**なら
キャッシュ不信頼 — 基準は「今回のスキャン時刻」ではなく verified_at)、段 2 = content_hash
(真実。§20.5 の安定確認 → LWW 比較 → コミット。**§20.5 に元設計 §15 のコミット作成処理 —
安定確認 / 変更判定 / 実体保存 tmp→rename / INSERT OR IGNORE の Tx / scan_cache の UPSERT
(verified_at = now) と delete 行の DELETE — が収録されていること**。本書 §15 は設計規約であり別物)。
**スキャンとコミット作成は tick のステップ 0 として tick.lock の下で実行する** (独立プロセス禁止 —
コミット作成 Tx と tick の現在版読取りが並行し得る)。**層 A の dirty 集合はプロセス内メモリで
非永続** (専用テーブルを作ったら誤り。喪失は起動時フルスキャンが吸収)。dirty 発生時の tick
早回し起動は可 (tick.lock が直列化)。消費した dirty はステップ 0 完了時にクリアする。
追加規範 (r4 反映): **delete 判定の正本は「現在版 LWW の生存集合 − walk 観測集合」**
(scan_cache を根拠にしたら誤り — cache 全損で削除を見逃す)。walk 観測は
readable / skipped / absent の三値で、**skipped は「読み取りの一時失敗」(プレースホルダ・
安定確認失敗・権限エラー) に限り存在扱いで削除しない。対象外の型 (symlink / FIFO 等) への
置き換えは absent 扱い** (恒久的な型不一致を skipped にすると旧内容が現在版に永久残留 — r7)。
非 UTF-8 名はどの論理名の観測にも数えない (status のみ)。
**fp_cache の更新は枝の段 1〜2 完了後のみ** (先に更新すると持ち越した変更が
永久にスキップされる)。§20.5 に**コミット入力の決定規範** (parent_hash = 最新コミット /
previous_commit_hash = 当該 file の LWW 先頭 (delete 行含む、無ければ省略、delete 後再作成は
create) / created_at = スキャン確定時刻で 1 コミット単一値 / **message = 常に省略** — 手動 commit
操作は §21 に存在しない (「明示操作時のみ任意指定」の到達不能分岐の残存は不備。提供は §19 の
将来拡張扱い)) があること。
fp の JCS 表現は hex64 文字列 + name は正規化なしの UTF-8 バイト順 (**非 UTF-8 名は fp 入力から
除外** — JCS string で表現不能・管理対象外)。
app 全損時の bootstrap は P1 側 (規約 9) — watch_roots 再入力 → repository-id 再発見。**物理制約の明記が必須**: walk (stat) は毎回必要 — ディレクトリ mtime は直下エントリの
作成・削除・rename でのみ更新され、内容上書き・孫の変更では変わらないため、fp が省くのは
walk 後の特定と後続処理のみ。低頻度 deep-scan (キャッシュ無視の全 hash 再計算) が補正。
集約容量による検知は不採用 (FS が集約値を持たず、同サイズ変更・相殺・rename を見逃す)。
検知層だけがツリーを見る — 管理単位 (フォルダ直下のみ) は不変。管理外の変更は無視、
新規管理フォルダの自動登録なし、フォルダ消失は猶予期間後にのみ削除処理、プレースホルダは
既定スキップ + status 表示、ignore 規則 (~$* / .tmp / .crdownload / 隠しファイル /
.folder-history)。新テーブル watch_roots / scan_cache / fp_cache / **pending_deletes** は
**app.sqlite** に置く (stat はデバイス固有 — フォルダ側に置いたら誤り)。すべてヒントで
喪失時は全再計算 (pending_deletes はカウントやり直し = 確定遅延のみ)。

追加規範 (r7 反映): §20.5 の delete「連続 2 回 absent」は **pending_deletes に永続化**
(1 回目の absent を観測した完全 walk で UPSERT / readable・skipped で DELETE / 確定 =
行が存在する状態で後続の完全 walk が再び absent、**かつ now − first_absent_at >= 最小不在時間
(既定 30 秒)** — 回数だけでは dirty 早回し tick (100ms 間隔もあり得る) が Office 保存の一時消失窓の
中で 2 回 walk して偽 delete を作る。**時間差は wall clock なので時計急変で誤満了し得る →
delete コミット直前に対象名を §20.4 と同じ lstat + O_NOFOLLOW + regular 判定で再確認し (**対象は
「論理名 → 物理名の解決」で得た raw エントリ** — 下記)、readable な
regular file なら確定中止 + pending リセット** (時計前進下でも「実在ファイルへの偽 delete」を防ぐ
安価な最終防衛 — 欠落は regression。**確認直後〜コミットの残余窓は次 walk の create が是正する
自己修復の範囲、と絶対主張を避けて明記**。**「存在すれば中止」の素朴な stat は誤り** — 対象外型
(directory / symlink / FIFO への置換) を absent と数える §20.4 と矛盾し、置換先を「存在」と見て delete を
永久に中止して旧内容が残る)。
**論理名 → 物理名の解決 (§20.5・全操作共通)**: 論理名 (NFC・保存表記) を対象とする個別ファイル操作
(delete 最終確認 / restore in-place §21.4 / fsck working copy §13) は、論理名をそのまま path に
使わず、**検証済み root の readdir 列挙から walk と同じ規則 (NFC + case 折り畳み + 採用規則) で
raw エントリを解決して操作する** — NTFS / ext4 は lookup を正規化しないため、NFD 実体への NFC 名
書込は別エントリを新規作成して二重実体 (name_collision — restore 結果が敗者になり得る) を作る
(APFS は API が正規化非依存 lookup のため顕在化しない)。raw 無しの分岐 = delete 確認: absent 確定 /
restore: NFC で新規作成可 / fsck: 喪失報告。**この解決規則の欠落は major regression**。
**残余の TOCTOU 窓は 3 呼出点共通** — 解決と実操作の間の外部競合は次回 walk が
name_collision / update として収束させる (delete 確認限定の軟化の残存は不備 — restore / fsck にも
同じ許容を明記。**restore の rename 直前の再 lstat は in-place restore では義務 — r14 で「任意の
強化」から格上げ (P16 の 21.4)。delete 確認 / fsck では任意のまま。§20.5 側の記述もこの義務と
整合していること (「任意の強化 — 義務ではない」の残存 = r15 で補修した転記漏れの再発 = regression)**)。
delete 確定コミット時に行も削除)。**残留掃除**: 手順 5 後・手順 6 前クラッシュの pending 永久残留は
**tick ステップ 0 冒頭で「現在版 LWW が delete のファイルの pending_deletes / scan_cache 行」を
冪等削除**して回収。**fp_cache を確定しない枝 = 4 条件** (処理持ち越し / racy / pending_deletes /
**name_collision・name_invalid**)。**`.folder-history` の発見・規約 12 照合は fp skip の対象外**
(fp は ignore で `.folder-history` を含まない — cache 済み dir へ marker だけ持ち込む変化を
fp では検出できない)。fp_cache 孤児は完全 walk 成功時の mark-and-sweep。racy 比較は秒切り捨て
(mtime_ns/1e9 >= verified_at/1e3)。
**walk 対象 = watch_roots 配下 ∪ folders.root_path を重複排除** (重複 walk は「連続 2 回 absent」を
同一 tick 内に圧縮して偽 delete を生む。watch_roots 外へ移動されたフォルダのみ足す)。
**root_path の更新契機は「repository-id による再発見のたび」(起動時 + 定期 walk の両方 —
「起動時のみ」の記述は不足)。再発見で root_path を更新したら新 root_path 配下の fp_cache を
無効化する** (cache 済みパスへ `.folder-history` ごと移動されると dir_fp 一致で初回スキャンが
丸ごとスキップされる)。**rebind の条件は「旧パスの不在」に限らない** — walk が folders の
root_path と異なる位置で同一 id を発見し、旧位置が当該 repo の実体でない (パス不在 / marker 無し /
別 id — §21.1 の rebind 判定の自動化) 場合も rebind する (同一 id が 2 箇所実在する場合のみ
conflict。「無ければ再探索」限定の残存は、旧パスが別実体で再利用されたケースで健全な移動先を
放置し damaged へ誤誘導する)。**fork_in_progress の old_id / new_id は再発見・root_path 更新の対象外**
(中断中フォルダ移動で除外が外れ未完 fork が復帰する穴 — 回復は §21.3 journal 走査)。root_path 消失は missing。**猶予の起点は folders.missing_since**
(初回不在で一度だけ設定・再発見で NULL — last_seen 起算は即満了 / 毎 tick 更新は永久不満了に
壊れる)。**猶予 (既定 30 日) 満了後は tick が §9.3-d を実行して retired へ** (実行者・契機の明示)。
**walk 不完全 (stat 恒常失敗が 1 件) はそのフォルダの delete 確定を停止し続ける** — 偽 delete
防止を優先する意図されたトレードオフとして明記されていること (status 表示 + ユーザー対処)。
watch_roots は登録時に realpath 正規化 (同一 = no-op / 包含 = 拒否 + status)。
**case 規則**: case-insensitive ボリューム (macOS/Windows 既定) では同一性判定を case-insensitive
で行い、**保存する論理名は「系列の初出時の表記」に固定する** — 既存系列と case 違いで一致したら
既存の保存名を使い続ける。**case 感度は走査時のボリューム属性で判定** — フォルダ移動 (rebind /
再発見) 後は新ボリュームの属性で再判定する (保存名は不変。insensitive→sensitive 移動で現れた
case 違い実体は折り畳み無効化により別系列 = create — 系列分裂でありデータ喪失ではない、と明記)。
**逆方向 (sensitive で分裂した複数系列 → insensitive へ移動) で折り畳み一致する既存系列が複数ある
場合の採用 tie-break**: readdir 表記と BINARY 一致する系列 → 無ければ保存論理名の UTF-8 バイト昇順の
先頭を採用して継続し、非採用系列は以後の walk で通常の delete 確認へ (tie-break の欠落 = 採用が
実装・スキャン順依存になり、実体の無い系列が現在版のまま恒久残留 = 不備)。
**「判定は折り畳み・保存は readdir 表記」は不可** (保存表記が揺れると
file_versions の複合 FK (file_name, previous_commit_hash) が BINARY 照合で参照先を見つけられず
INSERT が FK 違反で失敗 — **SQLite の ON CONFLICT (OR IGNORE) は FK 違反に適用されず、「黙って欠落」
ではなくコミット Tx が毎スキャン音を立てて失敗し続ける** (旧「OR IGNORE なら黙って欠落」の残存は
事実誤認 = 不備。設計判断 = 保存表記固定は不変)、§11.1 の PARTITION BY file_name も同一ファイルを
2 系列に分割 — r9 で SQLite 再現済み。保存固定なら DB 内比較はすべて BINARY のままで正しい)。
**file_name 検証 (fail-closed)**: パス区切り・`..`・単独 `.`・絶対パス・NUL・空白のみ・
`.folder-history` を含む名前は name_invalid で管理対象外 (path traversal を保存側・restore 側で
塞ぐ)。**NFC / case 衝突の敗者は専用ステータス name_collision** (skipped とは別の恒久状態)、
採用は**物理名 UTF-8 バイト昇順の先頭 1 件** (readdir 順依存は誤り)。§20.5 手順 1/2/4 = **1 回の
ストリームで hash 計算 + tmp/ 書き込みを兼ね** (2 回 open は「hash A に内容 B」を許す)。
**open は O_NOFOLLOW 相当 + open 後の fstat で regular file を再確認** (lstat §20.4 と open の間に
symlink へ差し替えられフォルダ外を読む TOCTOU の防止)。**規約 12 照合済みフォルダへの以降の操作
(open / stat / rename) は検証済み root の dirfd に相対 (openat / RESOLVE_BENEATH 相当)** — 照合〜使用の
間に root の途中成分が別実体へ swap される窓を塞ぐ (最終成分の O_NOFOLLOW では root swap を防げない。
restore §21.4 / fsck §13 / **fork §21.3 (手順 0 journal・手順 2 repository-id)** の書込にも適用 —
fork の欠落は不備)。**rename 後に格納ディレクトリを fsync**
(objects/ への全書き込みに適用 — 規約 6)。時計の大幅前進は警告 (now < 最新コミット − 閾値
(既定 72h))。
**§21 = 明示操作カタログ** (**tick.lock は最大 N 秒ブロッキング取得** — tick の即終了と異なる。
**全操作は lock 取得直後に §21.3 の fork 回復 (fork_in_progress / journal 走査) を完了してから
本体を実行する** — lock は同時実行しか防がず、未完 fork を跨いで直列実行された操作は後の回復に
反転される (例: ID_WRITTEN クラッシュ後の unregister(old) が回復の手順 3 の folders(new) INSERT で
取り消される)。回復先行の欠落は major regression。**唯一の例外 = 破損 journal の明示解決 (§21.3) —
回復が完了し得ないため、この解決経路だけはゲートを bypass する** (例外の明記が §21 前文に無ければ不備)。
21.1 register — **手順 1 冒頭で対象の fork-journal を処理する: 有効 (digest 一致) = §21.3 の回復を
先に完了 (watch_roots 外へ移動された未完 fork の検出点 — 素通し register は後の walk 回復が register
後のコミットを反転する) / **破損 = 「読めたが digest 不整合・構文不正」のみ** — §21.3「journal の
破損」の明示解決のみを提示 / **一時的に読めない (AV/EDR ロック・EIO) は破損と区別して無変更保留 +
status** (規約 12 の「読めない ≠ 壊れている」を journal にも適用 — 区別の欠落は有効 journal の一時
ロックを履歴破棄へ誤誘導 = major regression)** (チェックの欠落は不備)。
**対象 .folder-history の存在と可読性を分離** (一時読取不能 = ロック / EIO は無変更で
保留 status。「読めない ≠ 壊れている」を register にも適用 — 存在を見落として新規初期化へ進むと既存
履歴を破壊的に再初期化する)。再発見は分岐: **旧 root_path が現存し同一 id の実体を持つ場合のみ
conflict / 旧 path 不在 (missing) なら rebind (root_path UPDATE + missing_since NULL) / 旧 path が別実体
(異 id / marker 無) も rebind / 対象 root_path が別 id の folders 行に既登録なら旧行を先に §9.3-d 退役
(root_path 1 実体 1 行) / 未登録なら INSERT** (「別 root_path 登録済みは常に conflict」だと missing 回復が
自己衝突)。新規初期化は embedding_vec を profile 確定まで作らず配下 fp_cache を無効化 / **一時読取不能を
damaged (= 破壊的再初期化) にせず保留**、readable だが構造破損のみ damaged / damaged 再登録は
旧 folders 行を先に退役 / 21.2 unregister —
削除は「(cancel 確定 or terminal) かつ (upload 清掃済み or upload 無) **かつ intent_token IS NULL**」の
行のみ、それ以外は detached
(P9 規範 — token 条件の欠落は major regression)、cost_ledger は残す / 21.3 fork = **入力は realpath 正規化した対象パス**。**journal 作成前に、folders[old_id] があり
root_path が対象と不一致 (移動済み・未 rebind) なら §20.4 の rebind 判定を先に完了する** (未 rebind の
was_tracked=false 誤判定 → 手順 3 が旧行を退役せず残す → 旧パスの別実体再利用で恒久 damaged 偽表示 —
先行 rebind の欠落は不備。conflict の非追跡側 fork は意図どおり was_tracked=false で生存側に触れない)。
**phase 状態
機械** (PREPARED→HISTORY_CLEARED→ID_WRITTEN→APP_DONE を層 1 の fork-journal に安全書込で進める。
journal は {old_id, new_id, realpath, was_tracked, phase}。app 側 fork_in_progress = (old_id,
realpath) は **(old_id, realpath) パス単位**で tick 全ステップから除外・規約 12 抑止 — old_id 単位
だと非追跡側 fork 中に生存側も凍結。**保存先 = app_config 'fork_in_progress' key (JSON {old_id,
new_id, realpath, started_at} —
tick.lock 直列化で高々 1 件)** — 保存先未定義の残存は不備。**started_at から猶予 (既定 30 日) を
超えて回復が完了しない場合、status を「fork stalled — 手動介入が必要」へ格上げする (表示のみ —
自動では何も変更しない)** — 恒久ストレージ障害・watch scope 外への移動で journal を発見できない
滞留の可視化。エスカレーションの欠落は不備)。defer_foreign_keys で commits 全削除
(順序保証は仕様に無く
防御的指定) → repository-id 安全書込 → **was_tracked (journal 固定値) の場合のみ folders 旧行 DELETE
+ agg/sync/cache 退役** (folders を消す明示が必須 — 残すと旧 root_path × 新 id の規約 12 恒久偽
conflict)、新 folders 行は INSERT OR REPLACE (再実行 PK 衝突なし。**root_path = 手順実行時点の実体
realpath (回復経由なら journal 発見パス) — journal の凍結 realpath ではない** (識別・除外・flag 削除
キー専用)。**INSERT 前に同 root_path の別 id 行を §9.3-d で退役** — §21.1 と同型) →
**flag → journal の順で削除**
(逆順は「電断後の移動」と重なると flag が掃除不能 = 恒久除外 — 理由文はこの複合ケースで精密化済み)。**回復契機 = 毎 tick 冒頭 (journal 無でも realpath に
.folder-history 実体が現存し、**かつ marker の repository-id が fork_in_progress 記録 (journal 不在の
分岐なので照合元は flag の JSON — 「journal 記録の」という給源表記は字句誤り) の new_id と一致する
時のみ** flag 掃除。**id=old + journal 無は掃除せず damaged / 明示解決待ち** (手順 4 の削除順
(flag 先・journal 後) の下で正常系に生じない = journal の異常喪失の示唆。old でも掃除する旧規則は
履歴消去済み・id=old の未完 fork を通常運用へ復帰させ、fork の意図 (新 id) を黙って破棄する —
old/new 両許可の残存は不備)。実体ごと不在 = 移動は保留、**id が old/new 以外 (旧パスが別 repo に
再利用)・読取不能も
保留** — id 未確認の「実体があれば完了」推定は移動した未完 fork の flag を誤掃除する) +
bootstrap / walk の
journal 走査 (移動先で発見し再発見より先に回復)**、再開位置は phase + 実 id から一意 (**id=old なら
手順 1 から**。**HISTORY_CLEARED で commits 非空なら手順 1 から** = 中断中に移動・再発見され old_id で
新規コミットが積まれた場合の是正。「常に手順 3〜4」は旧 id のまま新 folders を作り即 conflict)。
**journal は版付き canonical record + SHA-256 digest** (構文上有効な改竄を検出) — 読めない /
digest 不一致は damaged (**「読めたが不整合」のみ — 一時読取不能は保留**、§21.3 側も三値)。
**明示解決の実体 = §20.4 の damaged 復旧: ユーザー確認の上で **(1) 破損 journal を除去 (flag は
残す) → (2) §21.1 手順 2 (新 id 初期化) → (3) flag は毎 tick 冒頭の (a) 規則 (id=new → 掃除) が
回収**する順序 — 途中クラッシュは「journal 無 + flag 有 + id=old = 明示解決待ち → 再実行で冪等」
か「id=new = flag 掃除」に着地し解決の意図が失われない (journal と flag の同時除去 → 初期化の
順序は、間のクラッシュで空履歴 old-id repo が通常運用へ復帰 = 不備)。この経路のみ §21 前文の回復先行
ゲートの例外** (解決経路の未定義 = 前文ゲートが全明示操作を恒久ブロックし脱出不能 = major
regression)。**回復表には「実体 id が old/new 以外 (第三の id) = damaged 停止 / 一時読取不能 =
保留」の行があること** (old/new だけの表で推測正常化する実装 = 不備) / 21.4 restore = **規約 12 照合を先に実行** (別 repo 置換
の working tree を上書きしない) + 宛先必須 (in-place は非 delete 三組・content_hash 単独は明示宛先)
+ file_name 検証 + hash 照合 + **in-place は書込前に対象の現内容を安定確認し、LWW と異なれば
先に §20.5 手順でコミットして履歴化する** (未取り込みの working 変更を黙って上書きしない —
履歴ツール自身の唯一の不可逆喪失経路。**保全なしの残存は major regression**。宛先の物理名は
raw 解決 — P16 resolver)。**安定確認自体の失敗 (2 回の stat 食い違い・読取エラー) は上書きへ進まず
restore を中止 + status** (「スキップして続行」は保全の素通り = 喪失経路の再開 — 失敗分岐の未規定は
regression)。**rename 直前に解決先 raw を再 lstat し、保全時の (size, mtime_ns, inode) と不一致なら
中止 — in-place では義務** (残余窓は §20.5 TOCTOU 同族の既知の残余と注記されていること)。
**対象 raw エントリの不在は「安定確認の失敗」と区別し、保全対象なしとして §20.5 resolver の規則
どおり NFC 新規作成へ進む** (混同して中止すると raw 無しへの正当な復元が恒久不能 = 不備)
→ tmp→rename→dir fsync、履歴反映は次 tick スキャン経由 / 21.5
watch_root add/remove + bootstrap (**app_config の現行 profile・image_filter 再入力 + watch_roots 外の
登録フォルダの個別パス再入力**を含む。**watch_roots 自体の復元起点の cite = 規約 9** — 「規約 7」参照の
残存は不正確。**解除の app Tx で walk 範囲外になる配下 fp_cache 行を明示 DELETE** — M&S は walk
主体が消えた領域を掃除できないため「M&S が掃除」の旧記述は誤り) / 21.6 drop-derivation (**入力に対象フォルダを含む** — 派生台帳は
フォルダ独立 §18.6。GC fail-closed の回復。**自動再投入の注記は「現在版 or backfill ON の過去版参照」
両方** — P13 + in-flight 後着受け入れの注記))。
**規約 12 (scoped read 拡張)**: フォルダ DB を開いて書き込む・レプリケーションする全操作で
repository-id を folders 行と照合、
不一致 = conflict 停止 (fork 進行中は当該 realpath のみ抑止)。**読み取り専用操作 (単独検索・
履歴閲覧・§12 解決) も対象パスが folders に登録済みなら照合必須 — 不一致は conflict で結果を
返さない** (書込限定の残存 = major regression: 差し替えられた別 repo の内容を provenance 偽装のまま
返す)。**folders に行が無いパスの読み取り (未登録・持ち込みコピーの standalone 検索) は層 1
自己完結 (§2) の正規利用として実行可 — repository-id を provenance として表示する** (無条件
fail-closed はコピー検索の自己完結と矛盾するため誤り)。**同 repository-id が folders の別 root_path で
登録済みなら「登録済み複製の重複コピー (conflict 中ならその旨)」を provenance / status に付す**
(黙って返すと conflict の非主流側を正本と誤認させる — 欠落は不備)。**standalone 読み取りも対象の
fork-journal を preflight で検査する — 有効 = 「fork 進行中」status で保留 / 破損 = damaged**
(journal を層 1 に置く目的 = app 全損を挟む「fork 中断」と「空履歴の通常 repo」の区別 (§21.3 手順 0)
は app を持たない読み手にも適用される — 検査の欠落は未完 fork の空・部分履歴を通常として返す = 不備)。**照合の読取失敗は 4 分類を全 open に適用**:
一時読取不能 = 保留 + status / 読めるが構造不正 = damaged / 不一致 = conflict / 不在 = damaged・
missing (一時失敗を conflict / damaged に倒すと破壊的解決へ誤誘導 — M13 の register 分離の一般化)。
**fork_in_progress (§21.3) の対象 (old_id, realpath) は、呼出元を問わず (tick 内外・読み書きとも)
本規約の照合・conflict 判定の適用対象から除外する — 共有ガードとして実装**
(fork 手順 2〜3 の間は実体 id = new・folders = old が正常な中間状態。tick 経由だけの抑止は tick 外の
単独検索が fork 中に誤 conflict を返す)。fork 中の読取要求は conflict でなく「fork 進行中」status。

**P16 追補 (r16)**: ①破損 journal 明示解決の手順 (2) は**新規採番せず flag (fork_in_progress) の
new_id を採用** (新規採番 = 第三 id → (a) 規則が掃除不能・realpath 恒久除外。flag 不在・読取不能時
のみ新規採番)。②restore の rename 直前再 lstat 義務は **raw 不在分岐にも適用** (不在 → 出現 =
不一致で中止) + 可能なら **no-replace rename** (RENAME_NOREPLACE / RENAME_EXCL / MoveFileEx 非置換)。
③rebind の action に**旧 root_path 配下の fp_cache DELETE**。④journal digest の目的 = **部分書込・
bit-rot 検出** (悪意ある改竄への耐性ではない)。⑤**同一 dir 内に case 違いのみの実体併存を検出したら
当該 dir は case-sensitive 扱い** (per-directory 感度への備え — 併存の事実が最強の証拠)。

**P16 追補 (r17)**: ①no-replace rename **非対応環境の規範** — 判定は初回試行エラーで確定 (ボリューム
単位記憶可)・fallback は「再 lstat + 通常 rename + 残余窓の明示的引き受け」限定・EEXIST 相当は常に
中止 (黙って置換 rename = 不適合)。②rebind の fp_cache DELETE は **3 箇所共通** (§21.1 missing /
§21.1 別実体 / §20.4 自動 rebind — 「rebind の実体は §21.1 と共通」)。③fork-journal record に
**started_at** (app 全損後も journal 単体で stalled 判定)。④case override は **sensitive 方向のみ** —
casefold dir on sensitive volume は併存証拠が原理的に出ない (属性照会可能な FS では dir 属性優先・
不能環境の分裂は喪失なしの既知挙動)。⑤resolver の採用規則は **walk の case 規則と同一実装を共有**。

**P16 追補 (r18)**: ①構文検証スキップは**有界** — 同一 (size, mtime_ns, inode) で連続 3 回/24h
失敗 = 安定内容として bytes のままコミット (保存は bytes ベース)。②管理フォルダ内 export =
**新規作成限定・no-replace 必須・既存実体は中止**。③walk に**訪問済み (st_dev, st_ino) 集合**
(bind mount・junction 循環の拒否)。④**未来 mtime の racy 例外** — 段 2 hash 一致で fp 確定可。
⑤滞留可視化の started_at は **flag 不在時 journal へフォールバック**。⑥§21.6 の再課金回避 =
「unregister **して watch_root 外へ移す**」(単独では再発見で再登録)。⑦flag 不在明示解決の crash
窓 = 解決前状態への復帰で安全側。

**P16 追補 (r19)**: ①有界スキップのカウントは **scan_cache に永続化** (syntax_fail_count /
first_failure_at 列 — stat 変化・成功で reset、一時 EIO・安定確認失敗はカウント外)。②再開表に
「**ID_WRITTEN / APP_DONE なのに id=old = 不可能組合せ → damaged 停止**」の独立行。③**fp 入力から
.folder-history を除外** + **fp 一致スキップの例外 = fork-journal 存在検査**。④(st_dev, st_ino)
不安定 FS = watch_root fail-closed。⑤明示操作のブロッキング = N 秒 (既定 30 秒・設定値)。
⑥§21.6 の退避回避策は **backfill OFF と併用**。⑦チャンク規則・フィルタは **device-local** —
コピー再登録の規則差は明示一括再チャンクで収束。⑧bytes 原則の参照は「(§1 の原則)」(文書内に
定義の無い「(P1)」等は不可)。

### 調査内容 (検査観点)

- **C1. 原則反映**: P1〜P16 の各項目について、対応する記述が文書に存在するか。存在する場合、
  内容が原則と一致するか (弱められたり条件が落ちたりしていないか)
- **C2. SQL 静的検証**: 全 DDL について — (a) SQLite 文法として妥当か (GENERATED 列の構文、
  WITHOUT ROWID と PK の関係、CHECK の論理)、(b) **FTS5 external content の content に指定された
  テーブルが rowid を持つか** (WITHOUT ROWID テーブルを content に使う誤りの検出)、
  (c) FK の参照先テーブル・列が存在し列数が一致するか、(d) trigger の insert/delete ペアの整合、
  (e) 「同形」「同一定義」等の省略記法が、実装者が一意に再現できるだけの具体性を持つか
- **C3. 相互参照整合**: 文書内の §参照 (例: §15 規約 4、§18.1) がすべて実在し、参照先の内容が
  参照元の文脈と一致するか
- **C4. クエリとスキーマの整合**: 文書中の全 SQL クエリ (ハイブリッド検索、GC、差集合) が
  同文書の DDL と整合するか — 存在しない列・テーブルの参照、join キーの型/形式の不一致、
  CTE で定義した列と使用箇所の不一致 (例: current_files に repository_id が必要な文脈で
  定義に含まれているか)
- **C5. 数値・事実の一貫性**: $2.5/1k、+25%、768 次元、RRF k=60、テーブル数の言及
  (「7 テーブル」等) が全出現箇所で一致し、DDL の実数と合うか
- **C6. 用語・形式の一貫性**: target_key の連結形式が §間で同一か
  (hex の有無、区切り、順序)、chunk_type と target_type の対応、obj:<hash> スキーム、
  embed_hash の定義の再掲間の一致
- **C7. 状態機械の完全性**: batch_requests の state 遷移に到達不能・脱出不能がないか。
  クラッシュ位置ごと (objects 書き込み後 / metadata Tx 後 / app 更新前) に次の tick が
  収束するかを文書の記述だけで追えるか
- **C8. 欠落**: 原則 P1〜P16 の範囲内で、文書に書かれるべきだが章として欠けている事項
  (範囲外の一般論は proposal へ)
- **C11. 合理性 (実装可能性・実行可能性)**: 決定済みの設計選択 (§18 / §19 で決着済みのもの) の
  再評価は行わない。その上で次を検査する — (a) 記述された手順・SQL・規範を、実装者が**追加の
  設計判断なしに**実装できるか (未定義の入力・分岐・失敗処理の欠落)、(b) 規範同士が実行時に
  両立するか (ある規範に従うと別の規範が守れなくなる組み合わせ)、(c) 文書内のコスト・性能・
  頻度の主張が自身の設計と矛盾しないか、(d) 検証不能または実行不能な過剰規範がないか。
  判定は major (実装不能・両立不能) / minor (曖昧だが実装者が安全側に倒せる) /
  proposal (改善余地) に振り分ける。これは文書内部の整合検査であり、
  外部のベストプラクティスを根拠に持ち込む許可ではない
- **C12. 探索型監査 (r16 の主眼)**: 原則リストの外に出て、監査者自身の専門知識で新規の設計不備を
  探す。**下記の探索観点 X1〜X78 の各観点について最低 1 つ、計 78 以上の具体シナリオを実際に
  「手で」実行する** — 文書の規範だけを使って初期状態から操作列をステップ実行し、各ステップで
  どのテーブル・ファイル・状態がどうなるかを追い、破綻 (データ喪失・不整合・課金事故・
  デッドロック・誤検索・復旧不能) を探す。X1〜X78 は seed であり、これに**限定しない** —
  監査者の直感で怪しいと感じた領域を自由に掘ってよい (むしろそれを推奨する)。
  X1〜X74 は r6〜r19 の計 80+ 系統監査で深く採掘済みのため各 1 シナリオで可。
  **r20 は X75〜X78 (r19 修正の相互作用 — scope_id が開ける穴・abandoned × 遷移表・fp スキップ
  例外の検査コスト・ガード拡張 × floor 順序) と自由探索、および補修 6 件の再発検査 (V01〜V06) に
  重心を置く** —
  特に X75/X76 は「fix が開ける穴」の定番パターンであり本命 (r8:17 件、r9:fatal 6 クラスタ +
  major 20、r10:fatal 4 + major 20、r11:fatal 1 + major 12、r12:major 8、r13:fatal 1 + major 8、
  r14:major 7、r15:major 8、r16:major 9、r17:major 5、r18:major 6、r19:major 5 をこの脈で開けた
  前科がある — 定番脈は **24 例目** (r19 = ①r18 有界スキップのカウンタ永続化不在 (4 系統・X74)
  ②r18 ガードの state=2 穴 (floor 明示再生成 — X71) ③r18 scope 規範の保存基盤なし) まで的中。
  破壊型 regression は 8 ラウンド連続 0 だが **r16〜r19 の 4 ラウンド連続で「前ラウンド適用の
  非伝播・実装基盤の不在」が回帰の主因** — 収束は本物に見えるが「もう出ない」と決めつけず
  総当りすること。
  **r15 で新設・変更された規範そのもの (自己記述化・submit_rejected 除外・detached terminal 化・
  (i)〜(iv) 1 Tx・伝播猶予の過去側定義 + 採用条件・相 1 共有終端ガード・decoder 対称化・journal
  三値・明示解決の順序・:current_tool tie-break) が今回の一次攻撃対象である**)。
  ただし探索の指摘にも前提の二本立て規則 (再現シナリオ + 文書引用) を適用し、
  §18 / §19 で決着済みの設計選択そのものへの異論は出さない — **決着済み選択の「帰結として生じる
  未対処の問題」は正規の指摘として可** (選択への異論と区別する)。

### 探索観点 (C12 の seed — 限定列挙ではない)

```text
X1  時系列シミュレーション: 現実的なシナリオを自分で構成し、文書の規範だけでステップ実行する。
    例: 作成→編集→削除が 1 tick 間に起きる / OCR in-flight 中にファイルが削除・改名される /
    backfill と明示再生成の交錯 / フォルダ移動と tick の競合 / 2 台の PC へフォルダをコピーして
    双方で編集後に片方を書き戻す (LWW と repository-id の挙動)
X2  敵対的・異常入力: ファイル名に改行・制御文字・"obj:" や "<!-- img:" を含む / 超長名 /
    大文字小文字だけ違う 2 ファイル / 0 バイトファイル / シンボリックリンク・ハードリンク /
    annotation 値によるコメント脱出 ("--\>" 以外の手段は?) / 保存済み Markdown 内の obj: 参照の
    手書き偽造や巨大 img block
X3  ファイルシステム多様性: case-insensitive (macOS/Windows 既定) と case-sensitive の間の
    フォルダ移動 / NFC・NFD (macOS は NFD を返す — file_name の NFC 正規化 §4.1 と衝突しないか) /
    パス長上限 / ネットワークドライブの stat 意味論
X4  時間: 時計後退・NTP ジャンプと LWW / 同一 ms 内の複数コミット / created_at 衝突時の
    タイブレーク / generated_at 単調規則と壁時計の関係
X5  スケール・計算量: 10 万ファイルの walk と fp 計算 / 100 万 chunk での FTS・KNN・
    レプリケーション全置換のコスト / SQLite の実制約 (bind 変数上限、IN 句の長さ、
    式 CHECK の評価コスト) / agg_chunks の全置換が起きる頻度と量
X6  依存技術の実制約: FTS5 trigram は 3 文字未満のクエリで何を返すか (日本語 2 文字語の検索) /
    sqlite-vec vec0 の実際の制約 (KNN 以外の述語、トランザクション境界) / Mistral Batch の
    入力上限 (1 ファイルのサイズ・ページ数・job あたり行数) / JCS の数値制約 (i64 超の値) /
    UUIDv7 の時刻依存性
X7  スキーマ進化: metadata.sqlite / app.sqlite に schema_version が無い — 将来の列追加・
    テーブル追加の手順、新旧アプリバージョンが同じ DB / フォルダを開く混在シナリオ、
    canonical img block grammar 自体の将来変更 (grammar version が無い) の影響
X8  セキュリティ・プライバシー: tmp/ と objects/ の権限 / file_name の path traversal 検証
    (file_name に ".." や絶対パスが入った場合の restore 相当操作) / Batch へ送る原本の扱いと
    ログ / app.sqlite を他ユーザーが読める場合の情報露出
X9  運用・復旧: バックアップ (フォルダコピー) 中の書き込み / objects/ の 1 ファイル欠損・
    破損をいつ誰が検出するか (fsck 相当の検証手段の有無) / ディスク満杯が各書き込み点
    (objects → metadata → app) で起きた場合 / metadata.sqlite だけ復元した場合の再構築手順
X10 ユーザー操作との競合: .folder-history の手動削除・中身の手動編集 / フォルダの zip 化→解凍
    往復 (mtime・inode 全変化) / 同期ソフトによる .folder-history 内ファイルの部分同期・競合コピー
X11 r6 修正の相互作用 (fix が開けた穴): r6 で 30 修正が一気に入った — 修正どうし・修正と既存
    規範の新たな衝突を重点的に掘る。例: NFC 論理名 (§20.5) と fp の非正規化 name (§20.3) の
    2 層の変換点は一意か / FTS の view 化 (§5.5) と chunks への trigger・'delete' コマンドの
    整合 / 単調 created_at と LWW・カーソル・複数フォルダの関係 / preflight の非対象ファイルと
    backfill の対象選定 / grammar v 混在期間の解析 / **profile 変更の kind=2 全行削除 (§8) が
    cost_usd の課金履歴 (§9.1 は行に累積) を道連れに消す問題** / floor_generated_at と
    reconcile (0.5) の相互作用
X12 エンドツーエンド・トレース: 「watch_root 登録 → フォルダ発見 → 文書追加 → スキャン →
    コミット → OCR → チャンク → embed → replicate → 横断検索 → 結果から原本を開く → 履歴表示 →
    過去版の復元」を文書の規範だけで一気通貫にステップ実行し、**受け渡しが未定義で途切れる箇所**
    を探す (各ステップの入力がどの § の出力から来るか言えるか)
X13 未定義操作の総点検: 文書中の「status に表示」「明示操作」「明示解決」「明示再登録」
    「明示再生成」「誘導」をすべて列挙し、それぞれについて操作の入力・手順・効果・失敗時の
    挙動が文書内で定義されているか (実装者が UI / CLI を追加設計なしに書けるか) を検査する
X14 資源とレート: プロバイダの 429 / レート制限が submit・collect に当たったときの挙動 /
    app.sqlite・fp_cache・scan_cache の肥大と掃除 (fp_cache は消えたディレクトリの行を誰が
    消すか) / objects の総容量の可視化・上限
X15 反証探索 (claim-refutation): 文書が明示的に主張する防御 (「〜を防ぐ」「〜は起きない」
    「〜で収束する」「〜が保証される」) を 5 つ以上選び、各主張を破る操作列の構成を試みる。
    破れなければ探索ログに「主張・試行・破れず」を記録する
X16 r7 修正の相互作用 (fix が開けた穴 — r8 の本命): r7 で約 30 修正が一気に入った。例:
    2 相 submit と「1 job = 1 repository」・JSONL 複数分割の整合 (intent_token は job 単位 —
    分割時の token 粒度と回復) / reconcile の縮小 (state 0,3) で「成果あり state=1」が collect
    不能な状況 (job 消滅・アカウント変更・provider 移行) でも閉じ漏れないか / cost_ledger
    追記点の網羅と冪等性 (collect 再実行・client 側キュー・kind=2 の単価が取れないプロバイダ) /
    floor の NULL 戻し (§10 2-d) と §5.3 の単調規則・§9.3-b の generated_at 伝播 /
    profile 内 attempts 計数 (§8-a) の実装可能性 — profile_hash 列は最新投入時の値 1 つだが
    数え直し判定に十分か / 相 1 の batch_job_id NULL 化と idx_batch_open・collect の突合 /
    upload_id 上書きと未清掃残骸の追跡
X17 §21 操作カタログの E2E: register の途中クラッシュ → damaged → 再実行 / fork 後の派生保持と
    GC・agg の整合 (旧履歴だけが参照する object の回収、旧 repo の agg wipe、新 repo の初回
    コミットと backfill) / restore 直後のスキャンが update を拾って履歴に乗る一連 /
    unregister → 再登録の全量再同期 / 各操作と tick.lock・進行中 tick の排他
X18 新テーブルの整合: profiles の孤児・不整合 (embeddings に無い profile_hash の行、record_json
    改竄の検出点、レプリケーションで集約側に profile record は要るか) / pending_deletes と
    deep-scan・fp 確定禁止・walk 完全性条件 (H03) の相互作用 (部分 walk 失敗時に pending は
    増えるか消えるか) / cost_ledger の app 全損後の意味論 (「記録できた課金」の下限性は
    どこに明記され、月次レポートの正確性主張と矛盾しないか)
X19 電源断・中断の再総当り (r7 で耐久規範が変わった): ディレクトリ fsync の適用点の網羅
    (objects の各 prefix / tmp / §21.1 の .folder-history 新規作成 / metadata.sqlite 自体) /
    migration 単一 Tx と journal_mode (DELETE / WAL) の関係 / 2 相 submit の各境界 (相 1 直後・
    相 2 途中・相 3 直前) でのクラッシュ反復と課金上限 / §21 各操作の途中クラッシュ
X20 反証探索 (r7 更新版の主張): 「重複課金は intent 回復により最悪 job 1 回分」「cost_ledger は
    月跨ぎ retry を発生月へ正しく配賦」「宣言的 profile 変更はどのクラッシュ位置でも収束」
    「fork は履歴再初期化で整合し派生は保持できる」「delete は pending_deletes で見逃さない」
    「rename 後 dir fsync で規約 6 の存在保証が成立」等を破る操作列を試みる
X21 r8 修正の相互作用 (fix が開けた穴 — r9 の本命): 2 相 submit の相 1 に profile_hash /
    upload_cleaned リセット / attempts=0 リセットを足したこと (J01/J02) と、intent 回復・
    reconcile・collect の突合が新たに食い違わないか / floor 引き上げ (J04) と §5.3 明示再生成・
    §9.3-b generated_at 伝播・§9.1 成果判定の三者整合 / vec 差集合再充填 (J05) と §8-b 置換・
    §8-d 掃除の二重実行や取りこぼし / app_config (J07) の更新点 (§8 変更・register・fork) の網羅と
    §8-e agg 検査が読む agg 構築 profile key (r10 以降は agg_building/ready_profile_hash — L09/M03) の
    書込点 / job_missing (J03) と result_expired・
    output_missing・detached job の分類境界
X22 §21 fork 耐久手続きの E2E (J13/J14): fork_in_progress の設定・解除・クラッシュ回復を全境界で
    追跡し、規約 12 抑止の窓が広すぎて別の不整合を通さないか / defer_foreign_keys Tx と
    §14 の foreign_keys=ON / journal_mode の相互作用 / 旧 app 行退役と新 folders INSERT の順序で
    conflict 検出や walk が誤らないか / fork と並行 tick・unregister・register の競合
X23 新テーブル・新ステータスの整合 (J06〜J09, J16, J18, J20): app_config / cost_ledger (NULL・
    estimated・UNIQUE) / detached batch_requests / name_collision / name_invalid が、それぞれの
    読み手 (集約・検索・status・GC・walk・restore) すべてで一貫し、未定義の分岐や到達不能行を
    作らないか / cost_ledger の UNIQUE と冪等再実行の相互作用 (二重計上防止が正当な再投入の
    記帳を妨げないか)
X24 宣言的収束の再反証 (J05 更新版): 「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」
    「agg 毎 tick 検査は一度きり破棄の喪失を吸収する」「client 側キューは state=1 を跨がないので
    intent 回復不要」を、次元変更・model 変更・部分充填・中断を組み合わせて破る操作列で試す
X25 E2E とデータ経路の未定義 (J07/J08/J16): app.sqlite 単独 (フォルダ未接続) での横断検索が
    app_config だけで実際にクエリ embedding を作れるか / restore の宛先検証が in-place・
    エクスポート・delete 版・content_hash 単独の全入力で一意に定まるか / watch_root 解除
    (§21.5) 後に folders 起点 walk が続くフォルダの扱い
X26 r9 修正の相互作用 (fix が開ける穴 — r10 の本命): **submission_seq × attempts × ledger の
    三者** — seq の書込点は相 3 / intent 採用 / client 前計上の 3 つで重複・欠落しないか、
    載せ直し (相 1 再通過) で seq は動かないか、detached の終端記帳と seq、ledger UNIQUE と
    冪等再実行 (同一 seq の close Tx 再実行は IGNORE でよいか) / **profile_record snapshot** —
    相 1 の UPDATE で旧 snapshot が残るケース、app_config 未設定 (bootstrap 前) の相 1、
    §5.7 profiles との hash 不一致 snapshot、detached 経由の profiles 書込は起きないか /
    相 2 恒久拒否 (submit_rejected) と成果あり reconcile・明示 retry の順序 / **client 前計上と
    server intent 回復の判別** (state=0 + batch_job_id 非 NULL = client 済みをどう区別するか) /
    floor 引き上げの app 先行順序とクラッシュ窓の再検証
X27 fork journal の E2E: journal 書込→手順 1→2→3→journal 削除の全境界クラッシュ + 再開 /
    journal 自体の残骸 (完了後の削除失敗) や破損の扱い / 非追跡側コピー fork で生存側の
    追跡・in-flight・agg が無傷であることのトレース / fork 中 tick 除外と dirty・watch_root
    walk・§9.3-d 猶予の相互作用 / fork 直後の bootstrap (journal 検出→回復→再発見) の順序
X28 detached の全ライフサイクル: 生成 3 経路 (unregister / §9.3-d 猶予満了 / fork) → collect の
    payload 破棄 → 記帳 → upload 掃除 → 行削除、を各 state (0/1/2/3) で追跡 / **detached 中に
    同一 repository_id が再登録された場合** (folders 復帰で detached 条件が消える — 行は通常行に
    戻るのか、その時 in-flight と新規 submit は衝突しないか — PK は同一) / detached の
    upload_cleaned 掃除は「全行終端」条件と両立するか
X29 保存名固定 (case 規則) の E2E: 初出表記固定と restore の宛先・status 表示・NFC 衝突
    (name_collision) の相互作用 / case-sensitive ボリュームへフォルダを移動した後に大小文字
    違いの 2 実体が共存した場合 (固定した保存名とどちらが照合されるか) / §11.1 PARTITION が
    BINARY 一致で正しく単一系列になることのトレース / 初出表記の決定 (create 時の readdir 表記)
    と §4.1 の NFC 正規化の順序
X30 反証探索 (r9 更新版の主張): 「ledger の UNIQUE (…, submission_seq) は正当な再課金を一切
    妨げない」「client 経路の重複課金は attempts 上限で有界」「fork はどの境界のクラッシュ
    からも journal で一意に再開できる (app 全損を含む)」「保存名固定により case-only rename の
    FK 違反は構造的に不可能」「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」
    「detached は課金を取りこぼさない」を破る操作列を試みる
X31 r10 修正の相互作用 (fix が開ける穴 — r11 の本命): **submission_seq 継承 × ledger** —
    継承の SELECT MAX が走る点 (§5.3 / 相 1 / register) の網羅、複数 target が同 tick で採番する
    競合、ledger が空 (初回) の COALESCE、継承値と相 3 の +1 の二重加算はないか / **reconcile
    close の 3 付随処理** (floor NULL 化 / NULL+estimated 記帳 / token 掃除) が state=0 と state=3
    で漏れなく走るか、collect の close と重複記帳しないか (submission_seq で防げるか)、
    kind=2 の close に floor NULL 化を誤適用しないか / **submit_rejected の attempts=上限**設定と
    明示 retry (attempts=0) の往復、rejected 後の upload 掃除 / **client_exhausted** の記帳と
    detached 化の境界
X32 fork phase 状態機械の全数トレース: PREPARED / HISTORY_CLEARED / ID_WRITTEN / APP_DONE の
    各 phase × (通常クラッシュ / app 全損 / journal 破損) で再開位置が一意か、was_tracked の
    journal 固定値と回復時の実 folders 状態の乖離、flag→journal 削除順の逆転耐性、INSERT OR
    REPLACE の再実行冪等性、(old_id, realpath) 除外中に realpath が変わる (fork 中にフォルダ移動)
X33 課金記帳の網羅行列: (server / client) × (成功 / result_expired / job_timeout / job_missing /
    output_missing / profile_changed / submit_rejected / tool_changed / client_exhausted) ×
    (通常 close / reconcile close / detached close) の各セルで cost_ledger 行が 0 or 1 行
    (二重も欠落もなし) になるか、submission_seq がセルをまたいで一意か
X34 検索の完全形と境界: §11.2 の掲載 SQL を実際に組み立て (eligible × agg_chunks 再 JOIN の
    LIKE fallback / ORDER BY 第 2 キー / agg_ready 照合 / at_hash=FF) 実行可能性を確認、
    ready 未更新中 (再構築窓) の FTS-only 応答、単独検索の部分 KNN と未 embed 残数 status
X35 反証探索 (r10 更新版の主張): 「seq 継承で行削除→再作成の UNIQUE 衝突は不可能」「reconcile
    close の付随処理で client の記帳欠落は起きない」「submit_rejected は自動再投入されない」
    「fork は id=old からでも journal で正しく再開する」「detached は課金を取りこぼさない (r10
    改訂後)」「delete 確定直前の最終 stat で時計急変の偽 delete は不可能」を破る操作列を試みる
X36 r11 修正の相互作用 (fix が開ける穴 — r12 の本命): **冪等記帳 (ON CONFLICT DO NOTHING) ×
    submission_seq 継承 (L01) × detached 採用 seq+1 (M06) の三者** — 全 close 経路 (collect 成功 /
    terminal 化 / reconcile・submit close / client_exhausted / detached / item 失敗 / invalid_output) の
    記帳が seq で一意か、冪等吸収が正当な別 attempt の課金を落とさないか (M06 が seq+1 する必要性の
    逆検証 — もし seq を増やさず ON CONFLICT に頼ると detached 採用の課金が消えないか)、
    profile A→B→A の同一 seq 衝突が本当に吸収され close が進むか、reconcile close (c) の Tx 外 token
    掃除 (M29) と close app Tx の原子性、item 失敗 / invalid_output の記帳と非課金 provider の両立
X37 ready 完了追跡 (synced_profile_hash, M09) の全数トレース: missing / fork 除外の母数定義、
    §9.3-c の (i) re-embed 被覆完了 と (ii) agg 複製差集合空 の判定、一部フォルダ missing での
    ready 窓 (KNN 停止の範囲)、agg_vec 差集合再充填 (M09) と ready 判定の順序、synced_profile_hash の
    更新点 (§9.3-c) と §8-e の読取の一貫、profile を再変更 (building が P2→P3) した際に旧 building で
    書いた synced_profile_hash が陳腐化しないか、fsck agg 差集合検査と再充填の分担
X38 fork 回復の拡張 (M05/M19) の全数トレース: flag 掃除の「realpath に .folder-history 実体現存」
    要件 × 中断中フォルダ移動 × 再発見の fork id 除外 (M05) の三者が組み合わさった全経路、
    HISTORY_CLEARED で commits 非空なら手順 1 から の判定 (何をもって「非空」とするか)、journal の
    版付き canonical record + digest (M19) の検証点と改竄 / 部分破損の検出、app 全損 × フォルダ移動 ×
    digest 不一致 の組合せ、移動先での journal 走査 (bootstrap / walk) と §9.3-d 猶予の競合
X39 register / detached / 検知周辺の相互作用 (M02/M08/M11/M13/M28): 一時読取不能保留 (M13) ×
    damaged 誘導 (破壊的再初期化) の境界、同 root_path 別 id の退役 (M11) × rebind × conflict の分岐、
    delete 最終 stat の型判定 (M08) × 対象外型置換 × pending の三値、root dirfd 束縛 (M28) ×
    restore / fsck / scan の各書込、§21.2 の §9.1 委譲 (M02) × 再登録 × PK 共有
X40 反証探索 (r11 更新版の主張) + 保留エッジの再評価: 「冪等記帳で close Tx abort は構造的に不可能」
    「ready は空 / 部分 index を通さない」「fork 中フォルダ移動でも未完 fork は通常運用へ復帰しない」
    「一時読取不能で既存履歴は破壊されない」「delete 最終確認は対象外型置換を見逃さない」
    「query_profile_hash 固定で embed 中 profile 変更の TOCTOU は不可能」「vec の距離変更は必ず
    DROP→CREATE される」を破る操作列。加えて **保留した単一系統エッジ**を再評価する:
    standalone (単独フォルダ) read が規約 12 (repository-id 照合) を通るか / restore が論理名 (NFC) から
    現在の raw 物理名へ逆解決するか / drop-derivation + backfill ON が過去版を再 OCR しないか /
    code fence (``` / ~~~) 内の # の解析仕様 / §2 の app 全損要約が規約 7-f を反映するか /
    case-insensitive→sensitive のボリューム間移動での系列の扱い
X41 r12 修正の相互作用 — 記帳経路の網羅行列の再検証 (r13 の本命): **(server / client) × 全終端理由
    (成功 / expired / timeout / job_missing / output_missing / invalid_output / item 失敗 /
    profile_changed / submit_rejected / tool_changed / client_exhausted / 期限超 confirmed-absent) ×
    全 close 経路 (collect / reconcile close b・b' / detached (a)(b) / client 再実行前記帳)** の各セルで
    cost_ledger 行が 0 or 1 行・submission_seq が一意かを総当り。特に: client 再実行前記帳 (旧 seq) と
    client_exhausted (旧 seq) の重複は冪等吸収で正しいか / (b') の seq+1 と後続 token sweep・detached 化の
    交錯 / 期限超 confirmed-absent 記帳 (seq+1) → 載せ直し → 相 3 (さらに +1) の連番と ledger の整合 /
    三値 unknown 保持中に成果あり化した行は reconcile close (b') と intent 回復のどちらが先に触るか /
    submit_rejected (client) の「記帳なし」と「実行された可能性」の境界 (呼出前 4xx は本当に未実行と
    確定できるか — 送信中断・応答喪失との区別)
X42 ready 母数と synced の動態: 母数 = 「当該 tick に §9.3 を実行できたフォルダ」の全数トレース —
    damaged / 一時読取不能 / missing / fork の出入りで ready が過渡的に立つ・落ちる系列を構成する
    (例: C が damaged の間に A/B だけで ready=P2 成立 → C 復旧 (旧 P1 の embeddings のまま) →
    C は §9.3-c 未完で synced=NULL → ready は P2 のまま? 母数復帰で落ちる? — どちらの読みも
    文書から一意か)。synced 全 NULL 化 (破棄 Tx) × §9.3-c の再 UPDATE の競合、接続 0 件 → 1 件目
    復帰の遷移、agg_vec DELETE→INSERT × 差集合再充填 × wipe の 3 経路が同一 tick に重なる順序
X43 論理名 → raw 物理名解決の全数: resolver の 3 呼出点 (delete 最終確認 / restore in-place /
    fsck working copy) × (NFD 実体のみ / NFC 実体のみ / 両方存在 = collision / raw 無し) ×
    (case-insensitive / sensitive) の行列。特に: collision 時の採用規則と restore の書込先の一貫 /
    resolver の readdir 列挙と walk の観測の時差 (解決直後の rename) / APFS (正規化非依存 lookup) で
    resolver を使っても挙動が変わらないこと (プラットフォーム分岐が要らない設計か)
X44 scoped 規約 12 と step -1 の運用面: 登録済み path の read 照合 × 一時読取不能 (4 分類) ×
    standalone read の provenance 表示の分岐一意性 / conflict 中 (同一 id 2 箇所) の単独検索が
    どちらの実体でも拒否されるか / step -1 の z 判定 × 検出フォルダの step 0〜4 除外 × 同 tick の
    step 5 wipe の一貫 (除外中の submit 対象から漏れるだけで detached にはならないこと) /
    z 判定自体の読取失敗 (metadata 一時 EIO) の扱い / fork 手順 3 の root_path = 発見パス ×
    再発見除外 × §9.3-d 猶予の交錯
X45 反証探索 (r12 更新版の主張): 「client の中間 attempt の課金は台帳から漏れない」「照会失敗
    (unknown) で二重 job は作られない」「保持期限超の相 2b 残骸も課金は記帳される」「state=0 server の
    成果あり close は job を無記帳で破棄しない」「ready は damaged・空母数・synced 陳腐化に騙されない」
    「raw 解決で restore の二重実体は作られない」「登録済み path の read は差し替えを検出する」
    「step -1 で復元直後 tick の誤課金は起きない」を破る操作列を試みる
X46 r13 修正の相互作用 — 記帳済み判別述語 × 冪等記帳 × seq 連番 (r14 の本命): 述語キー
    (batch_job_id 値) の全数 — 同一 lifecycle で token 記帳 (期限超) と job id 記帳 ((b')・相 3
    成功・terminal 化) が混在する系列を構成し、各記帳の (seq, batch_job_id) が一意かつ述語が
    正しい行だけを省略するか / 期限超記帳 (token, seq=k+1) → 載せ直し → 相 3 (job id, seq=k+2)
    → collect 成功記帳 — ledger 3 行は正当な別 attempt として一貫するか / (b') 記帳 (job id) 後の
    sweep 再訪は述語 (job id 一致) で正しく省略されるか / client 再実行前記帳 (旧 seq NULL+estimated)
    と述語の関係 (client は batch_job_id = token — 述語は期限超/(b')/sweep 限定か、client にも
    適用すべきか読みが一意か) / 述語 SELECT → INSERT の間の並行性 (tick.lock 単一 writer で
    閉じているか、明示操作経由の記帳と衝突しないか)
X47 期限超同一 Tx × token rotation × detached: (i) 述語 → (ii) 記帳 → (iii) attempts+1 →
    (iv) 相 1 rotation の同一 Tx を各境界クラッシュで再実行し、旧 token 記帳行が新 token 世代の
    述語に干渉しないこと / attempts+1 (期限超) が §8-a の profile 数え直し (attempts=0 リセット)
    と同 Tx で交錯した場合の順序 / detached の期限超記帳 → 削除 → 同 repo 再登録 → seq 継承
    (MAX には token 記帳行も含まれる) の連番 / 期限超判定と tool_changed ガードの適用順
X48 restore 保全 × §20.5 × resolver: 保全コミット (現内容 ≠ LWW) → 上書き → 次 tick scan の
    3 段が tick.lock 下で一貫するか / 保全対象の安定確認が失敗 (書き込み中) した場合の restore の
    中止・続行 / 保全コミットと restore 内容が同一 hash の場合 (no-op で良いか) / raw 解決
    (書込先) と保全 (読取元) が別実体になる collision ケース / エクスポート (管理外) が保全対象外で
    あることの明確さ
X49 回復先行 × 全 §21 操作: register / unregister / fork / restore / watch_root / drop の各操作
    前の fork 回復実行をトレースし、回復後の状態を入力に操作が一意に進むか / 回復自体が進めない
    (journal digest 不一致 = damaged) 場合に後続操作は実行してよいか拒否か (文書から一意か) /
    回復先行と「fork 中の読取 = fork 進行中 status」の整合 / 二重 fork (回復完了後の新 fork) の
    単一 flag 遷移
X50 反証探索 (r13 更新版の主張) : 「無 id 記帳は NOT NULL と衝突しない (値規則で常に埋まる)」
    「記帳済み判別で推定行は増殖しない」「(b') が飛んでも sweep が記帳を回収する」「detached は
    期限超でも記帳してから消える」「未来時計 token で無記帳載せ直しは起きない」「§6/§7 の往復は
    全段可逆 (G/\G/\\G)」「restore は未取り込みの working 変更を消さない」「明示操作は未完 fork に
    反転されない」を破る操作列を試みる
X51 r14 修正の相互作用 — seq 行 UPDATE × 連番一貫 (r15 の本命): 無 id / 発見記帳 3 箇所 (期限超
    (ii)・(b')・sweep 前段) が batch_requests.submission_seq を +1 へ UPDATE するようになった —
    期限超 (ii) の行 UPDATE → (iv) 相 1 → 相 3 の +1 で同一 attempt が二重加算されないか /
    (b')/sweep の行 UPDATE と close 本体・後続 collect 記帳の連番が衝突・飛びなく一貫するか /
    detached 採用 (+1)・client 前計上 (+1)・found 採用 (+1)・無 id 記帳 UPDATE が同一行の寿命で
    交錯する系列の全数 / 述語 (batch_job_id 一致) と seq 行 UPDATE の実行順の読みが一意か /
    行削除 → 再作成の MAX 継承 (L01) に無 id 記帳行の seq が正しく含まれるか /
    DDL コメント「その時点の batch_requests.submission_seq」が全記帳経路で成立するか
X52 expired terminal × 遷移表 × sweep × 明示 retry: (iii') の state=3 (error='expired') が遷移表
    「state=3・attempts >= 上限 → 投入しない」へ正しく着地するか / expired 行の intent_token 残存
    (sweep が NULL 化するまで) と §21.2 削除条件 (intent_token IS NULL) の整合 — unregister が
    expired 行を誤削除せず detached 保持するか / 明示 retry (attempts リセット) 後の再投入 →
    相 1 rotation と旧 token 記帳行の述語独立性 / terminal 4 種 (expired / submit_rejected /
    client_exhausted / tool_changed) で error 値・attempts・token・upload の残し方が一貫するか
X53 4 照合点の期限判定対称性: intent 回復・detached (b)・(b')・token sweep 前段のそれぞれで
    (a) 三値判定 (b) 期限超判定 (c) 未来 skew (d) 伝播猶予 (e) 記帳済み判別述語 (f) seq 行 UPDATE
    (g) batch_job_id 値 (token / 発見 job id) (h) 後続動作 (載せ直し / 削除 / 掃除) の 8 要素を
    表にして全数比較し、1 要素でも欠ける・食い違う組合せを探す / 「4 照合点に共通適用」の宣言と
    各照合点の個別記述の矛盾 / 期限内 confirmed-absent ((b')/sweep = 記帳なしで掃除) が「相 2b
    完了済みかもしれない」ケースを取り逃がさない構造か (伝播猶予がその穴を塞ぐ根拠の検証)
X54 回復ゲート例外 × register journal チェック × flag 掃除: 破損 journal の明示解決 (ゲート例外) が
    有効 journal を誤破棄する経路はないか (一時読取不能 ≠ digest 不整合の区別が例外経路にも
    効いているか) / journal (有効/破損/無) × flag (有/無) × 実体 id (old/new/他/読取不能) の全組合せ
    が §21.1 手順 1・前文ゲート・flag 掃除 (new 限定)・damaged 復旧の 4 規範で一意の帰結を持つか /
    明示解決 (journal + flag 除去 → 新 id 再登録) の途中クラッシュからの再開 / fork stalled (30 日)
    の status と missing 猶予・damaged 表示の優先関係
X55 単独検索の 2 決定規則: :current_profile (embeddings 一意) × :current_tool (markdown_documents
    最新 generated_at) の組合せ — embedding 混在 (KNN 停止) 中に tool も混在した場合の FTS 挙動 /
    generated_at 同時刻 tie の決定性 (§5.3 の単調更新 max(now, 旧+1) は同一派生の置換内の規則 —
    異なる派生行の間で同時刻はあり得るか、あり得るなら tie-break は?) / markdown_documents が空
    (OCR 未完) での :current_tool の帰結 (KNN・FTS とも 0 件で良いか、status は?) / backfill OFF ×
    tool 切替で「最新 generated_at の tool」が旧 tool 派生しか持たない content を eligible から
    落とす挙動 (被覆非保証の宣言で足りるか) / 横断 (app_config 給源) と単独 (最新 generated_at) が
    同一フォルダで異なる tool を選ぶ場合の説明可能性
X56 §6/§7 エスケープ条件の非対称 (r14 見送り論点の再評価): §6 のエスケープ対象 (0 個以上の `\` +
    行頭 `![` + `](obj:` を含む grammar 形) が §7 の un-escape 認識形 (hash64 込みの行全体一致) の
    上位集合であることに起因する「エスケープされたが un-escape されない行」(例:
    `![diagram](obj:see appendix)` — hash64 不一致で §7 非認識) の `\` 残留を、FTS 検索・preview・
    往復可逆性・phantom 防止の 4 面から実害評価する — 条件を狭める修正 (行全体一致に限定) が
    phantom 防止の二層目を弱めるトレードオフとの比較で、r14 裁定 (現状維持が安全側) を覆す反例
    (実害のある操作列) を構成できるか (※r15 で decoder 拡張により解消済み — X60 が後継)
X57 r15 修正の相互作用 — batch_job_id 自己記述化 × dispatch/照会経路 (r16 の本命): found 記帳で
    行の batch_job_id へ発見 job id を書く自己記述化が、(a) intent 回復の dispatch (「batch_job_id
    非 NULL の state=0 = client 前計上」の判定 — 自己記述化は terminal 行のみで state=0 に効かない
    ことが文書から一意か)、(b) idx_batch_open (batch_job_id WHERE state=1)、(c) job_missing の
    時刻基準、(d) sweep の対象条件 (batch_job_id NULL) と衝突しないか / 自己記述化された state=2/3
    行の再投入 (成果なし・state=2 → 投入対象) → 相 1 の batch_job_id NULL 戻しとの整合 / 自己記述化
    小 Tx のクラッシュ位置ごとの再駆動 (記帳あり・batch_job_id 未書込の中間状態は述語が拾うか)
X58 detached terminal 化 × 遷移表 × 再登録: error='detached'/'expired' の terminal 行が再登録で
    attached に戻った時の遷移表 (state=3・attempts<上限 → 投入対象) との整合 — 意図されたコスト
    注記との一貫 / terminal 化後の 4.5 (掃除 → NULL 化) → 削除条件成立までの各クラッシュ再駆動 /
    error 値 6 種 (submit_rejected / client_exhausted / tool_changed / expired / detached / 通常
    失敗系) で attempts・token・upload の残し方が一貫するか
X59 submit_rejected 除外 × 課金される拒否: sweep 前段の submit_rejected 除外 (照合・記帳なし) が
    「拒否にも課金する provider」(P8 の前提注記) と組み合うと課金を取りこぼすか — 前提が成立しない
    provider での安全側の倒し方が文書から導けるか / client_exhausted (記帳済み) 行の token NULL 化
    経路の網羅 (sweep の掃除フェーズが照合なしで到達するか) / 除外判定が error 値だけで足りるか
    (submit_rejected 後の明示 retry → 再拒否 → 再 terminal の反復で error が別値に化けないか)
X60 decoder 拡張の往復全数: escape (0+ \ + パターン) × un-escape (1+ \ + パターン) × 認識 (行全体
    厳密一致 + 実在検証) の 3 述語で、手書き `\`+パターン行・非 canonical 行・偶然 grammar 形・
    hash64 妥当だが object 不在の行、の全組合せを往復させ (a) 可逆性 (b) phantom 防止 (c) text_hash
    安定の同時成立を検証 / 再 materialize の非再適用 (本文引き継ぎ) と grammar v 移行・test vector
    3 段の整合 / char span (エスケープ済み位置) と un-escape 後 text の対応
X61 伝播猶予の採用条件 × 実プロバイダ × 反証: 「可視化遅延上限 ≤ 猶予」の契約が Mistral Batch で
    成立するかの読みが一意か・猶予の provider 別設定と期限判定 (timeout_hours+保持期限+猶予 1 日)
    の交錯 / r15 更新版主張の反証 — 「(i)〜(iv) 1 Tx で偽 expired は起きない」「自己記述化で同一
    job の二重記帳は起きない」「detached は削除ガードとデッドロックしない」「submit_rejected の
    token は残留しない」「§6/§7 は全行で往復可逆」「一括変換後の :current_tool は決定論的」を破る
    操作列を試みる
X62 r16 修正の相互作用 — job_create_started_at が開ける穴 (r17 の本命): 単独小 Tx (相 2b 呼出直前)
    の実行点と失敗・クラッシュの全組合せ / requeue (iv) 後の残置値 × 新 token の max() が誤起点を
    拾う操作列は構成可能か / app.sqlite 全損・復元で列だけ NULL に戻った場合の「未作成断定可」の
    正当性 (実 job が存在する状態で NULL になる経路はあるか) / detached (b)・(b')・sweep 前段での
    同列の扱いの一貫性 / 「記録後・呼出前クラッシュ」の反復が期限判定・attempts とどう交錯するか
X63 error='cancelled' × 遷移表 × 再登録: cancelled terminal 行は attempts 据え置きで「成果なし・
    state=3・attempts < 上限」= 再登録後に自動再投入される — 意図されたコストか規範矛盾か (§21.2
    注記との整合) / cancelled の課金記帳の値規則 (batch_job_id・seq・estimated) は他 terminal と
    一貫か / cancel 確定 Tx と token sweep (前段・掃除・NULL 化) の交錯 / cancel 未確定→detached
    例外との境界は一意か
X64 found 判別 IN (発見 job id, 当該 intent_token) の過吸収: token キーの推定行が存在する状態で
    **別 attempt の実 job** (rotation 後の J2) の found 記帳が誤って省略される操作列は構成可能か /
    IN 判別 (sweep found) と (i) 記帳済み判別 (token 単独) の非対称は問題を残すか / 自己記述化
    (行の batch_job_id ← J) と IN 判別の循環・干渉
X65 no-replace rename の OS 意味論差: RENAME_NOREPLACE 非対応 FS (NFS 旧版・FAT/exFAT・SMB) での
    フォールバック規範は一意か / EEXIST と ENOTEMPTY の区別 / no-replace 失敗 → 再 lstat 経路の
    整合 / 「可能なプラットフォームでは」の判定方法は実装可能か (試行して EINVAL なら通常 rename +
    再 lstat のみ、のような決定規則があるか)
X66 規範↔要約・掲載 SQL・DDL コメントの非伝播 (横断): r16 回帰 3 件 (R08/R18/R20) の同型を全域で
    掃く — 規範文とその (a) 括弧内要約 (b) 掲載 SQL 例 (c) DDL コメント (d) §間パラフレーズの 4 種の
    再掲がすべて同じ制約を保持しているか。特に §9.1↔§21.2/§21.3 の detached・cancel・削除条件、
    §11.2 規範↔差替え SQL、§13 fsck↔DDL コメント、§7↔§9.1 の key 契約、§10↔§9.1 の有界主張の限定子
X67 rotation ガード (T08) が開ける穴 (r18 の本命): 「token 残存行の再投入は sweep 前段完了後」の
    実行点と Tx 境界は一意か / 前段が unknown (照会失敗) を返し続ける行の再投入保留は滞留として
    可視化されるか (retry_not_before との交錯・dirty 早回し tick の反復) / detached → 再登録直後の
    行への適用 / ガード完了と相 1 の間のクラッシュ再開
X68 cancel (attempts=上限) × 明示 retry の循環: 明示 retry (attempts リセット — §8-a) 後に再
    unregister → cancel で再び上限 — 循環は有界か・記帳は毎回正しく積まれるか / cancelled 行の
    削除条件到達 (sweep 完了・token NULL 化) 前の明示 retry と token / upload 残骸の交錯 /
    再登録 → retry → 再 cancel の操作列で二重課金・記録欠落が生じないか
X69 fts_cap × RRF 再現率: 中間上限 (fts_cap / KNN k) で途中打ち切りされた rank 集合の意味論 —
    cap 到達時の欠落は決定論的か (同一クエリの再現性)・FTS 側 cap と KNN 側 k の非対称が fused の
    順位・tie-break に与える影響 / cap と外側 :limit の関係の実装一意性 / cap 到達の可視化
X70 変換決定論 × コンバータ更新: コンバータ版更新 = tool_profile 変更 → target_key 変化で自然
    再判定される連鎖の確認 / 旧版コンバータが消えた環境での再変換不能 (原本照合は通るが upload 物を
    作れない) の扱い / 変換失敗と unsupported_format の分岐一意性 / 変換物 upload と原本 content_hash
    の対応 (T10) を破る操作列
X71 rotation ガード縮小 (U03) の反例 (r19 の本命): 「state=0 の載せ直し・client dispatch は自身の
    照合経路が旧 token を処理済みのため対象外」の前提を破る操作列 — 載せ直し (iv) の Tx 内で旧
    token の記帳が完了しないまま新 token が書かれる境界クラッシュ / client 前計上の再実行 dispatch が
    旧実行 id (= token) の記帳を経ずに attempts+1 だけで進む経路 / ガード対象 (state=3 再投入) と
    非対象 (state=0) の判定が state 遷移の途中で入れ替わる競合
X72 明示 abandon (U03) × 後日 job 出現: abandon の estimated 記帳 (batch_job_id = token) の後に
    provider 側で job が可視化された場合 — sweep found の IN (発見 job id, token) 判別は abandon
    記帳を「記帳済み」と正しく判定するか / abandon 済み行の削除条件到達と、その後の found の帰属 /
    abandon → 明示 retry → 新 token の三重奏で記帳が二重計上・欠落しないか
X73 convert_failed (U09) × tool_profile 変更: コンバータ更新 = tool_profile 変更で target_key が
    変わり旧 terminal 行が残置される — 旧 (content, 旧 tool) の convert_failed 行の削除条件・課金
    なし terminal の掃除 / 新 target_key の初回投入と旧行の attempts の独立性 / 「1 回だけ terminal
    行を作る」の冪等性が tool 変更を跨いで正しく機能するか
X74 有界スキップ (U07) × 一時 EIO: 構文検証失敗のカウント (3 回/24h) と安定確認失敗 (一時 EIO・
    AV ロック) のカウントは分離されているか — EIO 混在で「安定した破損」と誤認して bytes コミット
    しないか / カウントの起点と (size, mtime_ns, inode) 変化時のリセット / スキップ有界化と
    fp_cache 非確定 (racy) の相互作用
X75 scope_id (V08) が開ける穴 (r20 の本命): 相 2b 直前の小 Tx が job_create_started_at と scope_id の
    2 値を書く — 記録成功・呼出前クラッシュ後の相 2b 再試行で scope が変わっていた場合の上書き
    意味論 / provider に workspace 概念が無い場合の canonical 化 (何を書くか — 空文字と NULL の
    区別) / scope_id NULL × job_create_started_at 非 NULL の「常に unknown」が abandon 以外で
    脱出できない滞留にならないか / scope 変更を跨ぐ found 採用・sweep・detached (b) の全照合点で
    比較が一貫するか
X76 abandoned (V10) × 遷移表・削除条件・再登録: error='abandoned' (attempts=上限) は遷移表の
    自動再投入から正しく外れるか・明示 retry (attempts リセット) 後の挙動 / 削除条件 (全行終端 +
    upload 清掃 + token NULL) への到達 — abandon は token を NULL 化するので削除が近い: upload
    残骸が残る場合の順序 / 再登録 (detached → attached) を跨いだ abandon 行の扱い / abandon 記帳
    (token キー) と後日 found (job キー) の IN 判別の全照合点一貫性
X77 fp スキップ例外 (V11) の検査コスト × 大規模ツリー: 「登録フォルダはスキップ前に fork-journal の
    存在を検査」— 登録フォルダの特定は folders 照会か marker 検査か (fp スキップの利得 (DB 照会
    ゼロ) と矛盾しないか) / 10 万フォルダ級での per-tick lstat コスト / journal 検査自体の一時
    読取失敗の扱い (スキップして良いか) / 非登録フォルダ (marker なし) への適用要否
X78 ガード拡張 (V07) × floor 明示再生成の順序: floor 設定 (app 1 Tx) とガードの sweep 前段の実行
    順序は一意か — floor 設定後・ガード完了前の tick 中断で floor が残ったまま再投入されない状態は
    滞留として可視化されるか / state=2 token 残存行への floor 設定 → 相 1 → 照合の全順列で記帳が
    欠落・重複しないか / ガードが要求する「照合・記帳・NULL 化」と sweep 本体の分担の境界
```
- **C9. 修正・追記の検証**: 下記の「r1」(A01〜A24)、「r2」(B01〜B18)、「§20 追記」(D01〜D14)、
  「r3」(E01〜E06)、「r4」(F01〜F27)、「r5」(G01〜G02)、「r6」(H01〜H30)、「r7」(I01〜I38)、
  「r8」(J01〜J20)、「r9」(K01〜K26)、「r10」(L01〜L28)、「r11」(M01〜M29)、「r12」(N01〜N45)、
  「r13」(O01〜O30)、「r14」(Q01〜Q37 — **P は原則番号のため欠番**)、「r15」(R01〜R29)、
  「r16」(S01〜S29)、「r17」(T01〜T18)、「r18」(U01〜U24)、「r19 修正検証リスト」(V01〜V20) の
  全項目について、文書の現状を fixed / partially-fixed / not-fixed / regression / **superseded** の
  5 値で判定する
  (D は「追記が期待状態で入っているか」の判定に読み替える)。partially-fixed は
  「主要箇所は直っているが同じ問題の残存箇所がある」場合 (残存箇所を引用する)。
  **superseded 対応表** — 次の旧項目は後続修正が期待状態を置き換えた。判定は対応する新項目で
  行い、旧項目は「superseded (→##)」と記して不合格事由に数えない:
  (r7 が置換) F05→I14 / F07→I15 / F12→I16・I17 / F21→I03・I04 / H04→I31 / H15→I08・I11 /
  H18→I16 / H22→I15、A11 の遷移詳細→I05・I06・I13・I14、H02 の衝突順→I32。
  (r8 が置換) **I03/I04 の cost 記述→J06 (cost_usd NULL 許容 + estimated + UNIQUE)、
  I05/I06 の 2 相 submit→J01・J02 (相 1 の profile_hash・upload_cleaned)、I09 の 404 未定義→J03、
  I11 の result_expired→J03 と同系、I15 の floor→J04 (再チャンク干渉)、I16/I17 の profile 宣言的→
  J05 (agg 側の毎 tick 検査化) と J01 (相 1 profile_hash)、I35 の fork→J13〜J16 (耐久手続き)、
  H26/I01 の lower(hex)→維持 (J で不変)**。
  (r9 が置換) **J04→K01 / J06 の UNIQUE(…,attempt)→K02 / J03→K10 / J10→K09 / J13→K16 /
  J16→K13〜K15 / I12→K04 / D08→K20 / A01→K25**。
  (r10 が置換) **K02 の UNIQUE 叙事文残存→L01 (submission_seq 継承で fatal を根治)、K12〜K13 の
  detached「state=0 = 課金なし」→L04 (照合必須化)、K06 の submit_rejected→L02 (attempts=上限を
  同 Tx)、K09 の client 写像→L03 (client_exhausted 出口)、K14 の fork→L07 (phase 状態機械)、
  J07 の app_config 単一 agg key / K24 の §11.2 agg 照合→L09 (building/ready 2 key)、K11 の
  「失効窓は記録できない」残余→reconcile close の
  記帳義務化で解消、K21 の fsck repair→L20 (1 ストリーム + 破損置換 + kind 別)、K19 の猶予→L13
  (missing_since 列)**。
  (r11 が置換) **L09 の app_config 2-key コメント未反映→M03 (DDL コメント 6-key 化)、L28 の
  app_config key / fsck agg 未反映→M03 (key) + M09 (fsck agg 対象化)、L20 の §13「§5.3 明示再生成」
  誤誘導残存→M04 (kind 別化)、L04 / L21 の §21.2「state=0 は即削除」→M02 (§9.1 の client/server 分岐へ
  委譲)**。
  (r12 が置換・拡張) **M09 の母数定義 (missing/fork のみ除外)→N05 (damaged・一時読取不能も除外 +
  0 件非更新 + synced NULL 化 = N06)、M10 の §10 側次元のみ照合→N10、M12 の「record とその hash」→
  N38 (record のみ)、M29 の掃除失敗再駆動→N15 (token sweep + 共有 guard)、M06/K08 の採用列挙→N17
  (submitted_at 明示)、L07/M05 の flag 保存先未定義→N16 (app_config key)、L26 (submit 側のみ) →
  N14 が相 2a を追加、M01 の DDL コメント残存→N09、M08 の「素朴 stat 禁止」→N28 (raw 解決の対象
  指定 + 絶対主張の軟化)、M13 の register 4 分類→N30 (全 open へ一般化)**。
  (r13 が置換・拡張) **N03 の期限超記帳→O05/O06 (同一 Tx・attempts+1・述語・未来 skew — N03 の
  UUIDv7 と期限判定自体は維持)、N04 の (b')→O02/O03 (述語 + unknown 保持)、N13→O21 (batch_job_id
  NULL 戻し)、N15 の sweep→O04 (前段義務化)・O25 (§10 列挙)、N36→O16 (三値化)、N39→O14
  (preflight 追加)、N40→O28 (§8 冒頭側)、N28→O13 (軟化の 3 呼出点一般化 — raw 解決対象の指定は
  維持)、N07→O12 (fork_in_progress 除外の追補)、§21.5 の「M&S が掃除」→O29**。
  (r14 が置換・拡張) **O28→Q01 (§5.7 末尾・§8-c の残存 2 箇所を含む全参照点の統一 — §8 冒頭・
  §10 step 3 の期待状態は維持)、O17→Q02 (step -1 の除外リストと z 注記の整合 — collect 実行可の
  注記自体は維持)、O02/O03 の (b') 述語・unknown 保持→Q05/Q07 が seq 行 UPDATE と期限判定を追加
  (述語・保持の期待状態は維持)、O04 の sweep 前段→Q06 (found / 期限超の分岐へ拡張)、O05 の期限超
  同一 Tx→Q04 ((iii') expired 出口と (iv) upload 掃除を追加 — 同一 Tx・述語・attempts+1 は維持)、
  O07 の detached 期限判定→Q09 (削除条件に intent_token 追加 — 期限判定自体は維持)、O09 の restore
  保全→Q11/Q12 (安定確認失敗の中止・再 lstat 義務化 — 保全自体は維持)、O11 の回復先行→Q13/Q36
  (破損 journal 例外の明文化 — 先行自体は維持)、O18 の flag 掃除 id 一致→Q23 (new 限定へ強化)、
  O19 の自動 rebind→Q24 (fork 前 rebind 先行を追加)、O13 の resolver 軟化→Q12 (restore の再 lstat を
  義務へ — delete 確認 / fsck の任意・3 呼出点の許容は維持)、O30 の mapping bind 給源→Q37
  (:current_tool 行を追加)**。
  (r15 が置換・拡張) **Q02→R01 (§9.3-z 側の鏡写し — §10 側の期待は維持)、Q04→R02 ((i)〜(iv) 1 Tx —
  述語・attempts+1・(iii') は維持)、Q09→R03 (パラフレーズ完全化 — ガード 3 条件自体は Q09 維持)、
  Q12→R04 (§20.5 側の義務整合 — §21.4 側の期待は維持)、Q03→R05 (過去側定義 + 採用条件 — 共通適用
  宣言は維持)、Q05/Q06 の found 記帳→R06 (自己記述化を追加 — seq 行 UPDATE・述語・期限分岐は維持)、
  Q06 の sweep 前段→R07 (submit_rejected 除外を追加。**Q06 は found 分岐 = R06 / 前段除外 = R07 の
  2 項へ分割 superseded — 重複記載ではない**)、Q10 の :current_tool→R14 (tie-break + 近似
  注記を追加 — 最新 generated_at 規則は維持)、Q13/Q14 の journal 破損→R15/R16 (三値化 + 解決順序 —
  ゲート例外・register チェック自体は維持)**。
  矛盾時の優先は R > Q > O > N > M > L > K > J > I > H > G > F > E > D > B > A (P は欠番)
- **C10. 修正が開けた穴**: r1 修正どうし・修正と既存記述の**新たな**矛盾を重点検査する。
  修正が入った §4.1 / §5.3 / §5.6 / §6 / §7 / §8 / §9.1 / §9.3 / §10 / §11 / §14 / §15 / §17 の
  周辺と、そこから張られる相互参照を優先的に読む。特に確認すべき相互作用:
  (a) DELETE → INSERT 統一 (A13) と規約 4 の唯一の例外 (generated_at 単調更新 §7) の整合
  (b) §9.1 状態遷移表 (A11) と §10 の submit / collect 記述 (A09/A10/A12) の完全一致
      (遷移表と tick 本文で判定条件・遷移先が食い違っていないか)
  (c) canonical block grammar (A04) と §7 の除去・取り込み規則の整合
      (grammar の全要素が §7 で漏れなく扱われるか。annotation 無効時 = 参照行のみの場合の扱い)
  (d) opt-in 画像フィルタ (A07) と §10 Embed submit の除外記述 (A10) の整合、
      およびフィルタ ON/OFF 切替時の挙動が未定義でないか
  (e) §11.1 の完全 CTE (A19) の列と §11.2 eligible / 最終 SELECT (A20) の列・join キーの一致、
      フォルダ単独版 (repository_id なし) への読み替え注記の整合
  (f) 逆差集合 (A16) / 孤児掃除 (A17) / GC (§13) の削除経路が重複も漏れもなく分担されているか
  (g) **§20 スキャンと §10 tick の接続**: スキャンは tick の一部か独立プロセスか、層 A の
      dirty 集合は誰が生成し誰が消費するか、tick.lock (単一実行) とスキャンの並行関係が
      定義されているか — 未定義なら指摘する
  (h) **§20.5 と既存規範の整合**: §4.1 (JCS commit_hash)・§5.1-5.2 (commits / file_versions の
      DDL と INSERT OR IGNORE)・規約 6 (書き込み順序 objects → metadata → app) と §20.5 の
      手順が食い違わないか。scan_cache (repository_id キー = 管理フォルダの直下ファイル) と
      fp_cache (path キー = 監視ツリー全体) の分担が §20.3 の記述と一致するか
  (i) **NFC 論理名 (H02) と fp_cache の非正規化 name (§20.3)**: raw 名の層 (fp) と論理名の層
      (scan_cache / file_versions / delete 判定) の変換点が一意に定義されているか
  (j) **FTS view 化 (H24) と trigger**: trigger は chunks 表に張られ view を経由しない —
      'delete' コマンド・rebuild・integrity-check の 3 操作すべてが view content と
      整合するか
  (k) **単調 created_at (H01)**: 単調性はフォルダごと — LWW・§9.3-a カーソル・§11.1 の
      行値比較・§4.1 の「同一の正規化コミット → 同一 hash」との相互作用に矛盾が無いか
  (l) **preflight (H14) と backfill (§10) / GC (§13)**: OCR 非対象ファイルの content_hash は
      submit 対象から外れるが、file_versions と GC 参照集合には正しく残るか
  (m) **cost_ledger 分離 (I03) と削除規範の両立**: ledger 不削除 (§9.1) と §8 / §9.3-d /
      §21.2 の削除処理が矛盾なく共存するか、attempt 値と ledger 行の一意性
  (n) **floor 方式の明示再生成 (I15) と各経路の一貫**: floor 設定後の submit / reconcile /
      backfill / collect で旧 md 行が「成果なし」として一貫して扱われるか、collect の
      floor NULL 戻しと generated_at 単調規則・§9.3-b 伝播の整合
  (o) **2 相 submit (I05/I06) の遷移表・tick 本文・DDL の三点一致**: state=0 の扱い・
      batch_job_id nullable CHECK・intent 回復の記述が §9.1 と §10 で食い違わないか
  (p) **reconcile 縮小 (I14)**: 「成果あり state=1」のすべての発生経路が collect 側で
      確実に閉じるか (閉じ漏れが残る状況の有無)
  (q) **upload 後始末 (I08)**: 「全行終端 + 未清掃」条件・相 1 の旧 upload 掃除・filename への
      token 埋め込みが §6 / §9.1 / §10 4.5 で整合するか
  (r) **profiles 表 (I20)**: 挿入点 (§10 2-c / 4) の網羅、8 テーブル言及の全箇所一致、
      検証規範 (SHA-256(record_json) = profile_hash) の配置
  (s) **pending_deletes (I27) と walk 完全性 (H03)・fp 確定禁止 (I28)・§9.3-d 掃除の整合**
  (t) **型不一致 = absent (I31) と skipped 存在扱い (F17/F24) の境界**: 一時 vs 恒久の判定基準が
      実装者に一意か
  (u) **§21 (I35) と §20.4 の参照整合**: fork / damaged / missing / 再登録の各記述が §21 の
      手順と矛盾しないか
  (v) **submission_seq (K02) の書込点の網羅**: 相 3 / intent 採用 / client 前計上の 3 点で
      +1 が重複・欠落しないか、ledger UNIQUE との整合、冪等再実行時の挙動
  (w) **profile_record snapshot (K03) の一貫**: 相 1 の書込・相 3 / 採用の不変・§10 collect の
      §5.7 INSERT・app_config 未設定時・detached 経由、の全経路
  (x) **detached 3 経路 (K12〜K15) の規則一致**: §21.2 / §9.3-d / §21.3 が同一規範を参照し、
      再登録による detached 解除 (folders 復帰) と PK 共有が衝突しないか
  (y) **保存名固定 (K17) の整合**: §11.1 PARTITION・複合 FK・restore 宛先・name_collision・
      §4.1 NFC との相互作用
  (z) **fork journal (K14/K15) の整合**: bootstrap 順序・規約 12 抑止・tick 除外・§9.3-d 猶予との
      相互作用、journal 残骸・破損の扱い
  (aa) **seq 継承 (L01) × 記帳経路**: MAX 継承の全書込点・二重加算の不在・close 経路 (通常 /
      reconcile / detached) の記帳が submission_seq で一意に保たれるか
  (bb) **reconcile close の付随処理 (L03) × collect close**: 二重記帳・floor 誤適用・kind 別分岐
  (cc) **fork phase 機械 (L07/L08) × 全クラッシュ位置**: 再開の一意性・folders DELETE・
      削除順・id=old 分岐・除外粒度
  (dd) **detached 照合 (L04/L21) × 3 生成経路**: client/server 分岐・upload 未清掃の削除禁止・
      state=1 採用と再登録の PK 共有
  (ee) **冪等記帳 (M01) × seq 継承 (L01) × detached 採用 seq+1 (M06)**: 全 close 経路 (通常 /
      reconcile / terminal / client_exhausted / detached) の記帳が submission_seq で一意か、
      ON CONFLICT DO NOTHING が正当な別 attempt (detached 採用等) の記帳を落とさないか、seq 書込点
      (相 3 / intent 採用 / client 前計上 / detached 採用) の網羅、reconcile close (c) の Tx 外 token 掃除
  (ff) **ready 完了追跡 (M09) × agg_vec 差集合 × fsck agg**: synced_profile_hash の更新点 (§9.3-c) と
      §8-e の ready 判定、missing / fork 除外の母数、被覆条件なしで空 index を通さないこと、差集合
      再充填と fsck 検査の分担、profile 再変更時の synced_profile_hash 陳腐化
  (gg) **fork 回復拡張 (M05/M19) × §20.4 再発見 × §9.3-d 猶予**: flag 掃除の実体現存要件・fork id
      除外・commits 非空 restart・journal digest が中断中フォルダ移動・app 全損で一意に収束するか
  (hh) **register/検知周辺 (M02/M08/M11/M13/M28)**: 一時読取不能保留・同 root_path 退役・delete
      最終型判定・root dirfd 束縛・§21.2 の §9.1 委譲が相互に矛盾しないか
  (ii) **三値照合 (N02) × UUIDv7 期限 (N03) × 載せ直し**: unknown 保持と期限判定の適用順、期限超
      記帳 (seq+1) → 載せ直し → 相 3 (+1) の連番、retry_not_before との交錯
  (jj) **(b') 記帳 (N04) × (c) 掃除 Tx 外 (N15) × token sweep**: 実行順 (照合 → 記帳 → 掃除)・
      共有 token 全行終端 guard・sweep の intent_token NULL 化が close 済み行と衝突しないか
  (kk) **client 再実行前記帳 (N01) × client_exhausted × 恒久 4xx (N13)**: 旧 seq 記帳の重複が
      冪等吸収で正しいか、submit_rejected (記帳なし) と「実行された可能性」の境界
  (ll) **ready 母数 (N05) × synced NULL (N06) × §9.3-c**: 母数の tick ごと変動と全一致判定・
      0 件非更新・除外フォルダ復帰の整合
  (mm) **raw 解決 (N08) × case 再判定 (N44) × name_collision**: resolver の採用規則と walk の
      採用規則の一貫、restore / delete 確認 / fsck の 3 呼出点の同一性
  (nn) **scoped 規約 12 (N07) × 4 分類 (N30) × standalone 表示**: read 経路の分岐一意性、
      conflict 中の単独検索の扱い
  (oo) **step -1 (N36) × step 0〜4 除外 × step 5 wipe**: 除外の粒度 (フォルダ単位) と detached・
      submit 対象からの漏れ方の一貫
  (pp) **記帳済み判別述語 (O02) × 冪等記帳 (ON CONFLICT) × seq 連番**: 述語キー (batch_job_id 値) の
      網羅 — 同一 lifecycle で token 記帳 (期限超) と job id 記帳 ((b')/相 3) が混在した場合の
      判別、述語 SELECT と記帳 INSERT の原子性 (tick.lock 単一 writer 前提の明示)、期限超記帳
      (token) → 載せ直し → 相 3 成功 (job id) の ledger 2 行が正当な別 attempt として一貫するか
  (qq) **期限超同一 Tx (O05) × token rotation × attempts**: (i)〜(iv) の Tx 境界、rotation 後の
      旧 token 記帳行と新 token 述語の独立性、attempts+1 (期限超) × §8-a profile 数え直しの交錯
  (rr) **restore 保全 (O09) × §20.5 手順 × tick.lock**: 保全コミットと restore 本体の順序・
      保全対象が restore 内容と同一の場合の無害性・エクスポート対象外の明確さ
  (ss) **回復先行 (O11) × 全 §21 操作 × 回復不能**: 回復自体が damaged (journal digest 不一致) の
      場合に後続操作は進めるか拒否か、回復先行 × 新 fork 起動の単一 flag
  (tt) **flag 掃除 id 一致 (O18) × 自動 rebind (O19) × 再発見除外**: 旧パス再利用・移動・回復の
      三つ巴で flag / journal / folders の収束が一意か
  (uu) **seq 行 UPDATE (Q04/Q05/Q06) × 相 3 / found 採用 / detached 採用 / client 前計上**: 同一行の
      submission_seq を進める全経路の交錯 — 二重加算・連番飛び・MAX 継承 (L01) との整合、DDL
      コメント「その時点の batch_requests.submission_seq」が全記帳経路で成立するか
  (vv) **expired 出口 (Q04) × 遷移表 × 明示 retry × token sweep**: terminal 4 種 (expired /
      submit_rejected / client_exhausted / tool_changed) の error・attempts・token・upload の
      残し方の一貫、expired 行の token 残存と削除ガード (Q09) の整合
  (ww) **伝播猶予 (Q03) × 期限超判定 × 未来 skew**: 3 つの時刻窓 (now−10 分 / 期限 / now+5 分) の
      境界と重なり — 「期限超かつ伝播猶予内」等の組合せの帰結が定義されるか、10 分猶予が期限内
      載せ直しの正当な回復を過剰に遅らせないか
  (xx) **回復ゲート例外 (Q13/Q36) × §21.1 journal チェック (Q14) × flag 掃除 new 限定 (Q23)**:
      journal (有効/破損/無) × flag (有/無) × 実体 id (old/new/他/読取不能) の全組合せの帰結一意性、
      例外経路が有効 fork を誤破棄しない防御 (一時読取不能 ≠ digest 不整合)
  (yy) **fsck の agg 親子検査 (Q21) × §9.3-b 全置換 × ready 母数 (P8-e)**: fsck 駆動の synced NULL
      化・親行 DELETE が ready を正しく降ろすか (降ろさないと修復中の空 index が ready を騙る)、
      次 Replicate の全置換との再収束
  (zz) **自己記述化 (R06) × dispatch (batch_job_id 非 NULL = client 判定) × idx_batch_open ×
      sweep 対象条件**: terminal 行への batch_job_id 書込が state=0 の client 判定・state=1 の
      照会・「batch_job_id NULL の行を照合」の各条件と衝突しないか、中間クラッシュの再駆動一意性
  (aaa) **detached terminal 化 (R08) × 遷移表 × 再登録復帰 × 意図されたコスト注記**: error='detached'
      /'expired' 行の attached 復帰後の再投入・attempts・token の一貫
  (bbb) **(i)〜(iv) 1 Tx (R02) × 記帳済み判別述語 × 明示 retry × sweep 引継ぎ**: Tx 境界の変更が
      述語の前提 (「完走しなかった再試行」) と expired 出口・retry 経路に開ける穴
  (ccc) **decoder 対称化 (R11) × §7 厳密認識 × test vector × 再 materialize 非再適用 (R12)**:
      escape/un-escape/認識の 3 述語の整合と `\` 累積の完全排除

### r1 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
A01: §15 規約 9 の真実が「.folder-history/ 全体 (metadata.sqlite + objects/ + repository-id)」
A02: §4 表で content_hash / commit_hash に SHA-256 が明記
A03: embedding_vec / agg_vec の DDL が float[<dim>] テンプレートで、768 は参考値と明記
A04: §6 に canonical block grammar (参照行単独行 / <!-- annot: block / field 3 つ順序固定 /
     値の 1 行正規化 / --> エスケープ / LF) があり、§7 が同 grammar を参照
A05: §7 の再チャンクで markdown_documents.generated_at の同一 Tx 単調更新が必須とされている
A06: image チャンクへ (target_type=1, text_hash) の embeddings 行を足すオプションが削除され、
     行キーは常に (chunks.chunk_type, chunks.embed_hash) で、それ以外は禁止と明記
A07: 画像フィルタが既定 OFF の opt-in で、既定は全 type=2 chunk を embed
A08: 「Batch」の確定範囲が OCR (Mistral Batch API) に限定され、embedding は非同期ジョブの意と明記
A09: §10 OCR submit が (content_hash, current_tool_profile_hash) ペアの NOT EXISTS
A10: §10 Embed submit が (chunk_type, embed_hash) と (target_type, target_hash) のペア比較
A11: §9.1 に状態遷移表 (INSERT は初回のみ / 以降 UPDATE / terminal failed と明示リセット /
     成果なし state=2 の再投入 / collect 遷移) がある
A12: collect 冒頭の冪等スキップ (フォルダ成果既存 → metadata 処理をスキップして app 行を閉じる)
     が §9.1 と §10 の両方にある
A13: markdown_documents の置き換えが同一 Tx の DELETE → INSERT に統一され、UPSERT 禁止と
     「親行 UPDATE では CASCADE 不発火」の理由が §5.3 / §10 / 規約 4 にある
A14: §10 に tick.lock (flock) によるプロセス単一実行の並行性規約があり、§14 の busy_timeout の
     コメントが「tick の直列化ではない」趣旨に直っている
A15: §9.3-b に agg_markdown_documents の同 Tx UPSERT がある
A16: §9.3-b に逆差集合 (フォルダ側に無い派生キーの agg 削除) があり、§13 の集約掃除参照が
     §9.3-b / §9.3-d を指す
A17: §9.3-d の一括 DELETE が repository-scoped 4 表に限定され、agg_embeddings / agg_vec は
     逆参照の孤児掃除
A18: §9.3-a に commits JOIN file_versions によるカーソル適用 SQL がある
A19: §11.1 に 3 モードの完全 CTE ((repository_id, file_name, content_hash) を返す) があり、
     §11.2 が current_files を WITH で参照
A20: §11.2 が eligible (版 + 現行 tool) を rank 計算より先に定義し、vec0 の over-fetch / refill
     規則 (k_fetch 初期値、倍化再クエリ) がある
A21: 新規表の hash CHECK が typeof='blob' + length=32、embeddings に length(vector)=4*dimensions
     と dimensions>0 の CHECK、§15 に規約 10 (commits / file_versions の書込境界検証) がある
A22: §4.1 に Commit Hash の正規化直列化規約 (入力と固定項目リスト) が収録され、
     「元設計」への言及が参照解決を要しない形 (冒頭注記 + 内容併記) になっている
A23: §17 の実装参照パスが crates/kcs-index/src/fts.rs / crates/kcs-index/src/chunking.rs
A24: §17 の job / 課金の移植元参照が docs/04-pipeline.md §5.1 / §5.4 と docs/10-operations.md §3
```

### r2 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
B01: §5.4 の image チャンク text の説明が「description + transcription のみ。文書由来
     キャプションは本文 (text チャンク) に残る」で、§7 規則 3 と矛盾しない
B02: §6 の課金単位と §16 の「$0」条件が、いずれも「同一 (content_hash, tool_profile_hash)」
B03: §9.3-c が「agg に無い行のコピー + 同一キーで embedding_profile_hash 不一致行の置換
     (agg_vec も DELETE → INSERT)」を含み、§8 に profile 変更時の agg 破棄・再レプリケーションがある
B04: 画像フィルタの実装が「image チャンクを生成しない」(§7 規則 6 / §8) で、設定変更は
     再チャンク経路、切替前 job の残骸は孤児掃除で回収、と明記されている
B05: image_type を含む画像メタの供給源が img block (保存済み Markdown 内) に一意化されている
B06: annotation OFF 時の alt = source_id という固定規則が §6 にある
B07: img block に page / bbox / source_id の meta 行が annotation の有無に関わらず常時出力され、
     image_meta が Markdown から再構築可能 (sidecar への言及が残っていないこと)
B08: §9.3-a が「:cursor_at IS NULL OR (行値比較)」を含む agg_commits / agg_file_versions への
     完全な INSERT ... SELECT 2 本として掲載されている
B09: §9.3-d のフォルダ削除の一括 DELETE に sync_state が含まれる
B10: §9.3-d と §13 の embeddings 孤児判定が (chunk_type, embed_hash) = (target_type, target_hash)
     のペア一致 (hash 単独比較の記述が残っていないこと)
B11: §11.1 の 3 モードがすべて公開名 selected_files を返す実行可能な完全 SQL で、§11.2 は
     それを WITH 節として前置する (SQL 中に literal placeholder が残っていないこと)
B12: §11.2 の eligible が selected_files への EXISTS で定義されている (JOIN ではない)
B13: §11.2 の最終 SELECT が chunk 単位 1 行で解決キー (repository_id / content_hash /
     tool_profile_hash / chunk_uid / char_start / char_end) を含み、file join を含まない。
     §12 に「created_at は commits 側 — file_versions JOIN commits」が明記されている
B14: §11.1 にフォルダ単独版への機械的 mapping 表 (agg_* → ローカル表名、chunk_uid → chunk_id) がある
B15: chunks.content_hash / tool_profile_hash、agg_* の全 hash 列と repository_id、
     sync_state.last_commit_hash に typeof + length の CHECK があり、agg_embeddings が
     省略コメントなしの実 DDL として掲載されている
B16: §4.1 が JCS (RFC 8785) / "v":1 / created_at ミリ秒 / フィールド省略 (null 不使用) /
     hex64 文字列 / file_name 昇順 / test vector 作成義務、として確定している
B17: §5.3 に「generated_at はすべての置き換え経路で max(now, 旧値+1) の単調増加」規則がある
B18: §10 の bind 名が :current_tool に統一されている (:current_tool_profile_hash が残っていないこと)
```

### §20 追記検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
D01: §20.1 に 3 層構成 (層 A = dirty マーキングのみ / 層 B = 正しさの基盤 / 層 C = tick 不変) と
     「イベントゼロでも全機能が成立し、非稼働中の変更は起動時スキャンが吸収」がある
D02: §20.2 に OS 監視 API の特性表 (FSEvents / ReadDirectoryChangesW / USN Journal / inotify —
     粒度・非稼働中・弱点) と、notify + debouncer 推奨、「全 API にイベント欠落の正規条件がある」
     旨がある
D03: §20.3 の段 0 が 2 成分 fingerprint — files_fp / dirs_fp / dir_fp、入力は stat メタデータのみ
     (内容を読まない)、JCS + name 昇順 — で、比較結果の分岐 (dir_fp 一致 = 丸ごとスキップ /
     files_fp 不一致 = 直下ファイルへ / dirs_fp 不一致 = 不一致の子のみ再帰) が定義されている
D04: 物理制約の明記 — walk (stat) は毎回必要であり、ディレクトリ mtime は直下エントリの
     作成・削除・rename でのみ更新され内容上書き・孫の変更では変わらない、fp が省くのは
     walk 後の特定と後続処理のみ
D05: 段 1 に racy 規則 (mtime がスキャン時刻と同一秒内ならキャッシュ不信頼で段 2 へ) がある
D06: deep-scan (低頻度・fp_cache / scan_cache を無視した全 content_hash 再計算) が補正として
     規定され、mtime 保存コピー・FAT 解像度・racy の見逃しを有界時間で補正すると書かれている
D07: 実装順序 (段 1 = scan_cache を先に完成、段 0 = fp は規模が問題になってから、層 A は最後。
     どの段階でも正しさは不変) が明記されている
D08: §20.4 — 検知層だけがツリーを見て管理単位 (フォルダ直下のみ) は不変、管理外の変更は無視、
     新規管理フォルダの自動登録なし (明示操作のみ)、repository-id による再発見、
     消失時は猶予期間を置いてから §9.3-d へ
D09: ignore 規則 (~$* / .tmp / .crdownload / 隠しファイル / .folder-history 自身) と、
     クラウドプレースホルダ (Windows 属性 / macOS dataless) の既定スキップ + status 表示がある
D10: §20.5 に元設計 §15 のコミット作成処理 (安定確認 2 回 stat / 変更判定 = LWW の content_hash
     比較 / §4.1 参照の Commit Hash / tmp → fsync → rename / BEGIN IMMEDIATE + INSERT OR IGNORE /
     scan_cache 更新) が収録され、§20 から本書 §15 (設計規約) への誤参照が無い
D11: watch_roots / scan_cache / fp_cache の DDL が §9.1 にあり、規約 10 準拠の CHECK
     (repository_id は blob 16、hash は blob 32、scan_cache.inode は nullable) と、
     app.sqlite 配置の理由 (stat はデバイス固有) が書かれている
D12: §2 の層 2 構成図に watch_roots / scan_cache / fp_cache が含まれる
D13: §15 に規約 11 (検知の根拠は常に content_hash、イベントからコミットを構成しない、
     fp_cache / scan_cache はヒントで喪失時は全再計算、deep-scan が補正) がある
D14: 集約容量 (フォルダ合計サイズ) による検知の不採用と理由 (FS が集約値を保持しない =
     取得は全 stat walk、同サイズ変更・相殺・rename を見逃す) が §20.1 にある
```

### r3 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
E01: §16 のコスト表が「同一 (content_hash, tool_profile_hash) につき 1 回きり」であり、
     「content_hash 単位で 1 回きり」という表記が残っていない。$0 の行も「同一内容・同一 tool」
E02: §10 tick にステップ 0 (Scan & Commit = §20.3 / §20.5 の実行と「現在版」の鮮度保証) があり、
     並行性規約に「スキャン・コミット作成も tick.lock の下 (独立プロセス禁止)」
     「層 A の dirty 集合はプロセス内メモリで非永続 (喪失は起動時フルスキャンが吸収)」
     「dirty 起因の tick 早回し可」がある。§20.3 冒頭にも tick ステップ 0 である旨がある
E03: §11.2 fts_hits が agg_chunk_fts にエイリアスを付けず、MATCH / bm25() / rowid を
     表名で参照している (エイリアスを付けつつ表名参照する形が残っていない)
E04: racy 規則の基準が scan_cache.verified_at (その行の content_hash を検証した時刻) で、
     §9.1 の verified_at コメント・§20.3 の規則・§20.5 手順 6 (verified_at = now で UPSERT)
     の 3 箇所が一貫している
E05: §20.5 手順 6 に「delete を記録したファイルの scan_cache 行は DELETE する」がある
E06: §11.2 の refill 上限 k_max に既定値 4,096 があり、上限到達時は不足のまま返すと明記
```

### r4 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。番号は r4 監査の E## に対応)

```text
F01: §13 の GC 参照集合 3 本目が「保存済み Markdown からの obj:<image_hash64> 抽出」であり、
     chunks.image_hash 基準の SQL が正でない理由 (フィルタ ON 中の誤回収) が書かれている
F02: §11.2 が §11.1 (A) の ranked / selected_files を実際に組み込んだ実行可能な完全 SQL で、
     B / C モードへの差し替えが同名 CTE の機械的置換と注記されている (placeholder なし)
F03: §16 のコスト表が (content_hash, tool_profile_hash) ペア単位 (r3 適用済み — 現行確認)
F04: §9.1 collect が kind=1 → §10 ステップ 2 の b〜c、kind=2 → ステップ 4 と分岐している
F05: §10 にステップ 0.5 Reconcile (state IN (1,3) × フォルダ成果の照合 → state=2) があり、
     §9.1 に「成果あり遷移の実行点 = reconciliation と collect 冒頭」の注記がある
F06: §10 ステップ 1 の対象が DISTINCT content_hash で、JSONL の custom_id 重複なし。
     cross-repo の coalescing / fan-out は §18.6 で不採用として記録されている
F07: §5.3 に明示再生成の経路 (旧 generated_at を控える → DELETE → attempts リセット →
     再投入 → INSERT 時 max(now, 旧+1)) がある
F08: batch_requests に profile_hash 列があり、**kind と連動する表 CHECK
     ((kind=1 AND profile_hash IS NULL) OR (kind=2 AND typeof='blob' AND length=32)) で強制**
     されている (単なる nullable blob32 CHECK では不足)。collect は現行 profile と不一致の
     結果を破棄して state=3 (error='profile_changed') にする
F09: §10 ステップ 1 に backfill (all_versions の DISTINCT content_hash を低優先投入、既定 ON・
     設定で無効化可) があり、過去版込み検索の本文成立が説明されている
F10: img block の meta が 4 行 (page / bbox / source_id / media_type) で、media_type は
     マジックバイトから決定論的判定、chunks.media_type は img block から充填
F11: §9.3-c が「コピー・置換のいずれも agg_embeddings と agg_vec を同一 Tx で投入」
F12: §8 の profile 変更手順に in-flight kind=2 の discard と、dimensions 変更時の
     vec DROP → CREATE 必須がある
F13: §13 のフォルダ側孤児掃除が「同一 Tx で embedding_vec → embeddings の順に削除」
F14: agg_chunks に §5.4 と同一の行 CHECK があり、agg_vec が実 DDL (テンプレート) で掲載
F15: 規約 9 に app 全損時の bootstrap (watch_roots はユーザー設定で再入力が起点、
     folders は repository-id 検出による再発見 = 自動登録ではない) がある
F16: §20.3 の fp_cache 更新が「その枝の段 1〜2 完了後にのみ」で、持ち越しファイルを含む枝は
     更新しないと明記されている
F17: §20.5 手順 2 の delete 判定の正本が「現在版 LWW の生存集合 − walk 観測集合」で、
     scan_cache は根拠にしない。readable / skipped / absent の三値があり skipped は削除しない
F18: §20.5 にコミット入力の決定規範 (parent_hash / previous_commit_hash / created_at /
     message / event_type、delete 後再作成 = create) がある
F19: tick ステップ 0 と dirty のクリア規則 (r3 適用 + r4 で ack 補強 — 現行確認)
F20: §13 に「GC は tick.lock を取得して実行 + 24h grace」がある
F21: §9.1 cost_usd が retry で加算 (上書きしない)、job_id / submitted_at は最新値と明記
F22: §4.1 の repository_id 表記が小文字・8-4-4-4-12・brace/urn なしに固定されている
F23: verified_at の役割・採番・racy 判定基準の 3 箇所一貫 (r3 適用済み — 現行確認)
F24: F17 の三値の一部として確認 (プレースホルダ skip は「存在」扱い)
F25: §20.3 fp の JCS 表現 (hex64 文字列・name は正規化なし UTF-8 バイト順) が固定されている
F26: k_max 既定 4,096 (r3 適用済み — 現行確認)
F27: §5.4 の char_start / char_end が Unicode スカラー値単位・end 排他と固定されている
```

### r5 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
G01: batch_requests の profile_hash が kind 連動の表 CHECK
     ((kind=1 AND IS NULL) OR (kind=2 AND typeof='blob' AND length=32)) で強制されている
G02: folders と batch_requests の repository_id に typeof='blob' AND length=16 の CHECK があり、
     文書内の全 repository_id 列 (scan_cache / agg_* / sync_state を含む 8 表) で一貫している
```

### r6 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
H01: §20.5 の created_at = max(スキャン確定時刻, 最新コミット created_at + 1) の単調クランプ
H02: §20.5 に file_name の NFC 論理名規則 (保存・LWW・walk 照合・scan_cache キーの全層共通) と
     NFC 衝突ペアの後順 skipped + status
H03: §20.5 の delete 確定 2 条件 (walk 完全成功 — エラー 1 件で判定・cache 更新見送り /
     連続 2 スキャン absent)
H04: §20.4 の walk 入力域 (lstat / regular file のみ / symlink 不追跡 / FIFO 等 skipped /
     非 UTF-8 名 skipped + status)
H05: §20.4 の同一 repository-id 2 箇所目 = conflict 停止 + 明示 fork
H06: §20.4 の .folder-history のみ消失 = damaged (削除処理へ進まない)
H07: §20.3 の fp で mtime_ns / size_bytes を 10 進文字列として JCS 直列化 (2^53 問題)。
     §4.1 に「ns を JCS 数値にしない」注記
H08: §6 grammar に v: 1 (meta 5 行) + 将来変更は v +1 と一括再 materialize 手順
H09: §6 のエスケープが可逆 (\→\\ の後 -->→--\>) + un-escape は逆順、と明記
H10: §6 の alt に 1 行正規化 + ]( エスケープ
H11: §6 の本文中 grammar 適合行の行頭 \ エスケープ (phantom 防止 1 層目)
H12: §7 規則 3 に image_hash の objects 実在検証 (2 層目。実在しなければ chunk 化せず除去のみ)
H13: §7 規則 5 に max_chars 既定 2,000 (Unicode スカラー) + 2 倍超の hard split
H14: §6 に preflight (PDF / 画像のみ・マジックバイト判定・512MB 上限・Office 文書は版付き
     決定論変換を tool_profile の入力に含める・対象外は status)
H15: §6 に upload 原本の collect 確定時削除 + 結果失効 (~24h) → result_expired → 再投入
     (再課金の明記)
H16: §10 に「1 Batch job = 1 repository」(custom_id の job 内一意性)
H17: §10 ステップ 4 冒頭の profile 照合 (不一致 = 破棄 + state=3。state=2 と書いたら誤り)
H18: §8 の profile 変更 = kind=2 batch_requests を state 問わず全削除 + embedding_vec は
     次元不変でも DROP → CREATE
H19: §9.3-c は現行 profile と一致する行のみ同期 (不一致は skip — 旧空間の混入と次元不一致
     INSERT 失敗の防止)
H20: §9.3 に後退検出 (z: フォルダ max < カーソル → repo wipe + full resync)
H21: §9.3-d の削除対象に batch_requests の該当 repo 行
H22: §5.3 の明示再生成が floor_generated_at の永続保存 + backfill 設定非依存の再投入 +
     再課金の明記 (§16 のコスト表にも例外行)
H23: §9.1 batch_requests に floor_generated_at 列
H24: §5.5 の FTS content が view chunks_fts_src (text IS NOT NULL)。content='chunks' 直指定は
     誤りと明記。agg 側 (agg_chunks_fts_src) も同形
H25: §11.2 の k_fetch 初期値 = min(k_max, max(40, :limit × 4))
H26: §11.2 に検索入力の契約 (query の決定論フレーズ化エスケープ / 3 文字未満は LIKE fallback /
     target_key hex 小文字固定 (SQL は lower(hex())) / :at_hash は BLOB bind)
H27: §13 に GC fail-closed (markdown 欠損検出で中断) + fsck (週次・参照済み object の hash
     再検証・破損時の誘導) + GC 頻度 (週次) + バックアップ規範 (tick.lock 静止コピー +
     復元後 fsck)
H28: §14 に PRAGMA user_version (両 DB・起動 gate・前方互換 migration) + 権限 0700/0600 +
     tmp 掃除 (24h) + metadata.sqlite の busy_timeout
H29: §5.4 / §9.2 の type=2 CHECK に image_meta IS NOT NULL、dimensions に typeof CHECK、
     §18.2 が「4 × dimensions bytes」表現
H30: §2 にライブ複数デバイス同時編集 + 汎用同期の非対応明記 (§19 参照)、§18.6 に device 横断
     dedup の非発火注記
```

### r7 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
I01: §11.2 vec_hits の join キーが e.chunk_type || ':' || lower(hex(e.embed_hash)) で、
     §5.6 の target_key コメントも lower(hex(...)) の小文字固定。§9.1 target_key にも小文字注記
I02: §11.2 の LIKE fallback が :like_pattern (生文字列を \→\\、%→\%、_→\_ の順でエスケープ) +
     ESCAPE '\' で、フレーズ化済み :query の流用を明示的に禁止。rank = instr 昇順 → chunk_uid 昇順
I03: §9.1 に cost_ledger (追記専用 — UPDATE/DELETE 禁止、profile 変更・フォルダ退役でも削除
     しない)。batch_requests に cost_usd / pages 列が無い (残っていたら regression)
I04: 月次コスト集計が cost_ledger の ts 基準 (attempt 単位・月跨ぎ retry の発生月配賦) で
     §9.1 / §16 が一致
I05: batch_requests: state IN (0,1,2,3) (0 = submit intent)、batch_job_id nullable +
     CHECK (state <> 1 OR batch_job_id IS NOT NULL)、intent_token / upload_id / upload_cleaned 列、
     attempts DEFAULT 0 = 「job の投入回数」、idx_batch_active (state IN (0,1,3)) 部分 index
I06: §9.1 の 2 相 submit (相 1 = state=0 + intent_token + batch_job_id NULL 化 + 旧 upload 掃除
     試行 / 相 2 = upload の filename と job の metadata 両方に intent_token / 相 3 = state=1 +
     job_id + upload_id + attempts+1) と intent 回復 (job 一覧照合 → 採用 or 残骸削除 + 載せ直し)
I07: §10 の損失上限が「重複課金は intent 回復により最悪 job 1 回分」と根拠付きで書かれ、
     app.sqlite 全損はこの有界化の外 (§2 / 規約 7 参照) と明記
I08: upload 後始末 = upload_id 記録 + 「全行終端 (2/3) かつ upload_cleaned=0」の state 独立掃除
     (tick 4.5)。失敗・クラッシュは次 tick 再試行 (§6 / §9.1 / §10)
I09: job 終端後に state=1 のまま残った行を state=3 (error='output_missing') へ閉じる
     (§9.1 collect / §10 2-e)
I10: 照会失敗 (HTTP 429 / ネットワーク断) = 行不変・attempts 不消費・Retry-After 尊重 (§9.1)
I11: result_expired = state=3 で閉じ、再投入は attempts 上限内のみ (§6 と §9.1 が両立 —
     「無条件に次 tick 再投入」の記述が残っていたら regression)
I12: attempts 上限 = app 設定 (既定 3)。kind=2 の terminal 判定は profile 内で計数
     (state=3 でも profile_hash ≠ 現行なら数え直して投入対象 — §8-a / §9.1)
I13: 「フォルダ成果あり」の定義が §9.1 に明文化され全経路で統一 — kind=1 = md 行存在 かつ
     (floor が NULL または generated_at > floor) / kind=2 = 行存在 かつ profile 一致
I14: reconcile (§10 0.5) = state IN (0, 3) のみ。state=1 は collect の冒頭スキップだけが
     cost_ledger 追記と同一 app Tx で閉じる。失効窓の課金行欠落が「既知の残余」として §9.1 に
     明記され「ledger は記録できた課金、請求の正はプロバイダ側」の位置づけがある
I15: §5.3 明示再生成 = app 1 Tx で floor_generated_at 設定 + attempts=0 のみ (metadata への
     DELETE なし)。旧派生は置換まで検索に残る。collect が generated_at = max(now, floor+1) を
     適用して floor を NULL へ戻す。floor 設定済み対象は backfill 設定に関わらず submit 候補
     (§10 1)。app 全損で intent が消える旨の注記
I16: §8 の profile 変更が宣言的 a〜e (kind=2 行の一括削除・多段手動手順の記述が残っていたら
     regression)
I17: Embed submit 冒頭 (§10 3) の (i) vec 次元照合 → DROP/CREATE/現行 profile 行から再充填
     (冪等)、(ii) 旧 profile 行の vec → embeddings 順の掃除、(iii) intent 回復。
     起動時検査に embedding_vec の存在・次元一致 (規約 3 / §8)
I18: §10 3 の NOT EXISTS に e.embedding_profile_hash = :current_profile が含まれる
I19: §10 4 (Embed collect) — 現行 profile で存在 = スキップ / 旧 profile 行 = 同一 Tx で
     vec → embeddings の順 DELETE → INSERT / 無ければ INSERT (embeddings + vec + profiles)
I20: §5.7 profiles 表 (profile_hash PK blob32 / kind 1|2 / record_json)。md・embeddings を書く
     同一 Tx で INSERT OR IGNORE、書込境界で SHA-256(record_json) = profile_hash 検証。
     §3 / §5 見出しが「8 テーブル」(「7 テーブル」残存は regression)
I21: §9.3-z が 2 条件 — (1) max < カーソル、(2) カーソル commit のフォルダ側不在 —
     いずれかで wipe + full resync
I22: §9.3-d の削除対象に scan_cache / pending_deletes / 旧 root_path 配下の fp_cache が追加。
     in-flight (state 0/1) の provider cancel 試行。cost_ledger は削除しない
I23: §13 GC の中断条件に「読めた bytes の SHA-256 ≠ markdown_hash (silent bit-rot)」が含まれ、
     「参照抽出の前提は hash 一致」と明記
I24: §13 fsck = object hash 照合 + PRAGMA integrity_check / foreign_key_check + 全 commit の
     commit_record 再構築照合 + parent/previous 鎖検査。原本欠損は working copy hash 一致で
     objects へ書き戻す repair (通常スキャンでは再保存されない理由付き)
I25: §14 migration = 版ごと単一 Tx (BEGIN IMMEDIATE → user_version 再確認 → DDL →
     PRAGMA user_version → COMMIT)、途中クラッシュは巻き戻りで再実行安全
I26: §14 Windows = 継承遮断 DACL (現在ユーザー + SYSTEM)、起動時・復元後の権限検査
I27: §9.1 pending_deletes 表 + §20.5 の規則 (1 回目 absent の完全 walk で UPSERT /
     readable・skipped で DELETE / 確定 = 行存在 + 後続完全 walk で再 absent / 喪失 =
     カウントやり直しのみ / 確定コミット時に行も削除 — 手順 6)
I28: §20.3 fp_cache を確定しない枝 = 3 条件 (持ち越し / racy / pending_deletes 残存)。
     fp_cache 孤児の mark-and-sweep (完全 walk 成功時)
I29: racy 比較式 = mtime_ns/1e9 >= verified_at/1e3 (秒切り捨て)、verified_at は UTC ミリ秒
     (§9.1 コメント / §20.3 段 1)
I30: walk 対象 = watch_roots 配下 + folders.root_path (§20.3)。watch_roots は realpath 正規化
     (同一 = no-op / 包含 = 拒否)。watch_roots 外へ移動 = root_path 有効なら検知継続、消失 =
     missing + 猶予 + 再登録誘導 (§20.4)
I31: 対象外の型 (symlink / FIFO / dir 化) = その論理名の absent 観測 (通常 delete 判定へ)。
     skipped = 読み取りの一時失敗のみ。非 UTF-8 名 = どの論理名の観測にも数えず status のみ (§20.4)
I32: NFC 衝突 = 物理名 UTF-8 バイト昇順の先頭 1 件採用 + 残り skipped (§20.5 — readdir 順
     依存の禁止理由付き)
I33: §20.5 手順 1/2/4 = 1 回のストリームで hash + tmp 書込 (2 回 open の禁止理由付き)、
     rename 後の格納ディレクトリ fsync (新規 prefix は親も)。objects への全書き込みに適用
     (§3 / §6 / 規約 6 / §21.4)
I34: §20.5 時計前進の警告 (閾値 既定 72h、コミットは latest+1 で続行、修復 = 再初期化のみ)
I35: §21 操作カタログ — 21.1 register (再発見 or 新規初期化 + 失敗回復) / 21.2 unregister
     (cancel + §9.3-d 同等 + ledger 保全) / 21.3 fork = 履歴再初期化 (commits 全削除 =
     CASCADE で file_versions も。派生台帳 + objects は保持、理由 = commit_hash が
     repository_id を含む) / 21.4 restore (hash 検証 → working へ書き出しのみ、履歴反映は
     スキャン経由) / 21.5 参照表。全操作 tick.lock 下
I36: 規約 12 (フォルダ DB を開く全操作の repository-id 照合、不一致 = conflict 停止) +
     §20.4 の対応バレット
I37: §4.1 size_bytes = 10 進文字列 + 統一規則「2^53 超があり得る整数は 10 進文字列」
     (profile options にも適用)。§4 の text_hash = SHA-256(UTF-8 bytes・追加正規化なし) 明記
I38: §6 preflight — 非対象 / 512MB 超過 = terminal marker 行 (error='unsupported_format' /
     'oversize'、attempts=上限) を 1 回だけ作成 (「status 表示のみ」の残存は regression)。
     §2 構成図に cost_ledger / pending_deletes、規約 7 に損失 (r8 で 5 点へ)、§19 に規模の再考条件
```

### r8 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
J01: §9.1 相 1 (app Tx) が **kind=2 の投入時 profile_hash = 現行を INSERT / UPDATE で設定**
     (相 1 が profile_hash に触れず相 3 でのみ設定する記述は DDL CHECK 違反 = fatal regression)
J02: §9.1 相 1 が **upload_cleaned を 0 にリセット** (相 3 で upload_id だけ更新し cleaned を
     戻さない記述は誤り = 再 submit の新 upload リーク)。相 1 の外部 upload 削除は app Tx 外
J03: §9.1 collect に **job_missing (404 恒久消滅) 分岐 = state=3** (一時失敗 429 と区別)。
     §10 step2 の失敗行にも job_missing。恒久滞留の脱出路
J04: §7 の再チャンクが **floor_generated_at 設定済み派生では floor も新 generated_at へ引き上げ**
     (据え置くと再チャンクが「成果あり」化して明示再生成を無効化)
J05: §8-c の vec 再充填が **差集合冪等** (次元一致でも毎回 vec に無い target_key を補填)。
     §8-e の agg 破棄が **毎 tick 宣言的検査** (Replicate 冒頭で agg_vec 次元 × app_config の
     agg 構築 profile を照合)。「一度きり破棄・クラッシュ位置を問わない」の残存は regression
J06: §9.1 cost_ledger の cost_usd **NULL 許容 + cost_estimated 列 + UNIQUE(repo,kind,target_key,
     attempt)**。単価不明プロバイダを $0 に埋没させない。NOT NULL の残存は regression
J07: §9.1 app_config 表 (key-value)。'tool_profile' / 'embedding_profile' record +
     'agg_embedding_profile_hash'。§8 profile 変更の実体で §11.2 クエリ embedding source
J08: §11.2 の `:query_vector` 生成源 = 横断は app_config / 単独は profiles (§5.7)。
     空クエリ (trim 後空) は 0 件で全経路実行しない (`LIKE '%%'` 全一致の防止)
J09: §9.1 collect の profile_changed 破棄が **課金済み分を cost_ledger に記帳** (vector 破棄と
     台帳記帳は別)。completed_at は collect で書く
J10: §8 の client 側キュー (server-side batch 無し) 写像 = **state=1 を跨がず同 tick 内で即
     collect** (intent 回復が依拠する job 一覧が無いため)
J11: §13 fsck に **profile 層 (profiles 全行の SHA-256(record_json)=profile_hash 照合)** +
     object 層の **読取一時失敗と破損の区別** (一時失敗は再生成誘導へ倒さない)
J12: §9.3-z の後退検出が **status に regressed 通知** (metadata のみ復元は fsck 通過のため
     無言 wipe だとデータ喪失相当が不可視)。§9.3-c の列名は embedding_profile_hash
J13: §21.3 fork = **耐久手続き**: fork_in_progress で規約 12 抑止 → PRAGMA defer_foreign_keys で
     commits 全削除 (自己参照 FK の即時検査だと削除順で実行不能) → 各境界から再開可能
J14: §21.3 fork の repository-id 書換えが **安全書込 (tmp→fsync→rename→dir fsync)** +
     旧 app 行を §9.3-d 相当で **明示退役**してから新 id folders INSERT (受動表現でなく実手順)
J15: §21.1 register — 別 root_path 登録済みの再発見は **上書きせず conflict** / 新規初期化は
     **embedding_vec を profile 確定まで作らず + 配下 fp_cache 無効化** (watch_root 配下 register の
     初回コミット欠落を防ぐ) / damaged 再登録は旧 folders 行を先に退役
J16: §21.2 unregister — cancel 未確定 in-flight は **detached で残す** (削除すると再登録で
     二重課金)。§21.4 restore = **宛先必須** (in-place は非 delete 三組 / content_hash 単独は明示宛先)
     + file_name 検証 + rename 同期失敗は tmp 保持 status
J17: §20.3 walk 対象 = **watch_roots ∪ folders.root_path を重複排除** (重複 walk が「連続 2 回
     absent」を同一 tick 内に圧縮して偽 delete を生む)
J18: §20.5 file_name に **case 折り畳み比較** (case-insensitive FS の大小文字 rename 対策) +
     **検証 (パス区切り・.. 等の name_invalid 拒否 — path traversal)** + **NFC/case 衝突敗者 =
     name_collision (skipped とは別の恒久ステータス)**
J19: §14 権限逸脱は **status + 修復試行 + 修復まで fail-closed** (report のみは不足)。
     §20.4 folders.root_path の更新契機は「再発見のたび」に統一
J20: §21.5 watch_root add/remove + bootstrap、§21.6 drop-derivation (GC 恒久 fail-closed の回復)、
     §21 前文の tick.lock ブロッキング取得、§18.7 profiles 孤児は意図的に掃除しない、
     §6 grammar/§7 版移行は追跡列なし全走査、§7 annotation OFF の image_type キー省略、
     「元設計 §15/§21」の番号衝突注記、§10 tick (step3 差集合再充填 / step5 agg 検査 /
     step2 job_missing / step4 profile_changed 記帳) — いずれも反映済みであること
```

### r9 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
K01: §7 に **floor の同時引き上げ**が実在する (grep で floor が §7 に出現しなければ not-fixed —
     r8 の裁定報告が「適用済み」と誤記して 6/6 系統が欠落を検出した箇所)。generated_at を進める
     全ローカル変換 (再チャンク・フィルタ変更・grammar 再 materialize) が対象で、
     **順序 = app (floor 引き上げ) → metadata (generated_at 更新)** (逆順はクラッシュ窓で成果あり化)
K02: §9.1 batch_requests に **submission_seq (リセットしない通算投入連番)** 列。cost_ledger の
     列は attempt ではなく submission_seq、**UNIQUE (repository_id, kind, target_key,
     submission_seq)** (attempt キーの UNIQUE 残存は fatal regression — attempts リセット後の
     正当な再課金が衝突して close Tx 恒久失敗)。attempts コメントに「課金記帳のキーに使わない」
K03: §9.1 に **profile_record 列** (投入時 snapshot — kind=1 は tool / kind=2 は embedding record)。
     相 1 で書き、**相 3 と intent 回復採用では profile_hash / profile_record に触れない**
     (採用時 current 上書きは旧空間 vector の照合素通り = major)。§10 2-c / 4 の profiles INSERT は
     snapshot 由来 (「current の record を書く」記述は tool 切替中の in-flight で破綻)
K04: 相 1 の attempts=0 リセット条件 = **profile_hash ≠ 現行なら state を問わず** (§8-a も同旨。
     terminal 限定の残存は partially-fixed — state=2 の旧 profile 行が旧 attempts を引き継ぐ)
K05: 相 1 で **error / completed_at を NULL に戻す** (旧 attempt の残骸が滞留監視を汚さない)
K06: 相 2 の失敗 2 分岐 — 一時 (429/断/5xx) = state=0 のまま不消費 / **恒久拒否 (内容起因 4xx) =
     state=3 (error='submit_rejected') terminal 直行** (この分岐が無いと attempts 永久 0 の
     無限載せ直しループ)
K07: 相 3 = attempts+1 + **submission_seq+1**。intent 回復採用も同様 (+ snapshot 不変)
K08: §9.1 job_missing の判別不能プロバイダ向け規則が**時刻基準** (submitted_at + timeout_hours +
     結果保持期限 + 猶予 1 日超の state=1)。「照会失敗が attempts 回続いたら」の回数基準は
     regression (非常駐 tick に連続回数の置き場が無い)
K09: §8 の client 側キュー写像 = **実行前計上** (呼出前 app Tx で attempts+1 / submission_seq+1 /
     batch_job_id = intent_token / submitted_at を永続化 → 成功で即 collect → クラッシュは
     「実行された可能性あり」として遷移表の attempts 上限で再実行)。**「state=0 = 未実行として
     無条件再実行」の残存は fatal regression** (呼出中クラッシュで無限重複課金)。
     「重複課金は最悪 job 1 回分」は server 経路限定の主張と明記
K10: §9.1 output_missing = **provider 出力に custom_id が実在しない item のみ**。出力に在るが
     ローカル処理失敗 (SQLITE_BUSY 等) は state=1 維持で次 tick 再処理 (再課金に倒さない)
K11: §9.1 terminal 化時の課金記帳 — batch_job_id 非 NULL の成果なし terminal (expired / timeout /
     missing / profile_changed) も cost_ledger へ記帳 (cost 不明は NULL + estimated)
K12: §9.1 に **detached 行の処理規範**ブロック — 課金追跡専用 / state=1 は payload 破棄 +
     終端遷移 + 記帳のみ (metadata 書込なしの明示) / state=0 は残骸掃除して即削除 /
     全行終端 + 掃除完了で行削除 / submit・reconcile・scan 対象外
K13: §9.3-d の batch_requests 削除 = **§21.2 と同一規則** (cancel 確定 / terminal のみ削除、
     未確定 in-flight は detached)。「cancel 失敗しても timeout で自然終端するから削除」の残存は
     fatal regression。§21.2 は §9.1 detached 規範を参照
K14: §21.3 fork = **入力は対象パス**、**fork journal は層 1** (.folder-history/fork-journal、
     old_id / new_id / phase、tmp→rename→dir fsync)。app 側 fork_in_progress = (old_id, パス)。
     **fork 中は当該 repo を tick 全ステップから除外** (規約 12 抑止だけでは fork 中 tick が
     旧 id でコミットを作る)。bootstrap は journal 検出 → 回復を再発見より先に実行
K15: §21.3 手順 3 の旧行退役 = **「対象パス == folders[old_id].root_path の場合のみ」**
     (非追跡側コピーの fork で生存側の追跡・in-flight・agg を wipe しない)。batch_requests は
     §21.2 規則 (detached)
K16: §5.3 — 参照が §21.7 (旧 §21.5 は watch_root 節で誤参照)。行なし INSERT の初期値 =
     state=2, attempts=0, batch_job_id / intent_token / upload_id = NULL, submission_seq=0
K17: §20.5 case 規則 = **保存論理名を「系列の初出時の表記」に固定** (「判定は折り畳み・保存は
     readdir 表記」の残存は fatal regression — 複合 FK / PARTITION 破壊、SQLite 再現済み)
K18: §20.5 delete 確定に **最小不在時間 (既定 30 秒)** — now − first_absent_at 条件 (dirty
     早回し 2 tick の偽 delete 防止)。tick step 0 冒頭に **pending_deletes / scan_cache の残留
     掃除** (現在版 LWW が delete の行の冪等削除 — 手順 5 後・6 前クラッシュの回収)
K19: §20.4 — root_path 更新契機 =「再発見のたび (起動時 + 定期 walk)」/ **再発見の root_path
     更新時に新 root_path 配下の fp_cache を無効化** / 猶予 (既定 30 日) 満了後は **tick が
     §9.3-d を実行して retired へ** (実行者・契機の明示)
K20: §21.1 再発見の 3 分岐 — 実在 conflict (旧 path 現存 + 同 id 実在) / **missing rebind
     (root_path UPDATE)** / 未登録 INSERT (「別 root_path 登録済みは常に conflict」の残存は
     missing 回復の自己衝突 = major)
K21: §13 fsck profile 層 = hash 照合 + **参照整合 (md / embeddings → profiles の LEFT JOIN
     欠落・kind 検査)** + **破損行修復 (検証済み record で DELETE → INSERT)** (INSERT OR IGNORE
     では破損が直らない旨の明記)
K22: §14 — **FTS 後付け migration の同 Tx 'rebuild'** + **PRAGMA 接続初期化規範** (foreign_keys
     は connection ごと・全接続の open initializer で適用検証)
K23: §11.2 — ROW_NUMBER の第 2 キー chunk_uid (fts_hits / vec_hits 両方) + LIKE rank =
     instr(lower(text), lower(生クエリ)) (LIKE の ASCII case-insensitive と instr の
     sensitive の不一致解消)
K24: §11.2 — 横断検索の実行前 agg_embedding_profile_hash 照合 (不一致中は KNN 停止 + FTS のみ +
     status) + フォルダ単独の現行決定規則 (embeddings の一意 profile。空 / 混在中は KNN 停止)
K25: 規約 7 = **6 点 (a〜f)** ((f) = app_config 現行設定と unregister 退役事実 — bootstrap で
     再入力)。規約 9 に「真実 = 履歴・派生・検索の正本」の二層注記。§21.5 bootstrap に
     app_config 再入力 + 退役済み再 unregister + fork journal 優先
K26: §6 ページ結合 (page index 昇順 + 末尾 LF 正規化 join) / §7 規則 4 の行全体一致 +
     image 非境界 (前後連結・span は除去前位置) / §7 一括再チャンクの中断後全量やり直し /
     §21.6 の自動再投入 + in-flight 受け入れ注記 / batch_job_id コメント (client 前計上で
     state=0 でも非 NULL)
```

### r10 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
L01: §5.3 / §9.1 の submission_seq **新規 INSERT 初期値が cost_ledger の同キー MAX 継承**
     (`COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE 同キー), 0)`)。**0 起点
     (DEFAULT 0 のみで継承なし) の残存は fatal regression** — 行削除→再登録→再投入で旧 ledger と
     UNIQUE 衝突し close Tx 恒久失敗
L02: §9.1 collect の冪等クローズ注記の UNIQUE キーが **submission_seq** (旧 `attempt` 表記の残存は
     regression — 15 中 10 エージェントが検出した箇所。DDL L728 と叙事文の一致)
L03: §9.1 の reconcile / submit が state=0|3 を成果ありで閉じる際の**付随処理 (同一 app Tx)**:
     (a) kind=1 は floor NULL 化 / (b) batch_job_id 非 NULL は cost_ledger へ NULL+estimated 記帳 /
     (c) intent_token 残骸の掃除。**旧「既知の残余 (失効窓は記録できない)」文の残存は regression**
     (この付随処理で解消済み)
L04: §9.1 detached の **state=0 に「job 未作成 = 課金なし」前提を禁止** — (a) client (batch_job_id
     非 NULL) = terminal 記帳して削除 / (b) server (NULL) = token 照合、実在なら state=1 detached へ
     採用・不存在確認で削除・照合不能なら保持。実行点 = collect 冒頭。削除条件に
     「upload 清掃済み or upload 無」を含む
L05: §9.1 相 2 の **恒久拒否 (submit_rejected) は同 Tx で attempts=上限を設定** (据え置きの terminal
     宣言だけでは遷移表が自動再投入 = major regression)。相 2 分割 = **相 2a (upload → 直後に
     upload_id 記録) → 相 2b (job 作成)** (job 4xx で upload handle を失わない)
L06: §9.1 の **client_exhausted** (attempts 上限到達の state=0 の唯一の出口) + intent 回復の
     **dispatch** (batch_job_id 非 NULL = client → §8(iii) / NULL = server → job 一覧照合)
L07: §21.3 fork の **phase 状態機械** (PREPARED / HISTORY_CLEARED / ID_WRITTEN / APP_DONE を層 1
     journal に安全書込で進める)。回復契機 = 毎 tick 冒頭 + bootstrap。**flag → journal の削除順**
     (逆順は恒久凍結)。除外粒度 = (old_id, realpath) パス単位。**id=old なら手順 1 から再開**
     (「常に手順 3〜4」の残存は regression — 旧 id で新 folders を作り即 conflict)
L08: §21.3 手順 3 が **folders 旧行 DELETE を明示** (残すと旧 root_path × 新 id の規約 12 恒久偽
     conflict)。was_tracked は journal 固定値。新 folders は INSERT OR REPLACE。journal 破損 = damaged
L09: §8-e の agg 照合が **building / ready の 2 key** (ready は全フォルダ再レプリケーション完了時
     のみ更新)。§11.2 の検索前照合は **agg_ready_profile_hash** (単一 key で部分 index が照合を
     通過する残存は major)。app_config hash は lower hex64 固定
L10: §11.2 kind=1 の載せ直しガード **tool_changed** (target_key の tool ≠ 現行なら state=3,
     attempts=上限。current record で snapshot 書き直すと key と食い違い §5.7 hash 検証が失敗)
L11: §11.2 **最終 ORDER BY に第 2 キー chunk_uid** (RRF 同点が LIMIT 境界で揺れる)。ROW_NUMBER の
     第 2 キーは fts/vec 両方
L12: §11.2 LIKE fallback = **eligible × agg_chunks の chunk_uid 再 JOIN 完全形** (裸の text 参照は
     列不在エラー) + instr(lower, lower)
L13: §20.4 猶予の起点 = **folders.missing_since 列** (初回不在で設定・再発見で NULL。§9.1 DDL に列)。
     満了後は tick が §9.3-d 実行 → retired
L14: §20.5 delete 確定**直前の最終 stat** (wall clock 誤満了への最終防衛。存在すれば中止 + pending
     リセット)
L15: §20.5 手順 1 の open = **O_NOFOLLOW + open 後 fstat 再確認** (lstat→open の TOCTOU)
L16: §20.3 fp_cache を確定しない枝に **name_collision / name_invalid** を追加 (4 条件目) +
     **`.folder-history` 発見・規約 12 照合は fp skip 対象外**
L17: §21.1 register の rebind が **旧 path 別実体 (異 id / marker 無) も rebind** (conflict は
     「同一 id 実体が 2 箇所」限定) + 一時読取不能は保留
L18: §21.4 restore が **規約 12 照合を先に実行** (別 repo 置換の working tree 上書き防止)
L19: §21.5 bootstrap に **watch_roots 外の登録フォルダの個別パス再入力** (規約 7-f) +
     §21.6 drop-derivation の**入力に対象フォルダ** (派生台帳はフォルダ独立)
L20: §13 fsck repair = **1 ストリーム規律** (2 回 open の TOCTOU 防止) + **破損 object は既存実体が
     あっても tmp 原子置換** (「同 hash は再保存しない」の例外) + **profile 破損誘導は kind 別**
     (tool → drop-derivation / embedding → 行削除 + re-embed。「明示再生成」誤誘導の残存は regression)
L21: §21.2 / §9.3-d の削除条件が **「(cancel 確定 or terminal) かつ (upload 清掃済み or upload 無)」**
     (未清掃行を消すと upload handle 喪失 = TTL まで機密残留)
L22: 規約 7 が **6 点 (a〜f) で (f) に「watch_roots 外の登録フォルダの個別パス」を含み**、
     **「有界」を 2 種** (再実行コスト / 運用量比例の記録喪失) に区別
L23: §6 の **本文エスケープはページ結合後の全文に対して**行う (ページ単位に先掛けは結合が作る
     行頭を取り逃がす)
L24: §11.1 の at_hash 時刻のみ指定 = **X'FF…FF' 固定** (同一 created_at の全 commit 包含の一意化)
L25: §20.5 walk 不完全 (stat 恒常失敗) はそのフォルダの delete 停止を継続する**意図されたトレード
     オフの明記** + name_collision 敗者集合の増減による採用交替の意味論
L26: retry_not_before (§9.1 — submit 429 の非常駐 tick を跨ぐ抑制) を app_config に永続化
L27: §11.1 過去版検索の tool 変更後の完全性 = backfill が成立させ、**OFF は完全性放棄の設定**として
     status 明示 (「再課金なしで過去版検索可」の無条件主張の残存は regression)
L28: register の embedding_vec profile 確定まで非作成 / fsck の agg 側 vec も対象 / DDL の
     missing_since 列・app_config の retry_not_before / building / ready key — DDL とコメントに反映
```

### r11 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
M01: §9.1 の **close 経路の cost_ledger 追記がすべて冪等** = `ON CONFLICT (repository_id, kind,
     target_key, submission_seq) DO NOTHING` (collect 成功 / terminal 化 / reconcile・submit close /
     client_exhausted / detached の全経路)。**素朴 INSERT のまま / 「UNIQUE が二重計上を構造的に防ぐ」を
     字義どおり残す = fatal regression** — profile A→B→A で collect の profile_changed 記帳と reconcile
     close 記帳が同一 seq 衝突し close Tx が恒久 abort する (SQLite 再現済み)
M02: §21.2 の detached state=0 が **§9.1 の client/server 分岐に従う** (「state=0 は残骸掃除して即削除」の
     残存は regression — client 前計上・server 実在 job の課金と upload handle を落とす)
M03: §9.1 app_config DDL コメント (と本文) が **6-key** (旧版の「5-key」は転記ミス — r12 で
     'fork_in_progress' が加わり 7-key) (tool_profile / embedding_profile /
     image_filter / retry_not_before / agg_building_profile_hash / agg_ready_profile_hash、hash は
     lower hex64)。**旧単一 'agg_embedding_profile_hash' の残存は major** (§11.2 ready 照合が永久不一致で
     KNN 恒久停止)
M04: §13 fsck の embedding profile 破損誘導が **kind 別** (embedding = 行削除 + re-embed)。**旧「§5.3
     明示再生成を一律誘導」の残存は regression** (§5.3 は kind=1 OCR floor 専用で embedding に誤適用 —
     §13 後段の kind 別規範と直接矛盾)
M05: §21.3 fork 回復の flag 掃除が **「realpath に .folder-history 実体が現存する時のみ」** (実体ごと
     不在 = 移動は保留)。**再発見 (§20.4 root_path 更新) が fork_in_progress の old/new id を除外**。
     **HISTORY_CLEARED で commits 非空なら手順 1 から** (中断中フォルダ移動で未完 fork が old_id で
     新規コミットを積む穴の是正)。移動先の journal は bootstrap / walk 走査で発見
M06: §9.1 detached server 採用が **通常 intent 採用と同一 UPDATE (state=1 + batch_job_id + attempts+1 +
     submission_seq+1 + submitted_at、snapshot 不変)**。**seq 増分なしの残存は不正** — close 記帳が
     旧 lifecycle の同一 seq と衝突し、M01 の冪等吸収がこの別 attempt の課金を落とす
M07: §8(iii) client 前計上のフィールド列挙に **profile_hash (kind=2 = 現行) + profile_record (現行)** を
     含む (欠くと kind=2 DDL CHECK 違反で前計上 INSERT 不能・collect の §5.7 保存不能)
M08: §20.5 delete 直前の最終確認が **§20.4 と同じ lstat + O_NOFOLLOW + regular 判定** (readable な
     regular file なら中止・skipped は保留・対象外型 / 不在は absent のまま確定)。**「存在すれば中止」の
     素朴な stat の残存は regression** (対象外型置換を永久 delete 不能にする)
M09: §8-e ready 更新が **接続フォルダ (missing / fork 除外) の synced_profile_hash 全一致条件** (§9.3-c が
     (i) 現行 profile eligible chunk の embeddings 被覆完了 かつ (ii) agg 複製差集合空 で building へ
     UPDATE。sync_state に **synced_profile_hash 列**)。**agg_vec の same-profile silent 欠落は §8-c 同型の
     差集合冪等再充填** + **fsck が agg_embeddings / agg_vec 差集合を検査**。被覆条件なしの「全フォルダ
     完了」判定 (0 行コピーの空 index が ready を騙る) / missing を母数に含める残存は major
M10: §8-c / §8-e の vec 再作成が **次元 + 距離 (distance_metric) の照合** (距離のみ変更が次元一致で
     見逃される残存は誤り)。vec0 DDL の distance_metric は profile record から展開する `<metric>`
     (cosine 固定リテラルの残存は誤り)
M11: §21.1 register 再発見が **対象 root_path の別 id 旧 folders 行を先に §9.3-d で退役** (root_path
     1 実体 1 行。残すと旧 id 行が walk に残り恒久偽 conflict)
M12: §8 の image_filter 設定を **app_config に canonical record + hash で永続化** + §21.5 bootstrap で
     再入力 (規約 7-f)。未永続だと app 全損後に既存 chunks の設定を復元できず差分検出不能
M13: §21.1 register が **existence と readability を分離** (一時読取不能 = ロック / EIO は無変更で保留・
     status、readable だが構造破損のみ damaged)。**一時失敗を damaged (= §20.4 破壊的再初期化) に倒す
     残存は major** (「読めない ≠ 壊れている」を register にも適用)
M14: §9.1 collect の item 失敗が **batch_job_id 非 NULL なら terminal 記帳と同じ冪等記帳** (課金する
     provider の台帳欠落防止。非課金 provider では ON CONFLICT で無害)
M15: §9.1 collect の 429 Retry-After を **app_config retry_not_before に永続化** (submit 側と対称 —
     同 tick 打ち切りだけだと非常駐 tick が期限前に再照会し provider 指定に反する)
M16: §9.1 collect の **invalid_output** (決定論的に不正な payload — base64 / JSON 破損・次元不一致・
     非有限 vector) が state=3 (error='invalid_output') + 記帳で閉じる (一時失敗と区別。state=1 永久滞留の防止)
M17: §5.4 chunks に **seq / char_start / char_end の CHECK** (typeof='integer' + seq≥0 + char_start≥0 +
     char_end≥char_start — INTEGER affinity だけでは seq=0.5 / span=[7,3) を弾けない)
M18: §9.2 agg_file_versions に **§5.2 file_versions と同一の event / content / size 複合 CHECK**
     (削除版 event_type=3 の content_hash 付き露出を弾く — §11.1(B) の過去版検索汚染防止)
M19: §21.3 fork journal が **版付き canonical record + SHA-256 digest** (構文上有効な改竄・部分破損を
     回復時に検出。digest 不一致は damaged)
M20: §11.2 短語 LIKE fallback が **text と heading_path の両列**を対象 (`text LIKE … OR heading_path
     LIKE …`、rank は両列 instr の非 0 最小)。片方だけだと heading のみの短語が 3 文字境界で挙動変化
M21: §11.2 query vector が **`:query_profile_hash` を固定し `agg_ready_profile_hash` == query_profile_hash`
     を照合** (「現行」照合は embed 中 profile 変更の TOCTOU)。**query embed 失敗 (429 / 断 / 認証) も
     FTS-only + status** (必須 bind を作れないため)
M22: §5.6 embeddings.vector の float32 byte order を **IEEE-754 little-endian に固定** (異 endian 機
     コピーで length CHECK を通過したまま黙った誤順位)
M23: §11.2 `:limit` の契約 = **正整数・上限付きで入力境界検証** (SQLite の `LIMIT -1` は無制限)
M24: §16 の「突合には batch_job_id (§9.1 の既知の残余)」参照が現行文へ更新済み (「既知の残余」は
     reconcile close の記帳義務化で解消済み — 陳腐化参照の残存は minor)
M25: §9.1 DDL コメントの **孤立した監査原則番号「P9」参照を除去** (「collect の profile 不一致破棄」等の
     文書内語彙へ直書き)
M26: §6 の alt エスケープが **`\` `[` `]` → `\\` `\[` `\]`** (`](` のみの置換は先行する裸の `]` が image
     label `![…]` を早期に閉じる)
M27: §9.3-z 後退検出が **当該 repository の scan_cache / 配下 fp_cache を無効化して強制 hash scan** を
     課す (metadata のみ旧版復元で working が新しいまま fp 一致で skip され、agg=旧 と実ファイル=新 が
     deep-scan まで乖離する)
M28: §20.5 の規約 12 照合済みフォルダへの以降の操作 (open / stat / rename) を **検証済み root の dirfd に
     相対 (openat / RESOLVE_BENEATH 相当)** (照合〜使用の間の root 途中成分 swap の TOCTOU。
     restore §21.4 / fsck §13 にも適用)
M29: §9.1 reconcile close 付随処理 (c) の intent_token 掃除を **close app Tx の外**で試行 (外部 API
     呼び出しを同一 Tx に置くと 429 等が close Tx を巻き添えにする。失敗は次 tick 再試行)
```

### r12 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。「回収」= r11 裁定の名寄せ落ちの回収)

```text
N01: §8(iii) client 再実行の前計上 Tx で**直前 attempt の submission_seq を NULL + estimated で
     冪等 terminal 記帳してから attempts+1・seq+1** (client_exhausted の一般化)。上限到達時のみ
     記帳する旧形の残存 = major regression (中間 attempt の課金が台帳から永久欠落)。(回収)
N02: §9.1 intent 回復の job 一覧照合が**三値** (found / confirmed-absent / unknown)。unknown
     (照会自体の失敗) = state=0 のまま保持 + retry_not_before。二値 (見つかれば/見つからなければ) の
     残存 = major regression (実在 job と二重化)。(回収)
N03: intent_token = **UUIDv7** (時刻成分 = 相 1 実行時刻)。confirmed-absent かつ期限超 (timeout_hours +
     結果保持期限 + 猶予 1 日) は「未作成」と断定せず **submission_seq+1 + NULL + estimated の冪等
     記帳をしてから**載せ直す。期限判定なしの載せ直しの残存 = regression。(回収)
N04: §9.1 付随処理 **(b')** — state=0 server (batch_job_id NULL)・intent_token 残存の成果あり close は
     token 照合で job 実在を確認し、実在すれば掃除前に小 Tx で seq+1 + NULL + estimated を冪等記帳
     (kind=2 の profile A→B→A が単一デバイスでこの行を作る — detached (b) と同型)
N05: §8-e ready 母数 = **「当該 tick に metadata を開けて §9.3 を実行できたフォルダ」** (missing /
     fork 中 / **damaged / 一時読取不能**を除外) + **接続 0 件中は ready 非更新** + status。
     「missing と fork のみ除外」の残存 = major regression (1 フォルダの破損で横断 KNN 恒久停止)
N06: §8-e — agg 破棄 (building 書込 + wipe) と**同一 app Tx で sync_state.synced_profile_hash を
     全行 NULL** に戻す (P2→P3→P2 再訪の空 index ready 防止 — 欠落 = major regression)。
     **ready = 「設定時点の被覆」の宣言** (設定後の新規 content 遅延・復帰分は通常状態) の明記
N07: §15 規約 12 の **scoped read 拡張** — 登録済み path の読み取り (単独検索・履歴閲覧・§12 解決) も
     照合し不一致は conflict で結果を返さない / **未登録 path の standalone read は実行可 +
     repository-id を provenance 表示** (無条件 fail-closed は層 1 自己完結と矛盾 = 誤り)。
     書込限定の残存 = major regression
N08: §20.5 **「論理名 → 物理名の解決」** — 検証済み root の readdir 列挙から walk と同じ規則
     (NFC + case 折り畳み + 採用規則) で raw エントリを解決。呼出点 = delete 最終確認・restore
     in-place (§21.4 が参照)・fsck working copy。raw 無し分岐 = absent / NFC 新規作成 / 喪失報告。
     欠落 = major regression (NTFS/ext4 で restore が二重実体を作る)
N09: cost_ledger UNIQUE の DDL コメント = 「同一 seq は 1 行のみ・writer は必ず ON CONFLICT DO
     NOTHING (衝突 = 同一課金の再観測)」。旧「同一投入の二重計上を構造的に排除」の残存 = regression
N10: §10 step 3 / step 5 の vec 照合が「**次元と距離**」(§8-c/e と一致 — 次元のみの残存は不備)
N11: §10 の「最悪でも job 1 回分」に **server-side batch 経路限定**を明記 (client は attempts 上限
     — §8/§9.1 と同一の限定。無限定の残存 = 文書内矛盾)。(回収)
N12: §10 step 0.5 の対象 = **folders 実在行のみ (detached 対象外 — §9.1)** の明記。(回収)
N13: §8 (ii) client 呼出失敗の 2 分岐 (一時 = retry_not_before / **恒久 4xx = submit_rejected +
     attempts=上限・記帳なし**) + (iii) 再実行は**相 1 の規則一式** (profile 不一致 attempts=0 +
     snapshot 書き直し) を含む。(回収)
N14: §9.1 相 2a (upload) の失敗も **2 分岐** (一時 = 見送り + retry_not_before / 恒久 4xx =
     submit_rejected) — 未分岐は恒久 4xx が毎 tick 再 upload
N15: §9.1 (c) 掃除の実行条件 = **同 token 共有の全行終端** (共有 job の早期掃除 = 残行の二重課金
     防止) + **4.5 の token sweep** (intent_token 非 NULL × 全行終端 → 掃除成功で NULL 化 =
     close 後の再駆動)。(回収 — 共有 guard)
N16: fork_in_progress の**保存先 = app_config 'fork_in_progress' key** (JSON {old_id, new_id,
     realpath}。fork 中のみ・tick.lock 直列化で高々 1 件)
N17: §9.1 intent 採用の UPDATE 列挙に **submitted_at=now** を含む (時刻基準 job_missing の入力)
N18: §21.3 手順 3 — 新 folders の **root_path = 手順実行時点の実体 realpath (回復経由なら journal
     発見パス)**。journal の realpath は識別・除外・flag 削除キー専用。**INSERT 前に同 root_path の
     別 id 行を §9.3-d で退役** (§21.1 と同型)
N19: §21.3 手順 4 の逆順理由 = 「**電断後の移動と重なると** flag が掃除不能 = 恒久除外」の精密化
     (単純な「journal なき flag = 恒久凍結」は (a) の掃除規則と表面矛盾)
N20: §20.5 dirfd 適用列挙に **fork §21.3 (手順 0 journal・手順 2 repository-id)** を含む
N21: §9.2 agg_chunks に **seq / char_start / char_end の CHECK** (§5.4 と同一 — §12 preview キーは
     agg 側から読む)
N22: §9.3-c — **agg_vec への投入は常に DELETE → INSERT** (vec 孤児との PK 衝突で replicate が毎 tick
     abort するのを防ぐ) + §13 fsck は **双方向差集合** (E→V 欠落 / V→E 孤児) を検査
N23: §21.6 注記 (a) = 「現在版、**または backfill ON では過去版から参照される場合も**」自動再投入。
     回避 = backfill OFF / unregister 先行 (+ floor 例外の注意)。「現在版なら」限定の残存 = regression
N24: §7 規則 1 の **code fence = CommonMark fenced code block 規則に固定** (```/~~~・3 個以上・
     0〜3 indent・同種かつ開始以上で閉じ・EOF 未閉は残り全文・4 空白インデントも見出し抑制対象)
N25: §2 の損失要約 = **規約 7 (a)〜(f) + 有界 2 種に同期** (規約 7 を正と明記。旧 a〜e 相当のみの
     残存 = regression)
N26: §21.5 の watch_roots 復元起点の cite = **規約 9** (「規約 7」参照の残存 = 不正確)
N27: §20.5 コミット入力の message = **常に省略** (手動 commit 非提供 — 「明示操作時のみ任意指定」の
     到達不能分岐の残存 = 不備)
N28: §20.5 delete 最終確認 — 対象 = **raw 解決済みエントリ** (N08) + 「構造的に防ぐ」の絶対主張を
     避け「確認直後の再作成は次 walk の create が是正する自己修復の範囲」と明記
N29: §20.3 fp の JCS 入力から**非 UTF-8 名を除外** (JCS string で表現不能・管理対象外)
N30: 規約 12 に**読取失敗の 4 分類** (一時 = 保留 / 構造不正 = damaged / 不一致 = conflict / 不在 =
     damaged・missing) を「フォルダ DB を開く全操作」へ一般化 (M13 の register 分離の一般化)
N31: §13 バックアップ規範に **app.sqlite = Online Backup API / VACUUM INTO** (WAL 中の main 単独
     raw コピーは commit 済み ledger を失うため禁止) を明記
N32: §7 規則 4 の除去単位 = **「行全体 + 行末 LF」・空行圧縮なし** + test vector に例を含める
N33: §12 — **「完全に解決できる」は接続中フォルダ限定**と明記 + missing フォルダへのヒットは除外せず
     解決段で「フォルダ接続なし (missing)」を status 表示
N34: §7 の **un-escape** — 行頭 `\` + grammar 一致行はチャンク text 生成時に `\` を 1 つ除去 (可逆。
     char span は保存済み Markdown 位置のまま)
N35: §9.1 detached — **削除猶予窓 × 再登録の自動再投入 = 意図されたコスト** (fork §21.3 の課金注記と
     同族) の注記
N36: §10 **step -1** — §9.3-z の判定を tick 冒頭でフォルダごとに実行し、検出フォルダを同 tick の
     step 0〜4 から除外 (wipe + resync は step 5)。**z 判定が step 5 のみの残存 = regression**
     (復元直後 tick の誤課金)
N37: §7 一括再チャンクの**再開駆動 = 明示操作の再実行** (全量・冪等)・未完了 status の明記
N38: §8 image_filter = **record のみ永続化** (専用 hash key は持たない — 比較は bytes 一致。
     「record とその hash」の残存 = 契約不一致)
N39: §5.3 / §9.1 の seq 継承適用点 = 「**batch_requests 行を新規 INSERT する全経路** (相 1・client
     前計上・明示再生成 INSERT)」(「register 後の全行作成」の残存 = 誤読誘発 — register は行を作らない)
N40: §10 step 3 の vec 作成・照合の「現行 profile」参照元 = **app_config の embedding_profile
     record** (§5.7 は履歴保管庫で新規フォルダでは空)。(回収)
N41: §11.2 — **:current_tool / :current_profile は raw BLOB (32 bytes) bind** (hex TEXT bind は
     無音 0 件) の契約明記
N42: §18.4 = 「**1 repository 内の**複数対象を 1 job に積む効率」(「複数フォルダを 1 job」の残存 =
     §10 の 1 job = 1 repository と矛盾)
N43: §9.1 folders DDL — **last_seen_at の書込規則** (INSERT (register / fork 手順 3)・再発見・
     rebind で now) をコメントに明記
N44: §20.5 case 感度 = **走査時のボリューム属性で判定** (rebind / 再発見後は新属性で再判定・保存名
     不変・sensitive 化で現れた case 違い実体は別系列 = create)
N45: §13 fsck profile repair の **DELETE → INSERT = 同一 Tx (BEGIN IMMEDIATE)** (別 Tx は二重障害で
     復元材料を両側から失う)
```

### r13 修正検証リスト (C9 の対象 — 各項目の「期待される状態」)

```text
O01: cost_ledger.batch_job_id (NOT NULL) の**値規則** — server job id / client 実行 id (= token 流用) /
     **無 id 記帳 (期限超・token sweep) = intent_token** / (b') = 照合で発見した実 job id。
     **値規則の欠落 = fatal regression** (期限超記帳の INSERT が NOT NULL 違反で intent 回復恒久停止 —
     r13 で 4 系統検出・SQLite 再現)。DDL コメントに「記帳済み判別の突合キーを兼ねる」の明記
O02: **記帳済み判別述語** — 無 id / (b') 記帳の前に「同 (repo, kind, target_key) × batch_job_id =
     当該 token / 発見 job id」の既存 ledger 行を確認し、既存なら記帳省略 (seq+1 もしない)。
     **述語なしの残存 = major regression** (seq+1 は非冪等 — 再駆動のたび別 seq の推定行が増殖)
O03: §9.1 (b') — 記帳は発見 job id・述語付き・**unknown (照合失敗) は記帳も掃除もせず保持**
     (次 tick の sweep が再試行)
O04: §9.1 token sweep に **(b') と同一の前段を義務化** — batch_job_id NULL の終端行は token 照合 →
     実在かつ未記帳なら記帳 → 掃除 → 成功で NULL 化。unknown は掃除も NULL 化もせず保持。
     **前段なしの「掃除 + NULL 化」だけの sweep の残存 = major regression** ((b') が飛んだ課金済み
     job を無記帳のまま掃除して痕跡を消す — close 後の唯一の再駆動点)
O05: §9.1 期限超 confirmed-absent の処理 = **同一 app Tx で (i) 述語 (ii) 記帳 (batch_job_id =
     intent_token) (iii) attempts+1 (iv) 載せ直し相 1 (新 token)**。記帳と rotation の分離 =
     major regression (間のクラッシュで述語の効かない別 token 世代)。attempts 不消費の残存 =
     相 2b/相 3 境界クラッシュ反復が上限を素通り
O06: §9.1 — intent_token の時刻成分が **now + 許容 skew (既定 5 分) より未来・解釈不能 = 期限超と
     同様に扱う** (未来時計 token の恒久「期限内」化 → 無記帳載せ直しの防止。過剰側は述語 +
     estimated 区分が吸収)
O07: §9.1 detached (b) — **不存在確認にも attached と同一の期限判定** (期限超・未来 skew の
     confirmed-absent は記帳してから削除 — detached は載せ直さない)。期限判定なしの削除の残存 =
     major regression
O08: §6 本文エスケープの対象 = **「0 個以上の `\` + grammar 形」に `\` を 1 個前置** (G→\G、
     \G→\\G — §7 の 1 個除去と全段往復可逆)。**裸の grammar 形のみの残存 = major regression**
     (元から `\` + grammar 形の本文が un-escape で変質)。test vector 3 段 (G / \G / \\G) の明記
O09: §21.4 in-place restore — **書込前に対象を安定確認し、現内容 ≠ LWW なら先に §20.5 手順で
     コミットして履歴化** (未取り込みの working 変更を黙って上書きしない)。保全なしの残存 =
     major regression (履歴ツール自身の唯一の不可逆喪失経路)
O10: §5.3 — **md 行不在の明示再生成は floor_generated_at = 0 (sentinel)** で INSERT (「floor 設定
     済み = backfill 無関係候補」で §21.6→§5.3 の回復連鎖が backfill OFF × 過去版のみでも機能)
O11: §21 前文 — **全操作は tick.lock 取得直後に §21.3 の fork 回復を完了してから本体を実行**
     (未完 fork を跨いだ unregister が回復の手順 3 に反転される穴・二重 fork の単一 flag 上書きの
     排除)。回復先行の欠落 = major regression
O12: §15 規約 12 — **fork_in_progress の対象は呼出元を問わず照合の適用対象から除外 (共有ガード)**。
     fork 中の読取は conflict でなく「fork 進行中」status
O13: §20.5 resolver — **TOCTOU 残余窓の許容 (次回 walk が収束) を 3 呼出点共通に明記**
     (delete 確認限定の残存は不備)。restore の rename 直前再 lstat = 任意の強化
O14: §5.3 / §9.1 の seq 継承列挙に **§6 preflight terminal marker INSERT** を含む (全 4 経路 —
     規則の無例外化)
O15: §13 embedding profile 修復 — **削除は同一 Tx で embedding_vec → embeddings の順** (embeddings
     のみ削除の残存 = vec 孤児 × re-embed collect の PK 衝突で恒久失敗)。fsck はローカル側の
     vec → embeddings 逆差集合 (vec 孤児) も検出対象
O16: §10 step -1 の判定 = **三値 (verified / regressed / unreadable)** — unreadable (一時 EIO) は
     未検証として step 0〜4 から除外・保留 (「開けなかったから進む」の残存 = regression)
O17: §10 step -1 の注記 — z 検出時も in-flight job の collect は通常実行してよい (巻き戻り後の
     履歴に無い content の派生は eligible に現れない。fence 機構は設けない)
O18: §21.3 flag 掃除 — 「journal 無 + 実体現存」に加え **marker の repository-id が journal の
     old/new と一致する場合のみ**掃除 (id 不一致 = 旧パスの別 repo 再利用・読取不能は保持)
O19: §20.4 — **自動 rebind の条件は「旧パス不在」に限らない**: walk が別位置で同一 id を発見し
     旧位置が当該 repo の実体でない場合も rebind (§21.1 判定の自動化。同一 id 2 箇所実在のみ conflict)
O20: §9.2 sync_state — **初回 Replicate で INSERT (カーソル・synced NULL・synced_at=now)** +
     **building (hex TEXT) との比較は hex→BLOB 復号** (TEXT 直書きは CHECK 違反・TEXT 比較は無音不一致)
O21: §8 (ii) — client の submit_rejected は **同 Tx で batch_job_id を NULL へ戻す** (残すと後日の
     成果あり close (b) が未実行 attempt を誤記帳)
O22: batch_requests に **CHECK (state NOT IN (0,1) OR profile_record IS NOT NULL)** (相 1 / 前計上の
     必須 snapshot のスキーマ強制 — terminal marker は対象外)
O23: §10 step 2 / step 4 の冒頭に **§9.1 detached 処理 (kind 別) の再掲** (実行点の明示)
O24: batch_requests に **CHECK (floor_generated_at IS NULL OR kind = 1)** と
     **CHECK (upload_cleaned IN (0, 1))**
O25: §10 の 4.5 行 = **「Upload 掃除 + token sweep」** ((b') 前段 → 掃除 → NULL 化の順を含む —
     §9.1 参照。列挙の欠落は P10 との不整合)
O26: 規約 7 (a) = **「未回収 job の再投入 (server = 未追跡 1 job / client = attempts 上限内)」**
     (無限定「1 回分」の残存 = §8/§10 の経路限定と矛盾)
O27: §14 — **migration は tick.lock 下 + 全 writer は lock 取得後・Tx 開始時に user_version を再確認**
     (常駐旧版 writer の書込遮断)
O28: §8 冒頭の起動時検査 — 次元の参照元 = **app_config の embedding_profile record** (「§5.7 の
     record から読む」の残存 = 新規フォルダで実行不能)
O29: §21.5 watch_root 解除 — **解除の app Tx で walk 範囲外になる配下 fp_cache 行を明示 DELETE**
     (「M&S が掃除」の旧記述の残存 = 誤り — walk 主体が消えた領域は掃除されない)
O30: §11.1 mapping 表に **bind 給源の行** (横断 = app_config / 単独 = §5.7 + 一意 profile 規則)
```

### r14 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。P は原則番号のため欠番、Q = r14)

```text
Q01: §5.7 末尾・§8-c を含む**全参照点**で「現行 profile の参照元 = app_config の embedding_profile
     record」に統一 (「(§5.7 record)」「dimensions をこの record から読む」の残存 = **regression —
     O28 の残存の 3 ラウンド目**。§5.7 側には「単独検索の現行は §11.2 の決定規則で導く」役割分担が
     明記されていること)
Q02: §10 step -1 の regressed 除外に「**ただし step 2 / 4 の既存 in-flight job の collect と detached
     処理は除外しない** — 除外対象は巻き戻った状態を入力にする scan / reconcile / submit / replicate」
     の明記 (「step 0〜4 一律除外」と collect 実行可注記の並記 = 文書内矛盾の残存は regression)
Q03: 期限判定に**逆側の伝播猶予**: token 時刻成分が now から数分以内 (既定 10 分) の confirmed-absent
     は unknown 扱いで保持 (job 一覧 API の read-after-write 整合を仮定しない)。**期限判定・伝播猶予は
     4 照合点 (intent 回復・detached (b)・(b')・token sweep 前段) に共通適用の明記** (欠落 = minor、
     照合点間の食い違い = major)
Q04: 期限超同一 Tx — (ii) が **batch_requests.submission_seq を +1 へ UPDATE + 新値で記帳**と行更新を
     明示 (行 UPDATE を欠く「記帳のみ」= **major regression**: 次の正規 close が旧値から同じ +1 を
     計算し ON CONFLICT が実課金を黙殺) / (iii) の後に **(iii') attempts >= 上限なら state=3
     (error='expired') で terminal 化し (iv) を行わない** (client_exhausted の server 対応物 — 出口
     なし = major regression。token は記帳済み・掃除は 4.5 sweep 引継ぎ・復帰は明示 retry) /
     (iv) は旧 token の upload 残骸 (filename の token 埋込で発見できる未記録 upload 含む) を Tx 外で
     先に削除 (期限内分岐との対称)
Q05: (b') が **batch_requests.submission_seq +1 UPDATE + 新値で記帳 (batch_job_id = 発見 job id)** と
     行更新を明示 (Q04 と同じ理由 — 欠落 = major regression)
Q06: token sweep 前段が **found / unknown / confirmed-absent の 3 分岐**: found = seq 行 UPDATE +
     発見 job id で記帳 / unknown = 掃除も NULL 化もせず保持 / confirmed-absent = 期限判定・伝播猶予を
     適用し、**期限超は記帳済み判別 → seq 行 UPDATE + 記帳 (batch_job_id = token) してから掃除・
     期限内は記帳なしで掃除** (期限分岐なし = major regression — sweep 自身が塞ぐはずの穴)
Q07: (b') にも confirmed-absent の期限判定・伝播猶予 (期限超 = 記帳してから (c) へ / 期限内 = 記帳
     なしで (c) へ) — Q06 と同一規則 (欠落 = major regression)
Q08: upload 後始末・token sweep・detached の残骸掃除で**不在応答 (404) = 削除成功** (失敗扱い =
     毎 tick 恒久再試行・detached 恒久残留 = 不備)
Q09: §21.2 / §9.3-d / §9.1 detached の行削除条件に **intent_token IS NULL** を追加 (token 残存 =
     (b')/sweep の記帳・掃除未完。欠落 = close 直後・(b') 前クラッシュの terminal 行削除で課金
     再駆動キー喪失 = major regression)
Q10: §11.2 の**フォルダ単独決定規則が 2 本**: :current_profile = embeddings 一意 profile 規則 /
     **:current_tool = markdown_documents の最新 generated_at を持つ行の tool_profile_hash**
     (embedding との非対称 = 意図的の明記つき。tool 規則の欠落 = 単独検索実装不能 = **major
     regression**)
Q11: §21.4 手順 3a — **安定確認自体の失敗 (stat 食い違い・読取エラー) は上書きへ進まず restore を
     中止 + status** (失敗分岐の未規定・「スキップして続行」= regression)
Q12: §21.4 手順 3a — **rename 直前に解決先 raw を再 lstat し、保全時の (size, mtime_ns, inode) と
     不一致なら中止 — in-place restore では義務** (§20.5「任意の強化」の格上げ。残余窓は §20.5
     TOCTOU 同族の既知の残余と注記されていること)
Q13: §21.3「journal の破損」に**明示解決の実体 = §20.4 damaged 復旧** (ユーザー確認の上で journal /
     flag を除去 → §21.1 手順 2 の新 id 再登録)。**この経路のみ回復先行ゲートの例外** (解決経路
     なし = 全明示操作の恒久ブロック = major regression)
Q14: §21.1 手順 1 冒頭で対象の fork-journal を処理 (**有効 = §21.3 回復を先に完了 / 破損 = 明示解決
     のみ提示**) — watch_roots 外へ移動した未完 fork の検出点 (欠落 = 素通し register 後の walk
     回復がコミットを反転 = 不備)
Q15: cost_ledger DDL の batch_job_id 値規則 = 「**無 id 記帳 (期限超 confirmed-absent — intent 回復・
     detached・(b')/sweep 前段の期限超分岐) = intent_token / job 発見記帳 ((b')・sweep 前段の found) =
     発見 job id**」で本文と一致 (sweep を intent_token 側へ一括分類した旧コメントの残存 = 述語キー
     分裂で二重記帳 = 不備)
Q16: cost_ledger.ts = 課金の**確定 (collect / close 記帳) 時刻 = 確定月への配賦** (provider 請求時刻と
     ずれ得る — 正はプロバイダ側 §16 の注記。「発生月へ正しく配賦」の残存 = 不備)
Q17: 規約 7-(a) = 「**全損時は喪失時点の in-flight 全 job が対象** — server = 未追跡 1 job はアプリ
     健在時のクラッシュ窓の主張で全損はその外」 (クラッシュ窓の主張の全損列挙への流用 = 不備)
Q18: §8 (ii) client 恒久 4xx の「記帳なし」に**「内容起因 4xx = 課金なし」はプロバイダ前提**の明文化
     (拒否にも課金する provider ではこの分岐にも記帳を足す)
Q19: **profile 未設定 (bootstrap 直後) は当該 kind の submit / client 前計上を対象選定ごと skip +
     status「profile 未設定」** (DDL CHECK 依存の暗黙 fail ではなく明示 skip — §9.1 遷移表の前)
Q20: §10 step 4 の「無ければ」分岐 — **embedding_vec は DELETE → INSERT** (agg §9.3-c と同形。素朴
     INSERT の残存 = 破損起源 vec 孤児との PK 衝突で毎 tick 同一失敗 = 不備)
Q21: §13 fsck — **ローカル vec 孤児は検出して削除 (修復)**。**agg の親子整合 (agg_markdown_documents
     × agg_chunks 子行) を検査し、不一致は親行 DELETE + 当該フォルダ synced NULL 化で次 Replicate の
     全置換を駆動** (検出のみの残存 = 子行部分喪失の恒久欠落 = 不備)
Q22: §8-c に **profile hash 非照合 = §8-e と意図的に非対称**の注記 (フォルダ層に構築 profile の耐久
     記録なし — 行単位置換 + §11.2 gate が覆う)。§8-e の破棄 = **agg_embeddings は行 DELETE、agg_vec
     のみ DROP → CREATE** の係り受け明確化
Q23: §21.3 失敗回復 (a) の flag 掃除 (journal 無) — 照合元 = **fork_in_progress 記録 (flag の JSON)**
     (「journal 記録の」は字句誤り)、掃除は **id = new_id 一致のみ**。**id=old + journal 無は掃除せず
     damaged / 明示解決待ち** (old/new 両許可の残存 = 未完 fork の通常運用復帰 = 不備)
Q24: §21.3 手順 0 の前に **folders[old_id] あり・root_path 不一致 (未 rebind) なら §20.4 の rebind
     判定を先に完了** (was_tracked=false 誤判定 → 旧行残留 → damaged 偽表示の防止)
Q25: fork_in_progress の JSON に **started_at** (DDL コメント側も {old_id, new_id, realpath,
     started_at})、**猶予 (既定 30 日) 超過で status を「fork stalled — 手動介入が必要」へ格上げ
     (表示のみ)**
Q26: 規約 12 — standalone 読み取りの **fork-journal preflight** (有効 = fork 進行中で保留 / 破損 =
     damaged) + **同 id が別 root_path 登録済みなら「登録済み複製の重複コピー (conflict 中なら
     その旨)」を provenance / status に付す**
Q27: §20.5 case 規則 — **折り畳み一致する既存系列が複数の場合の tie-break** (readdir 表記と BINARY
     一致する系列 → 無ければ保存論理名 UTF-8 バイト昇順の先頭。非採用系列は delete 確認へ)
Q28: §6 grammar v — **img block を含まない (画像 0 件) 文書は版判定の対象外として常にスキップ** +
     **未知の v の再解析は fail-closed でスキップ + status**
Q29: §12 — **解決チェーンは objects/ から読んだ実体の SHA-256 を再計算・照合してから提示**
     (restore と同じ規律。不一致 = fsck 誘導)
Q30: §21.3 手順 5 — **GC は fork 完了直後・次 scan 完了前に実行しない** (現在版原本も一時参照ゼロ。
     GC の実行点 = scan を含む tick の step 5 以降)
Q31: §20.5 — 「OR IGNORE なら履歴が黙って欠落」の**事実誤認修正** (SQLite の ON CONFLICT は FK 違反に
     適用されない — FK 違反で INSERT が失敗しコミット Tx が毎スキャン失敗する、へ。設計判断 =
     保存表記固定は不変)
Q32: §11.2 — **:query_vector の bind 形式 = float32 (little-endian) raw BLOB、dimensions × 4 バイト**
     の明記
Q33: §9.2 — agg_chunk_fts の**読み替え規則の明文化** (chunks→agg_chunks / chunk_id→chunk_uid /
     chunk_fts→agg_chunk_fts / view・trigger 名に agg_ 接頭辞。これ以外の読み替えは無い)
Q34: §13 バックアップ規範 — **復元 (書き戻し) も tick.lock 下**と明記 (lock 外の外部復元は z 判定が
     回収する検出前提の経路 — 静止復元が正)
Q35: 期限超 (iv) と期限内の載せ直しの **upload 残骸掃除の対称性** (期限超側にも token ベースの未記録
     upload 削除が明記 — Q04 (iv) の独立確認)
Q36: §21 前文 — 回復先行の**唯一の例外 = 破損 journal の明示解決 (§21.3)** の明記 (Q13 の前文側)
Q37: §11.1 mapping 表の bind 給源行 — 単独 = :current_profile (§5.7 + 一意 profile 規則) と
     **:current_tool (markdown_documents 最新 generated_at 規則)** の両方 (Q10 の mapping 側)
```

### r15 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。R01〜R04 は転記漏れ補修の再発検査)

```text
R01: §9.3-z 側にも「ただし step 2/4 の既存 in-flight job の collect と detached 処理は除外しない —
     除外対象は巻き戻った状態を入力にする scan / reconcile / submit / replicate」の例外が §10
     step -1 と**鏡写しで両方に**明記 (片側のみ = regression — r15 補修の再発)
R02: 期限超の Tx 境界 = 「**(i)〜(iv) の DB 書込 (載せ直し相 1 の行更新を含む) を 1 Tx** ((iv) の
     外部 upload 削除の呼出だけ Tx 外)」 (「(i)〜(iii') を 1 Tx」の残存 = regression — 記帳・attempts
     確定後・rotation 前クラッシュ反復の偽 expired)
R03: §9.3-d と fork 手順 3 の削除規則パラフレーズ = **完全 3 条件** (「(cancel 確定 or terminal) かつ
     (upload_id IS NULL or upload_cleaned=1) かつ intent_token IS NULL」) (ガード落ちの要約 = major
     regression)
R04: §20.5 の rename 直前再 lstat = 「**in-place restore では義務** (§21.4 — 保全時 (size, mtime_ns,
     inode) 照合・不一致中止)。delete 確認・fsck は任意」 (「任意の強化 — 義務ではない」の残存 =
     regression)
R05: 伝播猶予 = **過去側のみ (0 ≤ now − token 時刻 ≤ 猶予・既定 10 分)・未来 skew 判定が常に優先** +
     **プロバイダ採用条件** (「job 一覧の可視化遅延上限 ≤ 伝播猶予」— provider 別設定可。保証でき
     ない provider では有界化不成立の明記)
R06: (b')・token sweep の found 記帳 = seq 行 UPDATE + 新値で記帳 + **同じ小 Tx で行の batch_job_id
     へ発見 job id を書く (自己記述化)** (欠落 = found 記帳 (job id) → 一覧消滅 → 期限超記帳 (token)
     の述語時間差分裂で同一 job 二重計上 = major regression)
R07: token sweep 前段の照合対象から **error='submit_rejected' (未作成/未実行の確定) を除外**し、
     照合・記帳なしで残骸掃除 → NULL 化 (欠落 = client (job 一覧なし) で恒久 unknown → token 永久
     残留 → 削除ガードで削除不能 = major regression。server の期限超 phantom 記帳も防ぐ)
R08: detached state=0 (a)/(b) = 記帳 Tx で **state=3 (error='detached'/'expired') + completed_at の
     terminal 化** → 4.5 (掃除・NULL 化) → 削除条件成立で削除、の段階遷移 (「記帳して即削除」の
     残存 = 削除ガードとのデッドロック = major regression)
R09: 相 1 の旧 upload 削除 = **同 upload を共有する全行が終端 (2/3) の場合のみ** (4.5 と同条件。
     無条件削除 = state=1 の同輩の入力を消して回収不能 = major regression)
R10: 相 1 — 旧 intent_token 非 NULL のまま再投入する場合 (sweep 未完 terminal への明示 retry・
     profile 変更経由) は、その token の未記録 upload 残骸の削除を先に試みる (rotation の探索キー
     喪失対策)
R11: §7 un-escape の対象判定 = **§6 と同一の緩いパターン (1+ `\` + 行頭 `![`+`](obj:` or
     `<!-- img:`) — hash64・行全体一致を要求しない** (厳密読みの残存 = `\` 残留で往復可逆が破れる =
     major regression。認識は厳密一致 + 実在検証のまま)
R12: §6 — **grammar 再 materialize は本文を再エスケープしない** (保存時 1 回限りの変換 — 再適用 =
     `\` の版ごと累積)
R13: 規約 6 に **floor 引き上げ (app → metadata) の例外併記** (fence 系意図書込には適用しない —
     §7 の順序規範が優先)
R14: :current_tool の**同時刻 tie-break = tool_profile_hash バイト昇順** + **一括変換逆転の近似注記**
     (「最後に触れられた世代」の決定論的選択 — 厳密復元は層 1 の目的外)
R15: journal 検査の**三値化 (§21.1 手順 1 と §21.3 の両方)** — 破損 = 読めたが digest 不整合・構文
     不正のみ / **一時読取不能 (ロック・EIO) = 無変更保留 + status** (区別なし = 有効 journal の
     一時ロックを履歴破棄へ誤誘導 = major regression)
R16: 破損 journal 明示解決の**順序** = (1) journal 除去 (flag 残置) → (2) §21.1 手順 2 → (3) flag は
     (a) 規則 (id=new) が回収 (同時除去 → 初期化の残存 = 途中クラッシュで解決意図の喪失)
R17: fork 回復表に「**実体 id が old/new 以外 (第三の id) = damaged 停止 / 一時読取不能 = 保留**」の
     行 (old/new のみの表で推測正常化 = 不備)
R18: fsck に **FTS の external content 照合つき integrity-check** (local = 同 Tx rebuild / agg =
     synced NULL + 親 DELETE で全置換駆動 — posting 単独破損は PRAGMA integrity_check で検出不能)
R19: fsck の親子/FTS 再同期駆動 Tx で **agg_ready_profile_hash も削除** (修復中の部分 index が
     ready を騙らない)
R20: LIKE fallback = **`c.text IS NOT NULL AND (...)`** (fallback が FTS の対象集合を広げない)
R21: profile 未設定 skip の範囲 = submit / 前計上 + **reconcile/collect の成果判定・§8-c vec 検査・
     §8-e/Replicate 検査** (state=1 は不変で保留 — 再入力後の collect が回収・記帳)
R22: item 失敗記帳の文言 = 「非課金と契約上確定した provider では記帳省略可」 (「非課金 provider
     では ON CONFLICT で無害に skip」の残存 = 事実誤認 = 不備)
R23: 一括変換の **operation record** (app_config — 種別 + 目標 record/hash + 開始時刻。全量完了で
     消す hint — クラッシュ後の未完了 status 用。正しさは再実行が担う)
R24: **除去・un-escape 後の本文が空白のみの文書は text チャンクを生成しない** (画像のみ・全画像
     除外 — 空チャンクの実装分岐防止)
R25: §21.4 — **raw エントリ不在は「安定確認の失敗」と区別**し、保全対象なしとして NFC 新規作成へ
     (混同中止 = raw 無しへの正当な復元が恒久不能)
R26: profile 設定の**適用前に vec0 受理検証** (一時 CREATE 試行 — 拒否は commit せず status)
R27: §5.7 — **PK が hash 単独で足りる前提 (tool/embedding record の構造的排他) の注記** (record
     仕様変更時は kind 判別フィールド)
R28: app_config の key 契約 = **許可 key 集合 + key 別存在条件** (「すべて必須」の残存 = bootstrap
     直後・非 fork 時の正常状態と矛盾)
R29: §14 — **auto_vacuum = INCREMENTAL (新規 DB) + fsck 週次での PRAGMA incremental_vacuum** の注記
     (DELETE による単調肥大の防止。全量 VACUUM は規範にしない)
```

### r16 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。S01〜S03 は r15 検証項目の補修の再発検査 — **判定は必ず両側 (規範文とその要約・掲載 SQL・DDL コメント) を引用で証明する**)

(r16 が置換) R06→S10・S15 / R07→S19・S28 / R08→S01 / R13→S02 / R18→S02 / R20→S03 / R23→S04 /
R25→S06 — 判定は新項目で行い、旧項目は「superseded (→S##)」と記して不合格事由に数えない。

```text
S01: §21.2 detached の client (batch_job_id 非 NULL) 分岐 = **terminal 記帳 + state=3
     (error='detached') + completed_at で terminal 化し、削除は 3 条件 ((cancel 確定 or terminal)
     かつ upload 清掃済み (or 無) かつ intent_token IS NULL) の段階遷移に委ねる** (「記帳後に (即)
     削除」の残存 = regression。§9.1 detached (a) との両側一致を引用で確認)
S02: §13 の FTS 整合検査 = **`INSERT INTO chunk_fts(chunk_fts, rank) VALUES('integrity-check', 1)`**
     (SQLite 3.42+ — rank 引数なしの形の残存 = major regression。external content 照合が効かず
     posting 単独欠損が偽陰性)。**agg_chunk_fts の不一致は同 Tx 'rebuild'** (「synced NULL 化 +
     該当親行 DELETE」の残存 = 実行不能規範 = major — integrity-check は破損箇所を特定しない)
S03: §11.2 の**差替え用 SQL にも `c.text IS NOT NULL AND (...)`** (欠落 = major regression —
     text=NULL の画像 chunk が heading 短語一致で混入。規範側の必須条件との両側一致)
S04: app_config の許可 key 集合に **'bulk_operation'** — §9.1 の key 列挙 + key 別存在条件 (一括
     変換実行中のみ) + §7 側の key 名明示の **3 点全部** (いずれか欠落 = partially-fixed)
S05: §21.3 破損 journal 明示解決の手順 (2) = **新規採番せず flag (fork_in_progress) の new_id を
     採用** (id の自己記述化 — (a) 規則の掃除条件 (実体 id = new_id) を成立させる)。flag 不在・
     読取不能時のみ新規採番。素の §21.1 手順 2 呼出 (常に新規採番) の残存 = major (第三 id →
     flag 恒久残留・realpath 恒久除外)
S06: §21.4 の rename 直前再 lstat 義務が **raw 不在分岐にも適用** (不在 → 出現 = 不一致で中止) +
     可能なプラットフォームでは **no-replace rename** (renameat2 RENAME_NOREPLACE / renamex_np
     RENAME_EXCL / MoveFileEx 非置換、EEXIST 相当 = 中止・再試行)
S07: batch_requests に **job_create_started_at 列** (DDL) + **相 2b 呼出直前に単独小 Tx で記録**
     (再試行は上書き) + **伝播猶予の起点 = max(intent_token 時刻, 同列)** + **NULL = 相 2b 未着手 =
     期限判定のみで「未作成」断定可** — 4 点セット (いずれか欠落 = major)
S08: 伝播猶予の**未来側**: now < 起点 ≤ now + 許容 skew (5 分) の帯域は unknown と同様に保持
     (期限超扱いは skew 超のみ — 帯域無保護の残存 = major)
S09: 「一覧の正常応答」= **該当範囲の全ページ走査を完了した応答に限る** (pagination の部分応答は
     confirmed-absent でなく unknown — 全照合点の共通則の側に記載)
S10: token sweep found の未記帳判別 = **batch_job_id IN (発見 job id, 当該 intent_token) の ledger
     行なし** (発見 job id 単独の残存 = major — 期限超 token 記帳 → crash → 遅延可視化 found で
     同一 job が 2 行計上)
S11: §21.2 の cancel 確定 = **state=3 (error='cancelled') + completed_at + (batch_job_id 非 NULL
     なら) terminal 化時の冪等記帳を同一 Tx**、削除は段階遷移 (「cancel 確定した行は削除対象」の
     残存 = major — state=1 のまま token 永久残留)
S12: プロバイダ採用条件に**第 2 条件「terminal 後も job が一覧に残る保持期間 ≥ timeout_hours +
     結果保持期限 + 猶予 1 日」** (可視化遅延上限と独立)
S13: detached (b) の期限内 terminal 化に**「伝播猶予内の confirmed-absent は共通則どおり unknown
     保持 — 即 terminal 化しない」**の明記
S14: detached 期限超の列挙に **attempts+1** (attached (iii) と同じ「作成済みであり得た attempt」の
     消費)
S15: sweep found の小 Tx に **attempts+1** (実在した job = 消費された attempt)
S16: §10 の「最悪 job 1 回分」有界主張に**「§9.1 のプロバイダ採用条件 (可視化遅延上限・保持期間)
     を満たす provider に限る」**の限定
S17: §6 に **Batch 入力形式**: JSONL 行 = upload 済み原本の file id 参照 (**base64 内嵌不使用** —
     512MB 判定との乖離防止)・**JSONL 自身の upload も filename token 埋込の掃除対象** (upload_id
     列は原本用)
S18: §10 step 2 の state=1 照会 = **folders に現存する repository の行に限る** (detached は冒頭の
     detached 規範のみが扱う)
S19: submit_rejected の sweep 除外の注記に**「拒否にも課金する provider では倒す分岐自体で同一 Tx
     冪等記帳 (seq 現値・batch_job_id = token・NULL + estimated)」**の実体化
S20: §5.7 の kind 排他を **shape 検証で強制** (tool = annotation_schema 必須 / embedding = options
     内 dimensions・metric 必須・他 kind の必須フィールド持ちは拒否) + **model = provider /
     adapter 名前空間を含む解決済み完全修飾名**
S21: §13 に **folder 側の markdown_documents↔chunks 親子件数検査** (不一致 = §7 再解析で再構築 —
     agg 側検査との対称)
S22: §6 に**投入直前の原本再照合** (objects bytes の SHA-256 再計算 — 不一致は投入せず fsck へ)
S23: §20.5 に **per-directory case 感度への備え** (同一 dir 内の case 違い併存を検出 = 当該 dir を
     sensitive 扱い)
S24: §21.1 rebind に**旧 root_path 配下の fp_cache DELETE** (walk 主体喪失領域の孤児防止)
S25: **Retry-After 無し 429/5xx の既定 backoff** (例: 60 秒 × 連続失敗、上限 15 分) を
     retry_not_before へ (submit / collect 共通)
S26: §13 に**同一サイクル内は fsck → GC の順**
S27: §21.3 journal digest の目的 = **部分書込・bit-rot 検出 (悪意ある改竄への耐性ではない)** の文言
S28: sweep の自己記述化の注記に**「照合から外れるだけで、batch_job_id 非 NULL 行 (自己記述化済み・
     client 前計上・detached (a) terminal) も同 token の残骸掃除・intent_token NULL 化の対象に
     含まれ続ける」** (外すと token 永久残留 = 削除ガードと恒久矛盾)
S29: §10 step -1 の unreadable 分岐に**「in-flight collect の非除外例外は unreadable では実行不能 =
     実質 regressed 側にのみ効く」**の注記
```

### r17 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。T01〜T04 は r16 検証項目の補修の再発検査 — **判定は必ず両側 (規範文とその要約・掲載 SQL・DDL コメント) を引用で証明する**)

(r17 が置換) S06→T09 / S07→T05・T06 / S11→T07 / S19→T03 / S20→T01 / S23→T18 / S24→T02 /
S25→T04 — 判定は新項目で行い、旧項目は「superseded (→T##)」と記して不合格事由に数えない。

```text
T01: §4.1 の record 例は **kind 別 2 形に分離** (tool = annotation_schema あり / embedding =
     annotation_schema を持たない — 共通形の残存 = regression) + §5.7 の必須フィールド名は
     **distance_metric** (§4.1 / §5.6 と同一 — 「metric」等の別名の残存 = regression)
T02: rebind の**旧 root_path 配下 fp_cache DELETE が 3 箇所** — §21.1 missing 分岐・§21.1 別実体
     分岐 (共通 action 参照)・§20.4 自動 rebind (「rebind の実体は §21.1 と共通」)。いずれか欠落 =
     partially-fixed (§9.3-d 退役の一括 DELETE は既存の第 4 の掃除点)
T03: submit_rejected の「拒否にも課金する provider」の記帳 = **submission_seq を +1 へ行 UPDATE し
     新値で記帳** (「seq 現値」の残存 = major regression — 明示 retry 後の 2 度目拒否が同一 seq の
     UNIQUE で吸収され記録喪失)
T04: Retry-After 無し一時失敗の既定 backoff は**全分岐共通** (相 2a upload 失敗・相 2b job 作成
     失敗・client 呼出・collect 照会失敗・intent 回復 unknown — 「各分岐の Retry-After 記述は
     共通則の再掲」の明記)
T05: 相 1 の NULL 戻し = **batch_job_id / error / completed_at / job_create_started_at の 4 列**
     (job_create_started_at 欠落 = major — 旧 attempt の残置値を猶予起点の max() が拾い、時計後退と
     重なると未呼出 attempt の attempts 消費・estimated 記帳を反復)
T06: **「NULL = 相 2b 未着手の証明」は列導入後の lifecycle 限定** (§9.1 DDL コメント) + §14 に
     **列追加 migration の backfill 規範** (state=0 かつ intent_token 非 NULL の既存行へ token の
     時刻成分を backfill、同一 Tx) — 両側 (DDL コメント・§14) の一致
T07: §21.2 の cancel 確定 = state=3 (error='cancelled') + **attempts = 上限** + completed_at +
     (batch_job_id 非 NULL なら) 冪等記帳を同一 Tx (自動再投入なし・復帰は明示 retry のみ) /
     **batch_job_id NULL かつ intent_token 非 NULL の行は「cancel 確定」禁止** → detached 例外へ
     (確定扱いは実在し得る job を記帳なしで閉じる)
T08: **rotation ガード** — intent_token 非 NULL の行 (前 lifecycle の token 残存 = sweep 未完) の
     再投入は、当該 token の sweep 前段 (照合・記帳・残骸掃除・NULL 化) を完了してから相 1 を行う
     (先に rotation すると旧 token の照合キーが消え、作成済み job の発見・記帳経路が恒久喪失)
T09: no-replace rename **非対応環境 (ENOSYS / EINVAL / EOPNOTSUPP) の規範**: 判定は初回試行の
     エラーで確定 (ボリューム単位記憶可)・fallback は「rename 直前の再 lstat (不在 → 出現 = 中止) +
     通常 rename + 残余窓の明示的引き受け」に限定 (黙って置換 rename = 不適合)・EEXIST 相当は常に
     「出現 = 中止・再試行」
T10: **変換 PDF は一時生成物** — objects/ へ保存しない・content_hash / 保存 / 照合の対象は常に
     原本 bytes・投入直前再照合は原本 → 照合後に同一コンバータで決定論的に再変換して upload・
     **upload_id 列と filename への token 埋込は変換物 (実際に upload した bytes) に適用**・課金
     入力は job 応答から
T11: fork-journal record に **started_at** (stalled 猶予の起点 — flag と二重化し、app.sqlite 全損後も
     journal 単体で stalled 判定可能)
T12: img block の **v 混在 = fail-closed** (「先頭 block の v を正とする」前提の明文化 + 全 block
     一致検査 — 混在は未知の v と同様に解析停止 + status)
T13: resolver の採用規則 = **walk の case 規則 (初出表記固定・BINARY 一致優先・UTF-8 昇順
     tie-break) と同一実装の共有**を明示 (独立実装は name_collision の収束が呼出点ごとに分かれる)
T14: folder 側親子検査 = **件数 + 各 text チャンクの SHA-256(text) = text_hash 照合** (件数のみ =
     内容破損が素通りし FTS rebuild が破損を固定化)
T15: **query の NUL (U+0000) を境界で拒否/除去** (FTS5 MATCH bind の構文エラー防止 — :limit と同じ
     入力境界契約)
T16: fts_hits / KNN k に**内部上限 :fts_cap** (外側 :limit は fusion・集約・sort の後 — 中間膨張を
     防げない。cap は再現率とのトレードオフとして設定)
T17: trigram FTS と LIKE fallback の **case 折り畳み不一致の規範** — 両側同一折り畳みが正・不能な
     実装は「短語一致は case 厳密の近似」の明記を選ぶ (暗黙の非対称は不適合)
T18: per-dir case override は **sensitive 方向のみ**の明記 + 属性照会可能な FS では dir 属性優先 +
     照会不能環境の case-only rename 分裂は「喪失なしの既知の近似挙動」と明記
```

### r18 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。U01〜U08 は r17 検証項目の補修の再発検査 — **判定は必ず両側 (規範文とその要約・掲載 SQL・DDL コメント) を引用で証明する**)

(r18 が置換) T03→U04 / T08→U03 / T10→U01 / T11→U05 / T16→U02 — 判定は新項目で行い、旧項目は
「superseded (→U##)」と記して不合格事由に数えない。

```text
U01: §6 Batch 入力 = 「upload 済み**入力** (原本 — Office 文書は変換 PDF) の file id」+ §9.1 相 2a =
     「入力 upload (原本 — Office 文書は変換 PDF、§6)」 — 「原本の file id」「原本 upload」の
     残存 = regression (Office 文書で r17 M5 と両立不能に戻る)
U02: 掲載 SQL の fts_hits に **`ORDER BY bm25(agg_chunk_fts), e.chunk_uid` + `LIMIT :fts_cap`**
     (rank 順の決定論的打切り・KNN 側対応物 = :k_fetch の注記) + §19 は「§11.2 で :fts_cap として
     導入済み (旧称 :k_fts は同一物)」 — SQL 側欠落 or 旧称単独残存 = regression
U03: rotation ガードの**新 3 原則** — ①適用 = **state=3 (terminal) の再投入のみ** (state=0 の
     載せ直し・client 前計上の再実行 dispatch は対象外の明記つき) ②本体 = 照合・記帳・intent_token
     NULL 化 (**残骸掃除は完了条件に含めない** — best-effort 続行) ③照合が恒久 unknown の行 =
     stalled 可視化 + **明示 abandon** (ユーザー確認で estimated 記帳 + NULL 化)。旧「全行終端
     sweep 完了後」形の残存 = major regression (state=0 requeue と自己循環)
U04: §8 の「この分岐にも記帳を足す」に **submission_seq +1 行 UPDATE + 新値で記帳**の明記
     (§9.1 sweep 注記との両側一致)
U05: 滞留の可視化 = fork_in_progress の started_at (**flag 不在・app 全損時は journal の
     started_at へフォールバック**)
U06: collect close に **completed_at = now の同時書込 — 「state を 2/3 へ確定する全ての UPDATE に
     共通」**の明記 (detached 経路限定の残存 = partially)
U07: 構文検証スキップの**有界化** — 同一 (size, mtime_ns, inode) のまま連続 3 回 (or 24h) 失敗 =
     安定内容として **bytes のままコミット** (「保存は bytes ベース」の原則明記)
U08: §10 step 4 (Embed collect) に「**照会する state=1 は folders 現存行に限る**」(step 2 との
     両側一致)
U09: §6 変換の失敗分岐 — 決定論的失敗 = **state=3 (error='convert_failed', attempts=上限) を
     1 回だけ** / 環境起因 = 行を作らず次 tick + 共通 backoff + status。**512MB は変換後 bytes にも
     適用 (検査は変換してから)**
U10: GC 参照集合の**未知 grammar v fail-closed** — 未知 v・v 混在の文書由来の参照は保守的に全保持 +
     status (旧 regex 抽出が新形式参照を 0 件と誤認して原本を誤回収する穴の閉鎖)
U11: cancel の「自動再課金しない」= **行が存在する間の規範** (削除条件到達後の再登録 = detached
     注記と同じ意図されたコスト) + §21.6 = 「unregister **して watch_root 外へ移す**」(単独では
     再発見で再登録 — §21.2)
U12: 照合の正常応答 = 全ページ走査 **かつ job 作成時と同一の account / workspace scope** (資格情報・
     tenant 変更後の一覧は unknown — scope 安定は採用条件と同列)
U13: 管理フォルダ内 export = **新規作成限定・no-replace 必須・既存実体は中止** (上書きは保全つき
     in-place restore を使う)
U14: batch_job_id の DDL コメント = 「server 経路の state=0 では NULL (**行上は未記録 — job は
     存在し得る**。intent 回復が照合 — NULL を不存在の根拠にしない)」
U15: dedup 破棄の前に**既存 object の SHA-256 再計算照合** — 不一致 (bit-rot) は tmp で置換 (自己
     修復) + fsck 報告
U16: walk に**訪問済み (st_dev, st_ino) 集合**でディレクトリ再訪拒否 (bind mount・junction 循環)
U17: **未来 mtime の racy 例外** — 段 2 の hash 照合一致で fp 確定可 (恒久 racy の毎 tick 全量
     読取 → tick.lock 飢餓の防止)
U18: fsck 親子検査 = **全 field 照合** (text = SHA-256(text)=text_hash / image = image_hash・
     media_type・image_meta / 共通 = seq・chunk_type・heading_path・span — §7 再解析出力との
     完全一致)
U19: size_bytes 等の 10 進文字列 = **先頭ゼロなしの最短表記**に固定
U20: heading_path の JSON 直列化 = **raw UTF-8 固定 (\uXXXX escape 禁止)** (DDL コメント)
U21: PRAGMA **incremental_vacuum(N)** (N = 有界ページ数 — 引数なしの全量回収は不可)
U22: 表現整合 4 点 — §10 step 5 の破棄 = 「agg_embeddings (行 DELETE) / agg_vec (DROP→CREATE)」の
     区別 / §5.3 の「旧派生は保持しない」= 同一 (content, tool) の置換の話と明記 / FTS ラグ =
     chunk_fts (step 2) と agg_chunk_fts (step 5) の層区別 / intent_token = job 単位 (JSONL 分割の
     決定は相 1 の採番より前)
U23: flag 不在の明示解決の crash 窓 = 「解決前の運用状態への復帰で安全側」の注記
U24: 再開表の「phase × id の不可能組合せ」(ID_WRITTEN / APP_DONE なのに id=old 等) — **独立行は
     意図的に未追加** (既存「第三の id」行の fail-closed 原則で被覆と裁定)。現文で不可能組合せが
     damaged 停止に読めるなら fixed、素通りする読みが成立するなら partially-fixed として具体的な
     読み筋を引用 (r19 での要否再評価項目)
```

### r19 修正検証リスト (C9 の対象 — 各項目の「期待される状態」。V01〜V06 は r18 検証項目の補修の再発検査 — **判定は必ず両側 (規範文とその要約・掲載 SQL・DDL コメント) を引用で証明する**)

(r19 が置換) N23→V05 / U01→V01 / U03→V07 / U06→V02 / U11→V04 / U24→V03 — 判定は新項目で行い、
旧項目は「superseded (→V##)」と記して不合格事由に数えない。

```text
V01: §6 / §10 の upload 対象語 = **「入力 (原本 — Office 文書は変換 PDF)」に全所統一** — 「列は
     原本用」「upload 原本の削除」「原本を…投入」の残存 = regression。**例外 = 「投入直前の原本
     再照合」のみ「原本」を維持** (照合対象は常に原本 bytes — §6 変換規範)
V02: completed_at の DDL コメント = 「**state が 2/3 へ確定する全ての UPDATE で同時に書く**」
     (reconcile / submit_rejected / client_exhausted / expired / cancelled / detached / abandoned の
     列挙つき — 「collect が閉じた時刻」限定の残存 = regression)
V03: §21.3 再開表に「**phase = ID_WRITTEN / APP_DONE なのに id = old = 不可能組合せ → damaged
     停止 + 明示解決待ち**」の独立行 (「old/new 以外」の第三 id 条件だけでは id=old が素通り)
V04: §21.2 の再 OCR / re-embed 断定 = 「**完成済みの派生が保持されている場合**」に限定 + detached
     payload 破棄・cancel 行は再登録後に再課金され得る (意図されたコスト) の明記
V05: §21.6 の回避策「原本を退避する」に「**backfill ON では退避だけでは止まらない — backfill OFF と
     併用**」の注記
V06: §20.5 の bytes 原則参照 = 「**(§1 の原則)**」 (「(P1)」等、文書内に定義の無い参照の残存 =
     regression)
V07: rotation ガード = **state IN (2, 3) かつ intent_token 非 NULL の行の再投入** (明示 retry・
     遷移表再投入・**floor 明示再生成 (state=2 も投入対象)**) に適用 — state=3 単独の残存 = major
     regression (floor 再生成経路が token を上書き)。本体 = 照合・記帳・NULL 化 (掃除 best-effort)・
     state=0 対象外・恒久 unknown = stalled + 明示 abandon の 3 原則は維持
V08: batch_requests に **scope_id 列** (DDL — NULL = 相 2b 未着手 or 旧版由来) + **相 2b 直前の
     小 Tx で job_create_started_at と同時記録** + **照合の同一 scope 判定 = 行の scope_id と現照会
     scope の比較・NULL は (job_create_started_at 非 NULL なら) 常に unknown** — DDL・記録・照合の
     3 面一致 (いずれか欠落 = major)
V09: scan_cache に **syntax_fail_count / first_failure_at** (DDL) + **reset 規則** (stat tuple 変化・
     構文検証成功で reset / **一時読取失敗 (EIO・AV ロック) と安定確認失敗はカウントしない**) +
     24h の起点 = first_failure_at — DDL↔規範の両側 (メモリ計数の残存 = major)
V10: 明示 abandon の**操作実体** — 対象 = intent_token 非 NULL (state 不問・state=0 の恒久 unknown
     を含む)。**単一 app Tx**: (i) 記帳済み判別 (batch_job_id IN (発見 job id, 当該 token)) →
     (ii) 未記帳なら submission_seq +1 行 UPDATE + 新値で token キー estimated 記帳 → (iii) state=3
     (error='abandoned') + attempts=上限 + completed_at → (iv) intent_token NULL 化。後日可視化は
     IN 判別が吸収
V11: **fp の入力から `.folder-history/` を除外**の明記 + **fp 一致スキップの例外 = 登録フォルダの
     fork-journal 存在検査** (journal は fp 外 — 検査を怠ると §21.3 (b) の walk 検出が恒久に殺される)
V12: **未来 generated_at (now + 許容 skew 超) は :current_tool 判定の候補から除外 + status 警告**
     (全行未来なら最新採用)
V13: 安定した (st_dev, st_ino) を提供しない FS = **当該 watch_root を fail-closed** (走査せず status)
V14: alt の処理 = **1 行正規化 + label 置換 (`\` `[` `]`) を一度だけ** — field エスケープとの二重適用
     禁止の明記
V15: §5.6 の再利用効果 = 「**text_hash が変わらなかった chunk はそのまま再利用**」の限定表現
     (「99%」の無条件断定の残存 = minor)
V16: 明示操作のブロッキング = **N 秒 (設定値・既定 30 秒)**・タイムアウトは「tick 実行中」の再試行
     可能エラー
V17: §18.2 / §18.3 の vector 共有キー要約 = **(chunk_type, embed_hash)** (embed_hash 単独の残存 =
     minor)
V18: 掲載 SQL の fts_hits = **:fts_cap をサブクエリ内側段で適用** (window (ROW_NUMBER) と同段の
     LIMIT は全一致行を走査してから切る — 内側段の残存欠落 = major regression)
V19: **チャンク規則・フィルタは device-local** — 他 device 由来コピーの再登録では旧規則 chunk が
     残り得る・収束 = 明示一括再チャンク (自動再チャンクはしない) の明記
V20: §13 に **GC の実行点 = tick の step 5 以降** (§21.3 手順 5 の注記と同一) の明記
```

### 出力フォーマット

報告は 3 部構成とする。

**第 1 部 — 回帰確認 (C9、圧縮報告可)**: A01〜A24、B01〜B18、D01〜D14、E01〜E06、F01〜F27、
G01〜G02、H01〜H30、I01〜I38、J01〜J20、K01〜K26、L01〜L28、M01〜M29、N01〜N45、O01〜O30、
Q01〜Q37、R01〜R29、S01〜S29、T01〜T18、U01〜U24、V01〜V20 の全 494 項目を判定する (C9 の
superseded 対応表の旧項目は「superseded (→##)」と記して新項目側で判定)。**fixed / superseded の
項目は ID の列挙のみでよい** (例: 「A01〜A24 / B01〜B18 / … すべて fixed」)。それ以外
(partially-fixed / not-fixed / regression) が出た項目だけを次の表で詳細報告する:

```text
| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
```

**第 2 部 — 探索ログ (C12。監査の中核)**: 実行した**全シナリオ (78 以上、X1〜X78 の各観点で
最低 1 つ + 自由探索。重心は X75〜X78)** を、問題が出なかったものも含めて列挙する
(X15 / X20 / X24 / X30 / X35 / X40 / X45 / X50 / X61 は「主張・試行・破れたか」を記録):

```text
| # | 観点 (X# / 自由) | シナリオ (初期状態 → 操作列) | 結果 (問題なし / W## を検出) |
```

このログが 78 件未満、または未実行の X 観点がある場合、その監査報告は**無効**である
(判定を出してはならない)。

**第 3 部 — 新規検出 (C1〜C8, C10, C11, C12)**: ID は **W01 から採番** (A〜V は使用済み。
**P は原則番号 P1〜P16 と衝突するため欠番**)。
重大度: **fatal** = データ喪失・復旧不能・課金事故・SQL が動作しない、
**major** = 不整合の発生・原則との矛盾・実装不能・両立不能、
**minor** = 表記ゆれ・参照ミス・曖昧 (実装者が安全側に倒せる)、
**proposal** = 再現シナリオを構成できない改善案。
**C12 起因の指摘は「再現シナリオ」列を必須とする**:

```text
| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 (P#/C#/X#) | 修正案 |
```

**第 4 部 — 確認済みの列挙**: 検出 0 件だった検査観点 (C1〜C12) と原則 (P1〜P16) を
「確認済み」として明示的に列挙する。

### 合格基準 (報告の冒頭に判定を明記する)

```text
前提条件       : 探索ログが 78 シナリオ以上あり、X1〜X78 に未実行の観点が無いこと。
                 満たさない報告は無効 (判定を出さない)
合格           : C9 の 494 項目がすべて fixed または superseded (対応表どおり)、かつ
                 新規検出 (W) に fatal / major が 0 件
条件付き合格   : C9 が上記を満たし、新規検出が minor / proposal のみ (列挙の上で宣言してよい)
不合格         : 上記以外 (not-fixed / regression が 1 件でもある、または fatal / major がある)
```

判定は証拠 (§ + 引用 + シナリオ) に基づいて機械的に行い、温情判定・様子見判定はしない。
探索で何も出なかった場合も「どのシナリオを実行して出なかったか」で沈黙と区別する。
**判定語は「合格」「条件付き合格」「不合格」の 3 語のみを用い、報告の 1 行目に単独で記す**
(英語・独自語彙・両論併記は不可)。**重大度も fatal / major / minor / proposal の 4 語のみ** —
「情報」等の新造語は無効 (問題不成立と判断した検討は第 2 部の探索ログの「問題なし」行か第 4 部に
記し、第 3 部には載せない)。**出力は監査報告書 (読了証明 + 第 1〜4 部) のみとする** —
作業ログ・状態要約・次アクション提案・引き継ぎメモ等の混入は報告を無効にする (**「## Objective」
「## Important Details」「## Work State」「## Next Move」「How would you like to proceed?」等の
セクション見出し・対話文の出力自体を禁止** — これらが 1 つでも含まれる報告は無効)。**C9 で not-fixed /
regression を主張する場合は該当箇所の「両側」(規範文と、その再掲・要約・掲載 SQL・DDL コメント) を
必ず引用で証明する** — 片側だけ見た regression 主張は r16 で 4 件が誤読として却下されている。

### 対象文書

対象文書は本プロンプトと**同じディレクトリの `target.md`** (docs/research/folder-history-sqlite-design.md
の複製)。read ツールで offset を進めながら**全行を省略なく読了する**こと — 冒頭・末尾の拾い読みは
禁止。**読了の証明として、報告の 1 行目 (判定) の直後に「target.md 全 N 行を読了 — 最終 2 行: 『(最後から
2 行目の内容)』『(最終行の内容)』」を 1 行で記載する** (最終行がコードフェンス等の非コンテンツ行でも
文字どおり引用する — 2 行引用は末尾解釈の曖昧性を消すため)。証明が無い・行数や引用が実物と不一致の
報告は無効。
**read 以外のツール (bash / write / edit / task 等) は使用禁止** — 検証は静的分析のみで行う (C2 の
SQL 検証も静的でよい)。作業ディレクトリ外のファイルへのアクセスは禁止。
