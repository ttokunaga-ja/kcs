# Accepted markdown adapter targets are discarded before fixed Mistral execution

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts markdown adapter declarations that name an
execution target, such as a command adapter or a custom URL, but the production
online markdown path projects that declaration down to only `tool_id`, `model`,
and `auth`. When the operator later uses online markdownization, KCS keeps the
declared authentication reference and document bytes, then sends them through
the fixed Mistral OCR client. The result is destination confusion: a credential
and document intended for one declared adapter can be delivered to Mistral or to
an unrelated ambient `MISTRAL_API_BASE` recipient.

I reviewed the pinned source revision and ran the included local source
invariant check against that revision. I did not execute a live OCR request,
contact Mistral, read any real credential, or send any document to a network
service. No fixed revision or advisory identifier was available in the supplied
materials.

The validated security impact is wrong-recipient disclosure of the declared
markdown credential and eligible document content. The saved attack-path
analysis rates the final finding as Medium severity because the trigger is
operator-mediated, requires online execution gates and a resolvable credential,
and affects one configured markdown adapter workflow, but the crossed boundary
is concrete: data leaves for a recipient different from the accepted target.

## Background

KCS treats adapter execution configuration as device-local state. The adapter
specification separates KCS core from adapter execution and places command,
argument, URL, and authentication material in local `tools.toml` rather than in
shared `.kcs` artifacts. That is a sensible boundary: the operator can choose a
provider or command locally, and the archive only needs stable provenance.

For markdownization, the documented shape includes execution form and target
fields. In the source, the tools validator recognizes those fields as valid
adapter entry keys:

```rust
const TOOLS_ENTRY_FIELDS: &[&str] = &[
    "kind",
    "cmd",
    "args",
    "url",
    "model",
    "auth",
    "profile_hash",
    "capabilities",
    "dimensions",
    "distance",
    "modality",
    "mode",
];
```

The type checker then accepts `kind`, `cmd`, `url`, `model`, and other string
fields, while `args` and `capabilities` are accepted as string arrays. A
markdown declaration can therefore express a non-Mistral target without being
rejected as malformed. The existing contract tests also preserve this behavior:
the documented command-style markdown declaration is accepted, and even a plain
`url` value is accepted because the authentication-prefix check is scoped to the
`auth` field.

That matters because approval and preview are meaningful only if the target we
validate is the target we later execute. If we let the operator describe one
adapter and then silently run another, the trust decision moves from an explicit
local declaration to an implicit runtime default.

## Vulnerability Details

We first reach the lossy transition in `crates/kcs-adapter/src/tool_lock.rs`.
The runtime declaration type keeps only three fields:

```rust
pub struct DeclaredAdapter {
    pub tool_id: Option<String>,
    pub model: Option<String>,
    pub auth: Option<String>,
}
```

`declared_adapter_for_role()` then copies only `model` and `auth` from either
the direct `[markdown]` form or the nested `[markdown.<tool_id>]` form:

```rust
if has_direct_fields {
    return Some(DeclaredAdapter {
        tool_id: None,
        model: section
            .get("model")
            .and_then(toml::Value::as_str)
            .map(str::to_owned),
        auth: section
            .get("auth")
            .and_then(toml::Value::as_str)
            .map(str::to_owned),
    });
}
// `[role.tool_id]` form: take the first declared tool_id (MVP: one per role).
let (tool_id, entry) = section.iter().next()?;
let entry = entry.as_table()?;
Some(DeclaredAdapter {
    tool_id: Some(tool_id.clone()),
    model: entry
        .get("model")
        .and_then(toml::Value::as_str)
        .map(str::to_owned),
    auth: entry
        .get("auth")
        .and_then(toml::Value::as_str)
        .map(str::to_owned),
})
```

At this point we have already lost the declared execution kind, command,
arguments, and URL. The CLI registers this reduced object at startup, so later
online clients never receive the original destination. The important detail is
not merely that custom adapters are unsupported. Unsupported targets can be
rejected safely. The vulnerability is that KCS accepts those targets, preserves
their credential reference, and then executes a different target.

The production markdown path in `crates/kcs-adapter/src/catalog.rs` makes that
substitution concrete:

