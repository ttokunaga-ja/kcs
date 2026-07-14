import copy
import os
import subprocess
import sys
import unittest

from eval import persona_fixture_spec as v1
from eval import persona_v2_contract as envelope
from eval import persona_v2_variant_catalog as catalog


class PersonaV2VariantCatalogTests(unittest.TestCase):
    def test_identity_bindings_hash_size_and_negative_authority_are_exact(self):
        value = catalog.build_variant_catalog()
        self.assertEqual(value["artifact_schema"], catalog.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], catalog.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertIs(value["variant_rows_complete"], True)
        self.assertIs(value["variant_marginals_complete"], True)
        self.assertIs(value["variant_catalog_complete"], False)
        self.assertIs(value["renderer_validator_implementation_complete"], False)
        self.assertIs(value["source_level_feasibility_complete"], False)
        self.assertEqual(
            set(value["authority"]),
            {
                "actual_chunks_attested",
                "authorizes_g0_freeze",
                "authorizes_history_mutation",
                "authorizes_physical_write",
                "authorizes_solver_execution",
                "authorizes_source_plan",
                "filesystem_writer_available",
                "formal_capacity_gate_satisfied",
                "history_executor_available",
                "kcs_execution_available",
                "query_instances_rendered",
                "query_spec_hashed",
                "renderer_available",
                "validator_available",
            },
        )
        for key, flag in value["authority"].items():
            self.assertIs(type(flag), bool, key)
            self.assertIs(flag, False, key)
        raw = catalog.canonical_json_bytes(value)
        self.assertEqual(len(raw), 211_734)
        self.assertEqual(
            catalog.variant_catalog_sha256(value),
            "9eb29e7dc52acddfb9e57249d88791d07de4a1dadfac949119980c58f9c11be8",
        )
        self.assertTrue(catalog.validate_variant_catalog(value))

    def test_variant_and_marginal_shape_order_totals_are_exact(self):
        value = catalog.build_variant_catalog()
        variants = value["variant_rows"]
        marginals = value["persona_variant_marginals"]
        self.assertEqual(len(variants), 71)
        self.assertEqual(len(marginals), 566)
        self.assertEqual(sum(row["full_count"] > 0 for row in marginals), 541)
        self.assertEqual(sum(row["full_count"] == 0 for row in marginals), 25)
        self.assertEqual(
            {row["variant_id"] for row in variants},
            set(envelope.VARIANT_CATALOG),
        )
        family_index = {family: index for index, family in enumerate(envelope.FORMAT_KEYS)}
        self.assertEqual(
            [(family_index[row["family"]], row["variant_id"].encode("ascii")) for row in variants],
            sorted(
                (family_index[row["family"]], row["variant_id"].encode("ascii"))
                for row in variants
            ),
        )
        self.assertEqual(
            value["suite_gate_role_counts"],
            {
                "full": {
                    "contract_contributor": 67_296,
                    "incidental_searchable": 60_414,
                    "raw_only": 75_290,
                },
                "pilot": {
                    "contract_contributor": 6_731,
                    "incidental_searchable": 6_040,
                    "raw_only": 7_529,
                },
                "tiny-smoke": {
                    "contract_contributor": 1_324,
                    "incidental_searchable": 1_108,
                    "raw_only": 1_568,
                },
            },
        )
        for row in marginals:
            self.assertEqual(
                row["full_minus_pilot_count"],
                row["full_count"] - row["pilot_count"],
            )
            self.assertGreaterEqual(row["full_minus_pilot_count"], 0)
        expected_marginals = {}
        for persona_id in envelope.PERSONA_IDS:
            profile_rows = {
                profile: envelope.variant_counts(persona_id, profile)
                for profile in ("tiny-smoke", "pilot", "full")
            }
            for family in envelope.FORMAT_KEYS:
                by_profile = {
                    profile: {
                        row["variant_id"]: row for row in profile_rows[profile][family]
                    }
                    for profile in profile_rows
                }
                for variant_id, full_row in by_profile["full"].items():
                    key = (persona_id, family, variant_id)
                    pilot_count = by_profile["pilot"][variant_id]["count"]
                    expected_marginals[key] = {
                        "family": family,
                        "full_count": full_row["count"],
                        "full_minus_pilot_count": full_row["count"] - pilot_count,
                        "persona_id": persona_id,
                        "pilot_count": pilot_count,
                        "ratio_pct": full_row["ratio_pct"],
                        "tiny_smoke_count": by_profile["tiny-smoke"][variant_id]["count"],
                        "variant_id": variant_id,
                    }
        actual_marginals = {
            (row["persona_id"], row["family"], row["variant_id"]): row
            for row in marginals
        }
        self.assertEqual(actual_marginals, expected_marginals)
        for persona_id in envelope.PERSONA_IDS:
            persona_rows = [row for row in marginals if row["persona_id"] == persona_id]
            for field, profile in (
                ("tiny_smoke_count", "tiny-smoke"),
                ("pilot_count", "pilot"),
                ("full_count", "full"),
            ):
                self.assertEqual(
                    sum(row[field] for row in persona_rows),
                    envelope.profile_file_count(persona_id, profile),
                )

    def test_mime_gate_complexity_and_renderer_boundaries_are_explicit(self):
        value = catalog.build_variant_catalog()
        by_id = {row["variant_id"]: row for row in value["variant_rows"]}
        examples = {
            "wav": ("audio/wav", "application/octet-stream"),
            "pcap": ("application/vnd.tcpdump.pcap", "application/octet-stream"),
            "tif": ("image/tiff", "application/octet-stream"),
            "eml": ("message/rfc822", "application/octet-stream"),
            "dicom-part10": ("application/dicom", "application/octet-stream"),
            "ifczip": ("application/zip", "application/octet-stream"),
        }
        for variant_id, (content_mime, path_mime) in examples.items():
            self.assertEqual(by_id[variant_id]["content_media_type"], content_mime)
            self.assertEqual(by_id[variant_id]["expected_kcs_path_media_type"], path_mime)
        self.assertEqual(by_id["jsonl-gzip"]["compound_suffix_parts"], ["jsonl", "gz"])
        self.assertEqual(by_id["dicom-part10"]["filename_extension"], "dcm")
        for row in value["variant_rows"]:
            self.assertIs(row["renderer"]["implemented"], False)
            self.assertIs(row["validator"]["implemented"], False)
            self.assertIs(
                row["complexity_contract"]["feasibility_parameters_complete"],
                False,
            )
            if row["gate_role"] == "contract_contributor":
                self.assertEqual(
                    row["complexity_contract"]["quota_relation"],
                    "requested-chunk-quota-separate-from-format-complexity-formula-not-bound",
                )
                self.assertEqual(row["search_contract"]["requested_chunk_rule"], "integer-1-through-70")
            else:
                self.assertEqual(row["search_contract"]["requested_chunk_rule"], "exact-zero")
            self.assertIs(
                row["search_contract"]["contract_chunk_denominator_eligible"],
                row["gate_role"] == "contract_contributor",
            )
            self.assertIs(
                row["search_contract"]["incidental_cap_eligible"],
                row["gate_role"] == "incidental_searchable",
            )
            self.assertEqual(
                row["search_contract"]["observed_chunk_gate"],
                {
                    "contract_contributor": "actual-equals-assigned-quota",
                    "incidental_searchable": "actual-within-source-and-wave-cap",
                    "raw_only": "actual-equals-zero",
                }[row["gate_role"]],
            )
        self.assertIs(
            value["kcs_media_policy"]["cross_language_production_tables_verified"],
            False,
        )
        self.assertIn(
            "content-mime-versus-production-path-mime-cross-language-golden-missing",
            value["remaining_blockers"],
        )
        with self.assertRaises(catalog.PersonaV2VariantCatalogError):
            catalog.require_complete_variant_catalog()

    def test_all_variant_identities_exactly_join_the_envelope(self):
        value = catalog.build_variant_catalog()
        by_id = {row["variant_id"]: row for row in value["variant_rows"]}
        family_by_variant = {}
        for persona_id in envelope.PERSONA_IDS:
            for family, rows in envelope.variant_counts(persona_id, "full").items():
                for row in rows:
                    previous = family_by_variant.setdefault(row["variant_id"], family)
                    self.assertEqual(previous, family)
        self.assertEqual(set(by_id), set(envelope.VARIANT_CATALOG))
        self.assertEqual(set(family_by_variant), set(by_id))
        for variant_id, metadata in envelope.VARIANT_CATALOG.items():
            row = by_id[variant_id]
            self.assertEqual(row["family"], family_by_variant[variant_id])
            self.assertEqual(row["filename_extension"], metadata["extension"])
            self.assertEqual(row["expected_kcs_path_media_type"], metadata["media_type"])
            self.assertEqual(row["gate_role"], metadata["gate_role"])
            self.assertEqual(
                row["expected_offline_disposition"],
                metadata["expected_offline_disposition"],
            )
            self.assertEqual(row["renderer"]["renderer_id"], metadata["renderer_id"])
            self.assertEqual(
                row["renderer"]["renderer_schema_version"],
                metadata["renderer_schema_version"],
            )
            self.assertEqual(row["validator"]["validator_id"], metadata["validator_id"])
            self.assertEqual(
                row["validator"]["validator_schema_version"],
                metadata["validator_schema_version"],
            )
            self.assertEqual(
                row["validator"]["magic_and_structure_policy_id"],
                row["safety_profile_id"],
            )
            self.assertEqual(
                row["renderer"]["renderer_profile_id"],
                row["complexity_contract"]["complexity_profile_id"],
            )

        self.assertEqual(
            {
                role: sum(row["gate_role"] == role for row in value["variant_rows"])
                for role in ("contract_contributor", "incidental_searchable", "raw_only")
            },
            {"contract_contributor": 10, "incidental_searchable": 11, "raw_only": 50},
        )

    def test_all_content_media_types_and_compound_suffixes_are_exact(self):
        by_id = {
            row["variant_id"]: row
            for row in catalog.build_variant_catalog()["variant_rows"]
        }
        exact = {
            "aiff": "audio/aiff",
            "bmp": "image/bmp",
            "cpp": "text/x-c++src",
            "csv": "text/csv",
            "dicom-part10": "application/dicom",
            "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "eml": "message/rfc822",
            "go": "text/x-go",
            "html": "text/html",
            "ifczip": "application/zip",
            "ipynb": "application/x-ipynb+json",
            "jpg": "image/jpeg",
            "js": "text/javascript",
            "json": "application/json",
            "jsonl": "application/x-ndjson",
            "log": "text/plain",
            "markdown": "text/markdown",
            "md": "text/markdown",
            "mid": "audio/midi",
            "npz": "application/zip",
            "pcap": "application/vnd.tcpdump.pcap",
            "pdf-scan": "application/pdf",
            "pdf-text": "application/pdf",
            "png": "image/png",
            "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "py": "text/x-python",
            "rs": "text/x-rust",
            "sql": "application/sql",
            "tif": "image/tiff",
            "ts": "text/typescript",
            "tsv": "text/tab-separated-values",
            "txt": "text/plain",
            "wav": "audio/wav",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xml": "application/xml",
            "yaml": "application/yaml",
        }
        for variant_id, row in by_id.items():
            if variant_id in exact:
                expected = exact[variant_id]
            elif variant_id.endswith("-zip"):
                expected = "application/zip"
            elif variant_id.endswith("-ustar"):
                expected = "application/x-tar"
            elif variant_id.endswith("-gzip"):
                expected = "application/gzip"
            else:  # The exhaustive branch is itself part of the test.
                self.fail(f"unclassified content MIME: {variant_id}")
            self.assertEqual(row["content_media_type"], expected)
            self.assertEqual(
                row["compound_suffix_parts"],
                row["filename_extension"].split("."),
            )

    def test_format_specific_complexity_and_byte_lanes_are_separate(self):
        value = catalog.build_variant_catalog()
        by_id = {row["variant_id"]: row for row in value["variant_rows"]}
        expected_units = {
            "log": "log-records",
            "jsonl": "jsonl-records",
            "json": "json-nodes",
            "yaml": "yaml-nodes",
            "xml": "xml-elements",
            "sql": "sql-statements",
            "csv": "tabular-rows",
            "tsv": "tabular-rows",
            "html": "html-sections",
            "eml": "attachments",
            "ipynb": "notebook-cells",
        }
        for variant_id, unit in expected_units.items():
            self.assertEqual(
                by_id[variant_id]["complexity_contract"]["complexity_unit"],
                unit,
            )
        self.assertEqual(
            by_id["pdf-text"]["complexity_contract"]["maximum"],
            72,
        )
        self.assertEqual(by_id["eml"]["complexity_contract"]["minimum"], 0)
        self.assertEqual(by_id["eml"]["complexity_contract"]["maximum"], 5)

        formal = value["lane_contracts"]["formal_retrieval_history"]
        stress = value["lane_contracts"]["byte_stress"]
        self.assertEqual(formal["text_pdf_pages"], {"inclusive_minimum": 1, "inclusive_maximum": 72})
        self.assertEqual(formal["scan_pdf_pages"], {"inclusive_minimum": 1, "inclusive_maximum": 50})
        self.assertEqual(formal["eml_attachments"], {"inclusive_minimum": 0, "inclusive_maximum": 5})
        self.assertEqual(formal["xlsx_sheets"], {"inclusive_minimum": 1, "inclusive_maximum": 20})
        self.assertEqual(formal["pptx_slides"], {"inclusive_minimum": 1, "inclusive_maximum": 40})
        self.assertEqual(formal["image_media_domain_tail_bytes"]["max_files_per_persona"], 16)
        self.assertEqual(stress["cardinality_per_persona"], 64)
        self.assertEqual(stress["per_persona_payload_bytes"], 740 * 2**20)
        self.assertEqual(stress["per_persona_allocated_bytes_cap"], 768 * 2**20)
        self.assertEqual(stress["suite_allocated_bytes_cap"], 15 * 2**30)

        eligible = {
            row["variant_id"]
            for row in value["variant_rows"]
            if row["byte_contract"]["byte_stress_encoding_eligible"]
        }
        expected_eligible = {
            row["variant_id"]
            for row in value["variant_rows"]
            if row["family"] in {"image", "media", "domain_binary"}
        } | {"pdf-text", "pdf-scan", "eml", "xlsx", "pptx"}
        self.assertEqual(eligible, expected_eligible)
        self.assertEqual(len(eligible), 51)
        self.assertEqual(stress["lane_local_gate_role"], "raw_only")
        self.assertEqual(stress["lane_local_requested_chunks"], 0)
        self.assertEqual(
            stress["lane_local_observed_chunk_gate"],
            "actual-equals-zero",
        )
        self.assertIs(stress["projection_is_not_a_formal_variant_source_row"], True)
        for variant_id in ("docx", "xlsx", "pptx"):
            self.assertEqual(
                by_id[variant_id]["byte_contract"]["expanded_bytes_limit"],
                catalog.MAX_EXPANDED_CONTAINER_BYTES,
            )
            self.assertEqual(
                by_id[variant_id]["byte_contract"]["byte_distribution_profile_id"],
                "bounded-container-bytes-v2",
            )
        for row in value["variant_rows"]:
            self.assertIs(row["byte_contract"]["parameters_complete"], False)
            self.assertNotIn("formal_tail_max_files_per_persona", row["byte_contract"])
            classes = row["byte_contract"]["byte_stress_size_classes"]
            if not row["byte_contract"]["byte_stress_encoding_eligible"]:
                self.assertEqual(classes, [])
            elif row["byte_contract"]["expanded_bytes_limit"] == catalog.MAX_EXPANDED_CONTAINER_BYTES:
                self.assertEqual(classes, ["small", "medium"])
            else:
                self.assertEqual(classes, ["small", "medium", "large", "tail"])

    def test_balanced_tamper_cross_swap_strict_types_and_detachment_fail_closed(self):
        value = catalog.build_variant_catalog()
        balanced = copy.deepcopy(value)
        balanced["persona_variant_marginals"][0]["full_count"] += 1
        balanced["persona_variant_marginals"][1]["full_count"] -= 1
        with self.assertRaises(catalog.PersonaV2VariantCatalogError):
            catalog.validate_variant_catalog(balanced)

        swapped = copy.deepcopy(value)
        first, second = swapped["variant_rows"][0], swapped["variant_rows"][1]
        first["filename_extension"], second["filename_extension"] = (
            second["filename_extension"],
            first["filename_extension"],
        )
        with self.assertRaises(catalog.PersonaV2VariantCatalogError):
            catalog.validate_variant_catalog(swapped)

        for replacement in (True, 1.0, None, "e\u0301", "\ud800"):
            with self.subTest(replacement=repr(replacement)):
                tampered = catalog.build_variant_catalog()
                tampered["variant_rows"][0]["complexity_contract"]["maximum"] = replacement
                with self.assertRaises(catalog.PersonaV2VariantCatalogError):
                    catalog.validate_variant_catalog(tampered)

        value["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(catalog.build_variant_catalog()["variant_rows"][0]["variant_id"], "markdown")

    def test_hash_is_independent_and_v1_identity_is_unchanged(self):
        self.assertEqual(v1.SCHEMA_VERSION, 1)
        self.assertEqual(v1.FIXTURE_ID, "kcs-persona-pc-v1")
        script = (
            "from eval import persona_v2_variant_catalog as v; "
            "x=v.build_variant_catalog(); "
            "print(v.variant_catalog_sha256(x),len(v.canonical_json_bytes(x)))"
        )
        expected = None
        for seed, timezone in (("0", "UTC"), ("1", "Asia/Tokyo"), ("42", "UTC")):
            environment = os.environ.copy()
            environment.update(
                {"PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"}
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.getcwd(),
                env=environment,
                text=True,
            ).strip()
            if expected is None:
                expected = output
            self.assertEqual(output, expected)


if __name__ == "__main__":
    unittest.main()
