```rs
use std::collections::BTreeMap;

#[derive(Debug, Clone)]
pub struct SnapshotStatus {
    pub mart: String,
    pub observed_rows: u64,
    pub expected_min_rows: u64,
    pub watermark_hour_jst: u8,
}

pub fn evaluate(status: &SnapshotStatus) -> Result<(), String> {
    // planning refresh では、午前の dashboard 公開前に最低件数と watermark を確認する。
    if status.observed_rows < status.expected_min_rows {
        return Err(format!(
            "{} has {} rows; expected at least {}",
            status.mart, status.observed_rows, status.expected_min_rows
        ));
    }
    if status.watermark_hour_jst < 6 {
        return Err(format!("{} watermark is too early", status.mart));
    }
    Ok(())
}

pub fn summary(items: &[SnapshotStatus]) -> BTreeMap<String, String> {
    items
        .iter()
        .map(|item| {
            let result = evaluate(item).map(|_| "ready".to_string()).unwrap_or_else(|e| e);
            (item.mart.clone(), result)
        })
        .collect()
}
```
