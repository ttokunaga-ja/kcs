# Deferred Pre-Cap Read Probe

This PoC uses only a temporary directory and small synthetic files. It does not
invoke KCS, contact external services, or create large allocations.

Run from this directory:

```sh
make run
```

The vulnerable-order model reads the replacement file before deciding to retire
the stale task. The fixed-order model rejects the replacement by metadata before
reading any file bytes.
