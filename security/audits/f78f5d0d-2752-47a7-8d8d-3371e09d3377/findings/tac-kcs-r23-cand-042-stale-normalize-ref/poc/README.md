# Synthetic stale NormalizeRef probe

This proof of concept models the relevant KCS identity transition with
in-memory byte strings. It does not invoke KCS, read repository data, or race the
filesystem. The vulnerable model attaches a `NormalizeRef` by path after the file
bytes have changed; the fixed model carries `expected_raw_hash` and rejects the
drift before publication.

Run from this directory:

```sh
make run
```

Expected output includes:

```text
vulnerable_tree_has_normalize= True
vulnerable_rebuild_units_found= False
fixed_drift_rejected= True
fixed_tree_has_normalize= False
```
