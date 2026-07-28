```rs
//! 元帳イベントの簡易ラベル付け。手元の調査メモから切り出したもの。

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum JournalKind {
    Posting,
    Reversal,
    Hold,
    Unknown,
}

pub fn classify_event(value: &str) -> JournalKind {
    match value.trim().to_ascii_lowercase().as_str() {
        "posted" | "settled" => JournalKind::Posting,
        "reversed" | "voided" => JournalKind::Reversal,
        "held" | "pending_review" => JournalKind::Hold,
        _ => JournalKind::Unknown,
    }
}

pub fn needs_operator_note(kind: JournalKind) -> bool {
    matches!(kind, JournalKind::Hold | JournalKind::Unknown)
}
```
