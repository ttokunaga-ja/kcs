# PDF Page Marker Probe

This bounded probe mirrors the vulnerable KCS parser behavior over a synthetic
PDF. It demonstrates that lexical `/Page` prefixes, including `/PageX`, control
the derived page vector and prepared-unit count when one printable stream keeps
the deterministic PDF path active.

Run it from this directory:

```sh
make run
make test
```

The probe deliberately caps materialized unit keys with `--max-allocate`; it
computes the default-cap upper bound instead of allocating millions of objects.
