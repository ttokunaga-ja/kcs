```xml
<?xml version="1.0" encoding="UTF-8"?>
<fieldRequestBatch generatedAt="2026-07-22T09:15:00+09:00" ownerTeam="Commercial Intelligence">
  <request area="sales">
    <field name="recognized_net_sales" type="decimal" grain="business_date,market_code,channel">
      <description>会計確定済みの売上。取消は確定日で差し引く。</description>
      <consumer>weekly commercial scorecard</consumer>
    </field>
    <field name="campaign_family" type="string" grain="order_line">
      <description>planning refresh で施策群を比較するための正規化ラベル。</description>
      <consumer>scenario workbook export</consumer>
    </field>
  </request>
  <request area="operations">
    <field name="surcharge_amount" type="decimal" grain="shipment">
      <description>carrier service ごとの追加費用。基本送料とは別に表示する。</description>
      <consumer>margin bridge</consumer>
    </field>
  </request>
</fieldRequestBatch>
```
