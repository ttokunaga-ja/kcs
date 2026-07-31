"""Builder-independent validation for persona-PC lifecycle demand v2.

This module imports neither the lifecycle-demand producer nor any executor.
It validates a bounded canonical snapshot, authenticates the externally pinned
body, checks the demand algebra independently, and then re-authenticates the
caller-owned body.  There are no provider callbacks in this artifact layer;
the closing re-authentication still detects mutation during validation.
"""

from __future__ import annotations

import hashlib
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_chunk_accounting_validator as chunk_accounting_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_chunk_accounting_validator as chunk_accounting_validator


ARTIFACT_SCHEMA = "kio.persona.pc-lifecycle-demand/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-lifecycle-demand"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_LIFECYCLE_DEMAND_BYTES = 2 * 1024 * 1024
MAX_ORIGIN_PAYLOAD_BYTES = 256 * 1024
MAX_ACCOUNTING_BYTES = 256 * 1024
MAX_DEPENDENCY_BYTES = 2 * 1024 * 1024

EXPECTED_CHUNK_ACCOUNTING_CANONICAL_BYTES = 19_801
EXPECTED_CHUNK_ACCOUNTING_SHA256 = (
    "66a9bd0b5ab8c5f61cd4bdc66b45532810d65b056fcaf8955fff7f366248ab52"
)

# Installed only after the producer body is complete.  This is an external
# body pin; no self hash appears in the artifact.
EXPECTED_LIFECYCLE_DEMAND_CANONICAL_BYTES = 463_571
EXPECTED_LIFECYCLE_DEMAND_SHA256 = (
    "372a466e3994c9e41662457f144fc03338d96b76f57f9306e62bbe9511422005"
)

PERSONA_IDS = tuple(f"p{index:02d}" for index in range(1, 21))
PROFILE_ORDER = ("pilot", "full")
ALLOCATION_CLASS_ORDER = ("P", "X", "Y", "N", "U", "I")
HISTORY_COHORT_ORDER = ("P", "X", "Y", "N", "U")
WAVE_ORDER = ("W1", "W2", "W3", "W4", "W5")

AUTHORITY_FIELDS = frozenset(
    {
        "actual_history_receipts_attested",
        "actual_state_cardinalities_attested",
        "authorizes_compiled_history_plan",
        "authorizes_evaluation_target_resolution",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_source_instance_matching",
        "authorizes_solver_execution",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "source_instance_matching_available",
    }
)

BOOLEAN_FIELD_NAMES = frozenset(
    set(AUTHORITY_FIELDS)
    | {
        "anonymous_capability_demand_complete",
        "anonymous_capability_may_satisfy_multiple_states",
        "accounting_operation_match_required",
        "accounting_sidecar_bound",
        "actual_physical_delta_attested",
        "all_event_metric_specific_delta_rules_present",
        "compiled_literal_delta_available",
        "compiled_literal_requires_w0_attestation",
        "compiled_event_instances_present",
        "compiled_history_plan",
        "concrete_locations_present",
        "copying_replaced_content_satisfies",
        "cross_scope_move_metric_delta_rules_present",
        "cross_scope_move_metric_projection_complete",
        "chunk_accounting_contract_bound",
        "destination_objects_absent_before_move_required",
        "destination_live_materialization_absent_before_move_required",
        "different_leaf_scope_required",
        "empty_selection_satisfies",
        "evaluation_ordinal_inference_allowed",
        "evaluation_target_mapping_present",
        "event_template_symbolic_delta_complete",
        "execution_identifiers_present",
        "framed_byte_cap_before_body_required",
        "full_profile_must_reuse_pilot_origin_payload_bytes",
        "full_must_reuse_pilot_move_selection_bytes",
        "g0_contract_frozen",
        "lifecycle_disjointness_complete",
        "metric_specific_cardinalities_present",
        "metric_specific_current_history_delta_complete",
        "independent_store_transition_required",
        "null_float_or_negative_integer_allowed",
        "paired_x_prime_delete_required",
        "pairwise_disjoint_required",
        "pilot_origin_full_byte_reuse_proved",
        "planned_destination_endpoints_pairwise_noncolliding_required",
        "planned_destination_managed_locations_pairwise_distinct_required",
        "profile_specific_capability_regeneration_allowed",
        "product_move_lineage_semantics_allowed",
        "raw_payloads_distinct_per_anchor_required",
        "raw_objects_absent_before_move_required",
        "same_persona_required",
        "same_scope_required",
        "self_hash_embedded",
        "source_instance_matching_complete",
        "source_instance_matching_required",
        "per_anchor_positive_observation_required",
        "passes_total_upper",
        "physical_file_inode_object_receipts_attested",
        "physical_file_inode_object_receipts_required",
        "physical_projection_requires_all_move_preconditions",
        "symbolic_demand_compiled_to_events",
    }
)

INTEGER_FIELD_NAMES = frozenset(
    {
        "N",
        "P",
        "I",
        "U",
        "X",
        "Y",
        "anonymous_capability_count",
        "anonymous_capability_count_per_persona",
        "anchor_count_per_persona",
        "archive-history",
        "artifact_schema_version",
        "canonical_bytes",
        "coefficient",
        "component_count",
        "component_inclusive_maximum",
        "component_inclusive_minimum",
        "combined_current_plus_move_history_upper",
        "contract_contributor_capability_count",
        "contributor_capabilities_requiring_capacity_per_persona",
        "cross-scope-move",
        "current-restored",
        "derive_emphasis_witness_count",
        "exact_duplicate_emphasis_witness_count",
        "final-deleted",
        "fixture_schema_version",
        "locale-history",
        "incidental_current_upper",
        "incidental_move_capabilities_unreserved_per_persona",
        "incidental_searchable_capability_count",
        "incidental_total_upper",
        "m3-1-current",
        "matched_move_source_count_exact",
        "max_body_bytes",
        "max_nesting_depth",
        "max_string_bytes",
        "move_history_upper",
        "old-wording-history",
        "origin_payload_canonical_bytes",
        "per_anchor_observed_upper",
        "per_anchor_observed_lower",
        "observed_symbol_lower",
        "observed_symbol_upper",
        "persona_count",
        "profile_binding_count",
        "pre_solve_upper",
        "purged",
        "purged-negative",
        "required_count_per_persona",
        "required_witness_count",
        "result_inclusive_maximum",
        "result_inclusive_minimum",
        "right_integer",
        "same-scope-rename",
        "source_scope_live_binding_multiplicity_exact",
        "structural_transition_units",
        "unused_contributor_capacity_per_persona",
        "available_contributor_capacity_per_persona",
    }
)

TOP_LEVEL_KEYS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "anchor_capacity_contract",
        "boundary_assertions",
        "canonical_limits",
        "capability_class_contracts",
        "allocation_class_contracts",
        "compiled_history_plan",
        "completion_claims",
        "completion_scope",
        "cross_scope_move_metric_contract",
        "dependency_groups",
        "emphasis_witness_demands",
        "event_templates",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "incidental_capacity_reservation",
        "input_binding_order",
        "input_bindings",
        "lifecycle_disjointness_contract",
        "location_transition_rules",
        "orders",
        "origin_policy",
        "persona_demands",
        "remaining_blockers",
        "replacement_contracts",
        "scope_relation_rules",
        "transition_algebra_model",
        "suite_summary",
        "wave_delta_rules",
    }
)

