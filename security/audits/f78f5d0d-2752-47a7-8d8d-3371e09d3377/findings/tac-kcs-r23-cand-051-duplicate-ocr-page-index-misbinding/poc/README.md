# Offline duplicate page-index probe

This probe models the KCS OCR adapter's page-index map and positional fallback
for KCS-R23-CAND-051. It uses synthetic page labels only.

Run:

```sh
make
```

Expected behavior:

- duplicate provider indices `[(0, A), (0, B)]` map both prepared hints to `B`;
- the key/shape validation still sees both trusted unit keys;
- unique provider indices `[(0, A), (1, B)]` preserve the expected mapping;
- a proposed bijection check rejects the duplicate index.
