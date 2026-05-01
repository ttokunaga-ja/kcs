# Embedding Processing Adapter

> 正本: `adapter-overview.md` と `requirements.md §11`。

## 役割

Embedding 処理 Adapter は chunk object から embedding object を生成する。Embedding object は正本ではなく、`chunk_hash + embedding_profile_hash` から再構築可能な派生 artifact として扱う。

```text
chunk_hash + embedding_profile_hash
  -> embedding_object_hash
```

## Profile

```text
embedding_profile_hash:
  adapter_id
  model_family
  version
  dimensions
  distance
  pooling
```

profile が一致しない場合、KCS は vector 検索を無理に実行せず、再生成タスクを作るか全文検索へ fallback する。
