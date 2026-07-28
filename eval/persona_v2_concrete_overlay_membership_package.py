"""Concrete pre-solve overlay memberships for persona-PC v2.

This package joins the exact overlay reservations to the immutable structural
source inventory and to the source-owned semantic/fact memberships.  It owns
only compact pre-solve membership rows.  Logical identities and fact arrays
remain owned by the upstream semantic package, while scope placement, rendered
bytes, observed search behavior, history, and execution authority remain
strictly downstream.
"""

from __future__ import annotations

import copy
import functools
import gc
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay_contract
    from . import persona_v2_overlay_reservation_layout as reservation_layout
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_semantic_membership_package as semantic_package
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay_contract
    import persona_v2_overlay_reservation_layout as reservation_layout
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_semantic_membership_package as semantic_package


ORIGIN_ARTIFACT_SCHEMA = (
    "kio.persona.pc-concrete-overlay-membership-origin-manifest/v2"
)
ORIGIN_ARTIFACT_KIND = "persona-pc-v2-concrete-overlay-membership-origin-manifest"
PROFILE_ARTIFACT_SCHEMA = (
    "kio.persona.pc-concrete-overlay-membership-profile-manifest/v2"
)
PROFILE_ARTIFACT_KIND = "persona-pc-v2-concrete-overlay-membership-profile-manifest"
SUITE_ARTIFACT_SCHEMA = "kio.persona.pc-concrete-overlay-membership-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-concrete-overlay-membership-suite"
ARTIFACT_SCHEMA_VERSION = 2

ORIGIN_ORDER = semantic_package.ORIGIN_ORDER
PROFILE_ORDER = semantic_package.PROFILE_ORDER
RELATION_ORDER = tuple(overlay_contract.CONTENT_RELATION_ORDER)
ORIGIN_TO_TARGET_PROFILE = reservation_layout.ORIGIN_TO_TARGET_PROFILE

MAX_ROW_BYTES_INCLUDING_LF = 768
MAX_ROWS_PER_SHARD = 4_096
MAX_SHARD_BODY_BYTES = 4 * 2**20
MAX_ORIGIN_MANIFEST_BYTES = 128 * 1024
MAX_PROFILE_MANIFEST_BYTES = 128 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_PERSONA_PACKAGE_BYTES = source_package.MAX_PERSONA_PACKAGE_BYTES

EXPECTED_CONTENT_RELATION_ROW_COUNT = 19_870
EXPECTED_ATTACHMENT_ROW_COUNT = 5_690
EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT = 2_100
EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT = 25_560
EXPECTED_RICH_ROW_COUNT = 27_660
EXPECTED_UNIQUE_OVERLAY_SOURCE_COUNT = 46_840
EXPECTED_UNIQUE_JOINED_SOURCE_COUNT = 48_940
EXPECTED_CONFLICT_PAIR_COUNT = 1_560
EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_SHARD_COUNT = 40

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "formal_complete_persona_package_cap_proved",
        "history_executor_available",
        "kio_execution_available",
        "query_instances_rendered",
        "query_spec_hashed",
        "renderer_available",
    }
)

CONTENT_RELATION_ROW_FIELDS = frozenset(
    {
        "anchor_fact_profile_id",
        "anchor_intent_key",
        "cluster_key",
        "derivative_fact_profile_id",
        "derivative_intent_key",
        "placement_class_requirement",
        "relation_kind",
        "row_kind",
        "search_participation_requirement_id",
    }
)
ATTACHMENT_ROW_FIELDS = frozenset(
    {
        "attachment_key",
        "content_relation_membership",
        "decoded_payload_equivalence_key",
        "host_fact_profile_id",
        "host_intent_key",
        "host_member_count",
        "member_ordinal",
        "row_kind",
        "search_participation_requirement_id",
        "standalone_member_fact_profile_id",
        "standalone_member_intent_key",
    }
)
SEMANTIC_ANCHOR_ROW_FIELDS = frozenset(
    {
        "fact_profile_id",
        "intent_key",
        "row_kind",
        "semantic_anchor_slot_ordinal",
    }
)
SHARD_DESCRIPTOR_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "file_name",
        "first_row_sort_key",
        "last_row_sort_key",
        "maximum_row_bytes_including_lf",
        "origin",
        "persona_id",
        "row_count",
        "shard_index",
    }
)
DRAFT_PROJECTION_RECEIPT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "first_row_sort_key",
        "last_row_sort_key",
        "maximum_row_bytes_including_lf",
        "row_count",
    }
)
ORIGIN_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "draft_membership_projection_receipt",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "origin",
        "persona_id",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "target_marginals",
        "target_profile",
    }
)
PROFILE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "origin_manifest_bindings",
        "origin_order",
        "persona_id",
        "profile",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "target_marginals",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "orders",
        "origin_manifest_bindings",
        "persona_current_component_byte_ledger_contract",
        "persona_current_component_byte_ledgers",
        "profile_manifest_bindings",
        "remaining_blockers",
        "summary",
    }
)

REMAINING_BLOCKERS = [
    "formal-source-recipes-and-renderer-validator-implementations",
    "corpus-semantic-namespace-and-query-history-target-mapping",
    "scope-placement-joint-allocation-and-proof",
    "actual-payload-search-and-raw-identity-attestation",
    "render-write-chunk-observation-history-and-kio-execution",
    "future-complete-persona-package-cap-proof",
]


