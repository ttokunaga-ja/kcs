"""Canonical root-independent schedule for all persona event manifests.

The suite schedule is a thin immutable index over *supplied* per-person event
manifests and their exact canonical persona plans.  Before scheduling, it
calls the per-person canonical validator exactly once for every persona.  That
validator performs the sole canonical event rebuild; the suite then validates
the item inventory, records both complete input digests, and imposes one
deterministic cross-person execution order protected by one replay-root-wide
exclusive lock.

The schedule deliberately contains references rather than copies of events
and boundaries.  An executor must therefore receive the same per-person
manifests and persona plans whose digests are recorded in
``persona_event_manifests``.
"""

from __future__ import annotations

import hashlib
import heapq
import re

try:  # Package imports and direct ``python eval/...`` execution.
    from . import persona_event_manifest as persona_events
    from . import persona_fixture_spec as spec
    from . import persona_manifest as canonical_manifest
except ImportError:  # pragma: no cover - direct-script compatibility.
    import persona_event_manifest as persona_events
    import persona_fixture_spec as spec
    import persona_manifest as canonical_manifest


SUITE_EVENT_MANIFEST_SCHEMA = "kcs.persona.suite-event-manifest/v1"
SUITE_EVENT_MANIFEST_SCHEMA_VERSION = 1
SUITE_SCHEDULE_SCHEMA = "kcs.persona.suite-event-schedule/v1"
PLANNING_STATUS = "planned_not_observed"
WAVE_ORDER = ("W1", "W2", "W3", "W4", "W5")
PHASE_ORDER = (
    ("W1", "regular_events"),
    ("W1", "ordinary_auto_indexes"),
    ("W2", "regular_events"),
    ("W2", "ordinary_auto_indexes"),
    ("W3", "regular_events"),
    ("W3", "ordinary_auto_indexes"),
    ("W4", "regular_events"),
    ("W4", "ordinary_auto_indexes"),
    ("W5", "regular_events"),
    ("W5", "ordinary_auto_indexes"),
    ("W5", "serialized_path_purges"),
    ("W5", "post_purge_noop_indexes"),
)
_PHASE_ORDINAL = {
    value: ordinal for ordinal, value in enumerate(PHASE_ORDER)
}

_PROFILES = frozenset(("tiny", "pilot", "full"))
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_WINDOWS_ABSOLUTE_RE = re.compile(r"^[A-Za-z]:[\\/]")
_EXPECTED_PERSONA_IDS = tuple(persona["id"] for persona in spec.PERSONAS)
_EXPECTED_PERSONA_ID_SET = frozenset(_EXPECTED_PERSONA_IDS)
_PERSONA_ORDINAL = {
    persona_id: ordinal
    for ordinal, persona_id in enumerate(_EXPECTED_PERSONA_IDS)
}
_PERSONA_EVENT_MANIFEST_FIELDS = frozenset((
    "boundaries",
    "checkpoints",
    "contracts",
    "event_arithmetic",
    "events",
    "fixture_id",
    "inputs",
    "managed_event_state",
    "persona_id",
    "profile",
    "schedule",
    "schema",
    "schema_version",
    "status",
    "totals",
))

# These fields bind a plan to one host, replay, or filesystem root.  Merkle
# state-root fields such as ``managed_state_root_before_sha256`` are
# intentionally not forbidden: those are portable content digests, not root
# locators.
_ROOT_SPECIFIC_FIELDS = frozenset((
    "absolute_path",
    "absolute_paths",
    "absolute_root",
    "binary_path",
    "commit_oid",
    "commit_hash",
    "commit_sha",
    "corpus_root",
    "destination_root",
    "device_root",
    "filesystem_device",
    "fixture_root",
    "home",
    "home_path",
    "host",
    "hostname",
    "host_path",
    "machine_id",
    "mount_path",
    "mount_point",
    "output_root",
    "replay_id",
    "replay_root",
    "replay_root_path",
    "repository_head",
    "root",
    "root_binding_sha256",
    "root_id",
    "root_path",
    "scope_id",
    "source_root",
    "suite_root",
    "suite_root_path",
    "workspace_root",
    "working_directory",
    "cwd",
))


class SuiteEventManifestError(ValueError):
    """Raised when a suite schedule or supplied manifest is not canonical."""


def _digest(value):
    try:
        encoded = canonical_manifest.canonical_json_bytes(value)
    except (
        canonical_manifest.PersonaManifestError,
        TypeError,
        ValueError,
    ) as error:
        raise SuiteEventManifestError(str(error)) from error
    return hashlib.sha256(encoded).hexdigest()


def _same_canonical_json(actual, expected):
    if actual != expected:
        return False
    try:
        return (
            canonical_manifest.canonical_json_bytes(actual)
            == canonical_manifest.canonical_json_bytes(expected)
        )
    except (
        canonical_manifest.PersonaManifestError,
        TypeError,
        ValueError,
    ):
        return False


