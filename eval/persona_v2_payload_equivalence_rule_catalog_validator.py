"""Producer-independent validation for payload-equivalence rule projection.

This module intentionally does not import the sibling catalog producer.  It
reconstructs the catalog, normative source fragment, projection body, and
integration material from the four frozen upstream full owners.  Every public
body-validation call performs opening owner authentication and a final
postflight reauthentication; no mutable derived object is cached.
"""

from __future__ import annotations

import copy
import hashlib
import hmac
import json

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_concrete_overlay_membership_package as concrete
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay
    from . import persona_v2_source_parameter_assignment_package as parameters
    from . import persona_v2_source_semantic_membership_package as semantic
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_concrete_overlay_membership_package as concrete
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay
    import persona_v2_source_parameter_assignment_package as parameters
    import persona_v2_source_semantic_membership_package as semantic


ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_SCHEMA = "kio.persona.pc-payload-equivalence-rule-catalog/v1"
ARTIFACT_KIND = "persona-pc-v2-payload-equivalence-rule-catalog"
PROJECTION_SCHEMA = "kio.persona.pc-payload-equivalence-rules-projection/v1"
PROJECTION_KIND = "persona-pc-v2-payload-equivalence-rules-projection"
PROJECTION_CLASS_ID = "payload-equivalence-rules"
BODY_FRAMING = "canonical-json"
PROJECTOR_ID = "payload-equivalence-rules-content-projector"
RECEIPT_ID = "payload-equivalence-rules-global"

MAX_CATALOG_BYTES = 128 * 2**10
MAX_PROJECTION_BYTES = 16 * 2**10
MAX_FRAGMENT_BYTES = 16 * 2**10

# Frozen from the first clean reconstruction.  Focused tests reproduce all
# three pins in cold interpreters under two distinct hash seeds.
EXPECTED_CATALOG_BYTES = 8_649
EXPECTED_CATALOG_SHA256 = (
    "00dc78f6dd54a06e2669ffaeea08afdb56d2fe6bd978d342ca10cc3ed5919128"
)
EXPECTED_PROJECTION_BYTES = 4_288
EXPECTED_PROJECTION_SHA256 = (
    "05f8124cd1bd09652701d38ffd702824f3cff8d40a161815969071cd678e14e1"
)
EXPECTED_FRAGMENT_BYTES = 4_056
EXPECTED_FRAGMENT_SHA256 = (
    "91486a1d8b1190c187b8ca906cd16ace17d739896aaa77de3fd999bd847e2828"
)

RULE_ORDER = (
    "default",
    "exact-duplicate",
    "near-revision",
    "conflict-copy",
    "decoded-attachment",
)
OWNER_ORDER = (
    "persona-v2-overlay-contract",
    "persona-v2-source-semantic-membership-suite",
    "persona-v2-concrete-overlay-membership-suite",
    "persona-v2-source-parameter-assignment-suite",
)

OVERLAY_OWNER_BYTES = 71_179
OVERLAY_OWNER_SHA256 = (
    "e9154297f6dd5cf30ccbcc819d725cb08c533ec84a7b2df359937ddfb6517c23"
)
SEMANTIC_OWNER_BYTES = 49_837
SEMANTIC_OWNER_SHA256 = (
    "6027147bff72129aa308daa79c10581f6eceec9b04eb4667dbe72c0194ac6072"
)
CONCRETE_OWNER_BYTES = 51_133
CONCRETE_OWNER_SHA256 = (
    "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737"
)
PARAMETER_OWNER_BYTES = 72_535
PARAMETER_OWNER_SHA256 = (
    "42c437213fa9cd0c48ad0ca05477d968aba3d62d87be7ba23e9c201c473699e3"
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "actual_payload_bytes_attested",
        "authorizes_compiled_history_plan",
        "authorizes_corpus_semantic_namespace",
        "authorizes_final_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_completion",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_identity_derivation",
        "authorizes_source_plan",
        "compiled_history_plan_available",
        "corpus_semantic_namespace_available",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "history_executor_available",
        "kio_execution_available",
        "physical_materialization_observed",
        "solver_solution_available",
        "source_identity_namespace_authoritative",
    }
)
CATALOG_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "dependency_direction_contract",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "orders",
        "remaining_blockers",
        "rule_catalog",
        "summary",
    }
)
RULE_CATALOG_FIELDS = frozenset(
    {"precedence_contract", "rule_order", "rules"}
)
RULE_FIELDS = frozenset(
    {
        "applies_when",
        "attachment_relation",
        "decoded_payload_relation",
        "logical_identity_relation",
        "parameter_cell_relation",
        "payload_equivalence_key_relation",
        "precedence_ordinal",
        "raw_payload_relation",
        "rule_id",
        "semantic_version_relation",
        "structural_seed_relation",
    }
)
PROJECTION_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "fixture_id",
        "fixture_schema_version",
        "precedence_contract",
        "rule_order",
        "rules",
    }
)
INPUT_BINDING_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "dependency_role",
        "name",
        "sha256",
    }
)
FULL_OWNER_PIN_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body_framing",
        "canonical_bytes",
        "coordinates",
        "owner_id",
        "owner_role",
        "sha256",
    }
)
DIRECT_PIN_FIELDS = frozenset(
    {
        "body_framing",
        "canonical_bytes",
        "direct_pin_id",
        "direct_pin_role",
        "sha256",
    }
)
MATERIAL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "body",
        "body_framing",
        "coordinates",
        "direct_body_pins",
        "full_owner_pins",
        "projection_class_id",
        "projector_id",
        "receipt_id",
    }
)
FORBIDDEN_PROJECTION_KEY_TOKENS = frozenset(
    {
        "answer",
        "authority",
        "blocker",
        "completion",
        "distractor",
        "evidence",
        "final",
        "oracle",
        "owner",
        "pin",
        "query",
        "review",
        "runtime",
        "solution",
        "observed",
    }
)


