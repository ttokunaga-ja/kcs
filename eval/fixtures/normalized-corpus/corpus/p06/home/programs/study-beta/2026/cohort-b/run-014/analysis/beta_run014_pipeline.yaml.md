```yaml
run:
  label: run-014
  study: beta
  input_glob: "../raw-exports/*.json"
qc:
  retain_blank_wells: true
  control_recovery_min: 80
  control_recovery_max: 120
outputs:
  normalized_table: "run014_normalized.csv"
  review_note: "run014_review.md"
```
