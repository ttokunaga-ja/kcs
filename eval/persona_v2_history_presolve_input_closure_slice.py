"""Non-authorizing query-independent structural pre-solve history slice.

The compact candidate binds exactly four frozen roots: the pin-only corpus
semantic namespace, its complete derivation inventory, the source-matched
lifecycle suite, and the effective-membership reconciliation suite.  It
closes only the query-independent structural pre-solver demand and the W0-only
membership/witness verification views already proved by those roots.  It is a
small reusable input to a future solution-compiled history closure, not that
authoritative closure itself.

No corpus-input/evaluation/query/review/ledger dependency is imported.  No
whole-corpus post-W0 plan, solved scope/path/quota, planned/final identifier,
write, history mutation, KIO execution, or G0 authority is granted.
"""

from __future__ import annotations

import copy
import hashlib
import hmac

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_corpus_semantic_namespace_v3 as namespace
    from . import persona_v2_lifecycle_effective_membership_reconciliation as effective
    from . import persona_v2_semantic_projection_complete_inventory as complete
    from . import persona_v2_source_matched_lifecycle_inventory as lifecycle
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_corpus_semantic_namespace_v3 as namespace
    import persona_v2_lifecycle_effective_membership_reconciliation as effective
    import persona_v2_semantic_projection_complete_inventory as complete
    import persona_v2_source_matched_lifecycle_inventory as lifecycle


ARTIFACT_SCHEMA = "kio.persona.pc-history-presolve-input-closure-slice/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = (
    "persona-pc-v2-non-authorizing-history-presolve-input-closure-slice"
)

MAX_MANIFEST_BYTES = 128 * 2**10
TARGET_MANIFEST_BYTES = 64 * 2**10
MAX_DIRECT_DEPENDENCY_COUNT = 4
MAX_EXPANDED_NODE_COUNT = 32_768
MAX_DIRECT_DESCRIPTOR_BYTES = 2 * 2**20
MAX_NESTING_DEPTH = 16

# Frozen after corrected full and two-seed cold dependency builds; no authority.
EXPECTED_CANONICAL_BYTES = 8_455
EXPECTED_SHA256 = "64131249be0313bfbccdbc673fa56bd2f54e1a534ac5c52323d6e64741c55f2d"

NAMESPACE_CANONICAL_BYTES = 161_665
NAMESPACE_SHA256 = (
    "70fa743199265efd51ee940dd7032cb72d7c445561989c675060f15c158caafa"
)
COMPLETE_INVENTORY_CANONICAL_BYTES = 697_466
COMPLETE_INVENTORY_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
)
SOURCE_MATCHED_LIFECYCLE_CANONICAL_BYTES = 14_605
SOURCE_MATCHED_LIFECYCLE_SHA256 = (
    "b2ec04ef66476cc71b4ae1fb3275b8d5787eb560b5a7a7e2a3f03d690b77688b"
)
EFFECTIVE_MEMBERSHIP_CANONICAL_BYTES = 69_195
EFFECTIVE_MEMBERSHIP_SHA256 = (
    "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29"
)
DIRECT_DEPENDENCY_CANONICAL_BYTES = 942_931

DIRECT_DEPENDENCY_ORDER = (
    "corpus-semantic-namespace-v3",
    "complete-semantic-projection-inventory-v2",
    "source-matched-lifecycle-suite-v1",
    "lifecycle-effective-membership-suite-v1",
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_history_receipts_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_input_closure",
        "authorizes_evaluation_input_closure",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_input_closure",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_planned_event_identifiers",
        "authorizes_renderer_execution",
        "authorizes_scope_path_quota_solution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
    }
)


class PersonaV2HistoryPresolveInputClosureSliceError(ValueError):
    """Raised when the compact history input slice is not exact."""


