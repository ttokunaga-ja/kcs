# folder-history 設計書 r14 監査報告 (Claude Sonnet 5)

対象: `docs/research/folder-history-sqlite-design.md` (2762 行、r13 修正 O01〜O30 適用済み版)
監査日: 2026-07-16

> **本報告について**: 同名ファイルに既存の草稿が存在したが、その内容は `tasks/folder-history-r13-adjudication.md`
> が「H | 追走 64 シナリオ (自称 r14) | 合格 | 0 (proposal 2)」として言及する系統の産物であり、
> r13 裁定で「集約判定: 不合格。F/H の合格は過小検出」と明記されている。すなわち当時の "r14" 報告は
> N01〜N45 の 45 項目のみを検証し O01〜O30 (30 項目) を一切検証しておらず、探索も 64 シナリオに
> とどまっていた。本報告はその反省を踏まえ、監査プロンプトが要求する全 337 項目 (A01〜O30) の
> 回帰確認と 50 シナリオ以上 (X1〜X50 全観点 + 自由探索) の探索型監査を実施し、旧草稿を置き換える。

## 判定: **不合格**

- C9 回帰: **337/337 fixed または superseded** (regression・not-fixed 0 件。F10 のみ表記上の
  経過措置的な不一致だが実質は fixed — 詳細は第 1 部)。**破壊型 regression は 4 ラウンド連続 0**
  であり、この観点では文書の安定性は極めて高い
- 新規検出 (確定): **fatal 0・major 2 (Q01, Q05)・minor 7 (Q02, Q06, Q07, Q08, Q09, Q10, Q11)・
  proposal 3 (Q03, Q04, Q12)**
- 合格基準 (プロンプト冒頭の定義) は「新規検出に fatal/major が 0 件」を条件付き合格の要件とし、
  それ以外 (major が 1 件でもある場合を含む) を不合格と定めている。C9 が完全にクリーンであっても
  major が 2 件検出されたため、機械的な適用として **不合格**と判定する。Q01 は r12/r13 で新設
  された「無 id 記帳」ファミリー自体の内部に閉じた欠陥、Q05 は r12 で新設された found/
  confirmed-absent/unknown の三値判定が「照会失敗」と「照会成功だが結果整合性により不完全」を
  区別していないという、既存規範の**適用範囲の不完全な一般化**である。いずれも r10〜r13 で
  繰り返された「fix が既存の広い範囲を破壊する」型の regression ではなく、新設規範自身の
  射程が意図どおりに完結していない、という同じ性質の欠陥である (この点は r14 の重心である
  X46〜X50「r13 で新設された規範そのものが一次攻撃対象」という狙いとも整合的)。minor 7 件の
  うち複数 (Q08, Q09, Q11) も同様に「個々の修正は正しいが、隣接する別の既存規範との組み合わせ
  面に生じた非対称・空白」という r14 の狙いに合致する性質を持つ。破壊型 regression が今回も
  0 件だった一方で、探索を深化・拡張した結果 major 2 件を含む新規検出が増えたのは、r14 が
  「同じ深さをなぞる」のではなく実際に新しい攻撃面 (job 一覧 API の結果整合性、submission_seq
  の書込先、agg/local 間の非対称、fork のエスケープ機構の欠如等) を開拓した証左であり、
  過去 3 ラウンド (r11〜r13) の「合格系統は過小検出」という教訓を踏まえた結果と考える

---

## 第 1 部 — 回帰確認 (C9)

全 337 項目 (A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F27 / G01〜G02 / H01〜H30 /
I01〜I38 / J01〜J20 / K01〜K26 / L01〜L28 / M01〜M29 / N01〜N45 / O01〜O30) を検証した。
検証は 8 個の並列エージェント (A-N、307 項目) + 監査者本人 (O01〜O30、30 項目) が分担し、
各エージェントは対象文書を直接読み、該当箇所の引用によって判定した (想像による判定は禁止)。

**A01〜A24 / B01〜B18 / D01〜D14 / E01〜E06 / F01〜F09 / F11 / F13〜F20 / F22〜F27 / G01〜G02 /
H01〜H03 / H05〜H14 / H16〜H17 / H19〜H21 / H23〜H30 / I01〜I11 / I13〜I38 / J01〜J12 / J14〜J15 /
J17〜J20 / K01〜K08 / K10〜K11 / K16〜K18 / K20 / K22〜K23 / K25〜K26 / L01〜L28 / M01〜M29 /
N01〜N45 / O01〜O30: すべて fixed。**

**superseded (対応表どおり、後継 ID 側で fixed 確認済み)**: F05(→I14) / F07(→I15) / F12(→I16・I17) /
F21(→J06) / H04(→I31) / H15(→I08・I11) / H18(→I16) / H22(→I15) / I12(→K04) / J13(→K16) /
J16(→K13・K14・K15) / K09(→L03) / K12(→L04) / K13(→L04) / K14(→L07) / K15(→L07・L08) /
K19(→L13) / K21(→L20) / K24(→L09)

partially-fixed / not-fixed / regression が出た項目のみ詳細報告する:

| ID | 判定 | 根拠 (§ + 短い引用。残存・欠落箇所) |
|----|------|--------------------------------------|
| F10 | fixed (表記上の経過措置) | チェックリストの「img block の meta が 4 行 (page/bbox/source_id/media_type)」という原文言は r6 (H08) で `v` (grammar version) 行が追加される前の記述であり、現行文書は §6 L501, L518-519 で一貫して「meta **5 行** (v/page/bbox/source_id/media_type)」と定義している。これは意図的な仕様拡張 (grammar version 管理のため) であり後退ではない。サブ要件 (media_type のマジックバイト決定論的判定、chunks.media_type の img block からの充填) は文言どおり存在する。担当エージェントはこれを partially-fixed として報告したが、監査者の判断では実質 fixed (チェックリスト側の古い行数表記が更新されていないだけ) である。 |

数値・用語の機械検証 (エージェントによる grep 相当の確認を含む):
- 「7 テーブル」の残存: 0 件 (「8 テーブル」に統一。実テーブル 6 + 仮想テーブル 2 の内訳)
- 旧単一 `agg_embedding_profile_hash` キーの残存: 0 件 (7-key 化: tool_profile / embedding_profile /
  image_filter / retry_not_before / agg_building_profile_hash / agg_ready_profile_hash /
  fork_in_progress)
- `$2.5`, `$5`, `$4`, `+25%`, RRF `k=60`, `768` (参考値表記), `30 日` 猶予, `k_max=4,096`: 全出現箇所で一致
- `lower(hex(...))` の小文字固定契約: §5.6 / §9.1 / §11.2 で一貫 (§9.1 の DDL コメントは
  hex() 単独表記だが直後に「SQL で構築するなら lower(hex(...))」の注記あり — 実害なし)

---

## 第 2 部 — 探索ログ (C12)

X1〜X50 の全観点について最低 1 シナリオ、うち X46〜X50 (r14 の重心) は監査者本人が複数シナリオで
深掘りした。X1〜X45 は 3 系統の並列エージェントが分担し、各エージェントには「過去ラウンドで
深く採掘済みの観点だが、実際にシナリオを手で追った上での結論でなければならない」と明示して
ラバースタンプを禁止した。

### X46〜X50 (監査者本人による深掘り — r14 の本命)

