"""Complete structural source-slot package for persona-PC v2.

This module deterministically materializes the 203,000 reference-only source
intent rows reserved by :mod:`persona_v2_source_inventory_layout` and binds
their 73 canonical JSONL shard bodies into detached origin, profile, and suite
manifests.  It deliberately does not invent semantic content, fact sets,
formal source recipes, rendered files, filesystem paths, solver output, or
execution authority.

The full profile is a composition, not a regeneration convention: its first
origin binding and first shard descriptors are the exact immutable pilot
manifest/body references, followed by the ``full-residual`` origin.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_source_inventory_layout as source_layout
    from . import persona_v2_source_inventory_profile as inventory_profile
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_source_inventory_layout as source_layout
    import persona_v2_source_inventory_profile as inventory_profile


ORIGIN_ARTIFACT_SCHEMA = "kcs.persona.pc-source-inventory-origin-manifest/v2"
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-source-inventory-origin-manifest"
PROFILE_ARTIFACT_SCHEMA = "kcs.persona.pc-source-inventory-profile-manifest/v2"
PROFILE_ARTIFACT_KIND = "persona-pc-v2-source-inventory-profile-manifest"
SUITE_ARTIFACT_SCHEMA = "kcs.persona.pc-source-inventory-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-source-inventory-suite"
ARTIFACT_SCHEMA_VERSION = 2

ORIGIN_ORDER = source_layout.ORIGIN_ORDER
PROFILE_ORDER = ("pilot", "full")
GATE_ROLE_ORDER = source_layout.GATE_ROLE_ORDER

MAX_INTENT_ROW_BYTES_INCLUDING_LF = source_layout.MAX_INTENT_JSONL_RECORD_BYTES
MAX_INTENTS_PER_SHARD = source_layout.MAX_INTENTS_PER_SHARD
MAX_SHARD_BODY_BYTES = source_layout.MAX_SHARD_BODY_BYTES
MAX_PERSONA_PACKAGE_BYTES = source_layout.MAX_PERSONA_PACKAGE_BYTES
MAX_ORIGIN_MANIFEST_BYTES = 128 * 1024
MAX_PROFILE_MANIFEST_BYTES = 128 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 256 * 1024

EXPECTED_SOURCE_INTENT_COUNT = source_layout.EXPECTED_FULL_SOURCE_COUNT
EXPECTED_SHARD_COUNT = source_layout.EXPECTED_TOTAL_SHARD_COUNT
EXPECTED_ORIGIN_MANIFEST_COUNT = 40
EXPECTED_PROFILE_MANIFEST_COUNT = 40

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_inventory",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "joint_allocation_proved",
        "kcs_execution_available",
        "source_intent_refinement_policy_bound",
    }
)

INTENT_ROW_FIELDS = frozenset(
    {
        "content_context_id",
        "deterministic_payload_seed",
        "eligible_scope_set_id",
        "intent_key",
        "origin",
        "persona_id",
        "placement_context_id",
        "present_fact_set_key",
        "quota_context_id",
        "source_profile_id",
    }
)

SHARD_DESCRIPTOR_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "file_name",
        "first_intent_key",
        "first_origin_ordinal",
        "last_intent_key",
        "last_origin_ordinal",
        "max_row_bytes_including_lf",
        "origin",
        "persona_id",
        "row_count",
        "shard_id",
        "shard_ordinal",
    }
)


class PersonaV2SourceInventoryPackageError(ValueError):
    """Raised when a structural source-inventory package contract is broken."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2SourceInventoryPackageError(
            f"unknown persona ID: {persona_id!r}"
        )


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        raise PersonaV2SourceInventoryPackageError(
            f"unknown source origin: {origin!r}"
        )


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        raise PersonaV2SourceInventoryPackageError(
            f"unknown source profile: {profile!r}"
        )


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        raise PersonaV2SourceInventoryPackageError(f"{label} must remain non-G0")
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        raise PersonaV2SourceInventoryPackageError(
            f"{label} authority must be the exact all-false schema"
        )


def _public_binding(name, role, value, *, validate, canonical, digest):
    validate(value)
    raw = canonical(value)
    actual = hashlib.sha256(raw).hexdigest()
    if digest(value) != actual:
        raise PersonaV2SourceInventoryPackageError(
            f"{name} returned a non-canonical digest"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": actual,
    }


def _release_overlay_projection_caches():
    """Release verbose upstream generation values after compact projection.

    The overlay module intentionally caches all forty immutable origins for its
    own suite regeneration.  Once this package has cached every origin
    manifest, only the compact reservation suite/bindings are still needed.
    Clearing these internal generation caches keeps later validators from
    inheriting the verbose source-key pools; it does not alter artifact bytes.
    """

    for name in ("_canonical_origin", "_intent_slot_tuples_by_variant"):
        candidate = getattr(reservation_layout, name, None)
        clear = getattr(candidate, "cache_clear", None)
        if callable(clear):
            clear()


