# A symlinked `.kcs` binds one working root to another scope's live store

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts an
existing `.kcs` entry with link-following filesystem checks and then uses that
path as the repository's live object store. If a lower-trust shared root
contains `.kcs` as a symlink to another valid KCS store, normal commands bind
the selected working root to the linked store. We then read files from root A
while comparing, snapshotting, and advancing refs in store B.

I reviewed the vulnerable revision directly and executed the included local
PoC against synthetic temporary scopes; I did not use live services, real
credentials, or public targets. The PoC shows a snapshot run from the linked
lure root advancing the victim store's `HEAD`.

The realistic impact is cross-scope archive and evidence integrity loss. A
supplied root can create false history in a reachable foreign store, including
commit, ref, manifest, and derived index state for content that did not come
from that store's own working root. The target must be an existing valid KCS
store that the victim process can access, and the victim must invoke KCS in the
supplied root, so I rate this as medium severity.

## Background

KCS stores a folder-local archive under a `.kcs` directory. Commands such as
`status`, `snapshot`, and `index` first open the current folder as a
`Repository`; the resulting object carries both a canonical working-tree root
and a path to the `.kcs` state directory.

The CLI reaches that open path through ordinary commands. In `status` and
`snapshot`, we do not need a special or hidden entry point:

```rust
// crates/kcs-cli/src/main.rs, run()
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
```

`index` uses the same repository object, scans the opened root, and later calls
the auto-snapshot path:

```rust
// crates/kcs-cli/src/main.rs, run_index()
let repo = Repository::open_current()?;
let _lock = repo.lock_store()?;
validate_repo_tool_lock(&repo)?;
let preview = build_scan_preview(ScanPreviewRequest {
    scope_path: repo.root().display().to_string(),
    include_raw_hashes: !args.preview,
    require_network_approval: !args.offline,
})
.map_err(pipeline_to_kcs)?;
...
let outcome = repo.auto_snapshot_with_normalize(
    Some("kcs index auto snapshot"),
    None,
    &excluded,
    &index_result.normalize_by_path,
)?;
```

The security boundary we care about is the binding between `repo.root()` and
`repo.kcs_dir()`. Once KCS has accepted a `Repository`, readers and writers
assume the working files and archive state belong to the same scope.

## Vulnerability Details

The bug starts when KCS handles an existing `.kcs` entry. `Repository::init`
canonicalizes the selected root, builds `root/.kcs`, and delegates any existing
entry to `Repository::open`:

```rust
// crates/kcs-core/src/scope.rs, Repository::init()
let root = root.canonicalize().kcs_io(root)?;
let kcs_dir = root.join(".kcs");
if kcs_dir.exists() {
    return Self::open(root);
}
```

On Unix-like filesystems, `exists()` follows a symlink whose target exists. If
the supplied root contains `.kcs -> ../victim/.kcs`, we carry the canonical lure
root into `open` instead of rejecting the state entry or checking what it
physically resolves to.

`Repository::open` repeats the same pattern. It canonicalizes only the working
root, keeps the lexical `root/.kcs` path, checks it with `is_dir()`, and stores
that path as both `Repository.kcs_dir` and the `ObjectStore` root:

```rust
// crates/kcs-core/src/scope.rs, Repository::open()
pub fn open(path: impl AsRef<Path>) -> Result<Self> {
    let root = path.as_ref().canonicalize().kcs_io(path.as_ref())?;
    let kcs_dir = root.join(".kcs");
    if !kcs_dir.is_dir() {
        return Err(KcsError::invalid_usage("not a kcs scope"));
    }

    let repo = Self {
        root,
        kcs_dir: kcs_dir.clone(),
        store: ObjectStore::new(kcs_dir),
    };
    repo.validate()?;
    repo.self_heal_head()?;
    Ok(repo)
}
```

There is no `symlink_metadata()` check, no no-follow open, no canonicalization
of `.kcs`, and no comparison between the resolved state directory and the
selected root. From here, the repository has a split identity: `self.root` is
the lure directory, but `self.kcs_dir` and `self.store` resolve through the
symlink to the victim store.

The closest validation does not restore the invariant. `validate()` calls
`validate_scope()`, but `validate_scope()` checks schema shape, `scope_id`
presence, ULID syntax, and optional format version. It never reads or compares
the stored `scope_path`, and it never verifies that the state directory is a
real child of `self.root`:

