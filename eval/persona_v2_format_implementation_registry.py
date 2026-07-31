"""Frozen all-format implementation registry for persona-PC v2.

This sidecar closes only the renderer/independent-validator implementation
surface.  It deliberately does not rewrite the historical ten-ready/
sixty-one-missing source-profile catalog, bind any formal source recipe or
source instance, or grant execution, filesystem, KIO, history, solver, or G0
authority.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_format_implementation_registry_validator as independent
    from . import persona_v2_incidental_text_renderer as incidental_renderer
    from . import persona_v2_incidental_text_validator as incidental_validator
    from . import persona_v2_pdf_text_renderer as pdf_renderer
    from . import persona_v2_pdf_text_validator as pdf_validator
    from . import persona_v2_raw_document_renderer as raw_document_renderer
    from . import persona_v2_raw_document_validator as raw_document_validator
    from . import persona_v2_raw_domain_renderer as raw_domain_renderer
    from . import persona_v2_raw_domain_validator as raw_domain_validator
    from . import persona_v2_raw_image_media_renderer as raw_image_media_renderer
    from . import persona_v2_raw_image_media_validator as raw_image_media_validator
    from . import persona_v2_raw_tar_gzip_renderer as raw_tar_gzip_renderer
    from . import persona_v2_raw_tar_gzip_validator as raw_tar_gzip_validator
    from . import persona_v2_raw_zip_renderer as raw_zip_renderer
    from . import persona_v2_raw_zip_validator as raw_zip_validator
    from . import persona_v2_source_inventory_profile as inventory_catalog
    from . import persona_v2_source_profile_catalog as historical_catalog
    from . import persona_v2_text_renderer as contributor_renderer
    from . import persona_v2_text_validator as contributor_validator
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_format_implementation_registry_validator as independent
    import persona_v2_incidental_text_renderer as incidental_renderer
    import persona_v2_incidental_text_validator as incidental_validator
    import persona_v2_pdf_text_renderer as pdf_renderer
    import persona_v2_pdf_text_validator as pdf_validator
    import persona_v2_raw_document_renderer as raw_document_renderer
    import persona_v2_raw_document_validator as raw_document_validator
    import persona_v2_raw_domain_renderer as raw_domain_renderer
    import persona_v2_raw_domain_validator as raw_domain_validator
    import persona_v2_raw_image_media_renderer as raw_image_media_renderer
    import persona_v2_raw_image_media_validator as raw_image_media_validator
    import persona_v2_raw_tar_gzip_renderer as raw_tar_gzip_renderer
    import persona_v2_raw_tar_gzip_validator as raw_tar_gzip_validator
    import persona_v2_raw_zip_renderer as raw_zip_renderer
    import persona_v2_raw_zip_validator as raw_zip_validator
    import persona_v2_source_inventory_profile as inventory_catalog
    import persona_v2_source_profile_catalog as historical_catalog
    import persona_v2_text_renderer as contributor_renderer
    import persona_v2_text_validator as contributor_validator
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kio.persona.pc-format-implementation-registry/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-format-implementation-registry"
MAX_REGISTRY_BYTES = 512 * 1024
EXPECTED_IMPLEMENTATION_ROW_COUNT = 71

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
        "authorizes_source_recipes",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "renderer_execution_environment_available",
    }
)


class PersonaV2FormatImplementationRegistryError(ValueError):
    """Raised when the final implementation registry contract is violated."""


PAIR_SPECS = (
    (
        "contributor-text",
        "contract_contributor",
        contributor_renderer,
        contributor_validator,
    ),
    ("pdf-text", "contract_contributor", pdf_renderer, pdf_validator),
    (
        "incidental-text",
        "incidental_searchable",
        incidental_renderer,
        incidental_validator,
    ),
    (
        "raw-document",
        "raw_only",
        raw_document_renderer,
        raw_document_validator,
    ),
    (
        "raw-image-media",
        "raw_only",
        raw_image_media_renderer,
        raw_image_media_validator,
    ),
    ("raw-zip", "raw_only", raw_zip_renderer, raw_zip_validator),
    (
        "raw-tar-gzip",
        "raw_only",
        raw_tar_gzip_renderer,
        raw_tar_gzip_validator,
    ),
    ("raw-domain", "raw_only", raw_domain_renderer, raw_domain_validator),
)

RUNTIME_SPECS = {
    "contributor-text": (
        contributor_renderer.TextRenderRequest,
        contributor_renderer.render_text,
        contributor_validator.TextValidationRequest,
        contributor_validator.validate_text_payload,
    ),
    "pdf-text": (
        pdf_renderer.PdfTextRenderRequest,
        pdf_renderer.render_pdf_text,
        pdf_validator.PdfTextValidationRequest,
        pdf_validator.validate_pdf_text_payload,
    ),
    "incidental-text": (
        incidental_renderer.IncidentalTextRenderRequest,
        incidental_renderer.render_incidental_text,
        incidental_validator.IncidentalTextValidationRequest,
        incidental_validator.validate_incidental_text_payload,
    ),
    "raw-document": (
        raw_document_renderer.RawDocumentRenderRequest,
        raw_document_renderer.render_raw_document,
        raw_document_validator.RawDocumentValidationRequest,
        raw_document_validator.validate_raw_document_payload,
    ),
    "raw-image-media": (
        raw_image_media_renderer.RawImageMediaRenderRequest,
        raw_image_media_renderer.render_raw_image_media,
        raw_image_media_validator.RawImageMediaValidationRequest,
        raw_image_media_validator.validate_raw_image_media_payload,
    ),
    "raw-zip": (
        raw_zip_renderer.RawZipRenderRequest,
        raw_zip_renderer.render_raw_zip,
        raw_zip_validator.RawZipValidationRequest,
        raw_zip_validator.validate_raw_zip_payload,
    ),
    "raw-tar-gzip": (
        raw_tar_gzip_renderer.RawTarGzipRenderRequest,
        raw_tar_gzip_renderer.render_raw_tar_gzip,
        raw_tar_gzip_validator.RawTarGzipValidationRequest,
        raw_tar_gzip_validator.validate_raw_tar_gzip_payload,
    ),
    "raw-domain": (
        raw_domain_renderer.RawDomainRenderRequest,
        raw_domain_renderer.render_raw_domain,
        raw_domain_validator.RawDomainValidationRequest,
        raw_domain_validator.validate_raw_domain_payload,
    ),
}


def _require_all_false_authority(value, *, label):
    authority = value.get("authority") if type(value) is dict else None
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        raise PersonaV2FormatImplementationRegistryError(
            f"{label} authority must be non-empty and all false"
        )


def _upstream_binding(name, dependency_role, value, module):
    validate = getattr(module, f"validate_{name}")
    digest = getattr(module, f"{name}_sha256")
    validate(value)
    _require_all_false_authority(value, label=name)
    if value.get("g0_contract_frozen") is not False:
        raise PersonaV2FormatImplementationRegistryError(
            f"{name} must remain non-G0"
        )
    raw = module.canonical_json_bytes(value)
    sha256 = digest(value)
    if sha256 != hashlib.sha256(raw).hexdigest():
        raise PersonaV2FormatImplementationRegistryError(
            f"{name} returned a non-canonical digest"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name.replace("_", "-"),
        "sha256": sha256,
    }


def _contract_binding(pair_id, role, value, module):
    getattr(module, f"validate_{role}_contract")(value)
    _require_all_false_authority(value, label=f"{pair_id}/{role}")
    raw = module.canonical_json_bytes(value)
    generic_raw = artifact_common.canonical_json_bytes(
        value,
        label=f"{pair_id}/{role} contract",
        max_bytes=64 * 1024,
    )
    if raw == generic_raw:
        canonicalization_profile = "sorted-compact-utf8"
    elif raw == generic_raw + b"\n" and raw.isascii():
        canonicalization_profile = "sorted-compact-ascii-with-terminal-lf"
    else:
        raise PersonaV2FormatImplementationRegistryError(
            f"{pair_id}/{role} uses an unsupported canonical framing"
        )
    sha256 = getattr(module, f"{role}_contract_sha256")(value)
    if sha256 != hashlib.sha256(raw).hexdigest():
        raise PersonaV2FormatImplementationRegistryError(
            f"{pair_id}/{role} returned a non-canonical digest"
        )
    implementation_id_key = f"{role}_id"
    implementation_version_key = f"{role}_schema_version"
    variant_ids = [row["variant_id"] for row in value["variant_rows"]]
    if len(variant_ids) != len(set(variant_ids)):
        raise PersonaV2FormatImplementationRegistryError(
            f"{pair_id}/{role} repeats variant ownership"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "binding_id": f"{pair_id}-{role}-contract",
        "canonical_bytes": len(raw),
        "canonicalization_profile": canonicalization_profile,
        "contract_role": role,
        "implementation_id": value[implementation_id_key],
        "implementation_pair_id": pair_id,
        "implementation_schema_version": value[implementation_version_key],
        "sha256": sha256,
        "variant_count": value["variant_count"],
        "variant_ids": variant_ids,
    }


def _formula_kind(formula):
    if "exact_formula" in formula:
        return "exact-expression"
    if (
        "increment_bytes_per_additional_complexity" in formula
        and (
            "base_bytes_at_complexity_one" in formula
            or "base_bytes_at_minimum_complexity" in formula
        )
    ):
        return "affine"
    if type(formula.get("formula_kind")) is str:
        return formula["formula_kind"]
    return "bounded-declaration"


def _quantization_contract(renderer_row):
    if "size_quantization" in renderer_row:
        return {
            "declaration": "structured-implementation-contract",
            "metadata": copy.deepcopy(renderer_row["size_quantization"]),
        }
    inline = renderer_row["raw_byte_formula"].get("quantization")
    if type(inline) is str:
        return {
            "declaration": "inline-formula-contract",
            "metadata": {"mode": inline},
        }
    return {
        "declaration": "not-separately-declared",
        "metadata": {},
    }


def _complexity_parameters(request_fields):
    return [
        field
        for field in request_fields
        if field not in {"schema_version", "variant"}
    ]


def _normalized_implementation_contract(
    renderer_contract,
    renderer_row,
    validator_contract,
    variant_row,
    marginals,
):
    complexity = renderer_row["complexity"]
    formula = renderer_row["raw_byte_formula"]
    source_counts = {
        "full": sum(row["full_count"] for row in marginals),
        "full-residual": sum(
            row["full_minus_pilot_count"] for row in marginals
        ),
        "pilot": sum(row["pilot_count"] for row in marginals),
        "tiny-smoke": sum(row["tiny_smoke_count"] for row in marginals),
    }
    return {
        "complexity": copy.deepcopy(complexity),
        "formula": {
            "formula_kind": _formula_kind(formula),
            "parameters": copy.deepcopy(formula),
        },
        "lane": {
            "active_persona_variant_rows": sum(
                row["full_count"] > 0 for row in marginals
            ),
            "byte_distribution_profile_id": variant_row["byte_contract"][
                "byte_distribution_profile_id"
            ],
            "byte_stress_encoding_eligible": variant_row["byte_contract"][
                "byte_stress_encoding_eligible"
            ],
            "byte_stress_lane_implemented": renderer_contract.get(
                "byte_stress_lane_implemented", False
            ),
            "byte_stress_size_classes": copy.deepcopy(
                variant_row["byte_contract"]["byte_stress_size_classes"]
            ),
            "declared_persona_variant_rows": len(marginals),
            "gate_role": variant_row["gate_role"],
            "source_counts": source_counts,
        },
        "parameter_shape": {
            "complexity_parameters": _complexity_parameters(
                renderer_contract["request_fields"]
            ),
            "inclusive_maximum": complexity["inclusive_maximum"],
            "inclusive_minimum": complexity["inclusive_minimum"],
            "measure": complexity["measure"],
            "renderer_request_fields": copy.deepcopy(
                renderer_contract["request_fields"]
            ),
            "request_carriers_identity_free": True,
            "selection_phase": formula.get(
                "selection_phase", "not-declared-by-implementation-contract"
            ),
            "validator_request_fields": copy.deepcopy(
                validator_contract["request_fields"]
            ),
        },
        "quantization": _quantization_contract(renderer_row),
    }


def _factor_near_square(value, maximum_dimension):
    candidate = int(value**0.5)
    while candidate > 0:
        if value % candidate == 0 and value // candidate <= maximum_dimension:
            return candidate, value // candidate
        candidate -= 1
    raise PersonaV2FormatImplementationRegistryError(
        "raster probe complexity cannot be represented by bounded dimensions"
    )


def _probe_parameter_sets(renderer_contract, renderer_row):
    complexity = renderer_row["complexity"]
    minimum = complexity["inclusive_minimum"]
    maximum = complexity["inclusive_maximum"]
    midpoint = (minimum + maximum) // 2
    lanes = (("minimum", minimum), ("midpoint", midpoint), ("maximum", maximum))
    request_fields = renderer_contract["request_fields"]
    if "target_complexity" in request_fields:
        return [
            {"lane": lane, "parameters": {"target_complexity": target}}
            for lane, target in lanes
        ]
    if request_fields == [
        "schema_version",
        "variant",
        "width",
        "height",
        "frame_or_event_count",
    ]:
        if complexity["request_binding"] == "exact-frame-or-event-count":
            return [
                {
                    "lane": lane,
                    "parameters": {
                        "frame_or_event_count": target,
                        "height": 0,
                        "width": 0,
                    },
                }
                for lane, target in lanes
            ]
        dimension_maximum = complexity["raster_dimension_inclusive_maximum"]
        result = []
        for lane, target in lanes:
            width, height = _factor_near_square(target, dimension_maximum)
            result.append(
                {
                    "lane": lane,
                    "parameters": {
                        "frame_or_event_count": 0,
                        "height": height,
                        "width": width,
                    },
                }
            )
        return result
    raise PersonaV2FormatImplementationRegistryError(
        f"unsupported probe parameter shape: {request_fields!r}"
    )


def _observed_probe_complexity(parameters):
    if "target_complexity" in parameters:
        return parameters["target_complexity"]
    if parameters["frame_or_event_count"]:
        return parameters["frame_or_event_count"]
    return parameters["width"] * parameters["height"]


def _bound_runtime_receipt(owner, variant_id, rendered, native_receipt):
    return {
        "input_payload_sha256": hashlib.sha256(rendered["data"]).hexdigest(),
        "native_receipt": native_receipt,
        "validator_binding_id": owner["validator_binding"]["binding_id"],
        "validator_id": owner["validator_binding"]["implementation_id"],
        "validator_profile_id": owner["validator_profile_id"],
        "validator_schema_version": owner["validator_binding"][
            "implementation_schema_version"
        ],
        "variant_id": variant_id,
    }


def _validate_runtime_receipt(
    receipt,
    *,
    owner,
    variant_id,
    expected_complexity,
    payload_bytes,
    payload_sha256,
):
    if type(receipt) is not dict or set(receipt) != {
        "input_payload_sha256",
        "native_receipt",
        "validator_binding_id",
        "validator_id",
        "validator_profile_id",
        "validator_schema_version",
        "variant_id",
    }:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator must return the exact bound receipt schema"
        )
    if receipt != {
        "input_payload_sha256": payload_sha256,
        "native_receipt": receipt["native_receipt"],
        "validator_binding_id": owner["validator_binding"]["binding_id"],
        "validator_id": owner["validator_binding"]["implementation_id"],
        "validator_profile_id": owner["validator_profile_id"],
        "validator_schema_version": owner["validator_binding"][
            "implementation_schema_version"
        ],
        "variant_id": variant_id,
    }:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator receipt is rethreaded or payload-unbound"
        )
    native_receipt = receipt["native_receipt"]
    if type(native_receipt) is not dict or not native_receipt:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator native receipt must be a non-empty object"
        )
    try:
        artifact_common.validate_plain_value(
            receipt, label="runtime conformance receipt"
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryError(str(error)) from None
    for key, flag in native_receipt.items():
        if key.endswith("_attested") and (
            type(flag) is not bool or flag is not False
        ):
            raise PersonaV2FormatImplementationRegistryError(
                "runtime receipt attempted an attestation"
            )
    if "authority" in native_receipt:
        _require_all_false_authority(native_receipt, label="runtime receipt")
    if "structure_validated" in native_receipt and native_receipt[
        "structure_validated"
    ] is not True:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator did not accept structure"
        )
    if "identity_tokens_absent" in native_receipt and native_receipt[
        "identity_tokens_absent"
    ] is not True:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator did not accept the identity-free payload"
        )
    observed = native_receipt.get(
        "observed_local_complexity", native_receipt.get("observed_complexity")
    )
    if observed != expected_complexity or native_receipt.get(
        "target_bytes"
    ) != payload_bytes:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime validator receipt does not match the requested probe"
        )


def _render_probe(pair_id, variant_id, parameters):
    render_request, render, _, _ = RUNTIME_SPECS[pair_id]
    render_kwargs = {"schema_version": 2, "variant": variant_id, **parameters}
    rendered = render(render_request(**render_kwargs))
    return {
        "content_media_type": rendered.content_media_type,
        "data": rendered.data,
        "expected_kio_path_media_type": rendered.expected_kio_path_media_type,
        "expected_offline_disposition": rendered.expected_offline_disposition,
        "extension": rendered.extension,
        "target_bytes": rendered.target_bytes,
        "target_complexity": rendered.target_complexity,
    }


def _validate_probe(pair_id, variant_id, parameters, rendered):
    _, _, validation_request, validate = RUNTIME_SPECS[pair_id]
    render_kwargs = {"schema_version": 2, "variant": variant_id, **parameters}
    validation_kwargs = {
        **render_kwargs,
        "data": rendered["data"],
        "extension": rendered["extension"],
        "content_media_type": rendered["content_media_type"],
        "expected_kio_path_media_type": rendered["expected_kio_path_media_type"],
        "expected_offline_disposition": rendered["expected_offline_disposition"],
    }
    return validate(validation_request(**validation_kwargs))


def _execute_probe(owner, variant_id, parameters):
    rendered = _render_probe(owner["pair_id"], variant_id, parameters)
    native_receipt = _validate_probe(
        owner["pair_id"], variant_id, parameters, rendered
    )
    return rendered, _bound_runtime_receipt(
        owner, variant_id, rendered, native_receipt
    )


def _conformance_receipt(owner, variant_id, pair_payload_hasher):
    probe_rows = []
    for probe in _probe_parameter_sets(
        owner["renderer_contract"], owner["renderer_row"]
    ):
        rendered, validator_receipt = _execute_probe(
            owner, variant_id, probe["parameters"]
        )
        expected_complexity = _observed_probe_complexity(probe["parameters"])
        data = rendered["data"]
        if (
            type(data) is not bytes
            or rendered["target_bytes"] != len(data)
            or rendered["target_complexity"] != expected_complexity
        ):
            raise PersonaV2FormatImplementationRegistryError(
                f"renderer probe result drifted: {variant_id}/{probe['lane']}"
            )
        _validate_runtime_receipt(
            validator_receipt,
            owner=owner,
            variant_id=variant_id,
            expected_complexity=expected_complexity,
            payload_bytes=len(data),
            payload_sha256=hashlib.sha256(data).hexdigest(),
        )
        pair_payload_hasher.update(variant_id.encode("ascii") + b"\0")
        pair_payload_hasher.update(str(expected_complexity).encode("ascii") + b"\0")
        pair_payload_hasher.update(data)
        receipt_raw = artifact_common.canonical_json_bytes(
            validator_receipt,
            label="runtime validator receipt",
            max_bytes=64 * 1024,
        )
        probe_rows.append(
            {
                "lane": probe["lane"],
                "parameters": copy.deepcopy(probe["parameters"]),
                "payload_bytes": len(data),
                "payload_sha256": hashlib.sha256(data).hexdigest(),
                "validator_receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            }
        )
    aggregate_raw = artifact_common.canonical_json_bytes(
        probe_rows,
        label="variant min midpoint max conformance probes",
        max_bytes=64 * 1024,
    )
    return {
        "actual_chunks_attested": False,
        "actual_payload_bytes_attested": False,
        "aggregate_sha256": hashlib.sha256(aggregate_raw).hexdigest(),
        "probe_count": 3,
        "probe_profile": "minimum-midpoint-maximum-v2",
        "probes": probe_rows,
        "validator_accepted_all": True,
    }


def _format_specific_metadata(renderer_row):
    normalized_keys = {
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
    }
    return {
        key: copy.deepcopy(renderer_row[key])
        for key in sorted(set(renderer_row) - normalized_keys)
    }


def _coverage(variant_value, owner_rows):
    marginals = variant_value["persona_variant_marginals"]
    result = {}
    role_names = (
        ("contract_contributor", "contributor"),
        ("incidental_searchable", "incidental"),
        ("raw_only", "raw"),
    )
    for gate_role, output_name in role_names:
        variant_ids = {
            variant_id
            for variant_id, owner in owner_rows.items()
            if owner["gate_role"] == gate_role
        }
        selected = [row for row in marginals if row["variant_id"] in variant_ids]
        result[output_name] = {
            "full": sum(row["full_count"] for row in selected),
            "full-residual": sum(
                row["full_minus_pilot_count"] for row in selected
            ),
            "pilot": sum(row["pilot_count"] for row in selected),
            "variant_count": len(variant_ids),
        }
    result["total"] = {
        "active_persona_variant_rows": sum(
            row["full_count"] > 0 for row in marginals
        ),
        "full": sum(row["full_count"] for row in marginals),
        "full-residual": sum(
            row["full_minus_pilot_count"] for row in marginals
        ),
        "implementation_pair_count": len(PAIR_SPECS),
        "pilot": sum(row["pilot_count"] for row in marginals),
        "variant_count": len(owner_rows),
    }
    return result


@functools.lru_cache(maxsize=1)
def _canonical_registry():
    variant_value = variant_catalog.build_variant_catalog()
    historical_value = historical_catalog.build_source_profile_catalog()
    inventory_value = inventory_catalog.build_source_inventory_profile_catalog()
    variant_catalog.validate_variant_catalog(variant_value)
    historical_catalog.validate_source_profile_catalog(historical_value)
    inventory_catalog.validate_source_inventory_profile_catalog(inventory_value)

    contract_bindings = []
    contract_values = {}
    owner_rows = {}
    for pair_id, expected_gate_role, renderer_module, validator_module in PAIR_SPECS:
        renderer_value = renderer_module.build_renderer_contract()
        validator_value = validator_module.build_validator_contract()
        renderer_binding = _contract_binding(
            pair_id, "renderer", renderer_value, renderer_module
        )
        validator_binding = _contract_binding(
            pair_id, "validator", validator_value, validator_module
        )
        if renderer_binding["variant_ids"] != validator_binding["variant_ids"]:
            raise PersonaV2FormatImplementationRegistryError(
                f"{pair_id} renderer/validator ownership drifted"
            )
        renderer_rows = {
            row["variant_id"]: row for row in renderer_value["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row for row in validator_value["variant_rows"]
        }
        for variant_id in renderer_binding["variant_ids"]:
            renderer_row = renderer_rows[variant_id]
            validator_projection = copy.deepcopy(validator_rows[variant_id])
            validator_profile_id = validator_projection.pop("validator_profile_id")
            if validator_projection != renderer_row:
                raise PersonaV2FormatImplementationRegistryError(
                    f"{pair_id}/{variant_id} renderer-validator row projection drifted"
                )
            if renderer_row["gate_role"] != expected_gate_role:
                raise PersonaV2FormatImplementationRegistryError(
                    f"{pair_id}/{variant_id} gate role drifted"
                )
            if variant_id in owner_rows:
                raise PersonaV2FormatImplementationRegistryError(
                    f"variant ownership overlaps: {variant_id}"
                )
            owner_rows[variant_id] = {
                "gate_role": expected_gate_role,
                "pair_id": pair_id,
                "renderer_binding": renderer_binding,
                "renderer_contract": renderer_value,
                "renderer_row": renderer_row,
                "validator_binding": validator_binding,
                "validator_contract": validator_value,
                "validator_profile_id": validator_profile_id,
            }
        contract_bindings.extend((renderer_binding, validator_binding))
        contract_values[renderer_binding["binding_id"]] = renderer_value
        contract_values[validator_binding["binding_id"]] = validator_value

    variant_rows = variant_value["variant_rows"]
    if set(owner_rows) != {row["variant_id"] for row in variant_rows}:
        raise PersonaV2FormatImplementationRegistryError(
            "implementation ownership does not cover the exact 71 variants"
        )
    historical_rows = {
        row["variant_id"]: row for row in historical_value["source_profile_rows"]
    }
    inventory_rows = {
        row["variant_id"]: row for row in inventory_value["source_profile_rows"]
    }
    marginals_by_variant = {
        row["variant_id"]: [] for row in variant_rows
    }
    for marginal in variant_value["persona_variant_marginals"]:
        marginals_by_variant[marginal["variant_id"]].append(marginal)

    conformance_receipts = {}
    pair_conformance_receipts = []
    for pair_id, _, _, _ in PAIR_SPECS:
        pair_payload_hasher = hashlib.sha256()
        pair_variant_ids = owner_rows[next(
            variant_id
            for variant_id, owner in owner_rows.items()
            if owner["pair_id"] == pair_id
        )]["renderer_binding"]["variant_ids"]
        for variant_id in pair_variant_ids:
            conformance_receipts[variant_id] = _conformance_receipt(
                owner_rows[variant_id], variant_id, pair_payload_hasher
            )
        pair_conformance_receipts.append(
            {
                "aggregate_algorithm": (
                    "sha256-over-variant-nul-observed-complexity-nul-payload-sequence-v2"
                ),
                "implementation_pair_id": pair_id,
                "payload_aggregate_sha256": pair_payload_hasher.hexdigest(),
                "probe_count": 3 * len(pair_variant_ids),
                "variant_count": len(pair_variant_ids),
            }
        )

    implementation_rows = []
    exact_metadata = (
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
    )
    for variant_row in variant_rows:
        variant_id = variant_row["variant_id"]
        owner = owner_rows[variant_id]
        renderer_row = owner["renderer_row"]
        historical_row = historical_rows[variant_id]
        inventory_row = inventory_rows[variant_id]
        for field in exact_metadata:
            expected = variant_row[field]
            if (
                renderer_row[field] != expected
                or historical_row[field] != expected
                or inventory_row[field] != expected
            ):
                raise PersonaV2FormatImplementationRegistryError(
                    f"upstream metadata drifted: {variant_id}/{field}"
                )
        if "compound_suffix_parts" in renderer_row and (
            renderer_row["compound_suffix_parts"]
            != variant_row["compound_suffix_parts"]
        ):
            raise PersonaV2FormatImplementationRegistryError(
                f"compound suffix drifted: {variant_id}"
            )
        if "safety_profile_id" in renderer_row and (
            renderer_row["safety_profile_id"]
            != variant_row["safety_profile_id"]
        ):
            raise PersonaV2FormatImplementationRegistryError(
                f"safety profile drifted: {variant_id}"
            )
        recipe = inventory_row["source_recipe"]
        if recipe != {
            "binding_status": "reserved-unbound",
            "parameters_complete": False,
            "profile_id": "not-bound",
            "slot_id": inventory_catalog.source_recipe_slot_id(variant_id),
        }:
            raise PersonaV2FormatImplementationRegistryError(
                f"formal source recipe became bound: {variant_id}"
            )
        implementation_rows.append(
            {
                "compound_suffix_parts": copy.deepcopy(
                    variant_row["compound_suffix_parts"]
                ),
                "conformance_receipt": copy.deepcopy(
                    conformance_receipts[variant_id]
                ),
                "content_media_type": variant_row["content_media_type"],
                "expected_kio_path_media_type": variant_row[
                    "expected_kio_path_media_type"
                ],
                "expected_offline_disposition": variant_row[
                    "expected_offline_disposition"
                ],
                "family": variant_row["family"],
                "filename_extension": variant_row["filename_extension"],
                "format_specific_metadata": _format_specific_metadata(renderer_row),
                "gate_role": variant_row["gate_role"],
                "historical_source_profile": {
                    "bounded_feasibility_profile_id": historical_row[
                        "bounded_feasibility_profile_id"
                    ],
                    "catalog_status": historical_row["bounded_feasibility"][
                        "status"
                    ],
                    "source_recipe_profile_id": historical_row[
                        "source_recipe_profile_id"
                    ],
                    "vertical_slice_ready": historical_row[
                        "bounded_feasibility"
                    ]["vertical_slice_ready"],
                },
                "implementation": {
                    "implementation_profile_id": (
                        f"persona-v2-format-implementation-{variant_id}-v2"
                    ),
                    "pair_id": owner["pair_id"],
                    "renderer_binding_id": owner["renderer_binding"]["binding_id"],
                    "renderer_id": owner["renderer_binding"]["implementation_id"],
                    "renderer_schema_version": owner["renderer_binding"][
                        "implementation_schema_version"
                    ],
                    "validator_binding_id": owner["validator_binding"]["binding_id"],
                    "validator_id": owner["validator_binding"]["implementation_id"],
                    "validator_profile_id": owner["validator_profile_id"],
                    "validator_schema_version": owner["validator_binding"][
                        "implementation_schema_version"
                    ],
                },
                "normalized_contract": _normalized_implementation_contract(
                    owner["renderer_contract"],
                    renderer_row,
                    owner["validator_contract"],
                    variant_row,
                    marginals_by_variant[variant_id],
                ),
                "render_template": renderer_row["render_template"],
                "safety_profile_id": variant_row["safety_profile_id"],
                "search_contract": copy.deepcopy(variant_row["search_contract"]),
                "source_inventory_profile": {
                    "execution_eligibility_status": inventory_row[
                        "execution_eligibility_status"
                    ],
                    "source_profile_id": inventory_row["source_profile_id"],
                    "source_recipe_binding_status": recipe["binding_status"],
                    "source_recipe_profile_id": recipe["profile_id"],
                    "source_recipe_slot_id": recipe["slot_id"],
                },
                "upstream_planned_renderer": copy.deepcopy(
                    inventory_row["upstream_planned_renderer"]
                ),
                "upstream_planned_validator": copy.deepcopy(
                    inventory_row["upstream_planned_validator"]
                ),
                "variant_id": variant_id,
            }
        )

    input_bindings = [
        _upstream_binding(
            "variant_catalog",
            "frozen-71-variant-metadata-and-marginals",
            variant_value,
            variant_catalog,
        ),
        _upstream_binding(
            "source_profile_catalog",
            "historical-10-ready-61-missing-status-unchanged",
            historical_value,
            historical_catalog,
        ),
        _upstream_binding(
            "source_inventory_profile_catalog",
            "71-profile-and-reserved-recipe-slot-identity",
            inventory_value,
            inventory_catalog,
        ),
    ]
    # Give the historical binding an unambiguous name without changing its body.
    input_bindings[1]["name"] = "persona-v2-historical-source-profile-catalog"
    input_bindings[0]["name"] = "persona-v2-variant-catalog"
    input_bindings[2]["name"] = "persona-v2-source-inventory-profile-catalog"

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "exact_contract_bindings": 16,
            "exact_implementation_rows": EXPECTED_IMPLEMENTATION_ROW_COUNT,
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_REGISTRY_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_variant_implementation_rows_present": True,
            "formal_source_recipe_profiles_bound": False,
            "historical_source_profile_catalog_rewritten": False,
            "physical_source_materialization_complete": False,
            "renderer_validator_implementation_complete": True,
            "source_instances_bound": False,
            "source_level_allocation_solution_present": False,
        },
        "completion_scope": (
            "all-71-id-free-renderer-validator-format-contracts-only-"
            "historical-profile-unchanged-no-recipe-no-source-instance-no-execution-no-g0"
        ),
        "contract_binding_order": [
            binding["binding_id"] for binding in contract_bindings
        ],
        "contract_bindings": contract_bindings,
        "coverage": _coverage(variant_value, owner_rows),
        "fixture_id": variant_value["fixture_id"],
        "fixture_schema_version": variant_value["fixture_schema_version"],
        "g0_contract_frozen": False,
        "implementation_rows": implementation_rows,
        "implementation_pair_conformance_receipts": pair_conformance_receipts,
        "input_binding_order": [binding["name"] for binding in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "contract_bindings": "declared-eight-pair-order-renderer-before-validator",
            "implementation_rows": "exact-upstream-variant-catalog-order",
        },
        "remaining_blockers": [
            "all-formal-source-recipe-profiles-remain-unbound",
            "all-source-instance-identities-and-source-level-allocation-remain-unbound",
            "physical-render-write-history-and-kio-observation-not-present",
            "formal-persona-package-cap-and-byte-stress-gates-not-proved",
        ],
    }
    if len(implementation_rows) != EXPECTED_IMPLEMENTATION_ROW_COUNT:
        raise PersonaV2FormatImplementationRegistryError(
            "implementation registry must contain exactly 71 rows"
        )
    if value["coverage"] != {
        "contributor": {
            "full": 69236,
            "full-residual": 62311,
            "pilot": 6925,
            "variant_count": 10,
        },
        "incidental": {
            "full": 60414,
            "full-residual": 54374,
            "pilot": 6040,
            "variant_count": 11,
        },
        "raw": {
            "full": 73350,
            "full-residual": 66015,
            "pilot": 7335,
            "variant_count": 50,
        },
        "total": {
            "active_persona_variant_rows": 541,
            "full": 203000,
            "full-residual": 182700,
            "implementation_pair_count": 8,
            "pilot": 20300,
            "variant_count": 71,
        },
    }:
        raise PersonaV2FormatImplementationRegistryError(
            "implementation coverage marginals drifted"
        )
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 format implementation registry",
            max_bytes=MAX_REGISTRY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryError(str(error)) from None
    return value


def build_format_implementation_registry():
    """Return a detached immutable 71-row implementation registry body."""

    return copy.deepcopy(_canonical_registry())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 format implementation registry",
            max_bytes=MAX_REGISTRY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryError(str(error)) from None


def _contract_providers():
    renderer_values = {}
    validator_values = {}
    for pair_id, _, renderer_module, validator_module in PAIR_SPECS:
        renderer_values[f"{pair_id}-renderer-contract"] = (
            renderer_module.build_renderer_contract()
        )
        validator_values[f"{pair_id}-validator-contract"] = (
            validator_module.build_validator_contract()
        )
    return renderer_values.__getitem__, validator_values.__getitem__


def _probe_providers():
    owners = {}
    for pair_id, _, renderer_module, validator_module in PAIR_SPECS:
        renderer_contract = renderer_module.build_renderer_contract()
        validator_contract = validator_module.build_validator_contract()
        validator_rows = {
            row["variant_id"]: row
            for row in validator_contract["variant_rows"]
        }
        validator_binding = {
            "binding_id": f"{pair_id}-validator-contract",
            "implementation_id": validator_contract["validator_id"],
            "implementation_schema_version": validator_contract[
                "validator_schema_version"
            ],
        }
        for row in renderer_contract["variant_rows"]:
            variant_id = row["variant_id"]
            if variant_id in owners:
                raise PersonaV2FormatImplementationRegistryError(
                    f"runtime probe ownership overlaps: {variant_id}"
                )
            owners[variant_id] = {
                "pair_id": pair_id,
                "validator_binding": validator_binding,
                "validator_profile_id": validator_rows[variant_id][
                    "validator_profile_id"
                ],
            }
    if len(owners) != EXPECTED_IMPLEMENTATION_ROW_COUNT:
        raise PersonaV2FormatImplementationRegistryError(
            "runtime probe ownership must cover exactly 71 variants"
        )

    def renderer_provider(variant_id, parameters):
        return _render_probe(owners[variant_id]["pair_id"], variant_id, parameters)

    def validator_provider(variant_id, parameters, rendered):
        native_receipt = _validate_probe(
            owners[variant_id]["pair_id"], variant_id, parameters, rendered
        )
        return _bound_runtime_receipt(
            owners[variant_id], variant_id, rendered, native_receipt
        )

    return renderer_provider, validator_provider


def validate_format_implementation_registry(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_format_implementation_registry,
            label="persona v2 format implementation registry",
            max_bytes=MAX_REGISTRY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryError(str(error)) from None
    renderer_provider, validator_provider = _contract_providers()
    renderer_probe_provider, _ = _probe_providers()
    try:
        independent.validate_format_implementation_registry(
            value,
            variant_catalog_value=variant_catalog.build_variant_catalog(),
            historical_source_profile_value=(
                historical_catalog.build_source_profile_catalog()
            ),
            source_inventory_profile_value=(
                inventory_catalog.build_source_inventory_profile_catalog()
            ),
            renderer_contract_provider=renderer_provider,
            validator_contract_provider=validator_provider,
            renderer_probe_provider=renderer_probe_provider,
        )
    except independent.PersonaV2FormatImplementationRegistryValidationError as error:
        raise PersonaV2FormatImplementationRegistryError(str(error)) from None
    return True


def format_implementation_registry_sha256(value=None):
    if value is None:
        value = build_format_implementation_registry()
    validate_format_implementation_registry(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_IMPLEMENTATION_ROW_COUNT",
    "MAX_REGISTRY_BYTES",
    "PersonaV2FormatImplementationRegistryError",
    "build_format_implementation_registry",
    "canonical_json_bytes",
    "format_implementation_registry_sha256",
    "validate_format_implementation_registry",
]
