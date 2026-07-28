```xml
<?xml version="1.0" encoding="UTF-8"?>
<DeidentifiedScenarioBundle xmlns="urn:asteria:renal-study:deidentified-scenario:v1" generatedAt="2026-07-09T14:30:00+09:00">
  <Study code="ORCHID-CKD-201" site="MMC-ARU-01" dataClass="deidentified-training-scenario" cohortPurpose="protocol-dry-run-input" liveSiteStatus="false" />
  <Scenarios>
    <Scenario scenarioId="ALPHA-SYN-021">
      <Profile>
        <AgeBand>50-59</AgeBand>
        <SexAtEnrollment>female</SexAtEnrollment>
        <KidneyDiseaseStage>G3b</KidneyDiseaseStage>
      </Profile>
      <Screening>
        <ConsentState>confirmed</ConsentState>
        <LaboratoryPacket>complete</LaboratoryPacket>
        <InvestigatorReview>ready</InvestigatorReview>
      </Screening>
      <Visits>
        <Visit label="baseline" status="complete" />
        <Visit label="day-28" status="planned" />
      </Visits>
    </Scenario>
    <Scenario scenarioId="ALPHA-SYN-034">
      <Profile>
        <AgeBand>60-69</AgeBand>
        <SexAtEnrollment>male</SexAtEnrollment>
        <KidneyDiseaseStage>G3a</KidneyDiseaseStage>
      </Profile>
      <Screening>
        <ConsentState>confirmed</ConsentState>
        <LaboratoryPacket>pending-receipt</LaboratoryPacket>
        <InvestigatorReview>hold-for-source-check</InvestigatorReview>
      </Screening>
      <Visits>
        <Visit label="baseline" status="not-scheduled" />
      </Visits>
    </Scenario>
    <Scenario scenarioId="ALPHA-SYN-052">
      <Profile>
        <AgeBand>40-49</AgeBand>
        <SexAtEnrollment>female</SexAtEnrollment>
        <KidneyDiseaseStage>G4</KidneyDiseaseStage>
      </Profile>
      <Screening>
        <ConsentState>supplemental-witness-confirmation-pending</ConsentState>
        <LaboratoryPacket>complete</LaboratoryPacket>
        <InvestigatorReview>supplemental-consent-witness-confirmation-pending</InvestigatorReview>
      </Screening>
      <Visits>
        <Visit label="baseline" status="pending-consent" />
      </Visits>
    </Scenario>
  </Scenarios>
  <Provenance>
    <Statement>All records are fictional, de-identified training input scenarios and are not live site status.</Statement>
    <PermittedUse>protocol dry run and data-flow validation</PermittedUse>
  </Provenance>
</DeidentifiedScenarioBundle>
```
