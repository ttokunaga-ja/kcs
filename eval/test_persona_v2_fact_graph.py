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
    ("p01", 23_765, "59679aa5e52f1f9db9e9e5ede1066e68cba1b3ff6c4d2c6dd9f9df47c56ee36d"),
    ("p02", 23_720, "62eb9b71f9f3a35afb5da00eee67406123d2eb7707b966c447df64bb2ae2a27f"),
    ("p03", 23_834, "b6f87f235f87d449c8d4660086d79edb47572ed9c54a8f3c97e7eeaa6d7f7a61"),
    ("p04", 23_916, "96c332ec293085f1594f56f55e7a9b4b340f39392ec4a0d38b53dd2d1edc3192"),
    ("p05", 23_886, "be6d50dd17ca38555504b7a0fc3b854e48cb1b80da21498a5aca9f9595785f53"),
    ("p06", 23_874, "30db27b0cbff11701054f7bec194e5d00e6d5ca3484fffcf34c5841dee84b6e0"),
    ("p07", 24_010, "f447204c98c6c5fb4fe0f95b80fb033f9878654b94df19b0e4aab162d3916abb"),
    ("p08", 23_859, "1cd082aa37959990361e7b5b3a13af17fb27e9d2532f086e9f5c3518fd9fe66e"),
    ("p09", 23_893, "ba51f5ba4080604c82b3e59f9aba640a8edbd4aed4d136708aeac38346abb8f3"),
    ("p10", 23_851, "e2b1b8cf2cbf69c14dd0df665ea9c90170dad7bd0a7f59e6f5ccaf9d113780b0"),
    ("p11", 23_789, "93131519cfd58bea8a5b59758fdb568aba9b8f26a306f65b8221d81b4a2c79c9"),
    ("p12", 23_870, "410f550b51d4eff69add866328a5ce5e4b13c2fd6d445b4fb6b36e375084d585"),
    ("p13", 23_842, "2f16696b56390490ab4e02e0cff3f20f0ec54159ad83fd7a5c5d2f2f5efb4d47"),
    ("p14", 23_787, "014281d9430db1484f9a7040684c21c49c111da9db96bc44639a5038c8e4ab77"),
    ("p15", 23_885, "5a7ce55ea697304f9fda019f7d8d0e58e543b0b1e7b0bb9987d50e07cf55134a"),
    ("p16", 23_923, "190e5902b1d3f60039ec0a89dc87c7e8c6bb7efca816612b8c21f45a9fddff6e"),
    ("p17", 23_839, "b77beb7fd6cb6ff64275b35e9425ff08ee5d1a9c7ef75bb7cd69416b60fae6ad"),
    ("p18", 23_841, "4893c3ed0e5aa5281f566cc7063fd2b1a3a7b2f34fbabf6f0c7cb55f6a26ec0a"),
    ("p19", 23_803, "38201bd5a1bab363abe9c7503e2da07abd585b0ccb73aa4a280b89e2cf40f793"),
    ("p20", 23_895, "684712c3e78d974272d3cbb81265a63bcc830375ce924367bf7c2c6727eff4a3"),
)
EXPECTED_SUITE_CANONICAL_BYTES = 477_082
EXPECTED_SUITE_SUMMARY_BYTES = 2_566
EXPECTED_SUITE_SUMMARY_SHA256 = (
    "edf6dad5a7dc1057384f8c47a866fd86eaddd3823ade10aa4d24c86db42a6def"
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
                "kcs_execution_available",
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
                "edge_count": 4,
                "entity_count": 16,
                "fact_count": 32,
                "graph_count": 4,
                "revision_chain_count": 4,
            })
            for key in suite_counts:
                suite_counts[key] += value["summary"][key]
            project_ids.extend(graph["project_or_case_id"] for graph in value["graphs"])
        self.assertEqual(tuple(actual_bindings), EXPECTED_PERSONA_BINDINGS)
        self.assertEqual(sum(row[1] for row in actual_bindings), EXPECTED_SUITE_CANONICAL_BYTES)
        self.assertEqual(suite_counts, {
            "edge_count": 80,
            "entity_count": 320,
            "fact_count": 640,
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

        for identifiers in suite_namespace_ids.values():
            for identifier in identifiers:
                self.assertIsNotNone(synthetic_id.fullmatch(identifier), identifier)
        self.assertEqual(
            {name: len(identifiers) for name, identifiers in suite_namespace_ids.items()},
            {
                "predicate": 7,
                "graph": 80,
                "entity": 320,
                "fact": 640,
                "edge": 80,
                "revision": 80,
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
