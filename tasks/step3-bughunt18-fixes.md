# 探索型監査 第18ラウンド (R18) 裁定

- 実施日: 2026-07-08、対象 HEAD: 13208ca (テスト全 green 468・clippy --all-features/fmt clean を起点確認済み)
- エンジン: Claude-Opus / Claude-Sonnet-A / Claude-Sonnet-B / Claude-Sonnet-C / Claude-Sonnet-D /
  GPT-5.5 (read-only 静的) / GPT-5.3-Codex-Spark (範囲限定: R17 fix の新配線が開ける穴 + cost-ledger reclaim 会計残余)
- 結果: **新規 2 major + 2 minor (R18-1〜R18-4)**。却下 3 (Sonnet-B scalar overwrite / Spark lock 非対称 / Opus resolve_commit 誤誘導)、据え置き 1 (month 月跨ぎ)
- ラウンドの骨格: R18 焦点の「R17 fix が開ける穴」(定番脈 **8 例目**) が本命的中。R17-3 が新設した reclaim ledger が
  **「rate_limit/quota で失敗した online task の F8 予約は、その仕事が意味を失った (chunk 非 live 化 / ファイル削除) 時点で
  reclaim されるべき」という原則を、退役経路の一部にしか配線していない**という同型欠陥が 2 つの pipeline で露出した。
  (a) **本命 = embedding 経路に reclaim 機構が構造的に皆無** (R18-1) に **6 エンジン独立収束** (GPT-5.5 + Spark + Sonnet-A/B/C/D、
  Opus 以外全員。R16-1/R17-1 に匹敵する強収束)。embedding task は `reserved_usd`/`reserved_month` を一度も stamp せず
  (markdownize だけが stamp)、`reconcile_committed_embedding_tasks` は非 live task を Pending/Running のみ終端化し
  Failed(rate_limit) を素通しするため、rate_limit 1 回 + 編集 1 回という日常操作だけで embedding cap が phantom に恒久汚染され、
  無関係な将来ドキュメントの正当な埋め込みが budget_exceeded で誤 Paused される。**しかも batch retry は embedding を
  非 retryable 化して回収不能を確定させ markdownize より悪い** (Sonnet-B/C)。R15-7 の前提「非 live embedding は再課金されない=
  実害なし」を R16-7/R17-3 の「予約自体が cap を圧迫する」が覆した「別ラウンドの概念導入が既存 fix の前提を覆す」型。
  (b) **markdownize reclaim は「編集 (同一 path 再スキャン)」経路のみ・「削除/rename/precondition-failure」を見落とす** (R18-2、
  GPT-5.5 + Sonnet-C)。R17-3 の retire+reclaim は `enqueue_online_placeholder_task` 内で `task.input_path == candidate.input_path`
  前提のため、削除/rename されたパスは二度とスキャン候補に現れず reclaim 不発。batch retry の precondition 退役 (5862) も
  reserved_* を clear も reclaim もしない。R17-3 fix 前と同じ症状 (phantom が per-adapter cap 枯渇→正規タスク誤 Pause) が削除経路で生存。
  (c) **R17-3 が reclaim ledger を執行ゲートには netting したが status/warning の報告 3 面に配線し忘れ** (R18-3、GPT-5.5 + Opus)。
  (d) **R17-4 の store 破損クラス回復ガイダンスが「全 scope 除外」時のみで partial exclusion で欠落** (R18-4、Sonnet-A)。
- 全 major はオーケストレータが control 付き実機 repro で独立再確認済み (G2/G1 とも phantom scope=誤 Paused / control scope=成功)。

---

## R18-1 [major] embedding 経路に R17-3 相当の phantom reclaim 機構が構造的に皆無 — rate_limit/quota で失敗した embedding task の F8 予約は、chunk が編集/削除で非 live 化しても reclaim されず、embedding per-adapter/device cap を当月ずっと phantom で圧迫し、無関係な将来ドキュメントの正当な埋め込みを budget_exceeded で誤 Paused する

