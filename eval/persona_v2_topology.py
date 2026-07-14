"""Canonical, non-authorizing topology sidecar for persona-PC fidelity v2.

The authored path and activity-unit hypotheses live in
``persona_v2_topology_data``.  This module performs only deterministic integer
normalization, exact validation, profile projections, and canonical hashing.
It never renders files, writes a root, or claims that the later joint source
allocation is feasible.
"""

import copy
import functools
import hashlib
import re
from pathlib import PurePosixPath

from eval import persona_v2_contract as envelope
from eval.persona_v2_topology_data import (
    SCOPE_ROW_FIELDS as DATA_SCOPE_ROW_FIELDS,
    SECONDARY_FUNCTIONAL_SLOTS as DATA_SECONDARY_FUNCTIONAL_SLOTS,
    TOPOLOGY_INPUT_ROWS,
)


ARTIFACT_SCHEMA = "kcs.persona.pc-topology/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-topology"
MAX_TOPOLOGY_BYTES = 512 * 1024
MAX_PATH_BYTES = 240
MAX_COMPONENT_BYTES = 80
MAX_SLOT_BYTES = 80
MAX_LOAD_BASIS_ID_BYTES = 80
PHYSICAL_MINIMUM_BP = 50
CONTRIBUTOR_MINIMUM_BP = 25
ACTIVITY_UNIT_MINIMUM = 1
ACTIVITY_UNIT_MAXIMUM = 100
WEIGHT_NORMALIZATION_ALGORITHM_ID = "per-scope-floor-then-hamilton-residual-v1"
WEIGHT_NORMALIZATION_FORMULA = (
    "weight_i=minimum_bp+hamilton(group_bp-(minimum_bp*scope_count),activity_units)_i"
)
PROFILE_PROJECTION_ALGORITHM_ID = "group-subtotal-hamilton-v1"
MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE = 70
REQUIRED_SCOPE_HISTORY_COHORTS = ("P", "X", "Y", "N")
MIN_CONTRIBUTOR_SOURCES_PER_SCOPE = len(REQUIRED_SCOPE_HISTORY_COHORTS)
PRIMARY_SCOPE_COUNT = 12
SECONDARY_SCOPE_COUNT = 8
SCOPES_PER_PERSONA = PRIMARY_SCOPE_COUNT + SECONDARY_SCOPE_COUNT
SECONDARY_FUNCTIONAL_SLOTS = (
    "desktop-active",
    "documents-reference",
    "downloads-inbox",
    "downloads-exports",
    "cloud-personal",
    "cloud-team",
    "mail-recent",
    "archive-closed",
)
SCOPE_ROW_FIELDS = (
    "functional_slot",
    "relative_path",
    "physical_activity_units",
    "contributor_demand_units",
    "load_basis_id",
)

_COMPONENT_RE = re.compile(r"[a-z0-9][a-z0-9-]*\Z")
_SLOT_RE = re.compile(r"[a-z][a-z0-9-]*\Z")
_BASIS_RE = re.compile(r"[a-z][a-z0-9-]*\Z")
_WINDOWS_RESERVED = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


class PersonaV2TopologyError(ValueError):
    """Raised when topology data or a projection violates the v2 contract."""


def _require_int(value, label, *, minimum=None, maximum=None):
    if (
        type(value) is not int
        or (minimum is not None and value < minimum)
        or (maximum is not None and value > maximum)
    ):
        bounds = []
        if minimum is not None:
            bounds.append(f">= {minimum}")
        if maximum is not None:
            bounds.append(f"<= {maximum}")
        raise PersonaV2TopologyError(
            f"{label} must be an integer {' and '.join(bounds)}"
        )
    return value


def _bounded_hamilton(group_bp, units, minimum_bp):
    _require_int(group_bp, "group_bp", minimum=1)
    _require_int(minimum_bp, "minimum_bp", minimum=1)
    if type(units) is not tuple or not units:
        raise PersonaV2TopologyError("activity units must be a non-empty tuple")
    if any(type(unit) is not int or unit <= 0 for unit in units):
        raise PersonaV2TopologyError("activity units must be positive integers")
    baseline = minimum_bp * len(units)
    if baseline > group_bp:
        raise PersonaV2TopologyError("minimum basis points exceed group subtotal")
    extras = envelope.largest_remainder(group_bp - baseline, units)
    result = tuple(minimum_bp + value for value in extras)
    if sum(result) != group_bp or any(value < minimum_bp for value in result):
        raise PersonaV2TopologyError("bounded Hamilton normalization failed")
    return result


