"""Root-independent query-intent candidates for persona-PC fidelity v2.

This per-persona leaf fixes *what* each evaluation query is intended to ask
without containing query text, a query template, a rendered corpus value, or
any solved source/materialization/chunk identity.  It is an evaluation-closure
input.  It is deliberately outside the corpus-renderer dependency cone: a
query/oracle change must not change a corpus root or a source-ID preimage.

The companion semantic oracle adds authored fact answer membership.  Actual
query strings and compiled ``(raw_hash, section)`` relevance are later,
separately bounded artifacts.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph


ARTIFACT_SCHEMA = "kcs.persona.pc-query-intent/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-query-intent"
MAX_QUERY_INTENT_BYTES = 1 * 2**20

POSITIVE_QUERIES_PER_STRATUM = 10
NEGATIVE_QUERIES_PER_SCENARIO = 5
REPLAY_COUNT = 3

SCENARIO_STRATA = (
    (
        "M3-1",
        ("current-fact", "cross-format-fact", "locale-language-fact"),
    ),
    (
        "M3-2",
        ("old-wording", "rename-move", "locale-language-history"),
    ),
    (
        "M3-3",
        ("deleted", "restored", "locale-language-lifecycle"),
    ),
)

REQUIRED_EVIDENCE_STATE_BY_STRATUM = {
    "current-fact": "current",
    "cross-format-fact": "current",
    "locale-language-fact": "current",
    "old-wording": "old-wording-history",
    "rename-move": "rename-move-history",
    "locale-language-history": "locale-language-history",
    "deleted": "final-deleted",
    "restored": "current-restored",
    "locale-language-lifecycle": "locale-language-lifecycle-history",
}

SELECTOR_BY_STRATUM = {
    "current-fact": "default",
    "cross-format-fact": "default",
    "locale-language-fact": "default",
    "old-wording": "--all-history",
    "rename-move": "--all-history",
    "locale-language-history": "--all-history",
    "deleted": "--include-deleted",
    "restored": "default",
    "locale-language-lifecycle": "--all-history",
}

NEGATIVE_SELECTOR_BY_SCENARIO = {
    "M3-1": "default",
    "M3-2": "--all-history",
    "M3-3": "--include-deleted",
}

_ALLOWED_CONSUMER_ROLES = frozenset(
    (
        "evaluation-input-closure-builder",
        "query-renderer",
        "semantic-oracle-builder",
    )
)
_FORBIDDEN_DATA_KEYS = frozenset(
    (
        "chunk_id",
        "final_materialization_id",
        "final_source_id",
        "latency",
        "materialization_id",
        "normalized_section_id",
        "path",
        "query_template",
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


class PersonaV2QueryIntentError(ValueError):
    """Raised when a query-intent candidate differs from the exact contract."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2QueryIntentError(f"unknown persona: {persona_id!r}")
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
            raise PersonaV2QueryIntentError(
                f"query intent contains prohibited field: {key}"
            )
        _assert_no_forbidden_data_keys(item)


