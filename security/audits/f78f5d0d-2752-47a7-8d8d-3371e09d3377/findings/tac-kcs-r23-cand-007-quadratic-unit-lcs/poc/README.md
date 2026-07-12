# KCS LCS Matrix Probe

This proof of concept is local, offline, and synthetic. It models the
allocation shape and nested loop used by KCS `lcs_fingerprint_pairs` without
creating crafted documents or touching a KCS repository.

Run it from the report directory:

```sh
cd poc
make run
```

The default run allocates only bounded matrices up to 512 by 512. Larger
10,000, 20,000, and 50,000 unit cases are reported as exact Rust `usize`
matrix estimates and are not allocated.