class PersonaV2PayloadEquivalenceRuleCatalogValidationError(ValueError):
    """Raised on any independent catalog, body, or owner-chain mismatch."""


def _fail(message):
    raise PersonaV2PayloadEquivalenceRuleCatalogValidationError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _canonical(value, *, label, maximum):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=maximum,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _reject_json_number(_value):
    raise ValueError("floats and non-finite numbers are forbidden")


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _strict_object(raw, *, label, maximum):
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        _fail(f"{label} must be non-empty bounded exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict JSON: {error}")
    if type(value) is not dict:
        _fail(f"{label} must decode to an object")
    recanonical = _canonical(value, label=label, maximum=maximum)
    if not hmac.compare_digest(raw, recanonical):
        _fail(f"{label} is not exact canonical JSON")
    return value


def _pinned(raw, *, expected_bytes, expected_sha256, label):
    if type(expected_bytes) is not int or type(expected_sha256) is not str:
        _fail(f"{label} frozen pin is not installed")
    if len(raw) != expected_bytes or not hmac.compare_digest(
        _sha256(raw), expected_sha256
    ):
        _fail(f"{label} differs from its frozen canonical pin")


def _owner_specs():
    return (
        {
            "artifact_kind": overlay.ARTIFACT_KIND,
            "artifact_schema": overlay.ARTIFACT_SCHEMA,
            "artifact_schema_version": overlay.ARTIFACT_SCHEMA_VERSION,
            "builder": overlay.build_overlay_contract,
            "canonicalizer": overlay.canonical_json_bytes,
            "canonical_bytes": OVERLAY_OWNER_BYTES,
            "dependency_role": "overlay-payload-relation-semantics-owner",
            "name": OWNER_ORDER[0],
            "sha256": OVERLAY_OWNER_SHA256,
        },
        {
            "artifact_kind": semantic.SUITE_ARTIFACT_KIND,
            "artifact_schema": semantic.SUITE_ARTIFACT_SCHEMA,
            "artifact_schema_version": semantic.ARTIFACT_SCHEMA_VERSION,
            "builder": semantic.build_source_semantic_membership_suite_descriptor,
            "canonicalizer": semantic.canonical_json_bytes,
            "canonical_bytes": SEMANTIC_OWNER_BYTES,
            "dependency_role": "base-content-context-and-logical-identity-owner",
            "name": OWNER_ORDER[1],
            "sha256": SEMANTIC_OWNER_SHA256,
        },
        {
            "artifact_kind": concrete.SUITE_ARTIFACT_KIND,
            "artifact_schema": concrete.SUITE_ARTIFACT_SCHEMA,
            "artifact_schema_version": concrete.ARTIFACT_SCHEMA_VERSION,
            "builder": concrete.build_concrete_overlay_membership_suite_descriptor,
            "canonicalizer": concrete.canonical_json_bytes,
            "canonical_bytes": CONCRETE_OWNER_BYTES,
            "dependency_role": "concrete-overlay-relation-and-attachment-owner",
            "name": OWNER_ORDER[2],
            "sha256": CONCRETE_OWNER_SHA256,
        },
        {
            "artifact_kind": parameters.SUITE_KIND,
            "artifact_schema": parameters.SUITE_SCHEMA,
            "artifact_schema_version": parameters.ARTIFACT_SCHEMA_VERSION,
            "builder": parameters.build_source_parameter_assignment_suite_descriptor,
            "canonicalizer": parameters.canonical_json_bytes,
            "canonical_bytes": PARAMETER_OWNER_BYTES,
            "dependency_role": "exact-pair-cell-and-eml-parameter-owner",
            "name": OWNER_ORDER[3],
            "sha256": PARAMETER_OWNER_SHA256,
        },
    )


