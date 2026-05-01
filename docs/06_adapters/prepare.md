# Prepare Adapter

> 正本: `adapter-overview.md`。Prepare Adapter は raw object を後続処理が扱いやすい prepared object / prepared unit に分割・変換する。

## 役割

Prepare Adapter は、Markdownize Adapter と Embedding Adapter の前段で、入力ファイルを安定した処理単位へ変換する。

```text
raw object
  -> Prepare Adapter
  -> prepared object / prepared unit / image object
```

例:

```text
PDF -> page image units
PPTX -> slide units
XLSX -> sheet units
DOCX -> page-like or heading-like units
image file -> image object
audio file -> audio prepared unit
```

## Profile

```text
prepare_profile_hash:
  adapter_id
  execution_mode
  tool_family
  version
  unit_strategy
  fingerprint_strategy
```

Prepare Adapter が決定論的ライブラリで実装できる場合は、`execution_mode = deterministic_library` を優先する。