_EVENT = {
    "w1-p": "lifecycle-template-w1-edit-p-v2",
    "w1-x": "lifecycle-template-w1-edit-x-v2",
    "w1-y": "lifecycle-template-w1-edit-y-v2",
    "w2-rename-u": "lifecycle-template-w2-rename-u-v2",
    "w2-move-i": "lifecycle-template-w2-cross-scope-move-i-v2",
    "w3-x": "lifecycle-template-w3-edit-x-v2",
    "w3-y": "lifecycle-template-w3-edit-y-v2",
    "w3-n": "lifecycle-template-w3-edit-n-v2",
    "w3-derive": "lifecycle-template-w3-derive-emphasis-v2",
    "w3-duplicate": "lifecycle-template-w3-duplicate-emphasis-v2",
    "w4-delete-x": "lifecycle-template-w4-delete-x-v2",
    "w4-x-prime": "lifecycle-template-w4-create-x-prime-v2",
    "w4-archive-y": "lifecycle-template-w4-archive-y-v2",
    "w5-n": "lifecycle-template-w5-correct-n-v2",
    "w5-p-prime": "lifecycle-template-w5-create-p-prime-v2",
    "w5-export-x": "lifecycle-template-w5-export-deleted-x-v2",
    "w5-reingest-x": "lifecycle-template-w5-reingest-x-v2",
    "w5-delete-x-prime": "lifecycle-template-w5-delete-paired-x-prime-v2",
    "w5-purge-p": "lifecycle-template-w5-purge-p-v2",
}

_CAPABILITY_CLASSES = (
    ("m3-1-current", "U", "contract_contributor", ("U",), 30, "current", ()),
    ("same-scope-rename", "U", "contract_contributor", ("U",), 5, "current-after-rename", (_EVENT["w2-rename-u"],)),
    ("cross-scope-move", "I", "incidental_searchable", (), 5, "current-after-move", (_EVENT["w2-move-i"],)),
    ("old-wording-history", "Y", "contract_contributor", ("Y",), 10, "old-wording-history", (_EVENT["w1-y"],)),
    ("locale-history", "Y", "contract_contributor", ("Y",), 10, "locale-history", (_EVENT["w3-y"],)),
    ("archive-history", "Y", "contract_contributor", ("Y",), 10, "archive-history", (_EVENT["w4-archive-y"],)),
    ("final-deleted", "X", "contract_contributor", ("X",), 10, "final-deleted", (_EVENT["w1-x"], _EVENT["w3-x"], _EVENT["w4-delete-x"], _EVENT["w4-x-prime"])),
    (
        "current-restored",
        "X",
        "contract_contributor",
        ("X",),
        10,
        "current-restored",
        (
            _EVENT["w1-x"],
            _EVENT["w3-x"],
            _EVENT["w4-delete-x"],
            _EVENT["w4-x-prime"],
            _EVENT["w5-export-x"],
            _EVENT["w5-reingest-x"],
            _EVENT["w5-delete-x-prime"],
        ),
    ),
    ("purged-negative", "P", "contract_contributor", ("P",), 15, "purged", (_EVENT["w1-p"], _EVENT["w5-p-prime"], _EVENT["w5-purge-p"])),
)

# short key, wave, operation, allocation class, symbol, current direction,
# historical direction,
# scope rule, location rule, fact relation, replacement contracts, groups
_EVENT_ROWS = (
    ("w1-p", "W1", "semantic-edit", "P", "qP", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "new-version-with-revised-facts", (), ()),
    ("w1-x", "W1", "semantic-edit", "X", "qX", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "new-version-with-revised-facts", (), ()),
    ("w1-y", "W1", "semantic-edit", "Y", "qY", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "new-version-with-revised-facts", (), ()),
    ("w2-rename-u", "W2", "rename", "U", "zero", "preserve", "preserve", "same-bound-leaf-scope", "replace-basename-in-same-scope", "exact-fact-carry-forward", (), ()),
    ("w2-move-i", "W2", "cross-scope-source-delete-destination-ingest", "I", "qIM", "preserve", "preserve", "different-bound-leaf-scope-same-persona", "move-to-different-leaf-scope", "exact-fact-carry-forward", (), ()),
    ("w3-x", "W3", "surface-edit", "X", "qX", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "exact-fact-carry-forward", (), ()),
    ("w3-y", "W3", "surface-edit", "Y", "qY", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "exact-fact-carry-forward", (), ()),
    ("w3-n", "W3", "surface-edit", "N", "qN", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "exact-fact-carry-forward", (), ()),
    ("w3-derive", "W3", "derive-witness", "U", "zero", "preserve", "preserve", "downstream-selected-valid-leaf-scope", "create-distinct-derived-location", "derived-facts-must-remain-distinct", (), ("derive-emphasis-witness",)),
    ("w3-duplicate", "W3", "exact-duplicate-witness", "U", "zero", "preserve", "preserve", "downstream-selected-valid-leaf-scope", "create-distinct-duplicate-location", "exact-fact-carry-forward", (), ("duplicate-emphasis-witness",)),
    ("w4-delete-x", "W4", "delete", "X", "qX", "decrease", "increase", "same-bound-leaf-scope", "remove-live-location", "exact-fact-carry-forward", (), ("w4-x-capacity-balance",)),
    ("w4-x-prime", "W4", "capacity-replacement-create-index", "X", "qX", "increase", "preserve", "same-capacity-scope-as-replaced-cohort", "create-distinct-capacity-replacement-location", "distinct-replacement-facts", ("X-prime",), ("w4-x-capacity-balance",)),
    ("w4-archive-y", "W4", "archive", "Y", "zero", "preserve", "preserve", "same-bound-leaf-scope", "move-under-existing-archive-container", "exact-fact-carry-forward", (), ()),
    ("w5-n", "W5", "surface-correction", "N", "qN", "preserve", "increase", "same-bound-leaf-scope", "preserve-relative-location", "exact-fact-carry-forward", (), ("w5-final-checkpoint-closure",)),
    ("w5-p-prime", "W5", "capacity-replacement-create-index", "P", "qP", "increase", "preserve", "same-capacity-scope-as-replaced-cohort", "create-distinct-capacity-replacement-location", "distinct-replacement-facts", ("P-prime",), ("w5-p-capacity-and-purge", "w5-final-checkpoint-closure")),
    ("w5-export-x", "W5", "export-deleted", "X", "zero", "preserve", "preserve", "nonsearchable-export-staging", "emit-nonsearchable-export", "exact-fact-carry-forward", (), ("w5-restore-x-net-zero",)),
    ("w5-reingest-x", "W5", "reingest-and-index", "X", "qXR", "increase", "decrease", "downstream-selected-valid-leaf-scope", "create-restored-live-location", "exact-fact-carry-forward", (), ("w5-restore-x-net-zero",)),
    ("w5-delete-x-prime", "W5", "paired-capacity-filler-delete", "X", "qXR", "decrease", "increase", "same-capacity-scope-as-replaced-cohort", "remove-live-location", "distinct-replacement-facts", ("X-prime",), ("w5-restore-x-net-zero",)),
    ("w5-purge-p", "W5", "purge", "P", "qP", "decrease", "decrease", "same-bound-leaf-scope", "remove-live-and-reachable-history", "no-fact-carry-forward", ("P-prime",), ("w5-p-capacity-and-purge", "w5-final-checkpoint-closure")),
)


class PersonaV2LifecycleDemandValidationError(ValueError):
    """Raised when a lifecycle-demand body fails independent validation."""


def _fail(message):
    raise PersonaV2LifecycleDemandValidationError(message)


def _canonical(value, *, label="persona v2 lifecycle demand", max_bytes=MAX_LIFECYCLE_DEMAND_BYTES):
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
    return json.loads(raw.decode("utf-8", "strict")), raw


