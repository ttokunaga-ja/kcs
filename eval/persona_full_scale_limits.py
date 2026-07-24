"""Canonical count and resource limits for the planned full persona suite.

This module is deliberately an arithmetic/capacity oracle.  It expands one
canonical persona W0 plan at a time and builds the corresponding canonical
P/X/Y/N allocation, but it never builds a full event manifest and never
observes KIO.  Worker/suite values accepted here are caller-declared schema
projections only.  Artifact readback plus supervisor ``wait4`` evidence remains
mandatory before any formal capacity gate; these projections cannot authorize
a physical write or stand in for a KIO chunk/history attestation.
"""

from __future__ import annotations

import copy
from functools import lru_cache
import hashlib
import json
import re

try:  # Package imports and direct ``python eval/...`` execution.
    from . import generate_persona_corpus as generator
    from . import persona_fixture_spec as spec
    from . import persona_history_allocation as history
    from . import persona_manifest as canonical_manifest
    from . import persona_structural_allocation as structural
except ImportError:  # pragma: no cover - direct-script compatibility.
    import generate_persona_corpus as generator
    import persona_fixture_spec as spec
    import persona_history_allocation as history
    import persona_manifest as canonical_manifest
    import persona_structural_allocation as structural


FULL_SCALE_LIMITS_SCHEMA = "kio.persona.full-scale-limits/v1"
FULL_SCALE_LIMITS_SCHEMA_VERSION = 1
WORKER_RECEIPT_SCHEMA = "kio.persona.full-scale-worker-declared-projection/v1"
WORKER_RECEIPT_SCHEMA_VERSION = 1
SUITE_RECEIPT_SCHEMA = "kio.persona.full-scale-suite-declared-projection/v1"
SUITE_RECEIPT_SCHEMA_VERSION = 1

PROFILE = "full"
PLANNING_STATUS = "planned_capacity_only_not_kio_attestation"
DECLARED_PROJECTION_STATUS = (
    "caller_declared_capacity_projection_not_formal_measurement"
)
DECLARED_MEASUREMENT_STATUS = (
    "caller_declared_requires_supervisor_wait4_attestation"
)
MIB = 1024 * 1024
GIB = 1024 * MIB

MAX_PERSONA_PLAN_BYTES = 8 * MIB
MAX_SOURCES_PER_PERSONA = 16_000
MAX_SCOPES_PER_PERSONA = 20
MAX_MANAGED_INITIAL_MATERIALIZATIONS_PER_PERSONA = 2_500
MAX_LOGICAL_EVENT_BYTES_PER_PERSONA = 64 * MIB
MAX_EVENT_ROWS_PER_PERSONA = 6_000
MAX_BOUNDARY_ROWS_PER_PERSONA = 600
MAX_SCHEDULE_ROWS_PER_PERSONA = 6_600
MAX_CANONICAL_JSON_DEPTH = 16
MAX_EVENT_ROW_BYTES = 64 * 1024
MAX_BOUNDARY_ROW_BYTES = 64 * 1024
MAX_INITIAL_MATERIALIZATION_ROW_BYTES = 64 * 1024
MAX_SCHEDULE_ROW_BYTES = 4 * 1024
MAX_LOCATOR_ROW_BYTES = 4 * 1024
MAX_JSONL_SHARD_ROWS = 512
MAX_JSONL_SHARD_BYTES = 32 * MIB
MAX_SUITE_EVENT_ROWS = 45_000
MAX_SUITE_BOUNDARY_ROWS = 5_500
MAX_SUITE_SCHEDULE_ROWS = 50_000
MAX_SUITE_LOGICAL_FILE_BYTES = 64 * MIB
MAX_ARTIFACT_BYTES = 2 * GIB
MAX_WORKSPACE_BYTES = 4 * GIB
MAX_WORKER_RSS_BYTES = 384 * MIB
MAX_COMPOSER_RSS_BYTES = 128 * MIB
MAX_PROCESS_TREE_RSS_BYTES = 512 * MIB
MAX_CONCURRENT_PERSONA_WORKERS = 1

PERSONAS_PER_REPLAY = 20
SCOPES_PER_PERSONA = MAX_SCOPES_PER_PERSONA
REPLAY_COUNT = 3
STRUCTURAL_EVENTS_PER_PERSONA = 30
ORDINARY_INDEX_BOUNDARIES_PER_PERSONA = 100
POST_PURGE_NOOP_BOUNDARIES_PER_PERSONA = 20

FROZEN_PERSONA_COHORT_SOURCE_COUNTS = {
    "p01": {"P": 301, "X": 752, "Y": 451, "N": 301},
    "p02": {"P": 326, "X": 815, "Y": 489, "N": 328},
    "p03": {"P": 166, "X": 414, "Y": 249, "N": 166},
    "p04": {"P": 188, "X": 469, "Y": 282, "N": 188},
    "p05": {"P": 108, "X": 270, "Y": 162, "N": 108},
    "p06": {"P": 100, "X": 250, "Y": 150, "N": 100},
    "p07": {"P": 124, "X": 308, "Y": 185, "N": 124},
    "p08": {"P": 86, "X": 215, "Y": 129, "N": 86},
    "p09": {"P": 103, "X": 256, "Y": 154, "N": 103},
    "p10": {"P": 69, "X": 174, "Y": 104, "N": 69},
    "p11": {"P": 87, "X": 218, "Y": 131, "N": 87},
    "p12": {"P": 243, "X": 607, "Y": 366, "N": 243},
    "p13": {"P": 95, "X": 237, "Y": 142, "N": 95},
    "p14": {"P": 69, "X": 172, "Y": 103, "N": 69},
    "p15": {"P": 88, "X": 220, "Y": 132, "N": 88},
    "p16": {"P": 110, "X": 274, "Y": 164, "N": 110},
    "p17": {"P": 82, "X": 207, "Y": 124, "N": 82},
    "p18": {"P": 165, "X": 413, "Y": 248, "N": 165},
    "p19": {"P": 114, "X": 284, "Y": 171, "N": 114},
    "p20": {"P": 151, "X": 376, "Y": 226, "N": 151},
}

FROZEN_PER_REPLAY_COUNTS = {
    "cohort_sources": {"P": 2_775, "X": 6_931, "Y": 4_162, "N": 2_777},
    "events": 43_596,
    "boundaries": 5_175,
    "schedule_items": 48_771,
}

FROZEN_ALL_REPLAY_COUNTS = {
    "events": 130_788,
    "boundaries": 15_525,
    "schedule_items": 146_313,
}

