# KCS-R23-CAND-050 PoC

This directory contains a bounded local regression probe for oversized
`tasks.jsonl` records. It synthesizes records with the same field shape that
`TaskDescriptor` parses, demonstrates that large arrays are materialized before
the path guard runs, and removes its temporary directory before exit.

Run:

```sh
make run
```

The probe uses only local temporary files, no network, no credentials, and no
live KCS scope.
