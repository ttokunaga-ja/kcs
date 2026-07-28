```sql
-- 2026年3月度の見越候補。月末までに役務提供が完了したものだけを抽出する。
WITH received_services AS (
    SELECT
        s.vendor_code,
        s.contract_id,
        SUM(s.amount_jpy) AS service_amount_jpy,
        MAX(s.service_date) AS last_service_date
    FROM vendor_service_receipts AS s
    WHERE s.service_date BETWEEN DATE '2026-03-01' AND DATE '2026-03-31'
      AND s.receipt_status = 'accepted'
    GROUP BY s.vendor_code, s.contract_id
),
invoiced_services AS (
    SELECT
        i.vendor_code,
        i.contract_id,
        SUM(i.amount_jpy) AS invoiced_amount_jpy
    FROM accounts_payable_invoices AS i
    WHERE i.invoice_month = DATE '2026-03-01'
      AND i.approval_status IN ('approved', 'posted')
    GROUP BY i.vendor_code, i.contract_id
)
SELECT
    r.vendor_code,
    r.contract_id,
    r.last_service_date,
    r.service_amount_jpy - COALESCE(i.invoiced_amount_jpy, 0) AS proposed_accrual_jpy
FROM received_services AS r
LEFT JOIN invoiced_services AS i
  ON i.vendor_code = r.vendor_code
 AND i.contract_id = r.contract_id
WHERE r.service_amount_jpy > COALESCE(i.invoiced_amount_jpy, 0)
ORDER BY proposed_accrual_jpy DESC;

-- レビュー済み候補を証憑キーと共に固定する。実行前に担当者が金額を確認すること。
INSERT INTO month_end_accrual_review (
    close_month, vendor_code, contract_id, proposed_accrual_jpy, reviewer, review_status, evidence_key
)
SELECT
    DATE '2026-03-01',
    vendor_code,
    contract_id,
    proposed_accrual_jpy,
    '森',
    'pending_confirmation',
    CONCAT('shinonome/2026-03/accrual/', vendor_code, '/', contract_id)
FROM accrual_review_candidates;
```