def _ascii_length(value, label):
    if type(value) is not str:
        raise PersonaV2TopologyError(f"{label} must be an ASCII string")
    try:
        return len(value.encode("ascii", "strict"))
    except UnicodeEncodeError:
        raise PersonaV2TopologyError(f"{label} must be an ASCII string") from None


def _validate_relative_path(value):
    if not value or _ascii_length(value, "scope path") > MAX_PATH_BYTES:
        raise PersonaV2TopologyError(
            f"scope path must be portable ASCII <= {MAX_PATH_BYTES} bytes"
        )
    if value.startswith("/") or value.endswith("/") or "//" in value or "\\" in value:
        raise PersonaV2TopologyError(f"scope path is not canonical relative POSIX: {value!r}")
    parsed = PurePosixPath(value)
    if not parsed.parts or str(parsed) != value:
        raise PersonaV2TopologyError(f"scope path normalizes differently: {value!r}")
    for component in parsed.parts:
        if (
            len(component.encode("ascii")) > MAX_COMPONENT_BYTES
            or _COMPONENT_RE.fullmatch(component) is None
            or component.casefold() in _WINDOWS_RESERVED
        ):
            raise PersonaV2TopologyError(f"non-portable scope component: {component!r}")
    return tuple(parsed.parts)


def _row_map():
    if DATA_SCOPE_ROW_FIELDS != SCOPE_ROW_FIELDS:
        raise PersonaV2TopologyError("topology data scope-row schema differs")
    if DATA_SECONDARY_FUNCTIONAL_SLOTS != SECONDARY_FUNCTIONAL_SLOTS:
        raise PersonaV2TopologyError("topology data secondary slot contract differs")
    if type(TOPOLOGY_INPUT_ROWS) is not tuple:
        raise PersonaV2TopologyError("topology input rows must be a tuple")
    result = {}
    for row in TOPOLOGY_INPUT_ROWS:
        if type(row) is not tuple or len(row) != 2:
            raise PersonaV2TopologyError("persona topology row must have exactly two fields")
        persona_id, scopes = row
        if type(persona_id) is not str or persona_id in result:
            raise PersonaV2TopologyError("persona topology IDs must be unique strings")
        if type(scopes) is not tuple or len(scopes) != SCOPES_PER_PERSONA:
            raise PersonaV2TopologyError(f"{persona_id} must have exactly twenty scope rows")
        result[persona_id] = scopes
    if tuple(result) != envelope.PERSONA_IDS:
        raise PersonaV2TopologyError("topology personas are missing or out of canonical order")
    return result


