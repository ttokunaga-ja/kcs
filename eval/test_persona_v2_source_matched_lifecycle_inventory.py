"""Focused gates for the source-matched lifecycle inventory.

The artifact under test is the last query-independent, pre-solve bridge from
the frozen 20-persona source corpus to lifecycle intent.  These tests keep the
expensive source graph shared in-process and use only one cold subprocess for
hash-seed/resource reproducibility.
"""

from __future__ import annotations

import ast
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
from eval import persona_v2_contract as envelope
from eval import persona_v2_source_parameter_assignment_package as assignments
from eval import persona_v2_source_matched_lifecycle_inventory as package
from eval import (
    persona_v2_source_matched_lifecycle_inventory_validator as independent,
)


EXPECTED_PERSONA_COUNT = 20
EXPECTED_SOURCE_REF_COUNT_PER_PERSONA = 115
EXPECTED_SOURCE_REF_COUNT = 2_300
EXPECTED_PRIMARY_COUNT_PER_PERSONA = 105
EXPECTED_CONTRIBUTOR_PRIMARY_COUNT_PER_PERSONA = 100
EXPECTED_INCIDENTAL_PRIMARY_COUNT_PER_PERSONA = 5
EXPECTED_COMPANION_COUNT_PER_PERSONA = 10
EXPECTED_USED_ANCHOR_COUNT_PER_PERSONA = 100
EXPECTED_RESERVED_ANCHOR_COUNT_PER_PERSONA = 5

EXPECTED_SOURCE_EVENT_COUNT_PER_PERSONA = 244
EXPECTED_SOURCE_EVENT_COUNT = 4_880
EXPECTED_DERIVE_DIAGNOSTIC_COUNT = 20
EXPECTED_DUPLICATE_DIAGNOSTIC_COUNT = 30
EXPECTED_DIAGNOSTIC_COUNT = 50
EXPECTED_FORCED_PURGED_COMMIT_COUNT_PER_PERSONA = 15
EXPECTED_ORDINARY_SCOPE_INDEX_COUNT_PER_PERSONA = 100
EXPECTED_POST_PURGE_INDEX_COUNT_PER_PERSONA = 20
EXPECTED_EVENT_COUNT = 7_630
EXPECTED_MULTI_EVENT_DEPENDENCY_GROUP_COUNT_PER_PERSONA = 54
EXPECTED_CREATED_SOURCE_INTENT_BASE_COUNT_PER_PERSONA = 179
EXPECTED_MULTI_EVENT_DEPENDENCY_GROUP_COUNT = 1_080
EXPECTED_CREATED_SOURCE_INTENT_COUNT = 3_630

EXPECTED_FAMILY_WITNESS_COUNT = 93
EXPECTED_FAMILY_CLASS_COUNTS = {
    "pending-conversion-negative": 33,
    "raw-only-structural-negative": 8,
    "searchable-positive": 52,
}

EXPECTED_SOURCE_EVENT_TYPES_PER_PERSONA = {
    "w1-incidental-typed-edit": 1,
    "w1-typed-edit": 69,
    "w2-move": 5,
    "w2-rename": 5,
    "w3-surface-edit": 54,
    "w4-archive": 10,
    "w4-create-x-prime": 20,
    "w4-delete": 20,
    "w5-create-p-prime": 15,
    "w5-delete-x-prime": 10,
    "w5-export-x": 10,
    "w5-purge-p": 15,
    "w5-restore-x": 10,
}

DERIVE_DIAGNOSTIC_PERSONAS = frozenset({"p01", "p04", "p06", "p09"})
DUPLICATE_DIAGNOSTIC_PERSONAS = frozenset(
    {"p04", "p05", "p08", "p10", "p14", "p19"}
)

# Frozen only after the independent validator accepts the complete final
# reconstruction.  These literals intentionally live outside either module so
# a coordinated accidental re-pin remains review-visible.
EXPECTED_SUITE_BYTES = 14_605
EXPECTED_SUITE_SHA256 = (
    "b2ec04ef66476cc71b4ae1fb3275b8d5787eb560b5a7a7e2a3f03d690b77688b"
)
EXPECTED_ACTUAL_MAX_EVENT_BODY_BYTES = 318_846
EXPECTED_ACTUAL_MAX_EVENT_ROW_BYTES_INCLUDING_LF = 973
EXPECTED_ACTUAL_MAX_PERSONA_BYTES = 103_962
EXPECTED_ACTUAL_MAX_PROJECTION_BYTES = 256_800

MAX_COLD_BUILD_SECONDS = 15 * 60
MAX_COLD_BUILD_RSS_BYTES = 512 * 2**20
EXPECTED_MAX_EVENT_BODY_BYTES = 4 * 2**20
EXPECTED_MAX_EVENT_ROW_BYTES_INCLUDING_LF = 1_024

PERSONA_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "authority",
        "canonical_limits",
        "completion_claims",
        "completion_scope",
        "dependency_direction_contract",
        "event_receipt",
        "fixture_id",
        "fixture_schema_version",
        "g0_contract_frozen",
        "input_binding_order",
        "input_bindings",
        "orders",
        "persona_id",
        "primary_match_rows",
        "companion_match_rows",
        "reserved_semantic_anchor_rows",
        "remaining_blockers",
        "selection_policy",
        "summary",
        "use_case_family_witness_rows",
    }
)
PRIMARY_MATCH_FIELDS = frozenset(
    {
        "allocation_class",
        "base_fact_profile_id",
        "base_language",
        "base_logical_document_key",
        "base_logical_revision_key",
        "base_topic_id",
        "capability_class_key",
        "capability_key",
        "family",
        "gate_role",
        "intent_key",
        "lifecycle_logical_document_slot_key",
        "origin",
        "parameter_cell_key",
        "reservation_status",
        "source_profile_id",
        "variant_id",
    }
)
CONTRIBUTOR_PRIMARY_MATCH_FIELDS = PRIMARY_MATCH_FIELDS | {
    "semantic_anchor_slot_ordinal"
}
INCIDENTAL_PRIMARY_MATCH_FIELDS = PRIMARY_MATCH_FIELDS
RESERVED_SEMANTIC_ANCHOR_FIELDS = frozenset(
    {"family", "intent_key", "semantic_anchor_slot_ordinal", "variant_id"}
)
COMPANION_MATCH_FIELDS = frozenset(
    {
        "base_fact_profile_id",
        "base_language",
        "base_logical_document_key",
        "base_logical_revision_key",
        "base_topic_id",
        "companion_requirement_key",
        "effective_membership_rule",
        "family",
        "gate_role",
        "intent_key",
        "origin",
        "parameter_cell_key",
        "primary_capability_key",
        "rendition_group_key",
        "reservation_status",
        "source_profile_id",
        "variant_id",
    }
)
POSITIVE_USE_CASE_WITNESS_FIELDS = frozenset(
    {
        "classification",
        "family",
        "intent_key",
        "offline_disposition",
        "parameter_cell_key",
        "physical_witness_required",
        "primary_use_case_id",
        "query_answer_anchor_required",
        "query_anchor_ref",
        "source_profile_id",
        "source_selection_kind",
        "variant_id",
    }
)
NEGATIVE_USE_CASE_WITNESS_FIELDS = (
    POSITIVE_USE_CASE_WITNESS_FIELDS - {"query_anchor_ref"}
) | {"negative_expectation"}
EVENT_RECEIPT_FIELDS = frozenset(
    {
        "body_bytes",
        "body_persisted",
        "body_sha256",
        "first_event_intent_key",
        "first_event_sequence_ordinal",
        "last_event_intent_key",
        "last_event_sequence_ordinal",
        "maximum_row_bytes_including_lf",
        "persona_id",
        "row_count",
    }
)
SOURCE_EVENT_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "byte_transition_rule",
        "capability_key",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "family",
        "gate_role",
        "path_transition_rule_key",
        "persona_id",
        "predecessor_event_intent_refs",
        "row_kind",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "source_intent_key",
        "symbol_domain_ref",
        "variant_id",
        "wave",
    }
)
SCOPE_EVENT_ROW_FIELDS = frozenset(
    {
        "abstract_scope_slot_ordinal",
        "byte_transition_rule",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "event_sequence_ordinal",
        "fact_transition_rule",
        "path_transition_rule_key",
        "persona_id",
        "predecessor_event_intent_refs",
        "row_kind",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "symbol_domain_ref",
        "wave",
    }
)
CONTENT_ROW_FIELDS = frozenset(
    {
        "family",
        "gate_role",
        "intent_key",
        "parameter_cell_key",
        "selection_role_refs",
        "source_profile_id",
        "variant_id",
    }
)
CONTENT_SECTIONS_FIELDS = frozenset(
    {"scope_event_rows", "source_event_rows", "source_selection_rows"}
)
CONTENT_SOURCE_EVENT_ROW_FIELDS = frozenset(
    {
        "after_source_intent_key",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "fact_transition_rule",
        "path_transition_rule_key",
        "predecessor_event_intent_refs",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
        "source_intent_key",
    }
)
CONTENT_SCOPE_EVENT_ROW_FIELDS = frozenset(
    {
        "abstract_scope_slot_ordinal",
        "dependency_group_key",
        "delta_rule_ref",
        "event_intent_key",
        "event_profile_key",
        "fact_transition_rule",
        "path_transition_rule_key",
        "predecessor_event_intent_refs",
        "scenario_visibility_rule",
        "scope_relation_rule_key",
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
        "input_binding_order",
        "input_bindings",
        "orders",
        "persona_bindings",
        "policy",
        "remaining_blockers",
        "summary",
    }
)
PROJECTION_TOP_LEVEL_FIELDS = frozenset(
    {
        "artifact_kind",
        "artifact_schema",
        "artifact_schema_version",
        "content_rules",
        "fixture_id",
        "fixture_schema_version",
        "persona_id",
        "content_sections",
        "summary",
    }
)

