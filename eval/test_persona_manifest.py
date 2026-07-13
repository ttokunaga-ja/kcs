#!/usr/bin/env python3
"""Focused tests for canonical persona W0 ledgers and publication."""

import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from eval import persona_allocation as allocation
from eval import persona_fixture_spec as spec
from eval import persona_manifest as manifest


PLAN_SHA256 = "a" * 64


def _all_variant_counts():
    return {
        variant: 0
        for variants in spec.FORMAT_VARIANTS.values()
        for variant, _weight, _role, _disposition in variants
    }


def _extension(variant):
    return "pdf" if variant in ("pdf-text", "pdf-scan") else variant


def _unit_kind(variant):
    if variant in ("pdf-text", "pdf-scan"):
        return "page"
    if variant == "png":
        return "image"
    if variant == "wav":
        return "audio"
    if variant == "pcap":
        return "packet"
    if variant == "xlsx":
        return "sheet"
    if variant == "pptx":
        return "slide"
    if variant == "eml":
        return "message"
    return "document"


def _persona_shards(persona_id="p01", profile="tiny"):
    persona = spec.get_persona(persona_id)
    plan = allocation.build_allocation_plan(persona, profile)
    scopes = {scope["scope_key"]: scope for scope in spec.scope_specs(persona)}
    assignments = {scope_key: [] for scope_key in scopes}
    for row in plan["assignments"]:
        assignments[row["scope_key"]].append(row)
    chunk_targets = spec.scope_contributor_chunk_targets(persona, profile)
    counter = 0
    result = []
    for scope_key in sorted(scopes):
        scope = scopes[scope_key]
        physical = []
        metadata = []
        variant_counts = _all_variant_counts()
        for assignment in assignments[scope_key]:
            for _ in range(assignment["count"]):
                counter += 1
                source_id = f"{persona_id}-src-{counter:06d}"
                variant = assignment["variant"]
                extension = _extension(variant)
                file_name = f"source-{counter:06d}.{extension}"
                variant_counts[variant] += 1
                row = {
                    "source_id": source_id,
                    "persona_id": persona_id,
                    "scope_key": scope_key,
                    "relative_path": f"{scope['relative_path']}/{file_name}",
                    "file_name": file_name,
                    "format_family": assignment["family"],
                    "extension": extension,
                    "variant": variant,
                    "media_type": "application/octet-stream",
                    "raw_sha256": hashlib.sha256(
                        f"raw:{source_id}:{variant}".encode()
                    ).hexdigest(),
                    "bytes": 32,
                    "logical_members": 1,
                    "renderer_id": manifest.RENDERER_ID,
                    "renderer_schema_version": manifest.RENDERER_SCHEMA_VERSION,
                    "expected_contract_chunks": 0,
                    "expected_disposition": assignment["expected_disposition"],
                    "gate_role": assignment["gate_role"],
                }
                physical.append(row)
                metadata.append((row, _unit_kind(variant)))
        contributors = [
            row for row, _kind in metadata
            if row["gate_role"] == "contract_contributor"
        ]
        quotient, remainder = divmod(chunk_targets[scope_key], len(contributors))
        for index, row in enumerate(contributors):
            row["expected_contract_chunks"] = quotient + (index < remainder)
        logical = []
        searchable = []
        for row, kind in metadata:
            unit_key = f"{row['source_id']}:unit-000000"
            planned = row["expected_contract_chunks"]
            logical.append({
                "source_id": row["source_id"],
                "persona_id": persona_id,
                "scope_key": scope_key,
                "unit_index": 0,
                "unit_kind": kind,
                "unit_key": unit_key,
                "parent_unit_key": None,
                "planned_contract_chunks": planned,
            })
            searchable.append({
                "source_id": row["source_id"],
                "persona_id": persona_id,
                "scope_key": scope_key,
                "gate_role": row["gate_role"],
                "expected_disposition": row["expected_disposition"],
                "planned_contract_chunks": planned,
                "planned_unit_keys": [unit_key] if planned else [],
                "actual_chunk_policy": manifest.ACTUAL_CHUNK_POLICY_BY_ROLE[
                    row["gate_role"]
                ],
            })
        built, validated = manifest.build_w0_scope_manifest(
            reversed(physical), reversed(logical), reversed(searchable),
            fixture_id=spec.FIXTURE_ID,
            profile=profile,
            persona_id=persona_id,
            scope_key=scope_key,
            plan_sha256=PLAN_SHA256,
            expected_contract_chunks=chunk_targets[scope_key],
            expected_physical_rows=spec.scope_file_counts(persona, profile)[scope_key],
            expected_variant_counts=variant_counts,
        )
        result.append((built, validated))
    return result


