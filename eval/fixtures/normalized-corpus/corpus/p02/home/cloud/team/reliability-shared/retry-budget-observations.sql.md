```sql
-- Review retry behavior around the Atlas Checkout gateway release.
WITH request_window AS (
  SELECT
    date_trunc('minute', started_at) AS minute_bucket,
    region,
    retry_count,
    outcome,
    elapsed_ms
  FROM checkout_request_attempts
  WHERE started_at >= TIMESTAMPTZ '2026-07-13 13:00:00+00'
    AND started_at < TIMESTAMPTZ '2026-07-13 16:00:00+00'
    AND service = 'atlas-checkout'
),
by_region AS (
  SELECT
    minute_bucket,
    region,
    count(*) AS attempts,
    count(*) FILTER (WHERE retry_count > 0) AS retried_attempts,
    count(*) FILTER (WHERE outcome = 'error') AS failed_attempts,
    percentile_cont(0.95) WITHIN GROUP (ORDER BY elapsed_ms) AS p95_elapsed_ms
  FROM request_window
  GROUP BY minute_bucket, region
)
SELECT
  minute_bucket,
  region,
  attempts,
  round(retried_attempts::numeric / nullif(attempts, 0), 4) AS retry_ratio,
  round(failed_attempts::numeric / nullif(attempts, 0), 4) AS failure_ratio,
  p95_elapsed_ms
FROM by_region
ORDER BY minute_bucket, region;
```
