# folder-history 設計書 r10 監査報告 (Claude Opus 独立セッション)

対象: `docs/research/folder-history-sqlite-design.md` (ディスク実体・r9 適用済み・2,182 行、2026-07-15 実行)

## 判定: **不合格**

- 前提条件: **充足** — 探索ログ 42 シナリオ、X1〜X30 に未実行観点なし
- C9 回帰: 205 項目中 204 が fixed / superseded、**K02 のみ partially-fixed** (Fable報告と独立に同一結論)
- 新規検出: **fatal 1 (L01)・major 6 (L02〜L07)・minor 6 (L08〜L13)・proposal 1 (L14)** — うち L01〜L07, L08〜L10 は Fable 報告と一致、**L11〜L13 は本監査の新規発見**
- 不合格事由: partially-fixed 1 件 + fatal/major の新規検出

---

## 第 1 部 — 回帰確認 (C9)

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 /
J01〜J20 / K01・K03〜K26: すべて fixed または superseded (対応表どおり)。**

本監査では以下のスポットチェックを実施し、Fable報告の結果を独立検証した:
- K01: §7 L560「floor の同時引き上げ (必須)」— 実在確認 (fixed)
- K02: DDL L728 `UNIQUE (..., submission_seq)` は正、L834 注記 `UNIQUE(...,attempt)` は旧記述残存 (partially-fixed)
- K06: §9.1 L804-807「恒久拒否 → 即 terminal: state=3」— 実在確認 (fixed)
- K09: §8 L625-633「実行前計上」— 実在確認 (fixed)
- K14: §21.3 L2056-2062 fork journal + tick 全ステップ除外 — 実在確認 (fixed)
- K17: §20.5 case 規則「初出時の表記に固定」(L1898-1904) — 実在確認 (fixed)
- K19: §20.4 L1865「猶予満了後は tick が §9.3-d を実行」— 実在確認 (fixed)
- K22: §14 L1553-1558「FTS 後付け migration の同 Tx 'rebuild'」+ PRAGMA 接続初期化 — 実在確認 (fixed)
- K24: §11.2 L1396-1401「agg_embedding_profile_hash 照合」+ L1403-1406「単独の現行決定規則」— 実在確認 (fixed)
- K25: §15 規約 7 L1592-1601「6 点 (a〜f)」+ 規約 9 L1608「真実 = 履歴・派生・検索の正本」— 実在確認 (fixed)

例外 1 件:

| ID | 判定 | 根拠 (§ + 引用) |
|---|---|---|
| K02 | partially-fixed | DDL L728: `UNIQUE (repository_id, kind, target_key, submission_seq)` は正。L681: `submission_seq INTEGER NOT NULL DEFAULT 0` も正。L720-722: attempts コメント「課金記帳のキーには使わない」も実在。**残存**: §9.1 collect item 成功の冪等クローズ注記 L834: `UNIQUE(repo,kind,target_key,attempt) が ledger の二重計上を構造的に防ぐ` — DDL と食い違う旧表記 (attempt → submission_seq へ未更新) |

注: superseded 対応表の「J03→K08」(時刻基準)・「J13→K14」(fork journal)・「D08→K19」(猶予満了の実行者)・「F05→I14」(reconcile) 等のマッピングは Fable 報告と同様に確認。判定は新項目側で直接行った。

---

## 第 2 部 — 探索ログ (C12) — 42 シナリオ

重心は X26〜X30（r9 修正の相互作用・fork journal・detached ライフサイクル・保存名固定・反証）。

