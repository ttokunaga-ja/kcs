# Persisted manifest `unit_ref` can escape its normalized-instance directory

## Executive Summary

KCS stores normalized document units in a per-document instance directory. A
`manifest.json` file names each unit through `unit_ref`, and the normal writer
derives that reference as 16 lowercase hexadecimal characters. At revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, however, both production readers
deserialize `unit_ref` as an unconstrained string and append `.json` before
joining it to the instance directory. An absolute reference replaces the
intended base path, while a reference containing `..` components traverses out
of it.

A lower-trust contributor who supplies a copied, shared, synchronized, or
preseeded `.kcs` store can therefore make a later victim-side rebuild or
incremental operation read a compatible normalized-unit JSON file elsewhere
on the victim filesystem. KCS performs the read with the victim user's
authority. The selected unit's markdown can enter chunk/index rebuilding or
incremental previous context under the adopted scope, creating a cross-scope
confidentiality and evidence-integrity failure.

The final severity is **Medium (P2)**. The imported object may contain
sensitive normalized document text, but exploitation requires store adoption,
a victim-readable and predictable `.json` target, a schema-compatible unit,
and a later eligible KCS invocation. Fresh owner-only stores and operating
system permissions materially reduce likelihood.

I reviewed the exact revision above and ran the bundled network-free,
credential-free regression with `make check`. It demonstrated both absolute
and parent-component escape using synthetic files below one temporary
directory. I did not invoke KCS against a real store, read any non-synthetic
file, or test disclosure through a shared service.

No fixing revision was available during this review.

## Background

### Normalized instances and their manifest

KCS converts a source document into one or more `NormalizedUnitObject` values.
Each object contains the normalized markdown plus provenance fields such as
`raw_hash`, `tool_profile_hash`, `gen`, and `unit_key`. The corresponding
`NormalizedInstanceManifest` stores an ordered list of
`NormalizedUnitManifestEntry` records.

The persisted entry accepts `unit_ref` as a normal Serde string:

```rust
// crates/kcs-pipeline/src/markdownize.rs:65-84
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedUnitManifestEntry {
    pub order: u64,
    pub unit_key: String,
    pub unit_ref: String,
    pub unit_type: UnitType,
    pub status: UnitStatus,
    pub prepared_hash: String,
    pub error_kind: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NormalizedInstanceManifest {
    pub raw_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub parent_gen: Option<u64>,
    pub run_id: String,
    pub units: Vec<NormalizedUnitManifestEntry>,
    pub generated_at: String,
}
```

For a store produced exclusively by the normal writer, `unit_ref` is not an
arbitrary path. KCS derives it from `unit_key`:

```rust
// crates/kcs-pipeline/src/prepare.rs:175-179
#[must_use]
pub fn unit_ref(unit_key: &str) -> String {
    let digest = Sha256::digest(unit_key.as_bytes());
    lower_hex(&digest)[..16].to_owned()
}
```

The persistence path applies that derivation again instead of trusting a
caller-supplied filename:

```rust
// crates/kcs-pipeline/src/markdownize.rs:369-376
let manifest_bytes = serde_json::to_vec_pretty(manifest)
    .map_err(|err| PipelineError::Schema(err.to_string()))?;
write_synced_file(&tmp_dir.join("manifest.json"), &manifest_bytes)?;
for unit in units {
    let path = tmp_dir.join(format!("{}.json", prepared_unit_ref(&unit.unit_key)));
    let bytes = serde_json::to_vec_pretty(unit)
        .map_err(|err| PipelineError::Schema(err.to_string()))?;
    write_synced_file(&path, &bytes)?;
}
```

We should therefore treat the 16-hex derivation as a storage invariant, not
merely a naming convention. It is what makes a unit reference a local object
identifier rather than a path.

### The relevant trust boundary

The issue does not require an untrusted child file in an otherwise private,
healthy store to edit its own manifest. The realistic boundary is store
adoption: a user copies, extracts, synchronizes, or otherwise accepts a
`.kcs` directory whose persisted metadata came from a lower-trust contributor.
Once KCS processes that store, filesystem reads occur with the adopting
user's permissions. That difference in authority is what makes a
manifest-selected external path security relevant.

