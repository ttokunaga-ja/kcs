```json
{
  "dashboard": "Commercial Daily Pulse",
  "platform": "Harborline Storefront",
  "timezone": "Asia/Tokyo",
  "refresh": {
    "target": "06:45",
    "source_marts": [
      "mart_sales.daily_market_channel",
      "mart_operations.fulfillment_margin_daily"
    ]
  },
  "tiles": [
    {
      "label": "Net sales",
      "metric": "recognized_net_sales",
      "group_by": ["business_date", "market_code", "channel"],
      "format": "currency_jpy"
    },
    {
      "label": "Contribution margin",
      "metric": "fulfillment_margin",
      "group_by": ["business_date", "market_code"],
      "format": "currency_jpy"
    },
    {
      "label": "Active buyers",
      "metric": "active_buyers",
      "group_by": ["business_date", "channel"],
      "format": "integer"
    }
  ],
  "review_note": "月曜は前週確定分を優先し、速報値の比較は注記付きで表示する。"
}
```
