"""Exact, non-authorizing shard layout for the persona-PC v2 source inventory.

This artifact closes only the cardinality and key-range partition that must
exist before the 203,000 source-intent rows can be materialized.  It does not
invent source profiles for unfinished variants, does not contain shard body
hashes, and does not authorize a source inventory, solver, renderer, writer,
or G0 freeze.

The layout reserves one immutable pilot shard per persona and partitions only
the ``full-residual`` origin into additional shards.  A future full manifest
must reference the exact pilot shard bytes rather than regenerate or copy a
logically equivalent pilot body.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kcs.persona.pc-source-inventory-layout/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-source-inventory-layout"

MAX_LAYOUT_BYTES = 512 * 1024
MAX_INTENTS_PER_SHARD = 4_096
MAX_INTENT_JSONL_RECORD_BYTES = 768
MAX_SHARD_BODY_BYTES = 4 * 2**20
MAX_PERSONA_PACKAGE_BYTES = 16 * 2**20

ORIGIN_ORDER = ("pilot", "full-residual")
GATE_ROLE_ORDER = (
    "contract_contributor",
    "incidental_searchable",
    "raw_only",
)
EXPECTED_PERSONA_COUNT = 20
EXPECTED_PILOT_SOURCE_COUNT = 20_300
EXPECTED_FULL_RESIDUAL_SOURCE_COUNT = 182_700
EXPECTED_FULL_SOURCE_COUNT = 203_000
EXPECTED_PILOT_SHARD_COUNT = 20
EXPECTED_FULL_RESIDUAL_SHARD_COUNT = 53
EXPECTED_TOTAL_SHARD_COUNT = 73

AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_g0_freeze",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_intents",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "formal_capacity_gate_satisfied",
        "source_inventory_materialized",
    }
)


class PersonaV2SourceInventoryLayoutError(ValueError):
    """Raised when the exact source-inventory layout contract is violated."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2SourceInventoryLayoutError(
            f"unknown persona ID: {persona_id!r}"
        )


def _origin_source_count(persona_id, origin):
    _require_persona_id(persona_id)
    if origin == "pilot":
        return envelope.profile_file_count(persona_id, "pilot")
    if origin == "full-residual":
        return envelope.profile_file_count(
            persona_id, "full"
        ) - envelope.profile_file_count(persona_id, "pilot")
    raise PersonaV2SourceInventoryLayoutError(
        f"unknown source-intent origin: {origin!r}"
    )


def intent_key(persona_id, origin, origin_ordinal):
    """Return the canonical pre-solve key for one reserved source intent."""

    count = _origin_source_count(persona_id, origin)
    if (
        type(origin_ordinal) is not int
        or not 1 <= origin_ordinal <= count
    ):
        raise PersonaV2SourceInventoryLayoutError(
            f"origin ordinal is outside {persona_id}/{origin}: {origin_ordinal!r}"
        )
    width = 4 if origin == "pilot" else 5
    return (
        f"{persona_id}-intent-{origin}-syn-"
        f"{origin_ordinal:0{width}d}"
    )


def _shard_id(persona_id, origin, shard_ordinal):
    if type(shard_ordinal) is not int or shard_ordinal < 1:
        raise PersonaV2SourceInventoryLayoutError(
            "shard ordinal must be a positive integer"
        )
    return f"{persona_id}-source-intent-{origin}-shard-{shard_ordinal:04d}"


def _origin_shards(persona_id, origin):
    count = _origin_source_count(persona_id, origin)
    rows = []
    start = 1
    shard_ordinal = 1
    while start <= count:
        end = min(start + MAX_INTENTS_PER_SHARD - 1, count)
        rows.append(
            {
                "first_intent_key": intent_key(persona_id, origin, start),
                "first_origin_ordinal": start,
                "last_intent_key": intent_key(persona_id, origin, end),
                "last_origin_ordinal": end,
                "origin": origin,
                "persona_id": persona_id,
                "row_count": end - start + 1,
                "shard_id": _shard_id(persona_id, origin, shard_ordinal),
                "shard_ordinal": shard_ordinal,
            }
        )
        start = end + 1
        shard_ordinal += 1
    return rows