```rust
// crates/kcs-core/src/scope.rs, Repository::validate_scope()
fn validate_scope(&self) -> Result<()> {
    let path = self.kcs_dir.join("scope.json");
    let value: Value = serde_json::from_str(&fs::read_to_string(&path).kcs_io(&path)?)
        .map_err(|err| KcsError::schema(err.to_string()))?;
    validate_json_schema(SchemaKind::Scope, &value)?;
    let Some(scope_id) = value.get("scope_id").and_then(Value::as_str) else {
        return Err(KcsError::schema("scope.json missing scope_id"));
    };
    if scope_id.is_empty() {
        return Err(KcsError::schema("scope_id is empty"));
    }
    if !is_ulid(scope_id) {
        return Err(KcsError::schema("scope_id must be a ULID"));
    }
    if let Some(version) = value.get("kcs_format_version") {
        let version = version
            .as_str()
            .ok_or_else(|| KcsError::schema("kcs_format_version must be a string"))?;
        validate_format_version(version)?;
    }
    Ok(())
}
```

Once this split repository exists, read and write paths combine the two scopes.
`status` builds the current tree from `self.root`, then reads the comparison
tree through `self.store`:

```rust
// crates/kcs-core/src/scope.rs, Repository::status()
self.validate()?;
let current = self.build_working_tree(false)?.tree;
let current_map = tree_map(&current);
let (head_map, head_shallow) = match self.head_tree_state()? {
    HeadTreeState::Unborn => (BTreeMap::new(), false),
    HeadTreeState::Present(tree) => (tree_map(&tree), false),
    HeadTreeState::Shallow => (BTreeMap::new(), true),
};
```

The mutating path is more damaging. When `snapshot` or `index` asks KCS to store
raw bytes, KCS enumerates direct children of `self.root`, reads their bytes, and
writes raw objects through `self.store`:

```rust
// crates/kcs-core/src/scope.rs, Repository::build_working_tree_with_normalize()
for entry in fs::read_dir(&self.root).kcs_io(&self.root)? {
    let entry = entry.kcs_io(&self.root)?;
    if entry.file_name() == ".kcs" {
        continue;
    }
    let path = entry.path();
    ...
    let bytes = fs::read(&path).kcs_io(&path)?;
    let raw_hash = if store_raw {
        self.store.write_raw(&bytes)?
    } else {
        hash_bytes(&bytes)
    };
    let mut tree_entry = TreeEntry::raw_file(file_name.clone(), raw_hash)?;
```

We then carry that tree into `snapshot_with_type()`. The lock, tree write,
commit write, refs, `HEAD`, and manifest all use the substituted `kcs_dir` or
`store`:

```rust
// crates/kcs-core/src/scope.rs, Repository::snapshot_with_type()
self.validate()?;
let _lock = StoreLock::acquire(&self.kcs_dir)?;
...
let working = self
    .build_working_tree_with_normalize(true, excluded_paths, normalize_by_path)?
    .tree;
let tree_value =
    serde_json::to_value(&working).map_err(|err| KcsError::schema(err.to_string()))?;
let (tree_hash, _) = self.store.write_json(ObjectKind::Tree, &tree_value)?;
...
let (commit_hash, _) = self.store.write_json(ObjectKind::Commit, &commit_value)?;
atomic_overwrite(
    &self.kcs_dir.join("refs/heads/main"),
    commit_hash.as_bytes(),
)?;
atomic_overwrite(&self.kcs_dir.join("HEAD"), commit_hash.as_bytes())?;
self.write_manifest(&working, prior_tree.as_ref())?;
```

That is the vulnerable state transition: a lower-trust root controls the
working bytes, but the victim store receives the objects and ref update.

## Exploitability Analysis

The strongest route is a local confused-deputy attack against a reachable KCS
store. A lower-trust contributor gives the operator a directory whose `.kcs`
entry is a symlink to another valid store path that resolves in the operator's
filesystem namespace. When the operator runs `kcs snapshot` or `kcs index` from
that directory, KCS follows the symlink with the operator's permissions and
mutates the target store.

This does not provide arbitrary filesystem write. The symlink target must be a
structurally valid KCS store, and the process must be able to read and write it.
Those constraints matter: schema validation blocks a link to an arbitrary
directory, and newly initialized stores are owner-restricted on Unix-like
systems. The bug is still security-relevant because a shared folder, archive,
or generated workspace can cross a trust boundary inside the same user's
reachable storage. The attacker does not need code execution in the victim
process; they need control over the supplied root and a target store path that
the victim can resolve.

Once the repository is split, we get several useful effects:

- `status` creates false comparison evidence by listing files from the lure root
  against `HEAD` from the victim store.
- `snapshot` writes lure root bytes into the victim store's CAS, creates a new
  tree and commit, and advances the victim store's `refs/heads/main`, `HEAD`,
  and manifest.
- `index` follows the same open path, scans `repo.root()`, uses policy and task
  state below `repo.kcs_dir()`, and ends by auto-snapshotting normalized results
  into the linked store.

