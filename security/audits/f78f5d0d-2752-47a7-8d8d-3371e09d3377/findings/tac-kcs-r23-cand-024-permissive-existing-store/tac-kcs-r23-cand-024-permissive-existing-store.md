# Opening an existing permissive `.kcs` exposes future private archive bytes

## Executive Summary

KCS hardens a newly created `.kcs` archive directory to owner-only mode 0700,
because raw CAS objects store verbatim document bytes. The same invariant is not
checked when a scope already has a `.kcs` directory. If a lower-trust local
principal supplies or preserves a structurally valid but traversable store, the
victim can re-run `kcs init` or later open that scope, KCS will accept the
existing archive, and future `snapshot` or `index` operations can publish
victim-readable source bytes into group/world-readable raw objects under the
traversable store.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and ran
the included local Unix PoC against that checkout; I did not assess non-Unix ACL
semantics or a second-account read because the observed 0600 source, 0755
archive, and 0644 raw object already establish the Unix DAC exposure. The
affected version range is not narrowed here beyond the reviewed revision, and I
did not identify a fixing commit.

The practical impact is a medium-severity local confidentiality break. A
supplied-store contributor or another local filesystem principal can make future
private archive bytes readable across an OS-principal boundary, but the path
requires a multi-user or shared-filesystem setting, victim adoption of a valid
existing store, later mutation, and a non-0077 umask.

## Background

KCS scopes keep their archive state in a direct child `.kcs` directory. That
directory contains content-addressed objects, refs, manifests, logs, and other
local state. The raw object store is especially sensitive: when KCS snapshots a
direct child file, it stores the file's bytes under `objects/raw` and records the
raw hash in the tree.

The creation path recognizes that the directory itself is the confidentiality
boundary. In `crates/kcs-core/src/scope.rs`, `Repository::init` creates the
archive layout and then calls `restrict_dir_to_owner()`:

```rust
// crates/kcs-core/src/scope.rs, Repository::init, lines 135-158
let root = root.canonicalize().kcs_io(root)?;
let kcs_dir = root.join(".kcs");
if kcs_dir.exists() {
    return Self::open(root);
}

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

The helper is intentionally simple on Unix:

```rust
// crates/kcs-core/src/scope.rs, restrict_dir_to_owner, lines 1650-1660
pub fn restrict_dir_to_owner(dir: &Path) -> Result<()> {
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(dir, fs::Permissions::from_mode(0o700)).kcs_io(dir)?;
    }
    Ok(())
}
```

That design can be secure if all mutating opens either create the store
themselves or prove that an existing store is already owner-only and owned by the
same OS principal. The bug is that the second half of that invariant is absent.

## Vulnerability Details

The vulnerable transition is the existing-store shortcut in `Repository::init`.
As soon as `root/.kcs` exists, we return through `Self::open(root)` before any
mode, owner, or symlink-sensitive type check runs. From there, `Repository::open`
uses `Path::is_dir()` and logical schema validation:

```rust
// crates/kcs-core/src/scope.rs, Repository::open, lines 188-206
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

When we carry the attacker-influenced `.kcs` directory into `repo.validate()`,
the validation is about KCS file shape, not the filesystem boundary:

```rust
// crates/kcs-core/src/scope.rs, Repository::validate, lines 235-239
pub fn validate(&self) -> Result<()> {
    self.validate_config()?;
    self.validate_scope()?;
    self.validate_manifest()?;
    Ok(())
}
```

For example, `validate_scope()` parses `scope.json`, validates the schema, and
checks that `scope_id` is a ULID. It does not inspect `symlink_metadata()`, UID,
GID, or permission bits:

```rust
// crates/kcs-core/src/scope.rs, Repository::validate_scope, lines 889-909
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

That is enough to accept a valid copied, preseeded, or mode-weakened store.
The issue becomes a disclosure when a later write path archives new victim-only
content. `snapshot` eventually calls `build_working_tree_with_normalize(true,
...)`, so each regular direct child is read and sent to `ObjectStore::write_raw`:

```rust
// crates/kcs-core/src/scope.rs, build_working_tree_with_normalize, lines 261-292
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
    let bytes = fs::read(&path).kcs_io(&path)?;
    let raw_hash = if store_raw {
        self.store.write_raw(&bytes)?
    } else {
        hash_bytes(&bytes)
    };
