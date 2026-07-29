"""Regression gates for the complete non-authorizing source inventory package."""

import copy
import hashlib
import json
import os
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_overlay_reservation_layout as reservation
from eval import persona_v2_source_inventory_layout as layout
from eval import persona_v2_source_inventory_package as package
from eval import persona_v2_source_inventory_package_validator as independent_validator
from eval import persona_v2_source_inventory_profile as inventory_profiles


EXPECTED_SUITE_BYTES = 45_887
EXPECTED_SUITE_SHA256 = (
    "9f216f3d986bdc92f7b07e0d2bfe266dc03df46d990f8ded706ad802d227edc3"
)
EXPECTED_P01_PILOT_ORIGIN = (
    13_043,
    "19b5c2616d7188ac5f68c90ebcecb19e8c7e5c4b636829621230c1abb1f910f3",
)
EXPECTED_P12_RESIDUAL_ORIGIN = (
    15_474,
    "f9c531177e434c5b73d396b0c1390d658ee630b9046264bc1a27daa4c4ce1fc4",
)
EXPECTED_P01_PILOT_PROFILE = (
    7_814,
    "89fb76b9a6867790ef7c55ca6ae94b9e8dd97a5a981ed236e7677b2fbfb3b65b",
)
EXPECTED_P12_FULL_PROFILE = (
    10_369,
    "bdf7371dff9cb5ae106564026d616887fffa05ccf9735bff637936fd7fcac41b",
)
EXPECTED_P12_CURRENT_COMPONENT_BYTES = 8_598_540
EXPECTED_SOURCE_SHARD_BODY_BYTES = 108_682_911
EXPECTED_P01_PILOT_SHARD = (
    574_478,
    "89a7f4c6e8ff132e53c8ed120b1ca53b23bd87af4d5aea75c5cab4a1617b0299",
    492,
)
EXPECTED_MAXIMUM_SHARD = (
    "p18",
    "full-residual",
    2,
    2_225_794,
    "98672021398178750d8ea28a7f5797286b0dafd9a26e2cbfe30fb60c9fe6413a",
    545,
)

ROW_FIELDS = frozenset(
    {
        "content_context_id",
        "deterministic_payload_seed",
        "eligible_scope_set_id",
        "intent_key",
        "origin",
        "persona_id",
        "placement_context_id",
        "present_fact_set_key",
        "quota_context_id",
        "source_profile_id",
    }
)


def _rows(body):
    """Decode a bounded canonical JSONL body for test-side joins."""

    if body and not body.endswith(b"\n"):
        raise AssertionError("source shard body must end in LF")
    result = []
    for raw in body.splitlines():
        row = json.loads(raw)
        if artifact_common.canonical_json_bytes(
            row,
            label="source inventory test row",
            max_bytes=package.MAX_INTENT_ROW_BYTES_INCLUDING_LF - 1,
        ) != raw:
            raise AssertionError("source shard row is not canonical JSON")
        result.append(row)
    return result


def _overlay_requirements(value):
    anchors = {
        row["intent_key"]: row["variant_id"]
        for row in value["semantic_anchor_slots"]
    }
    overlay = {}

    def add(intent_key, variant_id):
        previous = overlay.setdefault(intent_key, variant_id)
        if previous != variant_id:
            raise AssertionError(
                f"overlay variant disagreement for {intent_key}: "
                f"{previous} != {variant_id}"
            )

    for row in value["reservation_rows"]:
        if row["row_kind"] == "content-relation-reservation":
            add(row["anchor_intent_key"], row["endpoint_variant_id"])
            add(row["derivative_intent_key"], row["endpoint_variant_id"])
        elif row["row_kind"] == "attachment-membership-reservation":
            add(row["host_intent_key"], row["host_variant_id"])
            add(
                row["standalone_member_intent_key"],
                row["standalone_member_variant_id"],
            )
        else:  # pragma: no cover - upstream validator should reject this first.
            raise AssertionError(f"unknown reservation row kind: {row['row_kind']}")
    return overlay, anchors


