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
  "canonical_text_hash": "sha256:...",
  "markdown_hash": "sha256:...",
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

それでも、同じページをMarkdown化しても出力が少し変わる可能性があります。

そのため、差分判定には `markdown_hash` だけでなく、**canonical hash** を使います。

---

## canonicalization

Markdownを比較する前に正規化します。

例：

```text
空白正規化
連続改行正規化
Markdown table整形
箇条書き記号統一
全角半角の一部正規化
HTML entity正規化
コードブロック保持
LaTeX保持
```

その後にhash。

```text
canonical_text_hash = hash(canonicalize(markdown))
```

これにより、軽微な表記ゆれによる全差分を減らせます。

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
  markdown_hash TEXT NOT NULL,
  canonical_hash TEXT NOT NULL,
  normalized_object_hash TEXT NOT NULL,
  created_at TEXT NOT NULL
);
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
