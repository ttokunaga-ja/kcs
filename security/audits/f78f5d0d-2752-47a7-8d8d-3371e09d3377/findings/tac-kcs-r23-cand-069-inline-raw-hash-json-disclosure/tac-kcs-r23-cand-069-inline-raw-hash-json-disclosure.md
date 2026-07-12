# Inline EvidencePointer raw_hash escapes tombstone storage and discloses JSON files

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
accepts inline JSON `EvidencePointer` operands whose `raw_hash` field is an
unconstrained string. When the pointer names a real scope and an existing commit
but the commit tree does not contain that `raw_hash`, pointer resolution checks
for a purge tombstone before returning not-found. The tombstone helper builds a
path by joining `.kcs/tombstones/<fanout>/<raw_hash>` and then reads it. Because
the final component is attacker controlled, an absolute value replaces the
intended tombstone prefix, and parent-bearing values can escape it when the OS
resolves the path.

The security consequence is a local arbitrary JSON file read across the selected
scope boundary: a lower-trust caller who can supply inline pointer text to a KCS
command and receive JSON-mode errors can cause KCS, running as the invoking user,
to parse a process-readable JSON file and serialize its fields in
`KcsError.context`. I reviewed the vulnerable revision directly and ran only the
included synthetic local path probe; I did not read real secrets, use live
targets, or invoke KCS against an external system.

The saved validation and attack-path analysis rate this finding High/P1 with
high confidence. That rating is appropriate because the primitive can expose
user-readable JSON configuration, state, or credential material to a caller who
does not otherwise have direct file-read authority, while still requiring a real
scope, an existing commit, a JSON target, and JSON-mode error exposure.

## Background

KCS evidence pointers identify a normalized chunk by scope, commit, raw content
hash, tool profile hash, and chunk hash. A pointer can arrive as a `kcs://` URI,
a short `sha256:` operand, or inline JSON. The inline JSON form is useful for
carrying the full pointer structure, but it also means the parser must validate
the same hash grammar that the more compact forms rely on.

The shared pointer type in `crates/kcs-search/src/evidence.rs` stores hash
fields as plain strings:

```rust
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct EvidencePointer {
    pub schema_version: u64,
    pub commit: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tree: Option<String>,
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub chunk_hash: String,
    // ...
    pub scope_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub scope_path: Option<String>,
}
```

That is not automatically unsafe. A string field can be fine when every entry
point applies the same grammar before the value reaches file-system code. The
important split here is that short-hash operands do receive a lowercase-hex
check, while inline JSON pointers do not.

For `open` and `view`, KCS reads the pointer operand and sends the non-short
forms through `parse_pointer_text()` before resolving the pointer:

```rust
fn run_open(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, false);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, false);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    // ...
}
```

We therefore have an explicit lower-trust input boundary: a caller can provide
pointer text without being authorized to read arbitrary files as the KCS process.
Normal scope and commit checks still matter, but they should not turn the
pointer's hash fields into path names.

## Vulnerability Details

The inline JSON parser only checks the schema version. After `serde_json`
constructs the `EvidencePointer`, the arbitrary `raw_hash` string is returned to
the resolver:

```rust
fn parse_pointer_text(pointer: &str) -> Result<EvidencePointer> {
    if pointer.starts_with("kcs://") {
        return parse_evidence_pointer_uri(pointer).map_err(search_to_kcs);
    }
    if pointer.trim_start().starts_with('{') {
        let pointer: EvidencePointer =
            serde_json::from_str(pointer).map_err(|err| KcsError::schema(err.to_string()))?;
        if pointer.schema_version != EVIDENCE_POINTER_SCHEMA_VERSION {
            return Err(KcsError::schema("unsupported evidence schema version"));
        }
        return Ok(pointer);
    }
    Err(KcsError::invalid_usage("invalid pointer argument"))
}
```

The nearby short-hash path shows the expected invariant. Before a short
`sha256:` operand can reach any lookup, it must contain at least four lowercase
hex characters:

```rust
fn validate_short_hash_operand(hash: &str) -> Result<()> {
    let digest = hash.strip_prefix("sha256:").unwrap_or(hash);
    if digest.len() < 4
        || !digest
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return Err(KcsError::invalid_usage(
            "short hash must be `sha256:` followed by at least 4 lowercase hex characters",
        ));
    }
    Ok(())
}
```

