# Normalized unit provenance can be rebound by copied store state

## Executive Summary

KCS rebuilds search chunks from cached normalized unit objects. At revision
`0e19f3c6489da458e93a982a333c308d92d0a0ae`, the rebuild path selects a
normalized instance directory using the requested `(raw_hash,
tool_profile_hash, gen)` tuple, but the reader does not bind that request back
to the manifest, the manifest entries, or the unit objects it deserializes. A
lower-trust contributor who can supply a copied, shared, or preseeded `.kcs`
archive before adoption can place parse-valid normalized state under the
requested directory and make KCS index attacker-chosen markdown with trusted
looking provenance.

The security impact is durable integrity loss in search attribution and
Evidence content. The final severity is Medium/P2: the data-integrity impact is
high for users who trust KCS Evidence, while exploitation requires a local
adopted-store workflow and crafted persisted state rather than a public network
listener.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` directly and
built a local synthetic parser probe for the relevant manifest/unit binding
rules. I did not execute against a live KCS store, use credentials, or test any
third-party target.

## Background

KCS stores the authoritative normalized representation of an indexed document
as a normalized instance. The instance is addressed by a raw object hash, a
tool-profile hash, and a generation number. The on-disk layout makes that tuple
visible in the directory name:

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

`crates/kcs-pipeline/src/markdownize.rs` also defines the normalized manifest
and unit object fields that should agree with that directory:

```rust
pub struct NormalizedUnitObject {
    pub unit_key: String,
    pub unit_type: UnitType,
    pub raw_hash: String,
    pub prepared_hash: String,
    pub tool_profile_hash: String,
    pub gen: u64,
    pub mode: MarkdownizeMode,
    pub markdown: String,
    pub reused_from: Option<ReusedFrom>,
    pub generated_at: String,
}

pub struct NormalizedUnitManifestEntry {
    pub order: u64,
    pub unit_key: String,
    pub unit_ref: String,
    pub unit_type: UnitType,
    pub status: UnitStatus,
    pub prepared_hash: String,
    pub error_kind: Option<String>,
}

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

The normal invariant is straightforward: if we are reading the instance
requested for raw object `R`, profile `P`, and generation `G`, then the manifest
must also describe `R/P/G`, every completed manifest entry must point to the
correct unit object for its `unit_key`, and each unit object must carry matching
identity and prepared-content metadata before its markdown is reused. Path
selection alone proves only where the files were found; it does not prove that
the serialized contents belong to that requested instance.

That distinction matters for KCS because copied and preseeded stores are a real
workflow. After adoption, the invoking user processes the archive as their own
local state. We therefore need the reader to treat persisted normalized JSON as
lower-trust input until it is rebound to the live tree entry and unit identity
it claims to represent.

## Vulnerability Details

The vulnerable path begins in `rebuild_step3_index()` in
`crates/kcs-cli/src/main.rs`. During `index`, `reindex`, and
`repair --rebuild-db`, KCS reads the current tree, extracts each entry's
normalized tuple, and asks `load_normalized_units()` for the cached units:

```rust
for entry in &tree.entries {
    let normalize = match &entry.normalize {
        Some(normalize) => normalize.clone(),
        None => match latest_normalize_ref(repo.kcs_dir(), &entry.raw_hash)? {
            Some(normalize) => normalize,
            None => continue,
        },
    };
    tree_entries.push(TreeEntryRow {
        commit_hash: head.clone(),
        path: entry.path.clone(),
        raw_hash: entry.raw_hash.clone(),
        tool_profile_hash: Some(normalize.tool_profile_hash.clone()),
        gen: normalize.gen,
    });
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
```

At this point, we have the live tree tuple in hand. If the normalized instance
belongs to a copied archive, these values are the point where the cache must be
reconciled with the trusted tree. Instead, `load_normalized_units()` only uses
the tuple to build a path and then trusts fields from the manifest and unit
objects:

