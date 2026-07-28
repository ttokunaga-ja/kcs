# Warehouse lineage の未解決点 — 2026-07

Q2 close 後の棚卸しで、利用者への影響が残る lineage の抜けを整理した。緊急停止が必要なものはなく、いずれも refresh の説明可能性を上げるための作業である。

| 対象 | 現状 | 対応 | 担当 |
| --- | --- | --- | --- |
| node capacity | holiday override が spreadsheet 経由 | config table に取り込み、更新者を記録 | Network Planning |
| campaign attribution | referral mapping の版が明示されない | mapping effective date を mart に渡す | Sales Analytics |
| product activation | session bot filter の除外理由が view に見えない | semantic layer の description に追記 | Product Insights |



## 補足

lineage は「どの表を読んだか」だけでなく、計画会議で数字を再説明できることを目的にする。特に Harborline Storefront の seasonal campaign は週途中で施策名が変わるため、effective date の扱いを先に固定する。

来週の governance huddle では、変更履歴を CSV に残すか warehouse comment に寄せるかを決める予定。The preferred option is a small governed table because it can be joined during incident review.
