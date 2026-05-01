# プロダクト化に向けた追記メモ

この文書は、既存の正本方針を変更するものではなく、実装・UI・運用へ落とすときに問題になりやすい点を補足する。

MVP は、検索体験を削った薄いデモではなく、KCS の基本機能を一通り実装した最小の完全系として扱う。この方針は維持する。

---

# 1. 初回スキャン前の承認

KCS はデフォルトで全 indexed scope を検索対象にし、全ファイルを管理対象にする。ただし、初回スキャンでは、対象範囲 preview、除外提案、明示承認を必須にする。

目的はデフォルト全管理を弱めることではない。KCS が単なる検索インデックスではなく、原本を content-addressed object として保存する知識アーカイブであることを、ユーザーが理解したうえで開始するためである。

必須フロー:

```text
kcs init
  ↓
候補 scope を探索
  ↓
対象フォルダ / 推定ファイル数 / 推定容量 / 大容量ファイル / 除外候補を preview
  ↓
.kcsignore / 設定を調整
  ↓
再 preview
  ↓
明示承認
  ↓
raw object 保存、Markdownize、Embedding、index 更新を開始
```

preview では、少なくとも次を表示する。

```text
root path
included scopes
excluded scopes
estimated file count
estimated total bytes
large files
hidden directories
build/cache/vendor candidates
network transmission policy
adapter execution mode
```

除外候補は提案であり、ユーザーの承認なしに自動除外しない。

```text
Suggested exclusions:
  node_modules/     build/cache candidate
  target/           build output candidate
  .git/             VCS internal metadata
  *.tmp             temporary file
  *.cache           cache file
  video.mp4         large file: 8.2GB
```

非対話環境では、承認済み scope または `--yes` / `--approve` のような明示オプションがない限り、`kcs index` は失敗させる。

承認記録には、少なくとも次を残す。

```text
scope_id
root_path
approved_at
actor
kcs_version
effective_ignore_hash
estimated_file_count
estimated_total_bytes
```

---

# 2. 容量より利便性を優先する

KCS は、容量効率よりも知識を失わないこと、あとから検索・履歴探索・復元できることを優先する。

したがって、全ファイル管理をデフォルトとする方針は維持する。動画・巨大PDF・画像・Officeファイルも、ユーザーが明示的に ignore しない限り管理対象に含める。

ただし、プロダクトはこの事実を隠してはならない。

```text
KCS は検索インデックスだけでなく、原本ファイルを content-addressed archive に保存します。
同じ内容は重複保存しませんが、初回 index では追加ディスク容量を使用します。
```

必要な表示:

```text
推定追加容量
dedup 後の保存見込み
大容量ファイル一覧
現在の空き容量
ディスク枯渇リスク
除外候補
```

ディスク枯渇が予測される場合、KCS は勝手に対象範囲を狭めない。続行、除外、延期、中断をユーザーに選ばせる。

---

# 3. Scope Registry

各 `.kcs` は親と子だけを知り、兄弟や全体を直接管理しない。全体検索は、検索実行側が scope registry または探索済み `.kcs` 一覧を束ねることで実現する。

実装では、device-local な scope registry を明確に持つことを推奨する。

保存先候補:

```text
~/.local/share/kcs/scope-registry.sqlite
```

保存する情報:

```text
scope_id
root_path
kcs_path
folder_id
participates_in_global_search
approved_at
last_seen_at
effective_ignore_hash
permission_status
```

scope registry はデバイスローカルな探索・検索対象管理であり、共有 `.kcs` の正本ではない。フォルダ移動や外部ドライブ切断時は、`folder_id` と `scope.json` を使って再発見または stale 扱いにする。

---

# 4. フォルダごとの `.kcs` 運用

`.kcs` は基本的に各フォルダに生成される。ただし、空フォルダや未到達フォルダへ先回りして作る必要はない。

推奨:

```text
kcs init は現在フォルダの .kcs だけを作る
kcs index は対象ファイルや子scopeを発見した時点で必要な .kcs を作る
空フォルダには .kcs を作らない
履歴やobjectを持たない .kcs は repair / cleanup で整理可能にする
```

実装前に方針を明示すべき境界:

