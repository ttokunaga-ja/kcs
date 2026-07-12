# Human-Readable CLI Output Emits Untrusted Terminal Control Sequences

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` safely
serializes structured `--json` output, but the default human-readable output
path writes several lower-trust strings directly to `stdout` or `stderr`.
Those strings include stored chunk text returned by `kcs view`, persisted
snapshot messages shown by log output, and repository relative paths shown by
diff and status output. If any of those strings contain terminal control bytes,
we carry data from a hostile scope into a control-sequence-aware terminal.

The realistic impact is operator-interface compromise rather than code
execution: a malicious scope can spoof trusted output, rewrite the terminal
title or display, create deceptive hyperlinks, and potentially trigger
emulator-dependent clipboard or terminal actions. I reviewed the vulnerable
revision and the saved validation and attack-path reports directly, and I ran
only a non-emitting local byte/JSON comparison probe; I did not print a live
terminal control sequence or exercise title, hyperlink, or clipboard behavior.

The finding is Medium severity. The trigger is routine and deterministic when
the operator uses human output in an interactive terminal, but the strongest
effects depend on terminal policy and the issue does not cross OS-user
permissions or establish shell command execution.

## Background

KCS exposes both machine-readable and human-readable command output. The
machine path is intended for automation and passes the whole response through
JSON serialization. The human path is intended for terminal users and selects a
few friendly fields from the same response object.

That distinction matters because KCS stores and later displays strings that can
come from a lower-trust boundary. A copied scope or repository can carry
document text, OCR-derived text, commit messages, and filenames. They are just
data while they live in KCS storage, but when we write them to a terminal, bytes
such as ESC, C0 controls, OSC introducers, bidi controls, and embedded newlines
can change how the operator sees the output.

For the `view` command, `run_view()` resolves a caller-supplied pointer and
places the selected chunk text into the `text` field of the command response:

```rust
// crates/kcs-cli/src/main.rs:2816-2836
fn run_view(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, true);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, true);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    Ok(json!({
        "status": "viewed",
        "raw_hash": pointer.raw_hash,
        "chunk_hash": pointer.chunk_hash,
        "text": resolved.text.unwrap_or_default(),
        "path": resolved.path,
        "temporary": resolved.temporary,
        "commit_shallow": resolved.commit_shallow,
    }))
}
```

The resolved text is read from stored chunk rows. The code binds the pointer to
the expected raw object and tool profile, which is good evidence integrity, but
it does not make the text terminal-safe:

```rust
// crates/kcs-cli/src/main.rs:4824-4859
let chunk = read_stored_chunks(&target.kcs_dir)?
    .into_iter()
    .find(|chunk| chunk.row.chunk_id == pointer.chunk_hash);