_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_PERSONA_IDS = tuple(persona["id"] for persona in spec.PERSONAS)
_SHARD_KINDS = ("events", "boundaries", "schedule")
_PHASE_ORDER = (
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


class FullScaleLimitsError(ValueError):
    """Raised when full-scale arithmetic, limits, or receipts drift."""


def _digest(value):
    try:
        encoded = canonical_manifest.canonical_json_bytes(value)
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError) as error:
        raise FullScaleLimitsError(str(error)) from error
    return hashlib.sha256(encoded).hexdigest()


def _exact_fields(value, fields, label):
    if type(value) is not dict:
        raise FullScaleLimitsError(f"{label} must be an object")
    if set(value) != set(fields):
        missing = sorted(set(fields) - set(value))
        extra = sorted(set(value) - set(fields))
        raise FullScaleLimitsError(
            f"{label} has an invalid field set (missing={missing}, extra={extra})"
        )
    return value


def _plain_int(value, label, *, minimum=0, maximum=2**63 - 1):
    if type(value) is not int or not minimum <= value <= maximum:
        raise FullScaleLimitsError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _sha256(value, label):
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise FullScaleLimitsError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _canonical_round_trip(value, label):
    try:
        encoded = canonical_manifest.canonical_json_bytes(value)
        decoded = json.loads(encoded.decode("utf-8"))
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError) as error:
        raise FullScaleLimitsError(f"{label} is not canonical JSON") from error
    if decoded != value:
        raise FullScaleLimitsError(f"{label} is not a canonical JSON value")
    return encoded


def _same_canonical_json(actual, expected):
    """Compare values without Python's bool/int or tuple/list coercions."""
    if actual != expected:
        return False
    try:
        return (
            canonical_manifest.canonical_json_bytes(actual)
            == canonical_manifest.canonical_json_bytes(expected)
        )
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError):
        return False


def _limits():
    return {
        "persona_plan_bytes": MAX_PERSONA_PLAN_BYTES,
        "sources_per_persona": MAX_SOURCES_PER_PERSONA,
        "scopes_per_persona": MAX_SCOPES_PER_PERSONA,
        "managed_initial_materializations_per_persona": (
            MAX_MANAGED_INITIAL_MATERIALIZATIONS_PER_PERSONA
        ),
        "logical_event_bytes_per_persona": MAX_LOGICAL_EVENT_BYTES_PER_PERSONA,
        "event_rows_per_persona": MAX_EVENT_ROWS_PER_PERSONA,
        "boundary_rows_per_persona": MAX_BOUNDARY_ROWS_PER_PERSONA,
        "schedule_rows_per_persona": MAX_SCHEDULE_ROWS_PER_PERSONA,
        "canonical_json_depth": MAX_CANONICAL_JSON_DEPTH,
        "event_row_bytes": MAX_EVENT_ROW_BYTES,
        "boundary_row_bytes": MAX_BOUNDARY_ROW_BYTES,
        "initial_materialization_row_bytes": (
            MAX_INITIAL_MATERIALIZATION_ROW_BYTES
        ),
        "schedule_row_bytes": MAX_SCHEDULE_ROW_BYTES,
        "locator_row_bytes": MAX_LOCATOR_ROW_BYTES,
        "jsonl_shard_rows": MAX_JSONL_SHARD_ROWS,
        "jsonl_shard_bytes": MAX_JSONL_SHARD_BYTES,
        "suite_event_rows": MAX_SUITE_EVENT_ROWS,
        "suite_boundary_rows": MAX_SUITE_BOUNDARY_ROWS,
        "suite_schedule_rows": MAX_SUITE_SCHEDULE_ROWS,
        "suite_logical_file_bytes": MAX_SUITE_LOGICAL_FILE_BYTES,
        "artifact_bytes": MAX_ARTIFACT_BYTES,
        "workspace_bytes": MAX_WORKSPACE_BYTES,
        "worker_peak_rss_bytes": MAX_WORKER_RSS_BYTES,
        "composer_peak_rss_bytes": MAX_COMPOSER_RSS_BYTES,
        "process_tree_peak_rss_bytes": MAX_PROCESS_TREE_RSS_BYTES,
        "concurrent_persona_workers": MAX_CONCURRENT_PERSONA_WORKERS,
    }


def _phase_row_counts(history_plan, structural_plan):
    """Derive schedule phases from canonical bounded allocation records."""
    waves = history_plan["waves"]
    structural_counts = structural_plan["event_counts_by_wave"]
    structural_scopes = structural_plan[
        "structural_index_scope_keys_by_wave"
    ]
    affected_scopes = {
        "W1": waves["W1"]["affected_scope_keys"],
        "W2": [],
        "W3": waves["W3"]["affected_scope_keys"],
        "W4": waves["W4"]["affected_scope_keys"],
        "W5": waves["W5"]["affected_scope_keys"],
    }
    history_regular = {
        "W1": len(waves["W1"]["edit_source_ids"]),
        "W2": 0,
        "W3": len(waves["W3"]["major_edit_source_ids"]),
        "W4": len(waves["W4"]["delete_source_ids"]),
        "W5": (
            len(waves["W5"]["correct_source_ids"])
            + len(waves["W5"]["replacement_sources"])
        ),
    }
    counts = []
    for wave in ("W1", "W2", "W3", "W4", "W5"):
        counts.extend((
            history_regular[wave] + structural_counts[wave],
            len(set(affected_scopes[wave]) | set(structural_scopes[wave])),
        ))
    counts.extend((
        2 * len(waves["W5"]["purge_source_ids"]),
        len(waves["W5"]["index_noop_scope_keys"]),
    ))
    return tuple(counts)


def _phase_ranges(history_plan, structural_plan):
    counts = _phase_row_counts(history_plan, structural_plan)
    result = []
    ordinal = 1
    for (wave, phase), rows in zip(_PHASE_ORDER, counts):
        result.append({
            "wave": wave,
            "phase": phase,
            "start_ordinal": ordinal,
            "end_ordinal": ordinal + rows - 1,
            "rows": rows,
        })
        ordinal += rows
    return result


def _managed_initial_materialization_count(history_plan, structural_plan):
    source_ids = {
        source_id
        for value in history_plan["strata"].values()
        for source_id in value["source_ids"]
    }
    anchors = structural_plan["anchors"]
    source_ids.update(
        value["source_id"] for value in anchors["rename_u_sources"]
    )
    source_ids.update({
        anchors["raw_traveler"]["source_id"],
        anchors["near_png_parent"]["source_id"],
        anchors["derive_png_parent"]["source_id"],
    })
    return len(source_ids)


