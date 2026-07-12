# Synthetic PDF reopen misbinding PoC

This local/offline probe models the reviewed KCS control flow with synthetic
PDF-like files. It does not invoke KCS, touch repository state, use credentials,
or contact a network service.

Run it from this directory:

```sh
make run
```

The script performs the same relevant sequence proved from source:

1. read and hash PDF version A;
2. keep `H(A)` as the authoritative raw identity;
3. replace the pathname with version B before the aggregate deterministic read;
4. replace the pathname again with version C before the per-page deterministic
   read;
5. show that C-derived markdown is stored under `H(A)` in the model.

Successful output ends with:

```text
[+] misbinding reproduced in the synthetic control-flow model
```
