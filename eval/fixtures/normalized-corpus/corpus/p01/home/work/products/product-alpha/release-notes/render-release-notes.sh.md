```sh
#!/usr/bin/env bash
set -euo pipefail

# Renders a short release-note heading from an already reviewed change list.
train=${1:?release train is required}
date=${2:?publication date is required}

printf '# Orchid Ledger %s\n\n' "$train"
printf 'Published: %s\n\n' "$date"
printf 'Changes are grouped by API compatibility, operations, and observability.\n'
```
