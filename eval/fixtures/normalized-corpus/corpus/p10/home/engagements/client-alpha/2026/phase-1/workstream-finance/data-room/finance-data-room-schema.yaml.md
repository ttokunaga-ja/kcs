```yaml
engagement: project-meridian
client: Verdant Bottling Group
as_of: 2026-07-18
datasets:
  purchase_orders:
    grain: purchase-order-line
    required_fields:
      - plant_code
      - supplier_code
      - material_family
      - order_date
      - receipt_date
      - amount_usd
  general_ledger:
    grain: accounting-month-account
    required_fields:
      - fiscal_month
      - account_code
      - plant_code
      - amount_usd
quality_rules:
  - source totals reconcile to the May close
  - supplier codes map to the approved crosswalk
  - dates use ISO-8601 format
owners:
  finance_extract: client-controller
  supplier_crosswalk: procurement-analytics
```
