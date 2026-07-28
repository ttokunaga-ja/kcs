```rs
use std::collections::BTreeSet;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Macro {
    pub name: String,
    pub locale: String,
    pub body: String,
}

#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord)]
pub enum Finding {
    MissingCustomerName,
    MissingCaseNumber,
    UnsupportedPromise(String),
    UnapprovedClosing,
}

const PROHIBITED_PROMISES: [&str; 3] = [
    "we guarantee",
    "will be fixed today",
    "within one hour",
];

const APPROVED_CLOSINGS: [&str; 2] = [
    "Thank you for your patience.",
    "Regards,\nHarborline Workspace Support",
];

pub fn lint(macro_reply: &Macro) -> BTreeSet<Finding> {
    let mut findings = BTreeSet::new();
    let body_lower = macro_reply.body.to_ascii_lowercase();

    if !macro_reply.body.contains("{{customer_name}}") {
        findings.insert(Finding::MissingCustomerName);
    }
    if !macro_reply.body.contains("{{case_number}}") {
        findings.insert(Finding::MissingCaseNumber);
    }

    for phrase in PROHIBITED_PROMISES {
        if body_lower.contains(phrase) {
            findings.insert(Finding::UnsupportedPromise(phrase.to_string()));
        }
    }

    if !APPROVED_CLOSINGS
        .iter()
        .any(|closing| macro_reply.body.ends_with(closing))
    {
        findings.insert(Finding::UnapprovedClosing);
    }

    findings
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn accepts_a_reviewed_status_update() {
        let reply = Macro {
            name: "investigation-update-en".into(),
            locale: "en".into(),
            body: "Hello {{customer_name}},\n\nWe are reviewing case {{case_number}} and will send the next update after the engineering review.\n\nThank you for your patience.".into(),
        };

        assert!(lint(&reply).is_empty());
    }

    #[test]
    fn flags_an_unapproved_promise() {
        let reply = Macro {
            name: "risky-update-en".into(),
            locale: "en".into(),
            body: "Hello {{customer_name}}, case {{case_number}} will be fixed today.".into(),
        };

        assert!(lint(&reply).contains(&Finding::UnsupportedPromise(
            "will be fixed today".into()
        )));
    }
}
```
