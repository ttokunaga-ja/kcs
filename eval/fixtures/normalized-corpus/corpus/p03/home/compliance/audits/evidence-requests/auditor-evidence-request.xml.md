```xml
<?xml version="1.0" encoding="UTF-8"?>
<evidenceRequest xmlns="https://nami-grid.example/schema/audit-request/v1">
  <requestId>AR-2026-Q3-014</requestId>
  <engagement>SOC 2 readiness review</engagement>
  <requestedBy>External assurance team</requestedBy>
  <receivedAt>2026-07-14T10:18:00+09:00</receivedAt>
  <scope>
    <service>Operator Hub</service>
    <service>Grid Console</service>
    <periodStart>2026-04-01</periodStart>
    <periodEnd>2026-06-30</periodEnd>
  </scope>
  <items>
    <item sequence="1">
      <control>CC6.1</control>
      <description>Provide the access-review population and reviewer completion record for the selected period.</description>
      <preferredFormat>CSV with accompanying procedure note</preferredFormat>
      <owner>Trust Engineering</owner>
    </item>
    <item sequence="2">
      <control>CC7.2</control>
      <description>Provide the incident triage sample and the escalation runbook revision history.</description>
      <preferredFormat>PDF or exported ticket record</preferredFormat>
      <owner>Security Operations</owner>
    </item>
  </items>
  <handling>
    <deliveryChannel>auditor portal</deliveryChannel>
    <notes>Exclude customer payloads and workforce personal data from exported attachments.</notes>
  </handling>
</evidenceRequest>
```
