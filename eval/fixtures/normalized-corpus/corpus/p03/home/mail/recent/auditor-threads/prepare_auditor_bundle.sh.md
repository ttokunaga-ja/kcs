```sh
#!/usr/bin/env bash
# Assemble a review copy of selected evidence for the auditor portal.
# This script refuses to add files outside the manifest so incidental downloads do not
# become part of a Nami Grid evidence bundle.

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "usage: $0 MANIFEST.tsv SOURCE_DIR OUTPUT_DIR" >&2
  exit 64
fi

manifest=$1
source_dir=$2
output_dir=$3

mkdir -p "$output_dir"
while IFS=$'\t' read -r relative_path label; do
  [ -z "$relative_path" ] && continue
  case "$relative_path" in
    /*|*".."*)
      echo "unsafe manifest entry: $relative_path" >&2
      exit 65
      ;;
  esac

  source_file="$source_dir/$relative_path"
  destination="$output_dir/$label"
  if [ ! -f "$source_file" ]; then
    echo "missing source file: $relative_path" >&2
    exit 66
  fi

  install -m 0640 "$source_file" "$destination"
  printf 'added %s as %s\n' "$relative_path" "$label"
done < "$manifest"

find "$output_dir" -type f ! -name checksums.sha256 -exec shasum -a 256 {} \; > "$output_dir/checksums.sha256"
echo "bundle prepared at $output_dir"
```
