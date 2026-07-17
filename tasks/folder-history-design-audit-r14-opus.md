# folder-history 設計監査 r14 — 裁定報告 (オーケストレータ統合)

対象: `docs/research/folder-history-sqlite-design.md` (2762 行)
日付: 2026-07-16
体制: 回帰確認 4 エージェント + SQL 静的検証 1 + 探索 4 エージェント (X1-15 / X16-30 / X31-45 / X46-50) + オーケストレータ深掘り (X46-50 + 自由探索)

---

## 合否判定

```
前提条件   : 満たす — 探索ログ 150+ シナリオ (X1〜X50 全観点実行済み。50 シナリオ下限を大幅超過)
判定       : 不合格
不合格事由 : (1) C9 の O28 が partially-fixed (§5.7 L432-433 / §8-c L651-652 に「§5.7 record から読む」残存)
             (2) 新規検出に major 2 件 (Q01: (b')/sweep 期限判定欠落 → 課金記録の永久欠落、
                 Q02: フォルダ単独検索の :current_tool 決定規則の欠落)
```

r13→r14 で破壊型 regression は 0 (4 ラウンド連続)。fatal は 0。major 2 件はいずれも
「r13 が新設した規範の内部に閉じた欠陥」(期限判定の照合点非対称) と「テーブル分離設計の
帰結として長く伏在した穴」(単独検索の tool 決定) であり、r12→r13 と同じく「新設規範の内側」に
問題が寄っている。

---

## 第 1 部 — 回帰確認 (C9 / 337 項目)

### fixed / superseded (336 項目)

- **A01〜A24**: A01(→K25) superseded、他すべて fixed
- **B01〜B18**: すべて fixed
- **D01〜D14**: D08(→K20) superseded、他すべて fixed
- **E01〜E06 / F01〜F27 / G01〜G02**: F05(→I14)/F07(→I15)/F12(→I16・I17)/F21(→I03・I04) superseded、他すべて fixed
- **H01〜H30**: H04(→I31)/H15(→I08・I11)/H18(→I16)/H22(→I15) superseded、他すべて fixed
- **I01〜I38**: I04/I05/I06/I09/I11/I12/I15/I16/I17/I35 superseded、他すべて fixed
- **J01〜J20**: J03(→K10)/J04(→K01)/J07(→L09)/J10(→K09)/J13(→K16)/J16 superseded、他すべて fixed
- **K01〜K26**: K06/K13/K14/K19/K21/K24 superseded、他すべて fixed
- **L01〜L28**: L26(→N14)/L28(→M03+M09) superseded、他すべて fixed
- **M01〜M29**: M29(→N15) superseded、他すべて fixed
- **N01〜N45**: N03/N04/N07/N13/N15/N28/N36/N39/N40 superseded、他すべて fixed
- **O01〜O30**: O28 を除きすべて fixed (下記参照)

禁止パターンの不在を grep で確認済み: `7 テーブル` / `agg_embedding_profile_hash'` /
`:current_tool_profile_hash` / attempt キーの UNIQUE / 「二重計上を構造的に排除」/
「未実行として無条件再実行」/「state=0 は即削除」/「判定だけ折り畳み、保存は readdir 表記」/
cosine 固定リテラル — いずれも 0 件または否定文脈のみ。superseded 項目の非置換中核 (I03 の
cost_ledger 追記専用・cost_usd/pages 列なし、K09 の実行前計上 + server 限定明記、M06 の detached 採用
seq+1、K13 の §21.2 委譲 等) もすべて健在を確認。

### 問題項目 (1 件)

| ID | 判定 | 根拠 (§ + 行 + 引用) |
| --- | --- | --- |
| O28 | **partially-fixed** | 主修正点は適用済み (§8 冒頭 L632「app_config の embedding_profile record から読む。§5.7 は履歴の保管庫で新規フォルダでは空」/ §10 step3 L1503-1505「参照元は app_config の embedding_profile record」)。**残存 2 箇所**: (a) §5.7 L432-433「§8 の起動時検査・embedding_vec の次元照合も dimensions を**この record** (=profiles 表) から読む」/ (b) §8-c L651-652「vec 表の次元と距離 … を現行 profile **(§5.7 record)** と照合し」。O28 の禁止事由「新規フォルダで §5.7 が空で実行不能」がこの 2 箇所にそのまま当たり、§8 冒頭・§10 step3 の修正文と同一文書内で矛盾する |

