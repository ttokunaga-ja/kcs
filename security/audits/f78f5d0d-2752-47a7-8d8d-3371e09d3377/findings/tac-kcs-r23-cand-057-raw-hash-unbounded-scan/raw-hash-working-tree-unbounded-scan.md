# Raw-hash working-tree resolution reads every direct child without bounds

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
contains an unbounded local resource-consumption issue in raw-object
resolution. When a user runs an `open`, `view`, or Evidence-pointer workflow
for a raw hash, the resolver scans the selected scope's direct children before
checking the immutable CAS store. For each regular file it visits, it allocates
the entire file with `fs::read()` and then hashes the resulting byte vector.

An attacker who can contribute files to a scope that an operator later adopts
or opens can place very large or sparse regular files there. If the requested
raw hash is absent or late in directory enumeration, the victim KCS process
performs `O(sum n_i)` disk and hash work and reaches `O(max n_i)` input
allocation for the largest visited file. The final attack-path decision rated
this as Low/P3 because the effect is local, per command, and recoverable, but
the bug is still reportable: lower-trust scope content can deterministically
consume the operator process's CPU, I/O, and memory.

I reviewed the vulnerable revision and the saved validation and attack-path
artifacts directly. I did not run a large-file or sparse-file stress test; the
included PoC uses only small synthetic files to demonstrate the unbounded
control-flow shape safely.

## Background

KCS is a local-first CLI. The important boundary here is not a network listener
but the relationship between a trusted operator process and files inside a
selected working scope. A shared, synced, or supplied scope can contain
lower-trust content while the KCS process still runs with the operator's OS
user privileges and resource limits.

Raw-object resolution is used when the CLI needs to turn a raw hash or an
Evidence Pointer into a local path. The `open` and `view` commands accept either
object URIs, short `sha256:` hashes, or pointer text:

```rust
// crates/kcs-cli/src/main.rs:2796-2825
fn run_open(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, false);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, false);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    // ...
}

fn run_view(args: UnsupportedArgs) -> Result<Value> {
    let raw = read_pointer_input(without_json(args.args))?;
    if let Some(object) = parse_object_uri(&raw)? {
        return resolve_object_uri(&object, true);
    }
    if raw.starts_with("sha256:") {
        return resolve_short_hash_command(&raw, true);
    }
    let pointer = parse_pointer_text(&raw)?;
    let resolved = resolve_pointer_for_cli(&pointer)?;
    // ...
}
```

The normal invariant we want is narrow: resolving one raw object should do work
proportional to that object, or to a bounded lookup budget. We should not let
unrelated direct-child files in the working tree control unbounded allocation
before the resolver has even checked whether the object already exists in CAS.

Evidence Pointer resolution reaches the same raw-object path after it has
validated the pointer identity and selected the scope target:

```rust
// crates/kcs-cli/src/main.rs:4861-4875
// Raw object resolution: working tree first (rename-tolerant), else CAS
// read-only expansion. Absent from both with no tombstone -> not_found.
match open_raw_object(
    &target,
    &pointer.raw_hash,
    pointer.path_at_commit.as_deref(),
)? {
    Some((path, temporary)) => Ok(PointerResolution {
        path: Some(path),
        text: Some(text),
        temporary,
        commit_shallow,
    }),
    None => Err(purge_not_found_error(&target, &pointer.raw_hash)),
}
```

This rename-tolerant working-tree preference is useful, but it creates the
resource boundary that matters for this finding. Once we accept scope files as
lookup candidates, we need to hash them without handing each file a complete
process-sized allocation.

## Vulnerability Details

The vulnerable ordering starts in `open_raw_object()`. It delegates to
`open_cas_byte_object()` with `scan_working_tree` set to `true` for raw objects:

```rust
// crates/kcs-cli/src/main.rs:4977-5007
fn open_raw_object(
    target: &ScopeTarget,
    raw_hash: &str,
    path_hint: Option<&str>,
) -> Result<Option<(PathBuf, bool)>> {
    open_cas_byte_object(target, "raw", true, raw_hash, path_hint)
}

fn open_cas_byte_object(
    target: &ScopeTarget,
    subdir: &str,
    scan_working_tree: bool,
    hash: &str,
    path_hint: Option<&str>,
) -> Result<Option<(PathBuf, bool)>> {
    if scan_working_tree {
        if let Some(path) = find_working_tree_raw(&target.repo_root, hash)? {
            return Ok(Some((path, false)));
        }
    }
    let object_path = cas_object_path(&target.kcs_dir, subdir, hash);
    if !object_path.is_file() {
        return Ok(None);
    }
    // ...
}
```

