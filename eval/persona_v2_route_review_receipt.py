"""Canonical negative-authority review receipt for persona-PC v2 routing.

The route-affinity candidate has deterministic machine-review precursors, but
there is no independently supplied reviewer identity, review statement, or
reasoned waiver evidence.  This sidecar binds the exact reviewed route body and
records that gap as an unwaived blocking violation.  It is deliberately unable
to mint a positive review: a future independent-review evidence schema and
validator must remain a separate change.

This module never authorizes solver execution, a G0 freeze, source planning,
filesystem writes, or history mutation.
"""

from __future__ import annotations

import copy

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_route_affinity as route_affinity
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_route_affinity as route_affinity


ARTIFACT_SCHEMA = "kcs.persona.pc-route-review-receipt/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-route-review-receipt"
COMPLETION_SCOPE = (
    "negative-machine-review-precursor-only-no-independent-review-evidence-"
    "no-positive-authority"
)
MAX_ROUTE_REVIEW_RECEIPT_BYTES = 32 * 1024

ROUTE_ARTIFACT_PRODUCER_ID = "persona-v2-route-affinity-candidate-authors"
MACHINE_CHECKER_ID = "persona-v2-route-review-machine-precursor-v1"
ABSENT_REVIEWER_ID = "absent"

TOP_LEVEL_FIELD_ORDER = (
    "artifact_kind",
    "artifact_schema",
    "artifact_schema_version",
    "authority",
    "authoritative_review_blockers",
    "checks",
    "completion_scope",
    "fixture_id",
    "fixture_schema_version",
    "g0_contract_frozen",
    "review_participants",
    "review_summary",
    "reviewed_route_artifact",
    "route_affinity_matrix_review_receipt_bound",
    "violations",
    "waivers",
)
TOP_LEVEL_FIELDS = frozenset(TOP_LEVEL_FIELD_ORDER)
AUTHORITY_FIELD_ORDER = (
    "authorizes_g0_freeze",
    "authorizes_solver_execution",
    "authorizes_source_plan",
    "authorizes_write_or_history",
    "review_authoritative",
)
AUTHORITY_FIELDS = frozenset(AUTHORITY_FIELD_ORDER)
REVIEWED_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_body_bytes",
        "canonical_body_sha256",
    }
)
PARTICIPANT_FIELDS = frozenset(
    {
        "artifact_producer_id",
        "identity_evidence_scheme",
        "independence_attested",
        "independent_reviewer_evidence_present",
        "independent_reviewer_id",
        "machine_checker_id",
        "review_method",
    }
)
CHECK_FIELDS = frozenset(
    {
        "check_class",
        "check_id",
        "expected",
        "observed",
        "result",
        "waiver_policy",
    }
)
VIOLATION_FIELDS = frozenset(
    {"check_id", "disposition", "severity", "violation_id"}
)
SUMMARY_FIELDS = frozenset(
    {
        "blocking_violation_count",
        "check_count",
        "failed_check_count",
        "independent_review_complete",
        "machine_check_count",
        "machine_checks_passed",
        "passed_check_count",
        "review_authoritative",
        "waiver_count",
    }
)

CHECK_ID_ORDER = (
    "exact-route-artifact-binding",
    "declared-axis-projection",
    "row-maximum-equals-four",
    "maximum-score-scope-count-one-through-eight",
    "no-secondary-only-row-maximum",
    "no-cross-person-same-variant-vector-clone",
    "all-persona-scopes-covered-by-score-at-least-two",
    "score-zero-soft-preference-semantics",
    "independent-review-evidence-bound",
)

AUTHORITATIVE_REVIEW_BLOCKERS = (
    "independent-reviewer-identity-evidence-absent",
    "independent-reviewer-distinctness-not-attested",
    "independent-review-statement-not-bound",
)


class PersonaV2RouteReviewReceiptError(ValueError):
    """Raised when the negative route-review receipt contract is violated."""


def _exact_dict(value, fields, label):
    if type(value) is not dict or set(value) != fields:
        raise PersonaV2RouteReviewReceiptError(
            f"{label} must be an exact object with no missing or unknown fields"
        )
    return value