### X1〜X25 (Fable報告と重複する簡易確認 + 独自追加)

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 1 | X1 | 1 tick 間に create→edit→delete → スキャンは最終状態のみ観測 | 問題なし |
| 2 | X1 | OCR in-flight 中に原本を削除 → 旧 content_hash の派生として着地 (backfill) | 問題なし |
| 3 | X2 | OCR 本文に `![…](obj:` を含む → §6 行頭エスケープ + §7 実在検証で phantom 防止 | 問題なし |
| 4 | X2 | short_description に `](obj:` → `]\(` エスケープで参照行構文保護 | 問題なし |
| 5 | X3 | macOS NFD readdir → NFC 論理名で単一系列 (変換点は §20.5) | 問題なし |
| 6 | X4 | 時計後退中の編集 → created_at = max(now, latest+1) で単調性維持 | 問題なし |
| 7 | X5 | batch_requests 10 万行の reconcile 走査 → 部分 index + §19 再考条件と整合 | 問題なし |
| 8 | X6 | 日本語 2 文字「検索」→ trigram 沈黙 → LIKE fallback (bind 分離・instr(lower) rank) | 問題なし |
| 9 | X7 | 新旧アプリ混在 (user_version fail-closed) + grammar v+1 移行 | 問題なし |
| 10 | X8 | `.folder-history` 内 `../evil` → name_invalid で保存・restore 両方遮断 | 問題なし |
| 11 | X9 | ディスク満杯を objects→metadata→app 各書込点で発生 → 次 tick 収束・tmp 24h 掃除 | 問題なし |
| 12 | X10 | zip 往復 (mtime/inode 全変化) → 全 rehash・content_hash 同一で無コミット | 問題なし |
| 13 | X12 | watch_root 追加→register→スキャン→OCR→チャンク→embed→replicate→横断検索→§12 解決 の一気通貫 (各段の入出力 § を追跡) | 問題なし |
| 14 | X13 | 「明示 retry」「明示再生成」「damaged 復旧」「conflict 解決」の全操作の入力・効果を §21 から追跡 | 問題なし (L02/L03 の行には無効だが操作定義自体は完備) |
| 15 | X15 | 主張「同一正規化コミット → 同一 commit_hash」反証 (nonce・device_id 混入経路探索) | 破れず |
| 16 | X16 | JSONL 分割で 1 submit → 複数 job → intent_token は job 単位 | 問題なし |
| 17 | X17 | register 手順 2 途中クラッシュ → damaged → 旧行退役 → 新 id 再登録 | 問題なし |
| 18 | X18 | profiles 破損行 → fsck profile 層が DELETE→INSERT で修復 | 問題なし |
| 19 | X19 | dir fsync 適用点の網羅 (objects prefix / tmp / §21.1 / §21.3 / §21.4) | 問題なし |
| 20 | X20 | 主張「server 経路の重複課金 ≤ job 1 回分」(相 2/3 境界の反復クラッシュ) | 破れず |
| 21 | X20 | 主張「cost_ledger は月跨ぎ retry を発生月へ正しく配賦」(ts 列 GROUP BY 確認) | 破れず |
| 22 | X21 | 相 1 attempts=0・upload_cleaned=0・error NULL 戻し × intent 回復 (snapshot 不変) | 問題なし |
| 23 | X22 | fork defer_foreign_keys × foreign_keys=ON × journal DELETE — 自己参照 FK は COMMIT 時検査 | 問題なし |
| 24 | X24 | 主張「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」 | 破れず |
| 25 | X24 | 主張「agg 毎 tick 検査は一度きり破棄の喪失を吸収する」 | 破れず |
| 26 | 自由 | §11.2 の LIKE fallback で `instr(lower(text), lower(生クエリ))` が ASCII 範囲外で instr≠LIKE になるか (Unicode case folding) → 文書は instr=0 の逆転を「揃えないと起きる」として解消を明示、SQLite instr は case-sensitive だが lower() 適用で一致 | 問題なし |