def _reauth(value, opening_raw, *, label, max_bytes):
    try:
        current = _canonical(value, label=label, max_bytes=max_bytes)
    except PersonaV2LifecycleDemandValidationError:
        _fail(f"caller-owned {label} changed during validation")
    if current != opening_raw:
        _fail(f"caller-owned {label} changed during validation")


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(key) is not str or type(flag) is not bool or flag is not False
        for key, flag in authority.items()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _expected_accounting_binding(value):
    raw = _canonical(
        value,
        label="persona v2 chunk accounting input",
        max_bytes=MAX_ACCOUNTING_BYTES,
    )
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual != (
        EXPECTED_CHUNK_ACCOUNTING_CANONICAL_BYTES,
        EXPECTED_CHUNK_ACCOUNTING_SHA256,
    ):
        _fail("persona-v2-chunk-accounting differs from its frozen dependency pin")
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": actual[0],
        "dependency_role": "cross-scope-move-metric-identity-and-delta-contract",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "persona-v2-chunk-accounting",
        "sha256": actual[1],
    }


def _accounting_term(metric_id, projection, direction, coefficient, symbol):
    return {
        "coefficient": coefficient,
        "direction": direction,
        "metric_id": metric_id,
        "projection": projection,
        "symbol": symbol,
    }


def _expected_accounting_cross_scope_move_operation():
    return {
        "delta_terms": [
            _accounting_term(
                "search-semantic-endpoint-v1",
                "contract-current",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "search-semantic-endpoint-v1",
                "contract-history-only",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "search-semantic-endpoint-v1",
                "incidental-current",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "search-semantic-endpoint-v1",
                "incidental-history-only",
                "increase",
                1,
                "qIM",
            ),
            _accounting_term(
                "persona-global-chunk-hash-v1",
                "distinct-chunk-hashes",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "history-path-binding-v1",
                "reachable-path-bindings",
                "increase",
                1,
                "qIM",
            ),
            _accounting_term(
                "physical-storage-v1",
                "managed-source-regular-files",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "physical-storage-v1",
                "raw-cas-regular-objects",
                "increase",
                1,
                "nIM",
            ),
            _accounting_term(
                "physical-storage-v1",
                "chunk-cas-regular-objects",
                "increase",
                1,
                "qIM",
            ),
            _accounting_term(
                "physical-storage-v1",
                "managed-source-inodes",
                "preserve",
                0,
                "zero",
            ),
            _accounting_term(
                "physical-storage-v1",
                "raw-cas-inodes",
                "increase",
                1,
                "nIM",
            ),
            _accounting_term(
                "physical-storage-v1",
                "chunk-cas-inodes",
                "increase",
                1,
                "qIM",
            ),
        ],
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
    }


def _expected_ledger_dimension_schema_crosswalk():
    projections = {
        "search-semantic-endpoint-v1": [
            "contract-current",
            "contract-history-only",
            "incidental-current",
            "incidental-history-only",
        ],
        "persona-global-chunk-hash-v1": ["distinct-chunk-hashes"],
        "history-path-binding-v1": ["reachable-path-bindings"],
        "physical-storage-v1": [
            "managed-source-regular-files",
            "raw-cas-regular-objects",
            "chunk-cas-regular-objects",
            "managed-source-inodes",
            "raw-cas-inodes",
            "chunk-cas-inodes",
        ],
    }
    return [
        {
            "accounting_metric_id": metric_id,
            "mapping_rule": "exact-projection-name-and-delta",
            "projection_mappings": [
                {
                    "accounting_projection": projection,
                    "lifecycle_dimension_key": projection,
                }
                for projection in projections[metric_id]
            ],
        }
        for metric_id in (
            "search-semantic-endpoint-v1",
            "persona-global-chunk-hash-v1",
            "history-path-binding-v1",
            "physical-storage-v1",
        )
    ]


def _require_exact_dict(value, keys, *, label):
    if type(value) is not dict or set(value) != set(keys):
        _fail(f"{label} field set drifted")


def _require_exact_list(value, *, label):
    if type(value) is not list:
        _fail(f"{label} must be an exact list")