def _require_object(value, label):
    if type(value) is not dict:
        raise SuiteEventManifestError(f"{label} must be an object")
    return value


def _require_array(value, label):
    if type(value) is not list:
        raise SuiteEventManifestError(f"{label} must be an array")
    return value


def _require_nonempty_string(value, label):
    if type(value) is not str or not value:
        raise SuiteEventManifestError(f"{label} must be a non-empty string")
    return value


def _require_sha256(value, label):
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise SuiteEventManifestError(
            f"{label} must be a lowercase SHA-256 digest"
        )
    return value


def _is_absolute_path(value):
    return (
        value.startswith(("/", "~/", "\\", "file://"))
        or _WINDOWS_ABSOLUTE_RE.match(value) is not None
    )


def _is_root_specific_field(key):
    normalized = key.casefold().replace("-", "_")
    return (
        normalized in _ROOT_SPECIFIC_FIELDS
        or normalized.endswith("_root")
        or normalized.endswith("_absolute_path")
        or normalized.endswith("_commit_oid")
        or normalized.endswith("_cwd")
        or normalized.endswith("_hostname")
        or normalized.endswith("_host_path")
        or normalized.endswith("_mount_path")
        or normalized.endswith("_mount_point")
        or normalized.endswith("_root_path")
        or normalized.endswith("_working_directory")
    )


def _reject_root_specific(value, label="value"):
    """Reject execution-root bindings while allowing relative fixture paths."""
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key:
                raise SuiteEventManifestError(
                    f"{label} has a non-string or empty field"
                )
            if _is_root_specific_field(key):
                raise SuiteEventManifestError(
                    f"{label}.{key} is a root-specific field"
                )
            _reject_root_specific(item, f"{label}.{key}")
        return
    if type(value) in (list, tuple):
        for index, item in enumerate(value):
            _reject_root_specific(item, f"{label}[{index}]")
        return
    if type(value) is str and _is_absolute_path(value):
        raise SuiteEventManifestError(
            f"{label} contains an absolute path"
        )


