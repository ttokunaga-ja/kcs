# Validation shard B1b

| Candidate | Disposition | Survives | Severity | Confidence | Closure |
|---|---|---|---|---|---|
| KCS-R23-CAND-018 | reportable | yes | medium | high (0.88) | Core snapshot/status checks a regular `DirEntry` before a later following pathname read; live-race reliability was not measured. |
| KCS-R23-CAND-024 | reportable | yes | high | high (0.97) | Existing permissive store stayed 0755 and a snapshot created a 0644 raw copy of a 0600 source in an isolated control. |
| KCS-R23-CAND-027 | reportable | yes | medium | high (0.91) | Scan can hash an outside replacement under a benign name, but practical race reliability was not reproduced, precluding High. |
