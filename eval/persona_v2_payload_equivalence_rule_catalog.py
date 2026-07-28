"""Global payload-equivalence rules for persona-PC fidelity v2.

The catalog is the first owner that closes the payload-key recipe left open by
the overlay contract.  It binds, in one direction only, the frozen overlay,
source-semantic, concrete-overlay, and source-parameter suite owners.  Its
single external projection contains only five normative content rules and
their precedence; it contains no owner pins, authority, completion state,
instance rows, query material, execution state, or observations.

This is still a planning artifact.  It does not attest rendered bytes, issue a
semantic namespace, authorize identifiers, solve placement, write files, run
KIO, compile history, or freeze G0.
"""

from __future__ import annotations

import copy
import functools
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
TARGET_PROJECTION_BYTES = 8 * 2**10
MAX_FRAGMENT_BYTES = 16 * 2**10

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
    "62394dd2a3544f7d6c332652e6799b7a60353e8e3aa6a87f80e0ff21590a2e28"
)
CONCRETE_OWNER_BYTES = 51_133
CONCRETE_OWNER_SHA256 = (
    "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737"
)
PARAMETER_OWNER_BYTES = 72_535
PARAMETER_OWNER_SHA256 = (
    "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a"
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


class PersonaV2PayloadEquivalenceRuleCatalogError(ValueError):
    """Raised when the catalog, projection, or owner chain drifts."""


def _fail(message):
    raise PersonaV2PayloadEquivalenceRuleCatalogError(message)


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


def _strict_object_from_raw(raw, *, label, maximum):
    if type(raw) is not bytes or not raw or len(raw) > maximum:
        _fail(f"{label} must be non-empty bounded exact bytes")
    try:
        text = raw.decode("utf-8", "strict")
        value = json.loads(
            text,
            object_pairs_hook=_unique_object,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict JSON: {error}")
    if type(value) is not dict:
        _fail(f"{label} must decode to an object")
    if not hmac.compare_digest(
        raw,
        _canonical(value, label=label, maximum=maximum),
    ):
        _fail(f"{label} is not exact canonical JSON")
    return value


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


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
        if (
            value.get("artifact_kind") != spec["artifact_kind"]
            or value.get("artifact_schema") != spec["artifact_schema"]
            or value.get("artifact_schema_version")
            != spec["artifact_schema_version"]
        ):
            _fail(f"{spec['name']} artifact identity drifted")
        raw = spec["canonicalizer"](value)
        if type(raw) is not bytes:
            _fail(f"{spec['name']} canonicalizer did not return exact bytes")
        if (
            len(raw) != spec["canonical_bytes"]
            or not hmac.compare_digest(_sha256(raw), spec["sha256"])
        ):
            _fail(f"{spec['name']} differs from its frozen full-owner pin")
        snapshot = _strict_object_from_raw(
            raw,
            label=spec["name"],
            maximum=max(spec["canonical_bytes"], 1),
        )
        records.append({"raw": bytes(raw), "spec": spec, "value": snapshot})
    return tuple(records)


def _require_reauthenticated(opening):
    closing = _fresh_owner_records()
    if len(opening) != len(closing):
        _fail("payload-equivalence owner chain cardinality changed")
    for first, last in zip(opening, closing, strict=True):
        if (
            first["spec"]["name"] != last["spec"]["name"]
            or not hmac.compare_digest(first["raw"], last["raw"])
        ):
            _fail("payload-equivalence owner changed during derivation")


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
        _fail("payload-equivalence input-binding schema drifted")
    return value


def _expected_overlay_semantics():
    return {
        "exact-duplicate": {
            "branch_relation": "same-branch",
            "decoded_payload_relation": "exactly-equal",
            "document_revision_relation": "same-logical-revision",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "same-raw-sha256",
        },
        "near-revision": {
            "branch_relation": "same-linear-branch",
            "decoded_payload_relation": "different-but-semantically-near",
            "document_revision_relation": "distinct-strictly-ordered-revisions",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "different-raw-sha256",
        },
        "conflict-copy": {
            "branch_relation": "distinct-unordered-branches",
            "decoded_payload_relation": (
                "different-with-conflicting-typed-fact-required"
            ),
            "document_revision_relation": "branch-distinct-no-linear-order",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "different-raw-sha256",
        },
    }


def _require_owner_algebra(records):
    by_name = {record["spec"]["name"]: record["value"] for record in records}
    contract = by_name[OWNER_ORDER[0]]
    semantic_suite = by_name[OWNER_ORDER[1]]
    concrete_suite = by_name[OWNER_ORDER[2]]
    parameter_suite = by_name[OWNER_ORDER[3]]

    actual_semantics = {
        row["relation_kind"]: {
            key: row[key]
            for key in (
                "branch_relation",
                "decoded_payload_relation",
                "document_revision_relation",
                "logical_document_relation",
                "raw_identity_relation",
            )
        }
        for row in contract["content_relation_semantics"]
    }
    attachment = contract["attachment_contract"]
    full_targets = contract["suite_target_marginals"]["full"]
    semantic_summary = semantic_suite["summary"]
    concrete_summary = concrete_suite["summary"]
    parameter_coverage = parameter_suite["coverage"]
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
    if actual_semantics != _expected_overlay_semantics():
        _fail("overlay payload relation semantics drifted")
    if any(full_targets.get(key) != value for key, value in expected_targets.items()):
        _fail("overlay full payload target marginals drifted")
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
        _fail("overlay attachment payload contract drifted")
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
        _fail("payload-equivalence cross-owner coverage algebra drifted")
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
        _fail("payload-equivalence derived source algebra drifted")
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


def _rules():
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
            "logical_identity_relation": (
                "same-document-branch-revision-and-section"
            ),
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
        or any(set(row) != RULE_FIELDS for row in rows)
        or [row["precedence_ordinal"] for row in rows] != list(range(1, 6))
    ):
        _fail("payload-equivalence normative rule schema drifted")
    return rows


def _rule_catalog():
    value = {
        "precedence_contract": {
            "attachment_rule_is_orthogonal_postcondition": True,
            "content_relation_rules_are_mutually_exclusive": True,
            "default_rule_requires_no_explicit_overlay_role": True,
            "exact_attachment_overlap_is_transitive_not-a-sixth-rule": True,
            "first_matching_content_rule_precedes_attachment_postcondition": True,
        },
        "rule_order": list(RULE_ORDER),
        "rules": _rules(),
    }
    if set(value) != RULE_CATALOG_FIELDS:
        _fail("payload-equivalence rule-catalog schema drifted")
    return value


def _build_catalog_value(records):
    coverage = _require_owner_algebra(records)
    bindings = [_input_binding(record) for record in records]
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
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
        "rule_catalog": _rule_catalog(),
        "summary": {
            **coverage,
            "input_owner_count": len(bindings),
            "projection_body_count": 1,
            "rule_count": len(RULE_ORDER),
        },
    }
    if set(value) != CATALOG_FIELDS:
        _fail("payload-equivalence catalog top-level schema drifted")
    if set(value["authority"]) != AUTHORITY_FIELDS or any(
        type(flag) is not bool or flag is not False
        for flag in value["authority"].values()
    ):
        _fail("payload-equivalence catalog authority must be exact all-false")
    return value