def _item_inventory(manifest, persona_id):
    """Validate and project only the opaque fields needed for scheduling."""
    events = _require_array(manifest.get("events"), f"{persona_id}.events")
    boundaries = _require_array(
        manifest.get("boundaries"), f"{persona_id}.boundaries"
    )
    schedule = _require_array(
        manifest.get("schedule"), f"{persona_id}.schedule"
    )

    event_by_id = {}
    event_hash_by_id = {}
    for ordinal, event in enumerate(events):
        event = _require_object(event, f"{persona_id}.events[{ordinal}]")
        event_id = _require_nonempty_string(
            event.get("event_id"), f"{persona_id}.event_id"
        )
        if event_id in event_by_id:
            raise SuiteEventManifestError(
                f"{persona_id} repeats event id {event_id!r}"
            )
        if event.get("wave") not in WAVE_ORDER:
            raise SuiteEventManifestError(
                f"{persona_id} event has an invalid wave"
            )
        if event.get("execution_phase") not in ("regular", "purge_serial"):
            raise SuiteEventManifestError(
                f"{persona_id} event has an invalid execution phase"
            )
        event_hash = _require_sha256(
            event.get("event_sha256"),
            f"{persona_id}.{event_id}.event_sha256",
        )
        unhashed_event = {
            key: value
            for key, value in event.items()
            if key != "event_sha256"
        }
        if _digest(unhashed_event) != event_hash:
            raise SuiteEventManifestError(
                f"{persona_id} event self-hash differs: {event_id}"
            )
        event_hash_by_id[event_id] = event_hash
        event_by_id[event_id] = event

    boundary_by_id = {}
    boundary_hash_by_id = {}
    for ordinal, boundary in enumerate(boundaries):
        boundary = _require_object(
            boundary, f"{persona_id}.boundaries[{ordinal}]"
        )
        boundary_id = _require_nonempty_string(
            boundary.get("boundary_id"), f"{persona_id}.boundary_id"
        )
        if boundary_id in boundary_by_id:
            raise SuiteEventManifestError(
                f"{persona_id} repeats boundary id {boundary_id!r}"
            )
        if boundary.get("wave") not in WAVE_ORDER:
            raise SuiteEventManifestError(
                f"{persona_id} boundary has an invalid wave"
            )
        kind = boundary.get("kind")
        if kind not in ("index_auto", "purged_commit", "index_noop"):
            raise SuiteEventManifestError(
                f"{persona_id} boundary has an invalid kind"
            )
        if kind != "index_auto" and boundary["wave"] != "W5":
            raise SuiteEventManifestError(
                f"{persona_id} {kind} boundary must be in W5"
            )
        boundary_hash = _require_sha256(
            boundary.get("boundary_sha256"),
            f"{persona_id}.{boundary_id}.boundary_sha256",
        )
        unhashed_boundary = {
            key: value
            for key, value in boundary.items()
            if key != "boundary_sha256"
        }
        if _digest(unhashed_boundary) != boundary_hash:
            raise SuiteEventManifestError(
                f"{persona_id} boundary self-hash differs: {boundary_id}"
            )
        boundary_hash_by_id[boundary_id] = boundary_hash
        boundary_by_id[boundary_id] = boundary

    overlap = set(event_by_id) & set(boundary_by_id)
    if overlap:
        raise SuiteEventManifestError(
            f"{persona_id} event and boundary ids overlap"
        )
    all_ids = set(event_by_id) | set(boundary_by_id)
    schedule_ids = []
    schedule_by_id = {}
    prior_item_id = None
    for ordinal, item in enumerate(schedule, start=1):
        item = _require_object(item, f"{persona_id}.schedule[{ordinal - 1}]")
        item_id = _require_nonempty_string(
            item.get("item_id"), f"{persona_id}.schedule.item_id"
        )
        if item_id in schedule_by_id:
            raise SuiteEventManifestError(
                f"{persona_id} schedule repeats item id {item_id!r}"
            )
        if type(item.get("schedule_ordinal")) is not int or item[
            "schedule_ordinal"
        ] != ordinal:
            raise SuiteEventManifestError(
                f"{persona_id} schedule ordinal is not contiguous"
            )
        if item.get("prior_item_id") != prior_item_id:
            raise SuiteEventManifestError(
                f"{persona_id} schedule prior-item chain differs"
            )
        if item_id in event_by_id:
            expected_kind = "event"
            value = event_by_id[item_id]
            planned_hash = event_hash_by_id[item_id]
        elif item_id in boundary_by_id:
            expected_kind = "boundary"
            value = boundary_by_id[item_id]
            planned_hash = boundary_hash_by_id[item_id]
        else:
            raise SuiteEventManifestError(
                f"{persona_id} schedule references an unknown item"
            )
        if item.get("item_kind") != expected_kind:
            raise SuiteEventManifestError(
                f"{persona_id} schedule item kind differs from inventory"
            )
        if item.get("wave") != value["wave"]:
            raise SuiteEventManifestError(
                f"{persona_id} schedule wave differs from inventory"
            )
        if (
            type(item.get("logical_tick")) is not int
            or item["logical_tick"] != ordinal
            or item.get("logical_time") != f"T{ordinal:08d}"
            or value.get("logical_tick") != ordinal
            or value.get("logical_time") != f"T{ordinal:08d}"
        ):
            raise SuiteEventManifestError(
                f"{persona_id} schedule/item logical order differs"
            )
        if expected_kind == "event":
            expected_phase = (
                "regular_events"
                if value["execution_phase"] == "regular"
                else "serialized_path_purges"
            )
        else:
            expected_phase = {
                "index_auto": "ordinary_auto_indexes",
                "purged_commit": "serialized_path_purges",
                "index_noop": "post_purge_noop_indexes",
            }[value["kind"]]
        if item.get("phase") != expected_phase:
            raise SuiteEventManifestError(
                f"{persona_id} schedule phase differs from inventory"
            )
        if item.get("planned_item_sha256") != planned_hash:
            raise SuiteEventManifestError(
                f"{persona_id} schedule planned item hash differs"
            )
        schedule_ids.append(item_id)
        schedule_by_id[item_id] = item
        prior_item_id = item_id

    if set(schedule_ids) != all_ids or len(schedule_ids) != len(all_ids):
        raise SuiteEventManifestError(
            f"{persona_id} schedule is not the exact item inventory"
        )
    totals = _require_object(
        manifest.get("totals"), f"{persona_id}.totals"
    )
    for field, expected_count in (
        ("events", len(events)),
        ("boundaries", len(boundaries)),
        ("schedule_items", len(schedule)),
    ):
        if (
            type(totals.get(field)) is not int
            or totals[field] != expected_count
        ):
            raise SuiteEventManifestError(
                f"{persona_id} declared item totals differ from inventory"
            )

    regular_by_wave = {wave: [] for wave in WAVE_ORDER}
    auto_by_wave = {wave: [] for wave in WAVE_ORDER}
    purge_events = []
    noop_boundaries = []
    purged_boundaries = []
    for item in schedule:
        item_id = item["item_id"]
        if item_id in event_by_id:
            event = event_by_id[item_id]
            if event["execution_phase"] == "regular":
                regular_by_wave[event["wave"]].append(item_id)
            else:
                if event["wave"] != "W5":
                    raise SuiteEventManifestError(
                        f"{persona_id} purge event must be in W5"
                    )
                purge_events.append(item_id)
        else:
            boundary = boundary_by_id[item_id]
            if boundary["kind"] == "index_auto":
                auto_by_wave[boundary["wave"]].append(item_id)
            elif boundary["kind"] == "purged_commit":
                purged_boundaries.append(item_id)
            else:
                noop_boundaries.append(item_id)

    purged_by_event = {}
    for boundary_id in purged_boundaries:
        boundary = boundary_by_id[boundary_id]
        covered = boundary.get("covered_event_ids")
        if type(covered) is not list or len(covered) != 1:
            raise SuiteEventManifestError(
                f"{persona_id} purged commit must cover exactly one event"
            )
        event_id = covered[0]
        if event_id not in purge_events or event_id in purged_by_event:
            raise SuiteEventManifestError(
                f"{persona_id} purged commit coverage differs"
            )
        purged_by_event[event_id] = boundary_id
    if set(purged_by_event) != set(purge_events):
        raise SuiteEventManifestError(
            f"{persona_id} purge events and commits are not one-to-one"
        )

    purge_pairs = []
    seen_source_ids = set()
    for event_id in purge_events:
        event = event_by_id[event_id]
        relation = _require_object(
            event.get("relation"), f"{persona_id}.{event_id}.relation"
        )
        source_ids = relation.get("source_ids")
        if (
            type(source_ids) is not list
            or len(source_ids) != 1
            or type(source_ids[0]) is not str
            or not source_ids[0]
        ):
            raise SuiteEventManifestError(
                f"{persona_id} purge event must identify one source"
            )
        source_id = source_ids[0]
        if source_id in seen_source_ids:
            raise SuiteEventManifestError(
                f"{persona_id} repeats a purge source id"
            )
        seen_source_ids.add(source_id)
        purge_pairs.append(
            (source_id, event_id, purged_by_event[event_id])
        )

    purge_event_rows = {
        event_id: (source_id, 0)
        for source_id, event_id, _boundary_id in purge_pairs
    }
    purge_boundary_rows = {
        boundary_id: (source_id, 1)
        for source_id, _event_id, boundary_id in purge_pairs
    }
    schedule_projection = []
    for item in schedule:
        item_id = item["item_id"]
        purge_sort = purge_event_rows.get(item_id)
        if purge_sort is None:
            purge_sort = purge_boundary_rows.get(item_id)
        schedule_projection.append({
            "persona_id": persona_id,
            "persona_ordinal": _PERSONA_ORDINAL[persona_id],
            "persona_schedule_ordinal": item["schedule_ordinal"],
            "wave": item["wave"],
            "phase": item["phase"],
            "item_id": item_id,
            "kind": item["item_kind"],
            "planned_item_sha256": item["planned_item_sha256"],
            "purge_source_id": purge_sort[0] if purge_sort else None,
            "purge_pair_ordinal": purge_sort[1] if purge_sort else None,
        })

    item_hashes = dict(event_hash_by_id)
    item_hashes.update(boundary_hash_by_id)
    return {
        "event_by_id": event_by_id,
        "boundary_by_id": boundary_by_id,
        "item_hashes": item_hashes,
        "all_item_ids": all_ids,
        "regular_by_wave": regular_by_wave,
        "auto_by_wave": auto_by_wave,
        "purge_pairs": purge_pairs,
        "noop_boundaries": noop_boundaries,
        "schedule_projection": schedule_projection,
    }


