"""Deterministic source-instance parameter assignment for persona-PC v2.

This package binds every one of the 203,000 authenticated structural source
intents to an explicit ``variant_id/bin_id`` content-parameter cell.  It is a
pre-solve content owner only: scope, bucket, cohort, chunk quota, cell-local
ordinal, final IDs, physical writes, and execution authority are absent.

The persisted artifacts are one shared 363-cell catalog, twenty persona cell
projections, forty compact origin manifests, forty profile manifests, and one
suite descriptor.  Expanded ``{intent_key, parameter_cell_key}`` JSONL bodies
are deterministic non-persisted verification views; only their seventy-three
receipts are retained.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_aggregate_byte_distribution_catalog as aggregate
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_concrete_overlay_membership_package as concrete
    from . import persona_v2_contract as envelope
    from . import persona_v2_formal_source_recipe_catalog as formal
    from . import persona_v2_overlay_compatible_byte_distribution as effective
    from . import persona_v2_source_inventory_layout as source_layout
    from . import persona_v2_source_inventory_package as source_package
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_aggregate_byte_distribution_catalog as aggregate
    import persona_v2_artifact_common as artifact_common
    import persona_v2_concrete_overlay_membership_package as concrete
    import persona_v2_contract as envelope
    import persona_v2_formal_source_recipe_catalog as formal
    import persona_v2_overlay_compatible_byte_distribution as effective
    import persona_v2_source_inventory_layout as source_layout
    import persona_v2_source_inventory_package as source_package


CELL_CATALOG_SCHEMA = "kcs.persona.pc-source-parameter-cell-catalog/v2"
CELL_CATALOG_KIND = "persona-pc-v2-source-parameter-cell-catalog"
CELL_PROJECTION_SCHEMA = "kcs.persona.pc-source-parameter-cell-projection/v2"
CELL_PROJECTION_KIND = "persona-pc-v2-source-parameter-cell-projection"
ORIGIN_MANIFEST_SCHEMA = (
    "kcs.persona.pc-source-instance-parameter-assignment-origin-manifest/v2"
)
ORIGIN_MANIFEST_KIND = (
    "persona-pc-v2-source-instance-parameter-assignment-origin-manifest"
)
PROFILE_MANIFEST_SCHEMA = (
    "kcs.persona.pc-source-instance-parameter-assignment-profile-manifest/v2"
)
PROFILE_MANIFEST_KIND = (
    "persona-pc-v2-source-instance-parameter-assignment-profile-manifest"
)
SUITE_SCHEMA = "kcs.persona.pc-source-instance-parameter-assignment-suite/v2"
SUITE_KIND = "persona-pc-v2-source-instance-parameter-assignment-suite"
ARTIFACT_SCHEMA_VERSION = 2

ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full")
NON_EML_BIN_ORDER = (
    "floor",
    "small",
    "medium",
    "large",
    "ordinary-max",
    "formal-tail",
)
EML_BIN_ORDER = tuple(f"attachment-{value}" for value in range(6))

EXPECTED_SOURCE_COUNT = 203_000
EXPECTED_PILOT_SOURCE_COUNT = 20_300
EXPECTED_RESIDUAL_SOURCE_COUNT = 182_700
EXPECTED_SOURCE_SHARD_COUNT = 73
EXPECTED_GLOBAL_CELL_COUNT = 363
EXPECTED_PERSONA_CELL_COUNT = 2_643
EXPECTED_ORIGIN_OWNER_ROW_COUNT = 4_759
EXPECTED_EXACT_PAIR_COUNT = 5_080
EXPECTED_PILOT_EXACT_PAIR_COUNT = 508
EXPECTED_RESIDUAL_EXACT_PAIR_COUNT = 4_572
EXPECTED_PAIR_BEARING_COORDINATE_COUNT = 485
EXPECTED_EXPANDED_BODY_BYTES = 17_527_680
EXPECTED_MAX_EXPANDED_BODY_BYTES = 367_471
EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 110
EXPECTED_EML_SOURCE_COUNT = 9_153
EXPECTED_EML_HOST_COUNT = 2_800
EXPECTED_EML_NONHOST_COUNT = 6_353
EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT = 5_690
EXPECTED_NON_EML_SINGLETON_COUNT = 183_687

MAX_CELL_CATALOG_BYTES = 256 * 1024
MAX_CELL_PROJECTION_BYTES = 128 * 1024
MAX_ORIGIN_MANIFEST_BYTES = 512 * 1024
MAX_PROFILE_MANIFEST_BYTES = 128 * 1024
MAX_SUITE_BYTES = 512 * 1024
MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 256

EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-source-inventory-layout": (
        274_566,
        "ef52b756c7100c719f66323cd3cdb4dfc58a78e48d78f2857ca378cb1eb83dba",
    ),
    "persona-v2-source-inventory-suite": (
        45_887,
        "b62fadfa42b0f3f61b6de017300e65c48a5c07fb801dc470999c3d89a39dd706",
    ),
    "persona-v2-formal-source-recipe-profile-catalog": (
        386_152,
        "973a31336b90abc6271165ce4a3130679f36d5a9d65b06fece6827123e5c6cc8",
    ),
    "persona-v2-aggregate-byte-distribution-catalog": (
        1_576_125,
        "7f2fdcc823885401cb7ed1b8fc42c9010b38af63d2c58879babb28aadeb6b343",
    ),
    "persona-v2-overlay-compatible-byte-distribution": (
        91_039,
        "e4acd26dd7b268d86e21320a4a893416e7de169501b479a0bd8a215927265a89",
    ),
    "persona-v2-concrete-overlay-membership-suite": (
        51_133,
        "4763e06e9408109ad90c5e07a1bb16cd430fd65e6c5730d0015dcbea60cdf41a",
    ),
}

AUTHORITY_FIELDS = frozenset(
    {
        "actual_allocated_bytes_attested",
        "actual_chunks_attested",
        "actual_payload_bytes_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_query_plan",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_complete_persona_package_cap_proved",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "joint_allocation_proved",
        "kcs_execution_available",
        "query_instances_rendered",
        "renderer_available",
        "root_bound_capacity_attested",
    }
)


class PersonaV2SourceParameterAssignmentPackageError(ValueError):
    """Raised when source-parameter assignment construction drifts."""


def _fail(message):
    raise PersonaV2SourceParameterAssignmentPackageError(message)


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail(f"unknown persona ID: {persona_id!r}")


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        _fail(f"unknown origin: {origin!r}")


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        _fail(f"unknown profile: {profile!r}")


def _ascii(value):
    if type(value) is not str:
        _fail("canonical assignment key must be a string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("canonical assignment keys must be ASCII")


def _canonical_fragment(value, *, label, max_bytes):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceParameterAssignmentPackageError(str(error)) from None


def _binding(name, role, value, *, canonical, validate, coordinate=None):
    validate(value)
    raw = canonical(value)
    actual = (len(raw), hashlib.sha256(raw).hexdigest())
    expected = EXPECTED_DEPENDENCY_PINS.get(name)
    if expected is not None and actual != expected:
        _fail(f"{name} differs from its frozen dependency pin")
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": actual[0],
        "dependency_role": role,
        "name": name,
        "sha256": actual[1],
    }
    if coordinate:
        result.update(coordinate)
    return result


def _source_suite_canonical(value):
    return source_package.canonical_json_bytes(value)


def _concrete_suite_canonical(value):
    return concrete.canonical_json_bytes(value)


def _input_fingerprint(inputs):
    if type(inputs) is not dict:
        _fail("dependency snapshot must be an object")
    distribution_keys = {"aggregate", "bindings", "effective", "formal"}
    assignment_keys = distribution_keys | {
        "concrete_suite",
        "source_layout",
        "source_suite",
    }
    if set(inputs) not in (distribution_keys, assignment_keys):
        _fail("dependency snapshot has an unexpected key set")
    try:
        parts = []
        if "source_layout" in inputs:
            parts.extend(
                [
                    source_layout.canonical_json_bytes(inputs["source_layout"]),
                    source_package.canonical_json_bytes(inputs["source_suite"]),
                ]
            )
        parts.extend(
            [
                formal.canonical_json_bytes(inputs["formal"]),
                aggregate.canonical_json_bytes(inputs["aggregate"]),
                effective.canonical_json_bytes(inputs["effective"]),
            ]
        )
        if "concrete_suite" in inputs:
            parts.append(concrete.canonical_json_bytes(inputs["concrete_suite"]))
        parts.append(
            _canonical_fragment(
                inputs["bindings"],
                label="source parameter dependency bindings",
                max_bytes=128 * 1024,
            )
        )
        return tuple(parts)
    except (KeyError, TypeError, ValueError) as error:
        raise PersonaV2SourceParameterAssignmentPackageError(
            "source parameter dependencies became invalid"
        ) from error


def _reauth_inputs(inputs, opening, *, label):
    current = _input_fingerprint(inputs)
    if len(current) != len(opening) or any(
        not hmac.compare_digest(actual, expected)
        for actual, expected in zip(current, opening)
    ):
        _fail(f"{label} changed during a provider callback")


@functools.lru_cache(maxsize=1)
def _cached_distribution_inputs():
    formal_value = formal.build_formal_source_recipe_catalog()
    aggregate_value = aggregate.build_aggregate_byte_distribution_catalog()
    effective_value = effective.build_overlay_compatible_byte_distribution()
    bindings = [
        _binding(
            "persona-v2-formal-source-recipe-profile-catalog",
            "all-71-recipe-profile-and-variant-order-owner",
            formal_value,
            canonical=formal.canonical_json_bytes,
            validate=formal.validate_formal_source_recipe_catalog,
        ),
        _binding(
            "persona-v2-aggregate-byte-distribution-catalog",
            "immutable-non-eml-parameter-cell-histograms",
            aggregate_value,
            canonical=aggregate.canonical_json_bytes,
            validate=aggregate.validate_aggregate_byte_distribution_catalog,
        ),
        _binding(
            "persona-v2-overlay-compatible-byte-distribution",
            "effective-eml-attachment-zero-through-five-histograms",
            effective_value,
            canonical=effective.canonical_json_bytes,
            validate=effective.validate_overlay_compatible_byte_distribution,
        ),
    ]
    result = {
        "aggregate": aggregate_value,
        "bindings": bindings,
        "effective": effective_value,
        "formal": formal_value,
    }
    _input_fingerprint(result)
    return result


@functools.lru_cache(maxsize=1)
def _cached_assignment_inputs():
    distribution = _cached_distribution_inputs()
    layout_value = source_layout.build_source_inventory_layout()
    source_suite_value = source_package.build_source_intent_suite_descriptor()
    concrete_suite_value = concrete.build_concrete_overlay_membership_suite_descriptor()
    additional = [
        _binding(
            "persona-v2-source-inventory-layout",
            "exact-source-key-ranges-and-canonical-shard-order",
            layout_value,
            canonical=source_layout.canonical_json_bytes,
            validate=source_layout.validate_source_inventory_layout,
        ),
        _binding(
            "persona-v2-source-inventory-suite",
            "authenticated-203000-source-intents-and-73-shard-bodies",
            source_suite_value,
            canonical=_source_suite_canonical,
            validate=source_package.validate_source_intent_suite_descriptor,
        ),
        _binding(
            "persona-v2-concrete-overlay-membership-suite",
            "exact-duplicate-and-eml-host-membership-owner",
            concrete_suite_value,
            canonical=_concrete_suite_canonical,
            validate=concrete.validate_concrete_overlay_membership_suite_descriptor,
        ),
    ]
    by_name = {
        row["name"]: row for row in [*distribution["bindings"], *additional]
    }
    binding_order = [
        "persona-v2-source-inventory-layout",
        "persona-v2-source-inventory-suite",
        "persona-v2-formal-source-recipe-profile-catalog",
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
        "persona-v2-concrete-overlay-membership-suite",
    ]
    result = {
        "aggregate": distribution["aggregate"],
        "bindings": [copy.deepcopy(by_name[name]) for name in binding_order],
        "concrete_suite": concrete_suite_value,
        "effective": distribution["effective"],
        "formal": distribution["formal"],
        "source_layout": layout_value,
        "source_suite": source_suite_value,
    }
    _input_fingerprint(result)
    return result


def _variant_order(inputs):
    rows = inputs["formal"]["recipe_profile_rows"]
    order = tuple(row["variant_id"] for row in rows)
    if len(order) != 71 or len(set(order)) != 71 or "eml" not in order:
        _fail("formal recipe variant order drifted")
    return order


def _parameter_cell_key(variant_id, bin_id):
    if "/" in variant_id or "/" in bin_id:
        _fail("parameter-cell key components cannot contain slash")
    return f"{variant_id}/{bin_id}"


def _cell_definition(row, parameter_bin, *, recipe_field="recipe_profile_id"):
    return {
        "bin_id": parameter_bin["bin_id"],
        "parameter_cell_key": _parameter_cell_key(
            row["variant_id"], parameter_bin["bin_id"]
        ),
        "recipe_profile_id": row[recipe_field],
        "renderer_parameters": copy.deepcopy(parameter_bin["renderer_parameters"]),
        "size_lane": parameter_bin["size_lane"],
        "target_bytes": parameter_bin["exact_raw_bytes"],
        "target_complexity": parameter_bin["target_complexity"],
        "variant_id": row["variant_id"],
    }


def _effective_rows(inputs):
    variant_order = _variant_order(inputs)
    order_index = {variant_id: index for index, variant_id in enumerate(variant_order)}
    base = {
        (row["persona_id"], row["variant_id"]): row
        for row in inputs["aggregate"]["persona_variant_rows"]
        if row["variant_id"] != "eml"
    }
    eml = {
        (row["persona_id"], "eml"): row
        for row in inputs["effective"]["eml_override_rows"]
    }
    rows = {**base, **eml}
    if len(rows) != aggregate.EXPECTED_PERSONA_VARIANT_ROWS:
        _fail("effective persona/variant row coverage drifted")
    result = {}
    for persona_id in envelope.PERSONA_IDS:
        selected = [
            row for (pid, _), row in rows.items() if pid == persona_id
        ]
        selected.sort(key=lambda row: order_index[row["variant_id"]])
        result[persona_id] = selected
    return result


def _global_cell_rows(inputs):
    rows_by_persona = _effective_rows(inputs)
    variant_order = _variant_order(inputs)
    definitions = {}
    for persona_rows in rows_by_persona.values():
        for row in persona_rows:
            recipe_field = (
                "base_recipe_profile_id" if row["variant_id"] == "eml"
                else "recipe_profile_id"
            )
            for parameter_bin in row["parameter_bins"]:
                cell = _cell_definition(
                    row, parameter_bin, recipe_field=recipe_field
                )
                key = cell["parameter_cell_key"]
                previous = definitions.setdefault(key, cell)
                if previous != cell:
                    _fail(f"parameter cell definition varies by persona: {key}")
    ordered = []
    for variant_id in variant_order:
        bins = EML_BIN_ORDER if variant_id == "eml" else NON_EML_BIN_ORDER
        for bin_id in bins:
            key = _parameter_cell_key(variant_id, bin_id)
            if key in definitions:
                ordered.append(definitions.pop(key))
    if definitions or len(ordered) != EXPECTED_GLOBAL_CELL_COUNT:
        _fail("global parameter-cell catalog cardinality/order drifted")
    return ordered


def _common_envelope(kind, schema, completion_scope):
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "completion_scope": completion_scope,
    }


def _selected_shared_bindings(inputs, names):
    by_name = {row["name"]: row for row in inputs["bindings"]}
    if len(by_name) != len(inputs["bindings"]) or not set(names) <= set(by_name):
        _fail("requested dependency binding coverage drifted")
    return [copy.deepcopy(by_name[name]) for name in names]


@functools.lru_cache(maxsize=1)
def _canonical_cell_catalog():
    inputs = _cached_distribution_inputs()
    rows = _global_cell_rows(inputs)
    direct_names = [
        "persona-v2-formal-source-recipe-profile-catalog",
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
    ]
    direct_bindings = _selected_shared_bindings(inputs, direct_names)
    value = {
        **_common_envelope(
            CELL_CATALOG_KIND,
            CELL_CATALOG_SCHEMA,
            "shared-363-explicit-content-parameter-cell-definitions-only-no-source-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "max_body_bytes": MAX_CELL_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_363_effective_parameter_cells_defined": True,
            "base_eml_parameter_bins_selected": False,
            "effective_eml_attachment_zero_through_five_selected": True,
            "source_instance_assignments_bound": False,
        },
        "input_binding_order": direct_names,
        "input_bindings": direct_bindings,
        "orders": {
            "parameter_cells": (
                "formal-variant-order-then-non-eml-floor-small-medium-large-"
                "ordinary-max-formal-tail-or-eml-attachment-zero-through-five"
            )
        },
        "parameter_cells": copy.deepcopy(rows),
        "remaining_blockers": [
            "source-instance-cell-assignment-not-in-this-shared-catalog",
            "frame-and-header-accounting-not-implemented",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
            "render-write-observation-history-kcs-capacity-and-g0-absent",
        ],
        "summary": {
            "eml_parameter_cell_count": len(EML_BIN_ORDER),
            "non_eml_parameter_cell_count": len(rows) - len(EML_BIN_ORDER),
            "parameter_cell_count": len(rows),
            "variant_count": len(_variant_order(inputs)),
        },
    }
    canonical_json_bytes(value)
    return value


def build_source_parameter_cell_catalog():
    return copy.deepcopy(_canonical_cell_catalog())


def _cell_catalog_binding():
    value = _canonical_cell_catalog()
    raw = canonical_json_bytes(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "shared-explicit-parameter-cell-definition-owner",
        "name": "persona-v2-source-parameter-cell-catalog",
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


@functools.lru_cache(maxsize=20)
def _canonical_cell_projection(persona_id):
    _require_persona_id(persona_id)
    inputs = _cached_distribution_inputs()
    rows = []
    for row in _effective_rows(inputs)[persona_id]:
        recipe_field = (
            "base_recipe_profile_id" if row["variant_id"] == "eml"
            else "recipe_profile_id"
        )
        for parameter_bin in row["parameter_bins"]:
            counts = copy.deepcopy(parameter_bin["counts"])
            if counts["full"] == 0:
                continue
            if counts["full"] != counts["pilot"] + counts["full-residual"]:
                _fail("persona parameter cell does not close pilot plus residual")
            definition = _cell_definition(
                row, parameter_bin, recipe_field=recipe_field
            )
            rows.append(
                {
                    "counts": counts,
                    "parameter_cell_key": definition["parameter_cell_key"],
                    "variant_id": definition["variant_id"],
                }
            )
    distribution_names = [
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
    ]
    distribution_bindings = _selected_shared_bindings(inputs, distribution_names)
    value = {
        **_common_envelope(
            CELL_PROJECTION_KIND,
            CELL_PROJECTION_SCHEMA,
            "one-persona-positive-effective-parameter-cell-count-projection-only-no-source-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "max_body_bytes": MAX_CELL_PROJECTION_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_positive_effective_cells_projected": True,
            "full_equals_exact_pilot_plus_residual_counts": True,
            "source_instance_assignments_bound": False,
        },
        "input_binding_order": [
            "persona-v2-source-parameter-cell-catalog",
            *distribution_names,
        ],
        "input_bindings": [_cell_catalog_binding(), *distribution_bindings],
        "orders": {"cell_count_rows": "shared-parameter-cell-catalog-order"},
        "persona_id": persona_id,
        "cell_count_rows": rows,
        "remaining_blockers": [
            "source-instance-cell-assignment-not-in-this-count-projection",
            "frame-and-header-accounting-not-implemented",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
        ],
        "summary": {
            "active_parameter_cell_count": len(rows),
            "source_counts": {
                profile: sum(row["counts"][profile] for row in rows)
                for profile in ("pilot", "full-residual", "full")
            },
        },
    }
    if value["summary"]["source_counts"]["full"] != sum(
        item["source_counts"]["full"]
        for item in inputs["aggregate"]["persona_summaries"]
        if item["persona_id"] == persona_id
    ):
        _fail("persona cell projection source count drifted")
    canonical_json_bytes(value)
    return value


def build_source_parameter_cell_projection(persona_id):
    return copy.deepcopy(_canonical_cell_projection(persona_id))


def _artifact_binding(
    value, *, name, role, max_bytes, coordinate_fields=()
):
    raw = _canonical_fragment(value, label=name, max_bytes=max_bytes)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    for field in coordinate_fields:
        result[field] = value[field]
    return result


def _projection_binding(persona_id):
    return _artifact_binding(
        _canonical_cell_projection(persona_id),
        name="persona-v2-source-parameter-cell-projection",
        role="persona-effective-positive-cell-count-owner",
        max_bytes=MAX_CELL_PROJECTION_BYTES,
        coordinate_fields=("persona_id",),
    )


def _suite_coordinate_binding(suite, bindings_field, persona_id, origin):
    matches = [
        row
        for row in suite[bindings_field]
        if row.get("persona_id") == persona_id and row.get("origin") == origin
    ]
    if len(matches) != 1:
        _fail(f"suite has no unique origin binding: {persona_id}/{origin}")
    return matches[0]


def _authenticated_source_origin(
    inputs, persona_id, origin, source_origin_provider
):
    try:
        value = copy.deepcopy(source_origin_provider(persona_id, origin))
        source_package.validate_source_intent_origin_manifest(
            persona_id, origin, value
        )
        raw = source_package.canonical_json_bytes(value)
    except Exception as error:
        raise PersonaV2SourceParameterAssignmentPackageError(
            "source origin provider failed authentication"
        ) from error
    expected = _suite_coordinate_binding(
        inputs["source_suite"], "origin_manifest_bindings", persona_id, origin
    )
    if (
        value.get("persona_id") != persona_id
        or value.get("origin") != origin
        or len(raw) != expected["canonical_bytes"]
        or not hmac.compare_digest(
            hashlib.sha256(raw).hexdigest(), expected["sha256"]
        )
    ):
        _fail("source origin differs from its authenticated suite binding")
    return value, raw


def _authenticated_concrete_origin(
    inputs, persona_id, origin, concrete_origin_provider
):
    try:
        value = copy.deepcopy(concrete_origin_provider(persona_id, origin))
        concrete.validate_concrete_overlay_membership_origin_manifest(
            persona_id, origin, value
        )
        raw = concrete.canonical_json_bytes(value)
    except Exception as error:
        raise PersonaV2SourceParameterAssignmentPackageError(
            "concrete overlay origin provider failed authentication"
        ) from error
    expected = _suite_coordinate_binding(
        inputs["concrete_suite"], "origin_manifest_bindings", persona_id, origin
    )
    if (
        value.get("persona_id") != persona_id
        or value.get("origin") != origin
        or len(raw) != expected["canonical_bytes"]
        or not hmac.compare_digest(
            hashlib.sha256(raw).hexdigest(), expected["sha256"]
        )
    ):
        _fail("concrete overlay origin differs from its suite binding")
    return value, raw


def _parse_canonical_jsonl(body, *, label, maximum_line_bytes):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        _fail(f"{label} must be non-empty LF-terminated bytes")
    rows = []
    for line in body.splitlines():
        if not line or len(line) + 1 > maximum_line_bytes:
            _fail(f"{label} contains an empty or oversized row")
        try:
            row = json.loads(line.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersonaV2SourceParameterAssignmentPackageError(
                f"{label} is not strict UTF-8 JSONL"
            ) from error
        if type(row) is not dict or _canonical_fragment(
            row,
            label=f"{label} row",
            max_bytes=maximum_line_bytes - 1,
        ) != line:
            _fail(f"{label} row is not canonical JSON")
        rows.append(row)
    return rows


def _provider_body(
    provider,
    coordinate,
    *,
    label,
    expected_bytes,
    expected_sha256,
):
    try:
        first = provider(*coordinate)
    except Exception as error:
        raise PersonaV2SourceParameterAssignmentPackageError(
            f"{label} provider failed"
        ) from error
    if type(first) is not bytes:
        _fail(f"{label} provider must return exact bytes")
    if (
        len(first) != expected_bytes
        or not hmac.compare_digest(
            hashlib.sha256(first).hexdigest(), expected_sha256
        )
    ):
        _fail(f"{label} provider first result differs from its descriptor")
    try:
        second = provider(*coordinate)
    except Exception as error:
        raise PersonaV2SourceParameterAssignmentPackageError(
            f"{label} provider failed"
        ) from error
    if type(second) is not bytes:
        _fail(f"{label} provider must return exact bytes")
    if (
        len(second) != expected_bytes
        or not hmac.compare_digest(
            hashlib.sha256(second).hexdigest(), expected_sha256
        )
    ):
        _fail(f"{label} provider is nondeterministic or descriptor-mismatched")
    if not hmac.compare_digest(first, second):
        _fail(f"{label} provider is nondeterministic or alias-mutated")
    return first


def _source_profile_to_variant(inputs):
    result = {
        row["source_inventory_profile_id"]: row["variant_id"]
        for row in inputs["formal"]["recipe_profile_rows"]
    }
    if len(result) != 71:
        _fail("source inventory profile to variant join is not bijective")
    return result


def _load_source_shards(
    inputs,
    persona_id,
    origin,
    manifest,
    source_body_provider,
):
    profile_to_variant = _source_profile_to_variant(inputs)
    seen = set()
    shards = []
    for descriptor in manifest["shard_descriptors"]:
        if (
            descriptor.get("persona_id") != persona_id
            or descriptor.get("origin") != origin
        ):
            _fail("source shard descriptor has the wrong coordinate")
        coordinate = (persona_id, origin, descriptor["shard_ordinal"])
        body = _provider_body(
            source_body_provider,
            coordinate,
            label="source intent shard body",
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
        )
        rows = _parse_canonical_jsonl(
            body,
            label="source intent shard",
            maximum_line_bytes=source_package.MAX_INTENT_ROW_BYTES_INCLUDING_LF,
        )
        if len(rows) != descriptor["row_count"]:
            _fail("source intent shard row count differs from descriptor")
        enriched = []
        for row in rows:
            if set(row) != source_package.INTENT_ROW_FIELDS:
                _fail("source intent row schema drifted")
            if row["persona_id"] != persona_id or row["origin"] != origin:
                _fail("source intent row has the wrong coordinate")
            intent_key = row["intent_key"]
            if intent_key in seen:
                _fail("source intent key repeats across authenticated shards")
            seen.add(intent_key)
            variant_id = profile_to_variant.get(row["source_profile_id"])
            if variant_id is None:
                _fail("source intent row has no formal variant join")
            enriched.append((intent_key, variant_id))
        if (
            enriched[0][0] != descriptor["first_intent_key"]
            or enriched[-1][0] != descriptor["last_intent_key"]
        ):
            _fail("source shard endpoint keys differ from descriptor")
        shards.append((descriptor, enriched))
    if len(seen) != manifest["summary"]["source_intent_count"]:
        _fail("source origin manifest count differs from authenticated bodies")
    return shards


def _load_concrete_rows(
    persona_id,
    origin,
    manifest,
    concrete_body_provider,
):
    rows = []
    for descriptor in manifest["shard_descriptors"]:
        if (
            descriptor.get("persona_id") != persona_id
            or descriptor.get("origin") != origin
        ):
            _fail("concrete overlay shard descriptor has the wrong coordinate")
        coordinate = (persona_id, origin, descriptor["shard_index"])
        body = _provider_body(
            concrete_body_provider,
            coordinate,
            label="concrete overlay shard body",
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
        )
        parsed = _parse_canonical_jsonl(
            body,
            label="concrete overlay shard",
            maximum_line_bytes=concrete.MAX_ROW_BYTES_INCLUDING_LF,
        )
        if len(parsed) != descriptor["row_count"]:
            _fail("concrete overlay shard row count differs from descriptor")
        rows.extend(parsed)
    if len(rows) != manifest["summary"]["rich_row_count"]:
        _fail("concrete overlay origin count differs from shard bodies")
    return rows


def _relation_and_host_maps(source_rows, concrete_rows):
    intent_to_variant = {
        intent_key: variant_id
        for _, rows in source_rows
        for intent_key, variant_id in rows
    }
    exact_pairs = []
    host_members = {}
    host_ordinals = {}
    for row in concrete_rows:
        if row.get("row_kind") == "content-relation-membership" and row.get(
            "relation_kind"
        ) == "exact-duplicate":
            anchor = row["anchor_intent_key"]
            derivative = row["derivative_intent_key"]
            variant = intent_to_variant.get(anchor)
            if (
                variant is None
                or variant == "eml"
                or intent_to_variant.get(derivative) != variant
                or anchor == derivative
            ):
                _fail("exact duplicate is not a same non-EML variant pair")
            exact_pairs.append(
                (anchor, derivative, row["cluster_key"], variant)
            )
        elif row.get("row_kind") == "attachment-membership":
            host = row["host_intent_key"]
            count = row["host_member_count"]
            ordinal = row["member_ordinal"]
            if intent_to_variant.get(host) != "eml" or count not in range(1, 6):
                _fail("attachment host does not resolve to EML complexity 1..5")
            previous = host_members.setdefault(host, count)
            if previous != count:
                _fail("one EML host declares inconsistent member counts")
            host_ordinals.setdefault(host, set()).add(ordinal)
    exact_pairs.sort(
        key=lambda row: (_ascii(row[0]), _ascii(row[1]), _ascii(row[2]))
    )
    endpoints = [key for row in exact_pairs for key in row[:2]]
    if len(endpoints) != len(set(endpoints)):
        _fail("exact duplicate endpoints repeat")
    for host, count in host_members.items():
        if host_ordinals[host] != set(range(1, count + 1)):
            _fail("EML host member ordinals do not close 1..N")
    return exact_pairs, host_members


def _hamilton_pair_counts(pair_count, cells):
    capacities = {
        row["parameter_cell_key"]: row["source_count"] // 2
        for row in cells
    }
    denominator = sum(capacities.values())
    if type(pair_count) is not int or pair_count < 0 or pair_count > denominator:
        _fail("exact-pair demand exceeds cell pair capacity")
    if pair_count == 0:
        return {row["parameter_cell_key"]: 0 for row in cells}
    result = {
        key: pair_count * capacity // denominator
        for key, capacity in capacities.items()
    }
    residual = pair_count - sum(result.values())
    order = {row["parameter_cell_key"]: index for index, row in enumerate(cells)}
    ranked = sorted(
        capacities,
        key=lambda key: (
            -(pair_count * capacities[key] % denominator),
            order[key],
        ),
    )
    for key in ranked[:residual]:
        result[key] += 1
    if sum(result.values()) != pair_count or any(
        result[key] > capacities[key] for key in result
    ):
        _fail("Hamilton exact-pair allocation did not close within capacity")
    return result


def _origin_target_cells(persona_id, origin):
    projection = _canonical_cell_projection(persona_id)
    rows = []
    for row in projection["cell_count_rows"]:
        count = row["counts"][origin]
        if count:
            rows.append(
                {
                    "parameter_cell_key": row["parameter_cell_key"],
                    "source_count": count,
                    "variant_id": row["variant_id"],
                }
            )
    return rows


def _allocate_origin(persona_id, origin, source_shards, concrete_rows):
    exact_pairs, host_members = _relation_and_host_maps(
        source_shards, concrete_rows
    )
    source_by_variant = {}
    for _, rows in source_shards:
        for intent_key, variant_id in rows:
            source_by_variant.setdefault(variant_id, []).append(intent_key)
    cells = _origin_target_cells(persona_id, origin)
    cells_by_variant = {}
    for row in cells:
        cells_by_variant.setdefault(row["variant_id"], []).append(row)
    pairs_by_variant = {}
    for pair in exact_pairs:
        pairs_by_variant.setdefault(pair[3], []).append(pair)
    assignments = {}
    owner_rows = []
    pair_coordinate_count = 0
    for variant_id, variant_cells in cells_by_variant.items():
        intents = source_by_variant.get(variant_id, [])
        if sum(row["source_count"] for row in variant_cells) != len(intents):
            _fail(f"cell histogram does not close source marginal: {variant_id}")
        if variant_id == "eml":
            for intent_key in intents:
                complexity = host_members.get(intent_key, 0)
                assignments[intent_key] = _parameter_cell_key(
                    "eml", f"attachment-{complexity}"
                )
            for cell in variant_cells:
                actual = sum(
                    value == cell["parameter_cell_key"]
                    for value in assignments.values()
                )
                if actual != cell["source_count"]:
                    _fail("EML host/nonhost assignment differs from effective histogram")
                owner_rows.append(
                    {
                        **cell,
                        "eml_fixed_intent_count": actual,
                        "exact_pair_endpoint_count": 0,
                        "exact_pair_unit_count": 0,
                        "singleton_intent_count": 0,
                    }
                )
            continue
        pairs = pairs_by_variant.get(variant_id, [])
        if pairs:
            pair_coordinate_count += 1
        pair_counts = _hamilton_pair_counts(len(pairs), variant_cells)
        pair_index = 0
        paired = set()
        for cell in variant_cells:
            count = pair_counts[cell["parameter_cell_key"]]
            for pair in pairs[pair_index : pair_index + count]:
                assignments[pair[0]] = cell["parameter_cell_key"]
                assignments[pair[1]] = cell["parameter_cell_key"]
                paired.update(pair[:2])
            pair_index += count
        if pair_index != len(pairs):
            _fail("exact pair allocation left trailing pairs")
        remaining = sorted(
            (key for key in intents if key not in paired), key=_ascii
        )
        singleton_index = 0
        for cell in variant_cells:
            pair_units = pair_counts[cell["parameter_cell_key"]]
            singleton_count = cell["source_count"] - 2 * pair_units
            for intent_key in remaining[
                singleton_index : singleton_index + singleton_count
            ]:
                assignments[intent_key] = cell["parameter_cell_key"]
            singleton_index += singleton_count
            owner_rows.append(
                {
                    **cell,
                    "eml_fixed_intent_count": 0,
                    "exact_pair_endpoint_count": 2 * pair_units,
                    "exact_pair_unit_count": pair_units,
                    "singleton_intent_count": singleton_count,
                }
            )
        if singleton_index != len(remaining):
            _fail("ASCII singleton fill left trailing intents")
    all_intents = {
        key for _, rows in source_shards for key, _ in rows
    }
    if set(assignments) != all_intents:
        _fail("source parameter assignment is not total and exact")
    for row in owner_rows:
        if row["source_count"] != (
            row["exact_pair_endpoint_count"]
            + row["singleton_intent_count"]
            + row["eml_fixed_intent_count"]
        ) or row["exact_pair_endpoint_count"] != 2 * row["exact_pair_unit_count"]:
            _fail("compact owner source-count equation did not close")
    return assignments, owner_rows, exact_pairs, host_members, pair_coordinate_count


def _expanded_row(intent_key, parameter_cell_key):
    value = {
        "intent_key": intent_key,
        "parameter_cell_key": parameter_cell_key,
    }
    raw = _canonical_fragment(
        value,
        label="source parameter expanded view row",
        max_bytes=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF - 1,
    )
    return value, raw + b"\n"


def _expanded_receipts(source_shards, assignments):
    receipts = []
    for descriptor, rows in source_shards:
        parts = []
        for intent_key, _ in rows:
            _, raw = _expanded_row(intent_key, assignments[intent_key])
            parts.append(raw)
        body = b"".join(parts)
        receipt = {
            "expanded_body_bytes": len(body),
            "expanded_body_persisted": False,
            "expanded_body_sha256": hashlib.sha256(body).hexdigest(),
            "first_intent_key": rows[0][0],
            "last_intent_key": rows[-1][0],
            "maximum_row_bytes_including_lf": max(map(len, parts)),
            "origin": descriptor["origin"],
            "persona_id": descriptor["persona_id"],
            "row_count": len(rows),
            "shard_ordinal": descriptor["shard_ordinal"],
            "source_shard_body_bytes": descriptor["body_bytes"],
            "source_shard_body_sha256": descriptor["body_sha256"],
            "source_shard_id": descriptor["shard_id"],
        }
        receipts.append(receipt)
    return receipts


def _origin_input_bindings(
    inputs,
    persona_id,
    source_origin,
    concrete_origin,
):
    direct = _selected_shared_bindings(
        inputs,
        [
            "persona-v2-source-inventory-layout",
            "persona-v2-source-inventory-suite",
            "persona-v2-concrete-overlay-membership-suite",
        ],
    )
    return [
        _projection_binding(persona_id),
        *direct,
        _artifact_binding(
            source_origin,
            name="persona-v2-source-inventory-origin-manifest",
            role="matching-authenticated-source-shard-descriptor-owner",
            max_bytes=source_package.MAX_ORIGIN_MANIFEST_BYTES,
            coordinate_fields=("persona_id", "origin"),
        ),
        _artifact_binding(
            concrete_origin,
            name="persona-v2-concrete-overlay-membership-origin-manifest",
            role="matching-exact-pair-and-eml-host-membership-owner",
            max_bytes=concrete.MAX_ORIGIN_MANIFEST_BYTES,
            coordinate_fields=("persona_id", "origin"),
        ),
    ]


def _build_origin_manifest(
    inputs,
    persona_id,
    origin,
    *,
    source_origin_provider,
    source_body_provider,
    concrete_origin_provider,
    concrete_body_provider,
    return_state=False,
):
    _require_persona_id(persona_id)
    _require_origin(origin)
    opening = _input_fingerprint(inputs)
    source_origin, source_origin_raw = _authenticated_source_origin(
        inputs, persona_id, origin, source_origin_provider
    )
    concrete_origin, concrete_origin_raw = _authenticated_concrete_origin(
        inputs, persona_id, origin, concrete_origin_provider
    )
    source_shards = _load_source_shards(
        inputs,
        persona_id,
        origin,
        source_origin,
        source_body_provider,
    )
    concrete_rows = _load_concrete_rows(
        persona_id,
        origin,
        concrete_origin,
        concrete_body_provider,
    )
    (
        assignments,
        owner_rows,
        exact_pairs,
        host_members,
        pair_coordinate_count,
    ) = _allocate_origin(persona_id, origin, source_shards, concrete_rows)
    receipts = _expanded_receipts(source_shards, assignments)

    # Postflight the mutable providers after every body callback.  A provider
    # cannot swap a coordinate, mutate a shared alias, or become nondeterministic
    # while retaining the opening suite pin.
    source_post, source_post_raw = _authenticated_source_origin(
        inputs, persona_id, origin, source_origin_provider
    )
    concrete_post, concrete_post_raw = _authenticated_concrete_origin(
        inputs, persona_id, origin, concrete_origin_provider
    )
    if (
        not hmac.compare_digest(source_origin_raw, source_post_raw)
        or not hmac.compare_digest(concrete_origin_raw, concrete_post_raw)
        or source_origin != source_post
        or concrete_origin != concrete_post
    ):
        _fail("origin provider changed during assignment construction")
    _reauth_inputs(inputs, opening, label="source parameter dependencies")

    source_count = len(assignments)
    eml_source_count = sum(
        row["source_count"] for row in owner_rows if row["variant_id"] == "eml"
    )
    input_bindings = _origin_input_bindings(
        inputs, persona_id, source_origin, concrete_origin
    )
    value = {
        **_common_envelope(
            ORIGIN_MANIFEST_KIND,
            ORIGIN_MANIFEST_SCHEMA,
            "one-persona-one-origin-compact-content-parameter-owner-and-nonpersisted-expanded-view-receipts-only-no-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "expanded_jsonl_record_terminator": "LF",
            "max_body_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "max_expanded_row_bytes_including_lf": MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "compact_assignment_rows": owner_rows,
        "completion_claims": {
            "all_origin_source_parameters_bound": True,
            "expanded_assignment_bodies_persisted": False,
            "expanded_receipts_bound_to_authenticated_source_shards": True,
            "exact_duplicate_pairs_coassigned": True,
            "formal_complete_persona_package_cap_proved": False,
            "scope_bucket_cohort_chunk_quota_or_final_ids_present": False,
        },
        "dependency_direction_contract": {
            "concrete_overlay_and_source_shards_are_strictly_upstream": True,
            "evaluation_query_or_oracle_imported": False,
            "lifecycle_demand_or_solution_imported": False,
            "source_parameter_owner_may_bind_scope_or_final_ids": False,
        },
        "expanded_view_receipts": receipts,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "compact_assignment_rows": "formal-variant-order-then-canonical-cell-order-positive-cells-only",
            "expanded_view_receipts": "authenticated-source-shard-order",
        },
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": [
            "frame-and-header-accounting-not-implemented",
            "formal-complete-persona-package-cap-not-proved",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
            "semantic-payload-render-write-observation-history-kcs-and-g0-absent",
        ],
        "selection_policy": {
            "cell_identity": "literal-variant-id-slash-bin-id-no-component-slash",
            "cell_order": (
                "formal-variant-order-then-non-eml-floor-small-medium-large-"
                "ordinary-max-formal-tail-or-eml-attachment-zero-through-five"
            ),
            "eml_rule": "concrete-host-member-count-one-through-five-else-attachment-zero",
            "exact_pair_cell_rule": "same-non-eml-parameter-cell-for-both-endpoints",
            "exact_pair_order": "anchor-intent-key-ascii-then-derivative-intent-key-ascii-then-cluster-key-ascii",
            "pair_allocation": "hamilton-over-floor-source-count-divided-by-two-capacity-canonical-cell-tie-break",
            "singleton_fill": "remaining-intent-key-ascii-order-into-residual-canonical-cell-counts",
        },
        "summary": {
            "active_parameter_cell_count": len(owner_rows),
            "eml_fixed_host_intent_count": len(host_members),
            "eml_attachment_membership_count": sum(host_members.values()),
            "eml_fixed_nonhost_intent_count": eml_source_count - len(host_members),
            "exact_pair_endpoint_count": 2 * len(exact_pairs),
            "exact_pair_unit_count": len(exact_pairs),
            "expanded_body_bytes_nonpersisted": sum(
                row["expanded_body_bytes"] for row in receipts
            ),
            "expanded_receipt_count": len(receipts),
            "maximum_expanded_body_bytes": max(
                row["expanded_body_bytes"] for row in receipts
            ),
            "maximum_expanded_row_bytes_including_lf": max(
                row["maximum_row_bytes_including_lf"] for row in receipts
            ),
            "pair_bearing_persona_origin_variant_coordinate_count": pair_coordinate_count,
            "singleton_intent_count": sum(
                row["singleton_intent_count"] for row in owner_rows
            ),
            "source_intent_count": source_count,
        },
    }
    if (
        value["summary"]["source_intent_count"]
        != source_origin["summary"]["source_intent_count"]
        or sum(row["source_count"] for row in owner_rows) != source_count
        or sum(row["row_count"] for row in receipts) != source_count
    ):
        _fail("origin owner/receipt/source counts do not close")
    canonical_json_bytes(value)
    state = {"assignments": assignments, "source_shards": source_shards}
    return (value, state) if return_state else value


def _default_origin_build(persona_id, origin, *, return_state=False):
    cached = _cached_assignment_inputs()
    opening_cached = _input_fingerprint(cached)
    inputs = copy.deepcopy(cached)
    opening_detached = _input_fingerprint(inputs)
    try:
        result = _build_origin_manifest(
            inputs,
            persona_id,
            origin,
            source_origin_provider=source_package.build_source_intent_origin_manifest,
            source_body_provider=source_package.source_intent_shard_body_bytes,
            concrete_origin_provider=concrete.build_concrete_overlay_membership_origin_manifest,
            concrete_body_provider=concrete.concrete_overlay_membership_shard_body_bytes,
            return_state=return_state,
        )
    finally:
        _reauth_inputs(inputs, opening_detached, label="detached dependencies")
        _reauth_inputs(cached, opening_cached, label="cached dependencies")
    return result


@functools.lru_cache(maxsize=40)
def _canonical_origin_manifest(persona_id, origin):
    return _default_origin_build(persona_id, origin)


def build_source_parameter_assignment_origin_manifest(persona_id, origin):
    return copy.deepcopy(_canonical_origin_manifest(persona_id, origin))


@functools.lru_cache(maxsize=1)
def _expanded_origin_state(persona_id, origin):
    _, state = _default_origin_build(persona_id, origin, return_state=True)
    return state


def iter_source_parameter_assignment_rows(persona_id, origin, shard_ordinal):
    """Yield one authenticated shard's exact two-field expanded view."""

    _require_persona_id(persona_id)
    _require_origin(origin)
    if type(shard_ordinal) is not int or shard_ordinal < 1:
        _fail("shard ordinal must be a positive exact integer")
    state = _expanded_origin_state(persona_id, origin)
    matches = [
        rows
        for descriptor, rows in state["source_shards"]
        if descriptor["shard_ordinal"] == shard_ordinal
    ]
    if len(matches) != 1:
        _fail(f"unknown assignment shard: {persona_id}/{origin}/{shard_ordinal}")
    for intent_key, _ in matches[0]:
        yield {
            "intent_key": intent_key,
            "parameter_cell_key": state["assignments"][intent_key],
        }