def _normalize_persona(persona_id, input_scopes):
    metadata = envelope.get_persona(persona_id)
    primary_bp = metadata["primary_share_pct"] * 100
    secondary_bp = 10_000 - primary_bp

    parsed = []
    for ordinal, raw in enumerate(input_scopes, start=1):
        if type(raw) is not tuple or len(raw) != 5:
            raise PersonaV2TopologyError(f"{persona_id} scope {ordinal} must have five fields")
        functional_slot, relative_path, physical_units, contributor_units, load_basis_id = raw
        if (
            type(functional_slot) is not str
            or _ascii_length(functional_slot, "functional slot") > MAX_SLOT_BYTES
            or _SLOT_RE.fullmatch(functional_slot) is None
        ):
            raise PersonaV2TopologyError(f"invalid functional slot: {persona_id}/{ordinal}")
        if (
            type(load_basis_id) is not str
            or _ascii_length(load_basis_id, "load basis ID") > MAX_LOAD_BASIS_ID_BYTES
            or _BASIS_RE.fullmatch(load_basis_id) is None
        ):
            raise PersonaV2TopologyError(f"invalid load basis ID: {persona_id}/{ordinal}")
        _require_int(
            physical_units,
            "physical activity units",
            minimum=ACTIVITY_UNIT_MINIMUM,
            maximum=ACTIVITY_UNIT_MAXIMUM,
        )
        _require_int(
            contributor_units,
            "contributor demand units",
            minimum=ACTIVITY_UNIT_MINIMUM,
            maximum=ACTIVITY_UNIT_MAXIMUM,
        )
        path_parts = _validate_relative_path(relative_path)
        kind = "primary" if ordinal <= PRIMARY_SCOPE_COUNT else "secondary"
        if kind == "secondary":
            expected_slot = SECONDARY_FUNCTIONAL_SLOTS[ordinal - PRIMARY_SCOPE_COUNT - 1]
            if functional_slot != expected_slot:
                raise PersonaV2TopologyError(
                    f"secondary functional slot order differs: {persona_id}/{ordinal}"
                )
        parsed.append({
            "contributor_demand_units": contributor_units,
            "functional_slot": functional_slot,
            "kind": kind,
            "load_basis_id": load_basis_id,
            "ordinal": ordinal,
            "path_parts": path_parts,
            "physical_activity_units": physical_units,
            "relative_path": relative_path,
            "scope_key": f"{persona_id}-scope-{ordinal:02d}",
        })

    if len({row["functional_slot"] for row in parsed}) != SCOPES_PER_PERSONA:
        raise PersonaV2TopologyError(f"all functional slots must be unique: {persona_id}")

    physical_weights = []
    contributor_weights = []
    for start, stop, subtotal in (
        (0, PRIMARY_SCOPE_COUNT, primary_bp),
        (PRIMARY_SCOPE_COUNT, SCOPES_PER_PERSONA, secondary_bp),
    ):
        group = parsed[start:stop]
        physical_weights.extend(_bounded_hamilton(
            subtotal,
            tuple(row["physical_activity_units"] for row in group),
            PHYSICAL_MINIMUM_BP,
        ))
        contributor_weights.extend(_bounded_hamilton(
            subtotal,
            tuple(row["contributor_demand_units"] for row in group),
            CONTRIBUTOR_MINIMUM_BP,
        ))

    scopes = []
    for row, physical_bp, contributor_bp in zip(parsed, physical_weights, contributor_weights):
        value = dict(row)
        del value["path_parts"]
        value["contributor_chunk_weight_bp"] = contributor_bp
        value["physical_file_weight_bp"] = physical_bp
        scopes.append(value)

    realized_dmax = max(len(row["path_parts"]) for row in parsed)
    if realized_dmax != metadata["formal_dmax"]:
        raise PersonaV2TopologyError(
            f"realized Dmax differs from envelope: {persona_id} {realized_dmax} != {metadata['formal_dmax']}"
        )
    primary_paths = {row["relative_path"] for row in parsed[:PRIMARY_SCOPE_COUNT]}
    secondary_paths = {row["relative_path"] for row in parsed[PRIMARY_SCOPE_COUNT:]}
    if metadata["representative_primary_scope"] not in primary_paths:
        raise PersonaV2TopologyError(f"representative primary path is absent: {persona_id}")
    if metadata["representative_secondary_scope"] not in secondary_paths:
        raise PersonaV2TopologyError(f"representative secondary path is absent: {persona_id}")

    return {
        "formal_dmax": metadata["formal_dmax"],
        "persona_id": persona_id,
        "primary_share_bp": primary_bp,
        "realized_dmax": realized_dmax,
        "role": metadata["role"],
        "scopes": scopes,
        "secondary_share_bp": secondary_bp,
    }


def _reject_path_and_vector_clones(personas):
    path_rows = []
    physical_vectors = []
    contributor_vectors = []
    for persona in personas:
        paths = [scope["relative_path"] for scope in persona["scopes"]]
        parts = [tuple(path.split("/")) for path in paths]
        path_rows.extend((persona["persona_id"], path, tuple_parts) for path, tuple_parts in zip(paths, parts))
        physical_vectors.append(tuple(scope["physical_file_weight_bp"] for scope in persona["scopes"]))
        contributor_vectors.append(tuple(scope["contributor_chunk_weight_bp"] for scope in persona["scopes"]))
        if physical_vectors[-1] == contributor_vectors[-1]:
            raise PersonaV2TopologyError(f"physical/chunk vectors are cloned: {persona['persona_id']}")

    folded = [path.casefold() for _, path, _ in path_rows]
    if len(folded) != len(set(folded)):
        raise PersonaV2TopologyError("scope paths must be globally casefold unique")
    for index, (_, _, left) in enumerate(path_rows):
        for _, _, right in path_rows[index + 1:]:
            if len(left) < len(right) and right[:len(left)] == left:
                raise PersonaV2TopologyError("scope paths may not be ancestor/descendant")
            if len(right) < len(left) and left[:len(right)] == right:
                raise PersonaV2TopologyError("scope paths may not be ancestor/descendant")

    for label, vectors in (
        ("physical", physical_vectors),
        ("contributor", contributor_vectors),
    ):
        if len(vectors) != len(set(vectors)):
            raise PersonaV2TopologyError(f"{label} load vectors must be persona-specific")
        sorted_vectors = [tuple(sorted(vector)) for vector in vectors]
        if len(sorted_vectors) != len(set(sorted_vectors)):
            raise PersonaV2TopologyError(f"{label} load vectors may not be permutation clones")


