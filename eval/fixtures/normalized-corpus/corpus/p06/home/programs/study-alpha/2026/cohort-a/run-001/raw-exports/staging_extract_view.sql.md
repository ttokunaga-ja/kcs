```sql
CREATE VIEW assay_run001_staging AS
SELECT source_file, well, sample_id, CAST(cycle AS INTEGER) AS measurement_cycle,
       CAST(signal_au AS REAL) AS signal_au, received_at
FROM vendor_staging
WHERE run_label = 'run-001' AND source_file IS NOT NULL;
```
