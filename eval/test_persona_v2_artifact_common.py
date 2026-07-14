import copy
import hashlib
import json
import unittest

from eval import persona_v2_artifact_common as common
from eval import persona_v2_contract as envelope
from eval import persona_v2_input_bindings as bindings
from eval import persona_v2_joint_problem as joint_problem


class _DictSubclass(dict):
    pass


class _ListSubclass(list):
    pass


class PersonaV2ArtifactCommonTests(unittest.TestCase):
    def test_strict_canonical_json_and_exact_regeneration(self):
        expected = {"a": [1, True, "é"], "z": 2}

        def builder():
            return copy.deepcopy(expected)

        raw = common.canonical_json_bytes(
            {"z": 2, "a": [1, True, "é"]},
            label="test artifact",
            max_bytes=1_024,
        )
        self.assertEqual(raw, '{"a":[1,true,"é"],"z":2}'.encode())
        self.assertTrue(
            common.validate_exact_regeneration(
                expected,
                builder=builder,
                label="test artifact",
                max_bytes=1_024,
            )
        )
        self.assertEqual(
            common.canonical_sha256(
                expected,
                builder=builder,
                label="test artifact",
                max_bytes=1_024,
            ),
            hashlib.sha256(raw).hexdigest(),
        )
        tampered = copy.deepcopy(expected)
        tampered["z"] = 3
        with self.assertRaises(common.PersonaV2ArtifactError):
            common.validate_exact_regeneration(
                tampered,
                builder=builder,
                label="test artifact",
                max_bytes=1_024,
            )

    def test_plain_value_rejects_python_aliases_unicode_depth_and_caps(self):
        invalid_values = (
            None,
            1.0,
            -1,
            2**127,
            (1,),
            _ListSubclass([1]),
            _DictSubclass({"a": 1}),
            {1: "value"},
            {"bad": "e\u0301"},
            {"bad": "\ud800"},
            {"\ud800": "bad-key"},
            {"bad": b"bytes"},
        )
        for value in invalid_values:
            with self.subTest(value=repr(value)):
                with self.assertRaises(common.PersonaV2ArtifactError):
                    common.validate_plain_value(value, label="test artifact")

        nested = 0
        for _ in range(66):
            nested = [nested]
        with self.assertRaises(common.PersonaV2ArtifactError):
            common.validate_plain_value(nested, label="test artifact")
        with self.assertRaises(common.PersonaV2ArtifactError):
            common.validate_plain_value(
                "x" * (common.MAX_CANONICAL_STRING_BYTES + 1),
                label="test artifact",
            )
        with self.assertRaises(common.PersonaV2ArtifactError):
            common.canonical_json_bytes(
                {"a": "x" * 128},
                label="test artifact",
                max_bytes=16,
            )

    def test_global_boundaries_are_inclusive_and_cannot_be_loosened(self):
        common.validate_plain_value(
            common.MAX_INTEGER_MAGNITUDE,
            label="test artifact",
        )
        common.validate_plain_value(
            "x" * common.MAX_CANONICAL_STRING_BYTES,
            label="test artifact",
        )
        nested = 0
        for _ in range(common.MAX_CANONICAL_DEPTH):
            nested = [nested]
        common.validate_plain_value(nested, label="test artifact")

        for kwargs in (
            {"max_depth": common.MAX_CANONICAL_DEPTH + 1},
            {"max_string_bytes": common.MAX_CANONICAL_STRING_BYTES + 1},
            {"max_integer": common.MAX_INTEGER_MAGNITUDE + 1},
            {"max_depth": True},
            {"max_string_bytes": 1.0},
            {"max_integer": False},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(common.PersonaV2ArtifactError):
                    common.validate_plain_value(0, label="test artifact", **kwargs)

        exact = common.canonical_json_bytes(
            {"a": "é" * 8},
            label="test artifact",
            max_bytes=1_024,
        )
        self.assertEqual(
            common.canonical_json_bytes(
                {"a": "é" * 8},
                label="test artifact",
                max_bytes=len(exact),
            ),
            exact,
        )
        with self.assertRaises(common.PersonaV2ArtifactError):
            common.canonical_json_bytes(
                {"a": "é" * 8},
                label="test artifact",
                max_bytes=len(exact) - 1,
            )

    def test_upstream_bindings_are_exact_non_authorizing_and_detached(self):
        expected = [
            (
                "envelope",
                70_835,
                "6b5c7145881f2ab1e8c84fe033f667757dccf478b704e0731d543bfddfcddbac",
            ),
            (
                "topology",
                134_141,
                "fc079fc8e0aaee0ae03a22fee349e0af8f2dfe18e1fed6d8bb05304643e4a958",
            ),
            (
                "joint-problem",
                744_081,
                "384c95f550355b63443d7f5ca94dad2ed008ab7b24d6b8148a9504f613c29227",
            ),
            (
                "joint-solver-policy",
                82_950,
                "29046b5b5d60d25db51a670e597617bec07b7c4513bded39196bb1053ee52f41",
            ),
        ]
        first = bindings.build_upstream_bindings()
        self.assertEqual(
            [(row["name"], row["canonical_bytes"], row["sha256"]) for row in first],
            expected,
        )
        for row in first:
            self.assertEqual(row["fixture_id"], envelope.FIXTURE_ID)
            self.assertEqual(
                row["fixture_schema_version"],
                envelope.FIXTURE_SCHEMA_VERSION,
            )
        first[0]["sha256"] = "0" * 64
        self.assertEqual(bindings.build_upstream_bindings()[0]["sha256"], expected[0][2])
        with self.assertRaises(TypeError):
            bindings.EXPECTED_UPSTREAM_BINDINGS["envelope"] = {}
        with self.assertRaises(TypeError):
            bindings.EXPECTED_UPSTREAM_BINDINGS["envelope"]["sha256"] = "0" * 64
        for name, _, _ in expected:
            self.assertEqual(bindings.get_upstream_binding(name)["name"], name)
        for invalid in (True, 1, "unknown"):
            with self.assertRaises(bindings.PersonaV2InputBindingError):
                bindings.get_upstream_binding(invalid)

    def test_binding_rejects_false_digest_identity_authority_and_back_edges(self):
        base = envelope.build_envelope_contract()

        def canonical(value):
            return envelope.canonical_json_bytes(value)

        def valid_digest(value):
            return hashlib.sha256(canonical(value)).hexdigest()

        self.assertEqual(
            bindings._binding(
                "envelope",
                base,
                validate=lambda value: True,
                canonical=canonical,
                digest=valid_digest,
            )["sha256"],
            valid_digest(base),
        )
        mutations = []
        authority_true = copy.deepcopy(base)
        authority_true["authority"][next(iter(authority_true["authority"]))] = True
        mutations.append(authority_true)
        authority_alias = copy.deepcopy(base)
        authority_alias["authority"][next(iter(authority_alias["authority"]))] = 0
        mutations.append(authority_alias)
        wrong_fixture = copy.deepcopy(base)
        wrong_fixture["fixture_id"] = "kcs-persona-pc-v1"
        mutations.append(wrong_fixture)
        authorizing = copy.deepcopy(base)
        authorizing["g0_contract_frozen"] = True
        mutations.append(authorizing)
        downstream_edge = copy.deepcopy(base)
        downstream_edge["realism_profile_sha256"] = "0" * 64
        mutations.append(downstream_edge)
        nested_downstream_edge = copy.deepcopy(base)
        nested_downstream_edge["profiles"]["full"]["realism_profile_sha256"] = (
            "0" * 64
        )
        mutations.append(nested_downstream_edge)
        for mutation in mutations:
            with self.subTest(keys=sorted(mutation)):
                with self.assertRaises(bindings.PersonaV2InputBindingError):
                    bindings._binding(
                        "envelope",
                        mutation,
                        validate=lambda value: True,
                        canonical=canonical,
                        digest=valid_digest,
                    )
        for false_digest in ("z" * 64, "A" * 64, "0" * 64):
            with self.subTest(false_digest=false_digest[:4]):
                with self.assertRaises(bindings.PersonaV2InputBindingError):
                    bindings._binding(
                        "envelope",
                        base,
                        validate=lambda value: True,
                        canonical=canonical,
                        digest=lambda value, result=false_digest: result,
                    )

        authorizing_problem = joint_problem.build_joint_problem()
        authorizing_problem["proof_status"]["solver_policy_bound"] = True

        def problem_canonical(value):
            return joint_problem.canonical_json_bytes(value)

        with self.assertRaises(bindings.PersonaV2InputBindingError):
            bindings._binding(
                "joint-problem",
                authorizing_problem,
                validate=lambda value: True,
                canonical=problem_canonical,
                digest=lambda value: hashlib.sha256(
                    problem_canonical(value)
                ).hexdigest(),
            )


if __name__ == "__main__":
    unittest.main()
