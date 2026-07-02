# Hash / Identity Research Notes

> Status: integrated
> Canonical refs: [../03-data-model.md](../03-data-model.md), [../04-pipeline.md](../04-pipeline.md), [../07-adapter-spec.md](../07-adapter-spec.md)

---

# 結論

KCS は同一性と類似性を分ける。

```text
raw_hash:
  原文バイト列の同一性。1 byte 違えば別 object。

tool_profile_hash:
  Markdownize / embedding 等の capability profile の同一性。

semantic_fingerprint:
  意味・視覚・構造の近さ。dedup 候補、page reuse、分類提案に使う。
```

hash は identity。fingerprint は similarity。混ぜない。

# Markdown の identity

Markdown content hash (`normalized_hash`) は採用しない。LLM ベースの Markdownize は非決定的であり、同じ raw + 同じ profile でも出力が揺れるため。

Normalized Markdown の identity は次だけで決まる。

```text
(raw_hash, tool_profile_hash)
```

# up-to-date 判定

あるファイルが Markdownize 済みと判定される条件:

```text
1. 現在の raw_hash と一致する normalization_run がある
2. tool_profile_hash が現在の設定と一致する
3. status = done
4. normalized object が存在する
```

Markdown 本文の hash は判定に使わない。

# 状態分類

```text
new              初回発見
up_to_date       raw_hash + tool_profile_hash の done artifact がある
modified         path は同じだが raw_hash が変わった
tool_changed     raw_hash は同じだが tool_profile_hash が変わった
missing_output   done 記録はあるが artifact がない
failed           前回失敗
pending          実行待ち
```

# tool_profile_hash

hash 対象は artifact の内容に影響する capability 情報に限定する。

```text
含める:
- adapter kind / model family
- capability set
- prompt_template_hash
- output schema version
- options that affect output
- spec_version

含めない:
- cmd / args / URL
- API key / credential
- OS / hardware
- adapter binary path
```

実行可能情報を `.kcs` に入れないことで、共有 `.kcs` が外部コマンド実行情報を運ばないようにする。

# first-instance wins

同じ `(raw_hash, tool_profile_hash)` で done artifact が存在する場合、再実行しない。明示的な `reindex --force` だけが例外で、その場合は parent_run_id で履歴を残す。

# 正本へ移した内容

```text
identity / schema / up-to-date      → 03-data-model.md
pipeline task 判定                  → 04-pipeline.md
tool_profile_hash 規約              → 07-adapter-spec.md
```
