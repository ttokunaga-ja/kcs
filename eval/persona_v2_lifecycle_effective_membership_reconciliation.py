"""Effective W0 lifecycle fact-membership reconciliation for persona-PC v2.

This package is the single sparse lifecycle membership owner over the immutable
203,000-source W0 inventory.  Expanded W0 membership, event-created witness
lineage, and the witness inverted index are bounded verification views and are
never persisted by this artifact.

The artifact is pre-solver and strictly non-authorizing.  It contains no
query/oracle payload, final physical identifiers, paths, quotas, observations,
or execution authority.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    from . import persona_v2_source_inventory_package as source_package
    from . import persona_v2_source_matched_lifecycle_inventory as matched_lifecycle
    from . import persona_v2_source_semantic_membership_package as source_semantic
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_lifecycle_coverage_catalog as lifecycle_coverage
    import persona_v2_source_inventory_package as source_package
    import persona_v2_source_matched_lifecycle_inventory as matched_lifecycle
    import persona_v2_source_semantic_membership_package as source_semantic


ORIGIN_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-origin-manifest/v1"
)
PROFILE_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-profile-manifest/v1"
)
SUITE_SCHEMA = "kio.persona.pc-lifecycle-effective-membership-reconciliation/v1"
PROJECTION_SCHEMA = (
    "kio.persona.pc-lifecycle-effective-membership-content-projection/v1"
)
ARTIFACT_SCHEMA_VERSION = 1

ORIGIN_KIND = "persona-pc-v2-lifecycle-effective-membership-origin-manifest"
PROFILE_KIND = "persona-pc-v2-lifecycle-effective-membership-profile-manifest"
SUITE_KIND = "persona-pc-v2-lifecycle-effective-membership-reconciliation"
PROJECTION_KIND = (
    "persona-pc-v2-lifecycle-effective-membership-content-projection"
)

ORIGIN_ORDER = source_package.ORIGIN_ORDER
PROFILE_ORDER = source_package.PROFILE_ORDER

EXPECTED_SOURCE_COUNT = 203_000
EXPECTED_SHARD_RECEIPT_COUNT = 73
EXPECTED_PRIMARY_OVERRIDE_COUNT = 2_000
EXPECTED_COMPANION_MIRROR_COUNT = 200
EXPECTED_TYPED_WITNESS_COUNT = 300
EXPECTED_COMPACT_ROW_COUNT = 2_573
EXPECTED_EVENT_CREATED_LINEAGE_COUNT = 3_630
EXPECTED_INVERTED_WITNESS_COUNT = 300
EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT = 600
EXPECTED_PRESENT_FACT_REFERENCE_COUNT = 1_033_680
EXPECTED_SUITE_CANONICAL_BYTES = 69_195
EXPECTED_SUITE_SHA256 = (
    "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29"
)
EXPECTED_MAX_ORIGIN_MANIFEST_BYTES = 5_592
EXPECTED_MAX_PROFILE_MANIFEST_BYTES = 3_301
# 2026-07-28 に 103_864 から動いた。改名で `_domain_key` の前置詞が変わり
# cross-format の照合結果が変わったため、最大の content projection が別の
# ペルソナのものになった。観測された最大値であって選んだ閾値ではないので、
# 実測に合わせる。同じ組の他の 6 つは動いていない。
EXPECTED_MAX_CONTENT_PROJECTION_BYTES = 103_840
EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 1_136
EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 913
EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF = 571
EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF = 600
EXPECTED_P01_PILOT_COMPACT_BODY_BYTES = 127_252
EXPECTED_P01_PILOT_COMPACT_BODY_SHA256 = (
    "b4dc476b51916e67d2e6c021f9a50a319611fe3840719c5de10ba4fd26f0404d"
)
EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES = 2_460
EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256 = (
    "aefbfd79351fce4cd369e7fbf548db1734882e14f14ec524bb4499acc036234d"
)
EXPECTED_P01_CONTENT_PROJECTION_BYTES = 103_439
EXPECTED_P01_CONTENT_PROJECTION_SHA256 = (
    "d620a63b9762cf6119d795845c5b1533207ced29ae97fbb6ab3765a966d07f5e"
)
EXPECTED_W0_MODE_COUNTS = {
    "base-inheritance": 200_800,
    "companion-mirror": 200,
    "graph-normal-plus-witness": 300,
    "graph-normal": 1_700,
}
EXPECTED_W0_FACT_DISTRIBUTION = {
    "conflict-branch": 3_120,
    "empty": 73_350,
    "graph-normal-only": 126_130,
    "graph-normal-plus-witness": 300,
    "singleton": 100,
}

MAX_ORIGIN_BODY_BYTES = 4 * 2**20
MAX_ORIGIN_ROWS = 4_096
MAX_ORIGIN_MANIFEST_BYTES = 256 * 1024
MAX_PROFILE_MANIFEST_BYTES = 256 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_CONTENT_PROJECTION_BYTES = 384 * 1024
TARGET_CONTENT_PROJECTION_BYTES = 256 * 1024
MAX_COMPACT_ROW_BYTES_INCLUDING_LF = 2_048
MAX_EXPANDED_ROW_BYTES_INCLUDING_LF = 1_024
MAX_EXPANDED_SHARD_BODY_BYTES = 4 * 2**20
MAX_EXPANDED_ROWS_PER_SHARD = 4_096
MAX_EVENT_LINEAGE_BODY_BYTES = 4 * 2**20
MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF = 1_024
MAX_INVERTED_BODY_BYTES = 2 * 2**20
MAX_INVERTED_ROW_BYTES_INCLUDING_LF = 1_024

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_lifecycle_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
    }
)

SHARD_RECEIPT_ROW_FIELDS = frozenset(
    {
        "expanded_body_bytes",
        "expanded_body_persisted",
        "expanded_body_sha256",
        "expanded_maximum_row_bytes_including_lf",
        "first_intent_key",
        "last_intent_key",
        "origin",
        "persona_id",
        "row_count",
        "row_kind",
        "source_semantic_expanded_body_sha256",
        "source_shard_id",
        "source_shard_ordinal",
    }
)
PRIMARY_OVERRIDE_ROW_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "capability_class_key",
        "capability_key",
        "effective_fact_profile_id",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
COMPANION_MIRROR_ROW_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "companion_requirement_key",
        "effective_fact_profile_id",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "primary_capability_key",
        "primary_intent_key",
        "rendition_group_key",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
TYPED_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "fact_id",
        "graph_id",
        "origin",
        "persona_id",
        "predicate_id",
        "project_or_case_id",
        "purge_witness_key",
        "row_kind",
        "subject_entity_id",
        "suite_global_uniqueness_required",
        "typed_value",
        "visibility_by_checkpoint",
    }
)
EXPANDED_W0_ROW_FIELDS = frozenset(
    {
        "effective_membership_mode",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "origin",
        "persona_id",
        "present_fact_ids",
        "present_fact_set_key",
        "projection_mode",
        "row_kind",
        "semantic_section_key",
        "witness_fact_ids",
    }
)
EVENT_LINEAGE_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "capability_key",
        "consumer_role",
        "dependency_group_key",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "persona_id",
        "present_purge_witness_fact_ids",
        "row_kind",
        "source_intent_key",
        "wave",
    }
)
INVERTED_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "consumer_count",
        "consumer_refs",
        "persona_id",
        "purge_witness_key",
        "row_kind",
        "witness_fact_id",
    }
)
CONTENT_PRIMARY_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "present_fact_ids",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
CONTENT_COMPANION_ROW_FIELDS = frozenset(
    {
        "effective_membership_mode",
        "graph_id",
        "intent_key",
        "lifecycle_branch_key",
        "lifecycle_logical_document_key",
        "lifecycle_revision_chain_key",
        "logical_revision_key",
        "present_fact_ids",
        "primary_capability_key",
        "primary_intent_key",
        "rendition_group_key",
        "row_kind",
        "semantic_section_key",
        "topic_id",
        "witness_fact_ids",
    }
)
CONTENT_WITNESS_ROW_FIELDS = frozenset(
    {
        "capability_key",
        "fact_id",
        "graph_id",
        "predicate_id",
        "purge_witness_key",
        "row_kind",
        "subject_entity_id",
        "typed_value",
        "visibility_by_checkpoint",
    }
)
CONTENT_SHARD_COMMITMENT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "first_intent_key",
        "last_intent_key",
        "origin",
        "row_count",
        "row_kind",
        "source_shard_id",
    }
)


class PersonaV2LifecycleEffectiveMembershipReconciliationError(ValueError):
    """Raised when exact effective-membership reconciliation drifts."""


def _fail(message):
    raise PersonaV2LifecycleEffectiveMembershipReconciliationError(message)


def _freeze_cached_value(value):
    """Convert cache state to a recursively immutable tuple representation."""

    if value is None or type(value) in {bool, int, float, str, bytes}:
        return ("atom", value)
    if isinstance(value, dict):
        return (
            "dict",
            tuple(
                (_freeze_cached_value(key), _freeze_cached_value(item))
                for key, item in value.items()
            ),
        )
    if type(value) is list:
        return ("list", tuple(_freeze_cached_value(item) for item in value))
    if type(value) is tuple:
        return ("tuple", tuple(_freeze_cached_value(item) for item in value))
    if type(value) in {set, frozenset}:
        frozen_items = tuple(
            sorted(
                (_freeze_cached_value(item) for item in value),
                key=repr,
            )
        )
        return (
            "set" if type(value) is set else "frozenset",
            frozen_items,
        )
    _fail(f"cache state contains an unsupported value: {type(value).__name__}")


def _thaw_cached_value(value):
    """Return a fully detached value from an immutable cache representation."""

    tag = value[0]
    if tag == "atom":
        return value[1]
    if tag == "dict":
        return {
            _thaw_cached_value(key): _thaw_cached_value(item)
            for key, item in value[1]
        }
    if tag == "list":
        return [_thaw_cached_value(item) for item in value[1]]
    if tag == "tuple":
        return tuple(_thaw_cached_value(item) for item in value[1])
    if tag == "set":
        return {_thaw_cached_value(item) for item in value[1]}
    if tag == "frozenset":
        return frozenset(_thaw_cached_value(item) for item in value[1])
    _fail("immutable cache state has an unknown tag")


def _detached_lru_cache(*, maxsize):
    """Cache immutable tuples while exposing a fresh detached value per call."""

    def decorate(builder):
        @functools.lru_cache(maxsize=maxsize)
        def immutable_cache(*args, **kwargs):
            return _freeze_cached_value(builder(*args, **kwargs))

        @functools.wraps(builder)
        def detached(*args, **kwargs):
            return _thaw_cached_value(immutable_cache(*args, **kwargs))

        detached.cache_clear = immutable_cache.cache_clear
        detached.cache_info = immutable_cache.cache_info
        detached.immutable_cache_only = True
        if hasattr(immutable_cache, "cache_parameters"):
            detached.cache_parameters = immutable_cache.cache_parameters
        return detached

    return decorate


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        _fail(f"unknown persona ID: {persona_id!r}")


def _require_origin(origin):
    if type(origin) is not str or origin not in ORIGIN_ORDER:
        _fail(f"unknown source origin: {origin!r}")


def _require_profile(profile):
    if type(profile) is not str or profile not in PROFILE_ORDER:
        _fail(f"unknown source profile: {profile!r}")


def _ascii(value):
    return value.encode("ascii")


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_negative_authority(value, *, label):
    if type(value) is not dict or value.get("g0_contract_frozen") is not False:
        _fail(f"{label} must remain non-G0")
    authority = value.get("authority")
    if set(authority or {}) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        _fail(f"{label} authority must be the exact all-false schema")


def _require_upstream_non_authorizing(value, *, label):
    if type(value) is not dict:
        _fail(f"{label} must be an object")
    authority = value.get("authority")
    if (
        value.get("g0_contract_frozen") is not False
        or type(authority) is not dict
        or not authority
        or any(type(flag) is not bool or flag is not False for flag in authority.values())
    ):
        _fail(f"{label} escalated upstream authority")


def canonical_fragment_bytes(value, *, label="persona v2 lifecycle effective-membership fragment", max_bytes=4 * 2**20):
    """Canonicalize a non-artifact row/body fragment under an explicit cap."""

    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=max_bytes
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _jsonl_row_bytes(row, *, label, cap):
    return canonical_fragment_bytes(row, label=label, max_bytes=cap - 1) + b"\n"


def _bounded_body(rows, *, label, row_cap, body_cap, row_count_cap=None):
    parts = []
    maximum = 0
    total = 0
    count = 0
    for row in rows:
        count += 1
        if row_count_cap is not None and count > row_count_cap:
            _fail(f"{label} exceeds its row-count cap")
        raw = _jsonl_row_bytes(row, label=label, cap=row_cap)
        maximum = max(maximum, len(raw))
        total += len(raw)
        if total > body_cap:
            _fail(f"{label} exceeds its body cap")
        parts.append(raw)
    if not parts:
        _fail(f"{label} cannot be empty")
    return b"".join(parts), maximum


def _binding(name, role, value, *, canonical, coordinates=()):
    raw = canonical(value)
    row = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": _sha256(raw),
    }
    for coordinate in coordinates:
        row[coordinate] = value[coordinate]
    return row


def _lifecycle_identity(document_key):
    return {
        "lifecycle_branch_key": f"{document_key}-branch-main-v1",
        "lifecycle_logical_document_key": document_key,
        "lifecycle_revision_chain_key": f"{document_key}-revision-chain-main-v1",
        "logical_revision_key": f"{document_key}-revision-w0-v1",
        "semantic_section_key": f"{document_key}-semantic-section-main-v1",
    }


def _base_revision_chain_key(base_row):
    digest = _sha256(
        (base_row["logical_document_key"] + "\x00" + base_row["logical_branch_key"]).encode(
            "utf-8"
        )
    )[:24]
    return f"{base_row['persona_id']}-base-revision-chain-{digest}-v1"


def _witness_fact_id(persona_id, ordinal):
    return f"purge-witness-fact-{persona_id}-syn-{ordinal:03d}"


def _witness_token_id(persona_id, ordinal):
    return f"purge-witness-token-{persona_id}-syn-{ordinal:03d}"


def _witness_visibility():
    return [
        {"checkpoint": checkpoint, "state": state}
        for checkpoint, state in (
            ("W0", "current"),
            ("W1", "current"),
            ("W2", "current"),
            ("W3", "current"),
            ("W4", "current"),
            ("W5-pre-purge", "current"),
            ("W5-final", "absent"),
        )
    ]


@_detached_lru_cache(maxsize=1)
def _shared_catalogs():
    semantic = source_semantic.build_source_semantic_membership_catalog()
    source_semantic.validate_source_semantic_membership_catalog(semantic)
    coverage = lifecycle_coverage.build_lifecycle_coverage_catalog()
    lifecycle_coverage.validate_lifecycle_coverage_catalog(coverage)
    _require_upstream_non_authorizing(semantic, label="source semantic catalog")
    _require_upstream_non_authorizing(coverage, label="lifecycle coverage catalog")
    graphs = fact_graph.build_fact_graph_suite()
    if len(graphs) != len(envelope.PERSONA_IDS):
        _fail("fact graph suite cardinality drifted")
    graph_by_persona = {}
    graph_fact_ids = set()
    for persona_id, graph_value in zip(envelope.PERSONA_IDS, graphs):
        fact_graph.validate_fact_graph(persona_id, graph_value)
        _require_upstream_non_authorizing(
            graph_value, label=f"fact graph {persona_id}"
        )
        predicate = {
            row["predicate_id"]: row for row in graph_value["predicate_catalog"]
        }.get("predicate-status-syn-004")
        if predicate != {
            "predicate_id": "predicate-status-syn-004",
            "value_kind": "synthetic-token",
        }:
            _fail("typed purge witness status predicate contract drifted")
        graph_by_persona[persona_id] = graph_value
        graph_fact_ids.update(
            (persona_id, fact["fact_id"])
            for graph in graph_value["graphs"]
            for fact in graph["facts"]
        )
    fact_profiles = {
        row["fact_profile_id"]: row for row in semantic["fact_profiles"]
    }
    graph_fact_ids.update(
        (row["persona_id"], fact_id)
        for row in semantic["fact_profiles"]
        for fact_id in row["present_fact_ids"]
    )
    topics = {row["topic_id"]: row for row in semantic["semantic_topics"]}
    witness_requirements = {
        row["capability_key"]: row
        for row in coverage["purge_witness_requirements"]
    }
    projected_witness_ids = {
        _witness_fact_id(persona_id, ordinal)
        for persona_id in envelope.PERSONA_IDS
        for ordinal in range(1, 16)
    }
    if len(projected_witness_ids) != EXPECTED_TYPED_WITNESS_COUNT or any(
        (persona_id, fact_id) in graph_fact_ids
        for persona_id in envelope.PERSONA_IDS
        for fact_id in projected_witness_ids
    ):
        _fail("purge witness fact IDs are not suite-global unique and graph-disjoint")
    return {
        "coverage": coverage,
        "fact_profiles": fact_profiles,
        "graph_by_persona": graph_by_persona,
        "graph_fact_ids": frozenset(graph_fact_ids),
        "semantic": semantic,
        "topics": topics,
        "witness_requirements": witness_requirements,
    }


def _primary_override_row(persona_id, match, normal_profile, witness_row=None):
    identity = _lifecycle_identity(match["lifecycle_logical_document_slot_key"])
    witness_ids = [] if witness_row is None else [witness_row["fact_id"]]
    row = {
        "base_fact_profile_id": match["base_fact_profile_id"],
        "capability_class_key": match["capability_class_key"],
        "capability_key": match["capability_key"],
        "effective_fact_profile_id": normal_profile["fact_profile_id"],
        "effective_membership_mode": (
            "graph-normal"
            if witness_row is None
            else "graph-normal-plus-witness"
        ),
        "graph_id": normal_profile["graph_id"],
        "intent_key": match["intent_key"],
        **identity,
        "origin": "pilot",
        "persona_id": persona_id,
        "present_fact_ids": [*normal_profile["present_fact_ids"], *witness_ids],
        "row_kind": "primary-effective-membership-override",
        "topic_id": match["base_topic_id"],
        "witness_fact_ids": witness_ids,
    }
    if set(row) != PRIMARY_OVERRIDE_ROW_FIELDS:
        _fail("primary override row schema drifted")
    return row


def _typed_witness_row(persona_id, ordinal, match, normal_profile, requirement):
    fact_id = _witness_fact_id(persona_id, ordinal)
    row = {
        "capability_key": match["capability_key"],
        "fact_id": fact_id,
        "graph_id": normal_profile["graph_id"],
        "origin": "pilot",
        "persona_id": persona_id,
        "predicate_id": "predicate-status-syn-004",
        "project_or_case_id": normal_profile["project_or_case_id"],
        "purge_witness_key": requirement["purge_witness_key"],
        "row_kind": "typed-purge-witness-fact",
        "subject_entity_id": normal_profile["project_or_case_id"],
        "suite_global_uniqueness_required": True,
        "typed_value": {
            "kind": "synthetic-token",
            "token_id": _witness_token_id(persona_id, ordinal),
        },
        "visibility_by_checkpoint": _witness_visibility(),
    }
    if set(row) != TYPED_WITNESS_ROW_FIELDS:
        _fail("typed witness row schema drifted")
    return row


def _companion_mirror_row(match, primary):
    if primary["witness_fact_ids"] or primary["capability_class_key"] == "purged-negative":
        _fail("rendition companion cannot mirror a purge-witness/P primary")
    row = {
        "base_fact_profile_id": match["base_fact_profile_id"],
        "companion_requirement_key": match["companion_requirement_key"],
        "effective_fact_profile_id": primary["effective_fact_profile_id"],
        "effective_membership_mode": "companion-mirror",
        "graph_id": primary["graph_id"],
        "intent_key": match["intent_key"],
        "lifecycle_branch_key": primary["lifecycle_branch_key"],
        "lifecycle_logical_document_key": primary[
            "lifecycle_logical_document_key"
        ],
        "lifecycle_revision_chain_key": primary["lifecycle_revision_chain_key"],
        "logical_revision_key": primary["logical_revision_key"],
        "origin": "pilot",
        "persona_id": primary["persona_id"],
        "present_fact_ids": list(primary["present_fact_ids"]),
        "primary_capability_key": match["primary_capability_key"],
        "primary_intent_key": primary["intent_key"],
        "rendition_group_key": match["rendition_group_key"],
        "row_kind": "companion-effective-membership-mirror",
        "semantic_section_key": primary["semantic_section_key"],
        "topic_id": primary["topic_id"],
        "witness_fact_ids": list(primary["witness_fact_ids"]),
    }
    if set(row) != COMPANION_MIRROR_ROW_FIELDS:
        _fail("companion mirror row schema drifted")
    return row


@_detached_lru_cache(maxsize=20)
def _persona_plan(persona_id):
    _require_persona_id(persona_id)
    catalogs = _shared_catalogs()
    lifecycle = matched_lifecycle.build_source_matched_lifecycle_persona(persona_id)
    matched_lifecycle.validate_source_matched_lifecycle_persona(
        persona_id, lifecycle
    )
    _require_upstream_non_authorizing(
        lifecycle, label=f"source-matched lifecycle {persona_id}"
    )
    contributor_matches = [
        row
        for row in lifecycle["primary_match_rows"]
        if row["gate_role"] == "contract_contributor"
    ]
    incidental_matches = [
        row
        for row in lifecycle["primary_match_rows"]
        if row["gate_role"] == "incidental_searchable"
    ]
    if len(contributor_matches) != 100 or len(incidental_matches) != 5:
        _fail("persona lifecycle contributor/incidental split drifted")

    typed_witness_rows = []
    witness_by_capability = {}
    purged = sorted(
        (
            row
            for row in contributor_matches
            if row["capability_class_key"] == "purged-negative"
        ),
        key=lambda row: _ascii(row["capability_key"]),
    )
    if len(purged) != 15:
        _fail("persona purge capability count drifted")
    for ordinal, match in enumerate(purged, start=1):
        topic = catalogs["topics"].get(match["base_topic_id"])
        if topic is None or topic["persona_id"] != persona_id:
            _fail("purge match topic is not persona-local")
        profile_id = source_semantic.normal_fact_profile_id(
            persona_id, topic["topic_slot"]
        )
        normal_profile = catalogs["fact_profiles"].get(profile_id)
        requirement = catalogs["witness_requirements"].get(match["capability_key"])
        if normal_profile is None or requirement is None:
            _fail("purge match lacks its authenticated graph or witness requirement")
        witness = _typed_witness_row(
            persona_id, ordinal, match, normal_profile, requirement
        )
        graph_value = catalogs["graph_by_persona"][persona_id]
        graph = next(
            (
                row
                for row in graph_value["graphs"]
                if row["graph_id"] == normal_profile["graph_id"]
            ),
            None,
        )
        if (
            graph is None
            or not any(
                entity["entity_id"] == witness["subject_entity_id"]
                and entity["entity_type"] == "project-or-case"
                for entity in graph["entities"]
            )
            or (persona_id, witness["fact_id"]) in catalogs["graph_fact_ids"]
        ):
            _fail("typed purge witness graph ownership or fact-ID separation drifted")
        typed_witness_rows.append(witness)
        witness_by_capability[match["capability_key"]] = witness

    primary_rows = []
    for match in sorted(contributor_matches, key=lambda row: _ascii(row["capability_key"])):
        topic = catalogs["topics"].get(match["base_topic_id"])
        if topic is None or topic["persona_id"] != persona_id:
            _fail("contributor match topic is not persona-local")
        profile_id = source_semantic.normal_fact_profile_id(
            persona_id, topic["topic_slot"]
        )
        normal_profile = catalogs["fact_profiles"].get(profile_id)
        if (
            normal_profile is None
            or normal_profile["profile_kind"] != "graph-normal-w0"
            or len(normal_profile["present_fact_ids"]) != 8
        ):
            _fail("contributor graph-normal W0 profile is invalid")
        primary_rows.append(
            _primary_override_row(
                persona_id,
                match,
                normal_profile,
                witness_by_capability.get(match["capability_key"]),
            )
        )
    primary_by_capability = {
        row["capability_key"]: row for row in primary_rows
    }
    primary_match_by_capability = {
        row["capability_key"]: row for row in contributor_matches
    }
    companion_rows = []
    for match in sorted(
        lifecycle["companion_match_rows"],
        key=lambda row: _ascii(row["primary_capability_key"]),
    ):
        primary = primary_by_capability.get(match["primary_capability_key"])
        primary_match = primary_match_by_capability.get(
            match["primary_capability_key"]
        )
        if (
            primary is None
            or primary_match is None
            or primary_match["allocation_class"] not in {"U", "Y"}
            or match["base_topic_id"] != primary_match["base_topic_id"]
            or match["base_language"] != primary_match["base_language"]
            or match["family"] == primary_match["family"]
            or match["gate_role"] != "contract_contributor"
        ):
            _fail("companion does not reference a contributor primary")
        companion_rows.append(_companion_mirror_row(match, primary))
    if len(primary_rows) != 100 or len(companion_rows) != 10:
        _fail("persona effective override cardinality drifted")

    override_by_intent = {
        row["intent_key"]: row for row in [*primary_rows, *companion_rows]
    }
    if len(override_by_intent) != 110:
        _fail("persona effective override intent keys are not unique")
    if set(override_by_intent) & {row["intent_key"] for row in incidental_matches}:
        _fail("incidental lifecycle sources must retain complete base membership")
    return {
        "companion_rows": tuple(companion_rows),
        "incidental_intent_keys": frozenset(
            row["intent_key"] for row in incidental_matches
        ),
        "lifecycle": lifecycle,
        "override_by_intent": override_by_intent,
        "primary_rows": tuple(primary_rows),
        "typed_witness_rows": tuple(typed_witness_rows),
        "witness_by_capability": witness_by_capability,
    }


def _effective_w0_row(base_row, override):
    if set(base_row) != source_semantic.EXPANDED_MEMBERSHIP_ROW_FIELDS:
        _fail("authenticated base membership row schema drifted")
    if override is None:
        present = list(base_row["present_fact_ids"])
        row = {
            "effective_membership_mode": "base-inheritance",
            "intent_key": base_row["intent_key"],
            "lifecycle_branch_key": base_row["logical_branch_key"],
            "lifecycle_logical_document_key": base_row["logical_document_key"],
            "lifecycle_revision_chain_key": _base_revision_chain_key(base_row),
            "logical_revision_key": base_row["logical_revision_key"],
            "origin": base_row["origin"],
            "persona_id": base_row["persona_id"],
            "present_fact_ids": present,
            "present_fact_set_key": base_row["present_fact_set_key"],
            "projection_mode": base_row["projection_mode"],
            "row_kind": "effective-w0-membership",
            "semantic_section_key": base_row["semantic_section_key"],
            "witness_fact_ids": [],
        }
    else:
        present = list(override["present_fact_ids"])
        row = {
            "effective_membership_mode": override["effective_membership_mode"],
            "intent_key": base_row["intent_key"],
            "lifecycle_branch_key": override["lifecycle_branch_key"],
            "lifecycle_logical_document_key": override[
                "lifecycle_logical_document_key"
            ],
            "lifecycle_revision_chain_key": override[
                "lifecycle_revision_chain_key"
            ],
            "logical_revision_key": override["logical_revision_key"],
            "origin": base_row["origin"],
            "persona_id": base_row["persona_id"],
            "present_fact_ids": present,
            "present_fact_set_key": base_row["present_fact_set_key"],
            "projection_mode": "all-present-facts-single-semantic-section",
            "row_kind": "effective-w0-membership",
            "semantic_section_key": override["semantic_section_key"],
            "witness_fact_ids": list(override["witness_fact_ids"]),
        }
    if set(row) != EXPANDED_W0_ROW_FIELDS:
        _fail("expanded effective W0 membership row schema drifted")
    if len(set(present)) != len(present):
        _fail("effective W0 membership contains duplicate fact IDs")
    return row


def iter_expanded_effective_w0_membership_rows(
    persona_id, origin, shard_ordinal
):
    """Yield one source shard's exact effective W0 memberships."""

    _require_persona_id(persona_id)
    _require_origin(origin)
    plan = _persona_plan(persona_id)
    for base_row in source_semantic.iter_expanded_fact_membership_rows(
        persona_id, origin, shard_ordinal
    ):
        yield _effective_w0_row(
            base_row, plan["override_by_intent"].get(base_row["intent_key"])
        )


