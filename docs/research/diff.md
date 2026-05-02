はい。ここはKCSのかなり重要な設計課題です。
結論から言うと、**PDF全体を毎回Markdown化して、単純にMarkdown全文diffを取る設計は避けるべき**です。

理由はあなたの指摘通りで、Markdownize Adapterは同じPDFでも表現ゆれを起こすため、

```text
原文は一部しか変わっていない
↓
Markdown出力は全体的に微妙に変わる
↓
全行差分になる
```

という問題が起きます。

したがって、KCSでは **「原文差分」ではなく「安定した構造単位ごとの差分」** を取る必要があります。

---

# 結論

KCSでは、変更検出を次の4段階に分けるべきです。

```text
1. Raw file hash
2. Prepared object hash
3. Page / block / section 単位 hash
4. Normalized Markdown section hash
```

つまり、ファイル全体ではなく、

```text
ページ単位
見出し単位
ブロック単位
チャンク単位
```

で差分を管理します。

---

# 1. 問題の本質

PDFを丸ごとMarkdown化すると、次のような変動が起きます。

```text
見出しの表記が変わる
改行位置が変わる
表のMarkdown表現が変わる
箇条書きが変わる
画像説明が変わる
空白が変わる
```

その結果、実際には1ページしか変わっていなくても、

```text
entire document changed
```

に見えてしまいます。

これは、KCSの差分管理・Embedding再生成・履歴保存にとって非常に悪いです。

---

# 2. 解決方針

KCSでは、Markdown化の出力を **1つの巨大Markdownファイル** として扱うのではなく、内部的には **構造化Markdown object** として扱います。

外から見ると：

```text
report.pdf.md
```

内部では：

```text
Document
 ├ page 1
 │   ├ block 1
 │   ├ block 2
 │   └ block 3
 ├ page 2
 │   ├ block 1
 │   └ block 2
 └ page 3
```

のように保存します。

---

# 3. 推奨する内部モデル

## Raw Object

原文ファイル。

```text
objects/raw/<raw_hash>
```

---

## Prepared Object

Markdown化ツールに渡す前の変換済み入力。

例：

```text
BMP → PNG
DOC → PDF
PDF → page images bundle
```

```text
objects/prepared/<prepared_hash>
```

---

## Markdown Unit Object

Markdown化結果を単位ごとに保存。

```text
objects/normalized_units/
  page_001.json
  page_002.json
  section_xxx.json
```

各unitはこうです。

```json
{
  "unit_id": "unit_...",
  "raw_hash": "sha256:...",
  "prepared_hash": "sha256:...",
  "unit_type": "page",
  "unit_key": "page:12",
  "markdown": "## 3.2 認証仕様\n...",
  "tool_profile_hash": "sha256:..."
}
```

---

# 4. まずページ単位で分割する

PDFの場合、最初の現実解は **ページ単位Markdown化** です。

```text
report.pdf
↓
page_001
page_002
page_003
...
```

各ページを個別にMarkdown化します。

これにより、1ページだけ変わった場合は、原則そのページだけ再処理すればよくなります。

---

## 処理例

```text
旧PDF:
 page 1 hash A
 page 2 hash B
 page 3 hash C

新PDF:
 page 1 hash A
 page 2 hash B'
 page 3 hash C
```

この場合、

```text
page 2 のみ Markdown化
page 1, 3 は既存Markdownを再利用
```

できます。

---

# 5. ページhashをどう作るか

PDF全体hashだけではなく、ページ単位hashを持ちます。

```json
{
  "raw_hash": "sha256:pdf_all",
  "units": [
    {
      "unit_key": "page:1",
      "prepared_hash": "sha256:page1"
    },
    {
      "unit_key": "page:2",
      "prepared_hash": "sha256:page2"
    }
  ]
}
```

PDFをページ画像化する場合は、ページごとの画像hashを取れます。

```text
PDF page 1 → image/page_001.png → hash
PDF page 2 → image/page_002.png → hash
```

この方式なら、PDF内部構造の微妙な差ではなく、実際に見えるページ単位で差分を取れます。

---

# 6. Markdownize Adapterには「単位ごと」に入力する

