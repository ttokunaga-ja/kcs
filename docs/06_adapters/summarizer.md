# Summarization Agent Adapter

> 正本: `adapter-overview.md`。要約は特定のモデル実装名ではなく、要約 Agent Adapter として扱う。

## 役割

要約 Agent Adapter は normalized object、chunk、検索結果から summary artifact を生成する。生成結果は入力 hash と agent profile に紐付け、同じ入力に対して既存 summary を再利用できるようにする。

```text
normalized_hash | chunk_hash | search_result_id
  -> summarization Agent Adapter
  -> summary_hash
```

## Profile

```text
agent_profile_hash:
  adapter_id
  agent_family
  version
  summary_kind
  max_input_tokens
  output_policy
```

外部サービスへ送信する場合は、対象 scope と送信許可を KCS API の task state に残す。
