```sh
#!/usr/bin/env bash
set -euo pipefail

# Produces a compact list of review references without copying payloads.
bundle_dir=${1:?bundle directory is required}

find "$bundle_dir" -maxdepth 1 -type f \( -name '*.patch' -o -name '*.md' \) -print \
  | sort \
  | while IFS= read -r path; do
      printf '%s\t%s\n' "$(basename "$path")" "$(wc -l < "$path") lines"
    done
```