def _fresh_owner_records():
    records = []
    for spec in _owner_specs():
        value = spec["builder"]()
        if type(value) is not dict:
            _fail(f"{spec['name']} builder did not return an exact object")
        raw = spec["canonicalizer"](value)
        if type(raw) is not bytes:
            _fail(f"{spec['name']} canonicalizer did not return exact bytes")
        _pinned(
            raw,
            expected_bytes=spec["canonical_bytes"],
            expected_sha256=spec["sha256"],
            label=spec["name"],
        )
        snapshot = _strict_object(
            raw,
            label=spec["name"],
            maximum=spec["canonical_bytes"],
        )
        if (
            snapshot.get("artifact_kind") != spec["artifact_kind"]
            or snapshot.get("artifact_schema") != spec["artifact_schema"]
            or snapshot.get("artifact_schema_version")
            != spec["artifact_schema_version"]
        ):
            _fail(f"{spec['name']} artifact identity drifted")
        records.append({"raw": bytes(raw), "spec": spec, "value": snapshot})
    return tuple(records)


def _postflight_owners(opening):
    closing = _fresh_owner_records()
    if len(opening) != len(closing):
        _fail("payload-equivalence owner-chain cardinality changed")
    for first, last in zip(opening, closing, strict=True):
        if (
            first["spec"]["name"] != last["spec"]["name"]
            or not hmac.compare_digest(first["raw"], last["raw"])
        ):
            _fail("payload-equivalence owner changed during validation")
    return closing


def _postflight_derivation(
    opening_owners,
    *,
    catalog_raw=None,
    fragment_raw=None,
    projection_raw=None,
):
    """Rebuild every direct role after the closing owner callbacks."""

    closing_owners = _postflight_owners(opening_owners)
    closing_catalog = _expected_catalog_raw(closing_owners)
    if catalog_raw is not None and not hmac.compare_digest(
        catalog_raw, closing_catalog
    ):
        _fail("payload-equivalence catalog changed during owner postflight")
    if fragment_raw is None and projection_raw is None:
        return True
    closing_fragment = _expected_fragment_raw(closing_catalog)
    if fragment_raw is not None and not hmac.compare_digest(
        fragment_raw, closing_fragment
    ):
        _fail("payload-equivalence direct fragment changed during owner postflight")
    if projection_raw is None:
        return True
    closing_projection = _expected_projection_raw(closing_fragment)
    if not hmac.compare_digest(projection_raw, closing_projection):
        _fail("payload-equivalence projection changed during owner postflight")
    return True


def _input_binding(record):
    spec = record["spec"]
    value = {
        "artifact_kind": spec["artifact_kind"],
        "artifact_schema": spec["artifact_schema"],
        "artifact_schema_version": spec["artifact_schema_version"],
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(record["raw"]),
        "dependency_role": spec["dependency_role"],
        "name": spec["name"],
        "sha256": _sha256(record["raw"]),
    }
    if set(value) != INPUT_BINDING_FIELDS:
        _fail("independent input-binding schema drifted")
    return value


