```sql
-- Active escalation snapshot for the Harborline Workspace support handoff.
-- Run in the read-only reporting replica before the Japan afternoon handoff.

WITH latest_customer_note AS (
    SELECT DISTINCT ON (n.case_number)
        n.case_number,
        n.created_at AS last_customer_note_at
    FROM support_case_notes AS n
    WHERE n.author_type = 'customer'
    ORDER BY n.case_number, n.created_at DESC
),
open_escalations AS (
    SELECT
        c.case_number,
        c.account_name,
        c.priority,
        c.status,
        c.owner_team,
        c.opened_at,
        c.next_update_due_at,
        e.reason AS escalation_reason,
        e.assigned_engineer
    FROM support_cases AS c
    JOIN support_escalations AS e
      ON e.case_number = c.case_number
     AND e.closed_at IS NULL
    WHERE c.status NOT IN ('resolved', 'closed')
)
SELECT
    o.case_number,
    o.account_name,
    o.priority,
    o.status,
    o.owner_team,
    o.escalation_reason,
    o.assigned_engineer,
    o.opened_at AT TIME ZONE 'Asia/Tokyo' AS opened_jst,
    o.next_update_due_at AT TIME ZONE 'Asia/Tokyo' AS next_update_due_jst,
    l.last_customer_note_at AT TIME ZONE 'Asia/Tokyo' AS last_customer_note_jst,
    CASE
        WHEN o.next_update_due_at < now() THEN 'update overdue'
        WHEN o.priority = 'P1' THEN 'watch closely'
        ELSE 'on track'
    END AS handoff_state
FROM open_escalations AS o
LEFT JOIN latest_customer_note AS l ON l.case_number = o.case_number
ORDER BY
    CASE o.priority WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 ELSE 3 END,
    o.next_update_due_at NULLS LAST;
```
