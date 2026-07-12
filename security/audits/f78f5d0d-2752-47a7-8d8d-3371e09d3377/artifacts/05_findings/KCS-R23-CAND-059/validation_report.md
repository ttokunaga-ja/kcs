# Validation: Human-readable CLI output emits untrusted terminal control sequences

## Identity and decision

| Field | Value |
| --- | --- |
| Candidate id / ledger row id | KCS-R23-CAND-059 |
| Instance key | KCS-R23-CAND-059:terminal-control-human-output |
| Advisory/source reference | R23 deep discovery; no external advisory |
| Seed anchor | crates/kcs-cli/src/main.rs:11135-11193 |
| Root control | crates/kcs-cli/src/main.rs:11135-11184 |
| Disposition | reportable |
| Survives validation | yes |
| Confidence | high |
| Confidence score | 0.93 |
| Severity | medium |
| Validation method | V10 complete untrusted-string-to-terminal trace plus non-emitting byte/JSON encoding control |

The candidate survives at Medium. KCS correctly JSON-serializes machine output, but its human output paths interpolate stored document text, commit messages, and relative paths directly into `println!`. A malicious or merely untrusted scope can therefore send ESC/C0 control bytes to an interactive terminal and trigger display spoofing or terminal-supported actions.

## Validation rubric

- [x] Source: stored document/OCR text reaches `view`, while repository filenames and persisted commit messages populate human result fields.
- [x] Closest control: the JSON branch calls `serde_json::to_string`, which escapes control characters, at crates/kcs-cli/src/main.rs:11135-11143.
- [x] Root-control gap: the human text, commit, changes, and files branches interpolate raw strings at crates/kcs-cli/src/main.rs:11144-11176.
- [x] Sink/impact: `println!` writes those bytes to the invoking terminal; supported emulators may apply title, hyperlink, display, or clipboard control actions.
- [x] Countercontrol: a synthetic control-bearing byte string was represented only as hex and escaped JSON; the raw form contained ESC while JSON contained no raw ESC byte.

## Exact source, control, sink, and boundary

- Source and boundary: an operator can inspect a repository or copied KCS scope containing untrusted text, filenames, or commit metadata. Those strings are data at the repository/store boundary but become instructions at a control-sequence-aware terminal boundary.
- Document-text source: `run_view` returns a selected stored chunk at crates/kcs-cli/src/main.rs:2816-2835, and the chunk text is loaded from `chunks.jsonl` at 4823-4859. The generic printer selects the `text` field and emits it verbatim at 11144-11149.
- Commit source: persisted snapshot messages are returned in the `commits` array and printed raw with hash and timestamp at crates/kcs-cli/src/main.rs:11151-11158.
- Path sources: diff/status result `relative_path` values are printed without escaping at crates/kcs-cli/src/main.rs:11160-11176. Direct-child path restrictions prevent traversal but do not reject terminal control bytes valid in Unix filenames.
- Error sibling: human errors print `error.message()` directly at crates/kcs-cli/src/main.rs:11184-11193, so any future lower-trust message component shares the same missing renderer.
- Closest control: when `json_mode` is true, `serde_json::to_string` emits JSON escapes before output at crates/kcs-cli/src/main.rs:11135-11143. No equivalent terminal-safe escaping or allowlist is called by the human branches.
- Sink: Rust formatting preserves the string bytes, and `println!` sends them to stdout/stderr. The concrete effect depends on the user's terminal emulator and configuration, but terminal output spoofing is inherent once ESC/C0 bytes cross the sink.

## Evidence and safe observation

- All source was read from immutable revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`.
- The bounded control used a synthetic byte sequence containing ESC and BEL. It emitted only hexadecimal for the raw bytes and escaped ASCII for the JSON form; the raw representation contained byte `1b`, while serialized JSON contained no raw `1b` byte.
- No control-bearing sequence was printed, no terminal title or clipboard was touched, and no KCS command or untrusted repository was opened.

## Counterevidence and severity calibration

- `--json` output is protected by JSON serialization, and piping human output into a non-terminal generally removes terminal interpretation.
- Terminal emulators differ: dangerous OSC operations may be disabled, gated, or ignored. Display rewriting and deceptive hyperlinks nevertheless remain broadly relevant.
- The issue requires the user to invoke a human-readable command on a hostile scope. It does not by itself cross OS-user permissions or execute shell commands.
- These constraints keep the finding at Medium while preserving the direct operator-integrity and terminal-action impact.

## Proof gap and next step

No material V10 gap remains. Regression tests should route every human branch through one renderer and compare bytes for C0, ESC, CSI, OSC, bidi, and newline cases, while asserting JSON output remains semantically unchanged. A live-terminal demonstration was intentionally not run because it would be unnecessary and could modify terminal or clipboard state.

## Closure row

| Ledger row id | Instance key | Source reference | Seed anchor | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KCS-R23-CAND-059 | KCS-R23-CAND-059:terminal-control-human-output | R23 discovery | crates/kcs-cli/src/main.rs:11135-11193 | crates/kcs-cli/src/main.rs:11135-11184 | untrusted text, commit message, or relative path | raw human `println!` to a control-sequence-aware terminal | reportable | JSON is escaped and terminal policies vary; no live control sequence was emitted | yes |