---

## 第 2 部 — 探索ログ (C12 / 150+ シナリオ)

X1〜X50 の全 50 観点を実行。各観点 1 シナリオ以上を手動ステップ実行。以下は担当別の集約
(問題なしのシナリオも沈黙と区別して記録)。Q## は第 3 部の新規検出に対応。

### X1〜X15 (34 シナリオ / 検出: Q02・Q06・Q07・Q08・Q14)

作成→編集→削除の 1-tick 圧縮 / OCR in-flight 中の削除改名 / 2 台コピー双方編集の書き戻し (z 検出) /
明示再生成×tool 変更の交錯 / obj: 偽装本文 / annotation 値の往復エスケープ / 0 バイト・制御文字名・
hardlink / 手書き偽造 Markdown / case 系列の insensitive 移動 [Q06] / NFC×fp 変換点 / 時計後退クランプ /
同一 ms タイブレーク / 10 万ファイル walk / trigram 短語 fallback / vec0 制約 / i64 超 JCS /
migration 混在 / grammar v2 混在 [Q08] / 権限・traversal / ディスク満杯 3 点 / bit-rot 検出 /
metadata のみ復元 / .folder-history 手動削除 / floor×ローカル変換 / backfill OFF×tool 変更 /
E2E 一気通貫 [Q02] / 初回 agg_vec 不在 / 明示操作総点検 [Q14] / 429 全経路 / 反証 8 主張 (全て破れず)

### X16〜X30 (31 シナリオ / 検出: Q01(関連 C4)・Q04・Q05・Q09・Q10・Q11・Q12・Q13・Q15)

2 相 submit×1job=1repo / reconcile 縮小の閉じ漏れ / cost_ledger 追記点網羅 / floor NULL 戻し伝播 /
profile 内 attempts 計数 / batch_job_id NULL 化×idx / upload_id 上書き追跡 / register クラッシュ→
damaged / fork 後派生保持 / restore→scan / unregister→再登録 / profiles 孤児 / pending×walk 不完全 /
cost_ledger app 全損意味論 [Q11] / dir fsync 網羅 / migration×journal_mode / 2 相各境界クラッシュ /
§21 各操作クラッシュ / 月次配賦 ts [Q09] / 期限超 upload 残骸 [Q10] / upload_cleaned 404 [Q12] /
vec 孤児 collect [Q13] / app_config 未設定窓 [Q15] / token sweep 記帳値二重定義 [Q04] /
反証 X20/X24/X30 (月跨ぎ配賦のみ破れ→Q09、他は破れず)

### X31〜X45 (38 シナリオ / 検出: Q01・Q03・Q05)