def expanded_effective_w0_membership_shard_body_bytes(
    persona_id, origin, shard_ordinal
):
    body, _maximum = _bounded_body(
        iter_expanded_effective_w0_membership_rows(
            persona_id, origin, shard_ordinal
        ),
        label="persona v2 expanded effective W0 membership row",
        row_cap=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
        row_count_cap=MAX_EXPANDED_ROWS_PER_SHARD,
    )
    return body


def _shard_receipt(persona_id, origin, descriptor):
    shard_ordinal = descriptor["shard_ordinal"]
    effective_rows = list(
        iter_expanded_effective_w0_membership_rows(
            persona_id, origin, shard_ordinal
        )
    )
    if (
        len(effective_rows) != descriptor["row_count"]
        or effective_rows[0]["intent_key"] != descriptor["first_intent_key"]
        or effective_rows[-1]["intent_key"] != descriptor["last_intent_key"]
    ):
        _fail("effective expanded shard range differs from source descriptor")
    effective_body, effective_maximum = _bounded_body(
        effective_rows,
        label="persona v2 expanded effective W0 membership row",
        row_cap=MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EXPANDED_SHARD_BODY_BYTES,
        row_count_cap=MAX_EXPANDED_ROWS_PER_SHARD,
    )
    base_body = source_semantic.expanded_fact_membership_shard_body_bytes(
        persona_id, origin, shard_ordinal
    )
    row = {
        "expanded_body_bytes": len(effective_body),
        "expanded_body_persisted": False,
        "expanded_body_sha256": _sha256(effective_body),
        "expanded_maximum_row_bytes_including_lf": effective_maximum,
        "first_intent_key": descriptor["first_intent_key"],
        "last_intent_key": descriptor["last_intent_key"],
        "origin": origin,
        "persona_id": persona_id,
        "row_count": descriptor["row_count"],
        "row_kind": "effective-w0-expanded-shard-receipt",
        "source_semantic_expanded_body_sha256": _sha256(base_body),
        "source_shard_id": descriptor["shard_id"],
        "source_shard_ordinal": shard_ordinal,
    }
    if set(row) != SHARD_RECEIPT_ROW_FIELDS:
        _fail("effective shard receipt schema drifted")
    return row


