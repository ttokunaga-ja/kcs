# KCS-R23-CAND-068 PoC

This PoC is a local, network-free regression harness for the duplicate
embedding identity split. It models the vulnerable storage sequence from the
scanned KCS revision and the expected fixed invariant.

Run:

```sh
python3 duplicate_embedding_split.py
```

The output should show that the vulnerable model keeps the first authoritative
vector while linking `chunk-b` from the second response vector, and that the
fixed model links every duplicate chunk from the same canonical vector.
