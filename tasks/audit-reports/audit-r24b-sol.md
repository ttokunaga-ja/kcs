読了行数: 677
最終2行: }
```
判定: 不合格

### R24b-sol-1 [fatal] preview と本実行が別集合を走査し、未確認対象まで削除する

- 対象箇所: §2 `run_repair` / `registry_prune(true)`・`registry_prune(false)`、`prune_orphans(&repo, true)`・`prune_orphans(&repo, false)`
- 根拠: 確認前後で削除対象を再走査しており、preview の集合を本実行へ固定していない。特に対話プロンプト中は状態変更のための長い窓が開く。対象 0 件でも本実行を再走査するため、その間に生じた対象を無確認で削除し得る。
- 再現手順: 到達不能 registry 行 A がある状態で `repair registry-prune` を対話実行する。件数 1 のプロンプト待機中に別プロセスから到達不能行 B を追加し、`yes` と答える。本実行は A と B を再走査して両方を削除する。
- 影響: preview 時に存在しなかった registry 行や CAS/cache オブジェクトが、ユーザーの承諾なしに失われる。
- 提案: preview で対象の識別子を含む削除計画を生成し、本実行ではその計画だけを処理する。集合が変化した場合は中止して再列挙・再確認する。registry はトランザクションまたは適切なロックで保護し、空の計画では再走査しない。

### R24b-sol-2 [fatal] blocked preview 後も確認なしで破壊的な本実行へ進む

- 対象箇所: §2 `run_repair` / `if preview.status != "blocked" { confirm_repair_prune(...) }` の直後にある `prune_orphans(&repo, false)?`
- 根拠: preview が `blocked` の場合は確認を省略する一方、処理を終了せず本実行を呼ぶ。2 回目までに blocker が解消すると、本実行は削除を行う。非対話・`--yes` 無しでも `KIO-E-CONFIRM-REJECTED-001` を経由しない。
- 再現手順: orphan と `Running` の task を用意して非対話で `repair verify-objects --prune-orphans` を開始する。preview が `non_terminal_task` で blocked になった直後、task を terminal に遷移させる。2 回目の走査は blocker がないため orphan を削除する。
- 影響: 一度も確認されていない対象が削除され、非対話時は「1 バイトも削除しない」という規範にも違反する。
- 提案: preview が blocked なら、その report を出力へ格納して exit 3 で直ちに return し、`dry_run=false` を絶対に呼ばない。

### R24b-sol-3 [major] 削除対象を列挙せず件数だけで確認している

- 対象箇所: §4 `confirm_repair_prune` / `"repair {what}: {count} item(s)..."`、§5・§6 の preview report
- 根拠: preview report が保持するのは件数だけであり、確認前に対象のハッシュ、パス、registry キー等を表示する処理がない。「削除対象を先に列挙して見せてから問う」という 06 §1 の明示的要件を満たさない。
- 再現手順: orphan または到達不能 registry 行を作り、TTY から対象コマンドを `--yes` 無しで実行する。stderr に出るのは総件数だけで、対象の識別情報は表示されない。
- 影響: ユーザーは何が消えるか確認できず、誤った対象を含む場合にも判断できない。
- 提案: preview report に対象種別と安定した識別子の一覧を含め、それを stderr に全件表示してからプロンプトを出す。その一覧を R24b-sol-1 の削除計画として再利用する。

### R24b-sol-4 [major] reachability 読み取り失敗を無視し、参照中オブジェクトを orphan 扱いする

- 対象箇所: §5 `prune_orphans` / `if let Ok(tree) = repo.read_tree(...)` および `let Ok(instance) = load_validated_normalized_instance(...) else { continue; };`
- 根拠: tree または normalized instance を読めない場合、その entry の prepared/image 参照を live 集合へ追加できないまま処理を続ける。その後、live 集合にない全 inventory を削除するため、コメントにある「cannot prove orphan-ness」という fail-closed 動作と逆になる。
- 再現手順: clean verify 完了後、prune の reachability 走査前に、prepared/image を参照する normalized instance を unreadable または不正な状態にする。走査は `continue` し、その参照先が他で使われていなければ削除候補になる。
- 影響: 実際には live な prepared/image オブジェクトを削除し、store を破損させ得る。
- 提案: tree、normalized instance、参照抽出のいずれかに失敗した時点で report を `blocked` にして、削除フェーズへ進まない。少なくとも「不明」を orphan として扱わない。

### R24b-sol-5 [major] `verify-objects --yes` 単独を clap の `requires` が拒否できない

- 対象箇所: §1 `RepairVerifyObjectsArgs` / `#[arg(long, requires = "prune_orphans")] yes: bool`
- 根拠: `prune_orphans: bool` は `ArgAction::SetTrue` の既定値 `false` を持つため、clap の存在判定上は値が存在し、`requires` の充足に使われ得る。この形では `--yes` が明示されたのに `--prune-orphans` がないケースを確実に排除できない。
- 再現手順: `kio repair verify-objects --yes --json` を実行する。期待される clap exit 2 ではなく通常の verify として受理され得る。§7 の `pb12_prune_orphans_flag_parsing` はこの組み合わせを試していない。
- 影響: `--yes` が効くべきでない非破壊モードで受理され、CLI 契約と利用者の認識がずれる。
- 提案: parse 後に `yes && !prune_orphans` を明示検証して clap 相当の usage error にするか、真偽値を条件にする clap predicate／構造へ変更する。

