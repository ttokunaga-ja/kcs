読了行数: 1732
最終2行: }\n```
判定: 不合格

### R24-terra1-001 [fatal] 宣言済み単価ではレーン差額が失われる
- 対象箇所: §4 `embedding_usd_per_token`
- 根拠: `registered_declared_pricing("embedding").get("tokens_in")` があれば、引数 `lane` を見ず同じ単価を返す。Batch と realtime は異なる単価で記帳すべき規範に反する。
- 再現手順: `tokens_in` を sync 単価で宣言し、既定 Batch で index を実行する。
- 影響: 予約額・確定額・budget cap が誤る。
- 提案: 宣言単価をレーン別に保持し、必ず実際の送信レーンに対応する値を選ぶ。

### R24-terra1-002 [fatal] 予約見積りが実際に送る embedding 入力を含まない
- 対象箇所: §3 `submit_embedding_batch_jobs`
- 根拠: `candidate_usd` は `representative.text` を見積もる一方、送信する `inputs[].text` は `contextualized_embedding_input(context, ...)` である。usage が無いため、この差分はそのまま過少記帳となる。
- 再現手順: 長い document context を持つ chunk を Batch 送信する。
- 影響: 実支出より少ない額で予約・確定され、cap を超過できる。
- 提案: 実際に組み立てた `inputs[].text` を使って、予約前に見積もる。

### R24-terra1-003 [fatal] 結果の全単射検査なしで不正ベクタを書き、完了扱いにする
- 対象箇所: §3 `poll_batch_embedding_jobs`
- 根拠: 結果キーを submitted job のキー集合ではなく現在の `by_chunk_id` に照合し、未知キー・`values: None`・欠落・重複を黙って通過する。その後は無条件で `Outcome::Succeeded` / `BatchState::Completed` にする。
- 再現手順: A/B を送った job に、A のみ、または現在存在する未送信 C のキーを含む応答を返す。
- 影響: A/B の未埋め込み、C への誤ベクタ永続化、成功記帳が同時に起きる。
- 提案: job ごとの送信キー・embedding hash を耐久保存し、結果集合の完全一致、重複なし、行エラーなしを検証してから一括永続化する。

### R24-terra1-004 [major] profile 変更後の古い job 結果を現在 profile として保存する
- 対象箇所: §3 `poll_batch_embedding_jobs`
- 根拠: `batch_poll_candidates` は profile hash を受け取らず、回収側は現在の `declared_embedding_profile` を使う。行の `tool_profile_hash` との一致確認がない。
- 再現手順: profile P1 で送信後、同次元だが別モデルの P2 に変更して `batch resume` する。
- 影響: P1 で生成されたベクタが P2 の索引として保存され、検索結果が不整合になる。
- 提案: job 作成時 profile を固定し、回収時に row の profile hash と照合する。不一致なら旧 profile として処理するか明示的に終端エラー化する。

### R24-terra1-005 [fatal] failed job を同一 resume 内で無制限に再送する
- 対象箇所: §3 `poll_batch_embedding_jobs`、§8 `known_gap_a_failed_job_is_resubmitted_within_the_same_pass`
- 根拠: 非成功 terminal を見積額で精算し token を消した直後、同じ pass の enrichment が同じ member set を新規 job として送る。テスト自身が「retry budget なしで 2 回 create」と固定している。
- 再現手順: 常に `BATCH_STATE_FAILED` を返す job で `kio batch resume` を繰り返す。
- 影響: provider が失敗分を請求する場合、再送ごとに費用が積み上がる。
- 提案: member/job 単位の attempts と `next_retry_at` を保存し、同一 pass の再送を禁止する。上限到達時は明示的に失敗として扱う。

### R24-terra1-006 [major] Batch client 不可時に OCR と embedding が別レーンになる
- 対象箇所: §3 `submit_embedding_batch_jobs`、§5 enrichment 分岐
- 根拠: Gemini Batch client を解決できないと `Ok(None)` で embedding だけ sync にフォールバックするが、`INVOCATION_LANE` は Batch のままである。規範の「1 invocation では両方 Batch または両方即時」に反する。
- 再現手順: OCR Batch client は利用可能、Gemini Batch client は利用不可の状態で既定レーンの index を実行する。
- 影響: 同一 invocation で OCR は Batch、embedding は sync となり、レーン規約と料金予測が崩れる。
- 提案: 送信開始前に両 adapter の可用性を判定し、片方でも Batch 不可なら invocation 全体を sync に固定する。

### R24-terra1-007 [major] 512 件固定分割は inline サイズ上限を保証しない
- 対象箇所: §3 `EMBEDDING_BATCH_JOB_MAX_MEMBERS`、`submit_embedding_batch_jobs`
- 根拠: 件数だけで 512 件に分割し、JSON の実バイト数検査は予約・phase 2 記録後の `create_embedding_job` 内で初めて行う。6,000 文字の制御文字などは JSON escape により 16 MiB を超え得る。
- 再現手順: 最大長の escape が多い chunk を 512 件投入する。
- 影響: job 未作成のまま予約済み・作成開始済み行が残り、同じ集合を繰り返し送ろうとして失敗する。
- 提案: 実際の serialized body サイズで予約前に動的分割し、上限超過時は半分へ分割して再計画する。

### R24-terra1-008 [major] `responsesFile` の成功 job が永続的に poll 失敗する
- 対象箇所: §2 `GeminiBatchJobRecord.responses_file`、§3 `poll_batch_embedding_jobs`
- 根拠: client は `responsesFile` を検出するが、poll 側は無視して `fetch_inlined_results` を呼ぶ。inline 結果が無ければ parse error で return し、行を終端化しない。
- 再現手順: `SUCCEEDED` と `responsesFile` だけを持つ provider 応答を返す。
- 影響: 完了済み job が state 1 のまま残り、予約と poll が恒久的に滞留する。
- 提案: file output を取得・検証できるようにするか、未対応なら費用を精算した terminal error に遷移させる。

### R24-terra1-009 [fatal] repair の preview と削除実行に TOCTOU 窓がある
- 対象箇所: §7 `registry_prune(true/false)`、`prune_orphans(true/false)`
- 根拠: preview の件数だけを確認し、対象集合・世代・ロックを実行側へ渡していない。特に `count == 0` は確認を省略するため、preview 後に現れた対象も無確認で削除される。
- 再現手順: preview 完了後、確認入力前に別プロセスで orphan を作成または対象状態を変更する。
- 影響: ユーザーが確認していないオブジェクトを永久削除できる。
- 提案: preview で immutable な対象 manifest を作り、その manifest のみを削除する。少なくとも対象再検証と排他ロックを行う。

### R24-terra1-010 [major] verify-objects の `--yes` 判定が誤った operation 配下にある
- 対象箇所: §7 `if let RepairOperation::RebuildDb(rebuild)` 内の `skip_prompt`
- 根拠: `RebuildDb` と判定した直後に同じ `args.operation` が `VerifyObjects(verify)` かを `matches!` しており、条件は常に false である。さらに prune 処理が RebuildDb 側に接続されている。
- 再現手順: 非対話環境で intended な `verify-objects --prune-orphans --yes` を実行する。
- 影響: `--yes` が効かず確認拒否になり得る一方、rebuild-db が意図しない prune 経路に入る。
- 提案: `VerifyObjects` の正しい match arm に `verify.yes` と prune 指定を配置し、非対話の `--yes`／拒否／rebuild-db を個別にテストする。

### R24-terra1-011 [major] 提示された実装断片は構文的に完結していない
- 対象箇所: §2 `let value = read_json_bounded(`、§4 重複した `fn estimate_embedding_cost`
- 根拠: §2 は関数呼出しを閉じず code fence で終わり、§4 は閉じ括弧なしで同名関数を再宣言している。
- 再現手順: target.md の断片をそのまま該当 Rust source に適用してコンパイルする。
- 影響: H1/H2 実装と契約テストを実行できない。
- 提案: 欠落した呼出し・括弧を復元し、`estimate_embedding_cost` を単一定義にしてコンパイル検査を必須化する。

### 確認したが問題なしと判断した点

- `inline_embed_batch_body` 自体は空入力、件数、serialized byte 上限を拒否している。
- inline embedding の terminal 処理で `clear_intent_token: true` を渡しており、upload 残骸のないレーンの規範と整合する。
- 実行中 job は terminal 精算されず、契約テストも繰返し poll で state 1・token 維持・行増殖なしを確認している。
- 明示的な `--realtime` の embedding 経路は sync を選び、Batch client を呼ばない契約テストがある。