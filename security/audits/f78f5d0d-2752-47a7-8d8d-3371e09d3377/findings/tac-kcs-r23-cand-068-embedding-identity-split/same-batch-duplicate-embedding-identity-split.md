# Same-batch duplicate embedding identities split authoritative and KNN vectors

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
can store two different vectors for duplicate chunk content when the duplicate
chunks are first embedded in the same batch. The content-addressed
`embeddings` row keeps the first vector for the shared embedding identity, but
the derived `chunk_vec` KNN row for each chunk is linked from that chunk's
current adapter response. If a faulty, variable, compromised, or malicious
embedding adapter returns different valid vectors for identical text in the
same request, KCS can rank one duplicate chunk with bytes that do not match the
authoritative content vector.

The final impact is Medium/P2: we do not get code execution, credential
disclosure, or an authorization bypass, but we can corrupt vector-search and
evidence-selection integrity inside the affected scope until a rebuild or
repair relinks the derived rows. I reviewed the vulnerable revision directly,
checked the saved validation and attack-path reports, and ran the included
network-free Python harness; I did not contact any external embedding service
or live KCS deployment.

## Background

KCS stores embeddings in two related places. The `embeddings` table is the
content-addressed source of truth. Its identity is derived from the chunk text
hash and embedding profile, not from the chunk ID:

```rust
pub fn embedding_hash(
    target_type: EmbeddingTargetType,
    target_hash: &str,
    dimensions: u64,
    distance: EmbeddingDistance,
    modality: EmbeddingModality,
    profile_hash: &str,
) -> Result<String> {
    let value = json!({
        "dimensions": dimensions,
        "distance": distance_name(distance),
        "modality": modality_name(modality),
        "profile_hash": profile_hash,
        "spec_version": 1,
        "target_hash": target_hash,
        "target_type": target_type_name(target_type),
    });
    hash_jcs(&value)
}
```

That design is useful: unchanged content can reuse a vector without sending the
same text to an adapter again. The KNN acceleration table, `chunk_vec`, is a
derived projection keyed by `chunk_id`. Normal search reads `chunk_vec`, while
reuse and rebuild paths read the authoritative `embeddings` vector.

The important wrinkle is that two chunks can be different chunks while sharing
the same text. `chunk_hash` includes raw-file and chunk-position identity, so
the same text copied into two files or sections can keep distinct `chunk_id`
values while sharing the same content text hash:

```rust
pub fn chunk_hash(row: &ChunkRow) -> Result<String> {
    let mut map = Map::new();
    map.insert("char_end".to_owned(), json!(row.char_end.unwrap_or(0)));
    map.insert("char_start".to_owned(), json!(row.char_start.unwrap_or(0)));
    map.insert("gen".to_owned(), json!(row.gen));
    map.insert(
        "heading_path".to_owned(),
        json!(row.heading_path.clone().unwrap_or_default()),
    );
    map.insert("raw_hash".to_owned(), json!(row.raw_hash));
    // ...
    map.insert("unit_key".to_owned(), json!(row.unit_key));
    hash_jcs(&Value::Object(map))
}
```

We therefore need KCS to enforce one canonical vector per content/profile
identity, even when several distinct chunks with that identity appear together
for the first time.

## Vulnerability Details

The vulnerable path begins in batch planning. `plan_embed_batch` walks every
chunk in the current batch, computes its content-addressed embedding hash, and
looks for an existing authoritative vector:

```rust
fn plan_embed_batch<'a>(
    conn: &Connection,
    profile: &DeclaredEmbeddingProfile,
    batch: &'a [EmbeddableChunk],
) -> std::result::Result<EmbedBatchPlan<'a>, TaskExecutionFailure> {
    let mut reuse = Vec::new();
    let mut to_send = Vec::new();
    for chunk in batch {
        let embedding_hash =
            chunk_embedding_hash(chunk, profile).map_err(|_| TaskExecutionFailure {
                retry_kind: RetryErrorKind::ContractViolation,
            })?;
        match embedding_store::content_vector(conn, &embedding_hash) {
            Ok(Some(bytes)) => reuse.push((chunk, bytes)),
            Ok(None) => to_send.push((chunk, embedding_hash)),
            Err(_) => {
                return Err(TaskExecutionFailure {
                    retry_kind: RetryErrorKind::ContractViolation,
                })
            }
        }
    }
    Ok(EmbedBatchPlan { reuse, to_send })
}
```

This is an all-read phase. If two same-text chunks are both absent before the
batch starts, we classify both as misses. There is no grouping by
`embedding_hash`, so we send both chunks to the adapter even though they need
the same authoritative vector.

`send_embed_batch` then calls the adapter and indexes returned vectors by
`chunk_id`:

