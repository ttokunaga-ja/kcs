# folder-history 設計書 r16 クロスシステム最終裁定記録

- 日付: 2026-07-17
- 対象: `docs/research/folder-history-sqlite-design.md` (裁定前 3,039 行 → 適用後 3,135 行)
- 監査プロンプト: `tasks/folder-history-design-audit-prompt.md` (r16 版 2,841 行 — C9=403 項目 A〜R、X1〜X61、新規 S 採番)
- 運用: **初の CLI 並列実行ラウンド** (従来の外部貼付から移行)。codex exec (GPT-5.6 sol Ultra ×3 / terra Ultra ×2) + opencode run (Hy3 / Kimi K2.7 / DeepSeek V4 Flash / Gemini 3.5 Flash ×2)。手法は `~/.claude/skills/multi-model-cli-audit/SKILL.md` に集約済み。
- 名寄せ・裁定: Fable (本セッション)。全争点は設計文書の該当行を直接検証して判定。

## 0. パネル構成と判定分布 (10 系統 + glm 参考)

| 系統 | 報告 | 判定 | 新規検出 | C9 非合格主張 |
|---|---|---|---|---|
| sol1 | r16-sol1.md | 不合格 | fatal 2 + major 8 (S01-S10) | R18 not-fixed |
| sol2 | r16-sol2.md | 不合格 | fatal 8 + major 12 + minor 3 (S01-S23) | L12/M02/R08/R18/R20 partially |
| sol3 | r16-sol3.md | 不合格 | fatal 2 + major 8 (S01-S10) | R08 regression, R18/R20 partially |
| terra1 | r16-terra1.md | 不合格 (FAIL) | major 11 (S01-S11) + 提案 3 | R18/R20 partially |
| terra2 | r16-terra2.md | 不合格 | fatal 3 + major 4 (S01-S07) | M02/R08/R20 partially |
| dsv4 | r16-dsv4.md | 不合格 | major 2 + minor 2 (S01-S04) | Q01/Q02/R02/R04 regression 主張 (**全て誤読・却下**) |
| kimi | r16-kimi.md | 条件付き合格 | minor 1 (S01) | 全合格 (R23 に留保) |
| hy3 | r16-hy3.md | 自己矛盾 (冒頭不合格/末尾合格) | minor/提案 4 (S01-S04) | 全合格 |
| gem-a | r16-gem-a.md | 合格 | 0 | 全合格 (ただし 8 項目無言及) |
| gem-b | r16-gem-b.md | 合格 | 0 | 全合格 |
| glm (参考) | 推論 101KB のみ (`scratchpad/r16/glm.reasoning.md`) | 報告書なし | 曖昧箇所 2 点 (→ m16/m17 に反映) | C9 全合格 (自己申告) |

- glm は V10 (凍結) → V12 (出力上限 32k を推論で消費し `finish:'length'`) → V13 (`--continue` 再開ハング) の 3 連続失敗で打ち切り。V12 の推論テキストは回収し参考入力とした (「max_tokens 空振りは stop_reason 確認 → 簡潔再送」の CLI 版は **length 死したセッションの --continue 自体が不안定**という追加知見)。
- 「**合格系統は過小検出**」**6 例目**: gem-b は 403 項目・61 シナリオ全緑で S 採番 0 件 (C10 は文字列ごと不在)。gem-a は fixed/superseded 列挙に I18-20/N36/Q15-18 の 8 項目が無言及のまま「403 全確認」を宣言、C1-C8/C10/C11 は一括宣言のみ。hy3 は判定ラベル自己矛盾 + 出力末尾にエージェント基盤の作業状態ログが混入。
- fatal 主張 **15 件 → 全降格 0 件** (標準基準: fatal = 恒久停止・データ喪失・SQL 非機能。per-path 恒久停止は r15 M4 deadlock 前例、restore 系データ喪失窓は r14 前例に従い major)。

## 1. 回帰補修 (3 件 — いずれも文書で実在確認、r15 適用の残穴)

