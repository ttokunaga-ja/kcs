"""Independent validator for the frozen persona-PC v2 format registry.

The module intentionally imports neither the registry producer nor any
renderer implementation.  The eight standalone validator modules are its
trusted runtime-validation base: they receive the supplied payload under the
exact bound variant request, so an external provider cannot relabel a receipt.
All three upstream catalogs and all sixteen contract bodies arrive through
explicit arguments.  Registry and binding metadata are authenticated before
either contract provider is called.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_incidental_text_validator as incidental_validator
    from . import persona_v2_pdf_text_validator as pdf_validator
    from . import persona_v2_raw_document_validator as raw_document_validator
    from . import persona_v2_raw_domain_validator as raw_domain_validator
    from . import persona_v2_raw_image_media_validator as raw_image_media_validator
    from . import persona_v2_raw_tar_gzip_validator as raw_tar_gzip_validator
    from . import persona_v2_raw_zip_validator as raw_zip_validator
    from . import persona_v2_text_validator as contributor_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_incidental_text_validator as incidental_validator
    import persona_v2_pdf_text_validator as pdf_validator
    import persona_v2_raw_document_validator as raw_document_validator
    import persona_v2_raw_domain_validator as raw_domain_validator
    import persona_v2_raw_image_media_validator as raw_image_media_validator
    import persona_v2_raw_tar_gzip_validator as raw_tar_gzip_validator
    import persona_v2_raw_zip_validator as raw_zip_validator
    import persona_v2_text_validator as contributor_validator


ARTIFACT_SCHEMA = "kio.persona.pc-format-implementation-registry/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-format-implementation-registry"
MAX_REGISTRY_BYTES = 512 * 1024
MAX_DEPENDENCY_BYTES = 256 * 1024
MAX_CONTRACT_BYTES = 64 * 1024

# Patched only after the deterministic body and every dependency contract have
# passed the complete test suite.  These pins cover the body, not a self hash.
EXPECTED_REGISTRY_CANONICAL_BYTES = 333_881
EXPECTED_REGISTRY_SHA256 = (
    "59ae0b2e5c755732e6937e70ada4b243ea2c7432a9ce654c7e9c219b4a13bc5d"
)

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

EXPECTED_COVERAGE = {
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
}

EXPECTED_INPUT_BINDINGS = (
    (
        "persona-v2-variant-catalog",
        "frozen-71-variant-metadata-and-marginals",
        "persona-pc-v2-variant-catalog",
        "kio.persona.pc-variant-catalog/v2",
        2,
        211733,
        "807dd3cdd8df613ac21e6ba64877fb5abb40c72ed4949abaa0d440a449e7f9e9",
    ),
    (
        "persona-v2-historical-source-profile-catalog",
        "historical-10-ready-61-missing-status-unchanged",
        "persona-pc-v2-source-profile-catalog",
        "kio.persona.pc-source-profile-catalog/v2",
        2,
        72559,
        "f575c597281071b1a9abb1d6dac1c244a42a2a302eb4d1f9ee79278276680d7d",
    ),
    (
        "persona-v2-source-inventory-profile-catalog",
        "71-profile-and-reserved-recipe-slot-identity",
        "persona-pc-v2-source-inventory-profile-catalog",
        "kio.persona.pc-source-inventory-profile-catalog/v2",
        2,
        87391,
        "9b0de3defbc106f0bfa8b96ca2134886acd6766ac69196e3498b6b6f7edf43c0",
    ),
)

# binding ID, pair ID, role, variant count, canonical bytes, sha256
EXPECTED_CONTRACT_BINDINGS = (
    (
        "contributor-text-renderer-contract",
        "contributor-text",
        "renderer",
        9,
        5976,
        "c9c5b93f61e2da72e1ddc20867d97c52d0a525f4b273427016c625ca21f04056",
    ),
    (
        "contributor-text-validator-contract",
        "contributor-text",
        "validator",
        9,
        6557,
        "a5c2bcbf73f4add58b2b4b7543840f1451dad3c6ec7503106b861be9d21675b3",
    ),
    (
        "pdf-text-renderer-contract",
        "pdf-text",
        "renderer",
        1,
        2075,
        "ab66e11d93e2aa7896bdffd28f1c1fec9f443a4ff3b48ba6dcc4d1c12bab69f6",
    ),
    (
        "pdf-text-validator-contract",
        "pdf-text",
        "validator",
        1,
        2233,
        "78c90d4cccb254f67bc030e79eaef46704ce4d8555a3edc8f42edc293e91805e",
    ),
    (
        "incidental-text-renderer-contract",
        "incidental-text",
        "renderer",
        11,
        9139,
        "22fae0f62a67856ef20b5820c7274aad542a2de06f76c93c5c68acdaed9652f4",
    ),
    (
        "incidental-text-validator-contract",
        "incidental-text",
        "validator",
        11,
        10090,
        "67a0f0913de6087ca4b1c836d6dff4f845d6ee50a3adf12b794236f128baed75",
    ),
    (
        "raw-document-renderer-contract",
        "raw-document",
        "renderer",
        4,
        4657,
        "ac43d8e60fe288552e5edf1e11d98123b34766db8387460cb9f7ddf70af3ba2c",
    ),
    (
        "raw-document-validator-contract",
        "raw-document",
        "validator",
        4,
        5183,
        "c664596fce5331268ad69886b3f2d159e090241b4ef2848ac4ce64c52a1a572a",
    ),
    (
        "raw-image-media-renderer-contract",
        "raw-image-media",
        "renderer",
        7,
        7504,
        "25231398ec7002e5ce7fbfe3d3089e14a9ef8547bc9a9f580cc385dd88fcda00",
    ),
    (
        "raw-image-media-validator-contract",
        "raw-image-media",
        "validator",
        7,
        8223,
        "b0fdf9e944b0df72b2f8d8601a83f6958654f92272466fd49b897a3b3e168953",
    ),
    (
        "raw-zip-renderer-contract",
        "raw-zip",
        "renderer",
        21,
        18670,
        "037897466c19ce476e4d5a7fff00d18905bbe80ad42d326b503c744d4e3dd1bb",
    ),
    (
        "raw-zip-validator-contract",
        "raw-zip",
        "validator",
        21,
        20737,
        "8c9390fa0667860e17a872b3c16e047d688dcc7919c73a4933eddfa38082aeec",
    ),
    (
        "raw-tar-gzip-renderer-contract",
        "raw-tar-gzip",
        "renderer",
        16,
        14589,
        "d23a9b29f4e26748f32f07e201c1294ede5cd4534a27533e9ddc9b88a01d8cb8",
    ),
    (
        "raw-tar-gzip-validator-contract",
        "raw-tar-gzip",
        "validator",
        16,
        15885,
        "2e98faae761d7ae4aaaeba37a560d4e78dc3cc948551abde1acc399018d31bf6",
    ),
    (
        "raw-domain-renderer-contract",
        "raw-domain",
        "renderer",
        2,
        3680,
        "d23868cb344a49ee2c2d354cfe0eb6b0ea9abd07163d573f1ba3b99da229f6ce",
    ),
    (
        "raw-domain-validator-contract",
        "raw-domain",
        "validator",
        2,
        3970,
        "520ced5cc89ca1bc5a0da45e14c7406e9d7e791d07ae27b2997749cf11ed2e9b",
    ),
)

FORBIDDEN_REQUEST_IDENTITY_FIELDS = frozenset(
    {
        "history_event_id",
        "persona_id",
        "query_id",
        "source_id",
        "source_instance_id",
    }
)

VALIDATOR_RUNTIME_SPECS = {
    "contributor-text": (
        contributor_validator,
        contributor_validator.TextValidationRequest,
        contributor_validator.validate_text_payload,
    ),
    "pdf-text": (
        pdf_validator,
        pdf_validator.PdfTextValidationRequest,
        pdf_validator.validate_pdf_text_payload,
    ),
    "incidental-text": (
        incidental_validator,
        incidental_validator.IncidentalTextValidationRequest,
        incidental_validator.validate_incidental_text_payload,
    ),
    "raw-document": (
        raw_document_validator,
        raw_document_validator.RawDocumentValidationRequest,
        raw_document_validator.validate_raw_document_payload,
    ),
    "raw-image-media": (
        raw_image_media_validator,
        raw_image_media_validator.RawImageMediaValidationRequest,
        raw_image_media_validator.validate_raw_image_media_payload,
    ),
    "raw-zip": (
        raw_zip_validator,
        raw_zip_validator.RawZipValidationRequest,
        raw_zip_validator.validate_raw_zip_payload,
    ),
    "raw-tar-gzip": (
        raw_tar_gzip_validator,
        raw_tar_gzip_validator.RawTarGzipValidationRequest,
        raw_tar_gzip_validator.validate_raw_tar_gzip_payload,
    ),
    "raw-domain": (
        raw_domain_validator,
        raw_domain_validator.RawDomainValidationRequest,
        raw_domain_validator.validate_raw_domain_payload,
    ),
}


class PersonaV2FormatImplementationRegistryValidationError(ValueError):
    """Raised by the producer-independent registry validator."""


def _fail(message):
    raise PersonaV2FormatImplementationRegistryValidationError(message)


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 format implementation registry",
            max_bytes=MAX_REGISTRY_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryValidationError(
            str(error)
        ) from None


def _canonical_dependency(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FormatImplementationRegistryValidationError(
            str(error)
        ) from None


def _exact_keys(value, expected, *, label):
    if type(value) is not dict or set(value) != set(expected):
        _fail(f"{label} must expose the exact field schema")


def _require_all_false_authority(value, *, label, exact_fields=None):
    authority = value.get("authority") if type(value) is dict else None
    if type(authority) is not dict or not authority:
        _fail(f"{label} authority must be a non-empty object")
    if exact_fields is not None and set(authority) != set(exact_fields):
        _fail(f"{label} authority field schema drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must be exactly all false")


def _verify_frozen_body(value):
    raw = canonical_json_bytes(value)
    if (
        len(raw) != EXPECTED_REGISTRY_CANONICAL_BYTES
        or hashlib.sha256(raw).hexdigest() != EXPECTED_REGISTRY_SHA256
    ):
        _fail("registry body differs from the final frozen pin")
    return raw


def _expected_input_binding_rows():
    return [
        {
            "artifact_kind": kind,
            "artifact_schema": schema,
            "artifact_schema_version": version,
            "canonical_bytes": canonical_bytes,
            "dependency_role": role,
            "name": name,
            "sha256": sha256,
        }
        for name, role, kind, schema, version, canonical_bytes, sha256 in (
            EXPECTED_INPUT_BINDINGS
        )
    ]


def _validate_binding_metadata_before_providers(value):
    _exact_keys(
        value,
        {
            "artifact_kind",
            "artifact_schema",
            "artifact_schema_version",
            "authority",
            "canonical_limits",
            "completion_claims",
            "completion_scope",
            "contract_binding_order",
            "contract_bindings",
            "coverage",
            "fixture_id",
            "fixture_schema_version",
            "g0_contract_frozen",
            "implementation_rows",
            "implementation_pair_conformance_receipts",
            "input_binding_order",
            "input_bindings",
            "orders",
            "remaining_blockers",
        },
        label="registry",
    )
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != "kio-persona-pc-v2"
        or value["fixture_schema_version"] != 2
        or value["g0_contract_frozen"] is not False
    ):
        _fail("registry identity or non-G0 state drifted")
    _require_all_false_authority(
        value, label="registry", exact_fields=AUTHORITY_FIELDS
    )
    if value["coverage"] != EXPECTED_COVERAGE:
        _fail("registry coverage marginals drifted")
    expected_inputs = _expected_input_binding_rows()
    if value["input_bindings"] != expected_inputs or value[
        "input_binding_order"
    ] != [row["name"] for row in expected_inputs]:
        _fail("upstream catalog binding metadata drifted")

    bindings = value["contract_bindings"]
    expected_ids = [row[0] for row in EXPECTED_CONTRACT_BINDINGS]
    if (
        type(bindings) is not list
        or len(bindings) != 16
        or value["contract_binding_order"] != expected_ids
    ):
        _fail("contract binding order or cardinality drifted")
    binding_by_id = {}
    pair_roles = {}
    renderer_ownership = {}
    for binding, expected in zip(bindings, EXPECTED_CONTRACT_BINDINGS):
        _exact_keys(
            binding,
            {
                "artifact_kind",
                "artifact_schema",
                "artifact_schema_version",
                "binding_id",
                "canonical_bytes",
                "canonicalization_profile",
                "contract_role",
                "implementation_id",
                "implementation_pair_id",
                "implementation_schema_version",
                "sha256",
                "variant_count",
                "variant_ids",
            },
            label="contract binding",
        )
        binding_id, pair_id, role, count, canonical_bytes, sha256 = expected
        expected_canonicalization = (
            "sorted-compact-ascii-with-terminal-lf"
            if pair_id == "raw-image-media"
            else "sorted-compact-utf8"
        )
        if (
            binding["binding_id"] != binding_id
            or binding["implementation_pair_id"] != pair_id
            or binding["contract_role"] != role
            or binding["variant_count"] != count
            or binding["canonical_bytes"] != canonical_bytes
            or binding["canonicalization_profile"] != expected_canonicalization
            or binding["sha256"] != sha256
            or type(binding["artifact_kind"]) is not str
            or type(binding["artifact_schema"]) is not str
            or binding["artifact_schema_version"] != 2
            or type(binding["implementation_id"]) is not str
            or not binding["implementation_id"]
            or binding["implementation_schema_version"] != 2
            or type(binding["variant_ids"]) is not list
            or len(binding["variant_ids"]) != count
            or any(type(item) is not str or not item for item in binding["variant_ids"])
            or len(set(binding["variant_ids"])) != count
        ):
            _fail(f"contract binding pin or shape drifted: {binding_id}")
        if binding_id in binding_by_id:
            _fail(f"duplicate contract binding: {binding_id}")
        binding_by_id[binding_id] = binding
        pair_roles.setdefault(pair_id, {})[role] = binding
    for pair_id, roles in pair_roles.items():
        if set(roles) != {"renderer", "validator"}:
            _fail(f"implementation pair is incomplete: {pair_id}")
        if roles["renderer"]["variant_ids"] != roles["validator"]["variant_ids"]:
            _fail(f"renderer/validator ownership rethreaded: {pair_id}")
        for variant_id in roles["renderer"]["variant_ids"]:
            if variant_id in renderer_ownership:
                _fail(f"variant ownership overlaps: {variant_id}")
            renderer_ownership[variant_id] = pair_id
    if len(renderer_ownership) != 71:
        _fail("contract ownership must cover exactly 71 unique variants")
    return binding_by_id, pair_roles, renderer_ownership


def _validate_upstream_binding(value, expected, *, label):
    name, _, kind, schema, version, expected_bytes, expected_sha = expected
    raw = _canonical_dependency(value, label=label, max_bytes=MAX_DEPENDENCY_BYTES)
    if (
        len(raw) != expected_bytes
        or hashlib.sha256(raw).hexdigest() != expected_sha
        or type(value) is not dict
        or value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version") != version
        or value.get("fixture_id") != "kio-persona-pc-v2"
        or value.get("fixture_schema_version") != 2
        or value.get("g0_contract_frozen") is not False
    ):
        _fail(f"frozen upstream body drifted: {name}")
    _require_all_false_authority(value, label=label)


def _validate_contract_body(contract, binding, *, role):
    generic_raw = _canonical_dependency(
        contract,
        label=f"{binding['binding_id']} body",
        max_bytes=MAX_CONTRACT_BYTES,
    )
    if binding["canonicalization_profile"] == "sorted-compact-utf8":
        raw = generic_raw
    elif binding[
        "canonicalization_profile"
    ] == "sorted-compact-ascii-with-terminal-lf" and generic_raw.isascii():
        raw = generic_raw + b"\n"
    else:
        _fail(f"unsupported contract canonicalization: {binding['binding_id']}")
    if (
        len(raw) != binding["canonical_bytes"]
        or hashlib.sha256(raw).hexdigest() != binding["sha256"]
        or type(contract) is not dict
        or contract.get("artifact_kind") != binding["artifact_kind"]
        or contract.get("artifact_schema") != binding["artifact_schema"]
        or contract.get("artifact_schema_version")
        != binding["artifact_schema_version"]
        or contract.get(f"{role}_id") != binding["implementation_id"]
        or contract.get(f"{role}_schema_version")
        != binding["implementation_schema_version"]
        or contract.get("variant_count") != binding["variant_count"]
        or contract.get("request_is_identity_free") is not True
        or contract.get("vertical_slice_implementation_available") is not True
    ):
        _fail(f"contract body pin or identity drifted: {binding['binding_id']}")
    _require_all_false_authority(contract, label=binding["binding_id"])
    request_fields = contract.get("request_fields")
    if (
        type(request_fields) is not list
        or not request_fields
        or any(type(field) is not str or not field for field in request_fields)
        or len(set(request_fields)) != len(request_fields)
        or FORBIDDEN_REQUEST_IDENTITY_FIELDS.intersection(request_fields)
    ):
        _fail(f"request field contract is not exact identity-free: {binding['binding_id']}")
    rows = contract.get("variant_rows")
    if (
        type(rows) is not list
        or len(rows) != binding["variant_count"]
        or [row.get("variant_id") for row in rows] != binding["variant_ids"]
    ):
        _fail(f"contract variant rows drifted: {binding['binding_id']}")
    return contract


def _load_contracts(binding_by_id, pair_roles, renderer_provider, validator_provider):
    if not callable(renderer_provider) or not callable(validator_provider):
        _fail("contract providers must be callable")
    seen_object_ids = set()
    contracts = {}
    for binding_id in [row[0] for row in EXPECTED_CONTRACT_BINDINGS]:
        binding = binding_by_id[binding_id]
        role = binding["contract_role"]
        provider = renderer_provider if role == "renderer" else validator_provider
        try:
            contract = provider(binding_id)
        except Exception as error:
            _fail(f"contract provider failed for {binding_id}: {type(error).__name__}")
        if id(contract) in seen_object_ids:
            _fail(f"contract provider aliased bodies: {binding_id}")
        seen_object_ids.add(id(contract))
        contracts[binding_id] = _validate_contract_body(
            contract, binding, role=role
        )
    shared_rows = {}
    validator_profiles = {}
    for pair_id, roles in pair_roles.items():
        renderer_contract = contracts[roles["renderer"]["binding_id"]]
        validator_contract = contracts[roles["validator"]["binding_id"]]
        runtime_module = VALIDATOR_RUNTIME_SPECS[pair_id][0]
        direct_validator_contract = runtime_module.build_validator_contract()
        runtime_module.validate_validator_contract(direct_validator_contract)
        _validate_contract_body(
            direct_validator_contract,
            roles["validator"],
            role="validator",
        )
        if direct_validator_contract != validator_contract:
            _fail(f"runtime validator contract rethreaded: {pair_id}")
        renderer_rows = {
            row["variant_id"]: row for row in renderer_contract["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row for row in validator_contract["variant_rows"]
        }
        if len(renderer_rows) != len(renderer_contract["variant_rows"]) or len(
            validator_rows
        ) != len(validator_contract["variant_rows"]):
            _fail(f"contract rows repeat ownership: {pair_id}")
        for variant_id, renderer_row in renderer_rows.items():
            validator_projection = copy.deepcopy(validator_rows[variant_id])
            profile_id = validator_projection.pop("validator_profile_id", None)
            if type(profile_id) is not str or not profile_id:
                _fail(f"validator profile is missing: {pair_id}/{variant_id}")
            if validator_projection != renderer_row:
                _fail(
                    f"renderer-validator shared row projection drifted: {pair_id}/{variant_id}"
                )
            shared_rows[variant_id] = renderer_row
            validator_profiles[variant_id] = profile_id
    return contracts, shared_rows, validator_profiles


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
    return {"declaration": "not-separately-declared", "metadata": {}}


def _complexity_parameters(request_fields):
    return [
        field
        for field in request_fields
        if field not in {"schema_version", "variant"}
    ]


def _normalized_contract(renderer_contract, validator_contract, renderer_row, variant_row, marginals):
    complexity = renderer_row["complexity"]
    formula = renderer_row["raw_byte_formula"]
    return {
        "complexity": copy.deepcopy(complexity),
        "formula": {
            "formula_kind": _formula_kind(formula),
            "parameters": copy.deepcopy(formula),
        },
        "lane": {
            "active_persona_variant_rows": sum(
                item["full_count"] > 0 for item in marginals
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
            "source_counts": {
                "full": sum(item["full_count"] for item in marginals),
                "full-residual": sum(
                    item["full_minus_pilot_count"] for item in marginals
                ),
                "pilot": sum(item["pilot_count"] for item in marginals),
                "tiny-smoke": sum(
                    item["tiny_smoke_count"] for item in marginals
                ),
            },
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


def _factor_near_square(value, maximum_dimension):
    candidate = int(value**0.5)
    while candidate > 0:
        if value % candidate == 0 and value // candidate <= maximum_dimension:
            return candidate, value // candidate
        candidate -= 1
    _fail("raster probe complexity cannot be represented by bounded dimensions")


def _probe_parameter_sets(renderer_contract, renderer_row):
    complexity = renderer_row["complexity"]
    minimum = complexity["inclusive_minimum"]
    maximum = complexity["inclusive_maximum"]
    lanes = (
        ("minimum", minimum),
        ("midpoint", (minimum + maximum) // 2),
        ("maximum", maximum),
    )
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
        result = []
        for lane, target in lanes:
            width, height = _factor_near_square(
                target, complexity["raster_dimension_inclusive_maximum"]
            )
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
    _fail(f"unsupported probe parameter shape: {request_fields!r}")


def _observed_probe_complexity(parameters):
    if "target_complexity" in parameters:
        return parameters["target_complexity"]
    if parameters["frame_or_event_count"]:
        return parameters["frame_or_event_count"]
    return parameters["width"] * parameters["height"]


def _validate_runtime_receipt(
    receipt,
    *,
    variant_id,
    validator_binding,
    validator_profile_id,
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
        _fail("runtime validator must return the exact bound receipt schema")
    if receipt != {
        "input_payload_sha256": payload_sha256,
        "native_receipt": receipt["native_receipt"],
        "validator_binding_id": validator_binding["binding_id"],
        "validator_id": validator_binding["implementation_id"],
        "validator_profile_id": validator_profile_id,
        "validator_schema_version": validator_binding[
            "implementation_schema_version"
        ],
        "variant_id": variant_id,
    }:
        _fail("runtime validator receipt is rethreaded or payload-unbound")
    native_receipt = receipt["native_receipt"]
    if type(native_receipt) is not dict or not native_receipt:
        _fail("runtime validator native receipt must be a non-empty object")
    try:
        artifact_common.validate_plain_value(
            receipt, label="runtime conformance receipt"
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    for key, flag in native_receipt.items():
        if key.endswith("_attested") and (
            type(flag) is not bool or flag is not False
        ):
            _fail("runtime receipt attempted an attestation")
    if "authority" in native_receipt:
        _require_all_false_authority(native_receipt, label="runtime receipt")
    if "structure_validated" in native_receipt and native_receipt[
        "structure_validated"
    ] is not True:
        _fail("runtime validator did not accept structure")
    if "identity_tokens_absent" in native_receipt and native_receipt[
        "identity_tokens_absent"
    ] is not True:
        _fail("runtime validator did not accept the identity-free payload")
    observed = native_receipt.get(
        "observed_local_complexity", native_receipt.get("observed_complexity")
    )
    if observed != expected_complexity or native_receipt.get(
        "target_bytes"
    ) != payload_bytes:
        _fail("runtime validator receipt does not match the requested probe")


def _direct_bound_runtime_receipt(
    pair_id,
    variant_id,
    parameters,
    rendered,
    validator_binding,
    validator_profile_id,
):
    _, request_type, validate_payload = VALIDATOR_RUNTIME_SPECS[pair_id]
    request_kwargs = {
        "schema_version": 2,
        "variant": variant_id,
        **parameters,
        "data": rendered["data"],
        "extension": rendered["extension"],
        "content_media_type": rendered["content_media_type"],
        "expected_kio_path_media_type": rendered["expected_kio_path_media_type"],
        "expected_offline_disposition": rendered[
            "expected_offline_disposition"
        ],
    }
    native_receipt = validate_payload(request_type(**request_kwargs))
    return {
        "input_payload_sha256": hashlib.sha256(rendered["data"]).hexdigest(),
        "native_receipt": native_receipt,
        "validator_binding_id": validator_binding["binding_id"],
        "validator_id": validator_binding["implementation_id"],
        "validator_profile_id": validator_profile_id,
        "validator_schema_version": validator_binding[
            "implementation_schema_version"
        ],
        "variant_id": variant_id,
    }


def _recompute_conformance_receipt(
    variant_id,
    renderer_contract,
    renderer_row,
    validator_binding,
    validator_profile_id,
    renderer_probe_provider,
    pair_payload_hasher,
):
    probe_rows = []
    expected_rendered_keys = {
        "content_media_type",
        "data",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "extension",
        "target_bytes",
        "target_complexity",
    }
    for probe in _probe_parameter_sets(renderer_contract, renderer_row):
        try:
            rendered = renderer_probe_provider(
                variant_id, copy.deepcopy(probe["parameters"])
            )
        except Exception as error:
            _fail(
                f"renderer probe provider failed for {variant_id}/{probe['lane']}: "
                f"{type(error).__name__}"
            )
        _exact_keys(rendered, expected_rendered_keys, label="renderer probe result")
        data = rendered["data"]
        expected_complexity = _observed_probe_complexity(probe["parameters"])
        if (
            type(data) is not bytes
            or type(rendered["target_bytes"]) is not int
            or rendered["target_bytes"] != len(data)
            or rendered["target_complexity"] != expected_complexity
            or rendered["extension"] != renderer_row["filename_extension"]
            or rendered["content_media_type"] != renderer_row["content_media_type"]
            or rendered["expected_kio_path_media_type"]
            != renderer_row["expected_kio_path_media_type"]
            or rendered["expected_offline_disposition"]
            != renderer_row["expected_offline_disposition"]
        ):
            _fail(f"renderer probe result drifted: {variant_id}/{probe['lane']}")
        try:
            validator_receipt = _direct_bound_runtime_receipt(
                validator_binding["implementation_pair_id"],
                variant_id,
                copy.deepcopy(probe["parameters"]),
                rendered,
                validator_binding,
                validator_profile_id,
            )
        except Exception as error:
            _fail(
                f"direct runtime validator failed for {variant_id}/{probe['lane']}: "
                f"{type(error).__name__}"
            )
        _validate_runtime_receipt(
            validator_receipt,
            variant_id=variant_id,
            validator_binding=validator_binding,
            validator_profile_id=validator_profile_id,
            expected_complexity=expected_complexity,
            payload_bytes=len(data),
            payload_sha256=hashlib.sha256(data).hexdigest(),
        )
        pair_payload_hasher.update(variant_id.encode("ascii") + b"\0")
        pair_payload_hasher.update(str(expected_complexity).encode("ascii") + b"\0")
        pair_payload_hasher.update(data)
        receipt_raw = _canonical_dependency(
            validator_receipt,
            label="runtime validator receipt",
            max_bytes=MAX_CONTRACT_BYTES,
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
    aggregate_raw = _canonical_dependency(
        probe_rows,
        label="variant min midpoint max conformance probes",
        max_bytes=MAX_CONTRACT_BYTES,
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


def _walk_forbidden_instance_keys(value):
    if type(value) is dict:
        for key, item in value.items():
            if key in FORBIDDEN_REQUEST_IDENTITY_FIELDS:
                _fail(f"registry embeds forbidden source/request identity field: {key}")
            _walk_forbidden_instance_keys(item)
    elif type(value) is list:
        for item in value:
            _walk_forbidden_instance_keys(item)


def _validate_rows(
    value,
    variant_value,
    historical_value,
    inventory_value,
    binding_by_id,
    renderer_ownership,
    contracts,
    shared_rows,
    validator_profiles,
    renderer_probe_provider,
):
    variant_rows = variant_value.get("variant_rows")
    historical_rows = historical_value.get("source_profile_rows")
    inventory_rows = inventory_value.get("source_profile_rows")
    implementation_rows = value["implementation_rows"]
    if not all(type(rows) is list and len(rows) == 71 for rows in (
        variant_rows,
        historical_rows,
        inventory_rows,
        implementation_rows,
    )):
        _fail("all registry and upstream row sets must contain exactly 71 rows")
    variant_ids = [row.get("variant_id") for row in variant_rows]
    if (
        len(set(variant_ids)) != 71
        or [row.get("variant_id") for row in historical_rows] != variant_ids
        or [row.get("variant_id") for row in inventory_rows] != variant_ids
        or [row.get("variant_id") for row in implementation_rows] != variant_ids
        or set(renderer_ownership) != set(variant_ids)
        or set(shared_rows) != set(variant_ids)
    ):
        _fail("variant rows are missing, duplicated, aliased, or rethreaded")
    historical_by_id = {row["variant_id"]: row for row in historical_rows}
    inventory_by_id = {row["variant_id"]: row for row in inventory_rows}
    variant_by_id = {row["variant_id"]: row for row in variant_rows}
    marginals_by_id = {variant_id: [] for variant_id in variant_ids}
    marginals = variant_value.get("persona_variant_marginals")
    if type(marginals) is not list or len(marginals) != 566:
        _fail("persona-variant marginals must remain the frozen 566 rows")
    for marginal in marginals:
        variant_id = marginal.get("variant_id")
        if variant_id not in marginals_by_id:
            _fail("marginal references an undeclared variant")
        marginals_by_id[variant_id].append(marginal)

    expected_conformance = {}
    expected_pair_conformance = []
    renderer_binding_ids = [
        row[0]
        for row in EXPECTED_CONTRACT_BINDINGS
        if row[2] == "renderer"
    ]
    for renderer_binding_id in renderer_binding_ids:
        renderer_binding = binding_by_id[renderer_binding_id]
        pair_id = renderer_binding["implementation_pair_id"]
        validator_binding = binding_by_id[f"{pair_id}-validator-contract"]
        renderer_contract = contracts[renderer_binding_id]
        pair_payload_hasher = hashlib.sha256()
        for variant_id in renderer_binding["variant_ids"]:
            expected_conformance[variant_id] = _recompute_conformance_receipt(
                variant_id,
                renderer_contract,
                shared_rows[variant_id],
                validator_binding,
                validator_profiles[variant_id],
                renderer_probe_provider,
                pair_payload_hasher,
            )
        expected_pair_conformance.append(
            {
                "aggregate_algorithm": (
                    "sha256-over-variant-nul-observed-complexity-nul-payload-sequence-v2"
                ),
                "implementation_pair_id": pair_id,
                "payload_aggregate_sha256": pair_payload_hasher.hexdigest(),
                "probe_count": 3 * renderer_binding["variant_count"],
                "variant_count": renderer_binding["variant_count"],
            }
        )
    if value["implementation_pair_conformance_receipts"] != expected_pair_conformance:
        _fail("implementation-pair runtime aggregate receipt drifted")

    exact_metadata = (
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "gate_role",
    )
    row_keys = {
        "compound_suffix_parts",
        "conformance_receipt",
        "content_media_type",
        "expected_kio_path_media_type",
        "expected_offline_disposition",
        "family",
        "filename_extension",
        "format_specific_metadata",
        "gate_role",
        "historical_source_profile",
        "implementation",
        "normalized_contract",
        "render_template",
        "safety_profile_id",
        "search_contract",
        "source_inventory_profile",
        "upstream_planned_renderer",
        "upstream_planned_validator",
        "variant_id",
    }
    for registry_row in implementation_rows:
        _exact_keys(registry_row, row_keys, label="implementation row")
        variant_id = registry_row["variant_id"]
        variant_row = variant_by_id[variant_id]
        historical_row = historical_by_id[variant_id]
        inventory_row = inventory_by_id[variant_id]
        renderer_row = shared_rows[variant_id]
        pair_id = renderer_ownership[variant_id]
        renderer_binding = binding_by_id[f"{pair_id}-renderer-contract"]
        validator_binding = binding_by_id[f"{pair_id}-validator-contract"]
        renderer_contract = contracts[renderer_binding["binding_id"]]
        validator_contract = contracts[validator_binding["binding_id"]]
        for field in exact_metadata:
            if not (
                registry_row[field]
                == variant_row[field]
                == historical_row[field]
                == inventory_row[field]
                == renderer_row[field]
            ):
                _fail(f"metadata mapping drifted: {variant_id}/{field}")
        if (
            registry_row["compound_suffix_parts"]
            != variant_row["compound_suffix_parts"]
            or registry_row["safety_profile_id"]
            != variant_row["safety_profile_id"]
            or registry_row["search_contract"] != variant_row["search_contract"]
            or registry_row["render_template"] != renderer_row["render_template"]
            or registry_row["format_specific_metadata"]
            != _format_specific_metadata(renderer_row)
        ):
            _fail(f"format/search projection drifted: {variant_id}")
        recipe = inventory_row.get("source_recipe")
        expected_slot = f"persona-v2-source-recipe-slot-{variant_id}-v2"
        if recipe != {
            "binding_status": "reserved-unbound",
            "parameters_complete": False,
            "profile_id": "not-bound",
            "slot_id": expected_slot,
        }:
            _fail(f"formal recipe is no longer reserved-unbound: {variant_id}")
        if registry_row["source_inventory_profile"] != {
            "execution_eligibility_status": "blocked",
            "source_profile_id": (
                f"persona-v2-inventory-profile-{variant_id}-v2"
            ),
            "source_recipe_binding_status": "reserved-unbound",
            "source_recipe_profile_id": "not-bound",
            "source_recipe_slot_id": expected_slot,
        }:
            _fail(f"inventory profile/slot mapping drifted: {variant_id}")
        if registry_row["historical_source_profile"] != {
            "bounded_feasibility_profile_id": historical_row[
                "bounded_feasibility_profile_id"
            ],
            "catalog_status": historical_row["bounded_feasibility"]["status"],
            "source_recipe_profile_id": historical_row["source_recipe_profile_id"],
            "vertical_slice_ready": historical_row["bounded_feasibility"][
                "vertical_slice_ready"
            ],
        }:
            _fail(f"historical 10/61 profile mapping drifted: {variant_id}")
        if (
            registry_row["upstream_planned_renderer"]
            != inventory_row["upstream_planned_renderer"]
            or registry_row["upstream_planned_validator"]
            != inventory_row["upstream_planned_validator"]
        ):
            _fail(f"upstream planned implementation mapping drifted: {variant_id}")
        if registry_row["implementation"] != {
            "implementation_profile_id": (
                f"persona-v2-format-implementation-{variant_id}-v2"
            ),
            "pair_id": pair_id,
            "renderer_binding_id": renderer_binding["binding_id"],
            "renderer_id": renderer_binding["implementation_id"],
            "renderer_schema_version": renderer_binding[
                "implementation_schema_version"
            ],
            "validator_binding_id": validator_binding["binding_id"],
            "validator_id": validator_binding["implementation_id"],
            "validator_profile_id": validator_profiles[variant_id],
            "validator_schema_version": validator_binding[
                "implementation_schema_version"
            ],
        }:
            _fail(f"implementation owner rethreaded: {variant_id}")
        if registry_row["normalized_contract"] != _normalized_contract(
            renderer_contract,
            validator_contract,
            renderer_row,
            variant_row,
            marginals_by_id[variant_id],
        ):
            _fail(f"normalized implementation metadata drifted: {variant_id}")
        if registry_row["conformance_receipt"] != expected_conformance[variant_id]:
            _fail(f"runtime conformance receipt drifted: {variant_id}")


def validate_format_implementation_registry(
    value,
    *,
    variant_catalog_value,
    historical_source_profile_value,
    source_inventory_profile_value,
    renderer_contract_provider,
    validator_contract_provider,
    renderer_probe_provider,
):
    """Validate the final registry without importing any implementation module."""

    # The final body pin and every binding descriptor are checked before any
    # provider callback.  A forged registry therefore cannot select a provider
    # key or cause provider I/O.
    _verify_frozen_body(value)
    frozen_value = copy.deepcopy(value)
    binding_by_id, pair_roles, renderer_ownership = (
        _validate_binding_metadata_before_providers(frozen_value)
    )
    _validate_upstream_binding(
        variant_catalog_value,
        EXPECTED_INPUT_BINDINGS[0],
        label="frozen variant catalog",
    )
    _validate_upstream_binding(
        historical_source_profile_value,
        EXPECTED_INPUT_BINDINGS[1],
        label="frozen historical source profile catalog",
    )
    _validate_upstream_binding(
        source_inventory_profile_value,
        EXPECTED_INPUT_BINDINGS[2],
        label="frozen source inventory profile catalog",
    )
    if historical_source_profile_value.get("coverage") != {
        "all_variant_count": 71,
        "not_ready_variant_count": 61,
        "ready_active_persona_variant_rows": 116,
        "ready_persona_variant_rows": 116,
        "ready_source_counts": {
            "full_count": 69236,
            "full_minus_pilot_count": 62311,
            "pilot_count": 6925,
            "tiny_smoke_count": 1370,
        },
        "ready_variant_count": 10,
    }:
        _fail("historical source profile 10/61 coverage pin drifted")
    inventory_coverage = source_inventory_profile_value.get("coverage", {})
    if (
        inventory_coverage.get("profile_count") != 71
        or inventory_coverage.get("local_ready_profile_count") != 10
        or inventory_coverage.get("implementation_missing_profile_count") != 61
    ):
        _fail("source inventory historical 10/61 coverage drifted")

    contracts, shared_rows, validator_profiles = _load_contracts(
        binding_by_id,
        pair_roles,
        renderer_contract_provider,
        validator_contract_provider,
    )
    if not callable(renderer_probe_provider):
        _fail("renderer runtime probe provider must be callable")
    _validate_rows(
        frozen_value,
        variant_catalog_value,
        historical_source_profile_value,
        source_inventory_profile_value,
        binding_by_id,
        renderer_ownership,
        contracts,
        shared_rows,
        validator_profiles,
        renderer_probe_provider,
    )
    if frozen_value["completion_claims"] != {
        "all_variant_implementation_rows_present": True,
        "formal_source_recipe_profiles_bound": False,
        "historical_source_profile_catalog_rewritten": False,
        "physical_source_materialization_complete": False,
        "renderer_validator_implementation_complete": True,
        "source_instances_bound": False,
        "source_level_allocation_solution_present": False,
    }:
        _fail("completion claims exceed the implementation-only scope")
    _walk_forbidden_instance_keys(frozen_value)
    # Providers are untrusted callbacks and may retain aliases to any caller
    # object.  Re-authenticate the original registry and upstream bodies after
    # all callbacks so an in-validation mutation cannot escape the opening
    # body pins (TOCTOU).  All semantic checks above run against the detached
    # opening snapshot.
    _verify_frozen_body(value)
    _validate_upstream_binding(
        variant_catalog_value,
        EXPECTED_INPUT_BINDINGS[0],
        label="frozen variant catalog after provider callbacks",
    )
    _validate_upstream_binding(
        historical_source_profile_value,
        EXPECTED_INPUT_BINDINGS[1],
        label="frozen historical source profile catalog after provider callbacks",
    )
    _validate_upstream_binding(
        source_inventory_profile_value,
        EXPECTED_INPUT_BINDINGS[2],
        label="frozen source inventory profile catalog after provider callbacks",
    )
    return True


def format_implementation_registry_sha256(value):
    _verify_frozen_body(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CONTRACT_BINDINGS",
    "EXPECTED_INPUT_BINDINGS",
    "EXPECTED_REGISTRY_CANONICAL_BYTES",
    "EXPECTED_REGISTRY_SHA256",
    "PersonaV2FormatImplementationRegistryValidationError",
    "canonical_json_bytes",
    "format_implementation_registry_sha256",
    "validate_format_implementation_registry",
]
