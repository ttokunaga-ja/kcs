"""Producer-independent validation for global persona-PC content projections.

The module intentionally does not import
``persona_v2_semantic_projection_global_content``.  It independently rebuilds
the three projection bodies from frozen upstream owners, caches only immutable
raw bytes, and re-reads live owner/direct-fragment builders around untrusted
projection-provider callbacks.
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
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_route_affinity as route
    from . import persona_v2_topology as topology
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_realism_profile as realism
    import persona_v2_route_affinity as route
    import persona_v2_topology as topology


ARTIFACT_SCHEMA_VERSION = 1
BODY_FRAMING = "canonical-json"
MAX_PROJECTION_BYTES = 384 * 2**10
TARGET_PROJECTION_BYTES = 256 * 2**10
MAX_FRAGMENT_BYTES = 384 * 2**10
MAX_MATERIAL_IMAGE_BYTES = 128 * 2**10

TOPOLOGY_CLASS_ID = "topology-path-load"
REALISM_CLASS_ID = "realism-locale-security"
ROUTE_CLASS_ID = "route-scores"
CLASS_ORDER = (TOPOLOGY_CLASS_ID, REALISM_CLASS_ID, ROUTE_CLASS_ID)

TOPOLOGY_PROJECTION_SCHEMA = (
    "kio.persona.pc-topology-path-load-content-projection/v1"
)
TOPOLOGY_PROJECTION_KIND = (
    "persona-pc-v2-topology-path-load-content-projection"
)
REALISM_PROJECTION_SCHEMA = (
    "kio.persona.pc-realism-locale-security-content-projection/v1"
)
REALISM_PROJECTION_KIND = (
    "persona-pc-v2-realism-locale-security-content-projection"
)
ROUTE_PROJECTION_SCHEMA = "kio.persona.pc-route-scores-content-projection/v1"
ROUTE_PROJECTION_KIND = "persona-pc-v2-route-scores-content-projection"

TOPOLOGY_OWNER_BYTES = 134_195
TOPOLOGY_OWNER_SHA256 = (
    "02e0e68d37378a1123743673aad826757d17480de77a5a7313f09932c5759c4a"
)
REALISM_OWNER_BYTES = 36_811
REALISM_OWNER_SHA256 = (
    "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb"
)
ROUTE_OWNER_BYTES = 70_626
ROUTE_OWNER_SHA256 = (
    "7536b815ed5f614db2c31d49138385c7be76c71d45d7fc30f3380b3a9ae3b957"
)

EXPECTED_PROJECTION_PINS = (
    (
        TOPOLOGY_CLASS_ID,
        133_187,
        "36c27d36ba074b884090a094541b33e34f719c2ed6c817309d26c9d9e2395db6",
    ),
    (
        REALISM_CLASS_ID,
        32_762,
        "6aec6942e00305334d90e0094c1a1903af2f6dd941ccc8e2e08d6f91980086ed",
    ),
    (
        ROUTE_CLASS_ID,
        88_085,
        "a555ef18181f525ca713e5f3655969dbd8d8b0ba3a205a5ae700f9ba2234ff03",
    ),
)
EXPECTED_DIRECT_FRAGMENT_PINS = (
    (
        "topology-path-load-source-fragment",
        132_561,
        "72cc4ce344e6b5ce6eda7a411b59ed8cf9ac89ba4248e381eba64a38fcefb3bb",
    ),
    (
        "realism-locale-security-source-fragment",
        32_196,
        "4119140b11132fa8213c8ca21c2b96fdc626d7ead167575e573c86e2fdf62197",
    ),
    (
        "route-score-row-body",
        69_762,
        "1e337e27433e73a1c4e9b5827138930b9a44cc8af5f88ee9e8bca1af45d85183",
    ),
    (
        "topology-scope-axis-body",
        17_284,
        "d9fa1f53526190c57a4a0a23ebfd09754c7decbcd04157bf4dc1f8a2a910e28c",
    ),
)

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "content_rules",
        "content_sections",
        "fixture_id",
        "fixture_schema_version",
        "summary",
    }
)
MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body",
        "body_framing",
        "class_id",
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projector",
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
PROJECTOR_FIELDS = frozenset({"projector_id", "projector_version"})

_PROJECTION_EXCLUDES = [
    "authority-completion-blocker-and-review-state",
    "derivation-receipts-and-full-owner-digests",
    "query-oracle-answer-distractor-and-evaluation-fields",
    "runtime-observations-and-capacity-state",
    "solver-solution-final-identifiers-and-compiled-history",
]
_FORBIDDEN_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "completion",
        "distractor",
        "g0",
        "observed",
        "oracle",
        "query",
        "review",
        "runtime",
        "sha256",
        "solution",
    }
)


class PersonaV2SemanticProjectionGlobalContentValidationError(ValueError):
    """Raised when global projection content or its owner chain is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionGlobalContentValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum=MAX_PROJECTION_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_duplicate_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_constant(_value):
    _fail("non-finite JSON numbers are forbidden")


