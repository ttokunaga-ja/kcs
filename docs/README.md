# KCS 設計ドキュメント

> **Local-first knowledge archive, powered by frontier AI.**
> **データはローカル、計算は最強の AI を使う。**

KCS は **local-first** な知識アーカイブ。データの主権はあなたのマシンにあり、Markdownize や Embedding には Gemini / Claude / GPT 等の frontier AI を使う。"offline-first 原理主義" ではない。

二次表現: **Evidence-grounded local knowledge archive (原文根拠付きローカル知識アーカイブ)**。

> **第一価値命題**: 「探せなかったファイルがすぐ見つかる」「根拠が死なない」。

---

# 0. KCS の中核 (3 点)

```
1. Evidence Pointer        path ではなく commit / tree / raw_hash / chunk_hash / span で根拠を指す
2. Markdown 正規化         全ファイル種別を Normalized Markdown に変換、人間と AI が同じビューを使う
3. Content-addressed CAS   全ファイルを CAS object として保存。削除済み・過去版・移動済みでも到達可能
```

最低体験ライン:

```bash
kcs init
kcs snapshot
kcs search "あの PDF"
kcs open
```

# 0.1 ターゲットユーザー

```
- 大量の PDF・Markdown・コード・画像・研究資料を扱う
- 開発者・研究者・技術者
- Git や CLI に抵抗がない
- ローカルファイルが散らかっている
- AI 検索を試したいが、クラウド丸投げは嫌
```

# 0.2 二層構造 — truth と cache

```
truth = folder-local .kcs                正本: raw object / normalized / chunks / commits / refs
cache = scope_registry / aggregator      検索キャッシュ: 探索対象一覧 / stale 検出 / UI 統合
```

`scope_registry` のみで `.kcs` の状態を変える実装は禁止。詳細 [03-data-model.md §4](03-data-model.md)。

---

# 1. ドキュメント構成 と Reading Path

`docs/` 直下を実装スペックの **正本** とし、ファイル名の **数字プレフィックスがそのまま読む順番** を表す。`README.md` (本書) を最初に読み、続いて `01-` から `11-` の順に読めば、概念がぶつからない。

| 順 | ファイル | 役割 |
| --- | --- | --- |
| 0 | [README.md](README.md) | 全体俯瞰・Reading Path (本書) |
| **01** | [01-positioning.md](01-positioning.md) | **★最初に読む**。core 一文 / ターゲット / 差別化の核 / **競合分析 + Perkeep 失敗分析** / 既存ワークフロー / 発言禁止リスト |
| **02** | [02-philosophy.md](02-philosophy.md) | 理念 (Evidence Pointer の根拠、Markdown 正規化の妥協点、忘れない vs purge) |
| **03** | [03-data-model.md](03-data-model.md) | **★契約**: CAS / `.kcs` layout / object 種別 / identity / `tool_profile_hash` / 書き込み境界 / dedup スコープ |
| **04** | [04-pipeline.md](04-pipeline.md) | **★契約**: ingest → prepare → markdownize (incremental) → chunk → embed → index / SQLite schema / batch (retry / budget) |
| **05** | [05-runtime.md](05-runtime.md) | **★契約**: 検索 (paging / MMR / `--at`) / commit_type / GC / purge / restore / time-travel / 並行性 |
| **06** | [06-cli-spec.md](06-cli-spec.md) | CLI 全コマンド / exit code / error code namespace / agent API / observability / GUI 用語翻訳 (Phase 4+) |
| **07** | [07-adapter-spec.md](07-adapter-spec.md) | Adapter trait (Prepare / Markdownize / Embedding / etc.) / 実行形態 / **incremental Markdownize プロンプト規約** |
| **08** | [08-evidence-pointer-spec.md](08-evidence-pointer-spec.md) | Evidence Pointer schema / 解決手順 / **Dead Pointer (purge) のセマンティクス** / retarget / 外部 Agent 相互運用 |
| **09** | [09-mvp-scope.md](09-mvp-scope.md) | MVP scope / Phase 1-5 / Step 1-4 + ripgrep 規模上限 / 北極星シナリオ 3 / 設計宿題 4 / 凍結ゲート |
| **10** | [10-operations.md](10-operations.md) | 横断規約 (semver / 観測ログ / 命名リネーム表 / 初回スキャン承認 / Adapter セキュリティ) |
| **11** | [11-requirements.md](11-requirements.md) | 既存の要件ドラフト (research/ を統合) |

各 spec は前番の概念を前提にできる構成。逆順参照 (例: 03 が 06 を前提) は基本的に発生しない。

## 1.1 設計検討メモ (正本ではない)