**収束**: GPT-5.5 (静的) / Spark 検証2(c) (静的) / Sonnet-A (実機) / Sonnet-B (実機) / Sonnet-C (実機) / Sonnet-D (実機 control/phantom DoS)
の **6 エンジン独立収束** (Opus 以外の全エンジン)。ランブックの R18 焦点 (cost-ledger reclaim 会計残余・Spark 検証2c) が
名指しした脈に本命的中。**Opus は reclaim「する」経路の cap-safe 不変条件だけを確認し reclaim「しない」退役経路 (embedding 全体) を未探索**
(「fail-open 経路なし」は正しいが phantom 保持による false-pause を見落とし)。

**根本原因**: embedding の F8 charge は送信前に `cost_ledger` へ実 charge 行を append する (`crates/kio-cli/src/main.rs:7170`
付近、`charge_cost_ledger_under_lock` / `EMBEDDING_ADAPTER_KIND`) が、markdownize (`main.rs:5989-5998`) と違い
task に `reserved_usd`/`reserved_month` を一切 stamp しない (`EmbeddingTransition` に予約フィールドがなく `apply_embedding_transitions`
[`main.rs:7278-7305`] は status/fallback_reason/attempts/next_retry_at のみ書戻し、`TaskDescriptor` 既定は `reserved_*: None`
[`main.rs:7670-7671`, `:7722-7723`])。R16-7 の `reservation_covers_resend` (`main.rs:7087-7099`) は「rate_limit/quota の予約は
resend を被覆する」として再課金を skip するので予約の存在は認識しているが、**retire 側 (reclaim) が未実装**。非 live 化した
embedding task を終端化する唯一の関数 `reconcile_committed_embedding_tasks` (`main.rs:7549-7596`) は `main.rs:7567`
`if !matches!(task.status, TaskStatus::Pending | TaskStatus::Running) { continue; }` で **Failed を無条件 skip** し、
`reclaim_ledger()` の write 呼出は markdownize 側 (`main.rs:9135-9139`) の 1 箇所のみ。結果、Failed(rate_limit) の phantom charge が
`cost-ledger.jsonl` に当月ずっと残り、`budget_remaining_for_adapter` の embedding spend を食う。**しかも `batch retry` は
retryable Failed を Pending に戻す→次パスの reconcile が `main.rs:7584-7590` で即 Failed(invalid_input) 非 retryable に終端化する
(cost-ledger 不変) ため、retry がむしろ回収不能を確定させ markdownize (R18-2) より悪い**。

**実機 (オーケストレータ独立再現・control 付き)**: `XDG_DATA_HOME`/`HOME` を都度 `mktemp -d` で隔離、scope は /tmp 配下。
seam は init 時にも `KIO_TEST_GEMINI_EMBED` を設定 (embedding tool-lock 具現化に必要)。
- phantom scope: `KIO_TEST_GEMINI_EMBED=rate_limit index --approve --yes --online` → embedding task
  `status=failed reason=rate_limit reserved_usd=None` + `cost-ledger.jsonl` に `{"adapter_kind":"embedding","usd":0.000135225}`。
  文書編集 (新 chunk) + `[budget.per_adapter] embedding=0.000214` (1 doc コストの 1.5×=phantom+legit 未満) 設定 → `mock` 再 index →
  **`paused_tasks:1` (executed 0)、新 embedding task `paused budget_exceeded`**。旧 Failed(rate_limit) は放置・`cost-ledger-reclaimed.jsonl`
  は生成されず。`batch retry`/`batch resume` を追加しても phantom 不変・回収不能。
- control scope (fresh・同一 V2 内容・同一 cap・phantom なし): `mock` index → **`embedding_tasks_executed:1 paused_tasks:0`** で成功。
唯一の差は過去の rate_limit phantom の有無。

**契約**: R16-7「rate_limit/quota は課金され得ない」+ R17-3「非課金予約は reclaim され正規タスクを誤 Pause しない」が
embedding 経路に及ぶべき (R17-3 fix方針が「embedding charge 経路の同型も同時に確認する」と明記) が未実装。

