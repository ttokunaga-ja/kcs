# 公開前後方互換分岐の撤去 — 実装監査計画

**方針の正本は [docs/10-operations.md §12.5](../docs/10-operations.md)。**
これは docs-only scan ではなく、Phase 3 の implementation audit 用 ledger である。このファイルは
実装・fixture・test が削除済みであることを主張しない。各 bundle は production path、旧 fixture / test、
current-format の置換 test を同じ変更で確認して初めて完了にする。

## Status

| 状態 | 意味 |
|---|---|
| `未監査` | docs の矛盾を解いたが `crates/` と test の call path は未確認 |
| `実装監査中` | production / fixture / test / CI の参照を列挙中 |
| `撤去可能` | 下記 precondition と置換契約を満たす実装 bundle がレビュー可能 |
| `完了` | production branch・旧 fixture/test を除去し、置換 test が通ったことを確認済み |

現状: **全項目 `実装監査中`。docs-only 更新済み。共有 worktree の未コミット実装は完了の証拠ではなく、コード削除・fixture/test の置換・validation は未完了。**

## 撤去 bundle と完了 precondition

| # | 対象 | 現状 | 実装監査で確認すること | 撤去後の必須契約 |
|---:|---|---|---|---|
| 1 | derived SQLite の旧 schema / `ALTER TABLE` / missing `context_key` | 実装監査中 | startup、repair、fixture、static test の旧 shape reader | fresh / missing DB は current schema で初期化。既存 incompatible DB は fingerprint gate で書込み前に検出し、無変更で `repair rebuild-db` を案内 |
| 2 | pre-object-store SQLite snapshot と旧 DB source | 実装監査中 | rebuild-db の source 選択、old-row fixture、history test | historical cache は current commit / tree / CAS から再構築。欠落 object は history を黙って落とさず corruption / shallow state で fail-closed |
| 3 | missing / legacy `kio_format_version` と current object の missing field default | 実装監査中 | scope loader、tree / pointer / normalized object reader、test vectors | current version と required fields は strict reject。自己より新しい version のみ read-only で維持 |
| 4 | legacy tree/path、raw-name ref、CAS colon/raw leaf fallback | 実装監査中 | resolver、fsck、restore、Windows fixture、canonical/legacy conflict test | canonical digest-only physical name のみ。Windows / non-Windows の canonical write/read/hash mismatch test と Unicode portability test は維持 |
| 5 | lifecycle event の missing `epoch` を 0 と読む分岐 | 実装監査中 | lifecycle parser、repair、event fixture | malformed current event は reject。counter file の欠落・torn-write recovery は current corruption recovery として維持 |
| 6 | cost-ledger JSONL importer、`.migrated` rename、**JSONL cutover** marker / 推測 backfill | 実装監査中 | startup、DDL fingerprint、recovery、JSONL fixture、migration test | ledger bytes と audit / intent truth を保存。old / incompatible ledger は ALTER・rename・import せず actionable error で fail-closed。current operational `schema_migrations` marker と current-schema crash recovery は維持 |
| 7 | approval / task / normalized object の missing field fallback | 実装監査中 | schema loader、cleanup/reservation、normalized-unit `metadata`、fixture、test | current schema に required な field は reject。normalized-unit の `metadata` は required object（空 `{}` は有効、field 全体の欠落は reject）。`approval_pending` 全体の absence は有効だが、存在する malformed pending は fail-closed。適用可能な current task field だけを required 化し、推測 default は置かない |

## 実装監査の手順

1. 各 bundle ごとに production symbol、すべての caller、fixture、unit / integration / static test、CI job を列挙する。
2. 旧 development data を読むだけの branch と、future-version read-only・current corruption recovery・Windows / Unicode portability を分離する。
3. production branch、旧 fixture、旧 behavior test を同一 change で削除する。テストだけの削除は禁止する。
4. 上表の置換契約を test 化する。derived cache は fresh / incompatible / history rebuild、ledger は byte-preserving fail-closed を含める。
5. targeted test と関連する broader validation を実行し、diff review 後に status を更新する。

## 除外（撤去しない契約）

- 自己より新しい `kio_format_version` を read-only で扱う future-version compatibility。
- current-format の purge / lifecycle counter、torn write、provider crash の corruption recovery。
- canonical digest-only physical naming、Unicode NFC / case folding、Windows portability。
- current commit/tree/CAS による historical cache rebuild と `--at` / `--all-history` / Evidence Pointer の可視性。

関連する docs-only reconciliation は [03-data-model.md §2 / §3 / §8](../docs/03-data-model.md)、
[04-pipeline.md §5.7](../docs/04-pipeline.md)、および
[10-operations.md §7.5.3 / §12.5](../docs/10-operations.md) にある。