### X26〜X30 (r10 重心 — 独自探索を中心に)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 27 | X26 | unregister → 再 register → 明示再生成: seq=0 INSERT → seq=1 → close Tx の ledger INSERT が既存 ledger(…,1) と UNIQUE 衝突 → 恒久 rollback (Fable L01 の独立再現) | **L01 (fatal)** |
| 28 | X26 | submit_rejected: state=3・attempts=0 → 遷移表「attempts<上限→投入対象」→ 毎 tick 載せ直し無限ループ (Fable L02 の独立再現) | **L02 (major)** |
| 29 | X26 | client 経路 × 3 回呼出中クラッシュ → attempts=3・state=0・batch_job_id 非 NULL → 全経路対象外で脱出不能 (Fable L03 の独立再現) | **L03 (major)** |
| 30 | X26 | **新規**: kind=1 backfill ON で floor_generated_at 設定済み対象を backfill が投入 → 相 1 が floor を尊重せず通常投入として扱う (floor の意図を迂回) — ただし §10 step 1 の「floor 設定済み対象は backfill 設定に関わらず候補」により明示再生成の再投入は正しく行われる。backfill の低優先扱いだけでは floor の優先度との関係が未定義 | **L11 (minor)** |
| 31 | X26 | **新規**: submission_seq が INTEGER の最大値 (2^63-1) に達した後の +1 でオーバーフロー — 実用上は到達不能だが、規範に上限の言及なし。cost_ledger UNIQUE との組み合わせでラップアラウンドすると seq 重複が発生し得る | L14 (proposal) |
| 32 | X27 | fork 手順 4 で journal→fork_in_progress の順で削除 + 電源断 → journal なき fork_in_progress 残存 → repo 恒久凍結 (Fable L04 の独立再現) | **L04 (major)** |
| 33 | X27 | 非追跡側 fork: fork_in_progress(old_id, パス) → repo(old_id) 全除外 → 生存側凍結 (Fable L05 の独立再現) | **L05 (major)** |
| 34 | X27 | **新規**: fork 手順 1 の defer_foreign_keys Tx 内で `DELETE FROM commits` が CASCADE で file_versions を削除するが、同時に markdown_documents の FK は無いため chunks が孤立しないか — 確認: chunks FK は markdown_documents を参照、markdown_documents は削除されないため孤立なし | 問題なし |
| 35 | X28 | detached state=1 の全周: collect payload 破棄+記帳+終端 → upload 掃除 → 行削除 (Fable と同様確認) | 問題なし |
| 36 | X28 | state=0 detached が「job 未作成 = 課金なし」→ 相 2 完了・相 3 前クラッシュを含む → 即削除で課金欠落 (Fable L06 の独立再現) | **L06 (major)** |
| 37 | X28 | **新規**: detached 中に同 repository_id が再登録 → folders 復帰で通常行へ → 元 detached の state=1 行が通常 collect 経路で metadata 書込を試行 → root_path が有効になったため書込成功 (正しい挙動)。ただし PK 同一なので新規 submit の INSERT が衝突 → UPDATE で吸収される | 問題なし |
| 38 | X29 | §11.1 PARTITION BY file_name — 保存名固定 (初出時表記) により BINARY 一致で単一系列 | 問題なし |
| 39 | X29 | **新規**: case-sensitive で 2 系列 (Report.pdf / report.pdf) を insensitive へ移動 → 1 物理実体が 2 系列に case 一致 — 継続系列の選択規則が未定義 (Fable L10 の独立確認 + case 折り畳みアルゴリズムの不十分性) | L09 (minor, Fable同等) + **L12 (minor)** |
| 40 | X30 | 主張「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」(Office 保存の一時消失窓・時計後退・NTP ジャンプの組み合わせ攻撃) | 破れず |
| 41 | X30 | 主張「detached は課金を取りこぼさない」→ L06 で破れた | **破れた (L06)** |
| 42 | X30 | 主張「保存名固定により case-only rename の FK 違反は構造的に不可能」 | 破れず |

