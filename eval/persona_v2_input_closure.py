"""Dependency-injected, non-authorizing persona-PC v2 input roots.

The source-identity namespace must not depend on review evidence or retrieval
questions.  This module therefore keeps four deterministic bodies separate:

``corpus semantic namespace``
    Binds only full bodies of content-affecting pre-solve artifacts.  It is
    the intended location of a future source-identity namespace, but is not
    yet eligible: current mixed artifacts also carry mutable completion and
    authority metadata, query-semantic absence is not generally provable from
    arbitrary full bodies, and no schema-specific semantic projection is bound.
``corpus input closure``
    Binds the semantic namespace plus review/evidence receipts.  Receipt byte
    changes must not perturb the semantic namespace.
``evaluation input closure``
    Binds the exact corpus closure plus query/oracle inputs.  Query byte
    changes must not perturb either corpus root.
``suite input descriptor``
    Binds the exact corpus and evaluation roots and checks that the evaluation
    root names that same corpus root.

All upstream modules are injected as bodies, validators, canonicalizers, and
exact pins.  Future source-intent, history, query, oracle, and review modules
can therefore be added without optional imports or import-time breakage.
These builders operate on already materialized values; they do not implement
the framed, pre-read byte caps required by G0.

Every body here remains a candidate.  A valid hash proves only exact bytes,
negative authority, reachability, and an acyclic one-way binding graph.  It
never authorizes a solver, source plan, G0 freeze, filesystem write, or history
execution and never proves that the production input inventory is complete.
Known-schema field completeness and arbitrary domain synonyms remain the
responsibility of each injected validator.  The scanner below is additional
fail-closed defense for canonical fields and the explicitly declared alias
families; it is not a replacement for those full-schema validators.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CORPUS_SEMANTIC_SCHEMA = "kcs.persona.pc-corpus-semantic-namespace/v2"
CORPUS_SEMANTIC_KIND = "persona-pc-v2-corpus-semantic-namespace"
CORPUS_INPUT_CLOSURE_SCHEMA = (
    "kcs.persona.pc-corpus-input-closure-manifest/v2"
)
CORPUS_INPUT_CLOSURE_KIND = "persona-pc-v2-corpus-input-closure-manifest"
EVALUATION_INPUT_CLOSURE_SCHEMA = (
    "kcs.persona.pc-evaluation-input-closure-manifest/v2"
)
EVALUATION_INPUT_CLOSURE_KIND = (
    "persona-pc-v2-evaluation-input-closure-manifest"
)
SUITE_INPUT_DESCRIPTOR_SCHEMA = (
    "kcs.persona.pc-suite-input-closure-descriptor/v2"
)
SUITE_INPUT_DESCRIPTOR_KIND = "persona-pc-v2-suite-input-closure-descriptor"

ARTIFACT_SCHEMA = CORPUS_INPUT_CLOSURE_SCHEMA
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = CORPUS_INPUT_CLOSURE_KIND

MAX_UPSTREAM_BODY_BYTES = 32 * 2**20
MAX_INPUT_ROOT_BYTES = 4 * 2**20
MAX_ENTRY_COUNT = 16_384
MAX_BINDING_ALIASES_PER_ENTRY = 256
MAX_DEPENDENCIES_PER_ENTRY = MAX_ENTRY_COUNT
MAX_PROPAGATED_FALSE_STATUS_COUNT = 131_072

PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "binding_aliases",
        "canonical_bytes",
        "dependency_ids",
        "entry_id",
        "fixture_id",
        "fixture_schema_version",
        "input_class",
        "sha256",
    }
)
PROVIDER_FIELDS = frozenset({"body", "canonicalize", "entry_id", "validate"})
_BINDING_OWNER_METADATA_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "fixture_id",
        "fixture_schema_version",
    }
)
ANCHOR_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "entry_id",
        "fixture_id",
        "fixture_schema_version",
        "sha256",
    }
)
INPUT_CLASSES = frozenset({"corpus-semantic", "evidence", "evaluation"})
_RESERVED_ANCHOR_ENTRY_IDS = frozenset(
    {
        "corpus-input-closure",
        "corpus-semantic-namespace",
        "evaluation-input-closure",
        "suite-input-descriptor",
    }
)

AUTHORITY_FIELDS = (
    "authorizes_g0_freeze",
    "authorizes_history_mutation",
    "authorizes_physical_write",
    "authorizes_solver_execution",
    "authorizes_source_plan",
)
_STANDARD_NEGATIVE_AUTHORITY_FIELDS = frozenset(AUTHORITY_FIELDS)
_EXACT_TOP_LEVEL_AUTHORITY_FIELDS_BY_SCHEMA = {
    "kcs.persona.pc-envelope/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-topology/v2": frozenset(
        {
            "activity_unit_review_receipt_bound",
            "actual_chunks_attested",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "joint_allocation_proved",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-joint-problem/v2": frozenset(
        {
            "activity_unit_review_receipt_bound",
            "actual_chunks_attested",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "joint_allocation_proved",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-joint-solver-policy/v2": frozenset(
        {
            "activity_unit_review_receipt_bound",
            "actual_chunks_attested",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "canonical_joint_allocation_solution_present",
            "exact_optimality_proved",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "joint_allocation_proved",
            "kcs_execution_available",
            "policy_authorizes_solver_execution",
            "policy_authorizes_source_plan",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
            "route_affinity_matrix_bound",
        }
    ),
    "kcs.persona.pc-realism-profile/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-variant-catalog/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
            "validator_available",
        }
    ),
    "kcs.persona.pc-route-affinity/v2": frozenset(
        {
            "authorizes_g0_freeze",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "authorizes_write_or_history",
        }
    ),
    "kcs.persona.pc-id-free-text-renderer/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_final_source_identifiers",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_source_intents",
            "authorizes_source_plan",
            "kcs_execution_attested",
        }
    ),
    "kcs.persona.pc-id-free-text-validator/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_final_source_identifiers",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_source_intents",
            "authorizes_source_plan",
            "kcs_execution_attested",
        }
    ),
    "kcs.persona.pc-id-free-pdf-text-renderer/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_final_source_identifiers",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_query_plan",
            "authorizes_source_intents",
            "authorizes_source_plan",
            "kcs_execution_attested",
        }
    ),
    "kcs.persona.pc-id-free-pdf-text-validator/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_final_source_identifiers",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_query_plan",
            "authorizes_source_intents",
            "authorizes_source_plan",
            "kcs_execution_attested",
        }
    ),
    "kcs.persona.pc-source-profile-catalog/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_final_source_identifiers",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_intents",
            "authorizes_source_plan",
            "formal_capacity_gate_satisfied",
            "kcs_execution_attested",
        }
    ),
    "kcs.persona.pc-overlay-contract/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_membership_publication",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
            "source_feasibility_proved",
            "validator_available",
        }
    ),
    "kcs.persona.pc-fact-graph/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-source-intent-origin-shard/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_kcs_execution",
            "authorizes_physical_write",
            "authorizes_renderer_execution",
            "authorizes_solver_execution",
            "authorizes_source_inventory",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "joint_allocation_proved",
            "kcs_execution_available",
            "source_intent_refinement_policy_bound",
        }
    ),
    "kcs.persona.pc-fact-membership/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
            "query_instances_rendered",
            "query_spec_hashed",
            "renderer_available",
        }
    ),
    "kcs.persona.pc-history-intent/v2": frozenset(
        {
            "actual_chunks_attested",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_solver_execution",
            "compiled_history_plan_available",
            "filesystem_writer_available",
            "formal_capacity_gate_satisfied",
            "history_executor_available",
            "kcs_execution_available",
        }
    ),
    "kcs.persona.pc-route-review-receipt/v2": frozenset(
        {
            "authorizes_g0_freeze",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "authorizes_write_or_history",
            "review_authoritative",
        }
    ),
    "kcs.persona.pc-query-intent/v2": frozenset(
        {
            "authorizes_compiled_relevance",
            "authorizes_corpus_rendering",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_query_execution",
            "authorizes_query_rendering",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "compiled_final_id_relevance_present",
            "query_instances_rendered",
            "query_spec_hashed_by_g0",
        }
    ),
    "kcs.persona.pc-semantic-oracle/v2": frozenset(
        {
            "authorizes_compiled_relevance",
            "authorizes_corpus_rendering",
            "authorizes_evaluation_publication",
            "authorizes_g0_freeze",
            "authorizes_history_mutation",
            "authorizes_physical_write",
            "authorizes_query_execution",
            "authorizes_solver_execution",
            "authorizes_source_plan",
            "compiled_final_id_relevance_present",
            "formal_recall_denominator_present",
        }
    ),
}

_ROOT_SCHEMAS = frozenset(
    {
        CORPUS_SEMANTIC_SCHEMA,
        CORPUS_INPUT_CLOSURE_SCHEMA,
        EVALUATION_INPUT_CLOSURE_SCHEMA,
        SUITE_INPUT_DESCRIPTOR_SCHEMA,
    }
)
_ROOT_KINDS = frozenset(
    {
        CORPUS_SEMANTIC_KIND,
        CORPUS_INPUT_CLOSURE_KIND,
        EVALUATION_INPUT_CLOSURE_KIND,
        SUITE_INPUT_DESCRIPTOR_KIND,
    }
)
_FORBIDDEN_CLOSURE_HASH_KEYS = frozenset(
    {
        "corpus_input_closure_sha256",
        "corpus_semantic_namespace_sha256",
        "evaluation_input_closure_sha256",
        "input_closure_manifest_sha256",
        "input_closure_sha256",
        "pre_solve_input_closure_sha256",
        "suite_input_descriptor_sha256",
    }
)
_FORBIDDEN_PRE_SOLVE_ID_KEYS = frozenset(
    {
        "chunk_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "raw_hash",
        "raw_sha256",
        "source_id",
    }
)
_FORBIDDEN_EVALUATION_DATA_KEYS = frozenset(
    {
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
    }
)
_FORBIDDEN_CORPUS_QUERY_SEMANTIC_KEYS = frozenset(
    {
        "answer",
        "answer_membership",
        "answers",
        "distractor",
        "distractor_sources",
        "distractors",
        "expected_answer",
        "expected_answers",
        "negative_query",
        "oracle",
        "positive_query",
        "query_intent",
        "query_intents",
        "query_spec",
        "query_template",
        "query_text",
        "rendered_query",
        "rendered_query_text",
        "semantic_oracle",
    }
)
_CORPUS_QUERY_SEMANTIC_KEY_FRAGMENTS = (
    "answer",
    "distractor",
    "oracle",
    "query",
)
_ALLOWED_CORPUS_QUERY_SEMANTIC_METADATA = {
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        "pilot_and_extension_oracle_share_all_pair_counters",
    ): True,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        "pilot_extension_oracle",
    ): (
        "admissible only on exact extension witness; exhausted oracle makes the "
        "entire result resource_exhausted-unknown"
    ),
}
_MUST_REMAIN_FALSE_KEYS = frozenset(
    {
        "compiled_relevance_present",
        "formal_relevance_compiled",
        "g0_contract_frozen",
        "policy_authorizes_solver_execution",
        "policy_authorizes_source_plan",
        "policy_ready_for_execution",
    }
)
_COMPACT_MUST_REMAIN_FALSE_KEYS = frozenset(
    "".join(character for character in key if character.isalnum())
    for key in _MUST_REMAIN_FALSE_KEYS
)
_FINAL_ID_KEY_FRAGMENTS = (
    "chunk_id",
    "final_id",
    "final_materialization_id",
    "final_source_id",
    "materialization_id",
    "raw_hash",
    "raw_sha256",
    "section_id",
    "source_id",
)
_ALLOWED_TRUE_COMPILED_RELEVANCE_KEYS = frozenset(
    {
        (
            "kcs.persona.pc-overlay-contract/v2",
            "logical_document_assignment_occurs_before_compiled-relevance",
        ),
        (
            "kcs.persona.pc-semantic-oracle/v2",
            "unresolved_target_keys_are_not_compiled_relevance",
        ),
    }
)
_ALLOWED_FINAL_ID_METADATA = {
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        "final_identity_derivation",
    ): (
        "source_id and materialization_id are derived only after exact "
        "aggregate-and-intent assignment succeeds"
    ),
}
_CLOSURE_KEY_FRAGMENTS = (
    "corpus_closure",
    "evaluation_closure",
    "input_closure",
    "semantic_namespace",
    "suite_input",
)
_COMPACT_CLOSURE_KEY_FRAGMENTS = tuple(
    fragment.replace("_", "") for fragment in _CLOSURE_KEY_FRAGMENTS
)
_COMPACT_FINAL_ID_KEY_FRAGMENTS = tuple(
    fragment.replace("_", "") for fragment in _FINAL_ID_KEY_FRAGMENTS
)
_ALLOWED_TRUE_CLOSURE_SEPARATION_KEYS = frozenset(
    {
        (
            "kcs.persona.pc-query-intent/v2",
            "separate_corpus_and_evaluation_closure_roots_required",
        ),
        (
            "kcs.persona.pc-semantic-oracle/v2",
            "evaluation_closure_root_is_separate_from_corpus_closure_root",
        ),
    }
)
_SEMANTIC_ORACLE_COMPILED_RELEVANCE_CONTRACT = {
    "actual_identity_membership_present": False,
    "compilation_must_follow_solved_source_plan": True,
    "compilation_must_join_fact_membership": True,
    "compilation_must_join_history_receipts": True,
    "compilation_must_join_rendered_outputs": True,
    "formal_mvp_relevance_projection_present": False,
    "semantic_logical_document_projection_only": True,
}
_EXPLICIT_DEPENDENCY_OWNER_BY_SCHEMA_PATH = {
    (
        "kcs.persona.pc-topology/v2",
        ("envelope_contract_sha256",),
    ): "envelope",
    (
        "kcs.persona.pc-joint-problem/v2",
        ("envelope_contract_sha256",),
    ): "envelope",
    (
        "kcs.persona.pc-joint-problem/v2",
        ("topology_contract_sha256",),
    ): "topology",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("envelope_contract_sha256",),
    ): "envelope",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("joint_problem_sha256",),
    ): "joint-problem",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("topology_contract_sha256",),
    ): "topology",
    (
        "kcs.persona.pc-route-affinity/v2",
        ("envelope_contract_sha256",),
    ): "envelope",
    (
        "kcs.persona.pc-route-affinity/v2",
        ("joint_problem_sha256",),
    ): "joint-problem",
    (
        "kcs.persona.pc-route-affinity/v2",
        ("joint_solver_policy_sha256",),
    ): "joint-solver-policy",
    (
        "kcs.persona.pc-route-affinity/v2",
        ("topology_contract_sha256",),
    ): "topology",
    (
        "kcs.persona.pc-route-review-receipt/v2",
        ("reviewed_route_artifact", "canonical_body_sha256"),
    ): "route-affinity-body",
}
_EXPLICIT_DEPENDENCY_IDENTITY_BY_ENTRY_ID = {
    "envelope": (
        "kcs.persona.pc-envelope/v2",
        "persona-pc-v2-envelope",
    ),
    "joint-problem": (
        "kcs.persona.pc-joint-problem/v2",
        "persona-pc-v2-joint-allocation-problem",
    ),
    "joint-solver-policy": (
        "kcs.persona.pc-joint-solver-policy/v2",
        "persona-pc-v2-joint-solver-policy",
    ),
    "route-affinity-body": (
        "kcs.persona.pc-route-affinity/v2",
        "persona-pc-v2-route-affinity-matrix",
    ),
    "topology": (
        "kcs.persona.pc-topology/v2",
        "persona-pc-v2-topology",
    ),
}
_FALSE_STATUS_TOKENS = (
    "authoritative",
    "available",
    "bound",
    "complete",
    "compiled",
    "frozen",
    "present",
    "proved",
    "ready",
    "satisfied",
)
_GENERIC_IMPLEMENTATION_SCHEMAS = frozenset(
    {
        "kcs.persona.pc-id-free-pdf-text-renderer/v2",
        "kcs.persona.pc-id-free-pdf-text-validator/v2",
        "kcs.persona.pc-id-free-text-renderer/v2",
        "kcs.persona.pc-id-free-text-validator/v2",
    }
)
# Current pre-solve bodies have no free-standing content digest fields.  A
# future field such as ``fidelity_profile_sha256`` must be added here with an
# exact schema/path contract before it can be distinguished from an omitted
# artifact dependency.  Keeping this allowlist empty is intentionally strict.
_NON_DEPENDENCY_SHA256_PATHS_BY_SCHEMA = {}
_NON_DIGEST_SHA256_METADATA_BY_SCHEMA_PATH = {
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "exact_back_binding_rules",
            "envelope_contract_sha256",
        ),
    ): "equals-bound-policy-envelope-contract-sha256",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "exact_back_binding_rules",
            "joint_problem_sha256",
        ),
    ): "equals-bound-policy-joint-problem-sha256",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "exact_back_binding_rules",
            "joint_solver_policy_sha256",
        ),
    ): "equals-canonical-sha256-of-this-generic-policy-sidecar",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "exact_back_binding_rules",
            "topology_contract_sha256",
        ),
    ): "equals-bound-policy-topology-contract-sha256",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "review_rubric",
            "future_receipt_must_bind_exact_route_matrix_sha256",
        ),
    ): True,
}

_EXACT_AUTHORITY_METADATA_BY_SCHEMA_PATH = {
    (
        "kcs.persona.pc-envelope/v2",
        ("capacity", "superseded_unmeasured_absolute_candidates_authoritative"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "authority_exact_false_fields",
        ),
    ): [
        "authorizes_g0_freeze",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "authorizes_write_or_history",
    ],
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("policy", "search_semantics", "warm_start_authority"),
    ): "advisory-only-never-acceptance-evidence",
    (
        "kcs.persona.pc-route-review-receipt/v2",
        ("authoritative_review_blockers",),
    ): [
        "independent-reviewer-identity-evidence-absent",
        "independent-reviewer-distinctness-not-attested",
        "independent-review-statement-not-bound",
    ],
    (
        "kcs.persona.pc-route-review-receipt/v2",
        ("review_summary", "review_authoritative"),
    ): False,
    (
        CORPUS_SEMANTIC_SCHEMA,
        ("completion_claims", "source_identity_namespace_authoritative"),
    ): False,
    (
        CORPUS_SEMANTIC_SCHEMA,
        ("namespace_contract", "completion_or_authority_metadata_excluded"),
    ): False,
    (
        CORPUS_SEMANTIC_SCHEMA,
        ("namespace_contract", "source_identity_derivation_authorized"),
    ): False,
    (
        CORPUS_INPUT_CLOSURE_SCHEMA,
        ("completion_claims", "source_identity_namespace_authoritative"),
    ): False,
    (
        CORPUS_INPUT_CLOSURE_SCHEMA,
        ("identity_stability_contract", "source_id_derivation_currently_authorized"),
    ): False,
    (
        EVALUATION_INPUT_CLOSURE_SCHEMA,
        ("completion_claims", "source_identity_namespace_authoritative"),
    ): False,
    (
        SUITE_INPUT_DESCRIPTOR_SCHEMA,
        ("completion_claims", "source_identity_namespace_authoritative"),
    ): False,
}
_ROOT_NEGATIVE_AUTHORITY_COUNT_PATHS = frozenset(
    {
        ("input_entries", "[]", "negative_authority_object_count"),
        ("evidence_entries", "[]", "negative_authority_object_count"),
        ("evaluation_entries", "[]", "negative_authority_object_count"),
    }
)

_EXACT_INPUT_BINDING_METADATA = {
    (
        "kcs.persona.pc-source-profile-catalog/v2",
        ("input_bindings", "binding_order"),
    ): [
        "envelope",
        "topology",
        "joint-problem",
        "joint-solver-policy",
        "variant-catalog",
        "id-free-text-renderer",
        "id-free-text-validator",
        "id-free-pdf-text-renderer",
        "id-free-pdf-text-validator",
    ],
}

_EXACT_CAPABILITY_METADATA = {
    (
        "kcs.persona.pc-realism-profile/v2",
        ("personas", "[]", "os_execution_mode"),
    ): "declared-target-metadata-only-not-native-or-emulated",
    (
        "kcs.persona.pc-envelope/v2",
        ("incidental_cap_contract", "rules", "current_plus_history"),
    ): "min(base_total,total_eligible-current_contract_chunks-history_only_contract_chunks)",
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("policy", "intent_and_identity_boundary", "pre_solve_prohibited_fields"),
    ): ["source_id", "materialization_id"],
    (
        "kcs.persona.pc-source-intent-origin-shard/v2",
        ("catalogs", "quota_contexts", "[]", "allowed_history_cohort_ids"),
    ): ["P", "X", "Y"],
    (
        "kcs.persona.pc-source-intent-origin-shard/v2",
        (
            "catalogs",
            "quota_contexts",
            "[]",
            "history_cohort_assignment_status",
        ),
    ): "solver-unassigned",
    (
        "kcs.persona.pc-fact-membership/v2",
        ("memberships", "[]", "allowed_history_cohort_ids"),
    ): ["P", "X", "Y"],
    (
        "kcs.persona.pc-history-intent/v2",
        ("representative_transition_constraint", "allowed_history_cohort_ids"),
    ): ["P", "X", "Y"],
}
_SHARED_FOUNDATIONAL_G0_BLOCKERS = [
    "bounded_framed_loader_and_exact_dispatch_missing",
    "exact_topology_sidecar_not_bound_by_g0_root",
    "joint_scope_variant_density_quota_solver_missing",
    "persona_fidelity_realism_profile_and_overlay_missing",
    "root_bound_capacity_caps_not_empirically_calibrated",
    "source_recipe_fact_oracle_and_query_spec_missing",
    "root_independent_history_intent_missing",
    "variant_complexity_units_and_feasibility_parameters_missing",
    "versioned_lane_spec_hashes_missing",
    "activity_unit_rubric_review_receipt_not_bound",
]
for _foundational_schema in (
    "kcs.persona.pc-topology/v2",
    "kcs.persona.pc-joint-problem/v2",
):
    _EXACT_CAPABILITY_METADATA[
        (_foundational_schema, ("remaining_g0_blockers",))
    ] = list(_SHARED_FOUNDATIONAL_G0_BLOCKERS)
_EXACT_CAPABILITY_METADATA[
    ("kcs.persona.pc-joint-solver-policy/v2", ("remaining_g0_blockers",))
] = [
    *_SHARED_FOUNDATIONAL_G0_BLOCKERS,
    "route_affinity_matrix_and_review_receipt_missing",
    "complete_solver_policy_binding_missing",
    "bounded_exact_solver_execution_missing",
    "canonical_joint_allocation_solution_missing",
    "exact_optimality_evidence_or_bounded_canonical_resolve_missing",
    "pilot_aggregate_cell_subset_proof_missing",
    "pilot_source_id_subset_proof_missing",
    "pilot_materialization_subset_proof_missing",
    "pilot_byte_subset_proof_missing",
    "immutable_intent_and_duplicate_cluster_refinement_missing",
    "solver_resource_limits_empirical_calibration_missing",
]
_EXACT_CAPABILITY_METADATA[
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("required_solver_outputs_and_optimality_evidence_intentionally_absent",),
    )
] = [
    "canonical-joint-allocation-solution",
    "exact-optimality-evidence-or-bounded-canonical-resolve",
    "pilot-aggregate-cell-subset-proof",
    "pilot-source-id-subset-proof",
    "pilot-materialization-subset-proof",
    "pilot-byte-subset-proof",
]
_EXACT_CAPABILITY_METADATA_VALUE_SETS = {
    (
        "kcs.persona.pc-overlay-contract/v2",
        ("content_relation_semantics", "[]", "checkpoint_history_relation"),
    ): frozenset(
        {
            "orthogonal-visible-W0-copy-not-a-KCS-history-version",
            "orthogonal-both-W0-visible-not-a-KCS-history-transition",
        }
    ),
}
_SEMANTIC_ORACLE_HISTORY_EVENT_CONTRACTS = {
    "old-wording": ("M3-2", "typed-revision"),
    "locale-language-history": ("M3-2", "typed-revision"),
    "locale-language-lifecycle": ("M3-3", "archive"),
}
_EXACT_CAPABILITY_SUBTREE_PINS = {
    (
        "kcs.persona.pc-history-intent/v2",
        ("history_cohort_templates",),
    ): (
        2_245,
        "a8c1e90f33aa4492f1d174261665edb0592e0e1546e5ddf73d901dea6623e909",
    ),
}

_EXACT_CAPABILITY_BOOL_METADATA_BY_SCHEMA_PATH = {
    (
        "kcs.persona.pc-envelope/v2",
        ("lanes", "formal-retrieval-history-v2", "formal_chunk_eligible"),
    ): True,
    (
        "kcs.persona.pc-topology/v2",
        ("policy", "activity_unit_review", "required_for_g0_freeze"),
    ): True,
    (
        "kcs.persona.pc-joint-problem/v2",
        ("proof_status", "joint_allocation_proved_for_g0"),
    ): False,
    (
        "kcs.persona.pc-joint-problem/v2",
        ("proof_status", "solver_policy_bound"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("exact_solver_executable",),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        (
            "policy",
            "route_affinity_future_input",
            "artifact_contract",
            "top_level_required_values",
            "g0_contract_frozen",
        ),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("policy_ready_for_execution",),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("proof_status", "exact_optimality_evidence_or_bounded_canonical_resolve_present"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("proof_status", "joint_allocation_proved_for_g0"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("proof_status", "solver_execution_attested"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("proof_status", "solver_policy_bound"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("proof_status", "solver_policy_bound_by_g0_root"),
    ): False,
    (
        "kcs.persona.pc-joint-solver-policy/v2",
        ("solver_policy_complete",),
    ): False,
    (
        "kcs.persona.pc-overlay-contract/v2",
        ("placement_contract", "content_relation_endpoints_must_resolve_to_different_scopes"),
    ): True,
    (
        "kcs.persona.pc-overlay-contract/v2",
        (
            "completion_claims",
            "query_history_target_namespace_mapping_complete",
        ),
    ): False,
    (
        "kcs.persona.pc-fact-graph/v2",
        ("history_intent_recipe_bound",),
    ): False,
    (
        "kcs.persona.pc-source-intent-origin-shard/v2",
        ("completion_claims", "history_event_recipe_bound"),
    ): False,
    (
        "kcs.persona.pc-source-intent-origin-shard/v2",
        ("origin_contract", "solver_delta_value_allowed_as_intent_origin"),
    ): False,
    (
        "kcs.persona.pc-fact-membership/v2",
        ("history_intent_recipe_bound",),
    ): False,
    (
        "kcs.persona.pc-history-intent/v2",
        ("compiled_history_plan",),
    ): False,
    (
        "kcs.persona.pc-history-intent/v2",
        ("history_executor_available",),
    ): False,
    (
        "kcs.persona.pc-history-intent/v2",
        ("history_intent_inventory_complete",),
    ): False,
    (
        "kcs.persona.pc-history-intent/v2",
        ("history_operation_template_inventory_complete",),
    ): False,
    (
        "kcs.persona.pc-history-intent/v2",
        (
            "representative_transition_constraint",
            "solver_assigned_history_cohort_id_present",
        ),
    ): False,
    (
        "kcs.persona.pc-query-intent/v2",
        (
            "target_resolution_contract",
            "all_expected_targets_must_exact_resolve_before_g0",
        ),
    ): True,
    (
        "kcs.persona.pc-query-intent/v2",
        ("target_resolution_contract", "history_intent_targets_bound"),
    ): False,
    (
        "kcs.persona.pc-query-intent/v2",
        (
            "target_resolution_contract",
            "unresolved_target_keys_are_not_source_plan_membership",
        ),
    ): True,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        ("compiled_relevance_contract", "compilation_must_follow_solved_source_plan"),
    ): True,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        ("compiled_relevance_contract", "compilation_must_join_history_receipts"),
    ): True,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        ("completion_claims", "full_history_intent_membership_bound"),
    ): False,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        ("completion_claims", "restore_anchor_source_history_bindings_compiled"),
    ): False,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        (
            "target_resolution_contract",
            "all_positive_answer_memberships_must_exact_resolve_before_g0",
        ),
    ): True,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        (
            "target_resolution_contract",
            "all_restore_and_deleted_event_templates_must_exact_resolve_before_g0",
        ),
    ): True,
    (
        "kcs.persona.pc-semantic-oracle/v2",
        (
            "target_resolution_contract",
            "unresolved_target_keys_are_not_compiled_relevance",
        ),
    ): True,
}
for _root_schema in _ROOT_SCHEMAS:
    _EXACT_CAPABILITY_BOOL_METADATA_BY_SCHEMA_PATH[
        (_root_schema, ("completion_claims", "canonical_g0_input_inventory_complete"))
    ] = False

_AUTHORITY_CAPABILITY_FRAGMENTS = (
    "capabilit",
    "contractfreeze",
    "execute",
    "execution",
    "filemodification",
    "filesystemmutation",
    "g0",
    "gzero",
    "history",
    "persistfile",
    "plansource",
    "solve",
    "solver",
    "sourceplan",
    "write",
)
_CAPABILITY_CLAIM_MARKERS = (
    "access",
    "active",
    "allow",
    "approv",
    "attest",
    "authoris",
    "authoriz",
    "available",
    "capability",
    "enable",
    "executable",
    "grant",
    "permission",
    "permit",
    "ready",
)
_NEGATIVE_CAPABILITY_FRAGMENTS = (
    "denied",
    "disabled",
    "disallow",
    "forbid",
    "notallowed",
    "prohibit",
)
_CAPABILITY_SCALAR_CLAIMS = frozenset(
    {
        "active",
        "allowed",
        "approved",
        "available",
        "enabled",
        "executable",
        "granted",
        "on",
        "permitted",
        "ready",
        "true",
        "unrestricted",
        "yes",
    }
)
_CAPABILITY_CLAIM_FIELD_SUFFIXES = ("flag", "mode", "state", "status")


class PersonaV2InputClosureError(ValueError):
    """Raised when an injected body, pin, edge, or input root is invalid."""


def _require_nonempty_string(value, *, label):
    if type(value) is not str or not value:
        raise PersonaV2InputClosureError(f"{label} must be a non-empty string")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        raise PersonaV2InputClosureError(f"{label} must be valid UTF-8") from None
    if len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        raise PersonaV2InputClosureError(f"{label} exceeds the shared string cap")
    artifact_common.validate_plain_value(value, label=label)
    return value


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise PersonaV2InputClosureError(
            f"{label} must be exact lowercase SHA-256"
        )
    return value


def _looks_like_sha256(value):
    return (
        type(value) is str
        and len(value) == 64
        and all(character.lower() in "0123456789abcdef" for character in value)
    )


def _is_input_binding_sha256_path(path):
    return bool(path) and path[-1] == "sha256" and any(
        segment == "input_bindings" for segment in path[:-1]
    )


def _explicit_dependency_owner(schema, path):
    normalized = tuple("[]" if type(segment) is int else segment for segment in path)
    return _EXPLICIT_DEPENDENCY_OWNER_BY_SCHEMA_PATH.get((schema, normalized))


def _is_sha256_field_name(key):
    if type(key) is not str:
        return False
    compact = "".join(character for character in key.lower() if character.isalnum())
    return compact == "sha256" or compact.endswith("sha256")


def _is_digest_field_name(key):
    if type(key) is not str:
        return False
    compact = "".join(character for character in key.lower() if character.isalnum())
    return compact == "digest" or compact.endswith("digest")


def _is_allowlisted_non_dependency_sha256_path(schema, path):
    normalized = tuple("[]" if type(segment) is int else segment for segment in path)
    return normalized in _NON_DEPENDENCY_SHA256_PATHS_BY_SCHEMA.get(schema, frozenset())


def _is_exact_non_digest_sha256_metadata(schema, path, item):
    normalized = tuple("[]" if type(segment) is int else segment for segment in path)
    metadata_key = (schema, normalized)
    if metadata_key not in _NON_DIGEST_SHA256_METADATA_BY_SCHEMA_PATH:
        return False
    expected = _NON_DIGEST_SHA256_METADATA_BY_SCHEMA_PATH[metadata_key]
    return type(item) is type(expected) and item == expected


def _is_exact_route_review_digest_evidence_path(body, path):
    if body.get("artifact_schema") != "kcs.persona.pc-route-review-receipt/v2":
        return False
    if tuple(path) not in {
        ("checks", 0, "expected"),
        ("checks", 0, "observed"),
    }:
        return False
    checks = body.get("checks")
    return (
        type(checks) is list
        and bool(checks)
        and type(checks[0]) is dict
        and checks[0].get("check_id") == "exact-route-artifact-binding"
    )


def _validate_exact_route_review_digest_evidence(body, path, item, *, entry_id):
    reviewed = body.get("reviewed_route_artifact")
    reviewed_digest = None if type(reviewed) is not dict else reviewed.get(
        "canonical_body_sha256"
    )
    if (
        not _looks_like_sha256(item)
        or item != item.lower()
        or item != reviewed_digest
    ):
        raise PersonaV2InputClosureError(
            f"{entry_id} exact route-review digest evidence at {path!r} must "
            "equal reviewed_route_artifact.canonical_body_sha256"
        )


def _validate_route_review_digest_evidence_contract(body, *, entry_id):
    if body.get("artifact_schema") != "kcs.persona.pc-route-review-receipt/v2":
        return
    reviewed = body.get("reviewed_route_artifact")
    checks = body.get("checks")
    if (
        type(reviewed) is not dict
        or type(checks) is not list
        or not checks
        or type(checks[0]) is not dict
        or checks[0].get("check_id") != "exact-route-artifact-binding"
    ):
        raise PersonaV2InputClosureError(
            f"{entry_id} route-review digest contract requires reviewed route "
            "metadata and exact check 0"
        )
    reviewed_digest = _require_sha256(
        reviewed.get("canonical_body_sha256"),
        label=f"{entry_id} reviewed route artifact SHA-256",
    )
    for field in ("expected", "observed"):
        if checks[0].get(field) != reviewed_digest:
            raise PersonaV2InputClosureError(
                f"{entry_id} exact route-review digest evidence at "
                f"{['checks', 0, field]!r} must equal "
                "reviewed_route_artifact.canonical_body_sha256"
            )


def _normalize_roots(root_entry_ids, *, label):
    if type(root_entry_ids) is not list or not root_entry_ids:
        raise PersonaV2InputClosureError(f"{label} must be a non-empty list")
    if len(root_entry_ids) > MAX_ENTRY_COUNT:
        raise PersonaV2InputClosureError(f"{label} exceeds the closure cap")
    normalized = [
        _require_nonempty_string(entry_id, label=f"{label} entry")
        for entry_id in root_entry_ids
    ]
    if len(set(normalized)) != len(normalized):
        raise PersonaV2InputClosureError(f"{label} contains duplicate entries")
    return sorted(normalized, key=lambda value: value.encode("utf-8"))


def _normalize_pins(pins, *, expected_input_class):
    if type(pins) is not list or not pins:
        raise PersonaV2InputClosureError("pins must be a non-empty list")
    if len(pins) > MAX_ENTRY_COUNT:
        raise PersonaV2InputClosureError("pin count exceeds the closure cap")
    normalized = []
    seen_ids = set()
    seen_sha256 = set()
    for index, pin in enumerate(pins):
        if type(pin) is not dict or set(pin) != PIN_FIELDS:
            raise PersonaV2InputClosureError(
                f"pin {index} must contain the exact pin schema"
            )
        row = copy.deepcopy(pin)
        entry_id = _require_nonempty_string(
            row["entry_id"], label=f"pin {index} entry_id"
        )
        if entry_id in seen_ids:
            raise PersonaV2InputClosureError(f"duplicate pin entry_id: {entry_id}")
        seen_ids.add(entry_id)
        for field in ("artifact_kind", "artifact_schema", "fixture_id"):
            _require_nonempty_string(row[field], label=f"{entry_id} {field}")
        if type(row["artifact_schema_version"]) is not int or row[
            "artifact_schema_version"
        ] != 2:
            raise PersonaV2InputClosureError(
                f"{entry_id} artifact_schema_version must be exact 2"
            )
        if type(row["fixture_schema_version"]) is not int or row[
            "fixture_schema_version"
        ] != 2:
            raise PersonaV2InputClosureError(
                f"{entry_id} fixture_schema_version must be exact 2"
            )
        if (
            type(row["canonical_bytes"]) is not int
            or row["canonical_bytes"] <= 0
            or row["canonical_bytes"] > MAX_UPSTREAM_BODY_BYTES
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} canonical_bytes is outside the in-memory cap"
            )
        digest = _require_sha256(row["sha256"], label=f"{entry_id} sha256")
        if digest in seen_sha256:
            raise PersonaV2InputClosureError(
                f"duplicate pinned body SHA-256: {digest}"
            )
        seen_sha256.add(digest)
        if row["input_class"] != expected_input_class:
            raise PersonaV2InputClosureError(
                f"{entry_id} input_class must be {expected_input_class!r}"
            )
        if row["input_class"] not in INPUT_CLASSES:
            raise PersonaV2InputClosureError(
                f"{entry_id} has an unknown input_class"
            )
        aliases = row["binding_aliases"]
        if type(aliases) is not list or not aliases:
            raise PersonaV2InputClosureError(
                f"{entry_id} binding_aliases must be a non-empty list"
            )
        if len(aliases) > MAX_BINDING_ALIASES_PER_ENTRY:
            raise PersonaV2InputClosureError(
                f"{entry_id} binding_aliases exceeds the per-entry cap"
            )
        normalized_aliases = [
            _require_nonempty_string(alias, label=f"{entry_id} binding alias")
            for alias in aliases
        ]
        if len(set(normalized_aliases)) != len(normalized_aliases):
            raise PersonaV2InputClosureError(
                f"{entry_id} contains duplicate binding aliases"
            )
        if entry_id not in normalized_aliases:
            raise PersonaV2InputClosureError(
                f"{entry_id} binding_aliases must include its entry_id"
            )
        reserved_aliases = set(normalized_aliases) & _RESERVED_ANCHOR_ENTRY_IDS
        if reserved_aliases:
            raise PersonaV2InputClosureError(
                f"{entry_id} uses reserved anchor binding aliases: "
                f"{sorted(reserved_aliases)!r}"
            )
        row["binding_aliases"] = sorted(
            normalized_aliases, key=lambda value: value.encode("utf-8")
        )
        dependencies = row["dependency_ids"]
        if type(dependencies) is not list:
            raise PersonaV2InputClosureError(
                f"{entry_id} dependency_ids must be a list"
            )
        if len(dependencies) > MAX_DEPENDENCIES_PER_ENTRY:
            raise PersonaV2InputClosureError(
                f"{entry_id} dependency_ids exceeds the per-entry cap"
            )
        for dependency_id in dependencies:
            _require_nonempty_string(
                dependency_id, label=f"{entry_id} dependency_id"
            )
        if len(set(dependencies)) != len(dependencies):
            raise PersonaV2InputClosureError(
                f"{entry_id} contains duplicate dependency IDs"
            )
        row["dependency_ids"] = sorted(
            dependencies, key=lambda value: value.encode("utf-8")
        )
        _enforce_input_class_identity(row)
        normalized.append(row)
    return normalized


def _enforce_input_class_identity(pin):
    identity = f"{pin['artifact_schema']} {pin['artifact_kind']}".lower()
    input_class = pin["input_class"]
    if input_class == "corpus-semantic" and any(
        token in identity for token in ("query", "oracle", "receipt", "review")
    ):
        raise PersonaV2InputClosureError(
            f"{pin['entry_id']} is not an admissible corpus-semantic body"
        )
    if input_class == "evidence" and not any(
        token in identity for token in ("evidence", "receipt", "review")
    ):
        raise PersonaV2InputClosureError(
            f"{pin['entry_id']} evidence input must be a receipt/review body"
        )
    if input_class == "evidence" and any(
        token in identity for token in ("query", "oracle")
    ):
        raise PersonaV2InputClosureError(
            f"{pin['entry_id']} evaluation identity is forbidden in evidence"
        )
    if input_class == "evaluation" and not any(
        token in identity for token in ("query", "oracle")
    ):
        raise PersonaV2InputClosureError(
            f"{pin['entry_id']} evaluation input must be query/oracle material"
        )
    if input_class == "evaluation" and any(
        token in identity for token in ("evidence", "receipt", "review")
    ):
        raise PersonaV2InputClosureError(
            f"{pin['entry_id']} evidence identity is forbidden in evaluation"
        )


def _normalize_providers(providers):
    if type(providers) is not list or not providers:
        raise PersonaV2InputClosureError("providers must be a non-empty list")
    if len(providers) > MAX_ENTRY_COUNT:
        raise PersonaV2InputClosureError("provider count exceeds the closure cap")
    result = {}
    for index, provider in enumerate(providers):
        if type(provider) is not dict or set(provider) != PROVIDER_FIELDS:
            raise PersonaV2InputClosureError(
                f"provider {index} must contain the exact provider schema"
            )
        entry_id = _require_nonempty_string(
            provider["entry_id"], label=f"provider {index} entry_id"
        )
        if entry_id in result:
            raise PersonaV2InputClosureError(
                f"duplicate provider entry_id: {entry_id}"
            )
        if type(provider["body"]) is not dict:
            raise PersonaV2InputClosureError(f"{entry_id} body must be an object")
        if not callable(provider["validate"]) or not callable(
            provider["canonicalize"]
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} validator and canonicalizer must be callable"
            )
        result[entry_id] = provider
    return result


def _normalized_contract_path(path):
    return tuple("[]" if type(segment) is int else segment for segment in path)


def _allowed_authority_metadata(body, path, value):
    schema = body.get("artifact_schema")
    if (
        _normalized_contract_path(path) in _ROOT_NEGATIVE_AUTHORITY_COUNT_PATHS
        and schema in _ROOT_SCHEMAS
        and type(value) is int
        and value > 0
    ):
        return True
    metadata_key = (schema, _normalized_contract_path(path))
    if metadata_key in _EXACT_AUTHORITY_METADATA_BY_SCHEMA_PATH:
        expected = _EXACT_AUTHORITY_METADATA_BY_SCHEMA_PATH[metadata_key]
        return type(value) is type(expected) and value == expected
    return False


def _allowed_authority_field_names(body, path, field_names):
    if path != ["authority"]:
        return False
    actual = frozenset(field_names)
    expected = _EXACT_TOP_LEVEL_AUTHORITY_FIELDS_BY_SCHEMA.get(
        body.get("artifact_schema")
    )
    if expected is not None:
        return actual == expected
    return actual == _STANDARD_NEGATIVE_AUTHORITY_FIELDS


def _allowed_semantic_oracle_history_event_template(body, path, value):
    if (
        body.get("artifact_schema") != "kcs.persona.pc-semantic-oracle/v2"
        or len(path) != 4
        or path[0] != "positive_oracle_rows"
        or type(path[1]) is not int
        or path[2:] != ["evidence_contract", "history_event_template_key"]
        or type(value) is not str
    ):
        return False
    rows = body.get("positive_oracle_rows")
    row_index = path[1]
    if (
        type(rows) is not list
        or row_index < 0
        or row_index >= len(rows)
        or type(rows[row_index]) is not dict
    ):
        return False
    row = rows[row_index]
    persona_id = body.get("persona_id")
    scenario_id = row.get("scenario_id")
    stratum_id = row.get("stratum_id")
    query_key = row.get("query_intent_key")
    if not all(
        type(item) is str and item
        for item in (persona_id, scenario_id, stratum_id, query_key)
    ):
        return False
    ordinal_text = query_key.rsplit("-", 1)[-1]
    if (
        len(ordinal_text) != 2
        or not ordinal_text.isascii()
        or not ordinal_text.isdigit()
    ):
        return False
    ordinal = int(ordinal_text)
    if ordinal < 1 or ordinal > 10:
        return False
    expected_scenario_and_operation = (
        ("M3-2", (
            "same-scope-rename"
            if ordinal % 2
            else "searchable-cross-scope-move"
        ))
        if stratum_id == "rename-move"
        else _SEMANTIC_ORACLE_HISTORY_EVENT_CONTRACTS.get(stratum_id)
    )
    if expected_scenario_and_operation is None:
        return False
    expected_scenario, operation = expected_scenario_and_operation
    expected_query_key = (
        f"query-{persona_id}-{expected_scenario.lower()}-"
        f"{stratum_id}-{ordinal:02d}"
    )
    if scenario_id != expected_scenario or query_key != expected_query_key:
        return False
    return value == f"history-event-template-{query_key[6:]}-{operation}"


def _allowed_capability_metadata(body, path, key, value):
    bool_metadata_key = (
        body.get("artifact_schema"),
        _normalized_contract_path(path),
    )
    if bool_metadata_key in _EXACT_CAPABILITY_BOOL_METADATA_BY_SCHEMA_PATH:
        expected = _EXACT_CAPABILITY_BOOL_METADATA_BY_SCHEMA_PATH[
            bool_metadata_key
        ]
        return type(value) is bool and value is expected
    metadata_key = (
        body.get("artifact_schema"),
        _normalized_contract_path(path),
    )
    if metadata_key in _EXACT_CAPABILITY_SUBTREE_PINS:
        try:
            raw = artifact_common.canonical_json_bytes(
                value,
                label="exact capability subtree",
                max_bytes=MAX_UPSTREAM_BODY_BYTES,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2InputClosureError(str(error)) from None
        expected_bytes, expected_sha256 = _EXACT_CAPABILITY_SUBTREE_PINS[
            metadata_key
        ]
        if (
            len(raw) != expected_bytes
            or hashlib.sha256(raw).hexdigest() != expected_sha256
        ):
            raise PersonaV2InputClosureError(
                "exact capability subtree canonical bytes/SHA pin drifted"
            )
        return True
    if metadata_key in _EXACT_CAPABILITY_METADATA:
        expected = _EXACT_CAPABILITY_METADATA[metadata_key]
        return type(value) is type(expected) and value == expected
    if metadata_key in _EXACT_CAPABILITY_METADATA_VALUE_SETS:
        return (
            type(value) is str
            and value in _EXACT_CAPABILITY_METADATA_VALUE_SETS[metadata_key]
        )
    if _allowed_semantic_oracle_history_event_template(body, path, value):
        return True
    return False


def _is_exact_capability_subtree_path(body, path):
    return (
        body.get("artifact_schema"),
        _normalized_contract_path(path),
    ) in _EXACT_CAPABILITY_SUBTREE_PINS


def _contains_protected_capability_scalar(value):
    if type(value) is str:
        compact = "".join(
            character for character in value.lower() if character.isalnum()
        )
        return any(
            fragment in compact
            for fragment in _AUTHORITY_CAPABILITY_FRAGMENTS
        )
    if type(value) is list:
        return any(_contains_protected_capability_scalar(item) for item in value)
    if type(value) is dict:
        return any(
            _contains_protected_capability_scalar(item)
            for item in value.values()
        )
    return False


def _require_negative_authority(body, *, entry_id):
    authority_path_count = 0

    def visit(
        node,
        path,
        *,
        inside_authority=False,
        capability_context=False,
    ):
        nonlocal authority_path_count
        if type(node) is str:
            compact_value = "".join(
                character for character in node.lower() if character.isalnum()
            )
            compact_field = (
                "".join(
                    character
                    for character in path[-1].lower()
                    if character.isalnum()
                )
                if path and type(path[-1]) is str
                else ""
            )
            if (
                capability_context
                and (
                    compact_field.endswith(("mode", "status"))
                    or
                    compact_value in _CAPABILITY_SCALAR_CLAIMS
                    or any(
                        fragment in compact_value
                        for fragment in _AUTHORITY_CAPABILITY_FRAGMENTS
                    )
                    or any(
                        marker in compact_value
                        for marker in _CAPABILITY_CLAIM_MARKERS
                    )
                    or any(
                        fragment in compact_value
                        for fragment in _NEGATIVE_CAPABILITY_FRAGMENTS
                    )
                    or "unblock" in compact_value
                )
            ):
                raise PersonaV2InputClosureError(
                    f"{entry_id} structured capability claim at {path!r} "
                    "has unsafe polarity"
                )
            return
        if type(node) is list:
            for index, item in enumerate(node):
                visit(
                    item,
                    path + [index],
                    inside_authority=inside_authority,
                    capability_context=capability_context,
                )
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            child_path = path + [key]
            if key == "authority":
                authority_path_count += 1
                if type(item) is not dict or not item:
                    raise PersonaV2InputClosureError(
                        f"{entry_id} authority must be a non-empty object"
                    )
                if any(
                    type(flag_name) is not str
                    or type(flag) is not bool
                    or flag is not False
                    for flag_name, flag in item.items()
                ):
                    raise PersonaV2InputClosureError(
                        f"{entry_id} authority flags must all be exact false"
                    )
                if not _allowed_authority_field_names(
                    body, child_path, item.keys()
                ):
                    raise PersonaV2InputClosureError(
                        f"{entry_id} authority must contain an exact "
                        "schema/path field-name set"
                    )
            lowered = key.lower()
            compact = "".join(
                character for character in lowered if character.isalnum()
            )
            if compact in _COMPACT_MUST_REMAIN_FALSE_KEYS and (
                type(item) is not bool or item is not False
            ):
                raise PersonaV2InputClosureError(
                    f"{entry_id} {key} must remain exact false"
                )
            if not inside_authority and key != "authority" and any(
                token in compact
                for token in ("authorit", "authoriz", "authoris")
            ) and not _allowed_authority_metadata(body, child_path, item):
                raise PersonaV2InputClosureError(
                    f"{entry_id} authority-like claim {key!r} is not exact "
                    "allowlisted metadata"
                )
            protected_capability = any(
                capability in compact
                for capability in _AUTHORITY_CAPABILITY_FRAGMENTS
            )
            claim_marker = any(
                marker in compact for marker in _CAPABILITY_CLAIM_MARKERS
            ) or (
                compact.startswith(("can", "may"))
                and not compact.startswith("canonical")
            ) or any(
                fragment in compact
                for fragment in _NEGATIVE_CAPABILITY_FRAGMENTS
            )
            child_capability_context = (
                not inside_authority
                and (
                    capability_context
                    or protected_capability
                    or (
                        claim_marker
                        and type(item) in {dict, list}
                        and _contains_protected_capability_scalar(item)
                    )
                )
            )
            allowed_metadata = False
            if child_capability_context:
                universally_required_top_level_g0_false = (
                    child_path == ["g0_contract_frozen"] and item is False
                )
                allowed_metadata = _allowed_capability_metadata(
                    body, child_path, key, item
                )
                if (
                    compact.endswith(_CAPABILITY_CLAIM_FIELD_SUFFIXES)
                    and not allowed_metadata
                ):
                    raise PersonaV2InputClosureError(
                        f"{entry_id} capability claim {key!r} has unsafe polarity"
                    )
                if type(item) is bool:
                    if not (
                        universally_required_top_level_g0_false
                        or allowed_metadata
                    ):
                        raise PersonaV2InputClosureError(
                            f"{entry_id} capability claim {key!r} has unsafe polarity"
                        )
                elif claim_marker and not allowed_metadata:
                    raise PersonaV2InputClosureError(
                        f"{entry_id} capability claim {key!r} has unsafe polarity"
                    )
            if allowed_metadata and _is_exact_capability_subtree_path(
                body, child_path
            ):
                continue
            visit(
                item,
                child_path,
                inside_authority=(key == "authority"),
                capability_context=(
                    False
                    if key == "authority" or allowed_metadata
                    else child_capability_context
                ),
            )

    visit(body, [])
    authority = body.get("authority")
    if type(authority) is not dict or not authority:
        raise PersonaV2InputClosureError(
            f"{entry_id} must expose top-level negative authority"
        )
    generic_implementation = (
        body.get("artifact_schema") in _GENERIC_IMPLEMENTATION_SCHEMAS
    )
    if body.get("g0_contract_frozen") is not False and not (
        generic_implementation
        and "g0_contract_frozen" not in body
        and authority.get("authorizes_g0_freeze") is False
    ):
        raise PersonaV2InputClosureError(
            f"{entry_id} must expose g0_contract_frozen=false"
        )
    return authority_path_count


def _binding_row_alias(row, path):
    aliases = []
    for field in ("entry_id", "name"):
        if field in row:
            if type(row[field]) is not str or not row[field]:
                raise PersonaV2InputClosureError(
                    f"input dependency {field} must be a non-empty string"
                )
            aliases.append(row[field])
    if (
        path
        and type(path[-1]) is str
        and path[-1] != "input_bindings"
    ):
        aliases.append(path[-1])
    if len(set(aliases)) != len(aliases):
        raise PersonaV2InputClosureError(
            "input dependency row contains duplicate textual identities"
        )
    if not aliases:
        raise PersonaV2InputClosureError(
            "input dependency SHA must have an entry_id, name, or mapping key"
        )
    return aliases


def _validate_input_binding_collections(
    body,
    *,
    entry_id,
    known_digest_to_id,
    known_metadata_by_id,
    aliases_by_id,
):
    seen_binding_digests = {}
    seen_binding_aliases = {}
    primary_names_by_collection = {}
    binding_orders_by_collection = {}

    def register_row(row, path, collection_path):
        digest = _require_sha256(
            row.get("sha256"),
            label=f"{entry_id} input dependency SHA at {path!r}",
        )
        if digest not in known_digest_to_id:
            raise PersonaV2InputClosureError(
                f"{entry_id} input dependency SHA has no known pin"
            )
        dependency_id = known_digest_to_id[digest]
        expected_metadata = known_metadata_by_id[dependency_id]
        for field in _BINDING_OWNER_METADATA_FIELDS:
            if field not in row:
                continue
            expected = expected_metadata[field]
            if type(row[field]) is not type(expected) or row[field] != expected:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input binding {field} contradicts exact "
                    f"SHA owner {dependency_id!r}"
                )
        declared_aliases = _binding_row_alias(row, path)
        primary_name = row.get("entry_id") or row.get("name") or path[-1]
        row_path = tuple(path)
        if digest in seen_binding_digests:
            raise PersonaV2InputClosureError(
                f"{entry_id} input bindings repeat SHA {digest!r} across "
                f"{seen_binding_digests[digest]!r} and {row_path!r}"
            )
        seen_binding_digests[digest] = row_path
        for alias in declared_aliases:
            if alias in seen_binding_aliases:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input bindings repeat name {alias!r} across "
                    f"{seen_binding_aliases[alias]!r} and {row_path!r}"
                )
            seen_binding_aliases[alias] = row_path
        primary_names_by_collection.setdefault(collection_path, set()).add(
            primary_name
        )
        allowed_aliases = aliases_by_id[dependency_id]
        for alias in declared_aliases:
            if alias not in allowed_aliases:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input binding name {alias!r} does not match "
                    f"SHA owner {dependency_id!r}"
                )

    def validate_collection(node, path, collection_path):
        if type(node) is list:
            for index, item in enumerate(node):
                if type(item) is not dict or not item:
                    raise PersonaV2InputClosureError(
                        f"{entry_id} input_bindings contains a non-object or empty leaf"
                    )
                validate_collection(item, path + [index], collection_path)
            return
        if type(node) is not dict:
            raise PersonaV2InputClosureError(
                f"{entry_id} input_bindings must be a list or object"
            )
        exact_metadata = []
        for key, item in node.items():
            metadata_key = (
                body.get("artifact_schema"),
                tuple(path + [key]),
            )
            if metadata_key not in _EXACT_INPUT_BINDING_METADATA:
                continue
            expected = _EXACT_INPUT_BINDING_METADATA[metadata_key]
            if type(item) is not type(expected) or item != expected:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input_bindings metadata at "
                    f"{path + [key]!r} drifted"
                )
            exact_metadata.append((key, item))
        if "sha256" in node:
            if exact_metadata:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input_bindings metadata cannot be embedded "
                    "in a binding leaf"
                )
            register_row(node, path, collection_path)
            for key, item in node.items():
                if key != "sha256":
                    find_nested_rows(item, path + [key], collection_path)
            return
        for key, item in node.items():
            metadata_key = (
                body.get("artifact_schema"),
                tuple(path + [key]),
            )
            if metadata_key in _EXACT_INPUT_BINDING_METADATA:
                if collection_path in binding_orders_by_collection:
                    raise PersonaV2InputClosureError(
                        f"{entry_id} input_bindings repeats binding_order metadata"
                    )
                binding_orders_by_collection[collection_path] = list(item)
                continue
            if type(item) not in {dict, list} or not item:
                raise PersonaV2InputClosureError(
                    f"{entry_id} input_bindings contains a malformed binding leaf"
                )
            validate_collection(item, path + [key], collection_path)

    def find_nested_rows(node, path, collection_path):
        if type(node) is list:
            for index, item in enumerate(node):
                find_nested_rows(item, path + [index], collection_path)
            return
        if type(node) is not dict:
            return
        if "sha256" in node:
            register_row(node, path, collection_path)
        for key, item in node.items():
            if key != "sha256":
                find_nested_rows(item, path + [key], collection_path)

    def find_collections(node, path):
        if type(node) is list:
            for index, item in enumerate(node):
                find_collections(item, path + [index])
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            child_path = path + [key]
            if key == "input_bindings":
                validate_collection(item, child_path, tuple(child_path))
            find_collections(item, child_path)

    find_collections(body, [])
    for collection_path, binding_order in binding_orders_by_collection.items():
        primary_names = primary_names_by_collection.get(collection_path, set())
        if (
            len(primary_names) != len(binding_order)
            or primary_names != set(binding_order)
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} input_bindings binding_order must exactly cover "
                "the collection binding row primary names"
            )


def _is_prohibited_corpus_query_semantic_key(body, *, key, item):
    normalized = "".join(
        character for character in key.lower() if character.isalnum()
    )
    if not any(
        fragment in normalized
        for fragment in _CORPUS_QUERY_SEMANTIC_KEY_FRAGMENTS
    ):
        return False
    # Exact false is admissible only as negative metadata.  It contributes to
    # propagated false-status evidence and cannot carry query/oracle content.
    if type(item) is bool and item is False:
        return False
    metadata_key = (body.get("artifact_schema"), key)
    if metadata_key in _ALLOWED_CORPUS_QUERY_SEMANTIC_METADATA:
        expected = _ALLOWED_CORPUS_QUERY_SEMANTIC_METADATA[metadata_key]
        if type(item) is type(expected) and item == expected:
            return False
    return True


def _path_sort_key(path):
    return tuple(
        (0, segment.encode("utf-8"))
        if type(segment) is str
        else (1, segment)
        for segment in path
    )


def _validate_sensitive_key(body, *, entry_id, key, item):
    normalized = key.lower().replace("-", "_")
    compact = "".join(character for character in normalized if character.isalnum())
    schema = body.get("artifact_schema")
    if any(fragment in compact for fragment in _COMPACT_CLOSURE_KEY_FRAGMENTS):
        if type(item) is bool and item is False:
            return
        if (
            (schema, key) in _ALLOWED_TRUE_CLOSURE_SEPARATION_KEYS
            and type(item) is bool
            and item is True
        ):
            return
        raise PersonaV2InputClosureError(
            f"{entry_id} contains a downstream closure/back-binding field {key!r}"
        )
    if any(fragment in compact for fragment in _COMPACT_FINAL_ID_KEY_FRAGMENTS):
        if type(item) is bool and item is False:
            return
        metadata_key = (schema, key)
        if metadata_key in _ALLOWED_FINAL_ID_METADATA:
            expected = _ALLOWED_FINAL_ID_METADATA[metadata_key]
            if type(item) is type(expected) and item == expected:
                return
        raise PersonaV2InputClosureError(
            f"{entry_id} contains final identity data field {key!r}"
        )
    if "compiledrelevance" in compact:
        if type(item) is bool and item is False:
            return
        if (
            key == "compiled_relevance_contract"
            and schema == "kcs.persona.pc-semantic-oracle/v2"
            and item == _SEMANTIC_ORACLE_COMPILED_RELEVANCE_CONTRACT
        ):
            return
        if (
            (schema, key) in _ALLOWED_TRUE_COMPILED_RELEVANCE_KEYS
            and type(item) is bool
            and item is True
        ):
            return
        raise PersonaV2InputClosureError(
            f"{entry_id} contains compiled relevance data field {key!r}"
        )


def _scan_body(
    *,
    body,
    entry_id,
    input_class,
    known_digest_to_id,
    known_metadata_by_id,
    known_identity_by_id,
    aliases_by_id,
):
    referenced_ids = set()

    _validate_route_review_digest_evidence_contract(body, entry_id=entry_id)
    _validate_input_binding_collections(
        body,
        entry_id=entry_id,
        known_digest_to_id=known_digest_to_id,
        known_metadata_by_id=known_metadata_by_id,
        aliases_by_id=aliases_by_id,
    )
    false_status_paths = []

    def visit(node, path):
        if type(node) is str:
            if node in _ROOT_SCHEMAS or node in _ROOT_KINDS:
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains a forbidden closure back-reference"
                )
            if _looks_like_sha256(node):
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains an unclassified artifact-looking "
                    f"digest at {path!r}"
                )
            return
        if type(node) is list:
            for index, item in enumerate(node):
                visit(item, path + [index])
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            if _looks_like_sha256(key):
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains an artifact-looking digest as an "
                    f"object key at {path + [key]!r}"
                )
            lowered = key.lower()
            _validate_sensitive_key(
                body, entry_id=entry_id, key=key, item=item
            )
            if key in _FORBIDDEN_CLOSURE_HASH_KEYS or (
                "input_closure" in lowered and lowered.endswith("sha256")
            ):
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains downstream closure hash field {key!r}"
                )
            if key in _FORBIDDEN_PRE_SOLVE_ID_KEYS:
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains prohibited pre-solve identifier {key!r}"
                )
            if input_class == "evaluation" and key in _FORBIDDEN_EVALUATION_DATA_KEYS:
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains prohibited evaluation input field {key!r}"
                )
            if (
                input_class in {"corpus-semantic", "evidence"}
                and (
                    key
                    in (
                        _FORBIDDEN_EVALUATION_DATA_KEYS
                        | _FORBIDDEN_CORPUS_QUERY_SEMANTIC_KEYS
                    )
                    or _is_prohibited_corpus_query_semantic_key(
                        body, key=key, item=item
                    )
                )
            ):
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains prohibited corpus-side query/oracle "
                    f"semantic field {key!r}"
                )
            child_path = path + [key]
            classified_digest_value = False
            if _is_sha256_field_name(key) or _is_digest_field_name(key):
                classified_digest_value = True
                if _is_digest_field_name(key) and type(item) is bool and item is False:
                    pass
                elif _is_exact_non_digest_sha256_metadata(
                    body.get("artifact_schema"), child_path, item
                ):
                    pass
                else:
                    digest = _require_sha256(
                        item,
                        label=f"{entry_id} SHA-256 field at {child_path!r}",
                    )
                    expected_owner = _explicit_dependency_owner(
                        body.get("artifact_schema"), child_path
                    )
                    if expected_owner is not None:
                        if digest not in known_digest_to_id:
                            raise PersonaV2InputClosureError(
                                f"{entry_id} dependency SHA at {child_path!r} has no "
                                "known internal or external pin"
                            )
                        actual_owner = known_digest_to_id[digest]
                        if actual_owner != expected_owner:
                            raise PersonaV2InputClosureError(
                                f"{entry_id} explicit dependency field at "
                                f"{child_path!r} must bind {expected_owner!r}, "
                                f"not {actual_owner!r}"
                            )
                        expected_identity = (
                            _EXPLICIT_DEPENDENCY_IDENTITY_BY_ENTRY_ID[
                                expected_owner
                            ]
                        )
                        if known_identity_by_id[actual_owner] != expected_identity:
                            raise PersonaV2InputClosureError(
                                f"{entry_id} explicit dependency field at "
                                f"{child_path!r} binds {actual_owner!r} with the "
                                "wrong artifact schema/kind identity"
                            )
                        referenced_ids.add(actual_owner)
                    elif _is_input_binding_sha256_path(child_path):
                        if digest not in known_digest_to_id:
                            raise PersonaV2InputClosureError(
                                f"{entry_id} dependency SHA at {child_path!r} has no "
                                "known internal or external pin"
                            )
                        referenced_ids.add(known_digest_to_id[digest])
                    elif not _is_allowlisted_non_dependency_sha256_path(
                        body.get("artifact_schema"), child_path
                    ):
                        raise PersonaV2InputClosureError(
                            f"{entry_id} has an unclassified SHA-256 field at "
                            f"{child_path!r}; bind it as a dependency or add an "
                            "exact schema/path non-dependency rule"
                        )
            elif _is_exact_route_review_digest_evidence_path(body, child_path):
                _validate_exact_route_review_digest_evidence(
                    body, child_path, item, entry_id=entry_id
                )
                classified_digest_value = True
            elif _looks_like_sha256(item):
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains an unclassified artifact-looking "
                    f"digest at {child_path!r}"
                )
            if (
                type(item) is bool
                and item is False
                and any(token in lowered for token in _FALSE_STATUS_TOKENS)
                and key != "g0_contract_frozen"
                and key != "authority"
            ):
                false_status_paths.append(child_path)
                if len(false_status_paths) > MAX_PROPAGATED_FALSE_STATUS_COUNT:
                    raise PersonaV2InputClosureError(
                        "propagated false-status count exceeds the closure cap"
                    )
            visit(key, path + ["<key>"])
            if not classified_digest_value:
                visit(item, child_path)

    visit(body, [])
    return referenced_ids, sorted(false_status_paths, key=_path_sort_key)


def _topological_order(pin_by_id, *, root_ids, external_ids):
    all_known = set(pin_by_id) | set(external_ids)
    for entry_id, pin in pin_by_id.items():
        for dependency_id in pin["dependency_ids"]:
            if dependency_id not in all_known:
                raise PersonaV2InputClosureError(
                    f"{entry_id} references missing dependency {dependency_id!r}"
                )
            if dependency_id == entry_id:
                raise PersonaV2InputClosureError(
                    f"{entry_id} contains a self dependency"
                )
    for root_id in root_ids:
        if root_id not in pin_by_id:
            raise PersonaV2InputClosureError(f"missing root entry {root_id!r}")

    state = {}
    order = []
    for root_id in root_ids:
        if root_id in external_ids or state.get(root_id) == 2:
            continue
        stack = [(root_id, False)]
        while stack:
            entry_id, expanded = stack.pop()
            if entry_id in external_ids:
                continue
            status = state.get(entry_id, 0)
            if expanded:
                if status == 1:
                    state[entry_id] = 2
                    order.append(entry_id)
                continue
            if status == 1:
                raise PersonaV2InputClosureError(
                    "input dependency graph contains a cycle"
                )
            if status == 2:
                continue
            state[entry_id] = 1
            stack.append((entry_id, True))
            for dependency_id in reversed(
                pin_by_id[entry_id]["dependency_ids"]
            ):
                if dependency_id in external_ids:
                    continue
                dependency_status = state.get(dependency_id, 0)
                if dependency_status == 1:
                    raise PersonaV2InputClosureError(
                        "input dependency graph contains a cycle"
                    )
                if dependency_status != 2:
                    stack.append((dependency_id, False))
    if set(order) != set(pin_by_id):
        unused = sorted(set(pin_by_id) - set(order))
        raise PersonaV2InputClosureError(
            f"unreferenced input entries are forbidden: {unused!r}"
        )
    return order


def _validate_and_bind_inputs(
    *,
    pins,
    providers,
    root_entry_ids,
    expected_input_class,
    external_entries=None,
):
    normalized_pins = _normalize_pins(
        pins, expected_input_class=expected_input_class
    )
    provider_by_id = _normalize_providers(providers)
    pin_by_id = {pin["entry_id"]: pin for pin in normalized_pins}
    if set(provider_by_id) != set(pin_by_id):
        missing = sorted(set(pin_by_id) - set(provider_by_id))
        extra = sorted(set(provider_by_id) - set(pin_by_id))
        raise PersonaV2InputClosureError(
            f"provider inventory differs from pins; missing={missing!r}, extra={extra!r}"
        )
    roots = _normalize_roots(root_entry_ids, label="root_entry_ids")

    if external_entries is None:
        external_entries = []
    if type(external_entries) is not list:
        raise PersonaV2InputClosureError("external_entries must be a list")
    if len(external_entries) > MAX_ENTRY_COUNT:
        raise PersonaV2InputClosureError(
            "external entry count exceeds the closure cap"
        )
    external_by_id = {}
    seen_external_sha256 = set()
    for row in external_entries:
        if type(row) is not dict or set(row) != {
            "artifact_kind",
            "artifact_schema",
            "artifact_schema_version",
            "binding_aliases",
            "canonical_bytes",
            "entry_id",
            "fixture_id",
            "fixture_schema_version",
            "sha256",
        }:
            raise PersonaV2InputClosureError(
                "external entry must contain the exact compact binding schema"
            )
        entry_id = _require_nonempty_string(
            row["entry_id"], label="external entry_id"
        )
        if entry_id in external_by_id or entry_id in pin_by_id:
            raise PersonaV2InputClosureError(
                f"duplicate local/external entry_id: {entry_id}"
            )
        _require_sha256(row["sha256"], label=f"{entry_id} external sha256")
        aliases = row["binding_aliases"]
        if (
            type(aliases) is not list
            or not aliases
            or len(aliases) > MAX_BINDING_ALIASES_PER_ENTRY
            or any(type(alias) is not str or not alias for alias in aliases)
            or len(set(aliases)) != len(aliases)
            or entry_id not in aliases
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} external binding aliases are invalid"
            )
        reserved_aliases = set(aliases) & _RESERVED_ANCHOR_ENTRY_IDS
        if reserved_aliases:
            raise PersonaV2InputClosureError(
                f"{entry_id} external aliases use reserved anchors: "
                f"{sorted(reserved_aliases)!r}"
            )
        if row["sha256"] in seen_external_sha256:
            raise PersonaV2InputClosureError(
                f"duplicate external body SHA-256: {row['sha256']}"
            )
        seen_external_sha256.add(row["sha256"])
        external_by_id[entry_id] = copy.deepcopy(row)

    all_digests = {
        pin["sha256"]: pin["entry_id"] for pin in normalized_pins
    }
    for entry_id, row in external_by_id.items():
        if row["sha256"] in all_digests:
            raise PersonaV2InputClosureError(
                f"duplicate local/external body SHA-256: {row['sha256']}"
            )
        all_digests[row["sha256"]] = entry_id
    aliases_by_id = {
        pin["entry_id"]: frozenset(pin["binding_aliases"])
        for pin in normalized_pins
    }
    aliases_by_id.update(
        {
            entry_id: frozenset(row["binding_aliases"])
            for entry_id, row in external_by_id.items()
        }
    )
    identity_by_id = {
        pin["entry_id"]: (pin["artifact_schema"], pin["artifact_kind"])
        for pin in normalized_pins
    }
    identity_by_id.update(
        {
            entry_id: (row["artifact_schema"], row["artifact_kind"])
            for entry_id, row in external_by_id.items()
        }
    )
    metadata_by_id = {
        pin["entry_id"]: {
            field: pin[field] for field in _BINDING_OWNER_METADATA_FIELDS
        }
        for pin in normalized_pins
    }
    metadata_by_id.update(
        {
            entry_id: {
                field: row[field]
                for field in _BINDING_OWNER_METADATA_FIELDS
            }
            for entry_id, row in external_by_id.items()
        }
    )
    alias_owners = {}
    for entry_id, aliases in aliases_by_id.items():
        for alias in aliases:
            previous_owner = alias_owners.get(alias)
            if previous_owner is not None and previous_owner != entry_id:
                raise PersonaV2InputClosureError(
                    f"binding alias {alias!r} is ambiguous between "
                    f"{previous_owner!r} and {entry_id!r}"
                )
            alias_owners[alias] = entry_id

    order = _topological_order(
        pin_by_id,
        root_ids=roots,
        external_ids=frozenset(external_by_id),
    )
    entries = []
    fixture_identity = None
    for entry_id in order:
        pin = pin_by_id[entry_id]
        provider = provider_by_id[entry_id]
        body = copy.deepcopy(provider["body"])
        try:
            validation_result = provider["validate"](copy.deepcopy(body))
        except Exception as error:
            raise PersonaV2InputClosureError(
                f"{entry_id} provider validation failed: {error}"
            ) from None
        if validation_result is not True:
            raise PersonaV2InputClosureError(
                f"{entry_id} provider validator must return exact true"
            )
        try:
            provider_raw = provider["canonicalize"](copy.deepcopy(body))
        except Exception as error:
            raise PersonaV2InputClosureError(
                f"{entry_id} provider canonicalization failed: {error}"
            ) from None
        if type(provider_raw) is not bytes:
            raise PersonaV2InputClosureError(
                f"{entry_id} canonicalizer must return exact bytes"
            )
        try:
            independent_raw = artifact_common.canonical_json_bytes(
                body,
                label=f"{entry_id} injected body",
                max_bytes=MAX_UPSTREAM_BODY_BYTES,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            raise PersonaV2InputClosureError(str(error)) from None
        if provider_raw != independent_raw:
            raise PersonaV2InputClosureError(
                f"{entry_id} provider canonical bytes differ from strict JSON"
            )
        if body.get("artifact_schema") != pin["artifact_schema"]:
            raise PersonaV2InputClosureError(f"{entry_id} artifact_schema drifted")
        if body.get("artifact_kind") != pin["artifact_kind"]:
            raise PersonaV2InputClosureError(f"{entry_id} artifact_kind drifted")
        if body.get("artifact_schema_version") != pin["artifact_schema_version"]:
            raise PersonaV2InputClosureError(
                f"{entry_id} artifact_schema_version drifted"
            )
        generic_implementation = (
            body.get("artifact_schema") in _GENERIC_IMPLEMENTATION_SCHEMAS
        )
        if generic_implementation:
            if "fixture_id" in body or "fixture_schema_version" in body:
                raise PersonaV2InputClosureError(
                    f"{entry_id} generic implementation fixture fields drifted"
                )
            fixture_binding_mode = "context-from-enclosing-fixture-input"
        else:
            if body.get("fixture_id") != pin["fixture_id"]:
                raise PersonaV2InputClosureError(f"{entry_id} fixture_id drifted")
            if body.get("fixture_schema_version") != pin["fixture_schema_version"]:
                raise PersonaV2InputClosureError(
                    f"{entry_id} fixture_schema_version drifted"
                )
            fixture_binding_mode = "body-top-level"
        if len(independent_raw) != pin["canonical_bytes"]:
            raise PersonaV2InputClosureError(
                f"{entry_id} canonical byte length differs from its exact pin"
            )
        digest = hashlib.sha256(independent_raw).hexdigest()
        if digest != pin["sha256"]:
            raise PersonaV2InputClosureError(
                f"{entry_id} SHA-256 differs from its exact pin"
            )
        authority_count = _require_negative_authority(body, entry_id=entry_id)
        references, false_status_paths = _scan_body(
            body=body,
            entry_id=entry_id,
            input_class=pin["input_class"],
            known_digest_to_id=all_digests,
            known_metadata_by_id=metadata_by_id,
            known_identity_by_id=identity_by_id,
            aliases_by_id=aliases_by_id,
        )
        expected_references = set(pin["dependency_ids"])
        if references != expected_references:
            raise PersonaV2InputClosureError(
                f"{entry_id} body hash references differ from declared dependencies; "
                f"found={sorted(references)!r}, expected={sorted(expected_references)!r}"
            )
        identity = (pin["fixture_id"], pin["fixture_schema_version"])
        if fixture_identity is None:
            fixture_identity = identity
        elif identity != fixture_identity:
            raise PersonaV2InputClosureError(
                "all injected bodies must share exact fixture identity"
            )
        entries.append(
            {
                **copy.deepcopy(pin),
                "fixture_binding_mode": fixture_binding_mode,
                "negative_authority_object_count": authority_count,
                "propagated_false_status_paths": false_status_paths,
            }
        )
    return {
        "entries": entries,
        "external_entries": [
            external_by_id[entry_id]
            for entry_id in sorted(
                external_by_id, key=lambda value: value.encode("utf-8")
            )
        ],
        "fixture_id": fixture_identity[0],
        "fixture_schema_version": fixture_identity[1],
        "root_entry_ids": roots,
    }


def _negative_authority():
    return {field: False for field in AUTHORITY_FIELDS}


def _completion_claims():
    return {
        "bounded_framed_loader_implemented": False,
        "canonical_g0_input_inventory_complete": False,
        "formal_relevance_compiled": False,
        "injected_body_identity_and_hash_pins_verified": True,
        "injected_dependency_graph_acyclic_and_reachable": True,
        "production_completion_receipts_satisfied": False,
        "semantic_payload_projection_bound": False,
        "source_identity_namespace_authoritative": False,
    }


def _remaining_blockers():
    return [
        "canonical-production-entry-inventory-and-pins-not-frozen",
        "schema-specific-semantic-payload-projections-not-defined-or-bound",
        "positive-independent-route-and-profile-review-receipts-not-bound",
        "full-source-intent-origin-shard-inventory-not-present",
        "overlay-membership-placement-and-eight-axis-inputs-not-complete",
        "fact-membership-history-query-oracle-bundles-not-canonically-complete",
        "source-profile-and-format-feasibility-not-complete",
        "complete-objective-solution-proof-and-final-source-plan-not-present",
        "bounded-framed-and-cumulative-package-loader-not-implemented",
        "compiled-final-raw-hash-section-relevance-intentionally-downstream",
    ]


def _canonical_bytes(value, *, label):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=MAX_INPUT_ROOT_BYTES
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2InputClosureError(str(error)) from None


def _root_value(*, schema, kind, completion_scope, bound):
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": 2,
        "authority": _negative_authority(),
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_INPUT_ROOT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "upstream_body_in_memory_cap": MAX_UPSTREAM_BODY_BYTES,
        },
        "completion_claims": _completion_claims(),
        "completion_scope": completion_scope,
        "fixture_id": bound["fixture_id"],
        "fixture_schema_version": bound["fixture_schema_version"],
        "g0_contract_frozen": False,
        "remaining_blockers": _remaining_blockers(),
    }


def build_corpus_semantic_namespace(*, pins, providers, root_entry_ids):
    """Bind only content-affecting pre-solve bodies, never evidence/query bytes."""

    bound = _validate_and_bind_inputs(
        pins=pins,
        providers=providers,
        root_entry_ids=root_entry_ids,
        expected_input_class="corpus-semantic",
    )
    value = _root_value(
        schema=CORPUS_SEMANTIC_SCHEMA,
        kind=CORPUS_SEMANTIC_KIND,
        completion_scope=(
            "dependency-injected-content-affecting-candidate-namespace-only-no-"
            "evidence-query-solver-source-plan-g0-write-or-history-authority"
        ),
        bound=bound,
    )
    value.update(
        {
            "entry_count": len(bound["entries"]),
            "input_entries": bound["entries"],
            "namespace_contract": {
                "canonical_source_identity_namespace_frozen": False,
                "completion_or_authority_metadata_excluded": False,
                "content_artifact_full_bodies_only": True,
                "evaluation_class_entries_included": False,
                "future_source_id_namespace_eligible": False,
                "query_semantics_absence_proved": False,
                "review_or_evidence_receipt_bytes_included": False,
                "semantic_payload_projection_bound": False,
                "source_identity_derivation_authorized": False,
            },
            "root_entry_ids": bound["root_entry_ids"],
        }
    )
    _canonical_bytes(value, label="persona v2 corpus semantic namespace")
    return value


def corpus_semantic_namespace_bytes(value):
    return _canonical_bytes(value, label="persona v2 corpus semantic namespace")


def corpus_semantic_namespace_sha256(value):
    return hashlib.sha256(corpus_semantic_namespace_bytes(value)).hexdigest()


def validate_corpus_semantic_namespace(
    value, *, pins, providers, root_entry_ids
):
    expected = build_corpus_semantic_namespace(
        pins=pins, providers=providers, root_entry_ids=root_entry_ids
    )
    if corpus_semantic_namespace_bytes(value) != corpus_semantic_namespace_bytes(
        expected
    ):
        raise PersonaV2InputClosureError(
            "corpus semantic namespace differs from exact regeneration"
        )
    return True


def _compact_binding(
    value, *, expected_schema, expected_kind, entry_id, expected_pin=None
):
    if type(value) is not dict:
        raise PersonaV2InputClosureError(f"{entry_id} anchor must be an object")
    if value.get("artifact_schema") != expected_schema:
        raise PersonaV2InputClosureError(f"{entry_id} anchor schema drifted")
    if value.get("artifact_kind") != expected_kind:
        raise PersonaV2InputClosureError(f"{entry_id} anchor kind drifted")
    if value.get("artifact_schema_version") != 2:
        raise PersonaV2InputClosureError(f"{entry_id} anchor version drifted")
    _require_nonempty_string(
        value.get("fixture_id"), label=f"{entry_id} anchor fixture_id"
    )
    if type(value.get("fixture_schema_version")) is not int or value.get(
        "fixture_schema_version"
    ) != 2:
        raise PersonaV2InputClosureError(
            f"{entry_id} anchor fixture schema version drifted"
        )
    raw = _canonical_bytes(value, label=f"{entry_id} anchor")
    _require_negative_authority(value, entry_id=entry_id)
    binding = {
        "artifact_kind": expected_kind,
        "artifact_schema": expected_schema,
        "artifact_schema_version": 2,
        "canonical_bytes": len(raw),
        "entry_id": entry_id,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "sha256": hashlib.sha256(raw).hexdigest(),
    }
    if expected_pin is not None:
        if type(expected_pin) is not dict or set(expected_pin) != ANCHOR_PIN_FIELDS:
            raise PersonaV2InputClosureError(
                f"{entry_id} expected anchor pin has an invalid schema"
            )
        for field in (
            "artifact_kind",
            "artifact_schema",
            "entry_id",
            "fixture_id",
        ):
            _require_nonempty_string(
                expected_pin[field],
                label=f"{entry_id} expected anchor pin {field}",
            )
        if (
            type(expected_pin["artifact_schema_version"]) is not int
            or expected_pin["artifact_schema_version"] != 2
            or type(expected_pin["fixture_schema_version"]) is not int
            or expected_pin["fixture_schema_version"] != 2
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} expected anchor pin versions must be exact 2"
            )
        if (
            type(expected_pin["canonical_bytes"]) is not int
            or expected_pin["canonical_bytes"] <= 0
            or expected_pin["canonical_bytes"] > MAX_INPUT_ROOT_BYTES
        ):
            raise PersonaV2InputClosureError(
                f"{entry_id} expected anchor pin canonical_bytes is invalid"
            )
        _require_sha256(
            expected_pin["sha256"],
            label=f"{entry_id} expected anchor pin sha256",
        )
        if binding != expected_pin:
            raise PersonaV2InputClosureError(
                f"{entry_id} anchor differs from its exact trusted pin"
            )
    return binding


def _semantic_external_entries(semantic_namespace):
    result = []
    for row in semantic_namespace["input_entries"]:
        result.append(
            {
                field: copy.deepcopy(row[field])
                for field in (
                    "artifact_kind",
                    "artifact_schema",
                    "artifact_schema_version",
                    "binding_aliases",
                    "canonical_bytes",
                    "entry_id",
                    "fixture_id",
                    "fixture_schema_version",
                    "sha256",
                )
            }
        )
    return result


def build_corpus_input_closure(
    *,
    semantic_namespace,
    semantic_pins,
    semantic_providers,
    semantic_root_entry_ids,
    evidence_pins,
    evidence_providers,
    evidence_root_entry_ids,
):
    """Bind semantic identity plus evidence without making evidence identity input."""

    validate_corpus_semantic_namespace(
        semantic_namespace,
        pins=semantic_pins,
        providers=semantic_providers,
        root_entry_ids=semantic_root_entry_ids,
    )
    semantic_binding = _compact_binding(
        semantic_namespace,
        expected_schema=CORPUS_SEMANTIC_SCHEMA,
        expected_kind=CORPUS_SEMANTIC_KIND,
        entry_id="corpus-semantic-namespace",
    )
    evidence = _validate_and_bind_inputs(
        pins=evidence_pins,
        providers=evidence_providers,
        root_entry_ids=evidence_root_entry_ids,
        expected_input_class="evidence",
        external_entries=_semantic_external_entries(semantic_namespace),
    )
    if (
        evidence["fixture_id"],
        evidence["fixture_schema_version"],
    ) != (
        semantic_binding["fixture_id"],
        semantic_binding["fixture_schema_version"],
    ):
        raise PersonaV2InputClosureError(
            "semantic namespace and evidence fixture identities differ"
        )
    value = _root_value(
        schema=CORPUS_INPUT_CLOSURE_SCHEMA,
        kind=CORPUS_INPUT_CLOSURE_KIND,
        completion_scope=(
            "dependency-injected-corpus-evidence-closure-candidate-only-no-solver-"
            "source-plan-g0-write-or-history-authority"
        ),
        bound=evidence,
    )
    value.update(
        {
            "corpus_semantic_namespace": semantic_binding,
            "evidence_entries": evidence["entries"],
            "evidence_entry_count": len(evidence["entries"]),
            "evidence_root_entry_ids": evidence["root_entry_ids"],
            "identity_stability_contract": {
                "evaluation_class_bytes_affect_semantic_namespace": False,
                "query_semantics_absence_from_semantic_full_bodies_proved": False,
                "review_receipt_bytes_affect_semantic_namespace": False,
                "route_or_content_body_bytes_affect_semantic_namespace": True,
                "semantic_namespace_is_only_future_source_id_namespace": False,
                "source_id_derivation_currently_authorized": False,
            },
        }
    )
    _canonical_bytes(value, label="persona v2 corpus input closure")
    return value


def corpus_input_closure_bytes(value):
    return _canonical_bytes(value, label="persona v2 corpus input closure")


def corpus_input_closure_sha256(value):
    return hashlib.sha256(corpus_input_closure_bytes(value)).hexdigest()


def validate_corpus_input_closure(value, **builder_inputs):
    expected = build_corpus_input_closure(**builder_inputs)
    if corpus_input_closure_bytes(value) != corpus_input_closure_bytes(expected):
        raise PersonaV2InputClosureError(
            "corpus input closure differs from exact regeneration"
        )
    return True


def build_evaluation_input_closure(
    *,
    corpus_input_closure,
    corpus_input_closure_pin,
    evaluation_pins,
    evaluation_providers,
    evaluation_root_entry_ids,
    semantic_namespace,
):
    """Bind query/oracle inputs downstream of the exact corpus closure."""

    corpus_binding = _compact_binding(
        corpus_input_closure,
        expected_schema=CORPUS_INPUT_CLOSURE_SCHEMA,
        expected_kind=CORPUS_INPUT_CLOSURE_KIND,
        entry_id="corpus-input-closure",
        expected_pin=corpus_input_closure_pin,
    )
    semantic_binding = _compact_binding(
        semantic_namespace,
        expected_schema=CORPUS_SEMANTIC_SCHEMA,
        expected_kind=CORPUS_SEMANTIC_KIND,
        entry_id="corpus-semantic-namespace",
    )
    if corpus_input_closure.get("corpus_semantic_namespace") != semantic_binding:
        raise PersonaV2InputClosureError(
            "corpus closure does not bind the supplied semantic namespace"
        )
    evaluation = _validate_and_bind_inputs(
        pins=evaluation_pins,
        providers=evaluation_providers,
        root_entry_ids=evaluation_root_entry_ids,
        expected_input_class="evaluation",
        external_entries=_semantic_external_entries(semantic_namespace),
    )
    if (
        evaluation["fixture_id"],
        evaluation["fixture_schema_version"],
    ) != (corpus_binding["fixture_id"], corpus_binding["fixture_schema_version"]):
        raise PersonaV2InputClosureError(
            "corpus closure and evaluation input fixture identities differ"
        )
    value = _root_value(
        schema=EVALUATION_INPUT_CLOSURE_SCHEMA,
        kind=EVALUATION_INPUT_CLOSURE_KIND,
        completion_scope=(
            "dependency-injected-query-oracle-closure-candidate-only-no-compiled-"
            "relevance-solver-source-plan-g0-write-or-history-authority"
        ),
        bound=evaluation,
    )
    value.update(
        {
            "corpus_input_closure": corpus_binding,
            "evaluation_entries": evaluation["entries"],
            "evaluation_entry_count": len(evaluation["entries"]),
            "evaluation_root_entry_ids": evaluation["root_entry_ids"],
            "formal_relevance_compiled": False,
            "query_isolation_contract": {
                "corpus_renderer_may_read_evaluation_entries": False,
                "query_or_oracle_bytes_affect_corpus_semantic_namespace": False,
                "query_or_oracle_bytes_affect_corpus_input_closure": False,
                "rendered_query_instances_present": False,
            },
        }
    )
    _canonical_bytes(value, label="persona v2 evaluation input closure")
    return value


def evaluation_input_closure_bytes(value):
    return _canonical_bytes(value, label="persona v2 evaluation input closure")


def evaluation_input_closure_sha256(value):
    return hashlib.sha256(evaluation_input_closure_bytes(value)).hexdigest()


def validate_evaluation_input_closure(value, **builder_inputs):
    expected = build_evaluation_input_closure(**builder_inputs)
    if evaluation_input_closure_bytes(value) != evaluation_input_closure_bytes(
        expected
    ):
        raise PersonaV2InputClosureError(
            "evaluation input closure differs from exact regeneration"
        )
    return True


def build_suite_input_descriptor(
    *,
    corpus_input_closure,
    corpus_input_closure_pin,
    evaluation_input_closure,
    evaluation_input_closure_pin,
):
    """Bind both roots and reject an evaluation root for another corpus root."""

    corpus_binding = _compact_binding(
        corpus_input_closure,
        expected_schema=CORPUS_INPUT_CLOSURE_SCHEMA,
        expected_kind=CORPUS_INPUT_CLOSURE_KIND,
        entry_id="corpus-input-closure",
        expected_pin=corpus_input_closure_pin,
    )
    evaluation_binding = _compact_binding(
        evaluation_input_closure,
        expected_schema=EVALUATION_INPUT_CLOSURE_SCHEMA,
        expected_kind=EVALUATION_INPUT_CLOSURE_KIND,
        entry_id="evaluation-input-closure",
        expected_pin=evaluation_input_closure_pin,
    )
    if evaluation_input_closure.get("corpus_input_closure") != corpus_binding:
        raise PersonaV2InputClosureError(
            "evaluation closure does not bind the supplied corpus closure"
        )
    if (
        corpus_binding["fixture_id"],
        corpus_binding["fixture_schema_version"],
    ) != (
        evaluation_binding["fixture_id"],
        evaluation_binding["fixture_schema_version"],
    ):
        raise PersonaV2InputClosureError("suite input fixture identities differ")
    bound = {
        "fixture_id": corpus_binding["fixture_id"],
        "fixture_schema_version": corpus_binding["fixture_schema_version"],
    }
    value = _root_value(
        schema=SUITE_INPUT_DESCRIPTOR_SCHEMA,
        kind=SUITE_INPUT_DESCRIPTOR_KIND,
        completion_scope=(
            "two-root-input-descriptor-candidate-only-no-solver-source-plan-g0-"
            "write-history-or-suite-execution-authority"
        ),
        bound=bound,
    )
    value.update(
        {
            "corpus_input_closure": corpus_binding,
            "evaluation_input_closure": evaluation_binding,
            "root_binding_count": 2,
        }
    )
    _canonical_bytes(value, label="persona v2 suite input descriptor")
    return value


def suite_input_descriptor_bytes(value):
    return _canonical_bytes(value, label="persona v2 suite input descriptor")


def suite_input_descriptor_sha256(value):
    return hashlib.sha256(suite_input_descriptor_bytes(value)).hexdigest()


def validate_suite_input_descriptor(
    value,
    *,
    corpus_input_closure,
    corpus_input_closure_pin,
    evaluation_input_closure,
    evaluation_input_closure_pin,
):
    expected = build_suite_input_descriptor(
        corpus_input_closure=corpus_input_closure,
        corpus_input_closure_pin=corpus_input_closure_pin,
        evaluation_input_closure=evaluation_input_closure,
        evaluation_input_closure_pin=evaluation_input_closure_pin,
    )
    if suite_input_descriptor_bytes(value) != suite_input_descriptor_bytes(expected):
        raise PersonaV2InputClosureError(
            "suite input descriptor differs from exact regeneration"
        )
    return True


def require_canonical_g0_authority():
    raise PersonaV2InputClosureError(
        "input-root mechanics are only a dependency-injected candidate; canonical "
        "production pins, schema-specific semantic payload projections, positive "
        "independent review receipts, complete source/overlay/fact/history/query/"
        "oracle inputs, bounded framed/package loaders, a complete solved objective, "
        "proof or execution receipt, and final source plan remain absent"
    )
