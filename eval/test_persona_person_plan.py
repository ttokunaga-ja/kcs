import copy
import hashlib
from pathlib import PurePosixPath
import unittest
from unittest import mock

from eval import generate_persona_corpus as generator
from eval import persona_fixture_spec as spec
from eval import persona_manifest as canonical_manifest


class PersonaGenerationPlanTests(unittest.TestCase):
    def test_persona_value_is_the_exact_existing_suite_projection(self):
        suite = generator.build_generation_plan("tiny")
        suite_people = {
            person["persona_id"]: person for person in suite["personas"]
        }
        self.assertEqual(len(suite_people), 20)
        for persona in spec.PERSONAS:
            persona_id = persona["id"]
            wrapper = generator.build_persona_generation_plan(
                "tiny", persona_id
            )
            self.assertEqual(wrapper["persona"], suite_people[persona_id])
            self.assertEqual(
                canonical_manifest.canonical_json_bytes(wrapper["persona"]),
                canonical_manifest.canonical_json_bytes(
                    suite_people[persona_id]
                ),
            )

    def test_wrapper_binds_fixture_profile_persona_and_relative_paths(self):
        for profile in ("tiny", "pilot", "full"):
            plan = generator.build_persona_generation_plan(profile, "p12")
            self.assertEqual(
                plan["schema"], generator.PERSONA_GENERATION_PLAN_SCHEMA
            )
            self.assertEqual(plan["fixture_id"], spec.FIXTURE_ID)
            self.assertEqual(plan["profile"], profile)
            self.assertEqual(plan["persona_id"], "p12")
            self.assertEqual(plan["persona"]["persona_id"], "p12")
            self.assertEqual(
                plan["contracts"],
                {
                    "root_independent": True,
                    "contains_absolute_paths": False,
                    "contains_rendered_source_bytes": False,
                    "source_expansion": "canonical_w0",
                },
            )
            scopes = plan["persona"]["scopes"]
            self.assertEqual(len(scopes), 20)
            self.assertTrue(
                all(
                    not PurePosixPath(scope["relative_path"]).is_absolute()
                    for scope in scopes
                )
            )
            source_count = sum(len(scope["sources"]) for scope in scopes)
            self.assertEqual(
                source_count, plan["persona"]["raw_file_count"]
            )
            self.assertLessEqual(
                source_count, generator.MAX_PERSONA_PLAN_SOURCES
            )
            self.assertLessEqual(
                len(generator.canonical_file_bytes(plan)),
                generator.MAX_PERSONA_PLAN_BYTES,
            )
            self.assertIs(
                generator.validate_persona_generation_plan(
                    plan,
                    expected_profile=profile,
                    expected_persona_id="p12",
                ),
                plan,
            )

    def test_event_projection_is_exact_validated_and_detached(self):
        plan = generator.build_persona_generation_plan("tiny", "p01")
        projected = generator.persona_event_plan_projection(
            plan,
            expected_profile="tiny",
            expected_persona_id="p01",
        )
        self.assertEqual(
            projected,
            {
                "persona_id": plan["persona"]["persona_id"],
                "planned_contract_chunks": plan["persona"][
                    "planned_contract_chunks"
                ],
                "scopes": plan["persona"]["scopes"],
            },
        )
        projected["scopes"][0]["sources"][0]["version"] = 99
        self.assertEqual(
            plan["persona"]["scopes"][0]["sources"][0]["version"], 0
        )

    def test_all_twenty_full_plans_are_processed_sequentially(self):
        source_total = 0
        largest_sources = 0
        largest_bytes = 0
        inventory_digest = hashlib.sha256()

        # The bounded path must neither construct the all-person plan nor
        # render source bytes/source_entries.  Each wrapper is released before
        # the next persona is built.
        with (
            mock.patch.object(
                generator,
                "_build_generation_plan",
                side_effect=AssertionError("all-person builder was called"),
            ),
            mock.patch.object(
                generator,
                "materialize_source",
                side_effect=AssertionError("source bytes were rendered"),
            ),
        ):
            for persona in spec.PERSONAS:
                persona_id = persona["id"]
                plan = generator.build_persona_generation_plan(
                    "full", persona_id
                )
                generator.validate_persona_generation_plan(
                    plan,
                    expected_profile="full",
                    expected_persona_id=persona_id,
                )
                raw = generator.canonical_file_bytes(plan)
                count = plan["persona"]["raw_file_count"]
                self.assertEqual(len(plan["persona"]["scopes"]), 20)
                self.assertLessEqual(
                    count, generator.MAX_PERSONA_PLAN_SOURCES
                )
                self.assertLessEqual(
                    len(raw), generator.MAX_PERSONA_PLAN_BYTES
                )
                source_total += count
                largest_sources = max(largest_sources, count)
                largest_bytes = max(largest_bytes, len(raw))
                inventory_digest.update(hashlib.sha256(raw).digest())
                del raw
                del plan

        self.assertEqual(source_total, 195_000)
        self.assertEqual(largest_sources, 16_000)
        self.assertGreater(largest_bytes, 4_000_000)
        self.assertNotEqual(inventory_digest.digest(), bytes(32))

    def test_validation_rejects_semantic_and_type_tampering(self):
        original = generator.build_persona_generation_plan("tiny", "p01")

        def changed(mutator):
            value = copy.deepcopy(original)
            mutator(value)
            return value

        cases = [
            changed(lambda value: value.__setitem__("schema", "wrong")),
            changed(lambda value: value.__setitem__("fixture_id", "wrong")),
            changed(lambda value: value.__setitem__("profile", "pilot")),
            changed(lambda value: value.__setitem__("persona_id", "p02")),
            changed(
                lambda value: value["persona"].__setitem__(
                    "persona_id", "p02"
                )
            ),
            changed(
                lambda value: value["contracts"].__setitem__(
                    "root_independent", False
                )
            ),
            changed(
                lambda value: value["persona"]["scopes"][0].__setitem__(
                    "relative_path", "/tmp/foreign-root"
                )
            ),
            changed(
                lambda value: value["persona"]["scopes"][0]["sources"][
                    0
                ].__setitem__("requested_contributor_chunks", 72)
            ),
            changed(lambda value: value.__setitem__("schema_version", True)),
            changed(lambda value: value.__setitem__("root", "/tmp/root")),
        ]

        missing_scope = changed(
            lambda value: value["persona"]["scopes"].pop()
        )
        cases.append(missing_scope)

        coherent_extra_source = copy.deepcopy(original)
        coherent_extra_source["persona"]["scopes"][0]["sources"].append(
            copy.deepcopy(
                coherent_extra_source["persona"]["scopes"][0]["sources"][0]
            )
        )
        coherent_extra_source["persona"]["raw_file_count"] += 1
        cases.append(coherent_extra_source)

        for ordinal, case in enumerate(cases):
            with self.subTest(case=ordinal):
                with self.assertRaises(generator.PersonaGenerationError):
                    generator.validate_persona_generation_plan(case)

    def test_expected_identity_rejects_canonical_shard_substitution(self):
        p02 = generator.build_persona_generation_plan("tiny", "p02")
        generator.validate_persona_generation_plan(p02)
        with self.assertRaisesRegex(
            generator.PersonaGenerationError, "expected persona"
        ):
            generator.validate_persona_generation_plan(
                p02, expected_profile="tiny", expected_persona_id="p01"
            )
        with self.assertRaisesRegex(
            generator.PersonaGenerationError, "expected profile"
        ):
            generator.validate_persona_generation_plan(
                p02, expected_profile="full", expected_persona_id="p02"
            )

    def test_source_and_canonical_byte_limits_fail_closed(self):
        plan = generator.build_persona_generation_plan("full", "p12")
        source_count = plan["persona"]["raw_file_count"]
        byte_count = len(generator.canonical_file_bytes(plan))

        with mock.patch.object(
            generator, "MAX_PERSONA_PLAN_SOURCES", source_count - 1
        ):
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "source bound"
            ):
                generator.validate_persona_generation_plan(plan)
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "source bound"
            ):
                generator.build_persona_generation_plan("full", "p12")

        with mock.patch.object(
            generator, "MAX_PERSONA_PLAN_BYTES", byte_count - 1
        ):
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "canonical-byte bound"
            ):
                generator.validate_persona_generation_plan(plan)
            with self.assertRaisesRegex(
                generator.PersonaGenerationError, "canonical-byte bound"
            ):
                generator.build_persona_generation_plan("full", "p12")

    def test_unknown_or_non_string_identity_is_rejected(self):
        for profile, persona_id in (
            ("unknown", "p01"),
            (True, "p01"),
            ("tiny", "p99"),
            ("tiny", True),
        ):
            with self.subTest(profile=profile, persona_id=persona_id):
                with self.assertRaises(generator.PersonaGenerationError):
                    generator.build_persona_generation_plan(
                        profile, persona_id
                    )


if __name__ == "__main__":
    unittest.main()