We first carry the caller's requested raw hash into the working-tree scan. The
CAS check only happens after that scan returns `None`, so an existing immutable
object does not protect the command from unrelated working-tree work.

The actual sink is compact, which is why the bug is easy to miss:

```rust
// crates/kcs-cli/src/main.rs:5165-5188
fn find_working_tree_raw(root: &Path, raw_hash: &str) -> Result<Option<PathBuf>> {
    for entry in fs::read_dir(root)
        .map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?
    {
        let entry =
            entry.map_err(|err| KcsError::io(err.to_string(), root.display().to_string()))?;
        if entry.file_name() == ".kcs" {
            continue;
        }
        if !entry
            .file_type()
            .map(|kind| kind.is_file())
            .unwrap_or(false)
        {
            continue;
        }
        let path = entry.path();
        let bytes = fs::read(&path)
            .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
        if hash_bytes(&bytes) == raw_hash {
            return Ok(Some(path));
        }
    }
    Ok(None)
}
```

The existing controls are correctness controls, not resource controls. We skip
`.kcs`, skip non-regular entries, and compare a cryptographic hash. From there,
however, each remaining direct child is read wholesale. If a lower-trust
contributor supplies files with sizes `n_1, n_2, ... n_m`, then an absent hash
or a match in the last enumerated file makes the victim process read and hash
the sum of those sizes. At any one loop iteration, the retained input allocation
is approximately the largest visited file, because the `Vec<u8>` returned by
`fs::read()` is dropped before the next iteration.

That gives us the concrete bad state:

- attacker-controlled regular-file content becomes process memory through
  `fs::read()`;
- no metadata precheck rejects an oversized file before allocation;
- no streaming reader limits live memory;
- no aggregate byte or file-count budget limits total work;
- CAS is checked only after the working-tree scan finishes.

The final validation artifact also notes a safe control observation using only
65,536-byte and 32,768-byte synthetic files. That was enough to confirm the
resource relation without attempting a disruptive allocation or sparse-file
stress test.

## Exploitability Analysis

The strongest route is a local denial of service against an operator or
automation process that consumes an adopted/shared scope. We do not need shell
access to the victim account or private `.kcs` writes. We need file-content
control in the selected scope and a raw-object resolution whose requested hash
is absent or reached late.

The attacker's useful levers are simple:

- number of direct-child regular files visited by `fs::read_dir()`;
- size and sparseness of each regular file;
- whether the supplied raw hash is absent or likely to match late;
- the host's memory, disk, and CPU limits.

If we choose an absent hash, we avoid relying on directory order for correctness:
the scan has to visit every eligible file before it can return `None`. Directory
order still affects exactly when a visible slowdown starts and how soon a
particular large file is encountered, but absence gives the deterministic full
scan. If we instead target a late match, we can make the command return a valid
working-tree path after doing nearly all of the same work; that is useful if an
operator expects success and treats failures as suspicious, but it depends more
on enumeration order.

Sparse files are the most interesting resource multiplier. A sparse direct
child can advertise a very large logical length without requiring the same
amount of physical disk space from the contributor. `fs::read()` still presents
the vulnerable process with the logical byte stream, so the victim pays memory
and CPU cost even when the storage footprint is smaller. I did not execute that
stress path for this report because it can be disruptive on the host running the
scan, but it is the route I would expect to expose the sharpest difference
between attacker cost and victim cost.

There are also constraints that keep this from a higher-severity finding. KCS
does not expose a public inbound service here; the operator or an integration
must run an `open`, `view`, or Evidence workflow in the hostile scope. The
effect is confined to one local KCS process and is recoverable by removing the
hostile files or avoiding the supplied pointer. The primitive does not provide
code execution, credential disclosure, network egress, or durable cross-scope
corruption by itself.

