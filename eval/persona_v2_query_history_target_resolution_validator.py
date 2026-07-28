"""Producer-independent validation for query/history target resolution.

The producer is intentionally not imported.  This module reconstructs the
semantic classification and the class-constrained bipartite matching from the
three accepted upstream owners.  Only immutable canonical dependency bytes are
cached, and every validation checks fresh opening and closing provider reads.
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
    "fbb0fd1a78d034fcd1777a6aaf0e7ee9bc21d07255f2ce9c7d5fc9761dc11593"
)
MATCHING_ALGORITHM = (
    "semantic-class-constrained-domain-separated-sha256-dfs-augmenting-path"
)

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

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "orders",
        "persona_summaries",
        "remaining_blockers",
        "resolution_contract",
        "resolution_rows",
        "summary",
    }
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_history_receipts_attested",
        "authorizes_compiled_relevance",
        "authorizes_corpus_namespace",
        "authorizes_evaluation_publication",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_execution",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_query_execution",
        "authorizes_query_rendering",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "effective_lifecycle_membership_available",
        "final_identity_relevance_available",
    }
)
CANONICAL_LIMIT_FIELDS = frozenset(
    {
        "framed_byte_cap_before_body_required",
        "max_body_bytes",
        "max_expanded_node_count",
        "max_input_binding_count",
        "max_nesting_depth",
        "max_resolution_row_count",
        "max_string_bytes",
        "null_float_or_negative_integer_allowed",
        "precanonical_expanded_structure_preflight_required",
        "self_hash_embedded",
        "target_body_bytes",
        "unicode_normalization",
    }
)
COMPLETION_FIELDS = frozenset(
    {
        "all_2100_query_intents_accounted",
        "abstract_query_to_lifecycle_capability_bijection_authored",
        "compiled_history_event_targets_present",
        "corpus_namespace_or_source_id_preimage_changed",
        "distractor_source_mapping_resolved",
        "effective_source_fact_membership_resolved",
        "exact_stratum_capability_count_table_proved",
        "final_identity_relevance_present",
        "global_answer_and_distractor_fact_sets_disjoint",
        "per_query_answer_and_distractor_fact_sets_disjoint",
        "primary_and_companion_source_intents_disjoint",
        "query_target_and_distractor_abstract_keys_disjoint",
        "query_target_and_lifecycle_source_intent_keys_disjoint",
        "rendered_query_or_compiled_relevance_present",
        "semantic_class_constraints_satisfied",
        "source_topic_language_fact_equality_proved",
        "target_primary_companion_and_distractor_source_intents_disjoint",
    }
)
DEPENDENCY_DIRECTION_FIELDS = frozenset(
    {
        "corpus_namespace_may_import_this_artifact",
        "corpus_renderer_may_import_this_artifact",
        "evaluation_closure_may_bind_this_artifact",
        "lifecycle_source_matching_remains_query_independent",
        "query_or_oracle_change_may_change_corpus_root",
        "query_or_oracle_change_may_change_source_id_preimage",
        "resolution_is_downstream_of_query_oracle_and_lifecycle_matching",
    }
)
ORDERS_FIELDS = frozenset(
    {"persona_order", "resolution_rows", "within_class_matching"}
)
SUMMARY_FIELDS = frozenset(
    {
        "abstract_companion_binding_count",
        "abstract_distractor_reference_count",
        "distinct_distractor_source_count",
        "input_binding_count",
        "negative_query_count",
        "persona_count",
        "positive_query_count",
        "query_capability_bijection_count",
    }
)
RESOLUTION_CONTRACT_FIELDS = frozenset(
    {
        "abstract_keys_only",
        "class_assignment_uses_revision_chain_and_operation_semantics",
        "effective_membership_overlay_required_before_fact_resolution",
        "matching_algorithm",
        "ordinal_zip_allowed",
        "source_topic_language_or_fact_match_inferred_from_w0_base",
        "stratum_capability_counts_per_persona",
    }
)
INPUT_BINDING_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "dependency_role",
        "fixture_id",
        "fixture_schema_version",
        "name",
        "persona_id",
        "sha256",
    }
)
PERSONA_SUMMARY_FIELDS = frozenset(
    {
        "abstract_companion_binding_count",
        "capability_class_counts",
        "negative_query_count",
        "persona_id",
        "positive_query_count",
        "query_capability_bijection_count",
        "stratum_counts",
    }
)
RESOLUTION_ROW_FIELDS = frozenset(
    {
        "abstract_answer_contract",
        "abstract_target",
        "distractor_contract",
        "evaluation_class",
        "lifecycle_binding",
        "oracle_evidence",
        "persona_id",
        "query_key",
        "resolution_status",
        "scenario_id",
        "semantic_match_rule_id",
        "stratum_id",
    }
)
ABSTRACT_ANSWER_FIELDS = frozenset(
    {"answer_membership_key", "expected_fact_ids", "expected_revision_chain_ids", "status"}
)
ABSTRACT_TARGET_FIELDS = frozenset({"intent_key", "logical_document_key"})
DISTRACTOR_FIELDS = frozenset(
    {
        "distractor_fact_ids",
        "distractor_intent_keys",
        "distractor_logical_document_keys",
        "mapped_source_intent_keys",
        "per_query_answer_fact_disjoint",
        "reference_kind",
        "source_mapping_resolved",
        "source_mapping_status",
    }
)
LIFECYCLE_BINDING_FIELDS = frozenset(
    {
        "capability_class_key",
        "capability_key",
        "companion",
        "logical_document_slot_key",
        "primary_source_intent_key",
        "required_event_profile_keys",
    }
)
ORACLE_EVIDENCE_FIELDS = frozenset(
    {"evidence_kind", "event_template_rows", "operation_kind", "required_evidence_state"}
)
RESOLUTION_STATUS_FIELDS = frozenset(
    {
        "abstract_capability_binding_authored",
        "compiled_history_event_binding_present",
        "effective_fact_membership_present",
        "final_identity_binding_present",
        "source_topic_language_fact_equality_proved",
    }
)

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


class PersonaV2QueryHistoryTargetResolutionValidationError(ValueError):
    """Raised when target resolution cannot be independently authenticated."""


def _fail(message):
    # Messages deliberately describe the failed invariant and never interpolate
    # untrusted query/target keys.
    raise PersonaV2QueryHistoryTargetResolutionValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _require_frozen_raw(raw, *, label):
    if (
        type(raw) is not bytes
        or len(raw) != EXPECTED_CANONICAL_BYTES
        or not hmac.compare_digest(_sha256(raw), EXPECTED_SHA256)
    ):
        _fail(f"{label} differs from the independent frozen canonical pin")


def _ascii(value):
    if type(value) is not str:
        _fail("canonical key must be a string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("synthetic keys must be ASCII")


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


def _require_exact_object(value, fields, *, label):
    if type(value) is not dict or set(value) != fields:
        _fail(f"{label} shallow schema differs")


def _require_exact_list(value, length, *, label):
    if type(value) is not list or len(value) != length:
        _fail(f"{label} shallow cardinality differs")


def _require_scalar(value, expected_type, *, label):
    if type(value) is not expected_type:
        _fail(f"{label} must be an exact scalar")


def _preflight_shallow_schema(value):
    """Reject type/list bombs before canonicalization or provider access."""

    _require_exact_object(value, TOP_LEVEL_FIELDS, label="target-resolution top level")
    for key, expected_type in (
        ("artifact_kind", str),
        ("artifact_schema", str),
        ("artifact_schema_version", int),
        ("completion_scope", str),
        ("fixture_id", str),
        ("fixture_schema_version", int),
        ("g0_contract_frozen", bool),
        ("hypothesis_status", str),
    ):
        _require_scalar(value[key], expected_type, label=key)
    for key, fields in (
        ("authority", AUTHORITY_FIELDS),
        ("canonical_limits", CANONICAL_LIMIT_FIELDS),
        ("completion_claims", COMPLETION_FIELDS),
        ("dependency_direction_contract", DEPENDENCY_DIRECTION_FIELDS),
        ("orders", ORDERS_FIELDS),
        ("resolution_contract", RESOLUTION_CONTRACT_FIELDS),
        ("summary", SUMMARY_FIELDS),
    ):
        _require_exact_object(value[key], fields, label=key)

    if any(type(flag) is not bool for flag in value["authority"].values()):
        _fail("authority fields must be exact booleans")
    if any(type(flag) is not bool for flag in value["completion_claims"].values()):
        _fail("completion fields must be exact booleans")
    if any(
        type(flag) is not bool
        for flag in value["dependency_direction_contract"].values()
    ):
        _fail("dependency-direction fields must be exact booleans")
    for key, item in value["canonical_limits"].items():
        expected_type = str if key == "unicode_normalization" else (
            bool
            if key
            in {
                "framed_byte_cap_before_body_required",
                "null_float_or_negative_integer_allowed",
                "precanonical_expanded_structure_preflight_required",
                "self_hash_embedded",
            }
            else int
        )
        _require_scalar(item, expected_type, label="canonical limit")
    if any(type(item) is not int for item in value["summary"].values()):
        _fail("summary fields must be exact integers")

    _require_exact_list(value["input_binding_order"], 1, label="input binding order")
    _require_exact_list(value["input_bindings"], 60, label="input bindings")
    _require_exact_list(value["persona_summaries"], 20, label="persona summaries")
    _require_exact_list(value["remaining_blockers"], 7, label="remaining blockers")
    _require_exact_list(value["resolution_rows"], 2_100, label="resolution rows")
    _require_exact_list(
        value["resolution_contract"]["stratum_capability_counts_per_persona"],
        10,
        label="stratum capability table",
    )
    if any(type(item) is not str for item in value["input_binding_order"]):
        _fail("input binding order entries must be strings")
    if any(type(item) is not str for item in value["remaining_blockers"]):
        _fail("remaining blockers must be strings")
    _require_exact_list(value["orders"]["persona_order"], 20, label="persona order")
    if any(type(item) is not str for item in value["orders"]["persona_order"]):
        _fail("persona order entries must be strings")
    _require_scalar(value["orders"]["resolution_rows"], str, label="row order")
    _require_scalar(
        value["orders"]["within_class_matching"], str, label="matching order"
    )
    for key, item in value["resolution_contract"].items():
        if key == "stratum_capability_counts_per_persona":
            continue
        expected_type = str if key == "matching_algorithm" else bool
        _require_scalar(item, expected_type, label="resolution contract scalar")

    for binding in value["input_bindings"]:
        _require_exact_object(binding, INPUT_BINDING_FIELDS, label="input binding")
        for key in INPUT_BINDING_FIELDS - {
            "artifact_schema_version",
            "canonical_bytes",
            "fixture_schema_version",
        }:
            _require_scalar(binding[key], str, label="input binding field")
        for key in (
            "artifact_schema_version",
            "canonical_bytes",
            "fixture_schema_version",
        ):
            _require_scalar(binding[key], int, label="input binding integer")

    for summary in value["persona_summaries"]:
        _require_exact_object(
            summary, PERSONA_SUMMARY_FIELDS, label="persona summary"
        )
        _require_exact_list(
            summary["capability_class_counts"], 15, label="capability class counts"
        )
        _require_exact_list(summary["stratum_counts"], 10, label="stratum counts")
        _require_scalar(summary["persona_id"], str, label="summary persona ID")
        for key in (
            "abstract_companion_binding_count",
            "negative_query_count",
            "positive_query_count",
            "query_capability_bijection_count",
        ):
            _require_scalar(summary[key], int, label="persona summary count")
        for count_row in summary["capability_class_counts"] + summary["stratum_counts"]:
            _require_exact_object(
                count_row, frozenset({"count", "key"}), label="summary count row"
            )
            _require_scalar(count_row["count"], int, label="summary count")
            _require_scalar(count_row["key"], str, label="summary count key")

    for contract_row in value["resolution_contract"][
        "stratum_capability_counts_per_persona"
    ]:
        _require_exact_object(
            contract_row,
            frozenset({"capability_class_counts", "stratum_id"}),
            label="stratum capability row",
        )
        _require_scalar(contract_row["stratum_id"], str, label="stratum ID")
        counts = contract_row["capability_class_counts"]
        if type(counts) is not list or not 1 <= len(counts) <= 3:
            _fail("stratum capability class list cardinality differs")
        for count_row in counts:
            _require_exact_object(
                count_row,
                frozenset({"capability_class_key", "count"}),
                label="stratum capability class count",
            )
            _require_scalar(
                count_row["capability_class_key"], str, label="capability class key"
            )
            _require_scalar(count_row["count"], int, label="capability class count")

    for row in value["resolution_rows"]:
        _require_exact_object(row, RESOLUTION_ROW_FIELDS, label="resolution row")
        _require_exact_object(
            row["abstract_answer_contract"],
            ABSTRACT_ANSWER_FIELDS,
            label="abstract answer contract",
        )
        _require_exact_object(
            row["abstract_target"], ABSTRACT_TARGET_FIELDS, label="abstract target"
        )
        _require_exact_object(
            row["distractor_contract"], DISTRACTOR_FIELDS, label="distractor contract"
        )
        _require_exact_object(
            row["lifecycle_binding"],
            LIFECYCLE_BINDING_FIELDS,
            label="lifecycle binding",
        )
        _require_exact_object(
            row["oracle_evidence"], ORACLE_EVIDENCE_FIELDS, label="oracle evidence"
        )
        _require_exact_object(
            row["resolution_status"],
            RESOLUTION_STATUS_FIELDS,
            label="resolution status",
        )
        for key in (
            "evaluation_class",
            "persona_id",
            "query_key",
            "scenario_id",
            "semantic_match_rule_id",
            "stratum_id",
        ):
            _require_scalar(row[key], str, label="resolution row scalar")
        answer = row["abstract_answer_contract"]
        for key in ("answer_membership_key", "status"):
            _require_scalar(answer[key], str, label="abstract answer scalar")
        for key in ("expected_fact_ids", "expected_revision_chain_ids"):
            if type(answer[key]) is not list or len(answer[key]) > 1:
                _fail("abstract answer list exceeds exact local cardinality")
            if any(type(item) is not str for item in answer[key]):
                _fail("abstract answer list entries must be strings")
        for key in ABSTRACT_TARGET_FIELDS:
            _require_scalar(row["abstract_target"][key], str, label="abstract target")
        distractor = row["distractor_contract"]
        for key in (
            "distractor_fact_ids",
            "distractor_intent_keys",
            "distractor_logical_document_keys",
        ):
            if type(distractor[key]) is not list or len(distractor[key]) not in {0, 3}:
                _fail("distractor list cardinality differs")
            if any(type(item) is not str for item in distractor[key]):
                _fail("distractor list entries must be strings")
        _require_exact_list(
            distractor["mapped_source_intent_keys"],
            0,
            label="mapped distractor source intents",
        )
        _require_scalar(
            distractor["per_query_answer_fact_disjoint"],
            bool,
            label="distractor disjointness flag",
        )
        _require_scalar(
            distractor["source_mapping_resolved"],
            bool,
            label="distractor source-mapping flag",
        )
        _require_scalar(
            distractor["reference_kind"], str, label="distractor reference kind"
        )
        _require_scalar(
            distractor["source_mapping_status"],
            str,
            label="distractor source-mapping status",
        )
        lifecycle_binding = row["lifecycle_binding"]
        if (
            type(lifecycle_binding["required_event_profile_keys"]) is not list
            or len(lifecycle_binding["required_event_profile_keys"]) > 7
        ):
            _fail("required event profile list exceeds its cap")
        if any(
            type(item) is not str
            for item in lifecycle_binding["required_event_profile_keys"]
        ):
            _fail("required event profile keys must be strings")
        for key in LIFECYCLE_BINDING_FIELDS - {
            "companion",
            "required_event_profile_keys",
        }:
            _require_scalar(
                lifecycle_binding[key], str, label="lifecycle binding scalar"
            )
        companion = lifecycle_binding["companion"]
        if type(companion) is not dict or frozenset(companion) not in {
            frozenset({"status"}),
            frozenset(
                {
                    "companion_requirement_key",
                    "rendition_group_key",
                    "source_intent_key",
                    "status",
                }
            ),
        }:
            _fail("companion shallow schema differs")
        if any(type(item) is not str for item in companion.values()):
            _fail("companion fields must be strings")
        evidence = row["oracle_evidence"]
        for key in ORACLE_EVIDENCE_FIELDS - {"event_template_rows"}:
            _require_scalar(evidence[key], str, label="oracle evidence scalar")
        event_rows = row["oracle_evidence"]["event_template_rows"]
        if type(event_rows) is not list or len(event_rows) > 2:
            _fail("oracle event-template list exceeds its cap")
        for event_row in event_rows:
            _require_exact_object(
                event_row,
                frozenset({"field", "template_key"}),
                label="event template row",
            )
            if any(type(item) is not str for item in event_row.values()):
                _fail("event template fields must be strings")
        if any(
            type(flag) is not bool for flag in row["resolution_status"].values()
        ):
            _fail("resolution status fields must be booleans")


def _json_string_byte_count(value):
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail("expanded preflight string is not valid UTF-8")
    if len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        _fail("expanded preflight string exceeds its byte cap")
    total = 2
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\"}:
            total += 2
        elif codepoint < 0x20:
            total += 6
        else:
            total += len(character.encode("utf-8", "strict"))
    return total


def _expanded_preflight(value):
    state = {"bytes": 0, "nodes": 0, "maximum_depth": 0}

    def add_bytes(count):
        state["bytes"] += count
        if state["bytes"] > MAX_ARTIFACT_BYTES:
            _fail("expanded structure exceeds the canonical byte cap")

    def walk(item, depth):
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail("expanded structure exceeds the nesting-depth cap")
        state["maximum_depth"] = max(state["maximum_depth"], depth)
        state["nodes"] += 1
        if state["nodes"] > MAX_EXPANDED_NODE_COUNT:
            _fail("expanded structure exceeds the node-count cap")
        if type(item) is bool:
            add_bytes(4 if item else 5)
        elif type(item) is int:
            if item < 0 or item > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail("expanded structure integer is outside the canonical range")
            add_bytes(len(str(item)))
        elif type(item) is str:
            add_bytes(_json_string_byte_count(item))
        elif type(item) is list:
            add_bytes(2 + max(0, len(item) - 1))
            for child in item:
                walk(child, depth + 1)
        elif type(item) is dict:
            add_bytes(2 + max(0, len(item) - 1) + len(item))
            for key, child in item.items():
                if type(key) is not str:
                    _fail("expanded structure object key is not a string")
                state["nodes"] += 1
                if state["nodes"] > MAX_EXPANDED_NODE_COUNT:
                    _fail("expanded structure exceeds the node-count cap")
                add_bytes(_json_string_byte_count(key))
                walk(child, depth + 1)
        else:
            _fail("expanded structure contains a non-canonical value type")

    try:
        walk(value, 0)
    except RecursionError:
        _fail("expanded structure recursion exceeds the depth cap")
    return state


def preflight_query_history_target_resolution(value):
    """Run bounded shallow and expanded checks without reading dependencies."""

    try:
        _preflight_shallow_schema(value)
        state = _expanded_preflight(value)
    except PersonaV2QueryHistoryTargetResolutionValidationError:
        raise
    except (
        IndexError,
        KeyError,
        MemoryError,
        RecursionError,
        RuntimeError,
        TypeError,
        UnicodeError,
    ):
        _fail("candidate changed or became invalid during structural preflight")
    return copy.deepcopy(state)


def _snapshot_candidate(value):
    preflight_query_history_target_resolution(value)
    try:
        detached = copy.deepcopy(value)
    except (RecursionError, MemoryError, RuntimeError, TypeError):
        _fail("candidate could not be copied within structural bounds")
    state = preflight_query_history_target_resolution(detached)
    raw = _canonical(detached)
    if state["bytes"] < len(raw):
        _fail("expanded byte preflight underestimated canonical bytes")
    return detached, raw


def _canonical(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 query history target resolution",
            max_bytes=MAX_ARTIFACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_duplicate_pairs(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail("canonical JSON contains a duplicate key")
        value[key] = item
    return value


def _reject_float(_value):
    _fail("canonical JSON floating-point values are forbidden")


def _reject_constant(_value):
    _fail("canonical JSON non-finite numbers are forbidden")


def strict_load_canonical_json_bytes(raw):
    """Parse one bounded, duplicate-free, byte-canonical artifact body."""

    if type(raw) is not bytes:
        _fail("canonical body must be exact built-in bytes")
    if len(raw) > MAX_ARTIFACT_BYTES:
        _fail("canonical body exceeds its pre-parse byte cap")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2QueryHistoryTargetResolutionValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail("canonical body is not strict UTF-8 JSON")
    if type(value) is not dict:
        _fail("canonical body must decode to an object")
    preflight_query_history_target_resolution(value)
    if not hmac.compare_digest(_canonical(value), raw):
        _fail("body bytes are valid JSON but not exact canonical JSON")
    return value


def _reject_forbidden_keys(value):
    if type(value) is list:
        for item in value:
            _reject_forbidden_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _FORBIDDEN_EXACT_KEYS:
            _fail("artifact contains a prohibited concrete identity field")
        _reject_forbidden_keys(item)


def _dependency_raws_from_live():
    queries = query_intent.build_query_intent_suite()
    oracles = semantic_oracle.build_semantic_oracle_suite()
    lifecycles = [
        lifecycle.build_source_matched_lifecycle_persona(persona_id)
        for persona_id in envelope.PERSONA_IDS
    ]
    expected_personas = list(envelope.PERSONA_IDS)
    for values in (queries, oracles, lifecycles):
        if (
            type(values) is not list
            or len(values) != 20
            or [row.get("persona_id") for row in values] != expected_personas
        ):
            _fail("upstream dependency persona order or cardinality drifted")
    return (
        tuple(query_intent.canonical_json_bytes(value) for value in queries),
        tuple(semantic_oracle.canonical_json_bytes(value) for value in oracles),
        tuple(lifecycle.canonical_json_bytes(value) for value in lifecycles),
    )


@functools.lru_cache(maxsize=1)
def _trusted_dependency_raws():
    # Bytes and tuples are the only cached trust state; callers always receive
    # newly decoded objects.
    return _dependency_raws_from_live()


def _decode_dependency_raws(raws):
    query_raws, oracle_raws, lifecycle_raws = raws
    return (
        [json.loads(raw.decode("utf-8", "strict")) for raw in query_raws],
        [json.loads(raw.decode("utf-8", "strict")) for raw in oracle_raws],
        [json.loads(raw.decode("utf-8", "strict")) for raw in lifecycle_raws],
    )


def _snapshot_dependencies(dependency_observer=None):
    trusted = _trusted_dependency_raws()
    opening = _dependency_raws_from_live()
    if not _strict_equal(opening, trusted):
        _fail("live upstream dependency differs from immutable trust snapshot")
    detached = _decode_dependency_raws(opening)
    if dependency_observer is not None:
        if not callable(dependency_observer):
            _fail("dependency observer must be callable")
        live = _decode_dependency_raws(opening)
        dependency_observer(*live)
        observed = (
            tuple(query_intent.canonical_json_bytes(value) for value in live[0]),
            tuple(semantic_oracle.canonical_json_bytes(value) for value in live[1]),
            tuple(lifecycle.canonical_json_bytes(value) for value in live[2]),
        )
        if not _strict_equal(observed, opening):
            _fail("dependency changed during validation snapshot")
    closing = _dependency_raws_from_live()
    if not _strict_equal(closing, opening) or not _strict_equal(closing, trusted):
        _fail("upstream dependency changed between validation reads")
    return detached


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


def _join_query_oracle(query_value, oracle_value):
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
        _fail("query/oracle dependency join is not exact")
    return queries, by_query


def _revision_ids(oracle_row):
    membership = oracle_row["abstract_answer_membership"]
    return [] if membership == [] else membership["expected_revision_chain_ids"]


def _semantic_class(query_row, oracle_row):
    stratum = query_row["stratum_id"]
    revisions = _revision_ids(oracle_row)
    if stratum == "purged-negative":
        if oracle_row["expected_empty"] is not True or revisions:
            _fail("negative semantic target is not empty")
        return "purged-negative", "purged-negative-empty-answer"
    if query_row["expected_empty"] is not False or oracle_row["expected_empty"] is not False:
        _fail("positive semantic target is unexpectedly empty")
    current_suffix = {
        "current-fact": "default",
        "cross-format-fact": "cross-format",
        "locale-language-fact": "locale",
    }
    if stratum in current_suffix:
        suffix = current_suffix[stratum]
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
                _fail("same-scope rename unexpectedly has revision semantics")
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
        _fail("rename/move semantic target lacks an exact operation")
    direct = {
        "old-wording": "old-wording-history",
        "locale-language-history": "locale-history",
        "deleted": "final-deleted",
        "restored": "current-restored",
        "locale-language-lifecycle": "archive-history",
    }
    if stratum not in direct:
        _fail("semantic target uses an unsupported stratum")
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


def _independent_match(persona_id, pairs, capabilities):
    query_by_class = {}
    capability_by_class = {}
    rules = {}
    for query_row, oracle_row in pairs:
        class_key, rule = _semantic_class(query_row, oracle_row)
        query_by_class.setdefault(class_key, []).append(query_row)
        rules[query_row["query_key"]] = rule
    for row in capabilities:
        capability_by_class.setdefault(row["capability_class_key"], []).append(row)
    counts = {
        class_key: count
        for _stratum, class_rows in STRATUM_CAPABILITY_COUNTS
        for class_key, count in class_rows
    }
    if set(query_by_class) != set(counts) or set(capability_by_class) != set(counts):
        _fail("semantic class domains differ")
    for class_key, count in counts.items():
        if len(query_by_class[class_key]) != count or len(
            capability_by_class[class_key]
        ) != count:
            _fail("semantic class exact count table differs")
    result = {}
    for class_key in sorted(counts, key=_ascii):
        left = sorted(
            query_by_class[class_key],
            key=lambda row: hashlib.sha256(
                ("left-order\x00" + row["target_intent_key"]).encode("ascii")
            ).digest(),
        )
        right = capability_by_class[class_key]
        right_owner = {}

        def augment(query_row, seen):
            candidates = sorted(
                right,
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

        if not all(augment(query_row, set()) for query_row in left):
            _fail("semantic bipartite matching is incomplete")
        by_key = {row["capability_key"]: row for row in right}
        for capability_key, query_row in right_owner.items():
            result[query_row["query_key"]] = (
                by_key[capability_key],
                rules[query_row["query_key"]],
            )
    if len(result) != 105:
        _fail("semantic bipartite matching is not bijective")
    return result


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
        "expected_revision_chain_ids": list(membership["expected_revision_chain_ids"]),
        "status": "abstract-oracle-membership-only",
    }


def _distractor_contract(oracle_row):
    distractors = oracle_row.get("distractors", [])
    answer = _answer_contract(oracle_row)
    fact_ids = [row["distractor_fact_id"] for row in distractors]
    intent_keys = [row["distractor_intent_key"] for row in distractors]
    logical_keys = [row["distractor_logical_document_key"] for row in distractors]
    if set(answer["expected_fact_ids"]) & set(fact_ids):
        _fail("answer fact overlaps a same-query distractor fact")
    if len(intent_keys) != len(set(intent_keys)) or len(logical_keys) != len(set(logical_keys)):
        _fail("same-query distractor keys are not unique")
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


def _event_template_rows(evidence):
    return [
        {"field": key, "template_key": evidence[key]}
        for key in sorted(evidence, key=_ascii)
        if key.endswith("_event_template_key")
    ]


def _companion_contract(capability, companions):
    row = companions.get(capability["capability_key"])
    if row is None:
        return {"status": "not-required"}
    if row["intent_key"] == capability["intent_key"]:
        _fail("primary and companion source intents overlap")
    return {
        "companion_requirement_key": row["companion_requirement_key"],
        "rendition_group_key": row["rendition_group_key"],
        "source_intent_key": row["intent_key"],
        "status": "source-matched-abstract-companion",
    }


def _expected_rows(persona_id, query_value, oracle_value, lifecycle_value):
    queries, oracle_by_query = _join_query_oracle(query_value, oracle_value)
    capabilities = lifecycle_value["primary_match_rows"]
    if len(capabilities) != 105 or len({row["capability_key"] for row in capabilities}) != 105:
        _fail("lifecycle primary capability inventory is not exact")
    pairs = [(row, oracle_by_query[row["query_key"]]) for row in queries]
    matches = _independent_match(persona_id, pairs, capabilities)
    companions = {
        row["primary_capability_key"]: row
        for row in lifecycle_value["companion_match_rows"]
    }
    if len(companions) != 10:
        _fail("lifecycle companion inventory is not exact")
    primary_source_intents = {row["intent_key"] for row in capabilities}
    companion_source_intents = {
        row["intent_key"] for row in companions.values()
    }
    if (
        len(primary_source_intents) != 105
        or len(companion_source_intents) != 10
        or primary_source_intents & companion_source_intents
    ):
        _fail("primary and companion source-intent domains overlap")
    target_intents = {row["target_intent_key"] for row in queries}
    target_documents = {row["target_logical_document_key"] for row in queries}
    distractor_intents = {
        item["distractor_intent_key"]
        for row in oracle_value["positive_oracle_rows"]
        for item in row["distractors"]
    }
    distractor_documents = {
        item["distractor_logical_document_key"]
        for row in oracle_value["positive_oracle_rows"]
        for item in row["distractors"]
    }
    if target_intents & distractor_intents or target_documents & distractor_documents:
        _fail("target and distractor abstract key domains overlap")
    if target_intents & (primary_source_intents | companion_source_intents):
        _fail("query targets overlap lifecycle source-intent keys")
    result = []
    for query_row in sorted(queries, key=lambda row: _ascii(row["query_key"])):
        oracle_row = oracle_by_query[query_row["query_key"]]
        capability, rule = matches[query_row["query_key"]]
        evidence = oracle_row["evidence_contract"]
        result.append(
            {
                "abstract_answer_contract": _answer_contract(oracle_row),
                "abstract_target": {
                    "intent_key": query_row["target_intent_key"],
                    "logical_document_key": query_row["target_logical_document_key"],
                },
                "distractor_contract": _distractor_contract(oracle_row),
                "evaluation_class": query_row["evaluation_class"],
                "lifecycle_binding": {
                    "capability_class_key": capability["capability_class_key"],
                    "capability_key": capability["capability_key"],
                    "companion": _companion_contract(capability, companions),
                    "logical_document_slot_key": capability[
                        "lifecycle_logical_document_slot_key"
                    ],
                    "primary_source_intent_key": capability["intent_key"],
                    "required_event_profile_keys": list(
                        CLASS_EVENT_PROFILES[capability["capability_class_key"]]
                    ),
                },
                "oracle_evidence": {
                    "evidence_kind": evidence["evidence_kind"],
                    "event_template_rows": _event_template_rows(evidence),
                    "operation_kind": evidence.get("operation_kind", "not-applicable"),
                    "required_evidence_state": query_row["required_evidence_state"],
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
                "semantic_match_rule_id": rule,
                "stratum_id": query_row["stratum_id"],
            }
        )
    if len({row["query_key"] for row in result}) != 105 or len(
        {row["lifecycle_binding"]["capability_key"] for row in result}
    ) != 105:
        _fail("expected rows are not a query/capability bijection")
    return result


def _count_rows(rows, path):
    counts = {}
    for row in rows:
        value = row
        for key in path:
            value = value[key]
        counts[value] = counts.get(value, 0) + 1
    return [
        {"count": counts[key], "key": key}
        for key in sorted(counts, key=_ascii)
    ]


def _expected_artifact(query_values, oracle_values, lifecycle_values):
    bindings = []
    rows = []
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
        persona_rows = _expected_rows(
            persona_id, query_value, oracle_value, lifecycle_value
        )
        rows.extend(persona_rows)
        persona_summaries.append(
            {
                "abstract_companion_binding_count": sum(
                    row["lifecycle_binding"]["companion"]["status"]
                    == "source-matched-abstract-companion"
                    for row in persona_rows
                ),
                "capability_class_counts": _count_rows(
                    persona_rows, ("lifecycle_binding", "capability_class_key")
                ),
                "negative_query_count": sum(
                    row["evaluation_class"] == "purged-negative"
                    for row in persona_rows
                ),
                "persona_id": persona_id,
                "positive_query_count": sum(
                    row["evaluation_class"] == "positive-recall"
                    for row in persona_rows
                ),
                "query_capability_bijection_count": len(persona_rows),
                "stratum_counts": _count_rows(persona_rows, ("stratum_id",)),
            }
        )
    total = 105 * len(envelope.PERSONA_IDS)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
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
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_ARTIFACT_BYTES,
            "max_expanded_node_count": MAX_EXPANDED_NODE_COUNT,
            "max_input_binding_count": 60,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_resolution_row_count": total,
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
        "hypothesis_status": "authored-semantic-class-resolution-not-observed-execution",
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
        "resolution_rows": rows,
        "summary": {
            "abstract_companion_binding_count": sum(
                row["lifecycle_binding"]["companion"]["status"]
                == "source-matched-abstract-companion"
                for row in rows
            ),
            "abstract_distractor_reference_count": sum(
                len(row["distractor_contract"]["distractor_fact_ids"])
                for row in rows
            ),
            "distinct_distractor_source_count": 0,
            "input_binding_count": len(bindings),
            "negative_query_count": sum(
                row["evaluation_class"] == "purged-negative" for row in rows
            ),
            "persona_count": len(persona_summaries),
            "positive_query_count": sum(
                row["evaluation_class"] == "positive-recall" for row in rows
            ),
            "query_capability_bijection_count": len(rows),
        },
    }


def _validate(value, *, dependency_observer=None):
    detached_value, opening_value_raw = _snapshot_candidate(value)
    _reject_forbidden_keys(detached_value)
    _require_frozen_raw(opening_value_raw, label="candidate target resolution")
    query_values, oracle_values, lifecycle_values = _snapshot_dependencies(
        dependency_observer
    )
    expected = _expected_artifact(
        query_values, oracle_values, lifecycle_values
    )
    expected_raw = _canonical(expected)
    _require_frozen_raw(expected_raw, label="independent target resolution")
    if len(expected_raw) > TARGET_ARTIFACT_BYTES:
        _fail("independent target resolution exceeds its target byte budget")
    if not hmac.compare_digest(opening_value_raw, expected_raw):
        _fail("target resolution differs from independent reconstruction")
    _closing_value, closing_value_raw = _snapshot_candidate(value)
    _require_frozen_raw(closing_value_raw, label="closing target resolution")
    if not hmac.compare_digest(closing_value_raw, opening_value_raw):
        _fail("target resolution changed during validation")
    return True


def validate_query_history_target_resolution(value):
    """Authenticate one in-memory target-resolution candidate."""

    return _validate(value)


def validate_query_history_target_resolution_bytes(raw):
    """Strictly parse and authenticate one canonical JSON body."""

    value = strict_load_canonical_json_bytes(raw)
    return validate_query_history_target_resolution(value)


__all__ = [
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_EXPANDED_NODE_COUNT",
    "MAX_ARTIFACT_BYTES",
    "PersonaV2QueryHistoryTargetResolutionValidationError",
    "preflight_query_history_target_resolution",
    "strict_load_canonical_json_bytes",
    "validate_query_history_target_resolution",
    "validate_query_history_target_resolution_bytes",
]