class PersonaV2ConcreteOverlayMembershipPackageError(ValueError):
    """Raised when the concrete overlay membership contract is broken."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"unknown persona ID: {persona_id!r}"
        )


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"unknown concrete overlay origin: {origin!r}"
        )


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"unknown concrete overlay profile: {profile!r}"
        )


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_negative_authority(value, *, label):
    if type(value) is not dict:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"{label} must be an object"
        )
    authority = value.get("authority")
    if (
        value.get("g0_contract_frozen") is not False
        or set(authority or {}) != AUTHORITY_FIELDS
        or any(type(flag) is not bool or flag is not False for flag in (authority or {}).values())
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"{label} authority must remain the exact all-false schema"
        )


def _ascii_key(value):
    if type(value) is not str:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "canonical ASCII key must be a string"
        )
    try:
        return value.encode("ascii")
    except UnicodeEncodeError:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "canonical key must contain ASCII only"
        ) from None


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _jsonl_row_bytes(row, *, label):
    try:
        raw = artifact_common.canonical_json_bytes(
            row, label=label, max_bytes=MAX_ROW_BYTES_INCLUDING_LF - 1
        ) + b"\n"
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None
    if len(raw) > MAX_ROW_BYTES_INCLUDING_LF:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"{label} exceeds its LF-inclusive row cap"
        )
    return raw


def _artifact_binding(
    name,
    role,
    value,
    *,
    canonical,
    coordinate_fields=(),
):
    required = {"artifact_kind", "artifact_schema", "artifact_schema_version"}
    if type(value) is not dict or not required <= set(value):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"{name} binding target lacks its exact artifact identity"
        )
    raw = canonical(value)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": _sha256(raw),
    }
    for field in coordinate_fields:
        if field not in value:
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                f"{name} binding lacks coordinate field {field}"
            )
        result[field] = value[field]
    return result


def _concrete_manifest_binding(
    name, role, value, *, coordinate_fields=()
):
    return _artifact_binding(
        name,
        role,
        value,
        canonical=canonical_json_bytes,
        coordinate_fields=coordinate_fields,
    )


@functools.lru_cache(maxsize=1)
def _base_inputs():
    contract = overlay_contract.build_overlay_contract()
    catalog = semantic_package.build_source_semantic_membership_catalog()
    overlay_contract.validate_overlay_contract(contract)
    semantic_package.validate_source_semantic_membership_catalog(catalog)
    fact_profiles = {
        (row["persona_id"], row["fact_profile_id"]): row
        for row in catalog["fact_profiles"]
    }
    if len(fact_profiles) != semantic_package.EXPECTED_FACT_PROFILE_COUNT:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "semantic fact-profile catalog coverage drifted"
        )
    return {
        "catalog": catalog,
        "contract": contract,
        "fact_profiles": fact_profiles,
    }


@functools.lru_cache(maxsize=1)
def _reservation_suite_value():
    reservation_suite = reservation_layout.build_overlay_reservation_suite()
    reservation_layout.validate_overlay_reservation_suite(reservation_suite)
    return reservation_suite


@functools.lru_cache(maxsize=1)
def _source_suite_value():
    source_suite = source_package.build_source_intent_suite_descriptor()
    source_package.validate_source_intent_suite_descriptor(source_suite)
    return source_suite


@functools.lru_cache(maxsize=1)
def _semantic_suite_value():
    semantic_suite = semantic_package.build_source_semantic_membership_suite_descriptor()
    semantic_package.validate_source_semantic_membership_suite_descriptor(
        semantic_suite
    )
    return semantic_suite


def _row_sort_key(row):
    row_kind = row.get("row_kind") if type(row) is dict else None
    if row_kind == "content-relation-membership":
        relation = row.get("relation_kind")
        if relation not in RELATION_ORDER:
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                f"unknown concrete relation kind: {relation!r}"
            )
        return (0, RELATION_ORDER.index(relation), _ascii_key(row["cluster_key"]))
    if row_kind == "attachment-membership":
        return (1, 0, _ascii_key(row["attachment_key"]))
    if row_kind == "semantic-anchor-membership":
        ordinal = row.get("semantic_anchor_slot_ordinal")
        if type(ordinal) is not int or ordinal < 1:
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                "semantic anchor slot ordinal must be a positive exact integer"
            )
        return (2, ordinal, _ascii_key(row["intent_key"]))
    raise PersonaV2ConcreteOverlayMembershipPackageError(
        f"unknown concrete overlay row kind: {row_kind!r}"
    )


def _serialized_sort_key(row):
    key = _row_sort_key(row)
    return [key[0], key[1], key[2].decode("ascii")]


def _require_row_schema(row):
    row_kind = row.get("row_kind") if type(row) is dict else None
    expected = {
        "content-relation-membership": CONTENT_RELATION_ROW_FIELDS,
        "attachment-membership": ATTACHMENT_ROW_FIELDS,
        "semantic-anchor-membership": SEMANTIC_ANCHOR_ROW_FIELDS,
    }.get(row_kind)
    if expected is None or set(row) != expected:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"concrete overlay row schema drifted: {row_kind!r}"
        )
    _jsonl_row_bytes(row, label="persona v2 concrete overlay membership row")


def _profile_origins(profile):
    _require_profile(profile)
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


@functools.lru_cache(maxsize=1)
def _origin_projection(persona_id, origin):
    """Return one bounded rich projection and the exact upstream owners."""

    _require_persona_id(persona_id)
    _require_origin(origin)
    semantic_manifest = (
        semantic_package.build_source_semantic_membership_origin_manifest(
            persona_id, origin
        )
    )
    source_manifest = source_package.build_source_intent_origin_manifest(
        persona_id, origin
    )
    reservation = reservation_layout.build_overlay_reservation_origin(
        persona_id, origin
    )
    catalog = _base_inputs()["catalog"]

    referenced_intents = set()
    overlay_intents = set()
    anchor_intents = set()
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            keys = (row["anchor_intent_key"], row["derivative_intent_key"])
        elif row["row_kind"] == "attachment-membership-reservation":
            keys = (row["host_intent_key"], row["standalone_member_intent_key"])
        else:
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                "reservation contains an unknown row kind"
            )
        referenced_intents.update(keys)
        overlay_intents.update(keys)
    for row in reservation["semantic_anchor_slots"]:
        referenced_intents.add(row["intent_key"])
        anchor_intents.add(row["intent_key"])
    if overlay_intents & anchor_intents:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "semantic anchors overlap relation or attachment membership"
        )

    membership_by_intent = {}
    for descriptor in source_manifest["shard_descriptors"]:
        shard_ordinal = descriptor["shard_ordinal"]
        for membership in semantic_package.iter_expanded_fact_membership_rows(
            persona_id, origin, shard_ordinal
        ):
            intent_key = membership["intent_key"]
            if intent_key not in referenced_intents:
                continue
            if intent_key in membership_by_intent:
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "semantic expansion contains a duplicate joined intent"
                )
            if (
                membership.get("persona_id") != persona_id
                or membership.get("origin") != origin
            ):
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "semantic membership escaped its persona/origin coordinate"
                )
            profile_key = (persona_id, membership["fact_profile_id"])
            profile = _base_inputs()["fact_profiles"].get(profile_key)
            if (
                profile is None
                or membership["present_fact_ids"] != profile["present_fact_ids"]
            ):
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "joined semantic membership differs from its fact profile"
                )
            membership_by_intent[intent_key] = membership
    if set(membership_by_intent) != referenced_intents:
        missing = sorted(referenced_intents - set(membership_by_intent), key=_ascii_key)
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"semantic expansion does not cover every reserved intent: {missing[:1]}"
        )

    rows = []
    relation_counts = {relation: 0 for relation in RELATION_ORDER}
    attachment_overlap_count = 0
    for reservation_row in reservation["reservation_rows"]:
        if reservation_row["row_kind"] == "content-relation-reservation":
            anchor_key = reservation_row["anchor_intent_key"]
            derivative_key = reservation_row["derivative_intent_key"]
            relation = reservation_row["relation_kind"]
            anchor_membership = membership_by_intent[anchor_key]
            derivative_membership = membership_by_intent[derivative_key]
            if not anchor_membership["present_fact_ids"] or not derivative_membership[
                "present_fact_ids"
            ]:
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "content relation endpoint cannot use an empty fact profile"
                )
            if relation == "conflict-copy":
                conflict = reservation_row["conflict_fact_binding"]
                if (
                    anchor_membership["present_fact_ids"]
                    != conflict["branch_a_present_fact_ids"]
                    or derivative_membership["present_fact_ids"]
                    != conflict["branch_b_present_fact_ids"]
                ):
                    raise PersonaV2ConcreteOverlayMembershipPackageError(
                        "conflict endpoints differ from the exact reserved A/B facts"
                    )
            elif (
                anchor_membership["fact_profile_id"]
                != derivative_membership["fact_profile_id"]
                or anchor_membership["present_fact_ids"]
                != derivative_membership["present_fact_ids"]
            ):
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "exact/near endpoints must share one exact fact profile"
                )
            row = {
                "anchor_fact_profile_id": anchor_membership["fact_profile_id"],
                "anchor_intent_key": anchor_key,
                "cluster_key": reservation_row["cluster_key"],
                "derivative_fact_profile_id": derivative_membership[
                    "fact_profile_id"
                ],
                "derivative_intent_key": derivative_key,
                "placement_class_requirement": reservation_row[
                    "placement_class_requirement"
                ],
                "relation_kind": relation,
                "row_kind": "content-relation-membership",
                "search_participation_requirement_id": "content-relation-v2",
            }
            relation_counts[relation] += 1
        else:
            host_key = reservation_row["host_intent_key"]
            member_key = reservation_row["standalone_member_intent_key"]
            if (
                not membership_by_intent[host_key]["present_fact_ids"]
                or not membership_by_intent[member_key]["present_fact_ids"]
            ):
                raise PersonaV2ConcreteOverlayMembershipPackageError(
                    "attachment host/member cannot use an empty fact profile"
                )
            row = {
                "attachment_key": reservation_row["attachment_key"],
                "content_relation_membership": reservation_row[
                    "content_relation_membership"
                ],
                "decoded_payload_equivalence_key": reservation_row[
                    "decoded_payload_equivalence_key"
                ],
                "host_fact_profile_id": membership_by_intent[host_key][
                    "fact_profile_id"
                ],
                "host_intent_key": host_key,
                "host_member_count": reservation_row["host_member_count"],
                "member_ordinal": reservation_row["member_ordinal"],
                "row_kind": "attachment-membership",
                "search_participation_requirement_id": "attachment-structural-v2",
                "standalone_member_fact_profile_id": membership_by_intent[member_key][
                    "fact_profile_id"
                ],
                "standalone_member_intent_key": member_key,
            }
            attachment_overlap_count += int(
                reservation_row["content_relation_membership"] != "none"
            )
        _require_row_schema(row)
        rows.append(row)

    for anchor in reservation["semantic_anchor_slots"]:
        intent_key = anchor["intent_key"]
        anchor_profile = _base_inputs()["fact_profiles"][
            (persona_id, membership_by_intent[intent_key]["fact_profile_id"])
        ]
        if anchor_profile["profile_kind"] != "w0-singleton":
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                "semantic anchor must resolve to an exact singleton fact profile"
            )
        row = {
            "fact_profile_id": membership_by_intent[intent_key]["fact_profile_id"],
            "intent_key": intent_key,
            "row_kind": "semantic-anchor-membership",
            "semantic_anchor_slot_ordinal": anchor[
                "semantic_anchor_slot_ordinal"
            ],
        }
        _require_row_schema(row)
        rows.append(row)

    rows.sort(key=_row_sort_key)
    sort_keys = [_row_sort_key(row) for row in rows]
    if len(sort_keys) != len(set(sort_keys)):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay membership sort keys are not unique"
        )
    relation_row_count = sum(relation_counts.values())
    attachment_row_count = sum(
        row["row_kind"] == "attachment-membership" for row in rows
    )
    anchor_row_count = len(anchor_intents)
    if (
        relation_row_count
        != reservation["summary"]["content_relation_row_count"]
        or attachment_row_count
        != reservation["summary"]["attachment_membership_row_count"]
        or anchor_row_count
        != reservation["summary"]["semantic_anchor_slot_count"]
        or len(rows)
        != reservation["summary"]["reservation_row_count"] + anchor_row_count
        or len(overlay_intents)
        != reservation["summary"]["overlay_referenced_unique_source_intent_count"]
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay origin cardinality differs from its reservation"
        )

    return {
        "anchor_intents": anchor_intents,
        "attachment_overlap_count": attachment_overlap_count,
        "catalog": catalog,
        "membership_by_intent": membership_by_intent,
        "overlay_intents": overlay_intents,
        "relation_counts": relation_counts,
        "reservation": reservation,
        "rows": tuple(rows),
        "semantic_manifest": semantic_manifest,
        "source_manifest": source_manifest,
    }


def iter_concrete_overlay_membership_origin_rows(persona_id, origin):
    """Yield one origin's exact rich rows in deterministic shard order."""

    for row in _origin_projection(persona_id, origin)["rows"]:
        yield copy.deepcopy(row)


