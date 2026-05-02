# 08 Evidence Pointer Spec

KCS の中核概念 **Evidence Pointer** の正式仕様。外部 AI Agent や他ツールが KCS と相互運用する際の契約となるため、独立 spec として保持する。

> 関連: [03-data-model.md §1, §5](03-data-model.md) (CAS / identity) / [05-runtime.md §3](05-runtime.md) (purge / Dead Pointer) / [02-philosophy.md](02-philosophy.md) (なぜ Evidence Pointer か)

---

# 1. なぜ Evidence Pointer か

通常のファイル検索ツールは「path + 行番号」で根拠を指す。これは:

- ファイル移動・リネームで死ぬ
- 削除で死ぬ
- 上書き保存で意味が変わる
- 過去版に戻れない

KCS は **path ではなく content-addressed object** で根拠を指すことで、これらの脆弱性を排除する。

```
通常:  "report.pdf:42"                  → 移動・リネーム・削除で死ぬ
KCS:   commit + raw_hash + chunk_hash   → ファイル移動・リネーム・削除に耐える
       + path_at_commit + span            (purge されない限り永続)
```

これは KCS の差別化の中核 ([01-positioning.md](01-positioning.md))。

---

# 2. Evidence Pointer のスキーマ

```json
{
  "schema_version": 1,
  "commit": "kcs_01H...",
  "tree": "tree_abc",
  "raw_hash": "sha256:abc123...",
  "tool_profile_hash": "sha256:tool1...",
  "chunk_hash": "sha256:chunk456...",
  "path_at_commit": "docs/report.pdf",
  "heading_path": ["認証仕様", "API Token", "有効期限"],
  "section_id": "auth/api-token/expiry",
  "char_start": 1200,
  "char_end": 1500,
  "scope_path": "/Users/foo/Research/.kcs"
}
```

## 2.1 必須フィールド

| フィールド | 役割 | 不変条件 |
| --- | --- | --- |
| `schema_version` | Evidence Pointer schema の semver | breaking change で bump |
| `commit` | snapshot DAG の commit_id | 該当 commit が purge されない限り解決可能 |
| `raw_hash` | 原文バイト列の identity | 移動・リネームで不変 |
| `tool_profile_hash` | Markdownize Adapter capability の identity | tool 変更で別 chunk に飛ばない保証 |
| `chunk_hash` | chunk object の identity | `(raw_hash, tool_profile_hash, span)` から導出 |
| `scope_path` | 正本 `.kcs` の絶対パス | truth レイヤーへの直接参照 |

## 2.2 Optional フィールド

| フィールド | 役割 |
| --- | --- |
| `tree` | 当該 commit の tree object id (高速解決用) |
| `path_at_commit` | commit 時点の表示用 path (UI 表示・人間可読性) |
| `heading_path` / `section_id` | chunk の構造的位置 (UI 表示・semantic retarget 用) |
| `char_start` / `char_end` | normalized Markdown 内の文字 span |

`path_at_commit` は **表示用** であり、解決には使わない。実際の解決は `commit + raw_hash` で行う (path はリネーム履歴をまたいでも追えるが、root 信頼は raw_hash 側)。

---

# 3. Evidence Pointer の解決

```
入力: Evidence Pointer
出力: { raw_object | normalized_unit | chunk_text } または error
```

## 3.1 解決手順

```
1. scope_path の .kcs を開く
2. commit を refs / objects/commits/ から取得
3. tree (commit.tree) を取得
4. tree から raw_hash で entry を検索
5. raw_hash が tombstone を持つなら → tombstone を返す (§4)
6. raw_hash + tool_profile_hash で normalized_unit を解決
7. chunk_hash で chunk object を解決し char_start/char_end の text を取り出す
```

## 3.2 不変条件

```
解決成功条件:
  - commit が存在
  - commit が shallow GC されていない (= tree が残っている)
  - raw object が存在 (purge されていない)
  - chunk object が存在 (= 同一 tool_profile_hash で生成済み)

部分的失敗:
  - shallow commit:        commit は表示できるが tree なし
                           → KCS-E-COMMIT-SHALLOW-001
  - purged raw_hash:       tombstone を返す (§4) または NOT-FOUND
  - tool_profile_hash 不一致: chunk が存在しない場合は retarget が必要 (§5)
```

---

# 4. Dead Evidence Pointer (purge 対応)

「Evidence Pointer の不変性」(§6) と「法務 purge」([05-runtime.md §3](05-runtime.md)) の緊張領域。purge された raw_hash を指す既存 pointer の挙動を以下に固定する (採用案。実装着手後の最終確定は [09-mvp-scope.md §5.3](09-mvp-scope.md))。

## 4.1 Tombstone レスポンス

raw_hash が tombstone を持つ場合 (= purge 済みだが履歴上は記録):