def require_consumer_access(consumer_role):
    """Fail closed when a corpus-side component asks for query intent."""

    if type(consumer_role) is not str or not consumer_role:
        raise PersonaV2QueryIntentError("consumer role must be a non-empty string")
    if consumer_role not in _ALLOWED_CONSUMER_ROLES:
        raise PersonaV2QueryIntentError(
            f"query intent is not available to consumer role: {consumer_role}"
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


def _query_prefix(persona_id, scenario_id, stratum_id, ordinal):
    return (
        f"{persona_id}-{scenario_id.lower()}-{stratum_id}-{ordinal:02d}"
    )


def _query_language(languages, stratum_id, ordinal):
    if stratum_id.startswith("locale-language-") and len(languages) > 1:
        return languages[1 + ((ordinal - 1) % (len(languages) - 1))]
    return languages[0]


def _positive_rows(persona_id, graph_value):
    languages = graph_value["eligible_languages"]
    graphs = graph_value["graphs"]
    rows = []
    for scenario_index, (scenario_id, strata) in enumerate(SCENARIO_STRATA):
        for stratum_index, stratum_id in enumerate(strata):
            for ordinal in range(1, POSITIVE_QUERIES_PER_STRATUM + 1):
                graph = graphs[
                    (scenario_index * len(strata) + stratum_index + ordinal - 1)
                    % len(graphs)
                ]
                prefix = _query_prefix(
                    persona_id, scenario_id, stratum_id, ordinal
                )
                rows.append(
                    {
                        "dedup_projection": "logical-document-key-semantic-candidate",
                        "evaluation_class": "positive-recall",
                        "evaluation_checkpoint": "W5-final",
                        "expected_empty": False,
                        "target_intent_key": f"intent-{prefix}",
                        "language": _query_language(
                            languages, stratum_id, ordinal
                        ),
                        "target_logical_document_key": f"logical-document-{prefix}",
                        "ordinal_in_stratum": ordinal,
                        "project_or_case_id": graph["project_or_case_id"],
                        "query_key": f"query-{prefix}",
                        "recall_denominator_member": True,
                        "required_evidence_state": (
                            REQUIRED_EVIDENCE_STATE_BY_STRATUM[stratum_id]
                        ),
                        "scenario_id": scenario_id,
                        "selector": SELECTOR_BY_STRATUM[stratum_id],
                        "stratum_id": stratum_id,
                        "top_k": 10,
                    }
                )
    return rows


def _negative_rows(persona_id, graph_value):
    languages = graph_value["eligible_languages"]
    graphs = graph_value["graphs"]
    rows = []
    for scenario_index, (scenario_id, _) in enumerate(SCENARIO_STRATA):
        for ordinal in range(1, NEGATIVE_QUERIES_PER_SCENARIO + 1):
            graph = graphs[(scenario_index + ordinal - 1) % len(graphs)]
            prefix = _query_prefix(
                persona_id, scenario_id, "purged-negative", ordinal
            )
            rows.append(
                {
                    "dedup_projection": "logical-document-key-semantic-candidate",
                    "evaluation_class": "purged-negative",
                    "evaluation_checkpoint": "W5-final",
                    "expected_empty": True,
                    "false_positive_at_10_must_equal": 0,
                    "target_intent_key": f"intent-{prefix}",
                    "language": languages[(ordinal - 1) % len(languages)],
                    "target_logical_document_key": f"logical-document-{prefix}",
                    "ordinal_in_stratum": ordinal,
                    "project_or_case_id": graph["project_or_case_id"],
                    "query_key": f"query-{prefix}",
                    "recall_denominator_member": False,
                    "required_evidence_state": "purged-absent",
                    "scenario_id": scenario_id,
                    "selector": NEGATIVE_SELECTOR_BY_SCENARIO[scenario_id],
                    "stratum_id": "purged-negative",
                    "top_k": 10,
                }
            )
    return rows


def _validate_rows(persona_id, graph_value, positive_rows, negative_rows):
    if len(positive_rows) != 90 or len(negative_rows) != 15:
        raise PersonaV2QueryIntentError(
            "each persona must contain exactly 90 positive and 15 negative intents"
        )
    all_rows = positive_rows + negative_rows
    for key in (
        "query_key",
        "target_intent_key",
        "target_logical_document_key",
    ):
        values = [row[key] for row in all_rows]
        if len(values) != len(set(values)):
            raise PersonaV2QueryIntentError(
                f"{key} values must be unique within each persona"
            )

    valid_projects = {
        graph["project_or_case_id"] for graph in graph_value["graphs"]
    }
    languages = graph_value["eligible_languages"]
    by_scenario_stratum = {}
    for row in positive_rows:
        if row["project_or_case_id"] not in valid_projects:
            raise PersonaV2QueryIntentError("query references a foreign graph topic")
        if row["language"] not in languages:
            raise PersonaV2QueryIntentError("query language is not persona-eligible")
        key = (row["scenario_id"], row["stratum_id"])
        by_scenario_stratum.setdefault(key, []).append(row)
        expected_state = REQUIRED_EVIDENCE_STATE_BY_STRATUM.get(row["stratum_id"])
        if row["required_evidence_state"] != expected_state:
            raise PersonaV2QueryIntentError("query evidence state drifted")
        if (
            row["evaluation_checkpoint"] != "W5-final"
            or row["selector"] != SELECTOR_BY_STRATUM[row["stratum_id"]]
            or row["expected_empty"] is not False
            or row["top_k"] != 10
            or row["dedup_projection"]
            != "logical-document-key-semantic-candidate"
        ):
            raise PersonaV2QueryIntentError("positive evaluation selector drifted")
    expected_pairs = {
        (scenario_id, stratum_id)
        for scenario_id, strata in SCENARIO_STRATA
        for stratum_id in strata
    }
    if set(by_scenario_stratum) != expected_pairs or any(
        len(rows) != POSITIVE_QUERIES_PER_STRATUM
        for rows in by_scenario_stratum.values()
    ):
        raise PersonaV2QueryIntentError(
            "positive scenario/stratum cardinalities drifted"
        )

    if len(languages) > 1:
        for _, strata in SCENARIO_STRATA:
            for stratum_id in strata:
                if not stratum_id.startswith("locale-language-"):
                    continue
                rows = by_scenario_stratum[
                    (next(
                        scenario_id
                        for scenario_id, candidate in SCENARIO_STRATA
                        if stratum_id in candidate
                    ), stratum_id)
                ]
                if not any(row["language"] != languages[0] for row in rows):
                    raise PersonaV2QueryIntentError(
                        "multilingual locale stratum needs a non-primary language"
                    )

    negative_scenarios = {}
    for row in negative_rows:
        negative_scenarios.setdefault(row["scenario_id"], []).append(row)
        if (
            row["stratum_id"] != "purged-negative"
            or row["required_evidence_state"] != "purged-absent"
            or row["recall_denominator_member"] is not False
            or row["false_positive_at_10_must_equal"] != 0
            or row["evaluation_checkpoint"] != "W5-final"
            or row["selector"]
            != NEGATIVE_SELECTOR_BY_SCENARIO[row["scenario_id"]]
            or row["expected_empty"] is not True
            or row["top_k"] != 10
            or row["dedup_projection"]
            != "logical-document-key-semantic-candidate"
        ):
            raise PersonaV2QueryIntentError("negative query semantics drifted")
    if set(negative_scenarios) != {row[0] for row in SCENARIO_STRATA} or any(
        len(rows) != NEGATIVE_QUERIES_PER_SCENARIO
        for rows in negative_scenarios.values()
    ):
        raise PersonaV2QueryIntentError("negative scenario cardinalities drifted")


def _canonical_query_intent(
    persona_id, *, fact_graph_value=None, trusted_fact_graph_value=False
):
    _require_persona_id(persona_id)
    graph_value = (
        fact_graph.build_fact_graph(persona_id)
        if fact_graph_value is None
        else copy.deepcopy(fact_graph_value)
    )
    if fact_graph_value is not None and not trusted_fact_graph_value:
        fact_graph.validate_fact_graph(persona_id, graph_value)
    positive_rows = _positive_rows(persona_id, graph_value)
    negative_rows = _negative_rows(persona_id, graph_value)
    _validate_rows(persona_id, graph_value, positive_rows, negative_rows)

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "authorizes_compiled_relevance": False,
            "authorizes_corpus_rendering": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_query_execution": False,
            "authorizes_query_rendering": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "compiled_final_id_relevance_present": False,
            "query_instances_rendered": False,
            "query_spec_hashed_by_g0": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_QUERY_INTENT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "compiled_final_id_relevance_present": False,
            "corpus_source_membership_bound": False,
            "intent_and_logical_document_targets_authored": True,
            "machine_readable_checkpoint_selector_and_dedup_authored": True,
            "membership_totality_proved": False,
            "positive_and_negative_inventory_complete": True,
            "positive_query_text_byte_uniqueness_attested": False,
            "query_instances_rendered": False,
            "required_evidence_states_authored": True,
            "semantic_oracle_bound": False,
            "source_intent_inventory_bound": False,
        },
        "completion_scope": (
            "semantic-query-intent-inventory-only-no-query-text-no-corpus-input-"
            "no-final-id-relevance-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "allowed_downstream_consumers": sorted(_ALLOWED_CONSUMER_ROLES),
            "corpus_renderer_access_allowed": False,
            "corpus_renderer_projection_contains_query_intent": False,
            "dependency_order": [
                "fact-graph",
                "query-intent",
                "semantic-oracle",
                "rendered-query-and-compiled-relevance",
            ],
            "query_or_oracle_change_may_change_corpus_root": False,
            "query_or_oracle_change_may_change_source_id_preimage": False,
            "separate_corpus_and_evaluation_closure_roots_required": True,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-queries",
        "input_bindings": [_fact_graph_binding(persona_id, graph_value)],
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "network_access_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "negative_query_intents": negative_rows,
        "persona_id": persona_id,
        "positive_query_intents": positive_rows,
        "remaining_blockers": [
            "source-intent-and-fact-membership-not-bound-for-all-query-targets",
            "history-intent-not-bound-for-all-lifecycle-targets",
            "semantic-oracle-candidate-not-bound",
            "query-renderer-and-rendered-query-bytes-not-present",
            "compiled-final-id-relevance-not-present",
            "formal-raw-hash-section-relevance-not-present",
            "external-frame-header-schema-dispatcher-not-implemented",
            "bounded-body-loader-not-bound-to-query-intent-frame",
        ],
        "target_resolution_contract": {
            "all_expected_targets_must_exact_resolve_before_g0": True,
            "fact_membership_targets_bound": False,
            "history_intent_targets_bound": False,
            "membership_totality_proved": False,
            "source_intent_targets_bound": False,
            "unresolved_target_keys_are_not_source_plan_membership": True,
        },
        "replay_evaluation_contract": {
            "negative_observation_rows_required": 45,
            "positive_observation_rows_required": 270,
            "query_spec_rows_per_persona": 105,
            "replay_count": REPLAY_COUNT,
            "same_query_specs_reused_unchanged_across_replays": True,
            "total_observation_rows_required": 315,
        },
        "summary": {
            "negative_query_count": len(negative_rows),
            "positive_query_count": len(positive_rows),
            "positive_stratum_count": sum(
                len(strata) for _, strata in SCENARIO_STRATA
            ),
            "scenario_count": len(SCENARIO_STRATA),
            "total_query_intent_count": len(positive_rows) + len(negative_rows),
        },
    }
    _assert_no_forbidden_data_keys(value)
    return value


def build_query_intent(persona_id):
    """Return one detached, non-authorizing persona query-intent leaf."""

    return copy.deepcopy(_canonical_query_intent(persona_id))


def build_query_intent_suite():
    """Build all twenty leaves while rebuilding the fact chain only once."""

    graphs = fact_graph.build_fact_graph_suite()
    return [
        copy.deepcopy(
            _canonical_query_intent(
                graph_value["persona_id"],
                fact_graph_value=graph_value,
                trusted_fact_graph_value=True,
            )
        )
        for graph_value in graphs
    ]


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 query intent",
            max_bytes=MAX_QUERY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2QueryIntentError(str(error)) from None


def validate_query_intent(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_query_intent(persona_id),
            label="persona v2 query intent",
            max_bytes=MAX_QUERY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2QueryIntentError(str(error)) from None


def query_intent_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_query_intent(persona_id),
            label="persona v2 query intent",
            max_bytes=MAX_QUERY_INTENT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2QueryIntentError(str(error)) from None
