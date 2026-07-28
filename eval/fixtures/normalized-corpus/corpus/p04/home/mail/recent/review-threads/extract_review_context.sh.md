```sh
#!/usr/bin/env bash
set -euo pipefail

thread_file=${1:?pass a plain-text review thread}
rg -n --ignore-case 'decision|rollback|collection revision' "$thread_file" || true
```
