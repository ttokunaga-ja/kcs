"""Content-only semantic projections for three Persona-PC v2 classes.

This module derives twenty-two external canonical JSON bodies from already
frozen planning artifacts:

* one primary-use-case corpus half (the query half is excluded),
* one 71-row recipe/content/filename policy dictionary, and
* twenty persona fact-graph content bodies.

The returned materials are derivation inputs for a future complete semantic
projection inventory.  They are not that inventory, do not alter Decision 150's
exact 113-body artifact, and grant no namespace, solver, G0, or write authority.
Only immutable canonical bytes are cached; every public object is detached.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_formal_source_recipe_catalog as recipe_catalog
    from . import persona_v2_format_implementation_registry as format_registry
    from . import persona_v2_joint_problem as joint_problem
    from . import persona_v2_joint_solver_policy as solver_policy
    from . import persona_v2_primary_use_case_catalog as use_case_catalog
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_source_inventory_profile as inventory_profile
    from . import persona_v2_topology as topology
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_formal_source_recipe_catalog as recipe_catalog
    import persona_v2_format_implementation_registry as format_registry
    import persona_v2_joint_problem as joint_problem
    import persona_v2_joint_solver_policy as solver_policy
    import persona_v2_primary_use_case_catalog as use_case_catalog
    import persona_v2_realism_profile as realism
    import persona_v2_source_inventory_profile as inventory_profile
    import persona_v2_topology as topology
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA_VERSION = 1
BODY_FRAMING = "canonical-json"

PRIMARY_CLASS_ID = "primary-use-case-corpus-half"
RECIPE_CLASS_ID = "recipe-content-filename-policy"
FACT_CLASS_ID = "fact-graph"
CLASS_ORDER = (PRIMARY_CLASS_ID, RECIPE_CLASS_ID, FACT_CLASS_ID)

PRIMARY_SCHEMA = (
    "kcs.persona.pc-primary-use-case-corpus-content-projection/v1"
)
PRIMARY_KIND = "persona-pc-v2-primary-use-case-corpus-content-projection"
RECIPE_SCHEMA = (
    "kcs.persona.pc-recipe-content-filename-policy-content-projection/v1"
)
RECIPE_KIND = "persona-pc-v2-recipe-content-filename-policy-content-projection"
FACT_SCHEMA = "kcs.persona.pc-fact-graph-content-projection/v1"
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
EXPECTED_MATERIAL_COUNT = 22

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
    "expected_kcs_path_media_type",
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


class PersonaV2SemanticProjectionCorpusContentError(ValueError):
    """Raised when a bounded content projection or its evidence is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionCorpusContentError(message)


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


