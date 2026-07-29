"""Non-authorizing semantic feasibility audit for query/history resolution v1.

The accepted v1 target-resolution artifact deliberately matches queries to
lifecycle *classes*, not to source topic/language/fact/revision semantics.  This
module measures that remaining gap against the generated twenty-person source
inventory.  It does not issue a resolution v2, compile relevance, or grant any
execution/G0 authority.

The audit has two deliberately separate results:

* a baseline W0 join (topic, language, effective present facts, and authored
  event-profile availability), and
* a capacity-only distractor upper bound after excluding the already selected
  primary and companion source intents.

Revision-chain vocabulary and checkpoint-effective membership do not yet have
an owner-defined join.  They are reported as unknown rather than inferred from
empty/non-empty lists or similarly named strings.
"""

from __future__ import annotations

import copy
import functools
import hashlib
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

# Frozen after an all-persona full reconstruction and two isolated cold
# reconstructions under distinct hash seeds agreed byte-for-byte.
EXPECTED_CANONICAL_BYTES = 40_947
EXPECTED_SHA256 = (
    "22e8e9b2af457ebe35c4655c49435eea72955cc753d5bd132c5bc469ce3aba27"
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
        "sha256": "bbb0941e7e640130fb57e07c1301991679c2dea80407573b82e9ef575b074637",
    },
    "complete-semantic-projection-inventory-v2": {
        "artifact_schema": "kio.persona.pc-semantic-projection-derivation-inventory/v2",
        "artifact_schema_version": 2,
        "canonical_bytes": 697_466,
        "sha256": "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91",
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


class PersonaV2SemanticResolutionFeasibilityError(ValueError):
    """Raised when the feasibility audit cannot be derived exactly."""


def _fail(message):
    raise PersonaV2SemanticResolutionFeasibilityError(message)


def _ascii(value):
    return value.encode("ascii", "strict")


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    """Return the optional frozen identity after validating its configuration."""

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
    """Fail closed on byte drift once the optional golden has been frozen."""

    if type(raw) is not bytes:
        _fail("feasibility-audit candidate must be exact bytes")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0] or _sha256(raw) != expected[1]
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


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _dependency_bindings():
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


def _live_join_bindings(snapshot):
    materials = _live_join_materials(snapshot)
    result = []
    for ordinal, projection_id in enumerate(LIVE_JOIN_ORDER, start=1):
        try:
            raw = artifact_common.canonical_json_bytes(
                materials[projection_id],
                label=f"{projection_id} projection",
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
                "sha256": _sha256(raw),
                "status": "exact-live-join-projection-bound",
            }
        )
    return result


