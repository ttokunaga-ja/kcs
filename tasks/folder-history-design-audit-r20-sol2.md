不合格
target.md 全 3348 行を読了 — 最終 2 行: 『embedding profile 変更       : §8 (現行設定の更新のみ — 宣言的収束)』『```』

## 第 1 部 — 回帰確認

全 494 項目を確認した。V01 / V02 / V09 を除く 491 項目は fixed、または監査プロンプトの対応表どおり superseded（矢印先は fixed）である。

対象範囲: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 / T01〜T18 / U01〜U24 / V01〜V20。

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|---|---|---|
| V01 | regression | §6 は「upload した入力（原本 — Office 文書は変換 PDF）」へ統一している一方、§9.1 相 2a に旧表現「TTL まで機密原本が追跡不能で残る」が残る。Office 文書で残留する実体は変換 PDF であり、再掲間で upload 対象語が不一致。 |
| V02 | regression | §9.1 DDL は completed_at を「state が 2/3 へ確定する全ての UPDATE」で書くと列挙する一方、直後に「書込点は §10 collect」と限定する旧コメントが残る。規範文と DDL コメントが矛盾。 |
| V09 | regression | §20.5 は「scan_cache に…syntax_fail_count / first_failure_at を記録し（列追加）」と要求するが、§9.1 の `CREATE TABLE scan_cache` は `verified_at` の直後に PRIMARY KEY で閉じ、両列を持たない。対象 DDL を in-memory SQLite に適用後、規範どおりの UPDATE は `no such column: syntax_fail_count` となった。 |

## 第 2 部 — 探索ログ

| # | 観点 | シナリオ（初期状態 → 操作列） | 結果 |
|---:|---|---|---|
| 1 | X1 | v1 をコミット済み → tick 間に編集・削除 → 2 回の完全 walk | 中間編集はスナップショット外、v1 保持と pending delete が成立。問題なし |
| 2 | X2 | `--\>`、偽 img block、存在しない hash、case 衝突名を入力 → OCR 保存・再解析 | field escape・本文 escape・実在検証・name_collision が分離。問題なし |
| 3 | X3 | NFD 名を持つフォルダを case-sensitive から insensitive FS へ移動 → rebind・scan | resolver と既存系列 tie-break で決定的に収束。問題なし |
| 4 | X4 | 時計後退中に同一 ms で複数変更 → コミット・単独 tool 選択 | created_at clamp、commit_hash、tool hash tie-break が機能。問題なし |
| 5 | X5 | 10 万ファイル・100 万 chunk → walk、FTS、KNN、全置換 | walk は残るが hash・FTS・KNN に上限と分散規範がある。問題なし |
| 6 | X6 | 2 文字日本語、2^53 超 size、異なる vec metric → 検索・直列化 | LIKE fallback、10 進文字列、metric 再作成で処理可能。問題なし |
| 7 | X7 | 新規 DB を掲載 DDLで作成 → 構文検証失敗を永続化 | scan_cache に必要列がなく実装不能。W04 を検出 |
| 8 | X8 | `../x`、symlink 差替え、他ユーザー可読 ACL → register・restore | name_invalid、dirfd、O_NOFOLLOW、DACL fail-closed が作用。問題なし |
| 9 | X9 | object fsync 後／metadata commit 後／app 更新前で順にディスク満杯 | 未参照 object、成果先行、次 tick close に収束。問題なし |
| 10 | X10 | `.folder-history` 手動削除、metadata のみ旧版復元、部分同期 | damaged、step -1 regressed、fsck が分離検出。問題なし |
| 11 | X11 | NFC 変換、FTS view、floor 更新、profile 変更を同 tick で実施 | 各変換点と app→metadata の floor 順序は整合。問題なし |
| 12 | X12 | watch_root → register → commit → OCR → embed → replicate → search → restore | 各段の出力から次段の入力を追跡可能。問題なし |
| 13 | X13 | 全ての「status」「明示操作」「明示解決」を §21 へ逆引き | abandon を含め操作自体は定義済み。問題なし |
| 14 | X14 | submit・collect が Retry-After 無し 429 → dirty 早回し tick | 共通 backoff が retry_not_before に残る。問題なし |
| 15 | X15 | 主張「構文検証スキップは有界」→ 新規 DB で3回失敗を記録 | 必須列欠落で主張を破った。W04 を検出 |
| 16 | X16 | 1 repository の JSONL を複数 job へ分割 → 各境界でクラッシュ | 分割前採番と job 単位 token により一意。問題なし |
| 17 | X17 | register 途中クラッシュ → fork → restore → unregister・再登録 | journal、退役、保全 commit、full replicate で収束。問題なし |
| 18 | X18 | profiles 改変、pending delete、scan 構文失敗を同時発生 | profile/pending は回復するが scan counter を保存不能。W04 を検出 |
| 19 | X19 | object rename、相 2b、fork 各 phase 直後で電源断 | dir fsync、intent 回復、phase journal が再駆動。問題なし |
| 20 | X20 | 主張「server 重複課金有界」「profile 変更収束」「fork 耐久」を反証試行 | 明記された provider 条件内では破れず。問題なし |
| 21 | X21 | profile A→B、floor 再生成、vec 部分充填を交錯 | 通常経路は収束するが token 残存時の retry budget は X78 で破綻。問題なし |
| 22 | X22 | fork の各 phase でフォルダ移動・app 全損 → journal 走査 | current realpath と phase/id 表で一意に再開。問題なし |
| 23 | X23 | app_config、ledger、detached、name status を全 reader から参照 | 読み手と状態値の対応は定義済み。問題なし |
| 24 | X24 | 主張「vec 差集合は全クラッシュ位置を回収」→ CREATE／充填途中で停止 | 次 tick の差集合が欠落を補完。問題なし |
| 25 | X25 | フォルダ未接続で横断検索、delete 版 restore、watch_root 解除 | app_config、宛先拒否、folders 起点 walk が機能。問題なし |
| 26 | X26 | attempts reset、submission_seq、ledger を profile 往復で追跡 | seq は単調、attempts のみ reset される。問題なし |
| 27 | X27 | journal 書込から削除まで全境界でクラッシュ → bootstrap | phase と実 id の組で再開可能。問題なし |
| 28 | X28 | detached を state 0/1/2/3 ごとに生成 → collect・掃除・再登録 | payload 破棄、記帳、PK 再利用が定義済み。問題なし |
| 29 | X29 | case-only rename後、別ボリュームで2実体化 → scan・restore | 初出表記固定と raw resolver が同じ系列を選択。問題なし |
| 30 | X30 | 主張「seq 継承・client 上限・fork・保存名固定」を反証試行 | 通常系列では破れず。問題なし |
| 31 | X31 | 行削除→再作成、reconcile close、client_exhausted を連続実行 | ledger MAX 継承と冪等 close が成立。問題なし |
| 32 | X32 | 各 fork phase × 通常クラッシュ／app 全損／journal 破損 | 不可能組合せを含め停止・再開先が定義済み。問題なし |
| 33 | X33 | server/client × 全 terminal reason × close 経路を追跡 | rejection の provider 条件を含め 0/1 ledger 行に収束。問題なし |
| 34 | X34 | 掲載 FTS DDL・trigger・rank=1 integrity-check を SQLite 3.51 で実行 | INSERT/MATCH/DELETE/integrity-check が成功。問題なし |
| 35 | X35 | 主張「seq 再作成衝突なし」「reconcile 記帳」「cancel 自動再投入なし」を反証 | 記載どおりの順序では破れず。問題なし |
| 36 | X36 | profile A→B→A で同一 seq を複数 close が再観測 | ON CONFLICT DO NOTHING が同一課金だけを吸収。問題なし |
| 37 | X37 | missing/damaged を除外して ready → 復帰・再同期 | synced 条件と差集合により復帰分を補完。問題なし |
| 38 | X38 | fork 中に移動、journal digest 不一致、app 全損 | 有効／破損／一時不能が混同されない。問題なし |
| 39 | X39 | register 中の一時 EIO、旧 root 再利用、型違い置換 | 保留、rebind、absent 判定が分離。問題なし |
| 40 | X40 | 主張「raw resolver・scoped read・step -1 が偽 provenance を防ぐ」を反証 | 規約12とdirfd条件内では破れず。問題なし |
| 41 | X41 | 全 terminal 理由を server/client・attached/detached で再計算 | seq と記帳値規則は一貫。問題なし |
| 42 | X42 | damaged 中に A/B だけ ready → C 復帰 | ready は設定時被覆、C は次 replicate の差集合へ入る。問題なし |
| 43 | X43 | NFD/NFC/両方/無し × sensitive/insensitive の resolver 行列 | raw 選択と不在分岐が一意。問題なし |
| 44 | X44 | 登録済み path 差替え、一時 EIO、standalone copy、z 後退 | conflict／保留／provenance／wipe が分離。問題なし |
| 45 | X45 | 主張「unknown は二重 job を作らない」「ready は空 index に騙されない」を反証 | provider 採用条件内では破れず。問題なし |
| 46 | X46 | token 推定記帳→遅延 found→正規 close | IN(job id, token) と自己記述化で二重記帳なし。問題なし |
| 47 | X47 | 期限超 (i)〜(iv) の各位置でクラッシュ → retry | DB 書込1 Txにより偽 expired を回避。問題なし |
| 48 | X48 | 未取り込み working 編集中に in-place restore | 保全 commit、再 lstat、no-replace が喪失を防止。問題なし |
| 49 | X49 | 未完 fork の後に全 §21 操作を順次要求 | 回復先行ゲートと破損例外が一意。問題なし |
| 50 | X50 | 主張「token 記帳増殖なし」「decoder 可逆」「restore は編集を消さない」を反証 | 指定された通常系列では破れず。問題なし |
| 51 | X51 | found／期限超／client／detached の seq 更新を同一行で連続実行 | 各別 attempt が異なる seq を取得。問題なし |
| 52 | X52 | expired terminal → sweep →明示 retry | token cleanup 後に新 lifecycle へ遷移。問題なし |
| 53 | X53 | 4照合点で found/unknown/期限内/期限超を全比較 | scope 問題を除き期限・猶予・記帳規則は対称。問題なし |
| 54 | X54 | journal 有効/破損/無 × flag 有無 × id old/new/第三 | 各組合せに回復・保留・damaged がある。問題なし |
| 55 | X55 | embedding 混在、tool 同時刻、全 generated_at 未来 | KNN停止、tool tie-break、未来警告が機能。問題なし |
| 56 | X56 | 非 canonical `\![...](obj:bad)` を保存→再解析 | 緩い un-escape と厳密 image 認識が両立。問題なし |
| 57 | X57 | found 記帳後に一覧消滅 → sweep 再訪 | batch_job_id 自己記述化で token 記帳へ分裂しない。問題なし |
| 58 | X58 | detached terminal 後、削除前に再登録 | attached に戻り成果なしなら意図された再投入。問題なし |
| 59 | X59 | 課金される submit_rejected を2回明示 retry | seq+1 記帳により両課金が残る。問題なし |
| 60 | X60 | G／`\G`／`\\G`、偽hash、object不在を往復 | escape・un-escape・認識の3述語が分離。問題なし |
| 61 | X61 | 主張「伝播猶予で未追跡 job は有界」を遅延・保持境界で反証 | 2つの provider 採用条件を満たす範囲では破れず。問題なし |
| 62 | X62 | job_create_started_at 記録直後クラッシュ → 同 scope 再照合 | max 起点と migration backfill は機能。scope 切替は X75 で破綻 |
| 63 | X63 | cancel → terminal →削除前再登録 | attempts 上限と明示 retry 条件が一貫。問題なし |
| 64 | X64 | token 推定行がある状態で別 attempt の job を found | token rotation 後は別 token/seq となり過吸収しない。問題なし |
| 65 | X65 | no-replace 非対応・EEXIST・EINVAL を順に返す FS | 非対応判定と再 lstat fallback が定義済み。問題なし |
| 66 | X66 | 規範文・DDLコメント・再掲の伝播を横断比較 | completed_at と upload 対象語の残存を検出。W05 / W06 |
| 67 | X67 | rotation/abandon 時に入力と JSONL upload が未清掃 | token を先に失い JSONL 掃除不能。W02 を検出 |
| 68 | X68 | cancel→明示 retry→再 cancel を反復 | seq と ledger は反復ごとに分離。問題なし |
| 69 | X69 | fts_cap 境界で同順位多数 → RRF | 内側 ORDER BY と chunk_uid で決定的。不足は設定トレードオフ。問題なし |
| 70 | X70 | converter 更新、旧 converter 消失、変換失敗 | tool profile 分離と convert_failed／一時失敗が機能。問題なし |
| 71 | X71 | state=0 server requeue と client dispatch を rotation guard 外で反復 | 各自身の記帳経路が先行し自己循環なし。問題なし |
| 72 | X72 | unknown job を abandon → upload cleanup →後日 job 可視化 | ledger は残るが JSONL cleanup key が消える。W02 を検出 |
| 73 | X73 | convert_failed 後に tool profile 更新 | 新 target_key で再判定、旧 terminal と独立。問題なし |
| 74 | X74 | 構文失敗に EIO を挟み3回/24hを追跡 | reset規範はあるが保存列がない。W04 を検出 |
| 75 | X75 | scope A の行を profile B で再利用 →相1後・相2b前クラッシュ | stale scope が unknown を強制。W01 を検出 |
| 76 | X76 | token T・JSONL upload 残存中に abandon | token NULL 化後に filename 探索不能。W02 を検出 |
| 77 | X77 | 10万登録フォルダで fp 一致 → journal preflight、一時 EIO | walk 自体は既定コストで、検査失敗は次 tick 再試行可能。問題なし |
| 78 | X78 | state=2・未完 token に floor 再生成 → guard found →新 submit | reset 後に旧 attempt が加算され retry budget が縮む。W03 を検出 |

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
|---|---|---|---|---|---|---|
| W01 | major | §9.1 相1「batch_job_id / error / completed_at / job_create_started_at も NULL へ戻す」／照合「scope_id と現照会 scope の比較」「不一致は unknown」 | 相1が `scope_id` を初期化しない。前 lifecycle の scope が新 token に残り、`job_create_started_at=NULL` で相2b未着手と証明できる場合も scope 不一致が unknown を強制する。また安定した scope ID を公開しない provider の canonical 値も未定義。 | kind=2 行に scope A が残る → profile を scope B へ変更 → 相1が新 token と B の snapshot を書くが scope=A のまま → 相2b前にクラッシュ → B の一覧は scope 不一致で永久 unknown → 実 job が存在しないのに stalled、abandon で推定課金行まで作る。 | C7 / C8 / C10 / C11 / C12 / X75 | 相1の NULL 戻しへ `scope_id` を追加する。`job_create_started_at IS NULL` は scope/list照合より先に「相2b未着手」と判定する。adapter に安定した完全修飾 scope ID を必須化し、提供不能 provider は server-side intent 回復の採用対象外とする。 |
| W02 | major | §6「JSONL の id は upload_id 列に持たず…token 埋込の filename 一覧で発見・削除」／§9.1 abandon「intent_token NULL 化。upload 残骸の掃除は通常の後始末が引き継ぐ」 | abandon が JSONL upload の唯一の探索キーを掃除前に消す。input upload は upload_id で掃除できても、JSONL upload は通常の後始末から到達不能になる。 | JSONL と入力を token T 付きで upload → job照合が恒久 unknown → abandon → Tx が intent_token を NULL → step 4.5 は T を復元できず JSONL file id を列挙できない → provider TTL まで機密を含む JSONL が残留。 | C7 / C8 / C10 / C11 / C12 / X67 / X72 / X76 | `cleanup_token` を別列で耐久保持し、JSONL/job残骸の削除または404確認後にのみ消す。あるいは JSONL upload id 自体を永続化する。`intent_token` の回復用途終了と残骸探索用途を分離する。 |
| W03 | major | §5.3「attempts = 0 にリセット」／§9.1 rotation guard「state IN (2,3)…先に照合・記帳」／token sweep found「attempts を +1」 | floor 明示再生成が retry budget を先にリセットし、その後の guard が前 lifecycle の未追跡 job を加算するため、新 lifecycle が 0 から始まらない。 | state=2・batch_job_id=NULL・token T 残存（reconcile close後、sweep前）→ 明示再生成で floor設定・attempts=0 → guard照合で旧 job J が found、attempts=1 → 新 job の相3で attempts=2 → 新 lifecycle の初回失敗が本来より早く terminal になる。 | C7 / C10 / C11 / C12 / X78 | rotation guard を floor/attempts reset より先に完了させる。難しい場合は guard 完了後、相1と同じ Tx で `floor_generated_at IS NOT NULL` の行を再度 attempts=0 にしてから新 attempt を開始する。 |
| W04 | major | §9.1 `CREATE TABLE scan_cache`／§20.5「syntax_fail_count / first_failure_at を記録し（列追加）」 | 規範の永続カウンタを保存する列が実 DDL にない。新規 DB では有界スキップを実装できず、追加設計なしには SQL が成立しない。V09 と同根。 | 掲載 DDLで新規 DB 作成 → 安定した破損ファイルの構文検証が失敗 → counter UPDATE → `no such column: syntax_fail_count` → step 0 が毎回失敗し、3回/24h後の bytes commit に到達不能。 | P16 / C1 / C2 / C4 / C8 / C11 / C12 / X7 / X15 / X18 / X74 | scan_cache に非負整数 `syntax_fail_count` と nullable INTEGER `first_failure_at` を追加し、0件時のNULL関係、reset、既存DB migrationをDDLと§14へ明記する。 |
| W05 | major | §9.1 completed_at DDL「確定する全ての UPDATE」対「書込点は §10 collect」 | 同一 DDL コメント内で書込範囲が矛盾する。後者に従う実装では submit_rejected、expired、cancelled、abandoned 等が completed_at=NULL のまま残る。V02 と同根。 | upload 4xx → state=3 submit_rejected・attempts上限 → collectを通らない → completed_at未設定 → status が正しく閉じた行を恒久滞留として表示。 | P9 / C3 / C7 / C9 / C11 / X66 | 「書込点は §10 collect」を削除し、state=2/3へ遷移する全分岐で `completed_at=now` を同時更新する規範だけに統一する。 |
| W06 | minor | §6「upload した入力（原本 — Office 文書は変換 PDF）」対 §9.1「TTL まで機密原本が…残る」 | Office 文書で provider に残るのは変換 PDF であり、upload 対象語の再掲が不正確。V01 と同根。 | DOCXをPDFへ変換してupload → job作成前クラッシュ → status/運用文が残留物を「原本」と報告 → 実際の削除・開示対象との説明が食い違う。 | P6 / C6 / C9 / X66 | 「機密を含む upload 入力（Office 文書は変換 PDF）」へ統一する。 |

## 第 4 部 — 確認済みの列挙

- C5: 確認済み・問題なし。料金 $2.5/1,000ページ、+25%、RRF k=60、768の参考値扱い、metadata.sqlite 8テーブルの記述は一致した。
- P1〜P4、P7、P11〜P15: 確認済み・問題なし。
- C2補足: W04以外の掲載 core DDL、GENERATED列、WITHOUT ROWID、FK、chunks FTS trigger、external-content view、rank=1 integrity-check は in-memory SQLite 3.51.0で構文・基本動作を確認した。