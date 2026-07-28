```sql
WITH duplicate_samples AS (
    SELECT sample_id, COUNT(*) AS occurrences
    FROM sample_manifest
    WHERE study_code = 'ALPHA'
    GROUP BY sample_id
    HAVING COUNT(*) > 1
)
SELECT m.sample_id, m.collection_date, m.storage_location,
       COALESCE(d.occurrences, 1) AS manifest_occurrences
FROM sample_manifest AS m
LEFT JOIN duplicate_samples AS d ON d.sample_id = m.sample_id
WHERE m.study_code = 'ALPHA'
ORDER BY m.collection_date, m.sample_id;
```