_SCHEDULE_PROJECTION_FIELDS = frozenset((
    "persona_id",
    "persona_ordinal",
    "persona_schedule_ordinal",
    "wave",
    "phase",
    "item_id",
    "kind",
    "planned_item_sha256",
    "purge_source_id",
    "purge_pair_ordinal",
))


def suite_schedule_sort_key(row):
    """Return the sole canonical cross-person ordering key.

    Storage-layer fields such as a target locator may be present in ``row``;
    they deliberately do not affect the logical schedule order or digest.
    """
    row = _require_object(row, "suite schedule projection row")
    missing = _SCHEDULE_PROJECTION_FIELDS - set(row)
    if missing:
        raise SuiteEventManifestError(
            f"suite schedule projection row is missing fields: {sorted(missing)}"
        )
    persona_id = row["persona_id"]
    if persona_id not in _EXPECTED_PERSONA_ID_SET:
        raise SuiteEventManifestError("schedule projection has an unknown persona")
    persona_ordinal = row["persona_ordinal"]
    if (
        type(persona_ordinal) is not int
        or persona_ordinal != _PERSONA_ORDINAL[persona_id]
    ):
        raise SuiteEventManifestError("schedule projection persona ordinal differs")
    phase_key = (row["wave"], row["phase"])
    if phase_key not in _PHASE_ORDINAL:
        raise SuiteEventManifestError("schedule projection phase is invalid")
    schedule_ordinal = row["persona_schedule_ordinal"]
    if type(schedule_ordinal) is not int or schedule_ordinal < 1:
        raise SuiteEventManifestError("persona schedule ordinal is invalid")
    item_id = _require_nonempty_string(row["item_id"], "projection item id")
    if not item_id.startswith(f"{persona_id}-"):
        raise SuiteEventManifestError("projection item id is outside its persona")
    if row["kind"] not in ("event", "boundary"):
        raise SuiteEventManifestError("schedule projection kind is invalid")
    _require_sha256(row["planned_item_sha256"], "projection item sha256")

    if phase_key == ("W5", "serialized_path_purges"):
        source_id = _require_nonempty_string(
            row["purge_source_id"], "purge source id"
        )
        pair_ordinal = row["purge_pair_ordinal"]
        if type(pair_ordinal) is not int or pair_ordinal not in (0, 1):
            raise SuiteEventManifestError("purge pair ordinal is invalid")
        if (pair_ordinal == 0) != (row["kind"] == "event"):
            raise SuiteEventManifestError("purge pair kind/order differs")
        local_key = (source_id, pair_ordinal)
    else:
        if row["purge_source_id"] is not None or row["purge_pair_ordinal"] is not None:
            raise SuiteEventManifestError(
                "non-purge schedule projection carries a purge sort key"
            )
        local_key = (schedule_ordinal,)
    return (
        _PHASE_ORDINAL[phase_key],
        persona_ordinal,
        local_key,
    )


