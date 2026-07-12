# Snapshot regular-file TOCTOU can archive an outside-scope symlink target

## Executive Summary

KCS snapshots direct children of the current scope and intentionally skips
stable symlinks and other non-regular files. At revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, that regular-file decision is
made from a `DirEntry` file-type observation, but the later read is a separate
pathname operation. If a lower-trust local writer can rename a checked direct
child after the type observation and before `fs::read(&path)`, KCS can follow a
replacement symlink to a file outside the scope and archive those bytes under
the benign in-scope name.

I reviewed the vulnerable revision directly and executed the included
local/offline PoC against a synthetic temporary directory; I did not run a live
timing stress harness against the KCS CLI, so the exact race win rate remains
filesystem- and scheduler-dependent. No public advisory, CVE, fixed release, or
introduction date was identified during this write-up. The final policy
decision for this candidate is reportable, with low severity and P3 priority:
the primitive crosses the scope boundary, but it requires local concurrent
write authority and the owner-only `.kcs` store normally prevents the lower
trust writer from reading archived bytes afterward.

## Background

The relevant KCS scope model is intentionally simple: the current folder is the
scope, direct child regular files are candidates for status and snapshot, and
subdirectories plus non-regular entries are outside this Step 1 surface.
Snapshot stores the selected file bytes in raw content-addressed storage (CAS)
and then builds a tree object that names each archived direct child.

The manual snapshot command first opens the current repository and computes a
name-only exclusion set for files that should not be snapshotted. Once that set
is ready, it delegates to `Repository::snapshot_filtered()`:

```rust
// crates/kcs-cli/src/main.rs, Command::Snapshot
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

The store lock acquired later protects `.kcs` object and reference updates from
cooperating KCS writers. It does not lock the working directory or prevent a
separate process from renaming a direct child while snapshot enumeration is in
progress. That distinction is the important boundary for this bug: the attacker
does not need to write into `.kcs`; they only need rename authority over one
ordinary child in a scope the operator snapshots.

## Vulnerability Details

We first reach the shared working-tree builder. It enumerates the repository
root, skips `.kcs`, observes the file type attached to the directory entry, and
rejects entries that are not regular files:

```rust
// crates/kcs-core/src/scope.rs, Repository::build_working_tree_with_normalize()
for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
    let entry = entry.kcs_io(&self.root)?;
    if entry.file_name() == ".kcs" {
        continue;
    }
    let path = entry.path();
    let file_type = entry.file_type().kcs_io(&path)?;
    // Subfolders are out of scope (03 §3: direct children only) and are
    // skipped silently. Symlinks / other non-regular files are skipped
    // with a warning so the omission is visible (WS1c S5, 10 §4).
    if file_type.is_dir() {
        continue;
    }
    if !file_type.is_file() {
        eprintln!("warning: skipping non-regular file: {}", path.display());
        continue;
    }
```

That check is a real product control for stable symlinks: if the entry is
already a symlink when KCS observes it, the entry is not treated as a file.
The problem is that we do not carry an open file descriptor, inode identity, or
no-follow open from this point to the actual byte read. After some additional
name processing and exclusion checks, KCS reuses the mutable pathname:

```rust
// crates/kcs-core/src/scope.rs, Repository::build_working_tree_with_normalize()
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
```

If we carry the attacker-controlled directory name across that gap, the bad
interleaving is straightforward:

1. The attacker presents `report.txt` as an ordinary direct-child regular file.
2. KCS observes `file_type.is_file()` and passes the stable-symlink control.
3. Before `fs::read(&path)`, the attacker atomically replaces `report.txt` with
   a symlink to a victim-readable file outside the scope.
4. `fs::read(&path)` opens the pathname again and follows the replacement
   symlink.
5. Snapshot stores the followed bytes under the original direct-child name.

The snapshot path holds the `.kcs` store lock before it builds the working tree:

```rust
// crates/kcs-core/src/scope.rs, Repository::snapshot_with_type()
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

We should read that lock narrowly. It serializes KCS store updates, but an
untrusted local contributor, sync client, editor, or build process with write
authority in the working root can still rename `report.txt` while this code is
between the type observation and the later read.

Once the followed bytes reach CAS, the store preserves exactly the supplied
buffer under its content hash:

