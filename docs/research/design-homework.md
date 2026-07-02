# Design Homework

> Status: reviewed
> Canonical refs: [../09-mvp-scope.md](../09-mvp-scope.md), [../08-evidence-pointer-spec.md](../08-evidence-pointer-spec.md), [../07-adapter-spec.md](../07-adapter-spec.md)

---

# 残す論点

実装前にぶつかる論点だけを残す。詳細仕様は正本へ移動済み。

| # | 論点 | 現状 | 期限 |
| --- | --- | --- | --- |
| 1 | Markdown 非決定性 = first-instance wins | 採用案あり | Step 1 前 |
| 2 | remarkdownize / evidence retarget | draft | Step 3 前 |
| 3 | Dead Evidence Pointer | draft。08 に採用案あり | Step 3 前 |
| 4 | Incremental Markdownize prompt 規約 | schema は決定、prompt level は詰める | Step 1 前 |

# 1. Markdown 非決定性

採用案:

```text
First-instance wins。
同じ (raw_hash, tool_profile_hash) の done artifact があれば再実行しない。
reindex --force のみ例外。parent_run_id で履歴を残す。
```

# 2. evidence retarget

Evidence Pointer は過去の根拠を指すため、最新 Markdown へ自動追従しない。最新 tool profile の chunk へ移す場合は、新しい pointer を返す retarget 操作にする。

未決:

```text
- 自動 retarget する場面を作るか
- 対応不能時の error code
- Agent API の bulk retarget / verify
```

# 3. Dead Evidence Pointer

purge 後の pointer 解決:

```text
tombstone がある:
  status=purged を返す。

完全削除:
  not_found を返す。
```

未決:

```text
- tombstone default か、完全削除 default か
- tombstone 自体の purge を許すか
```

# 4. Incremental Markdownize

決定済み:

```text
- KCS が changed_unit_keys を渡す
- Adapter は unchanged unit を出力しない
- 変更 unit は完全に書き直す
- fallback_to_full を許す
```

未決:

```text
- spec_version bump 規約
- Adapter の fallback 閾値
- streaming response の有無
```
