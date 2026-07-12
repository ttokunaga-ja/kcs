# Validation shard C1 closure

| Candidate | Disposition | Survives | Severity | Confidence | Method | Proof |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-003 | reportable | yes | high | high (0.99) | V1+V5+V10 | bounded non-finite/zero-vector SQLite probe |
| KCS-R23-CAND-004 | reportable | yes | medium | high (0.97) | V1+V5+V10 | checked-vs-unchecked overflow control and exact trace |
| KCS-R23-CAND-005 | reportable | yes | high | high (0.99) | V1+V10 | isolated Unicode ignore preview |
| KCS-R23-CAND-006 | reportable | yes | high | high (0.99) | V1+V5+V10 | bounded marker-to-unit growth probe |
| KCS-R23-CAND-007 | reportable | yes | high | high (0.99) | V1+V5+V10 | bounded LCS growth and exact allocation equation |
| KCS-R23-CAND-017 | reportable | yes | medium | high (0.99) | V1+V5+V10 | bounded exponential recurrence/timing probe |

