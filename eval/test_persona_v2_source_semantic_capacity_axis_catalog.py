"""Focused fast gates for the source-semantic capacity-axis candidate."""

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
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_source_semantic_capacity_axis_catalog as package
    from . import persona_v2_source_semantic_capacity_axis_catalog_validator as independent
    from . import persona_v2_source_semantic_membership_package as source_semantic
except ImportError:  # pragma: no cover - direct discovery compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_fact_graph as fact_graph
    import persona_v2_source_semantic_capacity_axis_catalog as package
    import persona_v2_source_semantic_capacity_axis_catalog_validator as independent
    import persona_v2_source_semantic_membership_package as source_semantic


EXPECTED_LANGUAGES = {
    "p01": ["ja", "en"], "p02": ["en"], "p03": ["ja", "en"],
    "p04": ["en"], "p05": ["ja", "en"], "p06": ["en"],
    "p07": ["en", "fr", "de", "ja"], "p08": ["ja", "en"],
    "p09": ["en", "ja"], "p10": ["en"], "p11": ["en", "es"],
    "p12": ["ja", "en"], "p13": ["ja", "en"],
    "p14": ["ja", "en"], "p15": ["ja", "en"],
    "p16": ["ja", "en"], "p17": ["ja", "en"],
    "p18": ["ja", "en"], "p19": ["ja", "en"],
    "p20": ["ja", "en"],
}


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


class PersonaV2SourceSemanticCapacityAxisCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.value = package.build_source_semantic_capacity_axis_catalog()
        cls.raw = package.canonical_json_bytes(cls.value)
        cls.graphs = fact_graph.build_fact_graph_suite()

    def _independent_validate(
        self,
        value,
        provider=None,
        graphs=None,
        *,
        semantic_catalog_value=None,
        require_semantic_catalog_body=False,
    ):
        return independent.validate_source_semantic_capacity_axis_catalog(
            value,
            producer_expected_golden=package._expected_golden(),
            fact_graph_values=self.graphs if graphs is None else graphs,
            capacity_cell_body_provider=(
                package.capacity_cell_body_bytes if provider is None else provider
            ),
            semantic_catalog_value=semantic_catalog_value,
            require_semantic_catalog_body=require_semantic_catalog_body,
        )

    def test_candidate_identity_golden_parity_and_both_validators(self):
        self.assertEqual(self.value["artifact_schema"], package.ARTIFACT_SCHEMA)
        self.assertEqual(self.value["artifact_schema_version"], 1)
        self.assertLess(len(self.raw), package.TARGET_CATALOG_BYTES)
        expected = package._require_golden_parity()
        exact = (
            50_473,
            "2bcb84e6ca46f09b29a3f4756191b98970a4f78101e4455675b6c713dc1cab85",
        )
        self.assertEqual(expected, exact)
        self.assertEqual(expected, independent._expected_golden())
        self.assertEqual(
            expected,
            (len(self.raw), hashlib.sha256(self.raw).hexdigest()),
        )
        self.assertTrue(package.validate_source_semantic_capacity_axis_catalog(self.value))
        self.assertTrue(self._independent_validate(self.value))

    def test_exact_twenty_persona_language_and_cell_table(self):
        rows = self.value["personas"]
        self.assertEqual([row["persona_id"] for row in rows], list(package.PERSONA_IDS))
        self.assertEqual(len(rows), 20)
        for row in rows:
            languages = EXPECTED_LANGUAGES[row["persona_id"]]
            self.assertEqual(row["eligible_languages"], languages)
            self.assertEqual(row["eligible_language_count"], len(languages))
            self.assertEqual(row["persona_language_pair_count"], len(languages))
            self.assertEqual(row["topic_count"], 4)
            self.assertEqual(row["fact_count_per_topic"], 9)
            self.assertEqual(row["replica_count_per_fact_cell"], 11)
            self.assertEqual(row["capacity_cell_count"], len(languages) * 4 * 9 * 11)
        self.assertEqual(sum(len(value) for value in EXPECTED_LANGUAGES.values()), 38)
        self.assertEqual(self.value["summary"]["eligible_persona_language_pair_count"], 38)
        self.assertEqual(self.value["summary"]["capacity_cell_count"], 15_048)
        self.assertEqual(self.value["summary"]["minimum_persona_capacity_cell_count"], 396)
        self.assertEqual(self.value["summary"]["maximum_persona_capacity_cell_count"], 1_584)

    def test_exact_four_topics_and_nine_fact_ids_per_topic(self):
        graph_ids = set()
        fact_ids = set()
        for persona in self.value["personas"]:
            self.assertEqual(
                [topic["topic_slot"] for topic in persona["topics"]],
                ["g01", "g02", "g03", "g04"],
            )
            for topic in persona["topics"]:
                self.assertEqual(
                    topic["topic_id"],
                    f"{persona['persona_id']}-semantic-topic-{topic['topic_slot']}-v2",
                )
                self.assertEqual(topic["fact_count"], 9)
                self.assertEqual(len(topic["fact_ids"]), 9)
                self.assertEqual(len(set(topic["fact_ids"])), 9)
                self.assertFalse(graph_ids.intersection({topic["graph_id"]}))
                self.assertFalse(fact_ids.intersection(topic["fact_ids"]))
                graph_ids.add(topic["graph_id"])
                fact_ids.update(topic["fact_ids"])
        self.assertEqual(len(graph_ids), 80)
        self.assertEqual(len(fact_ids), 720)

    def test_all_15048_cells_collision_free_and_domain_separated(self):
        seen = set()
        for persona_id in package.PERSONA_IDS:
            rows = package.build_capacity_cell_rows(persona_id)
            self.assertEqual(
                len(rows),
                next(row for row in self.value["personas"] if row["persona_id"] == persona_id)["capacity_cell_count"],
            )
            ids = [row["capacity_cell_id"] for row in rows]
            self.assertEqual(ids, sorted(ids, key=str.encode))
            self.assertEqual(len(ids), len(set(ids)))
            self.assertFalse(seen.intersection(ids))
            seen.update(ids)
        self.assertEqual(len(seen), 15_048)
        first = package.build_capacity_cell_rows("p01")[0]
        logical = [first[field] for field in package.CELL_LOGICAL_KEY_FIELDS]
        framed = package.CELL_DOMAIN_LABEL.encode("ascii") + b"\x00" + artifact_common.canonical_json_bytes(
            logical, label="test capacity-cell key", max_bytes=4 * 1024
        )
        self.assertEqual(first["capacity_cell_id"], hashlib.sha256(framed).hexdigest())
        other = b"kio/persona-pc-v2/source-semantic-capacity-slot-order/v1\x00" + framed.split(b"\x00", 1)[1]
        self.assertNotEqual(first["capacity_cell_id"], hashlib.sha256(other).hexdigest())

    def test_external_persona_bodies_are_bounded_and_receipt_exact(self):
        total = 0
        for persona in self.value["personas"]:
            body = package.capacity_cell_body_bytes(persona["persona_id"])
            descriptor = persona["capacity_cell_body"]
            self.assertIs(type(body), bytes)
            self.assertLessEqual(len(body), package.MAX_CELL_BODY_BYTES)
            self.assertEqual(len(body), descriptor["body_bytes"])
            self.assertEqual(hashlib.sha256(body).hexdigest(), descriptor["body_sha256"])
            lines = body.splitlines(keepends=True)
            self.assertEqual(len(lines), descriptor["row_count"])
            self.assertTrue(all(line.endswith(b"\n") for line in lines))
            self.assertEqual(max(map(len, lines)), descriptor["maximum_row_bytes_including_lf"])
            self.assertLessEqual(max(map(len, lines)), package.MAX_CELL_ROW_BYTES_INCLUDING_LF)
            first = json.loads(lines[0])
            last = json.loads(lines[-1])
            self.assertEqual(first["capacity_cell_id"], descriptor["first_capacity_cell_id"])
            self.assertEqual(last["capacity_cell_id"], descriptor["last_capacity_cell_id"])
            total += len(body)
        self.assertEqual(total, self.value["summary"]["external_capacity_cell_body_bytes"])
        self.assertLessEqual(total, package.MAX_CUMULATIVE_EXTERNAL_BODY_BYTES)
        self.assertFalse(self.value["canonical_limits"]["external_bodies_embedded"])

    def test_exact_input_pins_and_no_evaluation_side_dependency(self):
        bindings = self.value["input_bindings"]
        self.assertEqual(len(bindings), 21)
        self.assertEqual(
            (bindings[0]["canonical_bytes"], bindings[0]["sha256"]),
            (436_495, "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b"),
        )
        self.assertFalse(bindings[0]["body_opened_for_axis_derivation"])
        self.assertTrue(all(row["body_opened_for_axis_derivation"] for row in bindings[1:]))
        self.assertEqual([row["persona_id"] for row in bindings[1:]], list(package.PERSONA_IDS))
        self.assertTrue(all(value == 0 for value in self.value["dependency_exclusion_contract"].values()))

    def test_candidate_is_all_false_non_authorizing_and_require_fails(self):
        self.assertTrue(self.value["proposal_only"])
        self.assertFalse(self.value["g0_contract_frozen"])
        self.assertEqual(set(self.value["authority"]), package.AUTHORITY_FIELDS)
        self.assertTrue(all(flag is False for flag in self.value["authority"].values()))
        claims = self.value["completion_claims"]
        for field in (
            "capacity_membership_available",
            "capacity_source_assignment_available",
            "cell_to_source_bijection_proved",
            "full_dependency_body_replay_receipt_bound",
            "namespace_v4_issued",
            "semantic_catalog_body_reauthentication_receipt_bound",
            "two_hash_seed_cold_build_receipt_bound",
        ):
            self.assertFalse(claims[field])
        with self.assertRaises(package.PersonaV2SourceSemanticCapacityAxisCatalogError):
            package.require_issued_source_semantic_capacity_axis_catalog()
        self.assertEqual(
            self.value["semantic_catalog_trust_root"],
            {
                "body_opened_in_fast_candidate_build": False,
                "body_required_for_full_acceptance": True,
                "frozen_pin_is_not_live_body_validation": True,
                "missing_or_mismatched_body_fails_full_acceptance": True,
                "opening_mode": "frozen-pin-only-fast-candidate",
            },
        )

    def test_detached_snapshots(self):
        first = package.build_source_semantic_capacity_axis_catalog()
        second = package.build_source_semantic_capacity_axis_catalog()
        first["personas"][0]["eligible_languages"].append("zz")
        self.assertNotEqual(first, second)
        self.assertEqual(second, package.build_source_semantic_capacity_axis_catalog())
        rows = package.build_capacity_cell_rows("p01")
        rows[0]["capacity_cell_id"] = "0" * 64
        self.assertNotEqual(rows, package.build_capacity_cell_rows("p01"))

    def test_independent_rejects_metadata_and_body_tampering(self):
        tampered = copy.deepcopy(self.value)
        tampered["summary"]["capacity_cell_count"] -= 1
        metadata_provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(tampered, provider=metadata_provider)
        metadata_provider.assert_not_called()

        authority = copy.deepcopy(self.value)
        authority["authority"]["authorizes_g0_freeze"] = True
        authority_provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(authority, provider=authority_provider)
        authority_provider.assert_not_called()

        calls = {}
        def nondeterministic(persona_id):
            count = calls.get(persona_id, 0)
            calls[persona_id] = count + 1
            body = package.capacity_cell_body_bytes(persona_id)
            return body if count == 0 else body + b"\n"

        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(self.value, provider=nondeterministic)

        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(
                self.value,
                provider=lambda _persona_id: b"x" * (package.MAX_CELL_BODY_BYTES + 1),
            )

    def test_structural_preflight_rejects_alias_cycle_oversize_before_provider(self):
        fixtures = []

        alias = copy.deepcopy(self.value)
        alias["orders"]["persona"] = alias["remaining_blockers"]
        fixtures.append(alias)

        cycle = copy.deepcopy(self.value)
        cycle["cycle"] = cycle
        fixtures.append(cycle)

        oversize = copy.deepcopy(self.value)
        oversize["remaining_blockers"] = [
            "x"
        ] * (independent.MAX_PREFLIGHT_CONTAINER_ITEMS + 1)
        fixtures.append(oversize)

        for candidate in fixtures:
            provider = mock.Mock(
                side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
            )
            with self.subTest(kind=type(candidate).__name__), self.assertRaises(
                independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
            ):
                self._independent_validate(candidate, provider=provider)
            provider.assert_not_called()

        graphs = copy.deepcopy(self.graphs)
        graphs[0]["eligible_languages"] = graphs[0]["graphs"]
        provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(self.value, graphs=graphs, provider=provider)
        provider.assert_not_called()

        graphs = copy.deepcopy(self.graphs)
        graphs[0]["cycle"] = graphs[0]
        provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(self.value, graphs=graphs, provider=provider)
        provider.assert_not_called()

    def test_codepoint_bomb_fails_before_normalization_encoding_and_provider(self):
        candidate = copy.deepcopy(self.value)
        candidate["candidate_status"] = "x" * (
            artifact_common.MAX_CANONICAL_STRING_BYTES + 1
        )
        provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with mock.patch.object(
            independent.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ), self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(candidate, provider=provider)
        provider.assert_not_called()

        with mock.patch.object(
            package.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ), self.assertRaises(
            package.PersonaV2SourceSemanticCapacityAxisCatalogError
        ):
            package.canonical_json_bytes(candidate)

    def test_utf8_byte_bomb_fails_before_encoder_and_provider(self):
        candidate = copy.deepcopy(self.value)
        candidate["candidate_status"] = "\U0001f600" * 1025
        provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with mock.patch.object(
            independent.artifact_common,
            "canonical_json_bytes",
            side_effect=AssertionError("canonical encoder reached"),
        ), self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(candidate, provider=provider)
        provider.assert_not_called()

        with mock.patch.object(
            package.artifact_common,
            "canonical_json_bytes",
            side_effect=AssertionError("canonical encoder reached"),
        ), self.assertRaises(
            package.PersonaV2SourceSemanticCapacityAxisCatalogError
        ):
            package.canonical_json_bytes(candidate)

    def test_capacity_cell_id_codepoint_bomb_fails_before_normalization(self):
        oversized = "x" * (artifact_common.MAX_CANONICAL_STRING_BYTES + 1)
        with mock.patch.object(
            package.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ) as normalize, self.assertRaises(
            package.PersonaV2SourceSemanticCapacityAxisCatalogError
        ):
            package.capacity_cell_id(
                oversized,
                "p01-semantic-topic-g01-v2",
                "en",
                "fact-syn-001",
                1,
            )
        normalize.assert_not_called()

    def test_capacity_cell_id_utf8_byte_bomb_fails_before_normalization(self):
        oversized = "\U0001f600" * 1025
        with mock.patch.object(
            package.unicodedata,
            "normalize",
            side_effect=AssertionError("normalization reached"),
        ) as normalize, self.assertRaises(
            package.PersonaV2SourceSemanticCapacityAxisCatalogError
        ):
            package.capacity_cell_id(
                oversized,
                "p01-semantic-topic-g01-v2",
                "en",
                "fact-syn-001",
                1,
            )
        normalize.assert_not_called()

    def test_semantic_catalog_full_trust_root_is_explicit_and_fail_closed(self):
        missing_provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(
                self.value,
                provider=missing_provider,
                require_semantic_catalog_body=True,
            )
        missing_provider.assert_not_called()

        wrong_body = copy.deepcopy(self.value)
        wrong_provider = mock.Mock(
            side_effect=lambda persona_id: package.capacity_cell_body_bytes(persona_id)
        )
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(
                self.value,
                provider=wrong_provider,
                semantic_catalog_value=wrong_body,
                require_semantic_catalog_body=True,
            )
        wrong_provider.assert_not_called()

    def test_provider_replayed_exactly_twice_per_persona(self):
        calls = []
        def provider(persona_id):
            calls.append(persona_id)
            return package.capacity_cell_body_bytes(persona_id)
        self.assertTrue(self._independent_validate(self.value, provider=provider))
        self.assertEqual(len(calls), 40)
        for persona_id in package.PERSONA_IDS:
            self.assertEqual(calls.count(persona_id), 2)

    def test_provider_callback_toctou_on_catalog_and_graphs_fails(self):
        target = copy.deepcopy(self.value)
        mutated = False
        def mutate_catalog(persona_id):
            nonlocal mutated
            if not mutated:
                target["candidate_status"] = "mutated"
                mutated = True
            return package.capacity_cell_body_bytes(persona_id)
        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(target, provider=mutate_catalog)

        graphs = copy.deepcopy(self.graphs)
        mutated = False
        def mutate_graph(persona_id):
            nonlocal mutated
            if not mutated:
                graphs[0]["eligible_languages"].append("zz")
                mutated = True
            return package.capacity_cell_body_bytes(persona_id)
        with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
            self._independent_validate(self.value, provider=mutate_graph, graphs=graphs)

        target = copy.deepcopy(self.value)
        mutated = False
        def mutate_to_cycle(persona_id):
            nonlocal mutated
            if not mutated:
                target["postflight_cycle"] = target
                mutated = True
            return package.capacity_cell_body_bytes(persona_id)
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            self._independent_validate(target, provider=mutate_to_cycle)

    def test_hash_uses_detached_opening_and_reauthenticates_live_caller(self):
        self.assertEqual(
            package.source_semantic_capacity_axis_catalog_sha256(self.value),
            hashlib.sha256(self.raw).hexdigest(),
        )
        target = copy.deepcopy(self.value)
        original_validate = package.validate_source_semantic_capacity_axis_catalog

        def mutate_live(snapshot):
            target["candidate_status"] = "mutated-during-hash"
            return original_validate(snapshot)

        with mock.patch.object(
            package,
            "validate_source_semantic_capacity_axis_catalog",
            side_effect=mutate_live,
        ), self.assertRaises(
            package.PersonaV2SourceSemanticCapacityAxisCatalogError
        ):
            package.source_semantic_capacity_axis_catalog_sha256(target)

    def test_partial_goldens_fail_closed_before_provider(self):
        for module, error in (
            (package, package.PersonaV2SourceSemanticCapacityAxisCatalogError),
            (independent, independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError),
        ):
            with mock.patch.object(module, "EXPECTED_CANONICAL_BYTES", len(self.raw)), mock.patch.object(
                module, "EXPECTED_SHA256", None
            ):
                with self.assertRaises(error):
                    module._expected_golden()
        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(independent, "EXPECTED_CANONICAL_BYTES", len(self.raw)), mock.patch.object(
            independent, "EXPECTED_SHA256", None
        ):
            with self.assertRaises(independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError):
                independent.validate_source_semantic_capacity_axis_catalog(
                    self.value,
                    producer_expected_golden=package._expected_golden(),
                    fact_graph_values=self.graphs,
                    capacity_cell_body_provider=provider,
                )
        provider.assert_not_called()

    def test_golden_parity_fails_before_dependency_or_provider(self):
        valid_pair = (len(self.raw), hashlib.sha256(self.raw).hexdigest())
        with mock.patch.object(
            independent, "EXPECTED_CANONICAL_BYTES", valid_pair[0]
        ), mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ), mock.patch.object(
            package.fact_graph,
            "build_fact_graph_suite",
            side_effect=AssertionError("dependency opened"),
        ) as dependency:
            with self.assertRaises(
                package.PersonaV2SourceSemanticCapacityAxisCatalogError
            ):
                package.build_source_semantic_capacity_axis_catalog()
        dependency.assert_not_called()

        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with mock.patch.object(
            independent, "EXPECTED_SHA256", "0" * 64
        ), self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            independent.validate_source_semantic_capacity_axis_catalog(
                self.value,
                producer_expected_golden=valid_pair,
                fact_graph_values=self.graphs,
                capacity_cell_body_provider=provider,
            )
        provider.assert_not_called()

        provider = mock.Mock(side_effect=AssertionError("provider opened"))
        with self.assertRaises(
            independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
        ):
            independent.validate_source_semantic_capacity_axis_catalog(
                self.value,
                fact_graph_values=self.graphs,
                capacity_cell_body_provider=provider,
            )
        provider.assert_not_called()

    def test_raw_json_and_oversize_fail_closed_before_provider(self):
        self.assertTrue(
            independent.validate_source_semantic_capacity_axis_catalog_bytes(
                self.raw,
                producer_expected_golden=package._expected_golden(),
                fact_graph_values=self.graphs,
                capacity_cell_body_provider=package.capacity_cell_body_bytes,
            )
        )
        invalid_raws = (
            b'{"artifact_kind":"x","artifact_kind":"y"}',
            b'{ "artifact_kind":"x" }',
            b"x" * (independent.MAX_CATALOG_BYTES + 1),
        )
        for raw in invalid_raws:
            provider = mock.Mock(side_effect=AssertionError("provider opened"))
            with self.subTest(size=len(raw)), self.assertRaises(
                independent.PersonaV2SourceSemanticCapacityAxisCatalogValidationError
            ):
                independent.validate_source_semantic_capacity_axis_catalog_bytes(
                    raw,
                    producer_expected_golden=package._expected_golden(),
                    fact_graph_values=self.graphs,
                    capacity_cell_body_provider=provider,
                )
            provider.assert_not_called()

    def test_import_graph_has_no_query_oracle_or_sibling_producer_leakage(self):
        producer_path = Path(package.__file__)
        validator_path = Path(independent.__file__)
        banned = ("query", "oracle", "target_resolution", "evaluation")
        for path in (producer_path, validator_path):
            imports = _imported_modules(path)
            self.assertFalse(
                [name for name in imports if any(token in name for token in banned)],
                (path, imports),
            )
        self.assertFalse(
            [
                name for name in _imported_modules(validator_path)
                if "persona_v2_source_semantic_capacity_axis_catalog" in name
            ]
        )


