# KCS-R23-CAND-040 local regression probe

This probe performs a local static check for the redirect credential-retention
condition. It does not start listeners, send network traffic, or use real
credentials.

Run from this directory:

```sh
make SOURCE_ROOT=/path/to/kcs UREQ_SRC=/path/to/ureq-2.12.1/src check
```

`UREQ_SRC` is optional when the local Cargo registry already contains
`ureq-2.12.1/src`.
