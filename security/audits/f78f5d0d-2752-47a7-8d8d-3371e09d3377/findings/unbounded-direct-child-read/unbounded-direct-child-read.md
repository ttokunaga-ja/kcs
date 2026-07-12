# Status and snapshot read unbounded direct-child files into memory

| Field | Value |
| --- | --- |
| Severity | Medium |
| Priority | P2 |
| Weakness | CWE-400 (uncontrolled resource consumption), CWE-770 (allocation of resources without limits) |
| Confirmed revision | `0e19f3c6489da458e93a982a333c308d92d0a0ae` (`kcs 0.1.0`) |
| Fixed revision | Not identified |
| Affected component | Core working-tree construction used by `kcs status` and `kcs snapshot` |

## Executive Summary

KCS reads every included regular file directly under a scope into a single
`Vec<u8>` while building its working tree. `kcs status` takes this path merely
to calculate raw hashes. `kcs snapshot` takes the same path and then writes the
buffer to the raw content-addressed store. Neither command applies a per-file
or aggregate byte ceiling before the allocation. The configured
`adapter.policy.max_input_bytes` control is consulted later, in adapter
processing, and is not a core status or snapshot limit.

A lower-trust contributor who can place one file in a shared, synchronized, or
otherwise adopted scope can therefore make a victim's routine status or
snapshot operation consume resources proportional to the file's logical size.
A dense file causes correspondingly large memory and read I/O. A sparse file
can be cheaper to create while still making `fs::read` materialize its holes in
the process buffer; the first snapshot of that content can also expand it into
a dense raw object. Depending on host limits, the result can be long command
latency, allocation failure or process termination, and snapshot failure from
storage exhaustion. The hostile file keeps retriggering the condition until it
is removed, moved out of the direct-child set, or handled by a new core policy.

The effect is local and recoverable. KCS exposes no listener for this path, the
victim must run a CLI command in the affected scope, subdirectories and
non-regular entries are skipped, and a snapshot lock prevents concurrent
snapshots from multiplying work in one store. The defect does not establish
memory corruption, command execution, a privilege bypass, or confidentiality
loss. Those constraints support Medium severity and P2 priority.

I reviewed the exact source at
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, traced both CLI entry points,
and built that revision offline. I ran the included fixed-size 262,144-byte
probe and observed status return the complete file hash and snapshot persist a
262,144-byte raw object. I did not create a large or sparse file, measure peak
memory, try to exhaust any resource, or test a fixed revision. No fixing
commit, CVE, or public advisory was available for comparison.

Repository history places the same whole-file read in the initial Step 1 core
implementation, commit `5116c33d5b5bb08a6265c6eaa1d310f6947da1f5`
from 2026-07-03, and it remains in the confirmed revision from 2026-07-10.
There is no release tag that supports a broader published-version claim, so
the affected range should be expressed in source revisions until maintainers
map it to releases.

## Background

KCS is a folder-local knowledge archive. A scope's `.kcs` directory contains
its raw content-addressed objects, tree and commit objects, references, and
manifest. The data model deliberately manages only direct-child files; a
subdirectory is a separate potential scope rather than part of its parent's
tree. That makes the enumeration breadth easy to understand, but it does not
bound the size of any one selected file.

Two core commands need a view of the current files:

- `status` hashes current bytes and compares those hashes with the HEAD tree to
  classify files as new, modified, deleted, or unchanged.
- `snapshot` hashes the current bytes, stores raw objects, builds a tree, and
  creates or reuses a commit representing that state.

The relevant trust boundary appears whenever the person running KCS is not the
only person choosing the scope contents. Examples include a shared project
folder, a synchronized drop folder, an extracted bundle, or a checkout supplied
by another party. The contributor controls a regular file's bytes and logical
length; KCS, running as the victim OS user, decides how much of the victim's
memory, I/O bandwidth, and archive storage to spend on it.

The safe invariants are therefore stronger than “only direct children”:

