```rs
//! Bounds retry behavior for checkout calls during a degraded upstream event.

use std::time::Duration;

#[derive(Debug, Clone, Copy)]
pub struct RetryEnvelope {
    pub attempts: u8,
    pub base_delay: Duration,
    pub max_delay: Duration,
}

impl RetryEnvelope {
    pub fn checkout_default() -> Self {
        Self {
            attempts: 3,
            base_delay: Duration::from_millis(125),
            max_delay: Duration::from_secs(2),
        }
    }

    pub fn delay_for(&self, retry_index: u8) -> Duration {
        let multiplier = 1_u32 << retry_index.min(self.attempts.saturating_sub(1));
        let candidate = self.base_delay.saturating_mul(multiplier);
        candidate.min(self.max_delay)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn cap_is_respected() {
        let envelope = RetryEnvelope::checkout_default();
        assert_eq!(envelope.delay_for(8), Duration::from_secs(2));
    }
}
```
