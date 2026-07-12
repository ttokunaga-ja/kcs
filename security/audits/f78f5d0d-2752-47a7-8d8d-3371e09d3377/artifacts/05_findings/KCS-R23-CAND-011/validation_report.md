# Validation: a new secret content twin is vector-linked before its hold exists

- Candidate: `KCS-R23-CAND-011`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V1 isolated same-revision lifecycle reproduction + V10 exact ordering trace**

Index publishes the snapshot and calls `rebuild_step3_index` before `generate_scope_embeddings` at `crates/kcs-cli/src/main.rs:620-653`. Rebuild derives its denylist only from already persisted Paused `secrets_tier_b_hold` tasks at `main.rs:3008-3027`, then `rebuild_chunk_vec` links every non-denied chunk to an existing embedding by text hash at `crates/kcs-index/src/embedding_store.rs:149-185`.

A newly introduced Tier-B file has no hold task yet. If its chunk text has a previously embedded public twin, rebuild links the new secret chunk ID immediately. Later `live_chunks_without_embedding` sees both an authoritative content vector and an existing `chunk_vec` row and filters the chunk out before secret partition/hold creation at `crates/kcs-cli/src/main.rs:7848-7936`. The denylist can therefore never catch up.

A preserved isolated target reproduction embedded a public chunk, added a byte-identical secret-labeled document without `--send-secrets`, observed no hold task for the secret chunk, and received that chunk as the top vector result. The content text already has a public twin, constraining confidentiality to secret path/provenance and policy visibility; no unauthorized network send occurs. Reportable Medium. Create/derive current live secret holds before content-hash relinking, or pass a current classifier-derived denylist into rebuild.

