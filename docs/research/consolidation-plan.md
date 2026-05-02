# Document Consolidation Plan

KCS の現状ドキュメント (research 14 本 + 各層プレースホルダー多数 = 40 本超) を、**実装着手前に 18-20 本に圧縮** する。

> **背景**: 設計を綺麗にし続けるフェーズが長引くと空中楼閣化する。Step 1 のコードを書けば設計の致命的誤りは早期発見できる。統合作業の上限を設けて、超えたら凍結し実装に移る。

---

# 1. 統合上限とゲート

```
統合作業の上限:    2 週間
完了後のアクション: ドキュメントを凍結し、Step 1 の実装に着手
凍結中の更新:      ADR の追記のみ可。本文書き換えは ADR を起こすこと
```

このゲートを設ける理由:

- 統合作業は実装着手後にはほぼ取れない。
- 「綺麗にし続ける」と Phase 4-5 のドキュメントが永遠に肥大する。
- Step 1 (kcs-core + kcs-cli の init/status/commit/log) が動けば、設計の根本的誤りはほぼ検出できる。

---

# 2. 目標構造 (正本 + 契約 + 運用 = 10 本)

実装に必要なドキュメントは下記 10 本に集約する。

| # | ファイル | 統合元 | 役割 |
| --- | --- | --- | --- |
| 1 | README.md | 既存 | 全体俯瞰、Reading Path |
| 2 | positioning.md | 既存 | プロダクト位置づけ・MVP・Phase plan |
| 3 | data-model.md | git_kcs.md + kcs.md + hash.md + 02_data-model/* | object 種別 / hash / scope.json / tool-lock.json / chunk schema |
| 4 | pipeline.md | diff.md + db.md + 03_pipeline/* | ingest / markdownize / chunking / embedding / indexing / snapshot |
| 5 | runtime.md | hybrid.md + commit_snapshot.md + 04_runtime/* | search / time-travel / restore / GC / purge / locking |
| 6 | cli-spec.md | 05_interface/cli-spec.md (展開) | 全サブコマンド、exit code |
| 7 | adapter-spec.md | 06_adapters/* + 一部 batch.md | Adapter trait, capabilities, incremental Markdownize 規約 |
| 8 | evidence-pointer-spec.md | 02_data-model/evidence-pointer-schema.md (展開) | **外部 Agent が参照する仕様として独立** |
| 9 | mvp-scope.md | 09_mvp/* + 一部 productization_notes.md | やる/やらない、Done 条件、北極星シナリオ |
| 10 | philosophy.md | 既存 | 理念 (Evidence Pointer の根拠、忘れない vs purge の両立) |

**補助ドキュメント (8-10 本以下)**:

| 種別 | ファイル | 役割 |
| --- | --- | --- |
| 比較 | competitive-landscape.md | 競合分析 + Perkeep 失敗分析 |
| 実装 | testing-strategy.md, nfr-performance.md | 実装規約 (07_implementation/ から最小限) |
| 計画 | north-star-scenarios.md, design-homework.md, consolidation-plan.md | 実装着手前に確定する論点 |
| 履歴 | adr/*.md | 8-10 本に圧縮 (詳細 §4) |

---

# 3. 統合フェーズ (2 週間)

```
Day 1-3:  data-model.md を統合
          - git_kcs.md の概念モデル
          - kcs.md のディレクトリ構造
          - hash.md の identity 規約
          - 02_data-model/ の各 schema をインライン化

Day 4-5:  pipeline.md を統合
          - diff.md の prepared_units / incremental Markdownize
          - db.md の SQLite schema / FTS5 / sqlite-vec
          - 03_pipeline/ の各 stage

Day 6-7:  runtime.md を統合
          - hybrid.md の検索モード / paging / MMR
          - commit_snapshot.md の commit_type / GC / purge
          - 04_runtime/ の time-travel / restore / locking

Day 8-9:  adapter-spec.md と evidence-pointer-spec.md を切り出し
          - 06_adapters/ + batch.md から adapter 関連を抽出
          - evidence-pointer は外部 Agent 参照用の独立仕様として書き直し

Day 10-11: cli-spec.md と mvp-scope.md を仕上げ
          - exit code は productization_notes.md §12 から移植
          - 北極星シナリオ 3 つを mvp-scope.md の Done 条件に明記

Day 12:   philosophy.md と positioning.md を最終チェック

Day 13:   競合分析 + 補助ドキュメントの整合確認
          - design-homework.md の 4 項目が各正本ドキュメントから参照されているか

Day 14:   ADR の圧縮 (§4)、リンク切れ・旧称残置の grep、README の Reading Path 更新

Day 14 終了時点で凍結。Step 1 着手。
```

---

# 4. ADR の圧縮 (8-10 本に絞る)

残すべき ADR の基準:

```
1. 逆方向の判断もありえた (技術選定、設計トレードオフ)
2. 将来撤回されうる (外部依存、性能前提)
3. 外部から問われたら答える義務がある (CAS、purge、ライセンス)
```

統合候補 (data-model.md などへ吸収):

```
- 0007 (snapshot-vs-commit-naming) → data-model.md でセクション化
- 0009 (content-addressed-storage) → data-model.md の冒頭で説明
- 0014 (mvp-preserves-core-search-experience) → mvp-scope.md に統合
- 0016 (initial-scan-preview-and-approval) → cli-spec.md に統合
```

残す ADR (8-10 本想定):

```
0001 rust-workspace-split
0002 sqlite-as-default-store
0003 bm25-engine-choice
0004 vector-store-choice
0006 evidence-pointer-immutability
0008 archive-all-by-default
0010 → 0024 rename to local-first   (改名後はこちらだけ残す)
0011 default-global-search
0012 history-purge-for-legal-erasure
0013 folder-local-kcs-per-directory
0015 adapters-are-device-local
```

新規追加 (実装前確定):

```
0017 positioning-core-v2          (Local-first powered by frontier AI)
0018 no-normalized-hash
0019 hash-vs-semantic-fingerprint
0020 truth-vs-cache-two-layer
0021 incremental-markdownize-required
0022 tool-profile-hash-spec
0023 mvp-phase-plan
0025 markdown-first-instance-wins
0026 doc-consolidation-policy
```

統合後の ADR は 8-10 本程度に収める。10 本を超える場合は再度マージ判断。

---

# 5. 統合中の作業ルール

```
- 移動先が決まらない記述は design-homework.md に寄せて温存する。
  捨てない。後で評価する。
- 旧ファイルは削除せず docs/research/_archived/ に移動。
  実体は git history で追える。
- 新統合先には旧出典 (research/diff.md §13 等) を脚注で残す。
  ロスト防止。
- 用語の最終確定は 12.7 命名リネーム表 (productization_notes.md) を正本にする。
- リンク切れは grep で機械的に検出: `grep -rn "research/<old>" docs/`
```

---

# 6. ゲート後の規律

凍結後の規律:

```
- ドキュメント修正は ADR と対で行う。本文だけの書き換えは禁止。
- Phase 4-5 のドキュメントは Step 4 完了後まで深掘りしない。
- Step 1-4 の実装中に発見した致命的設計誤りは ADR で撤回・修正。
- "綺麗にする" 目的の修正は Step 1-4 完了後に再開可能。
```

---

# 7. 凍結を破る条件

以下の場合のみ、Step 実装中でもドキュメントを書き換えてよい:

```
1. Step 1-4 で実装が物理的に不可能と判明した設計
   → ADR で撤回し、対応する正本を更新
2. 外部 Agent との互換性を破壊する変更
   → evidence-pointer-spec.md / adapter-spec.md / cli-spec.md は更新
3. データ破壊リスクのある誤り
   → 即座に修正
```

それ以外の「綺麗にする」「より良い表現にする」は Step 4 完了後に回す。
