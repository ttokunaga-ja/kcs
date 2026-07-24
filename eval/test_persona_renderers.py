#!/usr/bin/env python3
"""Focused validity and safety tests for dependency-free persona renderers."""

import ast
import csv
from dataclasses import replace
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import unittest
from unittest import mock
import wave
import xml.etree.ElementTree as ET
from zipfile import ZIP_STORED, ZipFile
import zlib

from eval import persona_fixture_spec as fixture_spec
from eval import persona_renderers as renderers


class _HTMLProbe(HTMLParser):
    def __init__(self):
        super().__init__()
        self.starts = []

    def handle_starttag(self, tag, attrs):
        self.starts.append(tag)


def _request(family, variant, chunks, source_number=1, version=0, scope_index=0):
    persona = fixture_spec.get_persona("p01")
    scope = fixture_spec.scope_specs(persona)[scope_index]["scope_key"]
    return renderers.SourceRequest(
        fixture_spec.SCHEMA_VERSION,
        "p01",
        scope,
        f"p01-src-{source_number:06d}",
        version,
        family,
        variant,
        chunks,
    )


def _assert_pdf_xref(testcase, data):
    marker = b"startxref\n"
    xref = int(data.split(marker, 1)[1].splitlines()[0])
    testcase.assertEqual(data[xref:xref + 4], b"xref")
    lines = data[xref:].splitlines()
    count = int(lines[1].split()[1])
    entries = lines[2:2 + count]
    testcase.assertEqual(entries[0], b"0000000000 65535 f ")
    for object_number, entry in enumerate(entries[1:], start=1):
        offset = int(entry[:10])
        testcase.assertTrue(
            data[offset:].startswith(f"{object_number} 0 obj\n".encode("ascii"))
        )


