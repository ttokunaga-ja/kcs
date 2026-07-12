# PoC: unrecognized binary completeness telemetry

This PoC runs the real `kcs` CLI against a disposable local scope. It creates:

- `ok.md`, a recognized text control that becomes searchable;
- `photo.bmp`, a small binary input that is archived but reaches the unrecognized `application/octet-stream` branch.

The harness uses private `XDG_CONFIG_HOME`, `XDG_DATA_HOME`, and `XDG_CACHE_HOME` directories, performs no network activity, and deletes its temporary directory unless `--keep-temp` is supplied.

## Run

```sh
make dry-run
KCS_BIN=kcs make run
```

If `kcs` is not on `PATH`, set `KCS_BIN` to a built CLI executable using a path
that is valid from this directory:

```sh
KCS_BIN=./kcs make run
```

Expected output is recorded in `representative-output.txt`.
