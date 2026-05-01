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

### スコア合成の規約

各成分はスケールが異なるので、加算前に [0, 1] へ正規化してから重み付き和をとる。

```text
semantic_similarity: cosine(file_embedding, folder_embedding) を [-1,1] → [0,1] に線形変換
keyword_overlap:    Jaccard(file_keywords, folder_keywords). [0,1]
file_type_match:    folder の主要 MIME 分布における該当 MIME の出現確率. [0,1]
recency:            exp(-days_since_last_match / τ),  τ=30. [0,1]

score = 0.50 * semantic_similarity
      + 0.20 * keyword_overlap
      + 0.20 * file_type_match
      + 0.10 * recency
```

重みのデフォルトは上記。`.kcs/config.toml` の `[organize.weights]` で上書き可。

### 採否しきい値

```text
score >= 0.85: 自動承認候補 (auto-mode 時のみ自動移動。それ以外は最上位提案として inbox に出す)
0.65 <= score < 0.85: 提案として表示 (ユーザー承認待ち)
score < 0.65: 表示しない (低信頼)
```

### Embedding profile mismatch 時の退避

Folder Profile は配下ファイルの Embedding 平均だが、`embedding profile_hash` が混在するフォルダでは平均を取れない。`(dimensions, distance, modality, profile_hash)` ごとに **subprofile** を持ち、新ファイルの profile に一致する subprofile のみを比較対象にする。一致がない場合は `keyword_overlap + file_type_match + recency` だけで提案を出す (semantic は欠損扱い)。

### 評価方針

precision / recall を継続的にモニタするため、ground truth セットと評価指標を定める。

```text
Ground truth セット:
- ユーザーが kcs move --accept / --reject した過去 N=500 件を保存
  (~/.local/share/kcs/organize-feedback.sqlite)
- accept = 提案が正しかった、reject = 誤りだった

指標:
- precision@1 = accept(1) / (accept(1) + reject(1))   # 最上位提案の正解率
- recall@k    = ユーザーが手動で動かした先が上位 k 件に含まれた率
- target: precision@1 >= 0.7, recall@3 >= 0.85 (MVP 受入)
```

### フィードバックループ

reject されたファイル × フォルダ組は、24h は提案上位から抑制する (negative cache)。連続 reject が閾値を超えたフォルダ profile は再構築候補として `kcs status` に表示。

### 循環防止

`kcs move --accept` 直後の N=10 分間、移動先フォルダで同ファイルの再分類提案を出さない。これにより「移動 → 別 `.kcs` で再 indexing → 別フォルダへの再分類提案」サイクルを抑制する。

### コールドスタート

配下ファイル数 < 5 のフォルダは folder profile を構築しない (= 提案先候補から除外)。ユーザーが手動でファイルを移動して数が増えてから提案対象になる。

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
