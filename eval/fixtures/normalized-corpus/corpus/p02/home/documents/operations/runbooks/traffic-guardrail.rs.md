```rs
#[derive(Debug, Clone, Copy)]
pub struct GatewaySignals {
    pub edge_error_rate: f64,
    pub upstream_p95_ms: u64,
    pub route_skew: f64,
}

#[derive(Debug, PartialEq)]
pub enum ReleaseDecision {
    Continue,
    Hold(&'static str),
}

pub fn evaluate(signals: GatewaySignals) -> ReleaseDecision {
    if signals.edge_error_rate > 0.008 {
        return ReleaseDecision::Hold("edge error rate exceeded release guardrail");
    }
    if signals.upstream_p95_ms > 780 {
        return ReleaseDecision::Hold("upstream latency exceeded release guardrail");
    }
    if signals.route_skew > 0.12 {
        return ReleaseDecision::Hold("regional upstream selection is uneven");
    }
    ReleaseDecision::Continue
}

pub fn should_page(signals: GatewaySignals) -> bool {
    matches!(evaluate(signals), ReleaseDecision::Hold(_))
}
```
