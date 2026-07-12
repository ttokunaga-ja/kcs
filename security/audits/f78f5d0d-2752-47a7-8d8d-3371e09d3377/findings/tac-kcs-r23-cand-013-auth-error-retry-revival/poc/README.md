# AuthError Retry Revival PoC

This PoC models the embedding task state transition behind
`KCS-R23-CAND-013`. It is local and synthetic: it does not import KCS, read
credentials, open sockets, or contact an embedding provider.

Run it from this directory:

```sh
make
```

Expected result:

```text
[setup] live embedding task starts as Failed(auth_error), attempts=1
[retry] outer retry scheduler changed 0 task(s)
[vulnerable] reconciliation changed 1 task(s) without an auth-revival gate
[vulnerable] adapter mock sent 1 chunk(s): approved-chunk-1
[vulnerable] final task: Done(embedding_adapter_done), attempts=0
[fixed retry] reconciliation changed 0 task(s); sent 0 chunk(s); task stays Failed(auth_error)
[fixed resume] reconciliation changed 1 task(s); sent 1 chunk(s); task becomes Done(embedding_adapter_done)
[ok] vulnerable retry revival and fixed retry/resume split reproduced offline
```

The assertions fail if the vulnerable retry path stops reviving
`Failed(auth_error)` without an explicit auth-revival gate, or if the fixed
retry/resume split does not preserve the intended command contract.