| ID | 内容 | 検証 | fix |
|---|---|---|---|
| **R08** (partially-fixed) | §21.2 の括弧内要約「client は terminal 記帳後に削除」が §9.1 detached (a) の段階遷移 (r15 N4) と矛盾 — 同節前段には正しい 3 条件があり、要約だけが旧解釈 | L2756-2757 (旧) 実在 | 「terminal 化 — 削除は 3 条件の段階遷移に委ねる (即削除ではない)」へ書換 |
| **R18** (partially-fixed) | §13 integrity-check が rank 引数なし = label「external content 照合つき」に反し内部整合のみ (sol1 が SQLite 3.51 実機検証: rank=1 のみ posting 欠損で malformed を返す)。**agg 側の「synced_profile_hash NULL 化 + 該当親行 DELETE」も integrity-check が破損箇所を返さないため実行不能** (terra1 S07) | L2022-2026 (旧) 実在 | `INSERT INTO chunk_fts(chunk_fts, rank) VALUES('integrity-check', 1)` (SQLite 3.42+ 注記) + agg 側は folder 同様「同 Tx で 'rebuild'」へ置換 |
| **R20** (partially-fixed) | §11.2 の規範 `c.text IS NOT NULL` (L1915) が後段の差替え SQL (L1942) に欠落 (terra2 が SQLite 実機再現: text=NULL 画像 chunk が 2 文字クエリでヒット) — r15 適用の転記スコープ漏れ | 両行実在 | 差替え SQL に条件追加 + 「差し替え形にも必須のまま残す」を明記 |

**転記漏れ対策の成果と限界**: r16 プロンプトの R01〜R04 再発検査 (r15 補修 4 件の両側確認) は全系統で合格 — 前回漏れの再発は 0。今回の 3 件は「同一規範の**要約・実装例側**への非伝播」という一段深い同型 (規範文は正しく、圧縮表現・SQL 例が旧のまま)。適用後 grep 対象を「規範の再掲対」から「規範 ↔ 要約・掲載 SQL・DDL コメント」まで拡げる (r17 プロンプトに反映)。

## 2. major 採用 (9 件)

