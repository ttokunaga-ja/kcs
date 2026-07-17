# folder-history 設計書 r10 監査報告 (Claude Fable 5 系統)

対象: `docs/research/folder-history-sqlite-design.md` (ディスク実体・r9 適用済み・2,182 行、2026-07-15 実行)。
引用は全件ディスク実体と grep 照合済み (r4 の stale コピー事故の再発防止)。

## 判定: **不合格**

- 前提条件: **充足** — 探索ログ 50 シナリオ、X1〜X30 に未実行観点なし
- C9 回帰: 205 項目中 204 が fixed / superseded、**K02 のみ partially-fixed**
- 新規検出: **fatal 1 (L01)・major 6 (L02〜L07)**・minor 5 (L08〜L12)・proposal 1 (L13)
- 不合格事由: partially-fixed 1 件 + fatal/major の新規検出

r10 の重心どおり、fatal/major の大半は **r9 修正が開けた穴** (L01 = submission_seq×行ライフサイクル、
L02 = submit_rejected×遷移表、L03 = 実行前計上×上限、L04/L05 = fork journal/除外粒度、L06 = detached 規範) に集中した。

---

## 第 1 部 — 回帰確認 (C9)

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 /
J01〜J20 / K01・K03〜K26: すべて fixed または superseded (対応表どおり)。**

例外 1 件:

| ID | 判定 | 根拠 (§ + 引用) |
|---|---|---|
| K02 | partially-fixed | DDL は正: `submission_seq INTEGER NOT NULL DEFAULT 0` (L681)、`UNIQUE (repository_id, kind, target_key, submission_seq)` (L728)、attempts コメント「課金記帳のキーには使わない」も実在。**残存**: §9.1 collect item 成功の冪等クローズ注記が旧キーのまま —「UNIQUE(repo,kind,target_key,attempt) が ledger の二重計上を構造的に防ぐ」(L834)。DDL と食い違う旧表記であり submission_seq へ未更新 |

プロンプト側の注記 (判定に影響なし): superseded 対応表の「J03→K10」「J13→K16」「D08→K20」は
内容上それぞれ **K08** (時刻基準)・**K14** (fork journal)・**K19** (猶予満了の実行者) を指す番号ずれ。
判定は新項目側で直接行った。

---

