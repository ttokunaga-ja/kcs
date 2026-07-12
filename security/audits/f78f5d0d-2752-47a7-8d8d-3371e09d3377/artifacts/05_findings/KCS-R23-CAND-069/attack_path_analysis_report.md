# Attack-path analysis: Inline EvidencePointer raw_hash escapes tombstone storage and discloses arbitrary JSON files

- Candidate: `KCS-R23-CAND-069`
- Ledger row: `KCS-R23-CAND-069`
- Instance key: `KCS-R23-CAND-069:inline-raw-hash-tombstone-read`
- Final policy: **reportable**
- Final severity: **high**
- Priority: **P1**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-search/src/evidence.rs` | `9-30` |  |
| root_control | `crates/kcs-cli/src/main.rs` | `4576-4586` |  |
| reachable_branch | `crates/kcs-cli/src/main.rs` | `4773-4784` |  |
| file_read_sink | `crates/kcs-cli/src/main.rs` | `5207-5226` |  |
| disclosure_sink | `crates/kcs-cli/src/main.rs` | `5227-5249,11184-11190` |  |

## Scope and actor

### Context

The path crosses from partially trusted CLI/pointer input into filesystem reads outside the selected scope under the KCS user's identity, then crosses back through structured error output to the lower-trust caller.

### In scope

Yes.

### Exposure and identity

Local CLI/stdin and agent-tool input surface; there is no KCS listener, but calling automation is an explicit threat-model actor and consumes JSON output.

The KCS process reads with the invoking user's filesystem privileges. The lower-trust caller needs pointer-input authority but does not otherwise need read permission to the selected JSON file.

### Boundary crossed

Yes.

### Authorization scope

partially trusted calling automation or agent input with no authorization to read arbitrary user files

## Preconditions and attacker control

### Assumptions

- A calling automation, agent, or operator passes attacker-authored inline pointer text to open, view, or verify and returns structured errors to the caller.
- The attacker can reuse a legitimate scope_id/scope_path and existing commit, which are routinely present in a valid pointer.
- The chosen target is readable by the KCS OS identity and contains parseable JSON.
- The supplied raw_hash is absent from the selected commit tree so tombstone lookup is reached.

### Preconditions

- The caller must cause a KCS pointer-resolution command to process inline JSON.
- A real scope and existing commit must be named.
- The target file must be process-readable and valid JSON.
- Structured JSON error output must be returned or exposed to the caller.

### Attacker control

yes: the lower-trust caller directly controls inline raw_hash and can select an absolute or traversal-bearing path while reusing legitimate pointer metadata

### Vector

none

## Attack path

- A lower-trust caller supplies an inline EvidencePointer JSON object containing a legitimate scope identity and existing commit but an absolute or parent-bearing raw_hash naming a process-readable JSON file.
- The inline parser checks schema_version only and deserializes raw_hash as an unconstrained string, bypassing the strict hash validation used by the short-hash and URI routes.
- The valid commit does not contain that attacker value, so resolution reaches tombstone lookup before returning not-found.
- Tombstone path construction joins the unvalidated raw_hash as the final path component; an absolute component replaces the intended tombstone prefix and fs::read opens the attacker-selected file.
- KCS parses the file as JSON, retains its fields in KcsError.context, and emits the full context in JSON mode to the calling automation or agent.

## Impact and reach

- Category: path traversal, arbitrary local JSON file read, and structured error disclosure
- Impact: **high**
- Likelihood: **high**

### Impact surface

confidentiality of user-readable JSON configuration, application state, and credential material outside the selected scope

### Target reach

any process-readable parseable JSON file addressable on the local filesystem, repeatable across pointer invocations

### Secret references

- Potential targets include JSON credential stores, tokens, service configuration, and application state readable by the invoking user.
- The exact exposed secret depends on local file formats and permissions; non-JSON files are not reflected by this sink.

## Controls and counterevidence

### Existing controls

- Scope ID/path resolution and commit existence checks constrain which repository context reaches tombstone lookup.
- validate_short_hash_operand exists for another operand form but is not applied to inline pointers.
- read_tombstone checks only minimal digest length and performs no component or canonical containment validation.
- KcsError JSON serialization preserves the parsed tombstone object as context.

### Mitigations

- Scope resolution and commit existence are validated before tombstone access.
- The target must be readable under the KCS user's OS identity and parse as JSON.
- Human error output emits code/message rather than full context.
- URI and short-hash routes impose stronger syntax constraints; the strongest escape is specific to supported inline JSON.

### Counterevidence

- The attacker must know or obtain a valid scope identity and existing commit and must induce pointer resolution.
- Only process-readable parseable JSON is returned, and disclosure requires structured JSON output; ordinary human output omits the context.
- No file write, code execution, or general non-JSON file disclosure is established.
- URI pointers do not permit the same slash-bearing raw_hash form, but inline JSON is a separately supported input surface.

### Blind spots or proof gap

- The repository does not enumerate every external agent/tool integration that forwards attacker pointer text and returns JSON errors.
- No real secret file was read during validation; the conclusion rests on a complete source-to-output trace and safe lexical path observation.

## Final decision

A partially trusted calling automation is explicitly in scope, controls the pointer operand, and can receive structured output. The complete trace provides a direct arbitrary JSON read outside the chosen scope with potential credential exposure and no speculative chain. High impact with High likelihood maps to High/P1; Critical is not justified because valid repository context, JSON format, readable permissions, and tool invocation remain prerequisites and no code execution or broad automatic exfiltration is shown.

The strict impact/likelihood matrix therefore yields **high**
with policy **reportable** and priority **P1**.
