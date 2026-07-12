# Attack-path analysis: scan hashing allocates the full file before the input-size gate

- Candidate: `KCS-R23-CAND-032`
- Ledger row: `KCS-R23-CAND-032`
- Instance key: `KCS-R23-CAND-032`
- Final policy: **reportable**
- Final severity: **medium**
- Priority: **P2**
- Confidence: **high**

## Affected locations

| Label | Path | Lines | Detail |
| --- | --- | --- | --- |
| normal index enables raw hashing | `crates/kcs-cli/src/main.rs` | `558-584` |  |
| metadata length then whole-file allocation | `crates/kcs-pipeline/src/scan.rs` | `90-159` |  |
| late adapter-only input gate | `crates/kcs-cli/src/main.rs` | `9047-9070` |  |
| configured/default cap | `crates/kcs-cli/src/main.rs` | `4425-4444` |  |

## Scope and actor

### Context

This deterministic normal-index path lets a lower-trust file consume process memory and I/O before a known limit while the store lock is held. Impact is local and recoverable but can deny indexing for the scope and stress the host.

### In scope

Yes.

### Exposure and identity

No network exposure. The attack surface is an operator-selected local/shared scope containing lower-trust direct-child content.

The KCS process runs as the invoking OS user and consumes that user's memory, I/O bandwidth, and scope lock; no service account or credential is involved.

### Boundary crossed

Verified: attacker-controlled file length crosses the scope-filesystem/parser boundary into unbounded whole-file allocation before the configured policy control.

### Authorization scope

internal-only

## Preconditions and attacker control

### Assumptions

- The contributor can add a readable, included regular direct-child file to a scope the operator indexes.
- The file is not ignored, secret-excluded, a symlink, or a directory.
- The operator runs ordinary non-preview indexing.

### Preconditions

- Ability to supply an included regular file in the selected root.
- Operator invocation of normal indexing rather than --preview.
- Sufficient filesystem capacity or sparse-file support to present a large logical size.

### Attacker control

yes — the contributor directly controls file size and contents; allocation is deterministic and requires no race.

### Vector

none

## Attack path

- An in-scope content contributor places an included oversized or sparse regular file as a direct child of a selected scope.
- The operator runs normal non-preview indexing, which calls build_scan_preview with include_raw_hashes=true.
- The scanner already knows the logical length but calls std::fs::read on the whole file at crates/kcs-pipeline/src/scan.rs:122-149 before consulting the configured adapter cap.
- The process incurs O(n) allocation, I/O, and hashing while holding the scope store lock; the later cap at crates/kcs-cli/src/main.rs:9047-9070 only prevents downstream normalization/send.

## Impact and reach

- Category: CWE-400 uncontrolled resource consumption / whole-file allocation before size enforcement
- Impact: **medium**
- Likelihood: **high**

### Impact surface

runtime

### Target reach

One indexing process and the selected scope's store-lock availability per invocation; host memory and I/O may also be pressured.

### Secret references

- None.

## Controls and counterevidence

### Existing controls

- direct-child/type/ignore filtering
- preview-mode hash suppression
- late effective input-size gate
- operator recovery by removing the file

### Mitigations

- Directories, symlinks, ignored entries, .kcs state, XDG state, and Tier-A secret exclusions do not enter this read.
- --preview disables raw hashing.
- The later default/configured 100 MiB adapter cap prevents oversized normalization and network submission.
- The operator can remove the file and retry.

### Counterevidence

- The later cap correctly prevents adapter work and egress, so confidentiality and billed-network impact do not follow.
- The failure is recoverable by removing the file and retrying.
- No deliberate high-memory exhaustion run measured peak RSS.

### Blind spots or proof gap

- Actual process termination thresholds and host-wide impact depend on allocator, OS, and available memory.
- Sparse-file behavior varies by filesystem, although the source-order allocation proof does not depend on sparseness.

## Final decision

The lower-trust direct-child file is an explicit threat-model surface and normal indexing deterministically reaches the pre-cap whole-file allocation, so hard suppression does not apply. Impact is medium because availability loss is substantial but local and recoverable; likelihood is high because no race, privilege, or unusual command is required once the operator indexes the supplied scope. The matrix maps medium impact plus high likelihood to Medium/P2.

The strict impact/likelihood matrix therefore yields **medium**
with policy **reportable** and priority **P2**.
