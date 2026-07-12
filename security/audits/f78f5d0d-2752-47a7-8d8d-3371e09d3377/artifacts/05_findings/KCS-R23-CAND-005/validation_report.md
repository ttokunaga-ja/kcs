# Validation: byte-oriented question-mark globs bypass Unicode names

- Candidate: `KCS-R23-CAND-005`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.99)**
- Method: **V1 isolated scan probe + V10 exact policy-to-sink trace**

## Evidence

Ignore paths and patterns are normalized as strings and converted to UTF-8 bytes at `crates/kcs-pipeline/src/scan.rs:341-380`. The `?` arm advances both pattern and path by exactly one byte at `crates/kcs-pipeline/src/scan.rs:383-415`, not one Unicode scalar. Ignore decisions govern candidate ingestion at `crates/kcs-pipeline/src/scan.rs:97-159`; accepted content reaches index/normalization at `crates/kcs-cli/src/main.rs:9044-9118` and eligible online OCR/embedding paths thereafter.

The isolated scope used rule `?.txt`. `a.txt` was excluded, while precomposed `é.txt`, decomposed `é.txt`, and `😀.txt` were not; the actual scan preview likewise marked `a.txt` ignored and `é.txt` included. Evidence: `validation_artifacts/probe_output.json`.

## Counterevidence

Explicit literal rules, `*`, secret-name classification, offline mode, and authorization gates can independently prevent particular sinks. They do not preserve the operator's one-character ignore policy for Unicode filenames. A lower-trust scope contributor can choose the name while the operator relies on the rule.

## Closure

Reportable High because a declared exclusion boundary can be bypassed before archive and approved network processing. Match Unicode scalar values (or documented normalized grapheme semantics) and add NFC/NFD/non-BMP controls.

