# Validation: Gemini API keys are retained across cross-origin redirects

- Candidate: `KCS-R23-CAND-040`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-adapter/src/gemini_embedding.rs:62-80,120-148`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.96)**
- Method: **V10 exact repository-to-locked-dependency redirect trace**

## Rubric

- [x] Normal adopted embedding execution reaches a default `ureq` request carrying the resolved Gemini secret in `x-goog-api-key`.
- [x] The repository lockfile pins the dependency version whose redirect implementation was inspected.
- [x] Default requests automatically follow redirect responses that can change origin or scheme.
- [x] Redirect reconstruction strips standard credential headers but retains the custom Gemini key header.
- [x] KCS performs no post-redirect origin/scheme comparison or credential removal before the redirected send.

## Evidence

The normal production source and first sink are exact. The client resolves the declared embedding secret or `GEMINI_API_KEY` at `crates/kcs-adapter/src/gemini_embedding.rs:71-80`. `GeminiEmbeddingAdapter::default` uses the environment-backed client and fixed adopted model at `crates/kcs-adapter/src/gemini_embedding.rs:206-220`; `EmbeddingAdapter::embed` reaches the client at `crates/kcs-adapter/src/gemini_embedding.rs:259-285`. The client builds a URL from its effective base, places the secret in the nonstandard `x-goog-api-key` header, and submits the JSON request with the top-level `ureq::post` API at `crates/kcs-adapter/src/gemini_embedding.rs:120-148`. No agent or redirect policy is supplied by KCS.

The immutable dependency selection is `ureq 2.12.1` at `Cargo.lock:1396-1411`, selected by the workspace declaration at `Cargo.toml:17-29`. The resolved source at `$CARGO_HOME/registry/src/index.crates.io-1949cf8c6b5b557f/ureq-2.12.1/src/lib.rs:512-519,580-583` shows that the top-level request constructs a default `AgentBuilder`. That builder enables five redirects by default at `ureq-2.12.1/src/agent.rs:251-266`.

The closest control is incomplete. `ureq-2.12.1/src/unit.rs:154-187` accepts any parsed absolute or relative `Location` joined to the previous URL without a same-origin or no-downgrade requirement. For 301, 302, or 303, a POST becomes a GET at `unit.rs:189-204`. The redirect path then reuses the prior header vector and removes only `content-length`, `cookie`, and (by default) `authorization` at `unit.rs:206-235`. `x-goog-api-key` matches none of those names, so it remains on the reconstructed request to the new host/scheme.

The adopted immutable model returns early from model resolution, so the ordinary exploitable path is the embedding POST. A 301/302/303 response empties the body but forwards the API key to the `Location` origin. Body-bearing POST requests are not automatically followed for 307/308, which limits this exact instance to the redirect statuses above; it does not protect the credential on 301/302/303. No KCS layer sees the redirect target after `ureq` handles it, so general network opt-in for the initial Gemini adapter cannot bind the key to the final origin.

## Counterevidence and preconditions

- An accepted origin must return a cross-origin 301, 302, or 303. The repository does not establish an open redirect at Google's default endpoint.
- A deliberately malicious configured base already receives the key on the first request; the incremental risk is a trusted, compromised, misconfigured, or intermediary-controlled accepted origin redirecting it to a second unauthorized origin.
- HTTPS authenticates the initial host and prevents an ordinary on-path attacker from injecting a redirect. It does not constrain a redirect legitimately returned by that host.
- The POST request body is discarded on 301/302/303, and body-bearing POST 307/308 responses are returned rather than followed. This candidate proves credential disclosure, not redirected embedding-text disclosure.
- Adapter configuration, a valid credential, per-adapter network opt-in, and an operator-driven embedding operation remain required.

Severity is high because a reusable API credential crosses from the approved provider origin to an unapproved redirect origin under a normal remote response, matching the threat model's credential-origin invariant. It is not critical because the accepted origin must emit the redirect, normal online approval and execution are still required, and this redirect path does not forward the embedding request body.

## Tests and remaining uncertainty

No loopback listeners or external request were started under the no-network constraint. The V10 trace is complete through the exact locked dependency: default redirect count, `Location` parsing, method transition, retained header vector, and redirected connection are explicit in the resolved `ureq 2.12.1` source.

Proof gap: a two-origin capture was not run, and no redirect behavior of the default Google endpoint was established. A safe regression should use two loopback listeners with a fake key, return a 302 from the first, and assert the second never receives `x-goog-api-key`.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-040 | `crates/kcs-adapter/src/gemini_embedding.rs:62-80,120-148` | cross-origin 301/302/303 from the accepted embedding origin | redirected `ureq` request retaining `x-goog-api-key` | reportable | accepted origin must redirect; no default-endpoint open redirect or loopback capture | yes |

Validation artifacts: none (V10 trace only).
