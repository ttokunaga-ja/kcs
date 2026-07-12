# Validation: same-batch duplicate embedding identities split authoritative and KNN vectors

- Candidate: `KCS-R23-CAND-068`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.99)**
- Method: **V1 bounded real-store reproduction + V5 identity proof + V10 complete trace**

Embedding identity is derived from text hash and profile, not chunk ID, at `crates/kcs-index/src/embedding_store.rs:10-27`. Two chunks with identical text can therefore share one embedding hash while retaining distinct chunk IDs. Batch planning probes every item before any write and does not group equal hashes at `crates/kcs-cli/src/main.rs:7675-7708`, so both misses enter the adapter request.

Responses are processed sequentially at `main.rs:7726-7769`. `write_chunk_embedding` inserts the authoritative `embeddings` row with `ON CONFLICT(id) DO NOTHING`, preserving the first vector, but then always calls `link_chunk_vec` with the current response vector at `crates/kcs-index/src/embedding_store.rs:86-145`. If an untrusted/variable adapter returns different vectors for the equal texts, the second chunk's KNN row differs from the authoritative content vector. Rebuild later relinks both chunks from the first row, changing search ordering/evidence selection across repair.

A bounded in-memory target-store control wrote two basis vectors under one embedding ID. The authoritative row retained the first, chunk A matched the first, and chunk B matched the second and conflicted with the authoritative row. Evidence: `validation_artifacts/control_output.json`. This is a directly reproduced authoritative-vector split from a normal same-batch source, meeting High calibration.

Group equal embedding hashes before sending, persist one canonical vector, link every member from the persisted bytes, and reject conflicting responses atomically.

