# Bounded CAS Read Demonstration

This harness calls the affected `kcs-core` APIs against an isolated temporary
scope. It writes a small hash-consistent raw object, closes and reopens the
repository, and shows that `ObjectStore::read_by_hash` returns a `StoredObject`
whose `Vec<u8>` is exactly as large as the object. It then invokes the
metadata-only `Repository::inspect` path and exercises malformed-hash rejection
as a negative control.

The runner is deliberately non-destructive:

- `OBJECT_BYTES` defaults to 65,536 and is hard-limited to 1,048,576;
- Cargo is forced offline;
- no credentials or external services are used;
- the KCS source checkout is only used as a path dependency;
- all build output and scope state live under one temporary directory that is
  removed on exit; and
- the runner refuses a modified checkout or a revision other than
  `0e19f3c6489da458e93a982a333c308d92d0a0ae`.

Run from this directory, passing the path to the KCS source checkout. The
example keeps that path relative so the report bundle remains portable:

```sh
KCS_SOURCE=../../path-to-kcs-checkout
sh ./run.sh "$KCS_SOURCE"
```

The required Rust dependencies must already be present in Cargo's local cache,
because the runner does not permit network access. A different safe size can be
selected up to the hard ceiling:

```sh
OBJECT_BYTES=131072 sh ./run.sh "$KCS_SOURCE"
```

This is a diagnostic control, not an exhaustion test. It proves the size
relationship and the real call path without attempting to measure peak RSS or
trigger allocation failure.
