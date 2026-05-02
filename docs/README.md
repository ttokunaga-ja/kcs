# KCS 設計ドキュメント

KCS は **Evidence-grounded local knowledge archive (原文根拠付きローカル知識アーカイブ)** です。ローカルファイルを、過去も含めて、AI と人間が **根拠付きで** 探索できる知識アーカイブを作ります。

> **「探せなかったファイルがすぐ見つかる」「根拠が死なない」** — これが KCS の第一価値命題です。

KCS は次のいずれでもありません: 全部入りの "Git for knowledge" / 個人 AI 検索ツール / OS 級プロダクト / Knowledge Graph プラットフォーム。詳細は [positioning.md](research/positioning.md) と [competitive-landscape.md](research/competitive-landscape.md) を参照してください。

---

## 0. KCS の中核 (3 点)

```
1. Evidence Pointer        path ではなく commit / tree / raw_hash / chunk_hash / span で根拠を指す
2. Markdown 正規化         全ファイル種別を Normalized Markdown に変換し、人間と AI が同じビューを使う
3. Content-addressed CAS   全ファイルを CAS object として保存。削除済み・過去版・移動済みでも到達可能
```

技術的には **Git inspired な local-first content-addressed knowledge archive** ですが、これは手段であって目的ではありません。設計の中心は **object store + snapshot DAG + Evidence Pointer** に置きます。

---

## 0.1 ターゲットユーザー

**最初のターゲット**は明確に絞ります。一般ユーザー向け GUI プロダクトではありません。

```text
- 大量の PDF・Markdown・コード・画像・研究資料を扱う
- 開発者・研究者・技術者
- Git や CLI に抵抗がない
- ローカルファイルが散らかっている
- AI 検索を試したいが、クラウド丸投げは嫌
```

最低体験ライン:

```bash
kcs init
kcs snapshot
kcs search "あの PDF"
kcs open
```

これで価値が成立する状態が MVP の Definition of Done に含まれます。

---

## 0.2 二層構造 — truth と cache

KCS のデータ・所有権・権限の **正本は各フォルダ直下の `.kcs`** に閉じます。device-local な `scope_registry` や将来の global aggregator は **検索キャッシュ・発見補助に過ぎません**。

```
truth = folder-local .kcs       (raw object / normalized / chunks / commits / refs)
cache = scope_registry / aggregator  (検索の探索対象一覧、stale 検出、UI 統合)
```

`scope_registry` のみを更新して `.kcs` の状態が変わる実装は禁止です。詳細は [productization_notes.md §3](research/productization_notes.md), [positioning.md §7](research/positioning.md)。

---

## 0.3 KCS core の責務分離

KCS core は **オフラインで既存 snapshot / artifact を探索・復元できる** ことを基本要件にします (`requirements.md §2`)。Prepare / Markdownize（OCRを含む） / マルチモーダル Embedding / optional Summary・Classification・Rerank は KCS core ではなく **ユーザー選択の Adapter に委譲** し、LLM などのオンライン API、ローカル LLM などのオフライン API、決定論的ライブラリ実装を差し替え可能にします。

`.kcs/` は知識スコープのルートに 1 つだけ置くものではなく、各フォルダに隠しディレクトリとして生成されるフォルダローカルな管理単位です。各 `.kcs/` は **自フォルダ直下のファイルのみ** を管理し、サブフォルダの `.kcs/` 配下を再帰的に取り込むことはしません (= 親子間の重複保存は発生しません)。

---

## 1. ドキュメントの役割分担

ドキュメントは、変更コストの高い順に **正本 → 契約層 → 仕様層 → 実装規約層** に分かれます。

| 層 | 目的 | 変更ポリシー |
| --- | --- | --- |
| **正本 / 研究ノート** (`research/`) | プロダクト位置づけ・設計判断の唯一の真実。競合分析、MVP スコープ、Phase plan、概念モデル、横断規約を含む | **正本**。統合ドキュメントと矛盾する場合は研究ノートを優先 |
| **契約層** (`02_data-model/`, `05_interface/`, `06_adapters/`) | object hash・スキーマ・CLI・trait 署名など、後方互換コストが大きいもの | 変更時は必ず ADR を起票 |
| **仕様層** (`01_concepts/`, `03_pipeline/`, `04_runtime/`) | アルゴリズム・不変条件・処理フロー | 実装と同期して更新 |
| **実装規約層** (`07_implementation/`, `08_evaluation/`, `09_mvp/`) | クレート構成・テスト方針・MVP スコープ | 実装中の知見で随時更新 |
| **判断履歴** (`adr/`) | "なぜそう決めたか" の時系列ログ | 追記のみ。過去の ADR は書き換えない |

