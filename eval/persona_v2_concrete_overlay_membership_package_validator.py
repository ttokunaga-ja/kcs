"""Builder-independent validation for persona-PC v2 concrete overlays.

This validator deliberately does not import the target concrete-overlay
producer.  It validates the target metadata graph before calling any body
provider, delegates the complete structural/semantic package validation to the
existing independent validator exactly once, and then replays authenticated
upstream bodies one origin at a time to verify every concrete join.

Success proves only the pre-solve overlay membership package.  Scope
placement, rendered bytes, observed raw/chunk identities, query relevance,
history execution, KIO execution, G0 freeze, and write authority remain absent.
"""

from __future__ import annotations

import copy
import hashlib
import json
import gc

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_overlay_contract as overlay_contract
    from . import persona_v2_overlay_reservation_validator as reservation_validator
    from . import persona_v2_source_inventory_package_validator as source_validator
    from . import persona_v2_source_semantic_membership_package_validator as semantic_validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_overlay_contract as overlay_contract
    import persona_v2_overlay_reservation_validator as reservation_validator
    import persona_v2_source_inventory_package_validator as source_validator
    import persona_v2_source_semantic_membership_package_validator as semantic_validator


ORIGIN_ORDER = ("pilot", "full-residual")
PROFILE_ORDER = ("pilot", "full")
RELATION_ORDER = ("exact-duplicate", "near-revision", "conflict-copy")
PLACEMENT_ORDER = (
    "primary-to-primary",
    "primary-to-secondary",
    "secondary-to-primary",
    "secondary-to-secondary",
)

ORIGIN_ARTIFACT_SCHEMA = (
    "kio.persona.pc-concrete-overlay-membership-origin-manifest/v2"
)
ORIGIN_ARTIFACT_KIND = (
    "persona-pc-v2-concrete-overlay-membership-origin-manifest"
)
PROFILE_ARTIFACT_SCHEMA = (
    "kio.persona.pc-concrete-overlay-membership-profile-manifest/v2"
)
PROFILE_ARTIFACT_KIND = (
    "persona-pc-v2-concrete-overlay-membership-profile-manifest"
)
SUITE_ARTIFACT_SCHEMA = "kio.persona.pc-concrete-overlay-membership-suite/v2"
SUITE_ARTIFACT_KIND = "persona-pc-v2-concrete-overlay-membership-suite"
ARTIFACT_SCHEMA_VERSION = 2

EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_CONTENT_RELATION_ROW_COUNT = 19_870
EXPECTED_ATTACHMENT_ROW_COUNT = 5_690
EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT = 25_560
EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT = 2_100
EXPECTED_RICH_ROW_COUNT = 27_660
EXPECTED_UNIQUE_OVERLAY_REFERENCE_COUNT = 46_840
EXPECTED_UNIQUE_JOINED_SOURCE_COUNT = 48_940
EXPECTED_CONFLICT_ROW_COUNT = 1_560

MAX_ROW_BYTES_INCLUDING_LF = 768
MAX_ROWS_PER_SHARD = 4_096
MAX_SHARD_BODY_BYTES = 4 * 2**20
MAX_ORIGIN_MANIFEST_BYTES = 128 * 1024
MAX_PROFILE_MANIFEST_BYTES = 128 * 1024
MAX_SUITE_DESCRIPTOR_BYTES = 512 * 1024
MAX_PERSONA_PACKAGE_BYTES = 16 * 2**20

# Frozen only as an independent-validator release gate.  The validator never
# imports the producer that emits this descriptor.
EXPECTED_SUITE_DESCRIPTOR_BYTES = 51_133
EXPECTED_SUITE_SHA256 = (
    "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737"
)

AUTHORITY_FIELDS = frozenset(
    {
        "actual_chunks_attested",
        "authorizes_final_source_identifiers",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_physical_write",
        "authorizes_renderer_execution",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "filesystem_writer_available",
        "formal_capacity_gate_satisfied",
        "formal_complete_persona_package_cap_proved",
        "history_executor_available",
        "kio_execution_available",
        "query_instances_rendered",
        "query_spec_hashed",
        "renderer_available",
    }
)

CONTENT_RELATION_ROW_FIELDS = frozenset(
    {
        "anchor_fact_profile_id",
        "anchor_intent_key",
        "cluster_key",
        "derivative_fact_profile_id",
        "derivative_intent_key",
        "placement_class_requirement",
        "relation_kind",
        "row_kind",
        "search_participation_requirement_id",
    }
)
ATTACHMENT_ROW_FIELDS = frozenset(
    {
        "attachment_key",
        "content_relation_membership",
        "decoded_payload_equivalence_key",
        "host_fact_profile_id",
        "host_intent_key",
        "host_member_count",
        "member_ordinal",
        "row_kind",
        "search_participation_requirement_id",
        "standalone_member_fact_profile_id",
        "standalone_member_intent_key",
    }
)
SEMANTIC_ANCHOR_ROW_FIELDS = frozenset(
    {
        "fact_profile_id",
        "intent_key",
        "row_kind",
        "semantic_anchor_slot_ordinal",
    }
)

SHARD_DESCRIPTOR_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "file_name",
        "first_row_sort_key",
        "last_row_sort_key",
        "maximum_row_bytes_including_lf",
        "origin",
        "persona_id",
        "row_count",
        "shard_index",
    }
)
DRAFT_PROJECTION_RECEIPT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_sha256",
        "first_row_sort_key",
        "last_row_sort_key",
        "maximum_row_bytes_including_lf",
        "row_count",
    }
)
ORIGIN_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "draft_membership_projection_receipt",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "hypothesis_status",
        "input_binding_order",
        "input_bindings",
        "origin",
        "persona_id",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "target_marginals",
        "target_profile",
    }
)
PROFILE_TOP_LEVEL_FIELDS = frozenset(
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
        "origin_manifest_bindings",
        "origin_order",
        "persona_id",
        "profile",
        "remaining_blockers",
        "shard_descriptors",
        "summary",
        "target_marginals",
    }
)
SUITE_TOP_LEVEL_FIELDS = frozenset(
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
        "origin_manifest_bindings",
        "persona_current_component_byte_ledger_contract",
        "persona_current_component_byte_ledgers",
        "profile_manifest_bindings",
        "remaining_blockers",
        "summary",
    }
)

PUBLIC_INPUT_BINDING_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "canonical_bytes",
        "dependency_role",
        "name",
        "sha256",
    }
)
ORIGIN_COORDINATE_BINDING_FIELDS = frozenset(
    set(PUBLIC_INPUT_BINDING_FIELDS) | {"origin", "persona_id"}
)
PROFILE_COORDINATE_BINDING_FIELDS = frozenset(
    set(PUBLIC_INPUT_BINDING_FIELDS) | {"persona_id", "profile"}
)
ORIGIN_SUMMARY_FIELDS = frozenset(
    {
        "attachment_exact_overlap_row_count",
        "attachment_host_count",
        "attachment_membership_row_count",
        "conflict_copy_row_count",
        "content_relation_row_count",
        "exact_duplicate_row_count",
        "joined_source_reference_occurrence_count",
        "maximum_row_bytes_including_lf",
        "near_revision_row_count",
        "overlay_membership_row_count",
        "overlay_source_reference_occurrence_count",
        "rich_row_count",
        "semantic_anchor_membership_row_count",
        "shard_body_bytes",
        "shard_count",
        "unique_joined_source_count",
        "unique_overlay_source_count",
    }
)
PROFILE_SUMMARY_FIELDS = frozenset(
    set(ORIGIN_SUMMARY_FIELDS)
    | {
        "origin_manifest_count",
        "reused_pilot_rich_row_count",
        "reused_pilot_shard_body_bytes",
        "reused_pilot_shard_count",
    }
)
SUITE_SUMMARY_FIELDS = frozenset(
    set(ORIGIN_SUMMARY_FIELDS)
    | {
        "draft_projection_body_bytes",
        "draft_projection_row_count",
        "maximum_origin_manifest_bytes",
        "maximum_persona_current_component_bytes",
        "maximum_profile_manifest_bytes",
        "maximum_shard_body_bytes",
        "minimum_persona_headroom_bytes",
        "origin_manifest_count",
        "persona_count",
        "profile_manifest_count",
    }
)
PERSONA_COMPONENT_LEDGER_FIELDS = frozenset(
    {
        "concrete_origin_body_bytes",
        "concrete_origin_manifest_bytes",
        "concrete_profile_manifest_bytes",
        "current_component_bytes",
        "current_component_cap_satisfied",
        "formal_complete_persona_package_cap_proved",
        "headroom_bytes",
        "max_current_component_bytes",
        "overlay_contract_bytes_conservatively_charged_in_full",
        "persona_id",
        "semantic_current_component_bytes",
    }
)

REMAINING_BLOCKERS = [
    "formal-source-recipes-and-renderer-validator-implementations",
    "corpus-semantic-namespace-and-query-history-target-mapping",
    "scope-placement-joint-allocation-and-proof",
    "actual-payload-search-and-raw-identity-attestation",
    "render-write-chunk-observation-history-and-kio-execution",
    "future-complete-persona-package-cap-proof",
]
HYPOTHESIS_STATUS = "authored-benchmark-stress-join-not-observed-user-statistics"

ORIGIN_CANONICAL_LIMITS = {
    "max_manifest_bytes": MAX_ORIGIN_MANIFEST_BYTES,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_row_bytes_including_lf": MAX_ROW_BYTES_INCLUDING_LF,
    "max_rows_per_shard": MAX_ROWS_PER_SHARD,
    "max_shard_body_bytes": MAX_SHARD_BODY_BYTES,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "shard_index_base": 0,
    "unicode_normalization": "NFC",
}
PROFILE_CANONICAL_LIMITS = {
    "max_manifest_bytes": MAX_PROFILE_MANIFEST_BYTES,
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "shard_index_base": 0,
    "unicode_normalization": "NFC",
}
SUITE_CANONICAL_LIMITS = {
    "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
    "max_persona_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
    "max_suite_descriptor_bytes": MAX_SUITE_DESCRIPTOR_BYTES,
    "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
    "self_hash_embedded": False,
    "shard_index_base": 0,
    "unicode_normalization": "NFC",
}

ORIGIN_COMPLETION_CLAIMS = {
    "all_origin_reservation_membership_rows_joined": True,
    "all_origin_semantic_anchor_slots_joined": True,
    "all_referenced_source_fact_profiles_bound": True,
    "concrete_overlay_membership_bound": True,
    "draft_membership_projection_receipt_bound": True,
    "formal_complete_persona_package_cap_proved": False,
    "placement_integer_allocation_bound": False,
    "raw_or_rendered_identity_attested": False,
    "scope_assignment_present": False,
    "search_history_or_query_observation_bound": False,
}
ORIGIN_COMPLETION_SCOPE = (
    "one-origin-rich-pre-solve-overlay-membership-and-semantic-anchor-join-no-"
    "scope-solution-no-render-no-history-no-search-observation-no-g0"
)
ORIGIN_DEPENDENCY_CONTRACT = {
    "logical_identity_and_fact_arrays_remain_owned_by_semantic_package": True,
    "matching_reservation_source_and_semantic_origins_are_strictly_upstream": True,
    "placement_requirement_is_not_scope_assignment": True,
    "semantic_catalog_is_strictly_upstream": True,
    "upstream_back_reference_allowed": False,
}

PROFILE_COMPLETION_SCOPE = (
    "one-persona-pilot-or-full-rich-pre-solve-overlay-composition-with-exact-"
    "pilot-origin-reuse-no-scope-render-history-observation-or-g0"
)
PROFILE_DEPENDENCY_CONTRACT = {
    "full_profile_origin_order_is_pilot_then_full_residual": True,
    "full_profile_must_reuse_exact_pilot_origin_manifest_and_shards": True,
    "matching_source_and_semantic_profiles_are_strictly_upstream": True,
    "origin_manifests_are_strictly_upstream": True,
    "reservation_suite_and_semantic_catalog_are_directly_bound": True,
    "shard_indices_are_origin_local_and_restart_at_zero": True,
    "upstream_back_reference_allowed": False,
}

SUITE_COMPLETION_CLAIMS = {
    "all_1560_conflict_pairs_bound_to_distinct_branch_profiles": True,
    "all_25560_reservation_membership_rows_joined": True,
    "all_27660_rich_rows_bound": True,
    "all_46840_unique_overlay_source_references_resolved": True,
    "all_2100_semantic_anchor_slots_joined": True,
    "all_48940_reserved_or_anchor_unique_sources_resolved": True,
    "all_40_origin_manifests_bound": True,
    "all_40_profile_manifests_bound": True,
    "concrete_overlay_membership_bound": True,
    "current_concrete_overlay_component_cap_satisfied": True,
    "formal_complete_persona_package_cap_proved": False,
    "full_profiles_exactly_reuse_pilot_origins": True,
    "placement_integer_allocation_bound": False,
    "raw_or_rendered_identity_attested": False,
    "scope_assignment_present": False,
    "search_history_or_query_observation_bound": False,
}
SUITE_COMPLETION_SCOPE = (
    "all-persona-rich-pre-solve-overlay-and-semantic-anchor-memberships-with-"
    "exact-pilot-reuse-and-current-component-cap-no-scope-solution-no-render-"
    "history-search-observation-or-g0"
)
SUITE_DEPENDENCY_CONTRACT = {
    "catalog_and_all_three_upstream_suites_are_directly_bound": True,
    "concrete_origins_and_profiles_are_strictly_upstream_of_suite": True,
    "full_profiles_compose_origins_without_regeneration": True,
    "overlay_contract_is_directly_bound_without_repinning_upstream": True,
    "suite_may_bind_future_allocation_or_execution_artifact": False,
    "upstream_back_reference_allowed": False,
}
SUITE_ORDERS = {
    "origin": list(ORIGIN_ORDER),
    "origin_manifests": "persona-then-origin",
    "persona": list(envelope.PERSONA_IDS),
    "profile": list(PROFILE_ORDER),
    "profile_manifests": "persona-then-profile",
    "rich_rows": (
        "content-relation-order-then-cluster-then-attachment-key-then-"
        "semantic-anchor-slot-and-intent"
    ),
    "shard_index_base": 0,
    "shard_indices": "origin-local-zero-based-restart-per-origin",
}
PERSONA_COMPONENT_LEDGER_CONTRACT = {
    "draft_projection_body_is_receipt_only_and_not_persisted_or_charged": True,
    "global_suite_descriptor_is_not_charged_to_each_persona": True,
    "overlay_contract_is_conservatively_charged_in_full_to_each_persona": True,
    "reservation_and_catalog_components_are_already_in_semantic_base": True,
    "reservation_component_is_not_double_charged": True,
    "semantic_suite_current_component_bytes_is_the_exact_base": True,
    "unique_concrete_origin_bodies_and_both_profile_manifests_are_charged": True,
}


