# Metric model release — 2026-07-21

**対象:** Harborline Storefront の commercial semantic model



## 今回の内容

- `recognized_net_sales` に channel を必須次元として追加。
- `fulfillment_margin` で carrier surcharge を独立列に変更。
- active buyer cohort から internal test account を除外。



## 公開判断

Sales と Operations の日次値は close rehearsal の期待範囲に収まった。Product activation は前年比表記を外し、比較対象を FY2026 の週次基準へそろえた。The release is backward compatible for the existing executive tiles.



## ロールバック条件

1. daily_market_channel の watermark が 06:00 JST を超えて到着しない。
2. 同一日付・market・channel の重複が検知される。
3. finance ledger との差がレビュー閾値を超え、理由を説明できない。

公開後は 2 営業日だけ、朝会で refresh status を確認する。
