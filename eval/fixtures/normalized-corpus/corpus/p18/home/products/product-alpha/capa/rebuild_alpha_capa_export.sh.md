```sh
#!/usr/bin/env bash
set -euo pipefail

# Aster A1 の CAPA 抜粋を品質会議用に整形する。
input=${1:?QMS CSV のパスを指定してください}
output=${2:-alpha_capa_extract.csv}

awk -F, 'BEGIN { OFS="," }
  NR == 1 { print "record_no", "owner", "state", "next_review"; next }
  $2 == "Aster A1" && $5 != "closed" { print $1, $4, $5, $7 }
' "$input" > "$output"

printf 'wrote %s\n' "$output"
```