The most reliable proof is therefore not a crash or race. We can deterministically
prepare root A with attacker-controlled content, link `rootA/.kcs` to
`rootB/.kcs`, and ask KCS to snapshot root A. If `rootB/.kcs/HEAD` changes, KCS
has accepted one root's working files as new history in another root's store.

There are useful limits and dead ends. Prior commits are usually recoverable
because the object graph is content-addressed and append-oriented; the attacker
is not erasing history by default. The attack also depends on symlink
preservation and target-path availability. A copied store that is no longer a
live alias raises a different provenance and mobility question, so this report
focuses on the live symlink/alias case where ordinary commands keep mutating
the foreign store.

## Proof of Concept

The included PoC is a local shell harness under `poc/`. It creates two
temporary roots, initializes and snapshots the victim root, replaces the lure
root's `.kcs` entry with a symlink to the victim store, then runs `status` and
`snapshot` from the lure root. The check passes only if the victim store's
`HEAD` changes after the lure snapshot.

Run it with a vulnerable `kcs` binary on `PATH`:

```sh
cd poc
make run
```

If the binary is not on `PATH`, set `KCS_BIN` or `KCS_CMD`:

```sh
cd poc
KCS_BIN=kcs make run
```

Representative output from my local run against revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`:

```text
[+] created disposable victim root and lure root
[+] lure .kcs is a symlink to the victim store
[+] victim HEAD before: sha256:052dc462a259d4f5d4d87d8c93da97400de26330aa6a0198eed3d5b369df3552
[+] victim HEAD after:  sha256:85cebfc512b79c6857245121fe6ea9b2ae69ce9dab7ab83d51fab3c9d1407671
[+] snapshot from the lure root advanced the linked victim store
```

The script uses only temporary directories and sets KCS device/config state to
that disposable area. It removes the temporary workspace on exit.

## Remediation

The invariant to restore is simple: unless the user invokes an explicit,
audited import/adoption workflow, a live `.kcs` store opened for a root must be
the real `.kcs` directory inside that same canonical root. Normal command
opening should reject a symlink, bind mount alias, or other resolved path that
escapes the selected root.

A minimal fix is to inspect the `.kcs` directory without following symlinks,
canonicalize the accepted state directory, and require it to resolve to the
expected child path before constructing `ObjectStore`:

```rust
pub fn open(path: impl AsRef<Path>) -> Result<Self> {
    let root = path.as_ref().canonicalize().kcs_io(path.as_ref())?;
    let kcs_dir = root.join(".kcs");
    let metadata = fs::symlink_metadata(&kcs_dir).kcs_io(&kcs_dir)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(KcsError::invalid_usage("not a kcs scope"));
    }

    let resolved_kcs_dir = kcs_dir.canonicalize().kcs_io(&kcs_dir)?;
    let expected_kcs_dir = root.join(".kcs");
    if resolved_kcs_dir != expected_kcs_dir {
        return Err(KcsError::invalid_usage(
            ".kcs store must be inside the selected scope root",
        ));
    }

    let repo = Self {
        root,
        kcs_dir,
        store: ObjectStore::new(expected_kcs_dir),
    };
    repo.validate()?;
    repo.self_heal_head()?;
    Ok(repo)
}
```

That style of guard avoids relying on `scope_path` equality, which can be too
strict for legitimate whole-folder moves or detached imports. If KCS wants to
support external store adoption, it should be a separate command with an
explicit prompt, a recorded audit event, and a new scope-binding record created
for the selected root.

Regression tests should cover:

- `Repository::open` rejects a root whose `.kcs` is a symlink to another valid
  KCS store.
- `Repository::init` rejects or refuses to adopt the same symlinked existing
  entry instead of delegating to `open`.
- `status`, `snapshot`, and `index` cannot read from root A while using store B.
- A whole-folder move with a real `.kcs` directory inside the moved root still
  opens if that remains intended behavior.

## Summary

KCS trusts a link-following `root/.kcs` path as the live state directory after
canonicalizing only the selected working root. We can exploit that mismatch
with a supplied root whose `.kcs` links to another valid store: normal commands
then read attacker-controlled working files from the supplied root while using
the foreign store for history, refs, manifest, approvals, tasks, and indexing
state. The included local PoC demonstrates the core integrity failure by
advancing a victim store's `HEAD` from a snapshot executed in the lure root.

The most important fix is to bind the physical `.kcs` store to the selected
canonical root before any repository object is constructed. Variant analysis
should also review other paths that accept copied, imported, or registry-backed
scope state, but the live symlink/alias issue stands on its own because it
keeps two working roots attached to one mutable authoritative store.