def _person_counts(cohorts, history_plan, structural_plan):
    phase_rows = _phase_row_counts(history_plan, structural_plan)
    regular_events = sum(
        rows
        for (_wave, phase), rows in zip(_PHASE_ORDER, phase_rows)
        if phase == "regular_events"
    )
    purge_events = len(history_plan["waves"]["W5"]["purge_source_ids"])
    structural_events = structural_plan["totals"]["events"]
    history_events = regular_events - structural_events + purge_events
    formula_history_events = (
        3 * cohorts["P"] + 3 * cohorts["X"]
        + 2 * cohorts["Y"] + 2 * cohorts["N"]
    )
    if history_events != formula_history_events:
        raise FullScaleLimitsError("history allocation event arithmetic drifted")
    events = regular_events + purge_events
    ordinary_boundaries = sum(
        rows
        for (_wave, phase), rows in zip(_PHASE_ORDER, phase_rows)
        if phase == "ordinary_auto_indexes"
    )
    purged_boundaries = len(history_plan["waves"]["W5"]["purge_source_ids"])
    noop_boundaries = phase_rows[-1]
    boundaries = ordinary_boundaries + purged_boundaries + noop_boundaries
    schedule_items = sum(phase_rows)
    if schedule_items != events + boundaries:
        raise FullScaleLimitsError("allocation schedule arithmetic drifted")
    return {
        "history_events": history_events,
        "structural_events": structural_events,
        "events": events,
        "ordinary_index_boundaries": ordinary_boundaries,
        "purged_commit_boundaries": purged_boundaries,
        "post_purge_noop_boundaries": noop_boundaries,
        "boundaries": boundaries,
        "schedule_items": schedule_items,
        "logical_rows": events + boundaries + schedule_items,
    }


