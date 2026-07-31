"""Adversarial tests for the ID-free raw image/media feasibility slice."""

from __future__ import annotations

from dataclasses import replace
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

try:  # Support package and direct ``eval/*.py`` test execution.
    from . import persona_v2_raw_image_media_renderer as renderer
    from . import persona_v2_raw_image_media_validator as validator
    from . import persona_v2_variant_catalog as variant_catalog
except ImportError:  # pragma: no cover - direct-script compatibility
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from eval import persona_v2_raw_image_media_renderer as renderer
    from eval import persona_v2_raw_image_media_validator as validator
    from eval import persona_v2_variant_catalog as variant_catalog


MATRIX = {
    "aiff": {
        "family": "media",
        "extension": "aiff",
        "content": "audio/aiff",
        "path": "application/octet-stream",
        "disposition": "unsupported_binary",
        "measure": "frames-or-events",
        "counting_rule": "mono-pcm-sample-frames",
        "formula": "54+frames+(frames-mod-2)",
        "template": "canonical-aiff-8bit-mono-pcm-v2",
    },
    "bmp": {
        "family": "image",
        "extension": "bmp",
        "content": "image/bmp",
        "path": "application/octet-stream",
        "disposition": "unsupported_binary",
        "measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "formula": "62+4*ceil(width/32)*height",
        "template": "canonical-bmp-infoheader-1bit-v2",
    },
    "jpg": {
        "family": "image",
        "extension": "jpg",
        "content": "image/jpeg",
        "path": "image/jpeg",
        "disposition": "awaiting_ocr",
        "measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "formula": "154+ceil(ceil(width/8)*ceil(height/8)/4)",
        "template": "canonical-jfif-baseline-grayscale-zero-dct-v2",
    },
    "mid": {
        "family": "media",
        "extension": "mid",
        "content": "audio/midi",
        "path": "application/octet-stream",
        "disposition": "unsupported_binary",
        "measure": "frames-or-events",
        "counting_rule": "note-on-channel-events-excluding-end-of-track",
        "formula": "27+3*events",
        "template": "canonical-smf0-running-status-note-events-v2",
    },
    "png": {
        "family": "image",
        "extension": "png",
        "content": "image/png",
        "path": "image/png",
        "disposition": "awaiting_ocr",
        "measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "formula": (
            "63+(ceil(width/8)+1)*height+"
            "5*ceil(((ceil(width/8)+1)*height)/65535)"
        ),
        "template": "canonical-png-1bit-gray-stored-deflate-v2",
    },
    "tif": {
        "family": "image",
        "extension": "tif",
        "content": "image/tiff",
        "path": "application/octet-stream",
        "disposition": "unsupported_binary",
        "measure": "pixels",
        "counting_rule": "decoded-width-times-height",
        "formula": "110+ceil(width/8)*height",
        "template": "canonical-tiff-le-single-strip-1bit-v2",
    },
    "wav": {
        "family": "media",
        "extension": "wav",
        "content": "audio/wav",
        "path": "application/octet-stream",
        "disposition": "unsupported_binary",
        "measure": "frames-or-events",
        "counting_rule": "mono-pcm-sample-frames",
        "formula": "44+frames+(frames-mod-2)",
        "template": "canonical-wave-8bit-mono-pcm-v2",
    },
}

EXPECTED_VARIANTS = tuple(sorted(MATRIX))
RENDERER_CONTRACT_SHA256 = "c64b762b102aa4fbad000fc21ef2c810d1746daab9a11f959226cec45f16f92e"
VALIDATOR_CONTRACT_SHA256 = "a1c544dcc3f68167aefd3bba2cc90cd4fdd124473485e834f8a0e662df52ad9a"
REPRESENTATIVE_AGGREGATE_SHA256 = "d6985d963aa7b020359eb5afb01b209deaec07eb95c94c0839f39225416a7823"

