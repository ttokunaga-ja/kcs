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
    ("p01", 26_403, "2a17d26201ba45a1b7b3a5d42dbedf5b4cbae5a1f379e8213c5e3a6dcc23df65"),
    ("p02", 26_353, "8d7ef439aed58689dc873841dda12d17146d8646c90d9556578fedb423d7c8aa"),
    ("p03", 26_479, "527241e5864f47824f946910c7e0767867936326c0c67770bff5c500d3d52cdb"),
    ("p04", 26_569, "f02368bc0e29c631d68e73bb60dc0ddca101222198afdd63a13cf7c534c2d9ef"),
    ("p05", 26_536, "361d944568a68f3d473ff39c03ea5f505642ae028ad12dc111ce623b772cdb3a"),
    ("p06", 26_522, "843aa6c73d977f4e7a945e1f4fe676d9075925025bb0a7af1dfa70c4b672782d"),
    ("p07", 26_672, "ae37f7e554b65bf9c7585939380ae3895f671febbb18476be5f12243700cc447"),
    ("p08", 26_506, "32bae5c07b44e7b1252336543fe2bb82ce97d35ac0bc2f86bd2e7166fd0e2094"),
    ("p09", 26_544, "8d8971744bf6fbac7c0767243ba5cd9e1f51ddf5d52de29b1a2fe63a2fa94942"),
    ("p10", 26_497, "f2cb61e8ad2ad4378b277d00e807097a3fdb8243a7bb7642b24f563bb6072457"),
    ("p11", 26_428, "33dd344e33a1388c2531fb79b125b6558879c7e95a8e2ea546625b82189f0bb4"),
    ("p12", 26_518, "a2bc87ee8e32000f596ed7bd5e82edf6e7f5b01d3d24159cc759d2d4fd861b07"),
    ("p13", 26_487, "d71117236a333b56033bcb902cd257ebe765f84fa3322ac4851f04c9aaaaf359"),
    ("p14", 26_426, "187695085ab888ed56c421d2d5d9a10816ad25e333745146a3409235937ca1f5"),
    ("p15", 26_535, "f8f534aed03a97e14f7f4633adf590819f92f0926a9abd59e025a4337054f362"),
    ("p16", 26_577, "a4425ecd87232455a3db0bd77b7a9ee2917ea05d5742014d80f281dd19562064"),
    ("p17", 26_483, "743c2fd1aacf8228315f4e4b2272d41493d580c1526c24ec70a8a837150bd9f7"),
    ("p18", 26_485, "197d85105b0f0928787347f29babcf25c5173034897d9e7761c73c92abc26a2e"),
    ("p19", 26_442, "763dacdb0ee888088bdec4b3bda5ef598ba8fe19989d41e74c3f4b3bf1d912b8"),
    ("p20", 26_546, "70012f4de6c82cbb6220940a27000009344236e3bb5742e9975d5ea904d08db9"),
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