class PersonaV2ConcreteOverlayMembershipPackageValidationError(ValueError):
    """Raised for every public concrete-overlay validation failure."""


def _fail(message):
    raise PersonaV2ConcreteOverlayMembershipPackageValidationError(message)


def _sha256(value):
    return hashlib.sha256(value).hexdigest()


def _ascii_key(value):
    if type(value) is not str:
        _fail("canonical ordering keys must be exact strings")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError:
        _fail("canonical ordering keys must be lowercase ASCII")


def _require_persona_scoped_key(value, persona_id, *, label):
    _ascii_key(value)
    if not value.startswith(f"{persona_id}-"):
        _fail(f"{label} is not scoped by its owning persona")
    return value


def _canonical_bytes(value, *, label, max_bytes=None):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label=label,
            max_bytes=max_bytes,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_exact_fields(value, fields, *, label):
    if type(value) is not dict or set(value) != set(fields):
        _fail(f"{label} fields differ from the exact schema")


def _exact_value_equal(left, right):
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(
            _exact_value_equal(left[key], right[key]) for key in left
        )
    if type(left) is list:
        return len(left) == len(right) and all(
            _exact_value_equal(a, b) for a, b in zip(left, right, strict=True)
        )
    return left == right


def _require_exact_value(value, expected, *, label):
    if not _exact_value_equal(value, expected):
        _fail(f"{label} differs from its exact contract")


def _require_sha256(value, *, label):
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        _fail(f"{label} must be exact lowercase SHA-256")


def _require_exact_int(value, *, label, minimum=0, maximum=None):
    if type(value) is not int or value < minimum:
        _fail(f"{label} must be an exact integer >= {minimum}")
    if maximum is not None and value > maximum:
        _fail(f"{label} exceeds its exact maximum")
    return value


def _require_all_false_authority(value, *, label):
    if type(value) is not dict or set(value) != AUTHORITY_FIELDS:
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in value.values()):
        _fail(f"{label} authority must contain exact all-false booleans")


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"canonical JSONL contains duplicate key {key!r}")
        result[key] = value
    return result


def _reject_float(token):
    _fail(f"canonical JSONL contains floating-point token {token!r}")


def _reject_constant(token):
    _fail(f"canonical JSONL contains non-JSON constant {token!r}")


class _DigestRecordingProvider:
    """Record first validated bytes and reject nondeterministic provider replay."""

    def __init__(self, provider, label):
        if not callable(provider):
            _fail(f"{label} provider must be callable")
        self._provider = provider
        self._label = label
        self._digests = {}

    def __call__(self, *coordinate):
        try:
            body = self._provider(*coordinate)
        except Exception as error:
            raise PersonaV2ConcreteOverlayMembershipPackageValidationError(
                f"{self._label} provider failed for "
                + "/".join(map(str, coordinate))
            ) from error
        if type(body) is not bytes:
            _fail(f"{self._label} provider must return exact bytes")
        receipt = (len(body), _sha256(body))
        previous = self._digests.setdefault(tuple(coordinate), receipt)
        if previous != receipt:
            _fail(f"{self._label} provider is nondeterministic")
        return body

    def replay(self, *coordinate):
        key = tuple(coordinate)
        if key not in self._digests:
            _fail(f"{self._label} coordinate was not independently validated")
        return self(*coordinate)

    def clear(self):
        self._digests.clear()


def _parse_canonical_jsonl(
    body,
    *,
    label,
    row_cap,
    body_cap,
    max_rows,
    expected_fields=None,
):
    if type(body) is not bytes or not body or len(body) > body_cap:
        _fail(f"{label} body is empty, non-bytes, or exceeds its cap")
    if b"\r" in body or not body.endswith(b"\n") or body.startswith(b"\xef\xbb\xbf"):
        _fail(f"{label} must be LF-only canonical JSONL without BOM")
    # Count framing before splitting.  A body can fit inside four MiB while
    # still containing millions of tiny lines, so the row bound must be
    # enforced before allocating the split list.
    line_count = body.count(b"\n")
    if type(max_rows) is not int or max_rows < 1 or not 1 <= line_count <= max_rows:
        _fail(f"{label} exceeds its exact row-count cap")
    raw_rows = body[:-1].split(b"\n")
    if not raw_rows or any(not row for row in raw_rows):
        _fail(f"{label} contains an empty canonical JSONL row")
    rows = []
    maximum = 0
    for index, raw in enumerate(raw_rows, start=1):
        if len(raw) + 1 > row_cap:
            _fail(f"{label} row {index} exceeds its LF-inclusive cap")
        try:
            value = json.loads(
                raw.decode("utf-8", "strict"),
                object_pairs_hook=_reject_duplicate_keys,
                parse_float=_reject_float,
                parse_constant=_reject_constant,
            )
        except PersonaV2ConcreteOverlayMembershipPackageValidationError:
            raise
        except Exception as error:
            raise PersonaV2ConcreteOverlayMembershipPackageValidationError(
                f"{label} row {index} is not strict UTF-8 JSON"
            ) from error
        if type(value) is not dict:
            _fail(f"{label} row {index} must be an object")
        if expected_fields is not None:
            _require_exact_fields(value, expected_fields, label=f"{label} row {index}")
        canonical = _canonical_bytes(
            value,
            label=f"{label} row {index}",
            max_bytes=row_cap - 1,
        )
        if canonical != raw:
            _fail(f"{label} row {index} is not exact canonical JSON")
        rows.append(value)
        maximum = max(maximum, len(raw) + 1)
    return rows, maximum


def _row_sort_key(row):
    kind = row.get("row_kind") if type(row) is dict else None
    if kind == "content-relation-membership":
        relation = row.get("relation_kind")
        if relation not in RELATION_ORDER:
            _fail("content relation row has an unknown relation kind")
        cluster_key = row.get("cluster_key")
        _ascii_key(cluster_key)
        return [0, RELATION_ORDER.index(relation), cluster_key]
    if kind == "attachment-membership":
        attachment_key = row.get("attachment_key")
        _ascii_key(attachment_key)
        return [1, 0, attachment_key]
    if kind == "semantic-anchor-membership":
        ordinal = _require_exact_int(
            row.get("semantic_anchor_slot_ordinal"),
            label="semantic anchor slot ordinal",
            minimum=1,
        )
        intent_key = row.get("intent_key")
        _ascii_key(intent_key)
        return [2, ordinal, intent_key]
    _fail("concrete overlay row has an unknown row kind")


def _sort_tuple(row):
    key = _row_sort_key(row)
    return (key[0], key[1], _ascii_key(key[2]))


def _validate_rich_row_fields(row):
    kind = row.get("row_kind") if type(row) is dict else None
    fields = {
        "content-relation-membership": CONTENT_RELATION_ROW_FIELDS,
        "attachment-membership": ATTACHMENT_ROW_FIELDS,
        "semantic-anchor-membership": SEMANTIC_ANCHOR_ROW_FIELDS,
    }.get(kind)
    if fields is None:
        _fail("concrete overlay row has an unknown row kind")
    _require_exact_fields(row, fields, label=f"{kind} row")


def _profile_rows_by_id(semantic_catalog):
    fact_rows = semantic_catalog.get("fact_profiles")
    semantic_rows = semantic_catalog.get("semantic_profiles")
    if type(fact_rows) is not list or type(semantic_rows) is not list:
        _fail("semantic catalog profile rows are absent")
    fact_by_id = {}
    for row in fact_rows:
        profile_id = row.get("fact_profile_id") if type(row) is dict else None
        persona_id = row.get("persona_id") if type(row) is dict else None
        if (
            type(profile_id) is not str
            or persona_id not in envelope.PERSONA_IDS
            or not profile_id.startswith(f"{persona_id}-")
            or (persona_id, profile_id) in fact_by_id
        ):
            _fail("semantic catalog fact-profile identity is not persona-local unique")
        fact_by_id[(persona_id, profile_id)] = row
    semantic_by_source = {}
    for row in semantic_rows:
        source_profile_id = row.get("source_profile_id") if type(row) is dict else None
        if type(source_profile_id) is not str or source_profile_id in semantic_by_source:
            _fail("semantic profile source-profile mapping is not one-to-one")
        semantic_by_source[source_profile_id] = row
    return fact_by_id, semantic_by_source


def _reservation_reference_keys(reservation):
    rows = reservation.get("reservation_rows")
    anchors = reservation.get("semantic_anchor_slots")
    if type(rows) is not list or type(anchors) is not list:
        _fail("validated reservation origin is missing rows or anchor slots")
    result = set()
    for row in rows:
        kind = row.get("row_kind") if type(row) is dict else None
        if kind == "content-relation-reservation":
            keys = (row.get("anchor_intent_key"), row.get("derivative_intent_key"))
        elif kind == "attachment-membership-reservation":
            keys = (row.get("host_intent_key"), row.get("standalone_member_intent_key"))
        else:
            _fail("validated reservation contains an unknown row kind")
        for key in keys:
            _ascii_key(key)
            result.add(key)
    for row in anchors:
        if type(row) is not dict:
            _fail("validated semantic anchor slot must be an object")
        key = row.get("intent_key")
        _ascii_key(key)
        result.add(key)
    return result


def _reservation_reference_sets(reservation):
    overlay = set()
    relation_endpoints = set()
    relation_anchors = set()
    relation_derivatives = set()
    attachment_hosts = set()
    attachment_members = set()
    overlap_members = set()
    overlap_clusters = set()
    occurrence_count = 0
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            anchor = row["anchor_intent_key"]
            derivative = row["derivative_intent_key"]
            relation_anchors.add(anchor)
            relation_derivatives.add(derivative)
            relation_endpoints.update((anchor, derivative))
            overlay.update((anchor, derivative))
            occurrence_count += 2
        elif row["row_kind"] == "attachment-membership-reservation":
            host = row["host_intent_key"]
            member = row["standalone_member_intent_key"]
            attachment_hosts.add(host)
            attachment_members.add(member)
            overlay.update((host, member))
            occurrence_count += 2
            if row["content_relation_membership"] != "none":
                overlap_members.add(member)
                overlap_clusters.add(row["content_relation_membership"])
        else:
            _fail("validated reservation contains an unknown row kind")
    anchors = {row["intent_key"] for row in reservation["semantic_anchor_slots"]}
    if anchors & overlay:
        _fail("semantic anchors overlap concrete overlay references")
    if attachment_hosts & (relation_endpoints | attachment_members):
        _fail("attachment hosts overlap relation endpoints or standalone members")
    if overlap_members != relation_endpoints & attachment_members:
        _fail("attachment/member relation overlap differs from its declarations")
    if overlap_members & relation_anchors or not overlap_members <= relation_derivatives:
        _fail("attachment overlap must be one-sided on relation derivatives")
    return {
        "anchors": anchors,
        "attachment_hosts": attachment_hosts,
        "attachment_members": attachment_members,
        "occurrence_count": occurrence_count,
        "overlay": overlay,
        "overlap_clusters": overlap_clusters,
        "overlap_members": overlap_members,
        "relation_anchors": relation_anchors,
        "relation_derivatives": relation_derivatives,
        "relation_endpoints": relation_endpoints,
    }


def _verify_source_semantic_triplet(
    source_row,
    context_row,
    membership_row,
    *,
    persona_id,
    origin,
    fact_by_id,
    semantic_by_source,
):
    intent_key = source_row.get("intent_key")
    _require_persona_scoped_key(intent_key, persona_id, label="source intent key")
    if (
        context_row.get("intent_key") != intent_key
        or membership_row.get("intent_key") != intent_key
        or any(
            row.get("persona_id") != persona_id or row.get("origin") != origin
            for row in (source_row, context_row, membership_row)
        )
    ):
        _fail("source/context/fact rows do not share exact persona/origin/intent")
    if (
        context_row.get("content_context_id") != source_row.get("content_context_id")
        or context_row.get("deterministic_payload_seed")
        != source_row.get("deterministic_payload_seed")
        or membership_row.get("present_fact_set_key")
        != source_row.get("present_fact_set_key")
    ):
        _fail("source-owned semantic foreign keys differ from the structural source row")
    semantic_profile = semantic_by_source.get(source_row.get("source_profile_id"))
    if (
        semantic_profile is None
        or context_row.get("semantic_profile_id")
        != semantic_profile.get("semantic_profile_id")
    ):
        _fail("structural source profile does not resolve to its exact semantic profile")
    fact_profile_id = membership_row.get("fact_profile_id")
    _require_persona_scoped_key(
        fact_profile_id, persona_id, label="source fact-profile ID"
    )
    fact_profile = fact_by_id.get((persona_id, fact_profile_id))
    if (
        fact_profile is None
        or membership_row.get("present_fact_ids") != fact_profile.get("present_fact_ids")
    ):
        _fail("source fact membership does not resolve to a persona-owned fact profile")
    return semantic_profile, fact_profile


def _identity_matches(identity, context_row, membership_row):
    return (
        context_row.get("payload_equivalence_key")
        == identity.get("payload_equivalence_key")
        and membership_row.get("logical_document_key")
        == identity.get("logical_document_key")
        and membership_row.get("logical_branch_key")
        == identity.get("logical_branch_key")
        and membership_row.get("logical_revision_key")
        == identity.get("logical_revision_key")
        and membership_row.get("semantic_section_key")
        == identity.get("semantic_section_key")
    )


