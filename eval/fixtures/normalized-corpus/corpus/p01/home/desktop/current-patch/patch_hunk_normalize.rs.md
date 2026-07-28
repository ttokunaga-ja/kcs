```rs
//! Normalizes a patch hunk before it is attached to a review note.

pub fn trim_context(lines: &[String]) -> Vec<String> {
    lines
        .iter()
        .filter(|line| !line.trim_start().starts_with("// generated"))
        .map(|line| line.trim_end().to_string())
        .collect()
}

pub fn changed_line_count(lines: &[String]) -> usize {
    lines
        .iter()
        .filter(|line| line.starts_with('+') || line.starts_with('-'))
        .count()
}
```
