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
    ("p01", 23_741, "e7e0cd34834f375939406ddf4ff4069423d6350eedb1e902f84d1f0e8c6e0898"),
    ("p02", 23_696, "d90a7daad5be77053dea21d736994beb171916e53469fa6d2235c1a4b7e2acaa"),
    ("p03", 23_810, "8e0b53c5aa4a066e240075aad239dee6100ce7617069048007e5d93faff02dd2"),
    ("p04", 23_892, "a7a50c9d29a583ff791e1328aba85e5d090a8d9e3553cf83df2533187a3aee8e"),
    ("p05", 23_862, "d6ee7f454e96253c34b33022639387b3f69f9fa239f5148499272ffb847800ba"),
    ("p06", 23_850, "987aac5c9d653eae04faf712ebec3db4c463f4e2a0d24d7dc1882179ca94a901"),
    ("p07", 23_986, "a615e10c2f83a9e54928feaeefd40fe125fcd25ab66fb8384422fac92d5bb5bb"),
    ("p08", 23_835, "0b3087d4502710c2fe62708c46432c0f1e25f379f2b6fdcaf09ad8f7f2b6a528"),
    ("p09", 23_869, "d971fc356b4ab092db8bbf987983ea780204eec818c9bfc20ce4c34ddb573b09"),
    ("p10", 23_827, "566183211cc2fc4545e80f19b091f13f06393a3bb78927486c1faa0a6b96830b"),
    ("p11", 23_765, "943c1d68bac64c7475555d3f9698db7f66b0d1ea6e6649358196eb65949bbc33"),
    ("p12", 23_846, "c3fefd618aba43fcbdff06fddeea6485c73a82ae6301743fd0bfbb1517e80d53"),
    ("p13", 23_818, "a13dc4b0a496502c255cec9f2d1b1099a979f06d322a20a320beff54b5b50396"),
    ("p14", 23_763, "e522ab8596b1edc58831d62e2735f6f3655003d88155e7138935b1c5bd02511e"),
    ("p15", 23_861, "e7e43f8f2a547e18d6f416f92e6bba1da0dce858239317c5d6b5b6376646e052"),
    ("p16", 23_899, "43bac5d71ea6d1a35089d07bb6fa19ec5270fc916e91060ce1776b3f5f18cf61"),
    ("p17", 23_815, "b3ebae797bbd17e49ff62162bc3bb613a9486b9bad16bd8e6097c41b07529d62"),
    ("p18", 23_817, "dd6df0fa2b76916df6873ab433bb50ba4b008d65755dd73b99b0c10d09b1093a"),
    ("p19", 23_779, "bf23fed3a0f440db8d49fff8468bba2d60810aedaeac2467d29dd8208770dd28"),
    ("p20", 23_871, "4c923c6a96e2b821304d98698bea8dbd9c6abec8b07be6dbad0acc960d06f2db"),
)
EXPECTED_SUITE_CANONICAL_BYTES = 476_602
EXPECTED_SUITE_SUMMARY_BYTES = 2_566
EXPECTED_SUITE_SUMMARY_SHA256 = (
    "28e9273c3c69b8982ea0ec5553865ed99ace0845ff28295af3c969169ee7b0f7"
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
                    ["current", "current"] + ["history-only"] * 5,
                )
                self.assertEqual(
                    [row["state"] for row in new["visibility_by_checkpoint"]],
                    ["absent", "absent"] + ["current"] * 5,
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

        predicate_catalog = copy.deepcopy(self.values[0]["predicate_catalog"])
        predicate_catalog[0]["predicate_id"] = self.values[0]["graphs"][0]["entities"][1]["entity_id"]
        with self.assertRaises(fact_graph.PersonaV2FactGraphError):
            fact_graph._validate_identifier_namespaces(
                predicate_catalog,
                self.values[0]["graphs"],
            )


if __name__ == "__main__":
    unittest.main()
