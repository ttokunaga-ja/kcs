import ast
import copy
from dataclasses import fields, replace
import hashlib
import inspect
import io
import os
import re
import struct
import subprocess
import sys
import unittest
from unittest import mock
import xml.etree.ElementTree as ET
from zipfile import ZIP_STORED, ZipFile

from eval import persona_v2_raw_document_renderer as renderer
from eval import persona_v2_raw_document_validator as validator
from eval import persona_v2_source_profile_catalog as historical_catalog
from eval import persona_v2_variant_catalog as variant_catalog


MATRIX = {
    "docx": (
        1,
        32,
        64,
        8_192,
        2_048,
        137_216,
        "document-sections",
        "wordprocessingml-section-properties-elements",
        "docx",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "await_conversion",
        "docx",
        "canonical-stored-wordprocessingml-sections-v2",
    ),
    "pdf-scan": (
        1,
        25,
        50,
        8_192,
        4_096,
        208_896,
        "scan-pages",
        "page-tree-leaf-pages-each-with-one-image-xobject",
        "pdf",
        "application/pdf",
        "application/pdf",
        "awaiting_ocr",
        "pdf_scan",
        "canonical-image-xobject-scan-pdf-v2",
    ),
    "pptx": (
        1,
        20,
        40,
        16_384,
        8_192,
        335_872,
        "slides",
        "presentation-slide-identifiers-and-internal-slide-parts",
        "pptx",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "await_conversion",
        "pptx",
        "canonical-stored-presentationml-slides-v2",
    ),
    "xlsx": (
        1,
        10,
        20,
        12_288,
        6_144,
        129_024,
        "worksheets",
        "workbook-sheet-elements-and-internal-worksheet-parts",
        "xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "await_conversion",
        "xlsx",
        "canonical-stored-spreadsheetml-worksheets-v2",
    ),
}

EXPECTED_VARIANTS = tuple(sorted(MATRIX))
EXPECTED_RENDERER_BYTES = 4_657
EXPECTED_RENDERER_SHA256 = (
    "ac43d8e60fe288552e5edf1e11d98123b34766db8387460cb9f7ddf70af3ba2c"
)
EXPECTED_VALIDATOR_BYTES = 5_183
EXPECTED_VALIDATOR_SHA256 = (
    "c664596fce5331268ad69886b3f2d159e090241b4ef2848ac4ce64c52a1a572a"
)
EXPECTED_MATRIX_PAYLOAD_SHA256 = (
    "f5b19a7b2201c8e699eef539bf1e124c6d24c0076a71aff018821b8cf4fba171"
)
EXPECTED_PAYLOAD_SHA256 = {
    ("docx", 1): "291df9ee559f60a3b0e123f5082c7aeaf5cc18e8c02d47233700b34a68f023d9",
    ("docx", 32): "af1ede734cf9a5c4a6e7db6c80a2087fee3837b7225d3f746fc9977745207b98",
    ("docx", 64): "05a105bf1a31cd2a51a5b120412ab0dd411b1bcc662853278b663b0729c605cb",
    ("pdf-scan", 1): "de8f083084c319bd49fe27b4528023815bbf97e384cd6214e3aab1f2e9cff7fe",
    ("pdf-scan", 25): "3ed529ff44c175d29425e0522b2fb4055d8b5a64f11e51a80f3fa26558148f4b",
    ("pdf-scan", 50): "dd62a11bf1b59068a815af3ebd776a45d9abf1bf997e9c325e28e1e5540d8f3f",
    ("pptx", 1): "0b4f2a56fb76ee9a9331d8102294aefe6a9e1e337342eb86b455e52810996ef3",
    ("pptx", 20): "65dbb97eaf70ef477ce4c86b3a775f8be56b62f444a5cefd6d3d7307ec2044e6",
    ("pptx", 40): "aaaf30db76e01f8aec7d454420e493c7545d700c690d51e5a5aecf30f22790eb",
    ("xlsx", 1): "90393865c7ddb85c567c63e2223316eb387ff2ac4f248e23c7069dc5789b923f",
    ("xlsx", 10): "42ff0728fddc55e1537e3d10af4d9c1cf7e57451105e6b0bcde688df400fafac",
    ("xlsx", 20): "b064ebfc932bbe199caa08661f791185e26e37878f6140d78daac59f76fa5689",
}


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


