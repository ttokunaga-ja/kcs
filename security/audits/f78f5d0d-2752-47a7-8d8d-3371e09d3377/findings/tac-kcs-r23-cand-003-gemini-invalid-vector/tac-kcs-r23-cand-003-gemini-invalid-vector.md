# Gemini embedding vectors accept invalid numeric-domain states

## Executive Summary

KCS revision `0e19f3c6489da458e93a982a333c308d92d0a0ae` accepts Gemini
embedding response vectors after checking only JSON shape, response count, and
vector width. It does not validate that each component remains finite after
the `f64` to `f32` narrowing step, and it does not require a positive finite
norm before the vector is used for cosine search or persisted as authoritative
embedding state.

The affected versions are the target revision and any build that keeps this
same parser/store shape. I did not identify or review a fixing revision, and I
did not call a live Gemini endpoint; I reviewed the vulnerable source directly
and used local synthetic probes to validate the numeric behavior and the
expected rejection invariant.

The practical attack boundary is a configured remote embedding service after
the KCS operator has approved online embedding. A malicious, compromised, or
faulty service can return an exact-width vector containing a finite JSON number
such as `3.5e38`, which narrows to `f32::INFINITY`, or an exact-width all-zero
vector. The query path can fail the current vector/hybrid search, and the
batch path can persist the malformed vector so later vector searches for that
scope continue to fail. The validated impact is a scope-limited vector-index
denial of service, not credential disclosure or remote code execution. I rate
this as Medium severity, P2 priority.

## Background

KCS is local-first, but it can opt into online adapters for expensive
operations such as embedding Markdown chunks or a search query. Once the user
authorizes an online Gemini embedding operation, KCS sends text to the
configured service and treats the returned numeric vector as the semantic
representation for a query or for a content-addressed chunk embedding.

For cosine search, the important invariant is stronger than "the vector has
the right width." Every component must be finite in the stored `f32` domain,
and the vector must have a positive finite norm. If we carry `inf`, `NaN`, or
an all-zero vector into a cosine backend, the distance calculation no longer
has a meaningful finite result. Width validation protects only the byte layout
expected by `chunk_vec`; it does not protect the numeric domain that cosine
requires.

The Gemini HTTP implementation parses a JSON response from the remote service
and immediately delegates to the shared parser:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs, EnvGeminiEmbeddingClient::embed
let response: Value = ureq::post(&format!(
    "{}/v1beta/models/{model_pin}:batchEmbedContents",
    self.base_url()
))
.set("x-goog-api-key", &api_key)
.set("Content-Type", "application/json")
.send_json(json!({ "requests": requests }))
.map_err(http_error)?
.into_json()
.map_err(|err| AdapterError::ContractViolation(err.to_string()))?;
parse_embeddings(&response, items, dimensions)
```

From this point onward, the remote response has crossed into local trusted
indexing state. We therefore need parser-level validation before any vector is
returned to the query path or converted into the `embeddings` and `chunk_vec`
stores.

## Vulnerability Details

The vulnerable parser narrows every JSON number from `f64` to `f32`, then
checks only the vector length:

```rust
// crates/kcs-adapter/src/gemini_embedding.rs, parse_embeddings
let vector = embedding
    .get("values")
    .and_then(Value::as_array)
    .ok_or_else(|| {
        AdapterError::ContractViolation("embedding missing values".to_owned())
    })?
    .iter()
    .map(|value| value.as_f64().map(|value| value as f32))
    .collect::<Option<Vec<f32>>>()
    .ok_or_else(|| {
        AdapterError::ContractViolation("embedding values must be numeric".to_owned())
    })?;
if vector.len() != dimensions as usize {
    return Err(AdapterError::ContractViolation(format!(
        "embedding dimension mismatch: expected {dimensions}, got {}",
        vector.len()
    )));
}
```

This code rejects non-numeric JSON values and wrong-width arrays, which are
useful checks, but they stop short of the security invariant. JSON syntax also
rejects literal `NaN` and `Infinity`, but that does not save us: a finite JSON
`f64` outside the `f32` range is still syntactically valid, and the Rust
narrowing step turns it into an infinite `f32`. If we use `3.5e38`, the source
number is finite as JSON/f64 input and the stored component is not finite after
the cast. An all-zero exact-width array also passes because no norm check runs.

The query path returns the adapter vector unchanged:

```rust
// crates/kcs-cli/src/main.rs, compute_query_embedding
match run_embedding_adapter(execution, items, EmbeddingInputType::Query) {
    Ok(vectors) => Ok(vectors.into_iter().next().map(|vector| vector.vector)),
    Err(_) => Ok(None),
}
```

When we carry the same accepted vector into batch indexing, KCS serializes the
`f32` values to raw little-endian bytes and writes them as a successful chunk
embedding:

```rust
// crates/kcs-cli/src/main.rs, send_embed_batch
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
```

The store preserves the same gap. It inserts the blob as the source of truth
and links it to `chunk_vec` when the byte width and declared dimension match:

```rust
// crates/kcs-index/src/embedding_store.rs, write_chunk_embedding/link_chunk_vec
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