1. hashing a file must use bounded working memory, independent of file size;
2. a routine command must enforce explicit per-file and aggregate work budgets;
3. an oversized status entry must be disclosed as unhashed rather than
   misclassified; and
4. an oversized snapshot must fail closed before advancing the tree, commit,
   refs, or manifest rather than silently omitting content.

The affected implementation satisfies none of the resource parts of those
invariants. It first materializes bytes and only then hashes or stores them.

## Vulnerability Details

### Both CLI commands reach the shared builder

The status dispatch opens the current repository and calls `Repository::status`:

```rust
// crates/kcs-cli/src/main.rs:435-450
Command::Status => {
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    let task_store = TaskStore::new(repo.kcs_dir());
    let status = repo.status()?;
    Ok(json!({
        "scope_path": repo.kcs_dir(),
        "files": status.files,
        "head_shallow": status.head_shallow,
        "tasks": task_store.all().map_err(pipeline_to_kcs)?,
        "quarantine": quarantine_status_records(&repo)?,
        "budget": budget_status_json(&repo)?,
    }))
}
```

If we follow `status` into `crates/kcs-core/src/scope.rs`, it validates the
repository and immediately builds the current tree with `store_raw=false`:

```rust
// crates/kcs-core/src/scope.rs:306-309
pub fn status(&self) -> Result<StatusReport> {
    self.validate()?;
    let current = self.build_working_tree(false)?.tree;
    let current_map = tree_map(&current);
```

The `false` flag sounds reassuring, but it controls only whether bytes are
persisted after reading. It does not select a streaming or metadata-only path.
The no-filter wrapper also supplies an empty exclusion set, so status reaches
every direct regular child other than `.kcs` regardless of the snapshot
preview's ignore decisions.

Manual snapshot dispatch first builds a classifier preview with
`include_raw_hashes=false`, derives only an exclusion set, and then calls the
filtered snapshot:

```rust
// crates/kcs-cli/src/main.rs:452-472
Command::Snapshot(args) => {
    let _action = args.action;
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    let preview = build_scan_preview(ScanPreviewRequest {
        scope_path: repo.root().display().to_string(),
        include_raw_hashes: false,
        require_network_approval: false,
    })
    .map_err(pipeline_to_kcs)?;
    let excluded = preview
        .candidates
        .iter()
        .filter(|candidate| candidate.ignored)
        .map(|candidate| candidate.input_path.clone())
        .collect::<BTreeSet<_>>();
    let outcome = repo.snapshot_filtered(args.message.as_deref(), None, &excluded)?;
```

The preview records each candidate's metadata size, but this dispatch never
compares that size with a core limit. `snapshot_filtered` eventually acquires
the store lock and calls the same builder with `store_raw=true`:

```rust
// crates/kcs-core/src/scope.rs:413-430
fn snapshot_with_type(
    &self,
    message: Option<&str>,
    fixed_now: Option<&str>,
    commit_type: CommitType,
    excluded_paths: &BTreeSet<String>,
    normalize_by_path: &BTreeMap<String, NormalizeRef>,
) -> Result<SnapshotOutcome> {
    self.validate()?;
    let _lock = StoreLock::acquire(&self.kcs_dir)?;
    maybe_hold_lock_for_tests();

    let working = self
        .build_working_tree_with_normalize(true, excluded_paths, normalize_by_path)?
        .tree;
    let tree_value =
        serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
    let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
```

At this point we have two independently reachable wrappers and one decisive
implementation.

### The builder allocates before it hashes or stores

The complete direct-child loop is short enough to expose the missed invariant.
It filters by entry kind, name encoding, and exclusion, but never by byte size:

