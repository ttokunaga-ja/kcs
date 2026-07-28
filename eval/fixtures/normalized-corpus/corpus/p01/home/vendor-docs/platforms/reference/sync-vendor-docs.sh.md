```sh
#!/usr/bin/env bash
set -euo pipefail

# Verifies that a vendor OpenAPI document has the response headers we depend on.
spec_path=${1:?OpenAPI document is required}

jq --exit-status '
  .openapi and
  (.paths | type == "object") and
  ([.. | objects | .headers? | objects | keys[]?] | index("x-request-id"))
' "$spec_path" >/dev/null

printf 'vendor contract has a request correlation header\n'
```
