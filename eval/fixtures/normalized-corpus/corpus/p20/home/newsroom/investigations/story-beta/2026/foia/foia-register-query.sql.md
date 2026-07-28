```sql
-- 港湾再整備契約の開示受付簿を確認するための作業用クエリ
SELECT
  request_id,
  received_on,
  office_name,
  requested_record,
  disposition
FROM disclosure_register
WHERE project_label = '湾岸再整備契約'
  AND received_on >= DATE '2025-01-01'
ORDER BY received_on, request_id;
```
