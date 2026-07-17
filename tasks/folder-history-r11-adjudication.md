# folder-history 設計書 r11 監査 — 裁定 (adjudication)

対象: `docs/research/folder-history-sqlite-design.md` (r10 適用済み・2,320 行)
裁定日: 2026-07-15
入力: 6 系統の r11 監査結果 (5 不合格 / 1 合格)

## 系統の識別

| 略号 | 系統 | 判定 | 新規検出 |
|---|---|---|---|
| A | 50 シナリオ・15 サブエージェント (SQLite 3.53.2 + sqlite-vec 0.1.9) | 不合格 | fatal 10 / major 18 / minor 7 (M01–M35) |
| B | 42 シナリオ | 不合格 | fatal 2 / major 12 / minor 5 (M01–M18) |
| C | r11-sonnet (58 シナリオ・BG エージェント併用) | 不合格 | major 2 + minor 10 + proposal 6 |
| D | Fable 52 シナリオ (SQLite 3.51.0 実機) | 不合格 | fatal 1 / major 2 / minor 6 (M01–M09) |
| E | 47 シナリオ | 不合格 | fatal 1 / major 12 / minor 5 (M01–M18) |
| F | 独立セッション 42 シナリオ | **合格** | minor 2 のみ |

集約判定: **不合格**。F の「合格」は他 5 系統が独立検出した実欠陥を取り逃した過小検出 (F の minor 2 も既知 = item-failure 記帳 [下記 K] と PREPARED new_id 判定 [M-d に包含])。C9 は 5 系統とも「L28 partially-fixed + L20 regression 系」で概ね一致。

芯: r11 の重心予想どおり、fatal は **r9/r10 の fix どうしの相互作用**で開いた (close 経路の課金記帳の非冪等 × ledger UNIQUE)。「fix が開ける穴」定番脈 12 例目。発生源は §9.1 状態機械の本体からさらに外周 (close 経路の記帳冪等性・fork 回復・detached) へ移動。

---

## FATAL (採用 1)

### F1 — close 経路の課金記帳が非冪等で ledger UNIQUE と衝突し close Tx が恒久 abort
- 検出: **D-M01 (fatal・SQLite 実機再現)**, A-M10 (major)
- 該当: §9.1 L879–881「UNIQUE … が ledger の二重計上を構造的に防ぐ」/ L906–910 terminal 記帳 / L945–947 reconcile close 付随処理 (b)
- 事象: 同一 (repo, kind, target_key, submission_seq) への 2 回目の**素朴 INSERT** が UNIQUE を撃つ。UNIQUE は「abort で防ぐ」ため、記帳と state 更新が同一 Tx の close は毎 tick abort → 行が state=3・成果ありのまま脱出不能。
- 再現 (D): profile A で成果あり (seq=1) → B へ変更・再投入 (seq=2) → job 完了前に A へ戻す → collect が profile_changed で state=3 + 記帳 (seq=2) → 次 tick reconcile が成果あり (embeddings=A=現行) を検出し close + 付随処理 (b) で**再記帳 (seq=2)** → UNIQUE 衝突 → 恒久ループ。
- **裁定: 採用 (fatal)**。修正: close 経路の全記帳 (collect 成功 / terminal 化 / reconcile・submit close / client_exhausted / detached) を **`INSERT ... ON CONFLICT(repository_id,kind,target_key,submission_seq) DO NOTHING` (冪等追記)** と明文化。追記専用の意味論と両立 (同一 seq = 同一課金事実の再観測)。L879–881 の「防ぐ」も「衝突は同一課金の再観測として黙って吸収」に改める。→ **K (item 失敗記帳)・下記 minor L も同じ冪等化で同時に閉じる**。

---

## MAJOR (採用 12)

