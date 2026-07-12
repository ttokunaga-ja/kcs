# Attack-path analysis: byte-oriented question-mark globs bypass Unicode names

- Candidate: `KCS-R23-CAND-005`
- Ledger row: `KCS-R23-CAND-005`
- Instance key: `KCS-R23-CAND-005`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| normalization and byte projection | `crates/kcs-pipeline/src/scan.rs` | `341-380` |  |
| question wildcard | `crates/kcs-pipeline/src/scan.rs` | `383-415` |  |
| ingest decision | `crates/kcs-pipeline/src/scan.rs` | `97-159` |  |
| processing sink | `crates/kcs-cli/src/main.rs` | `9044-9118` |  |

## Scope and actor

### Context

The scope contributor is explicitly untrusted, and .kcsignore participates in scope and send eligibility. The bypass crosses the operator's declared exclusion boundary before durable archive or approved remote processing.

### In scope

Yes.

### Exposure and identity

Operator-mediated local filesystem input; any later network transfer is outbound and separately adapter-approved.

The lower-trust contributor controls the pathname and bytes; KCS consumes them with the operator's archive and optional adapter authority.

### Boundary crossed

Yes.

### Authorization scope

local untrusted scope content; optional outbound processing under prior adapter approval

## Preconditions and attacker control

### Assumptions

- A local content contributor can control direct-child filenames in a scope the operator indexes.
- The operator reasonably interprets ? as one Unicode character.
- For network impact, online processing is enabled and no independent secret/offline gate blocks the file.

### Preconditions

- The relevant ignore rule uses ?.
- The attacker chooses a precomposed, decomposed, or non-BMP Unicode filename that should satisfy the one-character policy.
- The operator runs indexing; a remote sink additionally requires existing online authorization.

### Attacker control

yes: an in-scope local content contributor directly controls the Unicode filename and file bytes

### Vector

none

## Attack path

- The operator defines a one-character .kcsignore rule such as ?.txt and relies on it as an exclusion boundary.
- A lower-trust scope contributor supplies a direct child whose one visible character occupies multiple UTF-8 bytes.
- The question-mark matcher advances one byte, so the Unicode path does not match while an ASCII peer does.
- The file becomes eligible for archive ingestion, normalization, and—when separately approved—online OCR or embedding despite the declared exclusion.

## Impact and reach

- Category: Unicode ignore-policy bypass and unintended scope/network eligibility
- Impact: **high**
- Likelihood: **medium**

### Impact surface

scope confidentiality/policy, archive contents, and potential remote data egress

### Target reach

each crafted direct-child filename within the selected scope

### Secret references

- A bypassed file could contain document secrets, but independent secret classification may still hold it.
- Adapter credentials are used only if online processing was already authorized.

## Controls and counterevidence

### Existing controls

- Direct-child scope policy.
- Other ignore rule forms.
- Secret Tier A/B classification.
- Offline and per-adapter authorization gates.

### Mitigations

- Literal and star rules can independently exclude a file.
- Secret classification, offline mode, and adapter approval can prevent a particular network send.
- The operator must invoke indexing.

### Counterevidence

- The bypass does not defeat literal rules, star rules, secret classification, offline mode, or adapter consent.
- The contributor generally knows content it supplies, limiting attacker-centric confidentiality impact.
- Operator invocation remains necessary.

### Blind spots or proof gap

- The receipts demonstrate eligibility and scan inclusion, but not an end-to-end transmission of a sensitive victim-owned file.
- Documented intended semantics for ? are inferred from ordinary character-glob expectations rather than an explicit Unicode contract.

## Final decision

A realistic lower-trust filename bypasses an operator-declared scope boundary and can make excluded bytes durable or remotely eligible. The potential confidentiality/policy impact is High, but the specific ? rule, Unicode name, operator action, and independent gates make likelihood Medium; the matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