重要なのは、Markdown化をファイル全体でなく **unit単位** にすることです。

```text
NG:
  entire PDF → one huge Markdown

OK:
  page / slide / sheet / image → unit Markdown
```

ファイル種別ごとのunit例：

| ファイル種別   | Markdown化単位                     |
| -------- | ------------------------------- |
| PDF      | page                            |
| PPTX     | slide                           |
| DOCX     | heading section / page相当        |
| XLSX     | sheet                           |
| 画像       | image                           |
| Markdown | heading section                 |
| code     | file / symbol / heading comment |

これにより、差分更新が可能になります。

## 6.1 Incremental Markdownize (差分前提の再生成) — 要件

ファイルが更新された場合、KCS は **新 raw だけを Adapter に投げ直すのではなく、旧 raw + 旧 Markdown + 新 raw + 変更ヒントをセットで Adapter に渡し、軽微な変更なら部分更新を返させる** 方式を採用します。これは MVP〜v1 のプロダクト要件として確定しています。

### 動機

- LLM API コストの抑制 (移行期、batch.md cost guardrail と整合)。
- 全文再生成による意図せぬ表記ゆれ・見出し変動を抑え、unit_id と chunk の安定性を高める。
- §13 の page fingerprint と整合し、変わっていない unit の再 LLM 呼び出しを完全に排除できる。

### 発動条件 (すべて満たす場合のみ incremental)

```text
1. 同一 file_id に対する既存 done normalization_run がある
2. raw_hash のみ変化 (tool_profile_hash は不変)
3. Adapter が capabilities = ["incremental_update"] を宣言
4. page fingerprint 変化率 < incremental_threshold (デフォルト 0.30)
5. 直前 N 回 (デフォルト 5) 連続で incremental だった場合は full を強制
   (style drift / 累積誤差を防ぐため)
```

いずれかが満たされなければ自動で **full re-Markdownize** にフォールバック。

### Adapter 入力契約

incremental モードで Adapter に渡す入力:

```json
{
  "mode": "incremental",
  "new_raw": { "path": "...", "raw_hash": "sha256:..." },
  "previous": {
    "raw": { "path": "...", "raw_hash": "sha256:..." },
    "normalized_units": [ /* 旧 unit objects (markdown 含む) */ ],
    "tool_profile_hash": "sha256:..."
  },
  "hints": {
    "changed_unit_keys": ["page:12", "page:13"],
    "added_unit_keys": ["page:57"],
    "removed_unit_keys": [],
    "page_fingerprints": { "page:12": {...}, ... }
  },
  "tool_profile_hash": "sha256:..."
}
```

Adapter からの出力:

```json
{
  "mode_used": "incremental",
  "updated_units": [ /* 変更が必要だった unit のみ */ ],
  "unchanged_unit_keys": ["page:01", "page:02", ...],
  "added_units": [...],
  "removed_unit_keys": [...],
  "fallback_to_full": false,
  "reason": null
}
```

Adapter 側が「軽微とは言えない」と判断した場合は `fallback_to_full: true` を返してよい。KCS 側は full を再要求する。

### identity への影響

- 出力 Markdown が incremental/full で異なっても、artifact identity は `(raw_hash, tool_profile_hash)` のまま不変。
- `tool_profile_hash` の計算入力 (hash.md §9.1) に **incremental flag は含めない**。同じ profile で full と incremental の結果が同等とみなす契約。
- これにより「過去に full で生成、次回 incremental で更新、その次は再び full」のような mode 混在でも identity 矛盾は起きない。

### 監査記録

`normalization_runs` テーブル / object に次のフィールドを追加する:

```text
mode                "full" | "incremental"
parent_run_id       直前の done run の id (incremental 時のみ)
changed_unit_keys   incremental で書き換えた unit の集合 (JSON array)
fallback_reason     full に倒した理由 (capability_missing | threshold_exceeded |
                    forced_refresh | adapter_requested | first_run | null)
```

これにより「この Markdown はどの incremental chain から来たか」を遡れる。連続 incremental 回数の counter もここから算出。

### Adapter capability 宣言

`tool-lock.json` の markdown adapter に `capabilities` を持たせる ([kcs.md §8](kcs.md))。

