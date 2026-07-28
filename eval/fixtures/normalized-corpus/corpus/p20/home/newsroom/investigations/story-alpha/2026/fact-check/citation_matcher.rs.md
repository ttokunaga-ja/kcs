```rs
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct Citation {
    pub label: String,
    pub document_key: String,
    pub page: u16,
}

pub fn group_by_document(items: &[Citation]) -> BTreeMap<String, Vec<&Citation>> {
    let mut grouped = BTreeMap::new();
    for item in items {
        grouped.entry(item.document_key.clone()).or_insert_with(Vec::new).push(item);
    }
    grouped
}

pub fn page_reference(item: &Citation) -> String {
    format!("{} p. {}", item.label, item.page)
}
```