seq 継承×ledger 全経路 / ledger 空 COALESCE / 同 tick 複数採番 / submit_rejected×明示 retry 往復 /
client_exhausted×detached 境界 / profile A→B→A 記帳衝突 / fork 全 phase×クラッシュ /
watch_roots 外移動+register [Q05] / journal digest 不一致 / 課金記帳 (server/client)×全 error×
全 close の網羅行列 [Q01] / §11.2 掲載 SQL 実行可能性 / ready 未更新窓 / 単独検索部分 KNN /
冪等記帳×seq×detached+1 逆検証 / (b') 後クラッシュ×sweep 再駆動 / ready 母数動態 / synced 全 NULL 化 /
flag 掃除 3 条件 / app 全損×移動×digest / register/detached/検知の相互作用 / raw 解決 3×4×2 行列 /
scoped 規約 12×step-1 / 反証 X35/X40/X45 (fork 再開・server close (b') のみ破れ→Q01/Q05、他破れず)

### X46〜X50 (12+ / オーケストレータ深掘り 35+ = 47+ シナリオ / 検出: Q01・Q03・Q04)

記帳済み判別述語×冪等記帳×seq 連番の全数 / 期限超記帳→載せ直し→相 3 の連番一貫 /
(b') 記帳後 sweep 再訪の述語省略 / client 再実行前記帳と述語の関係 / 述語 SELECT→INSERT の
単一 writer 直列性 / 期限超同一 Tx×token rotation×detached / attempts+1×profile 数え直しの順序 /
detached 期限超記帳→削除→再登録 seq 継承 / tool_changed ガード適用順 / restore 保全×§20.5×resolver /
保全安定確認失敗 / 保全=restore 内容の no-op / raw 解決×保全の collision / 回復先行×全 §21 操作 /
journal damaged で回復不能時の後続操作 [Q14] / 二重 fork 単一 flag / 反証 X50 8 主張
(記帳済み判別・(b') sweep 回収・restore 保全・明示操作反転 が条件付きで破れ→Q01/Q03/Q04/Q05、他破れず)

**探索の総括**: 中核機構 (2 相 submit・intent 回復三値照合・reconcile 縮小・冪等 close・宣言的
profile 収束・fork journal 再開・detached 記帳・保存名固定・raw 解決・step -1・scoped 規約 12) は
クラッシュ総当りで破れなかった。検出はすべて「r13 の新設規範の照合点非対称」(Q01)、「規範間の
食い違い」(Q04・O28)、「終端経路・分岐の欠落」(Q02・Q03・Q05・Q10-Q16) に集中。

---

## 第 3 部 — 新規検出

### major

| ID | 該当箇所 | 問題 | 再現シナリオ | 根拠 | 修正案 |
| --- | --- | --- | --- | --- | --- |
| **Q01** | §9.1 (b') L1135-1141「実在すれば…冪等記帳する…unknown…保持」/ token sweep L1078-1086「job 実在かつ未記帳なら…記帳…その後…掃除を試み…intent_token を NULL へ戻す」 | close 側 2 照合点 ((b')・sweep 前段) の job 照合が found/unknown の 2 分岐のみで、**confirmed-absent の期限判定が無い**。intent 回復 (L992-1007) と detached (b) (L1105-1110) には r13 で入った期限判定 (保持期限超は「未作成と断定せず記帳してから」) が、この 2 点にだけ欠落。保持期限超で一覧から消えた課金済み job を無記帳のまま掃除し token を NULL 化する — sweep 自身が「(b') が飛んだ課金済み job を無記帳で掃除して痕跡を消す」ことを防ぐために新設された (L1084-1086) のに、sweep 自体が同じ穴を持つ | 相 2b で job J 作成 (課金) → 相 3 前クラッシュ (state=0, batch_job_id NULL, token) → kind=2 の profile A→B→A (単一デバイスの正規操作 — L1142-1143 が成果あり化を明記) で成果あり化 → 数か月停止 → reconcile close (b') が job 照合 → J は保持期限超で一覧から消滅 = confirmed-absent → (b') は「実在せず」で記帳スキップ → (c)/sweep が掃除 + token NULL 化 → J の実課金が cost_ledger から**永久欠落** | C12/X41/X45/X46 (私 Q01 + X31-45 候補1 + X46-50 C2 の **3 系統独立検出**)。r10-r12 で塞いだ「実行された可能性のある課金を取りこぼさない」(§9.1 L1067) の破れ | detached (b) の期限判定 (L1105-1110) を (b')/sweep 前段の confirmed-absent 分岐へ移植 — 期限超・未来 skew は記帳済み判別 → seq+1 + NULL + estimated (batch_job_id = intent_token) で**記帳してから**掃除 |
| **Q02** | §11.2 単独検索規則 L1739-1744「embeddings の全行一致検査で得られる一意な **embedding_profile_hash** に対応する profiles 行を現行とする」/ eligible L1664-1667「WHERE c.tool_profile_hash = **:current_tool**」/ mapping 表 L1634「単独 = §5.7 profiles + embeddings の一意 profile 規則」 | フォルダ単独検索の「現行決定規則」は **embedding profile のみ**を定義し、`:current_tool` (tool_profile_hash) の決定規則が無い。eligible は :current_tool を FTS・KNN **両経路**の必須 gate とし、mapping 表は app_config を単独検索の給源から明示除外 (L1634「app_config は横断専用で単独検索の給源ではない」)。tool 切替を経たフォルダは旧 tool 派生が明示 drop (§13 L1902「消せば」) まで残るため markdown_documents に複数 tool 世代が併存するのが定常。この状態で :current_tool を一意に決められず、embedding の「混在なら停止」を類推適用すると eligible が FTS 経路も gate するため単独検索が恒久停止し §2「コピー・共有すれば検索がそのまま渡る」に反する | フォルダ F を tool T1 で全派生生成 → tool を T2 へ変更、backfill が T2 派生生成 (T1 派生残置) → F を別マシンへコピーし standalone 検索 → :current_tool の給源なし。T1/T2 どちらを bind するかで結果集合が変わり規範から一意に導けない (単一世代フォルダなら「一意な tool hash」類推で救えるが、tool 切替は混在が定常) | C12/X12 (X1-15 candidate01 + 私の確定検証)。§2 の一級要件に直結 | §11.2 の単独検索決定規則に tool 版を追加 (例: 「最新 generated_at をもつ tool_profile_hash を現行とする。混在時も FTS は全 tool を対象に縮退せず、eligible の tool gate は現行のみ」等、embedding と非対称に扱う規則を明記)。mapping 表の「一意 profile 規則」が embedding 専用であることも注記 |

### minor

| ID | 該当箇所 | 問題 | 再現シナリオ | 根拠 |
| --- | --- | --- | --- | --- |
| Q03 | §9.1 intent 回復 confirmed-absent L998-1009 (期限超・期限内とも attempts 上限チェックなし) / client dispatch L977-979 (client_exhausted あり) | server state=0 の confirmed-absent 載せ直しに **attempts 上限の terminal 出口が無い** — client には client_exhausted があるが server には対応物がない非対称。設計の有界化保証 (attempts 上限 — §8/§10) が server 経路に及ばない | 相 2b 完了・相 3 前クラッシュ → 数か月停止 (job 期限消滅) → confirmed-absent 期限超 → 記帳 + attempts+1 + 載せ直し → また相 3 前クラッシュ + 長期停止、の反復で attempts 上限を超えても新 job 作成 + estimated 記帳が続く。**通常は載せ直しが相 3 で state=1 に到達して収束**するため minor (client と違い server は state=1 に進めるので永久滞留しない。非有界化には相 3 前クラッシュ or job 期限消滅の反復という極端条件が必要) | X45/X46 (私 Q02 + X46-50 C3。a34 は fatal 寄りと裁定したが、相 3 到達で通常収束するため私は minor) |
| Q04 | cost_ledger DDL L845-848「(期限超 confirmed-absent・token sweep) は **intent_token**」/ sweep 本文 L1078-1081「(b') と同一の前段 … batch_job_id = **発見 job id** の ledger 行なし … 記帳」 | DDL コメントは「token sweep = intent_token」と分類するが sweep 本文は「(b') と同一 = 発見 job id」で記帳・突合。述語キーが分裂する実装 (DDL 準拠 sweep × 本文準拠 (b')) では、(b') が発見 job id X で記帳を試み unknown で飛んだ後、sweep が intent_token T で記帳 → 同一 attempt が (T) と (X) の 2 行で二重記帳 | (b') 記帳 unknown で保持 → 次 tick sweep が DDL コメント準拠で intent_token 記帳 → 別経路が発見 job id で再記帳 → 二重計上 | X16/X46 (afee C1 + a34 C1 の 2 系統。**両者 major 主張**だが本文 L1080「(b') と同一」で正しい実装 (発見 job id) が一意に決まり安全側に倒せるため私は minor。修正は DDL コメントの「token sweep」を intent_token 分類から外す) |
| Q05 | §21.1 register (手順内に fork チェック無し) / §20.4 L2287-2289「fork_in_progress の old/new は再発見の対象外 … 回復は §21.3 の journal 走査が担う」/ §21.3 (b) L2625-2626 走査範囲「watch_roots 配下と既知 folders」 | 未完 fork フォルダを watch_roots 外へ移動 → register(新パス) すると、register 前の fork 回復先行 (§21 前文 L2467) の journal 走査は新パス (まだ folders になく watch_roots 外) を見ない。前文の「回復先行が全操作を未完 fork の反転から保護する」保証が register 対象パスに及ばない非対称 | HISTORY_CLEARED 中断 → watch_roots 外へ移動 → register (fork-journal 未検出で再発見・old_id 運用化) → ユーザーがコミット → 次 tick walk が既知 folders から journal 検出 → 回復が「HISTORY_CLEARED + commits 非空 → 手順 1」(L2635-2637) で全 commits DELETE = register 後コミットの喪失 (操作反転)。**register 後の walk 回復先行で最終収束**し喪失も未完 fork の履歴 (fork の趣旨) の範囲のため minor | X32/X38/X49 (X31-45 候補2 は major・afee C2 は major・a34 C7/C8 は minor と裁定割れ。私は最終収束と有界性から minor。修正: register 手順 1 に「対象の .folder-history に fork-journal があれば先に §21.3 回復を完了してから判定」を追加) |
| Q06 | §20.5 L2386-2389「walk が … case 違いで一致する既存 file_versions **系列** (単数) を見つけたら既存の保存名を使い続ける」/ L2396-2400 (insensitive→sensitive 方向のみ規定) | sensitive ボリュームで "Report.pdf"/"report.pdf" の 2 系列が正当に併存 (文書明記の系列分裂) → insensitive ボリュームへ戻る (rebind / 再発見で case 感度は走査時属性で再判定) と、1 実体の観測が**複数**の既存系列に fold 一致。どちらを継続しどちらに delete を打つかの採用 tie-break が無く、literal な折り畳み集合減算では実体の無い系列が現在版として恒久残留 (phantom) | Linux で 2 系列コミット → "report.pdf" 削除 (未確定) → APFS へ移動・rebind → walk 観測 {Report.pdf} が両系列に fold 一致 → 採用先未定義、片方の読みで幽霊現在版を恒久化 | X3/X29 (X1-15 候補02 + afee C8 の 2 系統。稀な操作列で決定論的 tiebreak (BINARY 一致優先 → バイト昇順) を明文化すれば閉じるため minor) |
| Q07 | §6 L538-540 エスケープ条件「0 個以上の `\` に続いて grammar 形 (**行頭パターン `![` + `](obj:`**…) が現れる形」/ §7 L586-589 認識条件「**行全体が grammar に一致**する場合のみ … `\` を 1 つ除去」 | §6 のエスケープ条件 (行頭 `![` かつ `](obj:` を含む) は §7 の認識形 (hash64 まで含む行全体一致) の**上位集合**。`![diagram](obj:see appendix)` のような「§6 一致・§7 非一致」の本文行はエスケープされたまま un-escape されず、迷子の `\` が text チャンク・FTS・プレビューに恒久残留し可逆性 (O08) が破れる | 本文に `![diagram](obj:see appendix)` を含む PDF → materialize で `\![diagram]…` 保存 → §7 が行全体不一致で un-escape せず → `\` 付きで FTS/preview に固定 | X2/X15 (X1-15 候補03。エスケープ側も「行全体一致 = hash64 検証込み」に揃えれば phantom 防止・可逆性とも成立する安全側解釈があるため minor。r13 の test vector (G/\G/\\G) は G=完全 grammar のみでこの非対称を検出しない) |
| Q08 | §6 L521-522「`v` は grammar version … 解析器は v を見て版別に dispatch」/ §14 の fail-closed は user_version (DB schema) のみ gate | grammar v の混在 (v2 へ再 materialize 済みフォルダを grammar v1 しか知らない旧アプリが同 user_version のまま開いて再チャンク) で、未知 v の block の dispatch 先が未定義。テキスト扱い/スキップ/fail のいずれかで chunks・text_hash が実装依存に分岐し generated_at 単調更新で agg へ伝播 | デバイス A が grammar v2 移行完了 → フォルダを旧アプリのデバイス B (同 user_version) へコピー → B で画像フィルタ変更 (再チャンク) → v:2 block の解釈が未定義 | X7 (X1-15 候補05。「未知 v は当該派生の再解析を fail-closed でスキップ + status」に倒せる、grammar bump 時に user_version も bump する規範を足せば構造的に閉じるため minor) |
| Q09 | §9.1 L836-840「月次コスト = … この列 (ts) で行う (attempt 単位なので月跨ぎ retry も**発生月へ正しく配賦**される)」/ ts は「課金の確定 (collect) 時刻」(L834) | ts は collect (確定) 時刻であって provider 側の課金発生時刻ではない。submitted_at を ledger に持たないため、submit と collect が月境界を跨ぐと配賦がずれる。文書自身が想定する長期停止 (§6) では数か月ずれる。「発生月へ正しく配賦」は過大主張 | 1/30 相 3 完了 (provider 課金) → 端末停止 → 2/10 再開 collect が terminal 記帳 (ts=2/10) → 月次集計で 1 月の課金が 2 月計上 | X18 (afee C3。台帳は「記録できた課金・正はプロバイダ側」と明記済みで、主張文言の修正または ts 定義変更で安全側に倒せるため minor) |
| Q10 | §9.1 期限超処理 L998-1007 (upload 掃除なし) / L1008-1009「期限内の不一致は … 同 token の upload 残骸を削除してから」 | 相 2a 成功・記録前クラッシュ (upload_id 未記録、token は filename に埋込済み — L950-951) の残骸は、期限内回復なら token 掃除で消えるが、期限超経路 (長期停止後) の (iv) 載せ直しが掃除するのは「記録済み upload_id」だけで、未記録残骸を掃く手当てが無い。TTL (~30 日) まで機密残留 | 相 2a upload 成功 → 記録小 Tx 前クラッシュ → 3 日以上停止 → 再開 intent 回復が期限超分岐 → 記帳 + rotation のみ、旧 token upload は未掃除 | X19 (afee C4。機密残留はプロバイダ TTL で有界・文書が同種残余を既知として許容する枠内だが期限内と非対称のため minor) |
| Q11 | §15 規約 7 L1972-1974「(a) 未回収 job の再投入 (**server = 未追跡 1 job** / …)」/ §10 L1564「app.sqlite 全損はこの有界化の外」 | 規約 7 は app 全損時の損失列挙だが、全損では in-flight の**全** server job が未追跡になる (batch_requests ごと消え intent 回復の突合材料が無い)。「server = 未追跡 1 job」はクラッシュ窓の主張であり、§10 が明示的に有界化の外と除外している当の主張を全損の損失列挙が借用している | 3 フォルダで計 5 job in-flight → app.sqlite 全損 → bootstrap → 全 target が「成果なし・行なし」で再投入 = 5 job 分の重複課金 (旧 5 job の課金も台帳に載らない — 規約 7-(b) と複合) | X18 (afee C5。システム挙動は不変で損失量の記述の不整合。(a) を「in-flight 数に比例」に正せば整合するため minor) |
| Q12 | §9.1 相 1 L946-949「upload_cleaned を 0 に戻す … 未清掃なら削除を試みる」/ 4.5 掃除 L1075-1077「upload_cleaned=0 の … 削除し … 失敗・クラッシュは次 tick 再試行」 | attempt 1 で U1 清掃済み (cleaned=1) → attempt 2 の相 1 が cleaned=0 に戻す (upload_id=U1 は残る) → 相 2a 恒久拒否で終端すると「終端 + cleaned=0 + upload_id=U1 (既に provider に無い)」が成立。4.5 の削除は 404 を返すが「404=成功」の規定が無く、失敗扱い実装は毎 tick 恒久再試行、unregister 時は「掃除完了まで削除しない」で detached が恒久残留 | result_expired → 再投入 → 相 2a で 4xx、の 2 attempt で到達 | X16 (afee C6。「不在確認 = 成功」に倒せば収束するが規範化されていないため minor) |
| Q13 | §10 step4 L1528-1529「無ければ … embeddings + embedding_vec + profiles INSERT」(素朴 INSERT) / §9.3-c L1405-1408 (agg は DELETE→INSERT で孤児を無害化) / §13 L1889-1891 (fsck はローカル vec 孤児を検出のみ) | agg 側は破損起源の vec 孤児を DELETE→INSERT で防御するが、ローカル collect の INSERT は §8-b (旧 profile 行がある場合) しか置換せず、embeddings 行なしの vec 孤児では PK 衝突。衝突は「一時失敗」にも「invalid_output」にも分類されない未定義失敗で、当該 target が恒久に embeddings へ入らない。fsck は検出のみで修復規範が経路未接続 | 破損で embeddings 行 1 件のみ喪失 (vec 行残存) → 当該 content 再出現 → submit → collect INSERT が target_key PK 衝突 → 毎 tick 同一失敗 | X24 (afee C7。破損が前提だが agg 側と同じ根拠が成立するため、ローカル collect も DELETE→INSERT に統一するのが自然。minor) |
| Q14 | §21.3 L2646-2647「journal の破損 … damaged … ユーザーの**明示解決**を待つ」/ §21 前文 L2467「各操作は … fork 回復を**完了してから**本体」/ §21.7 カタログに journal 破損の解決操作なし | journal 破損フォルダでは fork 回復が「完了」し得ず、前文を literal に読むと register (damaged 復旧の唯一経路 §20.4) を含む全明示操作が恒久ブロック。§20.4 の damaged 復旧は「.folder-history 消失」想定で、「.folder-history 現存・journal 破損」への手順 (手動削除要否、register の bypass 可否) が無い | fork 手順 0 後クラッシュ → journal bit-rot (digest 不整合) → 毎 tick damaged → ユーザーが register → 前文回復先行が完了不能 → 脱出手順が導けない | X13/X49 (X1-15 候補04 + a34 C7 の 2 系統。「journal 破損の解決 = .folder-history 手動削除 → damaged → 新 id 再登録」に倒せるが手順・bypass 可否が未設計のため minor) |
| Q15 | §9.1 L869-871「現行の key 契約 (すべて必須…)」/ §21.5 L2717-2720 (bootstrap 再入力) / §10 step3 L1503-1505 (現行 profile の参照元 = app_config) | 全損後 bootstrap の再入力必要性は明記されるが「再入力**前**に tick が走ったら」の分岐が無い (初回インストール直後も同窓)。step 1 は snapshot 構成不能 (DDL CHECK profile_record NOT NULL で INSERT 失敗)、step 3 は `<dim>` 展開元なし。skip+status か tick 中断かが実装依存 | 新規インストール → watch_root 追加 → register → profile 設定前に cron tick 起動 → step 1/3 の挙動未定義 | X13 (afee C9。課金・データ喪失方向には倒れず「未設定 provider/kind は submit/collect/検索を skip + status」の 1 文で閉じるため minor) |
| Q16 | §21.3 失敗回復 (a) L2620「journal 無だが realpath に実体現存し、かつその repository-id が **journal 記録の** old/new と一致」 | この分岐は journal 不在時なので id の照合元は実際には app 側 fork_in_progress の JSON {old_id, new_id, realpath} のはず。「journal 記録の」という給源表記が分岐前提 (journal 無) と食い違う | (字句の精度問題。O18 の実質条件自体は満たしており規範の穴ではない) | X38 (K/L/M・N/O 両回帰エージェントが独立に指摘。「fork_in_progress 記録の」への字句修正が正確。minor) |

### proposal

| ID | 内容 | 根拠 |
| --- | --- | --- |
| Q17 | §20.5 の name_invalid リスト (パス区切り・`..`・NUL 等) に **Windows 予約デバイス名 (CON/PRN/AUX/NUL/COM*/LPT*) と末尾 dot/space** を追加。細工履歴の restore や Linux 由来の合法名の Windows 上書きで Win32 パス正規化が別実体へ着地し得るが、dirfd 規律 (openat 相当 = NT ハンドル相対 open) 準拠なら破綻を構成できず proposal 止まり | X8 (X1-15 proposal-A) |
| Q18 | §8 (ii) の「client の恒久 4xx = 未実行の確定 (記帳なし)」(L719-724) は「4xx = 課金なし」が全 provider で成立する前提。処理後に内容起因 4xx を返す (かつ課金する) provider では台帳漏れ。文書内規範だけからは破綻を構成できないため仮定の明文化を提案 | X41 (X31-45 proposal 1) |
| Q19 | 期限内 confirmed-absent = 「未作成」断定 (L992, 1008) は「作成直後の job が一覧に必ず現れる (read-after-write 整合)」前提。一覧が遅延する provider では期限内 confirmed-absent → 無記帳載せ直しで「旧 job 課金の無記帳 + 二重 job」が生じ「最悪 1 job」が provider 依存に。外部仮定のため proposal | X45 (X31-45 proposal 2) |

---

## 第 4 部 — 確認済み (検出 0 の観点)

- **C1 (原則反映 P1〜P16)**: P1〜P16 の反映を確認。弱化・条件落ちは O28 の partially-fixed
  (P2/P8 の embedding 次元参照元) を除き検出なし。
- **C2 (SQL 静的検証)**: sqlite3 3.51.0 + FTS5 trigram で §5/§9.1/§9.2 の全 DDL を実 CREATE、
  FK・CASCADE・FTS external content (view content)・trigger・全 CHECK (batch_requests の
  state/kind/snapshot 連動 CHECK 5 本、embeddings の length(vector)=4*dimensions の行内他列参照、
  chunks 複合 CHECK) を実データで検証。欠陥 0。vec0 固有構文のみ環境制約で未検証。
- **C3 (相互参照整合)**: §参照は Q16 の給源表記 (minor) を除き実在・整合。
- **C4 (クエリ×スキーマ)**: §11.1(A/B/C)・§11.2 ハイブリッド完全 SQL・§9.3-a INSERT…SELECT・
  §10 step3 NOT EXISTS・§13 孤児掃除を prepare/実行。存在しない列/表参照・join キー型不一致 0。
- **C5 (数値一貫性)**: $2.5/$4/$5/+25%/50%/768(参考値)/RRF 60/8 テーブル/k_max 4096/max_chars 2000/
  猶予 30 日/最小不在 30 秒/72h/24h/512MB/attempts 3/skew 5 分/週 1/0700-0600 — 全出現一致。
- **C6 (用語一貫性)**: target_key 連結形式 (小文字 hex)・chunk_type↔target_type・obj: スキーム・
  embed_hash 定義・bind 名 (:current_tool/:current_profile 等) — 全出現一致。Q04 の DDL コメント
  vs 本文の突合キー分岐のみ検出。
- **C7 (状態機械完全性)**: batch_requests の state 遷移をクラッシュ位置別 (objects 後/metadata Tx 後/
  app 更新前/2 相各境界) に追跡。到達不能・脱出不能は client_exhausted 対称の server 欠落 (Q03) を
  除き検出なし (収束を文書記述だけで追跡可能)。
- **C8 (欠落)**: P1〜P16 範囲の章欠落は Q02 (単独検索 tool 決定) を除き検出なし。
- **C11 (合理性)**: 手順・SQL・規範の実装可能性を検査。追加設計を要する箇所 = Q02 (major)・
  Q03/Q08/Q12/Q13/Q14/Q15 (minor)。規範同士の両立不能 = Q01 (major)・Q04/Q07/O28 (規範間矛盾)。
- **C12 (探索監査)**: X1〜X50 の全 50 観点で 150+ シナリオを実行 (前提条件充足)。