```

The CAS layer computes a hash, creates fanout directories if needed, and writes
the object with `File::create()`. There is no object-level chmod because the code
relies on the parent store mode to block traversal:

```rust
// crates/kcs-core/src/cas.rs, ObjectStore::write_raw, lines 60-75
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

```rust
// crates/kcs-core/src/cas.rs, atomic_write, lines 155-176
pub(crate) fn atomic_write(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| KcsError::io("path has no parent", path.display().to_string()))?;
    fs::create_dir_all(parent).kcs_io(parent)?;

    if path.exists() {
        return Ok(());
    }

    let temp = parent.join(format!(".tmp-{}-{}", std::process::id(), unix_nanos()));
    let result = (|| -> Result<()> {
        let mut file = File::create(&temp).kcs_io(&temp)?;
        file.write_all(bytes).kcs_io(&temp)?;
        file.sync_all().kcs_io(&temp)?;
        drop(file);
        fs::rename(&temp, path).kcs_io(path)
    })();
```

So the bad state is concrete. We start with a source file that only the victim
can read, for example mode 0600. We then carry those bytes through normal
snapshot processing into a raw CAS object created under a 0755 `.kcs` tree. With
the common umask 022, the resulting raw object is 0644, and a different local
principal can traverse the store and read the archive copy even though the
source path remained private.

## Exploitability Analysis

The strongest practical route is a supplied or precreated store on a multi-user
host or shared filesystem. We do not need to corrupt KCS metadata or win a race.
We only need KCS to accept a valid store whose Unix ownership or permission
state is weaker than the owner-only boundary that KCS applies to stores it
creates itself.

A realistic sequence looks like this:

1. A lower-trust participant prepares or influences a scope containing a valid
   `.kcs` directory whose mode is 0755, or otherwise leaves an existing store
   readable/traversable to another principal.
2. The victim runs `kcs init` in that scope, or runs another command that opens
   the existing repository. KCS validates the logical files and reports that the
   scope is already initialized.
3. The victim later snapshots a direct-child private file. The CLI's Tier A
   secret exclusion can skip known secret-looking names such as `.env`, but it
   is not a general filesystem-permission boundary. Ordinary private documents
   can still be regular direct children.
4. KCS writes the raw bytes into `objects/raw` under the unsafe store. If the
   victim process has the common umask 022, those objects are readable.

This is not a same-user "your own files are readable by you" issue. The useful
primitive is cross-principal publication by the victim process: KCS reads bytes
that the lower-trust principal could not read at the source path, then writes an
archive copy where that principal can read it.

There are meaningful constraints. The attacker needs a valid KCS store shape,
not just an empty directory, unless the victim first creates the store and its
mode is later weakened. The victim must perform a mutating operation after
adoption. A process umask of 0077 prevents the specific 0644 raw-object result,
although KCS still has not enforced its own archive boundary and a writable or
wrong-owner store remains an integrity concern. The demonstrated permission
model is Unix DAC; Windows ACL behavior and network filesystems with different
ownership semantics need separate assessment.

The read-only archive case is also important. Some users may intentionally open
trusted, read-only archive material for inspection or recovery. A repair that
blindly chmods every existing `.kcs` can surprise users, and a repair that
accepts every readable archive before mutation keeps the bug. The safer split is
to require owner/private validation before any mutating command and to support
explicit read-only inspection under a narrower policy.

Alternative escalation routes are less direct. If the store is writable by the
attacker, metadata tampering or cross-scope corruption may become possible, but
this report does not need that stronger claim. The source-backed and reproduced
primitive is already sufficient: future victim-only document bytes become
attacker-readable raw archive bytes.

## Proof of Concept