@functools.lru_cache(maxsize=1)
def _shared_inputs():
    layout = source_layout.build_source_inventory_layout()
    profiles = inventory_profile.build_source_inventory_profile_catalog()
    reservation_suite = reservation_layout.build_overlay_reservation_suite()
    source_layout.validate_source_inventory_layout(layout)
    inventory_profile.validate_source_inventory_profile_catalog(profiles)
    reservation_layout.validate_overlay_reservation_suite(reservation_suite)

    layout_by_persona = {row["persona_id"]: row for row in layout["personas"]}
    profile_by_variant = {
        row["variant_id"]: row for row in profiles["source_profile_rows"]
    }
    reservation_by_origin = {
        (row["persona_id"], row["origin"]): row
        for row in reservation_suite["origin_bindings"]
    }
    if (
        tuple(layout_by_persona) != envelope.PERSONA_IDS
        or len(profile_by_variant) != inventory_profile.EXPECTED_PROFILE_COUNT
        or len(reservation_by_origin) != EXPECTED_ORIGIN_MANIFEST_COUNT
    ):
        raise PersonaV2SourceInventoryPackageError(
            "source package upstream coverage drifted"
        )

    reservation_suite_raw = reservation_layout.overlay_reservation_suite_bytes(
        reservation_suite
    )
    shared_bindings = [
        _public_binding(
            "persona-v2-source-inventory-layout",
            "exact-source-key-ranges-and-shard-partition",
            layout,
            validate=source_layout.validate_source_inventory_layout,
            canonical=source_layout.canonical_json_bytes,
            digest=source_layout.source_inventory_layout_sha256,
        ),
        _public_binding(
            "persona-v2-source-inventory-profile-catalog",
            "all-variant-source-profile-foreign-keys",
            profiles,
            validate=inventory_profile.validate_source_inventory_profile_catalog,
            canonical=inventory_profile.canonical_json_bytes,
            digest=inventory_profile.source_inventory_profile_catalog_sha256,
        ),
        {
            "artifact_kind": reservation_suite["artifact_kind"],
            "artifact_schema": reservation_suite["artifact_schema"],
            "artifact_schema_version": reservation_suite["artifact_schema_version"],
            "canonical_bytes": len(reservation_suite_raw),
            "dependency_role": "overlay-source-reference-reservations",
            "name": "persona-v2-overlay-reservation-suite",
            "sha256": hashlib.sha256(reservation_suite_raw).hexdigest(),
        },
    ]
    if shared_bindings[-1]["sha256"] != reservation_layout.overlay_reservation_suite_sha256(
        reservation_suite
    ):
        raise PersonaV2SourceInventoryPackageError(
            "overlay reservation suite digest drifted"
        )
    return {
        "layout": layout,
        "layout_by_persona": layout_by_persona,
        "profile_by_variant": profile_by_variant,
        "profiles": profiles,
        "reservation_by_origin": reservation_by_origin,
        "reservation_suite": reservation_suite,
        "shared_bindings": shared_bindings,
    }


def _persona_layout(persona_id):
    _require_persona_id(persona_id)
    return _shared_inputs()["layout_by_persona"][persona_id]


def _origin_layout_shards(persona_id, origin):
    _require_origin(origin)
    return [
        row
        for row in _persona_layout(persona_id)["shards"]
        if row["origin"] == origin
    ]


def _layout_shard(persona_id, origin, shard_ordinal):
    if type(shard_ordinal) is not int or shard_ordinal < 1:
        raise PersonaV2SourceInventoryPackageError(
            "shard ordinal must be a positive exact integer"
        )
    shards = _origin_layout_shards(persona_id, origin)
    if shard_ordinal > len(shards):
        raise PersonaV2SourceInventoryPackageError(
            f"unknown shard coordinate: {persona_id}/{origin}/{shard_ordinal}"
        )
    return shards[shard_ordinal - 1]