@functools.lru_cache(maxsize=1)
def _catalog_raw():
    records = _fresh_owner_records()
    try:
        value = _build_catalog_value(records)
        return _canonical(
            value,
            label="persona v2 payload-equivalence rule catalog",
            maximum=MAX_CATALOG_BYTES,
        )
    finally:
        _require_reauthenticated(records)


@functools.lru_cache(maxsize=1)
def _rule_fragment_raw():
    catalog = _strict_object_from_raw(
        _catalog_raw(),
        label="persona v2 payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )
    return _canonical(
        catalog["rule_catalog"],
        label="payload-equivalence normative source fragment",
        maximum=MAX_FRAGMENT_BYTES,
    )


def _projection_value():
    fragment = _strict_object_from_raw(
        _rule_fragment_raw(),
        label="payload-equivalence normative source fragment",
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
        _fail("payload-equivalence projection schema drifted")
    return value


@functools.lru_cache(maxsize=1)
def _projection_raw():
    raw = _canonical(
        _projection_value(),
        label="persona v2 payload-equivalence rules projection",
        maximum=MAX_PROJECTION_BYTES,
    )
    if len(raw) > TARGET_PROJECTION_BYTES:
        _fail("payload-equivalence rules projection exceeds its 8-KiB target")
    return raw


def canonical_json_bytes(value):
    if type(value) is not dict:
        _fail("payload-equivalence artifact must be an exact object")
    schema = value.get("artifact_schema")
    if schema == ARTIFACT_SCHEMA:
        return _canonical(
            value,
            label="persona v2 payload-equivalence rule catalog",
            maximum=MAX_CATALOG_BYTES,
        )
    if schema == PROJECTION_SCHEMA:
        return _canonical(
            value,
            label="persona v2 payload-equivalence rules projection",
            maximum=MAX_PROJECTION_BYTES,
        )
    _fail(f"unknown payload-equivalence artifact schema: {schema!r}")


def build_payload_equivalence_rule_catalog():
    """Return a detached catalog; the cache stores only immutable raw bytes."""

    return _strict_object_from_raw(
        _catalog_raw(),
        label="persona v2 payload-equivalence rule catalog",
        maximum=MAX_CATALOG_BYTES,
    )


def build_payload_equivalence_rules_projection():
    """Return the detached global content-only projection."""

    return _strict_object_from_raw(
        _projection_raw(),
        label="persona v2 payload-equivalence rules projection",
        maximum=MAX_PROJECTION_BYTES,
    )


def _independent_validator():
    try:
        from . import persona_v2_payload_equivalence_rule_catalog_validator as independent
    except ImportError:  # pragma: no cover - direct-script compatibility
        import persona_v2_payload_equivalence_rule_catalog_validator as independent
    return independent


def validate_payload_equivalence_rule_catalog(value):
    try:
        result = _independent_validator().validate_payload_equivalence_rule_catalog(value)
    except Exception as error:
        if type(error) is PersonaV2PayloadEquivalenceRuleCatalogError:
            raise
        _fail(str(error))
    if result is not True:
        _fail("independent catalog validator did not return exact True")
    return True


def validate_payload_equivalence_rules_projection(value):
    try:
        result = _independent_validator().validate_payload_equivalence_rules_projection(value)
    except Exception as error:
        if type(error) is PersonaV2PayloadEquivalenceRuleCatalogError:
            raise
        _fail(str(error))
    if result is not True:
        _fail("independent projection validator did not return exact True")
    return True


def payload_equivalence_rule_catalog_sha256(value=None):
    if value is None:
        value = build_payload_equivalence_rule_catalog()
    opening_raw = canonical_json_bytes(value)
    snapshot = _strict_object_from_raw(
        opening_raw,
        label="payload-equivalence rule catalog SHA opening image",
        maximum=MAX_CATALOG_BYTES,
    )
    try:
        validate_payload_equivalence_rule_catalog(snapshot)
    finally:
        closing_raw = canonical_json_bytes(value)
        if not hmac.compare_digest(opening_raw, closing_raw):
            _fail("payload-equivalence rule catalog mutated during SHA validation")
    return _sha256(opening_raw)


def payload_equivalence_rules_projection_sha256(value=None):
    if value is None:
        value = build_payload_equivalence_rules_projection()
    opening_raw = canonical_json_bytes(value)
    snapshot = _strict_object_from_raw(
        opening_raw,
        label="payload-equivalence rules projection SHA opening image",
        maximum=MAX_PROJECTION_BYTES,
    )
    try:
        validate_payload_equivalence_rules_projection(snapshot)
    finally:
        closing_raw = canonical_json_bytes(value)
        if not hmac.compare_digest(opening_raw, closing_raw):
            _fail("payload-equivalence rules projection mutated during SHA validation")
    return _sha256(opening_raw)


def projection_body_bytes(class_id, coordinates):
    if type(class_id) is not str or class_id != PROJECTION_CLASS_ID:
        _fail(f"unknown payload-equivalence projection class: {class_id!r}")
    if type(coordinates) is not dict or coordinates:
        _fail("payload-equivalence projection coordinates must be the empty object")
    return bytes(_projection_raw())


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
        _fail("payload-equivalence full-owner pin schema drifted")
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
        _fail("payload-equivalence direct pin schema drifted")
    return value


def _material():
    catalog_raw = bytes(_catalog_raw())
    fragment_raw = bytes(_rule_fragment_raw())
    upstream_pins = [
        _full_owner_pin(
            artifact_kind=spec["artifact_kind"],
            artifact_schema=spec["artifact_schema"],
            artifact_schema_version=spec["artifact_schema_version"],
            canonical_bytes=spec["canonical_bytes"],
            owner_id=spec["name"],
            owner_role=spec["dependency_role"],
            sha256=spec["sha256"],
        )
        for spec in _owner_specs()
    ]
    value = {
        "artifact_kind": PROJECTION_KIND,
        "artifact_schema": PROJECTION_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "body": bytes(_projection_raw()),
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
            *upstream_pins,
        ],
        "projection_class_id": PROJECTION_CLASS_ID,
        "projector_id": PROJECTOR_ID,
        "receipt_id": RECEIPT_ID,
    }
    if set(value) != MATERIAL_FIELDS:
        _fail("payload-equivalence projection material schema drifted")
    return value


def iter_payload_equivalence_projection_materials():
    """Yield the sole detached global normative-rules material."""

    yield copy.deepcopy(_material())


def build_payload_equivalence_projection_materials():
    """Compatibility list form consumed by the complete inventory."""

    return list(iter_payload_equivalence_projection_materials())


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "BODY_FRAMING",
    "CATALOG_FIELDS",
    "DIRECT_PIN_FIELDS",
    "FULL_OWNER_PIN_FIELDS",
    "MATERIAL_FIELDS",
    "MAX_CATALOG_BYTES",
    "MAX_FRAGMENT_BYTES",
    "MAX_PROJECTION_BYTES",
    "OWNER_ORDER",
    "PROJECTION_CLASS_ID",
    "PROJECTION_FIELDS",
    "PROJECTION_KIND",
    "PROJECTION_SCHEMA",
    "RULE_FIELDS",
    "RULE_ORDER",
    "TARGET_PROJECTION_BYTES",
    "PersonaV2PayloadEquivalenceRuleCatalogError",
    "build_payload_equivalence_projection_materials",
    "build_payload_equivalence_rule_catalog",
    "build_payload_equivalence_rules_projection",
    "canonical_json_bytes",
    "iter_payload_equivalence_projection_materials",
    "payload_equivalence_rule_catalog_sha256",
    "payload_equivalence_rules_projection_sha256",
    "projection_body_bytes",
    "validate_payload_equivalence_rule_catalog",
    "validate_payload_equivalence_rules_projection",
]
