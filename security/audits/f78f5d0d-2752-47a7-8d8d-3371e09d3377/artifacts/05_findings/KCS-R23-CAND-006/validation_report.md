# Validation: lexical PDF page markers amplify derived work without a cardinality bound

- Candidate: `KCS-R23-CAND-006`
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.99)**
- Method: **V1 bounded growth probe + V5 complexity proof + V10 exact trace**

## Evidence

The deterministic PDF helper counts raw textual `/Page` prefixes rather than structural page objects at `crates/kcs-adapter/src/deterministic.rs:415-437`. That count pads the page vector at `crates/kcs-pipeline/src/prepare.rs:315-349`, and preparation creates an owned `PreparedUnit` per page at `crates/kcs-pipeline/src/prepare.rs:102-170`. Normal indexing applies only a byte cap before this expansion at `crates/kcs-cli/src/main.rs:9047-9110`.

The bounded probe used one printable stream plus 1, 4, 16, and 64 compact `/PageX` markers. Page count, page-vector length, and prepared-unit count each equaled marker count. Under the default 100 MiB byte cap, the same six-byte token permits approximately 17,476,260 synthetic pages. Evidence: `validation_artifacts/probe_output.json`.

## Counterevidence

The input-byte cap and scanned-PDF fallback limit some inputs. They do not cap derived page cardinality; a single printable stream keeps the deterministic path active. The large case was computed, not allocated, to keep validation safe.

## Closure

Reportable High: an ordinary untrusted PDF can cause persistent process-wide resource exhaustion whenever indexed. Replace lexical count with structural bounded parsing and enforce a derived-page/unit ceiling.

