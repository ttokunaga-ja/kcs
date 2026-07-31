"""Abstract query-to-lifecycle target resolution for persona-PC fidelity v2.

This evaluation-side candidate binds every authored query intent to exactly one
source-matched lifecycle capability.  The binding is constrained by scenario,
stratum, revision-chain, and rename/move semantics and is solved with a
domain-separated bipartite matcher; it is never an ordinal zip.

The artifact deliberately stops at abstract keys.  In particular, it does not
claim that the currently selected W0 source already contains the oracle fact,
or expose a solved scope/path, final source/materialization/chunk/section ID,
rendered query, compiled event, or KIO observation.  Those facts require the
effective lifecycle membership overlay and the later solver/compiler stages.
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
    from . import persona_v2_query_intent as query_intent
    from . import persona_v2_semantic_oracle as semantic_oracle
    from . import persona_v2_source_matched_lifecycle_inventory as lifecycle
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_query_intent as query_intent
    import persona_v2_semantic_oracle as semantic_oracle
    import persona_v2_source_matched_lifecycle_inventory as lifecycle


ARTIFACT_SCHEMA = "kio.persona.pc-query-history-target-resolution/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-query-history-target-resolution"
MAX_ARTIFACT_BYTES = 8 * 2**20
TARGET_ARTIFACT_BYTES = 6 * 2**20
MAX_EXPANDED_NODE_COUNT = 1_000_000
EXPECTED_CANONICAL_BYTES = 4_478_576
EXPECTED_SHA256 = (
    "8beed1ca21ebe80e029bcd003795306086514adcd852b98a9eed334fcd73f4ff"
)

MATCHING_ALGORITHM = (
    "semantic-class-constrained-domain-separated-sha256-dfs-augmenting-path"
)

# stratum, (capability class, exact per-persona count)
STRATUM_CAPABILITY_COUNTS = (
    (
        "current-fact",
        (("stable-current-default", 9), ("replacement-current-default", 1)),
    ),
    (
        "cross-format-fact",
        (
            ("stable-current-cross-format", 9),
            ("replacement-current-cross-format", 1),
        ),
    ),
    (
        "locale-language-fact",
        (("stable-current-locale", 9), ("replacement-current-locale", 1)),
    ),
    (
        "rename-move",
        (
            ("same-scope-rename", 5),
            ("stable-cross-scope-move", 4),
            ("w1-edited-cross-scope-move", 1),
        ),
    ),
    ("old-wording", (("old-wording-history", 10),)),
    ("locale-language-history", (("locale-history", 10),)),
    ("deleted", (("final-deleted", 10),)),
    ("restored", (("current-restored", 10),)),
    ("locale-language-lifecycle", (("archive-history", 10),)),
    ("purged-negative", (("purged-negative", 15),)),
)

CLASS_EVENT_PROFILES = {
    "stable-current-default": (),
    "stable-current-cross-format": (),
    "stable-current-locale": (),
    "replacement-current-default": ("w1-typed-edit", "w3-surface-edit"),
    "replacement-current-cross-format": (
        "w1-typed-edit",
        "w3-surface-edit",
    ),
    "replacement-current-locale": ("w1-typed-edit", "w3-surface-edit"),
    "same-scope-rename": ("w2-rename",),
    "stable-cross-scope-move": ("w2-move",),
    "w1-edited-cross-scope-move": ("w1-incidental-typed-edit", "w2-move"),
    "old-wording-history": ("w1-typed-edit", "w3-surface-edit"),
    "locale-history": ("w1-typed-edit", "w3-surface-edit"),
    "archive-history": ("w1-typed-edit", "w3-surface-edit", "w4-archive"),
    "final-deleted": (
        "w1-typed-edit",
        "w3-surface-edit",
        "w4-delete",
        "w4-create-x-prime",
    ),
    "current-restored": (
        "w1-typed-edit",
        "w3-surface-edit",
        "w4-delete",
        "w4-create-x-prime",
        "w5-export-x",
        "w5-restore-x",
        "w5-delete-x-prime",
    ),
    "purged-negative": (
        "w1-typed-edit",
        "w5-create-p-prime",
        "w5-purge-p",
    ),
}

_FORBIDDEN_EXACT_KEYS = frozenset(
    {
        "absolute_path",
        "chunk_id",
        "compiled_event_id",
        "final_event_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "normalized_section_id",
        "path",
        "raw_hash",
        "raw_sha256",
        "relative_path",
        "rendered_query",
        "rendered_query_text",
        "scope_id",
        "section_id",
        "solved_path",
        "solved_scope_key",
        "source_id",
    }
)


class PersonaV2QueryHistoryTargetResolutionError(ValueError):
    """Raised when target resolution differs from the exact safe contract."""


def _fail(message):
    raise PersonaV2QueryHistoryTargetResolutionError(message)


def _ascii(value):
    if type(value) is not str:
        _fail("canonical key must be a string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("synthetic key must be ASCII")


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_frozen_raw(raw):
    if (
        type(raw) is not bytes
        or len(raw) != EXPECTED_CANONICAL_BYTES
        or not hmac.compare_digest(_sha256(raw), EXPECTED_SHA256)
    ):
        _fail("target resolution differs from its frozen canonical body pin")


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


def _reject_forbidden_keys(value):
    if type(value) is list:
        for item in value:
            _reject_forbidden_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _FORBIDDEN_EXACT_KEYS:
            _fail("target resolution contains a prohibited concrete identity field")
        _reject_forbidden_keys(item)


def _canonical(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 query history target resolution",
            max_bytes=MAX_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _authority():
    return {
        "actual_history_receipts_attested": False,
        "authorizes_compiled_relevance": False,
        "authorizes_corpus_namespace": False,
        "authorizes_evaluation_publication": False,
        "authorizes_final_identifiers": False,
        "authorizes_g0_freeze": False,
        "authorizes_history_execution": False,
        "authorizes_kio_execution": False,
        "authorizes_physical_write": False,
        "authorizes_query_execution": False,
        "authorizes_query_rendering": False,
        "authorizes_solver_execution": False,
        "authorizes_source_plan": False,
        "compiled_history_plan_available": False,
        "effective_lifecycle_membership_available": False,
        "final_identity_relevance_available": False,
    }


def _binding(name, role, persona_id, value, canonical):
    raw = canonical(value)
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
        "sha256": _sha256(raw),
    }


def _dependency_fingerprint(query_values, oracle_values, lifecycle_values):
    rows = []
    for values, canonical in (
        (query_values, query_intent.canonical_json_bytes),
        (oracle_values, semantic_oracle.canonical_json_bytes),
        (lifecycle_values, lifecycle.canonical_json_bytes),
    ):
        rows.extend(_sha256(canonical(value)) for value in values)
    return tuple(rows)


def _load_dependencies(dependency_observer=None):
    query_values = query_intent.build_query_intent_suite()
    oracle_values = semantic_oracle.build_semantic_oracle_suite()
    lifecycle_values = [
        lifecycle.build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    expected_order = list(envelope.PERSONA_IDS)
    for label, values in (
        ("query", query_values),
        ("oracle", oracle_values),
        ("lifecycle", lifecycle_values),
    ):
        if (
            type(values) is not list
            or len(values) != len(expected_order)
            or [value.get("persona_id") for value in values] != expected_order
        ):
            _fail(f"{label} dependency suite persona order drifted")
    detached = (
        copy.deepcopy(query_values),
        copy.deepcopy(oracle_values),
        copy.deepcopy(lifecycle_values),
    )
    detached_fingerprint = _dependency_fingerprint(*detached)
    opening = _dependency_fingerprint(
        query_values, oracle_values, lifecycle_values
    )
    if not hmac.compare_digest(
        "\x00".join(detached_fingerprint), "\x00".join(opening)
    ):
        _fail("dependency changed while target-resolution snapshot was copied")
    if dependency_observer is not None:
        if not callable(dependency_observer):
            _fail("dependency observer must be callable")
        dependency_observer(query_values, oracle_values, lifecycle_values)
    if opening != _dependency_fingerprint(
        query_values, oracle_values, lifecycle_values
    ):
        _fail("dependency changed during target-resolution snapshot")
    # Re-read every live provider after the snapshot.  Builders return detached
    # values, so equality here also detects a poisoned mutable upstream cache.
    closing_query = query_intent.build_query_intent_suite()
    closing_oracle = semantic_oracle.build_semantic_oracle_suite()
    closing_lifecycle = [
        lifecycle.build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    if opening != _dependency_fingerprint(
        closing_query, closing_oracle, closing_lifecycle
    ):
        _fail("dependency changed between target-resolution reads")
    return detached


def _oracle_by_query(query_value, oracle_value):
    queries = (
        query_value["positive_query_intents"]
        + query_value["negative_query_intents"]
    )
    oracle_rows = (
        oracle_value["positive_oracle_rows"]
        + oracle_value["negative_oracle_rows"]
    )
    by_query = {row["query_intent_key"]: row for row in oracle_rows}
    if (
        len(queries) != 105
        or len(by_query) != 105
        or {row["query_key"] for row in queries} != set(by_query)
    ):
        _fail("query/oracle membership is not an exact 105-row join")
    return queries, by_query


def _expected_revision_chain_ids(oracle_row):
    membership = oracle_row["abstract_answer_membership"]
    if membership == []:
        return []
    return membership["expected_revision_chain_ids"]


def _semantic_class(query_row, oracle_row):
    stratum = query_row["stratum_id"]
    revisions = _expected_revision_chain_ids(oracle_row)
    if stratum == "purged-negative":
        if oracle_row["expected_empty"] is not True or revisions:
            _fail("purged-negative semantics drifted")
        return "purged-negative", "purged-negative-empty-answer"
    if query_row["expected_empty"] is not False or oracle_row["expected_empty"] is not False:
        _fail("positive target unexpectedly claims an empty answer")
    if stratum in {
        "current-fact",
        "cross-format-fact",
        "locale-language-fact",
    }:
        suffix = {
            "current-fact": "default",
            "cross-format-fact": "cross-format",
            "locale-language-fact": "locale",
        }[stratum]
        if revisions:
            return (
                f"replacement-current-{suffix}",
                "current-answer-is-current-endpoint-of-revision-chain",
            )
        return (
            f"stable-current-{suffix}",
            "current-answer-has-no-revision-chain",
        )
    if stratum == "rename-move":
        operation = oracle_row["evidence_contract"].get("operation_kind")
        if operation == "same-scope-rename":
            if revisions:
                _fail("same-scope rename unexpectedly requires a W1 edit")
            return "same-scope-rename", "oracle-operation-same-scope-rename"
        if operation == "searchable-cross-scope-move":
            if revisions:
                return (
                    "w1-edited-cross-scope-move",
                    "cross-scope-move-with-revision-chain",
                )
            return (
                "stable-cross-scope-move",
                "cross-scope-move-without-revision-chain",
            )
        _fail("rename/move oracle lacks an exact operation kind")
    direct = {
        "old-wording": "old-wording-history",
        "locale-language-history": "locale-history",
        "deleted": "final-deleted",
        "restored": "current-restored",
        "locale-language-lifecycle": "archive-history",
    }
    if stratum not in direct:
        _fail("query stratum has no lifecycle semantic class")
    return direct[stratum], f"exact-stratum-{stratum}"


def _match_score(persona_id, query_row, capability_row):
    material = (
        "persona-v2-query-history-target-resolution-v1\x00"
        + persona_id
        + "\x00"
        + query_row["target_intent_key"]
        + "\x00"
        + capability_row["capability_key"]
    ).encode("ascii", "strict")
    return hashlib.sha256(material).digest()


def _bipartite_match(persona_id, query_rows, capability_rows):
    by_class_queries = {}
    by_class_capabilities = {}
    semantic_evidence = {}
    for query_row, oracle_row in query_rows:
        class_key, rule_id = _semantic_class(query_row, oracle_row)
        by_class_queries.setdefault(class_key, []).append(query_row)
        semantic_evidence[query_row["query_key"]] = rule_id
    for capability_row in capability_rows:
        by_class_capabilities.setdefault(
            capability_row["capability_class_key"], []
        ).append(capability_row)
    expected_counts = {
        class_key: count
        for _stratum, class_rows in STRATUM_CAPABILITY_COUNTS
        for class_key, count in class_rows
    }
    if set(by_class_queries) != set(expected_counts) or set(
        by_class_capabilities
    ) != set(expected_counts):
        _fail("query and lifecycle capability class domains differ")
    if any(
        len(by_class_queries[class_key]) != count
        or len(by_class_capabilities[class_key]) != count
        for class_key, count in expected_counts.items()
    ):
        _fail("semantic class cardinality table is not exact")

    result = {}
    for class_key in sorted(expected_counts, key=_ascii):
        queries = sorted(
            by_class_queries[class_key],
            key=lambda row: hashlib.sha256(
                ("left-order\x00" + row["target_intent_key"]).encode("ascii")
            ).digest(),
        )
        capabilities = by_class_capabilities[class_key]
        right_owner = {}

        def augment(query_row, seen):
            candidates = sorted(
                capabilities,
                key=lambda row: (
                    _match_score(persona_id, query_row, row),
                    _ascii(row["capability_key"]),
                ),
            )
            for capability_row in candidates:
                capability_key = capability_row["capability_key"]
                if capability_key in seen:
                    continue
                seen.add(capability_key)
                previous = right_owner.get(capability_key)
                if previous is None or augment(previous, seen):
                    right_owner[capability_key] = query_row
                    return True
            return False

        if not all(augment(query_row, set()) for query_row in queries):
            _fail("semantic-class bipartite matching is incomplete")
        capability_by_key = {
            row["capability_key"]: row for row in capabilities
        }
        for capability_key, query_row in right_owner.items():
            result[query_row["query_key"]] = (
                capability_by_key[capability_key],
                semantic_evidence[query_row["query_key"]],
            )
    if len(result) != 105:
        _fail("query-to-capability matching is not bijective")
    return result


def _event_template_rows(evidence):
    rows = []
    for key in sorted(evidence, key=_ascii):
        if key.endswith("_event_template_key"):
            rows.append({"field": key, "template_key": evidence[key]})
    return rows


def _answer_contract(oracle_row):
    membership = oracle_row["abstract_answer_membership"]
    if membership == []:
        return {
            "answer_membership_key": "not-applicable-purged-negative",
            "expected_fact_ids": [],
            "expected_revision_chain_ids": [],
            "status": "expected-empty",
        }
    return {
        "answer_membership_key": membership["answer_membership_key"],
        "expected_fact_ids": list(membership["expected_fact_ids"]),
        "expected_revision_chain_ids": list(
            membership["expected_revision_chain_ids"]
        ),
        "status": "abstract-oracle-membership-only",
    }


def _distractor_contract(oracle_row):
    distractors = oracle_row.get("distractors", [])
    answer = _answer_contract(oracle_row)
    fact_ids = [row["distractor_fact_id"] for row in distractors]
    intent_keys = [row["distractor_intent_key"] for row in distractors]
    logical_keys = [
        row["distractor_logical_document_key"] for row in distractors
    ]
    if set(answer["expected_fact_ids"]) & set(fact_ids):
        _fail("one query answer fact overlaps its distractor facts")
    if len(intent_keys) != len(set(intent_keys)) or len(logical_keys) != len(
        set(logical_keys)
    ):
        _fail("one query contains duplicate distractor keys")
    return {
        "distractor_fact_ids": fact_ids,
        "distractor_intent_keys": intent_keys,
        "distractor_logical_document_keys": logical_keys,
        "mapped_source_intent_keys": [],
        "per_query_answer_fact_disjoint": True,
        "reference_kind": "abstract-semantic-oracle-reference",
        "source_mapping_resolved": False,
        "source_mapping_status": "pending-distinct-source-intent-resolution",
    }


def _companion_contract(capability_row, companion_by_capability):
    row = companion_by_capability.get(capability_row["capability_key"])
    if row is None:
        return {"status": "not-required"}
    if row["intent_key"] == capability_row["intent_key"]:
        _fail("primary and companion source intent keys overlap")
    return {
        "companion_requirement_key": row["companion_requirement_key"],
        "rendition_group_key": row["rendition_group_key"],
        "source_intent_key": row["intent_key"],
        "status": "source-matched-abstract-companion",
    }


def _resolution_rows(persona_id, query_value, oracle_value, lifecycle_value):
    queries, oracle_by_query = _oracle_by_query(query_value, oracle_value)
    pairs = [(row, oracle_by_query[row["query_key"]]) for row in queries]
    capabilities = lifecycle_value["primary_match_rows"]
    if len(capabilities) != 105 or len(
        {row["capability_key"] for row in capabilities}
    ) != 105:
        _fail("lifecycle dependency does not contain 105 unique capabilities")
    matching = _bipartite_match(persona_id, pairs, capabilities)
    companion_by_capability = {
        row["primary_capability_key"]: row
        for row in lifecycle_value["companion_match_rows"]
    }
    if len(companion_by_capability) != 10:
        _fail("lifecycle dependency does not contain ten unique companions")

    primary_source_intents = {row["intent_key"] for row in capabilities}
    companion_source_intents = {
        row["intent_key"] for row in companion_by_capability.values()
    }
    if (
        len(primary_source_intents) != 105
        or len(companion_source_intents) != 10
        or primary_source_intents & companion_source_intents
    ):
        _fail("primary and companion source-intent domains are not disjoint")

    rows = []
    all_target_intents = {row["target_intent_key"] for row in queries}
    all_target_documents = {
        row["target_logical_document_key"] for row in queries
    }
    all_distractor_intents = {
        row["distractor_intent_key"]
        for oracle_row in oracle_value["positive_oracle_rows"]
        for row in oracle_row["distractors"]
    }
    all_distractor_documents = {
        row["distractor_logical_document_key"]
        for oracle_row in oracle_value["positive_oracle_rows"]
        for row in oracle_row["distractors"]
    }
    if all_target_intents & all_distractor_intents or (
        all_target_documents & all_distractor_documents
    ):
        _fail("query targets overlap distractor abstract keys")
    if all_target_intents & (
        primary_source_intents | companion_source_intents
    ):
        _fail("query targets overlap lifecycle source-intent keys")

    for query_row in sorted(queries, key=lambda row: _ascii(row["query_key"])):
        oracle_row = oracle_by_query[query_row["query_key"]]
        capability_row, rule_id = matching[query_row["query_key"]]
        companion = _companion_contract(
            capability_row, companion_by_capability
        )
        evidence = oracle_row["evidence_contract"]
        operation_kind = evidence.get("operation_kind", "not-applicable")
        row = {
            "abstract_answer_contract": _answer_contract(oracle_row),
            "abstract_target": {
                "intent_key": query_row["target_intent_key"],
                "logical_document_key": query_row[
                    "target_logical_document_key"
                ],
            },
            "distractor_contract": _distractor_contract(oracle_row),
            "evaluation_class": query_row["evaluation_class"],
            "lifecycle_binding": {
                "capability_class_key": capability_row[
                    "capability_class_key"
                ],
                "capability_key": capability_row["capability_key"],
                "companion": companion,
                "logical_document_slot_key": capability_row[
                    "lifecycle_logical_document_slot_key"
                ],
                "primary_source_intent_key": capability_row["intent_key"],
                "required_event_profile_keys": list(
                    CLASS_EVENT_PROFILES[
                        capability_row["capability_class_key"]
                    ]
                ),
            },
            "oracle_evidence": {
                "evidence_kind": evidence["evidence_kind"],
                "event_template_rows": _event_template_rows(evidence),
                "operation_kind": operation_kind,
                "required_evidence_state": query_row[
                    "required_evidence_state"
                ],
            },
            "persona_id": persona_id,
            "query_key": query_row["query_key"],
            "resolution_status": {
                "abstract_capability_binding_authored": True,
                "compiled_history_event_binding_present": False,
                "effective_fact_membership_present": False,
                "final_identity_binding_present": False,
                "source_topic_language_fact_equality_proved": False,
            },
            "scenario_id": query_row["scenario_id"],
            "semantic_match_rule_id": rule_id,
            "stratum_id": query_row["stratum_id"],
        }
        rows.append(row)
    if len({row["query_key"] for row in rows}) != 105 or len(
        {row["lifecycle_binding"]["capability_key"] for row in rows}
    ) != 105:
        _fail("target resolution rows are not a query/capability bijection")
    return rows


def _count_rows(rows, key_path):
    result = {}
    for row in rows:
        value = row
        for key in key_path:
            value = value[key]
        result[value] = result.get(value, 0) + 1
    return [
        {"count": result[key], "key": key}
        for key in sorted(result, key=_ascii)
    ]


def _canonical_resolution(*, dependency_observer=None):
    query_values, oracle_values, lifecycle_values = _load_dependencies(
        dependency_observer
    )
    bindings = []
    resolution_rows = []
    persona_summaries = []
    for persona_id, query_value, oracle_value, lifecycle_value in zip(
        envelope.PERSONA_IDS,
        query_values,
        oracle_values,
        lifecycle_values,
        strict=True,
    ):
        bindings.extend(
            (
                _binding(
                    "persona-v2-query-intent",
                    "evaluation-query-intent",
                    persona_id,
                    query_value,
                    query_intent.canonical_json_bytes,
                ),
                _binding(
                    "persona-v2-semantic-oracle",
                    "evaluation-semantic-oracle",
                    persona_id,
                    oracle_value,
                    semantic_oracle.canonical_json_bytes,
                ),
                _binding(
                    "persona-v2-source-matched-lifecycle-persona",
                    "query-independent-lifecycle-capability-source-match",
                    persona_id,
                    lifecycle_value,
                    lifecycle.canonical_json_bytes,
                ),
            )
        )
        rows = _resolution_rows(
            persona_id, query_value, oracle_value, lifecycle_value
        )
        resolution_rows.extend(rows)
        persona_summaries.append(
            {
                "abstract_companion_binding_count": sum(
                    row["lifecycle_binding"]["companion"]["status"]
                    == "source-matched-abstract-companion"
                    for row in rows
                ),
                "capability_class_counts": _count_rows(
                    rows, ("lifecycle_binding", "capability_class_key")
                ),
                "negative_query_count": sum(
                    row["evaluation_class"] == "purged-negative"
                    for row in rows
                ),
                "persona_id": persona_id,
                "positive_query_count": sum(
                    row["evaluation_class"] == "positive-recall"
                    for row in rows
                ),
                "query_capability_bijection_count": len(rows),
                "stratum_counts": _count_rows(rows, ("stratum_id",)),
            }
        )

    expected_total = 105 * len(envelope.PERSONA_IDS)
    if len(resolution_rows) != expected_total:
        _fail("suite target resolution cardinality drifted")
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _authority(),
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_ARTIFACT_BYTES,
            "max_expanded_node_count": MAX_EXPANDED_NODE_COUNT,
            "max_input_binding_count": 60,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_resolution_row_count": expected_total,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "precanonical_expanded_structure_preflight_required": True,
            "self_hash_embedded": False,
            "target_body_bytes": TARGET_ARTIFACT_BYTES,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_2100_query_intents_accounted": True,
            "abstract_query_to_lifecycle_capability_bijection_authored": True,
            "compiled_history_event_targets_present": False,
            "corpus_namespace_or_source_id_preimage_changed": False,
            "distractor_source_mapping_resolved": False,
            "effective_source_fact_membership_resolved": False,
            "exact_stratum_capability_count_table_proved": True,
            "final_identity_relevance_present": False,
            "global_answer_and_distractor_fact_sets_disjoint": False,
            "per_query_answer_and_distractor_fact_sets_disjoint": True,
            "primary_and_companion_source_intents_disjoint": True,
            "query_target_and_distractor_abstract_keys_disjoint": True,
            "query_target_and_lifecycle_source_intent_keys_disjoint": True,
            "rendered_query_or_compiled_relevance_present": False,
            "semantic_class_constraints_satisfied": True,
            "source_topic_language_fact_equality_proved": False,
            "target_primary_companion_and_distractor_source_intents_disjoint": False,
        },
        "completion_scope": (
            "abstract-evaluation-query-to-lifecycle-capability-bijection-only-"
            "no-effective-membership-no-final-identities-no-render-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "corpus_namespace_may_import_this_artifact": False,
            "corpus_renderer_may_import_this_artifact": False,
            "evaluation_closure_may_bind_this_artifact": True,
            "lifecycle_source_matching_remains_query_independent": True,
            "query_or_oracle_change_may_change_corpus_root": False,
            "query_or_oracle_change_may_change_source_id_preimage": False,
            "resolution_is_downstream_of_query_oracle_and_lifecycle_matching": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-semantic-class-resolution-not-observed-execution"
        ),
        "input_binding_order": [
            "persona-then-query-intent-semantic-oracle-source-matched-lifecycle"
        ],
        "input_bindings": bindings,
        "orders": {
            "persona_order": list(envelope.PERSONA_IDS),
            "resolution_rows": "persona-id-then-query-key-ascii",
            "within_class_matching": MATCHING_ALGORITHM,
        },
        "persona_summaries": persona_summaries,
        "remaining_blockers": [
            "effective-lifecycle-fact-topic-language-membership-overlay-not-built",
            (
                "5400-abstract-distractor-references-not-mapped-to-distinct-source-"
                "intents-or-disjoint-from-target-primary-companion-sources"
            ),
            "abstract-event-template-to-compiled-history-event-binding-not-built",
            "scope-bucket-cohort-quota-solution-and-proof-not-built",
            "query-render-and-byte-uniqueness-attestation-not-built",
            "compiled-final-identity-relevance-not-built",
            "filesystem-render-index-history-kio-receipts-and-g0-not-built",
        ],
        "resolution_contract": {
            "abstract_keys_only": True,
            "class_assignment_uses_revision_chain_and_operation_semantics": True,
            "effective_membership_overlay_required_before_fact_resolution": True,
            "matching_algorithm": MATCHING_ALGORITHM,
            "ordinal_zip_allowed": False,
            "source_topic_language_or_fact_match_inferred_from_w0_base": False,
            "stratum_capability_counts_per_persona": [
                {
                    "capability_class_counts": [
                        {"capability_class_key": key, "count": count}
                        for key, count in class_rows
                    ],
                    "stratum_id": stratum,
                }
                for stratum, class_rows in STRATUM_CAPABILITY_COUNTS
            ],
        },
        "resolution_rows": resolution_rows,
        "summary": {
            "abstract_companion_binding_count": sum(
                row["lifecycle_binding"]["companion"]["status"]
                == "source-matched-abstract-companion"
                for row in resolution_rows
            ),
            "abstract_distractor_reference_count": sum(
                len(row["distractor_contract"]["distractor_fact_ids"])
                for row in resolution_rows
            ),
            "distinct_distractor_source_count": 0,
            "input_binding_count": len(bindings),
            "negative_query_count": sum(
                row["evaluation_class"] == "purged-negative"
                for row in resolution_rows
            ),
            "persona_count": len(persona_summaries),
            "positive_query_count": sum(
                row["evaluation_class"] == "positive-recall"
                for row in resolution_rows
            ),
            "query_capability_bijection_count": len(resolution_rows),
        },
    }
    _reject_forbidden_keys(value)
    raw = _canonical(value)
    if len(raw) > TARGET_ARTIFACT_BYTES:
        _fail("target resolution exceeds its target byte budget")
    return value


@functools.lru_cache(maxsize=1)
def _cached_canonical_raw():
    raw = _canonical(_canonical_resolution())
    _require_frozen_raw(raw)
    return raw


def build_query_history_target_resolution():
    """Return a detached all-persona abstract target-resolution candidate."""

    raw = _cached_canonical_raw()
    return json.loads(raw.decode("utf-8", "strict"))


def _build_query_history_target_resolution(*, dependency_observer=None):
    """Uncached observer-aware construction hook for adversarial tests."""

    return copy.deepcopy(
        _canonical_resolution(dependency_observer=dependency_observer)
    )


def canonical_json_bytes(value):
    if type(value) is not dict:
        _fail("target resolution must be an object")
    try:
        from . import persona_v2_query_history_target_resolution_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_query_history_target_resolution_validator as independent
    try:
        independent.preflight_query_history_target_resolution(value)
    except independent.PersonaV2QueryHistoryTargetResolutionValidationError as error:
        raise PersonaV2QueryHistoryTargetResolutionError(str(error)) from None
    _reject_forbidden_keys(value)
    raw = _canonical(value)
    _require_frozen_raw(raw)
    return raw


def validate_query_history_target_resolution(value):
    try:
        from . import persona_v2_query_history_target_resolution_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_query_history_target_resolution_validator as independent
    try:
        return independent.validate_query_history_target_resolution(value)
    except independent.PersonaV2QueryHistoryTargetResolutionValidationError as error:
        raise PersonaV2QueryHistoryTargetResolutionError(str(error)) from None


def query_history_target_resolution_sha256(value=None):
    if value is None:
        value = build_query_history_target_resolution()
    try:
        from . import persona_v2_query_history_target_resolution_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_query_history_target_resolution_validator as independent
    try:
        detached, opening = independent._snapshot_candidate(value)
    except independent.PersonaV2QueryHistoryTargetResolutionValidationError as error:
        raise PersonaV2QueryHistoryTargetResolutionError(str(error)) from None
    _require_frozen_raw(opening)
    validate_query_history_target_resolution(detached)
    try:
        _closing_value, closing = independent._snapshot_candidate(value)
    except independent.PersonaV2QueryHistoryTargetResolutionValidationError as error:
        raise PersonaV2QueryHistoryTargetResolutionError(str(error)) from None
    _require_frozen_raw(closing)
    if not hmac.compare_digest(opening, closing):
        _fail("target resolution changed during validation-to-hash snapshot")
    return _sha256(opening)


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_ARTIFACT_BYTES",
    "PersonaV2QueryHistoryTargetResolutionError",
    "build_query_history_target_resolution",
    "canonical_json_bytes",
    "query_history_target_resolution_sha256",
    "validate_query_history_target_resolution",
]
