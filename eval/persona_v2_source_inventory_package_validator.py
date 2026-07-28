"""Builder-independent validation for the full persona-PC v2 source package.

This module deliberately does not import ``persona_v2_source_inventory_package``.
It reconstructs the admissible 203,000-row domain from the frozen layout,
variant/profile catalogs, and independently checked overlay reservations.  Shard
bodies are consumed through the bounded canonical-JSONL reader one shard at a
time; a successful result is evidence about this non-authorizing metadata
package only and grants no renderer, writer, solver, KIO, history, or G0
authority.
"""

from __future__ import annotations

import copy
import functools
import gc
import hashlib
import io
from bisect import bisect_left

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_bounded_jsonl as bounded_jsonl
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_overlay_reservation_validator as reservation_validator
    from . import persona_v2_source_inventory_layout as source_layout
    from . import persona_v2_source_inventory_profile as inventory_profile
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_bounded_jsonl as bounded_jsonl
    import persona_v2_contract as envelope
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_overlay_reservation_validator as reservation_validator
    import persona_v2_source_inventory_layout as source_layout
    import persona_v2_source_inventory_profile as inventory_profile
    import persona_v2_variant_catalog as variant_catalog


ORIGIN_ARTIFACT_SCHEMA = "kio.persona.pc-source-inventory-origin-manifest/v2"
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-source-inventory-origin-manifest"
PROFILE_ARTIFACT_SCHEMA = "kio.persona.pc-source-inventory-profile-manifest/v2"
PROFILE_ARTIFACT_KIND = "persona-pc-v2-source-inventory-profile-manifest"
SUITE_ARTIFACT_SCHEMA = "kio.persona.pc-source-inventory-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-source-inventory-suite"
ARTIFACT_SCHEMA_VERSION = 2

ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full")
GATE_ROLE_ORDER = (
    "contract_contributor",
    "incidental_searchable",
    "raw_only",
)

MAX_ROW_BYTES_INCLUDING_LF = 768
MAX_ROWS_PER_SHARD = 4_096
MAX_SHARD_BODY_BYTES = 4 * 2**20
MAX_ORIGIN_MANIFEST_BYTES = 128 * 1024
MAX_PROFILE_MANIFEST_BYTES = 128 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 256 * 1024
MAX_PERSONA_CURRENT_COMPONENT_BYTES = 16 * 2**20

EXPECTED_PERSONA_COUNT = 20
EXPECTED_PILOT_ROW_COUNT = 20_300
EXPECTED_RESIDUAL_ROW_COUNT = 182_700
EXPECTED_FULL_ROW_COUNT = 203_000
EXPECTED_PILOT_SHARD_COUNT = 20
EXPECTED_RESIDUAL_SHARD_COUNT = 53
EXPECTED_SHARD_COUNT = 73
EXPECTED_OVERLAY_REFERENCE_COUNT = 46_840
EXPECTED_SEMANTIC_ANCHOR_COUNT = 2_100
EXPECTED_OVERLAY_ROLE_COUNTS = {
    "contract_contributor": 25_765,
    "incidental_searchable": 21_075,
    "raw_only": 0,
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "joint_allocation_proved",
        "kio_execution_available",
        "source_intent_refinement_policy_bound",
    }
)

ROW_FIELDS = frozenset(
    {
        "content_context_id",
        "deterministic_payload_seed",
        "eligible_scope_set_id",
        "intent_key",
        "origin",
        "persona_id",
        "placement_context_id",
        "present_fact_set_key",
        "quota_context_id",
        "source_profile_id",
    }
)

SHARD_DESCRIPTOR_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "file_name",
        "first_intent_key",
        "first_origin_ordinal",
        "last_intent_key",
        "last_origin_ordinal",
        "max_row_bytes_including_lf",
        "origin",
        "persona_id",
        "row_count",
        "shard_id",
        "shard_ordinal",
    }
)

ORIGIN_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "origin",
        "persona_id",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "variant_source_counts",
    }
)
PROFILE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "origin_manifest_bindings",
        "persona_id",
        "profile",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "variant_source_counts",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "coverage",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "orders",
        "origin_manifest_bindings",
        "persona_current_component_byte_ledgers",
        "profile_manifest_bindings",
        "remaining_blockers",
    }
)
ORIGIN_SUMMARY_FIELDS = frozenset(
    {
        "gate_role_source_counts",
        "implementation_missing_source_count",
        "local_feasibility_ready_source_count",
        "maximum_row_bytes_including_lf",
        "overlay_referenced_unique_source_intent_count",
        "semantic_anchor_slot_count",
        "shard_body_bytes",
        "shard_count",
        "source_intent_count",
        "unreserved_source_intent_count",
        "variant_with_sources_count",
    }
)
ORIGIN_VARIANT_COUNT_FIELDS = frozenset(
    {
        "first_intent_key",
        "first_origin_ordinal",
        "gate_role",
        "last_intent_key",
        "last_origin_ordinal",
        "row_count",
        "source_profile_id",
        "variant_id",
    }
)
PROFILE_SUMMARY_FIELDS = frozenset(
    {
        "full_residual_origin_manifest_count",
        "gate_role_source_counts",
        "maximum_row_bytes_including_lf",
        "origin_manifest_count",
        "pilot_origin_manifest_count",
        "reused_pilot_shard_body_bytes",
        "reused_pilot_shard_count",
        "reused_pilot_source_intent_count",
        "shard_body_bytes",
        "shard_count",
        "source_intent_count",
        "variant_with_sources_count",
    }
)
PROFILE_VARIANT_COUNT_FIELDS = frozenset(
    {"gate_role", "row_count", "source_profile_id", "variant_id"}
)
SUITE_COVERAGE_FIELDS = frozenset(
    {
        "full_residual_source_intent_count",
        "gate_role_source_counts",
        "maximum_origin_manifest_bytes",
        "maximum_profile_manifest_bytes",
        "maximum_row_bytes_including_lf",
        "maximum_shard_body_bytes",
        "origin_manifest_count",
        "persona_count",
        "pilot_source_intent_count",
        "profile_manifest_count",
        "shard_body_bytes",
        "shard_count",
        "source_intent_count",
        "variant_identity_count",
        "variant_with_sources_count",
    }
)
PERSONA_LEDGER_FIELDS = frozenset(
    {
        "current_component_bytes",
        "future_complete_package_cap_proved",
        "headroom_bytes",
        "included_components",
        "max_current_component_bytes",
        "persona_id",
        "profile_manifest_bytes",
        "source_origin_manifest_bytes",
        "unique_source_shard_body_bytes",
    }
)

PUBLIC_INPUT_BINDING_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "dependency_role",
        "name",
        "sha256",
    }
)
RESERVATION_ORIGIN_INPUT_BINDING_FIELDS = frozenset(
    set(PUBLIC_INPUT_BINDING_FIELDS) | {"origin", "persona_id"}
)
ORIGIN_MANIFEST_BINDING_FIELDS = frozenset(
    set(PUBLIC_INPUT_BINDING_FIELDS) | {"origin", "persona_id"}
)
PROFILE_MANIFEST_BINDING_FIELDS = frozenset(
    set(PUBLIC_INPUT_BINDING_FIELDS) | {"persona_id", "profile"}
)

