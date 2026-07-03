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

---

# 再検証 (2026-07-03、gemini-embedding-2 GA を受けて)

- 契機: ユーザーからの事実訂正 — 上記本文 §1/§3/§5 が前提にした「Gemini Embedding 2 multimodal は **preview** で版ピン留め不可」は誤り。**gemini-embedding-2 は 2026-04-22 に Vertex AI / Gemini API で GA 済み**。前回判定の決定的ロジック (判定基準 (a): pin 可能な multimodal が存在しない) の土台が消えたため再検証する。
- 本文 §1〜§6 は削除しない。以降が最新の有効判定。

## R1. 事実確認 (一次情報 + 二次情報、出典 URL 付き)

| # | 論点 | 確認結果 | 出典 |
|---|---|---|---|
| 1 | GA / 版ピン | **GA 済み (2026-04-22)**。Vertex の versioning ポリシーは「数値/日付付き stable version は本番の再現性用に固定、版番号なしの bare 名は auto-updated alias」。gemini-embedding-2 系には **pinned stable version が存在** (`gemini-embedding-2-flash-001` は "a pinned, stable version … for consistent, reproducible vectors over time" と明記。zenn/ユーザー提供では GA 名 `gemini-embedding-2` + preview `gemini-embedding-2-preview`)。→ **immutable pin は取得可能** | [1][2][3][4] |
| 2 | 料金 (PayGo, per 1M tok) | text **$0.20** / image **$0.45** (または $0.0001/画像) / audio **$6.50** / video **$12.00**。**Vertex は batch 非対応**（ユーザー訂正・zenn 一致）。※ Gemini Developer API 側は preview 期に「batch 50%off = $0.10/M」の記載があるが GA/Vertex では非対応として扱う（矛盾は R5 に明記） | [5][6][7][8] |
| 3 | text / 日本語品質 | MTEB/MMTEB Multilingual mean-by-task **69.9** = gemini-embedding-001 の **68.32 を上回る**（多言語集計で strict improvement、100+ 言語で首位圏）。MMEB (multimodal) 68.9。**日本語**: Google は JMTEB 個別値未公表。第三者 日本語 RAG 実測は P@1=0.588 / MRR=0.724 (fp16)。ただし日本語特化 OSS (Ruri v3 / PLaMo-Embedding-1B / Sarashina-Embedding) が Gemini を上回る構図は **gemini-001 でも同じ**（本文 §2: Ruri-large 0.842 > OpenAI-3-large 0.830）で、gemini-2 固有の劣化ではない | [1][9][10][11][12] |
| 4 | レート制限 / batch 非対応の運用 | gemini-embedding-2 は **global quota + Standard PayGo の shared-throughput tier**（固定 RPM/TPM は非公開・動的）。batch 非対応 = 初回 index は online 呼び出しをクライアント側で並列化 + 429/RESOURCE_EXHAUSTED backoff する必要。10万 chunk (≈8,192 tok/req に複数 instance を詰め、数百〜千 RPM 帯) なら **数十分〜数時間**で完了見込み。online 経路は incremental 更新（1ファイル編集の再 embed）で必須なので、batch 喪失で失うのは初回 bulk の利便とコストのみ | [4][13][14] |
| 5 | 次元 (MRL) | MRL 対応、default **3,072**、公式推奨 **768 / 1,536 / 3,072**（下位に 128/256/512 も可）。768 は "near-peak quality at ~1/4 storage of 3,072" | [3][10] |

## R2. 判断基準ごとの再評価（本文 §3 の枠組みを更新）

| 基準 | 前回 | 今回 | 差分の理由 |
|---|---|---|---|
| (a) pin 可能な multimodal が実在 | × (Gemini Emb 2 は preview) | **○** | GA 済み。immutable stable version を pin 可能（03 §5.1 の `model_version_pin` 要件を満たす。bare alias は禁止なので Adapter が dated 版へ解決して記録 = OCR alias と同機構、07 §6） |
| (b) コスト ($10-20/月) | ○ | **○** | 初回 50M tok(=10万chunk×500tok) × $0.20 = **$10.0**（batch $3.75 比 +$6.25、単月 budget 内）。増分 1M tok/月 = $0.20。image/audio は MVP で embed しないので発生しない |
| (c) 日本語 text 品質を犠牲にしないか | × (multimodal 側が gemini-001 未満/未検証) | **○** | gemini-embedding-2 (69.9) ≥ gemini-embedding-001 (68.32)。前回 online 第一候補より **上振れ**。OSS 優位は online 全モデル共通の別軸で、offline baseline 選択肢（Ruri 等、§4.1）は不変 |
| (d) batch 非対応の運用影響 | (前回は batch $0.075 を活用) | **△→許容** | 初回のみ client-side 並列 + backoff が必要。online 経路は incremental で必須のため追加装置は最小。コスト増は +$6.25/一過性 |

