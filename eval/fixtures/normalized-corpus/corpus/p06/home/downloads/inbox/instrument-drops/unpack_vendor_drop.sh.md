```sh
#!/usr/bin/env bash
set -euo pipefail
archive_path=$1
destination=$2
mkdir -p "$destination"
unzip -q "$archive_path" -d "$destination"
find "$destination" -name ".DS_Store" -delete
find "$destination" -maxdepth 2 -type f -print | sort
```