ORIGIN_CANONICAL_LIMITS = {
    "intent_jsonl_record_terminator": "LF",
    "max_body_bytes": MAX_ORIGIN_MANIFEST_BYTES,
    "max_intent_row_bytes_including_lf": MAX_ROW_BYTES_INCLUDING_LF,
    "max_intents_per_shard": MAX_ROWS_PER_SHARD,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_shard_body_bytes": MAX_SHARD_BODY_BYTES,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "unicode_normalization": "NFC",
}
ORIGIN_COMPLETION_CLAIMS = {
    "all_shard_bodies_materialized": True,
    "all_source_slot_rows_materialized": True,
    "body_bytes_and_sha_bound": True,
    "bounded_jsonl_descriptor_contract_bound": True,
    "concrete_overlay_membership_bound": False,
    "exact_variant_inventory_profile_assignments_complete": True,
    "formal_source_recipe_profiles_bound": False,
    "full_persona_package_bound_proved": False,
    "present_fact_sets_bound": False,
    "renderer_validator_implementation_complete": False,
    "semantic_content_catalogs_bound": False,
    "source_intent_inventory_complete": False,
    "source_intent_origin_manifest_complete": True,
    "source_level_exact_allocation_complete": False,
}
ORIGIN_COMPLETION_SCOPE = (
    "one-persona-one-origin-all-structural-source-slot-rows-and-shard-"
    "digests-only-no-semantic-catalog-no-formal-recipe-no-execution-no-g0"
)
ORIGIN_DEPENDENCY_CONTRACT = {
    "evaluation_query_or_oracle_identity_imported": False,
    "future_concrete_overlay_manifest_must_bind_reservation_source_and_fact_manifests": True,
    "future_source_owned_fact_manifest_must_bind_this_origin_manifest": True,
    "reservation_origin_is_strictly_upstream": True,
    "source_manifest_may_bind_future_fact_or_concrete_overlay_manifest": False,
}
ORIGIN_REMAINING_BLOCKERS = [
    "semantic-content-context-catalogs-not-bound",
    "source-owned-present-fact-set-manifests-not-bound",
    "all-formal-source-recipe-profiles-unbound",
    "sixty-one-renderer-validator-or-formula-implementations-missing",
    "concrete-overlay-membership-not-bound",
    "source-level-scope-placement-allocation-not-solved",
    "render-write-chunk-observation-and-history-not-present",
    "future-complete-persona-package-cap-not-proved",
]

PROFILE_CANONICAL_LIMITS = {
    "max_body_bytes": MAX_PROFILE_MANIFEST_BYTES,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_persona_current_source_component_bytes": MAX_PERSONA_CURRENT_COMPONENT_BYTES,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "unicode_normalization": "NFC",
}
PROFILE_COMPLETION_SCOPE = (
    "one-persona-structural-source-profile-manifest-with-exact-pilot-"
    "origin-reuse-no-semantic-catalog-no-formal-recipe-no-execution-no-g0"
)
PROFILE_DEPENDENCY_CONTRACT = {
    "full_profile_origin_order_is_pilot_then_full_residual": True,
    "full_profile_reuses_exact_pilot_origin_manifest_and_shard_descriptors": True,
    "profile_manifest_may_bind_future_fact_or_concrete_overlay_manifest": False,
    "source_origin_manifests_are_strictly_upstream": True,
}

SUITE_CANONICAL_LIMITS = {
    "max_body_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_persona_current_source_component_bytes": MAX_PERSONA_CURRENT_COMPONENT_BYTES,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "unicode_normalization": "NFC",
}
SUITE_COMPLETION_CLAIMS = {
    "all_203000_source_slot_rows_materialized": True,
    "all_40_origin_manifests_bound": True,
    "all_40_profile_manifests_bound": True,
    "all_73_shard_body_bytes_and_sha_bound": True,
    "all_variant_inventory_profile_assignments_complete": True,
    "concrete_overlay_membership_bound": False,
    "current_source_inventory_component_cap_satisfied": True,
    "formal_complete_persona_package_cap_proved": False,
    "formal_source_recipe_profiles_bound": False,
    "full_manifest_exact_pilot_origin_reuse_proved": True,
    "present_fact_sets_bound": False,
    "semantic_content_catalogs_bound": False,
    "source_intent_inventory_complete": False,
}
SUITE_COMPLETION_SCOPE = (
    "all-203000-structural-source-slot-rows-73-shards-40-origin-and-40-"
    "profile-manifests-only-no-semantic-catalog-no-formal-recipe-no-"
    "complete-package-cap-no-execution-no-g0"
)
SUITE_DEPENDENCY_CONTRACT = {
    "future_source_owned_fact_manifests_bind_origin_manifests": True,
    "profile_manifests_bind_origin_manifests_without_backedges": True,
    "reservation_source_profile_and_layout_artifacts_are_strictly_upstream": True,
    "suite_may_bind_future_fact_concrete_overlay_or_execution_artifact": False,
}
SUITE_REMAINING_BLOCKERS = [
    "semantic-content-and-source-owned-fact-membership-manifests-not-bound",
    "all-formal-source-recipe-profiles-unbound",
    "sixty-one-renderer-validator-or-formula-implementations-missing",
    "concrete-overlay-membership-shards-and-manifests-not-present",
    "source-level-scope-placement-allocation-not-solved",
    "future-complete-persona-package-cap-not-proved",
    "render-write-chunk-observation-history-and-kio-execution-not-present",
]
SUITE_ORDERS = {
    "origin": list(ORIGIN_ORDER),
    "origin_manifests": "persona-then-origin",
    "persona": list(envelope.PERSONA_IDS),
    "profile": list(PROFILE_ORDER),
    "profile_manifests": "persona-then-profile",
    "shards_within_profile": (
        "pilot-origin-then-full-residual-origin-then-shard-ordinal"
    ),
}
LEDGER_INCLUDED_COMPONENTS = [
    "unique-pilot-and-full-residual-source-jsonl-shard-bodies",
    "pilot-and-full-residual-source-origin-manifests",
    "pilot-and-full-source-profile-manifests",
]

# The producer may name negative guards explicitly, but no downstream identity,
# rendered payload, evaluation input, solver output, or fact-manifest digest may
# enter this source-slot package.
PROHIBITED_FIELD_NAMES = frozenset(
    {
        "allocation_solution_sha256",
        "answer_membership",
        "chunk_id",
        "compiled_relevance",
        "concrete_overlay_membership_sha256",
        "fact_membership_sha256",
        "final_materialization_id",
        "final_source_id",
        "history_event_key",
        "history_intent_sha256",
        "input_closure_manifest_sha256",
        "logical_branch_key",
        "logical_document_key",
        "logical_revision_key",
        "materialization_id",
        "payload_equivalence_key",
        "physical_path",
        "query_id",
        "query_instance_id",
        "query_text",
        "raw_bytes",
        "rendered_body",
        "rendered_bytes",
        "rendered_sha256",
        "scope_id",
        "scope_key",
        "semantic_oracle",
        "semantic_section_key",
        "solution_sha256",
        "source_plan_sha256",
    }
)


class PersonaV2SourceInventoryPackageValidationError(ValueError):
    """Raised when the full source inventory package fails validation."""


def _fail(message):
    raise PersonaV2SourceInventoryPackageValidationError(message)