def _draft_projection_row(row):
    if row["row_kind"] == "content-relation-membership":
        value = {
            "anchor_intent_key": row["anchor_intent_key"],
            "cluster_key": row["cluster_key"],
            "derivative_intent_key": row["derivative_intent_key"],
            "placement_class": row["placement_class_requirement"],
            "relation_kind": row["relation_kind"],
            "row_kind": "content-relation",
            "search_participation_profile_id": row[
                "search_participation_requirement_id"
            ],
        }
    elif row["row_kind"] == "attachment-membership":
        value = {
            "attachment_key": row["attachment_key"],
            "decoded_payload_equivalence_key": row[
                "decoded_payload_equivalence_key"
            ],
            "host_intent_key": row["host_intent_key"],
            "member_ordinal": row["member_ordinal"],
            "row_kind": "attachment-membership",
            "search_participation_profile_id": row[
                "search_participation_requirement_id"
            ],
            "standalone_member_intent_key": row[
                "standalone_member_intent_key"
            ],
        }
    else:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "semantic anchors are excluded from the draft membership projection"
        )
    return value


def _draft_projection_receipt(rows):
    rich_projected_rows = [
        row for row in rows if row["row_kind"] != "semantic-anchor-membership"
    ]
    projected = [_draft_projection_row(row) for row in rich_projected_rows]
    parts = [
        _jsonl_row_bytes(
            row, label="persona v2 draft overlay membership projection row"
        )
        for row in projected
    ]
    if not parts:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "draft overlay membership projection cannot be empty"
        )
    body = b"".join(parts)
    value = {
        "body_bytes": len(body),
        "body_sha256": _sha256(body),
        "first_row_sort_key": _serialized_sort_key(rich_projected_rows[0]),
        "last_row_sort_key": _serialized_sort_key(rich_projected_rows[-1]),
        "maximum_row_bytes_including_lf": max(map(len, parts)),
        "row_count": len(projected),
    }
    if set(value) != DRAFT_PROJECTION_RECEIPT_FIELDS:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "draft projection receipt schema drifted"
        )
    return value


