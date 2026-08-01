# ローカル Adapter 導入計画 (offline_api)

作成: 2026-07-26。Web 調査 + コードベース突合により確定した、`execution_mode = "offline_api"`
の Embedding / Markdownize Adapter を KIO へ導入するための正本。
2026-07-26 追記: §4 (検索結果への画像の載せ方) と Stage 1.5 を追加。

> **Stage 0 完了 (2026-07-26)**: §5 の裁定事項を spec 文書へ反映済み。
> 反映先は §5 の各項目に記載。実施時に判明した修正・追加は次のとおり。
>
> - **D2 は事実誤りだったため訂正した** — `runtime_kind = "local"` は同梱 deterministic
>   Adapter が既に本番使用中 (semver pin)。`execution_mode = "offline_api"` による限定を追加。
> - **D9 を新設** (consent gate 免除)。当初の裁定リストに欠けていた最大の論点。
> - **D10 を新設** (`image_vec` DDL)。§12 が Stage 0 前倒し対象に挙げていたが D 項目に無かった。
> - **V6 / U6 を確定**させ、§11 の未確定リストから外した。
> - 隣接する既存の不整合 2 件 (08 §7.1 の古い例、05 §1.7 に欠けていた `aggregator`) を併せて解消。

> 関連: [07-adapter-spec.md §2](../docs/07-adapter-spec.md) (実行形態) / [§3](../docs/07-adapter-spec.md) (network opt-in) /
> [§5.3](../docs/07-adapter-spec.md) (Embedding profile) / [§7](../docs/07-adapter-spec.md) (policy) /
> [03-data-model.md §5.1](../docs/03-data-model.md) (tool_profile_hash) / [§7](../docs/03-data-model.md) (embedding 互換) /
> [04-pipeline.md §4.3](../docs/04-pipeline.md) (embeddings / chunk_vec schema) /
> [05-runtime.md §1.7](../docs/05-runtime.md) (AI Agent レスポンス契約) / [§1.8](../docs/05-runtime.md) (RRF / MMR / multi-scope) /
> [08-evidence-pointer-spec.md](../docs/08-evidence-pointer-spec.md) (Evidence Pointer)

---

## 0. 現状 (grep 根拠付き)

| 要素 | 状態 | 根拠 |
|---|---|---|
| `ExecutionMode::OfflineApi` | **どこからも構築されていない** | 定義 [types.rs:23](../crates/kio-adapter/src/types.rs) と文字列化 [main.rs:21402](../crates/kio-cli/src/main.rs) のみ |
| `runtime_kind: "cloud" \| "local"` | `tool_profile_hash` の入力として実装済み | [identity.rs:39](../crates/kio-adapter/src/identity.rs) / [03 §5.1](../docs/03-data-model.md) |
| ローカル LLM = 単価 0 | **実装済み** | [main.rs:21035](../crates/kio-cli/src/main.rs) の `candidate_usd == 0.0` が cap 判定を bypass / [ledger/ops.rs:642](../crates/kio-pipeline/src/ledger/ops.rs) CL29 |
| offline markdownize 経路 | `DeterministicAdapter` が稼働中 | [catalog.rs:49](../crates/kio-adapter/src/catalog.rs) `builtin_offline_markdownize_adapter` |
| **role のゲート** | markdown / embedding とも built-in 1 個に固定。`kind != "online_api"` / `cmd`/`args`/`url` は schema error | [tool_lock.rs:226-329](../crates/kio-adapter/src/tool_lock.rs) `validate_supported_runtime_target` / `require_online_kind` |
| 画像オブジェクト | **作成・保存・テスト済み** (`objects/image/`) | [mistral_ocr.rs:1425](../crates/kio-adapter/src/mistral_ocr.rs) `persist_images` / [tasks/step3-ocr-image-fixtures.md](step3-ocr-image-fixtures.md) |
| 画像の Markdown 埋め込み | **実装済み**。`![alt](kio://<scope_id>/object/image/<hash>)` 形で normalized 本文に入る | [mistral_ocr.rs:1600](../crates/kio-adapter/src/mistral_ocr.rs) `replace_image_placeholders` (呼出 :725) / [:1362](../crates/kio-adapter/src/mistral_ocr.rs) `image_object_uri` |
| 画像の `kio open` | **実装済み**。`objects/image/` から解決してキャッシュパスを返す | [main.rs:10885](../crates/kio-cli/src/main.rs) `VALID_TYPES = ["image"]` / `resolve_object_uri` |
| 画像**埋め込み** | **経路なし**。`EmbeddingInputType::{Image,ImageObject}` / `EmbeddingTargetType::Image` は宣言のみで構築 0 件 | 構築されるのは `MarkdownChunk` [main.rs:15496](../crates/kio-cli/src/main.rs) と `Query` [main.rs:14454](../crates/kio-cli/src/main.rs)、`TargetType::Chunk` + `Modality::Multimodal` [main.rs:16363](../crates/kio-cli/src/main.rs) のみ |
| `image_object_hashes` | 3 構造体に宣言のみ・writer / reader なし | [07 §5.1](../docs/07-adapter-spec.md) が明記 / [prepare.rs:196,317,325](../crates/kio-pipeline/src/prepare.rs) は常に `Vec::new()` |

---

## 1. 裁定 (2026-07-26 ユーザー承認済み)

1. **Embedding はマルチモーダル入力対応モデルのみ採用する** (テキスト専用モデルは不採用)。
   [03 §7](../docs/03-data-model.md) の `modality="multimodal"` 固定を local にもそのまま適用する。
2. **日本語特化の実測は採用条件にしない。** 単一言語ではなく総合性能を優先する。
3. **常駐させない。** モデルは index / search の局面でのみ展開する。
4. **画像埋め込みを Stage 2 のスコープに含める** (Phase 4+ へ送らない)。
5. Sarashina2.2-OCR の vLLM 対応のための変更は許容する。
6. **検索結果は pointer であって payload ではない。** 画像ヒットは
   `payload_uri` (画像オブジェクト URI) と `evidence_pointer` (参照元 chunk) の**両方**を持つ (§4.1)。
7. **ランキングは統合する。クエリ意図の推定はしない。** 型で絞る場合は `--type` の明示フィルタ (§4.2)。
8. **Agent への画像受け渡しは path / URI で行う。** 検索レスポンスに base64 を埋めない (§4.4)。

---

## 2. サービング層の実態 (2026-07 時点)

**OpenAI の embeddings API スキーマには画像フィールドが無い。** したがって「ローカルの
OpenAI 互換 `/v1/embeddings` へ投げる」だけではマルチモーダル埋め込みは成立しない。

