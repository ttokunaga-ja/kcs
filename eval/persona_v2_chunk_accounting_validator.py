"""Independent validator for persona-PC v2 chunk accounting.

The producer is deliberately not imported.  This validator authenticates the
two frozen inputs, reconstructs the complete expected body from independent
constants and integer formulae, checks the cross-metric delta algebra, and
reauthenticates every caller-owned object in ``finally``.
"""

from __future__ import annotations

import hashlib
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay


ARTIFACT_SCHEMA = "kio.persona.pc-chunk-accounting/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-chunk-accounting"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_ACCOUNTING_BYTES = 256 * 1024
MAX_DEPENDENCY_BYTES = 2 * 1024 * 1024

# Installed only after independent semantic validation of the final body.
EXPECTED_ACCOUNTING_CANONICAL_BYTES = 19_801
EXPECTED_ACCOUNTING_SHA256 = (
    "66a9bd0b5ab8c5f61cd4bdc66b45532810d65b056fcaf8955fff7f366248ab52"
)

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-envelope": (
        71_979,
        "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7",
    ),
    "persona-v2-overlay-contract": (
        71_179,
        "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23",
    ),
}

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
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_solver_execution",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "kio_execution_available",
        "source_instance_matching_available",
    }
)
TOP_LEVEL_KEYS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "checkpoint_contract",
        "completion_claims",
        "completion_scope",
        "evaluation_denominator_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "incidental_move_cap_proof",
        "input_binding_order",
        "input_bindings",
        "metric_contracts",
        "metric_order",
        "move_anchor_contract",
        "operation_delta_contracts",
        "operation_order",
        "remaining_blockers",
        "state_partition_contract",
        "symbol_contracts",
    }
)
PROHIBITED_INSTANCE_KEYS = frozenset(
    {
        "actual_chunk_ids",
        "actual_path",
        "actual_scope_key",
        "compiled_event_ids",
        "final_id",
        "final_plan_id",
        "observed_receipts",
        "path_values",
        "query_instances",
        "scope_ids",
        "source_id",
        "source_ids",
    }
)


class PersonaV2ChunkAccountingValidationError(ValueError):
    """Raised when the accounting body or one of its inputs is invalid."""


def _fail(message):
    raise PersonaV2ChunkAccountingValidationError(message)


def _canonical(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _snapshot(value, *, label, max_bytes):
    raw = _canonical(value, label=label, max_bytes=max_bytes)
    # A canonical round trip is immune to hostile ``__deepcopy__`` methods and
    # fixes the validation snapshot to exactly the bytes authenticated above.
    return json.loads(raw.decode("utf-8", "strict")), raw


def _reauth(value, opening_raw, *, label, max_bytes):
    try:
        current = _canonical(value, label=label, max_bytes=max_bytes)
    except PersonaV2ChunkAccountingValidationError:
        _fail(f"caller-owned {label} changed during validation")
    if current != opening_raw:
        _fail(f"caller-owned {label} changed during validation")


def _require_exact(actual, expected, *, label):
    if _canonical(actual, label=label, max_bytes=MAX_ACCOUNTING_BYTES) != _canonical(
        expected,
        label=f"expected {label}",
        max_bytes=MAX_ACCOUNTING_BYTES,
    ):
        _fail(f"{label} differs from the independent contract")


def _require_exact_int(value, *, label):
    if type(value) is not int:
        _fail(f"{label} must be an exact integer")


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if any(
        type(key) is not str or type(flag) is not bool or flag is not False
        for key, flag in authority.items()
    ):
        _fail(f"{label} authority must be all false")


def _binding(name, role, value, canonical):
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


def _expected_metric_contracts():
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
            "participation_classes": [
                "contract_contributor",
                "incidental_searchable",
            ],
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


def _expected_operation_contracts():
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
                "source-delete-plus-destination-ingest-across-independent-kio-"
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


def _expected_checkpoint_contract(envelope_value):
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


def _expected_move_anchor_contract():
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
        "qIM_definition": (
            "sum-of-five-W0-observed-incidental-move-anchor-chunk-counts"
        ),
        "qIM_inclusive_maximum": 350,
        "qIM_inclusive_minimum": 5,
        "qIM_literal_resolution_stage": (
            "post-W0-attestation-before-W2-event-compilation"
        ),
        "query_oracle_mapping_is_separate_and_explicit": True,
        "semantic_anchor_slots_are_capacity_not_query_ordinals": True,
    }


