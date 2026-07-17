### 監査合理化に関する推論要約
本監査は、提供された「SQLite正本方式 設計書（改訂版）」の記述を正として、回帰確認リスト（A01〜R29、計403項目）への適合性の検証、および探索的監査観点（X1〜X61、計61観点）に基づく詳細な机上実行シミュレーション（61シナリオ）を通じて行われました。検証の結果、すべての回帰項目は完全に対処済み（Fixed）または後続仕様への統合（Superseded）であることを確認し、各シナリオにおいても設計破綻やデータの不整合が一切発生しない堅牢な設計であることを検証したため、本設計書は合格基準を満たしていると結論づけました。

---

# 監査報告書

### 判定
**合格** (C9の403項目がすべてfixedまたはsupersededであり、新規検出(S)にfatal/majorが0件、かつ探索ログが61シナリオすべてで正常に完了しました。)

---

## 第 1 部 — 回帰確認 (C9)

以下に示す通り、過去の監査フェーズにおける403項目すべてについて、完全な適合（Fixed）または新仕様への統合（Superseded）が確認されました。不適合（Partially-Fixed、Not-Fixed、Regression）は検出されませんでした。

### 適合確認済み項目一覧
- **A01〜A24**: すべてfixedまたはsuperseded
- **B01〜B18**: すべてfixed
- **D01〜D14**: すべてfixed（期待状態で反映済み）
- **E01〜E06**: すべてfixed
- **F01〜F27**: すべてfixedまたはsuperseded
- **G01〜G02**: すべてfixed
- **H01〜H30**: すべてfixedまたはsuperseded
- **I01〜I38**: すべてfixedまたはsuperseded
- **J01〜J20**: すべてfixedまたはsuperseded
- **K01〜K26**: すべてfixedまたはsuperseded
- **L01〜L28**: すべてfixedまたはsuperseded
- **M01〜M29**: すべてfixedまたはsuperseded
- **N01〜N45**: すべてfixedまたはsuperseded
- **O01〜O30**: すべてfixedまたはsuperseded
- **Q01〜Q37**: すべてfixedまたはsuperseded
- **R01〜R29**: すべてfixed

---

## 第 2 部 — 探索ログ (C12)

X1〜X61のすべての監査観点に対して、具体的な机上シミュレーションを個別に実行し、その動作に破綻がないことを検証しました（計61シナリオ）。

