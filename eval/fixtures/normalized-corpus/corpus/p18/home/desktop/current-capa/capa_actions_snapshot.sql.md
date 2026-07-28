```sql
-- Current CAPA action snapshot for the quality workbench.
WITH open_actions AS (
  SELECT action_no, owner_team, due_date, state
  FROM qms.capa_action
  WHERE state IN ('open', 'in_review')
    AND product_family IN ('Aster A1', 'Nagi B2')
)
SELECT owner_team, state, COUNT(*) AS action_count
FROM open_actions
GROUP BY owner_team, state
ORDER BY owner_team, state;
```
