# KCS-R23-CAND-031 PoC

This is a local synthetic regression probe for the prepared CAS identity
mismatch. It does not invoke KCS, does not write a `.kcs` store, and does not
access credentials or external services.

Run:

```sh
make
```

The script models the vulnerable state transition with synthetic bytes:
version A is the caller-verified first read, version B is the prepare-stage
reopen, and publication writes A under B's prepared hash. A fixed
implementation should reject this state before publication or publish bytes
whose SHA-256 matches the prepared object name.