@unittest.skipUnless(
    os.environ.get("KIO_RUN_SOURCE_SEMANTIC_CAPACITY_AXIS_FULL") == "1",
    "set KIO_RUN_SOURCE_SEMANTIC_CAPACITY_AXIS_FULL=1 for full trust-root validation",
)
class PersonaV2SourceSemanticCapacityAxisCatalogFullTest(unittest.TestCase):
    def test_full_semantic_catalog_opening_and_body_replay(self):
        import resource

        started = time.monotonic()
        value = package.build_source_semantic_capacity_axis_catalog()
        graphs = fact_graph.build_fact_graph_suite()
        semantic_value = source_semantic.build_source_semantic_membership_catalog()
        provider_calls = collections.Counter()
        trust_root_calls = collections.Counter()
        original_authenticate = independent._authenticate_semantic_catalog_body

        def counted_provider(persona_id):
            provider_calls[persona_id] += 1
            return package.capacity_cell_body_bytes(persona_id)

        def counted_authenticate(*args, **kwargs):
            trust_root_calls["semantic_catalog"] += 1
            return original_authenticate(*args, **kwargs)

        with mock.patch.object(
            independent,
            "_authenticate_semantic_catalog_body",
            side_effect=counted_authenticate,
        ):
            self.assertTrue(
                independent.validate_source_semantic_capacity_axis_catalog(
                    value,
                    producer_expected_golden=package._expected_golden(),
                    fact_graph_values=graphs,
                    capacity_cell_body_provider=counted_provider,
                    semantic_catalog_value=semantic_value,
                    require_semantic_catalog_body=True,
                )
            )
        raw = package.canonical_json_bytes(value)
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform != "darwin":
            rss *= 1024
        elapsed = time.monotonic() - started
        measurement = {
            "canonical_bytes": len(raw),
            "elapsed_seconds": elapsed,
            "maximum_rss_bytes": rss,
            "provider_call_count": sum(provider_calls.values()),
            "semantic_catalog_opening_count": trust_root_calls["semantic_catalog"],
            "sha256": hashlib.sha256(raw).hexdigest(),
            "unique_provider_coordinate_count": len(provider_calls),
        }
        print(json.dumps(measurement, sort_keys=True))
        self.assertEqual(measurement["semantic_catalog_opening_count"], 1)
        self.assertEqual(measurement["provider_call_count"], 40)
        self.assertEqual(measurement["unique_provider_coordinate_count"], 20)
        self.assertTrue(all(count == 2 for count in provider_calls.values()))
        self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
        self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
        self.assertLessEqual(measurement["canonical_bytes"], package.TARGET_CATALOG_BYTES)


