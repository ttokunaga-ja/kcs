NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Access Review Reconciliation
Q3 2026 operational handoff for the Tokyo service environment
Owner
Identity Operations with Trust Engineering review | Status: ready for evidence packaging
Purpose: reconcile the access-review population, reviewer attestations, and remediation records before the
quarterly audit package is frozen.
Scope and basis
The reconciliation covers production administration, support escalation, and the delegated service ac-
counts used by Nami Grid’s Tokyo operations. The population was taken from the July identity export
and matched to the review register owned by Identity Operations.
Control activity Evidence retained Review cadence
Entitlement review reviewer decision log and owner roster quarterly
Privileged access check approval trail and session inventory monthly
Leaver reconciliation disablement ticket reference weekly
Reconciliation rule
An account is considered reconciled when the identity export, the reviewer decision, and any resulting
remediation record point to the same owner and access state. Service accounts are checked against
their sponsoring application owner rather than an individual manager.
Internal working reference | 1


NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Evidence Package and Follow-up
What is handed to the GRC evidence coordinator
Package contents
The package contains the signed review export, the reviewer roster, a reconciliation worksheet, and a
compact exception register. Links point to systems of record; the package does not duplicate privileged
session data.
Item Acceptance check Custodian
Review export period and population visible Identity Operations
Reviewer roster manager mapping current People Systems
Exception register ticket references resolvable Trust Engineering
Next operating dates
The next roster refresh is scheduled for early August. Identity Operations will notify Trust Engineering
if a material organizational change affects the reviewer mapping before the next formal review cycle.
Prepared for the internal SOC 2 readiness workstream. Distribution is limited to the evidence coordinator and
the named control owners.
Internal working reference | 3


NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Reconciliation Results
Population comparison and exception handling
Comparison performed
The review register was normalized to remove duplicate aliases and to separate break-glass accounts
from ordinary administrative access. Each remaining record was compared to the July export using
immutable account identifiers, not display names.
Population segment Export Reviewed Outcome
Production administrators 38 38 all decisions linked
Support escalation access 64 64 owner labels normalized
Service accounts 29 29 sponsor evidence attached
Exceptions resolved during the pass
•
Two support aliases were consolidated after a team transfer; the old aliases were removed from the
active review set.
•
One service account had a stale display owner while its application sponsor record was current; the
roster was corrected.
•
A short-lived incident role was matched to its approved incident ticket and retained in the exception
register.
No unresolved mismatch remains in the reviewed population. Follow-up items are documented as normal
operational remediation, not audit exceptions.
Internal working reference | 2


## Access Review Reconciliation

Q3 2026 operational handoff for the Tokyo service environment

Owner Identity Operations with Trust Engineering review | Status: ready for evidence packaging

Purpose: reconcile the access-review population, reviewer attestations, and remediation records before the quarterly audit package is frozen.



## Evidence Package and Follow-up

What is handed to the GRC evidence coordinator



## Reconciliation Results

Population comparison and exception handling



### Comparison performed

The review register was normalized to remove duplicate aliases and to separate break-glass accounts from ordinary administrative access. Each remaining record was compared to the July export using immutable account identifiers, not display names.

|  Population segment | Export | Reviewed | Outcome  |
| --- | --- | --- | --- |
|  Production administrators | 38 | 38 | all decisions linked  |
|  Support escalation access | 64 | 64 | owner labels normalized  |
|  Service accounts | 29 | 29 | sponsor evidence attached  |



### Package contents

The package contains the signed review export, the reviewer roster, a reconciliation worksheet, and a compact exception register. Links point to systems of record; the package does not duplicate privileged session data.

|  Item | Acceptance check | Custodian  |
| --- | --- | --- |
|  Review export | period and population visible | Identity Operations  |
|  Reviewer roster | manager mapping current | People Systems  |
|  Exception register | ticket references resolvable | Trust Engineering  |



### Scope and basis

The reconciliation covers production administration, support escalation, and the delegated service accounts used by Nami Grid's Tokyo operations. The population was taken from the July identity export and matched to the review register owned by Identity Operations.

|  Control activity | Evidence retained | Review cadence  |
| --- | --- | --- |
|  Entitlement review | reviewer decision log and owner roster | quarterly  |
|  Privileged access check | approval trail and session inventory | monthly  |
|  Leaver reconciliation | disablement ticket reference | weekly  |



### Next operating dates

The next roster refresh is scheduled for early August. Identity Operations will notify Trust Engineering if a material organizational change affects the reviewer mapping before the next formal review cycle.

Prepared for the internal SOC 2 readiness workstream. Distribution is limited to the evidence coordinator and the named control owners.

Internal working reference | 3

### Exceptions resolved during the pass

- Two support aliases were consolidated after a team transfer; the old aliases were removed from the active review set.
- One service account had a stale display owner while its application sponsor record was current; the roster was corrected.
- A short-lived incident role was matched to its approved incident ticket and retained in the exception register.

No unresolved mismatch remains in the reviewed population. Follow-up items are documented as normal operational remediation, not audit exceptions.

Internal working reference | 2

### Reconciliation rule

An account is considered reconciled when the identity export, the reviewer decision, and any resulting remediation record point to the same owner and access state. Service accounts are checked against their sponsoring application owner rather than an individual manager.

Internal working reference | 1