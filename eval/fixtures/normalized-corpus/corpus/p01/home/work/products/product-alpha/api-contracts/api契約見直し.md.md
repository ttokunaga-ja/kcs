# Orchid Ledger API 契約の見直し

**July 2026 · Ledger Platform**



## 依頼本文の扱い

Orchid Ledger 2026.07 向けに、依頼本文の例と validation の説明を更新した。呼び出し側が業務上の用語をそのまま送っても、境界で `posting intent` に読み替えられることを明記する。

| 項目 | 契約上の扱い |
| --- | --- |
| `merchant_reference` | 加盟店側で追跡に使う識別子として保存する |
| `submission_key` | 再送を識別するため、同じ依頼では変更しない |
| `posted_at` | 業務上の記帳日として検証する |
| `entries` | 値の向きと通貨コードを一つの単位として検証する |



## エラーの表現

呼び出し元に返すエラーは、入力不備・業務規則・一時的な処理失敗に分けた。内部の例外名やストレージの詳細を本文に出さない。SDK の利用者が取るべき行動を判断できる粒度を維持する。



## 確認待ち

- OpenAPI の例を integration guide と照合する
- webhook 側の `event_type` と結果イベントの名称をそろえる
- 旧いクライアント向けの説明を release note に移す
