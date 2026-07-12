# Validation: closing snapshot can attach normalization metadata to different bytes

- Candidate: `KCS-R23-CAND-042`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.97)**
- Method: **V10 exact verified-normalization-to-publication interleaving**

Index reads candidate bytes, rehashes them against the scan identity, normalizes and persists units, then records only a path-keyed `NormalizeRef { tool_profile_hash, gen }` in `normalize_by_path` at `crates/kcs-cli/src/main.rs:9077-9103,9390-9426`. Auto-snapshot later enumerates and rereads the path at `crates/kcs-core/src/scope.rs:254-299`, computes the current raw hash, and attaches the earlier path's NormalizeRef without any expected-raw-hash comparison.

If the file changes after normalization but before closing snapshot, the tree records new raw bytes with a normalization reference produced for the old raw hash. Rebuild then resolves units using the tree's new raw hash and the stale profile/gen at `crates/kcs-cli/src/main.rs:3045-3090`, yielding missing/skipped enrichment and false historical provenance.

The earlier scan-to-normalize guard is correct; it does not bind the later publication. No scheduler-controlled race was run, so Medium—not High—is assigned. Fix by carrying expected raw hash with each path mapping and rejecting/draining drift before attaching NormalizeRef.

