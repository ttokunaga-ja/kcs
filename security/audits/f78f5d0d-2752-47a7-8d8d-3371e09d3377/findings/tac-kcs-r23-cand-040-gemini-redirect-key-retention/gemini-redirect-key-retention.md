# Gemini API keys are retained across cross-origin redirects

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` sends
Gemini embedding requests through the top-level `ureq::post()` helper while
placing the reusable provider credential in the custom `x-goog-api-key`
header. The workspace lockfile selects `ureq` 2.12.1. In that release, the
default agent follows up to five redirects, rewrites 301/302/303 POST requests
to bodyless GET requests, and strips `content-length`, `cookie`, and
`authorization` during redirect reconstruction. It does not strip
`x-goog-api-key`, and KCS does not install its own redirect policy around the
request. A trusted, compromised, or misconfigured accepted origin that returns a
cross-origin 301/302/303 can therefore cause the Gemini credential to be sent to
the redirect target.

I reviewed the vulnerable KCS revision and the pinned `ureq` 2.12.1 source
directly. I did not contact Gemini, start a loopback capture, or use any real
credential; the included proof of concept is a local static regression probe
over the checkout and the resolved dependency source.

The final attack-path decision rates this as Medium/P2: the credential impact
is high, but exploitation depends on a qualifying redirect from an accepted
origin, and no open redirect at the default Google endpoint was proven.

## Background

KCS's adopted Gemini embedding adapter is an online adapter. When an operator
has approved the adapter and supplied a credential, the adapter can embed query
or chunk text by sending JSON to the configured Gemini base URL. The important
security invariant is that a reusable provider credential should stay bound to
the origin the operator approved. Redirects are a separate trust boundary:
although the first origin is allowed to receive the credential, a `Location`
target is chosen by the remote response and can name a different host or scheme.

The KCS client chooses the effective origin and resolves the secret here:

```rust
fn base_url(&self) -> String {
    self.base_url
        .clone()
        .or_else(|| std::env::var("GEMINI_API_BASE").ok())
        .unwrap_or_else(|| "https://generativelanguage.googleapis.com".to_owned())
        .trim_end_matches('/')
        .to_owned()
}

fn api_key() -> Result<String> {
    crate::tool_lock::resolve_role_api_key("embedding", "GEMINI_API_KEY")?.ok_or_else(|| {
        AdapterError::Auth(
            "no Gemini embedding API key: set GEMINI_API_KEY or a tools.toml `[embedding] auth`"
                .to_owned(),
        )
    })
}
```

We reach that client through the normal production adapter. The default adapter
uses the environment-backed client, and `EmbeddingAdapter::embed()` calls into
the client before returning the vectors:

```rust
impl Default for GeminiEmbeddingAdapter<EnvGeminiEmbeddingClient> {
    fn default() -> Self {
        Self::new(
            EnvGeminiEmbeddingClient::new(),
            ADOPTED_MODEL_PIN,
            ADOPTED_DIMENSIONS,
        )
    }
}

impl<C: GeminiEmbeddingClient> EmbeddingAdapter for GeminiEmbeddingAdapter<C> {
    fn embed(&self, request: EmbeddingRequest) -> Result<EmbeddingResponse> {
        let model_pin = self.client.resolve_model_pin(&self.configured_model)?;
        let vectors = self
            .client
            .embed(&request.items, &model_pin, self.dimensions)?;
        Ok(EmbeddingResponse {
            vectors,
            dimensions: self.dimensions,
            distance: "cosine".to_owned(),
            modality: "multimodal".to_owned(),
        })
    }
}
```

So the boundary we need to inspect is not an inbound KCS listener. It is an
outbound authenticated request plus the library's treatment of a remote redirect
response.

## Vulnerability Details

The embedding client constructs the batch URL, attaches the secret as
`x-goog-api-key`, and immediately delegates the whole send to `ureq`:

```rust
let response: Value = ureq::post(&format!(
    "{}/v1beta/models/{model_pin}:batchEmbedContents",
    self.base_url()
))
.set("x-goog-api-key", &api_key)
.set("Content-Type", "application/json")
.send_json(json!({ "requests": requests }))
.map_err(http_error)?
.into_json()
.map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
```

There is no KCS `AgentBuilder`, redirect callback, origin comparison, or
credential-reconstruction step around this call. From here, we have to carry the
custom header into the exact dependency selected by the vulnerable revision.
`Cargo.toml` declares `ureq = { version = "2", features = ["json"] }`, and
`Cargo.lock` pins that to version `2.12.1`.

In `ureq` 2.12.1, the top-level `post()` helper constructs a fresh default
agent:

```rust
pub fn agent() -> Agent {
    #[cfg(not(test))]
    if is_test(false) {
        testserver::test_agent()
    } else {
        AgentBuilder::new().build()
    }
    #[cfg(test)]
    testserver::test_agent()
}

