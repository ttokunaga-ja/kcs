```yaml
version: 1.2
engagement: route-operations-reset
codes:
  dispatch_freeze:
    definition: Change to a route plan after the agreed morning cut-off
    examples:
      - late vehicle substitution
      - driver absence reported after plan issue
  handoff_visibility:
    definition: Missing or delayed acknowledgement between operational roles
    examples:
      - maintenance status not visible to dispatch
      - supervisor escalation not logged
  customer_impact:
    definition: Change likely to affect planned arrival or service window
review_rules:
  - Apply one primary code and optional secondary code.
  - Preserve the respondent's wording in the evidence field.
  - Escalate safety observations to the engagement lead on the same day.
```
