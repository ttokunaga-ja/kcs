```
読了行数: 1732
最終2行:
```
(行1731) ```
(行1732) ※空行(末尾改行のみ)
```
判定: 条件付き合格
```

---

### R24-glm-1 [major] `estimate_embedding_cost` の二重ネスト定義 — コンパイル不能
- 対象箇所: §4 lines 1159-1164
- 根拠: 外側の `fn estimate_embedding_cost(...) -> f64 {` の本体が `// (estimate_embedding_cost 本体)` というコメントと、**内側に同名のネスト fn** のみで終わっている。ネスト fn 宣言は文であり tail 式ではないため、外側の関数は `f64` を返さず Rust ではコンパイルエラー(E0308 系)になる。`estimate_embedding_cost` は §3 の Batch 予約額 (line 768) と sync 記帳の正本であり、これが壊れると課金の見積り=確定記帳が全滅する(§0「見積りがそのまま確定記帳になる」)。
- 再現手順: 記載どおりにビルドする。または当該関数を呼ぶ経路(`submit_embedding_batch_jobs`)のコンパイル。
- 影響: リテラルどおりなら実装全体がビルド不可。転記アーティファクトであっても「本体」が欠落しており監査不能な点は重大。
- 提案: ネスト fn を削除し、外側の fn 本体を `estimate_embedding_tokens(text) * embedding_usd_per_token(lane)` の単一式にする。

### R24-glm-2 [major] 失敗ジョブの無バックオフ再投入 (KNOWN GAP) — 課金の無限増幅
- 対象箇所: §3 `poll_batch_embedding_jobs` lines 920-943 + §8 `known_gap_a_failed_job_is_resubmitted_within_the_same_pass` lines 1574-1617
- 根拠: 非成功終端のジョブは `settle_batch_charge_terminal(Outcome::Expired, estimated_usd)` で一旦決済されるが、メンバ task は一度も Failed 遷移されない(line 1580「member tasks are never marked failed」)。同一 `batch resume` パス内で enrichment が再駆動され、同じメンバ集合で**新しい reservation + 新しい job** が作られる(テストは `creates == 2` を pin)。`markdownize` レーンが持つ `next_retry_at`/attempts 上限を embedding Batch は利用しないため、失敗が持続すると `batch resume` ごとに見積額相当が課金され続ける。監査観点4(無限ループ・リソース枯渇)の直撃。
- 再現手順: スクリプトが `BATCH_STATE_FAILED` を返す状態で `index --online` → `batch resume` を繰り返す。毎パス `cost_ledger` の `expired` 行が増殖する。
- 影響: 持続的失敗で課金が無界に増幅。各回は「失敗 job の見積額」(provider が部分課金した場合は過大記帳) が確定記帳される。
- 提案: 失敗終端でメンバ task を retryable-failed に遷移させ、`next_retry_at` を介したバックオフまたは `attempts` 上限を embedding Batch にも適用する。KNOWN GAP はテストで固定されているだけで是正が必要。

### R24-glm-3 [major] `--yes` が prune-orphans 確認で効かないデッドロジック
- 対象箇所: §7 lines 1299-1303
- 根拠: `if let RepairOperation::RebuildDb(rebuild) = &args.operation {` の内側で `skip_prompt = matches!(&args.operation, RepairOperation::VerifyObjects(verify) if verify.yes)` を計算している。この arm に入った時点で `args.operation` は `RebuildDb` なので `matches!` は**常に false** になる。結果として `--yes` が指定されても `confirm_repair_prune(..., skip_prompt)` の第3引数は常に `false` になり、非対話実行で `KIO-E-CONFIRM-REJECTED-001` になるか対話プロンプトが出る。監査観点6(H2 非対話挙動)の違反。加えて `prune_orphans` 呼び出し自体が `RebuildDb` 配下に置かれておりスコープ不一致。
- 再現手順: `kio repair verify-objects --prune-orphans --yes` を非対話で実行(この excerpt の分岐経路)。
- 影響: `--yes` が効かず、自動化パイプラインが確認拒否で停止する。
- 提案: `skip_prompt` の導出を正しい `VerifyObjects` arm 配下に移動するか、`args.operation` ではなく当該 arm の変数で判定する。

### R24-glm-4 [major] 結果行数の検査欠如 — プロバイダ一部省時の無言データ欠落
- 対象箇所: §3 `poll_batch_embedding_jobs` lines 945-985 + §2 `parse_inlined_results` lines 454-514
- 根拠: `fetch_inlined_results` は `inlinedResponses[]` の要素数をそのまま信じて iterate し、行の欠落(提出した N 件に対し M<N 件しか返さない場合)を検出しない。`metadata.key` 欠落は ContractViolation になるが、「行そのものが無い」場合は無警告でスキップされる。その後 `settle_batch_charge_terminal(Outcome::Succeeded, ...)` で行は完了確定し intent_token も NULL 化されるため、結果が来なかったメンバは二度とこの行から再収集されず、ベクタ未書き込みのまま恒久 Pending に滞留する(失敗扱いでもないため R24-glm-2 の再投入経路にも乗らない可能性がある)。
- 再現手順: 512 件提出に対しプロバイダが 511 件のみ返す mock。`batch resume` で行は完了、欠けた1チャンクはベクタ未登録のまま `index_status` に残り続ける。
- 影響: サイレントな埋め込み欠落(検索再現性の劣化)。監査観点3「結果の取りこぼし」。
- 提案: `results.len()` を提出時のメンバ数(または `row` から復元したメンバ数)と比較し、不一致は Succeeded ではなく Failed/Partial 扱いで settle するか、未到達メンバを明示的に failed 遷移させる。

### R24-glm-5 [minor] `active_embedding_send_lane` のコメントが実態と矛盾
- 対象箇所: §4 lines 1087-1098
- 根拠: コメントは「embedding Batch driver (submit + poll/collect) is still to land」と書くが、§3・§5 に `submit_embedding_batch_jobs`/`poll_batch_embedding_jobs` は既に存在する。関数は常に `Sync` を返すが、その理由説明が現状と逆。監査観点5(レーン規約)の読み手を誤導する。
- 提案: コメントを「enrichment sync フォールバック経路は常に Sync 単価」と実態に合わせて更新する。

### R24-glm-6 [minor] §3 ヘッダコメントの重複
- 対象箇所: §3 lines 616-625
- 根拠: lines 616-620 と 621-625 がほぼ同一内容で複製されている(コピペ残渣)。可読性・保守性の低下。
- 提案: 重複を削除。

### R24-glm-7 [minor] dry-run と本実行の TOCTOU 窓
- 対象箇所: §7 lines 1293-1296 (`registry_prune(true)`→確認→`registry_prune(false)`) および lines 1304-1316 (`prune_orphans(true)`→確認→`prune_orphans(false)`)
- 根拠: preview と本実行が別呼び出しで、間に確認プロンプトや他の処理が入る。表示件数と実削除件数がずれ得る。監査観点6「dry-run と本実行の結果がずれる窓」。
- 影響: ユーザーが承諾した件数より多く/少なく削除される可能性。対象は orphan のため参照整合性は壊さないが、確認の意味が薄れる。
- 提案: preview で取得した対象 ID を本実行に引き渡して同一集合を削除するか、件数ずれを結果に明示する。

### R24-glm-8 [minor] realtime 単価(2倍)のテスト欠落
- 対象箇所: §8 `realtime_uses_the_synchronous_lane_and_never_creates_a_batch_row` lines 1668-1700
- 根拠: `request_kind='sync'` になることのみ検証し、**sync 単価($0.20 = Batch の2倍)で記帳されたこと**を検証しない。§0「倍額は明示 opt-in でしか発生しない」の金額側がテストで守られていない。`estimate_embedding_cost`/`embedding_usd_per_token` が正しいレーン単価を選ぶかが無防備。
- 提案: `cost_ledger` の金額(または `estimated_usd`)が sync レートであることを assert する。

### R24-glm-9 [minor] Real client impl の truncation
- 対象箇所: §2 lines 611-612
- 根拠: `EnvGeminiBatchClient::create_embedding_job` の本体が `read_json_bounded(` で途切れており、`create_embedding_job`/`get_job`/`list_jobs`/`fetch_inlined_results` の実装が示されない。禁止事項に従い「不明」として扱い fatal にはしないが、実装の要である HTTP 呼び出し経路が監査対象から欠落している点を記録。
- 提案: 実ソースで該当実装の境界・エラー処理・retry 姿勢を別途確認する。

---

### 確認したが問題なしと判断した点
1. **intent_token の NULL 化(成功/失敗両終端)**: `settle_batch_charge_terminal` の第10引数 `clear_intent_token` が success(line 1000)/failed(line 940) とも `true` で渡されており、§0「inline レーンは終端=掃除完了」の裁定どおり。テスト(line 1500-1507)が `state=2, intent_token IS NULL` を pin している。残骸掃除のない inline の特性に合致。
2. **1 job = 1 task の再利用冪等性**: 同一メンバ集合の再投入は `get_batch_request(...).batch_job_id` 既存で `continue`(lines 803-811)し、2 job 目を作らない。テスト `resubmitting_the_same_member_set_...`(line 1706)が `creates == 1, row count == 1` を pin。
3. **インライン上限の二重防壁**: `MAX_INLINE_REQUESTS=2048`(line 212) + `MAX_INLINE_REQUEST_BYTES=16MiB`(line 208) を `inline_embed_batch_body` で事前検査し、加えて `EMBEDDING_BATCH_JOB_MAX_MEMBERS=512`(line 641) でチャンク化。過大入力は provider 往復前に局所拒否される。監査観点4(リソース枯渇)のインライン側は確保されている。
4. **正規化の二重検査**: `validate_cosine_vector` → L2 正規化 → 再 `validate_cosine_vector`(lines 666-683)。ゼロベクトルは第1検査で弾かれ `norm==0` の除算に至らない。オーバーフロー/アンダーフロー後のベクタも再検査で拒否される。§0 (1)-(5) に合致。
5. **Running 中ジョブのポール冪等性**: state 1 行は `is_terminal()==false` で `inflight += 1` のみで settle せず、課金・状態遷移とも無変化。テスト(line 1641-1661)が反復 poll で row count・token 保持とも不変を pin。二重課金なし。