REPRESENTATIVE_CASES = {
    "aiff": (0, 0, 7, 62, "c1b6a961e0f4df9e89723f290946c2604da60e3f6d48428fe8ba96f6e85e1ae2"),
    "bmp": (65, 64, 0, 830, "44792c9759e1bc8dd1b509c50bc88db60aa8ec95831aaac54bed5b113fb81e5b"),
    "jpg": (65, 64, 0, 172, "f85546ea48b0bb2339a26fafddaf4976b90ce8c779345e86ff8973ff7525b38e"),
    "mid": (0, 0, 7, 48, "32f4a5930cbbcd775267e52ecfbec085abedc2adf7771c68db10997bc60110ca"),
    "png": (65, 64, 0, 708, "1274bd80f046510d84e4224fa6a9958bdd0835dbd1aabd1a4a0cf023b59a4ddc"),
    "tif": (65, 64, 0, 686, "d03b3629128ec8da32dfd12ccb6e74751acdb77d143c6a85ede9f656c2da2b78"),
    "wav": (0, 0, 7, 52, "01763ed243907fabaa43bcaa2b57419f50059086dbd5b86ea39fac5c11b7bcde"),
}

MAXIMUM_LENGTHS = {
    "aiff": 4_800_054,
    "bmp": 2_350_142,
    "jpg": 67_474,
    "mid": 14_400_027,
    "png": 2_219_753,
    "tif": 2_154_350,
    "wav": 4_800_044,
}

MAXIMUM_AXES = {
    "aiff": (0, 0, 4_800_000),
    "bmp": (257, 65_280, 0),
    "jpg": (257, 65_280, 0),
    "mid": (0, 0, 4_800_000),
    "png": (257, 65_280, 0),
    "tif": (257, 65_280, 0),
    "wav": (0, 0, 4_800_000),
}


