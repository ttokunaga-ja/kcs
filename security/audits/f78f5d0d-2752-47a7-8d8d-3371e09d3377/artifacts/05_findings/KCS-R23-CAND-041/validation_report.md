# Validation: closing snapshot can ingest a newly introduced Tier-A secret

- Candidate: `KCS-R23-CAND-041`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.96)**
- Method: **V10 exact two-enumeration interleaving**

Manual snapshot first builds a scan preview and converts only the names currently marked ignored into an exclusion set at `crates/kcs-cli/src/main.rs:456-472`. Index follows the same preview-to-auto-snapshot pattern at `main.rs:575-580,623-635`. The later snapshot enumerates the root again and excludes only exact names already in that set at `crates/kcs-core/src/scope.rs:254-299`; it never re-runs Tier-A classification.

A concurrent content writer can create or rename `.env`, `*.pem`, or another Tier-A direct child after preview but before the closing enumeration. The new name is absent from the stale exclusion set, so snapshot reads it, writes the plaintext raw object, and publishes it in commit history. Normal stable inputs and secrets present during preview are correctly excluded.

No barrier-controlled race was run. Central severity is Medium because the trace proves a policy race and irreversible local archive inclusion, but practical timing was not measured and the owner-only store limits immediate disclosure. Closure requires classifying each closing-snapshot entry (or binding the preview candidate identity) before raw persistence.

