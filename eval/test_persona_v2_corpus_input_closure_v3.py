import ast
from collections import Counter
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

from eval import persona_v2_corpus_input_closure_v3 as package
from eval import persona_v2_corpus_input_closure_v3_validator as independent


class _ExactMockTrustSource:
    """Fast orchestration double; it is never accepted by the public API."""

    def __init__(self):
        self.opened = []
        self.validated = []
        self.closed = 0

    def open(self, bindings):
        self.opened = [row["dependency_id"] for row in bindings]
        return True

    def validate(self, binding):
        self.validated.append(binding["dependency_id"])
        return True

    def close(self):
        self.closed += 1
        return True


class CorpusInputClosureV3FastTests(unittest.TestCase):
    def setUp(self):
        self.value = package.build_corpus_input_closure_v3()

    def test_exact_request_only_non_authorizing_contract(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(
            [row["dependency_id"] for row in self.value["dependency_bindings"]],
            list(package.DEPENDENCY_ORDER),
        )
        self.assertEqual(len(self.value["dependency_bindings"]), 4)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        self.assertIs(self.value["g0_contract_frozen"], False)
        self.assertIs(
            self.value["completion_claims"]["corpus_input_closure_complete"],
            False,
        )
        review_gate = self.value["review_gate"]
        self.assertEqual(review_gate["required_review_request_count"], 7)
        self.assertEqual(review_gate["required_positive_receipt_count"], 7)
        self.assertEqual(review_gate["positive_review_receipt_bindings"], [])
        self.assertEqual(review_gate["positive_review_receipt_count"], 0)
        self.assertIs(review_gate["route_human_positive_receipt_bound"], False)
        self.assertEqual(
            review_gate["route_human_required_reviewer_kind"],
            "independent-human",
        )

    def test_exact_active_bootstrap_gate(self):
        gate = self.value["blocker_gate"]
        self.assertEqual(gate["source_count"], 3)
        self.assertEqual(gate["claim_count"], 36)
        self.assertEqual(gate["blocker_claim_count"], 21)
        self.assertEqual(gate["false_completion_claim_count"], 15)
        self.assertEqual(gate["active_g0_unresolved_count"], 36)
        self.assertIs(gate["closure_eligible"], False)
        self.assertIs(gate["g0_eligible"], False)
        self.assertIs(gate["historical_blocker_universe_complete"], False)
        self.assertIs(gate["source_registry_complete"], False)

    def test_exact_four_literal_pins(self):
        for row in self.value["dependency_bindings"]:
            expected = package.DEPENDENCY_SPECS[row["dependency_id"]]
            self.assertEqual(row["dependency_pin"], expected["pin"])
            self.assertEqual(row["dependency_role"], expected["dependency_role"])
            self.assertEqual(row["input_state"], expected["input_state"])
        namespace_pin = self.value["dependency_bindings"][0]["dependency_pin"]
        self.assertEqual(namespace_pin["canonical_bytes"], 161_665)
        self.assertEqual(
            namespace_pin["sha256"],
            "a8bc67e182ff57b64ae6df0f97bd5be31faf6e5f7b7cfbd0bc3f1ba7bc5cc509",
        )

    def test_body_is_compact_pin_only_and_has_no_downstream_fields(self):
        raw = package.corpus_input_closure_v3_candidate_bytes(self.value)
        self.assertLessEqual(len(raw), package.TARGET_MANIFEST_BYTES)
        lowered = raw.lower()
        for token in (b"query", b"oracle", b"evaluation"):
            self.assertNotIn(token, lowered)
        self.assertIs(
            self.value["canonical_limits"]["external_dependency_bodies_embedded"],
            False,
        )
        self.assertIs(
            self.value["canonical_limits"]["external_projection_bodies_embedded"],
            False,
        )

    def test_frozen_golden_matches_both_implementations_and_exact_body(self):
        expected = (
            7_590,
            "9b1fc39877ff108612159248f356fb29981de83091d2fe14c88f796b42a0276d",
        )
        self.assertEqual(
            (package.EXPECTED_CLOSURE_CANONICAL_BYTES, package.EXPECTED_CLOSURE_SHA256),
            expected,
        )
        self.assertEqual(
            (
                independent.EXPECTED_CLOSURE_CANONICAL_BYTES,
                independent.EXPECTED_CLOSURE_SHA256,
            ),
            expected,
        )
        raw = package.corpus_input_closure_v3_candidate_bytes(self.value)
        self.assertEqual(raw, independent._preflight_candidate(self.value))
        self.assertEqual((len(raw), hashlib.sha256(raw).hexdigest()), expected)

    def test_fast_mock_trust_source_exercises_exact_order(self):
        trust = _ExactMockTrustSource()
        self.assertIs(independent._validate_with_trust_source(self.value, trust), True)
        self.assertEqual(trust.opened, list(package.DEPENDENCY_ORDER))
        self.assertEqual(trust.validated, list(package.DEPENDENCY_ORDER))
        self.assertEqual(trust.closed, 1)

    def test_fast_trust_source_cannot_bypass_exact_candidate(self):
        value = copy.deepcopy(self.value)
        value["review_gate"]["positive_review_receipt_count"] = 1
        trust = _ExactMockTrustSource()
        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent._validate_with_trust_source(value, trust)
        self.assertEqual(trust.opened, [])

    def test_trust_source_exact_true_and_postflight_are_required(self):
        class BadOpen(_ExactMockTrustSource):
            def open(self, bindings):
                super().open(bindings)
                return 1

        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent._validate_with_trust_source(self.value, BadOpen())

        class BadClose(_ExactMockTrustSource):
            def close(self):
                return False

        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent._validate_with_trust_source(self.value, BadClose())

        value = copy.deepcopy(self.value)

        class MutatingTrust(_ExactMockTrustSource):
            def validate(self, binding):
                value["authority"]["authorizes_g0_freeze"] = True
                return super().validate(binding)

        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent._validate_with_trust_source(value, MutatingTrust())

        class FailingValidation(_ExactMockTrustSource):
            def validate(self, binding):
                super().validate(binding)
                raise independent.PersonaV2CorpusInputClosureV3ValidationError(
                    "synthetic semantic failure"
                )

        trust = FailingValidation()
        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent._validate_with_trust_source(self.value, trust)
        self.assertEqual(trust.closed, 1)

        failing_value = copy.deepcopy(self.value)

        class MutatingFailure(_ExactMockTrustSource):
            def validate(self, binding):
                super().validate(binding)
                failing_value["authority"]["authorizes_g0_freeze"] = True
                raise independent.PersonaV2CorpusInputClosureV3ValidationError(
                    "synthetic semantic failure"
                )

        trust = MutatingFailure()
        with self.assertRaisesRegex(
            independent.PersonaV2CorpusInputClosureV3ValidationError,
            "closure authority drifted",
        ):
            independent._validate_with_trust_source(failing_value, trust)
        self.assertEqual(trust.closed, 1)

    def test_authority_receipt_and_dependency_tampering_fail_closed(self):
        mutations = []
        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_solver_execution"] = True
        mutations.append(authority)
        receipt = copy.deepcopy(self.value)
        receipt["review_gate"]["positive_review_receipt_bindings"] = [
            {"request_id": "forged"}
        ]
        mutations.append(receipt)
        reordered = copy.deepcopy(self.value)
        reordered["dependency_bindings"][0], reordered["dependency_bindings"][1] = (
            reordered["dependency_bindings"][1],
            reordered["dependency_bindings"][0],
        )
        mutations.append(reordered)
        digest = copy.deepcopy(self.value)
        digest["dependency_bindings"][2]["dependency_pin"]["sha256"] = "0" * 64
        mutations.append(digest)
        extra = copy.deepcopy(self.value)
        extra["evaluation_input"] = {}
        mutations.append(extra)
        bool_ordinal = copy.deepcopy(self.value)
        bool_ordinal["dependency_bindings"][0]["dependency_ordinal"] = True
        mutations.append(bool_ordinal)
        bool_zero_count = copy.deepcopy(self.value)
        bool_zero_count["summary"]["authority_grant_count"] = False
        mutations.append(bool_zero_count)
        for value in mutations:
            with self.subTest(value=value):
                with self.assertRaises(package.PersonaV2CorpusInputClosureV3Error):
                    package.corpus_input_closure_v3_candidate_bytes(value)

    def test_resource_bombs_fail_before_producer_canonicalizer(self):
        huge = copy.deepcopy(self.value)
        huge["remaining_blockers"][0] = "x" * (4 * 2**10 + 1)
        shared = ["x"]
        for _ in range(15):
            shared = [shared, shared]
        expanded = copy.deepcopy(self.value)
        expanded["review_gate"]["positive_review_receipt_bindings"] = shared
        recursive = copy.deepcopy(self.value)
        recursive["review_gate"]["positive_review_receipt_bindings"].append(
            recursive["review_gate"]["positive_review_receipt_bindings"]
        )
        for value in (huge, expanded, recursive):
            with self.subTest(kind=type(value)):
                with mock.patch.object(
                    package,
                    "_canonical_unchecked",
                    side_effect=AssertionError("canonicalizer must not run"),
                ) as canonicalizer:
                    with self.assertRaises(package.PersonaV2CorpusInputClosureV3Error):
                        package.corpus_input_closure_v3_candidate_bytes(value)
                    canonicalizer.assert_not_called()

    def test_top_level_container_cap_precedes_key_set_copy(self):
        oversized = copy.deepcopy(self.value)
        for index in range(independent.MAX_CONTAINER_ITEMS):
            oversized[f"extra-{index}"] = False
        with mock.patch.object(
            independent,
            "_exact_dict",
            side_effect=AssertionError("top-level keys must not be copied"),
        ) as exact_dict:
            with self.assertRaises(
                independent.PersonaV2CorpusInputClosureV3ValidationError
            ):
                independent._preflight_candidate(oversized)
            exact_dict.assert_not_called()

    def test_dependency_cap_precedes_hash_and_parse(self):
        binding = self.value["dependency_bindings"][2]
        hard_cap = independent.DEPENDENCY_SPECS[binding["dependency_id"]]["hard_cap"]
        with mock.patch.object(
            independent.hashlib,
            "sha256",
            side_effect=AssertionError("hash must not run"),
        ) as digest:
            with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
                independent._authenticate_dependency_body(
                    b"x" * (hard_cap + 1), binding
                )
            digest.assert_not_called()

    def test_duplicate_key_bytes_fail_before_callbacks(self):
        raw = package.corpus_input_closure_v3_candidate_bytes(self.value)
        duplicate = raw[:-1] + b',"artifact_kind":"duplicate"}'
        provider = mock.Mock(side_effect=AssertionError("provider must not run"))
        with self.assertRaises(independent.PersonaV2CorpusInputClosureV3ValidationError):
            independent.validate_corpus_input_closure_v3_bytes(
                duplicate,
                dependency_body_provider=provider,
                projection_body_provider=provider,
            )
        provider.assert_not_called()

    def test_builder_cache_is_immutable_and_returns_detached_values(self):
        first = package.build_corpus_input_closure_v3()
        first["authority"]["authorizes_g0_freeze"] = True
        first["dependency_bindings"].clear()
        second = package.build_corpus_input_closure_v3()
        self.assertTrue(all(flag is False for flag in second["authority"].values()))
        self.assertEqual(len(second["dependency_bindings"]), 4)

    def test_dependency_snapshot_builds_each_body_once_and_shares_inventory(self):
        package._canonical_dependency_snapshot.cache_clear()
        self.addCleanup(package._canonical_dependency_snapshot.cache_clear)
        inventory_value = {"sentinel": "complete-inventory"}
        namespace_value = {"sentinel": "namespace"}
        ledger_value = {"sentinel": "ledger"}
        snapshot = (b"namespace", b"complete", b"review", b"ledger")
        with (
            mock.patch.object(
                package.complete,
                "build_semantic_projection_complete_inventory",
                return_value=inventory_value,
            ) as complete_builder,
            mock.patch.object(
                package.complete,
                "canonical_json_bytes",
                return_value=snapshot[1],
            ) as complete_canonicalizer,
            mock.patch.object(
                package.namespace,
                "build_corpus_semantic_namespace_v3",
                return_value=namespace_value,
            ) as namespace_builder,
            mock.patch.object(
                package.namespace,
                "corpus_semantic_namespace_v3_candidate_bytes",
                return_value=snapshot[0],
            ) as namespace_canonicalizer,
            mock.patch.object(
                package.review,
                "review_request_catalog_bytes",
                return_value=snapshot[2],
            ) as review_builder,
            mock.patch.object(
                package.ledger,
                "build_g0_blocker_resolution_ledger_bootstrap_candidate",
                return_value=ledger_value,
            ) as ledger_builder,
            mock.patch.object(
                package.ledger,
                "canonical_bootstrap_candidate_json_bytes",
                return_value=snapshot[3],
            ) as ledger_canonicalizer,
            mock.patch.object(
                package,
                "_authenticate_cached_dependency_body",
                side_effect=lambda _dependency_id, raw: raw,
            ) as authenticate,
        ):
            first = package._canonical_dependency_snapshot()
            second = package._canonical_dependency_snapshot()
        self.assertIs(first, second)
        self.assertEqual(first, snapshot)
        self.assertTrue(all(type(raw) is bytes for raw in first))
        complete_builder.assert_called_once_with()
        complete_canonicalizer.assert_called_once_with(inventory_value)
        namespace_builder.assert_called_once_with(
            complete_inventory=inventory_value
        )
        namespace_canonicalizer.assert_called_once_with(namespace_value)
        review_builder.assert_called_once_with()
        ledger_builder.assert_called_once_with()
        ledger_canonicalizer.assert_called_once_with(ledger_value)
        self.assertEqual(authenticate.call_count, 4)

    def test_eight_provider_reads_use_one_snapshot_and_recheck_every_body(self):
        package._canonical_dependency_snapshot.cache_clear()
        self.addCleanup(package._canonical_dependency_snapshot.cache_clear)
        snapshot = tuple(
            f"body:{dependency_id}".encode("ascii")
            for dependency_id in package.DEPENDENCY_ORDER
        )
        with (
            mock.patch.object(
                package,
                "_build_canonical_dependency_snapshot",
                return_value=snapshot,
            ) as builder,
            mock.patch.object(
                package,
                "_require_dependency_constant_alignment",
            ) as alignment,
            mock.patch.object(
                package,
                "_authenticate_cached_dependency_body",
                side_effect=lambda _dependency_id, raw: raw,
            ) as authenticate,
        ):
            supplied = [
                package._current_dependency_body(dependency_id)
                for _phase in ("opening", "closing")
                for dependency_id in package.DEPENDENCY_ORDER
            ]
        self.assertEqual(supplied, list(snapshot) * 2)
        builder.assert_called_once_with()
        self.assertEqual(alignment.call_count, 8)
        self.assertEqual(authenticate.call_count, 8)

    def test_every_provider_read_rejects_constant_or_cached_body_drift(self):
        dependency_id = package.DEPENDENCY_ORDER[0]
        with (
            mock.patch.object(
                package.namespace,
                "EXPECTED_NAMESPACE_SHA256",
                "0" * 64,
            ),
            mock.patch.object(
                package,
                "_canonical_dependency_snapshot",
                side_effect=AssertionError("snapshot must not be read"),
            ) as snapshot,
        ):
            with self.assertRaisesRegex(
                package.PersonaV2CorpusInputClosureV3Error,
                "current dependency constants drifted",
            ):
                package._current_dependency_body(dependency_id)
            snapshot.assert_not_called()

        pinned_length = package.DEPENDENCY_SPECS[dependency_id]["pin"][
            "canonical_bytes"
        ]
        for bad_raw in (b"short", b"x" * pinned_length):
            bad_snapshot = (bad_raw, b"complete", b"review", b"ledger")
            with self.subTest(length=len(bad_raw)), mock.patch.object(
                package,
                "_canonical_dependency_snapshot",
                return_value=bad_snapshot,
            ):
                with self.assertRaisesRegex(
                    package.PersonaV2CorpusInputClosureV3Error,
                    "cached dependency body drifted",
                ):
                    package._current_dependency_body(dependency_id)

    def test_full_trust_source_calls_each_validator_once_and_reads_twice(self):
        direct_bodies = {
            dependency_id: f"body:{dependency_id}".encode("ascii")
            for dependency_id in package.DEPENDENCY_ORDER
        }
        provider_counts = Counter()

        def dependency_provider(dependency_id):
            provider_counts[dependency_id] += 1
            return direct_bodies[dependency_id]

        inventory_value = {
            "summary": {
                "derivation_receipt_count": 253,
                "cumulative_external_projection_bytes": (
                    independent.EXACT_CUMULATIVE_EXTERNAL_PROJECTION_BYTES
                ),
            }
        }
        inventory_pin = copy.deepcopy(
            package.DEPENDENCY_SPECS[
                "complete-semantic-projection-inventory-v2"
            ]["pin"]
        )
        review_value = {
            "review_requests": [
                {
                    "positive_receipt_bound": False,
                    "request_id": "persona-v2-review-request-route-human",
                    "required_reviewer_kind": "independent-human",
                    "review_class_id": "route-human",
                },
                {
                    "review_class_id": "semantic-projection-inventory",
                    "subject_pins": [inventory_pin],
                },
                *[
                    {"review_class_id": f"synthetic-{index}"}
                    for index in range(5)
                ],
            ],
            "summary": {"positive_receipt_count": 0},
        }
        ledger_value = {
            "completion_claims": {
                "all_active_g0_blockers_resolved": False,
                "closure_eligible": False,
                "g0_eligible": False,
            },
            "registry_scope": {
                "historical_source_universe_complete": False,
                "source_registry_complete": False,
            },
            "summary": {
                "active_g0_unresolved_count": 36,
                "blocker_claim_count": 21,
                "claim_count": 36,
                "false_completion_claim_count": 15,
                "source_count": 3,
                "status_counts": {
                    "active-g0": 36,
                    "deferred-post-g0": 0,
                    "historical-local-negative": 0,
                    "resolved-by-downstream-pin": 0,
                },
            },
        }
        values = {
            "corpus-semantic-namespace-v3": {"sentinel": "namespace"},
            "complete-semantic-projection-inventory-v2": inventory_value,
            "review-request-catalog-v1": review_value,
            "g0-blocker-resolution-ledger-bootstrap-v2": ledger_value,
        }
        projection_provider = mock.Mock(name="all_253_projection_provider")
        with (
            mock.patch.object(
                independent,
                "_authenticate_dependency_body",
                side_effect=lambda _raw, binding: values[
                    binding["dependency_id"]
                ],
            ),
            mock.patch.object(
                independent.namespace_validator,
                "validate_corpus_semantic_namespace_v3",
                return_value=True,
            ) as namespace_validator,
            mock.patch.object(
                independent.review_validator,
                "validate_review_request_catalog",
                return_value=True,
            ) as review_validator,
            mock.patch.object(
                independent.ledger_validator,
                "load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate",
                return_value=ledger_value,
            ) as ledger_validator,
        ):
            self.assertIs(
                independent.validate_corpus_input_closure_v3(
                    self.value,
                    dependency_body_provider=dependency_provider,
                    projection_body_provider=projection_provider,
                ),
                True,
            )
        self.assertEqual(
            provider_counts,
            Counter({dependency_id: 2 for dependency_id in package.DEPENDENCY_ORDER}),
        )
        namespace_validator.assert_called_once()
        namespace_call = namespace_validator.call_args
        self.assertIs(
            namespace_call.kwargs["complete_inventory"], inventory_value
        )
        self.assertIs(
            namespace_call.kwargs["projection_body_provider"],
            projection_provider,
        )
        review_validator.assert_called_once_with(review_value)
        ledger_validator.assert_called_once_with(
            direct_bodies["g0-blocker-resolution-ledger-bootstrap-v2"]
        )

    def test_dependency_provider_output_mutation_fails_closing_read(self):
        calls = Counter()
        direct_bodies = {
            dependency_id: f"body:{dependency_id}".encode("ascii")
            for dependency_id in package.DEPENDENCY_ORDER
        }

        def mutating_provider(dependency_id):
            calls[dependency_id] += 1
            raw = direct_bodies[dependency_id]
            if dependency_id == "review-request-catalog-v1" and calls[dependency_id] == 2:
                return raw + b":mutated"
            return raw

        trust_source = independent._FullTrustSource(
            mutating_provider,
            mock.Mock(name="unused_projection_provider"),
        )
        with mock.patch.object(
            independent,
            "_authenticate_dependency_body",
            return_value={},
        ):
            self.assertIs(
                trust_source.open(copy.deepcopy(self.value["dependency_bindings"])),
                True,
            )
            with self.assertRaisesRegex(
                independent.PersonaV2CorpusInputClosureV3ValidationError,
                "changed during validation",
            ):
                trust_source.close()

    def test_public_validation_wires_only_full_trust_sources(self):
        with mock.patch.object(
            independent,
            "validate_corpus_input_closure_v3",
            return_value=True,
        ) as validator:
            self.assertIs(package.validate_corpus_input_closure_v3(self.value), True)
        kwargs = validator.call_args.kwargs
        self.assertTrue(callable(kwargs["dependency_body_provider"]))
        self.assertTrue(callable(kwargs["projection_body_provider"]))

    def test_accepted_hash_invokes_full_validator_exactly_once(self):
        expected = hashlib.sha256(
            package.corpus_input_closure_v3_candidate_bytes(self.value)
        ).hexdigest()
        with mock.patch.object(
            independent,
            "validate_corpus_input_closure_v3",
            return_value=True,
        ) as validator:
            self.assertEqual(
                package.accepted_corpus_input_closure_v3_sha256(self.value),
                expected,
            )
        validator.assert_called_once()

    def test_authoritative_require_helper_always_fails(self):
        with self.assertRaises(package.PersonaV2CorpusInputClosureV3Error):
            package.require_authoritative_corpus_input_closure_v3()

    def test_independent_validator_does_not_import_producer(self):
        tree = ast.parse(Path(independent.__file__).read_text(encoding="utf-8"))
        forbidden = "persona_v2_corpus_input_closure_v3"
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


@unittest.skipUnless(
    os.environ.get("KIO_RUN_CORPUS_INPUT_CLOSURE_V3_FULL") == "1",
    "set KIO_RUN_CORPUS_INPUT_CLOSURE_V3_FULL=1 for the long all-253 gate",
)
class CorpusInputClosureV3LongFullTest(unittest.TestCase):
    def test_full_current_dependency_and_all_253_validation(self):
        import resource

        started = time.monotonic()
        value = package.build_corpus_input_closure_v3()
        direct_calls = Counter()
        projection_calls = Counter()
        original_direct_provider = package._current_dependency_body
        original_projection_provider = package.complete.projection_body_provider

        def counted_direct_provider(dependency_id):
            direct_calls[dependency_id] += 1
            return original_direct_provider(dependency_id)

        def counted_projection_provider(receipt):
            projection_calls[receipt["receipt_id"]] += 1
            return original_projection_provider(receipt)

        with mock.patch.object(
            package,
            "_current_dependency_body",
            side_effect=counted_direct_provider,
        ), mock.patch.object(
            package.complete,
            "projection_body_provider",
            side_effect=counted_projection_provider,
        ):
            digest = package.accepted_corpus_input_closure_v3_sha256(value)
        raw = package.corpus_input_closure_v3_candidate_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        measurement = {
            "canonical_bytes": len(raw),
            "direct_dependency_call_count": sum(direct_calls.values()),
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "maximum_rss_bytes": rss,
            "projection_body_call_count": sum(projection_calls.values()),
            "sha256": digest,
            "unique_projection_receipt_count": len(projection_calls),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(
            direct_calls,
            Counter({dependency_id: 2 for dependency_id in package.DEPENDENCY_ORDER}),
        )
        self.assertEqual(sum(projection_calls.values()), 506)
        self.assertEqual(len(projection_calls), 253)
        self.assertTrue(all(count == 2 for count in projection_calls.values()))
        self.assertLessEqual(measurement["elapsed_seconds"], 7_200)
        self.assertLessEqual(rss, 1 * 2**30)
        self.assertEqual(digest, hashlib.sha256(raw).hexdigest())
        if package.EXPECTED_CLOSURE_CANONICAL_BYTES is not None:
            self.assertEqual(len(raw), package.EXPECTED_CLOSURE_CANONICAL_BYTES)
        if package.EXPECTED_CLOSURE_SHA256 is not None:
            self.assertEqual(digest, package.EXPECTED_CLOSURE_SHA256)


@unittest.skipUnless(
    os.environ.get("KIO_RUN_CORPUS_INPUT_CLOSURE_V3_COLD") == "1",
    "set KIO_RUN_CORPUS_INPUT_CLOSURE_V3_COLD=1 for two isolated cold gates",
)
class CorpusInputClosureV3LongColdHashSeedTest(unittest.TestCase):
    def test_two_isolated_hash_seeds_are_byte_stable(self):
        script = r'''
from collections import Counter
import hashlib
import json
import os
import resource
import sys
import time
from unittest import mock
from eval import persona_v2_corpus_input_closure_v3 as package

started = time.monotonic()
value = package.build_corpus_input_closure_v3()
raw = package.corpus_input_closure_v3_candidate_bytes(value)
direct_calls = Counter()
projection_calls = Counter()
original_direct_provider = package._current_dependency_body
original_projection_provider = package.complete.projection_body_provider

def counted_direct_provider(dependency_id):
    direct_calls[dependency_id] += 1
    return original_direct_provider(dependency_id)

def counted_projection_provider(receipt):
    projection_calls[receipt["receipt_id"]] += 1
    return original_projection_provider(receipt)

with mock.patch.object(
    package,
    "_current_dependency_body",
    side_effect=counted_direct_provider,
), mock.patch.object(
    package.complete,
    "projection_body_provider",
    side_effect=counted_projection_provider,
):
    accepted = package.accepted_corpus_input_closure_v3_sha256(value)
raw_sha256 = hashlib.sha256(raw).hexdigest()
if accepted != raw_sha256:
    raise RuntimeError("accepted digest differs from the exact candidate bytes")
if direct_calls != Counter({key: 2 for key in package.DEPENDENCY_ORDER}):
    raise RuntimeError("direct dependency opening/closing cardinality drifted")
if len(projection_calls) != 253 or sum(projection_calls.values()) != 506:
    raise RuntimeError("all-253 two-replay call cardinality drifted")
if any(count != 2 for count in projection_calls.values()):
    raise RuntimeError("one or more projection bodies were not replayed twice")
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "canonical_bytes": len(raw),
    "direct_dependency_call_count": sum(direct_calls.values()),
    "elapsed_seconds": time.monotonic() - started,
    "maximum_rss_bytes": rss,
    "projection_body_call_count": sum(projection_calls.values()),
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "raw_sha256": raw_sha256,
    "sha256": accepted,
    "unique_projection_receipt_count": len(projection_calls),
}, sort_keys=True))
'''
        measurements = []
        root = str(Path(__file__).resolve().parents[1])
        for seed in ("0", "1"):
            env = os.environ.copy()
            env.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            env.pop("KIO_RUN_CORPUS_INPUT_CLOSURE_V3_COLD", None)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=root,
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=14_400,
            )
            measurement = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["direct_dependency_call_count"], 8)
            self.assertEqual(measurement["projection_body_call_count"], 506)
            self.assertEqual(measurement["unique_projection_receipt_count"], 253)
            self.assertEqual(measurement["sha256"], measurement["raw_sha256"])
            self.assertLessEqual(measurement["elapsed_seconds"], 14_400)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["canonical_bytes"], package.TARGET_MANIFEST_BYTES
            )
            measurements.append(measurement)
        print(
            json.dumps(
                {"corpus_input_closure_v3_cold_measurements": measurements},
                sort_keys=True,
            )
        )
        stable_fields = ("canonical_bytes", "sha256")
        self.assertEqual(
            {field: measurements[0][field] for field in stable_fields},
            {field: measurements[1][field] for field in stable_fields},
        )
        if package.EXPECTED_CLOSURE_CANONICAL_BYTES is not None:
            self.assertEqual(
                measurements[0]["canonical_bytes"],
                package.EXPECTED_CLOSURE_CANONICAL_BYTES,
            )
        if package.EXPECTED_CLOSURE_SHA256 is not None:
            self.assertEqual(
                measurements[0]["sha256"], package.EXPECTED_CLOSURE_SHA256
            )


if __name__ == "__main__":
    unittest.main()
