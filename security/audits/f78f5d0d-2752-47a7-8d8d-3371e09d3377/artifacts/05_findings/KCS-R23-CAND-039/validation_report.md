# Validation: Accepted embedding adapter targets are discarded before fixed Gemini execution

- Candidate: `KCS-R23-CAND-039`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-adapter/src/tool_lock.rs:106-231,376-428`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.97)**
- Method: **V10 exact accepted-config-to-wrong-provider-sink trace**

## Rubric

- [x] The embedding configuration validator accepts execution target, model, and authentication fields.
- [x] Conversion to `DeclaredAdapter` drops target fields, while any declared embedding authentication activates real execution.
- [x] The real path ignores the declared tool target and model and always constructs the default Gemini adapter.
- [x] That adapter uses a fixed Gemini model/base selection with the retained declared secret and input text.
- [x] General network opt-in does not bind or disclose the accepted target versus the fixed effective provider.

## Evidence

The same tools schema recognizes the embedding role and accepts `kind`, `cmd`, `args`, `url`, `model`, and `auth` execution/configuration fields at `crates/kcs-adapter/src/tool_lock.rs:106-231`. The adapter specification presents command, URL, and authentication as device-local execution settings at `docs/07-adapter-spec.md:9-23` and distinguishes online, offline, and deterministic kinds at `docs/07-adapter-spec.md:46-67`.

Projection retains only `tool_id`, `model`, and `auth`, dropping the accepted execution kind, command, arguments, and URL at `crates/kcs-adapter/src/tool_lock.rs:376-428`; the CLI registers that reduced embedding declaration at `crates/kcs-cli/src/main.rs:10812-10838`. More importantly, the catalog uses the mere presence of a declared embedding authentication reference to select `AdoptedEmbeddingExecution::Real` at `crates/kcs-adapter/src/catalog.rs:313-343`. The resulting declared profile is the fixed adopted Gemini identity at `crates/kcs-adapter/src/catalog.rs:346-383`.

The real execution branch always calls `GeminiEmbeddingAdapter::default().embed(request)` at `crates/kcs-adapter/src/catalog.rs:386-401`; it does not dispatch the declared tool, command, URL, execution kind, or model. The default adapter constructs `EnvGeminiEmbeddingClient` with the fixed `gemini-embedding-2` model pin and fixed dimensions at `crates/kcs-adapter/src/gemini_embedding.rs:206-220`. That client resolves the retained declared embedding secret but chooses only a programmatic override, `GEMINI_API_BASE`, or Google's default base at `crates/kcs-adapter/src/gemini_embedding.rs:48-80`, then supplies the secret as `x-goog-api-key` for model discovery and the text embedding POST at `crates/kcs-adapter/src/gemini_embedding.rs:84-149`.

Therefore a declaration can name another online provider, a private URL, an offline/command implementation, and a different model, yet its authentication secret and input text are consumed by the fixed Gemini client. The CLI preview exposes generic embedding/network mode rather than the declared-versus-effective target at `crates/kcs-cli/src/main.rs:8736-8797`, so the user is not given the command/URL-specific approval described at `docs/07-adapter-spec.md:312-327`.

## Counterevidence and preconditions

- The current MVP is documented as using official adapters at `docs/07-adapter-spec.md:343-367`. Unsupported declarations could safely fail closed; their present acceptance followed by another provider is the validated defect.
- The device-local configuration is normally operator-controlled. This is nevertheless wrong-recipient disclosure when an operator supplies credentials for the visibly declared non-Gemini target.
- Outer online opt-in, credential availability, budget, and later operator invocation still gate an actual send. They do not compare the consented/declared recipient with Gemini.
- A programmatic or `GEMINI_API_BASE` override can point the fixed client elsewhere, but it is ambient and not derived from the accepted adapter URL.
- No network request was issued; an eligible text embedding operation and a valid declared secret are required for the sink to execute.

Severity is high because a custom-provider secret and indexed text can cross to a different external provider under an accepted declaration. It is not critical because local trusted configuration, generic online consent, credentials, and an operator-driven embedding operation are required.

## Tests and remaining uncertainty

No live embedding request was made under the no-network constraint. The V10 trace is complete from accepted target/model/auth input, through authentication-triggered real-mode selection and fixed Gemini construction, to the API-key-authenticated text sink.

Proof gap: a loopback request capture was not run. A safe regression should declare a non-Gemini URL/model and sentinel secret, then require rejection or prove that execution uses only the exact declared provider/model.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-039 | `crates/kcs-adapter/src/tool_lock.rs:106-231,376-428` | accepted embedding target/model/auth declaration | fixed Gemini API-key-authenticated text requests | reportable | official-adapter MVP and generic network gates remain; no request capture | yes |

Validation artifacts: none (V10 trace only).