```rust
// crates/kcs-core/src/cas.rs, ObjectStore
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

For `kcs status`, the same builder is reached with `store_raw=false`, so we get
the same out-of-scope read and hash decision without raw CAS persistence. For
`kcs snapshot`, `store_raw=true` turns the race from a transient status error
into authoritative archive state: outside bytes are bound to the tree as though
they were the direct child that passed the original check.

## Exploitability Analysis

The strongest standalone route is local scope-boundary confusion. The attacker
needs write and rename authority in the selected root, while KCS runs with the
operator's broader read authority. We can make the candidate entry look benign
at the start of enumeration, then switch it to a symlink target such as
`../outside-victim.txt` after the type check. If the operator snapshots the
scope and we win the timing window, the CAS object contains the target's bytes
even though the tree path still says `report.txt`.

That primitive is useful for archive integrity and boundary bypass: the
snapshot history now records content that was never an in-scope regular file at
the time of use. It can also become a confidentiality issue when some later
trusted reader, viewer, export, backup, or automation path consumes CAS/tree
state and exposes it under the benign name. The important limit is that this
candidate does not prove a separate lower-trust read path out of the owner-only
`.kcs` directory. Without that second step, the attacker may cause the operator
to archive out-of-scope data, but they do not automatically get to read it.

Reliability depends on scheduling. Losing races are bounded in several ways:
KCS might observe the symlink up front and skip it, read the benign file before
the replacement, or fail the read if the name is temporarily absent. The window
is still real because the check and use are separate filesystem operations with
additional Rust work between them. A practical attacker can improve odds by
looping atomic renames, using a large number of candidate files, or targeting
operators and automation that repeatedly run `status` or `snapshot`.

There are also weaker or noisier variants. Racing `status` demonstrates the
same pathname-following bug but only hashes the followed bytes. Racing a
replacement to a blocking or special target could create an availability
problem if the final open follows that target, but stable non-regular entries
are skipped and the data-archival route is the clearer security boundary here.
Hard-link behavior is a separate policy question: if KCS wants the scope to
mean "directory entries whose bytes are readable through this scope", hard
links may be acceptable; if it wants stronger origin guarantees, descriptor
identity and containment tests need to account for them too.

## Proof of Concept

The included PoC is a deterministic local model of the vulnerable interleaving,
not a live KCS race harness. It creates a temporary synthetic scope, observes a
direct child as a regular file using a no-follow directory-entry check, swaps
that name to a relative symlink outside the scope, and then performs the same
kind of pathname read that `fs::read(&path)` performs. This keeps the PoC safe
and repeatable while proving the missing binding between the checked object and
the read object.

Run it from the report directory:

```sh
cd poc
make run
```

Representative output:

```text
[+] built temporary synthetic scope
[+] observed report.txt as a regular direct child
[+] replaced report.txt with symlink target ../outside-victim.txt
[+] fs::read-style pathname reopen followed the replacement symlink
[+] archived tree name: report.txt
[+] followed bytes sha256: sha256:697a0756c45c9bd183a4f3506765a0892b9746c3bd44b53c7fffcf60a9f5a9d3
RESULT: OUTSIDE_SCOPE_BYTES_ARCHIVED_UNDER_BENIGN_NAME
```

The PoC only creates files inside its temporary directory and removes them when
the process exits. It uses no credentials, network access, third-party target,
or repository state.

## Remediation

The invariant to restore is simple: the object whose type is accepted must be
the same object whose bytes are hashed and, for snapshots, written to raw CAS.
Checking one pathname state and later opening the name again is not enough.

On Unix-like platforms, the minimal robust shape is to enumerate by name under
an opened directory descriptor, open each candidate with no-follow semantics,
validate the opened descriptor with `fstat`, and read from that descriptor:

```rust
// Sketch only: use a platform wrapper such as rustix/cap-std for real code.
let dir = open_scope_dir(&self.root)?;
for name in direct_child_names(&dir)? {
    if name == ".kcs" || excluded_paths.contains(&name) {
        continue;
    }
    let file = openat_nofollow_readonly(&dir, &name)?;
    let meta = file.metadata()?;
    if !meta.is_file() {
        warn_skip_non_regular(&name);
        continue;
    }
    let bytes = read_all_from_file(&file)?;
    let raw_hash = if store_raw {
        self.store.write_raw(&bytes)?
    } else {
        hash_bytes(&bytes)
    };
    entries.push(TreeEntry::raw_file(name, raw_hash)?);
}
```

If KCS needs portable behavior on platforms without `openat` and
`O_NOFOLLOW`, the fallback should be conservative: fail closed for symlinkable
or concurrently changed paths rather than silently relying on a pre-open
metadata check. A library that models filesystem capabilities can keep this
logic from spreading across scan, status, snapshot, and later adapter paths.

Regression coverage should include:

- a stable symlink direct child, which must remain skipped;
- a hook or test double that replaces a checked regular child with an outside
  symlink between metadata observation and read, which must not archive or hash
  the outside bytes;
- `status` and `snapshot` variants, because both call the same builder with
  different persistence behavior;
- a concurrent rename loop stress test that verifies snapshots never contain
  the outside marker even when timing is adversarial.

## Summary

The root cause is a classic pathname TOCTOU in the KCS working-tree builder:
we approve one filesystem object as a regular direct child, but later read a
mutable pathname that may now identify a symlink target outside the scope.
Snapshot then writes the followed bytes into raw CAS and binds them to the
benign tree name. The included PoC demonstrates the interleaving safely with a
temporary synthetic scope, while the source trace proves why the same shape is
reachable through ordinary status and snapshot code at the reviewed revision.

Future variant analysis should look for other KCS paths that perform
metadata-based authorization and then reopen by path, especially scan,
normalization, preview, and online-processing stages. The durable fix is to
make the descriptor, not the pathname string, carry the security decision from
type check through read, hash, and archive.