def _artifact_binding(
    name,
    dependency_role,
    value,
    *,
    validate,
    canonical,
    digest,
):
    validate(value)
    raw = canonical(value)
    actual_digest = digest(value)
    if actual_digest != hashlib.sha256(raw).hexdigest():
        raise PersonaV2SourceInventoryLayoutError(
            f"{name} returned a non-canonical digest"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "name": name,
        "sha256": actual_digest,
    }


def _input_bindings(envelope_value, variant_value):
    return [
        _artifact_binding(
            "persona-v2-envelope",
            "persona-physical-source-denominators",
            envelope_value,
            validate=envelope.validate_envelope_contract,
            canonical=envelope.canonical_json_bytes,
            digest=envelope.envelope_contract_sha256,
        ),
        _artifact_binding(
            "persona-v2-variant-catalog",
            "persona-variant-source-count-reservations",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
            digest=variant_catalog.variant_catalog_sha256,
        ),
    ]


def _variant_reservations(persona_id, variant_value, origin):
    count_field = "pilot_count" if origin == "pilot" else "full_minus_pilot_count"
    marginals = [
        row
        for row in variant_value["persona_variant_marginals"]
        if row["persona_id"] == persona_id
    ]
    rows = []
    start = 1
    for marginal in marginals:
        count = marginal[count_field]
        if count == 0:
            continue
        end = start + count - 1
        rows.append(
            {
                "first_intent_key": intent_key(persona_id, origin, start),
                "first_origin_ordinal": start,
                "last_intent_key": intent_key(persona_id, origin, end),
                "last_origin_ordinal": end,
                "origin": origin,
                "row_count": count,
                "variant_id": marginal["variant_id"],
            }
        )
        start = end + 1
    if start - 1 != _origin_source_count(persona_id, origin):
        raise PersonaV2SourceInventoryLayoutError(
            f"variant reservations do not cover {persona_id}/{origin}"
        )
    return rows


def _gate_role_counts(persona_id, variant_value, count_field):
    variant_roles = {
        row["variant_id"]: row["gate_role"]
        for row in variant_value["variant_rows"]
    }
    result = {role: 0 for role in GATE_ROLE_ORDER}
    for row in variant_value["persona_variant_marginals"]:
        if row["persona_id"] == persona_id:
            role = variant_roles[row["variant_id"]]
            if role not in result:
                raise PersonaV2SourceInventoryLayoutError(
                    f"unknown gate role for {persona_id}/{row['variant_id']}"
                )
            result[role] += row[count_field]
    return result


def _hard_zero_variant_ids(persona_id, variant_value):
    return [
        row["variant_id"]
        for row in variant_value["persona_variant_marginals"]
        if row["persona_id"] == persona_id and row["full_count"] == 0
    ]


def _declared_variant_count(persona_id, variant_value):
    return sum(
        row["persona_id"] == persona_id
        for row in variant_value["persona_variant_marginals"]
    )


def _suite_gate_role_counts(variant_value, count_field):
    result = {role: 0 for role in GATE_ROLE_ORDER}
    for persona_id in envelope.PERSONA_IDS:
        persona_counts = _gate_role_counts(
            persona_id, variant_value, count_field
        )
        for role in GATE_ROLE_ORDER:
            result[role] += persona_counts[role]
    return result


def _coverage(variant_value):
    marginals = variant_value["persona_variant_marginals"]
    return {
        "declared_hard_zero_persona_variant_row_count": sum(
            row["full_count"] == 0 for row in marginals
        ),
        "declared_persona_variant_row_count": len(marginals),
        "full_residual_shard_count": EXPECTED_FULL_RESIDUAL_SHARD_COUNT,
        "full_residual_source_count": EXPECTED_FULL_RESIDUAL_SOURCE_COUNT,
        "full_residual_variant_reservation_count": sum(
            row["full_minus_pilot_count"] > 0 for row in marginals
        ),
        "full_source_count": EXPECTED_FULL_SOURCE_COUNT,
        "persona_count": EXPECTED_PERSONA_COUNT,
        "pilot_shard_count": EXPECTED_PILOT_SHARD_COUNT,
        "pilot_source_count": EXPECTED_PILOT_SOURCE_COUNT,
        "pilot_variant_reservation_count": sum(
            row["pilot_count"] > 0 for row in marginals
        ),
        "total_shard_count": EXPECTED_TOTAL_SHARD_COUNT,
        "variant_identity_count": len(variant_value["variant_rows"]),
    }