```rust
let client = EnvMistralOcrClient::new();
let configured_model = declared_markdown_model();
let model_pin = client.resolve_model_pin(&configured_model)?;
let adapter = MistralOcrMarkdownizeAdapter::new(client, model_pin, request.scope_id)
    .with_image_store(request.kcs_dir);
let profile = adapter.profile();
let mut adapter_request = adapter_request;
adapter_request.tool_profile_hash = profile.tool_profile_hash.clone();
let response = adapter.markdownize(adapter_request)?;
```

We carry forward the declared model, but no declared command or URL can affect
this dispatch. The client is `EnvMistralOcrClient`, and the Mistral client picks
its destination independently:

```rust
fn base_url(&self) -> String {
    self.base_url
        .clone()
        .or_else(|| std::env::var("MISTRAL_API_BASE").ok())
        .unwrap_or_else(|| "https://api.mistral.ai".to_owned())
        .trim_end_matches('/')
        .to_owned()
}

fn api_key() -> Result<String> {
    crate::tool_lock::resolve_role_api_key("markdown", "MISTRAL_API_KEY")?.ok_or_else(|| {
        AdapterError::Auth(
            "no Mistral OCR API key: set MISTRAL_API_KEY or a tools.toml `[markdown] auth`"
                .to_owned(),
        )
    })
}
```

The credential source is still the markdown declaration. The destination is not.
When `ocr_markdown()` runs, it reads the local input document, attaches the
resolved bearer credential, and posts to the Mistral/effective-base OCR
endpoint:

```rust
let api_key = Self::api_key()?;
let path = request.raw.path.as_deref().ok_or_else(|| {
    AdapterError::ContractViolation("Mistral OCR requires a local raw path".to_owned())
})?;
let bytes = std::fs::read(path).map_err(|err| AdapterError::Io {
    path: path.to_owned(),
    message: err.to_string(),
})?;
let value: Value = ureq::post(&format!("{}/v1/ocr", self.base_url()))
    .set("Authorization", &format!("Bearer {api_key}"))
    .set("Content-Type", "application/json")
    .send_json(ocr_request_body(
        &request.media_type,
        &bytes,
        model_pin,
        pages.as_deref(),
    ))
```

The preview path does not repair this by showing the mismatch before the send.
`index_preview_json()` emits generic network policy and adapter execution mode
fields, but it does not show the declared command, declared URL, effective
Mistral base URL, or the fact that those values differ.

So the violated invariant is straightforward: if configuration accepts an
adapter target and an authentication reference together, execution must either
reject unsupported target fields before approval or bind the final request
recipient to the accepted target. This revision does neither.

## Exploitability Analysis

The strongest realistic route is not a public remote exploit. We should think
of it as a wrong-recipient disclosure across the operator's trust boundary. The
operator creates or receives a device-local markdown declaration that names a
private OCR service, an offline command, or another intended provider, and gives
that declaration a credential reference. KCS accepts the declaration. Later, an
ordinary online markdown run keeps the credential and document but executes the
fixed Mistral path.

From there, the recipient controls depend on the environment. If
`MISTRAL_API_BASE` is unset, we send to the hard-coded Mistral origin. If it is
set, we send to that ambient base instead. In neither case did the accepted
`url` or `cmd` field select the recipient. That makes the bug more subtle than
an arbitrary URL injection: the attacker may be passive, such as the unintended
provider that receives a credential and document the operator believed belonged
to a different adapter. A lower-trust launcher that can influence
`MISTRAL_API_BASE` would make the route stronger, but the final attack-path
record does not require direct attacker control of device-local configuration.

Several controls constrain reliability and severity. `tools.toml` is local and
normally trusted. The operator must have a resolvable markdown credential, must
approve online operation, must process an eligible document, and must have
budget available. The declared model is retained, so the issue is not complete
adapter profile erasure. Those facts lower likelihood, but they do not remove
the privilege delta: the final recipient is not the recipient represented by the
accepted target fields.

A useful dead end is to treat the official-adapter MVP as a full defense. The
documentation does say the MVP documents official adapters, and that is a fair
product constraint. But source enforcement needs to match that constraint. If
custom command or URL markdown adapters are out of scope, accepting their target
fields and silently executing Mistral is worse than rejecting them. It creates a
configuration shape that looks intentional to the operator while carrying only
part of the intent into the runtime.