## Vulnerability Details

### The rebuild reader turns the identifier into a path

We first reach `load_normalized_units()` during index reconstruction. KCS
derives the expected instance directory from the current raw hash, tool
profile, and generation, then parses `manifest.json` from that directory.
For each completed entry it uses the deserialized `unit_ref` directly:

```rust
// crates/kcs-cli/src/main.rs:3355-3390
fn load_normalized_units(
    kcs_dir: &Path,
    raw_hash: &str,
    tool_profile_hash: &str,
    gen: u64,
) -> Result<Vec<NormalizedUnitInput>> {
    let dir = kcs_pipeline::markdownize::normalized_instance_dir(
        kcs_dir,
        raw_hash,
        tool_profile_hash,
        gen,
    );
    let manifest_path = dir.join("manifest.json");
    let manifest: NormalizedInstanceManifest = serde_json::from_slice(
        &fs::read(&manifest_path)
            .map_err(|err| KcsError::io(err.to_string(), manifest_path.display().to_string()))?,
    )
    .map_err(|err| store_corrupt_error(&manifest_path, err.to_string()))?;
    let mut units = Vec::new();
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let unit_path = dir.join(format!("{}.json", entry.unit_ref));
        let unit: NormalizedUnitObject = serde_json::from_slice(
            &fs::read(&unit_path)
                .map_err(|err| KcsError::io(err.to_string(), unit_path.display().to_string()))?,
        )
        .map_err(|err| store_corrupt_error(&unit_path, err.to_string()))?;
        units.push(NormalizedUnitInput {
            raw_hash: unit.raw_hash,
            tool_profile_hash: unit.tool_profile_hash,
            gen: unit.gen,
            unit_key: unit.unit_key,
            markdown: unit.markdown,
        });
    }
    Ok(units)
}
```

The decisive transition is the `dir.join(format!(...))` call. Suppose the
instance directory is:

```text
/adopted/.kcs/objects/normalized_units/aa/aa/profile.g1
```

If `unit_ref` is `../../../../../../other-scope/victim-unit`, the selected
path normalizes outside the instance:

```text
/adopted/.kcs/objects/normalized_units/aa/aa/profile.g1/
  ../../../../../../other-scope/victim-unit.json
```

If `unit_ref` is an absolute stem such as
`/known/path/victim-unit`, the formatted component becomes
`/known/path/victim-unit.json` and Rust's path join discards the instance
base entirely.

No read-time check requires 16 lowercase hexadecimal characters, compares
the reference with `unit_ref(entry.unit_key)`, rejects path separators, or
proves that the final object remains below `dir`. The codebase has an
`is_normalized_unit_file()` helper for enumerating canonical unit filenames,
but this manifest-driven read does not call it.

### Parsed external markdown reaches derived state

The `.json` suffix and `NormalizedUnitObject` deserialization constrain what
can be imported, but they do not restore confinement. If the external bytes
have the expected shape, KCS carries their markdown into the rebuild:

```rust
// crates/kcs-cli/src/main.rs:3078-3119
let units = match load_normalized_units(
    repo.kcs_dir(),
    &entry.raw_hash,
    &normalize.tool_profile_hash,
    normalize.gen,
) {
    Ok(units) => units,
    Err(error) if is_rebuild_skippable_unit_error(&error) => {
        skipped_units.push(json!({
            "raw_hash": entry.raw_hash,
            "path": entry.path,
            "gen": normalize.gen,
            "reason": error.error_code(),
        }));
        continue;
    }
    Err(error) => return Err(error),
};
let input = ChunkingInput {
    raw_path: entry.path.clone(),
    units,
    config: config.clone(),
    created_at: now_utc_seconds(),
};
for mut row in chunk_normalized_instance(input).map_err(index_to_kcs)? {
    row.first_seen_commit = Some(head.clone());
    if known.insert(row.chunk_id.clone()) {
        appended.push(StoredChunk {
            rowid: next_rowid,
            row,
        });
        next_rowid += 1;
    }
}
```

