# Diff / Incremental Markdownize Research Notes

> Status: integrated
> Canonical refs: [../04-pipeline.md](../04-pipeline.md), [../07-adapter-spec.md](../07-adapter-spec.md)

---

# 問題

PDF / PPTX / DOCX などを丸ごと Markdownize すると、1 ページだけ変更されても全 Markdown が揺れる。これは差分、chunk、Evidence Pointer、embedding 再生成に悪い。

# 方針

非テキスト資料は安定した unit に分割し、unit 単位で Markdownize する。

| 種別 | unit |
| --- | --- |
| PDF | page |
| PPTX | slide |
| DOCX | heading section / page 相当 |
| XLSX | sheet |
| 画像 | image |
| Markdown | heading section |
| code | file / symbol |

Document-level Markdown は unit Markdown を結合した view。差分判定の正本は unit object 側。

# object model

```text
Raw Object:
  原本ファイルの CAS object。

Prepared Unit:
  page / slide / sheet 等。raw から決定論的に抽出する。

Markdown Unit:
  prepared unit + tool_profile_hash から生成する read-only artifact。
```

# page fingerprint

ページ挿入で page number がずれるため、単純な page index だけでは再利用できない。

```text
page_fingerprint =
  text hash
  + perceptual / visual hash
  + layout hints
```

fingerprint は identity ではなく reuse candidate 判定に使う。

# incremental Markdownize

発動条件:

```text
- raw_hash は変化した
- previous raw / normalized units がある
- changed_unit_keys を推定できる
- Adapter が incremental_update capability を持つ
- 変更率が閾値以下
```

Adapter 入力:

```text
mode = incremental
new_raw
previous.raw
previous.normalized_units
hints.changed_unit_keys
tool_profile_hash
spec_version
```

Adapter 出力:

```text
mode_used = incremental | full
updated_units
unchanged_unit_keys
added_units
removed_unit_keys
fallback_to_full
reason
```

`fallback_to_full=true` の場合は full Markdownize task を作る。

# 差分の種類

```text
Raw Diff:
  raw / prepared unit の変化。再処理判定の起点。

Normalized Diff:
  Markdown artifact の変化。表示・レビュー用。

Knowledge Diff:
  node / edge / summary の変化。Phase 5+。
```

KCS で重要なのは Raw Diff を起点にすること。LLM 出力の揺れを差分判定の起点にしない。

# 必要な台帳

```text
prepared_units:
  raw_hash, unit_key, unit_hash, fingerprint, order

normalized_units:
  raw_hash, unit_key, tool_profile_hash, normalized_ref, status

unit_mapping:
  old_unit_key, new_unit_key, confidence, reason
```

# 正本へ移した内容

```text
pipeline / schema              → 04-pipeline.md
Adapter 入出力契約             → 07-adapter-spec.md
incremental の運用規約         → 10-operations.md
```