pub fn post(path: &str) -> Request {
    request("POST", path)
}
```

The default builder enables redirects:

```rust
AgentBuilder {
    config: AgentConfig {
        proxy: None,
        timeout_connect: Some(Duration::from_secs(30)),
        timeout_read: None,
        timeout_write: None,
        timeout: None,
        https_only: false,
        no_delay: true,
        redirects: 5,
        redirect_auth_headers: RedirectAuthHeaders::Never,
        user_agent: format!("ureq/{}", env!("CARGO_PKG_VERSION")),
        tls_config: TlsConfig(crate::default_tls_config()),
    },
```

Now we can follow the redirect reconstruction. `ureq` joins the `Location`
header against the current URL without enforcing same-origin or a no-downgrade
policy. For 301, 302, and 303, it changes non-GET methods to `GET`, empties the
body, and then reuses the old header vector:

```rust
let new_url = url.join(location).map_err(|e| {
    ErrorKind::InvalidUrl
        .msg(format!("Bad redirection: {}", location))
        .src(e)
})?;

let new_method = match resp.status() {
    301 | 302 | 303 => match &method[..] {
        "GET" | "HEAD" => unit.method,
        _ => "GET".into(),
    },
    307 | 308 if ["GET", "HEAD", "OPTIONS", "TRACE"].contains(&method.as_str()) => {
        unit.method
    }
    _ => break resp,
};

body = Payload::Empty.into_read();
let mut headers = unit.headers;
```

The stripping control is intentionally narrow:

```rust
headers.retain(|h| {
    !h.is_name("content-length")
        && !h.is_name("cookie")
        && (!h.is_name("authorization") || keep_auth_header)
});
```

That control removes the standard `Authorization` header by default, and it
also removes cookies and content length. It does not match provider-specific
credential names. When we carry KCS's `x-goog-api-key` header into this retain
call, the predicate keeps it and builds the redirected request with that header
still present. The violated invariant is that credentials must be rebound to the
final origin after redirect processing, not only to the first URL KCS formatted.

## Exploitability Analysis

The strongest route is a credential-forwarding attack through a qualifying
redirect response. We start with an operator-approved embedding operation and a
valid Gemini credential. KCS sends the first request to the accepted origin,
which is allowed to see the key. If that origin returns a 301, 302, or 303 with
a `Location` pointing at a lower-trust host, `ureq` turns the embedding POST into
a bodyless GET and sends the retained `x-goog-api-key` to the new host.

This route is narrower than arbitrary request replay, and that matters for
severity. For the proven 301/302/303 path, the embedding request body is not
forwarded because `ureq` replaces it with `Payload::Empty`. For 307 and 308, the
same implementation does not automatically resend a body-bearing POST, so this
specific path is credential disclosure rather than embedding-text disclosure.
That is still security-relevant: the leaked value is a reusable provider API key
or a declared embedding secret, and the redirect recipient does not have to be
the origin the operator approved.

There are a few realistic redirect sources. A compromised or misconfigured
accepted service can emit the cross-origin `Location` directly. A custom base URL
selected through deployment configuration can produce the same response, but if
that base is fully malicious it already receives the key on the first request;
the incremental risk is clearer when the first origin is trusted enough for the
key but redirects through a second, lower-trust recipient. An ordinary network
attacker cannot inject the first redirect into the default HTTPS request without
breaking TLS, so the useful attacker position is control over the accepted
origin's response path, not passive on-path observation.

The negative control is useful too. If KCS had used a standard `Authorization`
header, `ureq`'s default redirect policy would strip it on origin changes. This
bug exists because the Gemini credential is carried in a custom header that the
library does not know is sensitive. The fix should therefore not rely on a
library-maintained list of sensitive names; KCS should treat every provider
credential header as origin-bound application state.

## Proof of Concept

The `poc/` directory contains a static regression probe. It does not start
servers, send network traffic, or use real credentials. Instead, it checks the
vulnerable source and the selected `ureq` source for the exact conditions that
make the redirect credential leak possible.

From this report directory, run:

```sh
cd poc
make SOURCE_ROOT=/path/to/kcs UREQ_SRC=/path/to/ureq-2.12.1/src check
```

If `UREQ_SRC` is omitted, the script searches `$CARGO_HOME/registry/src` and
`~/.cargo/registry/src` for `ureq-2.12.1/src`. Representative output on the
vulnerable revision is:

```text
[ok] KCS attaches the Gemini secret as x-goog-api-key on ureq::post
[ok] repository lockfile pins ureq 2.12.1
[ok] default ureq agent enables redirects
[ok] redirect code accepts Location without same-origin enforcement
[ok] redirect reconstruction strips authorization/cookie but not x-goog-api-key
[vulnerable] custom Gemini key header survives the locked redirect path
```

This is a local regression check, not a live exploit. A dynamic test for a fixed
implementation can use two loopback listeners and a fake key: the first listener
returns a 302 to the second, and the assertion is that the second listener never
receives `x-goog-api-key`. I did not run that two-listener capture here because
the authorized validation boundary for this write-up excluded network activity.

## Remediation

The invariant to restore is simple: a provider credential header must be added
only to a request whose final origin has been checked against the approved
provider identity. KCS can restore that invariant either by disabling redirects
for credential-bearing Gemini requests or by handling redirects explicitly and
reconstructing credentials only after same-origin and no-downgrade validation.

A minimal defensive shape is to stop using the top-level redirect-following
helper for this request:

```rust
let agent = ureq::AgentBuilder::new()
    .redirects(0)
    .build();

let response: Value = agent
    .post(&format!(
        "{}/v1beta/models/{model_pin}:batchEmbedContents",
        self.base_url()
    ))
    .set("x-goog-api-key", &api_key)
    .set("Content-Type", "application/json")
    .send_json(json!({ "requests": requests }))
    .map_err(http_error)?
    .into_json()
    .map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
```

If product behavior requires redirects, KCS should implement a small redirect
loop outside the HTTP library's credential propagation. The loop should parse
`Location`, require HTTPS, require the same host unless an explicitly approved
recipient set says otherwise, reject scheme downgrades, clear all provider
credential headers before any origin change, and then add the credential only
after the new origin passes policy.

Regression tests should cover both the source-level invariant and a fake
two-origin runtime path:

- a static test that fails if `gemini_embedding.rs` uses a redirect-following
  top-level `ureq::post()` with `x-goog-api-key`;
- a local loopback test where the first origin returns a 302 and the second
  asserts the custom credential header is absent;
- a same-origin redirect test, if redirects remain supported, that confirms
  credential reconstruction happens only after policy approval;
- a 307/308 test to prevent future library or wrapper changes from replaying a
  body and credential across origin boundaries.

## Summary

KCS binds the Gemini credential to the first URL it builds, but the pinned HTTP
client may choose a different final URL after a remote 301/302/303 response.
Because the credential lives in `x-goog-api-key` instead of `Authorization`, the
library's default stripping control does not remove it. We can prove the issue
from the vulnerable KCS source, the lockfile, and the selected `ureq` redirect
implementation without contacting any external service.

The practical impact is disclosure of one Gemini embedding credential to a
redirect target controlled by an accepted, compromised, or misconfigured origin.
The most useful variant work is to audit every provider-specific credential
header and every library-internal redirect path, then centralize outbound
credential handling behind one origin-bound request policy.
