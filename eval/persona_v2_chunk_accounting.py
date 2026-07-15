"""Non-authorizing chunk-accounting semantics for persona-PC v2.

This small sidecar reconciles the product search identity with the synthetic
persona workload without changing any frozen v2 envelope or overlay body.
It owns identities and symbolic deltas only.  It contains no source, path,
scope, chunk, final-plan, query, or observed receipt instance.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_chunk_accounting_validator as independent
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_chunk_accounting_validator as independent
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay


ARTIFACT_SCHEMA = "kcs.persona.pc-chunk-accounting/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-chunk-accounting"
FIXTURE_ID = "kcs-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_ACCOUNTING_BYTES = 256 * 1024

METRIC_ORDER = (
    "search-semantic-endpoint-v1",
    "persona-global-chunk-hash-v1",
    "history-path-binding-v1",
    "physical-storage-v1",
)
CHECKPOINT_ORDER = (
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5-pre-purge",
    "W5-final",
)
PROFILE_ORDER = ("pilot", "full")
OPERATION_ORDER = (
    "same-scope-rename-contributor",
    "cross-scope-move-incidental",
    "same-scope-exact-duplicate-diagnostic",
    "cross-scope-exact-duplicate-contributor",
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-envelope": (
        71_979,
        "1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370",
    ),
    "persona-v2-overlay-contract": (
        71_179,
        "ae219f90caf97e153e57f821b34f4f8a9ad671ee705387a5d0142ff9963fc75c",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_checkpoint_cardinalities_attested",
        "actual_chunks_attested",
        "actual_inodes_attested",
        "actual_search_performance_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_target_resolution",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_solver_execution",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "kcs_execution_available",
        "source_instance_matching_available",
    }
)


class PersonaV2ChunkAccountingError(ValueError):
    """Raised when chunk-accounting construction or validation fails."""


def _fail(message):
    raise PersonaV2ChunkAccountingError(message)


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(key) is not str or type(flag) is not bool or flag is not False
        for key, flag in authority.items()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _binding(name, role, value, *, validate, canonical):
    validate(value)
    _require_negative_authority(value, label=name)
    raw = canonical(value)
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual != EXPECTED_DEPENDENCY_PINS[name]:
        _fail(f"{name} differs from its frozen dependency pin")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": actual[0],
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual[1],
    }


def _metric_contracts():
    return [
        {
            "accounting_uses_current_chunking_config_only": True,
            "contract_exact_checkpoint_denominator": True,
            "cross_participation_endpoint_collision_allowed": False,
            "history_only_state_rule": (
                "zero-live-bindings-in-the-same-scope-and-at-least-one-reachable-"
                "nonpurged-historical-or-deleted-binding"
            ),
            "chunk_id_is_chunk_hash": True,
            "identity_fields_observed": ["scope_id", "chunk_id"],
            "identity_fields_planned": ["scope_key", "chunk_id"],
            "incidental_dynamic_cap_denominator": True,
            "metric_id": "search-semantic-endpoint-v1",
            "participation_classes": ["contract_contributor", "incidental_searchable"],
            "product_search_identity": True,
            "states": ["current", "history-only"],
            "states_are_pairwise_disjoint": True,
            "current_state_rule": "at-least-one-live-binding-in-the-same-scope",
        },
        {
            "can_collapse_equal_chunks_across_scopes": True,
            "checkpoint_or_performance_denominator": False,
            "diagnostic_dedup_only": True,
            "identity_fields": ["chunk_id"],
            "metric_id": "persona-global-chunk-hash-v1",
            "scope_and_path_are_not_identity_fields": True,
        },
        {
            "alias_expansion_occurs_after_semantic_ranking_and_dedup": True,
            "canonical_introduction_commit_is_evidence_not_identity": True,
            "identity_fields_observed": ["scope_id", "chunk_id", "path"],
            "identity_fields_planned": ["scope_key", "chunk_id", "path"],
            "metric_id": "history-path-binding-v1",
            "same_chunk_and_path_across_many_commits_collapses": True,
            "separate_renamed_paths_do_not_collapse": True,
        },
        {
            "cross_scope_cas_dedup_guaranteed": False,
            "identities_by_projection": {
                "chunk-cas-object": ["scope_key", "chunk_id"],
                "managed-source-materialization": ["scope_key", "path"],
                "raw-cas-object": ["scope_key", "raw_hash"],
            },
            "inode_number_is_canonical_identity": False,
            "metric_id": "physical-storage-v1",
            "regular_file_and_inode_counts_require_observed_receipts": True,
            "scope_local_object_store": True,
        },
    ]


def _term(metric_id, projection, direction, coefficient, symbol):
    return {
        "coefficient": coefficient,
        "direction": direction,
        "metric_id": metric_id,
        "projection": projection,
        "symbol": symbol,
    }


def _zero_search_terms():
    return [
        _term(
            "search-semantic-endpoint-v1",
            f"{participation}-{state}",
            "preserve",
            0,
            "zero",
        )
        for participation in ("contract", "incidental")
        for state in ("current", "history-only")
    ]


def _operation_contracts():
    rename_terms = _zero_search_terms() + [
        _term("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "preserve", 0, "zero"),
        _term("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qR"),
        _term("physical-storage-v1", "managed-source-regular-files", "preserve", 0, "zero"),
        _term("physical-storage-v1", "raw-cas-regular-objects", "preserve", 0, "zero"),
        _term("physical-storage-v1", "chunk-cas-regular-objects", "preserve", 0, "zero"),
        _term("physical-storage-v1", "managed-source-inodes", "preserve", 0, "zero"),
        _term("physical-storage-v1", "raw-cas-inodes", "preserve", 0, "zero"),
        _term("physical-storage-v1", "chunk-cas-inodes", "preserve", 0, "zero"),
    ]

    move_search = _zero_search_terms()
    move_search[3] = _term(
        "search-semantic-endpoint-v1",
        "incidental-history-only",
        "increase",
        1,
        "qIM",
    )
    move_terms = move_search + [
        _term("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "preserve", 0, "zero"),
        _term("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qIM"),
        _term("physical-storage-v1", "managed-source-regular-files", "preserve", 0, "zero"),
        _term("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "nIM"),
        _term("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qIM"),
        _term("physical-storage-v1", "managed-source-inodes", "preserve", 0, "zero"),
        _term("physical-storage-v1", "raw-cas-inodes", "increase", 1, "nIM"),
        _term("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qIM"),
    ]

    same_duplicate_terms = _zero_search_terms() + [
        _term("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "preserve", 0, "zero"),
        _term("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qD"),
        _term("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        _term("physical-storage-v1", "raw-cas-regular-objects", "preserve", 0, "zero"),
        _term("physical-storage-v1", "chunk-cas-regular-objects", "preserve", 0, "zero"),
        _term("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
        _term("physical-storage-v1", "raw-cas-inodes", "preserve", 0, "zero"),
        _term("physical-storage-v1", "chunk-cas-inodes", "preserve", 0, "zero"),
    ]

    cross_duplicate_search = _zero_search_terms()
    cross_duplicate_search[0] = _term(
        "search-semantic-endpoint-v1",
        "contract-current",
        "increase",
        1,
        "qD",
    )
    cross_duplicate_terms = cross_duplicate_search + [
        _term("persona-global-chunk-hash-v1", "distinct-chunk-hashes", "preserve", 0, "zero"),
        _term("history-path-binding-v1", "reachable-path-bindings", "increase", 1, "qD"),
        _term("physical-storage-v1", "managed-source-regular-files", "increase", 1, "one"),
        _term("physical-storage-v1", "raw-cas-regular-objects", "increase", 1, "one"),
        _term("physical-storage-v1", "chunk-cas-regular-objects", "increase", 1, "qD"),
        _term("physical-storage-v1", "managed-source-inodes", "increase", 1, "one"),
        _term("physical-storage-v1", "raw-cas-inodes", "increase", 1, "one"),
        _term("physical-storage-v1", "chunk-cas-inodes", "increase", 1, "qD"),
    ]

    return [
        {
            "delta_terms": rename_terms,
            "operation_id": "same-scope-rename-contributor",
            "preconditions": [
                "source-and-destination-basename-differ",
                "scope-key-is-unchanged",
                "source-path-is-a-live-contract-contributor-materialization",
                "destination-scope-path-has-no-live-materialization-before-rename",
                "destination-scope-chunk-path-bindings-are-not-reachable-before-rename",
                "raw-bytes-tool-profile-generation-and-chunk-set-are-preserved",
            ],
            "source_participation": "contract_contributor",
        },
        {
            "delta_terms": move_terms,
            "operation_id": "cross-scope-move-incidental",
            "preconditions": [
                "exactly-five-distinct-pilot-incidental-searchable-sources",
                "full-reuses-the-same-five-pilot-source-rows",
                "source-and-destination-are-different-leaf-scopes-of-one-persona",
                "each-source-endpoint-has-exactly-one-live-source-scope-binding",
                "destination-has-no-live-historical-or-cas-endpoint-collision",
                "all-planned-destination-scope-chunk-endpoints-are-pairwise-distinct",
                "all-planned-destination-scope-path-materializations-are-pairwise-distinct",
                "each-destination-scope-path-has-no-live-materialization-before-its-move",
                "five-raw-identities-are-distinct-and-absent-from-destination-stores",
                "raw-bytes-facts-tool-profile-generation-and-chunk-set-are-preserved",
            ],
            "runtime_interpretation": (
                "source-delete-plus-destination-ingest-across-independent-kcs-"
                "stores-not-product-cross-scope-lineage-inference"
            ),
            "source_participation": "incidental_searchable",
        },
        {
            "delta_terms": same_duplicate_terms,
            "formal_contract_contributor_target_eligible": False,
            "operation_id": "same-scope-exact-duplicate-diagnostic",
            "preconditions": [
                "new-path-is-distinct",
                "source-contract-endpoints-are-current-with-a-live-source-path-binding",
                "new-path-has-no-live-materialization-before-duplicate",
                "destination-scope-chunk-path-bindings-are-not-reachable-before-duplicate",
                "same-scope-raw-tool-generation-and-chunk-identities-are-equal",
            ],
            "source_participation": "contract_contributor",
        },
        {
            "delta_terms": cross_duplicate_terms,
            "formal_contract_contributor_target_eligible": True,
            "operation_id": "cross-scope-exact-duplicate-contributor",
            "preconditions": [
                "new-scope-differs-from-existing-endpoint-scope",
                "source-contract-endpoints-are-current-with-a-live-source-path-binding",
                "destination-scope-has-no-live-or-reachable-historical-matching-chunk-endpoint",
                "destination-scope-path-has-no-live-materialization-before-duplicate",
                "destination-scope-chunk-path-bindings-are-not-reachable-before-duplicate",
                "destination-store-has-no-matching-raw-or-chunk-object",
                "raw-tool-generation-and-chunk-identities-are-equal",
            ],
            "source_participation": "contract_contributor",
        },
    ]


def _checkpoint_contract(envelope_value):
    profiles = {}
    for profile in PROFILE_ORDER:
        rows = []
        for checkpoint in CHECKPOINT_ORDER:
            source = envelope_value["history_checkpoints"][profile][checkpoint]
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "current_contract_semantic_endpoints": source[
                        "current_contract_chunks"
                    ],
                    "history_only_contract_semantic_endpoints": source[
                        "history_only_contract_chunks"
                    ],
                    "incidental_move_history_multiplier": (
                        0 if checkpoint in {"W0", "W1"} else 1
                    ),
                    "incidental_move_history_symbol": "qIM",
                }
            )
        profiles[profile] = rows
    return {
        "contract_checkpoint_literals_unchanged_from_envelope": True,
        "contract_metric_id": "search-semantic-endpoint-v1",
        "incidental_move_changes_contract_checkpoint_literals": False,
        "profiles": profiles,
    }


def _move_anchor_contract():
    return {
        "anonymous_capability_reclassification": {
            "I": 5,
            "N": 0,
            "P": 15,
            "U": 35,
            "X": 20,
            "Y": 30,
        },
        "capability_count_per_persona": 105,
        "contributor_semantic_anchor_capacity_consumed": 100,
        "contributor_semantic_anchor_capacity_reserved": 105,
        "contributor_semantic_anchor_capacity_unused": 5,
        "incidental_move_anchor_count": 5,
        "incidental_move_anchors_must_be_unreserved_pilot_sources": True,
        "incidental_move_anchors_must_be_nonzero_after_W0_index": True,
        "per_source_actual_chunk_inclusive_maximum": 70,
        "per_source_actual_chunk_inclusive_minimum": 1,
        "qIM_definition": "sum-of-five-W0-observed-incidental-move-anchor-chunk-counts",
        "qIM_inclusive_maximum": 350,
        "qIM_inclusive_minimum": 5,
        "qIM_literal_resolution_stage": "post-W0-attestation-before-W2-event-compilation",
        "query_oracle_mapping_is_separate_and_explicit": True,
        "semantic_anchor_slots_are_capacity_not_query_ordinals": True,
    }


def _cap_rows(envelope_value):
    rows = []
    for profile in PROFILE_ORDER:
        pre = envelope_value["history_checkpoints"][profile]["W5-pre-purge"]
        caps = envelope_value["incidental_cap_contract"]["eligible_caps"][profile]
        current = min(
            caps["base_current"],
            caps["current"] - pre["current_contract_chunks"],
        )
        total = min(
            caps["base_total"],
            caps["total"]
            - pre["current_contract_chunks"]
            - pre["history_only_contract_chunks"],
        )
        q_upper = 5 * 70
        lhs = current + q_upper
        rows.append(
            {
                "incidental_current_upper_bound": current,
                "incidental_total_upper_bound": total,
                "move_history_upper_bound": q_upper,
                "profile": profile,
                "proof_checkpoint": "W5-pre-purge",
                "required_headroom_after_worst_case_move": total - lhs,
                "worst_case_current_plus_move_history": lhs,
                "worst_case_satisfies_total_cap": lhs <= total,
            }
        )
    return rows


def _evaluation_contract():
    return {
        "all_history_final_hit_identity": [
            "scope_id",
            "chunk_id",
            "path_at_commit",
            "evidence_pointer_commit",
        ],
        "all_history_hit_count_is_not_current_plus_history_endpoint_count": True,
        "formal_recall_denominator": ["raw_hash", "section"],
        "formal_recall_dedup_occurs_after_evidence_state_qualification": True,
        "mvp_performance_denominator": ["scope_id", "chunk_hash"],
        "mvp_performance_minimum_current_endpoints": 100_000,
        "persona_contract_current_endpoint_target": 120_000,
        "persona_profile_uses_twenty_participating_scopes": True,
        "performance_uses_actual_eligible_contract_plus_incidental_union": True,
        "planned_quota_global_hash_path_binding_and_cas_rows_are_not_performance_denominators": True,
        "recall_and_performance_denominators_are_intentionally_different": True,
    }


@functools.lru_cache(maxsize=1)
def _cached_contract():
    envelope_value = envelope.build_envelope_contract()
    overlay_value = overlay.build_overlay_contract()
    bindings = [
        _binding(
            "persona-v2-envelope",
            "numeric-checkpoint-cap-and-persona-owner",
            envelope_value,
            validate=envelope.validate_envelope_contract,
            canonical=envelope.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-overlay-contract",
            "scope-qualified-accounting-duplicate-and-recall-owner",
            overlay_value,
            validate=overlay.validate_overlay_contract,
            canonical=overlay.canonical_json_bytes,
        ),
    ]
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {key: False for key in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_body_bytes": MAX_ACCOUNTING_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "checkpoint_contract": _checkpoint_contract(envelope_value),
        "completion_claims": {
            "actual_accounting_attested": False,
            "compiled_event_deltas_present": False,
            "contract_and_incidental_denominators_separated": True,
            "four_metric_identities_authored": True,
            "operation_delta_algebra_authored": True,
            "source_instance_assignment_present": False,
            "upstream_frozen_bodies_bound": True,
        },
        "completion_scope": (
            "identity-and-symbolic-accounting-only-no-source-scope-path-chunk-"
            "or-final-instances-no-execution-no-g0"
        ),
        "evaluation_denominator_contract": _evaluation_contract(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "incidental_move_cap_proof": _cap_rows(envelope_value),
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "metric_contracts": _metric_contracts(),
        "metric_order": list(METRIC_ORDER),
        "move_anchor_contract": _move_anchor_contract(),
        "operation_delta_contracts": _operation_contracts(),
        "operation_order": list(OPERATION_ORDER),
        "remaining_blockers": [
            "source-instance-gate-role-and-scope-assignment-not-present",
            "W0-observed-incidental-move-chunk-counts-not-attested",
            "compiled-literal-history-events-not-present",
            "cross-metric-observed-ledger-not-present",
            "filesystem-cas-and-inode-receipts-not-present",
            "performance-and-recall-observations-not-present",
            "external-independent-review-approval-not-present",
        ],
        "state_partition_contract": {
            "contract_and_incidental_endpoint_sets_must_be_disjoint": True,
            "current_and_history_only_are_disjoint_within_each_participation_class": True,
            "history_liveness_is_scope_local_not_persona_global": True,
            "same_chunk_hash_may_be_current_in_one_scope_and_history_only_in_another": True,
            "sum_of_role_counts_requires_cross_role_endpoint_disjointness": True,
        },
        "symbol_contracts": [
            {"inclusive_maximum": 0, "inclusive_minimum": 0, "resolution_stage": "authored", "symbol": "zero"},
            {"inclusive_maximum": 1, "inclusive_minimum": 1, "resolution_stage": "authored", "symbol": "one"},
            {"inclusive_maximum": 5, "inclusive_minimum": 5, "resolution_stage": "authored", "symbol": "nIM"},
            {"inclusive_maximum": 70, "inclusive_minimum": 1, "resolution_stage": "post-solver-compiled-plan", "symbol": "qD"},
            {"inclusive_maximum": 350, "inclusive_minimum": 5, "resolution_stage": "post-W0-attestation-before-W2-event-compilation", "symbol": "qIM"},
            {"inclusive_maximum": 70, "inclusive_minimum": 1, "resolution_stage": "post-solver-compiled-plan", "symbol": "qR"},
        ],
    }
    raw = canonical_json_bytes(value)
    if len(raw) > MAX_ACCOUNTING_BYTES:
        _fail("chunk-accounting body exceeds its byte cap")
    return value


def build_chunk_accounting_contract():
    """Return a detached deterministic chunk-accounting contract."""

    return copy.deepcopy(_cached_contract())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 chunk accounting",
            max_bytes=MAX_ACCOUNTING_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def validate_chunk_accounting_contract(value):
    try:
        return independent.validate_chunk_accounting_contract(
            value,
            envelope_value=envelope.build_envelope_contract(),
            overlay_contract_value=overlay.build_overlay_contract(),
        )
    except independent.PersonaV2ChunkAccountingValidationError as error:
        _fail(str(error))


def chunk_accounting_sha256(value=None):
    if value is None:
        value = build_chunk_accounting_contract()
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


if __name__ == "__main__":  # pragma: no cover
    body = build_chunk_accounting_contract()
    validate_chunk_accounting_contract(body)
    print(chunk_accounting_sha256(body))
