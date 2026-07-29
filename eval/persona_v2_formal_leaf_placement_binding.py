"""Non-authorizing formal-leaf placement binding for persona-PC v2.

The existing topology owns the twenty logical scope paths for each persona and
the device-lane compositor owns the three isolated device/home/registry roots
per persona.  This candidate joins those two *already frozen* inputs into a
bounded external canonical LF-JSONL body of 1,200 planned leaf roots.

It deliberately does not make directories, register scopes, write files,
execute KIO, attach history, or issue a G0 decision.  In particular,
``direct_child_only`` is a writer-side placement rule, not a claim that any
filesystem entry has been observed.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_device_lane_compositor as compositor
    from . import persona_v2_formal_leaf_placement_binding_validator as independent
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_device_lane_compositor as compositor
    import persona_v2_formal_leaf_placement_binding_validator as independent
    import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kio.persona.pc-formal-leaf-placement-binding/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-non-authorizing-formal-leaf-placement-binding-candidate"
ARTIFACT_ID = "persona-pc-v2-formal-leaf-placement-binding-v1"
BODY_ID = "persona-pc-v2-formal-leaf-placement-rows-v1"
ROW_SCHEMA = "kio.persona.pc-formal-leaf-placement-row/v1"
BODY_FRAMING = "canonical-lf-jsonl/v1"
BODY_ENCODING = "canonical-json-per-row-utf8-nfc-lf"

MAX_BINDING_BYTES = 256 * 2**10
MAX_BODY_BYTES = 2 * 2**20
MAX_ROW_BYTES_INCLUDING_LF = 2_048
MAX_ROW_COUNT = 1_200
MAX_PERSONA_COUNT = 20
MAX_REPLAY_COUNT = 3
SCOPES_PER_PERSONA = 20

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, MAX_PERSONA_COUNT + 1))
REPLAY_IDS = (
    "formal-replay-01",
    "formal-replay-02",
    "formal-replay-03",
)

# These exact dependency pins are a binding to static contracts, not a new
# selection of topology or physical-device policy.
TOPOLOGY_PIN = (
    "kio.persona.pc-topology/v2",
    2,
    134_195,
    "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a",
)
COMPOSITOR_PIN = (
    "kio.persona.pc-device-lane-compositor/v1",
    1,
    41_099,
    "8c9071d0549c7d876068aa145de369f21f787ca2f23dfeb61254efa4e83b808f",
)

# Frozen content-only receipts for the independently regenerated body.  The
# descriptor pin below is computed after its freeze-status claim is set true;
# neither pin grants filesystem, KIO, history, or G0 authority.
EXPECTED_BODY_BYTES = 889_056
EXPECTED_BODY_SHA256 = "98e7239f498c8ebff3f2c754a24036ac7c5263a2f5f6b2bb66275ceaccd8f66e"
EXPECTED_CANONICAL_BYTES = 27_117
EXPECTED_SHA256 = "ce60077869f899473b439b3a48446a629016d9c5c2ba472445aee1fb427f1237"

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

AUTHORITY_FIELDS = (
    "actual_filesystem_paths_attested",
    "actual_scope_registration_attested",
    "authorizes_filesystem_materialization",
    "authorizes_g0_freeze",
    "authorizes_history_execution",
    "authorizes_kio_execution",
    "authorizes_physical_write",
    "authorizes_registry_creation",
    "authorizes_scope_registration",
    "physical_path_authority",
    "writer_available",
)


class PersonaV2FormalLeafPlacementBindingError(ValueError):
    """Raised when the formal-leaf placement candidate is not exact."""


def _fail(message):
    raise PersonaV2FormalLeafPlacementBindingError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(value, label=label, max_bytes=maximum)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _expected_body_pin():
    bytes_set = EXPECTED_BODY_BYTES is not None
    digest_set = EXPECTED_BODY_SHA256 is not None
    if bytes_set != digest_set:
        _fail("formal-leaf placement body golden must be entirely unset or entirely set")
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
        _fail("formal-leaf placement body golden configuration is invalid")
    return EXPECTED_BODY_BYTES, EXPECTED_BODY_SHA256


def _expected_descriptor_golden():
    bytes_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if bytes_set != digest_set:
        _fail("formal-leaf placement descriptor golden must be entirely unset or entirely set")
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
        _fail("formal-leaf placement descriptor golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_golden_parity():
    expected = (_expected_body_pin(), _expected_descriptor_golden())
    try:
        validator_expected = (
            independent._expected_body_pin(),
            independent._expected_descriptor_golden(),
        )
    except Exception as error:
        raise PersonaV2FormalLeafPlacementBindingError(
            "independent validator golden configuration is invalid"
        ) from error
    if type(expected) is not type(validator_expected) or expected != validator_expected:
        _fail("producer and validator formal-leaf placement goldens differ")
    return expected


def _require_body_pin(raw):
    if type(raw) is not bytes or not raw or len(raw) > MAX_BODY_BYTES:
        _fail("formal-leaf placement external body is outside the bounded byte domain")
    expected = _expected_body_pin()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("formal-leaf placement external body differs from frozen golden")
    return raw


def _require_descriptor_golden(raw):
    expected = _expected_descriptor_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("formal-leaf placement descriptor differs from frozen golden")
    return raw


def _authenticate_topology(value):
    """Authenticate a provider-owned topology value without retaining it."""

    try:
        raw = topology.canonical_json_bytes(value)
        topology.validate_topology_contract(value)
        closing = topology.canonical_json_bytes(value)
    except Exception as error:
        _fail(f"formal topology validation failed: {type(error).__name__}")
    if not hmac.compare_digest(raw, closing):
        _fail("formal topology changed during validation")
    if (
        type(value) is not dict
        or value.get("artifact_schema") != TOPOLOGY_PIN[0]
        or value.get("artifact_schema_version") != TOPOLOGY_PIN[1]
        or len(raw) != TOPOLOGY_PIN[2]
        or not hmac.compare_digest(_sha256(raw), TOPOLOGY_PIN[3])
    ):
        _fail("formal topology differs from the placement binding pin")
    return raw


def _authenticate_compositor(value):
    """Authenticate a provider-owned device compositor value without retaining it."""

    try:
        raw = compositor.canonical_json_bytes(value)
        compositor.validate_device_lane_compositor(value)
        closing = compositor.canonical_json_bytes(value)
    except Exception as error:
        _fail(f"device-lane compositor validation failed: {type(error).__name__}")
    if not hmac.compare_digest(raw, closing):
        _fail("device-lane compositor changed during validation")
    if (
        type(value) is not dict
        or value.get("artifact_schema") != COMPOSITOR_PIN[0]
        or value.get("artifact_schema_version") != COMPOSITOR_PIN[1]
        or len(raw) != COMPOSITOR_PIN[2]
        or not hmac.compare_digest(_sha256(raw), COMPOSITOR_PIN[3])
    ):
        _fail("device-lane compositor differs from the placement binding pin")
    return raw


def _two_read_dependency(label, provider, authenticate):
    """Take two authenticated snapshots so a mutable provider cannot drift."""

    if not callable(provider):
        _fail(f"{label} provider must be callable")
    try:
        first = provider()
        first_raw = authenticate(first)
        second = provider()
        second_raw = authenticate(second)
        detached = copy.deepcopy(second)
    except PersonaV2FormalLeafPlacementBindingError:
        raise
    except Exception as error:
        _fail(f"{label} provider failed: {type(error).__name__}")
    try:
        detached_raw = authenticate(detached)
    except PersonaV2FormalLeafPlacementBindingError:
        raise
    if not hmac.compare_digest(first_raw, second_raw):
        _fail(f"{label} provider replay is nondeterministic")
    if not hmac.compare_digest(second_raw, detached_raw):
        _fail(f"{label} detached snapshot differs from provider output")
    return detached, detached_raw


def _authenticate_upstreams():
    if tuple(compositor.REPLAY_IDS) != REPLAY_IDS:
        _fail("device-lane compositor replay order differs from placement contract")
    topology_value, topology_raw = _two_read_dependency(
        "formal topology",
        topology.build_topology_contract,
        _authenticate_topology,
    )
    compositor_value, compositor_raw = _two_read_dependency(
        "device-lane compositor",
        compositor.build_device_lane_compositor,
        _authenticate_compositor,
    )
    return topology_value, topology_raw, compositor_value, compositor_raw


def _exact_list(value, expected_length, label):
    if type(value) is not list or len(value) != expected_length:
        _fail(f"{label} must be an exact {expected_length}-row list")
    return value


def _derive_rows(topology_value, compositor_value):
    """Derive the 3 x 20 x 20 logical leaf placement rows."""

    try:
        topology_personas = _exact_list(
            topology_value["personas"], MAX_PERSONA_COUNT, "formal topology personas"
        )
        compositor_personas = _exact_list(
            compositor_value["personas"],
            MAX_PERSONA_COUNT,
            "device-lane compositor personas",
        )
    except (KeyError, TypeError):
        _fail("upstream persona projections are malformed")

    joined_personas = []
    for persona_ordinal, persona_id in enumerate(PERSONA_IDS, start=1):
        topology_persona = topology_personas[persona_ordinal - 1]
        compositor_persona = compositor_personas[persona_ordinal - 1]
        if (
            type(topology_persona) is not dict
            or type(compositor_persona) is not dict
            or topology_persona.get("persona_id") != persona_id
            or compositor_persona.get("persona_id") != persona_id
            or compositor_persona.get("logical_persona_ordinal") != persona_ordinal
        ):
            _fail("upstream persona order differs from formal-leaf placement contract")
        scopes = _exact_list(
            topology_persona.get("scopes"),
            SCOPES_PER_PERSONA,
            f"{persona_id} topology scopes",
        )
        mappings = _exact_list(
            compositor_persona.get("formal_replay_mappings"),
            MAX_REPLAY_COUNT,
            f"{persona_id} formal replay mappings",
        )
        joined_personas.append((persona_ordinal, persona_id, scopes, mappings))

    rows = []
    seen_leaf_roots = set()
    seen_registry_roots = set()
    for replay_ordinal, replay_id in enumerate(REPLAY_IDS, start=1):
        for persona_ordinal, persona_id, scopes, mappings in joined_personas:
            mapping = mappings[replay_ordinal - 1]
            if type(mapping) is not dict or mapping.get("replay_id") != replay_id:
                _fail("formal replay mapping order differs from placement contract")
            home_root = mapping.get("home_root")
            registry_root = mapping.get("registry_root")
            if (
                type(home_root) is not str
                or type(registry_root) is not str
                or not home_root
                or not registry_root
                or home_root.startswith("/")
                or registry_root.startswith("/")
                or "\\" in home_root
                or "\\" in registry_root
                or "//" in home_root
                or "//" in registry_root
            ):
                _fail("formal replay mapping paths are not canonical relative POSIX paths")
            if registry_root in seen_registry_roots:
                _fail("formal replay registry roots must be unique")
            seen_registry_roots.add(registry_root)
            for scope_ordinal, scope in enumerate(scopes, start=1):
                if (
                    type(scope) is not dict
                    or scope.get("ordinal") != scope_ordinal
                    or scope.get("scope_key") != f"{persona_id}-scope-{scope_ordinal:02d}"
                ):
                    _fail("formal topology scope order differs from placement contract")
                relative_path = scope.get("relative_path")
                if (
                    type(relative_path) is not str
                    or not relative_path
                    or relative_path.startswith("/")
                    or relative_path.endswith("/")
                    or "//" in relative_path
                    or "\\" in relative_path
                    or any(component in ("", ".", "..") for component in relative_path.split("/"))
                ):
                    _fail("formal topology relative path is unsafe for leaf placement")
                leaf_root = f"{home_root}/{relative_path}"
                if leaf_root in seen_leaf_roots:
                    _fail("formal leaf root collisions are forbidden")
                seen_leaf_roots.add(leaf_root)
                rows.append(
                    {
                        "row_schema": ROW_SCHEMA,
                        "schema_version": ARTIFACT_SCHEMA_VERSION,
                        "row_id": (
                            f"formal-leaf-placement-{replay_id}-{persona_id}"
                            f"-scope-{scope_ordinal:02d}"
                        ),
                        "replay_id": replay_id,
                        "replay_ordinal": replay_ordinal,
                        "persona_id": persona_id,
                        "persona_ordinal": persona_ordinal,
                        "scope_key": scope["scope_key"],
                        "scope_ordinal": scope_ordinal,
                        "scope_kind": scope.get("kind"),
                        "functional_slot": scope.get("functional_slot"),
                        "relative_path": relative_path,
                        "home_root": home_root,
                        "registry_root": registry_root,
                        "leaf_root": leaf_root,
                        "leaf_depth_from_home": len(relative_path.split("/")),
                        "direct_child_only": True,
                        "runtime_scope_id_assigned": False,
                    }
                )
    if (
        len(rows) != MAX_ROW_COUNT
        or len(seen_leaf_roots) != MAX_ROW_COUNT
        or len(seen_registry_roots) != MAX_PERSONA_COUNT * MAX_REPLAY_COUNT
    ):
        _fail("formal-leaf placement row/root totals differ from the fixed contract")
    return tuple(rows)


def _jsonl(rows):
    if type(rows) is not tuple or len(rows) != MAX_ROW_COUNT:
        _fail("formal-leaf placement rows must be the fixed tuple")
    body = _rows_jsonl(rows, label="formal-leaf placement row")
    _require_body_pin(body)
    return body


def _rows_jsonl(rows, *, label):
    """Encode an ordered row sequence as bounded canonical LF-JSONL."""

    if type(rows) not in (tuple, list) or not rows:
        _fail("formal-leaf placement JSONL rows must be a non-empty exact sequence")
    encoded_rows = []
    for row in rows:
        if type(row) is not dict or frozenset(row) != ROW_FIELDS:
            _fail("formal-leaf placement row fields differ from exact schema")
        raw = _canonical(
            row,
            label=label,
            maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
        )
        framed = raw + b"\n"
        if len(framed) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("formal-leaf placement row exceeds its LF-inclusive byte cap")
        encoded_rows.append(framed)
    body = b"".join(encoded_rows)
    if not body.endswith(b"\n") or b"\r" in body:
        _fail("formal-leaf placement body must be LF-only and LF-terminated")
    return body


def _leaf_path_projection_body(rows):
    """Return the ordered, leaf-root-only canonical projection used for digests."""

    if type(rows) not in (tuple, list) or not rows:
        _fail("formal-leaf path projection rows must be non-empty")
    encoded_rows = []
    for row in rows:
        if type(row) is not dict or frozenset(row) != ROW_FIELDS:
            _fail("formal-leaf path projection row fields differ from exact schema")
        leaf_root = row.get("leaf_root")
        if type(leaf_root) is not str:
            _fail("formal-leaf path projection requires a string leaf root")
        raw = _canonical(
            {"leaf_root": leaf_root},
            label="formal-leaf path projection row",
            maximum=MAX_ROW_BYTES_INCLUDING_LF - 1,
        )
        framed = raw + b"\n"
        if len(framed) > MAX_ROW_BYTES_INCLUDING_LF:
            _fail("formal-leaf path projection row exceeds its LF-inclusive byte cap")
        encoded_rows.append(framed)
    body = b"".join(encoded_rows)
    if not body.endswith(b"\n") or b"\r" in body:
        _fail("formal-leaf path projection must be LF-only and LF-terminated")
    return body


def _registry_summaries(rows):
    """Summarize each planned registry without claiming it exists on disk."""

    if type(rows) is not tuple or len(rows) != MAX_ROW_COUNT:
        _fail("formal-leaf placement registry summaries require the fixed row tuple")
    summaries = []
    for start in range(0, len(rows), SCOPES_PER_PERSONA):
        group = rows[start : start + SCOPES_PER_PERSONA]
        first = group[0]
        replay_id = first["replay_id"]
        persona_id = first["persona_id"]
        home_root = first["home_root"]
        registry_root = first["registry_root"]
        if (
            len(group) != SCOPES_PER_PERSONA
            or any(
                row["replay_id"] != replay_id
                or row["persona_id"] != persona_id
                or row["home_root"] != home_root
                or row["registry_root"] != registry_root
                or row["scope_ordinal"] != ordinal
                for ordinal, row in enumerate(group, start=1)
            )
        ):
            _fail("formal-leaf placement registry grouping differs from row order")
        registry_body = _rows_jsonl(group, label="formal-leaf placement registry row")
        leaf_path_body = _leaf_path_projection_body(group)
        summaries.append(
            {
                "replay_id": replay_id,
                "persona_id": persona_id,
                "home_root": home_root,
                "registry_root": registry_root,
                "entry_count": len(group),
                "registry_sha256": _sha256(registry_body),
                "leaf_path_sha256": _sha256(leaf_path_body),
            }
        )
    if len(summaries) != MAX_PERSONA_COUNT * MAX_REPLAY_COUNT:
        _fail("formal-leaf placement registry summary count differs from contract")
    return summaries


def _dependency_binding(dependency_id, dependency_role, pin):
    return {
        "artifact_schema": pin[0],
        "artifact_schema_version": pin[1],
        "canonical_bytes": pin[2],
        "dependency_id": dependency_id,
        "dependency_role": dependency_role,
        "sha256": pin[3],
    }


def _descriptor(rows, body, topology_raw, compositor_raw):
    _require_body_pin(body)
    if (
        len(topology_raw) != TOPOLOGY_PIN[2]
        or not hmac.compare_digest(_sha256(topology_raw), TOPOLOGY_PIN[3])
        or len(compositor_raw) != COMPOSITOR_PIN[2]
        or not hmac.compare_digest(_sha256(compositor_raw), COMPOSITOR_PIN[3])
    ):
        _fail("authenticated dependency raw bodies drifted before descriptor binding")
    line_rows = body.splitlines(keepends=True)
    if len(line_rows) != MAX_ROW_COUNT:
        _fail("formal-leaf placement body line count differs from contract")
    maximum_row = max(len(line) for line in line_rows)
    if maximum_row > MAX_ROW_BYTES_INCLUDING_LF:
        _fail("formal-leaf placement body maximum row byte count exceeds cap")
    registry_summaries = _registry_summaries(rows)
    leaf_path_projection = _leaf_path_projection_body(rows)
    return {
        "artifact_id": ARTIFACT_ID,
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in AUTHORITY_FIELDS},
        "body_canonical_bytes": len(body),
        "body_embedded": False,
        "body_encoding": BODY_ENCODING,
        "body_final_lf": True,
        "body_framing": BODY_FRAMING,
        "body_id": BODY_ID,
        "body_sha256": _sha256(body),
        "canonical_limits": {
            "external_body_max_bytes": MAX_BODY_BYTES,
            "max_binding_bytes": MAX_BINDING_BYTES,
            "max_row_count": MAX_ROW_COUNT,
            "maximum_lf_inclusive_row_bytes": MAX_ROW_BYTES_INCLUDING_LF,
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
            _dependency_binding(
                "persona-pc-topology-v2",
                "formal-relative-scope-paths",
                TOPOLOGY_PIN,
            ),
            _dependency_binding(
                "persona-pc-device-lane-compositor-v1",
                "formal-device-home-and-registry-roots",
                COMPOSITOR_PIN,
            ),
        ],
        "first_row_id": rows[0]["row_id"],
        "first_row_lf_bytes": len(line_rows[0]),
        "first_row_sha256": _sha256(line_rows[0]),
        "g0_contract_frozen": False,
        "last_row_id": rows[-1]["row_id"],
        "last_row_lf_bytes": len(line_rows[-1]),
        "last_row_sha256": _sha256(line_rows[-1]),
        "maximum_lf_inclusive_row_bytes": maximum_row,
        "persona_order": list(PERSONA_IDS),
        "planning_digests": {
            "scope_registry_sha256": _sha256(body),
            "leaf_path_projection_sha256": _sha256(leaf_path_projection),
        },
        "replay_order": list(REPLAY_IDS),
        "registry_summaries": registry_summaries,
        "row_count": len(rows),
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
            "formal_leaf_path_count_three_replays": MAX_ROW_COUNT,
            "formal_scope_count_per_persona": SCOPES_PER_PERSONA,
            "isolated_registry_count_three_replays": MAX_PERSONA_COUNT
            * MAX_REPLAY_COUNT,
            "logical_persona_count": MAX_PERSONA_COUNT,
            "physical_device_root_count_three_replays": MAX_PERSONA_COUNT
            * MAX_REPLAY_COUNT,
            "replay_count": MAX_REPLAY_COUNT,
        },
    }


def _build_state():
    """Re-authenticate both upstream contracts and return detached candidate state."""

    topology_value, topology_raw, compositor_value, compositor_raw = _authenticate_upstreams()
    rows = _derive_rows(topology_value, compositor_value)
    body = _jsonl(rows)
    descriptor = _descriptor(rows, body, topology_raw, compositor_raw)
    raw = _canonical(
        descriptor,
        label="formal-leaf placement descriptor",
        maximum=MAX_BINDING_BYTES,
    )
    _require_descriptor_golden(raw)
    return descriptor, body, rows


def build_formal_leaf_placement_rows():
    """Return detached logical placement rows; this never creates directories."""

    _require_golden_parity()
    return copy.deepcopy(_build_state()[2])


def formal_leaf_placement_body_bytes():
    """Return the canonical external LF-JSONL body, not a filesystem write."""

    _require_golden_parity()
    return bytes(_build_state()[1])


def build_formal_leaf_placement_binding():
    """Return a detached, non-authorizing descriptor for the 1,200 planned leaves."""

    _require_golden_parity()
    return copy.deepcopy(_build_state()[0])


def canonical_json_bytes(value):
    """Canonicalize a candidate descriptor and enforce a configured golden, if any."""

    _require_golden_parity()
    raw = _canonical(
        value,
        label="formal-leaf placement descriptor",
        maximum=MAX_BINDING_BYTES,
    )
    _require_descriptor_golden(raw)
    return raw


def validate_formal_leaf_placement_binding(value):
    """Independently validate an exact descriptor and two body-provider replays."""

    _require_golden_parity()
    opening_raw = canonical_json_bytes(value)
    try:
        opening_snapshot = json.loads(opening_raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"formal-leaf placement descriptor decoding failed: {type(error).__name__}")
    expected_raw = canonical_json_bytes(build_formal_leaf_placement_binding())
    if not hmac.compare_digest(opening_raw, expected_raw):
        _fail("formal-leaf placement descriptor differs from exact regeneration")
    try:
        accepted_body = independent.accepted_formal_leaf_placement_body_bytes(
            opening_snapshot,
            producer_expected_golden=(
                _expected_body_pin(),
                _expected_descriptor_golden(),
            ),
            topology_provider=topology.build_topology_contract,
            compositor_provider=compositor.build_device_lane_compositor,
            body_provider=lambda artifact_id, body_id: (
                formal_leaf_placement_body_bytes()
                if artifact_id == ARTIFACT_ID and body_id == BODY_ID
                else _fail("unexpected formal-leaf placement body provider coordinates")
            ),
        )
        _require_body_pin(accepted_body)
    except independent.PersonaV2FormalLeafPlacementBindingValidationError as error:
        _fail(str(error))
    finally:
        if not hmac.compare_digest(canonical_json_bytes(value), opening_raw):
            _fail("caller-owned formal-leaf placement descriptor changed during validation")
    return True


def formal_leaf_placement_binding_sha256(value=None):
    """Validate the candidate and return its descriptor SHA-256."""

    _require_golden_parity()
    if value is None:
        value = build_formal_leaf_placement_binding()
    opening_raw = canonical_json_bytes(value)
    try:
        validate_formal_leaf_placement_binding(value)
        return _sha256(opening_raw)
    finally:
        if not hmac.compare_digest(canonical_json_bytes(value), opening_raw):
            _fail("caller-owned formal-leaf placement descriptor changed during hashing")


def require_authorized_formal_leaf_placement_binding():
    """Fail closed: a static path binding cannot authorize physical execution."""

    _fail(
        "formal-leaf placement is non-authorizing: source plan, writer, capacity, "
        "scope registration, filesystem readback, KIO, history, and G0 issuance "
        "remain absent"
    )


def require_issued_formal_leaf_placement_binding():
    """Compatibility spelling; no content-only candidate is an issuance authority."""

    require_authorized_formal_leaf_placement_binding()


__all__ = [
    "ARTIFACT_ID",
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "BODY_ENCODING",
    "BODY_FRAMING",
    "BODY_ID",
    "COMPOSITOR_PIN",
    "EXPECTED_BODY_BYTES",
    "EXPECTED_BODY_SHA256",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_BINDING_BYTES",
    "MAX_BODY_BYTES",
    "MAX_ROW_BYTES_INCLUDING_LF",
    "PERSONA_IDS",
    "PersonaV2FormalLeafPlacementBindingError",
    "REPLAY_IDS",
    "ROW_SCHEMA",
    "TOPOLOGY_PIN",
    "build_formal_leaf_placement_binding",
    "build_formal_leaf_placement_rows",
    "canonical_json_bytes",
    "formal_leaf_placement_binding_sha256",
    "formal_leaf_placement_body_bytes",
    "require_authorized_formal_leaf_placement_binding",
    "require_issued_formal_leaf_placement_binding",
    "validate_formal_leaf_placement_binding",
]