def _persona_layout(persona_id, variant_value):
    pilot_count = _origin_source_count(persona_id, "pilot")
    residual_count = _origin_source_count(persona_id, "full-residual")
    full_count = envelope.profile_file_count(persona_id, "full")
    pilot_shards = _origin_shards(persona_id, "pilot")
    residual_shards = _origin_shards(persona_id, "full-residual")
    all_shards = pilot_shards + residual_shards
    pilot_ids = [row["shard_id"] for row in pilot_shards]
    full_ids = pilot_ids + [row["shard_id"] for row in residual_shards]
    pilot_role_counts = _gate_role_counts(
        persona_id, variant_value, "pilot_count"
    )
    residual_role_counts = _gate_role_counts(
        persona_id, variant_value, "full_minus_pilot_count"
    )
    full_role_counts = _gate_role_counts(
        persona_id, variant_value, "full_count"
    )
    return {
        "declared_hard_zero_variant_ids": _hard_zero_variant_ids(
            persona_id, variant_value
        ),
        "declared_persona_variant_count": _declared_variant_count(
            persona_id, variant_value
        ),
        "expected_full_manifest_shard_ids": full_ids,
        "expected_pilot_manifest_shard_ids": pilot_ids,
        "full_residual_source_count": residual_count,
        "full_source_count": full_count,
        "gate_role_source_counts": {
            "full": full_role_counts,
            "full-residual": residual_role_counts,
            "pilot": pilot_role_counts,
        },
        "persona_id": persona_id,
        "pilot_source_count": pilot_count,
        "shard_counts": {
            "full-residual": len(residual_shards),
            "pilot": len(pilot_shards),
            "total": len(all_shards),
        },
        "shards": all_shards,
        "variant_reservations": {
            "full-residual": _variant_reservations(
                persona_id, variant_value, "full-residual"
            ),
            "pilot": _variant_reservations(
                persona_id, variant_value, "pilot"
            ),
        },
    }


