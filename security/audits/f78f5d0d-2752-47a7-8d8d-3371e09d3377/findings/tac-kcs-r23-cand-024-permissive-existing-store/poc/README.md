# KCS permissive existing-store PoC

This PoC creates a disposable Unix fixture, initializes a KCS scope, makes the
existing `.kcs` directory traversable, re-runs `kcs init`, then snapshots a
mode-0600 file. On the vulnerable revision, `init` reports that the scope is
already initialized, leaves `.kcs` at mode 0755, and `snapshot` writes a raw CAS
object containing the private bytes with the process umask-derived mode.

## Run

From this directory:

```sh
chmod +x repro.sh
KCS_REPO=../../kcs make run
```

Set `KCS_REPO` to a local KCS checkout. Alternatively, set `KCS_BIN` to a built
`kcs` binary:

```sh
KCS_BIN=./kcs make run
```

The script uses only local temporary directories and deletes its fixture unless
`KEEP_POC_TMP=1` is set. When using `cargo`, it preserves the caller's
`CARGO_HOME` and `RUSTUP_HOME` and runs `cargo +stable` by default; override
that with `CARGO_TOOLCHAIN` if needed.
