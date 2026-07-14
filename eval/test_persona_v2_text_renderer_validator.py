import ast
import copy
from dataclasses import fields, replace
import inspect
import os
import re
import subprocess
import sys
import unittest

from eval import persona_v2_text_renderer as renderer
from eval import persona_v2_text_validator as validator


class PersonaV2TextRendererValidatorTests(unittest.TestCase):
    def _render_and_validate(self, variant, complexity):
        rendered = renderer.render_text(
            renderer.TextRenderRequest(2, variant, complexity)
        )
        receipt = validator.validate_text_payload(
            validator.TextValidationRequest(
                schema_version=2,
                variant=variant,
                target_complexity=complexity,
                data=rendered.data,
                extension=rendered.extension,
                content_media_type=rendered.content_media_type,
                expected_kcs_path_media_type=rendered.expected_kcs_path_media_type,
                expected_offline_disposition=rendered.expected_offline_disposition,
            )
        )
        return rendered, receipt

    def test_contract_hash_size_caps_and_negative_authority_are_exact(self):
        renderer_value = renderer.build_renderer_contract()
        validator_value = validator.build_validator_contract()
        self.assertEqual(len(renderer.canonical_json_bytes(renderer_value)), 5_976)
        self.assertEqual(
            renderer.renderer_contract_sha256(renderer_value),
            "c9c5b93f61e2da72e1ddc20867d97c52d0a525f4b273427016c625ca21f04056",
        )
        self.assertEqual(len(validator.canonical_json_bytes(validator_value)), 6_557)
        self.assertEqual(
            validator.validator_contract_sha256(validator_value),
            "a5c2bcbf73f4add58b2b4b7543840f1451dad3c6ec7503106b861be9d21675b3",
        )
        self.assertTrue(renderer.validate_renderer_contract(renderer_value))
        self.assertTrue(validator.validate_validator_contract(validator_value))
        for value in (renderer_value, validator_value):
            self.assertTrue(value["vertical_slice_implementation_available"])
            self.assertLessEqual(
                len(
                    renderer.canonical_json_bytes(value)
                    if value is renderer_value
                    else validator.canonical_json_bytes(value)
                ),
                value["canonical_limits"]["max_body_bytes"],
            )
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

    def test_request_and_payload_schemas_cannot_carry_internal_identity(self):
        forbidden = set(renderer.PROHIBITED_IDENTITY_FIELDS)
        self.assertEqual(
            tuple(field.name for field in fields(renderer.TextRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(field.name for field in fields(validator.TextValidationRequest)),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(set(renderer.REQUEST_FIELDS) & forbidden)
        self.assertFalse(set(validator.REQUEST_FIELDS) & forbidden)
        self.assertFalse(
            {field.name for field in fields(renderer.RenderedText)} & forbidden
        )

        renderer_source = inspect.getsource(renderer)
        validator_source = inspect.getsource(validator)
        self.assertNotIn("import persona_renderers", renderer_source)
        self.assertNotIn("import persona_v2_text_validator", renderer_source)
        self.assertNotIn("import persona_v2_text_renderer", validator_source)
        self.assertNotIn("from . import persona_v2_contract", renderer_source)
        self.assertNotIn("from . import persona_v2_contract", validator_source)

    def test_all_nine_variants_and_all_complexities_satisfy_exact_formulas(self):
        self.assertEqual(renderer.READY_VARIANTS, validator.READY_VARIANTS)
        self.assertEqual(len(renderer.READY_VARIANTS), 9)
        forbidden_payload = re.compile(
            rb"(?:p[0-9]{2}-src-[0-9]{6}|sha256:|[0-9a-f]{64})",
            re.IGNORECASE,
        )
        for variant in renderer.READY_VARIANTS:
            previous_target = None
            for complexity in range(1, 71):
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(
                        variant, complexity
                    )
                    second = renderer.render_text(
                        renderer.TextRenderRequest(2, variant, complexity)
                    )
                    self.assertEqual(first, second)
                    self.assertEqual(
                        len(first.data),
                        renderer.target_bytes_for(variant, complexity),
                    )
                    self.assertEqual(first.target_bytes, len(first.data))
                    self.assertEqual(
                        receipt["observed_local_complexity"], complexity
                    )
                    self.assertEqual(receipt["target_bytes"], len(first.data))
                    self.assertFalse(receipt["actual_chunks_attested"])
                    self.assertFalse(receipt["kcs_execution_attested"])
                    self.assertIsNone(forbidden_payload.search(first.data))
                    if previous_target is not None:
                        profile = next(
                            row
                            for row in renderer.build_renderer_contract()["variant_rows"]
                            if row["variant_id"] == variant
                        )
                        self.assertEqual(
                            len(first.data) - previous_target,
                            profile["raw_byte_formula"][
                                "increment_bytes_per_additional_complexity"
                            ],
                        )
                    previous_target = len(first.data)

    def test_heading_and_code_complexity_are_structurally_exact(self):
        for variant in ("md", "markdown", "txt"):
            rendered, _ = self._render_and_validate(variant, 70)
            text = rendered.data.decode("ascii")
            self.assertEqual(
                sum(line.startswith("## ") for line in text.splitlines()),
                70,
            )
            self.assertLessEqual(
                max(len(section) for section in re.split(r"(?m)(?=^## )", text) if section),
                renderer.CHUNKING_MAX_CHARS,
            )

        for variant in ("cpp", "go", "js", "py", "rs", "ts"):
            rendered, receipt = self._render_and_validate(variant, 70)
            text = rendered.data.decode("ascii")
            normalized = f"```{variant}\n{text.rstrip(chr(10))}\n```\n"
            self.assertNotIn("\n\n", normalized)
            self.assertEqual(
                len(normalized),
                69 * renderer.CHUNKING_MAX_CHARS
                + renderer.CODE_LAST_NORMALIZED_CHARS,
            )
            self.assertEqual(
                receipt["observed_complexity_measure"],
                "normalized-hard-split-spans",
            )
        ast.parse(
            renderer.render_text(renderer.TextRenderRequest(2, "py", 70)).data
        )

    def test_exact_extension_content_mime_path_mime_and_disposition(self):
        expected = {
            "cpp": ("cpp", "text/x-c++src", "text/x-code", "local_text"),
            "go": ("go", "text/x-go", "text/x-code", "local_text"),
            "js": ("js", "text/javascript", "text/x-code", "local_text"),
            "markdown": (
                "markdown", "text/markdown", "text/markdown", "local_text"
            ),
            "md": ("md", "text/markdown", "text/markdown", "local_text"),
            "py": ("py", "text/x-python", "text/x-code", "local_text"),
            "rs": ("rs", "text/x-rust", "text/x-code", "local_text"),
            "ts": ("ts", "text/typescript", "text/x-code", "local_text"),
            "txt": ("txt", "text/plain", "text/plain", "local_text"),
        }
        for variant, exact in expected.items():
            rendered, _ = self._render_and_validate(variant, 1)
            self.assertEqual(
                (
                    rendered.extension,
                    rendered.content_media_type,
                    rendered.expected_kcs_path_media_type,
                    rendered.expected_offline_disposition,
                ),
                exact,
            )

    def test_renderer_and_independent_validator_contracts_agree_exactly(self):
        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        self.assertEqual(set(renderer_rows), set(validator_rows))
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
        for variant in renderer.READY_VARIANTS:
            self.assertEqual(
                {key: renderer_rows[variant][key] for key in shared},
                {key: validator_rows[variant][key] for key in shared},
            )

    def test_requests_metadata_bytes_and_contract_tampering_fail_closed(self):
        valid_request = renderer.TextRenderRequest(2, "md", 2)
        invalid_renderer_requests = (
            replace(valid_request, schema_version=True),
            replace(valid_request, schema_version=1),
            replace(valid_request, variant=[]),
            replace(valid_request, variant="pdf-text"),
            replace(valid_request, target_complexity=True),
            replace(valid_request, target_complexity=0),
            replace(valid_request, target_complexity=71),
        )
        for request in invalid_renderer_requests:
            with self.subTest(request=repr(request)):
                with self.assertRaises(renderer.PersonaV2TextRendererError):
                    renderer.render_text(request)

        rendered = renderer.render_text(valid_request)
        valid_validation = validator.TextValidationRequest(
            2,
            "md",
            2,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )
        changed = bytearray(rendered.data)
        changed[-2] = ord("z") if changed[-2] != ord("z") else ord("y")
        invalid_validation_requests = (
            replace(valid_validation, schema_version=True),
            replace(valid_validation, variant="pdf-text"),
            replace(valid_validation, target_complexity=0),
            replace(valid_validation, data=bytearray(rendered.data)),
            replace(valid_validation, data=bytes(changed)),
            replace(valid_validation, data=rendered.data[:-1]),
            replace(valid_validation, extension="txt"),
            replace(valid_validation, content_media_type="text/plain"),
            replace(valid_validation, expected_kcs_path_media_type="text/plain"),
            replace(valid_validation, expected_offline_disposition="raw_only"),
        )
        for request in invalid_validation_requests:
            with self.subTest(request=repr(request)):
                with self.assertRaises(validator.PersonaV2TextValidatorError):
                    validator.validate_text_payload(request)

        renderer_contract = renderer.build_renderer_contract()
        forged_renderer = copy.deepcopy(renderer_contract)
        forged_renderer["variant_rows"][0]["raw_byte_formula"][
            "maximum_rendered_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2TextRendererError):
            renderer.validate_renderer_contract(forged_renderer)

        validator_contract = validator.build_validator_contract()
        forged_validator = copy.deepcopy(validator_contract)
        forged_validator["variant_rows"][0]["validator_profile_id"] = "forged"
        with self.assertRaises(validator.PersonaV2TextValidatorError):
            validator.validate_validator_contract(forged_validator)

        renderer_contract["variant_rows"][0]["variant_id"] = "poisoned"
        validator_contract["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "cpp",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "cpp",
        )

    def test_hashseed_timezone_and_locale_do_not_change_contracts_or_payloads(self):
        script = (
            "import hashlib; "
            "from eval import persona_v2_text_renderer as r; "
            "from eval import persona_v2_text_validator as v; "
            "parts=[r.renderer_contract_sha256(),v.validator_contract_sha256()]; "
            "parts += [hashlib.sha256(r.render_text(r.TextRenderRequest(2,x,70)).data).hexdigest() "
            "for x in r.READY_VARIANTS]; "
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