class PersonaV2RawImageMediaRendererValidatorTest(unittest.TestCase):
    maxDiff = None

    def _render(self, variant, width, height, count):
        request = renderer.RawImageMediaRenderRequest(
            schema_version=2,
            variant=variant,
            width=width,
            height=height,
            frame_or_event_count=count,
        )
        return renderer.render_raw_image_media(request)

    def _validation_request(self, variant, width, height, count, rendered):
        return validator.RawImageMediaValidationRequest(
            schema_version=2,
            variant=variant,
            width=width,
            height=height,
            frame_or_event_count=count,
            data=rendered.data,
            extension=rendered.extension,
            content_media_type=rendered.content_media_type,
            expected_kio_path_media_type=rendered.expected_kio_path_media_type,
            expected_offline_disposition=rendered.expected_offline_disposition,
        )

    def _assert_validator_rejects(self, request):
        with self.assertRaises(validator.PersonaV2RawImageMediaValidatorError):
            validator.validate_raw_image_media_payload(request)

    def test_exact_variant_matrix_and_contract_pins(self):
        self.assertEqual(renderer.READY_VARIANTS, EXPECTED_VARIANTS)
        self.assertEqual(validator.READY_VARIANTS, EXPECTED_VARIANTS)
        self.assertEqual(renderer.renderer_contract_sha256(), RENDERER_CONTRACT_SHA256)
        self.assertEqual(validator.validator_contract_sha256(), VALIDATOR_CONTRACT_SHA256)
        self.assertEqual(len(renderer.canonical_json_bytes(renderer.build_renderer_contract())), 7_504)
        self.assertEqual(len(validator.canonical_json_bytes(validator.build_validator_contract())), 8_223)

        renderer_contract = renderer.build_renderer_contract()
        validator_contract = validator.build_validator_contract()
        self.assertTrue(renderer.validate_renderer_contract(renderer_contract))
        self.assertTrue(validator.validate_validator_contract(validator_contract))
        for contract in (renderer_contract, validator_contract):
            self.assertEqual(contract["variant_count"], 7)
            self.assertEqual(
                tuple(row["variant_id"] for row in contract["variant_rows"]),
                EXPECTED_VARIANTS,
            )
            self.assertFalse(contract["byte_stress_lane_implemented"])
            self.assertTrue(all(value is False for value in contract["authority"].values()))
            self.assertTrue(contract["request_is_identity_free"])
            for row in contract["variant_rows"]:
                expected = MATRIX[row["variant_id"]]
                self.assertEqual(row["family"], expected["family"])
                self.assertEqual(row["filename_extension"], expected["extension"])
                self.assertEqual(row["content_media_type"], expected["content"])
                self.assertEqual(row["expected_kio_path_media_type"], expected["path"])
                self.assertEqual(row["expected_offline_disposition"], expected["disposition"])
                self.assertEqual(row["gate_role"], "raw_only")
                self.assertEqual(row["complexity"]["measure"], expected["measure"])
                self.assertEqual(row["complexity"]["counting_rule"], expected["counting_rule"])
                self.assertEqual(row["raw_byte_formula"]["exact_formula"], expected["formula"])
                self.assertEqual(
                    row["raw_byte_formula"]["maximum_rendered_bytes"],
                    MAXIMUM_LENGTHS[row["variant_id"]],
                )
                self.assertEqual(row["render_template"], expected["template"])

        detached = renderer.build_renderer_contract()
        detached["authority"]["authorizes_physical_write"] = True
        self.assertFalse(renderer.build_renderer_contract()["authority"]["authorizes_physical_write"])
        with self.assertRaises(renderer.PersonaV2RawImageMediaRendererError):
            renderer.validate_renderer_contract(detached)
        tampered = validator.build_validator_contract()
        tampered["variant_rows"][0]["gate_role"] = "contract_contributor"
        with self.assertRaises(validator.PersonaV2RawImageMediaValidatorError):
            validator.validate_validator_contract(tampered)

    def test_exact_formulas_domains_and_true_reachable_maxima(self):
        for variant, expected_length in MAXIMUM_LENGTHS.items():
            axes = MAXIMUM_AXES[variant]
            self.assertEqual(renderer.target_bytes_for(variant, *axes), expected_length)
            self.assertEqual(validator.target_bytes_for(variant, *axes), expected_length)
            self.assertEqual(renderer.maximum_rendered_bytes_for(variant), expected_length)
            self.assertEqual(validator.maximum_rendered_bytes_for(variant), expected_length)
            self.assertLessEqual(expected_length, 100 * 2**20)

        square_lengths = {
            "bmp": 2_097_214,
            "jpg": 65_690,
            "png": 2_101_476,
            "tif": 2_097_262,
        }
        for variant, square_length in square_lengths.items():
            self.assertEqual(
                renderer.target_bytes_for(variant, 4_096, 4_096, 0),
                square_length,
            )
            self.assertGreater(MAXIMUM_LENGTHS[variant], square_length)

        self.assertEqual(renderer.target_bytes_for("bmp", 65, 64, 0), 830)
        self.assertEqual(renderer.target_bytes_for("jpg", 65, 64, 0), 172)
        self.assertEqual(renderer.target_bytes_for("png", 65, 64, 0), 708)
        self.assertEqual(renderer.target_bytes_for("tif", 65, 64, 0), 686)
        self.assertEqual(renderer.target_bytes_for("aiff", 0, 0, 7), 62)
        self.assertEqual(renderer.target_bytes_for("mid", 0, 0, 7), 48)
        self.assertEqual(renderer.target_bytes_for("wav", 0, 0, 7), 52)
        self.assertEqual(renderer.target_complexity_for("png", 65, 64, 0), 4_160)
        self.assertEqual(renderer.target_complexity_for("mid", 0, 0, 7), 7)

        for module, error in (
            (renderer, renderer.PersonaV2RawImageMediaRendererError),
            (validator, validator.PersonaV2RawImageMediaValidatorError),
        ):
            for axes in ((63, 64, 0), (65_536, 64, 0), (4_097, 4_096, 0)):
                with self.assertRaises(error):
                    module.target_bytes_for("png", *axes)
            for axes in ((0, 0, 0), (0, 0, 4_800_001), (1, 0, 10)):
                with self.assertRaises(error):
                    module.target_bytes_for("wav", *axes)
            with self.assertRaises(error):
                module.target_bytes_for("wav", 0, 0, True)

    def test_hardcoded_rows_bind_to_catalog_and_exact_profile_marginals(self):
        catalog = variant_catalog.build_variant_catalog()
        rows = {
            row["variant_id"]: row
            for row in catalog["variant_rows"]
            if row["variant_id"] in MATRIX
        }
        self.assertEqual(set(rows), set(MATRIX))
        for variant, expected in MATRIX.items():
            row = rows[variant]
            self.assertEqual(row["family"], expected["family"])
            self.assertEqual(row["filename_extension"], expected["extension"])
            self.assertEqual(row["content_media_type"], expected["content"])
            self.assertEqual(row["expected_kio_path_media_type"], expected["path"])
            self.assertEqual(row["expected_offline_disposition"], expected["disposition"])
            self.assertEqual(row["gate_role"], "raw_only")
            self.assertEqual(row["complexity_contract"]["complexity_unit"], expected["measure"])

        marginals = [
            row
            for row in catalog["persona_variant_marginals"]
            if row["variant_id"] in MATRIX
        ]
        self.assertEqual(len(marginals), 110)
        self.assertEqual(sum(row["tiny_smoke_count"] for row in marginals), 282)
        self.assertEqual(sum(row["pilot_count"] for row in marginals), 1_353)
        self.assertEqual(sum(row["full_count"] for row in marginals), 13_530)
        self.assertTrue(all(row["family"] == MATRIX[row["variant_id"]]["family"] for row in marginals))

    def test_representative_payload_hashes_structure_and_negative_receipts(self):
        aggregate_rows = []
        forbidden_tokens = (b"persona", b"source_id", b"scope_key", b"oracle", b"query")
        for variant in EXPECTED_VARIANTS:
            width, height, count, expected_length, expected_sha = REPRESENTATIVE_CASES[variant]
            rendered = self._render(variant, width, height, count)
            self.assertEqual(len(rendered.data), expected_length)
            self.assertEqual(rendered.target_bytes, expected_length)
            self.assertEqual(hashlib.sha256(rendered.data).hexdigest(), expected_sha)
            self.assertEqual(rendered.extension, MATRIX[variant]["extension"])
            self.assertEqual(rendered.content_media_type, MATRIX[variant]["content"])
            self.assertEqual(rendered.expected_kio_path_media_type, MATRIX[variant]["path"])
            self.assertEqual(rendered.expected_offline_disposition, MATRIX[variant]["disposition"])
            self.assertEqual(rendered.size_lane, "feasibility-only")
            self.assertTrue(all(token not in rendered.data.lower() for token in forbidden_tokens))

            receipt = validator.validate_raw_image_media_payload(
                self._validation_request(variant, width, height, count, rendered)
            )
            self.assertTrue(receipt["structure_validated"])
            self.assertTrue(receipt["identity_tokens_absent"])
            self.assertFalse(receipt["actual_chunks_attested"])
            self.assertFalse(receipt["kio_execution_attested"])
            expected_complexity = width * height if width else count
            self.assertEqual(receipt["observed_local_complexity"], expected_complexity)
            aggregate_rows.append(
                [variant, width, height, count, expected_length, expected_sha]
            )
        canonical = json.dumps(
            aggregate_rows,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii") + b"\n"
        self.assertEqual(hashlib.sha256(canonical).hexdigest(), REPRESENTATIVE_AGGREGATE_SHA256)

    def test_size_lane_boundaries_preserve_true_semantics(self):
        ordinary_cases = {
            "aiff": (0, 0, 524_234, 524_288),
            "bmp": (2_048, 2_047, 0, 524_094),
            "jpg": (1_024, 1_024, 0, 4_250),
            "mid": (0, 0, 174_753, 524_286),
            "png": (313, 12_785, 0, 524_288),
            "tif": (2_048, 2_047, 0, 524_142),
            "wav": (0, 0, 524_244, 524_288),
        }
        for variant, (width, height, count, expected_length) in ordinary_cases.items():
            self.assertEqual(renderer.target_bytes_for(variant, width, height, count), expected_length)
            self.assertEqual(renderer.classify_size_lane(expected_length), "formal-ordinary")
            self.assertEqual(validator.classify_size_lane(expected_length), "formal-ordinary")

        crossing_cases = {
            "aiff": (0, 0, 524_235, 524_290),
            "bmp": (2_048, 2_048, 0, 524_350),
            "mid": (0, 0, 174_754, 524_289),
            "png": (313, 12_786, 0, 524_329),
            "tif": (2_048, 2_048, 0, 524_398),
            "wav": (0, 0, 524_245, 524_290),
        }
        for variant, (width, height, count, expected_length) in crossing_cases.items():
            self.assertEqual(renderer.target_bytes_for(variant, width, height, count), expected_length)
            self.assertEqual(renderer.classify_size_lane(expected_length), "feasibility-only")

        for variant in ("bmp", "png", "tif"):
            length = renderer.target_bytes_for(variant, 4_096, 4_096, 0)
            self.assertEqual(renderer.classify_size_lane(length), "formal-tail")
        self.assertEqual(renderer.classify_size_lane(1_048_576), "formal-tail")
        self.assertEqual(renderer.classify_size_lane(4_194_304), "formal-tail")
        self.assertEqual(renderer.classify_size_lane(4_194_305), "feasibility-only")
        self.assertEqual(renderer.classify_size_lane(4_095), "feasibility-only")
        self.assertEqual(renderer.classify_size_lane(4_096), "formal-ordinary")
        self.assertEqual(renderer.classify_size_lane(524_288), "formal-ordinary")
        self.assertEqual(renderer.classify_size_lane(524_289), "feasibility-only")
        self.assertEqual(renderer.classify_size_lane(MAXIMUM_LENGTHS["jpg"]), "formal-ordinary")
        for variant in ("aiff", "mid", "wav"):
            self.assertEqual(renderer.classify_size_lane(MAXIMUM_LENGTHS[variant]), "feasibility-only")

    def test_large_tail_examples_render_and_validate_without_identity(self):
        cases = (
            ("tif", 4_096, 4_096, 0),
            ("wav", 0, 0, 1_048_532),
            ("mid", 0, 0, 349_517),
        )
        for variant, width, height, count in cases:
            rendered = self._render(variant, width, height, count)
            self.assertEqual(rendered.size_lane, "formal-tail")
            receipt = validator.validate_raw_image_media_payload(
                self._validation_request(variant, width, height, count, rendered)
            )
            self.assertEqual(receipt["size_lane"], "formal-tail")

    def test_skewed_maximum_raster_geometry_renders_and_validates(self):
        for variant in ("bmp", "jpg", "png", "tif"):
            width, height, count = MAXIMUM_AXES[variant]
            self.assertEqual(width * height, 16_776_960)
            rendered = self._render(variant, width, height, count)
            self.assertEqual(rendered.target_bytes, MAXIMUM_LENGTHS[variant])
            receipt = validator.validate_raw_image_media_payload(
                self._validation_request(variant, width, height, count, rendered)
            )
            self.assertEqual(receipt["observed_local_complexity"], width * height)
            self.assertEqual(receipt["target_bytes"], MAXIMUM_LENGTHS[variant])

    def test_truncation_extension_and_single_byte_tampering_are_rejected(self):
        for variant in EXPECTED_VARIANTS:
            width, height, count, _, _ = REPRESENTATIVE_CASES[variant]
            rendered = self._render(variant, width, height, count)
            valid = self._validation_request(variant, width, height, count, rendered)
            self._assert_validator_rejects(replace(valid, data=valid.data[:-1]))
            self._assert_validator_rejects(replace(valid, data=valid.data + b"\x00"))
            index = len(valid.data) // 2
            mutated = bytearray(valid.data)
            mutated[index] ^= 1
            self._assert_validator_rejects(replace(valid, data=bytes(mutated)))
            self._assert_validator_rejects(replace(valid, extension="bin"))
            self._assert_validator_rejects(replace(valid, content_media_type="application/octet-stream"))

    def test_hostile_framing_is_rejected_before_unbounded_body_work(self):
        png = self._render("png", 65, 64, 0)
        png_request = self._validation_request("png", 65, 64, 0, png)
        forged_png = bytearray(png.data)
        forged_png[8:12] = b"\xff\xff\xff\xff"
        self._assert_validator_rejects(replace(png_request, data=bytes(forged_png)))

        jpg = self._render("jpg", 65, 64, 0)
        jpg_request = self._validation_request("jpg", 65, 64, 0, jpg)
        forged_jpg = bytearray(jpg.data)
        forged_jpg[4:6] = b"\xff\xff"
        self._assert_validator_rejects(replace(jpg_request, data=bytes(forged_jpg)))

        source = inspect.getsource(validator)
        self.assertLess(
            source.index("len(request.data) <= MAX_RENDERED_BYTES"),
            source.index("_validate_structure(request)"),
        )
        self.assertLess(
            source.index("length > MAX_RENDERED_BYTES"),
            source.index("memoryview(data)[payload_start:payload_end]"),
        )

    def test_type_subclass_axis_and_metadata_confusion_are_rejected(self):
        base = renderer.RawImageMediaRenderRequest(2, "png", 65, 64, 0)

        class ExplosiveRepr:
            def __repr__(self):
                raise RuntimeError("repr must not be called")

        class RenderRequestSubclass(renderer.RawImageMediaRenderRequest):
            pass

        with self.assertRaises(renderer.PersonaV2RawImageMediaRendererError):
            renderer.render_raw_image_media(RenderRequestSubclass(2, "png", 65, 64, 0))
        for request in (
            replace(base, schema_version=True),
            replace(base, variant="jpeg"),
            replace(base, variant=ExplosiveRepr()),
            replace(base, width=True),
            replace(base, frame_or_event_count=1),
            renderer.RawImageMediaRenderRequest(2, "wav", 1, 0, 10),
            renderer.RawImageMediaRenderRequest(2, "wav", 0, 0, False),
        ):
            with self.assertRaises(renderer.PersonaV2RawImageMediaRendererError):
                renderer.render_raw_image_media(request)

        rendered = self._render("png", 65, 64, 0)
        valid = self._validation_request("png", 65, 64, 0, rendered)

        class ValidationRequestSubclass(validator.RawImageMediaValidationRequest):
            pass

        with self.assertRaises(validator.PersonaV2RawImageMediaValidatorError):
            validator.validate_raw_image_media_payload(
                ValidationRequestSubclass(
                    valid.schema_version,
                    valid.variant,
                    valid.width,
                    valid.height,
                    valid.frame_or_event_count,
                    valid.data,
                    valid.extension,
                    valid.content_media_type,
                    valid.expected_kio_path_media_type,
                    valid.expected_offline_disposition,
                )
            )
        self._assert_validator_rejects(replace(valid, data=bytearray(valid.data)))
        self._assert_validator_rejects(replace(valid, variant=ExplosiveRepr()))
        self._assert_validator_rejects(replace(valid, width=True))
        self._assert_validator_rejects(replace(valid, expected_offline_disposition="incidental_sniff"))
        self._assert_validator_rejects(replace(valid, expected_kio_path_media_type="image/jpeg"))

        self.assertFalse(hasattr(base, "__dict__"))
        self.assertFalse(hasattr(rendered, "__dict__"))
        self.assertFalse(hasattr(valid, "__dict__"))
        with self.assertRaises(AttributeError):
            object.__setattr__(base, "source_id", "injected")
        with self.assertRaises(AttributeError):
            object.__setattr__(valid, "query_id", "injected")

    def test_canonical_contract_apis_fail_closed_before_json_serialization(self):
        class IntSubclass(int):
            pass

        class StrSubclass(str):
            pass

        class DictSubclass(dict):
            pass

        cases = (
            (
                renderer,
                renderer.build_renderer_contract,
                renderer.validate_renderer_contract,
                renderer.renderer_contract_sha256,
                renderer.PersonaV2RawImageMediaRendererError,
            ),
            (
                validator,
                validator.build_validator_contract,
                validator.validate_validator_contract,
                validator.validator_contract_sha256,
                validator.PersonaV2RawImageMediaValidatorError,
            ),
        )
        for module, builder, validate_contract, digest_contract, error in cases:
            contract = builder()
            contract["variant_count"] = IntSubclass(7)
            with self.assertRaises(error):
                validate_contract(contract)
            contract = builder()
            contract["artifact_kind"] = StrSubclass(contract["artifact_kind"])
            with self.assertRaises(error):
                validate_contract(contract)
            contract = builder()
            contract["authority"] = DictSubclass(contract["authority"])
            with self.assertRaises(error):
                validate_contract(contract)
            with self.assertRaises(error):
                module.canonical_json_bytes({"nested": IntSubclass(1)})
            with self.assertRaises(error):
                module.canonical_json_bytes({"wide": [0] * 32_769})
            for invalid in (
                {"null": None},
                {"float": 1.0},
                {"negative": -1},
                {"wide-integer": 2**127},
            ):
                with self.assertRaises(error):
                    module.canonical_json_bytes(invalid)
            contract = builder()
            contract["variant_count"] += 1
            with self.assertRaises(error):
                digest_contract(contract)

        deeply_nested = {}
        cursor = deeply_nested
        for _ in range(100_000):
            child = {}
            cursor["nested"] = child
            cursor = child
        with self.assertRaises(renderer.PersonaV2RawImageMediaRendererError):
            renderer.canonical_json_bytes(deeply_nested)
        with self.assertRaises(validator.PersonaV2RawImageMediaValidatorError):
            validator.canonical_json_bytes(deeply_nested)

    def test_format_specific_canonical_fields_are_rejected_when_tampered(self):
        mutations = {
            "aiff": 31,
            "bmp": 54,
            "jpg": 29,
            "mid": 23,
            "png": 29,
            "tif": 18,
            "wav": 22,
        }
        for variant, index in mutations.items():
            width, height, count, _, _ = REPRESENTATIVE_CASES[variant]
            rendered = self._render(variant, width, height, count)
            valid = self._validation_request(variant, width, height, count, rendered)
            mutated = bytearray(valid.data)
            mutated[index] ^= 0x40
            self._assert_validator_rejects(replace(valid, data=bytes(mutated)))

        for variant in ("aiff", "wav"):
            width, height, count, _, _ = REPRESENTATIVE_CASES[variant]
            rendered = self._render(variant, width, height, count)
            valid = self._validation_request(variant, width, height, count, rendered)
            mutated = bytearray(valid.data)
            mutated[-1] = 1
            self._assert_validator_rejects(replace(valid, data=bytes(mutated)))

    def test_implementation_independence_stdlib_only_and_negative_authority(self):
        validator_source = inspect.getsource(validator)
        renderer_source = inspect.getsource(renderer)
        for forbidden in (
            "persona_v2_raw_image_media_renderer",
            "persona_v2_variant_catalog",
            "persona_v2_contract",
            "import persona_v2_source_plan",
            "import PIL",
            "import numpy",
        ):
            self.assertNotIn(forbidden, validator_source)
        for forbidden in ("import PIL", "import numpy", "import cv2"):
            self.assertNotIn(forbidden, renderer_source)
        self.assertFalse(
            set(renderer.RawImageMediaRenderRequest.__dataclass_fields__)
            & set(renderer.PROHIBITED_IDENTITY_FIELDS)
        )
        self.assertFalse(
            set(validator.RawImageMediaValidationRequest.__dataclass_fields__)
            & set(validator.PROHIBITED_IDENTITY_FIELDS)
        )
        independence = validator.build_validator_contract()["independence_contract"]
        self.assertTrue(independence["checks_bounded_headers_before_payload_work"])
        self.assertTrue(independence["validates_dimensions_frames_or_events"])
        self.assertFalse(independence["imports_renderer_module"])
        self.assertFalse(independence["imports_source_or_variant_catalog"])
        self.assertFalse(independence["imports_planning_modules"])

    def test_subprocess_determinism_across_hashseed_timezone_and_locale(self):
        script = r'''
import hashlib
import json
from eval import persona_v2_raw_image_media_renderer as r
cases = {
    "aiff": (0, 0, 7), "bmp": (65, 64, 0), "jpg": (65, 64, 0),
    "mid": (0, 0, 7), "png": (65, 64, 0), "tif": (65, 64, 0),
    "wav": (0, 0, 7),
}
rows = []
for variant in sorted(cases):
    width, height, count = cases[variant]
    rendered = r.render_raw_image_media(
        r.RawImageMediaRenderRequest(2, variant, width, height, count)
    )
    rows.append([variant, len(rendered.data), hashlib.sha256(rendered.data).hexdigest()])
print(json.dumps({
    "contract": r.renderer_contract_sha256(),
    "rows": rows,
}, sort_keys=True, separators=(",", ":")))
'''
        outputs = []
        for seed, timezone in (("1", "UTC"), ("9173", "Asia/Tokyo")):
            environment = os.environ.copy()
            environment.update(
                {
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": timezone,
                }
            )
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=Path(__file__).resolve().parents[1],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            outputs.append(result.stdout)
        self.assertEqual(outputs[0], outputs[1])
        parsed = json.loads(outputs[0])
        self.assertEqual(parsed["contract"], RENDERER_CONTRACT_SHA256)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
