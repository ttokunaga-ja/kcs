"""Producer-independent validator for semantic-resolution feasibility v1.

This module intentionally does not import the producer.  It duplicates the
schema, fixed pins, profile-capacity matching, and all-persona join against the
upstream generated owners.  Public validation is heavy; focused tests use the
explicit snapshot hook and do not run full/cold acceptance gates.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_lifecycle_effective_membership_reconciliation as effective
    from . import persona_v2_query_history_target_resolution as target_resolution
    from . import persona_v2_query_intent as query_intent
    from . import persona_v2_semantic_oracle as semantic_oracle
    from . import persona_v2_source_matched_lifecycle_inventory as lifecycle
    from . import persona_v2_source_semantic_membership_package as source_semantic
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_lifecycle_effective_membership_reconciliation as effective
    import persona_v2_query_history_target_resolution as target_resolution
    import persona_v2_query_intent as query_intent
    import persona_v2_semantic_oracle as semantic_oracle
    import persona_v2_source_matched_lifecycle_inventory as lifecycle
    import persona_v2_source_semantic_membership_package as source_semantic


ARTIFACT_SCHEMA = (
    "kio.persona.pc-query-history-semantic-resolution-feasibility-audit/v1"
)
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = (
    "persona-pc-v2-query-history-semantic-resolution-feasibility-audit"
)
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2
MAX_ARTIFACT_BYTES = 2 * 2**20
TARGET_ARTIFACT_BYTES = 512 * 2**10
EXPECTED_CANONICAL_BYTES = 40_947
EXPECTED_SHA256 = (
    "890ce6510d9baa4b5faf533cb927bd296f12e289247bb63f88ee2303565af136"
)

DEPENDENCY_ORDER = (
    "query-history-target-resolution-v1",
    "source-semantic-membership-suite-v2",
    "source-matched-lifecycle-suite-v1",
    "lifecycle-effective-membership-reconciliation-v1",
    "corpus-semantic-namespace-v3",
    "complete-semantic-projection-inventory-v2",
)
DEPENDENCY_PINS = {
    "query-history-target-resolution-v1": {
        "artifact_schema": "kio.persona.pc-query-history-target-resolution/v1",
        "artifact_schema_version": 1,
        "canonical_bytes": 4_478_576,
        "sha256": "8beed1ca21ebe80e029bcd003795306086514adcd852b98a9eed334fcd73f4ff",
    },
    "source-semantic-membership-suite-v2": {
        "artifact_schema": "kio.persona.pc-source-semantic-membership-suite/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 49_837,
        "sha256": "6027147bff72129aa308daa79c10581f6eceec9b04eb4667dbe72c0194ac6072",
    },
    "source-matched-lifecycle-suite-v1": {
        "artifact_schema": "kio.persona.pc-source-matched-lifecycle-suite/v1",
        "artifact_schema_version": 1,
        "canonical_bytes": 14_605,
        "sha256": "b2ec04ef66476cc71b4ae1fb3275b8d5787eb560b5a7a7e2a3f03d690b77688b",
    },
    "lifecycle-effective-membership-reconciliation-v1": {
        "artifact_schema": "kio.persona.pc-lifecycle-effective-membership-reconciliation/v1",
        "artifact_schema_version": 1,
        "canonical_bytes": 69_195,
        "sha256": "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29",
    },
    "corpus-semantic-namespace-v3": {
        "artifact_schema": "kio.persona.pc-corpus-semantic-namespace/v3",
        "artifact_schema_version": 3,
        "canonical_bytes": 161_665,
        "sha256": "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509",
    },
    "complete-semantic-projection-inventory-v2": {
        "artifact_schema": "kio.persona.pc-semantic-projection-derivation-inventory/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 697_466,
        "sha256": "6826fb14293e7147159fae1849f93533c35ae76f1beecbd093d190cd6ddd3e69",
    },
}
DEPENDENCY_ROLES = {
    "query-history-target-resolution-v1": "baseline-query-to-lifecycle-class-bijection",
    "source-semantic-membership-suite-v2": "accepted-baseline-context-pin-not-live-body-authentication",
    "source-matched-lifecycle-suite-v1": "accepted-baseline-context-pin-not-live-body-authentication",
    "lifecycle-effective-membership-reconciliation-v1": "accepted-baseline-context-pin-not-live-body-authentication",
    "corpus-semantic-namespace-v3": "corpus-projection-pin-context-only",
    "complete-semantic-projection-inventory-v2": "transitive-owner-chain-context-only",
}
LIVE_JOIN_ORDER = (
    "query-oracle-resolution-live-join",
    "source-semantic-live-join",
    "source-matched-lifecycle-live-join",
    "effective-membership-live-join",
)
LIVE_JOIN_ROLES = {
    "query-oracle-resolution-live-join": "exact-query-oracle-resolution-rows-used-by-audit",
    "source-semantic-live-join": "exact-topics-fact-profiles-and-profile-counts-used-by-audit",
    "source-matched-lifecycle-live-join": "exact-primary-companion-and-event-rows-used-by-audit",
    "effective-membership-live-join": "exact-effective-primary-and-purge-witness-rows-used-by-audit",
}

AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_compiled_relevance",
        "authorizes_corpus_namespace",
        "authorizes_evaluation_publication",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_execution",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_execution",
        "authorizes_query_history_target_resolution_v2",
        "authorizes_query_rendering",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "checkpoint_effective_membership_compiled",
        "concrete_distractor_mapping_available",
        "four_domain_disjointness_proved",
        "revision_join_policy_available",
        "semantic_resolution_complete",
    }
)
DISTRACTOR_CLASSES = (
    "no-w0-profile-candidate",
    "singleton-only",
    "opposite-conflict",
    "graph-normal",
)
EXPECTED_DISTRACTOR_CLASS_COUNTS_PER_PERSONA = {
    "no-w0-profile-candidate": 36,
    "singleton-only": 186,
    "opposite-conflict": 30,
    "graph-normal": 18,
}
REMAINING_BLOCKERS = (
    "current-class-only-target-matching-does-not-enforce-source-topic-language-or-fact-equality",
    "revision-chain-vocabularies-have-no-owner-defined-exact-join-policy",
    "checkpoint-selector-effective-fact-membership-is-not-compiled",
    "720-distractor-references-have-no-w0-fact-profile-candidate",
    "3720-singleton-only-distractor-references-have-only-100-unused-suite-source-slots",
    "5400-distinct-distractor-source-mappings-exceed-the-1060-source-suite-upper-bound",
    "topic-and-language-filtered-distractor-capacity-is-not-proved",
    "four-domain-target-primary-companion-distractor-disjointness-is-not-proved",
    "full-direct-owner-suite-bodies-are-context-pins-not-reauthenticated-by-this-fast-audit",
    "query-history-target-resolution-v2-not-issued",
)
REMEDIATION_OPTIONS = (
    {
        "option_id": "semantic-constrained-rematch",
        "required_result": (
            "rematch all query targets and concrete distractors with exact "
            "topic-language-fact-checkpoint-revision constraints"
        ),
        "status": "required-not-implemented",
    },
    {
        "option_id": "narrow-source-membership",
        "required_result": (
            "reserve query-independent source memberships that are sufficient "
            "for 2100 targets and 5400 distinct distractors"
        ),
        "status": "required-not-implemented",
    },
    {
        "option_id": "post-w1-effective-membership",
        "required_result": (
            "publish an owner-defined post-W1 and checkpoint-effective fact and "
            "revision membership join before W2 event compilation"
        ),
        "status": "required-not-implemented",
    },
)

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "dependency_bindings",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "live_join_bindings",
        "methodology",
        "orders",
        "persona_feasibility_rows",
        "remaining_blockers",
        "remediation_options",
        "resolution_publication_contract",
        "summary",
    }
)
PERSONA_ROW_FIELDS = frozenset(
    {"baseline_target_feasibility", "distractor_feasibility", "persona_id"}
)
BASELINE_FIELDS = frozenset(
    {
        "all_condition_exact_resolution_count",
        "all_condition_exact_resolution_status",
        "baseline_aligned_count",
        "baseline_mismatch_count",
        "checkpoint_selector_effective_membership_compiled_count",
        "checkpoint_selector_effective_membership_unknown_count",
        "contributor_target_count",
        "incidental_target_count",
        "negative_target_count",
        "negative_vacuous_w0_fact_subset_count",
        "positive_target_count",
        "predicate_true_counts",
        "purged_typed_witness_semantics_authored_count",
        "revision_exact_join_proved_count",
        "revision_join_policy_available",
        "revision_join_unknown_count",
        "revision_target_nonempty_count",
        "total_resolution_target_count",
    }
)
PREDICATE_FIELDS = frozenset(
    {
        "authored_event_profile_subset",
        "baseline_topic_language_fact_and_event",
        "capability_class_equal",
        "language_equal",
        "topic_project_equal",
        "w0_expected_fact_subset",
    }
)
DISTRACTOR_FIELDS = frozenset(
    {
        "abstract_distractor_reference_count",
        "classification_counts",
        "concrete_mapping_count",
        "four_domain_disjointness_candidate_complete",
        "maximum_distinct_source_candidate_count_before_language_filter",
        "maximum_mapping_shortfall_count",
        "post_target_singleton_source_capacity",
        "source_language_filtered_capacity_proved",
        "topic_language_fact_revision_complete_mapping_proved",
    }
)

PROHIBITED_KEYS = frozenset(
    {
        "compiled_relevance",
        "final_id",
        "final_source_id",
        "mapped_distractor_source_intents",
        "query_history_target_resolution_v2",
        "solution_sha256",
    }
)


class PersonaV2SemanticResolutionFeasibilityValidationError(ValueError):
    """Raised when an audit candidate differs from independent reconstruction."""


def _fail(message):
    raise PersonaV2SemanticResolutionFeasibilityValidationError(message)


def _ascii(value):
    return value.encode("ascii", "strict")


def _expected_golden():
    """Return the validator-owned optional golden after strict configuration."""

    byte_count_is_set = EXPECTED_CANONICAL_BYTES is not None
    digest_is_set = EXPECTED_SHA256 is not None
    if byte_count_is_set != digest_is_set:
        _fail("feasibility-audit golden must be either entirely unset or entirely set")
    if not byte_count_is_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= TARGET_ARTIFACT_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("feasibility-audit golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_expected_raw(raw):
    """Fail closed on byte drift once the independent golden is frozen."""

    if type(raw) is not bytes:
        _fail("feasibility-audit candidate must be exact bytes")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), expected[1])
    ):
        _fail("feasibility-audit candidate differs from its frozen golden")
    return raw


def _canonical(value, *, label="semantic resolution feasibility audit"):
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=MAX_ARTIFACT_BYTES
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_exact_value(actual, expected, *, label):
    if not hmac.compare_digest(
        _canonical(actual, label=f"candidate {label}"),
        _canonical(expected, label=f"expected {label}"),
    ):
        _fail(f"{label} differs")


def _reject_prohibited(value):
    if type(value) is list:
        for item in value:
            _reject_prohibited(item)
    elif type(value) is dict:
        for key, item in value.items():
            if key in PROHIBITED_KEYS:
                _fail(f"audit contains prohibited key: {key}")
            _reject_prohibited(item)


def _exact_int(value, *, label, minimum=0, maximum=10_000_000):
    if type(value) is not int or not minimum <= value <= maximum:
        _fail(f"{label} must be an exact bounded integer")
    return value


def _expected_dependency_bindings():
    return [
        {
            "dependency_id": dependency_id,
            "dependency_ordinal": ordinal,
            "dependency_pin": copy.deepcopy(DEPENDENCY_PINS[dependency_id]),
            "dependency_role": DEPENDENCY_ROLES[dependency_id],
        }
        for ordinal, dependency_id in enumerate(DEPENDENCY_ORDER, start=1)
    ]


def _live_join_materials(snapshot):
    return {
        "query-oracle-resolution-live-join": {
            "oracles": snapshot["oracles"],
            "queries": snapshot["queries"],
            "resolution_rows": snapshot["resolution"]["resolution_rows"],
        },
        "source-semantic-live-join": {
            "fact_profiles": snapshot["catalog"]["fact_profiles"],
            "semantic_origins": snapshot["semantic_origins"],
            "semantic_topics": snapshot["catalog"]["semantic_topics"],
        },
        "source-matched-lifecycle-live-join": {
            "event_rows": snapshot["event_rows"],
            "lifecycles": snapshot["lifecycles"],
        },
        "effective-membership-live-join": {
            "effective_plans": snapshot["effective_plans"],
        },
    }


def _expected_live_join_bindings(snapshot):
    materials = _live_join_materials(snapshot)
    result = []
    for ordinal, projection_id in enumerate(LIVE_JOIN_ORDER, start=1):
        try:
            raw = artifact_common.canonical_json_bytes(
                materials[projection_id],
                label=f"independent {projection_id} projection",
                max_bytes=64 * 2**20,
            )
        except artifact_common.PersonaV2ArtifactError as error:
            _fail(str(error))
        result.append(
            {
                "canonical_bytes": len(raw),
                "live_join_ordinal": ordinal,
                "projection_id": projection_id,
                "projection_role": LIVE_JOIN_ROLES[projection_id],
                "sha256": hashlib.sha256(raw).hexdigest(),
                "status": "exact-live-join-projection-bound",
            }
        )
    return result


def preflight_query_history_semantic_resolution_feasibility_audit(value):
    """Bound and authenticate the compact candidate before heavy providers."""

    # Check the pairwise configuration before inspecting caller-controlled
    # structure, then authenticate the canonical bytes before any provider is
    # opened by public validation.
    _expected_golden()
    if type(value) is not dict or set(value) != TOP_LEVEL_FIELDS:
        _fail("audit top-level schema differs")
    raw = _canonical(value)
    _require_expected_raw(raw)
    if len(raw) > TARGET_ARTIFACT_BYTES:
        _fail("audit exceeds its 512-KiB target")
    if (
        value["artifact_kind"] != ARTIFACT_KIND
        or value["artifact_schema"] != ARTIFACT_SCHEMA
        or type(value["artifact_schema_version"]) is not int
        or value["artifact_schema_version"] != ARTIFACT_SCHEMA_VERSION
        or value["fixture_id"] != FIXTURE_ID
        or type(value["fixture_schema_version"]) is not int
        or value["fixture_schema_version"] != FIXTURE_SCHEMA_VERSION
        or value["g0_contract_frozen"] is not False
    ):
        _fail("audit identity or non-G0 state differs")
    authority = value["authority"]
    if type(authority) is not dict or set(authority) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False for flag in authority.values()
    ):
        _fail("audit authority must be the exact all-false schema")
    _require_exact_value(
        value["dependency_bindings"],
        _expected_dependency_bindings(),
        label="audit dependency pins/order",
    )
    _require_exact_value(
        value["remaining_blockers"],
        list(REMAINING_BLOCKERS),
        label="active blocker list",
    )
    _require_exact_value(
        value["remediation_options"],
        list(REMEDIATION_OPTIONS),
        label="required remediation options",
    )
    _require_exact_value(
        value["canonical_limits"],
        {
            "external_dependency_bodies_embedded": False,
            "framed_byte_cap_before_parse_required": True,
            "max_artifact_bytes": MAX_ARTIFACT_BYTES,
            "max_dependency_binding_count": len(DEPENDENCY_ORDER),
            "max_live_join_binding_count": len(LIVE_JOIN_ORDER),
            "max_live_join_projection_bytes": 64 * 2**20,
            "max_persona_count": 20,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "target_artifact_bytes": TARGET_ARTIFACT_BYTES,
            "unicode_normalization": "NFC",
        },
        label="canonical limits",
    )
    if value["hypothesis_status"] != (
        "generated-baseline-feasibility-audit-not-observed-execution-"
        "not-resolution-v2"
    ):
        _fail("hypothesis status differs")
    _require_exact_value(
        value["methodology"],
        {
            "baseline_alignment_predicates": [
                "persona-equal",
                "capability-class-equal",
                "query-project-equals-effective-source-topic-project",
                "query-oracle-source-language-equal",
                "oracle-expected-facts-subset-of-effective-w0-present-facts",
                "required-event-profile-keys-subset-of-authored-source-events",
            ],
            "checkpoint_effective_membership_is_not_inferred_from_w0": True,
            "distractor_capacity_excludes_all_selected_primary_and_companion_sources": True,
            "distractor_capacity_is_before_source-language-filter": True,
            "empty_negative_expected-fact-set-is-reported-as-vacuous": True,
            "fixed_suite_pins_are_context_only_not-live-body-authentication": True,
            "full_direct_owner_suite_bodies_reauthenticated_by_this_fast_audit": False,
            "live_join_projection_digests_cover_every-field-consumed-by-the-audit": True,
            "revision_empty_nonempty_parity_is_not-an-exact-join": True,
            "revision_owner_vocabulary_join_policy": "missing",
        },
        label="methodology",
    )
    _require_exact_value(
        value["orders"],
        {
            "dependency_order": list(DEPENDENCY_ORDER),
            "distractor_profile_class_order": list(DISTRACTOR_CLASSES),
            "live_join_order": list(LIVE_JOIN_ORDER),
            "persona_order": list(envelope.PERSONA_IDS),
            "remediation_option_order": [
                row["option_id"] for row in REMEDIATION_OPTIONS
            ],
        },
        label="orders",
    )
    publication = value["resolution_publication_contract"]
    _require_exact_value(
        publication,
        {
            "artifact_is_query_history_target_resolution_v2": False,
            "artifact_role": "audit-only-active-blocker-evidence",
            "may_replace_query_history_target_resolution_v1": False,
            "resolution_v2_schema_reserved_or_issued": False,
        },
        label="resolution-v2 non-issuance contract",
    )
    claims = value["completion_claims"]
    expected_claims = {
        "all_20_personas_independently_joined": True,
        "all_2100_resolution_targets_examined": True,
        "all_5400_abstract_distractors_examined": True,
        "all_condition_semantic_resolution_complete": False,
        "checkpoint_selector_effective_membership_compiled": False,
        "concrete_distractor_source_mapping_complete": False,
        "four_domain_disjointness_proved": False,
        "live_join_projections_exactly_bound": True,
        "query_history_target_resolution_v2_issued": False,
        "revision_join_policy_available": False,
    }
    _require_exact_value(claims, expected_claims, label="completion claims")
    live_bindings = value["live_join_bindings"]
    if type(live_bindings) is not list or len(live_bindings) != len(
        LIVE_JOIN_ORDER
    ):
        _fail("live join binding cardinality differs")
    for ordinal, (projection_id, binding) in enumerate(
        zip(LIVE_JOIN_ORDER, live_bindings, strict=True), start=1
    ):
        if type(binding) is not dict or set(binding) != {
            "canonical_bytes",
            "live_join_ordinal",
            "projection_id",
            "projection_role",
            "sha256",
            "status",
        }:
            _fail("live join binding schema differs")
        _exact_int(
            binding["canonical_bytes"],
            label="live join canonical bytes",
            minimum=1,
            maximum=64 * 2**20,
        )
        if (
            type(binding["live_join_ordinal"]) is not int
            or binding["live_join_ordinal"] != ordinal
            or binding["projection_id"] != projection_id
            or binding["projection_role"] != LIVE_JOIN_ROLES[projection_id]
            or type(binding["sha256"]) is not str
            or len(binding["sha256"]) != 64
            or any(
                character not in "0123456789abcdef"
                for character in binding["sha256"]
            )
            or binding["status"] != "exact-live-join-projection-bound"
        ):
            _fail("live join binding identity/digest differs")
    rows = value["persona_feasibility_rows"]
    if (
        type(rows) is not list
        or len(rows) != 20
        or any(type(row) is not dict for row in rows)
        or [row.get("persona_id") for row in rows] != list(envelope.PERSONA_IDS)
    ):
        _fail("persona audit order/cardinality differs")
    for row in rows:
        if set(row) != PERSONA_ROW_FIELDS:
            _fail("persona audit row schema differs")
        baseline = row["baseline_target_feasibility"]
        distractor = row["distractor_feasibility"]
        if (
            type(baseline) is not dict
            or type(distractor) is not dict
            or set(baseline) != BASELINE_FIELDS
            or set(distractor) != DISTRACTOR_FIELDS
        ):
            _fail("persona nested schema differs")
        predicates = baseline["predicate_true_counts"]
        if type(predicates) is not dict or set(predicates) != PREDICATE_FIELDS:
            _fail("baseline predicate schema differs")
        for key, count in predicates.items():
            _exact_int(count, label=f"predicate {key}", maximum=100)
        for key in (
            "all_condition_exact_resolution_count",
            "baseline_aligned_count",
            "baseline_mismatch_count",
            "checkpoint_selector_effective_membership_compiled_count",
            "checkpoint_selector_effective_membership_unknown_count",
            "contributor_target_count",
            "incidental_target_count",
            "negative_target_count",
            "negative_vacuous_w0_fact_subset_count",
            "positive_target_count",
            "purged_typed_witness_semantics_authored_count",
            "revision_exact_join_proved_count",
            "revision_join_unknown_count",
            "revision_target_nonempty_count",
            "total_resolution_target_count",
        ):
            _exact_int(baseline[key], label=f"baseline {key}", maximum=105)
        if (
            baseline["contributor_target_count"] != 100
            or baseline["incidental_target_count"] != 5
            or baseline["positive_target_count"] != 85
            or baseline["negative_target_count"] != 15
            or baseline["total_resolution_target_count"] != 105
            or baseline["baseline_aligned_count"]
            + baseline["baseline_mismatch_count"]
            != 100
            or baseline["all_condition_exact_resolution_count"] != 0
            or baseline["all_condition_exact_resolution_status"]
            != "unknown-not-proved"
            or baseline["revision_join_policy_available"] is not False
            or baseline["revision_exact_join_proved_count"] != 0
            or baseline["revision_join_unknown_count"] != 100
            or baseline["checkpoint_selector_effective_membership_compiled_count"]
            != 0
            or baseline["checkpoint_selector_effective_membership_unknown_count"]
            != 100
        ):
            _fail("baseline unresolved-state equations differ")
        expected_classes = [
            {
                "count": EXPECTED_DISTRACTOR_CLASS_COUNTS_PER_PERSONA[key],
                "profile_class": key,
            }
            for key in DISTRACTOR_CLASSES
        ]
        _require_exact_value(
            distractor,
            {
                "abstract_distractor_reference_count": 270,
                "classification_counts": expected_classes,
                "concrete_mapping_count": 0,
                "four_domain_disjointness_candidate_complete": False,
                "maximum_distinct_source_candidate_count_before_language_filter": 53,
                "maximum_mapping_shortfall_count": 217,
                "post_target_singleton_source_capacity": 5,
                "source_language_filtered_capacity_proved": False,
                "topic_language_fact_revision_complete_mapping_proved": False,
            },
            label=f"{row['persona_id']} distractor infeasibility contract",
        )
    p01_baseline = rows[0]["baseline_target_feasibility"]
    if (
        p01_baseline["baseline_aligned_count"] != 13
        or p01_baseline["baseline_mismatch_count"] != 87
    ):
        _fail("p01 baseline 13-aligned/87-mismatch sentinel differs")
    summary = value["summary"]
    baseline_total = sum(
        row["baseline_target_feasibility"]["baseline_aligned_count"]
        for row in rows
    )
    expected_summary_fixed = {
        "abstract_distractor_reference_count": 5_400,
        "all_condition_exact_resolution_count": 0,
        "baseline_aligned_contributor_target_count": baseline_total,
        "baseline_mismatched_contributor_target_count": 2_000 - baseline_total,
        "concrete_distractor_source_mapping_count": 0,
        "contributor_target_count": 2_000,
        "distractor_classification_counts": [
            {"count": count, "profile_class": key}
            for key, count in (
                ("no-w0-profile-candidate", 720),
                ("singleton-only", 3_720),
                ("opposite-conflict", 600),
                ("graph-normal", 360),
            )
        ],
        "four_domain_disjointness_proved": False,
        "incidental_target_count": 100,
        "live_join_binding_count": len(LIVE_JOIN_ORDER),
        "maximum_distinct_distractor_source_candidate_count_before_language_filter": 1_060,
        "maximum_distractor_mapping_shortfall_count": 4_340,
        "persona_count": 20,
        "query_history_target_resolution_v2_issued": False,
        "resolution_target_count": 2_100,
        "revision_join_unknown_count": 2_000,
        "singleton_only_distractor_reference_shortfall_count": 3_620,
        "w0_profile_absent_distractor_reference_count": 720,
    }
    _require_exact_value(
        summary, expected_summary_fixed, label="suite feasibility summary"
    )
    _reject_prohibited(value)
    return raw


def _load_actual_snapshot():
    resolution_value = target_resolution.build_query_history_target_resolution()
    resolution_raw = artifact_common.canonical_json_bytes(
        resolution_value,
        label="pinned query-history target resolution",
        max_bytes=target_resolution.MAX_ARTIFACT_BYTES,
    )
    pin = DEPENDENCY_PINS["query-history-target-resolution-v1"]
    if len(resolution_raw) != pin["canonical_bytes"] or hashlib.sha256(
        resolution_raw
    ).hexdigest() != pin["sha256"]:
        _fail("target-resolution dependency pin drifted")
    queries = query_intent.build_query_intent_suite()
    oracles = semantic_oracle.build_semantic_oracle_suite()
    lifecycles = [
        lifecycle.build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    catalog = source_semantic.build_source_semantic_membership_catalog()
    plans = {}
    events = {}
    origins = {}
    for persona_id in envelope.PERSONA_IDS:
        plan = effective._persona_plan(persona_id)  # noqa: SLF001
        plans[persona_id] = {
            "companion_rows": copy.deepcopy(list(plan["companion_rows"])),
            "primary_rows": copy.deepcopy(list(plan["primary_rows"])),
            "typed_witness_rows": copy.deepcopy(list(plan["typed_witness_rows"])),
        }
        events[persona_id] = list(
            lifecycle.iter_source_matched_lifecycle_event_rows(persona_id)
        )
        origins[persona_id] = [
            source_semantic.build_source_semantic_membership_origin_manifest(
                persona_id, origin
            )
            for origin in source_semantic.ORIGIN_ORDER
        ]
    return {
        "catalog": catalog,
        "effective_plans": plans,
        "event_rows": events,
        "lifecycles": lifecycles,
        "oracles": oracles,
        "queries": queries,
        "resolution": resolution_value,
        "semantic_origins": origins,
    }


def _profile_counts(origins):
    result = {}
    for origin in origins:
        for row in origin["fact_profile_assignment_counts"]:
            profile_id = row["fact_profile_id"]
            result[profile_id] = result.get(profile_id, 0) + row["source_count"]
    return result


def _remaining_profile_counts(lifecycle_value, origins):
    result = _profile_counts(origins)
    selected = lifecycle_value["primary_match_rows"] + lifecycle_value[
        "companion_match_rows"
    ]
    if len(selected) != 115 or len({row["intent_key"] for row in selected}) != 115:
        _fail("primary/companion exclusion domain differs")
    for row in selected:
        profile_id = row["base_fact_profile_id"]
        result[profile_id] = result.get(profile_id, 0) - 1
        if result[profile_id] < 0:
            _fail("profile capacity underflowed")
    return result


def _candidates(answer, distractor, profiles):
    answer = set(answer)
    return [
        row
        for row in profiles
        if distractor in row["present_fact_ids"]
        and answer.isdisjoint(row["present_fact_ids"])
    ]


def _classify(candidates):
    kinds = {row["profile_kind"] for row in candidates}
    if not candidates:
        return "no-w0-profile-candidate"
    if "graph-normal-w0" in kinds:
        return "graph-normal"
    if "conflict-branch" in kinds:
        return "opposite-conflict"
    if kinds == {"w0-singleton"}:
        return "singleton-only"
    _fail("independent distractor taxonomy encountered an unknown profile set")


def _capacity(reference_candidates, counts):
    slots_by_ref = {}
    for reference, profile_ids in reference_candidates:
        slots = []
        for profile_id in sorted(profile_ids, key=_ascii):
            slots.extend(
                (profile_id, ordinal)
                for ordinal in range(
                    1, min(counts.get(profile_id, 0), len(reference_candidates)) + 1
                )
            )
        slots_by_ref[reference] = slots
    owner = {}

    def augment(reference, seen):
        for slot in slots_by_ref[reference]:
            if slot in seen:
                continue
            seen.add(slot)
            previous = owner.get(slot)
            if previous is None or augment(previous, seen):
                owner[slot] = reference
                return True
        return False

    return sum(augment(reference, set()) for reference in slots_by_ref)


def _independent_persona_row(
    persona_id,
    query_value,
    oracle_value,
    lifecycle_value,
    resolution_rows,
    plan,
    event_rows,
    profiles,
    topics,
    origins,
):
    queries = query_value["positive_query_intents"] + query_value[
        "negative_query_intents"
    ]
    oracles = oracle_value["positive_oracle_rows"] + oracle_value[
        "negative_oracle_rows"
    ]
    query_by_key = {row["query_key"]: row for row in queries}
    oracle_by_key = {row["query_intent_key"]: row for row in oracles}
    lifecycle_by_capability = {
        row["capability_key"]: row for row in lifecycle_value["primary_match_rows"]
    }
    effective_by_capability = {
        row["capability_key"]: row for row in plan["primary_rows"]
    }
    witness_by_capability = {
        row["capability_key"]: row for row in plan["typed_witness_rows"]
    }
    if not (
        len(query_by_key)
        == len(oracle_by_key)
        == len(lifecycle_by_capability)
        == len(resolution_rows)
        == 105
        and len(effective_by_capability) == 100
        and len(witness_by_capability) == 15
    ):
        _fail("independent persona join cardinality differs")
    event_profiles = {}
    for event in event_rows:
        if type(event.get("capability_key")) is str:
            event_profiles.setdefault(event["capability_key"], set()).add(
                event["event_profile_key"]
            )
    predicates = {key: 0 for key in PREDICATE_FIELDS}
    contributor = incidental = positive = negative = 0
    revision_nonempty = negative_vacuous = purge_witness = 0
    for resolution in resolution_rows:
        query = query_by_key[resolution["query_key"]]
        oracle = oracle_by_key[resolution["query_key"]]
        capability = resolution["lifecycle_binding"]["capability_key"]
        source = lifecycle_by_capability[capability]
        if source["gate_role"] == "incidental_searchable":
            incidental += 1
            continue
        contributor += 1
        membership = effective_by_capability[capability]
        topic = topics[membership["topic_id"]]
        class_equal = (
            resolution["lifecycle_binding"]["capability_class_key"]
            == source["capability_class_key"]
        )
        topic_equal = topic["project_or_case_id"] == query["project_or_case_id"]
        language_equal = query["language"] == oracle["language"] == source["base_language"]
        answer = oracle["abstract_answer_membership"]
        expected = [] if answer == [] else answer["expected_fact_ids"]
        fact_subset = set(expected).issubset(membership["present_fact_ids"])
        event_subset = set(
            resolution["lifecycle_binding"]["required_event_profile_keys"]
        ).issubset(event_profiles.get(capability, set()))
        predicates["capability_class_equal"] += class_equal
        predicates["topic_project_equal"] += topic_equal
        predicates["language_equal"] += language_equal
        predicates["w0_expected_fact_subset"] += fact_subset
        predicates["authored_event_profile_subset"] += event_subset
        predicates["baseline_topic_language_fact_and_event"] += (
            class_equal and topic_equal and language_equal and fact_subset and event_subset
        )
        if answer == []:
            negative += 1
            negative_vacuous += fact_subset
            witness = witness_by_capability.get(capability)
            if (
                witness is not None
                and membership["witness_fact_ids"] == [witness["fact_id"]]
                and witness["visibility_by_checkpoint"][-1]
                == {"checkpoint": "W5-final", "state": "absent"}
            ):
                purge_witness += 1
        else:
            positive += 1
            revision_nonempty += bool(answer["expected_revision_chain_ids"])
    if (contributor, incidental, positive, negative) != (100, 5, 85, 15):
        _fail("independent target split differs")

    persona_profiles = [row for row in profiles if row["persona_id"] == persona_id]
    classes = {key: 0 for key in DISTRACTOR_CLASSES}
    references = []
    for oracle in oracle_value["positive_oracle_rows"]:
        answer = oracle["abstract_answer_membership"]["expected_fact_ids"]
        for distractor in oracle["distractors"]:
            candidates = _candidates(
                answer, distractor["distractor_fact_id"], persona_profiles
            )
            classes[_classify(candidates)] += 1
            references.append(
                (
                    distractor["distractor_intent_key"],
                    tuple(row["fact_profile_id"] for row in candidates),
                )
            )
    if classes != EXPECTED_DISTRACTOR_CLASS_COUNTS_PER_PERSONA:
        _fail("independent distractor class counts differ")
    remaining = _remaining_profile_counts(lifecycle_value, origins)
    maximum = _capacity(references, remaining)
    singleton = sum(
        remaining.get(row["fact_profile_id"], 0)
        for row in persona_profiles
        if row["profile_kind"] == "w0-singleton"
    )
    if (maximum, singleton) != (53, 5):
        _fail("independent distractor capacity differs")
    baseline = predicates["baseline_topic_language_fact_and_event"]
    return {
        "baseline_target_feasibility": {
            "all_condition_exact_resolution_count": 0,
            "all_condition_exact_resolution_status": "unknown-not-proved",
            "baseline_aligned_count": baseline,
            "baseline_mismatch_count": 100 - baseline,
            "checkpoint_selector_effective_membership_compiled_count": 0,
            "checkpoint_selector_effective_membership_unknown_count": 100,
            "contributor_target_count": 100,
            "incidental_target_count": 5,
            "negative_target_count": 15,
            "negative_vacuous_w0_fact_subset_count": negative_vacuous,
            "positive_target_count": 85,
            "predicate_true_counts": predicates,
            "purged_typed_witness_semantics_authored_count": purge_witness,
            "revision_exact_join_proved_count": 0,
            "revision_join_policy_available": False,
            "revision_join_unknown_count": 100,
            "revision_target_nonempty_count": revision_nonempty,
            "total_resolution_target_count": 105,
        },
        "distractor_feasibility": {
            "abstract_distractor_reference_count": 270,
            "classification_counts": [
                {"count": classes[key], "profile_class": key}
                for key in DISTRACTOR_CLASSES
            ],
            "concrete_mapping_count": 0,
            "four_domain_disjointness_candidate_complete": False,
            "maximum_distinct_source_candidate_count_before_language_filter": maximum,
            "maximum_mapping_shortfall_count": 270 - maximum,
            "post_target_singleton_source_capacity": singleton,
            "source_language_filtered_capacity_proved": False,
            "topic_language_fact_revision_complete_mapping_proved": False,
        },
        "persona_id": persona_id,
    }


def _expected_persona_rows(snapshot):
    order = list(envelope.PERSONA_IDS)
    if any(
        [row.get("persona_id") for row in snapshot[key]] != order
        for key in ("queries", "oracles", "lifecycles")
    ):
        _fail("independent dependency persona order differs")
    resolution_by_persona = {persona_id: [] for persona_id in order}
    for row in snapshot["resolution"]["resolution_rows"]:
        resolution_by_persona[row["persona_id"]].append(row)
    topics = {
        row["topic_id"]: row for row in snapshot["catalog"]["semantic_topics"]
    }
    profiles = snapshot["catalog"]["fact_profiles"]
    rows = [
        _independent_persona_row(
            persona_id,
            query,
            oracle,
            lifecycle_value,
            resolution_by_persona[persona_id],
            snapshot["effective_plans"][persona_id],
            snapshot["event_rows"][persona_id],
            profiles,
            topics,
            snapshot["semantic_origins"][persona_id],
        )
        for persona_id, query, oracle, lifecycle_value in zip(
            order,
            snapshot["queries"],
            snapshot["oracles"],
            snapshot["lifecycles"],
            strict=True,
        )
    ]
    p01_baseline = rows[0]["baseline_target_feasibility"]
    if (
        p01_baseline["baseline_aligned_count"] != 13
        or p01_baseline["baseline_mismatch_count"] != 87
    ):
        _fail("p01 baseline 13-aligned/87-mismatch sentinel drifted")
    return rows


def _snapshot_candidate(value):
    try:
        detached = copy.deepcopy(value)
    except Exception as error:  # pragma: no cover - hostile object boundary
        _fail(f"candidate copy failed: {type(error).__name__}")
    detached_raw = preflight_query_history_semantic_resolution_feasibility_audit(
        detached
    )
    live_raw = preflight_query_history_semantic_resolution_feasibility_audit(value)
    if not hmac.compare_digest(detached_raw, live_raw):
        _fail("candidate changed while copied")
    return detached, detached_raw


def _validate_with_snapshot(value, snapshot):
    detached, opening = _snapshot_candidate(value)
    detached_snapshot = copy.deepcopy(snapshot)
    expected_live_bindings = _expected_live_join_bindings(detached_snapshot)
    _require_exact_value(
        detached["live_join_bindings"],
        expected_live_bindings,
        label="live join projection bindings",
    )
    expected_rows = _expected_persona_rows(detached_snapshot)
    if not hmac.compare_digest(
        _canonical(
            detached["persona_feasibility_rows"],
            label="candidate persona feasibility rows",
        ),
        _canonical(expected_rows, label="independent persona feasibility rows"),
    ):
        _fail("persona feasibility rows differ from independent reconstruction")
    closing = preflight_query_history_semantic_resolution_feasibility_audit(value)
    if not hmac.compare_digest(opening, closing):
        _fail("candidate changed during independent validation")
    return True


def validate_query_history_semantic_resolution_feasibility_audit(value):
    """Replay all twenty generated joins and authenticate one candidate."""

    preflight_query_history_semantic_resolution_feasibility_audit(value)
    return _validate_with_snapshot(value, _load_actual_snapshot())


def validate_query_history_semantic_resolution_feasibility_audit_bytes(raw):
    _expected_golden()
    if type(raw) is not bytes or len(raw) > MAX_ARTIFACT_BYTES:
        _fail("audit frame must be bounded bytes")
    def reject_duplicates(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                _fail("audit JSON contains duplicate object keys")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=reject_duplicates,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"invalid JSON constant: {token}")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        _fail(f"audit JSON parse failed: {type(error).__name__}")
    if not hmac.compare_digest(_canonical(value), raw):
        _fail("audit bytes are not canonical JSON")
    return validate_query_history_semantic_resolution_feasibility_audit(value)


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "PersonaV2SemanticResolutionFeasibilityValidationError",
    "preflight_query_history_semantic_resolution_feasibility_audit",
    "validate_query_history_semantic_resolution_feasibility_audit",
    "validate_query_history_semantic_resolution_feasibility_audit_bytes",
]