def _require_layout_invariants(value):
    if type(value) is not dict:
        raise PersonaV2SourceInventoryLayoutError("layout must be an object")
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        raise PersonaV2SourceInventoryLayoutError(
            "source-inventory layout must remain exactly non-authorizing"
        )
    personas = value.get("personas")
    if (
        type(personas) is not list
        or tuple(row.get("persona_id") for row in personas)
        != envelope.PERSONA_IDS
    ):
        raise PersonaV2SourceInventoryLayoutError(
            "layout persona coverage or order drifted"
        )

    variant_value = variant_catalog.build_variant_catalog()
    variant_catalog.validate_variant_catalog(variant_value)

    observed_ids = set()
    total_pilot_sources = 0
    total_residual_sources = 0
    total_full_sources = 0
    total_pilot_shards = 0
    total_residual_shards = 0
    for row in personas:
        persona_id = row["persona_id"]
        expected_pilot = _origin_source_count(persona_id, "pilot")
        expected_residual = _origin_source_count(persona_id, "full-residual")
        expected_full = envelope.profile_file_count(persona_id, "full")
        if (
            row["pilot_source_count"] != expected_pilot
            or row["full_residual_source_count"] != expected_residual
            or row["full_source_count"] != expected_full
            or expected_pilot + expected_residual != expected_full
        ):
            raise PersonaV2SourceInventoryLayoutError(
                f"source counts drifted for {persona_id}"
            )
        shards = row["shards"]
        if type(shards) is not list or not shards:
            raise PersonaV2SourceInventoryLayoutError(
                f"shards are absent for {persona_id}"
            )
        expected_shards = _origin_shards(persona_id, "pilot") + _origin_shards(
            persona_id, "full-residual"
        )
        if shards != expected_shards:
            raise PersonaV2SourceInventoryLayoutError(
                f"shard partition has a gap, overlap, reorder, or key drift: {persona_id}"
            )
        shard_ids = [candidate["shard_id"] for candidate in shards]
        if observed_ids.intersection(shard_ids):
            raise PersonaV2SourceInventoryLayoutError(
                "shard IDs must be globally unique"
            )
        observed_ids.update(shard_ids)
        pilot_ids = [
            candidate["shard_id"]
            for candidate in shards
            if candidate["origin"] == "pilot"
        ]
        residual_ids = [
            candidate["shard_id"]
            for candidate in shards
            if candidate["origin"] == "full-residual"
        ]
        if row["expected_pilot_manifest_shard_ids"] != pilot_ids:
            raise PersonaV2SourceInventoryLayoutError(
                f"pilot manifest references drifted for {persona_id}"
            )
        if row["expected_full_manifest_shard_ids"] != pilot_ids + residual_ids:
            raise PersonaV2SourceInventoryLayoutError(
                f"full manifest must reuse exact pilot shard references: {persona_id}"
            )
        expected_counts = {
            "full-residual": len(residual_ids),
            "pilot": len(pilot_ids),
            "total": len(shards),
        }
        if row["shard_counts"] != expected_counts:
            raise PersonaV2SourceInventoryLayoutError(
                f"shard counts drifted for {persona_id}"
            )
        if any(
            candidate["row_count"] < 1
            or candidate["row_count"] > MAX_INTENTS_PER_SHARD
            for candidate in shards
        ):
            raise PersonaV2SourceInventoryLayoutError(
                f"shard row cap drifted for {persona_id}"
            )
        expected_reservations = {
            "full-residual": _variant_reservations(
                persona_id, variant_value, "full-residual"
            ),
            "pilot": _variant_reservations(
                persona_id, variant_value, "pilot"
            ),
        }
        if row.get("variant_reservations") != expected_reservations:
            raise PersonaV2SourceInventoryLayoutError(
                f"variant reservation ranges drifted for {persona_id}"
            )
        if row.get("declared_hard_zero_variant_ids") != _hard_zero_variant_ids(
            persona_id, variant_value
        ):
            raise PersonaV2SourceInventoryLayoutError(
                f"hard-zero variant declarations drifted for {persona_id}"
            )
        if row.get("declared_persona_variant_count") != _declared_variant_count(
            persona_id, variant_value
        ):
            raise PersonaV2SourceInventoryLayoutError(
                f"declared variant count drifted for {persona_id}"
            )
        expected_role_counts = {
            "full": _gate_role_counts(persona_id, variant_value, "full_count"),
            "full-residual": _gate_role_counts(
                persona_id, variant_value, "full_minus_pilot_count"
            ),
            "pilot": _gate_role_counts(persona_id, variant_value, "pilot_count"),
        }
        if row.get("gate_role_source_counts") != expected_role_counts:
            raise PersonaV2SourceInventoryLayoutError(
                f"gate-role source counts drifted for {persona_id}"
            )
        for role in GATE_ROLE_ORDER:
            if (
                expected_role_counts["pilot"][role]
                + expected_role_counts["full-residual"][role]
                != expected_role_counts["full"][role]
            ):
                raise PersonaV2SourceInventoryLayoutError(
                    f"pilot plus residual gate-role count drifted: {persona_id}/{role}"
                )
        total_pilot_sources += expected_pilot
        total_residual_sources += expected_residual
        total_full_sources += expected_full
        total_pilot_shards += len(pilot_ids)
        total_residual_shards += len(residual_ids)

    expected_coverage = _coverage(variant_value)
    exact_cardinality = {
        "full_residual_shard_count": total_residual_shards,
        "full_residual_source_count": total_residual_sources,
        "full_source_count": total_full_sources,
        "persona_count": len(personas),
        "pilot_shard_count": total_pilot_shards,
        "pilot_source_count": total_pilot_sources,
        "total_shard_count": total_pilot_shards + total_residual_shards,
    }
    if any(
        exact_cardinality[key] != expected_coverage[key]
        for key in exact_cardinality
    ) or value.get("coverage") != expected_coverage:
        raise PersonaV2SourceInventoryLayoutError(
            "suite source or shard coverage drifted"
        )
    expected_suite_roles = {
        "full": _suite_gate_role_counts(variant_value, "full_count"),
        "full-residual": _suite_gate_role_counts(
            variant_value, "full_minus_pilot_count"
        ),
        "pilot": _suite_gate_role_counts(variant_value, "pilot_count"),
    }
    if value.get("suite_gate_role_source_counts") != expected_suite_roles:
        raise PersonaV2SourceInventoryLayoutError(
            "suite gate-role source counts drifted"
        )


