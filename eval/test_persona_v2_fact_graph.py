import copy
import hashlib
import ipaddress
import re
import unittest

from eval import persona_v2_artifact_common as artifact_common
from eval import persona_v2_contract as envelope
from eval import persona_v2_fact_graph as fact_graph
from eval import persona_v2_fact_graph_data as data


EXPECTED_PERSONA_BINDINGS = (
    ("p01", 26_403, "94ab0655788534db4e784709a044fda2cdbeb69775082354b900068e8cbcd70d"),
    ("p02", 26_353, "92afd654b99da2b4eb537fd9269e0e95405a530e6c01d54eaaaeb8dae42887ef"),
    ("p03", 26_479, "648b4cb41ba37f925be9022ac683c8982e8aa8dc5d3a4cda0a020d93ae7d88ad"),
    ("p04", 26_569, "c184999ebbdc043cbb687965815e970954577022632a2b76720e4249e507bf32"),
    ("p05", 26_536, "ed8b9a49a65f9b9df00693492b1d27d8a52a70e23ba4d873a779160d54747b20"),
    ("p06", 26_522, "2c523a93fa6279b62aba2a7708a0929861b850f90260377e647455c8a810fe02"),
    ("p07", 26_672, "c2bc8a08e54de557617b5fe1c0b75732100c971c27bf1e6dc9bbc73b34bad3a4"),
    ("p08", 26_506, "fdce514cd277e9a5758a97fe6e814c68c3a29ec1d06c8cdd233f9adcb7650ae5"),
    ("p09", 26_544, "7db7bab2e3ca1c9c91ef7108a097646894907d358f9a304f72ee662e62c52a19"),
    ("p10", 26_497, "d7fb092cddfcfe45e6fc6910e35c33d8e00c1a99f8b272ff50e6d7c9edce1503"),
    ("p11", 26_428, "f2882db025022ee476ed2dba11e2813ecc3e0620df00ad2321295113d583c301"),
    ("p12", 26_518, "e86896736e304e1ba0b56fc43ddc31021db5cdb9b11f1edadd6ab9851389d994"),
    ("p13", 26_487, "c13953d43b88a817b4a6147c0e00c432f48ecaa7600610a5a87c3dc8e62cadb3"),
    ("p14", 26_426, "203cc67a8deaf06042d9a201237f89ceefe4c814705325d427c3dc1ecc7b1f62"),
    ("p15", 26_535, "302f8ba3fe9ee3a890724fb675a09a158d3890e70622b978441966b14af4a26e"),
    ("p16", 26_577, "ee1d0718b7b9cacc370ead3a19f1e8e5d22bdaf89fcb4503af2f225d17a77567"),
    ("p17", 26_483, "c342080dc551a4da7b2fbbcd0948bd80ffbc5300e3c04fae7400207639aaa119"),
    ("p18", 26_485, "26f3c8bbdd4af1ad87572a22ca45961d1276b30d699185331876839a73063eb9"),
    ("p19", 26_442, "02e33ebfdd8c381b704c2c0f67577f27588f5c4d442baad6e256570faf926b2f"),
    ("p20", 26_546, "423d3973d26d7ab8e234c1f93f04c166e3fcdc62b560101bbb4b893960a70df7"),
)
EXPECTED_SUITE_CANONICAL_BYTES = 530_008
EXPECTED_SUITE_SUMMARY_BYTES = 2_566
EXPECTED_SUITE_SUMMARY_SHA256 = (
    "ac976c886993a44dc40cd492a9da398736b464ffce36ff391b41d9df219003ac"
)