def _assert_forbidden_later_layer_fields_absent(value):
    forbidden_exact = {
        "absolute_path",
        "chunk_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "oracle_key",
        "planned_materialization_id",
        "planned_source_id",
        "query_id",
        "query_key",
        "query_text",
        "raw_id",
        "relative_path",
        "scope_path",
        "source_id",
    }
    if type(value) is list:
        for item in value:
            _assert_forbidden_later_layer_fields_absent(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in forbidden_exact or "quota" in key:
            _fail("later-layer identity, location, cardinality, or evaluation field is present")
        _assert_forbidden_later_layer_fields_absent(item)


def _assert_exact_scalar_types(value):
    """Reject Python bool/int equality aliases throughout the exact schema."""

    if type(value) is list:
        for item in value:
            _assert_exact_scalar_types(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in BOOLEAN_FIELD_NAMES and type(item) is not bool:
            _fail("lifecycle boolean field must use the exact JSON boolean type")
        if key in INTEGER_FIELD_NAMES and type(item) is not int:
            _fail("lifecycle integer field must use the exact JSON integer type")
        _assert_exact_scalar_types(item)


def _delta_cell(direction, coefficient, symbol):
    return {"coefficient": coefficient, "direction": direction, "symbol": symbol}


def _expected_event_templates():
    rows = []
    for (
        short_key,
        wave,
        operation,
        allocation_class,
        symbol,
        current_direction,
        history_direction,
        scope_rule,
        location_rule,
        fact_rule,
        replacement_keys,
        dependency_keys,
    ) in _EVENT_ROWS:
        coefficient = 0 if symbol == "zero" else 1
        is_incidental_move = short_key == "w2-move-i"
        rows.append(
            {
                "cardinality_binding_mode": (
                    "post-w0-observed-ledger-symbol-with-pre-solve-upper"
                    if is_incidental_move
                    else (
                        "exact-zero-structural"
                        if symbol == "zero"
                        else "downstream-symbolic-cohort-transition-units"
                    )
                ),
                "allocation_class": allocation_class,
                "delta_rule": {
                    "current_transition_units": _delta_cell(
                        current_direction,
                        0 if current_direction == "preserve" else coefficient,
                        "zero" if current_direction == "preserve" else symbol,
                    ),
                    "historical_transition_units": _delta_cell(
                        history_direction,
                        0 if history_direction == "preserve" else coefficient,
                        "zero" if history_direction == "preserve" else symbol,
                    ),
                },
                "dependency_group_keys": list(dependency_keys),
                "delta_rule_interpretation": (
                    "contract-participation-search-semantic-endpoint-only"
                    if is_incidental_move
                    else "abstract-transition-units-not-metric-specific"
                ),
                "event_template_key": _EVENT[short_key],
                "fact_relation_rule": fact_rule,
                "gate_role_requirement": (
                    "incidental_searchable"
                    if allocation_class == "I"
                    else "contract_contributor"
                ),
                "history_cohort_keys": (
                    [] if allocation_class == "I" else [allocation_class]
                ),
                "location_transition_rule_key": location_rule,
                "metric_projection_contract_keys": (
                    ["cross-scope-move-metric-v1"] if is_incidental_move else []
                ),
                "operation_kind": operation,
                "replacement_contract_keys": list(replacement_keys),
                "scope_relation_rule_key": scope_rule,
                "wave": wave,
            }
        )
    return rows


def _expected_class_contracts():
    return [
        {
            "allocation_class": allocation_class,
            "anonymous_capability_count_per_persona": count,
            "capability_class_key": class_key,
            "gate_role_requirement": gate_role,
            "history_cohort_keys": list(history_cohorts),
            "required_evidence_state": state,
            "required_event_template_keys": list(event_keys),
        }
        for (
            class_key,
            allocation_class,
            gate_role,
            history_cohorts,
            count,
            state,
            event_keys,
        ) in _CAPABILITY_CLASSES
    ]


def _expected_capabilities():
    rows = []
    ordinal = 1
    for (
        class_key,
        allocation_class,
        gate_role,
        history_cohorts,
        count,
        _,
        _,
    ) in _CAPABILITY_CLASSES:
        for _ in range(count):
            rows.append(
                {
                    "allocation_class": allocation_class,
                    "anonymous_capability_key": f"anonymous-capability-{ordinal:03d}",
                    "capability_class_key": class_key,
                    "gate_role_requirement": gate_role,
                    "history_cohort_keys": list(history_cohorts),
                }
            )
            ordinal += 1
    return rows


def _validate_identity_and_authority(value):
    _require_exact_dict(value, TOP_LEVEL_KEYS, label="lifecycle demand")
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or type(value["artifact_schema_version"]) is not int
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != FIXTURE_ID
        or type(value["fixture_schema_version"]) is not int
        or value["fixture_schema_version"] != FIXTURE_SCHEMA_VERSION
    ):
        _fail("lifecycle demand identity drifted")
    authority = value["authority"]
    _require_exact_dict(authority, AUTHORITY_FIELDS, label="lifecycle demand authority")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail("lifecycle demand authority must remain exact all-false")
    if value["g0_contract_frozen"] is not False or value["compiled_history_plan"] is not False:
        _fail("pre-solve lifecycle demand cannot be G0 or a compiled history plan")
    if value["completion_scope"] != "pre-solve-anonymous-lifecycle-demand-and-symbolic-event-templates-only":
        _fail("lifecycle completion scope drifted")


def _validate_boundaries(value):
    expected_limits = {
        "framed_byte_cap_before_body_required": True,
        "max_body_bytes": MAX_LIFECYCLE_DEMAND_BYTES,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "null_float_or_negative_integer_allowed": False,
        "self_hash_embedded": False,
        "unicode_normalization": "NFC",
    }
    if value["canonical_limits"] != expected_limits:
        _fail("lifecycle canonical limits drifted")
    expected_boundaries = {
        "accounting_sidecar_bound": True,
        "metric_specific_cardinalities_present": False,
        "compiled_event_instances_present": False,
        "concrete_locations_present": False,
        "evaluation_target_mapping_present": False,
        "execution_identifiers_present": False,
        "source_instance_matching_complete": False,
    }
    if value["boundary_assertions"] != expected_boundaries:
        _fail("lifecycle pre-solve boundary assertions drifted")
    expected_claims = {
        "anonymous_capability_demand_complete": True,
        "chunk_accounting_contract_bound": True,
        "event_template_symbolic_delta_complete": True,
        "lifecycle_disjointness_complete": True,
        "pilot_origin_full_byte_reuse_proved": True,
        "source_instance_matching_complete": False,
        "symbolic_demand_compiled_to_events": False,
        "metric_specific_current_history_delta_complete": False,
        "cross_scope_move_metric_projection_complete": True,
    }
    if value["completion_claims"] != expected_claims:
        _fail("lifecycle completion claims drifted")
    if value["origin_policy"] != {
        "full_profile_must_reuse_pilot_origin_payload_bytes": True,
        "origin_key": "pilot",
        "profile_specific_capability_regeneration_allowed": False,
    }:
        _fail("pilot-origin/full-reuse policy drifted")
    if value["orders"] != {
        "allocation_class_order": list(ALLOCATION_CLASS_ORDER),
        "history_cohort_order": list(HISTORY_COHORT_ORDER),
        "persona_order": list(PERSONA_IDS),
        "profile_order": list(PROFILE_ORDER),
        "wave_order": list(WAVE_ORDER),
    }:
        _fail("lifecycle canonical orders drifted")


def _validate_capability_contracts(value):
    if value["capability_class_contracts"] != _expected_class_contracts():
        _fail("anonymous capability class contract drifted")
    counts = {
        allocation_class: 0 for allocation_class in ALLOCATION_CLASS_ORDER
    }
    for _, allocation_class, _, _, count, _, _ in _CAPABILITY_CLASSES:
        counts[allocation_class] += count
    if counts != {"P": 15, "X": 20, "Y": 30, "N": 0, "U": 35, "I": 5}:
        _fail("per-persona allocation-class capability counts drifted")
    event_keys_by_class = {
        allocation_class: [] for allocation_class in ALLOCATION_CLASS_ORDER
    }
    for row in _expected_event_templates():
        event_keys_by_class[row["allocation_class"]].append(
            row["event_template_key"]
        )
    expected_classes = [
        {
            "allocation_class": allocation_class,
            "anonymous_capability_count_per_persona": counts[allocation_class],
            "eligible_event_template_keys": event_keys_by_class[allocation_class],
            "gate_role_requirement": (
                "incidental_searchable"
                if allocation_class == "I"
                else "contract_contributor"
            ),
            "history_cohort_keys": (
                [] if allocation_class == "I" else [allocation_class]
            ),
            "source_instance_matching_status": "unbound",
            "transition_unit_symbols": (
                ["qIM"] if allocation_class == "I" else [f"q{allocation_class}"]
            ),
        }
        for allocation_class in ALLOCATION_CLASS_ORDER
    ]
    if value["allocation_class_contracts"] != expected_classes:
        _fail("allocation-class or source-instance boundary drifted")


def _validate_cross_scope_move_accounting_boundary(value):
    expected_capacity = {
        "available_contributor_capacity_per_persona": 105,
        "contributor_capabilities_requiring_capacity_per_persona": 100,
        "evaluation_ordinal_inference_allowed": False,
        "incidental_move_capabilities_unreserved_per_persona": 5,
        "mapping_status": "unbound",
        "unused_contributor_capacity_per_persona": 5,
        "unused_contributor_capacity_status": "reserved-unused",
    }
    if value["anchor_capacity_contract"] != expected_capacity:
        _fail("semantic-anchor capacity separation drifted")

    expected_metric = {
        "accounting_operation_contract": _expected_accounting_cross_scope_move_operation(),
        "accounting_operation_match_required": True,
        "accounting_sidecar_binding_status": "bound-and-authenticated",
        "allocation_class": "I",
        "anchor_count_per_persona": 5,
        "actual_physical_delta_attested": False,
        "compiled_literal_delta_available": False,
        "compiled_literal_requires_w0_attestation": True,
        "chunk_configuration_relation": "must-match-source-exactly",
        "chunk_set_relation": "exact-carry-forward-source-to-destination",
        "destination_endpoint_collision_precondition": "no-live-historical-or-cas-endpoint-collision",
        "destination_live_materialization_absent_before_move_required": True,
        "destination_objects_absent_before_move_required": True,
        "delta_evidence_status": "planned-conditional-not-actual-attested",
        "event_template_key": _EVENT["w2-move-i"],
        "full_must_reuse_pilot_move_selection_bytes": True,
        "gate_role_requirement": "incidental_searchable",
        "history_cohort_keys": [],
        "independent_store_transition_required": True,
        "generation_profile_relation": "must-match-source-exactly",
        "ledger_dimension_schema_crosswalk": _expected_ledger_dimension_schema_crosswalk(),
        "move_metric_contract_key": "cross-scope-move-metric-v1",
        "matched_move_source_count_exact": 5,
        "matched_move_source_count_symbol": "nIM",
        "observed_symbol": "qIM",
        "observed_symbol_aggregation_rule": "sum-exact-five-matched-anchor-observations",
        "observed_symbol_binding_checkpoint": "W0",
        "observed_symbol_definition": "per-person-sum-of-five-w0-observed-source-endpoint-chunk-counts",
        "observed_symbol_lower": 5,
        "observed_symbol_upper": 350,
        "per_anchor_observed_lower": 1,
        "per_anchor_observed_upper": 70,
        "per_anchor_positive_observation_required": True,
        "pre_solve_upper": 350,
        "pre_solve_upper_symbol": "uIM",
        "planned_destination_endpoint_precondition": "all-planned-destination-scope-chunk-endpoints-are-pairwise-distinct",
        "planned_destination_endpoints_pairwise_noncolliding_required": True,
        "planned_destination_managed_location_precondition": "all-planned-destination-scope-path-materializations-are-pairwise-distinct",
        "planned_destination_managed_locations_pairwise_distinct_required": True,
        "planned_destination_materialization_absence_precondition": "each-destination-scope-path-has-no-live-materialization-before-its-move",
        "physical_file_inode_object_receipts_attested": False,
        "physical_file_inode_object_receipts_required": True,
        "physical_projection_requires_all_move_preconditions": True,
        "physical_projection_status": "planned-conditional",
        "product_move_lineage_semantics_allowed": False,
        "raw_bytes_relation": "byte-identical-source-to-destination",
        "raw_payloads_distinct_per_anchor_required": True,
        "raw_objects_absent_before_move_required": True,
        "source_scope_live_binding_multiplicity_exact": 1,
        "source_instance_matching_status": "unbound",
        "symbol_capacity_relations": [
            {
                "left_symbol": "qIM",
                "relation": "less-than-or-equal",
                "right_symbol": "uIM",
            },
            {
                "left_symbol": "uIM",
                "relation": "equal-integer",
                "right_integer": 350,
            },
            {
                "left_symbol": "nIM",
                "relation": "equal-integer",
                "right_integer": 5,
            },
        ],
        "tool_profile_relation": "must-match-source-exactly",
        "w0_endpoint_chunk_sum_contract": {
            "component_count": 5,
            "component_inclusive_maximum": 70,
            "component_inclusive_minimum": 1,
            "component_kind": "matched-anonymous-incidental-source-endpoint-chunk-count",
            "component_observation_checkpoint": "W0",
            "persona_aggregation": "exact-sum",
            "result_inclusive_maximum": 350,
            "result_inclusive_minimum": 5,
            "result_symbol": "qIM",
        },
    }
    if value["cross_scope_move_metric_contract"] != expected_metric:
        _fail("cross-scope incidental move metric projection drifted")
    operation_terms = expected_metric["accounting_operation_contract"]["delta_terms"]
    operation_pairs = [
        (term["metric_id"], term["projection"]) for term in operation_terms
    ]
    crosswalk_pairs = [
        (row["accounting_metric_id"], mapping["accounting_projection"])
        for row in expected_metric["ledger_dimension_schema_crosswalk"]
        for mapping in row["projection_mappings"]
    ]
    if (
        len(operation_pairs) != 12
        or len(set(operation_pairs)) != 12
        or operation_pairs != crosswalk_pairs
        or {
            row["accounting_metric_id"]
            for row in expected_metric["ledger_dimension_schema_crosswalk"]
        }
        != {
            "search-semantic-endpoint-v1",
            "persona-global-chunk-hash-v1",
            "history-path-binding-v1",
            "physical-storage-v1",
        }
    ):
        _fail("four-ledger accounting projection crosswalk does not close")
    w0_sum = expected_metric["w0_endpoint_chunk_sum_contract"]
    if (
        expected_metric["anchor_count_per_persona"]
        != expected_metric["matched_move_source_count_exact"]
        or expected_metric["anchor_count_per_persona"]
        * expected_metric["per_anchor_observed_lower"]
        != expected_metric["observed_symbol_lower"]
        or expected_metric["anchor_count_per_persona"]
        * expected_metric["per_anchor_observed_upper"]
        != expected_metric["observed_symbol_upper"]
        or expected_metric["observed_symbol_upper"]
        != expected_metric["pre_solve_upper"]
        or w0_sum["component_count"]
        * w0_sum["component_inclusive_minimum"]
        != w0_sum["result_inclusive_minimum"]
        or w0_sum["component_count"]
        * w0_sum["component_inclusive_maximum"]
        != w0_sum["result_inclusive_maximum"]
        or w0_sum["result_inclusive_minimum"]
        != expected_metric["observed_symbol_lower"]
        or w0_sum["result_inclusive_maximum"]
        != expected_metric["observed_symbol_upper"]
        or expected_metric["matched_move_source_count_exact"] != 5
        or expected_metric["pre_solve_upper"] != 350
    ):
        _fail("cross-scope move pre-solve upper does not close")
    relation_rows = expected_metric["symbol_capacity_relations"]
    if relation_rows[1]["right_integer"] != expected_metric["pre_solve_upper"]:
        _fail("uIM literal does not equal the move pre-solve upper")
    if relation_rows[2]["right_integer"] != expected_metric["matched_move_source_count_exact"]:
        _fail("nIM literal does not equal the matched move source count")
    if expected_metric["observed_symbol_upper"] > relation_rows[1]["right_integer"]:
        _fail("qIM does not fit within uIM")
    physical_terms = [
        term
        for term in operation_terms
        if term["metric_id"] == "physical-storage-v1"
    ]
    if (
        len(physical_terms) != 6
        or expected_metric["physical_projection_status"] != "planned-conditional"
        or expected_metric["physical_projection_requires_all_move_preconditions"]
        is not True
        or expected_metric["physical_file_inode_object_receipts_required"] is not True
        or expected_metric["physical_file_inode_object_receipts_attested"] is not False
        or expected_metric["actual_physical_delta_attested"] is not False
    ):
        _fail("planned physical delta receipt boundary drifted")

    expected_reservations = []
    for profile, current_upper, total_upper in (
        ("pilot", 1_020, 2_040),
        ("full", 10_200, 20_400),
    ):
        combined = current_upper + 350
        expected_reservations.append(
            {
                "checkpoint_key": "W5-pre-purge",
                "combined_current_plus_move_history_upper": combined,
                "incidental_current_upper": current_upper,
                "incidental_total_upper": total_upper,
                "move_history_upper": 350,
                "passes_total_upper": combined <= total_upper,
                "profile_key": profile,
            }
        )
    if value["incidental_capacity_reservation"] != expected_reservations:
        _fail("incidental move capacity reservation drifted")
    if any(
        row["passes_total_upper"] is not True
        or row["combined_current_plus_move_history_upper"]
        > row["incidental_total_upper"]
        for row in value["incidental_capacity_reservation"]
    ):
        _fail("incidental move capacity reservation does not fit")


def _validate_rules_and_events(value):
    expected_scopes = [
        {"different_leaf_scope_required": False, "same_persona_required": True, "same_scope_required": True, "scope_relation_rule_key": "same-bound-leaf-scope", "source_instance_matching_required": True},
        {"different_leaf_scope_required": True, "same_persona_required": True, "same_scope_required": False, "scope_relation_rule_key": "different-bound-leaf-scope-same-persona", "source_instance_matching_required": True},
        {"different_leaf_scope_required": False, "same_persona_required": True, "same_scope_required": False, "scope_relation_rule_key": "downstream-selected-valid-leaf-scope", "source_instance_matching_required": True},
        {"different_leaf_scope_required": False, "same_persona_required": True, "same_scope_required": True, "scope_relation_rule_key": "same-capacity-scope-as-replaced-cohort", "source_instance_matching_required": True},
        {"different_leaf_scope_required": False, "same_persona_required": True, "same_scope_required": False, "scope_relation_rule_key": "nonsearchable-export-staging", "source_instance_matching_required": True},
    ]
    expected_locations = [
        {"location_transition_rule_key": "preserve-relative-location", "operation_effect": "preserve"},
        {"location_transition_rule_key": "replace-basename-in-same-scope", "operation_effect": "rename"},
        {"location_transition_rule_key": "move-to-different-leaf-scope", "operation_effect": "move"},
        {"location_transition_rule_key": "create-distinct-derived-location", "operation_effect": "create"},
        {"location_transition_rule_key": "create-distinct-duplicate-location", "operation_effect": "create"},
        {"location_transition_rule_key": "remove-live-location", "operation_effect": "delete"},
        {"location_transition_rule_key": "create-distinct-capacity-replacement-location", "operation_effect": "create"},
        {"location_transition_rule_key": "move-under-existing-archive-container", "operation_effect": "archive"},
        {"location_transition_rule_key": "emit-nonsearchable-export", "operation_effect": "export"},
        {"location_transition_rule_key": "create-restored-live-location", "operation_effect": "reingest"},
        {"location_transition_rule_key": "remove-live-and-reachable-history", "operation_effect": "purge"},
    ]
    if value["scope_relation_rules"] != expected_scopes:
        _fail("scope-relation rules drifted")
    if value["location_transition_rules"] != expected_locations:
        _fail("location-transition rules drifted")
    expected_events = _expected_event_templates()
    if value["event_templates"] != expected_events:
        _fail("event template catalog or symbolic delta rule drifted")
    for row in value["event_templates"]:
        cells = row["delta_rule"]
        for dimension in ("current_transition_units", "historical_transition_units"):
            cell = cells[dimension]
            if set(cell) != {"coefficient", "direction", "symbol"}:
                _fail("symbolic delta cell shape drifted")
            if type(cell["coefficient"]) is not int or cell["coefficient"] not in {0, 1}:
                _fail("symbolic delta coefficients must be exact zero or one")
            if cell["direction"] not in {"preserve", "increase", "decrease"}:
                _fail("symbolic delta direction drifted")
            if cell["coefficient"] == 0 and (cell["direction"] != "preserve" or cell["symbol"] != "zero"):
                _fail("zero symbolic deltas must be exact structural zero")
            if cell["coefficient"] == 1 and (
                cell["direction"] == "preserve" or cell["symbol"] == "zero"
            ):
                _fail("nonzero symbolic deltas require a signed cohort symbol")


def _validate_replacements_and_disjointness(value):
    distinctness = {
        "contract_chunk_set_relation": "must-be-distinct",
        "logical_document_relation": "must-be-distinct",
        "raw_payload_relation": "must-be-distinct",
        "semantic_content_relation": "must-be-distinct",
        "typed_fact_membership_relation": "must-be-distinct",
    }
    expected = [
        {
            "allowed_relation_keys": ["capacity-replaces"],
            "copying_replaced_content_satisfies": False,
            "distinctness_contract": dict(distinctness),
            "origin_profile_relation": "must-match-replaced-source",
            "replaced_cohort_key": cohort,
            "replacement_pairing_rule": "one-distinct-replacement-per-matched-logical-document",
            "replacement_contract_key": key,
            "source_instance_pairing_status": "unbound",
            "transition_unit_relation": "must-equal-replaced-selection",
            "variant_relation": "must-match-replaced-source",
        }
        for cohort, key in (("P", "P-prime"), ("X", "X-prime"))
    ]
    if value["replacement_contracts"] != expected:
        _fail("P-prime/X-prime distinctness or capacity-only relation drifted")
    expected_disjoint = {
        "anonymous_capability_may_satisfy_multiple_states": False,
        "pairwise_disjoint_required": True,
        "state_classes": [
            {"capability_class_key": "final-deleted", "required_count_per_persona": 10, "state": "final-deleted", "transition_unit_symbol": "qXD"},
            {"capability_class_key": "current-restored", "required_count_per_persona": 10, "state": "current-restored", "transition_unit_symbol": "qXR"},
            {"capability_class_key": "purged-negative", "required_count_per_persona": 15, "state": "purged", "transition_unit_symbol": "qP"},
        ],
    }
    if value["lifecycle_disjointness_contract"] != expected_disjoint:
        _fail("deleted/restored/purged disjointness drifted")


def _validate_dependency_groups(value):
    groups = value["dependency_groups"]
    _require_exact_list(groups, label="dependency groups")
    keys = [row.get("dependency_group_key") for row in groups if type(row) is dict]
    expected_keys = [
        "w4-x-capacity-balance",
        "w5-restore-x-net-zero",
        "w5-p-capacity-and-purge",
        "w5-final-checkpoint-closure",
        "derive-emphasis-witness",
        "duplicate-emphasis-witness",
    ]
    if keys != expected_keys:
        _fail("dependency group order or cardinality drifted")
    by_key = {row["dependency_group_key"]: row for row in groups}
    restore = by_key["w5-restore-x-net-zero"]
    if restore != {
        "dependency_group_key": "w5-restore-x-net-zero",
        "empty_selection_satisfies": False,
        "exported_payload_relation": "byte-identical-to-matched-deleted-x",
        "member_event_template_keys": [_EVENT["w5-export-x"], _EVENT["w5-reingest-x"], _EVENT["w5-delete-x-prime"]],
        "member_selection_relation": "exact-same-matched-restored-subset",
        "ordered_dependencies": [
            [_EVENT["w5-export-x"], _EVENT["w5-reingest-x"]],
            [_EVENT["w5-reingest-x"], _EVENT["w5-delete-x-prime"]],
        ],
        "paired_replacement_selection_rule": "delete-corresponding-x-prime-one-to-one",
        "paired_x_prime_delete_required": True,
        "reingested_payload_relation": "byte-identical-to-exported-payload",
        "shared_selection_symbol": "qXR",
        "source_instance_matching_status": "unbound",
        "symbolic_net_delta": {
            "current_transition_units": _delta_cell("preserve", 0, "zero"),
            "historical_transition_units": _delta_cell("preserve", 0, "zero"),
        },
    }:
        _fail("restore must remain export, reingest, paired X-prime delete with net zero")
    w4 = by_key["w4-x-capacity-balance"]
    if w4["member_event_template_keys"] != [_EVENT["w4-delete-x"], _EVENT["w4-x-prime"]] or w4["symbolic_net_delta"] != {
        "current_transition_units": _delta_cell("preserve", 0, "zero"),
        "historical_transition_units": _delta_cell("increase", 1, "qX"),
    }:
        _fail("W4 X capacity balance drifted")
    p_group = by_key["w5-p-capacity-and-purge"]
    if p_group["member_event_template_keys"] != [_EVENT["w5-p-prime"], _EVENT["w5-purge-p"]] or p_group["symbolic_net_delta"] != {
        "current_transition_units": _delta_cell("preserve", 0, "zero"),
        "historical_transition_units": _delta_cell("decrease", 1, "qP"),
    }:
        _fail("W5 P capacity/purge balance drifted")
    closure = by_key["w5-final-checkpoint-closure"]
    if closure.get("required_symbolic_equalities") != [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}] or closure.get("symbolic_net_delta_after_required_equalities") != {
        "current_transition_units": _delta_cell("preserve", 0, "zero"),
        "historical_transition_units": _delta_cell("preserve", 0, "zero"),
    }:
        _fail("W5 symbolic checkpoint closure drifted")
    for key, template in (("derive-emphasis-witness", _EVENT["w3-derive"]), ("duplicate-emphasis-witness", _EVENT["w3-duplicate"])):
        row = by_key[key]
        if row.get("member_event_template_keys") != [template] or row.get("structural_transition_units") != 0 or row.get("symbolic_net_delta") != {
            "current_transition_units": _delta_cell("preserve", 0, "zero"),
            "historical_transition_units": _delta_cell("preserve", 0, "zero"),
        }:
            _fail("emphasis witness must remain q=0 structural demand")


