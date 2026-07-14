"""Non-authorizing source-profile completion sidecar for persona-PC v2.

All 71 frozen variants are represented.  Only the nine ID-free text
contributor variants implemented by :mod:`persona_v2_text_renderer` and checked
by the separate :mod:`persona_v2_text_validator` are marked ready in this
vertical slice.  Readiness means bounded local feasibility only: it does not
create source intents, final identifiers, files, KCS chunks, or G0 authority.

Dependency direction is one-way::

    frozen planning chain -> variant catalog -> this source-profile sidecar
    text renderer contract ------------------^             ^
    standalone validator contract -------------------------|

Neither implementation contract imports this sidecar or any planning input.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
    from . import persona_v2_text_renderer as text_renderer
    from . import persona_v2_text_validator as text_validator
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings
    import persona_v2_text_renderer as text_renderer
    import persona_v2_text_validator as text_validator
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kcs.persona.pc-source-profile-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-source-profile-catalog"
MAX_CATALOG_BYTES = 256 * 1024

READY_VARIANTS = frozenset(text_renderer.READY_VARIANTS)
EXPECTED_VARIANT_COUNT = 71
EXPECTED_READY_VARIANT_COUNT = 9


class PersonaV2SourceProfileCatalogError(ValueError):
    """Raised when the source-profile sidecar or one dependency drifts."""


def _artifact_binding(name, value, *, validate, canonical, digest):
    validate(value)
    raw = canonical(value)
    actual_digest = digest(value)
    if (
        type(actual_digest) is not str
        or len(actual_digest) != 64
        or any(character not in "0123456789abcdef" for character in actual_digest)
        or hashlib.sha256(raw).hexdigest() != actual_digest
    ):
        raise PersonaV2SourceProfileCatalogError(
            f"{name} returned a non-canonical digest"
        )
    authority = value.get("authority")
    if type(authority) is not dict or not authority:
        raise PersonaV2SourceProfileCatalogError(
            f"{name} must expose top-level negative authority"
        )
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        raise PersonaV2SourceProfileCatalogError(
            f"{name} must remain non-authorizing"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "name": name,
        "sha256": actual_digest,
    }


def _dependency_bindings(variant_value, renderer_value, validator_value):
    return {
        "binding_order": [
            "envelope",
            "topology",
            "joint-problem",
            "joint-solver-policy",
            "variant-catalog",
            "id-free-text-renderer",
            "id-free-text-validator",
        ],
        "id_free_text_renderer": _artifact_binding(
            "id-free-text-renderer",
            renderer_value,
            validate=text_renderer.validate_renderer_contract,
            canonical=text_renderer.canonical_json_bytes,
            digest=text_renderer.renderer_contract_sha256,
        ),
        "id_free_text_validator": _artifact_binding(
            "id-free-text-validator",
            validator_value,
            validate=text_validator.validate_validator_contract,
            canonical=text_validator.canonical_json_bytes,
            digest=text_validator.validator_contract_sha256,
        ),
        "planning_chain": input_bindings.build_upstream_bindings(),
        "variant_catalog": _artifact_binding(
            "variant-catalog",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
            digest=variant_catalog.variant_catalog_sha256,
        ),
    }


def _implementation_rows(contract, *, role):
    rows = contract.get("variant_rows")
    if type(rows) is not list:
        raise PersonaV2SourceProfileCatalogError(
            f"{role} contract must contain exact variant rows"
        )
    by_variant = {}
    for row in rows:
        if type(row) is not dict or type(row.get("variant_id")) is not str:
            raise PersonaV2SourceProfileCatalogError(
                f"{role} contract contains a malformed variant row"
            )
        variant_id = row["variant_id"]
        if variant_id in by_variant:
            raise PersonaV2SourceProfileCatalogError(
                f"{role} contract contains duplicate variant {variant_id}"
            )
        by_variant[variant_id] = row
    if set(by_variant) != READY_VARIANTS:
        raise PersonaV2SourceProfileCatalogError(
            f"{role} contract readiness set drifted"
        )
    return by_variant


def _require_renderer_validator_agreement(renderer_row, validator_row):
    keys = (
        "complexity",
        "content_media_type",
        "expected_kcs_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
        "raw_byte_formula",
        "render_template",
        "variant_id",
    )
    renderer_projection = {key: renderer_row[key] for key in keys}
    validator_projection = {key: validator_row[key] for key in keys}
    if renderer_projection != validator_projection:
        raise PersonaV2SourceProfileCatalogError(
            f"renderer/validator contract mismatch for {renderer_row['variant_id']}"
        )


def _source_profile_row(upstream_row, renderer_by_variant, validator_by_variant):
    variant_id = upstream_row["variant_id"]
    ready = variant_id in READY_VARIANTS
    row = {
        "bounded_feasibility": {
            "byte_and_complexity_parameters_complete": ready,
            "independent_validator_implemented": ready,
            "renderer_implemented": ready,
            "status": (
                "id-free-text-vertical-slice-ready"
                if ready
                else "renderer-validator-or-formula-not-implemented"
            ),
            "vertical_slice_ready": ready,
        },
        "bounded_feasibility_profile_id": "not-bound",
        "content_media_type": upstream_row["content_media_type"],
        "expected_kcs_path_media_type": upstream_row[
            "expected_kcs_path_media_type"
        ],
        "expected_offline_disposition": upstream_row[
            "expected_offline_disposition"
        ],
        "family": upstream_row["family"],
        "filename_extension": upstream_row["filename_extension"],
        "gate_role": upstream_row["gate_role"],
        "source_recipe_profile_id": "not-bound",
        "upstream_planned_renderer_id": upstream_row["renderer"]["renderer_id"],
        "upstream_planned_validator_id": upstream_row["validator"]["validator_id"],
        "variant_id": variant_id,
    }
    if not ready:
        row["byte_formula"] = {"parameters_complete": False}
        row["complexity_contract"] = {"parameters_complete": False}
        row["implementation_bindings"] = {
            "renderer_id": "not-bound",
            "validator_id": "not-bound",
            "validator_profile_id": "not-bound",
        }
        return row

    renderer_row = renderer_by_variant[variant_id]
    validator_row = validator_by_variant[variant_id]
    _require_renderer_validator_agreement(renderer_row, validator_row)
    exact_metadata = (
        "family",
        "content_media_type",
        "expected_kcs_path_media_type",
        "expected_offline_disposition",
        "filename_extension",
        "gate_role",
    )
    for key in exact_metadata:
        if upstream_row[key] != renderer_row[key]:
            raise PersonaV2SourceProfileCatalogError(
                f"implemented profile metadata differs from variant catalog: "
                f"{variant_id}/{key}"
            )
    row["byte_formula"] = {
        **copy.deepcopy(renderer_row["raw_byte_formula"]),
        "parameters_complete": True,
    }
    row["complexity_contract"] = {
        **copy.deepcopy(renderer_row["complexity"]),
        "parameters_complete": True,
    }
    row["implementation_bindings"] = {
        "renderer_id": text_renderer.RENDERER_ID,
        "validator_id": text_validator.VALIDATOR_ID,
        "validator_profile_id": validator_row["validator_profile_id"],
    }
    row["render_template"] = renderer_row["render_template"]
    row["bounded_feasibility_profile_id"] = (
        f"persona-v2-{variant_id}-id-free-text-feasibility-v2"
    )
    return row


def _coverage(variant_value):
    count_fields = (
        "tiny_smoke_count",
        "pilot_count",
        "full_count",
        "full_minus_pilot_count",
    )
    ready_marginals = [
        row
        for row in variant_value["persona_variant_marginals"]
        if row["variant_id"] in READY_VARIANTS
    ]
    return {
        "all_variant_count": EXPECTED_VARIANT_COUNT,
        "not_ready_variant_count": EXPECTED_VARIANT_COUNT
        - EXPECTED_READY_VARIANT_COUNT,
        "ready_active_persona_variant_rows": sum(
            row["full_count"] > 0 for row in ready_marginals
        ),
        "ready_persona_variant_rows": len(ready_marginals),
        "ready_source_counts": {
            field: sum(row[field] for row in ready_marginals)
            for field in count_fields
        },
        "ready_variant_count": EXPECTED_READY_VARIANT_COUNT,
    }


def _canonical_catalog_value():
    variant_value = variant_catalog.build_variant_catalog()
    renderer_value = text_renderer.build_renderer_contract()
    validator_value = text_validator.build_validator_contract()
    variant_catalog.validate_variant_catalog(variant_value)
    text_renderer.validate_renderer_contract(renderer_value)
    text_validator.validate_validator_contract(validator_value)

    renderer_by_variant = _implementation_rows(
        renderer_value, role="renderer"
    )
    validator_by_variant = _implementation_rows(
        validator_value, role="validator"
    )
    upstream_rows = variant_value["variant_rows"]
    if (
        type(upstream_rows) is not list
        or len(upstream_rows) != EXPECTED_VARIANT_COUNT
        or len({row["variant_id"] for row in upstream_rows})
        != EXPECTED_VARIANT_COUNT
        or set(envelope.VARIANT_CATALOG)
        != {row["variant_id"] for row in upstream_rows}
    ):
        raise PersonaV2SourceProfileCatalogError(
            "upstream 71-variant identity set drifted"
        )
    profile_rows = [
        _source_profile_row(row, renderer_by_variant, validator_by_variant)
        for row in upstream_rows
    ]
    ready_rows = [
        row
        for row in profile_rows
        if row["bounded_feasibility"]["vertical_slice_ready"]
    ]
    if (
        len(ready_rows) != EXPECTED_READY_VARIANT_COUNT
        or {row["variant_id"] for row in ready_rows} != READY_VARIANTS
    ):
        raise PersonaV2SourceProfileCatalogError(
            "source-profile readiness set drifted"
        )
    remaining = [
        row["variant_id"]
        for row in profile_rows
        if not row["bounded_feasibility"]["vertical_slice_ready"]
    ]
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_final_source_identifiers": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "formal_capacity_gate_satisfied": False,
            "kcs_execution_attested": False,
        },
        "canonical_limits": {
            "exact_profile_rows": EXPECTED_VARIANT_COUNT,
            "exact_ready_rows": EXPECTED_READY_VARIANT_COUNT,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "coverage": _coverage(variant_value),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_bindings": _dependency_bindings(
            variant_value, renderer_value, validator_value
        ),
        "orders": {
            "profile_rows": "exact-upstream-variant-catalog-order",
            "ready_variants": list(text_renderer.READY_VARIANTS),
        },
        "remaining_blockers": [
            "sixty-two-variant-renderer-validator-and-formula-profiles-not-ready",
            "semantic-content-recipe-inputs-not-bound",
            "source-intent-identities-not-allocated-or-hashed",
            "production-kcs-chunk-count-not-attested",
            "bounded-framed-external-loader-not-implemented",
            "formal-capacity-gate-not-satisfied",
        ],
        "remaining_variant_ids": remaining,
        "bounded_feasibility_vertical_slice_complete": True,
        "source_profile_catalog_complete": False,
        "source_profile_rows": profile_rows,
        "source_profile_vertical_slice_complete": False,
    }


def build_source_profile_catalog():
    """Return a detached 71-row catalog with exactly nine ready profiles."""

    return copy.deepcopy(_canonical_catalog_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source-profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceProfileCatalogError(str(error)) from None


def validate_source_profile_catalog(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_source_profile_catalog,
            label="persona v2 source-profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceProfileCatalogError(str(error)) from None


def source_profile_catalog_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_source_profile_catalog,
            label="persona v2 source-profile catalog",
            max_bytes=MAX_CATALOG_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceProfileCatalogError(str(error)) from None


def require_complete_source_profile_catalog():
    raise PersonaV2SourceProfileCatalogError(
        "only nine ID-free text contributor profiles are ready; 62 variants, "
        "semantic recipes, source intents, KCS attestation, and capacity gates remain"
    )
