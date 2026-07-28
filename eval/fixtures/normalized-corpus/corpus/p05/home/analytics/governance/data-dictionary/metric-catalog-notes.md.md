# FY2026 Q2 指標カタログ整理メモ

Commercial Intelligence では、Harborline Storefront の日次レポートを sales / operations / product の三つの mart で提供している。今週は Q2 planning refresh に合わせ、利用者が画面上で見る粒度と warehouse の集約粒度を照合した。



## 合意した定義

| 指標 | 表示単位 | 集計の注意 | 所有チーム |
| --- | --- | --- | --- |
| Net sales | 日付 × market × channel | 取消は注文日ではなく会計確定日で反映 | Sales Analytics |
| Fulfillment margin | 日付 × node × service | surcharge は配送完了日の費用に寄せる | Operations Finance |
| Product activation | 週 × product family | 同一 buyer の再訪は週内で重複除外 | Product Insights |



## 変更点

- `net_sales` は marketplace と direct を同じ列に積まず、channel を必須キーにする。
- 返品の provisional 状態は published metric から除く。Close review で確定したものだけを使う。
- 施策比較では Mosaic の計画ラベルを scenario 列に残し、通常の月次実績と混在させない。



## 次回までの確認

1. Operations 側で carrier surcharge の遅延計上を小さな注記で説明できるか確認する。
2. Product activation の分母を active buyer に統一し、旧 dashboard の visitor 分母を廃止する。
3. 英語版の metric description は Finance review の後にまとめて更新する。