@_detached_lru_cache(maxsize=40)
def _origin_dependencies(persona_id, origin):
    semantic_manifest = source_semantic.build_source_semantic_membership_origin_manifest(
        persona_id, origin
    )
    source_semantic.validate_source_semantic_membership_origin_manifest(
        persona_id, origin, semantic_manifest
    )
    _require_upstream_non_authorizing(
        semantic_manifest, label=f"source semantic origin {persona_id}/{origin}"
    )
    source_manifest = source_package.build_source_intent_origin_manifest(
        persona_id, origin
    )
    source_package.validate_source_intent_origin_manifest(
        persona_id, origin, source_manifest
    )
    _require_upstream_non_authorizing(
        source_manifest, label=f"source inventory origin {persona_id}/{origin}"
    )
    return semantic_manifest, source_manifest


@_detached_lru_cache(maxsize=40)
def _canonical_origin_rows(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    _semantic_manifest, source_manifest = _origin_dependencies(persona_id, origin)
    rows = []
    for descriptor in source_manifest["shard_descriptors"]:
        rows.append(_shard_receipt(persona_id, origin, descriptor))
    if origin == "pilot":
        plan = _persona_plan(persona_id)
        rows.extend(plan["primary_rows"])
        rows.extend(plan["companion_rows"])
        rows.extend(plan["typed_witness_rows"])
    return tuple(copy.deepcopy(rows))


def iter_lifecycle_effective_membership_origin_rows(persona_id, origin):
    """Yield the sparse owner: receipts, overrides, mirrors, then witnesses."""

    yield from (
        copy.deepcopy(row) for row in _canonical_origin_rows(persona_id, origin)
    )


def lifecycle_effective_membership_origin_body_bytes(persona_id, origin):
    body, _maximum = _bounded_body(
        iter_lifecycle_effective_membership_origin_rows(persona_id, origin),
        label="persona v2 compact lifecycle effective-membership row",
        row_cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_ORIGIN_BODY_BYTES,
        row_count_cap=MAX_ORIGIN_ROWS,
    )
    return body


def _origin_binding(name, role, value, *, canonical, coordinates):
    return _binding(
        name,
        role,
        value,
        canonical=canonical,
        coordinates=coordinates,
    )


@_detached_lru_cache(maxsize=40)
def _canonical_origin_manifest(persona_id, origin):
    _require_persona_id(persona_id)
    _require_origin(origin)
    semantic_manifest, source_manifest = _origin_dependencies(persona_id, origin)
    rows = list(iter_lifecycle_effective_membership_origin_rows(persona_id, origin))
    body = b"".join(
        _jsonl_row_bytes(
            row,
            label="persona v2 compact lifecycle effective-membership row",
            cap=MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        for row in rows
    )
    if len(rows) > MAX_ORIGIN_ROWS or len(body) > MAX_ORIGIN_BODY_BYTES:
        _fail("effective-membership origin body exceeds its compact cap")
    receipts = [row for row in rows if row["row_kind"] == "effective-w0-expanded-shard-receipt"]
    primaries = [row for row in rows if row["row_kind"] == "primary-effective-membership-override"]
    companions = [row for row in rows if row["row_kind"] == "companion-effective-membership-mirror"]
    witnesses = [row for row in rows if row["row_kind"] == "typed-purge-witness-fact"]
    plan = _persona_plan(persona_id)
    lifecycle = plan["lifecycle"]
    catalogs = _shared_catalogs()
    graph_value = catalogs["graph_by_persona"][persona_id]
    bindings = [
        _origin_binding(
            "persona-v2-source-semantic-membership-catalog",
            "graph-normal-W0-profile-and-topic-owner",
            catalogs["semantic"],
            canonical=source_semantic.canonical_json_bytes,
            coordinates=(),
        ),
        _origin_binding(
            "persona-v2-lifecycle-coverage-catalog",
            "typed-purge-witness-requirement-owner",
            catalogs["coverage"],
            canonical=lifecycle_coverage.canonical_json_bytes,
            coordinates=(),
        ),
        _origin_binding(
            "persona-v2-source-semantic-membership-origin-manifest",
            "immutable-base-W0-membership-and-source-owned-present-fact-set-owner",
            semantic_manifest,
            canonical=source_semantic.canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        ),
        _origin_binding(
            "persona-v2-source-matched-lifecycle-persona",
            "authenticated-capability-source-match-rendition-and-event-owner",
            lifecycle,
            canonical=matched_lifecycle.canonical_json_bytes,
            coordinates=("persona_id",),
        ),
        _origin_binding(
            "persona-v2-fact-graph",
            "persona-local-typed-fact-and-project-entity-owner",
            graph_value,
            canonical=fact_graph.canonical_json_bytes,
            coordinates=("persona_id",),
        ),
    ]
    source_count = semantic_manifest["summary"]["source_count"]
    mode_counts = {
        "base-inheritance": source_count - len(primaries) - len(companions),
        "companion-mirror": len(companions),
        "graph-normal-plus-witness": sum(
            row["effective_membership_mode"] == "graph-normal-plus-witness"
            for row in primaries
        ),
        "graph-normal": sum(
            row["effective_membership_mode"] == "graph-normal"
            for row in primaries
        ),
    }
    value = {
        "artifact_kind": ORIGIN_KIND,
        "artifact_schema": ORIGIN_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "body_descriptor": {
            "body_bytes": len(body),
            "body_persisted": True,
            "body_sha256": _sha256(body),
            "file_name": f"{persona_id}-lifecycle-effective-membership-{origin}.jsonl",
            "maximum_row_bytes_including_lf": max(len(line) + 1 for line in body.splitlines()),
            "row_count": len(rows),
        },
        "canonical_limits": {
            "max_compact_body_bytes": MAX_ORIGIN_BODY_BYTES,
            "max_compact_row_bytes_including_lf": MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            "max_compact_rows": MAX_ORIGIN_ROWS,
            "max_expanded_row_bytes_including_lf": MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            "max_expanded_shard_body_bytes": MAX_EXPANDED_SHARD_BODY_BYTES,
            "max_expanded_rows_per_shard": MAX_EXPANDED_ROWS_PER_SHARD,
            "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_origin_w0_memberships_effectively_reconciled": True,
            "expanded_effective_bodies_persisted": False,
            "formal_namespace_completion_authorized": False,
            "incidental_lifecycle_sources_inherit_complete_base_membership": True,
            "source_owned_present_fact_set_keys_preserved": True,
        },
        "completion_scope": (
            "one-persona-one-origin-effective-w0-membership-sparse-owner-and-"
            "streaming-receipts-no-solution-render-write-history-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "base_and_effective_membership_are_not_union_owners": True,
            "base_full_membership_remains_corpus-input-closure": True,
            "expanded_effective_rows_are_nonpersisted-verification-views": True,
            "source_inventory_or_semantic_origins_may_back_bind_this_artifact": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in bindings],
        "input_bindings": bindings,
        "origin": origin,
        "persona_id": persona_id,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "filesystem-materialization-capacity-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_companion_mirror_count": len(companions),
            "compact_primary_override_count": len(primaries),
            "compact_shard_receipt_count": len(receipts),
            "compact_typed_witness_count": len(witnesses),
            "effective_w0_mode_counts": mode_counts,
            "expanded_effective_body_bytes": sum(row["expanded_body_bytes"] for row in receipts),
            "maximum_compact_row_bytes_including_lf": max(len(line) + 1 for line in body.splitlines()),
            "maximum_expanded_row_bytes_including_lf": max(row["expanded_maximum_row_bytes_including_lf"] for row in receipts),
            "present_fact_reference_count": semantic_manifest["summary"]["present_fact_reference_count"] + (715 if origin == "pilot" else 0),
            "source_count": source_count,
            "source_shard_count": len(receipts),
        },
    }
    _require_negative_authority(value, label="effective-membership origin manifest")
    canonical_json_bytes(value)
    return value


def build_lifecycle_effective_membership_origin_manifest(persona_id, origin):
    return copy.deepcopy(_canonical_origin_manifest(persona_id, origin))


def iter_event_created_witness_lineage_rows(persona_id):
    """Yield all event-created intents with explicit purge-witness lineage."""

    _require_persona_id(persona_id)
    plan = _persona_plan(persona_id)
    source_events = []
    for event in matched_lifecycle.iter_source_matched_lifecycle_event_rows(
        persona_id
    ):
        event_fields = set(event)
        if event_fields == matched_lifecycle.SCOPE_EVENT_ROW_FIELDS:
            if event.get("row_kind") != "scope":
                _fail("scope event row kind drifted")
            continue
        if (
            event_fields != matched_lifecycle.SOURCE_EVENT_ROW_FIELDS
            or event.get("row_kind") != "source"
        ):
            _fail("lifecycle event iterator emitted an unknown row schema")
        source_events.append(event)
    created_events = [
        event
        for event in source_events
        if event["after_source_intent_key"] != event["source_intent_key"]
        and event["after_source_intent_key"]
        == f"{persona_id}-pre-solve-source-intent-{event['event_sequence_ordinal']:04d}"
    ]
    expected_count = 179 + (
        5 if persona_id in matched_lifecycle.DERIVE_DIAGNOSTIC_PERSONAS else 0
    ) + (5 if persona_id in matched_lifecycle.DUPLICATE_DIAGNOSTIC_PERSONAS else 0)
    if len(created_events) != expected_count:
        _fail("authenticated event-created source-intent count drifted")
    carry_count = 0
    prime_count = 0
    rows = []
    for event in created_events:
        witness = plan["witness_by_capability"].get(event["capability_key"])
        if witness is not None and event["event_profile_key"] == "w1-typed-edit":
            if event["fact_transition_rule"] != "facts/typed-revision":
                _fail("W1 P descendant fact transition rule drifted")
            role = "matching-w1-p-descendant"
            witness_ids = [witness["fact_id"]]
            carry_count += 1
        elif witness is not None and event["event_profile_key"] == "w5-create-p-prime":
            if event["fact_transition_rule"] != "facts/repl-distinct":
                _fail("P-prime distinct replacement fact transition rule drifted")
            role = "p-prime-capacity-replacement"
            witness_ids = []
            prime_count += 1
        else:
            role = "other-event-created-intent"
            witness_ids = []
        row = {
            "after_source_intent_key": event["after_source_intent_key"],
            "capability_key": event["capability_key"],
            "consumer_role": role,
            "dependency_group_key": event["dependency_group_key"],
            "event_intent_key": event["event_intent_key"],
            "event_profile_key": event["event_profile_key"],
            "event_sequence_ordinal": event["event_sequence_ordinal"],
            "fact_transition_rule": event["fact_transition_rule"],
            "persona_id": persona_id,
            "present_purge_witness_fact_ids": witness_ids,
            "row_kind": "event-created-purge-witness-lineage",
            "source_intent_key": event["source_intent_key"],
            "wave": event["wave"],
        }
        if set(row) != EVENT_LINEAGE_ROW_FIELDS:
            _fail("event-created witness-lineage row schema drifted")
        rows.append(row)
    if carry_count != 15 or prime_count != 15:
        _fail("persona P descendant/P-prime lineage count drifted")
    yield from rows


def lifecycle_effective_membership_event_created_lineage_body_bytes(persona_id):
    body, _maximum = _bounded_body(
        iter_event_created_witness_lineage_rows(persona_id),
        label="persona v2 event-created purge-witness lineage row",
        row_cap=MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EVENT_LINEAGE_BODY_BYTES,
    )
    return body


# Concise compatibility alias matching the iterator noun phrase.
event_created_witness_lineage_body_bytes = (
    lifecycle_effective_membership_event_created_lineage_body_bytes
)


@_detached_lru_cache(maxsize=20)
def _persona_w0_audit(persona_id):
    plan = _persona_plan(persona_id)
    known_by_fact_id = {
        row["fact_id"]: row for row in plan["typed_witness_rows"]
    }
    occurrences = {fact_id: [] for fact_id in known_by_fact_id}
    primary_by_intent = {
        row["intent_key"]: row for row in plan["primary_rows"]
    }
    mode_counts = {mode: 0 for mode in EXPECTED_W0_MODE_COUNTS}
    cardinality_counts = {
        "conflict-branch": 0,
        "empty": 0,
        "graph-normal-only": 0,
        "graph-normal-plus-witness": 0,
        "singleton": 0,
    }
    present_fact_reference_count = 0
    coordinates = set()
    for origin in ORIGIN_ORDER:
        _semantic_manifest, source_manifest = _origin_dependencies(
            persona_id, origin
        )
        for descriptor in source_manifest["shard_descriptors"]:
            for effective in iter_expanded_effective_w0_membership_rows(
                persona_id, origin, descriptor["shard_ordinal"]
            ):
                coordinate = (
                    effective["persona_id"],
                    effective["origin"],
                    effective["intent_key"],
                )
                if coordinate in coordinates:
                    _fail("expanded effective W0 coordinate is duplicated")
                coordinates.add(coordinate)
                mode = effective["effective_membership_mode"]
                if mode not in mode_counts:
                    _fail("expanded effective W0 mode is unknown")
                mode_counts[mode] += 1
                explicit = effective["witness_fact_ids"]
                embedded = [
                    fact_id
                    for fact_id in effective["present_fact_ids"]
                    if fact_id in known_by_fact_id
                    or fact_id.startswith("purge-witness-fact-")
                ]
                if explicit != embedded or any(
                    fact_id not in known_by_fact_id for fact_id in embedded
                ):
                    _fail("W0 effective row has an unknown or untyped witness occurrence")
                fact_count = len(effective["present_fact_ids"])
                present_fact_reference_count += fact_count
                if fact_count == 0 and not explicit:
                    bucket = "empty"
                elif fact_count == 1 and not explicit:
                    bucket = "singleton"
                elif fact_count == 7 and not explicit:
                    bucket = "conflict-branch"
                elif fact_count == 8 and not explicit:
                    bucket = "graph-normal-only"
                elif fact_count == 9 and len(explicit) == 1:
                    bucket = "graph-normal-plus-witness"
                else:
                    _fail("expanded effective W0 fact-cardinality bucket drifted")
                cardinality_counts[bucket] += 1
                for fact_id in explicit:
                    primary = primary_by_intent.get(effective["intent_key"])
                    if primary is None:
                        _fail("W0 witness consumer is not a contributor primary")
                    occurrences[fact_id].append(
                        {
                            "consumer_domain": "w0-source",
                            "consumer_role": "matching-w0-p-primary",
                            "event_intent_key": "not-applicable-w0",
                            "source_intent_key": effective["intent_key"],
                        }
                    )
    expected_source_count = envelope.profile_file_count(persona_id, "full")
    if len(coordinates) != expected_source_count:
        _fail("persona effective W0 audit does not cover its exact full source domain")
    return {
        "fact_cardinality_counts": cardinality_counts,
        "mode_counts": mode_counts,
        "occurrences": occurrences,
        "present_fact_reference_count": present_fact_reference_count,
        "source_count": len(coordinates),
    }


@_detached_lru_cache(maxsize=20)
def _persona_inverted_rows(persona_id):
    plan = _persona_plan(persona_id)
    primary_by_capability = {
        row["capability_key"]: row for row in plan["primary_rows"]
    }
    known_by_fact_id = {
        row["fact_id"]: row for row in plan["typed_witness_rows"]
    }
    occurrences = {
        fact_id: list(rows)
        for fact_id, rows in _persona_w0_audit(persona_id)["occurrences"].items()
    }
    lineage_rows = list(iter_event_created_witness_lineage_rows(persona_id))
    w1_by_capability = {}
    for event in lineage_rows:
        explicit = event["present_purge_witness_fact_ids"]
        if any(fact_id not in known_by_fact_id for fact_id in explicit):
            _fail("event-created lineage contains an unknown witness fact")
        for fact_id in explicit:
            occurrences[fact_id].append(
                {
                    "consumer_domain": "event-created-source",
                    "consumer_role": event["consumer_role"],
                    "event_intent_key": event["event_intent_key"],
                    "source_intent_key": event["after_source_intent_key"],
                }
            )
        if event["consumer_role"] == "matching-w1-p-descendant":
            if event["capability_key"] in w1_by_capability:
                _fail("P capability has multiple W1 witness descendants")
            w1_by_capability[event["capability_key"]] = event
    rows = []
    for witness in plan["typed_witness_rows"]:
        capability_key = witness["capability_key"]
        primary = primary_by_capability.get(capability_key)
        descendant = w1_by_capability.get(capability_key)
        if primary is None or descendant is None:
            _fail("purge witness lacks its exact W0/W1 lifecycle chain")
        expected_refs = [
            {
                "consumer_domain": "w0-source",
                "consumer_role": "matching-w0-p-primary",
                "event_intent_key": "not-applicable-w0",
                "source_intent_key": primary["intent_key"],
            },
            {
                "consumer_domain": "event-created-source",
                "consumer_role": "matching-w1-p-descendant",
                "event_intent_key": descendant["event_intent_key"],
                "source_intent_key": descendant["after_source_intent_key"],
            },
        ]
        refs = occurrences[witness["fact_id"]]
        if refs != expected_refs:
            _fail("purge witness does not have exactly its matching W0 and W1 consumers")
        row = {
            "capability_key": capability_key,
            "consumer_count": 2,
            "consumer_refs": refs,
            "persona_id": persona_id,
            "purge_witness_key": witness["purge_witness_key"],
            "row_kind": "purge-witness-inverted-consumers",
            "witness_fact_id": witness["fact_id"],
        }
        if set(row) != INVERTED_WITNESS_ROW_FIELDS:
            _fail("inverted purge-witness row schema drifted")
        rows.append(row)
    if len(rows) != 15:
        _fail("persona inverted purge-witness cardinality drifted")
    return tuple(rows)


def iter_inverted_purge_witness_rows(persona_id=None):
    """Yield persona-local or suite-global inverted witness consumers."""

    persona_ids = envelope.PERSONA_IDS if persona_id is None else (persona_id,)
    if persona_id is not None:
        _require_persona_id(persona_id)
    for current in persona_ids:
        yield from (copy.deepcopy(row) for row in _persona_inverted_rows(current))


def lifecycle_effective_membership_inverted_witness_body_bytes(persona_id=None):
    body, _maximum = _bounded_body(
        iter_inverted_purge_witness_rows(persona_id),
        label="persona v2 inverted purge-witness consumer row",
        row_cap=MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_INVERTED_BODY_BYTES,
    )
    return body


inverted_purge_witness_body_bytes = (
    lifecycle_effective_membership_inverted_witness_body_bytes
)


def _profile_origins(profile):
    _require_profile(profile)
    return ("pilot",) if profile == "pilot" else ORIGIN_ORDER


@_detached_lru_cache(maxsize=40)
def _canonical_profile_manifest(persona_id, profile):
    _require_persona_id(persona_id)
    _require_profile(profile)
    origins = [
        _canonical_origin_manifest(persona_id, origin)
        for origin in _profile_origins(profile)
    ]
    bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-origin-manifest",
            "sparse-effective-membership-origin-owner",
            value,
            canonical=canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        )
        for value in origins
    ]
    mode_counts = {
        mode: sum(
            origin["summary"]["effective_w0_mode_counts"][mode]
            for origin in origins
        )
        for mode in EXPECTED_W0_MODE_COUNTS
    }
    value = {
        "artifact_kind": PROFILE_KIND,
        "artifact_schema": PROFILE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_manifest_bytes": MAX_PROFILE_MANIFEST_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_profile_w0_memberships_effectively_reconciled": True,
            "full_profile_exactly_reuses_pilot_origin": profile == "full",
            "post_w0_complete_membership_compiled": False,
            "semantic_namespace_completion_authorized": False,
        },
        "completion_scope": (
            "one-persona-pilot-or-full-effective-w0-membership-composition-"
            "without-post-w0-solution-history-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "full_origin_order_is_pilot-then-full-residual": True,
            "full_profile_reuses_byte-identical-pilot-origin-binding": True,
            "origin_manifests_are-strictly-upstream": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "origin_manifest_bindings": bindings,
        "origin_order": [row["origin"] for row in origins],
        "persona_id": persona_id,
        "profile": profile,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "physical-capacity-materialization-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_body_bytes": sum(row["body_descriptor"]["body_bytes"] for row in origins),
            "compact_row_count": sum(row["body_descriptor"]["row_count"] for row in origins),
            "effective_w0_mode_counts": mode_counts,
            "origin_manifest_count": len(origins),
            "present_fact_reference_count": sum(row["summary"]["present_fact_reference_count"] for row in origins),
            "source_count": sum(row["summary"]["source_count"] for row in origins),
            "source_shard_count": sum(row["summary"]["source_shard_count"] for row in origins),
        },
    }
    if value["summary"]["source_count"] != envelope.profile_file_count(
        persona_id, profile
    ):
        _fail("effective-membership profile source count drifted")
    _require_negative_authority(value, label="effective-membership profile manifest")
    canonical_json_bytes(value)
    return value


