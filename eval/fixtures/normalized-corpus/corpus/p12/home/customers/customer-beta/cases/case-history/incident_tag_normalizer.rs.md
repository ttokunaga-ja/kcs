```rs
use std::collections::BTreeSet;

/// Convert support-facing aliases into tags that can be compared across incident notes.
pub fn normalize_incident_tags<I, S>(raw_tags: I) -> Vec<String>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    let mut normalized = BTreeSet::new();

    for raw in raw_tags {
        let cleaned = raw
            .as_ref()
            .trim()
            .to_ascii_lowercase()
            .replace('_', "-")
            .replace(' ', "-");

        if cleaned.is_empty() {
            continue;
        }

        normalized.insert(canonical_tag(&cleaned).to_owned());
    }

    normalized.into_iter().collect()
}

fn canonical_tag(tag: &str) -> &str {
    match tag {
        "permission" | "permissions" | "access" => "access-control",
        "push" | "push-notification" | "mobile-notification" => "notification",
        "audit" | "audit-log" | "audit-logs" => "audit-log",
        "csv" | "export" | "data-export" => "export",
        "integration" | "webhook" | "api" => "integration",
        _ => tag,
    }
}
```
