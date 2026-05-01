# Summary Adapter

> 正本: `adapter-overview.md`。Summary Adapter は optional Adapter であり、特定のモデル実装名には依存しない。

## 役割

Summary Adapter は normalized object、chunk、検索結果から summary artifact を生成する。生成結果は入力 hash と profile に紐付け、同じ入力に対して既存 summary を再利用できるようにする。

```text
normalized_hash | chunk_hash | search_result_id
  -> Summary Adapter
  -> summary_hash
```

## Profile

```text
summary_profile_hash:
  adapter_id
  adapter_family
  version
  summary_kind
  max_input_tokens
  output_policy
```

オンライン API へ送信する場合は、対象 scope とネットワーク送信許可を KCS API の task state に残す。オフライン API や決定論的ライブラリの場合も、execution_mode と profile を記録する。
