"""Regression gates for the concrete persona-v2 overlay membership package.

This suite intentionally treats the concrete overlay as a downstream, planned
membership join.  It must not infer solved scope placement, rendered bytes,
observed chunks, query/oracle identity, history execution, or G0 authority.
"""

from __future__ import annotations

import copy
import hashlib
import inspect
import json
import os
import subprocess
import sys
import unittest
from collections import Counter, defaultdict
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import (
    persona_v2_concrete_overlay_membership_package_validator as independent_validator,
)
from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_contract as overlay_contract
from eval import persona_v2_overlay_reservation_layout as reservation
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_semantic_membership_package as semantic_package

try:
    from eval import persona_v2_concrete_overlay_membership_package as package
except ImportError:  # Producer lands after the producer-independent test skeleton.
    package = None


ConcreteValidationError = (
    independent_validator.PersonaV2ConcreteOverlayMembershipPackageValidationError
)


EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_CONTENT_RELATION_ROW_COUNT = 19_870
EXPECTED_ATTACHMENT_ROW_COUNT = 5_690
EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT = 2_100
EXPECTED_RICH_ROW_COUNT = 27_660
EXPECTED_DRAFT_PROJECTION_ROW_COUNT = 25_560
EXPECTED_OVERLAY_UNIQUE_SOURCE_REF_COUNT = 46_840
EXPECTED_UNIQUE_SOURCE_REF_WITH_ANCHORS_COUNT = 48_940
EXPECTED_OVERLAY_SOURCE_REFERENCE_OCCURRENCE_COUNT = 51_120
EXPECTED_JOINED_SOURCE_REFERENCE_OCCURRENCE_COUNT = 53_220
EXPECTED_EXACT_CLUSTER_COUNT = 5_080
EXPECTED_NEAR_CLUSTER_COUNT = 13_230
EXPECTED_CONFLICT_CLUSTER_COUNT = 1_560
EXPECTED_ATTACHMENT_EXACT_OVERLAP_COUNT = 1_390
EXPECTED_ATTACHMENT_HOST_COUNT = 2_800
MAX_BUILD_RSS_BYTES = 384 * 2**20

CONTENT_ROW_KIND = "content-relation-membership"
ATTACHMENT_ROW_KIND = "attachment-membership"
ANCHOR_ROW_KIND = "semantic-anchor-membership"
RELATION_ORDER = ("exact-duplicate", "near-revision", "conflict-copy")