let Some(chunk) = chunk else {
    return Err(KcsError::new(
        "KCS-E-EVIDENCE-RETARGET-REQUIRED-001",
        "chunk not materialized for this tool_profile_hash; retarget required (08 §5)",
        json!({
            "chunk_hash": pointer.chunk_hash,
            "tool_profile_hash": pointer.tool_profile_hash,
            "raw_hash": pointer.raw_hash,
        }),
        ExitCode::IncompatibleProfile,
    ));
};
if chunk.row.raw_hash != pointer.raw_hash
    || chunk.row.tool_profile_hash != pointer.tool_profile_hash
{
    return Err(invalid_pointer_identity_error(pointer));
}
if let Some(entry_gen) = entry_gen {
    if chunk.row.gen != entry_gen {
        return Err(invalid_pointer_identity_error(pointer));
    }
}
let text = chunk.row.text;
```

The same output helper also handles commits, diff changes, status files, and
errors. That makes the bug a shared rendering invariant rather than a single
`view` bug.

## Vulnerability Details

The safe branch is visible first. If `json_mode` is true, KCS serializes the
entire response with `serde_json::to_string()`. JSON escaping converts raw
control bytes such as ESC and BEL into escaped text before the terminal sees
the output:

```rust
// crates/kcs-cli/src/main.rs:11135-11142
fn print_output(value: Value, json_mode: bool) {
    if json_mode {
        println!(
            "{}",
            serde_json::to_string(&value).expect("serializing command output cannot fail")
        );
        return;
    }
```

Once execution falls through to human mode, the invariant changes. The `text`
field is printed directly:

```rust
// crates/kcs-cli/src/main.rs:11144-11149
// M2: `kcs view` (non --json) must print the chunk body, not just the
// "viewed" status. When the payload carries a `text` field (view / chunk
// object resolution), print the body — that is the point of `view`.
if let Some(text) = value.get("text").and_then(Value::as_str) {
    println!("{text}");
}
```

If we carry a stored chunk containing the byte sequence spelled as
`\x1b]0;synthetic-title\x07` into this branch, Rust formatting preserves the
string bytes and `println!` appends a newline. The terminal receives an OSC
title-setting sequence, not a harmless printable description of that sequence.
The validation artifacts intentionally avoided emitting that byte stream, but
the source path is complete: stored text reaches `Value::String`, and the
human renderer forwards it without a terminal-safe escaping step.

The same helper repeats the pattern for commit messages and repository paths:

```rust
// crates/kcs-cli/src/main.rs:11151-11176
} else if let Some(commits) = value.get("commits").and_then(Value::as_array) {
    for commit in commits {
        println!(
            "{} {} {}",
            commit["commit_hash"].as_str().unwrap_or_default(),
            commit["created_at"].as_str().unwrap_or_default(),
            commit["message"].as_str().unwrap_or_default()
        );
    }
} else if let Some(changes) = value.get("changes").and_then(Value::as_array) {
    for change in changes {
        println!(
            "{} {}",
            change["change"].as_str().unwrap_or_default(),
            change["relative_path"].as_str().unwrap_or_default()
        );
    }
} else if let Some(files) = value.get("files").and_then(Value::as_array) {
    for file in files {
        println!(
            "{} {}",
            file["status"].as_str().unwrap_or_default(),
            file["relative_path"].as_str().unwrap_or_default()
        );
    }
}
```

The saved validation traces confirm that snapshot messages are caller supplied,
persisted, and returned by log output, while direct-child UTF-8 filenames become
tree entries and later appear as `relative_path` values in diff and status
responses. Direct-child path checks prevent traversal, but they do not reject
display controls that are legal in Unix filenames or text content. That leaves
the terminal renderer as the expected final control, and this branch does not
have one.

The error renderer has the same shape for any future lower-trust error message
component:

```rust
// crates/kcs-cli/src/main.rs:11184-11193
fn print_error(error: &KcsError, json_mode: bool) {
    if json_mode {
        eprintln!(
            "{}",
            serde_json::to_string(&error.to_error_json())
                .expect("serializing command error cannot fail")
        );
    } else {
        eprintln!("{}: {}", error.error_code(), error.message());
    }
}
```

The violated invariant is therefore precise: every human-readable string that
originates outside the operator's trust boundary must be rendered through a
terminal-safe encoder before it reaches `println!` or `eprintln!`. KCS already
has a safe machine-output control in JSON mode, but human mode bypasses it for
the fields users are most likely to inspect manually.

## Exploitability Analysis

The strongest practical route is output deception. We start with a hostile
scope that contains a terminal-active document chunk, filename, or snapshot
message. The operator then runs a routine command such as `kcs view`,
`kcs log`, `kcs diff`, or `kcs status` without `--json`. From there, we control
the bytes passed into one of the raw formatting sites above.

For a simple spoofing payload, newline and cursor-control sequences can make
the terminal display a forged success line, hide preceding warnings, or make a
malicious path appear to be a benign sibling. Bidi controls can further distort
the visual order of filenames or messages. These effects do not require a
terminal to enable high-risk OSC features; the attack only needs the terminal
to interpret ordinary display controls.

OSC-based payloads add more emulator-dependent options. OSC 0 or OSC 2 can
rewrite the terminal title in many configurations. OSC 8 can create a deceptive
hyperlink, so the visible text can look like a local file or trusted command
while the target URI points elsewhere. OSC 52 clipboard behavior is the more
sensitive branch: some terminals disable it, prompt for it, or restrict it, but
where it is enabled, raw output can request clipboard modification. We should
not overstate this as credential theft because the saved validation did not
demonstrate clipboard reads or exfiltration; the supported claim is that KCS
forwards attacker-controlled bytes into the terminal instruction channel.

There are useful constraints. `--json` output is not affected because JSON
serialization removes raw ESC bytes from the emitted stream. Piping output into
a file or non-terminal sink generally prevents terminal interpretation at the
time KCS runs, although later viewing that file with unsafe tooling can recreate
the risk. The operator still has to inspect the hostile scope, and the issue
does not give the lower-trust contributor the operator's OS privileges or
direct shell execution.

Those constraints explain the Medium rating without making the bug theoretical.
The vulnerable path has no race, no heap grooming, and no privileged setup: if
the hostile string is present and the operator uses the default human renderer,
the raw bytes are emitted.

## Proof of Concept

The included PoC is deliberately non-emitting. It models the vulnerable branch
and the JSON branch with the same synthetic byte string, then prints only a
hexadecimal representation and JSON-escaped text. We never write the raw
control-bearing string to `stdout`, so the probe is safe to run in an ordinary
terminal.

From this report directory:

```sh
cd poc
make run
```

Representative output:

```text
[+] synthetic payload bytes:
    53 41 46 45 1b 5d 30 3b 73 79 6e 74 68 65 74 69 63 2d 74 69 74 6c 65 07 45 4e 44
