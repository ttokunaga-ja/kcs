"""Focused gates for lifecycle effective-membership reconciliation.

The package under test is intentionally pre-solver and non-authorizing.  It
must reconcile the immutable W0 source-owned membership exactly once, bind
event-created source lineage without leaking purge witnesses to replacement
sources, and expose a content-only projection that is safe to place in the
future corpus semantic namespace.

The expensive full-suite build is shared by the in-process package tests.  An
explicit second-pass 203,000-row audit and the cold seeded subprocess audit are
kept in separate test classes so CI can budget or select them explicitly.
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

from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_lifecycle_effective_membership_reconciliation as package
from eval import (
    persona_v2_lifecycle_effective_membership_reconciliation_validator as independent,
)
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_matched_lifecycle_inventory as matched_lifecycle
from eval import persona_v2_source_semantic_membership_package as source_semantic


EXPECTED_W0_SOURCE_COUNT = 203_000
EXPECTED_PILOT_SOURCE_COUNT = 20_300
EXPECTED_RESIDUAL_SOURCE_COUNT = 182_700
EXPECTED_SOURCE_SHARD_COUNT = 73
EXPECTED_COMPACT_ROW_COUNT = 2_573
EXPECTED_PRIMARY_COUNT = 2_100
EXPECTED_PRIMARY_OVERRIDE_COUNT = 2_000
EXPECTED_COMPANION_COUNT = 200
EXPECTED_PURGE_WITNESS_COUNT = 300
EXPECTED_EVENT_CREATED_LINEAGE_COUNT = 3_630
EXPECTED_WITNESS_CONSUMER_COUNT = 600
EXPECTED_PERSONA_COUNT = 20
EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_I5_COUNT = 5 * EXPECTED_PERSONA_COUNT
EXPECTED_P_PRIME_COUNT = 15 * EXPECTED_PERSONA_COUNT

P01_PILOT_ORIGIN_MANIFEST_BYTES = 5_576
P01_PILOT_COMPACT_BODY_BYTES = 127_252
P01_PILOT_COMPACT_BODY_SHA256 = (
    "b4dc476b51916e67d2e6c021f9a50a319611fe3840719c5de10ba4fd26f0404d"
)
P01_PILOT_COMPACT_ROW_COUNT = 126
P01_PILOT_COMPACT_MAXIMUM_ROW_BYTES_INCLUDING_LF = 1_136
P01_PILOT_EXPANDED_SHARD_1_BODY_BYTES = 961_948
P01_PILOT_EXPANDED_MAXIMUM_ROW_BYTES_INCLUDING_LF = 913
P01_CONTENT_PROJECTION_BYTES = 103_439
P01_CONTENT_PROJECTION_SHA256 = (
    "d620a63b9762cf6119d795845c5b1533207ced29ae97fbb6ab3765a966d07f5e"
)
P01_CONTENT_PROJECTION_COMMITMENT_COUNT = 4
P12_RESIDUAL_COMPACT_BODY_BYTES = 2_460
P12_RESIDUAL_COMPACT_BODY_SHA256 = (
    "aefbfd79351fce4cd369e7fbf548db1734882e14f14ec524bb4499acc036234d"
)

EXPECTED_SUITE_CANONICAL_BYTES = 69_195
EXPECTED_SUITE_SHA256 = (
    "a624066396a534308c58cffe4f827160ea6d5f726c9507d9115e0ddb18752a29"
)
EXPECTED_MAXIMUM_ORIGIN_MANIFEST_BYTES = 5_592
EXPECTED_MAXIMUM_PROFILE_MANIFEST_BYTES = 3_301
EXPECTED_MAXIMUM_CONTENT_PROJECTION_BYTES = 103_840
EXPECTED_MAXIMUM_COMPACT_ROW_BYTES_INCLUDING_LF = 1_136
EXPECTED_MAXIMUM_EXPANDED_ROW_BYTES_INCLUDING_LF = 913
EXPECTED_MAXIMUM_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF = 571
EXPECTED_MAXIMUM_INVERTED_ROW_BYTES_INCLUDING_LF = 600

# 2026-08-01 に 15 分から引き上げた。**凍結値の drift ではなく wall-clock である。**
# この予算に当たっても値は 1 つも動いていないので、fixture を採り直して黙らせては
# ならない (`subprocess.TimeoutExpired` であって assert の失敗ではない)。
#
# 実測: この cold build は M4 Pro で **503.2s**、予算 900s の 56% しか使わない。
# それでも CI (ubuntu-latest) では直近 10 run のうち 8 回 900s を超えて落ちていた。
# つまりランナーが 1.79 倍遅ければ当たる位置に、ずっと張り付いていた。
#
# **改名は原因ではない。** 3 つで確かめた: (1) 改名前 `978e874` の同テストも CI で
# 落ちている、(2) 測定スクリプト本体が改名前後でバイト同一、(3) 同じ機械で測ると
# 改名前 503.9s / 改名後 503.2s で **0.999 倍** — salt の影響範囲に入るモジュール
# なので疑ったが、差は無かった。
#
# 同じ 15 分を持つ `source_parameter_assignment_package` と
# `source_matched_lifecycle_inventory` は 8/8 で通っている。予算が一律に短いのでは
# なく、**このモジュールだけが重い**。30 分は CI の実効値 (~900s) に対して約 2 倍で、
# ジョブ側の timeout-minutes (120) には影響しない — 予算は上限であって目標ではなく、
# 引き上げても所要は変わらないためである。
MAX_COLD_BUILD_SECONDS = 30 * 60
MAX_COLD_BUILD_RSS_BYTES = 512 * 2**20
P12_NOMINAL_PRE_SOLVE_HEADROOM_BYTES = 1_203_356


def _canonical(value):
    return package.canonical_json_bytes(value)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _walk_keys(value):
    if type(value) is dict:
        for key, item in value.items():
            yield key
            yield from _walk_keys(item)
    elif type(value) is list:
        for item in value:
            yield from _walk_keys(item)


def _jsonl_rows(body, *, row_cap):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        raise AssertionError("canonical JSONL body must be non-empty and LF-terminated")
    if b"\r" in body or body.endswith(b"\n\n"):
        raise AssertionError("canonical JSONL framing drifted")
    rows = []
    for raw in body.splitlines():
        if len(raw) + 1 > row_cap:
            raise AssertionError("canonical JSONL row exceeds its LF-inclusive cap")
        row = json.loads(raw)
        if package.canonical_fragment_bytes(row, max_bytes=row_cap - 1) != raw:
            raise AssertionError("JSONL row is not canonical JSON")
        rows.append(row)
    return rows


def _replace_bytes_once(body, old, new):
    if type(old) is not bytes or type(new) is not bytes or len(old) != len(new):
        raise AssertionError("same-length replacement required")
    if body.count(old) != 1:
        raise AssertionError("replacement needle must occur exactly once")
    return body.replace(old, new, 1)


class LifecycleEffectiveMembershipReconciliationTest(unittest.TestCase):
    """Cached full-package shape, semantic, tamper, and provider gates."""

    suite = None
    origins = None
    profiles = None
    projections = None

    @classmethod
    def _ensure_package(cls):
        if cls.suite is not None:
            return
        cls.origins = [
            package.build_lifecycle_effective_membership_origin_manifest(
                persona_id, origin
            )
            for persona_id in envelope.PERSONA_IDS
            for origin in package.ORIGIN_ORDER
        ]
        cls.profiles = [
            package.build_lifecycle_effective_membership_profile_manifest(
                persona_id, profile
            )
            for persona_id in envelope.PERSONA_IDS
            for profile in package.PROFILE_ORDER
        ]
        cls.suite = package.build_lifecycle_effective_membership_suite_descriptor()
        cls.projections = {
            persona_id: package.build_lifecycle_effective_membership_content_projection(
                persona_id
            )
            for persona_id in envelope.PERSONA_IDS
        }

    def test_public_api_schema_caps_and_exact_contract_constants(self):
        expected_callables = {
            "build_lifecycle_effective_membership_content_projection",
            "build_lifecycle_effective_membership_origin_manifest",
            "build_lifecycle_effective_membership_profile_manifest",
            "build_lifecycle_effective_membership_suite_descriptor",
            "canonical_fragment_bytes",
            "canonical_json_bytes",
            "expanded_effective_w0_membership_shard_body_bytes",
            "iter_event_created_witness_lineage_rows",
            "iter_expanded_effective_w0_membership_rows",
            "iter_inverted_purge_witness_rows",
            "iter_lifecycle_effective_membership_origin_rows",
            "lifecycle_effective_membership_event_created_lineage_body_bytes",
            "lifecycle_effective_membership_inverted_witness_body_bytes",
            "lifecycle_effective_membership_origin_body_bytes",
            "lifecycle_effective_membership_content_projection_sha256",
            "lifecycle_effective_membership_origin_manifest_sha256",
            "lifecycle_effective_membership_profile_manifest_sha256",
            "lifecycle_effective_membership_suite_sha256",
            "validate_lifecycle_effective_membership_content_projection",
            "validate_lifecycle_effective_membership_origin_manifest",
            "validate_lifecycle_effective_membership_profile_manifest",
            "validate_lifecycle_effective_membership_suite_descriptor",
        }
        for name in expected_callables:
            self.assertTrue(callable(getattr(package, name, None)), name)

        self.assertEqual(package.ORIGIN_ORDER, ("pilot", "full-residual"))
        self.assertEqual(package.PROFILE_ORDER, ("pilot", "full"))
        self.assertEqual(package.EXPECTED_SOURCE_COUNT, EXPECTED_W0_SOURCE_COUNT)
        self.assertEqual(
            package.EXPECTED_SHARD_RECEIPT_COUNT, EXPECTED_SOURCE_SHARD_COUNT
        )
        self.assertEqual(
            package.EXPECTED_PRIMARY_OVERRIDE_COUNT,
            EXPECTED_PRIMARY_OVERRIDE_COUNT,
        )
        self.assertEqual(
            package.EXPECTED_COMPANION_MIRROR_COUNT, EXPECTED_COMPANION_COUNT
        )
        self.assertEqual(
            package.EXPECTED_TYPED_WITNESS_COUNT, EXPECTED_PURGE_WITNESS_COUNT
        )
        self.assertEqual(
            package.EXPECTED_COMPACT_ROW_COUNT, EXPECTED_COMPACT_ROW_COUNT
        )
        self.assertEqual(
            package.EXPECTED_EVENT_CREATED_LINEAGE_COUNT,
            EXPECTED_EVENT_CREATED_LINEAGE_COUNT,
        )
        self.assertEqual(
            package.EXPECTED_INVERTED_CONSUMER_REFERENCE_COUNT,
            EXPECTED_WITNESS_CONSUMER_COUNT,
        )
        self.assertEqual(package.MAX_ORIGIN_MANIFEST_BYTES, 256 * 1024)
        self.assertEqual(package.MAX_PROFILE_MANIFEST_BYTES, 256 * 1024)
        self.assertEqual(package.MAX_EXPANDED_SHARD_BODY_BYTES, 4 * 2**20)
        self.assertEqual(package.MAX_EXPANDED_ROWS_PER_SHARD, 4_096)
        self.assertEqual(package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF, 2_048)
        self.assertEqual(package.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF, 1_024)
        self.assertEqual(package.MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF, 1_024)
        self.assertEqual(package.MAX_INVERTED_ROW_BYTES_INCLUDING_LF, 1_024)
        self.assertEqual(
            package.EXPECTED_SUITE_CANONICAL_BYTES,
            EXPECTED_SUITE_CANONICAL_BYTES,
        )
        self.assertEqual(package.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)
        self.assertEqual(
            package.EXPECTED_MAX_ORIGIN_MANIFEST_BYTES,
            EXPECTED_MAXIMUM_ORIGIN_MANIFEST_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_MAX_PROFILE_MANIFEST_BYTES,
            EXPECTED_MAXIMUM_PROFILE_MANIFEST_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_MAX_CONTENT_PROJECTION_BYTES,
            EXPECTED_MAXIMUM_CONTENT_PROJECTION_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            EXPECTED_MAXIMUM_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            package.EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
            EXPECTED_MAXIMUM_EXPANDED_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            package.EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
            EXPECTED_MAXIMUM_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            package.EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
            EXPECTED_MAXIMUM_INVERTED_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            package.EXPECTED_P01_PILOT_COMPACT_BODY_BYTES,
            P01_PILOT_COMPACT_BODY_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_P01_PILOT_COMPACT_BODY_SHA256,
            P01_PILOT_COMPACT_BODY_SHA256,
        )
        self.assertEqual(
            package.EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES,
            P12_RESIDUAL_COMPACT_BODY_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256,
            P12_RESIDUAL_COMPACT_BODY_SHA256,
        )
        self.assertEqual(
            package.EXPECTED_P01_CONTENT_PROJECTION_BYTES,
            P01_CONTENT_PROJECTION_BYTES,
        )
        self.assertEqual(
            package.EXPECTED_P01_CONTENT_PROJECTION_SHA256,
            P01_CONTENT_PROJECTION_SHA256,
        )
        for frozen_name in (
            "EXPECTED_SUITE_CANONICAL_BYTES",
            "EXPECTED_SUITE_SHA256",
            "EXPECTED_MAX_ORIGIN_MANIFEST_BYTES",
            "EXPECTED_MAX_PROFILE_MANIFEST_BYTES",
            "EXPECTED_MAX_CONTENT_PROJECTION_BYTES",
            "EXPECTED_MAX_COMPACT_ROW_BYTES_INCLUDING_LF",
            "EXPECTED_MAX_EXPANDED_ROW_BYTES_INCLUDING_LF",
            "EXPECTED_MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF",
            "EXPECTED_MAX_INVERTED_ROW_BYTES_INCLUDING_LF",
            "EXPECTED_P01_PILOT_COMPACT_BODY_BYTES",
            "EXPECTED_P01_PILOT_COMPACT_BODY_SHA256",
            "EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_BYTES",
            "EXPECTED_P12_FULL_RESIDUAL_COMPACT_BODY_SHA256",
            "EXPECTED_P01_CONTENT_PROJECTION_BYTES",
            "EXPECTED_P01_CONTENT_PROJECTION_SHA256",
        ):
            self.assertEqual(
                getattr(independent, frozen_name),
                getattr(package, frozen_name),
                frozen_name,
            )

        self.assertEqual(
            package.EXPECTED_W0_MODE_COUNTS,
            {
                "base-inheritance": 200_800,
                "companion-mirror": 200,
                "graph-normal": 1_700,
                "graph-normal-plus-witness": 300,
            },
        )
        self.assertEqual(
            package.EXPECTED_W0_FACT_DISTRIBUTION,
            {
                "conflict-branch": 3_120,
                "empty": 73_350,
                "graph-normal-only": 126_130,
                "graph-normal-plus-witness": 300,
                "singleton": 100,
            },
        )
        self.assertEqual(package.EXPECTED_PRESENT_FACT_REFERENCE_COUNT, 1_033_680)

        self.assertEqual(
            package.EXPECTED_SHARD_RECEIPT_COUNT
            + package.EXPECTED_PRIMARY_OVERRIDE_COUNT
            + package.EXPECTED_COMPANION_MIRROR_COUNT
            + package.EXPECTED_TYPED_WITNESS_COUNT,
            EXPECTED_COMPACT_ROW_COUNT,
        )
        independent_source = inspect.getsource(independent)
        self.assertNotIn(
            "import persona_v2_lifecycle_effective_membership_reconciliation as",
            independent_source,
        )
        self.assertNotIn(
            "from . import persona_v2_lifecycle_effective_membership_reconciliation",
            independent_source,
        )

    def test_opening_snapshot_is_deserialized_from_authenticated_bytes(self):
        opening = {"artifact_schema": package.ORIGIN_SCHEMA, "marker": "opening"}
        opening_raw = package.canonical_json_bytes(opening)
        live_value = {
            "artifact_schema": package.ORIGIN_SCHEMA,
            "marker": "changed-after-opening",
        }
        with mock.patch.object(independent, "_canonical", return_value=opening_raw):
            snapshot, authenticated = independent._snapshot(
                live_value, label="focused opening snapshot", maximum=4_096
            )
        self.assertEqual(authenticated, opening_raw)
        self.assertEqual(snapshot, opening)
        self.assertNotEqual(snapshot, live_value)

    def test_projection_candidate_identity_cannot_bypass_p01_pin(self):
        candidate = {
            "artifact_kind": independent.PROJECTION_KIND,
            "artifact_schema": independent.PROJECTION_SCHEMA,
            "artifact_schema_version": independent.ARTIFACT_SCHEMA_VERSION,
            "content_sections": {
                "effective_membership_shard_commitments": [
                    {
                        "body_bytes": 1,
                        "body_sha256": "0" * 64,
                        "first_intent_key": "first",
                        "last_intent_key": "last",
                        "origin": "pilot",
                        "row_count": 1,
                        "row_kind": (
                            "effective-membership-shard-content-commitment"
                        ),
                        "source_shard_id": "shard-1",
                    }
                ]
            },
            "fixture_id": envelope.FIXTURE_ID,
            "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
            "persona_id": "p02",
        }
        with (
            mock.patch.object(
                independent,
                "_expected_content_projection",
                return_value=copy.deepcopy(candidate),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "persona coordinate differs from validator argument",
            ),
        ):
            independent.validate_lifecycle_effective_membership_content_projection(
                "p01", candidate
            )
        p01_candidate = copy.deepcopy(candidate)
        p01_candidate["persona_id"] = "p01"
        with (
            mock.patch.object(
                independent,
                "_expected_content_projection",
                return_value=copy.deepcopy(p01_candidate),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "p01 effective content projection frozen pin drifted",
            ),
        ):
            independent.validate_lifecycle_effective_membership_content_projection(
                "p01", p01_candidate
            )
        for field in (
            "artifact_schema_version",
            "fixture_schema_version",
        ):
            with self.subTest(boolean_version_field=field):
                boolean_version = copy.deepcopy(p01_candidate)
                boolean_version[field] = True
                with (
                    mock.patch.object(
                        independent,
                        "_expected_content_projection",
                        return_value=copy.deepcopy(boolean_version),
                    ),
                    self.assertRaisesRegex(
                        independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                        "artifact identity drifted",
                    ),
                ):
                    independent.validate_lifecycle_effective_membership_content_projection(
                        "p01", boolean_version
                    )

    def test_cached_expected_objects_are_immutable_and_actual_authority_is_checked(self):
        validator_cached_helpers = (
            "_independent_catalog_state",
            "_independent_persona_plan",
            "_expected_origin_manifest",
            "_expected_profile_manifest",
            "_expected_content_projection",
            "_witness_registry",
            "_expected_suite_descriptor",
        )
        producer_cached_helpers = (
            "_shared_catalogs",
            "_persona_plan",
            "_origin_dependencies",
            "_canonical_origin_rows",
            "_canonical_origin_manifest",
            "_persona_w0_audit",
            "_persona_inverted_rows",
            "_canonical_profile_manifest",
            "_canonical_suite_descriptor",
            "_canonical_content_projection",
        )
        for module, names in (
            (independent, validator_cached_helpers),
            (package, producer_cached_helpers),
        ):
            for name in names:
                helper = getattr(module, name)
                self.assertIs(helper.immutable_cache_only, True, name)
                self.assertTrue(callable(helper.cache_clear), name)
        package._canonical_content_projection.cache_clear()
        self.assertEqual(
            package._canonical_content_projection.cache_info().currsize, 0
        )

        calls = []

        @package._detached_lru_cache(maxsize=1)
        def detached_sample():
            calls.append(True)
            return {"nested": [{"authority": False}]}

        first = detached_sample()
        first["nested"][0]["authority"] = True
        second = detached_sample()
        self.assertEqual(calls, [True])
        self.assertIs(second["nested"][0]["authority"], False)
        self.assertIsNot(first, second)
        self.assertIsNot(first["nested"][0], second["nested"][0])

        baseline = independent._expected_profile_manifest("p01", "pilot")
        baseline_raw = independent._canonical(
            baseline,
            label="cache-poisoning regression profile",
            maximum=independent.MAX_PROFILE_MANIFEST_BYTES,
        )
        poisoned = independent._expected_profile_manifest("p01", "pilot")
        poisoned["authority"]["authorizes_g0_freeze"] = True
        fresh = independent._expected_profile_manifest("p01", "pilot")
        self.assertIs(
            fresh["authority"]["authorizes_g0_freeze"], False
        )
        self.assertEqual(
            independent._canonical(
                fresh,
                label="cache-poisoning regression profile",
                maximum=independent.MAX_PROFILE_MANIFEST_BYTES,
            ),
            baseline_raw,
        )
        self.assertIs(
            independent.validate_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot", copy.deepcopy(fresh)
            ),
            True,
        )
        profile_coordinate_poisoned = copy.deepcopy(fresh)
        profile_coordinate_poisoned["persona_id"] = "p02"
        with (
            mock.patch.object(
                independent,
                "_expected_profile_manifest",
                return_value=copy.deepcopy(profile_coordinate_poisoned),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "persona coordinate differs from validator argument",
            ),
        ):
            independent.validate_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot", profile_coordinate_poisoned
            )

        profile_binding_poisoned = copy.deepcopy(fresh)
        profile_binding_poisoned["origin_manifest_bindings"][0][
            "persona_id"
        ] = "p02"
        with (
            mock.patch.object(
                independent,
                "_expected_profile_manifest",
                return_value=copy.deepcopy(profile_binding_poisoned),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "origin binding coordinates drifted",
            ),
        ):
            independent.validate_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot", profile_binding_poisoned
            )

        origin_coordinate_poisoned = independent._expected_origin_manifest(
            "p01", "pilot"
        )
        origin_coordinate_poisoned["origin"] = "full-residual"
        with (
            mock.patch.object(
                independent,
                "_expected_origin_manifest",
                return_value=copy.deepcopy(origin_coordinate_poisoned),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "origin coordinate differs from validator argument",
            ),
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01", "pilot", origin_coordinate_poisoned
            )

        origin_pin_poisoned = independent._expected_origin_manifest(
            "p01", "pilot"
        )
        origin_pin_poisoned["body_descriptor"]["body_bytes"] += 1
        with (
            mock.patch.object(
                independent,
                "_expected_origin_manifest",
                return_value=copy.deepcopy(origin_pin_poisoned),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "representative frozen body pin drifted",
            ),
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01", "pilot", origin_pin_poisoned
            )

        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot", copy.deepcopy(poisoned)
            )

        # Even a compromised comparison oracle cannot authorize an actual
        # candidate: the public validator checks the detached candidate first.
        with (
            mock.patch.object(
                independent,
                "_expected_profile_manifest",
                return_value=copy.deepcopy(poisoned),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "authority must be the exact all-false schema",
            ),
        ):
            independent.validate_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot", copy.deepcopy(poisoned)
            )

        producer_baseline = package._canonical_profile_manifest(
            "p01", "pilot"
        )
        producer_raw = package.canonical_json_bytes(producer_baseline)
        producer_poisoned = package._canonical_profile_manifest(
            "p01", "pilot"
        )
        producer_poisoned["authority"]["authorizes_g0_freeze"] = True
        producer_fresh = (
            package.build_lifecycle_effective_membership_profile_manifest(
                "p01", "pilot"
            )
        )
        self.assertIs(
            producer_fresh["authority"]["authorizes_g0_freeze"], False
        )
        self.assertEqual(
            package.canonical_json_bytes(producer_fresh), producer_raw
        )

    def test_unknown_lifecycle_event_schema_fails_closed(self):
        malformed = {"row_kind": "source"}
        with (
            mock.patch.object(package, "_persona_plan", return_value={}),
            mock.patch.object(
                matched_lifecycle,
                "iter_source_matched_lifecycle_event_rows",
                return_value=iter((malformed,)),
            ),
            self.assertRaisesRegex(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError,
                "unknown row schema",
            ),
        ):
            list(package.iter_event_created_witness_lineage_rows("p01"))

        with (
            mock.patch.object(
                independent,
                "_independent_persona_plan",
                return_value={"lifecycle": {"primary_match_rows": []}},
            ),
            mock.patch.object(
                matched_lifecycle,
                "iter_source_matched_lifecycle_event_rows",
                return_value=iter((malformed,)),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError,
                "unknown row schema",
            ),
        ):
            independent._event_created_lineage_rows("p01")

    def test_compact_origin_rows_exact_totality_shapes_and_witness_domain(self):
        compact_counts = Counter()
        primary_by_capability = {}
        companions = []
        witnesses = []
        graph_by_coordinate = {}
        predicate_by_coordinate = {}
        base_fact_ids = set()

        semantic_catalog = source_semantic.build_source_semantic_membership_catalog()
        source_semantic.validate_source_semantic_membership_catalog(semantic_catalog)
        for profile in semantic_catalog["fact_profiles"]:
            base_fact_ids.update(profile["present_fact_ids"])

        for persona_id in envelope.PERSONA_IDS:
            graph = fact_graph.build_fact_graph(persona_id)
            fact_graph.validate_fact_graph(persona_id, graph)
            graph_ids = {row["graph_id"] for row in graph["graphs"]}
            self.assertEqual(len(graph_ids), 4)
            graph_by_coordinate.update(
                {
                    (persona_id, graph_row["graph_id"]): graph_row
                    for graph_row in graph["graphs"]
                }
            )
            predicate_by_coordinate.update(
                {
                    (persona_id, row["predicate_id"]): row
                    for row in graph["predicate_catalog"]
                }
            )
            base_fact_ids.update(
                fact["fact_id"]
                for graph_row in graph["graphs"]
                for fact in graph_row["facts"]
            )

            for origin in package.ORIGIN_ORDER:
                body = package.lifecycle_effective_membership_origin_body_bytes(
                    persona_id, origin
                )
                rows = _jsonl_rows(
                    body, row_cap=package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF
                )
                if (persona_id, origin) in {
                    ("p01", "pilot"),
                    ("p12", "full-residual"),
                }:
                    self.assertEqual(
                        rows,
                        list(
                            package.iter_lifecycle_effective_membership_origin_rows(
                                persona_id, origin
                            )
                        ),
                    )
                self.assertLessEqual(len(body), package.MAX_ORIGIN_BODY_BYTES)
                self.assertLessEqual(len(rows), package.MAX_ORIGIN_ROWS)

                for row in rows:
                    self.assertEqual(row["persona_id"], persona_id)
                    self.assertEqual(row["origin"], origin)
                    kind = row["row_kind"]
                    compact_counts[kind] += 1
                    if kind == "effective-w0-expanded-shard-receipt":
                        self.assertEqual(set(row), package.SHARD_RECEIPT_ROW_FIELDS)
                        self.assertIs(row["expanded_body_persisted"], False)
                        self.assertLessEqual(
                            row["expanded_body_bytes"],
                            package.MAX_EXPANDED_SHARD_BODY_BYTES,
                        )
                        self.assertLessEqual(
                            row["expanded_maximum_row_bytes_including_lf"],
                            package.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
                        )
                    elif kind == "primary-effective-membership-override":
                        self.assertEqual(set(row), package.PRIMARY_OVERRIDE_ROW_FIELDS)
                        self.assertNotIn(row["capability_key"], primary_by_capability)
                        primary_by_capability[row["capability_key"]] = row
                    elif kind == "companion-effective-membership-mirror":
                        self.assertEqual(set(row), package.COMPANION_MIRROR_ROW_FIELDS)
                        companions.append(row)
                    elif kind == "typed-purge-witness-fact":
                        self.assertEqual(set(row), package.TYPED_WITNESS_ROW_FIELDS)
                        witnesses.append(row)
                    else:
                        self.fail(f"unknown compact row kind: {kind!r}")

        self.assertEqual(
            compact_counts,
            {
                "companion-effective-membership-mirror": 200,
                "effective-w0-expanded-shard-receipt": 73,
                "primary-effective-membership-override": 2_000,
                "typed-purge-witness-fact": 300,
            },
        )
        self.assertEqual(sum(compact_counts.values()), EXPECTED_COMPACT_ROW_COUNT)
        self.assertEqual(len(primary_by_capability), EXPECTED_PRIMARY_OVERRIDE_COUNT)
        self.assertEqual(len(companions), EXPECTED_COMPANION_COUNT)
        self.assertEqual(len(witnesses), EXPECTED_PURGE_WITNESS_COUNT)

        witness_fact_ids = [row["fact_id"] for row in witnesses]
        witness_keys = [row["purge_witness_key"] for row in witnesses]
        witness_tokens = [row["typed_value"]["token_id"] for row in witnesses]
        self.assertEqual(len(set(witness_fact_ids)), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertEqual(len(set(witness_keys)), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertEqual(len(set(witness_tokens)), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertTrue(set(witness_fact_ids).isdisjoint(base_fact_ids))
        for witness in witnesses:
            graph_row = graph_by_coordinate[
                (witness["persona_id"], witness["graph_id"])
            ]
            entity_ids = {row["entity_id"] for row in graph_row["entities"]}
            self.assertIn(witness["subject_entity_id"], entity_ids)
            self.assertEqual(
                witness["project_or_case_id"], graph_row["project_or_case_id"]
            )
            predicate = predicate_by_coordinate[
                (witness["persona_id"], witness["predicate_id"])
            ]
            self.assertEqual(predicate["value_kind"], "synthetic-token")
            self.assertEqual(witness["typed_value"]["kind"], "synthetic-token")
        self.assertTrue(
            all(row["suite_global_uniqueness_required"] is True for row in witnesses)
        )
        expected_visibility = [
            {"checkpoint": checkpoint, "state": state}
            for checkpoint, state in (
                ("W0", "current"),
                ("W1", "current"),
                ("W2", "current"),
                ("W3", "current"),
                ("W4", "current"),
                ("W5-pre-purge", "current"),
                ("W5-final", "absent"),
            )
        ]
        self.assertTrue(
            all(row["visibility_by_checkpoint"] == expected_visibility for row in witnesses)
        )

        for companion in companions:
            primary = primary_by_capability[companion["primary_capability_key"]]
            self.assertEqual(companion["witness_fact_ids"], [])
            self.assertIn(primary["capability_class_key"], {
                "replacement-current-cross-format",
                "stable-current-cross-format",
            })
            for field in (
                "effective_fact_profile_id",
                "graph_id",
                "lifecycle_branch_key",
                "lifecycle_logical_document_key",
                "lifecycle_revision_chain_key",
                "logical_revision_key",
                "present_fact_ids",
                "semantic_section_key",
                "topic_id",
                "witness_fact_ids",
            ):
                self.assertEqual(companion[field], primary[field], field)
            self.assertEqual(companion["primary_intent_key"], primary["intent_key"])
            self.assertNotEqual(companion["intent_key"], primary["intent_key"])

    def test_event_created_lineage_p_prime_empty_and_inverted_consumers_exact(self):
        lineage_rows = []
        event_maximum_row_bytes = 0
        witness_by_fact_id = {}
        primary_by_capability = {}
        for persona_id in envelope.PERSONA_IDS:
            compact = list(
                package.iter_lifecycle_effective_membership_origin_rows(
                    persona_id, "pilot"
                )
            )
            for row in compact:
                if row["row_kind"] == "typed-purge-witness-fact":
                    witness_by_fact_id[row["fact_id"]] = row
                elif row["row_kind"] == "primary-effective-membership-override":
                    primary_by_capability[row["capability_key"]] = row

            current = list(package.iter_event_created_witness_lineage_rows(persona_id))
            body = (
                package.lifecycle_effective_membership_event_created_lineage_body_bytes(
                    persona_id
                )
            )
            self.assertEqual(
                current,
                _jsonl_rows(
                    body,
                    row_cap=package.MAX_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
                ),
            )
            self.assertLessEqual(len(body), package.MAX_EVENT_LINEAGE_BODY_BYTES)
            event_maximum_row_bytes = max(
                event_maximum_row_bytes,
                max(len(line) + 1 for line in body.splitlines()),
            )
            lineage_rows.extend(current)

        self.assertEqual(len(lineage_rows), EXPECTED_EVENT_CREATED_LINEAGE_COUNT)
        self.assertEqual(
            len({row["after_source_intent_key"] for row in lineage_rows}),
            EXPECTED_EVENT_CREATED_LINEAGE_COUNT,
        )
        self.assertTrue(
            all(set(row) == package.EVENT_LINEAGE_ROW_FIELDS for row in lineage_rows)
        )
        for row in lineage_rows:
            self.assertNotEqual(
                row["after_source_intent_key"], row["source_intent_key"]
            )
            self.assertEqual(
                row["after_source_intent_key"],
                (
                    f"{row['persona_id']}-pre-solve-source-intent-"
                    f"{row['event_sequence_ordinal']:04d}"
                ),
            )
        roles = Counter(row["consumer_role"] for row in lineage_rows)
        self.assertEqual(
            roles,
            {
                "matching-w1-p-descendant": 300,
                "other-event-created-intent": 3_030,
                "p-prime-capacity-replacement": 300,
            },
        )
        p_prime = [
            row
            for row in lineage_rows
            if row["consumer_role"] == "p-prime-capacity-replacement"
        ]
        self.assertEqual(len(p_prime), EXPECTED_P_PRIME_COUNT)
        self.assertTrue(
            all(row["event_profile_key"] == "w5-create-p-prime" for row in p_prime)
        )
        self.assertTrue(
            all(row["present_purge_witness_fact_ids"] == [] for row in p_prime)
        )
        carrying = [
            row
            for row in lineage_rows
            if row["present_purge_witness_fact_ids"]
        ]
        self.assertEqual(len(carrying), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertTrue(
            all(row["consumer_role"] == "matching-w1-p-descendant" for row in carrying)
        )
        self.assertTrue(
            all(len(row["present_purge_witness_fact_ids"]) == 1 for row in carrying)
        )
        self.assertTrue(
            all(
                row["dependency_group_key"]
                and row["fact_transition_rule"]
                and row["event_intent_key"]
                for row in lineage_rows
            )
        )
        self.assertEqual(
            {row["present_purge_witness_fact_ids"][0] for row in carrying},
            set(witness_by_fact_id),
        )

        inverted = list(package.iter_inverted_purge_witness_rows())
        inverted_body = package.lifecycle_effective_membership_inverted_witness_body_bytes()
        self.assertEqual(
            inverted,
            _jsonl_rows(
                inverted_body,
                row_cap=package.MAX_INVERTED_ROW_BYTES_INCLUDING_LF,
            ),
        )
        self.assertEqual(len(inverted), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertEqual(
            event_maximum_row_bytes,
            EXPECTED_MAXIMUM_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            max(len(line) + 1 for line in inverted_body.splitlines()),
            EXPECTED_MAXIMUM_INVERTED_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            len({row["witness_fact_id"] for row in inverted}),
            EXPECTED_PURGE_WITNESS_COUNT,
        )
        self.assertEqual(
            sum(row["consumer_count"] for row in inverted),
            EXPECTED_WITNESS_CONSUMER_COUNT,
        )
        carrying_by_capability = {
            row["capability_key"]: row for row in carrying
        }
        for row in inverted:
            self.assertEqual(set(row), package.INVERTED_WITNESS_ROW_FIELDS)
            self.assertEqual(row["consumer_count"], 2)
            self.assertEqual(len(row["consumer_refs"]), 2)
            witness = witness_by_fact_id[row["witness_fact_id"]]
            self.assertEqual(row["capability_key"], witness["capability_key"])
            self.assertEqual(row["purge_witness_key"], witness["purge_witness_key"])
            primary = primary_by_capability[row["capability_key"]]
            descendant = carrying_by_capability[row["capability_key"]]
            self.assertEqual(
                row["consumer_refs"],
                [
                    {
                        "consumer_domain": "w0-source",
                        "consumer_role": "matching-w0-p-primary",
                        "event_intent_key": "not-applicable-w0",
                        "source_intent_key": primary["intent_key"],
                    },
                    {
                        "consumer_domain": "event-created-source",
                        "consumer_role": "matching-w1-p-descendant",
                        "event_intent_key": descendant["event_intent_key"],
                        "source_intent_key": descendant[
                            "after_source_intent_key"
                        ],
                    },
                ],
            )

    def test_origin_profile_suite_manifests_counts_reuse_authority_and_sizes(self):
        self._ensure_package()
        self.assertEqual(len(self.origins), EXPECTED_ORIGIN_COUNT)
        self.assertEqual(len(self.profiles), EXPECTED_PROFILE_COUNT)
        origin_by_key = {
            (row["persona_id"], row["origin"]): row for row in self.origins
        }
        profile_by_key = {
            (row["persona_id"], row["profile"]): row for row in self.profiles
        }

        for manifest in self.origins:
            self.assertEqual(manifest["artifact_schema"], package.ORIGIN_SCHEMA)
            self.assertEqual(set(manifest["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(
                all(type(flag) is bool and flag is False for flag in manifest["authority"].values())
            )
            self.assertIs(manifest["g0_contract_frozen"], False)
            raw = _canonical(manifest)
            self.assertLessEqual(len(raw), package.MAX_ORIGIN_MANIFEST_BYTES)
            body = package.lifecycle_effective_membership_origin_body_bytes(
                manifest["persona_id"], manifest["origin"]
            )
            descriptor = manifest["body_descriptor"]
            self.assertEqual(descriptor["body_bytes"], len(body))
            self.assertEqual(descriptor["body_sha256"], _sha256(body))
            self.assertEqual(descriptor["row_count"], len(body.splitlines()))
            self.assertEqual(
                descriptor["maximum_row_bytes_including_lf"],
                max(len(line) + 1 for line in body.splitlines()),
            )
            self.assertGreater(descriptor["maximum_row_bytes_including_lf"], 0)
            self.assertLessEqual(
                descriptor["maximum_row_bytes_including_lf"],
                package.MAX_COMPACT_ROW_BYTES_INCLUDING_LF,
            )
            self.assertEqual(
                manifest["summary"][
                    "maximum_compact_row_bytes_including_lf"
                ],
                descriptor["maximum_row_bytes_including_lf"],
            )
            self.assertIs(descriptor["body_persisted"], True)
            self.assertIs(
                manifest["completion_claims"][
                    "expanded_effective_bodies_persisted"
                ],
                False,
            )

        p01_pilot_origin = origin_by_key[("p01", "pilot")]
        p01_pilot_descriptor = p01_pilot_origin["body_descriptor"]
        self.assertEqual(
            len(_canonical(p01_pilot_origin)), P01_PILOT_ORIGIN_MANIFEST_BYTES
        )
        self.assertEqual(
            p01_pilot_descriptor,
            {
                "body_bytes": P01_PILOT_COMPACT_BODY_BYTES,
                "body_persisted": True,
                "body_sha256": P01_PILOT_COMPACT_BODY_SHA256,
                "file_name": "p01-lifecycle-effective-membership-pilot.jsonl",
                "maximum_row_bytes_including_lf": (
                    P01_PILOT_COMPACT_MAXIMUM_ROW_BYTES_INCLUDING_LF
                ),
                "row_count": P01_PILOT_COMPACT_ROW_COUNT,
            },
        )
        self.assertEqual(
            p01_pilot_origin["summary"]["source_shard_count"], 1
        )
        self.assertEqual(
            p01_pilot_origin["summary"]["expanded_effective_body_bytes"],
            P01_PILOT_EXPANDED_SHARD_1_BODY_BYTES,
        )
        self.assertEqual(
            p01_pilot_origin["summary"][
                "maximum_expanded_row_bytes_including_lf"
            ],
            P01_PILOT_EXPANDED_MAXIMUM_ROW_BYTES_INCLUDING_LF,
        )
        p12_residual_descriptor = origin_by_key[("p12", "full-residual")][
            "body_descriptor"
        ]
        self.assertEqual(
            p12_residual_descriptor["body_bytes"],
            P12_RESIDUAL_COMPACT_BODY_BYTES,
        )
        self.assertEqual(
            p12_residual_descriptor["body_sha256"],
            P12_RESIDUAL_COMPACT_BODY_SHA256,
        )
        self.assertEqual(
            max(len(_canonical(row)) for row in self.origins),
            EXPECTED_MAXIMUM_ORIGIN_MANIFEST_BYTES,
        )
        self.assertEqual(
            max(
                row["body_descriptor"]["maximum_row_bytes_including_lf"]
                for row in self.origins
            ),
            EXPECTED_MAXIMUM_COMPACT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            max(
                row["summary"]["maximum_expanded_row_bytes_including_lf"]
                for row in self.origins
            ),
            EXPECTED_MAXIMUM_EXPANDED_ROW_BYTES_INCLUDING_LF,
        )

        for manifest in self.profiles:
            self.assertEqual(manifest["artifact_schema"], package.PROFILE_SCHEMA)
            self.assertEqual(set(manifest["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(all(flag is False for flag in manifest["authority"].values()))
            self.assertIs(manifest["g0_contract_frozen"], False)
            self.assertLessEqual(
                len(_canonical(manifest)), package.MAX_PROFILE_MANIFEST_BYTES
            )
            expected_origins = (
                ["pilot"]
                if manifest["profile"] == "pilot"
                else ["pilot", "full-residual"]
            )
            self.assertEqual(manifest["origin_order"], expected_origins)
            self.assertEqual(
                manifest["summary"]["source_count"],
                envelope.profile_file_count(
                    manifest["persona_id"], manifest["profile"]
                ),
            )
        self.assertEqual(
            max(len(_canonical(row)) for row in self.profiles),
            EXPECTED_MAXIMUM_PROFILE_MANIFEST_BYTES,
        )

        for persona_id in envelope.PERSONA_IDS:
            pilot = profile_by_key[(persona_id, "pilot")]
            full = profile_by_key[(persona_id, "full")]
            self.assertEqual(
                pilot["origin_manifest_bindings"],
                full["origin_manifest_bindings"][:1],
            )
            self.assertEqual(
                full["origin_manifest_bindings"][0]["sha256"],
                _sha256(_canonical(origin_by_key[(persona_id, "pilot")])),
            )

        suite = self.suite
        self.assertEqual(suite["artifact_schema"], package.SUITE_SCHEMA)
        self.assertEqual(set(suite["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in suite["authority"].values()))
        self.assertIs(suite["g0_contract_frozen"], False)
        suite_raw = _canonical(suite)
        self.assertLessEqual(len(suite_raw), package.MAX_SUITE_DESCRIPTOR_BYTES)
        self.assertEqual(len(suite_raw), EXPECTED_SUITE_CANONICAL_BYTES)
        self.assertEqual(_sha256(suite_raw), EXPECTED_SUITE_SHA256)
        self.assertEqual(
            suite["summary"],
            {
                "compact_companion_mirror_count": 200,
                "compact_primary_override_count": 2_000,
                "compact_row_count": 2_573,
                "compact_shard_receipt_count": 73,
                "compact_typed_witness_count": 300,
                "content_projection_count": 20,
                "effective_w0_mode_counts": package.EXPECTED_W0_MODE_COUNTS,
                "event_created_lineage_count": 3_630,
                "inverted_consumer_reference_count": 600,
                "inverted_witness_count": 300,
                "origin_manifest_count": 40,
                "persona_count": 20,
                "present_fact_reference_count": 1_033_680,
                "profile_manifest_count": 40,
                "source_count": 203_000,
            },
        )
        self.assertEqual(len(suite["origin_manifest_bindings"]), 40)
        self.assertEqual(len(suite["profile_manifest_bindings"]), 40)
        self.assertEqual(len(suite["content_projection_bindings"]), 20)
        self.assertEqual(
            max(len(_canonical(row)) for row in self.projections.values()),
            EXPECTED_MAXIMUM_CONTENT_PROJECTION_BYTES,
        )
        self.assertEqual(
            suite["effective_w0_distribution_audit"],
            {
                "fact_cardinality_counts": package.EXPECTED_W0_FACT_DISTRIBUTION,
                "mode_counts": package.EXPECTED_W0_MODE_COUNTS,
                "present_fact_reference_count": 1_033_680,
                "source_count": 203_000,
                "streamed_complete_domain_verified": True,
            },
        )
        self.assertEqual(len(suite["verification_view_receipts"]), 20)
        for receipt in suite["verification_view_receipts"]:
            self.assertIs(receipt["event_created_lineage_body_persisted"], False)
            self.assertIs(receipt["inverted_witness_body_persisted"], False)
            self.assertLessEqual(
                receipt["event_created_lineage_body_bytes"],
                package.MAX_EVENT_LINEAGE_BODY_BYTES,
            )
            self.assertLessEqual(
                receipt["inverted_witness_body_bytes"],
                package.MAX_INVERTED_BODY_BYTES,
            )

        p12_origins = [row for row in self.origins if row["persona_id"] == "p12"]
        p12_profiles = [row for row in self.profiles if row["persona_id"] == "p12"]
        p12_actual_effective_component_bytes = (
            sum(row["body_descriptor"]["body_bytes"] for row in p12_origins)
            + sum(len(_canonical(row)) for row in p12_origins)
            + sum(len(_canonical(row)) for row in p12_profiles)
            + len(_canonical(self.projections["p12"]))
        )
        self.assertGreater(p12_actual_effective_component_bytes, 0)
        self.assertLess(
            p12_actual_effective_component_bytes,
            P12_NOMINAL_PRE_SOLVE_HEADROOM_BYTES,
        )

    def test_content_projection_exact_semantic_boundary_and_query_detachment(self):
        self._ensure_package()
        totals = Counter()
        forbidden_key_tokens = {
            "answer",
            "authority",
            "base_fact_profile",
            "binding",
            "blocker",
            "chunk",
            "completion",
            "derivation",
            "distractor",
            "final",
            "final_identifier",
            "format_positive",
            "latency",
            "materialization",
            "observed",
            "oracle",
            "path",
            "physical",
            "persisted",
            "query",
            "quota",
            "rank",
            "raw_hash",
            "receipt",
            "relevance",
            "review",
            "runtime_observation",
            "scope",
            "selection_role",
            "solution",
            "source_semantic",
            "use_case",
        }
        for persona_id in envelope.PERSONA_IDS:
            projection = self.projections[persona_id]
            self.assertEqual(projection["artifact_schema"], package.PROJECTION_SCHEMA)
            self.assertEqual(
                set(projection),
                {
                    "artifact_kind",
                    "artifact_schema",
                    "artifact_schema_version",
                    "content_rules",
                    "content_sections",
                    "fixture_id",
                    "fixture_schema_version",
                    "persona_id",
                    "summary",
                },
            )
            self.assertEqual(
                projection["content_rules"],
                {
                    "base_content_context_membership_fields_must_be_removed": True,
                    "effective_membership_is_single_namespace_owner": True,
                    "event_and_inverted_views_are-input-closure-only": True,
                    "projection_excludes": [
                        "base-fact-profile-pointers",
                        "completion-and-review-state",
                        "derivation-and-verification-view-receipts",
                        "execution-and-capacity-state",
                        "full-upstream-bindings-and-digests",
                        "physical-scope-path-quota-and-identifiers",
                        (
                            "query-oracle-answer-relevance-use-case-and-"
                            "format-selection"
                        ),
                        "runtime-observations",
                    ],
                },
            )
            raw = _canonical(projection)
            self.assertLessEqual(len(raw), package.TARGET_CONTENT_PROJECTION_BYTES)
            self.assertLessEqual(len(raw), package.MAX_CONTENT_PROJECTION_BYTES)
            keys = {
                key.lower().replace("-", "_") for key in _walk_keys(projection)
            }
            for key in keys:
                self.assertFalse(
                    any(token in key for token in forbidden_key_tokens),
                    key,
                )

            sections = projection["content_sections"]
            self.assertEqual(
                set(sections),
                {
                    "effective_companion_membership_rows",
                    "effective_membership_shard_commitments",
                    "effective_primary_membership_rows",
                    "typed_purge_witness_rows",
                },
            )
            primary_rows = sections["effective_primary_membership_rows"]
            companion_rows = sections["effective_companion_membership_rows"]
            witness_rows = sections["typed_purge_witness_rows"]
            commitment_rows = sections["effective_membership_shard_commitments"]
            self.assertEqual(len(primary_rows), 100)
            self.assertEqual(len(companion_rows), 10)
            self.assertEqual(len(witness_rows), 15)
            self.assertTrue(
                all(set(row) == package.CONTENT_PRIMARY_ROW_FIELDS for row in primary_rows)
            )
            self.assertTrue(
                all(
                    set(row) == package.CONTENT_COMPANION_ROW_FIELDS
                    for row in companion_rows
                )
            )
            self.assertTrue(
                all(set(row) == package.CONTENT_WITNESS_ROW_FIELDS for row in witness_rows)
            )
            self.assertTrue(
                all(
                    set(row) == package.CONTENT_SHARD_COMMITMENT_FIELDS
                    for row in commitment_rows
                )
            )
            self.assertTrue(
                all(
                    row["row_kind"]
                    == "effective-membership-shard-content-commitment"
                    for row in commitment_rows
                )
            )
            for row in commitment_rows:
                self.assertIn("body_bytes", row)
                self.assertIn("body_sha256", row)
                self.assertNotIn("source_semantic_expanded_body_sha256", row)
                self.assertNotIn("expanded_body_persisted", row)
                self.assertNotIn("expanded_maximum_row_bytes_including_lf", row)
            totals["primary"] += len(primary_rows)
            totals["companion"] += len(companion_rows)
            totals["witness"] += len(witness_rows)
            totals["commitment"] += len(commitment_rows)
            self.assertEqual(
                projection["summary"],
                {
                    "companion_membership_row_count": len(companion_rows),
                    "effective_shard_commitment_count": len(commitment_rows),
                    "primary_membership_row_count": len(primary_rows),
                    "typed_purge_witness_row_count": len(witness_rows),
                },
            )

        self.assertEqual(
            totals,
            {"commitment": 73, "companion": 200, "primary": 2_000, "witness": 300},
        )

        baseline = package.build_lifecycle_effective_membership_content_projection(
            "p01"
        )
        baseline_raw = _canonical(baseline)
        self.assertEqual(len(baseline_raw), P01_CONTENT_PROJECTION_BYTES)
        self.assertEqual(_sha256(baseline_raw), P01_CONTENT_PROJECTION_SHA256)
        self.assertEqual(
            baseline["summary"]["effective_shard_commitment_count"],
            P01_CONTENT_PROJECTION_COMMITMENT_COUNT,
        )
        plan = copy.deepcopy(package._persona_plan("p01"))
        query_rows = plan["lifecycle"]["use_case_family_witness_rows"]
        self.assertTrue(query_rows)
        positive = next(
            row for row in query_rows if "query_anchor_ref" in row
        )
        positive["query_anchor_ref"] = "evaluation-only-mutated-anchor"
        package._canonical_content_projection.cache_clear()
        try:
            with mock.patch.object(package, "_persona_plan", return_value=plan):
                mutated = (
                    package.build_lifecycle_effective_membership_content_projection(
                        "p01"
                    )
                )
        finally:
            package._canonical_content_projection.cache_clear()
        self.assertEqual(_canonical(mutated), _canonical(baseline))

    def test_public_validators_use_independent_reconstruction_and_reject_tamper(self):
        self._ensure_package()
        origin = next(
            row
            for row in self.origins
            if row["persona_id"] == "p01" and row["origin"] == "pilot"
        )
        profile = next(
            row
            for row in self.profiles
            if row["persona_id"] == "p01" and row["profile"] == "pilot"
        )
        projection = self.projections["p01"]

        with mock.patch.object(
            package,
            "_canonical_origin_manifest",
            side_effect=AssertionError("producer exact-regeneration shortcut used"),
        ):
            self.assertIs(
                package.validate_lifecycle_effective_membership_origin_manifest(
                    "p01", "pilot", origin
                ),
                True,
            )
        with mock.patch.object(
            package,
            "_canonical_profile_manifest",
            side_effect=AssertionError("producer exact-regeneration shortcut used"),
        ):
            self.assertIs(
                package.validate_lifecycle_effective_membership_profile_manifest(
                    "p01", "pilot", profile
                ),
                True,
            )
        with mock.patch.object(
            package,
            "_canonical_content_projection",
            side_effect=AssertionError("producer exact-regeneration shortcut used"),
        ):
            self.assertIs(
                package.validate_lifecycle_effective_membership_content_projection(
                    "p01", projection
                ),
                True,
            )

        with mock.patch.object(
            package, "_independent_validator", return_value=None
        ):
            for validate_without_independent in (
                lambda: package.validate_lifecycle_effective_membership_origin_manifest(
                    "p01", "pilot", origin
                ),
                lambda: package.validate_lifecycle_effective_membership_profile_manifest(
                    "p01", "pilot", profile
                ),
                lambda: package.validate_lifecycle_effective_membership_content_projection(
                    "p01", projection
                ),
                lambda: package.validate_lifecycle_effective_membership_suite_descriptor(
                    self.suite
                ),
            ):
                with self.assertRaisesRegex(
                    package.PersonaV2LifecycleEffectiveMembershipReconciliationError,
                    "producer-independent.*required",
                ):
                    validate_without_independent()

        for target, mutate, validate in (
            (
                origin,
                lambda value: value["authority"].__setitem__(
                    "authorizes_g0_freeze", True
                ),
                lambda value: package.validate_lifecycle_effective_membership_origin_manifest(
                    "p01", "pilot", value
                ),
            ),
            (
                profile,
                lambda value: value.__setitem__("unexpected", False),
                lambda value: package.validate_lifecycle_effective_membership_profile_manifest(
                    "p01", "pilot", value
                ),
            ),
            (
                projection,
                lambda value: value["content_sections"].__setitem__(
                    "query_rows", []
                ),
                lambda value: package.validate_lifecycle_effective_membership_content_projection(
                    "p01", value
                ),
            ),
        ):
            tampered = copy.deepcopy(target)
            mutate(tampered)
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                validate(tampered)

        for bad_persona in (None, True, "p00"):
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                package.build_lifecycle_effective_membership_origin_manifest(
                    bad_persona, "pilot"
                )
        for bad_origin in (None, True, "full"):
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                package.build_lifecycle_effective_membership_origin_manifest(
                    "p01", bad_origin
                )
        for bad_profile in (None, True, "full-residual"):
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                package.build_lifecycle_effective_membership_profile_manifest(
                    "p01", bad_profile
                )
        for bad_scalar in (None, True, -1, 1.5, package.MAX_ORIGIN_ROWS + 1):
            tampered = copy.deepcopy(origin)
            tampered["summary"]["source_count"] = bad_scalar
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                package.validate_lifecycle_effective_membership_origin_manifest(
                    "p01", "pilot", tampered
                )

        for mutate_projection in (
            lambda value: value["content_sections"][
                "effective_primary_membership_rows"
            ].pop(),
            lambda value: value["content_sections"][
                "effective_primary_membership_rows"
            ].append(
                copy.deepcopy(
                    value["content_sections"][
                        "effective_primary_membership_rows"
                    ][0]
                )
            ),
            lambda value: value["content_sections"][
                "effective_primary_membership_rows"
            ].__setitem__(
                slice(0, 2),
                list(
                    reversed(
                        value["content_sections"][
                            "effective_primary_membership_rows"
                        ][:2]
                    )
                ),
            ),
        ):
            tampered = copy.deepcopy(projection)
            mutate_projection(tampered)
            with self.assertRaises(
                package.PersonaV2LifecycleEffectiveMembershipReconciliationError
            ):
                package.validate_lifecycle_effective_membership_content_projection(
                    "p01", tampered
                )

    def test_sha_helpers_hash_the_authenticated_opening_snapshot(self):
        cases = (
            (
                "validate_lifecycle_effective_membership_origin_manifest",
                lambda value: package.lifecycle_effective_membership_origin_manifest_sha256(
                    "p01", "pilot", value
                ),
                package.ORIGIN_SCHEMA,
            ),
            (
                "validate_lifecycle_effective_membership_profile_manifest",
                lambda value: package.lifecycle_effective_membership_profile_manifest_sha256(
                    "p01", "pilot", value
                ),
                package.PROFILE_SCHEMA,
            ),
            (
                "validate_lifecycle_effective_membership_suite_descriptor",
                package.lifecycle_effective_membership_suite_sha256,
                package.SUITE_SCHEMA,
            ),
            (
                "validate_lifecycle_effective_membership_content_projection",
                lambda value: package.lifecycle_effective_membership_content_projection_sha256(
                    "p01", value
                ),
                package.PROJECTION_SCHEMA,
            ),
        )
        for validator_name, sha_helper, schema in cases:
            with self.subTest(validator=validator_name):
                caller_owned = {
                    "artifact_schema": schema,
                    "opening_marker": "authenticated-opening",
                }
                opening_raw = _canonical(caller_owned)

                def mutate_after_snapshot(*args):
                    snapshot = args[-1]
                    self.assertIsNot(snapshot, caller_owned)
                    self.assertEqual(_canonical(snapshot), opening_raw)
                    caller_owned["opening_marker"] = "mutated-after-validation"
                    return True

                with mock.patch.object(
                    package, validator_name, side_effect=mutate_after_snapshot
                ) as validator:
                    digest = sha_helper(caller_owned)
                validator.assert_called_once()
                self.assertEqual(digest, _sha256(opening_raw))

    def test_origin_body_provider_bounds_replay_and_caller_toctou(self):
        self._ensure_package()
        origin = next(
            row
            for row in self.origins
            if row["persona_id"] == "p01" and row["origin"] == "pilot"
        )
        compact = package.lifecycle_effective_membership_origin_body_bytes(
            "p01", "pilot"
        )

        calls = []

        def nondeterministic_compact(*args):
            calls.append(args)
            if len(calls) == 1:
                return compact
            return compact[:-1] + b" "

        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01",
                "pilot",
                origin,
                compact_body_provider=nondeterministic_compact,
                expanded_w0_body_provider=(
                    package.expanded_effective_w0_membership_shard_body_bytes
                ),
            )
        self.assertEqual(len(calls), 2)

        calls.clear()

        def wrong_type(*args):
            calls.append(args)
            return bytearray(compact)

        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01",
                "pilot",
                origin,
                compact_body_provider=wrong_type,
                expanded_w0_body_provider=(
                    package.expanded_effective_w0_membership_shard_body_bytes
                ),
            )
        self.assertEqual(len(calls), 1)

        expanded = package.expanded_effective_w0_membership_shard_body_bytes(
            "p01", "pilot", 1
        )

        for second_return in (
            expanded[:-1] + b" ",
            b"x" * (package.MAX_EXPANDED_SHARD_BODY_BYTES + 1),
        ):
            expanded_calls = []

            def unstable_expanded(*args, _second=second_return):
                expanded_calls.append(args)
                return expanded if len(expanded_calls) == 1 else _second

            with self.assertRaises(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
            ):
                independent.validate_lifecycle_effective_membership_origin_manifest(
                    "p01",
                    "pilot",
                    origin,
                    compact_body_provider=(
                        package.lifecycle_effective_membership_origin_body_bytes
                    ),
                    expanded_w0_body_provider=unstable_expanded,
                )
            self.assertEqual(
                expanded_calls,
                [("p01", "pilot", 1), ("p01", "pilot", 1)],
            )

        class BytesSubclass(bytes):
            pass

        expanded_calls = []

        def expanded_subclass(*args):
            expanded_calls.append(args)
            return BytesSubclass(expanded)

        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01",
                "pilot",
                origin,
                compact_body_provider=(
                    package.lifecycle_effective_membership_origin_body_bytes
                ),
                expanded_w0_body_provider=expanded_subclass,
            )
        self.assertEqual(expanded_calls, [("p01", "pilot", 1)])

        malformed = copy.deepcopy(origin)
        malformed["body_descriptor"]["body_bytes"] = True
        calls.clear()
        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01",
                "pilot",
                malformed,
                compact_body_provider=wrong_type,
                expanded_w0_body_provider=(
                    package.expanded_effective_w0_membership_shard_body_bytes
                ),
            )
        self.assertEqual(calls, [])

        for invalid_expected_bytes in (
            True,
            package.MAX_ORIGIN_BODY_BYTES + 1,
        ):
            calls.clear()
            with self.assertRaises(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
            ):
                independent._authenticated_body(
                    wrong_type,
                    ("p01", "pilot"),
                    expected_bytes=invalid_expected_bytes,
                    expected_sha256=_sha256(compact),
                    hard_cap=package.MAX_ORIGIN_BODY_BYTES,
                    label="test compact receipt",
                )
            self.assertEqual(calls, [])

        caller_owned = copy.deepcopy(origin)
        calls.clear()

        def persistent_caller_mutation(*args):
            calls.append(args)
            caller_owned["summary"]["source_count"] = 0
            return compact

        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent.validate_lifecycle_effective_membership_origin_manifest(
                "p01",
                "pilot",
                caller_owned,
                compact_body_provider=persistent_caller_mutation,
                expanded_w0_body_provider=(
                    package.expanded_effective_w0_membership_shard_body_bytes
                ),
            )
        self.assertEqual(len(calls), 2)


class LifecycleEffectiveMembershipFullStreamingTest(unittest.TestCase):
    """Long full-row gate kept separate from the compact package tests."""

    def test_all_203000_effective_rows_modes_facts_and_i5_exact_inheritance(self):
        semantic_catalog = source_semantic.build_source_semantic_membership_catalog()
        profile_kind_by_id = {
            row["fact_profile_id"]: row["profile_kind"]
            for row in semantic_catalog["fact_profiles"]
        }
        mode_counts = Counter()
        fact_distribution = Counter()
        seen_coordinates = set()
        present_fact_references = 0
        shard_count = 0
        incidental_seen = set()
        witness_consumers = defaultdict(list)
        sample_effective = None

        for persona_id in envelope.PERSONA_IDS:
            lifecycle = matched_lifecycle.build_source_matched_lifecycle_persona(
                persona_id
            )
            incidental_keys = {
                row["intent_key"]
                for row in lifecycle["primary_match_rows"]
                if row["gate_role"] == "incidental_searchable"
            }
            self.assertEqual(len(incidental_keys), 5)

            for origin in package.ORIGIN_ORDER:
                source_manifest = source_package.build_source_intent_origin_manifest(
                    persona_id, origin
                )
                for shard_ordinal in range(
                    1, len(source_manifest["shard_descriptors"]) + 1
                ):
                    shard_count += 1
                    base_rows = list(
                        source_semantic.iter_expanded_fact_membership_rows(
                            persona_id, origin, shard_ordinal
                        )
                    )
                    effective_rows = list(
                        package.iter_expanded_effective_w0_membership_rows(
                            persona_id, origin, shard_ordinal
                        )
                    )
                    self.assertEqual(len(effective_rows), len(base_rows))
                    body = package.expanded_effective_w0_membership_shard_body_bytes(
                        persona_id, origin, shard_ordinal
                    )
                    self.assertEqual(
                        effective_rows,
                        _jsonl_rows(
                            body,
                            row_cap=package.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF,
                        ),
                    )
                    self.assertLessEqual(
                        len(body), package.MAX_EXPANDED_SHARD_BODY_BYTES
                    )
                    if (persona_id, origin, shard_ordinal) == (
                        "p01",
                        "pilot",
                        1,
                    ):
                        self.assertEqual(
                            len(body), P01_PILOT_EXPANDED_SHARD_1_BODY_BYTES
                        )
                        self.assertEqual(
                            max(len(line) + 1 for line in body.splitlines()),
                            P01_PILOT_EXPANDED_MAXIMUM_ROW_BYTES_INCLUDING_LF,
                        )

                    for base, effective in zip(base_rows, effective_rows):
                        if sample_effective is None:
                            sample_effective = copy.deepcopy(effective)
                        self.assertEqual(set(effective), package.EXPANDED_W0_ROW_FIELDS)
                        self.assertEqual(effective["intent_key"], base["intent_key"])
                        self.assertEqual(effective["persona_id"], persona_id)
                        self.assertEqual(effective["origin"], origin)
                        coordinate = (persona_id, origin, effective["intent_key"])
                        self.assertNotIn(coordinate, seen_coordinates)
                        seen_coordinates.add(coordinate)
                        mode = effective["effective_membership_mode"]
                        mode_counts[mode] += 1
                        present_fact_references += len(effective["present_fact_ids"])

                        if effective["witness_fact_ids"]:
                            self.assertEqual(mode, "graph-normal-plus-witness")
                            self.assertEqual(len(effective["witness_fact_ids"]), 1)
                            self.assertEqual(len(effective["present_fact_ids"]), 9)
                            fact_distribution["graph-normal-plus-witness"] += 1
                            witness_consumers[
                                effective["witness_fact_ids"][0]
                            ].append(
                                {
                                    "consumer_domain": "w0-source",
                                    "consumer_role": "matching-w0-p-primary",
                                    "event_intent_key": "not-applicable-w0",
                                    "source_intent_key": effective["intent_key"],
                                }
                            )
                        elif mode in {"companion-mirror", "graph-normal"}:
                            self.assertEqual(len(effective["present_fact_ids"]), 8)
                            fact_distribution["graph-normal-only"] += 1
                        else:
                            self.assertEqual(mode, "base-inheritance")
                            kind = profile_kind_by_id[base["fact_profile_id"]]
                            mapped = {
                                "conflict-branch": "conflict-branch",
                                "empty": "empty",
                                "graph-normal-w0": "graph-normal-only",
                                "w0-singleton": "singleton",
                            }[kind]
                            fact_distribution[mapped] += 1

                        if effective["intent_key"] in incidental_keys:
                            incidental_seen.add(effective["intent_key"])
                            self.assertEqual(mode, "base-inheritance")
                            self.assertEqual(
                                effective["present_fact_ids"], base["present_fact_ids"]
                            )
                            self.assertEqual(
                                effective["present_fact_set_key"],
                                base["present_fact_set_key"],
                            )
                            self.assertEqual(
                                effective["lifecycle_branch_key"],
                                base["logical_branch_key"],
                            )
                            self.assertEqual(
                                effective["lifecycle_logical_document_key"],
                                base["logical_document_key"],
                            )
                            expected_chain_digest = hashlib.sha256(
                                (
                                    base["logical_document_key"]
                                    + "\x00"
                                    + base["logical_branch_key"]
                                ).encode("utf-8")
                            ).hexdigest()[:24]
                            self.assertEqual(
                                effective["lifecycle_revision_chain_key"],
                                (
                                    f"{persona_id}-base-revision-chain-"
                                    f"{expected_chain_digest}-v1"
                                ),
                            )
                            self.assertEqual(
                                effective["logical_revision_key"],
                                base["logical_revision_key"],
                            )
                            self.assertEqual(
                                effective["semantic_section_key"],
                                base["semantic_section_key"],
                            )
                            self.assertEqual(
                                effective["projection_mode"], base["projection_mode"]
                            )
                            self.assertEqual(effective["witness_fact_ids"], [])

        self.assertEqual(shard_count, EXPECTED_SOURCE_SHARD_COUNT)
        self.assertEqual(len(seen_coordinates), EXPECTED_W0_SOURCE_COUNT)
        self.assertEqual(len(incidental_seen), EXPECTED_I5_COUNT)
        self.assertEqual(mode_counts, package.EXPECTED_W0_MODE_COUNTS)
        self.assertEqual(fact_distribution, package.EXPECTED_W0_FACT_DISTRIBUTION)
        self.assertEqual(
            present_fact_references,
            package.EXPECTED_PRESENT_FACT_REFERENCE_COUNT,
        )

        for persona_id in envelope.PERSONA_IDS:
            for row in package.iter_event_created_witness_lineage_rows(persona_id):
                for witness_fact_id in row["present_purge_witness_fact_ids"]:
                    witness_consumers[witness_fact_id].append(
                        {
                            "consumer_domain": "event-created-source",
                            "consumer_role": row["consumer_role"],
                            "event_intent_key": row["event_intent_key"],
                            "source_intent_key": row["after_source_intent_key"],
                        }
                    )
        inverted = list(package.iter_inverted_purge_witness_rows())
        self.assertEqual(len(witness_consumers), EXPECTED_PURGE_WITNESS_COUNT)
        self.assertEqual(set(witness_consumers), {
            row["witness_fact_id"] for row in inverted
        })
        for row in inverted:
            self.assertEqual(
                row["consumer_refs"], witness_consumers[row["witness_fact_id"]]
            )

        self.assertIsNotNone(sample_effective)
        unknown_w0 = copy.deepcopy(sample_effective)
        unknown_w0["present_fact_ids"].append(
            "purge-witness-fact-unknown-syn-999"
        )
        unknown_w0["witness_fact_ids"] = [
            "purge-witness-fact-unknown-syn-999"
        ]
        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent._audit_w0_row(independent._new_suite_audit(), unknown_w0)

        unknown_event = next(
            row
            for persona_id in envelope.PERSONA_IDS
            for row in package.iter_event_created_witness_lineage_rows(persona_id)
        )
        unknown_event = copy.deepcopy(unknown_event)
        unknown_event["present_purge_witness_fact_ids"] = [
            "purge-witness-fact-unknown-syn-999"
        ]
        with self.assertRaises(
            independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
        ):
            independent._audit_event_lineage_row(
                independent._new_suite_audit(), unknown_event
            )

    def test_independent_full_suite_acceptance_and_target_snapshot(self):
        suite = package.build_lifecycle_effective_membership_suite_descriptor()
        with mock.patch.object(
            package,
            "_canonical_suite_descriptor",
            side_effect=AssertionError("producer suite comparison shortcut used"),
        ):
            self.assertIs(
                package.validate_lifecycle_effective_membership_suite_descriptor(
                    suite
                ),
                True,
            )
        independent_projection = independent._expected_content_projection("p01")
        self.assertNotIn("authority", independent_projection)
        independent_suite = independent._expected_suite_descriptor()
        self.assertTrue(
            all(
                "authority" not in binding
                for binding in independent_suite["content_projection_bindings"]
            )
        )

        calls = []

        def must_not_run(*args):
            calls.append(args)
            raise AssertionError("provider called for an invalid opening target")

        tampered_source_count = copy.deepcopy(suite)
        tampered_source_count["summary"]["source_count"] = 0
        tampered_authority = copy.deepcopy(suite)
        tampered_authority["authority"]["authorizes_g0_freeze"] = True
        for tampered in (tampered_source_count, tampered_authority):
            with self.assertRaises(
                independent.PersonaV2LifecycleEffectiveMembershipReconciliationValidationError
            ):
                independent.validate_lifecycle_effective_membership_suite_descriptor(
                    tampered,
                    origin_manifest_provider=must_not_run,
                    profile_manifest_provider=must_not_run,
                    compact_body_provider=must_not_run,
                    expanded_w0_body_provider=must_not_run,
                    event_lineage_provider=must_not_run,
                    inverted_provider=must_not_run,
                    content_projection_provider=must_not_run,
                )
            self.assertEqual(calls, [])


class LifecycleEffectiveMembershipColdBuildTest(unittest.TestCase):
    """Cold hash-seed/resource gate kept separate for CI timeout accounting."""

    def test_two_hashseeds_are_canonical_and_bounded(self):
        script = r'''
import hashlib
import json
import resource
import sys
from eval import persona_v2_contract as envelope
from eval import persona_v2_lifecycle_effective_membership_reconciliation as p

suite = p.build_lifecycle_effective_membership_suite_descriptor()
suite_raw = p.canonical_json_bytes(suite)
origins = [
    p.build_lifecycle_effective_membership_origin_manifest(persona, origin)
    for persona in envelope.PERSONA_IDS for origin in p.ORIGIN_ORDER
]
profiles = [
    p.build_lifecycle_effective_membership_profile_manifest(persona, profile)
    for persona in envelope.PERSONA_IDS for profile in p.PROFILE_ORDER
]
projections = [
    p.build_lifecycle_effective_membership_content_projection(persona)
    for persona in envelope.PERSONA_IDS
]
event_bodies = [
    p.lifecycle_effective_membership_event_created_lineage_body_bytes(persona)
    for persona in envelope.PERSONA_IDS
]
inverted_body = p.lifecycle_effective_membership_inverted_witness_body_bytes()
p01_pilot_body = p.lifecycle_effective_membership_origin_body_bytes("p01", "pilot")
p12_residual_body = p.lifecycle_effective_membership_origin_body_bytes(
    "p12", "full-residual"
)
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "maximum_compact_row_bytes": max(
        row["body_descriptor"]["maximum_row_bytes_including_lf"]
        for row in origins
    ),
    "maximum_event_row_bytes": max(
        len(line) + 1 for body in event_bodies for line in body.splitlines()
    ),
    "maximum_expanded_row_bytes": max(
        row["summary"]["maximum_expanded_row_bytes_including_lf"]
        for row in origins
    ),
    "maximum_inverted_row_bytes": max(
        len(line) + 1 for line in inverted_body.splitlines()
    ),
    "maximum_origin_bytes": max(len(p.canonical_json_bytes(row)) for row in origins),
    "maximum_profile_bytes": max(len(p.canonical_json_bytes(row)) for row in profiles),
    "maximum_projection_bytes": max(len(p.canonical_json_bytes(row)) for row in projections),
    "p01_pilot_compact_body_bytes": len(p01_pilot_body),
    "p01_pilot_compact_body_sha256": hashlib.sha256(p01_pilot_body).hexdigest(),
    "p12_residual_compact_body_bytes": len(p12_residual_body),
    "p12_residual_compact_body_sha256": hashlib.sha256(p12_residual_body).hexdigest(),
    "rss_bytes": rss,
    "suite_bytes": len(suite_raw),
    "suite_sha256": hashlib.sha256(suite_raw).hexdigest(),
    "summary": suite["summary"],
}, sort_keys=True, separators=(",", ":")))
'''
        outputs = []
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment["PYTHONHASHSEED"] = seed
            completed = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                capture_output=True,
                check=True,
                text=True,
                timeout=MAX_COLD_BUILD_SECONDS,
            )
            outputs.append(json.loads(completed.stdout.strip().splitlines()[-1]))

        stable = [
            {key: value for key, value in row.items() if key != "rss_bytes"}
            for row in outputs
        ]
        self.assertEqual(stable[0], stable[1])
        for row in outputs:
            self.assertLessEqual(row["rss_bytes"], MAX_COLD_BUILD_RSS_BYTES)
            self.assertEqual(
                row["maximum_compact_row_bytes"],
                EXPECTED_MAXIMUM_COMPACT_ROW_BYTES_INCLUDING_LF,
            )
            self.assertEqual(
                row["maximum_expanded_row_bytes"],
                EXPECTED_MAXIMUM_EXPANDED_ROW_BYTES_INCLUDING_LF,
            )
            self.assertEqual(
                row["maximum_event_row_bytes"],
                EXPECTED_MAXIMUM_EVENT_LINEAGE_ROW_BYTES_INCLUDING_LF,
            )
            self.assertEqual(
                row["maximum_inverted_row_bytes"],
                EXPECTED_MAXIMUM_INVERTED_ROW_BYTES_INCLUDING_LF,
            )
            self.assertLessEqual(
                row["maximum_origin_bytes"], package.MAX_ORIGIN_MANIFEST_BYTES
            )
            self.assertEqual(
                row["maximum_origin_bytes"],
                EXPECTED_MAXIMUM_ORIGIN_MANIFEST_BYTES,
            )
            self.assertLessEqual(
                row["maximum_profile_bytes"], package.MAX_PROFILE_MANIFEST_BYTES
            )
            self.assertEqual(
                row["maximum_profile_bytes"],
                EXPECTED_MAXIMUM_PROFILE_MANIFEST_BYTES,
            )
            self.assertLessEqual(
                row["maximum_projection_bytes"],
                package.TARGET_CONTENT_PROJECTION_BYTES,
            )
            self.assertEqual(
                row["maximum_projection_bytes"],
                EXPECTED_MAXIMUM_CONTENT_PROJECTION_BYTES,
            )
            self.assertLessEqual(
                row["suite_bytes"], package.MAX_SUITE_DESCRIPTOR_BYTES
            )
            self.assertEqual(row["suite_bytes"], EXPECTED_SUITE_CANONICAL_BYTES)
            self.assertEqual(row["suite_sha256"], EXPECTED_SUITE_SHA256)
            self.assertEqual(
                row["p01_pilot_compact_body_bytes"],
                P01_PILOT_COMPACT_BODY_BYTES,
            )
            self.assertEqual(
                row["p01_pilot_compact_body_sha256"],
                P01_PILOT_COMPACT_BODY_SHA256,
            )
            self.assertEqual(
                row["p12_residual_compact_body_bytes"],
                P12_RESIDUAL_COMPACT_BODY_BYTES,
            )
            self.assertEqual(
                row["p12_residual_compact_body_sha256"],
                P12_RESIDUAL_COMPACT_BODY_SHA256,
            )
            self.assertEqual(row["summary"]["source_count"], 203_000)
            self.assertEqual(row["summary"]["compact_row_count"], 2_573)


if __name__ == "__main__":
    unittest.main()
