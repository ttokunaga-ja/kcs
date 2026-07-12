# Attack-path analysis: Persisted manifest unit_ref can escape its normalized-instance directory

- Candidate: `KCS-R23-CAND-049`
- Ledger row: `KCS-R23-CAND-049`
- Instance key: `KCS-R23-CAND-049:manifest-unit-ref-cross-scope`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.88)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoint | `crates/kcs-pipeline/src/markdownize.rs` | `65-84` |  |
| root_control_and_read_sink | `crates/kcs-cli/src/main.rs` | `3355-3383` |  |
| index_sink | `crates/kcs-cli/src/main.rs` | `3030-3127` |  |
| previous_instance_sink | `crates/kcs-cli/src/main.rs` | `9685-9713` |  |

## Scope and actor

### Context

Lower-trust persisted metadata directs the victim process outside the normalized-instance boundary and imports another scope's normalized data using the victim's filesystem authority.

### In scope

yes; archive adoption, path confinement, and normalized provenance are covered by I1 and I7

### Exposure and identity

not public; deterministic local reachability through ordinary processing of an adopted store

KCS reads as the victim OS user. The supplied-store contributor controls unit_ref without requiring arbitrary write access to the victim's private live store.

### Boundary crossed

yes: a manifest entry escapes its instance and imports a victim-readable external normalized unit into current-scope derived state

### Authorization scope

internal-only adopted/shared-store workflow

## Preconditions and attacker control

### Assumptions

- The victim adopts copied, shared, synced, or preseeded normalized state.
- The contributor knows or can arrange a victim-readable external normalized-unit JSON path.
- The selected bytes parse as a compatible NormalizedUnitObject and a rebuild/index/incremental workflow runs.

### Preconditions

- Adoption of lower-trust persisted normalized state
- A known or arranged readable external path ending in parseable JSON
- A victim rebuild, index, or incremental invocation
- Compatible provenance fields for live search/evidence attribution

### Attacker control

yes over unit_ref and the supplied manifest; conditional over external path knowledge and compatible contents

### Vector

none

## Attack path

- A lower-trust contributor supplies an adopted store containing a normalized manifest whose Done entry has an absolute or parent-traversing unit_ref.
- NormalizedUnitManifestEntry accepts unit_ref as an unconstrained String at crates/kcs-pipeline/src/markdownize.rs:65-74; only normal writers generate canonical 16-hex references.
- load_normalized_units at crates/kcs-cli/src/main.rs:3367-3389 appends .json, joins the unvalidated reference, and reads the resulting external path; load_previous_instance repeats the sink at lines 9691-9713.
- If the bytes parse as NormalizedUnitObject, their markdown can be chunked and indexed at crates/kcs-cli/src/main.rs:3030-3127 or reused as previous context under the current scope.

## Impact and reach

- Category: path traversal, cross-scope normalized-data read, and provenance/index contamination
- Impact: **high**
- Likelihood: **medium**

### Impact surface

cross-scope data confidentiality, normalized provenance, chunks, search/evidence integrity, and incremental context

### Target reach

one victim-readable normalized unit per malicious manifest entry, repeatable within an adopted scope

### Secret references

- A referenced normalized unit can contain sensitive document text from another scope; arbitrary non-JSON credentials are not directly readable through this parser.

## Controls and counterevidence

### Existing controls

- Enforce the canonical unit_ref format during deserialization and before reads.
- Canonicalize and prove containment beneath the normalized-instance directory.
- Rebind every unit object to the requested scope/raw/profile/generation tuple before indexing or reuse.

### Mitigations

- Normal writers derive canonical 16-lowercase-hex unit references.
- Only Done entries are loaded.
- The target receives a .json suffix and must deserialize as NormalizedUnitObject.
- Search liveness joins chunks to current tree/profile/generation tuples.
- OS permissions limit readable external units.

### Counterevidence

- Fresh stores are intended owner-only, so ordinary direct-child contributors cannot normally edit a healthy live manifest.
- Arbitrary files fail because the path gains a .json suffix and content must match the normalized-unit schema.
- Tuple-mismatched units can be excluded from live search, although they can still enter persisted chunks or incremental reuse.
- Direct disclosure back to the contributor depends on a shared/synced store or another consumer of the contaminated scope.

### Blind spots or proof gap

- No two-root runtime regression or demonstrated shared-store readback was retained.
- Sibling normalized-store path predictability is unmeasured.
- CAND-047 and CAND-061 cover adjacent directory-selection and semantic-tuple roots.

## Final decision

Hard suppression does not apply because supplied-store adoption is an explicit lower-trust boundary and KCS exercises victim filesystem authority outside the selected instance. Cross-scope normalized-data import and trusted evidence contamination are High impact; adoption, path knowledge, schema compatibility, invocation, and tuple/readback constraints make likelihood Medium. The matrix yields Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