@functools.lru_cache(maxsize=1)
def _canonical_layout():
    envelope_value = envelope.build_envelope_contract()
    variant_value = variant_catalog.build_variant_catalog()
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "framed_byte_cap_required_by_contract": True,
            "max_intent_jsonl_record_bytes_including_lf": (
                MAX_INTENT_JSONL_RECORD_BYTES
            ),
            "max_intents_per_shard": MAX_INTENTS_PER_SHARD,
            "max_layout_bytes": MAX_LAYOUT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_package_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_shard_body_bytes": MAX_SHARD_BODY_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_shard_bodies_materialized": False,
            "all_source_intent_rows_materialized": False,
            "body_bytes_and_sha_bound": False,
            "exact_key_range_partition_complete": True,
            "exact_persona_and_origin_counts_complete": True,
            "full_manifest_pilot_shard_byte_reuse_proved": False,
            "full_manifest_pilot_shard_reference_layout_complete": True,
            "source_intent_inventory_complete": False,
            "source_inventory_layout_complete": True,
            "variant_profile_assignments_complete": False,
        },
        "completion_scope": (
            "exact-203000-source-key-and-73-shard-layout-only-no-row-bodies-"
            "no-source-profile-assignment-no-inventory-authority"
        ),
        "coverage": _coverage(variant_value),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [
            "persona-v2-envelope",
            "persona-v2-variant-catalog",
        ],
        "input_bindings": _input_bindings(envelope_value, variant_value),
        "intent_key_contract": {
            "full_residual_format": (
                "{persona_id}-intent-full-residual-syn-{origin_ordinal:05d}"
            ),
            "origin_ordinal_is_one_based": True,
            "origin_ordinal_is_local_to_origin": True,
            "pilot_format": "{persona_id}-intent-pilot-syn-{origin_ordinal:04d}",
            "runtime_path_clock_host_or_replay_inputs_allowed": False,
        },
        "ordering_contract": {
            "intent_rows_within_shard": "intent-key-utf8-byte-order",
            "origins": list(ORIGIN_ORDER),
            "personas": list(envelope.PERSONA_IDS),
            "shards_within_origin": "positive-shard-ordinal",
        },
        "personas": [
            _persona_layout(persona_id, variant_value)
            for persona_id in envelope.PERSONA_IDS
        ],
        "remaining_blockers": [
            "203000-source-intent-row-bodies-not-materialized",
            "73-shard-body-bytes-and-sha-not-bound",
            "unready-variant-renderer-validator-profiles-remain",
            "overlay-membership-and-placement-not-bound",
            "fact-membership-full-inventory-not-materialized",
            "schema-specific-semantic-payload-projection-not-implemented",
            "source-level-allocation-solution-and-proof-not-present",
            "persona-package-16mib-cap-not-proved",
            "external-frame-header-schema-dispatcher-not-implemented",
        ],
        "suite_gate_role_source_counts": {
            "full": _suite_gate_role_counts(variant_value, "full_count"),
            "full-residual": _suite_gate_role_counts(
                variant_value, "full_minus_pilot_count"
            ),
            "pilot": _suite_gate_role_counts(variant_value, "pilot_count"),
        },
    }
    _require_layout_invariants(value)
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source-inventory layout",
            max_bytes=MAX_LAYOUT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryLayoutError(str(error)) from None
    return value


def build_source_inventory_layout():
    """Return a detached exact layout for all twenty persona inventories."""

    return copy.deepcopy(_canonical_layout())


def expected_persona_shards(persona_id):
    """Return detached expected shard descriptors for one persona."""

    _require_persona_id(persona_id)
    layout = _canonical_layout()
    row = next(
        candidate
        for candidate in layout["personas"]
        if candidate["persona_id"] == persona_id
    )
    return copy.deepcopy(row["shards"])


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source-inventory layout",
            max_bytes=MAX_LAYOUT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryLayoutError(str(error)) from None


def validate_source_inventory_layout(value):
    try:
        artifact_common.validate_exact_regeneration(
            value,
            builder=build_source_inventory_layout,
            label="persona v2 source-inventory layout",
            max_bytes=MAX_LAYOUT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryLayoutError(str(error)) from None
    _require_layout_invariants(value)
    return True


def source_inventory_layout_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_source_inventory_layout,
            label="persona v2 source-inventory layout",
            max_bytes=MAX_LAYOUT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryLayoutError(str(error)) from None


def require_materialized_source_inventory():
    raise PersonaV2SourceInventoryLayoutError(
        "the exact 203,000-key/73-shard layout is complete, but source-intent "
        "row bodies, shard bytes/SHA, remaining variant profiles, overlay/fact membership, "
        "package-cap proof, solver allocation, and execution authority remain absent"
    )
