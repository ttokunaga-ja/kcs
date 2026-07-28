```yaml
dashboard:
  title: Harborline Storefront Product Health
  owner_team: Commercial Intelligence
  refresh_timezone: Asia/Tokyo
  audience:
    - product_leadership
    - commercial_planning
  filters:
    - name: reporting_week
      default: latest_closed_week
    - name: market_code
      default: all
datasets:
  activation_funnel:
    model: mart_product.activation_funnel_weekly
    metric: activated_buyers
    dimensions: [week_start, market_code, product_family]
  repeat_purchase:
    model: mart_sales.weekly_buyer_cohort
    metric: retained_buyers
    dimensions: [cohort_week, activity_week, channel]
release:
  change_window: Tuesday 13:00 JST
  validation:
    - row_count_check
    - semantic_contract_check
    - stakeholder_preview
```