def _validate_wave_algebra(value):
    def terms(items):
        return [
            {"coefficient": coefficient, "direction": direction, "symbol": symbol}
            for direction, coefficient, symbol in items
        ]

    expected = [
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": terms((("increase", 1, "qP"), ("increase", 1, "qX"), ("increase", 1, "qY"))), "wave": "W1"},
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": [], "wave": "W2"},
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": terms((("increase", 1, "qX"), ("increase", 1, "qY"), ("increase", 1, "qN"))), "wave": "W3"},
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": terms((("increase", 1, "qX"),)), "wave": "W4"},
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": [], "required_symbolic_equalities": [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}], "wave": "W5"},
    ]
    if value["wave_delta_rules"] != expected:
        _fail("W1-W5 exact symbolic wave algebra drifted")
    expected_model = {
        "all_event_metric_specific_delta_rules_present": False,
        "contract_checkpoint_ledger_id": "search-semantic-endpoint-v1",
        "contract_checkpoint_participation": "contract",
        "downstream_metric_candidates": [
            "search-semantic-endpoint-v1",
            "persona-global-chunk-hash-v1",
            "history-path-binding-v1",
            "physical-storage-v1",
        ],
        "cross_scope_move_metric_delta_rules_present": True,
        "metric_identity_binding_status": "ledger-identities-and-move-deltas-bound-to-authenticated-accounting-sidecar",
        "symbolic_transition_units": ["qP", "qX", "qY", "qN", "qU", "qXD", "qXR", "qIM", "uIM", "nIM"],
        "symbolic_equalities_required_after_solve": [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}],
        "symbolic_partition_rules": [
            {
                "part_symbols": ["qXD", "qXR"],
                "relation": "exact-sum",
                "whole_symbol": "qX",
            }
        ],
        "transition_unit_semantics": "contributor-events-use-abstract-units-cross-scope-move-uses-explicit-ledger-projections",
    }
    if value["transition_algebra_model"] != expected_model:
        _fail("accounting-bound transition algebra model drifted")


