"""Bounded, root-independent capacity projections for persona-PC fixtures.

This module never renders a source, probes a filesystem, or writes a receipt.
It joins exact cardinalities from one canonical persona plan with typed pilot
amplification declarations.  Until a future profiler reads those declarations
back from an actual pilot root, every byte result remains blocked.  A capacity projection deliberately
cannot approve a destination: filesystem identity, allocation unit, limits,
and free-space reserves are introduced only by :func:`build_capacity_receipt`.

Unknown evidence is represented by JSON ``null`` and is never coerced to
zero.  Every persisted number is an integer; booleans and floating point
values are rejected.  Arithmetic is checked against signed 64-bit bounds so a
coherently rehashed oversized input cannot wrap a later cap comparison.
"""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re

try:  # Package imports and direct imports from ``eval`` tests.
    from . import generate_persona_corpus as generator
    from . import persona_allocation as allocation
    from . import persona_fixture_spec as spec
    from . import persona_history_allocation as history
    from . import persona_manifest as canonical_manifest
    from . import persona_structural_allocation as structural
except ImportError:  # pragma: no cover - direct-script compatibility.
    import generate_persona_corpus as generator
    import persona_allocation as allocation
    import persona_fixture_spec as spec
    import persona_history_allocation as history
    import persona_manifest as canonical_manifest
    import persona_structural_allocation as structural


CAPACITY_PLAN_SCHEMA = "kcs.persona.capacity-plan/v1"
AMPLIFICATION_SCHEMA = "kcs.persona.pilot-capacity-amplification/v1"
PILOT_MEASUREMENT_SCHEMA = "kcs.persona.pilot-capacity-measurement/v1"
ROOT_MEASUREMENT_SCHEMA = "kcs.persona.root-capacity-measurement/v1"
CAPACITY_RECEIPT_SCHEMA = "kcs.persona.root-bound-capacity-receipt/v1"
SCHEMA_VERSION = 1
MAX_INTEGER = 2**63 - 1
MIN_FILESYSTEM_ALLOCATION_UNIT = 512
MAX_FILESYSTEM_ALLOCATION_UNIT = 1024 * 1024
SUITE_SHARED_FILES = 6
SUITE_SHARED_DIRECTORIES = 8
SUITE_SHARED_KNOWN_INODES = SUITE_SHARED_FILES + SUITE_SHARED_DIRECTORIES

COMPONENTS = ("raw", "cas", "index", "history", "staging", "transient")
RETAINED_COMPONENTS = ("raw", "cas", "index", "history")
COMPONENT_BASIS = {
    "raw": "final_active_files",
    "cas": "transient_current_chunks",
    "index": "transient_current_plus_history_chunks",
    "history": "history_only_chunks",
    "staging": "w0_physical_files",
    "transient": "transient_extra_chunk_rows",
}
PROFILES = frozenset(("tiny", "pilot", "full"))
EXPECTED_PERSONA_IDS = tuple(persona["id"] for persona in spec.PERSONAS)
EXPECTED_PERSONA_ID_SET = frozenset(EXPECTED_PERSONA_IDS)
SHA256_RE = re.compile(r"[0-9a-f]{64}")
PERSONA_WRAPPER_SCHEMA = "kcs.persona.w0.persona-generation-plan/v1"
DECLARED_UNVERIFIED = "declared_unverified"
MEASUREMENT_READBACK_REQUIRED = "measurement_receipt_readback_required"
ROOT_MEASUREMENT_READBACK_REQUIRED = (
    "root_availability_measurement_readback_required"
)
PILOT_MEASUREMENT_PROJECTION_DOMAIN = (
    "kcs.persona.pilot-capacity-measurement-projection/v1"
)
ROOT_MEASUREMENT_PROJECTION_DOMAIN = (
    "kcs.persona.root-capacity-measurement-projection/v1"
)


class PersonaCapacityError(ValueError):
    """Raised when capacity evidence or arithmetic is unsafe."""


def _integer(value, label, *, minimum=0, maximum=MAX_INTEGER):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PersonaCapacityError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _add(left, right, label):
    left = _integer(left, f"{label} left operand")
    right = _integer(right, f"{label} right operand")
    if left > MAX_INTEGER - right:
        raise PersonaCapacityError(f"{label} exceeds the checked integer bound")
    return left + right


def _sum(values, label):
    result = 0
    for value in values:
        result = _add(result, value, label)
    return result


def _multiply(left, right, label):
    left = _integer(left, f"{label} left operand")
    right = _integer(right, f"{label} right operand")
    if left and right > MAX_INTEGER // left:
        raise PersonaCapacityError(f"{label} exceeds the checked integer bound")
    return left * right


def _ceil_multiply_divide(value, numerator, denominator, label):
    value = _integer(value, f"{label} value")
    numerator = _integer(numerator, f"{label} numerator")
    denominator = _integer(denominator, f"{label} denominator", minimum=1)
    product = _multiply(value, numerator, label)
    if not product:
        return 0
    return _add(product, denominator - 1, label) // denominator


def _digest(value):
    try:
        raw = canonical_manifest.canonical_json_bytes(value)
    except (TypeError, ValueError, canonical_manifest.PersonaManifestError) as error:
        raise PersonaCapacityError(str(error)) from error
    return hashlib.sha256(raw).hexdigest()


def _sha256(value, label):
    if type(value) is not str or SHA256_RE.fullmatch(value) is None:
        raise PersonaCapacityError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _without_bool_or_float(value, label="value"):
    if type(value) is bool or type(value) is float:
        raise PersonaCapacityError(f"{label} contains a boolean or float")
    if value is None or type(value) in (str, int):
        if type(value) is int:
            _integer(value, label)
        return
    if type(value) in (list, tuple):
        for index, item in enumerate(value):
            _without_bool_or_float(item, f"{label}[{index}]")
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key:
                raise PersonaCapacityError(f"{label} has a non-string/empty key")
            _without_bool_or_float(item, f"{label}.{key}")
        return
    raise PersonaCapacityError(
        f"{label} has a non-canonical value type: {type(value).__name__}"
    )


def _canonical_person_row(persona_id, profile):
    """Bounded fallback for callers that have not adopted the wrapper API."""
    try:
        persona = spec.get_persona(persona_id)
        route = allocation.build_allocation_plan(persona, profile)
        scopes = generator._source_plan_for_persona(persona, profile, route)
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise PersonaCapacityError(str(error)) from error
    return {
        "persona_id": persona["id"],
        "role": persona["role"],
        "device_slug": f"{persona['id']}-{persona['role']}",
        "raw_file_count": spec.raw_file_count(persona, profile),
        "planned_contract_chunks": spec.contributor_plan(persona, profile)[
            "target_chunks"
        ],
        "format_percentages": persona["format_percentages"],
        "allocation": route,
        "scopes": scopes,
    }


