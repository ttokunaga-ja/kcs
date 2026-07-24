"""Bounded, non-authorizing storage and composition for persona event plans.

This layer keeps at most one complete per-person event manifest in memory and
merges only one compact schedule-projection row per persona.  It deliberately
does not execute W1--W5 events and does not claim that the generic storage
publisher's final-path identity is formally attested.  The artifacts are
development/planning evidence until that lower-level publication blocker is
resolved and a supervisor supplies independent RSS receipts.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import zip_longest
import hashlib
import json
import os
from pathlib import Path
from typing import Iterable, Iterator

try:  # Package imports and direct ``python eval/...`` execution.
    from . import generate_persona_corpus as generator
    from . import persona_event_manifest as persona_events
    from . import persona_fixture_spec as spec
    from . import persona_full_scale_limits as full_limits
    from . import persona_manifest as canonical_manifest
    from . import persona_storage as storage
    from . import persona_streaming_storage as stream_storage
    from . import persona_suite_event_manifest as suite_events
except ImportError:  # pragma: no cover - direct-script compatibility.
    import generate_persona_corpus as generator
    import persona_event_manifest as persona_events
    import persona_fixture_spec as spec
    import persona_full_scale_limits as full_limits
    import persona_manifest as canonical_manifest
    import persona_storage as storage
    import persona_streaming_storage as stream_storage
    import persona_suite_event_manifest as suite_events


PERSON_CONTROL_SCHEMA = "kio.persona.streaming-event-person-control/v1"
SUITE_CONTROL_SCHEMA = "kio.persona.streaming-event-suite-control/v1"
LOCATOR_SCHEMA = "kio.persona.streaming-event-locator/v1"
SCHEDULE_LOCATOR_SCHEMA = "kio.persona.streaming-suite-schedule-locator/v1"
MMR_SCHEMA = "kio.persona.streaming-schedule-mmr/v1"
SCHEMA_VERSION = 1
STATUS = "planned_not_observed_non_authorizing"
FORMAL_PUBLICATION_BLOCKER = stream_storage.FORMAL_PUBLICATION_BLOCKER

EVENTS_DIRECTORY = "events"
BOUNDARIES_DIRECTORY = "boundaries"
PERSON_SCHEDULE_DIRECTORY = "schedule-projection"
PERSON_CONTROL_DIRECTORY = "control"
SUITE_SCHEDULE_DIRECTORY = "schedule"
SUITE_LOCATORS_DIRECTORY = "locators"
SUITE_CONTROL_DIRECTORY = "control"

_PERSON_ENTRIES = frozenset((
    EVENTS_DIRECTORY,
    BOUNDARIES_DIRECTORY,
    PERSON_SCHEDULE_DIRECTORY,
    PERSON_CONTROL_DIRECTORY,
))
_SUITE_ENTRIES = frozenset((
    SUITE_SCHEDULE_DIRECTORY,
    SUITE_LOCATORS_DIRECTORY,
    SUITE_CONTROL_DIRECTORY,
))
_PERSONA_IDS = tuple(persona["id"] for persona in spec.PERSONAS)

_EVENT_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=full_limits.MAX_EVENT_ROW_BYTES,
    max_rows_per_shard=full_limits.MAX_JSONL_SHARD_ROWS,
    max_shard_bytes=full_limits.MAX_JSONL_SHARD_BYTES,
    max_shards=32,
    max_total_rows=full_limits.MAX_EVENT_ROWS_PER_PERSONA,
    max_total_bytes=full_limits.MAX_LOGICAL_EVENT_BYTES_PER_PERSONA,
)
_BOUNDARY_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=full_limits.MAX_BOUNDARY_ROW_BYTES,
    max_rows_per_shard=full_limits.MAX_JSONL_SHARD_ROWS,
    max_shard_bytes=full_limits.MAX_JSONL_SHARD_BYTES,
    max_shards=8,
    max_total_rows=full_limits.MAX_BOUNDARY_ROWS_PER_PERSONA,
    max_total_bytes=full_limits.MAX_LOGICAL_EVENT_BYTES_PER_PERSONA,
)
_PERSON_SCHEDULE_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=full_limits.MAX_SCHEDULE_ROW_BYTES,
    max_rows_per_shard=full_limits.MAX_JSONL_SHARD_ROWS,
    max_shard_bytes=full_limits.MAX_JSONL_SHARD_BYTES,
    max_shards=32,
    max_total_rows=full_limits.MAX_SCHEDULE_ROWS_PER_PERSONA,
    max_total_bytes=full_limits.MAX_LOGICAL_EVENT_BYTES_PER_PERSONA,
)
_CONTROL_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=8 * 1024 * 1024,
    max_rows_per_shard=1,
    max_shard_bytes=8 * 1024 * 1024,
    max_shards=1,
    max_total_rows=1,
    max_total_bytes=8 * 1024 * 1024,
)
_SUITE_SCHEDULE_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=full_limits.MAX_SCHEDULE_ROW_BYTES,
    max_rows_per_shard=full_limits.MAX_JSONL_SHARD_ROWS,
    max_shard_bytes=full_limits.MAX_JSONL_SHARD_BYTES,
    max_shards=128,
    max_total_rows=full_limits.FROZEN_PER_REPLAY_COUNTS["schedule_items"],
    max_total_bytes=1024 * 1024 * 1024,
)
_SUITE_LOCATOR_LIMITS = stream_storage.ArtifactLimits(
    max_row_bytes=full_limits.MAX_LOCATOR_ROW_BYTES,
    max_rows_per_shard=full_limits.MAX_JSONL_SHARD_ROWS,
    max_shard_bytes=full_limits.MAX_JSONL_SHARD_BYTES,
    max_shards=128,
    max_total_rows=full_limits.FROZEN_PER_REPLAY_COUNTS["schedule_items"],
    max_total_bytes=1024 * 1024 * 1024,
)


class PersonaSuiteEventStreamingError(RuntimeError):
    """Raised when a bounded planner artifact or locator is not canonical."""


@dataclass(frozen=True)
class PersonaArtifactSummary:
    root: Path
    persona_id: str
    profile: str
    persona_plan_sha256: str
    event_manifest_sha256: str
    events: int
    boundaries: int
    schedule_items: int
    control_envelope_sha256: str
    schedule_envelope_sha256: str
    worker_capacity_receipt: dict[str, object] | None
    formal_publication_attested: bool = False
    formal_publication_blockers: tuple[str, ...] = (
        stream_storage.FORMAL_PUBLICATION_BLOCKER,
    )


@dataclass(frozen=True)
class SuiteArtifactSummary:
    root: Path
    profile: str
    schedule_sha256: str
    suite_event_manifest_sha256: str
    schedule_locator_root_sha256: str
    schedule_mmr_root_sha256: str
    schedule_items: int
    control_envelope_sha256: str
    formal_publication_attested: bool = False
    formal_publication_blockers: tuple[str, ...] = (
        stream_storage.FORMAL_PUBLICATION_BLOCKER,
    )


def _digest(value: object) -> str:
    return hashlib.sha256(
        canonical_manifest.canonical_json_bytes(value)
    ).hexdigest()


def _same_canonical_json(actual: object, expected: object) -> bool:
    try:
        return (
            canonical_manifest.canonical_json_bytes(actual)
            == canonical_manifest.canonical_json_bytes(expected)
        )
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError):
        return False


def _canonical_array_sha256(rows: Iterable[dict[str, object]]) -> str:
    return suite_events.canonical_array_sha256(rows)


def _canonical_byte_length(pieces: Iterable[bytes]) -> int:
    total = 0
    for piece in pieces:
        total += len(piece)
    return total


def _artifact_max_row_bytes(
    root: Path,
    receipt: stream_storage.ArtifactReceipt,
    limits: stream_storage.ArtifactLimits,
) -> int:
    maximum = 0
    for record in stream_storage.iter_jsonl_records(
        root,
        limits=limits,
        expected_envelope_sha256=receipt.storage_envelope_sha256,
    ):
        maximum = max(maximum, record.byte_length)
    if maximum < 1:
        raise PersonaSuiteEventStreamingError(
            "a non-empty logical artifact has no verified rows"
        )
    return maximum


def _max_json_depth(value: object, depth: int = 0) -> int:
    maximum = depth
    if type(value) is dict:
        for item in value.values():
            maximum = max(maximum, _max_json_depth(item, depth + 1))
    elif type(value) in (list, tuple):
        for item in value:
            maximum = max(maximum, _max_json_depth(item, depth + 1))
    return maximum


def _artifact_projection(receipt: stream_storage.ArtifactReceipt) -> dict[str, object]:
    return {
        "storage_envelope_sha256": receipt.storage_envelope_sha256,
        "canonical_rows_sha256": receipt.canonical_rows_sha256,
        "rows": receipt.rows,
        "bytes": receipt.bytes,
        "formal_publication_attested": receipt.formal_publication_attested,
        "formal_publication_blockers": list(
            receipt.formal_publication_blockers
        ),
        "shards": [
            {
                "ordinal": value.ordinal,
                "file": value.file,
                "rows": value.rows,
                "bytes": value.bytes,
                "sha256": value.sha256,
            }
            for value in receipt.shards
        ],
    }


def _locator(
    kind: str,
    receipt: stream_storage.ArtifactReceipt,
    record: stream_storage.JsonlRecord,
) -> dict[str, object]:
    descriptor = receipt.shards[record.shard_ordinal]
    return {
        "schema": LOCATOR_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "kind": kind,
        "artifact_envelope_sha256": receipt.storage_envelope_sha256,
        "shard_ordinal": record.shard_ordinal,
        "shard_file": descriptor.file,
        "row_ordinal": None,
        "byte_offset": record.byte_offset,
        "byte_length": record.byte_length,
        "stored_row_sha256": record.row_sha256,
    }


def _records_with_ordinals(
    root: Path,
    receipt: stream_storage.ArtifactReceipt,
    limits: stream_storage.ArtifactLimits,
):
    for ordinal, record in enumerate(
        stream_storage.iter_jsonl_records(
            root,
            limits=limits,
            expected_envelope_sha256=receipt.storage_envelope_sha256,
        ),
        start=1,
    ):
        yield ordinal, record


def _one_control_row(
    root: Path,
    *,
    expected_envelope_sha256: str | None = None,
) -> tuple[dict[str, object], stream_storage.ArtifactReceipt]:
    receipt = stream_storage.verify_jsonl_artifact(
        root,
        limits=_CONTROL_LIMITS,
        expected_envelope_sha256=expected_envelope_sha256,
    )
    rows = list(stream_storage.iter_jsonl_artifact(
        root,
        limits=_CONTROL_LIMITS,
        expected_envelope_sha256=receipt.storage_envelope_sha256,
    ))
    if len(rows) != 1:
        raise PersonaSuiteEventStreamingError("control artifact must have one row")
    return rows[0], receipt


def _ensure_planning_root(path: Path) -> None:
    try:
        storage.atomic_create_directory(path, parents=True)
    except storage.PersonaStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    metadata = path.lstat()
    if not storage.is_plain_directory_metadata(metadata) or path.is_symlink():
        raise PersonaSuiteEventStreamingError("planning root is not a plain directory")


def _capacity_shards(
    kind: str,
    artifact_root: Path,
    receipt: stream_storage.ArtifactReceipt,
    limits: stream_storage.ArtifactLimits,
) -> list[dict[str, object]]:
    maximum_row_bytes = [0] * len(receipt.shards)
    for record in stream_storage.iter_jsonl_records(
        artifact_root,
        limits=limits,
        expected_envelope_sha256=receipt.storage_envelope_sha256,
    ):
        maximum_row_bytes[record.shard_ordinal] = max(
            maximum_row_bytes[record.shard_ordinal], record.byte_length
        )
    rows = []
    for index, value in enumerate(receipt.shards):
        if maximum_row_bytes[index] < 1:
            raise PersonaSuiteEventStreamingError(
                "capacity shard does not contain a verified row"
            )
        rows.append({
            "kind": kind,
            "ordinal": value.ordinal + 1,
            "sha256": value.sha256,
            "bytes": value.bytes,
            "rows": value.rows,
            "declared_max_row_bytes": maximum_row_bytes[index],
            "close_reason": (
                "final" if index == len(receipt.shards) - 1 else "row_limit"
            ),
        })
    return rows


def _expected_person_control_fields() -> frozenset[str]:
    return frozenset((
        "schema", "schema_version", "fixture_id", "profile", "status",
        "persona_id", "inputs", "outputs", "manifest_static",
        "worker_capacity_receipt", "contracts",
    ))


def build_persona_event_artifact(
    destination,
    profile,
    persona_id,
    *,
    generation_plan=None,
    event_manifest=None,
    supervised_peak_rss_bytes=None,
    supervised_max_initial_materialization_row_bytes=None,
    child_exit_code=0,
    child_terminating_signal=0,
):
    """Build and verify one canonical, non-authorizing person artifact.

    A formal full run must invoke this function in a fresh supervised process
    and pass the supervisor-observed RSS.  Even then the returned artifact
    retains the lower-level formal-publication blocker.
    """
    worker_measurement_values = (
        supervised_peak_rss_bytes,
        supervised_max_initial_materialization_row_bytes,
    )
    if any(value is not None for value in worker_measurement_values) and not all(
        value is not None for value in worker_measurement_values
    ):
        raise PersonaSuiteEventStreamingError(
            "worker capacity measurements must be supplied as one complete set"
        )
    if profile != "full" and any(
        value is not None for value in worker_measurement_values
    ):
        raise PersonaSuiteEventStreamingError(
            "worker capacity measurements are only valid for the full profile"
        )
    root = Path(destination).absolute()
    _ensure_planning_root(root)
    wrapper = (
        generator.build_persona_generation_plan(profile, persona_id)
        if generation_plan is None else generation_plan
    )
    generator.validate_persona_generation_plan(
        wrapper,
        expected_profile=profile,
        expected_persona_id=persona_id,
    )
    event_plan = generator.persona_event_plan_projection(
        wrapper,
        expected_profile=profile,
        expected_persona_id=persona_id,
    )
    manifest_value = (
        persona_events.build_event_manifest(event_plan, profile)
        if event_manifest is None else event_manifest
    )
    projected = suite_events.validate_and_project_persona_event_manifest(
        manifest_value, event_plan, profile
    )

    try:
        event_result = stream_storage.publish_jsonl_artifact(
            root / EVENTS_DIRECTORY, manifest_value["events"], limits=_EVENT_LIMITS
        )
        boundary_result = stream_storage.publish_jsonl_artifact(
            root / BOUNDARIES_DIRECTORY,
            manifest_value["boundaries"],
            limits=_BOUNDARY_LIMITS,
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    event_receipt = event_result.artifact
    boundary_receipt = boundary_result.artifact

    locators: dict[str, dict[str, object]] = {}
    for kind, artifact_root, receipt, limits, id_field in (
        ("event", root / EVENTS_DIRECTORY, event_receipt, _EVENT_LIMITS, "event_id"),
        (
            "boundary", root / BOUNDARIES_DIRECTORY, boundary_receipt,
            _BOUNDARY_LIMITS, "boundary_id",
        ),
    ):
        for ordinal, record in _records_with_ordinals(
            artifact_root, receipt, limits
        ):
            item_id = record.value.get(id_field)
            if type(item_id) is not str or item_id in locators:
                raise PersonaSuiteEventStreamingError(
                    "event/boundary artifact item identity is invalid"
                )
            value = _locator(kind, receipt, record)
            value["row_ordinal"] = ordinal
            locators[item_id] = value

    projection_rows = projected["schedule_projection"]
    phase_ranges = suite_events.projection_phase_ranges(projection_rows)
    schedule_rows = []
    if len(manifest_value["schedule"]) != len(projection_rows):
        raise PersonaSuiteEventStreamingError("person schedule/projection length differs")
    for schedule_item, projection in zip(
        manifest_value["schedule"], projection_rows
    ):
        item_id = schedule_item["item_id"]
        if projection["item_id"] != item_id or item_id not in locators:
            raise PersonaSuiteEventStreamingError(
                "person schedule projection locator inventory differs"
            )
        schedule_rows.append({
            "schedule_item": schedule_item,
            "projection": projection,
            "target_locator": locators[item_id],
        })
    try:
        schedule_result = stream_storage.publish_jsonl_artifact(
            root / PERSON_SCHEDULE_DIRECTORY,
            schedule_rows,
            limits=_PERSON_SCHEDULE_LIMITS,
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    schedule_receipt = schedule_result.artifact

    artifacts = {
        "events": _artifact_projection(event_receipt),
        "boundaries": _artifact_projection(boundary_receipt),
        "schedule": _artifact_projection(schedule_receipt),
    }
    event_manifest_sha256 = projected["manifest_sha256"]
    event_projection_sha256 = _canonical_array_sha256(projection_rows)
    worker_receipt = None
    if profile == "full" and supervised_peak_rss_bytes is not None:
        shards = (
            _capacity_shards(
                "events", root / EVENTS_DIRECTORY, event_receipt, _EVENT_LIMITS
            )
            + _capacity_shards(
                "boundaries", root / BOUNDARIES_DIRECTORY,
                boundary_receipt, _BOUNDARY_LIMITS,
            )
            + _capacity_shards(
                "schedule", root / PERSON_SCHEDULE_DIRECTORY,
                schedule_receipt, _PERSON_SCHEDULE_LIMITS,
            )
        )
        try:
            worker_receipt = full_limits.build_worker_capacity_receipt(
                persona_id=persona_id,
                event_manifest_sha256=event_manifest_sha256,
                event_projection_sha256=event_projection_sha256,
                shards=shards,
                max_json_depth=_max_json_depth(manifest_value),
                max_initial_materialization_row_bytes=(
                    supervised_max_initial_materialization_row_bytes
                ),
                peak_rss_bytes=supervised_peak_rss_bytes,
                child_exit_code=child_exit_code,
                child_terminating_signal=child_terminating_signal,
            )
        except full_limits.FullScaleLimitsError as error:
            raise PersonaSuiteEventStreamingError(str(error)) from error

    manifest_static = {
        key: value
        for key, value in manifest_value.items()
        if key not in ("events", "boundaries", "schedule")
    }
    control = {
        "schema": PERSON_CONTROL_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "status": STATUS,
        "persona_id": persona_id,
        "inputs": {
            "persona_generation_plan_sha256": _digest(wrapper),
            "persona_event_plan_sha256": _digest(event_plan),
        },
        "outputs": {
            "event_manifest_sha256": event_manifest_sha256,
            "event_projection_sha256": event_projection_sha256,
            "phase_ranges": phase_ranges,
            "counts": {
                "events": len(manifest_value["events"]),
                "boundaries": len(manifest_value["boundaries"]),
                "schedule_items": len(manifest_value["schedule"]),
            },
            "artifacts": artifacts,
            "content_binding_sha256": _digest({
                "domain": "kio.persona.streaming-event-person-content/v1",
                "persona_id": persona_id,
                "persona_event_plan_sha256": _digest(event_plan),
                "event_manifest_sha256": event_manifest_sha256,
                "event_projection_sha256": event_projection_sha256,
                "artifacts": artifacts,
            }),
        },
        "manifest_static": manifest_static,
        "worker_capacity_receipt": worker_receipt,
        "contracts": {
            "canonical_person_validator_completed": True,
            "contains_w1_w5_mutation": False,
            "planned_not_observed": True,
            "formal_publication_attested": False,
            "formal_publication_blocker": FORMAL_PUBLICATION_BLOCKER,
            "formal_publication_blockers": list(
                stream_storage.FORMAL_PUBLICATION_BLOCKERS
            ),
            "authorizes_history_execution": False,
        },
    }
    try:
        stream_storage.publish_jsonl_artifact(
            root / PERSON_CONTROL_DIRECTORY, [control], limits=_CONTROL_LIMITS
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    return verify_persona_event_artifact(root, profile, persona_id)


def _require_person_control(control, profile, persona_id):
    if type(control) is not dict or set(control) != _expected_person_control_fields():
        raise PersonaSuiteEventStreamingError("person control fields differ")
    if (
        control["schema"] != PERSON_CONTROL_SCHEMA
        or control["schema_version"] != SCHEMA_VERSION
        or control["fixture_id"] != spec.FIXTURE_ID
        or control["profile"] != profile
        or control["status"] != STATUS
        or control["persona_id"] != persona_id
    ):
        raise PersonaSuiteEventStreamingError("person control header differs")
    expected_contracts = {
        "canonical_person_validator_completed": True,
        "contains_w1_w5_mutation": False,
        "planned_not_observed": True,
        "formal_publication_attested": False,
        "formal_publication_blocker": FORMAL_PUBLICATION_BLOCKER,
        "formal_publication_blockers": list(
            stream_storage.FORMAL_PUBLICATION_BLOCKERS
        ),
        "authorizes_history_execution": False,
    }
    if control["contracts"] != expected_contracts:
        raise PersonaSuiteEventStreamingError("person control contracts differ")


def _receipt_for_control_artifact(root, name, control_projection, limits):
    if type(control_projection) is not dict:
        raise PersonaSuiteEventStreamingError("artifact projection is invalid")
    try:
        receipt = stream_storage.verify_jsonl_artifact(
            root / name,
            limits=limits,
            expected_envelope_sha256=control_projection.get(
                "storage_envelope_sha256"
            ),
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    if _artifact_projection(receipt) != control_projection:
        raise PersonaSuiteEventStreamingError(
            f"{name} artifact projection differs from control"
        )
    return receipt


def verify_persona_event_artifact(destination, profile, persona_id):
    """Read back and canonically revalidate exactly one person artifact."""
    root = Path(destination).absolute()
    try:
        metadata = root.lstat()
    except OSError as error:
        raise PersonaSuiteEventStreamingError("person artifact root is missing") from error
    if not storage.is_plain_directory_metadata(metadata) or root.is_symlink():
        raise PersonaSuiteEventStreamingError("person artifact root is unsafe")
    if set(os.listdir(root)) != _PERSON_ENTRIES:
        raise PersonaSuiteEventStreamingError(
            "person artifact root has an unexpected entry set"
        )
    try:
        control, control_receipt = _one_control_row(root / PERSON_CONTROL_DIRECTORY)
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    _require_person_control(control, profile, persona_id)
    outputs = control.get("outputs")
    if type(outputs) is not dict or set(outputs) != {
        "event_manifest_sha256", "event_projection_sha256", "phase_ranges",
        "counts", "artifacts", "content_binding_sha256",
    }:
        raise PersonaSuiteEventStreamingError("person control outputs differ")
    artifacts = outputs["artifacts"]
    if type(artifacts) is not dict or set(artifacts) != {
        "events", "boundaries", "schedule"
    }:
        raise PersonaSuiteEventStreamingError("person artifact inventory differs")
    event_receipt = _receipt_for_control_artifact(
        root, EVENTS_DIRECTORY, artifacts["events"], _EVENT_LIMITS
    )
    boundary_receipt = _receipt_for_control_artifact(
        root, BOUNDARIES_DIRECTORY, artifacts["boundaries"], _BOUNDARY_LIMITS
    )
    schedule_receipt = _receipt_for_control_artifact(
        root,
        PERSON_SCHEDULE_DIRECTORY,
        artifacts["schedule"],
        _PERSON_SCHEDULE_LIMITS,
    )

    events = []
    boundaries = []
    expected_locators = {}
    for kind, artifact_root, receipt, limits, destination_rows, id_field in (
        (
            "event", root / EVENTS_DIRECTORY, event_receipt, _EVENT_LIMITS,
            events, "event_id",
        ),
        (
            "boundary", root / BOUNDARIES_DIRECTORY, boundary_receipt,
            _BOUNDARY_LIMITS, boundaries, "boundary_id",
        ),
    ):
        for ordinal, record in _records_with_ordinals(
            artifact_root, receipt, limits
        ):
            item_id = record.value.get(id_field)
            if type(item_id) is not str or item_id in expected_locators:
                raise PersonaSuiteEventStreamingError(
                    "person artifact repeats an event/boundary id"
                )
            locator = _locator(kind, receipt, record)
            locator["row_ordinal"] = ordinal
            expected_locators[item_id] = locator
            destination_rows.append(record.value)

    schedule = []
    stored_projection = []
    for row in stream_storage.iter_jsonl_artifact(
        root / PERSON_SCHEDULE_DIRECTORY,
        limits=_PERSON_SCHEDULE_LIMITS,
        expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
    ):
        if type(row) is not dict or set(row) != {
            "schedule_item", "projection", "target_locator"
        }:
            raise PersonaSuiteEventStreamingError(
                "person schedule artifact row fields differ"
            )
        item = row["schedule_item"]
        projection = row["projection"]
        if type(item) is not dict or type(projection) is not dict:
            raise PersonaSuiteEventStreamingError("person schedule row is invalid")
        item_id = item.get("item_id")
        if (
            projection.get("item_id") != item_id
            or expected_locators.get(item_id) != row["target_locator"]
        ):
            raise PersonaSuiteEventStreamingError(
                "person schedule target locator differs"
            )
        schedule.append(item)
        stored_projection.append(projection)

    manifest_static = control["manifest_static"]
    if type(manifest_static) is not dict or any(
        key in manifest_static for key in ("events", "boundaries", "schedule")
    ):
        raise PersonaSuiteEventStreamingError("person manifest static value is invalid")
    manifest_value = dict(manifest_static)
    manifest_value.update({
        "events": events,
        "boundaries": boundaries,
        "schedule": schedule,
    })

    wrapper = generator.build_persona_generation_plan(profile, persona_id)
    event_plan = generator.persona_event_plan_projection(
        wrapper,
        expected_profile=profile,
        expected_persona_id=persona_id,
    )
    projected = suite_events.validate_and_project_persona_event_manifest(
        manifest_value, event_plan, profile
    )
    if projected["schedule_projection"] != stored_projection:
        raise PersonaSuiteEventStreamingError(
            "stored schedule projection differs from canonical manifest"
        )
    phase_ranges = suite_events.projection_phase_ranges(stored_projection)
    counts = {
        "events": len(events),
        "boundaries": len(boundaries),
        "schedule_items": len(schedule),
    }
    expected_inputs = {
        "persona_generation_plan_sha256": _digest(wrapper),
        "persona_event_plan_sha256": _digest(event_plan),
    }
    if control["inputs"] != expected_inputs:
        raise PersonaSuiteEventStreamingError("person plan input binding differs")
    if (
        outputs["event_manifest_sha256"] != projected["manifest_sha256"]
        or outputs["event_projection_sha256"]
        != _canonical_array_sha256(stored_projection)
        or outputs["phase_ranges"] != phase_ranges
        or outputs["counts"] != counts
    ):
        raise PersonaSuiteEventStreamingError("person logical output binding differs")
    expected_content_binding = _digest({
        "domain": "kio.persona.streaming-event-person-content/v1",
        "persona_id": persona_id,
        "persona_event_plan_sha256": expected_inputs[
            "persona_event_plan_sha256"
        ],
        "event_manifest_sha256": projected["manifest_sha256"],
        "event_projection_sha256": outputs["event_projection_sha256"],
        "artifacts": artifacts,
    })
    if outputs["content_binding_sha256"] != expected_content_binding:
        raise PersonaSuiteEventStreamingError("person content binding differs")

    worker_receipt = control["worker_capacity_receipt"]
    if profile == "full" and worker_receipt is not None:
        try:
            full_limits.validate_worker_capacity_receipt(worker_receipt)
        except full_limits.FullScaleLimitsError as error:
            raise PersonaSuiteEventStreamingError(str(error)) from error
        if (
            worker_receipt["persona_id"] != persona_id
            or worker_receipt["outputs"]["event_manifest_sha256"]
            != projected["manifest_sha256"]
            or worker_receipt["outputs"]["event_projection_sha256"]
            != outputs["event_projection_sha256"]
            or worker_receipt["outputs"]["shards"]
            != (
                _capacity_shards(
                    "events", root / EVENTS_DIRECTORY,
                    event_receipt, _EVENT_LIMITS,
                )
                + _capacity_shards(
                    "boundaries", root / BOUNDARIES_DIRECTORY,
                    boundary_receipt, _BOUNDARY_LIMITS,
                )
                + _capacity_shards(
                    "schedule", root / PERSON_SCHEDULE_DIRECTORY,
                    schedule_receipt, _PERSON_SCHEDULE_LIMITS,
                )
            )
            or worker_receipt["outputs"]["max_json_depth"]
            != _max_json_depth(manifest_value)
        ):
            raise PersonaSuiteEventStreamingError("worker receipt binding differs")
    elif worker_receipt is not None:
        raise PersonaSuiteEventStreamingError(
            "non-full artifact must not contain a full worker receipt"
        )
    return PersonaArtifactSummary(
        root=root,
        persona_id=persona_id,
        profile=profile,
        persona_plan_sha256=expected_inputs["persona_event_plan_sha256"],
        event_manifest_sha256=projected["manifest_sha256"],
        events=counts["events"],
        boundaries=counts["boundaries"],
        schedule_items=counts["schedule_items"],
        control_envelope_sha256=control_receipt.storage_envelope_sha256,
        schedule_envelope_sha256=schedule_receipt.storage_envelope_sha256,
        worker_capacity_receipt=worker_receipt,
    )


def _reject_duplicate_keys(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise PersonaSuiteEventStreamingError("pread row has duplicate JSON keys")
        value[key] = item
    return value


def _pread_target_locator(person_artifact_root, locator):
    """Resolve one target locator with descriptor-bound pread."""
    if type(locator) is not dict or set(locator) != {
        "schema", "schema_version", "kind", "artifact_envelope_sha256",
        "shard_ordinal", "shard_file", "row_ordinal", "byte_offset",
        "byte_length", "stored_row_sha256",
    }:
        raise PersonaSuiteEventStreamingError("scheduled item locator fields differ")
    kind = locator["kind"]
    if kind == "event":
        directory, limits = EVENTS_DIRECTORY, _EVENT_LIMITS
    elif kind == "boundary":
        directory, limits = BOUNDARIES_DIRECTORY, _BOUNDARY_LIMITS
    else:
        raise PersonaSuiteEventStreamingError("scheduled item locator kind is invalid")
    if locator["schema"] != LOCATOR_SCHEMA or locator["schema_version"] != 1:
        raise PersonaSuiteEventStreamingError("scheduled item locator schema differs")
    artifact_root = Path(person_artifact_root).absolute() / directory
    try:
        receipt = stream_storage.verify_jsonl_artifact(
            artifact_root,
            limits=limits,
            expected_envelope_sha256=locator["artifact_envelope_sha256"],
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    shard_ordinal = locator["shard_ordinal"]
    if (
        type(shard_ordinal) is not int
        or not 0 <= shard_ordinal < len(receipt.shards)
    ):
        raise PersonaSuiteEventStreamingError("locator shard ordinal is invalid")
    descriptor = receipt.shards[shard_ordinal]
    if locator["shard_file"] != descriptor.file:
        raise PersonaSuiteEventStreamingError("locator shard file differs")
    row_ordinal = locator["row_ordinal"]
    first_shard_row_ordinal = 1 + sum(
        value.rows for value in receipt.shards[:shard_ordinal]
    )
    if (
        type(row_ordinal) is not int
        or not first_shard_row_ordinal
        <= row_ordinal
        < first_shard_row_ordinal + descriptor.rows
    ):
        raise PersonaSuiteEventStreamingError("locator row ordinal is invalid")
    offset = locator["byte_offset"]
    length = locator["byte_length"]
    if (
        type(offset) is not int or type(length) is not int
        or offset < 0 or length < 1 or offset + length > descriptor.bytes
    ):
        raise PersonaSuiteEventStreamingError("locator byte range is invalid")
    parts = Path(descriptor.file).parts
    if len(parts) != 2 or parts[0] != stream_storage.SHARDS_DIRECTORY_NAME:
        raise PersonaSuiteEventStreamingError("locator descriptor path is invalid")
    root_fd = shards_fd = shard_fd = -1
    try:
        root_fd = os.open(
            artifact_root,
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
        )
        shards_fd = os.open(
            parts[0],
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
            dir_fd=root_fd,
        )
        before = os.stat(parts[1], dir_fd=shards_fd, follow_symlinks=False)
        shard_fd = os.open(
            parts[1],
            os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
            dir_fd=shards_fd,
        )
        opened = os.fstat(shard_fd)
        if (
            not storage.is_plain_regular_file_metadata(before)
            or not storage.is_plain_regular_file_metadata(opened)
            or before.st_nlink != 1 or opened.st_nlink != 1
            or (before.st_dev, before.st_ino, before.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
            or opened.st_size != descriptor.bytes
        ):
            raise PersonaSuiteEventStreamingError("locator shard identity differs")
        if offset > 0 and os.pread(shard_fd, 1, offset - 1) != b"\n":
            raise PersonaSuiteEventStreamingError(
                "locator byte offset is not a row boundary"
            )
        cursor = 0
        preceding_rows = 0
        while cursor < offset:
            requested = min(64 * 1024, offset - cursor)
            chunk = os.pread(shard_fd, requested, cursor)
            if len(chunk) != requested:
                raise PersonaSuiteEventStreamingError(
                    "cannot verify locator row ordinal"
                )
            preceding_rows += chunk.count(b"\n")
            cursor += len(chunk)
        if row_ordinal != first_shard_row_ordinal + preceding_rows:
            raise PersonaSuiteEventStreamingError(
                "locator row ordinal/offset binding differs"
            )
        raw = os.pread(shard_fd, length, offset)
        after = os.fstat(shard_fd)
        if (
            len(raw) != length
            or (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
        ):
            raise PersonaSuiteEventStreamingError("locator pread was unstable")
    except OSError as error:
        raise PersonaSuiteEventStreamingError("cannot safely pread locator") from error
    finally:
        for descriptor_fd in (shard_fd, shards_fd, root_fd):
            if descriptor_fd >= 0:
                os.close(descriptor_fd)
    if (
        not raw.endswith(b"\n")
        or hashlib.sha256(raw).hexdigest() != locator["stored_row_sha256"]
    ):
        raise PersonaSuiteEventStreamingError("locator row digest differs")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=lambda value: (_ for _ in ()).throw(
                PersonaSuiteEventStreamingError("pread row contains a float")
            ),
            parse_constant=lambda value: (_ for _ in ()).throw(
                PersonaSuiteEventStreamingError("pread row contains a constant")
            ),
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaSuiteEventStreamingError("locator row is invalid JSON") from error
    if type(value) is not dict or stream_storage.canonical_json_bytes(value) + b"\n" != raw:
        raise PersonaSuiteEventStreamingError("locator row is not canonical JSON")
    return value


def pread_scheduled_item(person_artifact_root, suite_locator):
    """Resolve and semantically bind one locator from a verified suite artifact."""
    if type(suite_locator) is not dict or set(suite_locator) != {
        "schema", "schema_version", "suite_schedule_ordinal", "persona_id",
        "item_id", "kind", "planned_item_sha256", "prior_item_id",
        "target_locator",
    }:
        raise PersonaSuiteEventStreamingError("suite locator fields differ")
    persona_id = suite_locator["persona_id"]
    item_id = suite_locator["item_id"]
    kind = suite_locator["kind"]
    planned_sha256 = suite_locator["planned_item_sha256"]
    if (
        suite_locator["schema"] != SCHEDULE_LOCATOR_SCHEMA
        or suite_locator["schema_version"] != SCHEMA_VERSION
        or type(suite_locator["suite_schedule_ordinal"]) is not int
        or suite_locator["suite_schedule_ordinal"] < 1
        or persona_id not in _PERSONA_IDS
        or type(item_id) is not str
        or not item_id.startswith(f"{persona_id}-")
        or kind not in ("event", "boundary")
        or type(planned_sha256) is not str
        or len(planned_sha256) != 64
        or any(value not in "0123456789abcdef" for value in planned_sha256)
        or (
            suite_locator["prior_item_id"] is not None
            and (
                type(suite_locator["prior_item_id"]) is not str
                or not suite_locator["prior_item_id"]
            )
        )
    ):
        raise PersonaSuiteEventStreamingError("suite locator header differs")
    target_locator = suite_locator["target_locator"]
    if type(target_locator) is not dict or target_locator.get("kind") != kind:
        raise PersonaSuiteEventStreamingError("suite/target locator kind differs")
    value = _pread_target_locator(person_artifact_root, target_locator)
    id_field, hash_field = (
        ("event_id", "event_sha256")
        if kind == "event" else ("boundary_id", "boundary_sha256")
    )
    if value.get(id_field) != item_id or value.get(hash_field) != planned_sha256:
        raise PersonaSuiteEventStreamingError(
            "suite locator does not bind the resolved planned item"
        )
    unhashed = {key: item for key, item in value.items() if key != hash_field}
    if _digest(unhashed) != planned_sha256:
        raise PersonaSuiteEventStreamingError(
            "resolved planned item self-hash differs"
        )
    return value


def _projection_stream(summary: PersonaArtifactSummary):
    for row in stream_storage.iter_jsonl_artifact(
        summary.root / PERSON_SCHEDULE_DIRECTORY,
        limits=_PERSON_SCHEDULE_LIMITS,
        expected_envelope_sha256=summary.schedule_envelope_sha256,
    ):
        if type(row) is not dict or set(row) != {
            "schedule_item", "projection", "target_locator"
        }:
            raise PersonaSuiteEventStreamingError(
                "person projection stream row fields differ"
            )
        projection = dict(row["projection"])
        projection["target_locator"] = row["target_locator"]
        yield projection


def _projection_streams(summaries):
    return [
        (summary.persona_id, _projection_stream(summary))
        for summary in summaries
    ]


def _suite_schedule_rows(summaries):
    yield from suite_events.iter_numbered_suite_schedule(
        _projection_streams(summaries)
    )


def _suite_locator_rows(summaries):
    prior_item_id = None
    for ordinal, row in enumerate(
        suite_events.iter_merged_suite_projection(
            _projection_streams(summaries)
        ),
        start=1,
    ):
        item_id = row["item_id"]
        yield {
            "schema": SCHEDULE_LOCATOR_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "suite_schedule_ordinal": ordinal,
            "persona_id": row["persona_id"],
            "item_id": item_id,
            "kind": row["kind"],
            "planned_item_sha256": row["planned_item_sha256"],
            "prior_item_id": prior_item_id,
            "target_locator": row["target_locator"],
        }
        prior_item_id = item_id


def _schedule_totals(rows):
    totals = {
        "personas": 20,
        "events": 0,
        "boundaries": 0,
        "schedule_items": 0,
        "regular_events": 0,
        "index_auto_boundaries": 0,
        "purge_events": 0,
        "purged_commit_boundaries": 0,
        "index_noop_boundaries": 0,
    }
    seen_personas = set()
    for row in rows:
        totals["schedule_items"] += 1
        seen_personas.add(row["persona_id"])
        if row["kind"] == "event":
            totals["events"] += 1
            if row["phase"] == "regular_events":
                totals["regular_events"] += 1
            elif row["phase"] == "serialized_path_purges":
                totals["purge_events"] += 1
        else:
            totals["boundaries"] += 1
            if row["phase"] == "ordinary_auto_indexes":
                totals["index_auto_boundaries"] += 1
            elif row["phase"] == "serialized_path_purges":
                totals["purged_commit_boundaries"] += 1
            elif row["phase"] == "post_purge_noop_indexes":
                totals["index_noop_boundaries"] += 1
    if seen_personas != set(_PERSONA_IDS):
        raise PersonaSuiteEventStreamingError("suite schedule persona set differs")
    if totals["schedule_items"] != totals["events"] + totals["boundaries"]:
        raise PersonaSuiteEventStreamingError("suite schedule item arithmetic differs")
    return totals


def _mmr_root(bindings):
    peaks: list[tuple[int, str]] = []
    leaf_count = 0
    for leaf_count, binding in enumerate(bindings, start=1):
        digest = hashlib.sha256(
            b"\x00"
            + (leaf_count - 1).to_bytes(8, "big")
            + canonical_manifest.canonical_json_bytes(binding)
        ).hexdigest()
        height = 0
        while peaks and peaks[-1][0] == height:
            _left_height, left = peaks.pop()
            digest = hashlib.sha256(
                b"\x01"
                + (height + 1).to_bytes(4, "big")
                + bytes.fromhex(left)
                + bytes.fromhex(digest)
            ).hexdigest()
            height += 1
        peaks.append((height, digest))
    value = {
        "schema": MMR_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "domain": "kio.persona.streaming-suite-schedule-locator-mmr/v1",
        "leaf_count": leaf_count,
        "ordered_peaks": [
            {"height": height, "sha256": digest}
            for height, digest in peaks
        ],
    }
    value["root_sha256"] = _digest(value)
    return value


def _paired_schedule_bindings(schedule_root, locator_root, schedule_sha, locator_sha):
    schedules = stream_storage.iter_jsonl_artifact(
        schedule_root,
        limits=_SUITE_SCHEDULE_LIMITS,
        expected_envelope_sha256=schedule_sha,
    )
    locators = stream_storage.iter_jsonl_artifact(
        locator_root,
        limits=_SUITE_LOCATOR_LIMITS,
        expected_envelope_sha256=locator_sha,
    )
    for schedule, locator in zip_longest(schedules, locators):
        if schedule is None or locator is None:
            raise PersonaSuiteEventStreamingError(
                "suite schedule/locator row counts differ"
            )
        if (
            schedule["suite_schedule_ordinal"]
            != locator["suite_schedule_ordinal"]
            or schedule["item_id"] != locator["item_id"]
            or schedule["persona_id"] != locator["persona_id"]
            or schedule["planned_item_sha256"]
            != locator["planned_item_sha256"]
            or schedule["prior_item_id"] != locator["prior_item_id"]
        ):
            raise PersonaSuiteEventStreamingError(
                "suite schedule/locator semantic binding differs"
            )
        yield {"schedule": schedule, "locator": locator}


def _expected_suite_control_fields():
    return frozenset((
        "schema", "schema_version", "fixture_id", "profile", "status",
        "inputs", "outputs", "logical_manifest_static",
        "suite_capacity_receipt", "contracts",
    ))


def compose_suite_event_artifact(
    destination,
    profile,
    persona_artifact_roots,
    *,
    replay_ordinal=1,
    supervised_composer_peak_rss_bytes=None,
    declared_artifact_bytes=None,
    declared_workspace_bytes=None,
):
    """Compose twenty verified person artifacts with an O(20) merge."""
    suite_measurement_values = (
        supervised_composer_peak_rss_bytes,
        declared_artifact_bytes,
        declared_workspace_bytes,
    )
    if any(value is not None for value in suite_measurement_values) and not all(
        value is not None for value in suite_measurement_values
    ):
        raise PersonaSuiteEventStreamingError(
            "suite capacity measurements must be supplied as one complete set"
        )
    if profile != "full" and any(
        value is not None for value in suite_measurement_values
    ):
        raise PersonaSuiteEventStreamingError(
            "suite capacity measurements are only valid for the full profile"
        )
    if type(persona_artifact_roots) is not dict or set(persona_artifact_roots) != set(
        _PERSONA_IDS
    ):
        raise PersonaSuiteEventStreamingError(
            "suite composer requires an exact persona-id/root mapping"
        )
    summaries = []
    for persona_id in _PERSONA_IDS:
        summaries.append(verify_persona_event_artifact(
            persona_artifact_roots[persona_id], profile, persona_id
        ))
    root = Path(destination).absolute()
    _ensure_planning_root(root)
    try:
        schedule_result = stream_storage.publish_jsonl_artifact(
            root / SUITE_SCHEDULE_DIRECTORY,
            _suite_schedule_rows(summaries),
            limits=_SUITE_SCHEDULE_LIMITS,
        )
        locator_result = stream_storage.publish_jsonl_artifact(
            root / SUITE_LOCATORS_DIRECTORY,
            _suite_locator_rows(summaries),
            limits=_SUITE_LOCATOR_LIMITS,
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    schedule_receipt = schedule_result.artifact
    locator_receipt = locator_result.artifact

    schedule_sha256 = _canonical_array_sha256(
        stream_storage.iter_jsonl_artifact(
            root / SUITE_SCHEDULE_DIRECTORY,
            limits=_SUITE_SCHEDULE_LIMITS,
            expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
        )
    )
    locator_root_sha256 = _canonical_array_sha256(
        stream_storage.iter_jsonl_artifact(
            root / SUITE_LOCATORS_DIRECTORY,
            limits=_SUITE_LOCATOR_LIMITS,
            expected_envelope_sha256=locator_receipt.storage_envelope_sha256,
        )
    )
    totals = _schedule_totals(stream_storage.iter_jsonl_artifact(
        root / SUITE_SCHEDULE_DIRECTORY,
        limits=_SUITE_SCHEDULE_LIMITS,
        expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
    ))
    persona_inputs = [
        {
            "persona_id": value.persona_id,
            "persona_plan_sha256": value.persona_plan_sha256,
            "event_manifest_sha256": value.event_manifest_sha256,
            "events": value.events,
            "boundaries": value.boundaries,
            "schedule_items": value.schedule_items,
        }
        for value in summaries
    ]
    logical_static = suite_events.build_suite_manifest_static(
        profile=profile,
        persona_inputs=persona_inputs,
        totals=totals,
        schedule_sha256=schedule_sha256,
    )
    suite_manifest_sha256 = suite_events.streamed_suite_manifest_sha256(
        logical_static,
        stream_storage.iter_jsonl_artifact(
            root / SUITE_SCHEDULE_DIRECTORY,
            limits=_SUITE_SCHEDULE_LIMITS,
            expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
        ),
    )
    mmr = _mmr_root(_paired_schedule_bindings(
        root / SUITE_SCHEDULE_DIRECTORY,
        root / SUITE_LOCATORS_DIRECTORY,
        schedule_receipt.storage_envelope_sha256,
        locator_receipt.storage_envelope_sha256,
    ))

    suite_capacity_receipt = None
    worker_receipts = [value.worker_capacity_receipt for value in summaries]
    if profile == "full" and supervised_composer_peak_rss_bytes is not None:
        if not all(value is not None for value in worker_receipts):
            raise PersonaSuiteEventStreamingError(
                "a supervised full suite receipt requires all twenty worker receipts"
            )
        # The capacity receipt is a declared resource projection only.  The
        # separate formal-publication blocker remains authoritative.
        try:
            suite_manifest_bytes = _canonical_byte_length(
                suite_events.iter_canonical_suite_manifest_bytes(
                    logical_static,
                    stream_storage.iter_jsonl_artifact(
                        root / SUITE_SCHEDULE_DIRECTORY,
                        limits=_SUITE_SCHEDULE_LIMITS,
                        expected_envelope_sha256=(
                            schedule_receipt.storage_envelope_sha256
                        ),
                    ),
                )
            )
            suite_capacity_receipt = full_limits.build_suite_capacity_receipt(
                replay_ordinal=replay_ordinal,
                worker_receipts=worker_receipts,
                suite_event_manifest_sha256=suite_manifest_sha256,
                suite_schedule_sha256=schedule_sha256,
                schedule_locator_root_sha256=locator_root_sha256,
                schedule_mmr_root_sha256=mmr["root_sha256"],
                schedule_mmr_leaf_count=mmr["leaf_count"],
                suite_event_manifest_bytes=suite_manifest_bytes,
                suite_schedule_bytes=schedule_receipt.bytes,
                schedule_locator_bytes=locator_receipt.bytes,
                schedule_mmr_bytes=len(
                    canonical_manifest.canonical_json_bytes(mmr)
                ),
                max_suite_schedule_row_bytes=_artifact_max_row_bytes(
                    root / SUITE_SCHEDULE_DIRECTORY,
                    schedule_receipt,
                    _SUITE_SCHEDULE_LIMITS,
                ),
                max_locator_row_bytes=_artifact_max_row_bytes(
                    root / SUITE_LOCATORS_DIRECTORY,
                    locator_receipt,
                    _SUITE_LOCATOR_LIMITS,
                ),
                artifact_bytes=declared_artifact_bytes,
                workspace_bytes=declared_workspace_bytes,
                composer_peak_rss_bytes=supervised_composer_peak_rss_bytes,
            )
        except (TypeError, full_limits.FullScaleLimitsError) as error:
            raise PersonaSuiteEventStreamingError(str(error)) from error

    inputs = {
        "person_artifacts": [
            {
                "persona_id": value.persona_id,
                "control_envelope_sha256": value.control_envelope_sha256,
                "event_manifest_sha256": value.event_manifest_sha256,
            }
            for value in summaries
        ]
    }
    outputs = {
        "schedule_sha256": schedule_sha256,
        "suite_event_manifest_sha256": suite_manifest_sha256,
        "schedule_locator_root_sha256": locator_root_sha256,
        "schedule_mmr": mmr,
        "totals": totals,
        "artifacts": {
            "schedule": _artifact_projection(schedule_receipt),
            "locators": _artifact_projection(locator_receipt),
        },
        "content_binding_sha256": _digest({
            "domain": "kio.persona.streaming-event-suite-content/v1",
            "inputs": inputs,
            "schedule_sha256": schedule_sha256,
            "suite_event_manifest_sha256": suite_manifest_sha256,
            "schedule_locator_root_sha256": locator_root_sha256,
            "schedule_mmr_root_sha256": mmr["root_sha256"],
            "artifacts": {
                "schedule": _artifact_projection(schedule_receipt),
                "locators": _artifact_projection(locator_receipt),
            },
        }),
    }
    control = {
        "schema": SUITE_CONTROL_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "status": STATUS,
        "inputs": inputs,
        "outputs": outputs,
        "logical_manifest_static": logical_static,
        "suite_capacity_receipt": suite_capacity_receipt,
        "contracts": {
            "o20_projection_merge": True,
            "contains_all_twenty_full_manifest_objects": False,
            "contains_w1_w5_mutation": False,
            "planned_not_observed": True,
            "formal_publication_attested": False,
            "formal_publication_blocker": FORMAL_PUBLICATION_BLOCKER,
            "formal_publication_blockers": list(
                stream_storage.FORMAL_PUBLICATION_BLOCKERS
            ),
            "authorizes_history_execution": False,
        },
    }
    try:
        stream_storage.publish_jsonl_artifact(
            root / SUITE_CONTROL_DIRECTORY, [control], limits=_CONTROL_LIMITS
        )
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    return verify_suite_event_artifact(
        root, profile, persona_artifact_roots
    )


def _require_suite_control(control, profile):
    if type(control) is not dict or set(control) != _expected_suite_control_fields():
        raise PersonaSuiteEventStreamingError("suite control fields differ")
    if (
        control["schema"] != SUITE_CONTROL_SCHEMA
        or control["schema_version"] != SCHEMA_VERSION
        or control["fixture_id"] != spec.FIXTURE_ID
        or control["profile"] != profile
        or control["status"] != STATUS
    ):
        raise PersonaSuiteEventStreamingError("suite control header differs")
    expected_contracts = {
        "o20_projection_merge": True,
        "contains_all_twenty_full_manifest_objects": False,
        "contains_w1_w5_mutation": False,
        "planned_not_observed": True,
        "formal_publication_attested": False,
        "formal_publication_blocker": FORMAL_PUBLICATION_BLOCKER,
        "formal_publication_blockers": list(
            stream_storage.FORMAL_PUBLICATION_BLOCKERS
        ),
        "authorizes_history_execution": False,
    }
    if control["contracts"] != expected_contracts:
        raise PersonaSuiteEventStreamingError("suite control contracts differ")


def _require_exact_stream(actual_rows, expected_rows, label):
    for ordinal, (actual, expected) in enumerate(
        zip_longest(actual_rows, expected_rows), start=1
    ):
        if actual is None or expected is None:
            raise PersonaSuiteEventStreamingError(f"{label} row count differs")
        if not _same_canonical_json(actual, expected):
            raise PersonaSuiteEventStreamingError(
                f"{label} row {ordinal} differs from the canonical merge"
            )


def _suite_persona_inputs(summaries):
    return [
        {
            "persona_id": value.persona_id,
            "persona_plan_sha256": value.persona_plan_sha256,
            "event_manifest_sha256": value.event_manifest_sha256,
            "events": value.events,
            "boundaries": value.boundaries,
            "schedule_items": value.schedule_items,
        }
        for value in summaries
    ]


def _suite_control_inputs(summaries):
    return {
        "person_artifacts": [
            {
                "persona_id": value.persona_id,
                "control_envelope_sha256": value.control_envelope_sha256,
                "event_manifest_sha256": value.event_manifest_sha256,
            }
            for value in summaries
        ]
    }


def verify_suite_event_artifact(destination, profile, persona_artifact_roots):
    """Revalidate the persisted suite from bounded person projection streams."""
    if type(persona_artifact_roots) is not dict or set(persona_artifact_roots) != set(
        _PERSONA_IDS
    ):
        raise PersonaSuiteEventStreamingError(
            "suite verifier requires an exact persona-id/root mapping"
        )
    root = Path(destination).absolute()
    try:
        metadata = root.lstat()
    except OSError as error:
        raise PersonaSuiteEventStreamingError("suite artifact root is missing") from error
    if not storage.is_plain_directory_metadata(metadata) or root.is_symlink():
        raise PersonaSuiteEventStreamingError("suite artifact root is unsafe")
    if set(os.listdir(root)) != _SUITE_ENTRIES:
        raise PersonaSuiteEventStreamingError(
            "suite artifact root has an unexpected entry set"
        )

    try:
        control, control_receipt = _one_control_row(root / SUITE_CONTROL_DIRECTORY)
    except stream_storage.PersonaStreamingStorageError as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error
    _require_suite_control(control, profile)

    # Full manifests are deliberately discarded after each person verifier;
    # only these twenty bounded summaries survive into the merge.
    summaries = []
    for persona_id in _PERSONA_IDS:
        summaries.append(verify_persona_event_artifact(
            persona_artifact_roots[persona_id], profile, persona_id
        ))
    expected_inputs = _suite_control_inputs(summaries)
    if not _same_canonical_json(control["inputs"], expected_inputs):
        raise PersonaSuiteEventStreamingError("suite person input binding differs")

    outputs = control["outputs"]
    if type(outputs) is not dict or set(outputs) != {
        "schedule_sha256", "suite_event_manifest_sha256",
        "schedule_locator_root_sha256", "schedule_mmr", "totals",
        "artifacts", "content_binding_sha256",
    }:
        raise PersonaSuiteEventStreamingError("suite control outputs differ")
    artifacts = outputs["artifacts"]
    if type(artifacts) is not dict or set(artifacts) != {"schedule", "locators"}:
        raise PersonaSuiteEventStreamingError("suite artifact inventory differs")
    schedule_receipt = _receipt_for_control_artifact(
        root, SUITE_SCHEDULE_DIRECTORY,
        artifacts["schedule"], _SUITE_SCHEDULE_LIMITS,
    )
    locator_receipt = _receipt_for_control_artifact(
        root, SUITE_LOCATORS_DIRECTORY,
        artifacts["locators"], _SUITE_LOCATOR_LIMITS,
    )

    try:
        _require_exact_stream(
            stream_storage.iter_jsonl_artifact(
                root / SUITE_SCHEDULE_DIRECTORY,
                limits=_SUITE_SCHEDULE_LIMITS,
                expected_envelope_sha256=(
                    schedule_receipt.storage_envelope_sha256
                ),
            ),
            _suite_schedule_rows(summaries),
            "suite schedule",
        )
        _require_exact_stream(
            stream_storage.iter_jsonl_artifact(
                root / SUITE_LOCATORS_DIRECTORY,
                limits=_SUITE_LOCATOR_LIMITS,
                expected_envelope_sha256=(
                    locator_receipt.storage_envelope_sha256
                ),
            ),
            _suite_locator_rows(summaries),
            "suite locator",
        )
    except (
        stream_storage.PersonaStreamingStorageError,
        suite_events.SuiteEventManifestError,
    ) as error:
        raise PersonaSuiteEventStreamingError(str(error)) from error

    schedule_sha256 = _canonical_array_sha256(
        stream_storage.iter_jsonl_artifact(
            root / SUITE_SCHEDULE_DIRECTORY,
            limits=_SUITE_SCHEDULE_LIMITS,
            expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
        )
    )
    locator_root_sha256 = _canonical_array_sha256(
        stream_storage.iter_jsonl_artifact(
            root / SUITE_LOCATORS_DIRECTORY,
            limits=_SUITE_LOCATOR_LIMITS,
            expected_envelope_sha256=locator_receipt.storage_envelope_sha256,
        )
    )
    totals = _schedule_totals(stream_storage.iter_jsonl_artifact(
        root / SUITE_SCHEDULE_DIRECTORY,
        limits=_SUITE_SCHEDULE_LIMITS,
        expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
    ))
    logical_static = suite_events.build_suite_manifest_static(
        profile=profile,
        persona_inputs=_suite_persona_inputs(summaries),
        totals=totals,
        schedule_sha256=schedule_sha256,
    )
    suite_manifest_sha256 = suite_events.streamed_suite_manifest_sha256(
        logical_static,
        stream_storage.iter_jsonl_artifact(
            root / SUITE_SCHEDULE_DIRECTORY,
            limits=_SUITE_SCHEDULE_LIMITS,
            expected_envelope_sha256=schedule_receipt.storage_envelope_sha256,
        ),
    )
    mmr = _mmr_root(_paired_schedule_bindings(
        root / SUITE_SCHEDULE_DIRECTORY,
        root / SUITE_LOCATORS_DIRECTORY,
        schedule_receipt.storage_envelope_sha256,
        locator_receipt.storage_envelope_sha256,
    ))
    if not _same_canonical_json(control["logical_manifest_static"], logical_static):
        raise PersonaSuiteEventStreamingError("suite logical static manifest differs")
    if (
        outputs["schedule_sha256"] != schedule_sha256
        or outputs["suite_event_manifest_sha256"] != suite_manifest_sha256
        or outputs["schedule_locator_root_sha256"] != locator_root_sha256
        or not _same_canonical_json(outputs["schedule_mmr"], mmr)
        or not _same_canonical_json(outputs["totals"], totals)
    ):
        raise PersonaSuiteEventStreamingError("suite logical output binding differs")
    expected_content_binding = _digest({
        "domain": "kio.persona.streaming-event-suite-content/v1",
        "inputs": expected_inputs,
        "schedule_sha256": schedule_sha256,
        "suite_event_manifest_sha256": suite_manifest_sha256,
        "schedule_locator_root_sha256": locator_root_sha256,
        "schedule_mmr_root_sha256": mmr["root_sha256"],
        "artifacts": artifacts,
    })
    if outputs["content_binding_sha256"] != expected_content_binding:
        raise PersonaSuiteEventStreamingError("suite content binding differs")

    capacity_receipt = control["suite_capacity_receipt"]
    worker_receipts = [value.worker_capacity_receipt for value in summaries]
    if profile == "full" and capacity_receipt is not None:
        if any(value is None for value in worker_receipts):
            raise PersonaSuiteEventStreamingError(
                "suite capacity receipt is missing a worker receipt"
            )
        try:
            full_limits.validate_suite_capacity_receipt(
                capacity_receipt, worker_receipts=worker_receipts
            )
        except full_limits.FullScaleLimitsError as error:
            raise PersonaSuiteEventStreamingError(str(error)) from error
        suite_manifest_bytes = _canonical_byte_length(
            suite_events.iter_canonical_suite_manifest_bytes(
                logical_static,
                stream_storage.iter_jsonl_artifact(
                    root / SUITE_SCHEDULE_DIRECTORY,
                    limits=_SUITE_SCHEDULE_LIMITS,
                    expected_envelope_sha256=(
                        schedule_receipt.storage_envelope_sha256
                    ),
                ),
            )
        )
        capacity_outputs = capacity_receipt["outputs"]
        if (
            capacity_outputs["suite_event_manifest_sha256"]
            != suite_manifest_sha256
            or capacity_outputs["suite_schedule_sha256"] != schedule_sha256
            or capacity_outputs["schedule_locator_root_sha256"]
            != locator_root_sha256
            or capacity_outputs["schedule_mmr_root_sha256"] != mmr["root_sha256"]
            or capacity_outputs["schedule_mmr_leaf_count"] != mmr["leaf_count"]
            or capacity_outputs["suite_logical_file_bytes"] != {
                "event_manifest": suite_manifest_bytes,
                "schedule": schedule_receipt.bytes,
                "locator": locator_receipt.bytes,
                "mmr": len(canonical_manifest.canonical_json_bytes(mmr)),
            }
            or capacity_outputs["declared_max_suite_schedule_row_bytes"]
            != _artifact_max_row_bytes(
                root / SUITE_SCHEDULE_DIRECTORY,
                schedule_receipt,
                _SUITE_SCHEDULE_LIMITS,
            )
            or capacity_outputs["declared_max_locator_row_bytes"]
            != _artifact_max_row_bytes(
                root / SUITE_LOCATORS_DIRECTORY,
                locator_receipt,
                _SUITE_LOCATOR_LIMITS,
            )
        ):
            raise PersonaSuiteEventStreamingError("suite capacity binding differs")
    elif capacity_receipt is not None:
        raise PersonaSuiteEventStreamingError(
            "non-full artifact must not contain a full suite receipt"
        )

    return SuiteArtifactSummary(
        root=root,
        profile=profile,
        schedule_sha256=schedule_sha256,
        suite_event_manifest_sha256=suite_manifest_sha256,
        schedule_locator_root_sha256=locator_root_sha256,
        schedule_mmr_root_sha256=mmr["root_sha256"],
        schedule_items=totals["schedule_items"],
        control_envelope_sha256=control_receipt.storage_envelope_sha256,
    )
