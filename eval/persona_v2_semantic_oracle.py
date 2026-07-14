"""Semantic-only answer oracle candidates for persona-PC fidelity v2.

The oracle joins each query intent to an authored logical document, source
intent key, exact typed fact/revision target, and required evidence state.  It
contains no solved source, materialization, chunk, raw, normalized-section,
path, rank, score, or latency identity.  History references are abstract event
*template* keys only.  A later compiler must join fact membership, history
intent, the solved source plan, rendered outputs, and KCS receipts before this
can become formal relevance.

Consequently this artifact is root-independent and non-authorizing.  It is an
evaluation-closure input and must never enter the corpus namespace, corpus
bytes, corpus renderer projection, or source-ID preimage.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_query_intent as query_intent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_query_intent as query_intent


ARTIFACT_SCHEMA = "kcs.persona.pc-semantic-oracle/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-semantic-oracle"
MAX_SEMANTIC_ORACLE_BYTES = 1536 * 1024
DISTRACTORS_PER_POSITIVE = 3
RESTORE_ANCHORS_PER_PERSONA = 10

_ALLOWED_CONSUMER_ROLES = frozenset(
    (
        "compiled-relevance-builder",
        "evaluation-input-closure-builder",
        "query-renderer",
    )
)

_FORBIDDEN_DATA_KEYS = frozenset(
    (
        "chunk_id",
        "expected_chunk_ids",
        "expected_materialization_ids",
        "expected_section_ids",
        "expected_source_ids",
        "final_materialization_id",
        "final_source_id",
        "latency",
        "materialization_id",
        "normalized_section_id",
        "path",
        "query_text",
        "rank",
        "raw_hash",
        "raw_sha256",
        "rendered_query",
        "rendered_query_text",
        "score",
        "section_id",
        "source_id",
    )
)


class PersonaV2SemanticOracleError(ValueError):
    """Raised when a semantic-oracle candidate differs from its contract."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2SemanticOracleError(f"unknown persona: {persona_id!r}")
    return persona_id


def _assert_no_forbidden_data_keys(value):
    if type(value) is list:
        for item in value:
            _assert_no_forbidden_data_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _FORBIDDEN_DATA_KEYS:
            raise PersonaV2SemanticOracleError(
                f"semantic oracle contains prohibited field: {key}"
            )
        _assert_no_forbidden_data_keys(item)


def require_consumer_access(consumer_role):
    """Fail closed when corpus-side code asks for the semantic oracle."""

    if type(consumer_role) is not str or not consumer_role:
        raise PersonaV2SemanticOracleError(
            "consumer role must be a non-empty string"
        )
    if consumer_role not in _ALLOWED_CONSUMER_ROLES:
        raise PersonaV2SemanticOracleError(
            f"semantic oracle is not available to consumer role: {consumer_role}"
        )
    return True


