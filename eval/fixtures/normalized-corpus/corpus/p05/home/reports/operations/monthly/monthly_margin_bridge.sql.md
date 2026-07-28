```sql
-- Monthly operations margin bridge for the FY2026 Q2 close
with sales as (
  select
    date_trunc('month', business_date) as month_start,
    market_code,
    sum(recognized_net_sales) as net_sales
  from mart_sales.daily_market_channel
  where business_date between date '2026-04-01' and date '2026-06-30'
  group by 1, 2
),
costs as (
  select
    date_trunc('month', business_date) as month_start,
    market_code,
    sum(base_freight) as base_freight,
    sum(surcharge_amount) as surcharge_amount,
    sum(handling_cost) as handling_cost
  from mart_operations.fulfillment_margin_daily
  where business_date between date '2026-04-01' and date '2026-06-30'
  group by 1, 2
)
select
  s.month_start,
  s.market_code,
  s.net_sales,
  c.base_freight,
  c.surcharge_amount,
  c.handling_cost,
  s.net_sales - c.base_freight - c.surcharge_amount - c.handling_cost as fulfillment_margin
from sales s
join costs c using (month_start, market_code)
order by month_start, market_code;
```
