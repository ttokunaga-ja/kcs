# Validation shard C2a closure

| Candidate | Disposition | Survives | Severity | Confidence | Method | Proof |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-020 | reportable | yes | medium | high (0.96) | V5+V10 | OCR POST fully materializes and expands response before unbounded page/image persistence; outbound request-size subclaim narrowed by live input cap |
| KCS-R23-CAND-022 | reportable | yes | medium | high (0.98) | bounded config test+V10 | default model alias reaches unbounded `into_json`; configured timeout is explicitly unwired and ureq has no read/overall timeout |