```rust
// crates/kcs-core/src/scope.rs:261-299
for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
    let entry = entry.kcs_io(&self.root)?;
    if entry.file_name() == ".kcs" {
        continue;
    }
    let path = entry.path();
    let file_type = entry.file_type().kcs_io(&path)?;
    if file_type.is_dir() {
        continue;
    }
    if !file_type.is_file() {
        eprintln!("warning: skipping non-regular file: {}", path.display());
        continue;
    }
    let file_name = match entry.file_name().into_string() {
        Ok(name) => name,
        Err(_) => {
            eprintln!("warning: skipping non-UTF-8 file name: {}", path.display());
            continue;
        }
    };
    if excluded_paths.contains(&file_name) {
        continue;
    }
    let bytes = fs::read(&path).kcs_io(&path)?;
    let raw_hash = if store_raw {
        self.store.write_raw(&bytes)?
    } else {
        hash_bytes(&bytes)
    };
    let mut tree_entry = TreeEntry::raw_file(file_name.clone(), raw_hash)?;
    tree_entry.normalize = normalize_by_path.get(&file_name).cloned();
    tree_entry.validate()?;
    entries.push(tree_entry);
}
```

`fs::read` returns an owned vector containing the complete file. When we carry
that vector into the two branches, status hashes it in memory and snapshot
passes the same complete slice to `write_raw`. `store_raw=false` therefore
removes the archive write but not the allocation.

The raw store hashes the slice and sends it to the atomic whole-object
writer:

```rust
// crates/kcs-core/src/cas.rs:60-75
pub fn write_raw(&self, bytes: &[u8]) -> Result<String> {
    let hash = hash_bytes(bytes);
    self.write_object_bytes(ObjectKind::Raw, &hash, bytes)?;
    Ok(hash)
}

pub fn write_object_bytes(&self, kind: ObjectKind, hash: &str, bytes: &[u8]) -> Result<()> {
    let path = self.object_path(kind, hash)?;
    atomic_write(&path, bytes)
}
```

For a new raw hash, `atomic_write` writes the complete slice to a temporary
file and renames it into the CAS. A sparse input is consequently not preserved
as sparse by this API: the zeros returned for holes are ordinary bytes in the
buffer and are written like any other content. If the raw object already
exists, CAS deduplication avoids rewriting it, but KCS has already read and
hashed the complete working file, so the memory and input-I/O cost remains.

### The nearby maximum is too late and belongs to a different operation

KCS does have a documented default of 104,857,600 bytes for
`adapter.policy.max_input_bytes`. The name can look like a defense until we
follow its caller. It is loaded inside `run_index_pipeline` and checked only
before handing candidates to Markdownize processing:

```rust
// crates/kcs-cli/src/main.rs:9047-9061
let max_input_bytes = effective_max_input_bytes(repo);

for candidate in preview
    .candidates
    .iter()
    .filter(|candidate| !candidate.ignored && candidate.media_type != "inode/directory")
{
    if candidate.size_bytes > max_input_bytes {
        result.skipped_oversized_files += 1;
        // ... record an adapter-processing skip ...
        continue;
    }
```

Neither `Repository::status` nor `snapshot_with_type` calls this function.
The source comment also says an oversized file “stays archived but
unenriched,” confirming that this control was designed to protect an adapter,
not core archive construction. We should not reinterpret that setting as an
existing status/snapshot guarantee. A fix needs a separately named core policy
or an explicitly documented expansion of this policy's scope.

The resulting resource behavior is:

| Command | Complete input buffer | Hash work | Raw-store work | Existing byte ceiling |
| --- | ---: | ---: | ---: | ---: |
| `status` | One file at a time | All included bytes | None | None |
| `snapshot` | One file at a time | All included bytes | All bytes for each new raw hash | None |

Because the loop is sequential and retains only tree entries after each
iteration, the live input-buffer bound is `O(largest included file)`, not the
sum of all file sizes. Total bytes read and hashed are `O(sum of included file
sizes)`. Snapshot storage growth is also proportional to the sum of unique raw
contents written. An allocator may retain freed pages in process RSS, but the
source alone does not establish how much or for how long on a particular host.

## Exploitability Analysis

### Strongest practical route

