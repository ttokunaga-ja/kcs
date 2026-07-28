"""Non-authorizing physical lane-path compositor for persona-PC v2.

The historical lane catalogs intentionally use logical roots such as
``formal-root/devices/{persona_id}/home`` and
``robustness-root/devices/{persona_id}/ambient-home``.  Those strings are not
writer paths.  This compact candidate joins the exact persona role slugs from
the v2 envelope to three fresh replay containers and plans one physical device
root per persona and replay.

The concrete designated replay for the ambient and byte-stress lanes is not a
frozen G0 decision.  ``formal-replay-01`` is therefore recorded only as an
unratified candidate.  No filesystem, registry, history, KIO, capacity, or G0
authority is granted by this artifact.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import re
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_device_lane_compositor_validator as independent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_device_lane_compositor_validator as independent


ARTIFACT_SCHEMA = "kio.persona.pc-device-lane-compositor/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-non-authorizing-device-lane-compositor-candidate"
BODY_FRAMING = "canonical-json"

MAX_COMPOSITOR_BYTES = 512 * 2**10
TARGET_COMPOSITOR_BYTES = 256 * 2**10
MAX_PERSONA_COUNT = 20
MAX_REPLAY_COUNT = 3
MAX_FORMAL_MAPPING_COUNT = 60
MAX_EXPANDED_NODE_COUNT = 100_000

# Frozen after two isolated, independently validated builds under distinct
# Python hash seeds.
EXPECTED_CANONICAL_BYTES = 41_099
EXPECTED_SHA256 = (
    "eb1a82d631b810ca96d90c84f9324263b4bb1018f0cde2a8339037a183d35bdf"
)

ENVELOPE_CANONICAL_BYTES = 71_979
ENVELOPE_SHA256 = (
    "12a5f175cbcd9b1ea9886c8a8e3b673b857f6b314ba48c9b71e6b279150244a7"
)

REPLAY_IDS = (
    "formal-replay-01",
    "formal-replay-02",
    "formal-replay-03",
)
DESIGNATED_REPLAY_CANDIDATE_ID = "formal-replay-01"
DESIGNATED_LANE_IDS = (
    "recursive-robustness-v1",
    "byte-stress-v1",
)

ROLE_SLUG_ALGORITHM_ID = "strict-ascii-lower-hyphen-role-v1"
PORTABLE_ROLE_RE = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*\Z")

AUTHORITY_FIELDS = (
    "actual_chunks_attested",
    "actual_lane_isolation_attested",
    "authorizes_filesystem_materialization",
    "authorizes_g0_freeze",
    "authorizes_history_execution",
    "authorizes_kio_execution",
    "authorizes_physical_write",
    "authorizes_registry_creation",
    "designated_replay_selection_authoritative",
    "filesystem_readback_receipt_bound",
    "physical_path_authority",
    "writer_available",
)

REMAINING_BLOCKERS = (
    "designated-ambient-and-byte-stress-replay-not-selected-by-g0",
    "device-lane-compositor-not-bound-by-production-g0-root",
    "filesystem-writer-and-root-bound-capacity-gate-missing",
    "physical-lane-isolation-and-shared-inode-readback-missing",
    "persona-device-materialization-receipts-missing",
)


class PersonaV2DeviceLaneCompositorError(ValueError):
    """Raised when a compositor candidate drifts or gains authority."""


def _fail(message):
    raise PersonaV2DeviceLaneCompositorError(message)


def portable_role_slug(role):
    """Derive the portable path slug without lossy transliteration."""

    if type(role) is not str or unicodedata.normalize("NFC", role) != role:
        _fail("persona role must be one NFC string")
    try:
        encoded = role.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("persona role is not ASCII portable")
    if len(encoded) > 80 or PORTABLE_ROLE_RE.fullmatch(role) is None:
        _fail("persona role is not a portable strict role slug")
    return role


def _canonical(value, *, label="persona v2 device-lane compositor"):
    try:
        independent.preflight_device_lane_compositor_value(value)
        raw = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=MAX_COMPOSITOR_BYTES,
        )
    except independent.PersonaV2DeviceLaneCompositorValidationError as error:
        _fail(str(error))
    except RecursionError:
        _fail(f"{label} exceeds the recursive canonicalization bound")
    except (UnicodeEncodeError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))
    if (
        independent.EXPECTED_CANONICAL_BYTES != EXPECTED_CANONICAL_BYTES
        or independent.EXPECTED_SHA256 != EXPECTED_SHA256
    ):
        _fail("producer and independent compositor golden constants differ")
    if len(raw) != EXPECTED_CANONICAL_BYTES:
        _fail("device-lane compositor canonical byte length drifted")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256):
        _fail("device-lane compositor SHA-256 drifted")
    return raw


def _snapshot_envelope(envelope_value=None):
    live = envelope.build_envelope_contract() if envelope_value is None else envelope_value
    try:
        independent.preflight_device_lane_compositor_value(live)
    except independent.PersonaV2DeviceLaneCompositorValidationError as error:
        _fail(str(error))
    try:
        opening = envelope.canonical_json_bytes(live)
        snapshot = copy.deepcopy(live)
        detached = envelope.canonical_json_bytes(snapshot)
        middle = envelope.canonical_json_bytes(live)
        if opening != detached or middle != opening:
            _fail("persona envelope mutated during opening snapshot")
        envelope.validate_envelope_contract(snapshot)
        closing = envelope.canonical_json_bytes(live)
    except PersonaV2DeviceLaneCompositorError:
        raise
    except Exception as error:
        _fail(f"persona envelope validation failed: {type(error).__name__}")
    if closing != opening:
        _fail("persona envelope mutated during validation")
    if len(detached) != ENVELOPE_CANONICAL_BYTES:
        _fail("persona envelope canonical byte pin drifted")
    if hashlib.sha256(detached).hexdigest() != ENVELOPE_SHA256:
        _fail("persona envelope SHA-256 pin drifted")
    return snapshot, detached


def _dependency_pin(envelope_value, raw):
    return {
        "artifact_kind": envelope_value["artifact_kind"],
        "artifact_schema": envelope_value["artifact_schema"],
        "artifact_schema_version": envelope_value["artifact_schema_version"],
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "dependency_id": "persona-envelope-v2",
        "fixture_id": envelope_value["fixture_id"],
        "fixture_schema_version": envelope_value["fixture_schema_version"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _formal_mapping(replay_id, persona_id, role_slug):
    device_root = f"{replay_id}/devices/{persona_id}-{role_slug}"
    return {
        "device_root": device_root,
        "formal_scope_count": 20,
        "fresh_w0_build_required": True,
        "home_root": f"{device_root}/home",
        "physical_materialization_claimed": False,
        "registry_root": f"{device_root}/.kio-eval-device",
        "replay_id": replay_id,
    }


def _designated_mapping(persona_id, role_slug):
    replay_id = DESIGNATED_REPLAY_CANDIDATE_ID
    device_root = f"{replay_id}/devices/{persona_id}-{role_slug}"
    return {
        "ambient_home_root": f"{device_root}/ambient-home",
        "byte_stress_root": f"{device_root}/byte-stress",
        "candidate_selection_authoritative": False,
        "device_root": device_root,
        "historical_template_path_imported": False,
        "physical_materialization_claimed": False,
        "replay_id": replay_id,
    }


def _build_value(envelope_value):
    personas = []
    for ordinal, persona_id in enumerate(envelope.PERSONA_IDS, start=1):
        source = next(
            row for row in envelope_value["personas"] if row["persona_id"] == persona_id
        )
        role = source["role"]
        role_slug = portable_role_slug(role)
        personas.append(
            {
                "designated_lane_candidate_mapping": _designated_mapping(
                    persona_id, role_slug
                ),
                "formal_replay_mappings": [
                    _formal_mapping(replay_id, persona_id, role_slug)
                    for replay_id in REPLAY_IDS
                ],
                "full_w0_source_files_per_replay": source["full_raw_files"],
                "logical_persona_ordinal": ordinal,
                "persona_id": persona_id,
                "planned_current_contract_chunks_per_physical_root": 120_000,
                "planned_w5_final_current_plus_history_contract_chunks_per_physical_root": 180_000,
                "role": role,
                "role_slug": role_slug,
            }
        )

    envelope_raw = envelope.canonical_json_bytes(envelope_value)
    suite_files_per_replay = sum(
        row["full_w0_source_files_per_replay"] for row in personas
    )
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in AUTHORITY_FIELDS},
        "canonical_limits": {
            "direct_dependency_bodies_embedded": False,
            "framed_byte_cap_before_body_required": True,
            "max_compositor_bytes": MAX_COMPOSITOR_BYTES,
            "max_expanded_node_count": MAX_EXPANDED_NODE_COUNT,
            "max_formal_mapping_count": MAX_FORMAL_MAPPING_COUNT,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_persona_count": MAX_PERSONA_COUNT,
            "max_replay_count": MAX_REPLAY_COUNT,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "target_compositor_bytes": TARGET_COMPOSITOR_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_20_logical_personas_mapped": True,
            "all_60_isolated_registries_planned": True,
            "all_60_physical_device_roots_planned": True,
            "all_1200_formal_scopes_planned": True,
            "designated_lane_candidate_mapped": True,
            "designated_lane_replay_selected_by_g0": False,
            "filesystem_materialized": False,
            "g0_eligible": False,
            "physical_isolation_readback_complete": False,
            "production_device_lane_composition_complete": False,
        },
        "dependency_pin": _dependency_pin(envelope_value, envelope_raw),
        "designated_lane_replay_candidate": {
            "applies_to_lane_ids": list(DESIGNATED_LANE_IDS),
            "candidate_replay_id": DESIGNATED_REPLAY_CANDIDATE_ID,
            "candidate_selection_basis": "proposal-example-only-not-g0-authority",
            "candidate_status": "unratified",
            "same_persona_device_root_required": True,
            "selected_by_g0": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "historical_lane_templates": {
            "coordinate_semantics": "logical-lane-plan-only",
            "direct_writer_input_allowed": False,
            "historical_roots_may_be_created": False,
            "physical_path_authority": False,
            "replacement_physical_template": (
                "{replay}/devices/{persona_id}-{role_slug}/{lane_child}"
            ),
            "templates": [
                {
                    "historical_template": "formal-root/devices/{persona_id}/home",
                    "lane_id": "formal-retrieval-history-v2",
                },
                {
                    "historical_template": (
                        "robustness-root/devices/{persona_id}/ambient-home"
                    ),
                    "lane_id": "recursive-robustness-v1",
                },
            ],
        },
        "hypothesis_status": "deterministic-path-plan-candidate-not-observation",
        "orders": {
            "designated_lane_ids": list(DESIGNATED_LANE_IDS),
            "personas": list(envelope.PERSONA_IDS),
            "replays": list(REPLAY_IDS),
        },
        "personas": personas,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "role_slug_contract": {
            "algorithm_id": ROLE_SLUG_ALGORITHM_ID,
            "collision_allowed": False,
            "derivation_is_lossless_for_current_roles": True,
            "maximum_ascii_bytes": 80,
            "pattern": "[a-z][a-z0-9]*(?:-[a-z0-9]+)*",
        },
        "safety_contract": {
            "completed_root_copy_allowed": False,
            "cross_boundary_file_copy_allowed": False,
            "cross_lane_payload_materialization_sharing_allowed": False,
            "cross_persona_payload_materialization_sharing_allowed": False,
            "cross_replay_payload_materialization_sharing_allowed": False,
            "filesystem_clone_allowed": False,
            "fresh_w0_build_required_for_every_formal_replay": True,
            "hard_link_allowed": False,
            "lane_pooling_allowed": False,
            "persona_pooling_allowed": False,
            "payload_materialization_reuse_allowed": False,
            "replay_pooling_allowed": False,
            "shared_inode_allowed": False,
            "symlink_allowed": False,
        },
        "summary": {
            "designated_ambient_home_roots_planned": 20,
            "designated_byte_stress_roots_planned": 20,
            "formal_current_contract_chunks_three_replays": 7_200_000,
            "formal_scope_count_per_device_root": 20,
            "formal_scope_count_three_replays": 1_200,
            "full_w0_source_files_per_replay": suite_files_per_replay,
            "full_w0_source_files_three_replays": suite_files_per_replay * 3,
            "isolated_registry_count_three_replays": 60,
            "logical_persona_count": 20,
            "physical_device_root_count_per_replay": 20,
            "physical_device_root_count_three_replays": 60,
            "planned_current_contract_chunks_per_device_root": 120_000,
            "planned_w5_final_current_plus_history_contract_chunks_per_device_root": 180_000,
            "planned_w5_final_current_plus_history_contract_chunks_three_replays": 10_800_000,
            "replay_count": 3,
        },
    }


def build_device_lane_compositor(envelope_value=None):
    """Build and independently validate a detached compositor candidate."""

    envelope_snapshot, _ = _snapshot_envelope(envelope_value)
    value = _build_value(envelope_snapshot)
    _canonical(value, label="built device-lane compositor")
    try:
        result = independent.validate_device_lane_compositor(
            value,
            envelope_value=envelope_snapshot,
        )
    except independent.PersonaV2DeviceLaneCompositorValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent validator did not return exact success")
    return copy.deepcopy(value)


def canonical_json_bytes(value):
    return _canonical(value)


def validate_device_lane_compositor(value, *, envelope_value=None):
    opening = _canonical(value, label="producer opening device-lane compositor")
    try:
        result = independent.validate_device_lane_compositor(
            value,
            envelope_value=envelope_value,
        )
    except independent.PersonaV2DeviceLaneCompositorValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent validator did not return exact success")
    closing = _canonical(value, label="producer closing device-lane compositor")
    if not hmac.compare_digest(opening, closing):
        _fail("device-lane compositor changed during producer validation")
    return True


def device_lane_compositor_sha256(value=None, *, envelope_value=None):
    if value is None:
        value = build_device_lane_compositor(envelope_value=envelope_value)
    opening = _canonical(value, label="caller device-lane compositor")
    snapshot = copy.deepcopy(value)
    snapshot_raw = _canonical(snapshot, label="detached device-lane compositor")
    middle = _canonical(value, label="caller device-lane compositor reauthentication")
    if opening != snapshot_raw or middle != opening:
        _fail("device-lane compositor mutated during opening snapshot")
    validate_device_lane_compositor(snapshot, envelope_value=envelope_value)
    closing = _canonical(value, label="caller device-lane compositor closing reauthentication")
    if closing != opening:
        _fail("device-lane compositor mutated during validation")
    return hashlib.sha256(snapshot_raw).hexdigest()


def require_authorized_device_lane_compositor():
    _fail(
        "device-lane compositor is non-authorizing: designated replay, writer, "
        "capacity, isolation readback, and production G0 binding remain missing"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "DESIGNATED_REPLAY_CANDIDATE_ID",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_COMPOSITOR_BYTES",
    "PersonaV2DeviceLaneCompositorError",
    "REPLAY_IDS",
    "build_device_lane_compositor",
    "canonical_json_bytes",
    "device_lane_compositor_sha256",
    "portable_role_slug",
    "require_authorized_device_lane_compositor",
    "validate_device_lane_compositor",
]
