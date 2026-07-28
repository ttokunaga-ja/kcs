```sql
-- Commercial Intelligence / FY2026 Q2 planning refresh
-- 指標カタログの粒度が、実装済み mart と一致しているかを週次で確認する。
with catalog as (
  select metric_key, expected_grain, owner_team
  from governance.metric_catalog
  where lifecycle_state = 'published'
),
observed as (
  select
    'net_sales' as metric_key,
    'business_date, market_code, channel' as observed_grain,
    count(*) as row_count,
    count(distinct concat_ws('|', business_date, market_code, channel)) as distinct_keys
  from mart_sales.daily_market_channel
  where business_date between date '2026-04-01' and date '2026-06-30'
  union all
  select
    'fulfillment_margin',
    'business_date, fulfillment_node, carrier_service',
    count(*),
    count(distinct concat_ws('|', business_date, fulfillment_node, carrier_service))
  from mart_operations.fulfillment_margin_daily
  where business_date between date '2026-04-01' and date '2026-06-30'
)
select
  c.metric_key,
  c.expected_grain,
  o.observed_grain,
  o.row_count,
  o.distinct_keys,
  case
    when c.expected_grain = o.observed_grain and o.row_count = o.distinct_keys then 'pass'
    else 'review'
  end as audit_result,
  c.owner_team
from catalog c
left join observed o using (metric_key)
order by audit_result desc, metric_key;
```
