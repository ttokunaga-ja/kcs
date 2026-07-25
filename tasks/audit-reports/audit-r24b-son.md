読了行数: 677
最終2行:
```
}
```
判定: 条件付き合格

### R24b-son-1 [major] registry-prune はロック無しで preview→確認→実行が非アトミック
- 対象箇所: §2 `run_repair` の `RepairOperation::RegistryPrune` 分岐 (main.rs 82-87行相当)、および §6 `registry_prune`
- 根拠: `verify-objects --prune-orphans` 経路では `let _lock = repo.lock_store()?;` を取得した**後**に preview→確認→実行の一連を行っている（`run_repair` 内で `_lock` 取得は99行目相当、prune分岐は127行目以降）。一方 `RegistryPrune` 分岐は `Repository::open` すら呼ばず、`_lock` を一切取得しないまま `registry_prune(true)`（preview）→ `confirm_repair_prune`（対話待ちでブロックし得る）→ `registry_prune(false)`（実行）を行う。`registry_prune` 自身は呼び出しごとに `entry.root_path` の到達可能性を独立に再計算するため、preview時点の `pruned_count` と実行時点で実際に削除される件数が、確認待ちの間に他プロセスがレジストリを変更すれば食い違い得る。06 §1「削除対象を先に列挙して見せてから問う」は、見せた集合と消す集合の一致を前提にした規範であり、ここではその前提が保証されていない。
- 再現手順: (1) `kio repair registry-prune` を対話モードで起動し確認プロンプトで待機させる。(2) その間に別プロセスが `kio init`/`kio index` 等でレジストリを更新し、新たに到達不能なエントリを追加する（あるいは既存の到達不能エントリが到達可能になる）。(3) ユーザーがプロンプトに `y` で応答すると、表示された件数とは異なる集合が削除される。
- 影響: ユーザーが同意した内容（表示件数）と実際に削除される対象が一致しない。ユーザーが見ていない項目が削除される、または見た項目が削除されない、という「同意の実質的な破綻」が起きる。
- 提案: `RegistryPrune` 分岐でもレジストリに対するロック（あるいは `RegistryDb` 自体のファイルロック）を確認プロンプトの前後で保持するか、preview で収集した具体的なキー集合を実行側に引き渡し、実行時はその集合のみを対象にする（再列挙しない）よう変更する。

### R24b-son-2 [major] 確認プロンプトが「列挙」ではなく合計件数のみを表示している
- 対象箇所: §4 `confirm_repair_prune` (`"repair {what}: {count} item(s) will be permanently removed. Proceed?"`)、および呼び出し元 §2 (127-142行相当、`preview.pruned_prepared_count + preview.pruned_image_count + preview.pruned_open_cache_count` の合算)
- 根拠: 規範は「削除対象を**先に列挙して見せてから**問う」と明記している（audit-prompt.md 10行目、target.md 9行目）。しかし実装が表示するのは単一の合計数 `count` のみであり、`verify-objects --prune-orphans` では prepared/image/cache の内訳さえプロンプト文面には現れず（呼び出し元で3つを合算してから渡している）、対象のハッシュやパスといった具体的な列挙は一切行われない。`registry-prune` も同様に `pruned_count` という数のみ。「列挙して見せる」という規範上の要求と「件数だけ見せる」という実装は明確に異なる。
- 再現手順: `kio repair verify-objects --prune-orphans` を対話実行し、表示される文言を確認する。「N item(s) will be permanently removed」以外の情報（対象のハッシュ、パス、種別ごとの内訳)は表示されない。
- 影響: ユーザーは何が消えるかを具体的に確認できないまま同意させられる。誤って重要なオブジェクトを消す判断をしてしまうリスクが高まり、「先に列挙して見せる」という規範の趣旨（誤削除の事前検知）が実現されていない。
- 提案: `PruneOrphansReport`/`RegistryPruneReport` に削除対象の識別子リスト（ハッシュ・パス等）を保持するフィールドを追加し、`confirm_repair_prune` （または専用の表示関数）でその一覧を表示してから確認を取る。少なくとも種別ごとの内訳（prepared/image/cache）は文面に含めるべき。

### R24b-son-3 [major] prune_orphans の内部ブロック時に __exit_code はあるが error_code が付かない
- 対象箇所: §2 `run_repair` 144-153行相当（`if prune.status == "blocked" { object.insert("__exit_code".to_owned(), json!(3)); }`）と、対比対象の111-122行相当（`has_findings` 分岐は `error_code` と `__exit_code` の両方を挿入）
- 根拠: `prune_orphans` は自身の内部で `active_purge_journal` / `non_terminal_task` / `ref_inventory_unsafe` の3条件により独立に `"blocked"` を返せる（§5）。verify 自体に findings が無く（＝has_findings分岐を通らず）、かつ verify 通過後の `prune_orphans` 呼び出しがこれら3条件のいずれかで blocked になった場合、`run_repair` は `__exit_code: 3` のみを挿入し `error_code` は一切設定しない。同じ「exit 3」を返すもう一方の経路（has_findings）は `error_code`（`KIO-E-PURGE-INCOMPLETE-001` または `KIO-E-STORE-CORRUPT-001`）を必ず設定しており、両者の整合が取れていない。監査観点4は「拒否・blocked・findings有りの各経路で `__exit_code` と `error_code` が正しく載るか」を明示的に問うており、これはその不整合そのものである。
- 再現手順: verify がクリーンに通る状態で、かつ `non_terminal_task`（Pending/Runningなタスクが残っている）または `ref_inventory_unsafe`（root_stateのexceeded_bounds/findings）条件を成立させたうえで `kio repair verify-objects --prune-orphans --yes` を実行する。JSON出力の `__exit_code` は3だが `error_code` フィールドが存在しない。
- 影響: exit code のみで機械的にエラー種別を判別したいクライアント／自動化スクリプトが、この経路だけ `error_code` を参照できず、他の exit 3 経路と扱いを揃えられない。
- 提案: `prune.status == "blocked"` 分岐でも `blocked_by` の値に応じた `error_code`（例: `KIO-E-PRUNE-BLOCKED-001` 等）を挿入し、`has_findings` 分岐と同じ形の契約に揃える。

