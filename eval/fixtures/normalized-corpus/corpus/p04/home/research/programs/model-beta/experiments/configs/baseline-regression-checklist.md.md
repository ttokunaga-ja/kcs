# Robust baseline regression checklist

Model-beta is the control package for the Cedar July review. It should remain boring, reproducible, and easy to restore.



## Before a replay

- Confirm the document collection revision and tokenizer checksum.
- Verify that duplicate suppression is enabled.
- Compare the judge-set manifest with the last accepted baseline package.
- Store the run summary beside the review bundle.



## Stop conditions

Pause the replay if the collection revision changes mid-run, if the evaluator cannot load the relevance slice, or if the output contains an unknown document identifier.
