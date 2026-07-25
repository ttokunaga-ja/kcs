読了行数: 677
最終2行: <code>}</code><br><code>```</code>
判定: 不合格

### R24b-terra-001 [fatal] `prune-orphans` のプレビュー結果が実削除を拘束していない

- 対象箇所: §2 `run_repair` の `prune_orphans(&repo, true)` → `prune_orphans(&repo, false)`、§4 の `if count == 0 || yes`。
- 根拠: preview の対象集合を保持せず、実行時に再走査している。0 件なら非対話確認前に通過し、`blocked` でも確認を省略したまま実削除を呼ぶ。状態変化後の実行では別集合を削除できる。
- 再現手順: clean な検証時には参照済みの prepared object を用意する。preview 後・実行前に対応する normalized instance を壊すと、§5 の `load_validated_normalized_instance` は `continue` し、prepared hash を live 集合へ入れない。非対話・`--yes` 無しでも preview が 0 件なら、その prepared object を実行側が削除する。
- 影響: 承諾も `--yes` もない状態でデータを削除し、PB15 と非対話拒否契約に反する。
- 提案: preview でハッシュ・種別・パスを含む削除計画を固定し、確認後はその計画だけを再検証して削除する。0 件・`blocked` は実削除を呼ばず即時 return する。

### R24b-terra-002 [fatal] `registry-prune` が確認後に未表示の registry 行を追加削除できる

- 対象箇所: §2 の `RegistryPrune` 分岐、§6 `registry_prune`。
- 根拠: preview は `pruned_count` だけを返し、実行は再度 `all_entries()` と `open_scope_from_hint()` を評価する。registry 全体を preview から削除まで固定する計画・トランザクションはない。
- 再現手順: 到達不能な行 A と到達可能な行 B を用意し、対話プロンプトが「1 item」と表示された後に B の scope を到達不能にして `y` を入力する。実行側は A と B を削除する。preview 0 件なら、非対話でも同じ隙間で追加された行を無確認で削除できる。
- 影響: device-global な registry 行が、ユーザーに表示・承諾されていない対象まで削除される。
- 提案: CWD 非依存のまま registry 専用の排他／トランザクションを使い、`(scope_id, kio_path)` の固定リストを表示して、そのリストだけを削除する。差分発生時は再 preview・再確認する。

### R24b-terra-003 [major] 確認プロンプトが削除対象を列挙していない

- 対象箇所: §4 `confirm_repair_prune`、§5 `PruneOrphansReport`、§6 `RegistryPruneReport`。
- 根拠: プロンプトの入力は `what` と `count` のみで、表示も `"{count} item(s)"` のみである。object hash、cache path、registry の scope ID／パスはいずれも表示されない。
- 再現手順: 複数の orphan object または複数の到達不能 registry 行を作り、対話実行する。表示されるのは件数だけで、削除対象を識別できない。
- 影響: 06 §1 の「削除対象を先に列挙して見せてから問う」に違反し、ユーザーは何を消すか判断できない。
- 提案: preview report に対象一覧を含め、種別・hash・path／scope ID を確認前に表示する。

### R24b-terra-004 [major] `--yes` 単独を `requires` が確実に拒否できない

- 対象箇所: §1 `#[arg(long, requires = "prune_orphans")] yes: bool`、§3 `parsed_repair`、§7 `pb12_prune_orphans_flag_parsing`。
- 根拠: `bool` は `ArgAction::SetTrue` と既定値 `false` を持つため、`requires` の存在判定が `prune_orphans` を常に存在扱いにし得る。さらに実行時の明示検証はなく、`yes` は prune mode 時だけ参照される。
- 再現手順: clean な scope で `kio repair verify-objects --yes` を実行する。本来 parser error であるべきところ、通常 verify として成功し、`--yes` は無意味に受理される。
- 影響: 誤った自動化が成功扱いとなり、`--yes` の適用範囲契約を破る。
- 提案: parse 後に `yes && !prune_orphans` を明示的に error にする。`--yes` 単独が exit 2 になる契約テストを追加する。

### R24b-terra-005 [major] blocked 時の JSON が exit code と `error_code` で整合しない

- 対象箇所: §2 の `if prune.status == "blocked"`。
- 根拠: blocked 時は `__exit_code: 3` だけを追加し、`error_code` を設定しない。clean verify の output を流用するため、トップレベルは成功形のまま非ゼロ exit になり得る。
- 再現手順: verify が clean で、`prune_orphans` だけが `non_terminal_task` などにより blocked となる状態で `--prune-orphans --yes` を実行する。
- 影響: JSON 利用者が標準の `error_code` で失敗理由を判定できず、成功 status と exit 3 が矛盾する。
- 提案: blocked reason に対応する `error_code` と一貫した status を設定し、`__exit_code` と組でテストする。

### R24b-terra-006 [major] 契約テストが registry と確認プロンプトの安全契約を守っていない

- 対象箇所: §7 の全テスト。
- 根拠: `registry-prune` を呼ぶテストがなく、対象列挙、interactive confirm、preview 後の対象変化、`--yes` 単独、blocked JSON のいずれも検証していない。PB15 テストも verify の早期 return を確認するだけで prune blocked 分岐に到達しない。
- 再現手順: 現在のテスト群を実行しても、`registry-prune` の確認呼出しを欠落させた変更や件数のみのプロンプトは検出されない。
- 影響: 必須の破壊的操作に対する安全契約が将来容易に退行する。
- 提案: registry の拒否・`--yes`・0 件・CWD 外実行、対象一覧、固定削除計画、blocked JSON、`--yes` 単独拒否を含む契約テストを追加する。

### 確認したが問題なしと判断した点

- §5・§6 で示された直接の削除呼出しは、`dry_run=true` 時には `remove_content`、`remove_dir_all`、`registry.remove` を実行しない分岐になっている。
- §2 は verify の remaining findings がある場合、prune 前に return しており、通常の壊れた store 上での prune を防いでいる。
- 安定した非 0 件・非 blocked の preview では、非対話かつ `--yes` 無しは `KIO-E-CONFIRM-REJECTED-001` を返してから実削除へ進まない。
- `registry-prune` は `Repository::open_current_without_head_repair()` より前に処理されており、CWD が scope 内であることを要求しない。