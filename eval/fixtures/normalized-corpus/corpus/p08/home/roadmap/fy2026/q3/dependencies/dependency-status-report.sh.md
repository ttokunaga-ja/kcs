```sh
#!/usr/bin/env bash
set -euo pipefail

# Roadmap review 用の軽い整合性確認。外部サービスには接続しない。
input_file="${1:-dependencies.csv}"

if [[ ! -f "$input_file" ]]; then
  printf 'missing dependency export: %s\n' "$input_file" >&2
  exit 1
fi

awk -F',' '
  NR == 1 {
    for (i = 1; i <= NF; i++) column[$i] = i
    next
  }
  {
    owner = $(column["owner"])
    status = $(column["status"])
    review = $(column["review_date"])
    name = $(column["dependency"])
    if (owner == "" || status == "" || review == "") {
      printf "INCOMPLETE,%s,owner=%s,status=%s,review_date=%s\n", name, owner, status, review
      next
    }
    if (status != "confirmed" && status != "watching") {
      printf "CHECK,%s,status=%s,review_date=%s\n", name, status, review
    }
  }
' "$input_file"
```
