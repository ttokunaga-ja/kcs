```sh
#!/usr/bin/env bash
    set -euo pipefail

    # inbox の手動 export を staging に置く。source は上書きせず日付別に保管する。
    input_file="${1:?usage: refresh_extract.sh <csv-file>}"
    stamp="$(date +%Y%m%d)"
    target_dir="../staging/inbox/${stamp}"

    mkdir -p "$target_dir"
    cp "$input_file" "$target_dir/crm_activity.csv"

    printf '%s
' "copied CRM activity extract to $target_dir"
    printf '%s
' "next: run cleanup notebook and inspect unknown market values"
```