def _load_actual_snapshot():
    """Load generated data needed by the audit without building 203k row bodies."""

    resolution_value = target_resolution.build_query_history_target_resolution()
    resolution_raw = artifact_common.canonical_json_bytes(
        resolution_value,
        label="pinned query-history target resolution",
        max_bytes=target_resolution.MAX_ARTIFACT_BYTES,
    )
    expected_pin = DEPENDENCY_PINS["query-history-target-resolution-v1"]
    if (
        len(resolution_raw) != expected_pin["canonical_bytes"]
        or _sha256(resolution_raw) != expected_pin["sha256"]
    ):
        _fail("query-history target resolution pin drifted")
    if (
        target_resolution.EXPECTED_CANONICAL_BYTES
        != expected_pin["canonical_bytes"]
        or target_resolution.EXPECTED_SHA256 != expected_pin["sha256"]
        or lifecycle.EXPECTED_SUITE_CANONICAL_BYTES
        != DEPENDENCY_PINS["source-matched-lifecycle-suite-v1"]["canonical_bytes"]
        or lifecycle.EXPECTED_SUITE_SHA256
        != DEPENDENCY_PINS["source-matched-lifecycle-suite-v1"]["sha256"]
        or effective.EXPECTED_SUITE_CANONICAL_BYTES
        != DEPENDENCY_PINS["lifecycle-effective-membership-reconciliation-v1"]["canonical_bytes"]
        or effective.EXPECTED_SUITE_SHA256
        != DEPENDENCY_PINS["lifecycle-effective-membership-reconciliation-v1"]["sha256"]
    ):
        _fail("accepted baseline module pins drifted")

    queries = query_intent.build_query_intent_suite()
    oracles = semantic_oracle.build_semantic_oracle_suite()
    lifecycles = [
        lifecycle.build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    catalog = source_semantic.build_source_semantic_membership_catalog()
    effective_plans = {}
    event_rows = {}
    semantic_origins = {}
    for persona_id in envelope.PERSONA_IDS:
        plan = effective._persona_plan(persona_id)  # noqa: SLF001 - exact owner view
        effective_plans[persona_id] = {
            "companion_rows": copy.deepcopy(list(plan["companion_rows"])),
            "primary_rows": copy.deepcopy(list(plan["primary_rows"])),
            "typed_witness_rows": copy.deepcopy(list(plan["typed_witness_rows"])),
        }
        event_rows[persona_id] = list(
            lifecycle.iter_source_matched_lifecycle_event_rows(persona_id)
        )
        semantic_origins[persona_id] = [
            source_semantic.build_source_semantic_membership_origin_manifest(
                persona_id, origin
            )
            for origin in source_semantic.ORIGIN_ORDER
        ]
    return {
        "catalog": catalog,
        "effective_plans": effective_plans,
        "event_rows": event_rows,
        "lifecycles": lifecycles,
        "oracles": oracles,
        "queries": queries,
        "resolution": resolution_value,
        "semantic_origins": semantic_origins,
    }


def _joined_query_rows(query_value, oracle_value):
    query_rows = query_value["positive_query_intents"] + query_value[
        "negative_query_intents"
    ]
    oracle_rows = oracle_value["positive_oracle_rows"] + oracle_value[
        "negative_oracle_rows"
    ]
    by_query = {row["query_key"]: row for row in query_rows}
    oracle_by_query = {row["query_intent_key"]: row for row in oracle_rows}
    if (
        len(by_query) != 105
        or len(oracle_by_query) != 105
        or set(by_query) != set(oracle_by_query)
    ):
        _fail("query/oracle suite is not an exact 105-row join")
    return by_query, oracle_by_query


def _profile_counts(origin_values):
    counts = {}
    for origin in origin_values:
        for row in origin["fact_profile_assignment_counts"]:
            profile_id = row["fact_profile_id"]
            counts[profile_id] = counts.get(profile_id, 0) + row["source_count"]
    return counts


def _remaining_profile_counts(lifecycle_value, origin_values):
    """Remove all primary/companion source domains from the profile supply."""

    counts = _profile_counts(origin_values)
    selected = lifecycle_value["primary_match_rows"] + lifecycle_value[
        "companion_match_rows"
    ]
    if len(selected) != 115 or len({row["intent_key"] for row in selected}) != 115:
        _fail("selected primary/companion source domains are not exact")
    for row in selected:
        profile_id = row["base_fact_profile_id"]
        counts[profile_id] = counts.get(profile_id, 0) - 1
        if counts[profile_id] < 0:
            _fail("selected source removal underflowed a fact-profile supply")
    return counts


def _candidate_profiles(answer_fact_ids, distractor_fact_id, profiles):
    answer = set(answer_fact_ids)
    return [
        row
        for row in profiles
        if distractor_fact_id in row["present_fact_ids"]
        and answer.isdisjoint(row["present_fact_ids"])
    ]


def _distractor_class(candidate_profiles):
    kinds = {row["profile_kind"] for row in candidate_profiles}
    if not candidate_profiles:
        return "no-w0-profile-candidate"
    if "graph-normal-w0" in kinds:
        return "graph-normal"
    if "conflict-branch" in kinds:
        return "opposite-conflict"
    if kinds == {"w0-singleton"}:
        return "singleton-only"
    _fail("distractor candidate profile kinds are outside the exact taxonomy")


def _maximum_distinct_source_candidates(reference_candidates, profile_counts):
    """Maximum capacity matching before source-language filtering."""

    slot_owner = {}
    candidate_slots = []
    for reference_key, profile_ids in reference_candidates:
        slots = []
        for profile_id in sorted(profile_ids, key=_ascii):
            capacity = min(profile_counts.get(profile_id, 0), len(reference_candidates))
            slots.extend((profile_id, ordinal) for ordinal in range(1, capacity + 1))
        candidate_slots.append((reference_key, slots))
    slots_by_reference = dict(candidate_slots)

    def augment(reference_key, slots, seen):
        for slot in slots:
            if slot in seen:
                continue
            seen.add(slot)
            previous = slot_owner.get(slot)
            if previous is None:
                slot_owner[slot] = reference_key
                return True
            previous_slots = slots_by_reference[previous]
            if augment(previous, previous_slots, seen):
                slot_owner[slot] = reference_key
                return True
        return False

    matched = 0
    for reference_key, slots in candidate_slots:
        if augment(reference_key, slots, set()):
            matched += 1
    return matched


def _persona_audit(
    persona_id,
    *,
    query_value,
    oracle_value,
    lifecycle_value,
    resolution_rows,
    effective_plan,
    events,
    profiles,
    topics,
    semantic_origins,
):
    query_by_key, oracle_by_query = _joined_query_rows(query_value, oracle_value)
    lifecycle_by_capability = {
        row["capability_key"]: row for row in lifecycle_value["primary_match_rows"]
    }
    effective_by_capability = {
        row["capability_key"]: row for row in effective_plan["primary_rows"]
    }
    witness_by_capability = {
        row["capability_key"]: row
        for row in effective_plan["typed_witness_rows"]
    }
    if (
        len(resolution_rows) != 105
        or len(lifecycle_by_capability) != 105
        or len(effective_by_capability) != 100
        or len(witness_by_capability) != 15
    ):
        _fail(f"{persona_id} source/query cardinality drifted")
    event_profiles = {}
    for row in events:
        capability_key = row.get("capability_key")
        event_profile = row.get("event_profile_key")
        if type(capability_key) is str and type(event_profile) is str:
            event_profiles.setdefault(capability_key, set()).add(event_profile)

    predicate_counts = {
        "authored_event_profile_subset": 0,
        "baseline_topic_language_fact_and_event": 0,
        "capability_class_equal": 0,
        "language_equal": 0,
        "topic_project_equal": 0,
        "w0_expected_fact_subset": 0,
    }
    positive_count = 0
    negative_count = 0
    negative_vacuous_fact_count = 0
    revision_target_nonempty_count = 0
    purge_witness_authored_count = 0
    contributor_count = 0
    incidental_count = 0
    for resolution_row in resolution_rows:
        query_key = resolution_row["query_key"]
        query_row = query_by_key[query_key]
        oracle_row = oracle_by_query[query_key]
        capability_key = resolution_row["lifecycle_binding"]["capability_key"]
        lifecycle_row = lifecycle_by_capability.get(capability_key)
        if lifecycle_row is None:
            _fail("resolution references an unknown lifecycle capability")
        if lifecycle_row["gate_role"] == "incidental_searchable":
            incidental_count += 1
            continue
        if lifecycle_row["gate_role"] != "contract_contributor":
            _fail("target source has an unknown gate role")
        contributor_count += 1
        effective_row = effective_by_capability.get(capability_key)
        if effective_row is None:
            _fail("contributor target lacks effective W0 membership")
        topic = topics.get(effective_row["topic_id"])
        if topic is None or lifecycle_row["base_topic_id"] != effective_row["topic_id"]:
            _fail("effective target topic does not match the selected source topic")

        class_equal = (
            resolution_row["lifecycle_binding"]["capability_class_key"]
            == lifecycle_row["capability_class_key"]
        )
        topic_equal = topic["project_or_case_id"] == query_row["project_or_case_id"]
        language_equal = (
            query_row["language"]
            == oracle_row["language"]
            == lifecycle_row["base_language"]
        )
        membership = oracle_row["abstract_answer_membership"]
        expected_facts = [] if membership == [] else membership["expected_fact_ids"]
        fact_subset = set(expected_facts).issubset(effective_row["present_fact_ids"])
        required_profiles = set(
            resolution_row["lifecycle_binding"]["required_event_profile_keys"]
        )
        event_subset = required_profiles.issubset(
            event_profiles.get(capability_key, set())
        )
        predicate_counts["capability_class_equal"] += class_equal
        predicate_counts["topic_project_equal"] += topic_equal
        predicate_counts["language_equal"] += language_equal
        predicate_counts["w0_expected_fact_subset"] += fact_subset
        predicate_counts["authored_event_profile_subset"] += event_subset
        predicate_counts["baseline_topic_language_fact_and_event"] += (
            class_equal and topic_equal and language_equal and fact_subset and event_subset
        )
        if membership == []:
            negative_count += 1
            negative_vacuous_fact_count += fact_subset
            witness = witness_by_capability.get(capability_key)
            visibility = [] if witness is None else witness["visibility_by_checkpoint"]
            if (
                witness is not None
                and effective_row["witness_fact_ids"] == [witness["fact_id"]]
                and visibility
                and visibility[-1] == {"checkpoint": "W5-final", "state": "absent"}
            ):
                purge_witness_authored_count += 1
        else:
            positive_count += 1
            revision_target_nonempty_count += bool(
                membership["expected_revision_chain_ids"]
            )

    if (contributor_count, incidental_count, positive_count, negative_count) != (
        100,
        5,
        85,
        15,
    ):
        _fail("contributor/incidental or positive/negative target split drifted")

    persona_profiles = [row for row in profiles if row["persona_id"] == persona_id]
    class_counts = {key: 0 for key in DISTRACTOR_CLASSES}
    reference_candidates = []
    for oracle_row in oracle_value["positive_oracle_rows"]:
        answer_facts = oracle_row["abstract_answer_membership"]["expected_fact_ids"]
        for distractor in oracle_row["distractors"]:
            candidates = _candidate_profiles(
                answer_facts,
                distractor["distractor_fact_id"],
                persona_profiles,
            )
            class_counts[_distractor_class(candidates)] += 1
            reference_candidates.append(
                (
                    distractor["distractor_intent_key"],
                    tuple(row["fact_profile_id"] for row in candidates),
                )
            )
    if class_counts != EXPECTED_DISTRACTOR_CLASS_COUNTS_PER_PERSONA:
        _fail(f"{persona_id} distractor profile taxonomy drifted: {class_counts}")
    remaining_counts = _remaining_profile_counts(lifecycle_value, semantic_origins)
    maximum = _maximum_distinct_source_candidates(
        reference_candidates, remaining_counts
    )
    if maximum != 53:
        _fail(f"{persona_id} distractor source upper bound drifted: {maximum}")
    singleton_remaining = sum(
        remaining_counts.get(row["fact_profile_id"], 0)
        for row in persona_profiles
        if row["profile_kind"] == "w0-singleton"
    )
    if singleton_remaining != 5:
        _fail("post-target singleton source capacity is not exact five")

    baseline = predicate_counts["baseline_topic_language_fact_and_event"]
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
            "negative_vacuous_w0_fact_subset_count": negative_vacuous_fact_count,
            "positive_target_count": 85,
            "predicate_true_counts": predicate_counts,
            "purged_typed_witness_semantics_authored_count": purge_witness_authored_count,
            "revision_exact_join_proved_count": 0,
            "revision_join_policy_available": False,
            "revision_join_unknown_count": 100,
            "revision_target_nonempty_count": revision_target_nonempty_count,
            "total_resolution_target_count": 105,
        },
        "distractor_feasibility": {
            "abstract_distractor_reference_count": 270,
            "classification_counts": [
                {"count": class_counts[key], "profile_class": key}
                for key in DISTRACTOR_CLASSES
            ],
            "concrete_mapping_count": 0,
            "four_domain_disjointness_candidate_complete": False,
            "maximum_distinct_source_candidate_count_before_language_filter": maximum,
            "maximum_mapping_shortfall_count": 270 - maximum,
            "post_target_singleton_source_capacity": singleton_remaining,
            "source_language_filtered_capacity_proved": False,
            "topic_language_fact_revision_complete_mapping_proved": False,
        },
        "persona_id": persona_id,
    }


