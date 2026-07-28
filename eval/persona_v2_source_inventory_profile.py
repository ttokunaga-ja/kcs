"""Exact all-variant inventory profiles for persona-PC v2 source slots.

The current feasibility catalog has ten locally renderable contributor
variants, while the complete physical inventory requires seventy-one variants.
This artifact gives every variant a unique, non-authorizing inventory-profile
foreign key without pretending that a formal source recipe exists.  It is a
structural bridge from the variant catalog to the future 203,000 source rows.

Inventory identity and execution readiness are intentionally separate:

* all 71 variant/profile identities and projected format metadata are exact;
* all formal source-recipe slots remain reserved but unbound;
* ten variants expose only local bounded-feasibility evidence;
* sixty-one variants remain implementation-missing;
* every G0, solver, renderer-execution, filesystem, write, KIO, and history
  authority remains false.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_source_profile_catalog as feasibility_catalog
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_source_profile_catalog as feasibility_catalog
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kio.persona.pc-source-inventory-profile-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-source-inventory-profile-catalog"

MAX_CATALOG_BYTES = 256 * 1024
EXPECTED_PROFILE_COUNT = 71
EXPECTED_LOCAL_READY_COUNT = 10
EXPECTED_IMPLEMENTATION_MISSING_COUNT = 61

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
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
        "kio_execution_available",
        "source_recipe_inventory_complete",
    }
)


class PersonaV2SourceInventoryProfileError(ValueError):
    """Raised when the all-variant inventory-profile contract is violated."""


def inventory_profile_id(variant_id):
    if type(variant_id) is not str or not variant_id:
        raise PersonaV2SourceInventoryProfileError(
            "variant ID must be a non-empty string"
        )
    return f"persona-v2-inventory-profile-{variant_id}-v2"


def source_recipe_slot_id(variant_id):
    if type(variant_id) is not str or not variant_id:
        raise PersonaV2SourceInventoryProfileError(
            "variant ID must be a non-empty string"
        )
    return f"persona-v2-source-recipe-slot-{variant_id}-v2"


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        raise PersonaV2SourceInventoryProfileError(f"{label} must remain non-G0")
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        raise PersonaV2SourceInventoryProfileError(
            f"{label} authority must be the exact all-false schema"
        )


def _require_upstream_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        raise PersonaV2SourceInventoryProfileError(f"{label} must remain non-G0")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        raise PersonaV2SourceInventoryProfileError(
            f"{label} must expose non-empty all-false authority"
        )


def _artifact_binding(name, dependency_role, value, *, validate, canonical, digest):
    validate(value)
    _require_upstream_negative_authority(value, label=name)
    if (
        value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version")
        != envelope.FIXTURE_SCHEMA_VERSION
    ):
        raise PersonaV2SourceInventoryProfileError(
            f"{name} fixture identity drifted"
        )
    raw = canonical(value)
    actual = digest(value)
    if actual != hashlib.sha256(raw).hexdigest():
        raise PersonaV2SourceInventoryProfileError(
            f"{name} returned a non-canonical digest"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name,
        "sha256": actual,
    }


def _profile_row(variant_row, feasibility_row):
    variant_id = variant_row["variant_id"]
    if feasibility_row["variant_id"] != variant_id:
        raise PersonaV2SourceInventoryProfileError(
            f"variant/feasibility order drifted: {variant_id}"
        )
    exact_metadata = (
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
    )
    for field in exact_metadata:
        if feasibility_row[field] != variant_row[field]:
            raise PersonaV2SourceInventoryProfileError(
                f"feasibility metadata drifted: {variant_id}/{field}"
            )
    local_ready = feasibility_row["bounded_feasibility"][
        "vertical_slice_ready"
    ]
    if type(local_ready) is not bool:
        raise PersonaV2SourceInventoryProfileError(
            f"local readiness is not an exact boolean: {variant_id}"
        )
    return {
        "bounded_feasibility": {
            "byte_and_complexity_parameters_complete": feasibility_row[
                "bounded_feasibility"
            ]["byte_and_complexity_parameters_complete"],
            "independent_validator_implemented": feasibility_row[
                "bounded_feasibility"
            ]["independent_validator_implemented"],
            "local_vertical_slice_ready": local_ready,
            "renderer_implemented": feasibility_row["bounded_feasibility"][
                "renderer_implemented"
            ],
            "status": (
                "ready-local-only-formal-recipe-unbound"
                if local_ready
                else "blocked-implementation-missing"
            ),
        },
        "compound_suffix_parts": copy.deepcopy(
            variant_row["compound_suffix_parts"]
        ),
        "content_media_type": variant_row["content_media_type"],
        "execution_eligibility_status": "blocked",
        "expected_kio_path_media_type": variant_row[
            "expected_kio_path_media_type"
        ],
        "expected_offline_disposition": variant_row[
            "expected_offline_disposition"
        ],
        "family": variant_row["family"],
        "feasibility_rule_id": variant_row["complexity_contract"][
            "feasibility_rule_id"
        ],
        "filename_extension": variant_row["filename_extension"],
        "gate_role": variant_row["gate_role"],
        "safety_profile_id": variant_row["safety_profile_id"],
        "source_profile_id": inventory_profile_id(variant_id),
        "source_recipe": {
            "binding_status": "reserved-unbound",
            "parameters_complete": False,
            "profile_id": "not-bound",
            "slot_id": source_recipe_slot_id(variant_id),
        },
        "upstream_planned_renderer": {
            "implementation_status": variant_row["renderer"][
                "implementation_status"
            ],
            "renderer_id": variant_row["renderer"]["renderer_id"],
            "renderer_schema_version": variant_row["renderer"][
                "renderer_schema_version"
            ],
        },
        "upstream_planned_validator": {
            "implementation_status": variant_row["validator"][
                "implementation_status"
            ],
            "validator_id": variant_row["validator"]["validator_id"],
            "validator_schema_version": variant_row["validator"][
                "validator_schema_version"
            ],
        },
        "variant_binding_status": "bound-exact",
        "variant_id": variant_id,
    }


def _require_invariants(value, variant_value, feasibility_value):
    _require_negative_authority(value, label="source inventory profile catalog")
    rows = value.get("source_profile_rows")
    variant_rows = variant_value["variant_rows"]
    feasibility_rows = feasibility_value["source_profile_rows"]
    if (
        type(rows) is not list
        or len(rows) != EXPECTED_PROFILE_COUNT
        or len(variant_rows) != EXPECTED_PROFILE_COUNT
        or len(feasibility_rows) != EXPECTED_PROFILE_COUNT
    ):
        raise PersonaV2SourceInventoryProfileError(
            "inventory profile cardinality drifted"
        )
    expected = [
        _profile_row(variant_row, feasibility_row)
        for variant_row, feasibility_row in zip(variant_rows, feasibility_rows)
    ]
    if rows != expected:
        raise PersonaV2SourceInventoryProfileError(
            "inventory profile metadata or order drifted"
        )
    profile_ids = [row["source_profile_id"] for row in rows]
    recipe_slots = [row["source_recipe"]["slot_id"] for row in rows]
    if (
        len(profile_ids) != len(set(profile_ids))
        or len(recipe_slots) != len(set(recipe_slots))
    ):
        raise PersonaV2SourceInventoryProfileError(
            "inventory profile or recipe-slot IDs are not unique"
        )
    ready = sum(
        row["bounded_feasibility"]["local_vertical_slice_ready"] for row in rows
    )
    if (
        ready != EXPECTED_LOCAL_READY_COUNT
        or len(rows) - ready != EXPECTED_IMPLEMENTATION_MISSING_COUNT
    ):
        raise PersonaV2SourceInventoryProfileError(
            "local feasibility readiness counts drifted"
        )
    if any(
        row["source_recipe"]["binding_status"] != "reserved-unbound"
        or row["source_recipe"]["profile_id"] != "not-bound"
        or row["source_recipe"]["parameters_complete"] is not False
        or row["execution_eligibility_status"] != "blocked"
        for row in rows
    ):
        raise PersonaV2SourceInventoryProfileError(
            "inventory profile escalated recipe or execution readiness"
        )


@functools.lru_cache(maxsize=1)
def _canonical_catalog():
    variant_value = variant_catalog.build_variant_catalog()
    feasibility_value = feasibility_catalog.build_source_profile_catalog()
    variant_catalog.validate_variant_catalog(variant_value)
    feasibility_catalog.validate_source_profile_catalog(feasibility_value)
    rows = [
        _profile_row(variant_row, feasibility_row)
        for variant_row, feasibility_row in zip(
            variant_value["variant_rows"],
            feasibility_value["source_profile_rows"],
        )
    ]
    ready = sum(
        row["bounded_feasibility"]["local_vertical_slice_ready"] for row in rows
    )
    marginals = variant_value["persona_variant_marginals"]
    ready_ids = {
        row["variant_id"]
        for row in rows
        if row["bounded_feasibility"]["local_vertical_slice_ready"]
    }
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "exact_profile_rows": EXPECTED_PROFILE_COUNT,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_variant_inventory_profiles_present": True,
            "exact_variant_metadata_projection_complete": True,
            "formal_source_recipe_profiles_bound": False,
            "inventory_profile_catalog_complete": True,
            "physical_source_materialization_complete": False,
            "profile_reference_namespace_unique": True,
            "renderer_validator_implementation_complete": False,
            "source_level_feasibility_complete": False,
        },
        "completion_scope": (
            "all-71-variant-inventory-profile-identities-and-metadata-only-"
            "no-formal-recipe-no-execution-no-g0"
        ),
        "coverage": {
            "active_persona_variant_rows": sum(
                row["full_count"] > 0 for row in marginals
            ),
            "declared_persona_variant_rows": len(marginals),
            "implementation_missing_profile_count": len(rows) - ready,
            "local_ready_profile_count": ready,
            "local_ready_source_counts": {
                "full": sum(
                    row["full_count"]
                    for row in marginals
                    if row["variant_id"] in ready_ids
                ),
                "full-residual": sum(
                    row["full_minus_pilot_count"]
                    for row in marginals
                    if row["variant_id"] in ready_ids
                ),
                "pilot": sum(
                    row["pilot_count"]
                    for row in marginals
                    if row["variant_id"] in ready_ids
                ),
            },
            "profile_count": len(rows),
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [
            "persona-v2-variant-catalog",
            "persona-v2-source-profile-feasibility-catalog",
        ],
        "input_bindings": [
            _artifact_binding(
                "persona-v2-variant-catalog",
                "all-variant-format-and-gate-role-identity",
                variant_value,
                validate=variant_catalog.validate_variant_catalog,
                canonical=variant_catalog.canonical_json_bytes,
                digest=variant_catalog.variant_catalog_sha256,
            ),
            _artifact_binding(
                "persona-v2-source-profile-feasibility-catalog",
                "local-feasibility-status-only",
                feasibility_value,
                validate=feasibility_catalog.validate_source_profile_catalog,
                canonical=feasibility_catalog.canonical_json_bytes,
                digest=feasibility_catalog.source_profile_catalog_sha256,
            ),
        ],
        "orders": {
            "source_profile_rows": "exact-upstream-variant-catalog-order"
        },
        "remaining_blockers": [
            "all-formal-source-recipe-profiles-unbound",
            "sixty-one-renderer-validator-or-formula-implementations-missing",
            "semantic-content-and-fact-membership-catalogs-not-bound",
            "source-level-allocation-solution-and-proof-not-present",
            "physical-source-render-write-and-kio-observation-not-present",
            "formal-persona-package-cap-not-proved",
        ],
        "source_profile_rows": rows,
    }
    _require_invariants(value, variant_value, feasibility_value)
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source inventory profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryProfileError(str(error)) from None
    return value


def build_source_inventory_profile_catalog():
    """Return a detached 71-row non-authorizing inventory-profile catalog."""

    return copy.deepcopy(_canonical_catalog())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source inventory profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryProfileError(str(error)) from None


def validate_source_inventory_profile_catalog(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_source_inventory_profile_catalog,
            label="persona v2 source inventory profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryProfileError(str(error)) from None
    variant_value = variant_catalog.build_variant_catalog()
    feasibility_value = feasibility_catalog.build_source_profile_catalog()
    _require_invariants(value, variant_value, feasibility_value)
    return True


def source_inventory_profile_catalog_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_source_inventory_profile_catalog,
            label="persona v2 source inventory profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryProfileError(str(error)) from None


def require_formal_source_recipe_profiles():
    raise PersonaV2SourceInventoryProfileError(
        "all 71 inventory-profile identities are exact, but formal source "
        "recipes, sixty-one implementations, source-level feasibility, and "
        "every execution or G0 authority remain absent"
    )
