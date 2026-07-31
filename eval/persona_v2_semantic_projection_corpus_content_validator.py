"""Producer-independent validation for three corpus-content projections.

The sibling projection producer is intentionally not imported.  Primary-use-
case and recipe projections are independently allowlisted from authenticated
full upstream bodies.  Fact graphs are reconstructed from the authored data
module and authenticated upstream planning artifacts without calling the fact-
graph producer.  Material providers are bounded, detached, replayed twice, and
all full owners/direct fragments are rebuilt on postflight.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph_data as fact_data
    from . import persona_v2_formal_source_recipe_catalog as recipe_catalog
    from . import persona_v2_formal_source_recipe_catalog_validator as recipe_validator
    from . import persona_v2_format_implementation_registry as format_registry
    from . import persona_v2_joint_problem as joint_problem
    from . import persona_v2_joint_solver_policy as solver_policy
    from . import persona_v2_primary_use_case_catalog as use_case_catalog
    from . import persona_v2_primary_use_case_catalog_validator as use_case_validator
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_source_inventory_profile as inventory_profile
    from . import persona_v2_source_profile_catalog as historical_profile
    from . import persona_v2_topology as topology
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph_data as fact_data
    import persona_v2_formal_source_recipe_catalog as recipe_catalog
    import persona_v2_formal_source_recipe_catalog_validator as recipe_validator
    import persona_v2_format_implementation_registry as format_registry
    import persona_v2_joint_problem as joint_problem
    import persona_v2_joint_solver_policy as solver_policy
    import persona_v2_primary_use_case_catalog as use_case_catalog
    import persona_v2_primary_use_case_catalog_validator as use_case_validator
    import persona_v2_realism_profile as realism
    import persona_v2_source_inventory_profile as inventory_profile
    import persona_v2_source_profile_catalog as historical_profile
    import persona_v2_topology as topology
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA_VERSION = 1
BODY_FRAMING = "canonical-json"
PRIMARY_CLASS_ID = "primary-use-case-corpus-half"
RECIPE_CLASS_ID = "recipe-content-filename-policy"
FACT_CLASS_ID = "fact-graph"
CLASS_ORDER = (PRIMARY_CLASS_ID, RECIPE_CLASS_ID, FACT_CLASS_ID)

PRIMARY_SCHEMA = (
    "kio.persona.pc-primary-use-case-corpus-content-projection/v1"
)
PRIMARY_KIND = "persona-pc-v2-primary-use-case-corpus-content-projection"
RECIPE_SCHEMA = (
    "kio.persona.pc-recipe-content-filename-policy-content-projection/v1"
)
RECIPE_KIND = "persona-pc-v2-recipe-content-filename-policy-content-projection"
FACT_SCHEMA = "kio.persona.pc-fact-graph-content-projection/v1"
FACT_KIND = "persona-pc-v2-fact-graph-content-projection"

PRIMARY_COORDINATES = {"scope": "suite"}
RECIPE_COORDINATES = {"scope": "suite"}
MAX_PRIMARY_BYTES = 64 * 2**10
TARGET_PRIMARY_BYTES = 16 * 2**10
MAX_RECIPE_BYTES = 384 * 2**10
TARGET_RECIPE_BYTES = 256 * 2**10
MAX_FACT_BYTES = 64 * 2**10
TARGET_FACT_BYTES = 32 * 2**10
MAX_FRAGMENT_BYTES = 2 * 2**20
MAX_MATERIAL_METADATA_BYTES = 256 * 2**10
EXPECTED_MATERIAL_COUNT = 22
MAX_FULL_OWNER_PINS = 6
MAX_DIRECT_BODY_PINS = 8

MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "bytes",
        "class_id",
        "coordinates",
        "direct_body_pins",
        "framing",
        "full_owner_pins",
    }
)
FULL_OWNER_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "coordinates",
        "owner_id",
        "owner_role",
        "sha256",
    }
)
DIRECT_PIN_FIELDS = frozenset(
    {
        "body_framing",
        "canonical_bytes",
        "direct_pin_id",
        "direct_pin_role",
        "sha256",
    }
)

PRIMARY_ROW_FIELDS = (
    "persona_id",
    "primary_use_case_id",
    "trigger",
    "desired_outcome",
    "required_families",
    "required_scope_role",
    "required_lifecycle_capabilities",
)
RECIPE_ROW_SCALAR_FIELDS = (
    "content_media_type",
    "expected_kio_path_media_type",
    "expected_offline_disposition",
    "family",
    "format_feasibility_render_template_id",
    "gate_role",
    "recipe_profile_id",
    "safety_profile_id",
    "semantic_profile_id",
    "source_inventory_profile_id",
    "source_recipe_slot_id",
    "variant_id",
)
RECIPE_COMPLEXITY_FIELDS = (
    "complexity",
    "formal_lane_policy_id",
    "formula",
    "lane",
    "parameter_shape",
    "quantization",
    "target_bytes_binding_mode",
)
RECIPE_LANE_FIELDS = (
    "active_persona_variant_rows",
    "byte_distribution_profile_id",
    "byte_stress_encoding_eligible",
    "byte_stress_size_classes",
    "declared_persona_variant_rows",
    "gate_role",
    "source_counts",
)
RECIPE_PARAMETER_SHAPE_FIELDS = (
    "complexity_parameters",
    "inclusive_maximum",
    "inclusive_minimum",
    "measure",
    "renderer_request_fields",
    "request_carriers_identity_free",
    "validator_request_fields",
)
RECIPE_CONTENT_FIELDS = (
    "content_template_profile_id",
    "content_template_slot_id",
    "control_input_fields",
    "document_role",
    "fact_profile_rule",
    "language_binding_mode",
    "literal_exposure_forbidden_fields",
    "semantic_membership_mode",
)
RECIPE_FILENAME_FIELDS = (
    "basename_policy_id",
    "compound_suffix_parts",
    "filename_extension",
    "filename_template_profile_id",
    "filename_template_slot_id",
)

PRIMARY_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "primary_use_case_rows",
    }
)
RECIPE_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "policy_catalogs",
        "recipe_profile_rows",
    }
)
FACT_TOP_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "graphs",
        "logical_time_contract",
        "persona_id",
        "predicate_catalog",
    }
)
FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "chunk-id",
        "completion",
        "distractor",
        "latency",
        "oracle",
        "query",
        "rank",
        "receipt",
        "review",
        "runtime",
        "solution",
    }
)
ALLOWED_SEMANTIC_RUNTIME_PATHS = frozenset(
    {
        ("logical_time_contract", "runtime_clock_read_allowed"),
    }
)
_SYNTHETIC_ID_RE = re.compile(r"^[a-z][a-z0-9-]*-syn-[0-9]{3}$")
_FACT_GRAPH_KINDS = frozenset({"case", "project"})
_FACT_VALUE_KINDS = frozenset(
    {
        "documentation-ip",
        "email",
        "entity-reference",
        "logical-day-offset",
        "scaled-integer",
        "synthetic-token",
        "unsigned-integer",
    }
)
_FACT_VALUE_KIND_ORDER = (
    "entity-reference",
    "email",
    "documentation-ip",
    "synthetic-token",
    "unsigned-integer",
    "scaled-integer",
    "logical-day-offset",
)
_FACT_CHECKPOINT_ORDER = (
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5-pre-purge",
    "W5-final",
)


class PersonaV2SemanticProjectionCorpusContentValidationError(ValueError):
    """Raised when one content projection/material fails closed validation."""


def _fail(message):
    raise PersonaV2SemanticProjectionCorpusContentValidationError(message)


def _sha256(raw):
    if type(raw) is not bytes:
        _fail("SHA-256 input must be exact built-in bytes")
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_duplicate_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_constant(_value):
    _fail("non-finite JSON numbers are forbidden")


def _reject_float(_value):
    _fail("JSON floating-point numbers are forbidden")


def _strict_loads(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except PersonaV2SemanticProjectionCorpusContentValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _opening_snapshot(value, *, label, maximum):
    if type(value) is not dict:
        _fail(f"{label} must be an exact object")
    opening_raw = _canonical(value, label=label, maximum=maximum)
    snapshot = _strict_loads(opening_raw, label=f"{label} opening image")
    if type(snapshot) is not dict:
        _fail(f"{label} opening image must be an object")
    if not hmac.compare_digest(
        opening_raw,
        _canonical(snapshot, label=label, maximum=maximum),
    ):
        _fail(f"{label} opening image is not canonical")
    return snapshot, opening_raw


def _reauth_target(value, opening_raw, *, label, maximum):
    current = _canonical(value, label=label, maximum=maximum)
    if not hmac.compare_digest(current, opening_raw):
        _fail(f"{label} mutated during validation")


def _canonical_projection(value):
    if type(value) is not dict:
        _fail("projection must be an object")
    schema = value.get("artifact_schema")
    limits = {
        PRIMARY_SCHEMA: ("primary-use-case corpus projection", MAX_PRIMARY_BYTES),
        RECIPE_SCHEMA: ("recipe/content/filename projection", MAX_RECIPE_BYTES),
        FACT_SCHEMA: ("fact-graph content projection", MAX_FACT_BYTES),
    }
    if schema not in limits:
        _fail("projection uses an unknown schema")
    label, maximum = limits[schema]
    return _canonical(value, label=label, maximum=maximum)


def _canonical_fragment(value, *, label):
    return _canonical(value, label=label, maximum=MAX_FRAGMENT_BYTES)


def _require_true(result, *, label):
    if result is not True:
        _fail(f"{label} validator did not return exact True")


def _owner_pin(value, raw, *, coordinates, owner_id, owner_role):
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "coordinates": copy.deepcopy(coordinates),
        "owner_id": owner_id,
        "owner_role": owner_role,
        "sha256": _sha256(raw),
    }


def _direct_pin(raw, *, direct_pin_id, direct_pin_role):
    return {
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": _sha256(raw),
    }


def _material(
    *, class_id, coordinates, artifact_kind, artifact_schema, body,
    full_owner_pins, direct_body_pins
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "bytes": body,
        "class_id": class_id,
        "coordinates": copy.deepcopy(coordinates),
        "direct_body_pins": copy.deepcopy(direct_body_pins),
        "framing": BODY_FRAMING,
        "full_owner_pins": copy.deepcopy(full_owner_pins),
    }


def _copy_fields(value, fields, *, label):
    if type(value) is not dict or any(field not in value for field in fields):
        _fail(f"{label} lacks a required source field")
    return {field: copy.deepcopy(value[field]) for field in fields}


def _project_primary(catalog):
    rows = [
        _copy_fields(row, PRIMARY_ROW_FIELDS, label="primary-use-case row")
        for row in catalog["primary_use_cases"]
    ]
    if (
        len(rows) != 20
        or [row["persona_id"] for row in rows] != list(envelope.PERSONA_IDS)
        or len({row["primary_use_case_id"] for row in rows}) != 20
    ):
        _fail("primary-use-case corpus row coverage drifted")
    return {
        "artifact_kind": PRIMARY_KIND,
        "artifact_schema": PRIMARY_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": catalog["fixture_id"],
        "fixture_schema_version": catalog["fixture_schema_version"],
        "primary_use_case_rows": rows,
    }


def _project_chunk_policy(row):
    value = copy.deepcopy(row)
    for field in ("expected_incidental_chunks_upper", "requested_chunks"):
        nested = value.get(field)
        if type(nested) is not dict or nested.pop("selected_value_present", None) is not False:
            _fail("recipe chunk selected-value boundary drifted")
    return value


def _project_policy_catalogs(policy_catalogs):
    if type(policy_catalogs) is not dict or set(policy_catalogs) != {
        "dynamic_incidental_wave_cap_policy",
        "filename_core_policy",
        "gate_role_chunk_policies",
        "lane_contracts",
    }:
        _fail("recipe policy catalog schema drifted")
    dynamic = copy.deepcopy(policy_catalogs["dynamic_incidental_wave_cap_policy"])
    for field in ("observed_values_present", "source_instance_assignments_present"):
        if dynamic.pop(field, None) is not False:
            _fail("dynamic incidental completion boundary drifted")
    lanes = copy.deepcopy(policy_catalogs["lane_contracts"])
    byte_stress = lanes.get("byte_stress")
    if type(byte_stress) is not dict:
        _fail("recipe lane policy lacks byte-stress semantics")
    if byte_stress.pop("projection_is_not_a_formal_variant_source_row", None) is not True:
        _fail("byte-stress projection boundary drifted")
    text_pdf = byte_stress.get("text_pdf_pages")
    if type(text_pdf) is not dict or text_pdf.pop("maximum_status", None) != "not-bound":
        _fail("byte-stress text-PDF status boundary drifted")
    return {
        "dynamic_incidental_wave_cap_policy": dynamic,
        "filename_core_policy": copy.deepcopy(policy_catalogs["filename_core_policy"]),
        "gate_role_chunk_policies": [
            _project_chunk_policy(row)
            for row in policy_catalogs["gate_role_chunk_policies"]
        ],
        "lane_contracts": lanes,
    }


def _project_recipe_row(row):
    result = _copy_fields(row, RECIPE_ROW_SCALAR_FIELDS, label="recipe row")
    chunk = row.get("chunk_policy")
    if type(chunk) is not dict or type(chunk.get("policy_id")) is not str:
        _fail("recipe row lacks chunk policy identity")
    result["chunk_policy_id"] = chunk["policy_id"]
    complexity = _copy_fields(
        row.get("complexity_byte_policy"),
        RECIPE_COMPLEXITY_FIELDS,
        label="recipe complexity policy",
    )
    complexity["lane"] = _copy_fields(
        complexity["lane"], RECIPE_LANE_FIELDS, label="recipe lane"
    )
    complexity["parameter_shape"] = _copy_fields(
        complexity["parameter_shape"],
        RECIPE_PARAMETER_SHAPE_FIELDS,
        label="recipe parameter shape",
    )
    result["complexity_byte_policy"] = complexity
    result["content_policy"] = _copy_fields(
        row.get("content_policy"), RECIPE_CONTENT_FIELDS, label="content policy"
    )
    result["filename_policy"] = _copy_fields(
        row.get("filename_policy"), RECIPE_FILENAME_FIELDS, label="filename policy"
    )
    implementation = row.get("implementation_binding")
    renderer = implementation.get("renderer") if type(implementation) is dict else None
    if type(renderer) is not dict:
        _fail("recipe row lacks renderer semantic identity")
    result["renderer_policy"] = {
        "implementation_pair_id": implementation["implementation_pair_id"],
        "implementation_profile_id": implementation["implementation_profile_id"],
        "renderer_id": renderer["renderer_id"],
        "renderer_schema_version": renderer["renderer_schema_version"],
    }
    return result


def _project_recipe(catalog):
    rows = [_project_recipe_row(row) for row in catalog["recipe_profile_rows"]]
    if (
        len(rows) != 71
        or len({row["variant_id"] for row in rows}) != 71
        or len({row["recipe_profile_id"] for row in rows}) != 71
    ):
        _fail("recipe projection coverage drifted")
    return {
        "artifact_kind": RECIPE_KIND,
        "artifact_schema": RECIPE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": catalog["fixture_id"],
        "fixture_schema_version": catalog["fixture_schema_version"],
        "policy_catalogs": _project_policy_catalogs(catalog["policy_catalogs"]),
        "recipe_profile_rows": rows,
    }


def _validated_value_raw(value, *, validate, canonical, label):
    snapshot_raw = canonical(value)
    snapshot = _strict_loads(snapshot_raw, label=f"{label} opening body")
    if type(snapshot) is not dict:
        _fail(f"{label} must be an object")
    _require_true(validate(snapshot), label=label)
    if not hmac.compare_digest(snapshot_raw, canonical(snapshot)):
        _fail(f"{label} validator mutated its detached opening body")
    if not hmac.compare_digest(snapshot_raw, canonical(value)):
        _fail(f"{label} changed during validation")
    return snapshot, snapshot_raw


def _primary_material():
    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    catalog_value = use_case_catalog.build_primary_use_case_catalog()
    envelope_snapshot, envelope_raw = _validated_value_raw(
        envelope_value,
        validate=envelope.validate_envelope_contract,
        canonical=envelope.canonical_json_bytes,
        label="envelope",
    )
    topology_snapshot, topology_raw = _validated_value_raw(
        topology_value,
        validate=topology.validate_topology_contract,
        canonical=topology.canonical_json_bytes,
        label="topology",
    )
    catalog_raw = use_case_catalog.canonical_json_bytes(catalog_value)
    catalog_snapshot = _strict_loads(catalog_raw, label="primary-use-case catalog")
    _require_true(
        use_case_validator.validate_primary_use_case_catalog(
            catalog_snapshot,
            envelope_value=envelope_snapshot,
            topology_value=topology_snapshot,
        ),
        label="independent primary-use-case catalog",
    )
    for snapshot, raw, canonical, label in (
        (
            catalog_snapshot,
            catalog_raw,
            use_case_catalog.canonical_json_bytes,
            "primary-use-case catalog",
        ),
        (
            envelope_snapshot,
            envelope_raw,
            envelope.canonical_json_bytes,
            "envelope dependency snapshot",
        ),
        (
            topology_snapshot,
            topology_raw,
            topology.canonical_json_bytes,
            "topology dependency snapshot",
        ),
    ):
        if not hmac.compare_digest(raw, canonical(snapshot)):
            _fail(f"{label} mutated during catalog validation")
    if not hmac.compare_digest(catalog_raw, use_case_catalog.canonical_json_bytes(catalog_value)):
        _fail("primary-use-case catalog changed during validation")
    projection = _project_primary(catalog_snapshot)
    body = _canonical_projection(projection)
    if len(body) > TARGET_PRIMARY_BYTES:
        _fail("primary-use-case projection exceeds its target")
    bindings = catalog_snapshot["input_bindings"]
    return _material(
        class_id=PRIMARY_CLASS_ID,
        coordinates=PRIMARY_COORDINATES,
        artifact_kind=PRIMARY_KIND,
        artifact_schema=PRIMARY_SCHEMA,
        body=body,
        full_owner_pins=[
            _owner_pin(
                catalog_snapshot, catalog_raw, coordinates={},
                owner_id="persona-v2-primary-use-case-catalog",
                owner_role="full-primary-use-case-catalog-owner-pin",
            ),
            _owner_pin(
                envelope_snapshot, envelope_raw, coordinates={},
                owner_id="persona-v2-envelope",
                owner_role="full-envelope-owner-pin",
            ),
            _owner_pin(
                topology_snapshot, topology_raw, coordinates={},
                owner_id="persona-v2-topology",
                owner_role="full-topology-owner-pin",
            ),
        ],
        direct_body_pins=[
            _direct_pin(
                _canonical_fragment(bindings[0], label="use-case envelope binding"),
                direct_pin_id="primary-use-case-catalog-envelope-binding",
                direct_pin_role="catalog-envelope-binding-row",
            ),
            _direct_pin(
                _canonical_fragment(bindings[1], label="use-case topology binding"),
                direct_pin_id="primary-use-case-catalog-topology-binding",
                direct_pin_role="catalog-topology-binding-row",
            ),
            _direct_pin(
                _canonical_fragment(
                    catalog_snapshot["primary_use_cases"],
                    label="primary-use-case source rows",
                ),
                direct_pin_id="primary-use-case-catalog-source-rows",
                direct_pin_role="primary-use-case-source-section",
            ),
        ],
    )


def _recipe_material():
    variant_value = variant_catalog.build_variant_catalog()
    inventory_value = inventory_profile.build_source_inventory_profile_catalog()
    registry_value = format_registry.build_format_implementation_registry()
    semantic_value = recipe_catalog._source_semantic_catalog_dependency()
    historical_value = historical_profile.build_source_profile_catalog()
    catalog_value = recipe_catalog.build_formal_source_recipe_catalog()

    values = (variant_value, inventory_value, registry_value, semantic_value)
    canonicalizers = (
        variant_catalog.canonical_json_bytes,
        inventory_profile.canonical_json_bytes,
        format_registry.canonical_json_bytes,
        recipe_catalog.semantic_catalog.canonical_json_bytes,
    )
    snapshots = []
    raws = []
    for value, canonical in zip(values, canonicalizers, strict=True):
        raw = canonical(value)
        snapshot = _strict_loads(raw, label="formal recipe dependency")
        if type(snapshot) is not dict:
            _fail("formal recipe dependency must be an object")
        snapshots.append(snapshot)
        raws.append(raw)
    historical_raw = historical_profile.canonical_json_bytes(historical_value)
    historical_snapshot = _strict_loads(
        historical_raw, label="historical source profile"
    )
    catalog_raw = recipe_catalog.canonical_json_bytes(catalog_value)
    catalog_snapshot = _strict_loads(catalog_raw, label="formal recipe catalog")
    renderer_contract_provider, validator_contract_provider = (
        format_registry._contract_providers()
    )
    renderer_probe_provider, _ = format_registry._probe_providers()
    _require_true(
        recipe_validator.validate_formal_source_recipe_catalog(
            catalog_snapshot,
            variant_catalog_value=snapshots[0],
            source_inventory_profile_value=snapshots[1],
            format_implementation_registry_value=snapshots[2],
            source_semantic_membership_catalog_value=snapshots[3],
            historical_source_profile_value=historical_snapshot,
            renderer_contract_provider=renderer_contract_provider,
            validator_contract_provider=validator_contract_provider,
            renderer_probe_provider=renderer_probe_provider,
        ),
        label="independent formal recipe catalog",
    )
    if not hmac.compare_digest(
        catalog_raw, recipe_catalog.canonical_json_bytes(catalog_snapshot)
    ):
        _fail("formal recipe validator mutated its detached catalog")
    for snapshot, raw, canonical in zip(
        snapshots, raws, canonicalizers, strict=True
    ):
        if not hmac.compare_digest(raw, canonical(snapshot)):
            _fail("formal recipe validator mutated a detached dependency")
    if not hmac.compare_digest(
        historical_raw,
        historical_profile.canonical_json_bytes(historical_snapshot),
    ):
        _fail("formal recipe validator mutated the historical dependency")
    if not hmac.compare_digest(catalog_raw, recipe_catalog.canonical_json_bytes(catalog_value)):
        _fail("formal recipe catalog changed during validation")
    for value, raw, canonical in zip(values, raws, canonicalizers, strict=True):
        if not hmac.compare_digest(raw, canonical(value)):
            _fail("formal recipe dependency changed during validation")
    if not hmac.compare_digest(
        historical_raw,
        historical_profile.canonical_json_bytes(historical_value),
    ):
        _fail("historical recipe dependency changed during validation")

    projection = _project_recipe(catalog_snapshot)
    body = _canonical_projection(projection)
    if len(body) > TARGET_RECIPE_BYTES:
        _fail("recipe projection exceeds its target")
    names = (
        "variant",
        "inventory-profile",
        "format-implementation-registry",
        "source-semantic-membership-catalog",
    )
    roles = (
        "full-variant-catalog-owner-pin",
        "full-source-inventory-profile-owner-pin",
        "full-format-implementation-registry-owner-pin",
        "full-source-semantic-membership-catalog-owner-pin",
    )
    owners = [
        _owner_pin(
            catalog_snapshot, catalog_raw, coordinates={},
            owner_id="persona-v2-formal-source-recipe-profile-catalog",
            owner_role="full-formal-recipe-catalog-owner-pin",
        )
    ]
    for name, role, value, raw in zip(names, roles, snapshots, raws, strict=True):
        owners.append(
            _owner_pin(
                value, raw, coordinates={}, owner_id=f"persona-v2-{name}",
                owner_role=role,
            )
        )
    binding_roles = (
        "catalog-variant-binding-row",
        "catalog-inventory-profile-binding-row",
        "catalog-format-registry-binding-row",
        "catalog-semantic-membership-binding-row",
    )
    direct = [
        _direct_pin(
            _canonical_fragment(binding, label="formal recipe binding"),
            direct_pin_id=f"formal-recipe-{binding['name']}-binding",
            direct_pin_role=role,
        )
        for binding, role in zip(
            catalog_snapshot["input_bindings"], binding_roles, strict=True
        )
    ]
    direct.extend(
        [
            _direct_pin(
                _canonical_fragment(
                    catalog_snapshot["policy_catalogs"],
                    label="formal recipe policy catalogs",
                ),
                direct_pin_id="formal-recipe-policy-catalogs",
                direct_pin_role="catalog-policy-section",
            ),
            _direct_pin(
                _canonical_fragment(
                    catalog_snapshot["recipe_profile_rows"],
                    label="formal recipe profile rows",
                ),
                direct_pin_id="formal-recipe-profile-rows",
                direct_pin_role="catalog-profile-row-section",
            ),
        ]
    )
    return _material(
        class_id=RECIPE_CLASS_ID,
        coordinates=RECIPE_COORDINATES,
        artifact_kind=RECIPE_KIND,
        artifact_schema=RECIPE_SCHEMA,
        body=body,
        full_owner_pins=owners,
        direct_body_pins=direct,
    )


def _fact_predicate_catalog(source):
    rows = []
    predicate_rows = source["predicate_rows"]
    if type(predicate_rows) is not tuple or len(predicate_rows) != 7:
        _fail("fact predicate source rows drifted")
    for predicate_id, value_kind in predicate_rows:
        rows.append({"predicate_id": predicate_id, "value_kind": value_kind})
    return rows


def _validate_fact_data_contract():
    theme_rows = fact_data.GRAPH_THEME_ROWS
    if type(theme_rows) is not tuple or len(theme_rows) != len(envelope.PERSONA_IDS):
        _fail("fact themes must contain exactly one tuple per persona")
    expected_ordinal = 1
    project_ids = []
    for index, row in enumerate(theme_rows):
        if type(row) is not tuple or len(row) != 2:
            _fail("each persona fact-theme row must be an exact pair")
        persona_id, themes = row
        if type(persona_id) is not str or persona_id != envelope.PERSONA_IDS[index]:
            _fail("fact-theme persona order drifted")
        if type(themes) is not tuple or len(themes) != 4:
            _fail("each persona must contain exactly four fact themes")
        for theme in themes:
            if type(theme) is not tuple or len(theme) != 2:
                _fail("each fact theme must be an exact pair")
            project_or_case_id, graph_kind = theme
            if (
                type(project_or_case_id) is not str
                or _SYNTHETIC_ID_RE.fullmatch(project_or_case_id) is None
                or not project_or_case_id.endswith(
                    f"-syn-{expected_ordinal:03d}"
                )
            ):
                _fail("fact-theme project/case identity or ordinal drifted")
            if type(graph_kind) is not str or graph_kind not in _FACT_GRAPH_KINDS:
                _fail("fact-theme graph kind must be exact project or case")
            project_ids.append(project_or_case_id)
            expected_ordinal += 1
    if (
        expected_ordinal != 81
        or len(project_ids) != 80
        or len(set(project_ids)) != 80
    ):
        _fail("fact-theme project/case identities are not suite-global unique")

    predicate_rows = fact_data.PREDICATE_ROWS
    if type(predicate_rows) is not tuple or len(predicate_rows) != 7:
        _fail("fact predicates must contain exactly seven pairs")
    predicate_ids = []
    value_kinds = []
    for ordinal, row in enumerate(predicate_rows, start=1):
        if type(row) is not tuple or len(row) != 2:
            _fail("each fact predicate must be an exact pair")
        predicate_id, value_kind = row
        if (
            type(predicate_id) is not str
            or _SYNTHETIC_ID_RE.fullmatch(predicate_id) is None
            or not predicate_id.endswith(f"-syn-{ordinal:03d}")
        ):
            _fail("fact predicate identity or suffix order drifted")
        if type(value_kind) is not str or value_kind not in _FACT_VALUE_KINDS:
            _fail("fact predicate value kind drifted")
        predicate_ids.append(predicate_id)
        value_kinds.append(value_kind)
    if (
        len(set(predicate_ids)) != 7
        or len(set(value_kinds)) != 7
        or tuple(value_kinds) != _FACT_VALUE_KIND_ORDER
    ):
        _fail("fact predicate identities/value kinds must be exact and unique")

    checkpoint_rows = fact_data.CHECKPOINT_ROWS
    if type(checkpoint_rows) is not tuple or len(checkpoint_rows) != 7:
        _fail("fact checkpoints must contain exactly seven pairs")
    checkpoint_names = []
    previous_offset = None
    for row in checkpoint_rows:
        if type(row) is not tuple or len(row) != 2:
            _fail("each fact checkpoint must be an exact pair")
        checkpoint, offset = row
        if type(checkpoint) is not str or not checkpoint:
            _fail("fact checkpoint names must be nonempty strings")
        if (
            type(offset) is not int
            or offset < 0
            or (previous_offset is not None and offset <= previous_offset)
        ):
            _fail("fact checkpoint offsets must be strictly increasing integers")
        checkpoint_names.append(checkpoint)
        previous_offset = offset
    if tuple(checkpoint_names) != _FACT_CHECKPOINT_ORDER:
        _fail("fact checkpoint names/order drifted")
    if (
        type(fact_data.REFERENCE_INSTANT_ID) is not str
        or _SYNTHETIC_ID_RE.fullmatch(fact_data.REFERENCE_INSTANT_ID) is None
        or fact_data.REFERENCE_INSTANT_UTC != "2026-07-13T00:00:00Z"
        or type(fact_data.MEASURE_UNIT_ID) is not str
        or _SYNTHETIC_ID_RE.fullmatch(fact_data.MEASURE_UNIT_ID) is None
    ):
        _fail("fact logical-time reference/unit identity drifted")
    return {
        "checkpoint_rows": checkpoint_rows,
        "graph_theme_rows": theme_rows,
        "measure_unit_id": fact_data.MEASURE_UNIT_ID,
        "predicate_rows": predicate_rows,
        "reference_instant_id": fact_data.REFERENCE_INSTANT_ID,
        "reference_instant_utc": fact_data.REFERENCE_INSTANT_UTC,
    }


def _fact_logical_time(source):
    checkpoint_rows = source["checkpoint_rows"]
    if type(checkpoint_rows) is not tuple or len(checkpoint_rows) != 7:
        _fail("fact checkpoint source rows drifted")
    return {
        "checkpoints": [
            {"checkpoint": checkpoint, "day_offset_after_reference": offset}
            for checkpoint, offset in checkpoint_rows
        ],
        "reference_instant_id": source["reference_instant_id"],
        "reference_instant_utc": source["reference_instant_utc"],
        "runtime_clock_read_allowed": False,
        "timezone_database_lookup_allowed": False,
    }


def _fact_visibility(profile, source):
    checkpoints = [row[0] for row in source["checkpoint_rows"]]
    states = {
        "stable-current": ["current"] * 7,
        "superseded-after-W1": ["current"] + ["history-only"] * 6,
        "introduced-at-W1": ["absent"] + ["current"] * 6,
    }.get(profile)
    if states is None:
        _fail("fact visibility profile drifted")
    return [
        {"checkpoint": checkpoint, "state": state}
        for checkpoint, state in zip(checkpoints, states, strict=True)
    ]


def _fact_row(
    fact_id, predicate_id, subject_id, typed_value, visibility, source
):
    return {
        "fact_id": fact_id,
        "predicate_id": predicate_id,
        "subject_entity_id": subject_id,
        "typed_value": typed_value,
        "visibility_by_checkpoint": _fact_visibility(visibility, source),
    }


def _fact_graph(project_or_case_id, graph_kind, ordinal, source):
    suffix = f"{ordinal:03d}"
    graph_id = f"graph-syn-{suffix}"
    owner_id = f"owner-unit-syn-{suffix}"
    contact_id = f"contact-syn-{suffix}"
    endpoint_id = f"endpoint-syn-{suffix}"
    fact_ids = [
        f"fact-syn-{((ordinal - 1) * 8 + index):03d}" for index in range(1, 9)
    ]
    conflict_fact_id = f"conflict-fact-syn-{suffix}"
    predicates = [row[0] for row in source["predicate_rows"]]
    facts = [
        _fact_row(
            fact_ids[0], predicates[0], project_or_case_id,
            {"entity_id": owner_id, "kind": "entity-reference"}, "stable-current",
            source,
        ),
        _fact_row(
            fact_ids[1], predicates[1], contact_id,
            {
                "kind": "email",
                "value": (
                    f"contact-syn-{suffix}@"
                    f"{project_or_case_id.rsplit('-syn-', 1)[0]}-syn-{suffix}.invalid"
                ),
            },
            "stable-current",
            source,
        ),
        _fact_row(
            fact_ids[2], predicates[2], endpoint_id,
            {"kind": "documentation-ip", "value": f"192.0.2.{ordinal}"},
            "stable-current", source,
        ),
        _fact_row(
            fact_ids[3], predicates[3], project_or_case_id,
            {"kind": "synthetic-token", "token_id": f"draft-syn-{suffix}"},
            "superseded-after-W1", source,
        ),
        _fact_row(
            fact_ids[4], predicates[3], project_or_case_id,
            {"kind": "synthetic-token", "token_id": f"approved-syn-{suffix}"},
            "introduced-at-W1", source,
        ),
        _fact_row(
            fact_ids[5], predicates[4], project_or_case_id,
            {"kind": "unsigned-integer", "value": (ordinal - 1) % 5 + 1},
            "stable-current", source,
        ),
        _fact_row(
            fact_ids[6], predicates[5], project_or_case_id,
            {
                "kind": "scaled-integer",
                "scale": 2,
                "unit_id": source["measure_unit_id"],
                "units": ordinal * 100_000,
            },
            "stable-current",
            source,
        ),
        _fact_row(
            fact_ids[7], predicates[6], project_or_case_id,
            {
                "direction": "after",
                "kind": "logical-day-offset",
                "magnitude": ordinal,
                "reference_instant_id": source["reference_instant_id"],
            },
            "stable-current",
            source,
        ),
        _fact_row(
            conflict_fact_id, predicates[4], project_or_case_id,
            {"kind": "unsigned-integer", "value": (ordinal - 1) % 5 + 101},
            "stable-current", source,
        ),
    ]
    return {
        "conflict_sets": [
            {
                "conflict_set_id": f"conflict-set-syn-{suffix}",
                "member_fact_ids": sorted((fact_ids[5], conflict_fact_id)),
                "required_current_checkpoint": "W0",
            }
        ],
        "entities": [
            {"entity_id": project_or_case_id, "entity_type": "project-or-case"},
            {"entity_id": owner_id, "entity_type": "synthetic-owner-unit"},
            {"entity_id": contact_id, "entity_type": "synthetic-contact"},
            {"entity_id": endpoint_id, "entity_type": "synthetic-endpoint"},
        ],
        "fact_edges": [
            {
                "edge_id": f"revision-edge-syn-{suffix}",
                "from_fact_id": fact_ids[3],
                "relation_kind": "superseded-by",
                "to_fact_id": fact_ids[4],
            }
        ],
        "facts": facts,
        "graph_id": graph_id,
        "graph_kind": graph_kind,
        "project_or_case_id": project_or_case_id,
        "revision_chains": [
            {
                "current_fact_id": fact_ids[4],
                "prior_fact_ids": [fact_ids[3]],
                "revision_chain_id": f"revision-syn-{suffix}",
            }
        ],
        "semantic_language_mode": "language-neutral-typed-facts",
    }


def _fact_theme_map(source):
    theme_rows = source["graph_theme_rows"]
    if type(theme_rows) is not tuple or len(theme_rows) != 20:
        _fail("fact theme source cardinality drifted")
    result = {}
    ordinal = 1
    for persona_id, themes in theme_rows:
        if persona_id not in envelope.PERSONA_IDS or len(themes) != 4:
            _fail("fact theme persona/graph cardinality drifted")
        result[persona_id] = []
        for project_or_case_id, graph_kind in themes:
            result[persona_id].append((project_or_case_id, graph_kind, ordinal))
            ordinal += 1
    if tuple(result) != tuple(envelope.PERSONA_IDS) or ordinal != 81:
        _fail("fact theme suite order drifted")
    return result


def _fact_shared_state():
    fact_source = _validate_fact_data_contract()
    values = (
        envelope.build_envelope_contract(),
        topology.build_topology_contract(),
        joint_problem.build_joint_problem(),
        solver_policy.build_joint_solver_policy(),
        realism.build_realism_profile(),
    )
    validators = (
        envelope.validate_envelope_contract,
        topology.validate_topology_contract,
        joint_problem.validate_joint_problem,
        solver_policy.validate_joint_solver_policy,
        realism.validate_realism_profile,
    )
    canonicalizers = (
        envelope.canonical_json_bytes,
        topology.canonical_json_bytes,
        joint_problem.canonical_json_bytes,
        solver_policy.canonical_json_bytes,
        realism.canonical_json_bytes,
    )
    snapshots = []
    raws = []
    for value, validate, canonical in zip(
        values, validators, canonicalizers, strict=True
    ):
        snapshot, raw = _validated_value_raw(
            value,
            validate=validate,
            canonical=canonical,
            label=value["artifact_kind"],
        )
        snapshots.append(snapshot)
        raws.append(raw)
    binding_names = (
        "envelope",
        "topology",
        "joint-problem",
        "joint-solver-policy",
    )
    bindings = [
        {
            "artifact_kind": value["artifact_kind"],
            "artifact_schema": value["artifact_schema"],
            "artifact_schema_version": value["artifact_schema_version"],
            "canonical_bytes": len(raw),
            "fixture_id": value["fixture_id"],
            "fixture_schema_version": value["fixture_schema_version"],
            "name": name,
            "sha256": _sha256(raw),
        }
        for name, value, raw in zip(
            binding_names, snapshots[:4], raws[:4], strict=True
        )
    ]
    if snapshots[4].get("input_bindings") != bindings:
        _fail("realism owner does not bind the exact reconstructed core owners")
    realism_binding = {
        "artifact_kind": snapshots[4]["artifact_kind"],
        "artifact_schema": snapshots[4]["artifact_schema"],
        "artifact_schema_version": snapshots[4]["artifact_schema_version"],
        "canonical_bytes": len(raws[4]),
        "fixture_id": snapshots[4]["fixture_id"],
        "fixture_schema_version": snapshots[4]["fixture_schema_version"],
        "name": "realism-profile",
        "sha256": _sha256(raws[4]),
    }
    return {
        "bindings": [*bindings, realism_binding],
        "fact_source": fact_source,
        "personas": {
            row["persona_id"]: row for row in snapshots[0]["personas"]
        },
        "profiles": {
            row["persona_id"]: row for row in snapshots[4]["personas"]
        },
        "raws": tuple(raws),
        "snapshots": tuple(snapshots),
        "themes": _fact_theme_map(fact_source),
    }


def _expected_full_fact_graph(persona_id, shared):
    profile = shared["profiles"][persona_id]
    persona = shared["personas"][persona_id]
    fact_source = shared["fact_source"]
    graphs = [
        _fact_graph(*row, fact_source) for row in shared["themes"][persona_id]
    ]
    graph_count = len(graphs)
    return {
        "artifact_kind": "persona-pc-v2-fact-graph",
        "artifact_schema": "kio.persona.pc-fact-graph/v2",
        "artifact_schema_version": 2,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kio_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": 2**20,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_scope": (
            "typed-authored-fact-graph-inventory-only-no-membership-no-surface-"
            "no-evaluation-oracle-no-solver-no-g0"
        ),
        "eligible_languages": [row["language"] for row in profile["language_weights_bp"]],
        "unordered_w0_current_fact_pair_inventory_complete": True,
        "fact_graph_input_leaf_complete": True,
        "fact_graph_inventory_complete": True,
        "fact_oracle_input_closure_complete": False,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "graphs": graphs,
        "history_intent_recipe_bound": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-records",
        "input_bindings": copy.deepcopy(shared["bindings"]),
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "live_sync_allowed": False,
            "network_access_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "logical_time_contract": _fact_logical_time(fact_source),
        "persona_id": persona_id,
        "persona_realism_profile_id": profile["profile_id"],
        "predicate_catalog": _fact_predicate_catalog(fact_source),
        "remaining_blockers": [
            "source-intent-recipe-not-bound",
            "semantic-oracle-not-present",
            "query-intent-not-present",
            "fact-oracle-persona-input-closure-not-present",
            "bounded-framed-loader-not-implemented",
            "joint-source-intent-refinement-not-proved",
        ],
        "role": persona["role"],
        "semantic_surface_text_present": False,
        "source_intent_recipe_bound": False,
        "summary": {
            "conflict_set_count": graph_count,
            "edge_count": graph_count,
            "entity_count": graph_count * 4,
            "fact_count": graph_count * 9,
            "graph_count": graph_count,
            "revision_chain_count": graph_count,
        },
    }


def _project_fact(value):
    return {
        "artifact_kind": FACT_KIND,
        "artifact_schema": FACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "graphs": copy.deepcopy(value["graphs"]),
        "logical_time_contract": copy.deepcopy(value["logical_time_contract"]),
        "persona_id": value["persona_id"],
        "predicate_catalog": copy.deepcopy(value["predicate_catalog"]),
    }


def _fact_material(persona_id, shared):
    full_value = _expected_full_fact_graph(persona_id, shared)
    full_raw = _canonical(
        full_value, label="independently reconstructed fact graph", maximum=2**20
    )
    projection = _project_fact(full_value)
    body = _canonical_projection(projection)
    if len(body) > TARGET_FACT_BYTES:
        _fail("fact projection exceeds its target")
    shared_names = (
        "envelope",
        "topology",
        "joint-problem",
        "joint-solver-policy",
        "realism-profile",
    )
    owners = [
        _owner_pin(
            full_value, full_raw, coordinates={"persona_id": persona_id},
            owner_id=f"persona-v2-fact-graph-{persona_id}",
            owner_role="full-persona-fact-graph-owner-pin",
        )
    ]
    for name, value, raw in zip(
        shared_names, shared["snapshots"], shared["raws"], strict=True
    ):
        owners.append(
            _owner_pin(
                value, raw, coordinates={}, owner_id=f"persona-v2-{name}",
                owner_role=f"full-{name}-owner-pin",
            )
        )
    direct = [
        _direct_pin(
            _canonical_fragment(binding, label="fact graph input binding"),
            direct_pin_id=f"fact-graph-{persona_id}-{binding['name']}-binding",
            direct_pin_role=f"fact-graph-{binding['name']}-binding-row",
        )
        for binding in full_value["input_bindings"]
    ]
    for field, role in (
        ("graphs", "fact-graph-content-section"),
        ("logical_time_contract", "fact-graph-logical-time-section"),
        ("predicate_catalog", "fact-graph-predicate-section"),
    ):
        direct.append(
            _direct_pin(
                _canonical_fragment(full_value[field], label=f"fact graph {field}"),
                direct_pin_id=f"fact-graph-{persona_id}-{field}",
                direct_pin_role=role,
            )
        )
    return _material(
        class_id=FACT_CLASS_ID,
        coordinates={"persona_id": persona_id},
        artifact_kind=FACT_KIND,
        artifact_schema=FACT_SCHEMA,
        body=body,
        full_owner_pins=owners,
        direct_body_pins=direct,
    )


def iter_expected_corpus_content_projection_materials():
    """Yield freshly authenticated expected materials in exact 22-body order."""

    try:
        yield _primary_material()
        yield _recipe_material()
        shared = _fact_shared_state()
        for persona_id in envelope.PERSONA_IDS:
            yield _fact_material(persona_id, shared)
    except PersonaV2SemanticProjectionCorpusContentValidationError:
        raise
    except Exception as error:
        raise PersonaV2SemanticProjectionCorpusContentValidationError(
            "projection owner rebuild failed"
        ) from error


def _expected_material(class_id, coordinates):
    if type(class_id) is not str or type(coordinates) is not dict:
        _fail("projection class/coordinates require exact built-in types")
    if any(type(key) is not str for key in coordinates):
        _fail("projection coordinate keys must be exact built-in strings")
    try:
        if (
            class_id == PRIMARY_CLASS_ID
            and set(coordinates) == {"scope"}
            and type(coordinates["scope"]) is str
            and coordinates["scope"] == "suite"
        ):
            return _primary_material()
        if (
            class_id == RECIPE_CLASS_ID
            and set(coordinates) == {"scope"}
            and type(coordinates["scope"]) is str
            and coordinates["scope"] == "suite"
        ):
            return _recipe_material()
        if (
            class_id == FACT_CLASS_ID
            and type(coordinates) is dict
            and set(coordinates) == {"persona_id"}
            and coordinates["persona_id"] in envelope.PERSONA_IDS
        ):
            return _fact_material(coordinates["persona_id"], _fact_shared_state())
        _fail("projection class/coordinates are outside the exact 22-body package")
    except PersonaV2SemanticProjectionCorpusContentValidationError:
        raise
    except Exception as error:
        raise PersonaV2SemanticProjectionCorpusContentValidationError(
            "projection owner rebuild failed"
        ) from error


def _reject_forbidden_keys(value, path=()):
    if type(value) is dict:
        for key, item in value.items():
            folded = key.replace("_", "-").lower()
            tokens = set(folded.split("-"))
            current_path = path + (key,)
            if current_path not in ALLOWED_SEMANTIC_RUNTIME_PATHS and (
                folded in FORBIDDEN_KEY_TOKENS
                or tokens & FORBIDDEN_KEY_TOKENS
            ):
                _fail("projection leaked forbidden metadata at " + ".".join(path + (key,)))
            if key == "sha256" or key.endswith("_sha256"):
                _fail("projection leaked an owner/runtime digest")
            _reject_forbidden_keys(item, path + (key,))
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_forbidden_keys(item, path + (str(index),))


def _parse_projection_body(body, *, expected_schema):
    caps = {
        PRIMARY_SCHEMA: MAX_PRIMARY_BYTES,
        RECIPE_SCHEMA: MAX_RECIPE_BYTES,
        FACT_SCHEMA: MAX_FACT_BYTES,
    }
    cap = caps[expected_schema]
    if type(body) is not bytes or not body or len(body) > cap:
        _fail("projection body violates exact bytes/nonempty/class-cap boundary")
    value = _strict_loads(body, label="projection body")
    if type(value) is not dict or value.get("artifact_schema") != expected_schema:
        _fail("projection body schema drifted")
    raw = _canonical(value, label="projection body", maximum=cap)
    if not hmac.compare_digest(raw, body):
        _fail("projection body is not canonical JSON")
    expected_fields = {
        PRIMARY_SCHEMA: PRIMARY_TOP_FIELDS,
        RECIPE_SCHEMA: RECIPE_TOP_FIELDS,
        FACT_SCHEMA: FACT_TOP_FIELDS,
    }[expected_schema]
    if set(value) != expected_fields:
        _fail("projection top-level field schema drifted")
    _reject_forbidden_keys(value)
    return value


def validate_projection_body(class_id, coordinates, body):
    """Validate one body and freshly reauthenticate its full/direct owners."""

    if type(class_id) is not str or type(coordinates) is not dict:
        _fail("projection body dispatch requires exact class/coordinate types")
    if any(type(key) is not str for key in coordinates):
        _fail("projection body coordinate keys must be exact strings")
    if any(type(value) is not str for value in coordinates.values()):
        _fail("projection body coordinate values must be exact strings")
    coordinate_opening_raw = _canonical(
        coordinates,
        label="projection body coordinates",
        maximum=1024,
    )
    coordinate_snapshot = _strict_loads(
        coordinate_opening_raw, label="projection body coordinates"
    )
    if type(coordinate_snapshot) is not dict:
        _fail("projection body coordinates must decode to an object")
    expected = None
    try:
        expected = _expected_material(class_id, coordinate_snapshot)
        if type(body) is not bytes:
            _fail("projection body must be exact built-in bytes")
        _parse_projection_body(body, expected_schema=expected["artifact_schema"])
        if not hmac.compare_digest(body, expected["bytes"]):
            _fail("projection body differs from independent reconstruction")
    finally:
        coordinate_closing_raw = _canonical(
            coordinates,
            label="projection body coordinates",
            maximum=1024,
        )
        if not hmac.compare_digest(
            coordinate_opening_raw, coordinate_closing_raw
        ):
            _fail("projection body coordinates mutated during validation")
        if expected is not None:
            closing = _expected_material(class_id, coordinate_snapshot)
            if not _strict_equal(closing, expected):
                _fail("projection owners/direct fragments changed during validation")
    return True


def _validate_projection_value(value, *, class_id, coordinates, maximum, label):
    snapshot, opening_raw = _opening_snapshot(value, label=label, maximum=maximum)
    try:
        validate_projection_body(class_id, coordinates, opening_raw)
    finally:
        _reauth_target(value, opening_raw, label=label, maximum=maximum)
    return True


def validate_primary_use_case_corpus_content_projection(value):
    return _validate_projection_value(
        value,
        class_id=PRIMARY_CLASS_ID,
        coordinates=PRIMARY_COORDINATES,
        maximum=MAX_PRIMARY_BYTES,
        label="primary-use-case corpus projection",
    )


def validate_recipe_content_filename_policy_content_projection(value):
    return _validate_projection_value(
        value,
        class_id=RECIPE_CLASS_ID,
        coordinates=RECIPE_COORDINATES,
        maximum=MAX_RECIPE_BYTES,
        label="recipe/content/filename projection",
    )


def validate_fact_graph_content_projection(persona_id, value):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("fact projection persona is outside the exact suite")
    return _validate_projection_value(
        value,
        class_id=FACT_CLASS_ID,
        coordinates={"persona_id": persona_id},
        maximum=MAX_FACT_BYTES,
        label="fact-graph content projection",
    )


def _require_sha(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} is not one lowercase SHA-256 digest")


def _validate_pin(pin, *, owner):
    fields = FULL_OWNER_PIN_FIELDS if owner else DIRECT_PIN_FIELDS
    if type(pin) is not dict or set(pin) != fields:
        _fail("projection material pin field schema drifted")
    if pin.get("body_framing") != BODY_FRAMING:
        _fail("projection material pin framing drifted")
    size = pin.get("canonical_bytes")
    if type(size) is not int or type(size) is bool or not 0 < size <= MAX_FRAGMENT_BYTES:
        _fail("projection material pin size is invalid")
    _require_sha(pin.get("sha256"), label="projection material pin")
    if owner:
        if (
            type(pin.get("coordinates")) is not dict
            or type(pin.get("owner_id")) is not str
            or not pin["owner_id"]
            or type(pin.get("owner_role")) is not str
            or not pin["owner_role"]
            or type(pin.get("artifact_schema_version")) is not int
            or type(pin.get("artifact_schema_version")) is bool
        ):
            _fail("full owner pin identity is invalid")
    else:
        if (
            type(pin.get("direct_pin_id")) is not str
            or not pin["direct_pin_id"]
            or type(pin.get("direct_pin_role")) is not str
            or not pin["direct_pin_role"]
        ):
            _fail("direct fragment pin identity is invalid")


def _validate_material_identity_and_body(material, body):
    class_id = material.get("class_id")
    if type(class_id) is not str:
        _fail("projection material class must be an exact string")
    contracts = {
        PRIMARY_CLASS_ID: (
            PRIMARY_KIND,
            PRIMARY_SCHEMA,
            PRIMARY_COORDINATES,
            MAX_PRIMARY_BYTES,
        ),
        RECIPE_CLASS_ID: (
            RECIPE_KIND,
            RECIPE_SCHEMA,
            RECIPE_COORDINATES,
            MAX_RECIPE_BYTES,
        ),
        FACT_CLASS_ID: (FACT_KIND, FACT_SCHEMA, None, MAX_FACT_BYTES),
    }
    if class_id not in contracts:
        _fail("projection material class is outside the exact package")
    expected_kind, expected_schema, expected_coordinates, cap = contracts[class_id]
    coordinates = material.get("coordinates")
    if type(coordinates) is not dict:
        _fail("projection material coordinates must be an exact object")
    if any(type(key) is not str for key in coordinates):
        _fail("projection material coordinate keys must be exact strings")
    if class_id == FACT_CLASS_ID:
        if (
            set(coordinates) != {"persona_id"}
            or type(coordinates["persona_id"]) is not str
            or coordinates["persona_id"] not in envelope.PERSONA_IDS
        ):
            _fail("fact projection material coordinates drifted")
    elif (
        set(coordinates) != {"scope"}
        or type(coordinates["scope"]) is not str
        or coordinates != expected_coordinates
    ):
        _fail("global projection material coordinates drifted")
    if (
        type(material.get("artifact_kind")) is not str
        or material["artifact_kind"] != expected_kind
        or type(material.get("artifact_schema")) is not str
        or material["artifact_schema"] != expected_schema
        or type(material.get("artifact_schema_version")) is not int
        or type(material["artifact_schema_version"]) is bool
        or material["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or type(material.get("framing")) is not str
        or material["framing"] != BODY_FRAMING
    ):
        _fail("projection material identity/framing drifted")
    if type(body) is not bytes or not body or len(body) > cap:
        _fail("projection material body violates its class byte cap")


def _snapshot_material(material):
    if type(material) is not dict or set(material) != MATERIAL_FIELDS:
        _fail("projection provider returned an invalid material schema")
    body = material.get("bytes")
    _validate_material_identity_and_body(material, body)
    owners = material.get("full_owner_pins")
    direct = material.get("direct_body_pins")
    if (
        type(owners) is not list
        or not owners
        or len(owners) > MAX_FULL_OWNER_PINS
        or type(direct) is not list
        or not direct
        or len(direct) > MAX_DIRECT_BODY_PINS
    ):
        _fail("projection material owner/direct pin cardinality is invalid")
    for pin in owners:
        _validate_pin(pin, owner=True)
    for pin in direct:
        _validate_pin(pin, owner=False)
    metadata = {key: value for key, value in material.items() if key != "bytes"}
    metadata_raw = _canonical(
        metadata,
        label="projection material metadata",
        maximum=MAX_MATERIAL_METADATA_BYTES,
    )
    detached = _strict_loads(metadata_raw, label="projection material metadata")
    detached["bytes"] = body
    return detached, metadata_raw, body


def _call_material_provider(provider, *, replay):
    try:
        result = provider()
        iterator = iter(result)
    except Exception as error:
        raise PersonaV2SemanticProjectionCorpusContentValidationError(
            "projection material provider failed" + (" during replay" if replay else "")
        ) from error
    snapshots = []
    originals = []
    fingerprints = []
    for index in range(EXPECTED_MATERIAL_COUNT + 1):
        try:
            item = next(iterator)
        except StopIteration:
            break
        except Exception as error:
            raise PersonaV2SemanticProjectionCorpusContentValidationError(
                "projection material provider failed during iteration"
                + (" on replay" if replay else "")
            ) from error
        if index == EXPECTED_MATERIAL_COUNT:
            _fail("projection material provider exceeded the exact 22-body cap")
        snapshot, metadata_raw, body = _snapshot_material(item)
        snapshots.append(snapshot)
        originals.append(item)
        fingerprints.append((metadata_raw, body))
    if len(snapshots) != EXPECTED_MATERIAL_COUNT:
        _fail("projection material provider must return exactly 22 bodies")
    return snapshots, originals, fingerprints


def _reauth_provider_materials(originals, fingerprints):
    for material, (metadata_raw, body) in zip(originals, fingerprints, strict=True):
        try:
            snapshot, closing_metadata, closing_body = _snapshot_material(material)
        except PersonaV2SemanticProjectionCorpusContentValidationError as error:
            raise PersonaV2SemanticProjectionCorpusContentValidationError(
                "projection material mutated during validation"
            ) from error
        del snapshot
        if not hmac.compare_digest(metadata_raw, closing_metadata) or not hmac.compare_digest(
            body, closing_body
        ):
            _fail("projection material mutated during validation")


def _compare_materials(actual, expected):
    if len(actual) != len(expected):
        _fail("projection material count drifted")
    for candidate, reference in zip(actual, expected, strict=True):
        if not _strict_equal(candidate, reference):
            _fail("projection material differs from independent reconstruction")
        _parse_projection_body(
            candidate["bytes"], expected_schema=reference["artifact_schema"]
        )


def _fresh_expected_materials():
    materials = list(iter_expected_corpus_content_projection_materials())
    if len(materials) != EXPECTED_MATERIAL_COUNT:
        _fail("independent material reconstruction cardinality drifted")
    coordinates = [
        (row["class_id"], json.dumps(row["coordinates"], sort_keys=True))
        for row in materials
    ]
    if len(set(coordinates)) != EXPECTED_MATERIAL_COUNT:
        _fail("independent projection material coordinates are not unique")
    return materials


def _reauthenticate_against(opening_materials):
    closing_materials = _fresh_expected_materials()
    _compare_materials(closing_materials, opening_materials)
    return True


def reauthenticate_all_projection_owners():
    """Freshly rebuild every owner/fragment twice and bind both images."""

    opening_materials = _fresh_expected_materials()
    _reauthenticate_against(opening_materials)
    return True


def validate_corpus_content_projection_materials(material_provider):
    """Validate exact 22 materials, two provider replays, and all owners."""

    if not callable(material_provider):
        _fail("projection material provider must be callable")
    expected = _fresh_expected_materials()
    first_originals = first_fingerprints = None
    replay_originals = replay_fingerprints = None
    try:
        first, first_originals, first_fingerprints = _call_material_provider(
            material_provider, replay=False
        )
        _compare_materials(first, expected)
        _reauth_provider_materials(first_originals, first_fingerprints)
        _reauthenticate_against(expected)
        replay, replay_originals, replay_fingerprints = _call_material_provider(
            material_provider, replay=True
        )
        _compare_materials(replay, expected)
        if not _strict_equal(first, replay):
            _fail("projection material provider replay is nondeterministic")
        _reauth_provider_materials(replay_originals, replay_fingerprints)
    finally:
        if first_originals is not None:
            _reauth_provider_materials(first_originals, first_fingerprints)
        if replay_originals is not None:
            _reauth_provider_materials(replay_originals, replay_fingerprints)
        _reauthenticate_against(expected)
    return True


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "BODY_FRAMING",
    "CLASS_ORDER",
    "DIRECT_PIN_FIELDS",
    "EXPECTED_MATERIAL_COUNT",
    "FACT_CLASS_ID",
    "FACT_KIND",
    "FACT_SCHEMA",
    "FULL_OWNER_PIN_FIELDS",
    "MATERIAL_FIELDS",
    "MAX_FACT_BYTES",
    "MAX_PRIMARY_BYTES",
    "MAX_RECIPE_BYTES",
    "PRIMARY_CLASS_ID",
    "PRIMARY_KIND",
    "PRIMARY_SCHEMA",
    "PersonaV2SemanticProjectionCorpusContentValidationError",
    "RECIPE_CLASS_ID",
    "RECIPE_KIND",
    "RECIPE_SCHEMA",
    "TARGET_FACT_BYTES",
    "TARGET_PRIMARY_BYTES",
    "TARGET_RECIPE_BYTES",
    "iter_expected_corpus_content_projection_materials",
    "reauthenticate_all_projection_owners",
    "validate_corpus_content_projection_materials",
    "validate_fact_graph_content_projection",
    "validate_primary_use_case_corpus_content_projection",
    "validate_projection_body",
    "validate_recipe_content_filename_policy_content_projection",
]