| ディレクトリ | 内容 |
| --- | --- |
| [research/](research/) | 設計検討メモ 16 本。**正本ではない**。設計判断の出典・経緯参照用 |

---

# 2. Phase Plan と Step 計画

詳細は [09-mvp-scope.md](09-mvp-scope.md)。

```
Phase 1: Evidence 基盤    raw / normalized / chunk / Evidence Pointer
Phase 2: 検索             FTS5 / sqlite-vec / hybrid (paging / MMR)
Phase 3: 履歴             tree / commit / restore / --at / time-travel
Phase 4: 自動化           auto snapshot / Downloads watch / inbox
Phase 5: Agent            agent API / navigation / neighbors / node / edge
```

Step 計画 (Phase 1-3 を実装):

```
Step 1 (1-2ヶ月): kcs-core + kcs-cli (init/status/commit/log)
Step 2 (2-3ヶ月): kcs-pipeline + kcs-adapter (frontier AI default)
Step 3 (2-3ヶ月): kcs-index + kcs-search (hybrid + Evidence Pointer)
Step 4 (1ヶ月):   restore + --at + time-travel
```

**コア規模上限** (ripgrep 以下): テスト除いて 11-16k LOC、テスト含めて 20-30k LOC。

---

# 3. 北極星シナリオ (Phase 3 完成時の Done 条件)

詳細は [09-mvp-scope.md §4](09-mvp-scope.md)。

```
M3-1: 「3ヶ月前に書いた結論の根拠 PDF を 5 秒以内に出す」
M3-2: 「リネーム済みファイルの過去版を含めて検索」
M3-3: 「削除したはずの資料から特定の数字を再発見」
```

実装中の機能追加は「3 シナリオのどれに resp するか」で判断。該当しないなら Phase 4-5 へ送る。

---

# 4. 設計上の宿題 (4 論点)

詳細は [09-mvp-scope.md §5](09-mvp-scope.md)。

```
1. Markdown 非決定性 = first-instance-wins        Step 1 着手前  decided
2. remarkdownize CLI セマンティクス               Step 3 着手前  draft
3. Dead Evidence Pointer のセマンティクス          Step 3 着手前  draft (採用案 08-evidence-pointer-spec.md §4)
4. Incremental Markdownize プロンプト規約          Step 1 着手前  partial (規約 07-adapter-spec.md §8)
```

未確定 (draft) のままステップに到達したら **そのステップを着手しない**。

---

# 5. 設計判断の正本は spec に閉じる

ADR (Architecture Decision Records) フォルダは廃止しました。本プロジェクトでは:

- **正本は `docs/*.md` の 10 本 spec** (current truth)
- 「なぜそう決めたか」は spec の各セクション冒頭に短く埋め込む (例: `01-positioning.md §1.1`「なぜ local-first であって offline-first ではないか」)
- 設計検討の経緯は `docs/research/` のメモから git history で辿れる

将来、本当に「逆方向の判断もありえた」「外部から問われたら答える義務がある」決定が出てきた時点で、改めて `adr/` を作る方針です。Phase 1 着手前の今、ADR を運用するコストはメリットを上回らないと判断しています ([09-mvp-scope.md §6](09-mvp-scope.md))。

---

# 6. 編集規約

- **形式**: GitHub-flavored Markdown。
- **言語**: 日本語。固有名詞・コード片は原語のまま。
- **コードブロック**: 言語タグ必須 (`bash`, `toml`, `json`, `rust`, `sql`, `text`)。
- **相対リンク**: docs/ ルート相対。
- **スキーマ変更**: 03-data-model.md / 07-adapter-spec.md の変更は破壊的変更扱い。`tool_profile_hash` / `tool_lock_hash` / `commit_type` enum / Evidence Pointer schema の変更には migration plan を伴う。
- **発言禁止フレーズ**:
  - ✗ "Git for knowledge" / "個人 AI アシスタント" / "OS 級" / "Knowledge Graph for personal data" / "Notion / Obsidian キラー"
  - ✗ "offline-first" (誤解を招く。"local-first" を使う)
  - ✗ "private AI" / "機密 AI"
- **採用する語**:
  - ✓ Local-first knowledge archive, powered by frontier AI. (core)
  - ✓ データはローカル、計算は最強の AI を使う。(core 日)
  - ✓ local-first / Evidence-grounded local knowledge archive
  - ✓ Evidence Pointer / time-travel knowledge navigation
- **凍結中の修正**: ドキュメント統合ゲート ([09-mvp-scope.md §6](09-mvp-scope.md)) 完了後の本文書き換えは、Step 1-4 で実装が物理的に不可能と判明した場合 / 外部 Agent 互換性を破壊する変更 / データ破壊リスク、の 3 ケースに限る。それ以外の「綺麗にする」修正は Step 4 完了後。