**fix 方針**: embedding にも markdownize R17-3 と同型の reclaim を配線する。(1) embedding 送信直前 (`main.rs:7170` 付近、
`apply_embedding_transitions` の Charged 分岐 or Running 遷移) で `reserved_usd`/`reserved_month` を stamp、(2)
`reconcile_committed_embedding_tasks` の非 live 分岐 (`main.rs:7584-7590`) を `Failed`(rate_limit/quota) にも拡張して
invalid_input 終端化 + 非課金種別なら `cost_ledger.reclaim_ledger()` へ reclaim。**NetworkError の予約は markdownize と同じく
reclaim しない** (サーバ課金の可能性・R15-5 cap bypass 防止)。reclaim は charge/reclaim/netting と同じ `repo.scope_id_for_adapter()`
scope_id・`reserved_month` (charge 月) で記帳し F3 (負値禁止) を継承。回帰テスト: rate_limit embedding→編集→再 index で
旧 task 退役 + reclaim 行 append + 新 task が phantom なしで実行 (control と一致)、NetworkError embedding では予約が保守的に残る (cap-safe) の
discriminator 2 本。

## R18-2 [major] markdownize の R17-3 reclaim は「編集 (同一 path の再スキャン)」経路のみをカバーし「削除 / rename / batch retry の precondition failure」を見落とす — 削除された旧 path の rate_limit phantom charge が恒久固着し、per-adapter markdown cap を枯渇させて無関係な正規タスクを誤 Paused する

**収束**: GPT-5.5 (静的・3 経路特定) + Sonnet-C (実機 control repro)。

**根本原因**: R17-3 の retire+reclaim (`main.rs:9091-9141`) は `enqueue_online_placeholder_task` 内にあり、今回のスキャンで
見つかった `ScanCandidate` ごとに `task.input_path == candidate.input_path` (`main.rs:9095`) で stale task を照合する。
ファイルを削除/rename すると旧 path は二度とスキャン候補に現れず、この retire+reclaim がそのパスに対して二度と発火しない。
`batch retry` で Pending に戻しても `online_markdownize_precondition_ok` (`main.rs:6249` 付近、削除ファイルの `fs::read` 失敗)
がガードし `Failed(invalid_input)` (`main.rs:5862-5882`) に落とすが、この分岐は `reserved_usd`/`reserved_month` を clear も
reclaim もしない。結果、R17-3 fix 前と同じ phantom-eats-cap→誤 Pause が削除/rename/precondition 経路で生存。

**実機 (オーケストレータ独立再現・control 付き)**:
- phantom scope: doc.pdf (20KB) を `KIO_TEST_MISTRAL_OCR=rate_limit index --online` + `batch resume` →
  `cost-ledger.jsonl` markdown usd=0.002・task `Failed(rate_limit) reserved_usd=0.002`。**`rm doc.pdf`** + doc2.pdf (4KB) 追加
  (削除、編集ではない) + `[budget.per_adapter] markdown=0.0012` (doc2 コスト 0.0004 < cap < phantom 0.002) → `mock` index+resume →
  **doc2.pdf が `paused budget_exceeded` (tasks_executed:0)**。削除された doc.pdf の Failed(rate_limit) phantom は放置・reclaim なし。
- control scope (doc2.pdf のみ・同一 cap・phantom なし): doc2.pdf `done`。
削除された旧ファイルの phantom が無関係な新ファイルを誤 Pause。

**契約**: R17-3 の裁定「stale task を reclaim して正規タスクを誤 Pause させない」を削除/rename 経路で破る。

**fix 方針**: `run_index` (または enrichment 駆動部) の末尾に、フレッシュな `ScanPreview.candidates` に存在しない `input_path` を持つ
Failed(retryable rate_limit/quota) markdownize task を一掃 (invalid_input 終端化 + 非課金なら reclaim) するスイープを追加し、
`enqueue_online_placeholder_task` 内の同一 path 限定 reclaim をスキャン候補外にも一般化する。併せて batch retry の
precondition 退役 (`main.rs:5862-5882`) でも、退役対象が rate_limit/quota で `reserved_*` を持つなら reclaim してから clear する
(退役 helper の共通化)。NetworkError は保守的に残す (R18-1 と同じ非対称)。回帰テスト: 削除された doc の rate_limit phantom が
再 index/batch resume 後に reclaim され、無関係な新 doc が phantom なしで実行 (control と一致)。

