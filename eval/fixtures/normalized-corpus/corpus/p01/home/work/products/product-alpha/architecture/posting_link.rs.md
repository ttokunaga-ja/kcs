```rs
//! Data types used while sketching the Orchid Ledger posting flow.

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PostingLink {
    pub request_id: String,
    pub journal_id: String,
    pub state: String,
}

impl PostingLink {
    pub fn is_terminal(&self) -> bool {
        matches!(self.state.as_str(), "posted" | "reversed" | "voided")
    }

    pub fn correlation_key(&self) -> String {
        format!("{}:{}", self.request_id, self.journal_id)
    }
}
```