---

## 2. ディレクトリ構成と各ファイルの責務

> 現時点では `00_overview/` 〜 `09_mvp/` および `adr/` の多くはプレースホルダーです。**唯一動いている正本は [research/](research/) 配下** です。実装時はまず `research/` を読み、その後で各層を順次具体化してください。

### `research/` — ★研究ノート (正本)

設計判断の正本。プロダクト位置づけ・競合分析・概念モデル・横断規約・実装契約のすべてがここに集約されています。

#### プロダクト戦略 (最初に読む)

| ファイル | 内容 |
| --- | --- |
| [positioning.md](research/positioning.md) | **★ポジショニング・ターゲット・第一価値命題・差別化の核 3 点・MVP スコープ・Phase plan・二層構造・既存ワークフローとの関係・発言禁止リスト** |
| [competitive-landscape.md](research/competitive-landscape.md) | **★競合分析** (Perkeep / git-annex / Khoj / Smart Connections / DEVONthink / Recall / Apple Intelligence / AnythingLLM)、Perkeep 失敗分析、KCS が重ならない / 重なる領域 |
| [philosophy.md](research/philosophy.md) | 理念 (Evidence Pointer の根拠、Markdown 正規化の妥協点、消えない履歴 vs purge の両立) |

#### 概念モデル

| ファイル | 内容 |
| --- | --- |
| [git_kcs.md](research/git_kcs.md) | content-addressed storage と snapshot DAG を Git の語彙で説明する概念モデル。dedup scope、object 種別 |
| [kcs.md](research/kcs.md) | `.kcs/` ディレクトリの最終設計案 (file-layout, scope.json, tool-lock.json, tool_lock_hash 計算規約) |

#### 設計契約

| ファイル | 内容 |
| --- | --- |
| [hash.md](research/hash.md) | **同一性 (hash) と類似性 (semantic_fingerprint) の分離**、`tool_profile_hash` の計算規約 (RFC 8785 JCS, capability vs binary 分離)、up_to_date 判定 |
| [diff.md](research/diff.md) | prepared_units / 差分判定 / **incremental Markdownize 要件** (旧 raw + 旧 Markdown + 新 raw を Adapter に渡し差分更新) |
| [db.md](research/db.md) | SQLite schema、FTS5 外部 content モード、CJK trigram tokenizer、sqlite-vec |
| [read_only.md](research/read_only.md) | 書き込み主体マトリクス (User / KCS / Agent 提案 / Agent 自動)、Markdown は read-only artifact (content hash を取らない) |
| [batch.md](research/batch.md) | 非同期ジョブ、retry budget / backoff、cost guardrail / kill switch、CLI exit code |
| [hybrid.md](research/hybrid.md) | hybrid search、MMR / dedup、paging / cursor、`--at` snapshot との組合せ |
| [commit_snapshot.md](research/commit_snapshot.md) | `commit_type` 永続契約、shallow / full GC、tiered retention、purge |
| [auto_organize.md](research/auto_organize.md) | 分類器 (Phase 4)、score 合成規約、precision / recall 評価方針、循環防止 |
| [synchronization.md](research/synchronization.md) | 共有・修正提案 (v2 以降, Phase 5+)。MVP 範囲外 |

#### 横断規約 / 実装方針

| ファイル | 内容 |
| --- | --- |
| [productization_notes.md](research/productization_notes.md) | **§12 横断規約** (エラーコード namespace / CLI exit code / 設定 schema validation / 時刻 UTC / semver / 観測ログ / 命名リネーム表 / 推奨 Reading Path)。初回スキャン承認、scope registry = cache、Adapter セキュリティ、incremental Markdownize 要件 |

---

### `00_overview/` — 全体俯瞰 (プレースホルダー)

| ファイル | 内容 |
| --- | --- |
| [glossary.md](00_overview/glossary.md) | Object / Tree / Commit / Chunk / Node / Edge / Scope / Evidence など全用語の唯一の定義 |
| [architecture.md](00_overview/architecture.md) | レイヤ図とデータフロー図 (取り込み〜object 化〜snapshot〜検索〜表示) |
| [roadmap.md](00_overview/roadmap.md) | Phase 1〜5 の段階定義 (詳細は [positioning.md §6](research/positioning.md)) |

