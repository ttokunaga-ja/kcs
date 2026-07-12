# KCS CAS write accepts a pre-existing corrupt destination as success

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
uses a content-addressed store for raw file bytes, tree objects, and commit
objects. The vulnerable write path computes the expected hash and pathname,
but `atomic_write()` treats any pre-existing destination as success without
checking that the destination is a regular file containing the expected bytes.

The practical attack is a persisted-state poisoning problem at an adopted or
shared `.kcs` store boundary. If a lower-trust contributor pre-seeds the exact
CAS fanout path for content the operator later snapshots, `write_raw()` reports
success and the snapshot can publish tree, commit, and refs that name the
expected hash while the durable raw slot still contains corrupt data. Later
reads detect the mismatch, so this does not silently return attacker bytes, but
the archive entry remains unreadable and later legitimate writes keep accepting
the occupied corrupt slot.

I reviewed the vulnerable revision and the saved validation and attack-path
records directly, and I ran the included local synthetic PoC. I did not test
against any live or third-party KCS store, and the PoC uses only disposable
temporary directories and synthetic bytes. The final attack-path calibration is
reportable Low/P3: the impact is recoverable local archive integrity and
availability loss, with adoption of lower-trust state and an exact-slot match
as meaningful constraints.

## Background

KCS stores durable objects under kind-specific directories and names them by
the SHA-256 hash of their canonical bytes. A raw file snapshot starts with the
file bytes, derives `sha256:<hex>`, maps that hash through a two-level fanout,
and writes the object only if the store is expected to need it. We can see the
raw path from `write_raw()` into the shared object writer:

```rust
// crates/kcs-core/src/cas.rs
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

The fanout path is deterministic and not a secret. Once we know the bytes, or
we supply the file whose bytes the operator will snapshot, we can compute the
same pathname KCS will use:

```rust
// crates/kcs-core/src/cas.rs
pub fn fanout_path(base: impl AsRef<Path>, hash: &str) -> Result<PathBuf> {
    if !is_hash(hash) {
        return Err(KcsError::invalid_usage("invalid hash"));
    }

    let digest = &hash["sha256:".len()..];
    Ok(base
        .as_ref()
        .join(&digest[0..2])
        .join(&digest[2..4])
        .join(hash))
}
```

KCS does have read-time protection. When a path exists during `read_by_hash()`,
the code reads the bytes, hashes them, and rejects a mismatch:

```rust
// crates/kcs-core/src/cas.rs
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
```

That control is important because it bounds the impact: we should expect
detected corruption, not silent object substitution. The missing control is
earlier, at the write side, where the store decides whether the existing slot
is already the object being written.

## Vulnerability Details

The vulnerable condition is concentrated in `atomic_write()`:

```rust
// crates/kcs-core/src/cas.rs
pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;

    if path.exists() {
        return Ok(());
    }
```

When we carry the expected object bytes into this function, the invariant
should be "a pre-existing destination is acceptable only if it is the same
regular CAS object." The current branch checks only `path.exists()`. It does
not reject a directory, symlink, or regular file containing different bytes,
and it does not compare the existing content with `bytes`.

The snapshot path then turns this write-side success into authoritative
history. While building the working tree, KCS writes raw object bytes and
records the returned hash in the tree entry:

```rust
// crates/kcs-core/src/scope.rs
let bytes = fs::read(&path).kcs_io(&path)?;
let raw_hash = if store_raw {
    self.store.write_raw(&bytes)?
} else {
    hash_bytes(&bytes)
};
let mut tree_entry = TreeEntry::raw_file(file_name.clone(), raw_hash)?;
```

After the working tree is built, the same snapshot operation writes the tree
and commit objects and advances refs:

```rust
// crates/kcs-core/src/scope.rs
let working = self
    .build_working_tree_with_normalize(true, excluded_paths, normalize_by_path)?
    .tree;
let tree_value =
    serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;

let commit = CommitObject::new(
    tree_hash.clone(),
    parents,
    created_at,
    message,
    self.tool_lock_hash()?,
    stats.clone(),
    commit_type,
)?;
let commit_value =
    serde_json::to_value(&commit).map_err(|err| KcsError::schema(err.to_string()))?;
let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;