## R18-3 [minor] R17-3 が新設した reclaim ledger を執行ゲート (`budget_remaining_for_adapter`) には netting したが、`kio status` / index・batch の budget 報告 (`budget_status_json` / `scope_budget_warning`) には配線し忘れた — reclaim 後も gross charge で spent/remaining/warning を表示し、Agent が budget を過小 remaining で誤監視する

**収束**: GPT-5.5 + Opus。

**根本原因**: 執行ゲート `budget_remaining_for_adapter` (`main.rs:9250-9293`) は charge − reclaim の netting を行う
(`(monthly_total(...) - reclaim_ledger.monthly_total(...)).max(0.0)`)。しかし報告系は netting しない: `budget_status_json`
(`main.rs:7883-7888`、`kio status` の budget / index・repair の budget) と `scope_budget_warning` (`main.rs:7927-7932`、
index・batch の budget_warning) は `ledger.monthly_total` のみを読み、非 netted 値を `budget_warning` (`main.rs:7897`/`7933`) に渡す。
reclaim 済み phantom を spend に計上し続けて remaining を過小報告し、`warn_at_percent` も取消済み phantom で誤発火し得る。
執行は正しく netting するので exit/pause には影響せず **fail-safe (remaining を過小報告する側)** だが、R17-3 のユーザー/Agent 可視の
狙い (phantom が cap を食わない) が status 上で成立せず、Agent が `kio status` で budget を監視すると誤自制する。

**実機**: OCR rate_limit phantom → 編集 supersede reclaim (reclaim ledger に 1.5e-6 書かれる) 後も `kio status --json` の
`folder_spent_usd` が phantom 込みのまま変化しない (Opus 実機確認)。

**fix 方針**: `budget_status_json` / `scope_budget_warning` の spent を `budget_remaining_for_adapter` と同じ
`(monthly_total − reclaim_ledger.monthly_total).max(0.0)` に統一する (netting を共通ヘルパーに切り出し、執行と報告の 3 面を
一括で net)。回帰テスト: reclaim 後の `status` budget が effective spend (charge − reclaim) を反映し warn が phantom で誤発火しない。

## R18-4 [minor] R17-4 の store 破損クラス (`store_corrupt` / `snapshot_shallow`) 回復ガイダンスが「全 scope 除外」時にしか付与されず、multi-scope search で一部 scope だけが除外される (実運用でより一般的な) partial failure では bare な `reason` のみで `recovery` が一切出ない

**発見**: Sonnet-A (実機 2-scope repro)。R17-4 (store 破損クラス全 scope 除外の回復ガイダンス) の適用範囲が狭かった縫い目。

**根本原因**: `Excluded(reason)` の per-scope push (`main.rs:1369-1373`) と Fatal→`store_corrupt` downgrade push
(`main.rs:1385-1389`) はいずれも `{scope_id, scope_path, reason}` のみで `recovery` を持たない。R17-4 の回復ガイダンス組立は
`if searched.is_empty()` (`main.rs:1397`、全 scope 失敗) ブロックの内側にしかなく、1 scope でも成功していればスキップされる。
既存テスト (`step3_p0_contract.rs` の R16-2/R17-4 系) も全 scope 失敗ケースしか `recovery` を検証していない。

**実機**: 2 scope (A 健全 + B の HEAD commit object をバイト改ざん→store_corrupt)、A から `search --all-scopes --json` →
exit 3・`excluded_scopes:[{"reason":"store_corrupt",...}]` だが `recovery` キーはレスポンスのどこにもなし。全 scope corrupt の
構成 (R17-4 テストが検証する) でだけ `context.recovery` が付く。

