# Atlas Checkout gateway event retrospective

**Review date:** 2026-07-15
**Incident:** INC-2026-0713
**Facilitator:** Reliability Engineering



## What happened

During a controlled production release, a gateway header-normalization rule led to uneven upstream selection in one region. The release was held, the rule was disabled, and new gateway pods were brought into service. Checkout availability remained within the customer-impact objective, although the team spent too long correlating the edge and upstream panels.



## What helped

- The change owner and the on-call engineer joined the same incident channel immediately.
- The canary stages limited the affected traffic share.
- Existing pod-drain automation made the reversal predictable.



## What needs improvement

| Area | Observation | Follow-up |
| --- | --- | --- |
| Detection | The regional route signal was not part of the standard canary view. | Add a pre-stage comparison panel. |
| Paging | Route skew notified Reliability Engineering but not Checkout On-call. | Update the alert contract. |
| Operations | The drain path had not been rehearsed recently. | Run a staging exercise. |



## Closing note

The next release should begin only after the revised dashboard and paging changes have been reviewed by both teams.