If we carry the inline pointer forward, the resolver does enforce real
repository context. It resolves the scope, opens the repository, and requires an
existing commit. On a non-shallow commit, it then looks for a tree entry whose
`entry.raw_hash` equals the attacker-controlled `pointer.raw_hash`. When the
tree does not contain that value, KCS probes the tombstone store before
returning not-found:

```rust
let (commit_shallow, entry_gen) = match repo.read_tree(&commit.tree) {
    Ok(tree) => {
        let entry = tree
            .entries
            .iter()
            .find(|entry| entry.raw_hash == pointer.raw_hash);
        let Some(entry) = entry else {
            // step 5 (tombstone) is checked before declaring not_found.
            if let Some(tombstone) = read_tombstone(&target, &pointer.raw_hash)? {
                return Err(tombstone_error(tombstone));
            }
            return Err(purge_not_found_error(&target, &pointer.raw_hash));
        };
        // ...
    }
    // ...
};
```

That branch is reachable with a legitimate pointer template: the attacker reuses
a real `scope_id`, optional `scope_path`, and existing `commit`, but supplies a
`raw_hash` that is not present in the tree. The bug is then in
`read_tombstone()`. We reach a helper that strips a `sha256:` prefix if present,
checks only that the resulting digest is at least four bytes long, and joins the
original `raw_hash` as the final path component:

```rust
fn read_tombstone(target: &ScopeTarget, raw_hash: &str) -> Result<Option<Value>> {
    let digest = raw_hash.trim_start_matches("sha256:");
    if digest.len() < 4 {
        return Ok(None);
    }
    let path = target
        .kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash);
    let bytes = match fs::read(&path) {
        Ok(bytes) => bytes,
        Err(err) if err.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(err) => return Err(KcsError::io(err.to_string(), path.display().to_string())),
    };
    let mut value: Value =
        serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    // ...
}
```

In Rust, `PathBuf::join()` does not sanitize a later component. If the later
component is absolute, it replaces the accumulated prefix; if it contains parent
components, the resulting relative path is still resolved by the OS at read
time. So the value we carried from inline JSON is no longer a content hash. It
has become the file name that `fs::read()` opens.

The helper then preserves the parsed JSON object and installs it as the error
context:

```rust
if let Some(object) = value.as_object_mut() {
    object
        .entry("raw_hash".to_owned())
        .or_insert_with(|| json!(raw_hash));
    object.insert(
        "scope_path".to_owned(),
        json!(target.kcs_dir.display().to_string()),
    );
}
Ok(Some(value))
```

```rust
fn tombstone_error(mut tombstone: Value) -> KcsError {
    if let Some(object) = tombstone.as_object_mut() {
        object.insert("status".to_owned(), json!("purged"));
    }
    KcsError::new(
        "KCS-E-PURGE-TOMBSTONED-001",
        "evidence target was purged (tombstone recorded)",
        tombstone,
        ExitCode::PermanentFailure,
    )
}
```

Finally, JSON-mode error output serializes that context:

```rust
pub fn to_error_json(&self) -> Value {
    json!({
        "error_code": self.error_code,
        "message": self.message,
        "context": self.context,
    })
}
```

