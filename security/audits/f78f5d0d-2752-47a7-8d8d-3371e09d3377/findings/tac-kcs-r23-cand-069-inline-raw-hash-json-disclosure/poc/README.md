# Synthetic tombstone path probe

This probe is local and non-destructive. It creates a temporary synthetic KCS
directory and a synthetic JSON marker file, then applies the same path
construction pattern as the vulnerable `read_tombstone()` helper.

It does not run KCS, read existing user files, use credentials, contact a
network service, or target a live system.

Run:

```sh
make
make run
```