def _normalize_person_plan(value, profile=None):
    if type(value) is not dict:
        raise PersonaCapacityError("persona plan must be an object")
    if value.get("schema") == PERSONA_WRAPPER_SCHEMA:
        validator = getattr(generator, "validate_persona_generation_plan", None)
        projector = getattr(generator, "persona_event_plan_projection", None)
        if not callable(validator) or not callable(projector):
            raise PersonaCapacityError(
                "persona wrapper API is unavailable; pass the canonical person object"
            )
        expected_profile = value.get("profile") if profile is None else profile
        try:
            validated = validator(value, expected_profile=expected_profile)
            projected = projector(validated, expected_profile=expected_profile)
        except (TypeError, ValueError, RuntimeError) as error:
            raise PersonaCapacityError(str(error)) from error
        person = validated["persona"]
        plan_digest = _digest(validated)
        input_kind = "validated_persona_wrapper"
    else:
        person = value
        expected_profile = profile
        if expected_profile not in PROFILES:
            candidate = person.get("allocation", {}).get("profile")
            if candidate not in PROFILES:
                raise PersonaCapacityError(
                    "profile is required for a canonical person object"
                )
            expected_profile = candidate
        persona_id = person.get("persona_id")
        if type(persona_id) is not str:
            raise PersonaCapacityError("canonical person object lacks persona_id")
        expected = _canonical_person_row(persona_id, expected_profile)
        projection = {
            "persona_id": expected["persona_id"],
            "planned_contract_chunks": expected["planned_contract_chunks"],
            "scopes": expected["scopes"],
        }
        if person == expected:
            projected = projection
            person = expected
            input_kind = "canonical_person_object"
        elif person == projection:
            projected = projection
            person = expected
            input_kind = "canonical_event_projection"
        else:
            raise PersonaCapacityError(
                "persona object differs from the canonical one-person expansion"
            )
        plan_digest = _digest(person)
    if expected_profile not in PROFILES:
        raise PersonaCapacityError(f"unknown profile: {expected_profile!r}")
    return person, projected, expected_profile, plan_digest, input_kind


def unknown_amplification(persona_id):
    """Return explicit unknown evidence; unknown is never numeric zero."""
    components = {}
    for name in COMPONENTS:
        components[name] = {
            "status": "unknown",
            "basis": COMPONENT_BASIS[name],
            "observed_units": None,
            "observed_bytes": None,
            "observed_additional_inodes": None,
            "pilot_receipt_sha256": None,
        }
    return {
        "schema": AMPLIFICATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "persona_id": persona_id,
        "pilot_profile": "pilot",
        "pilot_persona_plan_sha256": None,
        "filesystem_allocation_unit": {"status": "unknown", "bytes": None},
        "pilot_measurement_receipt": None,
        "components": components,
    }


def _validate_amplification(value, persona_id):
    if value is None:
        return unknown_amplification(persona_id)
    _without_bool_or_float(value, "amplification")
    expected_fields = {
        "schema", "schema_version", "fixture_id", "persona_id",
        "pilot_profile", "pilot_persona_plan_sha256",
        "filesystem_allocation_unit", "pilot_measurement_receipt", "components",
    }
    if type(value) is not dict or set(value) != expected_fields:
        raise PersonaCapacityError("amplification has an invalid field set")
    if (
        value["schema"] != AMPLIFICATION_SCHEMA
        or value["schema_version"] != SCHEMA_VERSION
        or value["fixture_id"] != spec.FIXTURE_ID
        or value["persona_id"] != persona_id
        or value["pilot_profile"] != "pilot"
    ):
        raise PersonaCapacityError("amplification header differs from the contract")
    unit = value["filesystem_allocation_unit"]
    if type(unit) is not dict or set(unit) != {"status", "bytes"}:
        raise PersonaCapacityError("filesystem allocation evidence is malformed")
    if unit["status"] == "unknown":
        if unit["bytes"] is not None:
            raise PersonaCapacityError("unknown allocation unit must use null bytes")
    elif unit["status"] == DECLARED_UNVERIFIED:
        _integer(
            unit["bytes"], "filesystem allocation unit",
            minimum=MIN_FILESYSTEM_ALLOCATION_UNIT,
            maximum=MAX_FILESYSTEM_ALLOCATION_UNIT,
        )
    elif unit["status"] == "measured":
        raise PersonaCapacityError(
            "measured pilot evidence requires an implemented receipt readback"
        )
    else:
        raise PersonaCapacityError("filesystem allocation status is invalid")
    components = value["components"]
    if type(components) is not dict or set(components) != set(COMPONENTS):
        raise PersonaCapacityError("amplification component inventory is incomplete")
    any_declared = False
    for name in COMPONENTS:
        row = components[name]
        fields = {
            "status", "basis", "observed_units", "observed_bytes",
            "observed_additional_inodes", "pilot_receipt_sha256",
        }
        if type(row) is not dict or set(row) != fields:
            raise PersonaCapacityError(f"{name} amplification fields are invalid")
        if row["basis"] != COMPONENT_BASIS[name]:
            raise PersonaCapacityError(f"{name} amplification basis is invalid")
        measured_fields = (
            "observed_units", "observed_bytes",
            "observed_additional_inodes", "pilot_receipt_sha256",
        )
        if row["status"] == "unknown":
            if any(row[field] is not None for field in measured_fields):
                raise PersonaCapacityError(
                    f"unknown {name} amplification must use null evidence"
                )
        elif row["status"] == DECLARED_UNVERIFIED:
            any_declared = True
            _integer(row["observed_units"], f"{name} observed units", minimum=1)
            _integer(row["observed_bytes"], f"{name} observed bytes")
            _integer(
                row["observed_additional_inodes"],
                f"{name} observed additional inodes",
            )
            if (
                row["observed_bytes"] == 0
                and row["observed_additional_inodes"] == 0
            ):
                raise PersonaCapacityError(
                    f"declared {name} evidence cannot be all-zero"
                )
            _sha256(row["pilot_receipt_sha256"], f"{name} pilot receipt")
        elif row["status"] == "measured":
            raise PersonaCapacityError(
                "measured pilot evidence requires an implemented receipt readback"
            )
        else:
            raise PersonaCapacityError(f"{name} amplification status is invalid")
    if any_declared:
        receipt = _validate_pilot_measurement_receipt(
            value["pilot_measurement_receipt"], persona_id
        )
        expected_plan_sha = _canonical_pilot_contract(persona_id)[
            "pilot_persona_plan_sha256"
        ]
        if value["pilot_persona_plan_sha256"] != expected_plan_sha:
            raise PersonaCapacityError(
                "pilot amplification is not bound to the canonical pilot plan"
            )
        if unit != {
            "status": DECLARED_UNVERIFIED,
            "bytes": receipt["filesystem_allocation_unit_bytes"],
        }:
            raise PersonaCapacityError(
                "pilot allocation evidence differs from its typed receipt"
            )
        receipt_sha = _digest(receipt)
        for name in COMPONENTS:
            row = components[name]
            measured_fields = (
                "observed_units", "observed_bytes",
                "observed_additional_inodes",
            )
            receipt_row = receipt["components"][name]
            if row["status"] == "unknown":
                if receipt_row["status"] != "unknown":
                    raise PersonaCapacityError(
                        f"{name} amplification omits declared receipt evidence"
                    )
                continue
            if (
                receipt_row["status"] != DECLARED_UNVERIFIED
                or any(row[field] != receipt_row[field] for field in measured_fields)
                or row["pilot_receipt_sha256"] != receipt_sha
            ):
                raise PersonaCapacityError(
                    f"{name} amplification differs from its typed receipt"
                )
    elif (
        value["pilot_persona_plan_sha256"] is not None
        or value["pilot_measurement_receipt"] is not None
        or unit["status"] != "unknown"
    ):
        raise PersonaCapacityError(
            "an entirely unknown amplification must use null pilot evidence"
        )
    return value