_DELTA_DIMENSIONS = (
    "current_transition_units",
    "historical_transition_units",
)


def _empty_polynomial():
    return {dimension: {} for dimension in _DELTA_DIMENSIONS}


def _add_cell_to_polynomial(polynomial, dimension, cell):
    coefficient = cell["coefficient"]
    if coefficient == 0:
        return
    sign = 1 if cell["direction"] == "increase" else -1
    symbol = cell["symbol"]
    polynomial[dimension][symbol] = (
        polynomial[dimension].get(symbol, 0) + sign * coefficient
    )
    if polynomial[dimension][symbol] == 0:
        del polynomial[dimension][symbol]


def _event_polynomial(event_rows):
    polynomial = _empty_polynomial()
    for row in event_rows:
        for dimension in _DELTA_DIMENSIONS:
            _add_cell_to_polynomial(polynomial, dimension, row["delta_rule"][dimension])
    return polynomial


def _declared_delta_polynomial(delta):
    polynomial = _empty_polynomial()
    for dimension in _DELTA_DIMENSIONS:
        _add_cell_to_polynomial(polynomial, dimension, delta[dimension])
    return polynomial


def _term_polynomial(row):
    polynomial = _empty_polynomial()
    for dimension, field in (
        ("current_transition_units", "current_transition_unit_terms"),
        ("historical_transition_units", "historical_transition_unit_terms"),
    ):
        for term in row[field]:
            _add_cell_to_polynomial(polynomial, dimension, term)
    return polynomial