if dimensions as usize != CHUNK_VEC_DIMENSIONS || vector.len() != CHUNK_VEC_DIMENSIONS * 4 {
    return Ok(());
}
conn.execute(
    "INSERT INTO chunk_vec(chunk_id, embedding) VALUES (?1, ?2)",
    params![chunk_id, vector],
)?;
```

Finally, the KNN consumer also validates only the query byte width before
handing both stored and query vectors to sqlite-vec, then decodes each returned
distance as `f64`:

```rust
// crates/kcs-index/src/embedding_store.rs, knn_chunk_distances
if query_vector.len() != CHUNK_VEC_DIMENSIONS * 4 {
    return Err(IndexError::Contract(
        "KCS-E-SEARCH-VEC-INCOMPAT-001: query vector width mismatch".to_owned(),
    ));
}
let mut stmt = conn.prepare(
    "SELECT chunk_id, distance FROM chunk_vec
     WHERE embedding MATCH ?1 ORDER BY distance LIMIT ?2",
)?;
let rows = stmt.query_map(params![query_vector, k as i64], |row| {
    Ok((row.get::<_, String>(0)?, row.get::<_, f64>(1)?))
})?;
```

The failure mode is therefore not confined to a parser return value. We accept
the malformed vector at the remote boundary, serialize it exactly, make it
authoritative for the chunk, and later ask a cosine KNN backend for a distance
that may be undefined. The local validation probe for this finding observed a
finite `3.5e38` source narrowing to `inf`, the non-finite component round
tripping from storage, and sqlite-vec returning a NULL distance that KCS failed
to decode as `f64`. The same probe showed an exact-width zero vector producing
the same KNN failure, while a finite basis-vector control returned distance
`0.0`.

## Exploitability Analysis

The strongest route is persistent poisoning through batch embedding. We start
with an operator-approved online embedding operation. The remote service
controls `embeddings[*].values[]`, so it can return the expected response
count and exactly `768` values per item. If one component is `3.5e38`, the
JSON value remains finite at the network/parser boundary, the vulnerable cast
turns it into `f32::INFINITY`, and the width check passes. If every component
is `0.0`, the vector is also exact-width and numeric, but its cosine norm is
zero. In both cases, the task can be treated as successfully embedded, and the
resulting bytes become local source-of-truth state.

Once we have a stored malformed vector, the attack is durable. Rebuilding the
derived vector table reads stored embeddings and links width-compatible blobs
back into `chunk_vec`; it does not recover by calling the adapter again or by
revalidating component semantics. That means one bad approved response can
outlive the triggering batch and continue affecting later vector/hybrid
searches for the same scope until the poisoned embedding row is removed or
rewritten.

The transient query route is narrower but still useful. If the service returns
an invalid query vector, `compute_query_embedding()` passes it to the vector
search path for the current search. KCS has a specific degradation path for
sqlite-vec capacity failures, but this NULL-distance decode is a different
backend error. As implemented, non-capacity vector errors become fatal for the
scope rather than cleanly falling back to the already-computed text ranks.

The main constraints keep the severity at Medium. KCS does not expose an
inbound listener here; the operator must opt into online embedding, and a
well-behaved official provider is expected to return finite normalized
vectors. The issue becomes directly attacker-controlled when the configured
remote endpoint is malicious, compromised, misdirected, or faulty. The defect
also does not disclose the Gemini API key: the key is used for the approved
outbound request, but the malformed response does not redirect it. Text-only
search remains an online-independent fallback, so the demonstrated impact is
availability and integrity of vector ranking for affected scopes, not loss of
the whole local archive.

Two exploitation details are worth preserving. First, literal JSON `NaN` or
`Infinity` is a dead end because JSON parsing rejects those tokens, so an
attacker should use finite over-range numbers if they want non-finite `f32`
state. Second, a zero vector does not rely on overflow at all; it stays finite
but still violates cosine's positive-norm invariant. A complete fix therefore
needs both component finiteness and positive finite norm checks.

## Proof of Concept

The included PoC is a local offline model of the vulnerable invariant. It uses
a four-dimensional synthetic vector for readability, but it exercises the same
properties that matter in KCS: numeric JSON values are accepted, narrowed to
`f32`, checked only for width, and then evaluated as cosine vectors. It does
not contact Gemini, require credentials, load sqlite-vec, or modify a KCS
repository.

From the report directory:

```sh
cd poc
make
```

Representative output:

```text
[overflow] source f64 finite: True
[overflow] vulnerable parser accepted: yes
[overflow] first f32 component: inf
[overflow] all components finite after cast: False
[overflow] squared norm: inf
[overflow] cosine distance result: NULL
[overflow] hardened validator: rejected (vector component is not finite after f32 narrowing)
[zero] vulnerable parser accepted: yes
[zero] first f32 component: 0.0
[zero] all components finite after cast: True
[zero] squared norm: 0.0
[zero] cosine distance result: NULL
[zero] hardened validator: rejected (vector norm must be positive and finite)
[control] vulnerable parser accepted: yes
[control] first f32 component: 1.0
[control] all components finite after cast: True
[control] squared norm: 1.0
[control] cosine distance result: 0.0
[control] hardened validator: accepted
```

This PoC is intentionally bounded. It demonstrates the parser and vector-domain
failure with synthetic data, while the KCS-specific validation for this finding
confirmed the same overflow and zero-norm cases against local storage and KNN
behavior.

## Remediation

Restore the invariant at every boundary that can introduce or revive embedding
bytes: a cosine vector is valid only if it has the expected dimension, every
component is finite after `f32` conversion, and its squared norm is positive
and finite. The primary fix should live immediately after parsing, before
`EmbeddingVector` is returned to callers, because that protects both query and
batch paths. The store and rebuild paths should also reject legacy invalid
blobs so old poisoned rows cannot be relinked indefinitely.

A minimal parser-side shape would look like this:

```rust
fn validate_cosine_vector(vector: &[f32], dimensions: u32) -> Result<()> {
    if vector.len() != dimensions as usize {
        return Err(AdapterError::ContractViolation(format!(
            "embedding dimension mismatch: expected {dimensions}, got {}",
            vector.len()
        )));
    }
    if vector.iter().any(|value| !value.is_finite()) {
        return Err(AdapterError::ContractViolation(
            "embedding values must be finite f32 values".to_owned(),
        ));
    }
    let norm_sq: f32 = vector.iter().map(|value| value * value).sum();
    if !norm_sq.is_finite() || norm_sq <= 0.0 {
        return Err(AdapterError::ContractViolation(
            "embedding vector must have a positive finite norm".to_owned(),
        ));
    }
    Ok(())
}
```

For the store, decode `vector: &[u8]` into `f32` values and apply the same
finite-component and positive-norm predicate before inserting into
`embeddings`, before linking `chunk_vec`, and during rebuild/reuse of legacy
rows. Invalid legacy rows should be reported clearly and excluded from KNN
until they are regenerated.

Regression coverage should include:

- a Gemini response containing a finite over-range JSON value such as
  `3.5e38`, proving it is rejected after narrowing;
- an exact-width all-zero response, proving the positive-norm check runs;
- a normal finite basis vector, proving valid vectors still pass;
- query embedding, batch persistence, reuse, and rebuild paths, proving no
  alternate caller can reintroduce invalid stored bytes;
- a legacy invalid embedding row, proving repair/rebuild excludes it instead
  of relinking it into `chunk_vec`.

## Summary

The bug is a classic numeric-domain validation gap at a trust boundary. KCS
correctly checks that the Gemini response has the expected shape and width, but
it does not check that the resulting `f32` vector is valid for cosine search.
Because we can carry a finite over-range JSON number into `f32::INFINITY`, or
carry an exact-width zero vector into cosine search, a remote embedding
response can create undefined distance behavior.

The most important consequence is durability. Query poisoning can break one
vector search, but batch poisoning can persist malformed bytes as authoritative
chunk embedding state and keep affecting later vector/hybrid searches. Future
variant analysis should look for other embedding adapters, import paths, or
rebuild/reuse helpers that accept width-correct vector bytes without enforcing
the same finite-domain and positive-norm invariant.
