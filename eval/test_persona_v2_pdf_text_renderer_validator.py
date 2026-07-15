import copy
from dataclasses import fields, replace
import hashlib
import inspect
import os
import re
import subprocess
import sys
import unittest

from eval import persona_v2_pdf_text_renderer as renderer
from eval import persona_v2_pdf_text_validator as validator


class PersonaV2PdfTextRendererValidatorTests(unittest.TestCase):
    def _render_and_validate(self, complexity):
        rendered = renderer.render_pdf_text(
            renderer.PdfTextRenderRequest(2, "pdf-text", complexity)
        )
        receipt = validator.validate_pdf_text_payload(
            validator.PdfTextValidationRequest(
                schema_version=2,
                variant="pdf-text",
                target_complexity=complexity,
                data=rendered.data,
                extension=rendered.extension,
                content_media_type=rendered.content_media_type,
                expected_kcs_path_media_type=rendered.expected_kcs_path_media_type,
                expected_offline_disposition=rendered.expected_offline_disposition,
            )
        )
        return rendered, receipt

    def _validation_request(self, complexity=4):
        rendered = renderer.render_pdf_text(
            renderer.PdfTextRenderRequest(2, "pdf-text", complexity)
        )
        return validator.PdfTextValidationRequest(
            2,
            "pdf-text",
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )

    def _assert_xref(self, data, page_count):
        match = re.search(rb"startxref\n([0-9]+)\n%%EOF\n\Z", data)
        self.assertIsNotNone(match)
        xref_offset = int(match.group(1))
        self.assertEqual(data[xref_offset:xref_offset + 5], b"xref\n")
        object_count = 3 + 2 * page_count
        lines = data[xref_offset:].splitlines()
        self.assertEqual(lines[1], f"0 {object_count + 1}".encode("ascii"))
        self.assertEqual(lines[2], b"0000000000 65535 f ")
        for object_number in range(1, object_count + 1):
            entry = lines[2 + object_number]
            self.assertRegex(entry, rb"^[0-9]{10} 00000 n $")
            offset = int(entry[:10])
            self.assertTrue(
                data.startswith(
                    f"{object_number} 0 obj\n".encode("ascii"), offset
                )
            )
        trailer_index = 3 + object_count
        self.assertEqual(
            lines[trailer_index:trailer_index + 5],
            [
                b"trailer",
                f"<< /Size {object_count + 1} /Root 1 0 R >>".encode("ascii"),
                b"startxref",
                str(xref_offset).encode("ascii"),
                b"%%EOF",
            ],
        )

    def test_contract_hash_size_caps_and_negative_authority_are_exact(self):
        renderer_value = renderer.build_renderer_contract()
        validator_value = validator.build_validator_contract()
        self.assertEqual(len(renderer.canonical_json_bytes(renderer_value)), 2_075)
        self.assertEqual(
            renderer.renderer_contract_sha256(renderer_value),
            "ab66e11d93e2aa7896bdffd28f1c1fec9f443a4ff3b48ba6dcc4d1c12bab69f6",
        )
        self.assertEqual(len(validator.canonical_json_bytes(validator_value)), 2_233)
        self.assertEqual(
            validator.validator_contract_sha256(validator_value),
            "78c90d4cccb254f67bc030e79eaef46704ce4d8555a3edc8f42edc293e91805e",
        )
        self.assertTrue(renderer.validate_renderer_contract(renderer_value))
        self.assertTrue(validator.validate_validator_contract(validator_value))
        for value in (renderer_value, validator_value):
            self.assertTrue(value["vertical_slice_implementation_available"])
            self.assertEqual(value["variant_count"], 1)
            self.assertEqual(value["variant_rows"][0]["variant_id"], "pdf-text")
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

    def test_request_payload_and_module_boundaries_are_identity_free(self):
        forbidden = set(renderer.PROHIBITED_IDENTITY_FIELDS)
        self.assertEqual(
            tuple(field.name for field in fields(renderer.PdfTextRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(field.name for field in fields(validator.PdfTextValidationRequest)),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(set(renderer.REQUEST_FIELDS) & forbidden)
        self.assertFalse(set(validator.REQUEST_FIELDS) & forbidden)
        self.assertFalse(
            {field.name for field in fields(renderer.RenderedPdfText)} & forbidden
        )

        renderer_source = inspect.getsource(renderer)
        validator_source = inspect.getsource(validator)
        self.assertNotIn("import persona_renderers", renderer_source)
        self.assertNotIn("from . import persona_renderers", renderer_source)
        self.assertNotIn("import persona_v2_pdf_text_validator", renderer_source)
        self.assertNotIn("import persona_v2_pdf_text_renderer", validator_source)
        self.assertNotIn("urllib", renderer_source)
        self.assertNotIn("urllib", validator_source)
        self.assertNotIn("requests", renderer_source)
        self.assertNotIn("requests", validator_source)
        self.assertNotIn("socket", renderer_source)
        self.assertNotIn("socket", validator_source)

    def test_all_72_complexities_have_exact_affine_bytes_and_valid_structure(self):
        forbidden_payload = re.compile(
            rb"(?:"
            rb"p[0-9]{2}-src-[0-9]{6}|"
            rb"(?:persona|scope|source|intent|materialization|query)"
            rb"[_-]?(?:id|key)\s*[:=]|"
            rb"sha256:|[0-9a-f]{64}"
            rb")",
            re.IGNORECASE,
        )
        previous_length = None
        for complexity in range(1, 73):
            with self.subTest(complexity=complexity):
                first, receipt = self._render_and_validate(complexity)
                second = renderer.render_pdf_text(
                    renderer.PdfTextRenderRequest(2, "pdf-text", complexity)
                )
                self.assertEqual(first, second)
                self.assertEqual(
                    len(first.data), renderer.target_bytes_for(complexity)
                )
                self.assertEqual(first.target_bytes, len(first.data))
                self.assertEqual(
                    receipt["observed_local_complexity"], complexity
                )
                self.assertEqual(
                    receipt["observed_complexity_measure"], "text-pages"
                )
                self.assertEqual(receipt["object_count"], 3 + 2 * complexity)
                self.assertEqual(receipt["target_bytes"], len(first.data))
                self.assertTrue(receipt["text_layer_validated"])
                self.assertTrue(receipt["xref_validated"])
                self.assertTrue(receipt["trailer_validated"])
                self.assertFalse(receipt["actual_chunks_attested"])
                self.assertFalse(receipt["kcs_execution_attested"])
                self.assertEqual(first.data.count(b"stream\nBT\n"), complexity)
                self.assertEqual(first.data.count(b"%%EOF\n"), 1)
                self.assertLessEqual(
                    max(len(line) for line in first.data.split(b"\n")),
                    255,
                )
                self.assertIsNone(forbidden_payload.search(first.data))
                self._assert_xref(first.data, complexity)
                if previous_length is not None:
                    self.assertEqual(
                        len(first.data) - previous_length,
                        renderer.FORMULA_INCREMENT_BYTES_PER_ADDITIONAL_COMPLEXITY,
                    )
                previous_length = len(first.data)

    def test_exact_payload_hash_pins_cover_low_middle_and_high_complexity(self):
        expected = {
            1: (
                4_096,
                "5746634bb33cd818205a4965e5136aa5f535c8814015fac1b56240829e75ac23",
            ),
            2: (
                6_144,
                "7c3357a60d5faac72d2deb21cac01244a872157751f4d738f212d8dd948bf8c8",
            ),
            36: (
                75_776,
                "b3350a2f050f7fb759c31dde4b4475ccacc2c97e8c6d60a5b0943c8c02184527",
            ),
            72: (
                149_504,
                "ceb78099be13caa523f52e3b46392e921bf05f836e6dceb44ae55f6bff8917e5",
            ),
        }
        for complexity, (byte_length, digest) in expected.items():
            with self.subTest(complexity=complexity):
                rendered, _ = self._render_and_validate(complexity)
                self.assertEqual(len(rendered.data), byte_length)
                self.assertEqual(hashlib.sha256(rendered.data).hexdigest(), digest)

    def test_exact_pdf_and_local_pdf_text_metadata(self):
        rendered, receipt = self._render_and_validate(1)
        self.assertEqual(
            (
                rendered.extension,
                rendered.content_media_type,
                rendered.expected_kcs_path_media_type,
                rendered.expected_offline_disposition,
            ),
            ("pdf", "application/pdf", "application/pdf", "local_pdf_text"),
        )
        self.assertTrue(rendered.data.startswith(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"))
        self.assertIn(b"/Type /Catalog", rendered.data)
        self.assertIn(b"/Type /Pages\n/Count 1", rendered.data)
        self.assertIn(b"/Type /Font /Subtype /Type1", rendered.data)
        self.assertIn(b"BT\n/F1 10 Tf", rendered.data)
        self.assertTrue(receipt["pdf_header_validated"])
        self.assertTrue(receipt["page_tree_validated"])
        for value in (
            renderer.build_renderer_contract(),
            validator.build_validator_contract(),
        ):
            self.assertEqual(
                value["language_coverage"]["content_profile"],
                "ascii-uncompressed-literal-text-only",
            )
            self.assertFalse(
                value["language_coverage"]["multilingual_text_layer_proved"]
            )
            self.assertFalse(
                value["language_coverage"][
                    "locale_language_query_coverage_proved"
                ]
            )

    def test_renderer_and_validator_contract_rows_agree_on_shared_facts(self):
        renderer_row = renderer.build_renderer_contract()["variant_rows"][0]
        validator_row = validator.build_validator_contract()["variant_rows"][0]
        shared = {
            "complexity",
            "content_media_type",
            "expected_kcs_path_media_type",
            "expected_offline_disposition",
            "family",
            "filename_extension",
            "gate_role",
            "raw_byte_formula",
            "render_template",
            "variant_id",
        }
        self.assertEqual(
            {key: renderer_row[key] for key in shared},
            {key: validator_row[key] for key in shared},
        )
        self.assertEqual(
            renderer_row["raw_byte_formula"],
            {
                "base_bytes_at_complexity_one": 4_096,
                "increment_bytes_per_additional_complexity": 2_048,
                "maximum_rendered_bytes": 149_504,
                "minimum_rendered_bytes": 4_096,
            },
        )

    def test_invalid_requests_metadata_and_contract_tampering_fail_closed(self):
        valid_render = renderer.PdfTextRenderRequest(2, "pdf-text", 4)
        invalid_render_requests = (
            replace(valid_render, schema_version=True),
            replace(valid_render, schema_version=1),
            replace(valid_render, variant=[]),
            replace(valid_render, variant="pdf-scan"),
            replace(valid_render, target_complexity=True),
            replace(valid_render, target_complexity=0),
            replace(valid_render, target_complexity=73),
        )
        for request in invalid_render_requests:
            with self.subTest(request=repr(request)):
                with self.assertRaises(renderer.PersonaV2PdfTextRendererError):
                    renderer.render_pdf_text(request)

        valid_validation = self._validation_request(4)
        invalid_validation_requests = (
            replace(valid_validation, schema_version=True),
            replace(valid_validation, variant="pdf-scan"),
            replace(valid_validation, target_complexity=True),
            replace(valid_validation, target_complexity=0),
            replace(valid_validation, target_complexity=73),
            replace(valid_validation, data=bytearray(valid_validation.data)),
            replace(valid_validation, extension="txt"),
            replace(valid_validation, content_media_type="text/plain"),
            replace(valid_validation, expected_kcs_path_media_type="text/plain"),
            replace(valid_validation, expected_offline_disposition="local_text"),
        )
        for request in invalid_validation_requests:
            with self.subTest(request=repr(request)):
                with self.assertRaises(validator.PersonaV2PdfTextValidatorError):
                    validator.validate_pdf_text_payload(request)

        renderer_contract = renderer.build_renderer_contract()
        forged_renderer = copy.deepcopy(renderer_contract)
        forged_renderer["variant_rows"][0]["raw_byte_formula"][
            "maximum_rendered_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2PdfTextRendererError):
            renderer.validate_renderer_contract(forged_renderer)

        validator_contract = validator.build_validator_contract()
        forged_validator = copy.deepcopy(validator_contract)
        forged_validator["independence_contract"]["validates_xref_and_trailer"] = False
        with self.assertRaises(validator.PersonaV2PdfTextValidatorError):
            validator.validate_validator_contract(forged_validator)

        renderer_contract["variant_rows"][0]["variant_id"] = "poisoned"
        validator_contract["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "pdf-text",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "pdf-text",
        )

    def test_structural_formula_content_and_identity_mutations_fail_closed(self):
        valid = self._validation_request(4)
        data = valid.data
        xref_offset = int(
            re.search(rb"startxref\n([0-9]+)\n%%EOF\n\Z", data).group(1)
        )

        mutations = []
        mutations.append(data.replace(b"%PDF-1.4", b"%PDF-1.3", 1))
        mutations.append(data.replace(b"/Count 4", b"/Count 5", 1))
        mutations.append(data.replace(b"page 002", b"page 099", 1))
        mutations.append(data.replace(b"BT\n/F1", b"BX\n/F1", 1))
        mutations.append(data.replace(b"/Root 1 0 R", b"/Root 2 0 R", 1))

        xref_lines = data[xref_offset:].splitlines(keepends=True)
        first_entry_start = xref_offset + sum(len(line) for line in xref_lines[:3])
        changed_xref = bytearray(data)
        digit_index = first_entry_start + 9
        changed_xref[digit_index] = (
            ord("0") if changed_xref[digit_index] != ord("0") else ord("1")
        )
        mutations.append(bytes(changed_xref))

        startxref_match = re.search(rb"startxref\n([0-9]+)\n%%EOF\n\Z", data)
        changed_pointer = bytearray(data)
        digit_index = startxref_match.start(1) + len(startxref_match.group(1)) - 1
        changed_pointer[digit_index] = (
            ord("0") if changed_pointer[digit_index] != ord("0") else ord("1")
        )
        mutations.append(bytes(changed_pointer))

        last_object_end = data.rfind(b"endobj\n", 0, xref_offset) + len(b"endobj\n")
        self.assertEqual(data[last_object_end:last_object_end + 2], b"%.")
        bad_padding = bytearray(data)
        bad_padding[last_object_end + 1] = ord("x")
        mutations.append(bytes(bad_padding))

        for token in (b"query_id=x", b"p01-src-000001", b"a" * 64, b"/JavaScript"):
            injected = bytearray(data)
            start = last_object_end + 1
            injected[start:start + len(token)] = token
            mutations.append(bytes(injected))

        mutations.extend((data[:-1], data + b"\n"))
        self.assertEqual(len({mutation for mutation in mutations}), len(mutations))
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                with self.assertRaises(validator.PersonaV2PdfTextValidatorError):
                    validator.validate_pdf_text_payload(
                        replace(valid, data=mutation)
                    )

    def test_oversized_decimal_tokens_fail_with_the_contract_error(self):
        valid = self._validation_request(4)
        data = valid.data
        startxref_match = re.search(
            rb"startxref\n([0-9]+)\n%%EOF\n\Z", data
        )
        self.assertIsNotNone(startxref_match)
        xref_offset = int(startxref_match.group(1))
        last_object_end = (
            data.rfind(b"endobj\n", 0, xref_offset) + len(b"endobj\n")
        )
        for decimal_digits in (7, 5_000):
            with self.subTest(decimal_digits=decimal_digits):
                oversized = b"9" * decimal_digits
                removed_padding_bytes = len(oversized) - len(
                    startxref_match.group(1)
                )
                self.assertGreater(
                    xref_offset - last_object_end,
                    removed_padding_bytes + 2,
                )
                mutated = (
                    data[: last_object_end + 1]
                    + data[
                        last_object_end
                        + 1
                        + removed_padding_bytes : startxref_match.start(1)
                    ]
                    + oversized
                    + data[startxref_match.end(1) :]
                )
                self.assertEqual(len(mutated), len(data))
                with self.assertRaises(validator.PersonaV2PdfTextValidatorError):
                    validator.validate_pdf_text_payload(
                        replace(valid, data=mutated)
                    )

    def test_hashseed_timezone_and_locale_do_not_change_contracts_or_payloads(self):
        script = (
            "import hashlib; "
            "from eval import persona_v2_pdf_text_renderer as r; "
            "from eval import persona_v2_pdf_text_validator as v; "
            "h=hashlib.sha256(); "
            "[h.update(r.render_pdf_text(r.PdfTextRenderRequest(2,'pdf-text',n)).data) "
            "for n in range(1,73)]; "
            "print(r.renderer_contract_sha256(),v.validator_contract_sha256(),h.hexdigest())"
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
