# Temporary-scope secret-twin regression probe

This probe checks one defensive state-machine invariant: a newly indexed,
secret-labeled chunk must be held before content-addressed vector reuse can make
that chunk vector-searchable.

The fixture is deliberately harmless. It uses synthetic Markdown, a disposable
temporary scope, isolated `HOME` and XDG directories, and KCS's deterministic
in-process embedding seam. It supplies no credentials, opens no existing KCS
store, and makes no network request. The temporary tree is removed on exit.

## Requirements

- a `kcs` binary built from the revision under test;
- Bash;
- `jq`.

To build the confirmed vulnerable revision from a KCS checkout without fetching
dependencies, when the dependency cache is already populated:

```sh
git checkout 0e19f3c6489da458e93a982a333c308d92d0a0ae
cargo build --locked --offline -p kcs-cli --bin kcs
export KCS_BIN="$(pwd)/target/debug/kcs"
```

Then, from the report directory:

```sh
cd poc
./reproduce.sh
```

If `kcs` is already the binary under test and is on `PATH`, `KCS_BIN` may be
omitted.

## Interpreting the result

On the confirmed vulnerable revision, the final lines are:

```text
secret_shared_chunk_hold_count=0
secret_shared_chunk_in_vector_results=true
result=VULNERABLE_POLICY_STATE_OBSERVED
```

The nearby control is `secret_unique_chunk_hold_count=1`. It shows that the
secret-name classifier and hold machinery ran; only the shared chunk fell
through the reuse-before-hold ordering.

A fixed build should instead report at least one hold for the shared secret
chunk, omit that chunk from vector results, and end with:

```text
result=FIXED_POLICY_STATE_OBSERVED
```

The script returns nonzero only when it cannot establish either coherent state.
No manual cleanup is required.