def _validated_route_binding(reviewed_route=None):
    if reviewed_route is None:
        reviewed_route = route_affinity.build_route_affinity()
    try:
        route_affinity.validate_route_affinity(reviewed_route)
        raw = route_affinity.canonical_json_bytes(reviewed_route)
        sha256 = route_affinity.route_affinity_sha256(reviewed_route)
    except route_affinity.PersonaV2RouteAffinityError as error:
        raise PersonaV2RouteReviewReceiptError(
            f"reviewed route artifact is invalid: {error}"
        ) from None
    return reviewed_route, raw, sha256


def _machine_checks(reviewed_route, route_sha256):
    diagnostics = route_affinity.candidate_review_diagnostics()
    rows = reviewed_route["rows"]
    observed_cells = sum(len(row["scores_by_scope_ordinal"]) for row in rows)
    if diagnostics["full_active_rows"] != len(rows):
        raise PersonaV2RouteReviewReceiptError(
            "route diagnostic row count differs from the reviewed artifact"
        )
    if diagnostics["route_score_cells"] != observed_cells:
        raise PersonaV2RouteReviewReceiptError(
            "route diagnostic cell count differs from the reviewed artifact"
        )

    checks = [
        {
            "check_class": "machine-precursor",
            "check_id": "exact-route-artifact-binding",
            "expected": route_sha256,
            "observed": route_sha256,
            "result": "pass",
            "waiver_policy": "not-waivable",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "declared-axis-projection",
            "expected": "declared=566;active=541;hard-zero=25;out-of-domain=854;cells=10820",
            "observed": (
                f"declared={diagnostics['declared_persona_variant_rows']};"
                f"active={diagnostics['full_active_rows']};"
                f"hard-zero={diagnostics['declared_hard_zero_rows']};"
                f"out-of-domain={diagnostics['out_of_domain_persona_variant_pairs']};"
                f"cells={diagnostics['route_score_cells']}"
            ),
            "result": "pass",
            "waiver_policy": "not-waivable",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "row-maximum-equals-four",
            "expected": "violation-count=0",
            "observed": f"violation-count={len(diagnostics['row_maximum_not_four'])}",
            "result": "pass",
            "waiver_policy": "not-waivable",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "maximum-score-scope-count-one-through-eight",
            "expected": "violation-count=0",
            "observed": (
                "violation-count="
                f"{len(diagnostics['maximum_scope_count_out_of_bounds'])}"
            ),
            "result": "pass",
            "waiver_policy": "independent-reasoned-waiver-required",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "no-secondary-only-row-maximum",
            "expected": "violation-count=0",
            "observed": (
                f"violation-count={len(diagnostics['secondary_only_maximum_rows'])}"
            ),
            "result": "pass",
            "waiver_policy": "independent-reasoned-waiver-required",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "no-cross-person-same-variant-vector-clone",
            "expected": "violation-count=0",
            "observed": (
                "violation-count="
                f"{len(diagnostics['cross_person_same_variant_vector_clones'])}"
            ),
            "result": "pass",
            "waiver_policy": "independent-reasoned-waiver-required",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "all-persona-scopes-covered-by-score-at-least-two",
            "expected": "violation-count=0",
            "observed": (
                "violation-count="
                f"{len(diagnostics['uncovered_persona_scopes_below_score_two'])}"
            ),
            "result": "pass",
            "waiver_policy": "not-waivable",
        },
        {
            "check_class": "machine-precursor",
            "check_id": "score-zero-soft-preference-semantics",
            "expected": route_affinity.SCORE_ZERO_SEMANTICS,
            "observed": diagnostics["score_zero_semantics"],
            "result": "pass",
            "waiver_policy": "not-waivable",
        },
        {
            "check_class": "independent-review-evidence",
            "check_id": "independent-review-evidence-bound",
            "expected": "present-distinct-reasoned-and-hash-bound",
            "observed": "absent",
            "result": "fail",
            "waiver_policy": "not-waivable-by-machine-receipt",
        },
    ]
    if tuple(check["check_id"] for check in checks) != CHECK_ID_ORDER:
        raise PersonaV2RouteReviewReceiptError("route review check order drifted")
    if any(
        check["result"] != "pass"
        for check in checks
        if check["check_class"] == "machine-precursor"
    ):
        raise PersonaV2RouteReviewReceiptError(
            "a route machine-review precursor did not pass"
        )
    return checks