class RenderRequestSubclass(renderer.RawDocumentRenderRequest):
    pass


class ValidationRequestSubclass(validator.RawDocumentValidationRequest):
    pass


class PersonaV2RawDocumentRendererValidatorTests(unittest.TestCase):
    def _render(self, variant, complexity):
        return renderer.render_raw_document(
            renderer.RawDocumentRenderRequest(2, variant, complexity)
        )

    def _validation_request(self, variant, complexity):
        rendered = self._render(variant, complexity)
        return validator.RawDocumentValidationRequest(
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
        request = validator.RawDocumentValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kcs_path_media_type,
            rendered.expected_offline_disposition,
        )
        return rendered, validator.validate_raw_document_payload(request)

    def _repack_same_length(self, request, mutator):
        parts = validator._parse_bounded_stored_zip(request.data)
        mutator(parts)
        core_pattern = re.compile(
            rb"(<dc:description>)(x*)(</dc:description>)"
        )
        match = core_pattern.search(parts["docProps/core.xml"])
        self.assertIsNotNone(match)
        padding = len(match.group(2))
        for _ in range(4):
            data = validator._assemble_expected_zip(parts)
            delta = len(request.data) - len(data)
            if delta == 0:
                self.assertEqual(
                    validator._parse_bounded_stored_zip(data), parts
                )
                return data
            padding += delta
            self.assertGreaterEqual(padding, 0)
            core = core_pattern.sub(
                lambda found: found.group(1)
                + b"x" * padding
                + found.group(3),
                parts["docProps/core.xml"],
                count=1,
            )
            parts["docProps/core.xml"] = core
        self.fail("could not repad canonical stored ZIP")

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
            self.assertEqual(value["variant_count"], 4)
            self.assertIs(value["byte_stress_lane_implemented"], False)
            self.assertEqual(
                value["canonical_limits"]["max_rendered_bytes"], 512 * 1024
            )
            self.assertEqual(value["canonical_limits"]["max_ooxml_members"], 128)
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

        forged_renderer = copy.deepcopy(renderer_value)
        forged_renderer["variant_rows"][0]["raw_byte_formula"][
            "maximum_rendered_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2RawDocumentRendererError):
            renderer.validate_renderer_contract(forged_renderer)
        forged_validator = copy.deepcopy(validator_value)
        forged_validator["independence_contract"]["imports_renderer_module"] = True
        with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
            validator.validate_validator_contract(forged_validator)

        renderer_value["variant_rows"][0]["variant_id"] = "poisoned"
        validator_value["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "docx",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "docx",
        )

    def test_hardcoded_matrix_upstream_metadata_inventory_and_capacity_bounds(self):
        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        upstream = variant_catalog.build_variant_catalog()
        upstream_rows = {row["variant_id"]: row for row in upstream["variant_rows"]}
        self.assertEqual(set(renderer_rows), set(MATRIX))
        self.assertEqual(set(validator_rows), set(MATRIX))
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
        for variant, exact in MATRIX.items():
            (
                minimum,
                _middle,
                maximum,
                base,
                increment,
                maximum_bytes,
                measure,
                counting_rule,
                extension,
                content_mime,
                path_mime,
                disposition,
                family,
                template,
            ) = exact
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
                self.assertEqual(row["expected_kcs_path_media_type"], path_mime)
                self.assertEqual(row["expected_offline_disposition"], disposition)
                self.assertEqual(row["family"], family)
                self.assertEqual(row["render_template"], template)
                self.assertEqual(row["gate_role"], "raw_only")
            self.assertEqual(
                {key: renderer_rows[variant][key] for key in shared},
                {key: validator_rows[variant][key] for key in shared},
            )
            upstream_row = upstream_rows[variant]
            for key in (
                "family",
                "filename_extension",
                "content_media_type",
                "expected_kcs_path_media_type",
                "expected_offline_disposition",
                "gate_role",
            ):
                self.assertEqual(renderer_rows[variant][key], upstream_row[key])
            self.assertEqual(
                upstream_row["complexity_contract"]["minimum"], minimum
            )
            self.assertEqual(
                upstream_row["complexity_contract"]["maximum"], maximum
            )
            self.assertEqual(
                upstream_row["complexity_contract"]["complexity_unit"], measure
            )

        marginals = [
            row
            for row in upstream["persona_variant_marginals"]
            if row["variant_id"] in MATRIX
        ]
        self.assertEqual(len(marginals), 80)
        self.assertEqual(sum(row["full_count"] for row in marginals), 53_140)
        self.assertEqual(sum(row["pilot_count"] for row in marginals), 5_314)
        self.assertEqual(sum(row["tiny_smoke_count"] for row in marginals), 1_110)
        counts = {
            variant: sum(
                row["full_count"]
                for row in marginals
                if row["variant_id"] == variant
            )
            for variant in MATRIX
        }
        minimum_bytes = sum(counts[name] * MATRIX[name][3] for name in counts)
        maximum_bytes = sum(counts[name] * MATRIX[name][5] for name in counts)
        self.assertEqual(minimum_bytes, 581_263_360)
        self.assertEqual(maximum_bytes, 9_991_700_480)

    def test_every_legal_complexity_obeys_the_exact_affine_formula(self):
        for variant, exact in MATRIX.items():
            minimum, _middle, maximum, base, increment, maximum_bytes, *_ = exact
            previous = None
            for complexity in range(minimum, maximum + 1):
                expected = base + (complexity - minimum) * increment
                self.assertEqual(
                    renderer.target_bytes_for(variant, complexity), expected
                )
                self.assertEqual(
                    validator.target_bytes_for(variant, complexity), expected
                )
                self.assertLessEqual(expected, 512 * 1024)
                if previous is not None:
                    self.assertEqual(expected - previous, increment)
                previous = expected
            self.assertEqual(previous, maximum_bytes)
            for bad in (
                minimum - 1,
                maximum + 1,
                True,
                False,
                1.0,
                "1",
                None,
                IntSubclass(minimum),
            ):
                with self.subTest(variant=variant, bad=repr(bad)):
                    with self.assertRaises(renderer.PersonaV2RawDocumentRendererError):
                        renderer.target_bytes_for(variant, bad)
                    with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                        validator.target_bytes_for(variant, bad)
        for bad_variant in ("unknown", b"docx", [], StrSubclass("docx")):
            with self.assertRaises(renderer.PersonaV2RawDocumentRendererError):
                renderer.target_bytes_for(bad_variant, 1)
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.target_bytes_for(bad_variant, 1)

    def test_min_middle_max_render_validate_receipts_and_hashes(self):
        digest = hashlib.sha256()
        for variant, exact in MATRIX.items():
            minimum, middle, maximum, base, increment, _, measure, *_ = exact
            for complexity in (minimum, middle, maximum):
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(variant, complexity)
                    second = self._render(variant, complexity)
                    expected_bytes = base + (complexity - minimum) * increment
                    self.assertEqual(first, second)
                    self.assertIs(type(first.data), bytes)
                    self.assertFalse(hasattr(first, "__dict__"))
                    with self.assertRaises(AttributeError):
                        object.__setattr__(
                            first, "final_source_id", "p01-src-000001"
                        )
                    self.assertEqual(len(first.data), expected_bytes)
                    self.assertEqual(first.target_bytes, expected_bytes)
                    self.assertEqual(
                        hashlib.sha256(first.data).hexdigest(),
                        EXPECTED_PAYLOAD_SHA256[(variant, complexity)],
                    )
                    expected_members = {
                        "docx": 6,
                        "pdf-scan": 0,
                        "pptx": 12 + 2 * complexity,
                        "xlsx": 7 + complexity,
                    }[variant]
                    self.assertEqual(
                        receipt,
                        {
                            "actual_chunks_attested": False,
                            "byte_length": expected_bytes,
                            "container_member_count": expected_members,
                            "identity_tokens_absent": True,
                            "kcs_execution_attested": False,
                            "observed_complexity_measure": measure,
                            "observed_local_complexity": complexity,
                            "pdf_text_layer_absent": variant == "pdf-scan",
                            "structure_validated": True,
                            "target_bytes": expected_bytes,
                            "zip_stored_validated": variant != "pdf-scan",
                        },
                    )
                    digest.update(variant.encode("ascii") + b"\0")
                    digest.update(str(complexity).encode("ascii") + b"\0")
                    digest.update(first.data)
        self.assertEqual(digest.hexdigest(), EXPECTED_MATRIX_PAYLOAD_SHA256)

    def test_scan_pdf_has_exact_image_only_pages_xref_and_bounded_padding(self):
        for complexity in (1, 9, 10, 50):
            rendered, _receipt = self._render_and_validate("pdf-scan", complexity)
            data = rendered.data
            self.assertTrue(data.startswith(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n"))
            self.assertTrue(data.endswith(b"%%EOF\n"))
            self.assertEqual(data.count(b"/Subtype /Image"), complexity)
            self.assertEqual(data.count(b"/Type /Page "), complexity)
            self.assertIn(f"/Count {complexity}\n".encode("ascii"), data)
            for token in (
                b"BT",
                b"ET",
                b"/Font",
                b"/ToUnicode",
                b"/Encrypt",
                b"/JavaScript",
                b"/EmbeddedFile",
            ):
                self.assertNotIn(token, data)
            xref_match = re.search(rb"startxref\n([0-9]+)\n%%EOF\n\Z", data)
            self.assertIsNotNone(xref_match)
            xref_offset = int(xref_match.group(1))
            self.assertEqual(data[xref_offset : xref_offset + 5], b"xref\n")
            last_endobj = data.rfind(b"\nendobj\n", 0, xref_offset)
            self.assertGreater(last_endobj, 0)
            padding = data[last_endobj + len(b"\nendobj\n") : xref_offset]
            self.assertTrue(padding)
            for line in padding.splitlines():
                self.assertTrue(line.startswith(b"%"))
                self.assertLessEqual(len(line), 255)
                self.assertFalse(set(line[1:]) - {ord("x")})

    def test_ooxml_is_consumer_parseable_stored_and_has_exact_graph(self):
        for variant, complexities in (
            ("docx", (1, 64)),
            ("xlsx", (1, 9, 10, 20)),
            ("pptx", (1, 9, 10, 40)),
        ):
            for complexity in complexities:
                with self.subTest(variant=variant, complexity=complexity):
                    rendered, receipt = self._render_and_validate(
                        variant, complexity
                    )
                    with ZipFile(io.BytesIO(rendered.data)) as archive:
                        infos = archive.infolist()
                        self.assertEqual(
                            [info.filename for info in infos],
                            sorted(info.filename for info in infos),
                        )
                        self.assertEqual(len(infos), receipt["container_member_count"])
                        self.assertIsNone(archive.testzip())
                        for info in infos:
                            self.assertEqual(info.compress_type, ZIP_STORED)
                            self.assertEqual(info.compress_size, info.file_size)
                            self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                            self.assertEqual(info.flag_bits, 0)
                            self.assertEqual(info.create_system, 0)
                            self.assertEqual(info.create_version, 20)
                            self.assertEqual(info.extract_version, 20)
                            self.assertEqual(info.extra, b"")
                            self.assertEqual(info.comment, b"")
                            payload = archive.read(info)
                            self.assertTrue(payload.startswith(b"<?xml version="))
                            ET.fromstring(payload)
                    parts = validator._parse_bounded_stored_zip(rendered.data)
                    self.assertIn("[Content_Types].xml", parts)
                    self.assertIn("_rels/.rels", parts)
                    self.assertIn("docProps/core.xml", parts)
                    if variant == "xlsx":
                        self.assertEqual(
                            len(
                                [
                                    name
                                    for name in parts
                                    if name.startswith("xl/worksheets/sheet")
                                ]
                            ),
                            complexity,
                        )
                        self.assertNotIn(b"<f>", rendered.data)
                    if variant == "pptx":
                        self.assertIn("ppt/presProps.xml", parts)
                        self.assertEqual(
                            len(
                                [
                                    name
                                    for name in parts
                                    if name.startswith("ppt/slides/slide")
                                    and name.endswith(".xml")
                                ]
                            ),
                            complexity,
                        )
                        presentation_ns = (
                            "http://schemas.openxmlformats.org/presentationml/2006/main"
                        )
                        drawing_ns = (
                            "http://schemas.openxmlformats.org/drawingml/2006/main"
                        )
                        master = ET.fromstring(
                            parts["ppt/slideMasters/slideMaster1.xml"]
                        )
                        layout_ids = master.findall(
                            f".//{{{presentation_ns}}}sldLayoutId"
                        )
                        self.assertEqual(len(layout_ids), 1)
                        self.assertGreaterEqual(
                            int(layout_ids[0].attrib["id"]), 2_147_483_648
                        )
                        theme = ET.fromstring(parts["ppt/theme/theme1.xml"])
                        font_scheme = theme.find(
                            f".//{{{drawing_ns}}}fontScheme"
                        )
                        self.assertIsNotNone(font_scheme)
                        for font_kind in ("majorFont", "minorFont"):
                            font = font_scheme.find(
                                f"{{{drawing_ns}}}{font_kind}"
                            )
                            self.assertIsNotNone(font)
                            self.assertEqual(
                                [
                                    child.tag.rsplit("}", 1)[-1]
                                    for child in list(font)[:3]
                                ],
                                ["latin", "ea", "cs"],
                            )
                        for list_name in (
                            "fillStyleLst",
                            "lnStyleLst",
                            "effectStyleLst",
                            "bgFillStyleLst",
                        ):
                            style_list = theme.find(
                                f".//{{{drawing_ns}}}{list_name}"
                            )
                            self.assertIsNotNone(style_list)
                            self.assertGreaterEqual(len(list(style_list)), 3)

    def test_exact_request_types_metadata_and_cross_format_substitution(self):
        self.assertEqual(
            tuple(field.name for field in fields(renderer.RawDocumentRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(
                field.name for field in fields(validator.RawDocumentValidationRequest)
            ),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(
            set(renderer.REQUEST_FIELDS) & set(renderer.PROHIBITED_IDENTITY_FIELDS)
        )
        self.assertFalse(
            set(validator.REQUEST_FIELDS) & set(validator.PROHIBITED_IDENTITY_FIELDS)
        )
        valid_render = renderer.RawDocumentRenderRequest(2, "docx", 1)
        self.assertFalse(hasattr(valid_render, "__dict__"))
        with self.assertRaises(AttributeError):
            object.__setattr__(valid_render, "source_id", "p01-src-000001")
        for request in (
            RenderRequestSubclass(2, "docx", 1),
            replace(valid_render, schema_version=True),
            replace(valid_render, schema_version=2.0),
            replace(valid_render, variant=StrSubclass("docx")),
            replace(valid_render, target_complexity=True),
        ):
            with self.assertRaises(renderer.PersonaV2RawDocumentRendererError):
                renderer.render_raw_document(request)

        valid = self._validation_request("docx", 1)
        self.assertFalse(hasattr(valid, "__dict__"))
        with self.assertRaises(AttributeError):
            object.__setattr__(valid, "query_id", "query-001")
        for request in (
            ValidationRequestSubclass(
                valid.schema_version,
                valid.variant,
                valid.target_complexity,
                valid.data,
                valid.extension,
                valid.content_media_type,
                valid.expected_kcs_path_media_type,
                valid.expected_offline_disposition,
            ),
            replace(valid, schema_version=True),
            replace(valid, data=bytearray(valid.data)),
            replace(valid, data=BytesSubclass(valid.data)),
            replace(valid, extension="DOCX"),
            replace(valid, content_media_type="application/zip"),
            replace(valid, expected_kcs_path_media_type="application/octet-stream"),
            replace(valid, expected_offline_disposition="unsupported_binary"),
            replace(valid, target_complexity=2),
        ):
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(request)

        docx = self._validation_request("docx", 3)
        xlsx_metadata = self._validation_request("xlsx", 1)
        self.assertEqual(len(docx.data), len(xlsx_metadata.data))
        relabeled_docx = replace(
            xlsx_metadata,
            data=docx.data,
        )
        with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
            validator.validate_raw_document_payload(relabeled_docx)
        scan = self._validation_request("pdf-scan", 3)
        pptx_metadata = self._validation_request("pptx", 1)
        self.assertEqual(len(scan.data), len(pptx_metadata.data))
        with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
            validator.validate_raw_document_payload(
                replace(pptx_metadata, data=scan.data)
            )

    def test_pdf_and_ooxml_same_length_semantic_tampering_fails(self):
        pdf = self._validation_request("pdf-scan", 10)
        mutations = (
            pdf.data.replace(b"/Width 16", b"/Width 17", 1),
            pdf.data.replace(b"/Count 10", b"/Count 11", 1),
            pdf.data.replace(b"/Im0 Do", b"/Im1 Do", 1),
        )
        for mutation in mutations:
            self.assertEqual(len(mutation), len(pdf.data))
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(replace(pdf, data=mutation))

        docx = self._validation_request("docx", 3)

        def external_relation(parts):
            parts["_rels/.rels"] = parts["_rels/.rels"].replace(
                b'<Relationship Id="rId1"',
                b'<Relationship TargetMode="External" Id="rId1"',
                1,
            )

        def dtd(parts):
            declaration_end = parts["docProps/core.xml"].find(b"?>") + 2
            parts["docProps/core.xml"] = (
                parts["docProps/core.xml"][:declaration_end]
                + b'<!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]>'
                + parts["docProps/core.xml"][declaration_end:]
            )

        def unicode_relationship_type(parts):
            parts["_rels/.rels"] = parts["_rels/.rels"].replace(
                b"officeDocument",
                "officeDocumént".encode("utf-8"),
                1,
            )

        xlsx = self._validation_request("xlsx", 3)

        def formula(parts):
            name = "xl/worksheets/sheet001.xml"
            parts[name] = parts[name].replace(
                b"<is><t>Bounded worksheet 001</t></is>",
                b"<f>1+1</f><v>2</v>",
                1,
            )

        pptx = self._validation_request("pptx", 3)

        def missing_presprops(parts):
            del parts["ppt/presProps.xml"]

        for request, mutator in (
            (docx, external_relation),
            (docx, dtd),
            (docx, unicode_relationship_type),
            (xlsx, formula),
            (pptx, missing_presprops),
        ):
            mutation = self._repack_same_length(request, mutator)
            self.assertEqual(len(mutation), len(request.data))
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(
                    replace(request, data=mutation)
                )

    def test_zip_header_path_duplicate_macro_and_size_attacks_fail_closed(self):
        docx = self._validation_request("docx", 4)

        traversal = docx.data.replace(
            b"docProps/app.xml", b"../evil/evil.xml"
        )
        self.assertEqual(len(traversal), len(docx.data))

        duplicate = docx.data.replace(
            b"docProps/core.xml", b"word/document.xml"
        )
        self.assertEqual(len(duplicate), len(docx.data))

        compressed = bytearray(docx.data)
        local = compressed.find(b"PK\x03\x04")
        central = compressed.find(b"PK\x01\x02")
        self.assertGreaterEqual(local, 0)
        self.assertGreaterEqual(central, 0)
        struct.pack_into("<H", compressed, local + 8, 8)
        struct.pack_into("<H", compressed, central + 10, 8)

        huge = bytearray(docx.data)
        central = huge.find(b"PK\x01\x02")
        struct.pack_into("<I", huge, central + 24, validator.MAX_XML_PART_BYTES + 1)

        def macro(parts):
            parts["word/vbaProject.bin"] = b"bounded"

        macro_payload = self._repack_same_length(docx, macro)
        attacks = (
            traversal,
            duplicate,
            bytes(compressed),
            bytes(huge),
            macro_payload,
        )
        for attack in attacks:
            self.assertEqual(len(attack), len(docx.data))
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(
                    replace(docx, data=attack)
                )

    def test_generic_identity_byte_and_framing_tampering_fails(self):
        for variant, exact in MATRIX.items():
            request = self._validation_request(variant, exact[1])
            changed = bytearray(request.data)
            if variant == "pdf-scan":
                index = request.data.find(b"%" + b"x" * 16)
                self.assertGreaterEqual(index, 0)
                changed[index + 1] = ord("y")
            else:
                index = request.data.find(b"<dc:description>")
                self.assertGreaterEqual(index, 0)
                index += len(b"<dc:description>")
                changed[index] = ord("y")
            for mutation in (bytes(changed), request.data[:-1], request.data + b"\x00"):
                with self.subTest(variant=variant, length=len(mutation)):
                    with self.assertRaises(
                        validator.PersonaV2RawDocumentValidatorError
                    ):
                        validator.validate_raw_document_payload(
                            replace(request, data=mutation)
                        )

        base = self._validation_request("docx", 8)
        insertion = base.data.find(b"x" * 100)
        self.assertGreaterEqual(insertion, 0)
        for token in (
            b"p01-src-000001",
            b"persona_id=x",
            b"scope_key=x",
            b"source_id=x",
            b"intent_key=x",
            b"materialization_id=x",
            b"query_id=x",
            b"sha256=x",
            b"a" * 64,
        ):
            changed = bytearray(base.data)
            changed[insertion : insertion + len(token)] = token
            with self.subTest(token=token):
                with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                    validator.validate_raw_document_payload(
                        replace(base, data=bytes(changed))
                    )

    def test_oversize_is_rejected_before_pdf_zip_or_xml_parsing(self):
        valid = self._validation_request("docx", 1)
        oversized = replace(valid, data=b"x" * (validator.MAX_RENDERED_BYTES + 1))
        with mock.patch.object(
            validator,
            "_parse_bounded_stored_zip",
            side_effect=AssertionError("ZIP parser called"),
        ) as zip_parser, mock.patch.object(
            validator,
            "_parse_bounded_xml",
            side_effect=AssertionError("XML parser called"),
        ) as xml_parser:
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(oversized)
            zip_parser.assert_not_called()
            xml_parser.assert_not_called()

        pdf = self._validation_request("pdf-scan", 1)
        oversized_pdf = replace(
            pdf, data=b"x" * (validator.MAX_RENDERED_BYTES + 1)
        )
        with mock.patch.object(
            validator,
            "_validate_pdf_structure",
            side_effect=AssertionError("PDF parser called"),
        ) as pdf_parser:
            with self.assertRaises(validator.PersonaV2RawDocumentValidatorError):
                validator.validate_raw_document_payload(oversized_pdf)
            pdf_parser.assert_not_called()

    def test_validator_import_independence_and_historical_catalog_pin(self):
        validator_source = inspect.getsource(validator)
        renderer_source = inspect.getsource(renderer)
        ast.parse(validator_source)
        ast.parse(renderer_source)
        for forbidden in (
            "persona_v2_raw_document_renderer",
            "persona_v2_contract",
            "persona_v2_variant_catalog",
            "persona_v2_source_profile_catalog",
            "persona_v2_joint_problem",
            "persona_v2_joint_solver_policy",
            "persona_renderers",
        ):
            self.assertNotIn(forbidden, validator_source)
        self.assertNotIn("persona_v2_raw_document_validator", renderer_source)

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
            "from eval import persona_v2_raw_document_renderer as r; "
            "from eval import persona_v2_raw_document_validator as v; "
            "rows={x['variant_id']:x for x in r.build_renderer_contract()['variant_rows']}; "
            "h=hashlib.sha256(); "
            "[(h.update(name.encode()+b'\\0'+str(n).encode()+b'\\0'+"
            "r.render_raw_document(r.RawDocumentRenderRequest(2,name,n)).data)) "
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
            environment.update(
                {"PYTHONHASHSEED": seed, "TZ": timezone, "LC_ALL": "C"}
            )
            output = subprocess.check_output(
                [sys.executable, "-c", script],
                cwd=os.getcwd(),
                env=environment,
                text=True,
            ).strip()
            self.assertEqual(output, expected)


if __name__ == "__main__":
    unittest.main()
