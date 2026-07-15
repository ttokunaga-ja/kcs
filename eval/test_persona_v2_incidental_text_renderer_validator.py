import ast
import copy
from dataclasses import fields, replace
from email import policy
from email.parser import BytesParser
import hashlib
import inspect
import os
import re
import subprocess
import sys
import unittest
from unittest import mock

from eval import persona_v2_incidental_text_renderer as renderer
from eval import persona_v2_incidental_text_validator as validator
from eval import persona_v2_source_profile_catalog as historical_catalog
from eval import persona_v2_variant_catalog as variant_catalog


MATRIX = {
    "csv": (1, 5_000, 10_000, 512, 48, 480_464, "tabular-rows", "data-rows-excluding-header", "csv", "text/csv", "csv_tsv", "canonical-comma-table-v2"),
    "eml": (0, 2, 5, 8_192, 16_384, 90_112, "attachments", "attachment-parts-excluding-primary-body", "eml", "message/rfc822", "html_eml", "canonical-crlf-multipart-mixed-v2"),
    "html": (1, 128, 256, 2_048, 1_024, 263_168, "html-sections", "section-elements", "html", "text/html", "html_eml", "canonical-html-sections-v2"),
    "ipynb": (1, 128, 256, 2_048, 1_024, 263_168, "notebook-cells", "notebook-cells", "ipynb", "application/x-ipynb+json", "ipynb", "canonical-nbformat-4-5-v2"),
    "json": (1, 512, 1_024, 1_024, 256, 262_912, "json-nodes", "top-level-array-items-excluding-root-object-and-array", "json", "application/json", "structured_text", "canonical-json-node-array-v2"),
    "jsonl": (1, 2_048, 4_096, 512, 96, 393_632, "jsonl-records", "physical-json-records", "jsonl", "application/x-ndjson", "txt_log", "canonical-json-lines-v2"),
    "log": (1, 2_048, 4_096, 512, 96, 393_632, "log-records", "physical-log-records", "log", "text/plain", "txt_log", "canonical-fixed-log-records-v2"),
    "sql": (1, 128, 256, 2_048, 1_024, 263_168, "sql-statements", "select-statements", "sql", "application/sql", "structured_text", "canonical-select-statements-v2"),
    "tsv": (1, 5_000, 10_000, 512, 48, 480_464, "tabular-rows", "data-rows-excluding-header", "tsv", "text/tab-separated-values", "csv_tsv", "canonical-tab-table-v2"),
    "xml": (1, 512, 1_024, 1_024, 256, 262_912, "xml-elements", "direct-item-elements-excluding-root-element", "xml", "application/xml", "structured_text", "canonical-xml-items-v2"),
    "yaml": (1, 512, 1_024, 1_024, 256, 262_912, "yaml-nodes", "block-sequence-items-excluding-sequence-container", "yaml", "application/yaml", "structured_text", "canonical-yaml-block-sequence-v2"),
}

EXPECTED_VARIANTS = tuple(sorted(MATRIX))
EXPECTED_RENDERER_BYTES = 9_139
EXPECTED_RENDERER_SHA256 = (
    "22fae0f62a67856ef20b5820c7274aad542a2de06f76c93c5c68acdaed9652f4"
)
EXPECTED_VALIDATOR_BYTES = 10_090
EXPECTED_VALIDATOR_SHA256 = (
    "67a0f0913de6087ca4b1c836d6dff4f845d6ee50a3adf12b794236f128baed75"
)
EXPECTED_MATRIX_PAYLOAD_SHA256 = (
    "c95779f318c0c2d54734e6868b56a0238c0fabd09409735046b505dc37843cdf"
)
EXPECTED_EML_SHA256 = {
    0: "8b0739598969b51ea71b002686c0ba098619c4d1b076069c62aa526c7698acc2",
    1: "291fbc107aaee5a5b0aac529ff49d101d859ff5ed6debc71869b9afc19841d53",
    2: "0022ecc4add86f89456365183ab4b38e0edfd09f9f391391d09bc555da8fa9c6",
    3: "7edf10b04c82efb30f4414d49ddb60f6fd249fd0f1dc00bc01315a5dc30c6c3c",
    4: "56e422a7230dd54e68efcff8d952207e21b508a61afc7bc86cb0c23dcb6dc857",
    5: "a8a2e94892f0589ba06ff4c6239752bd95ea2301d4c020f173abe2cb06824531",
}


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


