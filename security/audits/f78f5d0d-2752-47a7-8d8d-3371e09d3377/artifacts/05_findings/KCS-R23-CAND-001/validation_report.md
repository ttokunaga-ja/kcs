# Validation: secret-hold cycles erase terminal embedding failure state

- Candidate: `KCS-R23-CAND-001`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V1 isolated same-revision lifecycle reproduction + V10 exact state trace**

The hold demotion selector includes every non-Done, non-retired embedding task at `crates/kcs-cli/src/main.rs:8221-8231`, including permanent `Failed(contract_violation|auth_error|invalid_input)` and exhausted bounded failures. Demotion overwrites the reason with `secrets_tier_b_hold`, clears retry time, and resets attempts at `main.rs:8295-8325`. When the same content becomes non-secret, unhold converts that Paused row into fresh Pending work with attempts zero at `main.rs:8360-8368,8463-8484`. The normal enrichment path then reserves cost and sends it at `main.rs:7340-7345,7727-7768`.

This destroys the retry contract at `crates/kcs-pipeline/src/task.rs:320-378`, where AuthError/InvalidInput/ContractViolation are non-retryable and NetworkError has a finite cap. Preserved isolated target-binary reproductions injected `Failed(contract_violation)`, renamed the file into a Tier-B name and back, and observed a new adapter attempt, reservation, and replacement rate-limit failure; no real endpoint/key was used.

Countercontrols keep Done tasks and retired-non-live tasks out of demotion, but do not preserve terminal failure provenance. Impact is bounded repeated sends/cost and state-integrity loss under operator-driven rename/index cycles, supporting Medium. Preserve/restore the pre-hold state or exclude terminal failures from destructive demotion.

