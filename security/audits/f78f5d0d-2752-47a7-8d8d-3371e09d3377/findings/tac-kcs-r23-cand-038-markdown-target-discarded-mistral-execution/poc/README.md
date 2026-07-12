# KCS-R23-CAND-038 local invariant check

This proof of concept is local and offline. It reads the pinned KCS source
revision through `git show` and checks that fields accepted from `tools.toml`
(`kind`, `cmd`, `args`, and `url`) are discarded before production markdown
execution constructs the fixed Mistral OCR client.

Run from this directory with a checkout that contains the target revision:

```sh
KCS_REPO=<path-to-kcs-checkout> python3 check_destination_confusion.py
```

No network request is made, no credential is read, and no repository file is
modified.
