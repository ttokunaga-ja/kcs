"""Builder-independent validation for formal source-recipe profile bindings.

The validator intentionally imports neither the catalog producer nor any
renderer implementation.  It accepts the four frozen upstream bodies as
explicit data, authenticates their canonical bytes before using any row, and
then independently reconstructs the complete seventy-one-row artifact.

The caller must provide the registry's renderer/validator contract providers
and renderer probe provider.  They are inputs to the already-independent
registry validator, which reruns runtime conformance before any receipt is
projected here.  Every projected receipt is then joined again by variant,
implementation pair, renderer binding, and validator binding.  This prevents
a caller from rethreading a valid receipt or provider result onto another
recipe profile.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_format_implementation_registry_validator as registry_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_format_implementation_registry_validator as registry_validator


ARTIFACT_SCHEMA = "kio.persona.pc-formal-source-recipe-profile-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-formal-source-recipe-profile-catalog"
MAX_CATALOG_BYTES = 1024 * 1024
MAX_DEPENDENCY_BYTES = 2 * 1024 * 1024
MAX_FRAGMENT_BYTES = 128 * 1024
EXPECTED_PROFILE_COUNT = 71

# These pins cover the canonical body, not a self hash.  Any policy or
# dependency change is therefore review-visible.
EXPECTED_CATALOG_CANONICAL_BYTES = 386_152
EXPECTED_CATALOG_SHA256 = (
    "0ac0906397c8d81b7504637fe119d45ae2ffa7acb7cb47b719c985121ce1b2df"
)

DEPENDENCY_PINS = {
    "persona-v2-variant-catalog": (
        "persona-pc-v2-variant-catalog",
        "kio.persona.pc-variant-catalog/v2",
        2,
        211_733,
        "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    "persona-v2-source-inventory-profile-catalog": (
        "persona-pc-v2-source-inventory-profile-catalog",
        "kio.persona.pc-source-inventory-profile-catalog/v2",
        2,
        87_391,
        "9b0de3defbc106f0bfa8b96ca2134886acd6766ac69196e3498b6b6f7edf43c0",
    ),
    "persona-v2-format-implementation-registry": (
        "persona-pc-v2-format-implementation-registry",
        "kio.persona.pc-format-implementation-registry/v2",
        2,
        333_881,
        "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d",
    ),
    "persona-v2-source-semantic-membership-catalog": (
        "persona-pc-v2-source-semantic-membership-catalog",
        "kio.persona.pc-source-semantic-membership-catalog/v2",
        2,
        436_495,
        "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b",
    ),
}

DEPENDENCY_ROLES = {
    "persona-v2-variant-catalog": (
        "variant-identity-marginals-search-and-lane-policy"
    ),
    "persona-v2-source-inventory-profile-catalog": (
        "inventory-profile-and-reserved-recipe-slot-identity"
    ),
    "persona-v2-format-implementation-registry": (
        "all-71-format-contracts-and-runtime-conformance-receipts"
    ),
    "persona-v2-source-semantic-membership-catalog": (
        "semantic-content-and-filename-template-slot-identity"
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_payload_bytes_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_plan",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_instances",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "authorizes_source_recipe_instances",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "renderer_execution_environment_available",
        "semantic_payload_adapter_available",
    }
)

EXPECTED_COVERAGE = {
    "contract_contributor": {
        "full": 69_236,
        "full-residual": 62_311,
        "pilot": 6_925,
        "variant_count": 10,
    },
    "incidental_searchable": {
        "full": 60_414,
        "full-residual": 54_374,
        "pilot": 6_040,
        "variant_count": 11,
    },
    "raw_only": {
        "full": 73_350,
        "full-residual": 66_015,
        "pilot": 7_335,
        "variant_count": 50,
    },
    "total": {
        "active_persona_variant_rows": 541,
        "full": 203_000,
        "full-residual": 182_700,
        "pilot": 20_300,
        "profile_count": 71,
    },
}

FORBIDDEN_INSTANCE_KEYS = frozenset(
    {
        "basename",
        "final_source_id",
        "intent_key",
        "materialization_id",
        "path",
        "payload_seed",
        "scope_key",
        "selected_basename",
        "selected_target_bytes",
        "selected_target_complexity",
        "solution_sha256",
        "source_id",
        "source_instances",
        "source_rows",
    }
)


class PersonaV2FormalSourceRecipeCatalogValidationError(ValueError):
    """Raised when independent recipe-profile validation fails."""


def _fail(message):
    raise PersonaV2FormalSourceRecipeCatalogValidationError(message)


def _canonical(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_negative_authority(value, *, label, exact_fields=None):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if exact_fields is not None and set(authority) != exact_fields:
        _fail(f"{label} authority schema drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must be all false")


def _authenticate_dependency(name, value):
    if type(value) is not dict:
        _fail(f"{name} must be an object")
    expected_kind, expected_schema, expected_version, expected_bytes, expected_sha = (
        DEPENDENCY_PINS[name]
    )
    if (
        value.get("artifact_kind") != expected_kind
        or value.get("artifact_schema") != expected_schema
        or value.get("artifact_schema_version") != expected_version
    ):
        _fail(f"{name} identity drifted")
    _require_negative_authority(value, label=name)
    raw = _canonical(value, label=name, max_bytes=MAX_DEPENDENCY_BYTES)
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    if actual != (expected_bytes, expected_sha):
        _fail(f"{name} differs from its frozen body pin")
    return {
        "artifact_kind": expected_kind,
        "artifact_schema": expected_schema,
        "artifact_schema_version": expected_version,
        "canonical_bytes": expected_bytes,
        "dependency_role": DEPENDENCY_ROLES[name],
        "name": name,
        "sha256": expected_sha,
    }


def _exact_unique_map(rows, key, *, expected_count, label):
    if type(rows) is not list or len(rows) != expected_count:
        _fail(f"{label} cardinality drifted")
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get(key)) is not str or not row[key]:
            _fail(f"{label} contains an invalid {key}")
        if row[key] in result:
            _fail(f"{label} repeats {key}: {row[key]}")
        result[row[key]] = row
    return result


def _recipe_profile_id(variant_id):
    return f"persona-v2-formal-source-recipe-profile-{variant_id}-v2"


def _content_profile_id(variant_id):
    return f"persona-v2-content-template-profile-{variant_id}-v2"


def _filename_profile_id(variant_id):
    return f"persona-v2-filename-template-profile-{variant_id}-v2"


def _chunk_policy_rows():
    return [
        {
            "contract_chunk_denominator_eligible": True,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": False,
                "exact_value": 0,
                "selected_value_present": False,
            },
            "gate_role": "contract_contributor",
            "incidental_cap_eligible": False,
            "observed_chunk_gate": "actual-equals-assigned-quota",
            "policy_id": "persona-v2-contract-contributor-chunk-policy-v2",
            "requested_chunks": {
                "inclusive_maximum": 70,
                "inclusive_minimum": 1,
                "mode": "source-instance-integer-range",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "not-applicable",
        },
        {
            "contract_chunk_denominator_eligible": False,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": True,
                "inclusive_maximum": 15_000,
                "inclusive_minimum": 0,
                "selected_value_present": False,
            },
            "gate_role": "incidental_searchable",
            "incidental_cap_eligible": True,
            "observed_chunk_gate": "actual-within-source-and-wave-cap",
            "policy_id": "persona-v2-incidental-searchable-chunk-policy-v2",
            "requested_chunks": {
                "exact_value": 0,
                "mode": "exact-zero",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "persona-v2-dynamic-incidental-wave-caps-v2",
        },
        {
            "contract_chunk_denominator_eligible": False,
            "expected_incidental_chunks_upper": {
                "assignment_required_at_source_instance": False,
                "exact_value": 0,
                "selected_value_present": False,
            },
            "gate_role": "raw_only",
            "incidental_cap_eligible": False,
            "observed_chunk_gate": "actual-equals-zero",
            "policy_id": "persona-v2-raw-only-chunk-policy-v2",
            "requested_chunks": {
                "exact_value": 0,
                "mode": "exact-zero",
                "selected_value_present": False,
            },
            "requested_chunks_equal_format_complexity": False,
            "wave_cap_policy_id": "not-applicable",
        },
    ]


def _dynamic_incidental_wave_cap_policy():
    profile_inputs = (
        ("full", 135_000, 210_000, 15_000, 30_000),
        ("pilot", 13_500, 21_000, 1_500, 3_000),
    )
    checkpoints = {
        "full": (
            ("W0", 120_000, 0),
            ("W1", 120_000, 24_000),
            ("W2", 120_000, 24_000),
            ("W3", 120_000, 48_000),
            ("W4", 120_000, 60_000),
            ("W5-pre-purge", 124_800, 64_800),
            ("W5-final", 120_000, 60_000),
        ),
        "pilot": (
            ("W0", 12_000, 0),
            ("W1", 12_000, 2_400),
            ("W2", 12_000, 2_400),
            ("W3", 12_000, 4_800),
            ("W4", 12_000, 6_000),
            ("W5-pre-purge", 12_480, 6_480),
            ("W5-final", 12_000, 6_000),
        ),
    }
    rows = []
    for (
        profile,
        current_eligible,
        total_eligible,
        base_current,
        base_total,
    ) in profile_inputs:
        checkpoint_rows = []
        for checkpoint, current_chunks, history_chunks in checkpoints[profile]:
            current_cap = min(base_current, current_eligible - current_chunks)
            total_cap = min(
                base_total,
                total_eligible - current_chunks - history_chunks,
            )
            if current_cap < 0 or total_cap < current_cap:
                _fail("dynamic incidental checkpoint cap is internally invalid")
            checkpoint_rows.append(
                {
                    "checkpoint": checkpoint,
                    "contributor_current_chunks": current_chunks,
                    "contributor_history_only_chunks": history_chunks,
                    "incidental_current_cap": current_cap,
                    "incidental_current_plus_history_cap": total_cap,
                }
            )
        rows.append(
            {
                "base_incidental_current": base_current,
                "base_incidental_current_plus_history": base_total,
                "checkpoint_rows": checkpoint_rows,
                "current_eligible_ceiling": current_eligible,
                "current_plus_history_eligible_ceiling": total_eligible,
                "profile": profile,
            }
        )
    return {
        "cap_formulas": {
            "current": (
                "min(base-incidental-current,current-eligible-ceiling-minus-C(w))"
            ),
            "current_plus_history": (
                "min(base-incidental-current-plus-history,current-plus-history-"
                "eligible-ceiling-minus-C(w)-minus-H(w))"
            ),
        },
        "exact_integer_profile_and_checkpoint_table": True,
        "observed_values_present": False,
        "policy_id": "persona-v2-dynamic-incidental-wave-caps-v2",
        "profile_rows": rows,
        "source_instance_assignments_present": False,
    }


def _policy_catalogs(variant_value):
    lane_contracts = variant_value.get("lane_contracts")
    if type(lane_contracts) is not dict:
        _fail("variant catalog lane contracts are missing")
    return {
        "dynamic_incidental_wave_cap_policy": (
            _dynamic_incidental_wave_cap_policy()
        ),
        "filename_core_policy": {
            "basename_case": "lowercase-ascii",
            "casefold_uniqueness_check_phase": "downstream-final-source-plan",
            "collision_suffix_from_internal_identity_forbidden": True,
            "empty_optional_component_rule": "omit-before-hyphen-join",
            "extension_appended_exactly_once": True,
            "identity_tokens_forbidden": [
                "digest",
                "fixture-nonce",
                "intent-key",
                "materialization-id",
                "persona-id",
                "source-id",
            ],
            "lowercase_ascii_required": True,
            "max_basename_bytes": 120,
            "overlength_rule": "reject-source-instance-no-truncation",
            "path_separator_forbidden": True,
            "policy_id": "persona-v2-lowercase-ascii-semantic-basename-v2",
            "primary_entity_selection": "minimum-synthetic-entity-id-ascii",
            "stem_component_order": [
                "document-role",
                "project-or-case-slug",
                "primary-synthetic-entity-slug",
                "period",
                "status",
                "version",
            ],
            "stem_separator": "hyphen",
            "token_grammar": "lowercase-ascii-alnum-with-internal-hyphens",
            "version_grammar": "literal-v-plus-zero-padded-two-digit-positive-integer",
        },
        "gate_role_chunk_policies": _chunk_policy_rows(),
        "lane_contracts": copy.deepcopy(lane_contracts),
    }


def _fact_rule(role):
    if role == "raw_only":
        return "empty-present-fact-profile-only-no-search-participation"
    if role in {"contract_contributor", "incidental_searchable"}:
        return "source-owned-nonempty-present-fact-profile-required"
    _fail(f"unknown gate role: {role}")


def _content_policy(semantic_row, variant_id):
    return {
        "content_instance_values_bound": False,
        "content_template_profile_id": _content_profile_id(variant_id),
        "content_template_slot_id": semantic_row["content_template_slot_id"],
        "control_input_fields": [
            "document-role",
            "fact-graph-projection",
            "language",
            "period",
            "project-or-case",
            "semantic-version",
            "status",
            "synthetic-entities",
            "topic",
        ],
        "document_role": semantic_row["document_role"],
        "fact_profile_rule": _fact_rule(semantic_row["gate_role"]),
        "language_binding_mode": semantic_row["language_binding_mode"],
        "literal_exposure_forbidden_fields": [
            "digest-or-hash",
            "fixture-nonce",
            "intent-key",
            "materialization-id",
            "persona-id",
            "query-oracle-review-identifiers",
            "scope-key-or-path",
            "source-id",
        ],
        "query_oracle_inputs_allowed": False,
        "semantic_content_adapter_conformance_attested": False,
        "semantic_membership_mode": (
            "source-owned-content-context-and-present-fact-set-by-intent-key"
        ),
    }


def _filename_policy(semantic_row, implementation_row):
    variant_id = implementation_row["variant_id"]
    return {
        "basename_instance_bound": False,
        "basename_policy_id": "persona-v2-lowercase-ascii-semantic-basename-v2",
        "compound_suffix_parts": copy.deepcopy(
            implementation_row["compound_suffix_parts"]
        ),
        "filename_extension": implementation_row["filename_extension"],
        "filename_template_profile_id": _filename_profile_id(variant_id),
        "filename_template_slot_id": semantic_row["filename_template_slot_id"],
        "scope_casefold_uniqueness_attested": False,
    }


def _validate_registry_ownership(registry_value):
    contract_rows = registry_value.get("contract_bindings")
    contract_by_id = _exact_unique_map(
        contract_rows,
        "binding_id",
        expected_count=16,
        label="registry contract bindings",
    )
    pair_rows = registry_value.get("implementation_pair_conformance_receipts")
    pair_by_id = _exact_unique_map(
        pair_rows,
        "implementation_pair_id",
        expected_count=8,
        label="registry pair conformance receipts",
    )
    implementation_by_variant = _exact_unique_map(
        registry_value.get("implementation_rows"),
        "variant_id",
        expected_count=EXPECTED_PROFILE_COUNT,
        label="registry implementation rows",
    )
    for variant_id, row in implementation_by_variant.items():
        implementation = row.get("implementation")
        receipt = row.get("conformance_receipt")
        if type(implementation) is not dict or type(receipt) is not dict:
            _fail(f"registry implementation/receipt missing: {variant_id}")
        pair_id = implementation.get("pair_id")
        renderer = contract_by_id.get(implementation.get("renderer_binding_id"))
        validator = contract_by_id.get(implementation.get("validator_binding_id"))
        pair_receipt = pair_by_id.get(pair_id)
        if renderer is None or validator is None or pair_receipt is None:
            _fail(f"registry implementation binding is unresolved: {variant_id}")
        if (
            renderer.get("contract_role") != "renderer"
            or validator.get("contract_role") != "validator"
            or renderer.get("implementation_id")
            != implementation.get("renderer_id")
            or renderer.get("implementation_schema_version")
            != implementation.get("renderer_schema_version")
            or validator.get("implementation_id")
            != implementation.get("validator_id")
            or validator.get("implementation_schema_version")
            != implementation.get("validator_schema_version")
            or renderer.get("implementation_pair_id") != pair_id
            or validator.get("implementation_pair_id") != pair_id
            or variant_id not in renderer.get("variant_ids", [])
            or variant_id not in validator.get("variant_ids", [])
            or pair_receipt.get("implementation_pair_id") != pair_id
        ):
            _fail(f"registry contract/receipt ownership is rethreaded: {variant_id}")
        probes = receipt.get("probes")
        if (
            receipt.get("actual_chunks_attested") is not False
            or receipt.get("actual_payload_bytes_attested") is not False
            or receipt.get("probe_count") != 3
            or receipt.get("probe_profile") != "minimum-midpoint-maximum-v2"
            or receipt.get("validator_accepted_all") is not True
            or type(probes) is not list
            or [probe.get("lane") for probe in probes]
            != ["minimum", "midpoint", "maximum"]
        ):
            _fail(f"registry conformance receipt shape drifted: {variant_id}")
        for probe in probes:
            if (
                type(probe) is not dict
                or type(probe.get("payload_sha256")) is not str
                or len(probe["payload_sha256"]) != 64
                or type(probe.get("validator_receipt_sha256")) is not str
                or len(probe["validator_receipt_sha256"]) != 64
            ):
                _fail(f"registry probe receipt is malformed: {variant_id}")
    return contract_by_id, pair_by_id, implementation_by_variant


def _implementation_binding(implementation_row, contract_by_id):
    implementation = implementation_row["implementation"]
    renderer = contract_by_id[implementation["renderer_binding_id"]]
    validator = contract_by_id[implementation["validator_binding_id"]]
    return {
        "implementation_pair_id": implementation["pair_id"],
        "implementation_profile_id": implementation["implementation_profile_id"],
        "renderer": {
            "binding_id": renderer["binding_id"],
            "contract_sha256": renderer["sha256"],
            "renderer_id": implementation["renderer_id"],
            "renderer_schema_version": implementation["renderer_schema_version"],
        },
        "validator": {
            "binding_id": validator["binding_id"],
            "contract_sha256": validator["sha256"],
            "validator_id": implementation["validator_id"],
            "validator_profile_id": implementation["validator_profile_id"],
            "validator_schema_version": implementation["validator_schema_version"],
        },
    }


def _runtime_binding(implementation_row, pair_receipt):
    receipt = implementation_row["conformance_receipt"]
    receipt_raw = _canonical(
        receipt,
        label="variant runtime conformance receipt",
        max_bytes=MAX_FRAGMENT_BYTES,
    )
    pair_raw = _canonical(
        pair_receipt,
        label="implementation-pair conformance receipt",
        max_bytes=MAX_FRAGMENT_BYTES,
    )
    return {
        "conformance_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "conformance_scope": (
            "identity-free-minimum-midpoint-maximum-format-feasibility-only"
        ),
        "implementation_pair_id": implementation_row["implementation"]["pair_id"],
        "pair_payload_aggregate_sha256": pair_receipt[
            "payload_aggregate_sha256"
        ],
        "pair_receipt_sha256": hashlib.sha256(pair_raw).hexdigest(),
        "payload_aggregate_sha256": receipt["aggregate_sha256"],
        "probe_count": receipt["probe_count"],
        "probe_profile": receipt["probe_profile"],
        "runtime_validator_accepted_all": receipt["validator_accepted_all"],
        "variant_id": implementation_row["variant_id"],
    }


def _complexity_byte_policy(implementation_row):
    normalized = implementation_row["normalized_contract"]
    return {
        "complexity": copy.deepcopy(normalized["complexity"]),
        "formal_lane_policy_id": "formal-retrieval-history-v2",
        "formula": copy.deepcopy(normalized["formula"]),
        "lane": copy.deepcopy(normalized["lane"]),
        "parameter_shape": copy.deepcopy(normalized["parameter_shape"]),
        "quantization": copy.deepcopy(normalized["quantization"]),
        "selected_parameter_values_present": False,
        "selected_target_bytes_present": False,
        "selected_target_complexity_present": False,
        "target_bytes_binding_mode": "derived-exactly-by-renderer-formula",
    }


def _source_count_projection(variant_id, marginals):
    rows = marginals[variant_id]
    pilot = sum(row["pilot_count"] for row in rows)
    residual = sum(row["full_minus_pilot_count"] for row in rows)
    full = sum(row["full_count"] for row in rows)
    if full != pilot + residual:
        _fail(f"pilot/residual count arithmetic drifted: {variant_id}")
    return {
        "active_persona_count": sum(row["full_count"] > 0 for row in rows),
        "full": full,
        "full-residual": residual,
        "pilot": pilot,
        "projection_only_no_source_instances": True,
    }


def _profile_row(
    variant_row,
    inventory_row,
    implementation_row,
    semantic_row,
    contract_by_id,
    pair_by_id,
    marginals,
):
    variant_id = variant_row["variant_id"]
    if not all(
        row.get("variant_id") == variant_id
        for row in (inventory_row, implementation_row, semantic_row)
    ):
        _fail(f"profile upstream join drifted: {variant_id}")
    expected_recipe = {
        "binding_status": "reserved-unbound",
        "parameters_complete": False,
        "profile_id": "not-bound",
        "slot_id": f"persona-v2-source-recipe-slot-{variant_id}-v2",
    }
    if inventory_row.get("source_recipe") != expected_recipe:
        _fail(f"upstream recipe reservation drifted: {variant_id}")
    expected_semantic_binding = {
        "content_template_slot_id": (
            f"persona-v2-content-template-slot-{variant_id}-v2"
        ),
        "filename_template_slot_id": (
            f"persona-v2-filename-template-slot-{variant_id}-v2"
        ),
        "formal_recipe_binding_status": "reserved-unbound",
        "semantic_profile_id": (
            f"persona-v2-source-semantic-profile-{variant_id}-v2"
        ),
        "source_profile_id": inventory_row.get("source_profile_id"),
    }
    if any(
        semantic_row.get(field) != expected
        for field, expected in expected_semantic_binding.items()
    ):
        _fail(f"upstream semantic recipe-slot binding drifted: {variant_id}")
    exact_fields = (
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
        "safety_profile_id",
    )
    for field in exact_fields:
        expected = variant_row[field]
        if (
            inventory_row[field] != expected
            or implementation_row[field] != expected
            or semantic_row.get(field, expected) != expected
        ):
            _fail(f"profile metadata drifted: {variant_id}/{field}")
    if implementation_row.get("search_contract") != variant_row.get(
        "search_contract"
    ):
        _fail(f"profile search/chunk contract drifted: {variant_id}")
    source_counts = _source_count_projection(variant_id, marginals)
    registry_counts = implementation_row["normalized_contract"]["lane"][
        "source_counts"
    ]
    if any(
        registry_counts[profile] != source_counts[profile]
        for profile in ("pilot", "full-residual", "full")
    ):
        _fail(f"profile registry/count projection drifted: {variant_id}")
    implementation = implementation_row["implementation"]
    pair_receipt = pair_by_id[implementation["pair_id"]]
    policy_id = {
        "contract_contributor": "persona-v2-contract-contributor-chunk-policy-v2",
        "incidental_searchable": "persona-v2-incidental-searchable-chunk-policy-v2",
        "raw_only": "persona-v2-raw-only-chunk-policy-v2",
    }.get(variant_row["gate_role"])
    if policy_id is None:
        _fail(f"unknown profile gate role: {variant_id}")
    return {
        "binding_status": "profile-bound-instance-unbound",
        "chunk_policy": {
            "policy_id": policy_id,
            "selected_requested_chunks_present": False,
            "source_instance_incidental_upper_present": False,
        },
        "complexity_byte_policy": _complexity_byte_policy(implementation_row),
        "content_media_type": variant_row["content_media_type"],
        "content_policy": _content_policy(semantic_row, variant_id),
        "expected_kio_path_media_type": variant_row[
            "expected_kio_path_media_type"
        ],
        "expected_offline_disposition": variant_row[
            "expected_offline_disposition"
        ],
        "family": variant_row["family"],
        "filename_policy": _filename_policy(semantic_row, implementation_row),
        "format_feasibility_render_template_id": implementation_row[
            "render_template"
        ],
        "gate_role": variant_row["gate_role"],
        "implementation_binding": _implementation_binding(
            implementation_row, contract_by_id
        ),
        "recipe_profile_id": _recipe_profile_id(variant_id),
        "runtime_conformance_binding": _runtime_binding(
            implementation_row, pair_receipt
        ),
        "safety_profile_id": variant_row["safety_profile_id"],
        "semantic_profile_id": semantic_row["semantic_profile_id"],
        "source_count_projection": source_counts,
        "source_inventory_profile_id": inventory_row["source_profile_id"],
        "source_recipe_slot_id": expected_recipe["slot_id"],
        "variant_id": variant_id,
    }


def _coverage(rows):
    result = {}
    for role in ("contract_contributor", "incidental_searchable", "raw_only"):
        selected = [row for row in rows if row["gate_role"] == role]
        result[role] = {
            "full": sum(row["source_count_projection"]["full"] for row in selected),
            "full-residual": sum(
                row["source_count_projection"]["full-residual"] for row in selected
            ),
            "pilot": sum(row["source_count_projection"]["pilot"] for row in selected),
            "variant_count": len(selected),
        }
    result["total"] = {
        "active_persona_variant_rows": sum(
            row["source_count_projection"]["active_persona_count"] for row in rows
        ),
        "full": sum(row["source_count_projection"]["full"] for row in rows),
        "full-residual": sum(
            row["source_count_projection"]["full-residual"] for row in rows
        ),
        "pilot": sum(row["source_count_projection"]["pilot"] for row in rows),
        "profile_count": len(rows),
    }
    return result


def _walk_forbidden_instances(value):
    if type(value) is dict:
        for key, item in value.items():
            if key in FORBIDDEN_INSTANCE_KEYS:
                _fail(f"recipe profile catalog embeds source-instance field: {key}")
            _walk_forbidden_instances(item)
    elif type(value) is list:
        for item in value:
            _walk_forbidden_instances(item)


def _expected_value(
    variant_value,
    inventory_value,
    registry_value,
    semantic_value,
    input_bindings,
):
    variant_rows = variant_value.get("variant_rows")
    if type(variant_rows) is not list or len(variant_rows) != EXPECTED_PROFILE_COUNT:
        _fail("variant catalog must contain exact 71 ordered rows")
    variant_ids = [row.get("variant_id") for row in variant_rows]
    if any(type(value) is not str or not value for value in variant_ids) or len(
        set(variant_ids)
    ) != EXPECTED_PROFILE_COUNT:
        _fail("variant catalog identities are not exact and unique")
    inventory_by_variant = _exact_unique_map(
        inventory_value.get("source_profile_rows"),
        "variant_id",
        expected_count=EXPECTED_PROFILE_COUNT,
        label="inventory profiles",
    )
    contract_by_id, pair_by_id, implementation_by_variant = (
        _validate_registry_ownership(registry_value)
    )
    semantic_by_variant = _exact_unique_map(
        semantic_value.get("semantic_profiles"),
        "variant_id",
        expected_count=EXPECTED_PROFILE_COUNT,
        label="semantic profiles",
    )
    marginal_rows = variant_value.get("persona_variant_marginals")
    if type(marginal_rows) is not list or len(marginal_rows) != 566:
        _fail("variant catalog marginal cardinality drifted")
    marginals = {variant_id: [] for variant_id in variant_ids}
    for marginal in marginal_rows:
        variant_id = marginal.get("variant_id") if type(marginal) is dict else None
        if variant_id not in marginals:
            _fail("variant catalog marginal has an unknown variant")
        marginals[variant_id].append(marginal)

    rows = [
        _profile_row(
            variant_row,
            inventory_by_variant[variant_row["variant_id"]],
            implementation_by_variant[variant_row["variant_id"]],
            semantic_by_variant[variant_row["variant_id"]],
            contract_by_id,
            pair_by_id,
            marginals,
        )
        for variant_row in variant_rows
    ]
    if (
        len({row["recipe_profile_id"] for row in rows}) != EXPECTED_PROFILE_COUNT
        or len({row["source_recipe_slot_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len({row["source_inventory_profile_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len({row["semantic_profile_id"] for row in rows})
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["content_policy"]["content_template_profile_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["content_policy"]["content_template_slot_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["filename_policy"]["filename_template_profile_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
        or len(
            {row["filename_policy"]["filename_template_slot_id"] for row in rows}
        )
        != EXPECTED_PROFILE_COUNT
    ):
        _fail("recipe, inventory, semantic, content, or filename profiles are not bijective")
    coverage = _coverage(rows)
    if coverage != EXPECTED_COVERAGE:
        _fail("formal recipe profile coverage drifted")
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "exact_recipe_profile_rows": EXPECTED_PROFILE_COUNT,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_71_formal_recipe_profile_policies_bound": True,
            "content_and_filename_policy_profiles_bound": True,
            "exact_recipe_slot_profile_bijection": True,
            "format_contracts_and_runtime_receipts_bound": True,
            "physical_source_materialization_complete": False,
            "selected_complexity_and_bytes_present": False,
            "semantic_payload_materialization_complete": False,
            "source_instance_parameter_values_bound": False,
            "source_instances_bound": False,
            "source_level_allocation_solution_present": False,
        },
        "completion_scope": (
            "exact-71-formal-source-recipe-profile-policies-only-no-source-"
            "instances-no-selected-parameters-no-solver-no-render-no-write-no-g0"
        ),
        "coverage": coverage,
        "fixture_id": variant_value["fixture_id"],
        "fixture_schema_version": variant_value["fixture_schema_version"],
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "dependency_bindings": "variant-inventory-implementation-semantic",
            "recipe_profile_rows": "exact-upstream-variant-catalog-order",
        },
        "policy_catalogs": _policy_catalogs(variant_value),
        "recipe_profile_rows": rows,
        "remaining_blockers": [
            "all-source-instance-values-and-source-intent-bodies-unbound",
            "semantic-content-adapter-conformance-and-payload-materialization-unbound",
            "scope-bucket-cohort-quota-solver-solution-and-proof-unbound",
            "ordinary-tail-counts-byte-histograms-and-capacity-receipts-unbound",
            "production-mime-and-actual-chunk-observation-unbound",
            "physical-render-write-history-kio-and-g0-authority-absent",
        ],
    }


def validate_formal_source_recipe_catalog(
    value,
    *,
    variant_catalog_value,
    source_inventory_profile_value,
    format_implementation_registry_value,
    source_semantic_membership_catalog_value,
    historical_source_profile_value,
    renderer_contract_provider,
    validator_contract_provider,
    renderer_probe_provider,
):
    """Validate the exact profile catalog and its runtime-registry dependency."""

    if type(value) is not dict:
        _fail("formal source recipe profile catalog must be an object")
    actual_raw = _canonical(
        value,
        label="persona v2 formal source recipe profile catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if EXPECTED_CATALOG_CANONICAL_BYTES <= 0 or len(EXPECTED_CATALOG_SHA256) != 64:
        _fail("formal source recipe catalog final pins are not installed")
    if (
        len(actual_raw) != EXPECTED_CATALOG_CANONICAL_BYTES
        or hashlib.sha256(actual_raw).hexdigest() != EXPECTED_CATALOG_SHA256
    ):
        _fail("formal source recipe profile catalog body pin drifted")
    frozen_value = copy.deepcopy(value)
    frozen_variant_catalog = copy.deepcopy(variant_catalog_value)
    frozen_inventory_profiles = copy.deepcopy(source_inventory_profile_value)
    frozen_registry = copy.deepcopy(format_implementation_registry_value)
    frozen_semantic_catalog = copy.deepcopy(
        source_semantic_membership_catalog_value
    )
    frozen_historical_catalog = copy.deepcopy(historical_source_profile_value)
    _require_negative_authority(
        frozen_value,
        label="formal source recipe profile catalog",
        exact_fields=AUTHORITY_FIELDS,
    )
    _walk_forbidden_instances(frozen_value)

    dependencies = [
        ("persona-v2-variant-catalog", frozen_variant_catalog),
        (
            "persona-v2-source-inventory-profile-catalog",
            frozen_inventory_profiles,
        ),
        (
            "persona-v2-format-implementation-registry",
            frozen_registry,
        ),
        (
            "persona-v2-source-semantic-membership-catalog",
            frozen_semantic_catalog,
        ),
    ]
    input_bindings = [
        _authenticate_dependency(name, dependency)
        for name, dependency in dependencies
    ]
    try:
        registry_validator.validate_format_implementation_registry(
            frozen_registry,
            variant_catalog_value=frozen_variant_catalog,
            historical_source_profile_value=frozen_historical_catalog,
            source_inventory_profile_value=frozen_inventory_profiles,
            renderer_contract_provider=renderer_contract_provider,
            validator_contract_provider=validator_contract_provider,
            renderer_probe_provider=renderer_probe_provider,
        )
    except (
        registry_validator.PersonaV2FormatImplementationRegistryValidationError
    ) as error:
        _fail(f"format implementation registry runtime validation failed: {error}")
    expected = _expected_value(
        frozen_variant_catalog,
        frozen_inventory_profiles,
        frozen_registry,
        frozen_semantic_catalog,
        input_bindings,
    )
    expected_raw = _canonical(
        expected,
        label="independently reconstructed formal source recipe profile catalog",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if actual_raw != expected_raw:
        _fail(
            "formal source recipe profile catalog differs from independent reconstruction"
        )
    # Provider callbacks are untrusted and may retain aliases to caller-owned
    # objects.  All reconstruction above uses opening snapshots; after the
    # callbacks, re-authenticate the original formal body and every supplied
    # dependency so a persistent in-validation mutation cannot escape the
    # opening pins.
    final_raw = _canonical(
        value,
        label="persona v2 formal source recipe profile catalog after callbacks",
        max_bytes=MAX_CATALOG_BYTES,
    )
    if final_raw != actual_raw:
        _fail("formal source recipe profile catalog mutated during validation")
    for name, dependency in (
        ("persona-v2-variant-catalog", variant_catalog_value),
        (
            "persona-v2-source-inventory-profile-catalog",
            source_inventory_profile_value,
        ),
        (
            "persona-v2-format-implementation-registry",
            format_implementation_registry_value,
        ),
        (
            "persona-v2-source-semantic-membership-catalog",
            source_semantic_membership_catalog_value,
        ),
    ):
        _authenticate_dependency(name, dependency)
    registry_validator._validate_upstream_binding(
        historical_source_profile_value,
        registry_validator.EXPECTED_INPUT_BINDINGS[1],
        label="frozen historical source profile catalog after provider callbacks",
    )
    return True


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CATALOG_CANONICAL_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "MAX_CATALOG_BYTES",
    "PersonaV2FormalSourceRecipeCatalogValidationError",
    "validate_formal_source_recipe_catalog",
]