def projection_phase_ranges(projection_rows):
    """Validate one person's compact projection and return 12 exact ranges."""
    if type(projection_rows) not in (list, tuple):
        raise SuiteEventManifestError("projection rows must be an array")
    if not projection_rows:
        raise SuiteEventManifestError("projection rows must not be empty")
    persona_id = projection_rows[0].get("persona_id")
    prior_key = None
    counts = {phase: 0 for phase in PHASE_ORDER}
    for expected_ordinal, row in enumerate(projection_rows, start=1):
        if row.get("persona_id") != persona_id:
            raise SuiteEventManifestError("projection mixes personas")
        if row.get("persona_schedule_ordinal") != expected_ordinal:
            raise SuiteEventManifestError(
                "projection persona schedule ordinal is not contiguous"
            )
        key = suite_schedule_sort_key(row)
        if prior_key is not None and key <= prior_key:
            raise SuiteEventManifestError("projection ordering is not strict")
        prior_key = key
        counts[(row["wave"], row["phase"])] += 1
    ranges = []
    ordinal = 1
    for wave, phase in PHASE_ORDER:
        rows = counts[(wave, phase)]
        ranges.append({
            "wave": wave,
            "phase": phase,
            "start_ordinal": ordinal,
            "end_ordinal": ordinal + rows - 1,
            "rows": rows,
        })
        ordinal += rows
    return ranges


def _checked_projection_stream(persona_id, rows):
    prior_key = None
    expected_ordinal = 1
    for row in rows:
        if row.get("persona_id") != persona_id:
            raise SuiteEventManifestError("projection stream persona differs")
        if row.get("persona_schedule_ordinal") != expected_ordinal:
            raise SuiteEventManifestError(
                "projection stream persona ordinal is not contiguous"
            )
        key = suite_schedule_sort_key(row)
        if prior_key is not None and key <= prior_key:
            raise SuiteEventManifestError("projection stream is not strictly ordered")
        prior_key = key
        expected_ordinal += 1
        yield row


def iter_merged_suite_projection(persona_projection_streams):
    """Merge twenty canonical person streams while retaining only one row each."""
    if type(persona_projection_streams) not in (list, tuple):
        raise SuiteEventManifestError("persona projection streams must be an array")
    if len(persona_projection_streams) != len(_EXPECTED_PERSONA_IDS):
        raise SuiteEventManifestError("suite requires exactly 20 projection streams")
    streams = {}
    for value in persona_projection_streams:
        if type(value) not in (list, tuple) or len(value) != 2:
            raise SuiteEventManifestError("projection stream entry is invalid")
        persona_id, rows = value
        if persona_id not in _EXPECTED_PERSONA_ID_SET or persona_id in streams:
            raise SuiteEventManifestError("projection stream identity is invalid")
        streams[persona_id] = _checked_projection_stream(persona_id, rows)
    if set(streams) != _EXPECTED_PERSONA_ID_SET:
        raise SuiteEventManifestError("projection stream inventory is incomplete")

    yield from heapq.merge(
        *(streams[persona_id] for persona_id in _EXPECTED_PERSONA_IDS),
        key=suite_schedule_sort_key,
    )


def iter_numbered_suite_schedule(persona_projection_streams):
    """Number the canonical O(20) merge as the exact legacy suite schedule."""
    prior_item_id = None
    for ordinal, row in enumerate(
        iter_merged_suite_projection(persona_projection_streams), start=1
    ):
        item_id = row["item_id"]
        yield {
            "suite_schedule_ordinal": ordinal,
            "wave": row["wave"],
            "phase": row["phase"],
            "item_id": item_id,
            "kind": row["kind"],
            "persona_id": row["persona_id"],
            "planned_item_sha256": row["planned_item_sha256"],
            "prior_item_id": prior_item_id,
        }
        prior_item_id = item_id


