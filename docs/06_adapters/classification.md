# Classification Adapter

> 正本: `adapter-overview.md`。Classification Adapter は optional Adapter である。

## 役割

Classification Adapter は、raw object、normalized object、chunk、image object に対して分類ラベルや routing metadata を付与する。

```text
raw / normalized / chunk / image object
  -> Classification Adapter
  -> labels / categories / routing metadata
```

用途:

```text
文書種別分類
フォルダ候補
秘匿・法務ラベル
検索 facet
処理 routing
```

## Profile

```text
classification_profile_hash:
  adapter_id
  execution_mode
  label_schema_hash
  model_or_rule_family
  version
```

分類結果は検索・整理の補助情報であり、raw / normalized / chunk object の正本性を変更しない。