def _reject_float(_value):
    _fail("JSON floating-point numbers are forbidden")


def _strict_loads(raw, *, label):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact built-in bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
            parse_float=_reject_float,
        )
    except PersonaV2SemanticProjectionGlobalContentValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    try:
        artifact_common.validate_plain_value(value, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    return value


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _strict_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be lowercase SHA-256")


def _require_frozen_raw(raw, *, expected_bytes, expected_sha256, label):
    if (
        type(raw) is not bytes
        or len(raw) != expected_bytes
        or not hmac.compare_digest(_sha256(raw), expected_sha256)
    ):
        _fail(f"{label} differs from its frozen canonical owner pin")


def _require_named_pin(raw, pins, name, *, label):
    expected = {key: (size, digest) for key, size, digest in pins}.get(name)
    if expected is None:
        _fail(f"{label} has no independent frozen pin")
    if (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail(f"{label} differs from its independent frozen canonical pin")


def _fresh_topology_owner():
    try:
        value = topology.build_topology_contract()
        result = topology.validate_topology_contract(value)
        raw = topology.canonical_json_bytes(value)
    except Exception as error:
        raise PersonaV2SemanticProjectionGlobalContentValidationError(
            "topology owner rebuild failed"
        ) from error
    if result is not True:
        _fail("topology owner validator did not return exact True")
    _require_frozen_raw(
        raw,
        expected_bytes=TOPOLOGY_OWNER_BYTES,
        expected_sha256=TOPOLOGY_OWNER_SHA256,
        label="topology owner",
    )
    return value, raw


def _fresh_realism_owner():
    try:
        value = realism.build_realism_profile()
        result = realism.validate_realism_profile(value)
        raw = realism.canonical_json_bytes(value)
    except Exception as error:
        raise PersonaV2SemanticProjectionGlobalContentValidationError(
            "realism owner rebuild failed"
        ) from error
    if result is not True:
        _fail("realism owner validator did not return exact True")
    _require_frozen_raw(
        raw,
        expected_bytes=REALISM_OWNER_BYTES,
        expected_sha256=REALISM_OWNER_SHA256,
        label="realism owner",
    )
    return value, raw


def _fresh_route_owner():
    try:
        value = route.build_route_affinity()
        result = route.validate_route_affinity(value)
        raw = route.canonical_json_bytes(value)
    except Exception as error:
        raise PersonaV2SemanticProjectionGlobalContentValidationError(
            "route owner rebuild failed"
        ) from error
    if result is not True:
        _fail("route owner validator did not return exact True")
    _require_frozen_raw(
        raw,
        expected_bytes=ROUTE_OWNER_BYTES,
        expected_sha256=ROUTE_OWNER_SHA256,
        label="route owner",
    )
    return value, raw


@functools.lru_cache(maxsize=1)
def _topology_owner_raw():
    return _fresh_topology_owner()[1]


@functools.lru_cache(maxsize=1)
def _realism_owner_raw():
    return _fresh_realism_owner()[1]


@functools.lru_cache(maxsize=1)
def _route_owner_raw():
    return _fresh_route_owner()[1]


def _topology_policy_projection(value):
    policy = value["policy"]
    rubric = policy["activity_unit_rubric"]
    return {
        "activity_unit_rubric": {
            "bands": copy.deepcopy(rubric["bands"]),
            "contributor_dimension": rubric["contributor_dimension"],
            "physical_dimension": rubric["physical_dimension"],
            "scale_max": rubric["scale_max"],
            "scale_min": rubric["scale_min"],
        },
        "contributor_minimum_bp": policy["contributor_minimum_bp"],
        "cross_persona_diversity": copy.deepcopy(
            policy["cross_persona_diversity"]
        ),
        "path_limits": {
            key: policy["canonical_limits"][key]
            for key in (
                "max_component_bytes",
                "max_load_basis_id_bytes",
                "max_path_bytes",
                "max_slot_bytes",
            )
        },
        "physical_minimum_bp": policy["physical_minimum_bp"],
        "primary_scope_count": policy["primary_scope_count"],
        "profile_chunk_targets": copy.deepcopy(policy["profile_chunk_targets"]),
        "profile_projection": copy.deepcopy(policy["profile_projection"]),
        "secondary_functional_slots": copy.deepcopy(
            policy["secondary_functional_slots"]
        ),
        "secondary_scope_count": policy["secondary_scope_count"],
        "source_bound": copy.deepcopy(policy["source_bound"]),
        "tiny_chunk_rule": policy["tiny_chunk_rule"],
        "weight_normalization": copy.deepcopy(policy["weight_normalization"]),
        "within_persona_path_safety": copy.deepcopy(
            policy["within_persona_path_safety"]
        ),
    }


def _topology_scope_axes(value):
    return [
        {
            "persona_id": persona["persona_id"],
            "scopes": [
                {
                    "ordinal": scope["ordinal"],
                    "scope_key": scope["scope_key"],
                }
                for scope in persona["scopes"]
            ],
        }
        for persona in value["personas"]
    ]


def _topology_source_fragment(value):
    return {
        "path_load_policy": _topology_policy_projection(value),
        "persona_topology_rows": copy.deepcopy(value["personas"]),
    }


def _realism_persona_projection(persona):
    return {
        key: copy.deepcopy(value)
        for key, value in persona.items()
        if key != "os_execution_mode"
    }


def _realism_policy_projection(value):
    excluded = {
        "membership_requires_future_intent_keys",
        "placement_weights_are_source_recipe_routing_hypotheses_only",
    }
    result = {
        key: copy.deepcopy(item)
        for key, item in value["policy"].items()
        if key not in excluded
    }
    result["os_semantics_are_declared_target_metadata_only"] = True
    return result


def _realism_source_fragment(value):
    return {
        "catalogs": copy.deepcopy(value["catalogs"]),
        "persona_realism_rows": [
            _realism_persona_projection(persona) for persona in value["personas"]
        ],
        "realism_policy": _realism_policy_projection(value),
        "suite_overlay_targets": copy.deepcopy(value["suite_overlay_targets"]),
    }


def _route_rows_fragment(value):
    return {"route_score_rows": copy.deepcopy(value["rows"])}


def _fragment_raw(value, *, label):
    return _canonical(value, label=label, maximum=MAX_FRAGMENT_BYTES)


@functools.lru_cache(maxsize=1)
def _topology_fragment_raw():
    value = _strict_loads(_topology_owner_raw(), label="cached topology owner")
    raw = _fragment_raw(
        _topology_source_fragment(value),
        label="independent topology path/load source fragment",
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-path-load-source-fragment",
        label="independent topology path/load source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _realism_fragment_raw():
    value = _strict_loads(_realism_owner_raw(), label="cached realism owner")
    raw = _fragment_raw(
        _realism_source_fragment(value),
        label="independent realism locale/security source fragment",
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "realism-locale-security-source-fragment",
        label="independent realism locale/security source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _route_rows_fragment_raw():
    value = _strict_loads(_route_owner_raw(), label="cached route owner")
    raw = _fragment_raw(
        _route_rows_fragment(value),
        label="independent route score row source fragment",
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "route-score-row-body",
        label="independent route score row source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _topology_scope_axis_raw():
    value = _strict_loads(_topology_owner_raw(), label="cached topology owner")
    raw = _fragment_raw(
        {"persona_scope_axes": _topology_scope_axes(value)},
        label="independent topology scope-axis source fragment",
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-scope-axis-body",
        label="independent topology scope-axis source fragment",
    )
    return raw


def _expected_topology_value():
    fragment = _strict_loads(
        _topology_fragment_raw(), label="topology source fragment"
    )
    personas = fragment["persona_topology_rows"]
    scopes = [scope for persona in personas for scope in persona["scopes"]]
    return {
        "artifact_kind": TOPOLOGY_PROJECTION_KIND,
        "artifact_schema": TOPOLOGY_PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_rules": {
            **fragment["path_load_policy"],
            "projection_excludes": list(_PROJECTION_EXCLUDES),
        },
        "content_sections": {"persona_topology_rows": personas},
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "summary": {
            "persona_count": len(personas),
            "primary_scope_count": sum(scope["kind"] == "primary" for scope in scopes),
            "scope_count": len(scopes),
            "secondary_scope_count": sum(
                scope["kind"] == "secondary" for scope in scopes
            ),
        },
    }


def _expected_realism_value():
    fragment = _strict_loads(
        _realism_fragment_raw(), label="realism source fragment"
    )
    personas = fragment["persona_realism_rows"]
    return {
        "artifact_kind": REALISM_PROJECTION_KIND,
        "artifact_schema": REALISM_PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_rules": {
            **fragment["realism_policy"],
            "projection_excludes": list(_PROJECTION_EXCLUDES),
        },
        "content_sections": {
            "catalogs": fragment["catalogs"],
            "persona_realism_rows": personas,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "summary": {
            "persona_count": len(personas),
            "suite_overlay_targets": fragment["suite_overlay_targets"],
        },
    }


def _expected_route_value():
    route_fragment = _strict_loads(
        _route_rows_fragment_raw(), label="route row source fragment"
    )
    axis_fragment = _strict_loads(
        _topology_scope_axis_raw(), label="topology axis source fragment"
    )
    rows = route_fragment["route_score_rows"]
    axes = axis_fragment["persona_scope_axes"]
    return {
        "artifact_kind": ROUTE_PROJECTION_KIND,
        "artifact_schema": ROUTE_PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_rules": {
            "hard_scope_eligibility_is_separate": True,
            "projection_excludes": list(_PROJECTION_EXCLUDES),
            "route_scores_are_soft_physical_placement_preferences": True,
            "row_order": "persona-then-family-then-variant-ascii",
            "score_domain": {
                "maximum": 4,
                "minimum": 0,
                "type": "exact-int-not-bool",
            },
            "score_zero_semantics": (
                "soft-no-specific-affinity-never-hard-eligibility-ban"
            ),
            "scope_axis_identity": (
                "persona-id-plus-scope-key-with-ordinal-as-serialization-position"
            ),
        },
        "content_sections": {
            "persona_scope_axes": axes,
            "route_score_rows": rows,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "summary": {
            "persona_count": len(axes),
            "route_score_cell_count": sum(
                len(row["scores_by_scope_ordinal"]) for row in rows
            ),
            "route_score_row_count": len(rows),
            "scope_axis_row_count": sum(len(row["scopes"]) for row in axes),
        },
    }


def _validate_projection_shape(value, *, kind, schema, label):
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        _fail(f"{label} top-level schema drifted")
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail(f"{label} identity drifted")

    def visit(node, path=()):
        if type(node) is list:
            for item in node:
                visit(item, path + ("[]",))
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            folded = key.replace("_", "-").lower()
            tokens = frozenset(token for token in folded.split("-") if token)
            if tokens & _FORBIDDEN_KEY_TOKENS:
                _fail(
                    f"{label} leaked forbidden metadata field at "
                    + ".".join(path + (key,))
                )
            visit(item, path + (key,))

    visit(value)


def _checked_expected_raw(value, *, kind, schema, label):
    _validate_projection_shape(value, kind=kind, schema=schema, label=label)
    raw = _canonical(value, label=label)
    if len(raw) > TARGET_PROJECTION_BYTES:
        _fail(f"{label} exceeds its 256-KiB target")
    return raw


@functools.lru_cache(maxsize=1)
def _expected_topology_raw():
    raw = _checked_expected_raw(
        _expected_topology_value(),
        kind=TOPOLOGY_PROJECTION_KIND,
        schema=TOPOLOGY_PROJECTION_SCHEMA,
        label="independent topology path/load content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        TOPOLOGY_CLASS_ID,
        label="independent topology path/load content projection",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _expected_realism_raw():
    raw = _checked_expected_raw(
        _expected_realism_value(),
        kind=REALISM_PROJECTION_KIND,
        schema=REALISM_PROJECTION_SCHEMA,
        label="independent realism locale/security content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        REALISM_CLASS_ID,
        label="independent realism locale/security content projection",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _expected_route_raw():
    raw = _checked_expected_raw(
        _expected_route_value(),
        kind=ROUTE_PROJECTION_KIND,
        schema=ROUTE_PROJECTION_SCHEMA,
        label="independent route score content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        ROUTE_CLASS_ID,
        label="independent route score content projection",
    )
    return raw


def _expected_raw(class_id):
    values = {
        TOPOLOGY_CLASS_ID: _expected_topology_raw,
        REALISM_CLASS_ID: _expected_realism_raw,
        ROUTE_CLASS_ID: _expected_route_raw,
    }
    if type(class_id) is not str or class_id not in values:
        _fail(f"unknown global content projection class: {class_id!r}")
    return values[class_id]()


def _projection_identity(class_id):
    identities = {
        TOPOLOGY_CLASS_ID: (
            TOPOLOGY_PROJECTION_KIND,
            TOPOLOGY_PROJECTION_SCHEMA,
            "topology-path-load-content-projector",
        ),
        REALISM_CLASS_ID: (
            REALISM_PROJECTION_KIND,
            REALISM_PROJECTION_SCHEMA,
            "realism-locale-security-content-projector",
        ),
        ROUTE_CLASS_ID: (
            ROUTE_PROJECTION_KIND,
            ROUTE_PROJECTION_SCHEMA,
            "route-scores-content-projector",
        ),
    }
    if type(class_id) is not str or class_id not in identities:
        _fail(f"unknown global content projection class: {class_id!r}")
    return identities[class_id]


def _full_owner_pin(
    *, artifact_kind, artifact_schema, canonical_bytes, owner_id, owner_role, sha256
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": 2,
        "body_framing": BODY_FRAMING,
        "canonical_bytes": canonical_bytes,
        "coordinates": {},
        "owner_id": owner_id,
        "owner_role": owner_role,
        "sha256": sha256,
    }


def _direct_pin(raw, *, direct_pin_id, direct_pin_role):
    return {
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "direct_pin_id": direct_pin_id,
        "direct_pin_role": direct_pin_role,
        "sha256": _sha256(raw),
    }


def _topology_owner_pin():
    return _full_owner_pin(
        artifact_kind="persona-pc-v2-topology",
        artifact_schema="kio.persona.pc-topology/v2",
        canonical_bytes=TOPOLOGY_OWNER_BYTES,
        owner_id="persona-v2-topology",
        owner_role="full-topology-owner-pin",
        sha256=TOPOLOGY_OWNER_SHA256,
    )


def _realism_owner_pin():
    return _full_owner_pin(
        artifact_kind="persona-pc-v2-realism-profile",
        artifact_schema="kio.persona.pc-realism-profile/v2",
        canonical_bytes=REALISM_OWNER_BYTES,
        owner_id="persona-v2-realism-profile",
        owner_role="full-realism-owner-pin",
        sha256=REALISM_OWNER_SHA256,
    )


def _route_owner_pin():
    return _full_owner_pin(
        artifact_kind="persona-pc-v2-route-affinity-matrix",
        artifact_schema="kio.persona.pc-route-affinity/v2",
        canonical_bytes=ROUTE_OWNER_BYTES,
        owner_id="persona-v2-route-affinity",
        owner_role="full-route-owner-pin",
        sha256=ROUTE_OWNER_SHA256,
    )


def _expected_material(class_id):
    kind, schema, projector_id = _projection_identity(class_id)
    if class_id == TOPOLOGY_CLASS_ID:
        owners = [_topology_owner_pin()]
        direct = [
            _direct_pin(
                _topology_fragment_raw(),
                direct_pin_id="topology-path-load-source-fragment",
                direct_pin_role="topology-path-load-source-fragment",
            )
        ]
    elif class_id == REALISM_CLASS_ID:
        owners = [_realism_owner_pin()]
        direct = [
            _direct_pin(
                _realism_fragment_raw(),
                direct_pin_id="realism-locale-security-source-fragment",
                direct_pin_role="realism-locale-security-source-fragment",
            )
        ]
    else:
        owners = [_route_owner_pin(), _topology_owner_pin()]
        direct = [
            _direct_pin(
                _route_rows_fragment_raw(),
                direct_pin_id="route-score-row-body",
                direct_pin_role="route-score-row-body",
            ),
            _direct_pin(
                _topology_scope_axis_raw(),
                direct_pin_id="topology-scope-axis-body",
                direct_pin_role="topology-scope-axis-body",
            ),
        ]
    value = {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "body": bytes(_expected_raw(class_id)),
        "body_framing": BODY_FRAMING,
        "class_id": class_id,
        "coordinates": {},
        "direct_body_pins": direct,
        "full_owner_pins": owners,
        "projector": {
            "projector_id": projector_id,
            "projector_version": 1,
        },
    }
    if set(value) != MATERIAL_FIELDS:
        _fail("independent global projection material schema drifted")
    return value


def iter_expected_global_content_projection_materials():
    """Yield detached independently reconstructed integration materials."""

    for class_id in CLASS_ORDER:
        yield copy.deepcopy(_expected_material(class_id))


def expected_projection_body_bytes(class_id, coordinates):
    if type(coordinates) is not dict or coordinates:
        _fail("global content projection coordinates must be the empty object")
    return bytes(_expected_raw(class_id))


def _current_topology_fragment(value):
    return _fragment_raw(
        _topology_source_fragment(value),
        label="live topology path/load source fragment",
    )


def _current_realism_fragment(value):
    return _fragment_raw(
        _realism_source_fragment(value),
        label="live realism locale/security source fragment",
    )


def _current_route_rows_fragment(value):
    return _fragment_raw(
        _route_rows_fragment(value),
        label="live route score row source fragment",
    )


def _current_topology_axis_fragment(value):
    return _fragment_raw(
        {"persona_scope_axes": _topology_scope_axes(value)},
        label="live topology scope-axis source fragment",
    )


def _reauthenticate_class(class_id):
    if class_id == TOPOLOGY_CLASS_ID:
        topology_value, _ = _fresh_topology_owner()
        _require_named_pin(
            _current_topology_fragment(topology_value),
            EXPECTED_DIRECT_FRAGMENT_PINS,
            "topology-path-load-source-fragment",
            label="topology path/load source direct fragment",
        )
    elif class_id == REALISM_CLASS_ID:
        realism_value, _ = _fresh_realism_owner()
        _require_named_pin(
            _current_realism_fragment(realism_value),
            EXPECTED_DIRECT_FRAGMENT_PINS,
            "realism-locale-security-source-fragment",
            label="realism locale/security source direct fragment",
        )
    elif class_id == ROUTE_CLASS_ID:
        route_value, _ = _fresh_route_owner()
        topology_value, _ = _fresh_topology_owner()
        _require_named_pin(
            _current_route_rows_fragment(route_value),
            EXPECTED_DIRECT_FRAGMENT_PINS,
            "route-score-row-body",
            label="route score row source direct fragment",
        )
        _require_named_pin(
            _current_topology_axis_fragment(topology_value),
            EXPECTED_DIRECT_FRAGMENT_PINS,
            "topology-scope-axis-body",
            label="topology scope-axis source direct fragment",
        )
    else:
        _fail(f"unknown global content projection class: {class_id!r}")


def reauthenticate_all_projection_owners():
    """Re-read every live owner/direct body once; never trust cached owner state."""

    topology_value, _ = _fresh_topology_owner()
    realism_value, _ = _fresh_realism_owner()
    route_value, _ = _fresh_route_owner()
    _require_named_pin(
        _current_topology_fragment(topology_value),
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-path-load-source-fragment",
        label="topology path/load source direct fragment",
    )
    _require_named_pin(
        _current_realism_fragment(realism_value),
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "realism-locale-security-source-fragment",
        label="realism locale/security source direct fragment",
    )
    _require_named_pin(
        _current_route_rows_fragment(route_value),
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "route-score-row-body",
        label="route score row source direct fragment",
    )
    _require_named_pin(
        _current_topology_axis_fragment(topology_value),
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-scope-axis-body",
        label="topology scope-axis source direct fragment",
    )
    return True


def _validate_body_without_reauth(class_id, body):
    if type(body) is not bytes:
        _fail("projection body must be exact built-in bytes")
    if len(body) > MAX_PROJECTION_BYTES:
        _fail("projection body exceeds its hard byte cap")
    expected = _expected_raw(class_id)
    if len(body) > TARGET_PROJECTION_BYTES:
        _fail("projection body exceeds its current 256-KiB target")
    value = _strict_loads(body, label=f"{class_id} projection body")
    kind, schema, _ = _projection_identity(class_id)
    _validate_projection_shape(
        value,
        kind=kind,
        schema=schema,
        label=f"{class_id} projection body",
    )
    if not hmac.compare_digest(
        body,
        _canonical(value, label=f"{class_id} projection body"),
    ):
        _fail("projection body is not compact sorted canonical JSON")
    if not hmac.compare_digest(body, expected):
        _fail("projection body differs from independent reconstruction")
    return True


def validate_projection_body(class_id, coordinates, body):
    """Validate one body and live-repin only the owners needed by that class."""

    if type(coordinates) is not dict or coordinates:
        _fail("global content projection coordinates must be the empty object")
    _reauthenticate_class(class_id)
    try:
        return _validate_body_without_reauth(class_id, body)
    finally:
        _reauthenticate_class(class_id)


def _schema_to_class(schema):
    values = {
        TOPOLOGY_PROJECTION_SCHEMA: TOPOLOGY_CLASS_ID,
        REALISM_PROJECTION_SCHEMA: REALISM_CLASS_ID,
        ROUTE_PROJECTION_SCHEMA: ROUTE_CLASS_ID,
    }
    if type(schema) is not str or schema not in values:
        _fail("global content projection uses an unknown schema")
    return values[schema]


def _snapshot_projection(value, *, expected_schema):
    if type(value) is not dict or value.get("artifact_schema") != expected_schema:
        _fail("global content projection opening image uses the wrong schema")
    opening_raw = _canonical(value, label="global content projection opening image")
    snapshot = _strict_loads(opening_raw, label="global content projection opening image")
    if not hmac.compare_digest(
        opening_raw,
        _canonical(snapshot, label="global content projection detached opening image"),
    ):
        _fail("global content projection opening image is not canonical JSON")
    return snapshot, opening_raw


def _validate_projection_object(value, *, class_id, expected_schema):
    snapshot, opening_raw = _snapshot_projection(
        value,
        expected_schema=expected_schema,
    )
    owners_opened = False
    try:
        _reauthenticate_class(class_id)
        owners_opened = True
        _validate_body_without_reauth(class_id, opening_raw)
    finally:
        postflight_error = None
        if owners_opened:
            try:
                _reauthenticate_class(class_id)
            except Exception as error:
                postflight_error = error
        try:
            current_raw = _canonical(
                value,
                label="global content projection live image",
            )
            if not hmac.compare_digest(opening_raw, current_raw):
                _fail("caller-owned projection mutated during validation")
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


def validate_topology_path_load_content_projection(value):
    return _validate_projection_object(
        value,
        class_id=TOPOLOGY_CLASS_ID,
        expected_schema=TOPOLOGY_PROJECTION_SCHEMA,
    )


def validate_realism_locale_security_content_projection(value):
    return _validate_projection_object(
        value,
        class_id=REALISM_CLASS_ID,
        expected_schema=REALISM_PROJECTION_SCHEMA,
    )


def validate_route_scores_content_projection(value):
    return _validate_projection_object(
        value,
        class_id=ROUTE_CLASS_ID,
        expected_schema=ROUTE_PROJECTION_SCHEMA,
    )


def _validate_pin(pin, *, fields, label):
    if (
        type(pin) is not dict
        or any(type(key) is not str for key in pin)
        or set(pin) != fields
    ):
        _fail(f"{label} schema drifted")
    try:
        artifact_common.validate_plain_value(pin, label=label)
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    string_fields = fields - {
        "artifact_schema_version",
        "canonical_bytes",
        "coordinates",
    }
    if any(type(pin.get(field)) is not str for field in string_fields):
        _fail(f"{label} string field type drifted")
    if "artifact_schema_version" in fields and (
        type(pin.get("artifact_schema_version")) is not int
        or pin["artifact_schema_version"] <= 0
    ):
        _fail(f"{label} schema version is invalid")
    if "coordinates" in fields and (
        type(pin.get("coordinates")) is not dict or pin["coordinates"] != {}
    ):
        _fail(f"{label} coordinates must be empty")
    if pin.get("body_framing") != BODY_FRAMING:
        _fail(f"{label} framing drifted")
    if (
        type(pin.get("canonical_bytes")) is not int
        or type(pin["canonical_bytes"]) is bool
        or pin["canonical_bytes"] <= 0
    ):
        _fail(f"{label} canonical byte count is invalid")
    _require_sha256(pin.get("sha256"), label=f"{label} SHA-256")


def _validate_material_shape(material, *, expected_class):
    if (
        type(material) is not dict
        or any(type(key) is not str for key in material)
        or set(material) != MATERIAL_FIELDS
    ):
        _fail("global content projection material schema drifted")
    kind, schema, projector_id = _projection_identity(expected_class)
    if (
        type(material.get("class_id")) is not str
        or material.get("class_id") != expected_class
        or type(material.get("coordinates")) is not dict
        or material.get("coordinates") != {}
        or type(material.get("artifact_kind")) is not str
        or material.get("artifact_kind") != kind
        or type(material.get("artifact_schema")) is not str
        or material.get("artifact_schema") != schema
        or type(material.get("artifact_schema_version")) is not int
        or material.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or type(material.get("body_framing")) is not str
        or material.get("body_framing") != BODY_FRAMING
        or type(material.get("body")) is not bytes
        or len(material["body"]) > MAX_PROJECTION_BYTES
    ):
        _fail("global content projection material identity drifted")
    projector = material.get("projector")
    if (
        type(projector) is not dict
        or any(type(key) is not str for key in projector)
        or set(projector) != PROJECTOR_FIELDS
        or type(projector.get("projector_id")) is not str
        or projector.get("projector_id") != projector_id
        or type(projector.get("projector_version")) is not int
        or projector.get("projector_version") != 1
    ):
        _fail("global content projection projector identity drifted")
    try:
        artifact_common.validate_plain_value(
            projector,
            label="global content projection projector",
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))
    expected_owner_count = 2 if expected_class == ROUTE_CLASS_ID else 1
    expected_direct_count = 2 if expected_class == ROUTE_CLASS_ID else 1
    owners = material.get("full_owner_pins")
    direct = material.get("direct_body_pins")
    if type(owners) is not list or len(owners) != expected_owner_count:
        _fail("global projection full-owner cardinality drifted")
    if type(direct) is not list or len(direct) != expected_direct_count:
        _fail("global projection direct-pin cardinality drifted")
    for owner in owners:
        _validate_pin(owner, fields=FULL_OWNER_PIN_FIELDS, label="full owner pin")
        if type(owner.get("coordinates")) is not dict or owner.get("coordinates") != {}:
            _fail("global projection full-owner coordinates must be empty")
    for pin in direct:
        _validate_pin(pin, fields=DIRECT_PIN_FIELDS, label="direct body pin")


def _material_image(materials):
    if type(materials) is not list or len(materials) != len(CLASS_ORDER):
        _fail("global content projection materials must be an exact three-row list")
    rows = []
    for material, expected_class in zip(materials, CLASS_ORDER, strict=True):
        _validate_material_shape(material, expected_class=expected_class)
        rows.append(
            {
                key: material[key]
                for key in sorted(MATERIAL_FIELDS)
                if key != "body"
            }
        )
        rows[-1]["body_pin"] = {
            "canonical_bytes": len(material["body"]),
            "sha256": _sha256(material["body"]),
        }
    return _canonical(
        rows,
        label="global content projection material opening image",
        maximum=MAX_MATERIAL_IMAGE_BYTES,
    )


def _snapshot_materials(materials):
    opening_raw = _material_image(materials)
    image = _strict_loads(
        opening_raw,
        label="global content projection material opening image",
    )
    if type(image) is not list or len(image) != len(CLASS_ORDER):
        _fail("global content projection material opening image drifted")
    detached = []
    try:
        for index, (row, expected_class) in enumerate(
            zip(image, CLASS_ORDER, strict=True)
        ):
            if type(row) is not dict or "body_pin" not in row:
                _fail("global content projection material opening row drifted")
            body_pin = row.pop("body_pin")
            body = materials[index].get("body")
            if (
                type(body_pin) is not dict
                or set(body_pin) != {"canonical_bytes", "sha256"}
                or type(body) is not bytes
                or body_pin.get("canonical_bytes") != len(body)
                or body_pin.get("sha256") != _sha256(body)
            ):
                _fail("global content projection material body changed during opening")
            row["body"] = body
            _validate_material_shape(row, expected_class=expected_class)
            detached.append(row)
    except (IndexError, KeyError, RuntimeError) as error:
        raise PersonaV2SemanticProjectionGlobalContentValidationError(
            "caller-owned global projection materials mutated during opening"
        ) from error
    detached_raw = _material_image(detached)
    if not hmac.compare_digest(opening_raw, detached_raw):
        _fail("caller-owned global projection materials mutated during opening")
    current_raw = _material_image(materials)
    if not hmac.compare_digest(opening_raw, current_raw):
        _fail("caller-owned global projection materials mutated during opening")
    return detached, opening_raw


def _reauth_materials_target(materials, opening_raw):
    current = _material_image(materials)
    if not hmac.compare_digest(current, opening_raw):
        _fail("caller-owned global projection materials mutated during validation")


def _provider_descriptor(material):
    return {
        key: copy.deepcopy(value)
        for key, value in material.items()
        if key != "body"
    }


def validate_global_content_projection_materials(
    materials,
    projection_body_provider=None,
):
    """Validate exact materials and replay each untrusted body provider twice."""

    snapshot, opening_raw = _snapshot_materials(materials)
    expected = list(iter_expected_global_content_projection_materials())
    if not _strict_equal(snapshot, expected):
        _fail("global content projection materials differ from independent reconstruction")
    provider = projection_body_provider
    if provider is None:
        provider = lambda descriptor: expected_projection_body_bytes(
            descriptor["class_id"], descriptor["coordinates"]
        )
    if not callable(provider):
        _fail("global content projection body provider must be callable")

    owners_opened = False
    try:
        reauthenticate_all_projection_owners()
        owners_opened = True
        for material in snapshot:
            descriptor = _provider_descriptor(material)

            def post_callback():
                _reauth_materials_target(materials, opening_raw)
                _reauthenticate_class(material["class_id"])

            try:
                first = provider(copy.deepcopy(descriptor))
            finally:
                post_callback()
            _validate_body_without_reauth(material["class_id"], first)
            try:
                replay = provider(copy.deepcopy(descriptor))
            finally:
                post_callback()
            if type(replay) is not bytes:
                _fail("projection provider replay must return exact built-in bytes")
            if not hmac.compare_digest(first, replay):
                _fail("global content projection provider replay is nondeterministic")
    finally:
        postflight_error = None
        if owners_opened:
            try:
                reauthenticate_all_projection_owners()
            except Exception as error:
                postflight_error = error
        try:
            _reauth_materials_target(materials, opening_raw)
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "BODY_FRAMING",
    "CLASS_ORDER",
    "EXPECTED_DIRECT_FRAGMENT_PINS",
    "EXPECTED_PROJECTION_PINS",
    "MATERIAL_FIELDS",
    "MAX_PROJECTION_BYTES",
    "REALISM_CLASS_ID",
    "REALISM_PROJECTION_KIND",
    "REALISM_PROJECTION_SCHEMA",
    "ROUTE_CLASS_ID",
    "ROUTE_PROJECTION_KIND",
    "ROUTE_PROJECTION_SCHEMA",
    "TARGET_PROJECTION_BYTES",
    "TOPOLOGY_CLASS_ID",
    "TOPOLOGY_PROJECTION_KIND",
    "TOPOLOGY_PROJECTION_SCHEMA",
    "PersonaV2SemanticProjectionGlobalContentValidationError",
    "expected_projection_body_bytes",
    "iter_expected_global_content_projection_materials",
    "reauthenticate_all_projection_owners",
    "validate_global_content_projection_materials",
    "validate_projection_body",
    "validate_realism_locale_security_content_projection",
    "validate_route_scores_content_projection",
    "validate_topology_path_load_content_projection",
]