def _apply_symbolic_equalities(polynomial, equalities):
    normalized = {
        dimension: dict(terms) for dimension, terms in polynomial.items()
    }
    for equality in equalities:
        left = equality["left_symbol"]
        right = equality["right_symbol"]
        for dimension in _DELTA_DIMENSIONS:
            coefficient = normalized[dimension].pop(left, 0)
            if coefficient:
                normalized[dimension][right] = (
                    normalized[dimension].get(right, 0) + coefficient
                )
                if normalized[dimension][right] == 0:
                    del normalized[dimension][right]
    return normalized


def _assert_symbolic_algebra_recomputes(value):
    """Recompute group/wave polynomials from the supplied event rows."""

    events = {
        row["event_template_key"]: row for row in value["event_templates"]
    }
    groups = {
        row["dependency_group_key"]: row for row in value["dependency_groups"]
    }
    for group_key in (
        "w4-x-capacity-balance",
        "w5-restore-x-net-zero",
        "w5-p-capacity-and-purge",
        "derive-emphasis-witness",
        "duplicate-emphasis-witness",
    ):
        group = groups[group_key]
        calculated = _event_polynomial(
            [events[key] for key in group["member_event_template_keys"]]
        )
        declared = _declared_delta_polynomial(group["symbolic_net_delta"])
        if calculated != declared:
            _fail("dependency-group symbolic delta does not recompute from members")

    closure = groups["w5-final-checkpoint-closure"]
    calculated = _event_polynomial(
        [events[key] for key in closure["member_event_template_keys"]]
    )
    calculated = _apply_symbolic_equalities(
        calculated, closure["required_symbolic_equalities"]
    )
    declared = _declared_delta_polynomial(
        closure["symbolic_net_delta_after_required_equalities"]
    )
    if calculated != declared:
        _fail("W5 closure does not recompute after its required equality")

    by_wave = {wave: [] for wave in WAVE_ORDER}
    for event in value["event_templates"]:
        by_wave[event["wave"]].append(event)
    wave_rows = {row["wave"]: row for row in value["wave_delta_rules"]}
    for wave in WAVE_ORDER:
        calculated = _event_polynomial(by_wave[wave])
        if wave == "W5":
            calculated = _apply_symbolic_equalities(
                calculated, wave_rows[wave]["required_symbolic_equalities"]
            )
        declared = _term_polynomial(wave_rows[wave])
        if calculated != declared:
            _fail("wave symbolic delta does not recompute from event templates")


def _validate_persona_payloads(value):
    demands = value["persona_demands"]
    _require_exact_list(demands, label="persona demands")
    if len(demands) != 20:
        _fail("lifecycle demand must contain exactly twenty personas")
    expected_capabilities = _expected_capabilities()
    for expected_persona, row in zip(PERSONA_IDS, demands):
        _require_exact_dict(row, {"origin_payload", "profile_reuse_bindings"}, label="persona demand")
        payload = row["origin_payload"]
        _require_exact_dict(payload, {"anonymous_capabilities", "origin_key", "persona_id"}, label="pilot origin payload")
        if payload["persona_id"] != expected_persona or payload["origin_key"] != "pilot":
            _fail("persona pilot origin identity/order drifted")
        if payload["anonymous_capabilities"] != expected_capabilities:
            _fail("persona anonymous capability partition drifted")
        raw = _canonical(payload, label="persona lifecycle pilot origin payload", max_bytes=MAX_ORIGIN_PAYLOAD_BYTES)
        digest = hashlib.sha256(raw).hexdigest()
        expected_bindings = [
            {
                "origin_payload_canonical_bytes": len(raw),
                "origin_payload_sha256": digest,
                "profile_key": profile,
                "reuse_mode": "direct-byte-identical-origin-payload",
            }
            for profile in PROFILE_ORDER
        ]
        if row["profile_reuse_bindings"] != expected_bindings:
            _fail("pilot/full bindings must reuse one byte-identical origin payload")


def _validate_emphasis_and_summary(value):
    expected_witnesses = []
    for witness_kind, personas, template_key in (
        ("derive", ("p01", "p04", "p06", "p09"), _EVENT["w3-derive"]),
        ("exact-duplicate", ("p04", "p05", "p08", "p10", "p14", "p19"), _EVENT["w3-duplicate"]),
    ):
        for persona in personas:
            expected_witnesses.append(
                {
                    "event_template_key": template_key,
                    "persona_id": persona,
                    "required_witness_count": 5,
                    "source_instance_matching_status": "unbound",
                    "structural_transition_units": 0,
                    "witness_kind": witness_kind,
                }
            )
    if value["emphasis_witness_demands"] != expected_witnesses:
        _fail("persona emphasis witness demand drifted")
    class_counts = {
        class_key: count * 20
        for class_key, _, _, _, count, _, _ in _CAPABILITY_CLASSES
    }
    allocation_counts = {
        allocation_class: 0 for allocation_class in ALLOCATION_CLASS_ORDER
    }
    for _, allocation_class, _, _, count, _, _ in _CAPABILITY_CLASSES:
        allocation_counts[allocation_class] += count * 20
    expected_summary = {
        "allocation_class_capability_counts": allocation_counts,
        "anonymous_capability_count": 2_100,
        "anonymous_capability_count_per_persona": 105,
        "capability_class_counts": class_counts,
        "contract_contributor_capability_count": 2_000,
        "derive_emphasis_witness_count": 20,
        "exact_duplicate_emphasis_witness_count": 30,
        "incidental_searchable_capability_count": 100,
        "lifecycle_anchor_counts": {"current-restored": 200, "final-deleted": 200, "purged": 300},
        "persona_count": 20,
        "profile_binding_count": 40,
    }
    if value["suite_summary"] != expected_summary:
        _fail("lifecycle suite summary drifted")
    if value["remaining_blockers"] != [
        "source-instance-matching-unbound",
        "joint-cardinality-solve-not-executed",
        "cross-scope-move-w0-observation-not-attested",
        "compiled-history-plan-not-available",
        "concrete-location-transition-not-compiled",
        "history-executor-and-actual-receipts-not-available",
        "evaluation-target-resolution-remains-separate",
        "formal-g0-capacity-and-closure-gates-not-satisfied",
    ]:
        _fail("lifecycle remaining-blocker boundary drifted")


