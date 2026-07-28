```sh
#!/usr/bin/env bash
set -euo pipefail

# Runs a non-destructive health check against a supplied endpoint.
endpoint=${1:?endpoint is required}
expected_service=${2:-poppy-gateway}

response=$(curl --silent --show-error --fail --max-time 8 "$endpoint/health")
printf '%s' "$response" | jq --exit-status --arg service "$expected_service" \
  '.status == "ok" and .service == $service' >/dev/null
printf 'health check passed for %s\n' "$expected_service"
```
