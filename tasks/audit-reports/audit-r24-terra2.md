読了行数: 1732
最終2行: } / ```
判定: 不合格

### R24-terra2-001 [fatal] 失敗済み Batch job を同一 pass で無制限に再投入する
- 対象箇所: §3 `poll_batch_embedding_jobs` の非成功終端処理、§8 `known_gap_a_failed_job_is_resubmitted_within_the_same_pass`
- 根拠: 非成功 job は見積額で終端記帳された直後、同じ `batch resume` pass の enrichment で同一メンバ集合を新規予約・再送する。テスト自身が「fresh reservation and no backoff」「unbounded」と明記して 2 回の `create_embedding_job` を期待している。
- 再現手順: job を `BATCH_STATE_PENDING` で投入後、`BATCH_STATE_FAILED` を返す mock で `kio batch resume` を実行する。失敗 job の記帳後、同じ pass で 2 本目の job が作成される。これを繰り返す。
- 影響: 失敗 job が部分課金され得る状態で、再試行ごとに課金・予約が積み上がる。恒久的な provider 障害で支出と job 数が無制限に増える。
- 提案: job ごとの失敗をメンバへ耐久的に反映し、`attempts`・backoff・上限を適用する。同一 pass での即時再投入を禁止し、再試行は次回の許可時刻以降に限定する。

### R24-terra2-002 [fatal] 回収結果を job 入力集合・profile に照合せず成功確定する
- 対象箇所: §3 `poll_batch_embedding_jobs`、§2 `parse_inlined_results`
- 根拠: 回収側は全現行 chunk の `by_chunk_id` を引き、返却 `metadata.key` が当該 job のメンバか、重複・欠落がないかを検査しない。`values: None`（個別 error）や未知 key は `continue` するだけで、最後は job 全体を `Succeeded` として終端記帳する。さらに row の `tool_profile_hash` と現行 profile の一致確認もない。
- 再現手順: A を含む job を投入し、poll 時点で現行集合にあるがその job には含まれない B の key と有効なベクタだけを mock 応答で返す。B のベクタが保存され、A は未埋め込みのまま job は成功完了になる。profile hash だけ変更して同次元のまま resume しても、旧 profile の結果を現行 profile として保存できる。
- 影響: 別 chunk への誤ベクタ書込み、結果取りこぼし、profile 混在、成功扱いによる再送・再課金が起きる。
- 提案: 提出時の key・embedding hash・profile hash を job に耐久保存し、回収前に key の全単射、個別 error、次元、正規化、profile 一致を全件検査する。欠落・重複・想定外 key は成功確定せず、purge 済みだけを明示的に退役扱いにする。

### R24-terra2-003 [fatal] 宣言済み pricing では Batch/Realtime の単価差が消える
- 対象箇所: §4 `embedding_usd_per_token`
- 根拠: `registered_declared_pricing("embedding").get("tokens_in")` が存在すると、引数 `lane` を見ずにその値を返す。したがって `[embedding.*.pricing] tokens_in` 使用時は Batch と Sync が同額になるが、規範は $0.10/$0.20 のレーン別単価を要求している。
- 再現手順: 宣言済み `tokens_in` を設定し、同一入力で既定 Batch と `--realtime` を実行する。両方の見積り単価が同じになり、少なくとも片方が誤る。
- 影響: 予約額・確定記帳・budget cap が実支出と一致しない。
- 提案: pricing にレーン別値を持たせるか、宣言値を基準単価として Batch 割引を明示的に適用する。両レーンの ledger 金額を数値で検証する契約テストを追加する。

### R24-terra2-004 [fatal] 見積りが実際に送る contextualized input を含まない
- 対象箇所: §3 `submit_embedding_batch_jobs`
- 根拠: `candidate_usd` は `group.representative.text` だけで計算する一方、provider には `contextualized_embedding_input(context, &text)` の戻り値を送っている。非空の context は入力 token だが予約・確定額に含まれない。
- 再現手順: `chunk_embedding_context` が非空となる chunk を Batch 投入し、capture した送信 text と見積り対象 text を比較する。context 部分の token が見積りから漏れる。
- 影響: usage が返らないため不足予約がそのまま過少記帳となり、budget cap も過少に評価される。
- 提案: contextualized text を先に一度だけ生成し、その同一文字列を見積りと送信の両方に使う。capture input と ledger 見積りの一致をテストする。

### R24-terra2-005 [major] Batch client 不可時に embedding だけが Sync へ落ちる
- 対象箇所: §3 `submit_embedding_batch_jobs`、§4 `effective_invocation_lane` / `active_embedding_send_lane`
- 根拠: Gemini Batch client を解決できないと `submit_embedding_batch_jobs` は `None` を返し、embedding は Sync へフォールバックする。しかし invocation lane のセルは Batch のままであり、§4 は OCR 側もそのセルを読むとしている。両 adapter を同一レーンにする規約を局所フォールバックが破る。
- 再現手順: OCR Batch client は利用可能、Gemini Batch client だけ不可の状態で、OCR と embedding の両方が必要な `index --online` を実行する。OCR は Batch 選択のまま、embedding 側だけ Sync 経路へ進む。
- 影響: 一回の invocation 内で OCR/embedding が別レーンになり、明示的な料金・待ち時間の契約に反する。
- 提案: 送信前に両 Batch 依存性をまとめて判定し、どちらかが不可なら invocation 全体を Sync にするか失敗させる。片方だけの fallback を禁止するテストを追加する。

### R24-terra2-006 [major] repair の preview と削除実行の間に未確認削除の窓がある
- 対象箇所: §7 `registry_prune(true)` → `confirm_repair_prune` → `registry_prune(false)`、`prune_orphans(..., true/false)`
- 根拠: 確認対象は dry-run の件数だけで、削除対象集合は固定されない。特に preview が 0 件または `blocked` の場合は確認を省略したまま、後続の本実行で新たな対象を削除できる。
- 再現手順: preview 完了後、実削除前に別プロセスで orphan または registry-prune 対象を作る。本実行は preview 時の件数と異なる対象を削除する。
- 影響: 利用者が確認していない永久削除が発生し、H2 の確認契約に反する。
- 提案: lock 下で削除候補を materialize し、その ID・世代を確認後の実行へ渡す。不一致時は削除せず再 preview・再確認する。

### R24-terra2-007 [major] 未知の provider state を永久に in-flight 扱いする
- 対象箇所: §2 `GeminiBatchState::Other` / `is_terminal`、§3 `poll_batch_embedding_jobs`
- 根拠: 未知 state は `Other` になり、`is_terminal()` は false を返す。poll 側はそのまま `inflight += 1` して継続するだけで、契約違反・期限切れ・operator 向け失敗へ遷移しない。
- 再現手順: mock に未知の terminal 相当 state を返させ、繰り返し `kio batch resume` を実行する。row は JobCreated のまま残り、毎回 poll される。
- 影響: provider の状態追加や異常応答で job が恒久的に滞留し、poll と運用リソースを消費する。
- 提案: 未知 state を明示的な contract violation として扱い、bounded reconciliation 後に terminal error または要介入状態へ遷移させる。

### 確認したが問題なしと判断した点

- inline Batch body は空入力、2,048 request、16 MiB の上限を検査している。
- ベクタは次元・有限値・非ゼロを検査し、正規化後にも再検査している。
- 同一メンバ集合で job が既に `batch_job_id` を持つ場合は再作成せず、再実行テストも provider job が 1 本であることを確認している。
- `--realtime` の正常経路では Batch submit を通らず、Sync row だけを作る契約テストがある。
