Northwind Research / Applied Foundations

Evaluation export



Northwind Research / Applied Foundations

Evaluation export



Northwind Research / Applied Foundations

Evaluation export



Northwind Research / Applied Foundations
Evaluation export
Cedar Evaluation Export
Applied Foundations / July 2026 / internal review packet
Purpose of this export
This packet accompanies the July review of the Cedar document-ranking encoder. It places the model-alpha
candidate beside the model-beta baseline using the shared evaluation slice and preserves the context needed
to read the resulting ordering decisions. The export is intentionally narrow: it supports discussion of retrieval
behavior rather than a broad product claim.
Included material
•
Curated document groups that represent short references, long-form guidance, and mixed heading
structures.
•
Reviewer annotations that explain why an ordering was accepted, questioned, or held for another pass.
•
The evaluation harness context needed to distinguish a ranking change from an export or annotation
change.
Reading notes
The candidate should be read as a working system. Where it improves the placement of supporting passages,
reviewers should still inspect the nearby top results for omitted context. Where the baseline remains easier to
justify, the packet records the example so that the next experiment can begin from a concrete disagreement
rather than from a summary impression.
Current review stance
Applied Foundations is using this export to decide which examples deserve deeper inspection. The material
does not settle whether the candidate is ready for wider use; it identifies the evidence that needs to travel into
the next shared review.
1


Northwind Research / Applied Foundations
Evaluation export
Handoff Notes
What should travel with the next review cycle
Keep the review reproducible
The next owner should receive the same evaluation harness context, the document-preparation description,
and the reviewer packet. If an artifact needs to be regenerated, note the reason in the experiment record
before replacing it. That small discipline prevents a later comparison from inheriting an invisible change.
Recommended next actions
•
Refresh the shared evaluation packet only after the candidate and baseline have been run through the
same prepared document set.
•
Ask an independent reviewer to read the disputed examples without the original discussion thread.
•
Carry forward only the examples that explain a general ranking question, not one-off formatting noise.
•
Summarize unresolved items as questions for the protocol review rather than as conclusions.
Disposition
The export remains an internal working artifact. It is suitable for review, annotation, and rerun planning; any
broader claim about the Cedar encoder should wait for the team to complete the shared interpretation step.
3


Northwind Research / Applied Foundations
Evaluation export
Reading the Export
Interpretation guidance for reviewers
Compare like with like
Read each example within its task family before comparing it across the packet. A strong result on concise
reference material does not automatically explain behavior on policy text or multi-section technical notes.
The shared slice is designed to make that distinction visible without turning the review into a collection of
unrelated anecdotes.
What reviewers should flag
•
A result whose relevance depends on a heading but leaves the supporting passage too low to be useful.
•
A shift that appears to follow document preparation rather than encoder behavior.
•
A disagreement that cannot be resolved from the exported context and needs the original evaluation
record.
•
A repeatable failure mode that would make a useful addition to the next review packet.
How to record a disagreement
Use a plain explanation of the task, the expected evidence, and the reason the current ordering is difficult
to defend. A void labeling an example as a regression before the reviewer has checked the matching baseline
context. This keeps the thread useful for the research owner and for colleagues who did not participate in the
first pass.
Limits of the packet
This export does not include private rerun notes, experimental shortcuts, or provisional interpretations. Those
items can guide follow-up work, but they should not be treated as shared evidence until they are reproduced
within the team protocol.
2


# Cedar Evaluation Export

Applied Foundations / July 2026 / internal review packet



# Reading the Export

Interpretation guidance for reviewers



## Handoff Notes

What should travel with the next review cycle



## Compare like with like

Read each example within its task family before comparing it across the packet. A strong result on concise reference material does not automatically explain behavior on policy text or multi-section technical notes. The shared slice is designed to make that distinction visible without turning the review into a collection of unrelated anecdotes.



### Keep the review reproducible

The next owner should receive the same evaluation harness context, the document-preparation description, and the reviewer packet. If an artifact needs to be regenerated, note the reason in the experiment record before replacing it. That small discipline prevents a later comparison from inheriting an invisible change.



## Purpose of this export

This packet accompanies the July review of the Cedar document-ranking encoder. It places the model-alpha candidate beside the model-beta baseline using the shared evaluation slice and preserves the context needed to read the resulting ordering decisions. The export is intentionally narrow: it supports discussion of retrieval behavior rather than a broad product claim.



### Recommended next actions

- Refresh the shared evaluation packet only after the candidate and baseline have been run through the same prepared document set.
- Ask an independent reviewer to read the disputed examples without the original discussion thread.
- Carry forward only the examples that explain a general ranking question, not one-off formatting noise.
- Summarize unresolved items as questions for the protocol review rather than as conclusions.



## What reviewers should flag

- A result whose relevance depends on a heading but leaves the supporting passage too low to be useful.
- A shift that appears to follow document preparation rather than encoder behavior.
- A disagreement that cannot be resolved from the exported context and needs the original evaluation record.
- A repeatable failure mode that would make a useful addition to the next review packet.



## Included material

- Curated document groups that represent short references, long-form guidance, and mixed heading structures.
- Reviewer annotations that explain why an ordering was accepted, questioned, or held for another pass.
- The evaluation harness context needed to distinguish a ranking change from an export or annotation change.



## Reading notes

The candidate should be read as a working system. Where it improves the placement of supporting passages, reviewers should still inspect the nearby top results for omitted context. Where the baseline remains easier to justify, the packet records the example so that the next experiment can begin from a concrete disagreement rather than from a summary impression.



## How to record a disagreement

Use a plain explanation of the task, the expected evidence, and the reason the current ordering is difficult to defend. Avoid labeling an example as a regression before the reviewer has checked the matching baseline context. This keeps the thread useful for the research owner and for colleagues who did not participate in the first pass.



### Disposition

The export remains an internal working artifact. It is suitable for review, annotation, and rerun planning; any broader claim about the Cedar encoder should wait for the team to complete the shared interpretation step.

3

## Current review stance

Applied Foundations is using this export to decide which examples deserve deeper inspection. The material does not settle whether the candidate is ready for wider use; it identifies the evidence that needs to travel into the next shared review.

1

## Limits of the packet

This export does not include private rerun notes, experimental shortcuts, or provisional interpretations. Those items can guide follow-up work, but they should not be treated as shared evidence until they are reproduced within the team protocol.

2