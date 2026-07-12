# Raw-hash resolver bound probe

This is a safe local regression probe for KCS-R23-CAND-057. It uses only small
synthetic files in a temporary directory and models the relevant resolver shape:
skip `.kcs`, visit regular direct children, read each candidate in full, hash it,
and continue until an absent hash has forced a full scan.

Run:

```sh
make
```

The script does not invoke a live KCS command, use credentials, contact a
network service, or allocate large files.
