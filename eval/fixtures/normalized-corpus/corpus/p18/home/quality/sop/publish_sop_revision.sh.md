```sh
#!/usr/bin/env bash
set -euo pipefail

revision=${1:?revision を指定してください}
source_dir=${2:?承認済み SOP ディレクトリを指定してください}
release_dir=${3:-./released-sop}

install -d "$release_dir"
cp "$source_dir"/WI-QA-021.md "$release_dir/WI-QA-021-${revision}.md"
printf 'released WI-QA-021 revision %s\n' "$revision"
```