@functools.lru_cache(maxsize=1)
def _origin_shards(persona_id, origin):
    rows = _origin_projection(persona_id, origin)["rows"]
    shards = []
    current_rows = []
    current_parts = []
    current_bytes = 0
    for row in rows:
        raw = _jsonl_row_bytes(
            row, label="persona v2 concrete overlay membership row"
        )
        if current_rows and (
            len(current_rows) == MAX_ROWS_PER_SHARD
            or current_bytes + len(raw) > MAX_SHARD_BODY_BYTES
        ):
            shards.append((tuple(current_rows), b"".join(current_parts)))
            current_rows = []
            current_parts = []
            current_bytes = 0
        current_rows.append(row)
        current_parts.append(raw)
        current_bytes += len(raw)
    if current_rows:
        shards.append((tuple(current_rows), b"".join(current_parts)))
    if not shards:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay origin cannot have zero shards"
        )
    return tuple(shards)


def concrete_overlay_membership_shard_body_bytes(
    persona_id, origin, shard_index
):
    _require_persona_id(persona_id)
    _require_origin(origin)
    if type(shard_index) is not int or shard_index < 0:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "shard index must be a nonnegative exact integer"
        )
    shards = _origin_shards(persona_id, origin)
    if shard_index >= len(shards):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"unknown concrete overlay shard: {persona_id}/{origin}/{shard_index}"
        )
    return bytes(shards[shard_index][1])


def build_concrete_overlay_membership_shard_descriptor(
    persona_id, origin, shard_index
):
    body = concrete_overlay_membership_shard_body_bytes(
        persona_id, origin, shard_index
    )
    rows = _origin_shards(persona_id, origin)[shard_index][0]
    value = {
        "body_bytes": len(body),
        "body_sha256": _sha256(body),
        "file_name": (
            f"{persona_id}-concrete-overlay-membership-{origin}-"
            f"{shard_index:04d}.jsonl"
        ),
        "first_row_sort_key": _serialized_sort_key(rows[0]),
        "last_row_sort_key": _serialized_sort_key(rows[-1]),
        "maximum_row_bytes_including_lf": max(
            len(line) + 1 for line in body.splitlines()
        ),
        "origin": origin,
        "persona_id": persona_id,
        "row_count": len(rows),
        "shard_index": shard_index,
    }
    if (
        set(value) != SHARD_DESCRIPTOR_FIELDS
        or value["row_count"] > MAX_ROWS_PER_SHARD
        or value["body_bytes"] > MAX_SHARD_BODY_BYTES
        or value["maximum_row_bytes_including_lf"]
        > MAX_ROW_BYTES_INCLUDING_LF
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay shard descriptor violates its cap or schema"
        )
    return value


def _persona_target(persona_id, target_profile):
    for row in _base_inputs()["contract"]["persona_target_marginals"]:
        if row["persona_id"] == persona_id:
            return copy.deepcopy(row["targets"][target_profile])
    raise PersonaV2ConcreteOverlayMembershipPackageError(
        f"overlay contract lacks persona target: {persona_id}/{target_profile}"
    )


def _origin_summary(projection, descriptors):
    relation_counts = projection["relation_counts"]
    content_count = sum(relation_counts.values())
    attachment_count = projection["reservation"]["summary"][
        "attachment_membership_row_count"
    ]
    anchor_count = len(projection["anchor_intents"])
    value = {
        "attachment_exact_overlap_row_count": projection[
            "attachment_overlap_count"
        ],
        "attachment_host_count": projection["reservation"]["summary"][
            "attachment_host_intent_count"
        ],
        "attachment_membership_row_count": attachment_count,
        "conflict_copy_row_count": relation_counts["conflict-copy"],
        "content_relation_row_count": content_count,
        "exact_duplicate_row_count": relation_counts["exact-duplicate"],
        "joined_source_reference_occurrence_count": (
            2 * content_count + 2 * attachment_count + anchor_count
        ),
        "maximum_row_bytes_including_lf": max(
            row["maximum_row_bytes_including_lf"] for row in descriptors
        ),
        "near_revision_row_count": relation_counts["near-revision"],
        "overlay_membership_row_count": content_count + attachment_count,
        "overlay_source_reference_occurrence_count": (
            2 * content_count + 2 * attachment_count
        ),
        "rich_row_count": content_count + attachment_count + anchor_count,
        "semantic_anchor_membership_row_count": anchor_count,
        "shard_body_bytes": sum(row["body_bytes"] for row in descriptors),
        "shard_count": len(descriptors),
        "unique_joined_source_count": len(
            projection["overlay_intents"] | projection["anchor_intents"]
        ),
        "unique_overlay_source_count": len(projection["overlay_intents"]),
    }
    return value


def _origin_input_bindings(projection):
    persona_id = projection["reservation"]["persona_id"]
    origin = projection["reservation"]["origin"]
    return [
        _artifact_binding(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            projection["catalog"],
            canonical=semantic_package.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-overlay-reservation-origin",
            "matching-overlay-relation-container-and-anchor-reservation",
            projection["reservation"],
            canonical=reservation_layout.canonical_json_bytes,
            coordinate_fields=("persona_id", "origin"),
        ),
        _artifact_binding(
            "persona-v2-source-inventory-origin-manifest",
            "matching-immutable-structural-source-owner",
            projection["source_manifest"],
            canonical=source_package.canonical_json_bytes,
            coordinate_fields=("persona_id", "origin"),
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "matching-source-owned-context-and-fact-membership-owner",
            projection["semantic_manifest"],
            canonical=semantic_package.canonical_json_bytes,
            coordinate_fields=("persona_id", "origin"),
        ),
    ]