```text
symlink
hardlink
外部ドライブ
クラウドストレージの placeholder file
権限のないフォルダ
hidden directory
system directory
```

---

# 5. 物理レイアウト統一

内部正本は `.kcs/objects/normalized/` に統一する。

過去メモにある `.kcs/normalized/` は、bootstrap 時の簡略表記または仮想表示パスとして扱う。実装・契約ドキュメントでは、hash ベースの object store を正とする。

```text
internal:
  .kcs/objects/normalized/ab/cd/<normalized_hash>.md

virtual view:
  docs/report.pdf.md
```

---

# 6. 検索バックエンド統一

MVP の標準全文検索バックエンドは SQLite FTS5 とする。Vector は sqlite-vec を標準とする。

Tantivy など他の BM25 / full-text backend は将来候補として扱い、採用する場合は ADR で明示する。

```text
MVP:
  MetadataStore = SQLite
  TextSearchBackend = SQLite FTS5
  VectorSearchBackend = sqlite-vec

Future:
  Tantivy
  LanceDB
  Qdrant
  PostgreSQL + pgvector
```

---

# 7. Purge の保証範囲

`purge` は、KCS 管理下の object store、snapshot DAG、index、pack、cache、tombstone から対象ファイル由来の情報を削除する操作である。

ただし、OS backup、Time Machine、クラウド同期の過去版、外部 export、ユーザーが手動コピーしたファイル、KCS 外のログまでは KCS 単体では保証しない。

UI 文言は、過剰な保証を避ける。

```text
推奨:
  KCS 管理下の履歴から完全削除

避ける:
  世界中のすべてのコピーを完全削除
```

`purge` は必ず次を要求する。

```text
影響範囲 preview
理由入力
明示確認
対象 raw / normalized / chunk / embedding / evidence / index の削除
pack / cache / index rebuild
復元不能な最小 tombstone
```

---

# 8. commit_type の固定 enum について

現在の正本では、`commit_type` を `manual / auto / imported / migrated / repaired / merged / purged` の7種に閉じる方針である。

この方針を採用する場合でも、実装では以下を守る。

```text
type に混ぜない情報は actor / source / trigger / metadata に逃がす
metadata には schema_version を持たせる
未知 type を読んだ場合の error message を明確にする
新 type が必要に見える場合は、まず既存 type + metadata で表現できないか確認する
```

将来、実運用で固定 enum が強すぎると判明した場合は、既存の互換性を壊さない ADR と migration plan を作る。

---

# 9. local-first と同期構想の分離

MVP は単一端末・local-first を優先する。同期、共有版、Web修正提案、複数ユーザー権限は将来構想であり、MVP の CLI / core 仕様へ混ぜすぎない。

推奨:

```text
MVP文書:
  local object store
  local snapshot
  local search
  local restore
  local purge

将来同期文書:
  共有版
  Web修正提案
  権限
  同期競合
```

---

# 10. Adapter セキュリティ

Adapter は任意コマンド、任意URL、ローカルAPI、オンラインAPIを扱えるため、実行境界を明確にする。

最低限必要な制御:

```text
allow_network
allowed_scope
max_input_bytes
timeout_seconds
redact_logs
store_request_body = false
store_response_body = false
command allowlist / confirmation
secret redaction
```

オンライン Adapter は、`--online` 等の明示 opt-in なしにファイル内容を送信してはならない。初回スキャン preview でも、network transmission policy を表示する。

---

# 11. 実装前に埋めるべき仕様

実装前に、少なくとも以下の空ドキュメントを優先して具体化する。

```text
02_data-model/object-store.md
02_data-model/snapshot-dag.md
02_data-model/evidence-pointer-schema.md
02_data-model/normalized-markdown-spec.md
02_data-model/kcsignore-spec.md
02_data-model/sqlite-schema.sql.md
03_pipeline/ingest.md
03_pipeline/markdownization.md
03_pipeline/snapshot.md
04_runtime/restore.md
04_runtime/resume-and-retry.md
07_implementation/testing-strategy.md
08_evaluation/metrics-definitions.md
09_mvp/done-criteria.md
```

特に object hash 算出、Evidence Pointer、Normalized Markdown の決定性、purge 後の到達不能性は、実装後に変えると互換性コストが高い。
