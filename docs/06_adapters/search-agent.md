# Search Delegation Agent Adapter

> 正本: `adapter-overview.md` と `05_interface/agent-api.md`。

## 役割

検索代行 Agent Adapter は、KCS API を使って検索、再ランキング、回答用コンテキスト収集を行う Adapter である。KCS core の object store や検索 index を直接置き換えるものではない。

```text
query + scope + time_range
  -> KCS search API
  -> ranked result / context
  -> search delegation Agent Adapter
  -> ranked_context
```

## 返すべきメタデータ

```text
searched_scopes
excluded_scopes
unavailable_scopes
search_mode
fallback_reason
source_chunk_hashes
agent_profile_hash
```

Agent が外部サービスへ問い合わせる場合も、検索対象 scope と送信対象 artifact を KCS core の task state に残す。
