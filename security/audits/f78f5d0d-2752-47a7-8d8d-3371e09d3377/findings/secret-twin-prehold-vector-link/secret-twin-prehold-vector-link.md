# Secret-labeled content twins can be vector-linked before their hold exists

| Field | Value |
| --- | --- |
| Severity | Medium |
| Priority | P2 |
| Weakness | CWE-863 (closest fit: incorrect authorization of a derived search state) |
| Confirmed revision | `0e19f3c6489da458e93a982a333c308d92d0a0ae` |
| Fixed revision | Not identified |
| Affected component | Index rebuild, embedding hold lifecycle, and vector search projection |

## Executive Summary

KCS can make a newly added, secret-labeled chunk visible to local vector and
hybrid search before it creates the chunk's `secrets_tier_b_hold` task. The
condition arises when an already embedded public chunk and the new secret
chunk have the same normalized text but different chunk identities. KCS
correctly reuses one authoritative embedding for equal text. The security
failure is in when it creates the derived `chunk_vec` link: the index rebuild
runs before embedding enrichment creates holds, while the rebuild's denylist
contains only chunk IDs that already have a persisted hold task.

Once the rebuild has linked the new secret chunk to the public twin's vector,
the later enrichment pass treats that chunk as complete. It skips the chunk
before current-path secret classification, so the missing hold never catches
up. A vector search can then return the secret document's path, heading,
raw-document identity, and Evidence Pointer even though the user has not
approved secret embedding with `--send-secrets`.

The confidentiality impact is important but bounded. The linked chunk's text
is byte-identical to text that was already embedded from a public document,
and this path does not send the new secret document or credentials to an
external service. The additional information is the association between that
text and the secret-labeled document, including its path and provenance, plus
the loss of the expected hold/audit record. This matters to callers that rely
on the hold policy to keep secret-labeled provenance out of semantic results,
but it is not arbitrary-file disclosure or a cross-user operating-system
boundary bypass. Those facts support Medium severity and P2 priority.

I reviewed revision `0e19f3c6489da458e93a982a333c308d92d0a0ae`
directly and ran the included harmless probe with synthetic files, isolated
temporary HOME/XDG state, and KCS's in-process deterministic embedding seam. I
observed the missing hold and vector result without network access, credentials,
or an existing user store. I did not test a fixed revision because none was
available, and I did not rebuild every historical revision. Git history shows
that the constituent embedding/rebuild ordering predates the confirmed
revision and that secret embedding holds were present by commit
`4e77b87e3997f3976e94e55d3c841a96a55db68d`; the exact affected release range
should therefore be confirmed by maintainers rather than inferred from this
single-revision validation.

## Background

KCS is a local-first CLI that normalizes documents into chunks and maintains
two related vector stores in SQLite:

- `embeddings` is authoritative and content-addressed. A chunk embedding is
  keyed by the chunk's `text_hash` and embedding profile, so equal text can
  reuse a single vector.
- `chunk_vec` is a derived KNN projection. It maps each provenance-bearing
  `chunk_id` to the vector that search should consider for that chunk.

This distinction is deliberate and useful. Two chunks may have different raw
documents, headings, positions, and `chunk_id` values while sharing the same
normalized text and `text_hash`. We want to reuse the expensive vector, but we
must still decide independently whether each chunk identity is eligible for
vector search.

Secret handling adds that per-chunk policy decision. The current classifier
treats names containing words such as `credentials`, `secret`, `token`,
`apikey`, or `password` as Tier B:

```rust
// crates/kcs-pipeline/src/scan.rs:235-274, classify_secret
let tier_b = ["credentials", "secret", "token", "apikey", "password"]
    .iter()
    .any(|needle| lower.contains(needle));
tier_b.then_some(SecretTier::TierB)
```

Without a current `--send-secrets` approval, embedding enrichment should place
each such live chunk in a Paused task whose reason is
`secrets_tier_b_hold`. The hold has two related roles: it gives operators and
automation durable evidence that the chunk is intentionally blocked, and its
chunk ID is excluded from the derived vector index. After explicit approval,
KCS releases the hold and a later rebuild may link or generate the vector.

The intended invariant can be stated compactly:

```text
live secret path AND no current secret approval
    => persisted hold exists
    => chunk_id is absent from chunk_vec
```

The vulnerability breaks both conclusions for a new content twin because the
derived-vector decision consults the persisted task projection before the
current document has had an opportunity to create that task.

## Vulnerability Details

### The rebuild precedes hold creation

We first follow the normal `kcs index` command. After snapshot publication, it
rebuilds the Step 3 index and only then runs embedding enrichment:

