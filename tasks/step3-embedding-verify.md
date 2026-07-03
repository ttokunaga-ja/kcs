# Step3 発注前調査: Embedding ベンダー実地検証 (07 §5.3 リスク注記)

- 調査日: 2026-07-03
- 目的: 07-adapter-spec.md §5.3 が Step 2/3 着手前に要求する「単一マルチモーダル Embedding profile が実在・実用か」の裏取り。凍結例外 (09 §6.2 条件1) を適用するかの判定。
- 前提: 検索対象は日本語主体の個人文書、chunk 単位で数万〜10万 chunk、ローカル SQLite + sqlite-vec (10 §6)、brute-force KNN。budget は embedding 月 $10-20 想定。北極星 M3-1〜3 は text 検索のみで Done。
- 制約: 実 API 呼び出しはしていない (キー無し)。公式 doc / 価格ページ / ベンチマークを一次情報とした。出典は末尾。

---

## 1. マルチモーダル embedding API (text/image を同一 vector space) の実在調査

| モデル | 提供形態 / GA | 次元 (Matryoshka) | 距離 | 価格 | 版ピン留め | deprecation | 日本語 text | text専用比の品質 |
|---|---|---|---|---|---|---|---|---|
| **voyage-multimodal-3** | Voyage / GA | 1024 既定 (256/512/1024/2048) | cosine | $0.12/1M tok + $0.60/1B px (無料枠 200M tok/150B px) | ○ 版番号名で固定 | 公表なし | ベンチ値なし (未検証) | voyage-3 と同等 (英 +0.05%)。**voyage-3.5 より下** |
| **voyage-multimodal-3.5** | Voyage / GA (2026-01) | 同上 + video | cosine | 同上 | ○ | 公表なし | ベンチ値なし | 3系の延長。日本語未検証 |
| **cohere embed-v4.0** | Cohere / GA (2025-04) | 256/512/1024/1536 | cosine | $0.12/1M tok | ○ 版番号名で固定 | プロセス有 (v2系は2026-04退役)。v4は現行推奨 | 100+言語対応 (JMTEB個別値なし) | 統合モデル (text=multimodal 同一)。MTEB 65.2 |
| **Gemini Embedding 2** (`gemini-embedding-2-preview`) | Google / **preview** | 128〜3072 (768推奨) | — | text $0.20/1M (batch 50%off) | **× preview名は不安定** | preview は将来退役前提 | 100+言語 (native multimodal) | natively multimodal かつ MTEB上位。**だが preview** |

要点:
- **GA かつ版ピン留め可能な multimodal API は実在する** = voyage-multimodal-3 / voyage-multimodal-3.5 / cohere embed-v4.0。判定基準 (a) は「存在する」で満たす。
- ただし品質の裏取りは弱い。voyage-multimodal-3 は英語 pure-text で **voyage-3 と同等** (公式)。voyage-3 は既に voyage-3.5 (+8.25% over openai-3-large) に更新されており、multimodal-3 の text 品質は現行 text 専用の一世代前に相当。**日本語の数値は JapaneseEmbeddingEval / JMTEB いずれにも無く未検証**。
- 「natively multimodal かつ SOTA text」を満たす唯一の候補 Gemini Embedding 2 は **preview**。07 §6 の「版付きモデル名で呼ぶ」= immutable pin 要件と、03 §7「profile 変更=全 re-index」に照らし、MVP identity の土台に採れない。

---

## 2. text-only 第一候補調査

| モデル | 提供形態 / GA | 次元 (Matryoshka) | 距離 | 価格 | 版ピン留め | deprecation | 日本語 (JapaneseEmbeddingEval avg 他) |
|---|---|---|---|---|---|---|---|
| **gemini-embedding-001** | Google / GA (stable) | 3072 既定 (768/1536/3072) | cosine | $0.15/1M (batch $0.075) | ○ 版番号名 | 有 (旧 embedding-001/text-embedding-004 は日付付き退役)。予測可能 | **MTEB multilingual #1 = 68.32**。JMTEB個別値未取得だが多言語首位 |
| **OpenAI text-embedding-3-large** | OpenAI / GA | 3072 既定 (→1024/256) | cosine | $0.13/1M | ○ 版番号名 | 公表退役なし | avg **0.830** (JSTS 0.838 / JSICK 0.812 / MIRACL 0.841)。MTEB 64.6 / MIRACL 54.9 |
| **voyage-3.5** | Voyage / GA | 256/512/1024/2048 + int8/binary量子化 | cosine | **$0.06/1M** | ○ 版番号名 | 公表なし | 26言語multilingual。openai-3-large 比 +8.25% (日本語個別値なし) |
| **multilingual-e5-large** (ローカル) | OSS / self-host | 1024 | cosine | 無料 (自前計算) | ○ (weights固定) | 無 | avg **0.832** (JSTS 0.819 / JSICK 0.794 / MIRACL 0.883) |
| **Ruri-large** (cl-nagoya, ローカル) | OSS / self-host | 1024 | cosine | 無料 (自前計算) | ○ | 無 | avg **0.842** (JSTS 0.842 / JSICK 0.819 / MIRACL 0.864)。**日本語で openai-3-large / me5 を上回る** |

