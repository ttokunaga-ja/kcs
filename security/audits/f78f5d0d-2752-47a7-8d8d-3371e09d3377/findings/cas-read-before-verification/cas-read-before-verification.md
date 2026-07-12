# Hash-consistent CAS objects are fully allocated before verification

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` reads a selected
content-addressed-storage (CAS) object into a single `Vec<u8>` before it
verifies the object's digest, checks its type, parses its structure, or applies
any size ceiling. A lower-trust contributor who supplies a copied or preseeded
`.kcs` store can therefore choose the size of a hash-consistent object that the
victim process allocates and hashes. The most direct trigger is the ostensibly
metadata-only `inspect` command; supplied commit and tree references expose the
same primitive to additional repository operations.

The result is local, linear memory, I/O, and CPU consumption. A sufficiently
large object can disrupt or terminate the invoking KCS process, but exploitation
requires adoption of attacker-influenced on-disk state and selection of the
object or a reference that reaches it. Fresh stores are owner-only, the attacker
does not gain code execution or additional filesystem authority, and resource
use is proportional to bytes already present in the supplied store. Those
constraints support a **Low** final severity and **P3** priority.

I reviewed the affected revision directly and executed the included offline,
bounded PoC with a 65,536-byte object. It confirmed that both
`ObjectStore::read_by_hash()` and metadata-only `Repository::inspect()` retain
the complete object size, while malformed hash syntax is rejected before
lookup. I deliberately did not attempt an out-of-memory condition or measure
peak RSS. No fixed revision was available for comparison, and I did not attempt
to determine the exact introducing revision; the affected-version claim is
therefore limited to the revision named above.

## Background

KCS stores repository state under a `.kcs` directory. CAS objects are divided
into raw, tree, and commit namespaces, and their names are SHA-256 digests. A
new store is created with an owner-only `.kcs` directory, which is an important
defense against another local user modifying a live private store:

```rust
// crates/kcs-core/src/scope.rs:141-158, Repository::init
for dir in [
    kcs_dir.join("objects/raw"),
    kcs_dir.join("objects/trees"),
    kcs_dir.join("objects/commits"),
    kcs_dir.join("refs/heads"),
    kcs_dir.join("refs/tags"),
    kcs_dir.join("logs"),
] {
    fs::create_dir_all(&dir).kcs_io(&dir)?;
}

