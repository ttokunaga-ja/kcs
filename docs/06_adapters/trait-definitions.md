# Adapter Trait Definitions

> 正本: `adapter-overview.md`。実装時の Rust trait 名は変わってよいが、入出力契約はこの粒度を保つ。

## 共通メタデータ

すべての Adapter は、実行設定そのものではなく profile と artifact の対応だけを KCS core に返す。

```text
AdapterProfile:
  adapter_kind
  adapter_id
  tool_profile_hash
  version
  capability_flags
  allow_network

AdapterRun:
  task_id
  input_hashes
  output_hashes
  status
  error_kind
```

## Markdown 処理 Adapter

OCR は独立した top-level Adapter ではなく、この Adapter の capability として表現する。

```text
MarkdownProcessor:
  input: raw_hash, media_type, prepared_unit_hint
  output: normalized_hash, unit_hashes, evidence_pointers
  capability_flags: ocr, layout_detection, table_extraction, speech_to_text
```

## Embedding 処理 Adapter

```text
Embedder:
  input: chunk_hashes, embedding_profile_hash
  output: embedding_object_hashes
  metadata: dimensions, distance, model_family
```

## 検索代行 Agent Adapter

```text
SearchAgent:
  input: query, scope, time_range, mode
  output: ranked_context, searched_scopes, excluded_scopes, fallback_reason
```

検索代行 Agent は KCS core の検索 API を利用し、scope や fallback 情報を隠してはならない。

## 要約 Agent Adapter

```text
SummarizerAgent:
  input: normalized_hashes | chunk_hashes | search_result_ids
  output: summary_hash
  metadata: agent_profile_hash, source_hashes, summary_kind
```
