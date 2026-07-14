"""Exact W0 fact-membership projection for persona-PC fidelity v2.

The source-intent origin shard is the sole owner of ``present_fact_ids``.
This sidecar projects that complete W0 set onto one logical document, one
ordered semantic branch, the applicable typed revision chain, and section
memberships.  It never invents, drops, or independently owns a fact.

Only one pilot-origin representative intent per persona is covered.  Its bound
graph now contains one unequal W0-current unordered conflict pair, and this
sidecar projects that pair without inventing facts.  It does not assign the two
facts to distinct branches; full overlay membership is still absent.  It grants
no source-plan, G0, filesystem, history, query, or evaluation authority.
"""

from __future__ import annotations

import copy
import functools
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_source_intent as source_intent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_source_intent as source_intent


ARTIFACT_SCHEMA = "kcs.persona.pc-fact-membership/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-fact-membership"
MAX_FACT_MEMBERSHIP_BYTES = 128 * 1024
EXPECTED_REPRESENTATIVE_INTENT_COUNT = 1

_PROHIBITED_KEYS = frozenset(
    (
        "absolute_path",
        "answer_key",
        "chunk_id",
        "distractor_key",
        "event_id",
        "final_materialization_id",
        "final_source_id",
        "history_event_id",
        "materialization_id",
        "query_key",
        "query_text",
        "rank",
        "raw_sha256",
        "relative_path",
        "rendered_text",
        "score",
        "source_id",
    )
)