```rust
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

The full chain is therefore:

1. inline JSON pointer controls `raw_hash`;
2. schema validation accepts the object without hash validation;
3. a real scope and existing commit pass the authenticity gate;
4. a tree miss reaches tombstone lookup;
5. `PathBuf::join(raw_hash)` escapes `.kcs/tombstones`;
6. `fs::read()` opens a process-readable JSON file;
7. parsed JSON is returned through structured error output.

## Exploitability Analysis

The strongest route is a local or agent-tool workflow where a lower-trust actor
can provide pointer text and receives JSON-mode errors. We do not need to bypass
OS file permissions; instead, we cross the application boundary between the
lower-trust caller and the KCS process identity. If KCS is invoked by an
operator or automation with access to user-readable JSON configuration, KCS may
read and reflect data that the pointer author could not read directly.

The exploit has real prerequisites. We must supply a valid `scope_id` and an
existing `commit`; a random pointer will be rejected before the file read. We
also need the chosen `raw_hash` to miss the commit tree, because otherwise the
resolver follows the normal chunk path. The target file must be readable by the
KCS process and parse as JSON. Human-readable error output prints only the code
and message, so direct disclosure depends on `--json` or on an integration that
returns the structured error object.

Those constraints shape, but do not neutralize, the primitive. Scope IDs,
commits, and legitimate pointer templates are routinely visible in normal KCS
output. Once a caller has one template, the `raw_hash` value can be varied
across attempts. Absolute paths are the cleanest form because they replace the
accumulated tombstone prefix immediately. Parent traversal is noisier because
the fanout components remain in the path until the OS resolves them, but it is
still a useful variant to test in regression coverage.

The URI form is less useful for this particular escape because
`parse_evidence_pointer_uri()` requires exactly five slash-separated path
segments. That makes slash-bearing absolute paths and `../` segments awkward in
the URI surface. The inline JSON form is independently supported, however, and
does not inherit that segment constraint.

The primitive is limited to parseable JSON at this sink. Non-JSON files produce
a schema error rather than a reflected object, and the validation record does
not establish a write, code execution, or general binary file disclosure. For
severity, the important point is that many local automation and application
state files are JSON, and the reflected object is complete enough to carry
configuration fields, tokens, or other sensitive state when the invoking user's
permissions allow the read.

## Proof of Concept

The included PoC is a safe local probe. It does not run KCS, does not read any
existing user file, and does not use credentials. Instead, it creates a
temporary synthetic `.kcs` directory and a synthetic JSON marker file, then
applies the same path construction used by `read_tombstone()`. We use it to
demonstrate the decisive `PathBuf::join` behavior and the JSON context shape
without touching real targets.

From the report directory:

```sh
cd poc
make
make run
```

Representative output:

```text
[+] synthetic kcs_dir: <tmp>/repo/.kcs
[+] attacker raw_hash: <tmp>/marker.json
[+] vulnerable join result: <tmp>/marker.json
[+] containment under tombstones: false
[+] reflected JSON context keys: kind, note, raw_hash, scope_path, status
[+] strict sha256 validator rejects attacker raw_hash: true
```

The probe also includes a strict validator check for the remediation invariant:
`raw_hash` should be exactly `sha256:` plus 64 lowercase hexadecimal characters
before any lookup. Under that invariant, the synthetic absolute path is rejected
before path construction.

## Remediation

The invariant to restore is simple: pointer hash fields must remain content
hashes, not path components. KCS should validate every `EvidencePointer` hash
field on every operand surface before any lookup, and tombstone path
construction should use only validated digest slices.

A minimal defensive pattern is:

```rust
fn validate_full_hash(hash: &str) -> Result<&str> {
    let Some(digest) = hash.strip_prefix("sha256:") else {
        return Err(KcsError::invalid_usage("hash must start with `sha256:`"));
    };
    if digest.len() != 64
        || !digest
            .bytes()
            .all(|byte| matches!(byte, b'0'..=b'9' | b'a'..=b'f'))
    {
        return Err(KcsError::invalid_usage(
            "hash must be `sha256:` followed by 64 lowercase hex characters",
        ));
    }
    Ok(digest)
}

fn read_tombstone(target: &ScopeTarget, raw_hash: &str) -> Result<Option<Value>> {
    let digest = validate_full_hash(raw_hash)?;
    let path = target
        .kcs_dir
        .join("tombstones")
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(raw_hash);
    // read only after validation
    // ...
}
```

For additional defense in depth, KCS can reject any path component that is not a
normal component before file reads and canonicalize the final tombstone path
against the expected tombstone root. That containment check should be a backstop,
not the only guard; the primary fix is to make invalid hashes impossible to use
as lookup keys.

Regression tests should cover the inline JSON route, not only URI and
short-hash operands:

- absolute `raw_hash` such as a synthetic temporary JSON path is rejected before
  `fs::read()`;
- `../` and mixed-separator values are rejected;
- short, uppercase, missing-prefix, and malformed values are rejected;
- a valid `sha256:` plus 64 lowercase hex digest still checks the expected
  tombstone path;
- JSON-mode errors for rejected operands do not include file-derived context.

## Summary

KCS treats inline JSON evidence pointers as trusted enough to deserialize but
not validated enough to safely use as file-system lookup keys. We followed a
single attacker-controlled `raw_hash` from inline JSON through scope and commit
checks, into tombstone lookup, through `PathBuf::join()`, and back out through
structured error serialization. The vulnerability is not a general filesystem
compromise, but it is a direct arbitrary JSON read under the KCS process
identity when a lower-trust caller can induce pointer resolution and receive
JSON-mode errors.

The fix should centralize full hash validation and ensure tombstone paths are
constructed only from validated digest material. Variant review should look for
other places where serialized pointer fields, CAS hashes, or tombstone metadata
cross from logical identifiers into `PathBuf` construction without first being
reduced to validated digest components.
