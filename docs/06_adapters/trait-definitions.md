# Adapter Trait Definitions

> 正本: `adapter-overview.md`。実装時の Rust trait 名は変わってよいが、入出力契約はこの粒度を保つ。

## 共通メタデータ

すべての Adapter は、実行設定そのものではなく profile と artifact の対応だけを KCS core に返す。

```text
AdapterProfile:
  adapter_kind
  adapter_id
  execution_mode
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

## Prepare Adapter

```text
Prepare:
  input: raw_hash, media_type
  output: prepared_object_hashes, prepared_unit_hashes, image_object_hashes
  metadata: unit_kind, page_number, mime, fingerprint
```

Prepare Adapter は、後続の Markdownize / Embedding が扱いやすい単位を作る。PDF page image、Office intermediate、抽出済み image object などを生成できる。

## Markdownize Adapter

OCR は独立した top-level Adapter ではなく、この Adapter の capability として表現する。

```text
Markdownize:
  input: raw_hash, media_type, prepared_unit_hint
  output: normalized_hash, unit_hashes, evidence_pointers
  capability_flags: ocr, layout_detection, table_extraction, speech_to_text
```

## Embedding Adapter

```text
Embedding:
  input: text | image | markdown_chunk | image_object | query
  output: vectors
  metadata: dimensions, distance, modality, model_family, embedding_profile_hash
```

Text Embedding Adapter と Image Embedding Adapter は定義しない。単一の Embedding Adapter が、Markdown chunk、Image Object、Query text を同じマルチモーダル vector space へ写像する。

## Summary Adapter

```text
Summary:
  input: normalized_hashes | chunk_hashes | search_result_ids
  output: summary_hash
  metadata: profile_hash, source_hashes, summary_kind
```

## Classification Adapter

```text
Classification:
  input: raw_hashes | normalized_hashes | chunk_hashes | image_object_hashes
  output: labels, categories, confidence, routing_metadata
  metadata: profile_hash, label_schema_hash
```

## Rerank Adapter

```text
Rerank:
  input: query, candidate_result_ids, candidate_features
  output: reranked_result_ids, scores
  metadata: profile_hash, searched_scopes, fallback_reason
```

Rerank Adapter は KCS core の検索結果を再順位付けするだけで、検索 scope や fallback 情報を隠してはならない。
