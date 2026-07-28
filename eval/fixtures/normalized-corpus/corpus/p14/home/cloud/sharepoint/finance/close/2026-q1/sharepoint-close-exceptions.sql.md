```sql
-- SharePoint の月次締め例外リストを、レビュー会用に抽出する。
-- 対象: 東雲フルフィルメント株式会社 / 2026年3月締め

WITH latest_update AS (
    SELECT
        item_id,
        MAX(updated_at) AS latest_updated_at
    FROM finance_close_exception_history
    WHERE close_month = DATE '2026-03-01'
    GROUP BY item_id
)
SELECT
    e.item_id,
    e.category,
    e.department_name,
    e.owner_name,
    e.status,
    e.due_date,
    e.summary,
    e.updated_at
FROM finance_close_exceptions AS e
INNER JOIN latest_update AS u
    ON e.item_id = u.item_id
   AND e.updated_at = u.latest_updated_at
WHERE e.close_month = DATE '2026-03-01'
  AND e.status IN ('対応中', '確認待ち')
ORDER BY e.due_date NULLS LAST, e.department_name, e.item_id;

-- 会議で完了を確認した項目だけ、ステータスを更新する。
UPDATE finance_close_exceptions
SET
    status = '完了',
    resolved_at = TIMESTAMP '2026-04-03 16:30:00+09',
    resolution_note = '月次締めレビューで証憑と仕訳を確認済み'
WHERE item_id = 'CE-202603-014'
  AND close_month = DATE '2026-03-01'
  AND status = '対応中';
```