def _owner_algebra(records):
    by_name = {record["spec"]["name"]: record["value"] for record in records}
    contract = by_name[OWNER_ORDER[0]]
    semantic_summary = by_name[OWNER_ORDER[1]]["summary"]
    concrete_summary = by_name[OWNER_ORDER[2]]["summary"]
    parameter_coverage = by_name[OWNER_ORDER[3]]["coverage"]
    expected_semantics = {
        "exact-duplicate": (
            "same-branch",
            "exactly-equal",
            "same-logical-revision",
            "same-logical-document",
            "same-raw-sha256",
        ),
        "near-revision": (
            "same-linear-branch",
            "different-but-semantically-near",
            "distinct-strictly-ordered-revisions",
            "same-logical-document",
            "different-raw-sha256",
        ),
        "conflict-copy": (
            "distinct-unordered-branches",
            "different-with-conflicting-typed-fact-required",
            "branch-distinct-no-linear-order",
            "same-logical-document",
            "different-raw-sha256",
        ),
    }
    actual_semantics = {
        row["relation_kind"]: (
            row["branch_relation"],
            row["decoded_payload_relation"],
            row["document_revision_relation"],
            row["logical_document_relation"],
            row["raw_identity_relation"],
        )
        for row in contract["content_relation_semantics"]
    }
    targets = contract["suite_target_marginals"]["full"]
    expected_targets = {
        "attachment_exact_duplicate_overlap_count": 1_390,
        "attachment_membership_count": 5_690,
        "conflict_copy_cluster_count": 1_560,
        "content_relation_cluster_count": 19_870,
        "content_relation_endpoint_reference_count": 39_740,
        "exact_duplicate_cluster_count": 5_080,
        "membership_row_count": 25_560,
        "near_revision_cluster_count": 13_230,
    }
    attachment = contract["attachment_contract"]
    if actual_semantics != expected_semantics:
        _fail("independent overlay relation semantics drifted")
    if any(targets.get(key) != value for key, value in expected_targets.items()):
        _fail("independent overlay target marginals drifted")
    if (
        attachment.get("decoded_embedded_payload_must_equal_standalone_payload")
        is not True
        or attachment.get("attachment_axis_is_orthogonal_to_content_relation_axis")
        is not True
        or attachment.get("exact_duplicate_overlap_is_the_only_content_relation_overlap")
        is not True
        or attachment.get("host_and_standalone_intent_must_differ") is not True
        or attachment.get("standalone_and_embedded_member_share_logical_document_revision")
        is not True
    ):
        _fail("independent overlay attachment semantics drifted")
    if (
        semantic_summary.get("source_count") != 203_000
        or semantic_summary.get("semantic_version_source_counts")
        != {"v1": 189_770, "v2": 13_230}
        or concrete_summary.get("exact_duplicate_row_count") != 5_080
        or concrete_summary.get("near_revision_row_count") != 13_230
        or concrete_summary.get("conflict_copy_row_count") != 1_560
        or concrete_summary.get("attachment_membership_row_count") != 5_690
        or concrete_summary.get("attachment_exact_overlap_row_count") != 1_390
        or concrete_summary.get("attachment_host_count") != 2_800
        or concrete_summary.get("unique_overlay_source_count") != 46_840
        or parameter_coverage.get("source_intent_count") != 203_000
        or parameter_coverage.get("concrete_exact_duplicate_pair_count") != 5_080
        or parameter_coverage.get("eml_attachment_membership_count") != 5_690
        or parameter_coverage.get("eml_fixed_host_source_count") != 2_800
    ):
        _fail("independent payload cross-owner coverage drifted")
    relation_endpoints = 2 * (
        concrete_summary["exact_duplicate_row_count"]
        + concrete_summary["near_revision_row_count"]
        + concrete_summary["conflict_copy_row_count"]
    )
    attachment_only = (
        concrete_summary["attachment_host_count"]
        + concrete_summary["attachment_membership_row_count"]
        - concrete_summary["attachment_exact_overlap_row_count"]
    )
    default_sources = semantic_summary["source_count"] - concrete_summary[
        "unique_overlay_source_count"
    ]
    unique_payload_keys = (
        semantic_summary["source_count"]
        - concrete_summary["exact_duplicate_row_count"]
    )
    if (
        relation_endpoints != 39_740
        or attachment_only != 7_100
        or relation_endpoints + attachment_only != 46_840
        or default_sources != 156_160
        or unique_payload_keys != 197_920
    ):
        _fail("independent payload source algebra drifted")
    return {
        "attachment_exact_overlap_count": 1_390,
        "attachment_membership_count": 5_690,
        "attachment_only_source_count": attachment_only,
        "conflict_endpoint_count": 3_120,
        "default_source_count": default_sources,
        "exact_endpoint_count": 10_160,
        "exact_equivalence_group_count": 5_080,
        "near_endpoint_count": 26_460,
        "relation_endpoint_count": relation_endpoints,
        "source_intent_count": 203_000,
        "unique_overlay_source_count": 46_840,
        "unique_source_payload_equivalence_key_count": unique_payload_keys,
    }