def _canonical_negative_receipt(reviewed_route=None):
    reviewed_route, route_raw, route_sha256 = _validated_route_binding(reviewed_route)
    checks = _machine_checks(reviewed_route, route_sha256)
    violations = [
        {
            "check_id": "independent-review-evidence-bound",
            "disposition": "unwaived",
            "severity": "blocking",
            "violation_id": "independent-review-evidence-absent",
        }
    ]
    waivers = []
    machine_checks = [
        check for check in checks if check["check_class"] == "machine-precursor"
    ]
    passed = sum(check["result"] == "pass" for check in checks)
    failed = sum(check["result"] == "fail" for check in checks)
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "authorizes_g0_freeze": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "authorizes_write_or_history": False,
            "review_authoritative": False,
        },
        "authoritative_review_blockers": list(AUTHORITATIVE_REVIEW_BLOCKERS),
        "checks": checks,
        "completion_scope": COMPLETION_SCOPE,
        "fixture_id": reviewed_route["fixture_id"],
        "fixture_schema_version": reviewed_route["fixture_schema_version"],
        "g0_contract_frozen": False,
        "review_participants": {
            "artifact_producer_id": ROUTE_ARTIFACT_PRODUCER_ID,
            "identity_evidence_scheme": "none-negative-receipt",
            "independence_attested": False,
            "independent_reviewer_evidence_present": False,
            "independent_reviewer_id": ABSENT_REVIEWER_ID,
            "machine_checker_id": MACHINE_CHECKER_ID,
            "review_method": "deterministic-machine-precursors-only",
        },
        "review_summary": {
            "blocking_violation_count": 1,
            "check_count": len(checks),
            "failed_check_count": failed,
            "independent_review_complete": False,
            "machine_check_count": len(machine_checks),
            "machine_checks_passed": all(
                check["result"] == "pass" for check in machine_checks
            ),
            "passed_check_count": passed,
            "review_authoritative": False,
            "waiver_count": len(waivers),
        },
        "reviewed_route_artifact": {
            "artifact_kind": reviewed_route["artifact_kind"],
            "artifact_schema": reviewed_route["artifact_schema"],
            "artifact_schema_version": reviewed_route["artifact_schema_version"],
            "canonical_body_bytes": len(route_raw),
            "canonical_body_sha256": route_sha256,
        },
        "route_affinity_matrix_review_receipt_bound": False,
        "violations": violations,
        "waivers": waivers,
    }
    _require_negative_semantics(value)
    return value