def _fail(message):
    raise PersonaV2HistoryPresolveInputClosureSliceError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    """Return the optional producer golden as one atomic validated pair."""

    byte_count_is_set = EXPECTED_CANONICAL_BYTES is not None
    digest_is_set = EXPECTED_SHA256 is not None
    if byte_count_is_set != digest_is_set:
        _fail("history pre-solve slice golden must be entirely unset or set")
    if not byte_count_is_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= TARGET_MANIFEST_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("history pre-solve slice golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_expected_raw(raw):
    if type(raw) is not bytes:
        _fail("history pre-solve slice candidate must be exact bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        _fail("history pre-solve slice exceeds its direct artifact byte cap")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("history pre-solve slice differs from its frozen golden")
    return raw


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return len(left) == len(right) and all(
            key in right and _strict_equal(left[key], right[key]) for key in left
        )
    if type(left) in (list, tuple):
        return len(left) == len(right) and all(
            _strict_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _canonical(value, *, label, maximum=MAX_MANIFEST_BYTES):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _pin(
    *,
    dependency_id,
    dependency_role,
    artifact_kind,
    artifact_schema,
    artifact_schema_version,
    canonical_bytes,
    sha256,
):
    return {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": "canonical-json",
        "canonical_bytes": canonical_bytes,
        "dependency_id": dependency_id,
        "dependency_role": dependency_role,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "sha256": sha256,
    }


def _expected_direct_pins():
    return [
        _pin(
            dependency_id="corpus-semantic-namespace-v3",
            dependency_role="history-semantic-identity-context",
            artifact_kind=(
                "persona-pc-v2-projection-pin-corpus-semantic-namespace"
            ),
            artifact_schema="kio.persona.pc-corpus-semantic-namespace/v3",
            artifact_schema_version=3,
            canonical_bytes=NAMESPACE_CANONICAL_BYTES,
            sha256=NAMESPACE_SHA256,
        ),
        _pin(
            dependency_id="complete-semantic-projection-inventory-v2",
            dependency_role="namespace-validation-evidence-only",
            artifact_kind=(
                "persona-pc-v2-complete-semantic-projection-derivation-inventory"
            ),
            artifact_schema=(
                "kio.persona.pc-semantic-projection-derivation-inventory/v2"
            ),
            artifact_schema_version=2,
            canonical_bytes=COMPLETE_INVENTORY_CANONICAL_BYTES,
            sha256=COMPLETE_INVENTORY_SHA256,
        ),
        _pin(
            dependency_id="source-matched-lifecycle-suite-v1",
            dependency_role="query-independent-presolve-lifecycle-demand",
            artifact_kind="persona-pc-v2-source-matched-lifecycle-suite",
            artifact_schema="kio.persona.pc-source-matched-lifecycle-suite/v1",
            artifact_schema_version=1,
            canonical_bytes=SOURCE_MATCHED_LIFECYCLE_CANONICAL_BYTES,
            sha256=SOURCE_MATCHED_LIFECYCLE_SHA256,
        ),
        _pin(
            dependency_id="lifecycle-effective-membership-suite-v1",
            dependency_role="effective-w0-membership-and-witness-isolation",
            artifact_kind=(
                "persona-pc-v2-lifecycle-effective-membership-reconciliation"
            ),
            artifact_schema=(
                "kio.persona.pc-lifecycle-effective-membership-reconciliation/v1"
            ),
            artifact_schema_version=1,
            canonical_bytes=EFFECTIVE_MEMBERSHIP_CANONICAL_BYTES,
            sha256=EFFECTIVE_MEMBERSHIP_SHA256,
        ),
    ]


def _history_coverage():
    return {
        "companion_source_ref_count": 200,
        "effective_w0_base_inheritance_count": 200_800,
        "effective_w0_companion_mirror_count": 200,
        "effective_w0_graph_normal_count": 1_700,
        "effective_w0_graph_normal_plus_witness_count": 300,
        "event_created_source_intent_count": 3_630,
        "event_created_witness_carrying_count": 300,
        "event_created_witness_empty_count": 3_330,
        "inverted_consumer_reference_count": 600,
        "inverted_witness_count": 300,
        "lifecycle_source_ref_count": 2_300,
        "persona_count": 20,
        "pre_solve_lifecycle_event_intent_count": 7_630,
        "present_fact_reference_count": 1_033_680,
        "primary_source_ref_count": 2_100,
        "purge_witness_count": 300,
        "source_matched_format_witness_count": 93,
        "w0_purge_witness_consumer_count": 300,
        "w0_source_intent_count": 203_000,
        "witness_consumer_count_per_witness": 2,
    }


def _compact_owner_summary():
    return {
        "companion_mirror_row_count": 200,
        "effective_shard_receipt_count": 73,
        "event_and_inverted_views_persisted": False,
        "membership_compact_row_count": 2_573,
        "primary_override_row_count": 2_000,
        "typed_purge_witness_row_count": 300,
    }


def _semantic_context():
    return {
        "complete_inventory_evidence_bound": True,
        "cumulative_external_projection_bytes": 155_741_381,
        "external_projection_bodies_embedded": False,
        "namespace_entry_count": 253,
        "namespace_issued": False,
        "projection_class_count": 12,
    }


def _frozen_dependency_snapshot():
    """Return detached exact metadata for focused trust-boundary tests."""

    return {
        "compact_owner_summary": copy.deepcopy(_compact_owner_summary()),
        "dependency_pins": copy.deepcopy(_expected_direct_pins()),
        "history_coverage": copy.deepcopy(_history_coverage()),
        "semantic_context": copy.deepcopy(_semantic_context()),
    }


def _require_dependency_constant_alignment():
    actual = (
        (
            namespace.NAMESPACE_KIND,
            namespace.NAMESPACE_SCHEMA,
            namespace.ARTIFACT_SCHEMA_VERSION,
            namespace.EXPECTED_NAMESPACE_CANONICAL_BYTES,
            namespace.EXPECTED_NAMESPACE_SHA256,
        ),
        (
            complete.SUITE_KIND,
            complete.SUITE_SCHEMA,
            complete.ARTIFACT_SCHEMA_VERSION,
            complete.EXPECTED_SUITE_CANONICAL_BYTES,
            complete.EXPECTED_SUITE_SHA256,
        ),
        (
            lifecycle.SUITE_KIND,
            lifecycle.SUITE_SCHEMA,
            lifecycle.ARTIFACT_SCHEMA_VERSION,
            lifecycle.EXPECTED_SUITE_CANONICAL_BYTES,
            lifecycle.EXPECTED_SUITE_SHA256,
        ),
        (
            effective.SUITE_KIND,
            effective.SUITE_SCHEMA,
            effective.ARTIFACT_SCHEMA_VERSION,
            effective.EXPECTED_SUITE_CANONICAL_BYTES,
            effective.EXPECTED_SUITE_SHA256,
        ),
    )
    expected = tuple(
        (
            pin["artifact_kind"],
            pin["artifact_schema"],
            pin["artifact_schema_version"],
            pin["canonical_bytes"],
            pin["sha256"],
        )
        for pin in _expected_direct_pins()
    )
    if not _strict_equal(actual, expected):
        _fail("current direct-dependency constants drifted")
    pinned_bytes = sum(pin[3] for pin in expected)
    if pinned_bytes != DIRECT_DEPENDENCY_CANONICAL_BYTES:
        _fail("direct-dependency canonical byte total drifted")
    if pinned_bytes > MAX_DIRECT_DESCRIPTOR_BYTES:
        _fail("direct dependency descriptors exceed their cumulative byte cap")


def _pin_from_body(value, raw, expected):
    if type(value) is not dict or type(raw) is not bytes:
        _fail("live dependency did not expose an object and canonical bytes")
    pin = _pin(
        dependency_id=expected["dependency_id"],
        dependency_role=expected["dependency_role"],
        artifact_kind=value.get("artifact_kind"),
        artifact_schema=value.get("artifact_schema"),
        artifact_schema_version=value.get("artifact_schema_version"),
        canonical_bytes=len(raw),
        sha256=_sha256(raw),
    )
    if not _strict_equal(pin, expected):
        _fail("live history dependency differs from its exact frozen pin")
    if (
        value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("live history dependency fixture identity drifted")
    authority = value.get("authority")
    if type(authority) is dict and any(flag is not False for flag in authority.values()):
        _fail("live history dependency escalated authority")
    return pin


def _coverage_from_dependencies(lifecycle_value, effective_value, namespace_value):
    lifecycle_summary = lifecycle_value.get("summary")
    effective_summary = effective_value.get("summary")
    lifecycle_claims = lifecycle_value.get("completion_claims")
    effective_claims = effective_value.get("completion_claims")
    if not all(type(row) is dict for row in (
        lifecycle_summary,
        effective_summary,
        lifecycle_claims,
        effective_claims,
    )):
        _fail("live history dependency summaries are missing")
    mode_counts = effective_summary.get("effective_w0_mode_counts")
    coverage = {
        "companion_source_ref_count": lifecycle_summary.get(
            "companion_source_match_count"
        ),
        "effective_w0_base_inheritance_count": (mode_counts or {}).get(
            "base-inheritance"
        ),
        "effective_w0_companion_mirror_count": (mode_counts or {}).get(
            "companion-mirror"
        ),
        "effective_w0_graph_normal_count": (mode_counts or {}).get(
            "graph-normal"
        ),
        "effective_w0_graph_normal_plus_witness_count": (mode_counts or {}).get(
            "graph-normal-plus-witness"
        ),
        "event_created_source_intent_count": effective_summary.get(
            "event_created_lineage_count"
        ),
        "event_created_witness_carrying_count": 300,
        "event_created_witness_empty_count": 3_330,
        "inverted_consumer_reference_count": effective_summary.get(
            "inverted_consumer_reference_count"
        ),
        "inverted_witness_count": effective_summary.get(
            "inverted_witness_count"
        ),
        "lifecycle_source_ref_count": lifecycle_summary.get(
            "lifecycle_source_ref_count"
        ),
        "persona_count": lifecycle_summary.get("persona_count"),
        "pre_solve_lifecycle_event_intent_count": lifecycle_summary.get(
            "event_intent_count"
        ),
        "present_fact_reference_count": effective_summary.get(
            "present_fact_reference_count"
        ),
        "primary_source_ref_count": lifecycle_summary.get(
            "primary_source_match_count"
        ),
        "purge_witness_count": effective_summary.get(
            "compact_typed_witness_count"
        ),
        "source_matched_format_witness_count": lifecycle_summary.get(
            "format_witness_count"
        ),
        "w0_purge_witness_consumer_count": 300,
        "w0_source_intent_count": effective_summary.get("source_count"),
        "witness_consumer_count_per_witness": 2,
    }
    compact = {
        "companion_mirror_row_count": effective_summary.get(
            "compact_companion_mirror_count"
        ),
        "effective_shard_receipt_count": effective_summary.get(
            "compact_shard_receipt_count"
        ),
        "event_and_inverted_views_persisted": effective_claims.get(
            "expanded_and_inverted_views_persisted"
        ),
        "membership_compact_row_count": effective_summary.get(
            "compact_row_count"
        ),
        "primary_override_row_count": effective_summary.get(
            "compact_primary_override_count"
        ),
        "typed_purge_witness_row_count": effective_summary.get(
            "compact_typed_witness_count"
        ),
    }
    semantic = {
        "complete_inventory_evidence_bound": True,
        "cumulative_external_projection_bytes": namespace_value.get(
            "summary", {}
        ).get("cumulative_external_projection_bytes"),
        "external_projection_bodies_embedded": False,
        "namespace_entry_count": namespace_value.get("summary", {}).get(
            "namespace_entry_count"
        ),
        "namespace_issued": namespace_value.get("completion_claims", {}).get(
            "corpus_semantic_namespace_issued"
        ),
        "projection_class_count": namespace_value.get("summary", {}).get(
            "projection_class_count"
        ),
    }
    required_claims = (
        lifecycle_claims.get("all_2300_lifecycle_source_refs_bound") is True,
        lifecycle_claims.get("all_7630_event_intents_receipted") is True,
        lifecycle_claims.get("compiled_history_plan_available") is False,
        lifecycle_claims.get("solved_scope_path_quota_or_final_ids_present")
        is False,
        effective_claims.get("all_203000_effective_w0_memberships_reconciled")
        is True,
        effective_claims.get("all_3630_event_created_witness_lineages_receipted")
        is True,
        effective_claims.get("all_300_purge_witnesses_have_exactly_two_consumers")
        is True,
        effective_claims.get("post_w0_complete_membership_compiled") is False,
    )
    if not all(required_claims):
        _fail("live history dependency completion boundary drifted")
    snapshot = {
        "compact_owner_summary": compact,
        "history_coverage": coverage,
        "semantic_context": semantic,
    }
    expected = _frozen_dependency_snapshot()
    for key in snapshot:
        if not _strict_equal(snapshot[key], expected[key]):
            _fail(f"live history {key} differs from its exact compact contract")
    return snapshot


def _live_dependency_snapshot(*, full=False):
    """Return frozen pins, or replay all four live roots only on full opt-in."""

    _expected_golden()
    if full:
        _require_validator_golden_parity()
    _require_dependency_constant_alignment()
    if not full:
        return _frozen_dependency_snapshot()

    inventory = complete.build_semantic_projection_complete_inventory()
    inventory_raw = complete.canonical_json_bytes(inventory)
    namespace_value = namespace.build_corpus_semantic_namespace_v3(inventory)
    namespace_raw = namespace.corpus_semantic_namespace_v3_candidate_bytes(
        namespace_value
    )
    lifecycle_value = lifecycle.build_source_matched_lifecycle_suite_descriptor()
    lifecycle_raw = lifecycle.canonical_json_bytes(lifecycle_value)
    effective_value = effective.build_lifecycle_effective_membership_suite_descriptor()
    effective_raw = effective.canonical_json_bytes(effective_value)
    if sum(
        len(raw)
        for raw in (namespace_raw, inventory_raw, lifecycle_raw, effective_raw)
    ) > MAX_DIRECT_DESCRIPTOR_BYTES:
        _fail("live direct dependency descriptors exceed their cumulative byte cap")

    expected_pins = _expected_direct_pins()
    pins = [
        _pin_from_body(namespace_value, namespace_raw, expected_pins[0]),
        _pin_from_body(inventory, inventory_raw, expected_pins[1]),
        _pin_from_body(lifecycle_value, lifecycle_raw, expected_pins[2]),
        _pin_from_body(effective_value, effective_raw, expected_pins[3]),
    ]
    derived = _coverage_from_dependencies(
        lifecycle_value, effective_value, namespace_value
    )
    snapshot = {"dependency_pins": pins, **derived}
    try:
        from . import persona_v2_corpus_semantic_namespace_v3_validator as namespace_validator
    except ImportError:  # pragma: no cover
        import persona_v2_corpus_semantic_namespace_v3_validator as namespace_validator
    if namespace_validator.validate_corpus_semantic_namespace_v3(
        namespace_value,
        complete_inventory=inventory,
        projection_body_provider=complete.projection_body_provider,
    ) is not True:
        _fail("full namespace dependency validation was not exact true")
    # Effective-membership construction and independent validation each own a
    # distinct lifecycle trust pass.  A third direct lifecycle validation here
    # would replay the same suite without adding an independent boundary.
    if effective.validate_lifecycle_effective_membership_suite_descriptor(
        effective_value
    ) is not True:
        _fail("full effective-membership validation was not exact true")
    opening_raws = (namespace_raw, inventory_raw, lifecycle_raw, effective_raw)
    closing_raws = (
        namespace.corpus_semantic_namespace_v3_candidate_bytes(namespace_value),
        complete.canonical_json_bytes(inventory),
        lifecycle.canonical_json_bytes(lifecycle_value),
        effective.canonical_json_bytes(effective_value),
    )
    if any(
        not hmac.compare_digest(opening, closing)
        for opening, closing in zip(opening_raws, closing_raws, strict=True)
    ):
        _fail("a direct history dependency changed during full validation")
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("live history dependency snapshot differs from frozen metadata")
    return snapshot


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _completion_claims():
    return {
        "all_203000_effective_w0_memberships_bound": True,
        "all_2300_lifecycle_source_refs_bound": True,
        "all_300_witnesses_exact_two_consumers_bound": True,
        "all_3630_event_created_witness_lineages_bound": True,
        "all_4_direct_dependency_pins_bound": True,
        "all_7630_presolve_lifecycle_event_intents_bound": True,
        "compiled_history_plan_available": False,
        "authoritative_history_input_closure_ready": False,
        "final_identifiers_bound": False,
        "g0_approved": False,
        "history_presolve_local_slice_exact": True,
        "history_runtime_receipts_bound": False,
        "physical_files_written": False,
        "planned_event_identifiers_bound": False,
        "post_w0_complete_membership_compiled": False,
        "post_w0_history_state_ready": False,
        "production_history_input_closure_complete": False,
        "query_bound_history_state_ready": False,
        "scope_path_quota_solution_bound": False,
        "solver_solution_and_proof_bound": False,
        "whole_corpus_post_w0_event_plan_complete": False,
        "w0_only_structural_presolve_slice_bound": True,
    }


def _canonical_limits():
    return {
        "direct_dependency_bodies_embedded": False,
        "framed_byte_cap_before_body_required": True,
        "max_direct_dependency_count": MAX_DIRECT_DEPENDENCY_COUNT,
        "max_direct_descriptor_bytes": MAX_DIRECT_DESCRIPTOR_BYTES,
        "max_expanded_node_count": MAX_EXPANDED_NODE_COUNT,
        "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "max_nesting_depth": MAX_NESTING_DEPTH,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "null_float_or_negative_integer_allowed": False,
        "precanonical_expanded_structure_preflight_required": True,
        "self_hash_embedded": False,
        "target_manifest_bytes": TARGET_MANIFEST_BYTES,
        "unicode_normalization": "NFC",
    }


def _unresolved_solution_compilation():
    return {
        "actual_chunk_attestation_count": 0,
        "bucket_assignment_count": 0,
        "cohort_assignment_count": 0,
        "compiled_history_event_count": 0,
        "final_materialization_id_count": 0,
        "final_source_id_count": 0,
        "filesystem_write_receipt_count": 0,
        "g0_approval_receipt_count": 0,
        "history_mutation_receipt_count": 0,
        "kio_execution_receipt_count": 0,
        "path_assignment_count": 0,
        "planned_event_id_count": 0,
        "planned_materialization_id_count": 0,
        "planned_source_id_count": 0,
        "post_w0_complete_membership_row_count": 0,
        "presolve_lineage_is_complete_post_w0_membership": False,
        "quota_assignment_count": 0,
        "rendered_file_count": 0,
        "scope_assignment_count": 0,
        "solver_proof_count": 0,
        "solver_solution_count": 0,
        "whole_corpus_post_w0_event_intent_count": 0,
    }


def _expected_value(snapshot):
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": _canonical_limits(),
        "compact_owner_summary": copy.deepcopy(snapshot["compact_owner_summary"]),
        "completion_claims": _completion_claims(),
        "completion_scope": (
            "pinned-query-independent-structural-presolve-history-demand-w0-only-"
            "effective-membership-and-"
            "purge-witness-isolation-only-no-whole-corpus-post-w0-plan-solution-"
            "write-history-execution-or-g0"
        ),
        "dependency_direction_contract": {
            "complete_inventory_is_validation_evidence_not_history_identity": True,
            "corpus_namespace_may_import_this_history_slice": False,
            "future_solution_compiled_history_closure_may_bind_this_slice": True,
            "history_slice_may_back_bind_corpus_or_evaluation_inputs": False,
            "slice_is_authoritative_history_input_closure": False,
            "slice_is_query_independent_structural_w0_only": True,
            "source_matched_events_remain_presolve_intents_not_executed_events": True,
            "witness_lineage_does_not_claim_complete_post_w0_membership": True,
        },
        "dependency_exclusion_contract": {
            "blocker_ledger_bound": False,
            "corpus_input_closure_bound": False,
            "evaluation_input_closure_bound": False,
            "query_or_oracle_bound": False,
            "review_request_or_receipt_bound": False,
        },
        "dependency_order": list(DIRECT_DEPENDENCY_ORDER),
        "dependency_pins": copy.deepcopy(snapshot["dependency_pins"]),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "history_coverage": copy.deepcopy(snapshot["history_coverage"]),
        "hypothesis_status": (
            "authored-pinned-query-independent-structural-w0-only-presolve-"
            "history-input-slice-not-authoritative-not-observed-"
            "filesystem-history-or-kio-execution"
        ),
        "orders": {
            "direct_dependencies": "declared-dependency-order",
            "history_events": "dependency-owned-event-sequence-ordinal",
            "personas": "persona-id-ascii",
        },
        "remaining_blockers": [
            "whole-corpus-post-w0-event-and-membership-plan-not-built",
            "scope-bucket-cohort-path-quota-solution-and-proof-not-built",
            "planned-and-final-source-materialization-event-identifiers-not-built",
            "solution-compiled-history-plan-not-built",
            "render-write-index-history-mutation-and-kio-receipts-not-built",
            "production-input-closures-and-positive-approval-not-bound",
            "formal-g0-contract-not-frozen",
        ],
        "semantic_context": copy.deepcopy(snapshot["semantic_context"]),
        "summary": {
            "dependency_pin_count": MAX_DIRECT_DEPENDENCY_COUNT,
            "direct_dependency_canonical_bytes": DIRECT_DEPENDENCY_CANONICAL_BYTES,
            "event_created_source_intent_count": 3_630,
            "inverted_consumer_reference_count": 600,
            "lifecycle_source_ref_count": 2_300,
            "persona_count": 20,
            "pre_solve_lifecycle_event_intent_count": 7_630,
            "purge_witness_count": 300,
            "w0_source_intent_count": 203_000,
        },
        "unresolved_solution_compilation": _unresolved_solution_compilation(),
    }


def _require_snapshot(snapshot):
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("history dependency snapshot differs from exact frozen metadata")


def _build_from_snapshot(snapshot):
    _expected_golden()
    _require_dependency_constant_alignment()
    _require_snapshot(snapshot)
    value = _expected_value(snapshot)
    raw = _canonical(value, label="history pre-solve input closure slice")
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("history pre-solve closure slice exceeds its target byte budget")
    _require_expected_raw(raw)
    return value


def build_history_presolve_input_closure_slice():
    """Build a detached structural W0-only slice from four accepted pins."""

    _require_validator_golden_parity()
    _require_dependency_constant_alignment()
    return copy.deepcopy(_build_from_snapshot(_live_dependency_snapshot()))


def _independent_validator():
    try:
        from . import persona_v2_history_presolve_input_closure_slice_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_history_presolve_input_closure_slice_validator as independent
        except ImportError:
            independent = None
    return independent


def _require_validator_golden_parity(independent=None):
    """Authenticate both optional goldens before any live provider is opened."""

    producer_expected = _expected_golden()
    if independent is None:
        independent = _independent_validator()
    validator_expected = None if independent is None else getattr(
        independent, "_expected_golden", None
    )
    if not callable(validator_expected):
        _fail("independent history pre-solve golden guard is unavailable")
    try:
        validator_expected = validator_expected()
    except Exception:
        _fail("independent history pre-solve golden is invalid")
    if not _strict_equal(producer_expected, validator_expected):
        _fail("producer and validator history pre-solve goldens differ")
    return producer_expected, independent


def canonical_json_bytes(value):
    _expected, independent = _require_validator_golden_parity()
    snapshot = None if independent is None else getattr(
        independent, "_snapshot_candidate", None
    )
    if not callable(snapshot):
        _fail("independent history pre-solve closure snapshot is unavailable")
    try:
        _detached, raw = snapshot(value)
    except Exception:
        raise PersonaV2HistoryPresolveInputClosureSliceError(
            "history pre-solve closure slice failed strict structural preflight"
        ) from None
    return _require_expected_raw(raw)


def validate_history_presolve_input_closure_slice(value):
    _expected, independent = _require_validator_golden_parity()
    try:
        result = independent.validate_history_presolve_input_closure_slice(value)
    except independent.PersonaV2HistoryPresolveInputClosureSliceValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent history pre-solve closure validator was not exact true")
    return True


def history_presolve_input_closure_slice_sha256(value=None):
    _expected, independent = _require_validator_golden_parity()
    if value is None:
        value = build_history_presolve_input_closure_slice()
    try:
        _opening_value, opening = independent._snapshot_candidate(value)
    except independent.PersonaV2HistoryPresolveInputClosureSliceValidationError as error:
        _fail(str(error))
    validate_history_presolve_input_closure_slice(value)
    try:
        _closing_value, closing = independent._snapshot_candidate(value)
    except independent.PersonaV2HistoryPresolveInputClosureSliceValidationError as error:
        _fail(str(error))
    if not hmac.compare_digest(opening, closing):
        _fail("history pre-solve closure changed during validation-to-hash")
    return _sha256(opening)


def require_full_history_presolve_input_closure_slice():
    """Build and independently revalidate every direct dependency root."""

    producer_expected, independent = _require_validator_golden_parity()
    value = _build_from_snapshot(_frozen_dependency_snapshot())
    try:
        result = independent.validate_history_presolve_input_closure_slice_full(
            value,
            producer_expected_golden=producer_expected,
        )
    except independent.PersonaV2HistoryPresolveInputClosureSliceValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("full independent history pre-solve closure validation was not exact true")
    return copy.deepcopy(value)


def require_authoritative_history_presolve_input_closure_slice():
    """Fail closed: a structural W0-only pre-solve slice is not authoritative."""

    raise PersonaV2HistoryPresolveInputClosureSliceError(
        "the query-independent structural pre-solve slice binds only W0 views; "
        "it has no compiled post-W0 history plan, final identifiers, runtime "
        "receipts, production input closure, or positive G0 authority"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "DIRECT_DEPENDENCY_ORDER",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_MANIFEST_BYTES",
    "PersonaV2HistoryPresolveInputClosureSliceError",
    "build_history_presolve_input_closure_slice",
    "canonical_json_bytes",
    "history_presolve_input_closure_slice_sha256",
    "require_authoritative_history_presolve_input_closure_slice",
    "require_full_history_presolve_input_closure_slice",
    "validate_history_presolve_input_closure_slice",
]
