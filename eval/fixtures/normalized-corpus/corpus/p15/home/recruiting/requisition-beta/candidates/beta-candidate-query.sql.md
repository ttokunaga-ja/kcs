```sql
-- Atlas Beta の候補者ステージをローカル確認する読み取りクエリ。
WITH active_candidates AS (
  SELECT candidate_alias, current_stage, source_channel, updated_at
  FROM ats_candidate_stage
  WHERE requisition_code = 'atlas-beta'
    AND archived_at IS NULL
)
SELECT current_stage, source_channel, COUNT(*) AS candidate_count
FROM active_candidates
GROUP BY current_stage, source_channel
ORDER BY current_stage, candidate_count DESC;
```