```rust
// crates/kcs-cli/src/main.rs:647-652, run_index
let rebuild_report = rebuild_step3_index(&repo)?;
// Generate chunk embeddings behind the online opt-in / budget / cost-ledger
// guardrails ...
let enrichment = generate_scope_embeddings(&repo, &args)?;
```

This ordering means a newly materialized chunk is already present in the fresh
SQLite `chunks` table when `chunk_vec` is rebuilt, but it cannot yet have an
embedding task from this indexing pass. The later call to
`generate_scope_embeddings` is where KCS selects pending chunks, partitions
secret paths, and calls `hold_secret_embedding_tasks`.

### The rebuild denylist represents yesterday's policy state

The nearest control is `held_secret_embedding_chunk_ids`. It reads the task
store and returns only embedding tasks that are already Paused for the exact
secret-hold reason:

```rust
// crates/kcs-cli/src/main.rs:3008-3027
fn held_secret_embedding_chunk_ids(kcs_dir: &Path) -> Result<BTreeSet<String>> {
    let task_store = TaskStore::new(kcs_dir);
    Ok(task_store
        .all()
        .map_err(pipeline_to_kcs)?
        .into_iter()
        .filter(|task| {
            task.task_type == TaskType::Embedding
                && task.status == TaskStatus::Paused
                && task.fallback_reason.as_deref() == Some(SECRETS_TIER_B_HOLD)
        })
        .filter_map(|task| {
            task.output_ref
                .strip_prefix("embedding:")
                .map(str::to_owned)
        })
        .collect())
}
```

The fresh-database builder passes exactly that set to the vector rebuild:

```rust
// crates/kcs-cli/src/main.rs:3655-3658, build_sqlite_index_at
let held_chunk_ids = held_secret_embedding_chunk_ids(kcs_dir)?;
embedding_store::rebuild_chunk_vec(fts.connection(), &held_chunk_ids)
    .map_err(index_to_kcs)?;
```

This control works for a hold created on an earlier run. It cannot describe a
new secret chunk because the task does not exist yet. The task store is a
durable workflow projection, not the authoritative current secret
classification, so using it as the only rebuild policy source creates a
time-of-state gap even though the index command itself is serialized.

### Content reuse fills the gap

We now carry the new chunk into `rebuild_chunk_vec`. The function clears the
derived table, joins every stored chunk to an authoritative embedding by
`text_hash`, and skips only IDs present in the task-derived set:

```rust
// crates/kcs-index/src/embedding_store.rs:160-184
pub fn rebuild_chunk_vec(
    conn: &Connection,
    held_chunk_ids: &std::collections::BTreeSet<String>,
) -> Result<()> {
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
    Ok(())
}
```

Suppose the public chunk is `C_public`, the new secret chunk is `C_secret`, and
both carry text hash `T`. The existing `embeddings` row is `E(T)`. Because
`C_secret` is not yet in `held_chunk_ids`, this join creates
`chunk_vec(C_secret, E(T))` without generating a new vector or making an
adapter call.

That gives us the following deterministic state transition:

| Stage | Authoritative and policy state |
| --- | --- |
| Public index | `E(T)` exists; `chunk_vec(C_public)` exists; the public task is Done. |
| Secret document added | `C_secret` is live and has text hash `T`; no task exists for it yet. |
| Rebuild denylist | Existing tasks are read; `C_secret` is absent. |
| Content-hash relink | The join creates `chunk_vec(C_secret)` from `E(T)`. |
| Enrichment | The linked chunk is classified as complete and never reaches hold creation. |
| Vector search | KNN returns `C_secret`; live metadata resolves it to the secret path. |

### The later pass cannot repair the state

The important point is not merely that the link briefly exists. The next pass
filters it out permanently for the current lifecycle. `live_chunks_without_embedding`
loads all existing `chunk_vec` IDs, computes the content embedding identity,
and skips a chunk when both the authoritative vector and the derived link are
present:

```rust
// crates/kcs-cli/src/main.rs:7912-7918, live_chunks_without_embedding
let embedding_hash = chunk_embedding_hash(&chunk, profile)?;
let has_current_profile = embedding_store::content_vector(conn, &embedding_hash)
    .map_err(index_to_kcs)?
    .is_some();
if has_current_profile && existing.contains(&chunk.chunk_id) {
    continue;
}
```

Only chunks that survive this loop are returned as `pending`. The caller then
partitions `pending` by the current live path and persists the secret holds:

```rust
// crates/kcs-cli/src/main.rs:7317-7330, run_embedding_enrichment
let (held, sendable): (Vec<EmbeddableChunk>, Vec<EmbeddableChunk>) =
    pending.into_iter().partition(|chunk| {
        !secrets_approved && classify_secret(&chunk.raw_path).is_some()
    });
hold_secret_embedding_tasks(&task_store, repo, &held, &now)?;
```