| # | 観点 | シナリオ (初期状態 → 操作列) | 結果 |
|---|------|------------------------------|------|
| 1 | X46 | 記帳済み判別述語の基本動作: 期限超Tx がクラッシュで完走せず再試行される (同一 token T1 で述語が 2 回目に効くか) | 問題なし。§9.1 L999-1001 の述語は「同 (repo,kind,target_key) × batch_job_id=T1 の ledger 行の有無」を見るため、1 回目が完走していれば 2 回目は記帳をスキップする (Tx 全体がロールバックしていれば 1 回目自体が存在しないので通常どおり記帳)。冪等に機能する |
| 2 | X46 | **主要発見**: 期限超の (ii) 「submission_seq+1 …の冪等記帳」が `batch_requests.submission_seq` 自体を更新すると明記されているかを、相 3 (L970)・intent 採用 (L984)・client 前計上 (L710, L727-728)・detached 採用 (L1102-1103) の 4 箇所 (すべて「…へ UPDATE」「…で採用」等、batch_requests 行のミューテーションとして明示) と比較する | **Q01 を検出** — 期限超 (L1002)・(b') (L1137)・token sweep (L1081, L1108 で「同じ規則」として (b') へ委譲) の 3 箇所はいずれも「…の冪等記帳」という cost_ledger への INSERT のみを表す語法で、batch_requests.submission_seq 自体の UPDATE が明記されていない。詳細は第 3 部 Q01 |
| 3 | X46 | attempts+1 (期限超、L1004) と §8-a の profile 数え直し (attempts=0、相 1 内) が同一 Tx 内で交錯 — 期限超処理の直前に embedding profile が変更されていた場合 | 問題なし。(iii) の attempts+1 は「閉じられる旧 profile 世代の最後の attempt」を数え、(iv) の相 1 が profile 不一致を検出して attempts=0 にリセットするのは「新 profile 世代の予算を仕切り直す」という設計として整合する。profile 変更は稀な操作でありループ化しない |
| 4 | X46 | 述語の SELECT→INSERT 間の原子性: 期限超判定と記帳が同一 app Tx (§9.1 L998) 内で、tick.lock が単一 writer を保証するか | 問題なし。§21 前文・§10 の並行性規約により tick 全体および §21 の全明示操作が同一 tick.lock を取得するため、この Tx の実行中に他の writer が同じ行へ競合書込みすることは構造的に排除される |
| 5 | X46 | 明示操作 (§5.3 明示再生成、§21.7 経由) は cost_ledger へ直接書き込むか — 述語が想定しない経路からの記帳があり得るか | 問題なし。§5.3 の明示再生成は floor_generated_at と attempts のみを操作し cost_ledger への INSERT は行わない (課金記帳は常に collect / reconcile / submit の close 経路のみ) |
| 6 | X47 | (i)〜(iv) の同一 Tx を各境界 (Tx コミット前) でクラッシュさせ再実行 | 問題なし。SQLite のトランザクション原子性により Tx 内での部分クラッシュは常に全ロールバックになる。次回の再試行は述語 (i) から再開し冪等に収束する |
| 7 | X47 | 旧 token (T1) の期限超記帳行が、後続で発行される新世代 token (T2) の将来の述語判定に干渉するか | 問題なし。述語のキーは `batch_job_id = 当該 intent_token` であり、T1≠T2 のため、T2 自身の将来の期限超イベントは T1 の記帳行と衝突しない (別レコード) |
| 8 | X47 | detached の期限超記帳 (L1108「同じ規則」) → 行削除 → 同 repository 再登録 → 同一 target_key の新規行作成時の submission_seq 継承 | 問題なし。L01 のルール (COALESCE(MAX(cost_ledger.submission_seq), 0)) は新規 INSERT 時に ledger の MAX を都度再計算するため、削除→再作成を経由する経路では期限超記帳の seq を正しく引き継ぐ (Q01 の懸念は「行が削除されずに寿命を継続する」経路に限定される) |
| 9 | X47 | 期限超判定 (L992-1009) と kind=1 の tool_changed ガード (L1010-1014) の適用順序 — 両方とも「載せ直し」に関わる分岐で、期限超かつ tool 変更が同時に起きた場合の記述順が一意か | 軽微な疑問点 (proposal レベル)。L1010「kind=1 の載せ直しガード」は文面上 L1008-1009 (期限内の載せ直し) の直後に置かれ、期限超の載せ直し (L1005 の (iv)) にも同じガードが適用されるかは記述位置からの類推に依存する。ただし「載せ直し」という語自体が両分岐に共通するため、実装者が両方に適用すると解釈するのは自然であり、C11(b) の「安全側に倒せる」曖昧さに留まる。第 3 部では取り上げない (proposal 未満と判断) |
| 10 | X48 | 保全コミット (現内容≠LWW) → restore の上書き → 次 tick scan の 3 段が tick.lock 下で一貫するか | 問題なし。restore 自体が tick.lock を保持したまま §20.5 手順 3〜6 を呼び出すため (§21.4 L2676-2677「tick.lock 下なので競合しない」)、保全コミットと上書きは同一ロック内で完結する。上書き後に LWW と working が一時的に乖離するのは規約 11 (変更検知の根拠は常にスキャンの content_hash) に沿った意図された挙動であり、次 tick が通常の update として収束させる |
| 11 | X48 | **発見**: restore の保全ステップ (§21.4 手順 3a、§20.5 手順 1 の安定確認を呼ぶ) で、その安定確認自体が失敗した場合 (対象ファイルが書込み中で 2 回の stat が食い違う) に restore が中止するか続行するかが明記されているか | **Q02 を検出** — §20.5 手順 1 の通常のスキャン文脈での失敗時挙動 (「壊れた中間状態はスキップして次回スキャンに回す」) は、ファイル自体に触れない読み取り専用の判定なので安全に「今回は諦めて後で再試行」で済む。しかし restore の保全ステップでこの失敗が起きた場合に同じ「スキップ」の解釈 (保全をスキップしてそのまま上書きへ進む) を取ると、O09 が塞いだはずの「未取り込み working 変更の消失」が再現し得る。詳細は第 3 部 Q02 |
| 12 | X48 | 保全コミットと restore で書き込む内容が偶然同一 content_hash の場合 (no-op になるべきか) | 問題なし。§21.4 手順 3a の条件文は「content_hash が現在版と異なる場合」に保全を限定しているため、同一なら保全ステップ自体がスキップされ、そのまま上書き (実質 no-op) に進む。矛盾なし |
| 13 | X48 | raw 解決 (書込先の物理名解決) と保全 (読取元) が NFC/NFD collision で異なる実体になるケース | 問題なし。O13 の「残余の TOCTOU 窓は 3 呼出点共通 — 次回 walk が name_collision / update として収束させる」という一般的な許容が restore にも適用されると明記されている (§20.5 L2379-2382) |
| 14 | X48 | エクスポート (管理外 / 別名) が保全対象外であることの明確さ | 問題なし。§21.4 手順 3 の a (in-place) と b (エクスポート) は明確に分岐しており、保全ステップの記述は a に限定されている |
| 15 | X49 | register/unregister/fork/restore/watch_root/drop の各操作前の fork 回復実行をトレースし、回復後の状態を入力に操作が一意に進むか。特に: fork(A) が ID_WRITTEN でクラッシュ (id は既に new_id) → ユーザーが unregister(old_id) を実行 → tick.lock 取得直後の回復で手順 3 (旧 folders 行 DELETE + 新 folders 行 INSERT) が完了 → unregister 本体は old_id の folders 行を探すが既に存在しない | 軽微な観察 (proposal レベル)。unregister(old_id) は「対象行が存在しない」という通常の入力検証ケースに帰着し、多くの実装で自然に no-op/status 表示となる。これは O11 が塞いだ「操作が完了した後で回復により取り消される」問題とは異なる (ここでは回復が操作の**前**に走り、操作自体は「対象が既に無い」という無害な no-op になる)。ユーザーの意図 (このフォルダを追跡から外したい) が新 folders 行 (new_id) には及ばず追跡が継続する点は UX 上の驚きだが、データ整合性上の欠陥ではない。第 3 部では proposal (Q03) として軽く記録するに留める |
| 16 | X49 | 回復自体が進めない場合 (journal digest 不一致 = damaged) に後続操作 (例: restore) は実行してよいか拒否か | 文書は fork 自体について「status 表示してユーザーの明示解決を待つ (自動で推測して進めない)」(§21.3 L2647) と明記するが、後続操作 (register 等) 側が fork-damaged 状態をどう扱うかは §21 前文からは「回復を完了してから本体を実行する」としか読めず、回復が完了できない場合に本体を実行するかどうかの二択が文言上どちらとも取れる。ただし damaged 状態は既に §20.4 で「ユーザーの明示解決を待つ」という文書全体で一貫したパターンがあり、実装者が「回復未完了なら本体も保留」と解釈するのは自然。proposal 未満と判断し第 3 部では取り上げない |
| 17 | X49 | 回復先行と「fork 中の読取 = fork 進行中 status」(規約 12 共有ガード) の整合 | 問題なし。共有ガードは (old_id, realpath) のパス単位で tick 内外問わず適用され (§15 L2018)、回復自体が §21 操作の前提ステップである以上、回復完了までの間は一貫して「fork 進行中」status が返る |
| 18 | X49 | 二重 fork (回復完了後に同一パスへ新しい fork を起動) の単一 flag 遷移 | 問題なし。tick.lock による直列化 (§21 前文) により、2 つの fork 呼び出しが同時に app_config の 'fork_in_progress' キーを競合させることは構造的に発生しない |
| 19 | X50 | 反証: 「無 id 記帳は NOT NULL と衝突しない (値規則で常に埋まる)」 | 破れず。cost_ledger.batch_job_id には server job id / client 実行 id / intent_token (無 id 記帳) / 発見 job id ((b')) のいずれかが必ず入る値規則が §9.1 L845-851 に明記されている |
| 20 | X50 | 反証: 「記帳済み判別で推定行は増殖しない」 | 文字どおりには破れず (同一 token/job id に対する重複記帳は述語が防ぐ)。ただし Q01 が示すとおり、これとは別種の問題 (推定行と後続の実正記帳が seq 衝突し実正記帳が消える) が存在する — 「増殖しない」こと自体は真だが「実正記帳が失われない」という暗黙の期待は満たされない場合がある |
| 21 | X50 | 反証: 「(b') が飛んでも sweep が記帳を回収する」 | 破れず。§9.1 L1078-1082 の token sweep は (b') と同一の前段 (照合→未記帳なら記帳) を明示的に実行すると規定されている |
| 22 | X50 | 反証: 「detached は期限超でも記帳してから消える」 | 破れず。§9.1 L1104-1109 で attached と同一の期限判定・記帳規則が detached (b) にも適用されると明記 |
| 23 | X50 | 反証: 「未来時計 token で無記帳載せ直しは起きない」 | 破れず。§9.1 L995-998 で未来 skew (許容 5 分超) も期限超と同様に扱われ、記帳してから載せ直す規則が明記されている |
| 24 | X50 | 反証: 「§6/§7 の往復は全段可逆 (G/\G/\\G)」 | 破れず。§6 L537-543 のエスケープ対象が「0 個以上の `\` に続いて grammar 形」に拡張され、test vector に 3 段の往復例を含める指示まで明記されている (O08 の直接確認と一致) |
| 25 | X50 | 反証: 「restore は未取り込みの working 変更を消さない」 | **一部破れる (Q02)**。安定確認自体が失敗する狭い窓においては、この保証が明示的に保たれていない |
| 26 | X50 | 反証: 「明示操作は未完 fork に反転されない」 | 文字どおりには破れず (O11 が防いだ「操作完了後に回復が取り消す」パターンは構造的に排除されている)。ただし X49-15 で見たとおり「操作の対象が回復によって事前に消える」という別種の相互作用は残る (データ破壊ではない) |

### X1〜X45 (並列エージェント 5 系統による探索)

（下記は 5 系統のエージェント報告を統合したもの。当初 X16〜X30・X31〜X45 を担当した 2 系統は
出力が 64,000 トークン上限を超えて失敗したため、各々 2 分割・簡潔化して再実行した。各エージェント
には文書を実際に読み具体的操作列でシナリオを追うことを義務付け、疑わしい点には §引用と再現
シナリオを要求した。「疑わしい点を検出」として報告された項目は監査者本人が全件独立に再検証し、
既存ラウンドで既に受理・却下済みの論点 (upload handle 上書きの既知の残余など) は却下、実害が
別レイヤーの安全機構で相殺される論点は severity を調整した上で採否を決定した。詳細な採否根拠は
第 3 部を参照）

#### X1〜X15

| # | 観点 | シナリオ (簡潔に) | 結果 |
|---|---|---|---|
| 27 | X1 | 作成→編集→削除が同一 tick 間隔に収まる一時ファイル | 問題なし (周期スキャンの必然的丸め。規約 11・§2 の複数デバイス上書き注記と矛盾しない) |
| 28 | X2 | Markdown 本文に `![evil](obj:...)` を偽装挿入した敵対的 PDF | 問題なし (§6 の本文エスケープ + §7 規則 3 の実在検証の二層防御) |
| 29 | X3 | macOS (NFD readdir) での report.pdf 作成→scan→保存→別 tick で in-place restore | 問題なし (§20.5 の NFC 論理名 + raw 解決で二重エントリなし) |
| 30 | X4 | 時計が 10 年先へ誤進行→NTP で復帰 | 問題なし (§20.5 の 72h 汚染兆候検出 + latest+1 続行 + fork のみ修復、という明示的トレードオフ) |
| 31 | X5 | 10 万 chunk 規模の一括再チャンク直後の Replicate | 問題なし (WAL + tick.lock、§19 が規模再考条件として自認) |
| 32 | X6 | 日本語 2 文字クエリ「検索」 | 問題なし (trigram 沈黙→LIKE fallback の完全な代替経路) |
| 33 | X7 | grammar v=2 移行時、画像を 1 つも含まない文書の版判定 | **Q06 検出** (先頭 img block が存在しない場合の判定手順が未規定) |
| 34 | X8 | metadata.sqlite 直接改竄による file_name=`../../../etc/target` | 問題なし (restore 時の §20.5 file_name 検証が独立した二重防御) |
| 35 | X9 | silent bit-rot した画像 object を検索結果から開く (§12) | **Q07 検出** (restore/GC/fsck にある hash 再照合が §12 に無い) |
| 36 | X10 | フォルダ zip 化→同一パスへ解凍 (全 inode 変化・byte 内容不変) | 問題なし (段 1 の inode ミスマッチでも規約 11 の content_hash 一致で無コミット) |
| 37 | X11 | 明示再生成 (floor 設定) 後、次 tick の相 1 UPDATE で floor が消えないか | 問題なし (相 1 の書換フィールド列挙に floor_generated_at は含まれない) |
| 38 | X12 | register→…→restore の E2E 一気通貫 | 問題なし (各段の入出力を § 単位で追跡完了。1 フォルダの re-embed 遅延が横断 KNN を FTS 縮退させる点は §8-e 自身が理由付き許容) |
| 39 | X13 | 「明示再生成/明示解決/明示再登録/誘導」の全出現箇所の§21 カタログ突合 | 問題なし (§21 前文が UI/CLI 具体化を明示的にスコープ外化) |
| 40 | X14 | collect の job 照会に 429 が続く | 問題なし (state 不変・attempts 不消費・retry_not_before 永続化) |
| 41-46 | X15 (反証 6 件) | 「重複課金は最悪 job 1 回分」「GC は fail-closed」「ready 照合が TOCTOU を防ぐ」「同一正規化コミットは同一 hash」「app.sqlite 全損は復元できる」「tick.lock で単一実行」 | **X15-1 で疑わしい点を検出** (→ Q05 に統合。job 一覧 API の結果整合性ラグが confirmed-absent の信頼性前提を崩し得る)。他 5 件は破れず (ただし X15-5/X15-6 は文書が最初から条件付きで自認する範囲) |

#### X16〜X22

| # | 観点 | シナリオ (簡潔に) | 結果 |
|---|---|---|---|
| 47 | X16 | kind=1 state=3 再投入で旧 upload_id が未清掃のまま相 2a が新 upload_id で上書き | 検出したが**却下** — §9.1 相 1 が「残骸はプロバイダ保持期限で自然消滅する既知の残余」と自己文書化済み (G-O08/BG-O07 として r11・r12・r13 で 3 回却下済みの論点の再発見。L949 で文言を再確認) |
| 48 | X16 | collect の 401/403 (アカウント変更) が job_missing の 404 トリガーに明示的に該当しない | 検出したが**格下げ** — job_missing の時刻基準フォールバックは「404 か一時失敗か判別できないプロバイダ」向けの汎用フォールバックであり、401/403 も最終的にこの経路で救済される。独立した finding としては採用しない |
| 49 | X17 | fork 手順 1〜4 完了直後 (次 tick の scan 前) に GC を実行 | **Q08 検出** (現在版原本 object が一時的に参照ゼロになり得る) |
| 50 | X17 | unregister→wipe→再登録 (再発見) | 問題なし (§9.3-a の初回同期分岐へ自然に合流) |
| 51 | X18 | agg 層に profiles 相当の表が無く、missing/offline フォルダのヒットで tool_profile_hash を人間可読情報へ解決できない | 検出したが**proposal に格下げ** — 機能的整合性 (join・hash 一致) には影響しない UX 上のニッチ (Q04 と同系統の「省略記法/情報欠落」カテゴリとして言及に留める) |
| 52 | X18 | 恒常的 stat エラーを返す兄弟エントリがある中での delete 確定 | 問題なし (完全 walk 必須の設計により誤確定はしない。当該枝が永続的にフル walk され続ける性能面の留意のみ) |
| 53 | X18 | app.sqlite 全損後の月次集計の正確性主張 | 問題なし (§16 が「記録できた課金」であり請求の正はプロバイダ側と明言、過大主張なし) |
| 54 | X19 | register 手順 2 (`.folder-history`/`tmp/` の mkdir) 直後に親ディレクトリ fsync 前でクラッシュ | 検出したが**minor 未満と判断** — §20.5 の dir fsync 規律は「rename 後」パターンを明示的にスコープするため新規 mkdir 自体への適用が字面上薄いが、実務上は同じ规律 (書込後 dir fsync) が適用されると読むのが自然な安全側の解釈であり、C11(b) の範囲に留まる |
| 55-59 | X20 (反証 5 件) | 「重複課金は最悪 job1 回分」「cost_ledger は月跨ぎ retry を正しく配賦」「宣言的 profile 変更はどのクラッシュでも収束」「fork は履歴再初期化で整合」「delete は pending_deletes で見逃さない」 | X20-1 は Q05 と同一論点 (収斂・裏付けとして採用)。X20-2 (月配賦) は**却下** — ts は「確定 (collect) 時刻」であり請求時刻の代理指標として明示的に設計された値である (§16 が既に「記録できた課金」と限定的に位置付け済み)。X20-3 (vec0 atomicity) は**却下** — SQLite の DDL-in-Tx 原子性は標準保証であり、これを疑う具体的根拠が文書からもドメイン知識からも得られない。X20-4 は #49 (Q08) と同一 |
| 60 | X21 | profile 反復切替 (P1→P2→P1→P2…) による attempts=0 リセットの反復で再課金無制限化 | 検出したが**proposal に格下げ** — 攻撃には利用者自身の意図的・反復的な設定変更が必要で、attempts 上限が想定する「自動的な失敗ループ」の脅威モデルとは性質が異なる |
| 61 | X22 | fork 手順 1 が永続的ストレージ障害で毎 tick 失敗し続ける | **Q09 に統合** (missing_since 型のエスカレーション機構の欠如) |
| 62 | X22 | `defer_foreign_keys=ON` と `foreign_keys=ON` (接続レベル) の相互作用 | 問題なし (Tx 終了時の自動解除という標準 SQLite 挙動と整合) |

#### X23〜X30

| # | 観点 | シナリオ (簡潔に) | 結果 |
|---|---|---|---|
| 63 | X23 | profile 往復 (A→B→A) 中の profile_changed 記帳と reconcile close 記帳の同一 seq 衝突、name_collision/name_invalid の下流到達性 | 問題なし (ON CONFLICT DO NOTHING は同一事象の再観測のみ吸収し正当な再投入は新規 seq を取る。name_collision/name_invalid は単一書込点で濾過され下流表に伝播しない) |
| 64 | X24 | embedding profile P1→P2 が偶然 dimensions/distance_metric 同一 (model のみ異なる) のケースで §8-c ローカル vec0 再作成トリガーの挙動 | **Q11 検出** (§8-c は次元・距離の構造比較のみで hash を見ないため DROP→CREATE が発火せず新旧混在ベクトルが残り得る。ただし §11.2 の embeddings 全行一致ゲートが移行中を検出し KNN を FTS のみへ縮退させるため、誤順位が表面化する実害はない) |
| 65 | X25 | watch_root 解除後も folders 起点 walk が継続、restore 宛先 4 入力の一意性、app.sqlite 単独でのクエリ embedding 生成 | 問題なし (§20.4 の明記どおりの意図された挙動。restore の 4 入力は一意な宛先か明示拒否に帰着) |
| 66 | X26 | register 直後・app_config 未設定 (tool_profile/embedding_profile が一度も設定されていない) 状態での相 1 実行 | **Q12 検出** (DDL CHECK により沈黙破損はしないが、この tick でのスキップ等の扱いが明文化されていない bootstrap 順序のギャップ) |
| 67 | X26 | submission_seq 3 書込点 (相 3/found 採用/client 前計上) と相 1 (state=3→0 再投入) の相互作用、client 前計上と server intent 回復の判別条件 | 問題なし (相 1 自体は seq を操作しない。batch_job_id 非 NULL かつ state=0 は client 前計上以外に到達経路がない) |
| 68 | X27 | 非追跡側コピーの fork (was_tracked=false) の全境界クラッシュ + bootstrap 順序 | 問題なし (§21.3 手順 3 の「was_tracked でない場合は旧行に触れない」を確認。生存側は無傷) |
| 69 | X28 | detached (state=1, cancel 未確定) 中に同一 repository_id が再登録される | 問題なし (folders 行の有無から動的導出される性質のため PK 衝突なく自動的に通常行へ復帰。有界コストとして§9.1 が明示済み) |
| 70 | X29 | case-insensitive→sensitive 移動後の大小文字 2 実体共存 + in-place restore | 問題なし (BINARY 一致の固定保存表記 + raw 解決の採用規則が一貫) |
| 71-76 | X30 (反証 6 件) | 「ledger UNIQUE は正当な再課金を妨げない」「client 経路は attempts 上限で有界」「fork はどの境界からも再開できる」「保存名固定で case-only rename の FK 違反は不可能」「最小不在時間 30 秒で偽 delete は不可能」「detached は課金を取りこぼさない」 | 全 6 件、破れず |

#### X31〜X38

| # | 観点 | シナリオ (簡潔に) | 結果 |
|---|---|---|---|
| 77 | X31 | 新規 repo の submission_seq 継承 (行なし INSERT) と相 3 の +1 の二重加算有無、reconcile 付随処理の state=0/3 網羅 | 問題なし (継承は行 INSERT 時のみで相 3 の +1 とは別軸) |
| 78 | X32 | fork 手順 1 完了直後クラッシュ→手順 2 前にフォルダを watch_root 外 (かつ既知 folders の root_path とも不一致) へ移動 | **Q09 に統合** (回復契機の walk 探索範囲外になり永久停止し得る) |
| 79 | X33 | client kind=2 の profile 変更 + unregister (detached) + 再登録 + 再投入の seq 連番 | 問題なし (target_key が profile 非依存のため継承が正しく機能) |
| 80 | X34 | §11.2 SQL の実行可能性 (LIKE fallback 再 JOIN・ORDER BY 第 2 キー・at_hash=FF) | 問題なし (軽微な記述完成度差はあるが正当性に影響なし) |
| 81-86 | X35 (反証 6 件) | 「seq 衝突不可能」「reconcile で client 記帳欠落なし」「submit_rejected は自動再投入されない」「fork は id=old から再開」「detached は取りこぼさない」「時計急変下の偽 delete は不可能」 | 4 件生存。X35-4 は #78 (Q09) と同一根拠。X35-6 は「不可能」という**絶対主張への文言上の反証** — §20.5 自身が「原子的に塞げない」残余窓を明記しており、絶対主張と実際の記述 (次回 walk による自己修復) の間に軽微な文言上のずれがあるのみで、実害を伴う独立した finding ではない |
| 87 | X36 | 冪等記帳×seq継承×detached採用の三者、profile A→B→A 往復での reconcile 再 close 試行 | 問題なし (全 close 経路が ON CONFLICT DO NOTHING + UNIQUE で一貫) |
| 88 | X37 | agg_vec の次元・距離が一致する profile 切替で §8-e の破棄トリガーが発火しないか | 詳細検証の結果**問題なし** — §8-e の該当文 (L662-664) は「agg_vec の次元と距離」**および**「app_config の agg 構築 profile (= agg_building_profile_hash という hash 値)」を現行 profile と照合し「いずれか不一致なら破棄」としており、後者の hash 比較が dims/distance 一致でも profile 切替を確実に検出する。§8-c との非対称は存在するが (→ Q11)、§8-e (集約層) 自体には同種の穴はない |
| 89 | X38 | fork 回復拡張の全数トレース (flag 掃除要件×中断中移動×再発見除外、journal digest 検証) | 問題なし (fail-closed の一貫性を確認。恒久的なギャップは #78 のケースのみに限定) |

#### X39〜X45

| # | 観点 | シナリオ (簡潔に) | 結果 |
|---|---|---|---|
| 90 | X39 | 同一 id の健全なフルコピーが、一時 EIO 中の登録済みパスと並行して walk に発見される | 問題なし (一時読取不能の保留規則が damaged/conflict への誤誘導を防ぐ) |
| 91-96 | X40 (反証 6 件) | 「冪等記帳で close Tx abort は不可能」「ready は空/部分 index を通さない」「fork 中移動で未完 fork は復帰しない」「一時読取不能で履歴は破壊されない」「delete 最終確認は対象外型置換を見逃さない」「vec の距離変更は必ず DROP→CREATE される」 | 全 6 件、破れず |
| 97 | X41 (総当りサマリ) | server/client×全終端理由×全 close 経路の総当り | 問題なし (各セルで seq 一意・0/1 行を維持) |
| 98-100 | X41 (個別) | client 再実行前記帳と client_exhausted の重複可能性 / (b') の seq+1 と token sweep・detached 化の交錯 / 期限超記帳→載せ直し→相 3 の連番 | 全 3 件、問題なし (各 attempt が個別 seq に 1:1 対応) |
| 101 | X41 | unknown 保持中に成果あり化した行を reconcile (b') と intent 回復のどちらが先に触るか | 問題なし (tick 順序 0.5→1/3 で reconcile が先行し排他的) |
| 102 | X41 | client の submit_rejected (内容起因 4xx) が「記帳なし」とする前提の妥当性 | 検出したが**proposal に格下げ** — プロバイダの実際の課金契約 (拒否時に部分課金し得るか) についての外部仮定に依存する指摘であり、文書内部の論理矛盾ではなく「文書外のプロバイダ規範」寄りの論点のため、独立した finding としては採用を見送る |
| 103 | X42 | フォルダ C が damaged の間に A/B のみで ready=P2 成立→C 復旧 (旧 P1 embeddings のまま)→母数復帰 | 問題なし (§8-e が「除外フォルダの復帰分も非同期の宿命」と明示的に仕様化済み) |
| 104 | X43 | resolver の 3 呼出点×NFD/NFC/collision/raw 無し×case 感度の行列 | 問題なし (3 点共通の解決規則が一貫) |
| 105 | X43 | resolver の readdir 列挙直後の外部 rename 競合 | 問題なし (O13 が既に自認する既知の限定的残余。次回 walk の name_collision/update で収束) |
| 106 | X44 | conflict 状態 (同一 id 2 箇所) の非主流側 (未登録のまま残る) への standalone 検索 | **Q10 検出** (規約 12 の「未登録 path の standalone read は正規利用」規則が conflict の非主流側にもそのまま適用され、conflict である旨の警告なく検索可能) |
| 107 | X44 | step -1 の z 判定×検出フォルダの除外×同 tick step5 wipe、fork 手順 3 の root_path×missing 猶予の交錯 | 問題なし |
| 108-115 | X45 (反証 8 件) | 「client の中間 attempt の課金は漏れない」「unknown で二重 job は作られない」「保持期限超の相 2b 残骸も記帳される」「state=0 server の成果あり close は無記帳破棄しない」「ready は damaged・空母数・synced 陳腐化に騙されない」「raw 解決で restore の二重実体は作られない」「登録済み path の read は差し替えを検出する」「step -1 で復元直後の誤課金は起きない」 | 6 件完全生存。「raw 解決で二重実体は作られない」は #105 と同一根拠で**部分反証** (ただし O13 の既知の限定的残余の範囲内)。「登録済み path の read は差し替えを検出する」は登録済み path 自体への差替えには有効だが、#106 (Q10) の未登録重複コピー経由の読取は別問題として残る |

探索ログ合計: **115 シナリオ** (監査者本人 26 + エージェント 5 系統 89)。X1〜X50 の全観点で最低 1
シナリオを実施 (50 シナリオ以上の要件を満たす)。2 系統が出力上限超過で失敗したが、分割・簡潔化して
再実行し欠落なく完遂した。

---

## 第 3 部 — 新規検出 (C1〜C8, C10〜C12)

| ID | 重大度 | 該当箇所 (§ + 短い引用) | 問題 | 再現シナリオ (初期状態 → 操作列 → 壊れる状態) | 根拠 (P#/C#/X#) | 修正案 |
|----|--------|--------------------------|------|--------------------------------------------------|------------------|--------|
| Q01 | major | §9.1 L1002 (期限超 confirmed-absent 記帳)・L1081/L1108 (token sweep・detached の「同じ規則」)・L1137 ((b') 記帳)。いずれも「submission_seq+1 … の冪等記帳」という cost_ledger への INSERT 記述のみで、`batch_requests.submission_seq` 自体を UPDATE するとは明記されていない。対照的に、相 3 (L970「…へ UPDATE」)・intent 採用 (L984「相 3 と同じ UPDATE」)・client 前計上 (L710, L727-728「app Tx で…を永続化」)・detached 採用 (L1102「…で state=1 の detached へ採用」) の 4 箇所は、submission_seq+1 を明示的に batch_requests 行の UPDATE として記述している。さらに cost_ledger.submission_seq 自体の DDL コメント (L852) は「**その時点の** batch_requests.submission_seq」と定義しており、この定義が成立するには batch_requests.submission_seq がその都度更新済みでなければならない | 期限超・(b')・token sweep の「無 id / job-id 発見」記帳経路が、cost_ledger へは新しい submission_seq 値 (現在値+1) を書き込む一方で、その +1 を `batch_requests.submission_seq` 列自体に persist することが文書上明記されていない。この状態で行の寿命が (削除されずに) 継続すると、次に自然発生する正規の記帳 (相 3 → collect 成功) が `batch_requests.submission_seq` の**古い**値を基準に同じ「+1」を計算し、既に期限超記帳が使用した seq 値と衝突する。UNIQUE (repository_id, kind, target_key, submission_seq) への `ON CONFLICT DO NOTHING` (§9.1 L1031-1034, L1069-1074) は「同一課金の再観測」の吸収を意図したものだが、この場合は**異なる 2 つの事象** (推定のみのフォルダ幽霊 job と、実際に完了した正規 job) が同じ seq に写像されるため、後発の正規 INSERT が黙って無視され、実際に発生した課金の正確な記録 (実測 cost_usd・実 job_id) が永久に失われ、代わりに不正確な推定行 (cost_usd=NULL, estimated=1) だけが残る | 初期状態: batch_requests 行 R = (kind=2, target_key=K, state=0, intent_token=T1, submission_seq=5, attempts=1, batch_job_id=NULL)。<br>1. 相2b が provider job J1 を作成 (metadata に T1 埋込) するが、相3 (state=1 への UPDATE) の直前でプロセスがクラッシュ。R は state=0, submission_seq=5 のまま残る。<br>2. デバイスが 3 日間オフライン (ノート PC を閉じる等、猶予メカニズムが前提とする現実的なシナリオ)。この間に J1 は provider 側の結果保持期限 (§6「約 24 時間」) を超えて消滅。<br>3. 再開後、submit の intent 回復が R を処理: job 一覧照合で T1 は confirmed-absent、かつ T1 (UUIDv7) の時刻成分が (timeout_hours+結果保持期限+猶予1日) を超過 → 期限超処理へ。<br>4. 同一 Tx: (i) 未記帳 → (ii) `INSERT INTO cost_ledger (…, submission_seq=6, batch_job_id=T1, cost_usd=NULL, cost_estimated=1)` → (iii) attempts=2 → (iv) 新 token T2 で相1再実行。**この Tx は R.submission_seq を更新しない (文書に明記なし)** ので R.submission_seq は 5 のまま。<br>5. 次 tick: T2 で相2a/相2b が成功し新 job J2 作成。相3 が `UPDATE batch_requests SET state=1, submission_seq=submission_seq+1 (=6), attempts=3, …`。R.submission_seq は今度こそ 6 になる。<br>6. J2 の collect が成功: `INSERT INTO cost_ledger (…, submission_seq=6 [=R.submission_seq の現在値], batch_job_id=J2, cost_usd=<実測額>, cost_estimated=0) ON CONFLICT (…) DO NOTHING`。<br>7. **この INSERT は無視される** — (repo, kind=2, K, seq=6) は手順 4 で既に埋まっているため。J2 の実際の課金 (実測額) は台帳から永久に失われ、代わりに手順 4 の推定 (NULL, estimated=1) だけが seq=6 の記録として残る。R 自体は state=2 (成功) に正しく遷移するため、この記録喪失はどのステータス監視にも現れない | X46, C10-qq, C7 | 期限超処理 (ii)・(b') 処理・token sweep の各記帳ステップに、相 3 / intent 採用 / client 前計上 / detached 採用と同一のパターンで「同一 Tx 内で `batch_requests.submission_seq` を +1 へ UPDATE し、その新値を cost_ledger へ INSERT する」ことを明示する一文を追加する (例: 「(ii) 未記帳なら、同一 Tx で `UPDATE batch_requests SET submission_seq = submission_seq + 1` を実行し、その新しい submission_seq の値で cost_ledger へ NULL + estimated の冪等記帳を行う (batch_job_id = 当該 intent_token)」)。これにより cost_ledger.submission_seq の DDL コメント「その時点の batch_requests.submission_seq」という定義とも整合する |
| Q02 | minor | §21.4 L2675-2679 (in-place restore の working 保全)。「書込の前に対象ファイルを §20.5 手順 1 の安定確認で読み、現内容の content_hash が現在版 (LWW) と異なる場合は、先に通常のコミット…で履歴化してから上書きする」 | restore の working 保全ステップが依拠する §20.5 手順 1 の安定確認自体が失敗した場合 (対象ファイルが書込み中で 2 回の stat が食い違う) に、restore がどう振る舞うべきかが明記されていない。通常のスキャン文脈での安定確認失敗は「壊れた中間状態はスキップして次回スキャンに回す」(§20.5 手順 1) という安全な既定動作を持つが、これは「ファイルに一切触れない」読み取り専用の文脈で安全なのであって、restore の保全ステップという「この後に上書きが控えている」文脈にそのまま転用できるかは自明ではない。もし実装が「安定確認失敗 → 保全をスキップしてそのまま上書きへ進む」という解釈を取れば、O09 (r13 の major 修正) が塞いだはずの「履歴ツール自身の操作による唯一の不可逆なデータ喪失経路」が、この一つの未規定分岐において再現し得る | 初期状態: フォルダ F の report.docx、LWW=commit C5。ユーザーが Word で report.docx を編集中 (自動保存が数百ms間隔でファイルへの書込みを継続)。<br>1. 別途、ユーザーまたは自動化が restore(F, "report.docx", commit=C3, in-place) を実行、tick.lock を取得。<br>2. §21.4 手順 3a の安定確認 (2 回の stat) が Word の書込みタイミングと重なり、mtime/size が 1 回目・2 回目で食い違う → 安定確認失敗。<br>3. 文書はこの分岐の挙動を定義していない。実装が「スキップして上書きへ進む」を選んだ場合、Word が保持している未保存 (かつ安定して読み取れなかった) 編集内容は一度も履歴化されないまま restore の tmp→rename で上書きされ、working からも履歴からも消える | X48, X50-25, C11(a) | §21.4 手順 3a に「安定確認が失敗した場合は保全を経ずに上書きへ進まず、restore 操作全体を中止して次回再試行を促す (status 表示)」ことを明記する。あるいは、安定確認を有界回数だけリトライしてから中止する規則を追加する |
| Q03 | proposal | §21 前文 L2467-2470 (回復先行) と §21.2 unregister の相互作用 | fork(A) が ID_WRITTEN でクラッシュした直後 (repository-id ファイルは既に new_id、folders 行は旧 old_id のまま) に、ユーザーが古い認識のまま `unregister(old_id)` を発行すると、tick.lock 取得直後の回復先行 (O11) が手順 3 を完了させて old_id の folders 行を削除・new_id の folders 行を作成した**後**に unregister 本体が実行される。この時点で unregister の対象 (old_id の folders 行) は既に存在しないため、多くの実装では無害な no-op に帰着するが、ユーザーの本来の意図 (「このフォルダを追跡から外したい」) は new_id 側には及ばず、フォルダは追跡され続ける。データ破壊ではないが、驚き最小の原則の観点で言及に値する | 上記の説明のとおり (抽象的な UX 上の懸念であり、データ破壊やクラッシュを伴う具体的な壊れる状態は構成できないため proposal 扱いとする) | X49 | §21.7 または unregister の記述に「fork 回復により対象 repository_id が新 id へ引き継がれていた場合、unregister は新 id に対しては適用されない (no-op) — 引き続き追跡を止めたい場合は新 id を明示的に指定する」旨を一文添える |
| Q04 | proposal | §9.2 L1298 (agg_chunk_fts の定義)。「agg_chunk_fts: §5.5 と同一定義 — content には view agg_chunks_fts_src … を指定し (content_rowid='chunk_uid')、trigger は §5.5 の 2 本を表名・rowid 名の読み替えで適用」 | agg_chunk_fts の CREATE VIRTUAL TABLE および 2 本の trigger (chunks_ai/chunks_ad 相当) の実 DDL が §5.5 のような形で spelled out されておらず、「読み替えて適用」という参照のみで済まされている。読み替え規則自体は機械的 (chunk_id→chunk_uid、chunks→agg_chunks 等) で一意に導出可能ではあるが、C2(e) 「同形・同一定義等の省略記法が実装者が一意に再現できるだけの具体性を持つか」という観点では、§5.5 のように実 DDL を掲載する他のテーブルとの一貫性を欠く | 実装可能性は損なわれない (読み替え規則が単純明快なため) ため、再現可能な「壊れる状態」を構成できない | C2(e), C11 | agg_chunk_fts の CREATE VIRTUAL TABLE と 2 本の trigger を §5.5 と同様に実 DDL として §9.2 に掲載する (または「読み替え規則」自体を明示的に列挙する) |
| Q05 | major | §9.1 L989-991「unknown = 照会自体の失敗…は「不存在」と解釈しない…不存在扱いで載せ直すと実在 job と二重になり「最悪 1 job」の有界化が破れる」と L1008-1009「期限内の不一致は未作成として…行を今回の投入対象へ載せ直す (新 intent_token で相 1 から)」を対照 | 「confirmed-absent」(job 一覧の正常応答に対象 token が無い) の判定は、プロバイダの job 一覧 API が常に最新状態を強い一貫性で反映することを暗黙の前提としている。文書自身が unknown (照会失敗) の扱いの理由付けとして「不存在扱いで載せ直すと実在 job と二重になり有界化が破れる」と明記しているが、**この同じロジックは job 一覧 API が結果整合性 (eventual consistency) しか持たない場合の「照会は成功したが最新状態を未反映」ケースにも等しく当てはまる**。文書全体を検索しても「反映遅延」「結果整合性」等への言及は無く (grep 0 件)、confirmed-absent は HTTP レベルの成功/失敗でしか判定されていない。「期限内」の再投入経路には期限超経路が持つ記帳保護が一切無いため、job 作成直後の短い時間窓でこの経路が発火すると、実在する job と新規 job の両方が処理・課金され得る | 初期状態: batch_requests 行 R = (kind=2, state=0, intent_token=T1)。<br>1. tick N で相 2b が provider job J1 を作成 (metadata に T1 埋込)。相 3 実行前にプロセスがクラッシュ。<br>2. **dirty 早回し (§20.5 に「100ms 間隔もあり得る」と明記) により、ごく短い間隔で tick N+1 が起動**。<br>3. tick N+1 の intent 回復が R を処理: job 一覧を T1 で照合するが、J1 の作成がプロバイダ側の一覧インデックスへ未反映 (結果整合性のラグ) のため confirmed-absent と判定される。<br>4. T1 の時刻成分は「期限超」の閾値 (timeout_hours+結果保持期限+猶予1日、通常数十時間規模) に遠く及ばないため「期限内」分岐へ: 記帳も述語チェックも行わず、新 token T2 で相 1 から即座に載せ直す。<br>5. 直後に相 2a/相 2b が成功し、新 job J2 が作成される。<br>6. J1・J2 の両方がプロバイダ側で並行して処理・完了し、両方に課金が発生する。J1 はどの batch_requests 行からも参照されなくなる (token は T2 に置き換わった) ため、その課金は cost_ledger に一切記録されないまま実際には発生する — 不可視の二重課金 | X15 (X1-X15 担当エージェントが検出、監査者が独立検証), P9 の「重複課金は intent 回復により最悪 job 1 回分に有界」、N02 (三値化導入時の意図と同一ロジックの不完全な適用) | 「期限内」の載せ直し分岐にも、直近発行された token に限り期限超と同様の軽量な記帳済み判別 + 保守的な記帳を適用するか、token 発行から一覧 API の想定伝播時間 (例: 数秒〜数十秒) を経過するまでは confirmed-absent でも「unknown」相当として扱い載せ直さない猶予を設ける。あるいは、対象プロバイダ (Mistral Batch API) の job 一覧 API が強い一貫性を持つことが確認済みであれば、その前提を明記する |
| Q06 | minor | §6 L522-524「旧版行の特定は追跡列を持たず、markdown_documents を全走査して保存済み Markdown の先頭 img block の `v:` 行を読んで判定する」 | grammar version (`v`) は img block 内にのみ出現するフィールドであり、画像を 1 つも含まない文書の Markdown には先頭 img block 自体が存在しない。この場合の判定手順が明記されておらず、実装が (a) img block 不在をエラーとして扱う、または (b) 「v 不明 = 旧版」と誤判定して不要な DELETE→INSERT 再構築と generated_at 更新 (§9.3-b の集約差集合を無駄に発火) を行う、のいずれかにブレる余地がある | 初期状態: 画像を含まない純粋テキスト PDF の markdown_documents 行 (img block 無し)。<br>1. grammar v=2 への移行が発生し、一括再 materialize スキャンが全 markdown_documents を走査。<br>2. この文書の行を処理する際、「先頭 img block の v: 行」を読もうとするが img block 自体が存在しない。<br>3. 文書はこの分岐を定義していないため、実装によって不要な再処理またはスキャン中断のいずれかが起き得る | X7 (X1-X15 担当エージェントが検出、監査者が独立検証), C11(a) | 「先頭 img block が存在しない (画像 0 件の) 文書は grammar version の対象外であり常にスキップする (grammar 版は画像 encoding にのみ関わるため)」と明記する |
| Q07 | minor | §12「検索結果から原本への解決」の記述には、§21.4 restore 手順 1 や GC/fsck (§13) にある「読んだ bytes の SHA-256 を再計算して名前と照合する」という検証ステップが無い | objects/ 内のオブジェクトが silent bit-rot (読めるが hash 不一致) を起こした場合、restore や GC/fsck はこれを検出して中断・報告するが、検索結果から「原本を開く」(§12) という最も頻繁に使われるであろう経路には同等の検証が明記されていない。週次 fsck が最終的に検出するまでの間、破損したオブジェクトが無検証のまま「原本」として提示され得る | 初期状態: objects/ 内のある画像 object (image_hash=H) がストレージ層で静かにビット腐敗 (読めるが SHA-256≠H)。<br>1. ユーザーが横断検索でこの画像を含むチャンクをヒットさせ、§12 の解決チェーンで「objects/ の画像実体」を開く。<br>2. 文書にはこの経路での hash 再照合が明記されていないため、実装によっては破損した bytes がそのままユーザーへ提示される。<br>3. 週次 fsck (§13) が実行されるまでの間 (最大 1 週間)、この状態は検出されないまま続く | X9 (X1-X15 担当エージェントが検出、監査者が独立検証), C4, C11(a) | §12 の解決チェーンに「objects/ から読んだ bytes は SHA-256 を再計算し content_hash/image_hash/markdown_hash と照合してから提示する (不一致は fsck §13 へ誘導)」ことを明記する。restore の既存規範を援用する形で追記すればよい |
| Q08 | minor | §21.3 手順 1「`DELETE FROM commits`」(L2584, file_versions は FK CASCADE で全行削除。**過去版・現在版を区別しない**) と §13 GC 参照集合 1 本目「`SELECT content_hash FROM file_versions`」(L1815) を対照 | fork の手順 1 は当該 repository の commits/file_versions を**全行**削除する (「派生台帳と objects/ は保持する」のは markdown_documents/chunks/embeddings/profiles と objects/ 自体のみで、file_versions 自体は現在版・過去版の区別なく空になる)。この直後 (手順 2〜4 完了後、次 tick の scan が新規コミットとして現在版を再確立するまでの間)、GC の参照集合 1 本目 (file_versions.content_hash) は当該 repository について**何も返さない**。GC がこの狭い窓で実行されると、現在も working ツリーに存在するファイルの原本 object が「参照ゼロ」に見えて回収され得る (§21.3 手順 5 は「過去版のみの原本 object を次 GC が回収する」を意図された挙動として明記するが、**現在版の原本まで巻き込まれる**ケースは想定されていない) | 初期状態: repository R (フォルダ実体は健在、現在版ファイル F・content_hash=H が objects/ に存在)。<br>1. fork(R) が手順 1〜4 を完了 (commits/file_versions 全削除、repository-id は new_id、folders 行も new_id で再作成)。この時点でまだ次 tick の scan (step 0) は走っていない。<br>2. fork も GC も tick.lock を要求するが、fork が lock を解放した直後に (定期スケジュールされた) GC が次 tick の scan より先に lock を取得して実行される。<br>3. GC の参照集合 1 本目が空 (file_versions に F の H への参照が無い) であり、H の object が作成後 24h grace を過ぎていれば削除対象に含まれ得る。<br>4. **ただし working ツリーの F 自体は無傷** (fork は working ファイルに触れない) なので、次 tick の scan が F を再ハッシュし「objects/ に H が存在しない」ことを検出して再保存する — 自己修復するが、その窓の間に §12「原本を開く」を実行したユーザーは一時的に解決失敗を経験し得る | X17/X20-4 (X16-X22 担当エージェントが検出、監査者が独立検証: fork の全行 DELETE と GC 参照集合 1 本目を実文書で確認), C10 (fork 手順 5 の想定と手順 1 の実際の削除範囲の食い違い) | §21.3 手順 5 の注記に「現在版の原本 object も手順 1〜4 完了後・次 scan 完了前の窓では一時的に参照ゼロになり得るため、fork 完了直後の GC 実行は次 tick の scan 完了を待ってから行う (または fork 完了直後の対象 repository を GC の対象から一時除外する)」ことを明記する |
| Q09 | minor | §21.3 の失敗回復契機全体 (特に「毎 tick の walk が watch_roots 配下と既知 folders から fork-journal を持つフォルダを検出したら…回復を完了する」) と §20.4 の `missing_since` による 30 日猶予後の自動退役を対照 | fork が (a) 手順 1 の metadata Tx が永続的なストレージ障害で毎 tick 失敗し続ける、または (b) 手順完了前にフォルダが watch_roots 外・既知 folders 行の root_path とも一致しない場所へ移動される、のいずれかの理由で恒久的に完了できない場合、fork_in_progress フラグと journal は無期限に残存し、当該 repository は tick 全ステップから除外され続け、「fork 進行中」status 以外の兆候をユーザーに与えない。`missing_since` (§20.4) が持つ「猶予後に自動退役 (status を missing→retired へ)」という**エスカレーション機構**が §21.3 には無い | 初期状態: repository R (id=OLD)、realpath=/P、watch_root W=/W (/P は /W の配下)。<br>1. fork(R) を実行、手順 0 (journal 書込) 完了、手順 1 (commits 全削除、phase=HISTORY_CLEARED) 完了直後にクラッシュ。<br>2. クラッシュ直後、/P をどの watch_root の配下でもなく他の folders 行の root_path とも一致しない場所 /Q へ移動する。<br>3. 回復契機 (b) は「watch_roots 配下と既知 folders」を探索範囲とするが、/Q はそのいずれにも属さないため fork-journal は発見されない。<br>4. fork_in_progress=(OLD, /P) は永久に残存し、/Q (実体は健在) はどの tick 処理からも除外され続ける。ユーザーが明示的に /Q を register しない限り自然回復する経路が無い | X16#15・X32/X35-4 (X16-X22・X31-X38 担当の 2 系統がそれぞれ異なる根本原因 — 永続的ストレージ障害・watch scope 外への移動 — から同一の「エスカレーション機構欠如」という症状を独立に検出、監査者が統合・独立検証) | fork_in_progress にも開始時刻を記録し、missing_since と同様の猶予期間 (既定案: 30 日) を設け、猶予超過時は status を「fork stalled — 手動介入が必要」へ格上げする。加えて、回復契機 (b) の探索範囲を「watch_roots∪folders.root_path」に限定せず、journal が記録する realpath 自体を定期的に (移動されていないか) 直接チェックする経路を補助的に追加することで経路 (b) を軽減できる |
| Q10 | minor | §20.4「同一 repository-id の 2 箇所目を検出した場合…conflict として status 表示」と §15 規約 12「folders に行が無いパスの読み取り (未登録・持ち込みコピーの standalone 検索) は層 1 自己完結の正規の利用として実行可」を対照 | 同一 repository-id を持つフォルダが 2 箇所に存在し conflict 状態にある場合、規約 12 に基づき「登録済み (folders 行がある) 方」だけが照合対象となり、conflict の原因となっているもう一方 (conflict 検出時に folders へは登録されず未登録のまま残る) は「未登録 path の standalone 読み取り」規則の対象になり、拒否も警告もされない。ユーザーが誤って conflict の非主流側を検索・閲覧しても、システムは「これは conflict 中の複製の一方である」ことを伝えない | 初期状態: repository R (id=X) が Location1 (folders 登録済み) に存在。ユーザーが Location1 を丸ごと Location2 へコピー。<br>1. 次 tick の walk が Location2 で id=X の `.folder-history` を発見。「同一 repository-id の 2 箇所目」として conflict + status 表示 (folders 行は Location1 のみ、Location2 は未登録のまま)。<br>2. ユーザーが Location2 を対象に standalone 検索を実行する。<br>3. 規約 12 は「folders に行が無いパスの読み取りは正規の利用」と定めており、Location2 は folders に行が無い (conflict により登録されなかった) ため、この検索は拒否されず repository-id=X を provenance として結果が返る。conflict 状態にあることはこの検索結果には一切反映されない | X44 (X39-X45 担当エージェントが検出、監査者が独立検証) | standalone 読み取りの規約 12 照合に「対象パスの repository-id が、別のパスに登録済みの状態で conflict 中である場合はその旨を provenance に含めて status 表示する」ことを追加する。あるいは conflict 検出時に非主流側の `.folder-history` 配下へ一時的なマーカーを残し、以降の読み取り操作がこれを検出したら「conflict 中の複製」である旨を表示する |
| Q11 | minor | §8-c「vec 表は Embed submit 冒頭で**次元と距離 (distance_metric)** を現行 profile (§5.7 record) と照合し、いずれか不一致なら DROP → CREATE する」(L651-652) と §8-e「agg_vec の次元と距離**と app_config の agg 構築 profile (= hash 値) を**現行 profile と照合し、いずれか不一致なら破棄」(L662-664) を対照 | フォルダ単独 (ローカル) の embedding_vec 再作成トリガー (§8-c) は次元・距離という**構造的な**性質のみを照合し、profile の**識別子 (hash)** そのものは照合しない。これに対し集約層 (§8-e) は次元・距離**に加えて** app_config の hash 値 (agg_building_profile_hash) も照合しており非対称である。dimensions と distance_metric がたまたま同一で model 名など hash に影響する部分だけが異なる profile 変更 (§5.6 DDL コメントが警告する「距離だけの変更が次元一致で見逃される」問題と同じ構造の、より一般化された版) では、§8-c の DROP→CREATE が発火せず、フォルダ側 embedding_vec に新旧 profile のベクトルが混在したまま残り得る | 初期状態: フォルダ F で embedding profile P1 (dimensions=768, distance_metric=cosine) により embedding_vec が構築済み。<br>1. embedding profile を P2 (同じ dimensions=768, distance_metric=cosine だが異なるモデル・重み) へ変更。<br>2. 次 tick の Embed submit 冒頭、§8-c の照合は「次元と距離」のみを見るため P1 と P2 は一致と判定され DROP→CREATE が発火しない。<br>3. P2 の再 embed が進むにつれ、embeddings 側は新旧 profile_hash が混在する行として蓄積されるが、embedding_vec (vec0) 自体は再構築されないため P1 時代のベクトルと P2 の新ベクトルが同一空間に物理的に混在し得る。<br>4. **ただし §11.2 のフォルダ単独検索の現行決定規則「embeddings の全行一致検査で得られる一意な embedding_profile_hash」がこの移行期間中は不一致 (複数 hash 混在) を検出し、KNN 経路自体を実行させず FTS のみへ縮退させる**ため、誤った順位付けが実際にユーザーへ提示される実害には至らない (belt-and-suspenders の一方が欠けているが、もう一方が機能している) | X24 (X23-X30 担当エージェントが検出、監査者が独立検証: §8-c/§8-e 双方の原文を対照し §11.2 ゲートによる相殺を確認) | §8-c の照合条件に「次元・距離に加え、embedding_profile_hash 自体も現行 profile と一致するか」を明記し、§8-e と同水準の hash ベース判定に揃える。これにより §11.2 のゲートに依存しない、より直接的な一貫性が得られる |
| Q12 | proposal | §21.1 register の記述と §9.1 相 1 (「投入時 profile snapshot を書く…kind=2 は profile_hash=現行」) を対照。register 自体には app_config (tool_profile/embedding_profile) が設定済みであることを前提条件とする記述が無い | 新規登録されたフォルダに対し、app_config の tool_profile/embedding_profile が一度も設定されていない (真にブートストラップ直後の) 状態で tick の OCR/Embed submit の相 1 が実行されようとした場合の挙動が明記されていない。DDL の `CHECK (state NOT IN (0,1) OR profile_record IS NOT NULL)` により、profile_record が NULL のまま相 1 の INSERT/UPDATE を試みれば Tx は拒否される (沈黙破損はしない) が、「この tick で当該 repository の submit をスキップする」といった扱いが文書に明記されておらず、実装者の追加判断に委ねられている | 初期状態: 新規デバイスに folder-history アプリを初めてインストールし、watch_root を追加してフォルダを register したが、tool_profile/embedding_profile の初期設定 UI をまだ完了していない (app_config に該当キーが存在しない)。<br>1. dirty イベントまたは定期 tick が起動し、OCR submit の相 1 が対象ペアを見つけて investment を試みる。<br>2. 現行 tool_profile record が存在しないため、相 1 の INSERT が `profile_record` を NULL のまま書き込もうとし DDL CHECK に拒否される (kind=1 は profile_hash 自体は NULL 許容だが profile_record は state=0/1 で必須)。<br>3. この Tx 失敗をどう扱うか (この repository の submit だけスキップして次回 tick で再試行する、エラーとして status に出す、等) が文書に明記されていない | X26 (X23-X30 担当エージェントが検出、監査者が独立検証) | §21.1 register または §10 tick の記述に「app_config の該当 profile が未設定の場合、submit はその kind をスキップし status に『profile 未設定』を表示する。DDL の CHECK 制約が保証する fail-closed な安全側の挙動として明記する」旨を一文追加する |

---

## 第 4 部 — 確認済みの列挙

検出 0 件として確認した観点:

- **C1** (P1〜P16 の反映): 全 16 原則が文書に反映され、内容の弱まり・条件の脱落は検出されなかった
  (O01〜O30 を含む r13 由来の修正すべてが文書に忠実に反映されている)
- **C2** (SQL 静的検証): 全 DDL で GENERATED 列構文、WITHOUT ROWID + PK の関係、CHECK 論理、
  FTS5 external content + content_rowid、FK 参照先の存在・列数一致、trigger の insert/delete
  対称性を確認。省略記法 (agg_chunk_fts) は Q04 として軽微に指摘したが実装可能性は損なわれない
- **C3** (相互参照整合): 文書内の § 参照を広範に確認し、実在しない参照・文脈不一致は検出されなかった
- **C4** (クエリとスキーマの整合): §11.1/§11.2 のハイブリッド検索 SQL、§9.3-a のカーソル SQL、
  §13 の GC 差集合が同文書の DDL と列名・join キーの型/形式で整合することを確認 (Q07 は
  「整合」ではなく §12 に固有の検証ステップ欠落を指摘するものであり、C4 の不合格事由ではない)
- **C5** (数値・事実の一貫性): $2.5/1k・+25%・768(参考値)・RRF k=60・8 テーブル・app_config
  7-key・30 日猶予・k_max=4,096・最小不在時間 30 秒・許容 skew 5 分など、全出現箇所で一致
- **C6** (用語・形式の一貫性): target_key 連結形式・chunk_type/target_type 対応・obj: スキーム・
  embed_hash 定義がすべて一貫。target_key の hex() 大文字小文字は DDL コメント直後に
  lower(hex()) 注記がありフォローされている
- **C7** (状態機械の完全性): batch_requests の全状態遷移 (0→1/2/3, 1→2/3, 2→(再訪なし),
  3→0/2) を検査し、detached・client 側キュー・期限超・(b')・token sweep を含め到達不能・
  脱出不能な分岐は検出されなかった。ただし Q01 は状態遷移そのものではなく「同じ状態遷移が
  異なる 2 つの実世界事象を同じ seq スロットへ写像し得る」という記帳内容の正確性の問題であり、
  Q05 は状態遷移表自体ではなくその**遷移条件の判定根拠 (confirmed-absent) の信頼性前提**の問題
- **C8** (欠落章): 全 21 章 (§1〜§21、付随する §20.1〜§20.5・§21.1〜§21.7 を含む) が存在し、
  空・TBD の章は無い
- **C11** (実装可能性): Q01・Q02・Q08・Q09・Q11・Q12 は C11(a) (追加の設計判断が必要) の
  観点から指摘したが、いずれも「実装不能」ではなく「未規定の分岐が実装者の判断に委ねられ、
  誤った判断が実害を伴う」という水準に留まる。C11(d) (検証不能・過剰規範) に該当する新規検出は無い

新規検出はあったが「観点そのものとしては網羅的に検査し、深刻な体系的欠陥は検出されなかった」もの:

- **C10** (修正が開けた穴): (a)〜(tt) の全観点を検査し、r9〜r13 で繰り返された「close 経路の
  記帳漏れ」系統の regression は 0 件 (4 ラウンド連続)。Q01 は C10-qq (期限超同一 Tx × token
  rotation × attempts) が示唆する領域からの発見だが、qq 自体が明示的に問うている
  「attempts+1 と profile 数え直しの交錯」自体は問題なしと判定し (X46-3)、qq が明示的には
  触れていない「submission_seq の書込先」という角度から Q01 を検出した。Q11 も同種で、
  §8-c と §8-e という 2 つの既存の正しい規範の**間の非対称**から検出された
- **C12** (探索型監査): 監査者本人 26 シナリオ + エージェント 5 系統 89 シナリオ (X1〜X45、
  うち 2 系統は出力上限超過で分割再実行) の計 115 シナリオにより、Q01 (major)・Q05 (major)・
  Q02/Q06/Q07/Q08/Q09/Q10/Q11 (minor 7 件)・Q03/Q04/Q12 (proposal 3 件) を検出。同時に、
  過去ラウンドで既に採用・却下判定済みの論点 (upload handle 上書き=既知の残余、raw 解決の
  TOCTOU 残余窓=O13 で既に自認済み等) が複数のエージェントから独立に再発見されたが、
  既存の裁定と照合した上で却下し、二重計上しなかった

**破れなかった主張** (X15/X20/X30/X35/X40/X45/X50、計 8 セット・50 件超の反証チェックポイントの最終結果):
- 「無 id 記帳は NOT NULL と衝突しない」→ 完全生存
- 「記帳済み判別で推定行は増殖しない」→ 文字どおりには生存 (ただし Q01 は別種の問題)
- 「(b') が飛んでも sweep が記帳を回収する」→ 完全生存
- 「detached は期限超でも記帳してから消える」→ 完全生存
- 「未来時計 token で無記帳載せ直しは起きない」→ 完全生存
- 「§6/§7 の往復は全段可逆」→ 完全生存
- 「restore は未取り込みの working 変更を消さない」→ **部分的に破れる (Q02)**
- 「明示操作は未完 fork に反転されない」→ 文字どおりには生存 (X49-15 は「反転」ではなく
  「対象の事前消失」という別種の観察)
- 「重複課金は intent 回復により最悪 job 1 回分に有界」→ **部分的に破れる (Q05)** — 期限内
  reload 分岐には期限超分岐と同水準の保護が無い
- 「client 経路の重複課金は attempts 上限で有界」→ 完全生存
- 「fork はどの境界のクラッシュからも journal で一意に再開できる」→ 文字どおりには生存するが、
  **前提 (walk が journal を発見できること) 自体が崩れるケースが存在する (Q09)**
- 「保存名固定により case-only rename の FK 違反は構造的に不可能」→ 完全生存
- 「最小不在時間 30 秒で dirty 早回しの偽 delete は不可能」→ 完全生存
- 「ready は damaged・空母数・synced 陳腐化に騙されない」→ 完全生存
- 「登録済み path の read は差し替えを検出する」→ 登録済み path 自体には有効だが、
  **未登録の conflict 複製という別経路が残る (Q10)**
- 「vec の距離変更は必ず DROP→CREATE される」→ 集約層 (§8-e) では完全生存、
  **フォルダ単独層 (§8-c) では次元・距離一致時に生存しない (Q11)**
