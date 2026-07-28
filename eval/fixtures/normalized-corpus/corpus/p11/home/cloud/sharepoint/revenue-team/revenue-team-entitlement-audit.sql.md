```sql
-- Revenue team entitlement review for the Q3 account-planning workspace.
-- Run in the reporting replica only; this query does not change permissions.
WITH active_members AS (
  SELECT
    u.user_id,
    u.display_name,
    u.department,
    e.workspace_role,
    e.granted_at
  FROM revenue_workspace_entitlements AS e
  JOIN users AS u ON u.user_id = e.user_id
  WHERE e.workspace_name = 'Revenue Cloud Account Planning'
    AND e.revoked_at IS NULL
)
SELECT
  display_name,
  department,
  workspace_role,
  granted_at
FROM active_members
WHERE department IN ('Sales', 'Revenue Operations', 'Customer Success', 'Legal')
ORDER BY department, display_name;
```