def _decoded(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not canonical JSON: {error}")
    if type(value) is not dict:
        _fail(f"{label} must decode to an object")
    return value


def canonical_json_bytes(value):
    """Canonicalize exactly one of this module's three projection schemas."""

    if type(value) is not dict:
        _fail("corpus content projection must be an object")
    schema = value.get("artifact_schema")
    limits = {
        PRIMARY_SCHEMA: ("primary-use-case corpus projection", MAX_PRIMARY_BYTES),
        RECIPE_SCHEMA: ("recipe/content/filename projection", MAX_RECIPE_BYTES),
        FACT_SCHEMA: ("fact-graph content projection", MAX_FACT_BYTES),
    }
    if schema not in limits:
        _fail("corpus content projection uses an unknown schema")
    label, maximum = limits[schema]
    return _canonical(value, label=label, maximum=maximum)


def _canonical_fragment(value, *, label):
    return _canonical(value, label=label, maximum=MAX_FRAGMENT_BYTES)


def _require_true(result, *, label):
    if result is not True:
        _fail(f"{label} validator did not return exact True")


def _owner_pin(value, raw, *, coordinates, owner_id, owner_role):
    if type(value) is not dict or type(raw) is not bytes or not raw:
        _fail("full owner pins require an exact object and nonempty bytes")
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
    if type(raw) is not bytes or not raw:
        _fail("direct fragment pins require nonempty exact built-in bytes")
    return {
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": _sha256(raw),
    }


def _material(
    *,
    class_id,
    coordinates,
    artifact_kind,
    artifact_schema,
    body,
    full_owner_pins,
    direct_body_pins,
):
    if type(body) is not bytes or not body:
        _fail("projection materials require nonempty exact built-in bytes")
    value = {
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
    if set(value) != MATERIAL_FIELDS:
        _fail("projection material field schema drifted")
    return value


def _validated_raw(value, *, validate, canonical, label):
    opening_raw = canonical(value)
    if type(opening_raw) is not bytes or not opening_raw:
        _fail(f"{label} canonicalizer violated its byte contract")
    snapshot = _decoded(opening_raw, label=f"{label} opening body")
    _require_true(validate(snapshot), label=label)
    snapshot_closing_raw = canonical(snapshot)
    closing_raw = canonical(value)
    if (
        type(snapshot_closing_raw) is not bytes
        or not hmac.compare_digest(opening_raw, snapshot_closing_raw)
    ):
        _fail(f"{label} validator mutated its detached opening body")
    if (
        type(closing_raw) is not bytes
        or not hmac.compare_digest(opening_raw, closing_raw)
    ):
        _fail(f"{label} mutated during validation")
    return opening_raw


@functools.lru_cache(maxsize=1)
def _primary_owner_raws():
    catalog = use_case_catalog.build_primary_use_case_catalog()
    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    catalog_raw = _validated_raw(
        catalog,
        validate=use_case_catalog.validate_primary_use_case_catalog,
        canonical=use_case_catalog.canonical_json_bytes,
        label="primary-use-case catalog",
    )
    envelope_raw = _validated_raw(
        envelope_value,
        validate=envelope.validate_envelope_contract,
        canonical=envelope.canonical_json_bytes,
        label="envelope",
    )
    topology_raw = _validated_raw(
        topology_value,
        validate=topology.validate_topology_contract,
        canonical=topology.canonical_json_bytes,
        label="topology",
    )
    return catalog_raw, envelope_raw, topology_raw


def _primary_projection_value(catalog):
    rows = []
    for row in catalog["primary_use_cases"]:
        projected = {field: copy.deepcopy(row[field]) for field in PRIMARY_ROW_FIELDS}
        if set(projected) != set(PRIMARY_ROW_FIELDS):
            _fail("primary-use-case corpus row schema drifted")
        rows.append(projected)
    if (
        len(rows) != 20
        or [row["persona_id"] for row in rows] != list(envelope.PERSONA_IDS)
        or len({row["primary_use_case_id"] for row in rows}) != 20
    ):
        _fail("primary-use-case corpus projection cardinality/order drifted")
    return {
        "artifact_kind": PRIMARY_KIND,
        "artifact_schema": PRIMARY_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": catalog["fixture_id"],
        "fixture_schema_version": catalog["fixture_schema_version"],
        "primary_use_case_rows": rows,
    }


@functools.lru_cache(maxsize=1)
def _primary_projection_raw():
    catalog = _decoded(_primary_owner_raws()[0], label="primary-use-case owner")
    raw = canonical_json_bytes(_primary_projection_value(catalog))
    if len(raw) > TARGET_PRIMARY_BYTES:
        _fail("primary-use-case corpus projection exceeds its 16-KiB target")
    return raw


def build_primary_use_case_corpus_content_projection():
    return _decoded(_primary_projection_raw(), label="primary-use-case projection")


def _copy_fields(value, fields, *, label):
    if type(value) is not dict or any(field not in value for field in fields):
        _fail(f"{label} lacks a required source field")
    return {field: copy.deepcopy(value[field]) for field in fields}


def _project_chunk_policy(row):
    value = copy.deepcopy(row)
    for field in ("expected_incidental_chunks_upper", "requested_chunks"):
        nested = value.get(field)
        if type(nested) is not dict or "selected_value_present" not in nested:
            _fail("recipe chunk policy selected-value boundary drifted")
        del nested["selected_value_present"]
    return value


def _project_policy_catalogs(policy_catalogs):
    if type(policy_catalogs) is not dict or set(policy_catalogs) != {
        "dynamic_incidental_wave_cap_policy",
        "filename_core_policy",
        "gate_role_chunk_policies",
        "lane_contracts",
    }:
        _fail("formal recipe policy catalog schema drifted")
    dynamic = copy.deepcopy(policy_catalogs["dynamic_incidental_wave_cap_policy"])
    for field in ("observed_values_present", "source_instance_assignments_present"):
        if field not in dynamic:
            _fail("dynamic incidental policy status boundary drifted")
        del dynamic[field]
    lane_contracts = copy.deepcopy(policy_catalogs["lane_contracts"])
    byte_stress = lane_contracts.get("byte_stress")
    if type(byte_stress) is not dict:
        _fail("recipe lane policy lacks byte-stress semantics")
    byte_stress.pop("projection_is_not_a_formal_variant_source_row", None)
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
        "lane_contracts": lane_contracts,
    }


def _project_recipe_row(row):
    projected = _copy_fields(
        row,
        RECIPE_ROW_SCALAR_FIELDS,
        label="formal recipe row",
    )
    chunk_policy = row.get("chunk_policy")
    if type(chunk_policy) is not dict or type(chunk_policy.get("policy_id")) is not str:
        _fail("formal recipe row lacks its chunk-policy identity")
    projected["chunk_policy_id"] = chunk_policy["policy_id"]

    complexity = _copy_fields(
        row.get("complexity_byte_policy"),
        RECIPE_COMPLEXITY_FIELDS,
        label="complexity/byte policy",
    )
    complexity["lane"] = _copy_fields(
        complexity["lane"],
        RECIPE_LANE_FIELDS,
        label="complexity lane",
    )
    complexity["parameter_shape"] = _copy_fields(
        complexity["parameter_shape"],
        RECIPE_PARAMETER_SHAPE_FIELDS,
        label="complexity parameter shape",
    )
    projected["complexity_byte_policy"] = complexity
    projected["content_policy"] = _copy_fields(
        row.get("content_policy"),
        RECIPE_CONTENT_FIELDS,
        label="content policy",
    )
    projected["filename_policy"] = _copy_fields(
        row.get("filename_policy"),
        RECIPE_FILENAME_FIELDS,
        label="filename policy",
    )
    implementation = row.get("implementation_binding")
    renderer = implementation.get("renderer") if type(implementation) is dict else None
    if type(renderer) is not dict:
        _fail("formal recipe row lacks renderer semantic identity")
    projected["renderer_policy"] = {
        "implementation_pair_id": implementation["implementation_pair_id"],
        "implementation_profile_id": implementation["implementation_profile_id"],
        "renderer_id": renderer["renderer_id"],
        "renderer_schema_version": renderer["renderer_schema_version"],
    }
    return projected


@functools.lru_cache(maxsize=1)
def _recipe_owner_raws():
    catalog = recipe_catalog.build_formal_source_recipe_catalog()
    catalog_raw = _validated_raw(
        catalog,
        validate=recipe_catalog.validate_formal_source_recipe_catalog,
        canonical=recipe_catalog.canonical_json_bytes,
        label="formal source recipe catalog",
    )
    dependencies = (
        variant_catalog.build_variant_catalog(),
        inventory_profile.build_source_inventory_profile_catalog(),
        format_registry.build_format_implementation_registry(),
        recipe_catalog._source_semantic_catalog_dependency(),
    )
    canonicalizers = (
        variant_catalog.canonical_json_bytes,
        inventory_profile.canonical_json_bytes,
        format_registry.canonical_json_bytes,
        recipe_catalog.semantic_catalog.canonical_json_bytes,
    )
    validators = (
        variant_catalog.validate_variant_catalog,
        inventory_profile.validate_source_inventory_profile_catalog,
        format_registry.validate_format_implementation_registry,
        recipe_catalog.semantic_catalog.validate_source_semantic_membership_catalog,
    )
    dependency_raws = tuple(
        _validated_raw(
            value,
            validate=validate,
            canonical=canonical,
            label=value["artifact_kind"],
        )
        for value, validate, canonical in zip(
            dependencies, validators, canonicalizers, strict=True
        )
    )
    binding_by_name = {row["name"]: row for row in catalog["input_bindings"]}
    names = (
        "persona-v2-variant-catalog",
        "persona-v2-source-inventory-profile-catalog",
        "persona-v2-format-implementation-registry",
        "persona-v2-source-semantic-membership-catalog",
    )
    for name, value, raw in zip(names, dependencies, dependency_raws, strict=True):
        binding = binding_by_name.get(name)
        if (
            type(binding) is not dict
            or binding.get("artifact_schema") != value["artifact_schema"]
            or binding.get("canonical_bytes") != len(raw)
            or binding.get("sha256") != _sha256(raw)
        ):
            _fail("formal recipe direct dependency binding drifted")
    return (catalog_raw, *dependency_raws)


def _recipe_projection_value(catalog):
    rows = [_project_recipe_row(row) for row in catalog["recipe_profile_rows"]]
    if (
        len(rows) != 71
        or len({row["variant_id"] for row in rows}) != 71
        or len({row["recipe_profile_id"] for row in rows}) != 71
    ):
        _fail("recipe/content/filename projection cardinality drifted")
    return {
        "artifact_kind": RECIPE_KIND,
        "artifact_schema": RECIPE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": catalog["fixture_id"],
        "fixture_schema_version": catalog["fixture_schema_version"],
        "policy_catalogs": _project_policy_catalogs(catalog["policy_catalogs"]),
        "recipe_profile_rows": rows,
    }


@functools.lru_cache(maxsize=1)
def _recipe_projection_raw():
    catalog = _decoded(_recipe_owner_raws()[0], label="formal recipe owner")
    raw = canonical_json_bytes(_recipe_projection_value(catalog))
    if len(raw) > TARGET_RECIPE_BYTES:
        _fail("recipe/content/filename projection exceeds its 256-KiB target")
    return raw


def build_recipe_content_filename_policy_content_projection():
    return _decoded(_recipe_projection_raw(), label="recipe projection")


@functools.lru_cache(maxsize=1)
def _fact_shared_owner_raws():
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
    raws = []
    for value, validate, canonical in zip(
        values, validators, canonicalizers, strict=True
    ):
        raws.append(
            _validated_raw(
                value,
                validate=validate,
                canonical=canonical,
                label=value["artifact_kind"],
            )
        )
    return tuple(raws)


@functools.lru_cache(maxsize=1)
def _fact_owner_raws():
    values = fact_graph.build_fact_graph_suite()
    if [value["persona_id"] for value in values] != list(envelope.PERSONA_IDS):
        _fail("fact graph suite persona order drifted")
    raws = tuple(fact_graph.canonical_json_bytes(value) for value in values)
    return raws


@functools.lru_cache(maxsize=20)
def _fact_owner_raw(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("fact graph owner persona is outside the exact suite")
    value = fact_graph.build_fact_graph(persona_id)
    if value.get("persona_id") != persona_id:
        _fail("single fact graph builder returned the wrong persona")
    return fact_graph.canonical_json_bytes(value)


def _fact_projection_value(value):
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


def _fact_projection_raw_from_owner(persona_id, fact_raw):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail("fact projection persona is outside the exact suite")
    value = _decoded(fact_raw, label="fact graph owner")
    if value.get("persona_id") != persona_id:
        _fail("fact graph owner/persona coordinate drifted")
    raw = canonical_json_bytes(_fact_projection_value(value))
    if len(raw) > TARGET_FACT_BYTES:
        _fail("fact-graph content projection exceeds its 32-KiB target")
    return raw


@functools.lru_cache(maxsize=20)
def _fact_projection_raw(persona_id):
    return _fact_projection_raw_from_owner(persona_id, _fact_owner_raw(persona_id))


def build_fact_graph_content_projection(persona_id):
    return _decoded(_fact_projection_raw(persona_id), label="fact projection")


def _primary_material():
    catalog_raw, envelope_raw, topology_raw = _primary_owner_raws()
    catalog = _decoded(catalog_raw, label="primary catalog owner")
    envelope_value = _decoded(envelope_raw, label="envelope owner")
    topology_value = _decoded(topology_raw, label="topology owner")
    bindings = catalog["input_bindings"]
    return _material(
        class_id=PRIMARY_CLASS_ID,
        coordinates=PRIMARY_COORDINATES,
        artifact_kind=PRIMARY_KIND,
        artifact_schema=PRIMARY_SCHEMA,
        body=_primary_projection_raw(),
        full_owner_pins=[
            _owner_pin(
                catalog,
                catalog_raw,
                coordinates={},
                owner_id="persona-v2-primary-use-case-catalog",
                owner_role="full-primary-use-case-catalog-owner-pin",
            ),
            _owner_pin(
                envelope_value,
                envelope_raw,
                coordinates={},
                owner_id="persona-v2-envelope",
                owner_role="full-envelope-owner-pin",
            ),
            _owner_pin(
                topology_value,
                topology_raw,
                coordinates={},
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
                    catalog["primary_use_cases"], label="primary-use-case source rows"
                ),
                direct_pin_id="primary-use-case-catalog-source-rows",
                direct_pin_role="primary-use-case-source-section",
            ),
        ],
    )


def _recipe_material():
    raws = _recipe_owner_raws()
    catalog = _decoded(raws[0], label="formal recipe owner")
    dependencies = [
        _decoded(raw, label="formal recipe dependency") for raw in raws[1:]
    ]
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
    full_owners = [
        _owner_pin(
            catalog,
            raws[0],
            coordinates={},
            owner_id="persona-v2-formal-source-recipe-profile-catalog",
            owner_role="full-formal-recipe-catalog-owner-pin",
        )
    ]
    for name, role, value, raw in zip(names, roles, dependencies, raws[1:], strict=True):
        full_owners.append(
            _owner_pin(
                value,
                raw,
                coordinates={},
                owner_id=f"persona-v2-{name}",
                owner_role=role,
            )
        )
    binding_roles = (
        "catalog-variant-binding-row",
        "catalog-inventory-profile-binding-row",
        "catalog-format-registry-binding-row",
        "catalog-semantic-membership-binding-row",
    )
    direct = []
    for binding, role in zip(catalog["input_bindings"], binding_roles, strict=True):
        direct.append(
            _direct_pin(
                _canonical_fragment(binding, label="formal recipe binding"),
                direct_pin_id=f"formal-recipe-{binding['name']}-binding",
                direct_pin_role=role,
            )
        )
    direct.extend(
        [
            _direct_pin(
                _canonical_fragment(
                    catalog["policy_catalogs"], label="formal recipe policy catalogs"
                ),
                direct_pin_id="formal-recipe-policy-catalogs",
                direct_pin_role="catalog-policy-section",
            ),
            _direct_pin(
                _canonical_fragment(
                    catalog["recipe_profile_rows"], label="formal recipe profile rows"
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
        body=_recipe_projection_raw(),
        full_owner_pins=full_owners,
        direct_body_pins=direct,
    )


def _fact_material(persona_id):
    index = envelope.PERSONA_IDS.index(persona_id)
    fact_raw = _fact_owner_raws()[index]
    fact_value = _decoded(fact_raw, label="fact graph owner")
    shared_raws = _fact_shared_owner_raws()
    shared_values = [
        _decoded(raw, label="fact graph shared owner") for raw in shared_raws
    ]
    shared_names = (
        "envelope",
        "topology",
        "joint-problem",
        "joint-solver-policy",
        "realism-profile",
    )
    full_owners = [
        _owner_pin(
            fact_value,
            fact_raw,
            coordinates={"persona_id": persona_id},
            owner_id=f"persona-v2-fact-graph-{persona_id}",
            owner_role="full-persona-fact-graph-owner-pin",
        )
    ]
    for name, value, raw in zip(
        shared_names, shared_values, shared_raws, strict=True
    ):
        full_owners.append(
            _owner_pin(
                value,
                raw,
                coordinates={},
                owner_id=f"persona-v2-{name}",
                owner_role=f"full-{name}-owner-pin",
            )
        )
    direct = []
    for binding in fact_value["input_bindings"]:
        direct.append(
            _direct_pin(
                _canonical_fragment(binding, label="fact graph input binding"),
                direct_pin_id=f"fact-graph-{persona_id}-{binding['name']}-binding",
                direct_pin_role=f"fact-graph-{binding['name']}-binding-row",
            )
        )
    for field, role in (
        ("graphs", "fact-graph-content-section"),
        ("logical_time_contract", "fact-graph-logical-time-section"),
        ("predicate_catalog", "fact-graph-predicate-section"),
    ):
        direct.append(
            _direct_pin(
                _canonical_fragment(fact_value[field], label=f"fact graph {field}"),
                direct_pin_id=f"fact-graph-{persona_id}-{field}",
                direct_pin_role=role,
            )
        )
    return _material(
        class_id=FACT_CLASS_ID,
        coordinates={"persona_id": persona_id},
        artifact_kind=FACT_KIND,
        artifact_schema=FACT_SCHEMA,
        body=_fact_projection_raw_from_owner(persona_id, fact_raw),
        full_owner_pins=full_owners,
        direct_body_pins=direct,
    )


def iter_corpus_content_projection_materials():
    """Yield detached material dictionaries in exact class/persona order."""

    yield _primary_material()
    yield _recipe_material()
    for persona_id in envelope.PERSONA_IDS:
        yield _fact_material(persona_id)


def _require_coordinates(class_id, coordinates):
    if type(class_id) is not str or type(coordinates) is not dict:
        _fail("projection dispatch requires exact class/coordinate values")
    if any(type(key) is not str for key in coordinates):
        _fail("projection coordinate keys must be exact built-in strings")
    if class_id == PRIMARY_CLASS_ID:
        if (
            set(coordinates) != {"scope"}
            or type(coordinates["scope"]) is not str
            or coordinates["scope"] != "suite"
        ):
            _fail("primary-use-case projection coordinates drifted")
    elif class_id == RECIPE_CLASS_ID:
        if (
            set(coordinates) != {"scope"}
            or type(coordinates["scope"]) is not str
            or coordinates["scope"] != "suite"
        ):
            _fail("recipe projection coordinates drifted")
    elif class_id == FACT_CLASS_ID:
        if (
            set(coordinates) != {"persona_id"}
            or type(coordinates["persona_id"]) is not str
            or coordinates["persona_id"] not in envelope.PERSONA_IDS
        ):
            _fail("fact projection coordinates drifted")
    else:
        _fail("projection dispatch received an unknown class")


def projection_body_bytes(class_id, coordinates):
    """Rebuild one selected body without materializing the other 21 bodies."""

    _require_coordinates(class_id, coordinates)
    if class_id == PRIMARY_CLASS_ID:
        return _primary_projection_raw()
    if class_id == RECIPE_CLASS_ID:
        return _recipe_projection_raw()
    return _fact_projection_raw(coordinates["persona_id"])


def _independent_validator():
    try:
        from . import persona_v2_semantic_projection_corpus_content_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_semantic_projection_corpus_content_validator as independent
        except ImportError:
            independent = None
    if independent is None:
        _fail("independent corpus content projection validator is unavailable")
    return independent


def validate_primary_use_case_corpus_content_projection(value):
    try:
        result = _independent_validator().validate_primary_use_case_corpus_content_projection(value)
    except Exception as error:
        if type(error) is PersonaV2SemanticProjectionCorpusContentError:
            raise
        _fail(str(error))
    _require_true(result, label="independent primary-use-case projection")
    return True


def validate_recipe_content_filename_policy_content_projection(value):
    try:
        result = _independent_validator().validate_recipe_content_filename_policy_content_projection(value)
    except Exception as error:
        if type(error) is PersonaV2SemanticProjectionCorpusContentError:
            raise
        _fail(str(error))
    _require_true(result, label="independent recipe projection")
    return True


def validate_fact_graph_content_projection(persona_id, value):
    try:
        result = _independent_validator().validate_fact_graph_content_projection(
            persona_id, value
        )
    except Exception as error:
        if type(error) is PersonaV2SemanticProjectionCorpusContentError:
            raise
        _fail(str(error))
    _require_true(result, label="independent fact projection")
    return True


def validate_corpus_content_projection_materials(material_provider=None):
    provider = (
        iter_corpus_content_projection_materials
        if material_provider is None
        else material_provider
    )
    try:
        result = _independent_validator().validate_corpus_content_projection_materials(
            provider
        )
    except Exception as error:
        if type(error) is PersonaV2SemanticProjectionCorpusContentError:
            raise
        _fail(str(error))
    _require_true(result, label="independent corpus content material package")
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
    "PersonaV2SemanticProjectionCorpusContentError",
    "RECIPE_CLASS_ID",
    "RECIPE_KIND",
    "RECIPE_SCHEMA",
    "TARGET_FACT_BYTES",
    "TARGET_PRIMARY_BYTES",
    "TARGET_RECIPE_BYTES",
    "build_fact_graph_content_projection",
    "build_primary_use_case_corpus_content_projection",
    "build_recipe_content_filename_policy_content_projection",
    "canonical_json_bytes",
    "iter_corpus_content_projection_materials",
    "projection_body_bytes",
    "validate_corpus_content_projection_materials",
    "validate_fact_graph_content_projection",
    "validate_primary_use_case_corpus_content_projection",
    "validate_recipe_content_filename_policy_content_projection",
]
