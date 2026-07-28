```sql
-- ORCHID-CKD-201 training-simulation safety reconciliation extract
-- PostgreSQL 15; de-identified training data cut only, not live site status.
-- The input cohort is limited to scenario records explicitly marked for training.

WITH scheduled_reviews AS (
    SELECT
        v.subject_token,
        v.visit_id,
        v.visit_label,
        v.visit_date,
        v.visit_status,
        CASE
            WHEN v.visit_status IN ('completed', 'window-complete') THEN 'within-window'
            WHEN v.visit_status = 'missed' THEN 'missed'
            ELSE 'out-of-window-or-pending'
        END AS visit_window_assessment
    FROM clinical.visit v
    JOIN clinical.subject s
        ON s.study_code = v.study_code AND s.subject_token = v.subject_token
    WHERE v.study_code = 'ORCHID-CKD-201'
      AND v.visit_label = 'W12'
      AND s.is_training_scenario = true
),
event_rollup AS (
    SELECT
        ae.subject_token,
        ae.visit_id,
        COUNT(ae.event_id) FILTER (WHERE ae.status <> 'void') AS reported_event_count,
        COUNT(ae.event_id) FILTER (
            WHERE ae.status <> 'void' AND ae.is_serious = true
        ) AS serious_event_count,
        MAX(ae.updated_at) AS last_event_update
    FROM safety.adverse_event ae
    JOIN clinical.subject s
        ON s.study_code = ae.study_code AND s.subject_token = ae.subject_token
    WHERE ae.study_code = 'ORCHID-CKD-201'
      AND s.is_training_scenario = true
    GROUP BY ae.subject_token, ae.visit_id
),
lab_rollup AS (
    SELECT
        l.subject_token,
        l.visit_id,
        MAX(l.received_at) AS last_lab_receipt,
        BOOL_AND(l.review_status = 'reviewed') AS all_labs_reviewed
    FROM central_lab.result l
    JOIN clinical.subject s
        ON s.study_code = l.study_code AND s.subject_token = l.subject_token
    WHERE l.study_code = 'ORCHID-CKD-201'
      AND s.is_training_scenario = true
    GROUP BY l.subject_token, l.visit_id
)
SELECT
    r.subject_token,
    r.visit_label,
    r.visit_date,
    r.visit_status,
    r.visit_window_assessment,
    COALESCE(e.reported_event_count, 0) AS reported_event_count,
    COALESCE(e.serious_event_count, 0) AS serious_event_count,
    COALESCE(l.all_labs_reviewed, false) AS all_labs_reviewed,
    e.last_event_update,
    l.last_lab_receipt,
    CASE
        WHEN l.subject_token IS NULL THEN 'awaiting-lab-feed'
        WHEN NOT l.all_labs_reviewed THEN 'lab-review-pending'
        WHEN e.subject_token IS NULL THEN 'no-event-recorded'
        ELSE 'ready-for-safety-review'
    END AS reconciliation_status
FROM scheduled_reviews r
LEFT JOIN event_rollup e
    ON e.subject_token = r.subject_token AND e.visit_id = r.visit_id
LEFT JOIN lab_rollup l
    ON l.subject_token = r.subject_token AND l.visit_id = r.visit_id
ORDER BY r.visit_date, r.subject_token;
```
