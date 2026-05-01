はい、その設計でよいです。むしろ **KCSの検索体験としては最も自然**です。

結論は次です。

> **デフォルトはHybrid検索。ただしEmbeddingが使えない場合は、ユーザーにエラーを出して止めるのではなく、自動的に全文検索へフォールバックする。**

つまり、KCSの基本思想はこれです。

```text
Best effort Hybrid Search
=
全文検索は必ず動く
Embeddingは使えるときだけ追加で使う
```

---

# 推奨する検索モード

## デフォルト

```bash
kcs search "認証仕様"
```

内部動作：

```text
1. 全文検索を実行
2. Embeddingが利用可能か確認
3. 利用可能ならベクトル検索も実行
4. RRFなどで統合
5. 利用不可なら全文検索結果のみ返す
```

---

# Embeddingを使わない条件

以下の場合は自動で全文検索のみ。

```text
configでvector disabled
Embedding endpoint未設定
API key未設定
API接続失敗
API quota超過
Embedding index未構築
Embedding profile不一致
対象.kcsにvector indexが存在しない
```

---

# ただしログ・警告は残すべき

ユーザー体験としては止めない。
ただし、後から原因が分かるようにします。

例：

```text
Hybrid search requested, but vector search is unavailable.
Fallback to text search.

Reason:
  embedding endpoint is not configured
```

通常表示では短く：

```text
mode: text fallback
```

詳細表示：

```bash
kcs search "認証仕様" --verbose
```

で原因を出す。

---

# 設定案

```toml
[search]
default_mode = "auto"
fallback = "text"
show_fallback_warning = true

[text_search]
enabled = true

[vector_search]
enabled = true
optional = true
fail_behavior = "fallback"
```

`fail_behavior` は重要です。

```toml
fail_behavior = "fallback"
```

他にも将来的には：

```toml
fail_behavior = "error"
fail_behavior = "warn"
```

を許可してもよいです。

---

# CLIモード

```bash
kcs search "..."              # auto: hybrid if possible, otherwise text
kcs search "..." --text       # text only
kcs search "..." --vector     # vector only。失敗時はエラー
kcs search "..." --hybrid     # hybrid強制。vector失敗時は設定に従う
kcs search "..." --no-vector  # 明示的にvector無効
```

おすすめ挙動：

| コマンド                  | vector不可時                |
| --------------------- | ------------------------ |
| `kcs search`          | textへ自動fallback          |
| `kcs search --hybrid` | warning後fallback、または設定次第 |
| `kcs search --vector` | error                    |
| `kcs search --text`   | 常にtext                   |

---

# AI Agent向けレスポンス

Agentには、実際にどの検索が使われたかを返すべきです。

```json
{
  "query": "認証仕様",
  "requested_mode": "auto",
  "resolved_mode": "text",
  "fallback": true,
  "fallback_reason": "embedding_endpoint_not_configured",
  "results": [...]
}
```

これによりAgentは

```text
今回は全文検索だけだった
必要なら再試行する
別クエリにする
```

と判断できます。

---

# 重要な設計判断

Embeddingが使えないことを、KCSの失敗にしない方がよいです。

なぜなら、KCSの最低保証は

```text
Normalized Markdownを全文検索できること
```

だからです。

Embeddingは

```text
意味的ホップを強化する追加経路
```

です。

---

# 最終定義

KCSの検索仕様はこう定義するのが良いです。

> KCSの標準検索モードは `auto` とし、全文検索とEmbedding検索が利用可能な場合はHybrid検索を実行する。Embedding検索が設定・認証・エンドポイント・インデックス・実行時エラーのいずれかにより利用できない場合、KCSは検索を失敗させず、自動的に全文検索へフォールバックする。検索結果には、実際に使用された検索モードとフォールバック理由をメタデータとして付与する。

この仕様が一番実用的です。
