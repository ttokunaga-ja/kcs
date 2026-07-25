"""Focused fast gates for the capacity fact truth/occurrence policy."""

from __future__ import annotations

import ast
import collections
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import unittest
from unittest import mock

try:  # Support package and direct discovery modes.
    from . import persona_v2_capacity_fact_truth_occurrence_policy as package
    from . import persona_v2_capacity_fact_truth_occurrence_policy_validator as independent
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_capacity_fact_truth_occurrence_policy as package
    import persona_v2_capacity_fact_truth_occurrence_policy_validator as independent


def _imported_modules(path):
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.append(node.module)
            names.extend(alias.name for alias in node.names)
    return names


def _serialized_keys(value):
    keys = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            keys.extend(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return keys


class PersonaV2CapacityFactTruthOccurrencePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_capacity_fact_truth_occurrence_policy()
        cls.raw = package.canonical_json_bytes(cls.value)

    def _validate(self, value, **overrides):
        arguments = {
            "producer_expected_golden": package._expected_golden(),
            "capacity_axis_provider": package._capacity_axis_provider,
            "fact_graph_provider": package._fact_graph_provider,
            "capacity_cell_body_provider": package.capacity_axis.capacity_cell_body_bytes,
            "policy_body_provider": package.fact_truth_occurrence_policy_body_bytes,
        }
        arguments.update(overrides)
        return independent.validate_capacity_fact_truth_occurrence_policy(
            value, **arguments
        )

    def test_identity_exact_goldens_and_both_validators(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertEqual(self.value["artifact_kind"], package.ARTIFACT_KIND)
        self.assertLess(len(self.raw), package.TARGET_CATALOG_BYTES)
        exact = (
            29_868,
            "9f9653c1bb7a794bea33fe208b1de3c63f8dc011b8ac13f2d9a6955333681cd4",
        )
        self.assertEqual(package._require_golden_parity(), exact)
        self.assertEqual(independent._expected_golden(), exact)
        self.assertEqual((len(self.raw), hashlib.sha256(self.raw).hexdigest()), exact)
        self.assertTrue(package.validate_capacity_fact_truth_occurrence_policy(self.value))
        self.assertTrue(self._validate(self.value))

    def test_exact_720_persona_sharded_policy_rows_and_branch_templates(self):
        branch_rows = collections.Counter()
        row_ids = set()
        for persona_id in package.PERSONA_IDS:
            rows = package.build_fact_truth_occurrence_policy_rows(persona_id)
            self.assertEqual(len(rows), 36)
            self.assertEqual(
                [row["policy_row_id"] for row in rows],
                sorted((row["policy_row_id"] for row in rows), key=str.encode),
            )
            self.assertEqual(len({(row["topic_id"], row["fact_id"]) for row in rows}), 36)
            self.assertEqual(collections.Counter(row["branch"] for row in rows), {
                "stable": 28,
                "prior": 4,
                "introduced": 4,
            })
            for row in rows:
                self.assertEqual(row["persona_id"], persona_id)
                self.assertNotIn(row["policy_row_id"], row_ids)
                row_ids.add(row["policy_row_id"])
                branch_rows[row["branch"]] += 1
                states = row["checkpoint_states"]
                self.assertEqual(
                    [state["checkpoint"] for state in states],
                    list(package.CHECKPOINT_ORDER),
                )
                if row["branch"] == "stable":
                    self.assertEqual([state["truth_state"] for state in states], ["current"] * 7)
                    self.assertEqual([state["occurrence_state"] for state in states], ["fresh-current"] * 7)
                elif row["branch"] == "prior":
                    self.assertEqual([state["truth_state"] for state in states], ["current"] + ["history-only"] * 6)
                    self.assertEqual([state["occurrence_state"] for state in states], ["fresh-current"] + ["stale-current"] * 6)
                    self.assertEqual(sum(state["intentional_divergence"] for state in states), 6)
                else:
                    self.assertEqual([state["truth_state"] for state in states], ["absent"] + ["current"] * 6)
                    self.assertEqual([state["occurrence_state"] for state in states], ["absent"] + ["fresh-current"] * 6)
                    self.assertTrue(states[0]["neutral_required"])
                    self.assertFalse(any(state["neutral_required"] for state in states[1:]))
                self.assertFalse(any(state["future_before_introduction"] for state in states))
        self.assertEqual(len(row_ids), 720)
        self.assertEqual(dict(branch_rows), {"stable": 560, "prior": 80, "introduced": 80})

    def test_exact_capacity_join_projection_truth_and_occurrence_totals(self):
        summary = self.value["summary"]
        self.assertEqual(summary["capacity_cell_count"], 15_048)
        self.assertEqual(summary["checkpoint_count"], 7)
        self.assertEqual(summary["checkpoint_projection_count"], 105_336)
        self.assertEqual(
            summary["branch_capacity_cell_counts"],
            {"stable": 11_704, "prior": 1_672, "introduced": 1_672},
        )
        self.assertEqual(
            summary["truth_state_counts"],
            {"current": 93_632, "history-only": 10_032, "absent": 1_672},
        )
        self.assertEqual(
            summary["occurrence_state_counts"],
            {"fresh-current": 93_632, "stale-current": 10_032, "absent": 1_672},
        )
        self.assertEqual(summary["intentional_divergence_count"], 10_032)
        self.assertEqual(summary["neutral_required_count"], 1_672)
        self.assertEqual(summary["future_before_introduction_count"], 0)
        self.assertEqual(15_048 * 7, 105_336)

    def test_external_policy_bodies_are_exact_bounded_receipted_jsonl(self):
        total = 0
        for persona in self.value["personas"]:
            persona_id = persona["persona_id"]
            body = package.fact_truth_occurrence_policy_body_bytes(persona_id)
            descriptor = persona["fact_truth_occurrence_policy_body"]
            self.assertIs(type(body), bytes)
            self.assertEqual(len(body), descriptor["body_bytes"])
            self.assertEqual(hashlib.sha256(body).hexdigest(), descriptor["body_sha256"])
            lines = body.splitlines(keepends=True)
            self.assertEqual(len(lines), 36)
            self.assertTrue(all(line.endswith(b"\n") for line in lines))
            self.assertEqual(max(map(len, lines)), descriptor["maximum_row_bytes_including_lf"])
            self.assertLessEqual(max(map(len, lines)), package.MAX_POLICY_ROW_BYTES_INCLUDING_LF)
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            self.assertEqual(first["policy_row_id"], descriptor["first_policy_row_id"])
            self.assertEqual(last["policy_row_id"], descriptor["last_policy_row_id"])
            total += len(body)
        self.assertEqual(total, self.value["summary"]["external_policy_body_bytes"])
        self.assertEqual(total, self.value["canonical_limits"]["cumulative_external_body_bytes"])
        self.assertLessEqual(total, package.MAX_CUMULATIVE_EXTERNAL_BODY_BYTES)
        self.assertFalse(self.value["canonical_limits"]["external_bodies_embedded"])

    def test_capacity_axis_exact_pin_is_accepted_frozen_not_issued_and_graphs_bound(self):
        bindings = self.value["input_bindings"]
        self.assertEqual(len(bindings), 21)
        axis = bindings[0]
        self.assertEqual(axis["canonical_bytes"], 50_473)
        self.assertEqual(
            axis["sha256"],
            "4ed31455acb12c49b9dd14e2dd51f8ee81ed2a4845444949a80626df84ac8a29",
        )
        self.assertIs(axis["accepted"], True)
        self.assertIs(axis["frozen"], True)
        self.assertIs(axis["issued"], False)
        self.assertTrue(axis["body_opened_for_policy_derivation"])
        self.assertEqual(
            [binding["persona_id"] for binding in bindings[1:]],
            list(package.PERSONA_IDS),
        )
        self.assertTrue(all(binding["body_opened_for_policy_derivation"] for binding in bindings[1:]))

    def test_all_downstream_authority_acceptance_and_fit_claims_fail_closed(self):
        self.assertTrue(self.value["proposal_only"])
        self.assertFalse(self.value["g0_contract_frozen"])
        self.assertEqual(set(self.value["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        claims = self.value["completion_claims"]
        self.assertIs(claims["capacity_axis_accepted"], True)
        self.assertIs(claims["capacity_axis_frozen"], True)
        self.assertIs(claims["capacity_axis_issued"], False)
        for field in (
            "fact_truth_occurrence_policy_acceptance_receipt_bound",
            "fact_truth_occurrence_policy_golden_freeze_receipt_bound",
            "fact_truth_occurrence_policy_issued",
            "full_dependency_body_replay_receipt_bound",
            "history_plan_available",
            "physical_source_membership_available",
            "render_plan_available",
            "source_slot_assignment_available",
            "two_hash_seed_cold_build_receipt_bound",
            "w5_fit_proved",
        ):
            self.assertIs(claims[field], False)
        self.assertTrue(all(status.startswith("unknown-") for status in self.value["downstream_status"].values()))
        with self.assertRaises(package.PersonaV2CapacityFactTruthOccurrencePolicyError):
            package.require_accepted_capacity_fact_truth_occurrence_policy()

    def test_candidate_and_policy_rows_have_no_prohibited_fields_or_imports(self):
        banned = ("query", "oracle", "evaluation")
        candidate_keys = _serialized_keys(self.value)
        self.assertFalse([key for key in candidate_keys if any(token in key.lower() for token in banned)])
        for persona_id in package.PERSONA_IDS:
            keys = _serialized_keys(package.build_policy_rows(persona_id))
            self.assertFalse([key for key in keys if any(token in key.lower() for token in banned)])
        producer_path = Path(package.__file__)
        validator_path = Path(independent.__file__)
        for path in (producer_path, validator_path):
            imports = _imported_modules(path)
            self.assertFalse([name for name in imports if any(token in name.lower() for token in banned)])
        self.assertFalse(
            [
                name
                for name in _imported_modules(validator_path)
                if "persona_v2_capacity_fact_truth_occurrence_policy" in name
            ]
        )

    def test_independent_reconstruction_rejects_count_state_pin_and_bool_drift(self):
        mutations = []
        changed = copy.deepcopy(self.value)
        changed["summary"]["checkpoint_projection_count"] += 1
        mutations.append(changed)
        changed = copy.deepcopy(self.value)
        changed["input_bindings"][0]["sha256"] = "0" * 64
        mutations.append(changed)
        changed = copy.deepcopy(self.value)
        changed["completion_claims"]["w5_fit_proved"] = 0
        mutations.append(changed)
        for value in mutations:
            with self.subTest(value=value["summary"].get("checkpoint_projection_count")), self.assertRaises(
                independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError
            ):
                self._validate(value)

    def test_every_provider_is_two_read_and_unstable_provider_fails(self):
        calls = collections.Counter()

        def axis_provider():
            calls["axis"] += 1
            return package._capacity_axis_provider()

        def graph_provider(persona_id):
            calls[("graph", persona_id)] += 1
            return package._fact_graph_provider(persona_id)

        def cell_provider(persona_id):
            calls[("cell", persona_id)] += 1
            return package.capacity_axis.capacity_cell_body_bytes(persona_id)

        def policy_provider(persona_id):
            calls[("policy", persona_id)] += 1
            return package.policy_body_bytes(persona_id)

        self.assertTrue(
            self._validate(
                self.value,
                capacity_axis_provider=axis_provider,
                fact_graph_provider=graph_provider,
                capacity_cell_body_provider=cell_provider,
                policy_body_provider=policy_provider,
            )
        )
        self.assertEqual(calls["axis"], 2)
        for persona_id in package.PERSONA_IDS:
            self.assertEqual(calls[("graph", persona_id)], 2)
            self.assertEqual(calls[("cell", persona_id)], 2)
            self.assertEqual(calls[("policy", persona_id)], 2)

        unstable_calls = collections.Counter()

        def unstable_policy(persona_id):
            unstable_calls[persona_id] += 1
            body = package.policy_body_bytes(persona_id)
            return body if unstable_calls[persona_id] == 1 else body + b"\n"

        with self.assertRaises(independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError):
            self._validate(self.value, policy_body_provider=unstable_policy)
        self.assertEqual(unstable_calls["p01"], 2)

    def test_provider_mutation_of_caller_object_is_detected(self):
        value = copy.deepcopy(self.value)
        calls = 0

        def mutating_axis_provider():
            nonlocal calls
            calls += 1
            if calls == 1:
                value["summary"]["capacity_cell_count"] += 1
            return package._capacity_axis_provider()

        with self.assertRaises(independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError):
            self._validate(value, capacity_axis_provider=mutating_axis_provider)
        self.assertEqual(calls, 2)

    def test_preflight_alias_cycle_and_scalar_types_fail_closed(self):
        shared = []
        alias = {"a": shared, "b": shared}
        with self.assertRaises(package.PersonaV2CapacityFactTruthOccurrencePolicyError):
            package.canonical_json_bytes(alias)
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(package.PersonaV2CapacityFactTruthOccurrencePolicyError):
            package.canonical_json_bytes(cycle)
        for scalar in (None, 1.5, -1):
            with self.subTest(scalar=scalar), self.assertRaises(
                package.PersonaV2CapacityFactTruthOccurrencePolicyError
            ):
                package.canonical_json_bytes({"value": scalar})

    def test_golden_atomicity_and_parity_fail_before_any_provider(self):
        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(package, "EXPECTED_CANONICAL_BYTES", len(self.raw)), mock.patch.object(
            package, "EXPECTED_SHA256", None
        ):
            with self.assertRaises(package.PersonaV2CapacityFactTruthOccurrencePolicyError):
                package.build_capacity_fact_truth_occurrence_policy()
        with mock.patch.object(independent, "EXPECTED_CANONICAL_BYTES", len(self.raw)), mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ):
            with self.assertRaises(independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError):
                independent.validate_capacity_fact_truth_occurrence_policy(
                    self.value,
                    producer_expected_golden=None,
                    capacity_axis_provider=provider,
                    fact_graph_provider=provider,
                    capacity_cell_body_provider=provider,
                    policy_body_provider=provider,
                )
        provider.assert_not_called()

    def test_raw_loader_rejects_duplicate_noncanonical_and_oversize_before_provider(self):
        self.assertTrue(
            independent.validate_capacity_fact_truth_occurrence_policy_bytes(
                self.raw,
                producer_expected_golden=package._expected_golden(),
                capacity_axis_provider=package._capacity_axis_provider,
                fact_graph_provider=package._fact_graph_provider,
                capacity_cell_body_provider=package.capacity_axis.capacity_cell_body_bytes,
                policy_body_provider=package.policy_body_bytes,
            )
        )
        invalid = (
            b'{"artifact_kind":"x","artifact_kind":"y"}',
            b'{ "artifact_kind":"x" }',
            b'{"value":1.5}',
            b'{"value":' + b"9" * 100 + b"}",
            b"x" * (independent.MAX_CATALOG_BYTES + 1),
        )
        for raw in invalid:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.subTest(size=len(raw)), self.assertRaises(
                independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError
            ):
                independent.validate_capacity_fact_truth_occurrence_policy_bytes(
                    raw,
                    producer_expected_golden=package._expected_golden(),
                    capacity_axis_provider=provider,
                    fact_graph_provider=provider,
                    capacity_cell_body_provider=provider,
                    policy_body_provider=provider,
                )
            provider.assert_not_called()

    def test_configured_exact_pair_survives_freeze_and_mismatch_fails(self):
        pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        patches = (
            mock.patch.object(package, "EXPECTED_CANONICAL_BYTES", pair[0]),
            mock.patch.object(package, "EXPECTED_SHA256", pair[1]),
            mock.patch.object(independent, "EXPECTED_CANONICAL_BYTES", pair[0]),
            mock.patch.object(independent, "EXPECTED_SHA256", pair[1]),
        )
        with patches[0], patches[1], patches[2], patches[3]:
            self.assertEqual(package._require_golden_parity(), pair)
            self.assertTrue(package.validate_capacity_fact_truth_occurrence_policy(self.value))
        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(independent, "EXPECTED_CANONICAL_BYTES", pair[0]), mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ):
            with self.assertRaises(independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError):
                independent.validate_capacity_fact_truth_occurrence_policy(
                    self.value,
                    producer_expected_golden=pair,
                    capacity_axis_provider=provider,
                    fact_graph_provider=provider,
                    capacity_cell_body_provider=provider,
                    policy_body_provider=provider,
                )
        provider.assert_not_called()


@unittest.skipUnless(
    os.environ.get("KCS_RUN_CAPACITY_FACT_TRUTH_OCCURRENCE_POLICY_FULL") == "1",
    "set KCS_RUN_CAPACITY_FACT_TRUTH_OCCURRENCE_POLICY_FULL=1 for full replay",
)
class PersonaV2CapacityFactTruthOccurrencePolicyFullTest(unittest.TestCase):
    def test_full_two_read_replay_with_measurement(self):
        import resource

        started = time.monotonic()
        value = package.build_capacity_fact_truth_occurrence_policy()
        calls = collections.Counter()

        def axis_provider():
            calls["axis"] += 1
            return package._capacity_axis_provider()

        def graph_provider(persona_id):
            calls[("graph", persona_id)] += 1
            return package._fact_graph_provider(persona_id)

        def cell_provider(persona_id):
            calls[("cell", persona_id)] += 1
            return package.capacity_axis.capacity_cell_body_bytes(persona_id)

        def policy_provider(persona_id):
            calls[("policy", persona_id)] += 1
            return package.policy_body_bytes(persona_id)

        independent.validate_capacity_fact_truth_occurrence_policy(
            value,
            producer_expected_golden=package._expected_golden(),
            capacity_axis_provider=axis_provider,
            fact_graph_provider=graph_provider,
            capacity_cell_body_provider=cell_provider,
            policy_body_provider=policy_provider,
        )
        raw = package.canonical_json_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        measurement = {
            "canonical_bytes": len(raw),
            "elapsed_seconds": time.monotonic() - started,
            "maximum_rss_bytes": rss,
            "sha256": hashlib.sha256(raw).hexdigest(),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(calls["axis"], 2)
        self.assertTrue(all(calls[(kind, persona_id)] == 2 for kind in ("graph", "cell", "policy") for persona_id in package.PERSONA_IDS))
        self.assertLessEqual(measurement["canonical_bytes"], package.TARGET_CATALOG_BYTES)
        self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
        self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)


@unittest.skipUnless(
    os.environ.get("KCS_RUN_CAPACITY_FACT_TRUTH_OCCURRENCE_POLICY_COLD") == "1",
    "set KCS_RUN_CAPACITY_FACT_TRUTH_OCCURRENCE_POLICY_COLD=1 for two cold builds",
)
class PersonaV2CapacityFactTruthOccurrencePolicyColdTest(unittest.TestCase):
    def test_two_hashseed_cold_builds_are_byte_identical(self):
        script = r'''
import hashlib
import json
import os
import resource
import sys
import time
from eval import persona_v2_capacity_fact_truth_occurrence_policy as package
started = time.monotonic()
value = package.build_capacity_fact_truth_occurrence_policy()
package.validate_capacity_fact_truth_occurrence_policy(value)
raw = package.canonical_json_bytes(value)
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({"bytes": len(raw), "elapsed_seconds": time.monotonic() - started, "maximum_rss_bytes": rss, "seed": os.environ.get("PYTHONHASHSEED"), "sha256": hashlib.sha256(raw).hexdigest()}, sort_keys=True))
'''
        rows = []
        for seed in ("0", "1"):
            environment = dict(os.environ)
            environment.update({"LANG": "C", "LC_ALL": "C", "PYTHONHASHSEED": seed, "TZ": "UTC"})
            environment.pop("KCS_RUN_CAPACITY_FACT_TRUTH_OCCURRENCE_POLICY_COLD", None)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=21_600,
            )
            rows.append(json.loads(result.stdout.splitlines()[-1]))
        self.assertEqual([row["seed"] for row in rows], ["0", "1"])
        self.assertTrue(all(row["bytes"] <= package.TARGET_CATALOG_BYTES for row in rows))
        self.assertTrue(all(row["elapsed_seconds"] <= 21_600 for row in rows))
        self.assertTrue(all(row["maximum_rss_bytes"] <= 1 * 2**30 for row in rows))
        self.assertEqual((rows[0]["bytes"], rows[0]["sha256"]), (rows[1]["bytes"], rows[1]["sha256"]))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
