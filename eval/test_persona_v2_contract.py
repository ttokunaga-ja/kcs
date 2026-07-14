import copy
import json
import re
import unittest

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as spec

EXPECTED_ENVELOPE_SHA256 = "e7fd222653c7a9d5337c7ad6e08a1201ee49ab78379e3e9434f7212f11270d91"


class PersonaV2EnvelopeContractTests(unittest.TestCase):
    def test_header_and_authority_are_exact_and_negative(self):
        contract = spec.build_envelope_contract()
        self.assertEqual(contract["artifact_schema"], "kcs.persona.pc-envelope/v2")
        self.assertEqual(contract["artifact_schema_version"], 2)
        self.assertEqual(contract["artifact_kind"], "persona-pc-v2-envelope")
        self.assertEqual(contract["fixture_id"], "kcs-persona-pc-v2")
        self.assertEqual(contract["fixture_schema_version"], 2)
        self.assertFalse(contract["g0_contract_frozen"])
        self.assertEqual(
            contract["apportionment_contract"],
            {
                "algorithm_id": "hamilton-largest-remainder-v1",
                "tie_break": "descending-fractional-remainder-then-input-ordinal",
            },
        )
        self.assertEqual(
            contract["authority"],
            {
                "actual_chunks_attested": False,
                "authorizes_history_mutation": False,
                "authorizes_physical_write": False,
                "filesystem_writer_available": False,
                "formal_capacity_gate_satisfied": False,
                "history_executor_available": False,
                "kcs_execution_available": False,
                "query_instances_rendered": False,
                "query_spec_hashed": False,
                "renderer_available": False,
            },
        )
        with self.assertRaisesRegex(spec.PersonaV2ContractError, "not frozen"):
            spec.require_frozen_g0_contract()

    def test_twenty_persona_family_marginals_are_exact(self):
        self.assertEqual(spec.largest_remainder(1, (1, 1)), (1, 0))
        self.assertEqual(len(spec.PERSONA_IDS), 20)
        self.assertEqual(spec.PERSONA_IDS, tuple(f"p{i:02d}" for i in range(1, 21)))
        self.assertEqual(
            len({spec.get_persona(persona_id)["role"] for persona_id in spec.PERSONA_IDS}),
            20,
        )
        expected_suite_files = {"tiny-smoke": 4_000, "pilot": 20_300, "full": 203_000}
        for profile, expected in expected_suite_files.items():
            self.assertEqual(
                sum(spec.profile_file_count(persona_id, profile) for persona_id in spec.PERSONA_IDS),
                expected,
            )
            for persona_id in spec.PERSONA_IDS:
                if profile == "pilot":
                    self.assertEqual(
                        spec.profile_file_count(persona_id, profile) * 10,
                        spec.profile_file_count(persona_id, "full"),
                    )
                counts = spec.family_counts(persona_id, profile)
                self.assertEqual(tuple(counts), spec.FORMAT_KEYS)
                self.assertEqual(sum(counts.values()), spec.profile_file_count(persona_id, profile))

        expected_full = {
            "md": 18_580,
            "txt_log": 19_210,
            "code": 10_440,
            "structured_text": 15_310,
            "csv_tsv": 18_680,
            "html_eml": 14_430,
            "ipynb": 2_240,
            "pdf_text": 28_580,
            "pdf_scan": 11_680,
            "docx": 17_270,
            "xlsx": 15_430,
            "pptx": 10_620,
            "image": 11_380,
            "media": 2_150,
            "domain_binary": 7_000,
        }
        observed = {family: 0 for family in spec.FORMAT_KEYS}
        for persona_id in spec.PERSONA_IDS:
            for family, count in spec.family_counts(persona_id, "full").items():
                observed[family] += count
        self.assertEqual(observed, expected_full)

    def test_variant_profiles_are_person_specific_closed_and_projected(self):
        contract = spec.build_envelope_contract()
        self.assertFalse(contract["variant_catalog_complete"])
        self.assertIn(
            "variant_complexity_units_and_feasibility_parameters_missing",
            contract["blockers"],
        )
        profile_fingerprints = set()
        for persona_id in spec.PERSONA_IDS:
            full = spec.variant_counts(persona_id, "full")
            pilot = spec.variant_counts(persona_id, "pilot")
            tiny = spec.variant_counts(persona_id, "tiny-smoke")
            fingerprint = []
            for family in spec.FORMAT_KEYS:
                expected_family = spec.family_counts(persona_id, "full")[family]
                self.assertEqual(sum(row["count"] for row in full[family]), expected_family)
                self.assertEqual(
                    sum(row["count"] for row in pilot[family]),
                    spec.family_counts(persona_id, "pilot")[family],
                )
                self.assertEqual(
                    sum(row["count"] for row in tiny[family]),
                    spec.family_counts(persona_id, "tiny-smoke")[family],
                )
                full_by_variant = {row["variant_id"]: row for row in full[family]}
                for row in pilot[family]:
                    self.assertLessEqual(row["count"], full_by_variant[row["variant_id"]]["count"])
                for row in full[family]:
                    metadata = spec.VARIANT_CATALOG[row["variant_id"]]
                    self.assertEqual(row["gate_role"], metadata["gate_role"])
                    self.assertEqual(
                        row["expected_offline_disposition"],
                        metadata["expected_offline_disposition"],
                    )
                    self.assertFalse(metadata["implemented_by_renderer"])
                    fingerprint.append((family, row["variant_id"], row["ratio_pct"]))
            profile_fingerprints.add(tuple(fingerprint))
        self.assertEqual(len(profile_fingerprints), 20)
        self.assertEqual(spec.VARIANT_CATALOG["pdf-text"]["expected_offline_disposition"], "local_pdf_text")
        self.assertEqual(spec.VARIANT_CATALOG["pdf-scan"]["expected_offline_disposition"], "awaiting_ocr")
        self.assertEqual(spec.VARIANT_CATALOG["docx"]["expected_offline_disposition"], "await_conversion")
        self.assertEqual(spec.VARIANT_CATALOG["pdf-text"]["media_type"], "application/pdf")
        self.assertEqual(spec.VARIANT_CATALOG["txt"]["media_type"], "text/plain")
        self.assertEqual(spec.VARIANT_CATALOG["tif"]["media_type"], "application/octet-stream")
        self.assertTrue(all(not row["implemented_by_validator"] for row in spec.VARIANT_CATALOG.values()))
        with self.assertRaises(TypeError):
            spec.VARIANT_CATALOG["pdf-text"]["media_type"] = "text/plain"
        self.assertEqual(
            {row["variant_id"]: row["count"] for row in spec.variant_counts("p09", "pilot")["html_eml"]},
            {"html": 9, "eml": 18},
        )

    def test_density_intervals_cover_exact_pilot_and_full_targets(self):
        for profile, target in (("pilot", 12_000), ("full", 120_000)):
            for persona_id in spec.PERSONA_IDS:
                bucket_counts = spec.density_bucket_counts(persona_id, profile)
                self.assertEqual(tuple(bucket_counts), spec.DENSITY_BUCKET_ORDER)
                self.assertEqual(sum(bucket_counts.values()), spec.contributor_count(persona_id, profile))
                lower, upper = spec.density_chunk_interval(persona_id, profile)
                self.assertLessEqual(lower, target, persona_id)
                self.assertGreaterEqual(upper, target, persona_id)
        self.assertEqual(spec.contributor_count("p10", "full"), 2_728)
        self.assertEqual(spec.contributor_count("p10", "pilot"), 273)
        self.assertEqual(spec.contributor_count("p14", "full"), 2_464)
        self.assertEqual(spec.contributor_count("p14", "pilot"), 246)
        self.assertEqual(spec.density_chunk_interval("p07", "pilot")[1] - 12_000, 294)
        with self.assertRaisesRegex(spec.PersonaV2ContractError, "density"):
            spec.density_bucket_counts("p07", "tiny-smoke")

    def test_semantic_examples_are_portable_and_do_not_expose_fixture_ids(self):
        examples = []
        for persona_id in spec.PERSONA_IDS:
            example = spec.get_persona(persona_id)["semantic_filename_example"]
            examples.append(example)
            self.assertLessEqual(len(example.encode("ascii")), 120)
            self.assertRegex(example, r"^[a-z0-9][a-z0-9._-]*$")
            self.assertIsNone(re.search(r"(?:^|[-_.])p\d{2}(?:[-_.]|$)", example))
            self.assertNotIn("sha256", example)
            self.assertNotIn("source-id", example)
        self.assertEqual(len(examples), len(set(examples)))

    def test_lanes_capacity_and_pilot_history_projection_are_separate(self):
        contract = spec.build_envelope_contract()
        self.assertEqual(
            tuple(contract["lanes"]),
            ("formal-retrieval-history-v2", "recursive-robustness-v1", "byte-stress-v1"),
        )
        self.assertEqual(contract["lanes"]["formal-retrieval-history-v2"]["replay_count"], 3)
        self.assertEqual(contract["lanes"]["byte-stress-v1"]["replay_count"], 1)
        self.assertFalse(contract["lanes"]["recursive-robustness-v1"]["formal_chunk_eligible"])
        self.assertFalse(contract["lanes"]["byte-stress-v1"]["formal_chunk_eligible"])
        self.assertEqual(contract["capacity"]["formal_retained_suite_bytes"], 88 * 2**30)
        self.assertEqual(contract["capacity"]["byte_stress_payload_per_person"], 740 * 2**20)
        self.assertEqual(contract["capacity"]["byte_stress_cap_per_person"], 768 * 2**20)
        self.assertEqual(contract["capacity"]["byte_stress_suite_cap_bytes"], 15 * 2**30)
        self.assertEqual(contract["capacity"]["pilot_byte_cap"], 32 * 2**30)
        self.assertEqual(contract["capacity"]["pilot_reserve_bytes"], 96 * 2**30)
        self.assertEqual(contract["capacity"]["pilot_inode_cap"], 250_000)
        self.assertEqual(
            contract["history_checkpoints"]["pilot"]["W5-pre-purge"],
            {"current_contract_chunks": 12_480, "history_only_contract_chunks": 6_480},
        )
        self.assertEqual(
            spec.incidental_caps("pilot", "W5-pre-purge"),
            {"current": 1_020, "current_plus_history": 2_040},
        )
        self.assertEqual(
            contract["incidental_cap_contract"]["eligible_caps"]["pilot"],
            {"current": 13_500, "total": 21_000, "base_current": 1_500, "base_total": 3_000},
        )
        self.assertEqual(
            contract["history_cohort_contract"],
            {
                "allocation_unit": "contract_contributor_chunks",
                "coverage_required_in_all_twenty_scopes": ["P", "X", "Y", "N"],
                "partition": "whole_source",
                "profiles": ["pilot", "full"],
                "weights_pct": {"N": 4, "P": 4, "U": 76, "X": 10, "Y": 6},
            },
        )
        self.assertEqual(
            contract["history_checkpoints"],
            {
                profile: {
                    checkpoint: {
                        "current_contract_chunks": current,
                        "history_only_contract_chunks": history,
                    }
                    for checkpoint, (current, history) in checkpoints.items()
                }
                for profile, checkpoints in spec.HISTORY_CHECKPOINTS.items()
            },
        )
        with self.assertRaises(TypeError):
            spec.HISTORY_CHECKPOINTS["pilot"]["W0"] = (0, 0)

    def test_canonical_rebuild_validation_and_hash_are_fail_closed(self):
        first = spec.build_envelope_contract()
        second = spec.build_envelope_contract()
        self.assertEqual(first, second)
        self.assertIsNot(first, second)
        self.assertTrue(spec.validate_envelope_contract(first))
        canonical = spec.canonical_json_bytes(first)
        self.assertEqual(json.loads(canonical), first)
        self.assertEqual(spec.envelope_contract_sha256(first), spec.envelope_contract_sha256(second))
        self.assertEqual(spec.envelope_contract_sha256(first), EXPECTED_ENVELOPE_SHA256)
        self.assertEqual(
            first["canonical_limits"],
            {
                "integer_only": True,
                "max_envelope_bytes": 2 * 2**20,
                "max_nesting_depth": 64,
                "max_string_bytes": 4_096,
                "unicode_normalization": "NFC",
            },
        )

        for mutate in (
            lambda value: value.__setitem__("g0_contract_frozen", True),
            lambda value: value["authority"].__setitem__("authorizes_physical_write", True),
            lambda value: value["personas"][0].__setitem__("full_raw_files", 12_001),
            lambda value: value.__setitem__("unknown", False),
        ):
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(first)
                mutate(changed)
                with self.assertRaises(spec.PersonaV2ContractError):
                    spec.validate_envelope_contract(changed)

    def test_v1_identity_and_cardinality_remain_frozen(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kcs-persona-pc-v1")
        self.assertEqual(sum(persona["full_raw_files"] for persona in v1.PERSONAS), 195_000)


if __name__ == "__main__":
    unittest.main()