要点:
- 日本語の実測 (JapaneseEmbeddingEval, oshizo) では **日本語特化ローカル Ruri-large (0.842) > multilingual-e5-large (0.832) > OpenAI-3-large (0.830)**。日本語特化モデルが商用汎用モデルを上回る、が確認できた。
- gemini-embedding-001 は JapaneseEmbeddingEval に個別行が無いが、MTEB multilingual を 68.32 で首位維持 (2026-04時点)。日本語を含む多言語で商用最上位。GA・版番号名・batch 50%off。
- text 専用側は「日本語品質が検証済み」かつ「版ピン留め可能」かつ「価格が budget 内」の三条件を複数候補で満たす。

---

## 3. 判定 (07 §5.3 契約 vs 事前承認済み text-only 緩和)

判断基準ごとの評価:

| 基準 | 内容 | 結果 |
|---|---|---|
| (a) | 版ピン留め可能な multimodal API が実在するか | △ 実在する (voyage-mm-3 / cohere embed-v4) **が**、native-multimodal かつ SOTA-text の Gemini Emb 2 は preview で pin 不可。両立する profile が無い |
| (b) | 価格が budget ($10-20/月) と整合するか | ○ 全候補 OK (下記 §4 概算) |
| (c) | 日本語 text 品質を犠牲にしないか | **× multimodal 側が不利**。voyage-mm-3 は text-3系一世代前相当かつ日本語未検証、cohere-v4 は MTEB 65.2 で gemini-001 (68.32) 未満・JMTEB個別値なし |

**決定的ロジック**: image embedding は北極星 M3-1〜3 (= MVP の Done 条件) に一切寄与しない (すべて text 検索で完結)。よって Step 3 で単一 multimodal profile を確定して得られるのは **MVP では一度も Done 検証されない image 経路のみ**。その代償として (c) の日本語品質の不確実性/劣後を profile_hash に固定し、しかも profile 変更は全 re-index (03 §7) を伴う。これは割に合わない。

→ **凍結例外 (09 §6.2 条件1 / 07 §5.3) を適用する。MVP は `modality=text` の単一 Embedding Adapter とし、multimodal は 07 §5.3 の schema (`input_type` / `embeddings.modality`) を interface 予約として残す。**

multimodal を将来有効化する際の先頭候補は cohere embed-v4.0 (統合単一 vector space・GA・版ピン留め・1024 次元) または voyage-multimodal-3.5。その時点で別 profile_hash として全 re-index (03 §7) で切替え、日本語品質を再検証する。

---

## 4. 推奨構成

### 4.1 profile (tool-lock.json / embedding)

```json
{
  "embedding": {
    "tool_id": "gemini_text_embedding",
    "kind": "online_api",
    "mode": "batch",
    "dimensions": 768,
    "distance": "cosine",
    "modality": "text",
    "profile_hash": "sha256:..."
  }
}
```

- **第一候補 (online 既定)**: `gemini-embedding-001`, **768 次元** (Matryoshka)、cosine、batch mode。
  - 理由: MTEB multilingual #1 (68.32)、GA・版番号名で immutable pin (07 §6 の「版付きモデル名で呼ぶ」に合致)、退役が日付付きで予測可能 (計画的 re-index 可)、batch $0.075/1M で最安級。
  - 768 次元は Google 推奨の production sweet spot。sqlite-vec brute-force での 10万 chunk 格納は float32 で約 307 MB (768×4B×100k)、10 §6 の spike 目標 (p95<5s) に収まる規模。
- **fallback (online)**: `text-embedding-3-large`, 1024 次元 (Matryoshka)、cosine, $0.13/1M。日本語 avg 0.830 実測済み。コスト最優先なら `voyage-3.5` ($0.06/1M, +8% over openai-3-large) も可。
- **offline baseline (任意, no-network)**: `multilingual-e5-large` (0.832) もしくは日本語最上位の `Ruri-large` (0.842) を offline_api Adapter として提供。※ KCS の baseline index は BM25 のみ (07 §2.1) なのでローカル embedding は必須ではない。日本語を最重視するユーザ向けの上振れ選択肢。
- **multimodal 予約**: 07 §5.3 の `input_type`/`modality` schema と `embeddings.modality` 列は残置 (interface 予約)。image 経路は Step 3 で配線しない。

