"""Frozen pins, closure, runtime receipts, and adversarial registry gates."""

from __future__ import annotations

import copy
from dataclasses import fields, is_dataclass
import hashlib
import importlib
import inspect
import os
import subprocess
import sys
import unittest

from eval import persona_v2_format_implementation_registry as registry
from eval import persona_v2_format_implementation_registry_validator as independent
from eval import persona_v2_source_inventory_profile as inventory_catalog
from eval import persona_v2_source_profile_catalog as historical_catalog
from eval import persona_v2_variant_catalog as variant_catalog


EXPECTED_REGISTRY_BYTES = 333_881
EXPECTED_REGISTRY_SHA256 = (
    "f585ae477daa01db4dc11bbc1edd9824696bd91eddce5870d618caaffd90c683"
)
EXPECTED_PAIR_VARIANT_COUNTS = {
    "contributor-text": 9,
    "pdf-text": 1,
    "incidental-text": 11,
    "raw-document": 4,
    "raw-image-media": 7,
    "raw-zip": 21,
    "raw-tar-gzip": 16,
    "raw-domain": 2,
}
EXPECTED_PAIR_PAYLOAD_AGGREGATES = {
    "contributor-text": "0ce8a9152cf9fd6bdd9461c641eea64762b0b4de70a3c3c251aa78471ed7a8fc",
    "pdf-text": "6b8bd5309623f447dcf6dccb13c4a16889fe3b1e1af36c1a9a2bd1887076df55",
    "incidental-text": "c95779f318c0c2d54734e6868b56a0238c0fabd09409735046b505dc37843cdf",
    "raw-document": "f5b19a7b2201c8e699eef539bf1e124c6d24c0076a71aff018821b8cf4fba171",
    "raw-image-media": "880bb2be57d857b310116ac9cd91b566f341aee84c044939bafdc0056cc23440",
    "raw-zip": "39e62f8e4e78247dfbf62eb0b576876f5053b928576d8db7f3ce54699fa464dc",
    "raw-tar-gzip": "da82d8dbfb10dedfc881ff363a37bb5cfff4a015e7b3deb0536625ee96ea7f5d",
    "raw-domain": "61d6d991af039c12aea5409017a4e0931f7db2ff958bafe8c887b86505f22b1f",
}
FORMAT_PAIRS = (
    "text",
    "pdf_text",
    "incidental_text",
    "raw_document",
    "raw_image_media",
    "raw_zip",
    "raw_tar_gzip",
    "raw_domain",
)
PROHIBITED_CARRIER_FIELDS = {
    "final_source_id",
    "history_event_id",
    "persona_id",
    "query_id",
    "scope_key",
    "source_id",
    "source_instance_id",
}


class DictAlias(dict):
    pass