| スタック | テキスト埋め込み | **画像埋め込み** | 形式 / 状態 |
|---|:---:|:---:|---|
| **vLLM / SGLang** | ✅ | ✅ | `POST /v1/embeddings` に `input` ではなく **`messages`** を渡す superset。`--runner pooling` + `--chat-template`。**主系統** |
| llama.cpp (upstream) | ✅ | ⚠️ | **非 OAI の `POST /embedding`** が `content: {prompt_string, multimodal_data[]}` で対応 (#12898、experimental)。`/v1/embeddings` は非対応 |
| LM Studio | ✅ | ❌ | 露出するのは OpenAI 互換 `/v1/embeddings` (テキストのみ) と REST API v0。llama.cpp の native `/embedding` を通していない |
| Ollama | ✅ | ❌ | `/api/embed` の入力は string / string[] のみ (issue #5304 が 2024-06 から未解決) |

### 🔴 llama.cpp 経路は「動く」だけでは採用できない

配管は汎用でも、**モデルごとに vision encoder の数値互換を検証しないと使えない**。
llama.cpp Discussion #14851 (jina-embeddings-v4) の実測:

> text embeddings matched perfectly, **image embeddings diverged significantly**

原因は RoPE 単独ではなく patch creation / patch projection / patch gathering / LLM 内
cross attention の複数箇所。2025-08 時点で未解決・upstream 未マージ。Qwen3-VL-Embedding も
Discussion #19516 / draft PR #18665 が停滞中 (`1_Pooling` の問題)。

**KIO にとって致命的な理由**: 「テキストは一致・画像だけ乖離」という失敗モードは
**[03 §7](../docs/03-data-model.md) の互換ゲートが原理的に検知できない** (次元・distance・modality・
`profile_hash` がすべて一致するため)。しかも embedding は content-addressed identity を持ち
first-instance-wins で永続化されるので、**誤った空間の画像ベクトルが恒久的に凍結される**。

→ llama.cpp 経路の採用条件は **PyTorch 参照実装との数値一致検証**とする (Stage 2 の U7)。

---

## 3. 採用モデル

### 3.1 Embedding — **Qwen3-VL-Embedding-2B** (確定)

| 項目 | 値 |
|---|---|
| ライセンス | **Apache-2.0** |
| 規模 / 次元 | 2B / 28層 / native 2048、MRL 64–2048 |
| KIO 採用次元 | **768** (MRL 切り詰め — `chunk_vec` の `float[768]` を維持) |
| 入力 | テキスト / 画像 / スクリーンショット / 動画、およびその任意の組み合わせ |
| 実績 | 8B が MMEB-V2 **77.8** で全モデル 1 位。2B もクロスモーダル検索 0.945 で 1 位 |
| 配信 | vLLM ≥ 0.14.0 (`--runner pooling`) / SGLang (`is_embedding=True`) |

**ライセンスが決め手。** 対抗の jina-embeddings-v4 は当初 cc-by-nc-4.0 で公開後
「Qwen2.5-VL-3B 由来のため **Qwen Research License** が正しい」と訂正されており、
**研究・非商用限定**である。KIO は [PolyForm Shield 1.0.0](../LICENSE.md) で
「競合製品の提供以外のあらゆる目的 (商用・社内業務含む)」を許諾しているため、
既定の local embedding profile が研究ライセンスのモデルを指すと、
**KIO が持っていない制約を KIO の商用ユーザーへ押し付ける**ことになる。

**既知のトレードオフ (裁定 2 により受容)**: Qwen3-VL-Embedding は論文自身が MMTEB の
テキストのみタスクで同規模のテキスト専用 Qwen3-Embedding に対するギャップを認めている。
加えて Qwen3-Embedding は JMTEB での日本語 Retrieval が multilingual 総合の強さほど伸びない
という第三者報告がある。KIO は現状テキストチャンク主体で埋め込むため両者は直列に効くが、
**総合性能優先の裁定によりこれを受容する**。

### 3.2 Markdownize (OCR) — **既定 PaddleOCR-VL-0.9B + 任意 Sarashina2.2-OCR**

| | PaddleOCR-VL-0.9B (既定) | Sarashina2.2-OCR (任意) |
|---|---|---|
| ライセンス | Apache-2.0 | **MIT** |
| 規模 | 0.9B (NaViT encoder + ERNIE-4.5-0.3B) | 3B (SigLIP2 + Sarashina2.2-3B-Instruct) |
| 言語 | **109 言語** (日本語含む) | **日本語・英語のみ** |
| 出力 | Markdown / JSON、layout 座標・bbox | Markdown、表→HTML、数式→LaTeX、`<bbox>[(x1,y1),(x2,y2)]</bbox>` |
| 実績 | OmniDocBench v1.5 / v1.0 で SOTA | **VJRODa (縦書き日本語) CER 22.6 / BLEU 79.9 で最良** (GPT-4o-mini 72.4、Qwen2.5-VL-4B 86.1)。olmOCR-bench 0.683 |
| 配信 | **公式 vLLM 対応** (`paddleocr genai_server`) | transformers (`trust_remote_code`)。vLLM 化は裁定 5 により許容 |

#### なぜ両方を許すのか — markdownize は embedding と違い identity ロックが緩い

これは意思決定の中核なので明記する。

- **embedding**: profile が変わると [03 §7](../docs/03-data-model.md) の横断互換ゲートが
  incompatible と判定し、**全 chunk の再埋め込み**が必要になる。ベクトル空間は
  グローバルに 1 つでなければならない → **単一モデルへの収束が強制される**。
- **markdownize**: profile が変わっても [07 §9](../docs/07-adapter-spec.md) の
  first-instance-wins と [03 §2.1](../docs/03-data-model.md) の gen+1 により
  **既存 instance と Evidence Pointer は不変のまま残る**。[03 §7](../docs/03-data-model.md) の
  横断ゲートは embedding 専用で markdownize には適用されない。
- `tools.toml` はデバイスグローバル、`tool-lock.json` は **per-`.kio`**
  ([07 §6](../docs/07-adapter-spec.md))。したがって**デバイスに両方を宣言しておき、
  `.kio` ごとに lock する**構成が仕様上そのまま成立する。

→ **既定は多言語 (PaddleOCR-VL)** とし、裁定 2 (総合性能優先・単一言語をターゲットにしない) と
整合させる。**Sarashina2.2-OCR は日本語主体 scope 向けの第二 profile として登録可能にする** —
縦書き日本語では他を大きく引き離しており、捨てる理由が無い。選択の代償は当該 `.kio` に閉じる。

**Gemma 4 を第一候補にしない理由**: 汎用 VLM の失敗モードは「もっともらしい段落の捏造」であり、
Evidence Pointer を売りにするアーカイブでは品質差ではなく性質の違いになる。
[07 §8](../docs/07-adapter-spec.md) のプロンプト規約 (生成 LLM 系 Markdownize Adapter 向け) の
負担も最大。ただし Gemma 4 (Apache-2.0、E2B/E4B/12B、encoder-free、llama.cpp/MLX/Ollama 対応) は
**Mac 対応 OCR の唯一の現実解**であるため、第三 profile の候補として保留する。

---

## 4. 検索結果への画像の載せ方 (2026-07-26 確定)

KIO の主たる消費者は LLM Agent であり ([06 §9](../docs/06-cli-spec.md) — MVP の導線は
`kio search --json` + `kio open`)、現行モデルはほぼマルチモーダルである。
**適切な画像を Agent へ渡すことは KIO の使命に含まれる。**

### 4.1 pointer と payload を分離する — 「chunk か画像か」は偽の二択

[05 §1.7](../docs/05-runtime.md) のレスポンス契約が返すのは `chunk_hash` / `evidence_pointer` /
`evidence_uri` / `score` **のみ**で、本文すら含まない。Agent は `kio open <evidence_uri>` で
実体を取得する **2 段階プロトコル**である。したがって問うべきは
「chunk を返すか画像を返すか」ではなく **「result 行が何を指すか」**。

| フィールド | 役割 | 画像に使えるか |
|---|---|---|
| `evidence_pointer` | **引用の不変固定**。commit / tree / raw_hash / chunk_hash / path_at_commit / span を持ち、time-travel と `evidence verify` が可能 | ❌ **原理的に不可**。`kio://.../object/image/<hash>` は commit も tree も path_at_commit も持たず、時点指定も検証もできない ([08 §2.3](../docs/08-evidence-pointer-spec.md) — object URI は**参照用であって Evidence Pointer ではない**) |
| **`payload_uri` (新設)** | **LLM に渡す実体へのハンドル** | ✅ 画像ヒットなら画像オブジェクト URI。`kio open` でバイト列を取得 |
| **`result_type` (新設)** | `"chunk"` \| `"image"` | 表示・分岐用 |

→ **画像ヒットは `payload_uri` = 画像オブジェクト URI、`evidence_pointer` = 参照元 chunk** とする。
これにより画像を返しつつ Evidence Pointer の不変性・検証可能性・time-travel を守れる。

> 2026-07-26 の設計訂正: 当初案は「画像ヒットを参照元 chunk へ写像して返す」だった。
> これは **citation については正しく payload については誤り**である
> (Agent が欲しいのは画像そのものであり、それを指す chunk のテキストではない)。

### 4.2 ランキングは統合する — ただし構造的問題が 2 つある

**意図分類は採らない。** 非決定的であり KIO の設計原則 (決定論・テスト可能性) と衝突する。
KIO には既に `--mode <auto|text|vector|hybrid>` という明示軸があるので、型で絞る需要には
**`--type <all|text|image>` の明示フィルタ**で応じる (推定はしない)。

[UNIDOC-BENCH](https://arxiv.org/abs/2510.03663) の実測も分岐ではなく融合を支持する
(text-only / image-only / **fusion** / **joint embedding** の 4 方式比較で
"multimodal text-image fusion RAG systems consistently outperform both unimodal and
jointly multimodal embedding-based retrieval")。

> **不都合な事実**: 同ベンチは **fusion が joint embedding にも勝つ**、そして
> "current multimodal embeddings remain inadequate" と結論している。
> [03 §7](../docs/03-data-model.md) が強制する単一統合ベクトル空間はまさに joint 側である。
> ただし KIO は lane レベルで既に fusion 構造 (BM25 + vector を RRF) なので、
> **画像を「fusion される lane」に載せる**設計にすれば finding と整合する
> (下記 問題 A の対処案 (a) がそれに当たる)。

#### 問題 A: RRF が画像を構造的に不利にする [P0]

KIO の検索は BM25 text lane + vector lane を RRF 融合する ([05 §1.8](../docs/05-runtime.md))。
**画像は text lane に存在しない**ため、chunk が 2 lane から reciprocal rank を得るのに対し
画像は 1 lane 分しか得られず、**構造的に沈む**。

- **(a) 画像に text 表現を与える** ← 推奨。画像を参照している chunk の本文
  (または OCR が生成した alt/caption) を画像の text lane 表現として FTS に載せる。
  §0 のとおり参照は既に Markdown 中に存在するので手がかりは揃っている
- (b) 画像を別 lane として扱い quota で interleave する
- (c) 受容する

#### 問題 B: `max_per_raw_hash` と MMR が画像と chunk を競合させる [P0]

- [05 §1.8](../docs/05-runtime.md) の `max_per_raw_hash = 3` は同一 raw_hash の結果を 3 件に
  制限する。**画像とその参照 chunk は同じ raw_hash** を持つため同じ枠を食い合う
- MMR は「候補プールに embedding 未付与の chunk が 1 件でも混在すれば適用しない」規則である。
  画像にだけ embedding があり chunk が部分 enrichment という状況で **MMR が丸ごと無効化される**

→ Stage 2 の設計裁定に含める (画像を `max_per_raw_hash` の別枠にするか、同枠のまま許すか)。

### 4.3 段階 A / B / C

| 段階 | 内容 | 画像埋め込み | コスト |
|---|---|:---:|---|
| **A** (Stage 1.5) | chunk ヒットに `related_images[]` を添える | **不要** | **極小** |
| **B** (Stage 2) | 画像を独立に埋め込み vector lane へ。`result_type: "image"` + `payload_uri` | 必要 | 中 — 問題 A/B の解決を含む |
| **C** (将来) | page-as-image (ColPali 的) — ページ全体を画像として索引 | 必要 | 大 — Prepare が page image を持たない。[03 §5.1](../docs/03-data-model.md) の `render_params` が groundwork として既存 |

**段階 A を Stage 2 より前に出す。** 根拠は
[Index Light, Reason Deep (arXiv 2602.14162)](https://arxiv.org/abs/2602.14162) の実測 —
**画像を一切索引せず** BM25 でページを引き、**元画像を質問と一緒に VLM へ渡す**だけで
橋梁設計図 **65.6% vs 24.3% (+41.3pt)**、鋼材カタログ **30.6% vs 16.1% (+14.5pt)**。
2026 年のマルチモーダル RAG は「query 時に VLM へ元画像を見せる」設計を共有しており、
企業 PDF の約 80% が表・チャート・複雑レイアウトを含むため OCR ベース RAG は
劣化した入力から始まる、という指摘とも整合する。

→ **画像埋め込みの実装リスクをゼロで回避しつつ、LLM 消費者への価値を先に取れる。**
段階 B は A が確立した「画像を返す経路」の上に載せればよい。

### 4.4 base64 は渡さない

Agent への画像受け渡しの現行ベストプラクティスは **tool 引数に base64 を渡さず path / URI を渡す**
ことである (base64 は約 1 トークン/文字でコンテキストとコストを圧迫する。MCP でも符号化は
フレームワーク層に委ね、ファイル操作はサーバ側に留める)。

**KIO の search → open という 2 段階はこれと完全に一致している。**
`kio open` がキャッシュパスを返す既存挙動が正解であり、
**検索レスポンスに画像を base64 で埋めてはならない**。

---

## 5. Stage 0 — 裁定事項 (**2026-07-26 反映済み**)

| # | 内容 | 反映先 |
|---|---|---|
| D1 | offline_api の url を loopback リテラル限定 + 新 error code | [07 §3](../docs/07-adapter-spec.md) / [06 §8](../docs/06-cli-spec.md) / [06 §11](../docs/06-cli-spec.md) / [10 §12.1](../docs/10-operations.md) |
| D2 | local + offline_api の `model_version_pin` = 重み sha256 (**訂正あり**) | [03 §5.1](../docs/03-data-model.md) |
| D3 | chat template + instruction を `prompt_template_hash` へ | [07 §5.3](../docs/07-adapter-spec.md) |
| D4 | wire 形式を `messages` に一本化 | [07 §5.3](../docs/07-adapter-spec.md) |
| D5 | serving backend は identity 外 | [07 §5.3](../docs/07-adapter-spec.md) |
| D6 | 重み常駐はサーバ側の責務 | [05 §5](../docs/05-runtime.md) |
| D7 | execution_mode 別 timeout (`[adapter.policy.<mode>]`) | [07 §7](../docs/07-adapter-spec.md) |
| D8 | `result_type` / `payload_uri` / `related_images[]` | [05 §1.7](../docs/05-runtime.md) |
| **D9** | **offline_api を consent gate の対象外にする (新設)** | [07 §3](../docs/07-adapter-spec.md) / [05 §1.1](../docs/05-runtime.md) |
| **D10** | **`image_vec` DDL + rebuild 順 + purge 列挙 (新設)** | [04 §4.3](../docs/04-pipeline.md) / [05 §3.5](../docs/05-runtime.md) / [10 §7.5](../docs/10-operations.md) |
| V6 | 参照元 chunk 複数時の pointer 選択規則 (**確定**) | [05 §1.7](../docs/05-runtime.md) |
| U6 | `max_per_raw_hash` / MMR の image 行の扱い (**確定**) | [05 §1.4](../docs/05-runtime.md) |

### D1 `offline_api` の url は loopback リテラルに限定する [P0・セキュリティ]

[07 §3](../docs/07-adapter-spec.md) の送信同意は `execution_mode == online_api` を前提に
`approvals[]` 行 + scope config `allow_network` の AND で成立する。
`kind = "offline_api"` + `url = "https://api.example.com"` を受理すると
**同意記録なしに全ファイル本文が外部へ出る**。

- 受理: `127.0.0.1` / `localhost` / `[::1]` / UNIX domain socket **のみ**
- **ホスト名解決の結果ではなくリテラルで判定する** (DNS rebinding の排除)
- 違反は `KIO-E-CONFIG-OFFLINE-URL-001` (exit 2)
- **実装より先に [07 §3](../docs/07-adapter-spec.md) へ規範として追記する**

### D2 local の `model_version_pin` は重みファイルの sha256 とする [P0]

[identity.rs:102](../crates/kio-adapter/src/identity.rs) の `is_mutable_model_alias` が
`latest` 系を拒否する。ローカルでは `gemma-3-4b-it-q4_k_m` のようなタグ名は
「量子化違いで同名」になり得て pin として弱い。**重み (GGUF / safetensors) の sha256** を正本とする。

> 🔴 **2026-07-26 訂正 — `runtime_kind = "local"` だけでは条件が広すぎた**。
> 同梱の deterministic Adapter は既に `runtime_kind = "local"` で稼働しており、
> `model_version_pin` は **semver** である
> ([07 §2.1](../docs/07-adapter-spec.md) の PDF text layer 抽出が `1.0.0 → 1.1.0`、
> [identity.rs:163-171,193-204](../crates/kio-adapter/src/identity.rs) の凍結テストベクタが
> `"model_version_pin": "1.0.0"` / `"runtime_kind": "local"` を固定)。
> これらは**重みを持たないため sha256 が定義できない**。
> 当初の書き方は既存の運用規約を黙って上書きするものだった。
>
> **確定した条件**: `runtime_kind = "local"` **かつ** `execution_mode = "offline_api"`
> (= 重みを持つローカルモデル) のみ sha256。`deterministic_library` は semver のまま。

### D3 chat template と instruction を `prompt_template_hash` へ畳み込む [P0]

Qwen3-VL-Embedding は既定で `"Represent the user's input."` を system prompt として付与し、
タスク別 instruction で **1〜5% の精度差**が出る。vLLM のマルチモーダル埋め込みは
`--chat-template` に依存し、**同じ重みでも template が違えばトークン列が変わりベクトルが変わる**。
[identity.rs:9](../crates/kio-adapter/src/identity.rs) の `prompt_template_id` /
`prompt_template_hash` に固定する。

### D4 🔴 wire 形式を `messages` に一本化する [P0]

vLLM のテキスト埋め込みは `input: ["text"]` でバッチ可能だが、マルチモーダルは `messages` 必須。
`messages` は chat template でラップされるため、**同じモデル・同じ文字列でも `input` 経由と
`messages` 経由ではトークン列が異なりベクトルが異なる**。

MVP がテキストを `input` で、後から画像を `messages` で埋め込むと、
**同一 profile を名乗りながら実質 2 空間に分裂する** — 次元も distance も modality も
`profile_hash` も一致するため [03 §7](../docs/03-data-model.md) の互換ゲートは検知できない。

→ **テキストのみのチャンクでも常に `messages` 形式を使う。** 代償はバッチ不可
(1 リクエスト 1 アイテム) だが、[`send_embed_group`](../crates/kio-cli/src/main.rs) は既に
group ごとに 1 コールであり、ローカルサーバ側の continuous batching が吸収する。

### D5 ランタイム差は identity 外である旨を明文化する [P1]

[03 §5.1](../docs/03-data-model.md) は「実装バイナリのバージョン (`adapter_binary_version`,
OS, ハードウェア) は `binary_hash` として別保存し `tool_profile_hash` には含めない」と規定済み。
したがって **同一重み・同一 chat template なら vLLM 製のベクトルと llama.cpp 製のベクトルは
同一 profile として扱う**。この解釈を [07 §5.3](../docs/07-adapter-spec.md) に明記しておけば、
llama.cpp が upstream で対応した時点で **Mac を再埋め込みなしで合流させられる**。

### D6 モデル展開は TTL 付き遅延ロードに委ねる (裁定 3 の実装形) [P1]

- **index 側**: OCR モデル (Sarashina 3B BF16 ≈ 6–7GB) は index 中のみ必要。バッチのため
  ロードコストは償却される。裁定どおり常駐不要。
- **search 側**: [07 §5.3](../docs/07-adapter-spec.md) は「**例外 = query embedding は常に即時**」と
  定める。2B Q4 ≈ 1.5–2GB のロードで数秒かかり `kio search` の体感に直撃する。
- **KIO はプロセスを起動しない** ([07 §7](../docs/07-adapter-spec.md) — `cmd` は将来仕様) ため、
  「必要な局面で展開」の主体が KIO でないなら誰かが起動する必要がある。

→ **採用**: 「常駐」を **プロセス常駐 (数十MB・軽量) / 重み常駐 (idle TTL で解放)** に分離する。
llama-server / LM Studio / Ollama の idle TTL がそのまま裁定 3 の要件を満たす。
**KIO 側の実装は「サーバに繋がらなければ text fallback」のみ**
([05 §1](../docs/05-runtime.md) の既存縮退を再利用) で、`cmd` dispatcher は不要のまま。

### D7 execution_mode 別の timeout / max_input_bytes [P1]

[07 §7](../docs/07-adapter-spec.md) の既定 `timeout_seconds = 300` は
AdapterRun 1 回 = 1 request/job に適用される。CPU 推論の VLM は 1 ページで超え得る。

**確定した形**: `[adapter.policy.<execution_mode>]` の sub-table で上書きし、未指定キーは
親を継承する。enforcement 単位 (AdapterRun 1 回) は不変。`offline_api` の既定値は
Stage 3 の実測まで TBD。現時点で execution_mode 差を要するのは `timeout_seconds` のみ。

### D8 検索結果契約に `result_type` / `payload_uri` / `related_images[]` を追加する [P0・spec 改訂]

§4.1 / §4.3 の結論を [05 §1.7](../docs/05-runtime.md) のレスポンス契約へ反映する。
[06 §9](../docs/06-cli-spec.md) が「検索レスポンス schema」を Phase 5 構造化 API の
**互換性契約**として挙げているため、**MVP のうちに field を確定させておく**のが安全である
(後付けは互換性契約の変更になる)。§4.4 の base64 禁止も同節へ明記する。

なお [06 §9](../docs/06-cli-spec.md) 自体は「検索レスポンス schema ([05 §1.7](../docs/05-runtime.md))」を
参照で挙げているだけで形を複製していないため**変更不要**だった (確認済み)。

### D9 🔴 `offline_api` を network consent gate の対象外にする [P0・2026-07-26 新設]

**当初の裁定リストが取りこぼしていた最大の論点。**

[05 §1.1](../docs/05-runtime.md) は vector / hybrid の query embedding を**無条件に**
[07 §3](../docs/07-adapter-spec.md) の approvals[] + `allow_network` gate の対象としている。
しかし 07 §3 の opt-in 単位は明示的に「**`online_api` Adapter**」であり、
offline_api については「`execution_mode` と `profile_hash` は記録する」としか述べていない。
**ローカル embedding では何も端末外へ出ない**ため、この 2 つは矛盾している。

→ **完全に対象外とする** (ユーザー裁定)。

- `approvals[]` 行・`allow_network` boolean のいずれも要求しない
- **`--offline` 指定下でも local embedding による vector 検索は成立する** —
  `--offline` の定義は「当該実行の**新規送信**を禁止する」であり、送信しない Adapter には
  適用対象が無い。ローカルのみ構成のユーザーが常に text-only へ縮退する不合理を避ける
- `--online` も同様に無関係 (開くべき閉鎖が存在しない)
- **D1 と表裏一体である** — 免除が成立するのは url の loopback 限定が
  「送信が構造的に起こり得ない」ことを保証する場合に限る。両方を同じ addendum に書いた
- 免除しないもの: profile_hash 不一致 / `embedding_in_flight` /
  `embedding_contract_violation` / [07 §5.3](../docs/07-adapter-spec.md) の受入検査。
  これらは「送信してよいか」ではなく **vector が正当か**を問う規範であり execution_mode に依らない

### D10 `image_vec` の新設 [P0・spec 改訂・2026-07-26 新設]

§12 は Stage 0 前倒し対象に U3 を挙げていたが、D 項目に無かったため取りこぼしていた。
内容は §8 の U3 と同じ (`embeddings.target_type` は `image` を許容済みなのに
KNN 検索できる vec0 テーブルが chunk 用しか無い)。

実施時に判明した追加: **`image_vec` を作った以上、purge の SQLite 行列挙
([05 §3.5](../docs/05-runtime.md) が正本、[10 §7.5](../docs/10-operations.md) が要約) にも
含めないと、purge が画像ベクトルを取り残す**。判定単位は `image_hash` で、
共有画像は live 参照 0 の場合のみ削除する (chunk 側の `embeddings` 行と同じ規則)。
これは spec の自己整合の問題であり Stage 2 の U10 (実装) とは別。

---

## 6. Stage 1 — ゲート解放 (**embedding 分は 2026-07-26 完了**)

> 🔴 **本節の当初の記述は誤っていた** — 「`validate_supported_runtime_target` が唯一の
> ゲート」としていたが、**同じ規則が独立に 2 箇所へ実装されていた**。
>
> | | 場所 | 発火時点 |
> |---|---|---|
> | config 読込時 | `validate_supported_runtime_target` | 起動時の `tools.toml` 検証 |
> | **実行時** | **`validate_declared_runtime_target`** | `resolve_role_api_key` / `run_adopted_embedding` の Real arm |
>
> 後者だけを見落とすと、起動時検証を通った loopback url が**実行の瞬間に**拒否される。
> 両方を対称に緩和すること。

実施済み (embedding role のみ。markdown の offline は Stage 3):

- `require_online_kind` を `require_declared_kind(role, table, expected)` へ一般化
- **`EMBEDDING_RUNTIME_TARGETS` 表**を新設し、tool_id → `kind`/`mode`/`model`/
  `dimensions`/`distance`/`modality` を引く。Gemini の 768/cosine/multimodal/online
  ハードコードはこの表の 1 行になった
- `offline_api` では `url` を受理し、**D1 の loopback 判定** (`validate_offline_url`) を通す。
  `cmd` / `args` は**両 kind で拒否のまま** (Kio はプロセスを起動しない — [05 §5](../docs/05-runtime.md))
- 新 error code は `AdapterError::ConfigSchemaCoded { code, message }` で構造的に運ぶ。
  **`error_code()` に独自コードを返させることはできない** — あれは `retry_policy` の表に
  束縛されており `qa16_adapter_error_code_matches_retry_policy` が cross-check している。
  既存の `KIO-E-EMBED-MODALITY-001` の文字列 sniff もこの variant へ移行し、機構を 1 つにした
- **flat `[embedding]` 形は `kind` で target を解決する** (tool_id を書けないため)。
  offline embedding 実装が 2 つ目になったら tool_id 必須へ変える必要がある

**未実施 (Chunk B)**: 認証なし offline adapter の活性化。
`real_embedding_activation` は `declared.auth.is_some()` を見るが offline サーバは auth 不要。
これを先に広げると offline 宣言が `AdoptedEmbeddingExecution::Real` を活性化し
`GeminiEmbeddingAdapter` が loopback URL に対して構築されるため、**resolver と同時に入れる**。

```toml
# ~/.config/kio/tools.toml
[embedding.qwen3_vl_embedding_local]
kind       = "offline_api"
url        = "http://127.0.0.1:8000"
model      = "Qwen/Qwen3-VL-Embedding-2B"
dimensions = 768              # MRL 切り詰め — chunk_vec の float[768] を維持
distance   = "cosine"
modality   = "multimodal"
mode       = "offline"

[markdown.paddleocr_vl_local]
kind = "offline_api"
url   = "http://127.0.0.1:8001"
model = "PaddlePaddle/PaddleOCR-VL"

[markdown.sarashina_ocr_local]     # 日本語主体 scope 向け。.kio ごとに lock で選択
kind = "offline_api"
url   = "http://127.0.0.1:8002"
model = "sbintuitions/sarashina2.2-ocr"
```

---

## 7. Stage 1.5 — 検索結果への画像添付 (段階 A・画像埋め込み不要)

**ローカル Adapter とは独立に実施できる。** Stage 1 と並行、または先行してよい。

### W1 chunk 本文から画像 URI を抽出する [P0]
chunk の `text` に含まれる Markdown 画像参照
`![alt](kio://<scope_id>/object/image/<sha256>)` をパースする
([mistral_ocr.rs:1600](../crates/kio-adapter/src/mistral_ocr.rs) が埋め込んだ形)。
**決定論的なパースのみで、推論も追加索引も不要。**

- 抽出対象は `kio://<scope_id>/object/image/<hash>` 形の target に限る
  ([08 §2.3](../docs/08-evidence-pointer-spec.md) が accept する唯一の object URI type)
- `scope_id` と `hash` の形式検証は既存の [main.rs:10885](../crates/kio-cli/src/main.rs) 側の
  規則に合わせる (`is_hash` / 非空 scope_id)

### W2 レスポンスに `related_images[]` を載せる [P0]
```json
{
  "chunk_hash": "sha256:...",
  "result_type": "chunk",
  "evidence_pointer": { "...": "08 §2 の schema をそのまま" },
  "evidence_uri": "kio://...",
  "related_images": [
    { "image_uri": "kio://scope_01J8ZQ.../object/image/sha256:...", "order": 0 }
  ],
  "score": 0.87
}
```
`related_images` は**空なら field ごと省略**する (既存の `current_path` / `current_paths` の
省略規約と同じ姿勢 — [05 §1.7](../docs/05-runtime.md))。
Agent は `kio open <image_uri>` でバイト列を得る (§4.4 のとおり base64 は埋めない)。

### W3 chunk 境界をまたぐ URI の扱い [P1]
chunk は normalized unit 本文の byte span である ([03 §8.1](../docs/03-data-model.md))。
`[chunking].max_chars` (既定 6000) の切断が画像参照の途中に落ちると URI が分断され得る。
**分断された断片は抽出しない** (fail-empty) — 誤った hash を持つ URI を返すより安全側。
発生頻度は W1 実装時に dogfood corpus で計測して記録する。

### W4 purge / tombstone との整合 [P1]
purge 済み画像の URI が chunk 本文に残る場合がある。`related_images[]` は
**参照の列挙であって存在保証ではない**旨を [05 §1.7](../docs/05-runtime.md) に明記し、
`kio open` 側の既存の purge barrier ([main.rs](../crates/kio-cli/src/main.rs) の
`KIO-E-PURGE-NOT-FOUND-001`) がそのまま終端を担う。検索時に存在確認の I/O は行わない。

---

## 8. Stage 2 — ローカル Embedding Adapter (段階 B・画像埋め込みを含む)

> **U1 と配線は 2026-07-26 完了。** `crates/kio-adapter/src/local_embedding.rs` が
> `ExecutionMode::OfflineApi` / `allow_network: false` / `billable_kinds: []` /
> `preferred_request_kind: Sync` を宣言し、mock 実装で end-to-end に動作する。
> **実 HTTP wire (U2) は 2026-07-28 に実装済み** (下記 U2 節)。V4 で template・
> instruction・重み pin が実測で決まったので placeholder は要らなかった。
> ~~ただし **`dimensions` だけは V3 決着まで暫定**なので、`tool_profile_hash` を凍結扱いに
> せず、恒久コーパスを埋め込まないこと。~~
> **2026-08-01 解除** — V3b が 768 を確定させた (§11 の V3)。`dimensions = 768` と
> `tool_profile_hash` = `sha256:f9f610bb…439a` は**確定**であり、
> **恒久コーパスを埋め込んでよい**。
>
> 実装した dispatch:
>
> - `EmbeddingExecution { Online(AdoptedEmbeddingExecution) | Offline(LocalEmbeddingExecution) }` —
>   `AdoptedEmbeddingExecution` は Gemini の test seam 選択子という本来の役割に戻した
>   (`KIO_TEST_GEMINI_EMBED` の文字列値は不変。17 テストファイル 21 箇所が緑のまま)
> - `active_embedding_execution()` / `embedding_adapter_for()` →
>   `Box<dyn EmbeddingAdapter>`。**trait は既に正しい抽象だった** — `profile()` が
>   `execution_mode` / `allow_network` / `billable_kinds` を、
>   `preferred_request_kind()` が lane を持つので、offline の 3 分岐すべてが賄える
> - offline seam は `KIO_TEST_LOCAL_EMBED`。CI は GPU を持たないので、
>   **実モデル無しで offline の意味論を検証する唯一の手段**
>
> 🔴 **consent gate も ledger も「2 箇所」だった** (Chunk A のゲートと同じ構図):
>
> | 分岐 | 見つけた場所 |
> |---|---|
> | consent | 検索の precheck **と** `compute_query_embedding_page1` の PC6 再読 |
> | ledger | query 側の `device_claim` **と** index 側の `reserve_or_reuse_task_charge` |
>
> さらに `scope_embedding_state` の期待値が **Gemini profile 固定**で、
> offline で index した scope の全ベクトルを incompatible と誤判定していた
> (`adopted_embedding_profile_summary` → `active_embedding_profile_summary`)。
> index は正しく、期待値だけが古かった。
>
> **その修正で 1 度踏んだ罠**: 期待値を `declared_embedding_profile` から取ると
> `IncompatibleProfile` seam が壊れる。この seam は「declared が adapter の実出力と
> 食い違う」ことで stale/foreign index を模しているので、declared を期待値にすると
> **seam が自分自身と一致してしまい compatible と報告する**。
> 正しい参照は **adapter 自身の `profile()`** — 「今書くベクトルがどの空間に落ちるか」
> の正直な答え。`declared_embedding_profile` は lock 向けの view であって
> compat 判定の基準ではない。
>
> **もう 1 つ踏んだ罠**: 免除条件を「オンラインでない」と書くと
> **adapter 未設定の場合まで免除してしまう**。`--offline` は
> [05 §1.1](../docs/05-runtime.md) PC1 line (a) で**最優先・無条件**であり
> 「ユーザーの意思決定であって探査結果ではない」ため、未設定時は従来どおり
> `fallback_reason="offline"` を返さなければならない
> (`pc1_pc5_offline_flag_forces_text_fallback_with_no_error_code` が検出)。
> 正しい述語は「**active かつ offline_api**」。
> `is_some_and(|e| !is_online(e))` と `!is_some_and(is_online)` の違いがこれ。

課金 0 の配線は既存 ([main.rs:21035](../crates/kio-cli/src/main.rs))。
受入検査 (1)〜(5) ([07 §5.3](../docs/07-adapter-spec.md)) は core 側を再利用する。

profile 値:

```json
{
  "adapter_kind": "embedding",
  "adapter_role": "multimodal",
  "dimensions": 768,
  "distance": "cosine",
  "input_construction": "chunk_filename_context_v1",
  "modality": "multimodal",
  "model_or_tool_family": "qwen3-vl-embedding",
  "model_version_pin": "sha256:<weights digest>",
  "prompt_template_id": "kio-qwen3vl-embed-v1",
  "prompt_template_hash": "sha256:<chat template + instruction>",
  "runtime_kind": "local",
  "spec_version": 1
}
```

### 作業項目

#### U1 role ベース dispatch へのリファクタ [P0]
[`active_adopted_embedding_execution`](../crates/kio-adapter/src/catalog.rs) が Gemini 形状
(`AdoptedEmbeddingExecution` enum + `GEMINI_API_KEY`) に固まっている。**Stage 2 の最大の作業量**。

#### U2 vLLM `messages` wire の実装 [P0] ✅ 2026-07-28 実装
```http
POST http://127.0.0.1:8000/v1/embeddings
{
  "model": "Qwen/Qwen3-VL-Embedding-2B",
  "encoding_format": "float",
  "messages": [{"role": "user", "content": [
    {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    {"type": "text",      "text": "..."}
  ]}]
}
```
起動: `vllm serve Qwen/Qwen3-VL-Embedding-2B --runner pooling`
(V4 の実測どおり `--chat-template` は不要 — モデル同梱の `chat_template.jinja` が使われる)。
D4 によりテキストのみでも同形式を使う。
(この base64 は **Adapter → ローカルサーバ間の wire** であり、§4.4 が禁じる
「検索レスポンスに base64 を埋める」こととは別物である。)

> **実装時の裁定と所見 (2026-07-28)**
>
> - **`system` メッセージは送らない。** V4 の裁定どおり。`user` 1 通のみ。
>   これは実装への拘束であり、07 §5.3 に明記した上でテストで固定してある
>   (送る実装に変えるなら `prompt_template_hash` の再計算を伴う)
> - **テキストも画像も `content` は配列形式**にした。モデルの template は
>   単一 text について文字列形と配列形を同一に描画するのでトークンは変わらず、
>   **V4 が実測した描画の経路が 1 本になる**。2 本あって「一致するはず」と
>   言うより強い
> - **MRL は切り詰め後に再正規化する。** V4 が native 2048 で L2 ≈ 1.0 を
>   実測しているので、先頭 768 の prefix は**短い** — しかも短さの度合いは
>   ベクトルごとに違う。正規化せずに保存すると cosine が「その文の質量が
>   768 より先にどれだけ乗っていたか」に依存し、それは文の性質ではない
> - **切り詰めは 2048 と等値比較しない。** 同族のより広いモデルを切り詰めるのも
>   MRL である。禁じるべきは*広げる*ことなので、768 未満の応答だけを拒否する
> - **宣言は `Real` を選ぶ。** `KIO_TEST_LOCAL_EMBED=mock` を経由しない限り
>   mock は選ばれない。宣言が黙って mock ベクトルを実コーパスへ書く経路は無い
> - **mock と real は別 profile hash**。同一空間を名乗らせない (03 §7)
> - `tool_profile_hash` = `sha256:f9f610bb…` が V4 の `v4-profile.json` と
>   **一致することをテストで凍結した**。Python 移植と Rust 実装が独立に同じ値を
>   出しており、どちらかがずれたら落ちる
>
> **未実装**: D7 の `[adapter.policy.offline_api]` timeout 上書きは config 形の
> 確定のみで、実装は入っていない。現状は共通の既定 (実効 30 秒) で、
> chunk 1 件の embedding には十分。Stage 3 のローカル OCR では効いてくる。

> **実 vLLM との smoke test 済み (2026-07-28・GPU 実機・commit `2e7a2ba`)**
>
> U2 の Rust クライアントはそれまで fake client とスタブソケットしか相手に
> していなかった。実サーバ (vLLM 0.26.0 / RTX 4070 / WSL2) に対して
> `kio init` → `index --approve` → `search --mode vector` を通し、**wire の変更は
> 不要だった**。
>
> - `--mode vector` が **4 件**返し、`fallback: false` / `resolved_mode: "vector"`。
>   embedding 失敗時の静かな text 縮退 (`Err(_) => Ok(None)`) には入っていない
> - **保存されたベクトルを参照計算と数値比較した** — 同じ入力を生 HTTP で投げ、
>   768 へ切り詰めて再正規化した結果との cosine が **0.999999994** (最大絶対差
>   7e-9 = f32 の丸め)。`messages` 形・`chunk_filename_context_v1` の入力構築・
>   MRL 切り詰めの 3 つが揃って正しいことの実測であって、
>   「エラーが出なかった」ではない
> - `tool-lock.json` の embedding entry は `kind: "offline_api"` /
>   `profile_hash: sha256:f9f610bb…439a` で V4 と一致
> - **D9 の実証**: `approvals[]` に embedding の行は無い (在るのは markdownize の
>   `mistral_ocr_markdownize` = `online_api` 1 行のみ)。`--offline --mode vector`
>   も同じ 4 件を返す
> - cost ledger に embedding の行は増えない (在る 2 行は `deterministic_baseline`
>   = markdownize 側、いずれも `usd 0.0`)
>
> **併せて 07 §3 の設定例の誤りを修正した** — `[embedding]` 直下に `tool_id` を
> 書く形が例示されていたが、flat 形は `tool_id` を受け付けず
> `KIO-E-CONFIG-SCHEMA-001` で弾かれる (§6 の「flat 形は `kind` で解決する」と
> 矛盾していた)。テーブル形 `[embedding.qwen3_vl_embedding_local]` へ直した。

#### U3 🔴 `chunk_vec` は chunk 専用 — 画像用 vec0 テーブルが無い [P0・spec 改訂]
[04 §4.3](../docs/04-pipeline.md) の DDL:
```sql
CREATE VIRTUAL TABLE chunk_vec USING vec0(
  chunk_id TEXT PRIMARY KEY,
  embedding float[768] distance_metric=cosine
);
```
`embeddings` テーブルは `target_type: chunk | image | node | query_cache` を持つが、
**KNN 検索できる vec0 テーブルは chunk しか無い**。さらに同節は
「結合対象は `target_type='chunk'` の行のみ」と明記している。

→ `image_vec` を新設する (`vec0(image_id TEXT PRIMARY KEY, embedding float[768] ...)`)。
**[04 §4.3](../docs/04-pipeline.md) の schema 正本の改訂が必要**。
`kio repair rebuild-db` の再構築順 (`objects/` → `embeddings` → `chunk_vec`) にも
`image_vec` を追加する。

#### U4 画像ヒットの結果行 — `payload_uri` と `evidence_pointer` の分離 [P0] ✅ 2026-07-26 実装
§4.1 の裁定を実装する。

- `result_type: "image"`
- `payload_uri` = `kio://<scope_id>/object/image/<hash>` (Agent が `kio open` する実体)
- `evidence_pointer` = **その画像を参照している chunk** の pointer
  (commit / tree / raw_hash / chunk_hash / path_at_commit / span を持ち、
  time-travel と `evidence verify` が成立する)

参照元 chunk の特定は Stage 1.5 の W1 と**同じ抽出器を逆引きに使う**
(URI → その URI を本文に含む chunk)。

**選択規則は Stage 0 で確定済み (V6)**: 複数 chunk が同じ画像を参照する場合は
`chunk_hash` の UTF-8 byte order 最小を選ぶ。逆引きの探索範囲は検索対象 commit に限る
([05 §1.7](../docs/05-runtime.md))。

[08](../docs/08-evidence-pointer-spec.md) の schema 改訂は不要 — pointer 自体は chunk のもので
既存の `kio open` / restore / `evidence verify` 経路がそのまま動く。ただし §7.1 の古い
検索結果例は Stage 0 で正本への参照に置き換えた (`preview` field が実在しなかった)。

#### U5 ランキング — 問題 A (RRF の構造的不利) の解消 [P0] ✅ 2026-07-26 実装
§4.2 問題 A の対処案 (a) を実装する: 画像の text lane 表現 (参照元 chunk 本文 / alt / caption) を
与え、画像も 2 lane から reciprocal rank を得られるようにする。

> **実装時の裁定 (2026-07-26)**: 「**FTS に載せる**」という当初の書き方は採らず、
> **参照元 chunk の text rank を継承させた**。結果として得られる順位は (a) と同一だが、
> FTS へ重複 document を入れる方は **BM25 のコーパス統計を壊す** —
> 画像 1 件につき `N` が増え、その本文に含まれる全 term の `df` が増え、`avgdl` がずれるため、
> **ある文書に図を足すと無関係な text ヒットの順位が動く**。これは
> [05 §1.8](../docs/05-runtime.md) が replica を導入して除去した欠陥そのものであり、
> 一段下の層で再導入することになる。継承なら (a) の言う「画像の text lane 表現は
> 参照元 chunk 本文である」を満たしたままコーパスに触れない。
>
> alt/caption を採らなかった理由も併記する: OCR が書く alt は `img-0` のような
> 機械生成ラベルで、検索語と一致しない ([07 §5.2](../docs/07-adapter-spec.md) の置換は
> alt を保存するだけで内容を保証しない)。
>
> 継承は 2 箇所にある。per-scope は text rank 表への挿入 (参照元 chunk の直後 —
> `fuse_rrf` の `take(candidate_depth)` 窓から落ちないため)、replica 経路は
> `apply_global_ranks` が text lane を **参照元 chunk_hash で引く**ことで同じ規則になる。
> vector lane だけは行自身の identity で引く (画像は自分の vector で順位が付くため)。

#### U6 ランキング — 問題 B (`max_per_raw_hash` / MMR) の実装 [P0] ✅ 2026-07-26 実装
§4.2 問題 B。**裁定は Stage 0 で確定済み** ([05 §1.4](../docs/05-runtime.md) へ反映)。
本項に残るのは実装のみ。

> **実装時の所見 (2026-07-26)**: 「型で分岐させない」という Stage 0 の裁定が正しかったことが
> 実装で裏付けられた。**`diversify_merged` / `mmr.rs` は 1 行も変えていない。**
> image 行が `meta` に参照元 chunk のものを持ち `embedding` に自分の vector を持つだけで、
> `max_per_raw_hash` の計数先も MMR の無効化条件も pairwise cosine も自動的に規約どおりになる。
> MMR の候補 id は既に `"{index}\0{chunk_hash}"` の合成キーなので、
> image 行と参照元 chunk が同じ `chunk_hash` を持っても衝突しない。
>
> 一方 **`chunk_hash` を行の identity として使っていた層は分離が必要だった** —
> vector lane のキー、および最終ソートの tie-break。ここだけ `ResultPayload::row_id()`
> (chunk なら chunk_hash、image なら image_hash) を使う。

- **`max_per_raw_hash` は同枠**。画像専用の quota も lane も作らない。cap の目的
  (同一原文が上位を独占しない) は結果が chunk か image かで変わらないため。
  カウント先は当該 result 行の `evidence_pointer.raw_hash` (= V6 が選んだ chunk のもの) —
  **1 result 行 = 1 evidence_pointer = 1 raw_hash** で一貫させる
- **MMR 無効化条件は型に依らない**。「候補が 1 件でも embedding を欠けば無効」を
  chunk・image に等しく適用する。**「image は構造上必ず embedding を持つ」という論法は
  採らなかった** — 画像埋め込みも chunk と同じ Batch / budget 機構に載るため、同じく
  部分 enrichment 状態を取り得る
- **MMR tie-break key `(scope_id, chunk_hash)` はそのまま使える** (V6 により image 行も
  `chunk_hash` を持つ)。新キーは導入しない
- **pairwise similarity に特別扱いは不要** — 単一マルチモーダル空間の強制
  ([03 §7](../docs/03-data-model.md)) により image と chunk の vector は定義上 cosine 比較可能

#### U7 image/text 同一空間の契約検査 [P0]
§2 の「テキストは一致・画像だけ乖離」は KIO の互換ゲートで検知できない。
**参照実装との数値一致を採用条件とする**受け入れ検査を持つ。
vLLM 経路 (公式サポート) では優先度が下がるが、llama.cpp 経路では必須。

#### U8 `image_object_hashes` の writer / reader [P1]
現在 3 構造体に宣言のみ ([07 §5.1](../docs/07-adapter-spec.md) が明記)。
`PrepareResponse` / `PrepareStageOutput` を経由して埋め込み対象の画像集合を運ぶ。

#### U9 画像の重複排除 group [P1]
現在の group は chunk の `text_hash` ベース。画像は `image_hash` ベースの group が要る。
[07 §5.3](../docs/07-adapter-spec.md) の「task 単位 = job」の digest 計算にも影響する。

#### U10 purge / rebuild の列挙対象に image ベクトルを含める [P1]
[05 §3.5](../docs/05-runtime.md) の purge 列挙、`kio repair rebuild-db`、
`verify-objects` の対象に `image_vec` / `target_type='image'` 行を追加する。

#### U11 `EmbeddingModality::Image` は使わない [P1]
[04 §4.3](../docs/04-pipeline.md) の DDL コメントが `modality` を **`"multimodal"` のみ**と
規定している。画像行も `modality='multimodal'` / `target_type='image'` で書く。
`EmbeddingModality::Image` は dead variant として残すか削除する。

---

## 9. Stage 3 — ローカル Markdownize Adapter

新規モジュール `crates/kio-adapter/src/local_ocr_markdownize.rs`。
`/v1/chat/completions` に画像を data URI で渡す標準形 (vLLM)。

- 1 page = 1 unit = 1 呼出
- [07 §8.1](../docs/07-adapter-spec.md) の 6 規約を実装義務として負う
- **`sampling.temperature = 0` + `seed` 固定** — [07 §9](../docs/07-adapter-spec.md) の
  first-instance-wins によりブレが永久に凍結されるため
- `prompt_template_id` / `prompt_template_hash` を profile に固定 (D3 と同じ理由)
- bbox: PaddleOCR-VL は layout 座標、Sarashina は `<bbox>[(x1,y1),(x2,y2)]</bbox>` タグ。
  既存の [bbox_annotation.rs](../crates/kio-adapter/src/bbox_annotation.rs) と同型の後処理へ写像する
- **画像抽出は Stage 1.5 / 2 の前提**: 抽出画像を `objects/image/` へ persist し、
  normalized Markdown へ `kio://` URI を埋める既存契約
  ([mistral_ocr.rs:1425,1600](../crates/kio-adapter/src/mistral_ocr.rs)) を
  ローカル Adapter も満たすこと。これを欠くと `related_images[]` が常に空になる
- 採用ゲート: [experiments/ocr-verification](../experiments/ocr-verification) の fixture で
  Mistral OCR ベースラインと突き合わせる

---

## 10. 段階 C (将来) — page-as-image

ページ全体を画像として索引する ColPali / ColQwen 系の設計。
企業 PDF の約 80% が表・チャート・複雑レイアウトを含み、OCR ベース RAG は劣化した入力から
始まるという指摘が動機。

**現状 KIO には前提が無い**: Prepare は page image をレンダリングしない
([07 §2.1](../docs/07-adapter-spec.md) — 同梱 Prepare は PDF text layer 抽出のみ)。
ただし [03 §5.1](../docs/03-data-model.md) の `render_params`
(`{renderer_name, renderer_version, dpi, color_space, output_format}`) は
**レンダリングする Prepare Adapter を見越した groundwork として既に profile field に存在する**。

Stage 2 完了後に、段階 A/B の実測をもって着手可否を判断する。

---

## 11. 未確定 / 要検証

| # | 項目 | 影響 |
|---|---|---|
| V1 | Sarashina2.2-OCR の vLLM 対応 (モデルカードは transformers + `trust_remote_code` のみ) | 不可なら Stage 3 の第二 profile は `cmd` dispatcher が必要になりコストが跳ねる (裁定 5 により変更は許容) |
| V2 | PaddleOCR-VL の bbox 出力形式の詳細 (Markdown 内タグか別 JSON か) | Stage 3 の bbox 写像の実装形 |
| V3 | ✅ **2026-08-01 確定** — Qwen3-VL-Embedding の MRL 768 次元での劣化幅 (V3a 2026-07-28 / V3b 2026-08-01) | **768 で確定。** 24 問 recall@10 は 2048 が 0.5417、768 が 0.5833 で切り詰めの代償が出なかった。`dimensions` / `tool_profile_hash` の**暫定扱いを解除**し、恒久コーパスの埋め込み禁止も解けた。下記 |
| V4 | ✅ **2026-07-27 確定** — vLLM の chat template 既定値と推奨 instruction の実物 | D3 の `prompt_template_hash` の中身。下記 |
| V5 | llama.cpp #18665 / #19516 の進捗 | マージされれば Mac が D5 により再埋め込みなしで合流できる |
| V7 | chunk 境界による URI 分断の発生頻度 | W3。dogfood corpus で計測 |
| V8 | ✅ **2026-08-01 (a) 実測** — asymmetric instruction (query 側にのみ instruct prefix) を採れるか | D3 の帰結として**構造的に採れない**。**ただし採れたとしても得ではなかった** (recall 両幅とも悪化) ので (b) の仕様改訂は実測上の動機を持たない。下記 |
| V9 | tokenizer / vision preprocessor config が `model_version_pin` の対象外 | 同一 profile を名乗ったまま空間が割れうる。下記 |

### V3 は 2 段構えで、**両方とも済んだ** (V3a 2026-07-28 / V3b 2026-08-01・GPU 実機)

測定の全文と成果物は [eval/v3/results/](../eval/v3/results/README.md)。
RTX 4070 / vLLM 0.26.0 / `Qwen/Qwen3-VL-Embedding-2B` rev `9f2f7e71`。

**V3a (近傍構造)** — 切り詰めが近傍をどれだけ入れ替えるか。GPU だけで回る。

| 測定 | 値 |
|---|---:|
| 近傍一致率 mean (k=10) | **0.8037** |
| 近傍一致率 min | 0.1000 |
| top-1 一致率 | 0.7500 |
| 観測次元 (native) | 2048 |

判断表の `< 0.85` に落ちたので **V3b 送り**。曖昧帯 (0.85–0.95) も V3b 送りなので、
回避できたのは `≥ 0.95` の場合だけだった。

> **この 0.8037 は下振れした推定である。** 主計器は集合の重なりを数えるので、僅差の
> 入れ替わりと大差の入れ替わりを区別できない。独立実装の tie 診断によれば native 側の
> 上位 10 位と 11 位のギャップは中央値 **0.00394**、768 が失った類似度は中央値
> **0.00445** で同じ桁である (境界ギャップ < 0.01 の passage が 136 本中 110 本)。
> **集合は入れ替わるが、入れ替わった先は元とほぼ同じ近さにある。** コーパスが V3a では
> 同一プロジェクトの計画文書に偏っていたことが効いており、実際の Kio アーカイブは
> より異質なので overlap は上がる方向に動く。

**V3b (24 問 recall)** — ✅ **2026-08-01 実施。これが V3 の結論を出した。**
`eval/fixtures/normalized-corpus` の 1013 passages (persona 20 本すべて) に対し、
`answerable` 24/24 で測れた。手順は [eval/v3/V3B-PROMPT.md](../eval/v3/V3B-PROMPT.md)。

| 幅 | recall@10 |
|---|---:|
| native 2048 | 0.5417 (13/24) |
| **MRL 768** | **0.5833 (14/24)** |

**切り詰めの代償は測定に現れなかった** (差 +0.0417 = 1 問、n=24 なのでノイズ)。

> **この 0.5417 を、下の品質計器の表にある `run_baseline.py` の 0.9167 と比べないこと。**
> 同じ 24 問 fixture を使うが**計器が違う**。`run_baseline.py` は実際の `kio` バイナリを
> `kio --json search <query> --all-scopes` で回すので、chunk 分割・hybrid・集約まで
> 通った Kio の実力である。`v3_mrl.py` は Kio を一切通さず、**1 ファイル = 1 passage**
> (分割なし・先頭 4000 文字) の素の cosine しか見ない。
>
> 粗い計器をあえて使っているのは、**V3 が比べるのは同じベクトルの 2 つの幅**であり、
> 分割規則も入力構築も instruction も両側で相殺されるからである
> (`v3_mrl.py` の docstring)。**絶対値は Kio の検索品質ではなく、差だけが意味を持つ。**
> 0.5417 は 0.9167 からの劣化ではない。
正しい読みは「768 が recall を落とすという証拠は出なかった」であり、
それが移行しない理由として十分である — 2048 は `chunk_vec` の DDL 改訂と
**全再埋め込み**を要するのに、実測 recall はより低い。

V3a の予測 (「失った類似度がこの水準なら recall@10 の差は小さく出るはず」) は当たった。

> **2 回の実行は完全一致しなかった。** recall は両幅とも一致し、外した query の集合まで
> 同一だったが、**近傍一致率だけ 1013 passage 中 1 本ぶんずれた** (top-1 で 0.000987)。
> vLLM のバッチ構成に依存する浮動小数の揺れが同点を割ったものと見られる。
> 近傍が中央値 0.004 しか離れていない (V3a の tie 診断) こととも整合する。
> **判断に使う recall は再現した**が、近傍一致率を 3 桁目まで引用しないこと。

**→ `dimensions` は 768 で確定。`tool_profile_hash` = `sha256:f9f610bb…439a` の
暫定扱いを解除し、恒久コーパスの埋め込み禁止も解けた。**

### V4 は 2026-07-27 に確定 (GPU 実機)

測定の全文と成果物は [eval/v4/results/](../eval/v4/results/README.md)。
RTX 4070 / vLLM 0.26.0 / `Qwen/Qwen3-VL-Embedding-2B` rev `9f2f7e71`。

| 測定 | 値 | 影響 |
|---|---:|---|
| `cos(input[] 経由, messages 経由)` | 0.4740 | **D4 は正しい。** 参考: `cos(無関係な 2 文)` = 0.5966 — **wire 形式を変えるほうが内容を丸ごと差し替えるより遠い** |
| `cos(instruction 有, 無)` 非既定文面 | 0.7989 | **D3 の instruction 側も正しい**。probe 既定での 1.0 は下記のトートロジー |
| `cos(同一入力 2 回)` | 1.0000 | first-instance-wins が成立する |
| 観測次元 | 2048 (native) | **V3 の入口**。profile の 768 は MRL 切り詰め側 |

**確定した identity** (07 §5.3 へ反映済み):

```
model_version_pin    sha256:c73fa9ca…09c1   (単一 model.safetensors)
prompt_template_hash sha256:7b7f4722…9e8b   (instruction = "")
tool_profile_hash    sha256:f9f610bb…439a   ← dimensions が 768 のままの前提
```

**`instruction` は `""` を採った。** probe 既定の `cos = 1.0` は、モデルの chat template が
system message 不在時に注入する `default_system_message` と probe の
`DEFAULT_INSTRUCTION` が同一文字列だったことによる artifact であって、モデルの性質ではない。
その文字列は既に `chat_template` (T) の一部として hash 入力に入っており、Kio は
system message を送らないので、供給する instruction は無い。

**`tool_profile_hash` は V3 決着まで暫定。** `dimensions` は hash 入力であり、
実測 native は 2048。定数は `fts.rs::CHUNK_VEC_DIMENSIONS` (vec0 の DDL 幅) と
`local_embedding.rs::LOCAL_EMBEDDING_DIMENSIONS` の 2 本に閉じている。
**V3 決着前に恒久コーパスを埋め込まないこと。**

**手順上の罠を 1 つ潰した。** `/tokenize` は既定で `add_generation_prompt=True` を
適用するため、`v4-probe.json` の `rendered_prompt` (40 token) は embedding 経路が
実際に使った描画 (37 token) ではない。これを正にすると**存在しない assistant turn を
含む template を恒久凍結する**。今回は token id 一致まで取って確定した。

**これで U2 (実 vLLM の `messages` 配線) が unblock された。**

### V8 — asymmetric instruction は構造的に採れない疑い [新規・2026-07-27]

V4 の 0.7989 は instruction の文面がベクトルを大きく動かすことを示している。
Qwen3-Embedding 系は **query 側にのみ instruct prefix を付ける非対称運用**が標準だが、
Kio ではこれが**仕様の帰結として採れない**:

機構は互換ゲートではなく、**identity に置き場所が無い**ことである。Kio は embedding
adapter を 1 つしか持たず、query も `EmbeddingInputType::Query` として
**chunk / image と同じ `run_embedding_adapter`** を通る
([main.rs](../crates/kio-cli/src/main.rs) の 15167 / 16211 / 17508 が同一関数)。
したがって query は index と同じ template・同じ instruction で描画される。別文面にするには adapter が 2 通りの描画を持つ必要があるが、
`prompt_template_hash` は **(T, I) を 1 組だけ畳む単一フィールド**であり、2 つ目の描画を
記録する欄が無い。[03 §7](../docs/03-data-model.md) の横断ゲートが比較するのもその
単一の `profile_hash` なので、2 描画を導入するなら identity の形そのものを変えることになる。

バグではなく D3 の設計帰結だが、**検索品質を落としている可能性**があり、凍結前に
書き留める価値がある。着手順は (a) まず対称運用のコストを測る — V3 と同じ 24 問計器が使える。
(b) 実際に効くと分かってから、query 用 profile を分ける仕様改訂を検討する。
(b) はゲートの意味そのものを変える大改訂なので、(a) の実測なしに入らないこと。

> **(a) の実測 (2026-08-01・V3b と同じセッション)** — 全文は
> [eval/v3/results/](../eval/v3/results/README.md)。`v3_mrl.py` に
> `--query-instruction` を足し、passage は素のまま query にだけ
> `Instruct: …\nQuery: ` を前置して同じ 24 問を回した。
>
> | 条件 | recall@10 (2048) | recall@10 (768) |
> |---|---:|---:|
> | 対称 (現行) | 0.5417 | **0.5833** |
> | 非対称 (query 側 instruct) | 0.4583 | 0.5417 |
>
> **非対称は両幅とも悪化した。** したがって (b) の仕様改訂へは進まない —
> **構造的に採れない運用が、採れたとしても得ではなかった**ので、
> ゲートの意味を変える代償を払う理由が無い。
>
> n=24 なので 1〜2 問の差はノイズである。主張は「非対称が有利だという証拠は
> 出なかった」までで、「非対称は有害である」ではない。他モデル・他コーパスで
> 事情が変われば測り直す価値は残る。**V8 はここで「書き留めて閉じる」。**

### V9 — pin されていない決定要因がある [新規・2026-07-27]

ローカル multimodal embedding のトークン列 / パッチ列を決めるものは 4 つあるが、
**pin されているのは 2 つだけ**である:

| 決定要因 | pin | 経路 |
|---|---|---|
| 重み | ✅ | `model_version_pin` |
| chat template | ✅ | `prompt_template_hash` |
| tokenizer の vocab / merges | ❌ | どこにも入らない |
| vision preprocessor の設定 (`min_pixels` / `max_pixels` / patch / 正規化) | ❌ | 同上 |

後者 2 つは同じ HF snapshot に同居するので実務上は重みと一緒に動くが、
03 §5.1 が pin するのは **snapshot revision ではなく重みファイル**なので、
snapshot の局所改変を検知できない。特に vision preprocessor は画像ベクトルを実質的に
変えるため、[07 §5.3](../docs/07-adapter-spec.md) 冒頭が塞ごうとしている
「同じ profile_hash を名乗る 2 空間」そのものになる。

解法候補は (a) 集約に該当 config を含める、(b) snapshot revision を併記する、の 2 つ。
どのファイルが実際に効くかはモデル族ごとに違うので、Stage 3 の第二 profile を選ぶ前に
調べる。**優先度は低い** — 発生には snapshot の手動改変が要る。

**V6 は 2026-07-26 に確定** ([05 §1.7](../docs/05-runtime.md) へ反映済み) —
1 画像を複数 chunk が参照する場合、`evidence_pointer` は **`chunk_hash` の
UTF-8 byte order 最小**の chunk を指す。逆引きの探索範囲は検索対象 commit に限る。

> 検討した代替案「最小 rowid」は**不採用**。`index/sqlite.db` は
> [04 §4.3](../docs/04-pipeline.md) のとおり `objects/` から再構築可能な **cache** であり、
> rowid は `kio repair rebuild-db` をまたいで安定しない。Agent が保存し後から
> `kio evidence verify` する**永続的な引用**の選択根拠に cache の再構築順を使うと、
> rebuild 後に同じ検索が別 chunk を引用し得る。`chunk_hash` は content-addressed
> identity 由来で rebuild に不変であり、かつ §1.3 / §1.4 / §1.7 で既に横断使用されている
> tie-break idiom なので新概念がゼロ。

### 品質計器 — V3 の前提 (2026-07-27 調査)

**V3 は「劣化幅を測る」項目なので、測れる計器が要る。合成 eval では測れない。**

| 計器 | 実測 | 使えるか |
|---|---|---|
| `eval/run_eval.py` (合成・CI 常時) | M3-1/2/3 = 1.0 / 1.0 / 1.0 (目標 0.8) | ❌ 天井。劣化を検出できない |
| `eval/run_baseline.py` (fixture-b 24 問) | kio 0.9167、hard3 は 6/8 | ✅ 余地がある |

その fixture は失われていなかった。当時は改名前の `kio-` 名で残っていた
(**2026-07-28 に `kio-` へ改名済み**)。所在は 2026-07-28 に実測し直した:

| 場所 | golden 24 問 | `.kio` | 中身 |
|---|---:|---:|---|
| `~/kio-baseline-corpus` (14 MB) | **24/24** | 0 | **原本**。1,015 ファイル |
| `~/kio-dogfood/corpus-v1/corpus` (1.9 GB) | **24/24** | **428** | **index 済み**。下記 |
| `/private/tmp/kio-fixture-run-stale-20260724` (1.3 GB) | 0/24 | **0** | 2026-07-24 の残骸。使えない |

qhard の 24 ファイルは `/tmp` にしか無かったため `~/kio-baseline-corpus-qhard` へ
保全済み (バイト一致確認済み)。

> **訂正 (2026-07-28)**: 本節は以前 `/private/tmp/kio-fixture-run` を
> 「index 済み store」と書いていたが**誤り**だった。実際には `.kio` が 1 つも無く
> golden query の正解も 0/24 で、index 済みの実体は `~/kio-dogfood/corpus-v1/corpus`
> にある (`scope-registry.sqlite` の 433 scope もそちらを指している)。
>
> **したがって OCR の実費は再度払う必要がない。** 支払い済みの成果物は生きている:
>
> - `objects/normalized/*.md` (markdownize 出力) **1,223 ファイル / 5.0 MB**
> - chunks **3,711** / embeddings **3,537**
>
> V3b はこの正規化済み Markdown を `--corpus` に渡せば成立する。5.0 MB のテキストなので
> **commit して恒久化できる規模**であり、そうすれば以後の再測定は無料になる。

`register_fixture.py` は**削除されたのではなく、一度も commit されていなかった**
(`git log --all --diff-filter=D` が何も返さない)。生き残った fixture から仕様を採取して
再実装した (`eval/register_fixture.py`) — scope の規則は「`<persona>/home` 配下で
ファイルを直接含むディレクトリ」で、p01〜p20 すべて 20 個ちょうど、
`scope-registry.sqlite` と当時の `registration-report.json` に一致する。

24 問の正解担体は `.md` が 4・`.pdf`/`.docx`/`.pptx`/`.png`/`.jpeg` が 20 で、
後者は全て OCR lane を通る。つまり **`--offline` 構築では上限 4/24 = 0.167** に
しかならず、0.8 のゲートに対して品質を何も測らない。実測には `--online` が要る。

**2026-07-27 に実行し、基準値をクラス単位まで完全再現した。**

| | 2026-07-24b (凍結) | 2026-07-27 (再構築) |
|---|---:|---:|
| kio recall@10 | 0.916667 | **0.916667** |
| hard1 / hard2 / hard3 | 8 / 8 / 6 | **8 / 8 / 6** |
| ゲート (kio>=0.8 かつ各差>=0.3) | pass | **pass** |

構築は 400 scope (20 persona x 20) を失敗ゼロ、実費 **$1.2058** / ledger 1,688 行
(記録の $1.0747 / 1,112 行と同水準)。chunk 1,528 に対し embedding も 1,528 で
全 chunk 埋め込み済み。

**Batch の回収はカスケードする。** `index` は OCR/embedding を Batch へ渡して戻る
だけなので `batch resume` が要るが、OCR が完了すると正規化本文→chunk→embedding
タスクが新たに湧くため pending は単調減少しない。今回は 送信 1 パス + 回収 4 パス
で収束した。scope ごとに待つと 400 scope が直列になるので、
`--drain-rounds 0` で全件を先に送ってから回収する順が要る。

**これで V3 (MRL 768 vs native 2048) が測定可能になった。** 合成 eval は 1.0 で
天井なので、劣化幅を出せるのはこの計器だけである。

---

## 12. 作業順

```
Stage 0 (D1-D10 / V6 / U6)   ✅ 2026-07-26 完了 — spec 確定 (コード変更なし)
                     docs/07 §3 §5.3 §7 / docs/03 §5.1 / docs/04 §4.3
                     docs/05 §1.1 §1.4 §1.7 §3.5 §5 / docs/06 §8 §11
                     docs/08 §7.1 / docs/10 §7.5 §12.1
   ├─────────────────────────────┐
   ↓                             ↓
Stage 1                       Stage 1.5 (段階 A・W1-W4)
tool_lock.rs ゲート解放        related_images[] — 画像埋め込み不要・並行可
   ↓                             ↓
   └─────────────┬───────────────┘
                 ↓
Stage 2 (段階 B・U1-U11)  local_embedding.rs + 画像埋め込み + ランキング問題 A/B
   ├ U1  ✅ role dispatch + mock offline adapter (Chunk B)
   ├ U3  ✅ image_vec + 書き込み / rebuild / purge (C1)
   ├ U4/V6 ✅ result_type / payload_uri / 参照元 chunk の逆引き (C2)
   ├ U5  ✅ 問題 A — 参照元 chunk の text rank 継承 (C2)
   ├ U6  ✅ 問題 B — 同枠 quota / 型非依存 MMR (C2、既存コード無改修)
   ├ U2  ✅ 実 vLLM の messages 配線 + MRL 再正規化 (2026-07-28)
   ├ U7  ⏳ image/text 同一空間の数値一致検査 — U2 の後
   └ U8  — image_object_hashes の writer — C1 が chunk 本文の逆引きで代替。
          埋め込み対象の列挙としては不要になった (writer なき宣言は残る)
                 ↓
Stage 3           local_ocr_markdownize.rs (PaddleOCR-VL 既定 / Sarashina 任意)
                 ↓
段階 C (将来)      page-as-image — Stage 2 の実測をもって判断
```

**Stage 0 で前倒し確定した設計裁定** (spec 改訂を伴うもの):
U3 → **D10** (`image_vec` schema + purge 列挙)、U4 (`payload_uri` / `evidence_pointer` 分離)、
V6 (参照元 chunk の選択規則)、U6 (`max_per_raw_hash` / MMR の扱い)、
D8 (レスポンス契約の field 追加)。**D9 (consent gate 免除) は Stage 0 実施時に新規発見**。
いずれも実装は後続 Stage が担う。

**Stage 1.5 は Stage 1 と独立**である (ローカル Adapter に依存しない)。
[Index Light, Reason Deep](https://arxiv.org/abs/2602.14162) の実測が示すとおり、
画像埋め込みを待たずに LLM 消費者への価値を先に取れる。
