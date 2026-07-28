```sh
#!/usr/bin/env bash
set -euo pipefail

config=${1:?pass a Cedar candidate configuration}
python -m cedar.train --config "$config" --review-mode
```
