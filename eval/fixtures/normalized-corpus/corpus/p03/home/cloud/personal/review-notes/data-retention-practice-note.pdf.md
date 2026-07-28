NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING

Q3 2026 SOC 2 readiness



NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Data Retention Practice Note
Operational evidence handling for the Tokyo service environment
Audience
Trust Engineering, GRC, and control owners | July 2026 working note
This note describes how teams keep operational evidence available for review while respecting the retention
settings of the underlying systems. It does not replace a system-specific schedule.
Working principle
Evidence is retained in the system of record whenever practical. Readiness materials should iden-
tify the source, the relevant period, and the reviewer without creating uncontrolled copies of sensitive
operational data.
Evidence type Normal practice Primary owner
Access review output retain the approved export and decision trail Identity Opera-
tions
Change approval record retain ticket reference and approval history Platform Reliabil-
ity
Incident follow-up retain summary and action tracking Security Re-
sponse
Why summaries are used
Summaries make it possible to show a reviewer what was checked, by whom, and for which period.
They should point back to the source record rather than contain secrets, full event payloads, or unnec-
essary personal information.
Internal working reference | 1


NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Responsibilities and Escalation
A practical boundary between evidence work and data governance
Responsibility split
The system owner manages the underlying record and its retention configuration. The control owner
confirms that the record supports the control activity. Trust Engineering advises on evidence quality
and tracks readiness follow-up; it does not take ownership of production records.
Role Responsibility
System owner source availability and normal retention settings
Control owner evidence relevance and operating conclusion
Trust Engineering readiness coordination and evidence guidance
GRC coordinator package status and reviewer communication
Escalation triggers
Escalate when a source record is unexpectedly unavailable, a material evidence summary no longer
matches its source, or a planned system change affects how a reviewer can validate the activity. The
escalation should state the operational impact and the responsible team, not speculate about a control
conclusion.
This note supports the Q3 readiness cycle and should be revisited when the Tokyo operating model or source
systems materially change.
Internal working reference | 3


NAMI GRID | TRUST ENGINEERING
Q3 2026 SOC 2 readiness
Review and Refresh Cycle
Keeping evidence current without duplicating source data
Monthly operating check
Control owners confirm that the source records for their evidence remain reachable and that the normal
retention setting is still understood. The readiness coordinator records only the confirmation outcome
and any follow-up owner.
When a record is updated
•
Preserve the relationship between an earlier evidence reference and its successor.
•
Note the reason for the update, such as a corrected extract or revised ownership.
•
Recheck the evidence summary if its stated period or conclusion is affected.
•
Keep restricted source data in its approved system rather than placing it in a broad workspace.
Review question Expected answer
Can the source be reached? A named team can retrieve the record under normal access rules.
Is the period clear? Start and end of the reviewed period are visible or documented.
Is the summary sufficient? A reviewer can understand the activity without seeing unnecessary raw data.
If a source cannot be retrieved through its normal route, raise an operational follow-up rather than creating an
unmanaged copy.
Internal working reference | 2


## Data Retention Practice Note

Operational evidence handling for the Tokyo service environment

Audience Trust Engineering, GRC, and control owners | July 2026 working note

This note describes how teams keep operational evidence available for review while respecting the retention settings of the underlying systems. It does not replace a system-specific schedule.



## Responsibilities and Escalation

A practical boundary between evidence work and data governance



## Review and Refresh Cycle

Keeping evidence current without duplicating source data



### Monthly operating check

Control owners confirm that the source records for their evidence remain reachable and that the normal retention setting is still understood. The readiness coordinator records only the confirmation outcome and any follow-up owner.



### Responsibility split

The system owner manages the underlying record and its retention configuration. The control owner confirms that the record supports the control activity. Trust Engineering advises on evidence quality and tracks readiness follow-up; it does not take ownership of production records.

|  Role | Responsibility  |
| --- | --- |
|  System owner | source availability and normal retention settings  |
|  Control owner | evidence relevance and operating conclusion  |
|  Trust Engineering | readiness coordination and evidence guidance  |
|  GRC coordinator | package status and reviewer communication  |



### When a record is updated

- Preserve the relationship between an earlier evidence reference and its successor.
- Note the reason for the update, such as a corrected extract or revised ownership.
- Recheck the evidence summary if its stated period or conclusion is affected.
- Keep restricted source data in its approved system rather than placing it in a broad workspace.

|  Review question | Expected answer  |
| --- | --- |
|  Can the source be reached? | A named team can retrieve the record under normal access rules.  |
|  Is the period clear? | Start and end of the reviewed period are visible or documented.  |
|  Is the summary sufficient? | A reviewer can understand the activity without seeing unnecessary raw data.  |

If a source cannot be retrieved through its normal route, raise an operational follow-up rather than creating an unmanaged copy.

Internal working reference | 2

### Working principle

Evidence is retained in the system of record whenever practical. Readiness materials should identify the source, the relevant period, and the reviewer without creating uncontrolled copies of sensitive operational data.

|  Evidence type | Normal practice | Primary owner  |
| --- | --- | --- |
|  Access review output | retain the approved export and decision trail | Identity Operations  |
|  Change approval record | retain ticket reference and approval history | Platform Reliability  |
|  Incident follow-up | retain summary and action tracking | Security Response  |



### Escalation triggers

Escalate when a source record is unexpectedly unavailable, a material evidence summary no longer matches its source, or a planned system change affects how a reviewer can validate the activity. The escalation should state the operational impact and the responsible team, not speculate about a control conclusion.

This note supports the Q3 readiness cycle and should be revisited when the Tokyo operating model or source systems materially change.

Internal working reference | 3

### Why summaries are used

Summaries make it possible to show a reviewer what was checked, by whom, and for which period. They should point back to the source record rather than contain secrets, full event payloads, or unnecessary personal information.

Internal working reference | 1