```rs
//! Normalize metadata attached to a Cedar review bundle.

pub fn review_label(package: &str, collection_revision: &str) -> String {
    format!("{}@{}", package.trim(), collection_revision.trim())
}

pub fn has_required_fields(package: &str, judge_set: &str) -> bool {
    !package.trim().is_empty() && !judge_set.trim().is_empty()
}
```