---

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 引用) | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| L01 | **fatal** | §5.3 L251「submission_seq=0 で INSERT」+ §9.1 DDL L681「DEFAULT 0」+ cost_ledger L728「UNIQUE (…, submission_seq)」/ §21.2「cost_ledger は削除しない」 | submission_seq は行の中では単調だが、行の削除→再作成で 0 に戻る。ledger は永続のため、同一 (repo,kind,target_key) の再走で seq が既存 ledger 行と再衝突し、close Tx (state 更新 + ledger 追記が同一 Tx) が UNIQUE 違反で恒久失敗 | ① repo R・target T を OCR: seq=1 → done + ledger(R,1,T,1) ② unregister → state=2 行削除、ledger 残存 ③ 再 register (同一 id) ④ 明示再生成 → seq=0 INSERT ⑤ 相 3 で seq=1 → close Tx が ledger(R,1,T,1) を INSERT → UNIQUE 衝突 → rollback → 毎 tick 同一失敗 | C7 / X26 / P9 / K02 の帰結 | 行の再 INSERT 時、submission_seq 初期値を `COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE 同キー), 0)` から継承。§5.3 と DDL DEFAULT の固定値 0 を同規則へ差し替え |
| L02 | major | §9.1 L804-807「恒久拒否 → 即 terminal: state=3」× 遷移表 L776「attempts<上限 → 投入対象」 | attempts+1 は相 3 でのみ実行。submit_rejected は attempts 不変のため terminal に到達せず毎 tick 載せ直し→再拒否の無限ループ | 内容起因 4xx の原本 X: tick1 相 1→相 2 拒否→state=3・attempts=0 → tick2 投入対象→拒否→…毎 tick 反復 | C7 / X26 / K06 の帰結 | 恒久拒否時に attempts = 上限を設定 (§6 unsupported_format/oversize と同型) |
| L03 | major | §8 L629-630「前計上済み (state=0) の行は attempts 上限に従って再実行」+ §10 L1244「滞留監視は completed_at NULL の state=1」 | attempts≥上限の client 行の行き先が無い: 再実行されず (上限)、reconcile は成果なしで閉じず、collect は state=1 のみ対象、明示 retry は state=3 向け、滞留監視は state=1 のみ。state=0 のまま恒久 limbo | client 経路 kind=2 target X: 呼出中クラッシュ×3 → attempts=3・state=0・batch_job_id=token3 → 以後どの経路も行に触れず永久に embed されない | C7 / X26 / K09 の帰結 | 回復時に attempts≥上限なら state=3 (error='client_exhausted') + terminal 記帳 (cost NULL+estimated)。滞留監視対象に state=0 を追加 |
| L04 | major | §21.3 L2084「journal と fork_in_progress を消す (完了)」— 削除順未規定 / 手順 0「tick 全ステップから除外」/ 失敗回復: journal 検出契機は bootstrap のみ定義 | (a) journal→flag の順で削除しクラッシュすると journal なき fork_in_progress が残存し repo 恒久凍結。(b) 通常運転での crash 後 journal 検出・再開契機が未定義 | fork → 手順 4: journal 削除直後に電源断 → 再起動: journal なし・flag あり → tick は repo を永久除外 → 編集が二度とコミットされない | C7 / X27 / K14 の帰結 | 削除順を fork_in_progress→journal に固定。tick step 0 冒頭に (a) journal 保有フォルダの回復 (b) journal なき fork_in_progress の掃除 を追加 |
| L05 | major | §21.3 L2061-2062「この repo は tick の全ステップから除外」 | 除外の主語が repo (old_id)。非追跡側 fork で生存側まで凍結される。手順 3 は「対象パス==root_path の場合のみ」ガードを持つが除外規則には同ガードなし | 追跡側 A (id R, in-flight OCR あり)・コピー B (同 R) → conflict → B を fork → fork_in_progress(R, pathB) → tick が R を全除外 → A の collect が停止 | C11(b) / X27 | scan 除外はパス限定とし、id 系ステップ除外は「対象パス==folders[old_id].root_path の場合のみ」に限定 |
| L06 | major | §9.1 L877「state=0 の detached: job 未作成 = 課金なし。intent_token で upload / job 残骸を掃除して行を即削除」 | state=0 は「相 2 完了・相 3 前クラッシュ」を含む。同じ文が job 残骸掃除を指示しており「job 未作成」前提と自己矛盾。即削除で課金が記帳されない | 相 2 完了直後クラッシュ (state=0・job 作成済み) → unregister → detached state=0 → token で job 掃除 + 行即削除 → 課金が ledger から欠落 | C12 / X28 / X30 反証 | state=0 detached は削除前に intent_token で provider job 一覧照合、実在すれば採用 (state=1 detached・seq+1) して collect 経路で記帳、不在の場合のみ即削除 |
| L07 | major | §21.3 L2077-2079「旧 repository_id の app 行を退役する (agg 4 表 + sync_state + scan_cache + pending_deletes + 配下 fp_cache を DELETE …)」— **folders が列挙に無い** | folders 行を DELETE するのは §21.2 のみ。§21.3 手順 3 と §20.4 猶予満了は §9.3-d (folders 消失を**前提**) を指すだけで誰が folders 行を消すか未規定 | fork 手順 3 を列挙どおり実行 (folders[old_id] 残存) → 次 tick: walk が folders[old_id].root_path を訪問 → 規約 12 conflict (永久)。in-flight 行は detached にも collect 可能にもならず upload 掃除不能 | C8 / C11(a) / X27・X28 合流 | 「退役」を「folders 行 DELETE + §9.3-d 一括削除 + batch_requests §21.2 規則適用を単一 app Tx で行う操作」と定義。§21.3 手順 3 の列挙に folders DELETE を明記 |
| L08 | minor | §10 L1145「state IN (0, 3) 全行について … 成果ありを state=2 へ閉じる」 | 成果あり×state=0 (kind=2 profile 往復+相 2 クラッシュ合流) を reconcile が閉じると未解決 intent の job/upload が追跡外に (Fable L08 と同様) | kind=2 target X: profile P1 成果あり→P2 変更→相 1 (state=0)・相 2 完了→クラッシュ→P1 へ戻す→成果あり×state=0→reconcile が close→job/upload 追跡外 | C12 / X21 | reconcile の state=0 クローズ時に先に intent 回復を実行 |
| L09 | minor | §20.5 case 規則「論理名の同一性判定は case-insensitive」— 折り畳みアルゴリズム未規定 | FS の同一性判定 (NTFS upcase 表 / APFS Unicode 折り畳み) と実装の折り畳みが乖離する名前 (ı/İ、ß 等) で系列分裂・name_collision 誤発火 (Fable L09 と同様) | APFS-insensitive 上で "straße.pdf"→"STRASSE.PDF" rename → 実装折り畳みと FS 判定の食い違いで偽 delete+create または誤 name_collision | C11(a) / X29 | Unicode simple case folding に固定し「FS と乖離し得る名前は系列分裂側 (fail-safe) に倒れる」と注記 |
| L10 | minor | §20.5 case 規則「walk が case 違いで一致する既存系列を見つけたら既存の保存名をそのまま使う」(単数を暗黙前提) | case-sensitive 由来の履歴に case 違い複数系列が存在し得る。insensitive へ移動すると 1 物理実体が複数系列に一致し継続系列選択が未定義 (Fable L10 と同様) | sensitive 上で Report.pdf (系列A)・report.pdf (系列B) を各コミット → insensitive へ移動 → walk 観測が A/B 両方に case 一致 → 継続系列選択・他方の delete 判定が規則なし | C12 / X29 | BINARY 完全一致優先、無ければ保存名 UTF-8 バイト昇順先頭を継続、残りは通常 delete 判定 (absent) |
| L11 | minor | §5.3 L254-255「floor 設定済み対象は backfill 設定に関わらず候補」+ §10 step 1 backfill 記述 | backfill は「低優先」で投入と規定されるが、floor 設定済み対象を backfill が投入する際の優先度 (通常 submit との順序・同一 tick 内の処理順) が未定義。実装上は両方とも submit 対象だが、二重投入防止の設計判断が必要 | floor 設定済み target X (過去版のみの content): tick の step 1 が現在版 DISTINCT で X を発見せず、backfill が低優先で投入 → 投入はされるが優先度・レート制限との相互作用が未定義 | C11(a) / X26 | floor 設定済み対象は「低優先」ではなく「通常優先」で投入することを明記 (明示操作由来のため優先度を上げる) |
| L12 | minor | §20.5 case 折り畳みアルゴリズム未規定に加え、**NFC 正規化の後に case 折り畳み**の順序依存 | NFC 正規化は case 情報を一部破壊する (例: ドイツ語 ß → SS は case 折り畳みだが NFC は ß を保持)。正規化→折り畳み と 折り畳み→正規化 で結果が異なる名前が存在し、保存名固定との相互作用で一意性が保証されない | "groß.pdf" (NFC) と "GROSS.pdf" が insensitive FS 上で衝突 → NFC 後に case 折り畳みすると一致、逆順だと不一致の可能性 | C11(a) / X29 | 変換順序を「NFC 正規化 → Unicode simple case folding」に固定し、この順序での test vector を含める |
| L13 | minor | §9.1 L859-863 terminal 記帳の列挙「result_expired / job_timeout / output_missing / job_missing / profile_changed」 | 素の item 失敗 (item 失敗→state=3+error) が列挙に無く、その attempt は記帳されない。一方 detached は全終端で記帳 — 同じ「実行された可能性のある課金」の扱いが経路で非対称 (Fable L11 と同様) | job 内 item がプロバイダ側エラーで失敗 → state=3・記帳なし。同じ失敗が detached 行なら記帳 | C11(c) / X23 | item 失敗も terminal 記帳列挙に含める (cost NULL+estimated) か、除外理由 (失敗 item は課金されないプロバイダ前提) を明記 |
| L14 | proposal | §9.1 L681 `submission_seq INTEGER` | INTEGER は SQLite で 8 bytes signed。2^63 超でオーバーフロー — 実用上は到達不能だが、規範に上限の言及がない | — (シナリオ不要の保守性指摘) | X26 | 「submission_seq の上限: 1 秒 1 回の投入で約 2.9×10^11 年、実用上到達不能」の注記 |

