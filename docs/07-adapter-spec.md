# 07 Adapter Spec

Adapter (Prepare / Markdownize / Embedding / Summary / Classification / Rerank) の trait 契約 + 実行形態 + Markdown incremental プロンプト規約。

> 関連: [03-data-model.md §5](03-data-model.md) (`tool_profile_hash` 計算規約) / [04-pipeline.md §3](04-pipeline.md) (incremental Markdownize) / [06-cli-spec.md §9](06-cli-spec.md) (Agent/Adapter API)

---

# 1. 基本方針

Prepare / Markdownize / Embedding / Summary / Classification / Rerank は KCS core に含めず、**Adapter に委譲** する。OCR は Markdownize Adapter の **内部能力 (capability)** として扱う。Embedding は Text / Image を分離せず、**単一マルチモーダル Embedding Adapter** に統合する。

```
KCS core:                 Adapter:
  object store              Prepare
  snapshot                  Markdownize (OCR は内部能力)
  restore                   Embedding (multimodal)
  search                    Summary       optional
  task state                Classification optional
  common KCS API            Rerank        optional
```

Adapter の実行設定 (cmd / args / url / 認証情報) は **`.kcs/` の共有対象に含めない**。各デバイスの `~/.config/kcs/tools.toml` や OS keychain に保存する。`.kcs/` は生成済み artifact の provenance と互換性判定に必要な `profile_hash` だけを保持する。

---

# 2. 実行形態

Adapter は **提供主体ではなく実行形態と決定性** で分類する。

```
online_api               LLM 等のネットワーク越し API (frontier AI が中心)
                         明示的な network opt-in が必要
offline_api              ローカル LLM / ローカル embedding server
                         ネット送信なし。非決定的出力はあり得る
deterministic_library    決定論的ライブラリ (PDF text extraction, parser)
                         同じ入力 + 同じ profile なら同じ出力
```

KCS API の契約は実行形態に依らず同じ。

```
KCS core
  → task descriptor (task_id, adapter_kind, input_hash, allowed scope, network permission)
  → device-local Adapter
  → artifact descriptor (output_hash, status, error_kind)
  → KCS core
```

---

# 3. ネットワーク送信原則

KCS core は、**明示オプトインなしにネットワーク越し API へファイル内容を送信してはならない**。

```toml
default:           no network transmission

explicit opt-in:
  CLI:           --online
  config:        adapter.policy.allow_network = true
```

オンライン API Adapter を使う場合、ユーザーがどの scope / file / task を送信対象にしたかを記録する。オフライン API / 決定論的ライブラリの場合も `execution_mode` と `profile_hash` は記録する。

---

# 4. 共通メタデータ

すべての Adapter は次を返す:

```
AdapterProfile:
  adapter_kind          "prepare" | "markdownize" | "embedding" | ...
  adapter_id
  execution_mode        "online_api" | "offline_api" | "deterministic_library"
  tool_profile_hash     計算規約は 03-data-model.md §5.1
  version
  capability_flags      ["ocr", "layout_detection", "incremental_update", ...]
  allow_network

AdapterRun:
  task_id
  input_hashes
  output_hashes
  status                "pending" | "running" | "done" | "failed"
  error_kind            error_code (06-cli-spec.md §8)
```

---

# 5. 各 Adapter の trait

## 5.1 Prepare

```
input:
  raw_hash, media_type
output:
  prepared_object_hashes
  prepared_unit_hashes        (page / slide / sheet / image 単位)
  image_object_hashes         (画像抽出があれば)
metadata:
  unit_kind, page_number, mime, fingerprint (semantic_fingerprint)
```

PDF page image、Office intermediate、抽出済み image など、後続 Markdownize / Embedding が扱いやすい単位を作る。

## 5.2 Markdownize

OCR は独立 Adapter ではなく **本 Adapter の capability** として表現する。

```
input:
  raw_hash, media_type
  prepared_unit_hint          (optional)
  mode                        "full" | "incremental"
  previous (incremental 時のみ): { raw, normalized_units, tool_profile_hash }
  hints (incremental 時のみ):   { changed_unit_keys, added, removed, page_fingerprints }
  tool_profile_hash
  spec_version
output:
  mode_used                    "full" | "incremental"
  updated_units / added_units / removed_unit_keys / unchanged_unit_keys
  evidence_pointers
  fallback_to_full             bool
  reason
capability_flags:
  ocr, layout_detection, table_extraction, speech_to_text, incremental_update
```

incremental の詳細プロンプト規約は §8。

## 5.3 Embedding (multimodal)

```
input_type:           "text" | "image" | "markdown_chunk" | "image_object" | "query"
input:
  items: [{ id, text|path, mime? }]
output:
  vectors: [{ id, vector }]
  dimensions, distance, modality
metadata:
  adapter_id, model_family, version, embedding_profile_hash
```

