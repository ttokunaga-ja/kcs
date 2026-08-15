"""Create-only materialization of Rust-owned persona artifact bundles.

This retained Python boundary copies already-produced Rust artifacts into one
owned storage root. It does not render sources, execute Kio, or claim history.
"""

from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import sys

from . import persona_artifacts
from . import persona_storage as storage


ARTIFACT_BUNDLE_FILE = "artifact-bundle.json"
ROOT_BINDING_FILE = "persona-root-binding.json"
RECEIPT_FILE = "materialization-receipt.json"
ROOT_BINDING_SCHEMA = "kio.persona.storage-root-binding/v2"
MATERIALIZATION_RECEIPT_SCHEMA = "kio.persona.materialization-receipt/v2"


class PersonaGenerationError(RuntimeError):
    """The artifact bundle cannot be materialized without weakening safety."""


def _canonical(value: dict[str, object]) -> bytes:
    return storage.canonical_json_bytes(value)


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _absolute_destination(destination: Path) -> Path:
    supplied = Path(os.fspath(destination))
    if not supplied.is_absolute() or Path(os.path.normpath(supplied)) != supplied:
        raise PersonaGenerationError(
            "destination must be absolute and lexically normalized"
        )
    return supplied


def _root_binding(
    bundle: persona_artifacts.ArtifactBundle,
    replay_id: str,
    destination: Path,
    *,
    filesystem_device: int | None = None,
) -> dict[str, object]:
    destination = _absolute_destination(destination)
    if filesystem_device is None:
        try:
            filesystem_device = destination.parent.stat().st_dev
        except OSError as error:
            raise PersonaGenerationError("destination parent is unavailable") from error
    artifact = persona_artifacts.artifact_bundle_record(
        fixture_id=bundle.fixture_id,
        profile=bundle.profile,
        plan_digest=bundle.plan_digest,
        plan_sha256=bundle.plan_sha256,
        schedule_sha256=bundle.schedule_sha256,
        render_sha256=bundle.render_sha256,
    )
    return {
        "schema": ROOT_BINDING_SCHEMA,
        "fixture_id": bundle.fixture_id,
        "profile": bundle.profile,
        "replay_id": replay_id,
        "destination_root": str(destination),
        "filesystem_device": filesystem_device,
        "plan_digest": bundle.plan_digest,
        "plan_sha256": bundle.plan_sha256,
        "schedule_sha256": bundle.schedule_sha256,
        "render_sha256": bundle.render_sha256,
        "artifact_bundle_sha256": _digest(_canonical(artifact)),
        "sources_materialized": False,
        "actual_kio_evidence": False,
        "history_ready": False,
    }


def _materialization_receipt(binding: dict[str, object]) -> dict[str, object]:
    return {**binding, "schema": MATERIALIZATION_RECEIPT_SCHEMA}