We can now see the security state change: content selected outside the
normalized instance is chunked while `raw_path` comes from the current tree
entry. That can contaminate stored chunks and the rebuilt index with content
whose filesystem provenance belongs to another scope. Live search and
evidence attribution may impose further tuple/liveness constraints, so a
malicious unit should be made compatible with the requested raw/profile/gen
tuple for the strongest route.

### Incremental reuse repeats the same error

The previous-instance loader has an independent copy of the vulnerable
operation:

```rust
// crates/kcs-cli/src/main.rs:9685-9713
fn load_previous_instance(output_ref: &str) -> Result<Option<PreviousInstance>> {
    let dir = PathBuf::from(output_ref);
    let manifest_path = dir.join("manifest.json");
    let Ok(bytes) = fs::read(&manifest_path) else {
        return Ok(None);
    };
    let manifest: NormalizedInstanceManifest =
        serde_json::from_slice(&bytes).map_err(|err| KcsError::schema(err.to_string()))?;
    let mut units = Vec::new();
    for entry in &manifest.units {
        if entry.status != UnitStatus::Done {
            continue;
        }
        let unit_path = dir.join(format!("{}.json", entry.unit_ref));
        let Ok(bytes) = fs::read(&unit_path) else {
            return Ok(None);
        };
        let Ok(unit) = serde_json::from_slice::<NormalizedUnitObject>(&bytes) else {
            return Ok(None);
        };
        units.push(unit);
    }
```

When the external object parses, its units become the previous normalized
context for a later incremental adapter request. We do not need to rely on
rebuild indexing alone: both consumers violate the same local-object
identifier invariant.

## Exploitability Analysis

### Strongest practical route

The strongest route starts with a store that the victim will adopt or merge
into a working scope. The contributor places a valid normalized manifest in
an otherwise plausible instance and chooses one or more `Done` entries:

1. Each malicious `unit_ref` names a victim-readable external unit stem by
   absolute path or by a relative traversal whose directory topology is
   predictable.
2. The external file already ends in `.json` after KCS appends the suffix and
   contains a schema-compatible `NormalizedUnitObject`.
3. The victim invokes index reconstruction, repair/reindex behavior that
   shares the rebuilder, or a workflow that loads previous normalized state.
4. KCS reads the external object with the victim's authority and treats its
   markdown as part of the adopted instance.
5. For reliable live search contamination, the object uses provenance fields
   compatible with the current raw hash, profile, generation, and unit key.
   In incremental reuse, the content can also influence the previous context
   supplied to later normalization.

This gives two useful primitives. If the selected external unit contains
victim-only normalized text, it is a cross-scope read primitive. Whether the
original contributor receives that text depends on a later readback channel,
such as access to a synchronized contaminated store or another consumer of
the resulting index. If the external object is contributor-controlled but
outside the selected instance, the same path is an evidence and index
injection primitive: KCS assigns that markdown to the current tree entry.

### Absolute and relative references

An absolute reference is precise but host-specific. It is attractive when
the contributor knows a stable KCS data layout or a path embedded in copied
metadata. A parent-component reference is more portable when two stores have
a predictable relative layout. Both forms reach the same `fs::read` sink,
and a manifest can repeat the operation across multiple entries.

### Constraints and useful dead ends

Several constraints keep the likelihood below High:

- A random secret file is not a useful target. KCS appends `.json` and then
  requires the bytes to deserialize as `NormalizedUnitObject`.
- Operating system permissions still apply. The primitive does not grant
  rights beyond the victim process.
- Fresh KCS stores are intended to be owner-only. A normal lower-trust
  document contributor generally cannot edit a healthy private manifest;
  copied, shared, synchronized, or preseeded state is the important boundary.
- A tuple-mismatched unit may be rejected by later liveness joins or fail to
  appear in live search even though it was read or persisted. Matching the
  expected provenance fields makes the end-to-end outcome more reliable.
- The finding does not establish arbitrary file disclosure, command
  execution, or a public network entry point.

These are real deployment constraints, not compensating validation. None
prevents a compatible victim-readable normalized unit from being selected
outside the instance directory.

## Proof of Concept

The bundled PoC is a bounded source-faithful regression rather than a
production-store exploit. It creates a supplied instance and a second
synthetic scope below one automatically removed `TemporaryDirectory`. It
then models the production path expression exactly:

