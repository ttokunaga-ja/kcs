```rs
//! Parse the compact exception-review notes copied from the operator review queue.
//! The parser deliberately keeps the original wording in `rationale`; reviewers use it
//! when reconciling access evidence with the Nami Grid service owner register.

use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ExceptionReview {
    pub ticket: String,
    pub service: String,
    pub owner: String,
    pub disposition: String,
    pub rationale: String,
}

pub fn parse_note(input: &str) -> Result<ExceptionReview, String> {
    let values = input
        .lines()
        .filter_map(|line| line.split_once(':'))
        .map(|(key, value)| (key.trim().to_ascii_lowercase(), value.trim().to_owned()))
        .collect::<BTreeMap<_, _>>();

    let required = |key: &str| {
        values
            .get(key)
            .cloned()
            .filter(|value| !value.is_empty())
            .ok_or_else(|| format!("missing {key} in exception note"))
    };

    let disposition = required("disposition")?;
    if !matches!(disposition.as_str(), "accepted" | "remediate" | "not-an-exception") {
        return Err(format!("unsupported disposition: {disposition}"));
    }

    Ok(ExceptionReview {
        ticket: required("ticket")?,
        service: required("service")?,
        owner: required("owner")?,
        disposition,
        rationale: required("rationale")?,
    })
}

pub fn reviewer_summary(review: &ExceptionReview) -> String {
    format!(
        "{} / {} — {} ({})",
        review.ticket, review.service, review.disposition, review.owner
    )
}

#[cfg(test)]
mod tests {
    use super::parse_note;

    #[test]
    fn accepts_a_complete_review_note() {
        let note = "ticket: GRC-418\nservice: operator-hub\nowner: trust-engineering\ndisposition: remediate\nrationale: SSO group changed during the review window";
        assert_eq!(parse_note(note).unwrap().service, "operator-hub");
    }
}
```