The clearest threat model is a lower-trust contributor and a victim who uses a
shared or supplied scope. The contributor places an innocuously named regular
file directly under that folder, avoiding the snapshot ignore and secret-name
filters. The victim later runs `kcs status` during inspection or `kcs snapshot`
to archive the state.

With status, we reach `fs::read` before KCS knows the current file hash. The
process must hold the complete returned buffer while SHA-256 runs. With
snapshot, we reach the same allocation while the store lock is held, then keep
the buffer through hashing and any raw-object write. One hostile file controls
the largest single live buffer; several files can extend total read, hashing,
and disk time even though the loop is sequential.

A dense file is the most portable trigger. Its cost to the contributor is
roughly proportional to its bytes, but it makes the victim pay the cost again
in process memory and I/O on every status or snapshot attempt. This can still
matter in synchronized project folders, automated status checks, constrained
containers, or desktops where the contributor's storage budget differs from
the victim process's memory budget.

A sparse regular file offers stronger amplification when the delivery path
preserves holes. Its metadata logical length can be much larger than allocated
disk blocks. Reading a hole returns zeros, so `fs::read` grows the vector across
the logical length; snapshot then presents those zeros to the dense byte-slice
CAS writer. The contributor may spend little physical storage while the victim
spends memory, sequential read work, and potentially raw-store disk space close
to the logical size.

That sparse-file route is environment-dependent. Git does not normally
preserve sparse extents, and some archive, cloud, or synchronization tools
materialize holes before delivery. It is most credible on a local shared
filesystem or through an import mechanism that explicitly recreates sparse
files. The dense-file route does not have that dependency.

### Failure modes and reliability

The precise endpoint depends on the operating system, allocator, process
limits, free memory, filesystem quota, and input size. Plausible outcomes
include:

- the KCS process spends substantial time reading and hashing before producing
  status output;
- allocation pressure causes an allocation failure, abort, or OS termination;
- snapshot spends additional time writing a first-seen raw object;
- snapshot fails on an I/O or no-space error before it can create a complete
  new history point; or
- a smaller input succeeds but competes with other applications for memory and
  storage bandwidth.

We cannot claim one universal crash threshold. The source establishes that no
KCS-level threshold exists and that resource use scales with attacker-chosen
file size. The included PoC intentionally demonstrates only reachability with
a small file; it does not extrapolate a host-specific failure point.

### Countercontrols and dead ends

Several controls narrow the issue without closing it:

- Enumeration is non-recursive. Moving the file into a subdirectory removes it
  from this parent scope's builder.
- A direct symlink, directory, FIFO, device, or other non-regular entry is
  skipped at enumeration. The file must appear as a regular direct child.
- Snapshot uses its preview-derived exclusions. A correctly excluded file does
  not reach the snapshot builder. Status, however, calls the no-filter builder
  and does not receive that exclusion set.
- The store lock serializes snapshots against other store mutations, limiting
  same-store snapshot concurrency. It does not cap one snapshot, and status
  does not take that lock.
- CAS deduplication can avoid a second raw-object write for identical content.
  It cannot avoid reading and hashing the working file first.
- Removing or relocating the file lets the operator retry. No persistent
  compromise survives that cleanup, although a previously written raw object
  remains part of the archive or as an unreachable CAS object until lifecycle
  tooling removes it.

Trying to turn this into memory corruption or code execution is an unproductive
branch on the evidence available. The vulnerable object is a safe Rust vector,
and no out-of-bounds access or attacker-controlled pointer follows from the
allocation. Likewise, status does not expose file contents; it returns paths,
classifications, and hashes. The supported impact is availability and local
resource amplification.

These constraints also explain the Medium/P2 rating. In a single-user folder
where the operator authors every file, this is primarily self-inflicted
resource pressure. In a lower-trust shared or adopted scope, the file-size
boundary is real and a routine victim action reaches it, but the effect remains
limited to local processing and archive storage rather than crossing an OS
privilege boundary.

## Proof of Concept

