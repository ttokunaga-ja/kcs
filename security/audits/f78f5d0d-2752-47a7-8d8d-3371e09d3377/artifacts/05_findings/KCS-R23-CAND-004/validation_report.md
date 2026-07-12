# Validation: OCR bounding-box arithmetic can overflow

- Candidate: `KCS-R23-CAND-004`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **medium**
- Confidence: **high (0.97)**
- Method: **V1 bounded arithmetic control + V5 domain proof + V10 exact trace**

## Evidence

Remote OCR coordinate values are deserialized as signed 64-bit integers and normalized with unchecked `x + w` and `y + h` at `crates/kcs-adapter/src/mistral_ocr.rs:434-463`. The resulting boxes flow into extracted-image metadata at `crates/kcs-adapter/src/mistral_ocr.rs:398-422,466-480`. No range or geometry predicate precedes the additions.

A bounded local control demonstrates that `i64::MAX + 1` panics in the current debug profile while `checked_add` returns `None`, and ordinary 10+20 remains 30. Evidence: `validation_artifacts/probe_output.txt`. Release wrapping would instead create invalid coordinates, so neither build mode fails safely.

## Counterevidence

Only OCR responses that include the accepted array form with extreme coordinates reach the operation; object/corner forms that avoid the addition are unaffected. The failure is confined to the OCR operation and does not itself bypass authorization.

## Closure

Reportable Medium. Use checked arithmetic and reject negative, overflowing, inverted, or unreasonable boxes before metadata construction.

