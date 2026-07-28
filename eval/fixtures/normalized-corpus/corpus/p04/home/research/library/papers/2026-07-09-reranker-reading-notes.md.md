# Reading notes: query-aware reranking for Cedar

Reader: Applied Foundations
Captured: July 9, 2026



## Useful ideas

- Late interaction remains practical when the document encoder is cached by collection revision.
- A small margin loss is easier to diagnose than a large blended objective when editorial judgments disagree.
- Document-age features should be audited separately from lexical coverage; they can mask stale-content failures.



## Cedar implications

The next candidate sweep should keep the encoder interface unchanged and isolate only the reranker margin. Record the collection revision beside every review bundle so paper notes can be tied back to a reproducible corpus state.



## Follow-up

Review the appendix on negative selection before changing the in-batch sampling policy.
