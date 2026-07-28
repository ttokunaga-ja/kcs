```rs
//! Personal note index helpers used during Cedar experiment review.

pub fn normalize_heading(value: &str) -> String {
    value
        .trim()
        .to_lowercase()
        .split_whitespace()
        .collect::<Vec<_>>()
        .join("-")
}

pub fn is_review_note(path: &str) -> bool {
    path.ends_with(".md") && !path.contains("scratch")
}
```