def _row_for_variant(persona_id, origin, ordinal, variant_id):
    width = 4 if origin == "pilot" else 5
    suffix = f"{ordinal:0{width}d}"
    profile = _shared_inputs()["profile_by_variant"].get(variant_id)
    if profile is None:
        raise PersonaV2SourceInventoryPackageError(
            f"variant has no exact inventory profile: {variant_id}"
        )
    row = {
        "content_context_id": f"{persona_id}-content-slot-{origin}-syn-{suffix}",
        "deterministic_payload_seed": (
            f"{persona_id}-payload-seed-{origin}-syn-{suffix}"
        ),
        "eligible_scope_set_id": f"{persona_id}-eligible-scope-set-v2",
        "intent_key": source_layout.intent_key(persona_id, origin, ordinal),
        "origin": origin,
        "persona_id": persona_id,
        "placement_context_id": (
            f"{persona_id}-placement-slot-{origin}-syn-{suffix}"
        ),
        "present_fact_set_key": (
            f"{persona_id}-present-fact-set-{origin}-syn-{suffix}"
        ),
        "quota_context_id": f"{persona_id}-quota-slot-{origin}-syn-{suffix}",
        "source_profile_id": profile["source_profile_id"],
    }
    if set(row) != INTENT_ROW_FIELDS:
        raise PersonaV2SourceInventoryPackageError(
            "source intent row schema drifted"
        )
    try:
        raw = artifact_common.canonical_json_bytes(
            row,
            label="persona v2 source inventory row",
            max_bytes=MAX_INTENT_ROW_BYTES_INCLUDING_LF - 1,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryPackageError(str(error)) from None
    if len(raw) + 1 > MAX_INTENT_ROW_BYTES_INCLUDING_LF:
        raise PersonaV2SourceInventoryPackageError(
            "source intent row exceeds its LF-inclusive cap"
        )
    return row


def iter_source_intent_rows(persona_id, origin, shard_ordinal):
    """Yield one shard's exact rows without retaining any other shard body."""

    shard = _layout_shard(persona_id, origin, shard_ordinal)
    reservations = _persona_layout(persona_id)["variant_reservations"][origin]
    first = shard["first_origin_ordinal"]
    last = shard["last_origin_ordinal"]
    emitted = 0
    for reservation in reservations:
        start = max(first, reservation["first_origin_ordinal"])
        end = min(last, reservation["last_origin_ordinal"])
        if start > end:
            continue
        for ordinal in range(start, end + 1):
            emitted += 1
            yield _row_for_variant(
                persona_id, origin, ordinal, reservation["variant_id"]
            )
    if emitted != shard["row_count"]:
        raise PersonaV2SourceInventoryPackageError(
            f"variant reservations did not cover shard: {shard['shard_id']}"
        )


def source_intent_shard_body_bytes(persona_id, origin, shard_ordinal):
    """Return exact canonical JSONL bytes for one bounded shard."""

    parts = []
    total = 0
    for row in iter_source_intent_rows(persona_id, origin, shard_ordinal):
        try:
            raw = artifact_common.canonical_json_bytes(
                row,
                label="persona v2 source inventory row",
                max_bytes=MAX_INTENT_ROW_BYTES_INCLUDING_LF - 1,
            ) + b"\n"
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2SourceInventoryPackageError(str(error)) from None
        if len(raw) > MAX_INTENT_ROW_BYTES_INCLUDING_LF:
            raise PersonaV2SourceInventoryPackageError(
                "source intent row exceeds its LF-inclusive cap"
            )
        total += len(raw)
        if total > MAX_SHARD_BODY_BYTES:
            raise PersonaV2SourceInventoryPackageError(
                "source intent shard exceeds the four-MiB body cap"
            )
        parts.append(raw)
    body = b"".join(parts)
    if not body or len(parts) > MAX_INTENTS_PER_SHARD:
        raise PersonaV2SourceInventoryPackageError(
            "source intent shard is empty or exceeds its row cap"
        )
    return body


@functools.lru_cache(maxsize=73)
def _canonical_shard_descriptor(persona_id, origin, shard_ordinal):
    shard = _layout_shard(persona_id, origin, shard_ordinal)
    body = source_intent_shard_body_bytes(persona_id, origin, shard_ordinal)
    lines = body.splitlines()
    value = {
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "file_name": f"{shard['shard_id']}.jsonl",
        "first_intent_key": shard["first_intent_key"],
        "first_origin_ordinal": shard["first_origin_ordinal"],
        "last_intent_key": shard["last_intent_key"],
        "last_origin_ordinal": shard["last_origin_ordinal"],
        "max_row_bytes_including_lf": max(len(line) + 1 for line in lines),
        "origin": origin,
        "persona_id": persona_id,
        "row_count": len(lines),
        "shard_id": shard["shard_id"],
        "shard_ordinal": shard_ordinal,
    }
    if (
        set(value) != SHARD_DESCRIPTOR_FIELDS
        or value["row_count"] != shard["row_count"]
        or value["body_bytes"] > MAX_SHARD_BODY_BYTES
        or value["max_row_bytes_including_lf"]
        > MAX_INTENT_ROW_BYTES_INCLUDING_LF
    ):
        raise PersonaV2SourceInventoryPackageError(
            f"source shard descriptor drifted: {shard['shard_id']}"
        )
    return value


def build_source_intent_shard_descriptor(persona_id, origin, shard_ordinal):
    return copy.deepcopy(
        _canonical_shard_descriptor(persona_id, origin, shard_ordinal)
    )


def _reservation_origin_binding(persona_id, origin):
    source = _shared_inputs()["reservation_by_origin"][(persona_id, origin)]
    return {
        "artifact_kind": source["artifact_kind"],
        "artifact_schema": source["artifact_schema"],
        "artifact_schema_version": source["artifact_schema_version"],
        "canonical_bytes": source["canonical_bytes"],
        "dependency_role": "matching-overlay-source-reference-reservation",
        "name": "persona-v2-overlay-reservation-origin",
        "origin": origin,
        "persona_id": persona_id,
        "sha256": source["sha256"],
    }


def _origin_variant_counts(persona_id, origin):
    profiles = _shared_inputs()["profile_by_variant"]
    return [
        {
            "first_intent_key": row["first_intent_key"],
            "first_origin_ordinal": row["first_origin_ordinal"],
            "gate_role": profiles[row["variant_id"]]["gate_role"],
            "last_intent_key": row["last_intent_key"],
            "last_origin_ordinal": row["last_origin_ordinal"],
            "row_count": row["row_count"],
            "source_profile_id": profiles[row["variant_id"]]["source_profile_id"],
            "variant_id": row["variant_id"],
        }
        for row in _persona_layout(persona_id)["variant_reservations"][origin]
    ]


def _origin_summary(persona_id, origin, descriptors, variant_counts):
    profiles = _shared_inputs()["profile_by_variant"]
    reservation_suite = _shared_inputs()["reservation_suite"]
    reservation_binding = next(
        row
        for row in reservation_suite["origin_bindings"]
        if row["persona_id"] == persona_id and row["origin"] == origin
    )
    # Compact summary values are read from the exact reservation origin.  The
    # reservation module may retain that immutable value in its own bounded
    # forty-origin LRU; this package retains only the projected counts.
    reservation = reservation_layout.build_overlay_reservation_origin(
        persona_id, origin
    )
    reservation_layout.validate_overlay_reservation_origin(
        persona_id, origin, reservation
    )
    if reservation_layout.overlay_reservation_origin_sha256(
        persona_id, origin, reservation
    ) != reservation_binding["sha256"]:
        raise PersonaV2SourceInventoryPackageError(
            "matching reservation origin digest drifted"
        )
    ready = sum(
        row["row_count"]
        for row in variant_counts
        if profiles[row["variant_id"]]["bounded_feasibility"][
            "local_vertical_slice_ready"
        ]
    )
    source_count = sum(row["row_count"] for row in variant_counts)
    return {
        "gate_role_source_counts": copy.deepcopy(
            _persona_layout(persona_id)["gate_role_source_counts"][origin]
        ),
        "implementation_missing_source_count": source_count - ready,
        "local_feasibility_ready_source_count": ready,
        "maximum_row_bytes_including_lf": max(
            row["max_row_bytes_including_lf"] for row in descriptors
        ),
        "overlay_referenced_unique_source_intent_count": reservation["summary"][
            "overlay_referenced_unique_source_intent_count"
        ],
        "semantic_anchor_slot_count": reservation["summary"][
            "semantic_anchor_slot_count"
        ],
        "shard_body_bytes": sum(row["body_bytes"] for row in descriptors),
        "shard_count": len(descriptors),
        "source_intent_count": source_count,
        "unreserved_source_intent_count": reservation["summary"][
            "unreserved_source_intent_count"
        ],
        "variant_with_sources_count": len(variant_counts),
    }


ORIGIN_COMPLETION_CLAIMS = {
    "all_shard_bodies_materialized": True,
    "all_source_slot_rows_materialized": True,
    "body_bytes_and_sha_bound": True,
    "bounded_jsonl_descriptor_contract_bound": True,
    "concrete_overlay_membership_bound": False,
    "exact_variant_inventory_profile_assignments_complete": True,
    "formal_source_recipe_profiles_bound": False,
    "full_persona_package_bound_proved": False,
    "present_fact_sets_bound": False,
    "renderer_validator_implementation_complete": False,
    "semantic_content_catalogs_bound": False,
    "source_intent_inventory_complete": False,
    "source_intent_origin_manifest_complete": True,
    "source_level_exact_allocation_complete": False,
}

ORIGIN_DEPENDENCY_CONTRACT = {
    "evaluation_query_or_oracle_identity_imported": False,
    "future_concrete_overlay_manifest_must_bind_reservation_source_and_fact_manifests": True,
    "future_source_owned_fact_manifest_must_bind_this_origin_manifest": True,
    "reservation_origin_is_strictly_upstream": True,
    "source_manifest_may_bind_future_fact_or_concrete_overlay_manifest": False,
}

ORIGIN_REMAINING_BLOCKERS = [
    "semantic-content-context-catalogs-not-bound",
    "source-owned-present-fact-set-manifests-not-bound",
    "all-formal-source-recipe-profiles-unbound",
    "sixty-one-renderer-validator-or-formula-implementations-missing",
    "concrete-overlay-membership-not-bound",
    "source-level-scope-placement-allocation-not-solved",
    "render-write-chunk-observation-and-history-not-present",
    "future-complete-persona-package-cap-not-proved",
]


@functools.lru_cache(maxsize=40)
def _canonical_origin_manifest(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    descriptors = [
        _canonical_shard_descriptor(persona_id, origin, row["shard_ordinal"])
        for row in _origin_layout_shards(persona_id, origin)
    ]
    variant_counts = _origin_variant_counts(persona_id, origin)
    value = {
        "artifact_kind": ORIGIN_ARTIFACT_KIND,
        "artifact_schema": ORIGIN_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "intent_jsonl_record_terminator": "LF",
            "max_body_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "max_intent_row_bytes_including_lf": MAX_INTENT_ROW_BYTES_INCLUDING_LF,
            "max_intents_per_shard": MAX_INTENTS_PER_SHARD,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_shard_body_bytes": MAX_SHARD_BODY_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": copy.deepcopy(ORIGIN_COMPLETION_CLAIMS),
        "completion_scope": (
            "one-persona-one-origin-all-structural-source-slot-rows-and-shard-"
            "digests-only-no-semantic-catalog-no-formal-recipe-no-execution-no-g0"
        ),
        "dependency_direction_contract": copy.deepcopy(
            ORIGIN_DEPENDENCY_CONTRACT
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [
            "persona-v2-source-inventory-layout",
            "persona-v2-source-inventory-profile-catalog",
            "persona-v2-overlay-reservation-suite",
            "persona-v2-overlay-reservation-origin",
        ],
        "input_bindings": copy.deepcopy(_shared_inputs()["shared_bindings"])
        + [_reservation_origin_binding(persona_id, origin)],
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": list(ORIGIN_REMAINING_BLOCKERS),
        "shard_descriptors": copy.deepcopy(descriptors),
        "summary": _origin_summary(
            persona_id, origin, descriptors, variant_counts
        ),
        "variant_source_counts": variant_counts,
    }
    _require_negative_authority(value, label="source inventory origin manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source inventory origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryPackageError(str(error)) from None
    return value


def build_source_intent_origin_manifest(persona_id, origin):
    return copy.deepcopy(_canonical_origin_manifest(persona_id, origin))


def _manifest_binding(value, *, name, role, coordinate_fields, max_bytes):
    raw = artifact_common.canonical_json_bytes(
        value, label=name, max_bytes=max_bytes
    )
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


def _profile_origins(profile):
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


def _aggregate_variant_counts(origin_manifests):
    totals = {}
    for manifest in origin_manifests:
        for row in manifest["variant_source_counts"]:
            target = totals.setdefault(
                row["variant_id"],
                {
                    "gate_role": row["gate_role"],
                    "row_count": 0,
                    "source_profile_id": row["source_profile_id"],
                    "variant_id": row["variant_id"],
                },
            )
            target["row_count"] += row["row_count"]
    order = {
        row["variant_id"]: index
        for index, row in enumerate(
            _shared_inputs()["profiles"]["source_profile_rows"]
        )
    }
    return [totals[key] for key in sorted(totals, key=order.__getitem__)]


PROFILE_DEPENDENCY_CONTRACT = {
    "full_profile_origin_order_is_pilot_then_full_residual": True,
    "full_profile_reuses_exact_pilot_origin_manifest_and_shard_descriptors": True,
    "profile_manifest_may_bind_future_fact_or_concrete_overlay_manifest": False,
    "source_origin_manifests_are_strictly_upstream": True,
}

PROFILE_REMAINING_BLOCKERS = list(ORIGIN_REMAINING_BLOCKERS)


@functools.lru_cache(maxsize=40)
def _canonical_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    _require_profile(profile)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for origin in _profile_origins(profile)
    ]
    bindings = [
        _manifest_binding(
            manifest,
            name="persona-v2-source-inventory-origin-manifest",
            role="immutable-source-origin-manifest",
            coordinate_fields=("persona_id", "origin"),
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        for manifest in origins
    ]
    descriptors = [
        copy.deepcopy(row)
        for manifest in origins
        for row in manifest["shard_descriptors"]
    ]
    variants = _aggregate_variant_counts(origins)
    gate_roles = {role: 0 for role in GATE_ROLE_ORDER}
    for row in variants:
        gate_roles[row["gate_role"]] += row["row_count"]
    pilot = origins[0]
    value = {
        "artifact_kind": PROFILE_ARTIFACT_KIND,
        "artifact_schema": PROFILE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_body_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_current_source_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_profile_origin_manifests_bound": True,
            "all_profile_shard_references_bound": True,
            "concrete_overlay_membership_bound": False,
            "formal_source_recipe_profiles_bound": False,
            "full_profile_composition_bound": profile == "full",
            "full_profile_exact_pilot_origin_reuse_proved": profile == "full",
            "pilot_profile_single_origin_bound": profile == "pilot",
            "present_fact_sets_bound": False,
            "semantic_content_catalogs_bound": False,
            "source_intent_inventory_complete": False,
            "source_intent_profile_manifest_complete": True,
        },
        "completion_scope": (
            "one-persona-structural-source-profile-manifest-with-exact-pilot-"
            "origin-reuse-no-semantic-catalog-no-formal-recipe-no-execution-no-g0"
        ),
        "dependency_direction_contract": copy.deepcopy(
            PROFILE_DEPENDENCY_CONTRACT
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": ["persona-v2-overlay-reservation-suite"],
        "input_bindings": [
            copy.deepcopy(_shared_inputs()["shared_bindings"][2])
        ],
        "origin_manifest_bindings": bindings,
        "persona_id": persona_id,
        "profile": profile,
        "remaining_blockers": list(PROFILE_REMAINING_BLOCKERS),
        "shard_descriptors": descriptors,
        "summary": {
            "full_residual_origin_manifest_count": int(profile == "full"),
            "gate_role_source_counts": gate_roles,
            "maximum_row_bytes_including_lf": max(
                row["max_row_bytes_including_lf"] for row in descriptors
            ),
            "origin_manifest_count": len(origins),
            "pilot_origin_manifest_count": 1,
            "reused_pilot_shard_body_bytes": (
                pilot["summary"]["shard_body_bytes"] if profile == "full" else 0
            ),
            "reused_pilot_shard_count": (
                pilot["summary"]["shard_count"] if profile == "full" else 0
            ),
            "reused_pilot_source_intent_count": (
                pilot["summary"]["source_intent_count"]
                if profile == "full"
                else 0
            ),
            "shard_body_bytes": sum(row["body_bytes"] for row in descriptors),
            "shard_count": len(descriptors),
            "source_intent_count": sum(row["row_count"] for row in variants),
            "variant_with_sources_count": len(variants),
        },
        "variant_source_counts": variants,
    }
    _require_negative_authority(value, label="source inventory profile manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source inventory profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryPackageError(str(error)) from None
    return value


def build_source_intent_profile_manifest(persona_id, profile):
    return copy.deepcopy(_canonical_profile_manifest(persona_id, profile))


SUITE_DEPENDENCY_CONTRACT = {
    "future_source_owned_fact_manifests_bind_origin_manifests": True,
    "profile_manifests_bind_origin_manifests_without_backedges": True,
    "reservation_source_profile_and_layout_artifacts_are_strictly_upstream": True,
    "suite_may_bind_future_fact_concrete_overlay_or_execution_artifact": False,
}

SUITE_REMAINING_BLOCKERS = [
    "semantic-content-and-source-owned-fact-membership-manifests-not-bound",
    "all-formal-source-recipe-profiles-unbound",
    "sixty-one-renderer-validator-or-formula-implementations-missing",
    "concrete-overlay-membership-shards-and-manifests-not-present",
    "source-level-scope-placement-allocation-not-solved",
    "future-complete-persona-package-cap-not-proved",
    "render-write-chunk-observation-history-and-kcs-execution-not-present",
]

LEDGER_INCLUDED_COMPONENTS = [
    "unique-pilot-and-full-residual-source-jsonl-shard-bodies",
    "pilot-and-full-residual-source-origin-manifests",
    "pilot-and-full-source-profile-manifests",
]


@functools.lru_cache(maxsize=1)
def _canonical_suite_descriptor():
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
    origin_bindings = [
        _manifest_binding(
            manifest,
            name="persona-v2-source-inventory-origin-manifest",
            role="source-origin-manifest",
            coordinate_fields=("persona_id", "origin"),
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        for manifest in origins
    ]
    profile_bindings = [
        _manifest_binding(
            manifest,
            name="persona-v2-source-inventory-profile-manifest",
            role="source-profile-manifest",
            coordinate_fields=("persona_id", "profile"),
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        for manifest in profiles
    ]
    origin_by_key = {
        (row["persona_id"], row["origin"]): row for row in origins
    }
    profile_by_key = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        persona_origins = [origin_by_key[(persona_id, origin)] for origin in ORIGIN_ORDER]
        persona_profiles = [profile_by_key[(persona_id, profile)] for profile in PROFILE_ORDER]
        shard_bytes = sum(
            manifest["summary"]["shard_body_bytes"] for manifest in persona_origins
        )
        origin_bytes = sum(
            len(canonical_json_bytes(manifest)) for manifest in persona_origins
        )
        profile_bytes = sum(
            len(canonical_json_bytes(manifest)) for manifest in persona_profiles
        )
        current = shard_bytes + origin_bytes + profile_bytes
        if current > MAX_PERSONA_PACKAGE_BYTES:
            raise PersonaV2SourceInventoryPackageError(
                f"current source component exceeds 16 MiB for {persona_id}"
            )
        ledgers.append(
            {
                "current_component_bytes": current,
                "future_complete_package_cap_proved": False,
                "headroom_bytes": MAX_PERSONA_PACKAGE_BYTES - current,
                "included_components": list(LEDGER_INCLUDED_COMPONENTS),
                "max_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
                "persona_id": persona_id,
                "profile_manifest_bytes": profile_bytes,
                "source_origin_manifest_bytes": origin_bytes,
                "unique_source_shard_body_bytes": shard_bytes,
            }
        )

    all_descriptors = [
        descriptor for manifest in origins for descriptor in manifest["shard_descriptors"]
    ]
    full_role_counts = copy.deepcopy(
        _shared_inputs()["layout"]["suite_gate_role_source_counts"]["full"]
    )
    active_variants = {
        row["variant_id"]
        for manifest in origins
        for row in manifest["variant_source_counts"]
    }
    value = {
        "artifact_kind": SUITE_ARTIFACT_KIND,
        "artifact_schema": SUITE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_body_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_current_source_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_203000_source_slot_rows_materialized": True,
            "all_40_origin_manifests_bound": True,
            "all_40_profile_manifests_bound": True,
            "all_73_shard_body_bytes_and_sha_bound": True,
            "all_variant_inventory_profile_assignments_complete": True,
            "concrete_overlay_membership_bound": False,
            "current_source_inventory_component_cap_satisfied": True,
            "formal_complete_persona_package_cap_proved": False,
            "formal_source_recipe_profiles_bound": False,
            "full_manifest_exact_pilot_origin_reuse_proved": True,
            "present_fact_sets_bound": False,
            "semantic_content_catalogs_bound": False,
            "source_intent_inventory_complete": False,
        },
        "completion_scope": (
            "all-203000-structural-source-slot-rows-73-shards-40-origin-and-40-"
            "profile-manifests-only-no-semantic-catalog-no-formal-recipe-no-"
            "complete-package-cap-no-execution-no-g0"
        ),
        "coverage": {
            "full_residual_source_intent_count": source_layout.EXPECTED_FULL_RESIDUAL_SOURCE_COUNT,
            "gate_role_source_counts": full_role_counts,
            "maximum_origin_manifest_bytes": max(
                row["canonical_bytes"] for row in origin_bindings
            ),
            "maximum_profile_manifest_bytes": max(
                row["canonical_bytes"] for row in profile_bindings
            ),
            "maximum_row_bytes_including_lf": max(
                row["max_row_bytes_including_lf"] for row in all_descriptors
            ),
            "maximum_shard_body_bytes": max(
                row["body_bytes"] for row in all_descriptors
            ),
            "origin_manifest_count": len(origins),
            "persona_count": len(envelope.PERSONA_IDS),
            "pilot_source_intent_count": source_layout.EXPECTED_PILOT_SOURCE_COUNT,
            "profile_manifest_count": len(profiles),
            "shard_body_bytes": sum(row["body_bytes"] for row in all_descriptors),
            "shard_count": len(all_descriptors),
            "source_intent_count": sum(row["row_count"] for row in all_descriptors),
            "variant_identity_count": inventory_profile.EXPECTED_PROFILE_COUNT,
            "variant_with_sources_count": len(active_variants),
        },
        "dependency_direction_contract": copy.deepcopy(
            SUITE_DEPENDENCY_CONTRACT
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [
            "persona-v2-source-inventory-layout",
            "persona-v2-source-inventory-profile-catalog",
            "persona-v2-overlay-reservation-suite",
        ],
        "input_bindings": copy.deepcopy(_shared_inputs()["shared_bindings"]),
        "orders": {
            "origin": list(ORIGIN_ORDER),
            "origin_manifests": "persona-then-origin",
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "profile_manifests": "persona-then-profile",
            "shards_within_profile": "pilot-origin-then-full-residual-origin-then-shard-ordinal",
        },
        "origin_manifest_bindings": origin_bindings,
        "persona_current_component_byte_ledgers": ledgers,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": list(SUITE_REMAINING_BLOCKERS),
    }
    if (
        value["coverage"]["source_intent_count"] != EXPECTED_SOURCE_INTENT_COUNT
        or value["coverage"]["shard_count"] != EXPECTED_SHARD_COUNT
        or len(origins) != EXPECTED_ORIGIN_MANIFEST_COUNT
        or len(profiles) != EXPECTED_PROFILE_MANIFEST_COUNT
    ):
        raise PersonaV2SourceInventoryPackageError(
            "source suite exact coverage drifted"
        )
    _require_negative_authority(value, label="source inventory suite")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 source inventory suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryPackageError(str(error)) from None
    _release_overlay_projection_caches()
    return value


def build_source_intent_suite_descriptor():
    return copy.deepcopy(_canonical_suite_descriptor())


def canonical_json_bytes(value):
    if type(value) is not dict:
        raise PersonaV2SourceInventoryPackageError(
            "source package artifact must be an object"
        )
    schema = value.get("artifact_schema")
    if schema == ORIGIN_ARTIFACT_SCHEMA:
        label, cap = "persona v2 source inventory origin manifest", MAX_ORIGIN_MANIFEST_BYTES
    elif schema == PROFILE_ARTIFACT_SCHEMA:
        label, cap = "persona v2 source inventory profile manifest", MAX_PROFILE_MANIFEST_BYTES
    elif schema == SUITE_ARTIFACT_SCHEMA:
        label, cap = "persona v2 source inventory suite", MAX_SUITE_DESCRIPTOR_BYTES
    else:
        raise PersonaV2SourceInventoryPackageError(
            f"unknown source package artifact schema: {schema!r}"
        )
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=cap)
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SourceInventoryPackageError(str(error)) from None


def validate_source_intent_origin_manifest(persona_id, origin, value):
    expected = build_source_intent_origin_manifest(persona_id, origin)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceInventoryPackageError(
            "source origin manifest differs from exact regeneration"
        )
    return True


def validate_source_intent_profile_manifest(persona_id, profile, value):
    expected = build_source_intent_profile_manifest(persona_id, profile)
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceInventoryPackageError(
            "source profile manifest differs from exact regeneration"
        )
    return True


def validate_source_intent_suite_descriptor(value):
    expected = build_source_intent_suite_descriptor()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2SourceInventoryPackageError(
            "source suite descriptor differs from exact regeneration"
        )
    return True


def source_intent_origin_manifest_sha256(persona_id, origin, value=None):
    if value is None:
        value = build_source_intent_origin_manifest(persona_id, origin)
    validate_source_intent_origin_manifest(persona_id, origin, value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_intent_profile_manifest_sha256(persona_id, profile, value=None):
    if value is None:
        value = build_source_intent_profile_manifest(persona_id, profile)
    validate_source_intent_profile_manifest(persona_id, profile, value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def source_intent_suite_descriptor_sha256(value=None):
    if value is None:
        value = build_source_intent_suite_descriptor()
    validate_source_intent_suite_descriptor(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_complete_source_intent_inventory():
    raise PersonaV2SourceInventoryPackageError(
        "all 203,000 structural source-slot rows and 73 shard digests are exact, "
        "but semantic content/fact catalogs, all formal recipes, sixty-one "
        "implementations, concrete overlay membership, allocation, rendering, "
        "history, complete package-cap proof, execution, and G0 authority remain absent"
    )


__all__ = [
    "AUTHORITY_FIELDS",
    "MAX_INTENTS_PER_SHARD",
    "MAX_INTENT_ROW_BYTES_INCLUDING_LF",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_PERSONA_PACKAGE_BYTES",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_SHARD_BODY_BYTES",
    "MAX_SUITE_DESCRIPTOR_BYTES",
    "PersonaV2SourceInventoryPackageError",
    "build_source_intent_origin_manifest",
    "build_source_intent_profile_manifest",
    "build_source_intent_shard_descriptor",
    "build_source_intent_suite_descriptor",
    "canonical_json_bytes",
    "iter_source_intent_rows",
    "require_complete_source_intent_inventory",
    "source_intent_origin_manifest_sha256",
    "source_intent_profile_manifest_sha256",
    "source_intent_shard_body_bytes",
    "source_intent_suite_descriptor_sha256",
    "validate_source_intent_origin_manifest",
    "validate_source_intent_profile_manifest",
    "validate_source_intent_suite_descriptor",
]