@functools.lru_cache(maxsize=40)
def _canonical_origin_manifest(persona_id, origin):
    projection = _origin_projection(persona_id, origin)
    descriptors = [
        build_concrete_overlay_membership_shard_descriptor(
            persona_id, origin, shard_index
        )
        for shard_index in range(len(_origin_shards(persona_id, origin)))
    ]
    input_bindings = _origin_input_bindings(projection)
    summary = _origin_summary(projection, descriptors)
    target_profile = ORIGIN_TO_TARGET_PROFILE[origin]
    value = {
        "artifact_kind": ORIGIN_ARTIFACT_KIND,
        "artifact_schema": ORIGIN_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_row_bytes_including_lf": MAX_ROW_BYTES_INCLUDING_LF,
            "max_rows_per_shard": MAX_ROWS_PER_SHARD,
            "max_shard_body_bytes": MAX_SHARD_BODY_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "shard_index_base": 0,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_origin_reservation_membership_rows_joined": True,
            "all_origin_semantic_anchor_slots_joined": True,
            "all_referenced_source_fact_profiles_bound": True,
            "concrete_overlay_membership_bound": True,
            "draft_membership_projection_receipt_bound": True,
            "formal_complete_persona_package_cap_proved": False,
            "placement_integer_allocation_bound": False,
            "raw_or_rendered_identity_attested": False,
            "scope_assignment_present": False,
            "search_history_or_query_observation_bound": False,
        },
        "completion_scope": (
            "one-origin-rich-pre-solve-overlay-membership-and-semantic-anchor-"
            "join-no-scope-solution-no-render-no-history-no-search-observation-no-g0"
        ),
        "dependency_direction_contract": {
            "logical_identity_and_fact_arrays_remain_owned_by_semantic_package": True,
            "matching_reservation_source_and_semantic_origins_are_strictly_upstream": True,
            "placement_requirement_is_not_scope_assignment": True,
            "semantic_catalog_is_strictly_upstream": True,
            "upstream_back_reference_allowed": False,
        },
        "draft_membership_projection_receipt": _draft_projection_receipt(
            projection["rows"]
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-join-not-observed-user-statistics"
        ),
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "shard_descriptors": descriptors,
        "summary": summary,
        "target_marginals": _persona_target(persona_id, target_profile),
        "target_profile": target_profile,
    }
    if (
        set(value) != ORIGIN_TOP_LEVEL_FIELDS
        or summary["overlay_membership_row_count"]
        != value["target_marginals"]["membership_row_count"]
        or summary["content_relation_row_count"]
        != value["target_marginals"]["content_relation_cluster_count"]
        or summary["attachment_membership_row_count"]
        != value["target_marginals"]["attachment_membership_count"]
        or summary["attachment_exact_overlap_row_count"]
        != value["target_marginals"]["attachment_exact_duplicate_overlap_count"]
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay origin manifest differs from exact targets"
        )
    _require_negative_authority(value, label="concrete overlay origin manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 concrete overlay origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None
    return value


def build_concrete_overlay_membership_origin_manifest(persona_id, origin):
    return copy.deepcopy(_canonical_origin_manifest(persona_id, origin))


def _profile_input_bindings(persona_id, profile):
    catalog = _base_inputs()["catalog"]
    reservation_suite = _reservation_suite_value()
    source_profile = source_package.build_source_intent_profile_manifest(
        persona_id, profile
    )
    semantic_profile = (
        semantic_package.build_source_semantic_membership_profile_manifest(
            persona_id, profile
        )
    )
    return [
        _artifact_binding(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            catalog,
            canonical=semantic_package.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-overlay-reservation-suite",
            "global-overlay-reservation-index",
            reservation_suite,
            canonical=reservation_layout.overlay_reservation_suite_bytes,
        ),
        _artifact_binding(
            "persona-v2-source-inventory-profile-manifest",
            "matching-structural-source-profile-composition",
            source_profile,
            canonical=source_package.canonical_json_bytes,
            coordinate_fields=("persona_id", "profile"),
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-profile-manifest",
            "matching-source-semantic-profile-composition",
            semantic_profile,
            canonical=semantic_package.canonical_json_bytes,
            coordinate_fields=("persona_id", "profile"),
        ),
    ]


def _profile_summary(origins, profile):
    summaries = [row["summary"] for row in origins]
    additive_fields = (
        "attachment_exact_overlap_row_count",
        "attachment_host_count",
        "attachment_membership_row_count",
        "conflict_copy_row_count",
        "content_relation_row_count",
        "exact_duplicate_row_count",
        "joined_source_reference_occurrence_count",
        "near_revision_row_count",
        "overlay_membership_row_count",
        "overlay_source_reference_occurrence_count",
        "rich_row_count",
        "semantic_anchor_membership_row_count",
        "shard_body_bytes",
        "shard_count",
        "unique_joined_source_count",
        "unique_overlay_source_count",
    )
    pilot_summary = summaries[0]
    value = {
        field: sum(summary[field] for summary in summaries)
        for field in additive_fields
    }
    value.update(
        {
            "maximum_row_bytes_including_lf": max(
                summary["maximum_row_bytes_including_lf"]
                for summary in summaries
            ),
            "origin_manifest_count": len(origins),
            "reused_pilot_rich_row_count": (
                pilot_summary["rich_row_count"] if profile == "full" else 0
            ),
            "reused_pilot_shard_body_bytes": (
                pilot_summary["shard_body_bytes"] if profile == "full" else 0
            ),
            "reused_pilot_shard_count": (
                pilot_summary["shard_count"] if profile == "full" else 0
            ),
        }
    )
    return value


@functools.lru_cache(maxsize=40)
def _canonical_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    _require_profile(profile)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for origin in _profile_origins(profile)
    ]
    origin_bindings = [
        _concrete_manifest_binding(
            "persona-v2-concrete-overlay-membership-origin-manifest",
            "immutable-concrete-overlay-origin-owner",
            manifest,
            coordinate_fields=("persona_id", "origin"),
        )
        for manifest in origins
    ]
    input_bindings = _profile_input_bindings(persona_id, profile)
    summary = _profile_summary(origins, profile)
    value = {
        "artifact_kind": PROFILE_ARTIFACT_KIND,
        "artifact_schema": PROFILE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_manifest_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "shard_index_base": 0,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_profile_overlay_memberships_bound": True,
            "all_profile_semantic_anchor_memberships_bound": True,
            "concrete_overlay_membership_bound": True,
            "formal_complete_persona_package_cap_proved": False,
            "full_profile_exact_pilot_origin_reuse_proved": profile == "full",
            "pilot_profile_single_origin_bound": profile == "pilot",
            "placement_integer_allocation_bound": False,
            "raw_or_rendered_identity_attested": False,
            "scope_assignment_present": False,
            "search_history_or_query_observation_bound": False,
        },
        "completion_scope": (
            "one-persona-pilot-or-full-rich-pre-solve-overlay-composition-with-"
            "exact-pilot-origin-reuse-no-scope-render-history-observation-or-g0"
        ),
        "dependency_direction_contract": {
            "full_profile_origin_order_is_pilot_then_full_residual": True,
            "full_profile_must_reuse_exact_pilot_origin_manifest_and_shards": True,
            "matching_source_and_semantic_profiles_are_strictly_upstream": True,
            "origin_manifests_are_strictly_upstream": True,
            "reservation_suite_and_semantic_catalog_are_directly_bound": True,
            "shard_indices_are_origin_local_and_restart_at_zero": True,
            "upstream_back_reference_allowed": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-join-not-observed-user-statistics"
        ),
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "origin_manifest_bindings": origin_bindings,
        "origin_order": [row["origin"] for row in origins],
        "persona_id": persona_id,
        "profile": profile,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "shard_descriptors": [
            copy.deepcopy(descriptor)
            for manifest in origins
            for descriptor in manifest["shard_descriptors"]
        ],
        "summary": summary,
        "target_marginals": _persona_target(persona_id, profile),
    }
    if (
        set(value) != PROFILE_TOP_LEVEL_FIELDS
        or summary["overlay_membership_row_count"]
        != value["target_marginals"]["membership_row_count"]
        or summary["content_relation_row_count"]
        != value["target_marginals"]["content_relation_cluster_count"]
        or summary["attachment_membership_row_count"]
        != value["target_marginals"]["attachment_membership_count"]
        or (profile == "full" and [row["origin"] for row in origins] != list(ORIGIN_ORDER))
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay profile manifest differs from exact composition"
        )
    _require_negative_authority(value, label="concrete overlay profile manifest")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 concrete overlay profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None
    return value