def _require_exact_fields(value, expected, *, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(f"{label} must contain the exact field set")


def _require_exact_int(value, *, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum:
        _fail(f"{label} must be an exact integer >= {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} exceeds {maximum}")


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be a lowercase SHA-256 digest")


def _canonical_bytes(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_canonical_equal(actual, expected, *, label, max_bytes=MAX_SUITE_DESCRIPTOR_BYTES):
    actual_raw = _canonical_bytes(actual, label=label, max_bytes=max_bytes)
    expected_raw = _canonical_bytes(
        expected, label=f"expected {label}", max_bytes=max_bytes
    )
    if actual_raw != expected_raw:
        _fail(f"{label} differs from its exact expected value")


def _reject_prohibited_fields(value, *, path="$"):
    if type(value) is dict:
        for key, child in value.items():
            if key in PROHIBITED_FIELD_NAMES:
                _fail(f"{path}.{key} is a prohibited downstream field")
            _reject_prohibited_fields(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_prohibited_fields(child, path=f"{path}[{index}]")


def _require_all_false_authority(authority, expected_fields, *, label):
    if type(authority) is not dict or set(authority) != set(expected_fields):
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must contain exact all-false booleans")


def _validate_common_envelope(value, *, kind, schema, label):
    if (
        type(value) is not dict
        or value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
    ):
        _fail(f"{label} identity or non-G0 boundary drifted")
    _require_all_false_authority(
        value.get("authority"), AUTHORITY_FIELDS, label=label
    )


def _validate_input_bindings(value, expected_bindings, expected_order, *, label):
    bindings = value.get("input_bindings")
    order = value.get("input_binding_order")
    if (
        type(bindings) is not list
        or type(order) is not list
        or len(bindings) != len(expected_bindings)
        or len(order) != len(expected_order)
    ):
        _fail(f"{label} input binding coverage drifted")
    _require_canonical_equal(
        order, list(expected_order), label=f"{label} input binding order"
    )
    _require_canonical_equal(
        bindings,
        list(expected_bindings),
        label=f"{label} exact input bindings",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )


def _profile_completion_claims(profile):
    return {
        "all_profile_origin_manifests_bound": True,
        "all_profile_shard_references_bound": True,
        "concrete_overlay_membership_bound": False,
        "formal_source_recipe_profiles_bound": False,
        "full_profile_composition_bound": profile == "full",
        "full_profile_exact_pilot_origin_reuse_proved": profile == "full",
        "pilot_profile_single_origin_bound": profile == "pilot",
        "present_fact_sets_bound": False,
        "semantic_content_catalogs_bound": False,
        "source_intent_inventory_complete": False,
        "source_intent_profile_manifest_complete": True,
    }


def _public_binding(name, role, value, *, canonical):
    raw = canonical(value)
    actual = hashlib.sha256(raw).hexdigest()
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": actual,
    }


@functools.lru_cache(maxsize=1)
def _upstream_inputs():
    layout = source_layout.build_source_inventory_layout()
    variants = variant_catalog.build_variant_catalog()
    profiles = inventory_profile.build_source_inventory_profile_catalog()

    source_layout.validate_source_inventory_layout(layout)
    variant_catalog.validate_variant_catalog(variants)
    inventory_profile.validate_source_inventory_profile_catalog(profiles)

    layouts = {row["persona_id"]: row for row in layout["personas"]}
    profile_by_variant = {
        row["variant_id"]: row["source_profile_id"]
        for row in profiles["source_profile_rows"]
    }
    ready_by_variant = {
        row["variant_id"]: row["bounded_feasibility"][
            "local_vertical_slice_ready"
        ]
        for row in profiles["source_profile_rows"]
    }
    role_by_variant = {
        row["variant_id"]: row["gate_role"]
        for row in variants["variant_rows"]
    }
    if (
        tuple(layouts) != envelope.PERSONA_IDS
        or set(profile_by_variant) != set(role_by_variant)
    ):
        _fail("upstream coverage or identity ordering drifted")

    layout_binding = _public_binding(
        "persona-v2-source-inventory-layout",
        "exact-source-key-ranges-and-shard-partition",
        layout,
        canonical=source_layout.canonical_json_bytes,
    )
    profile_binding = _public_binding(
        "persona-v2-source-inventory-profile-catalog",
        "all-variant-source-profile-foreign-keys",
        profiles,
        canonical=inventory_profile.canonical_json_bytes,
    )
    return {
        "layout": layout,
        "layouts": layouts,
        "layout_binding": layout_binding,
        "profiles": profiles,
        "profile_binding": profile_binding,
        "profile_by_variant": profile_by_variant,
        "ready_by_variant": ready_by_variant,
        "role_by_variant": role_by_variant,
        "variants": variants,
    }


def _clear_reservation_working_caches():
    for module, names in (
        (
            reservation_layout,
            ("_canonical_origin", "_intent_slot_tuples_by_variant"),
        ),
        (reservation_validator, ("_source_domain",)),
    ):
        for name in names:
            clear = getattr(getattr(module, name, None), "cache_clear", None)
            if callable(clear):
                clear()


@functools.lru_cache(maxsize=1)
def _reservation_inputs():
    reservation_suite = reservation_layout.build_overlay_reservation_suite()
    reservation_layout.validate_overlay_reservation_suite(reservation_suite)
    reservation_binding_by_origin = {
        (row["persona_id"], row["origin"]): row
        for row in reservation_suite["origin_bindings"]
    }
    if len(reservation_binding_by_origin) != 40:
        _fail("reservation suite origin coverage drifted")

    # The compact suite build may have populated verbose origin/source-domain
    # caches.  They are derivation caches only, so release them before the
    # bounded one-origin-at-a-time independent pass.
    _clear_reservation_working_caches()
    gc.collect()
    reservation_requirements = {}
    reservation_summaries = {}
    for persona_id in envelope.PERSONA_IDS:
        for origin in ORIGIN_ORDER:
            artifact = reservation_layout.build_overlay_reservation_origin(
                persona_id, origin
            )
            reservation_validator.validate_overlay_reservation_origin(artifact)
            raw = reservation_layout.canonical_json_bytes(artifact)
            binding = reservation_binding_by_origin[(persona_id, origin)]
            if (
                type(binding["canonical_bytes"]) is not int
                or binding["canonical_bytes"] != len(raw)
                or binding["sha256"] != hashlib.sha256(raw).hexdigest()
            ):
                _fail("reservation suite does not bind the independently checked origin")
            reservation_requirements[(persona_id, origin)] = (
                _extract_overlay_requirements(artifact)
            )
            summary = artifact["summary"]
            reservation_summaries[(persona_id, origin)] = {
                "overlay_referenced_unique_source_intent_count": summary[
                    "overlay_referenced_unique_source_intent_count"
                ],
                "semantic_anchor_slot_count": summary[
                    "semantic_anchor_slot_count"
                ],
                "unreserved_source_intent_count": summary[
                    "unreserved_source_intent_count"
                ],
            }
            del artifact, raw
            _clear_reservation_working_caches()

    reservation_suite_raw = artifact_common.canonical_json_bytes(
        reservation_suite,
        label="persona v2 overlay reservation suite",
        max_bytes=reservation_layout.MAX_SUITE_ARTIFACT_BYTES,
    )
    reservation_suite_binding = {
        "artifact_kind": reservation_suite["artifact_kind"],
        "artifact_schema": reservation_suite["artifact_schema"],
        "artifact_schema_version": reservation_suite["artifact_schema_version"],
        "canonical_bytes": len(reservation_suite_raw),
        "dependency_role": "overlay-source-reference-reservations",
        "name": "persona-v2-overlay-reservation-suite",
        "sha256": hashlib.sha256(reservation_suite_raw).hexdigest(),
    }
    if reservation_suite_binding[
        "sha256"
    ] != reservation_layout.overlay_reservation_suite_sha256(reservation_suite):
        _fail("overlay reservation suite public digest drifted")
    gc.collect()
    return {
        "reservation_requirements": reservation_requirements,
        "reservation_summaries": reservation_summaries,
        "reservation_bindings": reservation_binding_by_origin,
        "reservation_suite": reservation_suite,
        "reservation_suite_binding": reservation_suite_binding,
    }


def _expected_shared_input_bindings():
    upstream = _upstream_inputs()
    reservations = _reservation_inputs()
    return [
        upstream["layout_binding"],
        upstream["profile_binding"],
        reservations["reservation_suite_binding"],
    ]


def _expected_origin_input_bindings(persona_id, origin):
    result = list(_expected_shared_input_bindings())
    source = _reservation_inputs()["reservation_bindings"][(persona_id, origin)]
    result.append(
        {
            "artifact_kind": source["artifact_kind"],
            "artifact_schema": source["artifact_schema"],
            "artifact_schema_version": source["artifact_schema_version"],
            "canonical_bytes": source["canonical_bytes"],
            "dependency_role": "matching-overlay-source-reference-reservation",
            "name": "persona-v2-overlay-reservation-origin",
            "origin": origin,
            "persona_id": persona_id,
            "sha256": source["sha256"],
        }
    )
    return result


def _layout_persona(persona_id):
    try:
        return _upstream_inputs()["layouts"][persona_id]
    except KeyError:
        _fail(f"unknown persona ID: {persona_id!r}")


def _expected_layout_shards(persona_id, origin):
    if origin not in ORIGIN_ORDER:
        _fail(f"unknown source origin: {origin!r}")
    return [
        row
        for row in _layout_persona(persona_id)["shards"]
        if row["origin"] == origin
    ]


@functools.lru_cache(maxsize=40)
def _variant_ranges(persona_id, origin):
    reservations = _layout_persona(persona_id)["variant_reservations"][origin]
    return (
        tuple(row["last_origin_ordinal"] for row in reservations),
        tuple(row["variant_id"] for row in reservations),
    )


def _variant_for_ordinal(persona_id, origin, ordinal):
    ends, variants = _variant_ranges(persona_id, origin)
    index = bisect_left(ends, ordinal)
    if index == len(ends) or ordinal < 1:
        _fail(
            "source ordinal is outside the variant reservation: "
            f"{persona_id}/{origin}/{ordinal}"
        )
    return variants[index]


def _expected_row(persona_id, origin, ordinal):
    width = 4 if origin == "pilot" else 5
    suffix = f"{ordinal:0{width}d}"
    variant_id = _variant_for_ordinal(persona_id, origin, ordinal)
    return {
        "content_context_id": f"{persona_id}-content-slot-{origin}-syn-{suffix}",
        "deterministic_payload_seed": (
            f"{persona_id}-payload-seed-{origin}-syn-{suffix}"
        ),
        "eligible_scope_set_id": f"{persona_id}-eligible-scope-set-v2",
        "intent_key": source_layout.intent_key(persona_id, origin, ordinal),
        "origin": origin,
        "persona_id": persona_id,
        "placement_context_id": (
            f"{persona_id}-placement-slot-{origin}-syn-{suffix}"
        ),
        "present_fact_set_key": (
            f"{persona_id}-present-fact-set-{origin}-syn-{suffix}"
        ),
        "quota_context_id": f"{persona_id}-quota-slot-{origin}-syn-{suffix}",
        "source_profile_id": _upstream_inputs()["profile_by_variant"][variant_id],
    }


def _expected_origin_variant_counts(persona_id, origin):
    result = []
    roles = _upstream_inputs()["role_by_variant"]
    profile_ids = _upstream_inputs()["profile_by_variant"]
    for reservation in _layout_persona(persona_id)["variant_reservations"][origin]:
        variant_id = reservation["variant_id"]
        result.append(
            {
                "first_intent_key": reservation["first_intent_key"],
                "first_origin_ordinal": reservation["first_origin_ordinal"],
                "gate_role": roles[variant_id],
                "last_intent_key": reservation["last_intent_key"],
                "last_origin_ordinal": reservation["last_origin_ordinal"],
                "row_count": reservation["row_count"],
                "source_profile_id": profile_ids[variant_id],
                "variant_id": variant_id,
            }
        )
    return result


def _expected_profile_variant_counts(persona_id, profile):
    count_field = "pilot_count" if profile == "pilot" else "full_count"
    roles = _upstream_inputs()["role_by_variant"]
    profile_ids = _upstream_inputs()["profile_by_variant"]
    result = []
    for row in _upstream_inputs()["variants"]["persona_variant_marginals"]:
        if row["persona_id"] != persona_id or row[count_field] == 0:
            continue
        variant_id = row["variant_id"]
        result.append(
            {
                "gate_role": roles[variant_id],
                "row_count": row[count_field],
                "source_profile_id": profile_ids[variant_id],
                "variant_id": variant_id,
            }
        )
    return result


def _extract_overlay_requirements(artifact):
    """Compact one independently validated reservation artifact."""

    result = {}

    def add(intent_key, variant_id, gate_role, kind):
        expected = (variant_id, gate_role)
        if intent_key in result and result[intent_key][:2] != expected:
            _fail(f"overlay reservation disagrees about source identity: {intent_key}")
        result.setdefault(intent_key, (variant_id, gate_role, set()))[2].add(kind)

    for slot in artifact["semantic_anchor_slots"]:
        add(slot["intent_key"], slot["variant_id"], slot["gate_role"], "anchor")
    for row in artifact["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            add(
                row["anchor_intent_key"],
                row["endpoint_variant_id"],
                row["endpoint_gate_role"],
                "overlay",
            )
            add(
                row["derivative_intent_key"],
                row["endpoint_variant_id"],
                row["endpoint_gate_role"],
                "overlay",
            )
        elif row["row_kind"] == "attachment-membership-reservation":
            add(
                row["host_intent_key"],
                row["host_variant_id"],
                row["host_gate_role"],
                "overlay",
            )
            add(
                row["standalone_member_intent_key"],
                row["standalone_member_variant_id"],
                row["standalone_member_gate_role"],
                "overlay",
            )
        else:  # Already independently checked, but stay fail-closed.
            _fail(f"unknown overlay reservation row kind: {row.get('row_kind')!r}")
    return result


def _overlay_requirements(persona_id, origin):
    """Return reserved key -> exact upstream variant/role expectations."""

    return _reservation_inputs()["reservation_requirements"][(persona_id, origin)]


def _expected_shard_descriptor(layout_shard, body_bytes, rows):
    maximum_row_bytes = max(
        len(
            artifact_common.canonical_json_bytes(
                row,
                label="persona v2 source intent row",
                max_bytes=MAX_ROW_BYTES_INCLUDING_LF - 1,
            )
        )
        + 1
        for row in rows
    )
    return {
        "body_bytes": len(body_bytes),
        "body_sha256": hashlib.sha256(body_bytes).hexdigest(),
        "file_name": f"{layout_shard['shard_id']}.jsonl",
        "first_intent_key": layout_shard["first_intent_key"],
        "first_origin_ordinal": layout_shard["first_origin_ordinal"],
        "last_intent_key": layout_shard["last_intent_key"],
        "last_origin_ordinal": layout_shard["last_origin_ordinal"],
        "max_row_bytes_including_lf": maximum_row_bytes,
        "origin": layout_shard["origin"],
        "persona_id": layout_shard["persona_id"],
        "row_count": layout_shard["row_count"],
        "shard_id": layout_shard["shard_id"],
        "shard_ordinal": layout_shard["shard_ordinal"],
    }


def _validate_descriptor_before_body(descriptor, layout_shard):
    _require_exact_fields(
        descriptor, SHARD_DESCRIPTOR_FIELDS, label="source shard descriptor"
    )
    exact_layout_projection = {
        "first_intent_key": layout_shard["first_intent_key"],
        "first_origin_ordinal": layout_shard["first_origin_ordinal"],
        "last_intent_key": layout_shard["last_intent_key"],
        "last_origin_ordinal": layout_shard["last_origin_ordinal"],
        "origin": layout_shard["origin"],
        "persona_id": layout_shard["persona_id"],
        "row_count": layout_shard["row_count"],
        "shard_id": layout_shard["shard_id"],
        "shard_ordinal": layout_shard["shard_ordinal"],
    }
    for field in (
        "first_origin_ordinal",
        "last_origin_ordinal",
        "row_count",
        "shard_ordinal",
    ):
        _require_exact_int(descriptor[field], label=f"source shard {field}")
    if any(
        type(descriptor[field]) is not type(expected)
        or descriptor[field] != expected
        for field, expected in exact_layout_projection.items()
    ):
        _fail("source shard descriptor range/order differs from the frozen layout")
    if descriptor["file_name"] != f"{layout_shard['shard_id']}.jsonl":
        _fail("source shard file name differs from its immutable shard ID")
    _require_exact_int(
        descriptor["body_bytes"],
        label="source shard body_bytes",
        minimum=1,
        maximum=MAX_SHARD_BODY_BYTES,
    )
    _require_sha256(descriptor["body_sha256"], label="source shard body_sha256")
    _require_exact_int(
        descriptor["max_row_bytes_including_lf"],
        label="source shard max_row_bytes_including_lf",
        minimum=3,
        maximum=MAX_ROW_BYTES_INCLUDING_LF,
    )


def _provider_body(provider, persona_id, origin, shard_ordinal):
    if not callable(provider):
        _fail("shard_body_provider must be callable")
    try:
        body = provider(persona_id, origin, shard_ordinal)
    except Exception as error:
        raise PersonaV2SourceInventoryPackageValidationError(
            f"shard body provider failed for {persona_id}/{origin}/{shard_ordinal}"
        ) from error
    if type(body) is not bytes:
        _fail("shard body provider must return exact bytes")
    return body


def _validate_manifest_binding(
    binding, manifest, raw, *, coordinates, name, role, label
):
    if type(binding) is not dict:
        _fail(f"{label} must be an object")
    expected = {
        "artifact_kind": manifest["artifact_kind"],
        "artifact_schema": manifest["artifact_schema"],
        "artifact_schema_version": manifest["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    expected.update({field: manifest[field] for field in coordinates})
    _require_exact_fields(binding, expected, label=label)
    _require_canonical_equal(binding, expected, label=label)
    _require_exact_int(
        binding["canonical_bytes"], label=f"{label} canonical_bytes", minimum=1
    )
    _require_sha256(binding["sha256"], label=f"{label} sha256")


def _validate_profile_composition(
    profile_by_key, profile_raw_by_key, origin_by_key, origin_raw_by_key
):
    for persona_id in envelope.PERSONA_IDS:
        pilot = profile_by_key[(persona_id, "pilot")]
        full = profile_by_key[(persona_id, "full")]
        pilot_origin = origin_by_key[(persona_id, "pilot")]
        residual_origin = origin_by_key[(persona_id, "full-residual")]
        expected = {
            "pilot": [("pilot", pilot_origin)],
            "full": [("pilot", pilot_origin), ("full-residual", residual_origin)],
        }
        for profile, manifest in (("pilot", pilot), ("full", full)):
            bindings = manifest.get("origin_manifest_bindings")
            if type(bindings) is not list or len(bindings) != len(expected[profile]):
                _fail(f"{persona_id}/{profile} origin manifest coverage drifted")
            descriptors = []
            for binding, (origin, origin_manifest) in zip(
                bindings, expected[profile]
            ):
                _validate_manifest_binding(
                    binding,
                    origin_manifest,
                    origin_raw_by_key[(persona_id, origin)],
                    coordinates=("persona_id", "origin"),
                    name="persona-v2-source-inventory-origin-manifest",
                    role="immutable-source-origin-manifest",
                    label="profile-to-origin manifest binding",
                )
                descriptors.extend(origin_manifest["shard_descriptors"])
            _require_canonical_equal(
                manifest.get("shard_descriptors"),
                descriptors,
                label=f"{persona_id}/{profile} shard composition",
                max_bytes=MAX_PROFILE_MANIFEST_BYTES,
            )
        if _canonical_bytes(
            full["origin_manifest_bindings"][0],
            label="full pilot manifest binding",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        ) != _canonical_bytes(
            pilot["origin_manifest_bindings"][0],
            label="pilot manifest binding",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        ):
            _fail(f"{persona_id}/full does not byte-reuse the pilot manifest binding")
        pilot_descriptors = pilot["shard_descriptors"]
        if _canonical_bytes(
            full["shard_descriptors"][: len(pilot_descriptors)],
            label="full pilot shard descriptor prefix",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        ) != _canonical_bytes(
            pilot_descriptors,
            label="pilot shard descriptors",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        ):
            _fail(f"{persona_id}/full does not byte-reuse the pilot shard descriptors")


def _validate_suite_manifest_bindings(
    suite,
    origin_manifests,
    origin_raw_by_key,
    profile_manifests,
    profile_raw_by_key,
):
    origin_bindings = suite.get("origin_manifest_bindings")
    profile_bindings = suite.get("profile_manifest_bindings")
    if type(origin_bindings) is not list or len(origin_bindings) != 40:
        _fail("suite must bind exactly forty origin manifests")
    if type(profile_bindings) is not list or len(profile_bindings) != 40:
        _fail("suite must bind exactly forty profile manifests")
    for binding, manifest in zip(origin_bindings, origin_manifests):
        key = (manifest["persona_id"], manifest["origin"])
        _validate_manifest_binding(
            binding,
            manifest,
            origin_raw_by_key[key],
            coordinates=("persona_id", "origin"),
            name="persona-v2-source-inventory-origin-manifest",
            role="source-origin-manifest",
            label="suite-to-origin manifest binding",
        )
    for binding, manifest in zip(profile_bindings, profile_manifests):
        key = (manifest["persona_id"], manifest["profile"])
        _validate_manifest_binding(
            binding,
            manifest,
            profile_raw_by_key[key],
            coordinates=("persona_id", "profile"),
            name="persona-v2-source-inventory-profile-manifest",
            role="source-profile-manifest",
            label="suite-to-profile manifest binding",
        )


def _load_and_validate_shard(descriptor, layout_shard, provider, requirements):
    _validate_descriptor_before_body(descriptor, layout_shard)
    body = _provider_body(
        provider,
        layout_shard["persona_id"],
        layout_shard["origin"],
        layout_shard["shard_ordinal"],
    )
    if len(body) != descriptor["body_bytes"]:
        _fail("source shard provider bytes differ from the declared bounded length")
    if len(body) > MAX_SHARD_BODY_BYTES:
        _fail("source shard body exceeds the four-MiB cap")
    try:
        rows = bounded_jsonl.load_declared_canonical_jsonl(
            io.BytesIO(body),
            declared_body_bytes=descriptor["body_bytes"],
            descriptor={
                "body_sha256": descriptor["body_sha256"],
                "first_key": descriptor["first_intent_key"],
                "last_key": descriptor["last_intent_key"],
                "row_count": descriptor["row_count"],
            },
            key_field="intent_key",
            max_body_bytes=MAX_SHARD_BODY_BYTES,
            max_row_bytes_including_lf=MAX_ROW_BYTES_INCLUDING_LF,
            max_rows=MAX_ROWS_PER_SHARD,
        )
    except bounded_jsonl.PersonaV2BoundedJsonlError as error:
        _fail(str(error))

    expected_descriptor = _expected_shard_descriptor(layout_shard, body, rows)
    if descriptor != expected_descriptor:
        _fail("source shard descriptor differs from its exact body and layout")

    role_counts = {role: 0 for role in GATE_ROLE_ORDER}
    variant_counts = {}
    seen_overlay = set()
    first_ordinal = layout_shard["first_origin_ordinal"]
    for offset, row in enumerate(rows):
        ordinal = first_ordinal + offset
        _require_exact_fields(row, ROW_FIELDS, label="source intent row")
        expected = _expected_row(
            layout_shard["persona_id"], layout_shard["origin"], ordinal
        )
        if row != expected:
            _fail(f"source intent row formula or variant assignment drifted: {expected['intent_key']}")
        variant_id = _variant_for_ordinal(
            layout_shard["persona_id"], layout_shard["origin"], ordinal
        )
        role = _upstream_inputs()["role_by_variant"][variant_id]
        role_counts[role] += 1
        variant_counts[variant_id] = variant_counts.get(variant_id, 0) + 1
        requirement = requirements.get(row["intent_key"])
        if requirement is not None:
            if requirement[:2] != (variant_id, role):
                _fail(f"source row does not satisfy overlay reservation: {row['intent_key']}")
            seen_overlay.add(row["intent_key"])
    return {
        "body_bytes": len(body),
        "descriptor": expected_descriptor,
        "role_counts": role_counts,
        "row_count": len(rows),
        "seen_overlay": seen_overlay,
        "variant_counts": variant_counts,
    }


def _validate_source_inventory_package_snapshot(
    suite, origin_manifests, profile_manifests, shard_body_provider
):
    """Validate the suite, eighty manifests, and seventy-three shard bodies.

    The callable is invoked as ``provider(persona_id, origin, shard_ordinal)``
    and must return exact ``bytes``.  Bodies are parsed and released one shard
    at a time; the validator never assembles the 203,000 rows in memory.
    """

    # The manifest/suite envelope validation is intentionally completed below
    # once their exact public field contracts have been checked.  The early
    # plain-value and prohibited-field checks make all later indexing safe and
    # ensure downstream identities cannot be hidden in an unused field.
    _canonical_bytes(
        suite,
        label="persona v2 source inventory suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    _require_exact_fields(
        suite, SUITE_TOP_LEVEL_FIELDS, label="source inventory suite"
    )
    _reject_prohibited_fields(suite)
    _validate_common_envelope(
        suite,
        kind=SUITE_ARTIFACT_KIND,
        schema=SUITE_ARTIFACT_SCHEMA,
        label="source inventory suite",
    )
    _require_canonical_equal(
        suite["canonical_limits"], SUITE_CANONICAL_LIMITS, label="suite canonical limits"
    )
    _require_canonical_equal(
        suite["completion_claims"],
        SUITE_COMPLETION_CLAIMS,
        label="suite completion claims",
    )
    _require_canonical_equal(
        suite["completion_scope"], SUITE_COMPLETION_SCOPE, label="suite completion scope"
    )
    _require_canonical_equal(
        suite["dependency_direction_contract"],
        SUITE_DEPENDENCY_CONTRACT,
        label="suite dependency-direction contract",
    )
    _require_canonical_equal(
        suite["remaining_blockers"],
        SUITE_REMAINING_BLOCKERS,
        label="suite blocker ledger",
    )
    _require_canonical_equal(suite["orders"], SUITE_ORDERS, label="suite orders")
    _validate_input_bindings(
        suite,
        _expected_shared_input_bindings(),
        (
            "persona-v2-source-inventory-layout",
            "persona-v2-source-inventory-profile-catalog",
            "persona-v2-overlay-reservation-suite",
        ),
        label="source inventory suite",
    )
    if type(origin_manifests) is not list or type(profile_manifests) is not list:
        _fail("origin_manifests and profile_manifests must be canonical lists")
    if len(origin_manifests) != 40 or len(profile_manifests) != 40:
        _fail("source package must supply exactly forty origin and forty profile manifests")

    expected_origins = [
        (persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    expected_profiles = [
        (persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    origin_by_key = {}
    origin_raw_by_key = {}
    for manifest, (persona_id, origin) in zip(origin_manifests, expected_origins):
        raw = _canonical_bytes(
            manifest,
            label="persona v2 source inventory origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reject_prohibited_fields(manifest)
        _require_exact_fields(
            manifest,
            ORIGIN_TOP_LEVEL_FIELDS,
            label="source inventory origin manifest",
        )
        _validate_common_envelope(
            manifest,
            kind=ORIGIN_ARTIFACT_KIND,
            schema=ORIGIN_ARTIFACT_SCHEMA,
            label="source inventory origin manifest",
        )
        if manifest.get("persona_id") != persona_id or manifest.get("origin") != origin:
            _fail("origin manifests are not in canonical persona/origin order")
        _require_canonical_equal(
            manifest["canonical_limits"],
            ORIGIN_CANONICAL_LIMITS,
            label=f"origin canonical limits {persona_id}/{origin}",
        )
        _require_canonical_equal(
            manifest["completion_claims"],
            ORIGIN_COMPLETION_CLAIMS,
            label=f"origin completion claims {persona_id}/{origin}",
        )
        _require_canonical_equal(
            manifest["completion_scope"],
            ORIGIN_COMPLETION_SCOPE,
            label=f"origin completion scope {persona_id}/{origin}",
        )
        _require_canonical_equal(
            manifest["dependency_direction_contract"],
            ORIGIN_DEPENDENCY_CONTRACT,
            label=f"origin dependency-direction contract {persona_id}/{origin}",
        )
        _require_canonical_equal(
            manifest["remaining_blockers"],
            ORIGIN_REMAINING_BLOCKERS,
            label=f"origin blocker ledger {persona_id}/{origin}",
        )
        _validate_input_bindings(
            manifest,
            _expected_origin_input_bindings(persona_id, origin),
            (
                "persona-v2-source-inventory-layout",
                "persona-v2-source-inventory-profile-catalog",
                "persona-v2-overlay-reservation-suite",
                "persona-v2-overlay-reservation-origin",
            ),
            label=f"source inventory origin {persona_id}/{origin}",
        )
        _require_exact_fields(
            manifest.get("summary"),
            ORIGIN_SUMMARY_FIELDS,
            label="source inventory origin summary",
        )
        if type(manifest.get("variant_source_counts")) is not list:
            _fail("origin variant source counts must be a list")
        for row in manifest["variant_source_counts"]:
            _require_exact_fields(
                row,
                ORIGIN_VARIANT_COUNT_FIELDS,
                label="origin variant source-count row",
            )
        _require_canonical_equal(
            manifest["variant_source_counts"],
            _expected_origin_variant_counts(persona_id, origin),
            label=f"origin variant source counts {persona_id}/{origin}",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        origin_by_key[(persona_id, origin)] = manifest
        origin_raw_by_key[(persona_id, origin)] = raw
    profile_by_key = {}
    profile_raw_by_key = {}
    for manifest, (persona_id, profile) in zip(profile_manifests, expected_profiles):
        raw = _canonical_bytes(
            manifest,
            label="persona v2 source inventory profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        _reject_prohibited_fields(manifest)
        _require_exact_fields(
            manifest,
            PROFILE_TOP_LEVEL_FIELDS,
            label="source inventory profile manifest",
        )
        _validate_common_envelope(
            manifest,
            kind=PROFILE_ARTIFACT_KIND,
            schema=PROFILE_ARTIFACT_SCHEMA,
            label="source inventory profile manifest",
        )
        if manifest.get("persona_id") != persona_id or manifest.get("profile") != profile:
            _fail("profile manifests are not in canonical persona/profile order")
        _require_canonical_equal(
            manifest["canonical_limits"],
            PROFILE_CANONICAL_LIMITS,
            label=f"profile canonical limits {persona_id}/{profile}",
        )
        _require_canonical_equal(
            manifest["completion_claims"],
            _profile_completion_claims(profile),
            label=f"profile completion claims {persona_id}/{profile}",
        )
        _require_canonical_equal(
            manifest["completion_scope"],
            PROFILE_COMPLETION_SCOPE,
            label=f"profile completion scope {persona_id}/{profile}",
        )
        _require_canonical_equal(
            manifest["dependency_direction_contract"],
            PROFILE_DEPENDENCY_CONTRACT,
            label=f"profile dependency-direction contract {persona_id}/{profile}",
        )
        _require_canonical_equal(
            manifest["remaining_blockers"],
            ORIGIN_REMAINING_BLOCKERS,
            label=f"profile blocker ledger {persona_id}/{profile}",
        )
        _validate_input_bindings(
            manifest,
            [_reservation_inputs()["reservation_suite_binding"]],
            ["persona-v2-overlay-reservation-suite"],
            label=f"source inventory profile {persona_id}/{profile}",
        )
        _require_exact_fields(
            manifest.get("summary"),
            PROFILE_SUMMARY_FIELDS,
            label="source inventory profile summary",
        )
        if type(manifest.get("variant_source_counts")) is not list:
            _fail("profile variant source counts must be a list")
        for row in manifest["variant_source_counts"]:
            _require_exact_fields(
                row,
                PROFILE_VARIANT_COUNT_FIELDS,
                label="profile variant source-count row",
            )
        _require_canonical_equal(
            manifest["variant_source_counts"],
            _expected_profile_variant_counts(persona_id, profile),
            label=f"profile variant source counts {persona_id}/{profile}",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        profile_by_key[(persona_id, profile)] = manifest
        profile_raw_by_key[(persona_id, profile)] = raw

    _validate_profile_composition(
        profile_by_key,
        profile_raw_by_key,
        origin_by_key,
        origin_raw_by_key,
    )
    _validate_suite_manifest_bindings(
        suite,
        origin_manifests,
        origin_raw_by_key,
        profile_manifests,
        profile_raw_by_key,
    )

    # Strict manifest/suite contracts are added after the producer artifact is
    # available.  Keeping the full row/body proof here avoids any dependency on
    # producer regeneration and fixes the streaming interface independently.
    total_rows = 0
    total_shards = 0
    total_body_bytes = 0
    suite_roles = {role: 0 for role in GATE_ROLE_ORDER}
    suite_variants = {}
    origin_metrics = {}
    persona_shard_body_bytes = {
        persona_id: 0 for persona_id in envelope.PERSONA_IDS
    }
    maximum_shard_body_bytes = 0
    maximum_row_bytes = 0
    overlay_keys = set()
    anchor_keys = set()
    overlay_role_counts = {role: 0 for role in GATE_ROLE_ORDER}
    anchor_role_counts = {role: 0 for role in GATE_ROLE_ORDER}
    for persona_id, origin in expected_origins:
        manifest = origin_by_key[(persona_id, origin)]
        descriptors = manifest.get("shard_descriptors")
        expected_layout = _expected_layout_shards(persona_id, origin)
        if type(descriptors) is not list or len(descriptors) != len(expected_layout):
            _fail(f"origin manifest shard descriptor coverage drifted: {persona_id}/{origin}")
        requirements = _overlay_requirements(persona_id, origin)
        for intent_key, (_, role, kinds) in requirements.items():
            if "overlay" in kinds:
                overlay_keys.add(intent_key)
                overlay_role_counts[role] += 1
            if "anchor" in kinds:
                anchor_keys.add(intent_key)
                anchor_role_counts[role] += 1
        seen_requirements = set()
        origin_row_count = 0
        origin_body_bytes = 0
        origin_maximum_row_bytes = 0
        origin_maximum_shard_bytes = 0
        origin_roles = {role: 0 for role in GATE_ROLE_ORDER}
        origin_variants = {}
        for descriptor, layout_shard in zip(descriptors, expected_layout):
            result = _load_and_validate_shard(
                descriptor, layout_shard, shard_body_provider, requirements
            )
            total_rows += result["row_count"]
            total_shards += 1
            total_body_bytes += result["body_bytes"]
            origin_row_count += result["row_count"]
            origin_body_bytes += result["body_bytes"]
            persona_shard_body_bytes[persona_id] += result["body_bytes"]
            origin_maximum_row_bytes = max(
                origin_maximum_row_bytes,
                result["descriptor"]["max_row_bytes_including_lf"],
            )
            origin_maximum_shard_bytes = max(
                origin_maximum_shard_bytes, result["body_bytes"]
            )
            maximum_row_bytes = max(maximum_row_bytes, origin_maximum_row_bytes)
            maximum_shard_body_bytes = max(
                maximum_shard_body_bytes, origin_maximum_shard_bytes
            )
            seen_requirements.update(result["seen_overlay"])
            for role in GATE_ROLE_ORDER:
                suite_roles[role] += result["role_counts"][role]
                origin_roles[role] += result["role_counts"][role]
            for variant_id, count in result["variant_counts"].items():
                suite_variants[variant_id] = suite_variants.get(variant_id, 0) + count
                origin_variants[variant_id] = (
                    origin_variants.get(variant_id, 0) + count
                )
        if seen_requirements != set(requirements):
            _fail(f"overlay/anchor source references are not total: {persona_id}/{origin}")
        reservation_summary = _reservation_inputs()["reservation_summaries"][(
            persona_id,
            origin,
        )]
        ready_source_count = sum(
            count
            for variant_id, count in origin_variants.items()
            if _upstream_inputs()["ready_by_variant"][variant_id]
        )
        expected_origin_summary = {
            "gate_role_source_counts": origin_roles,
            "implementation_missing_source_count": (
                origin_row_count - ready_source_count
            ),
            "local_feasibility_ready_source_count": ready_source_count,
            "maximum_row_bytes_including_lf": origin_maximum_row_bytes,
            "overlay_referenced_unique_source_intent_count": reservation_summary[
                "overlay_referenced_unique_source_intent_count"
            ],
            "semantic_anchor_slot_count": reservation_summary[
                "semantic_anchor_slot_count"
            ],
            "shard_body_bytes": origin_body_bytes,
            "shard_count": len(descriptors),
            "source_intent_count": origin_row_count,
            "unreserved_source_intent_count": reservation_summary[
                "unreserved_source_intent_count"
            ],
            "variant_with_sources_count": len(origin_variants),
        }
        _require_canonical_equal(
            manifest["summary"],
            expected_origin_summary,
            label=f"origin summary {persona_id}/{origin}",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        origin_metrics[(persona_id, origin)] = {
            "body_bytes": origin_body_bytes,
            "maximum_row_bytes": origin_maximum_row_bytes,
            "maximum_shard_bytes": origin_maximum_shard_bytes,
            "role_counts": origin_roles,
            "row_count": origin_row_count,
            "shard_count": len(descriptors),
            "variant_counts": origin_variants,
        }

    if (
        len(overlay_keys) != EXPECTED_OVERLAY_REFERENCE_COUNT
        or len(anchor_keys) != EXPECTED_SEMANTIC_ANCHOR_COUNT
        or overlay_keys & anchor_keys
        or overlay_role_counts != EXPECTED_OVERLAY_ROLE_COUNTS
        or anchor_role_counts
        != {
            "contract_contributor": EXPECTED_SEMANTIC_ANCHOR_COUNT,
            "incidental_searchable": 0,
            "raw_only": 0,
        }
    ):
        _fail("overlay reference, semantic-anchor, or role marginals drifted")

    if (
        total_rows != EXPECTED_FULL_ROW_COUNT
        or total_shards != EXPECTED_SHARD_COUNT
        or total_body_bytes <= 0
    ):
        _fail("suite source/shard/body cardinality drifted")
    _require_canonical_equal(
        suite_roles,
        _upstream_inputs()["layout"]["suite_gate_role_source_counts"]["full"],
        label="suite gate-role marginals",
    )
    expected_variant_counts = {
        row["variant_id"]: row["full_count"]
        for row in _upstream_inputs()["variants"]["persona_variant_marginals"]
    }
    # The catalog has one marginal per persona/variant, so aggregate explicitly.
    expected_variant_counts = {}
    for row in _upstream_inputs()["variants"]["persona_variant_marginals"]:
        expected_variant_counts[row["variant_id"]] = (
            expected_variant_counts.get(row["variant_id"], 0) + row["full_count"]
        )
    _require_canonical_equal(
        suite_variants,
        {key: value for key, value in expected_variant_counts.items() if value > 0},
        label="suite variant marginals and hard-zero exclusions",
    )

    for persona_id in envelope.PERSONA_IDS:
        pilot_metrics = origin_metrics[(persona_id, "pilot")]
        residual_metrics = origin_metrics[(persona_id, "full-residual")]
        for profile in PROFILE_ORDER:
            manifest = profile_by_key[(persona_id, profile)]
            metrics = (
                [pilot_metrics]
                if profile == "pilot"
                else [pilot_metrics, residual_metrics]
            )
            role_counts = {
                role: sum(row["role_counts"][role] for row in metrics)
                for role in GATE_ROLE_ORDER
            }
            variant_counts = {}
            for row in metrics:
                for variant_id, count in row["variant_counts"].items():
                    variant_counts[variant_id] = (
                        variant_counts.get(variant_id, 0) + count
                    )
            expected_profile_summary = {
                "full_residual_origin_manifest_count": int(profile == "full"),
                "gate_role_source_counts": role_counts,
                "maximum_row_bytes_including_lf": max(
                    row["maximum_row_bytes"] for row in metrics
                ),
                "origin_manifest_count": len(metrics),
                "pilot_origin_manifest_count": 1,
                "reused_pilot_shard_body_bytes": (
                    pilot_metrics["body_bytes"] if profile == "full" else 0
                ),
                "reused_pilot_shard_count": (
                    pilot_metrics["shard_count"] if profile == "full" else 0
                ),
                "reused_pilot_source_intent_count": (
                    pilot_metrics["row_count"] if profile == "full" else 0
                ),
                "shard_body_bytes": sum(row["body_bytes"] for row in metrics),
                "shard_count": sum(row["shard_count"] for row in metrics),
                "source_intent_count": sum(row["row_count"] for row in metrics),
                "variant_with_sources_count": len(variant_counts),
            }
            _require_canonical_equal(
                manifest["summary"],
                expected_profile_summary,
                label=f"profile summary {persona_id}/{profile}",
                max_bytes=MAX_PROFILE_MANIFEST_BYTES,
            )

    coverage = suite.get("coverage")
    _require_exact_fields(
        coverage, SUITE_COVERAGE_FIELDS, label="source inventory suite coverage"
    )
    expected_coverage = {
        "full_residual_source_intent_count": EXPECTED_RESIDUAL_ROW_COUNT,
        "gate_role_source_counts": _upstream_inputs()["layout"][
            "suite_gate_role_source_counts"
        ]["full"],
        "maximum_origin_manifest_bytes": max(
            len(raw) for raw in origin_raw_by_key.values()
        ),
        "maximum_profile_manifest_bytes": max(
            len(raw) for raw in profile_raw_by_key.values()
        ),
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "maximum_shard_body_bytes": maximum_shard_body_bytes,
        "origin_manifest_count": len(origin_manifests),
        "persona_count": EXPECTED_PERSONA_COUNT,
        "pilot_source_intent_count": EXPECTED_PILOT_ROW_COUNT,
        "profile_manifest_count": len(profile_manifests),
        "shard_body_bytes": total_body_bytes,
        "shard_count": total_shards,
        "source_intent_count": total_rows,
        "variant_identity_count": len(
            _upstream_inputs()["variants"]["variant_rows"]
        ),
        "variant_with_sources_count": len(suite_variants),
    }
    _require_canonical_equal(
        coverage,
        expected_coverage,
        label="suite coverage",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )

    ledgers = suite.get("persona_current_component_byte_ledgers")
    if (
        type(ledgers) is not list
        or [row.get("persona_id") for row in ledgers]
        != list(envelope.PERSONA_IDS)
    ):
        _fail("persona current-component ledgers must be in canonical persona order")
    for ledger in ledgers:
        _require_exact_fields(
            ledger, PERSONA_LEDGER_FIELDS, label="persona current-component ledger"
        )
        persona_id = ledger["persona_id"]
        origin_bytes = sum(
            len(origin_raw_by_key[(persona_id, origin)]) for origin in ORIGIN_ORDER
        )
        profile_bytes = sum(
            len(profile_raw_by_key[(persona_id, profile)])
            for profile in PROFILE_ORDER
        )
        body_bytes = persona_shard_body_bytes[persona_id]
        current_bytes = origin_bytes + profile_bytes + body_bytes
        expected_projection = {
            "current_component_bytes": current_bytes,
            "future_complete_package_cap_proved": False,
            "headroom_bytes": MAX_PERSONA_CURRENT_COMPONENT_BYTES - current_bytes,
            "max_current_component_bytes": MAX_PERSONA_CURRENT_COMPONENT_BYTES,
            "persona_id": persona_id,
            "profile_manifest_bytes": profile_bytes,
            "source_origin_manifest_bytes": origin_bytes,
            "unique_source_shard_body_bytes": body_bytes,
        }
        actual_projection = {
            field: ledger[field] for field in expected_projection
        }
        _require_canonical_equal(
            actual_projection,
            expected_projection,
            label=f"persona current-component byte ledger {persona_id}",
        )
        if current_bytes > MAX_PERSONA_CURRENT_COMPONENT_BYTES:
            _fail(f"persona current-component byte cap exceeded: {persona_id}")
        _require_canonical_equal(
            ledger["included_components"],
            LEDGER_INCLUDED_COMPONENTS,
            label=f"persona byte ledger denominator {persona_id}",
        )
    return True


def _snapshot_artifact(value, *, label, max_bytes):
    raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    return copy.deepcopy(value), raw


def _snapshot_artifact_list(values, *, label, expected_count, max_bytes):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"{label} must be an exact {expected_count}-item list")
    snapshots = []
    raws = []
    for value in values:
        snapshot, raw = _snapshot_artifact(
            value,
            label=label,
            max_bytes=max_bytes,
        )
        snapshots.append(snapshot)
        raws.append(raw)
    return snapshots, tuple(raws)


def _reauth_artifact(value, opening_raw, *, label, max_bytes):
    try:
        current_raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    except PersonaV2SourceInventoryPackageValidationError:
        _fail(f"caller-owned {label} changed during provider callback")
    if current_raw != opening_raw:
        _fail(f"caller-owned {label} changed during provider callback")


def _reauth_artifact_list(
    values, opening_raws, *, label, expected_count, max_bytes
):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"caller-owned {label} changed during provider callback")
    for value, opening_raw in zip(values, opening_raws, strict=True):
        _reauth_artifact(
            value,
            opening_raw,
            label=label,
            max_bytes=max_bytes,
        )


def validate_source_inventory_package(
    suite, origin_manifests, profile_manifests, shard_body_provider
):
    """Validate detached opening metadata and reject callback-time mutation."""

    suite_snapshot, suite_raw = _snapshot_artifact(
        suite,
        label="persona v2 source inventory suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    origin_snapshots, origin_raws = _snapshot_artifact_list(
        origin_manifests,
        label="persona v2 source inventory origin manifest",
        expected_count=40,
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    profile_snapshots, profile_raws = _snapshot_artifact_list(
        profile_manifests,
        label="persona v2 source inventory profile manifest",
        expected_count=40,
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
    )
    try:
        return _validate_source_inventory_package_snapshot(
            suite_snapshot,
            origin_snapshots,
            profile_snapshots,
            shard_body_provider,
        )
    finally:
        _reauth_artifact(
            suite,
            suite_raw,
            label="source inventory suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            origin_manifests,
            origin_raws,
            label="source inventory origin manifests",
            expected_count=40,
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            profile_manifests,
            profile_raws,
            label="source inventory profile manifests",
            expected_count=40,
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )


__all__ = [
    "PersonaV2SourceInventoryPackageValidationError",
    "validate_source_inventory_package",
]
