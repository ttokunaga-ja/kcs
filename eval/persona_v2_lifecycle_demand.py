"""Pre-solve lifecycle demand for the twenty persona-PC v2 roots.

The artifact owns anonymous lifecycle capabilities and symbolic event demand.
It is deliberately upstream of source-instance matching, the joint cardinality
solve, concrete locations, compiled history events, filesystem mutation, and
evaluation-target resolution.  A persona's capability payload is emitted once
with origin ``pilot``; both the pilot and full profiles bind the exact same
canonical payload bytes.

Negative deltas are represented by an exact non-negative coefficient plus a
``decrease`` direction.  Consequently the canonical body contains no null,
float, negative integer, or magic unresolved numeric value.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_chunk_accounting as chunk_accounting
    from . import persona_v2_lifecycle_demand_validator as independent
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_chunk_accounting as chunk_accounting
    import persona_v2_lifecycle_demand_validator as independent
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay


ARTIFACT_SCHEMA = "kcs.persona.pc-lifecycle-demand/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-lifecycle-demand"
FIXTURE_ID = "kcs-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_LIFECYCLE_DEMAND_BYTES = 2 * 1024 * 1024

EXPECTED_CHUNK_ACCOUNTING_CANONICAL_BYTES = 19_801
EXPECTED_CHUNK_ACCOUNTING_SHA256 = (
    "d9c59e922a2619b1748194241ffdf47ace3eb034f136b0d04154163bda3ccea2"
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
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_source_instance_matching",
        "authorizes_solver_execution",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kcs_execution_available",
        "source_instance_matching_available",
    }
)


class PersonaV2LifecycleDemandError(ValueError):
    """Raised when the pre-solve lifecycle demand drifts or gains authority."""


def _fail(message):
    raise PersonaV2LifecycleDemandError(message)


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(key) is not str or type(flag) is not bool or flag is not False
        for key, flag in authority.items()
    ):
        _fail(f"{label} authority must be non-empty and all false")


def _chunk_accounting_binding(value):
    chunk_accounting.validate_chunk_accounting_contract(value)
    _require_negative_authority(value, label="persona-v2-chunk-accounting")
    raw = chunk_accounting.canonical_json_bytes(value)
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


def _accounting_cross_scope_move_operation():
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
            "source-delete-plus-destination-ingest-across-independent-kcs-"
            "stores-not-product-cross-scope-lineage-inference"
        ),
        "source_participation": "incidental_searchable",
    }


def _ledger_dimension_schema_crosswalk():
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


# class key, allocation class, gate role, history cohorts, count/persona,
# evidence state, required templates
_CAPABILITY_CLASSES = (
    ("m3-1-current", "U", "contract_contributor", ("U",), 30, "current", ()),
    ("same-scope-rename", "U", "contract_contributor", ("U",), 5, "current-after-rename", (_EVENT["w2-rename-u"],)),
    ("cross-scope-move", "I", "incidental_searchable", (), 5, "current-after-move", (_EVENT["w2-move-i"],)),
    ("old-wording-history", "Y", "contract_contributor", ("Y",), 10, "old-wording-history", (_EVENT["w1-y"],)),
    ("locale-history", "Y", "contract_contributor", ("Y",), 10, "locale-history", (_EVENT["w3-y"],)),
    ("archive-history", "Y", "contract_contributor", ("Y",), 10, "archive-history", (_EVENT["w4-archive-y"],)),
    (
        "final-deleted",
        "X",
        "contract_contributor",
        ("X",),
        10,
        "final-deleted",
        (_EVENT["w1-x"], _EVENT["w3-x"], _EVENT["w4-delete-x"], _EVENT["w4-x-prime"]),
    ),
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
    (
        "purged-negative",
        "P",
        "contract_contributor",
        ("P",),
        15,
        "purged",
        (_EVENT["w1-p"], _EVENT["w5-p-prime"], _EVENT["w5-purge-p"]),
    ),
)


def _capability_class_contracts():
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


def _scope_relation_rules():
    return [
        {
            "different_leaf_scope_required": False,
            "same_persona_required": True,
            "same_scope_required": True,
            "scope_relation_rule_key": "same-bound-leaf-scope",
            "source_instance_matching_required": True,
        },
        {
            "different_leaf_scope_required": True,
            "same_persona_required": True,
            "same_scope_required": False,
            "scope_relation_rule_key": "different-bound-leaf-scope-same-persona",
            "source_instance_matching_required": True,
        },
        {
            "different_leaf_scope_required": False,
            "same_persona_required": True,
            "same_scope_required": False,
            "scope_relation_rule_key": "downstream-selected-valid-leaf-scope",
            "source_instance_matching_required": True,
        },
        {
            "different_leaf_scope_required": False,
            "same_persona_required": True,
            "same_scope_required": True,
            "scope_relation_rule_key": "same-capacity-scope-as-replaced-cohort",
            "source_instance_matching_required": True,
        },
        {
            "different_leaf_scope_required": False,
            "same_persona_required": True,
            "same_scope_required": False,
            "scope_relation_rule_key": "nonsearchable-export-staging",
            "source_instance_matching_required": True,
        },
    ]


def _location_transition_rules():
    return [
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


def _delta_cell(direction, coefficient, symbol):
    return {
        "coefficient": coefficient,
        "direction": direction,
        "symbol": symbol,
    }


# key, wave, operation, cohort, symbol, C direction, H direction,
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


def _event_templates():
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


def _replacement_contracts():
    distinctness = {
        "contract_chunk_set_relation": "must-be-distinct",
        "logical_document_relation": "must-be-distinct",
        "raw_payload_relation": "must-be-distinct",
        "semantic_content_relation": "must-be-distinct",
        "typed_fact_membership_relation": "must-be-distinct",
    }
    return [
        {
            "allowed_relation_keys": ["capacity-replaces"],
            "copying_replaced_content_satisfies": False,
            "distinctness_contract": copy.deepcopy(distinctness),
            "origin_profile_relation": "must-match-replaced-source",
            "replaced_cohort_key": "P",
            "replacement_pairing_rule": "one-distinct-replacement-per-matched-logical-document",
            "replacement_contract_key": "P-prime",
            "source_instance_pairing_status": "unbound",
            "transition_unit_relation": "must-equal-replaced-selection",
            "variant_relation": "must-match-replaced-source",
        },
        {
            "allowed_relation_keys": ["capacity-replaces"],
            "copying_replaced_content_satisfies": False,
            "distinctness_contract": copy.deepcopy(distinctness),
            "origin_profile_relation": "must-match-replaced-source",
            "replaced_cohort_key": "X",
            "replacement_pairing_rule": "one-distinct-replacement-per-matched-logical-document",
            "replacement_contract_key": "X-prime",
            "source_instance_pairing_status": "unbound",
            "transition_unit_relation": "must-equal-replaced-selection",
            "variant_relation": "must-match-replaced-source",
        },
    ]


def _dependency_groups():
    return [
        {
            "dependency_group_key": "w4-x-capacity-balance",
            "member_event_template_keys": [_EVENT["w4-delete-x"], _EVENT["w4-x-prime"]],
            "ordered_dependencies": [[_EVENT["w4-delete-x"], _EVENT["w4-x-prime"]]],
            "symbolic_net_delta": {
                "current_transition_units": _delta_cell("preserve", 0, "zero"),
                "historical_transition_units": _delta_cell("increase", 1, "qX"),
            },
        },
        {
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
        },
        {
            "dependency_group_key": "w5-p-capacity-and-purge",
            "member_event_template_keys": [_EVENT["w5-p-prime"], _EVENT["w5-purge-p"]],
            "ordered_dependencies": [[_EVENT["w5-p-prime"], _EVENT["w5-purge-p"]]],
            "symbolic_net_delta": {
                "current_transition_units": _delta_cell("preserve", 0, "zero"),
                "historical_transition_units": _delta_cell("decrease", 1, "qP"),
            },
        },
        {
            "dependency_group_key": "w5-final-checkpoint-closure",
            "member_event_template_keys": [_EVENT["w5-n"], _EVENT["w5-p-prime"], _EVENT["w5-purge-p"]],
            "ordered_dependencies": [[_EVENT["w5-p-prime"], _EVENT["w5-purge-p"]]],
            "required_symbolic_equalities": [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}],
            "symbolic_net_delta_after_required_equalities": {
                "current_transition_units": _delta_cell("preserve", 0, "zero"),
                "historical_transition_units": _delta_cell("preserve", 0, "zero"),
            },
        },
        {
            "dependency_group_key": "derive-emphasis-witness",
            "member_event_template_keys": [_EVENT["w3-derive"]],
            "ordered_dependencies": [],
            "structural_transition_units": 0,
            "symbolic_net_delta": {
                "current_transition_units": _delta_cell("preserve", 0, "zero"),
                "historical_transition_units": _delta_cell("preserve", 0, "zero"),
            },
        },
        {
            "dependency_group_key": "duplicate-emphasis-witness",
            "member_event_template_keys": [_EVENT["w3-duplicate"]],
            "ordered_dependencies": [],
            "structural_transition_units": 0,
            "symbolic_net_delta": {
                "current_transition_units": _delta_cell("preserve", 0, "zero"),
                "historical_transition_units": _delta_cell("preserve", 0, "zero"),
            },
        },
    ]


def _linear_delta(terms):
    return [
        {"coefficient": coefficient, "direction": direction, "symbol": symbol}
        for direction, coefficient, symbol in terms
    ]


def _wave_delta_rules():
    return [
        {
            "current_transition_unit_terms": [],
            "historical_transition_unit_terms": _linear_delta((("increase", 1, "qP"), ("increase", 1, "qX"), ("increase", 1, "qY"))),
            "wave": "W1",
        },
        {"current_transition_unit_terms": [], "historical_transition_unit_terms": [], "wave": "W2"},
        {
            "current_transition_unit_terms": [],
            "historical_transition_unit_terms": _linear_delta((("increase", 1, "qX"), ("increase", 1, "qY"), ("increase", 1, "qN"))),
            "wave": "W3",
        },
        {
            "current_transition_unit_terms": [],
            "historical_transition_unit_terms": _linear_delta((("increase", 1, "qX"),)),
            "wave": "W4",
        },
        {
            "current_transition_unit_terms": [],
            "historical_transition_unit_terms": [],
            "required_symbolic_equalities": [{"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}],
            "wave": "W5",
        },
    ]


def _allocation_class_contracts(event_templates):
    by_class = {allocation_class: [] for allocation_class in ALLOCATION_CLASS_ORDER}
    for row in event_templates:
        by_class[row["allocation_class"]].append(row["event_template_key"])
    counts = {allocation_class: 0 for allocation_class in ALLOCATION_CLASS_ORDER}
    for _, allocation_class, _, _, count, _, _ in _CAPABILITY_CLASSES:
        counts[allocation_class] += count
    return [
        {
            "allocation_class": allocation_class,
            "anonymous_capability_count_per_persona": counts[allocation_class],
            "eligible_event_template_keys": by_class[allocation_class],
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


def _anonymous_capabilities():
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
    if ordinal != 106:
        _fail("anonymous capability cardinality drifted")
    return rows


def _origin_payload(persona_id):
    return {
        "anonymous_capabilities": _anonymous_capabilities(),
        "origin_key": "pilot",
        "persona_id": persona_id,
    }


def _canonical_fragment(value, *, label):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=256 * 1024,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _persona_demands():
    rows = []
    for persona_id in PERSONA_IDS:
        payload = _origin_payload(persona_id)
        raw = _canonical_fragment(payload, label="persona lifecycle pilot origin payload")
        digest = hashlib.sha256(raw).hexdigest()
        rows.append(
            {
                "origin_payload": payload,
                "profile_reuse_bindings": [
                    {
                        "origin_payload_canonical_bytes": len(raw),
                        "origin_payload_sha256": digest,
                        "profile_key": profile,
                        "reuse_mode": "direct-byte-identical-origin-payload",
                    }
                    for profile in PROFILE_ORDER
                ],
            }
        )
    return rows


def _emphasis_witness_demands():
    rows = []
    for witness_kind, personas, template_key in (
        ("derive", ("p01", "p04", "p06", "p09"), _EVENT["w3-derive"]),
        ("exact-duplicate", ("p04", "p05", "p08", "p10", "p14", "p19"), _EVENT["w3-duplicate"]),
    ):
        for persona_id in personas:
            rows.append(
                {
                    "event_template_key": template_key,
                    "persona_id": persona_id,
                    "required_witness_count": 5,
                    "source_instance_matching_status": "unbound",
                    "structural_transition_units": 0,
                    "witness_kind": witness_kind,
                }
            )
    return rows


def _suite_summary():
    class_counts = {
        class_key: count * len(PERSONA_IDS)
        for class_key, _, _, _, count, _, _ in _CAPABILITY_CLASSES
    }
    allocation_counts = {
        allocation_class: 0 for allocation_class in ALLOCATION_CLASS_ORDER
    }
    for _, allocation_class, _, _, count, _, _ in _CAPABILITY_CLASSES:
        allocation_counts[allocation_class] += count * len(PERSONA_IDS)
    return {
        "allocation_class_capability_counts": allocation_counts,
        "anonymous_capability_count": 2_100,
        "anonymous_capability_count_per_persona": 105,
        "capability_class_counts": class_counts,
        "contract_contributor_capability_count": 2_000,
        "derive_emphasis_witness_count": 20,
        "exact_duplicate_emphasis_witness_count": 30,
        "incidental_searchable_capability_count": 100,
        "lifecycle_anchor_counts": {
            "current-restored": 200,
            "final-deleted": 200,
            "purged": 300,
        },
        "persona_count": 20,
        "profile_binding_count": 40,
    }


def _cross_scope_move_metric_contract():
    return {
        "accounting_operation_contract": _accounting_cross_scope_move_operation(),
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
        "ledger_dimension_schema_crosswalk": _ledger_dimension_schema_crosswalk(),
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


def _incidental_capacity_reservation():
    rows = []
    for profile, current_upper, total_upper in (
        ("pilot", 1_020, 2_040),
        ("full", 10_200, 20_400),
    ):
        combined = current_upper + 350
        rows.append(
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
    return rows


def _anchor_capacity_contract():
    return {
        "available_contributor_capacity_per_persona": 105,
        "contributor_capabilities_requiring_capacity_per_persona": 100,
        "evaluation_ordinal_inference_allowed": False,
        "incidental_move_capabilities_unreserved_per_persona": 5,
        "mapping_status": "unbound",
        "unused_contributor_capacity_per_persona": 5,
        "unused_contributor_capacity_status": "reserved-unused",
    }


def _canonical_lifecycle_demand():
    accounting_value = chunk_accounting.build_chunk_accounting_contract()
    accounting_binding = _chunk_accounting_binding(accounting_value)
    matching_operations = [
        row
        for row in accounting_value["operation_delta_contracts"]
        if row.get("operation_id") == "cross-scope-move-incidental"
    ]
    if matching_operations != [_accounting_cross_scope_move_operation()]:
        _fail("bound chunk accounting move operation differs from lifecycle demand")
    events = _event_templates()
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "anchor_capacity_contract": _anchor_capacity_contract(),
        "boundary_assertions": {
            "accounting_sidecar_bound": True,
            "metric_specific_cardinalities_present": False,
            "compiled_event_instances_present": False,
            "concrete_locations_present": False,
            "evaluation_target_mapping_present": False,
            "execution_identifiers_present": False,
            "source_instance_matching_complete": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_LIFECYCLE_DEMAND_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "capability_class_contracts": _capability_class_contracts(),
        "allocation_class_contracts": _allocation_class_contracts(events),
        "compiled_history_plan": False,
        "completion_claims": {
            "anonymous_capability_demand_complete": True,
            "chunk_accounting_contract_bound": True,
            "event_template_symbolic_delta_complete": True,
            "lifecycle_disjointness_complete": True,
            "pilot_origin_full_byte_reuse_proved": True,
            "source_instance_matching_complete": False,
            "symbolic_demand_compiled_to_events": False,
            "metric_specific_current_history_delta_complete": False,
            "cross_scope_move_metric_projection_complete": True,
        },
        "completion_scope": "pre-solve-anonymous-lifecycle-demand-and-symbolic-event-templates-only",
        "cross_scope_move_metric_contract": _cross_scope_move_metric_contract(),
        "dependency_groups": _dependency_groups(),
        "emphasis_witness_demands": _emphasis_witness_demands(),
        "event_templates": events,
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [accounting_binding["name"]],
        "input_bindings": [accounting_binding],
        "lifecycle_disjointness_contract": {
            "anonymous_capability_may_satisfy_multiple_states": False,
            "pairwise_disjoint_required": True,
            "state_classes": [
                {"capability_class_key": "final-deleted", "required_count_per_persona": 10, "state": "final-deleted", "transition_unit_symbol": "qXD"},
                {"capability_class_key": "current-restored", "required_count_per_persona": 10, "state": "current-restored", "transition_unit_symbol": "qXR"},
                {"capability_class_key": "purged-negative", "required_count_per_persona": 15, "state": "purged", "transition_unit_symbol": "qP"},
            ],
        },
        "location_transition_rules": _location_transition_rules(),
        "incidental_capacity_reservation": _incidental_capacity_reservation(),
        "orders": {
            "allocation_class_order": list(ALLOCATION_CLASS_ORDER),
            "history_cohort_order": list(HISTORY_COHORT_ORDER),
            "persona_order": list(PERSONA_IDS),
            "profile_order": list(PROFILE_ORDER),
            "wave_order": list(WAVE_ORDER),
        },
        "origin_policy": {
            "full_profile_must_reuse_pilot_origin_payload_bytes": True,
            "origin_key": "pilot",
            "profile_specific_capability_regeneration_allowed": False,
        },
        "persona_demands": _persona_demands(),
        "remaining_blockers": [
            "source-instance-matching-unbound",
            "joint-cardinality-solve-not-executed",
            "cross-scope-move-w0-observation-not-attested",
            "compiled-history-plan-not-available",
            "concrete-location-transition-not-compiled",
            "history-executor-and-actual-receipts-not-available",
            "evaluation-target-resolution-remains-separate",
            "formal-g0-capacity-and-closure-gates-not-satisfied",
        ],
        "replacement_contracts": _replacement_contracts(),
        "scope_relation_rules": _scope_relation_rules(),
        "transition_algebra_model": {
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
            "symbolic_equalities_required_after_solve": [
                {"left_symbol": "qN", "relation": "must-equal", "right_symbol": "qP"}
            ],
            "symbolic_partition_rules": [
                {
                    "part_symbols": ["qXD", "qXR"],
                    "relation": "exact-sum",
                    "whole_symbol": "qX",
                }
            ],
            "transition_unit_semantics": (
                "contributor-events-use-abstract-units-cross-scope-move-uses-explicit-ledger-projections"
            ),
        },
        "suite_summary": _suite_summary(),
        "wave_delta_rules": _wave_delta_rules(),
    }
    return value


@functools.lru_cache(maxsize=1)
def _cached_lifecycle_demand():
    return _canonical_lifecycle_demand()


def build_lifecycle_demand():
    """Return a detached deterministic pre-solve lifecycle demand."""

    return copy.deepcopy(_cached_lifecycle_demand())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 lifecycle demand",
            max_bytes=MAX_LIFECYCLE_DEMAND_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def validate_lifecycle_demand(value):
    try:
        return independent.validate_lifecycle_demand(
            value,
            chunk_accounting_value=chunk_accounting.build_chunk_accounting_contract(),
            envelope_value=envelope.build_envelope_contract(),
            overlay_contract_value=overlay.build_overlay_contract(),
        )
    except independent.PersonaV2LifecycleDemandValidationError as error:
        _fail(str(error))


def lifecycle_demand_sha256(value=None):
    if value is None:
        value = build_lifecycle_demand()
    validate_lifecycle_demand(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_compiled_history_plan():
    raise PersonaV2LifecycleDemandError(
        "lifecycle demand is pre-solve only; source matching, solved cardinalities, "
        "concrete locations, compiled events, receipts, and execution remain absent"
    )
