"""Content-only global semantic projections for persona-PC fidelity v2.

This module projects three already-frozen planning artifacts into namespace-safe
content bodies.  The bodies deliberately omit full-owner digests, authority,
completion/blocker/review state, query/evaluation material, solver output, and
runtime observations.  Derivation evidence is returned separately by
``iter_global_content_projection_materials``.

The Decision-150 derivation inventory remains unchanged.  These standalone
projections are inputs to a later, versioned complete inventory.
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

TOPOLOGY_CLASS_ID = "topology-path-load"
REALISM_CLASS_ID = "realism-locale-security"
ROUTE_CLASS_ID = "route-scores"
CLASS_ORDER = (TOPOLOGY_CLASS_ID, REALISM_CLASS_ID, ROUTE_CLASS_ID)

TOPOLOGY_PROJECTION_SCHEMA = (
    "kcs.persona.pc-topology-path-load-content-projection/v1"
)
TOPOLOGY_PROJECTION_KIND = (
    "persona-pc-v2-topology-path-load-content-projection"
)
REALISM_PROJECTION_SCHEMA = (
    "kcs.persona.pc-realism-locale-security-content-projection/v1"
)
REALISM_PROJECTION_KIND = (
    "persona-pc-v2-realism-locale-security-content-projection"
)
ROUTE_PROJECTION_SCHEMA = "kcs.persona.pc-route-scores-content-projection/v1"
ROUTE_PROJECTION_KIND = "persona-pc-v2-route-scores-content-projection"

TOPOLOGY_OWNER_BYTES = 134_195
TOPOLOGY_OWNER_SHA256 = (
    "204c9a136438c0dfff3718549c2fcb6009e6ccbe9debdd0cfe54bfaa4290b68f"
)
REALISM_OWNER_BYTES = 36_811
REALISM_OWNER_SHA256 = (
    "a32bbb0fd7c88c57205454d8555163ad97b2b1a3024e5a5d7f7234bf56766f05"
)
ROUTE_OWNER_BYTES = 70_626
ROUTE_OWNER_SHA256 = (
    "e8a401193fc751ed3d7b2a47e3661202835579df8700392ce9fdfd30ad07c790"
)

EXPECTED_PROJECTION_PINS = (
    (
        TOPOLOGY_CLASS_ID,
        133_187,
        "32b71dae205988d9671d6c3635bbe9690a03af4db363229c413f79c457375483",
    ),
    (
        REALISM_CLASS_ID,
        32_762,
        "9bf892c4cf71608c167e5dfcf168cad4fff125293689b178a5acc57dfb30130d",
    ),
    (
        ROUTE_CLASS_ID,
        88_085,
        "c088ba4cfabffd9474afee35d0874bfae45fd07a801ccd763bfe97b6d17ce535",
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

_PROJECTION_EXCLUDES = [
    "authority-completion-blocker-and-review-state",
    "derivation-receipts-and-full-owner-digests",
    "query-oracle-answer-distractor-and-evaluation-fields",
    "runtime-observations-and-capacity-state",
    "solver-solution-final-identifiers-and-compiled-history",
]


class PersonaV2SemanticProjectionGlobalContentError(ValueError):
    """Raised when a global content projection or derivation pin is invalid."""


def _fail(message):
    raise PersonaV2SemanticProjectionGlobalContentError(message)


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


def _detached_from_raw(raw):
    value = json.loads(raw.decode("utf-8", "strict"))
    if type(value) is not dict:
        _fail("cached global projection must decode to an object")
    return value


def _require_owner_pin(raw, *, expected_bytes, expected_sha256, label):
    if len(raw) != expected_bytes or _sha256(raw) != expected_sha256:
        _fail(f"{label} differs from its frozen canonical owner pin")


def _require_named_pin(raw, pins, name, *, label):
    expected = {key: (size, digest) for key, size, digest in pins}.get(name)
    if expected is None:
        _fail(f"{label} has no frozen pin")
    if len(raw) != expected[0] or _sha256(raw) != expected[1]:
        _fail(f"{label} differs from its frozen canonical pin")


def _fresh_topology_owner():
    value = topology.build_topology_contract()
    if topology.validate_topology_contract(value) is not True:
        _fail("topology owner validator did not return exact True")
    raw = topology.canonical_json_bytes(value)
    _require_owner_pin(
        raw,
        expected_bytes=TOPOLOGY_OWNER_BYTES,
        expected_sha256=TOPOLOGY_OWNER_SHA256,
        label="topology owner",
    )
    return value, raw


def _fresh_realism_owner():
    value = realism.build_realism_profile()
    if realism.validate_realism_profile(value) is not True:
        _fail("realism owner validator did not return exact True")
    raw = realism.canonical_json_bytes(value)
    _require_owner_pin(
        raw,
        expected_bytes=REALISM_OWNER_BYTES,
        expected_sha256=REALISM_OWNER_SHA256,
        label="realism owner",
    )
    return value, raw


def _fresh_route_owner():
    value = route.build_route_affinity()
    if route.validate_route_affinity(value) is not True:
        _fail("route owner validator did not return exact True")
    raw = route.canonical_json_bytes(value)
    _require_owner_pin(
        raw,
        expected_bytes=ROUTE_OWNER_BYTES,
        expected_sha256=ROUTE_OWNER_SHA256,
        label="route owner",
    )
    return value, raw


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


@functools.lru_cache(maxsize=1)
def _topology_owner_raw():
    return _fresh_topology_owner()[1]


@functools.lru_cache(maxsize=1)
def _realism_owner_raw():
    return _fresh_realism_owner()[1]


@functools.lru_cache(maxsize=1)
def _route_owner_raw():
    return _fresh_route_owner()[1]


@functools.lru_cache(maxsize=1)
def _topology_fragment_raw():
    value = _detached_from_raw(_topology_owner_raw())
    raw = _canonical(
        _topology_source_fragment(value),
        label="topology path/load source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-path-load-source-fragment",
        label="topology path/load source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _realism_fragment_raw():
    value = _detached_from_raw(_realism_owner_raw())
    raw = _canonical(
        _realism_source_fragment(value),
        label="realism locale/security source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "realism-locale-security-source-fragment",
        label="realism locale/security source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _route_rows_fragment_raw():
    value = _detached_from_raw(_route_owner_raw())
    raw = _canonical(
        _route_rows_fragment(value),
        label="route score row source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "route-score-row-body",
        label="route score row source fragment",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _topology_scope_axis_raw():
    value = _detached_from_raw(_topology_owner_raw())
    raw = _canonical(
        {"persona_scope_axes": _topology_scope_axes(value)},
        label="topology scope-axis source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    _require_named_pin(
        raw,
        EXPECTED_DIRECT_FRAGMENT_PINS,
        "topology-scope-axis-body",
        label="topology scope-axis source fragment",
    )
    return raw


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


def _topology_projection_value():
    fragment = json.loads(_topology_fragment_raw().decode("utf-8"))
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


def _realism_projection_value():
    fragment = json.loads(_realism_fragment_raw().decode("utf-8"))
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


def _route_projection_value():
    route_fragment = json.loads(_route_rows_fragment_raw().decode("utf-8"))
    axis_fragment = json.loads(_topology_scope_axis_raw().decode("utf-8"))
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
                "maximum": route.SCORE_MAXIMUM,
                "minimum": route.SCORE_MINIMUM,
                "type": "exact-int-not-bool",
            },
            "score_zero_semantics": route.SCORE_ZERO_SEMANTICS,
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


def _checked_projection_raw(value, *, label):
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        _fail(f"{label} top-level schema drifted")
    raw = _canonical(value, label=label)
    if len(raw) > TARGET_PROJECTION_BYTES:
        _fail(f"{label} exceeds its 256-KiB target")
    return raw


@functools.lru_cache(maxsize=1)
def _topology_projection_raw():
    raw = _checked_projection_raw(
        _topology_projection_value(),
        label="topology path/load content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        TOPOLOGY_CLASS_ID,
        label="topology path/load content projection",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _realism_projection_raw():
    raw = _checked_projection_raw(
        _realism_projection_value(),
        label="realism locale/security content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        REALISM_CLASS_ID,
        label="realism locale/security content projection",
    )
    return raw


@functools.lru_cache(maxsize=1)
def _route_projection_raw():
    raw = _checked_projection_raw(
        _route_projection_value(),
        label="route score content projection",
    )
    _require_named_pin(
        raw,
        EXPECTED_PROJECTION_PINS,
        ROUTE_CLASS_ID,
        label="route score content projection",
    )
    return raw


def canonical_json_bytes(value):
    if type(value) is not dict:
        _fail("global content projection must be an object")
    labels = {
        TOPOLOGY_PROJECTION_SCHEMA: "topology path/load content projection",
        REALISM_PROJECTION_SCHEMA: "realism locale/security content projection",
        ROUTE_PROJECTION_SCHEMA: "route score content projection",
    }
    schema = value.get("artifact_schema")
    if schema not in labels:
        _fail("global content projection uses an unknown schema")
    return _canonical(value, label=labels[schema])


def build_topology_path_load_content_projection():
    return _detached_from_raw(_topology_projection_raw())


def build_realism_locale_security_content_projection():
    return _detached_from_raw(_realism_projection_raw())


def build_route_scores_content_projection():
    return _detached_from_raw(_route_projection_raw())


def _independent_validator():
    try:
        from . import persona_v2_semantic_projection_global_content_validator
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_semantic_projection_global_content_validator
    return persona_v2_semantic_projection_global_content_validator


def validate_topology_path_load_content_projection(value):
    return _independent_validator().validate_topology_path_load_content_projection(
        value
    )


def validate_realism_locale_security_content_projection(value):
    return _independent_validator().validate_realism_locale_security_content_projection(
        value
    )


def validate_route_scores_content_projection(value):
    return _independent_validator().validate_route_scores_content_projection(value)


def global_content_projection_sha256(value):
    validators = {
        TOPOLOGY_PROJECTION_SCHEMA: validate_topology_path_load_content_projection,
        REALISM_PROJECTION_SCHEMA: validate_realism_locale_security_content_projection,
        ROUTE_PROJECTION_SCHEMA: validate_route_scores_content_projection,
    }
    if type(value) is not dict or value.get("artifact_schema") not in validators:
        _fail("global content projection SHA requires a known projection object")
    opening_raw = canonical_json_bytes(value)
    opening = _detached_from_raw(opening_raw)
    if validators[value["artifact_schema"]](opening) is not True:
        _fail("independent global content projection validator did not return True")
    current_raw = canonical_json_bytes(value)
    if not hmac.compare_digest(opening_raw, current_raw):
        _fail("caller-owned projection mutated during SHA authentication")
    return _sha256(opening_raw)


def projection_body_bytes(class_id, coordinates):
    """Rebuild exactly one projection body without materializing the other two."""

    if type(coordinates) is not dict or coordinates:
        _fail("global content projection coordinates must be the empty object")
    bodies = {
        TOPOLOGY_CLASS_ID: _topology_projection_raw,
        REALISM_CLASS_ID: _realism_projection_raw,
        ROUTE_CLASS_ID: _route_projection_raw,
    }
    if type(class_id) is not str or class_id not in bodies:
        _fail(f"unknown global content projection class: {class_id!r}")
    return bytes(bodies[class_id]())


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
        artifact_kind=topology.ARTIFACT_KIND,
        artifact_schema=topology.ARTIFACT_SCHEMA,
        canonical_bytes=TOPOLOGY_OWNER_BYTES,
        owner_id="persona-v2-topology",
        owner_role="full-topology-owner-pin",
        sha256=TOPOLOGY_OWNER_SHA256,
    )


def _realism_owner_pin():
    return _full_owner_pin(
        artifact_kind=realism.ARTIFACT_KIND,
        artifact_schema=realism.ARTIFACT_SCHEMA,
        canonical_bytes=REALISM_OWNER_BYTES,
        owner_id="persona-v2-realism-profile",
        owner_role="full-realism-owner-pin",
        sha256=REALISM_OWNER_SHA256,
    )


def _route_owner_pin():
    return _full_owner_pin(
        artifact_kind=route.ARTIFACT_KIND,
        artifact_schema=route.ARTIFACT_SCHEMA,
        canonical_bytes=ROUTE_OWNER_BYTES,
        owner_id="persona-v2-route-affinity",
        owner_role="full-route-owner-pin",
        sha256=ROUTE_OWNER_SHA256,
    )


def _material(class_id):
    kind, schema, projector_id = _projection_identity(class_id)
    body = projection_body_bytes(class_id, {})
    if class_id == TOPOLOGY_CLASS_ID:
        full_owners = [_topology_owner_pin()]
        direct_pins = [
            _direct_pin(
                _topology_fragment_raw(),
                direct_pin_id="topology-path-load-source-fragment",
                direct_pin_role="topology-path-load-source-fragment",
            )
        ]
    elif class_id == REALISM_CLASS_ID:
        full_owners = [_realism_owner_pin()]
        direct_pins = [
            _direct_pin(
                _realism_fragment_raw(),
                direct_pin_id="realism-locale-security-source-fragment",
                direct_pin_role="realism-locale-security-source-fragment",
            )
        ]
    else:
        full_owners = [_route_owner_pin(), _topology_owner_pin()]
        direct_pins = [
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
        "body": bytes(body),
        "body_framing": BODY_FRAMING,
        "class_id": class_id,
        "coordinates": {},
        "direct_body_pins": direct_pins,
        "full_owner_pins": full_owners,
        "projector": {
            "projector_id": projector_id,
            "projector_version": 1,
        },
    }
    if set(value) != MATERIAL_FIELDS:
        _fail("global content projection material schema drifted")
    return value


def iter_global_content_projection_materials():
    """Yield detached integration materials in minimum-class canonical order."""

    for class_id in CLASS_ORDER:
        yield copy.deepcopy(_material(class_id))


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "BODY_FRAMING",
    "CLASS_ORDER",
    "EXPECTED_DIRECT_FRAGMENT_PINS",
    "EXPECTED_PROJECTION_PINS",
    "MATERIAL_FIELDS",
    "MAX_FRAGMENT_BYTES",
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
    "PersonaV2SemanticProjectionGlobalContentError",
    "build_realism_locale_security_content_projection",
    "build_route_scores_content_projection",
    "build_topology_path_load_content_projection",
    "canonical_json_bytes",
    "global_content_projection_sha256",
    "iter_global_content_projection_materials",
    "projection_body_bytes",
    "validate_realism_locale_security_content_projection",
    "validate_route_scores_content_projection",
    "validate_topology_path_load_content_projection",
]
