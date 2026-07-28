```sh
#!/usr/bin/env bash
# Prepare a review-only safety listing for the ORCHID-CKD-201 data review meeting.
# The input is expected to contain de-identified participant keys only.

set -euo pipefail

if [[ "$#" -ne 2 ]]; then
  echo "usage: $0 INPUT_CSV OUTPUT_CSV" >&2
  exit 64
fi

input_csv="$1"
output_csv="$2"

if [[ ! -r "$input_csv" ]]; then
  echo "input is not readable: $input_csv" >&2
  exit 66
fi

expected_header="participant_key,event_term,onset_date,status,medical_review"
actual_header="$(head -n 1 "$input_csv")"
if [[ "$actual_header" != "$expected_header" ]]; then
  echo "unexpected input header; refusing to prepare a listing" >&2
  exit 65
fi

output_dir="$(dirname "$output_csv")"
mkdir -p "$output_dir"
temporary_listing="$(mktemp "$output_dir/.safety-listing.XXXXXX")"
trap 'rm -f "$temporary_listing"' EXIT

printf '%s\n' "$expected_header" > "$temporary_listing"
tail -n +2 "$input_csv" \
  | awk -F',' 'BEGIN { OFS="," } $4 != "withdrawn" { print $1, $2, $3, $4, $5 }' \
  | LC_ALL=C sort -t',' -k3,3 -k1,1 >> "$temporary_listing"

mv "$temporary_listing" "$output_csv"
trap - EXIT
echo "prepared review listing: $output_csv" >&2
```
