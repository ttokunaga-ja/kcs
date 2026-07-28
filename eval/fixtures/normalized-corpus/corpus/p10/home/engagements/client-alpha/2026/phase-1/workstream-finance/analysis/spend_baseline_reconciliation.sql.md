```sql
-- Project Meridian: reconcile purchasing detail to the May finance close.
WITH normalized_spend AS (
    SELECT
        po.plant_code,
        map.material_family,
        date_trunc('month', po.receipt_date) AS receipt_month,
        SUM(po.extended_amount_usd) AS purchase_order_spend_usd
    FROM raw_purchase_order_lines po
    JOIN supplier_material_map map
      ON map.supplier_code = po.supplier_code
     AND map.material_code = po.material_code
    WHERE po.receipt_date >= DATE '2026-05-01'
      AND po.receipt_date < DATE '2026-06-01'
    GROUP BY 1, 2, 3
), ledger_spend AS (
    SELECT plant_code, SUM(amount_usd) AS ledger_spend_usd
    FROM finance_general_ledger
    WHERE fiscal_month = DATE '2026-05-01'
      AND account_group = 'Packaging and freight'
    GROUP BY 1
)
SELECT
    n.plant_code,
    SUM(n.purchase_order_spend_usd) AS purchase_order_spend_usd,
    l.ledger_spend_usd,
    l.ledger_spend_usd - SUM(n.purchase_order_spend_usd) AS reconciliation_delta_usd
FROM normalized_spend n
JOIN ledger_spend l USING (plant_code)
GROUP BY 1, 3
ORDER BY 1;
```