@functools.lru_cache(maxsize=1)
def _canonical_contract_value():
    envelope_value = envelope.build_envelope_contract()
    envelope_required_cohorts = tuple(
        envelope_value["history_cohort_contract"][
            "coverage_required_in_all_twenty_scopes"
        ]
    )
    if envelope_required_cohorts != REQUIRED_SCOPE_HISTORY_COHORTS:
        raise PersonaV2TopologyError("envelope history scope-coverage contract differs")
    envelope_max_quota = max(
        maximum for _, maximum in envelope.DENSITY_BUCKET_BOUNDS.values()
    )
    if envelope_max_quota != MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE:
        raise PersonaV2TopologyError("envelope maximum contributor quota differs")
    personas = [
        _normalize_persona(persona_id, scopes)
        for persona_id, scopes in _row_map().items()
    ]
    _reject_path_and_vector_clones(personas)
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            **copy.deepcopy(envelope_value["authority"]),
            "activity_unit_review_receipt_bound": False,
            "joint_allocation_proved": False,
        },
        "completion_scope": "exact-topology-only-not-g0-root",
        "envelope_contract_sha256": envelope.envelope_contract_sha256(envelope_value),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "personas": personas,
        "policy": {
            "canonical_limits": {
                "max_component_bytes": MAX_COMPONENT_BYTES,
                "max_load_basis_id_bytes": MAX_LOAD_BASIS_ID_BYTES,
                "max_path_bytes": MAX_PATH_BYTES,
                "max_slot_bytes": MAX_SLOT_BYTES,
                "max_topology_bytes": MAX_TOPOLOGY_BYTES,
            },
            "contributor_minimum_bp": CONTRIBUTOR_MINIMUM_BP,
            "cross_persona_diversity": {
                "ancestor_relationships_forbidden": True,
                "casefold_unique_paths": True,
                "purpose": "anti-template synthetic diversity across independent roots",
            },
            "activity_unit_rubric": {
                "bands": [
                    {"id": "low", "max": 39, "min": 1},
                    {"id": "moderate", "max": 59, "min": 40},
                    {"id": "high", "max": 79, "min": 60},
                    {"id": "very-high", "max": 100, "min": 80},
                ],
                "contributor_dimension": (
                    "relative contract-chunk demand within one persona and scope kind"
                ),
                "physical_dimension": (
                    "relative file creation-import-retention pressure within one persona and scope kind"
                ),
                "scale_max": ACTIVITY_UNIT_MAXIMUM,
                "scale_min": ACTIVITY_UNIT_MINIMUM,
                "status": "authored-hypothesis-not-observed-or-empirically-calibrated",
                "within_band_precision": (
                    "canonical authored interpolation only, not measurement"
                ),
            },
            "activity_unit_review": {
                "receipt_bound": False,
                "required_for_g0_freeze": True,
            },
            "load_units_status": (
                "authored-stress-design-hypothesis-not-observed-statistics"
            ),
            "physical_minimum_bp": PHYSICAL_MINIMUM_BP,
            "primary_scope_count": PRIMARY_SCOPE_COUNT,
            "profile_chunk_targets": {
                profile: envelope_value["profiles"][profile]["target_chunks_per_person"]
                for profile in ("pilot", "full")
            },
            "profile_projection": {
                "algorithm_id": PROFILE_PROJECTION_ALGORITHM_ID,
                "tie_break": envelope.APPORTIONMENT_TIE_BREAK,
            },
            "secondary_functional_slots": list(SECONDARY_FUNCTIONAL_SLOTS),
            "secondary_scope_count": SECONDARY_SCOPE_COUNT,
            "source_bound": {
                "lower_formula": "max(required_cohort_count,ceil(scope_chunks/max_chunks_per_source))",
                "max_chunks_per_source": MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
                "required_cohorts_with_positive_source_per_scope": list(
                    envelope_required_cohorts
                ),
                "required_cohort_count": MIN_CONTRIBUTOR_SOURCES_PER_SCOPE,
                "upper_formula": "min(scope_chunks,scope_physical_files)",
            },
            "tiny_chunk_rule": "three-per-routed-contributor-source-not-fixed-total",
            "weight_normalization": {
                "algorithm_id": WEIGHT_NORMALIZATION_ALGORITHM_ID,
                "formula": WEIGHT_NORMALIZATION_FORMULA,
                "residual_apportionment_algorithm_id": envelope.APPORTIONMENT_ALGORITHM_ID,
                "tie_break": envelope.APPORTIONMENT_TIE_BREAK,
            },
            "within_persona_path_safety": {
                "ancestor_relationships_forbidden": True,
                "casefold_unique_paths": True,
            },
        },
        "remaining_g0_blockers": copy.deepcopy(envelope_value["blockers"])
        + ["activity_unit_rubric_review_receipt_not_bound"],
        "topology_complete": True,
    }


