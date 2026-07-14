"""Suite-level semantics and target marginals for persona-PC v2 overlays.

This sidecar closes only the *schema and authored-target* part of the realism
overlay.  It defines what exact duplicates, visible near revisions, conflict
copies, and standalone attachment copies mean; it also fixes the deterministic
integer placement-demand marginals, the complete membership schema, and a
bounded draft of the future eight-axis ledger schema.  The ledger draft still
lacks complete byte/host-metadata reconciliation and persona-local domains.

It deliberately contains no source row, intent value, cluster instance,
logical-document instance, scope assignment, planned ledger, or observed
ledger.  The artifact therefore grants no G0, solver, renderer, filesystem,
KCS, write, or history authority and makes no source-format feasibility claim.
"""

from __future__ import annotations

import copy
import hashlib

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_input_bindings as input_bindings
    from . import persona_v2_realism_profile as realism
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_input_bindings as input_bindings
    import persona_v2_realism_profile as realism
    import persona_v2_variant_catalog as variant_catalog


ARTIFACT_SCHEMA = "kcs.persona.pc-overlay-contract/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-overlay-contract"
MAX_OVERLAY_CONTRACT_BYTES = 256 * 1024

CONTENT_RELATION_ORDER = (
    "exact-duplicate",
    "near-revision",
    "conflict-copy",
)
PLACEMENT_CLASS_ORDER = (
    "primary-to-primary",
    "primary-to-secondary",
    "secondary-to-primary",
    "secondary-to-secondary",
)
TARGET_PROFILE_ORDER = ("pilot", "full-minus-pilot", "full")
LEDGER_AXIS_ORDER = (
    "physical-materialization",
    "logical-document",
    "gate-search-role-and-chunks",
    "container-member-and-attachment",
    "current-and-history-version",
    "content-relation-cluster",
    "allocated-bytes",
    "host-metadata-and-exclusion",
)

_DEPENDENCY_ROLE_BY_NAME = {
    "envelope": "core",
    "topology": "topology",
    "joint-problem": "joint",
    "joint-solver-policy": "solver",
}

_EXPECTED_SUITE_RELATION_TARGETS = {
    "pilot": {
        "attachment_exact_duplicate_overlap_count": 139,
        "attachment_membership_count": 569,
        "conflict_copy_cluster_count": 156,
        "content_relation_cluster_count": 1_987,
        "content_relation_endpoint_reference_count": 3_974,
        "exact_duplicate_cluster_count": 508,
        "membership_row_count": 2_556,
        "near_revision_cluster_count": 1_323,
    },
    "full-minus-pilot": {
        "attachment_exact_duplicate_overlap_count": 1_251,
        "attachment_membership_count": 5_121,
        "conflict_copy_cluster_count": 1_404,
        "content_relation_cluster_count": 17_883,
        "content_relation_endpoint_reference_count": 35_766,
        "exact_duplicate_cluster_count": 4_572,
        "membership_row_count": 23_004,
        "near_revision_cluster_count": 11_907,
    },
    "full": {
        "attachment_exact_duplicate_overlap_count": 1_390,
        "attachment_membership_count": 5_690,
        "conflict_copy_cluster_count": 1_560,
        "content_relation_cluster_count": 19_870,
        "content_relation_endpoint_reference_count": 39_740,
        "exact_duplicate_cluster_count": 5_080,
        "membership_row_count": 25_560,
        "near_revision_cluster_count": 13_230,
    },
}

_EXPECTED_SUITE_PLACEMENT_TARGETS = {
    "pilot": {
        "primary-to-primary": 868,
        "primary-to-secondary": 628,
        "secondary-to-primary": 309,
        "secondary-to-secondary": 182,
    },
    "full-minus-pilot": {
        "primary-to-primary": 7_800,
        "primary-to-secondary": 5_660,
        "secondary-to-primary": 2_786,
        "secondary-to-secondary": 1_637,
    },
    "full": {
        "primary-to-primary": 8_668,
        "primary-to-secondary": 6_288,
        "secondary-to-primary": 3_095,
        "secondary-to-secondary": 1_819,
    },
}


class PersonaV2OverlayContractError(ValueError):
    """Raised when the overlay semantics or target marginals drift."""


def _require_negative_authority(value, *, label):
    authority = value.get("authority") if type(value) is dict else None
    if type(authority) is not dict or not authority:
        raise PersonaV2OverlayContractError(
            f"{label} must contain a non-empty authority object"
        )
    for key, flag in authority.items():
        if type(key) is not str or type(flag) is not bool or flag is not False:
            raise PersonaV2OverlayContractError(
                f"{label} authority must contain exact false booleans"
            )


def _sidecar_binding(name, dependency_role, value, *, validate, canonical, digest):
    validate(value)
    _require_negative_authority(value, label=name)
    if value.get("fixture_id") != envelope.FIXTURE_ID:
        raise PersonaV2OverlayContractError(f"{name} fixture identity drifted")
    if value.get("fixture_schema_version") != envelope.FIXTURE_SCHEMA_VERSION:
        raise PersonaV2OverlayContractError(f"{name} fixture schema version drifted")
    if value.get("g0_contract_frozen") is not False:
        raise PersonaV2OverlayContractError(f"{name} must remain non-G0")
    raw = canonical(value)
    actual_digest = digest(value)
    if hashlib.sha256(raw).hexdigest() != actual_digest:
        raise PersonaV2OverlayContractError(
            f"{name} digest differs from its canonical body"
        )
    return {
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "dependency_role": dependency_role,
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": name,
        "sha256": actual_digest,
    }


def _build_input_bindings():
    rows = []
    upstream = input_bindings.build_upstream_bindings()
    if [row["name"] for row in upstream] != list(input_bindings.UPSTREAM_ORDER):
        raise PersonaV2OverlayContractError("upstream dependency order drifted")
    for row in upstream:
        name = row["name"]
        if name not in _DEPENDENCY_ROLE_BY_NAME:
            raise PersonaV2OverlayContractError("unknown upstream dependency role")
        rows.append({**row, "dependency_role": _DEPENDENCY_ROLE_BY_NAME[name]})

    realism_value = realism.build_realism_profile()
    if realism_value.get("input_bindings") != upstream:
        raise PersonaV2OverlayContractError(
            "realism dependency does not bind the same core chain"
        )
    rows.append(
        _sidecar_binding(
            "realism-profile",
            "realism",
            realism_value,
            validate=realism.validate_realism_profile,
            canonical=realism.canonical_json_bytes,
            digest=realism.realism_profile_sha256,
        )
    )
    variant_value = variant_catalog.build_variant_catalog()
    if variant_value.get("input_bindings") != upstream:
        raise PersonaV2OverlayContractError(
            "variant dependency does not bind the same core chain"
        )
    if variant_value.get("source_level_feasibility_complete") is not False:
        raise PersonaV2OverlayContractError(
            "variant dependency must not imply source-level feasibility"
        )
    if variant_value.get("renderer_validator_implementation_complete") is not False:
        raise PersonaV2OverlayContractError(
            "variant dependency must not imply renderer/validator completion"
        )
    rows.append(
        _sidecar_binding(
            "variant-catalog",
            "variant",
            variant_value,
            validate=variant_catalog.validate_variant_catalog,
            canonical=variant_catalog.canonical_json_bytes,
            digest=variant_catalog.variant_catalog_sha256,
        )
    )
    if [row["dependency_role"] for row in rows] != [
        "core",
        "topology",
        "joint",
        "solver",
        "realism",
        "variant",
    ]:
        raise PersonaV2OverlayContractError("overlay dependency DAG order drifted")
    return rows


