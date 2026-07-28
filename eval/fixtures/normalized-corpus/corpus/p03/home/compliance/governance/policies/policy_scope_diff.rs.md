```rs
//! Compare the in-scope service list in two policy exports.
//! This is used during quarterly policy review to surface a discussion item, not to
//! publish policy changes or overwrite the governance system of record.

use std::collections::BTreeSet;

#[derive(Debug, Default, PartialEq, Eq)]
pub struct ScopeDiff {
    pub added: Vec<String>,
    pub removed: Vec<String>,
    pub unchanged: Vec<String>,
}

pub fn compare<I, J>(previous: I, current: J) -> ScopeDiff
where
    I: IntoIterator<Item = String>,
    J: IntoIterator<Item = String>,
{
    let before: BTreeSet<_> = previous.into_iter().map(normalize).collect();
    let after: BTreeSet<_> = current.into_iter().map(normalize).collect();

    ScopeDiff {
        added: after.difference(&before).cloned().collect(),
        removed: before.difference(&after).cloned().collect(),
        unchanged: before.intersection(&after).cloned().collect(),
    }
}

fn normalize(value: String) -> String {
    value.trim().to_ascii_lowercase().replace('_', "-")
}

pub fn render_markdown(diff: &ScopeDiff) -> String {
    let mut output = String::from("# Policy scope comparison\n\n");
    for (heading, values) in [
        ("Added", &diff.added),
        ("Removed", &diff.removed),
        ("Unchanged", &diff.unchanged),
    ] {
        output.push_str(&format!("## {heading}\n"));
        if values.is_empty() {
            output.push_str("- none\n");
        } else {
            for value in values {
                output.push_str(&format!("- {value}\n"));
            }
        }
        output.push('\n');
    }
    output
}
```