def _parse_replayed_upstream_rows(
    persona_id,
    origin,
    source_manifest,
    referenced_keys,
    *,
    source_provider,
    context_provider,
    membership_provider,
    fact_by_id,
    semantic_by_source,
):
    selected = {}
    descriptors = source_manifest.get("shard_descriptors")
    if type(descriptors) is not list or not descriptors:
        _fail("source origin manifest has no shard descriptors")
    for descriptor in descriptors:
        shard_ordinal = descriptor.get("shard_ordinal")
        _require_exact_int(shard_ordinal, label="source shard ordinal", minimum=1)
        coordinate = (persona_id, origin, shard_ordinal)
        source_body = source_provider.replay(*coordinate)
        context_body = context_provider.replay(*coordinate)
        membership_body = membership_provider.replay(*coordinate)
        source_rows, _ = _parse_canonical_jsonl(
            source_body,
            label="replayed structural source shard",
            row_cap=source_validator.MAX_ROW_BYTES_INCLUDING_LF,
            body_cap=source_validator.MAX_SHARD_BODY_BYTES,
            max_rows=source_validator.MAX_ROWS_PER_SHARD,
            expected_fields=source_validator.ROW_FIELDS,
        )
        context_rows, _ = _parse_canonical_jsonl(
            context_body,
            label="replayed expanded content-context shard",
            row_cap=semantic_validator.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            body_cap=semantic_validator.MAX_EXPANDED_SHARD_BODY_BYTES,
            max_rows=semantic_validator.MAX_EXPANDED_ROWS_PER_SHARD,
            expected_fields=semantic_validator.EXPANDED_CONTEXT_ROW_FIELDS,
        )
        membership_rows, _ = _parse_canonical_jsonl(
            membership_body,
            label="replayed expanded fact-membership shard",
            row_cap=semantic_validator.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            body_cap=semantic_validator.MAX_EXPANDED_SHARD_BODY_BYTES,
            max_rows=semantic_validator.MAX_EXPANDED_ROWS_PER_SHARD,
            expected_fields=semantic_validator.EXPANDED_MEMBERSHIP_ROW_FIELDS,
        )
        if not (len(source_rows) == len(context_rows) == len(membership_rows)):
            _fail("replayed source/context/fact shard cardinalities differ")
        for source_row, context_row, membership_row in zip(
            source_rows, context_rows, membership_rows, strict=True
        ):
            intent_key = source_row.get("intent_key")
            if intent_key != context_row.get("intent_key") or intent_key != membership_row.get("intent_key"):
                _fail("replayed source/context/fact rows are not in identical intent order")
            if intent_key not in referenced_keys:
                continue
            if intent_key in selected:
                _fail("referenced source intent appears more than once in its origin")
            semantic_profile, fact_profile = _verify_source_semantic_triplet(
                source_row,
                context_row,
                membership_row,
                persona_id=persona_id,
                origin=origin,
                fact_by_id=fact_by_id,
                semantic_by_source=semantic_by_source,
            )
            selected[intent_key] = {
                "context": context_row,
                "fact_profile": fact_profile,
                "membership": membership_row,
                "semantic_profile": semantic_profile,
                "source": source_row,
            }
        del (
            source_body,
            context_body,
            membership_body,
            source_rows,
            context_rows,
            membership_rows,
        )
    if set(selected) != referenced_keys:
        _fail("concrete overlay references are not a total exact structural/semantic join")
    return selected


def _require_endpoint_matches_reservation(
    selected,
    intent_key,
    *,
    expected_identity,
    expected_variant,
    expected_gate_role,
):
    projection = selected.get(intent_key)
    if projection is None:
        _fail("reservation endpoint does not resolve to a selected source")
    semantic_profile = projection["semantic_profile"]
    if (
        semantic_profile.get("variant_id") != expected_variant
        or semantic_profile.get("gate_role") != expected_gate_role
        or not _identity_matches(
            expected_identity, projection["context"], projection["membership"]
        )
    ):
        _fail("reservation endpoint differs from structural/semantic ownership")
    return projection


def _expected_rich_rows(persona_id, origin, reservation, selected, fact_by_id):
    rows = []
    relation_by_cluster = {}
    conflict_count = 0
    for reserved in reservation["reservation_rows"]:
        if reserved["row_kind"] != "content-relation-reservation":
            continue
        anchor = _require_endpoint_matches_reservation(
            selected,
            reserved["anchor_intent_key"],
            expected_identity=reserved["anchor_identity"],
            expected_variant=reserved["endpoint_variant_id"],
            expected_gate_role=reserved["endpoint_gate_role"],
        )
        derivative = _require_endpoint_matches_reservation(
            selected,
            reserved["derivative_intent_key"],
            expected_identity=reserved["derivative_identity"],
            expected_variant=reserved["endpoint_variant_id"],
            expected_gate_role=reserved["endpoint_gate_role"],
        )
        prefix = {
            "exact-duplicate": "exact",
            "near-revision": "near",
            "conflict-copy": "conflict",
        }[reserved["relation_kind"]]
        if (
            anchor["context"].get("content_relation_role") != f"{prefix}-anchor"
            or derivative["context"].get("content_relation_role")
            != f"{prefix}-derivative"
            or anchor["context"].get("language") != derivative["context"].get("language")
            or anchor["context"].get("topic_id") != derivative["context"].get("topic_id")
        ):
            _fail("relation endpoints do not preserve the semantic component contract")
        expected_versions = (
            ("v1", "v2") if reserved["relation_kind"] == "near-revision" else ("v1", "v1")
        )
        if (
            anchor["context"].get("semantic_version"),
            derivative["context"].get("semantic_version"),
        ) != expected_versions:
            _fail("relation endpoint semantic versions drifted")
        anchor_context = anchor["context"]
        derivative_context = derivative["context"]
        anchor_membership = anchor["membership"]
        derivative_membership = derivative["membership"]
        if (
            anchor_context.get("deterministic_payload_seed")
            == derivative_context.get("deterministic_payload_seed")
        ):
            _fail(
                "relation endpoints must retain distinct structural payload seeds; "
                "content equality is not raw-byte equality"
            )
        shared_semantic_and_fact = (
            anchor_context.get("semantic_profile_id")
            == derivative_context.get("semantic_profile_id")
            and anchor_membership.get("fact_profile_id")
            == derivative_membership.get("fact_profile_id")
            and anchor_membership.get("present_fact_ids")
            == derivative_membership.get("present_fact_ids")
        )
        shared_logical_identity = (
            anchor_membership.get("logical_document_key")
            == derivative_membership.get("logical_document_key"),
            anchor_membership.get("logical_branch_key")
            == derivative_membership.get("logical_branch_key"),
            anchor_membership.get("logical_revision_key")
            == derivative_membership.get("logical_revision_key"),
            anchor_membership.get("semantic_section_key")
            == derivative_membership.get("semantic_section_key"),
            anchor_context.get("payload_equivalence_key")
            == derivative_context.get("payload_equivalence_key"),
        )
        relation_kind = reserved["relation_kind"]
        if relation_kind == "exact-duplicate":
            if not shared_semantic_and_fact or not all(shared_logical_identity):
                _fail(
                    "exact endpoints must share semantic/fact profiles and every "
                    "logical content identity"
                )
        elif relation_kind == "near-revision":
            if (
                not shared_semantic_and_fact
                or not shared_logical_identity[0]
                or not shared_logical_identity[1]
                or shared_logical_identity[2]
                or not shared_logical_identity[3]
                or shared_logical_identity[4]
            ):
                _fail(
                    "near endpoints must share document/branch/section and fact "
                    "membership while revision and payload identities differ"
                )
        else:
            conflict_count += 1
            binding = reserved.get("conflict_fact_binding")
            anchor_profile = anchor["fact_profile"]
            derivative_profile = derivative["fact_profile"]
            if (
                type(binding) is not dict
                or anchor_profile.get("profile_kind") != "conflict-branch"
                or derivative_profile.get("profile_kind") != "conflict-branch"
                or anchor_profile.get("branch_role") != "a"
                or derivative_profile.get("branch_role") != "b"
                or anchor_profile.get("present_fact_ids")
                != binding.get("branch_a_present_fact_ids")
                or derivative_profile.get("present_fact_ids")
                != binding.get("branch_b_present_fact_ids")
                or anchor_profile.get("conflict_set_id") != binding.get("conflict_set_id")
                or derivative_profile.get("conflict_set_id") != binding.get("conflict_set_id")
                or anchor_profile.get("conflict_template_key") != binding.get("template_key")
                or derivative_profile.get("conflict_template_key") != binding.get("template_key")
                or anchor_profile.get("graph_id") != binding.get("graph_id")
                or derivative_profile.get("graph_id") != binding.get("graph_id")
            ):
                _fail("conflict endpoints do not join exact persona-owned A/B profiles")
            if (
                anchor_context.get("semantic_profile_id")
                != derivative_context.get("semantic_profile_id")
                or anchor_membership.get("fact_profile_id")
                == derivative_membership.get("fact_profile_id")
                or not shared_logical_identity[0]
                or shared_logical_identity[1]
                or shared_logical_identity[2]
                or not shared_logical_identity[3]
                or shared_logical_identity[4]
            ):
                _fail(
                    "conflict endpoints must share document/section/semantic profile "
                    "while branch, revision, payload, and fact profiles differ"
                )
            common = set(anchor_profile["present_fact_ids"]) & set(
                derivative_profile["present_fact_ids"]
            )
            branch_a = set(anchor_profile["present_fact_ids"])
            branch_b = set(derivative_profile["present_fact_ids"])
            unordered_pair = set(binding.get("unordered_member_fact_ids", []))
            if (
                len(common) != 6
                or len(branch_a) != 7
                or len(branch_b) != 7
                or len(branch_a | branch_b) != 8
                or branch_a ^ branch_b != unordered_pair
                or binding.get("branch_a_selected_fact_id") not in branch_a - branch_b
                or binding.get("branch_b_selected_fact_id") not in branch_b - branch_a
            ):
                _fail(
                    "conflict profiles are not the exact persona-owned "
                    "common-six-plus-distinct-one fact pair"
                )
        row = {
            "anchor_fact_profile_id": anchor["membership"]["fact_profile_id"],
            "anchor_intent_key": reserved["anchor_intent_key"],
            "cluster_key": reserved["cluster_key"],
            "derivative_fact_profile_id": derivative["membership"]["fact_profile_id"],
            "derivative_intent_key": reserved["derivative_intent_key"],
            "placement_class_requirement": reserved["placement_class_requirement"],
            "relation_kind": reserved["relation_kind"],
            "row_kind": "content-relation-membership",
            "search_participation_requirement_id": "content-relation-v2",
        }
        _validate_rich_row_fields(row)
        rows.append(row)
        if row["cluster_key"] in relation_by_cluster:
            _fail("relation cluster key is not unique within its origin")
        relation_by_cluster[row["cluster_key"]] = row

    attachment_keys = set()
    attachment_members = set()
    attachment_hosts = set()
    attachments_by_host = {}
    overlap_clusters = set()
    overlap_hosts = set()
    overlap_members = set()
    relation_endpoint_keys = {
        key
        for relation in relation_by_cluster.values()
        for key in (relation["anchor_intent_key"], relation["derivative_intent_key"])
    }
    for reserved in reservation["reservation_rows"]:
        if reserved["row_kind"] != "attachment-membership-reservation":
            continue
        host = _require_endpoint_matches_reservation(
            selected,
            reserved["host_intent_key"],
            expected_identity=reserved["host_identity"],
            expected_variant=reserved["host_variant_id"],
            expected_gate_role=reserved["host_gate_role"],
        )
        member = _require_endpoint_matches_reservation(
            selected,
            reserved["standalone_member_intent_key"],
            expected_identity=reserved["standalone_member_identity"],
            expected_variant=reserved["standalone_member_variant_id"],
            expected_gate_role=reserved["standalone_member_gate_role"],
        )
        if (
            host["context"].get("container_role_ids") != ["attachment-host"]
            or member["context"].get("container_role_ids") != ["attachment-member"]
            or host["context"].get("content_relation_role") != "independent"
            or reserved["host_intent_key"]
            == reserved["standalone_member_intent_key"]
            or host["context"].get("deterministic_payload_seed")
            == member["context"].get("deterministic_payload_seed")
            or host["context"].get("payload_equivalence_key")
            == member["context"].get("payload_equivalence_key")
            or host["membership"].get("logical_document_key")
            == member["membership"].get("logical_document_key")
            or member["context"].get("payload_equivalence_key")
            != reserved["decoded_payload_equivalence_key"]
            or host["context"].get("language") != member["context"].get("language")
            or host["context"].get("topic_id") != member["context"].get("topic_id")
            or host["context"].get("semantic_version") != "v1"
            or member["context"].get("semantic_version") != "v1"
            or host["semantic_profile"].get("variant_id") != "eml"
            or host["semantic_profile"].get("gate_role")
            not in {"contract_contributor", "incidental_searchable"}
            or member["semantic_profile"].get("variant_id") == "eml"
            or member["semantic_profile"].get("gate_role")
            not in {"contract_contributor", "incidental_searchable"}
            or host["membership"].get("fact_profile_id")
            != member["membership"].get("fact_profile_id")
            or host["membership"].get("present_fact_ids")
            != member["membership"].get("present_fact_ids")
        ):
            _fail("attachment host/member semantic join drifted")
        host_member_count = _require_exact_int(
            reserved.get("host_member_count"),
            label="attachment host member count",
            minimum=1,
            maximum=5,
        )
        member_ordinal = _require_exact_int(
            reserved.get("member_ordinal"),
            label="attachment member ordinal",
            minimum=1,
            maximum=host_member_count,
        )
        attachment_key = reserved.get("attachment_key")
        _ascii_key(attachment_key)
        if attachment_key in attachment_keys:
            _fail("attachment key is not unique within its origin")
        attachment_keys.add(attachment_key)
        standalone_key = reserved["standalone_member_intent_key"]
        if standalone_key in attachment_members:
            _fail("standalone attachment member is reused by multiple memberships")
        attachment_members.add(standalone_key)
        attachment_hosts.add(reserved["host_intent_key"])
        attachments_by_host.setdefault(reserved["host_intent_key"], []).append(
            (host_member_count, member_ordinal)
        )
        relation_membership = reserved["content_relation_membership"]
        if relation_membership == "none":
            if (
                standalone_key in relation_endpoint_keys
                or member["context"].get("content_relation_role") != "independent"
            ):
                _fail("fresh attachment member must remain an independent source")
        else:
            relation = relation_by_cluster.get(relation_membership)
            if (
                relation is None
                or relation["relation_kind"] != "exact-duplicate"
                or relation["derivative_intent_key"]
                != reserved["standalone_member_intent_key"]
                or member_ordinal != 1
                or member["context"].get("content_relation_role")
                != "exact-derivative"
                or relation_membership in overlap_clusters
                or reserved["host_intent_key"] in overlap_hosts
            ):
                _fail("attachment exact overlap does not target one exact derivative")
            overlap_clusters.add(relation_membership)
            overlap_hosts.add(reserved["host_intent_key"])
            overlap_members.add(standalone_key)
        row = {
            "attachment_key": reserved["attachment_key"],
            "content_relation_membership": relation_membership,
            "decoded_payload_equivalence_key": reserved[
                "decoded_payload_equivalence_key"
            ],
            "host_fact_profile_id": host["membership"]["fact_profile_id"],
            "host_intent_key": reserved["host_intent_key"],
            "host_member_count": host_member_count,
            "member_ordinal": member_ordinal,
            "row_kind": "attachment-membership",
            "search_participation_requirement_id": "attachment-structural-v2",
            "standalone_member_fact_profile_id": member["membership"]["fact_profile_id"],
            "standalone_member_intent_key": reserved["standalone_member_intent_key"],
        }
        _validate_rich_row_fields(row)
        rows.append(row)

    for memberships in attachments_by_host.values():
        declared_counts = {count for count, _ in memberships}
        if len(declared_counts) != 1:
            _fail("one attachment host declares inconsistent member counts")
        declared_count = next(iter(declared_counts))
        if (
            len(memberships) != declared_count
            or {ordinal for _, ordinal in memberships}
            != set(range(1, declared_count + 1))
        ):
            _fail("attachment host membership ordinals are not exact and complete")
    if (
        attachment_hosts & (relation_endpoint_keys | attachment_members)
        or overlap_members != attachment_members & relation_endpoint_keys
    ):
        _fail("attachment host/member/relation overlap algebra drifted")

    previous_anchor_ordinal = 0
    anchor_keys = set()
    if origin != "pilot" and reservation["semantic_anchor_slots"]:
        _fail("semantic anchor capacity is pilot-only")
    for reserved in reservation["semantic_anchor_slots"]:
        projection = selected[reserved["intent_key"]]
        profile = projection["fact_profile"]
        anchor_ordinal = _require_exact_int(
            reserved.get("semantic_anchor_slot_ordinal"),
            label="semantic anchor slot ordinal",
            minimum=1,
        )
        if (
            anchor_ordinal != previous_anchor_ordinal + 1
            or projection["context"].get("semantic_anchor_capacity") is not True
            or projection["context"].get("content_relation_role") != "independent"
            or projection["context"].get("container_role_ids") != []
            or projection["context"].get("semantic_version") != "v1"
            or profile.get("profile_kind") != "w0-singleton"
            or len(profile.get("present_fact_ids", [])) != 1
            or projection["semantic_profile"].get("gate_role")
            != "contract_contributor"
            or projection["semantic_profile"].get("variant_id") != reserved["variant_id"]
            or projection["semantic_profile"].get("gate_role") != reserved["gate_role"]
        ):
            _fail("semantic anchor does not join its exact singleton source membership")
        previous_anchor_ordinal = anchor_ordinal
        if reserved["intent_key"] in anchor_keys:
            _fail("semantic anchor intent is repeated within its origin")
        anchor_keys.add(reserved["intent_key"])
        row = {
            "fact_profile_id": projection["membership"]["fact_profile_id"],
            "intent_key": reserved["intent_key"],
            "row_kind": "semantic-anchor-membership",
            "semantic_anchor_slot_ordinal": anchor_ordinal,
        }
        _validate_rich_row_fields(row)
        rows.append(row)

    if conflict_count != reservation["target_marginals"]["conflict_copy_cluster_count"]:
        _fail("origin conflict row count differs from reservation target")
    if any(_sort_tuple(left) >= _sort_tuple(right) for left, right in zip(rows, rows[1:])):
        _fail("independently projected rich rows are not in strict canonical order")
    return rows


