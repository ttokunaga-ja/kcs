# KCS 設計ドキュメント

KCS の正本は [research/](research/) 配下の研究ノートです。[requirements.md](requirements.md) は研究ノートから実装向けに統合した要件ドラフトであり、矛盾がある場合は `research/` を優先して同期します。本 README は、その研究ノートを実装ドキュメントへ落とすための **設計の地図** です。

KCS は **Git inspired な local-first content-addressed knowledge archive** です。`.kcs/` は単なる検索インデックスではなく、`raw / normalized / chunks / embeddings / nodes / edges / trees / commits` を保持する object store です。したがって設計の中心は **object store + snapshot DAG** に置きます。

`.kcs/` は知識スコープのルートに1つだけ置くものではなく、基本的には各フォルダに隠しディレクトリとして生成されるフォルダローカルな管理単位です。子フォルダや孫フォルダにもそれぞれ `.kcs/` が存在し、各 `.kcs/` は自フォルダ直下のファイルと子フォルダリンクを管理します。

KCS core は **オフラインで既存 snapshot / artifact を探索・復元できる** ことを基本要件とする(`requirements.md §2`)。Prepare / Markdownize（OCRを含む） / マルチモーダル Embedding / optional Summary・Classification・Rerank は KCS core ではなくユーザー選択の Adapter に委譲し、LLM などのオンライン API、ローカル LLM などのオフライン API、決定論的ライブラリ実装を差し替え可能にする。

KCS の作成意図は、AI を契機としてローカルの知識空間を再定義することです。長年、PDF / Office / 画像のような検索に向かないファイル空間がデフォルトでしたが、KCS はそれらを Markdown を主とする統一テキスト表現へ変換し、Google が Web 文書にもたらした共通の検索体験をローカルファイル空間にも持ち込みます。副目的として、開発者が Git で享受してきた履歴付き知識アーカイブの恩恵を、すべてのユーザーが扱える形へ広げます。

---

## 1. ドキュメントの役割分担

ドキュメントは、変更コストの高い順に **契約層 → 仕様層 → 実装規約層** に分かれます。

| 層 | 目的 | 変更ポリシー |
| --- | --- | --- |
| **契約層** (`02_data-model/`, `05_interface/`, `06_adapters/`) | object hash・スキーマ・CLI・trait 署名など、後方互換コストが大きいもの | 変更時は必ず ADR を起票 |
| **仕様層** (`01_concepts/`, `03_pipeline/`, `04_runtime/`) | アルゴリズム・不変条件・処理フロー | 実装と同期して更新 |
| **実装規約層** (`07_implementation/`, `08_evaluation/`, `09_mvp/`) | クレート構成・テスト方針・MVP スコープ | 実装中の知見で随時更新 |
| **判断履歴** (`adr/`) | "なぜそう決めたか" の時系列ログ | 追記のみ。過去の ADR は書き換えない |
| **研究ノート** (`research/`) | 設計判断の正本。プロダクト意図・検索範囲・履歴保持/削除・同期思想の根拠 | 正本。統合ドキュメントと矛盾する場合は研究ノートを優先 |

---

## 2. ディレクトリ構成と各ファイルの責務

### `00_overview/` — 全体俯瞰

| ファイル | 内容 |
| --- | --- |
| [glossary.md](00_overview/glossary.md) | Object / Tree / Commit / Chunk / Node / Edge / Scope / Evidence など全用語の唯一の定義 |
| [architecture.md](00_overview/architecture.md) | レイヤ図とデータフロー図(取り込み〜object 化〜snapshot〜検索〜表示) |
| [roadmap.md](00_overview/roadmap.md) | MVP → 拡張 → GUI までの段階定義(v0/v1/v2 の object store 進化を含む) |

### `01_concepts/` — "なぜそうなるか" の理屈