```json
{
  "status": "purged",
  "purged_at": "2026-04-25T12:00:00Z",
  "purged_reason": "legal" | "privacy" | "misingest" | "copyright" | "other",
  "purged_in_commit": "kcs_01H...",
  "raw_hash": "sha256:abc...",
  "scope_path": "/Users/foo/Research/.kcs"
}
```

「消した事実」は残し、本文・派生 artifact は到達不能にする (= 透明な忘却、[02-philosophy.md](02-philosophy.md))。

## 4.2 NOT-FOUND レスポンス

raw_hash が完全削除 (履歴書き換え) されている場合:

```
error_code: KCS-E-PURGE-NOT-FOUND-001
message: "Evidence target was purged with full history rewrite"
context: { raw_hash, scope_path }
```

完全削除は法的要件上必要な場合のみ。デフォルトは tombstone。

## 4.3 検証 API

AI Agent が過去回答で使った Evidence Pointer の生存確認用:

```bash
kcs evidence verify <pointer-or-json> [--strict]
```

```json
{
  "status": "alive" | "tombstoned" | "not_found",
  "details": { ... }
}
```

`--strict`: tombstoned と not_found の両方を **error** として扱う (CI / 自動化用)。

bulk verify:

```bash
kcs evidence verify --batch <pointers.jsonl>
# 各行が pointer JSON。各行に対する status を返す
```

---

# 5. Retarget (最新版へ pointer を切り替える)

別 LLM で再 Markdownize すると `tool_profile_hash` が変わり chunk が別物になる。既存 Evidence Pointer は古い `tool_profile_hash` の chunk を指し続ける (これは設計として正しい)。

「最新 Markdown へ pointer を切り替える」のは **明示操作** ([09-mvp-scope.md §5.2](09-mvp-scope.md), 設計確定後に本仕様に昇格):

```bash
kcs evidence retarget <pointer> [--latest|--at <commit>]
```

```json
// 入力 pointer は不変。新しい pointer を返す
{
  "status": "retargeted",
  "new_pointer": { ...更新後... },
  "retargeted_from": "<old_pointer>",
  "match_method": "heading_path_exact" | "heading_path_fuzzy" | "semantic_fingerprint",
  "confidence": 0.92
}
```

```json
// 対応が見つからない場合
{
  "status": "ambiguous",
  "candidates": [...],
  "error_code": "KCS-E-EVIDENCE-RETARGET-AMBIG-001"
}
```

retarget は **AI Agent からの呼び出しを前提** にしているため、API 形は 06-cli-spec.md と agent-api と同形を保つ。

---

# 6. 不変性保証 (immutability guarantee)

```
- 既存 Evidence Pointer は KCS によって書き換えられない
- raw_hash / chunk_hash / tool_profile_hash / commit は append-only
- pointer の意味する場所 (= 生成時に解決可能だった raw + chunk) は purge されない限り解決可能
- 解決失敗は schema 上区別される (shallow / tombstoned / not_found)
- "古い pointer" を "最新版" に勝手に飛ばさない (retarget は明示操作)
```

これは AI Agent が KCS から取得した Evidence を **長期参照** できる契約となる。

---

# 7. 外部 Agent との相互運用

KCS は Evidence Pointer を **JSON object として AI Agent に返す**。Agent はこれを記憶し、後続の検証・参照・引用に使える。

## 7.1 検索結果に含める形

```json
{
  "results": [
    {
      "score": 0.87,
      "evidence_pointer": { /* §2 schema */ },
      "preview": "API Token の有効期限は 30 日です..."
    }
  ]
}
```

Agent は `evidence_pointer` を保存し、後続のセッションで以下を実行できる:

```
- kcs evidence verify <pointer>     生存確認
- kcs view <pointer>                該当 chunk の Markdown 取得
- kcs open <pointer>                原本ファイルを OS で開く
- kcs evidence retarget <pointer>   最新版への切り替え (要承認)
```

## 7.2 引用フォーマット (人間向け)

UI / レポートでは Evidence Pointer を以下に整形して表示することを推奨:

```
[docs/report.pdf @ kcs_01H... > 認証仕様 > API Token > 有効期限]
                ↑               ↑                       ↑
                path_at_commit  heading_path            section
```

完全な hash は折りたたみ可能。

---

# 8. Evidence Pointer Schema 互換性

`schema_version` の semver 規約:

```
MAJOR  必須フィールド削除 / 既存フィールド意味変更    migration 必須
MINOR  新フィールド追加 (default で旧データを補える)
PATCH  typo / コメント修正
```

`path_at_commit` / `heading_path` 等の optional フィールドは **MINOR 互換** で追加してよい。`raw_hash` / `chunk_hash` / `commit` の意味変更は **MAJOR 扱い** (= migration plan + ユーザー通知)。

新 schema は古い解決ロジックでもエラーなく扱えること (forward compatible) を要件とする (= 未知フィールドは無視)。
