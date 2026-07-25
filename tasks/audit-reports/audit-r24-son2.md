読了行数: 1732
最終2行:
```
    assert_eq!(creates, 1, "the in-flight job must not be duplicated");
```
判定: 不合格

### R24-son2-1 [fatal] 失敗した embedding batch job が同一パス内で即座・無制限に再投入される
- 対象箇所: `poll_batch_embedding_jobs` の非成功終端処理 (`settle_batch_charge_terminal(..., Outcome::Expired, ..., increment_contract_violation=false, clear_intent_token=true)`, target.md 920-944行)、および §8 の契約テスト `known_gap_a_failed_job_is_resubmitted_within_the_same_pass` (1574-1617行) とそのすぐ上のコメント "KNOWN GAP" (1574-1583行)。
- 根拠: job が FAILED/CANCELLED/EXPIRED で終端すると、`intent_token` は常にクリアされ (`clear_intent_token=true`)、`contract_violation_count` は増分されない (`increment_contract_violation=false`)。かつ、失敗したメンバ群に対して `record_embedding_transitions` が一切呼ばれず Pending のままなので、同一 `kio batch resume` パス内で enrichment が再駆動され、同じメンバ集合が再度 `plan_embed_batch` に拾われる。`embedding_job_input_hash` は同一メンバ集合から同一 digest を出すため、`batch_requests` の同一 PRIMARY KEY 上に**新しい予約とジョブが即座に作られる** (`submission_seq` による再作成をスキーマが明示的に許容 — 102-105行のコメント参照)。テスト自身が `creates == 2`（1回の失敗で即再投入1回）を「現行動作」として固定しており、バックオフや試行回数上限は一切存在しない。
- 再現手順: (1) `kio index --approve --online` でジョブ投入。(2) provider が `BATCH_STATE_FAILED` を返す状態で `kio batch resume` を実行。(3) 同一パス内で `create_embedding_job` が即座に2回目呼ばれる（テストで確認済み）。(4) provider 側が恒久的に失敗する内容（コンテンツポリシー違反等）であれば、以後 `batch resume` を呼ぶたび（または「任意の write コマンド」経由でも自動的に）新規予約・新規ジョブが繰り返される。
- 影響: budget cap が `hard_stop=false` あるいは `override_budget=true` の場合、無制限に実課金が発生し得る（規範冒頭「budget cap が守る金額そのものが狂う」に直結）。`hard_stop=true` でも、cap に達するまで毎パス新規予約が積み上がり、無関係な他タスクの予約枠を圧迫する。監査観点4（無限ループ・リソース枯渇）と観点1（二重課金）の双方に該当する、target.md 自身が明示的に認めている未解決の欠陥。
- 提案: 失敗終端時にもメンバタスクを明示的に Fail 遷移させ、`contract_violation_count` に相当する試行回数/バックオフ機構（markdownize レーンの `attempts` / `next_retry_at` に準じるもの）を embedding Batch ジョブの失敗にも適用する。同一メンバ集合の即時再投入を禁止し、最小限でも「同一パス内での再投入」を防ぐガードを入れる。

### R24-son2-2 [major] `RebuildDb` 分岐の確認プロンプトが誤った enum variant を照合しており `--yes` が機能しない疑い
- 対象箇所: target.md 1299-1316行。
  ```
  if let RepairOperation::RebuildDb(rebuild) = &args.operation {
          let skip_prompt = matches!(
              &args.operation,
              RepairOperation::VerifyObjects(verify) if verify.yes
          );
          ...
          confirm_repair_prune("verify-objects --prune-orphans", ..., skip_prompt)?;
          ...
          let prune = verify_objects::prune_orphans(&repo, false)?;
  ```
- 根拠: 外側の `if let` で `args.operation` は `RepairOperation::RebuildDb` であることが確定しているにもかかわらず、内側の `matches!` は `RepairOperation::VerifyObjects(verify) if verify.yes` を照合している。同一値が2つの異なる enum variant に同時にマッチすることはあり得ないため、`skip_prompt` は**常に `false`** になる。束縛された `rebuild`（`RebuildDb` の内容）は一度も参照されない。さらに呼び出している関数は `verify_objects::prune_orphans`、ラベルも `"verify-objects --prune-orphans"` であり、`RebuildDb` 用のロジック（DB 再構築）がこの範囲に一切現れない。`VerifyObjects` 分岐からのコピペ跡と強く整合する。
- 再現手順: 非対話環境（CI 等、stdin が TTY でない）で `kio repair rebuild-db --yes` を実行する。`rebuild.yes` が真であっても `skip_prompt` は常に false のため `confirm_repair_prune` は非対話ガードに入り `KIO-E-CONFIRM-REJECTED-001` で失敗する（`--yes` を渡した意味がない）。
- 影響: 監査観点6「非対話での挙動」に反する。自動化・CI での `rebuild-db --yes` が意図せず失敗する。加えて（target.md が該当箇所で途中で切れているため確証はできないが）呼び出しているのが `prune_orphans` のみで rebuild 相当の処理が見当たらない点は、`RebuildDb` 操作そのものが正しく実装されているか疑わしい。
- 提案: `skip_prompt` の照合を `RepairOperation::RebuildDb(rebuild) if rebuild.yes` に修正する。あわせて、このブロックが本当に DB 再構築を行っているか（`verify_objects::prune_orphans` 呼び出しで完結していないか）を実装側で確認する。

