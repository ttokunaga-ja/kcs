# R1-R22 exploratory audit record

Status: **historical, non-authorizing**. This file preserves only the aggregate
provenance that was unique to the former reusable audit runbook. It is not an
instruction to start another audit, and its old prompts, environment setup,
model roster, implementation snapshot, and Step 4 work order were removed.
Current authority is the canonical `docs/`, Rust implementation and tests, and
`.github/workflows/ci.yml`.

The audits used independent implementation review followed by adjudication and
reproduction. R14-R22 used seven review lanes; R22 replaced the prior static
GPT-5.5 lane with GPT-5.6 Sol Ultra. Detailed findings, rejected candidates,
fixes, and reproduction evidence remain in the corresponding adjudication
records below.

| Round | Accepted findings | Detailed record |
| --- | --- | --- |
| R1 | 1 critical, 7 major | [step3-bughunt-fixes.md](step3-bughunt-fixes.md) |
| R2 | 1 critical, 6 major, 1 minor | [step3-bughunt2-fixes.md](step3-bughunt2-fixes.md) |
| R3 | 2 critical, 3 major, 2 minor | [step3-bughunt3-fixes.md](step3-bughunt3-fixes.md) |
| R4 | 1 critical, 4 major, 5 minor | [step3-bughunt4-fixes.md](step3-bughunt4-fixes.md) |
| R5 | 4 major, 2 minor | [step3-bughunt5-fixes.md](step3-bughunt5-fixes.md) |
| R6 | 1 critical, 3 major, 4 minor | [step3-bughunt6-fixes.md](step3-bughunt6-fixes.md) |
| R7 | 1 critical, 4 major | [step3-bughunt7-fixes.md](step3-bughunt7-fixes.md) |
| R8 | 6 major, 2 minor, 1 design decision | [step3-bughunt8-fixes.md](step3-bughunt8-fixes.md) |
| R9 | 5 major, 3 minor | [step3-bughunt9-fixes.md](step3-bughunt9-fixes.md) |
| R10 | 6 major, 2 minor | [step3-bughunt10-fixes.md](step3-bughunt10-fixes.md) |
| R11 | 7 major, 4 minor | [step3-bughunt11-fixes.md](step3-bughunt11-fixes.md) |
| R12 | 4 major, 3 minor | [step3-bughunt12-fixes.md](step3-bughunt12-fixes.md) |
| R13 | 4 major, 2 minor | [step3-bughunt13-fixes.md](step3-bughunt13-fixes.md) |
| R14 | 4 major, 2 minor | [step3-bughunt14-fixes.md](step3-bughunt14-fixes.md) |
| R15 | 6 major, 2 minor | [step3-bughunt15-fixes.md](step3-bughunt15-fixes.md) |
| R16 | 6 major, 1 minor | [step3-bughunt16-fixes.md](step3-bughunt16-fixes.md) |
| R17 | 3 major, 4 minor | [step3-bughunt17-fixes.md](step3-bughunt17-fixes.md) |
| R18 | 2 major, 2 minor | [step3-bughunt18-fixes.md](step3-bughunt18-fixes.md) |
| R19 | 4 major, 4 minor | [step3-bughunt19-fixes.md](step3-bughunt19-fixes.md) |
| R20 | 1 critical, 5 major, 5 minor | [step3-bughunt20-fixes.md](step3-bughunt20-fixes.md) |
| R21 | 1 critical, 5 major, 1 minor | [step3-bughunt21-fixes.md](step3-bughunt21-fixes.md) |
| R22 | 6 major, 2 minor | [step3-bughunt22-fixes.md](step3-bughunt22-fixes.md) |

The recurring lesson retained from these rounds is evidentiary rather than
procedural: independently reproduce candidate failures, audit the siblings of a
fix, and treat a historical finding count as evidence about its measured HEAD,
not as a statement about the current tree.
