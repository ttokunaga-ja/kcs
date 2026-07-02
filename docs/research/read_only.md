# Read-only Markdown Research Notes

> Status: integrated
> Canonical refs: [../03-data-model.md](../03-data-model.md), [../05-runtime.md](../05-runtime.md), [../08-evidence-pointer-spec.md](../08-evidence-pointer-spec.md)

---

# 結論

Normalized Markdown は読み取り専用 artifact。ユーザーや Agent が直接編集する対象ではない。

```text
原本 Markdown:
  そのファイル自体が正本。ユーザーが編集してよい。

PDF / 画像 / Office 由来の Markdown:
  KCS が生成した証拠表現。編集しない。
```

# なぜ read-only か

```text
- 原本との対応が壊れる
- Evidence Pointer の根拠が不安定になる
- LLM 出力の修正と原本の修正が混ざる
- 再 Markdownize 時に手編集が消える
```

誤抽出の指摘や補足は Markdown 本文ではなく、annotation / extraction issue / note として別 object にする。

# 表示方針

検索結果や preview はまず Normalized Markdown を表示する。理由:

```text
- 表示が速い
- AI Agent が扱いやすい
- ファイル種別をまたいで UI を統一できる
- hit span を示しやすい
```

原本は Evidence Pointer から開けるようにする。

# 保存形式

内部保存は hash ベース object store。

```text
.kcs/objects/normalized/<prefix>/<raw_hash>.<tool_profile_hash>.md
```

path ベースの見え方は virtual view。

# 破損検出

Markdown content hash は持たないため、本文 hash 不一致による `corrupted` は採用しない。

```text
検出する:
- artifact が存在しない → missing_output
- status が failed
- tool_profile_hash mismatch
```

# 書き込み主体

```text
原本ファイル内容:
  ユーザーまたは外部アプリのみ。

Normalized Markdown:
  KCS pipeline のみ。

annotation / note / extraction issue:
  ユーザー / Agent が作成可能。

原本の移動:
  auto organize の accept 操作として KCS が mv してよい。内容は変更しない。
```

# 正本へ移した内容

```text
write boundary / object identity       → 03-data-model.md
view / restore / search runtime        → 05-runtime.md
Evidence Pointer semantics             → 08-evidence-pointer-spec.md
```
