```sh
#!/usr/bin/env bash
set -euo pipefail

review_dir=${1:?pass the Cedar review directory}
printf 'Prepared Applied Foundations lab-update assets from %s\n' "$review_dir"
```