## 第 2 部 — 探索ログ (C12) — 50 シナリオ

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|---|---|---|
| 1 | X1 | 1 tick 間に create→編集→delete → walk は最終状態のみ観測、中間版は不生成 (スキャン方式の設計内) | 問題なし |
| 2 | X1 | OCR in-flight 中に原本を編集 → 新 content = 新 target、旧 job は旧 content の派生として着地 (backfill 対象) | 問題なし |
| 3 | X2 | OCR 本文に `![…](obj:` / `<!-- img:` を含める → §6 行頭 `\` エスケープ + §7 実在検証の二層で phantom 不成立 | 問題なし |
| 4 | X2 | short_description に改行・`](obj:` → 1 行正規化 + `]\(` + `--\>` の可逆エスケープで往復無変質 | 問題なし |
| 5 | X3 | macOS NFD readdir → NFC 論理名で単一系列 (fp は raw 名の別層、変換点は §20.5 の 1 箇所) | 問題なし |
| 6 | X3/X29 | case-sensitive で作った 2 系列 (Report.pdf / report.pdf) を insensitive へ移動 → 1 物理実体が 2 保存系列に case 一致、継続系列の選択規則なし | **L10** |
| 7 | X4 | 時計後退中の編集 → created_at = max(now, latest+1) で LWW 前進継続、72h 前進警告も確認 | 問題なし |
| 8 | X4 | 同一 ms 内の連続コミット → latest+1 でフォルダ内全順序 | 問題なし |
| 9 | X5 | batch_requests 10 万行の reconcile 走査 → 部分 index idx_batch_active + §19 再考条件と整合 | 問題なし |
| 10 | X6 | 2 文字クエリ「検索」→ trigram 沈黙 → LIKE fallback (bind 分離・ESCAPE・instr(lower) rank) | 問題なし |
| 11 | X6 | vec0 DROP→CREATE→再充填を tick 内で中断 → 差集合再充填が次 tick 補填 | 問題なし |
| 12 | X7 | 新旧アプリ混在 (user_version fail-closed) / grammar v+1 の追跡列なし全走査再 materialize | 問題なし |
| 13 | X8 | 細工 .folder-history の file_versions に `../evil` → name_invalid が保存側・restore 側の両方で遮断 | 問題なし |
| 14 | X9 | ディスク満杯を objects → metadata → app の各書込点で発生 → 差集合駆動で次 tick 収束、tmp は 24h 掃除 | 問題なし |
| 15 | X10 | zip 往復 (mtime/inode 全変化) → 全 rehash・content_hash 同一で無コミット | 問題なし |
| 16 | X11 | NFC 論理名層 (scan_cache/LWW) × raw 名層 (fp) × pending_deletes × fp 不確定 3 条件の連動 | 問題なし |
| 17 | X12 | watch_root 追加→register→スキャン→OCR→チャンク→embed→replicate→横断検索→§12 解決→restore の一気通貫 — 各受け渡しの出典 § を特定できた | 問題なし |
| 18 | X13 | 「明示 retry」(§21.7) = attempts→0、入力は PK から自明。ただし L02 (attempts=0 のまま) / L03 (state=0) の行には無効 | 問題なし (関連欠陥は L02/L03) |
| 19 | X14 | collect 429 + Retry-After → 同 tick 打ち切り・attempts 不消費; fp_cache 孤児は完全 walk 時 mark-and-sweep | 問題なし |
| 20 | X15 | 主張「同一の正規化コミット → 同一 commit_hash」反証 (nonce/device 混入を探索) | 破れず |
| 21 | X16 | JSONL 分割で 1 submit → 複数 job → intent_token は job 単位で行グループ別、token 単位で回復成立 | 問題なし |
| 22 | X17 | register 手順 2 途中クラッシュ → damaged → 旧行退役 → 新 id 再登録 (fp 無効化で初回コミット成立) | 問題なし |
| 23 | X18 | profiles 破損行 → fsck が検証済み record で DELETE→INSERT 修復 (OR IGNORE では直らない旨と整合) | 問題なし |
| 24 | X19 | dir fsync 適用点の網羅 (objects prefix / tmp / §21.1 / §21.3 journal・id / §21.4) + migration 単一 Tx + FTS rebuild | 問題なし |
| 25 | X20 | 主張「重複課金は intent 回復で最悪 job 1 回分」→ server 経路で反証試行 (相 2/3 境界の反復クラッシュ) | 破れず (client 経路は文書自身が除外済み) |
| 26 | X21 | 相 1 の attempts=0 (profile 数え直し)・upload_cleaned=0・error/completed_at NULL 戻し × intent 回復採用 (snapshot 不変) — profile 往復を挟んでも旧空間 vector は collect 照合で破棄 | 問題なし |
| 27 | X22 | fork 手順 1: defer_foreign_keys × foreign_keys=ON × journal DELETE — 自己参照 FK は COMMIT 時検査で成立 | 問題なし |
| 28 | X23 | name_collision / name_invalid の読み手 (walk 観測・delete 判定・status・restore) 総当り — 到達不能行なし | 問題なし |
| 29 | X23/X26 | cost_ledger UNIQUE × 冪等再実行: 行が生きている間は seq 単調で衝突なし。行 DELETE→再 INSERT で seq=0 に戻る経路を発見 | **L01** |
| 30 | X24 | vec CREATE 後・充填途中クラッシュ / agg 一度きり破棄の喪失 → 差集合再充填・毎 tick 検査が吸収 | 破れず |
| 31 | X25 | フォルダ未接続の app.sqlite 単独横断検索 — app_config の embedding_profile record だけで :query_vector 生成可 | 問題なし |
| 32 | X26 | unregister → 再 register (同一 id) → 明示再生成: §5.3 が seq=0 で INSERT → 相 3 で seq=1 → close Tx の ledger INSERT が残存 ledger(…,1) と UNIQUE 衝突 → 恒久 rollback | **L01 (fatal)** |
| 33 | X26 | 相 2 恒久拒否: state=3 (submit_rejected)・attempts 不変 → 遷移表「attempts<上限 → 投入対象」→ 毎 tick 載せ直し→再拒否の無限ループ | **L02 (major)** |
| 34 | X26 | submission_seq の書込 3 点 (相 3 / intent 採用 / client 前計上) の重複・欠落検査 — 各 1 job = 1 増分 | 問題なし |
| 35 | X26 | floor 引き上げ (app 先行) の全クラッシュ位置 — floor 過大は再 OCR 方向 = fail-safe、成果あり化の窓なし | 問題なし |
| 36 | X27 | fork 手順 4 を journal→flag の順で実装 + 電源断 → journal なき fork_in_progress 残存 → 当該 repo が tick 全ステップから恒久除外 (沈黙凍結)。通常運転時の journal 検出契機も未定義 | **L04 (major)** |
| 37 | X27 | 非追跡側コピーの fork: fork_in_progress(old_id, パス) の除外が repo (old_id) 粒度 → 生存側の submit/collect/replicate まで凍結 | **L05 (major)** |
| 38 | X27 | fork 各境界 (手順 0/1/2/3 後) のクラッシュ → journal {old_id,new_id} + 実体 (id ファイル・commits 有無) から再開位置一意 (完了後再実行の手順 3 folders INSERT 冪等性のみ要注記 — L04 修正案に含む) | 問題なし |
| 39 | X28 | detached state=1 の全周: collect payload 破棄+記帳+終端 → upload 掃除 → 行削除。detached 中の再 register → folders 復帰で通常行へ (PK 同一・submit は「回収待ち」で二重投入なし — §21.2 明記) | 問題なし |
| 40 | X28 | 相 2 完了 (job 作成済み)・相 3 前クラッシュ → unregister → state=0 detached が「job 未作成 = 課金なし」として job 残骸を掃除し行を即削除 → 課金が ledger から欠落 | **L06 (major)** |
| 41 | X29 | §11.1 PARTITION BY file_name — 保存名固定 (初出時表記) により BINARY 一致で単一系列、複合 FK も解決 | 問題なし |
| 42 | X29 | restore in-place を insensitive ボリュームの別 case 物理名へ → 物理名維持・次スキャンは case 一致で既存保存名継続 | 問題なし |
| 43 | X29 | 初出表記の決定順序: NFC 正規化 (全層共通) → case 照合 — §20.5 内で合成可能、循環なし | 問題なし |
| 44 | X30 | 主張「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」→ 一時消失窓・瞬間再出現・時計後退で攻撃 | 破れず |
| 45 | X30 | 主張「detached は課金を取りこぼさない」 | **破れた → L06** |
| 46 | X30 | 主張「保存名固定により case-only rename の FK 違反は構造的に不可能」 | 破れず |
| 47 | 自由 | client 経路で呼出中クラッシュ × attempts 上限到達 → state=0・batch_job_id 非 NULL のまま submit/reconcile/collect/明示 retry/滞留監視のすべての対象外 = 脱出不能 | **L03 (major)** |
| 48 | 自由 | fork (追跡側) 手順 3 を列挙どおり実装 (folders 行が残る) → 次 tick walk が旧 root_path × 新 id で規約 12 恒久 conflict、in-flight は detached にも collect 可能にもならない | **L07 (major)** |
| 49 | 自由 | 成果あり × state=0 (kind=2 profile 往復 + 相 2 クラッシュの合流) → reconcile が intent 未解決のまま閉じ、追跡外 job/upload が残る | L08 (minor) |
| 50 | 自由 | terminal 記帳の列挙 (expired/timeout/missing/profile_changed) に素の item 失敗がない一方 detached は全終端で記帳 — 基準非対称 / case 折り畳みアルゴリズム未規定 / app_config 初期投入経路未定義 | L11 / L09 / L12 (minor) |

---

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| L01 | **fatal** | §5.3「行が無ければ … submission_seq=0 で INSERT」(L251) / §9.1 DDL「submission_seq … DEFAULT 0」(L681) + cost_ledger「UNIQUE (repository_id, kind, target_key, submission_seq)」(L728) / §21.2「cancel が確定した行と terminal (state 2/3) の行のみ削除」+「cost_ledger は削除しない」 | submission_seq は**行の中では**単調だが、行の削除→再作成で 0 に戻る。ledger は永続 (退役でも不削除) のため、同一 (repo, kind, target_key) の再走で seq が既存 ledger 行と再衝突し、close Tx (state 更新 + ledger 追記が同一 Tx) が UNIQUE 違反で恒久失敗する。K02 が塞いだ「attempts リセット × UNIQUE」と同型の fatal が、行ライフサイクル (削除→再 INSERT) 経由で再発 | ① repo R・target T を OCR: 相 3 で seq=1 → collect done + ledger(R,1,T,1) ② unregister — state=2 行は削除、ledger は残存 ③ 同フォルダを再 register (同一 repository-id) ④ 明示再生成 (§5.3) — 行なし → **seq=0 で INSERT** ⑤ submit 相 3 で seq=1 → collect close Tx が ledger(R,1,T,1) を INSERT → **UNIQUE 衝突 → rollback** → state=1 のまま毎 tick 同一失敗。時刻基準 job_missing の terminal 記帳も同 seq で衝突 → 恒久 state=1・課金記帳不能・upload 掃除不能 (kind=2 の profile 変更後再投入でも同様に全 target で発生) | C7 / X26 / X23 / P9 | 行の (再) INSERT 時、submission_seq の初期値を `COALESCE((SELECT MAX(submission_seq) FROM cost_ledger WHERE 同 (repo,kind,target_key)), 0)` から継承する。§5.3 の固定値 0 と DDL DEFAULT 0 依存の初期化を同規則へ差し替え |
| L02 | major | §9.1 相 2「恒久拒否 (内容起因の 4xx …) → 即 terminal: state=3 (error='submit_rejected')、復帰は明示 retry のみ」(L804-805) × 遷移表「成果なし・state=3・attempts < 上限 → 投入対象 (再投入)」(L776) | attempts+1 は相 3 でのみ実行され、相 2 の恒久拒否は attempts を消費しない。submit_rejected 行は attempts が増えないため遷移表上 terminal に到達せず、次 tick が相 1 から載せ直し→再拒否 — **断つはずだった無限載せ直しループがそのまま残る** (毎 tick の upload + 拒否)。preflight terminal が「attempts = 上限」を明示設定するのと非対称 | 内容起因 4xx の原本 X: tick1 相 1→相 2 拒否→state=3・attempts=0 → tick2 遷移表で「投入対象」→ 相 1 (error NULL 化・新 token)→相 2 拒否 → … 毎 tick 反復、明示 retry (attempts→0) でも止まらない | C7 / X26 / K06 の帰結 | 恒久拒否時に state=3 と同時に **attempts = 上限** を設定する (§6 unsupported_format / oversize と同型)。明示 retry が唯一の復帰路になる |
| L03 | major | §8 (iii)「前計上済み (batch_job_id 非 NULL・state=0) の行は「実行された可能性がある」として扱い、遷移表の再投入判定 (attempts 上限) に従って再実行する」(L629-630) | attempts ≥ 上限に達した client 行の**行き先が無い**: 再実行されず (上限)、reconcile は成果なしで閉じず、collect は state=1 のみ対象、明示 retry は terminal (state=3) 向け、滞留監視は「completed_at NULL の **state=1**」(L1244) のみ。state=0 のまま恒久 limbo — terminal 化も課金記帳 (最大 3 回実行された可能性) も status 可視化もされない | client 経路 kind=2 の target X: 呼出中クラッシュ × 3 → attempts=3・state=0・batch_job_id=token3 → 以後どの経路も行に触れない → X は永久に embed されず、どの status にも現れない | C7 / X26 / K09 の帰結 | 回復時に attempts ≥ 上限なら state=3 (error='client_exhausted') へ terminal 化 + terminal 記帳 (cost NULL + estimated)。滞留監視の対象に state=0 を追加 |
| L04 | major | §21.3 手順 4「journal と fork_in_progress を消す (完了)」(L2084 — 削除順未規定) / 手順 0「この repo は tick の全ステップ … から除外」/ 失敗回復表 (journal 検出の契機は bootstrap のみ定義) | (a) journal→flag の順で削除しクラッシュすると **journal なき fork_in_progress が残存** — 回復の駆動源 (journal) が無いため flag を消す者がおらず、当該 repo は tick 全ステップから**恒久除外 = 沈黙凍結** (新規編集が二度とコミットされない)。(b) 通常運転 (app 全損なし) で crash 後に journal を検出・再開する契機が未定義 — fork がユーザー再操作まで放置される | fork 実行 → 手順 4 で journal 削除直後に電源断 → 再起動: journal なし・flag あり → tick は repo を除外し続ける → スキャンも collect も永久停止、status 通知もなし | C7 / X27 / K14 の帰結 | 削除順を **fork_in_progress → journal** に固定し、tick ステップ 0 冒頭に (a) fork-journal 保有フォルダの回復実行 (b) journal なき fork_in_progress の掃除、を追加。回復の手順 3 は冪等化 (folders INSERT OR IGNORE) |
| L05 | major | §21.3 手順 0「app 側には fork_in_progress = (old_id, 対象パス) を軽い印として記録し、**この repo** は tick の全ステップ (scan / submit / collect / replicate) から除外」(L2061-2062) | 除外の主語が repo (old_id)。conflict の**非追跡側コピー**を fork すると (conflict 解決の正規手順)、生存側 (同一 old_id、folders が指す実体) の submit / collect / replicate まで除外される。手順 3 は「対象パス == root_path の場合のみ」ガードを持つのに、除外規則には同ガードが無い。L04 と重なると生存側が恒久凍結 | 追跡側 A (id R、in-flight OCR あり)・コピー B (同 R) → conflict → B を fork → fork_in_progress(R, pathB) → tick が R を全除外 → A の collect・upload 掃除・replicate が停止。fork が crash で滞留すると (L04) 無期限 | C11(b) / X27 | scan の除外は対象パス限定とし、id 系ステップ (submit/collect/replicate) の除外は「対象パス == folders[old_id].root_path の場合のみ」(手順 3 と同一ガード) に限定する |
| L06 | major | §9.1 detached 規範「state=0 の detached: **job 未作成 = 課金なし**。intent_token で upload / **job 残骸**を掃除して行を即削除する」(L877) | state=0 は「相 2 完了 (job 作成済み)・相 3 前クラッシュ」を含む — 同じ文が job 残骸の掃除を指示しており「job 未作成」という前提と自己矛盾。掃除される job は実行・課金され得るが、行の即削除により ledger に一切記帳されない (通常経路なら intent 回復 → 採用 → collect 記帳で拾えた)。§21.2 手順 1 の cancel 確定削除にも同種の残余 (cancel 前処理分の課金の非記帳) がある | 相 2 完了直後にクラッシュ (state=0・job 作成済み) → ユーザーが unregister → detached state=0 → token で job を掃除 + 行即削除 → その job の課金がどの ledger 行にも記録されない | C12 / X28 / X30 (「detached は課金を取りこぼさない」の反証) | state=0 detached は削除前に intent_token で provider の job 一覧を照合し、**実在すれば採用 (state=1 detached・seq+1) して collect 経路で記帳**、不在の場合のみ upload 掃除 + 即削除。§21.2 cancel 確定行にも「取得可能なら部分課金を記帳」を注記 |
| L07 | major | §21.3 手順 3「旧 repository_id の app 行を退役する (agg 4 表 + sync_state + scan_cache + pending_deletes + 配下 fp_cache を DELETE。batch_requests は §21.2 と同一規則 …)」(L2077-2079 — **folders が列挙に無い**) / §20.4「猶予満了後は tick が §9.3-d を実行して退役」(L1865) × §9.3-d「folders **から消えた** repository_id について …」(前提の循環) | folders 行の DELETE を明示するのは §21.2 (「+ folders から DELETE」) のみ。§21.3 手順 3 と §20.4 猶予満了は §9.3-d (folders 消失を**前提とする事後処理**) を指すだけで、**誰が folders 行を消すか未規定**。列挙どおり実装すると folders 行が残存し、(a) detached 条件 (= folders 行なし) が成立せず in-flight の処理規範が発火しない、(b) fork 後は旧 root_path × 新 repository-id の規約 12 照合で**恒久偽 conflict**、collect も同照合で恒久停止、(c) 猶予満了退役が missing→retire を反復して確定しない | fork (追跡側・in-flight あり) → 手順 3 を列挙どおり実行 (folders[old_id] 残存) → 手順 4 完了 → 次 tick: walk が folders[old_id].root_path を訪問 → repository-id ファイルは new_id → 規約 12 conflict (永久)。old_id の state=1 行は detached でも collect 可能でもなく、upload も掃除されない | C8 / C11(a) / X27・X28 の合流 | 「退役」を「**folders 行 DELETE** + §9.3-d の一括削除 + batch_requests の §21.2 規則適用を単一 app Tx で行う操作」と定義し、§21.3 手順 3 の列挙に folders DELETE を明記、§20.4 猶予満了も同語で参照する |
| L08 | minor | §10 0.5「batch_requests の state IN (0, 3) 全行について … 成果ありを state=2 へ閉じる」 | 成果あり × state=0 (kind=2 の profile 往復 + 相 2 クラッシュの合流で発生) を reconcile が閉じると、未解決 intent の job / upload (upload_id 未記録) が追跡外になる — 記帳漏れ・機密残留は最大 1 job・provider TTL で消滅する既知残余の範囲だが、intent 回復なら拾えた | kind=2 target X: profile P1 で成果あり → P2 へ変更 → 相 1 (state=0)・相 2 まで実行してクラッシュ → P1 へ戻す → 成果あり (P1=現行) × state=0 → reconcile が state=2 へ → 相 2 で作られた job/upload が永久に追跡外 | C12 / X21 | reconcile の state=0 クローズ時は先に intent 回復 (token 照合 → 採用 or 残骸掃除) を実行してから閉じる |
| L09 | minor | §20.5「論理名の同一性判定は case-insensitive で行い」(折り畳みアルゴリズム未規定) | FS の同一性判定 (NTFS upcase 表 / APFS の Unicode 折り畳み) と実装の折り畳み (ASCII / simple / full fold) が乖離する名前 (ı/İ、ß 等) で、FS が同一視する 2 名を別系列にする (逆も) — 系列分裂 / name_collision の誤発火 | APFS-insensitive 上で "straße.pdf" → "STRASSE.PDF" に rename (FS は別実体扱い/同一扱いがボリューム実装依存) → 実装の折り畳みと食い違うと偽 delete+create または誤 name_collision | C11(a) / X29 | 折り畳みを Unicode simple case folding に固定し「FS と判定が乖離し得る名前は系列分裂側 (fail-safe) に倒れる」と注記 |
| L10 | minor | §20.5 case 規則「walk が readdir 表記と case 違いで一致する**既存 file_versions 系列**を見つけたら、既存の保存済み論理名をそのまま使い続ける」(単数を暗黙前提) | case-sensitive ボリューム由来の履歴には case 違いの複数生存系列があり得る。insensitive へ移動すると 1 物理実体が**複数系列**に一致し、どの系列を継続しどれを absent (delete) にするかが未定義 — 実装間で非決定 | sensitive 上で Report.pdf (系列 A)・report.pdf (系列 B) を各コミット → フォルダごと insensitive へコピー (物理は 1 実体) → walk の観測が A/B 両方に case 一致 → 継続系列の選択・他方の delete 判定が規則なし | C12 / X29 | タイブレークを明文化: BINARY 完全一致する系列を優先、無ければ保存名の UTF-8 バイト昇順先頭を継続、残りは通常の delete 判定 (absent) に入れる |
| L11 | minor | §9.1「terminal 化時の課金記帳: … 成果なしの terminal (result_expired / job_timeout / output_missing / job_missing / profile_changed) へ倒れる場合も記帳」 | 列挙に素の item 失敗 (item 失敗 → state=3 + error) が無く、その attempt は記帳されない。一方 detached は「終端したら … 記帳」と全終端で記帳する — 同じ「実行された可能性のある課金」の扱いが経路で非対称 (ledger の下限性の範囲内だが基準が不一致) | job 内の item がプロバイダ側エラーで失敗 (ページ処理分は課金され得る) → state=3・記帳なし。同じ失敗が detached 行で起きると記帳される | C11(c) / X23 | item 失敗も terminal 記帳の列挙に含める (cost 不明は NULL + estimated) か、除外理由 (失敗 item は課金されないプロバイダ前提) を明記 |
| L12 | minor | §21.5 bootstrap「app_config (現行 tool / embedding profile) も同時に再入力・確認する」(全損後のみ) | **初回セットアップ**での app_config 投入経路が未定義。現行 profile 不在時の submit (:current_tool 構成不能)・横断検索 (query embedding 不能) の挙動 (スキップ? エラー?) も未規定 | 新規インストール → watch_root 追加 → register → tick: app_config に 'tool_profile' が無い → step 1 の差集合が構成できない (挙動未定義) | C11(a) / X25 | 初期設定操作 (§21 に profile 設定操作を追加) と「app_config 未設定の kind はその submit / KNN をスキップし status 表示」の fail-closed 規則を明記 |
| L13 | proposal | §6 preflight「OCR へ投入するのは PDF と画像 … のみ」 | プレーンテキスト / Markdown / CSV 等のテキスト原本は unsupported_format terminal となり、本設計では**一切検索対象にならない** (chunks は OCR 派生からのみ生成)。知識アーカイブの用途上、意外性のある制約 | — (シナリオ不要の位置づけ明記提案) | X2 派生 | 「テキスト系ファイルは検索対象外」を §1 要件に明記するか、OCR を経ない直接 Markdown 取り込み経路 (tool_profile の一種) を将来拡張 §19 に記録 |

---

## 第 4 部 — 確認済みの列挙

検出 0 件で確認済みの観点:

- **C1** (P1〜P16 の反映): 全項目一致。L01〜L12 は原則への違反ではなく、原則が定めた機構の帰結・未対処 (C12 の正規指摘範囲)
- **C2** (SQL 静的): FTS5 external content の view + content_rowid 構成 / WITHOUT ROWID と PK / GENERATED 列 / 複合 FK の列数 / trigger の INSERT・DELETE 対 / CHECK 論理 — 問題なし
- **C3** (相互参照): §21.7・§9.3-d・「元設計 §15/§21」番号衝突注記を含め全参照が解決
- **C4** (クエリ × スキーマ): §11.2 / §9.3-a / §13 GC / 差集合 SQL の列・join キー (小文字 hex 含む) 整合
- **C5** (数値): $2.5/1k・+25%・RRF k=60・768 = 参考値・「8 テーブル」— 全出現一致 (「7 テーブル」残存なし、grep 確認)
- **C6** (用語形式): target_key 連結形式・chunk_type↔target_type・obj: スキーム・embed_hash 定義の再掲一致
- **C8** (章の欠落): なし (欠落は L07 / L12 として個別指摘)
- **C10** (修正が開けた穴の定点 a〜z): L01〜L08 に該当する項目以外は矛盾なし (特に v = seq 書込 3 点、w = snapshot 全経路、x = detached 3 経路の規則一致、y = 保存名固定 × PARTITION/FK は確認済み)
- **原則別**: P1〜P8・P10〜P15 は指摘なし。指摘は P9 (状態機械) と §21 操作カタログ (P16 周辺) に集中
- **破れなかった主張** (X15/X20/X24/X30): 「同一正規化コミット → 同一 hash」/「server 経路の重複課金 ≤ job 1 回分」/「vec 差集合再充填はどのクラッシュ位置でも収束」/「agg 毎 tick 検査は一度きり破棄の喪失を吸収」/「保存名固定で case-only rename の FK 違反は構造的に不可能」/「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」