def _draft_projection(rows):
    projected = []
    for row in rows:
        if row["row_kind"] == "semantic-anchor-membership":
            continue
        if row["row_kind"] == "content-relation-membership":
            value = {
                "anchor_intent_key": row["anchor_intent_key"],
                "cluster_key": row["cluster_key"],
                "derivative_intent_key": row["derivative_intent_key"],
                "placement_class": row["placement_class_requirement"],
                "relation_kind": row["relation_kind"],
                "row_kind": "content-relation",
                "search_participation_profile_id": row[
                    "search_participation_requirement_id"
                ],
            }
        else:
            value = {
                "attachment_key": row["attachment_key"],
                "decoded_payload_equivalence_key": row[
                    "decoded_payload_equivalence_key"
                ],
                "host_intent_key": row["host_intent_key"],
                "member_ordinal": row["member_ordinal"],
                "row_kind": "attachment-membership",
                "search_participation_profile_id": row[
                    "search_participation_requirement_id"
                ],
                "standalone_member_intent_key": row[
                    "standalone_member_intent_key"
                ],
            }
        projected.append(value)
    return projected


def _canonical_jsonl_bytes(rows, *, label, row_cap=MAX_ROW_BYTES_INCLUDING_LF):
    parts = []
    maximum = 0
    for index, row in enumerate(rows, start=1):
        raw = _canonical_bytes(row, label=f"{label} row {index}", max_bytes=row_cap - 1) + b"\n"
        if len(raw) > row_cap:
            _fail(f"{label} row exceeds its LF-inclusive cap")
        parts.append(raw)
        maximum = max(maximum, len(raw))
    if not parts:
        _fail(f"{label} cannot be empty")
    body = b"".join(parts)
    return body, maximum


def _reservation_row_sort_key(row):
    kind = row.get("row_kind") if type(row) is dict else None
    if kind == "content-relation-reservation":
        relation = row.get("relation_kind")
        if relation not in RELATION_ORDER:
            _fail("reservation relation kind is unknown")
        key = row.get("cluster_key")
        _ascii_key(key)
        return [0, RELATION_ORDER.index(relation), key]
    if kind == "attachment-membership-reservation":
        key = row.get("attachment_key")
        _ascii_key(key)
        return [1, 0, key]
    _fail("reservation row kind cannot be mapped to a rich-row sort key")


def _serialized_sort_key_tuple(value, *, label):
    if (
        type(value) is not list
        or len(value) != 3
        or type(value[0]) is not int
        or type(value[1]) is not int
        or type(value[2]) is not str
    ):
        _fail(f"{label} must be one exact serialized row sort key")
    return (value[0], value[1], _ascii_key(value[2]))


def _reservation_rich_sort_keys(reservation):
    keys = [_reservation_row_sort_key(row) for row in reservation["reservation_rows"]]
    keys.extend(
        [
            2,
            _require_exact_int(
                row.get("semantic_anchor_slot_ordinal"),
                label="semantic anchor slot ordinal",
                minimum=1,
            ),
            row.get("intent_key"),
        ]
        for row in reservation["semantic_anchor_slots"]
    )
    if not keys:
        _fail("concrete overlay origin cannot be empty")
    tuples = [
        _serialized_sort_key_tuple(key, label="reserved rich-row sort key")
        for key in keys
    ]
    if any(left >= right for left, right in zip(tuples, tuples[1:])):
        _fail("reservation rows do not imply strict rich-row order")
    return keys


def _prevalidate_origin_body_metadata(manifest, reservation):
    persona_id = manifest["persona_id"]
    origin = manifest["origin"]
    rich_sort_keys = _reservation_rich_sort_keys(reservation)
    expected_row_count = len(rich_sort_keys)
    descriptors = manifest.get("shard_descriptors")
    if type(descriptors) is not list or len(descriptors) != 1:
        _fail("each concrete overlay origin must contain exactly one bounded shard")
    descriptor = descriptors[0]
    _require_exact_fields(
        descriptor, SHARD_DESCRIPTOR_FIELDS, label="concrete overlay shard descriptor"
    )
    _require_sha256(descriptor.get("body_sha256"), label="concrete overlay body SHA")
    _require_exact_int(
        descriptor.get("shard_index"),
        label="concrete overlay shard index",
        minimum=0,
        maximum=0,
    )
    _require_exact_int(
        descriptor.get("row_count"),
        label="concrete overlay shard row count",
        minimum=expected_row_count,
        maximum=expected_row_count,
    )
    if (
        descriptor.get("persona_id") != persona_id
        or descriptor.get("origin") != origin
        or descriptor.get("file_name")
        != f"{persona_id}-concrete-overlay-membership-{origin}-0000.jsonl"
    ):
        _fail("concrete overlay shard coordinate, row range, or file name drifted")
    _require_exact_value(
        descriptor.get("first_row_sort_key"),
        rich_sort_keys[0],
        label="concrete overlay shard first row sort key",
    )
    _require_exact_value(
        descriptor.get("last_row_sort_key"),
        rich_sort_keys[-1],
        label="concrete overlay shard last row sort key",
    )
    _require_exact_int(
        descriptor.get("body_bytes"),
        label="concrete overlay shard body bytes",
        minimum=1,
        maximum=MAX_SHARD_BODY_BYTES,
    )
    _require_exact_int(
        descriptor.get("maximum_row_bytes_including_lf"),
        label="concrete overlay shard maximum row bytes",
        minimum=1,
        maximum=MAX_ROW_BYTES_INCLUDING_LF,
    )
    if expected_row_count > MAX_ROWS_PER_SHARD:
        _fail("concrete overlay origin row count exceeds one-shard capacity")

    receipt = manifest.get("draft_membership_projection_receipt")
    _require_exact_fields(
        receipt,
        DRAFT_PROJECTION_RECEIPT_FIELDS,
        label="draft membership projection receipt",
    )
    _require_sha256(receipt.get("body_sha256"), label="draft projection SHA")
    projection_keys = [
        _reservation_row_sort_key(row) for row in reservation["reservation_rows"]
    ]
    if not projection_keys:
        _fail("draft projection receipt range differs from the reservation")
    _require_exact_int(
        receipt.get("row_count"),
        label="draft projection row count",
        minimum=len(projection_keys),
        maximum=len(projection_keys),
    )
    _require_exact_value(
        receipt.get("first_row_sort_key"),
        projection_keys[0],
        label="draft projection first row sort key",
    )
    _require_exact_value(
        receipt.get("last_row_sort_key"),
        projection_keys[-1],
        label="draft projection last row sort key",
    )
    _require_exact_int(
        receipt.get("body_bytes"),
        label="draft projection body bytes",
        minimum=1,
        maximum=MAX_SHARD_BODY_BYTES,
    )
    _require_exact_int(
        receipt.get("maximum_row_bytes_including_lf"),
        label="draft projection maximum row bytes",
        minimum=1,
        maximum=MAX_ROW_BYTES_INCLUDING_LF,
    )
    return descriptor


def _origin_metrics_from_rows(rows, reference_sets, *, body_bytes, maximum_row_bytes):
    relation_counts = {relation: 0 for relation in RELATION_ORDER}
    relation_placement = {
        relation: {placement: 0 for placement in PLACEMENT_ORDER}
        for relation in RELATION_ORDER
    }
    attachment_count = 0
    anchor_count = 0
    for row in rows:
        kind = row["row_kind"]
        if kind == "content-relation-membership":
            relation = row["relation_kind"]
            placement = row["placement_class_requirement"]
            if placement not in PLACEMENT_ORDER:
                _fail("content relation placement requirement is unknown")
            relation_counts[relation] += 1
            relation_placement[relation][placement] += 1
        elif kind == "attachment-membership":
            attachment_count += 1
        else:
            anchor_count += 1
    content_count = sum(relation_counts.values())
    overlay_count = content_count + attachment_count
    return {
        "attachment_exact_overlap_row_count": len(reference_sets["overlap_members"]),
        "attachment_host_count": len(reference_sets["attachment_hosts"]),
        "attachment_membership_row_count": attachment_count,
        "conflict_copy_row_count": relation_counts["conflict-copy"],
        "content_relation_row_count": content_count,
        "exact_duplicate_row_count": relation_counts["exact-duplicate"],
        "joined_source_reference_occurrence_count": (
            reference_sets["occurrence_count"] + anchor_count
        ),
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "near_revision_row_count": relation_counts["near-revision"],
        "overlay_membership_row_count": overlay_count,
        "overlay_source_reference_occurrence_count": reference_sets[
            "occurrence_count"
        ],
        "relation_placement_joint_marginals": relation_placement,
        "rich_row_count": len(rows),
        "semantic_anchor_membership_row_count": anchor_count,
        "shard_body_bytes": body_bytes,
        "shard_count": 1,
        "unique_joined_source_count": len(
            reference_sets["overlay"] | reference_sets["anchors"]
        ),
        "unique_overlay_source_count": len(reference_sets["overlay"]),
    }


def _validate_one_origin_body(
    manifest,
    reservation,
    source_manifest,
    *,
    target_provider,
    source_provider,
    context_provider,
    membership_provider,
    fact_by_id,
    semantic_by_source,
):
    persona_id = manifest["persona_id"]
    origin = manifest["origin"]
    descriptor = manifest["shard_descriptors"][0]
    references = _reservation_reference_sets(reservation)
    referenced_keys = references["overlay"] | references["anchors"]
    selected = _parse_replayed_upstream_rows(
        persona_id,
        origin,
        source_manifest,
        referenced_keys,
        source_provider=source_provider,
        context_provider=context_provider,
        membership_provider=membership_provider,
        fact_by_id=fact_by_id,
        semantic_by_source=semantic_by_source,
    )
    expected_rows = _expected_rich_rows(
        persona_id, origin, reservation, selected, fact_by_id
    )
    expected_body, _ = _canonical_jsonl_bytes(
        expected_rows, label="independently projected concrete overlay membership"
    )
    body = target_provider(persona_id, origin, 0)
    replayed_body = target_provider.replay(persona_id, origin, 0)
    if body != replayed_body:
        _fail("concrete overlay body changed across exact provider replay")
    rows, maximum_row_bytes = _parse_canonical_jsonl(
        body,
        label=f"concrete overlay membership shard {persona_id}/{origin}/0",
        row_cap=MAX_ROW_BYTES_INCLUDING_LF,
        body_cap=MAX_SHARD_BODY_BYTES,
        max_rows=MAX_ROWS_PER_SHARD,
    )
    for row in rows:
        _validate_rich_row_fields(row)
    if any(
        _sort_tuple(left) >= _sort_tuple(right)
        for left, right in zip(rows, rows[1:])
    ):
        _fail("concrete overlay body rows are not in strict canonical order")
    if body != expected_body:
        _fail("concrete overlay body differs from its exact reservation/source join")
    if (
        descriptor["body_bytes"] != len(body)
        or descriptor["body_sha256"] != _sha256(body)
        or descriptor["row_count"] != len(rows)
        or descriptor["maximum_row_bytes_including_lf"] != maximum_row_bytes
        or descriptor["first_row_sort_key"] != _row_sort_key(rows[0])
        or descriptor["last_row_sort_key"] != _row_sort_key(rows[-1])
    ):
        _fail("concrete overlay body differs from its exact shard descriptor")

    projection_rows = _draft_projection(rows)
    projection_body, projection_maximum = _canonical_jsonl_bytes(
        projection_rows, label="draft membership projection"
    )
    rich_projection_rows = [
        row for row in rows if row["row_kind"] != "semantic-anchor-membership"
    ]
    expected_receipt = {
        "body_bytes": len(projection_body),
        "body_sha256": _sha256(projection_body),
        "first_row_sort_key": _row_sort_key(rich_projection_rows[0]),
        "last_row_sort_key": _row_sort_key(rich_projection_rows[-1]),
        "maximum_row_bytes_including_lf": projection_maximum,
        "row_count": len(projection_rows),
    }
    if manifest["draft_membership_projection_receipt"] != expected_receipt:
        _fail("draft membership projection receipt differs from exact rich rows")
    metrics = _origin_metrics_from_rows(
        rows,
        references,
        body_bytes=len(body),
        maximum_row_bytes=maximum_row_bytes,
    )
    if metrics["relation_placement_joint_marginals"] != reservation[
        "relation_placement_joint_marginals"
    ]:
        _fail("body-derived relation/placement joint marginal differs from reservation")
    del (
        body,
        replayed_body,
        expected_body,
        rows,
        expected_rows,
        projection_rows,
        projection_body,
        rich_projection_rows,
        selected,
    )
    gc.collect()
    return metrics