def build_lifecycle_effective_membership_profile_manifest(persona_id, profile):
    return copy.deepcopy(_canonical_profile_manifest(persona_id, profile))


def _view_receipt(persona_id):
    event_body, event_maximum = _bounded_body(
        iter_event_created_witness_lineage_rows(persona_id),
        label="persona v2 event-created purge-witness lineage row",
        row_cap=MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_EVENT_LINEAGE_BODY_BYTES,
    )
    inverted_body, inverted_maximum = _bounded_body(
        iter_inverted_purge_witness_rows(persona_id),
        label="persona v2 inverted purge-witness consumer row",
        row_cap=MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_INVERTED_BODY_BYTES,
    )
    return {
        "event_created_lineage_body_bytes": len(event_body),
        "event_created_lineage_body_persisted": False,
        "event_created_lineage_body_sha256": _sha256(event_body),
        "event_created_lineage_maximum_row_bytes_including_lf": event_maximum,
        "event_created_lineage_row_count": len(event_body.splitlines()),
        "inverted_witness_body_bytes": len(inverted_body),
        "inverted_witness_body_persisted": False,
        "inverted_witness_body_sha256": _sha256(inverted_body),
        "inverted_witness_maximum_row_bytes_including_lf": inverted_maximum,
        "inverted_witness_row_count": len(inverted_body.splitlines()),
        "persona_id": persona_id,
    }


