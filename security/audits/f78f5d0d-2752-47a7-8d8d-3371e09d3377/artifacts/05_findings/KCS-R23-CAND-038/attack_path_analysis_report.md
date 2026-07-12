# Attack-path analysis: Accepted markdown adapter targets are discarded before fixed Mistral execution

- Candidate: `KCS-R23-CAND-038`
- Ledger row: `KCS-R23-CAND-038`
- Instance key: `KCS-R23-CAND-038`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.96)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| accepted_surface | `crates/kcs-adapter/src/tool_lock.rs` | `106-231` | Markdown declarations accept execution kind, command, arguments, URL, model, and authentication fields. |
| lossy_projection | `crates/kcs-adapter/src/tool_lock.rs` | `376-428` | DeclaredAdapter retains only tool ID, model, and auth and drops the accepted execution target fields. |
| fixed_dispatch | `crates/kcs-adapter/src/catalog.rs` | `82-156` | Normal production markdown execution always constructs the Mistral OCR adapter, consulting only the retained declared model. |
| credential_data_sink | `crates/kcs-adapter/src/mistral_ocr.rs` | `47-138` | The retained declared secret and freshly read document bytes are sent through the fixed Mistral/effective-base client. |
| preview_gap | `crates/kcs-cli/src/main.rs` | `8736-8797` | Preview shows generic network policy rather than the declared and effective command/URL recipient. |

## Scope and actor

### Context

This is a real production adapter-selection workflow. Device-local configuration is operator-controlled, yet KCS turns a declaration for one provider or command into an authenticated document request to another provider, creating an unintended-recipient confidentiality boundary.

### In scope

yes; the threat model expressly keeps discarded adapter declarations and unexpected credential forwarding in scope under I3

### Exposure and identity

not inbound-public; local operator configuration triggers outbound network disclosure to the fixed Mistral or ambient effective base

The KCS operator authorizes the declared adapter; the lower-trust unintended Mistral/effective-base recipient gains document and credential access not conferred by that declaration.

### Boundary crossed

yes: credential and document bytes cross from the approved declared target boundary to a different external service

### Authorization scope

admin-only (local KCS operator), with disclosure to an unintended remote recipient

## Preconditions and attacker control

### Assumptions

- The operator reasonably relies on the accepted target declaration rather than separately matching MISTRAL_API_BASE to it.
- The declared authentication secret resolves and an eligible document is processed.
- General online approval is granted, but it is not approval for the substituted recipient.

### Preconditions

- A non-Mistral or command/offline markdown declaration is accepted
- A resolvable declared bearer credential
- General online opt-in and an eligible OCR document
- Later operator invocation and available budget

### Attacker control

no direct control of device-local configuration is required; the unintended external recipient is lower trust and passively receives data because KCS substitutes the target

### Vector

none

## Attack path

- An operator configures a markdown adapter declaration containing a target kind, command or URL, model, and authentication reference.
- Validation accepts those fields, but projection to DeclaredAdapter at crates/kcs-adapter/src/tool_lock.rs:376-428 drops kind, command, arguments, and URL.
- The production catalog unconditionally constructs the Mistral OCR implementation while retaining the declared model and authentication reference.
- After ordinary online, credential, media, and budget gates, the fixed Mistral/effective-base client attaches the retained bearer credential and uploads the eligible document to a recipient different from the accepted declaration.

## Impact and reach

- Category: adapter destination confusion and wrong-recipient credential/document disclosure
- Impact: **high**
- Likelihood: **medium**

### Impact surface

data and identity

### Target reach

one configured markdown adapter workflow and each eligible document processed through it

### Secret references

- Declared markdown authentication secret, attached as bearer authentication
- Eligible document bytes uploaded for OCR

## Controls and counterevidence

### Existing controls

- Reject unsupported execution kinds and targets before approval, or dispatch only the exact declared target.
- Bind preview, approval, credential resolution, model, and final request origin to the same canonical adapter identity.

### Mitigations

- Device-local tools configuration is normally operator-controlled.
- Outer online opt-in, credential presence, media eligibility, and budget checks still apply.
- The declared model is retained for markdown execution.
- Documentation describes an official-adapter MVP, although unsupported declarations are accepted rather than rejected.

### Counterevidence

- The operator controls tools.toml and must enable online execution.
- The current MVP is described as supporting official adapters.
- No live loopback request captured the substituted request.
- An operator who independently aligns MISTRAL_API_BASE with the declared service can avoid recipient drift.

### Blind spots or proof gap

- Dynamic request contents were not captured, although the static accepted-config-to-sink trace is complete.
- The prevalence of non-Mistral declarations in real deployments is unknown.

## Final decision

The operator-only trigger does not force suppression because KCS creates a concrete privilege delta for an unintended external recipient: it receives a provider-specific credential and document that the accepted declaration did not authorize. The explicit configuration and online-invocation prerequisites constrain likelihood to medium; high impact multiplied by medium likelihood maps mechanically to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