## Proof of Concept

The included PoC is a local source-invariant check, not a network reproduction.
It reads the pinned revision through `git show`, checks the accepted field set,
checks the lossy `DeclaredAdapter` projection, checks the fixed Mistral
dispatch, and checks that the preview omits the declared-versus-effective
recipient. It uses a synthetic URL only as a marker for the value that should
have survived projection.

Run it from the PoC directory with a checkout that contains the target revision:

```sh
cd poc
KCS_REPO=<path-to-kcs-checkout> python3 check_destination_confusion.py
```

Representative output from the local check:

```text
[+] checked target revision 0e19f3c6489da458e93a982a333c308d92d0a0ae
[+] found TOOLS_ENTRY_FIELDS
[+] tools.toml accepts kind/cmd/args/url/model/auth fields
[+] DeclaredAdapter retains only tool_id/model/auth
[+] DeclaredAdapter has no kind/cmd/args/url fields
[+] declared_adapter_for_role copies model/auth
[+] declared_adapter_for_role never copies kind/cmd/args/url
[+] CLI registers the lossy DeclaredAdapter projection
[+] production markdown path constructs EnvMistralOcrClient
[+] production markdown path consults only the declared model
[+] catalog has no declared target dispatcher
[+] Mistral client chooses ambient/default base URL
[+] Mistral client resolves the retained markdown auth secret
[+] document bytes are sent in a bearer-authenticated OCR request
[+] preview exposes generic network/mode fields
[+] preview does not disclose declared versus effective recipient
[+] synthetic declared url http://127.0.0.1:18080/private-ocr is not projected into runtime
[+] effective default recipient remains https://api.mistral.ai unless ambient base is set
result: vulnerable destination-confusion invariant is present
```

This PoC does not read an API key, does not create a document upload, and does
not contact Mistral or any loopback server. It is designed as a regression check
for the broken invariant: accepted target fields must not disappear before the
code chooses the authenticated document recipient.

## Remediation

The minimal safe invariant is: KCS must not accept an adapter target unless the
runtime will execute that exact target, show that exact recipient in preview and
approval, and bind the same recipient into provenance and credential selection.
For the current official-adapter MVP, the simplest fix is to reject unsupported
markdown target fields at configuration load:

```rust
fn validate_markdown_entry_target(context: &str, table: &toml::value::Table) -> Result<()> {
    let has_custom_target = table.contains_key("kind")
        || table.contains_key("cmd")
        || table.contains_key("args")
        || table.contains_key("url");
    if has_custom_target {
        return Err(AdapterError::ConfigSchema(format!(
            "tools.toml `{context}` declares an unsupported markdown execution target;              remove kind/cmd/args/url or implement recipient-bound dispatch"
        )));
    }
    Ok(())
}
```

If custom adapters are intended to work now, the opposite fix is required:
carry `kind`, `cmd`, `args`, and `url` into `DeclaredAdapter`, dispatch through
that target, and bind the final recipient to preview, approval records,
credential resolution, profile identity, and request execution. The important
part is that model and auth cannot be the only surviving fields.

Regression tests should cover both policy choices. A rejection-based fix should
assert that `[markdown.private] url = "http://127.0.0.1:18080/ocr"` or
`cmd = "local-ocr"` fails before any approval or send path. A dispatch-based fix
should assert that the exact declared URL or command reaches the markdown
executor, that the preview names it, and that changing the effective recipient
changes the approval/provenance identity. Existing tests that merely prove the
documented config parses are insufficient because they miss the projection and
sink.

## Summary

This finding is a destination-confusion bug in the markdown adapter pipeline.
We accept a target-rich adapter declaration, collapse it to model and auth, and
then send the credential and document through a fixed Mistral client. The local
PoC demonstrates the invariant in source without making any network request.

The practical risk is bounded by local configuration, online opt-in, credential
presence, and operator invocation, which is why the final severity is Medium
rather than High. The engineering fix is still important: either unsupported
adapter targets must be rejected loudly, or the exact declared target must be
preserved through preview, approval, credential use, dispatch, and provenance.
Variant review should look for other adapter roles where endpoint, auth, and
profile identity are accepted together but only a subset survives into the
runtime sink.