class RenderRequestSubclass(renderer.IncidentalTextRenderRequest):
    pass


class ValidationRequestSubclass(validator.IncidentalTextValidationRequest):
    pass


class PersonaV2IncidentalTextRendererValidatorTests(unittest.TestCase):
    def _render(self, variant, complexity):
        return renderer.render_incidental_text(
            renderer.IncidentalTextRenderRequest(2, variant, complexity)
        )

    def _validation_request(self, variant, complexity):
        rendered = self._render(variant, complexity)
        return validator.IncidentalTextValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )

    def _render_and_validate(self, variant, complexity):
        rendered = self._render(variant, complexity)
        request = validator.IncidentalTextValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )
        return rendered, validator.validate_incidental_text_payload(request)

    def test_contract_pins_caps_negative_authority_and_detachment(self):
        renderer_value = renderer.build_renderer_contract()
        validator_value = validator.build_validator_contract()
        self.assertEqual(renderer.READY_VARIANTS, EXPECTED_VARIANTS)
        self.assertEqual(validator.READY_VARIANTS, EXPECTED_VARIANTS)
        self.assertEqual(
            len(renderer.canonical_json_bytes(renderer_value)),
            EXPECTED_RENDERER_BYTES,
        )
        self.assertEqual(
            renderer.renderer_contract_sha256(renderer_value),
            EXPECTED_RENDERER_SHA256,
        )
        self.assertEqual(
            len(validator.canonical_json_bytes(validator_value)),
            EXPECTED_VALIDATOR_BYTES,
        )
        self.assertEqual(
            validator.validator_contract_sha256(validator_value),
            EXPECTED_VALIDATOR_SHA256,
        )
        self.assertTrue(renderer.validate_renderer_contract(renderer_value))
        self.assertTrue(validator.validate_validator_contract(validator_value))
        for value in (renderer_value, validator_value):
            self.assertEqual(value["variant_count"], 11)
            self.assertIs(value["byte_stress_lane_implemented"], False)
            self.assertEqual(value["canonical_limits"]["max_body_bytes"], 96 * 1024)
            self.assertEqual(value["canonical_limits"]["max_rendered_bytes"], 512 * 1024)
            self.assertEqual(value["canonical_limits"]["max_eml_wire_line_octets"], 78)
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

        forged_renderer = copy.deepcopy(renderer_value)
        forged_renderer["variant_rows"][0]["raw_byte_formula"][
            "maximum_rendered_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2IncidentalTextRendererError):
            renderer.validate_renderer_contract(forged_renderer)
        forged_validator = copy.deepcopy(validator_value)
        forged_validator["independence_contract"]["imports_renderer_module"] = True
        with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
            validator.validate_validator_contract(forged_validator)

        renderer_value["variant_rows"][0]["variant_id"] = "poisoned"
        validator_value["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(renderer.build_renderer_contract()["variant_rows"][0]["variant_id"], "csv")
        self.assertEqual(validator.build_validator_contract()["variant_rows"][0]["variant_id"], "csv")

    def test_hardcoded_variant_matrix_contracts_and_upstream_metadata(self):
        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        upstream_rows = {
            row["variant_id"]: row
            for row in variant_catalog.build_variant_catalog()["variant_rows"]
        }
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
        self.assertEqual(set(renderer_rows), set(MATRIX))
        self.assertEqual(set(validator_rows), set(MATRIX))
        for variant, exact in MATRIX.items():
            minimum, _, maximum, base, increment, maximum_bytes, measure, counting_rule, extension, content_mime, family, template = exact
            expected_complexity = {
                "counting_rule": counting_rule,
                "inclusive_maximum": maximum,
                "inclusive_minimum": minimum,
                "measure": measure,
            }
            expected_formula = {
                "base_bytes_at_minimum_complexity": base,
                "increment_bytes_per_additional_complexity": increment,
                "maximum_rendered_bytes": maximum_bytes,
                "minimum_complexity": minimum,
                "minimum_rendered_bytes": base,
                "selection_phase": "solved-source-recipe-instance-not-this-contract",
            }
            for rows in (renderer_rows, validator_rows):
                row = rows[variant]
                self.assertEqual(row["complexity"], expected_complexity)
                self.assertEqual(row["raw_byte_formula"], expected_formula)
                self.assertEqual(row["filename_extension"], extension)
                self.assertEqual(row["content_media_type"], content_mime)
                self.assertEqual(row["family"], family)
                self.assertEqual(row["render_template"], template)
                self.assertEqual(row["gate_role"], "incidental_searchable")
                self.assertEqual(row["expected_kcs_path_media_type"], "application/octet-stream")
                self.assertEqual(row["expected_offline_disposition"], "incidental_sniff")
            self.assertEqual(
                {key: renderer_rows[variant][key] for key in shared},
                {key: validator_rows[variant][key] for key in shared},
            )
            upstream = upstream_rows[variant]
            for key in (
                "family",
                "filename_extension",
                "content_media_type",
                "expected_kcs_path_media_type",
                "expected_offline_disposition",
                "gate_role",
            ):
                self.assertEqual(renderer_rows[variant][key], upstream[key])
            self.assertEqual(upstream["complexity_contract"]["minimum"], minimum)
            self.assertEqual(upstream["complexity_contract"]["maximum"], maximum)
            self.assertEqual(upstream["complexity_contract"]["complexity_unit"], measure)

    def test_every_legal_complexity_obeys_the_exact_affine_formula(self):
        for variant, exact in MATRIX.items():
            minimum, _, maximum, base, increment, maximum_bytes, *_ = exact
            previous = None
            for complexity in range(minimum, maximum + 1):
                expected = base + (complexity - minimum) * increment
                self.assertEqual(renderer.target_bytes_for(variant, complexity), expected)
                self.assertEqual(validator.target_bytes_for(variant, complexity), expected)
                self.assertLessEqual(expected, 512 * 1024)
                if previous is not None:
                    self.assertEqual(expected - previous, increment)
                previous = expected
            self.assertEqual(previous, maximum_bytes)
            for bad in (minimum - 1, maximum + 1, True, False, 1.0, "1", None, IntSubclass(minimum)):
                with self.subTest(variant=variant, bad=repr(bad)):
                    with self.assertRaises(renderer.PersonaV2IncidentalTextRendererError):
                        renderer.target_bytes_for(variant, bad)
                    with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                        validator.target_bytes_for(variant, bad)
        for bad_variant in ("unknown", b"json", [], StrSubclass("json")):
            with self.assertRaises(renderer.PersonaV2IncidentalTextRendererError):
                renderer.target_bytes_for(bad_variant, 1)
            with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                validator.target_bytes_for(bad_variant, 1)

    def test_min_middle_max_render_validate_and_receipts_are_exact(self):
        digest = hashlib.sha256()
        forbidden = re.compile(
            rb"(?:p[0-9]{2}-src-[0-9]{6}|(?:sha256|digest)\s*[:=]|[0-9a-f]{64})",
            re.IGNORECASE,
        )
        for variant, exact in MATRIX.items():
            minimum, middle, maximum, base, increment, _, measure, *_ = exact
            for complexity in (minimum, middle, maximum):
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(variant, complexity)
                    second = self._render(variant, complexity)
                    expected_bytes = base + (complexity - minimum) * increment
                    self.assertEqual(first, second)
                    self.assertIs(type(first.data), bytes)
                    self.assertEqual(len(first.data), expected_bytes)
                    self.assertEqual(first.target_bytes, expected_bytes)
                    self.assertTrue(first.data.isascii())
                    self.assertIsNone(forbidden.search(first.data))
                    if variant == "eml":
                        self.assertTrue(first.data.endswith(b"\r\n"))
                        self.assertNotIn(b"\n", first.data.replace(b"\r\n", b""))
                    else:
                        self.assertTrue(first.data.endswith(b"\n"))
                        self.assertFalse(first.data.endswith(b"\n\n"))
                        self.assertNotIn(b"\r", first.data)
                    self.assertEqual(
                        receipt,
                        {
                            "actual_chunks_attested": False,
                            "attachment_count": complexity if variant == "eml" else 0,
                            "byte_length": expected_bytes,
                            "identity_tokens_absent": True,
                            "kcs_execution_attested": False,
                            "observed_complexity_measure": measure,
                            "observed_local_complexity": complexity,
                            "structure_validated": True,
                            "target_bytes": expected_bytes,
                            "utf8_validated": True,
                        },
                    )
                    digest.update(variant.encode("ascii") + b"\0")
                    digest.update(str(complexity).encode("ascii") + b"\0")
                    digest.update(first.data)
        self.assertEqual(digest.hexdigest(), EXPECTED_MATRIX_PAYLOAD_SHA256)

    def test_eml_zero_through_five_are_strict_bounded_multipart_messages(self):
        for complexity in range(6):
            rendered, receipt = self._render_and_validate("eml", complexity)
            self.assertEqual(
                hashlib.sha256(rendered.data).hexdigest(),
                EXPECTED_EML_SHA256[complexity],
            )
            self.assertEqual(max(map(len, rendered.data.split(b"\r\n"))), 78)
            message = BytesParser(policy=policy.strict).parsebytes(rendered.data)
            self.assertFalse([defect for part in message.walk() for defect in part.defects])
            parts = list(message.iter_parts())
            self.assertEqual(len(parts), complexity + 1)
            self.assertEqual(receipt["attachment_count"], complexity)
            for ordinal, part in enumerate(parts[1:], start=1):
                self.assertEqual(part.get_filename(), f"note-{ordinal:02d}.txt")
                self.assertEqual(part.get_content_disposition(), "attachment")
                payload = part.get_payload(decode=True)
                prefix = f"Bounded attachment {ordinal:02d}. ".encode("ascii")
                self.assertTrue(payload.startswith(prefix))
                self.assertEqual(
                    set(payload[len(prefix) :].replace(b"\r\n", b"")),
                    {ord("x")},
                )
            boundary = b"--bounded-mixed-boundary"
            self.assertEqual(rendered.data.count(boundary + b"\r\n"), complexity + 1)
            self.assertEqual(rendered.data.count(boundary + b"--\r\n"), 1)

    def test_request_exact_types_metadata_and_cross_format_substitution(self):
        self.assertEqual(
            tuple(field.name for field in fields(renderer.IncidentalTextRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(field.name for field in fields(validator.IncidentalTextValidationRequest)),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(set(renderer.REQUEST_FIELDS) & set(renderer.PROHIBITED_IDENTITY_FIELDS))
        self.assertFalse(set(validator.REQUEST_FIELDS) & set(validator.PROHIBITED_IDENTITY_FIELDS))

        valid_render = renderer.IncidentalTextRenderRequest(2, "json", 2)
        invalid_render = (
            RenderRequestSubclass(2, "json", 2),
            replace(valid_render, schema_version=True),
            replace(valid_render, schema_version=2.0),
            replace(valid_render, variant=StrSubclass("json")),
            replace(valid_render, target_complexity=True),
        )
        for request in invalid_render:
            with self.assertRaises(renderer.PersonaV2IncidentalTextRendererError):
                renderer.render_incidental_text(request)

        valid = self._validation_request("json", 2)
        invalid_validation = (
            ValidationRequestSubclass(*valid.__dict__.values()),
            replace(valid, schema_version=True),
            replace(valid, data=bytearray(valid.data)),
            replace(valid, data=BytesSubclass(valid.data)),
            replace(valid, extension="JSON"),
            replace(valid, content_media_type="application/json; charset=utf-8"),
            replace(valid, expected_kcs_path_media_type="application/json"),
            replace(valid, expected_offline_disposition="local_text"),
            replace(valid, target_complexity=3),
        )
        for request in invalid_validation:
            with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                validator.validate_incidental_text_payload(request)

        for group in (
            ("csv", "tsv"),
            ("log", "jsonl"),
            ("json", "yaml", "xml"),
            ("html", "sql", "ipynb"),
        ):
            for source in group:
                for target in group:
                    if source == target:
                        continue
                    complexity = MATRIX[source][1]
                    source_payload = self._render(source, complexity)
                    target_payload = self._render(target, complexity)
                    request = validator.IncidentalTextValidationRequest(
                        2,
                        target,
                        complexity,
                        source_payload.data,
                        target_payload.extension,
                        target_payload.content_media_type,
                        target_payload.expected_kcs_path_media_type,
                        target_payload.expected_offline_disposition,
                    )
                    with self.subTest(source=source, target=target):
                        with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                            validator.validate_incidental_text_payload(request)

    def test_generic_format_specific_encoding_and_identity_tampering_fails(self):
        for variant, exact in MATRIX.items():
            request = self._validation_request(variant, exact[1])
            padding = request.data.find(b"x")
            self.assertGreaterEqual(padding, 0)
            changed = bytearray(request.data)
            changed[padding] = ord("y")
            mutations = (bytes(changed), request.data[:-1], request.data + b"\n")
            for mutation in mutations:
                with self.subTest(variant=variant, mutation=len(mutation)):
                    with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                        validator.validate_incidental_text_payload(replace(request, data=mutation))

        base = self._validation_request("log", 1)
        insertion = base.data.find(b"x" * 80)
        self.assertGreaterEqual(insertion, 0)
        tokens = (
            b"p01-src-000001",
            b"persona_id=x",
            b"scope_key=x",
            b"source_id=x",
            b"intent_key=x",
            b"materialization_id=x",
            b"query_id=x",
            b"sha256=x",
            b"a" * 64,
            b"answer=x",
            b"oracle=x",
            b"solution=x",
            b"raw_hash=x",
            b"path=x",
        )
        for token in tokens:
            changed = bytearray(base.data)
            changed[insertion : insertion + len(token)] = token
            with self.subTest(token=token):
                with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                    validator.validate_incidental_text_payload(
                        replace(base, data=bytes(changed))
                    )

        json_request = self._validation_request("json", 2)
        json_reordered = json_request.data.replace(b'{"nodes":', b'{ "nodes":', 1)
        json_reordered = json_reordered[:-1]
        self.assertEqual(len(json_reordered), len(json_request.data))
        html_request = self._validation_request("html", 2)
        html_changed = html_request.data.replace(b"<!doctype html>", b"<!--bounded -->", 1)
        xml_request = self._validation_request("xml", 2)
        xml_changed = xml_request.data.replace(b"<items>", b"<other>", 1)
        ipynb_request = self._validation_request("ipynb", 2)
        ipynb_changed = ipynb_request.data.replace(b'"markdown"', b'"code____"', 1)
        for request, mutation in (
            (json_request, json_reordered),
            (html_request, html_changed),
            (xml_request, xml_changed),
            (ipynb_request, ipynb_changed),
        ):
            self.assertEqual(len(request.data), len(mutation))
            with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                validator.validate_incidental_text_payload(replace(request, data=mutation))

        newline_request = self._validation_request("json", 2)
        for mutation in (
            b"\xef\xbb\xbf" + newline_request.data[3:],
            newline_request.data.replace(b"x", b"\x00", 1),
            newline_request.data.replace(b"x", b"\xff", 1),
            newline_request.data.replace(b"\n", b"\r", 1),
        ):
            with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                validator.validate_incidental_text_payload(
                    replace(newline_request, data=mutation)
                )

    def test_oversize_precedes_parsers_and_hostile_json_is_bounded(self):
        valid = self._validation_request("xml", 1)
        oversized = replace(valid, data=b"x" * (validator.MAX_RENDERED_BYTES + 1))
        with mock.patch.object(
            validator,
            "_validate_encoding_newline_and_identity",
            side_effect=AssertionError("decode called"),
        ) as decode, mock.patch.object(
            validator,
            "_validate_structure",
            side_effect=AssertionError("parser called"),
        ) as parser:
            with self.assertRaises(validator.PersonaV2IncidentalTextValidatorError):
                validator.validate_incidental_text_payload(oversized)
            decode.assert_not_called()
            parser.assert_not_called()

        huge = self._validation_request("json", 1_024)
        prefix = b'{"nodes":['
        suffix = b"]}\n"
        hostile = prefix + b"9" * (len(huge.data) - len(prefix) - len(suffix)) + suffix
        self.assertEqual(len(hostile), len(huge.data))
        with self.assertRaisesRegex(
            validator.PersonaV2IncidentalTextValidatorError,
            "integer exceeds 20 digits",
        ):
            validator.validate_incidental_text_payload(replace(huge, data=hostile))

        for variant, complexity in (("json", 1_024), ("ipynb", 256)):
            request = self._validation_request(variant, complexity)
            nesting = 100_000
            body = (
                b'{"nodes":['
                + b"[" * nesting
                + b"0"
                + b"]" * nesting
                + b"]}"
            )
            deep = body + b" " * (len(request.data) - len(body) - 1) + b"\n"
            self.assertEqual(len(deep), len(request.data))
            with self.subTest(variant=variant):
                with self.assertRaisesRegex(
                    validator.PersonaV2IncidentalTextValidatorError,
                    "nesting exceeds 16 containers",
                ):
                    validator.validate_incidental_text_payload(
                        replace(request, data=deep)
                    )

    def test_validator_import_independence_and_historical_catalog_pin(self):
        validator_source = inspect.getsource(validator)
        renderer_source = inspect.getsource(renderer)
        ast.parse(validator_source)
        ast.parse(renderer_source)
        for forbidden in (
            "persona_v2_incidental_text_renderer",
            "persona_v2_contract",
            "persona_v2_variant_catalog",
            "persona_v2_source_profile_catalog",
            "persona_v2_joint_problem",
            "persona_v2_joint_solver_policy",
            "persona_renderers",
        ):
            self.assertNotIn(forbidden, validator_source)
        self.assertNotIn("persona_v2_incidental_text_validator", renderer_source)

        historical = historical_catalog.build_source_profile_catalog()
        self.assertEqual(len(historical_catalog.canonical_json_bytes(historical)), 72_559)
        self.assertEqual(
            historical_catalog.source_profile_catalog_sha256(historical),
            "6e38fab07851f9fdcbf9d6e67e502484aea7edb66167ea86db1539593b8b58ac",
        )
        self.assertEqual(historical["coverage"]["ready_variant_count"], 10)
        self.assertEqual(historical["coverage"]["not_ready_variant_count"], 61)

    def test_hashseed_timezone_and_locale_are_deterministic(self):
        script = (
            "import hashlib; "
            "from eval import persona_v2_incidental_text_renderer as r; "
            "from eval import persona_v2_incidental_text_validator as v; "
            "rows={x['variant_id']:x for x in r.build_renderer_contract()['variant_rows']}; "
            "h=hashlib.sha256(); "
            "[(h.update(name.encode()+b'\\0'+str(n).encode()+b'\\0'+"
            "r.render_incidental_text(r.IncidentalTextRenderRequest(2,name,n)).data)) "
            "for name in r.READY_VARIANTS for n in sorted({rows[name]['complexity']['inclusive_minimum'],"
            "(rows[name]['complexity']['inclusive_minimum']+rows[name]['complexity']['inclusive_maximum'])//2,"
            "rows[name]['complexity']['inclusive_maximum']})]; "
            "print(r.renderer_contract_sha256(),v.validator_contract_sha256(),h.hexdigest())"
        )
        expected = (
            f"{EXPECTED_RENDERER_SHA256} {EXPECTED_VALIDATOR_SHA256} "
            f"{EXPECTED_MATRIX_PAYLOAD_SHA256}"
        )
        for seed, timezone in (("0", "UTC"), ("1", "Asia/Tokyo"), ("42", "UTC")):
            environment = os.environ.copy()
            environment.update({"PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"})
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.getcwd(),
                env=environment,
                text=True,
            ).strip()
            self.assertEqual(output, expected)


if __name__ == "__main__":
    unittest.main()