The `poc/` directory contains a deliberately bounded reachability probe. It
creates a disposable KCS scope and one fixed 262,144-byte ASCII file. The size
is a literal constant and cannot be changed by a command-line argument or
environment variable. The probe sets the adapter-only input ceiling to 4,096
bytes for context, runs status, runs snapshot, and checks two observations:

1. status returns the SHA-256 hash of the complete 262,144-byte file; and
2. snapshot creates a raw object of exactly 262,144 bytes.

This is not a memory benchmark. It creates no sparse file, applies no memory
pressure, and makes no attempt to fail either command. The source walkthrough
above proves the allocation; the PoC proves that the bounded file reaches both
complete-file paths in the reviewed build.

Build the revision under test without fetching dependencies:

```sh
cargo build --locked --offline -p kcs-cli
export PATH="$(pwd)/target/debug:$PATH"
```

Then, from the report directory:

```sh
cd poc
make run
```

The confirmed revision produced:

```text
fixture_bytes=262144
configured_adapter_cap_bytes=4096
status_exit=0
status_full_hash=true
snapshot_exit=0
snapshot_raw_object=true
snapshot_raw_object_bytes=262144
result=WHOLE_FILE_STATUS_AND_SNAPSHOT_PATH_REACHED
```

The temporary HOME, XDG directories, scope, file, and raw objects are removed
automatically on exit. The probe uses only offline core commands and synthetic
bytes.

If maintainers choose a cap-based fix, both commands should explicitly reject
the fixture when the configured core cap is below 262,144 bytes, and the script
will report `OVERSIZE_REJECTED_BY_BOTH_COMMANDS`. A streaming-only fix may
legitimately preserve the representative output while removing the allocation
defect. In that design this black-box probe remains useful for semantic
reachability, but a counting-reader unit test must assert the actual buffer and
aggregate-work bounds. The PoC README calls out this distinction so the sample
does not mislabel safe streaming as vulnerable.

## Remediation

The fix should restore both a memory invariant and a work-budget invariant:

> No direct-child file may cause a buffer proportional to its logical size,
> and no status or snapshot invocation may read more than explicit per-file and
> aggregate byte budgets without an operator override.

Do not silently reuse the adapter-only setting without updating its name and
documented semantics. A clearer design is a core/archive policy containing at
least `max_file_bytes`, `max_scope_bytes`, and a small fixed streaming buffer.
Keep a finite safe default and allow an explicit local override for legitimate
large archives.

At the shared builder, open the file, inspect metadata from the opened handle,
check both budgets, and then use a reader that can consume at most
`allowed + 1` bytes. That final extra byte is important: metadata is only a
preflight optimization, while the bounded reader detects growth or replacement
during processing. A proposed call-site shape is:

```rust
// Illustrative replacement in crates/kcs-core/src/scope.rs
let remaining = policy
    .max_scope_bytes
    .checked_sub(total_bytes)
    .ok_or_else(|| KcsError::scope_input_oversized(&file_name))?;
let allowed = policy.max_file_bytes.min(remaining);

let (raw_hash, consumed) = if store_raw {
    // Stream to a same-filesystem temporary CAS object while incrementally
    // hashing. Read at most allowed + 1 bytes; fsync and rename only after the
    // size check and digest complete.
    self.store.write_raw_file_bounded(&path, allowed, 64 * 1024)?
} else {
    // Incremental SHA-256 with the same fixed buffer and allowed + 1 guard.
    hash_file_bounded(&path, allowed, 64 * 1024)?
};

total_bytes = total_bytes
    .checked_add(consumed)
    .ok_or_else(|| KcsError::scope_input_oversized(&file_name))?;
```

The hashing helper can enforce the important race-safe bound without retaining
the complete file:

