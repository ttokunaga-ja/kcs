# Accepted embedding adapter targets are discarded before fixed Gemini execution

## Executive Summary

KCS accepts `tools.toml` embedding declarations that describe an execution
target, model, and authentication reference, but the runtime projection keeps
only the model and authentication reference. When a declared embedding
credential is present, the catalog selects real embedding execution and always
constructs the built-in Gemini adapter. The result is a destination/model
confusion bug: a user can approve or supply credentials for a private,
offline, command, non-Gemini, or otherwise custom embedding adapter, while KCS
later sends the retained secret and indexed text through the fixed Gemini
client or an ambient `GEMINI_API_BASE`.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and
used the saved validation and attack-path records for this candidate; I did
not issue any live embedding request or contact a remote provider. The saved
attack-path decision rates the finding as **medium severity** with high
confidence because exploitation requires local operator configuration, online
approval, a resolvable credential, and an embedding operation, but the data
and credential recipient can still differ from the accepted declaration.

No fixed revision was supplied with this finding. The exact affected version
range is therefore not established here; the vulnerable behavior is present in
the reviewed revision.

## Background

KCS uses adapter declarations to describe how roles such as markdownization and
embedding should execute. For embedding, the declaration is security-relevant:
the target kind, command, URL, model, and authentication reference tell the
operator which implementation should receive document chunks or search query
text and which credential should be used for that implementation.

The schema accepts the fields that make this promise meaningful:

```rust
// crates/kcs-adapter/src/tool_lock.rs
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

When we read that alongside the role list, embedding is not a side channel or
an undocumented escape hatch. The same validation machinery explicitly accepts
`[embedding]` and validates fields such as `url`, `model`, and `auth` as
documented adapter configuration. That makes the later projection important:
if KCS accepts those fields, the execution layer either needs to preserve them
or reject configurations that it cannot honor.

The preview exposed to the user is broader than the specific adapter identity.
It describes generic network and embedding behavior:

```rust
// crates/kcs-cli/src/main.rs
"network_transmission_policy": {
    "default": "disabled until --approve or --online",
    "yes_grants_network": false,
},
"adapter_execution_mode": {
    "markdownize": "deterministic_library baseline",
    "embedding": "not generated without online opt-in",
},
```

That preview is a useful online gate, but it does not bind the accepted
embedding declaration to the provider, model, and credential recipient that the
runtime will actually use. We therefore have to follow the declaration into
the runtime adapter registry.

## Vulnerability Details

The lossy transition starts in `DeclaredAdapter`. The validator accepts
`kind`, `cmd`, `args`, `url`, `model`, and `auth`, but the runtime object used
after parsing contains only `tool_id`, `model`, and `auth`:

```rust
// crates/kcs-adapter/src/tool_lock.rs
pub struct DeclaredAdapter {
    pub tool_id: Option<String>,
    pub model: Option<String>,
    pub auth: Option<String>,
}
```

The conversion function then copies only those retained fields:

```rust
// crates/kcs-adapter/src/tool_lock.rs
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
```

If we carry a declaration such as `kind = "online"`,
`url = "https://embedding.example.internal"`, `model = "custom-embedding"`,
and `auth = "env:CUSTOM_EMBEDDING_KEY"` through this function, the URL and
execution kind are already gone. The retained credential is no longer coupled
to the destination for which it was declared.

The next step turns that retained credential into the real-execution switch:

```rust
// crates/kcs-adapter/src/catalog.rs
None => real_embedding_activation(
    crate::tool_lock::registered_declared_adapter("embedding")
        .and_then(|declared| declared.auth)
        .is_some(),
    std::env::var("GEMINI_API_KEY").is_ok(),
),
```

From there, the real branch does not dispatch the declared adapter. It builds
the default Gemini adapter:

```rust
// crates/kcs-adapter/src/catalog.rs
let response = match execution {
    AdoptedEmbeddingExecution::Real => GeminiEmbeddingAdapter::default().embed(request),
    other => GeminiEmbeddingAdapter::new(
        MockAdoptedEmbeddingClient { execution: other },
        ADOPTED_MODEL_PIN,
        ADOPTED_DIMENSIONS,
    )
    .embed(request),
}?;
```

That is the decisive state transition. We start with an accepted declaration
that may name another provider or an offline command, then we reduce it to
`auth`, then we use `auth` as proof that real embedding is available, and then
we route real embedding through Gemini regardless of the declared target.

The fixed client chooses its own destination:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs
fn base_url(&self) -> String {
    self.base_url
        .clone()
        .or_else(|| std::env::var("GEMINI_API_BASE").ok())
        .unwrap_or_else(|| "https://generativelanguage.googleapis.com".to_owned())
        .trim_end_matches('/')
        .to_owned()
}
```

