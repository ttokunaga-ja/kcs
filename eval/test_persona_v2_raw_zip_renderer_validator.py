import copy
from dataclasses import fields, replace
import hashlib
import inspect
import io
import os
import struct
import subprocess
import sys
import unittest
import zipfile
import zlib

from eval import persona_v2_raw_zip_renderer as renderer
from eval import persona_v2_raw_zip_validator as validator
from eval import persona_v2_variant_catalog as variant_catalog


GENERIC_VARIANTS = (
    "archive-zip",
    "ats-zip",
    "cde-zip",
    "close-package-zip",
    "course-package-zip",
    "crm-zip",
    "data-room-zip",
    "dms-zip",
    "edc-zip",
    "evidence-zip",
    "foia-zip",
    "instrument-export-zip",
    "model-metadata-zip",
    "product-export-zip",
    "qms-zip",
    "recording-project-zip",
    "source-export-zip",
    "ticket-zip",
    "warehouse-zip",
)

EXPECTED_VARIANTS = tuple(sorted((*GENERIC_VARIANTS, "ifczip", "npz")))

MATRIX = {
    **{
        variant: {
            "minimum": 1,
            "middle": 32,
            "maximum": 64,
            "measure": "members",
            "counting_rule": "non-directory-stored-members",
            "extension": "zip",
            "template": "bounded-stored-zip-record-members-v2",
            "safety": "bounded-archive-v2",
        }
        for variant in GENERIC_VARIANTS
    },
    "ifczip": {
        "minimum": 1,
        "middle": 1,
        "maximum": 1,
        "measure": "spf-members",
        "counting_rule": "ifc-spf-members",
        "extension": "ifczip",
        "template": "bounded-stored-ifc4-spf-zip-v2",
        "safety": "bounded-ifczip-v2",
    },
    "npz": {
        "minimum": 1,
        "middle": 500_000,
        "maximum": 1_000_000,
        "measure": "array-elements",
        "counting_rule": "elements-in-the-single-canonical-array",
        "extension": "npz",
        "template": "bounded-stored-npy-array-zip-v2",
        "safety": "bounded-npz-v2",
    },
}

EXPECTED_RENDERER_BYTES = 18_670
EXPECTED_RENDERER_SHA256 = (
    "ecb621ade5bd81a3f5962a4ee10ea018c14c2ecd6d93a8e565378ba4065a2a4d"
)
EXPECTED_VALIDATOR_BYTES = 20_737
EXPECTED_VALIDATOR_SHA256 = (
    "4dc04c3689bbef7253a76dd7f046af5cf26734386494c4296c56fd080f6fd0d6"
)

PAYLOAD_PINS = {
    ("archive-zip", 1): (
        4_096,
        "7f3489f71d0887996a7cc635f9588d47f122dcae6d8aec89a73a52f4474642a6",
    ),
    ("archive-zip", 32): (
        131_072,
        "a6c1a03cc2ca7615484db6a8de86777cb19245d32000c617bdb42b04b8c49e8c",
    ),
    ("warehouse-zip", 64): (
        262_144,
        "d0c5977f38d2ac44ded53071b575213a56c550bc3f635694264f0414c03ed73e",
    ),
    ("ifczip", 1): (
        4_096,
        "133df7c119ff6c632264238361748f9c34c4b86bb8b3d4f46376dcce7c114c94",
    ),
    ("npz", 1): (
        248,
        "e5aa5c00ab88be368a6f62b824a00a6867cac5acf5cce6f618e1ccb1c6302e35",
    ),
    ("npz", 500_000): (
        2_000_244,
        "35e1044336f72dd8e3d87cbbdb373133afa1550fda685133d583d3cad0caab0a",
    ),
    ("npz", 1_000_000): (
        4_000_244,
        "e1149800bfb9db13cb964d89e3f9e571f627b3ccb4e552b94d0b1a0629a43e03",
    ),
}


class IntSubclass(int):
    pass


class StrSubclass(str):
    pass


class BytesSubclass(bytes):
    pass


class RenderRequestSubclass(renderer.RawZipRenderRequest):
    pass


class ValidationRequestSubclass(validator.RawZipValidationRequest):
    pass