| ID | クラスタ | 検出系統 | 該当 | 修正方針 |
|---|---|---|---|---|
| M-a | §21.2「state=0 は即削除」が §9.1 detached 分岐と矛盾 (課金・upload handle 喪失) | B-M01, E-M01 (+C9 L04/L21: A/B/E) | §21.2 L2150 | 「state=0 は即削除」を削除し §9.1 の client/server 分岐 (client=terminal 記帳後削除 / server=照合・採用・照合不能なら保持) を唯一の正本にする |
| M-b | app_config DDL コメントが旧単一 key `agg_embedding_profile_hash` のまま (building/ready 2 key・retry_not_before 未反映) | B-M04, C-M01, D-M09, E-M04 (+C9 L09/L28) | §9.1 L760–763 | コメントを `tool_profile` / `embedding_profile` / `retry_not_before` / `agg_building_profile_hash` / `agg_ready_profile_hash` に更新 (lower hex64 明記) |
| M-c | §13 fsck「旧 profile 破損 → §5.3 明示再生成」が embedding に誤適用 (L20 regression) | A-(H27/L20), B-M05, D-M05, E-M05 (+C9 L20) | §13 L1572–1573 | 誘導を kind 別に: tool は §21.6 drop-derivation、embedding は embeddings 行削除→re-embed (後段 L1588–1591 が唯一の正)。§5.3 の汎用誘導は tool 限定 |
| M-d | fork 中断中のフォルダ移動で「journal 無=手順4中間」が誤発火し未完 fork が通常運用へ復帰 | A-M23, D-M02, E-M10 (+ B-M11 flag realpath) | §21.3 L2211–2214 | (1) flag 掃除は「journal 無」に加え **realpath に .folder-history 実体が現存**を要件化 (実体ごと不在=移動→保留)。(2) §20.4 の再発見 (root_path 更新) は fork_in_progress の old/new id を対象外。(3) 回復再開位置は phase に加え実状態を確認 — **commits 非空なら手順1から** (手順1は冪等) |
| M-e | detached server 採用 (L928) が seq/attempts/submitted_at 増分未指定 → close で ledger UNIQUE 衝突 | B-M03, E-M03 (+C9 K07) | §9.1 L927–928 | 通常 intent 採用と同一 UPDATE (state=1 + batch_job_id + attempts+1 + submission_seq+1 + submitted_at) を明記 (profile snapshot は不変) |
| M-f | §8(i) client 前計上のフィールド列挙が profile_hash / profile_record を欠く → kind=2 CHECK 違反・§5.7 保存不能 | C-M02 | §8 L639–641 | (i) の列挙に「相1 の snapshot 書込 (profile_hash = 現行 / profile_record = 現行 record)」を追加 (「相1と相3の統合」の実体) |
| M-g | delete 直前の最終 stat「存在すれば中止」が §20.4 の三値 (対象外型=absent) と不整合 → 対象外型への置換を永久 delete 不能 | A-M20, B-M06, E-M06 | §20.5 L2005–2007 | 最終確認を walk と同じ lstat+O_NOFOLLOW+regular 判定に。regular で readable なら中止 (skipped=保留)、対象外型・不在は absent のまま確定 |
| M-h | ready 更新が「全フォルダ」の集合・完了追跡を未定義 + 半充填/同一 profile agg_vec 欠落を検出しない | A-M13/M14, B-M07/M18, D-M03, E-M07/M18 | §8-e L617–626, §9.3-c | (1) ready 更新条件を「missing/fork 中でない**接続フォルダ**すべてが building profile で §9.3-c 完了 (= 現行 embedding の被覆 & agg 複製の差集合が空)」に限定・sync_state で宣言的追跡。(2) agg_vec を agg_embeddings から**差集合冪等再充填** (§8-c のローカル版と同型)。(3) fsck (§13) が agg 差集合を検査。agg 意味論=接続フォルダの和 |
| M-i | vec0 DDL が `distance_metric=cosine` 固定・§8-c は次元照合のみ → profile の距離変更が反映されない | B-M09, E-M09 | §8-c L605–610, §5.6/§9.2 vec0 | §8-c/§8-e の vec 再作成条件を「次元**または距離**の不一致」に拡張。vec0 DDL の distance_metric は profile record の値から展開すると明記 |
| M-j | register 再発見が「対象 root_path が既に別 repo-id の folders 行に属す」を検査せず二重登録 | B-M12, E-M11 | §21.1 手順1 | 再発見の INSERT 前に正規化 root_path の既存行を照合し、別 id なら §9.3-d で先に退役 (root_path は 1 実体 1 行 — damaged 再登録 L2130–2133 と同型) |
| M-k | opt-in 画像フィルタの設定値が永続化されず app 全損 bootstrap で復元不能 | B-M13, E-M12 | §8 L654–660, §21.5 | filter record/hash を app_config に永続化し bootstrap で再入力 (規約 7-f の損失一覧・§21.5 に追加)。再入力後に全派生を再チャンク |
| M-l | register 手順1「開けるなら再発見」が一時読取不能 (AV/EIO) を damaged 扱い → 破壊的再初期化で履歴喪失 | A-M21 | §21.1 手順1 / L2128–2130 | existence と readability を分離 (§13 の「読めない≠壊れている」を register にも適用)。一時失敗は無変更で保留・status、readable だが構造破損のみ damaged |