CREATED_SOURCE_EVENT_PROFILES = frozenset(
    {
        "w1-incidental-typed-edit",
        "w1-typed-edit",
        "w3-derive-diagnostic",
        "w3-duplicate-diagnostic-cross-scope",
        "w3-duplicate-diagnostic-same-scope",
        "w3-surface-edit",
        "w4-create-x-prime",
        "w5-create-p-prime",
        "w5-export-x",
        "w5-restore-x",
    }
)

FORBIDDEN_KEYS = frozenset(
    {
        "absolute_path",
        "actual_qim",
        "assigned_bucket_key",
        "assigned_history_cohort_id",
        "assigned_scope_key",
        "chunk_id",
        "chunk_quota",
        "final_event_id",
        "final_materialization_id",
        "final_source_id",
        "materialization_id",
        "oracle_id",
        "oracle_key",
        "path",
        "query_id",
        "query_key",
        "query_text",
        "quota",
        "relative_path",
        "rendered_event_payload",
        "runtime_event_id",
        "scope_id",
        "solved_path",
        "solved_scope_key",
        "source_id",
    }
)
PRODUCER_MODULE_BASENAME = "persona_v2_source_matched_lifecycle_inventory"


def _canonical(value, *, label="source-matched lifecycle test value", maximum=None):
    return artifact_common.canonical_json_bytes(
        value,
        label=label,
        max_bytes=(package.MAX_SUITE_BYTES if maximum is None else maximum),
    )


def _walk(value):
    yield value
    if type(value) is dict:
        for child in value.values():
            yield from _walk(child)
    elif type(value) is list:
        for child in value:
            yield from _walk(child)


def _walk_dicts(value):
    return (item for item in _walk(value) if type(item) is dict)


def _resolved_import_targets(source):
    """Return module targets resolved from all ordinary Python import forms."""

    targets = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            targets.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            if node.module:
                targets.append(prefix)
            for alias in node.names:
                if alias.name == "*":
                    continue
                separator = "" if not prefix or prefix.endswith(".") else "."
                targets.append(f"{prefix}{separator}{alias.name}")
    return tuple(targets)


def _imports_producer_module(source):
    return any(
        PRODUCER_MODULE_BASENAME in target.lstrip(".").split(".")
        for target in _resolved_import_targets(source)
    )


def _assert_no_forbidden_keys(test, value):
    for mapping in _walk_dicts(value):
        test.assertFalse(
            set(mapping) & FORBIDDEN_KEYS,
            f"forbidden solved/evaluation key in {sorted(set(mapping) & FORBIDDEN_KEYS)}",
        )


def _assert_strict_json_domain(test, value, *, path="$", integer_key=None):
    """Reject null/float/negative integers and bool-as-int aliases recursively."""

    test.assertIsNotNone(value, f"null at {path}")
    test.assertIsNot(type(value), float, f"float at {path}")
    if type(value) is bool:
        if integer_key is not None:
            test.fail(f"bool used as integer at {path}")
    elif type(value) is int:
        test.assertGreaterEqual(value, 0, f"negative integer at {path}")
    elif type(value) is dict:
        for key, child in value.items():
            looks_numeric = key.endswith(("_bytes", "_count", "_ordinal", "_version"))
            _assert_strict_json_domain(
                test,
                child,
                path=f"{path}.{key}",
                integer_key=key if looks_numeric else None,
            )
    elif type(value) is list:
        for index, child in enumerate(value):
            _assert_strict_json_domain(
                test,
                child,
                path=f"{path}[{index}]",
                integer_key=integer_key,
            )


def _event_rows(persona_id):
    return list(package.iter_source_matched_lifecycle_event_rows(persona_id))


def _jsonl_rows(body):
    if type(body) is not bytes or not body or not body.endswith(b"\n"):
        raise AssertionError("event body must be non-empty exact bytes ending in LF")
    if b"\r" in body or body.endswith(b"\n\n"):
        raise AssertionError("event body has noncanonical framing")
    rows = []
    for raw in body.splitlines():
        if len(raw) + 1 > EXPECTED_MAX_EVENT_ROW_BYTES_INCLUDING_LF:
            raise AssertionError("event row exceeds the LF-inclusive cap")
        row = json.loads(raw.decode("utf-8", "strict"))
        canonical = artifact_common.canonical_json_bytes(
            row,
            label="source-matched lifecycle event row test replay",
            max_bytes=EXPECTED_MAX_EVENT_ROW_BYTES_INCLUDING_LF - 1,
        )
        if canonical != raw:
            raise AssertionError("event row is not canonical JSON")
        rows.append(row)
    return rows