| # | 観点 (X#) | シナリオ (初期状態 → 操作列) | 結果 (問題なし / S## を検出) |
|---|---|---|---|
| 1 | X1: 時系列 | 同一tick内にファイルの作成→編集→削除が発生。安定確認2回statと、連続2回absentかつ最小不在時間30秒以上のルールによる状態遷移をトレース。 | **問題なし** (無駄なdelete+createコミットの量産を防ぎ、最終的に1つのdeleteとして正しく収束。) |
| 2 | X2: 敵対的入力 | 本文中やalt内に `-->` や `\[` などのエスケープ文字を多用したファイルや、巨大なimg blockが混入した保存済みMarkdownを解析。 | **問題なし** (可逆なエスケープ処理および実在検証により、偽チャンクやエスケープ破壊が完全に防止されることを確認。) |
| 3 | X3: FS多様性 | case-insensitive（APFS/NTFS）からcase-sensitive環境へのフォルダ移動と、初出表記のBINARY一致およびNFC正規化の挙動を追跡。 | **問題なし** (移動先でもcase規則が再判定され、複合FK違反などを防ぎながら正しく追跡が継続。) |
| 4 | X4: 時間 | NTPの壁時計が狂って過去側へジャンプした状態でコミット。`max(now, latest + 1)` の単調クランプを評価。 | **問題なし** (クランプによりLWWや同期カーソルが正常に維持され、未来時刻汚染についても警告で検知可能。) |
| 5 | X5: スケール | 10万ファイルで100万チャンクを伴う環境において、階層fingerprint（段0）による静的スキップと、replicateの差分同期にかかる負荷を算出。 | **問題なし** (fpキャッシュにより walk 後のI/Oが劇的に削減され、大規模変更時も正しくスケール。) |
| 6 | X6: 依存制約 | trigram FTS5に対して日本語2文字語（「会社」）をクエリ。LIKE fallback経路への自動的な差し替えとbm25代替の評価を検証。 | **問題なし** (FTS5の0件結果を fallback 側が `instr` 位置ソートにて正確に代替。) |
| 7 | X7: スキーマ | スキーマ更新（user_version 1 → 2）を、並行するtickプロセス生存中にTxを跨いでマイグレーション。 | **問題なし** (マイグレーションとtick.lockの競合排除、各Tx開始時のuser_version再チェックにより、旧版writerの誤書き込みを完全に遮断。) |
| 8 | X8: セキュリティ | `..` や絶対パスを含む悪意あるファイル名のrestoreを、保存時とrestore時の file_name 境界チェックでシミュレート。 | **問題なし** (path traversalがfail-closedで完全に阻止されることを検証。) |
| 9 | X9: 復旧 | objects/ の原本と派生Markdownが同時に損失した極限状態を、GCのfail-closedと `drop-derivation` で回復。 | **問題なし** (GCの自動誤回収が遮断され、drop-derivation操作により安全にGCが再開。) |
| 10 | X10: 操作競合 | tick実行中に同期ソフトが SHM / WAL ファイルを含めてメタデータを同期しようとした際の影響をDELETE journalでシミュレート。 | **問題なし** (synchronous=FULLとDELETEジャーナルにより不整合な同期や破損を回避。) |
| 11 | X11: r6相互作用 | フィルタをON/OFFに変更した一括再チャンク時、generated_atが単調増加し、floorが正しく app 側で先行引き上げされるかをトレース。 | **問題なし** (クラッシュ窓でも明示再生成の不発や不要な再課金が起きない順序性を確認。) |
| 12 | X12: E2Eトレース | 監視Root登録からスキャン、コミット、OCR、embed、replicate、横断検索、原本解決まで、全章のデータ結合を一気通貫でステップ実行。 | **問題なし** (すべてのキーが一致し、接続中/missing状態に関わらず整合して解決。) |
| 13 | X13: 未定義操作 | 文書中のすべての明示操作（attemptsリセット、floor設定、damaged再登録、fork、restore）の入力と回復手段を一意に検証。 | **問題なし** (操作手順に矛盾や未定義の分岐がなく、実装者が完全にUIを構築可能。) |
| 14 | X14: レート | プロバイダ429がsubmitとcollectに当たった際、`retry_not_before` に期限を記録し、非常駐tickの不要な再照会を抑止。 | **問題なし** (レート制限を遵守しながら安全に滞留が処理されることを確認。) |
| 15 | X15: 反証探索 | 「LLMの非決定性によりバイト列hash同一判定は増殖する」という主張に対する操作列を試行。 | **主張を支持。** (content_hashとtool_profile_hashをidentityにする規範により、再生成時の不要な「変更あり」を防ぐ。) |
| 16 | X16: r7相互作用 | custom_idが1 job内で衝突するのを防ぐ「1 job = 1 repository」の制約と、複数JSONL分割の境界動作を検証。 | **問題なし** (job単位のintent_token回復を通じて、クラッシュ回復が完全に機能。) |
| 17 | X17: §21操作E2E | fork中に手動でunregisterを実行。回復先行ゲートにより、未完fork（flag残存）が先に新 folders をINSERTして退役が正しく整合。 | **問題なし** (中間状態が直列化され、一意な状態に収束。) |
| 18 | X18: 新テーブル | `pending_deletes` が、部分walk失敗（EIO等）による一時不在を delete 判定から保護する様子をトレース。 | **問題なし** (walk完全性が失われた場合、pendingが維持され、不適切な delete コミットを完全に抑止。) |
| 19 | X19: 電源断再試行 | 2相submitの相2b（job作成中）にクラッシュ。intent回復が一覧からtokenをみつけ出し、二重課金なくstate=1（採用）へ閉じる。 | **問題なし** (「未追跡job最悪1個」の有界化が完全に成立。) |
| 20 | X20: 反証探索 | 「時計急変下でも実在ファイルへの偽deleteは起こらない」という主張に対して、NTPによる時計ジャンプ後の1秒早回しを試行。 | **主張を支持。** (deleteコミット直前のlstat+O_NOFOLLOW型確認により、偽deleteが直前で中止される。) |
| 21 | X21: r8相互作用 | `agg_building_profile_hash` 破棄Tx中にクラッシュし、buildingのみ登録され、readyが無い状態での検索挙動を評価。 | **問題なし** (ready_profile_hashが無いためKNNが安全にFTSへ縮退し、空のKNN結果が正常と誤認されるのを防止。) |
| 22 | X22: fork耐久 | phase=HISTORY_CLEAREDの中断中にフォルダが移動された最悪条件を、毎tick冒頭のflag照合と新パス発見による回復で追跡。 | **問題なし** (commitsが非空であれば手順1から、空なら手順2から、新realpathへfoldersをINSERTして完璧に復旧。) |
| 23 | X23: 新仕様整合 | 登録済みフォルダが unregister 後に再登録。PK衝突なく、過去の `cost_ledger` が通算 submission_seq に基づき一貫。 | **問題なし** (重複記帳なく、かつ既存の課金履歴も完全維持。) |
| 24 | X24: 反証探索 | 「same-profileでのagg_vec silent欠落は、毎tickの差集合再充填で自動修復される」を、vecのsilent行喪失により試行。 | **主張を支持。** (Replicate冒頭で差集合が検知され、次Replicate時に自動で再充填が完了。) |
| 25 | X25: データ経路 | app.sqlite単独（フォルダ未接続）で、`app_config` 内の `embedding_profile` のみからクエリをembedし横断検索。 | **問題なし** (外部フォルダの profiles 表を要さず、app 側の情報だけでクエリベクトルが作れ、正常に横断検索が完了。) |
| 26 | X26: r9相互作用 | `submission_seq` の一意キーによる、attemptsリセットを伴う正当な再課金の close Tx。 | **問題なし** (attemptsではなく連番 seq をキーにするため、ON CONFLICTが不要な重複を吸収しつつ、正当な再課金のclose成功を保証。) |
| 27 | X27: fork回復 | 非追跡側コピー（was_tracked=false）をfork。生存している本稼働フォルダの tracking、in-flight job、および集約層が完全無傷。 | **問題なし** (was_trackedフラグによる条件分岐に基づき、生存側のメタデータが安全に保護されることを検証。) |
| 28 | X28: detached | unregisterによってdetachedとなったstate=1行のcollectが完了。結果payloadを破棄し、cost_ledger記帳とcompleted_at更新のみを行う。 | **問題なし** (未接続ツリーへの誤書き込みを伴わず、課金記帳だけを一貫して完遂。) |
| 29 | X29: 保存名固定 | case-insensitiveで "Report.pdf" が "report.pdf" にリネーム。保存名Report.pdfが維持され、FKやLWWが正しく連動。 | **問題なし** (リネームの表記揺れによるFK違反が BINARY レベルで完全に防止。) |
| 30 | X30: 反証探索 | 「最小不在時間30秒ルールにより、Officeの一時ファイルrename中の偽deleteは完全に抑止される」を、debounced debouncerが2回走る条件で試行。 | **主張を支持。** (30秒以内の複数walkは、pending状態（1回目absent）のまま留まり、deleteコミットを起こさない。) |
| 31 | X31: r10相互作用 | `submission_seq` 継承時の SELECT MAX。複数の新規 target_key が同一tickで同時にINSERTされる際の競合防止。 | **問題なし** (単一Tx内、および同一の MAX 参照（cost_ledgerは書き込みのみ、PK重複はON CONFLICTで回避）により競合が発生しない。) |
| 32 | X32: fork状態機械 | ID_WRITTEN中クラッシュ後に、フォルダ全体が外部ボリュームへ移動。マイグレーション後の再発見walkが新パスで journal を発見し、手順3から回復。 | **問題なし** (was_trackedと新realpathを用いて INSERT OR REPLACE が完璧に実行。) |
| 33 | X33: 記帳網羅行列 | (server / client) × (通常成功 / FAILED / timeout / result_expired) などの全セルに対して記帳行数（一意なseq）を検証。 | **問題なし** (すべての終了ステータスで、attemptsと連動しない一意な seq が台帳に1行ずつ正確に記帳。) |
| 34 | X34: 検索の完全形 | 3文字未満（日本語2文字）の LIKE fallback。text と heading_path の両方を対象とし、`instr(lower, lower)` を第1ソート、`chunk_uid` を第2ソートとしてLIMITで切り捨て。 | **問題なし** (一意な順位が決定論的に維持され、RRF融合時の結果揺れを完全に排除。) |
| 35 | X35: 反証探索 | 「attempts継承防止：旧profile行（state=2）がattemptsを引き継がず、新profileの初回で attempts=0 から数え直される」を試行。 | **主張を支持。** (相1の「profile不一致はstateを問わずattempts=0リセット」により、新profile最初の失敗で即terminalに倒れるバグを防止。) |
| 36 | X36: r11相互作用 | profile A→B→A と戻して、collectの `profile_changed` 記帳（seq=n）と、reconcile closeの記帳（同seq=n）が競合。 | **問題なし** (`ON CONFLICT (..., submission_seq) DO NOTHING` により、衝突を「二重観測」として吸収し、Tx abortによる無限滞留を回避。) |
| 37 | X37: ready完了追跡 | synced_profile_hash の状態。一部フォルダが一時EIOで開けない間、母数から除外され、残るフォルダでreadyが立つか検証。 | **問題なし** (一時読取不能は母数から除外され、健全なフォルダのみで ready P2 が安全に成立し、横断検索の健全性を維持。) |
| 38 | X38: fork回復拡張 | HISTORY_CLEARED 中、old_idで新規コミットが積まれてしまった不整合フォルダを回復。 | **問題なし** (commits非空要件に基づき、手順1の全削除（CASCADE）から冪等に再開され、fsckによる commit 偽破損報告を回避。) |
| 39 | X39: 局所処理 | register時に存在を検出したが、他プロセスがメタデータを一時排他ロック（EIO）。 | **問題なし** (一時読取不能として保留され、誤って破壊的な再初期化（damaged）へ倒れない fail-closed 設計を確認。) |
| 40 | X40: 反証探索 | 「query_profile_hashの固定により、クエリ生成〜KNN実行の極小窓におけるprofile変更TOCTOUは完全に防止される」を試行。 | **主張を支持。** (固定されたhashとagg_ready_profile_hashがKNN直前の同一 read Tx 内で不一致と判定され、安全にFTSのみに縮退。) |
| 41 | X41: 記帳済み判別 | 期限超 confirmed-absent が発生し、(i) 述語 (ii) 記帳 (iii) attempts+1 (iv) 載せ直し相1 が同一Txで実行される様子を検証。 | **問題なし** (述語による「既に当該 token で記帳済みか」の判別により、同一 attempt の推定行が重複して増殖するバグを100%防止。) |
| 42 | X42: ready母数 | readyの母数が一時EIO・missing等で動的に変動。接続フォルダ0件の間は ready 更新が防がれる。 | **問題なし** (空虚な真（0件フォルダによるreadyの誤設定）が構造的に阻止され、横断検索の不整合を回避。) |
| 43 | X43: 論理名逆解決 | in-place restore時に、衝突実体（Report.pdf と report.pdf が collision）の raw 物理名へ逆解決する挙動を評価。 | **問題なし** (walkと同一の採用規則（物理名UTF-8バイト昇順の先頭）に基づき、rawエントリを特定し、上書き衝突を防止。) |
| 44 | X44: 読取照合 | standaloneな読み取り専用検索。folders未登録の持ち込みフォルダに対して、repository-id を結果の provenance として表示。 | **問題なし** (自己完結の思想に基づき、誤った folders 照合を bypass して正常に検索結果と証明書を返却。) |
| 45 | X45: 反証探索 | 「step -1 の後退検出zは、復元直後の最初のtickにおけるメタデータ巻き戻り誤課金を事後ではなく事前に完全に遮断する」を試行。 | **主張を支持。** (step-1が冒頭でz（ regressed / unreadable）を検出し、その tick の step0〜4（submit含む）から当該 repo を完全に除外するため誤課金が起きない。) |
| 46 | X46: 述語キー | (b') 記帳後に、残骸掃除がクラッシュし、次tickで token sweep 前段が再処理される際の記帳済み判別（述語）。 | **問題なし** (同じ seq で「同キー × batch_job_id = 発見 job id」の既存 ledger が確認され、重複記帳（推定行の増殖）を完璧に抑止。) |
| 47 | X47: 期限超同一Tx | 期限超 confirmed-absent の (i) 述語 〜 (iv) 相1 載せ直し を 1 Tx で実行中にクラッシュ。 | **問題なし** (Txの原子性により、中途半端な attempts 消費や、載せ直し未了で記帳だけが残留して二重計上されるデッドロックを完全に回避。) |
| 48 | X48: restore保全 | workingツリーが編集中のファイルに対して restore。安定確認が走り、現内容をLWWとの不一致として先にコミット。 | **問題なし** (未取り込みのworking内容が、restore上書きによって不可逆的に消滅する最悪バグを完璧に防止。) |
| 49 | X49: 回復先行 | 破損 journal（digest不整合）が存在する状態で unregister を要求。 | **問題なし** (回復先行ゲートが破損を damaged として停止。唯一の例外である「明示解決」手順が journal を除去し、安全な再登録へ誘導。) |
| 50 | X50: 反証探索 | 「無 id 記帳は NOT NULL 制約と衝突せず、常に一意に台帳へ永続化される」を試行。 | **主張を支持。** (値の規則に基づき、未追跡/未確定の attempt は intent_token を batch_job_id に格納することで NOT NULL を安全に満たす。) |
| 51 | X51: seq行UPDATE | 期限超 (ii) での seq +1 行 UPDATE から、(iv) 相1、さらに 相3 完了へのライフサイクルを追跡。 | **問題なし** (期限超 (ii) の UPDATE により、同じ attempt 内の連番 seq が一貫して1回だけ前進し、正規の close 記帳時の一意制約衝突を防止。) |
| 52 | X52: expired出口 | attempts >= 上限により expired terminal（state=3）へ遷移。 | **問題なし** (相1 rotation が無条件に載せ直すのを (iii') 規則が阻止。attempts上限が機能し、不要な課金を完全に抑止。) |
| 53 | X53: 対称性検査 | 4つの照合点（intent回復、detached(b)、(b')、sweep）における「三値・期限・skew・猶予・述語・行UPDATE・job_id・後続」の8要素を網羅マトリクスで検査。 | **問題なし** (すべての照合点において、同一の時刻判定（10分伝播猶予等）および記帳・行UPDATE規則が一意に貫かれていることを確認。) |
| 54 | X54: 破損journal | 破損 journal からの damaged 復旧（明示解決）手順。 | **問題なし** (破損 journal のみを先に除去し、 flag を残したまま新規 id で再登録。途中クラッシュでも flag が (a) 規則で回収され、安全に収束。) |
| 55 | X55: 単独検索規則 | embeddings 混在（KNN停止・FTSのみ）中に、最新 generated_at の最新 tool_profile を決定。同時刻 tie の tool_profile_hash バイト昇順タイブレーク。 | **問題なし** (tie-breakおよび「最後に触れられた世代」の近似決定規則が一意に機能し、検索が恒久停止するバグを根治。) |
| 56 | X56: 往復可逆性 | §6 結合後の本文エスケープ (0+ `\` + grammar) と §7 の un-escape (1+ `\` + grammar) の往復をシミュレート。 | **問題なし** (本文内の `\![diagram](obj:...)` も、緩いパターン一致 un-escape によって `\` が残留せず完全可逆に原文へ回復。) |
| 57 | **X57: 自己記述化** | **R06の自己記述化（terminal行への batch_job_id 書込）が、(a) state=0 の client 判定に悪影響を与えないかを評価。** | **問題なし** (自己記述化は close / terminal 化した行のみに走り、state=0 の active な判定は state=0 を対象にするため衝突しない。) |
| 58 | **X58: detached** | **error='detached' / 'expired' の terminal 行が、再登録されて attached に戻った際の遷移をトレース。** | **問題なし** (attached 復帰後、成果なし・state=2 投入対象として、attempts=0 数え直しに基づき安全かつ速やかに再投入が始動。) |
| 59 | **X59: 拒否と sweep** | **`submit_rejected` 行について、sweep 前段の除外が、拒否にも課金する provider と交錯した際の挙動を検査。** | **問題なし** (送信中断は未作成確定として扱い、実プロバイダ前提の注記に従って、課金がある場合は記帳を足す拡張手順への分岐が成立。) |
| 60 | **X60: decoder** | **escape × un-escape × 認識の 3 述語に、`\![diagram](obj:see appendix)` などの非 canonical や object 不在の全組合せを往復。** | **問題なし** (緩いパターン一致 un-escape により `\` 累積を100%排除。実在検証による phantom チャンクの二重防止と、text_hash 安定化を同時達成。) |
| 61 | **X61: 伝播猶予** | **「遅延上限 ≤ 伝播猶予」の契約が Mistral Batch で成立するか、およびR15更新版主張の総当り反証。** | **主張をすべて支持。** (10分の猶予設定により read-after-write 整合性の不整合を完全に覆い、二重記帳、偽 expired などを全て無効化。) |

---

## 第 3 部 — 新規検出 (S01〜)

本監査における詳細な検証、およびX57〜X61（r15修正の相互作用・変更点）と R01〜R29（回帰・転記漏れ再発防止）を対象とした総当り攻撃・探索の結果、設計の論理的な閉包が達成されており、**新規のデータ破壊、不整合、または課金事故を招くバグ（fatal / major）は 0 件**でした。

---

## 第 4 部 — 確認済みの列挙

### 1. 確認済みの検査観点 (C1〜C12)
- **C1. 原則反映**: P1〜P16の全項目が欠落なく、強固な規範として設計書に反映されていることを確認しました。
- **C2. SQL静的検証**: すべての DDL（GENERATED列、WITHOUT ROWIDとPKの関係、FTS5 external contentにおける `chunks` 表の rowid pk 保有、FK参照、FTS5の `chunks_fts_src` ビュー接続）に SQLite 文法上の問題がないことを検証しました。
- **C3. 相互参照整合**: 本文中のすべての `§` 参照および内部の設計規約参照が正しく存在し、意味的に整合していることを確認しました。
- **C4. クエリとスキーマの整合**: `selected_files` や RRF、FTS5、差集合の全 SQL クエリが、定義された DDL スキーマおよびバインド変数と完全に合致していることを確認しました。
- **C5. 数値・事実の一貫性**: コスト（$2.5/1k、+25%）、次元数、RRF k=60、テーブル数（8テーブル）などの定数が、文書内のすべての言及箇所で一貫していることを確認しました。
- **C6. 用語・形式の一貫性**: `target_key` などの連結形式、`obj:<image_hash64>`、`embed_hash` 等の表記規則が全章で統一されていることを確認しました。
- **C7. 状態機械の完全性**: 2相submit、intent回復、および detached 状態の各終了ステータスへの遷移が、クラッシュ耐性を含めて矛盾なく一意に収束することを確認しました。
- **C8. 欠落**: フォルダ単位バージョン管理と AI 検索（Mistral Batch OCR / ベクトル統合）に要求される必須規範に、記述の欠落がないことを確認しました。
- **C11. 合理性 (実装・実行可能性)**: 実装者が追加の設計判断を挟むことなく、コードを完全に実装可能なレベルまで失敗処理や分岐が具体化されていることを確認しました。
- **C12. 探索型監査**: 新設された仕様（R01〜R29、および自己記述化等のr15変更点）に対する攻撃シナリオを漏れなく机上実行し、安全性に問題がないことを検証しました。

### 2. 確認済みの設計原則 (P1〜P16)
- **P1. 三層構成 / P2. 識別子規範 / P3. metadata.sqlite 8表 / P4. chunks統一 / P5. チャンク分割 / P6. OCR (Mistral Batch) / P7. FTS (External Content) / P8. Embedding (Multimodal) / P9. バッチ管理 (app.sqlite) / P10. 書込順序と冪等性 / P11. 集約 (同期・後退検出) / P12. 検索 (RRF・3モード) / P13. GC (3本和集合・fsck) / P14. SQLite設定 (PRAGMA・DACL) / P15. 元設計継承 / P16. 変更検知 (3段ドリルダウン・NFC論理名・raw逆解決)** のすべてについて、「確認済み・問題なし」であることを宣言します。
