Northwind Research / Applied Foundations

Personal working notes



Northwind Research / Applied Foundations

Personal working notes



Northwind Research / Applied Foundations

Personal working notes



Northwind Research / Applied Foundations
Personal working notes
Before I Rerun Again
Personal checklist for the next working pass
Prepare the same ground truth
Before repeating the work, I will confirm that the candidate and baseline use the same document preparation
description and the same evaluation harness. I will also preserve the disputed examples as a compact set,
rather than widening the rerun until it becomes difficult to read.
Questions for the team
•
Which examples are meaningful enough to become protocol cases rather than personal notes?
•
What minimum context should accompany a reviewer disagreement in the next packet?
•
Where should we draw the line between a retrieval issue and a document-preparation issue?
Personal disposition
I will keep these observations separate from the formal evaluation export. They are useful for choosing the
next experiment, but they should not become shared evidence until another reviewer can retrace the same
reasoning from the team materials.
3


Northwind Research / Applied Foundations
Personal working notes
Personal Rerun Observations
Cedar encoder / July 2026 / researcher notebook extract
Why I reran the comparison
I repeated a small Cedar comparison after the review thread exposed examples where the model-alpha
candidate felt more coherent in reading order but harder to explain from the exported context alone. My goal
was not to produce a new scorecard. I wanted to see whether the same qualitative pattern survived when I
rebuilt the local evaluation path from the shared inputs.
First pass notes
•
The candidate again favored supporting passages that completed a heading’s intent, which made several
long documents easier to inspect.
•
A few close cases still depended on how the document was segmented before ranking, so I treated those
as preparation questions rather than model conclusions.
•
The model-beta baseline remained a useful control because its ordering made the disputed evidence easy
to identify, even when I preferred the candidate’s result.
What I saved for later
I kept a short list of examples that deserve a fresh pair of eyes. I did not carry over the original chat
commentary, since it would make the next reader too likely to see the same explanation I saw.
1


Northwind Research / Applied Foundations
Personal working notes
What Changed in the Review
Notes from the local reading pass
Document shape mattered
The clearest differences appeared in material with a brief overview followed by dense supporting detail. The
candidate often held the overview and the relevant detail closer together in the ranked list. That looked
promising, but it also made it important to inspect whether the document boundaries were being handled
consistently.
Cases I would not overinterpret
•
Examples where the preferred result followed a formatting cleanup rather than a retrained encoder.
•
Examples that changed after a local cache refresh, because the surrounding retrieval context was not
stable enough for a claim.
•
Examples with ambiguous reviewer intent, where two reasonable passages served different readings of
the same request.
Practical takeaway
The rerun was useful as a debugging aid. It sharpened the questions that should go back to the shared packet,
especially around document segmentation and the evidence reviewers need to justify a close ordering.
2


# Before I Rerun Again

Personal checklist for the next working pass



# Personal Rerun Observations

Cedar encoder / July 2026 / researcher notebook extract



# What Changed in the Review

Notes from the local reading pass



## Document shape mattered

The clearest differences appeared in material with a brief overview followed by dense supporting detail. The candidate often held the overview and the relevant detail closer together in the ranked list. That looked promising, but it also made it important to inspect whether the document boundaries were being handled consistently.



## Prepare the same ground truth

Before repeating the work, I will confirm that the candidate and baseline use the same document preparation description and the same evaluation harness. I will also preserve the disputed examples as a compact set, rather than widening the rerun until it becomes difficult to read.



## Why I reran the comparison

I repeated a small Cedar comparison after the review thread exposed examples where the model-alpha candidate felt more coherent in reading order but harder to explain from the exported context alone. My goal was not to produce a new scorecard. I wanted to see whether the same qualitative pattern survived when I rebuilt the local evaluation path from the shared inputs.



## Questions for the team

- Which examples are meaningful enough to become protocol cases rather than personal notes?
- What minimum context should accompany a reviewer disagreement in the next packet?
- Where should we draw the line between a retrieval issue and a document-preparation issue?



## Cases I would not overinterpret

- Examples where the preferred result followed a formatting cleanup rather than a retrained encoder.
- Examples that changed after a local cache refresh, because the surrounding retrieval context was not stable enough for a claim.
- Examples with ambiguous reviewer intent, where two reasonable passages served different readings of the same request.



## First pass notes

- The candidate again favored supporting passages that completed a heading's intent, which made several long documents easier to inspect.
- A few close cases still depended on how the document was segmented before ranking, so I treated those as preparation questions rather than model conclusions.
- The model-beta baseline remained a useful control because its ordering made the disputed evidence easy to identify, even when I preferred the candidate's result.



## Personal disposition

I will keep these observations separate from the formal evaluation export. They are useful for choosing the next experiment, but they should not become shared evidence until another reviewer can retrace the same reasoning from the team materials.

3

## Practical takeaway

The rerun was useful as a debugging aid. It sharpened the questions that should go back to the shared packet, especially around document segmentation and the evidence reviewers need to justify a close ordering.

2

## What I saved for later

I kept a short list of examples that deserve a fresh pair of eyes. I did not carry over the original chat commentary, since it would make the next reader too likely to see the same explanation I saw.

1