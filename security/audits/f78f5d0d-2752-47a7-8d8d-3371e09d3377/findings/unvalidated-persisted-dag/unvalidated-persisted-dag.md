# Persisted DAG objects bypass semantic validation and escape normalized storage paths

## Executive Summary

| Field | Assessment |
| --- | --- |
| Severity / priority | Medium / P2 |
| CWE | CWE-22: Improper Limitation of a Pathname to a Restricted Directory |
| Confidence | High |
| Confirmed affected revision | `0e19f3c6489da458e93a982a333c308d92d0a0ae` |

KCS validates snapshot tree entries while it creates them, but it does not run
the same semantic validation after loading persisted commit and tree objects.
A lower-trust contributor can therefore supply a copied or preseeded KCS store
whose objects have correct content hashes while a tree entry's
`normalize.tool_profile_hash` contains path separators and parent components.
When the recipient deliberately runs `kcs reindex --force --yes`, KCS embeds
that persisted string in a normalized-instance path before it has been
revalidated. The resulting path can leave both `.kcs` and the selected scope.
The reindex copy path then creates the directory, replaces fixed KCS-shaped JSON
files, or recursively removes the constructed destination when copying fails.

This is **Medium severity / P2**, with high confidence (CWE-22). The filesystem
effect runs with the invoking user's permissions, so the potential impact is
high, but likelihood is medium: exploitation requires adoption of a
lower-trust store, a content-hash-correct poisoned DAG, explicit forced-reindex
confirmation, and a compatible user-writable target. The generated `.gN`
suffix and fixed output names materially limit target selection; this is not an
unconstrained arbitrary-file-write or code-execution primitive.

I reviewed exact revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, inspected the relevant history,
and ran the bundled offline checker against synthetic JSON. I did not build a
live poisoned `.kcs` store or invoke KCS's reindex command. No real data,
credentials, network service, or filesystem target was used, and the checker
performs no create, overwrite, or remove operation. The vulnerable reindex copy
helper first appears in commit
`8a089f56b5d8ca772203caf5792b78bc83fceb29` and remains present in the reviewed
revision; no fixed revision was available for comparison.

## Background

KCS represents snapshot history as content-addressed commit and tree objects.
`HEAD` names a commit, the commit names a tree, and each tree entry can name a
normalized instance through `(raw_hash, tool_profile_hash, gen)`. Commit and
tree bytes are stored beneath their SHA-256-derived names. This detects an
accidental or post-publication byte change, but a store author can intentionally
choose JSON first, calculate its hash, and place both the object and its correct
name in a supplied archive. Content integrity is not semantic trust.

The intended semantic boundary is clear in `TreeEntry::validate` and
`build_tree` (`crates/kcs-core/src/dag.rs:40-91`):

```rust
pub fn validate(&self) -> Result<()> {
    if self.path.contains('/') {
        return Err(KcsError::path(
            "tree entry path must be a direct child file name",
            self.path.clone(),
        ));
    }
    if self.path.is_empty() {
        return Err(KcsError::path(
            "tree entry path is empty",
            self.path.clone(),
        ));
    }
    if self.entry_type != "file" {
        return Err(KcsError::schema("Step 1 tree entry type must be file"));
    }
    if !is_hash(&self.raw_hash) {
        return Err(KcsError::schema("raw_hash must be sha256 lowercase hex"));
    }
    if let Some(normalize) = &self.normalize {
        if !is_hash(&normalize.tool_profile_hash) {
            return Err(KcsError::schema(
                "tool_profile_hash must be sha256 lowercase hex",
            ));
        }
    }
    Ok(())
}

pub fn build_tree(mut entries: Vec<TreeEntry>) -> Result<TreeObject> {
    for entry in &entries {
        entry.validate()?;
    }

    entries.sort_by(|a, b| a.path.as_bytes().cmp(b.path.as_bytes()));
    for pair in entries.windows(2) {
        if pair[0].path == pair[1].path {
            return Err(KcsError::duplicate_path(pair[0].path.clone()));
        }
    }

    Ok(TreeObject {
        entries,
        object_type: "tree".to_owned(),
    })
}
```

