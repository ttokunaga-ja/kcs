# Attack-path analysis: Raw-hash working-tree resolution reads every direct child without bounds

- Candidate: `KCS-R23-CAND-057`
- Ledger row: `KCS-R23-CAND-057`
- Instance key: `KCS-R23-CAND-057:raw-resolver-unbounded-scan`
- Final policy: **reportable**
- Final severity: **low**
- Priority: **P3**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| entrypoints | `crates/kcs-cli/src/main.rs` | `2796-2825` |  |
| wrapper | `crates/kcs-cli/src/main.rs` | `4993-5007` |  |
| root_control_and_sink | `crates/kcs-cli/src/main.rs` | `5165-5188` |  |

## Scope and actor

### Context

KCS has no listener, but untrusted scope files and caller-supplied pointers are explicit product inputs. The resource effect crosses from lower-trust content into the victim process deterministically, while remaining local, per-command, and recoverable.

### In scope

Yes.

### Exposure and identity

Local CLI processing of an adopted/shared scope; no public port or inbound network service.

The victim KCS process runs as the operator's OS user. The lower-trust contributor needs file-content control in the selected scope but no private .kcs write, credential, administrator, or shell access on the victim process.

### Boundary crossed

Yes.

### Authorization scope

internal-only local filesystem and CLI workflow

## Preconditions and attacker control

### Assumptions

- The selected scope is supplied, shared, synced, or otherwise contains files controlled by a lower-trust contributor.
- At least one included direct-child regular file is large enough to create material resource pressure.
- The operator or calling automation invokes a raw-object resolution whose match is absent or late in directory enumeration.

### Preconditions

- Control an included large regular file in an operator-selected scope.
- Cause or wait for open/view/Evidence resolution of an absent or late-matching raw hash.
- Host resource limits must be low enough relative to the visited file size for visible degradation or failure.

### Attacker control

yes over file size/content and plausibly over a supplied raw hash or Evidence input; the operator still invokes the local command

### Vector

none

## Attack path

- A lower-trust content contributor places one or more very large or sparse regular direct-child files in a scope the operator uses.
- The contributor or another caller supplies an absent or late-matching raw hash through an open, view, or Evidence workflow.
- Before checking immutable CAS, find_working_tree_raw visits every candidate and fs::read allocates the complete file, then hashes it.
- The victim KCS process incurs O(max n_i) peak input allocation and O(sum n_i) I/O/hash work, potentially failing or becoming unavailable for that command.

## Impact and reach

- Category: uncontrolled local resource consumption / denial of service
- Impact: **medium**
- Likelihood: **medium**

### Impact surface

runtime memory, disk I/O, and CPU availability

### Target reach

one KCS process and selected scope per resolution command

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- Hash through a bounded streaming reader rather than fs::read.
- Apply per-file and aggregate byte/work ceilings to working-tree lookup.
- Prefer an indexed raw-hash lookup and avoid scanning unrelated files before a verified CAS hit.

### Mitigations

- The .kcs entry, observed directories, symlinks, and special files are skipped.
- Each file Vec is dropped before the next iteration, limiting peak retained input memory to the largest visited file rather than the corpus total.
- Removing the hostile file or avoiding the supplied pointer restores service.

### Counterevidence

- The effect is transient and recoverable and does not authorize network egress, cross-scope access, or durable corruption.
- The victim must invoke a narrower open/view/Evidence path rather than a default background listener.
- No unsafe stress test measured actual RSS or failure thresholds.

### Blind spots or proof gap

- Directory ordering and host memory limits determine the exact work and failure point.
- The prevalence of automatically consumed attacker-supplied Evidence Pointers is unknown.

## Final decision

A realistic lower-trust scope contributor can deterministically reach a material resource sink without private-store or privileged access, so self-only suppression does not apply. The narrower operator-invoked resolution path and transient single-process impact limit likelihood and impact to Medium; the mandatory matrix maps Medium plus Medium to Low/P3.

The strict impact/likelihood matrix therefore yields **low**
with policy **reportable** and priority **P3**.
