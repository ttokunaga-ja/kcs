# Attack-path analysis: Accepted embedding adapter targets are discarded before fixed Gemini execution

- Candidate: `KCS-R23-CAND-039`
- Ledger row: `KCS-R23-CAND-039`
- Instance key: `KCS-R23-CAND-039`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.97)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| accepted_surface | `crates/kcs-adapter/src/tool_lock.rs` | `106-231` | Embedding declarations accept execution target, model, and authentication fields. |
| lossy_projection | `crates/kcs-adapter/src/tool_lock.rs` | `376-428` | DeclaredAdapter drops execution kind, command, arguments, and URL. |
| auth_triggered_dispatch | `crates/kcs-adapter/src/catalog.rs` | `313-401` | Any declared embedding authentication reference selects real execution, which always constructs GeminiEmbeddingAdapter::default and ignores the declared target/model. |
| credential_data_sink | `crates/kcs-adapter/src/gemini_embedding.rs` | `48-149,206-220` | The fixed Gemini model/base client sends the retained declared secret and input text in authenticated requests. |
| preview_gap | `crates/kcs-cli/src/main.rs` | `8736-8797` | Preview shows generic embedding/network policy rather than the declared and effective provider/model target. |

## Scope and actor

### Context

This is a production embedding workflow. Operator-controlled configuration is projected into a fixed Gemini implementation, allowing an unintended remote provider to receive a custom-provider credential and indexed text.

### In scope

yes; discarded declarations, destination binding, and unexpected credential forwarding are explicit I3 concerns

### Exposure and identity

not inbound-public; local operator configuration triggers outbound disclosure to Gemini or an ambient GEMINI_API_BASE

The KCS operator authorizes the declared embedding adapter; the lower-trust unintended Gemini/effective-base recipient gains credential and text access not granted by that declaration.

### Boundary crossed

yes: the declared provider/model boundary is crossed when the fixed Gemini client receives and transmits the retained secret and text

### Authorization scope

admin-only (local KCS operator), with disclosure to an unintended remote recipient

## Preconditions and attacker control

### Assumptions

- The operator reasonably relies on the accepted embedding target and model declaration.
- The declared authentication secret resolves and text is eligible for embedding.
- General online approval does not authorize silent substitution of the declared recipient and model.

### Preconditions

- A non-Gemini, offline, command, private-URL, or different-model embedding declaration is accepted
- A resolvable declared embedding credential
- General online opt-in and an eligible embedding operation
- Later operator invocation and available budget

### Attacker control

no direct control of device-local configuration is required; the unintended remote provider is lower trust and receives data through KCS's target substitution

### Vector

none

## Attack path

- An operator configures an embedding adapter declaration containing a target kind, command or URL, model, and authentication reference.
- Validation accepts the declaration, but projection at crates/kcs-adapter/src/tool_lock.rs:376-428 drops the execution target fields.
- The presence of the declared authentication reference activates real embedding execution, whose profile and implementation are fixed to the adopted Gemini adapter and model.
- After ordinary online and budget gates, the fixed Gemini/effective-base client attaches the retained API secret and sends the input text to a recipient and model different from the accepted declaration.

## Impact and reach

- Category: adapter destination/model confusion and wrong-recipient credential/text disclosure
- Impact: **high**
- Likelihood: **medium**

### Impact surface

data and identity

### Target reach

one configured embedding workflow and each eligible text processed through it

### Secret references

- Declared embedding authentication secret, used as x-goog-api-key
- Input document or chunk text sent for embedding

## Controls and counterevidence

### Existing controls

- Reject unsupported embedding declarations, or dispatch only the exact declared target and model.
- Bind approval, credential resolution, declared profile/model, and final request origin to one canonical adapter identity.

### Mitigations

- Device-local configuration is normally controlled by the operator.
- Online opt-in, credential availability, and budget controls still gate execution.
- The current MVP is documented around official adapters.
- A programmatic or GEMINI_API_BASE override can align the fixed client, but is not derived from the declaration.

### Counterevidence

- The operator controls tools.toml and must enable online execution.
- The current MVP is described as supporting official adapters.
- No live loopback request captured the fixed-client send.
- An independently aligned GEMINI_API_BASE can avoid recipient drift.

### Blind spots or proof gap

- Dynamic request contents were not captured, although the static target-loss-to-sink trace is complete.
- The prevalence of non-Gemini declarations in real deployments is unknown.

## Final decision

Although an operator initiates the workflow, silent target substitution grants the unintended external recipient access to a credential and indexed text, so the hard operator-only/no-privilege-delta suppression does not apply. Explicit configuration and execution prerequisites constrain likelihood to medium; the matrix maps high impact and medium likelihood to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