class TestPersonaRenderers(unittest.TestCase):
    def test_every_frozen_variant_renders_deterministically(self):
        source_number = 1
        seen = set()
        for family in fixture_spec.FORMAT_KEYS:
            for variant, _weight, gate_role, _disposition in fixture_spec.FORMAT_VARIANTS[family]:
                with self.subTest(family=family, variant=variant):
                    chunks = 3 if gate_role == "contract_contributor" else 0
                    request = _request(family, variant, chunks, source_number)
                    first = renderers.render_source(request)
                    second = renderers.render_source(request)
                    self.assertEqual(first, second)
                    self.assertEqual(
                        renderers.variant_output_contract(family, variant),
                        (first.extension, first.media_type),
                    )
                    self.assertEqual(first.renderer_id, "kio-persona-renderer")
                    self.assertEqual(first.renderer_schema_version, 1)
                    self.assertEqual(first.planned_contract_chunks, chunks)
                    self.assertEqual(
                        sum(member.planned_contract_chunks for member in first.logical_members),
                        chunks,
                    )
                    for member in first.logical_members:
                        self.assertRegex(member.unit_key, r"^[a-z0-9][a-z0-9._:-]*$")
                        self.assertIn(
                            member.kind,
                            {
                                "document", "message", "attachment", "page",
                                "sheet", "slide", "image", "audio", "packet",
                            },
                        )
                    self.assertLessEqual(len(first.data), renderers.MAX_ADAPTER_INPUT_BYTES)
                    self.assertNotIn((variant, first.data), seen)
                    seen.add((variant, first.data))
                source_number += 1

    def test_request_contract_fails_closed(self):
        valid = _request("md", "md", 1)
        invalid = (
            replace(valid, schema_version=True),
            replace(valid, schema_version=2),
            replace(valid, persona_id=[]),
            replace(valid, persona_id="p99"),
            replace(valid, scope_key=[]),
            replace(valid, scope_key="p01-primary-99"),
            replace(valid, source_id="source-000001"),
            replace(valid, source_id="p02-src-000001"),
            replace(valid, version=True),
            replace(valid, version=-1),
            replace(valid, family={}),
            replace(valid, variant=[]),
            replace(valid, requested_contributor_chunks=True),
            replace(valid, requested_contributor_chunks=0),
            replace(
                valid,
                requested_contributor_chunks=fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE + 1,
            ),
            replace(valid, family="image", variant="md"),
            _request("image", "png", 1),
        )
        for request in invalid:
            with self.subTest(request=request):
                with self.assertRaises(renderers.RendererContractError):
                    renderers.render_source(request)

    def test_forged_logical_member_metadata_fails_closed(self):
        request = _request("md", "md", 1)
        rendered = renderers.render_source(request)
        member = rendered.logical_members[0]
        second = replace(
            member,
            unit_key="doc:2",
            ordinal=1,
            planned_section_keys=(),
            planned_contract_chunks=0,
        )
        forged_members = (
            [member],
            ({"unit_key": "doc:1"},),
            (member, replace(second, unit_key=member.unit_key)),
            (member, replace(second, ordinal=0)),
            (replace(member, ordinal=1),),
            (replace(member, unit_key="../bad"),),
            (replace(member, kind="unknown"),),
            (replace(member, label=1),),
            (replace(member, label="bad\nlabel"),),
            (replace(member, label="bad\ud800label"),),
            (replace(member, planned_section_keys=["span:1"]),),
            (replace(member, planned_section_keys=(["span:1"],)),),
            (replace(member, planned_section_keys=("span:1", "span:1")),),
            (replace(member, planned_section_keys=("../bad",)),),
            (
                replace(member, planned_contract_chunks=-1),
                replace(second, planned_contract_chunks=2),
            ),
            (replace(member, planned_contract_chunks=True),),
        )
        for logical_members in forged_members:
            with self.subTest(logical_members=logical_members):
                forged = replace(rendered, logical_members=logical_members)
                with self.assertRaises(renderers.RendererContractError):
                    renderers.validate_rendered_source(request, forged)

        with self.assertRaises(renderers.RendererContractError):
            renderers.validate_rendered_source(request, replace(rendered, data=1))

    def test_heading_and_code_sources_plan_exact_chunk_boundaries(self):
        for variant, family in (("md", "md"), ("markdown", "md"), ("txt", "txt_log")):
            rendered = renderers.render_source(_request(family, variant, 7))
            text = rendered.data.decode("utf-8")
            self.assertTrue(text.endswith("\n"))
            self.assertNotIn("\r", text)
            self.assertEqual(sum(line.startswith("## ") for line in text.splitlines()), 7)
            self.assertEqual(len(rendered.logical_members[0].planned_section_keys), 7)

        for variant in ("py", "rs", "ts"):
            rendered = renderers.render_source(_request("code", variant, 7))
            raw = rendered.data.decode("utf-8").rstrip()
            normalized = f"```{variant}\n{raw}\n```\n"
            self.assertEqual(
                len(normalized),
                6 * renderers.CHUNKING_MAX_CHARS + renderers.CODE_LAST_CHUNK_CHARS,
            )
            self.assertNotIn("\n\n", normalized)
        ast.parse(renderers.render_source(_request("code", "py", 2)).data.decode("utf-8"))

    def test_family_and_variant_are_bound_into_overlapping_text_renderers(self):
        outputs = (
            renderers.render_source(_request("md", "md", 2)).data,
            renderers.render_source(_request("md", "markdown", 2)).data,
            renderers.render_source(_request("txt_log", "txt", 2)).data,
        )
        self.assertEqual(len(set(outputs)), len(outputs))

    def test_incidental_text_formats_are_parseable(self):
        json_data = renderers.render_source(_request("structured_text", "json", 0)).data
        self.assertEqual(json.loads(json_data)["schema"], fixture_spec.SCHEMA_VERSION)

        jsonl = renderers.render_source(_request("txt_log", "jsonl", 0)).data
        self.assertEqual(len([json.loads(line) for line in jsonl.splitlines()]), 2)

        xml_data = renderers.render_source(_request("structured_text", "xml", 0)).data
        self.assertEqual(ET.fromstring(xml_data).tag, "record")

        for variant, delimiter in (("csv", ","), ("tsv", "\t")):
            data = renderers.render_source(_request("csv_tsv", variant, 0)).data
            rows = list(csv.reader(io.StringIO(data.decode("utf-8")), delimiter=delimiter))
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0][0], "persona")

        message = BytesParser(policy=policy.default).parsebytes(
            renderers.render_source(_request("html_eml", "eml", 0)).data
        )
        self.assertEqual(message["From"], "fixture-sender@example.invalid")
        self.assertFalse(message.defects)

        notebook = json.loads(renderers.render_source(_request("ipynb", "ipynb", 0)).data)
        self.assertEqual((notebook["nbformat"], notebook["nbformat_minor"]), (4, 5))
        self.assertEqual([cell["cell_type"] for cell in notebook["cells"]], ["markdown", "code"])

        probe = _HTMLProbe()
        probe.feed(renderers.render_source(_request("html_eml", "html", 0)).data.decode("utf-8"))
        self.assertIn("main", probe.starts)

    def test_text_pdf_has_valid_xref_and_one_planned_page_per_chunk(self):
        rendered = renderers.render_source(_request("pdf_text", "pdf-text", 7))
        _assert_pdf_xref(self, rendered.data)
        self.assertEqual(rendered.data.count(b"/Type /Page "), 7)
        self.assertEqual(rendered.data.count(b"BT "), 7)
        self.assertEqual(rendered.data.count(b" Tj ET"), 7)
        self.assertEqual([member.unit_key for member in rendered.logical_members], [
            f"page:{index}" for index in range(1, 8)
        ])
        self.assertTrue(all(member.planned_contract_chunks == 1 for member in rendered.logical_members))

    def test_scan_pdf_has_image_xobject_and_is_bt_free_for_many_identities(self):
        # This is deliberately broad: a prior Flate implementation collided at
        # p01-src-011844 even though its PDF content stream had no text object.
        for source_number in range(1, 20_001):
            rendered = renderers.render_source(
                _request("pdf_scan", "pdf-scan", 0, source_number, scope_index=source_number % 20)
            )
            self.assertNotIn(b"BT", rendered.data)
            self.assertIn(b"/Subtype /Image", rendered.data)
            self.assertIn(b"/ASCIIHexDecode", rendered.data)
        reproduced = renderers.render_source(
            _request("pdf_scan", "pdf-scan", 0, 11_844, scope_index=4)
        )
        _assert_pdf_xref(self, reproduced.data)

    def test_structural_png_transforms_are_parent_bound_and_machine_verifiable(self):
        parent_request = _request("image", "png", 0, source_number=30_001)
        parent = renderers.render_source(parent_request)
        parent_pixels = renderers.decode_fixture_png_rgb(parent.data)

        near_request = _request("image", "png", 0, source_number=30_002)
        near, near_witness = renderers.render_near_png(
            parent.data, near_request
        )
        near_pixels = renderers.decode_fixture_png_rgb(near.data)
        differences = [
            index
            for index, values in enumerate(zip(parent_pixels, near_pixels))
            if values[0] != values[1]
        ]
        self.assertEqual(
            differences, [near_witness["changed_channel_index"]]
        )
        changed = differences[0]
        self.assertEqual(
            abs(parent_pixels[changed] - near_pixels[changed]), 1
        )
        self.assertNotEqual(parent.data, near.data)
        self.assertEqual(
            renderers.render_near_png(parent.data, near_request),
            (near, near_witness),
        )

        derived_request = _request(
            "pdf_scan", "pdf-scan", 0, source_number=30_003
        )
        derived, derived_witness = renderers.render_scan_pdf_from_png(
            parent.data, derived_request
        )
        self.assertIn(parent_pixels.hex().upper().encode("ascii") + b">", derived.data)
        self.assertNotIn(b"BT", derived.data)
        self.assertEqual(derived_witness["embedded_pixel_bytes"], 12)
        self.assertFalse(derived_witness["contains_text_layer_bt"])
        _assert_pdf_xref(self, derived.data)

    def test_structural_png_transforms_reject_wrong_or_corrupt_inputs(self):
        parent = renderers.render_source(
            _request("image", "png", 0, source_number=31_001)
        )
        corrupt = parent.data[:-5] + bytes([parent.data[-5] ^ 1]) + parent.data[-4:]
        with self.assertRaises(renderers.RendererContractError):
            renderers.decode_fixture_png_rgb(corrupt)
        with self.assertRaises(renderers.RendererContractError):
            renderers.render_near_png(
                parent.data,
                _request("pdf_scan", "pdf-scan", 0, source_number=31_002),
            )
        with self.assertRaises(renderers.RendererContractError):
            renderers.render_scan_pdf_from_png(
                parent.data,
                _request("image", "png", 0, source_number=31_003),
            )

    def test_ooxml_packages_are_complete_parseable_and_byte_stable(self):
        cases = {
            "docx": ("docx", "word/document.xml", "word/_rels/document.xml.rels"),
            "xlsx": ("xlsx", "xl/worksheets/sheet1.xml", "xl/_rels/workbook.xml.rels"),
            "pptx": ("pptx", "ppt/slides/slide1.xml", "ppt/slideMasters/slideMaster1.xml"),
        }
        for family, (variant, content_part, relationship_or_master) in cases.items():
            with self.subTest(family=family):
                request = _request(family, variant, 0)
                first = renderers.render_source(request).data
                second = renderers.render_source(request).data
                self.assertEqual(first, second)
                with ZipFile(io.BytesIO(first)) as archive:
                    infos = archive.infolist()
                    self.assertEqual([info.filename for info in infos], sorted(info.filename for info in infos))
                    self.assertTrue(all(info.date_time == (1980, 1, 1, 0, 0, 0) for info in infos))
                    self.assertTrue(all(info.compress_type == ZIP_STORED for info in infos))
                    names = set(archive.namelist())
                    self.assertIn("[Content_Types].xml", names)
                    self.assertIn("_rels/.rels", names)
                    self.assertIn(content_part, names)
                    self.assertIn(relationship_or_master, names)
                    for name in names:
                        if name.endswith((".xml", ".rels")):
                            ET.fromstring(archive.read(name))

    def test_png_wav_and_pcap_have_valid_binary_envelopes(self):
        png = renderers.render_source(_request("image", "png", 0)).data
        self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
        offset = 8
        kinds = []
        while offset < len(png):
            length = struct.unpack(">I", png[offset:offset + 4])[0]
            kind = png[offset + 4:offset + 8]
            payload = png[offset + 8:offset + 8 + length]
            expected_crc = struct.unpack(">I", png[offset + 8 + length:offset + 12 + length])[0]
            self.assertEqual(zlib.crc32(kind + payload) & 0xFFFFFFFF, expected_crc)
            kinds.append(kind)
            if kind == b"IDAT":
                self.assertEqual(len(zlib.decompress(payload)), 14)
            offset += 12 + length
        self.assertEqual(kinds, [b"IHDR", b"IDAT", b"IEND"])

        wav = renderers.render_source(_request("media", "wav", 0)).data
        with wave.open(io.BytesIO(wav), "rb") as wav_file:
            self.assertEqual((wav_file.getnchannels(), wav_file.getsampwidth()), (1, 2))
            self.assertEqual((wav_file.getframerate(), wav_file.getnframes()), (8_000, 160))

        pcap = renderers.render_source(_request("domain_binary", "pcap", 0)).data
        magic, major, minor, _zone, _sigfigs, snaplen, network = struct.unpack("<IHHIIII", pcap[:24])
        self.assertEqual((magic, major, minor, snaplen, network), (0xA1B2C3D4, 2, 4, 65535, 1))
        _seconds, micros, included, original = struct.unpack("<IIII", pcap[24:40])
        self.assertLess(micros, 1_000_000)
        self.assertEqual(included, original)
        self.assertEqual(len(pcap[40:]), included)
        self.assertEqual(pcap[52:54], b"\x08\x00")

    def test_result_validator_enforces_adapter_byte_ceiling(self):
        request = _request("md", "md", 1)
        rendered = renderers.render_source(request)
        with mock.patch.object(renderers, "MAX_RENDERED_SOURCE_BYTES", len(rendered.data) - 1):
            with self.assertRaisesRegex(renderers.RendererContractError, "byte bounds"):
                renderers.validate_rendered_source(request, rendered)
        self.assertEqual(renderers.MAX_RENDERED_SOURCE_BYTES, 100 * 1024 * 1024)

    def test_module_can_start_as_a_direct_script(self):
        module_path = Path(renderers.__file__).resolve()
        completed = subprocess.run(
            [sys.executable, str(module_path)],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout, "")


if __name__ == "__main__":
    unittest.main()
