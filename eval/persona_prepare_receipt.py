"""Non-executing receipt bound to Rust-produced persona artifacts.

This module deliberately composes identity evidence only. It never derives
persona plans, manifests, render output, source counts, or history state.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path

from . import persona_artifacts
from . import persona_storage as storage

PREPARE_RECEIPT_INTENT_SCHEMA = "kio.persona.prepare-receipt-intent/v2"
ROOT_RECEIPT_SCHEMA = "kio.persona.prepare-root-receipt/v2"
MAX_INTENT_BYTES = 4 * 1024 * 1024
MAX_ROOT_RECEIPT_BYTES = 4 * 1024 * 1024
MAX_DESTINATION_ROOT_BYTES = 4096
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}\Z")
_PROFILES = frozenset(("tiny", "pilot", "full"))

class PersonaPrepareReceiptError(ValueError):
    """An input does not make the narrow receipt contract."""

def _bytes(value: object) -> bytes:
    try:
        return (json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    except (TypeError, ValueError) as error:
        raise PersonaPrepareReceiptError("value is not canonical JSON") from error

def _digest(value: object, label: str) -> str:
    if type(value) is not str or _DIGEST.fullmatch(value) is None:
        raise PersonaPrepareReceiptError(f"{label} must be sha256:<64 lowercase hex>")
    return value

def _absolute_path(value: object, label: str) -> str:
    if type(value) is not str or not value or len(value.encode("utf-8")) > MAX_DESTINATION_ROOT_BYTES:
        raise PersonaPrepareReceiptError(f"{label} is not a bounded path")
    path = Path(value)
    if (
        not path.is_absolute()
        or "\x00" in value
        or Path(os.path.normpath(value)) != path
    ):
        raise PersonaPrepareReceiptError(
            f"{label} must be absolute and lexically normalized"
        )
    return str(path)

def _bundle_fields(bundle: object) -> dict[str, object]:
    try:
        fields = {
            name: getattr(bundle, name)
            for name in (
                "fixture_id",
                "profile",
                "plan_digest",
                "plan_sha256",
                "schedule_sha256",
                "render_sha256",
            )
        }
    except AttributeError as error:
        raise PersonaPrepareReceiptError("artifact bundle is invalid") from error
    if fields["fixture_id"] != persona_artifacts.FIXTURE_ID:
        raise PersonaPrepareReceiptError("artifact fixture id is invalid")
    if fields["profile"] not in _PROFILES:
        raise PersonaPrepareReceiptError("artifact profile is invalid")
    for name in ("plan_digest", "plan_sha256", "schedule_sha256", "render_sha256"):
        _digest(fields[name], name)
    if fields["plan_digest"] != fields["plan_sha256"]:
        raise PersonaPrepareReceiptError("artifact plan digest differs from plan bytes")
    return fields


def _bound_root_binding(path: os.PathLike[str] | str, fields: dict[str, object], replay_id: str, destination: str) -> tuple[str, str]:
    binding_path = _absolute_path(os.fspath(path), "root_binding_path")
    if Path(binding_path) != Path(destination) / "persona-root-binding.json":
        raise PersonaPrepareReceiptError("root binding path is outside destination root")
    try:
        raw, digest = persona_artifacts.read_exact_artifact(
            Path(binding_path), "root binding", 64 * 1024
        )
        value = json.loads(raw)
    except (OSError, ValueError, persona_artifacts.PersonaArtifactError) as error:
        raise PersonaPrepareReceiptError("root binding is unavailable or invalid") from error
    required = {"schema", "fixture_id", "profile", "replay_id", "destination_root", "filesystem_device", "plan_digest", "plan_sha256", "schedule_sha256", "render_sha256", "artifact_bundle_sha256", "sources_materialized", "actual_kio_evidence", "history_ready"}
    if type(value) is not dict or set(value) != required or storage.canonical_json_bytes(value) != raw:
        raise PersonaPrepareReceiptError("root binding is not canonical")
    if value.get("schema") != "kio.persona.storage-root-binding/v2" or value.get("fixture_id") != fields["fixture_id"] or value.get("profile") != fields["profile"] or value.get("replay_id") != replay_id or value.get("destination_root") != destination:
        raise PersonaPrepareReceiptError("root binding identity differs")
    for name in ("plan_digest", "plan_sha256", "schedule_sha256", "render_sha256"):
        if value.get(name) != fields[name]:
            raise PersonaPrepareReceiptError("root binding artifact differs")
    expected_artifact = persona_artifacts.artifact_bundle_record(
        fixture_id=fields["fixture_id"],
        profile=fields["profile"],
        plan_digest=fields["plan_digest"],
        plan_sha256=fields["plan_sha256"],
        schedule_sha256=fields["schedule_sha256"],
        render_sha256=fields["render_sha256"],
    )
    expected_artifact_sha256 = "sha256:" + hashlib.sha256(
        storage.canonical_json_bytes(expected_artifact)
    ).hexdigest()
    try:
        destination_metadata = Path(destination).lstat()
    except OSError as error:
        raise PersonaPrepareReceiptError("destination root is unavailable") from error
    if (
        not storage.is_plain_directory_metadata(destination_metadata)
        or type(value.get("filesystem_device")) is not int
        or value.get("filesystem_device") != destination_metadata.st_dev
        or value.get("artifact_bundle_sha256") != expected_artifact_sha256
        or not all(value.get(name) is False for name in ("sources_materialized", "actual_kio_evidence", "history_ready"))
    ):
        raise PersonaPrepareReceiptError("root binding makes unsupported claims")
    return binding_path, digest

def build_prepare_receipt_intent(*, bundle: object, replay_id: str, destination_root: os.PathLike[str] | str, root_binding_path: os.PathLike[str] | str, root_binding_sha256: str | None = None) -> dict[str, object]:
    fields = _bundle_fields(bundle)
    if type(replay_id) is not str or replay_id not in storage.REPLAY_IDS:
        raise PersonaPrepareReceiptError("replay_id is invalid")
    destination = _absolute_path(os.fspath(destination_root), "destination_root")
    binding_path, binding_digest = _bound_root_binding(root_binding_path, fields, replay_id, destination)
    if root_binding_sha256 is not None and _digest(root_binding_sha256, "root_binding_sha256") != binding_digest:
        raise PersonaPrepareReceiptError("root binding digest differs")
    intent = {"schema": PREPARE_RECEIPT_INTENT_SCHEMA, "schema_version": 2, **fields, "replay_id": replay_id,
        "destination_root": destination, "root_binding_path": binding_path, "root_binding_sha256": binding_digest,
        "claims": {"filesystem_mutation": False, "subprocess_execution": False, "materialization_complete": False, "actual_kio_evidence": False, "history_ready": False}}
    if len(_bytes(intent)) > MAX_INTENT_BYTES:
        raise PersonaPrepareReceiptError("prepare intent exceeds byte bound")
    return intent

def validate_prepare_receipt_intent(value: object) -> dict[str, object]:
    required = {"schema", "schema_version", "fixture_id", "profile", "plan_digest", "plan_sha256", "schedule_sha256", "render_sha256", "replay_id", "destination_root", "root_binding_path", "root_binding_sha256", "claims"}
    if type(value) is not dict or set(value) != required or value.get("schema") != PREPARE_RECEIPT_INTENT_SCHEMA or value.get("schema_version") != 2:
        raise PersonaPrepareReceiptError("prepare intent schema or fields differ")
    proxy = type("Bundle", (), {name: value[name] for name in ("fixture_id", "profile", "plan_digest", "plan_sha256", "schedule_sha256", "render_sha256")})()
    expected = build_prepare_receipt_intent(bundle=proxy, replay_id=value["replay_id"], destination_root=value["destination_root"], root_binding_path=value["root_binding_path"], root_binding_sha256=value["root_binding_sha256"])
    if _bytes(value) != _bytes(expected):
        raise PersonaPrepareReceiptError("prepare intent is not canonical or makes claims")
    return expected

def build_prepare_receipt(intent: object) -> dict[str, object]:
    intent = validate_prepare_receipt_intent(intent)
    receipt = {"schema": ROOT_RECEIPT_SCHEMA, "schema_version": 2, "prepare_receipt_intent": intent,
        "prepare_receipt_intent_sha256": "sha256:" + hashlib.sha256(_bytes(intent)).hexdigest(),
        "claims": {"execution_complete": False, "materialization_complete": False, "actual_kio_evidence": False, "history_ready": False}}
    if len(_bytes(receipt)) > MAX_ROOT_RECEIPT_BYTES:
        raise PersonaPrepareReceiptError("prepare receipt exceeds byte bound")
    return receipt

def validate_prepare_receipt(value: object) -> dict[str, object]:
    if type(value) is not dict or set(value) != {"schema", "schema_version", "prepare_receipt_intent", "prepare_receipt_intent_sha256", "claims"} or value.get("schema") != ROOT_RECEIPT_SCHEMA or value.get("schema_version") != 2:
        raise PersonaPrepareReceiptError("prepare receipt schema or fields differ")
    expected = build_prepare_receipt(value["prepare_receipt_intent"])
    if _bytes(value) != _bytes(expected):
        raise PersonaPrepareReceiptError("prepare receipt is not canonical or makes claims")
    return expected

def prepare_receipt_sha256(value: object) -> str:
    return "sha256:" + hashlib.sha256(_bytes(validate_prepare_receipt(value))).hexdigest()
