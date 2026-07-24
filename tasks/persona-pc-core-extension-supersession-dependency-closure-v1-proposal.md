# Persona-PC core allocation supersession — transitive content-owner closure v1 proposal

Status: **proposal only; no allocation truth selected**. This document maps the
replacement closure required if `persona-core-v1` becomes the upstream
persona/family/variant allocation truth. It does not select that outcome,
modify frozen v2/v3 artifacts, issue a namespace, create a source plan,
materialize folders/files, mutate history, or claim chunk/recall/capacity
completion.

## 1. Trigger and fixed evidence

The local count-only incompatibility audit has these frozen candidate pins:

| item | bytes | SHA-256 |
| --- | ---: | --- |
| audit descriptor | 3,500 | `1c52c83f8bd98407212e4014e7b006f38a93b0f82ff59a922a858d7e5663bfe2` |
| audit delta JSONL | 236,068 | `a755ef7ee770796f7d0a02c261c706089b23b6a016a766d6962e600bf027de44` |

The 566 common `(persona_id, family_id, variant_id)` coordinates have equal
suite totals but not equal allocations:

| profile | core total | legacy total | mismatched cells | L1 delta |
| --- | ---: | ---: | ---: | ---: |
| full | 203,000 | 203,000 | 489 | 70,500 |
| pilot | 20,300 | 20,300 | 483 | 7,050 |

Therefore these states remain fixed until a formal allocation decision:

```text
legacy_source_allocation_compatibility = unresolved
legacy_source_projection_reuse_authorized = false
core_allocation_supersession_selected = false
```

The audit compares counts only. It is not a format-metadata compatibility proof
and does not choose which allocation truth wins.

## 2. Allowed decision paths

Only one later path is allowed:

1. **Additive reuse:** requires an independent zero-mismatch proof for every
   full/pilot coordinate and allocation-relevant metadata. The pinned audit
   disproves this for current inputs.
2. **Supersession:** selects core allocation as the upstream truth and
   regenerates every definitely dependent content owner below as a versioned
   successor before semantic namespace admission.
3. **Deferral:** retains core allocation and its audit outside the semantic
   namespace. No successor work follows from this document.

An override table, post-solver translation, or source-plan back-edge is never a
substitute for a successor. A new allocation must be resolved in pre-solve
content owners, not injected into a solution, history, or renderer directive.

## 3. Immutable boundary

The following remain byte-for-byte frozen in every path:

- legacy variant catalog and source-inventory artifacts;
- complete semantic projection inventory v2;
- corpus semantic namespace v3 (its 12 classes and 253 entries);
- the W0 history pre-solve closure that directly pins v2/v3; and
- existing query, review, evaluation, history, and G0 artifacts.

Supersession creates new versioned artifacts and successor closures. It never
relabels, mutates, or treats old pins as if they represented the new allocation.

## 4. Definitely allocation-dependent closure

Every row below requires a successor or an exact, independent per-cell proof if
core allocation is selected. A successor means a separately identified,
content-only artifact with new pins and independent validation, not a patched
legacy body.

| layer | owner / role | required action |
| --- | --- | --- |
| allocation root | `persona_v2_variant_catalog.persona_variant_marginals` | Create a core-compatible 566-cell allocation owner. Preserve the coordinate universe only after a separate universe/metadata proof. |
| source reservation | `persona_v2_source_inventory_layout` | Recompute pilot and full-residual ordinal ranges from new full/pilot counts; do not retain legacy intent keys/ranges. |
| source package | `persona_v2_source_inventory_profile`, `persona_v2_source_inventory_package` | Rebuild origin/profile/suite manifests and all 73 source shard receipts. |
| overlay reservation | `persona_v2_overlay_reservation_layout` | Recompute reserved, anchor, and unreserved intent-key pools before source-owned semantics. |
| semantic membership | `persona_v2_source_semantic_membership_package` | Rebuild source-owned fact/content context and membership bodies from successor source and reservation domains. |
| concrete overlay | `persona_v2_concrete_overlay_membership_package` | Rejoin successor source, semantic, and reservation origins; labels alone do not make old endpoints portable. |
| recipe/distribution | formal recipe plus aggregate and overlay-compatible byte-distribution owners | Rebind or regenerate every allocation-count-dependent recipe/distribution projection. |
| parameters | `persona_v2_source_parameter_assignment_package` | Recompute all intent-to-variant/bin assignments from successor source, concrete, recipe, and distribution inputs. |
| lifecycle | `persona_v2_source_matched_lifecycle_inventory` | Reauthenticate successor pilot source, reservation, semantic, and parameter domains before selecting anchors. |
| effective membership | `persona_v2_lifecycle_effective_membership_reconciliation` | Rebuild W0 effective membership from successor semantic and matched-lifecycle owners. |

This is transitive: changing a 566-cell marginal changes intent ordinals,
sharding, overlay eligibility, membership joins, parameter rows, and lifecycle
inputs—not merely a format ratio.

