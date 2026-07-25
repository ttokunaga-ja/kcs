読了行数: 1732
最終2行:
```
}
```
```
判定: 不合格

---

### R24-son1-1 [fatal] 失敗した embedding batch job が同一パス内で即座に再投入され、課金と再送が無制限に積み上がる
- 対象箇所: `## 8. 契約テスト` の `known_gap_a_failed_job_is_resubmitted_within_the_same_pass` テスト、および同節の doc コメント「KNOWN GAP」(target.md 1574-1617行)。関連実装は `## 3` の `poll_batch_embedding_jobs`(920-943行、`settle_batch_charge_terminal(... Outcome::Expired ... true)` で `intent_token` を clear)と `## 5` の enrichment レーン分岐(1170-1196行)。
- 根拠: 規範「予約時の見積りがそのまま確定記帳になる」(0節)により、1 回の失敗 job ごとに `estimated_usd` が `cost_ledger` に確定記帳される。target.md 自身が明記する通り、failed job を settle した直後、同じ `batch resume` パス内で enrichment が再駆動され、member task が Failed 化されないまま同一メンバ集合で **fresh reservation・no backoff** の新規 job が即時投入される。テスト `known_gap_...` は `create_embedding_job` 呼び出しが 1 回の `batch resume` 実行で 2 回発生することを実測で確認しており、これは推測ではなく target.md 内の実文・実テストによる裏付けである。
- 再現手順: (1) `index --approve --online` で job を投入 (2) その job が `BATCH_STATE_FAILED` で終端 (3) `batch resume` を実行 → 失敗記帳 (`cost_ledger` に `estimated` charge 1件) の直後、同一メンバ集合で新規 `create_embedding_job` が発生し、新たな `estimated_usd` 予約が発生。恒久的に失敗し続けるコンテンツ (例: provider 側で拒否され続ける入力) であれば、`batch resume` を呼ぶたびに同じ回数分の課金が積み上がり続ける。
- 影響: budget cap に達するまで、実行のたびに実際には成功しない task に対して確定記帳が繰り返し積まれる (二重〜多重課金)。また `attempts` 列はインクリメントされる (`attempts_delta: 1`) にも関わらずそれを見て再送を止める分岐が示されていないため、無限に近い再送ループの温床になる。
- 提案: markdownize レーンが持つ `attempts`/`next_retry_at` によるバックオフ相当の仕組みを embedding batch レーンにも適用し、collect 失敗時に member task を明示的に Failed 化 (または cooldown を課す) してから enrichment の再選択対象に戻すべき。target.md はこれを「audit で議論すべき既知の欠落」として明示しているため、fatal 指摘として本監査で確定させる。

### R24-son1-2 [major] `verify-objects --prune-orphans` の確認プロンプトが誤った enum 分岐 (`RebuildDb`) にぶら下がっており、H2 の非対話/確認契約が成立しない
- 対象箇所: `## 7. repair の確認プロンプト (H2)` の呼び出し側コード、1298-1320行。特に `if let RepairOperation::RebuildDb(rebuild) = &args.operation { let skip_prompt = matches!(&args.operation, RepairOperation::VerifyObjects(verify) if verify.yes); ... verify_objects::prune_orphans(...) ... }`。
- 根拠: 直前の `RegistryPrune` 分岐 (1292-1297行) は `if let RepairOperation::RegistryPrune(prune) = &args.operation { ...; confirm_repair_prune(..., prune.yes)?; ... }` と、分岐の enum ガードと `.yes` の参照元が一致した正しい実装になっている。一方、直後の prune-orphans ブロックは本文が明らかに `verify-objects --prune-orphans` (`"verify-objects --prune-orphans"` という文字列や `preview.pruned_prepared_count + ...` など) を扱っているにも関わらず、ガードは `RepairOperation::RebuildDb(rebuild)` になっている。この分岐内部で `&args.operation` は `RebuildDb` であることが確定しているため、`matches!(&args.operation, RepairOperation::VerifyObjects(verify) if verify.yes)` は **恒久的に false** にしかなり得ず、`skip_prompt` は常に false。監査観点 6「非対話での挙動」が問う契約 (`--yes` で非対話実行できること) が、この分岐が実際に使われる経路のどちらであっても壊れている。
- 再現手順: 2通りの読み方いずれでも契約が壊れる。(a) 仮に `RepairOperation::VerifyObjects` の実行時にこのコードへ到達しない設計だとすると、`kio repair verify-objects --prune-orphans` はここで実装されている prune 実行そのものに到達せず、孤立オブジェクトの掃除が機能しない。(b) 仮に実装が意図通り「rebuild-db 実行時にも orphan pruning を副作用として行う」設計だとすると、`kio repair rebuild-db --yes` を非対話環境 (CI 等、stdin 非 tty) で実行しても `skip_prompt` が常に false のため `confirm_repair_prune` が `stdin().is_terminal()==false` の分岐に落ち `KIO-E-CONFIRM-REJECTED-001` で失敗し、非対話実行が想定通り通らない。
- 影響: (a) の場合は「削除されるべきものが削除されない」機能欠落、(b) の場合は「`--yes` 相当のフラグが効かず非対話運用が壊れる」regression。いずれの読み方でも H2 の確認プロンプト契約 (「非対話での挙動」) が満たされない。
- 提案: `skip_prompt` の判定と外側の `if let` ガードを同一の `RepairOperation` variant に揃える (本来は `RepairOperation::VerifyObjects(verify) if verify.prune_orphans` 相当でガードし、`skip_prompt = verify.yes` とすべき)。`RegistryPrune` 分岐にならい、ガードした variant から直接 `.yes` を取り出す形に統一する。

