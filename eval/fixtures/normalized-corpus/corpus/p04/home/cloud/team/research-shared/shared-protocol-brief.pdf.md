Northwind Research / Applied Foundations

Shared evaluation protocol



Northwind Research / Applied Foundations

Shared evaluation protocol



Northwind Research / Applied Foundations

Shared evaluation protocol



Northwind Research / Applied Foundations
Shared evaluation protocol
Cedar Shared Evaluation Protocol
Applied Foundations / July 2026 / team research brief
Purpose
This protocol gives Applied Foundations a common way to compare the Cedar document-ranking encoder
across experiments. It is designed for the model-alpha candidate and the model-beta baseline, with enough
structure to keep an evaluation discussion reproducible while leaving room for researchers to document genuine
uncertainty.
What belongs in the shared record
•
The prepared document set and a plain description of any exclusions.
•
The evaluation harness context needed to repeat the comparison.
•
A reviewer packet that keeps disputed examples readable without relying on private chat history.
•
A concise note about changes that may affect interpretation, such as document preparation or cache
refreshes.
What stays outside the record
Scratch observations, one-off diagnostic shortcuts, and incomplete reruns can guide an owner toward the next
experiment. They should not be presented as shared evidence until the team can reproduce the relevant
context.
1


Northwind Research / Applied Foundations
Shared evaluation protocol
Close-Out and Handoff
How a review becomes the next experiment
Close a review responsibly
At the end of a session, preserve the examples that explain the team decision and retire examples that were
only temporary debugging aids. Keep the reviewer packet, the preparation description, and the experiment
context together so that a later reader can understand the conclusion without reconstructing the discussion
from memory.
Handoff checklist
•
State the question that the next run is meant to answer.
•
Carry forward only the evidence that remains useful after independent reading.
•
List open interpretation risks without converting them into release claims.
•
Return private observations to their owners until they have been reproduced through this protocol.
Team stance
The protocol favors clear evidence over rapid escalation. A Cedar result is ready for broader internal discussion
when another reviewer can rerun the comparison, read the disputed examples, and reach the same practical
understanding from the shared materials.
3


Northwind Research / Applied Foundations
Shared evaluation protocol
Evaluation Sequence
A repeatable path from preparation to review
Prepare
Confirm that both systems use the same prepared documents and the same evaluation harness. If an input
needs to be refreshed, state why before the comparison begins. The purpose is not to eliminate every
operational change; it is to make each change visible to the reviewer.
Run and read
•
Produce the comparison packet from the shared evaluation slice.
•
Group examples by task family so that like is compared with like.
•
Ask reviewers to explain a disagreement in terms of the evidence they expected to find.
•
Mark examples that require source context instead of forcing a conclusion from a thin export.
Record interpretation
The owner should summarize the pattern, the exceptions, and the follow-up question. A useful record
distinguishes a likely encoder behavior from a likely preparation artifact. It also makes clear when the team
does not yet have enough evidence to choose between the candidate and baseline.
2


# Cedar Shared Evaluation Protocol

Applied Foundations / July 2026 / team research brief



# Close-Out and Handoff

How a review becomes the next experiment



# Evaluation Sequence

A repeatable path from preparation to review



## Close a review responsibly

At the end of a session, preserve the examples that explain the team decision and retire examples that were only temporary debugging aids. Keep the reviewer packet, the preparation description, and the experiment context together so that a later reader can understand the conclusion without reconstructing the discussion from memory.



## Prepare

Confirm that both systems use the same prepared documents and the same evaluation harness. If an input needs to be refreshed, state why before the comparison begins. The purpose is not to eliminate every operational change; it is to make each change visible to the reviewer.



## Purpose

This protocol gives Applied Foundations a common way to compare the Cedar document-ranking encoder across experiments. It is designed for the model-alpha candidate and the model-beta baseline, with enough structure to keep an evaluation discussion reproducible while leaving room for researchers to document genuine uncertainty.



## Run and read

- Produce the comparison packet from the shared evaluation slice.
- Group examples by task family so that like is compared with like.
- Ask reviewers to explain a disagreement in terms of the evidence they expected to find.
- Mark examples that require source context instead of forcing a conclusion from a thin export.



## Handoff checklist

- State the question that the next run is meant to answer.
- Carry forward only the evidence that remains useful after independent reading.
- List open interpretation risks without converting them into release claims.
- Return private observations to their owners until they have been reproduced through this protocol.



## What belongs in the shared record

- The prepared document set and a plain description of any exclusions.
- The evaluation harness context needed to repeat the comparison.
- A reviewer packet that keeps disputed examples readable without relying on private chat history.
- A concise note about changes that may affect interpretation, such as document preparation or cache refreshes.



## Record interpretation

The owner should summarize the pattern, the exceptions, and the follow-up question. A useful record distinguishes a likely encoder behavior from a likely preparation artifact. It also makes clear when the team does not yet have enough evidence to choose between the candidate and baseline.

2

## Team stance

The protocol favors clear evidence over rapid escalation. A Cedar result is ready for broader internal discussion when another reviewer can rerun the comparison, read the disputed examples, and reach the same practical understanding from the shared materials.

3

## What stays outside the record

Scratch observations, one-off diagnostic shortcuts, and incomplete reruns can guide an owner toward the next experiment. They should not be presented as shared evidence until the team can reproduce the relevant context.

1