def build_concrete_overlay_membership_profile_manifest(persona_id, profile):
    value = copy.deepcopy(_canonical_profile_manifest(persona_id, profile))
    _release_upstream_caches()
    return value


def _suite_input_bindings():
    base = _base_inputs()
    return [
        _artifact_binding(
            "persona-v2-overlay-contract",
            "overlay-semantics-schema-and-target-marginals",
            base["contract"],
            canonical=overlay_contract.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-overlay-reservation-suite",
            "global-overlay-reservation-index",
            _reservation_suite_value(),
            canonical=reservation_layout.overlay_reservation_suite_bytes,
        ),
        _artifact_binding(
            "persona-v2-source-inventory-suite",
            "global-immutable-source-inventory",
            _source_suite_value(),
            canonical=source_package.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            base["catalog"],
            canonical=semantic_package.canonical_json_bytes,
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-suite",
            "global-source-owned-semantic-and-fact-membership",
            _semantic_suite_value(),
            canonical=semantic_package.canonical_json_bytes,
        ),
    ]


def _suite_summary(origins, profiles, ledgers):
    summaries = [row["summary"] for row in origins]
    additive_fields = (
        "attachment_exact_overlap_row_count",
        "attachment_host_count",
        "attachment_membership_row_count",
        "conflict_copy_row_count",
        "content_relation_row_count",
        "exact_duplicate_row_count",
        "joined_source_reference_occurrence_count",
        "near_revision_row_count",
        "overlay_membership_row_count",
        "overlay_source_reference_occurrence_count",
        "rich_row_count",
        "semantic_anchor_membership_row_count",
        "shard_body_bytes",
        "shard_count",
        "unique_joined_source_count",
        "unique_overlay_source_count",
    )
    value = {
        field: sum(summary[field] for summary in summaries)
        for field in additive_fields
    }
    value.update(
        {
            "draft_projection_body_bytes": sum(
                row["draft_membership_projection_receipt"]["body_bytes"]
                for row in origins
            ),
            "draft_projection_row_count": sum(
                row["draft_membership_projection_receipt"]["row_count"]
                for row in origins
            ),
            "maximum_origin_manifest_bytes": max(
                len(canonical_json_bytes(row)) for row in origins
            ),
            "maximum_profile_manifest_bytes": max(
                len(canonical_json_bytes(row)) for row in profiles
            ),
            "maximum_row_bytes_including_lf": max(
                summary["maximum_row_bytes_including_lf"]
                for summary in summaries
            ),
            "maximum_shard_body_bytes": max(
                descriptor["body_bytes"]
                for row in origins
                for descriptor in row["shard_descriptors"]
            ),
            "maximum_persona_current_component_bytes": max(
                row["current_component_bytes"] for row in ledgers
            ),
            "minimum_persona_headroom_bytes": min(
                row["headroom_bytes"] for row in ledgers
            ),
            "origin_manifest_count": len(origins),
            "persona_count": len(envelope.PERSONA_IDS),
            "profile_manifest_count": len(profiles),
        }
    )
    return value


