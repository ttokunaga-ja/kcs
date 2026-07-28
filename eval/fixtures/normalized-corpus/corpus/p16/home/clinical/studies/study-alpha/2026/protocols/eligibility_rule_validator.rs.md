```rs
//! Screening-rule checks used during the ORCHID-CKD-201 protocol dry run.
//!
//! This module validates a de-identified screening record before it is placed
//! in the coordinator review queue. The clinical source documents remain the
//! authoritative record; this utility only makes missing fields visible.

use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ScreeningRecord {
    pub subject_token: String,
    pub age_years: u8,
    pub egfr_ml_min_1_73m2: u8,
    pub consent_confirmed: bool,
    pub chronic_kidney_disease_confirmed: bool,
    pub dialysis_at_screening: bool,
    pub required_labs_complete: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct EligibilityIssue {
    pub field: &'static str,
    pub message: String,
}

#[derive(Debug, Clone)]
pub struct RuleSet {
    pub minimum_age: u8,
    pub maximum_age: u8,
    pub minimum_egfr: u8,
    pub maximum_egfr: u8,
}

impl RuleSet {
    pub fn alpha_2026_07() -> Self {
        Self {
            minimum_age: 20,
            maximum_age: 80,
            minimum_egfr: 25,
            maximum_egfr: 75,
        }
    }
}

pub fn validate(record: &ScreeningRecord, rules: &RuleSet) -> Vec<EligibilityIssue> {
    let mut issues = Vec::new();

    if record.subject_token.trim().is_empty() {
        issues.push(issue("subject_token", "screening token is required"));
    }
    if !(rules.minimum_age..=rules.maximum_age).contains(&record.age_years) {
        issues.push(issue("age_years", "age is outside the screening range"));
    }
    if !(rules.minimum_egfr..=rules.maximum_egfr).contains(&record.egfr_ml_min_1_73m2) {
        issues.push(issue(
            "egfr_ml_min_1_73m2",
            "eGFR is outside the screening range",
        ));
    }
    if !record.consent_confirmed {
        issues.push(issue(
            "consent_confirmed",
            "consent confirmation is pending",
        ));
    }
    if !record.chronic_kidney_disease_confirmed {
        issues.push(issue(
            "chronic_kidney_disease_confirmed",
            "source documentation for CKD diagnosis is pending",
        ));
    }
    if record.dialysis_at_screening {
        issues.push(issue(
            "dialysis_at_screening",
            "requires investigator review",
        ));
    }
    if !record.required_labs_complete {
        issues.push(issue(
            "required_labs_complete",
            "required screening labs are incomplete",
        ));
    }

    issues
}

pub fn summarize(issues: &[EligibilityIssue]) -> BTreeMap<&'static str, usize> {
    let mut by_field = BTreeMap::new();
    for issue in issues {
        *by_field.entry(issue.field).or_insert(0) += 1;
    }
    by_field
}

fn issue(field: &'static str, message: impl Into<String>) -> EligibilityIssue {
    EligibilityIssue {
        field,
        message: message.into(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn complete_record_has_no_issues() {
        let record = ScreeningRecord {
            subject_token: "ALPHA-SYN-021".into(),
            age_years: 56,
            egfr_ml_min_1_73m2: 41,
            consent_confirmed: true,
            chronic_kidney_disease_confirmed: true,
            dialysis_at_screening: false,
            required_labs_complete: true,
        };

        assert!(validate(&record, &RuleSet::alpha_2026_07()).is_empty());
    }
}
```