def _validate_accounting_dependency(
    value,
    chunk_accounting_value,
    envelope_value,
    overlay_contract_value,
):
    try:
        chunk_accounting_validator.validate_chunk_accounting_contract(
            chunk_accounting_value,
            envelope_value=envelope_value,
            overlay_contract_value=overlay_contract_value,
        )
    except chunk_accounting_validator.PersonaV2ChunkAccountingValidationError as error:
        _fail(str(error))
    for dependency_value, label in (
        (chunk_accounting_value, "persona-v2-chunk-accounting"),
        (envelope_value, "persona-v2-envelope"),
        (overlay_contract_value, "persona-v2-overlay-contract"),
    ):
        _require_negative_authority(dependency_value, label=label)

    expected_binding = _expected_accounting_binding(chunk_accounting_value)
    if value["input_binding_order"] != ["persona-v2-chunk-accounting"]:
        _fail("lifecycle accounting input binding order drifted")
    if value["input_bindings"] != [expected_binding]:
        _fail("lifecycle accounting input binding drifted")

    move_rows = [
        row
        for row in chunk_accounting_value["operation_delta_contracts"]
        if row.get("operation_id") == "cross-scope-move-incidental"
    ]
    expected_move = _expected_accounting_cross_scope_move_operation()
    if move_rows != [expected_move]:
        _fail("bound accounting cross-scope move operation drifted")
    if value["cross_scope_move_metric_contract"]["accounting_operation_contract"] != expected_move:
        _fail("lifecycle and bound accounting move operations differ")
    if (
        chunk_accounting_value["completion_claims"]["actual_accounting_attested"]
        is not False
        or chunk_accounting_value["completion_claims"][
            "source_instance_assignment_present"
        ]
        is not False
        or "W0-observed-incidental-move-chunk-counts-not-attested"
        not in chunk_accounting_value["remaining_blockers"]
        or "filesystem-cas-and-inode-receipts-not-present"
        not in chunk_accounting_value["remaining_blockers"]
    ):
        _fail("bound accounting observation and receipt boundary drifted")

    move_anchor = chunk_accounting_value["move_anchor_contract"]
    capacity = value["anchor_capacity_contract"]
    metric = value["cross_scope_move_metric_contract"]
    if (
        move_anchor["anonymous_capability_reclassification"]
        != {"I": 5, "N": 0, "P": 15, "U": 35, "X": 20, "Y": 30}
        or move_anchor["capability_count_per_persona"]
        != capacity["available_contributor_capacity_per_persona"]
        or move_anchor["contributor_semantic_anchor_capacity_reserved"]
        != capacity["available_contributor_capacity_per_persona"]
        or move_anchor["contributor_semantic_anchor_capacity_consumed"]
        != capacity["contributor_capabilities_requiring_capacity_per_persona"]
        or move_anchor["contributor_semantic_anchor_capacity_unused"]
        != capacity["unused_contributor_capacity_per_persona"]
        or move_anchor["incidental_move_anchor_count"]
        != metric["matched_move_source_count_exact"]
        or move_anchor["per_source_actual_chunk_inclusive_minimum"]
        != metric["per_anchor_observed_lower"]
        or move_anchor["per_source_actual_chunk_inclusive_maximum"]
        != metric["per_anchor_observed_upper"]
        or move_anchor["qIM_inclusive_minimum"] != metric["observed_symbol_lower"]
        or move_anchor["qIM_inclusive_maximum"] != metric["observed_symbol_upper"]
    ):
        _fail("lifecycle move anchors differ from bound accounting anchors")

    accounting_caps = {
        row["profile"]: row
        for row in chunk_accounting_value["incidental_move_cap_proof"]
    }
    for lifecycle_row in value["incidental_capacity_reservation"]:
        accounting_row = accounting_caps.get(lifecycle_row["profile_key"])
        if accounting_row is None or (
            lifecycle_row["checkpoint_key"] != accounting_row["proof_checkpoint"]
            or lifecycle_row["incidental_current_upper"]
            != accounting_row["incidental_current_upper_bound"]
            or lifecycle_row["incidental_total_upper"]
            != accounting_row["incidental_total_upper_bound"]
            or lifecycle_row["move_history_upper"]
            != accounting_row["move_history_upper_bound"]
            or lifecycle_row["combined_current_plus_move_history_upper"]
            != accounting_row["worst_case_current_plus_move_history"]
            or lifecycle_row["passes_total_upper"]
            is not accounting_row["worst_case_satisfies_total_cap"]
        ):
            _fail("lifecycle move cap proof differs from bound accounting proof")


def _validate_lifecycle_demand_snapshot(
    value,
    chunk_accounting_value,
    envelope_value,
    overlay_contract_value,
):
    """Validate a detached canonical snapshot; exposed for TOCTOU tests."""

    _assert_forbidden_later_layer_fields_absent(value)
    _assert_exact_scalar_types(value)
    _validate_identity_and_authority(value)
    _validate_boundaries(value)
    _validate_accounting_dependency(
        value,
        chunk_accounting_value,
        envelope_value,
        overlay_contract_value,
    )
    _validate_capability_contracts(value)
    _validate_cross_scope_move_accounting_boundary(value)
    _validate_rules_and_events(value)
    _validate_replacements_and_disjointness(value)
    _validate_dependency_groups(value)
    _validate_wave_algebra(value)
    _assert_symbolic_algebra_recomputes(value)
    _validate_persona_payloads(value)
    _validate_emphasis_and_summary(value)
    return True


def validate_lifecycle_demand(
    value,
    *,
    chunk_accounting_value,
    envelope_value,
    overlay_contract_value,
):
    """Validate pinned lifecycle and accounting snapshots independently."""

    value_snapshot, value_raw = _snapshot(
        value,
        label="persona v2 lifecycle demand",
        max_bytes=MAX_LIFECYCLE_DEMAND_BYTES,
    )
    accounting_snapshot, accounting_raw = _snapshot(
        chunk_accounting_value,
        label="persona v2 chunk accounting input",
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
        opening_pin = (len(value_raw), hashlib.sha256(value_raw).hexdigest())
        if opening_pin != (
            EXPECTED_LIFECYCLE_DEMAND_CANONICAL_BYTES,
            EXPECTED_LIFECYCLE_DEMAND_SHA256,
        ):
            _fail("lifecycle demand differs from its installed canonical body pin")
        return _validate_lifecycle_demand_snapshot(
            value_snapshot,
            accounting_snapshot,
            envelope_snapshot,
            overlay_snapshot,
        )
    finally:
        _reauth(
            value,
            value_raw,
            label="lifecycle demand",
            max_bytes=MAX_LIFECYCLE_DEMAND_BYTES,
        )
        _reauth(
            chunk_accounting_value,
            accounting_raw,
            label="chunk accounting input",
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
