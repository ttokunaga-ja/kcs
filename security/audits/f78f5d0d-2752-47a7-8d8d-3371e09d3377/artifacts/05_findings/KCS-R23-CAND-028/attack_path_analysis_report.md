# Attack-path analysis: Mistral OCR reopens the path after the final hash check and sends unbound bytes

- Candidate: `KCS-R23-CAND-028`
- Ledger row: `KCS-R23-CAND-028`
- Instance key: `KCS-R23-CAND-028`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| secret_control | `crates/kcs-cli/src/main.rs` | `6050-6066` | Online task selection rechecks secret policy from the persisted lexical input_path. |
| closest_control | `crates/kcs-cli/src/main.rs` | `6533-6614` | Precondition and executor read/hash/size-check earlier path states against task.input_hash. |
| path_handoff | `crates/kcs-cli/src/main.rs` | `6615-6691` | Checked bytes are discarded; preparation and the online wrapper receive only the mutable path and old hash. |
| request_bridge | `crates/kcs-adapter/src/catalog.rs` | `82-101,134-147` | The catalog preserves raw_hash and path as independent request fields and delegates to Mistral. |
| network_sink | `crates/kcs-adapter/src/mistral_ocr.rs` | `112-138` | The client freshly reads path and places that buffer directly in the authenticated OCR POST without comparing raw_hash. |
| identity_sink | `crates/kcs-cli/src/main.rs` | `6674-6722,6770-6792` | Returned content is labeled and persisted under the earlier task.input_hash. |

## Scope and actor

### Context

This is a real online OCR product workflow in a local-first CLI. The attacker enters through mutable selected-scope content rather than a network listener; the security consequence is that bytes not covered by the final identity and secret decision cross the external-adapter boundary.

### In scope

Yes.

### Exposure and identity

No daemon, listener, ingress, or load balancer exists. Exposure is an operator-invoked local CLI operating on a selected root that may contain lower-trust mutable content; the configured remote service is the sink, not the attacker entrypoint.

The OCR request runs as the invoking OS user and attaches the operator-configured Mistral bearer credential. No service account or managed identity is evidenced, and the credential is not shown to be redirected to the contributor.

### Boundary crossed

Verified: lower-trust mutable pathname bytes bypass the approved raw-hash/secret identity and cross from the local selected scope to the configured external OCR service; returned data also enters trusted normalized provenance under the old hash.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- The selected root is shared, synced, or otherwise writable by an in-scope lower-trust content contributor while KCS runs.
- The operator has intentionally enabled the Mistral online adapter and the task passes approval, media, budget, and eligibility gates.
- The contributor can win the post-check/pre-read rename interval; no measured success rate is available.

### Preconditions

- Concurrent rename/write authority in the selected root.
- A pending eligible OCR task and an operator-driven online index, resume, or retry command.
- Configured adapter, network opt-in, approval, credential, and budget availability.
- Favorable scheduling after the final checked read and before the adapter read.

### Attacker control

yes — the contributor controls the replacement pathname target and bytes, but does not control the configured destination in the validated path.

### Vector

none

## Attack path

- A lower-trust contributor leaves an eligible OCR-supported file unchanged through task selection, secret classification, and the executor's final hash, size, and media checks at crates/kcs-cli/src/main.rs:6050-6066 and 6576-6614.
- After the checked buffer is discarded, the contributor atomically replaces the selected-scope pathname before the Mistral adapter's fresh read.
- The production adapter reads the replacement through request.raw.path and posts those bytes with the configured bearer credential at crates/kcs-adapter/src/mistral_ocr.rs:112-138 without comparing them to request.raw.raw_hash.
- KCS persists returned units under the earlier task.input_hash, causing an unapproved external disclosure and false provenance for one task.

## Impact and reach

- Category: CWE-367-style pathname TOCTOU causing exact-byte authorization/secret-decision bypass and provenance corruption
- Impact: **high**
- Likelihood: **medium**

### Impact surface

network

### Target reach

One eligible OCR task/file and its normalized provenance in one scope; the unchecked bytes are sent to one configured provider.

### Secret references

- The configured Mistral bearer credential is attached to the request but is not shown to be exposed to the contributor.
- Replacement document bytes may bypass the prior secret classification and approval decision.

## Controls and counterevidence

### Existing controls

- task.input_hash comparison
- effective input-size and media gates
- secret decision and adapter/network approval
- budget and eligibility checks

### Mitigations

- Replacements before the executor hash check are rejected.
- Secret, media, adapter approval, network-opt-in, tool, and budget gates run before execution.
- The destination is operator-configured rather than automatically attacker-selected.
- A lost race or I/O error prevents the substituted send.

### Counterevidence

- The executor correctly rejects an earlier replacement by hashing current_bytes against task.input_hash and applying size/media checks.
- The provider endpoint is an operator decision, so the trace does not establish credential theft or an attacker-selected exfiltration host.
- No barrier-controlled swap or loopback request capture measured practical race reliability.

### Blind spots or proof gap

- Race success rate across supported operating systems and filesystems is unmeasured.
- The validation did not demonstrate which sensitive replacement sources a contributor can practically name or read through the victim process.

## Final decision

Hard suppression does not apply: the shared/synced-scope contributor is explicitly in scope, does not need privileged private-store access, and the path crosses a core exact-byte authorization boundary in a real product workflow. Impact is high because unapproved document bytes can leave the device and trusted provenance is corrupted; likelihood is medium because online eligibility and an unmeasured rename race are required. The matrix maps high impact plus medium likelihood to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
