# Cedar experiment comparison

This note compares the candidate package with the durable control used by Applied Foundations during the July review.

| Package | Role | Evaluation slice | nDCG@10 | Disposition |
|---|---|---|---:|---|
| model-alpha | candidate | editorial holdout | 0.884 | keep under review |
| model-beta | robust baseline | editorial holdout | 0.879 | retain as control |



## Reading of the comparison

The candidate has a small gain on the editorial holdout, but the gain is uneven across long-form technical pages. The baseline is still preferred for unattended replays because its document-age behavior is less variable.



## Decision

Continue error analysis on the candidate and publish the delta table with the next lab update. Do not promote either package from this comparison alone.