atomic_overwrite(
    &self.kcs_dir.join("refs/heads/main"),
    commit_hash.as_bytes(),
)?;
atomic_overwrite(&self.kcs_dir.join("HEAD"), commit_hash.as_bytes())?;
```

The important state transition is therefore:

1. A lower-trust adopted store already contains an occupied raw slot at the
   exact fanout path for `sha256:<expected>`.
2. The operator snapshots a file whose bytes hash to `sha256:<expected>`.
3. `write_raw()` returns that expected hash because `atomic_write()` returned
   success.
4. The tree and commit can name that raw hash, and refs can advance.
5. A later read reaches the corrupt slot and reports a hash mismatch or I/O
   failure, but the write that should have repaired or rejected the state has
   already accepted it.

This is most interesting at an adoption boundary. If an attacker already has
unrestricted write access to the operator's private live store, the attacker
already has equivalent local authority. The useful case is a copied, synced,
shared, or preseeded `.kcs` directory whose state is lower trust than the
operator identity that later consumes it.

## Exploitability Analysis

The strongest route is a deterministic preseed rather than a timing race. We
first choose or predict content the operator will snapshot. Because the raw
object name is just `sha256` over those bytes, we can compute the exact raw CAS
fanout path. We then place wrong bytes, or a wrong-type filesystem entry, at
that path before the operator adopts the store. When KCS later tries to store
the real bytes, the early `path.exists()` branch prevents both repair and
failure.

The exact-slot requirement is a real constraint, but it is not prohibitive in
the shared-state scenario. If the lower-trust contributor also supplies the
scope content, the contributor knows the bytes and hash. If the contributor is
poisoning a common file, such as a generated report or template with stable
contents, the hash can also be computed offline. Where the contributor cannot
predict or influence the content, the primitive is much weaker.

Read-time verification is the key mitigating control. We do not get a silent
substitution where KCS returns the attacker's bytes as the expected object.
Instead, we get a durable denial and integrity failure: history points at a raw
object that cannot be read as that object. That still matters for an archive
system because future legitimate writes of the same content do not heal the
slot. The operator has to detect and quarantine or remove the corrupt path
manually before normal CAS behavior resumes.

Wrong-type entries are useful mainly as another way to make the slot
unusable. A directory or other non-regular entry at the destination satisfies
the write-side `exists()` test but makes later object reads fail. A regular
file with wrong bytes gives the clearest diagnostic because the read path can
compute and report an actual digest mismatch.

The route does not provide code execution, privilege escalation, or external
file overwrite. It is a local persisted-state poisoning issue that crosses a
trust boundary only when KCS treats adopted archive state as authoritative
under a more trusted operator workflow. That is why I agree with the final
Low/P3 calibration even though the write-side invariant itself is crisp.

## Proof of Concept

The included PoC is a local synthetic regression model. It does not modify a
real KCS checkout or use network access. Instead, it creates a disposable
store-shaped directory, pre-seeds the raw object fanout path with wrong bytes,
then runs a small function that mirrors the current `atomic_write()` early
success branch. We then compare that behavior with a fixed check that rejects
occupied slots whose bytes do not match the expected CAS object.

From the report directory:

```sh
cd poc
make
```

Expected output:

```text
[+] expected object hash: sha256:080a7a8cf0b4fe37ff7a2924a65be479af879b449a36605434b4fd4713e81c23
[+] preseeded slot hash: sha256:360bec7c1bc6e57af1739a2b1c351502afb3b41cd67f52485a27a143d7b034d7
[+] vulnerable write result: ok-existing-without-verification
[+] slot still contains preseeded bytes: yes
[+] later read detects mismatch: expected sha256:080a7a8cf0b4fe37ff7a2924a65be479af879b449a36605434b4fd4713e81c23 actual sha256:360bec7c1bc6e57af1739a2b1c351502afb3b41cd67f52485a27a143d7b034d7
[+] fixed write rejects mismatch: occupied slot does not match expected CAS object
[+] synthetic regression check complete
```

The PoC is intentionally safe. It only writes under a temporary directory
created by the script, uses synthetic byte strings, and models the vulnerable
write-side decision rather than touching an operator store.

## Remediation

The invariant to restore is simple: an existing CAS destination is idempotent
only if it is the exact regular object that the current write is trying to
store. The write path should reject or quarantine any occupied slot that is not
a regular file with matching bytes. It should do that before returning success,
and it should cover raw, tree, and commit objects because they all share
`atomic_write()`.

A minimal shape is:

```rust
fn verify_existing_object(path: &Path, expected: &[u8]) -> Result<()> {
    let metadata = fs::symlink_metadata(path).kcs_io(path)?;
    if !metadata.file_type().is_file() {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-EXISTING-001",
            "CAS object destination is not a regular file",
            serde_json::json!({ "path": path }),
            crate::ExitCode::PermanentFailure,
        ));
    }

    let existing = fs::read(path).kcs_io(path)?;
    if existing != expected {
        return Err(KcsError::new(
            "KCS-E-STORE-CORRUPT-EXISTING-001",
            "CAS object destination does not match expected bytes",
            serde_json::json!({
                "path": path,
                "expected": hash_bytes(expected),
                "actual": hash_bytes(&existing),
            }),
            crate::ExitCode::PermanentFailure,
        ));
    }

    Ok(())
}

pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;

    if path.exists() {
        return verify_existing_object(path, bytes);
    }

    // Existing temp-write, sync, and rename flow follows.
}
```

For a stronger hardening pass, KCS can combine this with a `create_new`-style
write or a post-rename verification path so a concurrent create between the
existence check and rename is handled as another idempotent-write case rather
than as an overwrite. That is not required to close the adopted-state preseed
path, but it makes the CAS writer's concurrency contract easier to reason
about.

Regression tests should cover:

- an existing regular file with exactly matching bytes, which remains an
  idempotent success;
- an existing regular file with mismatched bytes, which must fail or quarantine
  instead of returning success;
- an existing directory, symlink, or other non-regular entry, which must fail;
- a snapshot after a poisoned raw slot, which must not advance refs as though
  the raw object was safely stored;
- the same occupied-slot checks for tree and commit object writes, since they
  share the vulnerable primitive.

## Summary

KCS correctly verifies object contents when it reads them, but the write path
does not verify an occupied destination before treating it as a successful CAS
write. In an adopted or shared store, that lets lower-trust persisted state
turn a future legitimate snapshot into a reference to an unreadable object. We
demonstrated the broken state transition with a local synthetic PoC and tied it
back to the exact `write_raw()` to `atomic_write()` to snapshot publication
path in the vulnerable revision.

The fix is to make idempotent CAS writes prove idempotence: a pre-existing
destination must be a regular file containing the expected bytes. Variant
review should look at every path that treats existing persisted state as
trusted after adoption, especially places where a later read detects
corruption but an earlier write or publication step has already committed to
that state.
