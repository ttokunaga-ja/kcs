```xml
<?xml version="1.0" encoding="UTF-8"?>
<weeklyRefreshFeed weekEnding="2026-07-19" timezone="Asia/Tokyo">
  <mart name="daily_market_channel" domain="sales" status="ready">
    <watermark>2026-07-20T06:35:00+09:00</watermark>
    <note>会計確定済みの注文を含む。</note>
  </mart>
  <mart name="fulfillment_margin_daily" domain="operations" status="ready">
    <watermark>2026-07-20T07:12:00+09:00</watermark>
    <note>carrier surcharge は separate cost component。</note>
  </mart>
  <mart name="activation_funnel_weekly" domain="product" status="review">
    <watermark>2026-07-20T09:42:00+09:00</watermark>
    <note>bot filter の再計算を確認中。</note>
  </mart>
</weeklyRefreshFeed>
```
