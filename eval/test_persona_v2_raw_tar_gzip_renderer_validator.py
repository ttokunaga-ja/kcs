import ast
import copy
from dataclasses import fields, replace
import gzip
import inspect
import io
import os
import subprocess
import sys
import tarfile
import unittest

from eval import persona_v2_raw_tar_gzip_renderer as renderer
from eval import persona_v2_raw_tar_gzip_validator as validator


EXPECTED_USTAR_VARIANTS = (
    "legal-hold-ustar",
    "lms-ustar",
    "maildir-ustar",
    "plm-ustar",
    "session-ustar",
    "snapshot-ustar",
    "source-drop-ustar",
    "source-ustar",
    "team-export-ustar",
    "tiff-ustar",
)

EXPECTED_GZIP_VARIANTS = (
    "assay-csv-gzip",
    "crm-jsonl-gzip",
    "csv-gzip",
    "erp-csv-gzip",
    "hris-jsonl-gzip",
    "jsonl-gzip",
)

EXPECTED_PROFILE_COUNTS = {
    "assay-csv-gzip": {"tiny-smoke": 2, "pilot": 10, "full": 96},
    "crm-jsonl-gzip": {"tiny-smoke": 1, "pilot": 10, "full": 96},
    "csv-gzip": {"tiny-smoke": 5, "pilot": 29, "full": 288},
    "erp-csv-gzip": {"tiny-smoke": 4, "pilot": 23, "full": 234},
    "hris-jsonl-gzip": {"tiny-smoke": 2, "pilot": 6, "full": 64},
    "jsonl-gzip": {"tiny-smoke": 7, "pilot": 52, "full": 525},
    "legal-hold-ustar": {"tiny-smoke": 2, "pilot": 6, "full": 63},
    "lms-ustar": {"tiny-smoke": 1, "pilot": 5, "full": 54},
    "maildir-ustar": {"tiny-smoke": 2, "pilot": 8, "full": 80},
    "plm-ustar": {"tiny-smoke": 5, "pilot": 29, "full": 288},
    "session-ustar": {"tiny-smoke": 1, "pilot": 5, "full": 54},
    "snapshot-ustar": {"tiny-smoke": 1, "pilot": 4, "full": 44},
    "source-drop-ustar": {"tiny-smoke": 1, "pilot": 6, "full": 60},
    "source-ustar": {"tiny-smoke": 2, "pilot": 11, "full": 108},
    "team-export-ustar": {"tiny-smoke": 1, "pilot": 2, "full": 24},
    "tiff-ustar": {"tiny-smoke": 1, "pilot": 4, "full": 42},
}