def _build_from_snapshot(snapshot):
    if type(snapshot) is not dict:
        _fail("dependency snapshot must be an object")
    expected_order = list(envelope.PERSONA_IDS)
    live_join_bindings = _live_join_bindings(snapshot)
    queries = snapshot["queries"]
    oracles = snapshot["oracles"]
    lifecycles = snapshot["lifecycles"]
    if any(
        type(values) is not list
        or [row.get("persona_id") for row in values] != expected_order
        for values in (queries, oracles, lifecycles)
    ):
        _fail("dependency persona suites are not in exact p01..p20 order")
    resolution_rows = snapshot["resolution"]["resolution_rows"]
    by_persona = {persona_id: [] for persona_id in expected_order}
    for row in resolution_rows:
        if row.get("persona_id") not in by_persona:
            _fail("resolution contains an unknown persona")
        by_persona[row["persona_id"]].append(row)
    catalog = snapshot["catalog"]
    topics = {row["topic_id"]: row for row in catalog["semantic_topics"]}
    profiles = catalog["fact_profiles"]
    persona_rows = []
    for persona_id, query_value, oracle_value, lifecycle_value in zip(
        expected_order, queries, oracles, lifecycles, strict=True
    ):
        persona_rows.append(
            _persona_audit(
                persona_id,
                query_value=query_value,
                oracle_value=oracle_value,
                lifecycle_value=lifecycle_value,
                resolution_rows=by_persona[persona_id],
                effective_plan=snapshot["effective_plans"][persona_id],
                events=snapshot["event_rows"][persona_id],
                profiles=profiles,
                topics=topics,
                semantic_origins=snapshot["semantic_origins"][persona_id],
            )
        )

    total_aligned = sum(
        row["baseline_target_feasibility"]["baseline_aligned_count"]
        for row in persona_rows
    )
    total_maximum = sum(
        row["distractor_feasibility"][
            "maximum_distinct_source_candidate_count_before_language_filter"
        ]
        for row in persona_rows
    )
    distractor_class_totals = {
        key: sum(
            next(
                item["count"]
                for item in row["distractor_feasibility"]["classification_counts"]
                if item["profile_class"] == key
            )
            for row in persona_rows
        )
        for key in DISTRACTOR_CLASSES
    }
    if distractor_class_totals != {
        "no-w0-profile-candidate": 720,
        "singleton-only": 3_720,
        "opposite-conflict": 600,
        "graph-normal": 360,
    } or total_maximum != 1_060:
        _fail("suite distractor feasibility totals drifted")
    # 2026-07-28 に 13/87 から 10/90 へ動かした。原因は改名で、
    # `persona_v2_source_matched_lifecycle_inventory._domain_key` の
    # 前置詞が `kcs-lifecycle-v1/` から `kio-lifecycle-v1/` になったため
    # domain-separated-sha256-order の DFS 探索順が変わり、cross-format の
    # 照合結果が変わった。salt だけを戻すと 13 が復帰することを確かめてある。
    # distractor 分類の内訳 (720/3720/600/360) と上界 1060 は動いていないので、
    # 変わったのは照合の選び方であって fixture の構造ではない。
    p01_baseline = persona_rows[0]["baseline_target_feasibility"]
    if (
        p01_baseline["baseline_aligned_count"] != 10
        or p01_baseline["baseline_mismatch_count"] != 90
    ):
        _fail("p01 baseline 10-aligned/90-mismatch sentinel drifted")

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "canonical_limits": {
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
        "completion_claims": {
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
        },
        "dependency_bindings": _dependency_bindings(),
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "generated-baseline-feasibility-audit-not-observed-execution-"
            "not-resolution-v2"
        ),
        "live_join_bindings": live_join_bindings,
        "methodology": {
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
            "fixed_suite_pins_are_context_only_not-live-body-authentication": True,
            "full_direct_owner_suite_bodies_reauthenticated_by_this_fast_audit": False,
            "live_join_projection_digests_cover_every-field-consumed-by-the-audit": True,
            "empty_negative_expected-fact-set-is-reported-as-vacuous": True,
            "revision_empty_nonempty_parity_is_not-an-exact-join": True,
            "revision_owner_vocabulary_join_policy": "missing",
        },
        "orders": {
            "dependency_order": list(DEPENDENCY_ORDER),
            "distractor_profile_class_order": list(DISTRACTOR_CLASSES),
            "live_join_order": list(LIVE_JOIN_ORDER),
            "persona_order": expected_order,
            "remediation_option_order": [
                row["option_id"] for row in REMEDIATION_OPTIONS
            ],
        },
        "persona_feasibility_rows": persona_rows,
        "remaining_blockers": list(REMAINING_BLOCKERS),
        "remediation_options": copy.deepcopy(list(REMEDIATION_OPTIONS)),
        "resolution_publication_contract": {
            "artifact_is_query_history_target_resolution_v2": False,
            "artifact_role": "audit-only-active-blocker-evidence",
            "may_replace_query_history_target_resolution_v1": False,
            "resolution_v2_schema_reserved_or_issued": False,
        },
        "summary": {
            "abstract_distractor_reference_count": 5_400,
            "all_condition_exact_resolution_count": 0,
            "baseline_aligned_contributor_target_count": total_aligned,
            "baseline_mismatched_contributor_target_count": 2_000 - total_aligned,
            "concrete_distractor_source_mapping_count": 0,
            "contributor_target_count": 2_000,
            "distractor_classification_counts": [
                {"count": distractor_class_totals[key], "profile_class": key}
                for key in DISTRACTOR_CLASSES
            ],
            "four_domain_disjointness_proved": False,
            "incidental_target_count": 100,
            "live_join_binding_count": len(live_join_bindings),
            "maximum_distinct_distractor_source_candidate_count_before_language_filter": total_maximum,
            "maximum_distractor_mapping_shortfall_count": 5_400 - total_maximum,
            "persona_count": 20,
            "query_history_target_resolution_v2_issued": False,
            "resolution_target_count": 2_100,
            "revision_join_unknown_count": 2_000,
            "singleton_only_distractor_reference_shortfall_count": 3_620,
            "w0_profile_absent_distractor_reference_count": 720,
        },
    }
    raw = _canonical(value)
    if len(raw) > TARGET_ARTIFACT_BYTES:
        _fail("feasibility audit exceeds its 512-KiB target")
    return value


