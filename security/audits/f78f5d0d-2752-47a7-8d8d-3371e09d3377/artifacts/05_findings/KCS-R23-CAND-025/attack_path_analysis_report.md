# Attack-path analysis: Store-local consent records are forgeable or replayable across preseeded or copied scopes

- Candidate: `KCS-R23-CAND-025`
- Ledger row: `KCS-R23-CAND-025`
- Instance key: `KCS-R23-CAND-025`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.88)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| store_adoption | `crates/kcs-core/src/scope.rs` | `188-200` |  |
| scope_validation | `crates/kcs-core/src/scope.rs` | `889-909` |  |
| approval_prompt | `crates/kcs-cli/src/main.rs` | `586-610` |  |
| root_control | `crates/kcs-cli/src/main.rs` | `6362-6378` |  |
| network_gate | `crates/kcs-cli/src/main.rs` | `10418-10445` |  |
| secret_gate | `crates/kcs-cli/src/main.rs` | `10543-10555` |  |
| approval_writer | `crates/kcs-cli/src/main.rs` | `10718-10779` |  |

## Scope and actor

### Context

The source actor is the threat model's explicit untrusted shared/archive-state contributor. The forged row does not choose a new destination, but it turns attacker-supplied state into victim network and secret-release authority without proving that the current operator granted it.

### In scope

yes; copied/preseeded store adoption and current scope-by-adapter consent authenticity are explicit I1/I3 boundaries

### Exposure and identity

filesystem-supplied persisted state followed by an operator-invoked outbound adapter call; no public listener

the untrusted store contributor controls scope metadata and approval rows; KCS later uses the victim OS identity and configured provider credential

### Boundary crossed

yes; untrusted archive state crosses into network-authorization and secret-release decisions, then can cause local content to cross the external-adapter boundary

### Authorization scope

internal-only; adopted local store plus later operator command, with no authentication of the stored consent's author

## Preconditions and attacker control

### Assumptions

- The victim adopts a lower-trust copied or preseeded store rather than an already private live store being arbitrarily modified.
- A matching provider and credential are configured and the victim invokes an eligible online command.
- Offline mode and network revocation are not active.

### Preconditions

plausible but multi-step: victim adopts supplied state, has online adapter configuration, invokes an eligible command, and has not revoked network use

### Attacker control

yes; the supplied-store contributor controls the self-matching scope_id and unsigned approval records consumed by the gates

### Vector

none

## Attack path

- A lower-trust archive contributor supplies a copied or preseeded .kcs store containing a self-consistent scope_id plus forged persistent network and, optionally, send_secrets approval rows.
- The victim adopts the store; repository open validates schema and ULID shape but not consent provenance or current-root binding.
- The victim later invokes an online-capable index, resume, retry, or search workflow with a configured provider.
- KCS trusts the supplied approvals, skips fresh network consent and secret holds for the matching tool, and sends eligible local content through the victim's configured adapter.

## Impact and reach

- Category: forged/replayed persistent authorization and consent provenance failure
- Impact: **high**
- Likelihood: **medium**

### Impact surface

network authorization, secret-release policy, and confidentiality of content in one adopted scope

### Target reach

one adopted scope and each matching configured adapter; send_secrets rows can affect secret-classified chunks in that scope

### Secret references

- Victim provider credentials are attached to the later request.
- A forged approval_method=send_secrets row can release secret-classified content to the configured provider.

## Controls and counterevidence

### Existing controls

- scope_id and tool_id matching
- offline and scope-local network revocation
- execution-mode checks
- operator-invoked online workflow

### Mitigations

- Offline mode and network revocation override stored consent.
- Approval remains scoped to a known adapter tool_id and execution mode.
- The victim must adopt the store and invoke an online-capable command.
- Documentation treats .kcs as portable authoritative state, creating ambiguity for trusted moves but not authenticating an untrusted import.

### Counterevidence

- A row copied from a different scope_id is rejected.
- The destination remains the victim's configured provider rather than an attacker-selected endpoint in this candidate.
- Offline mode, revocation, absent credentials, or no later eligible command defeats the send.

### Blind spots or proof gap

- No same-ID forged-store end-to-end send was retained.
- The evidence does not establish that the archive contributor also controls or can observe the configured provider destination.

## Final decision

The preseeded-store contributor is a realistic lower-trust actor expressly included by the threat model, so same-user and operator-only suppression do not apply. Forged approval can release secret-bearing data, but adoption and a later configured online workflow constrain likelihood; high impact plus medium likelihood maps to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
