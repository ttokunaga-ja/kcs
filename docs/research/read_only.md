はい、その想定でかなり良いです。
KCSの設計としては、**生成されたNormalized Markdownはユーザー編集対象ではなく、KCSが管理する読み取り専用の派生物**として扱うべきです。

結論は次です。

> **Normalized MarkdownはKCSが生成・更新する読み取り専用ビュー。ユーザーは原文ファイルを編集し、KCSが再Markdown化してMarkdownを更新する。**

---

# 1. Markdownは読み取り専用でよいか

はい。むしろ読み取り専用にすべきです。

理由は、Normalized Markdownは正本ではなく、原文から生成された派生物だからです。

```text
Raw File
  ↓
Markdown化
  ↓
Normalized Markdown
```

ここでユーザーがNormalized Markdownを直接編集すると、次の問題が起きます。

```text
原文とMarkdownの対応が壊れる
Evidence Pointerが壊れる
次回Markdown化で編集内容が消える
差分管理が複雑になる
どちらが正本か分からなくなる
```

したがって、KCSでは正本を明確に分けるべきです。

```text
正本: 原文ファイル
派生物: Normalized Markdown
検索用: Chunk / Embedding / Index
```

---

# 2. Markdown更新はKCSのみが行う

Normalized Markdownを更新できるのはKCSだけにします。

許可される更新：

```text
kcs index
kcs normalize
kcs repair
kcs resume
kcs reindex
```

許可しない更新：

```text
ユーザーが .kcs/objects/normalized/... を直接編集
外部エディタでMarkdownを書き換える
AI Agentが直接Markdownを編集
```

必要なら、KCSはMarkdownファイルにヘッダーを入れます。

```markdown
<!--
KCS GENERATED FILE
Do not edit manually.
Source: docs/report.pdf
Raw-Hash: sha256:...
Tool-Profile-Hash: sha256:...
Generated-At: 2026-04-25T12:00:00Z
-->
```

これで人間にも「編集対象ではない」と分かります。

---

# 3. もしユーザーがMarkdownを編集したい場合

この場合は、2通りに分けるべきです。

## A. 原文がMarkdownファイルの場合

例えば `note.md` が原文なら、ユーザーは原文の `note.md` を編集します。

```text
note.md
  ↓
KCSがNormalized Markdownとして取り込む
```

この場合、原文自体がMarkdownなので問題ありません。

## B. PDFや画像から生成されたMarkdownの場合

このMarkdownを直接編集してはいけません。
編集したい場合は、**annotation / note** として別に保存するのが良いです。

例：

```text
原文: report.pdf
KCS生成: report.pdf.md
ユーザー追記: report.pdf.kcs-note.md
```

またはKCS内部に annotation object を作る。

```text
objects/annotations/
```

こうすると、原文由来のMarkdownとユーザーの追記が混ざりません。

---

# 4. ファイルシステムでのプレビュー方針

これもあなたの想定でよいです。

> **最初にMarkdownプレビューを表示し、原文を開きたい場合だけ原文へアクセスする。**

このUXが自然です。

---

## 基本表示

検索結果を開くと、まずNormalized Markdownを表示します。

```bash
kcs open result_1
```

表示：

```text
Normalized Markdown preview
```

その中に原文へのリンクを出す。

```markdown
Source: docs/report.pdf
Open original: kcs://open/raw/sha256...
```

CLIなら：

```bash
kcs open result_1 --raw
```

GUIなら「原文を開く」ボタン。

---

# 5. なぜMarkdownを先に出すべきか

理由は明確です。

## 1. 表示が速い

PDFやOfficeファイルを毎回開くより、Markdown表示の方が軽いです。

## 2. AI Agentが扱いやすい

AgentはMarkdownの方が読みやすいです。

## 3. 横断的に同じUIで見られる

PDF、画像、docx、pptx、xlsxを全部Markdownで見られます。

## 4. 検索ヒット箇所を示しやすい

チャンク・見出し・表・コードをハイライトできます。

---

# 6. 原文アクセスの位置付け

原文は「確認・詳細閲覧・復元」のために使います。

```text
通常閲覧: Markdown
根拠確認: 原文
完全表示: 原文
復元: 原文 object
```

つまり、KCSではこうです。

```text
Markdown = default view
Raw file = evidence / source of truth
```

---

# 7. Image Objectの場合

画像も同じです。

Markdown内には画像参照を表示します。

```markdown
![図3: KCS構成](kcs-object://image/sha256-abc...)
```

プレビューでは画像を展開表示します。

画像を原文文書内で確認したい場合：

```text
Open source PDF page
```

画像単体を開きたい場合：

```text
Open extracted image
```

この2つを分けると良いです。

---

# 8. `.kcs` 内のMarkdownファイルを直接見せるか

ファイルシステム上では `.kcs/objects/normalized/` にありますが、ユーザーに直接触らせるより、KCSビューア経由で見せるのが良いです。

理由：

```text
hash名で保存される可能性がある
KCS内部リンクがある
原文ポインタ解決が必要
画像展開が必要
```

したがって：

```bash
kcs view <object>
kcs open <result>
```

で見るのが基本です。