---

## MINOR (採用 ~11)

| ID | 内容 | 検出 | 該当 | 修正 |
|---|---|---|---|---|
| K | terminal 記帳列挙に item 失敗が無い (課金するプロバイダで台帳欠落) | A-M04, D-M06 | §9.1 L887/906 | 列挙に item 失敗を追加 (NULL+estimated・F1 の冪等追記と併用) |
| L | collect の Retry-After が tick 跨ぎで永続化されない (submit 側のみ) | A-M29, B-M18, E-M17, D-I10 | §9.1 L870–872 | collect も provider 別 retry_not_before を永続化 |
| M-16 | §16「突合には batch_job_id を使う (§9.1 の既知の残余)」の参照が陳腐化 (残余は L950 で解消済) | A-L03, D-M04 | §16 L1717 | 「(§9.1 — ledger は記録できた課金、最終正はプロバイダ)」へ書換 |
| N | chunks の seq/char_start/char_end に非負・順序 CHECK が無い | B-M16, E-M15 | §5.4 | `CHECK(typeof(seq)='integer' AND seq>=0)` / `CHECK(char_start>=0 AND char_end>=char_start)` |
| O | agg_file_versions に §5.2 の event/content/size 複合 CHECK が無い (削除版が過去版検索に露出) | B-M17, E-M16 | §9.2 | §5.2 L207–212 と同一 CHECK を追加 |
| S | fork journal に canonical encoding / digest が無く構文上有効な改竄を検出できない | A-M24, B-M15, E-M14 | §21.3 L2172/2229 | journal を版付き canonical record + digest で定義し回復時に検証 |
| M-15 | 短語 LIKE fallback が text のみで heading_path を見ない (FTS は両列索引) | A-M15 | §11.2 L1485–1500 | fallback を text OR heading_path に (instr も両列) |
| M-17 | query vector 生成に使った profile を固定せず ready==current 照合 (TOCTOU) | A-M17 | §11.2 L1461–1468 | query_profile_hash を snapshot し ready==query_profile_hash を照合 |
| M-26 | vector BLOB の float32 byte order 未規定 | A-M26 | §5.6 L366 | IEEE-754 float32 **little-endian** に固定 |
| M-35 | `LIMIT :limit` の型・正値・上限契約が無い (SQLite の -1 は無制限) | A-M35 | §11.2 L1441 | :limit を正整数・上限付きとして入力境界で検証 |
| M-30 | query embedding の 429/断/認証失敗時の検索分岐が無い | A-M30 | §11.2 L1461 | 失敗時は FTS-only + status (ready 不一致時と同型) |
| P9 | §5.9... の DDL コメントが監査プロンプトの原則番号 "P9" を参照 (孤立) | C-proposal | §9.1 L727 | 「collect の profile 不一致破棄 (§9.1)」へ直書き |

