# KCS Scan-Time Replacement PoC

This proof of concept is local, offline, and synthetic. It does not run KCS,
use credentials, contact any service, or read a real private file. Instead it
models the vulnerable interleaving from the source:

1. A benign direct child is observed as a regular file.
2. The directory writer atomically replaces that child with a symlink to an
   outside file.
3. The later scan hash and the later index hash both read through the pathname.
4. The accepted identity remains the benign in-scope name.

Run it from the report directory:

```sh
cd poc
make run
```

Expected output shows a matching scan/index hash and a synthetic outside marker
observed through the benign path.
