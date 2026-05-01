# Embedding Adapter

> 正本: `adapter-overview.md` と `requirements.md §11`。

## 役割

Embedding Adapter は、Markdown chunk、Image Object、検索クエリを同一のマルチモーダル Embedding 空間へ写像する。Text Embedding Adapter と Image Embedding Adapter は採用しない。

```text
Normalized Markdown chunk
Image Object
Query text
  -> Embedding Adapter
  -> vector
```

Embedding object は正本ではなく、`target_hash + embedding_profile_hash` から再構築可能な派生 artifact として扱う。

## 入力

対象入力は複数種類を許可する。

```text
text
image
markdown_chunk
image_object
query
```

Text chunk:

```json
{
  "input_type": "text",
  "items": [
    {
      "id": "chunk_001",
      "text": "## API認証\nトークンの有効期限は..."
    }
  ]
}
```

Image object:

```json
{
  "input_type": "image",
  "items": [
    {
      "id": "image_001",
      "path": ".kcs/objects/images/ab/cd/image.png",
      "mime": "image/png"
    }
  ]
}
```

Query:

```json
{
  "input_type": "query",
  "items": [
    {
      "id": "query_001",
      "text": "売上が急増しているグラフ"
    }
  ]
}
```

## 出力

```json
{
  "ok": true,
  "vectors": [
    {
      "id": "chunk_001",
      "vector": [0.01, 0.02, 0.03]
    }
  ],
  "dimensions": 1536,
  "distance": "cosine",
  "modality": "multimodal",
  "metadata": {
    "adapter": "gemini-embedding-2",
    "mode": "batch"
  }
}
```

## Profile

```text
embedding_profile_hash:
  adapter_id
  model_family
  version
  dimensions
  distance
  modality
  supported_input_types
  pooling
```

profile が一致しない場合、KCS は vector 検索を無理に実行せず、再生成タスクを作るか全文検索へ fallback する。

## 検索時の扱い

```text
query text
  -> Embedding Adapter
  -> query vector
  -> chunk vector search
  -> image vector search
  -> fusion
```

インデックスは物理的には分けてもよい。

```text
chunk_vec
image_vec
```

ただし概念上は、同じ Embedding Adapter、同じ `profile_hash`、同じ vector space である。

## DB 要件

概念上は1つの `embeddings` テーブルで表現できる。

```sql
CREATE TABLE embeddings (
  id TEXT PRIMARY KEY,
  target_type TEXT NOT NULL, -- chunk | image | node | query_cache
  target_id TEXT NOT NULL,
  modality TEXT NOT NULL,    -- text | image | multimodal
  vector BLOB NOT NULL,
  dimensions INTEGER NOT NULL,
  distance TEXT NOT NULL,
  profile_hash TEXT NOT NULL
);
```

sqlite-vec の制約で vector table を分ける場合でも、metadata は同じ `profile_hash` と `modality = "multimodal"` で統合する。

## tool-lock.json

```json
{
  "embedding": {
    "tool_id": "embed_multimodal",
    "kind": "command",
    "cmd_hash": "sha256:...",
    "args_hash": "sha256:...",
    "config_hash": "sha256:...",
    "mode": "batch",
    "dimensions": 1536,
    "distance": "cosine",
    "modality": "multimodal",
    "profile_hash": "sha256:..."
  }
}
```

## .kcs/config.toml

```toml
[tools]
embedding = "gemini_multimodal_embedding"
```

## 採用しない設計

```text
Image Embedding Adapter
Text Embedding Adapter
画像説明文を経由した二段階 Embedding
Image 専用 Embedding Adapter
```