def build_topology_contract():
    """Build a detached copy of the exact-400-row topology artifact."""
    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        raw = envelope.canonical_json_bytes(value)
    except envelope.PersonaV2ContractError as exc:
        raise PersonaV2TopologyError(f"invalid canonical topology value: {exc}") from exc
    if len(raw) > MAX_TOPOLOGY_BYTES:
        raise PersonaV2TopologyError("v2 topology exceeds 512 KiB canonical cap")
    return raw


def validate_topology_contract(value):
    if type(value) is not dict:
        raise PersonaV2TopologyError("v2 topology must be an object")
    actual_raw = canonical_json_bytes(value)
    if actual_raw != canonical_json_bytes(_canonical_contract_value()):
        raise PersonaV2TopologyError("v2 topology differs from canonical regeneration")
    return True


def topology_contract_sha256(value=None):
    if value is None:
        value = build_topology_contract()
    validate_topology_contract(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def get_persona_topology(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2TopologyError(f"unknown topology persona: {persona_id!r}")
    return copy.deepcopy(_canonical_contract_value()["personas"][envelope.PERSONA_IDS.index(persona_id)])


def _group_project(total, group_bp, weights):
    numerator = total * group_bp
    if numerator % 10_000:
        raise PersonaV2TopologyError("profile total cannot preserve exact primary/secondary share")
    return envelope.largest_remainder(numerator // 10_000, tuple(weights))


def project_physical_files(persona_id, profile):
    persona = get_persona_topology(persona_id)
    total = envelope.profile_file_count(persona_id, profile)
    primary = persona["scopes"][:PRIMARY_SCOPE_COUNT]
    secondary = persona["scopes"][PRIMARY_SCOPE_COUNT:]
    return tuple(
        _group_project(
            total,
            persona["primary_share_bp"],
            (scope["physical_file_weight_bp"] for scope in primary),
        )
        + _group_project(
            total,
            persona["secondary_share_bp"],
            (scope["physical_file_weight_bp"] for scope in secondary),
        )
    )


def project_contributor_chunks(persona_id, profile):
    if profile not in ("pilot", "full"):
        raise PersonaV2TopologyError("formal contributor chunk projection is pilot/full only")
    persona = get_persona_topology(persona_id)
    total = _canonical_contract_value()["policy"]["profile_chunk_targets"][profile]
    primary = persona["scopes"][:PRIMARY_SCOPE_COUNT]
    secondary = persona["scopes"][PRIMARY_SCOPE_COUNT:]
    return tuple(
        _group_project(
            total,
            persona["primary_share_bp"],
            (scope["contributor_chunk_weight_bp"] for scope in primary),
        )
        + _group_project(
            total,
            persona["secondary_share_bp"],
            (scope["contributor_chunk_weight_bp"] for scope in secondary),
        )
    )


def contributor_source_feasibility(persona_id, profile):
    if profile not in ("pilot", "full"):
        raise PersonaV2TopologyError("source feasibility is pilot/full only")
    physical = project_physical_files(persona_id, profile)
    chunks = project_contributor_chunks(persona_id, profile)
    lower = tuple(
        max(
            MIN_CONTRIBUTOR_SOURCES_PER_SCOPE,
            (
                chunk_count + MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE - 1
            ) // MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
        )
        for chunk_count in chunks
    )
    upper = tuple(min(chunk_count, file_count) for chunk_count, file_count in zip(chunks, physical))
    source_count = envelope.contributor_count(persona_id, profile)
    lower_total = sum(lower)
    upper_total = sum(upper)
    return {
        "feasible_necessary_bounds": all(left <= right for left, right in zip(lower, upper))
        and lower_total <= source_count <= upper_total,
        "lower_headroom": source_count - lower_total,
        "lower_by_scope": lower,
        "minimum_scope_span": min(right - left for left, right in zip(lower, upper)),
        "source_count": source_count,
        "upper_headroom": upper_total - source_count,
        "upper_by_scope": upper,
    }