def _topology_directory_count(person):
    prefixes = {"device", "device/home"}
    for scope in person["scopes"]:
        current = PurePosixPath("device/home")
        for component in PurePosixPath(scope["relative_path"]).parts:
            current /= component
            prefixes.add(str(current))
    return len(prefixes)


def _cardinalities(person, projected, profile):
    try:
        history_plan = history.build_history_allocation(projected, profile)
        structural_plan = structural.build_structural_allocation(projected, profile)
    except (TypeError, ValueError, RuntimeError) as error:
        raise PersonaCapacityError(str(error)) from error
    w0_files = _sum(
        (len(scope["sources"]) for scope in projected["scopes"]),
        "W0 source files",
    )
    if w0_files != person["raw_file_count"]:
        raise PersonaCapacityError("W0 source count differs from the person plan")
    p_count = history_plan["strata"]["P"]["source_count"]
    x_count = history_plan["strata"]["X"]["source_count"]
    structural_delta = structural_plan["totals"]["final_live_physical_file_delta"]
    final_files = _add(w0_files, structural_delta, "final active files")
    transient_files = _add(final_files, p_count, "transient active files")

    current = projected["planned_contract_chunks"]
    final_history = history_plan["checkpoints"]["W5"]["history_only"]
    transient_current = history_plan["checkpoints"]["W5_pre_purge_auto"]["current"]
    transient_history = history_plan["checkpoints"]["W5_pre_purge_auto"][
        "history_only"
    ]
    final_total_chunks = _add(current, final_history, "final chunk rows")
    transient_total_chunks = _add(
        transient_current, transient_history, "transient chunk rows"
    )
    transient_extra_chunks = transient_total_chunks - final_total_chunks
    if transient_extra_chunks < 0:
        raise PersonaCapacityError("transient chunks are below final chunks")

    waves = history_plan["waves"]
    history_events = _sum((
        len(waves["W1"]["edit_source_ids"]),
        len(waves["W3"]["major_edit_source_ids"]),
        len(waves["W4"]["delete_source_ids"]),
        len(waves["W5"]["correct_source_ids"]),
        _multiply(2, len(waves["W5"]["purge_source_ids"]), "purge events"),
    ), "history events")
    structural_events = structural_plan["totals"]["events"]
    events = _add(history_events, structural_events, "event total")
    index_auto = 0
    for wave in ("W1", "W2", "W3", "W4", "W5"):
        history_scopes = waves[wave].get(
            "index_auto_scope_keys", waves[wave].get("affected_scope_keys", ())
        )
        structural_scopes = structural_plan[
            "structural_index_scope_keys_by_wave"
        ][wave]
        index_auto = _add(
            index_auto,
            len(set(history_scopes) | set(structural_scopes)),
            "index-auto boundaries",
        )
    purged_commits = len(waves["W5"]["purge_source_ids"])
    index_noops = len(waves["W5"]["index_noop_scope_keys"])
    boundaries = _sum(
        (index_auto, purged_commits, index_noops), "boundary total"
    )
    schedule_items = _add(events, boundaries, "schedule items")

    scope_count = len(projected["scopes"])
    topology_dirs = _topology_directory_count(person)
    ledger_files = _add(1, _multiply(scope_count, 4, "ledger files"), "ledger files")
    ledger_dirs = _add(1, scope_count, "ledger directories")
    runtime_root_dirs = _add(1, scope_count, "runtime root directories")
    retained_known_inodes = _sum((
        final_files, topology_dirs, ledger_files, ledger_dirs, runtime_root_dirs,
    ), "known retained inodes")
    staging_known_inodes = _sum((
        w0_files, topology_dirs, ledger_files, ledger_dirs,
    ), "known staging inodes")
    transient_known_inodes = _add(
        retained_known_inodes, transient_files - final_files,
        "known transient inodes",
    )
    return {
        "files": {
            "w0_physical_files": w0_files,
            "final_active_files": final_files,
            "transient_active_files": transient_files,
            "history_replacement_sources": _add(p_count, x_count, "replacement sources"),
            "structural_new_sources": structural_plan["totals"]["new_source_ids"],
            "persona_and_ledger_files": ledger_files,
        },
        "scopes": {
            "active_scopes": scope_count,
            "topology_directories": topology_dirs,
            "runtime_store_roots": scope_count,
            "device_state_roots": 1,
        },
        "chunks": {
            "current_chunks": current,
            "history_only_chunks": final_history,
            "current_plus_history_chunks": final_total_chunks,
            "transient_current_chunks": transient_current,
            "transient_history_only_chunks": transient_history,
            "transient_current_plus_history_chunks": transient_total_chunks,
            "transient_extra_chunk_rows": transient_extra_chunks,
        },
        "events": {
            "history_events": history_events,
            "structural_events": structural_events,
            "events": events,
            "index_auto_boundaries": index_auto,
            "purged_commit_boundaries": purged_commits,
            "index_noop_boundaries": index_noops,
            "boundaries": boundaries,
            "schedule_items": schedule_items,
        },
        "inodes": {
            "final_active_source_inodes": final_files,
            "transient_active_source_inodes": transient_files,
            "exact_known_retained_inodes": retained_known_inodes,
            "exact_known_transient_inodes": transient_known_inodes,
            "exact_known_staging_inodes": staging_known_inodes,
        },
    }