If we follow a fresh snapshot, it takes this route. In particular,
`Repository::build_working_tree_with_normalize` attaches the normalize
reference, calls `tree_entry.validate()`, and then calls `build_tree`
(`crates/kcs-core/src/scope.rs:296-303`). A normal direct-child document cannot
put a slash or `..` sequence into `tool_profile_hash`; the profile must be an
exact `sha256:` value followed by 64 lowercase hexadecimal characters.

Normalized instances are not themselves content-addressed. Their identity is
encoded in a directory name beneath
`.kcs/objects/normalized_units/<fanout>/<fanout>/`. This makes validation of the
two hash strings a filesystem-containment invariant, not merely a formatting
preference.

The relevant actor is therefore not an ordinary document author in an already
healthy private scope. It is a lower-trust contributor who supplies or shares
persisted KCS state that another user later adopts. The recipient's explicit
`--force --yes` interaction authorizes reindexing that selected store; it does
not authorize filesystem effects outside it.

## Vulnerability Details

### Hash verification stops before semantic verification

`ObjectStore::read_by_hash` recomputes the SHA-256 digest of the stored bytes
(`crates/kcs-core/src/cas.rs:78-100`):

```rust
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

    Err(KcsError::not_found(hash))
}
```

That is a useful corruption check. It cannot reject a contributor who has
already hashed the poisoned bytes. If we carry those verified bytes forward,
we next reach `Repository::read_commit` and
`Repository::read_tree`, where the object-directory kind is checked and Serde
checks the JSON field shapes. Neither function invokes the constructor-side
validators (`crates/kcs-core/src/scope.rs:742-755`):

