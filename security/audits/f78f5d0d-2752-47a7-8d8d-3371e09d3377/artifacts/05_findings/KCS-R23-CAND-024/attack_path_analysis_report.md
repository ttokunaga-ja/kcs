# Attack-path analysis: Opening an existing permissive `.kcs` exposes future private archive bytes

- Candidate: `KCS-R23-CAND-024`
- Ledger row: `KCS-R23-CAND-024`
- Instance key: `KCS-R23-CAND-024`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.97) for the Unix mechanism; medium-high for deployment reachability**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| creation_control | `crates/kcs-core/src/scope.rs` | `135-158` | Existing .kcs returns through open before the new-store owner-only hardening call. |
| root_control | `crates/kcs-core/src/scope.rs` | `188-200` | Repository::open checks is_dir and logical store validity but no owner UID or permission mode. |
| owner_hardening | `crates/kcs-core/src/scope.rs` | `1650-1660` | The available Unix helper sets 0700 and documents the multi-user confidentiality boundary. |
| raw_source | `crates/kcs-core/src/scope.rs` | `254-303` | Snapshot reads direct-child bytes and sends them to ObjectStore. |
| raw_sink | `crates/kcs-core/src/cas.rs` | `60-75,155-176` | Raw CAS publication uses File::create/umask and relies on the parent store mode for confidentiality. |

## Scope and actor

### Context

This is not same-user arbitrary mutation of a private live store. It uses the threat model's in-scope supplied/preseeded-store actor and crosses a distinct Unix principal boundary when KCS adds new private bytes after unsafe adoption.

### In scope

yes; pre-existing store adoption, owner-only archive confidentiality, and shared-state contributors are explicit I1/I3 surfaces

### Exposure and identity

not public; local multi-user or shared-filesystem store reached through normal init/open and snapshot/index commands

the victim KCS process writes with the victim OS identity; a lower-privileged local principal reads through unsafe store and object modes

### Boundary crossed

yes; victim-only source bytes become readable across an OS-principal filesystem boundary

### Authorization scope

internal-only; lower-privileged local filesystem principal, not administrator or same-user unrestricted private-state access

## Preconditions and attacker control

### Assumptions

- A multi-principal Unix host or shared filesystem enforces ordinary DAC semantics.
- The victim adopts a valid existing store that is writable by KCS but readable or traversable by the lower-trust principal.
- The victim later adds private content and the process umask does not independently force 0600 objects.

### Preconditions

plausible but constrained: unsafe supplied or pre-existing store, victim adoption and later mutation, multi-principal access, and a non-0077 umask

### Attacker control

plausible; the lower-trust archive contributor can control or preserve the supplied store's ownership/mode state without needing victim credentials

### Vector

none

## Attack path

- A lower-trust participant supplies, precreates, or influences a structurally valid existing .kcs store whose Unix ownership or permissions do not provide the expected owner-only boundary.
- The victim adopts the scope and Repository::open accepts the store without rejecting or repairing its owner, type, or mode.
- The victim later snapshots or indexes a private direct-child file while using an ordinary permissive umask.
- KCS writes verbatim raw bytes as a group/world-readable CAS object beneath a traversable store, allowing a different local principal to read data that remained private at the source path.

## Impact and reach

- Category: improper ownership and permission validation causing sensitive-data exposure (CWE-276, CWE-732)
- Impact: **high**
- Likelihood: **medium**

### Impact surface

archive confidentiality and integrity on multi-user filesystems

### Target reach

all new raw objects written into one unsafely adopted store; the retained proof demonstrated one private file

### Secret references

- Raw CAS objects contain verbatim document bytes and may include document secrets.

## Controls and counterevidence

### Existing controls

- 0700 hardening for newly created stores
- logical scope and store validation
- content-addressed object publication
- ambient umask

### Mitigations

- Fresh stores are explicitly hardened to 0700.
- Repository open validates logical store structure.
- A 0077 process umask can incidentally produce owner-only raw files.
- The demonstrated path is Unix-specific and read-only trusted archives are a legitimate use case.

### Counterevidence

- No second OS-account read was executed, though the observed 0600 source, 0755 store, and 0644 raw object establish the Unix DAC result.
- A 0077 umask or a securely permissioned trusted store defeats the demonstrated confidentiality path.
- Exposure of bytes already present before open is not attributed to KCS; the validated impact is new bytes written after adoption.

### Blind spots or proof gap

- Non-Unix ACL and ownership behavior was not assessed.
- The exact supplied-store transfer mechanism and principal layout remain deployment-specific.

## Final decision

A supplied-store contributor and a different local OS principal are realistic in-scope actors, so privileged-only suppression does not apply. The disclosure can include private documents, but requires local setup and victim adoption; high impact plus medium likelihood maps to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
