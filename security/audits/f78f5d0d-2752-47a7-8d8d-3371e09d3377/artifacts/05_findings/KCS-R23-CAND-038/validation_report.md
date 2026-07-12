# Validation: Accepted markdown adapter targets are discarded before fixed Mistral execution

- Candidate: `KCS-R23-CAND-038`
- Instance key / ledger row: not supplied
- Target: `0e19f3c6489da458e93a982a333c308d92d0a0ae`
- Root control: `crates/kcs-adapter/src/tool_lock.rs:106-231,376-428`
- Disposition: **reportable** (`survives: yes`)
- Severity: **high**
- Confidence: **high (0.96)**
- Method: **V10 exact accepted-config-to-wrong-provider-sink trace**

## Rubric

- [x] The documented/validated markdown configuration accepts an execution kind, command, arguments, URL, model, and authentication reference.
- [x] Conversion to `DeclaredAdapter` drops the execution kind, command, arguments, and URL.
- [x] Normal production markdown execution ignores the declared target and unconditionally constructs the Mistral OCR client.
- [x] The retained declared authentication secret and input document reach the fixed Mistral/effective-base requests.
- [x] Neither validation nor preview rejects or clearly discloses this target substitution before the send.

## Evidence

The configuration surface represents these values as execution choices. The adapter specification says adapter execution is delegated and places command, arguments, URL, and authentication in device-local `tools.toml` at `docs/07-adapter-spec.md:9-23`; it defines online, offline, and deterministic execution modes at `docs/07-adapter-spec.md:46-67`. The schema/parser recognizes markdown roles and accepts string `kind`, `cmd`, `url`, `model`, and valid authentication prefixes, including nested declarations, at `crates/kcs-adapter/src/tool_lock.rs:106-231`. The documented command-style markdown declaration is also accepted by the pinned CLI contract test at `crates/kcs-cli/tests/step3_p0_contract.rs:4689-4707`, and an arbitrary plain URL is accepted at `crates/kcs-cli/tests/step3_p0_contract.rs:4709-4715`.

The accepted execution target is lost during projection. `DeclaredAdapter` contains only `tool_id`, `model`, and `auth`; `declared_adapter_for_role` fills only those fields and discards `kind`, `cmd`, `args`, and `url` at `crates/kcs-adapter/src/tool_lock.rs:376-428`. The CLI registers that reduced declaration for the markdown role at `crates/kcs-cli/src/main.rs:10812-10838`.

The normal production catalog then builds `RawInput` and unconditionally creates `EnvMistralOcrClient` plus `MistralOcrMarkdownizeAdapter` at `crates/kcs-adapter/src/catalog.rs:82-147`. It consults the retained declared model at `crates/kcs-adapter/src/catalog.rs:139-156`, but never the accepted execution kind, command, arguments, URL, or alternative tool target. The Mistral client resolves the retained declared markdown authentication secret and chooses only its programmatic override, `MISTRAL_API_BASE`, or Mistral's default base at `crates/kcs-adapter/src/mistral_ocr.rs:47-80`. It attaches that bearer secret to model discovery and posts the input document bytes to the OCR endpoint at `crates/kcs-adapter/src/mistral_ocr.rs:83-138`.

Thus a declaration that visibly names a custom, private, offline, or command adapter is accepted, but selecting it can send its configured credential and document to Mistral (or the unrelated ambient Mistral base) instead. The CLI preview reports only generic network policy/mode information and not the declared-versus-effective command or URL at `crates/kcs-cli/src/main.rs:8736-8797`. The specification's command/URL preview and approval requirement at `docs/07-adapter-spec.md:312-327` is therefore not met for this path.

## Counterevidence and preconditions

- The current MVP is described as supporting official adapters at `docs/07-adapter-spec.md:343-367`. That can justify rejecting unsupported custom declarations, but not accepting them and silently executing a different provider.
- `tools.toml` is device-local and normally trusted; an adversary does not need to author it for the confusion to disclose an operator-supplied custom-provider secret/document to the wrong provider.
- The retained declared model is honored, and outer network opt-in, credential presence, media, and budget controls still gate the send. Those controls do not bind the chosen recipient to the accepted target.
- No live request was made. The confidentiality consequence requires an eligible document, a resolvable declared secret, approval for online execution, and later operator invocation.
- An operator who intentionally sets `MISTRAL_API_BASE` to the same named private service may avoid recipient drift, but that ambient setting is neither derived from nor compared with the accepted declaration.

Severity is high because an accepted adapter declaration can redirect a provider-specific secret and document content to a different external service. It is not critical because configuration is local/trusted, the send remains behind general online consent and credentials, and an operator must execute an eligible job.

## Tests and remaining uncertainty

No command adapter or network request was executed under the no-network constraint. The V10 trace is complete from accepted fields, through the lossy projection and fixed catalog selection, to bearer-authenticated document upload.

Proof gap: a loopback capture was not run. A safe regression should declare a non-Mistral markdown URL/command and distinct sentinel secret, then assert configuration is rejected before execution or that only the exact declared target receives a request.

## Closure

| Candidate | Root control | Entrypoint/source | Sink/control | Disposition | Counterevidence or proof gap | Survives |
|---|---|---|---|---|---|---|
| KCS-R23-CAND-038 | `crates/kcs-adapter/src/tool_lock.rs:106-231,376-428` | accepted markdown target/model/auth declaration | fixed Mistral bearer-authenticated document requests | reportable | official-adapter MVP and outer online gates remain; no request capture | yes |

Validation artifacts: none (V10 trace only).
