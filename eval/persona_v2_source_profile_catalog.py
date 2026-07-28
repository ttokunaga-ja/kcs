"""Non-authorizing source-profile completion sidecar for persona-PC v2.

All 71 frozen variants are represented.  The nine ID-free local-text variants
and the separate ID-free text-layer PDF variant are marked ready in this
vertical slice.  Readiness means bounded local feasibility only: it does not
create source intents, final identifiers, files, KIO chunks, multilingual PDF
coverage, or G0 authority.

Dependency direction is one-way::

    frozen planning chain -> variant catalog -> this source-profile sidecar
    text renderer contract ------------------^             ^
    standalone validator contract -------------------------|

Neither implementation contract imports this sidecar or any planning input.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
    from . import persona_v2_pdf_text_renderer as pdf_text_renderer
    from . import persona_v2_pdf_text_validator as pdf_text_validator
    from . import persona_v2_text_renderer as text_renderer
    from . import persona_v2_text_validator as text_validator
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings
    import persona_v2_pdf_text_renderer as pdf_text_renderer
    import persona_v2_pdf_text_validator as pdf_text_validator
    import persona_v2_text_renderer as text_renderer
    import persona_v2_text_validator as text_validator
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kio.persona.pc-source-profile-catalog/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-source-profile-catalog"
MAX_CATALOG_BYTES = 256 * 1024

READY_VARIANTS = frozenset(text_renderer.READY_VARIANTS) | frozenset(
    {pdf_text_renderer.VARIANT_ID}
)
EXPECTED_VARIANT_COUNT = 71
EXPECTED_READY_VARIANT_COUNT = 10


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


def _dependency_bindings(
    variant_value,
    text_renderer_value,
    text_validator_value,
    pdf_renderer_value,
    pdf_validator_value,
):
    return {
        "binding_order": [
            "envelope",
            "topology",
            "joint-problem",
            "joint-solver-policy",
            "variant-catalog",
            "id-free-text-renderer",
            "id-free-text-validator",
            "id-free-pdf-text-renderer",
            "id-free-pdf-text-validator",
        ],
        "id_free_text_renderer": _artifact_binding(
            "id-free-text-renderer",
            text_renderer_value,
            validate=text_renderer.validate_renderer_contract,
            canonical=text_renderer.canonical_json_bytes,
            digest=text_renderer.renderer_contract_sha256,
        ),
        "id_free_text_validator": _artifact_binding(
            "id-free-text-validator",
            text_validator_value,
            validate=text_validator.validate_validator_contract,
            canonical=text_validator.canonical_json_bytes,
            digest=text_validator.validator_contract_sha256,
        ),
        "id_free_pdf_text_renderer": _artifact_binding(
            "id-free-pdf-text-renderer",
            pdf_renderer_value,
            validate=pdf_text_renderer.validate_renderer_contract,
            canonical=pdf_text_renderer.canonical_json_bytes,
            digest=pdf_text_renderer.renderer_contract_sha256,
        ),
        "id_free_pdf_text_validator": _artifact_binding(
            "id-free-pdf-text-validator",
            pdf_validator_value,
            validate=pdf_text_validator.validate_validator_contract,
            canonical=pdf_text_validator.canonical_json_bytes,
            digest=pdf_text_validator.validator_contract_sha256,
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


def _implementation_rows(contract, *, role, expected_variants):
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
    if set(by_variant) != set(expected_variants):
        raise PersonaV2SourceProfileCatalogError(
            f"{role} contract readiness set drifted"
        )
    return by_variant


def _require_renderer_validator_agreement(renderer_row, validator_row):
    keys = (
        "complexity",
        "content_media_type",
        "expected_kio_path_media_type",
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


def _source_profile_row(
    upstream_row,
    renderer_by_variant,
    validator_by_variant,
    renderer_ids,
    validator_ids,
):
    variant_id = upstream_row["variant_id"]
    ready = variant_id in READY_VARIANTS
    row = {
        "bounded_feasibility": {
            "byte_and_complexity_parameters_complete": ready,
            "independent_validator_implemented": ready,
            "renderer_implemented": ready,
            "status": (
                (
                    "id-free-pdf-text-vertical-slice-ready"
                    if variant_id == pdf_text_renderer.VARIANT_ID
                    else "id-free-text-vertical-slice-ready"
                )
                if ready
                else "renderer-validator-or-formula-not-implemented"
            ),
            "vertical_slice_ready": ready,
        },
        "bounded_feasibility_profile_id": "not-bound",
        "content_media_type": upstream_row["content_media_type"],
        "expected_kio_path_media_type": upstream_row[
            "expected_kio_path_media_type"
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
        "expected_kio_path_media_type",
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
        "renderer_id": renderer_ids[variant_id],
        "validator_id": validator_ids[variant_id],
        "validator_profile_id": validator_row["validator_profile_id"],
    }
    row["render_template"] = renderer_row["render_template"]
    slice_name = (
        "id-free-pdf-text"
        if variant_id == pdf_text_renderer.VARIANT_ID
        else "id-free-text"
    )
    row["bounded_feasibility_profile_id"] = (
        f"persona-v2-{variant_id}-{slice_name}-feasibility-v2"
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


@functools.lru_cache(maxsize=1)
def _canonical_catalog_value():
    variant_value = variant_catalog.build_variant_catalog()
    text_renderer_value = text_renderer.build_renderer_contract()
    text_validator_value = text_validator.build_validator_contract()
    pdf_renderer_value = pdf_text_renderer.build_renderer_contract()
    pdf_validator_value = pdf_text_validator.build_validator_contract()
    variant_catalog.validate_variant_catalog(variant_value)
    text_renderer.validate_renderer_contract(text_renderer_value)
    text_validator.validate_validator_contract(text_validator_value)
    pdf_text_renderer.validate_renderer_contract(pdf_renderer_value)
    pdf_text_validator.validate_validator_contract(pdf_validator_value)

    text_renderer_rows = _implementation_rows(
        text_renderer_value,
        role="text renderer",
        expected_variants=text_renderer.READY_VARIANTS,
    )
    pdf_renderer_rows = _implementation_rows(
        pdf_renderer_value,
        role="PDF-text renderer",
        expected_variants=(pdf_text_renderer.VARIANT_ID,),
    )
    text_validator_rows = _implementation_rows(
        text_validator_value,
        role="text validator",
        expected_variants=text_validator.READY_VARIANTS,
    )
    pdf_validator_rows = _implementation_rows(
        pdf_validator_value,
        role="PDF-text validator",
        expected_variants=(pdf_text_validator.VARIANT_ID,),
    )
    if set(text_renderer_rows).intersection(pdf_renderer_rows) or set(
        text_validator_rows
    ).intersection(pdf_validator_rows):
        raise PersonaV2SourceProfileCatalogError(
            "renderer or validator readiness ownership overlaps"
        )
    renderer_by_variant = {**text_renderer_rows, **pdf_renderer_rows}
    validator_by_variant = {**text_validator_rows, **pdf_validator_rows}
    renderer_ids = {
        **{
            variant_id: text_renderer.RENDERER_ID
            for variant_id in text_renderer.READY_VARIANTS
        },
        pdf_text_renderer.VARIANT_ID: pdf_text_renderer.RENDERER_ID,
    }
    validator_ids = {
        **{
            variant_id: text_validator.VALIDATOR_ID
            for variant_id in text_validator.READY_VARIANTS
        },
        pdf_text_validator.VARIANT_ID: pdf_text_validator.VALIDATOR_ID,
    }
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
        _source_profile_row(
            row,
            renderer_by_variant,
            validator_by_variant,
            renderer_ids,
            validator_ids,
        )
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
            "kio_execution_attested": False,
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
            variant_value,
            text_renderer_value,
            text_validator_value,
            pdf_renderer_value,
            pdf_validator_value,
        ),
        "orders": {
            "profile_rows": "exact-upstream-variant-catalog-order",
            "ready_variants": sorted(
                READY_VARIANTS, key=lambda value: value.encode("ascii")
            ),
        },
        "remaining_blockers": [
            "sixty-one-incidental-or-raw-variant-profiles-not-ready",
            "pdf-text-multilingual-and-kio-chunk-attestation-not-proved",
            "semantic-content-recipe-inputs-not-bound",
            "source-intent-identities-not-allocated-or-hashed",
            "production-kio-chunk-count-not-attested",
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
    """Return a detached 71-row catalog with exactly ten ready profiles."""

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
        "ten contributor feasibility profiles are ready, but 61 incidental/raw "
        "variants, multilingual PDF coverage, semantic recipes, source intents, "
        "KIO attestation, and capacity gates remain"
    )
