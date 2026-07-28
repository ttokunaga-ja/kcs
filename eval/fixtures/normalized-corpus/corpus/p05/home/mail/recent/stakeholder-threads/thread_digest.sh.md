```sh
#!/usr/bin/env bash
    set -euo pipefail

    # stakeholder thread の export から、会議で使う action 行だけを抜き出す。
    mailbox_export="${1:?usage: thread_digest.sh <mail-export.txt>}"

    rg --ignore-case "action|確認|review|owner" "$mailbox_export"       | sed -E 's/^[[:space:]]+//'       | sort -u

    printf '%s
' "---"
    printf '%s
' "Commercial Intelligence: owner と期限は calendar invite と照合してから転記する"
```
