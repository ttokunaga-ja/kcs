# Validation shard A2a

| Candidate | Disposition | Survives | Severity | Confidence | Closure |
|---|---|---|---|---|---|
| KCS-R23-CAND-026 | reportable | yes | medium | high (0.90) | Persistent approval omits destination/profile binding, but adversarial reachability is deployment-dependent because no lower-trust launcher/configuration path was established. |
| KCS-R23-CAND-038 | reportable | yes | high | high (0.96) | Accepted markdown target fields are discarded, and the retained credential plus document are sent through the fixed Mistral client. |
| KCS-R23-CAND-039 | reportable | yes | high | high (0.97) | Accepted embedding target/model fields are ignored, and declared authentication activates the fixed Gemini client for input text. |