The included PoC is a local Unix shell script under `poc/`. It creates a
disposable fixture, initializes a fresh scope, changes `.kcs` to 0755, re-runs
`kcs init`, writes a synthetic 0600 file, snapshots it, and then searches the raw
object store for the synthetic bytes. It uses a private temporary `HOME` and
`XDG_*` directories so it does not touch the user's normal KCS registry.

From the report directory:

```sh
cd poc
chmod +x repro.sh
KCS_REPO=../../kcs make run
```

Set `KCS_REPO` to a local checkout of the vulnerable revision. If a `kcs` binary
is already built, use `KCS_BIN` instead:

```sh
cd poc
KCS_BIN=./kcs make run
```

On the reviewed vulnerable checkout, I observed:

```text
[+] fresh .kcs mode: 700
[+] re-init status: already initialized
[+] retained .kcs mode after re-init: 755
[+] source file mode: 600
[+] raw object mode: 644
[+] raw object contains synthetic secret: yes
[!] vulnerable path demonstrated: private source bytes were published under a traversable store
```

The script deletes its temporary fixture by default. Set `KEEP_POC_TMP=1` only
when you want to inspect the generated `.kcs` tree after the run.

## Remediation

The invariant to restore is: before any mutating use of an existing `.kcs`, KCS
must prove that the store is a real directory owned by the effective user and
not accessible to group or other principals, or it must securely repair an
owner-controlled store before continuing. Logical schema validation is not a
substitute for that filesystem boundary.

A minimal Unix-focused shape is:

```rust
fn open_for_write(path: impl AsRef<Path>) -> Result<Self> {
    let repo = Self::open(path)?;
    reject_unsafe_store_dir(repo.kcs_dir())?;
    Ok(repo)
}

#[cfg(unix)]
fn reject_unsafe_store_dir(kcs_dir: &Path) -> Result<()> {
    use std::os::unix::fs::{MetadataExt, PermissionsExt};

    let meta = fs::symlink_metadata(kcs_dir).kcs_io(kcs_dir)?;
    if !meta.file_type().is_dir() {
        return Err(KcsError::invalid_usage(".kcs must be a directory"));
    }

    let mode = meta.permissions().mode() & 0o777;
    if mode & 0o077 != 0 {
        return Err(KcsError::invalid_usage(
            ".kcs must not be group/world accessible",
        ));
    }

    if meta.uid() != current_effective_uid()? {
        return Err(KcsError::invalid_usage(".kcs must be owned by the current user"));
    }

    Ok(())
}
```

The exact integration can be stricter than this sketch. In particular, KCS
should call the check from every command that can write archive state, including
`init` on an existing store, `snapshot`, `index`, repair paths that mutate
state, task updates, and any future garbage collection or ref updates. Pure
read-only commands can either share the same check for simplicity or require an
explicit read-only mode with clear warnings.

Regression coverage should include:

- fresh `init` creates `.kcs` as 0700 on Unix;
- re-running `init` on a valid 0755 `.kcs` rejects or repairs before reporting
  success;
- `snapshot` refuses to mutate a scope whose existing store is group/world
  accessible;
- a 0600 source file never produces a group/world-readable raw object beneath a
  traversable store;
- symlink and wrong-owner `.kcs` cases are rejected using `symlink_metadata()`;
- read-only trusted archive behavior is covered separately so mutation and
  observation do not share an unsafe path.

## Summary

KCS already documents and implements the right confidentiality boundary for new
archives: `.kcs` must be owner-only because raw objects contain verbatim document
bytes. The vulnerability is that existing stores skip that control and are
accepted based on logical structure alone. Once we carry a permissive store into
normal snapshot processing, KCS can read a victim-only direct-child file and
publish the same bytes as a 0644 raw object under a traversable archive.

The included PoC demonstrates that state transition locally with synthetic data.
Future research should look for sibling paths where KCS trusts existing archive
state before establishing filesystem ownership, store-root binding, or explicit
user consent, because those checks are security boundaries rather than only
operational hygiene.