def _clear_reservation_derivation_caches():
    """Release verbose origin working sets after compact test projections."""

    for name in ("_canonical_origin", "_intent_slot_tuples_by_variant"):
        clear = getattr(getattr(reservation, name, None), "cache_clear", None)
        if callable(clear):
            clear()


class PersonaV2SourceInventoryPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.layout = layout.build_source_inventory_layout()
        cls.profile_catalog = inventory_profiles.build_source_inventory_profile_catalog()
        cls.origins = [
            package.build_source_intent_origin_manifest(persona_id, origin)
            for persona_id in envelope.PERSONA_IDS
            for origin in layout.ORIGIN_ORDER
        ]
        cls.origin_by_key = {
            (value["persona_id"], value["origin"]): value for value in cls.origins
        }
        cls.profiles = [
            package.build_source_intent_profile_manifest(persona_id, profile)
            for persona_id in envelope.PERSONA_IDS
            for profile in ("pilot", "full")
        ]
        cls.profile_by_key = {
            (value["persona_id"], value["profile"]): value
            for value in cls.profiles
        }
        cls.reservation_suite = reservation.build_overlay_reservation_suite()
        # The producer has already authenticated and cached the reservation
        # origins. Compact them before the package suite releases those caches,
        # so the body/validator phases retain only the 48,940 selected joins.
        cls.overlay_by_origin = {}
        cls.anchor_by_origin = {}
        for persona_id in envelope.PERSONA_IDS:
            for origin in layout.ORIGIN_ORDER:
                value = reservation.build_overlay_reservation_origin(
                    persona_id, origin
                )
                overlay, anchors = _overlay_requirements(value)
                cls.overlay_by_origin[(persona_id, origin)] = overlay
                cls.anchor_by_origin[(persona_id, origin)] = anchors
        cls.suite = package.build_source_intent_suite_descriptor()
        _clear_reservation_derivation_caches()

    @classmethod
    def _body_provider(cls, persona_id, origin, shard_ordinal):
        return package.source_intent_shard_body_bytes(
            persona_id, origin, shard_ordinal
        )

    def test_exact_pins_counts_caps_and_negative_authority(self):
        self.assertEqual(len(self.origins), 40)
        self.assertEqual(len(self.profiles), 40)
        self.assertEqual(
            [(value["persona_id"], value["origin"]) for value in self.origins],
            [
                (persona_id, origin)
                for persona_id in envelope.PERSONA_IDS
                for origin in layout.ORIGIN_ORDER
            ],
        )
        self.assertEqual(
            [(value["persona_id"], value["profile"]) for value in self.profiles],
            [
                (persona_id, profile)
                for persona_id in envelope.PERSONA_IDS
                for profile in ("pilot", "full")
            ],
        )

        suite_raw = package.canonical_json_bytes(self.suite)
        self.assertEqual(len(suite_raw), EXPECTED_SUITE_BYTES)
        self.assertEqual(
            package.source_intent_suite_descriptor_sha256(self.suite),
            EXPECTED_SUITE_SHA256,
        )
        self.assertLessEqual(len(suite_raw), package.MAX_SUITE_DESCRIPTOR_BYTES)
        self.assertEqual(
            self.suite["completion_claims"],
            {
                "all_203000_source_slot_rows_materialized": True,
                "all_40_origin_manifests_bound": True,
                "all_40_profile_manifests_bound": True,
                "all_73_shard_body_bytes_and_sha_bound": True,
                "all_variant_inventory_profile_assignments_complete": True,
                "concrete_overlay_membership_bound": False,
                "current_source_inventory_component_cap_satisfied": True,
                "formal_complete_persona_package_cap_proved": False,
                "formal_source_recipe_profiles_bound": False,
                "full_manifest_exact_pilot_origin_reuse_proved": True,
                "present_fact_sets_bound": False,
                "semantic_content_catalogs_bound": False,
                "source_intent_inventory_complete": False,
            },
        )
        self.assertEqual(
            self.suite["dependency_direction_contract"],
            package.SUITE_DEPENDENCY_CONTRACT,
        )
        self.assertEqual(
            self.suite["remaining_blockers"], package.SUITE_REMAINING_BLOCKERS
        )

        expected_origins = {
            ("p01", "pilot"): EXPECTED_P01_PILOT_ORIGIN,
            ("p12", "full-residual"): EXPECTED_P12_RESIDUAL_ORIGIN,
        }
        for value in self.origins:
            raw = package.canonical_json_bytes(value)
            self.assertLessEqual(len(raw), package.MAX_ORIGIN_MANIFEST_BYTES)
            self.assertEqual(set(value["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(all(flag is False for flag in value["authority"].values()))
            self.assertIs(value["g0_contract_frozen"], False)
            self.assertEqual(
                value["completion_claims"], package.ORIGIN_COMPLETION_CLAIMS
            )
            self.assertEqual(
                value["dependency_direction_contract"],
                package.ORIGIN_DEPENDENCY_CONTRACT,
            )
            self.assertEqual(
                value["remaining_blockers"], package.ORIGIN_REMAINING_BLOCKERS
            )
            self.assertEqual(
                value["input_binding_order"],
                [
                    "persona-v2-source-inventory-layout",
                    "persona-v2-source-inventory-profile-catalog",
                    "persona-v2-overlay-reservation-suite",
                    "persona-v2-overlay-reservation-origin",
                ],
            )
            expected_reservation = next(
                row
                for row in self.reservation_suite["origin_bindings"]
                if row["persona_id"] == value["persona_id"]
                and row["origin"] == value["origin"]
            )
            self.assertEqual(
                value["input_bindings"][-1]["sha256"],
                expected_reservation["sha256"],
            )
            expected = expected_origins.get((value["persona_id"], value["origin"]))
            if expected is not None:
                expected_bytes, expected_sha = expected
                self.assertEqual(len(raw), expected_bytes)
                self.assertEqual(
                    package.source_intent_origin_manifest_sha256(
                        value["persona_id"], value["origin"], value
                    ),
                    expected_sha,
                )

        for value in self.profiles:
            raw = package.canonical_json_bytes(value)
            self.assertLessEqual(len(raw), package.MAX_PROFILE_MANIFEST_BYTES)
            self.assertEqual(set(value["authority"]), package.AUTHORITY_FIELDS)
            self.assertTrue(all(flag is False for flag in value["authority"].values()))
            self.assertIs(value["g0_contract_frozen"], False)
            profile = value["profile"]
            self.assertEqual(
                value["completion_claims"],
                {
                    "all_profile_origin_manifests_bound": True,
                    "all_profile_shard_references_bound": True,
                    "concrete_overlay_membership_bound": False,
                    "formal_source_recipe_profiles_bound": False,
                    "full_profile_composition_bound": profile == "full",
                    "full_profile_exact_pilot_origin_reuse_proved": (
                        profile == "full"
                    ),
                    "pilot_profile_single_origin_bound": profile == "pilot",
                    "present_fact_sets_bound": False,
                    "semantic_content_catalogs_bound": False,
                    "source_intent_inventory_complete": False,
                    "source_intent_profile_manifest_complete": True,
                },
            )
            self.assertEqual(
                value["dependency_direction_contract"],
                package.PROFILE_DEPENDENCY_CONTRACT,
            )
            self.assertEqual(
                value["remaining_blockers"], package.PROFILE_REMAINING_BLOCKERS
            )
            self.assertEqual(
                value["input_binding_order"],
                ["persona-v2-overlay-reservation-suite"],
            )
            self.assertEqual(
                value["input_bindings"], [self.suite["input_bindings"][2]]
            )
            expected = {
                ("p01", "pilot"): EXPECTED_P01_PILOT_PROFILE,
                ("p12", "full"): EXPECTED_P12_FULL_PROFILE,
            }.get((value["persona_id"], value["profile"]))
            if expected is not None:
                expected_bytes, expected_sha = expected
                self.assertEqual(len(raw), expected_bytes)
                self.assertEqual(
                    package.source_intent_profile_manifest_sha256(
                        value["persona_id"], value["profile"], value
                    ),
                    expected_sha,
                )

    def test_all_203000_rows_73_shards_exact_marginals_and_caps(self):
        row_count = 0
        shard_count = 0
        persona_source_bytes = {persona_id: 0 for persona_id in envelope.PERSONA_IDS}
        maximum_row_bytes = 0
        maximum_shard_bytes = 0
        source_shard_body_bytes = 0

        for manifest in self.origins:
            persona_id = manifest["persona_id"]
            origin = manifest["origin"]
            for descriptor in manifest["shard_descriptors"]:
                body = self._body_provider(
                    persona_id, origin, descriptor["shard_ordinal"]
                )
                lines = body.splitlines()
                shard_count += 1
                row_count += len(lines)
                persona_source_bytes[persona_id] += len(body)
                source_shard_body_bytes += len(body)
                maximum_shard_bytes = max(maximum_shard_bytes, len(body))
                self.assertTrue(body.endswith(b"\n"))
                self.assertFalse(body.endswith(b"\n\n"))
                self.assertEqual(len(lines), descriptor["row_count"])
                self.assertLessEqual(
                    len(lines), package.MAX_INTENTS_PER_SHARD
                )
                self.assertEqual(len(body), descriptor["body_bytes"])
                self.assertEqual(hashlib.sha256(body).hexdigest(), descriptor["body_sha256"])
                self.assertLessEqual(len(body), package.MAX_SHARD_BODY_BYTES)
                actual_maximum = max(len(raw) + 1 for raw in lines)
                maximum_row_bytes = max(maximum_row_bytes, actual_maximum)
                self.assertEqual(
                    actual_maximum, descriptor["max_row_bytes_including_lf"]
                )
                self.assertLessEqual(
                    actual_maximum,
                    package.MAX_INTENT_ROW_BYTES_INCLUDING_LF,
                )
                coordinate = (persona_id, origin, descriptor["shard_ordinal"])
                expected = {
                    ("p01", "pilot", 1): EXPECTED_P01_PILOT_SHARD,
                    EXPECTED_MAXIMUM_SHARD[:3]: EXPECTED_MAXIMUM_SHARD[3:],
                }.get(coordinate)
                if expected is not None:
                    expected_bytes, expected_sha, expected_row_maximum = expected
                    self.assertEqual(len(body), expected_bytes)
                    self.assertEqual(hashlib.sha256(body).hexdigest(), expected_sha)
                    self.assertEqual(actual_maximum, expected_row_maximum)

        self.assertEqual(row_count, 203_000)
        self.assertEqual(shard_count, 73)
        self.assertEqual(source_shard_body_bytes, EXPECTED_SOURCE_SHARD_BODY_BYTES)
        self.assertEqual(
            self.suite["coverage"]["gate_role_source_counts"],
            {
                "contract_contributor": 69_236,
                "incidental_searchable": 60_414,
                "raw_only": 73_350,
            },
        )
        self.assertEqual(
            self.suite["coverage"]["source_intent_count"], row_count
        )
        self.assertEqual(self.suite["coverage"]["shard_count"], shard_count)
        self.assertEqual(
            self.suite["coverage"]["maximum_row_bytes_including_lf"],
            maximum_row_bytes,
        )
        self.assertEqual(
            self.suite["coverage"]["maximum_shard_body_bytes"],
            maximum_shard_bytes,
        )
        self.assertEqual(
            self.suite["coverage"]["shard_body_bytes"],
            EXPECTED_SOURCE_SHARD_BODY_BYTES,
        )
        for persona_id, body_bytes in persona_source_bytes.items():
            self.assertLessEqual(
                body_bytes, package.MAX_PERSONA_PACKAGE_BYTES, persona_id
            )

    def test_every_overlay_reference_and_anchor_resolves_to_exact_origin_row(self):
        profile_by_variant = {
            row["variant_id"]: row["source_profile_id"]
            for row in self.profile_catalog["source_profile_rows"]
        }
        role_by_variant = {
            row["variant_id"]: row["gate_role"]
            for row in self.profile_catalog["source_profile_rows"]
        }
        grouped = {}
        suite_overlay = {}
        suite_anchors = {}
        for coordinate in (
            (persona_id, origin)
            for persona_id in envelope.PERSONA_IDS
            for origin in layout.ORIGIN_ORDER
        ):
            persona_id, origin = coordinate
            overlay = self.overlay_by_origin[coordinate]
            anchors = self.anchor_by_origin[coordinate]
            self.assertTrue(set(overlay).isdisjoint(anchors))
            for target, source in (
                (suite_overlay, overlay),
                (suite_anchors, anchors),
            ):
                for intent_key, variant_id in source.items():
                    previous = target.setdefault(intent_key, variant_id)
                    self.assertEqual(previous, variant_id)
                    ordinal = int(intent_key.rsplit("-", 1)[1])
                    shard_coordinate = (
                        persona_id,
                        origin,
                        (ordinal - 1) // layout.MAX_INTENTS_PER_SHARD + 1,
                    )
                    grouped.setdefault(shard_coordinate, {})[
                        (ordinal - 1) % layout.MAX_INTENTS_PER_SHARD
                    ] = (intent_key, variant_id)

        self.assertEqual(len(suite_overlay), 46_840)
        self.assertEqual(len(suite_anchors), 2_100)
        self.assertTrue(set(suite_overlay).isdisjoint(suite_anchors))
        self.assertEqual(len(set(suite_overlay) | set(suite_anchors)), 48_940)
        self.assertEqual(
            {
                role: sum(
                    role_by_variant[variant_id] == role
                    for variant_id in suite_overlay.values()
                )
                for role in layout.GATE_ROLE_ORDER
            },
            {
                "contract_contributor": 25_765,
                "incidental_searchable": 21_075,
                "raw_only": 0,
            },
        )
        self.assertTrue(
            all(
                role_by_variant[variant_id] == "contract_contributor"
                for variant_id in suite_anchors.values()
            )
        )

        # Only the selected overlay/anchor rows are decoded.  The independent
        # validator performs the sole complete 203,000-row semantic parse.
        for coordinate, expected_rows in grouped.items():
            lines = self._body_provider(*coordinate).splitlines()
            for local_index, (intent_key, variant_id) in expected_rows.items():
                row = json.loads(lines[local_index])
                self.assertEqual(frozenset(row), ROW_FIELDS)
                self.assertEqual(row["intent_key"], intent_key)
                self.assertEqual(
                    row["source_profile_id"], profile_by_variant[variant_id]
                )

    def test_full_profile_reuses_exact_pilot_manifest_and_shard(self):
        for persona_id in envelope.PERSONA_IDS:
            pilot = self.profile_by_key[(persona_id, "pilot")]
            full = self.profile_by_key[(persona_id, "full")]
            pilot_origin = self.origin_by_key[(persona_id, "pilot")]
            pilot_binding = pilot["origin_manifest_bindings"][0]
            self.assertEqual(full["origin_manifest_bindings"][0], pilot_binding)
            self.assertEqual(
                pilot_binding["sha256"],
                package.source_intent_origin_manifest_sha256(
                    persona_id, "pilot", pilot_origin
                ),
            )
            self.assertEqual(
                pilot["shard_descriptors"],
                full["shard_descriptors"][: len(pilot["shard_descriptors"])],
            )
            self.assertEqual(
                [row["shard_id"] for row in full["shard_descriptors"]],
                next(
                    row["expected_full_manifest_shard_ids"]
                    for row in self.layout["personas"]
                    if row["persona_id"] == persona_id
                ),
            )

    def test_current_component_ledger_stays_bounded_without_claiming_future_cap(self):
        for persona_id in envelope.PERSONA_IDS:
            ledger = next(
                row
                for row in self.suite["persona_current_component_byte_ledgers"]
                if row["persona_id"] == persona_id
            )
            unique_source_shard_body_bytes = sum(
                descriptor["body_bytes"]
                for value in self.origins
                if value["persona_id"] == persona_id
                for descriptor in value["shard_descriptors"]
            )
            source_origin_manifest_bytes = sum(
                len(package.canonical_json_bytes(value))
                for value in self.origins
                if value["persona_id"] == persona_id
            )
            profile_manifest_bytes = sum(
                len(package.canonical_json_bytes(value))
                for value in self.profiles
                if value["persona_id"] == persona_id
            )
            self.assertEqual(
                ledger["unique_source_shard_body_bytes"],
                unique_source_shard_body_bytes,
            )
            self.assertEqual(
                ledger["source_origin_manifest_bytes"],
                source_origin_manifest_bytes,
            )
            self.assertEqual(
                ledger["profile_manifest_bytes"], profile_manifest_bytes
            )
            self.assertEqual(
                ledger["current_component_bytes"],
                unique_source_shard_body_bytes
                + source_origin_manifest_bytes
                + profile_manifest_bytes,
            )
            self.assertEqual(
                ledger["included_components"],
                [
                    "unique-pilot-and-full-residual-source-jsonl-shard-bodies",
                    "pilot-and-full-residual-source-origin-manifests",
                    "pilot-and-full-source-profile-manifests",
                ],
            )
            self.assertLessEqual(
                ledger["current_component_bytes"], package.MAX_PERSONA_PACKAGE_BYTES
            )
            self.assertEqual(
                ledger["headroom_bytes"],
                package.MAX_PERSONA_PACKAGE_BYTES - ledger["current_component_bytes"],
            )
            self.assertIs(ledger["future_complete_package_cap_proved"], False)
        p12 = next(
            row
            for row in self.suite["persona_current_component_byte_ledgers"]
            if row["persona_id"] == "p12"
        )
        self.assertEqual(p12["current_component_bytes"], EXPECTED_P12_CURRENT_COMPONENT_BYTES)
        self.assertIs(
            self.suite["completion_claims"]["formal_complete_persona_package_cap_proved"],
            False,
        )

    def test_independent_validator_replays_all_bodies_and_rejects_authority(self):
        self.assertTrue(
            independent_validator.validate_source_inventory_package(
                self.suite,
                self.origins,
                self.profiles,
                self._body_provider,
            )
        )

        suite = copy.deepcopy(self.suite)
        first = next(iter(suite["authority"]))
        suite["authority"][first] = True
        with self.assertRaises(
            independent_validator.PersonaV2SourceInventoryPackageValidationError
        ):
            independent_validator.validate_source_inventory_package(
                suite, self.origins, self.profiles, self._body_provider
            )

        with self.assertRaises(package.PersonaV2SourceInventoryPackageError):
            package.require_complete_source_intent_inventory()

    def test_provider_callback_metadata_mutation_is_rejected_postflight(self):
        suite = copy.deepcopy(self.suite)
        origins = copy.deepcopy(self.origins)
        profiles = copy.deepcopy(self.profiles)
        opening_scope = suite["completion_scope"]

        def detached_validation(
            suite_snapshot,
            origin_snapshots,
            profile_snapshots,
            body_provider,
        ):
            self.assertIsNot(suite_snapshot, suite)
            self.assertIsNot(origin_snapshots, origins)
            self.assertIsNot(profile_snapshots, profiles)
            body_provider("p01", "pilot", 1)
            self.assertEqual(suite_snapshot["completion_scope"], opening_scope)
            return True

        def mutating_provider(persona_id, origin, shard_ordinal):
            suite["completion_scope"] = "mutated-during-provider-callback"
            return self._body_provider(persona_id, origin, shard_ordinal)

        with mock.patch.object(
            independent_validator,
            "_validate_source_inventory_package_snapshot",
            side_effect=detached_validation,
        ):
            with self.assertRaisesRegex(
                independent_validator.PersonaV2SourceInventoryPackageValidationError,
                "changed during provider callback",
            ):
                independent_validator.validate_source_inventory_package(
                    suite,
                    origins,
                    profiles,
                    mutating_provider,
                )
        self.assertEqual(
            suite["completion_scope"], "mutated-during-provider-callback"
        )

    def test_nested_metadata_tamper_fails_before_any_body_access(self):
        candidates = []

        candidate = copy.deepcopy(self.suite)
        candidate["canonical_limits"]["max_body_bytes"] = True
        candidates.append(candidate)

        candidate = copy.deepcopy(self.suite)
        false_claim = next(
            key
            for key, flag in candidate["completion_claims"].items()
            if flag is False
        )
        candidate["completion_claims"][false_claim] = True
        candidates.append(candidate)

        candidate = copy.deepcopy(self.suite)
        order_name = next(
            key
            for key, values in candidate["orders"].items()
            if type(values) is list and len(values) > 1
        )
        candidate["orders"][order_name].reverse()
        candidates.append(candidate)

        candidate = copy.deepcopy(self.suite)
        candidate["remaining_blockers"] = []
        candidates.append(candidate)

        candidate = copy.deepcopy(self.suite)
        candidate["query_id"] = "forbidden-downstream-field"
        candidates.append(candidate)

        for index, candidate in enumerate(candidates):
            body_requests = []

            def tracking_provider(persona_id, origin, shard_ordinal):
                body_requests.append((persona_id, origin, shard_ordinal))
                return self._body_provider(persona_id, origin, shard_ordinal)

            with self.subTest(mutation=index):
                with self.assertRaises(
                    independent_validator.PersonaV2SourceInventoryPackageValidationError
                ):
                    independent_validator.validate_source_inventory_package(
                        candidate,
                        self.origins,
                        self.profiles,
                        tracking_provider,
                    )
                self.assertEqual(body_requests, [])

    def test_digest_rethreaded_profile_swap_still_fails_semantic_validation(self):
        # Re-hash every affected wrapper so rejection cannot be explained by a
        # shallow body-digest mismatch.  The independent validator must recover
        # the exact variant interval from the upstream layout.
        origins = copy.deepcopy(self.origins)
        profiles = copy.deepcopy(self.profiles)
        suite = copy.deepcopy(self.suite)
        target = next(
            value
            for value in origins
            if value["persona_id"] == "p01" and value["origin"] == "pilot"
        )
        descriptor = target["shard_descriptors"][0]
        original_body = self._body_provider("p01", "pilot", 1)
        rows = _rows(original_body)
        rows[0]["source_profile_id"], rows[40]["source_profile_id"] = (
            rows[40]["source_profile_id"],
            rows[0]["source_profile_id"],
        )
        tampered_body = b"".join(
            artifact_common.canonical_json_bytes(
                row,
                label="tampered source inventory test row",
                max_bytes=package.MAX_INTENT_ROW_BYTES_INCLUDING_LF - 1,
            )
            + b"\n"
            for row in rows
        )
        self.assertEqual(len(tampered_body), len(original_body))
        descriptor["body_bytes"] = len(tampered_body)
        descriptor["body_sha256"] = hashlib.sha256(tampered_body).hexdigest()
        descriptor["max_row_bytes_including_lf"] = max(
            len(raw) + 1 for raw in tampered_body.splitlines()
        )

        origin_raw = artifact_common.canonical_json_bytes(
            target,
            label="tampered source inventory origin manifest",
            max_bytes=package.MAX_ORIGIN_MANIFEST_BYTES,
        )
        origin_sha = hashlib.sha256(origin_raw).hexdigest()
        affected_profiles = [
            value for value in profiles if value["persona_id"] == "p01"
        ]
        for profile in affected_profiles:
            profile["shard_descriptors"][0] = copy.deepcopy(descriptor)
            binding = next(
                row
                for row in profile["origin_manifest_bindings"]
                if row["origin"] == "pilot"
            )
            binding["canonical_bytes"] = len(origin_raw)
            binding["sha256"] = origin_sha

        origin_binding = next(
            row
            for row in suite["origin_manifest_bindings"]
            if row["persona_id"] == "p01" and row["origin"] == "pilot"
        )
        origin_binding["canonical_bytes"] = len(origin_raw)
        origin_binding["sha256"] = origin_sha
        for profile in affected_profiles:
            profile_raw = artifact_common.canonical_json_bytes(
                profile,
                label="tampered source inventory profile manifest",
                max_bytes=package.MAX_PROFILE_MANIFEST_BYTES,
            )
            binding = next(
                row
                for row in suite["profile_manifest_bindings"]
                if row["persona_id"] == "p01"
                and row["profile"] == profile["profile"]
            )
            binding["canonical_bytes"] = len(profile_raw)
            binding["sha256"] = hashlib.sha256(profile_raw).hexdigest()

        # Prove this is not a shallow broken-link test: every affected public
        # binding now agrees with the canonical bytes supplied to validation.
        self.assertEqual(
            origin_binding["sha256"], hashlib.sha256(origin_raw).hexdigest()
        )
        for profile in affected_profiles:
            profile_raw = artifact_common.canonical_json_bytes(
                profile,
                label="tampered source inventory profile manifest",
                max_bytes=package.MAX_PROFILE_MANIFEST_BYTES,
            )
            binding = next(
                row
                for row in suite["profile_manifest_bindings"]
                if row["persona_id"] == "p01"
                and row["profile"] == profile["profile"]
            )
            self.assertEqual(
                binding["sha256"], hashlib.sha256(profile_raw).hexdigest()
            )

        body_requests = []

        def provider(persona_id, origin, shard_ordinal):
            body_requests.append((persona_id, origin, shard_ordinal))
            if (persona_id, origin, shard_ordinal) == ("p01", "pilot", 1):
                return tampered_body
            return self._body_provider(persona_id, origin, shard_ordinal)

        with self.assertRaises(
            independent_validator.PersonaV2SourceInventoryPackageValidationError
        ):
            independent_validator.validate_source_inventory_package(
                suite, origins, profiles, provider
            )
        self.assertEqual(body_requests, [("p01", "pilot", 1)])

    def test_suite_pin_is_hashseed_timezone_and_locale_independent(self):
        script = (
            "from eval import persona_v2_source_inventory_package as p;"
            "import hashlib;"
            "x=p.build_source_intent_suite_descriptor();"
            "b=p.source_intent_shard_body_bytes('p01','pilot',1);"
            "print(len(p.canonical_json_bytes(x)),"
            "p.source_intent_suite_descriptor_sha256(x),"
            "hashlib.sha256(b).hexdigest())"
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
            timeout=120,
        ).strip()
        self.assertEqual(
            output,
            f"{EXPECTED_SUITE_BYTES} {EXPECTED_SUITE_SHA256} "
            f"{EXPECTED_P01_PILOT_SHARD[1]}",
        )

    def test_z_manifest_binding_and_pilot_composition_tamper_fail_before_bodies(self):
        cases = []

        origins = copy.deepcopy(self.origins)
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
        p01["input_bindings"][-1] = copy.deepcopy(p02["input_bindings"][-1])
        cases.append((self.suite, origins, self.profiles))

        profiles = copy.deepcopy(self.profiles)
        full = next(
            row
            for row in profiles
            if row["persona_id"] == "p01" and row["profile"] == "full"
        )
        full["origin_manifest_bindings"].reverse()
        cases.append((self.suite, self.origins, profiles))

        profiles = copy.deepcopy(self.profiles)
        pilot = next(
            row
            for row in profiles
            if row["persona_id"] == "p01" and row["profile"] == "pilot"
        )
        pilot["input_bindings"][0]["sha256"] = "0" * 64
        cases.append((self.suite, self.origins, profiles))

        suite = copy.deepcopy(self.suite)
        suite["origin_manifest_bindings"][0]["sha256"] = "0" * 64
        cases.append((suite, self.origins, self.profiles))

        for index, (suite, origins, profiles) in enumerate(cases):
            body_requests = []

            def tracking_provider(persona_id, origin, shard_ordinal):
                body_requests.append((persona_id, origin, shard_ordinal))
                return self._body_provider(persona_id, origin, shard_ordinal)

            with self.subTest(mutation=index):
                with self.assertRaises(
                    independent_validator.PersonaV2SourceInventoryPackageValidationError
                ):
                    independent_validator.validate_source_inventory_package(
                        suite, origins, profiles, tracking_provider
                    )
                self.assertEqual(body_requests, [])


if __name__ == "__main__":
    unittest.main()