@functools.lru_cache(maxsize=1)
def _cached_raw():
    # Reject a partial/invalid freeze before opening any heavy dependency.
    _expected_golden()
    return _require_expected_raw(
        _canonical(_build_from_snapshot(_load_actual_snapshot()))
    )


def build_query_history_semantic_resolution_feasibility_audit():
    """Return a detached all-persona audit; this can be a heavy first build."""

    raw = _require_expected_raw(_cached_raw())
    return json.loads(raw.decode("utf-8", "strict"))


def _build_query_history_semantic_resolution_feasibility_audit(*, snapshot):
    """Explicit snapshot hook used by bounded focused tests."""

    return copy.deepcopy(_build_from_snapshot(copy.deepcopy(snapshot)))


def candidate_bytes(value):
    """Canonicalize a candidate and enforce its identity once frozen."""

    _expected_golden()
    if type(value) is not dict:
        _fail("feasibility audit must be an object")
    return _require_expected_raw(_canonical(value))


def validate_query_history_semantic_resolution_feasibility_audit(value):
    # Authenticate against the producer-owned golden before opening the
    # independently implemented validator or any of its heavy providers.
    candidate_bytes(value)
    try:
        from . import persona_v2_query_history_semantic_resolution_feasibility_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_query_history_semantic_resolution_feasibility_validator as independent
    try:
        return independent.validate_query_history_semantic_resolution_feasibility_audit(
            value
        )
    except independent.PersonaV2SemanticResolutionFeasibilityValidationError as error:
        _fail(str(error))


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "DEPENDENCY_ORDER",
    "DEPENDENCY_PINS",
    "DISTRACTOR_CLASSES",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "PersonaV2SemanticResolutionFeasibilityError",
    "build_query_history_semantic_resolution_feasibility_audit",
    "candidate_bytes",
    "validate_query_history_semantic_resolution_feasibility_audit",
]
