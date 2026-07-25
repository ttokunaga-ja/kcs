"""Focused regressions for the non-authorizing blocker-ledger bootstrap."""

from __future__ import annotations

import copy
import hashlib
import unittest
from unittest import mock

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_g0_blocker_resolution_ledger as producer
    from . import persona_v2_g0_blocker_resolution_ledger_validator as validator
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_g0_blocker_resolution_ledger as producer
    import persona_v2_g0_blocker_resolution_ledger_validator as validator


class PersonaV2G0BlockerResolutionLedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = producer.build_g0_blocker_resolution_ledger_bootstrap_candidate()
        cls.raw = producer.canonical_bootstrap_candidate_json_bytes(cls.candidate)

    def fresh(self):
        return copy.deepcopy(self.candidate)

    def resolver_pin(self, source_id):
        registry = {
            item["source_id"]: item
            for item in self.candidate["source_artifact_registry"]
        }
        item = registry[source_id]
        return {
            "artifact_kind": item["artifact_kind"],
            "artifact_schema": item["artifact_schema"],
            "artifact_schema_version": item["artifact_schema_version"],
            "body_framing": item["body_framing"],
            "canonical_bytes": item["canonical_bytes"],
            "sha256": item["sha256"],
        }

    def test_exact_bootstrap_candidate_is_valid_and_non_authorizing(self):
        self.assertTrue(
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                self.candidate
            )
        )
        loaded = validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(
            self.raw
        )
        self.assertEqual(loaded["registry_profile_id"], "bootstrap-three-source-v1")
        self.assertEqual(loaded["summary"]["source_count"], 3)
        self.assertEqual(loaded["summary"]["claim_count"], 36)
        self.assertEqual(loaded["summary"]["blocker_claim_count"], 21)
        self.assertEqual(loaded["summary"]["false_completion_claim_count"], 15)
        self.assertEqual(loaded["summary"]["active_g0_unresolved_count"], 36)
        self.assertFalse(loaded["summary"]["active_g0_count_zero"])
        self.assertFalse(loaded["completion_claims"]["closure_eligible"])
        self.assertFalse(loaded["completion_claims"]["source_registry_complete"])
        self.assertFalse(any(loaded["authority"].values()))
        self.assertEqual(
            {entry["status"] for entry in loaded["resolution_entries"]},
            {"active-g0"},
        )
        with self.assertRaises(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError
        ):
            validator.require_production_g0_blocker_resolution_ledger(loaded)
        with self.assertRaises(producer.PersonaV2G0BlockerResolutionLedgerError):
            producer.require_complete_g0_blocker_resolution_ledger()

    def test_frozen_golden_is_exact_and_owned_independently(self):
        expected_bytes = 21_645
        expected_sha256 = (
            "e6428d280f8438875896dc210102611cfef54fd569e5c50ad9874ecef68146f2"
        )
        self.assertEqual(len(self.raw), expected_bytes)
        self.assertEqual(hashlib.sha256(self.raw).hexdigest(), expected_sha256)
        self.assertEqual(
            producer.EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES,
            expected_bytes,
        )
        self.assertEqual(
            producer.EXPECTED_BOOTSTRAP_CANDIDATE_SHA256,
            expected_sha256,
        )
        self.assertEqual(
            validator.EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES,
            expected_bytes,
        )
        self.assertEqual(
            validator.EXPECTED_BOOTSTRAP_CANDIDATE_SHA256,
            expected_sha256,
        )

    def test_producer_public_paths_fail_closed_on_golden_drift(self):
        drifted_bytes = producer.EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES + 1
        with mock.patch.object(
            producer,
            "EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES",
            drifted_bytes,
        ):
            self.assertEqual(
                validator.EXPECTED_BOOTSTRAP_CANDIDATE_CANONICAL_BYTES,
                21_645,
            )
            for operation in (
                producer.build_g0_blocker_resolution_ledger_bootstrap_candidate,
                lambda: producer.canonical_bootstrap_candidate_json_bytes(
                    self.candidate
                ),
                lambda: producer.g0_blocker_resolution_ledger_bootstrap_candidate_sha256(
                    self.candidate
                ),
            ):
                with self.subTest(operation=operation):
                    with self.assertRaisesRegex(
                        producer.PersonaV2G0BlockerResolutionLedgerError,
                        "frozen golden",
                    ):
                        operation()

    def test_validator_public_paths_fail_closed_on_golden_drift(self):
        drifted_sha256 = "0" * 64
        with mock.patch.object(
            validator,
            "EXPECTED_BOOTSTRAP_CANDIDATE_SHA256",
            drifted_sha256,
        ):
            self.assertEqual(
                producer.EXPECTED_BOOTSTRAP_CANDIDATE_SHA256,
                "e6428d280f8438875896dc210102611cfef54fd569e5c50ad9874ecef68146f2",
            )
            with self.assertRaisesRegex(
                validator.PersonaV2G0BlockerResolutionLedgerValidationError,
                "frozen golden",
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    self.candidate
                )
            with mock.patch.object(
                validator,
                "validate_g0_blocker_resolution_ledger_bootstrap_candidate",
                return_value=True,
            ):
                with self.assertRaisesRegex(
                    validator.PersonaV2G0BlockerResolutionLedgerValidationError,
                    "frozen golden",
                ):
                    validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                        self.raw
                    )

    def test_builder_returns_detached_values(self):
        first = producer.build_g0_blocker_resolution_ledger_bootstrap_candidate()
        first["summary"]["claim_count"] = 0
        second = producer.build_g0_blocker_resolution_ledger_bootstrap_candidate()
        self.assertEqual(second["summary"]["claim_count"], 36)

    def test_profile_dispatch_is_exact(self):
        candidate = self.fresh()
        candidate["registry_profile_id"] = "production-full-history-v1"
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "profile identity",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_duplicate_key_bytes_are_rejected_before_validation(self):
        duplicated = b'{"artifact_kind":"forged",' + self.raw[1:]
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "duplicate object key",
        ):
            validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                duplicated
            )

    def test_top_level_omission_and_extra_are_rejected(self):
        omitted = self.fresh()
        omitted.pop("registry_scope")
        extra = self.fresh()
        extra["forged"] = False
        for candidate in (omitted, extra):
            with self.subTest(keys=set(candidate)):
                with self.assertRaises(
                    validator.PersonaV2G0BlockerResolutionLedgerValidationError
                ):
                    validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                        candidate
                    )

    def test_source_registry_omission_and_extra_are_rejected(self):
        omitted = self.fresh()
        omitted["source_artifact_registry"].pop()
        extra = self.fresh()
        extra["source_artifact_registry"].append(
            copy.deepcopy(extra["source_artifact_registry"][0])
        )
        for candidate in (omitted, extra):
            with self.subTest(count=len(candidate["source_artifact_registry"])):
                with self.assertRaises(
                    validator.PersonaV2G0BlockerResolutionLedgerValidationError
                ):
                    validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                        candidate
                    )

    def test_claim_omission_extra_and_duplicate_are_rejected(self):
        omitted = self.fresh()
        omitted["resolution_entries"].pop()
        extra = self.fresh()
        forged = copy.deepcopy(extra["resolution_entries"][0])
        forged["claim_key_sha256"] = "0" * 64
        extra["resolution_entries"].append(forged)
        duplicate = self.fresh()
        duplicate["resolution_entries"].append(
            copy.deepcopy(duplicate["resolution_entries"][0])
        )
        for candidate in (omitted, extra, duplicate):
            with self.subTest(count=len(candidate["resolution_entries"])):
                with self.assertRaises(
                    validator.PersonaV2G0BlockerResolutionLedgerValidationError
                ):
                    validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                        candidate
                    )

    def test_summary_forgery_is_rejected(self):
        candidate = self.fresh()
        candidate["summary"]["active_g0_unresolved_count"] = 0
        candidate["summary"]["active_g0_count_zero"] = True
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "summary",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_resolved_status_requires_pin_path_and_value(self):
        candidate = self.fresh()
        entry = candidate["resolution_entries"][0]
        entry["status"] = "resolved-by-downstream-pin"
        entry["classification_basis"] = validator.RESOLVED_CLASSIFICATION_BASIS
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "requires downstream pin/path/value",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_defer_gate_is_an_exact_allowlist(self):
        candidate = self.fresh()
        entry = candidate["resolution_entries"][0]
        entry["status"] = "deferred-post-g0"
        entry["classification_basis"] = validator.DEFERRED_CLASSIFICATION_BASIS
        entry["defer_gate_ids"] = ["g999-unreviewed-defer"]
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "outside the exact allowlist",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_direct_self_resolution_edge_is_rejected(self):
        candidate = self.fresh()
        entry = candidate["resolution_entries"][0]
        entry["status"] = "resolved-by-downstream-pin"
        entry["classification_basis"] = validator.RESOLVED_CLASSIFICATION_BASIS
        entry["resolution_evidence"] = [
            {
                "resolution_field_path": [
                    {"token_kind": "object-key", "value": "resolved"}
                ],
                "resolution_value": True,
                "resolver_id": entry["source_id"],
                "resolver_pin": self.resolver_pin(entry["source_id"]),
            }
        ]
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "direct self edge",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_resolution_dependency_cycle_is_rejected(self):
        candidate = self.fresh()
        first = next(
            entry
            for entry in candidate["resolution_entries"]
            if entry["source_id"] == "source:realism-profile-v2"
        )
        second = next(
            entry
            for entry in candidate["resolution_entries"]
            if entry["source_id"] == "source:variant-catalog-v2"
        )
        for entry, resolver_id in (
            (first, second["source_id"]),
            (second, first["source_id"]),
        ):
            entry["status"] = "resolved-by-downstream-pin"
            entry["classification_basis"] = validator.RESOLVED_CLASSIFICATION_BASIS
            entry["resolution_evidence"] = [
                {
                    "resolution_field_path": [
                        {"token_kind": "object-key", "value": "resolved"}
                    ],
                    "resolution_value": True,
                    "resolver_id": resolver_id,
                    "resolver_pin": self.resolver_pin(resolver_id),
                }
            ]
        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "contains a cycle",
        ):
            validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(candidate)

    def test_source_provider_replay_rejects_toctou(self):
        bodies = {
            source_id: validator._trusted_source_body(source_id)
            for source_id in validator.SOURCE_ORDER
        }
        calls = {source_id: 0 for source_id in validator.SOURCE_ORDER}

        def changing_provider(source_id):
            calls[source_id] += 1
            raw = bodies[source_id]
            if source_id == validator.SOURCE_ORDER[0] and calls[source_id] == 2:
                return raw + b" "
            return raw

        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "changed during ledger validation",
        ):
            with mock.patch.object(
                validator, "_trusted_source_body", side_effect=changing_provider
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    self.candidate
                )

    def test_candidate_opening_snapshot_rejects_toctou(self):
        candidate = self.fresh()
        bodies = {
            source_id: validator._trusted_source_body(source_id)
            for source_id in validator.SOURCE_ORDER
        }
        mutated = False

        def mutating_provider(source_id):
            nonlocal mutated
            if not mutated:
                candidate["summary"]["claim_count"] += 1
                mutated = True
            return bodies[source_id]

        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "changed during validation",
        ):
            with mock.patch.object(
                validator, "_trusted_source_body", side_effect=mutating_provider
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    candidate
                )

    def test_source_duplicate_key_and_oversize_are_rejected(self):
        bodies = {
            source_id: validator._trusted_source_body(source_id)
            for source_id in validator.SOURCE_ORDER
        }
        first = validator.SOURCE_ORDER[0]
        duplicated = b'{"artifact_kind":"forged",' + bodies[first][1:]

        def duplicate_provider(source_id):
            return duplicated if source_id == first else bodies[source_id]

        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "duplicate object key",
        ):
            with mock.patch.object(
                validator, "_trusted_source_body", side_effect=duplicate_provider
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    self.candidate
                )

        def oversize_provider(source_id):
            if source_id == first:
                return b"x" * (realism_source_cap() + 1)
            return bodies[source_id]

        with self.assertRaisesRegex(
            validator.PersonaV2G0BlockerResolutionLedgerValidationError,
            "invalid framed body",
        ):
            with mock.patch.object(
                validator, "_trusted_source_body", side_effect=oversize_provider
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    self.candidate
                )

    def test_shallow_resource_bounds_precede_deep_walks(self):
        over_claims = self.fresh()
        over_claims["resolution_entries"] = [
            over_claims["resolution_entries"][0]
        ] * (validator.MAX_RESOLUTION_ENTRY_COUNT + 1)
        over_path = self.fresh()
        over_path["resolution_entries"][0]["field_path"] = [
            {"token_kind": "object-key", "value": "x"}
        ] * (validator.MAX_FIELD_PATH_DEPTH + 1)
        over_evidence = self.fresh()
        over_evidence["resolution_entries"][0]["resolution_evidence"] = [
            {}
        ] * (validator.MAX_RESOLVER_PINS_PER_CLAIM + 1)
        for candidate in (over_claims, over_path, over_evidence):
            with self.subTest():
                with self.assertRaises(
                    validator.PersonaV2G0BlockerResolutionLedgerValidationError
                ):
                    validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                        candidate
                    )

    def test_scalar_container_substitution_never_reads_trusted_sources(self):
        candidate = self.fresh()
        shared = []
        shared.append(shared)
        candidate["resolution_entries"][0]["classification_basis"] = shared
        source = mock.Mock(side_effect=AssertionError("trusted source was read"))
        with mock.patch.object(validator, "_trusted_source_body", source):
            with self.assertRaisesRegex(
                validator.PersonaV2G0BlockerResolutionLedgerValidationError,
                "classification basis",
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    candidate
                )
        source.assert_not_called()

    def test_shared_lists_hit_expanded_budget_before_trusted_source_read(self):
        candidate = self.fresh()
        token = {"token_kind": "object-key", "value": "x" * 4_096}
        shared_path = [token] * validator.MAX_FIELD_PATH_DEPTH
        resolver_pin = {
            "artifact_kind": "bounded-test-resolver",
            "artifact_schema": "kcs.persona.test-resolver/v1",
            "artifact_schema_version": 1,
            "body_framing": validator.BODY_FRAMING,
            "canonical_bytes": 1,
            "sha256": "0" * 64,
        }
        evidence = {
            "resolution_field_path": shared_path,
            "resolution_value": True,
            "resolver_id": "resolver:bounded-test",
            "resolver_pin": resolver_pin,
        }
        shared_evidence = [evidence] * validator.MAX_RESOLVER_PINS_PER_CLAIM
        for entry in candidate["resolution_entries"]:
            entry["resolution_evidence"] = shared_evidence
        source = mock.Mock(side_effect=AssertionError("trusted source was read"))
        with mock.patch.object(validator, "_trusted_source_body", source):
            with self.assertRaisesRegex(
                validator.PersonaV2G0BlockerResolutionLedgerValidationError,
                "expanded byte budget",
            ):
                validator.validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    candidate
                )
        source.assert_not_called()

        with mock.patch.object(
            producer,
            "_canonical_bootstrap_candidate_json_bytes_unchecked",
            side_effect=AssertionError("producer canonicalizer must not run"),
        ) as canonicalizer:
            with self.assertRaises(producer.PersonaV2G0BlockerResolutionLedgerError):
                producer.canonical_bootstrap_candidate_json_bytes(candidate)
            with self.assertRaises(producer.PersonaV2G0BlockerResolutionLedgerError):
                producer.g0_blocker_resolution_ledger_bootstrap_candidate_sha256(
                    candidate
                )
        canonicalizer.assert_not_called()

    def test_deep_raw_json_recursion_is_closed_before_trusted_source_read(self):
        raw = b'{"x":' + (b"[" * 5_000) + b"0" + (b"]" * 5_000) + b"}"
        source = mock.Mock(side_effect=AssertionError("trusted source was read"))
        with mock.patch.object(validator, "_trusted_source_body", source):
            with self.assertRaisesRegex(
                validator.PersonaV2G0BlockerResolutionLedgerValidationError,
                "nesting",
            ):
                validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate(
                    raw
                )
        source.assert_not_called()

    def test_hash_helper_detects_post_validation_mutation(self):
        candidate = self.fresh()
        original = validator.load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate

        def validate_then_mutate(raw):
            result = original(raw)
            candidate["summary"]["claim_count"] += 1
            return result

        with mock.patch.object(
            validator,
            "load_and_validate_g0_blocker_resolution_ledger_bootstrap_candidate",
            side_effect=validate_then_mutate,
        ):
            with self.assertRaisesRegex(
                producer.PersonaV2G0BlockerResolutionLedgerError,
                "changed during validated hashing",
            ):
                producer.g0_blocker_resolution_ledger_bootstrap_candidate_sha256(
                    candidate
                )

    def test_hash_helper_hashes_the_validated_opening_image(self):
        self.assertEqual(
            producer.g0_blocker_resolution_ledger_bootstrap_candidate_sha256(
                self.candidate
            ),
            hashlib.sha256(self.raw).hexdigest(),
        )


def realism_source_cap():
    for definition in validator._SOURCE_DEFINITIONS:
        if definition["source_id"] == validator.SOURCE_ORDER[0]:
            return definition["max_body_bytes"]
    raise AssertionError("realism source definition disappeared")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
