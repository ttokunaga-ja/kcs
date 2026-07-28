```csv
consumer_model,upstream_model,warehouse_domain,refresh_cadence,steward,contract_state,notes
mart_sales.daily_market_channel,core_orders.order_financials,sales,06:30 JST,Sales Analytics,approved,会計確定済み注文のみ
mart_sales.weekly_buyer_cohort,core_customers.buyer_activity,sales,Monday 08:00 JST,Commercial Intelligence,approved,guest checkout は匿名 cohort
mart_operations.fulfillment_margin_daily,core_fulfillment.shipment_costs,operations,07:15 JST,Operations Finance,approved,carrier surcharge を別列で保持
mart_operations.node_capacity_weekly,core_fulfillment.node_schedule,operations,Tuesday 09:00 JST,Network Planning,review,祝日補正の説明を追加予定
mart_product.activation_funnel_weekly,core_product.session_events,product,Monday 10:00 JST,Product Insights,approved,bot filter 適用後の session
semantic.commercial_kpis,mart_sales.daily_market_channel,sales,08:00 JST,Commercial Intelligence,approved,executive dashboard 用の共通 view
```