def _require_negative_semantics(value):
    _exact_dict(value, TOP_LEVEL_FIELDS, "route review receipt")
    authority = _exact_dict(value["authority"], AUTHORITY_FIELDS, "authority")
    if any(type(flag) is not bool for flag in authority.values()):
        raise PersonaV2RouteReviewReceiptError(
            "authority flags must be exact booleans"
        )
    if any(authority.values()):
        raise PersonaV2RouteReviewReceiptError(
            "negative route review receipt rejects positive authority"
        )
    if value["g0_contract_frozen"] is not False:
        raise PersonaV2RouteReviewReceiptError(
            "negative route review receipt cannot freeze G0"
        )
    if value["route_affinity_matrix_review_receipt_bound"] is not False:
        raise PersonaV2RouteReviewReceiptError(
            "negative route review receipt cannot mark review evidence bound"
        )

    participants = _exact_dict(
        value["review_participants"], PARTICIPANT_FIELDS, "review participants"
    )
    producer_id = participants["artifact_producer_id"]
    reviewer_id = participants["independent_reviewer_id"]
    if type(producer_id) is not str or type(reviewer_id) is not str:
        raise PersonaV2RouteReviewReceiptError(
            "review participant identifiers must be strings"
        )
    if reviewer_id == producer_id:
        raise PersonaV2RouteReviewReceiptError(
            "self-review cannot satisfy independent route review"
        )
    if (
        participants["independent_reviewer_evidence_present"] is not False
        or participants["independence_attested"] is not False
    ):
        raise PersonaV2RouteReviewReceiptError(
            "negative receipt cannot claim unvalidated independent review evidence"
        )
    if reviewer_id != ABSENT_REVIEWER_ID:
        raise PersonaV2RouteReviewReceiptError(
            "negative receipt cannot name an unbound independent reviewer"
        )

    reviewed = _exact_dict(
        value["reviewed_route_artifact"],
        REVIEWED_ARTIFACT_FIELDS,
        "reviewed route artifact binding",
    )
    if type(reviewed["canonical_body_bytes"]) is not int:
        raise PersonaV2RouteReviewReceiptError(
            "reviewed route canonical byte count must be an integer"
        )
    digest = reviewed["canonical_body_sha256"]
    if (
        type(digest) is not str
        or len(digest) != 64
        or any(character not in "0123456789abcdef" for character in digest)
    ):
        raise PersonaV2RouteReviewReceiptError(
            "reviewed route SHA-256 must be lowercase hexadecimal"
        )

    checks = value["checks"]
    if type(checks) is not list or len(checks) != len(CHECK_ID_ORDER):
        raise PersonaV2RouteReviewReceiptError(
            "route review checks must enumerate the exact rubric"
        )
    for check in checks:
        _exact_dict(check, CHECK_FIELDS, "route review check")
    if tuple(check["check_id"] for check in checks) != CHECK_ID_ORDER:
        raise PersonaV2RouteReviewReceiptError(
            "route review checks must use canonical rubric order"
        )

    violations = value["violations"]
    waivers = value["waivers"]
    if type(violations) is not list or len(violations) != 1:
        raise PersonaV2RouteReviewReceiptError(
            "negative receipt must enumerate its blocking review violation"
        )
    _exact_dict(violations[0], VIOLATION_FIELDS, "route review violation")
    if type(waivers) is not list or waivers:
        raise PersonaV2RouteReviewReceiptError(
            "negative machine receipt cannot carry independent-review waivers"
        )

    summary = _exact_dict(
        value["review_summary"], SUMMARY_FIELDS, "route review summary"
    )
    if summary["review_authoritative"] is not False:
        raise PersonaV2RouteReviewReceiptError(
            "negative route review receipt rejects positive review authority"
        )
    if summary["independent_review_complete"] is not False:
        raise PersonaV2RouteReviewReceiptError(
            "independent review cannot be complete without bound evidence"
        )


def build_negative_route_review_receipt(reviewed_route=None):
    """Return a detached receipt proving only machine-review precursor status."""

    return copy.deepcopy(_canonical_negative_receipt(reviewed_route))


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 negative route-review receipt",
            max_bytes=MAX_ROUTE_REVIEW_RECEIPT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteReviewReceiptError(str(error)) from None


def validate_negative_route_review_receipt(value, reviewed_route=None):
    """Validate exact bindings while rejecting self-review and positive authority."""

    _require_negative_semantics(value)
    _, route_raw, route_sha256 = _validated_route_binding(reviewed_route)
    binding = value["reviewed_route_artifact"]
    if (
        binding["canonical_body_bytes"] != len(route_raw)
        or binding["canonical_body_sha256"] != route_sha256
    ):
        raise PersonaV2RouteReviewReceiptError(
            "receipt does not bind the exact reviewed route artifact"
        )
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_negative_route_review_receipt(reviewed_route),
            label="persona v2 negative route-review receipt",
            max_bytes=MAX_ROUTE_REVIEW_RECEIPT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteReviewReceiptError(str(error)) from None


def route_review_receipt_sha256(value=None, reviewed_route=None):
    if value is None:
        value = build_negative_route_review_receipt(reviewed_route)
    validate_negative_route_review_receipt(value, reviewed_route)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_negative_route_review_receipt(reviewed_route),
            label="persona v2 negative route-review receipt",
            max_bytes=MAX_ROUTE_REVIEW_RECEIPT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2RouteReviewReceiptError(str(error)) from None


def require_authoritative_route_review(value=None, reviewed_route=None):
    """Fail closed: this schema cannot establish independent review authority."""

    if value is not None:
        validate_negative_route_review_receipt(value, reviewed_route)
    raise PersonaV2RouteReviewReceiptError(
        "independent route review evidence is absent; the negative receipt grants "
        "no review, solver, source-plan, G0, write, or history authority"
    )
