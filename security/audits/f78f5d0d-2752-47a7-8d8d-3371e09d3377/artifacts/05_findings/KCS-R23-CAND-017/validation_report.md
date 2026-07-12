# Validation: recursive star matching has exponential backtracking

- Candidate: `KCS-R23-CAND-017`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.99)**
- Method: **V1 bounded timing probe + V5 recurrence proof + V10 exact trace**

## Evidence

Scope-controlled `.kcsignore` lines are accepted without length/complexity limits at `crates/kcs-pipeline/src/scan.rs:178-200`. Every candidate is evaluated against each rule at `crates/kcs-pipeline/src/scan.rs:90-159,315-327`. The star branch recursively explores both zero-consumption and input-consumption states without memoization at `crates/kcs-pipeline/src/scan.rs:383-415`. Snapshot and index synchronously build this preview at `crates/kcs-cli/src/main.rs:452-472,558-580`.

For pattern `(*a)^n b` against `a^n`, the exact recurrence is `2^(n+2)-3`. The bounded probe grew from 1,021 recursive calls at n=8 to 1,048,573 at n=18, with measured time rising to about 17.6 ms; a linear successful control completed in microseconds. Larger cases were not run. Evidence: `validation_artifacts/probe_output.json`.

## Counterevidence

The scope is local and the operator can remove the rule; there is no daemon or cross-scope persistence. Simple globs remain fast. These conditions constrain severity but do not close the ordinary supplied-scope availability boundary.

## Closure

Reportable Medium. Replace recursive backtracking with memoized/iterative matching and impose pattern/rule work limits.