## R3. 再判定 — **text-only 緩和を撤回し、単一 multimodal profile を採用する**

- 前回の text-only 緩和は「pin 可能かつ text 品質を犠牲にしない multimodal が存在しない」という**リスク回避**が唯一の根拠だった。その根拠（Gemini Emb 2 = preview）が事実誤認と判明し、**(a) pin ・(c) text 品質を同時に満たす multimodal profile が実在**することが確定した以上、緩和を維持する理由は消える。
- **07 §5.3 の本来の契約（単一 multimodal Embedding Adapter）を復元する。** MVP で実際に embed するのは **text chunk のみ**だが、profile を `modality=multimodal` にしておくことで、Phase 4+ の image/audio embedding 追加時に **03 §7 の全 re-index を回避**できる（dimensions/distance/modality/profile_hash が不変のまま、同一 vector space に image 経路を後付けできる）。これが 07 §5.3 が multimodal を要求した本来の狙いであり、text 品質の裏取りが取れた今、機会費用なしで取り戻せる。
- 唯一の実質コストは (d) の運用（batch 喪失 = online 並列 + backoff）と初回 +$6.25。北極星 M3-1〜3 は依然 text 検索のみで Done だが、profile を multimodal にしても MVP の text 検索経路・評価は変わらない（embed 入力が text のみなだけ）。

## R4. 推奨 profile

```json
{
  "embedding": {
    "tool_id": "gemini_multimodal_embedding",
    "kind": "online_api",
    "mode": "online",              // batch 非対応 (Vertex)。client 側で並列 + 429 backoff
    "dimensions": 768,             // MRL 切り詰め。profile に固定 (03 §7)
    "distance": "cosine",
    "modality": "multimodal",      // MVP は text 入力のみ。image/audio は Phase 4+ で同 profile に後付け
    "profile_hash": "sha256:..."   // 下記 capability から再算出 (旧 08c93195… は無効化)
  }
}
```

- **model / pin**: `model_or_tool_family = "gemini-embedding-2"`、`model_version_pin` = ベンダー immutable stable tag（Vertex なら dated/numbered 版、例 `gemini-embedding-2-flash-001` 相当。bare `gemini-embedding-2` が auto-updated alias なら 03 §5.1 の禁止に該当するため、Adapter が実行開始時にモデル一覧 API で dated 版へ解決して pin する = 07 §6 の OCR alias と同一機構）。**実装前に live model list で正確な immutable tag 文字列を確定すること**（本再検証時点で GA 名は `gemini-embedding-2` / `gemini-embedding-2-preview`（zenn/ユーザー提供）と `gemini-embedding-2-flash-001`（Google/MindStudio）で表記揺れがあり、pin 対象の確定は実測必須）。
- **次元**: 既定 **768**。根拠 — (i) 10万 chunk × float32 で 307 MB（1536=614 MB / 3072=1.23 GB）、sqlite-vec brute-force + 10 §6 の p95<5s 予算に収まる、(ii) 768 は near-peak quality（3072 の ~1/4 storage）、(iii) 07 §6 の tool-lock.json 例・EMB-2 fixture の 768 と連続。**MRL 切り詰め次元は profile_hash に固定**（03 §7）し、Adapter はベンダー MRL 手順（先頭 N 次元 + L2 再正規化）を決定論的に適用する。品質最優先の大規模コーパス向けに 1536 を上位オプションとして残す（3072 は storage/latency 割に合わず非推奨）。
- **modality の二軸**（docs owner 向け注意、R5 参照）: tool-lock/profile の `modality=multimodal`（Adapter 能力）と、embeddings テーブル行の `modality`（各 vector の入力種別 = text chunk なら `text`）は**別軸**。03 §7 の横断検索互換は `profile_hash / dimensions / distance` を主キーに判定し、行 modality の text/image を混同しないこと（text も image も同一 multimodal 空間で比較可能）。

## R5. 07 §5.3 / 発注書 step3c / 契約テスト step3a への影響（発注側が docs に反映）

