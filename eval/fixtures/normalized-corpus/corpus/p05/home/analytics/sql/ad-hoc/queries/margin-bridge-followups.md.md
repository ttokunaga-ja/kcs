# Margin bridge follow-ups

7/22 の ad-hoc review では、Q2 の売上差異よりも freight と promotion funding の時点ずれが bridge の読みにくさを作っていると確認した。



## 決まったこと

- Sales mart は recognized net sales を固定値として渡す。受注ステータスを後から再解釈しない。
- Operations mart は base freight / surcharge / handling を分けて出す。
- Product incentive は施策開始週に寄せず、契約上の費用認識日に寄せる。



## 追跡項目

| 項目 | 期待する状態 | 次の確認 |
| --- | --- | --- |
| carrier mapping | service 名が月内で一意 | 月次 close 前 |
| promotion funding | finance ledger と差が小さい | 木曜の rehearsal |
| returns reserve | provisional を bridge から除外 | semantic model release |

Finance asked for a short narrative beside the chart so that the executive readout does not turn into a query walkthrough.
