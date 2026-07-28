```rs
use std::collections::HashSet;

#[derive(Debug)]
pub struct BuyerWeek {
    pub buyer_key: String,
    pub week_start: String,
    pub orders: u32,
}

pub fn sample_first_active_week(rows: &[BuyerWeek]) -> Vec<&BuyerWeek> {
    let mut seen = HashSet::new();
    let mut sample = Vec::new();

    for row in rows.iter().filter(|row| row.orders > 0) {
        let key = format!("{}:{}", row.buyer_key, row.week_start);
        if seen.insert(key) && stable_bucket(&row.buyer_key) < 5 {
            sample.push(row);
        }
    }
    sample
}

fn stable_bucket(value: &str) -> u8 {
    // 個人用の検証では、固定 hash で小さな cohort を再現する。
    value.bytes().fold(0u8, |acc, byte| acc.wrapping_add(byte)) % 100
}
```
