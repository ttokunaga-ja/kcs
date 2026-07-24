# Step3c K ラウンド 4 エンジン再監査の記録と裁定 (2026-07-04)

対象: コミット範囲 5b52861..0a46b35 (K ラウンド納品 7 コミット)。
エンジン: Claude Opus / Claude Sonnet (エージェント並列、品質ゲート・実機再現可) +
GPT-5.5 / GPT-5.3-Codex-Spark (codex exec、read-only sandbox、静的監査)。
全エンジンに同一監査指示書 (配線の実在 / P0 反証検証 / 契約適合 / 開示の正確性 / ゲート再現) を配布。

## エンジン別判定

| エンジン | verdict | findings |
| --- | --- | --- |
| Claude Opus | sound | minor 2 (FtsIndex::search 本番未使用 / fallback_reason 固定文字列) |
| Claude Sonnet | fix-required | major 1 (HYBRID-003 テスト不活性 — sqlite.db 削除の有無で --vector 出力がバイト同一と実機立証) / minor 1 (HYBRID-002 のペア依存) |
| GPT-5.5 | fix-required | major 2 (HYBRID-003 同件 / Evidence 手順 6-7 の失敗契約未実装) / minor 1 (cursor 消失 scope の誤 CURSOR-001) |
| GPT-5.3-Codex-Spark | sound | なし (配線実在 + P0 8 件抜き取り全 PASS) |

## 全エンジン一致の確認事項 (前ラウンド根本診断の解消)

- `kio search` は FTS5 MATCH (bm25) → fuse_rrf → rank ベース scope 間統合 →
  diversify_candidates / chunk_vec (vec0) KNN に真正配線。自作スコアラ・手計算リランクの
  残骸なし (4/4 一致)
- 品質ゲート再現 (Opus / Sonnet 独立): 227 green / clippy / fmt / eval M3-1 = 0.8889
  (バイト一致、miss 2 件は開示どおり)。実機シナリオ (a)-(e) を両エンジンが独立再現
- 開示の正確性: 完了報告の開示 8 項は実態と一致 (Opus/Sonnet が個別にコード裏取り)

## 統合裁定 = fix-required → 同日修正済み (コミット 2d13784)

採択 findings と処置 (全件、調整役がコード照合のうえ実在確認してから発注):

1. [major] HYBRID-003 (Sonnet + GPT-5.5): CT の When (`kio search`、auto) を検証しない
   --vector テスト + auto「両方不可」が SCOPE-ALL-FAILED-001 になる実装
   → 全 scope 除外かつ全理由が index 不能 (index_missing/corrupt) なら
   KIO-E-SEARCH-VEC-UNAVAIL-001 exit 1。到達不能系全滅は exit 4 を維持。テスト書換 + 対照 assert
2. [major] Evidence 手順 6/7 (GPT-5.5): chunk 行未実体化のポインタで view が空テキスト成功
   → KIO-E-EVIDENCE-RETARGET-REQUIRED-001 exit 8 (08 §3.2 / 06 §7、decisions #33)。
   tree entry の profile 等値は強制しない (Step 1 raw-only tree / chunk_hash 自己証明性のため)
3. [minor] cursor 消失 scope (GPT-5.5): query_hash 検証を cursor 自身の scope 集合で行い、
   未解決 scope は excluded + exit 3。consumed skip も解決可能 scope のみに補正
4. [minor] fallback_reason 実因分岐 (Opus)
5. [minor] FtsIndex trait の inherent 化 + テスト probe 明示 (Opus)
6. [minor] HYBRID-002 のテスト内ペア化 (Sonnet)

不採択: なし (提出された findings は全件実在と確認し全件修正)。

修正後ゲート: workspace 229 green / clippy -D warnings / fmt / eval M3-1 = 0.8889 (不変)。
主要 2 件は調整役が実バイナリでも再現確認 (auto+index 欠損 → exit 1 VEC-UNAVAIL / 修正前の
挙動が再現しないこと)。

## 運用メモ

- Spark は context window が小さく、full diff (6.5k 行) の丸読みで初回失敗 →
  「丸読み禁止・grep/sed 限定・監査軸 2 本に集中」の軽量プロトコルで完走。
  以後 Spark への監査発注は同プロトコルを使うこと
- read-only sandbox の GPT 系はゲート再現不可 (静的監査のみ)。ゲート再現は Claude 系が担保
- 4 エンジンの findings 検出は相補的だった: Sonnet = 実機反証 (テスト不活性の立証)、
  GPT-5.5 = 契約条文の深掘り (解決手順 6-7)、Opus = 実装衛生 (死 trait / reason 精度)、
  Spark = 主経路の独立確認。単一エンジルでは major 2 件のどちらかを見逃していた