def _basis_values(cardinalities):
    return {
        "final_active_files": cardinalities["files"]["final_active_files"],
        "w0_physical_files": cardinalities["files"]["w0_physical_files"],
        "transient_current_chunks": cardinalities["chunks"][
            "transient_current_chunks"
        ],
        "transient_current_plus_history_chunks": cardinalities["chunks"][
            "transient_current_plus_history_chunks"
        ],
        "history_only_chunks": cardinalities["chunks"]["history_only_chunks"],
        "transient_extra_chunk_rows": cardinalities["chunks"][
            "transient_extra_chunk_rows"
        ],
    }


def _canonical_pilot_contract(persona_id):
    try:
        wrapper = generator.build_persona_generation_plan("pilot", persona_id)
        projected = generator.persona_event_plan_projection(
            wrapper,
            expected_profile="pilot",
            expected_persona_id=persona_id,
        )
    except (TypeError, ValueError, RuntimeError) as error:
        raise PersonaCapacityError(str(error)) from error
    cardinalities = _cardinalities(wrapper["persona"], projected, "pilot")
    basis_values = _basis_values(cardinalities)
    return {
        "pilot_persona_plan_sha256": _digest(wrapper),
        "basis_values": {
            name: basis_values[COMPONENT_BASIS[name]] for name in COMPONENTS
        },
    }


def _pilot_measurement_projection(receipt):
    return {
        "domain": PILOT_MEASUREMENT_PROJECTION_DOMAIN,
        "fixture_id": spec.FIXTURE_ID,
        "profile": "pilot",
        "persona_id": receipt["persona_id"],
        "pilot_persona_plan_sha256": receipt["pilot_persona_plan_sha256"],
        "filesystem_allocation_unit_bytes": receipt[
            "filesystem_allocation_unit_bytes"
        ],
        "components": receipt["components"],
        "readback_status": receipt["readback_status"],
    }


def _validate_pilot_measurement_receipt(receipt, persona_id):
    _without_bool_or_float(receipt, "pilot measurement receipt")
    fields = {
        "schema", "schema_version", "fixture_id", "profile", "persona_id",
        "pilot_persona_plan_sha256", "filesystem_allocation_unit_bytes",
        "components", "measurement_projection_sha256", "readback_status",
        "approval_scope",
    }
    if type(receipt) is not dict or set(receipt) != fields:
        raise PersonaCapacityError("pilot measurement receipt fields are invalid")
    contract = _canonical_pilot_contract(persona_id)
    if (
        receipt["schema"] != PILOT_MEASUREMENT_SCHEMA
        or receipt["schema_version"] != SCHEMA_VERSION
        or receipt["fixture_id"] != spec.FIXTURE_ID
        or receipt["profile"] != "pilot"
        or receipt["persona_id"] != persona_id
        or receipt["pilot_persona_plan_sha256"]
        != contract["pilot_persona_plan_sha256"]
        or receipt["readback_status"] != MEASUREMENT_READBACK_REQUIRED
        or receipt["approval_scope"]
        != "declared_capacity_measurement_only_not_readback"
    ):
        raise PersonaCapacityError("pilot measurement receipt binding differs")
    _integer(
        receipt["filesystem_allocation_unit_bytes"],
        "pilot filesystem allocation unit",
        minimum=MIN_FILESYSTEM_ALLOCATION_UNIT,
        maximum=MAX_FILESYSTEM_ALLOCATION_UNIT,
    )
    rows = receipt["components"]
    if type(rows) is not dict or set(rows) != set(COMPONENTS):
        raise PersonaCapacityError("pilot measurement component inventory differs")
    for name in COMPONENTS:
        row = rows[name]
        if type(row) is not dict or set(row) != {
            "status", "basis", "observed_units", "observed_bytes",
            "observed_additional_inodes",
        }:
            raise PersonaCapacityError(
                f"{name} pilot measurement fields are invalid"
            )
        expected_units = contract["basis_values"][name]
        if (
            row["status"] != DECLARED_UNVERIFIED
            or row["basis"] != COMPONENT_BASIS[name]
            or row["observed_units"] != expected_units
        ):
            raise PersonaCapacityError(
                f"{name} pilot measurement basis differs from the canonical pilot"
            )
        _integer(row["observed_bytes"], f"{name} observed bytes")
        _integer(
            row["observed_additional_inodes"],
            f"{name} observed additional inodes",
        )
        if row["observed_bytes"] == 0 and row["observed_additional_inodes"] == 0:
            raise PersonaCapacityError(
                f"declared {name} evidence cannot be all-zero"
            )
    expected_projection_sha = _digest(_pilot_measurement_projection(receipt))
    if receipt["measurement_projection_sha256"] != expected_projection_sha:
        raise PersonaCapacityError("pilot measurement projection digest differs")
    return receipt


def build_declared_pilot_amplification(
    persona_id, *, filesystem_allocation_unit_bytes, component_observations,
):
    """Bind caller-declared pilot values without claiming measurement readback."""
    contract = _canonical_pilot_contract(persona_id)
    unit = _integer(
        filesystem_allocation_unit_bytes,
        "pilot filesystem allocation unit",
        minimum=MIN_FILESYSTEM_ALLOCATION_UNIT,
        maximum=MAX_FILESYSTEM_ALLOCATION_UNIT,
    )
    if (
        type(component_observations) is not dict
        or set(component_observations) != set(COMPONENTS)
    ):
        raise PersonaCapacityError(
            "component observations must cover every capacity component"
        )
    rows = {}
    for name in COMPONENTS:
        observation = component_observations[name]
        if type(observation) is not dict or set(observation) != {
            "observed_bytes", "observed_additional_inodes"
        }:
            raise PersonaCapacityError(
                f"{name} component observation fields are invalid"
            )
        observed_bytes = _integer(
            observation["observed_bytes"], f"{name} observed bytes"
        )
        observed_inodes = _integer(
            observation["observed_additional_inodes"],
            f"{name} observed additional inodes",
        )
        if observed_bytes == 0 and observed_inodes == 0:
            raise PersonaCapacityError(
                f"declared {name} evidence cannot be all-zero"
            )
        rows[name] = {
            "status": DECLARED_UNVERIFIED,
            "basis": COMPONENT_BASIS[name],
            "observed_units": contract["basis_values"][name],
            "observed_bytes": observed_bytes,
            "observed_additional_inodes": observed_inodes,
        }
    receipt = {
        "schema": PILOT_MEASUREMENT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": "pilot",
        "persona_id": persona_id,
        "pilot_persona_plan_sha256": contract["pilot_persona_plan_sha256"],
        "filesystem_allocation_unit_bytes": unit,
        "components": rows,
        "measurement_projection_sha256": None,
        "readback_status": MEASUREMENT_READBACK_REQUIRED,
        "approval_scope": "declared_capacity_measurement_only_not_readback",
    }
    receipt["measurement_projection_sha256"] = _digest(
        _pilot_measurement_projection(receipt)
    )
    _validate_pilot_measurement_receipt(receipt, persona_id)
    receipt_sha = _digest(receipt)
    amplification_rows = {
        name: {
            **rows[name],
            "pilot_receipt_sha256": receipt_sha,
        }
        for name in COMPONENTS
    }
    result = {
        "schema": AMPLIFICATION_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "persona_id": persona_id,
        "pilot_profile": "pilot",
        "pilot_persona_plan_sha256": contract["pilot_persona_plan_sha256"],
        "filesystem_allocation_unit": {
            "status": DECLARED_UNVERIFIED,
            "bytes": unit,
        },
        "pilot_measurement_receipt": receipt,
        "components": amplification_rows,
    }
    return _validate_amplification(result, persona_id)


