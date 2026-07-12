# Synthetic TOCTOU Secret Snapshot Probe

This PoC models the vulnerable KCS state transition without invoking KCS or
reading real secrets. It creates a temporary scope, records preview-time
ignored names, introduces `.env` after preview, and shows that a closing
enumeration using only the stale preview exclusion set would archive the new
Tier-A file.

Run:

```sh
make
```

Expected output includes:

```text
[!] stale exclusion admitted newly introduced Tier-A file: .env
```

The script uses only Python's standard library and deletes its temporary
directory automatically.
