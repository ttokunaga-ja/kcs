```rs
use std::collections::VecDeque;

#[derive(Clone, Debug)]
pub struct GatewaySample {
    pub edge_error_rate: f64,
    pub upstream_p95_ms: u64,
    pub route_skew: f64,
}

#[derive(Debug)]
pub struct SignalWindow {
    max_samples: usize,
    samples: VecDeque<GatewaySample>,
}

impl SignalWindow {
    pub fn new(max_samples: usize) -> Self {
        assert!(max_samples > 0, "a signal window needs capacity");
        Self {
            max_samples,
            samples: VecDeque::with_capacity(max_samples),
        }
    }

    pub fn record(&mut self, sample: GatewaySample) {
        if self.samples.len() == self.max_samples {
            self.samples.pop_front();
        }
        self.samples.push_back(sample);
    }

    pub fn average_error_rate(&self) -> Option<f64> {
        let count = self.samples.len();
        (count > 0).then(|| {
            self.samples
                .iter()
                .map(|sample| sample.edge_error_rate)
                .sum::<f64>()
                / count as f64
        })
    }

    pub fn worst_route_skew(&self) -> Option<f64> {
        self.samples
            .iter()
            .map(|sample| sample.route_skew)
            .reduce(f64::max)
    }

    pub fn p95_latency_ms(&self) -> Option<u64> {
        let mut values: Vec<u64> = self
            .samples
            .iter()
            .map(|sample| sample.upstream_p95_ms)
            .collect();
        values.sort_unstable();
        let index = values.len().checked_sub(1)?.saturating_mul(95) / 100;
        values.get(index).copied()
    }
}
```
