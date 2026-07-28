```rs
use std::ops::RangeInclusive;

pub fn stable_signal_window(intensities: &[f64]) -> Option<RangeInclusive<usize>> {
    let mut start = None;
    for (index, value) in intensities.iter().enumerate() {
        if *value >= 0.82 && start.is_none() { start = Some(index); }
        if let Some(first) = start {
            if *value < 0.82 { return Some(first..=index.saturating_sub(1)); }
        }
    }
    start.map(|first| first..=intensities.len().saturating_sub(1))
}
```