```rust
use std::fs::File;
use std::io::Read;

fn hash_file_bounded(path: &Path, allowed: u64, buffer_size: usize)
    -> Result<(String, u64)>
{
    let file = File::open(path).kcs_io(path)?;
    if file.metadata().kcs_io(path)?.len() > allowed {
        return Err(KcsError::scope_input_oversized(path.display().to_string()));
    }

    let mut reader = file.take(allowed.saturating_add(1));
    let mut buffer = vec![0_u8; buffer_size.clamp(1, 64 * 1024)];
    let mut digest = Sha256::new();
    let mut consumed = 0_u64;

    loop {
        let count = reader.read(&mut buffer).kcs_io(path)?;
        if count == 0 {
            break;
        }
        consumed = consumed
            .checked_add(count as u64)
            .ok_or_else(|| KcsError::scope_input_oversized(path.display().to_string()))?;
        if consumed > allowed {
            return Err(KcsError::scope_input_oversized(path.display().to_string()));
        }
        digest.update(&buffer[..count]);
    }

    Ok((format!("sha256:{:x}", digest.finalize()), consumed))
}
```

`write_raw_file_bounded` should use the same loop while writing chunks to a
temporary object. It should never collect those chunks into a second vector.
After EOF and the limit check, it can derive the fanout path from the digest,
discard the temporary file if the object already exists, or atomically rename
it into place. Error paths must remove the temporary file.

Before snapshot starts writing raw objects, it should also preflight the
current candidate set and aggregate metadata sizes. That gives normal oversized
inputs an early, side-effect-free failure. The streaming `allowed + 1` check
remains mandatory because files can change after preflight. Snapshot must not
advance tree, commit, refs, or manifest if any included file exceeds policy.
Silently omitting it would make the snapshot claim a false view of the folder.

Status has a different presentation choice. It may return a structured partial
result containing the path, metadata size, and an `oversized` or `unhashed`
state, but it must not label the file unchanged or modified without a current
hash. A stable nonzero/partial exit and an actionable error code such as
`KCS-E-SCOPE-INPUT-OVERSIZED-001` lets automation distinguish policy rejection
from store corruption.

Regression coverage should use small limits and fixtures rather than stress
inputs:

- with a 64 KiB per-file cap, accept exactly 64 KiB and reject 64 KiB plus one;
- reject a metadata-sized sparse fixture above the cap before reading its
  contents or creating a raw object;
- inject a reader that reports a small initial size but emits `cap + 1` bytes,
  proving the bounded stream catches growth races;
- use several individually valid files whose sum exceeds the aggregate cap;
- assert status reports an explicit unhashed/oversized state and never a false
  unchanged classification;
- assert snapshot rejection leaves HEAD, the branch ref, manifest, tree, and
  commit set unchanged and cleans temporary CAS files;
- inject a counting reader/writer and assert the largest buffer is at most
  64 KiB even when the accepted logical file is larger;
- preserve existing exact-hash, no-op snapshot, exclusion, deduplication, and
  direct-child-only behavior for inputs within policy; and
- test an explicit, audited large-file override without weakening the default.

Finally, document that `adapter.policy.max_input_bytes` protects adapter
processing only. If maintainers intentionally broaden it into the core limit,
rename or relocate the setting and update status/snapshot output so users can
tell why archive processing stopped.

## Summary

The reviewed KCS revision turns each included direct-child file into a complete
in-memory vector before status can hash it or snapshot can archive it. The
`store_raw` flag separates hashing from persistence but does not change the
read, and the only nearby size gate runs later in adapter processing. We can
therefore carry a lower-trust file's logical size directly into victim process
memory, total read/hash work, and, for a first snapshot, raw-store disk usage.

The included small probe confirms both command paths without attempting
resource exhaustion. Practical impact is bounded to local availability and
requires a victim command in a scope whose contents another party can
influence, which is why the appropriate rating is Medium/P2 rather than High.

The durable fix is a shared, streaming working-tree reader plus explicit
per-file and aggregate core budgets. Variant analysis should examine other
whole-file reads separately, but this report's remediation target is precise:
`Repository::status` and all snapshot variants that call
`build_working_tree_with_normalize` must stop allocating attacker-sized
buffers and must define honest oversized-file semantics.