[+] raw branch would contain ESC: yes
[+] raw branch would contain BEL: yes
[+] JSON branch:
    "SAFE\u001b]0;synthetic-title\u0007END"
[+] JSON branch contains raw ESC byte: no
[+] safe probe completed without emitting the raw control sequence
```

The probe demonstrates the branch difference that matters for the vulnerability.
If KCS sends the synthetic value through the human `println!("{text}")` path,
the byte stream contains `0x1b` and `0x07`. If KCS sends it through the JSON
path, those bytes are represented as printable escape text. I ran this probe
locally as a byte-encoding check only; I did not attempt to change the terminal
title, create a hyperlink, or touch the clipboard.

## Remediation

The minimal fix is to centralize human-output rendering for untrusted strings
and call it at every `println!` or `eprintln!` site that displays stored text,
commit messages, relative paths, or lower-trust error content. The invariant is
simple: JSON mode preserves structured machine semantics, while human mode
must visibly encode terminal-active characters before the terminal can interpret
them.

One possible Rust shape is:

```rust
fn terminal_safe_text(input: &str) -> String {
    input
        .chars()
        .flat_map(|ch| match ch {
            '\x00'..='\x1f' | '\x7f' => format!("\\x{:02x}", ch as u32).chars().collect(),
            '\u{202a}'..='\u{202e}' | '\u{2066}'..='\u{2069}' => {
                format!("\\u{{{:04x}}}", ch as u32).chars().collect()
            }
            _ => vec![ch],
        })
        .collect()
}

if let Some(text) = value.get("text").and_then(Value::as_str) {
    println!("{}", terminal_safe_text(text));
}
```

The exact display policy can be tuned, but the renderer should cover C0
controls, ESC, CSI/OSC introducers, DEL, bidi controls, embedded newlines when
they appear in metadata fields, and hyperlink delimiters. For full document
body output, KCS may decide to preserve ordinary newlines for usability, but it
should still escape ESC, C0 controls other than permitted line breaks, and bidi
characters that can mislead the operator.

Regression tests should exercise the shared renderer rather than only one
command. A useful suite would build synthetic `Value` objects for `text`,
`commits[*].message`, `changes[*].relative_path`, `files[*].relative_path`, and
an error message, then assert that human output contains no raw ESC, BEL, CSI,
OSC, or bidi controls. A paired `--json` test should assert that structured
output remains valid JSON and preserves the original logical string after
parsing.

## Summary

KCS already distinguishes structured automation output from friendly terminal
output, but the human renderer trusts strings that can originate in a hostile
scope. We followed stored chunk text into `kcs view`, observed the safe JSON
control, and then watched human-mode branches write text, commit messages, and
relative paths directly to terminal output. The resulting primitive is terminal
control-sequence injection: useful for output spoofing and emulator-dependent
terminal actions, but bounded away from direct OS privilege escalation.

The durable fix is one shared terminal-safe rendering invariant for every
human-readable untrusted field. Variant review should focus on new CLI output
branches, error messages that include lower-trust data, and any future command
that prints repository or OCR-derived strings outside JSON mode.
