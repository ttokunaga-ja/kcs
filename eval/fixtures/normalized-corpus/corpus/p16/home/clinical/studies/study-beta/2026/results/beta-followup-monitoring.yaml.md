```yaml
study:
  code: ORCHID-CKD-202
  site: "Asteria Renal Study Unit, Minato Medical Center"
  data_classification: deidentified-training-scenarios-only
reporting:
  timezone: Asia/Tokyo
  owner: beta-study-operations
  review_cadence: business-days
follow_up_schedule:
  - label: baseline
    nominal_day: 0
    required_checks:
      - consent-record
      - screening-completeness
      - contact-preference
  - label: day-28
    nominal_day: 28
    required_checks:
      - visit-confirmation
      - concomitant-medication-update
      - safety-contact-log
  - label: day-56
    nominal_day: 56
    required_checks:
      - visit-confirmation
      - laboratory-receipt-status
      - investigator-review-status
  - label: day-84
    nominal_day: 84
    required_checks:
      - visit-confirmation
      - data-reconciliation
      - safety-review-complete
triage_routes:
  missing-consent-evidence:
    owner: crc-lead
    target: next-business-day
  laboratory-feed-delay:
    owner: central-lab-liaison
    target: same-business-day
  investigator-review-needed:
    owner: investigator-delegate
    target: same-business-day
controls:
  permit_real_participant_data: false
  retain_free_text_identifiers: false
  require_audit_timestamp: true
```