GUIなら、Finder/Explorer風UIでMarkdownプレビューを出します。

---

# 9. Markdownの保存形式

内部保存はhashベースがよいです。Markdown 自体の content hash は取らないので、ファイル名は **原文の `raw_hash` と `tool_profile_hash` の組** で構成します。

```text
.kcs/objects/normalized/ab/cd/<raw_hash>.<tool_profile_hash>.md
```

ユーザーに見せるときは、元パスベースの仮想パスで表示します。

```text
docs/report.pdf.md
```

つまり：

```text
内部: content-addressed
表示: original-path-based virtual view
```

---

# 10. 読み取り専用をどう保証するか

## 1. OS上の権限

可能なら `.kcs/objects/normalized` を読み取り専用にする。

ただしクロスプラットフォームで面倒なので、必須ではない。

## 2. ハッシュ検証は行わない

KCS は Markdown 側の content hash (normalized_hash) を計算・保存しないため、Markdown が直接編集されたかをハッシュで検証することはしません。Markdownize Adapter は LLM ベースで非決定的なため、生成のたびに content hash が変わりえます。content hash 一致を破損検出条件にすると、正常な再生成までもが「破損」と誤検出されます。

直接編集を防ぐ・検出する手段は次のレイヤーに委ねます:

```text
1. ファイルの存在チェック (missing_output)
2. (raw_hash, tool_profile_hash) の組と normalization_run の状態
3. 必要なら OS 権限・ACL での read-only 化 (オプション)
4. ユーザーへの規約: .kcs/objects/normalized/ は手で編集しない
```

仮にユーザーが直接編集した場合でも、KCS は次回 `kcs index` 等で `(raw_hash, tool_profile_hash)` が一致する `done` 記録を見つけ「up-to-date」と判定します。これは設計上意図された挙動 (= Markdown 内容そのものは正本ではなく、原文 + tool_profile が正本) です。

## 3. statusで検出

```bash
kcs status
```

出力：

```text
Corrupted normalized objects:
  sha256:abc... expected sha256:def...
Run:
  kcs repair
```

これで十分強いです。

---

# 11. Agentによる更新はどうするか

Agentにも直接Normalized Markdownを書き換えさせない方が良いです。

Agentができること：

```text
annotationを追加
tagを付ける
nodeを作る
relationを作る
分類候補を出す
原文ファイルを編集する提案を出す
原文ファイルの「移動」を提案として出す (kcs move --propose)
```

Agentがしてはいけないこと：

```text
normalized markdownを直接編集する
raw objectを直接編集する
原文ファイルを承認なしに移動・削除する
```

## 書き込み主体マトリクス

各レイヤーの書き込み権限を以下に固定する。

```text
レイヤー                       | User | KCS  | Agent (提案) | Agent (自動適用)
------------------------------ | ---- | ---- | ----------- | ---------------
原本 (raw)                     | yes  | no*  | propose     | no
原本の移動 (file system mv)     | yes  | yes* | propose     | user 承認後のみ
normalized markdown            | no   | yes  | no          | no
chunks / embeddings            | no   | yes  | no          | no
annotations / tags / notes     | yes  | no   | yes         | yes
nodes / edges (knowledge graph)| yes  | no   | yes         | yes
commits / refs (履歴)           | no   | yes  | no          | yes (auto commit)
extraction issues              | yes  | yes  | yes         | yes
```

注:
- `*` 「原本の移動」は [auto_organize.md](auto_organize.md) の `kcs move --accept` 経由でのみ KCS が原本ファイルを mv する。これは「KCS による原本の物理位置変更」であり、原本の **内容** は不変である点で書き込みではない (移動のみ)。
- Agent が `kcs move --accept` を直接呼ぶことは禁止。Agent は `kcs move --propose` で提案キューに積み、ユーザーが承認した場合のみ適用される。
- `auto-mode` を ON にした場合に限り、Agent の提案を自動適用できるが、その場合も commit_type=auto で履歴に残し、いつでも revert 可能とする。

OCRやlayout detectionの誤りも、Normalized Markdownの手編集では直さない。MVPでは最低限、誤抽出箇所を extraction issue として記録し、再Markdown化または原本更新の候補として扱う。未反映の extraction issue は通常検索・RAGの根拠本文には混ぜず、修復・レビュー用の補助情報として扱う。

---

# 12. 要件文

設計書にはこう書くと良いです。

> KCSにおけるNormalized Markdownは、原文ファイルから生成された読み取り専用の派生ビューである。ユーザーおよびAI AgentはNormalized Markdownを直接編集せず、原文ファイルの変更またはKCSのMarkdown化処理によってのみ更新される。検索結果やファイルプレビューではNormalized Markdownを既定表示とし、原文ファイルは根拠確認・完全閲覧・復元が必要な場合にのみ明示的に開く。

---

# 最終結論

はい、あなたの想定でよいです。

```text
Normalized Markdown:
  読み取り専用
  KCSのみ更新可能
  検索・閲覧・Agent文脈の基本ビュー

Raw File:
  正本
  必要時のみ開く
  Evidence / restore対象
```

この設計にすると、KCSの責務がかなり明確になります。