### R24b-son-4 [major] registry-prune の「拒否時に何も削除しない」契約を検証するテストが無い
- 対象箇所: §7 契約テスト全体、特に `repair_prune_requires_confirmation_and_refuses_without_deleting`
- 根拠: 06 §1 は `verify-objects --prune-orphans` と `registry-prune` の**両方**に対して「非対話で `--yes` 無しは拒否し、何も削除しない」ことを要求している（target.md 10-11行）。しかし §7 に列挙された契約テストの中で、非対話拒否＋削除ゼロを実際に検証しているのは `verify-objects --prune-orphans` のみ（`repair_prune_requires_confirmation_and_refuses_without_deleting`）であり、`registry-prune` に対する同種のテスト（非対話で `--yes` 無し→exit 9→レジストリの内容が変化していないことの確認）は target.md 内に一つも存在しない。監査観点6「通っているが穴を見逃しているテスト」に直接該当する。コード自体は `!dry_run` ガードにより安全に見える（§6参照）が、それを保証するテストが欠落している。
- 再現手順: `step4b_p2b_contract.rs` の全テスト一覧（§7）を確認する。`registry-prune` を対象とした確認拒否テストが存在しないことが分かる。
- 影響: 将来 `registry_prune` のロジックが変更されて拒否時にも削除が起きるリグレッションが混入しても、既存テストでは検知できない。
- 提案: `repair_prune_requires_confirmation_and_refuses_without_deleting` と同型のテストを `registry-prune` にも追加し、非対話・`--yes`無しでの拒否（exit 9, `KIO-E-CONFIRM-REJECTED-001`）と、レジストリの対象エントリが依然存在すること（`registry.all_entries()` 等で確認）をアサートする。

### R24b-son-5 [minor] `yes: bool` への `requires = "prune_orphans"` が実効性を持たない可能性
- 対象箇所: §1 `RepairVerifyObjectsArgs` の `#[arg(long, requires = "prune_orphans")] yes: bool`
- 根拠: `prune_orphans`・`yes` はいずれも素の `bool` フィールドで `ArgAction::SetTrue`（既定値 `false`）として展開される。clapのこの種のフラグは既定値を持つため、`--prune-orphans` を渡していなくても matches 上「存在する」と扱われ、`requires` 制約が実効性を失う場合があることが知られている。target.md には clap のバージョンやカスタム設定は示されておらず、実際にこの版で機能するかは確認できない（不明）。
- 再現手順: （不明・target.md 内のコードのみからは実行結果を確定できない）`kio repair verify-objects --yes`（`--prune-orphans` 無し）を実行し、clapレベルのパースエラーになるか、`prune_orphans=false, yes=true` として素通りするかを確認する必要がある。
- 影響: 仮に `requires` が効かず素通りしたとしても、`parsed_repair`（§3）は `verify.prune_orphans` が `false` である限り `RepairMode::VerifyObjects`（prune無し通常経路）になり、`--yes` は単に未使用のまま無害に終わる。データ削除やプロンプト回避には結びつかない。
- 提案: `--prune-orphans` 無しで `--yes` を渡すケースをテストに追加し、clapが期待通りエラーにするか（あるいは無害な素通りになるか）を明示的に固定する。実効性が無いことが判明した場合は、`requires` に依存せず `run_repair` 側で明示チェックする形に変更する。

### 確認したが問題なしと判断した点
- `prune_orphans`（§5）の prepared/image オブジェクト削除ループは `dry_run || store.remove_content(...)` という `||` 短絡評価により、`dry_run=true` のときは `remove_content` が一度も呼ばれない。オープンキャッシュ削除も `if !dry_run { fs::remove_dir_all... }` および `dry_run || fs::remove_dir_all(...).is_ok()` で同様に保護されており、行単位で確認した限り dry-run 経路に副作用は無い。
- `registry_prune`（§6）も `if !dry_run { registry.remove(...) }` で削除処理を明確に囲っており、`dry_run=true` では `registry.remove` が呼ばれない。
- `run_repair`（§2）は verify に `remaining_findings` がある場合、`mode` が `VerifyObjectsPruneOrphans` であっても必ず `prune_orphans` 呼び出しに到達する前に `return Ok(output)` しており、PB15「壊れた store の上で刈らない」は構造的に守られている。
- `verify-objects --prune-orphans` の拒否経路は `confirm_repair_prune(...)?` の `?` により即時 `Err` として関数を抜け、後続の `prune_orphans(&repo, false)` 呼び出し（実削除）には到達しない。この挙動は `repair_prune_requires_confirmation_and_refuses_without_deleting` テストで、拒否後に対象オブジェクトがまだ store に存在することまで含めて明示的に検証されている。
- `confirm_repair_prune` の `count == 0 || yes` の早期 `Ok(())` は、`--yes` の有無に関わらず対象0件なら即成功・プロンプト無しとなり、「対象0件はプロンプト無しの冪等成功」の規範と整合している。
