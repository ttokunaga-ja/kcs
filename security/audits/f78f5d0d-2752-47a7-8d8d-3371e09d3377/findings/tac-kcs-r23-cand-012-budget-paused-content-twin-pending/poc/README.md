# Offline PoC

This PoC models the vulnerable KCS reconciliation state with synthetic data.
It does not use a real KCS store, an embedding adapter, credentials, network
access, or live services.

Run:

```sh
make
```

The script creates two byte-distinct documents that normalize to the same
chunk text, marks the first as `Paused(budget_exceeded)`, lets the second
materialize the shared content vector, rebuilds `chunk_vec`, and compares the
vulnerable reason-blind paused guard with a reason-specific fixed guard.
