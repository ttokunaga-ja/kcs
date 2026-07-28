```sql
-- 南砂物流センター増築工事: 材料検査の未提出証明書を確認するビュー
CREATE TABLE IF NOT EXISTS material_inspections (
  inspection_id INTEGER PRIMARY KEY,
  material_code TEXT NOT NULL,
  received_on DATE NOT NULL,
  certificate_status TEXT NOT NULL,
  reviewer TEXT NOT NULL
);

CREATE VIEW pending_certificate_checks AS
SELECT material_code, received_on, reviewer
FROM material_inspections
WHERE certificate_status <> 'accepted';

-- 防水材・止水材の受入記録はこのビューで日次確認する。
```