| ID | 内容 (fix) | 系統 | 備考 |
|---|---|---|---|
| **M1** | §7 operation record の key が §9.1 許可 key 集合に無い → `'bulk_operation'` を追加 (存在条件 = 一括変換中のみ) + §7 で key 名明示 | kimi S01, sol1 S04, sol2 S13, sol3 S03, terra1 S01, terra2 S01 (6 系統) | **「fix が開けた穴」17 例目** (r15 minor「operation record」が key 契約側に非伝播) |
| **M2** | §21.3 破損 journal 明示解決が §21.1 手順 2 で UUIDv7 新規採番 → flag の new_id と不一致で (a) 規則が掃除不能・journal は除去済みで (b) も不発 → **flag 恒久残留・realpath 恒久除外** (文書自身の着地主張「id=new = 掃除で完了」が不成立) → 手順 (2) は flag の new_id を採用 (id の自己記述化。flag 不在時のみ新規採番) | sol1 S02, sol2 S04, sol3 S02, terra2 S03 (4 系統・全 fatal 主張) | **18 例目** (r14「明示解決」fix の穴)。major へ降格 (per-path 停止 = r15 M4 前例) |
| **M3** | §21.4 restore の raw 不在分岐に保全・再 lstat とも無く、absent 確認後に外部が作った同名ファイルを rename が無痕跡上書き (保全が塞いだ唯一の不可逆喪失経路の不在側) → 不在分岐も再 lstat 義務 (不在→出現 = 不一致) + 可能なら no-replace rename (RENAME_NOREPLACE / RENAME_EXCL / MoveFileEx 非置換) | sol1 S01 (fatal 主張), sol2 S15 (2 系統) | major (r14 restore 再 lstat 前例)。§20.5 の TOCTOU 許容は名前衝突の二重実体のみで内容上書きは対象外と確認 |
| **M4** | 伝播猶予の起点が token 時刻のみ → 相 2a upload が猶予 (10 分) を超えると作成直後の job を「未作成」誤認 (期限内載せ直しは attempts も記帳も消費しない → §10「累積しない」主張を破る) → **batch_requests に job_create_started_at 列を追加**し、相 2b 呼出直前に単独小 Tx で記録・**猶予の起点 = max(token 時刻, 同列)**。NULL = 相 2b 未着手 = job 不存在で常に安全 | sol2 S07, sol3 S01 (fatal 主張), sol1 S09 の一部 (3 系統) | X61 (伝播猶予反証) の勝利。スキーマ変更を伴う唯一の fix |
| **M5** | 未来 skew の判定漏れ: 「5 分超 = 期限超扱い」と「猶予は過去側のみ」の間で token ∈ (now, now+5min] が無保護 (NTP 補正直後に素通し) → 帯域内は unknown 保持 | sol2 S06 (fatal 主張), terra1 S05 (2 系統) | M4 と同一段落で修正 |
| **M6** | 「一覧の正常応答に無い = confirmed-absent」が pagination の全ページ走査を要求していない → 共通則に「全ページ走査完了の応答に限る。部分応答は unknown」を追加 | sol2 S05, terra2 S04 (fatal 主張), terra1 提案 (3 系統) | |
| **M7** | sweep found の未記帳判別が「batch_job_id = 発見 job id」のみ → 期限超 T-記帳 → (掃除前) crash → 遅延可視化 found が J キーで再記帳 = 同一 job の二重記録 → 判別を `batch_job_id IN (発見 job id, 当該 token)` に対称化 | sol2 S08 (fatal 主張) + Fable 自己検証 (dsv4 S02/S03 の問題意識と同根) | **19 例目** (r15 N1 自己記述化の非対称残余)。X57 (自己記述化×dispatch) の勝利 |
| **M8** | §21.2「cancel が確定した行は削除対象」に terminal 遷移・記帳が無く、state=1 のまま token sweep の「全行終端」に入れず token 永久残留・削除ガードと恒久矛盾 + cancel 部分課金の記帳漏れ → cancel 確定 = state=3 (error='cancelled') + completed_at + 冪等記帳、削除は段階遷移 | terra1 S04 + Fable 自己検証 | |
| **M9** | プロバイダ採用条件に「terminal 後の一覧保持期間 ≥ timeout_hours + 結果保持期限 + 猶予 1 日」を追加 — 期限判定の暗黙前提を契約要件化 (可視化**遅延**上限と一覧**保持**下限は独立) | sol2 S20 (fatal 主張) | r15 N2 (採用条件) と同族 |

## 3. minor 採用 (17 件)

