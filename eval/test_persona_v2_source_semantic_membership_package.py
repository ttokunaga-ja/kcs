"""Regression gates for the full source-owned semantic-membership package."""

from __future__ import annotations

import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_overlay_reservation_layout as reservation
from eval import persona_v2_realism_profile as realism
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_inventory_layout as source_layout
from eval import persona_v2_source_inventory_profile as inventory_profile
from eval import persona_v2_source_semantic_membership_package as package
from eval import persona_v2_source_semantic_membership_package_validator as independent_validator


# Filled from the canonical producer only after the independent validator and
# all semantic/tamper gates pass.  Keeping the pins here makes an intentional
# contract change review-visible.
EXPECTED_CATALOG_BYTES = 436_495
EXPECTED_CATALOG_SHA256 = (
    "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b"
)
EXPECTED_SUITE_BYTES = 49_837
EXPECTED_SUITE_SHA256 = (
    "6027147bff72129aa308daa79c10581f6eceec9b04eb4667dbe72c0194ac6072"
)
EXPECTED_P01_PILOT_BODY = (
    22_156,
    "12c813d14a353b81d66872d6e56f83aa9923b3b4190286abe9cb05a14de0abae",
    112,
    706,
)
EXPECTED_P12_RESIDUAL_BODY = (
    42_356,
    "12828712e3f3a7896ae2fe3e7e8a97a30d47b65ce4c86c92ce060056c2c6e36d",
    112,
    734,
)
MAX_BUILD_RSS_BYTES = 384 * 2**20

EXPECTED_COMPONENT_SIZE_HISTOGRAM = {
    1: 156_160,
    2: 19_240,
    3: 820,
    4: 560,
    5: 360,
    6: 240,
    7: 60,
}

ROW_FORBIDDEN_TOKENS = frozenset(
    ("answer", "distractor", "final", "oracle", "query", "relevance", "retrieval")
)


def _canonical(value, *, label="semantic membership test value", max_bytes=8 * 2**20):
    return artifact_common.canonical_json_bytes(
        value, label=label, max_bytes=max_bytes
    )


def _jsonl_rows(body, *, cap):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        raise AssertionError("canonical JSONL body must be non-empty and LF-terminated")
    if body.endswith(b"\n\n") or b"\r" in body:
        raise AssertionError("canonical JSONL body has invalid framing")
    rows = []
    for raw in body.splitlines():
        if len(raw) + 1 > cap:
            raise AssertionError("canonical JSONL row exceeds its LF-inclusive cap")
        row = json.loads(raw)
        if _canonical(row, max_bytes=cap - 1) != raw:
            raise AssertionError("JSONL row is not canonical JSON")
        rows.append(row)
    return rows


def _row_has_forbidden_alias(value):
    if type(value) is dict:
        for key, item in value.items():
            lowered = key.lower().replace("-", "_")
            if any(token in lowered for token in ROW_FORBIDDEN_TOKENS):
                return True
            if _row_has_forbidden_alias(item):
                return True
        return False
    if type(value) is list:
        return any(_row_has_forbidden_alias(item) for item in value)
    return False


def _hamilton(total, weighted_rows):
    """Independently allocate exact largest-remainder quotas."""

    floors = {}
    remainders = {}
    for label, weight_bp in weighted_rows:
        numerator = total * weight_bp
        floors[label] = numerator // 10_000
        remainders[label] = numerator % 10_000
    missing = total - sum(floors.values())
    order = sorted(
        floors,
        key=lambda label: (-remainders[label], label.encode("ascii")),
    )
    for label in order[:missing]:
        floors[label] += 1
    if sum(floors.values()) != total:
        raise AssertionError("Hamilton allocation is not total")
    return floors


def _origin_targets(pilot_count, full_count, weighted_rows):
    pilot = _hamilton(pilot_count, weighted_rows)
    full = _hamilton(full_count, weighted_rows)
    residual = {label: full[label] - pilot[label] for label in full}
    if any(value < 0 for value in residual.values()):
        raise AssertionError("full-minus-pilot Hamilton target became negative")
    if sum(residual.values()) != full_count - pilot_count:
        raise AssertionError("full-minus-pilot Hamilton target lost mass")
    return {"pilot": pilot, "full": full, "full-residual": residual}


class _UnionFind:
    def __init__(self):
        self._parent = {}

    def add(self, key):
        self._parent.setdefault(key, key)

    def find(self, key):
        self.add(key)
        parent = self._parent[key]
        if parent != key:
            self._parent[key] = self.find(parent)
        return self._parent[key]

    def union(self, left, right):
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return
        if right_root.encode("ascii") < left_root.encode("ascii"):
            left_root, right_root = right_root, left_root
        self._parent[right_root] = left_root

    def components(self):
        result = defaultdict(set)
        for key in self._parent:
            result[self.find(key)].add(key)
        return dict(result)


