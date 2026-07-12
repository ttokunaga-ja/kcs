# KCS-R23-CAND-043 PoC

This is a local synthetic regression check for the KCS CAS occupied-slot
write bug. It creates a disposable store-shaped directory under the system temp
directory, pre-seeds the raw object fanout path with wrong bytes, then models
the vulnerable `atomic_write()` branch that returns success when the path
already exists.

Run:

```sh
make
```

The script uses only synthetic bytes and no network access. It does not touch a
real `.kcs` store.