| ID | 内容 | 系統 |
|---|---|---|
| m1 | detached (b)「期限内の不存在確認も terminal 化」に伝播猶予内保持の例外を明記 (共通則は既に detached (b) を名指し — 局所言い換えのみ欠落) | terra1 S11 |
| m2 | detached 期限超の列挙に attempts+1 (attached (iii) との鏡写し) | sol2 S09 (fatal 主張→minor) |
| m3 | sweep found 小 Tx に attempts+1 (実在 job = 消費 attempt) | sol2 S10 (fatal 主張→minor) |
| m4 | §10 有界主張に「採用条件を満たす provider に限る」を明記 | sol1 S09 |
| m5 | §6 に Batch 入力形式を明示: JSONL 行 = upload 済み原本の file id 参照 (base64 内嵌不使用)・JSONL 自身の upload も token 埋込 filename で掃除 (upload_id 列は原本用) | sol1 S07/S08 |
| m6 | §10 step 2 の state=1 照会を folders 現存 repository に限定 (detached は冒頭処理のみ) | terra1 S10 |
| m7 | submit_rejected sweep 除外に「拒否にも課金する provider では倒す分岐自体で同一 Tx 冪等記帳 (seq 現値・batch_job_id=token・estimated)」を実体化 (§8 注記の具体化) | sol2 S11, terra2 S07, terra1 S03 |
| m8 | §5.7 の kind 排他を shape 検証で強制 (tool=annotation_schema 必須 / embedding=dimensions・metric 必須) + model は provider/adapter 修飾名 | sol1 S05, sol2 S14+S19, sol3 S09, terra2 S05 |
| m9 | folder 側にも markdown_documents↔chunks 親子件数検査 (agg 側と対称。修復 = §7 再解析でローカル・無課金) | sol1 S06, sol2 S17 |
| m10 | OCR/embedding 投入直前に objects bytes の SHA-256 再照合 (restore と同じ規律 — 週次 fsck の間の窓) | sol3 S07 |
| m11 | §20.5 case 規則に per-directory 感度への備え: 同一 dir 内の case 違い併存 = 当該 dir を sensitive 扱い (evidence override) | sol3 S10 |
| m12 | rebind の action に旧 root_path 配下 fp_cache DELETE (watch_root 解除と同型) | sol2 S22 |
| m13 | Retry-After 無し 429/5xx の既定 backoff (60 秒×連続失敗、上限 15 分) を retry_not_before へ | sol2 S23 |
| m14 | §13 に「同一サイクル内は fsck → GC の順」 | hy3 S04 |
| m15 | §21.3 digest の目的を「部分書込・bit-rot 検出 (悪意ある改竄への耐性ではない)」と正確化 | sol2 S18 (却下→文言調整) |
| m16 | sweep の自己記述化注記に「照合から外れるだけで、batch_job_id 非 NULL 行 (自己記述化済み・client 前計上・detached (a) terminal) も同 token の掃除・NULL 化には含まれ続ける」を明記 | dsv4 S02 (却下→明確化) + **glm-1** (推論回収 — client 行の分岐漏れ読みを 3 周しても白黒つけられず = 文書側の曖昧の証跡) |
| m17 | §10 step -1 の unreadable 分岐に「in-flight collect 非除外例外は metadata を開けない unreadable では実行不能 = 実質 regressed 側のみ」を注記 | **glm-2** (推論回収) |

## 4. 却下 (理由つき)

