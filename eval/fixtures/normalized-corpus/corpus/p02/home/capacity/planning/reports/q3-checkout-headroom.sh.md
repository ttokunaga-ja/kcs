```sh
#!/usr/bin/env bash
# Collect the small set of Prometheus series used in the quarterly checkout readout.

set -euo pipefail

readonly report_day="${1:-2026-07-14}"
readonly prom_url="${PROM_URL:?set PROM_URL to the Prometheus query endpoint}"
readonly output_dir="${OUTPUT_DIR:-./out}"

/bin/mkdir -p "$output_dir"

query_range() {
  local name="$1"
  local expression="$2"
  curl --fail --silent --show-error --get "$prom_url/api/v1/query_range" \
    --data-urlencode "query=$expression" \
    --data-urlencode "start=${report_day}T00:00:00Z" \
    --data-urlencode "end=${report_day}T23:59:00Z" \
    --data-urlencode "step=300" \
    > "$output_dir/${name}.json"
}

query_range "checkout_rps" \
  'sum(rate(http_server_requests_total{service="atlas-checkout",environment="production"}[5m]))'
query_range "gateway_cpu" \
  'avg by (cluster) (rate(container_cpu_usage_seconds_total{app="checkout-gateway"}[5m]))'
query_range "worker_queue" \
  'max by (region) (checkout_worker_queue_depth{environment="production"})'
query_range "edge_errors" \
  'sum(rate(edge_requests_total{service="atlas-checkout",status=~"5.."}[5m])) / sum(rate(edge_requests_total{service="atlas-checkout"}[5m]))'

printf 'Wrote capacity inputs for %s to %s\n' "$report_day" "$output_dir"
```