### R24-son2-3 [major] representative チャンクが purge されると、生存メンバがいても embedding 結果が丸ごと破棄され再課金が必要になる
- 対象箇所: `poll_batch_embedding_jobs` 内、target.md 949-969行。
  ```rust
  let Some(chunk) = by_chunk_id.get(&result.key) else {
      // The chunk is gone (purged / reconfigured) since submission —
      // nothing to write, and nothing to fail either.
      continue;
  };
  ...
  // Re-derive the group from the CURRENT chunk set rather than
  // trusting the submitted membership: ...
  ```
- 根拠: 結果を引くキーは投入時に選ばれた「representative」の `chunk_id`（838行 `key: group.representative.chunk_id.clone()`）のみである。collect 時のグループ再構築（「現在のチャンク集合から再導出する」設計）は `by_chunk_id.get(&result.key)` が成功した**後**にしか走らない。したがって、投入から collect までの間に representative チャンクだけが purge/再構成で消え、同一 `embedding_hash` を持つ他のメンバ（重複コンテンツを持つ別ファイルのチャンク等）が現存していても、その行は無条件に `continue` され、支払い済みの embedding 結果全体が捨てられる。
- 再現手順: (1) 重複コンテンツを持つチャンク A（representative として選ばれる）とチャンク B（同一 `embedding_hash`）を含む job を投入。(2) collect 前に A を含むファイルを削除/編集し、A が現在のチャンク集合から消える。(3) job 成功で collect すると、B が生存していても `by_chunk_id.get("A")` が None となり、その行は破棄される。B は結局ベクタを得られず、後続パスで新たに再投入・再課金される。
- 影響: 監査観点1（課金漏れ/二重支払い）・3（データ喪失・不整合）に該当。既に provider に支払った embedding 結果が、なお有効な利用先（B）があるにもかかわらず破棄され、同一内容への再課金が発生する。恒久的なデータ喪失ではないが、確定的な無駄な実支出を生む。
- 提案: representative の `chunk_id` で引けなかった場合、`embedding_hash`（またはメタデータに含めた content-identity）で現在のチャンク集合から再検索し、生存メンバがあればそちらへ結果を適用するフォールバックを入れる。

### R24-son2-4 [major] batch collect 経路が `persist_group_vector` に常に空の `held` を渡しており、purge 競合保護が sync 経路と揃っていない疑い
- 対象箇所: target.md 908行 `let held = BTreeSet::new();` と 976行 `persist_group_vector(&conn, &profile, &group, &normalized, &held)`。
- 根拠: `persist_group_vector` が `held: &BTreeSet<_>` を受け取る設計になっている以上、これは何らかの「書き込みを避けるべきチャンク集合」（並行 purge/再構成中のチャンク等）を表すパラメータであると読むのが自然である。しかし batch collect 経路ではこれを**計算せず常に空集合**で渡している。sync 経路（target.md には実装が無く不明）が同じ関数を呼ぶ際に意味のある `held` を渡しているなら、batch collect はその保護を欠いていることになる。
- 再現手順: (不明な内部実装に依存するため確証はできないが) collect の走査中に対象チャンクが並行して purge 対象になった場合、`held` が空のため保護なしにベクタが書き込まれ、purge との競合（監査観点3）を招く可能性がある。
- 影響: 監査観点3「purge との競合」に該当し得る。ただし `held` の実際の意味論が target.md からは不明のため、確度は限定的。
- 提案: `held` パラメータの意味論を確認し、batch collect でも sync 経路と同等の集合を渡すか、不要なら関数シグネチャ側でこの経路には意味がないことを明文化する。