def materialize(
    *,
    plan: Path,
    schedule: Path,
    render: Path,
    destination: Path,
    replay_id: str,
) -> storage.PublishResult:
    destination = _absolute_destination(destination)
    try:
        bundle = persona_artifacts.load_bundle(plan, schedule, render)
    except persona_artifacts.PersonaArtifactError as error:
        raise PersonaGenerationError(str(error)) from error

    snapshots: list[tuple[str, bytes]] = []
    sources = (
        (
            "persona-plan.json",
            plan,
            persona_artifacts.MAX_PLAN_BYTES,
            bundle.plan_sha256,
        ),
        (
            "persona-schedule.json",
            schedule,
            persona_artifacts.MAX_SCHEDULE_BYTES,
            bundle.schedule_sha256,
        ),
        (
            "persona-render.json",
            render,
            persona_artifacts.MAX_RENDER_BYTES,
            bundle.render_sha256,
        ),
    )
    for name, source, maximum, expected in sources:
        try:
            raw, digest = persona_artifacts.read_exact_artifact(
                source, name, maximum
            )
        except persona_artifacts.PersonaArtifactError as error:
            raise PersonaGenerationError(str(error)) from error
        if digest != expected:
            raise PersonaGenerationError("artifact changed after bundle binding")
        snapshots.append((name, raw))

    artifact = persona_artifacts.artifact_bundle_record(
        fixture_id=bundle.fixture_id,
        profile=bundle.profile,
        plan_digest=bundle.plan_digest,
        plan_sha256=bundle.plan_sha256,
        schedule_sha256=bundle.schedule_sha256,
        render_sha256=bundle.render_sha256,
    )
    artifact_raw = _canonical(artifact)
    artifact_sha = _digest(artifact_raw)
    try:
        inspected = storage.preflight_destination(
            destination,
            expected_profile=bundle.profile,
            expected_replay_id=replay_id,
            expected_artifact_bundle_sha256=artifact_sha,
        )
    except storage.PersonaStorageError as error:
        raise PersonaGenerationError(str(error)) from error
    if inspected.root != destination:
        raise PersonaGenerationError("storage boundary changed destination spelling")

    try:
        filesystem_device = (
            inspected.root.stat().st_dev
            if inspected.disposition == "owned"
            else inspected.root.parent.stat().st_dev
        )
    except OSError as error:
        raise PersonaGenerationError("destination filesystem is unavailable") from error
    binding = _root_binding(
        bundle,
        replay_id,
        inspected.root,
        filesystem_device=filesystem_device,
    )
    binding_raw = _canonical(binding)
    binding_sha = _digest(binding_raw)
    receipt_raw = _canonical(_materialization_receipt(binding))

    def populate(root: Path) -> None:
        for name, raw in snapshots:
            storage.atomic_write_file(root / name, raw)
        storage.atomic_write_file(root / ARTIFACT_BUNDLE_FILE, artifact_raw)
        storage.atomic_write_file(root / ROOT_BINDING_FILE, binding_raw)
        storage.atomic_write_file(root / RECEIPT_FILE, receipt_raw)

    def validate(root: Path) -> None:
        allowed = {
            storage.OWNER_MARKER_NAME,
            storage.STAGING_OWNER_MARKER_NAME,
            storage.NOREPLACE_PROBE_SOURCE,
            storage.NOREPLACE_PROBE_DESTINATION,
            "persona-plan.json",
            "persona-schedule.json",
            "persona-render.json",
            ARTIFACT_BUNDLE_FILE,
            ROOT_BINDING_FILE,
            RECEIPT_FILE,
        }
        if {entry.name for entry in root.iterdir()} - allowed:
            raise PersonaGenerationError("published root has unexpected entries")
        try:
            loaded = persona_artifacts.load_bundle(
                root / "persona-plan.json",
                root / "persona-schedule.json",
                root / "persona-render.json",
            )
            if (
                persona_artifacts.artifact_bundle_record(
                    fixture_id=loaded.fixture_id,
                    profile=loaded.profile,
                    plan_digest=loaded.plan_digest,
                    plan_sha256=loaded.plan_sha256,
                    schedule_sha256=loaded.schedule_sha256,
                    render_sha256=loaded.render_sha256,
                )
                != artifact
                or root.stat().st_dev != binding["filesystem_device"]
                or storage._read_plain_file(
                    root / ARTIFACT_BUNDLE_FILE, 64 * 1024, "artifact bundle"
                )
                != artifact_raw
                or storage._read_plain_file(
                    root / ROOT_BINDING_FILE, 64 * 1024, "root binding"
                )
                != binding_raw
                or storage._read_plain_file(
                    root / RECEIPT_FILE, 64 * 1024, "materialization receipt"
                )
                != receipt_raw
            ):
                raise PersonaGenerationError(
                    "published artifact bundle changed during materialization"
                )
        except (
            persona_artifacts.PersonaArtifactError,
            storage.PersonaStorageError,
        ) as error:
            raise PersonaGenerationError(str(error)) from error

    try:
        if inspected.disposition == "owned":
            owner = storage.require_ready_owned_root(
                destination,
                profile=bundle.profile,
                replay_id=replay_id,
                artifact_bundle_sha256=artifact_sha,
                root_binding_sha256=binding_sha,
            )
            validate(inspected.root)
            return storage.PublishResult(
                inspected.root,
                owner,
                published=False,
                plan_only=False,
            )
        return storage.atomic_publish_owned_root(
            destination,
            profile=bundle.profile,
            replay_id=replay_id,
            artifact_bundle_sha256=artifact_sha,
            root_binding_sha256=binding_sha,
            populate=populate,
            validate=validate,
        )
    except storage.PersonaStorageError as error:
        raise PersonaGenerationError(str(error)) from error


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Materialize a Rust-owned persona artifact bundle."
    )
    commands = parser.add_subparsers(dest="command", required=True)
    command = commands.add_parser("materialize")
    for argument in ("plan", "schedule", "render", "destination"):
        command.add_argument(f"--{argument}", required=True, type=Path)
    command.add_argument(
        "--replay-id",
        required=True,
        choices=tuple(sorted(storage.REPLAY_IDS)),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = materialize(
            plan=args.plan,
            schedule=args.schedule,
            render=args.render,
            destination=args.destination,
            replay_id=args.replay_id,
        )
    except (OSError, PersonaGenerationError) as error:
        print(f"[error] {error}", file=sys.stderr)
        return 1
    disposition = "published" if result.published else "verified-noop"
    print(f"[ok] persona artifact bundle {disposition}: {result.root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
