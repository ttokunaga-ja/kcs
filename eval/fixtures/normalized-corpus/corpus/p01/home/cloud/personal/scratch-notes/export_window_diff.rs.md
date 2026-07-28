```rs
//! Small helpers used while comparing two export windows.

use std::collections::BTreeSet;

pub fn missing_keys(expected: &[String], observed: &[String]) -> Vec<String> {
    let observed: BTreeSet<_> = observed.iter().collect();
    expected
        .iter()
        .filter(|key| !observed.contains(key))
        .cloned()
        .collect()
}

pub fn stable_window_label(day: &str, region: &str) -> String {
    format!("{}:{}:ledger-reconcile", day, region.to_ascii_lowercase())
}
```
