```sql
-- Tidepool Study Alpha planning view
SELECT
  s.session_code,
  s.scheduled_at,
  s.moderator,
  s.prototype_build,
  p.segment,
  p.language_preference
FROM research_sessions AS s
JOIN participant_profiles AS p ON p.participant_code = s.participant_code
WHERE s.study_key = 'alpha_activation_weekly_plan'
  AND s.scheduled_at >= DATE '2026-06-15'
  AND s.scheduled_at < DATE '2026-07-11'
  AND s.status IN ('confirmed', 'completed')
ORDER BY s.scheduled_at;

SELECT session_code, follow_up_owner, due_on
FROM research_follow_ups
WHERE study_key = 'alpha_activation_weekly_plan'
  AND state <> 'closed'
ORDER BY due_on;
```
