import copy
import json
import re
import unittest

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as spec

EXPECTED_ENVELOPE_SHA256 = "1d49e79049b409ee5bd82d0b307db5055c2a58544df81858b77552ea82bff370"


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
            contract["topology_status"],
            "exact-topology-external-sidecar-not-g0-bound",
        )
        self.assertIn("exact_topology_sidecar_not_bound_by_g0_root", contract["blockers"])
        self.assertIn(
            "persona_fidelity_realism_profile_and_overlay_missing",
            contract["blockers"],
        )
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
            "md": 19_660,
            "txt_log": 19_210,
            "code": 10_440,
            "structured_text": 15_310,
            "csv_tsv": 18_680,
            "html_eml": 14_430,
            "ipynb": 2_240,
            "pdf_text": 29_680,
            "pdf_scan": 11_200,
            "docx": 16_490,
            "xlsx": 15_270,
            "pptx": 10_180,
            "image": 11_380,
            "media": 2_150,
            "domain_binary": 6_680,
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
        self.assertEqual(spec.contributor_count("p08", "pilot"), 267)
        self.assertEqual(spec.contributor_count("p08", "full"), 2_672)
        self.assertEqual(spec.contributor_count("p11", "pilot"), 268)
        self.assertEqual(spec.contributor_count("p11", "full"), 2_680)
        self.assertEqual(spec.contributor_count("p15", "pilot"), 268)
        self.assertEqual(spec.contributor_count("p15", "full"), 2_680)
        self.assertEqual(spec.contributor_count("p17", "pilot"), 267)
        self.assertEqual(spec.contributor_count("p17", "full"), 2_672)
        self.assertEqual(
            tuple(spec.density_bucket_counts("p17", "pilot").values()),
            (3, 11, 53, 200),
        )
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
        self.assertIs(contract["capacity"]["absolute_root_bound_caps_frozen"], False)
        self.assertIs(
            contract["capacity"]["superseded_unmeasured_absolute_candidates_authoritative"],
            False,
        )
        self.assertEqual(contract["capacity"]["byte_stress_payload_per_person"], 740 * 2**20)
        self.assertEqual(contract["capacity"]["byte_stress_cap_per_person"], 768 * 2**20)
        self.assertEqual(contract["capacity"]["byte_stress_suite_cap_bytes"], 15 * 2**30)
        self.assertEqual(
            contract["capacity"]["formal_workload_lower_bounds"]["pilot_w0"],
            {
                "contract_chunk_objects_per_replay": 240_000,
                "source_files_per_replay": 20_300,
                "source_plus_chunk_regular_file_inodes_per_replay": 260_300,
            },
        )
        self.assertEqual(
            contract["capacity"]["formal_workload_lower_bounds"]["full_w0"],
            {
                "contract_chunk_objects_per_replay": 2_400_000,
                "source_files_per_replay": 203_000,
                "source_plus_chunk_regular_file_inodes_per_replay": 2_603_000,
            },
        )
        self.assertEqual(
            contract["capacity"]["measurement_gate"]["minimum_headroom_basis_points"],
            2_500,
        )
        self.assertIs(
            contract["capacity"]["measurement_gate"]["pilot_inode_cap_frozen"],
            False,
        )
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
        history_contract = contract["history_cohort_contract"]
        self.assertEqual(history_contract["allocation_unit"], "contract_contributor_chunks")
        self.assertEqual(history_contract["cohort_order"], ["P", "X", "Y", "N", "U"])
        self.assertEqual(
            history_contract["coverage_required_in_all_twenty_scopes"],
            ["P", "X", "Y", "N"],
        )
        self.assertEqual(history_contract["partition"], "whole_source")
        self.assertEqual(history_contract["profiles"], ["pilot", "full"])
        self.assertEqual(history_contract["required_scope_count"], 20)
        self.assertEqual(history_contract["max_chunks_per_contributor_source"], 70)
        self.assertEqual(
            history_contract["weights_pct"],
            {"P": 4, "X": 10, "Y": 6, "N": 4, "U": 76},
        )
        expected_chunks = {
            "pilot": {"P": 480, "X": 1_200, "Y": 720, "N": 480, "U": 9_120},
            "full": {"P": 4_800, "X": 12_000, "Y": 7_200, "N": 4_800, "U": 91_200},
        }
        expected_lower = {
            "pilot": {"P": 20, "X": 20, "Y": 20, "N": 20, "U": 131},
            "full": {"P": 69, "X": 172, "Y": 103, "N": 69, "U": 1_303},
        }
        for profile in ("pilot", "full"):
            self.assertEqual(spec.history_cohort_chunk_counts(profile), expected_chunks[profile])
            self.assertEqual(
                spec.history_cohort_source_lower_bounds(profile),
                expected_lower[profile],
            )
            profile_contract = history_contract["profile_source_lower_bounds"][profile]
            self.assertEqual(
                profile_contract["minimum_contributor_sources"],
                sum(expected_lower[profile].values()),
            )
            self.assertEqual(
                {
                    row["cohort_id"]: row["contract_contributor_chunks"]
                    for row in profile_contract["cohorts"]
                },
                expected_chunks[profile],
            )
        self.assertEqual(
            min(
                spec.contributor_count(persona_id, "pilot")
                - sum(expected_lower["pilot"].values())
                for persona_id in spec.PERSONA_IDS
            ),
            27,
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
            lambda value: value["authority"].__setitem__("authorizes_physical_write", 0),
            lambda value: value["personas"][0].__setitem__("full_raw_files", 12_001),
            lambda value: value["personas"][0].__setitem__("full_raw_files", True),
            lambda value: value.__setitem__("unknown", False),
        ):
            with self.subTest(mutate=mutate):
                changed = copy.deepcopy(first)
                mutate(changed)
                with self.assertRaises(spec.PersonaV2ContractError):
                    spec.validate_envelope_contract(changed)

    def test_v1_identity_and_cardinality_remain_frozen(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kio-persona-pc-v1")
        self.assertEqual(sum(persona["full_raw_files"] for persona in v1.PERSONAS), 195_000)


if __name__ == "__main__":
    unittest.main()