def source_parameter_assignment_expanded_view_body_bytes(
    persona_id, origin, shard_ordinal
):
    parts = []
    for row in iter_source_parameter_assignment_rows(
        persona_id, origin, shard_ordinal
    ):
        _, raw = _expanded_row(row["intent_key"], row["parameter_cell_key"])
        parts.append(raw)
    if not parts:
        _fail("expanded assignment view cannot be empty")
    return b"".join(parts)


def _origin_manifest_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-instance-parameter-assignment-origin-manifest",
        role="immutable-compact-origin-assignment-owner",
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        coordinate_fields=("persona_id", "origin"),
    )


def _profile_origins(profile):
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


@functools.lru_cache(maxsize=40)
def _canonical_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    _require_profile(profile)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for origin in _profile_origins(profile)
    ]
    bindings = [_origin_manifest_binding(value) for value in origins]
    counts = {}
    for origin_value in origins:
        for row in origin_value["compact_assignment_rows"]:
            target = counts.setdefault(
                row["parameter_cell_key"],
                {
                    "eml_fixed_intent_count": 0,
                    "exact_pair_endpoint_count": 0,
                    "exact_pair_unit_count": 0,
                    "singleton_intent_count": 0,
                    "source_count": 0,
                },
            )
            for field in target:
                target[field] += row[field]
    projection = _canonical_cell_projection(persona_id)
    count_field = "pilot" if profile == "pilot" else "full"
    expected = {
        row["parameter_cell_key"]: row["counts"][count_field]
        for row in projection["cell_count_rows"]
        if row["counts"][count_field]
    }
    if {key: row["source_count"] for key, row in counts.items()} != expected:
        _fail(f"{persona_id}/{profile} origin union differs from cell projection")
    profile_rows = [
        {"parameter_cell_key": key, **counts[key]}
        for key in expected
    ]
    if any(
        row["source_count"]
        != row["exact_pair_endpoint_count"]
        + row["singleton_intent_count"]
        + row["eml_fixed_intent_count"]
        or row["exact_pair_endpoint_count"] != 2 * row["exact_pair_unit_count"]
        for row in profile_rows
    ):
        _fail("profile exact origin-union count equation did not close")
    value = {
        **_common_envelope(
            PROFILE_MANIFEST_KIND,
            PROFILE_MANIFEST_SCHEMA,
            "one-persona-profile-exact-origin-union-manifest-only-no-fresh-full-hamilton-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "max_body_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_profile_source_parameters_bound": True,
            "expanded_assignment_bodies_persisted": False,
            "formal_complete_persona_package_cap_proved": False,
            "full_is_exact_pilot_origin_reuse_plus_residual_union": profile == "full",
            "fresh_full_hamilton_recomputed": False,
        },
        "composition_contract": {
            "full_origin_order": list(ORIGIN_ORDER),
            "full_reuses_exact_pilot_origin_manifest": True,
            "full_rule": "exact-pilot-owner-body-plus-full-residual-owner-body-union",
            "independent_full_hamilton_allocation_allowed": False,
        },
        "input_binding_order": [
            "persona-v2-source-parameter-cell-projection",
            *[row["name"] for row in bindings],
        ],
        "input_bindings": [_projection_binding(persona_id), *bindings],
        "orders": {
            "origin_manifest_bindings": "pilot-only-or-pilot-then-full-residual",
            "profile_cell_count_rows": "persona-cell-projection-order-positive-profile-counts-only",
        },
        "origin_manifest_bindings": bindings,
        "persona_id": persona_id,
        "profile": profile,
        "profile_cell_count_rows": profile_rows,
        "remaining_blockers": [
            "frame-and-header-accounting-not-implemented",
            "formal-complete-persona-package-cap-not-proved",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
        ],
        "summary": {
            "active_parameter_cell_count": len(profile_rows),
            "exact_pair_unit_count": sum(
                row["summary"]["exact_pair_unit_count"] for row in origins
            ),
            "expanded_receipt_count": sum(
                row["summary"]["expanded_receipt_count"] for row in origins
            ),
            "origin_manifest_count": len(origins),
            "source_intent_count": sum(
                row["source_count"] for row in counts.values()
            ),
        },
    }
    canonical_json_bytes(value)
    return value


