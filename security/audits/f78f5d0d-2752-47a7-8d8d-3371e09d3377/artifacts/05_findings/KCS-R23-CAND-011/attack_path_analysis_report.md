# Attack-path analysis: a new secret content twin is vector-linked before its hold exists

- Candidate: `KCS-R23-CAND-011`
- Ledger row: `KCS-R23-CAND-011`
- Instance key: `KCS-R23-CAND-011`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| rebuild-before-enrichment ordering | `crates/kcs-cli/src/main.rs` | `620-653` |  |
| task-derived hold denylist | `crates/kcs-cli/src/main.rs` | `3008-3027` |  |
| content-twin relink | `crates/kcs-index/src/embedding_store.rs` | `149-185` |  |
| already-linked filtering | `crates/kcs-cli/src/main.rs` | `7848-7936` |  |

## Scope and actor

### Context

Normal sequential index execution; no private-store corruption, race, or privileged access is required.

### In scope

Yes.

### Exposure and identity

Untrusted local scope content enters trusted vector-index and search state through ordinary indexing; no network listener or unauthorized outbound send is involved.

A local content contributor or shared/synced archive contributor controls the new file, while the operator and its automation consume trusted search state.

### Boundary crossed

Yes.

### Authorization scope

internal-only: no network authorization is bypassed, but the local secret-hold and trusted-search policy boundary is crossed.

## Preconditions and attacker control

### Assumptions

- The scope accepts files from a local or shared/synced lower-trust contributor.
- An identical public text twin already has a current-profile embedding.
- The new file receives Tier-B classification and the operator has not approved sending secrets.

### Preconditions

- An existing public embedded twin.
- A new secret-labeled content twin.
- An ordinary index command without --send-secrets.

### Attacker control

The lower-trust contributor controls the new file's name and bytes and can deterministically satisfy the content-twin condition.

### Vector

none

## Attack path

- A public chunk is embedded under the active profile.
- A lower-trust scope contributor adds a Tier-B secret-labeled file containing the same chunk text.
- Index rebuild runs before secret-hold creation and links the new chunk to the existing embedding by text_hash.
- Because no hold task yet exists, the task-derived denylist does not exclude the new secret chunk.
- Later enrichment treats the linked chunk as complete, so no hold is created.
- Vector search exposes the secret file's path, provenance, and policy-visible presence.

## Impact and reach

- Category: secret-policy and search-identity bypass
- Impact: **medium**
- Likelihood: **high**

### Impact surface

data: secret path/provenance visibility and durable vector-search policy integrity

### Target reach

Secret twin chunks in the indexed scope that share text with an existing embedding.

### Secret references

- Tier-B secret classification
- secrets_tier_b_hold
- --send-secrets

## Controls and counterevidence

### Existing controls

- The rebuild denylist uses already persisted hold-task IDs.
- Secret partitioning is present but is skipped after the premature content link.
- Already-linked completion filtering prevents the missing hold from catching up.

### Mitigations

- Existing secret-hold task IDs are excluded from rebuild.
- Secret partitioning would create a hold if the chunk reached enrichment.
- The identical text already exists in a public twin and is not newly transmitted.

### Counterevidence

- The identical text is already present in a public twin.
- No secret bytes are newly transmitted.
- Disclosure is limited to secret path/provenance and policy visibility.

### Blind spots or proof gap

- The permitted artifacts do not quantify downstream reliance on secret-path search results.
- A contributor may already know the file it supplied, though other search consumers need not.

## Final decision

A realistic lower-trust path exists: an ordinary content contributor controls names and bytes, and deterministic normal indexing crosses that content into trusted vector/search state without store tampering. Impact is bounded because the text is already public and no send occurs. Medium impact plus high likelihood maps mechanically to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
