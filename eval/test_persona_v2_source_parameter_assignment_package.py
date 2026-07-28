"""Regression gates for persona-v2 source-parameter assignment.

The package under test is deliberately pre-solve.  It owns content parameter
cells and a deterministic mapping from the 203,000 structural ``intent_key``
values to those cells, but it must never acquire scope, quota, final-ID,
rendering, history, evaluation, or G0 authority.

The expensive complete build is lazy and shared by the in-process tests.  A
separate, seeded subprocess later in this file is the cold-build runtime/RSS
and reproducibility gate.
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
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from unittest import mock

from eval import persona_v2_aggregate_byte_distribution_catalog as aggregate
from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_concrete_overlay_membership_package as concrete
from eval import persona_v2_contract as envelope
from eval import persona_v2_source_inventory_package as source_package
from eval import persona_v2_source_parameter_assignment_package as package
from eval import (
    persona_v2_source_parameter_assignment_package_validator as independent,
)


EXPECTED_SOURCE_COUNT = 203_000
EXPECTED_PILOT_SOURCE_COUNT = 20_300
EXPECTED_RESIDUAL_SOURCE_COUNT = 182_700
EXPECTED_GLOBAL_CELL_COUNT = 363
EXPECTED_PERSONA_CELL_COUNT = 2_643
EXPECTED_ORIGIN_COUNT = 40
EXPECTED_PROFILE_COUNT = 40
EXPECTED_ORIGIN_OWNER_ROW_COUNT = 4_759
EXPECTED_EXPANDED_RECEIPT_COUNT = 73
EXPECTED_EXPANDED_BODY_BYTES = 17_527_680
EXPECTED_MAX_EXPANDED_BODY_BYTES = 367_471
EXPECTED_MAX_EXPANDED_ROW_BYTES = 110
EXPECTED_EXACT_PAIR_COUNT = 5_080
EXPECTED_PILOT_EXACT_PAIR_COUNT = 508
EXPECTED_RESIDUAL_EXACT_PAIR_COUNT = 4_572
EXPECTED_PAIR_BEARING_COORDINATE_COUNT = 485
EXPECTED_EML_SOURCE_COUNT = 9_153
EXPECTED_EML_HOST_COUNT = 2_800
EXPECTED_EML_NONHOST_COUNT = 6_353
EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT = 5_690
EXPECTED_NON_EML_SINGLETON_COUNT = 183_687

# The final suite pin is repeated here, rather than merely copied from either
# implementation, so accidental coordinated repinning is visible in review.
# It is updated only after the producer-independent validator accepts the
# complete package and the cold-build resource gate passes.
EXPECTED_SUITE_BYTES = 72_535
EXPECTED_SUITE_SHA256 = (
    "ed95d7875cb961d4fa054f6fa8a8a281cf6906724bc5f2524d9d046b2c3e8f1a"
)
EXPECTED_CELL_CATALOG_BYTES = 106_162
EXPECTED_DIRECT_PARAMETER_INPUTS = {
    "persona-v2-aggregate-byte-distribution-catalog": (
        1_576_125,
        "9bef8b1af10411bb1e8cc662aa95a64e155ea81e3db7e1be56433e83539450d2",
    ),
    "persona-v2-overlay-compatible-byte-distribution": (
        91_039,
        "a9e214e5dde82edf4967d5502f15fd92ffa6a1016c67a177dd574835a9962ddc",
    ),
    "persona-v2-formal-source-recipe-profile-catalog": (
        386_152,
        "0ac0906397c8d81b7504637fe119d45ae2ffa7acb7cb47b719c985121ce1b2df",
    ),
}
EXPECTED_DIRECT_PARAMETER_INPUT_BYTES = 2_053_316
EXPECTED_P12_LEDGER = {
    "expanded_view_body_bytes_excluded_nonpersisted": 1_370_715,
    "known_pre_solve_component_bytes": 15_573_860,
    "origin_manifest_bytes_including_compact_owner_rows": 65_847,
    "parameter_cell_projection_bytes": 19_130,
    "parameter_extension_bytes": 2_298_188,
    "profile_manifest_bytes": 53_733,
    "remaining_bytes_before_nominal_cap_not_a_completion_proof": 1_203_356,
    "shared_parameter_cell_catalog_bytes_charged_once": 106_162,
    "shared_direct_parameter_input_body_bytes_charged_once": 2_053_316,
    "upstream_concrete_current_component_bytes": 13_275_672,
}

MAX_COLD_BUILD_SECONDS = 15 * 60
MAX_COLD_BUILD_RSS_BYTES = 512 * 2**20

CELL_FIELDS = frozenset(
    {
        "bin_id",
        "parameter_cell_key",
        "recipe_profile_id",
        "renderer_parameters",
        "size_lane",
        "target_bytes",
        "target_complexity",
        "variant_id",
    }
)
PROJECTION_ROW_FIELDS = frozenset(
    {"counts", "parameter_cell_key", "variant_id"}
)
COMPACT_OWNER_ROW_FIELDS = frozenset(
    {
        "eml_fixed_intent_count",
        "exact_pair_endpoint_count",
        "exact_pair_unit_count",
        "parameter_cell_key",
        "singleton_intent_count",
        "source_count",
        "variant_id",
    }
)
PROFILE_ROW_FIELDS = frozenset(
    {
        "eml_fixed_intent_count",
        "exact_pair_endpoint_count",
        "exact_pair_unit_count",
        "parameter_cell_key",
        "singleton_intent_count",
        "source_count",
    }
)
EXPANDED_ROW_FIELDS = frozenset({"intent_key", "parameter_cell_key"})
EXPANDED_RECEIPT_FIELDS = frozenset(
    {
        "expanded_body_bytes",
        "expanded_body_persisted",
        "expanded_body_sha256",
        "first_intent_key",
        "last_intent_key",
        "maximum_row_bytes_including_lf",
        "origin",
        "persona_id",
        "row_count",
        "shard_ordinal",
        "source_shard_body_bytes",
        "source_shard_body_sha256",
        "source_shard_id",
    }
)
COMMON_ARTIFACT_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "completion_scope",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
    }
)
CATALOG_TOP_LEVEL_FIELDS = COMMON_ARTIFACT_FIELDS | {
    "canonical_limits",
    "completion_claims",
    "input_binding_order",
    "input_bindings",
    "orders",
    "parameter_cells",
    "remaining_blockers",
    "summary",
}
PROJECTION_TOP_LEVEL_FIELDS = COMMON_ARTIFACT_FIELDS | {
    "canonical_limits",
    "cell_count_rows",
    "completion_claims",
    "input_binding_order",
    "input_bindings",
    "orders",
    "persona_id",
    "remaining_blockers",
    "summary",
}
ORIGIN_TOP_LEVEL_FIELDS = COMMON_ARTIFACT_FIELDS | {
    "canonical_limits",
    "compact_assignment_rows",
    "completion_claims",
    "dependency_direction_contract",
    "expanded_view_receipts",
    "input_binding_order",
    "input_bindings",
    "orders",
    "origin",
    "persona_id",
    "remaining_blockers",
    "selection_policy",
    "summary",
}
PROFILE_TOP_LEVEL_FIELDS = COMMON_ARTIFACT_FIELDS | {
    "canonical_limits",
    "completion_claims",
    "composition_contract",
    "input_binding_order",
    "input_bindings",
    "orders",
    "origin_manifest_bindings",
    "persona_id",
    "profile",
    "profile_cell_count_rows",
    "remaining_blockers",
    "summary",
}
SUITE_TOP_LEVEL_FIELDS = COMMON_ARTIFACT_FIELDS | {
    "canonical_limits",
    "completion_claims",
    "coverage",
    "dependency_direction_contract",
    "input_binding_order",
    "input_bindings",
    "orders",
    "origin_manifest_bindings",
    "persona_cell_projection_bindings",
    "persona_parameter_component_byte_ledgers",
    "profile_manifest_bindings",
    "remaining_blockers",
}

FORBIDDEN_KEYS = frozenset(
    {
        "answer",
        "bucket",
        "bucket_id",
        "bucket_key",
        "cell_local_ordinal",
        "chunk_quota",
        "cohort",
        "cohort_id",
        "cohort_key",
        "final_id",
        "final_materialization_id",
        "final_source_id",
        "lifecycle_demand",
        "lifecycle_demand_id",
        "materialization_id",
        "materialization_key",
        "oracle",
        "oracle_id",
        "path",
        "payload",
        "query",
        "query_id",
        "quota",
        "raw_hash",
        "requested_chunks",
        "semantic_payload",
        "scope",
        "scope_id",
        "scope_key",
        "source_id",
        "source_key",
    }
)


def _canonical_fragment(value, *, label="assignment test value", max_bytes=8 * 2**20):
    return artifact_common.canonical_json_bytes(
        value,
        label=label,
        max_bytes=max_bytes,
    )


def _jsonl_rows(body):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        raise AssertionError("expanded assignment body must be non-empty LF JSONL")
    if b"\r" in body or body.endswith(b"\n\n"):
        raise AssertionError("expanded assignment body framing drifted")
    rows = []
    for raw in body.splitlines():
        if len(raw) + 1 > package.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF:
            raise AssertionError("expanded assignment row exceeds its cap")
        row = json.loads(raw.decode("utf-8", "strict"))
        if set(row) != EXPANDED_ROW_FIELDS:
            raise AssertionError("expanded assignment row schema drifted")
        if _canonical_fragment(
            row,
            label="expanded assignment test row",
            max_bytes=package.MAX_EXPANDED_ROW_BYTES_INCLUDING_LF - 1,
        ) != raw:
            raise AssertionError("expanded assignment row is not canonical JSON")
        rows.append(row)
    return rows


def _walk_dicts(value):
    if type(value) is dict:
        yield value
        for child in value.values():
            yield from _walk_dicts(child)
    elif type(value) is list:
        for child in value:
            yield from _walk_dicts(child)


def _assert_no_forbidden_keys(testcase, value):
    for mapping in _walk_dicts(value):
        testcase.assertFalse(
            set(mapping) & FORBIDDEN_KEYS,
            f"forbidden solved/evaluation fields: {set(mapping) & FORBIDDEN_KEYS}",
        )


def _all_false_authority(testcase, value):
    testcase.assertIs(value["g0_contract_frozen"], False)
    testcase.assertEqual(set(value["authority"]), package.AUTHORITY_FIELDS)
    testcase.assertTrue(
        all(type(flag) is bool and flag is False for flag in value["authority"].values())
    )


def _binding_key(binding):
    return tuple(
        binding.get(field)
        for field in ("persona_id", "origin", "profile")
        if field in binding
    )


def _refresh_binding(binding, value, *, maximum):
    raw = _canonical_fragment(
        value,
        label="rethreaded source parameter test artifact",
        max_bytes=maximum,
    )
    binding["canonical_bytes"] = len(raw)
    binding["sha256"] = hashlib.sha256(raw).hexdigest()


class PersonaV2SourceParameterAssignmentPackageTests(unittest.TestCase):
    """Full package assertions, with one shared in-process artifact graph."""

    catalog = None
    projections = None
    origins = None
    profiles = None
    suite = None
    bodies = None

    @classmethod
    def _ensure_package(cls):
        if cls.suite is not None:
            return
        cls.catalog = package.build_source_parameter_cell_catalog()
        cls.projections = [
            package.build_source_parameter_cell_projection(persona_id)
            for persona_id in envelope.PERSONA_IDS
        ]
        cls.origins = [
            package.build_source_parameter_assignment_origin_manifest(
                persona_id, origin
            )
            for persona_id in envelope.PERSONA_IDS
            for origin in package.ORIGIN_ORDER
        ]
        cls.profiles = [
            package.build_source_parameter_assignment_profile_manifest(
                persona_id, profile
            )
            for persona_id in envelope.PERSONA_IDS
            for profile in package.PROFILE_ORDER
        ]
        cls.suite = package.build_source_parameter_assignment_suite_descriptor()

    @classmethod
    def _ensure_bodies(cls):
        cls._ensure_package()
        if cls.bodies is not None:
            return
        bodies = {}
        for origin in cls.origins:
            for receipt in origin["expanded_view_receipts"]:
                coordinate = (
                    receipt["persona_id"],
                    receipt["origin"],
                    receipt["shard_ordinal"],
                )
                bodies[coordinate] = (
                    package.source_parameter_assignment_expanded_view_body_bytes(
                        *coordinate
                    )
                )
        cls.bodies = bodies

    @classmethod
    def _origin_by_key(cls):
        cls._ensure_package()
        return {
            (value["persona_id"], value["origin"]): value
            for value in cls.origins
        }

    @classmethod
    def _profile_by_key(cls):
        cls._ensure_package()
        return {
            (value["persona_id"], value["profile"]): value
            for value in cls.profiles
        }

    def test_exact_frozen_suite_counts_caps_and_component_status(self):
        self._ensure_package()
        raw = package.canonical_json_bytes(self.suite)
        self.assertEqual(len(raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SUITE_SHA256)
        self.assertEqual(
            independent.EXPECTED_SUITE_CANONICAL_BYTES, EXPECTED_SUITE_BYTES
        )
        self.assertEqual(independent.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)

        self.assertEqual(len(self.projections), len(envelope.PERSONA_IDS))
        self.assertEqual(len(self.origins), EXPECTED_ORIGIN_COUNT)
        self.assertEqual(len(self.profiles), EXPECTED_PROFILE_COUNT)
        coverage = self.suite["coverage"]
        self.assertEqual(
            coverage,
            {
                "active_parameter_cell_count_maximum_per_persona": 146,
                "active_parameter_cell_count_minimum_per_persona": 107,
                "active_parameter_cell_count_suite_sum": EXPECTED_PERSONA_CELL_COUNT,
                "compact_origin_assignment_row_count": EXPECTED_ORIGIN_OWNER_ROW_COUNT,
                "concrete_exact_duplicate_pair_count": EXPECTED_EXACT_PAIR_COUNT,
                "eml_attachment_membership_count": EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT,
                "eml_fixed_host_source_count": EXPECTED_EML_HOST_COUNT,
                "eml_fixed_nonhost_source_count": EXPECTED_EML_NONHOST_COUNT,
                "eml_source_count": EXPECTED_EML_SOURCE_COUNT,
                "expanded_body_bytes_nonpersisted": EXPECTED_EXPANDED_BODY_BYTES,
                "expanded_receipt_count": EXPECTED_EXPANDED_RECEIPT_COUNT,
                "global_parameter_cell_count": EXPECTED_GLOBAL_CELL_COUNT,
                "maximum_expanded_body_bytes": EXPECTED_MAX_EXPANDED_BODY_BYTES,
                "maximum_expanded_row_bytes_including_lf": EXPECTED_MAX_EXPANDED_ROW_BYTES,
                "non_eml_singleton_source_count": EXPECTED_NON_EML_SINGLETON_COUNT,
                "origin_manifest_count": EXPECTED_ORIGIN_COUNT,
                "pair_bearing_persona_origin_variant_coordinate_count": EXPECTED_PAIR_BEARING_COORDINATE_COUNT,
                "persona_count": 20,
                "pilot_exact_duplicate_pair_count": EXPECTED_PILOT_EXACT_PAIR_COUNT,
                "pilot_source_intent_count": EXPECTED_PILOT_SOURCE_COUNT,
                "profile_manifest_count": EXPECTED_PROFILE_COUNT,
                "residual_exact_duplicate_pair_count": EXPECTED_RESIDUAL_EXACT_PAIR_COUNT,
                "residual_source_intent_count": EXPECTED_RESIDUAL_SOURCE_COUNT,
                "source_intent_count": EXPECTED_SOURCE_COUNT,
            },
        )

        claims = self.suite["completion_claims"]
        self.assertIs(claims["all_203000_source_instance_parameters_bound"], True)
        self.assertIs(claims["all_expanded_assignment_bodies_persisted"], False)
        self.assertIs(claims["formal_complete_persona_package_cap_proved"], False)
        self.assertIs(claims["frame_and_header_implemented"], False)
        self.assertIs(
            claims["scope_bucket_cohort_chunk_quota_or_final_ids_present"], False
        )

        artifacts_and_caps = [
            (self.catalog, package.MAX_CELL_CATALOG_BYTES),
            *(
                (value, package.MAX_CELL_PROJECTION_BYTES)
                for value in self.projections
            ),
            *((value, package.MAX_ORIGIN_MANIFEST_BYTES) for value in self.origins),
            *((value, package.MAX_PROFILE_MANIFEST_BYTES) for value in self.profiles),
            (self.suite, package.MAX_SUITE_BYTES),
        ]
        for value, cap in artifacts_and_caps:
            with self.subTest(schema=value["artifact_schema"]):
                self.assertLessEqual(len(package.canonical_json_bytes(value)), cap)

        ledgers = self.suite["persona_parameter_component_byte_ledgers"]
        self.assertEqual([row["persona_id"] for row in ledgers], list(envelope.PERSONA_IDS))
        for ledger in ledgers:
            self.assertIs(ledger["formal_complete_persona_package_cap_proved"], False)
            self.assertIs(ledger["frame_and_header_bytes_included"], False)
            self.assertEqual(
                ledger["remaining_bytes_before_nominal_cap_not_a_completion_proof"],
                ledger["max_pre_solve_persona_package_bytes"]
                - ledger["known_pre_solve_component_bytes"],
            )
            self.assertGreater(
                ledger["remaining_bytes_before_nominal_cap_not_a_completion_proof"], 0
            )
            self.assertGreater(
                ledger["expanded_view_body_bytes_excluded_nonpersisted"], 0
            )
        p12 = next(row for row in ledgers if row["persona_id"] == "p12")
        self.assertEqual(
            max(ledgers, key=lambda row: row["known_pre_solve_component_bytes"])[
                "persona_id"
            ],
            "p12",
        )
        for field, expected in EXPECTED_P12_LEDGER.items():
            self.assertEqual(p12[field], expected, field)
        self.assertEqual(
            p12["known_pre_solve_component_bytes"],
            p12["upstream_concrete_current_component_bytes"]
            + p12["shared_direct_parameter_input_body_bytes_charged_once"]
            + p12["shared_parameter_cell_catalog_bytes_charged_once"]
            + p12["parameter_cell_projection_bytes"]
            + p12["origin_manifest_bytes_including_compact_owner_rows"]
            + p12["profile_manifest_bytes"],
        )
        self.assertEqual(
            p12["parameter_extension_bytes"],
            p12["shared_direct_parameter_input_body_bytes_charged_once"]
            + p12["shared_parameter_cell_catalog_bytes_charged_once"]
            + p12["parameter_cell_projection_bytes"]
            + p12["origin_manifest_bytes_including_compact_owner_rows"]
            + p12["profile_manifest_bytes"],
        )
        self.assertEqual(
            p12["max_pre_solve_persona_package_bytes"], 16 * 2**20
        )
        self.assertIs(
            p12["persona_recipe_projection_coalesced_no_separate_body"], True
        )
        self.assertIs(
            p12["compact_owner_rows_coalesced_in_origin_manifest"], True
        )
        self.assertEqual(p12["separate_recipe_or_owner_body_bytes_charged"], 0)

        self.assertEqual(len(package.canonical_json_bytes(self.catalog)), EXPECTED_CELL_CATALOG_BYTES)
        direct_names = p12["shared_direct_parameter_input_names"]
        self.assertEqual(
            direct_names,
            [
                "persona-v2-aggregate-byte-distribution-catalog",
                "persona-v2-overlay-compatible-byte-distribution",
                "persona-v2-formal-source-recipe-profile-catalog",
            ],
        )
        self.assertEqual(len(direct_names), len(set(direct_names)))
        self.assertEqual(
            sum(value[0] for value in EXPECTED_DIRECT_PARAMETER_INPUTS.values()),
            EXPECTED_DIRECT_PARAMETER_INPUT_BYTES,
        )
        bindings = {
            row["name"]: (row["canonical_bytes"], row["sha256"])
            for row in self.catalog["input_bindings"]
        }
        self.assertEqual(bindings, EXPECTED_DIRECT_PARAMETER_INPUTS)
        self.assertEqual(
            len({sha256 for _, sha256 in bindings.values()}), len(bindings)
        )

    def test_cell_catalog_and_persona_count_projections_are_exact(self):
        self._ensure_package()
        cells = self.catalog["parameter_cells"]
        self.assertEqual(len(cells), EXPECTED_GLOBAL_CELL_COUNT)
        self.assertEqual(len({row["parameter_cell_key"] for row in cells}), len(cells))
        by_key = {row["parameter_cell_key"]: row for row in cells}
        for row in cells:
            self.assertEqual(set(row), CELL_FIELDS)
            self.assertEqual(
                row["parameter_cell_key"], f"{row['variant_id']}/{row['bin_id']}"
            )
            self.assertIs(type(row["target_bytes"]), int)
            self.assertGreater(row["target_bytes"], 0)
            self.assertIs(type(row["target_complexity"]), int)
            self.assertGreaterEqual(row["target_complexity"], 0)
            self.assertIs(type(row["renderer_parameters"]), dict)
            self.assertIs(type(row["recipe_profile_id"]), str)
        self.assertEqual(
            [row["parameter_cell_key"] for row in cells if row["variant_id"] == "eml"],
            [f"eml/attachment-{ordinal}" for ordinal in range(6)],
        )

        active_counts = []
        suite_totals = defaultdict(int)
        catalog_order = {key: index for index, key in enumerate(by_key)}
        for projection in self.projections:
            rows = projection["cell_count_rows"]
            active_counts.append(len(rows))
            self.assertEqual(projection["summary"]["active_parameter_cell_count"], len(rows))
            self.assertEqual(
                [catalog_order[row["parameter_cell_key"]] for row in rows],
                sorted(catalog_order[row["parameter_cell_key"]] for row in rows),
            )
            for row in rows:
                self.assertEqual(set(row), PROJECTION_ROW_FIELDS)
                self.assertIn(row["parameter_cell_key"], by_key)
                self.assertEqual(row["variant_id"], by_key[row["parameter_cell_key"]]["variant_id"])
                self.assertEqual(set(row["counts"]), {"pilot", "full-residual", "full"})
                for count in row["counts"].values():
                    self.assertIs(type(count), int)
                    self.assertGreaterEqual(count, 0)
                self.assertEqual(
                    row["counts"]["full"],
                    row["counts"]["pilot"] + row["counts"]["full-residual"],
                )
                for profile, count in row["counts"].items():
                    suite_totals[profile] += count
            self.assertEqual(
                projection["summary"]["source_counts"],
                {
                    profile: sum(row["counts"][profile] for row in rows)
                    for profile in ("pilot", "full-residual", "full")
                },
            )
        self.assertEqual((sum(active_counts), min(active_counts), max(active_counts)), (2_643, 107, 146))
        self.assertEqual(
            dict(suite_totals),
            {
                "pilot": EXPECTED_PILOT_SOURCE_COUNT,
                "full-residual": EXPECTED_RESIDUAL_SOURCE_COUNT,
                "full": EXPECTED_SOURCE_COUNT,
            },
        )

    def test_origin_owners_and_receipts_close_all_exact_totals(self):
        self._ensure_package()
        self.assertEqual(
            [(row["persona_id"], row["origin"]) for row in self.origins],
            [
                (persona_id, origin)
                for persona_id in envelope.PERSONA_IDS
                for origin in package.ORIGIN_ORDER
            ],
        )
        owner_count = receipt_count = row_count = expanded_bytes = 0
        pair_counts = defaultdict(int)
        singleton_count = eml_count = host_count = nonhost_count = membership_count = 0
        pair_coordinates = 0
        maximum_body = maximum_row = 0
        for origin in self.origins:
            compact = origin["compact_assignment_rows"]
            receipts = origin["expanded_view_receipts"]
            owner_count += len(compact)
            receipt_count += len(receipts)
            pair_counts[origin["origin"]] += origin["summary"]["exact_pair_unit_count"]
            pair_coordinates += origin["summary"][
                "pair_bearing_persona_origin_variant_coordinate_count"
            ]
            host_count += origin["summary"]["eml_fixed_host_intent_count"]
            nonhost_count += origin["summary"]["eml_fixed_nonhost_intent_count"]
            membership_count += origin["summary"]["eml_attachment_membership_count"]
            for row in compact:
                self.assertEqual(set(row), COMPACT_OWNER_ROW_FIELDS)
                for field in (
                    "eml_fixed_intent_count",
                    "exact_pair_endpoint_count",
                    "exact_pair_unit_count",
                    "singleton_intent_count",
                    "source_count",
                ):
                    self.assertIs(type(row[field]), int)
                    self.assertGreaterEqual(row[field], 0)
                self.assertGreater(row["source_count"], 0)
                self.assertEqual(
                    row["source_count"],
                    row["eml_fixed_intent_count"]
                    + row["exact_pair_endpoint_count"]
                    + row["singleton_intent_count"],
                )
                self.assertEqual(
                    row["exact_pair_endpoint_count"],
                    2 * row["exact_pair_unit_count"],
                )
                singleton_count += row["singleton_intent_count"]
                if row["variant_id"] == "eml":
                    eml_count += row["source_count"]
                    self.assertEqual(row["source_count"], row["eml_fixed_intent_count"])
            for receipt in receipts:
                self.assertEqual(set(receipt), EXPANDED_RECEIPT_FIELDS)
                self.assertIs(receipt["expanded_body_persisted"], False)
                for field in (
                    "expanded_body_bytes",
                    "maximum_row_bytes_including_lf",
                    "row_count",
                    "shard_ordinal",
                    "source_shard_body_bytes",
                ):
                    self.assertIs(type(receipt[field]), int)
                    self.assertGreater(receipt[field], 0)
                self.assertEqual(receipt["persona_id"], origin["persona_id"])
                self.assertEqual(receipt["origin"], origin["origin"])
                row_count += receipt["row_count"]
                expanded_bytes += receipt["expanded_body_bytes"]
                maximum_body = max(maximum_body, receipt["expanded_body_bytes"])
                maximum_row = max(maximum_row, receipt["maximum_row_bytes_including_lf"])
        self.assertEqual(owner_count, EXPECTED_ORIGIN_OWNER_ROW_COUNT)
        self.assertEqual(receipt_count, EXPECTED_EXPANDED_RECEIPT_COUNT)
        self.assertEqual(row_count, EXPECTED_SOURCE_COUNT)
        self.assertEqual(expanded_bytes, EXPECTED_EXPANDED_BODY_BYTES)
        self.assertEqual(maximum_body, EXPECTED_MAX_EXPANDED_BODY_BYTES)
        self.assertEqual(maximum_row, EXPECTED_MAX_EXPANDED_ROW_BYTES)
        self.assertEqual(
            pair_counts,
            {
                "pilot": EXPECTED_PILOT_EXACT_PAIR_COUNT,
                "full-residual": EXPECTED_RESIDUAL_EXACT_PAIR_COUNT,
            },
        )
        self.assertEqual(pair_coordinates, EXPECTED_PAIR_BEARING_COORDINATE_COUNT)
        self.assertEqual(singleton_count, EXPECTED_NON_EML_SINGLETON_COUNT)
        self.assertEqual(eml_count, EXPECTED_EML_SOURCE_COUNT)
        self.assertEqual(host_count, EXPECTED_EML_HOST_COUNT)
        self.assertEqual(nonhost_count, EXPECTED_EML_NONHOST_COUNT)
        self.assertEqual(membership_count, EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT)

    def test_profiles_are_literal_origin_unions_never_fresh_full_hamilton(self):
        self._ensure_package()
        origins = self._origin_by_key()
        for profile in self.profiles:
            expected_origins = (
                ("pilot",) if profile["profile"] == "pilot" else package.ORIGIN_ORDER
            )
            self.assertEqual(
                [(row["persona_id"], row["origin"]) for row in profile["origin_manifest_bindings"]],
                [(profile["persona_id"], origin) for origin in expected_origins],
            )
            self.assertIs(
                profile["completion_claims"]["fresh_full_hamilton_recomputed"], False
            )
            self.assertIs(
                profile["composition_contract"][
                    "independent_full_hamilton_allocation_allowed"
                ],
                False,
            )
            union = {}
            for origin_name in expected_origins:
                origin = origins[(profile["persona_id"], origin_name)]
                for row in origin["compact_assignment_rows"]:
                    target = union.setdefault(
                        row["parameter_cell_key"],
                        {
                            "eml_fixed_intent_count": 0,
                            "exact_pair_endpoint_count": 0,
                            "exact_pair_unit_count": 0,
                            "singleton_intent_count": 0,
                            "source_count": 0,
                        },
                    )
                    for field in target:
                        target[field] += row[field]
            self.assertEqual(
                {
                    row["parameter_cell_key"]: {
                        field: row[field] for field in union[row["parameter_cell_key"]]
                    }
                    for row in profile["profile_cell_count_rows"]
                },
                union,
            )
            projection = next(
                row
                for row in self.projections
                if row["persona_id"] == profile["persona_id"]
            )
            count_field = "pilot" if profile["profile"] == "pilot" else "full"
            self.assertEqual(
                [row["parameter_cell_key"] for row in profile["profile_cell_count_rows"]],
                [
                    row["parameter_cell_key"]
                    for row in projection["cell_count_rows"]
                    if row["counts"][count_field]
                ],
            )
            for row in profile["profile_cell_count_rows"]:
                self.assertEqual(set(row), PROFILE_ROW_FIELDS)
                self.assertEqual(
                    row["source_count"],
                    row["eml_fixed_intent_count"]
                    + row["exact_pair_endpoint_count"]
                    + row["singleton_intent_count"],
                )
        profiles = self._profile_by_key()
        for persona_id in envelope.PERSONA_IDS:
            pilot_binding = profiles[(persona_id, "pilot")]["origin_manifest_bindings"][0]
            full_pilot_binding = profiles[(persona_id, "full")]["origin_manifest_bindings"][0]
            self.assertEqual(pilot_binding, full_pilot_binding)

    def test_independent_validator_reconstructs_without_importing_the_producer(self):
        self._ensure_package()
        validator_source = inspect.getsource(independent)
        self.assertNotIn(
            "import persona_v2_source_parameter_assignment_package",
            validator_source,
        )
        self.assertNotIn(
            "from . import persona_v2_source_parameter_assignment_package",
            validator_source,
        )
        with mock.patch.object(
            package,
            "_allocate_origin",
            side_effect=AssertionError("independent validator called producer logic"),
        ):
            self.assertTrue(
                independent.validate_source_parameter_assignment_suite_descriptor(
                    self.suite
                )
            )

        # The producer's public entry point must delegate to that independent
        # module; this cheap call avoids running the complete reconstruction a
        # second time in the same test process.
        with mock.patch.object(
            independent,
            "validate_source_parameter_assignment_suite_descriptor",
            return_value=True,
        ) as validate:
            self.assertTrue(
                package.validate_source_parameter_assignment_suite_descriptor(
                    self.suite
                )
            )
        validate.assert_called_once_with(self.suite)

    def test_fully_rethreaded_alternative_owner_is_rejected_beyond_the_suite_pin(self):
        """Rehash a coherent wrapper graph around a noncanonical cell transfer."""

        self._ensure_package()
        origins = self._origin_by_key()
        profiles = self._profile_by_key()
        forged_origin = copy.deepcopy(origins[("p01", "pilot")])
        by_variant = defaultdict(list)
        for row in forged_origin["compact_assignment_rows"]:
            if row["variant_id"] != "eml" and row["singleton_intent_count"] > 0:
                by_variant[row["variant_id"]].append(row)
        donor, recipient = next(
            rows[:2] for rows in by_variant.values() if len(rows) >= 2
        )
        donor_key = donor["parameter_cell_key"]
        recipient_key = recipient["parameter_cell_key"]
        donor["source_count"] -= 1
        donor["singleton_intent_count"] -= 1
        recipient["source_count"] += 1
        recipient["singleton_intent_count"] += 1
        self.assertEqual(
            sum(row["source_count"] for row in forged_origin["compact_assignment_rows"]),
            origins[("p01", "pilot")]["summary"]["source_intent_count"],
        )

        forged_profiles = {}
        for profile_name in package.PROFILE_ORDER:
            profile = copy.deepcopy(profiles[("p01", profile_name)])
            for binding_list in (
                profile["origin_manifest_bindings"],
                profile["input_bindings"],
            ):
                binding = next(
                    row
                    for row in binding_list
                    if row.get("name")
                    == "persona-v2-source-instance-parameter-assignment-origin-manifest"
                    and row.get("origin") == "pilot"
                )
                _refresh_binding(
                    binding,
                    forged_origin,
                    maximum=package.MAX_ORIGIN_MANIFEST_BYTES,
                )
            rows = {
                row["parameter_cell_key"]: row
                for row in profile["profile_cell_count_rows"]
            }
            for field in ("source_count", "singleton_intent_count"):
                rows[donor_key][field] -= 1
                rows[recipient_key][field] += 1
            forged_profiles[profile_name] = profile

        candidate = copy.deepcopy(self.suite)
        origin_binding = next(
            row
            for row in candidate["origin_manifest_bindings"]
            if row["persona_id"] == "p01" and row["origin"] == "pilot"
        )
        old_origin_bytes = origin_binding["canonical_bytes"]
        _refresh_binding(
            origin_binding,
            forged_origin,
            maximum=package.MAX_ORIGIN_MANIFEST_BYTES,
        )
        origin_delta = origin_binding["canonical_bytes"] - old_origin_bytes

        profile_delta = 0
        for profile_name, profile in forged_profiles.items():
            binding = next(
                row
                for row in candidate["profile_manifest_bindings"]
                if row["persona_id"] == "p01" and row["profile"] == profile_name
            )
            old_bytes = binding["canonical_bytes"]
            _refresh_binding(
                binding,
                profile,
                maximum=package.MAX_PROFILE_MANIFEST_BYTES,
            )
            profile_delta += binding["canonical_bytes"] - old_bytes

        ledger = next(
            row
            for row in candidate["persona_parameter_component_byte_ledgers"]
            if row["persona_id"] == "p01"
        )
        ledger["origin_manifest_bytes_including_compact_owner_rows"] += origin_delta
        ledger["profile_manifest_bytes"] += profile_delta
        ledger["parameter_extension_bytes"] += origin_delta + profile_delta
        ledger["known_pre_solve_component_bytes"] += origin_delta + profile_delta
        ledger["remaining_bytes_before_nominal_cap_not_a_completion_proof"] -= (
            origin_delta + profile_delta
        )

        forged_raw = package.canonical_json_bytes(candidate)
        self.assertNotEqual(forged_raw, package.canonical_json_bytes(self.suite))
        with (
            mock.patch.object(
                independent, "EXPECTED_SUITE_CANONICAL_BYTES", len(forged_raw)
            ),
            mock.patch.object(
                independent,
                "EXPECTED_SUITE_SHA256",
                hashlib.sha256(forged_raw).hexdigest(),
            ),
            self.assertRaisesRegex(
                independent.PersonaV2SourceParameterAssignmentValidationError,
                "independent upstream reconstruction",
            ),
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                candidate
            )

    def test_provider_callback_target_and_upstream_metadata_mutation_are_rejected(self):
        self._ensure_package()

        target = copy.deepcopy(self.suite)

        def mutate_target(_inputs, **_providers):
            target["completion_scope"] = "mutated-during-provider-callback"
            return copy.deepcopy(self.suite)

        with mock.patch.object(
            independent, "_expected_suite", side_effect=mutate_target
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SourceParameterAssignmentValidationError,
                "mutated during provider callback",
            ):
                independent.validate_source_parameter_assignment_suite_descriptor(
                    target
                )

        aggregate_value = aggregate.build_aggregate_byte_distribution_catalog()

        def mutate_upstream(_inputs, **_providers):
            aggregate_value["completion_scope"] = "mutated-during-provider-callback"
            return copy.deepcopy(self.suite)

        with mock.patch.object(
            independent, "_expected_suite", side_effect=mutate_upstream
        ):
            with self.assertRaisesRegex(
                independent.PersonaV2SourceParameterAssignmentValidationError,
                "mutated during provider callbacks",
            ):
                independent.validate_source_parameter_assignment_suite_descriptor(
                    self.suite,
                    aggregate_catalog_value=aggregate_value,
                )

    def test_independent_provider_nondeterminism_types_and_wrong_coordinates_fail_closed(self):
        self._ensure_package()
        calls = 0

        def nondeterministic_source_body(persona_id, origin, shard_ordinal):
            nonlocal calls
            calls += 1
            body = source_package.source_intent_shard_body_bytes(
                persona_id, origin, shard_ordinal
            )
            return body if calls % 2 else body[:-1]

        with self.assertRaisesRegex(
            independent.PersonaV2SourceParameterAssignmentValidationError,
            "nondeterministic|alias-mutated",
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_body_provider=nondeterministic_source_body,
            )

        with self.assertRaises(
            independent.PersonaV2SourceParameterAssignmentValidationError
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_origin_provider=lambda _persona, _origin: (
                    source_package.build_source_intent_origin_manifest("p02", "pilot")
                ),
            )

        with self.assertRaises(
            independent.PersonaV2SourceParameterAssignmentValidationError
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_body_provider=lambda _persona, _origin, shard: (
                    source_package.source_intent_shard_body_bytes(
                        "p02", "pilot", shard
                    )
                ),
            )

        oversized_calls = 0

        def oversized_first_source_body(persona_id, origin, shard_ordinal):
            nonlocal oversized_calls
            oversized_calls += 1
            if oversized_calls != 1:
                raise AssertionError("oversized first result must stop replay")
            return source_package.source_intent_shard_body_bytes(
                persona_id, origin, shard_ordinal
            ) + b"x"

        with self.assertRaisesRegex(
            independent.PersonaV2SourceParameterAssignmentValidationError,
            "first result differs from its descriptor",
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_body_provider=oversized_first_source_body,
            )
        self.assertEqual(oversized_calls, 1)

        with self.assertRaisesRegex(
            independent.PersonaV2SourceParameterAssignmentValidationError,
            "exact bytes",
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_body_provider=lambda persona, origin, shard: bytearray(
                    source_package.source_intent_shard_body_bytes(
                        persona, origin, shard
                    )
                ),
            )

        with self.assertRaises(
            independent.PersonaV2SourceParameterAssignmentValidationError
        ):
            independent.validate_source_parameter_assignment_suite_descriptor(
                self.suite,
                source_body_provider="not-callable",
            )

    def test_expanded_views_replay_receipts_exact_pairs_and_fixed_eml_hosts(self):
        self._ensure_bodies()
        cells = {
            row["parameter_cell_key"]: row
            for row in self.catalog["parameter_cells"]
        }
        all_intents = set()
        exact_pair_count = host_count = membership_count = 0
        eml_count = 0
        for origin in self.origins:
            assignments = {}
            for receipt in origin["expanded_view_receipts"]:
                coordinate = (
                    receipt["persona_id"],
                    receipt["origin"],
                    receipt["shard_ordinal"],
                )
                body = self.bodies[coordinate]
                rows = _jsonl_rows(body)
                self.assertEqual(len(body), receipt["expanded_body_bytes"])
                self.assertEqual(
                    hashlib.sha256(body).hexdigest(), receipt["expanded_body_sha256"]
                )
                self.assertEqual(len(rows), receipt["row_count"])
                self.assertEqual(rows[0]["intent_key"], receipt["first_intent_key"])
                self.assertEqual(rows[-1]["intent_key"], receipt["last_intent_key"])
                self.assertEqual(
                    max(len(raw) + 1 for raw in body.splitlines()),
                    receipt["maximum_row_bytes_including_lf"],
                )
                for row in rows:
                    self.assertIn(row["parameter_cell_key"], cells)
                    self.assertNotIn(row["intent_key"], assignments)
                    assignments[row["intent_key"]] = row["parameter_cell_key"]
            self.assertEqual(len(assignments), origin["summary"]["source_intent_count"])
            self.assertFalse(all_intents & set(assignments))
            all_intents.update(assignments)

            hosts = {}
            origin_pair_count = 0
            for row in concrete.iter_concrete_overlay_membership_origin_rows(
                origin["persona_id"], origin["origin"]
            ):
                if (
                    row.get("row_kind") == "content-relation-membership"
                    and row.get("relation_kind") == "exact-duplicate"
                ):
                    origin_pair_count += 1
                    self.assertEqual(
                        assignments[row["anchor_intent_key"]],
                        assignments[row["derivative_intent_key"]],
                    )
                    self.assertFalse(
                        assignments[row["anchor_intent_key"]].startswith("eml/")
                    )
                elif row.get("row_kind") == "attachment-membership":
                    host = row["host_intent_key"]
                    count = row["host_member_count"]
                    previous = hosts.setdefault(host, count)
                    self.assertEqual(previous, count)
            self.assertEqual(
                origin_pair_count, origin["summary"]["exact_pair_unit_count"]
            )
            exact_pair_count += origin_pair_count
            self.assertEqual(len(hosts), origin["summary"]["eml_fixed_host_intent_count"])
            self.assertEqual(
                sum(hosts.values()),
                origin["summary"]["eml_attachment_membership_count"],
            )
            for host, count in hosts.items():
                self.assertEqual(assignments[host], f"eml/attachment-{count}")
            eml_assignments = {
                intent_key: cell
                for intent_key, cell in assignments.items()
                if cell.startswith("eml/")
            }
            for intent_key, cell in eml_assignments.items():
                if intent_key not in hosts:
                    self.assertEqual(cell, "eml/attachment-0")
            eml_count += len(eml_assignments)
            host_count += len(hosts)
            membership_count += sum(hosts.values())
        self.assertEqual(len(all_intents), EXPECTED_SOURCE_COUNT)
        self.assertEqual(exact_pair_count, EXPECTED_EXACT_PAIR_COUNT)
        self.assertEqual(eml_count, EXPECTED_EML_SOURCE_COUNT)
        self.assertEqual(host_count, EXPECTED_EML_HOST_COUNT)
        self.assertEqual(membership_count, EXPECTED_EML_ATTACHMENT_MEMBERSHIP_COUNT)

    def test_all_artifacts_are_non_authorizing_strict_and_forbidden_field_free(self):
        self._ensure_bodies()
        artifacts = [
            (self.catalog, CATALOG_TOP_LEVEL_FIELDS),
            *((value, PROJECTION_TOP_LEVEL_FIELDS) for value in self.projections),
            *((value, ORIGIN_TOP_LEVEL_FIELDS) for value in self.origins),
            *((value, PROFILE_TOP_LEVEL_FIELDS) for value in self.profiles),
            (self.suite, SUITE_TOP_LEVEL_FIELDS),
        ]
        for value, expected_fields in artifacts:
            with self.subTest(schema=value["artifact_schema"], coordinate=_binding_key(value)):
                self.assertEqual(set(value), expected_fields)
                _all_false_authority(self, value)
                _assert_no_forbidden_keys(self, value)
                self.assertFalse(
                    any(
                        "expanded-assignment-bodies-are-nonpersisted" in blocker
                        for blocker in value.get("remaining_blockers", [])
                    ),
                    "an intentional nonpersisted verification view is not a blocker",
                )
                for mapping in _walk_dicts(value):
                    for key, child in mapping.items():
                        if key.endswith("_count") or key.endswith("_bytes") or key in {
                            "artifact_schema_version",
                            "fixture_schema_version",
                            "shard_ordinal",
                            "target_bytes",
                            "target_complexity",
                        }:
                            self.assertIsNot(type(child), bool, f"boolean used as integer at {key}")
        for body in self.bodies.values():
            for row in _jsonl_rows(body):
                _assert_no_forbidden_keys(self, row)
                self.assertEqual(set(row), EXPANDED_ROW_FIELDS)

        self.assertTrue(package.validate_source_parameter_cell_catalog(self.catalog))
        for projection in self.projections:
            self.assertTrue(
                package.validate_source_parameter_cell_projection(
                    projection["persona_id"], projection
                )
            )
        for origin in self.origins:
            self.assertTrue(
                package.validate_source_parameter_assignment_origin_manifest(
                    origin["persona_id"], origin["origin"], origin
                )
            )
        for profile in self.profiles:
            self.assertTrue(
                package.validate_source_parameter_assignment_profile_manifest(
                    profile["persona_id"], profile["profile"], profile
                )
            )

        suite = copy.deepcopy(self.suite)
        suite["coverage"]["source_intent_count"] = True
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.validate_source_parameter_assignment_suite_descriptor(suite)
        suite = copy.deepcopy(self.suite)
        suite["query_id"] = "forbidden-downstream-identity"
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.validate_source_parameter_assignment_suite_descriptor(suite)

    def test_public_builds_are_detached_and_invalid_coordinates_fail_closed(self):
        self._ensure_package()
        cases = [
            (
                package.build_source_parameter_cell_catalog,
                (),
                lambda value: value["parameter_cells"][0].update(target_bytes=1),
            ),
            (
                package.build_source_parameter_cell_projection,
                ("p01",),
                lambda value: value["cell_count_rows"][0]["counts"].update(full=0),
            ),
            (
                package.build_source_parameter_assignment_origin_manifest,
                ("p01", "pilot"),
                lambda value: value["compact_assignment_rows"][0].update(source_count=0),
            ),
            (
                package.build_source_parameter_assignment_profile_manifest,
                ("p01", "full"),
                lambda value: value["profile_cell_count_rows"][0].update(source_count=0),
            ),
            (
                package.build_source_parameter_assignment_suite_descriptor,
                (),
                lambda value: value["coverage"].update(source_intent_count=0),
            ),
        ]
        for builder, args, mutate in cases:
            with self.subTest(builder=builder.__name__):
                first = builder(*args)
                baseline = package.canonical_json_bytes(first)
                mutate(first)
                second = builder(*args)
                self.assertEqual(package.canonical_json_bytes(second), baseline)

        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.build_source_parameter_cell_projection(True)
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.build_source_parameter_assignment_origin_manifest("p01", "full")
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.build_source_parameter_assignment_profile_manifest("p01", "pilot ")
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            list(package.iter_source_parameter_assignment_rows("p01", "pilot", True))
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.canonical_json_bytes([])
        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            package.require_complete_source_parameter_assignment_package()

    def test_parameter_catalog_and_projection_dag_do_not_touch_source_or_concrete(self):
        """The two count-only layers must not acquire instance dependencies."""
        script = r'''
from unittest import mock
from eval import persona_v2_source_parameter_assignment_package as package

for name in (
    "_cached_shared_inputs",
    "_cached_parameter_inputs",
    "_cached_distribution_inputs",
    "_cached_assignment_inputs",
    "_canonical_cell_catalog",
    "_canonical_cell_projection",
):
    clear = getattr(getattr(package, name, None), "cache_clear", None)
    if callable(clear):
        clear()

with (
    mock.patch.object(
        package.source_package,
        "build_source_intent_suite_descriptor",
        side_effect=AssertionError("cell layers touched source instances"),
    ),
    mock.patch.object(
        package.concrete,
        "build_concrete_overlay_membership_suite_descriptor",
        side_effect=AssertionError("cell layers touched concrete overlay"),
    ),
):
    catalog = package.build_source_parameter_cell_catalog()
    projection = package.build_source_parameter_cell_projection("p01")
assert catalog["summary"]["parameter_cell_count"] == 363
assert projection["persona_id"] == "p01"
print("ok")
'''
        output = subprocess.check_output(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            text=True,
            timeout=180,
        ).strip()
        self.assertEqual(output, "ok")

    def test_producer_origin_provider_mutation_nondeterminism_and_wrong_coordinates_fail_closed(self):
        self._ensure_package()

        def inputs():
            return copy.deepcopy(package._cached_assignment_inputs())

        defaults = {
            "source_origin_provider": source_package.build_source_intent_origin_manifest,
            "source_body_provider": source_package.source_intent_shard_body_bytes,
            "concrete_origin_provider": concrete.build_concrete_overlay_membership_origin_manifest,
            "concrete_body_provider": concrete.concrete_overlay_membership_shard_body_bytes,
        }

        def build(candidate_inputs, **overrides):
            providers = dict(defaults)
            providers.update(overrides)
            return package._build_origin_manifest(
                candidate_inputs,
                "p01",
                "pilot",
                **providers,
            )

        candidate_inputs = inputs()
        calls = 0

        def nondeterministic_source_body(persona_id, origin, shard_ordinal):
            nonlocal calls
            calls += 1
            body = source_package.source_intent_shard_body_bytes(
                persona_id, origin, shard_ordinal
            )
            return body if calls % 2 else body[:-1]

        with self.assertRaisesRegex(
            package.PersonaV2SourceParameterAssignmentPackageError,
            "nondeterministic|alias-mutated",
        ):
            build(candidate_inputs, source_body_provider=nondeterministic_source_body)

        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            build(
                inputs(),
                source_origin_provider=lambda _persona, _origin: (
                    source_package.build_source_intent_origin_manifest("p02", "pilot")
                ),
            )

        with self.assertRaises(package.PersonaV2SourceParameterAssignmentPackageError):
            build(
                inputs(),
                source_body_provider=lambda _persona, _origin, shard: (
                    source_package.source_intent_shard_body_bytes(
                        "p02", "pilot", shard
                    )
                ),
            )

        candidate_inputs = inputs()
        mutated = False

        def mutating_source_body(persona_id, origin, shard_ordinal):
            nonlocal mutated
            if not mutated:
                candidate_inputs["aggregate"]["completion_scope"] = (
                    "mutated-during-provider-callback"
                )
                mutated = True
            return source_package.source_intent_shard_body_bytes(
                persona_id, origin, shard_ordinal
            )

        with self.assertRaisesRegex(
            package.PersonaV2SourceParameterAssignmentPackageError,
            "changed during a provider callback",
        ):
            build(candidate_inputs, source_body_provider=mutating_source_body)

        oversized_calls = 0

        def oversized_first_source_body(persona_id, origin, shard_ordinal):
            nonlocal oversized_calls
            oversized_calls += 1
            if oversized_calls != 1:
                raise AssertionError("oversized first result must stop replay")
            return source_package.source_intent_shard_body_bytes(
                persona_id, origin, shard_ordinal
            ) + b"x"

        with self.assertRaisesRegex(
            package.PersonaV2SourceParameterAssignmentPackageError,
            "first result differs from its descriptor",
        ):
            build(
                inputs(), source_body_provider=oversized_first_source_body
            )
        self.assertEqual(oversized_calls, 1)

    def test_z_hashseed_reproducibility_and_cold_build_runtime_rss_are_bounded(self):
        script = r'''
import hashlib
import json
import os
import resource
import sys
import time
from eval import persona_v2_source_parameter_assignment_package as package
from eval import persona_v2_source_parameter_assignment_package_validator as independent

started = time.monotonic()
suite = package.build_source_parameter_assignment_suite_descriptor()
raw = package.canonical_json_bytes(suite)
body = package.source_parameter_assignment_expanded_view_body_bytes(
    "p01", "pilot", 1
)
validated = (
    independent.validate_source_parameter_assignment_suite_descriptor(suite)
    if os.environ["KIO_ASSIGNMENT_VALIDATE"] == "1"
    else None
)
maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rss_bytes = int(maximum_rss) if sys.platform == "darwin" else int(maximum_rss) * 1024
print(json.dumps({
    "body_sha256": hashlib.sha256(body).hexdigest(),
    "elapsed_seconds": time.monotonic() - started,
    "rss_bytes": rss_bytes,
    "suite_bytes": len(raw),
    "suite_sha256": hashlib.sha256(raw).hexdigest(),
    "validated": validated,
}, sort_keys=True))
'''
        def run_seed(seed, validate):
            environment = dict(os.environ)
            environment.update(
                {
                    "KIO_ASSIGNMENT_VALIDATE": "1" if validate else "0",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                text=True,
                timeout=MAX_COLD_BUILD_SECONDS + 120,
            )
            return json.loads(output)

        seeds = (("73", True), ("777", False))
        with ThreadPoolExecutor(max_workers=len(seeds)) as executor:
            measurements = list(
                executor.map(lambda args: run_seed(*args), seeds)
            )
        for measured, (_, validate) in zip(measurements, seeds, strict=True):
            self.assertIs(measured["validated"], True if validate else None)
            self.assertEqual(measured["suite_bytes"], EXPECTED_SUITE_BYTES)
            self.assertEqual(measured["suite_sha256"], EXPECTED_SUITE_SHA256)
            self.assertEqual(
                measured["body_sha256"],
                "a70de71e5d004443e6ba60c7128e0f406cf21759ca6de5357a97a6a3f00c9b86",
            )
            self.assertGreater(measured["elapsed_seconds"], 0)
            self.assertLessEqual(
                measured["elapsed_seconds"], MAX_COLD_BUILD_SECONDS
            )
            self.assertGreater(measured["rss_bytes"], 0)
            self.assertLessEqual(measured["rss_bytes"], MAX_COLD_BUILD_RSS_BYTES)
        self.assertEqual(
            {row["suite_sha256"] for row in measurements},
            {EXPECTED_SUITE_SHA256},
        )
        self.assertEqual(
            {row["body_sha256"] for row in measurements},
            {"a70de71e5d004443e6ba60c7128e0f406cf21759ca6de5357a97a6a3f00c9b86"},
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