class TestPersonaManifest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p01_shards = _persona_shards()

    def first(self):
        built, validated = self.p01_shards[0]
        return copy.deepcopy(built), copy.deepcopy(validated)

    def rebuild(self, validated, built=None, **overrides):
        if built is None:
            built = self.p01_shards[0][0]
        arguments = {
            "fixture_id": spec.FIXTURE_ID,
            "profile": "tiny",
            "persona_id": built["persona_id"],
            "scope_key": built["scope_key"],
            "plan_sha256": PLAN_SHA256,
            "expected_contract_chunks": built["totals"]["planned_contract_chunks"],
            "expected_physical_rows": built["totals"]["physical_sources"],
            "expected_variant_counts": built["totals"]["sources_by_variant"],
        }
        arguments.update(overrides)
        return manifest.build_w0_scope_manifest(
            validated["physical_raw"], validated["logical_items"],
            validated["searchable_expectations"], **arguments,
        )

    def test_scope_manifest_is_canonical_sorted_and_root_independent(self):
        built, validated = self.first()
        rebuilt, second = self.rebuild(validated, built)
        self.assertEqual(rebuilt, built)
        self.assertEqual(second, validated)
        self.assertRegex(built["semantic_root_sha256"], r"^[0-9a-f]{64}$")
        self.assertRegex(built["state_root_sha256"], r"^[0-9a-f]{64}$")

        renamed = copy.deepcopy(validated)
        row = renamed["physical_raw"][0]
        old_name = row["file_name"]
        new_name = "renamed-source." + row["extension"]
        row["file_name"] = new_name
        row["relative_path"] = row["relative_path"][:-len(old_name)] + new_name
        renamed_manifest, _ = self.rebuild(renamed, built)
        self.assertEqual(
            renamed_manifest["semantic_root_sha256"], built["semantic_root_sha256"]
        )
        self.assertNotEqual(
            renamed_manifest["state_root_sha256"], built["state_root_sha256"]
        )

    def test_role_semantics_keep_plans_separate_from_actual_chunks(self):
        built, validated = self.first()
        contributor = next(
            row for row in validated["searchable_expectations"]
            if row["gate_role"] == "contract_contributor"
        )
        self.assertEqual(contributor["actual_chunk_policy"], "persona_contract_exact")
        incidental = next(
            row for row in validated["searchable_expectations"]
            if row["gate_role"] == "incidental_searchable"
        )
        self.assertEqual(incidental["planned_contract_chunks"], 0)
        self.assertEqual(incidental["planned_unit_keys"], [])
        self.assertEqual(
            incidental["actual_chunk_policy"], "observe_nonnegative_excluded"
        )

        invalid = copy.deepcopy(validated)
        invalid["searchable_expectations"][0]["chunk_hash"] = "0" * 64
        with self.assertRaisesRegex(manifest.PersonaManifestError, "field set"):
            self.rebuild(invalid, built)

    def test_logical_units_bind_exactly_to_physical_and_searchable_plans(self):
        built, validated = self.first()
        invalid = copy.deepcopy(validated)
        contributor = next(
            row for row in invalid["searchable_expectations"]
            if row["gate_role"] == "contract_contributor"
        )
        contributor["planned_unit_keys"] = [
            contributor["source_id"] + ":not-a-logical-unit"
        ]
        with self.assertRaisesRegex(manifest.PersonaManifestError, "logical units"):
            self.rebuild(invalid, built)

        invalid = copy.deepcopy(validated)
        invalid["logical_items"][0]["parent_unit_key"] = invalid["logical_items"][0][
            "unit_key"
        ]
        with self.assertRaisesRegex(manifest.PersonaManifestError, "parent itself"):
            self.rebuild(invalid, built)

    def test_duplicate_raw_hash_and_wrong_renderer_fail_closed(self):
        built, validated = self.first()
        invalid = copy.deepcopy(validated)
        invalid["physical_raw"][1]["raw_sha256"] = invalid["physical_raw"][0][
            "raw_sha256"
        ]
        with self.assertRaisesRegex(manifest.PersonaManifestError, "unique"):
            self.rebuild(invalid, built)

        invalid = copy.deepcopy(validated)
        invalid["physical_raw"][0]["renderer_id"] = "alternate-renderer"
        with self.assertRaisesRegex(manifest.PersonaManifestError, "renderer"):
            self.rebuild(invalid, built)

    def test_sensitive_and_nonportable_w0_basenames_are_rejected(self):
        built, validated = self.first()
        for file_name in ("client-password.md", "source."):
            invalid = copy.deepcopy(validated)
            row = invalid["physical_raw"][0]
            old_name = row["file_name"]
            row["file_name"] = file_name
            row["relative_path"] = row["relative_path"][:-len(old_name)] + file_name
            with self.subTest(file_name=file_name), self.assertRaises(
                manifest.PersonaManifestError
            ):
                self.rebuild(invalid, built)

    def test_canonical_json_rejects_float_and_atomic_write_is_no_replace(self):
        with self.assertRaises(manifest.PersonaManifestError):
            manifest.canonical_json_bytes({"not_canonical": 1.5})
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary).resolve() / "rows.jsonl"
            summary = manifest.atomic_write_canonical_jsonl(
                path, ({"z": 1}, {"a": 2})
            )
            self.assertEqual(path.read_bytes(), b'{"a":2}\n{"z":1}\n')
            self.assertEqual(summary["rows"], 2)
            before = path.read_bytes()
            with self.assertRaises(manifest.PersonaManifestError):
                manifest.atomic_write_canonical_jsonl(path, ({"new": True},))
            self.assertEqual(path.read_bytes(), before)

    def test_scope_publication_is_idempotent_and_verifier_detects_tamper(self):
        built, validated = self.first()
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary).resolve() / "oracle" / built["persona_id"] / built[
                "scope_key"
            ]
            arguments = {
                "fixture_id": spec.FIXTURE_ID,
                "profile": "tiny",
                "persona_id": built["persona_id"],
                "scope_key": built["scope_key"],
                "plan_sha256": PLAN_SHA256,
                "expected_contract_chunks": built["totals"]["planned_contract_chunks"],
                "expected_physical_rows": built["totals"]["physical_sources"],
                "expected_variant_counts": built["totals"]["sources_by_variant"],
            }
            first = manifest.publish_w0_scope_shard(
                destination, validated["physical_raw"], validated["logical_items"],
                validated["searchable_expectations"], **arguments,
            )
            second = manifest.publish_w0_scope_shard(
                destination, validated["physical_raw"], validated["logical_items"],
                validated["searchable_expectations"], **arguments,
            )
            self.assertEqual(first, second)
            self.assertEqual(
                manifest.verify_w0_scope_shard(destination)["manifest"], built
            )
            ledger = destination / manifest.PHYSICAL_LEDGER_NAME
            ledger.write_bytes(ledger.read_bytes() + b"{}\n")
            with self.assertRaises(manifest.PersonaManifestError):
                manifest.verify_w0_scope_shard(destination)

    def test_scope_publication_refuses_symlink_destination(self):
        built, validated = self.first()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            foreign = root / "foreign"
            foreign.mkdir()
            destination = root / "scope"
            try:
                destination.symlink_to(foreign, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            with self.assertRaises(manifest.PersonaManifestError):
                manifest.publish_w0_scope_shard(
                    destination, validated["physical_raw"],
                    validated["logical_items"], validated["searchable_expectations"],
                    fixture_id=spec.FIXTURE_ID, profile="tiny",
                    persona_id=built["persona_id"], scope_key=built["scope_key"],
                    plan_sha256=PLAN_SHA256,
                    expected_contract_chunks=built["totals"]["planned_contract_chunks"],
                    expected_physical_rows=built["totals"]["physical_sources"],
                    expected_variant_counts=built["totals"]["sources_by_variant"],
                )
            self.assertEqual(list(foreign.iterdir()), [])

    def test_suite_requires_complete_inventory_and_rejects_forged_identity(self):
        manifests = [item[0] for item in self.p01_shards]
        projections = [item[1] for item in self.p01_shards]
        with self.assertRaisesRegex(manifest.PersonaManifestError, "20 x 20"):
            manifest.build_w0_suite_manifest(
                fixture_id=spec.FIXTURE_ID, profile="tiny",
                plan_sha256=PLAN_SHA256, shard_manifests=manifests,
                validated_shards=projections,
            )
        forged_manifests = manifests * 20
        forged_projections = projections * 20
        forged_manifests = copy.deepcopy(forged_manifests)
        forged_manifests[0]["persona_id"] = "../../escape"
        with self.assertRaises(manifest.PersonaManifestError):
            manifest.build_w0_suite_manifest(
                fixture_id=spec.FIXTURE_ID, profile="tiny",
                plan_sha256=PLAN_SHA256, shard_manifests=forged_manifests,
                validated_shards=forged_projections,
            )

    def test_complete_tiny_suite_has_exact_20x20_totals_and_stable_order(self):
        shards = [item for persona in spec.PERSONAS for item in _persona_shards(persona["id"])]
        manifests = [item[0] for item in shards]
        projections = [item[1] for item in shards]
        suite = manifest.build_w0_suite_manifest(
            fixture_id=spec.FIXTURE_ID, profile="tiny", plan_sha256=PLAN_SHA256,
            shard_manifests=reversed(manifests),
            validated_shards=reversed(projections),
        )
        self.assertEqual(suite["totals"]["personas"], 20)
        self.assertEqual(suite["totals"]["scope_shards"], 400)
        self.assertEqual(suite["totals"], {
            **suite["expected_totals"],
            "logical_items": suite["totals"]["logical_items"],
        })
        self.assertNotIn(str(Path.cwd()), json.dumps(suite))


if __name__ == "__main__":
    unittest.main()