## 5. Capacity, projection, namespace, and candidate-domain closure

The following must be regenerated or independently proven byte-identical after
the source-side successor chain exists:

1. `source_semantic_capacity_axis_catalog`: its current artifact pins source
   semantic membership.  Although its conceptual 15,048-cell lattice has zero
   source-slot assignments, that fact alone is not enough to reuse the old
   receipt or pin.  It needs a successor receipt or an independent
   body-equality and input-compatibility proof.
2. capacity truth/occurrence policy, because it pins the axis; and lifecycle
   coverage, because it also pins source semantic membership.
3. source-derived semantic projections: base source content context, effective
   source membership, concrete overlay relations, source-instance parameters,
   source-matched lifecycle rules, and payload-equivalence dependencies.
4. a derivation/complete inventory successor and then a namespace successor.
5. candidate-domain input: it must reread successor full-residual source shards,
   expanded contexts, and residual overlay origins. Its prior 74,529 count/digest
   cannot be carried forward; source-to-cell assignment remains zero pre-solver.
6. corpus/history/evaluation closure successors, because their old pins cannot
   certify a new source allocation.

`corpus-semantic-namespace/v3` cannot be changed: it authenticates complete
inventory v2 and hard-codes 253 entries. A successor consumes only a successor
inventory, never a direct core-allocation argument or duplicate body pin.

### 5.1 Fixed namespace v3 impact

The existing namespace has 253 ordered entries.  Static ownership tracing marks
229 as allocation-dependent, so none of those entries can be reinterpreted as
core-allocation content.  They are not candidates for an append-only update.

| v3 ordinal(s) | projection class | entries | action if supersession is selected |
| --- | --- | ---: | --- |
| 5 | recipe-content-filename-policy | 1 | successor or exact dependency proof |
| 26–98 | base-source-content-context | 73 | successor |
| 99–118 | effective-source-membership | 20 | successor |
| 119–158 | concrete-overlay-relations | 40 | successor |
| 159–232 | source-instance-parameters | 74 | successor |
| 233–252 | query-independent lifecycle fact/rendition rules | 20 | successor |
| 253 | payload-equivalence-rules | 1 | successor receipt if any bound owner changes |
| **total** | **allocation-dependent entries** | **229** | **new complete inventory and namespace required** |

The remaining 24 entries (topology, realism, route, primary-use-case, and fact
graph classes) do not have a direct legacy marginal read path, but remain
audit-first rather than implicitly reusable.  In particular, the current route
affinity owner asserts 541 legacy full-active rows while the core candidate has
539 full-nonzero rows; it requires an explicit compatibility result before a
successor namespace can bind it.

## 6. Conditional metadata owners

These are audit-first, not automatically regenerated. They may remain
byte-identical only after a read-set and output-equality proof:

- format implementation registry and source-profile feasibility metadata;
- envelope, topology, realism, route affinity, fact graph, primary-use-case,
  and overlay-contract catalogs;
- chunk accounting and lifecycle demand, which currently do not directly pin
  allocation marginals; and
- representative source-intent/fact-membership slices and the rule text of
  payload equivalence.

If an otherwise stable body has a receipt that pins a changed successor owner,
its downstream receipt/descriptor still requires a successor. Stable text is
not permission to retain stale owner pins.

## 7. Required proof gates for a supersession proposal

Before namespace construction, the selected supersession path must provide:

- a direct core allocation owner with a 566-cell full/pilot/tiny body and an
  independent validator;
- exact persona/family/variant-universe and allocation-metadata join results;
- a machine-generated closure manifest marking each owner in §4/§5 as
  regenerated or proven byte-identical;
- no legacy source intent key, source instance, path, capacity-cell assignment,
  query, history event, solver output, or renderer receipt copied into the new
  allocation root merely for convenience;
- two-read/provider-mutation and cold hash-seed validation for every new root;
- a successor body-budget decision that does not conflate v3's 256 MiB total
  cap with the separately proposed 256 MiB new-body budget; and
- a formal decision-log entry selecting supersession. The local audit freeze is
  evidence, not that decision.

## 8. Safe order

```text
formal selection of core allocation as upstream truth
  -> core-compatible allocation owner / source-layout successor
  -> source package + overlay reservation successors
  -> semantic membership + concrete overlay successors
  -> recipe/distribution + parameter successors
  -> matched lifecycle + effective membership successors
  -> capacity-axis / truth-policy / lifecycle-coverage successors or equality proofs
  -> source-derived projection / complete inventory / namespace successors
  -> candidate-domain recomputation (assignment remains zero)
  -> corpus, history, and evaluation closure successors
  -> namespace-only joint solution/proof
  -> final source plan, planned history, G0, and only then materialization
```

This sequence does not prove 120,000 actual chunks per person. It establishes
the pre-solve content chain required before folders, files, history, and three
fresh replay measurements can be created and observed.