def _project_components(cardinalities, evidence, headroom):
    basis_values = _basis_values(cardinalities)
    result = {}
    for name in COMPONENTS:
        measured = evidence["components"][name]
        target_units = basis_values[COMPONENT_BASIS[name]]
        if measured["status"] == "unknown":
            result[name] = {
                **measured,
                "target_units": target_units,
                "projected_bytes_before_headroom": None,
                "projected_bytes": None,
                "projected_additional_inodes_before_headroom": None,
                "projected_additional_inodes": None,
            }
            continue
        before_bytes = _ceil_multiply_divide(
            measured["observed_bytes"], target_units,
            measured["observed_units"], f"{name} byte amplification",
        )
        before_inodes = _ceil_multiply_divide(
            measured["observed_additional_inodes"], target_units,
            measured["observed_units"], f"{name} inode amplification",
        )
        result[name] = {
            **measured,
            "target_units": target_units,
            "projected_bytes_before_headroom": before_bytes,
            "projected_bytes": _ceil_multiply_divide(
                before_bytes, headroom["numerator"], headroom["denominator"],
                f"{name} byte headroom",
            ),
            "projected_additional_inodes_before_headroom": before_inodes,
            "projected_additional_inodes": _ceil_multiply_divide(
                before_inodes, headroom["numerator"], headroom["denominator"],
                f"{name} inode headroom",
            ),
        }
    return result


def _headroom(value):
    if type(value) is not dict or set(value) != {"numerator", "denominator"}:
        raise PersonaCapacityError("headroom must contain numerator and denominator")
    numerator = _integer(value["numerator"], "headroom numerator", minimum=1)
    denominator = _integer(value["denominator"], "headroom denominator", minimum=1)
    if numerator < denominator:
        raise PersonaCapacityError("capacity headroom must not reduce a measurement")
    return {"numerator": numerator, "denominator": denominator}


def build_persona_capacity_projection(
    persona_plan, *, profile=None, amplification=None,
    headroom=None,
):
    """Build one exact-cardinality, byte-evidence-aware projection."""
    headroom = _headroom(headroom or {"numerator": 5, "denominator": 4})
    person, projected, profile, plan_sha, input_kind = _normalize_person_plan(
        persona_plan, profile
    )
    evidence = _validate_amplification(amplification, person["persona_id"])
    cardinalities = _cardinalities(person, projected, profile)
    components = _project_components(cardinalities, evidence, headroom)
    unknown = [name for name in COMPONENTS if components[name]["status"] == "unknown"]
    allocation_unknown = (
        evidence["filesystem_allocation_unit"]["status"] == "unknown"
    )
    declared_unverified = any(
        components[name]["status"] == DECLARED_UNVERIFIED
        for name in COMPONENTS
    )
    if unknown or allocation_unknown:
        readiness = "blocked_missing_pilot_evidence"
    elif declared_unverified:
        readiness = "blocked_measurement_receipt_readback_required"
    else:  # No verified state is accepted until readback is implemented.
        readiness = "projection_ready_root_measurement_required"
    result = {
        "schema": "kcs.persona.capacity-person-projection/v1",
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": person["persona_id"],
        "input_kind": input_kind,
        "persona_plan_sha256": plan_sha,
        "headroom": headroom,
        "cardinalities": cardinalities,
        "amplification_evidence_sha256": _digest(evidence),
        "pilot_filesystem_allocation_unit": evidence[
            "filesystem_allocation_unit"
        ],
        "components": components,
        "unknown_components": unknown,
        "measurement_readback_state": (
            MEASUREMENT_READBACK_REQUIRED
            if declared_unverified else "not_applicable"
        ),
        "readiness": readiness,
    }
    _without_bool_or_float(result, "persona capacity projection")
    return result