def _normalize_persona_plans(persona_plans, profile):
    if type(persona_plans) not in (list, tuple):
        raise SuiteEventManifestError("persona plans must be an array")
    if profile not in _PROFILES:
        raise SuiteEventManifestError(f"unknown persona profile: {profile!r}")
    if len(persona_plans) != len(_EXPECTED_PERSONA_IDS):
        raise SuiteEventManifestError(
            "suite requires exactly 20 persona plans"
        )

    records = {}
    for ordinal, supplied in enumerate(persona_plans):
        plan = _require_object(supplied, f"persona_plans[{ordinal}]")
        # Validate immutable JSON and root independence before handing the
        # plan to the per-person canonical rebuild.
        plan_sha256 = _digest(plan)
        _reject_root_specific(plan, f"persona_plans[{ordinal}]")
        persona_id = plan.get("persona_id")
        if persona_id not in _EXPECTED_PERSONA_ID_SET:
            raise SuiteEventManifestError(
                f"unknown persona plan identity: {persona_id!r}"
            )
        if persona_id in records:
            raise SuiteEventManifestError(
                f"duplicate persona plan: {persona_id}"
            )
        records[persona_id] = {
            "plan": plan,
            "plan_sha256": plan_sha256,
        }

    if frozenset(records) != _EXPECTED_PERSONA_ID_SET:
        raise SuiteEventManifestError(
            "suite persona plan inventory is incomplete"
        )
    return records


def validate_and_project_persona_event_manifest(
    event_manifest, persona_plan, profile
):
    """Canonically validate one person and return the scheduling projection.

    This is the bounded worker boundary used by the streaming composer.  It
    intentionally validates exactly one full manifest against exactly one
    canonical event-plan projection and returns only the compact scheduling
    inventory once that validation succeeds.
    """
    if profile not in _PROFILES:
        raise SuiteEventManifestError(f"unknown persona profile: {profile!r}")
    manifest = _require_object(event_manifest, "persona event manifest")
    plan = _require_object(persona_plan, "persona plan")
    persona_id = manifest.get("persona_id")
    if (
        persona_id not in _EXPECTED_PERSONA_ID_SET
        or plan.get("persona_id") != persona_id
    ):
        raise SuiteEventManifestError("persona event manifest/plan identity differs")
    _reject_root_specific(manifest, "persona_event_manifest")
    _reject_root_specific(plan, "persona_plan")
    manifest_sha256 = _digest(manifest)
    plan_sha256 = _digest(plan)
    try:
        persona_events.validate_event_manifest(manifest, plan, profile)
    except persona_events.EventManifestError as error:
        raise SuiteEventManifestError(
            f"{persona_id} event manifest/persona plan is not canonical: {error}"
        ) from error
    inventory = _item_inventory(manifest, persona_id)
    projection = inventory["schedule_projection"]
    projection_phase_ranges(projection)
    return {
        "persona_id": persona_id,
        "manifest": manifest,
        "manifest_sha256": manifest_sha256,
        "plan_sha256": plan_sha256,
        **inventory,
    }


