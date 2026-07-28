"""Independent validator for persona-PC v2 source parameter assignment.

The implementation deliberately shares no code with the assignment producer.
It re-authenticates the six direct upstream artifacts, reconstructs effective
parameter cells, compact origin allocations, all seventy-three expanded-view
receipts, profile unions, and byte ledgers, then requires byte-identical suite
output.  Expanded assignment bodies remain transient verification views.
"""

from __future__ import annotations

import copy
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


CELL_CATALOG_SCHEMA = "kio.persona.pc-source-parameter-cell-catalog/v2"
CELL_CATALOG_KIND = "persona-pc-v2-source-parameter-cell-catalog"
CELL_PROJECTION_SCHEMA = "kio.persona.pc-source-parameter-cell-projection/v2"
CELL_PROJECTION_KIND = "persona-pc-v2-source-parameter-cell-projection"
ORIGIN_SCHEMA = (
    "kio.persona.pc-source-instance-parameter-assignment-origin-manifest/v2"
)
ORIGIN_KIND = "persona-pc-v2-source-instance-parameter-assignment-origin-manifest"
PROFILE_SCHEMA = (
    "kio.persona.pc-source-instance-parameter-assignment-profile-manifest/v2"
)
PROFILE_KIND = "persona-pc-v2-source-instance-parameter-assignment-profile-manifest"
SUITE_SCHEMA = "kio.persona.pc-source-instance-parameter-assignment-suite/v2"
SUITE_KIND = "persona-pc-v2-source-instance-parameter-assignment-suite"
SCHEMA_VERSION = 2

ORIGINS = ("pilot", "full-residual")
PROFILES = ("pilot", "full")
NON_EML_BINS = (
    "floor",
    "small",
    "medium",
    "large",
    "ordinary-max",
    "formal-tail",
)
EML_BINS = tuple(f"attachment-{value}" for value in range(6))

MAX_CELL_CATALOG_BYTES = 256 * 1024
MAX_CELL_PROJECTION_BYTES = 128 * 1024
MAX_ORIGIN_BYTES = 512 * 1024
MAX_PROFILE_BYTES = 128 * 1024
MAX_SUITE_BYTES = 512 * 1024
MAX_EXPANDED_ROW_BYTES = 256

EXPECTED_SUITE_CANONICAL_BYTES = 72_535
EXPECTED_SUITE_SHA256 = (
    "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a"
)
EXPECTED_DEPENDENCY_PINS = {
    "persona-v2-source-inventory-layout": (
        274_566,
        "81fcec92df932d9357b5202a6eda3f6c11ac9bd70762a281cbc2d094d6e8579a",
    ),
    "persona-v2-source-inventory-suite": (
        45_887,
        "9f216f3d986bdc92f7b07e0d2bfe266dc03df46d990f8ded706ad802d227edc3",
    ),
    "persona-v2-formal-source-recipe-profile-catalog": (
        386_152,
        "0ac0906397c8d81b7504637fe119d45ae2ffa7acb7cb47b719c985121ce1b2df",
    ),
    "persona-v2-aggregate-byte-distribution-catalog": (
        1_576_125,
        "9bef8b1af10411bb1e8cc662aa95a64e155ea81e3db7e1be56433e83539450d2",
    ),
    "persona-v2-overlay-compatible-byte-distribution": (
        91_039,
        "a9e214e5dde82edf4967d5502f15fd92ffa6a1016c67a177dd574835a9962ddc",
    ),
    "persona-v2-concrete-overlay-membership-suite": (
        51_133,
        "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737",
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
        "authorizes_kio_execution",
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
        "kio_execution_available",
        "query_instances_rendered",
        "renderer_available",
        "root_bound_capacity_attested",
    }
)

FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "bucket",
        "bucket_id",
        "bucket_key",
        "cell_local_ordinal",
        "chunk_quota",
        "cohort",
        "cohort_id",
        "cohort_key",
        "final_id",
        "final_materialization_id",
        "final_source_id",
        "lifecycle_demand_id",
        "lifecycle_demand",
        "materialization_id",
        "materialization_key",
        "oracle_id",
        "oracle",
        "answer",
        "path",
        "payload",
        "query_id",
        "query",
        "quota",
        "scope",
        "scope_id",
        "scope_key",
        "requested_chunks",
        "raw_hash",
        "semantic_payload",
        "source_id",
        "source_key",
    }
)


class PersonaV2SourceParameterAssignmentValidationError(ValueError):
    """Raised when independent assignment reconstruction rejects an artifact."""


def _fail(message):
    raise PersonaV2SourceParameterAssignmentValidationError(message)