def _hamilton_apportion(total, weights_bp):
    if type(total) is not int or total < 0:
        raise PersonaV2OverlayContractError(
            "Hamilton total must be a non-negative exact integer"
        )
    if (
        type(weights_bp) is not list
        or len(weights_bp) != len(PLACEMENT_CLASS_ORDER)
        or any(type(weight) is not int or weight < 0 for weight in weights_bp)
        or sum(weights_bp) != 10_000
    ):
        raise PersonaV2OverlayContractError(
            "placement weights must be four non-negative basis points summing to 10000"
        )
    floors = [total * weight // 10_000 for weight in weights_bp]
    remaining = total - sum(floors)
    order = sorted(
        range(len(weights_bp)),
        key=lambda index: (-(total * weights_bp[index] % 10_000), index),
    )
    for index in order[:remaining]:
        floors[index] += 1
    if sum(floors) != total:
        raise PersonaV2OverlayContractError("Hamilton apportionment lost mass")
    return {
        placement_class: count
        for placement_class, count in zip(PLACEMENT_CLASS_ORDER, floors)
    }


def _subtract_counts(full, pilot, *, label):
    if type(full) is not dict or type(pilot) is not dict or set(full) != set(pilot):
        raise PersonaV2OverlayContractError(f"{label} coordinate schema drifted")
    residual = {}
    for key in full:
        if type(full[key]) is not int or type(pilot[key]) is not int:
            raise PersonaV2OverlayContractError(
                f"{label} coordinates must be exact integers"
            )
        value = full[key] - pilot[key]
        if value < 0:
            raise PersonaV2OverlayContractError(
                f"{label} full-minus-pilot coordinate became negative"
            )
        residual[key] = value
    return residual


def _relation_targets(profile_counts, overlap):
    required_keys = {
        "conflict_copy",
        "exact_duplicate",
        "near_revision",
        "relation_cluster_count",
        "required_relation_endpoint_count",
        "standalone_attachment",
    }
    if type(profile_counts) is not dict or set(profile_counts) != required_keys:
        raise PersonaV2OverlayContractError("realism relation target schema drifted")
    if type(overlap) is not int or overlap < 0:
        raise PersonaV2OverlayContractError(
            "attachment overlap must be a non-negative exact integer"
        )
    cluster_count = (
        profile_counts["exact_duplicate"]
        + profile_counts["near_revision"]
        + profile_counts["conflict_copy"]
    )
    if cluster_count != profile_counts["relation_cluster_count"]:
        raise PersonaV2OverlayContractError("content-relation cluster sum drifted")
    if profile_counts["required_relation_endpoint_count"] != 2 * cluster_count:
        raise PersonaV2OverlayContractError("binary relation endpoint count drifted")
    if overlap > min(
        profile_counts["exact_duplicate"],
        profile_counts["standalone_attachment"],
    ):
        raise PersonaV2OverlayContractError(
            "attachment/exact-duplicate overlap exceeds either target"
        )
    return {
        "attachment_exact_duplicate_overlap_count": overlap,
        "attachment_membership_count": profile_counts["standalone_attachment"],
        "conflict_copy_cluster_count": profile_counts["conflict_copy"],
        "content_relation_cluster_count": cluster_count,
        "content_relation_endpoint_reference_count": 2 * cluster_count,
        "exact_duplicate_cluster_count": profile_counts["exact_duplicate"],
        "membership_row_count": cluster_count
        + profile_counts["standalone_attachment"],
        "near_revision_cluster_count": profile_counts["near_revision"],
    }


def _build_target_marginals(realism_value):
    catalogs = realism_value.get("catalogs")
    if type(catalogs) is not dict:
        raise PersonaV2OverlayContractError("realism catalogs are absent")
    if catalogs.get("placement_class_order") != list(PLACEMENT_CLASS_ORDER):
        raise PersonaV2OverlayContractError("placement class order drifted")
    profiles = catalogs.get("placement_profiles")
    if type(profiles) is not list:
        raise PersonaV2OverlayContractError("placement profiles are absent")
    weights_by_profile = {}
    for row in profiles:
        if type(row) is not dict or set(row) != {
            "placement_profile_id",
            "weights_bp",
        }:
            raise PersonaV2OverlayContractError("placement profile schema drifted")
        profile_id = row["placement_profile_id"]
        if profile_id in weights_by_profile:
            raise PersonaV2OverlayContractError("duplicate placement profile")
        weights_by_profile[profile_id] = row["weights_bp"]

    personas = realism_value.get("personas")
    if type(personas) is not list or [row.get("persona_id") for row in personas] != list(
        envelope.PERSONA_IDS
    ):
        raise PersonaV2OverlayContractError("realism persona order drifted")

    persona_targets = []
    for row in personas:
        persona_id = row["persona_id"]
        profile_id = row["placement_profile_id"]
        if profile_id not in weights_by_profile:
            raise PersonaV2OverlayContractError("unknown placement profile")
        overlay = row.get("overlay_targets")
        if type(overlay) is not dict:
            raise PersonaV2OverlayContractError("persona overlay targets are absent")
        overlap = overlay.get("attachment_exact_duplicate_overlap")
        if type(overlap) is not dict or set(overlap) != {
            "full_count",
            "pilot_count",
        }:
            raise PersonaV2OverlayContractError("attachment overlap schema drifted")

        pilot_relations = _relation_targets(
            overlay["pilot"], overlap["pilot_count"]
        )
        full_relations = _relation_targets(overlay["full"], overlap["full_count"])
        residual_relations = _subtract_counts(
            full_relations,
            pilot_relations,
            label=f"{persona_id}/relations",
        )
        pilot_placement = _hamilton_apportion(
            pilot_relations["content_relation_cluster_count"],
            weights_by_profile[profile_id],
        )
        full_placement = _hamilton_apportion(
            full_relations["content_relation_cluster_count"],
            weights_by_profile[profile_id],
        )
        residual_placement = _subtract_counts(
            full_placement,
            pilot_placement,
            label=f"{persona_id}/placement",
        )
        targets = {
            "pilot": {
                "placement_demand_by_scope_class": pilot_placement,
                **pilot_relations,
            },
            "full-minus-pilot": {
                "placement_demand_by_scope_class": residual_placement,
                **residual_relations,
            },
            "full": {
                "placement_demand_by_scope_class": full_placement,
                **full_relations,
            },
        }
        for profile in TARGET_PROFILE_ORDER:
            if sum(targets[profile]["placement_demand_by_scope_class"].values()) != (
                targets[profile]["content_relation_cluster_count"]
            ):
                raise PersonaV2OverlayContractError(
                    f"{persona_id}/{profile} placement demand lost mass"
                )
        persona_targets.append({
            "persona_id": persona_id,
            "placement_profile_id": profile_id,
            "targets": targets,
        })

    suite_targets = {}
    for profile in TARGET_PROFILE_ORDER:
        relation_keys = tuple(_EXPECTED_SUITE_RELATION_TARGETS[profile])
        relation_totals = {
            key: sum(row["targets"][profile][key] for row in persona_targets)
            for key in relation_keys
        }
        placement_totals = {
            placement_class: sum(
                row["targets"][profile]["placement_demand_by_scope_class"][
                    placement_class
                ]
                for row in persona_targets
            )
            for placement_class in PLACEMENT_CLASS_ORDER
        }
        if relation_totals != _EXPECTED_SUITE_RELATION_TARGETS[profile]:
            raise PersonaV2OverlayContractError(
                f"{profile} suite relation target marginals drifted"
            )
        if placement_totals != _EXPECTED_SUITE_PLACEMENT_TARGETS[profile]:
            raise PersonaV2OverlayContractError(
                f"{profile} suite placement target marginals drifted"
            )
        suite_targets[profile] = {
            "placement_demand_by_scope_class": placement_totals,
            **relation_totals,
        }
    for key in _EXPECTED_SUITE_RELATION_TARGETS["full"]:
        if suite_targets["full-minus-pilot"][key] != (
            suite_targets["full"][key] - suite_targets["pilot"][key]
        ):
            raise PersonaV2OverlayContractError(
                "suite residual relation target must be coordinatewise full minus pilot"
            )
    for placement_class in PLACEMENT_CLASS_ORDER:
        if suite_targets["full-minus-pilot"]["placement_demand_by_scope_class"][
            placement_class
        ] != (
            suite_targets["full"]["placement_demand_by_scope_class"][placement_class]
            - suite_targets["pilot"]["placement_demand_by_scope_class"][
                placement_class
            ]
        ):
            raise PersonaV2OverlayContractError(
                "suite residual placement target must be coordinatewise full minus pilot"
            )
    return persona_targets, suite_targets


def _relation_semantics():
    return [
        {
            "anchor_role": "canonical-original-copy-role",
            "branch_relation": "same-branch",
            "checkpoint_history_relation": (
                "orthogonal-visible-W0-copy-not-a-KCS-history-version"
            ),
            "decoded_payload_relation": "exactly-equal",
            "derivative_role": "exact-copy-role",
            "document_revision_relation": "same-logical-revision",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "same-raw-sha256",
            "relation_kind": "exact-duplicate",
            "required_source_profile_relation": "same-source-profile-id",
            "scoring_projection": "one-distinct-logical-document",
        },
        {
            "anchor_role": "earlier-logical-revision",
            "branch_relation": "same-linear-branch",
            "checkpoint_history_relation": (
                "orthogonal-both-W0-visible-not-a-KCS-history-transition"
            ),
            "decoded_payload_relation": "different-but-semantically-near",
            "derivative_role": "later-logical-revision",
            "document_revision_relation": "distinct-strictly-ordered-revisions",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "different-raw-sha256",
            "relation_kind": "near-revision",
            "required_source_profile_relation": (
                "renderer-compatible-profile-validated-after-intent-membership"
            ),
            "scoring_projection": "one-distinct-logical-document",
        },
        {
            "anchor_role": "canonical-main-branch-copy",
            "branch_relation": "distinct-unordered-branches",
            "checkpoint_history_relation": (
                "orthogonal-both-W0-visible-not-a-KCS-history-transition"
            ),
            "decoded_payload_relation": "different-with-conflicting-typed-fact-required",
            "derivative_role": "conflicting-branch-copy",
            "document_revision_relation": "branch-distinct-no-linear-order",
            "logical_document_relation": "same-logical-document",
            "raw_identity_relation": "different-raw-sha256",
            "relation_kind": "conflict-copy",
            "required_source_profile_relation": (
                "renderer-compatible-profile-validated-after-intent-membership"
            ),
            "scoring_projection": "one-distinct-logical-document-with-branch-aware-evidence",
        },
    ]


def _attachment_contract():
    return {
        "allowed_host_variant_ids": ["eml"],
        "attachment_axis_is_orthogonal_to_content_relation_axis": True,
        "attachment_exact_duplicate_overlap_member_role": (
            "standalone-member-only-never-host"
        ),
        "attachment_membership_count_unit": (
            "one-row-equals-one-unique-standalone-member-intent"
        ),
        "decoded_embedded_payload_must_equal_standalone_payload": True,
        "embedded_member_adds_physical_file_or_contract_chunk": False,
        "embedded_member_is_a_separate_source_intent": False,
        "embedded_member_search_identity": (
            "not-a-separate-source-result-any-extracted-chunks-attributed-to-host"
        ),
        "embedded_only_evidence_may_satisfy_member_logical_document_target": False,
        "exact_duplicate_overlap_is_the_only_content_relation_overlap": True,
        "host_and_standalone_intent_must_differ": True,
        "host_gate_role": "incidental_searchable",
        "host_logical_document_is_distinct_from_member_logical_document": True,
        "host_source_result_projects_to": "host-logical-document-revision",
        "host_search_rule": "governed-by-source-gate-role",
        "inclusive_members_per_host_maximum": 5,
        "inclusive_members_per_host_minimum": 1,
        "member_ordinal_must_be_unique_and_contiguous_per_host": True,
        "nested_attachment_member_allowed": False,
        "overlap_count_unit": (
            "one-unique-standalone-member-intent-to-one-unique-exact-cluster"
        ),
        "overlap_exact_cluster_may_contain_both_attachment_members": False,
        "overlap_exact_cluster_may_contribute_more_than_one_count": False,
        "standalone_member_gate_role_allowed": [
            "contract_contributor",
            "incidental_searchable",
        ],
        "standalone_member_is_an_existing_physical_source_intent": True,
        "standalone_member_intent_may_appear_in_multiple_attachment_rows": False,
        "standalone_member_result_projects_to": "member-logical-document-revision",
        "standalone_and_embedded_member_share_logical_document_revision": True,
    }


def _membership_shard_schema():
    return {
        "artifact_schema": "kcs.persona.pc-overlay-membership-shard/v2",
        "body_encoding": {
            "bom_allowed": False,
            "canonical_json": "UTF-8-NFC-sorted-keys-compact-no-float-no-null",
            "carriage_return_allowed": False,
            "each_row_terminated_by_single_lf": True,
            "empty_or_trailing_blank_row_allowed": False,
            "shard_body_contains_rows_only": True,
        },
        "cross_row_constraints": [
            "cluster-key-unique-within-persona-and-origin",
            "attachment-key-unique-within-persona-and-origin",
            "content-relation-endpoint-intent-used-by-exactly-one-content-cluster",
            "content-relation-endpoints-are-distinct",
            "attachment-host-and-standalone-member-are-distinct",
            "attachment-host-intent-never-appears-in-a-content-relation-cluster",
            "attachment-standalone-member-intent-used-by-exactly-one-attachment-row",
            "attachment-host-plus-member-ordinal-unique",
            "attachment-member-ordinals-contiguous-one-through-host-member-count",
            "attachment-host-member-count-in-one-through-five",
            "attachment-standalone-member-is-not-eml",
            "attachment-exact-overlap-uses-standalone-member-endpoint-only",
            "attachment-exact-overlap-is-one-standalone-intent-to-one-exact-cluster",
            "attachment-exact-overlap-cluster-has-exactly-one-attachment-endpoint",
            "attachment-near-or-conflict-overlap-count-equals-zero",
            "relation-kind-counts-equal-bound-persona-origin-targets",
            "attachment-row-and-unique-standalone-member-counts-equal-bound-target",
            "attachment-exact-overlap-count-equals-bound-target",
            "placement-class-counts-equal-bound-persona-origin-targets",
            "all-referenced-intents-exist-in-bound-intent-only-manifest",
            "all-referenced-intents-share-shard-persona-and-origin",
            "no-membership-row-crosses-pilot-and-full-residual-origins",
        ],
        "deterministic_row_sort": {
            "attachment_membership_key": [
                "row-kind-ordinal-1",
                "relation-kind-sentinel-ordinal-0",
                "attachment-key-ascending-ASCII-bytes",
            ],
            "content_relation_key": [
                "row-kind-ordinal-0",
                "relation-kind-order-ordinal",
                "cluster-key-ascending-ASCII-bytes",
            ],
            "duplicate-sort-keys-allowed": False,
            "hash-ordering-allowed": False,
            "sort_key_encoding": {
                "attachment-membership": [
                    "exact-integer-1",
                    "exact-integer-0",
                    "attachment-key",
                ],
                "content-relation": [
                    "exact-integer-0",
                    "relation-kind-order-zero-based-ordinal",
                    "cluster-key",
                ],
            },
        },
        "full_manifest_composition": (
            "reuse-exact-pilot-shard-bytes-and-sha256-plus-full-residual-shards"
        ),
        "full_manifest_schema": {
            "artifact_schema": "kcs.persona.pc-overlay-membership-manifest/v2",
            "exact_fields": [
                "artifact_schema",
                "artifact_schema_version",
                "fixture_id",
                "fixture_schema_version",
                "persona_id",
                "profile",
                "overlay_contract_sha256",
                "pilot_origin_manifest_sha256",
                "full_residual_origin_manifest_sha256",
                "target_marginals",
            ],
            "max_canonical_body_bytes": 128 * 1024,
            "profile_exact_value": "full",
            "self_hash_embedded": False,
        },
        "hash_dag_order": [
            "source-profile-catalog",
            "source-intent-shards",
            "intent-only-manifest",
            "overlay-membership-shards",
            "overlay-manifest",
        ],
        "max_canonical_jsonl_row_bytes_including_lf": 768,
        "max_rows_per_shard": 4_096,
        "max_shard_body_bytes": 4 * 2**20,
        "membership_key_semantics": (
            "pre-solve-semantic-keys-only-never-final-source-or-materialization-ids"
        ),
        "membership_key_syntax": [
            {
                "field_name": "attachment_key",
                "syntax": "lowercase-ASCII-regex-^[a-z][a-z0-9-]{0,119}$",
            },
            {
                "field_name": "cluster_key",
                "syntax": "lowercase-ASCII-regex-^[a-z][a-z0-9-]{0,119}$",
            },
        ],
        "origin_order": ["pilot", "full-residual"],
        "origin_manifest_schema": {
            "artifact_schema": "kcs.persona.pc-overlay-origin-manifest/v2",
            "exact_fields": [
                "artifact_schema",
                "artifact_schema_version",
                "fixture_id",
                "fixture_schema_version",
                "persona_id",
                "origin",
                "target_profile",
                "overlay_contract_sha256",
                "source_intent_manifest_sha256",
                "target_marginals",
                "aggregate_row_count",
                "aggregate_body_bytes",
                "aggregate_shard_count",
                "shard_descriptors",
            ],
            "max_canonical_body_bytes": 128 * 1024,
            "origin_to_target_profile": {
                "full-residual": "full-minus-pilot",
                "pilot": "pilot",
            },
            "self_hash_embedded": False,
            "shard_descriptors_follow-index-order": True,
        },
        "origin_rules": {
            "full-residual": "all-referenced-intents-have-full-residual-origin",
            "pilot": "all-referenced-intents-have-pilot-origin",
        },
        "persona_local_only": True,
        "row_schemas": [
            {
                "exact_fields": [
                    "row_kind",
                    "relation_kind",
                    "cluster_key",
                    "anchor_intent_key",
                    "derivative_intent_key",
                    "placement_class",
                    "search_participation_profile_id",
                ],
                "field_constraints": [
                    "row-kind-equals-content-relation",
                    "relation-kind-in-content-relation-order",
                    "anchor-and-derivative-intent-keys-differ",
                    "both-endpoints-have-shard-origin-and-persona",
                    "both-endpoints-have-searchable-gate-role",
                    "both-endpoints-resolve-to-different-scope-keys-after-solve",
                    "placement-class-matches-anchor-then-derivative-scope-classes",
                    "search-participation-profile-id-equals-content-relation-v2",
                ],
                "row_kind": "content-relation",
            },
            {
                "exact_fields": [
                    "row_kind",
                    "attachment_key",
                    "host_intent_key",
                    "standalone_member_intent_key",
                    "member_ordinal",
                    "decoded_payload_equivalence_key",
                    "search_participation_profile_id",
                ],
                "field_constraints": [
                    "row-kind-equals-attachment-membership",
                    "host-and-standalone-intent-keys-differ",
                    "both-intents-have-shard-origin-and-persona",
                    "host-variant-equals-eml",
                    "member-ordinal-in-one-through-five",
                    "decoded-member-payload-equals-standalone-payload",
                    "standalone-member-variant-is-not-eml",
                    "search-participation-profile-id-equals-attachment-structural-v2",
                ],
                "row_kind": "attachment-membership",
            },
        ],
        "search_participation_profiles": [
            {
                "profile_id": "content-relation-v2",
                "rule": "both-endpoints-gate-searchable-score-one-logical-document",
                "row_kind": "content-relation",
            },
            {
                "profile_id": "attachment-structural-v2",
                "rule": (
                    "host-and-standalone-gate-searchable-embedded-not-source-"
                    "host-result-scores-host-document"
                ),
                "row_kind": "attachment-membership",
            },
        ],
        "shard_descriptor_schema": {
            "exact_fields": [
                "artifact_schema",
                "artifact_schema_version",
                "persona_id",
                "origin",
                "shard_index",
                "file_name",
                "first_row_sort_key",
                "last_row_sort_key",
                "row_count",
                "body_bytes",
                "body_sha256",
                "source_intent_manifest_sha256",
            ],
            "file_name_formula": "overlay-{origin}-{shard-index-zero-padded-4}.jsonl",
            "first_shard_index": 0,
            "indices_contiguous_without-gaps": True,
            "row_count_and-body-bytes-recomputed-before-hash": True,
            "sha256_domain": "exact-canonical-jsonl-body-bytes-only",
        },
        "shard_partition_rule": (
            "globally-sort-rows-then-greedily-append-consecutive-rows-until-next-row-"
            "would-exceed-4096-rows-or-4194304-body-bytes-no-empty-shards"
        ),
        "source_or_materialization_or_final_ids_allowed": False,
        "source_intent_manifest_back_reference_to_overlay_allowed": False,
        "source_intent_manifest_kind": "intent-only-no-overlay-membership",
    }


def _search_and_scoring_contract():
    return {
        "attachment_embedded_member_counts_as_physical_source": False,
        "attachment_embedded_only_evidence_target_eligible": False,
        "attachment_host_source_result_projection": "host-logical-document-revision",
        "attachment_standalone_member_search_rule": "governed-by-source-gate-role",
        "attachment_standalone_result_projection": "member-logical-document-revision",
        "content_relation_endpoint_allowed_gate_roles": [
            "contract_contributor",
            "incidental_searchable",
        ],
        "content_relation_raw_only_endpoint_allowed": False,
        "content_relation_search_rule": "both-physical-endpoints-participate",
        "contract_chunk_accounting_identity": "distinct-scope-key-plus-chunk-id",
        "default_recall_denominator_identity": "distinct-logical-document-key",
        "duplicate_or_revision_paths_may_increase_recall_denominator": False,
        "evidence_may_report_multiple_physical_materializations": True,
        "exact_duplicate_contributor_endpoints_require_different_scopes": True,
        "logical_document_assignment_occurs_before_compiled-relevance": True,
        "oracle_query_or_rank_instances_present": False,
        "planned_participation_requires_observed-attestation-later": True,
        "top_k_comparison_projection": "top-ten-distinct-logical-documents",
    }


def _ledger_profile_marginal_contract():
    checkpoint_order = list(envelope.HISTORY_CHECKPOINTS["pilot"])
    if list(envelope.HISTORY_CHECKPOINTS["full"]) != checkpoint_order:
        raise PersonaV2OverlayContractError(
            "pilot and full checkpoint catalogs must have the same exact order"
        )

    checkpoint_chunk_marginals = {}
    for target_profile in TARGET_PROFILE_ORDER:
        rows = []
        for checkpoint in checkpoint_order:
            pilot_current, pilot_history = envelope.HISTORY_CHECKPOINTS["pilot"][
                checkpoint
            ]
            full_current, full_history = envelope.HISTORY_CHECKPOINTS["full"][
                checkpoint
            ]
            if target_profile == "pilot":
                current, history = pilot_current, pilot_history
            elif target_profile == "full":
                current, history = full_current, full_history
            else:
                current = full_current - pilot_current
                history = full_history - pilot_history
            if current < 0 or history < 0:
                raise PersonaV2OverlayContractError(
                    "residual checkpoint chunk marginal became negative"
                )
            rows.append(
                {
                    "checkpoint": checkpoint,
                    "current_contract_chunks_per_persona": current,
                    "history_only_contract_chunks_per_persona": history,
                }
            )
        checkpoint_chunk_marginals[target_profile] = rows

    w0_file_rows = []
    for persona_id in envelope.PERSONA_IDS:
        pilot = envelope.profile_file_count(persona_id, "pilot")
        full = envelope.profile_file_count(persona_id, "full")
        residual = full - pilot
        if residual < 0:
            raise PersonaV2OverlayContractError(
                "residual W0 physical-file marginal became negative"
            )
        w0_file_rows.append(
            {
                "full": full,
                "full-minus-pilot": residual,
                "persona_id": persona_id,
                "pilot": pilot,
            }
        )

    return {
        "checkpoint_chunk_marginals": checkpoint_chunk_marginals,
        "checkpoint_order": checkpoint_order,
        "full_minus_pilot_rule": "coordinatewise-full-minus-pilot",
        "w0_physical_file_marginals_by_persona": w0_file_rows,
    }


def _ledger_schema(realism_value):
    checkpoint_values = list(envelope.HISTORY_CHECKPOINTS["pilot"])
    if list(envelope.HISTORY_CHECKPOINTS["full"]) != checkpoint_values:
        raise PersonaV2OverlayContractError(
            "pilot and full checkpoint catalogs must have the same exact order"
        )
    realism_catalogs = realism_value["catalogs"]
    snapshot_source_kinds = sorted(
        {
            source_kind
            for persona in realism_value["personas"]
            for source_kind in persona["synthetic_snapshot_source_kinds"]
        }
    )
    enum_domains = [
        {
            "domain_id": "origin-v2",
            "source_binding": "overlay-origin-and-profile-contract",
            "values": ["pilot", "full-residual"],
        },
        {
            "domain_id": "checkpoint-v2",
            "source_binding": "bound-envelope-history-checkpoint-order",
            "values": checkpoint_values,
        },
        {
            "domain_id": "materialization-existence-v2",
            "source_binding": "overlay-contract-local-v2",
            "values": [
                "present",
                "absent-not-yet-created",
                "absent-deleted-history-retained",
                "absent-purged",
            ],
        },
        {
            "domain_id": "logical-visibility-v2",
            "source_binding": "overlay-contract-local-v2",
            "values": ["absent", "current", "history-only", "purged"],
        },
        {
            "domain_id": "gate-role-v2",
            "source_binding": "bound-variant-catalog-gate-role",
            "values": [
                "contract_contributor",
                "incidental_searchable",
                "raw_only",
            ],
        },
        {
            "domain_id": "observed-search-disposition-v2",
            "source_binding": "overlay-contract-local-v2",
            "values": [
                "indexed-contract-contributor",
                "indexed-incidental-searchable",
                "not-indexed-raw-only",
                "not-indexed-absent",
                "not-indexed-purged",
            ],
        },
        {
            "domain_id": "attachment-member-disposition-v2",
            "source_binding": "overlay-attachment-contract",
            "values": [
                "decoded-equal-host-attributed-and-standalone-searchable"
            ],
        },
        {
            "domain_id": "content-relation-kind-v2",
            "source_binding": "overlay-content-relation-order",
            "values": list(CONTENT_RELATION_ORDER),
        },
        {
            "domain_id": "placement-class-v2",
            "source_binding": "bound-realism-placement-class-order",
            "values": list(PLACEMENT_CLASS_ORDER),
        },
        {
            "domain_id": "mtime-bucket-v2",
            "source_binding": "bound-realism-mtime-bucket-order",
            "values": list(realism_catalogs["mtime_bucket_order"]),
        },
        {
            "domain_id": "permission-mode-v2",
            "source_binding": "bound-realism-permission-mode-order",
            "values": list(realism_catalogs["permission_mode_order"]),
        },
        {
            "domain_id": "sensitivity-tier-v2",
            "source_binding": "bound-realism-sensitivity-tier-order",
            "values": list(realism_catalogs["sensitivity_tier_order"]),
        },
        {
            "domain_id": "snapshot-source-kind-v2",
            "source_binding": "bound-realism-persona-snapshot-source-kind-union",
            "values": snapshot_source_kinds,
        },
        {
            "domain_id": "exclusion-disposition-v2",
            "source_binding": "overlay-contract-local-v2",
            "values": [
                "included",
                "excluded-by-path-policy",
                "excluded-by-permission-policy",
                "excluded-by-sensitivity-policy",
                "excluded-by-unsupported-source",
            ],
        },
        {
            "domain_id": "path-case-state-v2",
            "source_binding": "overlay-contract-local-v2",
            "values": [
                "exact-case-match",
                "case-fold-equivalent",
                "portable-case-unspecified",
                "collision-rejected",
            ],
        },
    ]
    enum_field_domain_ids = {
        "checkpoint": "checkpoint-v2",
        "existence_state": "materialization-existence-v2",
        "gate_role": "gate-role-v2",
        "mtime_bucket": "mtime-bucket-v2",
        "observed_exclusion_disposition": "exclusion-disposition-v2",
        "observed_member_disposition": "attachment-member-disposition-v2",
        "observed_mtime_bucket": "mtime-bucket-v2",
        "observed_path_case_state": "path-case-state-v2",
        "observed_permission_mode": "permission-mode-v2",
        "observed_search_disposition": "observed-search-disposition-v2",
        "observed_version_state": "logical-visibility-v2",
        "observed_visibility_state": "logical-visibility-v2",
        "origin": "origin-v2",
        "permission_mode": "permission-mode-v2",
        "placement_class": "placement-class-v2",
        "planned_exclusion_disposition": "exclusion-disposition-v2",
        "planned_materialization_state": "materialization-existence-v2",
        "planned_version_state": "logical-visibility-v2",
        "planned_visibility_state": "logical-visibility-v2",
        "relation_kind": "content-relation-kind-v2",
        "sensitivity_tier": "sensitivity-tier-v2",
        "snapshot_source_kind": "snapshot-source-kind-v2",
    }
    if len({row["domain_id"] for row in enum_domains}) != len(enum_domains):
        raise PersonaV2OverlayContractError("ledger enum domain IDs must be unique")
    if not set(enum_field_domain_ids.values()).issubset(
        {row["domain_id"] for row in enum_domains}
    ):
        raise PersonaV2OverlayContractError("ledger enum field references unknown domain")
    axis_rows = [
        {
            "axis_id": "physical-materialization",
            "cardinality_unit": "one-source-intent-materialization-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "intent_key",
                "checkpoint",
            ],
            "observed_fields": [
                "final_source_id",
                "materialization_id",
                "relative_path",
                "raw_sha256",
                "existence_state",
            ],
            "planned_fields": [
                "source_profile_id",
                "solved_scope_key",
                "cell_local_ordinal",
                "planned_materialization_state",
            ],
        },
        {
            "axis_id": "logical-document",
            "cardinality_unit": "one-logical-document-revision-branch-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "logical_document_key",
                "logical_revision_key",
                "branch_key",
                "checkpoint",
            ],
            "observed_fields": ["materialization_ids", "observed_visibility_state"],
            "planned_fields": ["intent_keys", "planned_visibility_state"],
        },
        {
            "axis_id": "gate-search-role-and-chunks",
            "cardinality_unit": "one-source-intent-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "intent_key",
                "checkpoint",
            ],
            "observed_fields": [
                "actual_current_chunks",
                "actual_history_only_chunks",
                "actual_deleted_chunks",
                "observed_search_disposition",
            ],
            "planned_fields": [
                "gate_role",
                "requested_contract_chunks",
                "expected_incidental_chunks_upper",
            ],
        },
        {
            "axis_id": "container-member-and-attachment",
            "cardinality_unit": "one-unique-host-plus-member-ordinal",
            "checkpoint_domain": "W0-overlay-static-only",
            "identity_fields": [
                "persona_id",
                "origin",
                "host_intent_key",
                "member_ordinal",
            ],
            "observed_fields": [
                "observed_host_source_id",
                "observed_decoded_member_sha256",
                "observed_member_disposition",
            ],
            "planned_fields": [
                "standalone_member_intent_key",
                "decoded_payload_equivalence_key",
            ],
        },
        {
            "axis_id": "current-and-history-version",
            "cardinality_unit": "one-logical-revision-branch-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "logical_document_key",
                "logical_revision_key",
                "branch_key",
                "checkpoint",
            ],
            "observed_fields": ["observed_version_state", "observed_commit_id"],
            "planned_fields": ["planned_version_state", "history_event_key"],
        },
        {
            "axis_id": "content-relation-cluster",
            "cardinality_unit": "one-binary-content-relation-cluster",
            "checkpoint_domain": "W0-overlay-static-only",
            "identity_fields": ["persona_id", "origin", "cluster_key"],
            "observed_fields": [
                "observed_anchor_source_id",
                "observed_derivative_source_id",
                "observed_raw_identity_relation",
            ],
            "planned_fields": [
                "relation_kind",
                "anchor_intent_key",
                "derivative_intent_key",
                "placement_class",
            ],
        },
        {
            "axis_id": "allocated-bytes",
            "cardinality_unit": "one-source-intent-materialization-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "intent_key",
                "checkpoint",
            ],
            "observed_fields": [
                "observed_raw_bytes",
                "observed_expanded_bytes",
                "observed_normalized_bytes",
                "observed_st_blocks_bytes",
            ],
            "planned_fields": [
                "target_raw_bytes",
                "expanded_bytes_cap",
                "renderer_absolute_bytes_cap",
            ],
        },
        {
            "axis_id": "host-metadata-and-exclusion",
            "cardinality_unit": "one-source-intent-materialization-at-one-checkpoint",
            "checkpoint_domain": "all-envelope-checkpoints-for-bound-profile",
            "identity_fields": [
                "persona_id",
                "origin",
                "intent_key",
                "checkpoint",
            ],
            "observed_fields": [
                "observed_mtime_bucket",
                "observed_permission_mode",
                "observed_exclusion_disposition",
                "observed_path_case_state",
            ],
            "planned_fields": [
                "mtime_bucket",
                "permission_mode",
                "sensitivity_tier",
                "snapshot_source_kind",
                "planned_exclusion_disposition",
            ],
        },
    ]
    if [row["axis_id"] for row in axis_rows] != list(LEDGER_AXIS_ORDER):
        raise PersonaV2OverlayContractError("eight-axis ledger order drifted")
    for row in axis_rows:
        row["planned_exact_fields"] = [
            "axis_id",
            *row["identity_fields"],
            *row["planned_fields"],
        ]
        row["observed_exact_fields"] = [
            "axis_id",
            *row["identity_fields"],
            *row["observed_fields"],
            "attestation_evidence_sha256",
        ]
    return {
        "axis_order": list(LEDGER_AXIS_ORDER),
        "axes": axis_rows,
        "body_encoding": {
            "canonical_json": "UTF-8-NFC-sorted-keys-compact-no-float-no-null",
            "each_row_terminated_by_single_lf": True,
            "empty-bom-carriage-return-or-blank-row-allowed": False,
        },
        "canonical_row_order": (
            "axis-order-ordinal-then-axis-identity-fields-in-declared-order-"
            "strings-by-UTF8-bytes-integers-numerically-no-hash-order"
        ),
        "profile_marginal_contract": _ledger_profile_marginal_contract(),
        "cross_axis_reconciliation_rules": [
            "W0-physical-materialization-count-reconciles-to-exact-target-profile-W0-file-marginals",
            "embedded-attachment-members-do-not-increase-physical-materialization-count",
            "exact-duplicate-endpoints-share-one-logical-document-and-revision",
            "near-and-conflict-endpoints-share-one-logical-document-with-distinct-revisions",
            "content-relation-and-attachment-counts-reconcile-to-persona-target-marginals",
            "contract-contributor-observed-chunks-reconcile-to-exact-target-profile-checkpoint-chunk-marginals",
            "raw-only-observed-chunks-equal-zero",
            "planned-and-observed-values-remain-separate-and-observed-requires-attestation",
            "history-state-reconciles-to-checkpoint-event-and-commit-evidence",
            "allocated-byte-ledger-never-substitutes-logical-counts-for-physical-bytes",
        ],
        "field_type_contract": {
            "catalog_bound_enum_fields": list(enum_field_domain_ids),
            "enum_domains": enum_domains,
            "enum_field_domain_ids": enum_field_domain_ids,
            "nonnegative_exact_integer_fields": [
                "cell_local_ordinal",
                "member_ordinal",
                "requested_contract_chunks",
                "expected_incidental_chunks_upper",
                "actual_current_chunks",
                "actual_history_only_chunks",
                "actual_deleted_chunks",
                "target_raw_bytes",
                "expanded_bytes_cap",
                "renderer_absolute_bytes_cap",
                "observed_raw_bytes",
                "observed_expanded_bytes",
                "observed_normalized_bytes",
                "observed_st_blocks_bytes",
            ],
            "reference_string_fields": (
                "all-fields-ending-id-or-key-and-relative-path-exact-NFC-strings-"
                "validated-by-their-bound-upstream-catalog"
            ),
            "sha256_fields": (
                "all-fields-ending-sha256-exact-64-lowercase-hex-over-declared-domain"
            ),
            "sorted_unique_string_list_fields": ["intent_keys", "materialization_ids"],
        },
        "instance_artifact_schemas": {
            "observed": "kcs.persona.pc-eight-axis-observed-ledger/v2",
            "planned": "kcs.persona.pc-eight-axis-planned-ledger/v2",
        },
        "hash_back_reference_rules": [
            "all-hash-edges-follow-hash-dag-order-only",
            "source-intent-origin-manifests-must-not-bind-planned-or-observed-ledger-sha256",
            "history-intent-manifest-must-not-bind-planned-or-observed-ledger-sha256",
            "overlay-membership-manifest-allocation-solution-and-final-source-plan-must-not-bind-planned-or-observed-ledger-sha256",
            "planned-eight-axis-ledger-must-not-bind-observed-eight-axis-ledger-sha256",
            "execution-receipts-and-root-attestation-may-bind-planned-but-must-not-bind-observed-ledger-sha256",
            "observed-eight-axis-ledger-is-terminal-and-no-earlier-node-may-bind-its-sha256",
        ],
        "hash_dag_order": [
            "source-intent-origin-manifests",
            "history-intent-manifest",
            "overlay-membership-manifest",
            "canonical-allocation-solution",
            "final-source-plan",
            "planned-eight-axis-ledger",
            "filesystem-and-KCS-history-execution",
            "root-attestation-and-history-execution-receipt",
            "observed-eight-axis-ledger",
        ],
        "hash_dag_required_edges": [
            "overlay-membership-origin-manifests-bind-source-intent-origin-manifest-sha256",
            "canonical-allocation-solution-binds-overlay-membership-manifest-sha256",
            "final-source-plan-binds-canonical-allocation-solution-sha256",
            "planned-eight-axis-ledger-binds-overlay-membership-canonical-allocation-final-source-plan-and-history-intent-sha256s",
            "filesystem-and-KCS-history-execution-binds-planned-eight-axis-ledger-manifest-sha256",
            "root-attestation-and-history-execution-receipt-bind-planned-ledger-and-execution-evidence-sha256s",
            "observed-eight-axis-ledger-binds-planned-ledger-root-attestation-and-history-execution-receipt-sha256s",
        ],
        "manifest_schemas": {
            "observed": {
                "artifact_schema": (
                    "kcs.persona.pc-eight-axis-observed-ledger-manifest/v2"
                ),
                "exact_fields": [
                    "artifact_schema",
                    "artifact_schema_version",
                    "fixture_id",
                    "fixture_schema_version",
                    "persona_id",
                    "profile",
                    "planned_ledger_manifest_sha256",
                    "replay_id",
                    "root_attestation_sha256",
                    "history_execution_receipt_sha256",
                    "axis_row_counts",
                    "shard_descriptors",
                ],
            },
            "planned": {
                "artifact_schema": (
                    "kcs.persona.pc-eight-axis-planned-ledger-manifest/v2"
                ),
                "exact_fields": [
                    "artifact_schema",
                    "artifact_schema_version",
                    "fixture_id",
                    "fixture_schema_version",
                    "persona_id",
                    "profile",
                    "overlay_membership_manifest_sha256",
                    "canonical_allocation_solution_sha256",
                    "final_source_plan_sha256",
                    "history_intent_manifest_sha256",
                    "axis_row_counts",
                    "shard_descriptors",
                ],
            },
        },
        "max_canonical_jsonl_row_bytes_including_lf": 2_048,
        "max_manifest_body_bytes": 128 * 1024,
        "max_rows_per_shard": 4_096,
        "max_shard_body_bytes": 4 * 2**20,
        "manifest_axis_row_counts_use_exact-axis-order-and-recomputed-totals": True,
        "manifest_self_hash_embedded": False,
        "manifest_shard_descriptors_follow-index-order": True,
        "null_values_allowed": False,
        "observed_evidence_required": True,
        "phase_separation": (
            "planned-and-observed-use-different-artifact-schemas-and-shards-no-mixed-phase"
        ),
        "planned_and_observed_rows_are_distinct": True,
        "profile_values": list(TARGET_PROFILE_ORDER),
        "row_identity_unique_within-persona-profile-phase-and-axis": True,
        "shard_descriptor_schema": {
            "exact_fields": [
                "phase",
                "shard_index",
                "file_name",
                "first_row_sort_key",
                "last_row_sort_key",
                "row_count",
                "body_bytes",
                "body_sha256",
            ],
            "file_name_formula": (
                "{phase}-eight-axis-ledger-{shard-index-zero-padded-4}.jsonl"
            ),
            "indices_contiguous_from_zero": True,
            "phase_values": ["planned", "observed"],
            "row-count-body-bytes-and-sha256-recomputed": True,
        },
        "shard_partition_rule": (
            "globally-sort-phase-rows-then-greedily-partition-consecutive-rows-at-"
            "4096-rows-or-4194304-body-bytes-no-empty-shards"
        ),
    }


