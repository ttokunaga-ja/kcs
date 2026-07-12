# Validation: Gemini vectors lack numeric-domain and positive-norm validation

- Candidate: `KCS-R23-CAND-003`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.99)**
- Method: **V1 bounded local probe + V5 numeric-domain proof + V10 exact trace**

## Evidence

The real Gemini parser converts every JSON number with `as_f64() as f32` and checks only array count and width at `crates/kcs-adapter/src/gemini_embedding.rs:153-203`. No post-cast finite, magnitude, or positive-norm predicate exists. The CLI returns query vectors unchanged at `crates/kcs-cli/src/main.rs:7184-7204`, and persists batch vectors at `crates/kcs-cli/src/main.rs:7727-7768`. The source-of-truth and sqlite-vec link accept width-correct bytes at `crates/kcs-index/src/embedding_store.rs:91-146`; KNN checks only byte width and decodes distance as f64 at `crates/kcs-index/src/embedding_store.rs:240-264`.

The isolated probe parsed finite JSON `3.5e38`, observed narrowing to `f32::INFINITY`, persisted and read the non-finite component, then received a NULL-distance decode error from KNN. An exact-width zero vector produced the same KNN failure. A finite basis-vector negative control returned distance 0.0. Evidence: `validation_artifacts/probe_output.json`.

## Counterevidence

JSON syntax rejects literal NaN/Infinity, normal mock vectors are normalized, width and request count are checked, and online adapter approval remains required. Those controls do not reject finite f64 values outside f32 range or zero-norm vectors. The stored malformed vector persists across later searches/rebuilds, so a remote response can durably disable vector search for the scope.

## Closure

Reportable High. Validate finite f32 range and positive finite norm before both query use and authoritative insertion; reuse/rebuild must reject legacy invalid blobs.