def _persona_ledgers(origins, profiles):
    semantic_ledgers = {
        row["persona_id"]: row
        for row in _semantic_suite_value()[
            "persona_current_component_byte_ledgers"
        ]
    }
    contract_bytes = len(
        overlay_contract.canonical_json_bytes(_base_inputs()["contract"])
    )
    origins_by_persona = {
        persona_id: [row for row in origins if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    profiles_by_persona = {
        persona_id: [row for row in profiles if row["persona_id"] == persona_id]
        for persona_id in envelope.PERSONA_IDS
    }
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        persona_origins = origins_by_persona[persona_id]
        persona_profiles = profiles_by_persona[persona_id]
        concrete_body_bytes = sum(
            row["summary"]["shard_body_bytes"] for row in persona_origins
        )
        origin_manifest_bytes = sum(
            len(canonical_json_bytes(row)) for row in persona_origins
        )
        profile_manifest_bytes = sum(
            len(canonical_json_bytes(row)) for row in persona_profiles
        )
        semantic_current = semantic_ledgers[persona_id]["current_component_bytes"]
        current = (
            semantic_current
            + contract_bytes
            + concrete_body_bytes
            + origin_manifest_bytes
            + profile_manifest_bytes
        )
        if current > MAX_PERSONA_PACKAGE_BYTES:
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                f"current concrete overlay component exceeds 16 MiB for {persona_id}"
            )
        ledgers.append(
            {
                "concrete_origin_body_bytes": concrete_body_bytes,
                "concrete_origin_manifest_bytes": origin_manifest_bytes,
                "concrete_profile_manifest_bytes": profile_manifest_bytes,
                "current_component_bytes": current,
                "current_component_cap_satisfied": True,
                "formal_complete_persona_package_cap_proved": False,
                "headroom_bytes": MAX_PERSONA_PACKAGE_BYTES - current,
                "max_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
                "overlay_contract_bytes_conservatively_charged_in_full": contract_bytes,
                "persona_id": persona_id,
                "semantic_current_component_bytes": semantic_current,
            }
        )
    return ledgers


def _build_canonical_suite_descriptor():
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
    origin_by_key = {
        (row["persona_id"], row["origin"]): row for row in origins
    }
    profile_by_key = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    for persona_id in envelope.PERSONA_IDS:
        pilot = profile_by_key[(persona_id, "pilot")]
        full = profile_by_key[(persona_id, "full")]
        if (
            pilot["origin_manifest_bindings"] != full["origin_manifest_bindings"][:1]
            or pilot["shard_descriptors"] != full["shard_descriptors"][: len(pilot["shard_descriptors"])]
            or full["origin_manifest_bindings"][0]
            != _concrete_manifest_binding(
                "persona-v2-concrete-overlay-membership-origin-manifest",
                "immutable-concrete-overlay-origin-owner",
                origin_by_key[(persona_id, "pilot")],
                coordinate_fields=("persona_id", "origin"),
            )
        ):
            raise PersonaV2ConcreteOverlayMembershipPackageError(
                "full profile does not reuse the exact pilot origin and shards"
            )

    origin_bindings = [
        _concrete_manifest_binding(
            "persona-v2-concrete-overlay-membership-origin-manifest",
            "concrete-overlay-origin-owner",
            manifest,
            coordinate_fields=("persona_id", "origin"),
        )
        for manifest in origins
    ]
    profile_bindings = [
        _concrete_manifest_binding(
            "persona-v2-concrete-overlay-membership-profile-manifest",
            "concrete-overlay-profile-composition",
            manifest,
            coordinate_fields=("persona_id", "profile"),
        )
        for manifest in profiles
    ]
    input_bindings = _suite_input_bindings()
    ledgers = _persona_ledgers(origins, profiles)
    summary = _suite_summary(origins, profiles, ledgers)
    value = {
        "artifact_kind": SUITE_ARTIFACT_KIND,
        "artifact_schema": SUITE_ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
            "max_suite_descriptor_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "shard_index_base": 0,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_1560_conflict_pairs_bound_to_distinct_branch_profiles": True,
            "all_25560_reservation_membership_rows_joined": True,
            "all_27660_rich_rows_bound": True,
            "all_46840_unique_overlay_source_references_resolved": True,
            "all_2100_semantic_anchor_slots_joined": True,
            "all_48940_reserved_or_anchor_unique_sources_resolved": True,
            "all_40_origin_manifests_bound": True,
            "all_40_profile_manifests_bound": True,
            "concrete_overlay_membership_bound": True,
            "current_concrete_overlay_component_cap_satisfied": True,
            "formal_complete_persona_package_cap_proved": False,
            "full_profiles_exactly_reuse_pilot_origins": True,
            "placement_integer_allocation_bound": False,
            "raw_or_rendered_identity_attested": False,
            "scope_assignment_present": False,
            "search_history_or_query_observation_bound": False,
        },
        "completion_scope": (
            "all-persona-rich-pre-solve-overlay-and-semantic-anchor-memberships-"
            "with-exact-pilot-reuse-and-current-component-cap-no-scope-solution-"
            "no-render-history-search-observation-or-g0"
        ),
        "dependency_direction_contract": {
            "catalog_and_all_three_upstream_suites_are_directly_bound": True,
            "concrete_origins_and_profiles_are_strictly_upstream_of_suite": True,
            "full_profiles_compose_origins_without_regeneration": True,
            "overlay_contract_is_directly_bound_without_repinning_upstream": True,
            "suite_may_bind_future_allocation_or_execution_artifact": False,
            "upstream_back_reference_allowed": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-join-not-observed-user-statistics"
        ),
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "origin": list(ORIGIN_ORDER),
            "origin_manifests": "persona-then-origin",
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "profile_manifests": "persona-then-profile",
            "rich_rows": (
                "content-relation-order-then-cluster-then-attachment-key-then-"
                "semantic-anchor-slot-and-intent"
            ),
            "shard_index_base": 0,
            "shard_indices": "origin-local-zero-based-restart-per-origin",
        },
        "origin_manifest_bindings": origin_bindings,
        "persona_current_component_byte_ledger_contract": {
            "draft_projection_body_is_receipt_only_and_not_persisted_or_charged": True,
            "global_suite_descriptor_is_not_charged_to_each_persona": True,
            "overlay_contract_is_conservatively_charged_in_full_to_each_persona": True,
            "reservation_and_catalog_components_are_already_in_semantic_base": True,
            "reservation_component_is_not_double_charged": True,
            "semantic_suite_current_component_bytes_is_the_exact_base": True,
            "unique_concrete_origin_bodies_and_both_profile_manifests_are_charged": True,
        },
        "persona_current_component_byte_ledgers": ledgers,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "summary": summary,
    }
    required_summary = {
        "attachment_exact_overlap_row_count": 1_390,
        "attachment_host_count": 2_800,
        "attachment_membership_row_count": EXPECTED_ATTACHMENT_ROW_COUNT,
        "conflict_copy_row_count": EXPECTED_CONFLICT_PAIR_COUNT,
        "content_relation_row_count": EXPECTED_CONTENT_RELATION_ROW_COUNT,
        "draft_projection_row_count": EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT,
        "exact_duplicate_row_count": 5_080,
        "joined_source_reference_occurrence_count": 53_220,
        "near_revision_row_count": 13_230,
        "origin_manifest_count": EXPECTED_ORIGIN_COUNT,
        "overlay_membership_row_count": EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT,
        "overlay_source_reference_occurrence_count": 51_120,
        "persona_count": 20,
        "profile_manifest_count": EXPECTED_PROFILE_COUNT,
        "rich_row_count": EXPECTED_RICH_ROW_COUNT,
        "semantic_anchor_membership_row_count": EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT,
        "shard_count": EXPECTED_SHARD_COUNT,
        "unique_joined_source_count": EXPECTED_UNIQUE_JOINED_SOURCE_COUNT,
        "unique_overlay_source_count": EXPECTED_UNIQUE_OVERLAY_SOURCE_COUNT,
    }
    if (
        set(value) != SUITE_TOP_LEVEL_FIELDS
        or any(summary.get(key) != expected for key, expected in required_summary.items())
    ):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay suite exact coverage drifted"
        )
    _require_negative_authority(value, label="concrete overlay suite")
    try:
        artifact_common.canonical_json_bytes(
            value,
            label="persona v2 concrete overlay membership suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None
    return value


def _release_upstream_caches():
    for module, names in (
        (
            reservation_layout,
            ("_canonical_origin", "_intent_slot_tuples_by_variant"),
        ),
        (semantic_package, ("_origin_plan",)),
        (
            source_package,
            (
                "_canonical_shard_descriptor",
                "_canonical_origin_manifest",
                "_canonical_profile_manifest",
            ),
        ),
    ):
        for name in names:
            clear = getattr(getattr(module, name, None), "cache_clear", None)
            if callable(clear):
                clear()
    _origin_projection.cache_clear()
    _origin_shards.cache_clear()
    gc.collect()


@functools.lru_cache(maxsize=1)
def _canonical_suite_descriptor():
    try:
        return _build_canonical_suite_descriptor()
    finally:
        _release_upstream_caches()


def build_concrete_overlay_membership_suite_descriptor():
    return copy.deepcopy(_canonical_suite_descriptor())


def canonical_json_bytes(value):
    if type(value) is not dict:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay manifest must be an object"
        )
    schema = value.get("artifact_schema")
    if schema == ORIGIN_ARTIFACT_SCHEMA:
        label = "persona v2 concrete overlay origin manifest"
        cap = MAX_ORIGIN_MANIFEST_BYTES
    elif schema == PROFILE_ARTIFACT_SCHEMA:
        label = "persona v2 concrete overlay profile manifest"
        cap = MAX_PROFILE_MANIFEST_BYTES
    elif schema == SUITE_ARTIFACT_SCHEMA:
        label = "persona v2 concrete overlay membership suite"
        cap = MAX_SUITE_DESCRIPTOR_BYTES
    else:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            f"unknown concrete overlay artifact schema: {schema!r}"
        )
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=cap
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None


