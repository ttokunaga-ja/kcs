# Bounded manifest `unit_ref` regression

This credential-free, network-free harness demonstrates the path-selection
primitive with synthetic normalized-unit JSON. It mirrors the vulnerable
reader's `instance_dir / (unit_ref + ".json")` operation and compares it with
a fixed model that requires the 16-lowercase-hex reference derived from the
manifest entry's `unit_key`.

All paths and files live below one automatically deleted temporary directory.
The vulnerable-loader model has an additional lab-root safety guard, so the
harness will abort rather than read any host file outside that directory.

Run both malicious path forms and the canonical control:

```sh
make check
```

Or run one malicious path form:

```sh
python3 manifest_unit_ref_regression.py --case absolute
python3 manifest_unit_ref_regression.py --case parent
```

The expected result is that the vulnerable model imports the marker from the
synthetic external normalized unit for both path forms. The fixed model must
reject both malicious references and accept the canonical in-instance unit.

This is a source-faithful path regression, not an end-to-end invocation of the
KCS CLI. It does not modify a real `.kcs` store, contact an adapter, or exercise
search readback.
