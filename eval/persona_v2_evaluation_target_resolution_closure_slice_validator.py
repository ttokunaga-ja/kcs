"""Producer-independent validator for the evaluation closure slice.

The slice producer is intentionally not imported.  Fast validation treats the
five frozen body pins as accepted trust boundaries and independently rebuilds
the compact descriptor.  The opt-in full entry point traverses all 253
projection bodies exactly once through the request-only corpus closure,
validates target resolution once, and replays the semantic-feasibility
producer plus its independent reconstruction once.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_corpus_input_closure_v3 as corpus_closure
    from . import persona_v2_corpus_semantic_namespace_v3 as namespace
    from . import persona_v2_query_history_semantic_resolution_feasibility as feasibility
    from . import (
        persona_v2_query_history_semantic_resolution_feasibility_validator
        as feasibility_validator,
    )
    from . import persona_v2_query_history_target_resolution as resolution
    from . import persona_v2_query_history_target_resolution_validator as resolution_validator
    from . import persona_v2_semantic_projection_complete_inventory as complete
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_corpus_input_closure_v3 as corpus_closure
    import persona_v2_corpus_semantic_namespace_v3 as namespace
    import persona_v2_query_history_semantic_resolution_feasibility as feasibility
    import persona_v2_query_history_semantic_resolution_feasibility_validator
    import persona_v2_query_history_target_resolution as resolution
    import persona_v2_query_history_target_resolution_validator as resolution_validator
    import persona_v2_semantic_projection_complete_inventory as complete
    feasibility_validator = (
        persona_v2_query_history_semantic_resolution_feasibility_validator
    )


ARTIFACT_SCHEMA = (
    "kio.persona.pc-evaluation-target-resolution-closure-slice/v1"
)
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = (
    "persona-pc-v2-non-authorizing-evaluation-target-resolution-closure-slice"
)

MAX_MANIFEST_BYTES = 256 * 2**10
TARGET_MANIFEST_BYTES = 128 * 2**10
MAX_DIRECT_DEPENDENCY_COUNT = 5
MAX_TRANSITIVE_BINDING_COUNT = 60
MAX_PERSONA_COUNT = 20
MAX_QUERY_MAPPING_COUNT = 2_100
MAX_EXPANDED_NODE_COUNT = 100_000
MAX_DIRECT_DESCRIPTOR_BYTES = 16 * 2**20
MAX_TRANSITIVE_PROVIDER_BYTES = 60 * 2**20

EXPECTED_CANONICAL_BYTES = 16_735
EXPECTED_SHA256 = (
    "1d2ff1822bc3e15a7c3d9e58ce55eb1908340bc3a1c445fd566e0539b25ff282"
)

NAMESPACE_CANONICAL_BYTES = 161_665
NAMESPACE_SHA256 = (
    "bbb0941e7e640130fb57e07c1301991679c2dea80407573b82e9ef575b074637"
)
COMPLETE_INVENTORY_CANONICAL_BYTES = 697_466
COMPLETE_INVENTORY_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
)
ORDERED_PROJECTION_PINS_SHA256 = (
    "f524ddcccdd89a216b87d2ad8f98076c8eacabbc258e7b68d514162764a3a97c"
)
TARGET_RESOLUTION_CANONICAL_BYTES = 4_478_576
TARGET_RESOLUTION_SHA256 = (
    "8beed1ca21ebe80e029bcd003795306086514adcd852b98a9eed334fcd73f4ff"
)
REQUEST_ONLY_CORPUS_CLOSURE_CANONICAL_BYTES = 7_590
REQUEST_ONLY_CORPUS_CLOSURE_SHA256 = (
    "cd2dbcf3829beb13c2278d93f2d410df8f99611dabc7a3e4c6ce579f671a53ec"
)
SEMANTIC_FEASIBILITY_CANONICAL_BYTES = 40_947
SEMANTIC_FEASIBILITY_SHA256 = (
    "22e8e9b2af457ebe35c4655c49435eea72955cc753d5bd132c5bc469ce3aba27"
)
TRANSITIVE_BINDING_ROWS_CANONICAL_BYTES = 24_961
TRANSITIVE_BINDING_ROWS_SHA256 = (
    "d611ac23722a087cefc4051f1b290e6f7cd18dd699ff657a7f92eed05ac9289e"
)
TRANSITIVE_CUMULATIVE_CANONICAL_BYTES = 7_385_300
TRANSITIVE_ROLE_TOTALS = (
    ("evaluation-query-intent", 20, 1_320_327),
    ("evaluation-semantic-oracle", 20, 4_001_640),
    (
        "query-independent-lifecycle-capability-source-match",
        20,
        2_063_333,
    ),
)
TRANSITIVE_BINDING_ORDER = (
    "persona-then-query-intent-semantic-oracle-source-matched-lifecycle"
)
DIRECT_DEPENDENCY_ORDER = (
    "corpus-semantic-namespace",
    "complete-semantic-projection-inventory",
    "query-history-target-resolution",
    "request-only-corpus-input-closure",
    "query-history-semantic-resolution-feasibility-audit",
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_history_receipts_attested",
        "authorizes_compiled_relevance",
        "authorizes_corpus_namespace",
        "authorizes_evaluation_input_closure",
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
        "authoritative_corpus_input_closure_available",
        "authoritative_corpus_input_closure_bound",
        "authorizes_request_only_corpus_closure_as_complete",
        "exact_source_semantic_resolution_available",
        "final_identity_relevance_available",
    }
)

TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "corpus_context_summary",
        "dependency_direction_contract",
        "dependency_order",
        "dependency_pins",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "missing_required_full_closure_dependencies",
        "orders",
        "persona_coverage",
        "remaining_blockers",
        "summary",
        "transitive_resolution_input_commitment",
        "unresolved_distractor_sources",
        "unresolved_target_semantics",
    }
)
CANONICAL_LIMIT_FIELDS = frozenset(
    {
        "direct_dependency_bodies_embedded",
        "framed_byte_cap_before_body_required",
        "max_direct_dependency_count",
        "max_direct_descriptor_bytes",
        "max_expanded_node_count",
        "max_manifest_bytes",
        "max_nesting_depth",
        "max_persona_count",
        "max_query_mapping_count",
        "max_string_bytes",
        "max_transitive_binding_count",
        "max_transitive_provider_bytes",
        "null_float_or_negative_integer_allowed",
        "precanonical_expanded_structure_preflight_required",
        "self_hash_embedded",
        "target_manifest_bytes",
        "unicode_normalization",
    }
)
COMPLETION_FIELDS = frozenset(
    {
        "abstract_distractor_requirements_bound",
        "all_20_persona_summaries_bound",
        "all_2100_query_capability_mappings_bound",
        "authoritative_corpus_input_closure_bound",
        "complete_inventory_evidence_pin_bound",
        "compiled_history_event_bindings_present",
        "corpus_namespace_pin_bound",
        "distractor_source_mapping_resolved",
        "exact_source_semantic_query_history_resolution_bound",
        "final_identity_relevance_present",
        "namespace_query_isolation_bound",
        "positive_independent_review_receipt_bound",
        "production_evaluation_input_closure_complete",
        "query_instances_rendered",
        "query_spec_hashed_by_g0",
        "request_only_corpus_input_closure_bound",
        "semantic_resolution_feasibility_audit_bound",
        "source_fact_equality_proved",
        "source_language_equality_proved",
        "source_topic_equality_proved",
        "target_primary_companion_distractor_disjointness_proved",
        "target_resolution_pin_bound",
        "transitive_60_dependency_commitment_bound",
    }
)
PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "dependency_id",
        "dependency_role",
        "fixture_id",
        "fixture_schema_version",
        "sha256",
    }
)
CORPUS_CONTEXT_FIELDS = frozenset(
    {
        "active_g0_unresolved_count",
        "authoritative_corpus_input_closure_available",
        "authoritative_corpus_input_closure_bound",
        "complete_inventory_evidence_bound",
        "cumulative_external_projection_bytes",
        "external_projection_bodies_embedded",
        "namespace_entry_count",
        "namespace_issued",
        "ordered_projection_pins_sha256",
        "positive_review_receipt_count",
        "projection_class_count",
        "request_only_corpus_input_closure_authoritative",
        "request_only_corpus_input_closure_bound",
        "request_only_corpus_input_closure_candidate_available",
        "request_only_corpus_input_closure_complete",
        "required_positive_review_receipt_count",
    }
)
DEPENDENCY_DIRECTION_FIELDS = frozenset(
    {
        "complete_inventory_is_validation_evidence_not_semantic_identity",
        "corpus_namespace_may_import_this_slice",
        "corpus_renderer_may_import_this_slice",
        "future_full_evaluation_closure_may_bind_this_slice",
        "positive_review_receipts_are_transitive_authoritative_closure_inputs",
        "query_or_oracle_change_may_change_corpus_namespace",
        "query_or_oracle_change_may_change_evaluation_slice",
        "query_or_oracle_change_may_change_source_id_preimage",
        "request_only_corpus_closure_is_evidence_not_authority",
        "semantic_feasibility_audit_is_blocker_evidence_not_resolution_v2",
        "slice_is_downstream_of_namespace_and_target_resolution",
    }
)
ORDERS_FIELDS = frozenset(
    {"direct_dependencies", "persona_coverage", "transitive_bindings"}
)
PERSONA_FIELDS = frozenset(
    {
        "abstract_companion_binding_count",
        "abstract_distractor_reference_count",
        "mapped_distinct_distractor_source_count",
        "negative_query_count",
        "persona_id",
        "positive_query_count",
        "query_capability_mapping_count",
        "required_distinct_distractor_source_count",
    }
)
ROLE_TOTAL_FIELDS = frozenset(
    {"body_count", "cumulative_canonical_bytes", "dependency_role"}
)
TRANSITIVE_FIELDS = frozenset(
    {
        "binding_count",
        "binding_order",
        "binding_rows_canonical_bytes",
        "binding_rows_sha256",
        "bodies_embedded",
        "cumulative_canonical_bytes",
        "role_totals",
    }
)
SUMMARY_FIELDS = frozenset(
    {
        "abstract_companion_binding_count",
        "abstract_distractor_reference_count",
        "dependency_pin_count",
        "mapped_distinct_distractor_source_count",
        "negative_query_count",
        "persona_count",
        "positive_query_count",
        "query_capability_mapping_count",
        "required_distinct_distractor_source_count",
        "transitive_binding_count",
    }
)
UNRESOLVED_TARGET_FIELDS = frozenset(
    {
        "all_condition_exact_resolution_proved_count",
        "all_condition_exact_resolution_status",
        "baseline_aligned_contributor_target_count",
        "baseline_live_join_examined_contributor_target_count",
        "baseline_mismatched_contributor_target_count",
        "checkpoint_selector_effective_membership_compiled_count",
        "compiled_event_id_binding_count",
        "contributor_target_count",
        "final_materialization_id_binding_count",
        "final_source_id_binding_count",
        "inference_from_abstract_or_base_membership_allowed",
        "incidental_target_count",
        "lifecycle_capability_mapping_count",
        "negative_expected_empty_count",
        "positive_answer_requirement_count",
        "query_history_target_resolution_v2_issued",
        "raw_hash_section_binding_count",
        "resolution_target_count",
        "revision_join_unknown_contributor_target_count",
    }
)
UNRESOLVED_DISTRACTOR_FIELDS = frozenset(
    {
        "abstract_distinct_distractor_intent_key_count",
        "abstract_distinct_distractor_logical_document_key_count",
        "abstract_distractor_reference_count",
        "distractor_nonanswer_fact_source_proved_count",
        "distractor_same_language_source_proved_count",
        "distractor_same_topic_source_proved_count",
        "mapped_distinct_distractor_source_count",
        "mapped_source_intent_keys_embedded",
        "maximum_distinct_distractor_source_candidate_count_before_language_filter",
        "maximum_distractor_mapping_shortfall_count",
        "per_query_abstract_answer_distractor_fact_disjoint",
        "positive_query_count",
        "required_distinct_distractor_source_count_per_persona",
        "required_distinct_distractor_source_count_suite",
        "source_mapping_resolved",
        "target_primary_companion_distractor_source_domains_disjoint",
    }
)


class PersonaV2EvaluationTargetResolutionClosureSliceValidationError(ValueError):
    """Raised when the slice cannot be independently authenticated."""


def _fail(message):
    raise PersonaV2EvaluationTargetResolutionClosureSliceValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    """Return the validator-owned optional golden after strict validation."""

    byte_count_is_set = EXPECTED_CANONICAL_BYTES is not None
    digest_is_set = EXPECTED_SHA256 is not None
    if byte_count_is_set != digest_is_set:
        _fail("evaluation closure golden must be entirely unset or entirely set")
    if not byte_count_is_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= TARGET_MANIFEST_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(
            character not in "0123456789abcdef"
            for character in EXPECTED_SHA256
        )
    ):
        _fail("evaluation closure golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_expected_raw(raw):
    if type(raw) is not bytes:
        _fail("evaluation closure candidate must be exact bytes")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("evaluation closure candidate differs from its frozen golden")
    return raw


_GOLDEN_NOT_PROVIDED = object()


def _require_producer_golden_parity(producer_expected):
    validator_expected = _expected_golden()
    if producer_expected is _GOLDEN_NOT_PROVIDED:
        _fail("producer evaluation closure golden was not supplied")
    if producer_expected is not None and (
        type(producer_expected) is not tuple
        or len(producer_expected) != 2
        or type(producer_expected[0]) is not int
        or type(producer_expected[0]) is bool
        or not 1 <= producer_expected[0] <= TARGET_MANIFEST_BYTES
        or type(producer_expected[1]) is not str
        or len(producer_expected[1]) != 64
        or any(
            character not in "0123456789abcdef"
            for character in producer_expected[1]
        )
    ):
        _fail("producer evaluation closure golden is invalid")
    if not _strict_equal(producer_expected, validator_expected):
        _fail("producer and validator evaluation closure goldens differ")
    return validator_expected


def _strict_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return len(left) == len(right) and all(
            key in right and _strict_equal(left[key], right[key])
            for key in left
        )
    if type(left) is list:
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


def _require_object(value, fields, *, label):
    if type(value) is not dict:
        _fail(f"{label} shallow schema differs")
    if len(value) != len(fields) or any(key not in value for key in fields):
        _fail(f"{label} shallow schema differs")


def _require_list(value, length, *, label):
    if type(value) is not list or len(value) != length:
        _fail(f"{label} shallow cardinality differs")


def _require_scalar(value, expected_type, *, label):
    if type(value) is not expected_type:
        _fail(f"{label} must be an exact scalar")


def _preflight_shallow(value):
    _require_object(value, TOP_LEVEL_FIELDS, label="closure slice top level")
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
        ("corpus_context_summary", CORPUS_CONTEXT_FIELDS),
        ("dependency_direction_contract", DEPENDENCY_DIRECTION_FIELDS),
        ("orders", ORDERS_FIELDS),
        ("summary", SUMMARY_FIELDS),
        ("transitive_resolution_input_commitment", TRANSITIVE_FIELDS),
        ("unresolved_distractor_sources", UNRESOLVED_DISTRACTOR_FIELDS),
        ("unresolved_target_semantics", UNRESOLVED_TARGET_FIELDS),
    ):
        _require_object(value[key], fields, label=key)

    if any(type(flag) is not bool for flag in value["authority"].values()):
        _fail("authority fields must be exact booleans")
    if any(
        type(flag) is not bool for flag in value["completion_claims"].values()
    ):
        _fail("completion fields must be exact booleans")
    if any(
        type(flag) is not bool
        for flag in value["dependency_direction_contract"].values()
    ):
        _fail("dependency-direction fields must be exact booleans")

    _require_list(value["dependency_order"], 5, label="dependency order")
    _require_list(value["dependency_pins"], 5, label="dependency pins")
    _require_list(
        value["missing_required_full_closure_dependencies"],
        5,
        label="missing full-closure dependencies",
    )
    _require_list(value["persona_coverage"], 20, label="persona coverage")
    _require_list(value["remaining_blockers"], 8, label="remaining blockers")
    for key in (
        "dependency_order",
        "missing_required_full_closure_dependencies",
        "remaining_blockers",
    ):
        if any(type(item) is not str for item in value[key]):
            _fail(f"{key} entries must be strings")

    for pin in value["dependency_pins"]:
        _require_object(pin, PIN_FIELDS, label="dependency pin")
        for key in PIN_FIELDS - {
            "artifact_schema_version",
            "canonical_bytes",
            "fixture_schema_version",
        }:
            _require_scalar(pin[key], str, label="dependency pin field")
        for key in (
            "artifact_schema_version",
            "canonical_bytes",
            "fixture_schema_version",
        ):
            _require_scalar(pin[key], int, label="dependency pin integer")

    for row in value["persona_coverage"]:
        _require_object(row, PERSONA_FIELDS, label="persona coverage row")
        _require_scalar(row["persona_id"], str, label="persona ID")
        for key in PERSONA_FIELDS - {"persona_id"}:
            _require_scalar(row[key], int, label="persona count")

    transitive = value["transitive_resolution_input_commitment"]
    _require_list(transitive["role_totals"], 3, label="transitive role totals")
    for row in transitive["role_totals"]:
        _require_object(row, ROLE_TOTAL_FIELDS, label="transitive role total")
        _require_scalar(row["dependency_role"], str, label="dependency role")
        _require_scalar(row["body_count"], int, label="dependency body count")
        _require_scalar(
            row["cumulative_canonical_bytes"],
            int,
            label="dependency byte count",
        )
    for key in (
        "binding_count",
        "binding_rows_canonical_bytes",
        "cumulative_canonical_bytes",
    ):
        _require_scalar(transitive[key], int, label="transitive integer")
    _require_transitive_provider_budget(
        transitive["cumulative_canonical_bytes"]
    )
    _require_scalar(transitive["binding_order"], str, label="binding order")
    _require_scalar(
        transitive["binding_rows_sha256"], str, label="binding digest"
    )
    _require_scalar(
        transitive["bodies_embedded"], bool, label="embedded-body flag"
    )

    for key, item in value["canonical_limits"].items():
        if key == "unicode_normalization":
            expected_type = str
        elif key in {
            "direct_dependency_bodies_embedded",
            "framed_byte_cap_before_body_required",
            "null_float_or_negative_integer_allowed",
            "precanonical_expanded_structure_preflight_required",
            "self_hash_embedded",
        }:
            expected_type = bool
        else:
            expected_type = int
        _require_scalar(item, expected_type, label="canonical limit")

    context = value["corpus_context_summary"]
    for key in (
        "authoritative_corpus_input_closure_available",
        "authoritative_corpus_input_closure_bound",
        "complete_inventory_evidence_bound",
        "external_projection_bodies_embedded",
        "namespace_issued",
        "request_only_corpus_input_closure_authoritative",
        "request_only_corpus_input_closure_bound",
        "request_only_corpus_input_closure_candidate_available",
        "request_only_corpus_input_closure_complete",
    ):
        _require_scalar(context[key], bool, label="corpus context flag")
    _require_scalar(
        context["ordered_projection_pins_sha256"],
        str,
        label="projection pin digest",
    )
    for key in CORPUS_CONTEXT_FIELDS - {
        "authoritative_corpus_input_closure_available",
        "authoritative_corpus_input_closure_bound",
        "complete_inventory_evidence_bound",
        "external_projection_bodies_embedded",
        "namespace_issued",
        "ordered_projection_pins_sha256",
        "request_only_corpus_input_closure_authoritative",
        "request_only_corpus_input_closure_bound",
        "request_only_corpus_input_closure_candidate_available",
        "request_only_corpus_input_closure_complete",
    }:
        _require_scalar(context[key], int, label="corpus context count")

    for key, item in value["summary"].items():
        _require_scalar(item, int, label=f"summary {key}")
    for key, item in value["orders"].items():
        _require_scalar(item, str, label=f"order {key}")
    for field_name in (
        "unresolved_target_semantics",
        "unresolved_distractor_sources",
    ):
        for key, item in value[field_name].items():
            if (
                field_name == "unresolved_target_semantics"
                and key == "all_condition_exact_resolution_status"
            ):
                expected_type = str
            else:
                expected_type = bool if type(item) is bool else int
            _require_scalar(item, expected_type, label=f"{field_name} {key}")


def _json_string_size(value):
    if len(value) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        _fail("expanded string exceeds its codepoint cap")
    try:
        encoded = value.encode("utf-8", "strict")
    except UnicodeEncodeError:
        _fail("expanded string is not valid UTF-8")
    if len(encoded) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        _fail("expanded string exceeds its byte cap")
    if unicodedata.normalize("NFC", value) != value:
        _fail("expanded string is not NFC-normalized")
    size = 2
    for character in value:
        codepoint = ord(character)
        if character in {'"', "\\"}:
            size += 2
        elif codepoint <= 0x1F:
            size += 2 if character in "\b\t\n\f\r" else 6
        else:
            size += len(character.encode("utf-8"))
    return size


def _expanded_preflight(value):
    state = {"bytes": 0, "nodes": 0}

    def add_bytes(amount):
        state["bytes"] += amount
        if state["bytes"] > MAX_MANIFEST_BYTES:
            _fail("expanded structure exceeds the manifest byte cap")

    def add_node():
        state["nodes"] += 1
        if state["nodes"] > MAX_EXPANDED_NODE_COUNT:
            _fail("expanded structure exceeds the node-count cap")

    def walk(node, depth):
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail("expanded structure exceeds the nesting-depth cap")
        add_node()
        if type(node) is dict:
            add_bytes(2 + max(0, len(node) - 1))
            for key, item in node.items():
                if type(key) is not str:
                    _fail("expanded object key is not a string")
                add_node()
                add_bytes(_json_string_size(key) + 1)
                walk(item, depth + 1)
        elif type(node) is list:
            add_bytes(2 + max(0, len(node) - 1))
            for item in node:
                walk(item, depth + 1)
        elif type(node) is str:
            add_bytes(_json_string_size(node))
        elif type(node) is bool:
            add_bytes(4 if node else 5)
        elif type(node) is int:
            if node < 0 or node > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail("expanded integer exceeds its checked non-negative range")
            add_bytes(len(str(node)))
        else:
            _fail("expanded structure contains a forbidden value type")

    try:
        walk(value, 0)
    except RecursionError:
        _fail("expanded structure recursion exceeds the depth cap")
    return state


def preflight_evaluation_target_resolution_closure_slice(value):
    """Bound candidate structure before any dependency provider is invoked."""

    _expected_golden()
    try:
        _preflight_shallow(value)
        state = _expanded_preflight(value)
        # This artifact has one frozen static body shape even while its own
        # outer golden pin is awaiting cold measurement.  Enforcing that shape
        # here prevents candidate canonicalization from laundering an authority
        # flip or a false completion claim during the measurement window.
        if not _strict_equal(
            value, _expected_value(_frozen_dependency_snapshot())
        ):
            _fail("candidate differs from the exact static closure-slice contract")
    except PersonaV2EvaluationTargetResolutionClosureSliceValidationError:
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
    _require_expected_raw(
        _canonical(
            value,
            label="preflight evaluation target-resolution closure slice",
        )
    )
    return copy.deepcopy(state)


def _snapshot_candidate(value):
    preflight_evaluation_target_resolution_closure_slice(value)
    try:
        detached = copy.deepcopy(value)
    except (MemoryError, RecursionError, RuntimeError, TypeError):
        _fail("candidate could not be copied within structural bounds")
    state = preflight_evaluation_target_resolution_closure_slice(detached)
    raw = _canonical(detached, label="evaluation target-resolution closure slice")
    if state["bytes"] < len(raw):
        _fail("expanded byte preflight underestimated canonical bytes")
    try:
        preflight_evaluation_target_resolution_closure_slice(value)
        live_opening_raw = _canonical(
            value,
            label="live opening evaluation target-resolution closure slice",
        )
    except PersonaV2EvaluationTargetResolutionClosureSliceValidationError:
        raise
    except (MemoryError, RecursionError, RuntimeError, TypeError, UnicodeError):
        _fail("candidate changed while its opening snapshot was created")
    if not hmac.compare_digest(raw, live_opening_raw):
        _fail("candidate changed while its opening snapshot was created")
    return detached, _require_expected_raw(raw)


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
    _fail("canonical JSON non-finite values are forbidden")


def strict_load_canonical_json_bytes(raw):
    _expected_golden()
    if type(raw) is not bytes:
        _fail("canonical body must be exact built-in bytes")
    if len(raw) > MAX_MANIFEST_BYTES:
        _fail("canonical body exceeds its pre-parse byte cap")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_pairs,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except PersonaV2EvaluationTargetResolutionClosureSliceValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError, RecursionError):
        _fail("canonical body is not strict UTF-8 JSON")
    if type(value) is not dict:
        _fail("canonical body must decode to an object")
    preflight_evaluation_target_resolution_closure_slice(value)
    if not hmac.compare_digest(
        raw,
        _canonical(value, label="strict evaluation closure slice body"),
    ):
        _fail("body bytes are valid JSON but not exact canonical JSON")
    return value


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
            dependency_id="corpus-semantic-namespace",
            dependency_role="corpus-semantic-identity-context",
            artifact_kind=(
                "persona-pc-v2-projection-pin-corpus-semantic-namespace"
            ),
            artifact_schema="kio.persona.pc-corpus-semantic-namespace/v3",
            artifact_schema_version=3,
            canonical_bytes=NAMESPACE_CANONICAL_BYTES,
            sha256=NAMESPACE_SHA256,
        ),
        _pin(
            dependency_id="complete-semantic-projection-inventory",
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
            dependency_id="query-history-target-resolution",
            dependency_role="evaluation-target-resolution",
            artifact_kind="persona-pc-v2-query-history-target-resolution",
            artifact_schema=(
                "kio.persona.pc-query-history-target-resolution/v1"
            ),
            artifact_schema_version=1,
            canonical_bytes=TARGET_RESOLUTION_CANONICAL_BYTES,
            sha256=TARGET_RESOLUTION_SHA256,
        ),
        _pin(
            dependency_id="request-only-corpus-input-closure",
            dependency_role=(
                "request-only-corpus-closure-active-blocker-evidence"
            ),
            artifact_kind=(
                "persona-pc-v2-corpus-input-closure-manifest-request-only-"
                "candidate"
            ),
            artifact_schema="kio.persona.pc-corpus-input-closure-manifest/v3",
            artifact_schema_version=3,
            canonical_bytes=REQUEST_ONLY_CORPUS_CLOSURE_CANONICAL_BYTES,
            sha256=REQUEST_ONLY_CORPUS_CLOSURE_SHA256,
        ),
        _pin(
            dependency_id=(
                "query-history-semantic-resolution-feasibility-audit"
            ),
            dependency_role=(
                "semantic-resolution-feasibility-active-blocker-evidence"
            ),
            artifact_kind=(
                "persona-pc-v2-query-history-semantic-resolution-"
                "feasibility-audit"
            ),
            artifact_schema=(
                "kio.persona.pc-query-history-semantic-resolution-"
                "feasibility-audit/v1"
            ),
            artifact_schema_version=1,
            canonical_bytes=SEMANTIC_FEASIBILITY_CANONICAL_BYTES,
            sha256=SEMANTIC_FEASIBILITY_SHA256,
        ),
    ]


def _require_transitive_provider_budget(cumulative_bytes):
    """Bound the logical canonical bytes of the exact sixty provider bodies."""

    if (
        type(cumulative_bytes) is not int
        or type(cumulative_bytes) is bool
        or cumulative_bytes < 0
        or cumulative_bytes > MAX_TRANSITIVE_PROVIDER_BYTES
    ):
        _fail("target-resolution transitive provider bytes exceed their cap")
    return cumulative_bytes


def _transitive_commitment():
    _require_transitive_provider_budget(TRANSITIVE_CUMULATIVE_CANONICAL_BYTES)
    return {
        "binding_count": 60,
        "binding_order": TRANSITIVE_BINDING_ORDER,
        "binding_rows_canonical_bytes": 24_961,
        "binding_rows_sha256": TRANSITIVE_BINDING_ROWS_SHA256,
        "bodies_embedded": False,
        "cumulative_canonical_bytes": 7_385_300,
        "role_totals": [
            {
                "body_count": count,
                "cumulative_canonical_bytes": byte_count,
                "dependency_role": role,
            }
            for role, count, byte_count in TRANSITIVE_ROLE_TOTALS
        ],
    }


def _persona_coverage():
    return [
        {
            "abstract_companion_binding_count": 10,
            "abstract_distractor_reference_count": 270,
            "mapped_distinct_distractor_source_count": 0,
            "negative_query_count": 15,
            "persona_id": persona_id,
            "positive_query_count": 90,
            "query_capability_mapping_count": 105,
            "required_distinct_distractor_source_count": 270,
        }
        for persona_id in envelope.PERSONA_IDS
    ]


def _corpus_context_summary():
    return {
        "active_g0_unresolved_count": 36,
        "authoritative_corpus_input_closure_available": False,
        "authoritative_corpus_input_closure_bound": False,
        "complete_inventory_evidence_bound": True,
        "cumulative_external_projection_bytes": 155_741_475,
        "external_projection_bodies_embedded": False,
        "namespace_entry_count": 253,
        "namespace_issued": False,
        "ordered_projection_pins_sha256": ORDERED_PROJECTION_PINS_SHA256,
        "positive_review_receipt_count": 0,
        "projection_class_count": 12,
        "request_only_corpus_input_closure_authoritative": False,
        "request_only_corpus_input_closure_bound": True,
        "request_only_corpus_input_closure_candidate_available": True,
        "request_only_corpus_input_closure_complete": False,
        "required_positive_review_receipt_count": 7,
    }


def _require_constant_pin_alignment():
    expected = _expected_direct_pins()
    direct_constants = (
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
            resolution.ARTIFACT_KIND,
            resolution.ARTIFACT_SCHEMA,
            resolution.ARTIFACT_SCHEMA_VERSION,
            resolution.EXPECTED_CANONICAL_BYTES,
            resolution.EXPECTED_SHA256,
        ),
        (
            corpus_closure.ARTIFACT_KIND,
            corpus_closure.ARTIFACT_SCHEMA,
            corpus_closure.ARTIFACT_SCHEMA_VERSION,
            corpus_closure.EXPECTED_CLOSURE_CANONICAL_BYTES,
            corpus_closure.EXPECTED_CLOSURE_SHA256,
        ),
        (
            feasibility.ARTIFACT_KIND,
            feasibility.ARTIFACT_SCHEMA,
            feasibility.ARTIFACT_SCHEMA_VERSION,
            feasibility.EXPECTED_CANONICAL_BYTES,
            feasibility.EXPECTED_SHA256,
        ),
    )
    expected_constants = tuple(
        (
            pin["artifact_kind"],
            pin["artifact_schema"],
            pin["artifact_schema_version"],
            pin["canonical_bytes"],
            pin["sha256"],
        )
        for pin in expected
    )
    if direct_constants != expected_constants:
        _fail("dependency constants differ from independent literal pins")

    nested_checks = (
        (
            corpus_closure.DEPENDENCY_SPECS[
                "corpus-semantic-namespace-v3"
            ]["pin"],
            expected[0],
            True,
        ),
        (
            corpus_closure.DEPENDENCY_SPECS[
                "complete-semantic-projection-inventory-v2"
            ]["pin"],
            expected[1],
            True,
        ),
        (
            feasibility.DEPENDENCY_PINS[
                "query-history-target-resolution-v1"
            ],
            expected[2],
            False,
        ),
        (
            feasibility.DEPENDENCY_PINS["corpus-semantic-namespace-v3"],
            expected[0],
            False,
        ),
        (
            feasibility.DEPENDENCY_PINS[
                "complete-semantic-projection-inventory-v2"
            ],
            expected[1],
            False,
        ),
    )
    fields = (
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "sha256",
    )
    for nested, direct, framing_required in nested_checks:
        if any(nested.get(field) != direct[field] for field in fields):
            _fail("redundant frozen pin differs across dependency bodies")
        if framing_required and nested.get("body_framing") != direct[
            "body_framing"
        ]:
            _fail("redundant frozen dependency framing differs")
        nested_kind = nested.get("artifact_kind")
        if nested_kind is not None and nested_kind != direct["artifact_kind"]:
            _fail("redundant frozen dependency kind differs")


def _dependency_pin_index(value, *, label):
    bindings = value.get("dependency_bindings")
    if type(bindings) is not list:
        _fail(f"{label} does not expose dependency bindings")
    index = {}
    for binding in bindings:
        if type(binding) is not dict:
            _fail(f"{label} dependency binding is not an object")
        dependency_id = binding.get("dependency_id")
        dependency_pin = binding.get("dependency_pin")
        if (
            type(dependency_id) is not str
            or dependency_id in index
            or type(dependency_pin) is not dict
        ):
            _fail(f"{label} dependency bindings are not unique exact pins")
        index[dependency_id] = dependency_pin
    return index


def _validate_redundant_live_evidence(closure_value, feasibility_value):
    expected = _expected_direct_pins()
    closure_index = _dependency_pin_index(
        closure_value,
        label="request-only corpus closure",
    )
    feasibility_index = _dependency_pin_index(
        feasibility_value,
        label="semantic feasibility audit",
    )
    checks = (
        (
            closure_index.get("corpus-semantic-namespace-v3"),
            expected[0],
            True,
        ),
        (
            closure_index.get(
                "complete-semantic-projection-inventory-v2"
            ),
            expected[1],
            True,
        ),
        (
            feasibility_index.get("query-history-target-resolution-v1"),
            expected[2],
            False,
        ),
        (
            feasibility_index.get("corpus-semantic-namespace-v3"),
            expected[0],
            False,
        ),
        (
            feasibility_index.get(
                "complete-semantic-projection-inventory-v2"
            ),
            expected[1],
            False,
        ),
    )
    fields = (
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "sha256",
    )
    for nested, direct, framing_required in checks:
        if type(nested) is not dict or any(
            nested.get(field) != direct[field] for field in fields
        ):
            _fail("live redundant dependency pin differs from direct pin")
        if framing_required and nested.get("body_framing") != direct[
            "body_framing"
        ]:
            _fail("live redundant dependency framing differs from direct pin")
        nested_kind = nested.get("artifact_kind")
        if nested_kind is not None and nested_kind != direct["artifact_kind"]:
            _fail("live redundant dependency kind differs from direct pin")

    closure_summary = closure_value.get("summary", {})
    closure_completion = closure_value.get("completion_claims", {})
    closure_review = closure_value.get("review_gate", {})
    if (
        any(closure_value.get("authority", {}).values())
        or closure_summary.get("corpus_input_closure_complete") is not False
        or closure_summary.get("active_g0_unresolved_count") != 36
        or closure_completion.get("corpus_input_closure_complete") is not False
        or closure_review.get("positive_review_receipt_count") != 0
        or closure_review.get("required_positive_receipt_count") != 7
        or closure_review.get("all_required_positive_receipts_bound") is not False
    ):
        _fail("request-only closure no longer reports exact blockers")

    summary = feasibility_value.get("summary", {})
    expected_metrics = (
        ("abstract_distractor_reference_count", 5_400),
        ("all_condition_exact_resolution_count", 0),
        ("baseline_aligned_contributor_target_count", 327),
        ("baseline_mismatched_contributor_target_count", 1_673),
        ("concrete_distractor_source_mapping_count", 0),
        ("contributor_target_count", 2_000),
        ("four_domain_disjointness_proved", False),
        (
            "maximum_distinct_distractor_source_candidate_count_before_language_filter",
            1_060,
        ),
        ("maximum_distractor_mapping_shortfall_count", 4_340),
        ("query_history_target_resolution_v2_issued", False),
        ("revision_join_unknown_count", 2_000),
    )
    if any(summary.get(key) != expected for key, expected in expected_metrics):
        _fail("semantic feasibility audit measured facts differ")
    completion = feasibility_value.get("completion_claims", {})
    publication = feasibility_value.get("resolution_publication_contract", {})
    if (
        any(feasibility_value.get("authority", {}).values())
        or completion.get("all_condition_semantic_resolution_complete")
        is not False
        or completion.get("checkpoint_selector_effective_membership_compiled")
        is not False
        or completion.get("query_history_target_resolution_v2_issued")
        is not False
        or publication.get("artifact_role")
        != "audit-only-active-blocker-evidence"
        or publication.get("artifact_is_query_history_target_resolution_v2")
        is not False
    ):
        _fail("semantic feasibility audit gained authority or resolution status")


def _frozen_dependency_snapshot():
    _require_constant_pin_alignment()
    return {
        "corpus_context_summary": _corpus_context_summary(),
        "dependency_pins": _expected_direct_pins(),
        "persona_coverage": _persona_coverage(),
        "transitive_resolution_input_commitment": _transitive_commitment(),
    }


def _pin_from_body(value, raw, expected):
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
        _fail("live dependency differs from its independent frozen pin")
    if (
        value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("live dependency fixture identity drifted")
    return pin


def _target_commitment(target):
    bindings = target.get("input_bindings")
    if type(bindings) is not list or len(bindings) != 60:
        _fail("live target resolution input-binding cardinality drifted")
    raw = _canonical(
        bindings,
        label="independent target-resolution input bindings",
        maximum=128 * 2**10,
    )
    role_totals = []
    for role, expected_count, expected_bytes in TRANSITIVE_ROLE_TOTALS:
        matching = [row for row in bindings if row.get("dependency_role") == role]
        total = sum(row.get("canonical_bytes", -1) for row in matching)
        if len(matching) != expected_count or total != expected_bytes:
            _fail("live target-resolution role totals drifted")
        role_totals.append(
            {
                "body_count": len(matching),
                "cumulative_canonical_bytes": total,
                "dependency_role": role,
            }
        )
    cumulative_bytes = sum(
        row["cumulative_canonical_bytes"] for row in role_totals
    )
    _require_transitive_provider_budget(cumulative_bytes)
    commitment = {
        "binding_count": len(bindings),
        "binding_order": target.get("input_binding_order", [None])[0],
        "binding_rows_canonical_bytes": len(raw),
        "binding_rows_sha256": _sha256(raw),
        "bodies_embedded": False,
        "cumulative_canonical_bytes": cumulative_bytes,
        "role_totals": role_totals,
    }
    if not _strict_equal(commitment, _transitive_commitment()):
        _fail("live target-resolution binding commitment drifted")
    return commitment


def _target_coverage(target):
    rows = target.get("resolution_rows")
    summaries = target.get("persona_summaries")
    if type(rows) is not list or len(rows) != 2_100:
        _fail("live target resolution row cardinality drifted")
    if type(summaries) is not list or len(summaries) != 20:
        _fail("live target resolution persona-summary cardinality drifted")
    by_persona = {row.get("persona_id"): row for row in summaries}
    if set(by_persona) != set(envelope.PERSONA_IDS):
        _fail("live target-resolution persona identities drifted")
    result = []
    for persona_id in envelope.PERSONA_IDS:
        persona_rows = [row for row in rows if row.get("persona_id") == persona_id]
        distractor_intents = []
        distractor_documents = []
        for row in persona_rows:
            distractor = row.get("distractor_contract")
            status = row.get("resolution_status")
            if type(distractor) is not dict or type(status) is not dict:
                _fail("live target resolution row schema drifted")
            if (
                distractor.get("mapped_source_intent_keys") != []
                or distractor.get("source_mapping_resolved") is not False
                or status.get("effective_fact_membership_present") is not False
                or status.get("final_identity_binding_present") is not False
                or status.get("source_topic_language_fact_equality_proved")
                is not False
            ):
                _fail("live target resolution gained an unresolved claim")
            distractor_intents.extend(distractor.get("distractor_intent_keys", []))
            distractor_documents.extend(
                distractor.get("distractor_logical_document_keys", [])
            )
        summary = by_persona[persona_id]
        if (
            len(persona_rows) != 105
            or len(distractor_intents) != 270
            or len(set(distractor_intents)) != 270
            or len(distractor_documents) != 270
            or len(set(distractor_documents)) != 270
        ):
            _fail("live target resolution per-persona coverage drifted")
        result.append(
            {
                "abstract_companion_binding_count": summary.get(
                    "abstract_companion_binding_count"
                ),
                "abstract_distractor_reference_count": len(distractor_intents),
                "mapped_distinct_distractor_source_count": 0,
                "negative_query_count": summary.get("negative_query_count"),
                "persona_id": persona_id,
                "positive_query_count": summary.get("positive_query_count"),
                "query_capability_mapping_count": summary.get(
                    "query_capability_bijection_count"
                ),
                "required_distinct_distractor_source_count": 270,
            }
        )
    if not _strict_equal(result, _persona_coverage()):
        _fail("live target resolution compact coverage drifted")
    return result


def _live_dependency_snapshot(*, full=False):
    _require_constant_pin_alignment()
    if not full:
        return _frozen_dependency_snapshot()

    inventory = complete.build_semantic_projection_complete_inventory()
    inventory_raw = complete.canonical_json_bytes(inventory)
    namespace_value = namespace.build_corpus_semantic_namespace_v3(inventory)
    namespace_raw = namespace.corpus_semantic_namespace_v3_candidate_bytes(
        namespace_value
    )
    target = resolution.build_query_history_target_resolution()
    target_raw = resolution.canonical_json_bytes(target)
    closure_value = corpus_closure.build_corpus_input_closure_v3()
    closure_raw = corpus_closure.corpus_input_closure_v3_candidate_bytes(
        closure_value
    )
    feasibility_value = (
        feasibility.build_query_history_semantic_resolution_feasibility_audit()
    )
    feasibility_raw = feasibility.candidate_bytes(feasibility_value)
    bodies = (
        namespace_raw,
        inventory_raw,
        target_raw,
        closure_raw,
        feasibility_raw,
    )
    if sum(map(len, bodies)) > MAX_DIRECT_DESCRIPTOR_BYTES:
        _fail("full direct dependency descriptors exceed their bounded cap")

    _validate_redundant_live_evidence(closure_value, feasibility_value)
    # The request-only closure is the single owner of the all-253 replay.
    # Revalidating namespace here would duplicate its 506 projection reads.
    if corpus_closure.validate_corpus_input_closure_v3(closure_value) is not True:
        _fail("request-only closure full validation was not exact true")
    if resolution_validator.validate_query_history_target_resolution(target) is not True:
        _fail("independent target-resolution validation was not exact true")
    if (
        feasibility.validate_query_history_semantic_resolution_feasibility_audit(
            feasibility_value
        )
        is not True
    ):
        _fail("semantic feasibility independent validation was not exact true")
    closing_bodies = (
        namespace.corpus_semantic_namespace_v3_candidate_bytes(namespace_value),
        complete.canonical_json_bytes(inventory),
        resolution.canonical_json_bytes(target),
        corpus_closure.corpus_input_closure_v3_candidate_bytes(closure_value),
        feasibility.candidate_bytes(feasibility_value),
    )
    if any(
        not hmac.compare_digest(opening, closing)
        for opening, closing in zip(bodies, closing_bodies, strict=True)
    ):
        _fail("a full direct dependency changed during validation")
    _validate_redundant_live_evidence(closure_value, feasibility_value)

    expected_pins = _expected_direct_pins()
    pins = [
        _pin_from_body(namespace_value, namespace_raw, expected_pins[0]),
        _pin_from_body(inventory, inventory_raw, expected_pins[1]),
        _pin_from_body(target, target_raw, expected_pins[2]),
        _pin_from_body(closure_value, closure_raw, expected_pins[3]),
        _pin_from_body(feasibility_value, feasibility_raw, expected_pins[4]),
    ]
    context = _corpus_context_summary()
    live_namespace_summary = namespace_value["summary"]
    if (
        live_namespace_summary["cumulative_external_projection_bytes"]
        != context["cumulative_external_projection_bytes"]
        or live_namespace_summary["namespace_entry_count"]
        != context["namespace_entry_count"]
        or live_namespace_summary["projection_class_count"]
        != context["projection_class_count"]
        or namespace_value["completion_claims"][
            "corpus_semantic_namespace_issued"
        ]
        != context["namespace_issued"]
    ):
        _fail("live namespace summary differs from independent context")
    snapshot = {
        "corpus_context_summary": context,
        "dependency_pins": pins,
        "persona_coverage": _target_coverage(target),
        "transitive_resolution_input_commitment": _target_commitment(target),
    }
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("live dependency snapshot differs from independent frozen metadata")
    return snapshot


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _completion_claims():
    return {
        "abstract_distractor_requirements_bound": True,
        "all_20_persona_summaries_bound": True,
        "all_2100_query_capability_mappings_bound": True,
        "authoritative_corpus_input_closure_bound": False,
        "complete_inventory_evidence_pin_bound": True,
        "compiled_history_event_bindings_present": False,
        "corpus_namespace_pin_bound": True,
        "distractor_source_mapping_resolved": False,
        "exact_source_semantic_query_history_resolution_bound": False,
        "final_identity_relevance_present": False,
        "namespace_query_isolation_bound": True,
        "positive_independent_review_receipt_bound": False,
        "production_evaluation_input_closure_complete": False,
        "query_instances_rendered": False,
        "query_spec_hashed_by_g0": False,
        "request_only_corpus_input_closure_bound": True,
        "semantic_resolution_feasibility_audit_bound": True,
        "source_fact_equality_proved": False,
        "source_language_equality_proved": False,
        "source_topic_equality_proved": False,
        "target_primary_companion_distractor_disjointness_proved": False,
        "target_resolution_pin_bound": True,
        "transitive_60_dependency_commitment_bound": True,
    }


def _canonical_limits():
    return {
        "direct_dependency_bodies_embedded": False,
        "framed_byte_cap_before_body_required": True,
        "max_direct_dependency_count": 5,
        "max_direct_descriptor_bytes": 16 * 2**20,
        "max_expanded_node_count": 100_000,
        "max_manifest_bytes": 256 * 2**10,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_persona_count": 20,
        "max_query_mapping_count": 2_100,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "max_transitive_binding_count": 60,
        "max_transitive_provider_bytes": 60 * 2**20,
        "null_float_or_negative_integer_allowed": False,
        "precanonical_expanded_structure_preflight_required": True,
        "self_hash_embedded": False,
        "target_manifest_bytes": 128 * 2**10,
        "unicode_normalization": "NFC",
    }


def _unresolved_target_semantics():
    return {
        "all_condition_exact_resolution_proved_count": 0,
        "all_condition_exact_resolution_status": "unknown-not-proved",
        "baseline_aligned_contributor_target_count": 327,
        "baseline_live_join_examined_contributor_target_count": 2_000,
        "baseline_mismatched_contributor_target_count": 1_673,
        "checkpoint_selector_effective_membership_compiled_count": 0,
        "compiled_event_id_binding_count": 0,
        "contributor_target_count": 2_000,
        "final_materialization_id_binding_count": 0,
        "final_source_id_binding_count": 0,
        "inference_from_abstract_or_base_membership_allowed": False,
        "incidental_target_count": 100,
        "lifecycle_capability_mapping_count": 2_100,
        "negative_expected_empty_count": 300,
        "positive_answer_requirement_count": 1_800,
        "query_history_target_resolution_v2_issued": False,
        "raw_hash_section_binding_count": 0,
        "resolution_target_count": 2_100,
        "revision_join_unknown_contributor_target_count": 2_000,
    }


def _unresolved_distractor_sources():
    return {
        "abstract_distinct_distractor_intent_key_count": 5_400,
        "abstract_distinct_distractor_logical_document_key_count": 5_400,
        "abstract_distractor_reference_count": 5_400,
        "distractor_nonanswer_fact_source_proved_count": 0,
        "distractor_same_language_source_proved_count": 0,
        "distractor_same_topic_source_proved_count": 0,
        "mapped_distinct_distractor_source_count": 0,
        "mapped_source_intent_keys_embedded": False,
        "maximum_distinct_distractor_source_candidate_count_before_language_filter": 1_060,
        "maximum_distractor_mapping_shortfall_count": 4_340,
        "per_query_abstract_answer_distractor_fact_disjoint": True,
        "positive_query_count": 1_800,
        "required_distinct_distractor_source_count_per_persona": 270,
        "required_distinct_distractor_source_count_suite": 5_400,
        "source_mapping_resolved": False,
        "target_primary_companion_distractor_source_domains_disjoint": False,
    }


def _expected_value(snapshot):
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": 1,
        "authority": _negative_authority(),
        "canonical_limits": _canonical_limits(),
        "completion_claims": _completion_claims(),
        "completion_scope": (
            "pinned-evaluation-target-resolution-slice-with-request-only-"
            "corpus-closure-and-active-blocker-feasibility-evidence-no-"
            "authoritative-corpus-closure-no-exact-source-semantic-"
            "resolution-no-final-identities-render-execution-or-g0"
        ),
        "corpus_context_summary": copy.deepcopy(
            snapshot["corpus_context_summary"]
        ),
        "dependency_direction_contract": {
            "complete_inventory_is_validation_evidence_not_semantic_identity": True,
            "corpus_namespace_may_import_this_slice": False,
            "corpus_renderer_may_import_this_slice": False,
            "future_full_evaluation_closure_may_bind_this_slice": True,
            "positive_review_receipts_are_transitive_authoritative_closure_inputs": True,
            "query_or_oracle_change_may_change_corpus_namespace": False,
            "query_or_oracle_change_may_change_evaluation_slice": True,
            "query_or_oracle_change_may_change_source_id_preimage": False,
            "request_only_corpus_closure_is_evidence_not_authority": True,
            "semantic_feasibility_audit_is_blocker_evidence_not_resolution_v2": True,
            "slice_is_downstream_of_namespace_and_target_resolution": True,
        },
        "dependency_order": list(DIRECT_DEPENDENCY_ORDER),
        "dependency_pins": copy.deepcopy(snapshot["dependency_pins"]),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-pinned-evaluation-closure-slice-with-measured-"
            "semantic-infeasibility-active-blockers-not-observed-source-"
            "relevance-or-execution"
        ),
        "missing_required_full_closure_dependencies": [
            "authoritative-corpus-input-closure",
            "query-intent",
            "semantic-oracle",
            "complete-fact-oracle-query-history-manifest",
            "exact-source-semantic-query-history-resolution",
        ],
        "orders": {
            "direct_dependencies": "declared-dependency-order",
            "persona_coverage": "persona-id-ascii",
            "transitive_bindings": TRANSITIVE_BINDING_ORDER,
        },
        "persona_coverage": copy.deepcopy(snapshot["persona_coverage"]),
        "remaining_blockers": [
            "authoritative-corpus-input-closure-with-transitive-positive-receipts-not-bound",
            "exact-source-semantic-query-history-resolution-not-issued",
            "5400-distinct-distractor-source-mappings-have-only-1060-candidate-upper-bound",
            "target-primary-companion-distractor-source-domain-disjointness-not-proved",
            "abstract-event-templates-not-compiled-to-history-event-identities",
            "scope-bucket-cohort-quota-solution-proof-and-final-source-plan-not-built",
            "query-render-byte-uniqueness-and-compiled-relevance-not-built",
            "filesystem-render-index-history-kio-receipts-and-g0-not-built",
        ],
        "summary": {
            "abstract_companion_binding_count": 200,
            "abstract_distractor_reference_count": 5_400,
            "dependency_pin_count": 5,
            "mapped_distinct_distractor_source_count": 0,
            "negative_query_count": 300,
            "persona_count": 20,
            "positive_query_count": 1_800,
            "query_capability_mapping_count": 2_100,
            "required_distinct_distractor_source_count": 5_400,
            "transitive_binding_count": 60,
        },
        "transitive_resolution_input_commitment": copy.deepcopy(
            snapshot["transitive_resolution_input_commitment"]
        ),
        "unresolved_distractor_sources": _unresolved_distractor_sources(),
        "unresolved_target_semantics": _unresolved_target_semantics(),
    }


def _require_snapshot(snapshot):
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("dependency snapshot differs from independent accepted metadata")


def _snapshot_dependencies(provider, dependency_observer=None):
    if not callable(provider):
        _fail("dependency snapshot provider must be callable")
    try:
        opening_value = provider()
        _require_snapshot(opening_value)
        opening = copy.deepcopy(opening_value)
        opening_raw = _canonical(
            opening,
            label="evaluation closure dependency snapshot",
            maximum=128 * 2**10,
        )
        _require_snapshot(opening_value)
        live_opening_raw = _canonical(
            opening_value,
            label="live opening evaluation closure dependency snapshot",
            maximum=128 * 2**10,
        )
        if not hmac.compare_digest(opening_raw, live_opening_raw):
            _fail("dependency snapshot changed while its opening copy was created")
        if dependency_observer is not None:
            if not callable(dependency_observer):
                _fail("dependency observer must be callable")
            dependency_observer(opening_value)
            if not hmac.compare_digest(
                opening_raw,
                _canonical(
                    opening_value,
                    label="observed evaluation closure dependency snapshot",
                    maximum=128 * 2**10,
                ),
            ):
                _fail("dependency snapshot changed during validation")
        closing_value = provider()
        _require_snapshot(closing_value)
        closing_raw = _canonical(
            closing_value,
            label="closing evaluation closure dependency snapshot",
            maximum=128 * 2**10,
        )
    except PersonaV2EvaluationTargetResolutionClosureSliceValidationError:
        raise
    except (MemoryError, RecursionError, RuntimeError, TypeError, ValueError):
        _fail("dependency snapshot provider failed closed")
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("dependency snapshot changed between validation reads")
    return opening


def _validate(
    value,
    *,
    dependency_snapshot_provider=None,
    dependency_observer=None,
):
    _expected_golden()
    detached, opening_raw = _snapshot_candidate(value)
    if dependency_snapshot_provider is None:
        # Fast validation opens only the accepted frozen-pin boundary, then
        # preserves the opening/closing replay contract with detached copies.
        # The opt-in full gate separately authenticates every live body.
        try:
            live_snapshot = _live_dependency_snapshot()
        except PersonaV2EvaluationTargetResolutionClosureSliceValidationError:
            raise
        except (MemoryError, RecursionError, RuntimeError, TypeError, ValueError):
            _fail("live dependency snapshot failed closed")

        def provider():
            return copy.deepcopy(live_snapshot)

    else:
        provider = dependency_snapshot_provider
    snapshot = _snapshot_dependencies(provider, dependency_observer)
    expected = _expected_value(snapshot)
    expected_raw = _canonical(
        expected, label="independent expected evaluation closure slice"
    )
    if len(expected_raw) > TARGET_MANIFEST_BYTES:
        _fail("independent expected slice exceeds its target byte budget")
    if not hmac.compare_digest(opening_raw, expected_raw):
        _fail("evaluation closure slice differs from independent regeneration")
    _closing_value, closing_raw = _snapshot_candidate(value)
    if not hmac.compare_digest(opening_raw, closing_raw):
        _fail("evaluation closure slice changed during validation")
    return True


def validate_evaluation_target_resolution_closure_slice(value):
    _expected_golden()
    return _validate(value)


def validate_evaluation_target_resolution_closure_slice_full(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
):
    _require_producer_golden_parity(producer_expected_golden)
    _snapshot_candidate(value)
    snapshot = _live_dependency_snapshot(full=True)
    return _validate(
        value,
        dependency_snapshot_provider=lambda: copy.deepcopy(snapshot),
    )


def validate_evaluation_target_resolution_closure_slice_bytes(raw):
    _expected_golden()
    value = strict_load_canonical_json_bytes(raw)
    return validate_evaluation_target_resolution_closure_slice(value)


__all__ = [
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_MANIFEST_BYTES",
    "PersonaV2EvaluationTargetResolutionClosureSliceValidationError",
    "preflight_evaluation_target_resolution_closure_slice",
    "strict_load_canonical_json_bytes",
    "validate_evaluation_target_resolution_closure_slice",
    "validate_evaluation_target_resolution_closure_slice_bytes",
    "validate_evaluation_target_resolution_closure_slice_full",
]
