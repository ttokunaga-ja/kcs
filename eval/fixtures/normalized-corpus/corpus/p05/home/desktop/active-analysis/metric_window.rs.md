```rs
#[derive(Debug, Clone, Copy)]
pub struct MetricWindow {
    pub start_day: i32,
    pub end_day: i32,
    pub include_partial_day: bool,
}

impl MetricWindow {
    pub fn closed_q2() -> Self {
        Self {
            start_day: 20260401,
            end_day: 20260630,
            include_partial_day: false,
        }
    }

    pub fn contains(&self, day: i32) -> bool {
        day >= self.start_day && day <= self.end_day
    }
}

pub fn label(window: MetricWindow) -> String {
    // 調査ノートでは暦日を固定し、後から rolling window に変えない。
    format!("{}-{}", window.start_day, window.end_day)
}
```