def _aggregate(personas, replay_count):
    cardinality_sections = ("files", "scopes", "chunks", "events", "inodes")
    per_replay_cardinalities = {}
    for section in cardinality_sections:
        keys = personas[0]["cardinalities"][section]
        per_replay_cardinalities[section] = {
            key: _sum(
                (person["cardinalities"][section][key] for person in personas),
                f"suite {section}.{key}",
            )
            for key in keys
        }
    for key in ("exact_known_retained_inodes", "exact_known_transient_inodes"):
        per_replay_cardinalities["inodes"][key] = _add(
            per_replay_cardinalities["inodes"][key],
            SUITE_SHARED_KNOWN_INODES,
            f"suite shared {key}",
        )
    all_replay_cardinalities = {
        section: {
            key: _multiply(value, replay_count, f"all replay {section}.{key}")
            for key, value in values.items()
        }
        for section, values in per_replay_cardinalities.items()
    }
    unknown = sorted({
        f"{person['persona_id']}:{component}"
        for person in personas for component in person["unknown_components"]
    })
    unknown.extend(sorted(
        f"{person['persona_id']}:filesystem_allocation_unit"
        for person in personas
        if person["pilot_filesystem_allocation_unit"]["status"] == "unknown"
    ))
    bytes_known = not unknown
    if bytes_known:
        retained_per_replay_bytes = _sum((
            person["components"][name]["projected_bytes"]
            for person in personas for name in RETAINED_COMPONENTS
        ), "retained bytes per replay")
        retained_per_replay_extra_inodes = _sum((
            person["components"][name]["projected_additional_inodes"]
            for person in personas for name in RETAINED_COMPONENTS
        ), "retained additional inodes per replay")
        staging_bytes = max(
            person["components"]["staging"]["projected_bytes"]
            for person in personas
        )
        staging_inodes = max(_add(
            person["cardinalities"]["inodes"]["exact_known_staging_inodes"],
            person["components"]["staging"]["projected_additional_inodes"],
            f"{person['persona_id']} staging inodes",
        ) for person in personas)
        # W5 regular events run for every persona before the first purge, so
        # all persona transient additions coexist within one replay.
        transient_bytes = _sum((
            person["components"]["transient"]["projected_bytes"]
            for person in personas
        ), "transient bytes per replay")
        transient_inodes = _sum((
            _add(
                person["cardinalities"]["inodes"][
                    "exact_known_transient_inodes"
                ] - person["cardinalities"]["inodes"][
                    "exact_known_retained_inodes"
                ],
                person["components"]["transient"][
                    "projected_additional_inodes"
                ],
                f"{person['persona_id']} transient inodes",
            )
            for person in personas
        ), "transient additional inodes per replay")
        known_inodes = per_replay_cardinalities["inodes"][
            "exact_known_retained_inodes"
        ]
        retained_per_replay_inodes = _add(
            known_inodes, retained_per_replay_extra_inodes,
            "retained inodes per replay",
        )
        all_retained_bytes = _multiply(
            retained_per_replay_bytes, replay_count, "all replay retained bytes"
        )
        all_retained_inodes = _multiply(
            retained_per_replay_inodes, replay_count, "all replay retained inodes"
        )
        peak_extra_bytes = max(staging_bytes, transient_bytes)
        peak_extra_inodes = max(staging_inodes, transient_inodes)
        payload_peak_bytes = _add(
            all_retained_bytes, peak_extra_bytes, "all replay payload peak bytes"
        )
        projected_peak_inodes = _add(
            all_retained_inodes, peak_extra_inodes, "all replay peak inodes"
        )
    else:
        retained_per_replay_bytes = retained_per_replay_inodes = None
        staging_bytes = staging_inodes = None
        transient_bytes = transient_inodes = None
        all_retained_bytes = all_retained_inodes = None
        peak_extra_bytes = peak_extra_inodes = None
        payload_peak_bytes = projected_peak_inodes = None
    return {
        "per_replay": {
            "cardinalities": per_replay_cardinalities,
            "suite_shared_known_inodes": SUITE_SHARED_KNOWN_INODES,
            "retained_payload_bytes": retained_per_replay_bytes,
            "retained_inodes": retained_per_replay_inodes,
            "sequential_persona_staging_peak_bytes": staging_bytes,
            "sequential_persona_staging_peak_inodes": staging_inodes,
            "coexisting_w5_transient_extra_bytes": transient_bytes,
            "coexisting_w5_transient_extra_inodes": transient_inodes,
        },
        "all_replays": {
            "replay_count": replay_count,
            "cardinalities": all_replay_cardinalities,
            "retained_payload_bytes": all_retained_bytes,
            "retained_inodes": all_retained_inodes,
            "peak_extra_bytes": peak_extra_bytes,
            "peak_extra_inodes": peak_extra_inodes,
            "payload_peak_bytes_before_filesystem_allocation": payload_peak_bytes,
            "peak_inodes": projected_peak_inodes,
        },
        "unknown_evidence": unknown,
    }


def build_capacity_plan(
    persona_plans, *, profile=None, amplifications=None,
    headroom=None, replay_count=spec.REPLAY_COUNT,
):
    """Compose bounded one-person projections into a root-independent plan."""
    if type(persona_plans) not in (list, tuple) or not persona_plans:
        raise PersonaCapacityError("persona_plans must be a non-empty array")
    replay_count = _integer(replay_count, "replay_count", minimum=1)
    if replay_count > spec.REPLAY_COUNT:
        raise PersonaCapacityError("replay_count exceeds the three-replay contract")
    headroom = _headroom(headroom or {"numerator": 5, "denominator": 4})
    if amplifications is None:
        amplifications = {}
    if type(amplifications) is not dict:
        raise PersonaCapacityError("amplifications must be keyed by persona id")
    personas = []
    seen = set()
    resolved_profile = profile
    for value in persona_plans:
        if type(value) is not dict:
            raise PersonaCapacityError("each persona plan must be an object")
        persona_id = value.get("persona_id")
        if value.get("schema") == PERSONA_WRAPPER_SCHEMA:
            persona_id = value.get("persona_id")
        if type(persona_id) is not str or persona_id in seen:
            raise PersonaCapacityError("persona plan identities must be unique")
        seen.add(persona_id)
        projection = build_persona_capacity_projection(
            value,
            profile=resolved_profile,
            amplification=amplifications.get(persona_id),
            headroom=headroom,
        )
        if resolved_profile is None:
            resolved_profile = projection["profile"]
        if projection["profile"] != resolved_profile:
            raise PersonaCapacityError("capacity plan mixes profiles")
        personas.append(projection)
    if set(amplifications) - seen:
        raise PersonaCapacityError("amplification supplied for an absent persona")
    personas.sort(key=lambda value: value["persona_id"])
    aggregate = _aggregate(personas, replay_count)
    missing_personas = sorted(EXPECTED_PERSONA_ID_SET - seen)
    unexpected_personas = sorted(seen - EXPECTED_PERSONA_ID_SET)
    blockers = []
    if resolved_profile == "full" and replay_count != spec.REPLAY_COUNT:
        blockers.append("full_requires_three_replays")
    if resolved_profile == "full" and (missing_personas or unexpected_personas):
        blockers.append("full_requires_all_twenty_personas")
    if aggregate["unknown_evidence"]:
        blockers.append("pilot_amplification_or_allocation_unit_unknown")
    if any(
        person["measurement_readback_state"] == MEASUREMENT_READBACK_REQUIRED
        for person in personas
    ):
        blockers.append("pilot_measurement_receipt_readback_required")
    readiness = (
        "projection_ready_root_measurement_required"
        if not blockers else "blocked"
    )
    input_inventory = [
        {
            "persona_id": person["persona_id"],
            "persona_plan_sha256": person["persona_plan_sha256"],
            "amplification_evidence_sha256": person[
                "amplification_evidence_sha256"
            ],
        }
        for person in personas
    ]
    result = {
        "schema": CAPACITY_PLAN_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": resolved_profile,
        "root_binding": "forbidden_in_projection",
        "replay_count": replay_count,
        "headroom": headroom,
        "input_inventory": input_inventory,
        "input_inventory_sha256": _digest(input_inventory),
        "personas": personas,
        **aggregate,
        "formal_inventory": {
            "expected_personas": len(EXPECTED_PERSONA_IDS),
            "supplied_personas": len(personas),
            "missing_persona_ids": missing_personas,
            "unexpected_persona_ids": unexpected_personas,
        },
        "blockers": blockers,
        "readiness": readiness,
        "contracts": {
            "byte_evidence_kind": (
                "pilot_declared_rational_amplification_readback_required"
            ),
            "unknown_byte_evidence": "json_null_not_zero",
            "filesystem_binding_phase": "root_bound_receipt_only",
            "staging_concurrency": "one_person_at_a_time",
            "w5_transient_concurrency": "all_personas_before_first_purge",
            "planned_chunks_are_not_kcs_attestation": "required",
            "actual_kcs_attestation": "false",
            "physical_write_authorization": "false",
        },
    }
    _without_bool_or_float(result, "capacity plan")
    return result