class PersonaV2FactGraphTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.values = fact_graph.build_fact_graph_suite()

    def test_identity_bindings_cap_and_negative_authority_are_exact(self):
        value = self.values[0]
        self.assertEqual(value["artifact_schema"], fact_graph.ARTIFACT_SCHEMA)
        self.assertEqual(value["artifact_kind"], fact_graph.ARTIFACT_KIND)
        self.assertEqual(value["artifact_schema_version"], 2)
        self.assertEqual(value["fixture_id"], envelope.FIXTURE_ID)
        self.assertEqual(value["persona_id"], "p01")
        self.assertIs(value["fact_graph_input_leaf_complete"], True)
        self.assertIs(value["fact_graph_inventory_complete"], True)
        self.assertIs(
            value["unordered_w0_current_fact_pair_inventory_complete"], True
        )
        self.assertIs(value["fact_oracle_input_closure_complete"], False)
        self.assertIs(value["source_intent_recipe_bound"], False)
        self.assertIs(value["history_intent_recipe_bound"], False)
        self.assertIs(value["semantic_surface_text_present"], False)
        self.assertIs(value["g0_contract_frozen"], False)
        self.assertEqual(
            [row["name"] for row in value["input_bindings"]],
            [
                "envelope",
                "topology",
                "joint-problem",
                "joint-solver-policy",
                "realism-profile",
            ],
        )
        realism_binding = value["input_bindings"][-1]
        self.assertEqual(realism_binding["canonical_bytes"], 36_811)
        self.assertEqual(realism_binding["sha256"], fact_graph.EXPECTED_REALISM_SHA256)
        self.assertEqual(value["canonical_limits"]["max_body_bytes"], 2**20)
        self.assertEqual(
            set(value["authority"]),
            {
                "actual_chunks_attested",
                "authorizes_g0_freeze",
                "authorizes_history_mutation",
                "authorizes_physical_write",
                "authorizes_solver_execution",
                "authorizes_source_plan",
                "filesystem_writer_available",
                "formal_capacity_gate_satisfied",
                "history_executor_available",
                "kio_execution_available",
                "query_instances_rendered",
                "query_spec_hashed",
                "renderer_available",
            },
        )
        for key, flag in value["authority"].items():
            self.assertIs(type(flag), bool, key)
            self.assertIs(flag, False, key)
        for key, flag in value["isolation_policy"].items():
            self.assertIs(type(flag), bool, key)
            self.assertIs(flag, False, key)
        raw = fact_graph.canonical_json_bytes(value)
        self.assertEqual(len(raw), EXPECTED_PERSONA_BINDINGS[0][1])
        self.assertEqual(
            fact_graph.fact_graph_sha256("p01", value),
            EXPECTED_PERSONA_BINDINGS[0][2],
        )
        self.assertTrue(fact_graph.validate_fact_graph("p01", value))

    def test_twenty_persona_four_graph_inventory_and_exact_digests(self):
        self.assertEqual(
            [value["persona_id"] for value in self.values],
            list(envelope.PERSONA_IDS),
        )
        actual_bindings = []
        project_ids = []
        suite_counts = {
            "conflict_set_count": 0,
            "edge_count": 0,
            "entity_count": 0,
            "fact_count": 0,
            "graph_count": 0,
            "revision_chain_count": 0,
        }
        for value in self.values:
            raw = fact_graph.canonical_json_bytes(value)
            actual_bindings.append(
                (value["persona_id"], len(raw), hashlib.sha256(raw).hexdigest())
            )
            self.assertLessEqual(len(raw), fact_graph.MAX_FACT_GRAPH_BYTES)
            self.assertEqual(value["summary"], {
                "conflict_set_count": 4,
                "edge_count": 4,
                "entity_count": 16,
                "fact_count": 36,
                "graph_count": 4,
                "revision_chain_count": 4,
            })
            for key in suite_counts:
                suite_counts[key] += value["summary"][key]
            project_ids.extend(graph["project_or_case_id"] for graph in value["graphs"])
        self.assertEqual(tuple(actual_bindings), EXPECTED_PERSONA_BINDINGS)
        self.assertEqual(sum(row[1] for row in actual_bindings), EXPECTED_SUITE_CANONICAL_BYTES)
        self.assertEqual(suite_counts, {
            "conflict_set_count": 80,
            "edge_count": 80,
            "entity_count": 320,
            "fact_count": 720,
            "graph_count": 80,
            "revision_chain_count": 80,
        })
        self.assertEqual(len(project_ids), len(set(project_ids)))
        self.assertEqual(project_ids[0], "release-syn-001")
        self.assertEqual(project_ids[-1], "fact-check-syn-080")

        summary = {
            "artifact_schema": fact_graph.ARTIFACT_SCHEMA,
            "fixture_id": envelope.FIXTURE_ID,
            "persona_count": len(actual_bindings),
            "personas": [
                {"canonical_bytes": byte_count, "persona_id": persona_id, "sha256": digest}
                for persona_id, byte_count, digest in actual_bindings
            ],
            "suite_canonical_bytes": EXPECTED_SUITE_CANONICAL_BYTES,
        }
        summary_raw = artifact_common.canonical_json_bytes(
            summary,
            label="fact graph suite summary",
            max_bytes=64 * 1024,
        )
        self.assertEqual(len(summary_raw), EXPECTED_SUITE_SUMMARY_BYTES)
        self.assertEqual(
            hashlib.sha256(summary_raw).hexdigest(),
            EXPECTED_SUITE_SUMMARY_SHA256,
        )

    def test_typed_values_synthetic_identifiers_and_revision_semantics(self):
        synthetic_id = re.compile(r"^[a-z][a-z0-9-]*-syn-[0-9]{3}$")
        checkpoint_order = [row[0] for row in data.CHECKPOINT_ROWS]
        suite_namespace_ids = {
            "predicate": set(),
            "graph": set(),
            "entity": set(),
            "fact": set(),
            "edge": set(),
            "revision": set(),
            "conflict_set": set(),
        }
        for value in self.values:
            artifact_common.validate_plain_value(value, label="fact graph test value")
            self.assertEqual(
                value["logical_time_contract"]["reference_instant_utc"],
                "2026-07-13T00:00:00Z",
            )
            predicate_kind = {
                row["predicate_id"]: row["value_kind"]
                for row in value["predicate_catalog"]
            }
            suite_namespace_ids["predicate"].update(predicate_kind)
            for graph in value["graphs"]:
                suite_namespace_ids["graph"].add(graph["graph_id"])
                suite_namespace_ids["entity"].update(
                    row["entity_id"] for row in graph["entities"]
                )
                suite_namespace_ids["fact"].update(
                    row["fact_id"] for row in graph["facts"]
                )
                suite_namespace_ids["edge"].update(
                    row["edge_id"] for row in graph["fact_edges"]
                )
                suite_namespace_ids["revision"].update(
                    row["revision_chain_id"] for row in graph["revision_chains"]
                )
                suite_namespace_ids["conflict_set"].update(
                    row["conflict_set_id"] for row in graph["conflict_sets"]
                )
                by_fact_id = {row["fact_id"]: row for row in graph["facts"]}
                chain = graph["revision_chains"][0]
                old = by_fact_id[chain["prior_fact_ids"][0]]
                new = by_fact_id[chain["current_fact_id"]]
                self.assertEqual(old["predicate_id"], new["predicate_id"])
                self.assertEqual(old["subject_entity_id"], new["subject_entity_id"])
                self.assertNotEqual(old["typed_value"], new["typed_value"])
                self.assertEqual(
                    [row["state"] for row in old["visibility_by_checkpoint"]],
                    ["current"] + ["history-only"] * 6,
                )
                self.assertEqual(
                    [row["state"] for row in new["visibility_by_checkpoint"]],
                    ["absent"] + ["current"] * 6,
                )
                for fact in graph["facts"]:
                    self.assertEqual(
                        [row["checkpoint"] for row in fact["visibility_by_checkpoint"]],
                        checkpoint_order,
                    )
                    typed = fact["typed_value"]
                    self.assertEqual(typed["kind"], predicate_kind[fact["predicate_id"]])
                    if typed["kind"] == "email":
                        self.assertTrue(typed["value"].endswith(".invalid"))
                    if typed["kind"] == "documentation-ip":
                        self.assertIn(
                            ipaddress.ip_address(typed["value"]),
                            ipaddress.ip_network("192.0.2.0/24"),
                        )

                conflict_set = graph["conflict_sets"][0]
                self.assertEqual(
                    conflict_set["member_fact_ids"],
                    sorted(conflict_set["member_fact_ids"]),
                )
                self.assertEqual(
                    conflict_set["required_current_checkpoint"], "W0"
                )
                left, right = (
                    by_fact_id[fact_id]
                    for fact_id in conflict_set["member_fact_ids"]
                )
                self.assertEqual(left["predicate_id"], right["predicate_id"])
                self.assertEqual(
                    left["subject_entity_id"], right["subject_entity_id"]
                )
                self.assertNotEqual(left["typed_value"], right["typed_value"])
                for fact in (left, right):
                    states = {
                        row["checkpoint"]: row["state"]
                        for row in fact["visibility_by_checkpoint"]
                    }
                    self.assertEqual(states["W0"], "current")
                revision_members = set(chain["prior_fact_ids"]) | {
                    chain["current_fact_id"]
                }
                self.assertFalse(
                    revision_members & set(conflict_set["member_fact_ids"])
                )

        for identifiers in suite_namespace_ids.values():
            for identifier in identifiers:
                self.assertIsNotNone(synthetic_id.fullmatch(identifier), identifier)
        self.assertEqual(
            {name: len(identifiers) for name, identifiers in suite_namespace_ids.items()},
            {
                "predicate": 7,
                "graph": 80,
                "entity": 320,
                "fact": 720,
                "edge": 80,
                "revision": 80,
                "conflict_set": 80,
            },
        )
        namespace_names = tuple(suite_namespace_ids)
        for index, left_name in enumerate(namespace_names):
            for right_name in namespace_names[index + 1:]:
                self.assertFalse(
                    suite_namespace_ids[left_name] & suite_namespace_ids[right_name],
                    f"{left_name}/{right_name}",
                )

    def test_graphs_exclude_membership_surface_identity_and_output_fields(self):
        forbidden = {
            "absolute_path", "answer_key", "chunk_id", "distractor_key",
            "intent_key", "materialization_id", "query_key", "query_text",
            "rank", "raw_sha256", "relative_path", "rendered_text", "score",
            "source_id",
        }

        def visit(node):
            if type(node) is list:
                for item in node:
                    visit(item)
                return
            if type(node) is not dict:
                return
            self.assertFalse(set(node) & forbidden)
            for item in node.values():
                visit(item)

        for value in self.values:
            visit(value["graphs"])
            self.assertNotIn("/", repr(value["graphs"]))
            self.assertNotIn("\\", repr(value["graphs"]))

    def test_tamper_strict_types_persona_binding_and_detachment_fail_closed(self):
        original = self.values[0]
        cases = []
        changed_fact = copy.deepcopy(original)
        changed_fact["graphs"][0]["facts"][5]["typed_value"]["value"] += 1
        cases.append(changed_fact)
        changed_binding = copy.deepcopy(original)
        changed_binding["input_bindings"][-1]["sha256"] = "0" * 64
        cases.append(changed_binding)
        changed_revision = copy.deepcopy(original)
        changed_revision["graphs"][0]["revision_chains"][0]["current_fact_id"] = (
            changed_revision["graphs"][0]["facts"][0]["fact_id"]
        )
        cases.append(changed_revision)
        for replacement in (True, 1.0, None, "e\u0301", "\ud800"):
            changed_type = copy.deepcopy(original)
            changed_type["graphs"][0]["facts"][5]["typed_value"]["value"] = replacement
            cases.append(changed_type)
        for value in cases:
            with self.subTest(value=repr(value)[-80:]):
                with self.assertRaises(fact_graph.PersonaV2FactGraphError):
                    fact_graph.validate_fact_graph("p01", value)

        detached = fact_graph.build_fact_graph_suite()
        detached[0]["graphs"][0]["facts"][0]["typed_value"]["entity_id"] = "poisoned"
        self.assertNotEqual(
            detached[1]["graphs"][0]["facts"][0]["typed_value"]["entity_id"],
            "poisoned",
        )
        for invalid in (True, 1, "p21"):
            with self.assertRaises(fact_graph.PersonaV2FactGraphError):
                fact_graph.build_fact_graph(invalid)
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph.require_fact_oracle_input_closure()

    def test_independent_builder_guards_revision_and_namespace_drift(self):
        graph = copy.deepcopy(self.values[0]["graphs"][0])
        old_id = graph["revision_chains"][0]["prior_fact_ids"][0]
        new_id = graph["revision_chains"][0]["current_fact_id"]
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[new_id]["subject_entity_id"] = graph["entities"][1]["entity_id"]
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[old_id]["visibility_by_checkpoint"][2]["state"] = "current"
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        members = graph["conflict_sets"][0]["member_fact_ids"]
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[members[1]]["typed_value"] = copy.deepcopy(
            by_id[members[0]]["typed_value"]
        )
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        graph["conflict_sets"][0]["member_fact_ids"].reverse()
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        members = graph["conflict_sets"][0]["member_fact_ids"]
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[members[1]]["subject_entity_id"] = graph["entities"][1]["entity_id"]
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        members = graph["conflict_sets"][0]["member_fact_ids"]
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[members[1]]["visibility_by_checkpoint"][0]["state"] = "absent"
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        revision_member = graph["revision_chains"][0]["prior_fact_ids"][0]
        graph["conflict_sets"][0]["member_fact_ids"][0] = revision_member
        graph["conflict_sets"][0]["member_fact_ids"].sort()
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        for replacement in ([], graph["conflict_sets"] * 2):
            changed = copy.deepcopy(self.values[0]["graphs"][0])
            changed["conflict_sets"] = copy.deepcopy(replacement)
            with self.assertRaises(fact_graph.PersonaV2FactGraphError):
                fact_graph._validate_graph(changed)

        graph = copy.deepcopy(self.values[0]["graphs"][0])
        by_id = {row["fact_id"]: row for row in graph["facts"]}
        by_id[old_id]["visibility_by_checkpoint"][1]["state"] = "current"
        by_id[new_id]["visibility_by_checkpoint"][1]["state"] = "absent"
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_graph(graph)

        predicate_catalog = copy.deepcopy(self.values[0]["predicate_catalog"])
        predicate_catalog[0]["predicate_id"] = self.values[0]["graphs"][0]["entities"][1]["entity_id"]
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_identifier_namespaces(
                predicate_catalog,
                self.values[0]["graphs"],
            )


if __name__ == "__main__":
    unittest.main()
