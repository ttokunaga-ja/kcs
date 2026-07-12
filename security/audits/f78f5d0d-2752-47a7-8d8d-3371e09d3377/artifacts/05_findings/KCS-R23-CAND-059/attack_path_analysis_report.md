# Attack-path analysis: Human-readable CLI output emits untrusted terminal control sequences

- Candidate: `KCS-R23-CAND-059`
- Ledger row: `KCS-R23-CAND-059`
- Instance key: `KCS-R23-CAND-059:terminal-control-human-output`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| view_entrypoint | `crates/kcs-cli/src/main.rs` | `2816-2835` |  |
| stored_text_source | `crates/kcs-cli/src/main.rs` | `4823-4859` |  |
| human_output_sink | `crates/kcs-cli/src/main.rs` | `11135-11176` |  |
| human_error_sink | `crates/kcs-cli/src/main.rs` | `11184-11193` |  |

## Scope and actor

### Context

Untrusted repository/store strings are data until KCS writes them to an interactive terminal, where control bytes become terminal instructions. This is a real product surface with an ordinary one-command user interaction, though it does not by itself grant OS privileges or shell execution.

### In scope

Yes.

### Exposure and identity

Interactive local terminal output; no network listener, port, ingress, or load balancer.

KCS runs as the operator and writes to that operator's terminal. The lower-trust content contributor controls stored strings but not the OS identity or terminal configuration.

### Boundary crossed

Yes.

### Authorization scope

internal-only local operator terminal workflow

## Preconditions and attacker control

### Assumptions

- The hostile string reaches one of the documented human-output fields.
- The operator uses default human output in a control-sequence-aware terminal rather than --json or a non-terminal sink.
- The terminal supports at least display manipulation; stronger OSC effects depend on its policy.

### Preconditions

- Control a filename, indexed text/OCR response, or persisted commit message in a scope the victim inspects.
- The victim invokes a human-readable command in an interactive terminal.
- The desired terminal action must be enabled by that emulator for effects stronger than output spoofing.

### Attacker control

yes over the emitted string; the operator controls command invocation and terminal policy

### Vector

none

## Attack path

- A lower-trust contributor places ESC/C0, bidi, newline, or terminal-active sequences in a direct-child filename, indexed document/OCR text, or commit message.
- The operator runs a routine human-readable view, status, diff, or log command on the hostile scope.
- The non-JSON branches interpolate the string directly into println without a terminal-safe renderer.
- The interactive terminal interprets the bytes, enabling trusted-output spoofing and, depending on emulator policy, deceptive hyperlinks, title rewriting, or clipboard/control actions.

## Impact and reach

- Category: terminal control-sequence injection and output spoofing
- Impact: **medium**
- Likelihood: **high**

### Impact surface

operator-interface integrity and emulator-dependent terminal state

### Target reach

one operator terminal session and command output at a time

### Secret references

- Clipboard content could be overwritten or solicited only when the terminal implements and enables the corresponding OSC behavior; no secret exfiltration was demonstrated.

## Controls and counterevidence

### Existing controls

- Route every untrusted human-output string through one visible terminal-safe escaping renderer.
- Cover C0, ESC, CSI, OSC, bidi controls, newlines, and hyperlink delimiters while preserving JSON semantics.
- Retain structured --json output as the automation-safe interface.

### Mitigations

- JSON output uses serde_json serialization and escapes control bytes.
- Piping output into a non-terminal generally prevents terminal interpretation.
- Many terminals gate or disable high-impact OSC actions.

### Counterevidence

- The --json path is already safe against raw control-byte interpretation.
- Terminal policies vary and may ignore title, hyperlink, or clipboard sequences.
- No shell execution, OS permission crossing, or credential theft was established.
- A live control sequence was intentionally not emitted during validation.

### Blind spots or proof gap

- The exact effect varies across terminal emulators and user configuration.
- The relative frequency of human versus --json operation is not measured.

## Final decision

A lower-trust contributor can deterministically place control bytes in common status/view inputs, and a routine human command reaches the sink without a race or privileged prerequisite. The impact is bounded to terminal/operator integrity rather than code execution, so Medium impact plus High likelihood maps mechanically to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