### 4.2 tool_profile の pin 方針 (07 §6 整合)

- config (`tools.toml`) では alias 可だが、Adapter は **呼び出し自体を版付き名 `gemini-embedding-001` で行い**、`model_version_pin` を `tool_profile_hash` 入力に記録する (03 §5.1 — 可変 alias の pin 禁止)。embedding モデル名は数値版が版そのもの (`-latest` alias 不要) なので OCR (07 §6) のようなモデル一覧 API での解決は不要。
- distance=cosine / dimensions=768 / modality=text を profile に固定。03 §7 の横断検索互換 (dimensions/distance/modality/profile_hash 一致) はこの固定値で担保。

### 4.3 概算コスト (10万 chunk)

前提: 日本語 chunk ≈ 平均 500 tok/chunk → 初回 10万 chunk ≈ 50M tokens。

| モデル | 初回 (50M tok) real-time | 初回 batch | 増分 (月2k chunk ≈ 1M tok) |
|---|---|---|---|
| gemini-embedding-001 | $7.5 | **$3.75** | $0.15 (batch $0.075) |
| openai text-embedding-3-large | $6.5 | — | $0.13 |
| voyage-3.5 | $3.0 | — | $0.06 |

初回は一過性コストで月 budget $10-20 に単月で収まる。増分は月 $1 未満。**budget 整合 = 問題なし**。

---

## 5. 結論: 07 §5.3 の凍結例外を適用するか

**Yes — 適用する (MVP は modality=text 単一 Embedding Adapter、multimodal は interface 予約のみ)。**

根拠 (3行):
1. GA・版ピン留め可能な multimodal API は実在する (voyage-multimodal-3 / cohere embed-v4.0) が、その日本語 text 品質は未検証 (JapaneseEmbeddingEval/JMTEB に数値なし) または gemini-001 未満で、唯一 native-multimodal かつ SOTA-text の Gemini Embedding 2 は preview のため版ピン留め不可 (profile 変更=全 re-index の MVP 土台に不適)。→ 判定基準 (a)+(c) を同時に満たす multimodal profile が存在しない。
2. 北極星 M3-1〜3 は text 検索のみで Done。image embedding は MVP の Done 条件に一切寄与せず、日本語品質の不確実性を負ってまで multimodal profile を Step 3 で確定する利得がない。
3. text 専用候補 (gemini-embedding-001 / openai-3-large / voyage-3.5、ローカル Ruri/me5) は日本語品質が実測で検証済み・版ピン留め可能・価格も budget 内。よって基準 (b)(c) を満たす text-only profile を Step 3 で確定する方が合理的。

---

## 6. 出典 URL

マルチモーダル:
- Voyage multimodal-3 blog: https://blog.voyageai.com/2024/11/12/voyage-multimodal-3/
- Voyage multimodal-3.5 blog: https://blog.voyageai.com/2026/01/15/voyage-multimodal-3-5/
- Voyage pricing: https://docs.voyageai.com/docs/pricing
- Voyage multimodal docs: https://docs.voyageai.com/docs/multimodal-embeddings
- Cohere Embed Multimodal v4 changelog: https://docs.cohere.com/changelog/embed-multimodal-v4
- Cohere embeddings docs: https://docs.cohere.com/docs/embeddings
- Cohere deprecations: https://docs.cohere.com/docs/deprecations
- Vertex AI multimodalembedding: https://console.cloud.google.com/vertex-ai/publishers/google/model-garden/multimodalembedding
- Gemini Embedding 2 (preview) 論文: https://arxiv.org/pdf/2605.27295
- Jina embeddings v4: https://jina.ai/news/jina-embeddings-v4-universal-embeddings-for-multimodal-multilingual-retrieval/

text-only:
- gemini-embedding-001 GA blog: https://developers.googleblog.com/gemini-embedding-available-gemini-api/
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Gemini Embedding paper: https://arxiv.org/html/2503.07891v1
- OpenAI new embedding models: https://openai.com/index/new-embedding-models-and-api-updates/
- OpenAI text-embedding-3-large model page: https://platform.openai.com/docs/models/text-embedding-3-large
- Voyage-3.5 blog: https://blog.voyageai.com/2025/05/20/voyage-3-5/
- Voyage text embeddings docs: https://docs.voyageai.com/docs/embeddings

日本語ベンチ:
- JapaneseEmbeddingEval (oshizo): https://github.com/oshizo/JapaneseEmbeddingEval
- JMTEB (sbintuitions): https://github.com/sbintuitions/JMTEB
- Ruri paper: https://arxiv.org/html/2409.07737v1
- MTEB leaderboard 2026 (Google #1 68.32): https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/
