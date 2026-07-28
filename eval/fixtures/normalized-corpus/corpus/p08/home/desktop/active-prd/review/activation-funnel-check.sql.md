```sql
-- Harbor の activation review 用。週次の大きな差分を会話の起点にする。
WITH first_signal AS (
  SELECT
    workspace_id,
    actor_id,
    MIN(created_at) AS first_signal_at
  FROM research_signals
  WHERE product_area = 'harbor'
  GROUP BY 1, 2
),
assignment_state AS (
  SELECT
    s.workspace_id,
    s.actor_id,
    s.first_signal_at,
    MIN(a.assigned_at) AS first_assignment_at,
    COUNT(DISTINCT CASE WHEN e.evidence_url IS NOT NULL THEN e.signal_id END) AS evidence_linked
  FROM first_signal s
  LEFT JOIN signal_assignments a
    ON a.workspace_id = s.workspace_id
   AND a.actor_id = s.actor_id
   AND a.assigned_at >= s.first_signal_at
  LEFT JOIN signal_evidence e
    ON e.workspace_id = s.workspace_id
   AND e.created_at >= s.first_signal_at
  GROUP BY 1, 2, 3
)
SELECT
  DATE_TRUNC('week', first_signal_at) AS week_start,
  COUNT(*) AS activated_reviewers,
  COUNT(*) FILTER (
    WHERE first_assignment_at <= first_signal_at + INTERVAL '24 hours'
  ) AS assigned_within_one_day,
  COUNT(*) FILTER (WHERE evidence_linked > 0) AS reviewers_with_evidence
FROM assignment_state
GROUP BY 1
ORDER BY 1;
```