class PersonaV2FactMembershipError(ValueError):
    """Raised when membership differs from its source-intent-owned fact set."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2FactMembershipError(f"unknown persona: {persona_id!r}")
    return persona_id


def _canonical_fact_ids(fact_ids, *, label):
    if (
        type(fact_ids) is not list
        or not fact_ids
        or any(type(fact_id) is not str or not fact_id for fact_id in fact_ids)
        or fact_ids != sorted(fact_ids)
        or len(fact_ids) != len(set(fact_ids))
    ):
        raise PersonaV2FactMembershipError(
            f"{label} must be a non-empty sorted unique fact-ID list"
        )
    return list(fact_ids)


def validate_exact_present_fact_projection(
    source_present_fact_ids,
    membership_present_fact_ids,
    section_memberships,
):
    """Require total-set equality across source, membership, and sections."""

    source_ids = _canonical_fact_ids(
        source_present_fact_ids, label="source-intent present fact set"
    )
    membership_ids = _canonical_fact_ids(
        membership_present_fact_ids, label="membership present fact set"
    )
    if membership_ids != source_ids:
        raise PersonaV2FactMembershipError(
            "fact membership must exactly equal the source-intent-owned present set"
        )
    if type(section_memberships) is not list or len(section_memberships) != len(
        source_ids
    ):
        raise PersonaV2FactMembershipError(
            "section memberships must cover every present fact exactly once"
        )
    section_fact_ids = []
    section_keys = []
    for row in section_memberships:
        if type(row) is not dict or set(row) != {"fact_id", "section_key"}:
            raise PersonaV2FactMembershipError("section membership shape drifted")
        if type(row["section_key"]) is not str or not row["section_key"]:
            raise PersonaV2FactMembershipError("section key must be a string")
        section_fact_ids.append(row["fact_id"])
        section_keys.append(row["section_key"])
    if section_fact_ids != source_ids or len(section_keys) != len(set(section_keys)):
        raise PersonaV2FactMembershipError(
            "section membership must be ordered, total, unique, and exact"
        )
    return True


def _assert_no_prohibited_keys(value):
    if type(value) is list:
        for item in value:
            _assert_no_prohibited_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _PROHIBITED_KEYS:
            raise PersonaV2FactMembershipError(f"prohibited membership field: {key}")
        _assert_no_prohibited_keys(item)


def _sha256_paths(value, path=()):
    result = set()
    if type(value) is dict:
        for key, item in value.items():
            child = path + (key,)
            if key == "sha256" or key.endswith("_sha256"):
                result.add(child)
            result.update(_sha256_paths(item, child))
    elif type(value) is list:
        for item in value:
            result.update(_sha256_paths(item, path + ("[]",)))
    return frozenset(result)


def _dependency_binding(name, role, persona_id, value, *, validate, canonical, digest):
    validate(persona_id, value)
    raw = canonical(value)
    actual_digest = digest(persona_id, value)
    if hashlib.sha256(raw).hexdigest() != actual_digest:
        raise PersonaV2FactMembershipError(f"{name} binding digest drifted")
    if value.get("fixture_id") != envelope.FIXTURE_ID:
        raise PersonaV2FactMembershipError(f"{name} fixture identity drifted")
    authority = value.get("authority")
    if type(authority) is not dict or not authority or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        raise PersonaV2FactMembershipError(
            f"{name} dependency must remain non-authorizing"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "persona_id": persona_id,
        "sha256": actual_digest,
    }


def _fact_state_at_checkpoint(fact, checkpoint):
    matches = [
        row["state"]
        for row in fact["visibility_by_checkpoint"]
        if row["checkpoint"] == checkpoint
    ]
    if len(matches) != 1:
        raise PersonaV2FactMembershipError("fact checkpoint visibility is incomplete")
    return matches[0]


def _extract_source_projection(persona_id, source_value):
    intents = source_value.get("intent_rows")
    catalogs = source_value.get("catalogs")
    fact_sets = (
        catalogs.get("present_fact_sets") if type(catalogs) is dict else None
    )
    quota_contexts = (
        catalogs.get("quota_contexts") if type(catalogs) is dict else None
    )
    if (
        type(intents) is not list
        or len(intents) != EXPECTED_REPRESENTATIVE_INTENT_COUNT
        or type(fact_sets) is not list
        or len(fact_sets) != EXPECTED_REPRESENTATIVE_INTENT_COUNT
        or type(quota_contexts) is not list
        or len(quota_contexts) != EXPECTED_REPRESENTATIVE_INTENT_COUNT
    ):
        raise PersonaV2FactMembershipError(
            "source-intent candidate must contain one intent and one present fact set"
        )
    intent = intents[0]
    fact_set = fact_sets[0]
    quota_context = quota_contexts[0]
    required_intent_keys = {
        "intent_key",
        "origin",
        "present_fact_set_key",
        "quota_context_id",
    }
    required_set_keys = {
        "present_fact_ids",
        "present_fact_set_key",
        "project_or_case_id",
    }
    if type(intent) is not dict or not required_intent_keys <= set(intent):
        raise PersonaV2FactMembershipError("source intent projection fields are missing")
    if type(fact_set) is not dict or not required_set_keys <= set(fact_set):
        raise PersonaV2FactMembershipError("source present-fact set fields are missing")
    if (
        type(quota_context) is not dict
        or not {"allowed_history_cohort_ids", "quota_context_id"}
        <= set(quota_context)
        or intent["quota_context_id"] != quota_context["quota_context_id"]
    ):
        raise PersonaV2FactMembershipError("source quota context is unresolved")
    if intent["present_fact_set_key"] != fact_set["present_fact_set_key"]:
        raise PersonaV2FactMembershipError("source present-fact reference is unresolved")
    if intent["intent_key"] != f"{persona_id}-intent-pilot-syn-0001":
        raise PersonaV2FactMembershipError("representative intent key drifted")
    if intent["origin"] != "pilot":
        raise PersonaV2FactMembershipError("representative origin must remain pilot")
    if quota_context["allowed_history_cohort_ids"] != ["P", "X", "Y"]:
        raise PersonaV2FactMembershipError(
            "W0 revision membership must be restricted to W1-edit cohorts P/X/Y"
        )
    return intent, fact_set, quota_context["allowed_history_cohort_ids"]


def _canonical_fact_membership(persona_id, *, graph_value=None, source_value=None):
    _require_persona_id(persona_id)
    graph = fact_graph.build_fact_graph(persona_id) if graph_value is None else graph_value
    source = (
        source_intent.build_source_intent_origin_shard(persona_id)
        if source_value is None
        else source_value
    )
    fact_graph.validate_fact_graph(persona_id, graph)
    source_intent.validate_source_intent_origin_shard(persona_id, source)
    intent, fact_set, allowed_history_cohort_ids = _extract_source_projection(
        persona_id, source
    )
    present_fact_ids = _canonical_fact_ids(
        fact_set["present_fact_ids"], label="source W0 present fact set"
    )

    matching_graphs = [
        row
        for row in graph["graphs"]
        if row["project_or_case_id"] == fact_set["project_or_case_id"]
    ]
    if len(matching_graphs) != 1:
        raise PersonaV2FactMembershipError(
            "source project/case must resolve to exactly one bound fact graph"
        )
    selected_graph = matching_graphs[0]
    graph_fact_ids = {row["fact_id"] for row in selected_graph["facts"]}
    if not set(present_fact_ids) <= graph_fact_ids:
        raise PersonaV2FactMembershipError("source membership references a foreign fact")
    expected_w0 = sorted(
        row["fact_id"]
        for row in selected_graph["facts"]
        if _fact_state_at_checkpoint(row, "W0") == "current"
    )
    if present_fact_ids != expected_w0:
        raise PersonaV2FactMembershipError(
            "source-intent W0 set must equal all and only W0-current graph facts"
        )

    revision_memberships = copy.deepcopy(selected_graph["revision_chains"])
    if len(revision_memberships) != 1:
        raise PersonaV2FactMembershipError(
            "representative graph must expose exactly one typed revision chain"
        )
    revision = revision_memberships[0]
    if (
        not set(revision["prior_fact_ids"]) <= set(present_fact_ids)
        or revision["current_fact_id"] in present_fact_ids
    ):
        raise PersonaV2FactMembershipError(
            "W0 membership must contain revision prior facts and exclude replacement"
        )

    conflict_memberships = copy.deepcopy(selected_graph["conflict_sets"])
    if len(conflict_memberships) != 1:
        raise PersonaV2FactMembershipError(
            "representative graph must expose exactly one unordered conflict set"
        )
    conflict_member_ids = conflict_memberships[0]["member_fact_ids"]
    if not set(conflict_member_ids) <= set(present_fact_ids):
        raise PersonaV2FactMembershipError(
            "W0 membership must contain both unordered conflict facts"
        )

    section_memberships = [
        {
            "fact_id": fact_id,
            "section_key": f"{persona_id}-section-syn-{ordinal:04d}",
        }
        for ordinal, fact_id in enumerate(present_fact_ids, start=1)
    ]
    validate_exact_present_fact_projection(
        fact_set["present_fact_ids"], present_fact_ids, section_memberships
    )
    member = {
        "allowed_history_cohort_ids": copy.deepcopy(allowed_history_cohort_ids),
        "branch_key": f"{persona_id}-branch-main-syn-0001",
        "unordered_w0_current_fact_pairs": conflict_memberships,
        "intent_key": intent["intent_key"],
        "logical_document_key": f"{persona_id}-logical-document-syn-0001",
        "origin": intent["origin"],
        "present_fact_ids": present_fact_ids,
        "present_fact_set_key": intent["present_fact_set_key"],
        "project_or_case_id": fact_set["project_or_case_id"],
        "revision_memberships": revision_memberships,
        "section_memberships": section_memberships,
    }
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kcs_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_FACT_MEMBERSHIP_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_scope": (
            "one-pilot-origin-w0-exact-membership-projection-per-persona-only-"
            "with-conflict-fact-precondition-no-full-overlay-no-oracle-no-history-plan"
        ),
        "conflict_copy_feasibility": {
            "conflict_overlay_membership_complete": False,
            "distinct_conflict_branch_membership_complete": False,
            "existing_unordered_w0_current_conflict_fact_pair_count": len(
                conflict_memberships
            ),
            "fact_invention_allowed": False,
            "requires_same_subject_predicate_unequal_typed_values": True,
            "requires_two_distinct_unordered_w0_current_branches": True,
            "unordered_w0_current_fact_pair_precondition_complete": True,
        },
        "fact_membership_inventory_complete": False,
        "fact_oracle_input_closure_complete": False,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "history_intent_recipe_bound": False,
        "hypothesis_status": "candidate-planning-only-non-authorizing",
        "input_bindings": [
            _dependency_binding(
                "fact-graph",
                "typed-fact-inventory",
                persona_id,
                graph,
                validate=fact_graph.validate_fact_graph,
                canonical=fact_graph.canonical_json_bytes,
                digest=fact_graph.fact_graph_sha256,
            ),
            _dependency_binding(
                "source-intent-origin-shard",
                "present-fact-set-owner",
                persona_id,
                source,
                validate=source_intent.validate_source_intent_origin_shard,
                canonical=source_intent.canonical_json_bytes,
                digest=source_intent.source_intent_origin_shard_sha256,
            ),
        ],
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "network_access_allowed": False,
            "runtime_clock_reads_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "memberships": [member],
        "persona_id": persona_id,
        "remaining_blockers": [
            "full-source-intent-inventory-not-present",
            "overlay-instance-membership-not-bound",
            "distinct-conflict-branch-membership-not-bound",
            "history-cohort-scope-quota-and-final-identities-not-solved",
            "restore-delete-query-and-semantic-oracle-anchors-not-bound",
            "compiled-raw-hash-section-relevance-not-present",
            "external-frame-header-schema-dispatcher-not-implemented",
            "bounded-loader-not-bound-to-artifact-frame",
        ],
        "representative_membership_count": 1,
        "representative_vertical_slice_complete": True,
        "source_intent_is_canonical_present_fact_set_owner": True,
    }
    _assert_no_prohibited_keys(value)
    if (
        [row.get("name") for row in value["input_bindings"]]
        != ["fact-graph", "source-intent-origin-shard"]
        or any(
            type(row.get("sha256")) is not str or len(row["sha256"]) != 64
            for row in value["input_bindings"]
        )
    ):
        raise PersonaV2FactMembershipError(
            "fact membership dependency binding cardinality or digest drifted"
        )
    if _sha256_paths(value) != frozenset({("input_bindings", "[]", "sha256")}):
        raise PersonaV2FactMembershipError(
            "fact membership has a missing, downstream, or cyclic SHA binding"
        )
    return value


@functools.lru_cache(maxsize=1)
def _canonical_suite_values():
    graph_values = fact_graph.build_fact_graph_suite()
    source_values = source_intent.build_source_intent_origin_shard_suite()
    if (
        [value["persona_id"] for value in graph_values]
        != list(envelope.PERSONA_IDS)
        or [value["persona_id"] for value in source_values]
        != list(envelope.PERSONA_IDS)
    ):
        raise PersonaV2FactMembershipError("dependency suite persona order drifted")
    values = tuple(
        _canonical_fact_membership(
            persona_id,
            graph_value=graph_value,
            source_value=source_value,
        )
        for persona_id, graph_value, source_value in zip(
            envelope.PERSONA_IDS, graph_values, source_values
        )
    )
    if tuple(value["persona_id"] for value in values) != envelope.PERSONA_IDS:
        raise PersonaV2FactMembershipError("membership suite persona order drifted")
    return values


def build_fact_membership(persona_id):
    """Return one detached exact W0 projection with negative authority."""

    _require_persona_id(persona_id)
    index = envelope.PERSONA_IDS.index(persona_id)
    return copy.deepcopy(_canonical_suite_values()[index])


def build_fact_membership_suite():
    """Return all twenty detached candidates in canonical persona order."""

    return copy.deepcopy(list(_canonical_suite_values()))


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 fact membership",
            max_bytes=MAX_FACT_MEMBERSHIP_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactMembershipError(str(error)) from None


def validate_fact_membership(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_fact_membership(persona_id),
            label="persona v2 fact membership",
            max_bytes=MAX_FACT_MEMBERSHIP_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactMembershipError(str(error)) from None


def fact_membership_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_fact_membership(persona_id),
            label="persona v2 fact membership",
            max_bytes=MAX_FACT_MEMBERSHIP_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactMembershipError(str(error)) from None


def require_fact_oracle_input_closure():
    raise PersonaV2FactMembershipError(
        "the representative W0 projection is not full fact/oracle input closure; "
        "full intent, conflict overlay, history, restore/delete, query, and compiled "
        "relevance bindings remain absent"
    )