### R24-son1-3 [major] job 作成成功後・`batch_job_id` 記帳前の crash 窓を検証する契約テスト・回復コードが target.md に存在しない
- 対象箇所: `## 3` の `submit_embedding_batch_jobs` 内、846-855行 (`let job = client.create_embedding_job(...)?; phase2b_record_job_created(...)?;` の間)。および `## 2` の doc コメント「the recovery walk's 発見キー (04 §5.8 / 10 §7.5.2)」。
- 根拠: 監査観点1が最重視する「job 作成後 crash」の窓そのもの。`create_embedding_job` が provider 側でジョブ作成に成功した直後、`phase2b_record_job_created` で `batch_job_id` を記帳する前にプロセスが crash した場合、その task 行は `batch_job_id` が NULL のまま残る。`## 3` 内のコメント (868-869行) は「job id が unknown な行は `kio ledger reconcile` の回復ウォークの管轄であり、poll 側の対象外」と明記するが、target.md には `kio ledger reconcile` の embedding レーン向け実装も、この crash 窓を突く契約テストも一切含まれていない。
- 再現手順: `create_embedding_job` 呼び出し成功直後、`phase2b_record_job_created` 実行前にプロセスを終了させ、その後 `kio ledger reconcile` を経ずに `index --online` を再実行した場合に、同一 task key への再訪問がどう振る舞うか (再作成して二重 job になるか、CAS で恒久停止するか) が target.md の文面からは判定できない。
- 影響: 監査観点1 (二重課金) にとって最も危険な窓が実装未提示・テスト未検証のまま残っている。target.md の範囲内では安全側 (二重投入なし) とも危険側 (二重投入あり) とも断定できないため fatal ではなく major とするが、契約テストの欠如自体が「テストが実際には守っていない契約」(観点7) に該当する。
- 提案: この crash 窓を再現する契約テスト (例: `create_embedding_job` 成功を記録した mock capture の直後にプロセスを模擬終了させ、再実行時の挙動を固定する) を追加し、`kio ledger reconcile` の embedding レーン対応実装 (display_name → intent_token 逆引きでの自己記述化) を target.md の範囲内で明示する。

### R24-son1-4 [minor] `estimate_embedding_cost` が二重定義されており、記載されたままではコンパイルが通らない
- 対象箇所: `## 4. CLI: レーン解決と単価` 1159-1163行。
```
fn estimate_embedding_cost(text: &str, lane: PreferredRequestKind) -> f64 {
    // (estimate_embedding_cost 本体)
fn estimate_embedding_cost(text: &str, lane: PreferredRequestKind) -> f64 {
    estimate_embedding_tokens(text) * embedding_usd_per_token(lane)
}
```
- 根拠: 同名・同シグネチャの関数が外側関数の本体としてネストされており、外側関数の閉じ括弧が示されていない (内側の `}` で閉じているのは内側の fn item のみ)。文面通りだと外側の `fn estimate_embedding_cost` は `f64` を返す本体を持たず型不整合になる。
- 再現手順: 該当コードをそのままコンパイルすると重複定義・戻り値型不一致でビルドが失敗する。
- 影響: 実運用上の課金額そのものへの影響は不明 (どちらが実体かは target.md からは断定できない) だが、この関数は「課金の正確性」の根幹 (§0 で強調される見積り=確定記帳ロジック) を担うため、ドキュメント上の混入であっても放置すべきではない。
- 提案: 監査対象ソースの生成元 (抜粋ツール) で重複貼り付けが起きていないか確認し、単一定義に整理する。