We therefore never reach the otherwise-correct current-path classifier for
`C_secret`. A repeated index follows the same logic: the link already exists,
and there is still no task-derived denylist entry for that chunk.

Finally, vector search reads `chunk_vec`, then resolves each KNN chunk ID
against live `tree_entries`. The liveness check is correct, but it does not
repeat the secret policy check. The result metadata includes `te.path`, so the
new secret document's association and provenance become observable through a
normal search response.

## Exploitability Analysis

This is best understood as a deterministic policy-state failure, not a race or
memory-safety primitive. We can reach it through ordinary local indexing with
four narrow preconditions:

1. The scope already has a current-profile embedding for a non-secret chunk.
2. A newly indexed secret-labeled document contains a chunk with exactly the
   same normalized text and therefore the same `text_hash`.
3. The new document has a different raw/provenance identity, producing a
   distinct `chunk_id` for the shared text.
4. No current secret-send approval exists when the new document is indexed.

No concurrent process, malformed store record, privileged access, credential,
or external response is required. Reliability is high once those conditions
hold because all relevant steps are sequential inside one index command. A
different introduction in each document is enough to give the two raw
documents distinct identities, while a matching heading and paragraph provide
the shared normalized chunk.

The strongest practical consequence is provenance visibility to a local
search consumer. A vector or hybrid result can identify the secret-labeled
file, its heading path, raw hash, current commit association, and Evidence
Pointer. An automation layer that treats KCS's secret hold as a policy boundary
may therefore receive and propagate an association it expected KCS to suppress.
At the same time, task/status evidence is internally inconsistent: another
unique chunk in the same secret file can be correctly Paused while the shared
chunk has no task at all and appears enriched.

Several constraints prevent a stronger conclusion:

- The reused chunk text is already public within the same scope and already
  has an embedding. Reuse does not reveal previously unknown chunk bytes.
- `rebuild_chunk_vec` performs a local SQLite link. This path makes no new
  adapter request and does not transmit the secret document.
- Search runs with the local KCS user's authority. The issue does not by
  itself bypass operating-system file permissions or disclose an arbitrary
  file to another local account.
- If the text differs after normalization, there is no matching embedding and
  the chunk remains pending, where the normal secret partition creates a hold.
- If a valid hold task for this exact chunk ID already exists, the existing
  held-ID denylist works and rebuild omits the link.
- If secret sending is explicitly approved, vector eligibility is expected and
  the condition no longer represents a policy violation.
- Local full-text indexing may already expose document text to the same user;
  this finding is specifically about the stronger secret-hold promise for
  semantic indexing, provenance, and durable audit state.

These dead ends are useful for calibration. They rule out arbitrary secret
exfiltration while leaving a reproducible, policy-relevant confidentiality and
integrity gap. That combination is why Medium/P2 is appropriate.

## Proof of Concept

The `poc/reproduce.sh` regression probe creates two synthetic Markdown files in
a fresh temporary scope. It indexes the public file using KCS's deterministic
in-process embedding implementation, adds a differently identified file named
`credentials_backup.md` with one identical normalized paragraph, and indexes
again without `--send-secrets`. It then compares chunk IDs and text hashes,
reads the disposable task ledger, and performs a vector search scoped only to
that temporary directory.

The probe deliberately verifies a nearby control. The secret document's unique
introductory chunk must receive a hold, proving that the filename classifier
and hold mechanism ran. The shared secret chunk is the only one expected to
show the vulnerable ordering.

Build the revision under test, make its `kcs` binary available through
`KCS_BIN` or `PATH`, and run from the report directory:

```sh
cd poc
./reproduce.sh
```

Representative output from the confirmed revision is included in
`poc/output.txt`:

```text
temporary_scope=true
network_adapter=deterministic_in_process_mock
distinct_chunk_ids_share_text_hash=true
secret_unique_chunk_hold_count=1
secret_shared_chunk_hold_count=0
secret_shared_chunk_in_vector_results=true
result=VULNERABLE_POLICY_STATE_OBSERVED
```

I ran this probe locally. It completed without contacting a service or reading
an existing store. The script starts each KCS process with an empty environment
apart from `PATH`, isolated HOME/XDG locations, and the explicit mock selector;
it removes its own temporary tree on exit. It contains no destructive action,
requires no manual cleanup, and should be suitable as a regression check.

A fixed build should report a hold for the shared secret chunk and should not
return that chunk from vector search before approval. The script recognizes
that pair as `FIXED_POLICY_STATE_OBSERVED`. Because no fixed revision was
available, that branch is a stated expected result rather than an observation.

## Remediation

