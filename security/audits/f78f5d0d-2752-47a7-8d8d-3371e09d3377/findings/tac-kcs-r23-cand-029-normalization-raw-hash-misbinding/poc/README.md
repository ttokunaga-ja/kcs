# Normalization Raw-Hash Misbinding PoC

This PoC is a local/offline model of the deterministic normalization bug. It
uses temporary synthetic files and does not run KCS, use credentials, contact
network services, or read any real target data.

Run it from this directory:

```sh
make
```

or directly:

```sh
python3 normalization_raw_hash_misbinding_poc.py
```

The script writes version A, computes and verifies `H(A)`, prepares from A,
then replaces the path with version B before the markdownization step. The
modeled deterministic adapter reads B from the path while persistence keeps
the earlier `raw_hash`, demonstrating the provenance binding failure.

Expected output is recorded in `representative-output.txt`.