```rust
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

The missing comparisons are the root cause. We never compare
`manifest.raw_hash`, `manifest.tool_profile_hash`, or `manifest.gen` with the
request. We then use `entry.unit_ref` as a filename but do not check that it is
the deterministic `unit_ref(entry.unit_key)`. We also do not compare
`entry.unit_key`, `entry.unit_type`, or `entry.prepared_hash` with the unit
object. Finally, we emit a `NormalizedUnitInput` from the unit object's
self-declared `raw_hash`, `tool_profile_hash`, `gen`, `unit_key`, and
`markdown`.

If we carry that unchecked `NormalizedUnitInput` forward, the chunker persists
the self-declared identity into each chunk row:

```rust
let mut row = ChunkRow {
    chunk_id: String::new(),
    raw_hash: unit.raw_hash.clone(),
    tool_profile_hash: unit.tool_profile_hash.clone(),
    gen: unit.gen,
    unit_key: unit.unit_key.clone(),
    chunking_config_hash: input.config.chunking_config_hash.clone(),
    raw_path: input.raw_path.clone(),
    heading_path: Some(section.heading_path.clone()),
    section_id: section_id.clone(),
    char_start: Some(start as u64),
    char_end: Some(end as u64),
    text_hash: hash_bytes(text.as_bytes()),
    text,
    first_seen_commit: None,
    created_at: input.created_at.clone(),
};
row.chunk_id = chunk_hash(&row)?;
rows.push(row);
```

The row's `text_hash` and `chunk_id` are internally consistent with the forged
markdown and forged identity, but they are no longer proof that the markdown was
derived from the raw object selected by the rebuild caller. A copied store can
therefore supply syntactically valid state that passes JSON parsing and path
lookup while failing the semantic identity check that KCS needs for evidence.

Search then joins chunks back to live tree entries using the chunk row's stored
identity:

```rust
let sql = "SELECT c.chunk_id, c.raw_hash, c.tool_profile_hash, c.heading_path,
                  c.section_id, c.char_start, c.char_end, c.text, te.path,
                  bm25(chunk_fts, 1.0, 0.3) AS score
           FROM chunk_fts f
           JOIN chunks c ON c.rowid = f.rowid
           JOIN tree_entries te ON te.commit_hash = ?1
               AND te.raw_hash = c.raw_hash
               AND te.tool_profile_hash = c.tool_profile_hash
               AND te.gen = c.gen
           WHERE chunk_fts MATCH ?2
               AND c.chunking_config_hash = ?3
               AND c.rowid <= ?4
           ORDER BY score, c.chunk_id
           LIMIT 200";
```

This join is a useful live-set control, but it happens after the chunk row has
already been poisoned. If the forged identity matches a live tree entry, the
attacker-controlled text is returned with that entry's trusted path. If it does
not match any live entry, the row can disappear from search instead, which is
still a silent integrity failure for the affected content.

Evidence resolution has the same limitation. It checks that a pointer agrees
with the materialized `ChunkRow`, but by then the chunk row is the object that
needs independent provenance proof:

```rust
if chunk.row.raw_hash != pointer.raw_hash
    || chunk.row.tool_profile_hash != pointer.tool_profile_hash
{
    return Err(invalid_pointer_identity_error(pointer));
}
if let Some(entry_gen) = entry_gen {
    if chunk.row.gen != entry_gen {
        return Err(invalid_pointer_identity_error(pointer));
    }
}
let text = chunk.row.text;
```

Those checks reject a tampered pointer, not a poisoned normalized unit that was
accepted earlier. Once the bad markdown and identity have become a chunk row,
later consumers can only attest that they are consistently reading the poisoned
row.

## Exploitability Analysis

The strongest route is a copied-store provenance confusion attack. The
lower-trust contributor does not need to write into the victim's already-private
live store after adoption. Instead, we start from a workflow where the operator
receives or syncs a `.kcs` archive that contains normalized instance state. The
contributor crafts a directory name for a live requested tuple and places a
schema-valid `manifest.json` and completed unit JSON inside it.

From there, we can choose between two useful outcomes.

The first route is false attribution. We put arbitrary markdown in the unit and
make the unit object self-declare the `(raw_hash, tool_profile_hash, gen)` of
another live tree entry. Rebuild accepts the unit, chunking persists the forged
identity, and the search join associates the text with that other entry. This
is the route that most directly threatens Evidence users because the result can
look like a normal chunk from a normal path.

The second route is silent exclusion or substitution within the requested
document. We place arbitrary markdown under the requested instance and keep the
self-declared identity aligned enough to join the same live tree entry, while
breaking the manifest entry, unit reference, or prepared-hash relation that
should have tied the markdown to the prepared unit. The system can then index
content that was never produced by the expected normalization pipeline. If the
forged tuple fails the live join, the poisoned row is filtered instead, causing
missing search coverage rather than visible false text.

Several constraints keep this at Medium severity. There is no public listener
and no unauthenticated remote parser in the validated path. The contributor
must influence the persisted store before the operator adopts it, know the
public schema well enough to create parse-valid JSON, and wait for the operator
to run rebuild, index, repair, search, or Evidence workflows. Directly modifying
an already-private live store as the same OS user would not be an interesting
security boundary; the security-relevant boundary here is the lower-trust
archive contributor crossing into the operator's trusted local search and
Evidence state.

The controls that exist are real but not sufficient. Directory construction
uses the requested tuple, typed deserialization rejects malformed JSON, and
later search/Evidence joins prevent some inconsistent rows from surfacing.
None of those controls rebinds the normalized source. We need a fail-closed
check before `NormalizedUnitInput` is created, because that is the last point
where KCS still has both the request tuple and the serialized manifest/unit
contents in one place.

## Proof of Concept

The included PoC is a local synthetic regression probe. It does not open a real
KCS store, does not use credentials, and does not contact any external system.
Instead, it models the reader boundary with a deliberately mismatched
manifest/unit pair and compares the current permissive behavior with the
expected strict rebinding rule.

From this report directory:

```sh
cd poc
make
```

Representative output:

```text
[+] built synthetic normalized instance for requested tuple sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa / sha256:1111111111111111111111111111111111111111111111111111111111111111 / g7
[+] vulnerable reader accepted 1 done unit(s)
[+] accepted unit identity: raw_hash=sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb tool_profile_hash=sha256:2222222222222222222222222222222222222222222222222222222222222222 gen=99 unit_key=page:99
[+] strict rebinding rejected the same files:
    - manifest.raw_hash does not match requested raw_hash
    - manifest.tool_profile_hash does not match requested tool_profile_hash
    - manifest.gen does not match requested gen
    - unit_ref filename is not derived from unit.unit_key
    - unit.raw_hash does not match requested raw_hash
    - unit.tool_profile_hash does not match requested tool_profile_hash
    - unit.gen does not match requested gen
    - unit.unit_key does not match manifest entry
    - unit.prepared_hash does not match manifest entry