def capacity_plan_sha256(plan):
    return _digest(plan)


def validate_capacity_plan(
    plan, persona_plans, *, profile=None, amplifications=None,
    headroom=None, replay_count=spec.REPLAY_COUNT,
):
    _without_bool_or_float(plan, "capacity plan")
    expected = build_capacity_plan(
        persona_plans, profile=profile, amplifications=amplifications,
        headroom=headroom, replay_count=replay_count,
    )
    if plan != expected or _digest(plan) != _digest(expected):
        raise PersonaCapacityError("capacity plan differs from canonical expansion")
    return plan


def _limits(byte_cap, inode_cap, reserve_bytes, reserve_inodes):
    return {
        "byte_cap": _integer(byte_cap, "byte cap", minimum=1),
        "inode_cap": _integer(inode_cap, "inode cap", minimum=1),
        "reserve_bytes": _integer(reserve_bytes, "reserve bytes"),
        "reserve_inodes": _integer(reserve_inodes, "reserve inodes"),
    }


def _canonical_destination_root(value):
    if type(value) is not str:
        raise PersonaCapacityError(
            "destination_root must be an absolute non-root path"
        )
    root = Path(value)
    if (
        not root.is_absolute()
        or root == Path("/")
        or str(root) != value
        or any(component in (".", "..") for component in root.parts)
    ):
        raise PersonaCapacityError(
            "destination_root must be an absolute non-root path"
        )
    return value


def _root_measurement_projection(measurement):
    return {
        "domain": ROOT_MEASUREMENT_PROJECTION_DOMAIN,
        "fixture_id": spec.FIXTURE_ID,
        "destination_root": measurement["destination_root"],
        "filesystem": measurement["filesystem"],
        "readback_status": measurement["readback_status"],
    }


def build_declared_root_capacity_measurement(
    *, destination_root, filesystem_device,
    filesystem_allocation_unit_bytes, free_bytes, free_inodes,
):
    """Bind caller values as an unverified projection, never as a probe result."""
    root = _canonical_destination_root(destination_root)
    result = {
        "schema": ROOT_MEASUREMENT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "destination_root": root,
        "filesystem": {
            "device": _integer(filesystem_device, "filesystem device"),
            "allocation_unit_bytes": _integer(
                filesystem_allocation_unit_bytes,
                "destination filesystem allocation unit",
                minimum=MIN_FILESYSTEM_ALLOCATION_UNIT,
                maximum=MAX_FILESYSTEM_ALLOCATION_UNIT,
            ),
            "free_bytes": _integer(free_bytes, "free bytes"),
            "free_inodes": _integer(free_inodes, "free inodes"),
        },
        "measurement_projection_sha256": None,
        "readback_status": ROOT_MEASUREMENT_READBACK_REQUIRED,
        "approval_scope": "caller_declared_projection_only_not_filesystem_readback",
    }
    result["measurement_projection_sha256"] = _digest(
        _root_measurement_projection(result)
    )
    return _validate_root_capacity_measurement(result)


def _validate_root_capacity_measurement(
    measurement, *, expected_destination_root=None,
):
    _without_bool_or_float(measurement, "root capacity measurement")
    fields = {
        "schema", "schema_version", "fixture_id", "destination_root",
        "filesystem", "measurement_projection_sha256", "readback_status",
        "approval_scope",
    }
    if type(measurement) is not dict or set(measurement) != fields:
        raise PersonaCapacityError("root capacity measurement fields are invalid")
    root = _canonical_destination_root(measurement["destination_root"])
    if expected_destination_root is not None:
        expected_root = _canonical_destination_root(expected_destination_root)
        if root != expected_root:
            raise PersonaCapacityError("root capacity measurement destination differs")
    if (
        measurement["schema"] != ROOT_MEASUREMENT_SCHEMA
        or measurement["schema_version"] != SCHEMA_VERSION
        or measurement["fixture_id"] != spec.FIXTURE_ID
        or measurement["readback_status"]
        != ROOT_MEASUREMENT_READBACK_REQUIRED
        or measurement["approval_scope"]
        != "caller_declared_projection_only_not_filesystem_readback"
    ):
        raise PersonaCapacityError("root capacity measurement binding differs")
    filesystem = measurement["filesystem"]
    if type(filesystem) is not dict or set(filesystem) != {
        "device", "allocation_unit_bytes", "free_bytes", "free_inodes",
    }:
        raise PersonaCapacityError("root capacity filesystem fields are invalid")
    _integer(filesystem["device"], "filesystem device")
    _integer(
        filesystem["allocation_unit_bytes"],
        "destination filesystem allocation unit",
        minimum=MIN_FILESYSTEM_ALLOCATION_UNIT,
        maximum=MAX_FILESYSTEM_ALLOCATION_UNIT,
    )
    _integer(filesystem["free_bytes"], "free bytes")
    _integer(filesystem["free_inodes"], "free inodes")
    expected_sha = _digest(_root_measurement_projection(measurement))
    if measurement["measurement_projection_sha256"] != expected_sha:
        raise PersonaCapacityError("root capacity measurement digest differs")
    return measurement


