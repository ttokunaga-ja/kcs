# Validation: normalized manifests and unit objects are not rebound to the requested provenance tuple

- Candidate: `KCS-R23-CAND-061`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.96)**
- Method: **V6 poisoned-state provenance + complete V10 source-to-sink trace**

Rebuild requests a normalized instance using a tree entry's `raw_hash`, profile, and generation. `load_normalized_units` constructs that directory but only deserializes `manifest.json` and each referenced unit at `crates/kcs-cli/src/main.rs:3355-3390`. It does not compare the requested tuple with `manifest.raw_hash/tool_profile_hash/gen`; it does not compare manifest entry key/type/prepared hash/ref with the unit; and it emits `NormalizedUnitInput` from the unit's self-declared `raw_hash`, profile, generation, key, and markdown.

`chunk_normalized_units` then hashes and persists chunks from those unverified fields at `crates/kcs-index/src/chunking.rs:167-185`. Rebuild/search joins them to live tree entries by those same fields and returns their text/provenance at `crates/kcs-cli/src/main.rs:3045-3090,2107-2120`. A copied/preseeded store can therefore place parse-valid objects in one requested instance while self-declaring another live tuple, substituting arbitrary normalized text as durable searchable/evidence content for that file.

Path construction and JSON parsing are real controls, but they establish location/shape, not semantic identity. Later Evidence checks bind to the already-poisoned ChunkRow and cannot prove the normalized source. The adopted-store source and exact reader-to-chunk-to-search chain are complete, satisfying High durable false-evidence calibration without executing a poisoned real store. Validate the complete requested/manifest/entry/unit tuple and derived unit_ref before any text is reused or indexed.