```

The probe is intentionally diagnostic. It demonstrates the exact invariant KCS
should enforce without building a poisoned production archive or asking a user
to run a search against live data.

## Remediation

The invariant to restore is: every consumed normalized unit must be proven to
belong to the requested normalized instance before its markdown is indexed.
The reader should treat any mismatch as store corruption and skip or fail
closed before chunking.

A minimal defensive pattern is to validate the request against the manifest,
then validate each manifest entry against the unit object before constructing
`NormalizedUnitInput`:

```rust
if manifest.raw_hash != raw_hash
    || manifest.tool_profile_hash != tool_profile_hash
    || manifest.gen != gen
{
    return Err(store_corrupt_error(
        &manifest_path,
        "normalized manifest identity does not match requested instance",
    ));
}

for entry in &manifest.units {
    if entry.status != UnitStatus::Done {
        continue;
    }
    if entry.unit_ref != unit_ref(&entry.unit_key) {
        return Err(store_corrupt_error(
            &manifest_path,
            "manifest unit_ref does not match unit_key",
        ));
    }

    let unit_path = dir.join(format!("{}.json", entry.unit_ref));
    let unit: NormalizedUnitObject = read_unit(&unit_path)?;
    if unit.raw_hash != raw_hash
        || unit.tool_profile_hash != tool_profile_hash
        || unit.gen != gen
        || unit.unit_key != entry.unit_key
        || unit.unit_type != entry.unit_type
        || unit.prepared_hash != entry.prepared_hash
    {
        return Err(store_corrupt_error(
            &unit_path,
            "normalized unit identity does not match manifest entry",
        ));
    }
}
```

The exact helper names can follow the local style, but the important point is
that the comparison happens before `chunk_normalized_instance()` receives any
unit text. Regression tests should cover:

- manifest `raw_hash`, `tool_profile_hash`, and `gen` mismatches;
- `entry.unit_ref` that is not derived from `entry.unit_key`;
- unit `raw_hash`, `tool_profile_hash`, `gen`, `unit_key`, `unit_type`, and
  `prepared_hash` mismatches;
- a poisoned unit that would otherwise join a different live tree entry;
- a mismatch during `repair --rebuild-db` so recovery skips or reports only the
  corrupt document rather than silently accepting the poisoned unit.

It is also worth adding a small structured corruption reason to the existing
`skipped_units` report. That keeps rebuild behavior operator-friendly while
making the provenance failure auditable.

## Summary

We traced a copied-store integrity bug from the tree rebuild caller through
`load_normalized_units()`, into chunk construction, and then into search and
Evidence consumers. The decisive issue is not malformed JSON or path traversal;
it is a missing semantic binding between the requested normalized instance and
the parse-valid manifest/unit objects found at that path.

The local PoC shows that a mismatched manifest and unit can be accepted by the
current reader model while a strict rebinding check rejects the same files. The
fix is correspondingly direct: compare the complete requested tuple, manifest
identity, manifest entry, derived `unit_ref`, and unit object before any
markdown is reused or indexed. Variant analysis should look for other cache
readers that convert persisted state into trusted search, Evidence, or repair
state before checking that the serialized object still belongs to the caller's
requested provenance tuple.
