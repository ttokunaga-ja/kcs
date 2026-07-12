# Symlinked `.kcs` Cross-Scope Store PoC

This PoC is local and offline. It creates disposable KCS roots, links the
second root's `.kcs` entry to the first root's live store, and checks whether a
snapshot run from the linked root advances the first store's `HEAD`.

Run it with a vulnerable `kcs` binary on `PATH`:

```sh
cd poc
make run
```

Alternatively, set `KCS_BIN` to a built binary or `KCS_CMD` to a command prefix
that accepts KCS arguments:

```sh
cd poc
KCS_BIN=kcs make run
KCS_CMD='cargo run --quiet --bin kcs --' make run
```

All KCS state, device data, and test files are created under a temporary
directory and removed when the script exits.
