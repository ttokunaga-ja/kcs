"""Producer-independent validator for the persona-PC v2 lane compositor.

The validator embeds the exact twenty persona/role/file-count rows and
regenerates all sixty formal device roots itself.  It never imports the target
producer.  A supplied persona envelope is authenticated, detached, and checked
again on return so mutable caller-owned inputs cannot silently change the role
or path domain during validation.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import re
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope


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
MAX_CONTAINER_ITEMS = 4_096
MAX_PREFLIGHT_EXPANDED_BYTES = 2 * MAX_COMPOSITOR_BYTES

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

PERSONA_ROWS = (
    ("p01", "software-engineer", 12_000),
    ("p02", "site-reliability-engineer", 15_000),
    ("p03", "security-grc-analyst", 10_000),
    ("p04", "ml-research-engineer", 10_000),
    ("p05", "bi-data-analyst", 12_000),
    ("p06", "life-science-researcher", 8_000),
    ("p07", "humanities-researcher", 7_000),
    ("p08", "product-manager", 8_000),
    ("p09", "ux-researcher", 9_000),
    ("p10", "management-consultant", 11_000),
    ("p11", "account-executive", 10_000),
    ("p12", "support-success-lead", 16_000),
    ("p13", "corporate-privacy-counsel", 7_000),
    ("p14", "finance-controller", 13_000),
    ("p15", "recruiter-people-ops", 8_000),
    ("p16", "clinical-researcher", 8_000),
    ("p17", "construction-project-manager", 8_000),
    ("p18", "manufacturing-quality-engineer", 12_000),
    ("p19", "educator-instructional-designer", 9_000),
    ("p20", "investigative-journalist", 10_000),
)
PERSONA_IDS = tuple(row[0] for row in PERSONA_ROWS)

AUTHORITY_FIELDS = frozenset(
    {
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
    }
)
REMAINING_BLOCKERS = (
    "designated-ambient-and-byte-stress-replay-not-selected-by-g0",
    "device-lane-compositor-not-bound-by-production-g0-root",
    "filesystem-writer-and-root-bound-capacity-gate-missing",
    "physical-lane-isolation-and-shared-inode-readback-missing",
    "persona-device-materialization-receipts-missing",
)

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "dependency_pin",
        "designated_lane_replay_candidate",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "historical_lane_templates",
        "hypothesis_status",
        "orders",
        "personas",
        "remaining_blockers",
        "role_slug_contract",
        "safety_contract",
        "summary",
    }
)
PERSONA_FIELDS = frozenset(
    {
        "designated_lane_candidate_mapping",
        "formal_replay_mappings",
        "full_w0_source_files_per_replay",
        "logical_persona_ordinal",
        "persona_id",
        "planned_current_contract_chunks_per_physical_root",
        "planned_w5_final_current_plus_history_contract_chunks_per_physical_root",
        "role",
        "role_slug",
    }
)
FORMAL_MAPPING_FIELDS = frozenset(
    {
        "device_root",
        "formal_scope_count",
        "fresh_w0_build_required",
        "home_root",
        "physical_materialization_claimed",
        "registry_root",
        "replay_id",
    }
)
DESIGNATED_MAPPING_FIELDS = frozenset(
    {
        "ambient_home_root",
        "byte_stress_root",
        "candidate_selection_authoritative",
        "device_root",
        "historical_template_path_imported",
        "physical_materialization_claimed",
        "replay_id",
    }
)


class PersonaV2DeviceLaneCompositorValidationError(ValueError):
    """Raised when a compositor candidate fails independent validation."""


def _fail(message):
    raise PersonaV2DeviceLaneCompositorValidationError(message)


def _exact_dict(value, fields, label):
    if type(value) is not dict or frozenset(value) != frozenset(fields):
        _fail(f"{label} fields differ from the exact schema")


def _portable_role_slug(role):
    if type(role) is not str or unicodedata.normalize("NFC", role) != role:
        _fail("persona role must be one NFC string")
    try:
        encoded = role.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("persona role is not ASCII portable")
    if len(encoded) > 80 or PORTABLE_ROLE_RE.fullmatch(role) is None:
        _fail("persona role is not a portable strict role slug")
    return role


def _preflight(value):
    """Bound shared-reference expansion before recursive canonicalization."""

    stack = [(value, 0)]
    nodes = 0
    expanded_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_EXPANDED_NODE_COUNT:
            _fail("compositor exceeds the expanded node budget")
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail("compositor exceeds the nesting budget")
        if type(item) is dict:
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail("compositor object exceeds the item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            for key, child in item.items():
                if type(key) is not str:
                    _fail("compositor object keys must be strings")
                try:
                    key_bytes = key.encode("utf-8", "strict")
                except UnicodeEncodeError:
                    _fail("compositor object key is not valid UTF-8")
                expanded_bytes += 6 * len(key_bytes) + 3
                stack.append((child, depth + 1))
        elif type(item) is list:
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail("compositor list exceeds the item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            try:
                raw = item.encode("utf-8", "strict")
            except UnicodeEncodeError:
                _fail("compositor string is not valid UTF-8")
            expanded_bytes += 6 * len(raw) + 2
        elif type(item) is bool:
            expanded_bytes += 5
        elif type(item) is int and type(item) is not bool:
            if item < 0 or item > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail("compositor integer is outside the bounded range")
            expanded_bytes += 40
        else:
            _fail("compositor contains a non-canonical value type")
        if expanded_bytes > MAX_PREFLIGHT_EXPANDED_BYTES:
            _fail("compositor exceeds the expanded byte budget")


def preflight_device_lane_compositor_value(value):
    """Apply the non-recursive expanded-value budget without canonicalizing."""

    _preflight(value)
    return True


def _canonical(value, *, label):
    _preflight(value)
    try:
        raw = artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=MAX_COMPOSITOR_BYTES,
        )
    except RecursionError:
        _fail(f"{label} exceeds the recursive canonicalization bound")
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    if len(raw) != EXPECTED_CANONICAL_BYTES:
        _fail("device-lane compositor canonical byte length drifted")
    if not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), EXPECTED_SHA256):
        _fail("device-lane compositor SHA-256 drifted")
    return raw


def _snapshot_envelope(envelope_value=None):
    live = envelope.build_envelope_contract() if envelope_value is None else envelope_value
    _preflight(live)
    try:
        opening = envelope.canonical_json_bytes(live)
        snapshot = copy.deepcopy(live)
        detached = envelope.canonical_json_bytes(snapshot)
        middle = envelope.canonical_json_bytes(live)
        if opening != detached or middle != opening:
            _fail("persona envelope mutated during opening snapshot")
        envelope.validate_envelope_contract(snapshot)
        closing = envelope.canonical_json_bytes(live)
    except PersonaV2DeviceLaneCompositorValidationError:
        raise
    except Exception as error:
        _fail(f"persona envelope validation failed: {type(error).__name__}")
    if closing != opening:
        _fail("persona envelope mutated during validation")
    if len(detached) != ENVELOPE_CANONICAL_BYTES:
        _fail("persona envelope canonical byte pin drifted")
    if hashlib.sha256(detached).hexdigest() != ENVELOPE_SHA256:
        _fail("persona envelope SHA-256 pin drifted")

    rows = snapshot.get("personas")
    if type(rows) is not list or len(rows) != len(PERSONA_ROWS):
        _fail("persona envelope does not contain the exact twenty rows")
    observed = tuple(
        (row.get("persona_id"), row.get("role"), row.get("full_raw_files"))
        for row in rows
        if type(row) is dict
    )
    if observed != PERSONA_ROWS:
        _fail("persona envelope role or W0 file rows drifted")
    if tuple(envelope.PERSONA_IDS) != PERSONA_IDS:
        _fail("persona envelope exported ID order drifted")
    return snapshot, detached, live, opening


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


def _expected_value(envelope_value, envelope_raw):
    personas = []
    for ordinal, (persona_id, role, source_files) in enumerate(PERSONA_ROWS, start=1):
        role_slug = _portable_role_slug(role)
        personas.append(
            {
                "designated_lane_candidate_mapping": _designated_mapping(
                    persona_id, role_slug
                ),
                "formal_replay_mappings": [
                    _formal_mapping(replay_id, persona_id, role_slug)
                    for replay_id in REPLAY_IDS
                ],
                "full_w0_source_files_per_replay": source_files,
                "logical_persona_ordinal": ordinal,
                "persona_id": persona_id,
                "planned_current_contract_chunks_per_physical_root": 120_000,
                "planned_w5_final_current_plus_history_contract_chunks_per_physical_root": 180_000,
                "role": role,
                "role_slug": role_slug,
            }
        )

    suite_files_per_replay = sum(row[2] for row in PERSONA_ROWS)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
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
            "personas": list(PERSONA_IDS),
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


def _safe_relative_path(path, label):
    if type(path) is not str or not path or path.startswith(("/", "\\")):
        _fail(f"{label} must be a non-empty relative path")
    if "\\" in path or "\x00" in path:
        _fail(f"{label} contains a forbidden path character")
    parts = path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _fail(f"{label} contains an unsafe path component")
    if unicodedata.normalize("NFC", path) != path:
        _fail(f"{label} must be NFC")
    return tuple(parts)


def _validate_semantics(value):
    _exact_dict(value, TOP_LEVEL_FIELDS, "device-lane compositor")
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or type(value["artifact_schema_version"]) is not int
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != envelope.FIXTURE_ID
        or type(value["fixture_schema_version"]) is not int
        or value["fixture_schema_version"] != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("device-lane compositor identity drifted")
    _exact_dict(value["authority"], AUTHORITY_FIELDS, "authority")
    if any(flag is not False for flag in value["authority"].values()):
        _fail("device-lane compositor authority must remain exactly false")
    if value["g0_contract_frozen"] is not False:
        _fail("device-lane compositor cannot freeze G0")

    historical = value["historical_lane_templates"]
    if (
        type(historical) is not dict
        or historical.get("physical_path_authority") is not False
        or historical.get("direct_writer_input_allowed") is not False
        or historical.get("historical_roots_may_be_created") is not False
    ):
        _fail("historical lane templates gained physical authority")
    candidate = value["designated_lane_replay_candidate"]
    if (
        type(candidate) is not dict
        or candidate.get("candidate_replay_id") != DESIGNATED_REPLAY_CANDIDATE_ID
        or candidate.get("candidate_status") != "unratified"
        or candidate.get("selected_by_g0") is not False
    ):
        _fail("designated lane replay candidate gained selection authority")

    personas = value["personas"]
    if type(personas) is not list or len(personas) != MAX_PERSONA_COUNT:
        _fail("compositor must contain exactly twenty persona rows")
    if [row.get("persona_id") for row in personas if type(row) is dict] != list(
        PERSONA_IDS
    ):
        _fail("persona rows are missing or reordered")

    device_roots = []
    home_roots = []
    registry_roots = []
    ambient_roots = []
    stress_roots = []
    for ordinal, (row, expected) in enumerate(zip(personas, PERSONA_ROWS), start=1):
        _exact_dict(row, PERSONA_FIELDS, "persona row")
        persona_id, role, source_files = expected
        if (
            row["persona_id"] != persona_id
            or row["role"] != role
            or row["role_slug"] != _portable_role_slug(role)
            or type(row["logical_persona_ordinal"]) is not int
            or row["logical_persona_ordinal"] != ordinal
            or type(row["full_w0_source_files_per_replay"]) is not int
            or row["full_w0_source_files_per_replay"] != source_files
            or row["planned_current_contract_chunks_per_physical_root"] != 120_000
            or row[
                "planned_w5_final_current_plus_history_contract_chunks_per_physical_root"
            ]
            != 180_000
        ):
            _fail(f"persona scalar contract drifted: {persona_id}")

        mappings = row["formal_replay_mappings"]
        if type(mappings) is not list or len(mappings) != MAX_REPLAY_COUNT:
            _fail(f"persona must map exactly three formal replays: {persona_id}")
        for mapping, replay_id in zip(mappings, REPLAY_IDS):
            _exact_dict(mapping, FORMAL_MAPPING_FIELDS, "formal replay mapping")
            expected_mapping = _formal_mapping(replay_id, persona_id, role)
            if mapping != expected_mapping:
                _fail(f"formal replay mapping drifted: {persona_id}/{replay_id}")
            for path_field in ("device_root", "home_root", "registry_root"):
                _safe_relative_path(mapping[path_field], f"{persona_id} {path_field}")
            device_roots.append(mapping["device_root"])
            home_roots.append(mapping["home_root"])
            registry_roots.append(mapping["registry_root"])

        designated = row["designated_lane_candidate_mapping"]
        _exact_dict(designated, DESIGNATED_MAPPING_FIELDS, "designated lane mapping")
        expected_designated = _designated_mapping(persona_id, role)
        if designated != expected_designated:
            _fail(f"designated lane mapping drifted: {persona_id}")
        if designated["device_root"] != mappings[0]["device_root"]:
            _fail(f"designated lanes left the persona device root: {persona_id}")
        for path_field in ("device_root", "ambient_home_root", "byte_stress_root"):
            _safe_relative_path(designated[path_field], f"{persona_id} {path_field}")
        ambient_roots.append(designated["ambient_home_root"])
        stress_roots.append(designated["byte_stress_root"])

    for label, paths, count in (
        ("device roots", device_roots, 60),
        ("home roots", home_roots, 60),
        ("registry roots", registry_roots, 60),
        ("ambient roots", ambient_roots, 20),
        ("byte-stress roots", stress_roots, 20),
    ):
        if len(paths) != count or len(set(paths)) != count:
            _fail(f"{label} are pooled or duplicated")
    all_lane_paths = home_roots + registry_roots + ambient_roots + stress_roots
    if len(all_lane_paths) != len(set(all_lane_paths)):
        _fail("formal, registry, ambient, and byte-stress paths overlap")

    safety = value["safety_contract"]
    if type(safety) is not dict:
        _fail("safety contract must be one object")
    for key, flag in safety.items():
        if key == "fresh_w0_build_required_for_every_formal_replay":
            if flag is not True:
                _fail("every formal replay must require a fresh W0 build")
        elif flag is not False:
            _fail(f"unsafe sharing permission enabled: {key}")


def validate_device_lane_compositor(value, *, envelope_value=None):
    """Validate one candidate and reauthenticate all caller-owned inputs."""

    _preflight(value)
    opening = _canonical(value, label="caller device-lane compositor")
    snapshot = copy.deepcopy(value)
    detached = _canonical(snapshot, label="detached device-lane compositor")
    middle = _canonical(value, label="caller device-lane compositor reauthentication")
    if opening != detached or middle != opening:
        _fail("device-lane compositor mutated during opening snapshot")

    envelope_snapshot, envelope_raw, envelope_live, envelope_opening = _snapshot_envelope(
        envelope_value
    )
    _validate_semantics(snapshot)
    expected = _expected_value(envelope_snapshot, envelope_raw)
    expected_raw = _canonical(expected, label="independently regenerated compositor")
    if detached != expected_raw:
        _fail("device-lane compositor differs from independent regeneration")

    closing = _canonical(value, label="caller device-lane compositor closing reauthentication")
    try:
        envelope_closing = envelope.canonical_json_bytes(envelope_live)
    except Exception as error:
        _fail(f"persona envelope closing authentication failed: {type(error).__name__}")
    if closing != opening or envelope_closing != envelope_opening:
        _fail("caller-owned compositor or envelope mutated during validation")
    return True


def strict_load_canonical_json_bytes(raw):
    """Load exact canonical UTF-8 JSON with duplicate-key rejection."""

    if type(raw) is not bytes or not raw or len(raw) > MAX_COMPOSITOR_BYTES:
        _fail("compositor body must be immutable bytes within its framed cap")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("compositor body must not contain a UTF-8 BOM")

    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                _fail("compositor body contains a duplicate object key")
            result[key] = value
        return result

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=object_pairs,
        )
    except PersonaV2DeviceLaneCompositorValidationError:
        raise
    except RecursionError:
        _fail("compositor body exceeds the JSON nesting bound")
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"compositor body is not strict UTF-8 JSON: {type(error).__name__}")
    if type(value) is not dict:
        _fail("compositor body must be one JSON object")
    canonical = _canonical(value, label="loaded device-lane compositor")
    if canonical != raw:
        _fail("compositor body is not exact canonical JSON")
    return value


def load_and_validate_device_lane_compositor(raw, *, envelope_value=None):
    value = strict_load_canonical_json_bytes(raw)
    validate_device_lane_compositor(value, envelope_value=envelope_value)
    return value


def require_authorized_device_lane_compositor(value):
    validate_device_lane_compositor(value)
    _fail(
        "device-lane compositor is a non-authorizing candidate; designated "
        "replay selection and physical readback remain unresolved"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_COMPOSITOR_BYTES",
    "PERSONA_ROWS",
    "PersonaV2DeviceLaneCompositorValidationError",
    "load_and_validate_device_lane_compositor",
    "preflight_device_lane_compositor_value",
    "require_authorized_device_lane_compositor",
    "strict_load_canonical_json_bytes",
    "validate_device_lane_compositor",
]
