"""Independent validator for the non-authorizing formal-leaf placement binding.

This module deliberately does *not* import the sibling placement-binding
producer.  It authenticates the frozen topology and device-lane compositor
twice, derives every one of the 1,200 planned formal leaf paths itself, and
then checks an external canonical JSONL body against that derivation.  The
binding is a planning receipt only: it neither creates a directory nor grants
writer, registry, history, KCS, capacity, or G0 authority.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import unicodedata

try:  # Support both package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_device_lane_compositor as compositor
    from . import persona_v2_device_lane_compositor_validator as compositor_independent
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_device_lane_compositor as compositor
    import persona_v2_device_lane_compositor_validator as compositor_independent
    import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kcs.persona.pc-formal-leaf-placement-binding/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-non-authorizing-formal-leaf-placement-binding-candidate"
ARTIFACT_ID = "persona-pc-v2-formal-leaf-placement-binding-v1"
BODY_ID = "persona-pc-v2-formal-leaf-placement-rows-v1"
BODY_FRAMING = "canonical-lf-jsonl/v1"
BODY_ENCODING = "canonical-json-per-row-utf8-nfc-lf"
ROW_SCHEMA = "kcs.persona.pc-formal-leaf-placement-row/v1"

MAX_BINDING_BYTES = 256 * 2**10
MAX_BODY_BYTES = 2 * 2**20
MAX_ROW_BYTES_INCLUDING_LF = 2_048
MAX_ROW_COUNT = 1_200
MAX_EXPANDED_NODE_COUNT = 100_000
MAX_CONTAINER_ITEMS = 4_096
MAX_PREFLIGHT_EXPANDED_BYTES = 4 * MAX_BODY_BYTES

REPLAY_IDS = (
    "formal-replay-01",
    "formal-replay-02",
    "formal-replay-03",
)
PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
SCOPES_PER_PERSONA = 20
EXPECTED_ROW_COUNT = len(REPLAY_IDS) * len(PERSONA_IDS) * SCOPES_PER_PERSONA

TOPOLOGY_PIN = (
    "kcs.persona.pc-topology/v2",
    2,
    134_195,
    "204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f",
)
COMPOSITOR_PIN = (
    "kcs.persona.pc-device-lane-compositor/v1",
    1,
    41_099,
    "eb1a82d631b810ca96d90c84f9324263b4bb1018f0cde2a8339037a183d35bdf",
)

# Frozen after matching independent producer/validator builds.  This freezes
# only the canonical planning receipt, never a filesystem or execution claim.
EXPECTED_BODY_BYTES = 889_056
EXPECTED_BODY_SHA256 = "98e7239f498c8ebff3f2c754a24036ac7c5263a2f5f6b2bb66275ceaccd8f66e"
EXPECTED_CANONICAL_BYTES = 27_117
EXPECTED_SHA256 = "de518d1fef7a6955462774ace7321943ff5ca918be7f6210380890fca78857f8"

ROW_FIELDS = frozenset(
    {
        "row_schema",
        "schema_version",
        "row_id",
        "replay_id",
        "replay_ordinal",
        "persona_id",
        "persona_ordinal",
        "scope_key",
        "scope_ordinal",
        "scope_kind",
        "functional_slot",
        "relative_path",
        "home_root",
        "registry_root",
        "leaf_root",
        "leaf_depth_from_home",
        "direct_child_only",
        "runtime_scope_id_assigned",
    }
)
DESCRIPTOR_FIELDS = frozenset(
    {
        "artifact_id",
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "body_canonical_bytes",
        "body_embedded",
        "body_encoding",
        "body_final_lf",
        "body_framing",
        "body_id",
        "body_sha256",
        "canonical_limits",
        "completion_claims",
        "dependency_bindings",
        "first_row_id",
        "first_row_lf_bytes",
        "first_row_sha256",
        "g0_contract_frozen",
        "last_row_id",
        "last_row_lf_bytes",
        "last_row_sha256",
        "maximum_lf_inclusive_row_bytes",
        "persona_order",
        "planning_digests",
        "replay_order",
        "registry_summaries",
        "row_count",
        "row_order",
        "row_schema",
        "safety_contract",
        "summary",
    }
)
AUTHORITY_FIELDS = frozenset(
    {
        "actual_filesystem_paths_attested",
        "actual_scope_registration_attested",
        "authorizes_filesystem_materialization",
        "authorizes_g0_freeze",
        "authorizes_history_execution",
        "authorizes_kcs_execution",
        "authorizes_physical_write",
        "authorizes_registry_creation",
        "authorizes_scope_registration",
        "physical_path_authority",
        "writer_available",
    }
)
COMPLETION_CLAIM_FIELDS = frozenset(
    {
        "all_1200_formal_leaf_paths_planned",
        "body_descriptor_golden_frozen",
        "filesystem_materialized",
        "g0_eligible",
        "scope_registry_created",
    }
)
SAFETY_CONTRACT_FIELDS = frozenset(
    {
        "direct_child_files_required",
        "filesystem_write_authorized",
        "hard_link_allowed",
        "nested_managed_files_allowed",
        "registry_sharing_allowed",
        "symlink_allowed",
    }
)
CANONICAL_LIMIT_FIELDS = frozenset(
    {
        "external_body_max_bytes",
        "maximum_lf_inclusive_row_bytes",
        "max_binding_bytes",
        "max_row_count",
        "unicode_normalization",
    }
)
SUMMARY_FIELDS = frozenset(
    {
        "formal_leaf_path_count_three_replays",
        "formal_scope_count_per_persona",
        "isolated_registry_count_three_replays",
        "logical_persona_count",
        "physical_device_root_count_three_replays",
        "replay_count",
    }
)
PLANNING_DIGEST_FIELDS = frozenset(
    {
        "scope_registry_sha256",
        "leaf_path_projection_sha256",
    }
)
REGISTRY_SUMMARY_FIELDS = frozenset(
    {
        "replay_id",
        "persona_id",
        "home_root",
        "registry_root",
        "entry_count",
        "registry_sha256",
        "leaf_path_sha256",
    }
)
DEPENDENCY_BINDING_FIELDS = frozenset(
    {
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "dependency_id",
        "dependency_role",
        "sha256",
    }
)

_GOLDEN_NOT_PROVIDED = object()


class PersonaV2FormalLeafPlacementBindingValidationError(ValueError):
    """Raised when a formal-leaf binding violates its closed planning contract."""


def _fail(message):
    raise PersonaV2FormalLeafPlacementBindingValidationError(message)


def _sha256(raw):
    if type(raw) is not bytes:
        _fail("SHA-256 input must be exact bytes")
    return hashlib.sha256(raw).hexdigest()


def _exact_dict(value, fields, label):
    if type(value) is not dict or frozenset(value) != frozenset(fields):
        _fail(f"{label} fields differ from the exact schema")


def _preflight(value, *, label, maximum_bytes):
    """Reject aliases/cycles and bound expansion before recursive JSON work."""

    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        _fail("preflight maximum must be one positive exact integer")
    stack = [(value, 0)]
    seen_containers = set()
    nodes = 0
    expanded_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > MAX_EXPANDED_NODE_COUNT:
            _fail(f"{label} exceeds the expanded node budget")
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail(f"{label} exceeds the nesting budget")
        if type(item) is dict:
            identity = id(item)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail(f"{label} object exceeds the item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            for key, child in item.items():
                if type(key) is not str:
                    _fail(f"{label} object keys must be strings")
                try:
                    key_raw = key.encode("utf-8", "strict")
                except UnicodeEncodeError:
                    _fail(f"{label} object key is not valid UTF-8")
                expanded_bytes += 6 * len(key_raw) + 3
                stack.append((child, depth + 1))
        elif type(item) is list:
            identity = id(item)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(item) > MAX_CONTAINER_ITEMS:
                _fail(f"{label} list exceeds the item budget")
            expanded_bytes += 2 + max(0, len(item) - 1)
            stack.extend((child, depth + 1) for child in item)
        elif type(item) is str:
            try:
                text = item.encode("utf-8", "strict")
            except UnicodeEncodeError:
                _fail(f"{label} string is not valid UTF-8")
            expanded_bytes += 6 * len(text) + 2
        elif type(item) is bool:
            expanded_bytes += 5
        elif type(item) is int:
            if item < 0 or item > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail(f"{label} integer is outside the bounded range")
            expanded_bytes += 40
        else:
            _fail(f"{label} contains a non-canonical value type")
        if expanded_bytes > min(MAX_PREFLIGHT_EXPANDED_BYTES, 8 * maximum_bytes):
            _fail(f"{label} exceeds the expanded byte budget")


def _canonical(value, *, label, maximum):
    _preflight(value, label=label, maximum_bytes=maximum)
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=maximum)
    except RecursionError:
        _fail(f"{label} exceeds the recursive canonicalization bound")
    except (UnicodeEncodeError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_float(token):
    _fail(f"floating-point token is forbidden: {token!r}")


def _reject_constant(token):
    _fail(f"non-JSON constant is forbidden: {token!r}")


def _owned_snapshot(value, *, label, maximum):
    """Canonicalize first, then parse an owned strict JSON snapshot."""

    raw = _canonical(value, label=label, maximum=maximum)
    try:
        snapshot = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2FormalLeafPlacementBindingValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} snapshot cannot be parsed: {type(error).__name__}")
    if _canonical(snapshot, label=f"{label} owned snapshot", maximum=maximum) != raw:
        _fail(f"{label} owned snapshot is not canonical")
    return snapshot, raw


def _expected_body_golden():
    bytes_set = EXPECTED_BODY_BYTES is not None
    digest_set = EXPECTED_BODY_SHA256 is not None
    if bytes_set != digest_set:
        _fail("body golden must be entirely unset or entirely set")
    if not bytes_set:
        return None
    if (
        type(EXPECTED_BODY_BYTES) is not int
        or type(EXPECTED_BODY_BYTES) is bool
        or not 1 <= EXPECTED_BODY_BYTES <= MAX_BODY_BYTES
        or type(EXPECTED_BODY_SHA256) is not str
        or len(EXPECTED_BODY_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_BODY_SHA256)
    ):
        _fail("body golden configuration is invalid")
    return EXPECTED_BODY_BYTES, EXPECTED_BODY_SHA256


# Kept as a private compatibility spelling for the sibling producer while the
# four coordinated freeze constants are still deliberately unset.
def _expected_body_pin():
    return _expected_body_golden()


def _expected_descriptor_golden():
    bytes_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if bytes_set != digest_set:
        _fail("descriptor golden must be entirely unset or entirely set")
    if not bytes_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= MAX_BINDING_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("descriptor golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def configured_descriptor_golden():
    """Return the frozen descriptor pin, or ``None`` before the freeze."""

    return _expected_descriptor_golden()


def _require_producer_golden_parity(producer_expected_golden):
    expected = _expected_descriptor_golden()
    expected_body = _expected_body_golden()
    if producer_expected_golden is _GOLDEN_NOT_PROVIDED:
        return expected
    # The sibling producer supplies the coordinated ``(body, descriptor)``
    # pair so a later four-pin freeze cannot accidentally split the two
    # receipts.  Direct validator callers may still supply descriptor-only.
    if (
        type(producer_expected_golden) is tuple
        and len(producer_expected_golden) == 2
        and producer_expected_golden[0] == expected_body
        and producer_expected_golden[1] == expected
    ):
        return expected
    # A producer may conveniently pass ``(None, None)`` while the shared
    # golden is deliberately not frozen yet.
    if expected is None and producer_expected_golden in (None, (None, None)):
        return None
    if producer_expected_golden != expected:
        _fail("producer and validator descriptor goldens differ")
    return expected


def _require_body_golden(raw):
    expected = _expected_body_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("external formal-leaf body differs from its frozen golden")


def _assert_descriptor_golden(raw):
    expected = _expected_descriptor_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("formal-leaf descriptor differs from its frozen golden")


def _authenticate_topology(value):
    snapshot, raw = _owned_snapshot(
        value,
        label="formal-leaf topology provider value",
        maximum=topology.MAX_TOPOLOGY_BYTES,
    )
    try:
        topology.validate_topology_contract(snapshot)
    except Exception as error:
        _fail(f"topology provider validation failed: {type(error).__name__}")
    if (
        snapshot.get("artifact_schema") != TOPOLOGY_PIN[0]
        or snapshot.get("artifact_schema_version") != TOPOLOGY_PIN[1]
        or len(raw) != TOPOLOGY_PIN[2]
        or not hmac.compare_digest(_sha256(raw), TOPOLOGY_PIN[3])
    ):
        _fail("topology provider differs from the exact v2 dependency pin")
    return snapshot, raw


def _authenticate_compositor(value):
    snapshot, raw = _owned_snapshot(
        value,
        label="formal-leaf device-lane compositor provider value",
        maximum=compositor.MAX_COMPOSITOR_BYTES,
    )
    try:
        compositor_independent.validate_device_lane_compositor(snapshot)
    except Exception as error:
        _fail(f"device-lane compositor provider validation failed: {type(error).__name__}")
    if (
        snapshot.get("artifact_schema") != COMPOSITOR_PIN[0]
        or snapshot.get("artifact_schema_version") != COMPOSITOR_PIN[1]
        or len(raw) != COMPOSITOR_PIN[2]
        or not hmac.compare_digest(_sha256(raw), COMPOSITOR_PIN[3])
    ):
        _fail("device-lane compositor differs from the exact v1 dependency pin")
    return snapshot, raw


def _read_provider_twice(provider, *, label, authenticate, maximum):
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    first_live = provider()
    first_snapshot, first_raw = authenticate(first_live)
    second_live = provider()
    second_snapshot, second_raw = authenticate(second_live)
    if first_raw != second_raw:
        _fail(f"{label} provider replay is nondeterministic")
    return (
        second_snapshot,
        second_raw,
        (
            (f"{label} read-1", first_live, first_raw, maximum),
            (f"{label} read-2", second_live, second_raw, maximum),
        ),
    )


def _safe_relative_path(path, *, label):
    if type(path) is not str or not path or path.startswith(("/", "\\")):
        _fail(f"{label} must be a non-empty relative path")
    if "\\" in path or "\x00" in path or unicodedata.normalize("NFC", path) != path:
        _fail(f"{label} contains unsafe or non-NFC characters")
    try:
        path.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail(f"{label} must remain portable ASCII")
    parts = path.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        _fail(f"{label} contains an unsafe path component")
    return tuple(parts)


def _topology_scopes(topology_value):
    personas = topology_value.get("personas") if type(topology_value) is dict else None
    if type(personas) is not list or len(personas) != len(PERSONA_IDS):
        _fail("topology must expose exactly twenty personas")
    result = {}
    global_relative_paths = set()
    for persona_ordinal, (persona_id, persona) in enumerate(zip(PERSONA_IDS, personas), start=1):
        if type(persona) is not dict or persona.get("persona_id") != persona_id:
            _fail("topology persona order differs from the placement contract")
        scopes = persona.get("scopes")
        if type(scopes) is not list or len(scopes) != SCOPES_PER_PERSONA:
            _fail(f"topology scope count differs: {persona_id}")
        normalized = []
        for scope_ordinal, scope in enumerate(scopes, start=1):
            if type(scope) is not dict:
                _fail("topology scope must be an object")
            scope_key = scope.get("scope_key")
            relative_path = scope.get("relative_path")
            functional_slot = scope.get("functional_slot")
            kind = scope.get("kind")
            if (
                scope_key != f"{persona_id}-scope-{scope_ordinal:02d}"
                or scope.get("ordinal") != scope_ordinal
                or kind not in {"primary", "secondary"}
                or (kind == "primary") != (scope_ordinal <= 12)
                or type(functional_slot) is not str
                or not functional_slot
            ):
                _fail(f"topology scope identity or kind drifted: {persona_id}/{scope_ordinal}")
            _safe_relative_path(relative_path, label="topology relative path")
            if relative_path.casefold() in global_relative_paths:
                _fail("topology relative scope paths are no longer globally unique")
            global_relative_paths.add(relative_path.casefold())
            normalized.append(
                {
                    "functional_slot": functional_slot,
                    "relative_path": relative_path,
                    "scope_key": scope_key,
                    "scope_kind": kind,
                    "scope_ordinal": scope_ordinal,
                }
            )
        result[persona_id] = tuple(normalized)
    return result


def _compositor_mappings(compositor_value):
    personas = compositor_value.get("personas") if type(compositor_value) is dict else None
    if type(personas) is not list or len(personas) != len(PERSONA_IDS):
        _fail("device-lane compositor must expose exactly twenty personas")
    result = {}
    all_homes = set()
    all_registries = set()
    for persona_ordinal, (persona_id, persona) in enumerate(zip(PERSONA_IDS, personas), start=1):
        if (
            type(persona) is not dict
            or persona.get("persona_id") != persona_id
            or persona.get("logical_persona_ordinal") != persona_ordinal
        ):
            _fail("device-lane compositor persona order differs from placement contract")
        mappings = persona.get("formal_replay_mappings")
        if type(mappings) is not list or len(mappings) != len(REPLAY_IDS):
            _fail(f"device-lane compositor replay count differs: {persona_id}")
        persona_mappings = {}
        for replay_id, mapping in zip(REPLAY_IDS, mappings):
            if (
                type(mapping) is not dict
                or mapping.get("replay_id") != replay_id
                or mapping.get("formal_scope_count") != SCOPES_PER_PERSONA
                or mapping.get("fresh_w0_build_required") is not True
                or mapping.get("physical_materialization_claimed") is not False
            ):
                _fail(f"device-lane formal mapping drifted: {persona_id}/{replay_id}")
            home_root = mapping.get("home_root")
            registry_root = mapping.get("registry_root")
            device_root = mapping.get("device_root")
            _safe_relative_path(device_root, label="device root")
            _safe_relative_path(home_root, label="home root")
            _safe_relative_path(registry_root, label="registry root")
            if (
                not home_root.startswith(device_root + "/")
                or not registry_root.startswith(device_root + "/")
                or home_root == registry_root
            ):
                _fail("home or registry root escaped/reused its device root")
            if home_root in all_homes or registry_root in all_registries:
                _fail("home or registry roots are pooled")
            all_homes.add(home_root)
            all_registries.add(registry_root)
            persona_mappings[replay_id] = {
                "home_root": home_root,
                "registry_root": registry_root,
            }
        result[persona_id] = persona_mappings
    if len(all_homes) != 60 or len(all_registries) != 60 or all_homes & all_registries:
        _fail("formal home and registry roots must be sixty isolated pairs")
    return result


def _derive_rows(topology_value, compositor_value):
    scopes_by_persona = _topology_scopes(topology_value)
    mappings_by_persona = _compositor_mappings(compositor_value)
    rows = []
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS, start=1):
        for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1):
            mapping = mappings_by_persona[persona_id][replay_id]
            for scope in scopes_by_persona[persona_id]:
                relative_parts = _safe_relative_path(
                    scope["relative_path"], label="derived topology relative path"
                )
                scope_ordinal = scope["scope_ordinal"]
                leaf_root = f"{mapping['home_root']}/{scope['relative_path']}"
                _safe_relative_path(leaf_root, label="derived formal leaf root")
                rows.append(
                    {
                        "row_schema": ROW_SCHEMA,
                        "schema_version": 1,
                        "row_id": (
                            f"formal-leaf-placement-{replay_id}-{persona_id}-"
                            f"scope-{scope_ordinal:02d}"
                        ),
                        "replay_id": replay_id,
                        "replay_ordinal": replay_ordinal,
                        "persona_id": persona_id,
                        "persona_ordinal": persona_ordinal,
                        "scope_key": scope["scope_key"],
                        "scope_ordinal": scope_ordinal,
                        "scope_kind": scope["scope_kind"],
                        "functional_slot": scope["functional_slot"],
                        "relative_path": scope["relative_path"],
                        "home_root": mapping["home_root"],
                        "registry_root": mapping["registry_root"],
                        "leaf_root": leaf_root,
                        "leaf_depth_from_home": len(relative_parts),
                        "direct_child_only": True,
                        "runtime_scope_id_assigned": False,
                    }
                )
    if len(rows) != EXPECTED_ROW_COUNT:
        _fail("independent formal-leaf derivation did not produce exactly 1,200 rows")
    _validate_derived_rows(tuple(rows))
    return tuple(rows)


def _validate_derived_rows(rows):
    if type(rows) is not tuple or len(rows) != EXPECTED_ROW_COUNT:
        _fail("formal-leaf rows must be the exact fixed tuple")
    leaf_roots = set()
    coordinate_rows = set()
    registries = set()
    for expected_index, row in enumerate(rows):
        replay_ordinal = expected_index // (len(PERSONA_IDS) * SCOPES_PER_PERSONA) + 1
        within_replay = expected_index % (len(PERSONA_IDS) * SCOPES_PER_PERSONA)
        persona_ordinal = within_replay // SCOPES_PER_PERSONA + 1
        scope_ordinal = within_replay % SCOPES_PER_PERSONA + 1
        _exact_dict(row, ROW_FIELDS, "formal-leaf row")
        replay_id = REPLAY_IDS[replay_ordinal - 1]
        persona_id = PERSONA_IDS[persona_ordinal - 1]
        if (
            row["row_schema"] != ROW_SCHEMA
            or row["schema_version"] != 1
            or row["row_id"]
            != f"formal-leaf-placement-{replay_id}-{persona_id}-scope-{scope_ordinal:02d}"
            or row["replay_id"] != replay_id
            or row["replay_ordinal"] != replay_ordinal
            or row["persona_id"] != persona_id
            or row["persona_ordinal"] != persona_ordinal
            or row["scope_key"] != f"{persona_id}-scope-{scope_ordinal:02d}"
            or row["scope_ordinal"] != scope_ordinal
            or row["scope_kind"] not in {"primary", "secondary"}
            or (row["scope_kind"] == "primary") != (scope_ordinal <= 12)
            or row["direct_child_only"] is not True
            or row["runtime_scope_id_assigned"] is not False
        ):
            _fail("formal-leaf row scalar contract drifted")
        for field in (
            "row_schema",
            "row_id",
            "replay_id",
            "persona_id",
            "scope_key",
            "scope_kind",
            "functional_slot",
            "relative_path",
            "home_root",
            "registry_root",
            "leaf_root",
        ):
            if type(row[field]) is not str or not row[field]:
                _fail(f"formal-leaf row string field is invalid: {field}")
        for field in (
            "schema_version",
            "replay_ordinal",
            "persona_ordinal",
            "scope_ordinal",
            "leaf_depth_from_home",
        ):
            if type(row[field]) is not int or type(row[field]) is bool or row[field] < 1:
                _fail(f"formal-leaf row integer field is invalid: {field}")
        relative_parts = _safe_relative_path(row["relative_path"], label="row relative path")
        _safe_relative_path(row["home_root"], label="row home root")
        _safe_relative_path(row["registry_root"], label="row registry root")
        _safe_relative_path(row["leaf_root"], label="row leaf root")
        if (
            row["leaf_root"] != f"{row['home_root']}/{row['relative_path']}"
            or row["leaf_depth_from_home"] != len(relative_parts)
            or not row["leaf_root"].startswith(row["home_root"] + "/")
            or row["registry_root"] == row["home_root"]
        ):
            _fail("formal-leaf row path join/distance contract drifted")
        coordinate = (row["replay_id"], row["persona_id"], row["scope_key"])
        if coordinate in coordinate_rows or row["leaf_root"] in leaf_roots:
            _fail("formal-leaf coordinates or roots are not unique")
        coordinate_rows.add(coordinate)
        leaf_roots.add(row["leaf_root"])
        registries.add((row["replay_id"], row["persona_id"], row["registry_root"]))
    if len(coordinate_rows) != EXPECTED_ROW_COUNT or len(leaf_roots) != EXPECTED_ROW_COUNT:
        _fail("formal-leaf uniqueness receipt is incomplete")
    if len(registries) != 60:
        _fail("formal-leaf binding must retain sixty isolated registries")


def _jsonl(rows):
    _validate_derived_rows(rows)
    lines = []
    for row in rows:
        line = _canonical(
            row,
            label="independently derived formal-leaf row",
            maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
        ) + b"\n"
        if len(line) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("formal-leaf row exceeds its LF-inclusive byte cap")
        lines.append(line)
    body = b"".join(lines)
    if len(body) > MAX_BODY_BYTES or not body.endswith(b"\n") or b"\r" in body:
        _fail("independently derived formal-leaf body framing is invalid")
    _require_body_golden(body)
    return body


def _leaf_path_projection_jsonl(rows):
    """Return the ordered plan-only leaf-root projection used for digests."""

    if type(rows) not in (tuple, list) or not rows:
        _fail("leaf-path projection requires non-empty ordered rows")
    lines = []
    for row in rows:
        if type(row) is not dict or type(row.get("leaf_root")) is not str:
            _fail("leaf-path projection row is invalid")
        line = _canonical(
            {"leaf_root": row["leaf_root"]},
            label="formal-leaf path projection row",
            maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
        ) + b"\n"
        if len(line) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("leaf-path projection row exceeds its LF-inclusive byte cap")
        lines.append(line)
    projection = b"".join(lines)
    if not projection.endswith(b"\n") or b"\r" in projection:
        _fail("leaf-path projection framing is invalid")
    return projection


def _registry_summaries(rows):
    """Summarize the 60 planned registry domains without claiming creation."""

    _validate_derived_rows(rows)
    summaries = []
    for start in range(0, len(rows), SCOPES_PER_PERSONA):
        group = rows[start : start + SCOPES_PER_PERSONA]
        if len(group) != SCOPES_PER_PERSONA:
            _fail("formal-leaf registry group is incomplete")
        first = group[0]
        if any(
            row["replay_id"] != first["replay_id"]
            or row["persona_id"] != first["persona_id"]
            or row["home_root"] != first["home_root"]
            or row["registry_root"] != first["registry_root"]
            for row in group
        ):
            _fail("formal-leaf registry group crosses one planned device domain")
        registry_body = b"".join(
            _canonical(
                row,
                label="formal-leaf registry summary row",
                maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
            )
            + b"\n"
            for row in group
        )
        leaf_projection = _leaf_path_projection_jsonl(group)
        summaries.append(
            {
                "replay_id": first["replay_id"],
                "persona_id": first["persona_id"],
                "home_root": first["home_root"],
                "registry_root": first["registry_root"],
                "entry_count": SCOPES_PER_PERSONA,
                "registry_sha256": _sha256(registry_body),
                "leaf_path_sha256": _sha256(leaf_projection),
            }
        )
    if len(summaries) != 60:
        _fail("formal-leaf registry summary count differs from sixty")
    return summaries


def _binding(dependency_id, dependency_role, pin):
    return {
        "artifact_schema": pin[0],
        "artifact_schema_version": pin[1],
        "canonical_bytes": pin[2],
        "dependency_id": dependency_id,
        "dependency_role": dependency_role,
        "sha256": pin[3],
    }


def _descriptor(rows, body):
    _validate_derived_rows(rows)
    if type(body) is not bytes or not body.endswith(b"\n"):
        _fail("formal-leaf descriptor requires one framed body")
    lines = body.splitlines(keepends=True)
    if len(lines) != EXPECTED_ROW_COUNT:
        _fail("formal-leaf descriptor body row count is invalid")
    leaf_path_projection = _leaf_path_projection_jsonl(rows)
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "body_canonical_bytes": len(body),
        "body_embedded": False,
        "body_encoding": BODY_ENCODING,
        "body_final_lf": True,
        "body_framing": BODY_FRAMING,
        "body_id": BODY_ID,
        "body_sha256": _sha256(body),
        "canonical_limits": {
            "external_body_max_bytes": MAX_BODY_BYTES,
            "maximum_lf_inclusive_row_bytes": MAX_ROW_BYTES_INCLUDING_LF,
            "max_binding_bytes": MAX_BINDING_BYTES,
            "max_row_count": MAX_ROW_COUNT,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_1200_formal_leaf_paths_planned": True,
            "body_descriptor_golden_frozen": True,
            "filesystem_materialized": False,
            "g0_eligible": False,
            "scope_registry_created": False,
        },
        "dependency_bindings": [
            _binding(
                "persona-pc-topology-v2",
                "formal-relative-scope-paths",
                TOPOLOGY_PIN,
            ),
            _binding(
                "persona-pc-device-lane-compositor-v1",
                "formal-device-home-and-registry-roots",
                COMPOSITOR_PIN,
            ),
        ],
        "first_row_id": rows[0]["row_id"],
        "first_row_lf_bytes": len(lines[0]),
        "first_row_sha256": _sha256(lines[0]),
        "g0_contract_frozen": False,
        "last_row_id": rows[-1]["row_id"],
        "last_row_lf_bytes": len(lines[-1]),
        "last_row_sha256": _sha256(lines[-1]),
        "maximum_lf_inclusive_row_bytes": max(len(line) for line in lines),
        "persona_order": list(PERSONA_IDS),
        "planning_digests": {
            "scope_registry_sha256": _sha256(body),
            "leaf_path_projection_sha256": _sha256(leaf_path_projection),
        },
        "replay_order": list(REPLAY_IDS),
        "registry_summaries": _registry_summaries(rows),
        "row_count": EXPECTED_ROW_COUNT,
        "row_order": "replay-ordinal-persona-ordinal-scope-ordinal",
        "row_schema": ROW_SCHEMA,
        "safety_contract": {
            "direct_child_files_required": True,
            "filesystem_write_authorized": False,
            "hard_link_allowed": False,
            "nested_managed_files_allowed": False,
            "registry_sharing_allowed": False,
            "symlink_allowed": False,
        },
        "summary": {
            "formal_leaf_path_count_three_replays": EXPECTED_ROW_COUNT,
            "formal_scope_count_per_persona": SCOPES_PER_PERSONA,
            "isolated_registry_count_three_replays": 60,
            "logical_persona_count": len(PERSONA_IDS),
            "physical_device_root_count_three_replays": 60,
            "replay_count": len(REPLAY_IDS),
        },
    }


def _owned_body(value):
    if type(value) is not bytes or len(value) > MAX_BODY_BYTES:
        _fail("external formal-leaf body provider returned unbounded non-exact bytes")
    return bytes(bytearray(value))


def _validate_body_rows(raw, expected_rows):
    if (
        type(raw) is not bytes
        or not raw
        or len(raw) > MAX_BODY_BYTES
        or raw.startswith(b"\xef\xbb\xbf")
        or not raw.endswith(b"\n")
        or b"\r" in raw
    ):
        _fail("external formal-leaf body framing is invalid")
    _require_body_golden(raw)
    lines = raw.splitlines(keepends=True)
    if (
        len(lines) != EXPECTED_ROW_COUNT
        or any(
            not line.endswith(b"\n")
            or line.endswith(b"\r\n")
            or len(line) > MAX_ROW_BYTES_INCLUDING_LF
            for line in lines
        )
    ):
        _fail("external formal-leaf body row framing is invalid")
    parsed = []
    for ordinal, line in enumerate(lines, start=1):
        try:
            row = json.loads(
                line[:-1].decode("utf-8", "strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_float=_reject_float,
                parse_constant=_reject_constant,
            )
        except PersonaV2FormalLeafPlacementBindingValidationError:
            raise
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            _fail(f"external formal-leaf row {ordinal} is invalid: {type(error).__name__}")
        _exact_dict(row, ROW_FIELDS, "external formal-leaf row")
        if (
            _canonical(
                row,
                label="parsed external formal-leaf row",
                maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
            )
            + b"\n"
            != line
        ):
            _fail("external formal-leaf row is not exact canonical JSON")
        parsed.append(row)
    parsed_rows = tuple(parsed)
    _validate_derived_rows(parsed_rows)
    if parsed_rows != expected_rows:
        _fail("external formal-leaf rows differ from independent regeneration")
    return raw


def _check_descriptor_static(snapshot):
    _exact_dict(snapshot, DESCRIPTOR_FIELDS, "formal-leaf descriptor")
    if (
        snapshot["artifact_id"] != ARTIFACT_ID
        or snapshot["artifact_kind"] != ARTIFACT_KIND
        or snapshot["artifact_schema"] != ARTIFACT_SCHEMA
        or snapshot["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or snapshot["body_id"] != BODY_ID
        or snapshot["body_framing"] != BODY_FRAMING
        or snapshot["body_encoding"] != BODY_ENCODING
        or snapshot["row_schema"] != ROW_SCHEMA
        or snapshot["row_count"] != EXPECTED_ROW_COUNT
        or snapshot["row_order"] != "replay-ordinal-persona-ordinal-scope-ordinal"
        or snapshot["persona_order"] != list(PERSONA_IDS)
        or snapshot["replay_order"] != list(REPLAY_IDS)
        or snapshot["body_embedded"] is not False
        or snapshot["body_final_lf"] is not True
        or snapshot["g0_contract_frozen"] is not False
    ):
        _fail("formal-leaf descriptor static identity or boundary is invalid")
    if (
        type(snapshot["body_canonical_bytes"]) is not int
        or type(snapshot["body_canonical_bytes"]) is bool
        or not 1 <= snapshot["body_canonical_bytes"] <= MAX_BODY_BYTES
        or type(snapshot["body_sha256"]) is not str
        or len(snapshot["body_sha256"]) != 64
        or any(character not in "0123456789abcdef" for character in snapshot["body_sha256"])
    ):
        _fail("formal-leaf descriptor body receipt is invalid")
    for label in ("first", "last"):
        row_id = snapshot[f"{label}_row_id"]
        row_bytes = snapshot[f"{label}_row_lf_bytes"]
        row_sha256 = snapshot[f"{label}_row_sha256"]
        if (
            type(row_id) is not str
            or not row_id
            or type(row_bytes) is not int
            or type(row_bytes) is bool
            or not 1 <= row_bytes <= MAX_ROW_BYTES_INCLUDING_LF
            or type(row_sha256) is not str
            or len(row_sha256) != 64
            or any(character not in "0123456789abcdef" for character in row_sha256)
        ):
            _fail(f"formal-leaf descriptor {label}-row receipt is invalid")
    maximum_row = snapshot["maximum_lf_inclusive_row_bytes"]
    if (
        type(maximum_row) is not int
        or type(maximum_row) is bool
        or not 1 <= maximum_row <= MAX_ROW_BYTES_INCLUDING_LF
    ):
        _fail("formal-leaf descriptor maximum row receipt is invalid")
    _exact_dict(snapshot["authority"], AUTHORITY_FIELDS, "formal-leaf authority")
    if any(type(flag) is not bool or flag is not False for flag in snapshot["authority"].values()):
        _fail("formal-leaf authority must remain exact all-false")
    _exact_dict(
        snapshot["completion_claims"],
        COMPLETION_CLAIM_FIELDS,
        "formal-leaf completion claims",
    )
    if snapshot["completion_claims"] != {
        "all_1200_formal_leaf_paths_planned": True,
        "body_descriptor_golden_frozen": True,
        "filesystem_materialized": False,
        "g0_eligible": False,
        "scope_registry_created": False,
    }:
        _fail("formal-leaf completion claims gained execution authority")
    _exact_dict(snapshot["safety_contract"], SAFETY_CONTRACT_FIELDS, "formal-leaf safety contract")
    if snapshot["safety_contract"] != {
        "direct_child_files_required": True,
        "filesystem_write_authorized": False,
        "hard_link_allowed": False,
        "nested_managed_files_allowed": False,
        "registry_sharing_allowed": False,
        "symlink_allowed": False,
    }:
        _fail("formal-leaf safety contract drifted")
    _exact_dict(snapshot["canonical_limits"], CANONICAL_LIMIT_FIELDS, "formal-leaf canonical limits")
    if snapshot["canonical_limits"] != {
        "external_body_max_bytes": MAX_BODY_BYTES,
        "maximum_lf_inclusive_row_bytes": MAX_ROW_BYTES_INCLUDING_LF,
        "max_binding_bytes": MAX_BINDING_BYTES,
        "max_row_count": MAX_ROW_COUNT,
        "unicode_normalization": "NFC",
    }:
        _fail("formal-leaf canonical limits drifted")
    _exact_dict(snapshot["summary"], SUMMARY_FIELDS, "formal-leaf summary")
    if snapshot["summary"] != {
        "formal_leaf_path_count_three_replays": EXPECTED_ROW_COUNT,
        "formal_scope_count_per_persona": SCOPES_PER_PERSONA,
        "isolated_registry_count_three_replays": 60,
        "logical_persona_count": 20,
        "physical_device_root_count_three_replays": 60,
        "replay_count": 3,
    }:
        _fail("formal-leaf summary drifted")
    _exact_dict(
        snapshot["planning_digests"],
        PLANNING_DIGEST_FIELDS,
        "formal-leaf planning digests",
    )
    if any(
        type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
        for digest in snapshot["planning_digests"].values()
    ):
        _fail("formal-leaf planning digest is invalid")
    registry_summaries = snapshot["registry_summaries"]
    if type(registry_summaries) is not list or len(registry_summaries) != 60:
        _fail("formal-leaf registry summaries must contain exactly sixty rows")
    for summary in registry_summaries:
        _exact_dict(summary, REGISTRY_SUMMARY_FIELDS, "formal-leaf registry summary")
        if (
            type(summary["replay_id"]) is not str
            or type(summary["persona_id"]) is not str
            or type(summary["home_root"]) is not str
            or type(summary["registry_root"]) is not str
            or type(summary["entry_count"]) is not int
            or type(summary["entry_count"]) is bool
            or summary["entry_count"] != SCOPES_PER_PERSONA
            or any(
                type(summary[field]) is not str
                or len(summary[field]) != 64
                or any(character not in "0123456789abcdef" for character in summary[field])
                for field in ("registry_sha256", "leaf_path_sha256")
            )
        ):
            _fail("formal-leaf registry summary scalar fields are invalid")
    bindings = snapshot["dependency_bindings"]
    if type(bindings) is not list or len(bindings) != 2:
        _fail("formal-leaf descriptor must bind exactly two upstream artifacts")
    expected_bindings = [
        _binding("persona-pc-topology-v2", "formal-relative-scope-paths", TOPOLOGY_PIN),
        _binding(
            "persona-pc-device-lane-compositor-v1",
            "formal-device-home-and-registry-roots",
            COMPOSITOR_PIN,
        ),
    ]
    for binding in bindings:
        _exact_dict(binding, DEPENDENCY_BINDING_FIELDS, "formal-leaf dependency binding")
    if bindings != expected_bindings:
        _fail("formal-leaf dependency bindings drifted")


def _postflight(value, opening_raw, dependencies):
    if _canonical(
        value,
        label="caller-owned formal-leaf descriptor postflight",
        maximum=MAX_BINDING_BYTES,
    ) != opening_raw:
        _fail("caller-owned formal-leaf descriptor changed during validation")
    for label, dependency, opening, maximum in dependencies:
        if _canonical(
            dependency,
            label=f"caller-owned {label} postflight",
            maximum=maximum,
        ) != opening:
            _fail(f"caller-owned {label} changed during validation")


def validate_formal_leaf_placement_binding(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    topology_value=None,
    compositor_value=None,
    topology_provider=None,
    compositor_provider=None,
    body_provider=None,
    _return_accepted_body=False,
):
    """Validate a descriptor, two read-only providers, and a two-read body.

    The value adapters exist for compatibility.  New integration code should
    supply providers; each provider is opened exactly twice and the validator
    uses only its owned second snapshot.
    """

    expected_golden = _require_producer_golden_parity(producer_expected_golden)
    snapshot, opening_raw = _owned_snapshot(
        value,
        label="formal-leaf placement descriptor",
        maximum=MAX_BINDING_BYTES,
    )
    if expected_golden is not None:
        _assert_descriptor_golden(opening_raw)
    _check_descriptor_static(snapshot)
    if type(_return_accepted_body) is not bool:
        _fail("accepted-body return selector must be an exact boolean")
    if topology_provider is None:
        topology_provider = (
            topology.build_topology_contract
            if topology_value is None
            else lambda: topology_value
        )
    if compositor_provider is None:
        compositor_provider = (
            compositor.build_device_lane_compositor
            if compositor_value is None
            else lambda: compositor_value
        )
    dependencies = ()
    try:
        topology_snapshot, topology_raw, topology_dependencies = _read_provider_twice(
            topology_provider,
            label="topology",
            authenticate=_authenticate_topology,
            maximum=topology.MAX_TOPOLOGY_BYTES,
        )
        compositor_snapshot, compositor_raw, compositor_dependencies = _read_provider_twice(
            compositor_provider,
            label="device-lane compositor",
            authenticate=_authenticate_compositor,
            maximum=compositor.MAX_COMPOSITOR_BYTES,
        )
        dependencies = topology_dependencies + compositor_dependencies
        rows = _derive_rows(topology_snapshot, compositor_snapshot)
        expected_body = _jsonl(rows)
        expected_descriptor = _descriptor(rows, expected_body)
        expected_raw = _canonical(
            expected_descriptor,
            label="independently regenerated formal-leaf descriptor",
            maximum=MAX_BINDING_BYTES,
        )
        _assert_descriptor_golden(expected_raw)
        if opening_raw != expected_raw or snapshot != expected_descriptor:
            _fail("formal-leaf descriptor differs from independent exact regeneration")
        if body_provider is None:
            body_provider = lambda artifact_id, body_id: expected_body
        if not callable(body_provider):
            _fail("external formal-leaf body provider must be callable")
        try:
            first = body_provider(ARTIFACT_ID, BODY_ID)
            first_owned = _owned_body(first)
            _validate_body_rows(first_owned, rows)
            second = body_provider(ARTIFACT_ID, BODY_ID)
            second_owned = _owned_body(second)
            _validate_body_rows(second_owned, rows)
        except PersonaV2FormalLeafPlacementBindingValidationError:
            raise
        except Exception as error:
            _fail(f"external formal-leaf body provider failed: {type(error).__name__}")
        if first_owned != second_owned or second_owned != expected_body:
            _fail("external formal-leaf body provider replay is nondeterministic")
        return second_owned if _return_accepted_body else True
    finally:
        _postflight(value, opening_raw, dependencies)


def accepted_formal_leaf_placement_body_bytes(value, **kwargs):
    """Return the owned second body read without opening a provider a third time."""

    kwargs["_return_accepted_body"] = True
    accepted = validate_formal_leaf_placement_binding(value, **kwargs)
    if type(accepted) is not bytes:
        _fail("accepted formal-leaf body did not remain exact bytes")
    return accepted


def strict_load_canonical_json_bytes(raw):
    """Load an exact canonical UTF-8 descriptor with duplicate-key rejection."""

    if type(raw) is not bytes or not raw or len(raw) > MAX_BINDING_BYTES:
        _fail("formal-leaf descriptor body must be immutable bytes within its cap")
    if raw.startswith(b"\xef\xbb\xbf"):
        _fail("formal-leaf descriptor body must not contain a UTF-8 BOM")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2FormalLeafPlacementBindingValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"formal-leaf descriptor body is not strict UTF-8 JSON: {type(error).__name__}")
    if type(value) is not dict:
        _fail("formal-leaf descriptor body must be one JSON object")
    if _canonical(value, label="loaded formal-leaf descriptor", maximum=MAX_BINDING_BYTES) != raw:
        _fail("formal-leaf descriptor body is not exact canonical JSON")
    return value


def load_and_validate_formal_leaf_placement_binding(raw, **kwargs):
    value = strict_load_canonical_json_bytes(raw)
    validate_formal_leaf_placement_binding(value, **kwargs)
    return value


def validate_formal_leaf_placement_binding_bytes(raw, **kwargs):
    """Compatibility alias for strict descriptor loading plus validation."""

    return load_and_validate_formal_leaf_placement_binding(raw, **kwargs)


def formal_leaf_placement_binding_golden_receipts(
    *, topology_provider=None, compositor_provider=None
):
    """Report deterministic body/descriptor receipts for a later explicit freeze."""

    if topology_provider is None:
        topology_provider = topology.build_topology_contract
    if compositor_provider is None:
        compositor_provider = compositor.build_device_lane_compositor
    topology_snapshot, _, _ = _read_provider_twice(
        topology_provider,
        label="topology",
        authenticate=_authenticate_topology,
        maximum=topology.MAX_TOPOLOGY_BYTES,
    )
    compositor_snapshot, _, _ = _read_provider_twice(
        compositor_provider,
        label="device-lane compositor",
        authenticate=_authenticate_compositor,
        maximum=compositor.MAX_COMPOSITOR_BYTES,
    )
    rows = _derive_rows(topology_snapshot, compositor_snapshot)
    body = _jsonl(rows)
    descriptor = _descriptor(rows, body)
    descriptor_raw = _canonical(
        descriptor,
        label="formal-leaf descriptor golden receipt",
        maximum=MAX_BINDING_BYTES,
    )
    return {
        "body_canonical_bytes": len(body),
        "body_sha256": _sha256(body),
        "descriptor_canonical_bytes": len(descriptor_raw),
        "descriptor_sha256": _sha256(descriptor_raw),
    }


def require_authorized_formal_leaf_placement_binding(value, **kwargs):
    """Fail closed: this planning candidate can never authorize execution."""

    validate_formal_leaf_placement_binding(value, **kwargs)
    _fail(
        "formal-leaf placement binding is non-authorizing; physical writer, "
        "scope registry, root-bound capacity, readback, history, KCS, and G0 "
        "receipts remain unresolved"
    )


__all__ = [
    "ARTIFACT_ID",
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "BODY_FRAMING",
    "BODY_ID",
    "COMPOSITOR_PIN",
    "EXPECTED_BODY_BYTES",
    "EXPECTED_BODY_SHA256",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_ROW_COUNT",
    "EXPECTED_SHA256",
    "MAX_BINDING_BYTES",
    "MAX_BODY_BYTES",
    "PERSONA_IDS",
    "PersonaV2FormalLeafPlacementBindingValidationError",
    "REPLAY_IDS",
    "ROW_SCHEMA",
    "TOPOLOGY_PIN",
    "accepted_formal_leaf_placement_body_bytes",
    "configured_descriptor_golden",
    "formal_leaf_placement_binding_golden_receipts",
    "load_and_validate_formal_leaf_placement_binding",
    "require_authorized_formal_leaf_placement_binding",
    "strict_load_canonical_json_bytes",
    "validate_formal_leaf_placement_binding",
    "validate_formal_leaf_placement_binding_bytes",
]
