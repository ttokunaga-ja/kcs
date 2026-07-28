# Candidate sweep parameter notes



## Intent

This sweep narrows the Cedar candidate search around the existing document-ranking encoder. Model-alpha keeps the production tokenizer and index schema so the comparison with model-beta remains interpretable.



## Working ranges

| Parameter | Current range | Reason |
|---|---|---|
| learning rate | 2.0e-5 to 3.0e-5 | keeps early updates smooth |
| effective batch | 160 to 224 | fits the replay workers |
| warmup fraction | 0.04 to 0.08 | avoids a sharp first-epoch jump |
| hard-negative mix | 0.28 to 0.40 | emphasizes confusing near-matches |



## Guardrails

Do not alter document normalization in this sweep. Each run must record the collection revision, judge-set revision, and tokenizer checksum before it enters the review queue.