The important dead end is assuming that the CAS fallback bounds work. It does
not. We can carry a hash that exists in immutable CAS, but the code still scans
the working tree first whenever `scan_working_tree` is true. That means a
performance fix should address both absent hashes and CAS hits; merely improving
the missing-object path would leave the pre-CAS scan exposed.

## Proof of Concept

The included PoC is a safe regression probe, not a destructive stress test. It
creates a disposable synthetic scope, writes small direct-child files, then runs
a Python model of the vulnerable resolver loop. The model intentionally mirrors
the relevant source shape: skip `.kcs`, skip non-files, read each regular file
as a complete byte string, hash it, and continue until an absent hash has
forced the full scan. It also shows the intended fixed shape by hashing the
same files through a small streaming buffer.

Run it from the report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] synthetic files created: alpha.bin=32768, bravo.bin=65536, notes.txt=11
[+] vulnerable-style absent-hash scan visited 3 regular files
[+] vulnerable-style total bytes read: 98315
[+] vulnerable-style largest single allocation: 65536
[+] streaming regression probe hashed the same files with a 4096-byte chunk cap
[+] no live KCS command, credentials, network, or large allocation was used
```

This demonstrates the exact resource relation we care about while keeping the
allocation sizes harmless. A project-level regression test should exercise the
real `find_working_tree_raw()` path with a controlled fixture and assert that an
existing CAS hit or absent raw hash cannot cause unbounded unrelated file reads.

## Remediation

The invariant to restore is: raw-object lookup may compare working-tree file
content to a requested hash, but it must do so under explicit per-file and
aggregate work limits, and it should not allocate a whole candidate file at
once. A good fix has two layers.

First, stream candidate files through the hash function and reject or skip
oversized candidates based on metadata before reading:

```rust
// sketch only: use the project's actual error and SHA-256 helpers
const MAX_WORKING_TREE_RAW_FILE_BYTES: u64 = 64 * 1024 * 1024;
const MAX_WORKING_TREE_RAW_SCAN_BYTES: u64 = 256 * 1024 * 1024;

fn hash_regular_file_bounded(path: &Path, remaining: &mut u64) -> Result<Option<String>> {
    let metadata = fs::metadata(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    if metadata.len() > MAX_WORKING_TREE_RAW_FILE_BYTES {
        return Ok(None);
    }
    if metadata.len() > *remaining {
        return Ok(None);
    }
    *remaining -= metadata.len();

    let file = fs::File::open(path)
        .map_err(|err| KcsError::io(err.to_string(), path.display().to_string()))?;
    let mut reader = std::io::BufReader::new(file);
    let digest = hash_reader(&mut reader)?;
    Ok(Some(digest))
}
```

Then make `find_working_tree_raw()` carry a budget through enumeration and
compare the streaming digest instead of `hash_bytes(&bytes)`. Whether oversized
files are skipped or reported as a typed error is a product decision, but the
behavior should be deterministic and documented so callers do not confuse a
resource guard with object absence.

Second, avoid unnecessary scans. If a raw object already exists in CAS and the
caller does not need rename-tolerant working-tree recovery, prefer the indexed
or immutable lookup. If rename tolerance remains mandatory, consider maintaining
an indexed raw-hash map for direct children during normal indexing so that
`open` and `view` do not rediscover hashes by rereading arbitrary files.

Regression tests should cover at least these cases:

- an absent raw hash in a scope with multiple direct-child regular files;
- an existing CAS raw object while unrelated working-tree files are present;
- a direct-child file larger than the per-file limit;
- many small files whose aggregate size exceeds the scan budget;
- `.kcs`, directories, symlinks, and special files remaining excluded.

## Summary

The bug is a narrow but real resource-boundary failure. We start from a local
read-oriented command, carry a caller-supplied raw hash into working-tree raw
resolution, and then let lower-trust direct-child files force whole-file
allocation and hashing before CAS is consulted. The impact is local availability
loss for one KCS process and selected scope, which matches the final Low/P3
attack-path rating, but the defensive fix should be straightforward: stream the
hashing, budget the work, and avoid scanning unrelated files when an indexed or
CAS lookup can answer the request.

Variant analysis should look for other resolver, preview, and evidence paths
that read candidate files before applying the project's existing size and work
budgets. The pattern to search for is not only `fs::read()`, but any path where
attacker-controlled scope content is materialized in full before the command
has established that the specific object is needed.