def _expected_rules():
    rows = [
        {
            "applies_when": (
                "intent-has-no-content-relation-endpoint-role-and-no-attachment-"
                "host-or-standalone-member-role"
            ),
            "attachment_relation": "not-an-explicit-attachment-participant",
            "decoded_payload_relation": "one-source-local-decoded-payload",
            "logical_identity_relation": (
                "one-source-local-document-branch-revision-and-section"
            ),
            "parameter_cell_relation": (
                "independently-owned-by-source-parameter-assignment"
            ),
            "payload_equivalence_key_relation": (
                "equals-that-intent-deterministic-payload-seed"
            ),
            "precedence_ordinal": 1,
            "raw_payload_relation": "one-source-local-payload-recipe",
            "rule_id": "default",
            "semantic_version_relation": "v1",
            "structural_seed_relation": "one-source-local-structural-seed",
        },
        {
            "applies_when": "intent-is-an-explicit-exact-duplicate-endpoint",
            "attachment_relation": (
                "standalone-member-overlap-allowed-only-on-exact-derivative-and-"
                "inherits-transitive-exact-equality"
            ),
            "decoded_payload_relation": "anchor-and-derivative-exactly-equal",
            "logical_identity_relation": "same-document-branch-revision-and-section",
            "parameter_cell_relation": (
                "same-non-eml-parameter-cell-for-both-endpoints"
            ),
            "payload_equivalence_key_relation": (
                "same-key-for-anchor-and-derivative"
            ),
            "precedence_ordinal": 2,
            "raw_payload_relation": "same-raw-sha256",
            "rule_id": "exact-duplicate",
            "semantic_version_relation": "anchor-v1-and-derivative-v1",
            "structural_seed_relation": "endpoint-seeds-must-be-distinct",
        },
        {
            "applies_when": "intent-is-an-explicit-near-revision-endpoint",
            "attachment_relation": "no-attachment-overlap-allowed",
            "decoded_payload_relation": (
                "anchor-and-derivative-different-but-semantically-near"
            ),
            "logical_identity_relation": (
                "same-document-branch-and-section-with-distinct-strictly-"
                "ordered-revisions"
            ),
            "parameter_cell_relation": "endpoint-cell-equality-is-unconstrained",
            "payload_equivalence_key_relation": (
                "distinct-keys-for-anchor-and-derivative"
            ),
            "precedence_ordinal": 3,
            "raw_payload_relation": "different-raw-sha256",
            "rule_id": "near-revision",
            "semantic_version_relation": "anchor-v1-and-derivative-v2",
            "structural_seed_relation": "endpoint-seeds-must-be-distinct",
        },
        {
            "applies_when": "intent-is-an-explicit-conflict-copy-endpoint",
            "attachment_relation": "no-attachment-overlap-allowed",
            "decoded_payload_relation": (
                "different-with-conflicting-persona-owned-typed-facts"
            ),
            "logical_identity_relation": (
                "same-document-and-section-with-distinct-unordered-branches-"
                "revisions-and-fact-profiles"
            ),
            "parameter_cell_relation": "endpoint-cell-equality-is-unconstrained",
            "payload_equivalence_key_relation": (
                "distinct-keys-for-anchor-and-derivative"
            ),
            "precedence_ordinal": 4,
            "raw_payload_relation": "different-raw-sha256",
            "rule_id": "conflict-copy",
            "semantic_version_relation": "anchor-v1-and-derivative-v1",
            "structural_seed_relation": "endpoint-seeds-must-be-distinct",
        },
        {
            "applies_when": (
                "intent-is-an-explicit-attachment-host-or-standalone-member-"
                "with-embedded-decoded-member"
            ),
            "attachment_relation": (
                "orthogonal-postcondition-after-content-rule-overlap-only-one-"
                "exact-derivative-at-member-ordinal-one"
            ),
            "decoded_payload_relation": (
                "embedded-decoded-member-exactly-equals-standalone-member"
            ),
            "logical_identity_relation": (
                "host-and-member-documents-differ-embedded-member-inherits-"
                "standalone-member-document-revision"
            ),
            "parameter_cell_relation": (
                "host-uses-eml-attachment-n-cell-member-uses-independent-non-"
                "eml-cell"
            ),
            "payload_equivalence_key_relation": (
                "host-and-member-keys-differ-embedded-decoded-key-equals-"
                "standalone-member-key"
            ),
            "precedence_ordinal": 5,
            "raw_payload_relation": (
                "host-container-raw-differs-embedded-decoded-bytes-equal-"
                "standalone-decoded-bytes"
            ),
            "rule_id": "decoded-attachment",
            "semantic_version_relation": "host-v1-and-member-v1",
            "structural_seed_relation": "host-and-member-seeds-must-be-distinct",
        },
    ]
    if (
        [row["rule_id"] for row in rows] != list(RULE_ORDER)
        or [row["precedence_ordinal"] for row in rows] != list(range(1, 6))
        or any(set(row) != RULE_FIELDS for row in rows)
    ):
        _fail("independent normative rule schema drifted")
    return rows


