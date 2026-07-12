# KCS-R23-CAND-047 PoC

This probe is local and synthetic. It models the persisted `output_ref` path
selection and unchanged-unit reuse described in the report without invoking KCS,
using credentials, contacting an adapter, or reading any real external document.

Run from this directory:

```sh
make
```

Expected output is recorded in `expected-output.txt`.
