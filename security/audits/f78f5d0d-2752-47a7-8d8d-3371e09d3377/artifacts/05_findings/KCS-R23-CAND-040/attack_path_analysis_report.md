# Attack-path analysis: Gemini API keys are retained across cross-origin redirects

- Candidate: `KCS-R23-CAND-040`
- Ledger row: `KCS-R23-CAND-040`
- Instance key: `KCS-R23-CAND-040`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.96) for header retention; medium for real-world redirect occurrence**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| credential_source | `crates/kcs-adapter/src/gemini_embedding.rs` | `71-80` | Resolves the declared embedding secret or GEMINI_API_KEY. |
| custom_header_sink | `crates/kcs-adapter/src/gemini_embedding.rs` | `120-148` | Places the credential in x-goog-api-key on a top-level ureq POST with no redirect policy. |
| production_reachability | `crates/kcs-adapter/src/gemini_embedding.rs` | `206-220,259-285` | The adopted default adapter reaches the environment-backed client's embed call. |
| dependency_selection | `Cargo.toml` | `17-29` | Selects ureq without a configured wrapper or redirect override. |
| dependency_pin | `Cargo.lock` | `1396-1411` | Pins ureq 2.12.1, whose resolved redirect code defaults to five redirects and retains custom headers. |

## Scope and actor

### Context

Normal adopted embedding execution reaches a remote-response trust boundary. The configured service identity is an operator choice, but redirect destinations are remote-controlled and are not rebound to that approved identity.

### In scope

yes; credential-origin and redirect-destination binding are explicit I3 security properties

### Exposure and identity

outbound authenticated adapter request with a remote-controlled redirect response; no KCS listener exists

The approved Gemini service or an accepted intermediary controls the redirect response; the unauthorized redirect origin receives the reusable API credential.

### Boundary crossed

yes: x-goog-api-key crosses from the approved provider origin to a second, unapproved origin

### Authorization scope

internal-only (credentialed, operator-approved adapter operation)

## Preconditions and attacker control

### Assumptions

- The initially approved HTTPS origin is trusted enough to receive the key but may be compromised, misconfigured, or redirect through a lower-trust origin.
- The redirected origin can observe the custom API-key header.
- A cross-origin 301/302/303 occurs; this behavior was not established for the default Google endpoint.

### Preconditions

- Valid Gemini credential and per-adapter network opt-in
- An operator-driven embedding operation
- The accepted origin returns a cross-origin 301, 302, or 303
- The redirect target is observable by a lower-trust recipient

### Attacker control

yes over the redirect target when the accepted origin, compromised service, or relevant intermediary can emit the response; no default-endpoint open redirect was proven

### Vector

remote

## Attack path

- An operator performs an approved embedding operation using a valid Gemini credential.
- KCS sends the request with the credential in x-goog-api-key through the default ureq 2.12.1 agent.
- The accepted origin returns a 301, 302, or 303 with a cross-origin or downgraded Location.
- ureq rewrites the POST to a bodyless GET, strips standard Authorization/Cookie headers but retains x-goog-api-key, and sends that credential to the redirect origin.

## Impact and reach

- Category: cross-origin credential forwarding on redirect
- Impact: **high**
- Likelihood: **medium**

### Impact surface

identity

### Target reach

one Gemini credential and each embedding request encountering a qualifying redirect

### Secret references

- Declared embedding secret or GEMINI_API_KEY
- x-goog-api-key request header retained across redirect

## Controls and counterevidence

### Existing controls

- Disable redirects for credential-bearing requests or enforce same-origin and no-scheme-downgrade redirect policy.
- Strip all provider credential headers before any origin change.

### Mitigations

- HTTPS authenticates the initial origin against ordinary on-path response injection.
- Per-adapter opt-in and a valid credential are required.
- The embedding body is discarded on 301/302/303, so this path proves credential rather than text disclosure.
- Body-bearing 307/308 POST responses are not automatically followed by this exact path.
- ureq removes standard Authorization and Cookie headers, but not x-goog-api-key.

### Counterevidence

- No open redirect or cross-origin redirect was established at Google's default endpoint.
- A malicious custom base already receives the key on the initial request.
- HTTPS blocks an ordinary on-path attacker from injecting the first redirect.
- The request body is not forwarded on the proven 301/302/303 route.

### Blind spots or proof gap

- No two-origin loopback capture was run.
- The frequency and destination behavior of real accepted-origin redirects are unknown.

## Final decision

A remote in-scope actor can cause a reusable credential to cross an approved origin boundary. The missing evidence that the default endpoint actually issues such a redirect constrains likelihood to medium. The mandatory matrix maps high impact and medium likelihood to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