def _canonical_overlay_contract_value():
    realism_value = realism.build_realism_profile()
    realism.validate_realism_profile(realism_value)
    persona_targets, suite_targets = _build_target_marginals(realism_value)
    relation_semantics = _relation_semantics()
    if [row["relation_kind"] for row in relation_semantics] != list(
        CONTENT_RELATION_ORDER
    ):
        raise PersonaV2OverlayContractError("content relation order drifted")
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "attachment_contract": _attachment_contract(),
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_membership_publication": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kcs_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
            "source_feasibility_proved": False,
            "validator_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_OVERLAY_CONTRACT_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_or_float_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "attachment_semantics_complete": True,
            "conflict_fact_realizability_proved": False,
            "content_relation_semantics_complete": True,
            "eight_axis_ledger_schema_complete": False,
            "logical_document_instance_assignment_complete": False,
            "logical_document_scoring_semantics_complete": True,
            "membership_shard_schema_complete": True,
            "observed_eight_axis_ledger_instances_present": False,
            "overlay_integer_target_marginals_complete": True,
            "overlay_membership_instances_present": False,
            "placement_demand_marginals_complete": True,
            "placement_scope_assignment_complete": False,
            "planned_eight_axis_ledger_instances_present": False,
            "search_participation_semantics_complete": True,
            "source_format_feasibility_complete": False,
        },
        "completion_scope": (
            "suite-overlay-semantics-membership-schema-ledger-axis-draft-and-exact-integer-"
            "target-marginals-only-no-instances-no-scope-assignment-no-feasibility-no-g0"
        ),
        "content_relation_global_contract": {
            "anchor_reuse_across_clusters_allowed": False,
            "cluster_cardinality_physical_materializations": 2,
            "cluster_endpoints_are_distinct_intents": True,
            "cluster_endpoints_are_distinct_physical_materializations": True,
            "clusters_are_physical-member-disjoint": True,
            "exact_near_conflict_membership_is_mutually_exclusive": True,
            "overlay_may_change_contract_chunk_target": False,
            "overlay_may_change_family_or_variant_marginals": False,
            "overlay_may_change_physical_file_marginals": False,
        },
        "content_relation_order": list(CONTENT_RELATION_ORDER),
        "content_relation_semantics": relation_semantics,
        "eight_axis_ledger_schema": _ledger_schema(realism_value),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": (
            "authored-benchmark-stress-semantics-and-targets-not-observed-user-statistics"
        ),
        "input_bindings": _build_input_bindings(),
        "membership_shard_schema": _membership_shard_schema(),
        "origin_and_profile_contract": {
            "full_manifest_origin_composition": ["pilot", "full-residual"],
            "full_minus_pilot_profile_maps_to_origin": "full-residual",
            "origin_values": ["pilot", "full-residual"],
            "pilot_membership_bytes_and_sha256_reused_unchanged_in_full": True,
            "pilot_profile_maps_to_origin": "pilot",
            "residual_is_coordinatewise_full_minus_pilot": True,
            "residual_membership_may_reference_pilot_intent": False,
        },
        "persona_target_marginals": persona_targets,
        "placement_contract": {
            "anchor_then_derivative_orientation": True,
            "apportionment_method": (
                "per-persona-Hamilton-largest-remainder-descending-fraction-"
                "then-placement-class-order"
            ),
            "classes_count_content_relation-clusters-not-endpoints": True,
            "content_relation_endpoints_must_resolve_to_different_scopes": True,
            "full_minus_pilot_is_subtraction_not-independent-apportionment": True,
            "placement_class_order": list(PLACEMENT_CLASS_ORDER),
            "primary_secondary_classification_bound_by_topology": True,
        },
        "remaining_blockers": [
            "source-intent-profile-and-recipe-not-bound",
            "overlay-membership-shards-not-instantiated",
            "overlay-membership-runtime-validator-not-implemented",
            "scope-and-placement-membership-not-assigned",
            "logical-document-and-revision-keys-not-instantiated",
            "conflict-branch-fact-membership-not-bound",
            "current-fact-graph-has-no-w0-current-unordered-conflict-pairs",
            "planned-eight-axis-ledgers-not-instantiated",
            "observed-eight-axis-ledgers-not-attested",
            "eight-axis-ledger-cross-axis-and-persona-domain-schema-incomplete",
            "eight-axis-ledger-runtime-validator-not-implemented",
            "renderer-and-standalone-validator-feasibility-not-proved",
            "bounded-framed-external-loader-not-implemented",
            "independent-overlay-review-receipt-not-bound",
        ],
        "search_and_scoring_contract": _search_and_scoring_contract(),
        "suite_target_marginals": suite_targets,
        "target_count_unit_contract": {
            "attachment_exact_duplicate_overlap_count": (
                "unique-standalone-member-intents-each-paired-one-to-one-with-a-"
                "different-exact-duplicate-cluster"
            ),
            "attachment_membership_count": (
                "attachment-rows-equals-unique-standalone-member-intents"
            ),
            "content_relation_cluster_count": (
                "unique-binary-physical-member-disjoint-clusters"
            ),
            "content_relation_endpoint_reference_count": (
                "two-endpoint-references-per-content-relation-cluster"
            ),
            "membership_row_count": (
                "content-relation-cluster-rows-plus-attachment-membership-rows"
            ),
            "placement_demand_by_scope_class": (
                "content-relation-clusters-oriented-anchor-then-derivative"
            ),
        },
        "target_profile_order": list(TARGET_PROFILE_ORDER),
    }
    _require_negative_authority(value, label="overlay contract")
    return value


def build_overlay_contract():
    """Return a detached semantics/schema/target artifact with no instances."""

    return copy.deepcopy(_canonical_overlay_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 overlay contract",
            max_bytes=MAX_OVERLAY_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayContractError(str(error)) from None


def validate_overlay_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_overlay_contract,
            label="persona v2 overlay contract",
            max_bytes=MAX_OVERLAY_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayContractError(str(error)) from None


def overlay_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_overlay_contract,
            label="persona v2 overlay contract",
            max_bytes=MAX_OVERLAY_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2OverlayContractError(str(error)) from None


def require_overlay_membership_and_ledgers():
    raise PersonaV2OverlayContractError(
        "overlay semantics, schemas, and integer target marginals are exact, but "
        "source-intent membership, scope placement, logical-document instances, "
        "planned/observed ledgers, feasibility, and execution remain absent"
    )
