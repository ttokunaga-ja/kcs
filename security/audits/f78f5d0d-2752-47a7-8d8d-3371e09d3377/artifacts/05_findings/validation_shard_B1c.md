# Validation shard B1c

| Candidate | Disposition | Survives | Severity | Confidence | Closure |
|---|---|---|---|---|---|
| KCS-R23-CAND-028 | reportable | yes | medium | high (0.94) | The executor discards checked bytes, but the last-check-to-send race was not reproduced, precluding High. |
| KCS-R23-CAND-029 | reportable | yes | medium | high (0.92) | Deterministic normalization rereads a mutable path, but practical replacement-race reliability was not reproduced, precluding High. |