The invariant to restore is that current live classification, not historical
task existence, decides vector eligibility. For every current chunk identity,
KCS should persist or reconcile its secret hold before `chunk_vec` can contain
a content-reuse link. Task state may record that decision, but it must not be
the sole source for making the initial decision.

The preferred structural fix is to split rebuild/enrichment into explicit
phases:

1. Materialize current chunks, `tree_entries`, and authoritative `embeddings`
   without publishing `chunk_vec` links.
2. Classify every current live chunk using its current path and current
   secret-send approval.
3. Create, demote, release, or retire hold tasks so the task projection matches
   that classification.
4. Build `chunk_vec` only for policy-eligible chunk IDs.
5. Run embedding work for the remaining sendable chunks.

As a minimal fail-closed patch, the rebuild can union its existing task-derived
set with chunk IDs derived directly from current live secret paths. The current
approval state must be plumbed into the rebuild so approved secrets are not
blocked. The following is an illustrative source shape:

```rust
fn current_live_secret_chunk_ids(conn: &Connection) -> Result<BTreeSet<String>> {
    let mut stmt = conn.prepare(
        "SELECT DISTINCT c.chunk_id, te.path
         FROM chunks c
         JOIN tree_entries te
           ON te.raw_hash = c.raw_hash
          AND te.tool_profile_hash = c.tool_profile_hash
          AND te.gen = c.gen",
    )?;
    let rows = stmt.query_map([], |row| {
        Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
    })?;

    let mut blocked = BTreeSet::new();
    for row in rows {
        let (chunk_id, live_path) = row?;
        if classify_secret(&live_path).is_some() {
            blocked.insert(chunk_id);
        }
    }
    Ok(blocked)
}

let mut blocked = held_secret_embedding_chunk_ids(kcs_dir)?;
if !secrets_approved {
    blocked.extend(current_live_secret_chunk_ids(fts.connection())?);
}
embedding_store::rebuild_chunk_vec(fts.connection(), &blocked)?;
```

This minimal change closes the immediate gap: the new secret twin is absent
from `chunk_vec`, so `live_chunks_without_embedding` cannot take its early
`continue`; enrichment then reaches current-path classification and creates
the missing hold. The structural phase split is still preferable because it
makes the lifecycle ordering explicit and gives task/status consumers the
durable decision before any derived vector publication.

The patch should also preserve the existing conservative behavior for multiple
live paths: if any live provenance for a content-addressed chunk is secret and
unapproved, the chunk identity must remain blocked. Conversely, releasing an
approval or removing the last live secret provenance should converge the task
and vector projection without requiring users to lower the entire scope's
policy unnecessarily.

Regression coverage should include:

- the exact two-document case in `poc/reproduce.sh`: distinct chunk IDs, equal
  text hashes, one public vector, and a newly added secret path;
- an assertion immediately after indexing that every live, unapproved secret
  chunk has a Paused `secrets_tier_b_hold` task and no `chunk_vec` row;
- an assertion that vector and hybrid search omit the secret twin's path and
  Evidence Pointer before approval;
- a negative control in which an ordinary public twin remains linked;
- a negative control in which the secret text is not identical and follows the
  normal pending-to-hold path;
- multiple live aliases, proving that one secret path makes the decision
  conservative for the shared identity;
- `--send-secrets` approval, proving that the hold is released and the vector
  link becomes available only afterward;
- each rebuild entry point (`index`, `reindex`, and `repair --rebuild-db`), so
  no alternate projection path reintroduces the stale-task decision; and
- interruption between policy reconciliation and database publication,
  proving recovery fails closed and converges on the next run.

An additional invariant test can compare the two durable projections after
every rebuild: no unapproved live secret chunk may be present in `chunk_vec`,
and no such chunk may be missing its corresponding hold. Testing both halves
would have caught this issue even if the implementation order changed.

## Summary

KCS correctly recognizes the secret filename and correctly knows how to hold a
pending embedding. The failure occurs one step earlier: vector rebuild treats
the existing task ledger as the complete secret-policy state even though new
holds are created only afterward. Content-addressed reuse then gives the new
secret chunk a derived vector link, and the later pending filter prevents the
hold from ever being created.

We demonstrated the full local state transition with synthetic content and an
in-process deterministic vector: two distinct chunk IDs shared one text hash,
the unique secret chunk was held, the shared secret chunk was not held, and
vector search returned the shared secret provenance. We also bounded the
impact: no new secret bytes, credentials, or requests crossed a network
boundary, but secret path/provenance and audit state became visible contrary
to the hold policy.

The durable fix is to make current live classification authoritative and to
reconcile holds before derived vector eligibility. Future review should look
for the same architectural smell within this subsystem—derived indexes that
use workflow/task rows as a proxy for current policy—while keeping the scope
of any follow-up analysis tied to this hold-before-reuse invariant.