Text Embedding Adapter / Image Embedding Adapter は**採用しない**。同一 Embedding Adapter が同一 profile で多モダリティを単一 vector space へ写像する。

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL,    -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,       -- text | image | multimodal
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);
```

sqlite-vec の制約で vector table を物理分割してもよいが、概念上は単一の Embedding Adapter / 単一の `profile_hash`。profile が一致しない場合、KCS は vector 検索を強行せず再生成または text fallback。

## 5.4 Summary (optional)

```
input:   normalized_hashes | chunk_hashes | search_result_ids
output:  summary_hash
metadata: profile_hash, source_hashes, summary_kind
```

## 5.5 Classification (optional)

```
input:   raw_hashes | normalized_hashes | chunk_hashes | image_object_hashes
output:  labels, categories, confidence, routing_metadata
metadata: profile_hash, label_schema_hash
```

## 5.6 Rerank (optional)

```
input:   query, candidate_result_ids, candidate_features
output:  reranked_result_ids, scores
metadata: profile_hash, searched_scopes, fallback_reason
```

Rerank Adapter は KCS の検索結果を再順位付けするだけで、**searched_scopes / fallback_reason を隠蔽してはならない**。

---

# 6. tool-lock.json

`.kcs/tool-lock.json` は使用 Adapter の identity を記録する。実行可能情報 (`cmd`, `args`, `url`, 認証情報) は **絶対に含めない**:

```json
{
  "spec_version": 1,
  "prepare": {
    "tool_id": "prepare_default",
    "kind": "deterministic_library",
    "profile_hash": "sha256:..."
  },
  "markdown": {
    "tool_id": "markdown_default",
    "kind": "online_api",
    "profile_hash": "sha256:...",
    "capabilities": ["ocr", "layout_detection", "incremental_update"]
  },
  "embedding": {
    "tool_id": "gemini_multimodal_embedding",
    "kind": "online_api",
    "mode": "batch",
    "dimensions": 1536,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

`tool_lock_hash` は `tool-lock.json` 全体を JCS 畳み込みした identity ([03-data-model.md §5.2](03-data-model.md))。

---

# 7. Adapter 実行制約 (policy)

```toml
[adapter.policy]
allow_network = false
allowed_scope = "."
max_input_bytes = 104857600        # 100 MB
timeout_seconds = 300
redact_logs = true
store_request_body = false
store_response_body = false
require_command_confirmation = true
```

任意コマンド/任意 URL を使う Adapter は、**初回実行時** に command / URL / scope / network policy を preview し、ユーザー承認を得る。実装は command allowlist、secret redaction、ログ本文禁止を前提にする。

ログに残してよいもの:

```
task_id, adapter_id, tool_profile_hash
input_raw_hash, output_hash
status, error_kind
started_at, finished_at
```

残してはならないもの:

```
原文本文 / normalized 本文 / API request body / API response body / 秘密情報
```

---

# 8. Incremental Markdownize プロンプト規約

[04-pipeline.md §3.1](04-pipeline.md) で発動条件と入出力 schema を定義した。本節は **Adapter 内部のプロンプト規約** を固定する (Adapter ごとの揺れを防ぐため)。

## 8.1 Adapter が守るべき規約

```
1. "unchanged" と判断した unit は出力に含めない (旧 unit を再利用)
2. 変更 unit は完全に書き直す (部分編集ではなく full unit replacement)
   → Markdown の局所一貫性を保つ
3. heading 構造の変更は KCS には影響しない (chunk side で対応)
4. Adapter が「軽微とは言えない」と判断したら fallback_to_full=true で短絡
   閾値の Adapter 側 hint は KCS 側 hint と衝突したら **KCS 側を優先**
5. spec_version 不一致なら、Adapter は invalid_input として失敗
```

## 8.2 推奨プロンプト構造 (frontier AI 系)

```
SYSTEM:
  You are a markdownization adapter for KCS.
  Given the previous markdown of <unit_key> and the new raw input,
  produce updated markdown for changed units only.
  Keep unchanged units out of the output.

USER:
  Mode: incremental
  Tool profile: <hash>
  Previous markdown for changed units:
    <unit_key_1>: <markdown_1>
    <unit_key_2>: <markdown_2>
  New raw content (relevant pages only):
    <raw_excerpt>
  Hints:
    changed_unit_keys: [...]
    page_fingerprints: {...}

  If you judge the change as non-minor, return fallback_to_full=true
  with a brief reason. Otherwise return updated_units.
```

具体的な system prompt は Adapter 実装で固定し、`prompt_template_hash` (`tool_profile_hash` 入力フィールド) で identity に含める。

## 8.3 ストリーミング応答

大型 PDF (100+ pages) では TTFB を抑えるためストリーミング出力を許容する。KCS は Adapter からの SSE / chunked JSON を受け取り、unit 完了ごとに persist する。

ストリーミング失敗時は完了済み unit のみ commit し、未完了は `pending` で再開可能にする。

## 8.4 Capability 宣言なしの Adapter

`capabilities` に `incremental_update` を含まない Adapter は、KCS が **常に full モード** で呼ぶ。これにより既存 Adapter との後方互換が保たれる。

---

# 9. 再現性ポリシー

Adapter の完全な再実行決定性は要求しない。KCS が保証するのは:

```
raw_hash 不変                既存 artifact を尊重 (first-instance-wins)
raw_hash 変化                 新 artifact 候補を作る
explicit re-normalize         同 raw_hash に対して別 artifact を作る
                              (kcs reindex --force のみ許可)
```

Markdown の content hash は持たない ([03-data-model.md §5](03-data-model.md))。同一 `(raw_hash, tool_profile_hash)` から複数回生成した結果が異なっても、**最初に確定したインスタンスを永続化** し、以後は再生成しない (first-instance-wins)。