1. **07 §5.3 の注記（line 219）**: 「text-only 緩和を適用」→「**multimodal profile を採用（gemini-embedding-2、GA）**。MVP は text chunk のみ embed、image/audio は Phase 4+ に同 profile で後付け（全 re-index 不要）」に書き換え。第一候補 profile を `gemini-embedding-2 / 768 / cosine / multimodal / online` に更新。
2. **07 §6 tool-lock.json 例（line 284-293）**: `tool_id` を multimodal 用に、`mode` を `batch`→`online`、`modality` を `text`→`multimodal` に更新。alias→dated 版解決の一文（OCR と同機構）を embedding にも適用。
3. **03 §5.2 tool_lock_hash / §7**: `modality=multimodal` 値化。§7 に「profile modality と per-row embeddings.modality は別軸」の明確化を追記（R4 参照）。
4. **発注書 step3c（line 13, 20）**: 「text-only 緩和適用済み・第一候補 gemini-embedding-001 (768/cosine/batch)」→「multimodal 採用・gemini-embedding-2 (768/cosine/**online**/multimodal)」。「batch mode」記述を online に修正。
5. **【重要・要判断】契約テスト step3a の凍結 vector 失効**: step3a は text-only profile を **実計算済み・変更禁止**で凍結している。撤回すると次が無効化される —
   - `tool_profile_hash = sha256:08c93195…b20f`（`model_or_tool_family=gemini-embedding` / `model_version_pin=gemini-embedding-001` / `modality=text` / `dim=768` から算出、step3a line 130-131）
   - それに依存する **EMB-2 embedding_hash = sha256:728cd198…d8c5**（line 133, 352）
   - **CT3-EMBED-004**（"text-only 緩和適用時の契約 (modality=text 単一 Embedding)"、line 373-381）— 前提そのものが撤回される
   → **step3c 実装着手前に step3a を multimodal profile で再凍結**（model_or_tool_family=`gemini-embedding-2` / model_version_pin=確定 dated 版 / modality=`multimodal` / dim=768 で tool_profile_hash・embedding_hash を再計算、CT3-EMBED-004 を multimodal 契約へ差し替え）する必要がある。これは発注書 step3c の「期待値の変更禁止」と衝突するため、**再凍結は発注側の明示判断事項**。dim は 768 据え置きでも profile_hash は必ず変わる（model/modality が hash 入力）ので、この再計算は不可避。
6. **09 §6.2 凍結例外（条件1）の適用取消**: text-only 緩和は撤回されるため、当該凍結例外の embedding への適用は解除。

## R6. 追加出典

- [1] Gemini Embedding 2 GA blog (Google): https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-embedding-2-generally-available/
- [2] Vertex AI model versions & lifecycle (stable vs auto-updated alias): https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/model-versions
- [3] Gemini Embedding 2 model doc (Vertex): https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/embedding-2
- [4] MindStudio: Gemini Embedding 2 variants (`gemini-embedding-2-flash-001` = pinned stable): https://www.mindstudio.ai/blog/what-is-gemini-embedding-2
- [5] Gemini Enterprise Agent Platform pricing (Vertex): https://cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing
- [6] Gemini Developer API pricing: https://ai.google.dev/gemini-api/docs/pricing
- [7] Gemini Embedding 2 cost calculator (holori): https://calculator.holori.com/llm/google/vertex_ai%2Fgemini-embedding-2
- [8] zenn (suwash) 仕様・ベンチ・採用判断 (GA 2026-04-22 / Vertex batch 非対応 / 料金): https://zenn.dev/suwash/articles/gemini_embedding_2_20260424
- [9] MMTEB 69.9 vs 68.32 比較 (leaderboard): https://awesomeagents.ai/leaderboards/embedding-model-leaderboard-mteb-april-2026/
- [10] buildfastwithai: 仕様/MTEB 69.9/推奨 768: https://www.buildfastwithai.com/blogs/gemini-embedding-2-multimodal-model
- [11] knowleful: 日本語で OSS が Gemini を上回る (Ruri v3 推奨): https://www.knowleful.ai/plus/embedding-japanese-oss/
- [12] AQUA テックブログ Gemini Embedding 2 完全ガイド: https://www.aquallc.jp/gemini-embedding-2-guide/
- [13] Vertex AI quotas & system limits (global quota / shared throughput): https://docs.cloud.google.com/vertex-ai/generative-ai/docs/quotas
- [14] Vertex batch prediction capabilities: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/maas/capabilities/batch-prediction
