読了行数: 1732
最終2行: }\n```
判定: 不合格

### R24-sol-1 [fatal] 宣言済み単価がレーンを無視し、Batch と realtime が同額で記帳される
- 対象箇所: §4 `embedding_usd_per_token` — `registered_declared_pricing("embedding")` の `tokens_in` をレーン判定前に返す箇所
- 根拠: 宣言単価が存在すると `lane` は参照されず、Batch と Sync が同じ単価になる。規範上は Batch $0.10、Sync $0.20 でなければならない。
- 再現手順: `tools.toml` に `tokens_in = p` を設定し、同じテキストを既定 Batch と `--realtime` で見積もる。どちらも `tokens × p` となり、少なくとも片方が誤額になる。
- 影響: 確定記帳額と budget cap が半額または倍額ずれ、過少記帳なら cap を超過できる。
- 提案: Batch/Sync の単価を別々に宣言するか、`tokens_in` の基準レーンを固定して倍率を適用する。両レーンの確定額が正確に 1:2 となるテストを追加する。

### R24-sol-2 [fatal] 予約額が実際に送信する contextualized text を含んでいない
- 対象箇所: §3 `submit_embedding_batch_jobs` — 見積りは `group.representative.text`、送信は `contextualized_embedding_input(context, &group.representative.text)`
- 根拠: 予約対象と provider に送る課金対象文字列が異なる。usage が `None` なので、この不足額は確定時にも補正されない。
- 再現手順: `chunk_embedding_context` が非空となる raw path の chunk を投入する。context を付加した入力が送られる一方、予約・確定額は本文だけで計算される。
- 影響: embedding 支出が恒常的に過少記帳され、budget cap の保護額も小さくなる。
- 提案: `GeminiBatchEmbedInput` を先に構築し、実際の `input.text` そのものから job の予約額を計算する。

### R24-sol-3 [fatal] job digest にメンバ集合を保存しないため、集合変化時に飛行中メンバが重複送信される
- 対象箇所: §3 `embedding_job_input_hash`、`submit_embedding_batch_jobs`、引用「Submitted members stay Pending」「a different selection is a different task」
- 根拠: 行に残るのは不可逆な集合 digest だけで、個々の `embedding_hash` や request key は保存されない。飛行中メンバも Pending のままなので、集合が少し変わると別 digest の新規 job に再び含まれる。
- 再現手順: 512 未満の集合 A を Batch 送信し、job が Pending の間に新規 chunk B を追加して再度 index する。新しい集合 A∪B は別キーとなり、A を含む第2 job と第2予約が作られる。
- 影響: 同じ embedding が並行して二重課金され、結果の競合も起きる。`--realtime` 時に飛行中メンバだけを除外するための耐久情報もない。
- 提案: job ごとの耐久的な member manifestを保存し、未終端 job に属する `embedding_hash` を全レーンの選択から除外する。abandon・失敗・collect もその manifest 単位で処理する。

### R24-sol-4 [fatal] collect が入力との全単射を検査せず、不完全結果でも成功確定する
- 対象箇所: §3 `poll_batch_embedding_jobs` — 未知 key と `values == None` を `continue` し、最後に無条件で `Outcome::Succeeded`
- 根拠: 規範の「id 全単射」に反し、missing、duplicate、extra、per-line error のいずれも検査されない。未知 key が別の現存 chunk を指せば、その chunk 用として返却 vector を書き込む。
- 再現手順: 2 request の job に対し1件だけ返す、または片方を `error` にする。1件だけ保存した後、行は state 2、token NULL、全額 succeeded になる。別の現存 chunk IDへ key を差し替えると、その chunk に誤った vector が保存される。
- 影響: vector の誤書き込み、未埋め込みの見落とし、欠落メンバ再送時の追加課金が発生する。
- 提案: 保存済み manifest と結果 key の完全一致・一意性・全件成功を先に検査する。不一致時は成功確定せず contract violation として終端処理する。

### R24-sol-5 [major] 飛行中行の profile と現在の profile の一致を確認していない
- 対象箇所: §3 `poll_batch_embedding_jobs` — 現在の `declared_embedding_profile(execution)` を全行に使用
- 根拠: `row.key.tool_profile_hash` と現在の `profile.profile_hash` の比較がない。これは受入検査の profile 一致条件に直接反する。
- 再現手順: profile P1 で job を送信後、同じ次元数の別 profile P2 に切り替えて resume する。P1 の結果が P2 の hash・保存先で処理される。次元が違えば、同じ成功 job が毎回検証エラーになる。
- 影響: 次元互換時は誤 profile の vector が混入し、非互換時は回収不能になる。
- 提案: 行に記録された profile を解決して処理し、現在値と不一致なら書き込まず明示的に保留・終端する。

### R24-sol-6 [major] 不正な成功結果が state 1 のまま無限に再処理される
- 対象箇所: §3 `fetch_inlined_results(...)?`、`normalize_embedding_vector(...)?`
- 根拠: parse、次元、有限性、非ゼロ、正規化後検査の失敗が terminal transaction に変換されない。`contract_violation_count` も増えない。
- 再現手順: Succeeded job にゼロ vector、767 次元、または values 欠落を返す。resume のたびに同じ箇所で終了し、行は state 1、token 非NULLのまま残る。
- 影響: poll の永久失敗、予約額の占有、手動 abandon まで進行不能となる。
- 提案: 検証エラーを捕捉し、同一 Tx で state 3、課金、contract violation count、member failure を記録する。

### R24-sol-7 [major] 失敗 job が同じ pass 内で無制限に再投入される
- 対象箇所: §8 `known_gap_a_failed_job_is_resubmitted_within_the_same_pass`
- 根拠: テスト自身が、失敗直後に fresh reservation と第2 job が作られ、backoff・attempt 上限がないことを固定している。
- 再現手順: job を `BATCH_STATE_FAILED` にして `batch resume` を繰り返す。各 pass が失敗分を確定後、同じ集合を直ちに再送する。
- 影響: provider job と課金が反復し、通常の write command だけでコスト・リソースを継続消費する。
- 提案: manifest から member task を失敗遷移させ、`attempts`、`next_retry_at`、最大試行回数を適用し、同じ pass では再選択しない。

### R24-sol-8 [major] crash 回復用の job 一覧走査が5000件で打ち切られる
- 対象箇所: §2 `BATCH_LIST_PAGE_SIZE = 100`、`BATCH_LIST_MAX_PAGES = 50`、引用「walk STOPS at the bound」
- 根拠: job 作成後・`batch_job_id` 記録前の crash は displayName による一覧照合が唯一の回復経路だが、走査が完全ではない。
- 再現手順: provider に5000件超の job がある状態で新規 job を作成し、`phase2b_record_job_created` 前に crash する。対象が50ページ以降なら token を発見できない。
- 影響: 予約と provider job の対応が回復できず、abandon・再投入により二重課金する可能性がある。
- 提案: crash reconciliation は一致発見またはページ終端まで走査する。表示用 inventory の上限と回復処理の完全走査を分離する。

### R24-sol-9 [major] repair の preview と削除が別計算で、未確認対象を削除できる
- 対象箇所: §7 `registry_prune(true)` → 確認 → `registry_prune(false)`、および `prune_orphans(true)` → `prune_orphans(false)`
- 根拠: 確認した対象集合・世代を実行側へ渡していない。特に preview が0件または `blocked` の場合は確認を完全に省略した後でも本実行を呼ぶ。
- 再現手順: preview が0件または blocked を返した直後、別プロセス等で対象を追加または unblock する。本実行は新しい集合を再計算し、確認なしで削除する。
- 影響: 表示した件数を超える、または一度も承認されていない永久削除が起きる。
- 提案: preview で対象IDの不変 plan を作り、その plan だけをロック下で削除する。集合・世代が変わった場合は中止して再確認し、0件・blocked なら本実行を呼ばない。

### R24-sol-10 [major] repair の `--yes` 判定が到達分岐と異なる variant を検査している
- 対象箇所: §7 — `if let RepairOperation::RebuildDb(...)` 内の `matches!(..., RepairOperation::VerifyObjects(verify) if verify.yes)`
- 根拠: 提示された分岐に入っている限り operation は `RebuildDb` なので、`skip_prompt` は必ず false になる。
- 再現手順: この分岐で削除件数を1件以上にし、非TTYで実行する。確認省略フラグは有効にならず、`KIO-E-CONFIRM-REJECTED-001` になる。
- 影響: 非対話 repair の自動化契約が成立せず、意図した operation と prune 処理の配線も不明瞭になる。
- 提案: 現在処理中の variant から対応する `yes` を直接取得し、operation ごとの非TTYテストを追加する。

### R24-sol-11 [major] 契約テストが重大な課金・回復・削除条件を守っていない
- 対象箇所: §8 契約テスト全体
- 根拠: 金額そのもの、変化したメンバ集合、partial/duplicate/unknown key、profile 変更、job 作成直後 crash、collect 中 crash、repair の拒否・競合を検証していない。失敗即再送は修正を要求せず「CURRENT behavior」として assert している。
- 再現手順: R24-sol-1〜10 の入力を与えても、提示されたテスト群だけは通過できる。
- 影響: 二重課金、誤 vector、未確認削除を回帰として検出できない。
- 提案: exact USD と1:2比、飛行中集合への追加・削除、全単射、profile pin、各 crash 窓、preview/execute 間の集合変更を契約テストへ追加し、known-gap テストは望ましい挙動へ反転する。

### 確認したが問題なしと判断した点

- `inline_embed_batch_body` は空入力、2048 request 上限、最終JSONの16 MiB上限を検査している。
- `normalize_embedding_vector` は生 vector と正規化後 vector の双方に次元・有限・非ゼロ検査を適用している。
- provider scope と job-create 開始時刻を作成前に記録し、作成後に job ID を記録する順序、および displayName への intent token 埋め込みは crash 回復の基本形に沿っている。
- Running job は終端記帳せず state 1・token保持のまま残し、反復 poll でも新しい予約を作らない。
- 集合が変化しない通常の拒否経路では、`confirm_repair_prune` のエラーが本実行呼び出しより前に返るため、拒否後の削除は行われない。