# KCS Scan Hash Pre-Cap Allocation Probe

This PoC is a defensive, local-only source-order probe for
`KCS-R23-CAND-032`. It does not run KCS, does not use credentials, does not
contact a network service, and does not create a large file.

Run the standalone embedded check:

```sh
make check
```

Run the same check against a KCS checkout:

```sh
python3 scan_hash_order_probe.py --repo <kcs-checkout> \
  --rev 0e19f3c6489da458e93a982a333c308d92d0a0ae
```

The script verifies that normal indexing enables scan raw hashes, the scanner
records metadata length before `std::fs::read`, and the `max_input_bytes` gate
is downstream of the scan preview. It also performs a bounded 1 MiB synthetic
read to demonstrate whole-file allocation without stressing the host.
