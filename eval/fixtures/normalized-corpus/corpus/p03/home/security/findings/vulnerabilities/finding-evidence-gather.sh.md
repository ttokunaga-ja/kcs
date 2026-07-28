```sh
#!/usr/bin/env bash
# Collect a bounded evidence snapshot for a security finding.
# The script reads local exports only; it does not call production services.

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 FINDING_ID EXPORT_DIR OUTPUT_DIR" >&2
  exit 64
fi

finding_id=$1
export_dir=$2
output_dir=$3

case "$finding_id" in
  FIND-*|PT-*) ;;
  *)
    echo "finding id must begin with FIND- or PT-" >&2
    exit 65
    ;;
esac

mkdir -p "$output_dir"
for suffix in summary timeline owner; do
  input="$export_dir/${finding_id}-${suffix}.json"
  if [ ! -f "$input" ]; then
    echo "missing export: $input" >&2
    exit 66
  fi
  jq --sort-keys '.' "$input" > "$output_dir/${suffix}.json"
done

{
  printf 'finding=%s\n' "$finding_id"
  date -u '+collected_at=%Y-%m-%dT%H:%M:%SZ'
  find "$output_dir" -type f -name '*.json' -exec shasum -a 256 {} \;
} > "$output_dir/manifest.txt"

echo "evidence snapshot written to $output_dir"
```