class PersonaV2FormatImplementationRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = registry.build_format_implementation_registry()
        cls.variant_value = variant_catalog.build_variant_catalog()
        cls.historical_value = historical_catalog.build_source_profile_catalog()
        cls.inventory_value = (
            inventory_catalog.build_source_inventory_profile_catalog()
        )
        renderer_contract_provider, validator_contract_provider = (
            registry._contract_providers()
        )
        renderer_probe_provider, _ = registry._probe_providers()
        cls.renderer_contract_provider = staticmethod(renderer_contract_provider)
        cls.validator_contract_provider = staticmethod(validator_contract_provider)
        cls.renderer_probe_provider = staticmethod(renderer_probe_provider)

    def _validate_independently(
        self,
        value,
        *,
        variant_value=None,
        historical_value=None,
        inventory_value=None,
        renderer_contract_provider=None,
        validator_contract_provider=None,
        renderer_probe_provider=None,
    ):
        return independent.validate_format_implementation_registry(
            value,
            variant_catalog_value=(
                self.variant_value if variant_value is None else variant_value
            ),
            historical_source_profile_value=(
                self.historical_value
                if historical_value is None
                else historical_value
            ),
            source_inventory_profile_value=(
                self.inventory_value if inventory_value is None else inventory_value
            ),
            renderer_contract_provider=(
                self.renderer_contract_provider
                if renderer_contract_provider is None
                else renderer_contract_provider
            ),
            validator_contract_provider=(
                self.validator_contract_provider
                if validator_contract_provider is None
                else validator_contract_provider
            ),
            renderer_probe_provider=(
                self.renderer_probe_provider
                if renderer_probe_provider is None
                else renderer_probe_provider
            ),
        )

    def test_final_body_pin_detachment_and_independent_runtime_validation(self):
        raw = registry.canonical_json_bytes(self.value)
        self.assertEqual(len(raw), EXPECTED_REGISTRY_BYTES)
        self.assertEqual(hashlib.sha256(raw).hexdigest(), EXPECTED_REGISTRY_SHA256)
        self.assertEqual(
            independent.EXPECTED_REGISTRY_CANONICAL_BYTES,
            EXPECTED_REGISTRY_BYTES,
        )
        self.assertEqual(
            independent.EXPECTED_REGISTRY_SHA256, EXPECTED_REGISTRY_SHA256
        )
        self.assertTrue(registry.validate_format_implementation_registry(self.value))
        self.assertEqual(
            registry.format_implementation_registry_sha256(self.value),
            EXPECTED_REGISTRY_SHA256,
        )
        detached = registry.build_format_implementation_registry()
        detached["implementation_rows"][0]["variant_id"] = "poisoned"
        self.assertNotEqual(
            detached["implementation_rows"][0]["variant_id"],
            registry.build_format_implementation_registry()["implementation_rows"][0][
                "variant_id"
            ],
        )

    def test_contract_and_upstream_body_pins(self):
        bindings = self.value["contract_bindings"]
        self.assertEqual(len(bindings), 16)
        self.assertEqual(
            [row["binding_id"] for row in bindings],
            [row[0] for row in independent.EXPECTED_CONTRACT_BINDINGS],
        )
        expected_by_id = {
            row[0]: row for row in independent.EXPECTED_CONTRACT_BINDINGS
        }
        for binding in bindings:
            expected = expected_by_id[binding["binding_id"]]
            self.assertEqual(
                (
                    binding["implementation_pair_id"],
                    binding["contract_role"],
                    binding["variant_count"],
                    binding["canonical_bytes"],
                    binding["sha256"],
                ),
                expected[1:],
            )
            expected_canonicalization = (
                "sorted-compact-ascii-with-terminal-lf"
                if binding["implementation_pair_id"] == "raw-image-media"
                else "sorted-compact-utf8"
            )
            self.assertEqual(
                binding["canonicalization_profile"], expected_canonicalization
            )
        self.assertEqual(
            self.value["input_bindings"], independent._expected_input_binding_rows()
        )

    def test_exact_71_coverage_unique_ownership_and_marginals(self):
        rows = self.value["implementation_rows"]
        self.assertEqual(len(rows), 71)
        self.assertEqual(len({row["variant_id"] for row in rows}), 71)
        self.assertEqual(
            [row["variant_id"] for row in rows],
            [row["variant_id"] for row in self.variant_value["variant_rows"]],
        )
        owner_counts = {}
        gate_counts = {}
        for row in rows:
            pair_id = row["implementation"]["pair_id"]
            owner_counts[pair_id] = owner_counts.get(pair_id, 0) + 1
            gate_role = row["gate_role"]
            gate_counts[gate_role] = gate_counts.get(gate_role, 0) + 1
        self.assertEqual(owner_counts, EXPECTED_PAIR_VARIANT_COUNTS)
        self.assertEqual(
            gate_counts,
            {
                "contract_contributor": 10,
                "incidental_searchable": 11,
                "raw_only": 50,
            },
        )
        self.assertEqual(self.value["coverage"], independent.EXPECTED_COVERAGE)

    def test_historical_10_61_pin_and_all_recipe_slots_remain_unbound(self):
        rows = self.value["implementation_rows"]
        self.assertEqual(
            sum(
                row["historical_source_profile"]["vertical_slice_ready"]
                for row in rows
            ),
            10,
        )
        slots = set()
        profiles = set()
        for row in rows:
            inventory = row["source_inventory_profile"]
            slots.add(inventory["source_recipe_slot_id"])
            profiles.add(inventory["source_profile_id"])
            self.assertEqual(
                inventory["source_recipe_binding_status"], "reserved-unbound"
            )
            self.assertEqual(inventory["source_recipe_profile_id"], "not-bound")
            self.assertEqual(inventory["execution_eligibility_status"], "blocked")
        self.assertEqual(len(slots), 71)
        self.assertEqual(len(profiles), 71)
        self.assertFalse(
            self.value["completion_claims"]["formal_source_recipe_profiles_bound"]
        )
        self.assertFalse(self.value["completion_claims"]["source_instances_bound"])

    def test_normalized_contracts_and_non_authorizing_receipts(self):
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        for row in self.value["implementation_rows"]:
            normalized = row["normalized_contract"]
            self.assertEqual(
                set(normalized),
                {"complexity", "formula", "lane", "parameter_shape", "quantization"},
            )
            self.assertIn(
                normalized["formula"]["formula_kind"],
                {"affine", "exact-expression", "bounded-declaration"},
            )
            self.assertIs(type(normalized["parameter_shape"]["complexity_parameters"]), list)
            self.assertTrue(
                normalized["parameter_shape"]["request_carriers_identity_free"]
            )
            self.assertIn(
                normalized["quantization"]["declaration"],
                {
                    "inline-formula-contract",
                    "not-separately-declared",
                    "structured-implementation-contract",
                },
            )
            receipt = row["conformance_receipt"]
            self.assertIs(receipt["actual_chunks_attested"], False)
            self.assertIs(receipt["actual_payload_bytes_attested"], False)
            self.assertIs(receipt["validator_accepted_all"], True)
            self.assertEqual(receipt["probe_count"], 3)
            self.assertEqual(
                [probe["lane"] for probe in receipt["probes"]],
                ["minimum", "midpoint", "maximum"],
            )
            for probe in receipt["probes"]:
                self.assertGreater(probe["payload_bytes"], 0)
                self.assertRegex(probe["payload_sha256"], r"^[0-9a-f]{64}$")
                self.assertRegex(
                    probe["validator_receipt_sha256"], r"^[0-9a-f]{64}$"
                )

    def test_pair_payload_receipts_include_final_raw_document_pin(self):
        receipts = self.value["implementation_pair_conformance_receipts"]
        self.assertEqual(len(receipts), 8)
        self.assertEqual(sum(row["probe_count"] for row in receipts), 213)
        self.assertEqual(
            {
                row["implementation_pair_id"]: row["payload_aggregate_sha256"]
                for row in receipts
            },
            EXPECTED_PAIR_PAYLOAD_AGGREGATES,
        )
        for row in receipts:
            self.assertEqual(
                row["variant_count"],
                EXPECTED_PAIR_VARIANT_COUNTS[row["implementation_pair_id"]],
            )
            self.assertEqual(row["probe_count"], 3 * row["variant_count"])

    def test_binding_and_catalog_rejection_precedes_provider_calls(self):
        calls = []

        def forbidden_provider(*args):
            calls.append(args)
            raise AssertionError("provider must not be called")

        forged = copy.deepcopy(self.value)
        forged["contract_bindings"][0]["sha256"] = "0" * 64
        with self.assertRaises(
            independent.PersonaV2FormatImplementationRegistryValidationError
        ):
            self._validate_independently(
                forged,
                renderer_contract_provider=forbidden_provider,
                validator_contract_provider=forbidden_provider,
                renderer_probe_provider=forbidden_provider,
            )
        self.assertEqual(calls, [])

        forged_upstream = copy.deepcopy(self.variant_value)
        forged_upstream["variant_rows"][0]["gate_role"] = "raw_only"
        with self.assertRaises(
            independent.PersonaV2FormatImplementationRegistryValidationError
        ):
            self._validate_independently(
                self.value,
                variant_value=forged_upstream,
                renderer_contract_provider=forbidden_provider,
                validator_contract_provider=forbidden_provider,
                renderer_probe_provider=forbidden_provider,
            )
        self.assertEqual(calls, [])

    def test_contract_provider_body_tamper_is_rejected(self):
        calls = []

        def renderer_provider(binding_id):
            calls.append(binding_id)
            value = self.renderer_contract_provider(binding_id)
            value = copy.deepcopy(value)
            if binding_id == "contributor-text-renderer-contract":
                value["variant_rows"][0]["render_template"] = "poisoned"
            return value

        with self.assertRaises(
            independent.PersonaV2FormatImplementationRegistryValidationError
        ):
            self._validate_independently(
                self.value, renderer_contract_provider=renderer_provider
            )
        self.assertEqual(calls, ["contributor-text-renderer-contract"])

    def test_provider_callback_cannot_mutate_registry_after_opening_pin(self):
        candidate = copy.deepcopy(self.value)
        calls = []

        def mutating_renderer_provider(variant_id, parameters):
            if not calls:
                candidate["completion_scope"] = "mutated-during-provider-callback"
            calls.append(variant_id)
            return self.renderer_probe_provider(variant_id, parameters)

        with self.assertRaises(
            independent.PersonaV2FormatImplementationRegistryValidationError
        ):
            self._validate_independently(
                candidate,
                renderer_probe_provider=mutating_renderer_provider,
            )
        self.assertTrue(calls)
        self.assertEqual(
            candidate["completion_scope"],
            "mutated-during-provider-callback",
        )

    def test_direct_runtime_validator_rejects_cross_variant_payload_rethread(self):
        wrong_calls = []

        def wrong_renderer_provider(variant_id, parameters):
            if variant_id == "go":
                wrong_calls.append((variant_id, "js"))
                correct_metadata = self.renderer_probe_provider("go", parameters)
                wrong_rendered = self.renderer_probe_provider("js", parameters)
                correct_metadata["data"] = wrong_rendered["data"]
                correct_metadata["target_bytes"] = len(wrong_rendered["data"])
                return correct_metadata
            return self.renderer_probe_provider(variant_id, parameters)

        with self.assertRaises(
            independent.PersonaV2FormatImplementationRegistryValidationError
        ):
            self._validate_independently(
                self.value,
                renderer_probe_provider=wrong_renderer_provider,
            )
        self.assertEqual(wrong_calls, [("go", "js")])

    def test_tamper_rethread_alias_overlap_and_missing_row_are_rejected(self):
        forged_values = []

        rethreaded = copy.deepcopy(self.value)
        rethreaded["implementation_rows"][0]["implementation"]["pair_id"] = (
            "raw-domain"
        )
        forged_values.append(rethreaded)

        overlapping = copy.deepcopy(self.value)
        second_renderer = next(
            row
            for row in overlapping["contract_bindings"]
            if row["binding_id"] == "pdf-text-renderer-contract"
        )
        second_renderer["variant_ids"][0] = overlapping["contract_bindings"][0][
            "variant_ids"
        ][0]
        forged_values.append(overlapping)

        missing = copy.deepcopy(self.value)
        missing["implementation_rows"].pop()
        forged_values.append(missing)

        receipt_tamper = copy.deepcopy(self.value)
        receipt_tamper["implementation_rows"][0]["conformance_receipt"]["probes"][
            0
        ]["payload_sha256"] = "0" * 64
        forged_values.append(receipt_tamper)

        forged_values.append(DictAlias(copy.deepcopy(self.value)))
        bool_alias = copy.deepcopy(self.value)
        bool_alias["coverage"]["total"]["variant_count"] = True
        forged_values.append(bool_alias)

        for forged in forged_values:
            with self.subTest(kind=type(forged).__name__):
                with self.assertRaises(
                    independent.PersonaV2FormatImplementationRegistryValidationError
                ):
                    self._validate_independently(forged)

    def test_standalone_import_boundary_uses_trusted_validators_not_producer_renderers(self):
        source = inspect.getsource(independent)
        self.assertNotIn("import persona_v2_format_implementation_registry\n", source)
        self.assertNotIn("_renderer as", source)
        self.assertEqual(
            set(independent.VALIDATOR_RUNTIME_SPECS),
            set(EXPECTED_PAIR_VARIANT_COUNTS),
        )
        self.assertTrue(
            all(
                module.__name__.endswith("_validator")
                for module, _, _ in independent.VALIDATOR_RUNTIME_SPECS.values()
            )
        )
        eval_dir = os.path.dirname(independent.__file__)
        script = (
            "import builtins,sys\n"
            f"sys.path.insert(0,{eval_dir!r})\n"
            "original=builtins.__import__\n"
            "def guarded(name,*a,**k):\n"
            "  if name == 'persona_v2_format_implementation_registry' or name.endswith('_renderer'):\n"
            "    raise RuntimeError(name)\n"
            "  return original(name,*a,**k)\n"
            "builtins.__import__=guarded\n"
            "import persona_v2_format_implementation_registry_validator as v\n"
            "print(v.ARTIFACT_SCHEMA)\n"
        )
        completed = subprocess.run(
            [sys.executable, "-c", script],
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.stdout.strip(), independent.ARTIFACT_SCHEMA)

    def test_all_identity_free_request_carriers_are_exactly_slotted(self):
        checked = 0
        for pair in FORMAT_PAIRS:
            for role in ("renderer", "validator"):
                module = importlib.import_module(f"eval.persona_v2_{pair}_{role}")
                carriers = [
                    value
                    for value in vars(module).values()
                    if isinstance(value, type)
                    and is_dataclass(value)
                    and value.__name__.endswith("Request")
                ]
                self.assertEqual(len(carriers), 1, (pair, role))
                carrier = carriers[0]
                declared = tuple(field.name for field in fields(carrier))
                self.assertEqual(declared, tuple(module.REQUEST_FIELDS))
                self.assertEqual(tuple(carrier.__slots__), declared)
                self.assertTrue(PROHIBITED_CARRIER_FIELDS.isdisjoint(declared))
                instance = carrier.__new__(carrier)
                self.assertFalse(hasattr(instance, "__dict__"))
                for extra in ("source_id", "query_id", "history_event_id"):
                    with self.assertRaises(AttributeError):
                        object.__setattr__(instance, extra, "identity-injection")
                checked += 1
        self.assertEqual(checked, 16)

    def test_hostile_variant_repr_never_escapes_public_pair_errors(self):
        class ExplosiveRepr:
            def __repr__(self):
                raise RuntimeError("repr must not be called")

        defaults = {
            "schema_version": 2,
            "variant": ExplosiveRepr(),
            "target_complexity": 1,
            "width": 65,
            "height": 64,
            "frame_or_event_count": 0,
            "data": b"",
            "extension": "",
            "content_media_type": "",
            "expected_kcs_path_media_type": "",
            "expected_offline_disposition": "",
        }
        for pair_id, (
            render_request_type,
            render,
            validation_request_type,
            validate,
        ) in registry.RUNTIME_SPECS.items():
            for role, request_type, operation in (
                ("renderer", render_request_type, render),
                ("validator", validation_request_type, validate),
            ):
                request = request_type(
                    **{
                        field_name: defaults[field_name]
                        for field_name in request_type.__dataclass_fields__
                    }
                )
                with self.subTest(pair=pair_id, role=role):
                    with self.assertRaises(ValueError):
                        operation(request)


if __name__ == "__main__":
    unittest.main()
