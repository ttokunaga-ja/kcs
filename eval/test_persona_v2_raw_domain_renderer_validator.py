"""Contract, format, adversarial, and determinism gates for raw binaries."""

from __future__ import annotations

import ast
import copy
from dataclasses import fields, replace
import hashlib
import inspect
import json
import os
import re
import struct
import subprocess
import sys
import unittest

from eval import persona_v2_raw_domain_renderer as renderer
from eval import persona_v2_raw_domain_validator as validator
from eval import persona_v2_variant_catalog as variant_catalog


MATRIX = {
    "dicom-part10": (
        1,
        32,
        64,
        5_208,
        4_100,
        263_508,
        "frames",
        "number-of-frames-and-contiguous-native-pixel-frames",
        "dcm",
        "application/dicom",
        "domain_binary",
        "dicom-part10-multiframe-grayscale-byte-sc-explicit-vr-little-endian-v3",
    ),
    "pcap": (
        1,
        2_048,
        4_096,
        146,
        122,
        499_736,
        "packets",
        "classic-pcap-packet-records",
        "pcap",
        "application/vnd.tcpdump.pcap",
        "domain_binary",
        "classic-pcap-ethernet-ipv4-udp-fixed-record-v2",
    ),
}

EXPECTED_VARIANTS = tuple(sorted(MATRIX))
EXPECTED_RENDERER_BYTES = 3_680
EXPECTED_RENDERER_SHA256 = (
    "63e84afe98283aad93427e2b8260b7dfc30e9f0b20af3ee4d9968f7459872303"
)
EXPECTED_VALIDATOR_BYTES = 3_970
EXPECTED_VALIDATOR_SHA256 = (
    "c305e733011f2791237b3ffd6d7e3e044330bf81201794f2e85702edffd88a82"
)
EXPECTED_MATRIX_PAYLOAD_SHA256 = (
    "c3b157a903ab2d98659776c562e3d72160956453c8e8f772f1dc617074f85f7f"
)
EXPECTED_PAYLOAD_PINS = {
    ("dicom-part10", 1): (
        5_208,
        "d79154065192d6ccd8b50745c993357ded2eba02e1e9031cd44c0b4622b12336",
    ),
    ("dicom-part10", 64): (
        263_508,
        "39e73d49cbb8b8e5442a5c6dbde0af54e47a48e5207a585e2776218b27345f22",
    ),
    ("pcap", 1): (
        146,
        "4ea46c3e5d7db2d525bdc18499b0dd86639f67302207b2e4d375b78c3702b05d",
    ),
    ("pcap", 4_096): (
        499_736,
        "aa5b778adb4670681b0c0ff0512d3f3fa76d5581be5a2e0bd683b913e8e2e163",
    ),
}


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


class RenderRequestSubclass(renderer.RawDomainRenderRequest):
    pass


class ValidationRequestSubclass(validator.RawDomainValidationRequest):
    pass


def _checksum(data):
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for offset in range(0, len(data), 2):
        total += (data[offset] << 8) | data[offset + 1]
        total = (total & 0xFFFF) + (total >> 16)
    total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _parse_dicom(data):
    if data[:128] != b"\x00" * 128 or data[128:132] != b"DICM":
        raise AssertionError("not a DICOM Part 10 body")
    long_vrs = {b"OB", b"OD", b"OF", b"OL", b"OW", b"SQ", b"UC", b"UN", b"UR", b"UT"}
    offset = 132
    rows = []
    while offset < len(data):
        start = offset
        group, element = struct.unpack_from("<HH", data, offset)
        vr = data[offset + 4 : offset + 6]
        if vr in long_vrs:
            if data[offset + 6 : offset + 8] != b"\x00\x00":
                raise AssertionError("bad DICOM long-VR reserved bytes")
            length = struct.unpack_from("<I", data, offset + 8)[0]
            value_offset = offset + 12
        else:
            length = struct.unpack_from("<H", data, offset + 6)[0]
            value_offset = offset + 8
        if length == 0xFFFFFFFF:
            raise AssertionError("undefined DICOM length")
        end = value_offset + length
        if end > len(data):
            raise AssertionError("DICOM element out of bounds")
        rows.append(
            {
                "end": end,
                "length": length,
                "start": start,
                "tag": (group, element),
                "value": data[value_offset:end],
                "value_offset": value_offset,
                "vr": vr,
            }
        )
        offset = end
    if offset != len(data):
        raise AssertionError("DICOM trailing bytes")
    return rows


