```sql
-- 部門別経費のカットオフ確認用。
-- 3月にサービスを受け、4月以降に請求書が到着した可能性がある費用を抽出する。
SELECT
    e.department_code,
    d.department_name,
    e.vendor_code,
    e.expense_type,
    e.service_from,
    e.service_to,
    e.expected_amount_jpy,
    e.invoice_received_at,
    e.owner_name
FROM department_expense_commitments AS e
INNER JOIN department_master AS d
    ON d.department_code = e.department_code
WHERE e.service_from <= DATE '2026-03-31'
  AND e.service_to >= DATE '2026-03-01'
  AND (e.invoice_received_at IS NULL OR e.invoice_received_at >= DATE '2026-04-01')
  AND e.commitment_status IN ('open', 'awaiting_invoice')
ORDER BY d.department_name, e.expected_amount_jpy DESC;

-- 部門責任者が確認済みにした行を、月次レビューから除外する。
UPDATE department_expense_commitments
SET
    close_review_status = 'confirmed_no_accrual',
    close_reviewed_at = CURRENT_TIMESTAMP
WHERE commitment_id = :commitment_id
  AND close_month = DATE '2026-03-01'
  AND close_review_status = 'pending';
```