def check_root_bound_capacity(
    plan, persona_plans, *, root_measurement,
    byte_cap, inode_cap, reserve_bytes, reserve_inodes,
    profile=None, amplifications=None, headroom=None,
    replay_count=spec.REPLAY_COUNT,
):
    """Compute a blocked projection after rebuilding every canonical input."""
    validate_capacity_plan(
        plan,
        persona_plans,
        profile=profile,
        amplifications=amplifications,
        headroom=headroom,
        replay_count=replay_count,
    )
    measurement = _validate_root_capacity_measurement(root_measurement)
    filesystem = measurement["filesystem"]
    unit = filesystem["allocation_unit_bytes"]
    free_bytes = filesystem["free_bytes"]
    free_inodes = filesystem["free_inodes"]
    limits = _limits(byte_cap, inode_cap, reserve_bytes, reserve_inodes)
    blockers = set(plan["blockers"])
    allowed_projection_blockers = {
        "pilot_measurement_receipt_readback_required",
    }
    if blockers - allowed_projection_blockers:
        raise PersonaCapacityError(
            "capacity plan is not byte-projectable: "
            + ", ".join(sorted(blockers - allowed_projection_blockers))
        )
    peak_inodes = plan["all_replays"]["peak_inodes"]
    payload_peak = plan["all_replays"][
        "payload_peak_bytes_before_filesystem_allocation"
    ]
    if type(peak_inodes) is not int or type(payload_peak) is not int:
        raise PersonaCapacityError("capacity projection contains unknown peak values")
    allocation_allowance = _multiply(
        peak_inodes, unit, "filesystem allocation allowance"
    )
    required_bytes = _add(
        payload_peak, allocation_allowance, "required peak bytes"
    )
    problems = []
    if required_bytes > limits["byte_cap"]:
        problems.append("byte_cap")
    if peak_inodes > limits["inode_cap"]:
        problems.append("inode_cap")
    free_bytes_after = free_bytes - required_bytes
    free_inodes_after = free_inodes - peak_inodes
    if free_bytes_after < limits["reserve_bytes"]:
        problems.append("reserve_bytes")
    if free_inodes_after < limits["reserve_inodes"]:
        problems.append("reserve_inodes")
    if problems:
        raise PersonaCapacityError(
            "capacity preflight failed: " + ", ".join(problems)
        )
    return {
        "required_peak_bytes": required_bytes,
        "required_peak_inodes": peak_inodes,
        "payload_peak_bytes": payload_peak,
        "filesystem_allocation_allowance_bytes": allocation_allowance,
        "free_bytes_after": free_bytes_after,
        "free_inodes_after": free_inodes_after,
        "reserve_bytes": limits["reserve_bytes"],
        "reserve_inodes": limits["reserve_inodes"],
        "blocking_evidence": sorted({
            *blockers,
            ROOT_MEASUREMENT_READBACK_REQUIRED,
        }),
        "capacity_state": "blocked_measurement_receipt_readback_required",
        "physical_write_authorization": "false",
        "actual_kcs_attestation": "false",
    }


def build_capacity_receipt(
    plan, persona_plans, *, root_measurement, suite_manifest_sha256,
    byte_cap, inode_cap, reserve_bytes, reserve_inodes,
    profile=None, amplifications=None, headroom=None,
    replay_count=spec.REPLAY_COUNT,
):
    """Build a blocked root projection; this is never write authorization."""
    measurement = _validate_root_capacity_measurement(root_measurement)
    suite_sha = _sha256(suite_manifest_sha256, "suite manifest digest")
    limits = _limits(byte_cap, inode_cap, reserve_bytes, reserve_inodes)
    check = check_root_bound_capacity(
        plan,
        persona_plans,
        root_measurement=measurement,
        profile=profile,
        amplifications=amplifications,
        headroom=headroom,
        replay_count=replay_count,
        **limits,
    )
    result = {
        "schema": CAPACITY_RECEIPT_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": plan["profile"],
        "destination_root": measurement["destination_root"],
        "root_measurement": measurement,
        "root_measurement_sha256": _digest(measurement),
        "capacity_plan_sha256": capacity_plan_sha256(plan),
        "input_inventory_sha256": plan["input_inventory_sha256"],
        "suite_manifest_sha256": suite_sha,
        "limits": limits,
        "check": check,
        "approval_scope": "capacity_only_not_physical_write_authorization",
        "actual_kcs_attestation": "false",
    }
    _without_bool_or_float(result, "capacity receipt")
    return result


def validate_capacity_receipt(
    receipt, plan, persona_plans, *, expected_destination_root,
    expected_suite_manifest_sha256, profile=None, amplifications=None,
    headroom=None, replay_count=spec.REPLAY_COUNT,
):
    """Rebuild plan, measurement projection, arithmetic, caps, and receipt."""
    validate_capacity_plan(
        plan,
        persona_plans,
        profile=profile,
        amplifications=amplifications,
        headroom=headroom,
        replay_count=replay_count,
    )
    _without_bool_or_float(receipt, "capacity receipt")
    fields = {
        "schema", "schema_version", "fixture_id", "profile",
        "destination_root", "root_measurement", "root_measurement_sha256",
        "capacity_plan_sha256",
        "input_inventory_sha256", "suite_manifest_sha256", "limits",
        "check", "approval_scope", "actual_kcs_attestation",
    }
    if type(receipt) is not dict or set(receipt) != fields:
        raise PersonaCapacityError("capacity receipt has an invalid field set")
    if (
        receipt["schema"] != CAPACITY_RECEIPT_SCHEMA
        or receipt["schema_version"] != SCHEMA_VERSION
        or receipt["fixture_id"] != spec.FIXTURE_ID
        or receipt["profile"] != plan.get("profile")
        or receipt["approval_scope"]
        != "capacity_only_not_physical_write_authorization"
        or receipt["actual_kcs_attestation"] != "false"
        or receipt["destination_root"]
        != _canonical_destination_root(expected_destination_root)
        or receipt["capacity_plan_sha256"] != capacity_plan_sha256(plan)
        or receipt["input_inventory_sha256"] != plan["input_inventory_sha256"]
        or receipt["suite_manifest_sha256"]
        != _sha256(expected_suite_manifest_sha256, "suite manifest digest")
    ):
        raise PersonaCapacityError("capacity receipt binding differs")
    measurement = _validate_root_capacity_measurement(
        receipt["root_measurement"],
        expected_destination_root=expected_destination_root,
    )
    if receipt["root_measurement_sha256"] != _digest(measurement):
        raise PersonaCapacityError("capacity receipt measurement digest differs")
    expected_check = check_root_bound_capacity(
        plan,
        persona_plans,
        root_measurement=measurement,
        profile=profile,
        amplifications=amplifications,
        headroom=headroom,
        replay_count=replay_count,
        **receipt["limits"],
    )
    if receipt["check"] != expected_check:
        raise PersonaCapacityError("capacity receipt arithmetic differs")
    return receipt