### `01_concepts/` — "なぜそうなるか" の理屈

| ファイル | 内容 |
| --- | --- |
| [overview.md](01_concepts/overview.md) | KCS の本質: Evidence-grounded local knowledge archive |
| [kcs-vs-git.md](01_concepts/kcs-vs-git.md) | Git との類似点 / 相違点、なぜ Git fork ではないか |
| [folder-local-kcs.md](01_concepts/folder-local-kcs.md) | `.kcs` のフォルダローカル原則、二層構造 (truth vs cache)、デフォルト全 indexed scope 検索 |
| [evidence-pointer.md](01_concepts/evidence-pointer.md) | Evidence Pointer = `commit + tree + raw_hash + chunk_hash + path_at_commit + span` (Markdown 側 content hash は持たない) |
| [knowledge-node.md](01_concepts/knowledge-node.md) | Chunk → Dynamic Node → Stable Node の昇格条件 (Phase 5) |
| [graph-model.md](01_concepts/graph-model.md) | Static / Inferred / Behavioral edge (Phase 5) |
| [navigation-model.md](01_concepts/navigation-model.md) | Query → Result の認知モデル (time-travel 含む) |

### `02_data-model/` — ★契約層

| ファイル | 内容 |
| --- | --- |
| [file-layout.md](02_data-model/file-layout.md) | `.kcs/` の物理レイアウト (`HEAD / config.toml / scope.json / tool-lock.json / objects/ / refs/ / index/ / packs/ / logs/`) |
| [object-store.md](02_data-model/object-store.md) | object 種別 / hash アルゴリズム / 物理レイアウト / dedup / validation |
| [snapshot-dag.md](02_data-model/snapshot-dag.md) | tree / commit / parent / HEAD / refs/heads/* / refs/tags/* の DAG |
| [config-schema.md](02_data-model/config-schema.md) | `config.toml` 全項目とデフォルト |
| [manifest-schema.md](02_data-model/manifest-schema.md) | `manifest.json` = working/index state (永続的真実は tree/commit object 側) |
| [normalized-markdown-spec.md](02_data-model/normalized-markdown-spec.md) | Normalized Markdown は **read-only artifact**。content hash は持たず、identity は `(raw_hash, tool_profile_hash)` |
| [evidence-pointer-schema.md](02_data-model/evidence-pointer-schema.md) | Evidence Pointer の正式スキーマ |
| [chunk-schema.md](02_data-model/chunk-schema.md) | chunk の identity は `(raw_hash, tool_profile_hash, heading_path/section_id, span)` |
| [node-schema.md](02_data-model/node-schema.md) | node object のスキーマ (Phase 5) |
| [edge-schema.md](02_data-model/edge-schema.md) | edge object のスキーマ (Phase 5) |
| [kcsignore-spec.md](02_data-model/kcsignore-spec.md) | `.kcsignore` 文法 / 評価順序 / 巨大ファイル警告 / 子 `.kcs` |
| [sqlite-schema.sql.md](02_data-model/sqlite-schema.sql.md) | SQLite = query acceleration layer (真実ではない、`objects/` から再構築可能) |

### `03_pipeline/` — working tree → object store → snapshot

| ファイル | 内容 |
| --- | --- |
| [ingest.md](03_pipeline/ingest.md) | working tree スキャン、変更検知、raw object 化 |
| [markdownization.md](03_pipeline/markdownization.md) | raw → normalized object。**incremental Markdownize 含む** (旧 raw + 旧 Markdown + 新 raw を Adapter に渡す) |
| [chunking.md](03_pipeline/chunking.md) | normalized → chunk object |
| [embedding.md](03_pipeline/embedding.md) | chunk → embedding object。次元 / 距離 / profile_hash |
| [indexing.md](03_pipeline/indexing.md) | object → BM25 (FTS5) / Vector (sqlite-vec) index 構築 |
| [graph-build.md](03_pipeline/graph-build.md) | Static 抽出規則、Inferred 生成基準 (Phase 5) |
| [snapshot.md](03_pipeline/snapshot.md) | working tree → index → tree object → commit object の遷移 |

### `04_runtime/` — 検索・復元・運用時の挙動

| ファイル | 内容 |
| --- | --- |
| [search.md](04_runtime/search.md) | BM25 + Vector の融合 (RRF)、MMR / dedup、paging / cursor |
| [time-travel-search.md](04_runtime/time-travel-search.md) | `--at <snapshot> / --all-history / --deleted / --since` の挙動 |
| [restore.md](04_runtime/restore.md) | `kcs restore` の安全要件 (現実ファイル非破壊、`--to <dir>` 必須) |
| [ephemeral-graph.md](04_runtime/ephemeral-graph.md) | 検索ごとの局所グラフ生成 (Phase 5) |
| [node-promotion.md](04_runtime/node-promotion.md) | 昇格スコア計算、降格、TTL (Phase 5) |
| [access-log.md](04_runtime/access-log.md) | `logs/access.jsonl` に何を残し何を残さないか |
| [concurrency-and-locking.md](04_runtime/concurrency-and-locking.md) | 多重 index / search の整合性、`.kcs.lock` |
| [gc-and-pack.md](04_runtime/gc-and-pack.md) | GC スケジューリング (on_idle / manual_only / after_index)、tiered retention、purge |
| [resume-and-retry.md](04_runtime/resume-and-retry.md) | パイプライン中断時の再開、retry budget、cost guardrail |

### `05_interface/` — ★ユーザー契約

| ファイル | 内容 |
| --- | --- |
| [cli-spec.md](05_interface/cli-spec.md) | 全サブコマンド: `init / add / status / commit / snapshot / checkout / tag / restore / search / open / inspect / log / diff / gc / pack / purge` |
| [output-format.md](05_interface/output-format.md) | ヒト向け / JSON 両モードのスキーマ |
| [exit-codes-and-errors.md](05_interface/exit-codes-and-errors.md) | エラー分類と終了コード表 (横断規約は [productization_notes.md §12](research/productization_notes.md)) |
| [agent-api.md](05_interface/agent-api.md) | AI Agent と Adapter が共通利用する KCS API (MCP / 直接呼び出し) の契約 |
| [git-integration.md](05_interface/git-integration.md) | optional。Git commit との紐付けは MVP 必須機能ではない |
| [export-import.md](05_interface/export-import.md) | `.kcs/` の bundle 形式、別マシンへの転送 |
| [ui-future.md](05_interface/ui-future.md) | 将来の GUI に渡す前提 (Phase 4 以降)。CLI の Git 風語彙を GUI で一般向けに言い換える |

### `06_adapters/` — ★差し替え契約

| ファイル | 内容 |
| --- | --- |
| [adapter-overview.md](06_adapters/adapter-overview.md) | ライフサイクル、`tool-lock.json` との関係、`capabilities = ["incremental_update"]` 宣言 |
| [trait-definitions.md](06_adapters/trait-definitions.md) | 各 Adapter の trait 署名 |
| [prepare.md](06_adapters/prepare.md) | raw object → prepared object / prepared unit の I/O 契約 |
| [markdownizer.md](06_adapters/markdownizer.md) | prepared unit / raw text → MD の I/O 契約。OCR は内部能力。**incremental_update capability で旧 raw + 旧 Markdown を受け取って差分更新** |
| [embedder.md](06_adapters/embedder.md) | マルチモーダル Embedding Adapter。Text / Image 分離は行わない |
| [summarizer.md](06_adapters/summarizer.md) | optional |
| [classification.md](06_adapters/classification.md) | optional |
| [rerank.md](06_adapters/rerank.md) | optional |
| [bm25-backend.md](06_adapters/bm25-backend.md) | BM25 バックエンド (FTS5 デフォルト) |
| [vector-backend.md](06_adapters/vector-backend.md) | ベクトル検索バックエンド (sqlite-vec デフォルト) |
| [graph-backend.md](06_adapters/graph-backend.md) | グラフ DB バックエンド (Phase 5) |

### `07_implementation/` — Rust 側の実装規約

| ファイル | 内容 |
| --- | --- |
| [workspace-layout.md](07_implementation/workspace-layout.md) | クレート分割 |
| [module-responsibilities.md](07_implementation/module-responsibilities.md) | 各クレートの public API 一覧 |
| [error-model.md](07_implementation/error-model.md) | `thiserror` / `anyhow` の使い分け、エラー伝播方針 |
| [logging-and-tracing.md](07_implementation/logging-and-tracing.md) | `tracing` spans、ログレベル |
| [coding-guidelines.md](07_implementation/coding-guidelines.md) | 命名 / feature flag / `unsafe` 禁則 |
| [testing-strategy.md](07_implementation/testing-strategy.md) | 単体 / 結合 / ゴールデン / プロパティ / ベンチ |
| [nfr-performance.md](07_implementation/nfr-performance.md) | 索引化スループット、検索レイテンシ目標 |

### `08_evaluation/` — 評価ハーネス仕様

| ファイル | 内容 |
| --- | --- |
| [benchmark-corpus.md](08_evaluation/benchmark-corpus.md) | 評価コーパス選定、ライセンス |
| [metrics-definitions.md](08_evaluation/metrics-definitions.md) | 検索時間 / Recall / nDCG / 操作回数の計算式 |
| [tree-vs-kcs-protocol.md](08_evaluation/tree-vs-kcs-protocol.md) | Tree 構造との比較実験プロトコル |

### `09_mvp/` — MVP スコープ

| ファイル | 内容 |
| --- | --- |
| [mvp-scope.md](09_mvp/mvp-scope.md) | やる / やらない の二値化 (詳細は [positioning.md §5](research/positioning.md)) |
| [milestones.md](09_mvp/milestones.md) | M0..Mn と完了条件 |
| [done-criteria.md](09_mvp/done-criteria.md) | MVP 受入テストチェックリスト |

### `adr/` — 設計判断の履歴

追記のみ。過去の ADR は書き換えず、新しい判断は新しい ADR で上書きする。

| ファイル | 判断対象 |
| --- | --- |
| [0001-rust-workspace-split.md](adr/0001-rust-workspace-split.md) | クレート分割の単位 |
| [0002-sqlite-as-default-store.md](adr/0002-sqlite-as-default-store.md) | SQLite を query acceleration layer として採用する根拠 |
| [0003-bm25-engine-choice.md](adr/0003-bm25-engine-choice.md) | BM25 エンジンの選定 (FTS5 デフォルト) |
| [0004-vector-store-choice.md](adr/0004-vector-store-choice.md) | ベクトルストアの選定 (sqlite-vec デフォルト) |
| [0005-normalized-markdown-determinism.md](adr/0005-normalized-markdown-determinism.md) | ~~Normalized Markdown を決定的に生成する方針~~ → **Markdown は read-only artifact、content hash は取らない** に修正 |
| [0006-evidence-pointer-immutability.md](adr/0006-evidence-pointer-immutability.md) | Evidence Pointer の不変性保証 (object hash 基盤) |
| [0007-snapshot-vs-commit-naming.md](adr/0007-snapshot-vs-commit-naming.md) | `commit` / `snapshot` は同一履歴 object。CLI は Git 風 |
| [0008-archive-all-by-default.md](adr/0008-archive-all-by-default.md) | デフォルト全管理 (容量効率より知識喪失防止を優先) |
| [0009-content-addressed-storage.md](adr/0009-content-addressed-storage.md) | raw / chunk / embedding / tree / commit を全て CAS で管理 (Markdown は CAS 内 read-only artifact) |
| [0010-offline-first.md](adr/0010-offline-first.md) | KCS core はオフラインで既存 snapshot / artifact を探索・復元可能 |
| [0011-default-global-search.md](adr/0011-default-global-search.md) | デフォルト検索は全 indexed scope を対象 |
| [0012-history-purge-for-legal-erasure.md](adr/0012-history-purge-for-legal-erasure.md) | 法務・秘匿・誤取り込み向けに特定ファイルの全履歴を完全削除する purge を提供 |
| [0013-folder-local-kcs-per-directory.md](adr/0013-folder-local-kcs-per-directory.md) | `.kcs/` は各フォルダに生成されるフォルダローカルな隠しメタデータ |
| [0014-mvp-preserves-core-search-experience.md](adr/0014-mvp-preserves-core-search-experience.md) | MVP は最小完全系 (詳細は [positioning.md](research/positioning.md)) |
| [0015-adapters-are-device-local.md](adr/0015-adapters-are-device-local.md) | Adapter 実行設定はデバイスローカルに保持 |
| [0016-initial-scan-preview-and-approval.md](adr/0016-initial-scan-preview-and-approval.md) | 初回スキャンでは対象範囲 preview、除外提案、明示承認を必須にする |

> **要追記 ADR (TODO)**:
> - 0017: positioning を Evidence-grounded local knowledge archive に確定
> - 0018: normalized_hash を採用しない (Markdown は content hash を持たない read-only artifact)
> - 0019: hash (同一性) と semantic_fingerprint (類似性) を分離
> - 0020: 二層構造 (folder-local truth + global cache)
> - 0021: incremental Markdownize 要件 (Adapter capability)
> - 0022: tool_profile_hash の計算規約 (RFC 8785 JCS, capability vs binary 分離)
> - 0023: MVP スコープ絞り込みと Phase plan (1〜5)

---

## 3. 読む順序 (依存順)

新規参加者は次の順で読むことで概念がぶつかりません。

```text
0a. research/positioning.md          ★最初に読む。プロダクト位置づけ・MVP・Phase plan
0b. research/competitive-landscape.md ★競合・Perkeep 失敗分析・差別化の核
1.  research/philosophy.md            理念 (Evidence Pointer の根拠、忘れない vs purge の両立)
2.  research/git_kcs.md               概念モデル (CAS, snapshot DAG, dedup scope)
3.  research/kcs.md                   .kcs ディレクトリの最終設計案
4.  research/hash.md                  identity (hash) vs 類似性 (semantic_fingerprint), tool_profile_hash 計算規約
5.  research/diff.md                  prepared_units / 差分判定 / incremental Markdownize 要件
6.  research/db.md                    SQLite schema / FTS5 / sqlite-vec
7.  research/read_only.md             書き込み主体マトリクス、権限境界
8.  research/batch.md                 retry budget / cost guardrail / CLI exit code
9.  research/hybrid.md                hybrid search / MMR / paging
10. research/commit_snapshot.md       commit_type / GC / purge
11. research/auto_organize.md         分類器 (Phase 4)
12. research/synchronization.md       共有 (Phase 5+, MVP 範囲外)
13. research/productization_notes.md  ★横断規約 (エラーコード / exit / schema / semver / TZ / リネーム表)
14. requirements.md                   研究ノートを統合した要件ドラフト
```

その後、実装層 (`02_data-model/` → `06_adapters/` → `05_interface/` → `03_pipeline/` → `04_runtime/` → `07_implementation/` → `09_mvp/`) を順に具体化します。

---

## 4. Phase Plan (実装順)

詳細は [positioning.md §6](research/positioning.md)。

```
Phase 1: Evidence 基盤    raw object / normalized / chunk / Evidence Pointer
Phase 2: 検索             FTS5 / sqlite-vec / hybrid search
Phase 3: 履歴             tree / commit / restore / --at / time-travel
Phase 4: 自動化           auto snapshot / Downloads watch / inbox / classification suggestion
Phase 5: Agent            agent API / navigation / neighbors / node / edge
```

各 Phase は前 Phase に依存します。Phase 1 が動かないうちに Phase 4-5 を深掘りしません。

---

## 5. 編集規約

- **形式**: GitHub-flavored Markdown。数式は LaTeX (`$...$` / `$$...$$`)。
- **言語**: 日本語。固有名詞・コード片は原語のまま。
- **コードブロック**: 言語タグを必須 (`bash`, `toml`, `json`, `rust`, `sql`, `text`)。
- **相対リンク**: ドキュメント間の参照はリポジトリルートからの相対パス。
- **要件への参照**: `requirements.md §N` の形式で章番号を明示。
- **スキーマ変更**: `02_data-model/` または `06_adapters/` の変更は ADR と対で行う。特に `tool_profile_hash` / `tool_lock_hash` の算出ルールは破壊的変更扱い。
- **未確定事項**: 文中に `> TODO:` または `> OPEN QUESTION:` で明示し、決まり次第本文に取り込む。
- **発言禁止フレーズ**: README / pitch / docs では以下を使わない (詳細は [positioning.md §9](research/positioning.md))。
  - ✗ "Git for knowledge"
  - ✗ "個人 AI アシスタント"
  - ✗ "OS 級プロダクト"
  - ✗ "Knowledge Graph for personal data"
  - ✗ "Notion / Obsidian キラー"
- **採用する語**:
  - ✓ Evidence-grounded local knowledge archive
  - ✓ 原文根拠付きローカル知識アーカイブ
  - ✓ Evidence Pointer
  - ✓ time-travel knowledge navigation
