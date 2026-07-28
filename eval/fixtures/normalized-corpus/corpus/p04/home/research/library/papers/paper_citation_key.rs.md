```rs
//! Stable local keys for literature notes in the Cedar paper folder.

pub fn citation_key(author: &str, year: u16, topic: &str) -> String {
    let author = author.trim().to_lowercase().replace(' ', "");
    let topic = topic.trim().to_lowercase().replace(' ', "-");
    format!("{}-{}-{}", author, year, topic)
}
```