### R24b-sol-6 [major] prune blocked の JSON に `error_code` がない

- 対象箇所: §2 `run_repair` / `if prune.status == "blocked" { object.insert("__exit_code", json!(3)); }`
- 根拠: blocked 経路では `__exit_code` だけを挿入し、トップレベルの `error_code` を設定していない。verify findings 経路では両方を設定しており、同じ exit 3 の JSON が経路によって分類不能になる。
- 再現手順: clean verify は通るが `prune_orphans` が `non_terminal_task` で blocked になる状態を作り、`--yes` 付きで実行する。出力には `__exit_code: 3` と `blocked_by` がある一方、`error_code` がない。
- 影響: JSON クライアントが終了理由を安定して判別できず、blocked を成功または未知の失敗として扱う。
- 提案: blocked 用の定義済み `error_code` を必ずトップレベルへ設定する。未定義なら専用コードを定義し、`blocked_by` は詳細コンテキストとして維持する。

### R24b-sol-7 [minor] 契約テストが主要な確認経路を網羅していない

- 対象箇所: §7 契約テスト
- 根拠: registry-prune の拒否・非削除、対象 0 件、`verify-objects --yes` 単独、image/open-cache の拒否時非削除、blocked preview 後に本実行しないことを検証していない。PB15 テストは verify の早期 return で終わるため、`prune_orphans` 自身の blocked 分岐には到達しない。
- 再現手順: `--yes` 単独を受理する、registry dry-run で削除する、または blocked preview 後に本実行する実装へ変更しても、掲載されたテストは通過し得る。
- 影響: 破壊的操作の重要な契約違反が回帰テストで検出されない。
- 提案: 両コマンドについて拒否時の全対象不変、空集合成功、flag の不正組合せ、blocked の早期終了、preview と実行の間に状態を変更する決定的なテストを追加する。

### 確認したが問題なしと判断した点

- `prune_orphans(repo, true)` の掲載コードでは、prepared/image の `remove_content` は `dry_run || ...` の短絡評価で呼ばれず、raw cache と image cache の削除も `dry_run` で明示的に抑止されている。
- `registry_prune(true)` は `registry.remove(...)` を `if !dry_run` 内に限定しており、掲載範囲内に preview 自体の削除処理はない。
- preview 件数が安定して 1 件以上ある非対話経路では、`confirm_repair_prune` が `KIO-E-CONFIRM-REJECTED-001` と `ExitCode::ConfirmationRejected` を返し、本実行へ到達しない。
- 対象件数が安定して 0 件なら `confirm_repair_prune` はプロンプトを出さず成功する。
- verify に findings がある場合は prune 前に return し、`purge_incomplete` とその他の破損を区別した `error_code` と `__exit_code: 3` を設定している。
- `registry-prune` は `Repository::open_current_without_head_repair()` より前に分岐しており、device-global 操作に CWD 内の scope を要求していない。