The retained declared secret is still used:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs
fn api_key() -> Result<String> {
    crate::tool_lock::resolve_role_api_key("embedding", "GEMINI_API_KEY")?.ok_or_else(|| {
        AdapterError::Auth(
            "no Gemini embedding API key: set GEMINI_API_KEY or a tools.toml `[embedding] auth`"
                .to_owned(),
        )
    })
}
```

Finally, the sink attaches that secret and sends the embedding text:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs
let requests = items
    .iter()
    .map(|item| {
        json!({
            "model": format!("models/{model_pin}"),
            "content": { "parts": [{ "text": item.text.clone().unwrap_or_default() }] },
            "outputDimensionality": dimensions,
        })
    })
    .collect::<Vec<_>>();
let response: Value = ureq::post(&format!(
    "{}/v1beta/models/{model_pin}:batchEmbedContents",
    self.base_url()
))
.set("x-goog-api-key", &api_key)
.set("Content-Type", "application/json")
.send_json(json!({ "requests": requests }))
```

The violated invariant is therefore concrete: the destination and model that
receive embedding text and credentials must be the destination and model that
were accepted for the embedding role. In this revision, KCS accepts one
identity and executes another.

## Exploitability Analysis

The strongest route is wrong-recipient disclosure rather than direct code
execution. We need a configured embedding workflow, a resolvable embedding
secret, online approval or equivalent network opt-in, and an operator action
that indexes chunks or embeds a query. Once those conditions hold, the
attacker does not need to compromise the local machine. The lower-trust
recipient is the unintended effective provider: Google's Gemini endpoint by
default, or an ambient `GEMINI_API_BASE` if the process environment sets one.

The primitive has two parts. First, the credential chosen for the declared
embedding role is supplied as `x-goog-api-key`. If the operator declared a
custom provider credential, that secret is now presented to the wrong HTTP
recipient. Second, each eligible embedding item contributes text through
`item.text.clone().unwrap_or_default()`, so document chunks or query text cross
the same boundary.

The route is reliable because it is not a race or parser edge case. The
declaration is parsed once, registered globally, and then the real execution
branch always calls `GeminiEmbeddingAdapter::default()`. The main constraint is
reachability: a deployment that never enables online embedding, never resolves
the credential, or only declares the official Gemini adapter will not leak by
this path. Likewise, if `GEMINI_API_BASE` is intentionally aligned with the
operator's intended provider, the observed recipient drift may be neutralized,
but that alignment is ambient and not derived from the accepted declaration.

There are also useful dead ends. Supplying a different `model` in the
declaration does not appear to select the runtime model for this path; the
default adapter is built with the adopted Gemini model pin and dimensions.
Changing the declared `url` does not steer the request either, because `url`
is removed before `DeclaredAdapter` is registered. Those dead ends matter:
they show that this is not merely a missing preview label. The accepted
configuration has already lost the state needed to enforce the user's chosen
provider.

## Proof of Concept

The included PoC is a static regression probe. It does not send traffic, read
credentials, or execute an adapter. Instead, it checks the vulnerable source
shape that the saved validation established: accepted destination fields,
lossy runtime projection, authentication-triggered real execution, fixed
Gemini dispatch, and the credentialed text sink.

