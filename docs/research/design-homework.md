# Design Homework — 実装で必ずぶつかる 4 論点

実装着手前に確定すべき 4 論点を集約した index。各項目は対応する正本ドキュメントで明文化される。本書はステータス追跡を担う。

> **Step 1 着手前**: (1) と (4) を確定。
> **Step 3 着手前**: (2) と (3) を確定。
> 4 論点が確定するまで、そのステップに着手しない。

---

# 1. Markdown 非決定性の運用

**問題**: 同じ `(raw_hash, tool_profile_hash)` から複数回 Markdownize を実行した結果が、LLM の非決定性により異なる可能性がある。Markdown 側 content hash は持たない設計なので、何が「正しい結果」かを定義する必要がある。

**落としどころ (採用案)**:

```
First-instance wins: 最初に確定したインスタンスを永続化。
                     以後は同 identity で再生成しない。

実装規約:
- normalization_run のキャッシュヒット判定で短絡する
  (raw_hash + tool_profile_hash + status=done が見つかれば再実行しない)
- 例外: kcs reindex --force で明示再生成を要求した場合のみ上書き
- 上書き時は parent_run_id でチェーンを残す
```

**正本**: data-model.md (統合後) / 暫定: [hash.md](hash.md), [diff.md §6.1](diff.md)

**Status**: 案あり。ADR 0025 として起票予定。Step 1 着手前に確定。

---

# 2. remarkdownize の CLI セマンティクス

**問題**: 別 LLM (新しい tool_profile_hash) で再変換すると chunk 全体が別物になる。既存 Evidence Pointer は古い `tool_profile_hash` の chunk_hash を指し続けるため、最新 Markdown には到達しない。

**設計判断 (確定)**: これは **設計として正しい**。Evidence Pointer は「過去の根拠」を保証するものであり、最新 Markdown を保証するものではない。

**未確定の論点**: 「最新 Markdown へ pointer を切り替える」操作 (Git の cherry-pick / rebase 相当) のセマンティクス。

**設計案 (検討中)**:

```bash
# 既存 pointer を最新 tool_profile_hash で生成された chunk へ「再ターゲット」
kcs evidence retarget <pointer> [--latest|--at <commit>]

# 動作:
# - 同一 raw_hash 配下で最新の Markdownize 結果を取得
# - heading_path / span を semantic_fingerprint で対応付ける
# - 対応が見つかれば新 chunk_hash を返す。曖昧なら候補リスト
# - 元 pointer は不変。新 pointer が返る (履歴に retargeted_from を保持)
```

**未決事項**:
- `--latest` のデフォルト挙動 (自動 retarget か、提案のみか)
- 対応が見つからなかった場合のエラーコード
- AI Agent からの呼び出し API (agent-api.md)

**正本**: cli-spec.md / runtime.md (統合後)

**Status**: 設計案あり。Step 3 着手前に確定。

---

# 3. Dead Evidence Pointer のセマンティクス

**問題**: ADR 0006 (Evidence Pointer の不変性) と ADR 0012 (法務 purge) の緊張領域。purge された raw_hash を指す既存 pointer の挙動が未定義。

**設計案 (検討中)**:

```
purge 後の pointer 解決:
1. raw_hash が tombstone を持つ場合 → tombstone レスポンスを返す
   {
     "status": "purged",
     "purged_at": "2026-04-25T12:00:00Z",
     "purged_reason": "legal" | "privacy" | "misingest",
     "commit": "kcs_01H...",
     "raw_hash": "sha256:..."
   }
2. raw_hash が完全削除 (履歴書き換え) された場合 → not_found エラー
   error_code: KCS-E-PURGE-NOT-FOUND-001

検出 API:
kcs evidence verify <pointer> [--strict]
  → status=alive | tombstoned | not_found
  → AI Agent が過去回答の pointer を verify するために用意
```

**未決事項**:
- tombstone がデフォルトか、完全削除がデフォルトか (法務要件次第)
- AI Agent から bulk verify する API のスループット要件
- tombstone 自体を purge する操作 (二重 purge) の有無

**正本**: runtime.md (統合後) / evidence-pointer-spec.md (新規)

**Status**: 設計案あり。Step 3 着手前に確定。

---

# 4. Incremental Markdownize のプロンプト規約

**問題**: 「旧 raw + 旧 Markdown + 新 raw を LLM に入力して差分更新」という挙動を adapter 実装ごとに任せると、結果がブレて Evidence Pointer の安定性が損なわれる。

**設計案 (検討中)**:

```
KCS が Adapter に渡す入力 schema (固定):
{
  "mode": "incremental",
  "new_raw":  { "path": "...", "raw_hash": "..." },
  "previous": {
    "raw":               { "path": "...", "raw_hash": "..." },
    "normalized_units":  [...],
    "tool_profile_hash": "..."
  },
  "hints": {
    "changed_unit_keys":  ["page:12"],
    "added_unit_keys":    ["page:57"],
    "removed_unit_keys":  [],
    "page_fingerprints":  {...}
  },
  "tool_profile_hash":   "...",
  "spec_version":        1
}

Adapter からの出力 schema (固定):
{
  "mode_used":           "incremental" | "full",
  "updated_units":       [...],
  "unchanged_unit_keys": [...],
  "added_units":         [...],
  "removed_unit_keys":   [...],
  "fallback_to_full":    false,
  "reason":              null | "..."
}

プロンプト規約 (Adapter 内):
- "unchanged" と判断した unit は出力に含めない (旧 unit を再利用)
- 変更 unit は **完全に書き直す** (部分編集ではなく)。
  これにより Markdown の局所一貫性を保つ
- heading 構造の変更は KCS には影響しない (chunk side で対応)
- Adapter が「軽微とは言えない」と判断したら fallback_to_full=true で短絡
```

**未決事項**:
- spec_version の bump 規約 (RFC 8785 JCS との関係)
- "fallback_to_full" の判断閾値の Adapter 側ヒント (KCS 側 hint との衝突)
- ストリーミング応答の有無 (大型 PDF で TTFB が長くなる問題)

**正本**: adapter-spec.md (統合後) / 暫定: [diff.md §6.1](diff.md)

**Status**: schema は確定済み。プロンプト規約のレベルが未確定。Step 1 着手前に確定 (Step 2 で実装するため)。

---

# 5. 進行ステータス管理

```
Status:
  draft         案を書いた段階。レビュー前。
  reviewing     設計レビュー中。
  decided       採用案が決まった。ADR 起票準備中。
  finalized     ADR 採番済み。正本ドキュメントに反映済み。
```

| # | 項目 | Status | 期日 (Step) | ADR |
| --- | --- | --- | --- | --- |
| 1 | Markdown 非決定性 = first-instance-wins | decided | Step 1 着手前 | 0025 (起票予定) |
| 2 | remarkdownize CLI セマンティクス | draft | Step 3 着手前 | 未採番 |
| 3 | Dead Evidence Pointer | draft | Step 3 着手前 | 未採番 |
| 4 | Incremental Markdownize プロンプト規約 | draft → decided 部分あり | Step 1 着手前 | 未採番 |

---

# 6. 凍結後の扱い

[consolidation-plan.md](consolidation-plan.md) の凍結ゲート後、未確定 (draft) のままステップに到達した項目は **そのステップを着手しない**。設計を先に進める方が、実装中に手戻りするより安価。
