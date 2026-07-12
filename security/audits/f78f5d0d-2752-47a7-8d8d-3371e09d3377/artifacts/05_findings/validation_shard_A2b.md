# Validation shard A2b

| Candidate | Disposition | Survives | Severity | Confidence | Closure |
|---|---|---|---|---|---|
| KCS-R23-CAND-040 | reportable | yes | high | high (0.96) | Locked `ureq` redirect handling retains `x-goog-api-key` when an accepted origin returns a cross-origin 301/302/303. |
| KCS-R23-CAND-064 | reportable | yes | medium | high (0.93) | Batch resume/retry can mutate tasks and execute adapters while `tool-lock.json` is malformed, although the existing validator would not detect a well-formed config mismatch. |
| KCS-R23-CAND-067 | reportable | yes | high | high (0.97) | A normally persisted unchanged OCR task is uploaded after its path becomes currently ignored because batch never rebuilds scan authorization. |
