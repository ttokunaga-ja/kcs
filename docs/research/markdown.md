# Markdownize Adapter 選定 Research Notes (Mistral OCR vs Gemini)

> Research note
> Status: integrated
> Canonical refs: [../07-adapter-spec.md](../07-adapter-spec.md), [../04-pipeline.md](../04-pipeline.md), [../03-data-model.md](../03-data-model.md)
> Scope: 非 text-native ファイル (PDF/DOCX/PPTX/画像) の Markdownize 第一候補を Mistral OCR 系にする調査

---

# 結論

```text
標準 Markdownize Adapter (非 text-native): Mistral OCR latest (2026-07 時点の実体は OCR 4)
補助・fallback:                            Gemini (品質検証 / 図表解釈 / 要約), Docling, PyMuPDF / LibreOffice / mutool
```

Gemini は文書理解・要約・QA に強いが「理解」の API。KCS が必要とするのは**再利用可能な抽出パイプライン** (Markdown + 画像 + 表 + bbox + confidence を構造化して返す文書処理 API) であり、Mistral OCR の出力形式が KCS の内部形式に直接対応する。

# 根拠 (Mistral OCR の出力)

- 出力 JSON は `pages[].markdown / images / tables / hyperlinks / dimensions / confidence_scores / blocks` を返す。画像・表は Markdown 内 placeholder (`![img-0.jpeg](...)`) + 実体フィールドの対応付け ([Mistral Docs][2])
- OCR 4 (2026-06-23 発表): bounding boxes / block classification / inline confidence / 170 言語 / **single-container self-hosting**。API $4 / 1,000 pages、Batch $2 / 1,000 pages ([Mistral AI][1])
- OCR 3: $2 / 1,000 pages (Batch $1)。HTML table reconstruction 対応 ([Mistral AI][4])
- Gemini: native vision で最大 1,000 ページの文書理解・構造化出力は可能だが、画像抽出 + placeholder 置換 + bbox の抽出パイプラインとしては間接的 ([Google AI][3])

# KCS 適用方針

```text
表:   table_format=null (Markdown 本文に inline)。表を独立 object にしない既定と一致。
      複雑表のみ html → KCS 側で Markdown 表へ正規化 or HTML 許容
画像: include_image_base64=true で抽出 → hash 化して CAS 保存 → Markdown 内 placeholder を
      KCS object 参照に置換 (URI 形式は未決 — 下記論点 3)
bbox / page / confidence: unit / chunk のメタデータとして保存 (Evidence Pointer 必須 schema は変えない)
Adapter 名: mistral_ocr_markdownize (内部用語は「Markdownize」に統一、OCR は外部サービス名としてのみ)
```

Gemini の役割: OCR 後 Markdown の品質チェック / 図表の意味説明 / 曖昧な画像・グラフの解釈 / 横断要約 / Document Q&A。

# 正本 spec との差分 (原文 LLM 出力から修正した点)

```text
- 原文の「objects/normalized/<normalized_hash>.md」は旧語彙。正本は normalized instance =
  (raw_hash, tool_profile_hash, gen) の unit object 群 (03 §2.1)。normalized_hash は不採用 (03 §5)
- 「mistral-ocr-latest を指定」は config 上のみ可。tool_profile_hash の model_version_pin は
  immutable tag 必須 (03 §5.1) のため、実行時に解決した実モデル名を pin として記録する
- 「Evidence Pointer に bbox を持つ」は現 08 schema に存在しない。必須 schema の変更は breaking
  のため、入れるなら optional フィールド (forward compat: 未知フィールド無視) として Phase 判断
```

# 正本への反映 (2026-07-02)

```text
- 07 §5.2: 標準 Adapter = mistral_ocr_markdownize。表は inline、embedded image は
  image object 保存 + kcs:// 参照置換、bbox/confidence は unit metadata (pointer 必須 schema 不変)
- 07 §6:   tool-lock 例を mistral_ocr_markdownize に。latest alias は config のみ可、
  model_version_pin は実行時解決した immutable 版
- 07 §8:   incremental プロンプト規約は生成 LLM 系限定 (OCR 系は unit fingerprint 再利用経路)
- 03 §1/§2/§8.1/§10: image object type を予約 (content hash。実装 Step 2)
- 08 §2.3: kcs://<scope_id>/object/<type>/<hash> の object 参照形式を追加
- 01 §1.1 / README / 04 §3: frontier AI 例示に Mistral を追加
- 09 §3.1 (割当表 Step 2 行)・§4.1 (コスト試算根拠 = OCR 4 Batch $2/1k pages)・
  §5.5 (宿題 #6: 実地検証を Step 2 着手前ゲートに登録)
```

残: 宿題 #6 の実地検証 (07 §5.2 リスク注記)。view export 時の相対パス画像解決は Phase 4+ 構想。

[1]: https://mistral.ai/news/ocr-4 "Mistral OCR 4 : SOTA OCR for Document Intelligence"
[2]: https://docs.mistral.ai/capabilities/document_ai/basic_ocr "OCR Processor | Mistral Docs"
[3]: https://ai.google.dev/gemini-api/docs/document-processing "Document understanding | Gemini API"
[4]: https://mistral.ai/news/mistral-ocr-3 "Introducing Mistral OCR 3 | Mistral AI"
