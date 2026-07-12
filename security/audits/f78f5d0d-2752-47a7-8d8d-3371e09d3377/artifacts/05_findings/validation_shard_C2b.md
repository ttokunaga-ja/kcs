# Validation shard C2b closure

| Candidate | Disposition | Survives | Severity | Confidence | Method | Proof |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-023 | reportable | yes | medium | high (0.98) | bounded parser tests+V10 | Gemini POST fully materializes/decompresses JSON with no read/body limit before count and dimension checks |
| KCS-R23-CAND-032 | reportable | yes | medium | high (0.99) | bounded cap test+V5+V10 | scanner knows metadata length, then performs whole-file `fs::read`; configured cap executes only after preview returns |
