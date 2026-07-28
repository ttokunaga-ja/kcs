```json
{
  "captured_at": "2026-07-13T14:30:00Z",
  "incident": "INC-2026-0713",
  "service": "atlas-checkout",
  "component": "checkout-gateway",
  "cluster": "prod-apne-a",
  "rollout": {
    "change_id": "CHG-4821",
    "state": "held",
    "rule": "header-normalization"
  },
  "pods": {
    "ready": 12,
    "restarting": 0,
    "oldest_ready_seconds": 8460
  },
  "upstreams": [
    {
      "name": "orders-edge-apne1",
      "request_share": 0.41,
      "error_ratio": 0.003
    },
    {
      "name": "orders-edge-apne2",
      "request_share": 0.59,
      "error_ratio": 0.011
    }
  ],
  "signals": {
    "edge_error_ratio": 0.008,
    "upstream_p95_ms": 742,
    "route_skew": 0.143
  }
}
```
