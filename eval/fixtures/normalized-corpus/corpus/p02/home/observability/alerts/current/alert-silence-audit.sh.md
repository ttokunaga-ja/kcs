```sh
#!/usr/bin/env bash
#
# Lists active Alertmanager silences relevant to Atlas Checkout and flags
# entries that need an owner confirmation before a production change.

set -euo pipefail

alertmanager_url="${ALERTMANAGER_URL:-https://alerts.prod.internal}"
now_epoch="$(date -u +%s)"

curl --fail --silent "${alertmanager_url}/api/v2/silences" |
  jq -r --argjson now "${now_epoch}" '
    .[]
    | select(.status.state == "active")
    | select(any(.matchers[]; .value | test("checkout|gateway"; "i")))
    | [
        .id,
        .createdBy,
        .endsAt,
        ([.matchers[] | "\(.name)=\(.value)"] | join(", ")),
        .comment
      ]
    | @tsv
  ' |
  while IFS=$'\t' read -r silence_id owner ends_at matchers comment; do
    printf 'active silence %s\n' "${silence_id}"
    printf '  owner: %s\n  ends: %s\n  matchers: %s\n  note: %s\n' \
      "${owner}" "${ends_at}" "${matchers}" "${comment}"
  done

echo "Confirm that incident-only silences have an expiry and a named owner."
```