Run it from the report directory against a checkout of the vulnerable revision:

```sh
cd poc
python3 check_declared_embedding_target_drift.py --source-root <repo-root>
```

Expected output on the reviewed vulnerable revision:

```text
[+] accepted embedding declaration fields include kind/cmd/args/url/model/auth
[+] DeclaredAdapter keeps model/auth but not destination execution fields
[+] declared embedding auth activates real execution
[+] real embedding execution dispatches GeminiEmbeddingAdapter::default()
[+] Gemini client chooses GEMINI_API_BASE or Google's default, not the declared URL
[+] Gemini embed sink sends x-goog-api-key and item text
[+] vulnerable pattern confirmed: accepted embedding target/model can drift to fixed Gemini execution
```

On a fixed tree, at least one of those checks should fail. For example, a
correct fix might reject unsupported `url`/`cmd` declarations before
registration, preserve the declared target in the runtime adapter, or dispatch
only an implementation whose destination and model are bound to the accepted
embedding declaration.

## Remediation

The minimal invariant is: an embedding credential and input text may be sent
only to the provider/model identity that was accepted for the embedding role.
KCS can restore that invariant in either of two defensible ways.

The safest short-term patch is to fail closed for unsupported declarations.
If the current MVP only supports the adopted Gemini adapter, reject embedding
entries that name a non-Gemini target, command, URL, or incompatible model
instead of accepting them and executing Gemini:

```rust
// sketch: enforce before registering the embedding declaration
if role == "embedding" {
    let kind = entry.get("kind").and_then(toml::Value::as_str);
    let url = entry.get("url").and_then(toml::Value::as_str);
    let cmd = entry.get("cmd").and_then(toml::Value::as_str);
    let model = entry.get("model").and_then(toml::Value::as_str);

    if cmd.is_some() || url.is_some_and(|u| !is_gemini_base_url(u)) {
        return Err(AdapterError::ConfigSchema(
            "unsupported embedding adapter target for the adopted Gemini backend".to_owned(),
        ));
    }
    if model.is_some_and(|m| m != ADOPTED_MODEL_PIN) {
        return Err(AdapterError::ConfigSchema(
            "embedding model does not match the adopted Gemini backend".to_owned(),
        ));
    }
    if kind.is_some_and(|k| k != "online") {
        return Err(AdapterError::ConfigSchema(
            "unsupported embedding adapter kind for the adopted Gemini backend".to_owned(),
        ));
    }
}
```

The more complete fix is to stop projecting away the execution identity.
`DeclaredAdapter` should carry the accepted `kind`, `cmd`, `args`, `url`,
`model`, `auth`, and profile fields into the registry. The catalog should then
construct an adapter implementation from that declared identity, and the
approval/provenance path should display and bind the same provider/model that
will receive the request.

Regression tests should cover these cases:

1. A non-Gemini `[embedding]` declaration with `url`, `model`, and `auth` is
   rejected unless a matching implementation exists.
2. If custom online embedding is supported, the request base URL and model are
   exactly the declared URL and model.
3. A custom-provider credential is never attached to the built-in Gemini
   endpoint.
4. Preview and approval output includes the declared provider/model and the
   effective provider/model, and fails when they differ.
5. `GEMINI_API_BASE` cannot silently override a declaration-bound destination.

## Summary

KCS accepts embedding adapter configuration that appears to identify a
provider, model, and credential, but the runtime projection keeps only the
credential and then uses it to activate a fixed Gemini client. We traced the
state from accepted `tools.toml` fields, through the lossy `DeclaredAdapter`,
into the real execution switch, and finally to an authenticated text POST.

The practical impact is wrong-recipient disclosure of a declared embedding
secret and document or query text. The operator-controlled configuration and
online execution gates keep the severity at medium in the saved attack-path
decision, but they do not remove the boundary violation. Future variant review
should look for other adapter roles where accepted execution identity,
approval identity, provenance identity, and final HTTP origin can drift apart.