def _expected_cap_rows(envelope_value):
    rows = []
    for profile in PROFILE_ORDER:
        checkpoint = envelope_value["history_checkpoints"][profile][
            "W5-pre-purge"
        ]
        caps = envelope_value["incidental_cap_contract"]["eligible_caps"][profile]
        current = min(
            caps["base_current"],
            caps["current"] - checkpoint["current_contract_chunks"],
        )
        total = min(
            caps["base_total"],
            caps["total"]
            - checkpoint["current_contract_chunks"]
            - checkpoint["history_only_contract_chunks"],
        )
        move_upper = 5 * 70
        lhs = current + move_upper
        rows.append(
            {
                "incidental_current_upper_bound": current,
                "incidental_total_upper_bound": total,
                "move_history_upper_bound": move_upper,
                "profile": profile,
                "proof_checkpoint": "W5-pre-purge",
                "required_headroom_after_worst_case_move": total - lhs,
                "worst_case_current_plus_move_history": lhs,
                "worst_case_satisfies_total_cap": lhs <= total,
            }
        )
    return rows


def _expected_evaluation_contract():
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


def _expected_body(envelope_value, overlay_value):
    bindings = [
        _binding(
            "persona-v2-envelope",
            "numeric-checkpoint-cap-and-persona-owner",
            envelope_value,
            envelope.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-overlay-contract",
            "scope-qualified-accounting-duplicate-and-recall-owner",
            overlay_value,
            overlay.canonical_json_bytes,
        ),
    ]
    return {
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
        "checkpoint_contract": _expected_checkpoint_contract(envelope_value),
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
        "evaluation_denominator_contract": _expected_evaluation_contract(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "incidental_move_cap_proof": _expected_cap_rows(envelope_value),
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "metric_contracts": _expected_metric_contracts(),
        "metric_order": list(METRIC_ORDER),
        "move_anchor_contract": _expected_move_anchor_contract(),
        "operation_delta_contracts": _expected_operation_contracts(),
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
            {
                "inclusive_maximum": 0,
                "inclusive_minimum": 0,
                "resolution_stage": "authored",
                "symbol": "zero",
            },
            {
                "inclusive_maximum": 1,
                "inclusive_minimum": 1,
                "resolution_stage": "authored",
                "symbol": "one",
            },
            {
                "inclusive_maximum": 5,
                "inclusive_minimum": 5,
                "resolution_stage": "authored",
                "symbol": "nIM",
            },
            {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "resolution_stage": "post-solver-compiled-plan",
                "symbol": "qD",
            },
            {
                "inclusive_maximum": 350,
                "inclusive_minimum": 5,
                "resolution_stage": (
                    "post-W0-attestation-before-W2-event-compilation"
                ),
                "symbol": "qIM",
            },
            {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "resolution_stage": "post-solver-compiled-plan",
                "symbol": "qR",
            },
        ],
    }