```json
"markdown": {
  "tool_id": "markdown_default",
  "kind": "local_adapter",
  "profile_hash": "sha256:...",
  "capabilities": ["ocr", "layout_detection", "incremental_update"]
}
```

`incremental_update` が含まれない Adapter は常に full モードで呼ばれる。

### 設定

```toml
# .kcs/config.toml
[markdownize.incremental]
enabled = true
threshold = 0.30           # 変化率の上限。これを超えると full
max_consecutive = 5        # 連続 incremental の上限。超えると次回 full
include_neighbors = 1      # 変更 page の前後 N page も hint に含める
```

---

# 7. Markdown全文は生成物として組み立てる

ユーザーに見せる `.md` は、unitを結合して生成します。

```text
unit_001.md
unit_002.md
unit_003.md
↓
report.pdf.md
```

つまり、

```text
report.pdf.md は正本ではなく view
```

です。

正本はunit objectです。

これにより、ページ2だけ変わったときに、page2 unitだけ差し替えればよい。

---

# 8. Agent出力ゆれ対策

同じページをMarkdown化しても LLM ベースの Adapter は出力が少し変わる可能性があります。

KCS ではこの非決定性を **Markdown 側 content hash で吸収しようとしない** 方針です。Markdown の content hash (markdown_hash / canonical_text_hash 等) は計算・保存・比較しません。代わりに、差分判定は **raw 側で完結** させます。

---

## raw 側で差分を判定する

unit が「変わったか」は次で判定します。

```text
prepared_hash が変わった
  または
raw_hash が変わり、unit に対応する page_fingerprint (§13) が変わった
  または
tool_profile_hash が変わった
```

これらが変わらなければ、Markdown を再生成する必要はなく、既存の Markdown unit をそのまま再利用します (= LLM 再呼び出し不要)。Markdownize Adapter の出力ゆれは「同じ unit について複数の表現がありうる」状態を許容することで吸収し、表記ゆれ吸収のための canonicalization は **検索インデックス側** (FTS tokenization, normalization) に閉じます。

---

# 9. 差分は3種類に分ける

KCSでは差分を1種類にしない方がよいです。

## 1. Raw Diff

原文の差分。

```text
raw_hash changed
page_hash changed
```

---

## 2. Normalized Diff

Markdown化結果の差分。

```text
unit markdown changed
section changed
```

---

## 3. Knowledge Diff

知識ノード単位の差分。

```text
追加された知識
削除された知識
変更された知識
矛盾が発生した知識
```

---

# 10. KCSで重要なのはRaw Diffを起点にすること

Markdown差分を起点にするとAgent出力ゆれの影響を受けます。

したがって起点は、

```text
Raw / Prepared unit hash
```

です。

処理順：

```text
1. raw file changed?
2. prepared units changed?
3. changed unitsだけMarkdown化
4. changed normalized unitsだけchunk更新
5. changed chunksだけEmbedding更新
6. changed nodesだけ再評価
```

---

# 11. 実装フロー

ファイル更新時の推奨フローです。

```text
kcs index
  ↓
scan files
  ↓
raw_hash比較
  ↓
ファイル全体が未変更ならskip
  ↓
prepared units生成
  ↓
unit_hash比較
  ↓
変更unitだけMarkdown化
  ↓
unit Markdown保存
  ↓
document Markdown view再構築
  ↓
changed chunks抽出
  ↓
changed chunksだけEmbedding
  ↓
FTS / vector index更新
  ↓
snapshot作成
```

---

# 12. 具体例：PDF 100ページ中1ページ変更

旧：

```text
page 1〜100 indexed
```

新：

```text
page 57だけ変更
```

処理：

```text
page 57のprepared_hashだけ変化
↓
page 57のみMarkdown化
↓
page 57由来chunkのみ更新
↓
page 57由来Embeddingのみ更新
↓
検索index更新
```

結果：

```text
99ページ分のMarkdownは再利用
99ページ分のEmbeddingも再利用
```

---

# 13. 問題：ページ挿入でページ番号がずれる場合

ここが難所です。

PDFの途中にページが1枚追加されると、

```text
旧 page 10
新 page 11
```

のように番号がずれます。