CONTENT_ROW_FIELDS = frozenset(
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
ANCHOR_ROW_FIELDS = frozenset(
    {
        "fact_profile_id",
        "intent_key",
        "row_kind",
        "semantic_anchor_slot_ordinal",
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

# Frozen only after the public independent validator accepted the complete
# package under the 384 MiB RSS ceiling.
EXPECTED_SUITE_BYTES = 51_133
EXPECTED_SUITE_SHA256 = (
    "129eb05bd2331996742d69489f270f1012855d16cf8e47d5bd991a1b67305737"
)
EXPECTED_P01_PILOT_BODY = (
    87_203,
    "a288ce79d46d7945d87a0837d455577fd1873ac9ec9a91ac6b30d9bf0c70efe9",
    243,
    587,
)
EXPECTED_P12_RESIDUAL_BODY = (
    985_356,
    "74372f418a36dd0fa37f2146e05d03c5d14167c8856a1a3dc03f339934bafc0d",
    1_836,
    632,
)

PROHIBITED_IDENTITY_TOKENS = frozenset(
    {
        "answer",
        "chunk",
        "final",
        "materialization",
        "oracle",
        "query",
        "raw_hash",
        "relevance",
        "retrieval",
        "scope_key",
        "solution",
    }
)


def _canonical(value, *, label="concrete overlay test value", max_bytes=8 * 2**20):
    return artifact_common.canonical_json_bytes(
        value,
        label=label,
        max_bytes=max_bytes,
    )


def _jsonl_rows(body, *, row_cap):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        raise AssertionError("canonical JSONL body must be non-empty and LF-terminated")
    if b"\r" in body or body.endswith(b"\n\n"):
        raise AssertionError("canonical JSONL body has invalid framing")
    rows = []
    for raw in body.splitlines():
        if len(raw) + 1 > row_cap:
            raise AssertionError("canonical JSONL row exceeds its LF-inclusive cap")
        row = json.loads(raw)
        if _canonical(row, max_bytes=row_cap - 1) != raw:
            raise AssertionError("JSONL row is not canonical JSON")
        rows.append(row)
    return rows


def _encode_jsonl(rows, *, row_cap):
    parts = []
    for row in rows:
        raw = _canonical(
            row,
            label="tampered concrete overlay row",
            max_bytes=row_cap - 1,
        )
        if len(raw) + 1 > row_cap:
            raise AssertionError("tampered row exceeds the test contract")
        parts.append(raw + b"\n")
    return b"".join(parts)


def _contains_prohibited_identity(value):
    if type(value) is dict:
        for key, item in value.items():
            normalized = key.lower().replace("-", "_")
            if any(token in normalized for token in PROHIBITED_IDENTITY_TOKENS):
                return True
            if _contains_prohibited_identity(item):
                return True
        return False
    if type(value) is list:
        return any(_contains_prohibited_identity(item) for item in value)
    if type(value) is str:
        normalized = value.lower().replace("-", "_")
        return any(token in normalized for token in PROHIBITED_IDENTITY_TOKENS)
    return False


def _ascii(value, *, label):
    if type(value) is not str:
        raise AssertionError(f"{label} must be an exact string")
    try:
        return value.encode("ascii", "strict")
    except UnicodeEncodeError as error:
        raise AssertionError(f"{label} must be ASCII") from error


def _rich_row_sort_key(row):
    if type(row) is not dict:
        raise AssertionError("rich concrete overlay row must be an object")
    kind = row.get("row_kind")
    if kind == CONTENT_ROW_KIND:
        if set(row) != CONTENT_ROW_FIELDS:
            raise AssertionError("content row fields differ from the exact schema")
        relation = row["relation_kind"]
        if relation not in RELATION_ORDER:
            raise AssertionError("content row has an unknown relation kind")
        cluster = _ascii(row["cluster_key"], label="cluster key")
        return (0, RELATION_ORDER.index(relation), cluster)
    if kind == ATTACHMENT_ROW_KIND:
        if set(row) != ATTACHMENT_ROW_FIELDS:
            raise AssertionError("attachment row fields differ from the exact schema")
        attachment = _ascii(row["attachment_key"], label="attachment key")
        return (1, 0, attachment)
    if kind == ANCHOR_ROW_KIND:
        if set(row) != ANCHOR_ROW_FIELDS:
            raise AssertionError("anchor row fields differ from the exact schema")
        ordinal = row["semantic_anchor_slot_ordinal"]
        if type(ordinal) is not int or ordinal < 1:
            raise AssertionError("semantic anchor ordinal must be a positive integer")
        intent = _ascii(row["intent_key"], label="anchor intent key")
        return (2, ordinal, intent)
    raise AssertionError(f"unknown concrete overlay row kind: {kind!r}")


def _serialized_rich_row_sort_key(row):
    key = _rich_row_sort_key(row)
    return [key[0], key[1], key[2].decode("ascii")]


def _project_rich_row_to_draft(row):
    """Project one rich relation/attachment row into the frozen minimal draft."""

    kind = row.get("row_kind") if type(row) is dict else None
    if kind == CONTENT_ROW_KIND:
        if set(row) != CONTENT_ROW_FIELDS:
            raise AssertionError("content row fields differ from the exact schema")
        return {
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
    if kind == ATTACHMENT_ROW_KIND:
        if set(row) != ATTACHMENT_ROW_FIELDS:
            raise AssertionError("attachment row fields differ from the exact schema")
        return {
            "attachment_key": row["attachment_key"],
            "decoded_payload_equivalence_key": row[
                "decoded_payload_equivalence_key"
            ],
            "host_intent_key": row["host_intent_key"],
            "member_ordinal": row["member_ordinal"],
            "row_kind": ATTACHMENT_ROW_KIND,
            "search_participation_profile_id": row[
                "search_participation_requirement_id"
            ],
            "standalone_member_intent_key": row[
                "standalone_member_intent_key"
            ],
        }
    if kind == ANCHOR_ROW_KIND:
        return None
    raise AssertionError(f"unknown concrete overlay row kind: {kind!r}")


def _draft_projection(rows):
    projected = []
    previous = None
    for row in rows:
        key = _rich_row_sort_key(row)
        if previous is not None and key <= previous:
            raise AssertionError("rich concrete overlay rows are not strictly sorted")
        previous = key
        draft = _project_rich_row_to_draft(row)
        if draft is not None:
            projected.append(draft)
    return projected


def _body_receipt(body, *, row_cap):
    rows = _jsonl_rows(body, row_cap=row_cap)
    return {
        "body_bytes": len(body),
        "body_sha256": hashlib.sha256(body).hexdigest(),
        "maximum_row_bytes_including_lf": max(
            len(line) + 1 for line in body.splitlines()
        ),
        "row_count": len(rows),
    }


def _flip_one_body_byte(body):
    if type(body) is not bytes or len(body) < 2:
        raise AssertionError("tamper body must contain at least one JSON byte and LF")
    mutated = bytearray(body)
    index = (len(mutated) - 1) // 2
    if mutated[index] in b"\n\r":
        index = 0
    mutated[index] = ord("0") if mutated[index] != ord("0") else ord("1")
    return bytes(mutated)


def _refresh_binding(binding, value):
    """Refresh an existing target binding without changing its exact role."""

    raw = package.canonical_json_bytes(value)
    binding["canonical_bytes"] = len(raw)
    binding["sha256"] = hashlib.sha256(raw).hexdigest()


def _rethread_target_metadata(origins, profiles, suite):
    """Re-hash target wrappers after an intentional same-shape mutation."""

    origin_by_key = {
        (row["persona_id"], row["origin"]): row for row in origins
    }
    profile_by_key = {
        (row["persona_id"], row["profile"]): row for row in profiles
    }
    for profile in profiles:
        composed = [
            origin_by_key[(profile["persona_id"], origin)]
            for origin in profile["origin_order"]
        ]
        profile["shard_descriptors"] = [
            copy.deepcopy(descriptor)
            for origin in composed
            for descriptor in origin["shard_descriptors"]
        ]
        for binding, origin in zip(
            profile["origin_manifest_bindings"], composed, strict=True
        ):
            _refresh_binding(binding, origin)

    for binding in suite["origin_manifest_bindings"]:
        _refresh_binding(
            binding,
            origin_by_key[(binding["persona_id"], binding["origin"])],
        )
    for binding in suite["profile_manifest_bindings"]:
        _refresh_binding(
            binding,
            profile_by_key[(binding["persona_id"], binding["profile"])],
        )


def _descriptor_rethreaded_for_body(manifest, body):
    """Return a copy whose descriptor authenticates ``body`` exactly."""

    value = copy.deepcopy(manifest)
    descriptor = value["shard_descriptors"][0]
    descriptor["body_bytes"] = len(body)
    descriptor["body_sha256"] = hashlib.sha256(body).hexdigest()
    raw_rows = body.splitlines()
    if raw_rows and b"\r" not in body:
        try:
            rows = [json.loads(raw) for raw in raw_rows]
        except (UnicodeDecodeError, json.JSONDecodeError):
            return value
        descriptor["row_count"] = len(rows)
        descriptor["maximum_row_bytes_including_lf"] = max(
            len(raw) + 1 for raw in raw_rows
        )
        descriptor["first_row_sort_key"] = _serialized_rich_row_sort_key(rows[0])
        descriptor["last_row_sort_key"] = _serialized_rich_row_sort_key(rows[-1])
    return value


class PersonaV2ConcreteOverlayMembershipPackageTests(unittest.TestCase):
    """The expensive full-package build is lazy and shared exactly once."""

    origins = None
    profiles = None
    suite = None
    bodies = None
    upstream = None
    origin_harness = None

    @classmethod
    def _ensure_package(cls):
        if cls.suite is not None:
            return
        if package is None:  # pragma: no cover - only during parallel landing.
            raise AssertionError("concrete overlay producer has not landed")
        origins = []
        bodies = {}
        for persona_id in envelope.PERSONA_IDS:
            for origin in package.ORIGIN_ORDER:
                manifest = package.build_concrete_overlay_membership_origin_manifest(
                    persona_id, origin
                )
                origins.append(manifest)
                # Capture each body while the producer's bounded origin cache is
                # still hot.  The suite builder intentionally releases it.
                for descriptor in manifest["shard_descriptors"]:
                    coordinate = (persona_id, origin, descriptor["shard_index"])
                    bodies[coordinate] = (
                        package.concrete_overlay_membership_shard_body_bytes(
                            *coordinate
                        )
                    )
        profiles = [
            package.build_concrete_overlay_membership_profile_manifest(
                persona_id, profile
            )
            for persona_id in envelope.PERSONA_IDS
            for profile in package.PROFILE_ORDER
        ]
        suite = package.build_concrete_overlay_membership_suite_descriptor()
        cls.origins = origins
        cls.profiles = profiles
        cls.suite = suite
        cls.bodies = bodies

    @classmethod
    def _ensure_upstream(cls):
        if cls.upstream is not None:
            return
        reservation_origins = [
            reservation.build_overlay_reservation_origin(persona_id, origin)
            for persona_id in envelope.PERSONA_IDS
            for origin in package.ORIGIN_ORDER
        ]
        source_origins = [
            source_package.build_source_intent_origin_manifest(persona_id, origin)
            for persona_id in envelope.PERSONA_IDS
            for origin in package.ORIGIN_ORDER
        ]
        source_profiles = [
            source_package.build_source_intent_profile_manifest(persona_id, profile)
            for persona_id in envelope.PERSONA_IDS
            for profile in package.PROFILE_ORDER
        ]
        semantic_origins = [
            semantic_package.build_source_semantic_membership_origin_manifest(
                persona_id, origin
            )
            for persona_id in envelope.PERSONA_IDS
            for origin in package.ORIGIN_ORDER
        ]
        semantic_profiles = [
            semantic_package.build_source_semantic_membership_profile_manifest(
                persona_id, profile
            )
            for persona_id in envelope.PERSONA_IDS
            for profile in package.PROFILE_ORDER
        ]
        cls.upstream = {
            "overlay_contract_value": overlay_contract.build_overlay_contract(),
            "reservation_origins": reservation_origins,
            "reservation_suite": reservation.build_overlay_reservation_suite(),
            "semantic_catalog": (
                semantic_package.build_source_semantic_membership_catalog()
            ),
            "semantic_origins": semantic_origins,
            "semantic_profiles": semantic_profiles,
            "semantic_suite": (
                semantic_package.build_source_semantic_membership_suite_descriptor()
            ),
            "source_origins": source_origins,
            "source_profiles": source_profiles,
            "source_suite": source_package.build_source_intent_suite_descriptor(),
        }

    @classmethod
    def _ensure_origin_harness(cls):
        """Cache the authenticated p01/pilot upstream bodies for tamper cases."""

        if cls.origin_harness is not None:
            return
        persona_id = "p01"
        origin = "pilot"
        target_manifest = package.build_concrete_overlay_membership_origin_manifest(
            persona_id, origin
        )
        target_body = package.concrete_overlay_membership_shard_body_bytes(
            persona_id, origin, 0
        )
        source_manifest = source_package.build_source_intent_origin_manifest(
            persona_id, origin
        )
        catalog = semantic_package.build_source_semantic_membership_catalog()
        body_maps = {"source": {}, "context": {}, "membership": {}}
        for descriptor in source_manifest["shard_descriptors"]:
            shard_ordinal = descriptor["shard_ordinal"]
            coordinate = (persona_id, origin, shard_ordinal)
            body_maps["source"][coordinate] = (
                source_package.source_intent_shard_body_bytes(*coordinate)
            )
            body_maps["context"][coordinate] = (
                semantic_package.expanded_content_context_shard_body_bytes(
                    *coordinate
                )
            )
            body_maps["membership"][coordinate] = (
                semantic_package.expanded_fact_membership_shard_body_bytes(
                    *coordinate
                )
            )

        providers = {}
        for label in ("source", "context", "membership"):
            bodies = body_maps[label]
            provider = independent_validator._DigestRecordingProvider(
                lambda *coordinate, bodies=bodies: bodies[tuple(coordinate)],
                f"test {label}",
            )
            for coordinate in bodies:
                provider(*coordinate)
            providers[label] = provider

        fact_by_id, semantic_by_source = (
            independent_validator._profile_rows_by_id(catalog)
        )
        cls.origin_harness = {
            "body": target_body,
            "catalog": catalog,
            "fact_by_id": fact_by_id,
            "manifest": target_manifest,
            "membership_provider": providers["membership"],
            "reservation": reservation.build_overlay_reservation_origin(
                persona_id, origin
            ),
            "semantic_by_source": semantic_by_source,
            "source_manifest": source_manifest,
            "source_provider": providers["source"],
            "context_provider": providers["context"],
        }

    @classmethod
    def _validate_one_origin(cls, manifest, body):
        cls._ensure_origin_harness()
        harness = cls.origin_harness
        target_provider = independent_validator._DigestRecordingProvider(
            lambda persona_id, origin, shard_index: body,
            "test concrete overlay",
        )
        return independent_validator._validate_one_origin_body(
            manifest,
            harness["reservation"],
            harness["source_manifest"],
            target_provider=target_provider,
            source_provider=harness["source_provider"],
            context_provider=harness["context_provider"],
            membership_provider=harness["membership_provider"],
            fact_by_id=harness["fact_by_id"],
            semantic_by_source=harness["semantic_by_source"],
        )

    @classmethod
    def _validate_public(
        cls,
        *,
        suite=None,
        origins=None,
        profiles=None,
        upstream_overrides=None,
        providers=None,
    ):
        cls._ensure_package()
        cls._ensure_upstream()
        upstream = dict(cls.upstream)
        if upstream_overrides:
            upstream.update(upstream_overrides)
        body_providers = {
            "membership": package.concrete_overlay_membership_shard_body_bytes,
            "semantic_compact": (
                semantic_package.source_semantic_membership_origin_body_bytes
            ),
            "semantic_context": (
                semantic_package.expanded_content_context_shard_body_bytes
            ),
            "semantic_membership": (
                semantic_package.expanded_fact_membership_shard_body_bytes
            ),
            "source": source_package.source_intent_shard_body_bytes,
        }
        if providers:
            body_providers.update(providers)
        return independent_validator.validate_concrete_overlay_membership_package(
            suite if suite is not None else cls.suite,
            origins if origins is not None else cls.origins,
            profiles if profiles is not None else cls.profiles,
            body_providers["membership"],
            overlay_contract_value=upstream["overlay_contract_value"],
            reservation_suite=upstream["reservation_suite"],
            reservation_origin_artifacts=upstream["reservation_origins"],
            semantic_catalog=upstream["semantic_catalog"],
            semantic_suite=upstream["semantic_suite"],
            semantic_origin_manifests=upstream["semantic_origins"],
            semantic_profile_manifests=upstream["semantic_profiles"],
            semantic_compact_origin_body_provider=body_providers[
                "semantic_compact"
            ],
            semantic_expanded_context_body_provider=body_providers[
                "semantic_context"
            ],
            semantic_expanded_membership_body_provider=body_providers[
                "semantic_membership"
            ],
            source_suite=upstream["source_suite"],
            source_origin_manifests=upstream["source_origins"],
            source_profile_manifests=upstream["source_profiles"],
            source_shard_body_provider=body_providers["source"],
        )

    def test_contract_constants_are_distinct_and_exact(self):
        self.assertEqual(
            EXPECTED_SUITE_BYTES,
            independent_validator.EXPECTED_SUITE_DESCRIPTOR_BYTES,
        )
        self.assertEqual(
            EXPECTED_SUITE_SHA256,
            independent_validator.EXPECTED_SUITE_SHA256,
        )
        self.assertEqual(
            EXPECTED_P01_PILOT_BODY,
            (
                87_203,
                "a288ce79d46d7945d87a0837d455577fd1873ac9ec9a91ac6b30d9bf0c70efe9",
                243,
                587,
            ),
        )
        self.assertEqual(
            EXPECTED_P12_RESIDUAL_BODY,
            (
                985_356,
                "74372f418a36dd0fa37f2146e05d03c5d14167c8856a1a3dc03f339934bafc0d",
                1_836,
                632,
            ),
        )
        self.assertEqual(
            EXPECTED_CONTENT_RELATION_ROW_COUNT
            + EXPECTED_ATTACHMENT_ROW_COUNT
            + EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT,
            EXPECTED_RICH_ROW_COUNT,
        )
        self.assertEqual(
            EXPECTED_CONTENT_RELATION_ROW_COUNT + EXPECTED_ATTACHMENT_ROW_COUNT,
            EXPECTED_DRAFT_PROJECTION_ROW_COUNT,
        )
        self.assertEqual(
            EXPECTED_OVERLAY_UNIQUE_SOURCE_REF_COUNT
            + EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT,
            EXPECTED_UNIQUE_SOURCE_REF_WITH_ANCHORS_COUNT,
        )
        self.assertEqual(
            2 * EXPECTED_CONTENT_RELATION_ROW_COUNT
            + EXPECTED_ATTACHMENT_HOST_COUNT
            + EXPECTED_ATTACHMENT_ROW_COUNT
            - EXPECTED_ATTACHMENT_EXACT_OVERLAP_COUNT,
            EXPECTED_OVERLAY_UNIQUE_SOURCE_REF_COUNT,
        )
        self.assertEqual(
            CONTENT_ROW_FIELDS, independent_validator.CONTENT_RELATION_ROW_FIELDS
        )
        self.assertEqual(
            ATTACHMENT_ROW_FIELDS, independent_validator.ATTACHMENT_ROW_FIELDS
        )
        self.assertEqual(
            ANCHOR_ROW_FIELDS, independent_validator.SEMANTIC_ANCHOR_ROW_FIELDS
        )

        content = {
            "anchor_fact_profile_id": "p01-source-fact-profile-g01-normal-v2",
            "anchor_intent_key": "p01-intent-pilot-syn-0001",
            "cluster_key": "p01-overlay-pilot-exact-duplicate-syn-0001",
            "derivative_fact_profile_id": "p01-source-fact-profile-g01-normal-v2",
            "derivative_intent_key": "p01-intent-pilot-syn-0002",
            "placement_class_requirement": "primary-to-primary",
            "relation_kind": "exact-duplicate",
            "row_kind": CONTENT_ROW_KIND,
            "search_participation_requirement_id": "content-relation-v2",
        }
        attachment = {
            "attachment_key": "p01-attachment-pilot-syn-0001",
            "content_relation_membership": "none",
            "decoded_payload_equivalence_key": (
                "p01-payload-pilot-syn-0003-attachment-member"
            ),
            "host_fact_profile_id": "p01-source-fact-profile-g01-normal-v2",
            "host_intent_key": "p01-intent-pilot-syn-0004",
            "host_member_count": 1,
            "member_ordinal": 1,
            "row_kind": ATTACHMENT_ROW_KIND,
            "search_participation_requirement_id": "attachment-structural-v2",
            "standalone_member_fact_profile_id": (
                "p01-source-fact-profile-g01-normal-v2"
            ),
            "standalone_member_intent_key": "p01-intent-pilot-syn-0003",
        }
        anchor = {
            "fact_profile_id": "p01-source-fact-profile-g01-f001-v2",
            "intent_key": "p01-intent-pilot-syn-0005",
            "row_kind": ANCHOR_ROW_KIND,
            "semantic_anchor_slot_ordinal": 1,
        }
        self.assertLess(_rich_row_sort_key(content), _rich_row_sort_key(attachment))
        self.assertLess(_rich_row_sort_key(attachment), _rich_row_sort_key(anchor))
        projection = _draft_projection([content, attachment, anchor])
        self.assertEqual(len(projection), 2)
        self.assertEqual(projection[0]["row_kind"], "content-relation")
        self.assertEqual(projection[1]["row_kind"], ATTACHMENT_ROW_KIND)
        self.assertNotIn("fact_profile_id", projection[0])
        self.assertFalse(
            any(
                _contains_prohibited_identity(row)
                for row in (content, attachment, anchor)
            )
        )

        body = _encode_jsonl(
            [content], row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF
        )
        receipt = _body_receipt(
            body,
            row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(receipt["row_count"], 1)
        self.assertNotEqual(_flip_one_body_byte(body), body)

    def test_provider_callback_target_and_upstream_metadata_mutation_are_rejected(self):
        self._ensure_package()
        self._ensure_upstream()

        for mutation_target in ("concrete-suite", "semantic-suite"):
            with self.subTest(mutation_target=mutation_target):
                suite = copy.deepcopy(self.suite)
                origins = copy.deepcopy(self.origins)
                profiles = copy.deepcopy(self.profiles)
                upstream = copy.deepcopy(self.upstream)
                target_opening_scope = suite["completion_scope"]
                semantic_opening_scope = upstream["semantic_suite"][
                    "completion_scope"
                ]

                def mutating_provider(*coordinate):
                    if mutation_target == "concrete-suite":
                        suite["completion_scope"] = (
                            "mutated-during-provider-callback"
                        )
                    else:
                        upstream["semantic_suite"]["completion_scope"] = (
                            "mutated-during-provider-callback"
                        )
                    return b""

                def detached_validation(*args, **kwargs):
                    self.assertIsNot(args[0], suite)
                    self.assertIsNot(
                        kwargs["semantic_suite"], upstream["semantic_suite"]
                    )
                    args[3]("p01", "pilot", 0)
                    self.assertEqual(
                        args[0]["completion_scope"], target_opening_scope
                    )
                    self.assertEqual(
                        kwargs["semantic_suite"]["completion_scope"],
                        semantic_opening_scope,
                    )
                    return True

                with mock.patch.object(
                    independent_validator,
                    "_validate_concrete_overlay_membership_package_snapshot",
                    side_effect=detached_validation,
                ):
                    with self.assertRaisesRegex(
                        ConcreteValidationError,
                        "changed during provider callback",
                    ):
                        self._validate_public(
                            suite=suite,
                            origins=origins,
                            profiles=profiles,
                            upstream_overrides=upstream,
                            providers={"membership": mutating_provider},
                        )

    def test_full_package_shape_semantics_pins_and_negative_authority(self):
        self._ensure_package()
        self.assertEqual(len(self.origins), EXPECTED_ORIGIN_COUNT)
        self.assertEqual(len(self.profiles), EXPECTED_PROFILE_COUNT)
        self.assertEqual(
            [(row["persona_id"], row["origin"]) for row in self.origins],
            [
                (persona_id, origin)
                for persona_id in envelope.PERSONA_IDS
                for origin in package.ORIGIN_ORDER
            ],
        )
        self.assertEqual(
            [(row["persona_id"], row["profile"]) for row in self.profiles],
            [
                (persona_id, profile)
                for persona_id in envelope.PERSONA_IDS
                for profile in package.PROFILE_ORDER
            ],
        )
        self.assertEqual(set(self.suite), package.SUITE_TOP_LEVEL_FIELDS)
        self.assertEqual(self.suite["artifact_kind"], package.SUITE_ARTIFACT_KIND)
        self.assertEqual(self.suite["artifact_schema"], package.SUITE_ARTIFACT_SCHEMA)
        self.assertIs(self.suite["g0_contract_frozen"], False)

        row_kind_counts = Counter()
        relation_counts = Counter()
        placement_counts = defaultdict(Counter)
        overlay_refs = set()
        anchor_refs = set()
        attachment_hosts = set()
        attachment_members = set()
        overlap_clusters = set()
        all_rows = 0
        all_body_bytes = 0
        maximum_row_bytes = 0

        for manifest in self.origins:
            self.assertEqual(set(manifest), package.ORIGIN_TOP_LEVEL_FIELDS)
            self.assertEqual(set(manifest["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(
                all(flag is False for flag in manifest["authority"].values())
            )
            self.assertIs(manifest["g0_contract_frozen"], False)
            self.assertEqual(len(manifest["shard_descriptors"]), 1)
            descriptor = manifest["shard_descriptors"][0]
            self.assertEqual(set(descriptor), SHARD_DESCRIPTOR_FIELDS)
            self.assertEqual(descriptor["shard_index"], 0)
            self.assertEqual(
                descriptor["file_name"],
                f"{manifest['persona_id']}-concrete-overlay-membership-"
                f"{manifest['origin']}-0000.jsonl",
            )
            body = self.bodies[
                (manifest["persona_id"], manifest["origin"], 0)
            ]
            rows = _jsonl_rows(body, row_cap=package.MAX_ROW_BYTES_INCLUDING_LF)
            self.assertEqual(len(rows), descriptor["row_count"])
            self.assertEqual(len(body), descriptor["body_bytes"])
            self.assertEqual(
                hashlib.sha256(body).hexdigest(), descriptor["body_sha256"]
            )
            self.assertEqual(
                max(len(line) + 1 for line in body.splitlines()),
                descriptor["maximum_row_bytes_including_lf"],
            )
            self.assertLessEqual(descriptor["row_count"], package.MAX_ROWS_PER_SHARD)
            self.assertLessEqual(descriptor["body_bytes"], package.MAX_SHARD_BODY_BYTES)
            self.assertLessEqual(
                descriptor["maximum_row_bytes_including_lf"],
                package.MAX_ROW_BYTES_INCLUDING_LF,
            )
            sort_keys = [_rich_row_sort_key(row) for row in rows]
            self.assertEqual(sort_keys, sorted(set(sort_keys)))
            self.assertEqual(
                descriptor["first_row_sort_key"],
                _serialized_rich_row_sort_key(rows[0]),
            )
            self.assertEqual(
                descriptor["last_row_sort_key"],
                _serialized_rich_row_sort_key(rows[-1]),
            )
            self.assertFalse(any(_contains_prohibited_identity(row) for row in rows))

            origin_hosts = defaultdict(list)
            origin_overlap_clusters = set()
            origin_overlay_refs = set()
            origin_anchor_refs = set()
            for row in rows:
                kind = row["row_kind"]
                row_kind_counts[kind] += 1
                if kind == CONTENT_ROW_KIND:
                    self.assertEqual(set(row), CONTENT_ROW_FIELDS)
                    relation = row["relation_kind"]
                    relation_counts[relation] += 1
                    placement_counts[relation][
                        row["placement_class_requirement"]
                    ] += 1
                    self.assertNotEqual(
                        row["anchor_intent_key"], row["derivative_intent_key"]
                    )
                    if relation == "conflict-copy":
                        self.assertNotEqual(
                            row["anchor_fact_profile_id"],
                            row["derivative_fact_profile_id"],
                        )
                    else:
                        self.assertEqual(
                            row["anchor_fact_profile_id"],
                            row["derivative_fact_profile_id"],
                        )
                    origin_overlay_refs.update(
                        (row["anchor_intent_key"], row["derivative_intent_key"])
                    )
                elif kind == ATTACHMENT_ROW_KIND:
                    self.assertEqual(set(row), ATTACHMENT_ROW_FIELDS)
                    host = row["host_intent_key"]
                    member = row["standalone_member_intent_key"]
                    self.assertNotEqual(host, member)
                    origin_hosts[host].append(row)
                    attachment_hosts.add(host)
                    attachment_members.add(member)
                    origin_overlay_refs.update((host, member))
                    if row["content_relation_membership"] != "none":
                        self.assertNotIn(
                            row["content_relation_membership"],
                            origin_overlap_clusters,
                        )
                        origin_overlap_clusters.add(
                            row["content_relation_membership"]
                        )
                elif kind == ANCHOR_ROW_KIND:
                    self.assertEqual(set(row), ANCHOR_ROW_FIELDS)
                    self.assertNotIn(row["intent_key"], origin_anchor_refs)
                    origin_anchor_refs.add(row["intent_key"])
                else:  # pragma: no cover - exact row-kind schema above.
                    self.fail(f"unknown rich row kind: {kind!r}")

            for host, member_rows in origin_hosts.items():
                declared = {row["host_member_count"] for row in member_rows}
                self.assertEqual(len(declared), 1, host)
                expected_count = next(iter(declared))
                self.assertEqual(len(member_rows), expected_count)
                self.assertEqual(
                    sorted(row["member_ordinal"] for row in member_rows),
                    list(range(1, expected_count + 1)),
                )
            self.assertTrue(origin_overlay_refs.isdisjoint(origin_anchor_refs))
            overlay_refs.update(origin_overlay_refs)
            anchor_refs.update(origin_anchor_refs)
            overlap_clusters.update(origin_overlap_clusters)

            draft_rows = _draft_projection(rows)
            draft_body = _encode_jsonl(
                draft_rows,
                row_cap=package.MAX_ROW_BYTES_INCLUDING_LF,
            )
            draft_receipt = manifest["draft_membership_projection_receipt"]
            self.assertEqual(
                set(draft_receipt), package.DRAFT_PROJECTION_RECEIPT_FIELDS
            )
            self.assertEqual(draft_receipt["body_bytes"], len(draft_body))
            self.assertEqual(
                draft_receipt["body_sha256"],
                hashlib.sha256(draft_body).hexdigest(),
            )
            self.assertEqual(draft_receipt["row_count"], len(draft_rows))
            rich_projected = [
                row for row in rows if row["row_kind"] != ANCHOR_ROW_KIND
            ]
            self.assertEqual(
                draft_receipt["first_row_sort_key"],
                _serialized_rich_row_sort_key(rich_projected[0]),
            )
            self.assertEqual(
                draft_receipt["last_row_sort_key"],
                _serialized_rich_row_sort_key(rich_projected[-1]),
            )
            self.assertEqual(
                draft_receipt["maximum_row_bytes_including_lf"],
                max(len(line) + 1 for line in draft_body.splitlines()),
            )
            self.assertEqual(
                manifest["summary"]["rich_row_count"], len(rows)
            )
            self.assertEqual(
                manifest["summary"]["overlay_membership_row_count"],
                len(draft_rows),
            )
            all_rows += len(rows)
            all_body_bytes += len(body)
            maximum_row_bytes = max(
                maximum_row_bytes,
                descriptor["maximum_row_bytes_including_lf"],
            )

        self.assertEqual(
            row_kind_counts,
            {
                CONTENT_ROW_KIND: EXPECTED_CONTENT_RELATION_ROW_COUNT,
                ATTACHMENT_ROW_KIND: EXPECTED_ATTACHMENT_ROW_COUNT,
                ANCHOR_ROW_KIND: EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT,
            },
        )
        self.assertEqual(
            relation_counts,
            {
                "exact-duplicate": EXPECTED_EXACT_CLUSTER_COUNT,
                "near-revision": EXPECTED_NEAR_CLUSTER_COUNT,
                "conflict-copy": EXPECTED_CONFLICT_CLUSTER_COUNT,
            },
        )
        self.assertEqual(
            placement_counts,
            {
                "exact-duplicate": Counter(
                    {
                        "primary-to-primary": 2_184,
                        "primary-to-secondary": 1_625,
                        "secondary-to-primary": 796,
                        "secondary-to-secondary": 475,
                    }
                ),
                "near-revision": Counter(
                    {
                        "primary-to-primary": 5_825,
                        "primary-to-secondary": 4_163,
                        "secondary-to-primary": 2_047,
                        "secondary-to-secondary": 1_195,
                    }
                ),
                "conflict-copy": Counter(
                    {
                        "primary-to-primary": 659,
                        "primary-to-secondary": 500,
                        "secondary-to-primary": 252,
                        "secondary-to-secondary": 149,
                    }
                ),
            },
        )
        self.assertEqual(len(overlay_refs), EXPECTED_OVERLAY_UNIQUE_SOURCE_REF_COUNT)
        self.assertEqual(len(anchor_refs), EXPECTED_SEMANTIC_ANCHOR_ROW_COUNT)
        self.assertTrue(overlay_refs.isdisjoint(anchor_refs))
        self.assertEqual(
            len(overlay_refs | anchor_refs),
            EXPECTED_UNIQUE_SOURCE_REF_WITH_ANCHORS_COUNT,
        )
        self.assertEqual(len(attachment_hosts), EXPECTED_ATTACHMENT_HOST_COUNT)
        self.assertEqual(len(attachment_members), EXPECTED_ATTACHMENT_ROW_COUNT)
        self.assertEqual(
            len(overlap_clusters), EXPECTED_ATTACHMENT_EXACT_OVERLAP_COUNT
        )
        self.assertEqual(all_rows, EXPECTED_RICH_ROW_COUNT)

        summary = self.suite["summary"]
        self.assertEqual(summary["shard_body_bytes"], all_body_bytes)
        self.assertEqual(summary["maximum_row_bytes_including_lf"], maximum_row_bytes)
        self.assertEqual(
            summary["overlay_source_reference_occurrence_count"],
            EXPECTED_OVERLAY_SOURCE_REFERENCE_OCCURRENCE_COUNT,
        )
        self.assertEqual(
            summary["joined_source_reference_occurrence_count"],
            EXPECTED_JOINED_SOURCE_REFERENCE_OCCURRENCE_COUNT,
        )
        self.assertEqual(
            summary["draft_projection_row_count"],
            EXPECTED_DRAFT_PROJECTION_ROW_COUNT,
        )
        self.assertEqual(summary["origin_manifest_count"], EXPECTED_ORIGIN_COUNT)
        self.assertEqual(summary["profile_manifest_count"], EXPECTED_PROFILE_COUNT)
        self.assertEqual(summary["shard_count"], EXPECTED_ORIGIN_COUNT)

        profile_by_key = {
            (row["persona_id"], row["profile"]): row for row in self.profiles
        }
        for persona_id in envelope.PERSONA_IDS:
            pilot = profile_by_key[(persona_id, "pilot")]
            full = profile_by_key[(persona_id, "full")]
            self.assertEqual(set(pilot), package.PROFILE_TOP_LEVEL_FIELDS)
            self.assertEqual(set(full), package.PROFILE_TOP_LEVEL_FIELDS)
            self.assertEqual(pilot["origin_order"], ["pilot"])
            self.assertEqual(full["origin_order"], list(package.ORIGIN_ORDER))
            self.assertEqual(
                pilot["origin_manifest_bindings"],
                full["origin_manifest_bindings"][:1],
            )
            self.assertEqual(
                pilot["shard_descriptors"],
                full["shard_descriptors"][: len(pilot["shard_descriptors"])],
            )
            for manifest in (pilot, full):
                self.assertEqual(set(manifest["authority"]), package.AUTHORITY_FIELDS)
                self.assertTrue(
                    all(flag is False for flag in manifest["authority"].values())
                )

        ledgers = self.suite["persona_current_component_byte_ledgers"]
        self.assertEqual(
            [row["persona_id"] for row in ledgers], list(envelope.PERSONA_IDS)
        )
        for ledger in ledgers:
            expected_current = (
                ledger["semantic_current_component_bytes"]
                + ledger["overlay_contract_bytes_conservatively_charged_in_full"]
                + ledger["concrete_origin_body_bytes"]
                + ledger["concrete_origin_manifest_bytes"]
                + ledger["concrete_profile_manifest_bytes"]
            )
            self.assertEqual(ledger["current_component_bytes"], expected_current)
            self.assertLessEqual(expected_current, package.MAX_PERSONA_PACKAGE_BYTES)
            self.assertEqual(
                ledger["headroom_bytes"],
                package.MAX_PERSONA_PACKAGE_BYTES - expected_current,
            )
            self.assertIs(ledger["current_component_cap_satisfied"], True)
            self.assertIs(
                ledger["formal_complete_persona_package_cap_proved"], False
            )

        suite_raw = package.canonical_json_bytes(self.suite)
        self.assertEqual(len(suite_raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(
            hashlib.sha256(suite_raw).hexdigest(), EXPECTED_SUITE_SHA256
        )
        for coordinate, expected in {
            ("p01", "pilot", 0): EXPECTED_P01_PILOT_BODY,
            ("p12", "full-residual", 0): EXPECTED_P12_RESIDUAL_BODY,
        }.items():
            body = self.bodies[coordinate]
            actual = (
                len(body),
                hashlib.sha256(body).hexdigest(),
                len(body.splitlines()),
                max(len(line) + 1 for line in body.splitlines()),
            )
            self.assertEqual(actual, expected)

        with self.assertRaises(
            package.PersonaV2ConcreteOverlayMembershipPackageError
        ):
            package.require_complete_concrete_overlay_membership_package()

    def test_public_validator_and_deterministic_producer_accept_once_with_bounded_rss(
        self,
    ):
        script = r"""
import hashlib
import json
import resource
import sys

from eval import persona_v2_concrete_overlay_membership_package as package
from eval import persona_v2_concrete_overlay_membership_package_validator as validator
from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_contract as overlay_contract
from eval import persona_v2_overlay_reservation_layout as reservation
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_semantic_membership_package as semantic_package

suite = package.build_concrete_overlay_membership_suite_descriptor()
suite_raw = package.canonical_json_bytes(suite)
suite_again = package.canonical_json_bytes(
    package.build_concrete_overlay_membership_suite_descriptor()
)
origins = [
    package.build_concrete_overlay_membership_origin_manifest(persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
]
profiles = [
    package.build_concrete_overlay_membership_profile_manifest(persona_id, profile)
    for persona_id in envelope.PERSONA_IDS
    for profile in package.PROFILE_ORDER
]
reservation_origins = [
    reservation.build_overlay_reservation_origin(persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
]
source_origins = [
    source_package.build_source_intent_origin_manifest(persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
]
source_profiles = [
    source_package.build_source_intent_profile_manifest(persona_id, profile)
    for persona_id in envelope.PERSONA_IDS
    for profile in package.PROFILE_ORDER
]
semantic_origins = [
    semantic_package.build_source_semantic_membership_origin_manifest(
        persona_id, origin
    )
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
]
semantic_profiles = [
    semantic_package.build_source_semantic_membership_profile_manifest(
        persona_id, profile
    )
    for persona_id in envelope.PERSONA_IDS
    for profile in package.PROFILE_ORDER
]

target_calls = {}
upstream_calls = {
    "compact": {},
    "context": {},
    "membership": {},
    "source": {},
}
representative_bodies = {}
wanted = {("p01", "pilot", 0), ("p12", "full-residual", 0)}

def counted_provider(label, provider):
    def wrapped(*coordinate):
        calls = upstream_calls[label]
        calls[coordinate] = calls.get(coordinate, 0) + 1
        return provider(*coordinate)
    return wrapped

compact_provider = counted_provider(
    "compact", semantic_package.source_semantic_membership_origin_body_bytes
)
context_provider = counted_provider(
    "context", semantic_package.expanded_content_context_shard_body_bytes
)
membership_provider = counted_provider(
    "membership", semantic_package.expanded_fact_membership_shard_body_bytes
)
source_provider = counted_provider(
    "source", source_package.source_intent_shard_body_bytes
)

def target_provider(persona_id, origin, shard_index):
    coordinate = (persona_id, origin, shard_index)
    body = package.concrete_overlay_membership_shard_body_bytes(*coordinate)
    target_calls[coordinate] = target_calls.get(coordinate, 0) + 1
    if coordinate in wanted:
        receipt = [
            len(body),
            hashlib.sha256(body).hexdigest(),
            len(body.splitlines()),
            max(len(line) + 1 for line in body.splitlines()),
        ]
        previous = representative_bodies.setdefault(
            "/".join(map(str, coordinate)), receipt
        )
        if previous != receipt:
            raise AssertionError("representative target body changed across replay")
    return body

success = validator.validate_concrete_overlay_membership_package(
    suite,
    origins,
    profiles,
    target_provider,
    overlay_contract_value=overlay_contract.build_overlay_contract(),
    reservation_suite=reservation.build_overlay_reservation_suite(),
    reservation_origin_artifacts=reservation_origins,
    semantic_catalog=semantic_package.build_source_semantic_membership_catalog(),
    semantic_suite=semantic_package.build_source_semantic_membership_suite_descriptor(),
    semantic_origin_manifests=semantic_origins,
    semantic_profile_manifests=semantic_profiles,
    semantic_compact_origin_body_provider=compact_provider,
    semantic_expanded_context_body_provider=context_provider,
    semantic_expanded_membership_body_provider=membership_provider,
    source_suite=source_package.build_source_intent_suite_descriptor(),
    source_origin_manifests=source_origins,
    source_profile_manifests=source_profiles,
    source_shard_body_provider=source_provider,
)
expected_origins = {
    (persona_id, origin)
    for persona_id in envelope.PERSONA_IDS
    for origin in package.ORIGIN_ORDER
}
expected_source_shards = {
    (manifest["persona_id"], manifest["origin"], descriptor["shard_ordinal"])
    for manifest in source_origins
    for descriptor in manifest["shard_descriptors"]
}
for label, expected_coordinates, expected_count in (
    ("compact", expected_origins, 2),
    ("context", expected_source_shards, 2),
    ("membership", expected_source_shards, 2),
    ("source", expected_source_shards, 3),
):
    if (
        set(upstream_calls[label]) != expected_coordinates
        or set(upstream_calls[label].values()) != {expected_count}
    ):
        raise AssertionError(f"unexpected {label} provider coordinate/replay counts")
maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rss_bytes = int(maximum_rss) if sys.platform == "darwin" else int(maximum_rss) * 1024
print(json.dumps({
    "representative_bodies": representative_bodies,
    "rss_bytes": rss_bytes,
    "success": success,
    "suite_bytes": len(suite_raw),
    "suite_deterministic": suite_raw == suite_again,
    "suite_sha256": hashlib.sha256(suite_raw).hexdigest(),
    "target_call_coordinate_count": len(target_calls),
    "target_call_counts": sorted(set(target_calls.values())),
    "upstream_call_summaries": {
        label: {
            "coordinate_count": len(calls),
            "counts": sorted(set(calls.values())),
            "total": sum(calls.values()),
        }
        for label, calls in upstream_calls.items()
    },
}, sort_keys=True))
"""
        environment = dict(os.environ)
        environment.update(
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PYTHONHASHSEED": "73",
                "TZ": "UTC",
            }
        )
        output = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            text=True,
            # Reserve twenty minutes of the dedicated 90-minute job for the
            # preceding in-process tests, job setup, and failure reporting.
            timeout=4_200,
        )
        measured = json.loads(output)
        self.assertIs(measured["success"], True)
        self.assertIs(measured["suite_deterministic"], True)
        self.assertEqual(
            measured["target_call_coordinate_count"], EXPECTED_ORIGIN_COUNT
        )
        self.assertEqual(measured["target_call_counts"], [2])
        self.assertEqual(
            measured["upstream_call_summaries"],
            {
                "compact": {
                    "coordinate_count": EXPECTED_ORIGIN_COUNT,
                    "counts": [2],
                    "total": 80,
                },
                "context": {
                    "coordinate_count": 73,
                    "counts": [2],
                    "total": 146,
                },
                "membership": {
                    "coordinate_count": 73,
                    "counts": [2],
                    "total": 146,
                },
                "source": {
                    "coordinate_count": 73,
                    "counts": [3],
                    "total": 219,
                },
            },
        )
        self.assertEqual(
            measured["suite_bytes"],
            independent_validator.EXPECTED_SUITE_DESCRIPTOR_BYTES,
        )
        self.assertEqual(
            measured["suite_sha256"], independent_validator.EXPECTED_SUITE_SHA256
        )
        self.assertEqual(measured["suite_bytes"], EXPECTED_SUITE_BYTES)
        self.assertEqual(measured["suite_sha256"], EXPECTED_SUITE_SHA256)
        for key, expected in {
            "p01/pilot/0": EXPECTED_P01_PILOT_BODY,
            "p12/full-residual/0": EXPECTED_P12_RESIDUAL_BODY,
        }.items():
            self.assertEqual(
                tuple(measured["representative_bodies"][key]), expected
            )
        self.assertGreater(measured["rss_bytes"], 0)
        self.assertLessEqual(measured["rss_bytes"], MAX_BUILD_RSS_BYTES)

    def test_metadata_first_rethread_and_malformed_upstream_never_call_providers(self):
        self._ensure_package()
        self._ensure_upstream()
        self.assertIsNotNone(
            independent_validator.EXPECTED_SUITE_DESCRIPTOR_BYTES
        )
        self.assertIsNotNone(independent_validator.EXPECTED_SUITE_SHA256)

        def run_case(label, mutate):
            origins = copy.deepcopy(self.origins)
            profiles = copy.deepcopy(self.profiles)
            suite = copy.deepcopy(self.suite)
            upstream_overrides = {}
            mutate(origins, profiles, suite, upstream_overrides)
            requests = []

            def forbidden_provider(*coordinate):
                requests.append(coordinate)
                return b""

            with self.subTest(label=label):
                with self.assertRaises(
                    ConcreteValidationError
                ):
                    self._validate_public(
                        suite=suite,
                        origins=origins,
                        profiles=profiles,
                        upstream_overrides=upstream_overrides,
                        providers={
                            "membership": forbidden_provider,
                            "semantic_compact": forbidden_provider,
                            "semantic_context": forbidden_provider,
                            "semantic_membership": forbidden_provider,
                            "source": forbidden_provider,
                        },
                    )
                self.assertEqual(requests, [])

        def frozen_digest_rethread(origins, profiles, suite, upstream_overrides):
            del upstream_overrides
            manifest = next(
                row
                for row in origins
                if row["persona_id"] == "p01" and row["origin"] == "pilot"
            )
            digest = manifest["shard_descriptors"][0]["body_sha256"]
            replacement = ("0" if digest[0] != "0" else "1") + digest[1:]
            manifest["shard_descriptors"][0]["body_sha256"] = replacement
            _rethread_target_metadata(origins, profiles, suite)

        run_case("frozen-suite-pin-after-full-digest-rethread", frozen_digest_rethread)

        def bool_shard_index(origins, profiles, suite, upstream_overrides):
            del upstream_overrides
            origins[0]["shard_descriptors"][0]["shard_index"] = False
            _rethread_target_metadata(origins, profiles, suite)

        run_case("bool-is-not-zero-shard-index", bool_shard_index)

        def bool_sort_key(origins, profiles, suite, upstream_overrides):
            del upstream_overrides
            origins[0]["shard_descriptors"][0]["first_row_sort_key"][0] = False
            _rethread_target_metadata(origins, profiles, suite)

        run_case("bool-is-not-zero-sort-discriminator", bool_sort_key)

        def bool_draft_receipt_count(
            origins, profiles, suite, upstream_overrides
        ):
            del upstream_overrides
            origins[0]["draft_membership_projection_receipt"]["row_count"] = False
            _rethread_target_metadata(origins, profiles, suite)

        run_case("bool-is-not-zero-draft-receipt-count", bool_draft_receipt_count)

        def malformed_source_suite(origins, profiles, suite, upstream_overrides):
            del origins, profiles, suite
            value = copy.deepcopy(self.upstream["source_suite"])
            value["artifact_schema_version"] = False
            upstream_overrides["source_suite"] = value

        run_case("malformed-upstream-source-suite", malformed_source_suite)

        def malformed_semantic_catalog(
            origins, profiles, suite, upstream_overrides
        ):
            del origins, profiles, suite
            value = copy.deepcopy(self.upstream["semantic_catalog"])
            value["authority"][next(iter(sorted(value["authority"])))] = True
            upstream_overrides["semantic_catalog"] = value

        run_case("malformed-upstream-semantic-catalog", malformed_semantic_catalog)

        def target_authority(origins, profiles, suite, upstream_overrides):
            del origins, profiles, upstream_overrides
            suite["authority"][next(iter(sorted(suite["authority"])))] = True

        run_case("target-suite-positive-authority", target_authority)

    def test_one_origin_body_tamper_matrix(self):
        self._ensure_origin_harness()
        harness = self.origin_harness
        body = harness["body"]
        rows = _jsonl_rows(
            body, row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF
        )
        baseline = self._validate_one_origin(harness["manifest"], body)
        self.assertEqual(baseline["rich_row_count"], len(rows))

        foreign_fact_profile_id = next(
            row["fact_profile_id"]
            for row in harness["catalog"]["fact_profiles"]
            if row["persona_id"] == "p02"
        )

        def encoded(mutator, *, sort_rows=False):
            value = copy.deepcopy(rows)
            mutator(value)
            if sort_rows:
                value.sort(key=_rich_row_sort_key)
            return _encode_jsonl(
                value,
                row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF,
            )

        def missing(value):
            value.pop()

        def extra(value):
            row = copy.deepcopy(value[-1])
            row["semantic_anchor_slot_ordinal"] += 1
            row["intent_key"] += "-extra"
            value.append(row)

        def duplicate(value):
            value.insert(1, copy.deepcopy(value[0]))

        def reordered(value):
            value[0], value[1] = value[1], value[0]

        def foreign_content_fact(value):
            row = next(
                row for row in value if row["row_kind"] == CONTENT_ROW_KIND
            )
            row["anchor_fact_profile_id"] = foreign_fact_profile_id

        def conflict_branch_collapse(value):
            row = next(
                row
                for row in value
                if row["row_kind"] == CONTENT_ROW_KIND
                and row["relation_kind"] == "conflict-copy"
            )
            row["derivative_fact_profile_id"] = row["anchor_fact_profile_id"]

        def conflict_branch_swap(value):
            row = next(
                row
                for row in value
                if row["row_kind"] == CONTENT_ROW_KIND
                and row["relation_kind"] == "conflict-copy"
            )
            (
                row["anchor_fact_profile_id"],
                row["derivative_fact_profile_id"],
            ) = (
                row["derivative_fact_profile_id"],
                row["anchor_fact_profile_id"],
            )

        def relation_kind(value):
            row = next(
                row
                for row in value
                if row["row_kind"] == CONTENT_ROW_KIND
                and row["relation_kind"] == "near-revision"
            )
            row["relation_kind"] = "exact-duplicate"

        def placement(value):
            row = next(
                row for row in value if row["row_kind"] == CONTENT_ROW_KIND
            )
            alternatives = [
                item
                for item in (
                    "primary-to-primary",
                    "primary-to-secondary",
                    "secondary-to-primary",
                    "secondary-to-secondary",
                )
                if item != row["placement_class_requirement"]
            ]
            row["placement_class_requirement"] = alternatives[0]

        def attachment_fanout(value):
            row = next(
                row for row in value if row["row_kind"] == ATTACHMENT_ROW_KIND
            )
            row["host_member_count"] += 1

        def attachment_ordinal_duplicate(value):
            attachments = [
                row for row in value if row["row_kind"] == ATTACHMENT_ROW_KIND
            ]
            by_host = defaultdict(list)
            for row in attachments:
                by_host[row["host_intent_key"]].append(row)
            members = next(group for group in by_host.values() if len(group) > 1)
            members[1]["member_ordinal"] = members[0]["member_ordinal"]

        def attachment_overlap_to_near(value):
            near_cluster = next(
                row["cluster_key"]
                for row in value
                if row["row_kind"] == CONTENT_ROW_KIND
                and row["relation_kind"] == "near-revision"
            )
            row = next(
                row
                for row in value
                if row["row_kind"] == ATTACHMENT_ROW_KIND
                and row["content_relation_membership"] != "none"
            )
            row["content_relation_membership"] = near_cluster

        def attachment_payload(value):
            row = next(
                row for row in value if row["row_kind"] == ATTACHMENT_ROW_KIND
            )
            row["decoded_payload_equivalence_key"] += "-tampered"

        def foreign_anchor_fact(value):
            row = next(
                row for row in value if row["row_kind"] == ANCHOR_ROW_KIND
            )
            row["fact_profile_id"] = foreign_fact_profile_id

        def anchor_intent_overlap(value):
            relation = next(
                row for row in value if row["row_kind"] == CONTENT_ROW_KIND
            )
            anchor = next(
                row for row in value if row["row_kind"] == ANCHOR_ROW_KIND
            )
            anchor["intent_key"] = relation["anchor_intent_key"]

        def search_requirement(value):
            row = next(
                row for row in value if row["row_kind"] == CONTENT_ROW_KIND
            )
            row["search_participation_requirement_id"] = "attachment-structural-v2"

        cases = {
            "single-byte": _flip_one_body_byte(body),
            "missing-row": encoded(missing),
            "extra-row": encoded(extra),
            "duplicate-row": encoded(duplicate),
            "reordered-rows": encoded(reordered),
            "p01-row-valid-p02-fact-profile": encoded(foreign_content_fact),
            "conflict-branch-a-b-collapse": encoded(conflict_branch_collapse),
            "conflict-branch-a-b-swap": encoded(conflict_branch_swap),
            "relation-kind": encoded(relation_kind, sort_rows=True),
            "placement-class": encoded(placement),
            "attachment-fanout": encoded(attachment_fanout),
            "attachment-ordinal-duplicate": encoded(attachment_ordinal_duplicate),
            "attachment-overlap-to-near": encoded(attachment_overlap_to_near),
            "decoded-payload-equivalence": encoded(attachment_payload),
            "semantic-anchor-valid-p02-fact-profile": encoded(foreign_anchor_fact),
            "semantic-anchor-intent-overlap": encoded(
                anchor_intent_overlap, sort_rows=True
            ),
            "search-requirement": encoded(search_requirement),
            "crlf": body.replace(b"\n", b"\r\n"),
            "bom": b"\xef\xbb\xbf" + body,
            "blank-row": body + b"\n",
        }

        oversized_rows = copy.deepcopy(rows)
        oversized = next(
            row for row in oversized_rows if row["row_kind"] == CONTENT_ROW_KIND
        )
        oversized["cluster_key"] = "p01-" + "x" * 1_024
        oversized_rows.sort(key=_rich_row_sort_key)
        cases["row-over-768-bytes"] = b"".join(
            _canonical(row, max_bytes=4_096) + b"\n" for row in oversized_rows
        )
        one_row = _canonical(rows[0], max_bytes=4_096) + b"\n"
        cases["row-count-over-4096"] = one_row * (
            independent_validator.MAX_ROWS_PER_SHARD + 1
        )
        cases["body-over-4-mib"] = one_row * (
            independent_validator.MAX_SHARD_BODY_BYTES // len(one_row) + 1
        )

        for label, tampered_body in cases.items():
            manifest = _descriptor_rethreaded_for_body(
                harness["manifest"], tampered_body
            )
            with self.subTest(label=label):
                with self.assertRaises(
                    ConcreteValidationError
                ):
                    self._validate_one_origin(manifest, tampered_body)

        calls = 0

        def nondeterministic_provider(persona_id, origin, shard_index):
            nonlocal calls
            del persona_id, origin, shard_index
            calls += 1
            return body if calls == 1 else _flip_one_body_byte(body)

        target_provider = independent_validator._DigestRecordingProvider(
            nondeterministic_provider, "nondeterministic test target"
        )
        with self.assertRaises(ConcreteValidationError):
            independent_validator._validate_one_origin_body(
                harness["manifest"],
                harness["reservation"],
                harness["source_manifest"],
                target_provider=target_provider,
                source_provider=harness["source_provider"],
                context_provider=harness["context_provider"],
                membership_provider=harness["membership_provider"],
                fact_by_id=harness["fact_by_id"],
                semantic_by_source=harness["semantic_by_source"],
            )
        self.assertEqual(calls, 2)

    def test_draft_membership_projection_receipt_is_exact_and_not_a_second_body(self):
        self._ensure_package()
        projected_count = 0
        for manifest in self.origins:
            coordinate = (manifest["persona_id"], manifest["origin"], 0)
            rows = _jsonl_rows(
                self.bodies[coordinate],
                row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF,
            )
            projected = _draft_projection(rows)
            self.assertTrue(
                all(
                    row["row_kind"]
                    in {"content-relation", ATTACHMENT_ROW_KIND}
                    for row in projected
                )
            )
            self.assertFalse(
                any(row["row_kind"] == ANCHOR_ROW_KIND for row in projected)
            )
            projected_body = _encode_jsonl(
                projected,
                row_cap=independent_validator.MAX_ROW_BYTES_INCLUDING_LF,
            )
            receipt = manifest["draft_membership_projection_receipt"]
            self.assertEqual(
                receipt,
                {
                    "body_bytes": len(projected_body),
                    "body_sha256": hashlib.sha256(projected_body).hexdigest(),
                    "first_row_sort_key": _serialized_rich_row_sort_key(
                        next(
                            row
                            for row in rows
                            if row["row_kind"] != ANCHOR_ROW_KIND
                        )
                    ),
                    "last_row_sort_key": _serialized_rich_row_sort_key(
                        next(
                            row
                            for row in reversed(rows)
                            if row["row_kind"] != ANCHOR_ROW_KIND
                        )
                    ),
                    "maximum_row_bytes_including_lf": max(
                        len(line) + 1 for line in projected_body.splitlines()
                    ),
                    "row_count": len(projected),
                },
            )
            projected_count += len(projected)
        self.assertEqual(projected_count, EXPECTED_DRAFT_PROJECTION_ROW_COUNT)

        signature = inspect.signature(
            independent_validator.validate_concrete_overlay_membership_package
        )
        self.assertFalse(
            any(
                "draft" in name and "provider" in name
                for name in signature.parameters
            )
        )
        self.assertFalse(
            hasattr(package, "draft_membership_projection_body_bytes")
        )
        self.assertIs(
            self.suite["persona_current_component_byte_ledger_contract"][
                "draft_projection_body_is_receipt_only_and_not_persisted_or_charged"
            ],
            True,
        )

        self._ensure_origin_harness()
        receipt_tamper = copy.deepcopy(self.origin_harness["manifest"])
        digest = receipt_tamper["draft_membership_projection_receipt"][
            "body_sha256"
        ]
        receipt_tamper["draft_membership_projection_receipt"]["body_sha256"] = (
            ("0" if digest[0] != "0" else "1") + digest[1:]
        )
        with self.assertRaises(ConcreteValidationError):
            self._validate_one_origin(receipt_tamper, self.origin_harness["body"])

        origins = copy.deepcopy(self.origins)
        profiles = copy.deepcopy(self.profiles)
        suite = copy.deepcopy(self.suite)
        digest = origins[0]["draft_membership_projection_receipt"]["body_sha256"]
        origins[0]["draft_membership_projection_receipt"]["body_sha256"] = (
            ("0" if digest[0] != "0" else "1") + digest[1:]
        )
        _rethread_target_metadata(origins, profiles, suite)
        requests = []

        def forbidden_provider(*coordinate):
            requests.append(coordinate)
            return b""

        with self.assertRaises(ConcreteValidationError):
            self._validate_public(
                suite=suite,
                origins=origins,
                profiles=profiles,
                providers={
                    "membership": forbidden_provider,
                    "semantic_compact": forbidden_provider,
                    "semantic_context": forbidden_provider,
                    "semantic_membership": forbidden_provider,
                    "source": forbidden_provider,
                },
            )
        self.assertEqual(requests, [])


if __name__ == "__main__":
    unittest.main()
