# Search Runtime

> 正本: `docs/research/git_kcs.md` の検索スコープ方針、および `docs/research/db.md` の検索バックエンド方針。

## デフォルト検索

KCS のデフォルト検索は、KCS が認識している **すべての indexed scope** を対象にする。

初回の indexed scope は、ユーザーが `.kcsignore` や設定で明示的に除外していないすべての対象範囲とする。

```bash
kcs search "認証仕様"
```

意味:

```text
all indexed scopes / all tracked folders and files
```

これは、ローカルファイル空間全体に対して Google 的な横断検索体験を提供するための既定動作である。

## スコープ制限

検索範囲を絞る場合は明示的に指定する。

```bash
kcs search "認証仕様" --scope .
kcs search "認証仕様" --scope . --descendants
kcs search "認証仕様" --scope ./Research
kcs search "認証仕様" --scope ./Research --descendants
kcs search "認証仕様" --all-scopes
```

| 指定 | 対象 |
| --- | --- |
| なし | 全 indexed scope |
| `--all-scopes` | 全 indexed scope |
| `--scope .` | 現在フォルダのみ |
| `--scope . --descendants` | 現在フォルダと配下 |
| `--scope <path>` | 指定フォルダのみ |
| `--scope <path> --descendants` | 指定フォルダと配下 |

## 検索モード

標準モードは `auto` とする。

```text
auto = hybrid if possible, otherwise text fallback
```

Embedding / vector index が利用できない場合でも検索は失敗させず、全文検索へ fallback する。

## レスポンスメタデータ

人間向け表示でも JSON でも、実際に検索した scope と検索モードを返す。

```json
{
  "query": "認証仕様",
  "requested_mode": "auto",
  "resolved_mode": "text",
  "fallback": true,
  "fallback_reason": "vector_index_missing",
  "scope": {
    "mode": "all_scopes",
    "included": ["A/.kcs", "A/B/.kcs", "Work/.kcs"],
    "excluded": []
  }
}
```

Agent API でも同じ情報を必ず返す。