```rust
let vectors = run_embedding_adapter(execution, items, EmbeddingInputType::MarkdownChunk)?;
let by_id = vectors
    .into_iter()
    .map(|vector| (vector.id, vector.vector))
    .collect::<BTreeMap<_, _>>();
for (chunk, embedding_hash) in to_send {
    let Some(vector) = by_id.get(&chunk.chunk_id) else {
        return Err(TaskExecutionFailure {
            retry_kind: RetryErrorKind::ContractViolation,
        });
    };
    let bytes = f32_to_le_bytes(vector);
    embedding_store::write_chunk_embedding(
        conn,
        embedding_hash,
        &chunk.text_hash,
        &chunk.chunk_id,
        &bytes,
        profile.dimensions,
        &profile.distance,
        &profile.modality,
        &profile.profile_hash,
    )
    .map_err(|_| TaskExecutionFailure {
        retry_kind: RetryErrorKind::ContractViolation,
    })?;
}
```

If we carry duplicate text through this loop, the adapter response for each
duplicate is still treated as a separate current vector. The storage routine
has the invariant documented in its comment: `embeddings` is the source of
truth and `chunk_vec` is its derived KNN copy. The implementation preserves the
first source-of-truth vector but links the derived row from the current vector:

```rust
pub fn write_chunk_embedding(
    conn: &Connection,
    embedding_hash: &str,
    text_hash: &str,
    chunk_id: &str,
    vector: &[u8],
    dimensions: u64,
    distance: &str,
    modality: &str,
    profile_hash: &str,
) -> Result<()> {
    conn.execute(
        "INSERT INTO embeddings(id, target_type, target_id, modality, vector, dimensions, distance, profile_hash)
         VALUES (?1, 'chunk', ?2, ?3, ?4, ?5, ?6, ?7)
         ON CONFLICT(id) DO NOTHING",
        params![
            embedding_hash,
            text_hash,
            modality,
            vector,
            dimensions as i64,
            distance,
            profile_hash
        ],
    )?;
    link_chunk_vec(conn, chunk_id, vector, dimensions)?;
    Ok(())
}
```

For the first duplicate, the `INSERT` creates the authoritative vector and
`link_chunk_vec` copies the same bytes into `chunk_vec`. For the second
duplicate, `ON CONFLICT(id) DO NOTHING` correctly preserves the first
authoritative row, but `link_chunk_vec` still receives the second response's
bytes. We now have one content identity with two derived KNN projections: one
chunk matches the source of truth and the other does not.

The rebuild path proves why that mismatch is a real integrity problem rather
than a harmless duplicate write. Rebuild deletes `chunk_vec`, joins chunks back
to `embeddings` by text hash, and relinks from the authoritative vector:

```rust
conn.execute_batch("DELETE FROM chunk_vec;")?;
let mut stmt = conn.prepare(
    "SELECT c.chunk_id, e.vector, e.dimensions
     FROM chunks c
     JOIN embeddings e ON e.target_type = 'chunk' AND e.target_id = c.text_hash",
)?;
// ...
for (chunk_id, vector, dimensions) in rows {
    if held_chunk_ids.contains(&chunk_id) {
        continue;
    }
    link_chunk_vec(conn, &chunk_id, &vector, dimensions)?;
}
```

After repair, both duplicate chunks converge to the first vector. Before
repair, search used the second chunk's adapter-supplied vector. That means KCS
can make different nearest-neighbor and evidence-selection decisions for the
same indexed content depending on whether a repair has happened.

## Exploitability Analysis

The attacker boundary is the approved outbound embedding workflow. KCS has no
inbound listener here, so the realistic actor is the configured embedding
adapter or a service behind that adapter. The KCS user authorizes the adapter
request, but KCS is still responsible for making the local content-addressed
store internally consistent once untrusted response bytes come back.

The strongest route is straightforward:

1. We arrange or wait for a batch containing two distinct chunks with identical
   text under the same profile. This can occur naturally when duplicated
   content appears in separate files or sections.
2. Because both entries are probed before any write, both miss and are sent to
   the adapter.
3. The adapter recognizes that it received duplicate text and returns two
   dimension-valid but non-identical vectors, one per chunk ID.
4. KCS stores the first vector in `embeddings`, ignores the conflicting second
   source-of-truth insert, and still links the second chunk's KNN row from the
   second vector.
5. Until rebuild, KNN search and any downstream evidence selection that depends
   on `chunk_vec` can rank the duplicate chunks as though they represented
   different semantic content.

This is not a confidentiality primitive. The configured adapter already sees
the outbound text that the user allowed KCS to send, and the saved attack-path
analysis found no credential disclosure or destination rewrite. It is also not
stronger than the adapter's general ability to provide bad embeddings for any
one item. The incremental security issue is narrower and more precise: the
local source-of-truth row and the local derived search row disagree for the same
content identity, so KCS loses the invariant that repair, reuse, and search all
operate on the same canonical vector.

