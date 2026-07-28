```sh
#!/usr/bin/env bash
# Produce a shareable case export for Customer Alpha without requester details.

set -euo pipefail

input_file=${1:?Usage: case-export-sanitize.sh INPUT.csv OUTPUT.csv}
output_file=${2:?Usage: case-export-sanitize.sh INPUT.csv OUTPUT.csv}

if ! command -v mlr >/dev/null 2>&1; then
  echo "miller (mlr) is required to process CSV files" >&2
  exit 127
fi

if [[ ! -f "$input_file" ]]; then
  echo "input file not found: $input_file" >&2
  exit 2
fi

output_dir=$(dirname "$output_file")
mkdir -p "$output_dir"
temporary_file=$(mktemp "$output_dir/.case-export.XXXXXX")
trap 'rm -f "$temporary_file"' EXIT

# Select the fields that are useful in a handoff and omit personal contact data.
mlr --icsv --ocsv cut \
  -f ticket_number,opened_at,last_updated,status,category,summary,owner_team \
  "$input_file" > "$temporary_file"

mv "$temporary_file" "$output_file"
trap - EXIT

echo "wrote sanitized export: $output_file"
```
