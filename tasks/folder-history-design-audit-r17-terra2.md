不合格
target.md 全 3135 行を読了 — 最終行: 『```』

## 第 1 部 — 回帰確認（C9）

集計: fixed / superseded 430 件、partially-fixed 2 件、not-fixed / regression 0 件。

fixed: A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 / I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30 / Q01〜Q37 / R01〜R29 / S01〜S29 のうち、下記 superseded と S20・S24 を除く全 ID。

superseded（監査指示の対応表どおり）: F05→I14、F07→I15、F12→I16/I17、F21→I03/I04、H04→I31、H15→I08/I11、H18→I16、H22→I15、A11→I05/I06/I13/I14、H02→I32、I03/I04→J06、I05/I06→J01/J02、I09/I11→J03、I15→J04、I16/I17→J05/J01、I35→J13〜J16、J04→K01、J06→K02、J03→K10、J10→K09、J13→K16、J16→K13〜K15、I12→K04、D08→K20、A01→K25、K02→L01、K12/K13→L04、K06→L02、K09→L03、K14→L07、J07/K24→L09、K21→L20、K19→L13、L09/L28→M03/M09、L20→M04、L04/L21→M02、M09→N05/N06、M10→N10、M12→N38、M29→N15、M06/K08→N17、L07/M05→N16、L26→N14、M01→N09、M08→N28、M13→N30、N03→O05/O06、N04→O02/O03、N13→O21、N15→O04/O25、N36→O16、N39→O14、N40→O28、N28→O13、N07→O12、O28→Q01、O17→Q02、O02/O03→Q05/Q07、O04→Q06、O05→Q04、O07→Q09、O09→Q11/Q12、O11→Q13/Q36、O18→Q23、O19→Q24、O13→Q12、O30→Q37、Q02→R01、Q04→R02、Q09→R03、Q12→R04、Q03→R05、Q05/Q06→R06、Q10→R14、Q13/Q14→R15/R16、R06→S10/S15、R07→S19/S28、R08→S01、R13/R18→S02、R20→S03、R23→S04、R25→S06。

| ID | 判定 | 根拠（§ + 残存箇所） |
| --- | --- | --- |
| S20 | partially-fixed | §5.7 は「tool は annotation_schema 必須」「embedding は options 内 dimensions / metric 必須」「他 kind の必須フィールドを持つ record は拒否」と形状排他を要求する。一方 §4.1 は kind を分けず `profile_record = {"v":1,"model":…,"annotation_schema":{...},"options":{...}}` と直列化形式を固定する。embedding record は §4.1 に従えば annotation_schema を持って §5.7 に拒否され、除けば §4.1 の hash 入力を満たせない。さらに `distance_metric` と `metric` のフィールド名も一致しない。 |
| S24 | partially-fixed | §21.1 の「旧 root_path が不在」分岐には「旧 root_path 配下の fp_cache 行を DELETE」とあるが、直後の「旧 root_path は現存するが別の実体」の分岐は rebind のみを指示する。§20.4 も再発見時には「新 root_path 配下の fp_cache を無効化」としか書かない。旧パスが別フォルダに再利用された rebind では、旧 prefix の fp_cache を削除する規範が残っていない。 |

## 第 2 部 — 探索ログ（C12）

全 67 シナリオを実行した（X1〜X66 各 1 件、および自由探索 1 件）。

| # | 観点 | scenario（初期状態 → 操作列） | 結果 |
| --- | --- | --- | --- |
| X1 | 時系列 | 新規 PDF と別 target の OCR in-flight → create→edit→delete を 1 tick 間に連続させ次 tick を追跡 | 破綻なし |
| X2 | 異常入力 | eligible text=`foobar` → NUL を含む query `foo\0bar` を phrase 化して FTS 実行 | 破綻: T05 |
| X3 | FS 多様性 | case-sensitive volume 内の casefold child directory → `Report.pdf` の case-only rename | 破綻: T07 |
| X4 | 時刻 | 同一 ms の commit と時計後退 → created_at clamp と commit_hash tie-break を追跡 | 破綻なし |
| X5 | スケール | 100 万件の eligible chunk 全件が FTS に一致 → `:limit=1` で SQL を評価 | 破綻: T09 |
| X6 | 依存技術 | text=`Äbc` → 3 文字 query と 2 文字 fallback query を比較 | 破綻: T06 |
| X7 | スキーマ進化 | 旧 user_version DB → migration Tx の DDL 後・version 更新前で中断 → 再起動 | 破綻なし |
| X8 | セキュリティ | path traversal 名・symlink・特殊ファイル → walk / open / restore 経路を追跡 | 破綻なし |
| X9 | 運用・復旧 | `proposal.docx` を履歴保存済み → OCR submit を実行 | 破綻: T04 |
| X10 | 手動操作 | `.folder-history` の手動削除 → 次 tick と再登録誘導を追跡 | 破綻なし |
| X11 | r6 相互作用 | embedding profile record を §4.1 の直列化形式で保存 → §5.7 shape 検証 | 破綻: T03 |
| X12 | E2E | watch_root 登録→DOCX 追加→commit→OCR upload まで一気通貫 | 破綻: T04 |
| X13 | 未定義操作 | restore 直前に宛先が競合 → no-replace primitive 非対応 FS を想定 | 破綻: T08 |
| X14 | 資源・レート | Retry-After 無しの 429 → submit / collect の retry_not_before を追跡 | 破綻なし |
| X15 | 反証探索 | 主張「pending_deletes が偽 delete を防ぐ」→ dirty 早回しと 2 回 absent 観測を試行 | 破れず |
| X16 | r7 相互作用 | 相 1 snapshot 後に profile 変更 → intent 採用・collect を追跡 | 破綻なし |
| X17 | §21 E2E | server state=0 の相 2b 後クラッシュ → unregister→即再登録 | 破綻: T02 |
| X18 | 新テーブル | embedding profile の profiles 保存・hash 検証 → tool/embedding 形状を比較 | 破綻: T03 |
| X19 | 電源断 | 旧 token の相 2b 時刻記録後に時計補正 → requeue 後の新 token で再中断 | 破綻: T01 |
| X20 | 反証探索 | 主張「server 経路の未追跡 job は最大 1」→相 1 / 相 2a / 相 3 の各中断を試行 | 破れず |
| X21 | r8 相互作用 | floor 設定済み OCR と profile 切替 → 成果判定と再投入を追跡 | 破綻なし |
| X22 | fork E2E | PREPARED→HISTORY_CLEARED→ID_WRITTEN→APP_DONE の各中断から回復 | 破綻なし |
| X23 | 新 status | submit_rejected / client_exhausted / detached の status 読み手を追跡 | 破綻なし |
| X24 | 反証探索 | 主張「vec 差集合再充填は中断後も欠落を埋める」→ profile/次元変更中断を試行 | 破れず |
| X25 | E2E 経路 | in-place restore の宛先再検証 → no-replace 非対応 FS を想定 | 破綻: T08 |
| X26 | r9 相互作用 | submission_seq 継承→相 3→再作成の連番を追跡 | 破綻なし |
| X27 | fork journal | journal 残骸・破損・移動後回復を追跡 | 破綻なし |
| X28 | detached | unregister で server state=0 を detached 化 → 再登録前後を追跡 | 破綻: T02 |
| X29 | 保存名固定 | casefold child の case-only rename → file_versions 系列を追跡 | 破綻: T07 |
| X30 | 反証探索 | 主張「detached は課金を取りこぼさない」→ state=0 server の cancel→再登録を試行 | 破れた: T02 |
| X31 | r10 相互作用 | reconcile close・client_exhausted・seq 継承を交差させる | 破綻なし |
| X32 | fork phase | 各 phase × app 全損 / journal 破損 / 移動を追跡 | 破綻なし |
| X33 | 課金行列 | server の cancel 済み state=0 を detached→再登録へ遷移 | 破綻: T02 |
| X34 | 検索完全形 | eligible、LIKE 再 JOIN、ready 不一致 FTS-only、at_hash を組み立て | 破綻なし |
| X35 | 反証探索 | 主張「detached は課金を取りこぼさない」→ cancel 確定直後に再登録を試行 | 破れた: T02 |
| X36 | r11 相互作用 | ON CONFLICT と seq 継承、profile A→B→A の close を追跡 | 破綻なし |
| X37 | ready 追跡 | missing / fork / damaged の母数変動と synced NULL 化を追跡 | 破綻なし |
| X38 | fork 回復 | digest 不一致・中断中移動・app 全損を組み合わせる | 破綻なし |
| X39 | register / 検知 | 旧 root_path が別実体へ再利用 → 新位置へ rebind | 破綻: T10 |
| X40 | 反証探索 | 主張「close Tx は冪等記帳で abort しない」→同一 seq の再観測を試行 | 破れず |
| X41 | 記帳網羅 | cancel 確定した server state=0 を detached 経由で再登録 | 破綻: T02 |
| X42 | ready 動態 | damaged 復旧と profile 再構築を交差させる | 破綻なし |
| X43 | raw resolver | NFC / NFD / collision / raw 不在の restore・fsck を追跡 | 破綻なし |
| X44 | scoped 規約 12 | registered read、standalone read、conflict、step -1 を追跡 | 破綻なし |
| X45 | 反証探索 | 主張「state=0 server の課金は追跡される」→ cancel 後に token rotation を試行 | 破れた: T02 |
| X46 | 記帳済み判別 | token 記帳→rotation→job id 記帳の seq と述語を追跡 | 破綻なし |
| X47 | 期限超 Tx | 未来時刻の旧 job_create_started_at を残して新 token を採番 | 破綻: T01 |
| X48 | restore 保全 | raw 宛先競合時の no-replace fallback を追跡 | 破綻: T08 |
| X49 | 回復先行 | register / unregister / fork / restore 前の journal 回復を追跡 | 破綻なし |
| X50 | 反証探索 | 主張「b' が飛んでも sweep が記帳を回収する」→ close 後中断を試行 | 破れず |
| X51 | seq 行更新 | found / expired / client / detached の全 +1 経路を追跡 | 破綻なし |
| X52 | expired | expired→sweep→explicit retry の token・attempts を追跡 | 破綻なし |
| X53 | 4 照合点 | intent recovery / detached / b' / sweep の期限判定要素を比較 | 破綻なし |
| X54 | 回復ゲート | journal 有効・破損・不存在 × flag × 実体 ID を追跡 | 破綻なし |
| X55 | 単独検索 | embedding 混在・tool tie・空 markdown の現行決定を追跡 | 破綻なし |
| X56 | escape | G / `\G` / `\\G`、非 canonical 行、object 不在を往復 | 破綻なし |
| X57 | 自己記述化 | server state=0 の成果あり close → b' と reconciliation の同一 app Tx を追跡 | 破綻なし |
| X58 | detached terminal | cancelled / expired の attached 復帰→自動 submit を追跡 | 破綻: T02 |
| X59 | submit_rejected | 課金する provider と token sweep 除外の分岐を追跡 | 破綻なし |
| X60 | decoder | escape / un-escape / 厳密認識 / 再 materialize を総当り | 破綻なし |
| X61 | 伝播猶予 | 主張「provider 採用条件下で偽 expired を防ぐ」→過去側・未来側境界を試行 | 破れず |
| X62 | r16 相互作用 | requeue 後も旧 job_create_started_at が残る状態を構成 | 破綻: T01 |
| X63 | cancelled | state=0 server job の cancel 確定→再登録を構成 | 破綻: T02 |
| X64 | found IN | token 推定行と別 attempt の発見 job を交差させる | 破綻なし |
| X65 | no-replace | FAT / exFAT / 旧 NFS 等で primitive 非対応を構成 | 破綻: T08 |
| X66 | 横断非伝播 | §4.1↔§5.7 と §20.4↔§21.1 の要約・規範を比較 | 破綻: T03、T10 |
| F1 | 自由探索 | original DOCX hash と converter 出力 PDF hash を分離して upload 直前検査へ接続 | 破綻: T04 |

## 第 3 部 — 新規検出

| ID | 重大度 | 該当箇所（§ + 短い引用） | 問題 | 再現シナリオ（初期状態 → 操作列 → 壊れる状態） | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- | --- |
| T01 | major | §9.1: 「job_create_started_at = now を単独の小 Tx で記録」「相 1…新規 UUIDv7」「batch_job_id は NULL へ戻し」。相 1 に同列を NULL 化する規定がない。 | job_create_started_at は job 試行の時刻なのに、token rotation 後も旧試行の値を保持する。新 token の伝播猶予・未来 skew 判定が旧 job の時刻に汚染される。 | 初期: 旧 token T の相 2b 前に時計 13:00 で時刻を記録し、一時失敗。操作: NTP 補正で now=12:00 になり、T を期限超として N へ載せ直し、N の相 2b 前に中断。結果: 次の confirmed-absent は max(N の 12:00, 残存する 13:00) を用い、未作成の N を未来 skew 超過・期限超として記帳・attempt 消費し、上限で terminal 化できる。 | C7, C10, C11, C12; X19, X47, X62 | 相 1 で新 intent_token を書く全経路に job_create_started_at=NULL を加える。相 2b の呼出直前だけが当該 token の値を書けるようにする。 |
| T02 | fatal | §21.2: 「state IN (0,1) に cancel」「batch_job_id 非 NULL なら…記帳」。§9.1: 「相 2b 完了・相 3 前クラッシュの state=0 は job 作成済みであり得る」。 | state=0 server 行は実 job があっても batch_job_id=NULL である。cancel 成功後に job id の採用・記帳を規定せず terminal 化できるため、再登録時の token rotation が部分課金を永久に切り離す。 | 初期: server の相 2b は job J を作成済み、相 3 前クラッシュで state=0、batch_job_id=NULL、token=T。操作: unregister で J を cancel、直後に再登録して submit。結果: cancel は partial charge でも ledger は非 NULL 条件から漏れ、state=3・attempts<上限の行が相 1 で新 token に回転し、T と J を sweep が追跡できない。新 submit による再課金も可能。 | C7, C10, C11, C12; X17, X28, X30, X33, X35, X41, X45, X58, X63 | state=0 server の cancel 前に token 照合で J を採用し、job id・seq・冪等 ledger・terminal 化を同一 app Tx で確定する。少なくとも当該 token の sweep / 記帳完了前は再投入で token を上書きしない。 |
| T03 | major | §4.1: `profile_record = {"v":1,"model":…,"annotation_schema":{...},"options":{...}}`。§5.7: 「embedding…dimensions / metric 必須」「他 kind の必須フィールドを持つ record は拒否」。 | embedding profile に annotation_schema を必須にする直列化形式と、tool 専用必須フィールドとして拒否する shape 規範が両立しない。distance_metric / metric の名称も不一致。 | 初期: embedding profile を保存する。操作: §4.1 どおり annotation_schema を含めて hash 化し §5.7 で検証。結果: embedding record は他 kind 必須フィールドを持つため拒否される。省略すると §4.1 の profile_hash 入力が変わる。 | P2; C1, C10, C11, C12; X11, X18, X66 | §4.1 を kind 別 canonical schema にする。tool のみ annotation_schema、embedding のみ dimensions / distance_metric 等を許可し、§5.7 はその schema を参照する。 |
| T04 | major | §4: content_hash は「原本ファイルの bytes」。§6: 「Word 等…PDF へ変換してから投入」かつ「upload する objects/<content_hash> の bytes を再計算」。 | 原本 DOCX の hash と、OCR に送る PDF の bytes/hash が異なる。変換後 PDF の保存先、hash、サイズ検証、upload_id との対応が規定されず、原本再照合と OCR 対象形式を同時に満たせない。 | 初期: objects/H は DOCX 原本、変換 PDF は P。操作: OCR submit。結果: H を upload すれば PDF / image 限定に反し、P を upload すれば `objects/H` の再照合規範に反する。 | P6; C1, C10, C11, C12; X9, X12, F1 | source artifact（H）と transport artifact（P）を分離して定義する。変換 PDF の一時・保存寿命、P の hash / magic / size 再照合、batch_requests との対応を明記する。 |
| T05 | major | §11.2: query は内部 `"` を二重化して phrase 化する、とだけ規定し NUL を拒否しない。 | FTS5 query parser へ NUL を渡せる。引用符エスケープだけでは FTS 構文エラーを防げず、同一 SQL の KNN 経路も失敗する。 | 初期: eligible chunk=`foobar`。操作: query=`foo\0bar` を規定どおり phrase 化して SQLite FTS5 MATCH に bind。結果: in-memory SQLite で `unterminated string` となり、検索全体が abort する。 | C11, C12; X2 | 入力境界で U+0000 を拒否し、制御文字の許容・正規化規則を定める。拒否時は SQL を実行せず status と空結果を返す。 |
| T06 | major | §5.5: `tokenize='trigram'`。§11.2: 3 文字未満は LIKE fallback、「LIKE と同じ case 折り畳み」。 | trigram FTS の Unicode case-insensitive 挙動と SQLite 既定 LIKE の ASCII 限定 case-insensitive 挙動が異なる。短語 fallback で非 ASCII の検索結果が 3 文字境界により変わる。 | 初期: text=`Äbc`。操作: `äbc` を FTS、`äb` を短語 LIKE fallback で検索。結果: in-memory SQLite で FTS5 trigram の quoted MATCH は 1 件、LIKE `%äb%` は 0 件となり、同じ語の短語検索が偽陰性になる。 | C11, C12; X6 | FTS と fallback の双方に同一の Unicode casefold / 正規化済み検索列を用いるか、同じ Unicode 照合規則を明示して実装する。 |
| T07 | major | §20.5: per-directory case 感度への備えを「同一 dir 内の case 違い併存を検出したら sensitive」と定義する。 | globally case-sensitive な volume 内の casefold directory は case 違いの 2 実体を併存できないため、併存検出では case-insensitive を検出できない。 | 初期: ext4 等の case-sensitive volume に casefold 属性付き child directory。操作: `Report.pdf` を `report.pdf` へ rename。結果: volume 属性だけで sensitive と扱われ、同一ファイルが delete/create の別履歴系列へ分裂する。 | P16; C1, C11, C12; X3, X29 | directory ごとの casefold / flag を取得して判定する。取得不能時は保守的に扱う規範と、既存系列との照合手順を定義する。 |
| T08 | minor | §21.4: 「可能なプラットフォームでは no-replace rename」「EEXIST 相当 = 中止・再試行」。 | primitive 非対応時の capability 判定と errno 別の fallback が未定義である。安全な実装と通常 rename に落ちる破壊的実装の双方が文書に適合し得る。 | 初期: raw 不在確認後、ユーザーが宛先を新規作成。操作: FAT / exFAT / 旧 NFS 等で no-replace primitive が ENOSYS/EOPNOTSUPP/EINVAL。結果: 通常 rename へ落ちればユーザー内容を上書きし、拒否実装なら復元不能となる。 | P16; C1, C11, C12; X13, X25, X48, X65 | 非対応・各 errno の必須動作を定める。安全側なら restore を中止して tmp を保持し status を出し、通常 rename への fallback を禁止する。 |
| T09 | major | §11.2 の fts_hits は全 MATCH 行へ ROW_NUMBER、fused は UNION ALL / GROUP BY、最後にのみ `LIMIT :limit`。同節は `LIMIT -1` が「100 万件規模の FTS ヒットを全件返してメモリを食い潰す」とする。 | 外側 LIMIT は window rank、GROUP BY、最終 sort より後であり、中間 FTS 候補数を制限しない。limit 検証は返却行数しか抑えない。 | 初期: 100 万 eligible chunk が同一 query に一致。操作: `:limit=1` で掲載 SQL を実行。結果: 全 FTS 行の rank 化・fusion・集約・排序が先に必要になり、巨大な一時領域・メモリを消費する。 | C11, C12; X5 | FTS 候補に `:k_fts` の明示上限を、fusion 前に適用する。不完全性を status に出すか、上限超過を資源エラーとして規定する。 |
| T10 | minor | §21.1 の missing 分岐は「旧 root_path 配下の fp_cache 行を DELETE」。同節の「旧 root_path は現存するが別の実体」分岐は rebind のみ。§20.4 は新 root 配下の無効化のみ。 | rebind の一方の正規分岐で旧 prefix の fp_cache が永久に孤児化する。 | 初期: `/old` 配下を追跡し fp_cache がある。操作: repo を `/new` へ移し、`/old` を無関係なフォルダとして再利用して rebind。結果: `/old` 配下は追跡 walk の主体でなく、mark-and-sweep も届かず fp_cache が残る。 | P16; C1, C10, C11, C12; C9-S24; X39, X66 | old root が不存在か別実体かを問わず、rebind の app Tx で旧 root_path prefix の fp_cache を DELETE する。 |

## 第 4 部 — 確認済みの列挙

検出 0 件として確認済み: C2、C3、C4、C5、C6、C8。

検出 0 件として確認済み: P1、P3、P4、P5、P7、P8、P10、P11、P13、P14、P15。