def build_source_parameter_assignment_profile_manifest(persona_id, profile):
    return copy.deepcopy(_canonical_profile_manifest(persona_id, profile))


def _profile_manifest_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-instance-parameter-assignment-profile-manifest",
        role="assignment-profile-origin-union-manifest",
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        coordinate_fields=("persona_id", "profile"),
    )


def _projection_manifest_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-parameter-cell-projection",
        role="persona-effective-cell-count-projection",
        max_bytes=MAX_CELL_PROJECTION_BYTES,
        coordinate_fields=("persona_id",),
    )


def _concrete_component_ledger(inputs, persona_id):
    matches = [
        row
        for row in inputs["concrete_suite"]["persona_current_component_byte_ledgers"]
        if row["persona_id"] == persona_id
    ]
    if len(matches) != 1:
        _fail("concrete overlay suite has no unique persona component ledger")
    return matches[0]


@functools.lru_cache(maxsize=1)
def _canonical_suite_descriptor():
    inputs = _cached_assignment_inputs()
    opening = _input_fingerprint(inputs)
    cell_catalog = _canonical_cell_catalog()
    projections = [
        _canonical_cell_projection(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    profiles = [
        _canonical_profile_manifest(persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    projection_bindings = [_projection_manifest_binding(row) for row in projections]
    origin_bindings = [_origin_manifest_binding(row) for row in origins]
    profile_bindings = [_profile_manifest_binding(row) for row in profiles]
    origins_by_key = {
        (row["persona_id"], row["origin"]): row for row in origins
    }
    profiles_by_key = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    projections_by_persona = {row["persona_id"]: row for row in projections}

    cell_catalog_raw = canonical_json_bytes(cell_catalog)
    direct_parameter_input_names = (
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
        "persona-v2-formal-source-recipe-profile-catalog",
    )
    direct_parameter_input_bytes = sum(
        EXPECTED_DEPENDENCY_PINS[name][0]
        for name in direct_parameter_input_names
    )
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        projection = projections_by_persona[persona_id]
        persona_origins = [
            origins_by_key[(persona_id, origin)] for origin in ORIGIN_ORDER
        ]
        persona_profiles = [
            profiles_by_key[(persona_id, profile)] for profile in PROFILE_ORDER
        ]
        projection_bytes = len(canonical_json_bytes(projection))
        origin_bytes = sum(len(canonical_json_bytes(row)) for row in persona_origins)
        profile_bytes = sum(len(canonical_json_bytes(row)) for row in persona_profiles)
        local_parameter_bytes = (
            len(cell_catalog_raw) + projection_bytes + origin_bytes + profile_bytes
        )
        concrete_component = _concrete_component_ledger(inputs, persona_id)
        parameter_extension_bytes = (
            direct_parameter_input_bytes + local_parameter_bytes
        )
        known_pre_solve_bytes = (
            concrete_component["current_component_bytes"]
            + parameter_extension_bytes
        )
        ledgers.append(
            {
                "expanded_view_body_bytes_excluded_nonpersisted": sum(
                    row["summary"]["expanded_body_bytes_nonpersisted"]
                    for row in persona_origins
                ),
                "formal_complete_persona_package_cap_proved": False,
                "frame_and_header_bytes_included": False,
                "known_pre_solve_component_bytes": known_pre_solve_bytes,
                "max_pre_solve_persona_package_bytes": source_package.MAX_PERSONA_PACKAGE_BYTES,
                "origin_manifest_bytes_including_compact_owner_rows": origin_bytes,
                "parameter_cell_projection_bytes": projection_bytes,
                "parameter_extension_bytes": parameter_extension_bytes,
                "persona_id": persona_id,
                "persona_recipe_projection_coalesced_no_separate_body": True,
                "profile_manifest_bytes": profile_bytes,
                "remaining_bytes_before_nominal_cap_not_a_completion_proof": (
                    source_package.MAX_PERSONA_PACKAGE_BYTES - known_pre_solve_bytes
                ),
                "shared_parameter_cell_catalog_bytes_charged_once": len(cell_catalog_raw),
                "shared_direct_parameter_input_body_bytes_charged_once": direct_parameter_input_bytes,
                "shared_direct_parameter_input_names": list(
                    direct_parameter_input_names
                ),
                "upstream_concrete_current_component_bytes": concrete_component[
                    "current_component_bytes"
                ],
                "compact_owner_rows_coalesced_in_origin_manifest": True,
                "separate_recipe_or_owner_body_bytes_charged": 0,
            }
        )
    if any(
        row["remaining_bytes_before_nominal_cap_not_a_completion_proof"] < 0
        for row in ledgers
    ):
        _fail("known source and parameter components exceed the persona cap")

    pilot_pair_count = sum(
        row["summary"]["exact_pair_unit_count"]
        for row in origins
        if row["origin"] == "pilot"
    )
    residual_pair_count = sum(
        row["summary"]["exact_pair_unit_count"]
        for row in origins
        if row["origin"] == "full-residual"
    )
    source_count = sum(
        profiles_by_key[(persona_id, "full")]["summary"]["source_intent_count"]
        for persona_id in envelope.PERSONA_IDS
    )
    pilot_source_count = sum(
        row["summary"]["source_intent_count"]
        for row in origins
        if row["origin"] == "pilot"
    )
    residual_source_count = sum(
        row["summary"]["source_intent_count"]
        for row in origins
        if row["origin"] == "full-residual"
    )
    owner_row_count = sum(len(row["compact_assignment_rows"]) for row in origins)
    receipt_count = sum(len(row["expanded_view_receipts"]) for row in origins)
    expanded_bytes = sum(
        row["summary"]["expanded_body_bytes_nonpersisted"] for row in origins
    )
    max_expanded_body = max(
        receipt["expanded_body_bytes"]
        for row in origins
        for receipt in row["expanded_view_receipts"]
    )
    max_expanded_row = max(
        receipt["maximum_row_bytes_including_lf"]
        for row in origins
        for receipt in row["expanded_view_receipts"]
    )
    pair_coordinates = sum(
        row["summary"]["pair_bearing_persona_origin_variant_coordinate_count"]
        for row in origins
    )
    eml_source_count = sum(
        row["source_count"]
        for origin_value in origins
        for row in origin_value["compact_assignment_rows"]
        if row["variant_id"] == "eml"
    )
    eml_host_count = sum(
        row["summary"]["eml_fixed_host_intent_count"] for row in origins
    )
    eml_nonhost_count = sum(
        row["summary"]["eml_fixed_nonhost_intent_count"] for row in origins
    )
    eml_membership_count = sum(
        row["summary"]["eml_attachment_membership_count"] for row in origins
    )
    non_eml_singleton_count = sum(
        compact["singleton_intent_count"]
        for origin_value in origins
        for compact in origin_value["compact_assignment_rows"]
        if compact["variant_id"] != "eml"
    )
    if (
        source_count != EXPECTED_SOURCE_COUNT
        or pilot_source_count != EXPECTED_PILOT_SOURCE_COUNT
        or residual_source_count != EXPECTED_RESIDUAL_SOURCE_COUNT
        or source_count != pilot_source_count + residual_source_count
        or owner_row_count != EXPECTED_ORIGIN_OWNER_ROW_COUNT
        or receipt_count != EXPECTED_SOURCE_SHARD_COUNT
        or pilot_pair_count != EXPECTED_PILOT_EXACT_PAIR_COUNT
        or residual_pair_count != EXPECTED_RESIDUAL_EXACT_PAIR_COUNT
        or pilot_pair_count + residual_pair_count != EXPECTED_EXACT_PAIR_COUNT
        or pair_coordinates != EXPECTED_PAIR_BEARING_COORDINATE_COUNT
        or expanded_bytes != EXPECTED_EXPANDED_BODY_BYTES
        or max_expanded_body != EXPECTED_MAX_EXPANDED_BODY_BYTES
        or max_expanded_row != EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF
        or eml_source_count != EXPECTED_EML_SOURCE_COUNT
        or eml_host_count != EXPECTED_EML_HOST_COUNT
        or eml_nonhost_count != EXPECTED_EML_NONHOST_COUNT
        or eml_membership_count != EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT
        or non_eml_singleton_count != EXPECTED_NON_EML_SINGLETON_COUNT
        or 2 * (pilot_pair_count + residual_pair_count)
        + non_eml_singleton_count
        + eml_source_count
        != EXPECTED_SOURCE_COUNT
    ):
        _fail("suite source/pair/owner/expanded-view exact totals drifted")
    active_counts = [
        row["summary"]["active_parameter_cell_count"] for row in projections
    ]
    if (
        sum(active_counts) != EXPECTED_PERSONA_CELL_COUNT
        or min(active_counts) != 107
        or max(active_counts) != 146
    ):
        _fail("persona parameter-cell projection cardinalities drifted")

    direct_names = [
        "persona-v2-source-inventory-layout",
        "persona-v2-source-inventory-suite",
        "persona-v2-concrete-overlay-membership-suite",
    ]
    direct_bindings = _selected_shared_bindings(inputs, direct_names)
    suite_inputs = [_cell_catalog_binding(), *direct_bindings]
    value = {
        **_common_envelope(
            SUITE_KIND,
            SUITE_SCHEMA,
            "all-203000-pre-solve-source-content-parameter-assignments-via-compact-origin-owners-and-73-nonpersisted-expanded-view-receipts-only-no-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "max_body_bytes": MAX_SUITE_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_203000_source_instance_parameters_bound": True,
            "all_40_compact_origin_owners_bound": True,
            "all_40_profile_origin_unions_bound": True,
            "all_73_expanded_view_receipts_bound": True,
            "all_expanded_assignment_bodies_persisted": False,
            "all_full_profiles_exact_pilot_plus_residual_union": True,
            "all_current_assignment_parameter_component_bytes_reported": True,
            "formal_complete_persona_package_cap_proved": False,
            "frame_and_header_implemented": False,
            "scope_bucket_cohort_chunk_quota_or_final_ids_present": False,
        },
        "coverage": {
            "active_parameter_cell_count_maximum_per_persona": max(active_counts),
            "active_parameter_cell_count_minimum_per_persona": min(active_counts),
            "active_parameter_cell_count_suite_sum": sum(active_counts),
            "compact_origin_assignment_row_count": owner_row_count,
            "concrete_exact_duplicate_pair_count": pilot_pair_count + residual_pair_count,
            "eml_attachment_membership_count": eml_membership_count,
            "eml_fixed_host_source_count": eml_host_count,
            "eml_fixed_nonhost_source_count": eml_nonhost_count,
            "eml_source_count": eml_source_count,
            "expanded_body_bytes_nonpersisted": expanded_bytes,
            "expanded_receipt_count": receipt_count,
            "global_parameter_cell_count": len(cell_catalog["parameter_cells"]),
            "maximum_expanded_body_bytes": max_expanded_body,
            "maximum_expanded_row_bytes_including_lf": max_expanded_row,
            "origin_manifest_count": len(origins),
            "non_eml_singleton_source_count": non_eml_singleton_count,
            "pair_bearing_persona_origin_variant_coordinate_count": pair_coordinates,
            "persona_count": len(envelope.PERSONA_IDS),
            "pilot_exact_duplicate_pair_count": pilot_pair_count,
            "pilot_source_intent_count": pilot_source_count,
            "profile_manifest_count": len(profiles),
            "residual_exact_duplicate_pair_count": residual_pair_count,
            "residual_source_intent_count": residual_source_count,
            "source_intent_count": source_count,
        },
        "dependency_direction_contract": {
            "base_eml_bins_are_not_effective_cells": True,
            "compact_owner_rows_are_embedded_once_in_origin_manifests": True,
            "compact_owner_separate_body_persisted": False,
            "evaluation_query_or_oracle_imported": False,
            "expanded_views_are_receipted_but_not_persisted": True,
            "full_assignment_is_origin_union_not_fresh_hamilton": True,
            "lifecycle_demand_or_solution_imported": False,
            "scope_bucket_cohort_chunk_quota_cell_local_ordinal_or_final_ids_allowed": False,
            "persona_recipe_projection_is_shared_cell_recipe_fields_plus_persona_active_foreign_keys_and_counts": True,
            "separate_persona_recipe_projection_body_persisted": False,
        },
        "input_binding_order": [row["name"] for row in suite_inputs],
        "input_bindings": suite_inputs,
        "orders": {
            "origin_manifest_bindings": "persona-then-pilot-full-residual",
            "persona_cell_projection_bindings": "persona-id",
            "profile_manifest_bindings": "persona-then-pilot-full",
        },
        "origin_manifest_bindings": origin_bindings,
        "persona_cell_projection_bindings": projection_bindings,
        "persona_parameter_component_byte_ledgers": ledgers,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": [
            "frame-and-header-accounting-not-implemented",
            "formal-complete-pre-solve-persona-package-cap-not-proved",
            "semantic-payload-and-lifecycle-effective-membership-not-bound",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
            "render-write-observation-history-kcs-root-capacity-and-g0-absent",
        ],
    }
    _reauth_inputs(inputs, opening, label="suite dependencies")
    canonical_json_bytes(value)
    return value


def build_source_parameter_assignment_suite_descriptor():
    return copy.deepcopy(_canonical_suite_descriptor())


def canonical_json_bytes(value):
    if type(value) is not dict:
        _fail("source parameter assignment artifact must be an object")
    schema = value.get("artifact_schema")
    labels = {
        CELL_CATALOG_SCHEMA: (
            "persona v2 source parameter cell catalog",
            MAX_CELL_CATALOG_BYTES,
        ),
        CELL_PROJECTION_SCHEMA: (
            "persona v2 source parameter cell projection",
            MAX_CELL_PROJECTION_BYTES,
        ),
        ORIGIN_MANIFEST_SCHEMA: (
            "persona v2 source parameter assignment origin manifest",
            MAX_ORIGIN_MANIFEST_BYTES,
        ),
        PROFILE_MANIFEST_SCHEMA: (
            "persona v2 source parameter assignment profile manifest",
            MAX_PROFILE_MANIFEST_BYTES,
        ),
        SUITE_SCHEMA: (
            "persona v2 source parameter assignment suite",
            MAX_SUITE_BYTES,
        ),
    }
    if schema not in labels:
        _fail(f"unknown source parameter assignment schema: {schema!r}")
    label, maximum = labels[schema]
    return _canonical_fragment(value, label=label, max_bytes=maximum)


def validate_source_parameter_cell_catalog(value):
    expected = build_source_parameter_cell_catalog()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("parameter cell catalog differs from exact regeneration")
    return True


def validate_source_parameter_cell_projection(persona_id, value):
    expected = build_source_parameter_cell_projection(persona_id)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("parameter cell projection differs from exact regeneration")
    return True


def validate_source_parameter_assignment_origin_manifest(
    persona_id, origin, value
):
    expected = build_source_parameter_assignment_origin_manifest(persona_id, origin)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("assignment origin manifest differs from exact regeneration")
    return True


def validate_source_parameter_assignment_profile_manifest(
    persona_id, profile, value
):
    expected = build_source_parameter_assignment_profile_manifest(persona_id, profile)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        _fail("assignment profile manifest differs from exact regeneration")
    return True


def validate_source_parameter_assignment_suite_descriptor(value):
    try:
        from . import persona_v2_source_parameter_assignment_package_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_source_parameter_assignment_package_validator as independent
    try:
        independent.validate_source_parameter_assignment_suite_descriptor(value)
    except independent.PersonaV2SourceParameterAssignmentValidationError as error:
        raise PersonaV2SourceParameterAssignmentPackageError(str(error)) from None
    return True


def source_parameter_assignment_suite_sha256(value=None):
    if value is None:
        value = build_source_parameter_assignment_suite_descriptor()
    validate_source_parameter_assignment_suite_descriptor(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_complete_source_parameter_assignment_package():
    raise PersonaV2SourceParameterAssignmentPackageError(
        "all 203,000 pre-solve content parameter assignments and 73 expanded-view "
        "receipts are exact, but frame/header and the complete 16-MiB persona-package "
        "proof are absent, and semantic payload, "
        "placement, rendering, history, KCS, root capacity, and G0 remain blocked"
    )


__all__ = [
    "AUTHORITY_FIELDS",
    "CELL_CATALOG_SCHEMA",
    "CELL_PROJECTION_SCHEMA",
    "MAX_CELL_CATALOG_BYTES",
    "MAX_CELL_PROJECTION_BYTES",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_SUITE_BYTES",
    "ORIGIN_MANIFEST_SCHEMA",
    "PROFILE_MANIFEST_SCHEMA",
    "PersonaV2SourceParameterAssignmentPackageError",
    "SUITE_SCHEMA",
    "build_source_parameter_assignment_origin_manifest",
    "build_source_parameter_assignment_profile_manifest",
    "build_source_parameter_assignment_suite_descriptor",
    "build_source_parameter_cell_catalog",
    "build_source_parameter_cell_projection",
    "canonical_json_bytes",
    "iter_source_parameter_assignment_rows",
    "require_complete_source_parameter_assignment_package",
    "source_parameter_assignment_expanded_view_body_bytes",
    "source_parameter_assignment_suite_sha256",
    "validate_source_parameter_assignment_origin_manifest",
    "validate_source_parameter_assignment_profile_manifest",
    "validate_source_parameter_assignment_suite_descriptor",
    "validate_source_parameter_cell_catalog",
    "validate_source_parameter_cell_projection",
]