Stable deterministic adapters reduce likelihood because equal text normally
gets equal or near-equal vectors. They do not remove the bug. A compromised or
faulty adapter can choose divergent vectors while satisfying the existing
response count and dimension checks, and nondeterministic providers can
accidentally create the same shape of inconsistency. The path is easiest to
observe when vector search is used before rebuild; after rebuild, both chunks
are relinked from the first authoritative vector, which both repairs the local
state and exposes that earlier search ordering was repair-dependent.

## Proof of Concept

The included PoC is a network-free regression harness. It does not call an
embedding provider, use credentials, or modify a repository checkout. Instead,
it models the exact KCS storage invariant from the vulnerable source: an
all-read batch planner, a first-wins authoritative `embeddings` row, and a
per-chunk `chunk_vec` link from the current response vector.

Run it from the report directory:

```sh
cd poc
python3 duplicate_embedding_split.py
```

Representative output:

```json
{
  "bounded": true,
  "duplicate_embedding_id": true,
  "planned_duplicate_misses": true,
  "vulnerable": {
    "authoritative_kept_first": true,
    "chunk_a_matches_first": true,
    "chunk_b_matches_second": true,
    "chunk_b_conflicts_with_authoritative": true,
    "rebuild_changes_chunk_b": true
  },
  "fixed": {
    "one_adapter_item_for_duplicate_identity": true,
    "both_chunks_link_authoritative": true,
    "conflicting_duplicate_rejected": true
  }
}
```

The `vulnerable` block demonstrates the saved finding: chunk B is linked to the
second response even though the authoritative row kept the first response. The
`fixed` block demonstrates the regression property we want after remediation:
same-identity batch members share one canonical vector, both chunks link from
that vector, and a conflicting duplicate response is rejected instead of being
partially accepted.

## Remediation

The invariant to restore is simple: for one `(text_hash, profile)` embedding
identity, KCS must persist exactly one canonical vector and every derived
`chunk_vec` row for that identity must be linked from those persisted bytes.
The batch code should group duplicate misses before adapter dispatch, send one
item per embedding identity, and then fan the persisted vector out to every
member chunk.

A minimal pattern is:

```rust
// During planning, group same-identity misses.
let mut grouped: BTreeMap<String, Vec<&EmbeddableChunk>> = BTreeMap::new();
for chunk in batch {
    let embedding_hash = chunk_embedding_hash(chunk, profile)?;
    if let Some(bytes) = embedding_store::content_vector(conn, &embedding_hash)? {
        reuse.push((chunk, bytes));
    } else {
        grouped.entry(embedding_hash).or_default().push(chunk);
    }
}

// Send one representative per embedding_hash, persist once, then link members
// from the persisted source-of-truth vector.
for (embedding_hash, chunks) in grouped {
    let representative = chunks[0];
    let vector = adapter_vector_for(&representative.chunk_id)?;
    embedding_store::write_chunk_embedding(
        conn,
        &embedding_hash,
        &representative.text_hash,
        &representative.chunk_id,
        &vector,
        profile.dimensions,
        &profile.distance,
        &profile.modality,
        &profile.profile_hash,
    )?;
    let canonical = embedding_store::content_vector(conn, &embedding_hash)?
        .ok_or(TaskExecutionFailure { retry_kind: RetryErrorKind::ContractViolation })?;
    for chunk in chunks {
        embedding_store::link_chunk_vec(conn, &chunk.chunk_id, &canonical, profile.dimensions)?;
    }
}
```

If the adapter contract continues to return one vector per original chunk,
KCS should compare same-identity responses before committing state. Equal
identities with conflicting vectors should fail atomically rather than leaving
`embeddings` and `chunk_vec` split. The regression tests should cover:

- two identical texts in the same first-seen batch;
- the same path with a malicious adapter returning different valid vectors;
- a reuse path where an authoritative vector already exists before planning;
- rebuild parity, asserting pre-rebuild and post-rebuild `chunk_vec` bytes are
  identical for every chunk sharing the same text hash;
- nearby dimension and response-count contract failures.

## Summary

KCS already has the right high-level design: a content-addressed authoritative
embedding row and a derived KNN projection. The bug is that same-batch duplicate
misses bypass the single-vector invariant. We first classify every duplicate as
a miss, then preserve only the first source-of-truth vector while linking each
chunk from its own current adapter response. A remote adapter that returns
conflicting vectors for duplicate text can therefore create repair-dependent
search and evidence-selection results.

The fix is to make the content identity the unit of work throughout planning,
adapter response validation, persistence, and derived linking. Variant analysis
should look for other places where KCS has an authoritative content-addressed
object plus a derived acceleration table; those paths need the same "derive
from the persisted canonical object" rule.