def _normalize_persona_manifests(event_manifests, persona_plans, profile):
    if type(event_manifests) not in (list, tuple):
        raise SuiteEventManifestError(
            "persona event manifests must be an array"
        )
    if profile not in _PROFILES:
        raise SuiteEventManifestError(f"unknown persona profile: {profile!r}")
    if len(event_manifests) != len(_EXPECTED_PERSONA_IDS):
        raise SuiteEventManifestError(
            "suite requires exactly 20 persona event manifests"
        )
    plans_by_persona = _normalize_persona_plans(persona_plans, profile)

    records = []
    seen_persona_ids = set()
    seen_item_ids = set()
    for ordinal, supplied in enumerate(event_manifests):
        manifest = _require_object(
            supplied, f"persona_event_manifests[{ordinal}]"
        )
        # Canonical encoding rejects floats, non-string keys, exotic types,
        # excessive depth, and other values that cannot be immutable JSON.
        manifest_sha256 = _digest(manifest)
        _reject_root_specific(
            manifest, f"persona_event_manifests[{ordinal}]"
        )
        if set(manifest) != _PERSONA_EVENT_MANIFEST_FIELDS:
            raise SuiteEventManifestError(
                "persona event manifest top-level fields differ"
            )
        if (
            manifest.get("schema") != persona_events.EVENT_MANIFEST_SCHEMA
            or manifest.get("schema_version")
            != persona_events.EVENT_MANIFEST_SCHEMA_VERSION
        ):
            raise SuiteEventManifestError(
                "persona event manifest schema differs"
            )
        if manifest.get("fixture_id") != spec.FIXTURE_ID:
            raise SuiteEventManifestError(
                "persona event manifest fixture differs"
            )
        if manifest.get("profile") != profile:
            raise SuiteEventManifestError(
                "persona event manifest profile differs"
            )
        persona_id = manifest.get("persona_id")
        if persona_id not in _EXPECTED_PERSONA_ID_SET:
            raise SuiteEventManifestError(
                f"unknown persona event manifest identity: {persona_id!r}"
            )
        if persona_id in seen_persona_ids:
            raise SuiteEventManifestError(
                f"duplicate persona event manifest: {persona_id}"
            )
        if manifest.get("status") != PLANNING_STATUS:
            raise SuiteEventManifestError(
                f"{persona_id} is not a planned event manifest"
            )
        contracts = _require_object(
            manifest.get("contracts"), f"{persona_id}.contracts"
        )
        if (
            contracts.get("root_independent") is not True
            or contracts.get("contains_absolute_paths") is not False
            or contracts.get("contains_observed_commit_hashes") is not False
        ):
            raise SuiteEventManifestError(
                f"{persona_id} is not declared root-independent"
            )
        plan_record = plans_by_persona[persona_id]
        projected = validate_and_project_persona_event_manifest(
            manifest, plan_record["plan"], profile
        )
        inventory = {
            key: value
            for key, value in projected.items()
            if key not in {
                "persona_id", "manifest", "manifest_sha256", "plan_sha256"
            }
        }
        overlap = seen_item_ids & inventory["all_item_ids"]
        if overlap:
            raise SuiteEventManifestError(
                "suite item ids are not globally unique"
            )
        seen_item_ids.update(inventory["all_item_ids"])
        seen_persona_ids.add(persona_id)
        records.append({
            "persona_id": persona_id,
            "manifest": manifest,
            "manifest_sha256": projected["manifest_sha256"],
            "plan_sha256": plan_record["plan_sha256"],
            **inventory,
        })

    if seen_persona_ids != _EXPECTED_PERSONA_ID_SET:
        raise SuiteEventManifestError(
            "suite persona manifest inventory is incomplete"
        )
    records.sort(key=lambda value: _PERSONA_ORDINAL[value["persona_id"]])
    return records


def canonical_array_sha256(rows):
    """Hash a canonical JSON array without materializing it."""
    digest = hashlib.sha256()
    digest.update(b"[")
    first = True
    for row in rows:
        if not first:
            digest.update(b",")
        digest.update(canonical_manifest.canonical_json_bytes(row))
        first = False
    digest.update(b"]")
    return digest.hexdigest()


def build_suite_manifest_static(
    *, profile, persona_inputs, totals, schedule_sha256
):
    """Build every legacy suite field except the potentially large schedule."""
    if profile not in _PROFILES:
        raise SuiteEventManifestError(f"unknown persona profile: {profile!r}")
    if type(persona_inputs) is not list or len(persona_inputs) != 20:
        raise SuiteEventManifestError("suite requires exactly 20 persona inputs")
    if [row.get("persona_id") for row in persona_inputs] != list(
        _EXPECTED_PERSONA_IDS
    ):
        raise SuiteEventManifestError("suite persona input order differs")
    for row in persona_inputs:
        if type(row) is not dict or set(row) != {
            "persona_id", "persona_plan_sha256", "event_manifest_sha256",
            "events", "boundaries", "schedule_items",
        }:
            raise SuiteEventManifestError("suite persona input fields differ")
        _require_sha256(row["persona_plan_sha256"], "persona plan sha256")
        _require_sha256(row["event_manifest_sha256"], "event manifest sha256")
        for field in ("events", "boundaries", "schedule_items"):
            if type(row[field]) is not int or row[field] < 0:
                raise SuiteEventManifestError("suite persona input count is invalid")
    if type(totals) is not dict or set(totals) != {
        "personas", "events", "boundaries", "schedule_items",
        "regular_events", "index_auto_boundaries", "purge_events",
        "purged_commit_boundaries", "index_noop_boundaries",
    }:
        raise SuiteEventManifestError("suite totals fields differ")
    if any(type(value) is not int or value < 0 for value in totals.values()):
        raise SuiteEventManifestError("suite total is invalid")
    _require_sha256(schedule_sha256, "suite schedule sha256")
    return {
        "schema": SUITE_EVENT_MANIFEST_SCHEMA,
        "schema_version": SUITE_EVENT_MANIFEST_SCHEMA_VERSION,
        "schedule_schema": SUITE_SCHEDULE_SCHEMA,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "status": PLANNING_STATUS,
        "contracts": {
            "root_independent": True,
            "planned_not_observed": True,
            "contains_absolute_paths": False,
            "contains_root_specific_fields": False,
            "exactly_twenty_persona_manifests": True,
            "exactly_twenty_canonical_persona_plans": True,
            "per_person_canonical_validation_completed_before_scheduling": True,
            "suite_schedule_is_single_execution_dependency_chain": True,
            "w1_w4_all_regular_before_all_index_auto": True,
            "w5_regular_auto_purge_pairs_noop_order": True,
        },
        "execution_lock": {
            "kind": "exclusive_replay_root_lock",
            "required_lock_count": 1,
            "coverage": "entire_suite_schedule",
            "acquire_before_first_item": True,
            "release_after_last_item": True,
        },
        "persona_event_manifests": persona_inputs,
        "schedule_sha256": schedule_sha256,
        "totals": totals,
    }