```rust
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

We therefore receive a tree that can be valid JSON and valid CAS content while
violating the required entry type, direct-child path, raw hash, normalized
profile hash, object-type tag, sorting, or uniqueness rules. The path escape
needs only the normalized profile field; its `String` type satisfies
deserialization.

`CommitObject::new` has the same construction/read asymmetry. It validates the
tree hash, tool-lock hash, parent hashes, and timestamp at
`crates/kcs-core/src/dag.rs:117-156`, but `read_commit` does not reapply those
rules. A minimally crafted attack can keep the commit otherwise valid and put
the semantic violation solely in its referenced tree.

### Forced reindex carries the poisoned field forward

`run_reindex` does impose meaningful operator interaction: it rejects calls
without both `--force` and `--yes`. After opening and locking the store, however,
we read the persisted HEAD tree and directly forward each normalize reference
to the copy helper (`crates/kcs-cli/src/main.rs:2839-2890`):

```rust
fn run_reindex(args: UnsupportedArgs) -> Result<Value> {
    let parsed = parse_reindex_args(without_json(args.args))?;
    if !parsed.force {
        return Err(KcsError::invalid_usage(
            "reindex requires --force in Step 3",
        ));
    }
    if !parsed.yes {
        return Err(KcsError::new(
            "KCS-E-CONFIRM-REJECTED-001",
            "reindex --force requires confirmation; pass --yes in non-interactive mode",
            json!({}),
            ExitCode::ConfirmationRejected,
        ));
    }
    let repo = Repository::open_current()?;
    let _lock = repo.lock_store()?;
    validate_repo_tool_lock(&repo)?;
    let head = repo
        .head_commit_hash()?
        .ok_or_else(|| KcsError::not_found("HEAD"))?;
    let tree = read_head_tree_for_rebuild(&repo, &head)?;

    for entry in &tree.entries {
        let Some(normalize) = &entry.normalize else {
            continue;
        };
        let new_gen = normalize.gen + 1;
        match copy_normalized_instance_gen(
            repo.kcs_dir(),
            &entry.raw_hash,
            &normalize.tool_profile_hash,
            normalize.gen,
            new_gen,
        ) {
            // ...
        }
    }
    // ...
}
```

As we move through `read_head_tree_for_rebuild`, no validation intervenes; it is
a thin wrapper around `repo.read_commit` and `repo.read_tree`. A later snapshot
does validate newly constructed entries, but that happens only after the copy
helper has already performed its filesystem operations.

### Path construction treats a semantic hash as a path fragment

`normalized_instance_dir` embeds `tool_profile_hash` verbatim
(`crates/kcs-pipeline/src/markdownize.rs:311-329`):

```rust
pub fn normalized_instance_dir(
    kcs_dir: impl AsRef<Path>,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> PathBuf {
    let digest = raw_hash.strip_prefix("sha256:").unwrap_or(raw_hash);
    let fanout_a = digest.get(0..2).unwrap_or(digest);
    let fanout_b = digest.get(2..4).unwrap_or("");
    kcs_dir
        .as_ref()
        .join("objects/normalized_units")
        .join(fanout_a)
        .join(fanout_b)
        .join(format!("{raw_hash}.{tool_profile_hash}.g{gen}"))
}
```

The short-digest guards prevent slice panics, but they do not make either hash
a safe path component. A synthetic profile such as
`marker/../../../../../../../__synthetic_escape_marker__` creates real parent
components after the raw-hash-prefixed first component. If we substitute that
value with the bundled fixture's virtual scope root and generation 2, lexical
normalization moves the destination from below
`synthetic-scope/.kcs/objects/normalized_units/aa/aa/` to
`__synthetic_escape_marker__.g2`, outside `synthetic-scope`. KCS does not need
to call `canonicalize` for the effect: filesystem operations interpret the
parent components during path resolution. There is no component check or
containment check before the path reaches those operations.

### Error cleanup turns the path into a recursive-removal primitive

At the final sink, the copy helper constructs both generations, creates the
destination, reads the old manifest and units, atomically replaces selected
JSON files, and removes the entire destination on any error
(`crates/kcs-cli/src/main.rs:5453-5544`):

```rust
let old_dir = kcs_pipeline::markdownize::normalized_instance_dir(
    kcs_dir,
    raw_hash,
    tool_profile_hash,
    old_gen,
);
let new_dir = kcs_pipeline::markdownize::normalized_instance_dir(
    kcs_dir,
    raw_hash,
    tool_profile_hash,
    new_gen,
);
fs::create_dir_all(&new_dir)
    .map_err(|err| KcsError::io(err.to_string(), new_dir.display().to_string()))?;
let result = (|| -> Result<()> {
    let manifest_path = old_dir.join("manifest.json");
    let mut manifest: Value =
        serde_json::from_slice(&fs::read(&manifest_path).map_err(|err| {
            KcsError::io(err.to_string(), manifest_path.display().to_string())
        })?)
        .map_err(|err| store_corrupt_error(&manifest_path, err.to_string()))?;
    // ... update manifest fields ...
    atomic_overwrite_file(&new_dir.join("manifest.json"), &manifest_bytes)?;
    // ... copy recognized 16-lowercase-hex .json unit files ...
    Ok(())
})();
if result.is_err() {
    let _ = fs::remove_dir_all(&new_dir);
}
result
```

To maximize this bounded primitive, we can choose a non-overflowing persisted
generation so `new_dir` matches a pre-existing user-writable directory whose
name ends in `.g<new_gen>`, while the adjacent old-generation directory or its
`manifest.json` is absent. `create_dir_all` succeeds for the existing target,
the old-manifest read fails, and cleanup recursively removes `new_dir`. This
route does not require a valid old normalized instance.

If we instead arrange for both escaped generation directories to exist and the
old one contains valid KCS-shaped data, the success path can replace
`manifest.json` and unit files whose names match 16 lowercase hexadecimal
characters plus `.json`.
Those bytes are derived from the old JSON with generation and timestamp fields
updated; the attacker does not gain an arbitrary filename or arbitrary-byte
write. Directory creation is also observable when the rest of the copy can
complete. These distinctions are important to the severity assessment.

## Exploitability Analysis

The attack chain is realistic at the supplied-store boundary:

1. A lower-trust archive contributor creates a tree with ordinary JSON types
   but a non-hash `tool_profile_hash` containing path components. The contributor
   computes the tree's content hash, creates an otherwise valid commit naming
   it, computes the commit hash, and makes that commit the supplied store's HEAD.
2. The recipient copies or adopts that store. Ordinary CAS reads accept the
   objects because the bytes match the contributor-chosen hashes.
3. The recipient intentionally runs the documented forced-reindex workflow.
   The unchecked tree field reaches `normalized_instance_dir` and then
   `copy_normalized_instance_gen`.
4. KCS acts as a confused deputy with the recipient's filesystem authority at
   the escaped destination.

The recursive-removal branch is more practical than the overwrite branch.
Here we deliberately rely on failure: the old generation can simply be absent
or malformed. Reliability then depends on predicting a writable directory with
a compatible `.gN` suffix and choosing `gen` so the next generation matches it.
Permissions and the existing directory layout still decide whether
`create_dir_all` and `remove_dir_all` succeed.

For the overwrite branch, we face stricter prerequisites. Both escaped old and
new locations have the same attacker-selected stem and adjacent generation
suffixes. The old location must provide parseable JSON, and only
`manifest.json` plus recognized unit-file names are copied. Atomic rename helps
crash consistency but does not restore scope containment; it replaces those
fixed names in the escaped destination.

Several stronger-sounding interpretations do not follow from the evidence:

- A healthy locally built tree rejects the profile before persistence, so
  controlling an ordinary selected-scope document is insufficient.
- Mutating a private live store as the same user is not the relevant authority
  gain. The meaningful boundary is a copied, shared, synced, or preseeded store
  authored at lower trust and later consumed by another user.
- There is no network entry point, credential use, or remote service in this
  path.
- Target names retain the generated `.gN` suffix, and writes retain KCS-shaped
  filenames. We cannot claim a completely arbitrary path or arbitrary bytes.
- The filesystem operations use only the invoking user's authority. The trace
  does not establish privilege escalation or code execution.

High impact reflects the possibility of recursive data removal or replacement
outside the selected scope. Medium likelihood reflects the multi-step adoption
and confirmation requirements plus target-shape and permission constraints.
That combination yields the final Medium/P2 rating.

## Proof of Concept

The `poc/` directory contains a deliberately non-operational regression oracle.
When we run it, we separate three facts that are easy to conflate: JSON shape
acceptance, content hashing, and semantic validity.

- `synthetic-tree.json` is a single synthetic tree object. It is not a complete
  store, contains no real path or data, and cannot be passed directly to KCS as
  an archive.
- `check_regression.py` computes the fixture's canonical content hash, models
  the current shape-only acceptance, reproduces the exact POSIX path formula
  lexically, and runs the proposed strict semantic check. It reads the fixture
  and prints calculations only.

Run it from this report directory:

```sh
cd poc
python3 check_regression.py
```

Representative output from the reviewed fixture is:

```text
fixture=synthetic-tree.json
canonical_cas_hash=sha256:f88fa1be66e76bb6af2037d84646bfb520704c9211bb7f3c4bc82c0e8e3a17f3
json_shape_deserialization=accepted
constructed_destination=synthetic-scope/.kcs/objects/normalized_units/aa/aa/sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.marker/../../../../../../../__synthetic_escape_marker__.g2
normalized_destination=__synthetic_escape_marker__.g2
contained_in_scope=false
strict_read_validation=rejected: tool_profile_hash must be sha256 lowercase hex
filesystem_operations=none
PASS: shape-valid content is rejected semantically before path use
```

This is intentionally an offline proof of the semantic mismatch and path
calculation, not an operational deletion payload. It does not invoke KCS or
touch the modeled destination. A production regression should use temporary
directories and call the real persisted-read API, as described below.

## Remediation

The invariant to restore is simple: **no persisted DAG object may be returned
to a caller until it satisfies every semantic invariant enforced when KCS
constructs that object**. Validation belongs in the central `read_commit` and
`read_tree` methods so every current and future consumer receives a validated
object. Reindex-only validation would leave other readers exposed to poisoned
fields.

Refactor constructor checks into reusable, non-mutating `validate` methods.
For trees, validate the object tag, every entry, and strict UTF-8-byte ordering
and uniqueness. For commits, validate the object tag, tree/tool-lock/parent
hashes, and timestamp. Then make both persisted readers fail closed:

```rust
impl TreeObject {
    pub fn validate(&self) -> Result<()> {
        if self.object_type != "tree" {
            return Err(KcsError::schema("tree object_type must be tree"));
        }
        for entry in &self.entries {
            entry.validate()?;
        }
        for pair in self.entries.windows(2) {
            if pair[0].path.as_bytes() >= pair[1].path.as_bytes() {
                return Err(KcsError::schema(
                    "tree entries must be strictly sorted and unique",
                ));
            }
        }
        Ok(())
    }
}

impl CommitObject {
    pub fn validate(&self) -> Result<()> {
        if self.object_type != "commit" {
            return Err(KcsError::schema("commit object_type must be commit"));
        }
        if !is_hash(&self.tree) || !is_hash(&self.tool_lock_hash) {
            return Err(KcsError::schema("commit contains an invalid hash"));
        }
        if self.parents.iter().any(|parent| !is_hash(parent)) {
            return Err(KcsError::schema("parent must be sha256 lowercase hex"));
        }
        if !is_valid_created_at(&self.created_at) {
            return Err(KcsError::schema("created_at is not canonical UTC ISO8601"));
        }
        Ok(())
    }
}

pub fn read_tree(&self, hash: &str) -> Result<TreeObject> {
    let object = self.store.read_by_hash(hash)?;
    if object.kind != ObjectKind::Tree {
        return Err(KcsError::schema("hash does not identify a tree"));
    }
    let tree: TreeObject = serde_json::from_slice(&object.bytes)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    tree.validate()?;
    Ok(tree)
}

pub fn read_commit(&self, hash: &str) -> Result<CommitObject> {
    let object = self.store.read_by_hash(hash)?;
    if object.kind != ObjectKind::Commit {
        return Err(KcsError::schema("hash does not identify a commit"));
    }
    let commit: CommitObject = serde_json::from_slice(&object.bytes)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    commit.validate()?;
    Ok(commit)
}
```

`build_tree` and `CommitObject::new` should call these same validators after
constructing their objects so write-side and read-side rules cannot drift.
Preserve the existing `gen` default for compatible older trees, but do not use
`build_tree` itself as the read validator: it sorts input and would silently
normalize a noncanonical persisted object instead of rejecting it.

Add a second defense at the path boundary. Change
`normalized_instance_dir` to return `Result<PathBuf>`, require both identity
arguments to satisfy the exact KCS hash grammar, and reject non-normal path
components before joining. Because valid hashes contain only the `sha256:`
prefix and lowercase hex, component validation is deterministic and does not
require touching the filesystem. Filesystem mutators should accept only this
validated path type. A containment assertion against the normalized-units root
is useful defense in depth, but canonicalizing an attacker-selected path alone
is insufficient because targets may not exist and symlink races remain possible.

### Regression tests

The fix should include at least the following hermetic tests:

1. Write canonical synthetic tree bytes with a correct CAS hash but a traversal
   `tool_profile_hash`; assert `Repository::read_tree` returns a store/schema
   error.
2. Create one temporary scope and a separate temporary sentinel directory named
   with a compatible `.gN` suffix. Point a synthetic adopted HEAD at the invalid
   tree, invoke the reindex path, and assert rejection occurs before any
   directory creation, JSON replacement, or sentinel removal.
3. Table-test `read_tree` against an invalid object tag, nested/empty paths,
   non-file entries, malformed raw/profile hashes, duplicate paths, and
   noncanonical entry ordering.
4. Table-test `read_commit` against invalid object tags, tree/tool-lock/parent
   hashes, and timestamps. These are constructor-only checks in the vulnerable
   revision and should become read invariants.
5. Confirm valid existing trees still load, including an omitted normalize block
   and an omitted `normalize.gen` that defaults to zero.
6. Unit-test the hardened normalized-path constructor with valid hashes and with
   parent, absolute, separator, short-hash, and mixed-case inputs; every invalid
   case must fail before returning a `PathBuf`.

All tests can use a single disposable temporary directory and synthetic bytes.
They should require no network, credentials, user files, or pre-existing KCS
store.

## Summary

KCS correctly validates DAG semantics when creating fresh objects and correctly
verifies persisted bytes against their content hashes. The gap lies between
those controls: persisted JSON is deserialized and trusted without reapplying
the construction invariants. In an adopted lower-trust store, that lets a
CAS-correct tree carry path syntax in a field that later becomes a normalized
instance directory.

We followed that field from the supplied HEAD tree through `read_tree`, forced
reindex, `normalized_instance_dir`, and the create/write/error-cleanup sinks.
The bundled offline regression shows the semantic rejection that must occur
before path use, without constructing a store or changing the filesystem.
Central strict validation on every commit/tree read is the primary fix; a
fallible, hash-validating path constructor provides the necessary second line
of defense. Future variant review should examine other persisted structs that
derive paths, generations, or resource decisions after shape-only Serde reads,
while keeping this report's impact calibrated to the adopted-store and
forced-reindex constraints.
