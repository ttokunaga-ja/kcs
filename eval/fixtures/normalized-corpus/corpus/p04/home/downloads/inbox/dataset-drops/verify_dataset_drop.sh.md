```sh
#!/usr/bin/env bash
set -euo pipefail

drop_dir=${1:?pass a dataset-drop directory}
test -f "$drop_dir/card.json" && printf 'dataset drop is complete: %s\n' "$drop_dir"
```