def _fact_graph_binding(persona_id, value):
    raw = fact_graph.canonical_json_bytes(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "typed-semantic-input",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "fact-graph",
        "persona_id": persona_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _query_intent_binding(persona_id, value):
    raw = query_intent.canonical_json_bytes(value)
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": "evaluation-query-input",
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "query-intent",
        "persona_id": persona_id,
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def _graph_by_project(graph_value):
    result = {
        graph["project_or_case_id"]: graph for graph in graph_value["graphs"]
    }
    if len(result) != len(graph_value["graphs"]):
        raise PersonaV2SemanticOracleError("fact graph project keys are not unique")
    return result


def _fact_visibility_at_w5(fact):
    rows = fact["visibility_by_checkpoint"]
    if rows[-1]["checkpoint"] != "W5-final":
        raise PersonaV2SemanticOracleError("fact graph lacks a W5-final checkpoint")
    return rows[-1]["state"]


def _answer_fact(graph, query_row):
    stratum_id = query_row["stratum_id"]
    if stratum_id in (
        "old-wording",
        "locale-language-history",
        "locale-language-lifecycle",
    ):
        fact_id = graph["revision_chains"][0]["prior_fact_ids"][0]
    else:
        current_facts = [
            fact
            for fact in graph["facts"]
            if _fact_visibility_at_w5(fact) == "current"
        ]
        fact_id = current_facts[
            (query_row["ordinal_in_stratum"] - 1) % len(current_facts)
        ]["fact_id"]
    by_id = {fact["fact_id"]: fact for fact in graph["facts"]}
    return by_id[fact_id]


def _revision_chain_ids(graph, fact_id):
    return [
        chain["revision_chain_id"]
        for chain in graph["revision_chains"]
        if fact_id == chain["current_fact_id"] or fact_id in chain["prior_fact_ids"]
    ]


def _event_template_key(query_row, operation):
    return f"history-event-template-{query_row['query_key'][6:]}-{operation}"


def _evidence_contract(query_row):
    stratum_id = query_row["stratum_id"]
    common = {
        "evaluation_checkpoint": query_row["evaluation_checkpoint"],
        "raw_only_structural_sentinel_sufficient": False,
        "required_evidence_state": query_row["required_evidence_state"],
        "selector": query_row["selector"],
        "unindexed_file_sufficient": False,
    }
    if stratum_id == "current-fact":
        return {
            **common,
            "current_searchable_binding_required": True,
            "evidence_kind": "current-semantic-fact",
        }
    if stratum_id == "cross-format-fact":
        return {
            **common,
            "evidence_kind": "cross-format-current-semantic-fact",
            "minimum_distinct_format_families": 2,
            "same_logical_document_required": True,
        }
    if stratum_id == "locale-language-fact":
        return {
            **common,
            "evidence_kind": "locale-language-current-semantic-fact",
            "query_and_answer_language_must_equal": True,
        }
    if stratum_id == "old-wording":
        return {
            **common,
            "evidence_kind": "superseded-typed-fact-history",
            "history_event_checkpoint": "W1",
            "history_event_template_key": _event_template_key(
                query_row, "typed-revision"
            ),
            "prior_revision_fact_required": True,
        }
    if stratum_id == "rename-move":
        operation = (
            "same-scope-rename"
            if query_row["ordinal_in_stratum"] % 2
            else "searchable-cross-scope-move"
        )
        return {
            **common,
            "bytes_unchanged_across_event_required": True,
            "cross_scope_required": operation == "searchable-cross-scope-move",
            "evidence_kind": "searchable-rename-or-move-history",
            "history_event_checkpoint": "W2",
            "history_event_template_key": _event_template_key(
                query_row, operation
            ),
            "operation_kind": operation,
            "searchable_contributor_required": True,
        }
    if stratum_id == "locale-language-history":
        return {
            **common,
            "evidence_kind": "locale-language-superseded-history",
            "history_event_checkpoint": "W1",
            "history_event_template_key": _event_template_key(
                query_row, "typed-revision"
            ),
            "prior_revision_fact_required": True,
            "query_and_answer_language_must_equal": True,
        }
    if stratum_id == "deleted":
        return {
            **common,
            "delete_event_template_key": _event_template_key(query_row, "delete"),
            "delete_event_checkpoint": "W4",
            "evidence_kind": "final-deleted-searchable-binding",
            "final_deleted_binding_required": True,
            "lifecycle_receipt_required": True,
            "live_current_copy_sufficient": False,
            "restore_after_delete_allowed": False,
        }
    if stratum_id == "restored":
        suffix = query_row["query_key"][6:]
        return {
            **common,
            "delete_event_template_key": _event_template_key(query_row, "delete"),
            "delete_event_checkpoint": "W4",
            "destination_index_checkpoint": "W5-pre-purge",
            "destination_index_receipt_required": True,
            "distinct_searchable_logical_document_required": True,
            "evidence_kind": "delete-then-restore-then-destination-index",
            "new_restored_materialization_required": True,
            "one_to_one_query_anchor_required": True,
            "required_event_order": ["delete", "restore", "destination-index"],
            "restore_anchor_key": f"restore-anchor-{suffix}",
            "restore_event_checkpoint": "W5-pre-purge",
            "restore_event_template_key": _event_template_key(query_row, "restore"),
            "same_content_other_current_copy_sufficient": False,
            "lifecycle_receipt_required": True,
        }
    if stratum_id == "locale-language-lifecycle":
        return {
            **common,
            "evidence_kind": "locale-language-archive-history",
            "history_event_checkpoint": "W4",
            "history_event_template_key": _event_template_key(
                query_row, "archive"
            ),
            "lifecycle_operation_kind": "archive",
            "prior_revision_fact_required": True,
            "query_and_answer_language_must_equal": True,
        }
    raise PersonaV2SemanticOracleError(f"unknown positive stratum: {stratum_id}")


def _distractors(query_row, graph, answer_fact):
    alternatives = [
        fact for fact in graph["facts"] if fact["fact_id"] != answer_fact["fact_id"]
    ]
    rows = []
    base = query_row["query_key"][6:]
    for ordinal in range(1, DISTRACTORS_PER_POSITIVE + 1):
        fact = alternatives[
            (query_row["ordinal_in_stratum"] + ordinal - 2) % len(alternatives)
        ]
        rows.append(
            {
                "distractor_fact_id": fact["fact_id"],
                "distractor_intent_key": f"distractor-intent-{base}-{ordinal:02d}",
                "distractor_logical_document_key": (
                    f"distractor-logical-document-{base}-{ordinal:02d}"
                ),
                "excluded_from_abstract_relevance": True,
                "language": query_row["language"],
                "topic_project_or_case_id": query_row["project_or_case_id"],
            }
        )
    return rows


def _positive_oracle_row(query_row, graph):
    answer_fact = _answer_fact(graph, query_row)
    expected_visibility = _fact_visibility_at_w5(answer_fact)
    base = query_row["query_key"][6:]
    row = {
        "abstract_answer_membership": {
            "answer_membership_key": f"answer-membership-{base}",
            "expected_fact_ids": [answer_fact["fact_id"]],
            "expected_fact_visibility_at_checkpoint": expected_visibility,
            "expected_predicate_ids": [answer_fact["predicate_id"]],
            "expected_revision_chain_ids": _revision_chain_ids(
                graph, answer_fact["fact_id"]
            ),
            "semantic_section_role": "answer-bearing-section",
            "target_intent_key": query_row["target_intent_key"],
            "target_logical_document_key": query_row[
                "target_logical_document_key"
            ],
        },
        "distractors": _distractors(query_row, graph, answer_fact),
        "evidence_contract": _evidence_contract(query_row),
        "expected_empty": False,
        "language": query_row["language"],
        "query_intent_key": query_row["query_key"],
        "scenario_id": query_row["scenario_id"],
        "stratum_id": query_row["stratum_id"],
        "top_k": query_row["top_k"],
    }
    if query_row["stratum_id"] in (
        "old-wording",
        "locale-language-history",
        "locale-language-lifecycle",
    ) and expected_visibility != "history-only":
        raise PersonaV2SemanticOracleError(
            "history wording/lifecycle query must target a history-only fact"
        )
    return row


def _negative_oracle_row(query_row, graph):
    former_fact = _answer_fact(graph, {
        **query_row,
        "stratum_id": "current-fact",
    })
    return {
        "abstract_answer_membership": [],
        "evidence_contract": {
            "evaluation_checkpoint": query_row["evaluation_checkpoint"],
            "evidence_kind": "purged-absent-from-all-kcs-managed-history",
            "former_semantic_fact_ids": [former_fact["fact_id"]],
            "post_purge_noop_indexes_required": True,
            "purge_event_template_key": _event_template_key(query_row, "purge"),
            "required_evidence_state": "purged-absent",
            "selector": query_row["selector"],
        },
        "expected_empty": True,
        "false_positive_at_10_must_equal": 0,
        "language": query_row["language"],
        "query_intent_key": query_row["query_key"],
        "scenario_id": query_row["scenario_id"],
        "stratum_id": "purged-negative",
        "top_k": query_row["top_k"],
    }


def _validate_oracle_rows(graph_value, query_value, positive_rows, negative_rows):
    if len(positive_rows) != 90 or len(negative_rows) != 15:
        raise PersonaV2SemanticOracleError(
            "each oracle must contain exactly 90 positive and 15 negative rows"
        )
    positive_intents = query_value["positive_query_intents"]
    negative_intents = query_value["negative_query_intents"]
    if [row["query_intent_key"] for row in positive_rows] != [
        row["query_key"] for row in positive_intents
    ] or [row["query_intent_key"] for row in negative_rows] != [
        row["query_key"] for row in negative_intents
    ]:
        raise PersonaV2SemanticOracleError("oracle/query order or membership drifted")

    fact_ids = {
        fact["fact_id"]
        for graph in graph_value["graphs"]
        for fact in graph["facts"]
    }
    answer_membership_keys = []
    distractor_documents = []
    restore_rows = []
    deleted_rows = []
    for row in positive_rows:
        membership = row["abstract_answer_membership"]
        if len(membership["expected_fact_ids"]) != 1 or not set(
            membership["expected_fact_ids"]
        ).issubset(fact_ids):
            raise PersonaV2SemanticOracleError(
                "positive answer membership must bind one persona fact"
            )
        answer_membership_keys.append(membership["answer_membership_key"])
        distractors = row["distractors"]
        if len(distractors) != DISTRACTORS_PER_POSITIVE:
            raise PersonaV2SemanticOracleError(
                "each positive must have exactly three distractors"
            )
        if any(
            distractor["language"] != row["language"]
            or distractor["excluded_from_abstract_relevance"] is not True
            for distractor in distractors
        ):
            raise PersonaV2SemanticOracleError(
                "distractors must share language and remain irrelevant"
            )
        distractor_documents.extend(
            item["distractor_logical_document_key"] for item in distractors
        )
        if row["stratum_id"] == "restored":
            restore_rows.append(row)
        elif row["stratum_id"] == "deleted":
            deleted_rows.append(row)
    if len(answer_membership_keys) != len(set(answer_membership_keys)):
        raise PersonaV2SemanticOracleError("answer membership keys must be unique")
    if len(distractor_documents) != len(set(distractor_documents)):
        raise PersonaV2SemanticOracleError("distractor documents must be unique")
    if len(restore_rows) != RESTORE_ANCHORS_PER_PERSONA or len(deleted_rows) != 10:
        raise PersonaV2SemanticOracleError(
            "restored and final-deleted strata must each contain ten rows"
        )
    restore_anchors = [
        row["evidence_contract"]["restore_anchor_key"] for row in restore_rows
    ]
    if len(restore_anchors) != len(set(restore_anchors)):
        raise PersonaV2SemanticOracleError("restore anchors must be distinct")
    restored_documents = {
        row["abstract_answer_membership"]["target_logical_document_key"]
        for row in restore_rows
    }
    deleted_documents = {
        row["abstract_answer_membership"]["target_logical_document_key"]
        for row in deleted_rows
    }
    if restored_documents & deleted_documents:
        raise PersonaV2SemanticOracleError(
            "restored and final-deleted anchor sets must be disjoint"
        )
    for row in negative_rows:
        if (
            row["abstract_answer_membership"] != []
            or row["expected_empty"] is not True
            or row["false_positive_at_10_must_equal"] != 0
        ):
            raise PersonaV2SemanticOracleError("negative oracle row drifted")


def _canonical_semantic_oracle(
    persona_id,
    *,
    fact_graph_value=None,
    query_intent_value=None,
    trusted_dependency_values=False,
):
    _require_persona_id(persona_id)
    query_intent.require_consumer_access("semantic-oracle-builder")
    graph_value = (
        fact_graph.build_fact_graph(persona_id)
        if fact_graph_value is None
        else copy.deepcopy(fact_graph_value)
    )
    if fact_graph_value is not None and not trusted_dependency_values:
        fact_graph.validate_fact_graph(persona_id, graph_value)
    query_value = (
        query_intent._canonical_query_intent(
            persona_id,
            fact_graph_value=graph_value,
            trusted_fact_graph_value=True,
        )
        if query_intent_value is None
        else copy.deepcopy(query_intent_value)
    )
    if query_intent_value is not None and not trusted_dependency_values:
        expected_query = query_intent._canonical_query_intent(
            persona_id,
            fact_graph_value=graph_value,
            trusted_fact_graph_value=True,
        )
        actual_query_bytes = query_intent.canonical_json_bytes(query_value)
        expected_query_bytes = query_intent.canonical_json_bytes(expected_query)
        if actual_query_bytes != expected_query_bytes:
            raise PersonaV2SemanticOracleError(
                "query intent differs from deterministic regeneration"
            )
    if query_value["input_bindings"] != [_fact_graph_binding(persona_id, graph_value)]:
        raise PersonaV2SemanticOracleError(
            "query intent does not bind the exact semantic fact graph"
        )

    by_project = _graph_by_project(graph_value)
    positive_rows = [
        _positive_oracle_row(row, by_project[row["project_or_case_id"]])
        for row in query_value["positive_query_intents"]
    ]
    negative_rows = [
        _negative_oracle_row(row, by_project[row["project_or_case_id"]])
        for row in query_value["negative_query_intents"]
    ]
    _validate_oracle_rows(
        graph_value, query_value, positive_rows, negative_rows
    )

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "authorizes_compiled_relevance": False,
            "authorizes_corpus_rendering": False,
            "authorizes_evaluation_publication": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_query_execution": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "compiled_final_id_relevance_present": False,
            "formal_recall_denominator_present": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_SEMANTIC_ORACLE_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "compiled_relevance_contract": {
            "actual_identity_membership_present": False,
            "compilation_must_follow_solved_source_plan": True,
            "compilation_must_join_fact_membership": True,
            "compilation_must_join_history_receipts": True,
            "compilation_must_join_rendered_outputs": True,
            "formal_mvp_relevance_projection_present": False,
            "semantic_logical_document_projection_only": True,
        },
        "completion_claims": {
            "answer_fact_and_revision_targets_authored": True,
            "compiled_final_id_relevance_present": False,
            "distractor_semantic_inventory_authored": True,
            "final_deleted_semantic_anchors_authored": True,
            "formal_recall_denominator_present": False,
            "full_history_intent_membership_bound": False,
            "full_source_intent_and_fact_membership_bound": False,
            "membership_totality_proved": False,
            "positive_negative_and_stratum_inventory_complete": True,
            "restore_anchor_semantic_inventory_authored": True,
            "restore_anchor_source_history_bindings_compiled": False,
        },
        "completion_scope": (
            "semantic-answer-and-evidence-candidate-only-no-final-identities-"
            "no-corpus-input-no-compiled-relevance-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "allowed_downstream_consumers": sorted(_ALLOWED_CONSUMER_ROLES),
            "corpus_namespace_or_bytes_may_depend_on_this_artifact": False,
            "corpus_renderer_access_allowed": False,
            "dependency_order": [
                "fact-graph",
                "query-intent",
                "semantic-oracle",
                "solved-plan-and-rendered-output",
                "compiled-formal-relevance",
            ],
            "evaluation_closure_root_is_separate_from_corpus_closure_root": True,
            "oracle_change_may_change_corpus_root": False,
            "oracle_change_may_change_source_id_preimage": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-relevance",
        "input_bindings": [
            _fact_graph_binding(persona_id, graph_value),
            _query_intent_binding(persona_id, query_value),
        ],
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "network_access_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "negative_oracle_rows": negative_rows,
        "persona_id": persona_id,
        "positive_oracle_rows": positive_rows,
        "remaining_blockers": [
            "full-source-intent-inventory-not-bound-to-query-targets",
            "full-fact-membership-not-bound-to-answer-membership-keys",
            "full-history-intent-not-bound-to-lifecycle-event-templates",
            "searchable-cross-scope-move-source-plan-not-present",
            "text-layer-pdf-renderer-validator-and-positive-anchor-minima-not-bound",
            "scan-pdf-raw-only-awaiting-ocr-structural-negative-disposition-not-attested",
            "same-topic-language-rendered-distractor-vocabulary-not-attested",
            "restore-and-final-deleted-source-history-bindings-not-compiled",
            "rendered-query-and-byte-uniqueness-attestation-not-present",
            "compiled-final-id-relevance-not-present",
            "formal-relevance-projection-not-present",
            "external-frame-header-schema-dispatcher-not-implemented",
            "bounded-body-loader-not-bound-to-semantic-oracle-frame",
        ],
        "target_resolution_contract": {
            "all_positive_answer_memberships_must_exact_resolve_before_g0": True,
            "all_restore_and_deleted_event_templates_must_exact_resolve_before_g0": True,
            "membership_totality_proved": False,
            "same_topic_language_rendered_distractors_attested": False,
            "unresolved_target_keys_are_not_compiled_relevance": True,
        },
        "replay_evaluation_contract": {
            "negative_observation_rows_required": 45,
            "positive_observation_rows_required": 270,
            "query_spec_rows_per_persona": 105,
            "replay_count": query_intent.REPLAY_COUNT,
            "same_semantic_oracle_reused_unchanged_across_replays": True,
            "total_observation_rows_required": 315,
        },
        "summary": {
            "answer_membership_count": len(positive_rows),
            "distractor_count": len(positive_rows) * DISTRACTORS_PER_POSITIVE,
            "final_deleted_anchor_count": sum(
                row["stratum_id"] == "deleted" for row in positive_rows
            ),
            "negative_query_count": len(negative_rows),
            "positive_query_count": len(positive_rows),
            "restore_anchor_count": sum(
                row["stratum_id"] == "restored" for row in positive_rows
            ),
        },
    }
    _assert_no_forbidden_data_keys(value)
    return value


def build_semantic_oracle(persona_id):
    """Return one detached, semantic-only, non-authorizing oracle leaf."""

    return copy.deepcopy(_canonical_semantic_oracle(persona_id))


def build_semantic_oracle_suite():
    """Build all twenty leaves while sharing already rebuilt fact leaves."""

    graph_values = fact_graph.build_fact_graph_suite()
    result = []
    for graph_value in graph_values:
        persona_id = graph_value["persona_id"]
        query_value = query_intent._canonical_query_intent(
            persona_id,
            fact_graph_value=graph_value,
            trusted_fact_graph_value=True,
        )
        result.append(
            copy.deepcopy(
                _canonical_semantic_oracle(
                    persona_id,
                    fact_graph_value=graph_value,
                    query_intent_value=query_value,
                    trusted_dependency_values=True,
                )
            )
        )
    return result


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 semantic oracle",
            max_bytes=MAX_SEMANTIC_ORACLE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SemanticOracleError(str(error)) from None


def validate_semantic_oracle(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_semantic_oracle(persona_id),
            label="persona v2 semantic oracle",
            max_bytes=MAX_SEMANTIC_ORACLE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SemanticOracleError(str(error)) from None


def semantic_oracle_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_semantic_oracle(persona_id),
            label="persona v2 semantic oracle",
            max_bytes=MAX_SEMANTIC_ORACLE_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2SemanticOracleError(str(error)) from None