def _artifact_binding(
    name,
    role,
    value,
    *,
    label,
    max_bytes,
    coordinate_fields=(),
):
    if type(value) is not dict:
        _fail(f"{label} binding target must be an object")
    for field in ("artifact_kind", "artifact_schema", "artifact_schema_version"):
        if field not in value:
            _fail(f"{label} binding target lacks artifact identity")
    raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    result = {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": role,
        "name": name,
        "sha256": _sha256(raw),
    }
    for field in coordinate_fields:
        if field not in value:
            _fail(f"{label} binding target lacks coordinate field {field}")
        result[field] = value[field]
    return result


def _validate_input_bindings(value, expected, *, label):
    if type(value) is not dict:
        _fail(f"{label} must be an object")
    _require_exact_value(value.get("input_bindings"), expected, label=f"{label} inputs")
    _require_exact_value(
        value.get("input_binding_order"),
        [row["name"] for row in expected],
        label=f"{label} input order",
    )
    for index, binding in enumerate(expected):
        fields = PUBLIC_INPUT_BINDING_FIELDS
        if "origin" in binding:
            fields = ORIGIN_COORDINATE_BINDING_FIELDS
        elif "profile" in binding:
            fields = PROFILE_COORDINATE_BINDING_FIELDS
        _require_exact_fields(
            binding, fields, label=f"{label} expected binding {index}"
        )


def _contains_exact_binding(bindings, expected):
    return type(bindings) is list and any(
        _exact_value_equal(binding, expected) for binding in bindings
    )


def _validate_upstream_envelope(
    value,
    *,
    fields,
    kind,
    schema,
    authority_fields,
    label,
    max_bytes,
):
    _canonical_bytes(value, label=label, max_bytes=max_bytes)
    _require_exact_fields(value, fields, label=label)
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or type(value.get("artifact_schema_version")) is not int
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or type(value.get("fixture_schema_version")) is not int
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
    ):
        _fail(f"{label} artifact identity or fixture binding drifted")
    authority = value.get("authority")
    if type(authority) is not dict or set(authority) != set(authority_fields):
        _fail(f"{label} authority field set drifted")
    if any(type(flag) is not bool or flag is not False for flag in authority.values()):
        _fail(f"{label} authority must remain exact all-false")


def _persona_target(overlay_contract_value, persona_id, profile):
    rows = overlay_contract_value.get("persona_target_marginals")
    if type(rows) is not list:
        _fail("overlay contract persona target marginals are absent")
    matches = [row for row in rows if row.get("persona_id") == persona_id]
    if len(matches) != 1 or type(matches[0].get("targets")) is not dict:
        _fail("overlay contract persona target marginal is not unique")
    target = matches[0]["targets"].get(profile)
    if type(target) is not dict:
        _fail("overlay contract lacks the requested persona/profile target")
    return target


def _validate_target_common(
    value,
    *,
    fields,
    kind,
    schema,
    label,
    max_bytes,
    canonical_limits,
    completion_claims,
    completion_scope,
    dependency_contract,
):
    _canonical_bytes(value, label=label, max_bytes=max_bytes)
    _require_exact_fields(value, fields, label=label)
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or type(value.get("artifact_schema_version")) is not int
        or value.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or value.get("fixture_id") != envelope.FIXTURE_ID
        or type(value.get("fixture_schema_version")) is not int
        or value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION
        or value.get("g0_contract_frozen") is not False
        or value.get("hypothesis_status") != HYPOTHESIS_STATUS
    ):
        _fail(f"{label} identity, fixture, hypothesis, or G0 state drifted")
    _require_all_false_authority(value.get("authority"), label=label)
    _require_exact_value(
        value.get("canonical_limits"), canonical_limits, label=f"{label} limits"
    )
    _require_exact_value(
        value.get("completion_claims"),
        completion_claims,
        label=f"{label} completion claims",
    )
    if value.get("completion_scope") != completion_scope:
        _fail(f"{label} completion scope drifted")
    _require_exact_value(
        value.get("dependency_direction_contract"),
        dependency_contract,
        label=f"{label} dependency contract",
    )
    _require_exact_value(
        value.get("remaining_blockers"), REMAINING_BLOCKERS, label=f"{label} blockers"
    )