### R24-son2-5 [minor] repair のプレビュー→確認→本実行の間、`.kio/.lock` の保持範囲が target.md から確認できない
- 対象箇所: target.md 1292-1321行 (`RegistryPrune` / `RebuildDb` 双方の `preview → confirm_repair_prune → 本実行` パターン)。近傍の1289-1291行コメントは `kio batch abandon` については「`run_batch` が既に取得済みの `.kio/.lock` の内側で動く」と明記しているが、repair 側の同種のパターンにはロックの記載が無い。
- 根拠: `confirm_repair_prune` はユーザー入力待ち（対話プロンプト）でブロックし得る。もしこの待機中に `.kio/.lock` が保持されていなければ、他プロセスの並行実行により dry-run のプレビュー（`preview.pruned_count` 等）と、ユーザーが承認した後に走る本実行 (`registry_prune(false)` / `prune_orphans(false)`) の対象がずれ得る（監査観点6「dry-run と本実行の結果がずれる窓」）。
- 再現手順: (不明。ロック取得箇所が target.md に無いため具体的な手順は構成できない)
- 影響: 確証はないが、もしロックが確認待ち中に外れているなら、ユーザーが承認した件数と実際に削除される件数がずれる可能性がある。
- 提案: `verify_objects::registry_prune` / `prune_orphans` 呼び出しを含む一連の処理全体が単一の `.kio/.lock` 保持区間内にあることを実装/ドキュメントで確認・明記する。

### R24-son2-6 [minor] `active_embedding_send_lane()` のドキュメンテーションコメントが陳腐化している
- 対象箇所: target.md 1087-1098行（§4）と、既に driver が着地済みであることを示す §3/§5 (614-1201行)。
- 根拠: §4 のコメントは「embedding Batch driver (submit + `kio batch resume` poll/collect) はまだ着地していない」「driver が着地する変更で `effective_invocation_lane()` に置き換わる」と書かれているが、§3 で `submit_embedding_batch_jobs` / `poll_batch_embedding_jobs` が既に実装され、§5 で `effective_invocation_lane() == PreferredRequestKind::Batch` によるバッチ経路への分岐が現に存在する。つまり driver は既に着地しているのに、コメントは着地前の状態を記述したままである。
- 再現手順: N/A（ドキュメント不整合）。
- 影響: 実害は無い（実際の呼び出しは Sync 専用経路からのみで、現状の動作自体は正しい）が、将来の保守者が「driver は未着地」と誤読するおそれがある。
- 提案: コメントを更新し、`active_embedding_send_lane()` が「レーン不明時のフォールバックおよび `--realtime` 用の固定 Sync 単価」である旨に書き直す。

### R24-son2-7 [minor] target.md 内にコードの重複貼り付けと思われる箇所がある
- 対象箇所: 616-627行（見出しコメントブロックの二重貼り付け）、1159-1163行（`fn estimate_embedding_cost` の入れ子的な二重定義、`// (estimate_embedding_cost 本体)` というプレースホルダコメント付き）。
- 根拠: どちらも同一テキストの反復・不完全な差し込みであり、そのまま実ソースだとすれば型不整合等でコンパイルが通らない形をしている。監査対象の抜粋作成過程のアーティファクトである可能性が高い。
- 再現手順: N/A。
- 影響: 実装そのものへの影響は不明（抜粋アーティファクトの可能性が高い）。監査対象の再提出時にはクリーンな抜粋を用いることを推奨。
- 提案: target.md 作成側で該当箇所の重複を除去する。

### 確認したが問題なしと判断した点
- `--realtime` 指定時は同期レーンのみが使われ `batch_requests` に `batch` 行が一切作られないことがテストで裏付けられている（`realtime_uses_the_synchronous_lane_and_never_creates_a_batch_row`, 1667-1700行）。OCR/embedding を分けて片方だけ即時レーンに倒す経路は見当たらなかった。
- クラッシュや再実行を伴わない通常の再投入では、同一メンバ集合は同一 task key (`embedding_job_input_hash`) に落ち、2回目のジョブ作成が起きないことがテストで確認されている（`resubmitting_the_same_member_set_reuses_the_row_and_creates_no_second_job`, 1705-1731行）。「1 job = 1 task」の基本形は守られている。
- クエリ埋め込み用レーン (`query_embedding_send_lane`) は常に Sync 固定であり、「検索は batch の turnaround を待てない」という規範（71-72行）と一致している。
- 埋め込みレーンの終端処理はすべて（成功・失敗いずれも）`clear_intent_token=true` で `intent_token` をクリアしており、「inline レーンは残骸を作らないので終端＝掃除完了」という §5.8/§5.4 特例の解釈が実装（`settle_batch_charge_terminal` の両呼び出し箇所）と整合している。
- collect 時に投入済みメンバの一覧を信用せず「現在のチャンク集合から再導出する」設計（959-969行）により、投入後に**追加**された同一内容チャンクが正しく結果を受け取れる点は、メンバ集合変化への対応として妥当に設計されている（一方で representative 消失方向の欠落は R24-son2-3 で別途指摘）。
