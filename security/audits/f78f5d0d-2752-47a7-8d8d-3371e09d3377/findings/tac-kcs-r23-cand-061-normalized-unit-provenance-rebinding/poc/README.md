# Synthetic normalized-unit rebinding probe

This directory contains a local regression probe for the normalized-unit
provenance binding issue. It builds a temporary manifest and unit object, runs a
small model of the vulnerable reader, and then runs the strict checks that KCS
should enforce before indexing normalized markdown.

Run it from this directory:

```sh
make
```

The probe uses only Python's standard library and a temporary directory. It
does not open a real KCS store or contact any external service.
