```rs
//! Registry manifest helpers for Cedar model-card publication.

use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct ModelCardManifest {
    pub package: String,
    pub role: String,
    pub collection_revision: String,
    pub labels: BTreeMap<String, String>,
}

impl ModelCardManifest {
    pub fn publishable(&self) -> bool {
        !self.package.is_empty()
            && !self.collection_revision.is_empty()
            && matches!(self.role.as_str(), "candidate" | "robust-baseline")
    }
}
```
