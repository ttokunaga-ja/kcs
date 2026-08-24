# 公開前後方互換分岐の撤去 — 完了監査 ledger

**方針の正本は [docs/10-operations.md §11.5](../docs/10-operations.md)。**
これは docs-only scan ではなく、完了した implementation audit の ledger である。各 bundle は
production path、旧 fixture / test、current-format の置換 test を同じ変更で確認して完了した。

## Status

| 状態 | 意味 |
|---|---|
| `未監査` | docs の矛盾を解いたが `crates/` と test の call path は未確認 |
| `実装監査中` | production / fixture / test / CI の参照を列挙中 |
| `撤去可能` | 下記 precondition と置換契約を満たす実装 bundle がレビュー可能 |
| `完了` | production branch・旧 fixture/test を除去し、置換 test が通ったことを確認済み |

現状: **bundle 1〜7 は production branch・旧 fixture/test の撤去、置換テスト、関連 validation まで完了。**

## 撤去 bundle と完了 precondition

| # | 対象 | 現状 | 実装監査で確認すること | 撤去後の必須契約 |
|---:|---|---|---|---|
| 1 | derived SQLite の旧 schema / `ALTER TABLE` / missing `context_key` | 完了 | startup、repair、fixture、static test の旧 shape reader | fresh / missing DB は current schema で初期化。既存 incompatible DB は fingerprint gate で書込み前に検出し、無変更で `repair rebuild-db` を案内 |
| 2 | pre-object-store SQLite snapshot と旧 DB source、mutable normalized unit body を history source にする分岐 | 完了 | rebuild-db の source 選択、old-row fixture、history test、manifest → unit_object_hash CAS closure | historical cache は current commit / tree / manifest CAS → unit_object_hash CAS から再構築。missing / old unit-object field は history を黙って落とさず corruption / shallow state で fail-closed |
| 3 | missing / legacy `kio_format_version` と current object の missing field default | 完了 | scope loader、tree / pointer / normalized object reader、test vectors | `KIO_FORMAT_VERSION` と完全一致する current version と required fields だけを受理する。missing / non-string / malformed / older / newer / unknown は全 command で strict reject |
| 4 | legacy tree/path、raw-name ref、CAS colon/raw leaf fallback | 完了 | resolver、fsck、restore、Windows fixture、canonical/noncanonical or conflicting representation rejection test | canonical digest-only physical name のみ。Windows / non-Windows の canonical write/read/hash mismatch test と Unicode portability test は維持 |
| 5 | lifecycle event の missing `epoch` を 0 と読む分岐 | 完了 | lifecycle parser、repair、event fixture | malformed current event は reject。counter file の欠落・torn-write recovery は current corruption recovery として維持 |
| 6 | cost-ledger JSONL importer、`.migrated` rename、**JSONL cutover** marker / 推測 backfill | 完了 | startup、DDL fingerprint、recovery、JSONL fixture、migration test | ledger bytes と audit / intent truth を保存。old / incompatible ledger は ALTER・rename・import せず actionable error で fail-closed。current operational `schema_migrations` marker と current-schema crash recovery は維持 |
| 7 | approval / task / normalized object の missing field fallback | 完了 | schema loader、cleanup/reservation、normalized-unit `metadata` / `unit_object_hash`、fixture、test | current schema に required な field は reject。normalized-unit の `metadata` は required object（空 `{}` は有効、field 全体の欠落は reject）。Done manifest entry は non-null `unit_object_hash`、failed entry は explicit null が必須で、missing / default / migration reader は置かない。`approval_pending` 全体の absence は有効だが、存在する malformed pending は fail-closed。TaskDescriptor は nullable field も key を必須にし、online bbox policy・paused hold reason・reservation triple を append/read 双方で検証する。推測 default は置かない |

## 完了時に確認した手順

1. 各 bundle ごとに production symbol、すべての caller、fixture、unit / integration / static test、CI job を列挙する。
2. 旧 development data を読む branch と、current corruption recovery・Windows / Unicode portability を分離する。format-version 不一致は全て strict reject とする。
3. production branch、旧 fixture、旧 behavior test を同一 change で削除する。テストだけの削除は禁止する。
4. 上表の置換契約を test 化する。derived cache は fresh / incompatible / history rebuild、ledger は byte-preserving fail-closed を含める。
5. targeted test と関連する broader validation を実行し、diff review 後に status を更新する。

## 除外（撤去しない契約）

- `kio_format_version` の完全一致を要求する fail-closed boundary（互換 reader ではない）。
- current-format の purge / lifecycle counter、torn write、provider crash の corruption recovery。
- canonical digest-only physical naming、Unicode NFC / case folding、Windows portability。
- current commit/tree/manifest CAS → unit_object_hash CAS による historical cache rebuild と `--at` / `--all-history` / Evidence Pointer の可視性。

関連する docs-only reconciliation は [03-data-model.md §2 / §3 / §8](../docs/03-data-model.md)、
[04-pipeline.md §5.7](../docs/04-pipeline.md)、および
[10-operations.md §7.5.3 / §11.5](../docs/10-operations.md) にある。
