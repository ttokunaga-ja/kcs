```rs
//! Orionの仕訳キーと証憑フォルダを結び付けるための小さな補助コマンド。
//! 月次締めの調査時に、共有フォルダ上のファイル名を統一する用途で使う。

use std::collections::BTreeMap;

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PostingLink {
    pub journal_id: String,
    pub evidence_key: String,
    pub close_month: String,
}

pub fn build_evidence_key(company: &str, journal_id: &str, close_month: &str) -> String {
    format!("{company}/{close_month}/journal/{journal_id}")
}

pub fn index_links(rows: impl IntoIterator<Item = PostingLink>) -> BTreeMap<String, PostingLink> {
    rows.into_iter()
        .map(|row| (row.journal_id.clone(), row))
        .collect()
}

pub fn unresolved_links(index: &BTreeMap<String, PostingLink>, expected: &[&str]) -> Vec<String> {
    expected
        .iter()
        .filter(|journal_id| !index.contains_key(**journal_id))
        .map(|journal_id| (*journal_id).to_owned())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn evidence_key_uses_month_and_journal() {
        assert_eq!(
            build_evidence_key("shinonome", "JR-2603-1842", "2026-03"),
            "shinonome/2026-03/journal/JR-2603-1842"
        );
    }
}
```