### R24-son1-5 [minor] `active_embedding_send_lane` の doc コメントが実装済みの driver に対して古いまま
- 対象箇所: `## 4` 1087-1098行の `active_embedding_send_lane` doc コメント。
- 根拠: コメントは「embedding Batch driver (submit + `kio batch resume` poll/collect) はまだ着地していない」「driver が着地する同じ変更で `effective_invocation_lane()` になる」と述べるが、`## 3` で driver (`submit_embedding_batch_jobs` / `poll_batch_embedding_jobs`) は既に実装済みであり、`## 5` の enrichment 分岐 (1175行) は既に `effective_invocation_lane()` を直接参照している。関数自体の戻り値 (常に `Sync`) は、Batch 分岐が早期 return するため到達経路 (realtime 指定 or レーン不可フォールバック) がいずれも sync 単価で正しいため機能的には問題ないが、コメントは実態と矛盾し将来の読者を誤誘導する。
- 再現手順: 該当コメントを読むだけで実装状況について誤った前提を持つ (再現というよりレビュー時の誤解のリスク)。
- 影響: 機能影響なし。可読性・保守性の問題のみ。
- 提案: コメントを「driver 着地済み、到達する両経路 (realtime 指定 / レーン不可フォールバック) はいずれも sync 単価が正しいため定数のまま」という趣旨に更新するか、関数自体を削除して呼び出し側で直接 `PreferredRequestKind::Sync` を使う。

### R24-son1-6 [minor] `registry-prune` / `verify-objects --prune-orphans` の確認は prune 対象のスナップショットを共有せず、preview と実行の間で対象がずれ得る
- 対象箇所: `## 7` 1292-1316行。`registry_prune(true)` → `confirm_repair_prune(...)` → `registry_prune(false)` (および `prune_orphans` の同型パターン)。
- 根拠: 観点6が問う「dry-run と本実行の結果がずれる窓」そのもの。2回の呼び出しは真偽値のみが異なる独立呼び出しで、対象 ID 集合や snapshot を共有していない。`kio batch abandon` については「`run_batch` の既に取得済みの `.kio/.lock` 内で実行する」と明記されている (1289-1290行) が、この repair の prune 呼び出し周りにはロック取得の言及が無い。
- 再現手順: target.md の範囲内では、preview 呼び出しと実行呼び出しの間に他プロセス (または同プロセス内の他ステップ) が対象状態を変化させ得るかどうかは断定できない (ロックの有無が「不明」)。
- 影響: 仮に両呼び出しの間で対象が変化し得る環境であれば、ユーザーが確認した件数と実際に削除される対象が一致しない可能性がある。ロックの有無が不明なため、これを fatal/major の根拠にはしない。
- 提案: 明示的に「同一 `.kio/.lock` 内で preview→confirm→実行が完結する」ことをコメントとして明記するか、preview で得た対象 ID 集合をそのまま実行呼び出しに渡す設計に変更し、ずれを構造的に排除する。

### 確認したが問題なしと判断した点
- `normalize_embedding_vector` (## 3, 666-683行) は正規化前後の両方で `validate_cosine_vector` を通しており、07 §5.3 (3)/(4) が要求する「アンダーフローでゼロベクトルになる／オーバーフローで無限大になる結果を index に到達させない」規範を正しく満たしている。
- invocation 単位のレーン解決 (`resolve_invocation_lane` / `effective_invocation_lane`, ## 4) は `--realtime` と `--batch` の排他検証、CLI→scope config→user config→既定Batch の解決順、および `--online` との軸の分離を正しく実装しており、`realtime_uses_the_synchronous_lane_and_never_creates_a_batch_row` テストで OCR/embedding が同一レーンに倒れ `batch_requests` に `batch` 行が作られないことまで確認されている。
- 終端時の `intent_token` NULL 化 (`settle_batch_charge_terminal` 経由、成功・失敗いずれの終端でも `clear_intent_token=true`) は、inline レーンには upload 残骸が存在しないため「終端=掃除完了」という §5.8/§5.4 の理由付けと整合しており、`batch_resume_collects_the_vectors_and_clears_the_intent_token` テストで `state=2 かつ intent_token IS NULL` が実測確認されている。
- `poll_batch_embedding_jobs` の collect 処理は、提出時のメンバ集合をそのまま信頼せず、現在の chunk 集合から `embedding_hash` を再導出してグループを再構成しており、purge されて消えた chunk の結果は静かに読み捨てる (何も誤記帳しない) 設計になっている。これはデータ喪失・不整合 (観点3) に対して妥当な対処である。
- 実行中ジョブへの繰り返しポーリングは冪等であり (`a_running_batch_job_stays_in_flight_across_repeated_polls` テストで、2回ポーリングしても `batch_requests` の行数が1のまま、状態も `1|0` (token保持) のままであることを確認)、ポーリングが誤って再課金・再確定記帳しないことが検証されている。