@_detached_lru_cache(maxsize=1)
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
    semantic_catalog = _shared_catalogs()["semantic"]
    coverage_catalog = _shared_catalogs()["coverage"]
    semantic_suite = source_semantic.build_source_semantic_membership_suite_descriptor()
    source_semantic.validate_source_semantic_membership_suite_descriptor(
        semantic_suite
    )
    lifecycle_suite = matched_lifecycle.build_source_matched_lifecycle_suite_descriptor()
    matched_lifecycle.validate_source_matched_lifecycle_suite_descriptor(
        lifecycle_suite
    )
    for label, upstream in (
        ("source semantic suite", semantic_suite),
        ("source-matched lifecycle suite", lifecycle_suite),
    ):
        _require_upstream_non_authorizing(upstream, label=label)
    input_bindings = [
        _binding(
            "persona-v2-source-semantic-membership-catalog",
            "graph-normal-W0-profile-and-topic-owner",
            semantic_catalog,
            canonical=source_semantic.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-semantic-membership-suite",
            "authenticated-base-membership-suite-and-derivation-closure",
            semantic_suite,
            canonical=source_semantic.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-lifecycle-coverage-catalog",
            "typed-purge-witness-requirement-owner",
            coverage_catalog,
            canonical=lifecycle_coverage.canonical_json_bytes,
        ),
        _binding(
            "persona-v2-source-matched-lifecycle-suite",
            "authenticated-source-match-rendition-and-event-owner",
            lifecycle_suite,
            canonical=matched_lifecycle.canonical_json_bytes,
        ),
    ]
    origin_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-origin-manifest",
            "sparse-effective-membership-origin-owner",
            value,
            canonical=canonical_json_bytes,
            coordinates=("persona_id", "origin"),
        )
        for value in origins
    ]
    profile_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-profile-manifest",
            "effective-membership-profile-composition",
            value,
            canonical=canonical_json_bytes,
            coordinates=("persona_id", "profile"),
        )
        for value in profiles
    ]
    receipts = [_view_receipt(persona_id) for persona_id in envelope.PERSONA_IDS]
    projections = [
        _canonical_content_projection(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    projection_bindings = [
        _binding(
            "persona-v2-lifecycle-effective-membership-content-projection",
            "persona-semantic-namespace-effective-membership-content",
            projection,
            canonical=canonical_json_bytes,
            coordinates=("persona_id",),
        )
        for projection in projections
    ]
    full_profiles = [row for row in profiles if row["profile"] == "full"]
    manifest_mode_counts = {
        mode: sum(
            row["summary"]["effective_w0_mode_counts"][mode]
            for row in full_profiles
        )
        for mode in EXPECTED_W0_MODE_COUNTS
    }
    audits = [_persona_w0_audit(persona_id) for persona_id in envelope.PERSONA_IDS]
    mode_counts = {
        mode: sum(audit["mode_counts"][mode] for audit in audits)
        for mode in EXPECTED_W0_MODE_COUNTS
    }
    fact_distribution = {
        bucket: sum(
            audit["fact_cardinality_counts"][bucket] for audit in audits
        )
        for bucket in EXPECTED_W0_FACT_DISTRIBUTION
    }
    audited_source_count = sum(audit["source_count"] for audit in audits)
    audited_fact_reference_count = sum(
        audit["present_fact_reference_count"] for audit in audits
    )
    if (
        manifest_mode_counts != mode_counts
        or mode_counts != EXPECTED_W0_MODE_COUNTS
        or fact_distribution != EXPECTED_W0_FACT_DISTRIBUTION
        or audited_source_count != EXPECTED_SOURCE_COUNT
        or audited_fact_reference_count != EXPECTED_PRESENT_FACT_REFERENCE_COUNT
    ):
        _fail("streamed effective W0 distribution audit drifted")
    value = {
        "artifact_kind": SUITE_KIND,
        "artifact_schema": SUITE_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
            "max_content_projection_bytes": MAX_CONTENT_PROJECTION_BYTES,
            "max_event_created_lineage_body_bytes_per_persona": MAX_EVENT_LINEAGE_BODY_BYTES,
            "max_inverted_witness_body_bytes": MAX_INVERTED_BODY_BYTES,
            "max_suite_descriptor_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
            "self_hash_embedded": False,
            "target_content_projection_bytes": TARGET_CONTENT_PROJECTION_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_203000_effective_w0_memberships_reconciled": True,
            "all_3630_event_created_witness_lineages_receipted": True,
            "all_300_purge_witnesses_have_exactly_two_consumers": True,
            "all_73_expanded_effective_shards_receipted": True,
            "expanded_and_inverted_views_persisted": False,
            "post_w0_complete_membership_compiled": False,
            "semantic_namespace_completion_authorized": False,
        },
        "completion_scope": (
            "all-twenty-persona-effective-w0-membership-and-purge-witness-"
            "isolation-proof-only-no-solved-complete-post-w0-history-execution-or-g0"
        ),
        "content_projection_bindings": projection_bindings,
        "dependency_direction_contract": {
            "base-membership-and-reconciliation-receipts-remain-input-closure": True,
            "effective-W0-is-the-single-formal-namespace-membership-owner": True,
            "witness-isolation-does-not-claim-complete-post-W0-membership": True,
        },
        "effective_w0_distribution_audit": {
            "fact_cardinality_counts": fact_distribution,
            "mode_counts": mode_counts,
            "present_fact_reference_count": audited_fact_reference_count,
            "source_count": audited_source_count,
            "streamed_complete_domain_verified": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [row["name"] for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "origin": list(ORIGIN_ORDER),
            "origin_manifests": "persona-then-origin",
            "persona": list(envelope.PERSONA_IDS),
            "profile": list(PROFILE_ORDER),
            "profile_manifests": "persona-then-profile",
            "verification_view_receipts": "persona-id",
        },
        "origin_manifest_bindings": origin_bindings,
        "profile_manifest_bindings": profile_bindings,
        "remaining_blockers": [
            "joint-scope-bucket-cohort-quota-solution-and-proof",
            "solution-compiled-complete-post-W0-membership-and-history-plan",
            "physical-capacity-materialization-and-kio-observation",
            "formal-G0-approval",
        ],
        "summary": {
            "compact_companion_mirror_count": sum(row["summary"]["compact_companion_mirror_count"] for row in origins),
            "compact_primary_override_count": sum(row["summary"]["compact_primary_override_count"] for row in origins),
            "compact_row_count": sum(row["body_descriptor"]["row_count"] for row in origins),
            "compact_shard_receipt_count": sum(row["summary"]["compact_shard_receipt_count"] for row in origins),
            "compact_typed_witness_count": sum(row["summary"]["compact_typed_witness_count"] for row in origins),
            "content_projection_count": len(projections),
            "effective_w0_mode_counts": mode_counts,
            "event_created_lineage_count": sum(row["event_created_lineage_row_count"] for row in receipts),
            "inverted_consumer_reference_count": 2 * sum(row["inverted_witness_row_count"] for row in receipts),
            "inverted_witness_count": sum(row["inverted_witness_row_count"] for row in receipts),
            "origin_manifest_count": len(origins),
            "persona_count": len(envelope.PERSONA_IDS),
            "present_fact_reference_count": audited_fact_reference_count,
            "profile_manifest_count": len(profiles),
            "source_count": audited_source_count,
        },
        "verification_view_receipts": receipts,
    }
    summary = value["summary"]
    if (
        summary["compact_row_count"] != EXPECTED_COMPACT_ROW_COUNT
        or summary["compact_shard_receipt_count"] != EXPECTED_SHARD_RECEIPT_COUNT
        or summary["compact_primary_override_count"] != EXPECTED_PRIMARY_OVERRIDE_COUNT
        or summary["compact_companion_mirror_count"] != EXPECTED_COMPANION_MIRROR_COUNT
        or summary["compact_typed_witness_count"] != EXPECTED_TYPED_WITNESS_COUNT
        or summary["source_count"] != EXPECTED_SOURCE_COUNT
        or summary["present_fact_reference_count"] != EXPECTED_PRESENT_FACT_REFERENCE_COUNT
        or summary["event_created_lineage_count"] != EXPECTED_EVENT_CREATED_LINEAGE_COUNT
        or summary["inverted_witness_count"] != EXPECTED_INVERTED_WITNESS_COUNT
        or summary["inverted_consumer_reference_count"] != EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT
        or summary["content_projection_count"] != len(envelope.PERSONA_IDS)
        or mode_counts != EXPECTED_W0_MODE_COUNTS
    ):
        _fail("effective-membership suite exact aggregate drifted")
    observed_maxima = {
        "compact-row": max(
            row["body_descriptor"]["maximum_row_bytes_including_lf"]
            for row in origins
        ),
        "content-projection": max(
            len(canonical_json_bytes(row)) for row in projections
        ),
        "event-lineage-row": max(
            row["event_created_lineage_maximum_row_bytes_including_lf"]
            for row in receipts
        ),
        "expanded-row": max(
            row["summary"]["maximum_expanded_row_bytes_including_lf"]
            for row in origins
        ),
        "inverted-row": max(
            row["inverted_witness_maximum_row_bytes_including_lf"]
            for row in receipts
        ),
        "origin-manifest": max(
            len(canonical_json_bytes(row)) for row in origins
        ),
        "profile-manifest": max(
            len(canonical_json_bytes(row)) for row in profiles
        ),
    }
    expected_maxima = {
        "compact-row": EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        "content-projection": EXPECTED_MAX_CONTENT_PROJECTION_BYTES,
        "event-lineage-row": EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        "expanded-row": EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
        "inverted-row": EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
        "origin-manifest": EXPECTED_MAX_ORIGIN_MANIFEST_BYTES,
        "profile-manifest": EXPECTED_MAX_PROFILE_MANIFEST_BYTES,
    }
    if observed_maxima != expected_maxima:
        _fail("effective-membership observed canonical maxima drifted")
    sentinel_bodies = (
        (
            lifecycle_effective_membership_origin_body_bytes("p01", "pilot"),
            EXPECTED_P01_PILOT_COMPACT_BODY_BYTES,
            EXPECTED_P01_PILOT_COMPACT_BODY_SHA256,
        ),
        (
            lifecycle_effective_membership_origin_body_bytes(
                "p12", "full-residual"
            ),
            EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES,
            EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256,
        ),
    )
    if any(
        len(body) != expected_bytes or _sha256(body) != expected_sha256
        for body, expected_bytes, expected_sha256 in sentinel_bodies
    ):
        _fail("effective-membership representative compact body pin drifted")
    p01_projection_raw = canonical_json_bytes(
        _canonical_content_projection("p01")
    )
    if (
        len(p01_projection_raw) != EXPECTED_P01_CONTENT_PROJECTION_BYTES
        or _sha256(p01_projection_raw)
        != EXPECTED_P01_CONTENT_PROJECTION_SHA256
    ):
        _fail("p01 effective-membership content projection pin drifted")
    _require_negative_authority(value, label="effective-membership suite")
    suite_raw = canonical_json_bytes(value)
    if (
        len(suite_raw) != EXPECTED_SUITE_CANONICAL_BYTES
        or _sha256(suite_raw) != EXPECTED_SUITE_SHA256
    ):
        _fail("effective-membership suite canonical pin drifted")
    return value


def build_lifecycle_effective_membership_suite_descriptor():
    return copy.deepcopy(_canonical_suite_descriptor())


@_detached_lru_cache(maxsize=20)
def _canonical_content_projection(persona_id):
    _require_persona_id(persona_id)
    plan = _persona_plan(persona_id)
    primary_rows = []
    for source in plan["primary_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_PRIMARY_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "effective-primary-membership-content"
        if set(row) != CONTENT_PRIMARY_ROW_FIELDS:
            _fail("primary content projection row schema drifted")
        primary_rows.append(row)
    companion_rows = []
    for source in plan["companion_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_COMPANION_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "effective-companion-membership-content"
        if set(row) != CONTENT_COMPANION_ROW_FIELDS:
            _fail("companion content projection row schema drifted")
        companion_rows.append(row)
    witness_rows = []
    for source in plan["typed_witness_rows"]:
        row = {
            key: copy.deepcopy(source[key])
            for key in CONTENT_WITNESS_ROW_FIELDS
            if key != "row_kind"
        }
        row["row_kind"] = "typed-purge-witness-content"
        if set(row) != CONTENT_WITNESS_ROW_FIELDS:
            _fail("witness content projection row schema drifted")
        witness_rows.append(row)
    shard_rows = []
    for origin in ORIGIN_ORDER:
        for source in _canonical_origin_rows(persona_id, origin):
            if source["row_kind"] != "effective-w0-expanded-shard-receipt":
                continue
            row = {
                "body_bytes": source["expanded_body_bytes"],
                "body_sha256": source["expanded_body_sha256"],
                "first_intent_key": source["first_intent_key"],
                "last_intent_key": source["last_intent_key"],
                "origin": source["origin"],
                "row_count": source["row_count"],
                "row_kind": "effective-membership-shard-content-commitment",
                "source_shard_id": source["source_shard_id"],
            }
            if set(row) != CONTENT_SHARD_COMMITMENT_FIELDS:
                _fail("effective shard content receipt schema drifted")
            shard_rows.append(row)
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "content_rules": {
            "base_content_context_membership_fields_must_be_removed": True,
            "effective_membership_is_single_namespace_owner": True,
            "event_and_inverted_views_are-input-closure-only": True,
            "projection_excludes": [
                "base-fact-profile-pointers",
                "completion-and-review-state",
                "derivation-and-verification-view-receipts",
                "execution-and-capacity-state",
                "full-upstream-bindings-and-digests",
                "physical-scope-path-quota-and-identifiers",
                "query-oracle-answer-relevance-use-case-and-format-selection",
                "runtime-observations",
            ],
        },
        "content_sections": {
            "effective_companion_membership_rows": companion_rows,
            "effective_membership_shard_commitments": shard_rows,
            "effective_primary_membership_rows": primary_rows,
            "typed_purge_witness_rows": witness_rows,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "persona_id": persona_id,
        "summary": {
            "companion_membership_row_count": len(companion_rows),
            "effective_shard_commitment_count": len(shard_rows),
            "primary_membership_row_count": len(primary_rows),
            "typed_purge_witness_row_count": len(witness_rows),
        },
    }
    raw = canonical_json_bytes(value)
    if len(raw) > TARGET_CONTENT_PROJECTION_BYTES:
        _fail("effective-membership content projection exceeds its 256-KiB target")
    return value


def build_lifecycle_effective_membership_content_projection(persona_id):
    return copy.deepcopy(_canonical_content_projection(persona_id))


def canonical_json_bytes(value):
    """Canonicalize one schema-dispatched reconciliation artifact."""

    if type(value) is not dict:
        _fail("lifecycle effective-membership artifact must be an object")
    schema = value.get("artifact_schema")
    labels = {
        ORIGIN_SCHEMA: (
            "persona v2 lifecycle effective-membership origin manifest",
            MAX_ORIGIN_MANIFEST_BYTES,
        ),
        PROFILE_SCHEMA: (
            "persona v2 lifecycle effective-membership profile manifest",
            MAX_PROFILE_MANIFEST_BYTES,
        ),
        SUITE_SCHEMA: (
            "persona v2 lifecycle effective-membership suite",
            MAX_SUITE_DESCRIPTOR_BYTES,
        ),
        PROJECTION_SCHEMA: (
            "persona v2 lifecycle effective-membership content projection",
            MAX_CONTENT_PROJECTION_BYTES,
        ),
    }
    if schema not in labels:
        _fail(f"unknown lifecycle effective-membership schema: {schema!r}")
    label, maximum = labels[schema]
    return canonical_fragment_bytes(value, label=label, max_bytes=maximum)


def _independent_validator():
    try:
        from . import persona_v2_lifecycle_effective_membership_reconciliation_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_lifecycle_effective_membership_reconciliation_validator as independent
        except ImportError:
            independent = None
    return independent


def _require_independent_validator():
    independent = _independent_validator()
    if independent is None:
        _fail(
            "the producer-independent effective-membership validator is required"
        )
    return independent


def validate_lifecycle_effective_membership_origin_manifest(
    persona_id, origin, value
):
    _require_persona_id(persona_id)
    _require_origin(origin)
    independent = _require_independent_validator()
    try:
        independent.validate_lifecycle_effective_membership_origin_manifest(
            persona_id,
            origin,
            value,
            compact_body_provider=lifecycle_effective_membership_origin_body_bytes,
            expanded_w0_body_provider=expanded_effective_w0_membership_shard_body_bytes,
        )
    except independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError as error:
        _fail(str(error))
    return True


def validate_lifecycle_effective_membership_profile_manifest(
    persona_id, profile, value
):
    _require_persona_id(persona_id)
    _require_profile(profile)
    independent = _require_independent_validator()
    try:
        independent.validate_lifecycle_effective_membership_profile_manifest(
            persona_id, profile, value
        )
    except independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError as error:
        _fail(str(error))
    return True


def validate_lifecycle_effective_membership_suite_descriptor(value):
    independent = _require_independent_validator()
    try:
        independent.validate_lifecycle_effective_membership_suite_descriptor(
            value,
            origin_manifest_provider=build_lifecycle_effective_membership_origin_manifest,
            profile_manifest_provider=build_lifecycle_effective_membership_profile_manifest,
            compact_body_provider=lifecycle_effective_membership_origin_body_bytes,
            expanded_w0_body_provider=expanded_effective_w0_membership_shard_body_bytes,
            event_lineage_provider=lifecycle_effective_membership_event_created_lineage_body_bytes,
            inverted_provider=lifecycle_effective_membership_inverted_witness_body_bytes,
            content_projection_provider=build_lifecycle_effective_membership_content_projection,
        )
    except independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError as error:
        _fail(str(error))
    return True


def validate_lifecycle_effective_membership_content_projection(
    persona_id, value
):
    _require_persona_id(persona_id)
    independent = _require_independent_validator()
    try:
        independent.validate_lifecycle_effective_membership_content_projection(
            persona_id, value
        )
    except independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError as error:
        _fail(str(error))
    return True


def lifecycle_effective_membership_origin_manifest_sha256(
    persona_id, origin, value=None
):
    if value is None:
        value = build_lifecycle_effective_membership_origin_manifest(
            persona_id, origin
        )
    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    validate_lifecycle_effective_membership_origin_manifest(
        persona_id, origin, snapshot
    )
    return _sha256(raw)


def lifecycle_effective_membership_profile_manifest_sha256(
    persona_id, profile, value=None
):
    if value is None:
        value = build_lifecycle_effective_membership_profile_manifest(
            persona_id, profile
        )
    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    validate_lifecycle_effective_membership_profile_manifest(
        persona_id, profile, snapshot
    )
    return _sha256(raw)


def lifecycle_effective_membership_suite_sha256(value=None):
    if value is None:
        value = build_lifecycle_effective_membership_suite_descriptor()
    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    validate_lifecycle_effective_membership_suite_descriptor(snapshot)
    return _sha256(raw)


def lifecycle_effective_membership_content_projection_sha256(
    persona_id, value=None
):
    if value is None:
        value = build_lifecycle_effective_membership_content_projection(persona_id)
    raw = canonical_json_bytes(value)
    snapshot = json.loads(raw)
    validate_lifecycle_effective_membership_content_projection(
        persona_id, snapshot
    )
    return _sha256(raw)


def require_solution_compiled_history_and_execution():
    raise PersonaV2LifecycleEffectiveMembershipReconciliationError(
        "effective W0 lifecycle membership and purge-witness isolation are exact, "
        "but joint solving, complete post-W0 membership, compiled history, "
        "physical materialization, capacity/KIO observations, and G0 authority "
        "remain downstream"
    )


__all__ = [
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "COMPANION_MIRROR_ROW_FIELDS",
    "CONTENT_COMPANION_ROW_FIELDS",
    "CONTENT_PRIMARY_ROW_FIELDS",
    "CONTENT_SHARD_COMMITMENT_FIELDS",
    "CONTENT_WITNESS_ROW_FIELDS",
    "EVENT_LINEAGE_ROW_FIELDS",
    "EXPANDED_W0_ROW_FIELDS",
    "EXPECTED_COMPACT_ROW_COUNT",
    "EXPECTED_COMPANION_MIRROR_COUNT",
    "EXPECTED_EVENT_CREATED_LINEAGE_COUNT",
    "EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT",
    "EXPECTED_INVERTED_WITNESS_COUNT",
    "EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF",
    "EXPECTED_MAX_CONTENT_PROJECTION_BYTES",
    "EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF",
    "EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF",
    "EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF",
    "EXPECTED_MAX_ORIGIN_MANIFEST_BYTES",
    "EXPECTED_MAX_PROFILE_MANIFEST_BYTES",
    "EXPECTED_P01_CONTENT_PROJECTION_BYTES",
    "EXPECTED_P01_CONTENT_PROJECTION_SHA256",
    "EXPECTED_P01_PILOT_COMPACT_BODY_BYTES",
    "EXPECTED_P01_PILOT_COMPACT_BODY_SHA256",
    "EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES",
    "EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256",
    "EXPECTED_PRESENT_FACT_REFERENCE_COUNT",
    "EXPECTED_PRIMARY_OVERRIDE_COUNT",
    "EXPECTED_SHARD_RECEIPT_COUNT",
    "EXPECTED_SOURCE_COUNT",
    "EXPECTED_SUITE_CANONICAL_BYTES",
    "EXPECTED_SUITE_SHA256",
    "EXPECTED_TYPED_WITNESS_COUNT",
    "EXPECTED_W0_FACT_DISTRIBUTION",
    "EXPECTED_W0_MODE_COUNTS",
    "INVERTED_WITNESS_ROW_FIELDS",
    "MAX_COMPACT_ROW_BYTES_INCLUDING_LF",
    "MAX_CONTENT_PROJECTION_BYTES",
    "MAX_EVENT_LINEAGE_BODY_BYTES",
    "MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_ROW_BYTES_INCLUDING_LF",
    "MAX_EXPANDED_SHARD_BODY_BYTES",
    "MAX_INVERTED_BODY_BYTES",
    "MAX_INVERTED_ROW_BYTES_INCLUDING_LF",
    "MAX_ORIGIN_BODY_BYTES",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_ORIGIN_ROWS",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_SUITE_DESCRIPTOR_BYTES",
    "ORIGIN_ORDER",
    "ORIGIN_SCHEMA",
    "PROFILE_ORDER",
    "PROFILE_SCHEMA",
    "PRIMARY_OVERRIDE_ROW_FIELDS",
    "PROJECTION_SCHEMA",
    "PersonaV2LifecycleEffectiveMembershipReconciliationError",
    "SHARD_RECEIPT_ROW_FIELDS",
    "SUITE_SCHEMA",
    "TARGET_CONTENT_PROJECTION_BYTES",
    "TYPED_WITNESS_ROW_FIELDS",
    "build_lifecycle_effective_membership_content_projection",
    "build_lifecycle_effective_membership_origin_manifest",
    "build_lifecycle_effective_membership_profile_manifest",
    "build_lifecycle_effective_membership_suite_descriptor",
    "canonical_fragment_bytes",
    "canonical_json_bytes",
    "event_created_witness_lineage_body_bytes",
    "expanded_effective_w0_membership_shard_body_bytes",
    "inverted_purge_witness_body_bytes",
    "iter_event_created_witness_lineage_rows",
    "iter_expanded_effective_w0_membership_rows",
    "iter_inverted_purge_witness_rows",
    "iter_lifecycle_effective_membership_origin_rows",
    "lifecycle_effective_membership_content_projection_sha256",
    "lifecycle_effective_membership_event_created_lineage_body_bytes",
    "lifecycle_effective_membership_inverted_witness_body_bytes",
    "lifecycle_effective_membership_origin_body_bytes",
    "lifecycle_effective_membership_origin_manifest_sha256",
    "lifecycle_effective_membership_profile_manifest_sha256",
    "lifecycle_effective_membership_suite_sha256",
    "require_solution_compiled_history_and_execution",
    "validate_lifecycle_effective_membership_content_projection",
    "validate_lifecycle_effective_membership_origin_manifest",
    "validate_lifecycle_effective_membership_profile_manifest",
    "validate_lifecycle_effective_membership_suite_descriptor",
]