def validate_concrete_overlay_membership_shard_descriptor(
    persona_id, origin, shard_index, value
):
    expected = build_concrete_overlay_membership_shard_descriptor(
        persona_id, origin, shard_index
    )
    try:
        actual_raw = artifact_common.canonical_json_bytes(
            value,
            label="persona v2 concrete overlay shard descriptor",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        expected_raw = artifact_common.canonical_json_bytes(
            expected,
            label="persona v2 concrete overlay shard descriptor",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2ConcreteOverlayMembershipPackageError(str(error)) from None
    if actual_raw != expected_raw:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay shard descriptor differs from exact regeneration"
        )
    return True


def validate_concrete_overlay_membership_shard_body(
    persona_id, origin, shard_index, value
):
    if type(value) is not bytes:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay shard body must be exact bytes"
        )
    expected = concrete_overlay_membership_shard_body_bytes(
        persona_id, origin, shard_index
    )
    if value != expected:
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay shard body differs from exact regeneration"
        )
    return True


def concrete_overlay_membership_shard_body_sha256(
    persona_id, origin, shard_index, value=None
):
    if value is None:
        value = concrete_overlay_membership_shard_body_bytes(
            persona_id, origin, shard_index
        )
    validate_concrete_overlay_membership_shard_body(
        persona_id, origin, shard_index, value
    )
    return _sha256(value)


def validate_concrete_overlay_membership_origin_manifest(
    persona_id, origin, value
):
    expected = build_concrete_overlay_membership_origin_manifest(
        persona_id, origin
    )
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay origin manifest differs from exact regeneration"
        )
    return True


def validate_concrete_overlay_membership_profile_manifest(
    persona_id, profile, value
):
    expected = build_concrete_overlay_membership_profile_manifest(
        persona_id, profile
    )
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay profile manifest differs from exact regeneration"
        )
    return True


def validate_concrete_overlay_membership_suite_descriptor(value):
    expected = build_concrete_overlay_membership_suite_descriptor()
    if canonical_json_bytes(value) != canonical_json_bytes(expected):
        raise PersonaV2ConcreteOverlayMembershipPackageError(
            "concrete overlay suite differs from exact regeneration"
        )
    return True


def concrete_overlay_membership_origin_manifest_sha256(
    persona_id, origin, value=None
):
    if value is None:
        value = build_concrete_overlay_membership_origin_manifest(
            persona_id, origin
        )
    validate_concrete_overlay_membership_origin_manifest(
        persona_id, origin, value
    )
    return _sha256(canonical_json_bytes(value))


def concrete_overlay_membership_profile_manifest_sha256(
    persona_id, profile, value=None
):
    if value is None:
        value = build_concrete_overlay_membership_profile_manifest(
            persona_id, profile
        )
    validate_concrete_overlay_membership_profile_manifest(
        persona_id, profile, value
    )
    return _sha256(canonical_json_bytes(value))


def concrete_overlay_membership_suite_descriptor_sha256(value=None):
    if value is None:
        value = build_concrete_overlay_membership_suite_descriptor()
    validate_concrete_overlay_membership_suite_descriptor(value)
    return _sha256(canonical_json_bytes(value))


def require_complete_concrete_overlay_membership_package():
    raise PersonaV2ConcreteOverlayMembershipPackageError(
        "all 25,560 reserved overlay memberships and 2,100 semantic anchors "
        "are joined to exact source-owned fact profiles, but formal recipes, "
        "scope placement, semantic namespace/query/history mappings, rendering, "
        "writing, observed search/chunks, complete package-cap proof, execution, "
        "and G0 authority remain absent"
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "ATTACHMENT_ROW_FIELDS",
    "AUTHORITY_FIELDS",
    "CONTENT_RELATION_ROW_FIELDS",
    "DRAFT_PROJECTION_RECEIPT_FIELDS",
    "EXPECTED_ATTACHMENT_ROW_COUNT",
    "EXPECTED_CONFLICT_PAIR_COUNT",
    "EXPECTED_CONTENT_RELATION_ROW_COUNT",
    "EXPECTED_ORIGIN_COUNT",
    "EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT",
    "EXPECTED_PROFILE_COUNT",
    "EXPECTED_RICH_ROW_COUNT",
    "EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT",
    "EXPECTED_SHARD_COUNT",
    "EXPECTED_UNIQUE_JOINED_SOURCE_COUNT",
    "EXPECTED_UNIQUE_OVERLAY_SOURCE_COUNT",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_PERSONA_PACKAGE_BYTES",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_ROWS_PER_SHARD",
    "MAX_ROW_BYTES_INCLUDING_LF",
    "MAX_SHARD_BODY_BYTES",
    "MAX_SUITE_DESCRIPTOR_BYTES",
    "ORIGIN_ARTIFACT_KIND",
    "ORIGIN_ARTIFACT_SCHEMA",
    "ORIGIN_ORDER",
    "ORIGIN_TOP_LEVEL_FIELDS",
    "PROFILE_ARTIFACT_KIND",
    "PROFILE_ARTIFACT_SCHEMA",
    "PROFILE_ORDER",
    "PROFILE_TOP_LEVEL_FIELDS",
    "PersonaV2ConcreteOverlayMembershipPackageError",
    "SEMANTIC_ANCHOR_ROW_FIELDS",
    "SHARD_DESCRIPTOR_FIELDS",
    "RELATION_ORDER",
    "REMAINING_BLOCKERS",
    "SUITE_ARTIFACT_KIND",
    "SUITE_ARTIFACT_SCHEMA",
    "SUITE_TOP_LEVEL_FIELDS",
    "build_concrete_overlay_membership_origin_manifest",
    "build_concrete_overlay_membership_profile_manifest",
    "build_concrete_overlay_membership_shard_descriptor",
    "build_concrete_overlay_membership_suite_descriptor",
    "canonical_json_bytes",
    "concrete_overlay_membership_origin_manifest_sha256",
    "concrete_overlay_membership_profile_manifest_sha256",
    "concrete_overlay_membership_shard_body_bytes",
    "concrete_overlay_membership_shard_body_sha256",
    "concrete_overlay_membership_suite_descriptor_sha256",
    "iter_concrete_overlay_membership_origin_rows",
    "require_complete_concrete_overlay_membership_package",
    "validate_concrete_overlay_membership_origin_manifest",
    "validate_concrete_overlay_membership_profile_manifest",
    "validate_concrete_overlay_membership_shard_body",
    "validate_concrete_overlay_membership_shard_descriptor",
    "validate_concrete_overlay_membership_suite_descriptor",
]