単純なpage番号比較だと、後続ページ全部が変わったように見えます。

---

## 対策：ページ fingerprint

各ページに内容fingerprintを持たせます。

```text
page_fingerprint = perceptual hash + text hash + visual hash
```

簡易には：

```text
prepared page image hash
```

高度には：

```text
Markdownize前のページ画像 pHash
```

これで、ページ番号が変わっても同じページを対応づけます。

```text
旧 page 10 fingerprint X
新 page 11 fingerprint X
```

なら、移動しただけと判断できます。

---

# 14. PPTXの場合

スライド単位で同じです。

```text
slide fingerprint
```

スライド番号が変わっても、内容fingerprintで対応付けます。

---

# 15. DOCXの場合

DOCXはページ概念が不安定なので、見出し単位がよいです。

```text
heading path
+
paragraph block hash
```

ただし、KCS方針では非テキストはMarkdownize Adapterに渡すので、最初は

```text
DOCX → prepared PDF or page images
```

にして、ページ/見出し単位にしてもよいです。

---

# 16. 実装の現実解

最初のMVPでは、複雑なsemantic diffまでは不要です。

MVPではこれでよいです。

```text
PDF/PPTX: page/slide単位
Markdown/txt: heading単位
画像: file単位
Excel: sheet単位
```

そして：

```text
unit_hashが変わったunitだけ再Markdown化
```

これだけでかなり解決します。

---

# 17. `.kcs` に必要なデータ

## prepared_units テーブル

```sql
CREATE TABLE prepared_units (
  unit_id TEXT PRIMARY KEY,
  raw_hash TEXT NOT NULL,
  file_path TEXT NOT NULL,
  unit_type TEXT NOT NULL,
  unit_key TEXT NOT NULL,
  unit_order INTEGER,
  prepared_hash TEXT NOT NULL,
  fingerprint TEXT,
  created_at TEXT NOT NULL
);
```

---

## normalized_units テーブル

```sql
CREATE TABLE normalized_units (
  normalized_unit_id TEXT PRIMARY KEY,
  unit_id TEXT NOT NULL,
  prepared_hash TEXT NOT NULL,
  tool_profile_hash TEXT NOT NULL,
  normalized_object_path TEXT NOT NULL,
  created_at TEXT NOT NULL,
  UNIQUE (unit_id, prepared_hash, tool_profile_hash)
);

-- 注: Markdown 側 content hash (markdown_hash / canonical_hash) は持たない。
-- normalized_unit の identity は (unit_id, prepared_hash, tool_profile_hash) で
-- 一意に決まり、再生成判定もこの組のみで行う。
```

---

## unit_mapping テーブル

バージョン間の対応。

```sql
CREATE TABLE unit_mapping (
  old_unit_id TEXT,
  new_unit_id TEXT,
  relation TEXT, -- same, modified, moved, inserted, deleted
  confidence REAL
);
```

---

# 18. 「全行更新」問題への直接回答

PDF全体を1回のMarkdown化リクエストにすると、全行更新問題が起きます。

対策は：

```text
1. ファイル全体ではなくunit単位でMarkdown化する
2. unitごとにprepared_hashを持つ
3. 変更unitだけ再Markdown化する
4. Markdown比較前にcanonicalizeする
5. document-level Markdownはunit結合viewとして生成する
```

これが基本解です。

---

# 19. KCSの要件文

設計書にはこう書くと良いです。

> KCSでは、非テキストファイルを1つの巨大なMarkdownとして直接生成しない。PDFはページ、PPTXはスライド、XLSXはシート、Markdownは見出し単位といった安定したunitに分割し、unit単位でMarkdown化する。各unitにはprepared hashとfingerprintを付与し、ファイル更新時には変更されたunitのみを再Markdown化する。最終的なNormalized Markdownはunit Markdownを結合したviewとして生成し、差分判定の正本はunit object側に置く。

---

# 20. 最終方針

KCSの差分更新はこう定義するのが最適です。

```text
正本:
  raw object
  prepared unit object
  normalized unit object

表示:
  combined markdown view

差分:
  file diff ではなく unit diff

更新:
  changed units only
```

これにより、PDF全体を再Markdown化して全行更新になる問題を避けられます。