def _expected_rule_catalog():
    value = {
        "precedence_contract": {
            "attachment_rule_is_orthogonal_postcondition": True,
            "content_relation_rules_are_mutually_exclusive": True,
            "default_rule_requires_no_explicit_overlay_role": True,
            "exact_attachment_overlap_is_transitive_not-a-sixth-rule": True,
            "first_matching_content_rule_precedes_attachment_postcondition": True,
        },
        "rule_order": list(RULE_ORDER),
        "rules": _expected_rules(),
    }
    if set(value) != RULE_CATALOG_FIELDS:
        _fail("independent rule-catalog schema drifted")
    return value


def _expected_catalog_value(records):
    coverage = _owner_algebra(records)
    bindings = [_input_binding(record) for record in records]
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "canonical_limits": {
            "max_catalog_bytes": MAX_CATALOG_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_projection_bytes": MAX_PROJECTION_BYTES,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "actual_payload_bytes_attested": False,
            "all_203000_payload_keys_instantiated_by_this_catalog": False,
            "global_payload_equivalence_rule_catalog_complete": True,
            "projection_duplicates_instance_rows": False,
            "rule_owner_chain_bound": True,
        },
        "dependency_direction_contract": {
            "catalog_may_be_bound_by_future_namespace_inventory": True,
            "catalog_never_repins_or_mutates_upstream_owners": True,
            "four_full_upstream_owners_are_directly_bound": True,
            "upstream_back_reference_allowed": False,
        },
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-payload-equivalence-rules-not-rendered-byte-"
            "observations"
        ),
        "input_binding_order": list(OWNER_ORDER),
        "input_bindings": bindings,
        "orders": {
            "input_bindings": "exact-declared-owner-order",
            "rules": "default-exact-near-conflict-then-attachment-postcondition",
        },
        "remaining_blockers": [
            "rendered-raw-and-decoded-payload-byte-attestation",
            "semantic-namespace-and-final-identifier-issuance",
            "placement-render-write-history-kio-capacity-and-g0",
        ],
        "rule_catalog": _expected_rule_catalog(),
        "summary": {
            **coverage,
            "input_owner_count": len(bindings),
            "projection_body_count": 1,
            "rule_count": len(RULE_ORDER),
        },
    }
    if set(value) != CATALOG_FIELDS:
        _fail("independent catalog top-level schema drifted")
    if set(value["authority"]) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in value["authority"].values()
    ):
        _fail("independent catalog authority is not exact all-false")
    return value


