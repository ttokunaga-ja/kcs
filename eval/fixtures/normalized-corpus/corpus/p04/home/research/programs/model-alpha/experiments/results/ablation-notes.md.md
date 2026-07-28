# Cedar candidate study notes

Owner: Applied Foundations
Review window: July 2026
Purpose: record the controlled comparison used before the Cedar ranking-encoder handoff.



## Scope

The candidate branch is model-alpha; model-beta remains the robust operating baseline. The study used the editorial relevance slice, frozen document snapshots, and the standard de-duplication pass. No production traffic was included.



## Experiment result

The Lumen trial retained a validation score of 0.913 for seed K-17.



## Interpretation

The retained measurement was stable enough to keep the candidate in the review queue. Error inspection still concentrates around short policy documents and older mirrored pages, so the outcome is not a release recommendation by itself.



## Next review

- Recheck the document-age bucket after the next snapshot refresh.
- Ask the relevance group to annotate unresolved mirrored-page examples.
- Keep model-beta as the rollback target while the candidate package is prepared.