def _build_full_scale_limits_uncached():
    """Recompute the frozen oracle without constructing event manifests."""
    if (
        len(_PERSONA_IDS) != PERSONAS_PER_REPLAY
        or spec.REPLAY_COUNT != REPLAY_COUNT
        or generator.MAX_PERSONA_PLAN_BYTES != MAX_PERSONA_PLAN_BYTES
        or generator.MAX_PERSONA_PLAN_SOURCES != MAX_SOURCES_PER_PERSONA
        or generator.PERSONA_PLAN_SCOPE_COUNT != MAX_SCOPES_PER_PERSONA
        or structural.FULL_EVENT_COUNTS
        != {"W1": 3, "W2": 21, "W3": 3, "W4": 2, "W5": 1}
    ):
        raise FullScaleLimitsError("upstream full-scale constants drifted")

    people = []
    cohort_totals = {name: 0 for name in ("P", "X", "Y", "N")}
    total_events = total_boundaries = total_schedule = 0
    maximum_plan_bytes = 0
    for persona_id in _PERSONA_IDS:
        try:
            generation_plan = generator.build_persona_generation_plan(
                PROFILE, persona_id
            )
            event_plan = generator.persona_event_plan_projection(
                generation_plan,
                expected_profile=PROFILE,
                expected_persona_id=persona_id,
            )
            generation_bytes = len(generator.canonical_file_bytes(generation_plan))
            history_plan = history.build_history_allocation(event_plan, PROFILE)
            structural_plan = structural.build_structural_allocation(
                event_plan, PROFILE
            )
            structural.validate_structural_allocation(
                structural_plan, event_plan, PROFILE
            )
        except (
            generator.PersonaGenerationError,
            history.HistoryAllocationError,
            structural.StructuralAllocationError,
            canonical_manifest.PersonaManifestError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise FullScaleLimitsError(str(error)) from error
        if generation_bytes > MAX_PERSONA_PLAN_BYTES:
            raise FullScaleLimitsError(f"{persona_id} plan exceeds 8 MiB")
        maximum_plan_bytes = max(maximum_plan_bytes, generation_bytes)
        scope_count = len(event_plan["scopes"])
        source_count = sum(
            len(scope["sources"]) for scope in event_plan["scopes"]
        )
        managed_initials = _managed_initial_materialization_count(
            history_plan, structural_plan
        )
        if (
            scope_count != MAX_SCOPES_PER_PERSONA
            or source_count > MAX_SOURCES_PER_PERSONA
            or managed_initials
            > MAX_MANAGED_INITIAL_MATERIALIZATIONS_PER_PERSONA
        ):
            raise FullScaleLimitsError(
                f"{persona_id} plan cardinalities exceed formal caps"
            )

        cohorts = {
            name: history_plan["strata"][name]["source_count"]
            for name in ("P", "X", "Y", "N")
        }
        if cohorts != FROZEN_PERSONA_COHORT_SOURCE_COUNTS[persona_id]:
            raise FullScaleLimitsError(
                f"{persona_id} P/X/Y/N source counts drifted"
            )
        for name, value in cohorts.items():
            cohort_totals[name] += value
        for name in cohorts:
            if history_plan["strata"][name]["scope_count"] != SCOPES_PER_PERSONA:
                raise FullScaleLimitsError(
                    f"{persona_id} {name} no longer covers twenty scopes"
                )

        counts = _person_counts(cohorts, history_plan, structural_plan)
        if (
            counts["events"] > MAX_EVENT_ROWS_PER_PERSONA
            or counts["boundaries"] > MAX_BOUNDARY_ROWS_PER_PERSONA
            or counts["schedule_items"] > MAX_SCHEDULE_ROWS_PER_PERSONA
            or counts["structural_events"] != STRUCTURAL_EVENTS_PER_PERSONA
            or counts["ordinary_index_boundaries"]
            != ORDINARY_INDEX_BOUNDARIES_PER_PERSONA
            or counts["post_purge_noop_boundaries"]
            != POST_PURGE_NOOP_BOUNDARIES_PER_PERSONA
        ):
            raise FullScaleLimitsError(f"{persona_id} row counts exceed caps")
        phases = _phase_ranges(history_plan, structural_plan)
        if phases[-1]["end_ordinal"] != counts["schedule_items"]:
            raise FullScaleLimitsError(f"{persona_id} phase arithmetic drifted")
        total_events += counts["events"]
        total_boundaries += counts["boundaries"]
        total_schedule += counts["schedule_items"]
        people.append({
            "persona_id": persona_id,
            "persona_generation_plan_sha256": _digest(generation_plan),
            "persona_event_plan_sha256": _digest(event_plan),
            "history_allocation_sha256": _digest(history_plan),
            "structural_allocation_sha256": _digest(structural_plan),
            "persona_generation_plan_file_bytes": generation_bytes,
            "scope_count": scope_count,
            "w0_physical_sources": source_count,
            "managed_initial_materializations": managed_initials,
            "current_contract_chunks": history_plan["current_contract_chunks"],
            "final_history_only_contract_chunks": history_plan["checkpoints"][
                "W5"
            ]["history_only"],
            "cohort_source_counts": cohorts,
            "cohort_chunk_targets": {
                name: history_plan["strata"][name]["target_chunks"]
                for name in ("P", "X", "Y", "N")
            },
            "counts": counts,
            "phase_ranges": phases,
        })

    per_replay = {
        "personas": len(people),
        "cohort_sources": cohort_totals,
        "events": total_events,
        "boundaries": total_boundaries,
        "schedule_items": total_schedule,
        "logical_rows": total_events + total_boundaries + total_schedule,
        "maximum_persona_generation_plan_file_bytes": maximum_plan_bytes,
    }
    for key, expected in FROZEN_PER_REPLAY_COUNTS.items():
        if per_replay[key] != expected:
            raise FullScaleLimitsError(f"full per-replay {key} drifted")
    if (
        per_replay["events"] > MAX_SUITE_EVENT_ROWS
        or per_replay["boundaries"] > MAX_SUITE_BOUNDARY_ROWS
        or per_replay["schedule_items"] > MAX_SUITE_SCHEDULE_ROWS
    ):
        raise FullScaleLimitsError("full suite row counts exceed formal caps")
    all_replays = {
        "replays": REPLAY_COUNT,
        "events": total_events * REPLAY_COUNT,
        "boundaries": total_boundaries * REPLAY_COUNT,
        "schedule_items": total_schedule * REPLAY_COUNT,
        "logical_rows": per_replay["logical_rows"] * REPLAY_COUNT,
    }
    for key, expected in FROZEN_ALL_REPLAY_COUNTS.items():
        if all_replays[key] != expected:
            raise FullScaleLimitsError(f"full all-replay {key} drifted")
    result = {
        "schema": FULL_SCALE_LIMITS_SCHEMA,
        "schema_version": FULL_SCALE_LIMITS_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": PROFILE,
        "status": PLANNING_STATUS,
        "contracts": {
            "planned_counts_only": True,
            "builds_full_event_manifests": False,
            "phase_counts_derived_from_canonical_allocations": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        },
        "derivation": {
            "event_formula": "3P+3X+2Y+2N+30",
            "boundary_formula": "P+120",
            "schedule_formula": "events+boundaries",
            "structural_events_per_persona": STRUCTURAL_EVENTS_PER_PERSONA,
            "ordinary_index_boundaries_per_persona": (
                ORDINARY_INDEX_BOUNDARIES_PER_PERSONA
            ),
            "post_purge_noop_boundaries_per_persona": (
                POST_PURGE_NOOP_BOUNDARIES_PER_PERSONA
            ),
        },
        "limits": _limits(),
        "personas": people,
        "per_replay": per_replay,
        "all_replays": all_replays,
    }
    _canonical_round_trip(result, "full-scale limits")
    return result


@lru_cache(maxsize=1)
def _canonical_full_scale_limits():
    return _build_full_scale_limits_uncached()


def build_full_scale_limits():
    """Return the canonical full count/limit oracle as a detached value."""
    return copy.deepcopy(_canonical_full_scale_limits())


def build_full_scale_oracle():
    """Compatibility spelling for callers that treat limits as an oracle."""
    return build_full_scale_limits()


def validate_full_scale_limits(value):
    """Require exact equality with this process's immutable canonical oracle."""
    if type(value) is not dict:
        raise FullScaleLimitsError("full-scale limits must be an object")
    _canonical_round_trip(value, "full-scale limits")
    expected = _canonical_full_scale_limits()
    if value != expected or canonical_manifest.canonical_json_bytes(value) != (
        canonical_manifest.canonical_json_bytes(expected)
    ):
        raise FullScaleLimitsError("full-scale limits differ from the canonical oracle")
    return True


def full_scale_limits_sha256(value=None):
    value = build_full_scale_limits() if value is None else value
    validate_full_scale_limits(value)
    return _digest(value)


def _require_oracle(value):
    oracle = build_full_scale_limits() if value is None else value
    validate_full_scale_limits(oracle)
    return oracle


def _person_record(oracle, persona_id):
    if type(persona_id) is not str or persona_id not in _PERSONA_IDS:
        raise FullScaleLimitsError("receipt has an unknown persona id")
    return next(row for row in oracle["personas"] if row["persona_id"] == persona_id)


def _validate_shards(shards, expected_counts):
    if type(shards) is not list:
        raise FullScaleLimitsError("worker shards must be an array")
    maximum_shards = sum(expected_counts[kind] for kind in _SHARD_KINDS)
    if not 3 <= len(shards) <= maximum_shards:
        raise FullScaleLimitsError("worker shard count is outside its row bound")
    rows_by_kind = {kind: 0 for kind in _SHARD_KINDS}
    expected_ordinal = {kind: 1 for kind in _SHARD_KINDS}
    seen_sha256 = set()
    last_kind_index = 0
    total_bytes = 0
    normalized = []
    for index, shard in enumerate(shards):
        _exact_fields(shard, (
            "kind", "ordinal", "sha256", "bytes", "rows",
            "declared_max_row_bytes", "close_reason",
        ), f"shards[{index}]")
        kind = shard["kind"]
        if type(kind) is not str or kind not in _SHARD_KINDS:
            raise FullScaleLimitsError("worker shard has an invalid kind")
        kind_index = _SHARD_KINDS.index(kind)
        if kind_index < last_kind_index:
            raise FullScaleLimitsError("worker shards are not in canonical kind order")
        last_kind_index = kind_index
        ordinal = _plain_int(shard["ordinal"], "shard ordinal", minimum=1)
        if ordinal != expected_ordinal[kind]:
            raise FullScaleLimitsError("worker shard ordinals are not contiguous")
        expected_ordinal[kind] += 1
        digest = _sha256(shard["sha256"], "shard sha256")
        if digest in seen_sha256:
            raise FullScaleLimitsError("worker shard digests must be unique")
        seen_sha256.add(digest)
        shard_bytes = _plain_int(
            shard["bytes"], "shard bytes", minimum=1,
            maximum=MAX_JSONL_SHARD_BYTES,
        )
        rows = _plain_int(
            shard["rows"], "shard rows", minimum=1,
            maximum=MAX_JSONL_SHARD_ROWS,
        )
        row_cap = {
            "events": MAX_EVENT_ROW_BYTES,
            "boundaries": MAX_BOUNDARY_ROW_BYTES,
            "schedule": MAX_SCHEDULE_ROW_BYTES,
        }[kind]
        declared_max_row_bytes = _plain_int(
            shard["declared_max_row_bytes"], "declared max row bytes",
            minimum=1, maximum=row_cap,
        )
        if not rows <= shard_bytes <= rows * declared_max_row_bytes:
            raise FullScaleLimitsError(
                "worker shard bytes differ from its declared row bound"
            )
        close_reason = shard["close_reason"]
        if type(close_reason) is not str or close_reason not in (
            "row_limit", "final"
        ):
            raise FullScaleLimitsError("worker shard close reason is invalid")
        rows_by_kind[kind] += rows
        total_bytes += shard_bytes
        normalized.append({
            "kind": kind,
            "rows": rows,
            "bytes": shard_bytes,
            "declared_max_row_bytes": declared_max_row_bytes,
            "close_reason": close_reason,
        })
    for index, shard in enumerate(normalized):
        is_last_for_kind = (
            index == len(normalized) - 1
            or normalized[index + 1]["kind"] != shard["kind"]
        )
        if is_last_for_kind:
            if shard["close_reason"] != "final":
                raise FullScaleLimitsError(
                    "the last shard of each kind must be final"
                )
        elif (
            shard["close_reason"] != "row_limit"
            or shard["rows"] != MAX_JSONL_SHARD_ROWS
        ):
            raise FullScaleLimitsError(
                "non-final shards must close exactly at the row limit"
            )
    if rows_by_kind != expected_counts:
        raise FullScaleLimitsError("worker shard row arithmetic differs from oracle")
    if total_bytes > MAX_LOGICAL_EVENT_BYTES_PER_PERSONA:
        raise FullScaleLimitsError("worker logical event bytes exceed 64 MiB")
    return {
        "rows_by_kind": rows_by_kind,
        "total_bytes": total_bytes,
        "shard_count": len(shards),
        "shard_index_sha256": _digest(shards),
    }


def build_worker_capacity_receipt(
    *, persona_id, event_manifest_sha256, event_projection_sha256, shards,
    max_json_depth, max_initial_materialization_row_bytes, peak_rss_bytes,
    child_exit_code, child_terminating_signal, oracle=None,
):
    """Build a declared worker projection, never a measured/formal receipt."""
    oracle = _require_oracle(oracle)
    person = _person_record(oracle, persona_id)
    expected_counts = {
        "events": person["counts"]["events"],
        "boundaries": person["counts"]["boundaries"],
        "schedule": person["counts"]["schedule_items"],
    }
    shard_summary = _validate_shards(shards, expected_counts)
    receipt = {
        "schema": WORKER_RECEIPT_SCHEMA,
        "schema_version": WORKER_RECEIPT_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": PROFILE,
        "status": DECLARED_PROJECTION_STATUS,
        "persona_id": persona_id,
        "limits_oracle_sha256": full_scale_limits_sha256(oracle),
        "inputs": {
            "persona_generation_plan_sha256": person[
                "persona_generation_plan_sha256"
            ],
            "persona_event_plan_sha256": person["persona_event_plan_sha256"],
            "history_allocation_sha256": person["history_allocation_sha256"],
            "structural_allocation_sha256": person[
                "structural_allocation_sha256"
            ],
        },
        "outputs": {
            "event_manifest_sha256": _sha256(
                event_manifest_sha256, "event manifest sha256"
            ),
            "event_projection_sha256": _sha256(
                event_projection_sha256, "event projection sha256"
            ),
            "shard_index_sha256": shard_summary["shard_index_sha256"],
            "shards": copy.deepcopy(shards),
            "logical_event_bytes": shard_summary["total_bytes"],
            "max_json_depth": _plain_int(
                max_json_depth, "max JSON depth", minimum=1,
                maximum=MAX_CANONICAL_JSON_DEPTH,
            ),
            "counts": copy.deepcopy(expected_counts),
            "plan_cardinalities": {
                "sources": person["w0_physical_sources"],
                "scopes": person["scope_count"],
                "managed_initial_materializations": person[
                    "managed_initial_materializations"
                ],
            },
            "declared_max_initial_materialization_row_bytes": _plain_int(
                max_initial_materialization_row_bytes,
                "declared max initial materialization row bytes",
                minimum=1,
                maximum=MAX_INITIAL_MATERIALIZATION_ROW_BYTES,
            ),
            "phase_ranges": copy.deepcopy(person["phase_ranges"]),
        },
        "process": {
            "measurement_status": DECLARED_MEASUREMENT_STATUS,
            "declared_child_exit_code": _plain_int(
                child_exit_code, "child exit code", minimum=0, maximum=255
            ),
            "declared_child_terminating_signal": _plain_int(
                child_terminating_signal, "child terminating signal",
                minimum=0, maximum=255,
            ),
            "declared_peak_rss_bytes": _plain_int(
                peak_rss_bytes, "worker peak RSS", minimum=1,
                maximum=MAX_WORKER_RSS_BYTES,
            ),
            "declared_concurrent_persona_workers": (
                MAX_CONCURRENT_PERSONA_WORKERS
            ),
        },
        "limits": {
            key: oracle["limits"][key]
            for key in (
                "persona_plan_bytes",
                "sources_per_persona",
                "scopes_per_persona",
                "managed_initial_materializations_per_persona",
                "logical_event_bytes_per_persona",
                "event_rows_per_persona",
                "boundary_rows_per_persona",
                "schedule_rows_per_persona",
                "canonical_json_depth",
                "event_row_bytes",
                "boundary_row_bytes",
                "initial_materialization_row_bytes",
                "schedule_row_bytes",
                "jsonl_shard_rows",
                "jsonl_shard_bytes",
                "worker_peak_rss_bytes",
                "concurrent_persona_workers",
            )
        },
        "contracts": {
            "declared_projection_only": True,
            "artifact_readback_required": True,
            "supervisor_wait4_required": True,
            "formal_capacity_gate_satisfied": False,
            "planned_counts_only": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        },
    }
    validate_worker_capacity_receipt(receipt, oracle=oracle)
    return receipt


def validate_worker_capacity_receipt(receipt, *, oracle=None):
    oracle = _require_oracle(oracle)
    _exact_fields(receipt, (
        "schema", "schema_version", "fixture_id", "profile", "status",
        "persona_id", "limits_oracle_sha256", "inputs", "outputs",
        "process", "limits", "contracts",
    ), "worker receipt")
    _canonical_round_trip(receipt, "worker receipt")
    if (
        receipt["schema"] != WORKER_RECEIPT_SCHEMA
        or type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != WORKER_RECEIPT_SCHEMA_VERSION
        or receipt["fixture_id"] != spec.FIXTURE_ID
        or receipt["profile"] != PROFILE
        or receipt["status"] != DECLARED_PROJECTION_STATUS
        or receipt["limits_oracle_sha256"] != full_scale_limits_sha256(oracle)
    ):
        raise FullScaleLimitsError("worker receipt header differs")
    person = _person_record(oracle, receipt["persona_id"])
    expected_inputs = {
        key: person[key]
        for key in (
            "persona_generation_plan_sha256", "persona_event_plan_sha256",
            "history_allocation_sha256", "structural_allocation_sha256",
        )
    }
    if not _same_canonical_json(receipt["inputs"], expected_inputs):
        raise FullScaleLimitsError("worker receipt plan inputs differ")

    outputs = _exact_fields(receipt["outputs"], (
        "event_manifest_sha256", "event_projection_sha256",
        "shard_index_sha256", "shards", "logical_event_bytes",
        "max_json_depth", "counts", "plan_cardinalities",
        "declared_max_initial_materialization_row_bytes", "phase_ranges",
    ), "worker outputs")
    _sha256(outputs["event_manifest_sha256"], "event manifest sha256")
    _sha256(outputs["event_projection_sha256"], "event projection sha256")
    expected_counts = {
        "events": person["counts"]["events"],
        "boundaries": person["counts"]["boundaries"],
        "schedule": person["counts"]["schedule_items"],
    }
    summary = _validate_shards(outputs["shards"], expected_counts)
    if (
        outputs["shard_index_sha256"] != summary["shard_index_sha256"]
        or type(outputs["logical_event_bytes"]) is not int
        or outputs["logical_event_bytes"] != summary["total_bytes"]
        or not _same_canonical_json(outputs["counts"], expected_counts)
        or not _same_canonical_json(outputs["plan_cardinalities"], {
            "sources": person["w0_physical_sources"],
            "scopes": person["scope_count"],
            "managed_initial_materializations": person[
                "managed_initial_materializations"
            ],
        })
        or not _same_canonical_json(
            outputs["phase_ranges"], person["phase_ranges"]
        )
    ):
        raise FullScaleLimitsError("worker output arithmetic differs")
    _plain_int(
        outputs["max_json_depth"], "max JSON depth", minimum=1,
        maximum=MAX_CANONICAL_JSON_DEPTH,
    )
    _plain_int(
        outputs["declared_max_initial_materialization_row_bytes"],
        "declared max initial materialization row bytes", minimum=1,
        maximum=MAX_INITIAL_MATERIALIZATION_ROW_BYTES,
    )

    process = _exact_fields(receipt["process"], (
        "measurement_status", "declared_child_exit_code",
        "declared_child_terminating_signal", "declared_peak_rss_bytes",
        "declared_concurrent_persona_workers",
    ), "worker process")
    if (
        process["measurement_status"] != DECLARED_MEASUREMENT_STATUS
        or _plain_int(
            process["declared_child_exit_code"], "declared child exit code",
            maximum=255,
        )
        != 0
        or _plain_int(
            process["declared_child_terminating_signal"],
            "declared child terminating signal",
            maximum=255,
        ) != 0
        or _plain_int(
            process["declared_peak_rss_bytes"], "declared worker peak RSS",
            minimum=1,
            maximum=MAX_WORKER_RSS_BYTES,
        ) != process["declared_peak_rss_bytes"]
        or type(process["declared_concurrent_persona_workers"]) is not int
        or process["declared_concurrent_persona_workers"]
        != MAX_CONCURRENT_PERSONA_WORKERS
    ):
        raise FullScaleLimitsError("worker process did not exit cleanly within caps")
    required_limit_keys = {
        "persona_plan_bytes", "sources_per_persona", "scopes_per_persona",
        "managed_initial_materializations_per_persona",
        "logical_event_bytes_per_persona",
        "event_rows_per_persona", "boundary_rows_per_persona",
        "schedule_rows_per_persona", "canonical_json_depth",
        "event_row_bytes", "boundary_row_bytes",
        "initial_materialization_row_bytes", "schedule_row_bytes",
        "jsonl_shard_rows", "jsonl_shard_bytes", "worker_peak_rss_bytes",
        "concurrent_persona_workers",
    }
    expected_limits = {
        key: oracle["limits"][key] for key in required_limit_keys
    }
    if not _same_canonical_json(receipt["limits"], expected_limits):
        raise FullScaleLimitsError("worker receipt limits differ from oracle")
    if not _same_canonical_json(receipt["contracts"], {
        "declared_projection_only": True,
        "artifact_readback_required": True,
        "supervisor_wait4_required": True,
        "formal_capacity_gate_satisfied": False,
        "planned_counts_only": True,
        "actual_kio_evidence": False,
        "authorizes_physical_write": False,
    }):
        raise FullScaleLimitsError("worker receipt evidence contract differs")
    return True


def worker_capacity_receipt_sha256(receipt, *, oracle=None):
    validate_worker_capacity_receipt(receipt, oracle=oracle)
    return _digest(receipt)


def _ordered_worker_rows(worker_receipts, oracle):
    if type(worker_receipts) is not list or len(worker_receipts) != PERSONAS_PER_REPLAY:
        raise FullScaleLimitsError("suite requires exactly twenty worker receipts")
    by_persona = {}
    for receipt in worker_receipts:
        validate_worker_capacity_receipt(receipt, oracle=oracle)
        persona_id = receipt["persona_id"]
        if persona_id in by_persona:
            raise FullScaleLimitsError("suite repeats a worker persona")
        by_persona[persona_id] = receipt
    if set(by_persona) != set(_PERSONA_IDS):
        raise FullScaleLimitsError("suite worker persona set differs")
    return [
        {
            "persona_id": persona_id,
            "worker_receipt_sha256": worker_capacity_receipt_sha256(
                by_persona[persona_id], oracle=oracle
            ),
        }
        for persona_id in _PERSONA_IDS
    ]


def build_suite_capacity_receipt(
    *, replay_ordinal, worker_receipts, suite_event_manifest_sha256,
    suite_schedule_sha256, schedule_locator_root_sha256,
    schedule_mmr_root_sha256, schedule_mmr_leaf_count,
    suite_event_manifest_bytes, suite_schedule_bytes, schedule_locator_bytes,
    schedule_mmr_bytes, max_suite_schedule_row_bytes,
    max_locator_row_bytes, artifact_bytes, workspace_bytes,
    composer_peak_rss_bytes, oracle=None,
):
    """Build a declared suite projection, never a measured/formal receipt."""
    oracle = _require_oracle(oracle)
    workers = _ordered_worker_rows(worker_receipts, oracle)
    max_worker_rss = max(
        receipt["process"]["declared_peak_rss_bytes"]
        for receipt in worker_receipts
    )
    composer_rss = _plain_int(
        composer_peak_rss_bytes, "composer peak RSS", minimum=1,
        maximum=MAX_COMPOSER_RSS_BYTES,
    )
    conservative_tree = composer_rss + max_worker_rss
    if conservative_tree > MAX_PROCESS_TREE_RSS_BYTES:
        raise FullScaleLimitsError("conservative process tree exceeds 512 MiB")
    suite_files = {
        "event_manifest": _plain_int(
            suite_event_manifest_bytes, "declared suite event manifest bytes",
            minimum=1, maximum=MAX_SUITE_LOGICAL_FILE_BYTES,
        ),
        "schedule": _plain_int(
            suite_schedule_bytes, "declared suite schedule bytes",
            minimum=1, maximum=MAX_SUITE_LOGICAL_FILE_BYTES,
        ),
        "locator": _plain_int(
            schedule_locator_bytes, "declared schedule locator bytes",
            minimum=1, maximum=MAX_SUITE_LOGICAL_FILE_BYTES,
        ),
        "mmr": _plain_int(
            schedule_mmr_bytes, "declared schedule MMR bytes",
            minimum=1, maximum=MAX_SUITE_LOGICAL_FILE_BYTES,
        ),
    }
    minimum_artifact_bytes = (
        sum(
            value["outputs"]["logical_event_bytes"]
            for value in worker_receipts
        )
        + sum(suite_files.values())
    )
    declared_artifact_bytes = _plain_int(
        artifact_bytes, "declared artifact bytes",
        minimum=minimum_artifact_bytes, maximum=MAX_ARTIFACT_BYTES,
    )
    declared_workspace_bytes = _plain_int(
        workspace_bytes, "declared workspace bytes",
        minimum=declared_artifact_bytes, maximum=MAX_WORKSPACE_BYTES,
    )
    receipt = {
        "schema": SUITE_RECEIPT_SCHEMA,
        "schema_version": SUITE_RECEIPT_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": PROFILE,
        "status": DECLARED_PROJECTION_STATUS,
        "replay_ordinal": _plain_int(
            replay_ordinal, "replay ordinal", minimum=1, maximum=REPLAY_COUNT
        ),
        "limits_oracle_sha256": full_scale_limits_sha256(oracle),
        "inputs": {"worker_receipts": workers},
        "outputs": {
            "suite_event_manifest_sha256": _sha256(
                suite_event_manifest_sha256, "suite event manifest sha256"
            ),
            "suite_schedule_sha256": _sha256(
                suite_schedule_sha256, "suite schedule sha256"
            ),
            "schedule_locator_root_sha256": _sha256(
                schedule_locator_root_sha256, "schedule locator root sha256"
            ),
            "schedule_mmr_root_sha256": _sha256(
                schedule_mmr_root_sha256, "schedule MMR root sha256"
            ),
            "schedule_mmr_leaf_count": _plain_int(
                schedule_mmr_leaf_count, "schedule MMR leaf count", minimum=1
            ),
            "counts": {
                key: oracle["per_replay"][key]
                for key in ("events", "boundaries", "schedule_items")
            },
            "worker_logical_event_bytes": sum(
                receipt["outputs"]["logical_event_bytes"]
                for receipt in worker_receipts
            ),
            "worker_shards": sum(
                len(receipt["outputs"]["shards"])
                for receipt in worker_receipts
            ),
            "suite_logical_file_bytes": suite_files,
            "declared_max_suite_schedule_row_bytes": _plain_int(
                max_suite_schedule_row_bytes,
                "declared max suite schedule row bytes", minimum=1,
                maximum=MAX_SCHEDULE_ROW_BYTES,
            ),
            "declared_max_locator_row_bytes": _plain_int(
                max_locator_row_bytes, "declared max locator row bytes",
                minimum=1, maximum=MAX_LOCATOR_ROW_BYTES,
            ),
            "minimum_artifact_bytes": minimum_artifact_bytes,
            "declared_artifact_bytes": declared_artifact_bytes,
            "declared_workspace_bytes": declared_workspace_bytes,
        },
        "process": {
            "measurement_status": DECLARED_MEASUREMENT_STATUS,
            "declared_max_worker_peak_rss_bytes": max_worker_rss,
            "declared_composer_peak_rss_bytes": composer_rss,
            "declared_conservative_process_tree_peak_rss_bytes": (
                conservative_tree
            ),
            "declared_concurrent_persona_workers": (
                MAX_CONCURRENT_PERSONA_WORKERS
            ),
        },
        "limits": {
            key: oracle["limits"][key]
            for key in (
                "worker_peak_rss_bytes", "composer_peak_rss_bytes",
                "process_tree_peak_rss_bytes", "concurrent_persona_workers",
                "locator_row_bytes", "schedule_row_bytes",
                "suite_event_rows", "suite_boundary_rows",
                "suite_schedule_rows", "suite_logical_file_bytes",
                "artifact_bytes", "workspace_bytes",
            )
        },
        "contracts": {
            "declared_projection_only": True,
            "artifact_readback_required": True,
            "supervisor_wait4_required": True,
            "single_worker_no_grandchildren_required": True,
            "formal_capacity_gate_satisfied": False,
            "planned_counts_only": True,
            "actual_kio_evidence": False,
            "authorizes_physical_write": False,
        },
    }
    validate_suite_capacity_receipt(
        receipt, worker_receipts=worker_receipts, oracle=oracle
    )
    return receipt


def validate_suite_capacity_receipt(receipt, *, worker_receipts, oracle=None):
    oracle = _require_oracle(oracle)
    _exact_fields(receipt, (
        "schema", "schema_version", "fixture_id", "profile", "status",
        "replay_ordinal", "limits_oracle_sha256", "inputs", "outputs",
        "process", "limits", "contracts",
    ), "suite receipt")
    _canonical_round_trip(receipt, "suite receipt")
    if (
        receipt["schema"] != SUITE_RECEIPT_SCHEMA
        or type(receipt["schema_version"]) is not int
        or receipt["schema_version"] != SUITE_RECEIPT_SCHEMA_VERSION
        or receipt["fixture_id"] != spec.FIXTURE_ID
        or receipt["profile"] != PROFILE
        or receipt["status"] != DECLARED_PROJECTION_STATUS
        or receipt["limits_oracle_sha256"] != full_scale_limits_sha256(oracle)
    ):
        raise FullScaleLimitsError("suite receipt header differs")
    _plain_int(
        receipt["replay_ordinal"], "replay ordinal", minimum=1,
        maximum=REPLAY_COUNT,
    )
    expected_workers = _ordered_worker_rows(worker_receipts, oracle)
    if not _same_canonical_json(
        receipt["inputs"], {"worker_receipts": expected_workers}
    ):
        raise FullScaleLimitsError("suite worker receipt inventory differs")

    outputs = _exact_fields(receipt["outputs"], (
        "suite_event_manifest_sha256", "suite_schedule_sha256",
        "schedule_locator_root_sha256", "schedule_mmr_root_sha256",
        "schedule_mmr_leaf_count", "counts", "worker_logical_event_bytes",
        "worker_shards", "suite_logical_file_bytes",
        "declared_max_suite_schedule_row_bytes",
        "declared_max_locator_row_bytes", "minimum_artifact_bytes",
        "declared_artifact_bytes", "declared_workspace_bytes",
    ), "suite outputs")
    for key in (
        "suite_event_manifest_sha256", "suite_schedule_sha256",
        "schedule_locator_root_sha256", "schedule_mmr_root_sha256",
    ):
        _sha256(outputs[key], key)
    expected_worker_bytes = sum(
        value["outputs"]["logical_event_bytes"] for value in worker_receipts
    )
    suite_files = _exact_fields(outputs["suite_logical_file_bytes"], (
        "event_manifest", "schedule", "locator", "mmr",
    ), "suite logical file bytes")
    for key, value in suite_files.items():
        _plain_int(
            value, f"declared suite {key} bytes", minimum=1,
            maximum=MAX_SUITE_LOGICAL_FILE_BYTES,
        )
    expected_minimum_artifact = expected_worker_bytes + sum(
        suite_files.values()
    )
    if (
        type(outputs["schedule_mmr_leaf_count"]) is not int
        or outputs["schedule_mmr_leaf_count"]
        != oracle["per_replay"]["schedule_items"]
        or not _same_canonical_json(outputs["counts"], {
            key: oracle["per_replay"][key]
            for key in ("events", "boundaries", "schedule_items")
        })
        or type(outputs["worker_logical_event_bytes"]) is not int
        or outputs["worker_logical_event_bytes"] != expected_worker_bytes
        or type(outputs["worker_shards"]) is not int
        or outputs["worker_shards"] != sum(
            len(value["outputs"]["shards"]) for value in worker_receipts
        )
        or _plain_int(
            outputs["declared_max_suite_schedule_row_bytes"],
            "declared max suite schedule row bytes", minimum=1,
            maximum=MAX_SCHEDULE_ROW_BYTES,
        ) != outputs["declared_max_suite_schedule_row_bytes"]
        or _plain_int(
            outputs["declared_max_locator_row_bytes"],
            "declared max locator row bytes", minimum=1,
            maximum=MAX_LOCATOR_ROW_BYTES,
        ) != outputs["declared_max_locator_row_bytes"]
        or type(outputs["minimum_artifact_bytes"]) is not int
        or outputs["minimum_artifact_bytes"] != expected_minimum_artifact
        or _plain_int(
            outputs["declared_artifact_bytes"],
            "declared artifact bytes", minimum=expected_minimum_artifact,
            maximum=MAX_ARTIFACT_BYTES,
        ) != outputs["declared_artifact_bytes"]
        or _plain_int(
            outputs["declared_workspace_bytes"],
            "declared workspace bytes",
            minimum=outputs["declared_artifact_bytes"],
            maximum=MAX_WORKSPACE_BYTES,
        ) != outputs["declared_workspace_bytes"]
    ):
        raise FullScaleLimitsError("suite output arithmetic differs")

    process = _exact_fields(receipt["process"], (
        "measurement_status", "declared_max_worker_peak_rss_bytes",
        "declared_composer_peak_rss_bytes",
        "declared_conservative_process_tree_peak_rss_bytes",
        "declared_concurrent_persona_workers",
    ), "suite process")
    max_worker = max(
        value["process"]["declared_peak_rss_bytes"]
        for value in worker_receipts
    )
    composer = _plain_int(
        process["declared_composer_peak_rss_bytes"],
        "declared composer peak RSS", minimum=1,
        maximum=MAX_COMPOSER_RSS_BYTES,
    )
    if (
        process["measurement_status"] != DECLARED_MEASUREMENT_STATUS
        or type(process["declared_max_worker_peak_rss_bytes"]) is not int
        or process["declared_max_worker_peak_rss_bytes"] != max_worker
        or type(
            process["declared_conservative_process_tree_peak_rss_bytes"]
        ) is not int
        or process["declared_conservative_process_tree_peak_rss_bytes"]
        != composer + max_worker
        or process["declared_conservative_process_tree_peak_rss_bytes"]
        > MAX_PROCESS_TREE_RSS_BYTES
        or type(process["declared_concurrent_persona_workers"]) is not int
        or process["declared_concurrent_persona_workers"]
        != MAX_CONCURRENT_PERSONA_WORKERS
    ):
        raise FullScaleLimitsError("suite process arithmetic or caps differ")
    if not _same_canonical_json(receipt["limits"], {
        key: oracle["limits"][key]
        for key in (
            "worker_peak_rss_bytes", "composer_peak_rss_bytes",
            "process_tree_peak_rss_bytes", "concurrent_persona_workers",
            "locator_row_bytes", "schedule_row_bytes", "suite_event_rows",
            "suite_boundary_rows", "suite_schedule_rows",
            "suite_logical_file_bytes", "artifact_bytes", "workspace_bytes",
        )
    }):
        raise FullScaleLimitsError("suite receipt limits differ from oracle")
    if not _same_canonical_json(receipt["contracts"], {
        "declared_projection_only": True,
        "artifact_readback_required": True,
        "supervisor_wait4_required": True,
        "single_worker_no_grandchildren_required": True,
        "formal_capacity_gate_satisfied": False,
        "planned_counts_only": True,
        "actual_kio_evidence": False,
        "authorizes_physical_write": False,
    }):
        raise FullScaleLimitsError("suite receipt evidence contract differs")
    return True


def suite_capacity_receipt_sha256(receipt, *, worker_receipts, oracle=None):
    validate_suite_capacity_receipt(
        receipt, worker_receipts=worker_receipts, oracle=oracle
    )
    return _digest(receipt)
