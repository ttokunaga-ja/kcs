```xml
<?xml version="1.0" encoding="UTF-8"?>
<invoiceHoldRegister company="東雲フルフィルメント株式会社" exportedAt="2026-04-02T09:15:00+09:00">
  <period fiscalYear="2026" month="03" />
  <holds>
    <hold id="AP-2603-041" status="awaiting_receipt">
      <supplier code="V-10482">瑞穂ロジスティクス株式会社</supplier>
      <invoiceNumber>ML-202603-118</invoiceNumber>
      <amount currency="JPY">1248000</amount>
      <owner>買掛担当・森</owner>
      <reason>3月30日納品分の受領登録が倉庫側で未完了</reason>
      <nextAction due="2026-04-03">西東京DCの受領記録を確認する</nextAction>
    </hold>
    <hold id="AP-2603-057" status="tax_check">
      <supplier code="V-20816">霞ヶ関データセンター株式会社</supplier>
      <invoiceNumber>KDC-0326-77</invoiceNumber>
      <amount currency="JPY">486000</amount>
      <owner>買掛担当・森</owner>
      <reason>請求書の消費税区分と契約台帳の区分が一致しない</reason>
      <nextAction due="2026-04-04">契約更新覚書を経理共有へ添付する</nextAction>
    </hold>
  </holds>
</invoiceHoldRegister>
```
