はい、**Agentを使わなくても可能**です。むしろKCSの基本価値は、まず **ローカルOnlyでも成立する** ように設計すべきです。

整理すると、KCSには2段階あります。

```text
1. ローカル検索・分類基盤
2. Agentによる高度なナビゲーション
```

Agentは2段階目であり、1段階目だけでも十分に価値があります。

---

## ローカルOnlyで可能なこと

Markdown化によって、PDF・画像・Office文書などもすべてテキストとして扱えます。
そのため、ローカルだけで以下が可能です。

```text
全文検索
見出し検索
タグ候補生成
類似ファイル検索
重複候補検出
フォルダ分類候補
関連ファイル推薦
```

Embeddingをローカルで生成すれば、APIなしでも概念検索・類似検索ができます。

---

## 自動分類提案の基本設計

分類はAgentがなくても、かなり機械的にできます。

```text
新規ファイル
 ↓
Markdown化
 ↓
全文検索インデックス登録
 ↓
Embedding生成
 ↓
既存フォルダ・既存ファイルとの類似度計算
 ↓
分類候補を提示
```

例：

```text
downloaded: graph_rag_survey.pdf

Suggested:
1. ~/Documents/Research/RAG/
   reason: 類似ファイル 12件、"GraphRAG", "retrieval", "knowledge graph" が頻出

2. ~/Documents/University/AI/
   reason: 講義資料と類似
```

これはAgentではなく、Embedding類似度・キーワード一致・既存フォルダの代表ベクトルで十分できます。

---

## フォルダ分類の方法

各フォルダに「フォルダプロファイル」を持たせます。

```text
Folder Profile =
  配下ファイルのEmbedding平均
  頻出キーワード
  見出し一覧
  ファイル種別分布
  最近使われた検索語
```

新規ファイルのEmbeddingと比較して、近いフォルダを推薦します。

```text
score(folder, file)
=
semantic_similarity
+ keyword_overlap
+ file_type_match
+ recency
```

---

## Agentなしでの分類提案例

```bash
kcs inbox
```

```text
New files in Downloads:

1. 2026_invoice_april.pdf
   Suggested folder:
   - Documents/Receipts/2026/   score 0.91
   Suggested tags:
   - invoice
   - finance
   - 2026

2. graphrag_survey.pdf
   Suggested folder:
   - Documents/Research/RAG/    score 0.87
   Suggested tags:
   - RAG
   - knowledge graph
   - retrieval
```

ユーザーは確認して移動します。

```bash
kcs move --accept 1
```

またはGUIで「移動」を押す。

---

## Agentを使う場合との差

| 項目       | ローカルOnly | Agentあり |
| -------- | -------- | ------- |
| 全文検索     | 可能       | 可能      |
| 類似検索     | 可能       | 可能      |
| 自動分類候補   | 可能       | 可能      |
| 理由説明     | 簡易       | 高度      |
| 複雑な判断    | 弱い       | 強い      |
| 複数ステップ探索 | 限定的      | 強い      |
| 移動・整理提案  | 可能       | より柔軟    |

Agentなしでも十分に実用的です。
Agentは「なぜここに分類するのか」「関連資料をまとめて」「このフォルダ構造を再編して」などの高度操作に効きます。

---

## KCSの価値を再定義すると強い

KCSはAgent専用システムではなく、こう定義する方がよいです。

> **KCSは、Prepare・Markdownize（OCRを含む）・マルチモーダルEmbedding・全文検索によって、ローカルファイルを検索可能かつ分類可能な知識空間に変換する。Agentはその知識空間を利用する高度な利用者の一形態である。**

つまり、

```text
KCSの基盤価値 = ローカル知識インデックス
Agent価値 = その上の高度ナビゲーション
```

です。

---

## 最終方針

KCSは以下の3層にすると綺麗です。

```text
Layer 1: Local Index
  Markdown化
  全文検索
  Embedding
  類似検索

Layer 2: Local Intelligence
  自動分類候補
  タグ候補
  重複候補
  関連ファイル推薦

Layer 3: Agent Navigation
  複雑な探索
  文脈理解
  自動整理計画
  回答生成
```

この設計なら、Agentがなくてもプロダクトとして成立します。
そしてAgentを使うとさらに強くなります。
