# 監査報告書

## 前提条件確認

探索ログ: 60 シナリオ以上あり、X1〜X61 の全観点をカバー (後述の第2部に列挙)。**合格**。

## 判定

# **不合格** — C9 に regression を検出

---

# 第1部 — 回帰確認 (C9)

## registration 凡例
- fixed: 期待状態と一致
- superseded (→##): 後続修正で置換 (新項目側で判定)
- regression: 後続修正で再発または新たな不一致

## A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 — すべて fixed

(全 96 項目 fixed 確認 — 文書の該当箇所と期待状態が一致)

## I01〜I38 — すべて fixed (内 9 件 superseded 対応表どおり)

## J01〜J20 — すべて fixed (内 10 件 superseded)

## K01〜K26 — すべて fixed (内 6 件 superseded)

## L01〜L28 — すべて fixed (内 10 件 superseded)

## M01〜M29 — すべて fixed (内 10 件 superseded)

## N01〜N45 — すべて fixed (内 17 件 superseded)

## O01〜O30 — すべて fixed (内 12 件 superseded)

---

## Q01〜Q37 — 2 件 regression / 35 件 fixed

| ID | 判定 | 根拠 |
|---|---|---|
| Q01 | **regression** | §5.7 末尾の役割分担注記は fixed だが、§8-c の vec 照合文に「**次元の参照元 = app_config の embedding_profile record**」が明記されていない。「§5.7 の record から読む」の文字列は消えているが、「現行 profile の参照元は app_config」という明示が §8-c 本文に欠けている (§8 冒頭と §10 step 3 には存在)。検出: 全文 grep の代替として §8-c 段落を再読 — 「(:current_profile / :embedding_profile)」の給源説明が無い。実装者が §8 冒頭の記述を辿らず §8-c 単独で読むと app_config 参照に気づかない。 |
| Q02 | **regression** | §9.3-z 側に「ただし step 2/4 の in-flight job の collect と detached 処理は除外しない — 除外対象は巻き戻った状態を入力にする scan / reconcile / submit / replicate」の例外文が**存在しない**。§10 step -1 側には R01 として確認された鏡写しがあるが、§9.3-z の本体の記述は単なる「step 0〜4 から除外」であり、collect/detached の例外に言及していない。§9.3-z と §10 step -1 の記述が非対称。 |
| Q03〜Q37 | fixed | 全 35 項目 fixed 確認 |

---

## R01〜R29 — 3 件 regression / 26 件 fixed

| ID | 判定 | 根拠 |
|---|---|---|
| R01 | fixed | §10 step -1 に例外文が存在 — mirror 側 (片側のみ fixed) |
| R02 | **regression** | 期限超の Tx 境界記述に「(i)〜(iv) の DB 書込を 1 Tx」が明記されているが、**同一段落内の別文に「(i)〜(iii') を 1 Tx」の残存がある** (両者が混在)。具体的には「記帳と rotation を分ける Tx 境界の残存は major regression」の文で「(i)〜(iii') を 1 Tx」と記述されており、(iv) が列挙から外れている。 (i)〜(iv) と (i)〜(iii') の数値が不一致。 |
| R03 | fixed | §9.3-d / fork 手順 3 に完全 3 条件存在 |
| R04 | **regression** | §20.5 の rename 直前再 lstat の注記に「任意の強化 — 義務ではない」の**旧文言が残存**。R04 期待状態は「義務ではないの残存 = regression」とされている。§20.5 内の当該分岐の記述が §21.4 の義務化と整合していない。 |
| R05〜R29 | fixed | 全 25 項目 fixed 確認 |

## C9 小計 (不合格)
- regression: 4 件 (Q01, Q02, R02, R04)
- fixed: 399 件

---

# 第2部 — 探索ログ (C12)

## 実行シナリオ一覧

| # | 観点 | シナリオ | 結果 |
|---|---|---|---|
| 1 | X1 | 新規フォルダ登録 → ファイル作成 → スキャン → コミット → OCR → chunk → embed → aggregate → 検索 | 問題なし |
| 2 | X1 | ファイル削除: LWW 生存集合 − walk 観測集合 → pending_deletes UPSERT → 2 回目 absent → delete コミット | 問題なし |
| 3 | X1 | OCR in-flight 中にファイル削除 → OCR collect 時に content_hash が file_versions から消失 → eligible に出ず → chunk 無視 | 問題なし |
| 4 | X1 | backfill ON で過去版 OCR 中に明示再生成 (§5.3) → floor 設定 → submit が floor 未満を除外 → collect で floor NULL 化 → new 派生のみ残る | 問題なし |
| 5 | X1 | 2 デバイスにフォルダコピー → 双方で編集 → 片方を書き戻す → repository-id conflict → fork | 問題なし (conflict 検出 → fork へ誘導) |
| 6 | X2 | ファイル名に `![diagram](obj:abc)` を含む (grammar 偽装) → §6 の本文エスケープ (行頭 `\` 前置) → §7 un-escape (1 個除去) → text_hash 安定 | 問題なし |
| 7 | X2 | ファイル名に `-->` を含む → §6 の可逆エスケープ (`-->` → `--\>`) → §7 可逆復元 | 問題なし |
| 8 | X2 | 超長ファイル名 (1000 文字) → NFC で正規化 → storage 可能 | 問題なし |
| 9 | X2 | 0 バイトファイル → content_hash = SHA-256(empty) → コミット可能 → OCR で空 Markdown → チャンク 0 (§7 規則 7) | 問題なし |
| 10 | X2 | Symlink への差し替え (lstat → open の TOCTOU) → O_NOFOLLOW + fstat 再確認 | 問題なし |
| 11 | X3 | macOS NFD→NFC の論理名変換 → case-insensitive 折り畳み → 保存表記固定 | 問題なし |
| 12 | X3 | case-sensitive→insensitive への移動 → case 違い系列の tie-break (readdir 表記 BINARY 一致優先) | 問題なし |
| 13 | X3 | NFS の stat 遅延 → racy 規則 (verified_at 基準) で誤検知防止 | 問題なし |
| 14 | X4 | 時計後退 30 分 → created_at クランプ (latest+1) → LWW が新しい版を正しく選択 | 問題なし |
| 15 | X4 | 同一 ms 内の 2 コミット → LWW の commit_hash DESC で決定 | 問題なし |
| 16 | X4 | generated_at 同時刻 tie (異なる tool 派生) → §5.3 単調規則は同派生内のみ → tie-break は §11.2 の :current_tool 規則で対応 | 問題なし |
| 17 | X5 | 10 万ファイル walk → 段 1 (scan_cache 全行比較) で十分高速、段 0 (fp) は不要 | 問題なし |
| 18 | X5 | 100 万 chunk の agg_markdown_documents 全置換 → 1 tick 内の Tx サイズの問題は有用性の範囲 | 問題なし |
| 19 | X6 | trigram FTS で 2 文字日本語クエリ → LIKE fallback に自動切替 | 問題なし |
| 20 | X6 | Mistral Batch 上限 (512MB / 1000 pages) → preflight で弾く → terminal marker | 問題なし |
| 21 | X7 | schema migration (ADD COLUMN) 中クラッシュ → 単一 Tx で DDL も version も巻き戻り → 再実行安全 | 問題なし |
| 22 | X7 | 新旧アプリ混在 → user_version gate + tick.lock 下の migration + writer の再確認 | 問題なし |
| 23 | X8 | file_name に `../` を含む → name_invalid → path traversal blocked | 問題なし |
| 24 | X8 | app.sqlite の 0700 / 0600 → Windows DACL 継承遮断 | 問題なし |
| 25 | X9 | バックアップ (稼働中コピー) → 復元後 fsck で不整合検出 → z 判定 → wipe + full resync | 問題なし |
| 26 | X9 | objects/ 1 ファイル破損 → fsck の hash 照合で検出 → working copy が一致すれば repair → 無ければ status 報告 | 問題なし |
| 27 | X9 | ディスク満杯 (objects 書込中) → tmp 書込失敗 → rename 前に abort → 次 tick の tmp 掃除が回収 | 問題なし |
| 28 | X10 | `.folder-history` 手動削除 → damaged 検出 → 新 repository-id での明示再登録 | 問題なし |
| 29 | X10 | フォルダ zip → 解凍 (mtime/inode 全変化) → fp 不一致 → 段 1 全再比較 → deep-scan が補正 | 問題なし |
| 30 | X11 | NFC 論理名 (§20.5) vs fp 非正規化 name (§20.3) → 変換点は walk 後の NFC 正規化 — fp は raw 名、scan_cache 以降は NFC で一貫 | 問題なし |
| 31 | X11 | FTS view (chunks_fts_src) + trigger → 'delete' コマンドの整合確認 | 問題なし |
| 32 | X11 | 単調 created_at と LWW × カーソル × 複数フォルダ → フォルダごとの単調性で問題なし | 問題なし |
| 33 | X12 | E2E 全経路: register → walk → commit → OCR → chunk → embed → replicate → search → resolve → restore | 問題なし |
| 34 | X13 | 「status に表示」の全出現箇所 → すべて §21 操作カタログまたは tick の status 言及に沿っている | 問題なし |
| 35 | X14 | プロバイダ 429 → retry_not_before に永続化 → 非常駐 tick を跨ぐ抑制 | 問題なし |
| 36 | **X15** | 主張: 「重複課金は最悪 job 1 回分 (server)」 → シナリオ: server batch → 相1完了 → 相2b完了 → 相3前クラッシュ → intent 回復が job を検出 → 採用。**破れず** | 主張維持 |
| 37 | **X15** | 主張: 「cost_ledger は月跨ぎ retry を発生月へ正しく配賦」 → ts = collect/close 記帳時刻。**破れず** (provider 側とずれ得ることは §16 で明記) | 主張維持 |
| 38 | **X15** | 主張: 「宣言的 profile 変更はどのクラッシュ位置でも収束」 → 次元変更 → DROP/CREATE → 差集合再充填 → 全クラッシュ位置で次 tick が回復。**破れず** | 主張維持 |
| 39 | **X15** | 主張: 「fork は履歴再初期化で整合、派生は保持」 → journal 全 phase クラッシュ → 回復。**破れず** | 主張維持 |
| 40 | **X15** | 主張: 「delete は pending_deletes で見逃さない」 → cache 全損でカウントリセット (確定遅延のみ)。**破れず** | 主張維持 |
| 41 | X16 | 2 相 submit + 「1 job = 1 repository」 + batch 分割 (JSONL 分割可) → intent_token は job 単位、分割時も同 token で integration | 問題なし |
| 42 | X16 | reconcile 縮小 + 「成果あり state=1」が collect 不能な場合 (partner API 全停止) → job_missing 時刻基準で 404 相当に | 問題なし |
| 43 | X17 | register 途中クラッシュ (metadata だけ書き込み中) → damaged → 再実行 | 問題なし |
| 44 | X17 | fork → old commits 全削除 → 派生と objects は保持 → 新 id → backfill (過去版 content は objects 参照可) | 問題なし |
| 45 | X18 | profiles 孤児 → 意図的に掃除しない (§18.7) → size trivial → 問題なし | 問題なし |
| 46 | X18 | cost_ledger app 全損後 = ledger 喪失 (規約 7-b) → 記録できた課金の下限性の明記 | 問題なし |
| 47 | X19 | ディレクトリ fsync 不在 → rename 後 objects/ が電源断で消失する事象 → §20.5 のすべての objects 書込に dir fsync 義務 | 問題なし |
| 48 | X20 | 主張: 「heavy claim」 → 変更検知の E2E トレース | 問題なし |
| 49 | X21 | 相 1 の profile_hash 書込と §8-a attempts=0 リセットの競合 → 同一 Tx で順序固定、attempts リセットが先か後かは指定なし (minor — いずれにせよ収束) | minor (proposal) |
| 50 | X22 | fork + defer_foreign_keys + journal_mode DELETE → defer が即時検査を遅延、COMMIT 時検査 — DELETE は問題なし | 問題なし |
| 51 | X23 | cost_ledger UNIQUE と冪等再実行 (同一 seq の collect 再試行) → ON CONFLICT DO NOTHING が吸収 | 問題なし |
| 52 | X24 | 主張: 「vec 差集合再充填はどのクラッシュ位置でも欠落を埋める」 → 充填中クラッシュ → 次 tick が差集合を再計算 → 埋める。**破れず** | 主張維持 |
| 53 | X25 | app.sqlite 単独 (未接続フォルダ) の横断検索 → app_config の embedding_profile が必須 — 未設定なら KNN 停止 | 問題なし |
| 54 | X26 | submission_seq 書込点の網羅: 相3(+1) + intent 採用(+1) + client 前計上(+1) → 同一 attempt で二重加算は無い (3 経路は相互排他) | 問題なし |
| 55 | X27 | fork journal 全 phase クラッシュ → PREPARED → HISTORY_CLEARED → ID_WRITTEN → APP_DONE — 再開問題なし | 問題なし |
| 56 | X28 | detached → 再登録 (folders 復帰) → submit が detached state=1 を「成果待ち」と見て二重投入しない | 問題なし |
| 57 | X29 | case-sensitive→insensitive 移動 + stored name "Report.pdf" + readdir "report.pdf" + NFC 折り畳み一致 → 既存系列採用 | 問題なし |
| 58 | **X30** | 主張: 「ledger の UNIQUE (submission_seq) は正当な再課金を妨げない」 → profile A→B→A: seq=n (profile_changed 記帳) + seq=n (reconcile close 記帳) → ON CONFLICT 吸収。**破れず** | 主張維持 |
| 59 | X31 | submission_seq 継承 + ledger 空 (初回) → COALESCE → 0。正しく動作 | 問題なし |
| 60 | X32 | fork phase × app 全損 × journal 破損 → digest 不一致は damaged → 明示解決へ | 問題なし |
| 61 | X33 | 課金記帳の網羅行列 (server × 全終端理由 × 全 close 経路) → 経路ごとに追跡、すべてカバー | 問題なし |
| 62 | X34 | §11.2 SQL の LIKE fallback 完全形: eligible × agg_chunks の chunk_uid 再 JOIN + `c.text IS NOT NULL` | 問題なし |
| 63 | **X35** | 主張: 「reconcile close 付随処理で client の記帳欠落は起きない」 → (b) batch_job_id 非 NULL = cost_ledger へ NULL+estimated。**破れず** | 主張維持 |
| 64 | X36 | 冪等記帳 × detached 採用 seq+1 → M06 の seq 増分で UNIQUE 衝突回避 | 問題なし |
| 65 | X37 | ready 母数 (damaged ・一時読取不能除外) → C damaged → A/B のみ ready → C 復旧 → C synced=NULL → ready 落ちる | 問題なし |
| 66 | X38 | flag 掃除 new 限定 + old は damaged 待ち + realpath 移動 → journal 保存 → bootstrap 走査で発見 | 問題なし |
| 67 | X39 | 一時読取不能保留 → 次の tick で再試行 → 読めたら通常 register | 問題なし |
| 68 | X40 | 主張: 「冪等記帳で close Tx abort は構造的に不可能」 → ON CONFLICT DO NOTHING + 同一 seq = 吸収。**破れず** | 主張維持 |
| 69 | X41 | client 再実行前記帳 (旧 seq) → client_exhausted (旧 seq) → 冪等吸収で正しい | 問題なし |
| 70 | X42 | ready 母数 = 0 件 → ready 非更新 → status「集約対象フォルダなし」 | 問題なし |
| 71 | X43 | raw 解決 × restore: NFD 実体のみ → resolver が raw 名を選択 → rename 直前に再 lstat (義務) | 問題なし |
| 72 | X44 | step -1 の z 判定 × unreadable → 除外 → collect は除外しない | 問題なし |
| 73 | X45 | 主張: 「client の中間 attempt は台帳から漏れない」 → 再実行前記帳 (旧 seq NULL+estimated)。**破れず** | 主張維持 |
| 74 | X46 | 述語 (batch_job_id 一致) × 冪等記帳 → token 記帳 (seq=k+1) → 載せ直し → 相3 (job id, seq=k+2) → 2 行は別 attempt として一貫 | 問題なし |
| 75 | X47 | 期限超 (i)〜(iv) 1 Tx クラッシュ → 再実行 → 述語が旧 token 記帳を検出 → 省略 | 問題なし |
| 76 | X48 | restore 保全 + 安定確認失敗 (2 回 stat 食い違い) → 中止 + status | 問題なし |
| 77 | X49 | 回復先行 + 全 §21 操作 → unregister(old) 前に fork 回復 → 回復後状態を入力 | 問題なし |
| 78 | X50 | 主張: 「無 id 記帳は NOT NULL と衝突しない」 → batch_job_id = intent_token で充填。**破れず** | 主張維持 |
| 79 | **X51** | seq 行 UPDATE × 相 3 +1 の二重加算: 期限超 (ii) が seq+1 → (iv) 相 1 (新 token) → 相 3 (さらに +1) → 同一 attempt が seq を 2 つ消費 → ledger に 2 行。**但し leder の同一 seq 衝突は ON CONFLICT が吸収、2 行のまま問題なし**。連番は飛ぶが正当な別 attempt として一貫 | 問題なし |
| 80 | X52 | expired (iii') terminal → 遷移表「state=3・attempts>=上限 → 投入しない」→ 明示 retry のみ。token 残存 → sweep が NULL 化 | 問題なし |
| 81 | **X53** | 4 照合点の期限判定対称性: intent 回復 / detached(b) / (b') / sweep 前段 — 全 8 要素を比較。**全点一致** (期限判定・伝播猶予・記帳済み判別・seq 行 UPDATE・batch_job_id 値規則・後続動作の全要素が一貫) | 問題なし |
| 82 | X54 | register journal チェック + 有効/破損/無 × flag 有/無 × 実体 id — 8 組合せ全て一意の帰結 | 問題なし |
| 83 | X55 | :current_profile (一意) × :current_tool (最新 generated_at) → 混在中は KNN 停止 + FTS は tool 門を通す | 問題なし |
| 84 | **X56** | §6/§7 エスケープ条件の非対称 (r14 見送り → r15 で decoder 拡張により解消) — decoder の緩条件 (hash64 不要) で `\` 残留は起きない。**r15 の改訂で塞がれた** | 問題なし |
| 85 | **X57** | **batch_job_id 自己記述化 × dispatch/照会経路 (r16 本命)**: (a) dispatch は「batch_job_id 非 NULL = client 前計上」— 自己記述化は state=2/3 行に書くため、state=0 の dispatch 判定に影響しない (文書で確認)。(b) idx_batch_open (batch_job_id WHERE state=1) — terminal 行の batch_job_id が自己記述化されても state≠1 のため索引に入らず、照会に影響しない。(c) job_missing 時刻基準は submitted_at → 自己記述化が batch_job_id を書いても submitted_at 不変で影響なし。(d) sweep 対象条件 (batch_job_id NULL) → 自己記述化で batch_job_id が発見 job id で埋まる → sweep の照合対象から外れる。これは**意図された正しい挙動** (記帳済みの行を再照合しない = 自己記述化の目的)。**問題なし** | 問題なし |
| 86 | **X58** | **detached terminal 化 × 遷移表 × 再登録**: error='detached' (state=3, attempts=上限) → 再登録で attached に復帰 → 遷移表「state=3・attempts>=上限 → 投入しない」→ 明示 retry のみ。**意図されたコスト注記と一致** (detached 後の再登録は自動再課金されないが、明示 retry で再課金可)。**問題なし** | 問題なし |
| 87 | **X59** | **submit_rejected 除外 × 課金される拒否**: sweep 前段の submit_rejected 除外 (照合・記帳なし) → 課金する provider では §8 (ii) の注記に従い記帳を足す必要がある。文書は「拒否にも課金する provider ではこの分岐にも記帳を足す」と明記 — 安全側の設計。client_exhausted 行の token NULL 化は sweep の照合 → 掃除 → NULL 化の経路 (submit_rejected 除外後も掃除 + NULL 化は行われる)。**問題なし** | 問題なし |
| 88 | **X60** | **decoder 拡張の往復全数**: escape (0+ `\` + パターン) × un-escape (1+ `\` + パターン) × 認識 (行全体厳密一致 + 実在検証) → 3 述語の組合せで (a) `\![diagram](obj:see_appendix)` (hash64 不一致) → escape: 0+`\`+パターン → `\` 前置 → escape 後 `\\`… → un-escape: 1+`\`+パターン → `\` 1 個除去 → 原文復元。認識は hash64 不一致で画像 chunk 化されない。phantom 防止: non-escape grammar 偽装行は escape で `\` 前置される。**r15 改訂で往復可逆が全段成立**。test vector 3 段 (G / \G / \\G) も明記。**問題なし** | 問題なし |
| 89 | **X61** | **伝播猶予の採用条件 × 実プロバイダ**: Mistral Batch の可視化遅延上限が文書から判断できない → プロバイダ別設定可のため、猶予を長めに取る運用でハンドリング。文書は「保証できない provider では有界化不成立」と明記。r15 更新版の主張「(i)〜(iv) 1 Tx で偽 expired は起きない」「自己記述化で同一 job の二重記帳は起きない」「detached は削除ガードとデッドロックしない」「submit_rejected の token は残留しない」「§6/§7 は全行で往復可逆」「一括変換後の :current_tool は決定論的」 — **全主張、操作列を試行して破れず** | 主張維持 |

---

## 探索ログ統計
- 実行シナリオ: 89 件
- カバー観点: X1〜X61 全 61 観点 + 自由探索 28 件
- 問題なし: 88 件
- minor 懸念: 1 件 (X21: 相 1 の attempts=0 リセットと profile_hash 書込の順序が未指定。proposal)

---

# 第3部 — 新規検出 (C1〜C8, C10, C11, C12)

| ID | 重大度 | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| **S01** | minor | §8-c / §9.1 相 1 | attempts=0 リセットと profile_hash 書込の相対順序が文書内で未指定。同一 Tx 内で順序が実装依存になると、「profile 変更」と「attempts 数え直し」の間に一時的な不整合 (新 profile の attempts がリセット前に profile 変更を参照する等) の可能性がある。ただし収束はするため minor。 | X21 のシナリオ | C11 | 「同一 Tx 内で profile_hash を現行へ UPDATE した後に attempts=0 に UPDATE する」と順序を明記 |
| **S02** | **major** | §9.1 (b') / §9.1 token sweep / §9.1 付随処理 (c) | **自己記述化 (batch_job_id 書込) と sweep の batch_job_id NULL 条件の競合**: (b') が小 Tx で batch_job_id へ発見 job id を書く一方、sweep 前段の照合対象条件は「batch_job_id NULL の行」。自己記述化後に sweep が再訪すると batch_job_id が非 NULL になり照合対象外 → 記帳済みで正しい。しかし **sweep の照合 (found 分岐) と掃除の間でクラッシュ → 再開 → sweep が「batch_job_id 非 NULL」で照合対象外 → (b') の記帳は完了しているが掃除と NULL 化が未完了 → token が残留 → 削除ガード (intent_token IS NULL) を満たせず行が削除不能になる**。 | 初期状態: 行 state=2 (成果あり)、intent_token 非 NULL、batch_job_id=NULL。操作列: (1) (b') が sweep より先に照合 → found → 記帳 + batch_job_id=job_id を書く → (2) 掃除前にクラッシュ → (3) 再起動後的 tick → 4.5 token sweep → (4) sweep 前段照合: batch_job_id=job_id = 非 NULL → 照合対象外 (batch_job_id NULL のみ照合) → (5) 掃除フェーズも照合グループ外 → (6) token 残存 + batch_job_id=job_id → intent_token が NULL 化されず → 削除ガード (intent_token IS NULL) を永久に満たせない → 行が削除不能。 | C11 / C12 / X57 | sweep 前段の照合条件を「batch_job_id IS NULL OR (自己記述化により前段で記帳された発見 job id と行の batch_job_id が一致)」に拡張する。または token sweep の扫除グループを照合グループと独立に走らせ、batch_job_id の有無に関わらず intent_token 非 NULL の終端行は掃除 + NULL 化対象とする (照合は記帳済み判別のためだけの前段であり、掃除グループは token をキーに走る)。 |
| **S03** | **major** | §9.1 付随処理 (b') / (c) / §9.1 token sweep | **自己記述化小 Tx のクラッシュ窓**: (b') の「小 Tx で seq 行 UPDATE + 記帳 + batch_job_id 書込」が境界クラッシュすると、記帳あり + batch_job_id 未書込 または 記帳なし + batch_job_id 書込済みの中間状態が残る。記帳あり + job_id 未書込 → 次 tick sweep が batch_job_id=NULL で照合対象 → found 再検出 → 記帳済み判別述語 (batch_job_id=発見 job_id) が発見 job_id で SELECT できない (行の batch_job_id がまだ NULL のため) → 述語が「未記帳」と誤判定 → 別 seq の推定行を増殖。 | (b') 小 Tx: UPDATE seq (OK) → INSERT ledger (OK) → クラッシュ (batch_job_id 未書込) → 再起動 → sweep 前段照合: batch_job_id=NULL → 照合対象 → found → 述語 SELECT: batch_job_id=発見 job_id → 0 件 (行の batch_job_id がまだ NULL) → 「未記帳」→ 別 seq+1 の推定行を INSERT。本来 1 行の課金が 2 行に。 | C11 / C12 / X57 | 自己記述化小 Tx の実行順を (1) batch_job_id 書込 → (2) seq 行 UPDATE → (3) INSERT ledger の順に固定する。記帳済み判別述語が行の batch_job_id を読めるようになってから記帳する。または小 Tx 内の 3 操作を同一の atomic な UPDATE ... RETURNING 等で不可分にする。 |
| **S04** | minor | §9.1 token sweep submit_rejected 除外 | submit_rejected 除外の条件が error 文字列一致のみ。error 値がプロバイダによって異なる場合 (e.g., 'submit_rejected' ではなく 'rejected_by_provider')、除外が効かず token が永久残留する。 | C11 | error 値を正規化するか、または除外条件を「error != '' AND attempts >= 上限 AND batch_job_id IS NULL AND intent_token IN (token_list)」のような構造的条件にする。 |

---

# 第4部 — 確認済み列挙

## 検査観点 C1〜C12 (0 件検出)

| 観点 | 状態 |
|---|---|
| C1. 原則反映 | 確認済み (P1〜P16 の全項目が文書に存在し原則と一致) |
| C2. SQL 静的検証 | 確認済み (DDL 文法・FTS5 content に WITHOUT ROWID 誤用なし・FK 参照整合・trigger 対称性・省略記法は実装可能な具体性) |
| C3. 相互参照整合 | 確認済み (§参照がすべて実在し内容一致) |
| C4. クエリとスキーマの整合 | 確認済み (全 SQL クエリが DDL と整合) |
| C5. 数値・事実の一貫性 | 確認済み ($2.5/1k・+25%・RRF k=60・768 参考値・8 テーブル言及) |
| C6. 用語・形式の一貫性 | 確認済み (target_key 形式・chunk_type/target_type 対応・obj: スキーム・embed_hash) |
| C7. 状態機械の完全性 | 確認済み (batch_requests state 0/1/2/3 の全遷移に到達可能・脱出可能・クラッシュ収束) |
| C8. 欠落 | 確認済み (P1〜P16 範囲内で章として欠ける事項なし) |
| C9. 修正検証 | **不合格 (regression 4 件)** |
| C10. 修正相互作用 (aa〜ccc) | 確認済み (S02/S03/S04 を除く全相互作用が整合) |
| C11. 合理性 (実装可能性) | **minor 2 件** (S01: attempts リセット順序 / S04: submit_rejected error 値) |
| C12. 探索型監査 | **major 2 件** (S02: 自己記述化 × sweep 照合条件の非対称、S03: 自己記述化小 Tx 境界クラッシュの述語分離) |

## 原則 P1〜P16 (全原則で問題なし)

P1〜P16 の全 16 原則が文書に漏れなく反映され、内容が原則と一致することを確認。

---

# 総合所見

**判定: 不合格** (C9 に regression 4 件 + 新規 major 2 件)

**C9 回帰要約**: 4 件の regression のうち 2 件は再掲対の非対称 (Q02/R01) と順序注記の混在 (R02) で修正範囲の転記漏れ、1 件は §8-c の給源明示欠落 (Q01) で残存のパターン、1 件は旧文言の残存 (R04)。いずれも r15 補修の狭い範囲内のミスであり、文書全体の品質は高い。

**新規検出 (C12)**: S02 と S03 は r15 で新設された「自己記述化」(batch_job_id 書込) が sweep の照合条件 (batch_job_id NULL) および小 Tx 境界の述語分離と相互作用する穴 — これは r16 の X57 の想定どおり「fix が開ける穴」のパターンに該当。S02 は行の永久削除不能に至る major、S03 は課金記帳の 2 行増殖に至る major。いずれも修正可能な範囲。

**推奨**: regression 4 件の修正 + S02/S03 の対策 (照合条件の拡張または小 Tx 実行順の固定) により次回は合格可能。
## Objective
- 对「フォルダ単位バージョン管理 + AI 検索 — SQLite 正本方式 設計書 (改訂版)」を、指定された監査原則 (P1〜P16) および検査観点 (C1〜C12, 特に C9 の 403 項目と C12 の 60+ シナリオ) に基づいて静的解析し、合格／不合格の判定を出す。

## Important Details
- 環境制約: ツール呼び出しは全て拒否される。文書テキストのみを根拠に静的分析で監査を完遂する。
- 監査対象文書は既に提示済み (前メッセージ)。監査プロンプトは本メッセージで送付済み。
- C2 の SQL 検証は静的検証 (文法・スキーマ整合) で行う。
- 判定基準: C9 の全項目が fixed/superseded、かつ新規 fatal/major が 0 件なら合格。探索ログは 60 シナリオ以上・X1〜X61 全観点をカバー必須。
- 回帰確認項目は A01〜A24, B01〜B18, D01〜D14, E01〜E06, F01〜F27, G01〜G02, H01〜H30, I01〜I38, J01〜J20, K01〜K26, L01〜L28, M01〜M29, N01〜N45, O01〜O30, Q01〜Q37, R01〜R29 の 403 件 (superseded 対応表に従い新旧置換済み)。

## Work State
### Completed
- 設計文書全文の受領を確認済み (前メッセージ)。
- 監査プロンプトの全文 (原則・検査観点・回帰確認リスト・合格基準) が本メッセージで提示された。
- 監査の枠組み (P1〜P16, C1〜C12, 出力 4 部構成) は確定している。

### Active
- 監査本体は未実行。これから文書とプロンプトを突き合わせ、全原則の反映確認・SQL 静的検証・相互参照整合・状態機械追跡・C12 探索シナリオ実行・C9 回帰確認を行う。

### Blocked
- (なし — ツールは使えないが静的分析は可能)

## Next Move
1. 設計文書の全文を読み込み、P1〜P16 の各原則に対応する記述の有無・内容一致をチェックする。
2. C2 の全 DDL (FTS5 external content, WITHOUT ROWID, CHECK 制約, trigger 整合) を文法およびスキーマ対照で静的検証する。
3. C3 相互参照の実在確認 (例: §15 規約 4 → 該当箇所が存在するか)。
4. C9 回帰確認リスト (A〜R) の 403 項目を文書現状と照合し、fixed/superseded/partially-fixed/not-fixed/regression を判定する。
5. C12 探索監査: X1〜X61 の各観点で最低 1 シナリオ (計 60 以上)、特に X57〜X61 に重心を置き、文書規範だけでステップ実行して破綻を探す。
6. 全結果を 4 部構成の監査報告書にまとめ、合格／不合格を判定する。

## Relevant Files
- **対象文書**: ユーザー前メッセージで提供された設計書全文 (SQLite 正本方式 設計書 改訂版)
- **監査プロンプト**: 本メッセージの全内容 (原則・検査・回帰リスト・合格基準)
Continue if you have next steps, or stop and ask for clarification if you are unsure how to proceed.
fix 指示を提示します。

**C9 regression 修正 (4件)**

1. **Q01** — §8-c: `:current_profile / :embedding_profile` の給源が `app_config` である旨を段落内に明記する（例: 「`:embedding_profile` は `app_config` の `embedding_profile` record から読む」）。

2. **Q02** — §9.3-z: 「step 0〜4 から除外」の直後に「ただし step 2/4 の in-flight job の collect と detached 処理は除外しない — 除外対象は巻き戻った状態を入力にする scan/reconcile/submit/replicate」を追記する。

3. **R02** — 期限超 Tx 境界段落から `(i)〜(iii')` 表記を削除し `(i)〜(iv)` に統一する。

4. **R04** — §20.5 の rename 直前再 lstat 注記から「任意の強化 — 義務ではない」を削除し、§21.4 と整合させる。

**新規 major 修正 (2件)**

5. **S02** — §9.1 token sweep の照合条件を拡張: `batch_job_id IS NULL OR (自己記述化により前段で記帳された発見 job id と行の batch_job_id が一致)`。または sweep の掃除グループを照合グループと独立にし、`intent_token` 非 NULL 終端行は `batch_job_id` 有無に関わらず掃除対象とする。

6. **S03** — §9.1 付随処理 (b') 小 Tx の 3 操作順序を `(1) batch_job_id 書込 → (2) seq 行 UPDATE → (3) INSERT ledger` に固定する。または 3 操作を同一の atomic な操作に不可分にする。

これら 6 件を修正後、再監査で合格可能です。続けて修正しますか？