def _expected_catalog_raw(records):
    raw = _canonical(
        _expected_catalog_value(records),
        label="independent payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )
    _pinned(
        raw,
        expected_bytes=EXPECTED_CATALOG_BYTES,
        expected_sha256=EXPECTED_CATALOG_SHA256,
        label="payload-equivalence rule catalog",
    )
    return raw


def _expected_fragment_raw(catalog_raw):
    catalog = _strict_object(
        catalog_raw,
        label="independent payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )
    raw = _canonical(
        catalog["rule_catalog"],
        label="independent payload-equivalence normative source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    _pinned(
        raw,
        expected_bytes=EXPECTED_FRAGMENT_BYTES,
        expected_sha256=EXPECTED_FRAGMENT_SHA256,
        label="payload-equivalence normative source fragment",
    )
    return raw


def _reject_projection_leakage(value, *, path="$projection"):
    if type(value) is dict:
        for key, item in value.items():
            tokens = set(key.lower().replace("-", "_").split("_"))
            if tokens & FORBIDDEN_PROJECTION_KEY_TOKENS:
                _fail(f"content-only projection leaks forbidden field at {path}.{key}")
            _reject_projection_leakage(item, path=f"{path}.{key}")
    elif type(value) is list:
        for index, item in enumerate(value):
            _reject_projection_leakage(item, path=f"{path}[{index}]")


def _expected_projection_raw(fragment_raw):
    fragment = _strict_object(
        fragment_raw,
        label="independent payload-equivalence normative source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        **fragment,
    }
    if set(value) != PROJECTION_FIELDS:
        _fail("independent payload-equivalence projection schema drifted")
    _reject_projection_leakage(value)
    raw = _canonical(
        value,
        label="independent payload-equivalence rules projection",
        maximum=MAX_PROJECTION_BYTES,
    )
    _pinned(
        raw,
        expected_bytes=EXPECTED_PROJECTION_BYTES,
        expected_sha256=EXPECTED_PROJECTION_SHA256,
        label="payload-equivalence rules projection",
    )
    return raw


def _catalog_input_raw(value):
    return _canonical(
        value,
        label="target payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )


def _projection_input_raw(value):
    return _canonical(
        value,
        label="target payload-equivalence rules projection",
        maximum=MAX_PROJECTION_BYTES,
    )


def _postflight_target(value, opening_raw, *, canonicalizer, label):
    closing = canonicalizer(value)
    if not hmac.compare_digest(opening_raw, closing):
        _fail(f"{label} mutated during validation")


def validate_payload_equivalence_rule_catalog(value):
    if type(value) is not dict:
        _fail("payload-equivalence rule catalog must be an exact object")
    opening_raw = _catalog_input_raw(value)
    snapshot = _strict_object(
        opening_raw,
        label="target payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )
    _pinned(
        opening_raw,
        expected_bytes=EXPECTED_CATALOG_BYTES,
        expected_sha256=EXPECTED_CATALOG_SHA256,
        label="target payload-equivalence rule catalog",
    )
    owners = None
    expected = None
    try:
        owners = _fresh_owner_records()
        expected = _expected_catalog_raw(owners)
        if not hmac.compare_digest(opening_raw, expected):
            _fail("catalog differs from independent owner reconstruction")
        if snapshot.get("g0_contract_frozen") is not False:
            _fail("payload-equivalence catalog must remain non-G0")
    finally:
        postflight_error = None
        if owners is not None:
            try:
                _postflight_derivation(owners, catalog_raw=expected)
            except Exception as error:  # preserve postflight over optimistic success
                postflight_error = error
        try:
            _postflight_target(
                value,
                opening_raw,
                canonicalizer=_catalog_input_raw,
                label="target payload-equivalence rule catalog",
            )
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


def validate_payload_equivalence_rules_projection(value):
    if type(value) is not dict:
        _fail("payload-equivalence rules projection must be an exact object")
    opening_raw = _projection_input_raw(value)
    snapshot = _strict_object(
        opening_raw,
        label="target payload-equivalence rules projection",
        maximum=MAX_PROJECTION_BYTES,
    )
    _reject_projection_leakage(snapshot)
    _pinned(
        opening_raw,
        expected_bytes=EXPECTED_PROJECTION_BYTES,
        expected_sha256=EXPECTED_PROJECTION_SHA256,
        label="target payload-equivalence rules projection",
    )
    owners = None
    catalog_raw = fragment_raw = expected = None
    try:
        owners = _fresh_owner_records()
        catalog_raw = _expected_catalog_raw(owners)
        fragment_raw = _expected_fragment_raw(catalog_raw)
        expected = _expected_projection_raw(fragment_raw)
        if not hmac.compare_digest(opening_raw, expected):
            _fail("projection differs from independent owner reconstruction")
    finally:
        postflight_error = None
        if owners is not None:
            try:
                _postflight_derivation(
                    owners,
                    catalog_raw=catalog_raw,
                    fragment_raw=fragment_raw,
                    projection_raw=expected,
                )
            except Exception as error:
                postflight_error = error
        try:
            _postflight_target(
                value,
                opening_raw,
                canonicalizer=_projection_input_raw,
                label="target payload-equivalence rules projection",
            )
        except Exception as error:
            if postflight_error is None:
                postflight_error = error
        if postflight_error is not None:
            raise postflight_error
    return True


def validate_projection_body(class_id, coordinates, body):
    """Authenticate one body and reauthenticate every full/direct owner.

    Invalid dispatch metadata is rejected before any upstream callback.
    """

    if type(class_id) is not str or class_id != PROJECTION_CLASS_ID:
        _fail(f"unknown payload-equivalence projection class: {class_id!r}")
    if type(coordinates) is not dict or coordinates:
        _fail("payload-equivalence projection coordinates must be the empty object")
    if type(body) is not bytes or not body or len(body) > MAX_PROJECTION_BYTES:
        _fail("payload-equivalence projection body must be bounded exact bytes")
    body_snapshot = _strict_object(
        body,
        label="target payload-equivalence projection body",
        maximum=MAX_PROJECTION_BYTES,
    )
    _reject_projection_leakage(body_snapshot)
    opening_body = bytes(body)
    _pinned(
        opening_body,
        expected_bytes=EXPECTED_PROJECTION_BYTES,
        expected_sha256=EXPECTED_PROJECTION_SHA256,
        label="target payload-equivalence projection body",
    )
    owners = _fresh_owner_records()
    catalog_raw = fragment_raw = expected_body = None
    try:
        catalog_raw = _expected_catalog_raw(owners)
        fragment_raw = _expected_fragment_raw(catalog_raw)
        expected_body = _expected_projection_raw(fragment_raw)
        if not hmac.compare_digest(opening_body, expected_body):
            _fail("projection body differs from independent derivation")
    finally:
        _postflight_derivation(
            owners,
            catalog_raw=catalog_raw,
            fragment_raw=fragment_raw,
            projection_raw=expected_body,
        )
    if not hmac.compare_digest(opening_body, body):
        _fail("projection body mutated during validation")
    return True


def _full_owner_pin(
    *, artifact_kind, artifact_schema, artifact_schema_version, canonical_bytes,
    owner_id, owner_role, sha256
):
    value = {
        "artifact_kind": artifact_kind,
        "artifact_schema": artifact_schema,
        "artifact_schema_version": artifact_schema_version,
        "body_framing": BODY_FRAMING,
        "canonical_bytes": canonical_bytes,
        "coordinates": {},
        "owner_id": owner_id,
        "owner_role": owner_role,
        "sha256": sha256,
    }
    if set(value) != FULL_OWNER_PIN_FIELDS:
        _fail("independent full-owner pin schema drifted")
    return value


def _direct_pin(raw):
    value = {
        "body_framing": BODY_FRAMING,
        "canonical_bytes": len(raw),
        "direct_pin_id": "payload-equivalence-normative-rule-fragment",
        "direct_pin_role": "content-only-normative-rule-source-fragment",
        "sha256": _sha256(raw),
    }
    if set(value) != DIRECT_PIN_FIELDS:
        _fail("independent direct pin schema drifted")
    return value


def _expected_material(owners, catalog_raw, fragment_raw, projection_raw):
    upstream = [
        _full_owner_pin(
            artifact_kind=record["spec"]["artifact_kind"],
            artifact_schema=record["spec"]["artifact_schema"],
            artifact_schema_version=record["spec"]["artifact_schema_version"],
            canonical_bytes=len(record["raw"]),
            owner_id=record["spec"]["name"],
            owner_role=record["spec"]["dependency_role"],
            sha256=_sha256(record["raw"]),
        )
        for record in owners
    ]
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "body": bytes(projection_raw),
        "body_framing": BODY_FRAMING,
        "coordinates": {},
        "direct_body_pins": [_direct_pin(fragment_raw)],
        "full_owner_pins": [
            _full_owner_pin(
                artifact_kind=ARTIFACT_KIND,
                artifact_schema=ARTIFACT_SCHEMA,
                artifact_schema_version=ARTIFACT_SCHEMA_VERSION,
                canonical_bytes=len(catalog_raw),
                owner_id="persona-v2-payload-equivalence-rule-catalog",
                owner_role="principal-payload-equivalence-rule-owner",
                sha256=_sha256(catalog_raw),
            ),
            *upstream,
        ],
        "projection_class_id": PROJECTION_CLASS_ID,
        "projector_id": PROJECTOR_ID,
        "receipt_id": RECEIPT_ID,
    }
    if set(value) != MATERIAL_FIELDS:
        _fail("independent projection material schema drifted")
    return value


def iter_expected_payload_equivalence_projection_materials():
    """Yield the one independently reconstructed, detached material."""

    owners = _fresh_owner_records()
    catalog_raw = fragment_raw = projection_raw = None
    try:
        catalog_raw = _expected_catalog_raw(owners)
        fragment_raw = _expected_fragment_raw(catalog_raw)
        projection_raw = _expected_projection_raw(fragment_raw)
        material = _expected_material(
            owners,
            catalog_raw,
            fragment_raw,
            projection_raw,
        )
    finally:
        _postflight_derivation(
            owners,
            catalog_raw=catalog_raw,
            fragment_raw=fragment_raw,
            projection_raw=projection_raw,
        )
    yield copy.deepcopy(material)


def reauthenticate_all_projection_owners():
    """Rebuild and pin the full owner chain and the direct fragment."""

    owners = _fresh_owner_records()
    catalog_raw = fragment_raw = projection_raw = None
    try:
        catalog_raw = _expected_catalog_raw(owners)
        fragment_raw = _expected_fragment_raw(catalog_raw)
        projection_raw = _expected_projection_raw(fragment_raw)
    finally:
        _postflight_derivation(
            owners,
            catalog_raw=catalog_raw,
            fragment_raw=fragment_raw,
            projection_raw=projection_raw,
        )
    return True


__all__ = [
    "EXPECTED_CATALOG_BYTES",
    "EXPECTED_CATALOG_SHA256",
    "EXPECTED_FRAGMENT_BYTES",
    "EXPECTED_FRAGMENT_SHA256",
    "EXPECTED_PROJECTION_BYTES",
    "EXPECTED_PROJECTION_SHA256",
    "PersonaV2PayloadEquivalenceRuleCatalogValidationError",
    "iter_expected_payload_equivalence_projection_materials",
    "reauthenticate_all_projection_owners",
    "validate_payload_equivalence_rule_catalog",
    "validate_payload_equivalence_rules_projection",
    "validate_projection_body",
]