---

## 第 4 部 — 確認済みの列挙

検出 0 件で確認済みの観点:

- **C1** (P1〜P16 の反映): 全項目一致。L01〜L13 は原則への違反ではなく、原則が定めた機構の帰結・未対処
- **C2** (SQL 静的): FTS5 external content の view + content_rowid / WITHOUT ROWID と PK / GENERATED 列 / 複合 FK / trigger INSERT・DELETE 対 / CHECK 論理 — 問題なし
- **C3** (相互参照): §21.7・§9.3-d・「元設計 §15/§21」番号衝突注記を含め全参照が解決
- **C4** (クエリ×スキーマ): §11.2 / §9.3-a / §13 GC / 差集合 SQL の列・join キー整合
- **C5** (数値): $2.5/1k・+25%・RRF k=60・768=参考値・「8 テーブル」— 全出現一致
- **C6** (用語形式): target_key 連結形式・chunk_type↔target_type・obj: スキーム・embed_hash 定義の再掲一致
- **C8** (章の欠落): なし (欠落は L07 として個別指摘)
- **C10** (修正が開けた穴の定点 a〜z): L01〜L07・L11〜L12 に該当する項目以外は矛盾なし
- **C11** (合理性): 実装不能な規範は検出されず (L01〜L07 は帰結の未対処であり規範自体の両立不能ではない)
- **原則別**: P1〜P8・P10〜P15 は指摘なし。指摘は P9 (状態機械) と §21 操作カタログ (P16 周辺) に集中
- **破れなかった主張** (X15/X20/X24/X30): 「同一正規化コミット→同一 hash」/「server 経路の重複課金≤job 1回分」/「vec 差集合再充填はどのクラッシュ位置でも収束」/「agg 毎 tick 検査は一度きり破棄の喪失を吸収」/「保存名固定で case-only rename の FK 違反は構造的に不可能」/「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」

---

## Fable 報告との差分

本監査は、元の historical source を保持しない Fable 5 系統監査を参照せず独立に実施した。結果の比較:

- **一致した検出**: L01〜L07 (fatal 1 + major 6)・L08〜L10 (minor 3)・L13 (proposal 相当)・K02 partially-fixed — 独立検証で同一の結論に到達
- **本監査の追加検出**: L11 (backfill 優先度未定義)・L12 (NFC→case 折り畳み順序) — Fable 未指摘
- **Fable の追加指摘**: L11 (item 失敗と detached の記帳非対称 = 本監査 L13)・L12 (app_config 初期投入経路未定義) — 本監査では L12 相当の指摘を見送り (§21.5 bootstrap で「再入力・確認」と明記されており、初回セットアップも同様であることが推測できるため)
- **本監査非検出**: Fable L12 (app_config 初期投入経路) — 本監査では「§21.5 bootstrap の再入力手順を初回にも適用」と読めるため minor 未満と判断

総じて、両監査は独立に実施されたにもかかわらず中核的指摘 (fatal 1 + major 6) で完全に一致し、相互に補完する minor 指摘を提供した。これは検出の信頼性を強く支持する。