@unittest.skipUnless(
    os.environ.get("KIO_RUN_SOURCE_SEMANTIC_CAPACITY_AXIS_COLD") == "1",
    "set KIO_RUN_SOURCE_SEMANTIC_CAPACITY_AXIS_COLD=1 for two isolated full builds",
)
class PersonaV2SourceSemanticCapacityAxisCatalogColdTest(unittest.TestCase):
    def test_two_hashseed_full_builds_are_byte_identical(self):
        script = r'''
import collections
import hashlib
import json
import os
import resource
import sys
import time
from unittest import mock
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_source_semantic_capacity_axis_catalog as package
from eval import persona_v2_source_semantic_capacity_axis_catalog_validator as independent
from eval import persona_v2_source_semantic_membership_package as source_semantic

if package._require_golden_parity() != package._expected_golden():
    raise RuntimeError("capacity-axis golden parity drifted")
started = time.monotonic()
value = package.build_source_semantic_capacity_axis_catalog()
graphs = fact_graph.build_fact_graph_suite()
semantic_value = source_semantic.build_source_semantic_membership_catalog()
provider_calls = collections.Counter()
trust_root_calls = collections.Counter()
original_authenticate = independent._authenticate_semantic_catalog_body

def counted_provider(persona_id):
    provider_calls[persona_id] += 1
    return package.capacity_cell_body_bytes(persona_id)

def counted_authenticate(*args, **kwargs):
    trust_root_calls["semantic_catalog"] += 1
    return original_authenticate(*args, **kwargs)

with mock.patch.object(
    independent,
    "_authenticate_semantic_catalog_body",
    side_effect=counted_authenticate,
):
    independent.validate_source_semantic_capacity_axis_catalog(
        value,
        producer_expected_golden=package._expected_golden(),
        fact_graph_values=graphs,
        capacity_cell_body_provider=counted_provider,
        semantic_catalog_value=semantic_value,
        require_semantic_catalog_body=True,
    )
if trust_root_calls != {"semantic_catalog": 1}:
    raise RuntimeError("semantic catalog opening count drifted")
if len(provider_calls) != 20 or sum(provider_calls.values()) != 40:
    raise RuntimeError("capacity body replay count drifted")
if any(count != 2 for count in provider_calls.values()):
    raise RuntimeError("capacity body replay parity drifted")
raw = package.canonical_json_bytes(value)
rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
if sys.platform != "darwin":
    rss *= 1024
print(json.dumps({
    "canonical_bytes": len(raw),
    "elapsed_seconds": time.monotonic() - started,
    "maximum_rss_bytes": rss,
    "provider_call_count": sum(provider_calls.values()),
    "python_hash_seed": os.environ.get("PYTHONHASHSEED"),
    "semantic_catalog_opening_count": trust_root_calls["semantic_catalog"],
    "sha256": hashlib.sha256(raw).hexdigest(),
    "unique_provider_coordinate_count": len(provider_calls),
}, sort_keys=True))
'''
        measurements = []
        for seed in ("0", "1"):
            environment = dict(os.environ)
            environment.update(
                {
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONHASHSEED": seed,
                    "TZ": "UTC",
                }
            )
            environment.pop("KIO_RUN_SOURCE_SEMANTIC_CAPACITY_AXIS_COLD", None)
            result = subprocess.run(
                [sys.executable, "-c", script],
                cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                env=environment,
                check=True,
                capture_output=True,
                text=True,
                timeout=21_600,
            )
            measurement = json.loads(result.stdout.splitlines()[-1])
            self.assertEqual(measurement["python_hash_seed"], seed)
            self.assertEqual(measurement["semantic_catalog_opening_count"], 1)
            self.assertEqual(measurement["provider_call_count"], 40)
            self.assertEqual(measurement["unique_provider_coordinate_count"], 20)
            self.assertLessEqual(measurement["elapsed_seconds"], 21_600)
            self.assertLessEqual(measurement["maximum_rss_bytes"], 1 * 2**30)
            self.assertLessEqual(
                measurement["canonical_bytes"], package.TARGET_CATALOG_BYTES
            )
            measurements.append(measurement)
        self.assertEqual(
            (measurements[0]["canonical_bytes"], measurements[0]["sha256"]),
            (measurements[1]["canonical_bytes"], measurements[1]["sha256"]),
        )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
