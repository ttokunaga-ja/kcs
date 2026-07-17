# Research Notes

このディレクトリは、LLM 出力由来の研究メモを **要点版に圧縮した保管場所** です。正本ではありません。

正本は [`../README.md`](../README.md) と `../01-` から `../10-` の spec です。Research と spec が矛盾する場合は spec を優先します。削った原文は Git 履歴から復元できます。

---

# 1. 使い方

```text
実装判断              → docs/01- から docs/10- を読む
設計経緯の要点        → docs/research/ の該当メモを読む
LLM 生出力の原文       → git history から復元する
Phase 4+ の構想確認    → auto_organize.md / synchronization.md を読む
```

Research note は「なぜそう決めたか」を短く残す場所です。仕様の詳細、schema、CLI、実装契約は正本 spec に集約します。

---

# 2. 分類

| File | 主題 | 主な正本 |
| --- | --- | --- |
| [philosophy.md](philosophy.md) | 理念、Git/VCS から借りる思想 | [02-philosophy.md](../02-philosophy.md), [01-positioning.md](../01-positioning.md) |
| [git_kcs.md](git_kcs.md) | CAS、snapshot DAG、scope | [03-data-model.md](../03-data-model.md), [05-runtime.md](../05-runtime.md) |
| [kcs.md](kcs.md) | `.kcs` layout、tool-lock、manifest | [03-data-model.md](../03-data-model.md), [07-adapter-spec.md](../07-adapter-spec.md) |
| [hash.md](hash.md) | identity、`tool_profile_hash`、up-to-date 判定 | [03-data-model.md](../03-data-model.md), [07-adapter-spec.md](../07-adapter-spec.md) |
| [read_only.md](read_only.md) | Normalized Markdown の読み取り専用境界 | [03-data-model.md](../03-data-model.md), [08-evidence-pointer-spec.md](../08-evidence-pointer-spec.md) |
| [diff.md](diff.md) | prepared units、差分、incremental Markdownize | [04-pipeline.md](../04-pipeline.md), [07-adapter-spec.md](../07-adapter-spec.md) |
| [markdown.md](markdown.md) | Markdownize Adapter 選定 (Mistral OCR vs Gemini) | [07-adapter-spec.md](../07-adapter-spec.md), [04-pipeline.md](../04-pipeline.md) |
| [db.md](db.md) | SQLite、FTS5、sqlite-vec、検索 backend | [04-pipeline.md](../04-pipeline.md), [05-runtime.md](../05-runtime.md) |
| [batch.md](batch.md) | task、retry、resume、budget | [04-pipeline.md](../04-pipeline.md), [06-cli-spec.md](../06-cli-spec.md) |
| [hybrid.md](hybrid.md) | hybrid search、fallback、cursor、MMR | [05-runtime.md](../05-runtime.md) |
| [commit_snapshot.md](commit_snapshot.md) | commit/snapshot、GC、purge、retention | [05-runtime.md](../05-runtime.md) |
| [productization_notes.md](productization_notes.md) | 横断運用、scope registry、security | [10-operations.md](../10-operations.md) |
| [consolidation-plan.md](consolidation-plan.md) | ドキュメント統合計画の記録 | [README.md](../README.md), [09-mvp-scope.md](../09-mvp-scope.md) |
| [design-homework.md](design-homework.md) | 実装前に残る論点 | [09-mvp-scope.md](../09-mvp-scope.md), [08-evidence-pointer-spec.md](../08-evidence-pointer-spec.md) |
| [north-star-scenarios.md](north-star-scenarios.md) | Phase 3 Done 条件 | [09-mvp-scope.md](../09-mvp-scope.md) |
| [auto_organize.md](auto_organize.md) | Phase 4+ 自動整理構想 | なし。将来構想 |
| [synchronization.md](synchronization.md) | v2 / Phase 5+ 同期構想 | なし。将来構想 |
| [folder-history-sqlite-design.md](folder-history-sqlite-design.md) | SQLite 正本方式のフォルダ履歴 + AI 検索の独立設計検討 (KCS 対比、2026-07-14 確定、多エンジン監査 r8〜r20 済み) | 正本方式 (metadata.sqlite = truth) は KCS と独立のまま。監査で固めた機構 (Batch 2 相プロトコル / スキャン安全 / 採用条件 / 検索実装規則) は 2026-07-18 に KCS spec へ選別移植し、**記録ストアの SQL 正本も同日確定** (cost-ledger.sqlite: `cost_ledger` / `batch_requests` の 2 表 — 旧 JSONL 3 ファイル構成を廃止) — [04-pipeline.md §1.1/§5.4/§5.8](../04-pipeline.md)、[07-adapter-spec.md §5.7](../07-adapter-spec.md)、[06-cli-spec.md §1](../06-cli-spec.md)、[10-operations.md §1/§7.5.3](../10-operations.md)、[05-runtime.md §1.3/§6](../05-runtime.md) |

---

# 3. 編集ルール

```text
- Research は短く保つ。詳細仕様は正本へ移す。
- LLM 出力を貼る場合は、先に要点へ圧縮してから追加する。
- 旧語彙はそのまま増やさない: offline-first, normalized_hash, 正本=research など。
- MVP と Phase 4+ を混ぜない。
- 正本へ移した内容は Research に重複させない。
```

新しいメモの冒頭テンプレート:

```markdown
> Research note
> Status: raw | reviewed | integrated | archived
> Canonical refs: ../03-data-model.md
> Scope: one-line topic

---
```

Status:

```text
raw         要点化前。なるべく残さない。
reviewed    内容確認済み。正本との差分あり。
integrated  正本へ必要部分を移植済み。
archived    採用しないが経緯として残す。
```