def _canon(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=maximum
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceParameterAssignmentValidationError(str(error)) from None


def _suite_bytes(value):
    return _canon(
        value,
        label="persona v2 source parameter assignment suite",
        maximum=MAX_SUITE_BYTES,
    )


def _reject_forbidden_keys(value, *, path="$"):
    if type(value) is dict:
        for key, child in value.items():
            if key in FORBIDDEN_EXACT_KEYS:
                _fail(f"forbidden solved/evaluation namespace at {path}.{key}")
            _reject_forbidden_keys(child, path=f"{path}.{key}")
    elif type(value) is list:
        for index, child in enumerate(value):
            _reject_forbidden_keys(child, path=f"{path}[{index}]")


def _all_false_authority(value, *, label):
    authority = value.get("authority") if type(value) is dict else None
    if (
        value.get("g0_contract_frozen") is not False
        or type(authority) is not dict
        or set(authority) != AUTHORITY_FIELDS
        or any(type(flag) is not bool or flag is not False for flag in authority.values())
    ):
        _fail(f"{label} authority must be exact all-false and non-G0")


def _ascii(value):
    if type(value) is not str:
        _fail("assignment key must be a string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("assignment key must be ASCII")


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _common(kind, schema, completion_scope):
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": SCHEMA_VERSION,
        "authority": _negative_authority(),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "completion_scope": completion_scope,
    }


def _dependency_specs():
    return (
        (
            "source_layout",
            "persona-v2-source-inventory-layout",
            "exact-source-key-ranges-and-canonical-shard-order",
            source_layout.build_source_inventory_layout,
            source_layout.validate_source_inventory_layout,
            source_layout.canonical_json_bytes,
        ),
        (
            "source_suite",
            "persona-v2-source-inventory-suite",
            "authenticated-203000-source-intents-and-73-shard-bodies",
            source_package.build_source_intent_suite_descriptor,
            source_package.validate_source_intent_suite_descriptor,
            source_package.canonical_json_bytes,
        ),
        (
            "formal",
            "persona-v2-formal-source-recipe-profile-catalog",
            "all-71-recipe-profile-and-variant-order-owner",
            formal.build_formal_source_recipe_catalog,
            formal.validate_formal_source_recipe_catalog,
            formal.canonical_json_bytes,
        ),
        (
            "aggregate",
            "persona-v2-aggregate-byte-distribution-catalog",
            "immutable-non-eml-parameter-cell-histograms",
            aggregate.build_aggregate_byte_distribution_catalog,
            aggregate.validate_aggregate_byte_distribution_catalog,
            aggregate.canonical_json_bytes,
        ),
        (
            "effective",
            "persona-v2-overlay-compatible-byte-distribution",
            "effective-eml-attachment-zero-through-five-histograms",
            effective.build_overlay_compatible_byte_distribution,
            effective.validate_overlay_compatible_byte_distribution,
            effective.canonical_json_bytes,
        ),
        (
            "concrete_suite",
            "persona-v2-concrete-overlay-membership-suite",
            "exact-duplicate-and-eml-host-membership-owner",
            concrete.build_concrete_overlay_membership_suite_descriptor,
            concrete.validate_concrete_overlay_membership_suite_descriptor,
            concrete.canonical_json_bytes,
        ),
    )


def _resolve_inputs(overrides):
    originals = {}
    bindings = []
    canonicalizers = {}
    for key, name, role, builder, validator, canonical in _dependency_specs():
        value = overrides.get(key)
        if value is None:
            value = builder()
        try:
            validator(value)
            raw = canonical(value)
        except Exception as error:
            raise PersonaV2SourceParameterAssignmentValidationError(
                f"{name} failed direct authentication"
            ) from error
        actual = (len(raw), hashlib.sha256(raw).hexdigest())
        if actual != EXPECTED_DEPENDENCY_PINS[name]:
            _fail(f"{name} differs from its frozen dependency pin")
        originals[key] = value
        canonicalizers[key] = canonical
        bindings.append(
            {
                "artifact_kind": value["artifact_kind"],
                "artifact_schema": value["artifact_schema"],
                "artifact_schema_version": value["artifact_schema_version"],
                "canonical_bytes": actual[0],
                "dependency_role": role,
                "name": name,
                "sha256": actual[1],
            }
        )
    opening = tuple(
        canonicalizers[key](originals[key])
        for key, *_ in _dependency_specs()
    )
    inputs = {key: copy.deepcopy(value) for key, value in originals.items()}
    inputs["bindings"] = bindings
    return originals, canonicalizers, opening, inputs


def _reauth_originals(originals, canonicalizers, opening):
    current = tuple(
        canonicalizers[key](originals[key])
        for key, *_ in _dependency_specs()
    )
    if len(current) != len(opening) or any(
        not hmac.compare_digest(actual, expected)
        for actual, expected in zip(current, opening)
    ):
        _fail("upstream artifact mutated during provider callbacks")


def _binding_subset(inputs, names):
    by_name = {row["name"]: row for row in inputs["bindings"]}
    if set(by_name) != set(EXPECTED_DEPENDENCY_PINS):
        _fail("dependency binding coverage drifted")
    return [copy.deepcopy(by_name[name]) for name in names]


def _variant_order(inputs):
    result = tuple(
        row["variant_id"] for row in inputs["formal"]["recipe_profile_rows"]
    )
    if len(result) != 71 or len(set(result)) != 71 or "eml" not in result:
        _fail("formal variant order is not exact")
    return result


def _cell_key(variant_id, bin_id):
    if type(variant_id) is not str or type(bin_id) is not str:
        _fail("parameter-cell components must be strings")
    if "/" in variant_id or "/" in bin_id:
        _fail("parameter-cell components cannot contain slash")
    return f"{variant_id}/{bin_id}"


def _definition(row, parameter_bin):
    recipe_field = (
        "base_recipe_profile_id" if row["variant_id"] == "eml"
        else "recipe_profile_id"
    )
    return {
        "bin_id": parameter_bin["bin_id"],
        "parameter_cell_key": _cell_key(
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
    order = _variant_order(inputs)
    index = {variant_id: position for position, variant_id in enumerate(order)}
    rows = {
        (row["persona_id"], row["variant_id"]): row
        for row in inputs["aggregate"]["persona_variant_rows"]
        if row["variant_id"] != "eml"
    }
    rows.update(
        {
            (row["persona_id"], "eml"): row
            for row in inputs["effective"]["eml_override_rows"]
        }
    )
    if len(rows) != 566:
        _fail("effective persona/variant coverage is not 566")
    return {
        persona_id: sorted(
            [row for (pid, _), row in rows.items() if pid == persona_id],
            key=lambda row: index[row["variant_id"]],
        )
        for persona_id in envelope.PERSONA_IDS
    }


def _cell_catalog(inputs):
    definitions = {}
    effective_rows = _effective_rows(inputs)
    for persona_rows in effective_rows.values():
        for row in persona_rows:
            for parameter_bin in row["parameter_bins"]:
                definition = _definition(row, parameter_bin)
                key = definition["parameter_cell_key"]
                previous = definitions.setdefault(key, definition)
                if previous != definition:
                    _fail("global parameter-cell definition varies by persona")
    ordered = []
    for variant_id in _variant_order(inputs):
        bins = EML_BINS if variant_id == "eml" else NON_EML_BINS
        for bin_id in bins:
            key = _cell_key(variant_id, bin_id)
            if key in definitions:
                ordered.append(definitions.pop(key))
    if definitions or len(ordered) != 363:
        _fail("global parameter-cell catalog is not exactly 363 cells")
    names = [
        "persona-v2-formal-source-recipe-profile-catalog",
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
    ]
    value = {
        **_common(
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
        "input_binding_order": names,
        "input_bindings": _binding_subset(inputs, names),
        "orders": {
            "parameter_cells": (
                "formal-variant-order-then-non-eml-floor-small-medium-large-"
                "ordinary-max-formal-tail-or-eml-attachment-zero-through-five"
            )
        },
        "parameter_cells": ordered,
        "remaining_blockers": [
            "source-instance-cell-assignment-not-in-this-shared-catalog",
            "frame-and-header-accounting-not-implemented",
            "scope-bucket-cohort-chunk-quota-and-final-id-solution-unbound",
            "render-write-observation-history-kio-capacity-and-g0-absent",
        ],
        "summary": {
            "eml_parameter_cell_count": 6,
            "non_eml_parameter_cell_count": 357,
            "parameter_cell_count": 363,
            "variant_count": 71,
        },
    }
    _canon(value, label="independent cell catalog", maximum=MAX_CELL_CATALOG_BYTES)
    return value


def _artifact_binding(value, *, name, role, maximum, coordinates=()):
    raw = _canon(value, label=name, maximum=maximum)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    for field in coordinates:
        result[field] = value[field]
    return result


def _cell_catalog_binding(cell_catalog):
    return _artifact_binding(
        cell_catalog,
        name="persona-v2-source-parameter-cell-catalog",
        role="shared-explicit-parameter-cell-definition-owner",
        maximum=MAX_CELL_CATALOG_BYTES,
    )


def _cell_projection(inputs, cell_catalog, persona_id):
    rows = []
    for row in _effective_rows(inputs)[persona_id]:
        for parameter_bin in row["parameter_bins"]:
            counts = copy.deepcopy(parameter_bin["counts"])
            if counts["full"] == 0:
                continue
            if counts["full"] != counts["pilot"] + counts["full-residual"]:
                _fail("persona cell count does not close pilot plus residual")
            definition = _definition(row, parameter_bin)
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
    bindings = [
        _cell_catalog_binding(cell_catalog),
        *_binding_subset(inputs, distribution_names),
    ]
    value = {
        **_common(
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
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
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
                profile: sum(item["counts"][profile] for item in rows)
                for profile in ("pilot", "full-residual", "full")
            },
        },
    }
    _canon(value, label="independent cell projection", maximum=MAX_CELL_PROJECTION_BYTES)
    return value


def _coordinate_binding(suite, field, persona_id, origin):
    matches = [
        row
        for row in suite[field]
        if row.get("persona_id") == persona_id and row.get("origin") == origin
    ]
    if len(matches) != 1:
        _fail(f"no unique upstream origin binding: {persona_id}/{origin}")
    return matches[0]


def _origin_from_provider(
    inputs, persona_id, origin, provider, *, concrete_origin
):
    try:
        value = copy.deepcopy(provider(persona_id, origin))
        _reject_forbidden_keys(value, path="$upstream_origin")
        if concrete_origin:
            concrete.validate_concrete_overlay_membership_origin_manifest(
                persona_id, origin, value
            )
            raw = concrete.canonical_json_bytes(value)
            suite = inputs["concrete_suite"]
        else:
            source_package.validate_source_intent_origin_manifest(
                persona_id, origin, value
            )
            raw = source_package.canonical_json_bytes(value)
            suite = inputs["source_suite"]
    except Exception as error:
        raise PersonaV2SourceParameterAssignmentValidationError(
            "upstream origin provider failed authentication"
        ) from error
    expected = _coordinate_binding(
        suite, "origin_manifest_bindings", persona_id, origin
    )
    if (
        value.get("persona_id") != persona_id
        or value.get("origin") != origin
        or len(raw) != expected["canonical_bytes"]
        or not hmac.compare_digest(
            hashlib.sha256(raw).hexdigest(), expected["sha256"]
        )
    ):
        _fail("upstream origin differs from exact suite coordinate binding")
    return value, raw


def _body_from_provider(
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
        raise PersonaV2SourceParameterAssignmentValidationError(
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
        raise PersonaV2SourceParameterAssignmentValidationError(
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


def _jsonl(body, *, label, max_row_bytes):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        _fail(f"{label} must be nonempty LF-terminated bytes")
    rows = []
    for line in body.splitlines():
        if not line or len(line) + 1 > max_row_bytes:
            _fail(f"{label} has an empty or oversized row")
        try:
            row = json.loads(line.decode("utf-8", "strict"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PersonaV2SourceParameterAssignmentValidationError(
                f"{label} is not strict UTF-8 JSONL"
            ) from error
        if type(row) is not dict:
            _fail(f"{label} row must be an object")
        _reject_forbidden_keys(row, path=f"${label}_row")
        if _canon(row, label=f"{label} row", maximum=max_row_bytes - 1) != line:
            _fail(f"{label} row is not canonical JSON")
        rows.append(row)
    return rows


def _source_shards(inputs, persona_id, origin, manifest, provider):
    profile_map = {
        row["source_inventory_profile_id"]: row["variant_id"]
        for row in inputs["formal"]["recipe_profile_rows"]
    }
    if len(profile_map) != 71:
        _fail("formal source-profile join is not bijective")
    seen = set()
    result = []
    for descriptor in manifest["shard_descriptors"]:
        if descriptor["persona_id"] != persona_id or descriptor["origin"] != origin:
            _fail("source shard descriptor has the wrong coordinate")
        body = _body_from_provider(
            provider,
            (persona_id, origin, descriptor["shard_ordinal"]),
            label="source shard body",
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
        )
        rows = _jsonl(
            body,
            label="source shard",
            max_row_bytes=source_package.MAX_INTENT_ROW_BYTES_INCLUDING_LF,
        )
        if len(rows) != descriptor["row_count"]:
            _fail("source shard row count differs from descriptor")
        joined = []
        for row in rows:
            if set(row) != source_package.INTENT_ROW_FIELDS:
                _fail("source row field schema drifted")
            if row["persona_id"] != persona_id or row["origin"] != origin:
                _fail("source row coordinate drifted")
            intent_key = row["intent_key"]
            if intent_key in seen:
                _fail("source intent repeats across authenticated shards")
            seen.add(intent_key)
            variant_id = profile_map.get(row["source_profile_id"])
            if variant_id is None:
                _fail("source row has no formal variant join")
            joined.append((intent_key, variant_id))
        if (
            joined[0][0] != descriptor["first_intent_key"]
            or joined[-1][0] != descriptor["last_intent_key"]
        ):
            _fail("source shard endpoint receipt drifted")
        result.append((descriptor, joined))
    if len(seen) != manifest["summary"]["source_intent_count"]:
        _fail("source origin source count does not close")
    return result


def _concrete_rows(persona_id, origin, manifest, provider):
    result = []
    for descriptor in manifest["shard_descriptors"]:
        if descriptor["persona_id"] != persona_id or descriptor["origin"] != origin:
            _fail("concrete shard descriptor has the wrong coordinate")
        body = _body_from_provider(
            provider,
            (persona_id, origin, descriptor["shard_index"]),
            label="concrete shard body",
            expected_bytes=descriptor["body_bytes"],
            expected_sha256=descriptor["body_sha256"],
        )
        rows = _jsonl(
            body,
            label="concrete shard",
            max_row_bytes=concrete.MAX_ROW_BYTES_INCLUDING_LF,
        )
        if len(rows) != descriptor["row_count"]:
            _fail("concrete shard row count differs from descriptor")
        result.extend(rows)
    if len(result) != manifest["summary"]["rich_row_count"]:
        _fail("concrete origin rich rows do not close")
    return result


def _relations(source_shards, rows):
    variant_by_key = {
        key: variant
        for _, shard_rows in source_shards
        for key, variant in shard_rows
    }
    pairs = []
    hosts = {}
    ordinals = {}
    for row in rows:
        if row.get("row_kind") == "content-relation-membership" and row.get(
            "relation_kind"
        ) == "exact-duplicate":
            anchor = row["anchor_intent_key"]
            derivative = row["derivative_intent_key"]
            variant = variant_by_key.get(anchor)
            if (
                variant is None
                or variant == "eml"
                or variant_by_key.get(derivative) != variant
                or anchor == derivative
            ):
                _fail("exact pair is not two distinct same-variant non-EML sources")
            pairs.append((anchor, derivative, row["cluster_key"], variant))
        elif row.get("row_kind") == "attachment-membership":
            host = row["host_intent_key"]
            count = row["host_member_count"]
            ordinal = row["member_ordinal"]
            if variant_by_key.get(host) != "eml" or count not in range(1, 6):
                _fail("attachment host does not join to EML complexity 1..5")
            if hosts.setdefault(host, count) != count:
                _fail("EML host declares inconsistent member counts")
            ordinals.setdefault(host, set()).add(ordinal)
    pairs.sort(key=lambda row: (_ascii(row[0]), _ascii(row[1]), _ascii(row[2])))
    endpoints = [key for row in pairs for key in row[:2]]
    if len(endpoints) != len(set(endpoints)):
        _fail("exact-pair endpoint repeats")
    if any(ordinals[key] != set(range(1, count + 1)) for key, count in hosts.items()):
        _fail("EML host ordinals do not close 1..N")
    return pairs, hosts


def _pair_apportionment(pair_count, cells):
    capacities = {
        row["parameter_cell_key"]: row["source_count"] // 2 for row in cells
    }
    denominator = sum(capacities.values())
    if type(pair_count) is not int or pair_count < 0 or pair_count > denominator:
        _fail("pair demand exceeds cell capacity")
    if pair_count == 0:
        return {key: 0 for key in capacities}
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
        _fail("independent Hamilton allocation failed exact capacity closure")
    return result


def _origin_cells(projection, origin):
    return [
        {
            "parameter_cell_key": row["parameter_cell_key"],
            "source_count": row["counts"][origin],
            "variant_id": row["variant_id"],
        }
        for row in projection["cell_count_rows"]
        if row["counts"][origin]
    ]


def _assignment(projection, origin, source_shards, concrete_rows):
    pairs, hosts = _relations(source_shards, concrete_rows)
    sources = {}
    for _, rows in source_shards:
        for key, variant in rows:
            sources.setdefault(variant, []).append(key)
    cells_by_variant = {}
    for row in _origin_cells(projection, origin):
        cells_by_variant.setdefault(row["variant_id"], []).append(row)
    pairs_by_variant = {}
    for pair in pairs:
        pairs_by_variant.setdefault(pair[3], []).append(pair)
    assigned = {}
    owners = []
    pair_coordinates = 0
    for variant_id, cells in cells_by_variant.items():
        intents = sources.get(variant_id, [])
        if sum(row["source_count"] for row in cells) != len(intents):
            _fail("variant source marginal differs from cell counts")
        if variant_id == "eml":
            for intent_key in intents:
                assigned[intent_key] = _cell_key(
                    "eml", f"attachment-{hosts.get(intent_key, 0)}"
                )
            for cell in cells:
                count = sum(
                    value == cell["parameter_cell_key"] for value in assigned.values()
                )
                if count != cell["source_count"]:
                    _fail("independent EML assignment differs from effective histogram")
                owners.append(
                    {
                        **cell,
                        "eml_fixed_intent_count": count,
                        "exact_pair_endpoint_count": 0,
                        "exact_pair_unit_count": 0,
                        "singleton_intent_count": 0,
                    }
                )
            continue
        variant_pairs = pairs_by_variant.get(variant_id, [])
        if variant_pairs:
            pair_coordinates += 1
        apportioned = _pair_apportionment(len(variant_pairs), cells)
        pair_index = 0
        paired = set()
        for cell in cells:
            count = apportioned[cell["parameter_cell_key"]]
            for pair in variant_pairs[pair_index : pair_index + count]:
                assigned[pair[0]] = cell["parameter_cell_key"]
                assigned[pair[1]] = cell["parameter_cell_key"]
                paired.update(pair[:2])
            pair_index += count
        if pair_index != len(variant_pairs):
            _fail("pair allocation left trailing pairs")
        singletons = sorted((key for key in intents if key not in paired), key=_ascii)
        singleton_index = 0
        for cell in cells:
            q = apportioned[cell["parameter_cell_key"]]
            count = cell["source_count"] - 2 * q
            for intent_key in singletons[singleton_index : singleton_index + count]:
                assigned[intent_key] = cell["parameter_cell_key"]
            singleton_index += count
            owners.append(
                {
                    **cell,
                    "eml_fixed_intent_count": 0,
                    "exact_pair_endpoint_count": 2 * q,
                    "exact_pair_unit_count": q,
                    "singleton_intent_count": count,
                }
            )
        if singleton_index != len(singletons):
            _fail("ASCII singleton fill did not close")
    all_keys = {key for _, rows in source_shards for key, _ in rows}
    if set(assigned) != all_keys:
        _fail("independent assignment is not total")
    for row in owners:
        if (
            row["source_count"]
            != row["exact_pair_endpoint_count"]
            + row["singleton_intent_count"]
            + row["eml_fixed_intent_count"]
            or row["exact_pair_endpoint_count"] != 2 * row["exact_pair_unit_count"]
        ):
            _fail("compact owner count equation failed")
    return assigned, owners, pairs, hosts, pair_coordinates


def _expanded_receipts(source_shards, assigned):
    receipts = []
    for descriptor, rows in source_shards:
        parts = []
        for intent_key, _ in rows:
            assignment_row = {
                "intent_key": intent_key,
                "parameter_cell_key": assigned[intent_key],
            }
            raw = _canon(
                assignment_row,
                label="independent expanded assignment row",
                maximum=MAX_EXPANDED_ROW_BYTES - 1,
            ) + b"\n"
            parts.append(raw)
        body = b"".join(parts)
        receipts.append(
            {
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
        )
    return receipts


def _projection_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-parameter-cell-projection",
        role="persona-effective-positive-cell-count-owner",
        maximum=MAX_CELL_PROJECTION_BYTES,
        coordinates=("persona_id",),
    )


def _origin(
    inputs,
    projection,
    persona_id,
    origin,
    *,
    source_origin_provider,
    source_body_provider,
    concrete_origin_provider,
    concrete_body_provider,
):
    source_origin, source_raw = _origin_from_provider(
        inputs,
        persona_id,
        origin,
        source_origin_provider,
        concrete_origin=False,
    )
    concrete_origin, concrete_raw = _origin_from_provider(
        inputs,
        persona_id,
        origin,
        concrete_origin_provider,
        concrete_origin=True,
    )
    source_shards = _source_shards(
        inputs, persona_id, origin, source_origin, source_body_provider
    )
    concrete_rows = _concrete_rows(
        persona_id, origin, concrete_origin, concrete_body_provider
    )
    assigned, owners, pairs, hosts, pair_coordinates = _assignment(
        projection, origin, source_shards, concrete_rows
    )
    receipts = _expanded_receipts(source_shards, assigned)

    source_after, source_after_raw = _origin_from_provider(
        inputs,
        persona_id,
        origin,
        source_origin_provider,
        concrete_origin=False,
    )
    concrete_after, concrete_after_raw = _origin_from_provider(
        inputs,
        persona_id,
        origin,
        concrete_origin_provider,
        concrete_origin=True,
    )
    if (
        source_origin != source_after
        or concrete_origin != concrete_after
        or not hmac.compare_digest(source_raw, source_after_raw)
        or not hmac.compare_digest(concrete_raw, concrete_after_raw)
    ):
        _fail("origin provider changed during reconstruction")

    shared_names = [
        "persona-v2-source-inventory-layout",
        "persona-v2-source-inventory-suite",
        "persona-v2-concrete-overlay-membership-suite",
    ]
    bindings = [
        _projection_binding(projection),
        *_binding_subset(inputs, shared_names),
        _artifact_binding(
            source_origin,
            name="persona-v2-source-inventory-origin-manifest",
            role="matching-authenticated-source-shard-descriptor-owner",
            maximum=source_package.MAX_ORIGIN_MANIFEST_BYTES,
            coordinates=("persona_id", "origin"),
        ),
        _artifact_binding(
            concrete_origin,
            name="persona-v2-concrete-overlay-membership-origin-manifest",
            role="matching-exact-pair-and-eml-host-membership-owner",
            maximum=concrete.MAX_ORIGIN_MANIFEST_BYTES,
            coordinates=("persona_id", "origin"),
        ),
    ]
    eml_source_count = sum(
        row["source_count"] for row in owners if row["variant_id"] == "eml"
    )
    value = {
        **_common(
            ORIGIN_KIND,
            ORIGIN_SCHEMA,
            "one-persona-one-origin-compact-content-parameter-owner-and-nonpersisted-expanded-view-receipts-only-no-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "expanded_jsonl_record_terminator": "LF",
            "max_body_bytes": MAX_ORIGIN_BYTES,
            "max_expanded_row_bytes_including_lf": MAX_EXPANDED_ROW_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "compact_assignment_rows": owners,
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
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
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
            "semantic-payload-render-write-observation-history-kio-and-g0-absent",
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
            "active_parameter_cell_count": len(owners),
            "eml_fixed_host_intent_count": len(hosts),
            "eml_attachment_membership_count": sum(hosts.values()),
            "eml_fixed_nonhost_intent_count": eml_source_count - len(hosts),
            "exact_pair_endpoint_count": 2 * len(pairs),
            "exact_pair_unit_count": len(pairs),
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
            "pair_bearing_persona_origin_variant_coordinate_count": pair_coordinates,
            "singleton_intent_count": sum(
                row["singleton_intent_count"] for row in owners
            ),
            "source_intent_count": len(assigned),
        },
    }
    if (
        sum(row["source_count"] for row in owners) != len(assigned)
        or sum(row["row_count"] for row in receipts) != len(assigned)
        or len(assigned) != source_origin["summary"]["source_intent_count"]
    ):
        _fail("origin source/owner/receipt counts do not close")
    _all_false_authority(value, label="independent origin")
    _reject_forbidden_keys(value, path="$expected_origin")
    _canon(value, label="independent origin", maximum=MAX_ORIGIN_BYTES)
    return value


def _origin_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-instance-parameter-assignment-origin-manifest",
        role="immutable-compact-origin-assignment-owner",
        maximum=MAX_ORIGIN_BYTES,
        coordinates=("persona_id", "origin"),
    )


def _profile(projection, persona_id, profile, origin_values):
    selected_origins = ("pilot",) if profile == "pilot" else ORIGINS
    selected = [origin_values[(persona_id, origin)] for origin in selected_origins]
    origin_bindings = [_origin_binding(row) for row in selected]
    counts = {}
    for origin_value in selected:
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
    count_field = "pilot" if profile == "pilot" else "full"
    expected_counts = {
        row["parameter_cell_key"]: row["counts"][count_field]
        for row in projection["cell_count_rows"]
        if row["counts"][count_field]
    }
    if {key: row["source_count"] for key, row in counts.items()} != expected_counts:
        _fail("profile origin union differs from effective cell projection")
    profile_rows = [
        {"parameter_cell_key": key, **counts[key]} for key in expected_counts
    ]
    if any(
        row["source_count"]
        != row["exact_pair_endpoint_count"]
        + row["singleton_intent_count"]
        + row["eml_fixed_intent_count"]
        or row["exact_pair_endpoint_count"] != 2 * row["exact_pair_unit_count"]
        for row in profile_rows
    ):
        _fail("profile compact union equation does not close")
    bindings = [_projection_binding(projection), *origin_bindings]
    value = {
        **_common(
            PROFILE_KIND,
            PROFILE_SCHEMA,
            "one-persona-profile-exact-origin-union-manifest-only-no-fresh-full-hamilton-placement-write-execution-or-g0",
        ),
        "canonical_limits": {
            "max_body_bytes": MAX_PROFILE_BYTES,
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
            "full_origin_order": list(ORIGINS),
            "full_reuses_exact_pilot_origin_manifest": True,
            "full_rule": "exact-pilot-owner-body-plus-full-residual-owner-body-union",
            "independent_full_hamilton_allocation_allowed": False,
        },
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "orders": {
            "origin_manifest_bindings": "pilot-only-or-pilot-then-full-residual",
            "profile_cell_count_rows": "persona-cell-projection-order-positive-profile-counts-only",
        },
        "origin_manifest_bindings": origin_bindings,
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
                row["summary"]["exact_pair_unit_count"] for row in selected
            ),
            "expanded_receipt_count": sum(
                row["summary"]["expanded_receipt_count"] for row in selected
            ),
            "origin_manifest_count": len(selected),
            "source_intent_count": sum(
                row["source_count"] for row in counts.values()
            ),
        },
    }
    _all_false_authority(value, label="independent profile")
    _reject_forbidden_keys(value, path="$expected_profile")
    _canon(value, label="independent profile", maximum=MAX_PROFILE_BYTES)
    return value


def _suite_projection_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-parameter-cell-projection",
        role="persona-effective-cell-count-projection",
        maximum=MAX_CELL_PROJECTION_BYTES,
        coordinates=("persona_id",),
    )


def _profile_binding(value):
    return _artifact_binding(
        value,
        name="persona-v2-source-instance-parameter-assignment-profile-manifest",
        role="assignment-profile-origin-union-manifest",
        maximum=MAX_PROFILE_BYTES,
        coordinates=("persona_id", "profile"),
    )


def _expected_suite(
    inputs,
    *,
    source_origin_provider,
    source_body_provider,
    concrete_origin_provider,
    concrete_body_provider,
):
    cell_catalog = _cell_catalog(inputs)
    projections = {
        persona_id: _cell_projection(inputs, cell_catalog, persona_id)
        for persona_id in envelope.PERSONA_IDS
    }
    origins = {
        (persona_id, origin): _origin(
            inputs,
            projections[persona_id],
            persona_id,
            origin,
            source_origin_provider=source_origin_provider,
            source_body_provider=source_body_provider,
            concrete_origin_provider=concrete_origin_provider,
            concrete_body_provider=concrete_body_provider,
        )
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGINS
    }
    profiles = {
        (persona_id, profile): _profile(
            projections[persona_id], persona_id, profile, origins
        )
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILES
    }
    ordered_origins = [
        origins[(persona_id, origin)]
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGINS
    ]
    ordered_profiles = [
        profiles[(persona_id, profile)]
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILES
    ]
    ordered_projections = [projections[persona_id] for persona_id in envelope.PERSONA_IDS]
    origin_bindings = [_origin_binding(row) for row in ordered_origins]
    profile_bindings = [_profile_binding(row) for row in ordered_profiles]
    projection_bindings = [
        _suite_projection_binding(row) for row in ordered_projections
    ]

    cell_raw = _canon(
        cell_catalog, label="independent cell catalog", maximum=MAX_CELL_CATALOG_BYTES
    )
    direct_parameter_names = (
        "persona-v2-aggregate-byte-distribution-catalog",
        "persona-v2-overlay-compatible-byte-distribution",
        "persona-v2-formal-source-recipe-profile-catalog",
    )
    direct_parameter_bytes = sum(
        EXPECTED_DEPENDENCY_PINS[name][0] for name in direct_parameter_names
    )
    concrete_ledgers = {
        row["persona_id"]: row
        for row in inputs["concrete_suite"]["persona_current_component_byte_ledgers"]
    }
    if set(concrete_ledgers) != set(envelope.PERSONA_IDS):
        _fail("concrete suite persona ledger coverage drifted")
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        projection_bytes = len(
            _canon(
                projections[persona_id],
                label="independent cell projection",
                maximum=MAX_CELL_PROJECTION_BYTES,
            )
        )
        origin_bytes = sum(
            len(
                _canon(
                    origins[(persona_id, origin)],
                    label="independent origin",
                    maximum=MAX_ORIGIN_BYTES,
                )
            )
            for origin in ORIGINS
        )
        profile_bytes = sum(
            len(
                _canon(
                    profiles[(persona_id, profile)],
                    label="independent profile",
                    maximum=MAX_PROFILE_BYTES,
                )
            )
            for profile in PROFILES
        )
        local_parameter_bytes = (
            len(cell_raw) + projection_bytes + origin_bytes + profile_bytes
        )
        extension_bytes = direct_parameter_bytes + local_parameter_bytes
        known = concrete_ledgers[persona_id]["current_component_bytes"] + extension_bytes
        if known > source_package.MAX_PERSONA_PACKAGE_BYTES:
            _fail("known pre-solve components exceed nominal persona cap")
        ledgers.append(
            {
                "expanded_view_body_bytes_excluded_nonpersisted": sum(
                    origins[(persona_id, origin)]["summary"][
                        "expanded_body_bytes_nonpersisted"
                    ]
                    for origin in ORIGINS
                ),
                "formal_complete_persona_package_cap_proved": False,
                "frame_and_header_bytes_included": False,
                "known_pre_solve_component_bytes": known,
                "max_pre_solve_persona_package_bytes": source_package.MAX_PERSONA_PACKAGE_BYTES,
                "origin_manifest_bytes_including_compact_owner_rows": origin_bytes,
                "parameter_cell_projection_bytes": projection_bytes,
                "parameter_extension_bytes": extension_bytes,
                "persona_id": persona_id,
                "persona_recipe_projection_coalesced_no_separate_body": True,
                "profile_manifest_bytes": profile_bytes,
                "remaining_bytes_before_nominal_cap_not_a_completion_proof": (
                    source_package.MAX_PERSONA_PACKAGE_BYTES - known
                ),
                "shared_parameter_cell_catalog_bytes_charged_once": len(cell_raw),
                "shared_direct_parameter_input_body_bytes_charged_once": direct_parameter_bytes,
                "shared_direct_parameter_input_names": list(direct_parameter_names),
                "upstream_concrete_current_component_bytes": concrete_ledgers[
                    persona_id
                ]["current_component_bytes"],
                "compact_owner_rows_coalesced_in_origin_manifest": True,
                "separate_recipe_or_owner_body_bytes_charged": 0,
            }
        )

    source_count = sum(
        profiles[(persona_id, "full")]["summary"]["source_intent_count"]
        for persona_id in envelope.PERSONA_IDS
    )
    pilot_sources = sum(
        row["summary"]["source_intent_count"]
        for row in ordered_origins
        if row["origin"] == "pilot"
    )
    residual_sources = sum(
        row["summary"]["source_intent_count"]
        for row in ordered_origins
        if row["origin"] == "full-residual"
    )
    pilot_pairs = sum(
        row["summary"]["exact_pair_unit_count"]
        for row in ordered_origins
        if row["origin"] == "pilot"
    )
    residual_pairs = sum(
        row["summary"]["exact_pair_unit_count"]
        for row in ordered_origins
        if row["origin"] == "full-residual"
    )
    owner_count = sum(len(row["compact_assignment_rows"]) for row in ordered_origins)
    receipt_count = sum(len(row["expanded_view_receipts"]) for row in ordered_origins)
    expanded_bytes = sum(
        row["summary"]["expanded_body_bytes_nonpersisted"]
        for row in ordered_origins
    )
    max_body = max(
        receipt["expanded_body_bytes"]
        for row in ordered_origins
        for receipt in row["expanded_view_receipts"]
    )
    max_row = max(
        receipt["maximum_row_bytes_including_lf"]
        for row in ordered_origins
        for receipt in row["expanded_view_receipts"]
    )
    pair_coordinates = sum(
        row["summary"]["pair_bearing_persona_origin_variant_coordinate_count"]
        for row in ordered_origins
    )
    eml_sources = sum(
        compact["source_count"]
        for row in ordered_origins
        for compact in row["compact_assignment_rows"]
        if compact["variant_id"] == "eml"
    )
    hosts = sum(
        row["summary"]["eml_fixed_host_intent_count"] for row in ordered_origins
    )
    nonhosts = sum(
        row["summary"]["eml_fixed_nonhost_intent_count"] for row in ordered_origins
    )
    memberships = sum(
        row["summary"]["eml_attachment_membership_count"] for row in ordered_origins
    )
    singletons = sum(
        compact["singleton_intent_count"]
        for row in ordered_origins
        for compact in row["compact_assignment_rows"]
        if compact["variant_id"] != "eml"
    )
    active_counts = [
        row["summary"]["active_parameter_cell_count"] for row in ordered_projections
    ]
    exact = {
        "source_count": source_count,
        "pilot_sources": pilot_sources,
        "residual_sources": residual_sources,
        "pilot_pairs": pilot_pairs,
        "residual_pairs": residual_pairs,
        "owner_count": owner_count,
        "receipt_count": receipt_count,
        "expanded_bytes": expanded_bytes,
        "max_body": max_body,
        "max_row": max_row,
        "pair_coordinates": pair_coordinates,
        "eml_sources": eml_sources,
        "hosts": hosts,
        "nonhosts": nonhosts,
        "memberships": memberships,
        "singletons": singletons,
    }
    expected_exact = {
        "source_count": 203_000,
        "pilot_sources": 20_300,
        "residual_sources": 182_700,
        "pilot_pairs": 508,
        "residual_pairs": 4_572,
        "owner_count": 4_759,
        "receipt_count": 73,
        "expanded_bytes": 17_527_680,
        "max_body": 367_471,
        "max_row": 110,
        "pair_coordinates": 485,
        "eml_sources": 9_153,
        "hosts": 2_800,
        "nonhosts": 6_353,
        "memberships": 5_690,
        "singletons": 183_687,
    }
    if (
        exact != expected_exact
        or source_count != pilot_sources + residual_sources
        or 2 * (pilot_pairs + residual_pairs) + singletons + eml_sources
        != source_count
        or sum(active_counts) != 2_643
        or min(active_counts) != 107
        or max(active_counts) != 146
    ):
        _fail("independent suite exact closure drifted")

    direct_names = [
        "persona-v2-source-inventory-layout",
        "persona-v2-source-inventory-suite",
        "persona-v2-concrete-overlay-membership-suite",
    ]
    suite_inputs = [_cell_catalog_binding(cell_catalog), *_binding_subset(inputs, direct_names)]
    value = {
        **_common(
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
            "compact_origin_assignment_row_count": owner_count,
            "concrete_exact_duplicate_pair_count": pilot_pairs + residual_pairs,
            "eml_attachment_membership_count": memberships,
            "eml_fixed_host_source_count": hosts,
            "eml_fixed_nonhost_source_count": nonhosts,
            "eml_source_count": eml_sources,
            "expanded_body_bytes_nonpersisted": expanded_bytes,
            "expanded_receipt_count": receipt_count,
            "global_parameter_cell_count": len(cell_catalog["parameter_cells"]),
            "maximum_expanded_body_bytes": max_body,
            "maximum_expanded_row_bytes_including_lf": max_row,
            "origin_manifest_count": len(ordered_origins),
            "non_eml_singleton_source_count": singletons,
            "pair_bearing_persona_origin_variant_coordinate_count": pair_coordinates,
            "persona_count": len(envelope.PERSONA_IDS),
            "pilot_exact_duplicate_pair_count": pilot_pairs,
            "pilot_source_intent_count": pilot_sources,
            "profile_manifest_count": len(ordered_profiles),
            "residual_exact_duplicate_pair_count": residual_pairs,
            "residual_source_intent_count": residual_sources,
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
            "render-write-observation-history-kio-root-capacity-and-g0-absent",
        ],
    }
    _all_false_authority(value, label="independent suite")
    _reject_forbidden_keys(value, path="$expected_suite")
    _suite_bytes(value)
    return value


def validate_source_parameter_assignment_suite_descriptor(
    value,
    *,
    source_layout_value=None,
    source_suite_value=None,
    formal_catalog_value=None,
    aggregate_catalog_value=None,
    effective_distribution_value=None,
    concrete_suite_value=None,
    source_origin_provider=None,
    source_body_provider=None,
    concrete_origin_provider=None,
    concrete_body_provider=None,
):
    """Independently validate the exact assignment suite and all detached views."""

    if type(value) is not dict:
        _fail("source parameter assignment suite must be an object")
    actual = _suite_bytes(value)
    target_opening = bytes(actual)
    if (
        len(actual) != EXPECTED_SUITE_CANONICAL_BYTES
        or hashlib.sha256(actual).hexdigest() != EXPECTED_SUITE_SHA256
    ):
        _fail("source parameter assignment suite differs from canonical pin")
    if (
        value.get("artifact_kind") != SUITE_KIND
        or value.get("artifact_schema") != SUITE_SCHEMA
        or value.get("artifact_schema_version") != SCHEMA_VERSION
    ):
        _fail("source parameter assignment suite envelope drifted")
    _all_false_authority(value, label="target suite")
    _reject_forbidden_keys(value, path="$target_suite")

    providers = {
        "source_origin_provider": (
            source_package.build_source_intent_origin_manifest
            if source_origin_provider is None
            else source_origin_provider
        ),
        "source_body_provider": (
            source_package.source_intent_shard_body_bytes
            if source_body_provider is None
            else source_body_provider
        ),
        "concrete_origin_provider": (
            concrete.build_concrete_overlay_membership_origin_manifest
            if concrete_origin_provider is None
            else concrete_origin_provider
        ),
        "concrete_body_provider": (
            concrete.concrete_overlay_membership_shard_body_bytes
            if concrete_body_provider is None
            else concrete_body_provider
        ),
    }
    if any(not callable(provider) for provider in providers.values()):
        _fail("all detached origin and body providers must be callable")
    overrides = {
        "source_layout": source_layout_value,
        "source_suite": source_suite_value,
        "formal": formal_catalog_value,
        "aggregate": aggregate_catalog_value,
        "effective": effective_distribution_value,
        "concrete_suite": concrete_suite_value,
    }
    originals = canonicalizers = opening = None
    try:
        originals, canonicalizers, opening, inputs = _resolve_inputs(overrides)
        expected = _expected_suite(inputs, **providers)
        expected_raw = _suite_bytes(expected)
        if not hmac.compare_digest(actual, expected_raw):
            _fail("suite differs from independent upstream reconstruction")
    finally:
        postflight_error = None
        if originals is not None:
            try:
                _reauth_originals(originals, canonicalizers, opening)
            except Exception as error:
                postflight_error = error
        try:
            target_current = _suite_bytes(value)
            if not hmac.compare_digest(target_opening, target_current):
                _fail("target suite mutated during provider callbacks")
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


__all__ = [
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "PersonaV2SourceParameterAssignmentValidationError",
    "validate_source_parameter_assignment_suite_descriptor",
]
