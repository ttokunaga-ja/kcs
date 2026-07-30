"""Non-authorizing evaluation target-resolution closure slice.

This compact descriptor binds five already frozen trust roots:

* the projection-pin-only corpus semantic namespace,
* its complete projection-inventory validation evidence,
* the abstract query/history target resolution,
* the request-only corpus-input closure candidate, and
* the query/history semantic-resolution feasibility audit.

The 2,100 resolution rows and their sixty query/oracle/lifecycle dependency
bodies are not embedded.  Instead, the exact target-resolution body pin and an
ordered commitment to its sixty input bindings are recorded.  The artifact is
deliberately only a closure *slice*: the request-only candidate is not an
authoritative corpus closure and the feasibility audit is active-blocker
evidence rather than resolution v2.  The slice does not bind exact
source-semantic resolution, distractor source mappings, final identifiers,
rendered queries, compiled relevance, execution receipts, or G0.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_corpus_input_closure_v3 as corpus_closure
    from . import persona_v2_corpus_semantic_namespace_v3 as namespace
    from . import persona_v2_query_history_target_resolution as resolution
    from . import persona_v2_query_history_semantic_resolution_feasibility as feasibility
    from . import persona_v2_semantic_projection_complete_inventory as complete
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_corpus_input_closure_v3 as corpus_closure
    import persona_v2_corpus_semantic_namespace_v3 as namespace
    import persona_v2_query_history_target_resolution as resolution
    import persona_v2_query_history_semantic_resolution_feasibility as feasibility
    import persona_v2_semantic_projection_complete_inventory as complete


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

# Frozen only after two isolated full dependency builds under distinct hash
# seeds.  Keeping these absent during the measurement window changes no body
# field and grants no authority.
EXPECTED_CANONICAL_BYTES = 16_735
EXPECTED_SHA256 = (
    "635f67fc988cc7d339698fe6c8c8e211390e164e0df11cb216d2f497fff0d1a5"
)

NAMESPACE_CANONICAL_BYTES = 161_665
NAMESPACE_SHA256 = (
    "70fa743199265efd51ee940dd7032cb72d7c445561989c675060f15c158caafa"
)
COMPLETE_INVENTORY_CANONICAL_BYTES = 697_466
COMPLETE_INVENTORY_SHA256 = (
    "820c976a930c3f2ed0a54e44c08b01cad8a0879513f1b06012e353fb9bd3fd91"
)
ORDERED_PROJECTION_PINS_SHA256 = (
    "d9ffe202e88bff01c3238e0b4749e4c9cd1e8a759b420d2e12dcf27d8b25b7c8"
)
TARGET_RESOLUTION_CANONICAL_BYTES = 4_478_576
TARGET_RESOLUTION_SHA256 = (
    "8beed1ca21ebe80e029bcd003795306086514adcd852b98a9eed334fcd73f4ff"
)
REQUEST_ONLY_CORPUS_CLOSURE_CANONICAL_BYTES = 7_590
REQUEST_ONLY_CORPUS_CLOSURE_SHA256 = (
    "ee7010335ab6d50c9b36492e6bfd71c5d445544aeda95649002bbb66b798bd3f"
)
SEMANTIC_FEASIBILITY_CANONICAL_BYTES = 40_949
SEMANTIC_FEASIBILITY_SHA256 = (
    "573810a44e1823a685338cc87d249aea57934a9be3ba7940f02285d0fab16d0f"
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


class PersonaV2EvaluationTargetResolutionClosureSliceError(ValueError):
    """Raised when the compact evaluation closure slice is not exact."""


def _fail(message):
    raise PersonaV2EvaluationTargetResolutionClosureSliceError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    """Return an optional atomic golden pair after strict validation."""

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


def _transitive_commitment():
    _require_transitive_provider_budget(TRANSITIVE_CUMULATIVE_CANONICAL_BYTES)
    return {
        "binding_count": MAX_TRANSITIVE_BINDING_COUNT,
        "binding_order": TRANSITIVE_BINDING_ORDER,
        "binding_rows_canonical_bytes": (
            TRANSITIVE_BINDING_ROWS_CANONICAL_BYTES
        ),
        "binding_rows_sha256": TRANSITIVE_BINDING_ROWS_SHA256,
        "bodies_embedded": False,
        "cumulative_canonical_bytes": TRANSITIVE_CUMULATIVE_CANONICAL_BYTES,
        "role_totals": [
            {
                "body_count": count,
                "cumulative_canonical_bytes": byte_count,
                "dependency_role": role,
            }
            for role, count, byte_count in TRANSITIVE_ROLE_TOTALS
        ],
    }


def _require_transitive_provider_budget(cumulative_bytes):
    """Bound the logical canonical bytes of the exact sixty provider bodies."""

    if (
        type(cumulative_bytes) is not int
        or type(cumulative_bytes) is bool
        or cumulative_bytes < 0
        or cumulative_bytes > MAX_TRANSITIVE_PROVIDER_BYTES
    ):
        _fail("target-resolution transitive provider reads exceed their cap")
    return cumulative_bytes


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
        "cumulative_external_projection_bytes": 155_741_381,
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


def _pin_identity(pin):
    return (
        pin.get("artifact_kind"),
        pin.get("artifact_schema"),
        pin.get("artifact_schema_version"),
        pin.get("canonical_bytes"),
        pin.get("sha256"),
    )


def _require_dependency_constant_alignment():
    """Cross-check direct and redundant transitive pins without body reads."""

    expected = _expected_direct_pins()
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
    if actual != tuple(_pin_identity(pin) for pin in expected):
        _fail("direct dependency module constants drifted from frozen pins")

    closure_specs = corpus_closure.DEPENDENCY_SPECS
    feasibility_pins = feasibility.DEPENDENCY_PINS
    redundant_pairs = (
        (
            closure_specs["corpus-semantic-namespace-v3"]["pin"],
            expected[0],
            True,
        ),
        (
            closure_specs["complete-semantic-projection-inventory-v2"]["pin"],
            expected[1],
            True,
        ),
        (
            feasibility_pins["query-history-target-resolution-v1"],
            expected[2],
            False,
        ),
        (
            feasibility_pins["corpus-semantic-namespace-v3"],
            expected[0],
            False,
        ),
        (
            feasibility_pins[
                "complete-semantic-projection-inventory-v2"
            ],
            expected[1],
            False,
        ),
    )
    for nested, direct, framing_required in redundant_pairs:
        for field in (
            "artifact_schema",
            "artifact_schema_version",
            "canonical_bytes",
            "sha256",
        ):
            if nested.get(field) != direct[field]:
                _fail("redundant dependency pin drifted across frozen bodies")
        if framing_required and nested.get("body_framing") != direct[
            "body_framing"
        ]:
            _fail("redundant dependency framing drifted across frozen bodies")
        if "artifact_kind" in nested and nested["artifact_kind"] != direct[
            "artifact_kind"
        ]:
            _fail("redundant dependency kind drifted across frozen bodies")


def _binding_map(value, *, label):
    rows = value.get("dependency_bindings")
    if type(rows) is not list:
        _fail(f"{label} dependency bindings are unavailable")
    result = {}
    for row in rows:
        if type(row) is not dict or type(row.get("dependency_id")) is not str:
            _fail(f"{label} dependency binding schema drifted")
        dependency_id = row["dependency_id"]
        if dependency_id in result or type(row.get("dependency_pin")) is not dict:
            _fail(f"{label} dependency binding identities drifted")
        result[dependency_id] = row["dependency_pin"]
    return result


def _require_live_nested_alignment(closure_value, feasibility_value):
    """Authenticate redundant pins and the measured non-authorizing facts."""

    expected = _expected_direct_pins()
    closure_bindings = _binding_map(closure_value, label="request-only closure")
    feasibility_bindings = _binding_map(
        feasibility_value,
        label="semantic feasibility audit",
    )
    redundant_pairs = (
        (
            closure_bindings.get("corpus-semantic-namespace-v3"),
            expected[0],
            True,
        ),
        (
            closure_bindings.get(
                "complete-semantic-projection-inventory-v2"
            ),
            expected[1],
            True,
        ),
        (
            feasibility_bindings.get("query-history-target-resolution-v1"),
            expected[2],
            False,
        ),
        (
            feasibility_bindings.get("corpus-semantic-namespace-v3"),
            expected[0],
            False,
        ),
        (
            feasibility_bindings.get(
                "complete-semantic-projection-inventory-v2"
            ),
            expected[1],
            False,
        ),
    )
    for nested, direct, framing_required in redundant_pairs:
        if type(nested) is not dict:
            _fail("a redundant live dependency pin is missing")
        for field in (
            "artifact_schema",
            "artifact_schema_version",
            "canonical_bytes",
            "sha256",
        ):
            if nested.get(field) != direct[field]:
                _fail("redundant live dependency pin differs from direct pin")
        if framing_required and nested.get("body_framing") != direct[
            "body_framing"
        ]:
            _fail("redundant live dependency framing differs from direct pin")
        if "artifact_kind" in nested and nested["artifact_kind"] != direct[
            "artifact_kind"
        ]:
            _fail("redundant live dependency kind differs from direct pin")

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
        _fail("request-only closure body gained completion or authority")

    feasibility_summary = feasibility_value.get("summary", {})
    feasibility_completion = feasibility_value.get("completion_claims", {})
    feasibility_publication = feasibility_value.get(
        "resolution_publication_contract", {}
    )
    expected_summary = {
        "abstract_distractor_reference_count": 5_400,
        "all_condition_exact_resolution_count": 0,
        "baseline_aligned_contributor_target_count": 327,
        "baseline_mismatched_contributor_target_count": 1_673,
        "concrete_distractor_source_mapping_count": 0,
        "contributor_target_count": 2_000,
        "four_domain_disjointness_proved": False,
        "maximum_distinct_distractor_source_candidate_count_before_language_filter": 1_060,
        "maximum_distractor_mapping_shortfall_count": 4_340,
        "query_history_target_resolution_v2_issued": False,
        "revision_join_unknown_count": 2_000,
    }
    if any(
        feasibility_summary.get(field) != expected_value
        for field, expected_value in expected_summary.items()
    ):
        _fail("semantic feasibility measured summary drifted")
    if (
        any(feasibility_value.get("authority", {}).values())
        or feasibility_completion.get(
            "all_condition_semantic_resolution_complete"
        )
        is not False
        or feasibility_completion.get(
            "checkpoint_selector_effective_membership_compiled"
        )
        is not False
        or feasibility_completion.get(
            "query_history_target_resolution_v2_issued"
        )
        is not False
        or feasibility_publication.get("artifact_role")
        != "audit-only-active-blocker-evidence"
        or feasibility_publication.get(
            "artifact_is_query_history_target_resolution_v2"
        )
        is not False
    ):
        _fail("semantic feasibility body gained resolution or authority")


def _frozen_dependency_snapshot():
    """Return detached accepted-pin metadata for focused trust-boundary tests."""

    _require_dependency_constant_alignment()
    return {
        "corpus_context_summary": _corpus_context_summary(),
        "dependency_pins": _expected_direct_pins(),
        "persona_coverage": _persona_coverage(),
        "transitive_resolution_input_commitment": _transitive_commitment(),
    }


def _binding_rows_commitment(target):
    rows = target.get("input_bindings")
    if type(rows) is not list or len(rows) != MAX_TRANSITIVE_BINDING_COUNT:
        _fail("target resolution does not expose sixty input bindings")
    raw = _canonical(
        rows,
        label="target-resolution ordered transitive bindings",
        maximum=128 * 2**10,
    )
    role_totals = []
    for role, expected_count, expected_bytes in TRANSITIVE_ROLE_TOTALS:
        matching = [row for row in rows if row.get("dependency_role") == role]
        total = sum(
            row.get("canonical_bytes", -1)
            for row in matching
            if type(row) is dict
        )
        if len(matching) != expected_count or total != expected_bytes:
            _fail("target-resolution transitive dependency totals drifted")
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
        "binding_count": len(rows),
        "binding_order": target.get("input_binding_order", [None])[0],
        "binding_rows_canonical_bytes": len(raw),
        "binding_rows_sha256": _sha256(raw),
        "bodies_embedded": False,
        "cumulative_canonical_bytes": cumulative_bytes,
        "role_totals": role_totals,
    }
    if not _strict_equal(commitment, _transitive_commitment()):
        _fail("target-resolution transitive commitment drifted")
    return commitment


def _coverage_from_target(target):
    rows = target.get("resolution_rows")
    summaries = target.get("persona_summaries")
    if type(rows) is not list or len(rows) != MAX_QUERY_MAPPING_COUNT:
        _fail("target resolution row cardinality drifted")
    if type(summaries) is not list or len(summaries) != MAX_PERSONA_COUNT:
        _fail("target resolution persona-summary cardinality drifted")
    by_persona_summary = {row.get("persona_id"): row for row in summaries}
    if set(by_persona_summary) != set(envelope.PERSONA_IDS):
        _fail("target resolution persona summaries drifted")

    result = []
    for persona_id in envelope.PERSONA_IDS:
        persona_rows = [row for row in rows if row.get("persona_id") == persona_id]
        summary = by_persona_summary[persona_id]
        distractor_intents = []
        distractor_documents = []
        for row in persona_rows:
            distractor = row.get("distractor_contract")
            if type(distractor) is not dict:
                _fail("target resolution distractor contract drifted")
            if (
                distractor.get("mapped_source_intent_keys") != []
                or distractor.get("source_mapping_resolved") is not False
            ):
                _fail("target resolution unexpectedly maps distractor sources")
            distractor_intents.extend(distractor.get("distractor_intent_keys", []))
            distractor_documents.extend(
                distractor.get("distractor_logical_document_keys", [])
            )
            status = row.get("resolution_status")
            if (
                type(status) is not dict
                or status.get("effective_fact_membership_present") is not False
                or status.get("final_identity_binding_present") is not False
                or status.get("source_topic_language_fact_equality_proved")
                is not False
            ):
                _fail("target resolution gained an unresolved semantic claim")
        if (
            len(persona_rows) != 105
            or len(distractor_intents) != 270
            or len(set(distractor_intents)) != 270
            or len(distractor_documents) != 270
            or len(set(distractor_documents)) != 270
        ):
            _fail("target resolution per-persona abstract coverage drifted")
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
        _fail("target resolution persona coverage differs from the frozen contract")
    return result


def _pin_from_body(value, raw, *, expected):
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
        _fail("live dependency differs from its exact frozen pin")
    if (
        value.get("fixture_id") != envelope.FIXTURE_ID
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
    ):
        _fail("live dependency fixture identity drifted")
    return pin


def _live_dependency_snapshot(*, full=False):
    """Return accepted pins, or fully replay all five dependencies on opt-in."""

    _expected_golden()
    if full:
        _require_validator_golden_parity()
    _require_dependency_constant_alignment()
    if not full:
        # Fast acceptance is explicitly pin-bound.  Only the opt-in full/cold
        # gates open the multi-minute dependency bodies.
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
    if sum(
        len(raw)
        for raw in (
            namespace_raw,
            inventory_raw,
            target_raw,
            closure_raw,
            feasibility_raw,
        )
    ) > MAX_DIRECT_DESCRIPTOR_BYTES:
        _fail("direct dependency descriptors exceed their cumulative cap")

    _require_live_nested_alignment(closure_value, feasibility_value)
    # The request-only closure owns the sole all-253 traversal.  A separate
    # namespace traversal here would duplicate 506 projection reads.
    if corpus_closure.validate_corpus_input_closure_v3(closure_value) is not True:
        _fail("request-only corpus closure did not pass full validation")
    if resolution.validate_query_history_target_resolution(target) is not True:
        _fail("target resolution did not pass full validation")
    if (
        feasibility.validate_query_history_semantic_resolution_feasibility_audit(
            feasibility_value
        )
        is not True
    ):
        _fail("semantic feasibility audit did not pass independent validation")
    closing_raws = (
        namespace.corpus_semantic_namespace_v3_candidate_bytes(namespace_value),
        complete.canonical_json_bytes(inventory),
        resolution.canonical_json_bytes(target),
        corpus_closure.corpus_input_closure_v3_candidate_bytes(closure_value),
        feasibility.candidate_bytes(feasibility_value),
    )
    opening_raws = (
        namespace_raw,
        inventory_raw,
        target_raw,
        closure_raw,
        feasibility_raw,
    )
    if any(
        not hmac.compare_digest(opening, closing)
        for opening, closing in zip(opening_raws, closing_raws, strict=True)
    ):
        _fail("a direct dependency body changed during full validation")
    _require_live_nested_alignment(closure_value, feasibility_value)

    expected_pins = _expected_direct_pins()
    pins = [
        _pin_from_body(namespace_value, namespace_raw, expected=expected_pins[0]),
        _pin_from_body(inventory, inventory_raw, expected=expected_pins[1]),
        _pin_from_body(target, target_raw, expected=expected_pins[2]),
        _pin_from_body(closure_value, closure_raw, expected=expected_pins[3]),
        _pin_from_body(
            feasibility_value,
            feasibility_raw,
            expected=expected_pins[4],
        ),
    ]
    context = _corpus_context_summary()
    if (
        context["cumulative_external_projection_bytes"]
        != namespace_value["summary"]["cumulative_external_projection_bytes"]
        or context["namespace_entry_count"]
        != namespace_value["summary"]["namespace_entry_count"]
        or context["namespace_issued"]
        != namespace_value["completion_claims"][
            "corpus_semantic_namespace_issued"
        ]
        or context["projection_class_count"]
        != namespace_value["summary"]["projection_class_count"]
    ):
        _fail("live namespace context differs from frozen summary")
    snapshot = {
        "corpus_context_summary": context,
        "dependency_pins": pins,
        "persona_coverage": _coverage_from_target(target),
        "transitive_resolution_input_commitment": _binding_rows_commitment(
            target
        ),
    }
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("live dependency snapshot differs from accepted frozen metadata")
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
        "max_direct_dependency_count": MAX_DIRECT_DEPENDENCY_COUNT,
        "max_direct_descriptor_bytes": MAX_DIRECT_DESCRIPTOR_BYTES,
        "max_expanded_node_count": MAX_EXPANDED_NODE_COUNT,
        "max_manifest_bytes": MAX_MANIFEST_BYTES,
        "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
        "max_persona_count": MAX_PERSONA_COUNT,
        "max_query_mapping_count": MAX_QUERY_MAPPING_COUNT,
        "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
        "max_transitive_binding_count": MAX_TRANSITIVE_BINDING_COUNT,
        "max_transitive_provider_bytes": MAX_TRANSITIVE_PROVIDER_BYTES,
        "null_float_or_negative_integer_allowed": False,
        "precanonical_expanded_structure_preflight_required": True,
        "self_hash_embedded": False,
        "target_manifest_bytes": TARGET_MANIFEST_BYTES,
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
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
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
            "dependency_pin_count": MAX_DIRECT_DEPENDENCY_COUNT,
            "mapped_distinct_distractor_source_count": 0,
            "negative_query_count": 300,
            "persona_count": MAX_PERSONA_COUNT,
            "positive_query_count": 1_800,
            "query_capability_mapping_count": MAX_QUERY_MAPPING_COUNT,
            "required_distinct_distractor_source_count": 5_400,
            "transitive_binding_count": MAX_TRANSITIVE_BINDING_COUNT,
        },
        "transitive_resolution_input_commitment": copy.deepcopy(
            snapshot["transitive_resolution_input_commitment"]
        ),
        "unresolved_distractor_sources": _unresolved_distractor_sources(),
        "unresolved_target_semantics": _unresolved_target_semantics(),
    }


def _require_snapshot(snapshot):
    if not _strict_equal(snapshot, _frozen_dependency_snapshot()):
        _fail("dependency snapshot differs from exact accepted metadata")


def _require_validator_golden_parity(independent=None):
    """Authenticate producer/validator golden parity before provider access."""

    producer_expected = _expected_golden()
    if independent is None:
        independent = _independent_validator()
    validator_expected = None if independent is None else getattr(
        independent,
        "_expected_golden",
        None,
    )
    if not callable(validator_expected):
        _fail("independent evaluation closure golden guard is unavailable")
    try:
        validator_expected = validator_expected()
    except Exception:
        _fail("independent evaluation closure golden is invalid")
    if not _strict_equal(producer_expected, validator_expected):
        _fail("producer and validator evaluation closure goldens differ")
    return producer_expected, independent


def _build_from_snapshot(snapshot):
    _expected_golden()
    _require_snapshot(snapshot)
    value = _expected_value(snapshot)
    raw = _canonical(value, label="evaluation target-resolution closure slice")
    if len(raw) > TARGET_MANIFEST_BYTES:
        _fail("evaluation closure slice exceeds its target byte budget")
    _require_expected_raw(raw)
    return value


def build_evaluation_target_resolution_closure_slice():
    """Build a detached compact slice from accepted frozen dependency pins."""

    _require_validator_golden_parity()
    return copy.deepcopy(_build_from_snapshot(_live_dependency_snapshot()))


def _independent_validator():
    try:
        from . import (
            persona_v2_evaluation_target_resolution_closure_slice_validator as independent,
        )
    except ImportError:  # pragma: no cover - direct-script compatibility
        try:
            import persona_v2_evaluation_target_resolution_closure_slice_validator as independent
        except ImportError:
            independent = None
    return independent


def canonical_json_bytes(value):
    _expected, independent = _require_validator_golden_parity()
    snapshot = None if independent is None else getattr(
        independent, "_snapshot_candidate", None
    )
    if not callable(snapshot):
        _fail("independent evaluation closure slice snapshot is unavailable")
    try:
        _detached, raw = snapshot(value)
    except Exception:
        raise PersonaV2EvaluationTargetResolutionClosureSliceError(
            "evaluation closure slice failed strict structural preflight"
        ) from None
    return _require_expected_raw(raw)


def validate_evaluation_target_resolution_closure_slice(value):
    _expected, independent = _require_validator_golden_parity()
    try:
        result = independent.validate_evaluation_target_resolution_closure_slice(
            value
        )
    except independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("independent evaluation closure slice validator did not return exact true")
    return True


def evaluation_target_resolution_closure_slice_sha256(value=None):
    _expected, independent = _require_validator_golden_parity()
    if value is None:
        value = build_evaluation_target_resolution_closure_slice()
    try:
        _opening_value, opening = independent._snapshot_candidate(value)
    except independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError as error:
        _fail(str(error))
    validate_evaluation_target_resolution_closure_slice(value)
    try:
        _closing_value, closing = independent._snapshot_candidate(value)
    except independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError as error:
        _fail(str(error))
    if not hmac.compare_digest(opening, closing):
        _fail("evaluation closure slice changed during validation-to-hash")
    return _sha256(opening)


def require_full_evaluation_target_resolution_closure_slice():
    """Build and fully revalidate every external dependency trust source."""

    producer_expected, independent = _require_validator_golden_parity()
    value = _build_from_snapshot(_frozen_dependency_snapshot())
    try:
        result = independent.validate_evaluation_target_resolution_closure_slice_full(
            value,
            producer_expected_golden=producer_expected,
        )
    except independent.PersonaV2EvaluationTargetResolutionClosureSliceValidationError as error:
        _fail(str(error))
    if result is not True:
        _fail("full independent evaluation closure validation was not exact true")
    return copy.deepcopy(value)


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_MANIFEST_BYTES",
    "PersonaV2EvaluationTargetResolutionClosureSliceError",
    "build_evaluation_target_resolution_closure_slice",
    "canonical_json_bytes",
    "evaluation_target_resolution_closure_slice_sha256",
    "require_full_evaluation_target_resolution_closure_slice",
    "validate_evaluation_target_resolution_closure_slice",
]
