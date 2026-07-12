# Codex Security Deep Scan Export

This directory is the repository-tracked export of the final accepted outputs
for the KCS deep security scan.

| Field | Value |
| --- | --- |
| Scan ID | `f78f5d0d-2752-47a7-8d8d-3371e09d3377` |
| Repository | `https://github.com/ttokunaga-ja/kcs` |
| Target revision | `0e19f3c6489da458e93a982a333c308d92d0a0ae` |
| Mode and scope | `deep`, `.` |
| Completed | `2026-07-11T20:52:16Z` |
| Coverage | `420/420` |
| Final findings | `47` |

## Contents

- `report.md`, `findings.json`, `coverage.json`, and `scan-manifest.json` are
  the canonical final scan outputs.
- `exports/results.sarif` is the machine-readable SARIF export.
- `hardening/` contains the generated hardening portfolio and its context.
- `findings/` contains the final indexed report path and receipt-bound original
  report path for every finding, its local synthetic PoC material, and
  colocated accepted provenance files.
- `artifacts/05_findings/` contains the final validation, attack-path, ledger,
  receipt, worklist, and provenance-audit evidence used during reporting.
- `artifacts/fix_report.md` records the remediation implementation and
  verification completed after the scan.
- `SHA256SUMS` binds every exported file other than the checksum file itself.

All generated source artifacts were copied byte-for-byte. The export excludes
the transient 560 MB discovery workspace, superseded or rejected write-up
attempts outside the accepted final paths, duplicate raw validation fixtures,
caches, build outputs, and session logs. Those items are not part of the final
report package and may contain host-local implementation state.