class PersonaV2SourceMatchedLifecycleInventoryTests(unittest.TestCase):
    """One shared package graph, plus focused semantic/adversarial gates."""

    personas = None
    projections = None
    suite = None
    events = None
    assignment_payloads = {}

    @classmethod
    def _ensure_package(cls):
        if cls.suite is not None:
            return
        cls.personas = [
            package.build_source_matched_lifecycle_persona(persona_id)
            for persona_id in envelope.PERSONA_IDS
        ]
        cls.projections = [
            package.build_source_matched_lifecycle_content_projection(persona_id)
            for persona_id in envelope.PERSONA_IDS
        ]
        cls.suite = package.build_source_matched_lifecycle_suite_descriptor()

    @classmethod
    def _ensure_events(cls):
        cls._ensure_package()
        if cls.events is None:
            cls.events = {
                persona_id: _event_rows(persona_id)
                for persona_id in envelope.PERSONA_IDS
            }

    @classmethod
    def _persona_by_id(cls):
        cls._ensure_package()
        return {value["persona_id"]: value for value in cls.personas}

    @classmethod
    def _assignment_provider(cls, persona_id):
        if persona_id not in cls.assignment_payloads:
            cls.assignment_payloads[persona_id] = (
                package._default_assignment_origin_provider(persona_id)
            )
        return copy.deepcopy(cls.assignment_payloads[persona_id])

    def test_opening_snapshot_is_deserialized_from_authenticated_bytes(self):
        opening_raw = b'{"marker":"opening"}'
        live_value = {"marker": "changed-after-opening"}
        with mock.patch.object(independent, "_canonical", return_value=opening_raw):
            snapshot, authenticated = independent._opening_snapshot(
                live_value, label="focused opening snapshot", maximum=4_096
            )
        self.assertEqual(authenticated, opening_raw)
        self.assertEqual(snapshot, {"marker": "opening"})
        self.assertNotEqual(snapshot, live_value)

    def test_exact_source_matching_anchor_companion_and_small_cell_counts(self):
        self._ensure_package()
        cells = {
            row["parameter_cell_key"]: row
            for row in assignments.build_source_parameter_cell_catalog()[
                "parameter_cells"
            ]
        }
        total_primary = 0
        total_companions = 0
        all_refs = 0
        for persona in self.personas:
            persona_id = persona["persona_id"]
            primary = persona["primary_match_rows"]
            companions = persona["companion_match_rows"]
            total_primary += len(primary)
            total_companions += len(companions)
            all_refs += len(primary) + len(companions)

            self.assertEqual(set(persona), PERSONA_TOP_LEVEL_FIELDS)
            self.assertEqual(len(primary), EXPECTED_PRIMARY_COUNT_PER_PERSONA)
            self.assertEqual(len(companions), EXPECTED_COMPANION_COUNT_PER_PERSONA)
            contributor = [
                row for row in primary if row["gate_role"] == "contract_contributor"
            ]
            incidental = [
                row for row in primary if row["gate_role"] == "incidental_searchable"
            ]
            self.assertTrue(
                all(set(row) == CONTRIBUTOR_PRIMARY_MATCH_FIELDS for row in contributor)
            )
            self.assertTrue(
                all(set(row) == INCIDENTAL_PRIMARY_MATCH_FIELDS for row in incidental)
            )
            self.assertTrue(
                all(set(row) == COMPANION_MATCH_FIELDS for row in companions)
            )
            self.assertEqual(
                Counter(row["gate_role"] for row in primary),
                Counter(
                    {
                        "contract_contributor": EXPECTED_CONTRIBUTOR_PRIMARY_COUNT_PER_PERSONA,
                        "incidental_searchable": EXPECTED_INCIDENTAL_PRIMARY_COUNT_PER_PERSONA,
                    }
                ),
            )
            self.assertEqual(len(contributor), EXPECTED_USED_ANCHOR_COUNT_PER_PERSONA)
            reserved = persona["reserved_semantic_anchor_rows"]
            self.assertEqual(len(reserved), EXPECTED_RESERVED_ANCHOR_COUNT_PER_PERSONA)
            self.assertTrue(
                all(set(row) == RESERVED_SEMANTIC_ANCHOR_FIELDS for row in reserved)
            )
            used_intents = {row["intent_key"] for row in contributor}
            reserved_intents = {row["intent_key"] for row in reserved}
            self.assertEqual(len(used_intents), 100)
            self.assertEqual(len(reserved_intents), 5)
            self.assertTrue(used_intents.isdisjoint(reserved_intents))
            used_slots = {row["semantic_anchor_slot_ordinal"] for row in contributor}
            reserved_slots = {
                row["semantic_anchor_slot_ordinal"] for row in reserved
            }
            self.assertEqual(len(used_slots), 100)
            self.assertEqual(len(reserved_slots), 5)
            self.assertTrue(used_slots.isdisjoint(reserved_slots))
            self.assertEqual(used_slots | reserved_slots, set(range(1, 106)))

            refs = primary + companions
            self.assertEqual(len({row["intent_key"] for row in refs}), 115)
            self.assertTrue(all(row["origin"] == "pilot" for row in refs))
            self.assertTrue(all(row["parameter_cell_key"] in cells for row in refs))
            self.assertTrue(
                all(row["capability_key"].startswith(persona_id) for row in primary)
            )
            self.assertEqual(len(incidental), 5)
            self.assertTrue(
                all(cells[row["parameter_cell_key"]]["target_bytes"] <= 32_768 for row in incidental)
            )
            self.assertNotIn("actual_qim", persona)

        self.assertEqual(total_primary, 2_100)
        self.assertEqual(total_companions, 200)
        self.assertEqual(all_refs, EXPECTED_SOURCE_REF_COUNT)

    def test_cross_format_companions_are_distinct_and_semantically_aligned(self):
        self._ensure_package()
        for persona in self.personas:
            primary = {
                row["capability_key"]: row for row in persona["primary_match_rows"]
            }
            self.assertEqual(len(persona["companion_match_rows"]), 10)
            for companion in persona["companion_match_rows"]:
                anchor = primary[companion["primary_capability_key"]]
                self.assertNotEqual(companion["intent_key"], anchor["intent_key"])
                self.assertNotEqual(companion["variant_id"], anchor["variant_id"])
                self.assertNotEqual(companion["family"], anchor["family"])
                self.assertEqual(companion["gate_role"], "contract_contributor")
                self.assertEqual(companion["base_language"], anchor["base_language"])
                self.assertEqual(companion["base_topic_id"], anchor["base_topic_id"])
                self.assertEqual(
                    companion["effective_membership_rule"],
                    "replace-with-primary-lifecycle-logical-document-fact-revision-chain",
                )
                self.assertTrue(companion["rendition_group_key"].startswith(persona["persona_id"]))

    def test_canonical_suite_pin_exact_summary_and_body_bounds(self):
        self._ensure_package()
        raw = package.canonical_json_bytes(self.suite)
        self.assertEqual(len(raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_SUITE_SHA256)
        self.assertLessEqual(len(raw), package.MAX_SUITE_BYTES)
        for module in (package, independent):
            self.assertEqual(
                module.EXPECTED_SUITE_CANONICAL_BYTES,
                EXPECTED_SUITE_BYTES,
            )
            self.assertEqual(module.EXPECTED_SUITE_SHA256, EXPECTED_SUITE_SHA256)

        self.assertEqual(
            self.suite["summary"],
            {
                "companion_source_match_count": 200,
                "event_intent_count": EXPECTED_EVENT_COUNT,
                "format_witness_count": EXPECTED_FAMILY_WITNESS_COUNT,
                "format_witness_counts": EXPECTED_FAMILY_CLASS_COUNTS,
                "lifecycle_source_ref_count": EXPECTED_SOURCE_REF_COUNT,
                "maximum_event_body_bytes_nonpersisted": (
                    EXPECTED_ACTUAL_MAX_EVENT_BODY_BYTES
                ),
                "maximum_event_row_bytes_including_lf": (
                    EXPECTED_ACTUAL_MAX_EVENT_ROW_BYTES_INCLUDING_LF
                ),
                "maximum_persona_match_owner_bytes": (
                    EXPECTED_ACTUAL_MAX_PERSONA_BYTES
                ),
                "persona_count": EXPECTED_PERSONA_COUNT,
                "primary_source_match_count": 2_100,
                "reserved_unused_semantic_anchor_count": 100,
            },
        )
        self.assertEqual(
            max(value["event_receipt"]["body_bytes"] for value in self.personas),
            EXPECTED_ACTUAL_MAX_EVENT_BODY_BYTES,
        )
        self.assertEqual(
            max(
                value["event_receipt"]["maximum_row_bytes_including_lf"]
                for value in self.personas
            ),
            EXPECTED_ACTUAL_MAX_EVENT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(
            max(len(package.canonical_json_bytes(value)) for value in self.personas),
            EXPECTED_ACTUAL_MAX_PERSONA_BYTES,
        )
        projection_bytes = [
            len(package.canonical_json_bytes(value)) for value in self.projections
        ]
        self.assertEqual(max(projection_bytes), EXPECTED_ACTUAL_MAX_PROJECTION_BYTES)
        self.assertTrue(
            all(
                size <= package.TARGET_CONTENT_PROJECTION_BYTES
                <= package.MAX_CONTENT_PROJECTION_BYTES
                for size in projection_bytes
            )
        )

    def test_use_case_family_classification_and_witness_anchors_are_exact(self):
        self._ensure_package()
        witnesses = [
            row
            for persona in self.personas
            for row in persona["use_case_family_witness_rows"]
        ]
        self.assertEqual(len(witnesses), EXPECTED_FAMILY_WITNESS_COUNT)
        self.assertEqual(
            Counter(row["classification"] for row in witnesses),
            Counter(EXPECTED_FAMILY_CLASS_COUNTS),
        )
        positive_use_cases = set()
        for persona in self.personas:
            matched = {
                row["intent_key"]: row
                for row in persona["primary_match_rows"]
                + persona["companion_match_rows"]
            }
            for row in persona["use_case_family_witness_rows"]:
                classification = row["classification"]
                self.assertIs(row["physical_witness_required"], True)
                if classification == "searchable-positive":
                    self.assertEqual(set(row), POSITIVE_USE_CASE_WITNESS_FIELDS)
                    self.assertIn(row["family"], package.SEARCHABLE_POSITIVE_FAMILIES)
                    self.assertIs(row["query_answer_anchor_required"], True)
                    self.assertEqual(row["query_anchor_ref"], row["intent_key"])
                    self.assertIn(row["query_anchor_ref"], matched)
                    self.assertEqual(
                        matched[row["query_anchor_ref"]]["family"], row["family"]
                    )
                    self.assertIn(
                        row["offline_disposition"],
                        {"incidental_sniff", "local_pdf_text", "local_text"},
                    )
                    positive_use_cases.add(row["primary_use_case_id"])
                else:
                    self.assertEqual(set(row), NEGATIVE_USE_CASE_WITNESS_FIELDS)
                    self.assertIs(row["query_answer_anchor_required"], False)
                    self.assertNotIn("query_anchor_ref", row)
                    if classification == "pending-conversion-negative":
                        self.assertIn(row["family"], package.PENDING_CONVERSION_FAMILIES)
                        self.assertIn(
                            row["offline_disposition"],
                            {"await_conversion", "awaiting_ocr"},
                        )
                    else:
                        self.assertEqual(classification, "raw-only-structural-negative")
                        self.assertIn(row["family"], package.RAW_ONLY_FAMILIES)
                        self.assertEqual(row["offline_disposition"], "unsupported_binary")
        self.assertEqual(len(positive_use_cases), EXPECTED_PERSONA_COUNT)

    def test_content_only_projection_and_pilot_full_reuse_boundary(self):
        self._ensure_events()
        self.assertEqual(set(self.suite), SUITE_TOP_LEVEL_FIELDS)
        self.assertEqual([value["persona_id"] for value in self.projections], list(envelope.PERSONA_IDS))
        personas = self._persona_by_id()
        for projection in self.projections:
            persona_id = projection["persona_id"]
            self.assertEqual(set(projection), PROJECTION_TOP_LEVEL_FIELDS)
            sections = projection["content_sections"]
            self.assertEqual(set(sections), CONTENT_SECTIONS_FIELDS)
            selection_rows = sections["source_selection_rows"]
            source_event_rows = sections["source_event_rows"]
            scope_event_rows = sections["scope_event_rows"]
            self.assertTrue(
                all(set(row) == CONTENT_ROW_FIELDS for row in selection_rows)
            )
            self.assertTrue(
                all(
                    set(row) == CONTENT_SOURCE_EVENT_ROW_FIELDS
                    for row in source_event_rows
                )
            )
            self.assertTrue(
                all(
                    set(row) == CONTENT_SCOPE_EVENT_ROW_FIELDS
                    for row in scope_event_rows
                )
            )

            original_rows = self.events[persona_id]
            original_source_rows = [
                row for row in original_rows if set(row) == SOURCE_EVENT_ROW_FIELDS
            ]
            original_scope_rows = [
                row for row in original_rows if set(row) == SCOPE_EVENT_ROW_FIELDS
            ]
            self.assertEqual(
                source_event_rows,
                [
                    {key: row[key] for key in CONTENT_SOURCE_EVENT_ROW_FIELDS}
                    for row in original_source_rows
                ],
            )
            self.assertEqual(
                scope_event_rows,
                [
                    {key: row[key] for key in CONTENT_SCOPE_EVENT_ROW_FIELDS}
                    for row in original_scope_rows
                ],
            )
            dependency_counts = Counter(
                row["dependency_group_key"] for row in original_rows
            )
            created_count = sum(
                row["after_source_intent_key"]
                == (
                    f"{persona_id}-pre-solve-source-intent-"
                    f"{row['event_sequence_ordinal']:04d}"
                )
                for row in original_source_rows
            )
            self.assertEqual(
                projection["summary"],
                {
                    "created_source_intent_count": created_count,
                    "lifecycle_event_content_row_count": len(original_rows),
                    "multi_event_dependency_group_count": sum(
                        count > 1 for count in dependency_counts.values()
                    ),
                    "negative_extra_witness_content_row_count": personas[
                        persona_id
                    ]["summary"]["negative_extra_physical_witness_count"],
                    "scope_event_content_row_count": len(original_scope_rows),
                    "selection_role_reference_count": sum(
                        len(row["selection_role_refs"]) for row in selection_rows
                    ),
                    "source_event_content_row_count": len(original_source_rows),
                    "source_selection_content_row_count": len(selection_rows),
                    "unique_selected_intent_count": len(selection_rows),
                },
            )
            _assert_no_forbidden_keys(self, projection)
            self.assertFalse(
                set(projection)
                & {
                    "authority",
                    "completion_claims",
                    "g0_contract_frozen",
                    "input_bindings",
                    "remaining_blockers",
                    "sha256",
                }
            )
        self.assertTrue(
            all(
                row["origin"] == "pilot"
                for persona in self.personas
                for row in persona["primary_match_rows"] + persona["companion_match_rows"]
            )
        )
        self.assertIs(
            self.suite["completion_claims"][
                "all_2300_lifecycle_source_refs_bound"
            ],
            True,
        )
        self.assertIs(
            self.suite["dependency_direction_contract"][
                "full_profile_is_exact-pilot-selection-reuse"
            ],
            True,
        )

    def test_event_inventory_exact_counts_diagnostics_order_and_receipts(self):
        self._ensure_events()
        suite_profiles = Counter()
        suite_rows = 0
        all_body_bytes = 0
        for persona in self.personas:
            persona_id = persona["persona_id"]
            rows = self.events[persona_id]
            profiles = Counter(row["event_profile_key"] for row in rows)
            suite_profiles.update(profiles)
            suite_rows += len(rows)

            expected_diagnostics = (
                (5 if persona_id in DERIVE_DIAGNOSTIC_PERSONAS else 0)
                + (5 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0)
            )
            self.assertEqual(len(rows), 379 + expected_diagnostics)
            self.assertEqual(
                [row["event_sequence_ordinal"] for row in rows],
                list(range(1, len(rows) + 1)),
            )
            for key, count in EXPECTED_SOURCE_EVENT_TYPES_PER_PERSONA.items():
                self.assertEqual(profiles[key], count, f"{persona_id}/{key}")
            self.assertEqual(profiles["w5-forced-purged-commit"], 15)
            self.assertEqual(profiles["ordinary-scope-index"], 100)
            self.assertEqual(profiles["w5-post-purge-noop-index"], 20)
            self.assertEqual(
                profiles["w3-derive-diagnostic"],
                5 if persona_id in DERIVE_DIAGNOSTIC_PERSONAS else 0,
            )
            self.assertEqual(
                profiles["w3-duplicate-diagnostic-same-scope"],
                3 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0,
            )
            self.assertEqual(
                profiles["w3-duplicate-diagnostic-cross-scope"],
                2 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0,
            )

            source_rows = [row for row in rows if "source_intent_key" in row]
            scope_rows = [row for row in rows if "abstract_scope_slot_ordinal" in row]
            self.assertEqual(len(scope_rows), 120)
            self.assertEqual(len(source_rows), len(rows) - 120)
            self.assertTrue(all(set(row) == SOURCE_EVENT_ROW_FIELDS for row in source_rows))
            self.assertTrue(all(set(row) == SCOPE_EVENT_ROW_FIELDS for row in scope_rows))

            body = package.source_matched_lifecycle_event_body_bytes(persona_id)
            body_rows = _jsonl_rows(body)
            self.assertEqual(body_rows, rows)
            self.assertLessEqual(len(body), EXPECTED_MAX_EVENT_BODY_BYTES)
            receipt = persona["event_receipt"]
            self.assertEqual(set(receipt), EVENT_RECEIPT_FIELDS)
            self.assertEqual(receipt["body_bytes"], len(body))
            self.assertEqual(receipt["body_sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(receipt["row_count"], len(rows))
            self.assertEqual(receipt["first_event_sequence_ordinal"], 1)
            self.assertEqual(receipt["last_event_sequence_ordinal"], len(rows))
            self.assertEqual(
                receipt["first_event_intent_key"], rows[0]["event_intent_key"]
            )
            self.assertEqual(
                receipt["last_event_intent_key"], rows[-1]["event_intent_key"]
            )
            self.assertIs(receipt["body_persisted"], False)
            self.assertEqual(
                receipt["maximum_row_bytes_including_lf"],
                max(len(raw) + 1 for raw in body.splitlines()),
            )
            self.assertLessEqual(
                receipt["maximum_row_bytes_including_lf"],
                EXPECTED_MAX_EVENT_ROW_BYTES_INCLUDING_LF,
            )
            all_body_bytes += len(body)

        self.assertEqual(suite_rows, EXPECTED_EVENT_COUNT)
        self.assertEqual(
            sum(suite_profiles[key] for key in EXPECTED_SOURCE_EVENT_TYPES_PER_PERSONA),
            EXPECTED_SOURCE_EVENT_COUNT,
        )
        self.assertEqual(suite_profiles["w3-derive-diagnostic"], 20)
        self.assertEqual(
            suite_profiles["w3-duplicate-diagnostic-same-scope"]
            + suite_profiles["w3-duplicate-diagnostic-cross-scope"],
            30,
        )
        self.assertEqual(suite_profiles["w5-forced-purged-commit"], 300)
        self.assertEqual(suite_profiles["ordinary-scope-index"], 2_000)
        self.assertEqual(suite_profiles["w5-post-purge-noop-index"], 400)
        self.assertEqual(
            self.suite["summary"]["maximum_event_body_bytes_nonpersisted"],
            max(value["event_receipt"]["body_bytes"] for value in self.personas),
        )
        self.assertEqual(
            self.suite["summary"]["maximum_event_row_bytes_including_lf"],
            max(
                value["event_receipt"]["maximum_row_bytes_including_lf"]
                for value in self.personas
            ),
        )
        self.assertGreater(all_body_bytes, 0)

    def test_created_source_identity_and_dependency_group_closure_are_exact(self):
        self._ensure_events()
        personas = self._persona_by_id()
        expected_group_kinds = Counter(
            {
                "index-w1": 1,
                "index-w2": 1,
                "index-w3": 1,
                "index-w4": 1,
                "index-w5-final": 1,
                "index-w5-pre-purge": 1,
                "mirror-w1": 1,
                "mirror-w3": 1,
                "move-bundle": 1,
                "p5": 15,
                "x4": 20,
                "x5": 10,
            }
        )
        suite_created_source_intents = 0
        suite_multi_event_groups = 0
        for persona_id in envelope.PERSONA_IDS:
            rows = self.events[persona_id]
            event_by_key = {row["event_intent_key"]: row for row in rows}
            self.assertEqual(len(event_by_key), len(rows))
            source_rows = [row for row in rows if set(row) == SOURCE_EVENT_ROW_FIELDS]
            created_after_keys = []
            for row in source_rows:
                ordinal = row["event_sequence_ordinal"]
                self.assertEqual(
                    row["event_intent_key"],
                    f"{persona_id}-lifecycle-event-intent-{ordinal:04d}",
                )
                self.assertIs(type(row["source_intent_key"]), str)
                self.assertIs(type(row["after_source_intent_key"]), str)
                expected_created_key = (
                    f"{persona_id}-pre-solve-source-intent-{ordinal:04d}"
                )
                if row["event_profile_key"] in CREATED_SOURCE_EVENT_PROFILES:
                    self.assertEqual(
                        row["after_source_intent_key"], expected_created_key
                    )
                    created_after_keys.append(row["after_source_intent_key"])
                else:
                    self.assertEqual(
                        row["after_source_intent_key"], row["source_intent_key"]
                    )

                predecessors = row["predecessor_event_intent_refs"]
                self.assertIs(type(predecessors), list)
                self.assertEqual(len(predecessors), len(set(predecessors)))
                predecessor_ordinals = []
                for predecessor_key in predecessors:
                    self.assertIn(predecessor_key, event_by_key)
                    predecessor = event_by_key[predecessor_key]
                    self.assertEqual(predecessor["persona_id"], persona_id)
                    self.assertLess(predecessor["event_sequence_ordinal"], ordinal)
                    predecessor_ordinals.append(
                        predecessor["event_sequence_ordinal"]
                    )
                self.assertEqual(predecessor_ordinals, sorted(predecessor_ordinals))

            expected_diagnostics = (
                (5 if persona_id in DERIVE_DIAGNOSTIC_PERSONAS else 0)
                + (5 if persona_id in DUPLICATE_DIAGNOSTIC_PERSONAS else 0)
            )
            self.assertEqual(
                len(created_after_keys),
                EXPECTED_CREATED_SOURCE_INTENT_BASE_COUNT_PER_PERSONA
                + expected_diagnostics,
            )
            self.assertEqual(len(created_after_keys), len(set(created_after_keys)))
            suite_created_source_intents += len(created_after_keys)
            selected_intents = {
                row["intent_key"]
                for row in personas[persona_id]["primary_match_rows"]
                + personas[persona_id]["companion_match_rows"]
            }
            self.assertTrue(set(created_after_keys).isdisjoint(selected_intents))

            grouped = defaultdict(list)
            for row in rows:
                grouped[row["dependency_group_key"]].append(row)
            multi = {
                key: members for key, members in grouped.items() if len(members) > 1
            }
            self.assertEqual(
                len(multi), EXPECTED_MULTI_EVENT_DEPENDENCY_GROUP_COUNT_PER_PERSONA
            )
            suite_multi_event_groups += len(multi)
            observed_group_kinds = Counter()
            for group_key, members in multi.items():
                profiles = Counter(row["event_profile_key"] for row in members)
                by_profile = {row["event_profile_key"]: row for row in members}
                if "-event-dependency-x4-" in group_key:
                    kind = "x4"
                    self.assertEqual(
                        profiles,
                        Counter({"w4-create-x-prime": 1, "w4-delete": 1}),
                    )
                    self.assertIn(
                        by_profile["w4-delete"]["event_intent_key"],
                        by_profile["w4-create-x-prime"][
                            "predecessor_event_intent_refs"
                        ],
                    )
                elif "-event-dependency-x5-" in group_key:
                    kind = "x5"
                    self.assertEqual(
                        profiles,
                        Counter(
                            {
                                "w5-delete-x-prime": 1,
                                "w5-export-x": 1,
                                "w5-restore-x": 1,
                            }
                        ),
                    )
                    self.assertEqual(
                        by_profile["w5-restore-x"][
                            "predecessor_event_intent_refs"
                        ],
                        [by_profile["w5-export-x"]["event_intent_key"]],
                    )
                    delete_predecessor_profiles = {
                        event_by_key[key]["event_profile_key"]
                        for key in by_profile["w5-delete-x-prime"][
                            "predecessor_event_intent_refs"
                        ]
                    }
                    self.assertEqual(
                        delete_predecessor_profiles,
                        {"w4-create-x-prime", "w5-restore-x"},
                    )
                elif "-event-dependency-p5-" in group_key:
                    kind = "p5"
                    self.assertEqual(
                        profiles,
                        Counter(
                            {
                                "w5-create-p-prime": 1,
                                "w5-forced-purged-commit": 1,
                                "w5-purge-p": 1,
                            }
                        ),
                    )
                    self.assertIn(
                        by_profile["w5-create-p-prime"]["event_intent_key"],
                        by_profile["w5-purge-p"][
                            "predecessor_event_intent_refs"
                        ],
                    )
                    self.assertEqual(
                        by_profile["w5-forced-purged-commit"][
                            "predecessor_event_intent_refs"
                        ],
                        [by_profile["w5-purge-p"]["event_intent_key"]],
                    )
                elif group_key.endswith("-event-dependency-move-bundle"):
                    kind = "move-bundle"
                    self.assertEqual(profiles, Counter({"w2-move": 5}))
                elif group_key.endswith("-event-dependency-mirror-w1"):
                    kind = "mirror-w1"
                    self.assertEqual(profiles, Counter({"w1-typed-edit": 2}))
                    self.assertTrue(
                        any(
                            other["event_intent_key"]
                            in row["predecessor_event_intent_refs"]
                            for row in members
                            for other in members
                            if row is not other
                        )
                    )
                elif group_key.endswith("-event-dependency-mirror-w3"):
                    kind = "mirror-w3"
                    self.assertEqual(profiles, Counter({"w3-surface-edit": 2}))
                    self.assertTrue(
                        any(
                            other["event_intent_key"]
                            in row["predecessor_event_intent_refs"]
                            for row in members
                            for other in members
                            if row is not other
                        )
                    )
                elif "-event-dependency-index-barrier-" in group_key:
                    wave_key = group_key.rsplit(
                        "-event-dependency-index-barrier-", 1
                    )[-1]
                    kind = f"index-{wave_key}"
                    expected_profile = (
                        "w5-post-purge-noop-index"
                        if wave_key == "w5-final"
                        else "ordinary-scope-index"
                    )
                    self.assertEqual(
                        profiles, Counter({expected_profile: 20})
                    )
                    wave = members[0]["wave"]
                    source_predecessors = [
                        row
                        for row in rows
                        if set(row) == SOURCE_EVENT_ROW_FIELDS
                        and row["wave"] == wave
                    ]
                    self.assertTrue(source_predecessors)
                    last_source = max(
                        source_predecessors,
                        key=lambda row: row["event_sequence_ordinal"],
                    )
                    for row in members:
                        self.assertEqual(
                            row["predecessor_event_intent_refs"],
                            [last_source["event_intent_key"]],
                        )
                        self.assertLess(
                            last_source["event_sequence_ordinal"],
                            row["event_sequence_ordinal"],
                        )
                else:
                    self.fail(f"unexpected multi-event dependency group: {group_key}")
                observed_group_kinds[kind] += 1
            self.assertEqual(observed_group_kinds, expected_group_kinds)
        self.assertEqual(
            suite_created_source_intents, EXPECTED_CREATED_SOURCE_INTENT_COUNT
        )
        self.assertEqual(
            suite_multi_event_groups,
            EXPECTED_MULTI_EVENT_DEPENDENCY_GROUP_COUNT,
        )

    def test_diagnostic_sources_are_distinct_stable_current_matches(self):
        self._ensure_events()
        for persona in self.personas:
            persona_id = persona["persona_id"]
            by_capability = {
                row["capability_key"]: row for row in persona["primary_match_rows"]
            }
            diagnostic = [
                row
                for row in self.events[persona_id]
                if "diagnostic" in row["event_profile_key"]
            ]
            self.assertEqual(
                len({row["source_intent_key"] for row in diagnostic}),
                len(diagnostic),
            )
            for row in diagnostic:
                match = by_capability[row["capability_key"]]
                self.assertEqual(row["source_intent_key"], match["intent_key"])
                self.assertTrue(match["capability_class_key"].startswith("stable-current"))
            duplicate = [
                row
                for row in diagnostic
                if "duplicate-diagnostic" in row["event_profile_key"]
            ]
            if duplicate:
                duplicate.sort(
                    key=lambda row: (
                        hashlib.sha256(
                            b"kio-lifecycle-v1/diagnostic-source/"
                            + row["source_intent_key"].encode("ascii")
                        ).digest(),
                        row["source_intent_key"].encode("ascii"),
                    )
                )
                self.assertEqual(
                    [row["event_profile_key"] for row in duplicate],
                    [
                        "w3-duplicate-diagnostic-same-scope",
                        "w3-duplicate-diagnostic-cross-scope",
                        "w3-duplicate-diagnostic-same-scope",
                        "w3-duplicate-diagnostic-cross-scope",
                        "w3-duplicate-diagnostic-same-scope",
                    ],
                )

    def test_artifacts_remain_strict_non_authorizing_and_forbidden_field_free(self):
        self._ensure_events()
        self.assertEqual(package.MAX_EVENT_BODY_BYTES, EXPECTED_MAX_EVENT_BODY_BYTES)
        self.assertEqual(
            package.MAX_EVENT_ROW_BYTES_INCLUDING_LF,
            EXPECTED_MAX_EVENT_ROW_BYTES_INCLUDING_LF,
        )
        self.assertEqual(set(self.suite["authority"]), package.AUTHORITY_FIELDS)
        for value in [*self.personas, self.suite]:
            self.assertIs(value["g0_contract_frozen"], False)
            self.assertEqual(set(value["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(
                all(
                    type(flag) is bool and flag is False
                    for flag in value["authority"].values()
                )
            )
            _assert_no_forbidden_keys(self, value)
            _assert_strict_json_domain(self, value)
            self.assertIs(
                value["completion_claims"]["query_or_oracle_dependency_present"],
                False,
            )
        for projection in self.projections:
            _assert_no_forbidden_keys(self, projection)
            _assert_strict_json_domain(self, projection)
        for rows in self.events.values():
            for row in rows:
                _assert_no_forbidden_keys(self, row)
                _assert_strict_json_domain(self, row)

        for module in (package, independent):
            tree = ast.parse(inspect.getsource(module))
            imported = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.append(node.module or "")
            self.assertFalse(
                any("query" in name.lower() or "oracle" in name.lower() for name in imported)
            )

        # Negative capability/authority claims are safe metadata, not a query
        # dependency.  Exact downstream identity fields still fail closed.
        package._reject_prohibited_keys(
            {"query_or_oracle_dependency_present": False}
        )
        with self.assertRaises(
            package.PersonaV2SourceMatchedLifecycleInventoryError
        ):
            package._reject_prohibited_keys({"query_id": "forbidden"})

    def test_independent_validator_reconstructs_suite_and_content_projection(self):
        self._ensure_events()
        validator_source = inspect.getsource(independent)
        producer_import_examples = (
            "import eval.persona_v2_source_matched_lifecycle_inventory\n",
            "from eval import persona_v2_source_matched_lifecycle_inventory\n",
            "from . import persona_v2_source_matched_lifecycle_inventory\n",
            "from .persona_v2_source_matched_lifecycle_inventory import X\n",
            "from parent.eval.persona_v2_source_matched_lifecycle_inventory import X\n",
        )
        self.assertTrue(all(map(_imports_producer_module, producer_import_examples)))
        self.assertFalse(_imports_producer_module("from eval import unrelated\n"))
        self.assertFalse(
            _imports_producer_module(validator_source),
            "independent validator imports the producer through an AST-resolved path",
        )
        self.assertTrue(
            independent.validate_source_matched_lifecycle_suite_descriptor(
                self.suite,
                persona_provider=package.build_source_matched_lifecycle_persona,
                event_body_provider=package.source_matched_lifecycle_event_body_bytes,
                assignment_origin_provider=self._assignment_provider,
            )
        )
        self.assertTrue(
            independent.validate_source_matched_lifecycle_content_projection(
                "p01",
                self.projections[0],
                assignment_origin_provider=self._assignment_provider,
            )
        )

        # The producer entry point must delegate, but this assertion avoids a
        # second complete independent reconstruction in the same process.
        with mock.patch.object(
            independent,
            "validate_source_matched_lifecycle_suite_descriptor",
            return_value=True,
        ) as validate:
            self.assertTrue(
                package.validate_source_matched_lifecycle_suite_descriptor(
                    self.suite
                )
            )
        validate.assert_called_once_with(self.suite)

    def test_public_persona_content_validator_and_sha_api_wiring(self):
        self._ensure_package()
        persona = self.personas[0]
        projection = self.projections[0]

        with mock.patch.object(
            independent,
            "validate_source_matched_lifecycle_persona",
            return_value=True,
        ) as validate_persona:
            self.assertTrue(
                package.validate_source_matched_lifecycle_persona("p01", persona)
            )
        validate_persona.assert_called_once_with(
            "p01",
            persona,
            event_body_provider=package.source_matched_lifecycle_event_body_bytes,
        )

        with mock.patch.object(
            independent,
            "validate_source_matched_lifecycle_content_projection",
            return_value=True,
        ) as validate_projection:
            self.assertTrue(
                package.validate_source_matched_lifecycle_content_projection(
                    "p01", projection
                )
            )
        validate_projection.assert_called_once_with("p01", projection)

        with (
            mock.patch.object(
                package,
                "build_source_matched_lifecycle_persona",
                return_value=persona,
            ) as build_persona_sha,
            mock.patch.object(
                package,
                "validate_source_matched_lifecycle_persona",
                return_value=True,
            ) as validate_persona_sha,
        ):
            persona_sha = package.source_matched_lifecycle_persona_sha256("p01")
        build_persona_sha.assert_called_once_with("p01")
        validate_persona_sha.assert_called_once_with("p01", persona)
        self.assertEqual(
            persona_sha,
            hashlib.sha256(package.canonical_json_bytes(persona)).hexdigest(),
        )

        with (
            mock.patch.object(
                package,
                "build_source_matched_lifecycle_suite_descriptor",
                return_value=self.suite,
            ) as build_suite_sha,
            mock.patch.object(
                package,
                "validate_source_matched_lifecycle_suite_descriptor",
                return_value=True,
            ) as validate_suite_sha,
        ):
            suite_sha = package.source_matched_lifecycle_suite_sha256()
        build_suite_sha.assert_called_once_with()
        validate_suite_sha.assert_called_once_with(self.suite)
        self.assertEqual(
            suite_sha,
            hashlib.sha256(package.canonical_json_bytes(self.suite)).hexdigest(),
        )

        with (
            mock.patch.object(
                package,
                "build_source_matched_lifecycle_content_projection",
                return_value=projection,
            ) as build_projection_sha,
            mock.patch.object(
                package,
                "validate_source_matched_lifecycle_content_projection",
                return_value=True,
            ) as validate_projection_sha,
        ):
            projection_sha = package.source_matched_lifecycle_content_projection_sha256(
                "p01"
            )
        build_projection_sha.assert_called_once_with("p01")
        validate_projection_sha.assert_called_once_with("p01", projection)
        self.assertEqual(
            projection_sha,
            hashlib.sha256(package.canonical_json_bytes(projection)).hexdigest(),
        )

    def test_dependency_tamper_repin_and_producer_snapshot_toctou_fail_closed(self):
        self._ensure_package()
        coverage = copy.deepcopy(package._cached_global_inputs()["coverage"])
        coverage["primary_capabilities"][0]["allocation_class"] = "Y"
        raw = artifact_common.canonical_json_bytes(
            coverage,
            label="re-pinned tampered lifecycle coverage",
            max_bytes=2 * 2**20,
        )
        # Even a coordinated dependency-pin change must not bypass the
        # upstream semantic validator.
        forged_pin = (len(raw), hashlib.sha256(raw).hexdigest())
        with (
            mock.patch.dict(
                independent.EXPECTED_DEPENDENCY_PINS,
                {"persona-v2-lifecycle-coverage-catalog": forged_pin},
            ),
            self.assertRaises(
                independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
            ),
        ):
            independent.validate_source_matched_lifecycle_persona(
                "p01", self.personas[0], coverage_value=coverage
            )

        cached = package._cached_global_inputs()
        original = cached["bindings"][0]["sha256"]

        def mutate_dependency(inputs):
            inputs["bindings"][0]["sha256"] = "0" * 64

        try:
            with self.assertRaises(package.PersonaV2SourceMatchedLifecycleInventoryError):
                package._build_source_matched_lifecycle_persona(
                    "p01", dependency_observer=mutate_dependency
                )
        finally:
            cached["bindings"][0]["sha256"] = original

    def test_independent_target_mutation_during_event_callback_is_rejected(self):
        self._ensure_package()
        target = copy.deepcopy(self.personas[0])
        mutated = False

        def mutating_event_provider(persona_id):
            nonlocal mutated
            if not mutated:
                target["summary"]["event_intent_count"] = 0
                mutated = True
            return package.source_matched_lifecycle_event_body_bytes(persona_id)

        with self.assertRaisesRegex(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
            "mutated during provider callbacks",
        ):
            independent.validate_source_matched_lifecycle_persona(
                "p01",
                target,
                event_body_provider=mutating_event_provider,
                assignment_origin_provider=self._assignment_provider,
            )

    def test_independent_persona_target_aba_relay_uses_opening_snapshot(self):
        self._ensure_package()
        canonical = self.personas[0]
        target = copy.deepcopy(canonical)
        canonical_event_count = canonical["summary"]["event_intent_count"]
        target["summary"]["event_intent_count"] = 0
        assignment_calls = []
        event_calls = []

        def restoring_assignment_provider(persona_id):
            assignment_calls.append(persona_id)
            target["summary"]["event_intent_count"] = canonical_event_count
            return self._assignment_provider(persona_id)

        def restoring_event_provider(persona_id):
            event_calls.append(persona_id)
            target["summary"]["event_intent_count"] = 0
            return package.source_matched_lifecycle_event_body_bytes(persona_id)

        # A live-target validator accepted this relay: the assignment callback
        # changed tampered -> canonical before semantic comparison, then the
        # event callback changed canonical -> opening tamper before postflight.
        # A detached opening snapshot rejects before the closing callback runs.
        with self.assertRaises(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
        ):
            independent.validate_source_matched_lifecycle_persona(
                "p01",
                target,
                event_body_provider=restoring_event_provider,
                assignment_origin_provider=restoring_assignment_provider,
            )
        self.assertEqual(assignment_calls, ["p01", "p01"])
        self.assertEqual(event_calls, [])
        self.assertEqual(
            target["summary"]["event_intent_count"], canonical_event_count
        )

    def test_independent_suite_target_aba_relay_uses_opening_snapshot(self):
        self._ensure_package()
        canonical = self.suite
        target = copy.deepcopy(canonical)
        canonical_primary_count = canonical["summary"][
            "primary_source_match_count"
        ]
        target["summary"]["primary_source_match_count"] = 0
        opening = package.canonical_json_bytes(target)
        personas = self._persona_by_id()
        assignment_calls = []
        persona_calls = []

        def restoring_assignment_provider(persona_id):
            assignment_calls.append(persona_id)
            target["summary"][
                "primary_source_match_count"
            ] = canonical_primary_count
            return {"unused-by-focused-reconstruction": True}

        def focused_reconstruction(
            _inputs, persona_id, *, assignment_origin_provider=None
        ):
            assignment_origin_provider(persona_id)
            return {
                "event_rows": [],
                "persona": copy.deepcopy(personas[persona_id]),
            }

        def restoring_persona_provider(persona_id):
            persona_calls.append(persona_id)
            target["summary"]["primary_source_match_count"] = 0
            return copy.deepcopy(personas[persona_id])

        # Coordinated re-pinning is test-only.  With the historical live target,
        # assignment callbacks made the semantic body canonical, persona
        # callbacks restored the opening tamper, and the forged opening pin made
        # the complete relay validate.  The opening snapshot remains tampered.
        with (
            mock.patch.object(
                independent,
                "EXPECTED_SUITE_CANONICAL_BYTES",
                len(opening),
            ),
            mock.patch.object(
                independent,
                "EXPECTED_SUITE_SHA256",
                hashlib.sha256(opening).hexdigest(),
            ),
            mock.patch.object(
                independent,
                "_resolve_inputs",
                return_value=({}, {}, {}, {}),
            ),
            mock.patch.object(
                independent,
                "_reconstruct_expected_persona",
                side_effect=focused_reconstruction,
            ),
            mock.patch.object(
                independent,
                "_expected_suite_value",
                return_value=copy.deepcopy(canonical),
            ),
            self.assertRaises(
                independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
            ),
        ):
            independent.validate_source_matched_lifecycle_suite_descriptor(
                target,
                persona_provider=restoring_persona_provider,
                assignment_origin_provider=restoring_assignment_provider,
            )
        self.assertEqual(assignment_calls, list(envelope.PERSONA_IDS))
        self.assertEqual(persona_calls, [])
        self.assertEqual(
            target["summary"]["primary_source_match_count"],
            canonical_primary_count,
        )

    def test_independent_projection_callback_compares_detached_opening_snapshot(self):
        self._ensure_package()
        canonical = self.projections[0]
        target = copy.deepcopy(canonical)
        summary_key = "source_selection_content_row_count"
        canonical_count = canonical["summary"][summary_key]
        target["summary"][summary_key] = 0
        assignment_calls = []
        projection_comparands = []
        strict_equal = independent._strict_equal

        def restoring_assignment_provider(persona_id):
            assignment_calls.append(persona_id)
            target["summary"][summary_key] = canonical_count
            return self._assignment_provider(persona_id)

        def observing_strict_equal(value, expected):
            if (
                type(value) is dict
                and value.get("artifact_schema") == independent.PROJECTION_SCHEMA
            ):
                projection_comparands.append(value)
            return strict_equal(value, expected)

        with (
            mock.patch.object(
                independent,
                "_strict_equal",
                side_effect=observing_strict_equal,
            ),
            self.assertRaises(
                independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
            ),
        ):
            independent.validate_source_matched_lifecycle_content_projection(
                "p01",
                target,
                assignment_origin_provider=restoring_assignment_provider,
            )
        self.assertEqual(assignment_calls, ["p01", "p01"])
        self.assertEqual(len(projection_comparands), 1)
        self.assertIsNot(projection_comparands[0], target)
        self.assertEqual(projection_comparands[0]["summary"][summary_key], 0)
        self.assertEqual(target["summary"][summary_key], canonical_count)

    def test_event_provider_types_coordinates_nondeterminism_and_bounds_fail_closed(self):
        self._ensure_package()
        receipt = self.personas[0]["event_receipt"]
        baseline = package.source_matched_lifecycle_event_body_bytes("p01")

        calls = 0

        def nondeterministic(persona_id):
            nonlocal calls
            calls += 1
            self.assertEqual(persona_id, "p01")
            return baseline if calls == 1 else baseline[:-1]

        with self.assertRaisesRegex(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
            "nondeterministic|alias-mutated",
        ):
            independent._event_rows_from_provider("p01", receipt, nondeterministic)

        with self.assertRaisesRegex(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
            "exact bytes",
        ):
            independent._event_rows_from_provider(
                "p01", receipt, lambda _persona: bytearray(baseline)
            )

        with self.assertRaises(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
        ):
            independent._event_rows_from_provider(
                "p01",
                receipt,
                lambda _persona: package.source_matched_lifecycle_event_body_bytes(
                    "p02"
                ),
            )

        oversized_calls = 0

        def oversized_first(_persona):
            nonlocal oversized_calls
            oversized_calls += 1
            if oversized_calls != 1:
                raise AssertionError("receipt mismatch must stop before replay")
            return baseline + b"x"

        with self.assertRaisesRegex(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
            "authenticated receipt",
        ):
            independent._event_rows_from_provider(
                "p01", receipt, oversized_first
            )
        self.assertEqual(oversized_calls, 1)

        preflight_calls = 0

        def forbidden_preflight_callback():
            nonlocal preflight_calls
            preflight_calls += 1
            return b"x"

        valid_sha = hashlib.sha256(b"x").hexdigest()
        malformed_descriptors = (
            (0, valid_sha, 1),
            (2, valid_sha, 1),
            (1, valid_sha[:-1], 1),
            (1, "G" * 64, 1),
            (1, valid_sha, True),
        )
        for (
            expected_bytes,
            expected_sha256,
            maximum_bytes,
        ) in malformed_descriptors:
            with (
                self.subTest(
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                    maximum_bytes=maximum_bytes,
                ),
                self.assertRaisesRegex(
                    independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
                    "invalid authenticated receipt bounds",
                ),
            ):
                independent._authenticated_body(
                    forbidden_preflight_callback,
                    (),
                    expected_bytes=expected_bytes,
                    expected_sha256=expected_sha256,
                    maximum_bytes=maximum_bytes,
                    label="focused malformed descriptor",
                    replay=True,
                )
        self.assertEqual(preflight_calls, 0)

        replay_values = iter((b"x", b"xx"))
        with (
            mock.patch.object(independent.hmac, "compare_digest") as compare,
            self.assertRaisesRegex(
                independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
                "pre-compare byte bound",
            ),
        ):
            independent._authenticated_body(
                lambda: next(replay_values),
                (),
                expected_bytes=1,
                expected_sha256=valid_sha,
                maximum_bytes=1,
                label="focused oversized replay",
                replay=True,
            )
        compare.assert_not_called()

        class DerivedBytes(bytes):
            pass

        replay_values = iter((b"x", DerivedBytes(b"x")))
        with (
            mock.patch.object(independent.hmac, "compare_digest") as compare,
            self.assertRaisesRegex(
                independent.PersonaV2SourceMatchedLifecycleInventoryValidationError,
                "replay must return exact bytes",
            ),
        ):
            independent._authenticated_body(
                lambda: next(replay_values),
                (),
                expected_bytes=1,
                expected_sha256=valid_sha,
                maximum_bytes=1,
                label="focused replay byte subclass",
                replay=True,
            )
        compare.assert_not_called()

        with self.assertRaises(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
        ):
            independent._event_rows_from_provider("p01", receipt, "not-callable")

    def test_public_builds_are_detached_and_invalid_coordinates_fail_closed(self):
        self._ensure_package()
        cases = [
            (
                package.build_source_matched_lifecycle_persona,
                ("p01",),
                lambda value: value["primary_match_rows"][0].update(
                    parameter_cell_key="mutated"
                ),
            ),
            (
                package.build_source_matched_lifecycle_suite_descriptor,
                (),
                lambda value: value["summary"].update(event_intent_count=0),
            ),
            (
                package.build_source_matched_lifecycle_content_projection,
                ("p01",),
                lambda value: value["content_sections"]["source_selection_rows"][
                    0
                ].update(variant_id="mutated"),
            ),
        ]
        for builder, args, mutate in cases:
            with self.subTest(builder=builder.__name__):
                first = builder(*args)
                baseline = package.canonical_json_bytes(first)
                mutate(first)
                self.assertEqual(
                    package.canonical_json_bytes(builder(*args)), baseline
                )

        for invalid in (True, "p00", "p01 ", None):
            with self.subTest(invalid=invalid):
                with self.assertRaises(
                    package.PersonaV2SourceMatchedLifecycleInventoryError
                ):
                    package.build_source_matched_lifecycle_persona(invalid)
                with self.assertRaises(
                    package.PersonaV2SourceMatchedLifecycleInventoryError
                ):
                    list(package.iter_source_matched_lifecycle_event_rows(invalid))
        with self.assertRaises(package.PersonaV2SourceMatchedLifecycleInventoryError):
            package.require_compiled_history_and_solution()

    def test_strict_bool_int_null_float_and_forbidden_alias_tamper_are_rejected(self):
        self._ensure_package()
        for replacement in (True, None, 1.0, -1):
            changed = copy.deepcopy(self.suite)
            changed["summary"]["event_intent_count"] = replacement
            with self.subTest(replacement=replacement):
                with self.assertRaises(
                    independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
                ):
                    independent.validate_source_matched_lifecycle_suite_descriptor(
                        changed
                    )

        changed = copy.deepcopy(self.suite)
        changed["query_id"] = "forbidden-downstream-id"
        with self.assertRaises(
            independent.PersonaV2SourceMatchedLifecycleInventoryValidationError
        ):
            independent.validate_source_matched_lifecycle_suite_descriptor(changed)

    def test_z_hashseed_full_suite_cold_build_is_deterministic_and_resource_bounded(self):
        self._ensure_package()
        expected_persona = package.canonical_json_bytes(self.personas[0])
        expected_event = package.source_matched_lifecycle_event_body_bytes("p01")
        expected_projection = package.canonical_json_bytes(self.projections[0])
        expected_projection_sha256_by_persona = {
            projection["persona_id"]: hashlib.sha256(
                package.canonical_json_bytes(projection)
            ).hexdigest()
            for projection in self.projections
        }
        expected_suite = package.canonical_json_bytes(self.suite)
        script = r'''
import hashlib
import json
import resource
import sys
import time
from eval import persona_v2_contract as envelope
from eval import persona_v2_source_matched_lifecycle_inventory as package

started = time.monotonic()
persona = package.build_source_matched_lifecycle_persona("p01")
event_body = package.source_matched_lifecycle_event_body_bytes("p01")
projection = package.build_source_matched_lifecycle_content_projection("p01")
suite = package.build_source_matched_lifecycle_suite_descriptor()
persona_raw = package.canonical_json_bytes(persona)
projection_raw = package.canonical_json_bytes(projection)
suite_raw = package.canonical_json_bytes(suite)
projection_sha256_by_persona = {
    persona_id: hashlib.sha256(package.canonical_json_bytes(
        package.build_source_matched_lifecycle_content_projection(persona_id)
    )).hexdigest()
    for persona_id in envelope.PERSONA_IDS
}
maximum_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
rss_bytes = int(maximum_rss) if sys.platform == "darwin" else int(maximum_rss) * 1024
print(json.dumps({
    "elapsed_seconds": time.monotonic() - started,
    "event_body_bytes": len(event_body),
    "event_body_sha256": hashlib.sha256(event_body).hexdigest(),
    "persona_bytes": len(persona_raw),
    "persona_sha256": hashlib.sha256(persona_raw).hexdigest(),
    "projection_bytes": len(projection_raw),
    "projection_sha256_by_persona": projection_sha256_by_persona,
    "projection_sha256": hashlib.sha256(projection_raw).hexdigest(),
    "rss_bytes": rss_bytes,
    "suite_bytes": len(suite_raw),
    "suite_sha256": hashlib.sha256(suite_raw).hexdigest(),
}, sort_keys=True, separators=(",", ":")))
'''
        environment = dict(os.environ)
        environment.update(
            {
                "LANG": "C",
                "LC_ALL": "C",
                "PYTHONHASHSEED": "73",
                "TZ": "UTC",
            }
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=environment,
            text=True,
            capture_output=True,
            check=True,
            timeout=MAX_COLD_BUILD_SECONDS,
        )
        self.assertEqual(completed.stderr, "")
        stdout = completed.stdout.strip()
        self.assertEqual(completed.stdout, stdout + "\n")
        measured = json.loads(stdout)
        self.assertEqual(
            stdout,
            json.dumps(measured, sort_keys=True, separators=(",", ":")),
        )
        self.assertEqual(measured["persona_bytes"], len(expected_persona))
        self.assertEqual(
            measured["persona_sha256"], hashlib.sha256(expected_persona).hexdigest()
        )
        self.assertEqual(measured["event_body_bytes"], len(expected_event))
        self.assertEqual(
            measured["event_body_sha256"], hashlib.sha256(expected_event).hexdigest()
        )
        self.assertEqual(measured["projection_bytes"], len(expected_projection))
        self.assertEqual(
            measured["projection_sha256"],
            hashlib.sha256(expected_projection).hexdigest(),
        )
        self.assertEqual(
            measured["projection_sha256_by_persona"],
            expected_projection_sha256_by_persona,
        )
        self.assertEqual(measured["suite_bytes"], len(expected_suite))
        self.assertEqual(
            measured["suite_sha256"], hashlib.sha256(expected_suite).hexdigest()
        )
        self.assertEqual(measured["suite_bytes"], EXPECTED_SUITE_BYTES)
        self.assertEqual(measured["suite_sha256"], EXPECTED_SUITE_SHA256)
        self.assertGreater(measured["elapsed_seconds"], 0)
        self.assertLessEqual(measured["elapsed_seconds"], MAX_COLD_BUILD_SECONDS)
        self.assertGreater(measured["rss_bytes"], 0)
        self.assertLessEqual(measured["rss_bytes"], MAX_COLD_BUILD_RSS_BYTES)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