**fix 方針**: R17-4 の reason→recovery 文字列組立を小さなヘルパーに切り出し、`main.rs:1369-1373` と `1385-1389` の各
`excluded_scopes` entry push 時点で該当 entry に同じ `recovery` 文字列を直接埋め込む (全滅集約ブロックだけでなく個々の除外 entry にも
適用)。**新エラーコードは導入しない** (R17-4 の教訓・docs 凍結下)。回帰テスト: partial exclusion (健全 scope あり) でも
excluded の store 破損クラス entry に recovery が付く。

---

## 却下・据え置き

- **却下 (Sonnet-B R18-1: markdownize `reserved_*` スカラー上書きで混在 retry の旧予約が reclaim 対象外)**: Sonnet-B は
  RateLimit(C1 charge)→NetworkError(C1 再利用)→RateLimit(C2 charge・stamp を C2 上書き)→編集で reclaim が C2 のみになり C1 が
  orphan (charge 2 行 vs reclaim 1 行) と主張し実機 repro を提示。しかし **C1 は attempt2 の NetworkError 送信を
  `reservation_covers_resend` (`main.rs:7087`/`5905`) で被覆した予約**であり、R16-7 のコメント (`main.rs:5893-5900`) が明記する通り
  「NetworkError re-send はサーバ側課金の可能性がある (request can reach the backend before the socket drops) ため予約を保守的に残す。
  reserve-once は server-side-billed retries で実支出が予約 cap を超える R15-5 silent cap bypass を開く」。C1 を reclaim する
  Sonnet-B の fix は、まさに R16-7 が却下した「reserve once / 生涯 1 予約」であり cap bypass を開く。retained C1 は既存の
  NetworkError 保守 (R16-7 裁定) を混在経路で踏んだだけで **cap-safe (effective_spent ≥ real spend、fail-open せず)**。Sonnet-B は
  C1 を「純 RateLimit phantom」と誤解析。却下 (rationale は既にコードコメントに固定済み)。
- **却下 (Spark 検証2(a): reclaim append の lock 非対称)**: `charge_cost_ledger_under_lock` (`main.rs:9351`) は device-global
  `StoreLock` 下で charge を append するが、reclaim append (`main.rs:9135-9139`) は lock なし。Spark は「同時実行時に
  `budget_remaining_for_adapter` の評価と反映がズレる可能性」を確定問題としたが、**reclaim は必ず既存 phantom charge に遅れて
  append され (phantom は元の送信時に durable)、reclaim_total ≤ charge_total が常時成立するため effective_spent = charge − reclaim ≥ 0 で
  fail-open しない**。非ロック reclaim との torn read は「実際より多く残って見えない=保守側」にしか外れない。Sonnet-C/Sonnet-A/
  Sonnet-D/Opus が独立に「バグではなく安全側」と反証。R17 の Spark TOCTOU 却下と同型。却下。