class PersonaV2RawTarGzipRendererValidatorTests(unittest.TestCase):
    def _render_and_validate(self, variant, complexity):
        rendered = renderer.render_raw_tar_gzip(
            renderer.RawTarGzipRenderRequest(2, variant, complexity)
        )
        receipt = validator.validate_raw_tar_gzip_payload(
            validator.RawTarGzipValidationRequest(
                schema_version=2,
                variant=variant,
                target_complexity=complexity,
                data=rendered.data,
                extension=rendered.extension,
                content_media_type=rendered.content_media_type,
                expected_kcs_path_media_type=(
                    rendered.expected_kcs_path_media_type
                ),
                expected_offline_disposition=(
                    rendered.expected_offline_disposition
                ),
            )
        )
        return rendered, receipt

    @staticmethod
    def _validation_request(rendered, variant, complexity):
        return validator.RawTarGzipValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )

    @staticmethod
    def _rewrite_tar_checksum(data, header_offset=0):
        changed = bytearray(data)
        header = bytearray(
            changed[
                header_offset : header_offset + renderer.USTAR_BLOCK_BYTES
            ]
        )
        header[148:156] = b"        "
        header[148:156] = f"{sum(header):06o}\0 ".encode("ascii")
        changed[
            header_offset : header_offset + renderer.USTAR_BLOCK_BYTES
        ] = header
        return bytes(changed)

    def test_exact_matrix_profile_counts_and_common_contract_rows(self):
        self.assertEqual(renderer.USTAR_VARIANTS, EXPECTED_USTAR_VARIANTS)
        self.assertEqual(renderer.GZIP_VARIANTS, EXPECTED_GZIP_VARIANTS)
        self.assertEqual(renderer.READY_VARIANTS, validator.READY_VARIANTS)
        self.assertEqual(len(renderer.READY_VARIANTS), 16)

        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        self.assertEqual(set(renderer_rows), set(EXPECTED_PROFILE_COUNTS))
        shared_fields = {
            "archive_format",
            "complexity",
            "content_media_type",
            "expected_kcs_path_media_type",
            "expected_offline_disposition",
            "family",
            "filename_extension",
            "gate_role",
            "profile_counts",
            "raw_byte_formula",
            "render_template",
            "size_quantization",
            "variant_id",
        }
        for variant in renderer.READY_VARIANTS:
            self.assertEqual(
                renderer_rows[variant]["profile_counts"],
                EXPECTED_PROFILE_COUNTS[variant],
            )
            self.assertEqual(
                {key: renderer_rows[variant][key] for key in shared_fields},
                {key: validator_rows[variant][key] for key in shared_fields},
            )
            self.assertEqual(renderer_rows[variant]["gate_role"], "raw_only")
            self.assertEqual(
                renderer_rows[variant]["expected_kcs_path_media_type"],
                "application/octet-stream",
            )
            self.assertEqual(
                renderer_rows[variant]["expected_offline_disposition"],
                "unsupported_binary",
            )

        totals = {
            profile: sum(
                counts[profile] for counts in EXPECTED_PROFILE_COUNTS.values()
            )
            for profile in renderer.PROFILE_ORDER
        }
        self.assertEqual(totals, {"tiny-smoke": 38, "pilot": 210, "full": 2_120})
        self.assertEqual(renderer.PROFILE_TOTALS, totals)
        self.assertEqual(validator.PROFILE_TOTALS, totals)

    def test_contract_pins_caps_detachment_and_negative_authority(self):
        renderer_contract = renderer.build_renderer_contract()
        validator_contract = validator.build_validator_contract()
        self.assertEqual(
            len(renderer.canonical_json_bytes(renderer_contract)), 14_589
        )
        self.assertEqual(
            renderer.renderer_contract_sha256(renderer_contract),
            "d23a9b29f4e26748f32f07e201c1294ede5cd4534a27533e9ddc9b88a01d8cb8",
        )
        self.assertEqual(
            len(validator.canonical_json_bytes(validator_contract)), 15_885
        )
        self.assertEqual(
            validator.validator_contract_sha256(validator_contract),
            "2e98faae761d7ae4aaaeba37a560d4e78dc3cc948551abde1acc399018d31bf6",
        )
        self.assertTrue(renderer.validate_renderer_contract(renderer_contract))
        self.assertTrue(validator.validate_validator_contract(validator_contract))
        for value in (renderer_contract, validator_contract):
            self.assertTrue(value["vertical_slice_implementation_available"])
            self.assertEqual(value["variant_count"], 16)
            self.assertLessEqual(
                len(
                    renderer.canonical_json_bytes(value)
                    if value is renderer_contract
                    else validator.canonical_json_bytes(value)
                ),
                value["canonical_limits"]["max_body_bytes"],
            )
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

        poisoned_renderer = copy.deepcopy(renderer_contract)
        poisoned_renderer["variant_rows"][0]["size_quantization"][
            "raw_size_quantum_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2RawTarGzipRendererError):
            renderer.validate_renderer_contract(poisoned_renderer)
        poisoned_validator = copy.deepcopy(validator_contract)
        poisoned_validator["authority"]["authorizes_physical_write"] = True
        with self.assertRaises(validator.PersonaV2RawTarGzipValidatorError):
            validator.validate_validator_contract(poisoned_validator)

        renderer_contract["variant_rows"][0]["variant_id"] = "poisoned"
        validator_contract["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "assay-csv-gzip",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "assay-csv-gzip",
        )

    def test_canonical_contract_helpers_match_shared_strict_plain_value_rules(self):
        deep = "leaf"
        for _ in range(66):
            deep = [deep]

        class DictAlias(dict):
            pass

        invalid_values = (
            None,
            -1,
            2**127,
            "\ud800",
            {"nullable": None},
            {1: "non-string-key"},
            ("tuple",),
            DictAlias({"alias": True}),
            "x" * 4_097,
            deep,
        )
        for module, error_type in (
            (renderer, renderer.PersonaV2RawTarGzipRendererError),
            (validator, validator.PersonaV2RawTarGzipValidatorError),
        ):
            for value in invalid_values:
                with self.subTest(module=module.__name__, value=repr(value)[:80]):
                    with self.assertRaises(error_type):
                        module.canonical_json_bytes(value)

    def test_request_and_rendered_schemas_are_identity_free(self):
        forbidden = set(renderer.PROHIBITED_IDENTITY_FIELDS)
        self.assertEqual(
            tuple(field.name for field in fields(renderer.RawTarGzipRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(
                field.name
                for field in fields(validator.RawTarGzipValidationRequest)
            ),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(set(renderer.REQUEST_FIELDS) & forbidden)
        self.assertFalse(set(validator.REQUEST_FIELDS) & forbidden)
        self.assertFalse(
            {field.name for field in fields(renderer.RenderedRawTarGzip)}
            & forbidden
        )

        valid = renderer.RawTarGzipRenderRequest(2, "source-ustar", 1)
        invalid = (
            replace(valid, schema_version=True),
            replace(valid, schema_version=1),
            replace(valid, variant=[]),
            replace(valid, variant="source-export-zip"),
            replace(valid, target_complexity=True),
            replace(valid, target_complexity=0),
            replace(valid, target_complexity=65),
        )
        for request in invalid:
            with self.subTest(request=repr(request)):
                with self.assertRaises(renderer.PersonaV2RawTarGzipRendererError):
                    renderer.render_raw_tar_gzip(request)

    def test_malicious_variant_subclass_and_equality_impostor_fail_closed(self):
        class MaliciousVariant(str):
            def __format__(self, format_spec):
                return "p99-src-999999"

        class EqualityImpostor:
            def __eq__(self, other):
                return other == "source-ustar"

            def __hash__(self):
                return hash("source-ustar")

            def __format__(self, format_spec):
                return "p99-src-999999"

        bad_variants = (
            MaliciousVariant("source-ustar"),
            EqualityImpostor(),
        )
        rendered = renderer.render_raw_tar_gzip(
            renderer.RawTarGzipRenderRequest(2, "source-ustar", 1)
        )
        valid_validation = self._validation_request(
            rendered, "source-ustar", 1
        )
        for bad_variant in bad_variants:
            with self.subTest(kind=type(bad_variant).__name__):
                with self.assertRaises(
                    renderer.PersonaV2RawTarGzipRendererError
                ):
                    renderer.render_raw_tar_gzip(
                        renderer.RawTarGzipRenderRequest(
                            2, bad_variant, 1
                        )
                    )
                with self.assertRaises(
                    renderer.PersonaV2RawTarGzipRendererError
                ):
                    renderer.target_bytes_for(bad_variant, 1)
                with self.assertRaises(
                    validator.PersonaV2RawTarGzipValidatorError
                ):
                    validator.validate_raw_tar_gzip_payload(
                        replace(valid_validation, variant=bad_variant)
                    )

        receipt = validator.validate_raw_tar_gzip_payload(valid_validation)
        self.assertIs(type(receipt["variant_id"]), str)
        canonical = next(
            variant
            for variant in validator.READY_VARIANTS
            if variant == "source-ustar"
        )
        self.assertIs(receipt["variant_id"], canonical)

    def test_all_variants_minimum_and_maximum_are_deterministic_and_valid(self):
        rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        for variant in renderer.READY_VARIANTS:
            row = rows[variant]
            for complexity in (
                row["complexity"]["inclusive_minimum"],
                row["complexity"]["inclusive_maximum"],
            ):
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(
                        variant, complexity
                    )
                    second = renderer.render_raw_tar_gzip(
                        renderer.RawTarGzipRenderRequest(
                            2, variant, complexity
                        )
                    )
                    self.assertEqual(first, second)
                    self.assertEqual(
                        len(first.data),
                        renderer.target_bytes_for(variant, complexity),
                    )
                    self.assertEqual(first.target_bytes, len(first.data))
                    self.assertEqual(
                        first.expanded_bytes,
                        renderer.expanded_bytes_for(variant, complexity),
                    )
                    self.assertEqual(
                        receipt["observed_complexity"], complexity
                    )
                    self.assertEqual(
                        receipt["observed_expanded_bytes"],
                        first.expanded_bytes,
                    )
                    self.assertFalse(receipt["raw_only_zero_chunks_attested"])
                    self.assertTrue(
                        all(flag is False for flag in receipt["authority"].values())
                    )

                    if variant in renderer.USTAR_VARIANTS:
                        with tarfile.open(
                            fileobj=io.BytesIO(first.data), mode="r:"
                        ) as archive:
                            members = archive.getmembers()
                            self.assertEqual(len(members), complexity)
                            self.assertTrue(all(member.isreg() for member in members))
                            self.assertTrue(
                                all(
                                    member.size
                                    == renderer.USTAR_MEMBER_PAYLOAD_BYTES
                                    for member in members
                                )
                            )
                    else:
                        expanded = gzip.decompress(first.data)
                        self.assertEqual(len(expanded), first.expanded_bytes)
                        self.assertEqual(
                            len(expanded.splitlines()), complexity
                        )

    def test_p1_ustar_formula_quantization_headers_and_terminal_blocks(self):
        for variant in renderer.USTAR_VARIANTS:
            previous = None
            for complexity in (1, 2, 64):
                rendered, receipt = self._render_and_validate(
                    variant, complexity
                )
                self.assertEqual(
                    len(rendered.data), 1_024 + 1_024 * complexity
                )
                self.assertEqual(
                    len(rendered.data) % renderer.USTAR_BLOCK_BYTES, 0
                )
                self.assertEqual(rendered.size_quantum_bytes, 512)
                self.assertEqual(
                    rendered.data[-1_024:], bytes(1_024)
                )
                self.assertEqual(rendered.data[257:263], b"ustar\0")
                self.assertEqual(receipt["observed_complexity_measure"], "members")
                if previous is not None:
                    self.assertEqual(len(rendered.data) - previous, (complexity - 2) * 1_024 if complexity == 64 else 1_024)
                previous = len(rendered.data)

    def test_p2_gzip_stored_formula_crc_isize_and_expansion_bound(self):
        for variant in renderer.GZIP_VARIANTS:
            for complexity in (1, 2, 4_096):
                rendered, receipt = self._render_and_validate(
                    variant, complexity
                )
                self.assertEqual(len(rendered.data), 18 + 69 * complexity)
                self.assertEqual(
                    rendered.expanded_bytes, 64 * complexity
                )
                self.assertLessEqual(
                    rendered.expanded_bytes, renderer.GZIP_MAX_EXPANDED_BYTES
                )
                self.assertLessEqual(
                    len(rendered.data), renderer.MAX_RENDERED_BYTES
                )
                self.assertEqual(rendered.data[:10], renderer.GZIP_HEADER_BYTES)
                self.assertEqual(
                    int.from_bytes(rendered.data[-4:], "little"),
                    rendered.expanded_bytes,
                )
                self.assertEqual(receipt["observed_complexity_measure"], "records")

    def test_ustar_truncation_header_checksum_path_member_and_type_tampering_fail(self):
        rendered = renderer.render_raw_tar_gzip(
            renderer.RawTarGzipRenderRequest(2, "source-ustar", 2)
        )
        valid = self._validation_request(rendered, "source-ustar", 2)

        bad_checksum = bytearray(rendered.data)
        bad_checksum[10] ^= 1

        bad_magic = bytearray(rendered.data)
        bad_magic[257] = ord("x")
        bad_magic = self._rewrite_tar_checksum(bad_magic)

        unsafe_path = bytearray(rendered.data)
        unsafe_path[:100] = bytes(100)
        unsafe_path[:13] = b"../escape.dat"
        unsafe_path = self._rewrite_tar_checksum(unsafe_path)

        wrong_type = bytearray(rendered.data)
        wrong_type[156] = ord("5")
        wrong_type = self._rewrite_tar_checksum(wrong_type)

        bad_terminal = bytearray(rendered.data)
        bad_terminal[-1] = 1

        wrong_member_count = replace(valid, target_complexity=1)
        invalid = (
            replace(valid, data=rendered.data[:-1]),
            replace(valid, data=bytes(bad_checksum)),
            replace(valid, data=bad_magic),
            replace(valid, data=unsafe_path),
            replace(valid, data=wrong_type),
            replace(valid, data=bytes(bad_terminal)),
            wrong_member_count,
        )
        for request in invalid:
            with self.subTest(case=len(request.data)):
                with self.assertRaises(
                    validator.PersonaV2RawTarGzipValidatorError
                ):
                    validator.validate_raw_tar_gzip_payload(request)

    def test_gzip_truncation_header_block_crc_isize_and_metadata_tampering_fail(self):
        rendered = renderer.render_raw_tar_gzip(
            renderer.RawTarGzipRenderRequest(2, "jsonl-gzip", 2)
        )
        valid = self._validation_request(rendered, "jsonl-gzip", 2)
        bad_header = bytearray(rendered.data)
        bad_header[3] = 1
        bad_final = bytearray(rendered.data)
        bad_final[10] = 1
        bad_length = bytearray(rendered.data)
        bad_length[11:13] = (65).to_bytes(2, "little")
        bad_crc = bytearray(rendered.data)
        bad_crc[-8] ^= 1
        bad_isize = bytearray(rendered.data)
        bad_isize[-4:] = (1).to_bytes(4, "little")
        invalid = (
            replace(valid, data=rendered.data[:-1]),
            replace(valid, data=bytes(bad_header)),
            replace(valid, data=bytes(bad_final)),
            replace(valid, data=bytes(bad_length)),
            replace(valid, data=bytes(bad_crc)),
            replace(valid, data=bytes(bad_isize)),
            replace(valid, data=bytearray(rendered.data)),
            replace(valid, extension="jsonl"),
            replace(valid, content_media_type="application/octet-stream"),
            replace(valid, expected_kcs_path_media_type="application/gzip"),
            replace(valid, expected_offline_disposition="incidental_sniff"),
        )
        for request in invalid:
            with self.subTest(request=repr(request)[:120]):
                with self.assertRaises(
                    validator.PersonaV2RawTarGzipValidatorError
                ):
                    validator.validate_raw_tar_gzip_payload(request)

    def test_modules_are_stdlib_only_independent_and_have_no_write_path(self):
        renderer_source = inspect.getsource(renderer)
        validator_source = inspect.getsource(validator)
        for forbidden in (
            "persona_v2_variant_catalog",
            "persona_v2_contract",
            "persona_v2_raw_tar_gzip_validator",
        ):
            self.assertNotIn(forbidden, renderer_source)
        for forbidden in (
            "persona_v2_variant_catalog",
            "persona_v2_contract",
            "persona_v2_raw_tar_gzip_renderer",
        ):
            self.assertNotIn(forbidden, validator_source)
        self.assertNotIn("open(", renderer_source)
        self.assertNotIn("open(", validator_source)
        self.assertNotIn(".write(", renderer_source)
        self.assertNotIn(".write(", validator_source)

        allowed_import_roots = {
            "",
            "__future__",
            "copy",
            "csv",
            "dataclasses",
            "io",
            "json",
            "persona_v2_artifact_common",
            "zlib",
        }
        for module in (renderer, validator):
            tree = ast.parse(inspect.getsource(module))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    imported.add((node.module or "").split(".")[0])
            self.assertLessEqual(imported, allowed_import_roots)

    def test_hashseed_timezone_and_locale_do_not_change_contracts_or_payloads(self):
        script = (
            "import hashlib; "
            "from eval import persona_v2_raw_tar_gzip_renderer as r; "
            "from eval import persona_v2_raw_tar_gzip_validator as v; "
            "parts=[r.renderer_contract_sha256(),v.validator_contract_sha256()]; "
            "parts += [hashlib.sha256(r.render_raw_tar_gzip("
            "r.RawTarGzipRenderRequest(2,x,64 if x.endswith('-ustar') else 4096)"
            ").data).hexdigest() for x in r.READY_VARIANTS]; "
            "print(' '.join(parts))"
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
