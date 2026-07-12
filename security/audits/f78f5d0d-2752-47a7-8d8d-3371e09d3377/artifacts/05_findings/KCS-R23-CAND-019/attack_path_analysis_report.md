# Attack-path analysis: status and snapshot read unbounded direct-child files before any cap

- Candidate: `KCS-R23-CAND-019`
- Ledger row: `KCS-R23-CAND-019`
- Instance key: `KCS-R23-CAND-019`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high (0.98)**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| status entry | `crates/kcs-cli/src/main.rs` | `435-442` |  |
| working-tree builder | `crates/kcs-core/src/scope.rs` | `261-309` |  |
| snapshot entry | `crates/kcs-core/src/scope.rs` | `373-386,413-427` |  |
| unrelated later input cap | `crates/kcs-cli/src/main.rs` | `4425-4444,9047-9061` |  |

## Scope and actor

### Context

KCS has no listener; this is a filesystem-mediated availability path. Impact crosses from lower-trust scope content into the victim KCS process, but remains local, recoverable, and limited to the selected workflow.

### In scope

yes; untrusted direct-child files and bounded local processing are explicit threat-model surfaces under I6 and I12

### Exposure and identity

not public; reachable through local CLI processing of an adopted or shared scope

KCS runs as the victim OS user with that user's filesystem and memory limits; the attacker needs no KCS or OS-administrator identity

### Boundary crossed

yes; lower-trust file size crosses the scope-content boundary into victim-process memory, I/O, and archive storage

### Authorization scope

internal-only; local filesystem and CLI surface with no network authentication boundary

## Preconditions and attacker control

### Assumptions

- The selected scope is shared, supplied, or otherwise writable by a lower-trust content contributor.
- The hostile file is a direct regular child and is not explicitly excluded.
- The victim invokes a routine status or snapshot command.

### Preconditions

plausible: control one included direct-child file and wait for the operator to run status or snapshot; sparse files can make the logical-size amplification inexpensive

### Attacker control

yes; the lower-trust contributor controls the included file's logical size and bytes

### Vector

none

## Attack path

- A lower-trust content contributor places a very large or sparse regular direct-child file in a scope the victim uses.
- The victim runs status or snapshot on that scope.
- The working-tree builder accepts the file through the type, name, and exclusion filters and calls fs::read before applying any byte ceiling.
- The victim process allocates and reads attacker-sized bytes; snapshot can additionally copy them into the archive, causing command failure or substantial local resource pressure.

## Impact and reach

- Category: resource consumption / local denial of service (CWE-400, CWE-770)
- Impact: **medium**
- Likelihood: **high**

### Impact surface

runtime memory and I/O; snapshot also affects archive disk usage

### Target reach

one KCS process and selected scope per invocation

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- direct-child, file-type, and exclusion filtering
- snapshot store lock
- late adapter-only input-size gate

### Mitigations

- Subdirectories, symlinks observed at enumeration, non-regular entries, and explicit exclusions are skipped.
- Status does not persist the bytes and snapshot holds the store lock.
- The operator can remove the hostile file and retry.

### Counterevidence

- The later effective_max_input_bytes control applies only to adapter processing and does not protect status or snapshot.
- The command is recoverable after removing the file and does not create a confidentiality or authorization bypass.

### Blind spots or proof gap

- No large or sparse-file runtime measurement was retained; actual failure thresholds depend on host limits.

## Final decision

A realistic lower-trust scope contributor can deterministically reach a victim resource sink through routine commands, so self-only suppression does not apply. The required matrix maps medium impact plus high likelihood to medium.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