| 系統 ID | 主張 | 却下理由 |
|---|---|---|
| dsv4 Q01 | §8-c に embedding_profile 参照元の明記なし | L660-661/L684 に「app_config の embedding_profile record から読む」実在 |
| dsv4 Q02 | §9.3-z に除外例外文なし (regression) | L1484 (§9.3-z 側)「処理は除外しない — §10 step -1 と同一の例外」+ L1580 (§10 側) の両側実在。sol2 の両側確認が正 |
| dsv4 R02 | (i)〜(iii') 旧表記の混在残存 | `(iii')` の出現は手順定義 (L1086) の 1 箇所のみ — (iii) と (iv) の間の正当な手順ラベルで、範囲表記の残存は無い |
| dsv4 R04 | §20.5 に「任意の強化」残存で §21.4 と不整合 | L2584-2586 は「in-place restore では義務 (§21.4)。delete 最終確認・fsck では任意の強化」と正しくスコープ済み |
| dsv4 S03 | (b') 小 Tx の部分永続で記帳重複 | 小 Tx = 単一 SQLite Tx でオールオアナッシング — 部分永続の前提が原子性と矛盾 (問題意識は M7 が同根で吸収) |
| dsv4 S04 | submit_rejected の error 値ゆらぎで除外不全 | error 値は本設計が自家採番する canonical 値 — プロバイダ由来のゆらぎは発生しない |
| terra1 S02 | (b') が batch_job_id を書いて state 更新前に crash → dispatch が client 誤分類 | batch_job_id の書込は常に state 遷移と同一 Tx (found 採用 L1048・detached (b) L1216) か全行終端 token の terminal 行のみ (sweep L1180) — state=0 + jobid が生じる経路が本文に無い |
| terra1 S08 | agg_commits/agg_file_versions ミラー非検査 + forward-only cursor で欠落恒久化 | agg は cache — 読める DB 内の沈黙欠落 (bit-rot/手改変) の全数検証は正本側 fsck の脅威モデル外。回復経路 = agg 破棄・再構築が既定 |
| terra1 無番1 | active 行の intent_token NOT NULL をスキーマ強制 | terminal 後の sweep による NULL 化順序と条件付き CHECK が衝突しやすく利得が薄い (提案として保留) |
| terra1 無番3 | cost_ledger append-only の trigger 強制 | 採否は実装裁量 (設計規範は追記専用を既に明記) — r17 で再評価可の提案として保留 |
| sol1 S10 / sol2 S16 | vec の値 (bytes) 検証なしで stale/破損 vector 永続 | 同一 key で vector 値だけ変わる設計上の遷移が無い (embed_hash = 内容 hash・同一 profile で再 embed なし)。破損 = 読める DB 内 bit-rot は fsck 脅威モデル外・cache は再構築可 |
| sol2 S12 | requeue 時の旧 upload 削除不能・upload_id 上書き | L1092-1093 が「失敗は続行 = 既知の残余」+ filename token 埋込による発見手段を明記済み (documented tradeoff) |
| sol2 S21 | retired 状態の永続先が無い | L2767「退役事実の非永続は規約 7-f の明示的トレードオフ」— documented |
| sol3 S08 | decoder 拡張なのに grammar v:1 据え置きで新旧不区別 | encoder は不変 (r15 は decoder 側の対称化) — 保存済み bytes の意味は変わらず、v bump は同一内容の text_hash を無用に変えて全派生を偽無効化する。X60 (対称往復) は 3+ 系統が問題なしと検証済み |
| hy3 S01 | §20.5 手順 1「tmp は破棄」の誤読可能性 | 報告自身が「規範矛盾なし」と認める記述順序の指摘 — 現文で規範は一意 |
| hy3 S02 | vec DDL テンプレの一元実体化保証 | 報告自身が「設計上の不備ではない」と明記する実装注記 |
| hy3 S03 | CHECK 追加等の将来 migration パターン未記載 | 現規範への違反なし — 将来の §14 拡張課題 |

## 5. 適用サマリ

- 文書: 3,039 → **3,135 行** (33 編集 = 回帰 4 + major 16 + minor 13 相当のブロック)
- 適用後検証: fence 80 (偶数) / 「記帳後に削除」「cancel 確定=削除対象」「旧・猶予式 (0 ≤ now − token)」残存 0 / `c.text IS NOT NULL` が規範・差替え両所 / integrity-check は rank 形式 + agg rebuild 化 / bulk_operation ×3・job_create_started_at ×4 で全再掲対が同期
- スキーマ変更: batch_requests に `job_create_started_at INTEGER` を追加 (M4) — 唯一の DDL 変更

## 6. r17 への申し送り

1. **検証リスト (S 採番)**: R08/R18/R20 の補修 + M1〜M9 + m1〜m17 を r17 の C9 検証対象に追加 (特に「規範 ↔ 要約・掲載 SQL・DDL コメント」の非伝播を明示検査 — 今回の回帰 3 件は全てこの同型)
2. **探索重心候補**: (a) job_create_started_at の導入が開ける穴 (小 Tx の順序・requeue 時の残置値・app 全損との相互作用)、(b) error='cancelled' の遷移表・再登録との相互作用、(c) found 判別 IN (J, T) の二重条件が逆に吸収しすぎる経路が無いか、(d) 不在分岐 no-replace rename の各 OS 意味論差
3. **プロンプト整備**: sol1 指摘の Q06 二重出現 (Q05/Q06→R06 と Q06→R07) を正本で確認・整理。terra1 の「FAIL」形式・hy3 の作業ログ混入を受け、判定語彙 (合格/条件付き合格/不合格) と出力体裁の強制文言をスキル §2 の読了証明と併せて強化
4. **CLI 運用**: glm (zai-coding-plan/glm-5.2) は大型監査に不適 (出力 32k を推論が食い潰す)。再挑戦するなら msg2 を「C9 は範囲一括・S のみ詳細」の短出力仕様にするか、パネルから外す
