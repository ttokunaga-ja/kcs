# Attack-path analysis: normalized manifests and unit objects are not rebound to the requested provenance tuple

- Candidate: `KCS-R23-CAND-061`
- Ledger row: `KCS-R23-CAND-061`
- Instance key: `KCS-R23-CAND-061`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| unbound normalized reader | `crates/kcs-cli/src/main.rs` | `3355-3390` |  |
| chunk provenance sink | `crates/kcs-index/src/chunking.rs` | `167-185` |  |
| rebuild consumer | `crates/kcs-cli/src/main.rs` | `3045-3090` |  |
| search attribution sink | `crates/kcs-cli/src/main.rs` | `2107-2120` |  |

## Scope and actor

### Context

The .kcs archive is authoritative after adoption but can originate from a lower-trust copied/preseeded source. Schema and path checks prove shape/location only. The missing semantic rebinding lets supplied state cross into trusted search and Evidence content, which is a meaningful core-product integrity boundary.

### In scope

Yes.

### Exposure and identity

No public listener; local adoption of a copied/shared scope followed by routine index, repair, search, or Evidence operations.

KCS processes the store as the invoking OS user. The lower-trust contributor needs control of the supplied archive before adoption, not arbitrary write access to the victim's already-private live store.

### Boundary crossed

Yes.

### Authorization scope

internal-only adopted-store workflow with a meaningful archive trust boundary

## Preconditions and attacker control

### Assumptions

- The operator adopts a copied, shared, synced, or preseeded .kcs store from a lower-trust contributor, as expressly covered by the threat model.
- The contributor knows the public on-disk schemas and places parse-valid files at the requested normalized-instance path.
- The operator runs a rebuild/index/search workflow that consumes the poisoned state.

### Preconditions

- Supply or influence a copied/preseeded .kcs store before the operator adopts it.
- Craft schema-valid manifest and unit objects at the normalized-instance location used by a live tree entry.
- The operator performs rebuild/index and later consumes search or Evidence output.

### Attacker control

yes over the supplied persisted normalized state and markdown; no private live-store or OS-administrator authority is required in the adopted-store scenario

### Vector

none

## Attack path

- A shared, copied, or preseeded scope contributor supplies parse-valid normalized manifest and unit files under the directory for a live tree entry's requested raw-hash/profile/generation tuple.
- The objects self-declare attacker-chosen raw_hash, profile, generation, unit key, and markdown values that are inconsistent with their requested directory or manifest entry.
- During index, reindex, or repair rebuild, load_normalized_units parses those files but does not compare the requested tuple to the manifest, entry, unit_ref, or unit object.
- chunk_normalized_units hashes and stores chunks from the unverified self-declared identity and text; rebuild/search/evidence consumers then expose durable attacker-chosen content with trusted-looking provenance.

## Impact and reach

- Category: persisted-state provenance confusion and durable false-evidence injection
- Impact: **high**
- Likelihood: **medium**

### Impact surface

durable data integrity, search attribution, and Evidence provenance

### Target reach

crafted documents/units in one adopted scope, with downstream search and Evidence consumers

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Compare the requested raw_hash/profile/gen tuple with manifest identity before reading units.
- Bind every manifest entry to its derived unit_ref and compare entry key/type/prepared hash with the unit object.
- Reject mismatches before chunking and rebuilding derived search state.

### Mitigations

- Normalized-instance path construction uses the requested raw hash, profile, and generation.
- Manifest and unit JSON must deserialize into typed schemas.
- Later pointer checks bind to stored ChunkRow fields, but cannot recover the missing binding to the original normalized source.

### Counterevidence

- Path construction and typed JSON parsing constrain location and shape.
- A mismatch that does not join a live tree tuple can be omitted rather than surfaced as false evidence.
- Direct arbitrary modification of an already-private live store by the same unrestricted OS user would confer equivalent authority and is not the relied-upon attacker model.
- No public network surface distributes the poisoned state automatically.

### Blind spots or proof gap

- No full poisoned-store runtime was executed during central validation, although the source-to-sink trace is complete.
- The frequency of operators adopting archives that retain contributor-controlled .kcs state is unknown.

## Final decision

The copied/preseeded-store contributor is explicitly in scope and can deterministically inject durable false evidence without already possessing private live-store authority. Impact is High because trusted provenance and downstream Evidence can be substituted; local archive adoption and crafted-state prerequisites make likelihood Medium. The matrix maps High plus Medium to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