（任意採用の候補、いずれも低リスク）:
- M-27 (A): alt の `](` エスケープが先行 `]` を残す → alt 中の `\`/`[`/`]` を `\\`/`\[`/`\]` にエスケープ (§6 L489)。
- M-16c (A-M16): 後退検出 (§9.3-z) 時に scan_cache/fp_cache を無効化しない → z 検出時に両 cache を無効化し強制 hash scan を予約 (§9.3-z)。
- M-25 (A): 恒久 invalid payload と一時失敗を区別しない → deterministic invalid は state=3 (invalid_output) + 記帳 (§9.1 L901–905)。
- M-19 (A): 検証済み root を dirfd で固定しない (照合〜使用の TOCTOU) → openat/RESOLVE_BENEATH 相当で root に束縛 (§20.5 ハードニング注記)。

---

## DOWNGRADE / 却下 (理由付き)

| ID | 検出 | 裁定 | 理由 |
|---|---|---|---|
| **G: fork 中 in-flight OCR の二重課金** | A-M03 (fatal), B-M10 (fatal) **対** D-X22 (意図されたトレードオフ) | **係争 → 要ユーザー判断** | fork は派生台帳を保持 (L2190) するため、成果ありの content は再投入されない。二重課金は **fork 時点で in-flight (成果なし) の job に限定**され、(a) 旧 detached job は payload 破棄でも ledger に記帳=追跡済み、(b) 有界、(c) fork は稀な明示操作、(d) §18.6 の per-repository 課金モデルと整合。構造修正 (旧 job の new_id への re-home) は detached モデルを複雑化する。→ 「§21.3 に有界の意図されたコストとして明記」を推奨。構造修正を望むなら別途。 |
| R1-M01: unregister に退役 tombstone が無く再発見で再登録 | A-M01 (fatal) | **降格 (doc 明確化)** | 退役事実の喪失は既に規約 7-f・§21.5 L2284 で「意図された損失」として明記済み。再発見は marker=規約 9 の証拠による復帰で、**再 OCR 課金は発生しない** (派生保持・content-addressed)。「意図しない課金」の前提は OCR には当たらない。→ §21.2 に「active watch_root 配下の unregister は次 walk で再発見・再登録される (marker=規約 9)。恒久停止は watch_root 除外か移動後 unregister」と 1 行補足。 |
| M-32: agg 側 DDL block 単体に view/FTS/trigger が無い | A-M32 | **却下** | §9.2 L1089–1091 が「§5.5 と同一定義 — 表名・rowid 名の読み替えで適用」と**明示的な代入規約**を置いており、一意に再現可能。「省略なし」は実表 DDL を指し、読み替え規約は別途明記済み。 |
| M-31 code fence / M-33 §2 要約 / M-34 cross-volume case / M-18 NFC 逆解決 / M-28 read-only 規約12 / M-22 drop+backfill | A / A / A / A / A / A | **保留 (低優先 minor)** | いずれも単一系統・周辺エッジ。M-28 (standalone read の規約 12) と M-18 (restore の logical→raw 逆解決) は一定の妥当性があり将来ラウンドで再評価。今回は本命クラスタを優先。 |

---

## 適用範囲の提案

- **必須**: F1 + M-a〜M-l (fatal 1 + major 12)
- **推奨**: 上表 minor 採用分 (K, L, M-16, N, O, S, M-15, M-17, M-26, M-35, M-30, P9) + 任意候補 (M-27, M-16c, M-25, M-19)
- **明記のみ**: G (係争), R1-M01 (降格)
- **保留**: M-31/M-33/M-34/M-18/M-28/M-22, M-32 却下
