```sh
#!/usr/bin/env bash
set -euo pipefail

# メール添付の差分を確認する前に、対象リポジトリの状態だけを記録する。
repo_dir=${1:?対象リポジトリを指定してください}

git -C "$repo_dir" status --short
git -C "$repo_dir" log -1 --format='%h %s'
```
