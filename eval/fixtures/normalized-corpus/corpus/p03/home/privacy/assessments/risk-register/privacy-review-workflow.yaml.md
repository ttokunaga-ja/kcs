```yaml
workflow: privacy-evidence-review
version: 2026.07
owner: privacy-office
applies_to:
  - audit-evidence-exports
  - vendor-attestations
stages:
  - name: intake
    required_fields: [source_system, business_purpose, data_categories]
    reviewer_group: vendor-risk
  - name: minimization
    checks:
      - remove_direct_identifiers
      - confirm_export_columns
      - record_redaction_method
    reviewer_group: privacy-office
  - name: release-review
    required_approvers: 2
    reviewer_group: trust-engineering
exceptions:
  require_ticket: true
  permitted_reasons:
    - legal_request
    - security_investigation
    - auditor_clarification
logging:
  event_stream: privacy-risk-register-events
  include_payload_values: false
```
