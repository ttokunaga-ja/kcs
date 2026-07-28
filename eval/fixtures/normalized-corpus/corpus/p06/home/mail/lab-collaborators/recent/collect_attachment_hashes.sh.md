```sh
#!/usr/bin/env bash
set -euo pipefail
inbox_dir=$1
find "$inbox_dir" -type f \( -name "*.pdf" -o -name "*.docx" -o -name "*.xlsx" \) -print0 |
  while IFS= read -r -d '' file; do shasum -a 256 "$file"; done | sort
```