class PersonaV2RawZipRendererValidatorTests(unittest.TestCase):
    def _render(self, variant, complexity):
        return renderer.render_raw_zip(
            renderer.RawZipRenderRequest(2, variant, complexity)
        )

    def _validation_request(self, variant, complexity):
        rendered = self._render(variant, complexity)
        return validator.RawZipValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kio_path_media_type,
            rendered.expected_offline_disposition,
        )

    def _render_and_validate(self, variant, complexity):
        rendered = self._render(variant, complexity)
        request = validator.RawZipValidationRequest(
            2,
            variant,
            complexity,
            rendered.data,
            rendered.extension,
            rendered.content_media_type,
            rendered.expected_kio_path_media_type,
            rendered.expected_offline_disposition,
        )
        return rendered, validator.validate_raw_zip_payload(request)

    @staticmethod
    def _central_offset(data):
        return struct.unpack_from("<I", data, len(data) - 6)[0]

    @classmethod
    def _rewrite_single_member_payload(cls, data, transform):
        result = bytearray(data)
        name_length = struct.unpack_from("<H", result, 26)[0]
        extra_length = struct.unpack_from("<H", result, 28)[0]
        payload_length = struct.unpack_from("<I", result, 18)[0]
        payload_start = 30 + name_length + extra_length
        payload_end = payload_start + payload_length
        old_payload = bytes(result[payload_start:payload_end])
        new_payload = transform(old_payload)
        if len(new_payload) != len(old_payload):
            raise AssertionError("adversarial payload transform changed length")
        result[payload_start:payload_end] = new_payload
        checksum = zlib.crc32(new_payload) & 0xFFFFFFFF
        struct.pack_into("<I", result, 14, checksum)
        struct.pack_into("<I", result, cls._central_offset(result) + 16, checksum)
        return bytes(result)

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
            self.assertEqual(value["variant_count"], 21)
            self.assertIs(value["byte_stress_lane_implemented"], False)
            self.assertEqual(
                value["canonical_limits"]["max_rendered_bytes"], 4 * 2**20
            )
            self.assertEqual(
                value["canonical_limits"]["max_expanded_container_bytes"],
                8 * 2**20,
            )
            self.assertEqual(
                value["canonical_limits"]["max_container_members"], 64
            )
            for name, flag in value["authority"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)
            for name, flag in value["payload_identity_policy"].items():
                self.assertIs(type(flag), bool, name)
                self.assertIs(flag, False, name)

        forged_renderer = copy.deepcopy(renderer_value)
        forged_renderer["zip_subset"]["zip64_allowed"] = True
        with self.assertRaises(renderer.PersonaV2RawZipRendererError):
            renderer.validate_renderer_contract(forged_renderer)
        forged_validator = copy.deepcopy(validator_value)
        forged_validator["independence_contract"]["imports_renderer_module"] = True
        with self.assertRaises(validator.PersonaV2RawZipValidatorError):
            validator.validate_validator_contract(forged_validator)

        renderer_value["variant_rows"][0]["variant_id"] = "poisoned"
        validator_value["variant_rows"][0]["variant_id"] = "poisoned"
        self.assertEqual(
            renderer.build_renderer_contract()["variant_rows"][0]["variant_id"],
            "archive-zip",
        )
        self.assertEqual(
            validator.build_validator_contract()["variant_rows"][0]["variant_id"],
            "archive-zip",
        )

    def test_hardcoded_matrix_upstream_metadata_and_marginal_coverage(self):
        renderer_rows = {
            row["variant_id"]: row
            for row in renderer.build_renderer_contract()["variant_rows"]
        }
        validator_rows = {
            row["variant_id"]: row
            for row in validator.build_validator_contract()["variant_rows"]
        }
        upstream = variant_catalog.build_variant_catalog()
        upstream_rows = {
            row["variant_id"]: row for row in upstream["variant_rows"]
        }
        selected_upstream = {
            variant_id
            for variant_id, row in upstream_rows.items()
            if row["family"] == "domain_binary"
            and row["gate_role"] == "raw_only"
            and row["content_media_type"] == "application/zip"
        }
        self.assertEqual(set(MATRIX), set(EXPECTED_VARIANTS))
        self.assertEqual(set(renderer_rows), selected_upstream)
        self.assertEqual(set(validator_rows), selected_upstream)

        shared = {
            "complexity",
            "compound_suffix_parts",
            "content_media_type",
            "expected_kio_path_media_type",
            "expected_offline_disposition",
            "family",
            "filename_extension",
            "gate_role",
            "raw_byte_formula",
            "render_template",
            "safety_profile_id",
            "variant_id",
        }
        for variant, exact in MATRIX.items():
            with self.subTest(variant=variant):
                expected_complexity = {
                    "counting_rule": exact["counting_rule"],
                    "inclusive_maximum": exact["maximum"],
                    "inclusive_minimum": exact["minimum"],
                    "measure": exact["measure"],
                }
                for rows in (renderer_rows, validator_rows):
                    row = rows[variant]
                    self.assertEqual(row["complexity"], expected_complexity)
                    self.assertEqual(row["filename_extension"], exact["extension"])
                    self.assertEqual(row["compound_suffix_parts"], [exact["extension"]])
                    self.assertEqual(row["content_media_type"], "application/zip")
                    self.assertEqual(row["expected_kio_path_media_type"], "application/octet-stream")
                    self.assertEqual(row["expected_offline_disposition"], "unsupported_binary")
                    self.assertEqual(row["family"], "domain_binary")
                    self.assertEqual(row["gate_role"], "raw_only")
                    self.assertEqual(row["render_template"], exact["template"])
                    self.assertEqual(row["safety_profile_id"], exact["safety"])
                self.assertEqual(
                    {key: renderer_rows[variant][key] for key in shared},
                    {key: validator_rows[variant][key] for key in shared},
                )
                catalog_row = upstream_rows[variant]
                for key in (
                    "compound_suffix_parts",
                    "content_media_type",
                    "expected_kio_path_media_type",
                    "expected_offline_disposition",
                    "family",
                    "filename_extension",
                    "gate_role",
                    "safety_profile_id",
                    "variant_id",
                ):
                    self.assertEqual(renderer_rows[variant][key], catalog_row[key])
                self.assertEqual(
                    catalog_row["complexity_contract"]["minimum"],
                    exact["minimum"],
                )
                self.assertEqual(
                    catalog_row["complexity_contract"]["maximum"],
                    exact["maximum"],
                )
                self.assertEqual(
                    catalog_row["complexity_contract"]["complexity_unit"],
                    exact["measure"],
                )

        marginals = [
            row
            for row in upstream["persona_variant_marginals"]
            if row["variant_id"] in EXPECTED_VARIANTS
        ]
        self.assertEqual(sum(row["full_count"] for row in marginals), 4_047)
        self.assertEqual(sum(row["pilot_count"] for row in marginals), 406)
        self.assertEqual(sum(row["tiny_smoke_count"] for row in marginals), 83)

    def test_all_variants_render_validate_at_minimum_middle_and_maximum(self):
        for variant, exact in MATRIX.items():
            complexities = sorted(
                {exact["minimum"], exact["middle"], exact["maximum"]}
            )
            previous = None
            for complexity in complexities:
                with self.subTest(variant=variant, complexity=complexity):
                    first, receipt = self._render_and_validate(variant, complexity)
                    second = self._render(variant, complexity)
                    self.assertEqual(first, second)
                    self.assertEqual(
                        len(first.data),
                        renderer.target_bytes_for(variant, complexity),
                    )
                    self.assertEqual(
                        first.target_bytes,
                        validator.target_bytes_for(variant, complexity),
                    )
                    self.assertEqual(
                        receipt["observed_local_complexity"], complexity
                    )
                    self.assertEqual(
                        receipt["observed_complexity_measure"], exact["measure"]
                    )
                    self.assertLessEqual(
                        receipt["expanded_bytes"], 8 * 2**20
                    )
                    self.assertTrue(receipt["structure_validated"])
                    self.assertTrue(receipt["zip_subset_validated"])
                    self.assertFalse(receipt["actual_chunks_attested"])
                    self.assertFalse(receipt["kio_execution_attested"])
                    if variant in GENERIC_VARIANTS:
                        self.assertEqual(receipt["member_count"], complexity)
                        if previous is not None:
                            self.assertEqual(
                                len(first.data) - previous,
                                4_096 * (complexity - previous_complexity),
                            )
                    else:
                        self.assertEqual(receipt["member_count"], 1)
                    if variant == "npz":
                        self.assertEqual(
                            len(first.data), 248 + 4 * (complexity - 1)
                        )
                    previous = len(first.data)
                    previous_complexity = complexity

    def test_payload_hash_pins_cover_each_distinct_template_and_bounds(self):
        for (variant, complexity), (byte_length, digest) in PAYLOAD_PINS.items():
            with self.subTest(variant=variant, complexity=complexity):
                rendered, _ = self._render_and_validate(variant, complexity)
                self.assertEqual(len(rendered.data), byte_length)
                self.assertEqual(hashlib.sha256(rendered.data).hexdigest(), digest)

    def test_zip_wire_subset_is_stored_ordered_fixed_and_bounded(self):
        cases = (
            ("archive-zip", 64),
            ("ifczip", 1),
            ("npz", 1_000_000),
        )
        for variant, complexity in cases:
            with self.subTest(variant=variant):
                rendered = self._render(variant, complexity)
                self.assertTrue(
                    rendered.data.endswith(
                        b"PK\x05\x06" + rendered.data[-18:]
                    )
                )
                self.assertNotIn(b"PK\x07\x08", rendered.data)
                self.assertNotIn(b"PK\x06\x06", rendered.data)
                self.assertNotIn(b"PK\x06\x07", rendered.data)
                with zipfile.ZipFile(io.BytesIO(rendered.data), "r") as archive:
                    self.assertEqual(archive.comment, b"")
                    self.assertIsNone(archive.testzip())
                    infos = archive.infolist()
                    names = [info.filename for info in infos]
                    self.assertEqual(names, sorted(names))
                    self.assertEqual(len(names), len(set(names)))
                    self.assertLessEqual(len(names), 64)
                    self.assertLessEqual(
                        sum(info.file_size for info in infos), 8 * 2**20
                    )
                    for info in infos:
                        self.assertEqual(info.compress_type, zipfile.ZIP_STORED)
                        self.assertEqual(info.compress_size, info.file_size)
                        self.assertEqual(info.flag_bits, 0)
                        self.assertEqual(info.date_time, (1980, 1, 1, 0, 0, 0))
                        self.assertEqual(info.extra, b"")
                        self.assertEqual(info.comment, b"")
                        self.assertEqual(info.create_system, 0)
                        self.assertEqual(info.create_version, 20)
                        self.assertEqual(info.extract_version, 20)
                        self.assertEqual(info.internal_attr, 0)
                        self.assertEqual(info.external_attr, 0x20)

    def test_npz_is_strict_single_float32_c_order_npy_v1_subset(self):
        for complexity in (1, 9, 10, 99, 100, 999_999, 1_000_000):
            with self.subTest(complexity=complexity):
                rendered, receipt = self._render_and_validate("npz", complexity)
                with zipfile.ZipFile(io.BytesIO(rendered.data), "r") as archive:
                    self.assertEqual(archive.namelist(), ["array.npy"])
                    payload = archive.read("array.npy")
                self.assertEqual(payload[:8], b"\x93NUMPY\x01\x00")
                header_length = struct.unpack_from("<H", payload, 8)[0]
                header = payload[10 : 10 + header_length]
                self.assertEqual((10 + header_length) % 64, 0)
                self.assertEqual(header[-1:], b"\n")
                self.assertIn(b"'descr': '<f4'", header)
                self.assertIn(b"'fortran_order': False", header)
                self.assertIn(f"'shape': ({complexity},)".encode("ascii"), header)
                array = payload[10 + header_length :]
                self.assertEqual(len(array), 4 * complexity)
                self.assertEqual(array, b"\x00" * len(array))
                self.assertEqual(receipt["expanded_bytes"], len(payload))

    def test_ifczip_is_one_canonical_ifc4_spf_exchange_file(self):
        rendered, receipt = self._render_and_validate("ifczip", 1)
        with zipfile.ZipFile(io.BytesIO(rendered.data), "r") as archive:
            self.assertEqual(archive.namelist(), ["model.ifc"])
            payload = archive.read("model.ifc")
        self.assertTrue(payload.startswith(b"ISO-10303-21;\nHEADER;\n"))
        self.assertEqual(payload.count(b"FILE_SCHEMA(('IFC4'));"), 1)
        self.assertEqual(payload.count(b"#1=IFCPROJECT("), 1)
        self.assertTrue(payload.endswith(b"ENDSEC;\nEND-ISO-10303-21;\n"))
        self.assertEqual(receipt["member_count"], 1)
        self.assertEqual(receipt["expanded_bytes"], len(payload))

    def test_validator_rejects_zip_header_and_path_attacks(self):
        base = self._validation_request("archive-zip", 2)
        attacks = {}

        encrypted = bytearray(base.data)
        struct.pack_into("<H", encrypted, 6, 1)
        attacks["encryption"] = bytes(encrypted)

        descriptor = bytearray(base.data)
        struct.pack_into("<H", descriptor, 6, 8)
        attacks["data-descriptor"] = bytes(descriptor)

        deflated = bytearray(base.data)
        struct.pack_into("<H", deflated, 8, 8)
        attacks["compression"] = bytes(deflated)

        timestamp = bytearray(base.data)
        struct.pack_into("<H", timestamp, 10, 1)
        attacks["timestamp"] = bytes(timestamp)

        extra = bytearray(base.data)
        struct.pack_into("<H", extra, 28, 1)
        attacks["local-extra"] = bytes(extra)

        zip64 = bytearray(base.data)
        struct.pack_into("<I", zip64, 18, 0xFFFFFFFF)
        attacks["zip64-size"] = bytes(zip64)

        unsafe = bytearray(base.data)
        unsafe[30:33] = b"../"
        attacks["unsafe-dotdot"] = bytes(unsafe)

        reserved = bytearray(base.data)
        reserved[30:37] = b"con.txt"
        attacks["windows-device-path"] = bytes(reserved)

        duplicate = base.data.replace(b"record-0002.txt", b"record-0001.txt")
        self.assertEqual(len(duplicate), len(base.data))
        attacks["duplicate-name"] = duplicate

        too_many = bytearray(base.data)
        struct.pack_into("<H", too_many, len(too_many) - 12, 65)
        struct.pack_into("<H", too_many, len(too_many) - 10, 65)
        attacks["member-cap"] = bytes(too_many)

        archive_comment = bytearray(base.data)
        struct.pack_into("<H", archive_comment, len(archive_comment) - 2, 1)
        attacks["archive-comment"] = bytes(archive_comment)

        for name, data in attacks.items():
            with self.subTest(attack=name):
                with self.assertRaises(validator.PersonaV2RawZipValidatorError):
                    validator.validate_raw_zip_payload(replace(base, data=data))

    def test_validator_rejects_crc_identity_and_exact_regeneration_attacks(self):
        generic = self._validation_request("archive-zip", 1)
        corrupt = bytearray(generic.data)
        payload_start = 30 + struct.unpack_from("<H", corrupt, 26)[0]
        corrupt[payload_start] ^= 1
        with self.assertRaises(validator.PersonaV2RawZipValidatorError):
            validator.validate_raw_zip_payload(replace(generic, data=bytes(corrupt)))

        identity = generic.data.replace(b"xxxxxxxxxxx", b"source_id=x", 1)
        self.assertEqual(len(identity), len(generic.data))
        with self.assertRaises(validator.PersonaV2RawZipValidatorError):
            validator.validate_raw_zip_payload(replace(generic, data=identity))

        npz = self._validation_request("npz", 8)
        wrong_dtype = self._rewrite_single_member_payload(
            npz.data, lambda payload: payload.replace(b"<f4", b"|O4", 1)
        )
        wrong_shape = self._rewrite_single_member_payload(
            npz.data, lambda payload: payload.replace(b"(8,)", b"(9,)", 1)
        )
        wrong_value = self._rewrite_single_member_payload(
            npz.data,
            lambda payload: payload[:-1] + b"\x01",
        )
        for name, data in (
            ("npy-object-dtype", wrong_dtype),
            ("npy-wrong-shape", wrong_shape),
            ("npy-nonzero-data", wrong_value),
        ):
            with self.subTest(attack=name):
                with self.assertRaises(validator.PersonaV2RawZipValidatorError):
                    validator.validate_raw_zip_payload(replace(npz, data=data))

        ifc = self._validation_request("ifczip", 1)
        wrong_schema = self._rewrite_single_member_payload(
            ifc.data, lambda payload: payload.replace(b"IFC4", b"IFC2", 1)
        )
        with self.assertRaises(validator.PersonaV2RawZipValidatorError):
            validator.validate_raw_zip_payload(replace(ifc, data=wrong_schema))

    def test_schema_metadata_bounds_and_exact_types_fail_closed(self):
        with self.assertRaises(renderer.PersonaV2RawZipRendererError):
            renderer.render_raw_zip(RenderRequestSubclass(2, "archive-zip", 1))
        for schema in (True, IntSubclass(2), 1, 3):
            with self.subTest(renderer_schema=schema):
                with self.assertRaises(renderer.PersonaV2RawZipRendererError):
                    renderer.render_raw_zip(
                        renderer.RawZipRenderRequest(schema, "archive-zip", 1)
                    )
        for variant, complexity in (
            ("docx", 1),
            ("xlsx", 1),
            ("pptx", 1),
            ("unknown-zip", 1),
            ("archive-zip", 0),
            ("archive-zip", 65),
            ("ifczip", 2),
            ("npz", 0),
            ("npz", 1_000_001),
        ):
            with self.subTest(variant=variant, complexity=complexity):
                with self.assertRaises(renderer.PersonaV2RawZipRendererError):
                    renderer.render_raw_zip(
                        renderer.RawZipRenderRequest(2, variant, complexity)
                    )
        for complexity in (True, IntSubclass(1)):
            with self.assertRaises(renderer.PersonaV2RawZipRendererError):
                renderer.render_raw_zip(
                    renderer.RawZipRenderRequest(2, "archive-zip", complexity)
                )
        with self.assertRaises(renderer.PersonaV2RawZipRendererError):
            renderer.render_raw_zip(
                renderer.RawZipRenderRequest(2, StrSubclass("archive-zip"), 1)
            )

        request = self._validation_request("archive-zip", 1)
        with self.assertRaises(validator.PersonaV2RawZipValidatorError):
            validator.validate_raw_zip_payload(
                ValidationRequestSubclass(
                    *(getattr(request, field.name) for field in fields(request))
                )
            )
        mutations = (
            {"schema_version": True},
            {"target_complexity": True},
            {"variant": StrSubclass("archive-zip")},
            {"data": BytesSubclass(request.data)},
            {"extension": "npz"},
            {"content_media_type": "application/octet-stream"},
            {"expected_kio_path_media_type": "application/zip"},
            {"expected_offline_disposition": "incidental_sniff"},
            {"data": request.data[:-1]},
            {"data": request.data + b"x"},
        )
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                with self.assertRaises(validator.PersonaV2RawZipValidatorError):
                    validator.validate_raw_zip_payload(replace(request, **mutation))

    def test_request_and_module_boundaries_are_identity_free_and_standalone(self):
        self.assertEqual(
            tuple(field.name for field in fields(renderer.RawZipRenderRequest)),
            renderer.REQUEST_FIELDS,
        )
        self.assertEqual(
            tuple(field.name for field in fields(validator.RawZipValidationRequest)),
            validator.REQUEST_FIELDS,
        )
        self.assertFalse(
            set(renderer.REQUEST_FIELDS) & set(renderer.PROHIBITED_IDENTITY_FIELDS)
        )
        self.assertFalse(
            set(validator.REQUEST_FIELDS) & set(validator.PROHIBITED_IDENTITY_FIELDS)
        )
        self.assertFalse(
            {field.name for field in fields(renderer.RenderedRawZip)}
            & set(renderer.PROHIBITED_IDENTITY_FIELDS)
        )
        renderer_source = inspect.getsource(renderer)
        validator_source = inspect.getsource(validator)
        self.assertNotIn("persona_v2_raw_zip_validator", renderer_source)
        self.assertNotIn("persona_v2_raw_zip_renderer", validator_source)
        self.assertNotIn("persona_v2_variant_catalog", validator_source)
        self.assertNotIn("persona_v2_source_profile_catalog", validator_source)
        self.assertNotIn("persona_v2_source_plan", validator_source)
        for source in (renderer_source, validator_source):
            self.assertNotIn("requests", source)
            self.assertNotIn("urllib", source)
            self.assertNotIn("socket", source)
            self.assertNotIn("numpy", source)

    def test_environment_hashseed_timezone_and_locale_do_not_change_outputs(self):
        code = r'''
import hashlib
from eval import persona_v2_raw_zip_renderer as r
cases = (("archive-zip", 64), ("ifczip", 1), ("npz", 1000000))
print(r.renderer_contract_sha256())
for variant, complexity in cases:
    value = r.render_raw_zip(r.RawZipRenderRequest(2, variant, complexity))
    print(variant, complexity, len(value.data), hashlib.sha256(value.data).hexdigest())
'''
        outputs = []
        for seed, timezone, locale in (
            ("1", "UTC", "C"),
            ("77", "Asia/Tokyo", "C"),
            ("random", "America/Los_Angeles", "C"),
        ):
            environment = os.environ.copy()
            environment.update(
                {
                    "PYTHONHASHSEED": seed,
                    "TZ": timezone,
                    "LC_ALL": locale,
                    "LANG": locale,
                }
            )
            completed = subprocess.run(
                [sys.executable, "-c", code],
                cwd=os.path.dirname(os.path.dirname(__file__)),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(completed.stderr, "")
            outputs.append(completed.stdout)
        self.assertEqual(outputs, [outputs[0]] * len(outputs))


if __name__ == "__main__":
    unittest.main()