def _reservation_components(value):
    union_find = _UnionFind()
    for row in value["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            union_find.union(row["anchor_intent_key"], row["derivative_intent_key"])
        elif row["row_kind"] == "attachment-membership-reservation":
            union_find.union(
                row["host_intent_key"], row["standalone_member_intent_key"]
            )
        else:  # pragma: no cover - independently checked upstream contract.
            raise AssertionError(f"unknown reservation row kind: {row['row_kind']}")
    return union_find.components()


def _all_source_components(intent_keys, reservation_value):
    union_find = _UnionFind()
    for intent_key in intent_keys:
        union_find.add(intent_key)
    for row in reservation_value["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            union_find.union(row["anchor_intent_key"], row["derivative_intent_key"])
        elif row["row_kind"] == "attachment-membership-reservation":
            union_find.union(
                row["host_intent_key"], row["standalone_member_intent_key"]
            )
    return sorted(
        (tuple(sorted(members, key=lambda value: value.encode("ascii")))
         for members in union_find.components().values()),
        key=lambda members: members[0].encode("ascii"),
    )


def _assign_components(components, targets, fixed_labels):
    """Independently repeat fixed-first, multi-before-singleton allocation."""

    labels = sorted(targets, key=lambda value: value.encode("ascii"))
    total = sum(targets.values())
    by_key = {members[0]: members for members in components}
    component_for_intent = {
        intent_key: members[0]
        for members in components
        for intent_key in members
    }
    fixed_by_component = {}
    for intent_key, label in fixed_labels.items():
        component_key = component_for_intent[intent_key]
        previous = fixed_by_component.setdefault(component_key, label)
        if previous != label:
            raise AssertionError("one component received conflicting fixed labels")

    fixed = sorted(
        (
            (by_key[component_key], label)
            for component_key, label in fixed_by_component.items()
        ),
        key=lambda row: (-len(row[0]), row[0][0].encode("ascii")),
    )
    free = sorted(
        (
            members
            for component_key, members in by_key.items()
            if component_key not in fixed_by_component
        ),
        key=lambda members: (-len(members), members[0].encode("ascii")),
    )
    assigned = {label: 0 for label in labels}
    result = {}
    processed = 0

    def apply(members, label):
        nonlocal processed
        size = len(members)
        if targets[label] - assigned[label] < size:
            raise AssertionError("component does not fit its selected target")
        result.update((intent_key, label) for intent_key in members)
        assigned[label] += size
        processed += size

    for members, label in fixed:
        apply(members, label)
    for members in free:
        size = len(members)
        next_processed = processed + size
        eligible = [
            label for label in labels if targets[label] - assigned[label] >= size
        ]
        if not eligible:
            raise AssertionError("no quota has room for the next component")
        chosen = min(
            eligible,
            key=lambda label: (
                -(targets[label] * next_processed - assigned[label] * total),
                label.encode("ascii"),
            ),
        )
        apply(members, chosen)
    if processed != total or assigned != targets or len(result) != total:
        raise AssertionError("component allocation did not close exact targets")
    return result


def _w0_fact_ids_by_graph(graph_value):
    result = {}
    for graph in graph_value["graphs"]:
        fact_ids = []
        for fact in graph["facts"]:
            state = next(
                row["state"]
                for row in fact["visibility_by_checkpoint"]
                if row["checkpoint"] == "W0"
            )
            if state == "current":
                fact_ids.append(fact["fact_id"])
        result[graph["graph_id"]] = tuple(sorted(fact_ids))
    return result


def _fact_profile_indexes(catalog):
    """Build test-owned semantic indexes without using producer ID helpers."""

    by_id = {row["fact_profile_id"]: row for row in catalog["fact_profiles"]}
    normal = {}
    singleton = {}
    conflict = {}
    empty = {}
    for row in catalog["fact_profiles"]:
        key = (row["persona_id"], row["graph_id"])
        if row["profile_kind"] == "empty":
            empty[row["persona_id"]] = row["fact_profile_id"]
        elif row["profile_kind"] == "graph-normal-w0":
            normal[key] = row["fact_profile_id"]
        elif row["profile_kind"] == "w0-singleton":
            singleton[(row["persona_id"], row["graph_id"], row["present_fact_ids"][0])] = (
                row["fact_profile_id"]
            )
        elif row["profile_kind"] == "conflict-branch":
            conflict[(row["persona_id"], row["graph_id"], row["branch_role"])] = (
                row["fact_profile_id"]
            )
        else:
            raise AssertionError(f"unknown fact-profile kind: {row['profile_kind']}")
    return {
        "by_id": by_id,
        "conflict": conflict,
        "empty": empty,
        "normal": normal,
        "singleton": singleton,
    }


def _origin_expectations(persona_id, origin, catalog):
    """Independently derive one origin's components, quotas, and overrides."""

    source_manifest = source_package.build_source_intent_origin_manifest(
        persona_id, origin
    )
    intent_keys = [
        row["intent_key"]
        for descriptor in source_manifest["shard_descriptors"]
        for row in source_package.iter_source_intent_rows(
            persona_id, origin, descriptor["shard_ordinal"]
        )
    ]
    reservation_value = reservation.build_overlay_reservation_origin(
        persona_id, origin
    )
    components = _all_source_components(intent_keys, reservation_value)
    profile_indexes = _fact_profile_indexes(catalog)
    graph_value = fact_graph.build_fact_graph(persona_id)
    graphs = sorted(graph_value["graphs"], key=lambda row: row["graph_id"].encode("ascii"))
    graph_ids = [row["graph_id"] for row in graphs]
    w0_by_graph = _w0_fact_ids_by_graph(graph_value)

    fixed_topic = {}
    anchor_profile_by_key = {}
    for slot in reservation_value["semantic_anchor_slots"]:
        ordinal = slot["semantic_anchor_slot_ordinal"]
        graph_id = graph_ids[(ordinal - 1) % 4]
        fact_id = w0_by_graph[graph_id][((ordinal - 1) // 4) % 8]
        intent_key = slot["intent_key"]
        fixed_topic[intent_key] = graph_id
        anchor_profile_by_key[intent_key] = profile_indexes["singleton"][
            (persona_id, graph_id, fact_id)
        ]

    relation_by_key = {}
    identity_by_key = {}
    container_roles = defaultdict(set)
    conflict_profile_by_key = {}
    near_derivatives = set()
    overlay_keys = set()
    conflict_rows = []
    for row in reservation_value["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            anchor_key = row["anchor_intent_key"]
            derivative_key = row["derivative_intent_key"]
            relation_kind = row["relation_kind"]
            relation_prefix = {
                "exact-duplicate": "exact",
                "near-revision": "near",
                "conflict-copy": "conflict",
            }[relation_kind]
            relation_by_key[anchor_key] = f"{relation_prefix}-anchor"
            relation_by_key[derivative_key] = f"{relation_prefix}-derivative"
            identity_by_key[anchor_key] = row["anchor_identity"]
            identity_by_key[derivative_key] = row["derivative_identity"]
            overlay_keys.update((anchor_key, derivative_key))
            if relation_kind == "near-revision":
                near_derivatives.add(derivative_key)
            if relation_kind == "conflict-copy":
                graph_id = row["conflict_fact_binding"]["graph_id"]
                anchor_profile = profile_indexes["conflict"][
                    (persona_id, graph_id, "a")
                ]
                derivative_profile = profile_indexes["conflict"][
                    (persona_id, graph_id, "b")
                ]
                fixed_topic[anchor_key] = graph_id
                fixed_topic[derivative_key] = graph_id
                conflict_profile_by_key[anchor_key] = anchor_profile
                conflict_profile_by_key[derivative_key] = derivative_profile
                conflict_rows.append(
                    {
                        "anchor_fact_profile_id": anchor_profile,
                        "anchor_intent_key": anchor_key,
                        "cluster_key": row["cluster_key"],
                        "derivative_fact_profile_id": derivative_profile,
                        "derivative_intent_key": derivative_key,
                        "row_kind": "fact-conflict-pair-override",
                    }
                )
        elif row["row_kind"] == "attachment-membership-reservation":
            host_key = row["host_intent_key"]
            member_key = row["standalone_member_intent_key"]
            identity_by_key[host_key] = row["host_identity"]
            identity_by_key[member_key] = row["standalone_member_identity"]
            container_roles[host_key].add("attachment-host")
            container_roles[member_key].add("attachment-member")
            overlay_keys.update((host_key, member_key))
        else:
            raise AssertionError(f"unknown reservation kind: {row['row_kind']}")

    realism_value = realism.build_realism_profile()
    persona_realism = next(
        row for row in realism_value["personas"] if row["persona_id"] == persona_id
    )
    language_weights = [
        (row["language"], row["weight_bp"])
        for row in persona_realism["language_weights_bp"]
    ]
    persona_layout = next(
        row
        for row in source_layout.build_source_inventory_layout()["personas"]
        if row["persona_id"] == persona_id
    )
    pilot_count = persona_layout["pilot_source_count"]
    full_count = persona_layout["full_source_count"]
    language_targets = _origin_targets(pilot_count, full_count, language_weights)[origin]
    topic_targets = _origin_targets(
        pilot_count, full_count, [(graph_id, 2_500) for graph_id in graph_ids]
    )[origin]
    language_assignment = _assign_components(components, language_targets, {})
    topic_assignment = _assign_components(components, topic_targets, fixed_topic)
    return {
        "anchor_profile_by_key": anchor_profile_by_key,
        "components": components,
        "conflict_profile_by_key": conflict_profile_by_key,
        "conflict_rows": sorted(
            conflict_rows, key=lambda row: row["cluster_key"].encode("ascii")
        ),
        "container_roles": {
            key: sorted(values, key=lambda value: value.encode("ascii"))
            for key, values in container_roles.items()
        },
        "identity_by_key": identity_by_key,
        "language_assignment": language_assignment,
        "language_targets": language_targets,
        "near_derivatives": near_derivatives,
        "normal_profile_by_graph": {
            graph_id: profile_indexes["normal"][(persona_id, graph_id)]
            for graph_id in graph_ids
        },
        "overlay_keys": overlay_keys,
        "profile_indexes": profile_indexes,
        "relation_by_key": relation_by_key,
        "reservation": reservation_value,
        "source_manifest": source_manifest,
        "topic_assignment": topic_assignment,
        "topic_targets": topic_targets,
    }


def _encode_jsonl(rows, *, cap):
    parts = []
    for row in rows:
        raw = _canonical(row, label="tampered semantic membership row", max_bytes=cap - 1)
        parts.append(raw + b"\n")
    return b"".join(parts)


def _refresh_binding(binding, value, *, canonical):
    raw = canonical(value)
    binding["artifact_kind"] = value["artifact_kind"]
    binding["artifact_schema"] = value["artifact_schema"]
    binding["artifact_schema_version"] = value["artifact_schema_version"]
    binding["canonical_bytes"] = len(raw)
    binding["sha256"] = hashlib.sha256(raw).hexdigest()


def _rewrite_origin_body(origin_manifest, body):
    rows = _jsonl_rows(body, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF)
    descriptor = origin_manifest["body_descriptor"]
    descriptor["body_bytes"] = len(body)
    descriptor["body_sha256"] = hashlib.sha256(body).hexdigest()
    descriptor["maximum_row_bytes_including_lf"] = max(
        len(line) + 1 for line in body.splitlines()
    )
    descriptor["row_count"] = len(rows)
    ranges = [
        row for row in rows if row.get("row_kind") == "source-shard-total-projection"
    ]
    anchors = [
        row for row in rows if row.get("row_kind") == "fact-semantic-anchor-override"
    ]
    conflicts = [
        row for row in rows if row.get("row_kind") == "fact-conflict-pair-override"
    ]
    summary = origin_manifest["summary"]
    summary["compact_range_receipt_row_count"] = len(ranges)
    summary["compact_anchor_row_count"] = len(anchors)
    summary["compact_conflict_pair_row_count"] = len(conflicts)
    if ranges:
        summary["expanded_content_context_body_bytes"] = sum(
            row["expanded_content_context_body_bytes"] for row in ranges
        )
        summary["expanded_fact_membership_body_bytes"] = sum(
            row["expanded_fact_membership_body_bytes"] for row in ranges
        )
        summary[
            "maximum_expanded_content_context_row_bytes_including_lf"
        ] = max(
            row["expanded_content_context_max_row_bytes_including_lf"]
            for row in ranges
        )
        summary[
            "maximum_expanded_content_context_shard_body_bytes"
        ] = max(row["expanded_content_context_body_bytes"] for row in ranges)
        summary[
            "maximum_expanded_fact_membership_row_bytes_including_lf"
        ] = max(
            row["expanded_fact_membership_max_row_bytes_including_lf"]
            for row in ranges
        )
        summary[
            "maximum_expanded_fact_membership_shard_body_bytes"
        ] = max(row["expanded_fact_membership_body_bytes"] for row in ranges)
        summary["source_count"] = sum(row["row_count"] for row in ranges)
        summary["source_shard_count"] = len(ranges)


def _sum_assignment_rows(manifests, field, label_field):
    counts = Counter()
    for manifest in manifests:
        for row in manifest[field]:
            counts[row[label_field]] += row["source_count"]
    return counts


def _rethread_package(catalog, suite, origins, profiles):
    """Re-hash every supplied wrapper after an intentional semantic mutation."""

    origin_by_key = {
        (row["persona_id"], row["origin"]): row for row in origins
    }
    for origin in origins:
        catalog_binding = next(
            row
            for row in origin["input_bindings"]
            if row["name"] == "persona-v2-source-semantic-membership-catalog"
        )
        _refresh_binding(
            catalog_binding, catalog, canonical=package.canonical_json_bytes
        )

    profile_by_key = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    for profile in profiles:
        _refresh_binding(
            profile["catalog_binding"],
            catalog,
            canonical=package.canonical_json_bytes,
        )
        composed = [
            origin_by_key[(profile["persona_id"], origin)]
            for origin in profile["origin_order"]
        ]
        for binding, origin in zip(
            profile["origin_manifest_bindings"], composed, strict=True
        ):
            _refresh_binding(
                binding, origin, canonical=package.canonical_json_bytes
            )
        profile["fact_profile_assignment_counts"] = [
            {"fact_profile_id": label, "source_count": count}
            for label, count in sorted(
                _sum_assignment_rows(
                    composed, "fact_profile_assignment_counts", "fact_profile_id"
                ).items()
            )
        ]
        profile["language_quota_counts"] = [
            {"language": label, "source_count": count}
            for label, count in sorted(
                _sum_assignment_rows(
                    composed, "language_quota_counts", "language"
                ).items()
            )
        ]
        profile["topic_quota_counts"] = [
            {"source_count": count, "topic_id": label}
            for label, count in sorted(
                _sum_assignment_rows(
                    composed, "topic_quota_counts", "topic_id"
                ).items()
            )
        ]
        summary = profile["summary"]
        summary["compact_body_bytes"] = sum(
            row["body_descriptor"]["body_bytes"] for row in composed
        )
        summary["compact_row_count"] = sum(
            row["body_descriptor"]["row_count"] for row in composed
        )
        summary["expanded_content_context_body_bytes"] = sum(
            row["summary"]["expanded_content_context_body_bytes"]
            for row in composed
        )
        summary["expanded_fact_membership_body_bytes"] = sum(
            row["summary"]["expanded_fact_membership_body_bytes"]
            for row in composed
        )
        summary["origin_manifest_count"] = len(composed)
        summary["present_fact_reference_count"] = sum(
            row["summary"]["present_fact_reference_count"] for row in composed
        )
        summary["semantic_version_source_counts"] = {
            version: sum(
                row["summary"]["semantic_version_source_counts"][version]
                for row in composed
            )
            for version in ("v1", "v2")
        }
        summary["source_count"] = sum(
            row["summary"]["source_count"] for row in composed
        )
        summary["source_shard_count"] = sum(
            row["summary"]["source_shard_count"] for row in composed
        )

    _refresh_binding(
        suite["catalog_binding"], catalog, canonical=package.canonical_json_bytes
    )
    for binding in suite["origin_manifest_bindings"]:
        origin = origin_by_key[(binding["persona_id"], binding["origin"])]
        _refresh_binding(binding, origin, canonical=package.canonical_json_bytes)
    for binding in suite["profile_manifest_bindings"]:
        profile = profile_by_key[(binding["persona_id"], binding["profile"])]
        _refresh_binding(binding, profile, canonical=package.canonical_json_bytes)

    catalog_bytes = len(package.canonical_json_bytes(catalog))
    for ledger in suite["persona_current_component_byte_ledgers"]:
        persona_id = ledger["persona_id"]
        persona_origins = [
            row for row in origins if row["persona_id"] == persona_id
        ]
        persona_profiles = [
            row for row in profiles if row["persona_id"] == persona_id
        ]
        ledger["catalog_bytes_conservatively_charged_in_full"] = catalog_bytes
        ledger["compact_semantic_origin_body_bytes"] = sum(
            row["body_descriptor"]["body_bytes"] for row in persona_origins
        )
        ledger["semantic_origin_manifest_bytes"] = sum(
            len(package.canonical_json_bytes(row)) for row in persona_origins
        )
        ledger["semantic_profile_manifest_bytes"] = sum(
            len(package.canonical_json_bytes(row)) for row in persona_profiles
        )
        current = (
            ledger["existing_source_inventory_component_bytes"]
            + ledger["matching_reservation_origin_bytes"]
            + ledger["catalog_bytes_conservatively_charged_in_full"]
            + ledger["compact_semantic_origin_body_bytes"]
            + ledger["semantic_origin_manifest_bytes"]
            + ledger["semantic_profile_manifest_bytes"]
        )
        ledger["current_component_bytes"] = current
        ledger["headroom_bytes"] = package.MAX_PERSONA_PACKAGE_BYTES - current

    summary = suite["summary"]
    summary["compact_anchor_row_count"] = sum(
        row["summary"]["compact_anchor_row_count"] for row in origins
    )
    summary["compact_body_bytes"] = sum(
        row["body_descriptor"]["body_bytes"] for row in origins
    )
    summary["compact_conflict_pair_row_count"] = sum(
        row["summary"]["compact_conflict_pair_row_count"] for row in origins
    )
    summary["compact_range_receipt_row_count"] = sum(
        row["summary"]["compact_range_receipt_row_count"] for row in origins
    )
    summary["compact_row_count"] = sum(
        row["body_descriptor"]["row_count"] for row in origins
    )
    summary["expanded_content_context_body_bytes"] = sum(
        row["summary"]["expanded_content_context_body_bytes"] for row in origins
    )
    summary["expanded_fact_membership_body_bytes"] = sum(
        row["summary"]["expanded_fact_membership_body_bytes"] for row in origins
    )
    profile_kind_by_id = {
        row["fact_profile_id"]: row["profile_kind"]
        for row in catalog["fact_profiles"]
    }
    kind_counts = Counter()
    for origin in origins:
        for row in origin["fact_profile_assignment_counts"]:
            kind_counts[profile_kind_by_id[row["fact_profile_id"]]] += row[
                "source_count"
            ]
    summary["fact_profile_kind_source_counts"] = dict(kind_counts)
    summary["maximum_compact_row_bytes_including_lf"] = max(
        row["body_descriptor"]["maximum_row_bytes_including_lf"]
        for row in origins
    )
    summary["maximum_component_source_count"] = max(
        row["summary"]["maximum_component_source_count"] for row in origins
    )
    summary[
        "maximum_expanded_content_context_row_bytes_including_lf"
    ] = max(
        row["summary"]["maximum_expanded_content_context_row_bytes_including_lf"]
        for row in origins
    )
    summary["maximum_expanded_content_context_shard_body_bytes"] = max(
        row["summary"]["maximum_expanded_content_context_shard_body_bytes"]
        for row in origins
    )
    summary[
        "maximum_expanded_fact_membership_row_bytes_including_lf"
    ] = max(
        row["summary"]["maximum_expanded_fact_membership_row_bytes_including_lf"]
        for row in origins
    )
    summary["maximum_expanded_fact_membership_shard_body_bytes"] = max(
        row["summary"]["maximum_expanded_fact_membership_shard_body_bytes"]
        for row in origins
    )
    summary["origin_manifest_count"] = len(origins)
    summary["present_fact_reference_count"] = sum(
        row["summary"]["present_fact_reference_count"] for row in origins
    )
    summary["profile_manifest_count"] = len(profiles)
    summary["semantic_version_source_counts"] = {
        version: sum(
            row["summary"]["semantic_version_source_counts"][version]
            for row in origins
        )
        for version in ("v1", "v2")
    }
    summary["source_count"] = sum(
        row["summary"]["source_count"] for row in origins
    )
    summary["source_shard_count"] = sum(
        row["summary"]["source_shard_count"] for row in origins
    )


class PersonaV2SourceSemanticMembershipPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = package.build_source_semantic_membership_catalog()

    @classmethod
    def _full_package_values(cls):
        if not hasattr(cls, "_cached_full_package_values"):
            origins = [
                package.build_source_semantic_membership_origin_manifest(
                    persona_id, origin
                )
                for persona_id in envelope.PERSONA_IDS
                for origin in source_layout.ORIGIN_ORDER
            ]
            profiles = [
                package.build_source_semantic_membership_profile_manifest(
                    persona_id, profile
                )
                for persona_id in envelope.PERSONA_IDS
                for profile in package.PROFILE_ORDER
            ]
            suite = package.build_source_semantic_membership_suite_descriptor()
            cls._cached_full_package_values = (origins, profiles, suite)
        return cls._cached_full_package_values

    @classmethod
    def _upstream_source_values(cls):
        if not hasattr(cls, "_cached_upstream_source_values"):
            origins = [
                source_package.build_source_intent_origin_manifest(
                    persona_id, origin
                )
                for persona_id in envelope.PERSONA_IDS
                for origin in source_layout.ORIGIN_ORDER
            ]
            profiles = [
                source_package.build_source_intent_profile_manifest(
                    persona_id, profile
                )
                for persona_id in envelope.PERSONA_IDS
                for profile in source_package.PROFILE_ORDER
            ]
            suite = source_package.build_source_intent_suite_descriptor()
            cls._cached_upstream_source_values = (origins, profiles, suite)
        return cls._cached_upstream_source_values

    @staticmethod
    def _compact_body_provider(persona_id, origin):
        return package.source_semantic_membership_origin_body_bytes(
            persona_id, origin
        )

    @staticmethod
    def _expanded_context_body_provider(persona_id, origin, shard_ordinal):
        return package.expanded_content_context_shard_body_bytes(
            persona_id, origin, shard_ordinal
        )

    @staticmethod
    def _expanded_membership_body_provider(persona_id, origin, shard_ordinal):
        return package.expanded_fact_membership_shard_body_bytes(
            persona_id, origin, shard_ordinal
        )

    @staticmethod
    def _source_body_provider(persona_id, origin, shard_ordinal):
        return source_package.source_intent_shard_body_bytes(
            persona_id, origin, shard_ordinal
        )

    @classmethod
    def _validate_full_package(
        cls,
        catalog,
        suite,
        origins,
        profiles,
        compact_provider=None,
        context_provider=None,
        membership_provider=None,
        source_provider=None,
        source_suite_override=None,
        source_origins_override=None,
        source_profiles_override=None,
    ):
        source_origins, source_profiles, source_suite = (
            cls._upstream_source_values()
        )
        if source_suite_override is not None:
            source_suite = source_suite_override
        if source_origins_override is not None:
            source_origins = source_origins_override
        if source_profiles_override is not None:
            source_profiles = source_profiles_override
        return independent_validator.validate_source_semantic_membership_package(
            catalog,
            suite,
            origins,
            profiles,
            compact_provider or cls._compact_body_provider,
            context_provider or cls._expanded_context_body_provider,
            membership_provider or cls._expanded_membership_body_provider,
            source_suite=source_suite,
            source_origin_manifests=source_origins,
            source_profile_manifests=source_profiles,
            source_shard_body_provider=source_provider or cls._source_body_provider,
        )

    def test_catalog_has_exact_45_profiles_per_persona_and_no_w0_absent_fact(self):
        raw = package.canonical_json_bytes(self.catalog)
        self.assertEqual(len(raw), EXPECTED_CATALOG_BYTES)
        self.assertEqual(
            package.source_semantic_membership_catalog_sha256(self.catalog),
            EXPECTED_CATALOG_SHA256,
        )
        self.assertLessEqual(len(raw), package.MAX_CATALOG_BYTES)
        self.assertEqual(set(self.catalog["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.catalog["authority"].values()))
        self.assertIs(self.catalog["g0_contract_frozen"], False)

        profiles = self.catalog["fact_profiles"]
        self.assertEqual(len(profiles), 20 * 45)
        self.assertEqual(len(self.catalog["semantic_profiles"]), 71)
        self.assertEqual(len(self.catalog["semantic_topics"]), 20 * 4)
        self.assertFalse(_row_has_forbidden_alias(profiles))
        self.assertFalse(_row_has_forbidden_alias(self.catalog["semantic_profiles"]))
        self.assertFalse(_row_has_forbidden_alias(self.catalog["semantic_topics"]))

        inventory = inventory_profile.build_source_inventory_profile_catalog()
        expected_semantic_profiles = {
            row["source_profile_id"]: row for row in inventory["source_profile_rows"]
        }
        actual_semantic_profiles = {
            row["source_profile_id"]: row
            for row in self.catalog["semantic_profiles"]
        }
        self.assertEqual(set(actual_semantic_profiles), set(expected_semantic_profiles))
        self.assertEqual(
            len({row["semantic_profile_id"] for row in actual_semantic_profiles.values()}),
            71,
        )
        for source_profile_id, row in actual_semantic_profiles.items():
            self.assertEqual(frozenset(row), package.SEMANTIC_PROFILE_FIELDS)
            upstream = expected_semantic_profiles[source_profile_id]
            self.assertEqual(row["variant_id"], upstream["variant_id"])
            self.assertEqual(row["family"], upstream["family"])
            self.assertEqual(row["gate_role"], upstream["gate_role"])
            self.assertEqual(
                row["formal_recipe_binding_status"],
                upstream["source_recipe"]["binding_status"],
            )
            self.assertEqual(row["formal_recipe_binding_status"], "reserved-unbound")

        by_persona = defaultdict(list)
        for row in profiles:
            self.assertEqual(frozenset(row), package.FACT_PROFILE_FIELDS)
            by_persona[row["persona_id"]].append(row)
        self.assertEqual(tuple(by_persona), envelope.PERSONA_IDS)

        for persona_id in envelope.PERSONA_IDS:
            graph_value = fact_graph.build_fact_graph(persona_id)
            w0_by_graph = _w0_fact_ids_by_graph(graph_value)
            all_graph_fact_ids = {
                row["graph_id"]: {fact["fact_id"] for fact in row["facts"]}
                for row in graph_value["graphs"]
            }
            rows = by_persona[persona_id]
            self.assertEqual(len(rows), 45)
            self.assertEqual(
                Counter(row["profile_kind"] for row in rows),
                {
                    "empty": 1,
                    "w0-singleton": 32,
                    "graph-normal-w0": 4,
                    "conflict-branch": 8,
                },
            )
            empty = next(row for row in rows if row["profile_kind"] == "empty")
            self.assertEqual(empty["present_fact_ids"], [])
            self.assertEqual(empty["graph_id"], "not-applicable")

            for row in rows:
                present = row["present_fact_ids"]
                self.assertEqual(present, sorted(set(present)))
                if row["graph_id"] == "not-applicable":
                    self.assertEqual(present, [])
                    continue
                graph_id = row["graph_id"]
                self.assertTrue(set(present) <= set(w0_by_graph[graph_id]))
                absent_at_w0 = all_graph_fact_ids[graph_id] - set(w0_by_graph[graph_id])
                self.assertTrue(set(present).isdisjoint(absent_at_w0))

            for graph_id in sorted(w0_by_graph):
                branch_a = next(
                    row
                    for row in rows
                    if row["graph_id"] == graph_id
                    and row["profile_kind"] == "conflict-branch"
                    and row["branch_role"] == "a"
                )
                branch_b = next(
                    row
                    for row in rows
                    if row["graph_id"] == graph_id
                    and row["profile_kind"] == "conflict-branch"
                    and row["branch_role"] == "b"
                )
                a_facts = set(branch_a["present_fact_ids"])
                b_facts = set(branch_b["present_fact_ids"])
                self.assertNotEqual(a_facts, b_facts)
                self.assertEqual(len(a_facts), 7)
                self.assertEqual(len(b_facts), 7)
                self.assertEqual(len(a_facts & b_facts), 6)

    def test_catalog_topic_and_semantic_profile_bijections_are_exact(self):
        topics = self.catalog["semantic_topics"]
        self.assertEqual(len(topics), 80)
        self.assertEqual(len({row["topic_id"] for row in topics}), 80)
        self.assertEqual(
            len({(row["persona_id"], row["graph_id"]) for row in topics}), 80
        )
        self.assertEqual(
            len(
                {
                    (row["persona_id"], row["project_or_case_id"])
                    for row in topics
                }
            ),
            80,
        )
        for persona_id in envelope.PERSONA_IDS:
            graph_value = fact_graph.build_fact_graph(persona_id)
            expected = {
                (row["graph_id"], row["project_or_case_id"])
                for row in graph_value["graphs"]
            }
            actual = {
                (row["graph_id"], row["project_or_case_id"])
                for row in topics
                if row["persona_id"] == persona_id
            }
            self.assertEqual(actual, expected)

        inventory = inventory_profile.build_source_inventory_profile_catalog()
        semantic_profiles = self.catalog["semantic_profiles"]
        self.assertEqual(len(semantic_profiles), inventory_profile.EXPECTED_PROFILE_COUNT)
        self.assertEqual(
            [row["source_profile_id"] for row in semantic_profiles],
            [row["source_profile_id"] for row in inventory["source_profile_rows"]],
        )
        self.assertEqual(
            len({row["semantic_profile_id"] for row in semantic_profiles}), 71
        )
        self.assertTrue(
            all(
                row["formal_recipe_binding_status"] == "reserved-unbound"
                for row in semantic_profiles
            )
        )

    def test_independent_catalog_validator_rejects_semantic_tamper(self):
        validate_catalog = (
            independent_validator.validate_source_semantic_membership_catalog
        )
        self.assertIsNotNone(validate_catalog(self.catalog))
        cases = []

        candidate = copy.deepcopy(self.catalog)
        singleton = next(
            row
            for row in candidate["fact_profiles"]
            if row["persona_id"] == "p01"
            and row["profile_kind"] == "w0-singleton"
        )
        foreign_graph = fact_graph.build_fact_graph("p02")["graphs"][0]
        foreign_fact = foreign_graph["facts"][0]
        singleton["present_fact_ids"] = [foreign_fact["fact_id"]]
        singleton["synthetic_entity_ids"] = [foreign_fact["subject_entity_id"]]
        cases.append(("foreign-fact", candidate))

        candidate = copy.deepcopy(self.catalog)
        singleton = next(
            row
            for row in candidate["fact_profiles"]
            if row["persona_id"] == "p01"
            and row["profile_kind"] == "w0-singleton"
        )
        graph = next(
            row
            for row in fact_graph.build_fact_graph("p01")["graphs"]
            if row["graph_id"] == singleton["graph_id"]
        )
        absent = next(
            fact
            for fact in graph["facts"]
            if next(
                state["state"]
                for state in fact["visibility_by_checkpoint"]
                if state["checkpoint"] == "W0"
            )
            != "current"
        )
        singleton["present_fact_ids"] = [absent["fact_id"]]
        singleton["synthetic_entity_ids"] = [absent["subject_entity_id"]]
        cases.append(("w0-absent-fact", candidate))

        candidate = copy.deepcopy(self.catalog)
        branch_a = next(
            row
            for row in candidate["fact_profiles"]
            if row["persona_id"] == "p01"
            and row["profile_kind"] == "conflict-branch"
            and row["branch_role"] == "a"
        )
        branch_b = next(
            row
            for row in candidate["fact_profiles"]
            if row["persona_id"] == "p01"
            and row["profile_kind"] == "conflict-branch"
            and row["branch_role"] == "b"
            and row["graph_id"] == branch_a["graph_id"]
        )
        branch_b["present_fact_ids"] = copy.deepcopy(branch_a["present_fact_ids"])
        branch_b["synthetic_entity_ids"] = copy.deepcopy(
            branch_a["synthetic_entity_ids"]
        )
        cases.append(("collapsed-conflict-branches", candidate))

        candidate = copy.deepcopy(self.catalog)
        candidate["semantic_topics"][0]["graph_id"], candidate["semantic_topics"][1][
            "graph_id"
        ] = (
            candidate["semantic_topics"][1]["graph_id"],
            candidate["semantic_topics"][0]["graph_id"],
        )
        cases.append(("topic-graph-mutation", candidate))

        candidate = copy.deepcopy(self.catalog)
        first, second = candidate["semantic_profiles"][:2]
        first["source_profile_id"], second["source_profile_id"] = (
            second["source_profile_id"],
            first["source_profile_id"],
        )
        cases.append(("semantic-profile-source-swap", candidate))

        candidate = copy.deepcopy(self.catalog)
        candidate["semantic_profiles"][0]["query_alias"] = "forbidden"
        cases.append(("query-alias", candidate))

        candidate = copy.deepcopy(self.catalog)
        candidate["authority"][next(iter(sorted(candidate["authority"])))] = True
        cases.append(("authority-escalation", candidate))

        for label, candidate in cases:
            with self.subTest(label=label):
                with self.assertRaises(
                    independent_validator.PersonaV2SourceSemanticMembershipPackageValidationError
                ):
                    validate_catalog(candidate)

    def test_all_203000_expanded_rows_and_3733_compact_rows_are_exact(self):
        fact_profiles = _fact_profile_indexes(self.catalog)
        fact_by_id = fact_profiles["by_id"]
        semantic_by_source = {
            row["source_profile_id"]: row
            for row in self.catalog["semantic_profiles"]
        }
        topic_by_id = {
            row["topic_id"]: row for row in self.catalog["semantic_topics"]
        }
        total_sources = 0
        total_shards = 0
        compact_kinds = Counter()
        component_histogram = Counter()
        semantic_versions = Counter()
        used_semantic_profiles = set()
        raw_source_count = 0
        searchable_source_count = 0

        for persona_id in envelope.PERSONA_IDS:
            for origin in source_layout.ORIGIN_ORDER:
                expectations = _origin_expectations(
                    persona_id, origin, self.catalog
                )
                source_manifest = expectations["source_manifest"]
                manifest = package.build_source_semantic_membership_origin_manifest(
                    persona_id, origin
                )
                body = package.source_semantic_membership_origin_body_bytes(
                    persona_id, origin
                )
                compact_rows = _jsonl_rows(
                    body, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
                )
                self.assertEqual(
                    len(body), manifest["body_descriptor"]["body_bytes"]
                )
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(),
                    manifest["body_descriptor"]["body_sha256"],
                )
                self.assertEqual(
                    len(compact_rows), manifest["body_descriptor"]["row_count"]
                )
                self.assertLessEqual(
                    len(compact_rows), package.MAX_COMPACT_ROWS_PER_ORIGIN
                )
                self.assertLessEqual(len(body), package.MAX_ORIGIN_BODY_BYTES)
                self.assertEqual(set(manifest["authority"]), package.AUTHORITY_FIELDS)
                self.assertTrue(
                    all(flag is False for flag in manifest["authority"].values())
                )
                self.assertIs(manifest["g0_contract_frozen"], False)
                self.assertFalse(_row_has_forbidden_alias(compact_rows))

                for row in compact_rows:
                    compact_kinds[row["row_kind"]] += 1
                range_rows = [
                    row
                    for row in compact_rows
                    if row["row_kind"] == "source-shard-total-projection"
                ]
                anchor_rows = [
                    row
                    for row in compact_rows
                    if row["row_kind"] == "fact-semantic-anchor-override"
                ]
                conflict_rows = [
                    row
                    for row in compact_rows
                    if row["row_kind"] == "fact-conflict-pair-override"
                ]
                self.assertTrue(
                    all(frozenset(row) == package.RANGE_ROW_FIELDS for row in range_rows)
                )
                self.assertTrue(
                    all(frozenset(row) == package.ANCHOR_ROW_FIELDS for row in anchor_rows)
                )
                self.assertTrue(
                    all(
                        frozenset(row) == package.CONFLICT_ROW_FIELDS
                        for row in conflict_rows
                    )
                )
                expected_anchor_rows = [
                    {
                        "fact_profile_id": expectations[
                            "anchor_profile_by_key"
                        ][slot["intent_key"]],
                        "intent_key": slot["intent_key"],
                        "row_kind": "fact-semantic-anchor-override",
                        "semantic_anchor_slot_ordinal": slot[
                            "semantic_anchor_slot_ordinal"
                        ],
                    }
                    for slot in expectations["reservation"]["semantic_anchor_slots"]
                ]
                self.assertEqual(anchor_rows, expected_anchor_rows)
                self.assertEqual(conflict_rows, expectations["conflict_rows"])
                self.assertTrue(
                    set(expectations["anchor_profile_by_key"]).isdisjoint(
                        expectations["overlay_keys"]
                    )
                )
                range_by_shard = {
                    row["source_shard_id"]: row for row in range_rows
                }
                self.assertEqual(
                    list(range_by_shard),
                    [
                        row["shard_id"]
                        for row in source_manifest["shard_descriptors"]
                    ],
                )

                component_histogram.update(
                    len(component) for component in expectations["components"]
                )
                actual_language_by_key = {}
                actual_topic_by_key = {}
                actual_facts_by_key = {}
                origin_language_counts = Counter()
                origin_topic_counts = Counter()
                origin_fact_profile_counts = Counter()
                origin_fact_reference_count = 0
                origin_context_bytes = 0
                origin_membership_bytes = 0

                for descriptor in source_manifest["shard_descriptors"]:
                    shard_ordinal = descriptor["shard_ordinal"]
                    receipt = range_by_shard[descriptor["shard_id"]]
                    source_rows = source_package.iter_source_intent_rows(
                        persona_id, origin, shard_ordinal
                    )
                    context_rows = package.iter_expanded_content_context_rows(
                        persona_id, origin, shard_ordinal
                    )
                    membership_rows = package.iter_expanded_fact_membership_rows(
                        persona_id, origin, shard_ordinal
                    )
                    context_digest = hashlib.sha256()
                    membership_digest = hashlib.sha256()
                    context_bytes = 0
                    membership_bytes = 0
                    context_maximum = 0
                    membership_maximum = 0
                    shard_count = 0
                    for source_row, context, membership in zip(
                        source_rows, context_rows, membership_rows, strict=True
                    ):
                        shard_count += 1
                        total_sources += 1
                        intent_key = source_row["intent_key"]
                        self.assertEqual(
                            frozenset(context), package.EXPANDED_CONTEXT_ROW_FIELDS
                        )
                        self.assertEqual(
                            frozenset(membership),
                            package.EXPANDED_MEMBERSHIP_ROW_FIELDS,
                        )
                        self.assertFalse(_row_has_forbidden_alias(context))
                        self.assertFalse(_row_has_forbidden_alias(membership))
                        self.assertEqual(context["intent_key"], intent_key)
                        self.assertEqual(membership["intent_key"], intent_key)
                        self.assertEqual(context["persona_id"], persona_id)
                        self.assertEqual(membership["persona_id"], persona_id)
                        self.assertEqual(context["origin"], origin)
                        self.assertEqual(membership["origin"], origin)
                        self.assertEqual(
                            context["content_context_id"],
                            source_row["content_context_id"],
                        )
                        self.assertEqual(
                            context["deterministic_payload_seed"],
                            source_row["deterministic_payload_seed"],
                        )
                        self.assertEqual(
                            membership["present_fact_set_key"],
                            source_row["present_fact_set_key"],
                        )
                        semantic_profile = semantic_by_source[
                            source_row["source_profile_id"]
                        ]
                        used_semantic_profiles.add(
                            semantic_profile["semantic_profile_id"]
                        )
                        self.assertEqual(
                            context["semantic_profile_id"],
                            semantic_profile["semantic_profile_id"],
                        )
                        self.assertEqual(
                            context["language"],
                            expectations["language_assignment"][intent_key],
                        )
                        expected_graph_id = expectations["topic_assignment"][
                            intent_key
                        ]
                        self.assertEqual(
                            topic_by_id[context["topic_id"]]["graph_id"],
                            expected_graph_id,
                        )
                        self.assertEqual(context["logical_period_id"], "W0")
                        self.assertEqual(context["membership_status"], "current")
                        expected_version = (
                            "v2"
                            if intent_key in expectations["near_derivatives"]
                            else "v1"
                        )
                        self.assertEqual(context["semantic_version"], expected_version)
                        semantic_versions[expected_version] += 1
                        self.assertEqual(
                            context["content_relation_role"],
                            expectations["relation_by_key"].get(
                                intent_key, "independent"
                            ),
                        )
                        self.assertEqual(
                            context["container_role_ids"],
                            expectations["container_roles"].get(intent_key, []),
                        )
                        self.assertEqual(
                            context["semantic_anchor_capacity"],
                            intent_key in expectations["anchor_profile_by_key"],
                        )

                        identity = expectations["identity_by_key"].get(intent_key)
                        if identity is None:
                            content_context_id = source_row["content_context_id"]
                            identity = {
                                "logical_branch_key": (
                                    f"{content_context_id}-branch-v2"
                                ),
                                "logical_document_key": (
                                    f"{content_context_id}-document-v2"
                                ),
                                "logical_revision_key": (
                                    f"{content_context_id}-revision-v2"
                                ),
                                "payload_equivalence_key": source_row[
                                    "deterministic_payload_seed"
                                ],
                                "semantic_section_key": (
                                    f"{content_context_id}-section-v2"
                                ),
                            }
                        self.assertEqual(
                            context["payload_equivalence_key"],
                            identity["payload_equivalence_key"],
                        )
                        for field in (
                            "logical_branch_key",
                            "logical_document_key",
                            "logical_revision_key",
                        ):
                            self.assertEqual(membership[field], identity[field])

                        fact_profile_id = expectations[
                            "anchor_profile_by_key"
                        ].get(intent_key)
                        if fact_profile_id is None:
                            fact_profile_id = expectations[
                                "conflict_profile_by_key"
                            ].get(intent_key)
                        if fact_profile_id is None:
                            if semantic_profile["gate_role"] == "raw_only":
                                fact_profile_id = fact_profiles["empty"][persona_id]
                            else:
                                fact_profile_id = expectations[
                                    "normal_profile_by_graph"
                                ][expected_graph_id]
                        fact_profile = fact_by_id[fact_profile_id]
                        self.assertEqual(
                            membership["fact_profile_id"], fact_profile_id
                        )
                        self.assertEqual(
                            membership["present_fact_ids"],
                            fact_profile["present_fact_ids"],
                        )
                        if semantic_profile["gate_role"] == "raw_only":
                            raw_source_count += 1
                            self.assertEqual(membership["present_fact_ids"], [])
                            self.assertEqual(
                                membership["projection_mode"], "no-present-facts"
                            )
                            self.assertEqual(
                                membership["semantic_section_key"],
                                "not-applicable-no-present-facts",
                            )
                        else:
                            searchable_source_count += 1
                            self.assertTrue(membership["present_fact_ids"])
                            self.assertEqual(
                                membership["projection_mode"],
                                "all-present-facts-single-semantic-section",
                            )
                            self.assertEqual(
                                membership["semantic_section_key"],
                                identity["semantic_section_key"],
                            )
                            self.assertEqual(
                                fact_profile["graph_id"], expected_graph_id
                            )

                        origin_language_counts[context["language"]] += 1
                        origin_topic_counts[context["topic_id"]] += 1
                        origin_fact_profile_counts[fact_profile_id] += 1
                        origin_fact_reference_count += len(
                            membership["present_fact_ids"]
                        )
                        actual_language_by_key[intent_key] = context["language"]
                        actual_topic_by_key[intent_key] = context["topic_id"]
                        actual_facts_by_key[intent_key] = tuple(
                            membership["present_fact_ids"]
                        )

                        context_raw = _canonical(
                            context,
                            label="expanded context test row",
                            max_bytes=(
                                package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF
                                - 1
                            ),
                        ) + b"\n"
                        membership_raw = _canonical(
                            membership,
                            label="expanded membership test row",
                            max_bytes=(
                                package.MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF
                                - 1
                            ),
                        ) + b"\n"
                        context_digest.update(context_raw)
                        membership_digest.update(membership_raw)
                        context_bytes += len(context_raw)
                        membership_bytes += len(membership_raw)
                        context_maximum = max(context_maximum, len(context_raw))
                        membership_maximum = max(
                            membership_maximum, len(membership_raw)
                        )

                    total_shards += 1
                    self.assertEqual(shard_count, descriptor["row_count"])
                    self.assertLessEqual(
                        shard_count, package.MAX_EXPANDED_ROWS_PER_SHARD
                    )
                    self.assertEqual(receipt["row_count"], shard_count)
                    self.assertEqual(
                        receipt["first_intent_key"],
                        descriptor["first_intent_key"],
                    )
                    self.assertEqual(
                        receipt["last_intent_key"],
                        descriptor["last_intent_key"],
                    )
                    self.assertEqual(
                        receipt["source_body_sha256"], descriptor["body_sha256"]
                    )
                    self.assertEqual(
                        receipt["expanded_content_context_body_bytes"],
                        context_bytes,
                    )
                    self.assertEqual(
                        receipt["expanded_content_context_sha256"],
                        context_digest.hexdigest(),
                    )
                    self.assertEqual(
                        receipt[
                            "expanded_content_context_max_row_bytes_including_lf"
                        ],
                        context_maximum,
                    )
                    self.assertEqual(
                        receipt["expanded_fact_membership_body_bytes"],
                        membership_bytes,
                    )
                    self.assertEqual(
                        receipt["expanded_fact_membership_sha256"],
                        membership_digest.hexdigest(),
                    )
                    self.assertEqual(
                        receipt[
                            "expanded_fact_membership_max_row_bytes_including_lf"
                        ],
                        membership_maximum,
                    )
                    self.assertLessEqual(
                        context_maximum,
                        package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
                    )
                    self.assertLessEqual(
                        membership_maximum,
                        package.MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF,
                    )
                    self.assertLessEqual(
                        context_bytes, package.MAX_EXPANDED_SHARD_BODY_BYTES
                    )
                    self.assertLessEqual(
                        membership_bytes, package.MAX_EXPANDED_SHARD_BODY_BYTES
                    )
                    origin_context_bytes += context_bytes
                    origin_membership_bytes += membership_bytes

                for component in expectations["components"]:
                    self.assertEqual(
                        len({actual_language_by_key[key] for key in component}), 1
                    )
                    self.assertEqual(
                        len({actual_topic_by_key[key] for key in component}), 1
                    )
                    roles = {
                        expectations["relation_by_key"].get(key, "independent")
                        for key in component
                    }
                    if not any(role.startswith("conflict-") for role in roles):
                        self.assertEqual(
                            len({actual_facts_by_key[key] for key in component}), 1
                        )

                expected_topic_counts = Counter(
                    {
                        next(
                            row["topic_id"]
                            for row in self.catalog["semantic_topics"]
                            if row["persona_id"] == persona_id
                            and row["graph_id"] == graph_id
                        ): count
                        for graph_id, count in expectations["topic_targets"].items()
                    }
                )
                self.assertEqual(origin_language_counts, expectations["language_targets"])
                self.assertEqual(origin_topic_counts, expected_topic_counts)
                self.assertEqual(
                    manifest["language_quota_counts"],
                    [
                        {"language": label, "source_count": count}
                        for label, count in sorted(origin_language_counts.items())
                    ],
                )
                self.assertEqual(
                    manifest["topic_quota_counts"],
                    [
                        {"source_count": count, "topic_id": label}
                        for label, count in sorted(origin_topic_counts.items())
                    ],
                )
                self.assertEqual(
                    manifest["fact_profile_assignment_counts"],
                    [
                        {"fact_profile_id": label, "source_count": count}
                        for label, count in sorted(origin_fact_profile_counts.items())
                    ],
                )
                self.assertEqual(
                    manifest["summary"]["present_fact_reference_count"],
                    origin_fact_reference_count,
                )
                self.assertEqual(
                    manifest["summary"]["expanded_content_context_body_bytes"],
                    origin_context_bytes,
                )
                self.assertEqual(
                    manifest["summary"]["expanded_fact_membership_body_bytes"],
                    origin_membership_bytes,
                )

        self.assertEqual(total_sources, 203_000)
        self.assertEqual(total_shards, 73)
        self.assertEqual(
            compact_kinds,
            {
                "source-shard-total-projection": 73,
                "fact-semantic-anchor-override": 2_100,
                "fact-conflict-pair-override": 1_560,
            },
        )
        self.assertEqual(component_histogram, EXPECTED_COMPONENT_SIZE_HISTOGRAM)
        self.assertEqual(
            semantic_versions, {"v1": 189_770, "v2": 13_230}
        )
        self.assertEqual(
            used_semantic_profiles,
            {
                row["semantic_profile_id"]
                for row in self.catalog["semantic_profiles"]
            },
        )
        self.assertEqual(raw_source_count + searchable_source_count, 203_000)
        self.assertGreater(raw_source_count, 0)
        self.assertGreater(searchable_source_count, 0)

    def test_suite_profiles_pilot_reuse_caps_and_negative_authority(self):
        origins, profiles, suite = self._full_package_values()
        origin_by_key = {
            (row["persona_id"], row["origin"]): row for row in origins
        }
        profile_by_key = {
            (row["persona_id"], row["profile"]): row for row in profiles
        }
        suite_raw = package.canonical_json_bytes(suite)
        self.assertEqual(len(origins), 40)
        self.assertEqual(len(profiles), 40)
        self.assertEqual(len(suite_raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(
            package.source_semantic_membership_suite_descriptor_sha256(suite),
            EXPECTED_SUITE_SHA256,
        )
        self.assertLessEqual(len(suite_raw), package.MAX_SUITE_DESCRIPTOR_BYTES)
        self.assertEqual(set(suite), package.SUITE_TOP_LEVEL_FIELDS)
        self.assertEqual(set(suite["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in suite["authority"].values()))
        self.assertIs(suite["g0_contract_frozen"], False)
        self.assertEqual(
            suite["summary"]["fact_profile_kind_source_counts"],
            {
                "conflict-branch": 3_120,
                "empty": 73_350,
                "graph-normal-w0": 124_430,
                "w0-singleton": 2_100,
            },
        )
        self.assertEqual(
            suite["summary"]["semantic_version_source_counts"],
            {"v1": 189_770, "v2": 13_230},
        )
        self.assertEqual(suite["summary"]["present_fact_reference_count"], 1_019_380)
        self.assertEqual(suite["summary"]["source_count"], 203_000)
        self.assertEqual(suite["summary"]["source_shard_count"], 73)
        self.assertEqual(suite["summary"]["compact_range_receipt_row_count"], 73)
        self.assertEqual(suite["summary"]["compact_anchor_row_count"], 2_100)
        self.assertEqual(suite["summary"]["compact_conflict_pair_row_count"], 1_560)
        self.assertEqual(suite["summary"]["compact_row_count"], 3_733)
        self.assertEqual(suite["summary"]["maximum_component_source_count"], 7)
        self.assertLessEqual(
            suite["summary"]["maximum_compact_row_bytes_including_lf"],
            package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertLessEqual(
            suite["summary"][
                "maximum_expanded_content_context_row_bytes_including_lf"
            ],
            package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertLessEqual(
            suite["summary"][
                "maximum_expanded_fact_membership_row_bytes_including_lf"
            ],
            package.MAX_EXPANDED_MEMBERSHIP_ROW_BYTES_INCLUDING_LF,
        )
        self.assertLessEqual(
            suite["summary"][
                "maximum_expanded_content_context_shard_body_bytes"
            ],
            package.MAX_EXPANDED_SHARD_BODY_BYTES,
        )
        self.assertLessEqual(
            suite["summary"][
                "maximum_expanded_fact_membership_shard_body_bytes"
            ],
            package.MAX_EXPANDED_SHARD_BODY_BYTES,
        )
        self.assertFalse(
            suite["completion_claims"][
                "formal_complete_persona_package_cap_proved"
            ]
        )

        self.assertEqual(
            [(row["persona_id"], row["origin"]) for row in origins],
            [
                (persona_id, origin)
                for persona_id in envelope.PERSONA_IDS
                for origin in source_layout.ORIGIN_ORDER
            ],
        )
        self.assertEqual(
            [(row["persona_id"], row["profile"]) for row in profiles],
            [
                (persona_id, profile)
                for persona_id in envelope.PERSONA_IDS
                for profile in package.PROFILE_ORDER
            ],
        )
        for value in origins:
            self.assertEqual(set(value), package.ORIGIN_TOP_LEVEL_FIELDS)
            self.assertLessEqual(
                len(package.canonical_json_bytes(value)),
                package.MAX_ORIGIN_MANIFEST_BYTES,
            )
            self.assertTrue(
                all(flag is False for flag in value["authority"].values())
            )
        for value in profiles:
            self.assertEqual(set(value), package.PROFILE_TOP_LEVEL_FIELDS)
            self.assertLessEqual(
                len(package.canonical_json_bytes(value)),
                package.MAX_PROFILE_MANIFEST_BYTES,
            )
            self.assertTrue(
                all(flag is False for flag in value["authority"].values())
            )

        for persona_id in envelope.PERSONA_IDS:
            pilot = profile_by_key[(persona_id, "pilot")]
            full = profile_by_key[(persona_id, "full")]
            pilot_origin = origin_by_key[(persona_id, "pilot")]
            self.assertEqual(pilot["origin_order"], ["pilot"])
            self.assertEqual(full["origin_order"], list(source_layout.ORIGIN_ORDER))
            self.assertEqual(
                pilot["origin_manifest_bindings"][0],
                full["origin_manifest_bindings"][0],
            )
            pilot_binding = full["origin_manifest_bindings"][0]
            self.assertEqual(
                pilot_binding["sha256"],
                package.source_semantic_membership_origin_manifest_sha256(
                    persona_id, "pilot", pilot_origin
                ),
            )
            self.assertEqual(
                full["summary"]["source_count"],
                envelope.profile_file_count(persona_id, "full"),
            )

            ledger = next(
                row
                for row in suite["persona_current_component_byte_ledgers"]
                if row["persona_id"] == persona_id
            )
            self.assertEqual(
                ledger["current_component_bytes"],
                ledger["existing_source_inventory_component_bytes"]
                + ledger["matching_reservation_origin_bytes"]
                + ledger["catalog_bytes_conservatively_charged_in_full"]
                + ledger["compact_semantic_origin_body_bytes"]
                + ledger["semantic_origin_manifest_bytes"]
                + ledger["semantic_profile_manifest_bytes"],
            )
            self.assertLessEqual(
                ledger["current_component_bytes"],
                package.MAX_PERSONA_PACKAGE_BYTES,
            )
            self.assertEqual(
                ledger["headroom_bytes"],
                package.MAX_PERSONA_PACKAGE_BYTES
                - ledger["current_component_bytes"],
            )
            self.assertIs(
                ledger["formal_complete_persona_package_cap_proved"], False
            )

        for coordinate, expected in {
            ("p01", "pilot"): EXPECTED_P01_PILOT_BODY,
            ("p12", "full-residual"): EXPECTED_P12_RESIDUAL_BODY,
        }.items():
            body = package.source_semantic_membership_origin_body_bytes(*coordinate)
            actual = (
                len(body),
                hashlib.sha256(body).hexdigest(),
                len(body.splitlines()),
                max(len(line) + 1 for line in body.splitlines()),
            )
            self.assertEqual(actual, expected)

        with self.assertRaises(
            package.PersonaV2SourceSemanticMembershipPackageError
        ):
            package.require_complete_source_semantic_membership_package()

    def test_independent_full_package_validator_accepts_every_streamed_body(self):
        script = """
import json
import resource
import sys
from eval import persona_v2_contract as envelope
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_semantic_membership_package as package
from eval import persona_v2_source_semantic_membership_package_validator as validator

catalog = package.build_source_semantic_membership_catalog()
origins = [
    package.build_source_semantic_membership_origin_manifest(persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
]
profiles = [
    package.build_source_semantic_membership_profile_manifest(persona_id, profile)
    for persona_id in envelope.PERSONA_IDS
    for profile in package.PROFILE_ORDER
]
suite = package.build_source_semantic_membership_suite_descriptor()
source_origins = [
    source_package.build_source_intent_origin_manifest(persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in source_package.ORIGIN_ORDER
]
source_profiles = [
    source_package.build_source_intent_profile_manifest(persona_id, profile)
    for persona_id in envelope.PERSONA_IDS
    for profile in source_package.PROFILE_ORDER
]
source_suite = source_package.build_source_intent_suite_descriptor()

success = validator.validate_source_semantic_membership_package(
    catalog,
    suite,
    origins,
    profiles,
    package.source_semantic_membership_origin_body_bytes,
    package.expanded_content_context_shard_body_bytes,
    package.expanded_fact_membership_shard_body_bytes,
    source_suite=source_suite,
    source_origin_manifests=source_origins,
    source_profile_manifests=source_profiles,
    source_shard_body_provider=source_package.source_intent_shard_body_bytes,
)
maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform == "darwin":
    rss_bytes = int(maximum_rss)
elif sys.platform.startswith("linux"):
    rss_bytes = int(maximum_rss) * 1024
else:
    raise RuntimeError(f"unsupported ru_maxrss unit contract: {sys.platform}")
print(json.dumps({"rss_bytes": rss_bytes, "success": success}, sort_keys=True))
"""
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONHASHSEED": "73",
                "TZ": "UTC",
                "LC_ALL": "C",
                "LANG": "C",
            }
        )
        output = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            text=True,
            timeout=1_200,
        )
        measured = json.loads(output)
        self.assertIs(measured["success"], True)
        self.assertGreater(measured["rss_bytes"], 0)
        self.assertLessEqual(measured["rss_bytes"], MAX_BUILD_RSS_BYTES)

    def test_provider_callback_target_and_upstream_metadata_mutation_are_rejected(self):
        base_origins, base_profiles, base_suite = self._full_package_values()
        base_source_origins, base_source_profiles, base_source_suite = (
            self._upstream_source_values()
        )

        for mutation_target in ("semantic-suite", "source-suite"):
            with self.subTest(mutation_target=mutation_target):
                catalog = copy.deepcopy(self.catalog)
                suite = copy.deepcopy(base_suite)
                origins = copy.deepcopy(base_origins)
                profiles = copy.deepcopy(base_profiles)
                source_suite = copy.deepcopy(base_source_suite)
                source_origins = copy.deepcopy(base_source_origins)
                source_profiles = copy.deepcopy(base_source_profiles)
                semantic_opening_scope = suite["completion_scope"]
                source_opening_scope = source_suite["completion_scope"]

                def mutating_provider(*coordinates):
                    if mutation_target == "semantic-suite":
                        suite["completion_scope"] = (
                            "mutated-during-provider-callback"
                        )
                    else:
                        source_suite["completion_scope"] = (
                            "mutated-during-provider-callback"
                        )
                    return b""

                def detached_validation(*args, **kwargs):
                    self.assertIsNot(args[1], suite)
                    self.assertIsNot(kwargs["source_suite"], source_suite)
                    args[4]("p01", "pilot")
                    self.assertEqual(
                        args[1]["completion_scope"], semantic_opening_scope
                    )
                    self.assertEqual(
                        kwargs["source_suite"]["completion_scope"],
                        source_opening_scope,
                    )
                    return True

                with mock.patch.object(
                    independent_validator,
                    "_validate_source_semantic_membership_package_snapshot",
                    side_effect=detached_validation,
                ):
                    with self.assertRaisesRegex(
                        independent_validator.PersonaV2SourceSemanticMembershipPackageValidationError,
                        "changed during provider callback",
                    ):
                        independent_validator.validate_source_semantic_membership_package(
                            catalog,
                            suite,
                            origins,
                            profiles,
                            mutating_provider,
                            mutating_provider,
                            mutating_provider,
                            source_suite=source_suite,
                            source_origin_manifests=source_origins,
                            source_profile_manifests=source_profiles,
                            source_shard_body_provider=mutating_provider,
                        )

    def test_digest_rethreaded_metadata_tamper_fails_before_body_access(self):
        base_origins, base_profiles, base_suite = self._full_package_values()

        def run_case(label, mutate):
            catalog = copy.deepcopy(self.catalog)
            origins = copy.deepcopy(base_origins)
            profiles = copy.deepcopy(base_profiles)
            suite = copy.deepcopy(base_suite)
            mutate(catalog, origins, profiles, suite)
            requests = []

            def forbidden_provider(*coordinates):
                requests.append(coordinates)
                return b""

            with self.subTest(label=label):
                with self.assertRaises(
                    independent_validator.PersonaV2SourceSemanticMembershipPackageValidationError
                ):
                    self._validate_full_package(
                        catalog,
                        suite,
                        origins,
                        profiles,
                        compact_provider=forbidden_provider,
                        context_provider=forbidden_provider,
                        membership_provider=forbidden_provider,
                        source_provider=forbidden_provider,
                    )
                self.assertEqual(requests, [])

        def catalog_foreign_fact(catalog, origins, profiles, suite):
            target = next(
                row
                for row in catalog["fact_profiles"]
                if row["persona_id"] == "p01"
                and row["profile_kind"] == "w0-singleton"
            )
            foreign = fact_graph.build_fact_graph("p02")["graphs"][0]["facts"][0]
            target["present_fact_ids"] = [foreign["fact_id"]]
            target["synthetic_entity_ids"] = [foreign["subject_entity_id"]]
            _rethread_package(catalog, suite, origins, profiles)

        run_case("foreign-fact", catalog_foreign_fact)

        def catalog_w0_absent(catalog, origins, profiles, suite):
            target = next(
                row
                for row in catalog["fact_profiles"]
                if row["persona_id"] == "p01"
                and row["profile_kind"] == "w0-singleton"
            )
            graph = next(
                row
                for row in fact_graph.build_fact_graph("p01")["graphs"]
                if row["graph_id"] == target["graph_id"]
            )
            absent = next(
                fact
                for fact in graph["facts"]
                if next(
                    state["state"]
                    for state in fact["visibility_by_checkpoint"]
                    if state["checkpoint"] == "W0"
                )
                != "current"
            )
            target["present_fact_ids"] = [absent["fact_id"]]
            target["synthetic_entity_ids"] = [absent["subject_entity_id"]]
            _rethread_package(catalog, suite, origins, profiles)

        run_case("w0-absent-fact", catalog_w0_absent)

        def catalog_branch_collapse(catalog, origins, profiles, suite):
            branch_a = next(
                row
                for row in catalog["fact_profiles"]
                if row["persona_id"] == "p01"
                and row["profile_kind"] == "conflict-branch"
                and row["branch_role"] == "a"
            )
            branch_b = next(
                row
                for row in catalog["fact_profiles"]
                if row["persona_id"] == "p01"
                and row["profile_kind"] == "conflict-branch"
                and row["branch_role"] == "b"
                and row["graph_id"] == branch_a["graph_id"]
            )
            branch_b["present_fact_ids"] = copy.deepcopy(
                branch_a["present_fact_ids"]
            )
            branch_b["synthetic_entity_ids"] = copy.deepcopy(
                branch_a["synthetic_entity_ids"]
            )
            _rethread_package(catalog, suite, origins, profiles)

        run_case("conflict-a-b-collapse", catalog_branch_collapse)

        def query_alias(catalog, origins, profiles, suite):
            catalog["semantic_profiles"][0]["query_alias"] = "forbidden"
            _rethread_package(catalog, suite, origins, profiles)

        run_case("query-alias", query_alias)

        for binding_name in (
            "persona-v2-source-inventory-origin-manifest",
            "persona-v2-overlay-reservation-origin",
            "persona-v2-fact-graph",
        ):

            def binding_swap(
                catalog,
                origins,
                profiles,
                suite,
                binding_name=binding_name,
            ):
                p01 = next(
                    row
                    for row in origins
                    if row["persona_id"] == "p01" and row["origin"] == "pilot"
                )
                p02 = next(
                    row
                    for row in origins
                    if row["persona_id"] == "p02" and row["origin"] == "pilot"
                )
                p01_index = next(
                    index
                    for index, row in enumerate(p01["input_bindings"])
                    if row["name"] == binding_name
                )
                donor = next(
                    row for row in p02["input_bindings"] if row["name"] == binding_name
                )
                p01["input_bindings"][p01_index] = copy.deepcopy(donor)
                _rethread_package(catalog, suite, origins, profiles)

            run_case(f"binding-swap-{binding_name}", binding_swap)

        def pilot_reuse_swap(catalog, origins, profiles, suite):
            _rethread_package(catalog, suite, origins, profiles)
            full = next(
                row
                for row in profiles
                if row["persona_id"] == "p01" and row["profile"] == "full"
            )
            full["origin_manifest_bindings"].reverse()
            suite_binding = next(
                row
                for row in suite["profile_manifest_bindings"]
                if row["persona_id"] == "p01" and row["profile"] == "full"
            )
            _refresh_binding(
                suite_binding, full, canonical=package.canonical_json_bytes
            )

        run_case("pilot-reuse-profile-swap", pilot_reuse_swap)

        def suite_ledger(catalog, origins, profiles, suite):
            ledger = suite["persona_current_component_byte_ledgers"][0]
            ledger["current_component_bytes"] += 1
            ledger["headroom_bytes"] -= 1

        run_case("suite-ledger", suite_ledger)

        def suite_authority(catalog, origins, profiles, suite):
            suite["authority"][next(iter(sorted(suite["authority"])))] = True

        run_case("suite-authority", suite_authority)

    def test_cross_review_upstream_shape_and_frozen_pin_tamper_is_metadata_first(self):
        base_origins, base_profiles, base_suite = self._full_package_values()
        base_source_origins, base_source_profiles, base_source_suite = (
            self._upstream_source_values()
        )

        def assert_rejected_without_providers(
            *,
            catalog=None,
            suite=None,
            origins=None,
            profiles=None,
            source_suite=None,
            source_origins=None,
            source_profiles=None,
        ):
            requests = []

            def forbidden_provider(*coordinates):
                requests.append(coordinates)
                return b""

            with self.assertRaises(
                independent_validator.PersonaV2SourceSemanticMembershipPackageValidationError
            ):
                self._validate_full_package(
                    catalog if catalog is not None else self.catalog,
                    suite if suite is not None else base_suite,
                    origins if origins is not None else base_origins,
                    profiles if profiles is not None else base_profiles,
                    compact_provider=forbidden_provider,
                    context_provider=forbidden_provider,
                    membership_provider=forbidden_provider,
                    source_provider=forbidden_provider,
                    source_suite_override=(
                        source_suite
                        if source_suite is not None
                        else base_source_suite
                    ),
                    source_origins_override=(
                        source_origins
                        if source_origins is not None
                        else base_source_origins
                    ),
                    source_profiles_override=(
                        source_profiles
                        if source_profiles is not None
                        else base_source_profiles
                    ),
                )
            self.assertEqual(requests, [])

        catalog = copy.deepcopy(self.catalog)
        origins = copy.deepcopy(base_origins)
        profiles = copy.deepcopy(base_profiles)
        suite = copy.deepcopy(base_suite)
        target = origins[0]
        target["body_descriptor"]["body_sha256"] = "0" * 64
        _rethread_package(catalog, suite, origins, profiles)
        target_raw = package.canonical_json_bytes(target)
        target_sha = hashlib.sha256(target_raw).hexdigest()
        self.assertNotEqual(
            hashlib.sha256(package.canonical_json_bytes(suite)).hexdigest(),
            EXPECTED_SUITE_SHA256,
        )
        self.assertEqual(
            next(
                row
                for row in suite["origin_manifest_bindings"]
                if row["persona_id"] == target["persona_id"]
                and row["origin"] == target["origin"]
            )["sha256"],
            target_sha,
        )
        for profile in profiles:
            if profile["persona_id"] != target["persona_id"]:
                continue
            binding = next(
                (
                    row
                    for row in profile["origin_manifest_bindings"]
                    if row["origin"] == target["origin"]
                ),
                None,
            )
            if binding is not None:
                self.assertEqual(binding["sha256"], target_sha)
            profile_sha = hashlib.sha256(
                package.canonical_json_bytes(profile)
            ).hexdigest()
            self.assertEqual(
                next(
                    row
                    for row in suite["profile_manifest_bindings"]
                    if row["persona_id"] == profile["persona_id"]
                    and row["profile"] == profile["profile"]
                )["sha256"],
                profile_sha,
            )
        assert_rejected_without_providers(
            catalog=catalog,
            suite=suite,
            origins=origins,
            profiles=profiles,
        )

        source_origins = copy.deepcopy(base_source_origins)
        self.assertIn("persona_id", source_origins[0])
        self.assertIn("origin", source_origins[0])
        del source_origins[0]["artifact_kind"]
        assert_rejected_without_providers(source_origins=source_origins)

        source_suite_mutations = (
            ("missing-artifact-kind", lambda value: value.pop("artifact_kind")),
            ("missing-artifact-schema", lambda value: value.pop("artifact_schema")),
            (
                "changed-artifact-kind",
                lambda value: value.__setitem__(
                    "artifact_kind", "not-a-source-inventory-suite"
                ),
            ),
            (
                "changed-artifact-schema",
                lambda value: value.__setitem__(
                    "artifact_schema", "kio.invalid-source-suite/v999"
                ),
            ),
        )
        for label, mutate in source_suite_mutations:
            with self.subTest(label=label):
                source_suite = copy.deepcopy(base_source_suite)
                mutate(source_suite)
                assert_rejected_without_providers(source_suite=source_suite)

    def test_one_origin_independent_body_validation_rejects_bounded_tamper(self):
        catalog_projection = independent_validator._validate_catalog(self.catalog)
        origin_manifest = package.build_source_semantic_membership_origin_manifest(
            "p01", "pilot"
        )
        source_manifest = source_package.build_source_intent_origin_manifest(
            "p01", "pilot"
        )
        independent_validator._prevalidate_origin_manifest(
            origin_manifest,
            persona_id="p01",
            origin="pilot",
            catalog=self.catalog,
            catalog_projection=catalog_projection,
            source_manifest=source_manifest,
        )
        origin_projection = independent_validator._origin_reservation_projection(
            "p01",
            "pilot",
            catalog_projection["fact_profiles"]["semantic_index"],
        )
        compact = package.source_semantic_membership_origin_body_bytes(
            "p01", "pilot"
        )
        context = package.expanded_content_context_shard_body_bytes(
            "p01", "pilot", 1
        )
        membership = package.expanded_fact_membership_shard_body_bytes(
            "p01", "pilot", 1
        )

        def flip_one_byte(body):
            mutated = bytearray(body)
            index = len(mutated) // 2
            mutated[index] = ord("0") if mutated[index] != ord("0") else ord("1")
            return bytes(mutated)

        compact_rows = _jsonl_rows(
            compact, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        )
        first_anchor = next(
            index
            for index, row in enumerate(compact_rows)
            if row["row_kind"] == "fact-semantic-anchor-override"
        )
        second_anchor = first_anchor + 1

        range_gap_rows = copy.deepcopy(compact_rows)
        range_gap_rows[0]["first_intent_key"] = range_gap_rows[0]["last_intent_key"]
        range_gap = _encode_jsonl(
            range_gap_rows, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        )
        missing_anchor_rows = copy.deepcopy(compact_rows)
        del missing_anchor_rows[first_anchor]
        missing_anchor = _encode_jsonl(
            missing_anchor_rows, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        )
        extra_anchor_rows = copy.deepcopy(compact_rows)
        extra_anchor_rows.insert(
            second_anchor, copy.deepcopy(extra_anchor_rows[first_anchor])
        )
        extra_anchor = _encode_jsonl(
            extra_anchor_rows, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        )
        duplicate_anchor_rows = copy.deepcopy(compact_rows)
        duplicate_anchor_rows[first_anchor] = copy.deepcopy(
            duplicate_anchor_rows[second_anchor]
        )
        duplicate_anchor = _encode_jsonl(
            duplicate_anchor_rows, cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
        )

        context_rows = _jsonl_rows(
            context, cap=package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF
        )
        language_topic_rows = copy.deepcopy(context_rows)
        language_topic_rows[0]["language"] = (
            "en" if language_topic_rows[0]["language"] != "en" else "ja"
        )
        persona_topics = [
            row["topic_id"]
            for row in self.catalog["semantic_topics"]
            if row["persona_id"] == "p01"
        ]
        language_topic_rows[0]["topic_id"] = next(
            topic
            for topic in persona_topics
            if topic != language_topic_rows[0]["topic_id"]
        )
        language_topic = _encode_jsonl(
            language_topic_rows,
            cap=package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
        )
        query_alias_rows = copy.deepcopy(context_rows)
        query_alias_rows[0]["query_alias"] = "forbidden"
        query_alias = _encode_jsonl(
            query_alias_rows,
            cap=package.MAX_EXPANDED_CONTEXT_ROW_BYTES_INCLUDING_LF,
        )
        bad_framing = context.replace(b"\n", b"\r\n")

        cases = {
            "compact-one-byte": (flip_one_byte(compact), context, membership),
            "context-one-byte": (compact, flip_one_byte(context), membership),
            "membership-one-byte": (
                compact,
                context,
                flip_one_byte(membership),
            ),
            "range-gap": (range_gap, context, membership),
            "missing-anchor": (missing_anchor, context, membership),
            "extra-anchor": (extra_anchor, context, membership),
            "duplicate-anchor": (duplicate_anchor, context, membership),
            "language-topic": (compact, language_topic, membership),
            "query-alias": (compact, query_alias, membership),
            "jsonl-framing": (compact, bad_framing, membership),
        }
        for label, (compact_body, context_body, membership_body) in cases.items():
            with self.subTest(label=label):
                with self.assertRaises(
                    independent_validator.PersonaV2SourceSemanticMembershipPackageValidationError
                ):
                    independent_validator._validate_origin_bodies(
                        origin_manifest,
                        source_manifest,
                        origin_projection,
                        catalog_projection,
                        compact_origin_body_provider=(
                            lambda _persona_id, _origin, body=compact_body: body
                        ),
                        expanded_context_body_provider=(
                            lambda _persona_id, _origin, _shard, body=context_body: body
                        ),
                        expanded_membership_body_provider=(
                            lambda _persona_id, _origin, _shard, body=membership_body: body
                        ),
                        source_shard_body_provider=self._source_body_provider,
                    )

    def test_full_suite_is_deterministic_and_build_rss_is_bounded(self):
        script = """
import hashlib
import json
import resource
import sys
from eval import persona_v2_source_semantic_membership_package as package

suite = package.build_source_semantic_membership_suite_descriptor()
suite_body = package.canonical_json_bytes(suite)

def body_pin(persona_id, origin):
    body = package.source_semantic_membership_origin_body_bytes(persona_id, origin)
    return [
        len(body),
        hashlib.sha256(body).hexdigest(),
        len(body.splitlines()),
        max(len(line) + 1 for line in body.splitlines()),
    ]

rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "p01_pilot": body_pin("p01", "pilot"),
    "p12_residual": body_pin("p12", "full-residual"),
    "rss_bytes": rss,
    "suite_bytes": len(suite_body),
    "suite_sha256": hashlib.sha256(suite_body).hexdigest(),
}, sort_keys=True))
"""
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONHASHSEED": "73",
                "TZ": "UTC",
                "LC_ALL": "C",
                "LANG": "C",
            }
        )
        output = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            text=True,
            timeout=600,
        )
        measured = json.loads(output)
        self.assertEqual(measured["suite_bytes"], EXPECTED_SUITE_BYTES)
        self.assertEqual(measured["suite_sha256"], EXPECTED_SUITE_SHA256)
        self.assertEqual(tuple(measured["p01_pilot"]), EXPECTED_P01_PILOT_BODY)
        self.assertEqual(
            tuple(measured["p12_residual"]), EXPECTED_P12_RESIDUAL_BODY
        )
        self.assertLessEqual(measured["rss_bytes"], MAX_BUILD_RSS_BYTES)

    def test_catalog_is_hashseed_timezone_and_locale_independent(self):
        script = (
            "from eval import persona_v2_source_semantic_membership_package as p;"
            "import hashlib;"
            "x=p.build_source_semantic_membership_catalog();"
            "b=p.canonical_json_bytes(x);"
            "print(len(b),hashlib.sha256(b).hexdigest())"
        )
        environment = dict(os.environ)
        environment.update(
            {
                "PYTHONHASHSEED": "73",
                "TZ": "UTC",
                "LC_ALL": "C",
                "LANG": "C",
            }
        )
        output = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            text=True,
            timeout=180,
        ).strip()
        self.assertEqual(
            output,
            f"{EXPECTED_CATALOG_BYTES} {EXPECTED_CATALOG_SHA256}",
        )


if __name__ == "__main__":
    unittest.main()