def _prevalidate_upstream_metadata(
    *,
    overlay_contract_value,
    reservation_suite,
    reservation_origin_artifacts,
    semantic_catalog,
    semantic_suite,
    semantic_origin_manifests,
    semantic_profile_manifests,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
):
    try:
        overlay_contract.validate_overlay_contract(overlay_contract_value)
        reservation_validator.validate_overlay_reservation_suite(
            reservation_suite, reservation_origin_artifacts
        )
        semantic_validator.validate_source_semantic_membership_catalog(
            semantic_catalog
        )
    except (
        overlay_contract.PersonaV2OverlayContractError,
        reservation_validator.PersonaV2OverlayReservationValidationError,
        semantic_validator.PersonaV2SourceSemanticMembershipPackageValidationError,
    ) as error:
        _fail(str(error))

    collections = (
        (reservation_origin_artifacts, "reservation origin artifacts"),
        (semantic_origin_manifests, "semantic origin manifests"),
        (semantic_profile_manifests, "semantic profile manifests"),
        (source_origin_manifests, "source origin manifests"),
        (source_profile_manifests, "source profile manifests"),
    )
    for values, label in collections:
        if type(values) is not list:
            _fail(f"{label} must be an exact list")
    if any(
        len(values) != expected
        for values, expected in (
            (reservation_origin_artifacts, EXPECTED_ORIGIN_COUNT),
            (semantic_origin_manifests, EXPECTED_ORIGIN_COUNT),
            (source_origin_manifests, EXPECTED_ORIGIN_COUNT),
            (semantic_profile_manifests, EXPECTED_PROFILE_COUNT),
            (source_profile_manifests, EXPECTED_PROFILE_COUNT),
        )
    ):
        _fail("upstream package does not contain exact forty origin/profile artifacts")

    _validate_upstream_envelope(
        source_suite,
        fields=source_validator.SUITE_TOP_LEVEL_FIELDS,
        kind=source_validator.SUITE_ARTIFACT_KIND,
        schema=source_validator.SUITE_ARTIFACT_SCHEMA,
        authority_fields=source_validator.AUTHORITY_FIELDS,
        label="bound source inventory suite",
        max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    _validate_upstream_envelope(
        semantic_suite,
        fields=semantic_validator.SUITE_TOP_LEVEL_FIELDS,
        kind=semantic_validator.SUITE_ARTIFACT_KIND,
        schema=semantic_validator.SUITE_ARTIFACT_SCHEMA,
        authority_fields=semantic_validator.AUTHORITY_FIELDS,
        label="bound source semantic membership suite",
        max_bytes=semantic_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )

    expected_origins = [
        (persona_id, origin)
        for persona_id in envelope.PERSONA_IDS
        for origin in ORIGIN_ORDER
    ]
    expected_profiles = [
        (persona_id, profile)
        for persona_id in envelope.PERSONA_IDS
        for profile in PROFILE_ORDER
    ]
    reservation_by_key = {}
    source_origin_by_key = {}
    semantic_origin_by_key = {}
    for index, coordinate in enumerate(expected_origins):
        reservation = reservation_origin_artifacts[index]
        source_manifest = source_origin_manifests[index]
        semantic_manifest = semantic_origin_manifests[index]
        if any(
            type(value) is not dict
            for value in (reservation, source_manifest, semantic_manifest)
        ):
            _fail("upstream origin artifacts must be exact objects")
        if (
            (reservation.get("persona_id"), reservation.get("origin")) != coordinate
            or (source_manifest.get("persona_id"), source_manifest.get("origin"))
            != coordinate
            or (
                semantic_manifest.get("persona_id"),
                semantic_manifest.get("origin"),
            )
            != coordinate
        ):
            _fail("upstream origin artifacts are not in persona/origin order")
        _validate_upstream_envelope(
            source_manifest,
            fields=source_validator.ORIGIN_TOP_LEVEL_FIELDS,
            kind=source_validator.ORIGIN_ARTIFACT_KIND,
            schema=source_validator.ORIGIN_ARTIFACT_SCHEMA,
            authority_fields=source_validator.AUTHORITY_FIELDS,
            label="bound source inventory origin manifest",
            max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        _validate_upstream_envelope(
            semantic_manifest,
            fields=semantic_validator.ORIGIN_TOP_LEVEL_FIELDS,
            kind=semantic_validator.ORIGIN_ARTIFACT_KIND,
            schema=semantic_validator.ORIGIN_ARTIFACT_SCHEMA,
            authority_fields=semantic_validator.AUTHORITY_FIELDS,
            label="bound source semantic origin manifest",
            max_bytes=semantic_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        reservation_by_key[coordinate] = reservation
        source_origin_by_key[coordinate] = source_manifest
        semantic_origin_by_key[coordinate] = semantic_manifest

    source_profile_by_key = {}
    semantic_profile_by_key = {}
    for index, coordinate in enumerate(expected_profiles):
        source_manifest = source_profile_manifests[index]
        semantic_manifest = semantic_profile_manifests[index]
        if type(source_manifest) is not dict or type(semantic_manifest) is not dict:
            _fail("upstream profile manifests must be exact objects")
        if (
            (source_manifest.get("persona_id"), source_manifest.get("profile"))
            != coordinate
            or (
                semantic_manifest.get("persona_id"),
                semantic_manifest.get("profile"),
            )
            != coordinate
        ):
            _fail("upstream profile manifests are not in persona/profile order")
        _validate_upstream_envelope(
            source_manifest,
            fields=source_validator.PROFILE_TOP_LEVEL_FIELDS,
            kind=source_validator.PROFILE_ARTIFACT_KIND,
            schema=source_validator.PROFILE_ARTIFACT_SCHEMA,
            authority_fields=source_validator.AUTHORITY_FIELDS,
            label="bound source inventory profile manifest",
            max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
        )
        _validate_upstream_envelope(
            semantic_manifest,
            fields=semantic_validator.PROFILE_TOP_LEVEL_FIELDS,
            kind=semantic_validator.PROFILE_ARTIFACT_KIND,
            schema=semantic_validator.PROFILE_ARTIFACT_SCHEMA,
            authority_fields=semantic_validator.AUTHORITY_FIELDS,
            label="bound source semantic profile manifest",
            max_bytes=semantic_validator.MAX_PROFILE_MANIFEST_BYTES,
        )
        source_profile_by_key[coordinate] = source_manifest
        semantic_profile_by_key[coordinate] = semantic_manifest

    return {
        "expected_origins": expected_origins,
        "expected_profiles": expected_profiles,
        "reservation_by_key": reservation_by_key,
        "semantic_origin_by_key": semantic_origin_by_key,
        "semantic_profile_by_key": semantic_profile_by_key,
        "source_origin_by_key": source_origin_by_key,
        "source_profile_by_key": source_profile_by_key,
    }


def _origin_summary_from_reservation(reservation, descriptor):
    relation_counts = {relation: 0 for relation in RELATION_ORDER}
    attachment_count = 0
    for row in reservation["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            relation_counts[row["relation_kind"]] += 1
        else:
            attachment_count += 1
    references = _reservation_reference_sets(reservation)
    content_count = sum(relation_counts.values())
    anchor_count = len(references["anchors"])
    return {
        "attachment_exact_overlap_row_count": len(references["overlap_members"]),
        "attachment_host_count": len(references["attachment_hosts"]),
        "attachment_membership_row_count": attachment_count,
        "conflict_copy_row_count": relation_counts["conflict-copy"],
        "content_relation_row_count": content_count,
        "exact_duplicate_row_count": relation_counts["exact-duplicate"],
        "joined_source_reference_occurrence_count": (
            references["occurrence_count"] + anchor_count
        ),
        "maximum_row_bytes_including_lf": descriptor[
            "maximum_row_bytes_including_lf"
        ],
        "near_revision_row_count": relation_counts["near-revision"],
        "overlay_membership_row_count": content_count + attachment_count,
        "overlay_source_reference_occurrence_count": references["occurrence_count"],
        "rich_row_count": content_count + attachment_count + anchor_count,
        "semantic_anchor_membership_row_count": anchor_count,
        "shard_body_bytes": descriptor["body_bytes"],
        "shard_count": 1,
        "unique_joined_source_count": len(
            references["overlay"] | references["anchors"]
        ),
        "unique_overlay_source_count": len(references["overlay"]),
    }


def _prevalidate_target_origins(
    origin_manifests,
    *,
    upstream,
    overlay_contract_value,
    semantic_catalog,
):
    if type(origin_manifests) is not list or len(origin_manifests) != EXPECTED_ORIGIN_COUNT:
        _fail("target package requires exact forty origin manifests")
    result = {}
    canonical_bytes_by_key = {}
    for manifest, coordinate in zip(
        origin_manifests, upstream["expected_origins"], strict=True
    ):
        if type(manifest) is not dict:
            _fail("target origin manifest must be an exact object")
        persona_id, origin = coordinate
        if (manifest.get("persona_id"), manifest.get("origin")) != coordinate:
            _fail("target origin manifests are not in persona/origin order")
        _validate_target_common(
            manifest,
            fields=ORIGIN_TOP_LEVEL_FIELDS,
            kind=ORIGIN_ARTIFACT_KIND,
            schema=ORIGIN_ARTIFACT_SCHEMA,
            label="concrete overlay origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
            canonical_limits=ORIGIN_CANONICAL_LIMITS,
            completion_claims=ORIGIN_COMPLETION_CLAIMS,
            completion_scope=ORIGIN_COMPLETION_SCOPE,
            dependency_contract=ORIGIN_DEPENDENCY_CONTRACT,
        )
        reservation = upstream["reservation_by_key"][coordinate]
        source_manifest = upstream["source_origin_by_key"][coordinate]
        semantic_manifest = upstream["semantic_origin_by_key"][coordinate]
        descriptor = _prevalidate_origin_body_metadata(manifest, reservation)
        target_profile = "pilot" if origin == "pilot" else "full-minus-pilot"
        if manifest.get("target_profile") != target_profile:
            _fail("target origin profile coordinate drifted")
        _require_exact_value(
            manifest.get("target_marginals"),
            _persona_target(overlay_contract_value, persona_id, target_profile),
            label="origin target marginals",
        )
        expected_summary = _origin_summary_from_reservation(reservation, descriptor)
        _require_exact_fields(
            manifest.get("summary"), ORIGIN_SUMMARY_FIELDS, label="origin summary"
        )
        _require_exact_value(
            manifest.get("summary"), expected_summary, label="origin summary"
        )
        expected_bindings = [
            _artifact_binding(
                "persona-v2-source-semantic-membership-catalog",
                "semantic-profile-topic-and-fact-profile-owner",
                semantic_catalog,
                label="semantic catalog",
                max_bytes=semantic_validator.MAX_CATALOG_BYTES,
            ),
            _artifact_binding(
                "persona-v2-overlay-reservation-origin",
                "matching-overlay-relation-container-and-anchor-reservation",
                reservation,
                label="overlay reservation origin",
                max_bytes=reservation_validator.MAX_ORIGIN_ARTIFACT_BYTES,
                coordinate_fields=("persona_id", "origin"),
            ),
            _artifact_binding(
                "persona-v2-source-inventory-origin-manifest",
                "matching-immutable-structural-source-owner",
                source_manifest,
                label="source inventory origin manifest",
                max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
                coordinate_fields=("persona_id", "origin"),
            ),
            _artifact_binding(
                "persona-v2-source-semantic-membership-origin-manifest",
                "matching-source-owned-context-and-fact-membership-owner",
                semantic_manifest,
                label="source semantic origin manifest",
                max_bytes=semantic_validator.MAX_ORIGIN_MANIFEST_BYTES,
                coordinate_fields=("persona_id", "origin"),
            ),
        ]
        _validate_input_bindings(
            manifest, expected_bindings, label="concrete overlay origin manifest"
        )

        # Explicitly prove that the caller-supplied source and semantic origin
        # manifests bind this same reservation, rather than a regenerated or
        # rethreaded sibling with matching coordinates.
        source_reservation_binding = _artifact_binding(
            "persona-v2-overlay-reservation-origin",
            "matching-overlay-source-reference-reservation",
            reservation,
            label="source-bound reservation origin",
            max_bytes=reservation_validator.MAX_ORIGIN_ARTIFACT_BYTES,
            coordinate_fields=("persona_id", "origin"),
        )
        semantic_reservation_binding = _artifact_binding(
            "persona-v2-overlay-reservation-origin",
            "matching-relation-container-anchor-and-conflict-reservation",
            reservation,
            label="semantic-bound reservation origin",
            max_bytes=reservation_validator.MAX_ORIGIN_ARTIFACT_BYTES,
            coordinate_fields=("persona_id", "origin"),
        )
        semantic_source_binding = _artifact_binding(
            "persona-v2-source-inventory-origin-manifest",
            "immutable-source-row-owner",
            source_manifest,
            label="semantic-bound source origin",
            max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
            coordinate_fields=("persona_id", "origin"),
        )
        if not _contains_exact_binding(
            source_manifest.get("input_bindings"), source_reservation_binding
        ):
            _fail("source origin does not bind the caller-supplied reservation origin")
        if not _contains_exact_binding(
            semantic_manifest.get("input_bindings"), semantic_reservation_binding
        ) or not _contains_exact_binding(
            semantic_manifest.get("input_bindings"), semantic_source_binding
        ):
            _fail("semantic origin does not bind the caller-supplied source/reservation")

        raw = _canonical_bytes(
            manifest,
            label="concrete overlay origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        canonical_bytes_by_key[coordinate] = len(raw)
        result[coordinate] = manifest
    return result, canonical_bytes_by_key


def _profile_completion_claims(profile):
    return {
        "all_profile_overlay_memberships_bound": True,
        "all_profile_semantic_anchor_memberships_bound": True,
        "concrete_overlay_membership_bound": True,
        "formal_complete_persona_package_cap_proved": False,
        "full_profile_exact_pilot_origin_reuse_proved": profile == "full",
        "pilot_profile_single_origin_bound": profile == "pilot",
        "placement_integer_allocation_bound": False,
        "raw_or_rendered_identity_attested": False,
        "scope_assignment_present": False,
        "search_history_or_query_observation_bound": False,
    }


def _profile_summary_from_origins(origins, profile):
    summaries = [row["summary"] for row in origins]
    additive_fields = set(ORIGIN_SUMMARY_FIELDS) - {
        "maximum_row_bytes_including_lf"
    }
    result = {
        field: sum(summary[field] for summary in summaries)
        for field in additive_fields
    }
    pilot_summary = summaries[0]
    result.update(
        {
            "maximum_row_bytes_including_lf": max(
                summary["maximum_row_bytes_including_lf"] for summary in summaries
            ),
            "origin_manifest_count": len(origins),
            "reused_pilot_rich_row_count": (
                pilot_summary["rich_row_count"] if profile == "full" else 0
            ),
            "reused_pilot_shard_body_bytes": (
                pilot_summary["shard_body_bytes"] if profile == "full" else 0
            ),
            "reused_pilot_shard_count": (
                pilot_summary["shard_count"] if profile == "full" else 0
            ),
        }
    )
    return result


def _prevalidate_target_profiles(
    profile_manifests,
    *,
    upstream,
    origin_by_key,
    overlay_contract_value,
    reservation_suite,
    semantic_catalog,
):
    if (
        type(profile_manifests) is not list
        or len(profile_manifests) != EXPECTED_PROFILE_COUNT
    ):
        _fail("target package requires exact forty profile manifests")
    result = {}
    canonical_bytes_by_key = {}
    for manifest, coordinate in zip(
        profile_manifests, upstream["expected_profiles"], strict=True
    ):
        if type(manifest) is not dict:
            _fail("target profile manifest must be an exact object")
        persona_id, profile = coordinate
        if (manifest.get("persona_id"), manifest.get("profile")) != coordinate:
            _fail("target profile manifests are not in persona/profile order")
        _validate_target_common(
            manifest,
            fields=PROFILE_TOP_LEVEL_FIELDS,
            kind=PROFILE_ARTIFACT_KIND,
            schema=PROFILE_ARTIFACT_SCHEMA,
            label="concrete overlay profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
            canonical_limits=PROFILE_CANONICAL_LIMITS,
            completion_claims=_profile_completion_claims(profile),
            completion_scope=PROFILE_COMPLETION_SCOPE,
            dependency_contract=PROFILE_DEPENDENCY_CONTRACT,
        )
        origins = (
            [origin_by_key[(persona_id, "pilot")]]
            if profile == "pilot"
            else [
                origin_by_key[(persona_id, "pilot")],
                origin_by_key[(persona_id, "full-residual")],
            ]
        )
        _require_exact_value(
            manifest.get("origin_order"),
            [row["origin"] for row in origins],
            label="profile origin order",
        )
        expected_descriptors = [
            descriptor
            for origin_manifest in origins
            for descriptor in origin_manifest["shard_descriptors"]
        ]
        _require_exact_value(
            manifest.get("shard_descriptors"),
            expected_descriptors,
            label="profile shard descriptor composition",
        )
        for descriptor in manifest["shard_descriptors"]:
            _require_exact_fields(
                descriptor,
                SHARD_DESCRIPTOR_FIELDS,
                label="profile concrete overlay shard descriptor",
            )
            _require_exact_int(
                descriptor.get("shard_index"),
                label="profile origin-local shard index",
                minimum=0,
                maximum=0,
            )
        expected_origin_bindings = [
            _artifact_binding(
                "persona-v2-concrete-overlay-membership-origin-manifest",
                "immutable-concrete-overlay-origin-owner",
                origin_manifest,
                label="concrete overlay origin manifest",
                max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
                coordinate_fields=("persona_id", "origin"),
            )
            for origin_manifest in origins
        ]
        _require_exact_value(
            manifest.get("origin_manifest_bindings"),
            expected_origin_bindings,
            label="profile origin manifest bindings",
        )
        source_profile = upstream["source_profile_by_key"][coordinate]
        semantic_profile = upstream["semantic_profile_by_key"][coordinate]
        expected_inputs = [
            _artifact_binding(
                "persona-v2-source-semantic-membership-catalog",
                "semantic-profile-topic-and-fact-profile-owner",
                semantic_catalog,
                label="semantic catalog",
                max_bytes=semantic_validator.MAX_CATALOG_BYTES,
            ),
            _artifact_binding(
                "persona-v2-overlay-reservation-suite",
                "global-overlay-reservation-index",
                reservation_suite,
                label="overlay reservation suite",
                max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
            ),
            _artifact_binding(
                "persona-v2-source-inventory-profile-manifest",
                "matching-structural-source-profile-composition",
                source_profile,
                label="source inventory profile manifest",
                max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
                coordinate_fields=("persona_id", "profile"),
            ),
            _artifact_binding(
                "persona-v2-source-semantic-membership-profile-manifest",
                "matching-source-semantic-profile-composition",
                semantic_profile,
                label="source semantic profile manifest",
                max_bytes=semantic_validator.MAX_PROFILE_MANIFEST_BYTES,
                coordinate_fields=("persona_id", "profile"),
            ),
        ]
        _validate_input_bindings(
            manifest, expected_inputs, label="concrete overlay profile manifest"
        )
        source_reservation_binding = _artifact_binding(
            "persona-v2-overlay-reservation-suite",
            "overlay-source-reference-reservations",
            reservation_suite,
            label="source-profile-bound reservation suite",
            max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
        )
        if not _contains_exact_binding(
            source_profile.get("input_bindings"), source_reservation_binding
        ):
            _fail("source profile does not bind the caller-supplied reservation suite")

        _require_exact_fields(
            manifest.get("summary"), PROFILE_SUMMARY_FIELDS, label="profile summary"
        )
        _require_exact_value(
            manifest.get("summary"),
            _profile_summary_from_origins(origins, profile),
            label="profile summary",
        )
        _require_exact_value(
            manifest.get("target_marginals"),
            _persona_target(overlay_contract_value, persona_id, profile),
            label="profile target marginals",
        )
        raw = _canonical_bytes(
            manifest,
            label="concrete overlay profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        canonical_bytes_by_key[coordinate] = len(raw)
        result[coordinate] = manifest

    for persona_id in envelope.PERSONA_IDS:
        pilot = result[(persona_id, "pilot")]
        full = result[(persona_id, "full")]
        if (
            not _exact_value_equal(
                pilot["origin_manifest_bindings"],
                full["origin_manifest_bindings"][:1],
            )
            or not _exact_value_equal(
                pilot["shard_descriptors"],
                full["shard_descriptors"][: len(pilot["shard_descriptors"])],
            )
        ):
            _fail("full profile does not reuse the exact pilot origin and shard prefix")
    return result, canonical_bytes_by_key


def _expected_persona_ledgers(
    *,
    overlay_contract_value,
    semantic_suite,
    origin_by_key,
    profile_by_key,
    origin_bytes_by_key,
    profile_bytes_by_key,
):
    semantic_ledgers = semantic_suite.get("persona_current_component_byte_ledgers")
    if type(semantic_ledgers) is not list or len(semantic_ledgers) != len(
        envelope.PERSONA_IDS
    ):
        _fail("semantic suite persona ledger coverage drifted")
    semantic_by_persona = {}
    for row, persona_id in zip(semantic_ledgers, envelope.PERSONA_IDS, strict=True):
        if type(row) is not dict or row.get("persona_id") != persona_id:
            _fail("semantic suite persona ledgers are not in persona order")
        _require_exact_int(
            row.get("current_component_bytes"),
            label="semantic current component bytes",
            minimum=1,
            maximum=MAX_PERSONA_PACKAGE_BYTES,
        )
        semantic_by_persona[persona_id] = row
    contract_bytes = len(
        _canonical_bytes(
            overlay_contract_value,
            label="persona v2 overlay contract",
            max_bytes=overlay_contract.MAX_OVERLAY_CONTRACT_BYTES,
        )
    )
    ledgers = []
    for persona_id in envelope.PERSONA_IDS:
        concrete_body_bytes = sum(
            origin_by_key[(persona_id, origin)]["summary"]["shard_body_bytes"]
            for origin in ORIGIN_ORDER
        )
        origin_manifest_bytes = sum(
            origin_bytes_by_key[(persona_id, origin)] for origin in ORIGIN_ORDER
        )
        profile_manifest_bytes = sum(
            profile_bytes_by_key[(persona_id, profile)] for profile in PROFILE_ORDER
        )
        semantic_current = semantic_by_persona[persona_id]["current_component_bytes"]
        current = (
            semantic_current
            + contract_bytes
            + concrete_body_bytes
            + origin_manifest_bytes
            + profile_manifest_bytes
        )
        if current > MAX_PERSONA_PACKAGE_BYTES:
            _fail("persona current concrete component exceeds 16 MiB")
        ledgers.append(
            {
                "concrete_origin_body_bytes": concrete_body_bytes,
                "concrete_origin_manifest_bytes": origin_manifest_bytes,
                "concrete_profile_manifest_bytes": profile_manifest_bytes,
                "current_component_bytes": current,
                "current_component_cap_satisfied": True,
                "formal_complete_persona_package_cap_proved": False,
                "headroom_bytes": MAX_PERSONA_PACKAGE_BYTES - current,
                "max_current_component_bytes": MAX_PERSONA_PACKAGE_BYTES,
                "overlay_contract_bytes_conservatively_charged_in_full": contract_bytes,
                "persona_id": persona_id,
                "semantic_current_component_bytes": semantic_current,
            }
        )
    return ledgers


def _suite_summary_from_metadata(
    origin_manifests,
    profile_manifests,
    ledgers,
    *,
    origin_bytes_by_key,
    profile_bytes_by_key,
):
    summaries = [row["summary"] for row in origin_manifests]
    additive_fields = set(ORIGIN_SUMMARY_FIELDS) - {
        "maximum_row_bytes_including_lf"
    }
    result = {
        field: sum(summary[field] for summary in summaries)
        for field in additive_fields
    }
    result.update(
        {
            "draft_projection_body_bytes": sum(
                row["draft_membership_projection_receipt"]["body_bytes"]
                for row in origin_manifests
            ),
            "draft_projection_row_count": sum(
                row["draft_membership_projection_receipt"]["row_count"]
                for row in origin_manifests
            ),
            "maximum_origin_manifest_bytes": max(origin_bytes_by_key.values()),
            "maximum_persona_current_component_bytes": max(
                row["current_component_bytes"] for row in ledgers
            ),
            "maximum_profile_manifest_bytes": max(profile_bytes_by_key.values()),
            "maximum_row_bytes_including_lf": max(
                summary["maximum_row_bytes_including_lf"] for summary in summaries
            ),
            "maximum_shard_body_bytes": max(
                descriptor["body_bytes"]
                for row in origin_manifests
                for descriptor in row["shard_descriptors"]
            ),
            "minimum_persona_headroom_bytes": min(
                row["headroom_bytes"] for row in ledgers
            ),
            "origin_manifest_count": len(origin_manifests),
            "persona_count": len(envelope.PERSONA_IDS),
            "profile_manifest_count": len(profile_manifests),
        }
    )
    return result


def _prevalidate_target_suite(
    suite,
    *,
    origin_manifests,
    profile_manifests,
    origin_by_key,
    profile_by_key,
    origin_bytes_by_key,
    profile_bytes_by_key,
    overlay_contract_value,
    reservation_suite,
    semantic_catalog,
    semantic_suite,
    source_suite,
):
    _validate_target_common(
        suite,
        fields=SUITE_TOP_LEVEL_FIELDS,
        kind=SUITE_ARTIFACT_KIND,
        schema=SUITE_ARTIFACT_SCHEMA,
        label="concrete overlay membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        canonical_limits=SUITE_CANONICAL_LIMITS,
        completion_claims=SUITE_COMPLETION_CLAIMS,
        completion_scope=SUITE_COMPLETION_SCOPE,
        dependency_contract=SUITE_DEPENDENCY_CONTRACT,
    )
    _require_exact_value(suite.get("orders"), SUITE_ORDERS, label="suite orders")
    _require_exact_value(
        suite.get("persona_current_component_byte_ledger_contract"),
        PERSONA_COMPONENT_LEDGER_CONTRACT,
        label="persona component ledger contract",
    )
    expected_inputs = [
        _artifact_binding(
            "persona-v2-overlay-contract",
            "overlay-semantics-schema-and-target-marginals",
            overlay_contract_value,
            label="overlay contract",
            max_bytes=overlay_contract.MAX_OVERLAY_CONTRACT_BYTES,
        ),
        _artifact_binding(
            "persona-v2-overlay-reservation-suite",
            "global-overlay-reservation-index",
            reservation_suite,
            label="overlay reservation suite",
            max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
        ),
        _artifact_binding(
            "persona-v2-source-inventory-suite",
            "global-immutable-source-inventory",
            source_suite,
            label="source inventory suite",
            max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-catalog",
            "semantic-profile-topic-and-fact-profile-owner",
            semantic_catalog,
            label="source semantic catalog",
            max_bytes=semantic_validator.MAX_CATALOG_BYTES,
        ),
        _artifact_binding(
            "persona-v2-source-semantic-membership-suite",
            "global-source-owned-semantic-and-fact-membership",
            semantic_suite,
            label="source semantic suite",
            max_bytes=semantic_validator.MAX_SUITE_DESCRIPTOR_BYTES,
        ),
    ]
    _validate_input_bindings(suite, expected_inputs, label="concrete overlay suite")

    expected_origin_bindings = [
        _artifact_binding(
            "persona-v2-concrete-overlay-membership-origin-manifest",
            "concrete-overlay-origin-owner",
            manifest,
            label="concrete overlay origin manifest",
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
            coordinate_fields=("persona_id", "origin"),
        )
        for manifest in origin_manifests
    ]
    expected_profile_bindings = [
        _artifact_binding(
            "persona-v2-concrete-overlay-membership-profile-manifest",
            "concrete-overlay-profile-composition",
            manifest,
            label="concrete overlay profile manifest",
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
            coordinate_fields=("persona_id", "profile"),
        )
        for manifest in profile_manifests
    ]
    _require_exact_value(
        suite.get("origin_manifest_bindings"),
        expected_origin_bindings,
        label="suite origin manifest bindings",
    )
    _require_exact_value(
        suite.get("profile_manifest_bindings"),
        expected_profile_bindings,
        label="suite profile manifest bindings",
    )

    ledgers = _expected_persona_ledgers(
        overlay_contract_value=overlay_contract_value,
        semantic_suite=semantic_suite,
        origin_by_key=origin_by_key,
        profile_by_key=profile_by_key,
        origin_bytes_by_key=origin_bytes_by_key,
        profile_bytes_by_key=profile_bytes_by_key,
    )
    actual_ledgers = suite.get("persona_current_component_byte_ledgers")
    if type(actual_ledgers) is not list or len(actual_ledgers) != len(ledgers):
        _fail("suite persona current-component ledger coverage drifted")
    for row in actual_ledgers:
        _require_exact_fields(
            row, PERSONA_COMPONENT_LEDGER_FIELDS, label="persona component ledger"
        )
    _require_exact_value(actual_ledgers, ledgers, label="persona component ledgers")
    expected_summary = _suite_summary_from_metadata(
        origin_manifests,
        profile_manifests,
        ledgers,
        origin_bytes_by_key=origin_bytes_by_key,
        profile_bytes_by_key=profile_bytes_by_key,
    )
    _require_exact_fields(
        suite.get("summary"), SUITE_SUMMARY_FIELDS, label="suite summary"
    )
    _require_exact_value(suite.get("summary"), expected_summary, label="suite summary")

    # Cross-bind both upstream package roots to the exact caller-supplied
    # reservation/source/catalog objects before any body provider may run.
    source_reservation_binding = _artifact_binding(
        "persona-v2-overlay-reservation-suite",
        "overlay-source-reference-reservations",
        reservation_suite,
        label="source-suite-bound reservation suite",
        max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
    )
    semantic_reservation_binding = _artifact_binding(
        "persona-v2-overlay-reservation-suite",
        "global-overlay-reservation-index",
        reservation_suite,
        label="semantic-suite-bound reservation suite",
        max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
    )
    semantic_source_binding = _artifact_binding(
        "persona-v2-source-inventory-suite",
        "global-immutable-source-inventory",
        source_suite,
        label="semantic-suite-bound source suite",
        max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    semantic_catalog_binding = _artifact_binding(
        "persona-v2-source-semantic-membership-catalog",
        "semantic-profile-topic-and-fact-profile-owner",
        semantic_catalog,
        label="semantic-suite-bound catalog",
        max_bytes=semantic_validator.MAX_CATALOG_BYTES,
    )
    if not _contains_exact_binding(
        source_suite.get("input_bindings"), source_reservation_binding
    ):
        _fail("source suite does not bind the caller-supplied reservation suite")
    if not _contains_exact_binding(
        semantic_suite.get("input_bindings"), semantic_reservation_binding
    ) or not _contains_exact_binding(
        semantic_suite.get("input_bindings"), semantic_source_binding
    ):
        _fail("semantic suite does not bind caller-supplied source/reservation suites")
    _require_exact_value(
        semantic_suite.get("catalog_binding"),
        semantic_catalog_binding,
        label="semantic suite catalog binding",
    )

    raw = _canonical_bytes(
        suite,
        label="concrete overlay membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    if EXPECTED_SUITE_DESCRIPTOR_BYTES is None or EXPECTED_SUITE_SHA256 is None:
        _fail("concrete overlay suite frozen pin is not configured")
    if len(raw) != EXPECTED_SUITE_DESCRIPTOR_BYTES or _sha256(raw) != EXPECTED_SUITE_SHA256:
        _fail("concrete overlay suite differs from its frozen bytes/SHA pin")
    return expected_summary


def _prevalidate_all_metadata(
    suite,
    origin_manifests,
    profile_manifests,
    *,
    overlay_contract_value,
    reservation_suite,
    reservation_origin_artifacts,
    semantic_catalog,
    semantic_suite,
    semantic_origin_manifests,
    semantic_profile_manifests,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
):
    upstream = _prevalidate_upstream_metadata(
        overlay_contract_value=overlay_contract_value,
        reservation_suite=reservation_suite,
        reservation_origin_artifacts=reservation_origin_artifacts,
        semantic_catalog=semantic_catalog,
        semantic_suite=semantic_suite,
        semantic_origin_manifests=semantic_origin_manifests,
        semantic_profile_manifests=semantic_profile_manifests,
        source_suite=source_suite,
        source_origin_manifests=source_origin_manifests,
        source_profile_manifests=source_profile_manifests,
    )
    origin_by_key, origin_bytes_by_key = _prevalidate_target_origins(
        origin_manifests,
        upstream=upstream,
        overlay_contract_value=overlay_contract_value,
        semantic_catalog=semantic_catalog,
    )
    profile_by_key, profile_bytes_by_key = _prevalidate_target_profiles(
        profile_manifests,
        upstream=upstream,
        origin_by_key=origin_by_key,
        overlay_contract_value=overlay_contract_value,
        reservation_suite=reservation_suite,
        semantic_catalog=semantic_catalog,
    )
    _prevalidate_target_suite(
        suite,
        origin_manifests=origin_manifests,
        profile_manifests=profile_manifests,
        origin_by_key=origin_by_key,
        profile_by_key=profile_by_key,
        origin_bytes_by_key=origin_bytes_by_key,
        profile_bytes_by_key=profile_bytes_by_key,
        overlay_contract_value=overlay_contract_value,
        reservation_suite=reservation_suite,
        semantic_catalog=semantic_catalog,
        semantic_suite=semantic_suite,
        source_suite=source_suite,
    )
    fact_by_id, semantic_by_source = _profile_rows_by_id(semantic_catalog)
    return {
        "fact_by_id": fact_by_id,
        "origin_by_key": origin_by_key,
        "profile_by_key": profile_by_key,
        "semantic_by_source": semantic_by_source,
        **upstream,
    }


def _aggregate_and_require_body_metrics(
    metrics_by_key,
    *,
    suite,
    origin_by_key,
    reservation_by_key,
    overlay_contract_value,
):
    if set(metrics_by_key) != set(origin_by_key):
        _fail("body metrics do not cover exact target origin coordinates")
    additive_fields = set(ORIGIN_SUMMARY_FIELDS) - {
        "maximum_row_bytes_including_lf"
    }
    totals = {field: 0 for field in additive_fields}
    actual_joint = {
        relation: {placement: 0 for placement in PLACEMENT_ORDER}
        for relation in RELATION_ORDER
    }
    expected_joint = {
        relation: {placement: 0 for placement in PLACEMENT_ORDER}
        for relation in RELATION_ORDER
    }
    maximum_row = 0
    for coordinate in metrics_by_key:
        metrics = metrics_by_key[coordinate]
        manifest_summary = origin_by_key[coordinate]["summary"]
        body_summary = {
            key: value
            for key, value in metrics.items()
            if key != "relation_placement_joint_marginals"
        }
        _require_exact_value(
            body_summary,
            manifest_summary,
            label="body-derived origin summary",
        )
        for field in additive_fields:
            totals[field] += metrics[field]
        maximum_row = max(maximum_row, metrics["maximum_row_bytes_including_lf"])
        reservation_joint = reservation_by_key[coordinate][
            "relation_placement_joint_marginals"
        ]
        for relation in RELATION_ORDER:
            for placement in PLACEMENT_ORDER:
                actual_joint[relation][placement] += metrics[
                    "relation_placement_joint_marginals"
                ][relation][placement]
                expected_joint[relation][placement] += reservation_joint[relation][
                    placement
                ]
    if not _exact_value_equal(actual_joint, expected_joint):
        _fail("suite body-derived relation/placement matrix differs from reservations")

    exact_totals = {
        "attachment_exact_overlap_row_count": 1_390,
        "attachment_host_count": 2_800,
        "attachment_membership_row_count": EXPECTED_ATTACHMENT_ROW_COUNT,
        "conflict_copy_row_count": EXPECTED_CONFLICT_ROW_COUNT,
        "content_relation_row_count": EXPECTED_CONTENT_RELATION_ROW_COUNT,
        "exact_duplicate_row_count": 5_080,
        "joined_source_reference_occurrence_count": 53_220,
        "near_revision_row_count": 13_230,
        "overlay_membership_row_count": EXPECTED_OVERLAY_MEMBERSHIP_ROW_COUNT,
        "overlay_source_reference_occurrence_count": 51_120,
        "rich_row_count": EXPECTED_RICH_ROW_COUNT,
        "semantic_anchor_membership_row_count": EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT,
        "shard_count": EXPECTED_ORIGIN_COUNT,
        "unique_joined_source_count": EXPECTED_UNIQUE_JOINED_SOURCE_COUNT,
        "unique_overlay_source_count": EXPECTED_UNIQUE_OVERLAY_REFERENCE_COUNT,
    }
    for key, expected in exact_totals.items():
        if type(totals.get(key)) is not int or totals[key] != expected:
            _fail(f"suite body-derived exact total drifted: {key}")
    if len(envelope.PERSONA_IDS) != 20 or len(metrics_by_key) != EXPECTED_ORIGIN_COUNT:
        _fail("suite body-derived persona/origin coverage drifted")
    if suite["summary"]["maximum_row_bytes_including_lf"] != maximum_row:
        _fail("suite body-derived maximum row bytes drifted")

    suite_targets = overlay_contract_value.get("suite_target_marginals")
    full_target = suite_targets.get("full") if type(suite_targets) is dict else None
    if type(full_target) is not dict:
        _fail("overlay contract full suite target marginal is absent")
    body_placement = {
        placement: sum(
            actual_joint[relation][placement] for relation in RELATION_ORDER
        )
        for placement in PLACEMENT_ORDER
    }
    expected_target_projection = {
        "attachment_exact_duplicate_overlap_count": totals[
            "attachment_exact_overlap_row_count"
        ],
        "attachment_membership_count": totals["attachment_membership_row_count"],
        "conflict_copy_cluster_count": totals["conflict_copy_row_count"],
        "content_relation_cluster_count": totals["content_relation_row_count"],
        "content_relation_endpoint_reference_count": (
            2 * totals["content_relation_row_count"]
        ),
        "exact_duplicate_cluster_count": totals["exact_duplicate_row_count"],
        "membership_row_count": totals["overlay_membership_row_count"],
        "near_revision_cluster_count": totals["near_revision_row_count"],
        "placement_demand_by_scope_class": body_placement,
    }
    _require_exact_value(
        expected_target_projection,
        full_target,
        label="body-derived full overlay target marginal",
    )


def _clear_working_caches():
    clear_all = getattr(
        semantic_validator, "_clear_upstream_working_caches", None
    )
    if callable(clear_all):
        try:
            clear_all()
        except Exception:
            pass
    for name in (
        "_expected_conflict_inputs",
        "_expected_fact_graph_binding",
        "_pilot_host_count",
        "_source_domain",
        "_upstream_inputs",
    ):
        clear = getattr(getattr(reservation_validator, name, None), "cache_clear", None)
        if callable(clear):
            try:
                clear()
            except Exception:
                pass
    validated = getattr(reservation_validator, "_VALIDATED_ORIGIN_DIGESTS", None)
    if type(validated) is set:
        try:
            validated.clear()
        except Exception:
            pass


def _validate_concrete_overlay_membership_package_snapshot(
    suite,
    origin_manifests,
    profile_manifests,
    membership_body_provider,
    *,
    overlay_contract_value,
    reservation_suite,
    reservation_origin_artifacts,
    semantic_catalog,
    semantic_suite,
    semantic_origin_manifests,
    semantic_profile_manifests,
    semantic_compact_origin_body_provider,
    semantic_expanded_context_body_provider,
    semantic_expanded_membership_body_provider,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
    source_shard_body_provider,
):
    """Validate the complete pre-solve concrete overlay package independently."""

    provider_wrappers = []
    try:
        metadata = _prevalidate_all_metadata(
            suite,
            origin_manifests,
            profile_manifests,
            overlay_contract_value=overlay_contract_value,
            reservation_suite=reservation_suite,
            reservation_origin_artifacts=reservation_origin_artifacts,
            semantic_catalog=semantic_catalog,
            semantic_suite=semantic_suite,
            semantic_origin_manifests=semantic_origin_manifests,
            semantic_profile_manifests=semantic_profile_manifests,
            source_suite=source_suite,
            source_origin_manifests=source_origin_manifests,
            source_profile_manifests=source_profile_manifests,
        )

        # Provider wrappers are created only after every target/upstream
        # metadata edge and the frozen suite pin have passed.
        target_provider = _DigestRecordingProvider(
            membership_body_provider, "concrete overlay membership body"
        )
        compact_provider = _DigestRecordingProvider(
            semantic_compact_origin_body_provider,
            "semantic compact origin body",
        )
        context_provider = _DigestRecordingProvider(
            semantic_expanded_context_body_provider,
            "semantic expanded context body",
        )
        semantic_membership_provider = _DigestRecordingProvider(
            semantic_expanded_membership_body_provider,
            "semantic expanded fact-membership body",
        )
        source_provider = _DigestRecordingProvider(
            source_shard_body_provider, "structural source shard body"
        )
        provider_wrappers.extend(
            (
                target_provider,
                compact_provider,
                context_provider,
                semantic_membership_provider,
                source_provider,
            )
        )

        # This is the one and only semantic-package public validation call.  It
        # also validates the complete structural source package.
        try:
            semantic_validator.validate_source_semantic_membership_package(
                semantic_catalog,
                semantic_suite,
                semantic_origin_manifests,
                semantic_profile_manifests,
                compact_provider,
                context_provider,
                semantic_membership_provider,
                source_suite=source_suite,
                source_origin_manifests=source_origin_manifests,
                source_profile_manifests=source_profile_manifests,
                source_shard_body_provider=source_provider,
            )
        except semantic_validator.PersonaV2SourceSemanticMembershipPackageValidationError as error:
            _fail(str(error))

        metrics_by_key = {}
        for coordinate in metadata["expected_origins"]:
            persona_id, origin = coordinate
            replayed_compact = compact_provider.replay(persona_id, origin)
            del replayed_compact
            metrics_by_key[coordinate] = _validate_one_origin_body(
                metadata["origin_by_key"][coordinate],
                metadata["reservation_by_key"][coordinate],
                metadata["source_origin_by_key"][coordinate],
                target_provider=target_provider,
                source_provider=source_provider,
                context_provider=context_provider,
                membership_provider=semantic_membership_provider,
                fact_by_id=metadata["fact_by_id"],
                semantic_by_source=metadata["semantic_by_source"],
            )
        _aggregate_and_require_body_metrics(
            metrics_by_key,
            suite=suite,
            origin_by_key=metadata["origin_by_key"],
            reservation_by_key=metadata["reservation_by_key"],
            overlay_contract_value=overlay_contract_value,
        )
        return True
    except PersonaV2ConcreteOverlayMembershipPackageValidationError:
        raise
    except Exception as error:
        raise PersonaV2ConcreteOverlayMembershipPackageValidationError(
            f"concrete overlay package validation failed: {error}"
        ) from error
    finally:
        for wrapper in provider_wrappers:
            try:
                wrapper.clear()
            except Exception:
                pass
        _clear_working_caches()
        gc.collect()


def _snapshot_artifact(value, *, label, max_bytes):
    raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    return copy.deepcopy(value), raw


def _snapshot_artifact_list(values, *, label, expected_count, max_bytes):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"{label} must be an exact {expected_count}-item list")
    snapshots = []
    raws = []
    for value in values:
        snapshot, raw = _snapshot_artifact(
            value,
            label=label,
            max_bytes=max_bytes,
        )
        snapshots.append(snapshot)
        raws.append(raw)
    return snapshots, tuple(raws)


def _reauth_artifact(value, opening_raw, *, label, max_bytes):
    try:
        current_raw = _canonical_bytes(value, label=label, max_bytes=max_bytes)
    except PersonaV2ConcreteOverlayMembershipPackageValidationError:
        _fail(f"caller-owned {label} changed during provider callback")
    if current_raw != opening_raw:
        _fail(f"caller-owned {label} changed during provider callback")


def _reauth_artifact_list(
    values, opening_raws, *, label, expected_count, max_bytes
):
    if type(values) is not list or len(values) != expected_count:
        _fail(f"caller-owned {label} changed during provider callback")
    for value, opening_raw in zip(values, opening_raws, strict=True):
        _reauth_artifact(
            value,
            opening_raw,
            label=label,
            max_bytes=max_bytes,
        )


def validate_concrete_overlay_membership_package(
    suite,
    origin_manifests,
    profile_manifests,
    membership_body_provider,
    *,
    overlay_contract_value,
    reservation_suite,
    reservation_origin_artifacts,
    semantic_catalog,
    semantic_suite,
    semantic_origin_manifests,
    semantic_profile_manifests,
    semantic_compact_origin_body_provider,
    semantic_expanded_context_body_provider,
    semantic_expanded_membership_body_provider,
    source_suite,
    source_origin_manifests,
    source_profile_manifests,
    source_shard_body_provider,
):
    """Validate detached metadata and reject provider callback TOCTOU."""

    suite_snapshot, suite_raw = _snapshot_artifact(
        suite,
        label="persona v2 concrete overlay membership suite",
        max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
    )
    origin_snapshots, origin_raws = _snapshot_artifact_list(
        origin_manifests,
        label="persona v2 concrete overlay membership origin manifest",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
    )
    profile_snapshots, profile_raws = _snapshot_artifact_list(
        profile_manifests,
        label="persona v2 concrete overlay membership profile manifest",
        expected_count=EXPECTED_PROFILE_COUNT,
        max_bytes=MAX_PROFILE_MANIFEST_BYTES,
    )
    overlay_contract_snapshot, overlay_contract_raw = _snapshot_artifact(
        overlay_contract_value,
        label="bound overlay contract",
        max_bytes=overlay_contract.MAX_OVERLAY_CONTRACT_BYTES,
    )
    reservation_suite_snapshot, reservation_suite_raw = _snapshot_artifact(
        reservation_suite,
        label="bound overlay reservation suite",
        max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
    )
    reservation_origin_snapshots, reservation_origin_raws = _snapshot_artifact_list(
        reservation_origin_artifacts,
        label="bound overlay reservation origin",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=reservation_validator.MAX_ORIGIN_ARTIFACT_BYTES,
    )
    semantic_catalog_snapshot, semantic_catalog_raw = _snapshot_artifact(
        semantic_catalog,
        label="bound source semantic membership catalog",
        max_bytes=semantic_validator.MAX_CATALOG_BYTES,
    )
    semantic_suite_snapshot, semantic_suite_raw = _snapshot_artifact(
        semantic_suite,
        label="bound source semantic membership suite",
        max_bytes=semantic_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    semantic_origin_snapshots, semantic_origin_raws = _snapshot_artifact_list(
        semantic_origin_manifests,
        label="bound source semantic membership origin manifest",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=semantic_validator.MAX_ORIGIN_MANIFEST_BYTES,
    )
    semantic_profile_snapshots, semantic_profile_raws = _snapshot_artifact_list(
        semantic_profile_manifests,
        label="bound source semantic membership profile manifest",
        expected_count=EXPECTED_PROFILE_COUNT,
        max_bytes=semantic_validator.MAX_PROFILE_MANIFEST_BYTES,
    )
    source_suite_snapshot, source_suite_raw = _snapshot_artifact(
        source_suite,
        label="bound source inventory suite",
        max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
    )
    source_origin_snapshots, source_origin_raws = _snapshot_artifact_list(
        source_origin_manifests,
        label="bound source inventory origin manifest",
        expected_count=EXPECTED_ORIGIN_COUNT,
        max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
    )
    source_profile_snapshots, source_profile_raws = _snapshot_artifact_list(
        source_profile_manifests,
        label="bound source inventory profile manifest",
        expected_count=EXPECTED_PROFILE_COUNT,
        max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
    )
    try:
        return _validate_concrete_overlay_membership_package_snapshot(
            suite_snapshot,
            origin_snapshots,
            profile_snapshots,
            membership_body_provider,
            overlay_contract_value=overlay_contract_snapshot,
            reservation_suite=reservation_suite_snapshot,
            reservation_origin_artifacts=reservation_origin_snapshots,
            semantic_catalog=semantic_catalog_snapshot,
            semantic_suite=semantic_suite_snapshot,
            semantic_origin_manifests=semantic_origin_snapshots,
            semantic_profile_manifests=semantic_profile_snapshots,
            semantic_compact_origin_body_provider=(
                semantic_compact_origin_body_provider
            ),
            semantic_expanded_context_body_provider=(
                semantic_expanded_context_body_provider
            ),
            semantic_expanded_membership_body_provider=(
                semantic_expanded_membership_body_provider
            ),
            source_suite=source_suite_snapshot,
            source_origin_manifests=source_origin_snapshots,
            source_profile_manifests=source_profile_snapshots,
            source_shard_body_provider=source_shard_body_provider,
        )
    finally:
        _reauth_artifact(
            suite,
            suite_raw,
            label="concrete overlay membership suite",
            max_bytes=MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            origin_manifests,
            origin_raws,
            label="concrete overlay membership origin manifests",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            profile_manifests,
            profile_raws,
            label="concrete overlay membership profile manifests",
            expected_count=EXPECTED_PROFILE_COUNT,
            max_bytes=MAX_PROFILE_MANIFEST_BYTES,
        )
        _reauth_artifact(
            overlay_contract_value,
            overlay_contract_raw,
            label="bound overlay contract",
            max_bytes=overlay_contract.MAX_OVERLAY_CONTRACT_BYTES,
        )
        _reauth_artifact(
            reservation_suite,
            reservation_suite_raw,
            label="bound overlay reservation suite",
            max_bytes=reservation_validator.MAX_SUITE_ARTIFACT_BYTES,
        )
        _reauth_artifact_list(
            reservation_origin_artifacts,
            reservation_origin_raws,
            label="bound overlay reservation origins",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=reservation_validator.MAX_ORIGIN_ARTIFACT_BYTES,
        )
        _reauth_artifact(
            semantic_catalog,
            semantic_catalog_raw,
            label="bound source semantic membership catalog",
            max_bytes=semantic_validator.MAX_CATALOG_BYTES,
        )
        _reauth_artifact(
            semantic_suite,
            semantic_suite_raw,
            label="bound source semantic membership suite",
            max_bytes=semantic_validator.MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            semantic_origin_manifests,
            semantic_origin_raws,
            label="bound source semantic membership origins",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=semantic_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            semantic_profile_manifests,
            semantic_profile_raws,
            label="bound source semantic membership profiles",
            expected_count=EXPECTED_PROFILE_COUNT,
            max_bytes=semantic_validator.MAX_PROFILE_MANIFEST_BYTES,
        )
        _reauth_artifact(
            source_suite,
            source_suite_raw,
            label="bound source inventory suite",
            max_bytes=source_validator.MAX_SUITE_DESCRIPTOR_BYTES,
        )
        _reauth_artifact_list(
            source_origin_manifests,
            source_origin_raws,
            label="bound source inventory origins",
            expected_count=EXPECTED_ORIGIN_COUNT,
            max_bytes=source_validator.MAX_ORIGIN_MANIFEST_BYTES,
        )
        _reauth_artifact_list(
            source_profile_manifests,
            source_profile_raws,
            label="bound source inventory profiles",
            expected_count=EXPECTED_PROFILE_COUNT,
            max_bytes=source_validator.MAX_PROFILE_MANIFEST_BYTES,
        )


__all__ = [
    "ATTACHMENT_ROW_FIELDS",
    "CONTENT_RELATION_ROW_FIELDS",
    "DRAFT_PROJECTION_RECEIPT_FIELDS",
    "EXPECTED_SUITE_DESCRIPTOR_BYTES",
    "EXPECTED_SUITE_SHA256",
    "MAX_ORIGIN_MANIFEST_BYTES",
    "MAX_PROFILE_MANIFEST_BYTES",
    "MAX_ROWS_PER_SHARD",
    "MAX_ROW_BYTES_INCLUDING_LF",
    "MAX_SHARD_BODY_BYTES",
    "MAX_SUITE_DESCRIPTOR_BYTES",
    "ORIGIN_TOP_LEVEL_FIELDS",
    "PROFILE_TOP_LEVEL_FIELDS",
    "PersonaV2ConcreteOverlayMembershipPackageValidationError",
    "SEMANTIC_ANCHOR_ROW_FIELDS",
    "SHARD_DESCRIPTOR_FIELDS",
    "SUITE_TOP_LEVEL_FIELDS",
    "validate_concrete_overlay_membership_package",
]