- **却下 (Opus #2: `resolve_commit` [diff/tag] が never-existed commit を COMMIT-SHALLOW+「restore the object」と誤誘導)**:
  Opus は R17-1 が resolve_pointer で捏造 commit を EVIDENCE-POINTER-INVALID に分離したのと非対称に、`diff HEAD sha256:000…0` /
  `tag t sha256:000…0` が COMMIT-SHALLOW exit 1「restore the commit object」を返すと指摘 (Opus 自己評価: 低確度/borderline-deliberate)。
  **R17-5 は STORE-NOT-FOUND→COMMIT-SHALLOW 変換を意図的に行っており、「object が GC された真の shallow (hash リテラル経由)」と
  「never-existed hash」は read_commit レベルで区別不能** (両方 STORE-NOT-FOUND)。区別には ref/reflog walk が要り 1 行では済まず、
  Opus の「not_found に戻す」修正は真の shallow (hash リテラル経由) を not_found と誤報し R17-5 を退行させる。harm は誤誘導
  メッセージのみで integrity/security bypass はない (R17-1 とは別次元)。borderline-deliberate として却下 (据え置き扱い)。
- **据え置き (month の月跨ぎ誤記帳)**: `month` が pass 開始時に 1 回計算され (`main.rs:5826` markdownize / `main.rs:7034` embedding)、
  ループ内の全 charge/reclaim に使い回される (Spark 検証2(b) + Sonnet-D 再確認)。R17 で既に据え置き済み。charge 総額は正しく
  (二重/欠落なし)、月末開始の長時間 pass の翌月分が前月に逃げる有界・稀なケースに留まる。tasks.jsonl/cost-ledger 月跨ぎの
  据え置き群と同族の月次会計マターとして Step 4 gc/月次境界設計へ送る。reclaim も `reserved_month` (charge 月) で対称に記帳されるため
  reclaim が月跨ぎを複合的に悪化させることはない (Sonnet-D/Sonnet-B 確認)。
- **参考 (非所見・健全確認)**: R17 fix の本体は 7 エンジンの静的+実機で健全確認 — R17-1 の best-effort 分離 (真の shallow
  [commit 実在・tree GC] の view/open degrade は継続・status/log/search は resolve_pointer を経由せず厳格化に巻き込まれない・
  EVIDENCE-POINTER-INVALID は tombstone/retarget と衝突せず [purge は Step4 未実装で tombstone write 経路が現状到達不能])、
  R17-2 の reindex skip-continue (前世代 gen 維持・copy 失敗ロールバック・JOIN 3 軸 gen 厳密一致で古 gen 検索混入なし・
  merge_reindex_skips の raw_hash dedup)、R17-3 reclaim 会計 (二重 reclaim 防止・NetworkError 非 reclaim・month=charge month・
  F3 継承・.max(0.0) clamp)、R17-6 searchable/stale の (raw_hash, gen) 突合、Tier B secrets-approved の scope_id 束縛。
  時刻/TZ は Howard Hinnant civil 算法で UTC 一貫・ログ日次ローテの retention 境界に off-by-one なし (Opus)。

## エンジン別スコア (参考)

- **Sonnet-A/B/C/D + GPT-5.5 + Spark**: R18-1 (embedding orphan) に 6 エンジン独立収束 (R16-1/R17-1 級)。Sonnet-C/D は
  control/phantom DoS を決定的に実機再現、Sonnet-B は「R15-7 前提を R16-7/R17-3 が覆す」framing、Sonnet-C は「batch retry が
  embedding を非 retryable 化して悪化」を特定。GPT-5.5/Spark は静的で reclaim ledger の markdownize 限定を立証。
- **GPT-5.5**: R18-1/R18-2/R18-3 の 3 脈すべてを静的で先取り (reclaim の path-scoped 限界 + embedding 皆無 + status 非 netting)。
  read-only 制約で実機はできないが file:line で全立証。今ラウンド最多スコープ。
- **Sonnet-C**: R18-1 + R18-2 の両方を control 付き実機 repro。reclaim 発火条件の「状況の一部にしか及ばない」同型欠陥として統合。
- **Sonnet-A**: R18-1 実機 + R18-2(store_corrupt partial-exclusion=R18-4) を別脈で。R9-1 パターン (焦点外からフルスコープ major)。
- **Opus**: R18-3 (status 非 netting) を実機フルサイクルで確定 + resolve_commit 誤誘導 (却下)。ただし R18-1/R18-2 (reclaim しない
  退役経路) を未探索し「reclaim 会計 cap-safe・fail-open なし」で健全側に振れた (phantom 保持の false-pause 見落とし)。
  R17 の resolve_pointer に続く「reclaim する経路だけ見て reclaim しない経路を見落とす」型。
- **Spark**: 範囲限定焦点 (R17 fix 新配線 + cost-ledger reclaim 残余) で検証1 (R17-1/R17-2/R17-3 double-reclaim/effective_spent) は
  全「該当なし」の健全確認、検証2(c) で embedding orphan (R18-1) の骨格を静的立証。lock 非対称 (検証2a) は却下、month (検証2b) は据え置き。
  R14/R16 型の「健全確認 + 1 骨格」着地でフルスコープと噛み合い。