def iter_canonical_suite_manifest_bytes(static_manifest, schedule_rows):
    """Yield exact legacy canonical bytes with the schedule streamed in place."""
    if type(static_manifest) is not dict or "schedule" in static_manifest:
        raise SuiteEventManifestError("suite static manifest is invalid")
    keys = sorted(tuple(static_manifest) + ("schedule",))
    yield b"{"
    for index, key in enumerate(keys):
        if index:
            yield b","
        yield canonical_manifest.canonical_json_bytes(key)
        yield b":"
        if key == "schedule":
            yield b"["
            first = True
            for row in schedule_rows:
                if not first:
                    yield b","
                yield canonical_manifest.canonical_json_bytes(row)
                first = False
            yield b"]"
        else:
            yield canonical_manifest.canonical_json_bytes(static_manifest[key])
    yield b"}"


def streamed_suite_manifest_sha256(static_manifest, schedule_rows):
    digest = hashlib.sha256()
    for piece in iter_canonical_suite_manifest_bytes(
        static_manifest, schedule_rows
    ):
        digest.update(piece)
    return digest.hexdigest()


def _build_suite_event_manifest(event_manifests, persona_plans, profile):
    records = _normalize_persona_manifests(
        event_manifests, persona_plans, profile
    )
    schedule = list(iter_numbered_suite_schedule([
        (record["persona_id"], record["schedule_projection"])
        for record in records
    ]))
    expected_item_count = sum(
        len(record["all_item_ids"]) for record in records
    )
    if len(schedule) != expected_item_count:
        raise SuiteEventManifestError(
            "suite schedule is not the exact global item inventory"
        )

    purge_pair_count = sum(
        len(record["purge_pairs"]) for record in records
    )

    persona_inputs = [
        {
            "persona_id": record["persona_id"],
            "persona_plan_sha256": record["plan_sha256"],
            "event_manifest_sha256": record["manifest_sha256"],
            "events": len(record["event_by_id"]),
            "boundaries": len(record["boundary_by_id"]),
            "schedule_items": len(record["all_item_ids"]),
        }
        for record in records
    ]
    totals = {
        "personas": len(records),
        "events": sum(len(record["event_by_id"]) for record in records),
        "boundaries": sum(
            len(record["boundary_by_id"]) for record in records
        ),
        "schedule_items": len(schedule),
        "regular_events": sum(
            len(record["regular_by_wave"][wave])
            for record in records for wave in WAVE_ORDER
        ),
        "index_auto_boundaries": sum(
            len(record["auto_by_wave"][wave])
            for record in records for wave in WAVE_ORDER
        ),
        "purge_events": purge_pair_count,
        "purged_commit_boundaries": purge_pair_count,
        "index_noop_boundaries": sum(
            len(record["noop_boundaries"]) for record in records
        ),
    }
    result = build_suite_manifest_static(
        profile=profile,
        persona_inputs=persona_inputs,
        totals=totals,
        schedule_sha256=canonical_array_sha256(schedule),
    )
    result["schedule"] = schedule
    return result


def build_suite_event_manifest(event_manifests, persona_plans, profile):
    """Build from exactly 20 canonical manifests and matching persona plans."""
    return _build_suite_event_manifest(
        event_manifests, persona_plans, profile
    )


def validate_suite_event_manifest(
    suite_event_manifest, event_manifests, persona_plans, profile
):
    """Reject anything other than the exact canonical-input expansion."""
    if type(suite_event_manifest) is not dict:
        raise SuiteEventManifestError(
            "suite event manifest must be an object"
        )
    _reject_root_specific(suite_event_manifest, "suite_event_manifest")
    expected = _build_suite_event_manifest(
        event_manifests, persona_plans, profile
    )
    if not _same_canonical_json(suite_event_manifest, expected):
        raise SuiteEventManifestError(
            "suite event manifest differs from canonical expansion"
        )
    return True


def suite_event_manifest_sha256(suite_event_manifest):
    """Return the stable digest of one canonical suite event manifest."""
    if type(suite_event_manifest) is not dict:
        raise SuiteEventManifestError(
            "suite event manifest must be an object"
        )
    _reject_root_specific(suite_event_manifest, "suite_event_manifest")
    return _digest(suite_event_manifest)
