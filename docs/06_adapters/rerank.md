# Rerank Adapter

> 正本: `adapter-overview.md`。Rerank Adapter は optional Adapter であり、KCS core の検索結果を再順位付けする。

## 役割

Rerank Adapter は、全文検索・vector search・hybrid fusion で得られた候補を、query と候補情報に基づいて再順位付けする。

```text
query + candidate results
  -> Rerank Adapter
  -> reranked results
```

Rerank Adapter は検索 scope、excluded scope、fallback reason を隠してはならない。KCS core の検索対象決定やアクセス制御を迂回しない。

## Profile

```text
rerank_profile_hash:
  adapter_id
  execution_mode
  model_or_rule_family
  version
  input_feature_schema_hash
```

オンライン API へ送信する場合は、候補本文・画像・metadata のどれを送ったかを task state に記録する。
