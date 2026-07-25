"""Fast focused tests for semantic-resolution feasibility audit v1."""

from __future__ import annotations

import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

from eval import persona_v2_contract as envelope
from eval import persona_v2_query_history_semantic_resolution_feasibility as package
from eval import persona_v2_query_history_semantic_resolution_feasibility_validator as independent


def _synthetic_snapshot():
    queries = []
    oracles = []
    lifecycles = []
    resolution_rows = []
    topics = []
    profiles = []
    plans = {}
    events = {}
    origins = {}
    class_sequence = (
        ["no-w0-profile-candidate"] * 36
        + ["singleton-only"] * 186
        + ["opposite-conflict"] * 30
        + ["graph-normal"] * 18
    )
    fact_by_class = {
        "no-w0-profile-candidate": "fact-no-w0",
        "singleton-only": "fact-singleton",
        "opposite-conflict": "fact-conflict",
        "graph-normal": "fact-normal",
    }
    for persona_id in envelope.PERSONA_IDS:
        topic_id = f"{persona_id}-topic"
        topics.append(
            {
                "graph_id": f"{persona_id}-graph",
                "persona_id": persona_id,
                "project_or_case_id": f"{persona_id}-project-ok",
                "topic_id": topic_id,
                "topic_slot": "g01",
            }
        )
        selected_profile = f"{persona_id}-profile-selected"
        singleton_profile = f"{persona_id}-profile-singleton"
        conflict_profile = f"{persona_id}-profile-conflict"
        normal_profile = f"{persona_id}-profile-normal"
        profiles.extend(
            [
                {
                    "fact_profile_id": selected_profile,
                    "persona_id": persona_id,
                    "present_fact_ids": [],
                    "profile_kind": "empty",
                },
                {
                    "fact_profile_id": singleton_profile,
                    "persona_id": persona_id,
                    "present_fact_ids": ["fact-singleton"],
                    "profile_kind": "w0-singleton",
                },
                {
                    "fact_profile_id": conflict_profile,
                    "persona_id": persona_id,
                    "present_fact_ids": ["fact-conflict"],
                    "profile_kind": "conflict-branch",
                },
                {
                    "fact_profile_id": normal_profile,
                    "persona_id": persona_id,
                    "present_fact_ids": ["fact-normal"],
                    "profile_kind": "graph-normal-w0",
                },
            ]
        )
        positive_queries = []
        negative_queries = []
        positive_oracles = []
        negative_oracles = []
        primary_matches = []
        effective_primary = []
        typed_witnesses = []
        distractor_cursor = 0
        for ordinal in range(1, 106):
            query_key = f"query-{persona_id}-{ordinal:03d}"
            capability_key = f"{persona_id}-capability-{ordinal:03d}"
            contributor = ordinal <= 100
            positive = ordinal <= 85 or ordinal > 100
            aligned = ordinal <= 13
            query = {
                "evaluation_class": (
                    "positive-recall" if positive else "purged-negative"
                ),
                "expected_empty": not positive,
                "language": "ja",
                "project_or_case_id": (
                    f"{persona_id}-project-ok"
                    if aligned
                    else f"{persona_id}-project-mismatch-{ordinal:03d}"
                ),
                "query_key": query_key,
            }
            if positive:
                positive_queries.append(query)
                distractors = []
                for distractor_ordinal in range(1, 4):
                    profile_class = class_sequence[distractor_cursor]
                    distractor_cursor += 1
                    distractors.append(
                        {
                            "distractor_fact_id": fact_by_class[profile_class],
                            "distractor_intent_key": (
                                f"{persona_id}-distractor-{distractor_cursor:03d}"
                            ),
                        }
                    )
                positive_oracles.append(
                    {
                        "abstract_answer_membership": {
                            "expected_fact_ids": ["fact-answer"],
                            "expected_revision_chain_ids": (
                                [f"revision-{ordinal:03d}"]
                                if ordinal <= 30
                                else []
                            ),
                        },
                        "distractors": distractors,
                        "language": "ja",
                        "query_intent_key": query_key,
                    }
                )
            else:
                negative_queries.append(query)
                negative_oracles.append(
                    {
                        "abstract_answer_membership": [],
                        "language": "ja",
                        "query_intent_key": query_key,
                    }
                )
            match = {
                "base_fact_profile_id": selected_profile,
                "base_language": "ja",
                "base_topic_id": topic_id,
                "capability_class_key": "synthetic-class",
                "capability_key": capability_key,
                "gate_role": (
                    "contract_contributor"
                    if contributor
                    else "incidental_searchable"
                ),
                "intent_key": f"{persona_id}-primary-{ordinal:03d}",
            }
            primary_matches.append(match)
            resolution_rows.append(
                {
                    "lifecycle_binding": {
                        "capability_class_key": "synthetic-class",
                        "capability_key": capability_key,
                        "required_event_profile_keys": [],
                    },
                    "persona_id": persona_id,
                    "query_key": query_key,
                }
            )
            if contributor:
                witness_ids = [] if positive else [f"{persona_id}-witness-{ordinal:03d}"]
                effective_primary.append(
                    {
                        "capability_key": capability_key,
                        "present_fact_ids": ["fact-answer"],
                        "topic_id": topic_id,
                        "witness_fact_ids": witness_ids,
                    }
                )
                if not positive:
                    typed_witnesses.append(
                        {
                            "capability_key": capability_key,
                            "fact_id": witness_ids[0],
                            "visibility_by_checkpoint": [
                                {"checkpoint": "W0", "state": "current"},
                                {"checkpoint": "W5-final", "state": "absent"},
                            ],
                        }
                    )
        if distractor_cursor != 270:
            raise AssertionError("synthetic distractor cardinality drifted")
        companions = [
            {
                "base_fact_profile_id": selected_profile,
                "intent_key": f"{persona_id}-companion-{ordinal:02d}",
            }
            for ordinal in range(1, 11)
        ]
        queries.append(
            {
                "negative_query_intents": negative_queries,
                "persona_id": persona_id,
                "positive_query_intents": positive_queries,
            }
        )
        oracles.append(
            {
                "negative_oracle_rows": negative_oracles,
                "persona_id": persona_id,
                "positive_oracle_rows": positive_oracles,
            }
        )
        lifecycles.append(
            {
                "companion_match_rows": companions,
                "persona_id": persona_id,
                "primary_match_rows": primary_matches,
            }
        )
        plans[persona_id] = {
            "companion_rows": [],
            "primary_rows": effective_primary,
            "typed_witness_rows": typed_witnesses,
        }
        events[persona_id] = []
        origins[persona_id] = [
            {
                "fact_profile_assignment_counts": [
                    {"fact_profile_id": selected_profile, "source_count": 115},
                    {"fact_profile_id": singleton_profile, "source_count": 5},
                    {"fact_profile_id": conflict_profile, "source_count": 30},
                    {"fact_profile_id": normal_profile, "source_count": 18},
                ]
            }
        ]
    return {
        "catalog": {"fact_profiles": profiles, "semantic_topics": topics},
        "effective_plans": plans,
        "event_rows": events,
        "lifecycles": lifecycles,
        "oracles": oracles,
        "queries": queries,
        "resolution": {"resolution_rows": resolution_rows},
        "semantic_origins": origins,
    }


class SemanticResolutionFeasibilityFastTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.package_golden = (
            package.EXPECTED_CANONICAL_BYTES,
            package.EXPECTED_SHA256,
        )
        cls.independent_golden = (
            independent.EXPECTED_CANONICAL_BYTES,
            independent.EXPECTED_SHA256,
        )
        cls.snapshot = _synthetic_snapshot()
        cls.value = package._build_query_history_semantic_resolution_feasibility_audit(
            snapshot=cls.snapshot
        )
        # The synthetic body is intentionally not the all-persona actual
        # golden.  Keep it available after a future freeze so focused schema
        # tests do not weaken the public golden boundary.
        cls.raw = package._canonical(cls.value)

    def setUp(self):
        # Public candidate/preflight paths must reject this synthetic fixture
        # after freeze.  Focused tests explicitly unfreeze those paths and the
        # dedicated golden tests below exercise the frozen behavior directly.
        for module, name in (
            (package, "EXPECTED_CANONICAL_BYTES"),
            (package, "EXPECTED_SHA256"),
            (independent, "EXPECTED_CANONICAL_BYTES"),
            (independent, "EXPECTED_SHA256"),
        ):
            patcher = mock.patch.object(module, name, None)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_exact_non_authorizing_audit_and_no_resolution_v2(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(
            self.value["completion_claims"][
                "query_history_target_resolution_v2_issued"
            ],
            False,
        )
        self.assertEqual(
            self.value["resolution_publication_contract"]["artifact_role"],
            "audit-only-active-blocker-evidence",
        )
        bindings = {
            row["dependency_id"]: row for row in self.value["dependency_bindings"]
        }
        self.assertEqual(
            bindings["source-matched-lifecycle-suite-v1"]["dependency_pin"][
                "artifact_schema"
            ],
            "kcs.persona.pc-source-matched-lifecycle-suite/v1",
        )
        self.assertEqual(
            bindings["lifecycle-effective-membership-reconciliation-v1"][
                "dependency_pin"
            ]["artifact_schema"],
            "kcs.persona.pc-lifecycle-effective-membership-reconciliation/v1",
        )
        self.assertEqual(len(self.value["live_join_bindings"]), 4)
        self.assertTrue(
            all(
                row["status"] == "exact-live-join-projection-bound"
                for row in self.value["live_join_bindings"]
            )
        )

    def test_all_twenty_personas_and_exact_synthetic_baseline_counts(self):
        rows = self.value["persona_feasibility_rows"]
        self.assertEqual([row["persona_id"] for row in rows], list(envelope.PERSONA_IDS))
        self.assertEqual(len(rows), 20)
        self.assertTrue(
            all(
                row["baseline_target_feasibility"]["baseline_aligned_count"] == 13
                and row["baseline_target_feasibility"]["baseline_mismatch_count"]
                == 87
                for row in rows
            )
        )
        self.assertEqual(
            self.value["summary"]["baseline_aligned_contributor_target_count"],
            260,
        )

    def test_exact_distractor_taxonomy_and_capacity_shortfall(self):
        row = self.value["persona_feasibility_rows"][0]["distractor_feasibility"]
        self.assertEqual(
            {item["profile_class"]: item["count"] for item in row["classification_counts"]},
            package.EXPECTED_DISTRACTOR_CLASS_COUNTS_PER_PERSONA,
        )
        self.assertEqual(
            row["maximum_distinct_source_candidate_count_before_language_filter"],
            53,
        )
        self.assertEqual(row["maximum_mapping_shortfall_count"], 217)
        summary = self.value["summary"]
        self.assertEqual(
            summary[
                "maximum_distinct_distractor_source_candidate_count_before_language_filter"
            ],
            1_060,
        )
        self.assertEqual(summary["maximum_distractor_mapping_shortfall_count"], 4_340)
        self.assertEqual(
            summary["singleton_only_distractor_reference_shortfall_count"], 3_620
        )

    def test_revision_and_checkpoint_predicates_remain_unknown(self):
        for row in self.value["persona_feasibility_rows"]:
            baseline = row["baseline_target_feasibility"]
            self.assertIs(baseline["revision_join_policy_available"], False)
            self.assertEqual(baseline["revision_exact_join_proved_count"], 0)
            self.assertEqual(baseline["revision_join_unknown_count"], 100)
            self.assertEqual(
                baseline["checkpoint_selector_effective_membership_compiled_count"],
                0,
            )
            self.assertEqual(
                baseline["checkpoint_selector_effective_membership_unknown_count"],
                100,
            )
            self.assertEqual(baseline["all_condition_exact_resolution_count"], 0)

    def test_independent_snapshot_reconstruction_accepts_exact_candidate(self):
        self.assertIs(independent._validate_with_snapshot(self.value, self.snapshot), True)
        self.assertEqual(
            self.raw,
            independent.preflight_query_history_semantic_resolution_feasibility_audit(
                self.value
            ),
        )

    def test_public_validator_and_bytes_path_can_use_independent_provider(self):
        with mock.patch.object(
            independent, "_load_actual_snapshot", return_value=copy.deepcopy(self.snapshot)
        ):
            self.assertIs(
                independent.validate_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
                True,
            )
            self.assertIs(
                independent.validate_query_history_semantic_resolution_feasibility_audit_bytes(
                    self.raw
                ),
                True,
            )

    def test_authority_counts_pins_and_v2_claim_tampering_fail_closed(self):
        mutations = []
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_g0_freeze"] = True
        mutations.append(authority)
        count = copy.deepcopy(self.value)
        count["persona_feasibility_rows"][0]["baseline_target_feasibility"][
            "baseline_aligned_count"
        ] += 1
        mutations.append(count)
        pin = copy.deepcopy(self.value)
        pin["dependency_bindings"][0]["dependency_pin"]["sha256"] = "0" * 64
        mutations.append(pin)
        issued = copy.deepcopy(self.value)
        issued["completion_claims"]["query_history_target_resolution_v2_issued"] = True
        mutations.append(issued)
        revision = copy.deepcopy(self.value)
        revision["persona_feasibility_rows"][0]["baseline_target_feasibility"][
            "revision_join_policy_available"
        ] = True
        mutations.append(revision)
        methodology = copy.deepcopy(self.value)
        methodology["methodology"]["revision_owner_vocabulary_join_policy"] = (
            "available"
        )
        mutations.append(methodology)
        bool_version = copy.deepcopy(self.value)
        bool_version["artifact_schema_version"] = True
        mutations.append(bool_version)
        bool_ordinal = copy.deepcopy(self.value)
        bool_ordinal["dependency_bindings"][0]["dependency_ordinal"] = True
        mutations.append(bool_ordinal)
        for mutation in mutations:
            with self.subTest(mutation=mutations.index(mutation)):
                with self.assertRaises(
                    independent.PersonaV2SemanticResolutionFeasibilityValidationError
                ):
                    independent.preflight_query_history_semantic_resolution_feasibility_audit(
                        mutation
                    )

    def test_p01_13_of_100_is_an_authenticated_actual_baseline_sentinel(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["queries"][0]["positive_query_intents"][12][
            "project_or_case_id"
        ] = "p01-forced-mismatch"
        with self.assertRaisesRegex(
            package.PersonaV2SemanticResolutionFeasibilityError,
            "p01 baseline 13-aligned/87-mismatch",
        ):
            package._build_query_history_semantic_resolution_feasibility_audit(
                snapshot=snapshot
            )

    def test_live_join_digest_rejects_owner_drift_even_when_counts_are_unchanged(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["lifecycles"][1]["primary_match_rows"][0][
            "synthetic_unconsumed_drift"
        ] = "changed-owner-body"
        with self.assertRaisesRegex(
            independent.PersonaV2SemanticResolutionFeasibilityValidationError,
            "live join projection bindings",
        ):
            independent._validate_with_snapshot(self.value, snapshot)

    def test_noncanonical_and_duplicate_key_bytes_fail_before_provider(self):
        noncanonical = json.dumps(self.value, ensure_ascii=False).encode("utf-8")
        duplicate = b'{"artifact_kind":"a","artifact_kind":"b"}'
        with mock.patch.object(
            independent, "_load_actual_snapshot", side_effect=AssertionError("opened")
        ):
            for raw in (noncanonical, duplicate):
                with self.assertRaises(
                    independent.PersonaV2SemanticResolutionFeasibilityValidationError
                ):
                    independent.validate_query_history_semantic_resolution_feasibility_audit_bytes(
                        raw
                    )

    def test_canonical_nested_type_attacks_fail_with_dedicated_error(self):
        mutations = []
        row = copy.deepcopy(self.value)
        row["persona_feasibility_rows"][0] = [{}]
        mutations.append(row)
        baseline = copy.deepcopy(self.value)
        baseline["persona_feasibility_rows"][0][
            "baseline_target_feasibility"
        ] = [{}]
        mutations.append(baseline)
        authority = copy.deepcopy(self.value)
        authority["authority"] = []
        mutations.append(authority)
        with mock.patch.object(
            independent, "_load_actual_snapshot", side_effect=AssertionError("opened")
        ):
            for mutation in mutations:
                raw = package.candidate_bytes(mutation)
                with self.assertRaises(
                    independent.PersonaV2SemanticResolutionFeasibilityValidationError
                ):
                    independent.validate_query_history_semantic_resolution_feasibility_audit_bytes(
                        raw
                    )

    def test_candidate_and_snapshot_are_detached(self):
        snapshot = copy.deepcopy(self.snapshot)
        value = package._build_query_history_semantic_resolution_feasibility_audit(
            snapshot=snapshot
        )
        snapshot["queries"][0]["positive_query_intents"][0]["language"] = "mutated"
        self.assertEqual(value, self.value)
        first = copy.deepcopy(self.value)
        first["authority"]["authorizes_g0_freeze"] = True
        self.assertIs(self.value["authority"]["authorizes_g0_freeze"], False)

    def test_producer_independent_validator_does_not_import_producer(self):
        tree = ast.parse(Path(independent.__file__).read_text(encoding="utf-8"))
        forbidden = "persona_v2_query_history_semantic_resolution_feasibility"
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                imported.extend(alias.name for alias in node.names)
                if module:
                    imported.append(module)
                    imported.extend(
                        f"{module}.{alias.name}" for alias in node.names
                    )
        self.assertFalse(
            any(name.endswith(forbidden) for name in imported),
            imported,
        )

    def test_checked_in_golden_is_pairwise_and_modules_agree(self):
        self.assertEqual(self.package_golden, self.independent_golden)
        canonical_bytes, digest = self.package_golden
        self.assertEqual(canonical_bytes is None, digest is None)
        if canonical_bytes is not None:
            self.assertIs(type(canonical_bytes), int)
            self.assertGreater(canonical_bytes, 0)
            self.assertLessEqual(canonical_bytes, package.TARGET_ARTIFACT_BYTES)
            self.assertIs(type(digest), str)
            self.assertEqual(len(digest), 64)
            self.assertTrue(all(character in "0123456789abcdef" for character in digest))
        self.assertLessEqual(len(self.raw), package.TARGET_ARTIFACT_BYTES)
        self.assertEqual(len(hashlib.sha256(self.raw).hexdigest()), 64)

    def test_exact_configured_golden_accepts_all_public_paths(self):
        expected_bytes = len(self.raw)
        expected_sha256 = hashlib.sha256(self.raw).hexdigest()
        with mock.patch.object(
            package, "EXPECTED_CANONICAL_BYTES", expected_bytes
        ), mock.patch.object(
            package, "EXPECTED_SHA256", expected_sha256
        ), mock.patch.object(
            independent, "EXPECTED_CANONICAL_BYTES", expected_bytes
        ), mock.patch.object(
            independent, "EXPECTED_SHA256", expected_sha256
        ), mock.patch.object(
            package, "_cached_raw", return_value=self.raw
        ), mock.patch.object(
            independent,
            "_load_actual_snapshot",
            return_value=copy.deepcopy(self.snapshot),
        ):
            self.assertEqual(package.candidate_bytes(self.value), self.raw)
            self.assertEqual(
                package.build_query_history_semantic_resolution_feasibility_audit(),
                self.value,
            )
            self.assertEqual(
                independent.preflight_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
                self.raw,
            )
            self.assertIs(
                package.validate_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
                True,
            )

    def test_partial_or_drifting_goldens_fail_closed_on_every_public_path(self):
        expected_sha256 = hashlib.sha256(self.raw).hexdigest()

        for byte_count, digest in ((len(self.raw), None), (None, expected_sha256)):
            with self.subTest(owner="producer", bytes=byte_count, sha256=digest):
                with mock.patch.object(
                    package, "EXPECTED_CANONICAL_BYTES", byte_count
                ), mock.patch.object(package, "EXPECTED_SHA256", digest):
                    with self.assertRaises(
                        package.PersonaV2SemanticResolutionFeasibilityError
                    ):
                        package.candidate_bytes(self.value)
            with self.subTest(owner="validator", bytes=byte_count, sha256=digest):
                with mock.patch.object(
                    independent, "EXPECTED_CANONICAL_BYTES", byte_count
                ), mock.patch.object(independent, "EXPECTED_SHA256", digest):
                    with self.assertRaises(
                        independent.PersonaV2SemanticResolutionFeasibilityValidationError
                    ):
                        independent.preflight_query_history_semantic_resolution_feasibility_audit(
                            self.value
                        )

        with mock.patch.object(
            package, "EXPECTED_CANONICAL_BYTES", len(self.raw) + 1
        ), mock.patch.object(
            package, "EXPECTED_SHA256", expected_sha256
        ), mock.patch.object(
            package, "_cached_raw", return_value=self.raw
        ):
            for operation in (
                lambda: package.candidate_bytes(self.value),
                package.build_query_history_semantic_resolution_feasibility_audit,
                lambda: package.validate_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
            ):
                with self.subTest(owner="producer", operation=operation):
                    with self.assertRaises(
                        package.PersonaV2SemanticResolutionFeasibilityError
                    ):
                        operation()

        with mock.patch.object(
            independent, "EXPECTED_CANONICAL_BYTES", len(self.raw)
        ), mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ), mock.patch.object(
            independent,
            "_load_actual_snapshot",
            side_effect=AssertionError("heavy provider opened before golden rejection"),
        ):
            for operation in (
                lambda: independent.preflight_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
                lambda: independent.validate_query_history_semantic_resolution_feasibility_audit(
                    self.value
                ),
                lambda: independent.validate_query_history_semantic_resolution_feasibility_audit_bytes(
                    self.raw
                ),
            ):
                with self.subTest(owner="validator", operation=operation):
                    with self.assertRaises(
                        independent.PersonaV2SemanticResolutionFeasibilityValidationError
                    ):
                        operation()


@unittest.skipUnless(
    os.environ.get(
        "KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_FULL"
    )
    == "1",
    "set KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_FULL=1 "
    "for the long all-persona build and independent validation gate",
)
class SemanticResolutionFeasibilityLongFullTest(unittest.TestCase):
    def test_actual_all_persona_build_and_independent_validation(self):
        import resource

        self.assertEqual(
            (package.EXPECTED_CANONICAL_BYTES, package.EXPECTED_SHA256),
            (independent.EXPECTED_CANONICAL_BYTES, independent.EXPECTED_SHA256),
        )
        started = time.monotonic()
        value = package.build_query_history_semantic_resolution_feasibility_audit()
        raw = package.candidate_bytes(value)
        self.assertIs(
            independent.validate_query_history_semantic_resolution_feasibility_audit(
                value
            ),
            True,
        )
        elapsed = time.monotonic() - started
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        digest = hashlib.sha256(raw).hexdigest()
        summary = value["summary"]
        measurement = {
            "abstract_distractor_reference_count": summary[
                "abstract_distractor_reference_count"
            ],
            "canonical_bytes": len(raw),
            "contributor_target_count": summary["contributor_target_count"],
            "elapsed_seconds": round(elapsed, 3),
            "live_join_binding_count": len(value["live_join_bindings"]),
            "maximum_rss_bytes": rss,
            "persona_count": len(value["persona_feasibility_rows"]),
            "sha256": digest,
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(measurement["persona_count"], 20)
        self.assertEqual(measurement["contributor_target_count"], 2_000)
        self.assertEqual(
            measurement["abstract_distractor_reference_count"], 5_400
        )
        self.assertEqual(measurement["live_join_binding_count"], 4)
        self.assertLessEqual(elapsed, 7_200)
        self.assertLessEqual(rss, 1 * 2**30)
        self.assertLessEqual(len(raw), package.TARGET_ARTIFACT_BYTES)
        if package.EXPECTED_CANONICAL_BYTES is not None:
            self.assertEqual(len(raw), package.EXPECTED_CANONICAL_BYTES)
            self.assertEqual(digest, package.EXPECTED_SHA256)


@unittest.skipUnless(
    os.environ.get(
        "KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_COLD"
    )
    == "1",
    "set KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_COLD=1 "
    "for two isolated hash-seed gates",
)
class SemanticResolutionFeasibilityLongColdHashSeedTest(unittest.TestCase):
    def test_two_isolated_hash_seeds_are_byte_stable(self):
        script = r'''
import hashlib
import json
import os
import resource
import sys
import time
from eval import persona_v2_query_history_semantic_resolution_feasibility as package
from eval import persona_v2_query_history_semantic_resolution_feasibility_validator as independent

if (
    package.EXPECTED_CANONICAL_BYTES,
    package.EXPECTED_SHA256,
) != (
    independent.EXPECTED_CANONICAL_BYTES,
    independent.EXPECTED_SHA256,
):
    raise RuntimeError("producer and validator golden configurations differ")
started = time.monotonic()
value = package.build_query_history_semantic_resolution_feasibility_audit()
raw = package.candidate_bytes(value)
if not independent.validate_query_history_semantic_resolution_feasibility_audit(value):
    raise RuntimeError("producer-independent all-persona validation returned false")
elapsed = time.monotonic() - started
summary = value["summary"]
persona_count = len(value["persona_feasibility_rows"])
live_join_binding_count = len(value["live_join_bindings"])
if persona_count != 20:
    raise RuntimeError("actual persona count drifted")
if summary["contributor_target_count"] != 2000:
    raise RuntimeError("actual contributor target count drifted")
if summary["abstract_distractor_reference_count"] != 5400:
    raise RuntimeError("actual distractor reference count drifted")
if live_join_binding_count != 4:
    raise RuntimeError("actual live join binding count drifted")
digest = hashlib.sha256(raw).hexdigest()
if package.EXPECTED_CANONICAL_BYTES is not None and (
    len(raw) != package.EXPECTED_CANONICAL_BYTES
    or digest != package.EXPECTED_SHA256
):
    raise RuntimeError("actual candidate differs from the configured golden")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "abstract_distractor_reference_count": summary[
        "abstract_distractor_reference_count"
    ],
    "canonical_bytes": len(raw),
    "contributor_target_count": summary["contributor_target_count"],
    "elapsed_seconds": elapsed,
    "live_join_binding_count": live_join_binding_count,
    "maximum_rss_bytes": rss,
    "persona_count": persona_count,
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "sha256": digest,
}, sort_keys=True))
'''
        root = str(Path(__file__).resolve().parents[1])
        measurements = []
        for seed in ("0", "1"):
            environment = os.environ.copy()
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            environment.pop(
                "KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_COLD",
                None,
            )
            environment.pop(
                "KCS_RUN_QUERY_HISTORY_SEMANTIC_RESOLUTION_FEASIBILITY_FULL",
                None,
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=7_200,
            )
            measurement = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["persona_count"], 20)
            self.assertEqual(measurement["contributor_target_count"], 2_000)
            self.assertEqual(
                measurement["abstract_distractor_reference_count"], 5_400
            )
            self.assertEqual(measurement["live_join_binding_count"], 4)
            self.assertLessEqual(measurement["elapsed_seconds"], 7_200)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["canonical_bytes"], package.TARGET_ARTIFACT_BYTES
            )
            measurements.append(measurement)
        print(
            json.dumps(
                {"semantic_resolution_feasibility_cold": measurements},
                sort_keys=True,
            )
        )
        self.assertEqual(
            {
                "canonical_bytes": measurements[0]["canonical_bytes"],
                "sha256": measurements[0]["sha256"],
            },
            {
                "canonical_bytes": measurements[1]["canonical_bytes"],
                "sha256": measurements[1]["sha256"],
            },
        )


if __name__ == "__main__":
    unittest.main()