```python
path = instance_dir / f"{unit_ref}.json"
unit = validate_unit_shape(json.loads(path.read_text(encoding="utf-8")))
```

A harness-only guard refuses any path outside that temporary lab root. The
fixed model requires both the canonical 16-hex form and equality with the
reference derived from `unit_key`, then checks that the selected file's
resolved parent is the instance directory.

From the report directory, run:

```sh
cd poc
make check
```

The observed output was:

```text
[absolute] unit_ref=<tmp>/other-scope/victim-unit
[absolute] selected=<tmp>/other-scope/victim-unit.json
[absolute] contained_in_instance=false
[absolute] vulnerable_loader_marker=True
[absolute] fixed_loader_rejected=non-canonical or mismatched unit_ref
[parent] unit_ref=../../../../../../other-scope/victim-unit
[parent] selected=<tmp>/other-scope/victim-unit.json
[parent] contained_in_instance=false
[parent] vulnerable_loader_marker=True
[parent] fixed_loader_rejected=non-canonical or mismatched unit_ref
[control] canonical_unit_ref=a2a5535cfd14b3dd
[control] fixed_loader_accepted=true
[+] all bounded regression checks passed
```

Both malicious references imported the marker from the synthetic external
unit, while the fixed model rejected them and accepted the in-instance
control. The script performs no network access, uses no credential, touches
no real `.kcs` store, and cleans up automatically.

## Remediation

The invariant to restore is simple: a manifest `unit_ref` is a derived local
object identifier, never a path. Every reader must reject a reference unless
it exactly equals the canonical value derived from the same entry's
`unit_key`, and it must construct the filename from that derived value.

A minimal pattern in both readers is:

```rust
let expected_ref = kcs_pipeline::prepare::unit_ref(&entry.unit_key);
if entry.unit_ref != expected_ref {
    return Err(store_corrupt_error(
        &manifest_path,
        format!("non-canonical unit_ref for {}", entry.unit_key),
    ));
}
let unit_path = dir.join(format!("{expected_ref}.json"));
```

For `load_previous_instance()`, preserve its intended fail-soft behavior by
returning `Ok(None)` on a non-canonical reference rather than reading it.
Centralizing this check in one shared normalized-instance loader avoids the
current duplicated sink.

The minimal fix should be paired with defense in depth:

- Validate the complete manifest at deserialization or at one mandatory
  store-boundary function, including the derived reference equality.
- After opening the object, verify that its `unit_key`, `raw_hash`,
  `tool_profile_hash`, `gen`, and `prepared_hash` agree with the manifest and
  the requested instance before using its markdown.
- If KCS must support non-derived names in the future, canonicalize the
  instance and selected object and require the object to remain a direct
  child. Prefer directory-handle-relative, no-follow opens so a symlink swap
  cannot create a separate time-of-check/time-of-use path.
- Treat imported stores as lower-trust state and run full structural,
  confinement, and provenance validation before rebuild or incremental reuse.

Regression coverage should exercise both `load_normalized_units()` and
`load_previous_instance()` with absolute references, `../` traversal,
embedded separators, overlong and uppercase values, a valid-looking but
mismatched 16-hex reference, and a symlinked unit. Every negative case should
fail before an external read. A canonical control must continue to load, and
an end-to-end rebuild assertion should prove that an external marker never
appears in chunks, search results, evidence, or incremental context.

## Summary

KCS's normal writer makes `unit_ref` safe by deriving a compact hexadecimal
identifier, but its two manifest readers forget that invariant and treat the
persisted field as a path fragment. In an adopted lower-trust store, an
absolute or parent-bearing reference therefore escapes the normalized
instance and selects a compatible external unit with the victim's filesystem
authority.

We demonstrated both path forms with a bounded synthetic regression and
confirmed that a derived-reference check rejects them. The practical impact
is cross-scope normalized-text import plus index, evidence, or incremental
context contamination; store-adoption and schema/path knowledge requirements
calibrate the issue to Medium/P2. The most valuable follow-on variant review
is to inventory every persisted object reference and ensure all readers
re-derive identity, enforce direct-child confinement, and rebind object
provenance before consumption.
