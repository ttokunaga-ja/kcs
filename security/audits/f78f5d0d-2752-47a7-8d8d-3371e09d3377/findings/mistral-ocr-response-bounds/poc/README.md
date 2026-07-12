# In-memory OCR response-bounds probe

This probe models the allocation, image decoding, and would-be persistence
sequence in the affected Mistral OCR response path, then runs the same small
responses through a defensive bounded parser.  It uses deliberately tiny test
limits so the over-limit cases remain harmless.

The probe does not start a service, open a network connection, read credentials,
sleep, or write image objects.  Persistence is represented only by summing the
unique SHA-256-addressed image bytes in memory.

Run it from the report directory:

```sh
cd poc
python3 response_bounds_poc.py
```

Representative output:

```text
PASS baseline: current=accepted(pages=1, images=1, decoded=200, would_persist=200); bounded=accepted(decoded=200, unique_persist=200)
PASS virtual_slow_read: current=accepted(pages=1, images=1, decoded=200, would_persist=200); bounded=rejected[deadline]
PASS body_over_limit: current=accepted(pages=0, images=0, decoded=0, would_persist=0); bounded=rejected[body_bytes]
PASS page_cardinality: current=accepted(pages=5, images=0, decoded=0, would_persist=0); bounded=rejected[pages]
PASS unique_persistence_budget: current=accepted(pages=1, images=2, decoded=1600, would_persist=1600); bounded=rejected[persist_total]
PASS cas_dedup_control: current=accepted(pages=1, images=2, decoded=1600, would_persist=800); bounded=accepted(decoded=1600, unique_persist=800)
All cases passed; no network, credentials, sleeps, or file writes were used.
```

The virtual tick case demonstrates the policy decision without timing a socket.
It is not a measurement of `ureq` or a live Mistral endpoint.  The body case is
uncompressed; production code also needs an explicit policy for compressed wire
bytes and decompressed bytes.