def _walk_keys(value):
    if type(value) is dict:
        for key, child in value.items():
            yield key
            yield from _walk_keys(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_keys(child)


def _term_map(operation):
    result = {}
    for term in operation["delta_terms"]:
        key = (term["metric_id"], term["projection"])
        if key in result:
            _fail(f"duplicate operation delta projection: {key!r}")
        _require_exact_int(term["coefficient"], label=f"delta coefficient {key!r}")
        result[key] = (
            term["direction"],
            term["coefficient"],
            term["symbol"],
        )
    return result


def _validate_formula_semantics(value, envelope_value):
    if type(value) is not dict or set(value) != TOP_LEVEL_KEYS:
        _fail("chunk-accounting top-level fields differ from the v1 schema")
    if any(key in PROHIBITED_INSTANCE_KEYS for key in _walk_keys(value)):
        _fail("chunk-accounting body contains a prohibited concrete instance field")
    _require_negative_authority(value, label="chunk accounting")
    if set(value["authority"]) != AUTHORITY_FIELDS:
        _fail("chunk-accounting authority field set differs from the v1 schema")

    metrics = value["metric_contracts"]
    if (
        type(metrics) is not list
        or value["metric_order"] != list(METRIC_ORDER)
        or [row.get("metric_id") for row in metrics] != list(METRIC_ORDER)
    ):
        _fail("four metric domains must be unique and canonically ordered")
    if metrics[0].get("identity_fields_observed") != ["scope_id", "chunk_id"]:
        _fail("search semantic identity must remain scope-qualified")
    if metrics[0].get("chunk_id_is_chunk_hash") is not True:
        _fail("search chunk_id must be explicitly identical to KIO chunk_hash")
    if metrics[1].get("identity_fields") != ["chunk_id"]:
        _fail("persona-global hash identity must remain diagnostic and scopeless")
    if metrics[2].get("identity_fields_observed") != [
        "scope_id",
        "chunk_id",
        "path",
    ]:
        _fail("history path binding identity must remain a separate metric")
    if metrics[0].get("states_are_pairwise_disjoint") is not True:
        _fail("current/history-only semantic endpoint states must be disjoint")

    move = value["move_anchor_contract"]
    for field in (
        "capability_count_per_persona",
        "contributor_semantic_anchor_capacity_consumed",
        "contributor_semantic_anchor_capacity_reserved",
        "contributor_semantic_anchor_capacity_unused",
        "incidental_move_anchor_count",
        "per_source_actual_chunk_inclusive_maximum",
        "per_source_actual_chunk_inclusive_minimum",
        "qIM_inclusive_maximum",
        "qIM_inclusive_minimum",
    ):
        _require_exact_int(move.get(field), label=f"move anchor {field}")
    capabilities = move["anonymous_capability_reclassification"]
    if (
        sum(capabilities.values()) != 105
        or capabilities != {"I": 5, "N": 0, "P": 15, "U": 35, "X": 20, "Y": 30}
        or move["contributor_semantic_anchor_capacity_consumed"]
        + move["incidental_move_anchor_count"]
        != move["contributor_semantic_anchor_capacity_reserved"]
        or move["contributor_semantic_anchor_capacity_unused"] != 5
    ):
        _fail("move-anchor capability reclassification does not close at 105")
    if (
        move["qIM_inclusive_minimum"]
        != move["incidental_move_anchor_count"]
        * move["per_source_actual_chunk_inclusive_minimum"]
        or move["qIM_inclusive_maximum"]
        != move["incidental_move_anchor_count"]
        * move["per_source_actual_chunk_inclusive_maximum"]
        or move["qIM_inclusive_maximum"] > 350
    ):
        _fail("qIM must be five W0-observed source counts in the range 1..70")

    operations = value["operation_delta_contracts"]
    if (
        type(operations) is not list
        or value["operation_order"] != list(OPERATION_ORDER)
        or [row.get("operation_id") for row in operations]
        != list(OPERATION_ORDER)
    ):
        _fail("operation delta table order differs from the v1 schema")
    required_operation_preconditions = {
        "same-scope-rename-contributor": {
            "source-path-is-a-live-contract-contributor-materialization",
            "destination-scope-path-has-no-live-materialization-before-rename",
            "destination-scope-chunk-path-bindings-are-not-reachable-before-rename",
        },
        "same-scope-exact-duplicate-diagnostic": {
            "source-contract-endpoints-are-current-with-a-live-source-path-binding",
            "new-path-has-no-live-materialization-before-duplicate",
            "destination-scope-chunk-path-bindings-are-not-reachable-before-duplicate",
        },
        "cross-scope-exact-duplicate-contributor": {
            "source-contract-endpoints-are-current-with-a-live-source-path-binding",
            "destination-scope-has-no-live-or-reachable-historical-matching-chunk-endpoint",
            "destination-scope-path-has-no-live-materialization-before-duplicate",
            "destination-scope-chunk-path-bindings-are-not-reachable-before-duplicate",
        },
    }
    for operation in operations:
        required = required_operation_preconditions.get(operation["operation_id"])
        if required is not None and not required.issubset(operation["preconditions"]):
            _fail(
                f"{operation['operation_id']} lacks live/path preconditions for its deltas"
            )
    rename, cross_move, same_duplicate, cross_duplicate = map(_term_map, operations)
    zero = ("preserve", 0, "zero")
    physical_projections = {
        "managed-source-regular-files",
        "raw-cas-regular-objects",
        "chunk-cas-regular-objects",
        "managed-source-inodes",
        "raw-cas-inodes",
        "chunk-cas-inodes",
    }
    for operation_id, terms in zip(
        OPERATION_ORDER,
        (rename, cross_move, same_duplicate, cross_duplicate),
        strict=True,
    ):
        actual_physical = {
            projection
            for (metric_id, projection) in terms
            if metric_id == "physical-storage-v1"
        }
        if actual_physical != physical_projections:
            _fail(f"{operation_id} does not close every physical projection")
    if any(
        rename[("search-semantic-endpoint-v1", projection)] != zero
        for projection in (
            "contract-current",
            "contract-history-only",
            "incidental-current",
            "incidental-history-only",
        )
    ):
        _fail("same-scope rename must preserve all semantic endpoint states")
    if cross_move[("search-semantic-endpoint-v1", "contract-current")] != zero or cross_move[
        ("search-semantic-endpoint-v1", "contract-history-only")
    ] != zero:
        _fail("incidental cross-scope move must not alter contract checkpoints")
    expected_move = {
        ("search-semantic-endpoint-v1", "incidental-current"): zero,
        ("search-semantic-endpoint-v1", "incidental-history-only"): (
            "increase",
            1,
            "qIM",
        ),
        ("persona-global-chunk-hash-v1", "distinct-chunk-hashes"): zero,
        ("history-path-binding-v1", "reachable-path-bindings"): (
            "increase",
            1,
            "qIM",
        ),
        ("physical-storage-v1", "managed-source-regular-files"): zero,
        ("physical-storage-v1", "raw-cas-regular-objects"): (
            "increase",
            1,
            "nIM",
        ),
        ("physical-storage-v1", "chunk-cas-regular-objects"): (
            "increase",
            1,
            "qIM",
        ),
        ("physical-storage-v1", "managed-source-inodes"): zero,
        ("physical-storage-v1", "raw-cas-inodes"): ("increase", 1, "nIM"),
        ("physical-storage-v1", "chunk-cas-inodes"): (
            "increase",
            1,
            "qIM",
        ),
    }
    for key, expected in expected_move.items():
        if cross_move.get(key) != expected:
            _fail(f"cross-scope move delta differs for {key!r}")
    if same_duplicate[("search-semantic-endpoint-v1", "contract-current")] != zero:
        _fail("same-scope exact duplicate must collapse as one semantic endpoint")
    if cross_duplicate[("search-semantic-endpoint-v1", "contract-current")] != (
        "increase",
        1,
        "qD",
    ) or cross_duplicate[(
        "persona-global-chunk-hash-v1",
        "distinct-chunk-hashes",
    )] != zero:
        _fail("cross-scope exact duplicate must split endpoint and global projections")

    known_full = (
        (120_000, 0),
        (120_000, 24_000),
        (120_000, 24_000),
        (120_000, 48_000),
        (120_000, 60_000),
        (124_800, 64_800),
        (120_000, 60_000),
    )
    checkpoint_profiles = value["checkpoint_contract"]["profiles"]
    for profile, divisor in (("pilot", 10), ("full", 1)):
        rows = checkpoint_profiles[profile]
        if [row.get("checkpoint") for row in rows] != list(CHECKPOINT_ORDER):
            _fail(f"{profile} checkpoint order differs from the envelope")
        for index, row in enumerate(rows):
            for field in (
                "current_contract_semantic_endpoints",
                "history_only_contract_semantic_endpoints",
                "incidental_move_history_multiplier",
            ):
                _require_exact_int(row.get(field), label=f"{profile} checkpoint {field}")
            expected_current = known_full[index][0] // divisor
            expected_history = known_full[index][1] // divisor
            source = envelope_value["history_checkpoints"][profile][CHECKPOINT_ORDER[index]]
            if (
                row["current_contract_semantic_endpoints"] != expected_current
                or row["history_only_contract_semantic_endpoints"] != expected_history
                or expected_current != source["current_contract_chunks"]
                or expected_history != source["history_only_contract_chunks"]
            ):
                _fail(f"{profile} contract checkpoint literal changed")
            expected_multiplier = 0 if index < 2 else 1
            if row["incidental_move_history_multiplier"] != expected_multiplier:
                _fail("incidental move history must be +qIM from W2 onward only")

    cap_rows = value["incidental_move_cap_proof"]
    if [row.get("profile") for row in cap_rows] != list(PROFILE_ORDER):
        _fail("incidental cap proof profile order differs")
    for row in cap_rows:
        profile = row["profile"]
        for field in (
            "incidental_current_upper_bound",
            "incidental_total_upper_bound",
            "move_history_upper_bound",
            "required_headroom_after_worst_case_move",
            "worst_case_current_plus_move_history",
        ):
            _require_exact_int(row.get(field), label=f"{profile} cap proof {field}")
        checkpoint = envelope_value["history_checkpoints"][profile]["W5-pre-purge"]
        caps = envelope_value["incidental_cap_contract"]["eligible_caps"][profile]
        expected_current = min(
            caps["base_current"],
            caps["current"] - checkpoint["current_contract_chunks"],
        )
        expected_total = min(
            caps["base_total"],
            caps["total"]
            - checkpoint["current_contract_chunks"]
            - checkpoint["history_only_contract_chunks"],
        )
        lhs = expected_current + move["qIM_inclusive_maximum"]
        if row != {
            "incidental_current_upper_bound": expected_current,
            "incidental_total_upper_bound": expected_total,
            "move_history_upper_bound": 350,
            "profile": profile,
            "proof_checkpoint": "W5-pre-purge",
            "required_headroom_after_worst_case_move": expected_total - lhs,
            "worst_case_current_plus_move_history": lhs,
            "worst_case_satisfies_total_cap": lhs <= expected_total,
        }:
            _fail(f"{profile} incidental cap inequality does not close")

    evaluation = value["evaluation_denominator_contract"]
    if evaluation["mvp_performance_denominator"] != ["scope_id", "chunk_hash"]:
        _fail("MVP performance denominator must be scope-qualified chunk hash")
    if evaluation["formal_recall_denominator"] != ["raw_hash", "section"]:
        _fail("formal Recall denominator must remain raw-hash section")
    if evaluation["mvp_performance_denominator"] == evaluation[
        "formal_recall_denominator"
    ]:
        _fail("performance and Recall denominators must not collapse")
    for field in (
        "mvp_performance_minimum_current_endpoints",
        "persona_contract_current_endpoint_target",
    ):
        _require_exact_int(evaluation.get(field), label=field)
    if (
        evaluation["mvp_performance_minimum_current_endpoints"] != 100_000
        or evaluation["persona_contract_current_endpoint_target"] != 120_000
    ):
        _fail("MVP performance threshold and exact persona target must remain separate")


def _validate_dependency_snapshots(envelope_value, overlay_value):
    try:
        envelope.validate_envelope_contract(envelope_value)
        overlay.validate_overlay_contract(overlay_value)
    except (envelope.PersonaV2ContractError, overlay.PersonaV2OverlayContractError) as error:
        _fail(str(error))
    _require_negative_authority(envelope_value, label="persona-v2-envelope")
    _require_negative_authority(overlay_value, label="persona-v2-overlay-contract")
    envelope_raw = envelope.canonical_json_bytes(envelope_value)
    overlay_raw = overlay.canonical_json_bytes(overlay_value)
    if (
        len(envelope_raw),
        hashlib.sha256(envelope_raw).hexdigest(),
    ) != EXPECTED_DEPENDENCY_PINS["persona-v2-envelope"]:
        _fail("persona-v2-envelope dependency pin differs")
    if (
        len(overlay_raw),
        hashlib.sha256(overlay_raw).hexdigest(),
    ) != EXPECTED_DEPENDENCY_PINS["persona-v2-overlay-contract"]:
        _fail("persona-v2-overlay-contract dependency pin differs")
    embedded = next(
        (row for row in overlay_value["input_bindings"] if row.get("name") == "envelope"),
        None,
    )
    if embedded is None or (
        embedded.get("canonical_bytes"),
        embedded.get("sha256"),
    ) != EXPECTED_DEPENDENCY_PINS["persona-v2-envelope"]:
        _fail("overlay and direct envelope bindings are split-brain")


def _validate_snapshot(value, envelope_value, overlay_value):
    _validate_dependency_snapshots(envelope_value, overlay_value)
    _validate_formula_semantics(value, envelope_value)
    expected = _expected_body(envelope_value, overlay_value)
    _require_exact(value, expected, label="chunk-accounting body")
    raw = _canonical(
        value,
        label="persona v2 chunk accounting",
        max_bytes=MAX_ACCOUNTING_BYTES,
    )
    actual_pin = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual_pin != (
        EXPECTED_ACCOUNTING_CANONICAL_BYTES,
        EXPECTED_ACCOUNTING_SHA256,
    ):
        _fail("chunk-accounting body differs from its external canonical pin")
    return True


def validate_chunk_accounting_contract(
    value,
    *,
    envelope_value,
    overlay_contract_value,
):
    """Validate detached snapshots and reauthenticate all caller-owned inputs."""

    value_snapshot, value_raw = _snapshot(
        value,
        label="persona v2 chunk accounting",
        max_bytes=MAX_ACCOUNTING_BYTES,
    )
    envelope_snapshot, envelope_raw = _snapshot(
        envelope_value,
        label="persona v2 envelope input",
        max_bytes=MAX_DEPENDENCY_BYTES,
    )
    overlay_snapshot, overlay_raw = _snapshot(
        overlay_contract_value,
        label="persona v2 overlay contract input",
        max_bytes=MAX_DEPENDENCY_BYTES,
    )
    try:
        return _validate_snapshot(
            value_snapshot,
            envelope_snapshot,
            overlay_snapshot,
        )
    finally:
        _reauth(
            value,
            value_raw,
            label="chunk accounting",
            max_bytes=MAX_ACCOUNTING_BYTES,
        )
        _reauth(
            envelope_value,
            envelope_raw,
            label="envelope input",
            max_bytes=MAX_DEPENDENCY_BYTES,
        )
        _reauth(
            overlay_contract_value,
            overlay_raw,
            label="overlay contract input",
            max_bytes=MAX_DEPENDENCY_BYTES,
        )


__all__ = [
    "EXPECTED_ACCOUNTING_CANONICAL_BYTES",
    "EXPECTED_ACCOUNTING_SHA256",
    "PersonaV2ChunkAccountingValidationError",
    "validate_chunk_accounting_contract",
]