| ファイル | 内容 |
| --- | --- |
| [overview.md](01_concepts/overview.md) | KCS の本質: Finder + Git + AI Agent Knowledge Index の合成 |
| [kcs-vs-git.md](01_concepts/kcs-vs-git.md) | Git との類似点 / 相違点、なぜ Git fork ではないか |
| [folder-local-kcs.md](01_concepts/folder-local-kcs.md) | `.kcs` のフォルダローカル原則、デフォルト検索は全 indexed scope、オプション指定時の現在フォルダ/配下 scope 制限 |
| [evidence-pointer.md](01_concepts/evidence-pointer.md) | Evidence Pointer は path ではなく `commit + tree + raw_hash + normalized_hash + chunk_hash + path_at_commit + span` を指す |
| [knowledge-node.md](01_concepts/knowledge-node.md) | Chunk → Dynamic Node → Stable Node の昇格条件と履歴化 |
| [graph-model.md](01_concepts/graph-model.md) | Static / Inferred / Behavioral edge の定義と寿命 |
| [navigation-model.md](01_concepts/navigation-model.md) | Query → Result までの認知モデル(time-travel 含む) |

### `02_data-model/` — ★契約層(最優先で固める)

| ファイル | 内容 |
| --- | --- |
| [file-layout.md](02_data-model/file-layout.md) | `.kcs/` の物理レイアウト(`HEAD / config.toml / scope.json / tool-lock.json / objects/ / refs/ / index/ / packs/ / logs/ / cache/ / tmp/`) |
| [object-store.md](02_data-model/object-store.md) | ★object type / hash アルゴリズム / 物理レイアウト / dedup / compression / validation |
| [snapshot-dag.md](02_data-model/snapshot-dag.md) | ★tree / commit / parent / HEAD / refs/heads/* / refs/tags/* の DAG |
| [config-schema.md](02_data-model/config-schema.md) | `config.toml` 全項目とデフォルト |
| [manifest-schema.md](02_data-model/manifest-schema.md) | `manifest.json` = working/index state(永続的真実は tree/commit object 側) |
| [normalized-markdown-spec.md](02_data-model/normalized-markdown-spec.md) | Normalized Markdown の厳密仕様(決定的生成が前提) |
| [evidence-pointer-schema.md](02_data-model/evidence-pointer-schema.md) | Evidence Pointer の正式スキーマ(object hash 基盤) |
| [chunk-schema.md](02_data-model/chunk-schema.md) | chunk = content-addressed object。chunk_hash 算出規則 |
| [node-schema.md](02_data-model/node-schema.md) | node object のスキーマ・履歴化(`created_at_commit`) |
| [edge-schema.md](02_data-model/edge-schema.md) | edge object のスキーマ・寿命 |
| [kcsignore-spec.md](02_data-model/kcsignore-spec.md) | `.kcsignore` 文法 / 評価順序 / 巨大ファイル警告 / hidden files / 子 `.kcs` |
| [sqlite-schema.sql.md](02_data-model/sqlite-schema.sql.md) | SQLite = query acceleration layer(真実ではない、`objects/` から再構築可能) |

### `03_pipeline/` — working tree → object store → snapshot

| ファイル | 内容 |
| --- | --- |
| [ingest.md](03_pipeline/ingest.md) | working tree スキャン、変更検知、raw object 化 |
| [markdownization.md](03_pipeline/markdownization.md) | raw → normalized object。tool profile による決定性 |
| [chunking.md](03_pipeline/chunking.md) | normalized → chunk object(見出し / 粒度 / オーバーラップ) |
| [embedding.md](03_pipeline/embedding.md) | chunk → embedding object。次元 / 距離 / profile_hash |
| [indexing.md](03_pipeline/indexing.md) | object → BM25 / Vector / Graph index 構築 |
| [graph-build.md](03_pipeline/graph-build.md) | Static 抽出規則、Inferred 生成基準、再計算条件 |
| [snapshot.md](03_pipeline/snapshot.md) | working tree → index → tree object → commit object の遷移 |

### `04_runtime/` — 検索・復元・運用時の挙動

| ファイル | 内容 |
| --- | --- |
| [search.md](04_runtime/search.md) | BM25 + Vector の融合(RRF 等)、再ランク、上限 |
| [time-travel-search.md](04_runtime/time-travel-search.md) | `--at <snapshot> / --all-history / --deleted / --since` の挙動 |
| [restore.md](04_runtime/restore.md) | `kcs restore` の安全要件(現実ファイル非破壊、`--to <dir>` 必須) |
| [ephemeral-graph.md](04_runtime/ephemeral-graph.md) | 検索ごとの局所グラフ生成、コスト上限 |
| [node-promotion.md](04_runtime/node-promotion.md) | 昇格スコア計算、降格、TTL |
| [access-log.md](04_runtime/access-log.md) | `logs/access.jsonl` に何を残し何を残さないか |
| [concurrency-and-locking.md](04_runtime/concurrency-and-locking.md) | 多重 index / search の整合性、`.kcs.lock` |
| [gc-and-pack.md](04_runtime/gc-and-pack.md) | GC / pack file / delta 圧縮(v0 / v1 / v2 段階)、法務・秘匿向けの履歴完全削除 |
| [resume-and-retry.md](04_runtime/resume-and-retry.md) | パイプライン中断時の再開、idempotent 化 |

### `05_interface/` — ★ユーザー契約

| ファイル | 内容 |
| --- | --- |
| [cli-spec.md](05_interface/cli-spec.md) | 全サブコマンド: `init / add / status / commit / snapshot / checkout / tag / restore / search / open / inspect / neighbors / log / diff / gc / pack / purge` |
| [output-format.md](05_interface/output-format.md) | ヒト向け / JSON 両モードのスキーマ |
| [exit-codes-and-errors.md](05_interface/exit-codes-and-errors.md) | エラー分類と終了コード表 |
| [agent-api.md](05_interface/agent-api.md) | AI Agent と Adapter が共通利用する KCS API(MCP / 直接呼び出し)の契約 |
| [git-integration.md](05_interface/git-integration.md) | `git kcs` プラグイン仕様、Git commit との紐付け(optional) |
| [export-import.md](05_interface/export-import.md) | `.kcs/` の bundle 形式、別マシンへの転送 |
| [ui-future.md](05_interface/ui-future.md) | 将来の Tauri GUI に渡す前提(MVP 外)。CLI の Git 風語彙を GUI では一般向けに言い換える |

### `06_adapters/` — ★差し替え契約

| ファイル | 内容 |
| --- | --- |
| [adapter-overview.md](06_adapters/adapter-overview.md) | ライフサイクル、`tool-lock.json` との関係、優先順位、フォールバック |
| [trait-definitions.md](06_adapters/trait-definitions.md) | 各 Adapter の trait 署名 |
| [prepare.md](06_adapters/prepare.md) | raw object → prepared object / prepared unit の I/O 契約 |
| [markdownizer.md](06_adapters/markdownizer.md) | prepared unit / raw text → MD の I/O 契約。OCR はこの Adapter の内部能力として扱う |
| [embedder.md](06_adapters/embedder.md) | マルチモーダル Embedding Adapter。Text / Image 分離は行わない |
| [summarizer.md](06_adapters/summarizer.md) | Summary Adapter(optional) |
| [classification.md](06_adapters/classification.md) | Classification Adapter(optional) |
| [rerank.md](06_adapters/rerank.md) | Rerank Adapter(optional) |
| [bm25-backend.md](06_adapters/bm25-backend.md) | BM25 バックエンド |
| [vector-backend.md](06_adapters/vector-backend.md) | ベクトル検索バックエンド |
| [graph-backend.md](06_adapters/graph-backend.md) | グラフ DB バックエンド |

### `07_implementation/` — Rust 側の実装規約

| ファイル | 内容 |
| --- | --- |
| [workspace-layout.md](07_implementation/workspace-layout.md) | クレート分割(object store / snapshot / index / nav / cli / adapters …) |
| [module-responsibilities.md](07_implementation/module-responsibilities.md) | 各クレートの public API 一覧 |
| [error-model.md](07_implementation/error-model.md) | `thiserror` / `anyhow` の使い分け、エラー伝播方針 |
| [logging-and-tracing.md](07_implementation/logging-and-tracing.md) | `tracing` spans、ログレベル |
| [coding-guidelines.md](07_implementation/coding-guidelines.md) | 命名 / feature flag / `unsafe` 禁則 |
| [testing-strategy.md](07_implementation/testing-strategy.md) | 単体 / 結合 / ゴールデン / プロパティ / ベンチ |
| [nfr-performance.md](07_implementation/nfr-performance.md) | 索引化スループット、検索レイテンシ目標、object store I/O 目標 |

### `08_evaluation/` — 評価ハーネス仕様

| ファイル | 内容 |
| --- | --- |
| [benchmark-corpus.md](08_evaluation/benchmark-corpus.md) | 評価コーパス選定、ライセンス |
| [metrics-definitions.md](08_evaluation/metrics-definitions.md) | 検索時間 / 操作回数 / トークン等の計算式 |
| [tree-vs-kcs-protocol.md](08_evaluation/tree-vs-kcs-protocol.md) | Tree 構造との比較実験プロトコル |

### `09_mvp/` — MVP スコープ

| ファイル | 内容 |
| --- | --- |
| [mvp-scope.md](09_mvp/mvp-scope.md) | やる / やらない の二値化(object store は MVP 必須) |
| [milestones.md](09_mvp/milestones.md) | M0..Mn と完了条件 |
| [done-criteria.md](09_mvp/done-criteria.md) | MVP 受入テストチェックリスト |

### `adr/` — 設計判断の履歴

追記のみ。過去の ADR は書き換えず、新しい判断は新しい ADR で上書きする。

| ファイル | 判断対象 |
| --- | --- |
| [0001-rust-workspace-split.md](adr/0001-rust-workspace-split.md) | クレート分割の単位 |
| [0002-sqlite-as-default-store.md](adr/0002-sqlite-as-default-store.md) | SQLite を query acceleration layer として採用する根拠 |
| [0003-bm25-engine-choice.md](adr/0003-bm25-engine-choice.md) | BM25 エンジン(Tantivy 等)の選定 |
| [0004-vector-store-choice.md](adr/0004-vector-store-choice.md) | ベクトルストアの選定 |
| [0005-normalized-markdown-determinism.md](adr/0005-normalized-markdown-determinism.md) | Normalized Markdown を決定的に生成する方針 |
| [0006-evidence-pointer-immutability.md](adr/0006-evidence-pointer-immutability.md) | Evidence Pointer の不変性保証(object hash 基盤) |
| [0007-snapshot-vs-commit-naming.md](adr/0007-snapshot-vs-commit-naming.md) | `commit` / `snapshot` は同一履歴 object。CLI は Git 風、GUI は一般向けに言い換え |
| [0008-archive-all-by-default.md](adr/0008-archive-all-by-default.md) | デフォルト全管理(容量効率より知識喪失防止を優先) |
| [0009-content-addressed-storage.md](adr/0009-content-addressed-storage.md) | raw / normalized / chunk / embedding / node / edge / tree / commit を全て CAS で管理 |
| [0010-offline-first.md](adr/0010-offline-first.md) | KCS core はオフラインで既存 snapshot / artifact を探索・復元可能。Prepare / Markdownize（OCRを含む） / マルチモーダル Embedding / optional Summary・Classification・Rerank は Adapter に委譲 |
| [0011-default-global-search.md](adr/0011-default-global-search.md) | デフォルト検索は全 indexed scope を対象にし、scope option で現在フォルダ/配下に制限 |
| [0012-history-purge-for-legal-erasure.md](adr/0012-history-purge-for-legal-erasure.md) | 法務・秘匿・誤取り込み向けに特定ファイルの全履歴を完全削除する purge を提供 |
| [0013-folder-local-kcs-per-directory.md](adr/0013-folder-local-kcs-per-directory.md) | `.kcs/` は各フォルダに生成されるフォルダローカルな隠しメタデータ |
| [0014-mvp-preserves-core-search-experience.md](adr/0014-mvp-preserves-core-search-experience.md) | MVP は検索体験を削った薄いデモではなく、基本機能を備えた最小の完全系 |
| [0015-adapters-are-device-local.md](adr/0015-adapters-are-device-local.md) | Adapter 実行設定はデバイスローカルに保持し、共有 `.kcs/` では管理しない |

### `research/` — 研究ノート(正本)

設計判断の正本となる検討メモ。統合ドキュメントや空の仕様ファイルと矛盾する場合は、まず `research/` 側を優先する。

| ファイル | 内容 |
| --- | --- |
| [batch.md](research/batch.md) | バッチ処理の検討 |
| [git_kcs.md](research/git_kcs.md) | Git との対比から KCS を再定義した検討(現要件の出発点) |
| [hash.md](research/hash.md) | ハッシュアルゴリズムの検討 |
| [hybrid.md](research/hybrid.md) | ハイブリッド検索の検討 |
| [kcs.md](research/kcs.md) | KCS の初期構想 |

---

## 3. 読む順序(依存順)

1. [research/philosophy.md](research/philosophy.md) + [research/git_kcs.md](research/git_kcs.md) — プロダクト意図と正本方針
2. [requirements.md](requirements.md) — 研究ノートを統合した要件ドラフト
3. [01_concepts/overview.md](01_concepts/overview.md) + [kcs-vs-git.md](01_concepts/kcs-vs-git.md) + [00_overview/glossary.md](00_overview/glossary.md) — 共通語彙と全体像
4. **`02_data-model/`** の中核 — [file-layout.md](02_data-model/file-layout.md) → [object-store.md](02_data-model/object-store.md) → [snapshot-dag.md](02_data-model/snapshot-dag.md) → [evidence-pointer-schema.md](02_data-model/evidence-pointer-schema.md)
5. `02_data-model/` のスキーマ群 — normalized-markdown-spec / chunk / node / edge / kcsignore / manifest / sqlite
6. [01_concepts/folder-local-kcs.md](01_concepts/folder-local-kcs.md), [evidence-pointer.md](01_concepts/evidence-pointer.md) — 境界条件と原文回帰
7. [06_adapters/trait-definitions.md](06_adapters/trait-definitions.md) — 差し替え契約(`tool_profile_hash` の意味も)
8. [05_interface/cli-spec.md](05_interface/cli-spec.md) — ユーザー契約(`commit / checkout / restore / search --at` を含む)
9. `03_pipeline/` → `04_runtime/`(特に [time-travel-search.md](04_runtime/time-travel-search.md), [restore.md](04_runtime/restore.md), [gc-and-pack.md](04_runtime/gc-and-pack.md))
10. `07_implementation/` および `09_mvp/`
11. `08_evaluation/` は実装と並走可

> NOTE: 現時点では `00_overview/`、`01_concepts/`、`02_data-model/`、`03_pipeline/`、`04_runtime/`、`05_interface/`、`06_adapters/`、`07_implementation/`、`08_evaluation/`、`09_mvp/`、`adr/` の多くはプレースホルダーです。実装時は `research/` と `requirements.md` を参照して順次具体化します。

---

## 4. 編集規約

- **形式**: GitHub-flavored Markdown。数式は LaTeX(`$...$` / `$$...$$`)。
- **言語**: 日本語。固有名詞・コード片は原語のまま。
- **コードブロック**: 言語タグを必須(`bash`, `toml`, `json`, `rust`, `sql`, `text`)。
- **相対リンク**: ドキュメント間の参照はリポジトリルートからの相対パス。
- **要件への参照**: `requirements.md §N` の形式で章番号を明示。
- **スキーマ変更**: `02_data-model/` または `06_adapters/` の変更は ADR と対で行う。特に object hash の算出ルールは破壊的変更扱い。
- **未確定事項**: 文中に `> TODO:` または `> OPEN QUESTION:` で明示し、決まり次第本文に取り込む。
