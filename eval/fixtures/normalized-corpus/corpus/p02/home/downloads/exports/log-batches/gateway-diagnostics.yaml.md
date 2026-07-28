```yaml
capture:
  incident: INC-2026-0713
  captured_at: "2026-07-13T14:30:00Z"
  collector: edge-diagnostics-cli
  service: atlas-checkout
  component: checkout-gateway
regions:
  ap-northeast:
    healthy_pods: 12
    restarting_pods: 0
    upstreams:
      orders-edge-apne1:
        request_share: 0.41
        error_ratio: 0.003
      orders-edge-apne2:
        request_share: 0.59
        error_ratio: 0.011
signals:
  edge_error_ratio: 0.008
  upstream_p95_ms: 742
  route_skew: 0.143
recommended_actions:
  - hold the active release stage
  - capture a trace from each upstream group
  - compare route selection after pod replacement
```