restrict_dir_to_owner(&kcs_dir)?;
```

That permission boundary does not authenticate a store before adoption. When
an operator receives or copies an existing scope, the supplied `.kcs` contents
become input to the KCS process running with the operator's identity. This is
the relevant boundary for this issue: we do not assume that an attacker can
write into an already-private live store.

The read interface returns an owned object whose payload is always a
`Vec<u8>`:

```rust
// crates/kcs-core/src/cas.rs:40-45
#[derive(Debug, Clone)]
pub struct StoredObject {
    pub kind: ObjectKind,
    pub hash: String,
    pub bytes: Vec<u8>,
}
```

This shape is convenient for tree and commit deserialization, but it makes
allocation policy part of the security boundary. Once we carry a supplied
object through this interface, every caller receives all bytes at once even if
it needs only metadata.

## Vulnerability Details

### The digest check occurs after an unbounded `fs::read`

The central path is `ObjectStore::read_by_hash()`. We first reach a useful
control: `is_hash()` rejects malformed names, and `object_path()` derives a
fixed fan-out path. The function then checks each object-kind directory. When a
path exists, however, it calls `fs::read()` without consulting metadata or a
per-kind limit:

```rust
// crates/kcs-core/src/cas.rs:78-100, ObjectStore::read_by_hash
pub fn read_by_hash(&self, hash: &str) -> Result<StoredObject> {
    if !is_hash(hash) {
        return Err(KcsError::invalid_usage("invalid hash"));
    }

    for kind in [ObjectKind::Tree, ObjectKind::Commit, ObjectKind::Raw] {
        let path = self.object_path(kind, hash)?;
        if path.exists() {
            let bytes = fs::read(&path).kcs_io(&path)?;
            let actual = hash_bytes(&bytes);
            if actual != hash {
                return Err(KcsError::new(
                    "KCS-E-STORE-CORRUPT-001",
                    "CAS object hash mismatch",
                    serde_json::json!({ "path": path, "expected": hash, "actual": actual }),
                    crate::ExitCode::PermanentFailure,
                ));
            }
            return Ok(StoredObject {
                kind,
                hash: hash.to_owned(),
                bytes,
            });
        }
    }
```

For an object of size `N`, `fs::read()` allocates and fills an `N`-byte vector.
`hash_bytes()` then traverses the same vector. Digest equality proves that the
bytes match the supplied name, but it cannot undo the allocation and I/O that
have already occurred. Requiring a valid digest also does not bound `N`: a
contributor who provides the bytes can calculate the corresponding SHA-256
name.

The ordering is the violated invariant. An integrity check answers whether the
bytes are the expected bytes; it is not a resource limit. KCS needs to decide
whether an object is acceptably sized before allocating storage proportional to
it, and it should verify the digest through a bounded streaming reader.

### A metadata-only command retains the entire raw object

The clearest consumer is `Repository::inspect()`. The CLI accepts a hash and
forwards it to this method. For a raw object, the command ultimately returns
only the digest and length:

```rust
// crates/kcs-core/src/scope.rs:623-637, Repository::inspect
pub fn inspect(&self, hash: &str) -> Result<InspectedObject> {
    self.validate()?;
    let object = self.store.read_by_hash(hash)?;
    match object.kind {
        ObjectKind::Tree => serde_json::from_slice(&object.bytes)
            .map(InspectedObject::Tree)
            .map_err(|err| KcsError::schema(err.to_string())),
        ObjectKind::Commit => serde_json::from_slice(&object.bytes)
            .map(InspectedObject::Commit)
            .map_err(|err| KcsError::schema(err.to_string())),
        ObjectKind::Raw => Ok(InspectedObject::Raw {
            raw_hash: object.hash,
            size_bytes: object.bytes.len() as u64,
        }),
    }
}
```

If we follow the raw branch, `object.bytes.len()` is the sole payload-derived
value. Nevertheless, the full vector remains live until the match completes.
This makes `inspect` a strong diagnostic trigger because it demonstrates that
the allocation is not an unavoidable consequence of returning file content.

The CLI path confirms that the result is metadata only:

```rust
// crates/kcs-cli/src/main.rs:513-530
Command::Inspect(args) => {
    let repo = Repository::open_current()?;
    validate_repo_tool_lock(&repo)?;
    match repo.inspect(&args.hash)? {
        // tree and commit branches omitted
        InspectedObject::Raw {
            raw_hash,
            size_bytes,
        } => Ok(json!({
            "object_type": "raw",
            "raw_hash": raw_hash,
            "size_bytes": size_bytes,
        })),
    }
}
```

### Commit and tree consumers share the same primitive

The issue is not confined to an explicit raw-object inspection. Commit and tree
readers call the same generic method before checking the kind or deserializing
JSON:

```rust
// crates/kcs-core/src/scope.rs:742-755
pub fn read_commit(&self, hash: &str) -> Result<CommitObject> {
    let object = self.store.read_by_hash(hash)?;
    if object.kind != ObjectKind::Commit {
        return Err(KcsError::schema("hash does not identify a commit"));
    }
    serde_json::from_slice(&object.bytes).map_err(|err| KcsError::schema(err.to_string()))
}

pub fn read_tree(&self, hash: &str) -> Result<TreeObject> {
    let object = self.store.read_by_hash(hash)?;
    if object.kind != ObjectKind::Tree {
        return Err(KcsError::schema("hash does not identify a tree"));
    }
    serde_json::from_slice(&object.bytes).map_err(|err| KcsError::schema(err.to_string()))
}
```

A supplied `HEAD`, branch, or tag can therefore select a large, hash-consistent
commit or tree object during ordinary repository operations. For structured
objects, JSON parsing may add further allocations after the first full read.
That is useful variant context, but the vulnerability is already complete at
the initial `fs::read()`.

## Exploitability Analysis

The strongest realistic route is a prepared store rather than mutation of a
live private store. A lower-trust contributor creates a `.kcs` object whose
content length approaches or exceeds the memory headroom of the intended
machine, calculates its valid SHA-256 name, and places it in the corresponding
fan-out directory. The contributor either gives the operator the hash for an
`inspect` command or binds the object into supplied refs so a normal commit/tree
consumer selects it. When the operator adopts the store and invokes the
relevant command, we reach `fs::read()` under the operator's KCS process.

The attacker controls the object bytes, size, digest-derived filename, object
namespace, and supplied refs. That is enough to control the amount of memory
requested by a single read. It does not provide a small-input amplification:
shipping an `N`-byte ordinary file generally costs the attacker and victim
roughly `O(N)` storage and transfer. A sparse file could make packaging cheaper
on some local filesystems, but sparse-hole preservation across an archive or
copy workflow is environment-dependent and was not required or tested.

There are three meaningful routes:

1. **Direct raw inspection.** The contributor supplies the exact hash and asks
   the operator to inspect it. This is deterministic and needs no valid DAG,
   but it relies on a socially or operationally plausible reason for the
   operator to select that hash.
2. **Ref-driven commit or tree consumption.** A prepared `HEAD`, branch, or tag
   can make routine commands select the oversized object. This broadens trigger
   reach, but the object must still be hash-consistent and sufficiently
   well-formed for execution to continue beyond the first allocation. If the
   goal is only resource exhaustion, later type or JSON rejection does not
   protect the first read.
3. **Repeated selection.** Automation that repeatedly opens the poisoned ref
   can incur the cost on every invocation. The vector is not retained across
   completed processes, so persistence comes from the on-disk object and the
   surrounding job retry policy rather than an in-process leak.

Several constraints keep the final rating low. The actor needs control over a
store before the victim adopts it; fresh stores are owner-only; the effect is
local to commands that select the object; and recovery consists of stopping the
process and removing or rejecting the supplied store. The demonstrated
primitive does not cross a confidentiality or privilege boundary. It can still
cause substantial availability impact on a memory-constrained workstation or
automated job, especially when the input approaches system memory, but I did
not stress-test those thresholds and do not claim a particular peak-RSS ratio.

Digest verification is an informative dead end as a mitigation. It blocks
false-name substitution, yet a contributor choosing both the object and its
name can satisfy the digest exactly. Type checks and JSON schema validation are
also too late because they run only after `read_by_hash()` returns the full
vector. The owner-only mode is valuable for live-store integrity but cannot
establish the provenance of a copied store.

## Proof of Concept

The `poc/` directory contains a bounded Rust harness and a safety-focused
runner. The harness uses the affected `kcs-core` APIs to create a small,
hash-consistent raw object in a temporary scope, closes and reopens the
repository, calls `read_by_hash()`, and then calls metadata-only `inspect()`.
It reports whether each returned size equals the selected input size. A
malformed short hash is included as a negative control.

The runner fixes the target revision, refuses a modified checkout, forces Cargo
offline, confines build and scope state to a temporary directory, removes that
directory on exit, and rejects `OBJECT_BYTES` values above 1,048,576. This is a
diagnostic demonstration, not an exhaustion tool.

From this report directory, set `KCS_SOURCE` to a path to the target checkout
and run:

```sh
cd poc
KCS_SOURCE=../../path-to-kcs-checkout
sh ./run.sh "$KCS_SOURCE"
```

The target checkout must be clean and checked out at
`0e19f3c6489da458e93a982a333c308d92d0a0ae`. Required Rust dependencies must
already exist in Cargo's local cache because the runner does not use the
network. The default run uses only 65,536 bytes. A different bounded value can
be selected up to the hard ceiling:

```sh
OBJECT_BYTES=131072 sh ./run.sh "$KCS_SOURCE"
```

Representative output from the default run is:

```json
{
  "bounded_object_bytes": 65536,
  "full_vec_retained_by_read_by_hash": true,
  "hash_consistent": true,
  "inspect_reported_size_bytes": 65536,
  "malformed_hash_rejected_before_lookup": true,
  "network_used": false,
  "repository_reopened": true,
  "stored_object_vec_bytes": 65536
}
```

We can read this result narrowly but decisively. The valid object reached the
real CAS read path, `StoredObject.bytes` retained all 65,536 bytes, and the raw
inspect path reported the same size after another full-object read. The
malformed hash control failed before lookup, showing that the PoC did not bypass
the existing syntax check. Cleanup is automatic, and the harness never writes
to the target checkout.

## Remediation

The invariant to restore is: **untrusted CAS metadata must not cause allocation
above an explicit per-kind ceiling, and integrity verification must not require
retaining the whole object**. A minimal risk-reduction patch can open the file,
apply a conservative size limit before and during the read, and only then return
an owned vector. The second check matters because metadata and contents can
change between operations on platforms where the store is concurrently
mutable.

One possible shape is:

```rust
use std::io::{Read, Write};

fn max_object_bytes(kind: ObjectKind) -> u64 {
    match kind {
        ObjectKind::Raw => 64 * 1024 * 1024,
        ObjectKind::Tree | ObjectKind::Commit => 8 * 1024 * 1024,
    }
}

fn read_bounded(path: &Path, kind: ObjectKind) -> Result<Vec<u8>> {
    let limit = max_object_bytes(kind);
    let file = File::open(path).kcs_io(path)?;
    if file.metadata().kcs_io(path)?.len() > limit {
        return Err(KcsError::invalid_usage("CAS object exceeds size limit"));
    }

    let mut bytes = Vec::new();
    file.take(limit + 1).read_to_end(&mut bytes).kcs_io(path)?;
    if bytes.len() as u64 > limit {
        return Err(KcsError::invalid_usage("CAS object exceeds size limit"));
    }
    Ok(bytes)
}
```

The concrete limits should come from the data model and expected workload, not
from the illustrative values above. Structured objects also need cardinality
limits for tree entries and commit parents so a small-enough JSON file cannot
cause disproportionate downstream allocation.

For the stronger design, KCS should expose separate operations:

- a streaming verifier that hashes through a fixed-size buffer and enforces a
  byte limit;
- a bounded materializer for callers that genuinely need payload bytes; and
- a raw metadata inspector that verifies and counts bytes without retaining
  the complete payload.

Regression coverage should exercise the real boundary. Tests should assert
that an object one byte above each kind's limit is rejected before a large
allocation, an object exactly at the limit verifies successfully, a file that
grows during reading cannot exceed the cap, an incorrect digest still produces
the corruption error, and raw `inspect` does not retain the object body. Commit
and tree tests should cover both direct hashes and supplied refs, including
cardinality ceilings after streaming verification.

## Summary

KCS correctly validates hash syntax and digest equality, but it performs the
digest check only after `fs::read()` has allocated the complete CAS object. We
followed that value into raw `inspect`, which needs only the byte count, and
into the shared commit/tree readers. The included bounded PoC confirmed the
full-vector relationship through the real target APIs without attempting
resource exhaustion.

The practical risk is a local availability failure when an operator adopts a
lower-trust copied or preseeded store and selects a prepared object or ref.
Owner-only permissions and the linear input cost constrain exploitability, but
they do not bound resources at the adoption boundary. A streaming, capped CAS
reader plus per-kind byte and cardinality policy would close this primitive.
Future variant analysis should audit other on-disk readers for the same
pattern: integrity, schema, or type validation that occurs only after an
unbounded whole-file allocation.