class PersonaV2RawDomainRendererValidatorTests(unittest.TestCase):
    def _render(self, variant, complexity):
        return renderer.render_raw_domain(
            renderer.RawDomainRenderRequest(2, variant, complexity)
        )

    def _validation_request(self, variant, complexity, data=None):
        rendered = self._render(variant, complexity)
        return validator.RawDomainValidationRequest(
            2,
            variant,
            complexity,
            rendered.data if data is None else data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kio_path_media_type,
            rendered.expected_offline_disposition,
        )

    def _render_and_validate(self, variant, complexity):
        rendered = self._render(variant, complexity)
        receipt = validator.validate_raw_domain_payload(
            self._validation_request(variant, complexity, rendered.data)
        )
        return rendered, receipt

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
            self.assertEqual(value["variant_count"], 2)
            self.assertIs(value["byte_stress_lane_implemented"], False)
            self.assertIs(value["payload_runtime_standard_library_only"], True)
            self.assertEqual(
                value["canonical_limits"]["max_rendered_bytes"], 512 * 1024
            )
            self.assertTrue(all(flag is False for flag in value["authority"].values()))
            self.assertTrue(
                value["coverage_contract"][
                    "non_container_special_raw_domain_variants_complete"
                ]
            )
            for excluded in (
                "archive_gzip_tar_zip_variants_in_scope",
                "document_variants_in_scope",
                "image_variants_in_scope",
                "media_variants_in_scope",
            ):
                self.assertIs(value["coverage_contract"][excluded], False)

        forged = copy.deepcopy(renderer_value)
        forged["variant_rows"][0]["raw_byte_formula"][
            "maximum_rendered_bytes"
        ] += 1
        with self.assertRaises(renderer.PersonaV2RawDomainRendererError):
            renderer.validate_renderer_contract(forged)
        forged = copy.deepcopy(validator_value)
        forged["independence_contract"]["imports_renderer_module"] = True
        with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
            validator.validate_validator_contract(forged)

        renderer_value["variant_rows"][0]["variant_id"] = "poisoned"
        validator_value["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "dicom-part10",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "dicom-part10",
        )

    def test_hardcoded_matrix_common_rows_and_exact_catalog_slice(self):
        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        catalog = variant_catalog.build_variant_catalog()
        upstream_rows = {row["variant_id"]: row for row in catalog["variant_rows"]}
        shared = {
            "complexity",
            "content_media_type",
            "expected_kio_path_media_type",
            "expected_offline_disposition",
            "family",
            "filename_extension",
            "format_limits",
            "gate_role",
            "raw_byte_formula",
            "render_template",
            "variant_id",
        }
        self.assertEqual(set(renderer_rows), set(MATRIX))
        self.assertEqual(set(validator_rows), set(MATRIX))
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
                self.assertEqual(row["family"], family)
                self.assertEqual(row["render_template"], template)
                self.assertEqual(row["gate_role"], "raw_only")
                self.assertEqual(
                    row["expected_kio_path_media_type"], "application/octet-stream"
                )
                self.assertEqual(
                    row["expected_offline_disposition"], "unsupported_binary"
                )
            self.assertEqual(
                {key: renderer_rows[variant][key] for key in shared},
                {key: validator_rows[variant][key] for key in shared},
            )
            upstream = upstream_rows[variant]
            for key in (
                "family",
                "filename_extension",
                "content_media_type",
                "expected_kio_path_media_type",
                "expected_offline_disposition",
                "gate_role",
            ):
                self.assertEqual(renderer_rows[variant][key], upstream[key])
            self.assertEqual(upstream["complexity_contract"]["minimum"], minimum)
            self.assertEqual(upstream["complexity_contract"]["maximum"], maximum)
            self.assertEqual(
                upstream["complexity_contract"]["complexity_unit"], measure
            )

        excluded = {
            row["variant_id"]
            for row in catalog["variant_rows"]
            if row["family"] in {"image", "media", "docx", "xlsx", "pptx"}
            or row["variant_id"].endswith(("-zip", "-ustar", "-gzip"))
            or row["variant_id"] in {"npz", "ifczip"}
        }
        self.assertFalse(set(EXPECTED_VARIANTS) & excluded)
        marginals = catalog["persona_variant_marginals"]
        self.assertEqual(
            {
                "tiny": sum(
                    row["tiny_smoke_count"]
                    for row in marginals
                    if row["variant_id"] in EXPECTED_VARIANTS
                ),
                "pilot": sum(
                    row["pilot_count"]
                    for row in marginals
                    if row["variant_id"] in EXPECTED_VARIANTS
                ),
                "full": sum(
                    row["full_count"]
                    for row in marginals
                    if row["variant_id"] in EXPECTED_VARIANTS
                ),
            },
            {"tiny": 9, "pilot": 52, "full": 513},
        )

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
                    with self.assertRaises(renderer.PersonaV2RawDomainRendererError):
                        renderer.target_bytes_for(variant, bad)
                    with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                        validator.target_bytes_for(variant, bad)
        for bad_variant in ("unknown", b"pcap", [], StrSubclass("pcap")):
            with self.assertRaises(renderer.PersonaV2RawDomainRendererError):
                renderer.target_bytes_for(bad_variant, 1)
            with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                validator.target_bytes_for(bad_variant, 1)

    def test_min_middle_max_render_validate_receipts_and_pins_are_exact(self):
        digest = hashlib.sha256()
        forbidden = re.compile(
            rb"(?:p[0-9]{2}-src-[0-9]{6}|(?:sha256|digest)\s*[:=]|[0-9a-f]{64})",
            re.IGNORECASE,
        )
        for variant, exact in MATRIX.items():
            minimum, middle, maximum, base, increment, *_ = exact
            for complexity in (minimum, middle, maximum):
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(variant, complexity)
                    second = self._render(variant, complexity)
                    expected_bytes = base + (complexity - minimum) * increment
                    self.assertEqual(first, second)
                    self.assertIs(type(first.data), bytes)
                    self.assertEqual(len(first.data), expected_bytes)
                    self.assertEqual(first.target_bytes, expected_bytes)
                    self.assertIsNone(forbidden.search(first.data))
                    self.assertEqual(receipt["byte_length"], expected_bytes)
                    self.assertEqual(receipt["target_bytes"], expected_bytes)
                    self.assertEqual(receipt["observed_local_complexity"], complexity)
                    self.assertEqual(
                        receipt["observed_complexity_measure"], exact[6]
                    )
                    self.assertIs(receipt["actual_chunks_attested"], False)
                    self.assertIs(receipt["kio_execution_attested"], False)
                    self.assertIs(receipt["structure_validated"], True)
                    self.assertIs(receipt["identity_tokens_absent"], True)
                    if variant == "pcap":
                        self.assertEqual(receipt["packet_count"], complexity)
                        self.assertEqual(receipt["frame_count"], 0)
                        self.assertEqual(receipt["pixel_bytes"], 0)
                        self.assertEqual(receipt["private_padding_bytes"], 0)
                    else:
                        self.assertEqual(receipt["packet_count"], 0)
                        self.assertEqual(receipt["frame_count"], complexity)
                        self.assertEqual(receipt["pixel_bytes"], 4_096 * complexity)
                        self.assertEqual(receipt["private_padding_bytes"], 256)
                    digest.update(variant.encode("ascii") + b"\0")
                    digest.update(str(complexity).encode("ascii") + b"\0")
                    digest.update(first.data)
                    pin = EXPECTED_PAYLOAD_PINS.get((variant, complexity))
                    if pin is not None:
                        self.assertEqual(
                            (len(first.data), hashlib.sha256(first.data).hexdigest()),
                            pin,
                        )
        self.assertEqual(digest.hexdigest(), EXPECTED_MATRIX_PAYLOAD_SHA256)

    def test_pcap_records_have_exact_lengths_and_ipv4_udp_checksums(self):
        data = self._render("pcap", 3).data
        self.assertEqual(
            struct.unpack_from("<IHHIIII", data, 0),
            (0xA1B2C3D4, 2, 4, 0, 0, 65_535, 1),
        )
        offset = 24
        for packet_ordinal in range(1, 4):
            ts_sec, ts_usec, included, original = struct.unpack_from(
                "<IIII", data, offset
            )
            self.assertEqual(ts_sec, 1_700_000_000 + packet_ordinal)
            self.assertEqual(ts_usec, (packet_ordinal * 7_919) % 1_000_000)
            self.assertEqual((included, original), (106, 106))
            offset += 16
            frame = data[offset : offset + included]
            offset += included
            self.assertEqual(frame[12:14], b"\x08\x00")
            ipv4 = frame[14:34]
            self.assertEqual(_checksum(ipv4), 0)
            self.assertEqual(struct.unpack_from(">H", ipv4, 2)[0], 92)
            udp = frame[34:42]
            payload = frame[42:]
            udp_length = struct.unpack_from(">H", udp, 4)[0]
            self.assertEqual(udp_length, 72)
            pseudo = ipv4[12:20] + b"\x00\x11" + struct.pack(">H", udp_length)
            self.assertEqual(_checksum(pseudo + udp + payload), 0)
            self.assertNotEqual(struct.unpack_from(">H", udp, 6)[0], 0)
        self.assertEqual(offset, len(data))

    def test_dicom_is_fixed_part10_explicit_vr_defined_length_and_bounded(self):
        sop_instance_uids = set()
        for frames in (1, 64):
            data = self._render("dicom-part10", frames).data
            rows = _parse_dicom(data)
            by_tag = {row["tag"]: row for row in rows}
            self.assertEqual(len(by_tag), len(rows))
            self.assertEqual(rows[0]["tag"], (0x0002, 0x0000))
            self.assertEqual(rows[0]["vr"], b"UL")
            group_length = struct.unpack("<I", rows[0]["value"])[0]
            first_dataset = by_tag[(0x0008, 0x0016)]["start"]
            self.assertEqual(group_length, first_dataset - rows[0]["end"])
            self.assertEqual(
                by_tag[(0x0002, 0x0010)]["value"],
                b"1.2.840.10008.1.2.1\x00",
            )
            self.assertEqual(
                by_tag[(0x0008, 0x0016)]["value"],
                b"1.2.840.10008.5.1.4.1.1.7.2\x00",
            )
            self.assertEqual(
                by_tag[(0x0002, 0x0002)]["value"],
                by_tag[(0x0008, 0x0016)]["value"],
            )
            self.assertEqual(
                by_tag[(0x0002, 0x0003)]["value"],
                by_tag[(0x0008, 0x0018)]["value"],
            )
            sop_instance_uids.add(by_tag[(0x0008, 0x0018)]["value"])
            self.assertFalse(any(row["vr"] == b"SQ" for row in rows))
            self.assertTrue(all(row["length"] != 0xFFFFFFFF for row in rows))
            self.assertTrue(all(row["length"] % 2 == 0 for row in rows))
            self.assertEqual(by_tag[(0x0011, 0x1001)]["length"], 256)
            mandatory_module_tags = {
                (0x0008, 0x0020),
                (0x0008, 0x0030),
                (0x0008, 0x0050),
                (0x0008, 0x0060),
                (0x0008, 0x0064),
                (0x0008, 0x0090),
                (0x0010, 0x0010),
                (0x0010, 0x0020),
                (0x0010, 0x0030),
                (0x0010, 0x0040),
                (0x0018, 0x2001),
                (0x0020, 0x000D),
                (0x0020, 0x000E),
                (0x0020, 0x0010),
                (0x0020, 0x0011),
                (0x0020, 0x0013),
                (0x0020, 0x0020),
                (0x0028, 0x0009),
                (0x0028, 0x0301),
                (0x0028, 0x1052),
                (0x0028, 0x1053),
                (0x0028, 0x1054),
                (0x2050, 0x0020),
            }
            self.assertTrue(mandatory_module_tags <= set(by_tag))
            self.assertEqual(
                by_tag[(0x0028, 0x0008)]["value"], f"{frames:02d}".encode()
            )
            page_vector = b"\\".join(
                f"{ordinal:03d}".encode("ascii")
                for ordinal in range(1, frames + 1)
            ) + b" "
            self.assertEqual(by_tag[(0x0018, 0x2001)]["value"], page_vector)
            self.assertEqual(
                by_tag[(0x0028, 0x0009)]["value"],
                struct.pack("<HH", 0x0018, 0x2001),
            )
            self.assertEqual(by_tag[(0x0028, 0x0010)]["value"], b"@\x00")
            self.assertEqual(by_tag[(0x0028, 0x0011)]["value"], b"@\x00")
            self.assertEqual(by_tag[(0x0028, 0x0100)]["value"], b"\x08\x00")
            self.assertEqual(by_tag[(0x0028, 0x0301)]["value"], b"NO")
            self.assertEqual(by_tag[(0x0028, 0x1052)]["value"], b"0 ")
            self.assertEqual(by_tag[(0x0028, 0x1053)]["value"], b"1 ")
            self.assertEqual(by_tag[(0x0028, 0x1054)]["value"], b"US")
            self.assertEqual(by_tag[(0x2050, 0x0020)]["value"], b"IDENTITY")
            self.assertEqual(by_tag[(0x7FE0, 0x0010)]["vr"], b"OB")
            self.assertEqual(by_tag[(0x7FE0, 0x0010)]["length"], frames * 4_096)
            self.assertLessEqual(by_tag[(0x7FE0, 0x0010)]["length"], 262_144)
        self.assertEqual(len(sop_instance_uids), 2)
        all_sop_instance_uids = {
            {
                row["tag"]: row
                for row in _parse_dicom(
                    self._render("dicom-part10", frames).data
                )
            }[(0x0008, 0x0018)]["value"]
            for frames in range(1, 65)
        }
        self.assertEqual(len(all_sop_instance_uids), 64)
        self.assertTrue(all(len(value) == 44 for value in all_sop_instance_uids))
        one_frame_by_tag = {
            row["tag"]: row
            for row in _parse_dicom(self._render("dicom-part10", 1).data)
        }
        study_series_uids = {
            one_frame_by_tag[(0x0020, 0x000D)]["value"],
            one_frame_by_tag[(0x0020, 0x000E)]["value"],
        }
        self.assertEqual(len(study_series_uids), 2)
        self.assertTrue(study_series_uids.isdisjoint(all_sop_instance_uids))
        self.assertEqual(len(study_series_uids | all_sop_instance_uids), 66)

    def test_request_exact_types_metadata_and_validator_import_independence(self):
        self.assertEqual(
            tuple(field.name for field in fields(renderer.RawDomainRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(field.name for field in fields(validator.RawDomainValidationRequest)),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(
            set(renderer.REQUEST_FIELDS) & set(renderer.PROHIBITED_IDENTITY_FIELDS)
        )
        self.assertFalse(
            set(validator.REQUEST_FIELDS) & set(validator.PROHIBITED_IDENTITY_FIELDS)
        )

        valid_render = renderer.RawDomainRenderRequest(2, "pcap", 1)
        for request in (
            RenderRequestSubclass(2, "pcap", 1),
            replace(valid_render, schema_version=True),
            replace(valid_render, schema_version=2.0),
            replace(valid_render, variant=StrSubclass("pcap")),
            replace(valid_render, target_complexity=True),
        ):
            with self.assertRaises(renderer.PersonaV2RawDomainRendererError):
                renderer.render_raw_domain(request)

        valid = self._validation_request("pcap", 1)
        for request in (
            ValidationRequestSubclass(
                *(getattr(valid, field.name) for field in fields(valid))
            ),
            replace(valid, schema_version=True),
            replace(valid, data=bytearray(valid.data)),
            replace(valid, data=BytesSubclass(valid.data)),
            replace(valid, extension="PCAP"),
            replace(valid, content_media_type="application/octet-stream"),
            replace(valid, expected_kio_path_media_type="application/vnd.tcpdump.pcap"),
            replace(valid, expected_offline_disposition="incidental_sniff"),
        ):
            with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                validator.validate_raw_domain_payload(request)

        tree = ast.parse(inspect.getsource(validator))
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for forbidden in (
            "persona_v2_raw_domain_renderer",
            "persona_v2_variant_catalog",
            "persona_v2_contract",
            "planning",
        ):
            self.assertFalse(any(forbidden in name for name in imported))

    def test_pcap_and_dicom_adversarial_mutations_fail_closed(self):
        pcap = self._render("pcap", 2).data
        pcap_cases = []
        candidate = bytearray(pcap)
        candidate[0] ^= 1
        pcap_cases.append(bytes(candidate))
        candidate = bytearray(pcap)
        struct.pack_into("<I", candidate, 32, 105)
        pcap_cases.append(bytes(candidate))
        candidate = bytearray(pcap)
        candidate[64] ^= 1
        pcap_cases.append(bytes(candidate))
        candidate = bytearray(pcap)
        candidate[80] ^= 1
        pcap_cases.append(bytes(candidate))
        candidate = bytearray(pcap)
        candidate[90] ^= 1
        pcap_cases.append(bytes(candidate))
        for index, body in enumerate(pcap_cases):
            with self.subTest(format="pcap", case=index):
                with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                    validator.validate_raw_domain_payload(
                        self._validation_request("pcap", 2, body)
                    )

        dicom = self._render("dicom-part10", 2).data
        dicom_cases = []
        candidate = bytearray(dicom)
        candidate[128] ^= 1
        dicom_cases.append(bytes(candidate))
        candidate = bytearray(dicom)
        struct.pack_into("<I", candidate, 140, 0)
        dicom_cases.append(bytes(candidate))
        transfer = dicom.index(struct.pack("<HH", 0x0002, 0x0010))
        candidate = bytearray(dicom)
        candidate[transfer + 8] = ord("9")
        dicom_cases.append(bytes(candidate))
        frames_tag = dicom.index(struct.pack("<HH", 0x0028, 0x0008))
        candidate = bytearray(dicom)
        candidate[frames_tag + 8 : frames_tag + 10] = b"03"
        dicom_cases.append(bytes(candidate))
        private_tag = dicom.index(struct.pack("<HH", 0x0011, 0x1001))
        candidate = bytearray(dicom)
        candidate[private_tag + 12] ^= 1
        dicom_cases.append(bytes(candidate))
        candidate = bytearray(dicom)
        struct.pack_into("<I", candidate, private_tag + 8, 258)
        dicom_cases.append(bytes(candidate))
        pixel_tag = dicom.index(struct.pack("<HH", 0x7FE0, 0x0010))
        candidate = bytearray(dicom)
        candidate[pixel_tag + 12] ^= 1
        dicom_cases.append(bytes(candidate))
        candidate = bytearray(dicom)
        struct.pack_into("<I", candidate, pixel_tag + 8, 0xFFFFFFFF)
        dicom_cases.append(bytes(candidate))
        for index, body in enumerate(dicom_cases):
            with self.subTest(format="dicom", case=index):
                with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                    validator.validate_raw_domain_payload(
                        self._validation_request("dicom-part10", 2, body)
                    )

        for variant, complexity in (("pcap", 2), ("dicom-part10", 2)):
            body = self._render(variant, complexity).data
            for malformed in (body[:-1], body + b"\x00"):
                with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                    validator.validate_raw_domain_payload(
                        self._validation_request(variant, complexity, malformed)
                    )
        pcap_one = self._render("pcap", 1).data
        dicom_one = self._render("dicom-part10", 1).data
        for variant, body in (
            ("pcap", dicom_one),
            ("dicom-part10", pcap_one),
        ):
            with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
                validator.validate_raw_domain_payload(
                    self._validation_request(variant, 1, body)
                )

        candidate = bytearray(pcap)
        candidate[82:96] = b"p01-src-000001"
        with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
            validator.validate_raw_domain_payload(
                self._validation_request("pcap", 2, bytes(candidate))
            )
        over_cap = b"x" * (validator.MAX_RENDERED_BYTES + 1)
        with self.assertRaises(validator.PersonaV2RawDomainValidatorError):
            validator.validate_raw_domain_payload(
                self._validation_request("pcap", 1, over_cap)
            )

    def test_contract_and_payloads_are_hashseed_timezone_locale_independent(self):
        script = """
import hashlib, json
from eval import persona_v2_raw_domain_renderer as r
from eval import persona_v2_raw_domain_validator as v
d=hashlib.sha256()
for name, values in [('dicom-part10',(1,32,64)),('pcap',(1,2048,4096))]:
    for value in values:
        body=r.render_raw_domain(r.RawDomainRenderRequest(2,name,value)).data
        d.update(name.encode('ascii')+b'\\0')
        d.update(str(value).encode('ascii')+b'\\0')
        d.update(body)
print(json.dumps({
    'renderer':[len(r.canonical_json_bytes(r.build_renderer_contract())),r.renderer_contract_sha256()],
    'validator':[len(v.canonical_json_bytes(v.build_validator_contract())),v.validator_contract_sha256()],
    'payload':d.hexdigest(),
},sort_keys=True))
"""
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
            timeout=30,
        )
        self.assertEqual(
            json.loads(output),
            {
                "payload": EXPECTED_MATRIX_PAYLOAD_SHA256,
                "renderer": [EXPECTED_RENDERER_BYTES, EXPECTED_RENDERER_SHA256],
                "validator": [EXPECTED_VALIDATOR_BYTES, EXPECTED_VALIDATOR_SHA256],
            },
        )


if __name__ == "__main__":
    unittest.main()
