# Embedding ベンダー実地検証 — 確定版 (2026-07-03)

> **本書は確定版。** 初回調査 (2026-07-03 午前) は「Gemini Embedding 2 multimodal は preview で版ピン留め不可」
> という事実誤認に基づき text-only 緩和 (gemini-embedding-001 / modality=text) を推奨していたが、
> ユーザー指摘と再検証により**誤りと確定し、当該分析・推奨は全文破棄した** (git 履歴にのみ残る)。
> 別ベクトル空間への埋め込み (非 multimodal profile) は [03-data-model.md §7](../docs/03-data-model.md) /
> [07-adapter-spec.md §5.3](../docs/07-adapter-spec.md) により**採用不可** (`KCS-E-EMBED-MODALITY-001` で拒否)。

## 確定判定

**単一マルチモーダル Embedding profile を採用する** (07 §5.3 の本来の契約どおり。text-only 緩和は撤回)。

## 採用 profile

```json
{
  "tool_id": "gemini_embedding_2",
  "kind": "online_api",
  "mode": "online",
  "dimensions": 768,
  "distance": "cosine",
  "modality": "multimodal",
  "profile_hash": "(実装時に tool_profile_hash を算出)"
}
```

- **モデル**: `gemini-embedding-2` — 2026-04-22 GA (preview は 2026-03-10)。text / image / audio / video を
  同一ベクトル空間へ写像。最大入力 8,192 tok、MRL 対応 (最大 3,072 次元)
- **版ピン留め**: GA の pinned stable 版を Adapter が起動時に解決して `model_version_pin` に記録
  (07 §6 の規約どおり)。03 §5.1 の版固定要件と両立
- **次元**: **768** (MRL 切り詰め)。切り詰め後次元も profile に固定 — 変更は profile_hash 変化 = 全 re-index
- **mode**: **online** (Vertex はバッチ推論非対応)。client 側で並列 + 429 backoff
- **MVP で embed するのは text chunk のみ**。image / audio / video の実生成は Phase 4+ — profile が
  multimodal なので [03-data-model.md §7](../docs/03-data-model.md) の全 re-index なしに追加できる
  (これが単一 multimodal 契約の狙い)

## 判定根拠 (再検証で裏取り済み)

1. **(a) pin 可能性**: `gemini-embedding-2` は GA + pinned stable 版あり → 03 §5.1 と両立
2. **(c) 日本語 text 品質**: MTEB/MMTEB 69.9 で `gemini-embedding-001` (68.32) を上回り、日本語も同格 →
   multimodal 採用で text 品質を犠牲にしない
3. **(b) コスト**: 10 万 chunk 初回 ≈ $10 (バッチ非対応の通常 PayGo 単価)。単月 budget ($10-20) 内。増分は月 $1 未満
4. **機会費用**: 北極星 M3-1〜M3-3 は text 検索で完結するが、multimodal profile の採用に品質・pin の犠牲が
   無い以上、Phase 4+ の image/audio 拡張を re-index なしで得られる multimodal が優位

## 強制 (2026-07-03 追加)

- 03 §7: `modality` は `"multimodal"` に固定。非 multimodal profile は tool-lock materialize / adapter 登録で
  `KCS-E-EMBED-MODALITY-001` (exit 2) として拒否
- 06 §8: `KCS-E-EMBED-MODALITY-001` を登録済み
- step3a: CT3-EMBED-008 (P0) が拒否契約を検証。CT3-EMBED-004 + A.2 ベクタは本 profile で凍結済み
  (tool_profile_hash `sha256:66aff638…`、embedding_hash `sha256:7bd32d26…`)

## 将来の代替候補 (参考、いずれも現時点で非採用)

- multimodal: cohere embed-v4.0 (GA・pin 可だが text 品質が劣後) / voyage-multimodal-3 (同)
- 出典: Vertex AI 公式モデルページ・料金ページ・リリースノート (2026-07-03 参照)
