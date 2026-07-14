"""Canonical, non-authorizing joint-allocation *problem* for persona-PC v2.

This artifact binds the reviewed v2 envelope and exact topology, expands their
pilot/full integer marginals, derives the immutable-full-minus-pilot residual,
and evaluates inexpensive necessary feasibility conditions.  It deliberately
contains no source rows and no allocation solution: variant-to-scope routing,
density quotas, whole-source cohort assignments, recipes, names, and payloads
remain inputs to a future bounded exact solver.

Passing every check in this module is necessary, but is not a proof that the
joint allocation exists.  Consequently this module never grants write or
history authority and never freezes G0.
"""

import copy
import functools
import hashlib
import json
import unicodedata

from eval import persona_v2_contract as envelope
from eval import persona_v2_topology as topology


ARTIFACT_SCHEMA = "kcs.persona.pc-joint-problem/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-joint-allocation-problem"
COMPLETION_SCOPE = (
    "bound-envelope-topology-integer-marginals-and-necessary-feasibility-only-"
    "not-joint-solution-not-g0-root"
)

PROFILES = ("pilot", "full")
RESIDUAL_PROFILE = "full-minus-pilot"
GATE_ROLE_ORDER = (
    "contract_contributor",
    "incidental_searchable",
    "raw_only",
)
HISTORY_COHORT_ORDER = envelope.HISTORY_COHORT_ORDER

MAX_JOINT_PROBLEM_BYTES = 4 * 2**20
# Backward-neutral local alias; the descriptive public constant above is the
# canonical limit name used in the artifact.
MAX_PROBLEM_BYTES = MAX_JOINT_PROBLEM_BYTES
MAX_CANONICAL_DEPTH = 64
MAX_CANONICAL_STRING_BYTES = 4_096
MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE = (
    topology.MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE
)
REQUIRED_SCOPE_HISTORY_COHORTS = topology.REQUIRED_SCOPE_HISTORY_COHORTS


class PersonaV2JointProblemError(ValueError):
    """Raised when the v2 joint problem differs from canonical regeneration."""


def _ceil_div(numerator, denominator):
    if (
        type(numerator) is not int
        or numerator < 0
        or type(denominator) is not int
        or denominator <= 0
    ):
        raise PersonaV2JointProblemError(
            "ceiling division requires a non-negative integer numerator and "
            "positive integer denominator"
        )
    return (numerator + denominator - 1) // denominator


def _check(check_id, passed):
    if type(check_id) is not str or not check_id:
        raise PersonaV2JointProblemError("check ID must be a non-empty string")
    if type(passed) is not bool:
        raise PersonaV2JointProblemError("necessary check result must be boolean")
    return {"check_id": check_id, "passed": passed}


def _history_contract(envelope_value):
    contract = envelope_value["history_cohort_contract"]
    weights = contract["weights_pct"]
    if set(weights) != set(HISTORY_COHORT_ORDER):
        raise PersonaV2JointProblemError("history cohort IDs differ from v2 problem")
    if sum(weights.values()) != 100 or any(
        type(value) is not int or value <= 0 for value in weights.values()
    ):
        raise PersonaV2JointProblemError(
            "history cohort weights must be positive integer percentages"
        )
    required = tuple(contract["coverage_required_in_all_twenty_scopes"])
    if required != REQUIRED_SCOPE_HISTORY_COHORTS:
        raise PersonaV2JointProblemError(
            "required history cohort coverage differs from exact topology"
        )
    if contract["partition"] != "whole_source":
        raise PersonaV2JointProblemError(
            "joint problem requires the reviewed whole-source cohort partition"
        )
    if tuple(contract["cohort_order"]) != HISTORY_COHORT_ORDER:
        raise PersonaV2JointProblemError(
            "history cohort serialization order differs from the bound envelope"
        )
    if contract["required_scope_count"] != topology.SCOPES_PER_PERSONA:
        raise PersonaV2JointProblemError(
            "history cohort required scope count differs from exact topology"
        )
    if (
        contract["max_chunks_per_contributor_source"]
        != MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE
    ):
        raise PersonaV2JointProblemError(
            "history cohort quota maximum differs from exact topology"
        )
    return weights


def _validate_bound_history_source_lower_bounds(
    envelope_value, profile, target_chunks, history_rows, feasibility
):
    bound = envelope_value["history_cohort_contract"][
        "profile_source_lower_bounds"
    ][profile]
    if bound["target_contract_contributor_chunks"] != target_chunks:
        raise PersonaV2JointProblemError(
            f"bound history target differs for {profile}"
        )
    actual_chunks = _rows_by_key(history_rows, "cohort_id")
    actual_bounds = _rows_by_key(
        feasibility["cohort_source_interval"]["per_cohort"], "cohort_id"
    )
    bound_rows = _rows_by_key(bound["cohorts"], "cohort_id")
    if tuple(bound_rows) != HISTORY_COHORT_ORDER:
        raise PersonaV2JointProblemError(
            f"bound history cohort rows reorder for {profile}"
        )
    for cohort in HISTORY_COHORT_ORDER:
        expected = bound_rows[cohort]
        if (
            expected["contract_contributor_chunks"]
            != actual_chunks[cohort]["contract_contributor_chunks"]
            or expected["coverage_source_lower_bound"]
            != actual_bounds[cohort]["coverage_lower_bound"]
            or expected["necessary_source_lower_bound"]
            != actual_bounds[cohort]["necessary_source_lower_bound"]
            or expected["quota_source_lower_bound"]
            != actual_bounds[cohort]["quota_lower_bound"]
        ):
            raise PersonaV2JointProblemError(
                f"bound history source lower differs for {profile}/{cohort}"
            )
    if (
        bound["minimum_contributor_sources"]
        != feasibility["cohort_source_interval"]["lower_bound"]
    ):
        raise PersonaV2JointProblemError(
            f"bound history source lower total differs for {profile}"
        )


def _history_chunk_marginals(target_chunks, weights):
    counts = envelope.largest_remainder(
        target_chunks,
        tuple(weights[cohort] for cohort in HISTORY_COHORT_ORDER),
    )
    return [
        {
            "cohort_id": cohort,
            "contract_contributor_chunks": count,
            "weight_pct": weights[cohort],
        }
        for cohort, count in zip(HISTORY_COHORT_ORDER, counts)
    ]


def _variant_marginals(persona_id, profile):
    counts = envelope.variant_counts(persona_id, profile)
    rows = []
    for family in envelope.FORMAT_KEYS:
        variants = []
        for variant in counts[family]:
            variants.append({
                "file_count": variant["count"],
                "gate_role": variant["gate_role"],
                "ratio_pct": variant["ratio_pct"],
                "variant_id": variant["variant_id"],
            })
        rows.append({
            "family": family,
            "file_count": sum(row["file_count"] for row in variants),
            "variants": variants,
        })
    return rows


def _gate_role_counts(variant_rows):
    counts = {role: 0 for role in GATE_ROLE_ORDER}
    for family in variant_rows:
        for variant in family["variants"]:
            role = variant["gate_role"]
            if role not in counts:
                raise PersonaV2JointProblemError(f"unknown v2 gate role: {role!r}")
            counts[role] += variant["file_count"]
    return [
        {"file_count": counts[role], "gate_role": role}
        for role in GATE_ROLE_ORDER
    ]


def _density_marginals(persona_id, profile):
    counts = envelope.density_bucket_counts(persona_id, profile)
    return [
        {
            "bucket_id": bucket,
            "contributor_source_count": counts[bucket],
            "quota_max": envelope.DENSITY_BUCKET_BOUNDS[bucket][1],
            "quota_min": envelope.DENSITY_BUCKET_BOUNDS[bucket][0],
        }
        for bucket in envelope.DENSITY_BUCKET_ORDER
    ]


def _scope_marginals(persona_id, profile, *, coverage_floor):
    persona = topology.get_persona_topology(persona_id)
    physical = topology.project_physical_files(persona_id, profile)
    chunks = topology.project_contributor_chunks(persona_id, profile)
    rows = []
    for scope, file_count, chunk_count in zip(persona["scopes"], physical, chunks):
        lower = max(
            coverage_floor,
            _ceil_div(chunk_count, MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE),
        )
        upper = min(chunk_count, file_count)
        rows.append({
            "contributor_chunk_count": chunk_count,
            "contributor_source_lower_bound": lower,
            "contributor_source_upper_bound": upper,
            "functional_slot": scope["functional_slot"],
            "kind": scope["kind"],
            "ordinal": scope["ordinal"],
            "physical_file_count": file_count,
            "relative_path": scope["relative_path"],
            "scope_key": scope["scope_key"],
        })
    return rows


def _rows_by_key(rows, key):
    result = {}
    for row in rows:
        value = row[key]
        if value in result:
            raise PersonaV2JointProblemError(f"duplicate {key}: {value!r}")
        result[value] = row
    return result


def _necessary_feasibility(
    *,
    physical_file_count,
    contributor_source_count,
    target_chunks,
    variant_rows,
    gate_role_rows,
    density_rows,
    history_rows,
    scope_rows,
    required_scope_coverage,
):
    scope_lower = sum(row["contributor_source_lower_bound"] for row in scope_rows)
    scope_upper = sum(row["contributor_source_upper_bound"] for row in scope_rows)
    density_lower = sum(
        row["contributor_source_count"] * row["quota_min"] for row in density_rows
    )
    density_upper = sum(
        row["contributor_source_count"] * row["quota_max"] for row in density_rows
    )

    cohort_source_bounds = []
    required = set(REQUIRED_SCOPE_HISTORY_COHORTS) if required_scope_coverage else set()
    for row in history_rows:
        cohort = row["cohort_id"]
        chunks = row["contract_contributor_chunks"]
        quota_lower = _ceil_div(chunks, MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE)
        coverage_lower = len(scope_rows) if cohort in required else 0
        cohort_source_bounds.append({
            "cohort_id": cohort,
            "coverage_lower_bound": coverage_lower,
            "necessary_source_lower_bound": max(quota_lower, coverage_lower),
            "quota_lower_bound": quota_lower,
            "source_upper_bound": chunks,
        })
    cohort_lower = sum(row["necessary_source_lower_bound"] for row in cohort_source_bounds)
    cohort_upper = sum(row["source_upper_bound"] for row in cohort_source_bounds)

    variant_total = sum(row["file_count"] for row in variant_rows)
    nested_variant_counts_match_family = all(
        sum(variant["file_count"] for variant in row["variants"])
        == row["file_count"]
        for row in variant_rows
    )
    gate_total = sum(row["file_count"] for row in gate_role_rows)
    gate_counts = _rows_by_key(gate_role_rows, "gate_role")
    density_source_total = sum(row["contributor_source_count"] for row in density_rows)
    history_chunk_total = sum(row["contract_contributor_chunks"] for row in history_rows)
    scope_physical_total = sum(row["physical_file_count"] for row in scope_rows)
    scope_chunk_total = sum(row["contributor_chunk_count"] for row in scope_rows)
    required_chunks_sufficient = all(
        row["contract_contributor_chunks"] >= len(scope_rows)
        for row in history_rows
        if row["cohort_id"] in required
    )

    checks = [
        _check("variant-file-count-sums-to-profile-physical-total", variant_total == physical_file_count),
        _check(
            "nested-variant-file-counts-match-family-marginals",
            nested_variant_counts_match_family,
        ),
        _check("gate-role-count-sums-to-profile-physical-total", gate_total == physical_file_count),
        _check(
            "contract-contributor-gate-count-matches-source-total",
            gate_counts["contract_contributor"]["file_count"] == contributor_source_count,
        ),
        _check(
            "scope-count-matches-persona-topology",
            len(scope_rows) == topology.SCOPES_PER_PERSONA,
        ),
        _check(
            "scope-physical-file-count-sums-to-profile-physical-total",
            scope_physical_total == physical_file_count,
        ),
        _check(
            "scope-contributor-chunks-sum-to-profile-target",
            scope_chunk_total == target_chunks,
        ),
        _check(
            "scope-contributor-source-intervals-are-nonempty",
            all(
                row["contributor_source_lower_bound"]
                <= row["contributor_source_upper_bound"]
                for row in scope_rows
            ),
        ),
        _check(
            "contributor-source-total-is-within-aggregate-scope-interval",
            scope_lower <= contributor_source_count <= scope_upper,
        ),
        _check(
            "density-source-count-sums-to-contributor-source-total",
            density_source_total == contributor_source_count,
        ),
        _check(
            "density-global-quota-interval-contains-target-chunks",
            density_lower <= target_chunks <= density_upper,
        ),
        _check(
            "history-cohort-chunks-sum-to-target-chunks",
            history_chunk_total == target_chunks,
        ),
        _check(
            "required-history-cohorts-have-one-chunk-per-scope-capacity",
            required_chunks_sufficient,
        ),
        _check(
            "whole-source-cohort-partition-can-fit-contributor-source-total",
            cohort_lower <= contributor_source_count <= cohort_upper,
        ),
    ]
    failed = [row["check_id"] for row in checks if not row["passed"]]
    return {
        "all_checks_pass": not failed,
        "checks": checks,
        "cohort_source_interval": {
            "lower_bound": cohort_lower,
            "lower_headroom": contributor_source_count - cohort_lower,
            "per_cohort": cohort_source_bounds,
            "upper_bound": cohort_upper,
            "upper_headroom": cohort_upper - contributor_source_count,
        },
        "density_chunk_interval": {
            "lower_bound": density_lower,
            "lower_headroom": target_chunks - density_lower,
            "upper_bound": density_upper,
            "upper_headroom": density_upper - target_chunks,
        },
        "failed_check_ids": failed,
        "scope_source_interval": {
            "lower_bound": scope_lower,
            "lower_headroom": contributor_source_count - scope_lower,
            "minimum_scope_span": min(
                row["contributor_source_upper_bound"]
                - row["contributor_source_lower_bound"]
                for row in scope_rows
            ),
            "upper_bound": scope_upper,
            "upper_headroom": scope_upper - contributor_source_count,
        },
    }


def _build_profile(persona_id, profile, envelope_value):
    if profile not in PROFILES:
        raise PersonaV2JointProblemError(f"unknown problem profile: {profile!r}")
    physical_file_count = envelope.profile_file_count(persona_id, profile)
    target_chunks = envelope_value["profiles"][profile]["target_chunks_per_person"]
    contributor_source_count = envelope.contributor_count(persona_id, profile)
    variant_rows = _variant_marginals(persona_id, profile)
    gate_role_rows = _gate_role_counts(variant_rows)
    density_rows = _density_marginals(persona_id, profile)
    history_rows = _history_chunk_marginals(
        target_chunks, _history_contract(envelope_value)
    )
    scope_rows = _scope_marginals(
        persona_id,
        profile,
        coverage_floor=len(REQUIRED_SCOPE_HISTORY_COHORTS),
    )
    feasibility = _necessary_feasibility(
        physical_file_count=physical_file_count,
        contributor_source_count=contributor_source_count,
        target_chunks=target_chunks,
        variant_rows=variant_rows,
        gate_role_rows=gate_role_rows,
        density_rows=density_rows,
        history_rows=history_rows,
        scope_rows=scope_rows,
        required_scope_coverage=True,
    )
    _validate_bound_history_source_lower_bounds(
        envelope_value,
        profile,
        target_chunks,
        history_rows,
        feasibility,
    )
    return {
        "contributor_source_count": contributor_source_count,
        "density_bucket_marginals": density_rows,
        "family_variant_marginals": variant_rows,
        "gate_role_counts": gate_role_rows,
        "history_cohort_chunk_marginals": history_rows,
        "necessary_feasibility": feasibility,
        "physical_file_count": physical_file_count,
        "profile": profile,
        "scope_marginals": scope_rows,
        "target_contract_contributor_chunks": target_chunks,
    }


def _subtract_keyed_rows(
    full_rows, pilot_rows, key, count_fields, invariant_fields=()
):
    full = _rows_by_key(full_rows, key)
    pilot = _rows_by_key(pilot_rows, key)
    if tuple(full) != tuple(pilot):
        raise PersonaV2JointProblemError(f"pilot/full {key} rows differ or reorder")
    result = []
    for row_key in full:
        if any(
            full[row_key][field] != pilot[row_key][field]
            for field in invariant_fields
        ):
            raise PersonaV2JointProblemError(
                f"pilot/full {key} invariant differs: {row_key!r}"
            )
        value = copy.deepcopy(full[row_key])
        for field in count_fields:
            value[field] -= pilot[row_key][field]
            if value[field] < 0:
                raise PersonaV2JointProblemError(
                    f"negative full-minus-pilot {key}/{field}: {row_key!r}"
                )
        result.append(value)
    return result


def _subtract_variant_rows(full_rows, pilot_rows):
    full = _rows_by_key(full_rows, "family")
    pilot = _rows_by_key(pilot_rows, "family")
    if tuple(full) != tuple(pilot):
        raise PersonaV2JointProblemError("pilot/full family rows differ or reorder")
    result = []
    for family in full:
        full_variants = _rows_by_key(full[family]["variants"], "variant_id")
        pilot_variants = _rows_by_key(pilot[family]["variants"], "variant_id")
        if tuple(full_variants) != tuple(pilot_variants):
            raise PersonaV2JointProblemError(
                f"pilot/full variant rows differ or reorder: {family}"
            )
        variants = []
        for variant_id in full_variants:
            for field in ("gate_role", "ratio_pct", "variant_id"):
                if (
                    full_variants[variant_id][field]
                    != pilot_variants[variant_id][field]
                ):
                    raise PersonaV2JointProblemError(
                        "pilot/full variant invariant differs: "
                        f"{family}/{variant_id}/{field}"
                    )
            row = copy.deepcopy(full_variants[variant_id])
            row["file_count"] -= pilot_variants[variant_id]["file_count"]
            if row["file_count"] < 0:
                raise PersonaV2JointProblemError(
                    f"negative full-minus-pilot variant count: {family}/{variant_id}"
                )
            variants.append(row)
        result.append({
            "family": family,
            "file_count": sum(row["file_count"] for row in variants),
            "variants": variants,
        })
    return result


def _subtract_scope_rows(full_rows, pilot_rows):
    full = _rows_by_key(full_rows, "scope_key")
    pilot = _rows_by_key(pilot_rows, "scope_key")
    if tuple(full) != tuple(pilot):
        raise PersonaV2JointProblemError("pilot/full scope rows differ or reorder")
    result = []
    invariant_fields = (
        "functional_slot",
        "kind",
        "ordinal",
        "relative_path",
        "scope_key",
    )
    for scope_key in full:
        if any(full[scope_key][field] != pilot[scope_key][field] for field in invariant_fields):
            raise PersonaV2JointProblemError(
                f"pilot/full scope identity differs: {scope_key}"
            )
        file_count = full[scope_key]["physical_file_count"] - pilot[scope_key]["physical_file_count"]
        chunk_count = full[scope_key]["contributor_chunk_count"] - pilot[scope_key]["contributor_chunk_count"]
        if file_count < 0 or chunk_count < 0:
            raise PersonaV2JointProblemError(
                f"negative full-minus-pilot scope marginal: {scope_key}"
            )
        lower = _ceil_div(chunk_count, MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE)
        upper = min(chunk_count, file_count)
        result.append({
            "contributor_chunk_count": chunk_count,
            "contributor_source_lower_bound": lower,
            "contributor_source_upper_bound": upper,
            "functional_slot": full[scope_key]["functional_slot"],
            "kind": full[scope_key]["kind"],
            "ordinal": full[scope_key]["ordinal"],
            "physical_file_count": file_count,
            "relative_path": full[scope_key]["relative_path"],
            "scope_key": scope_key,
        })
    return result


def _build_residual(pilot, full):
    physical_file_count = full["physical_file_count"] - pilot["physical_file_count"]
    contributor_source_count = (
        full["contributor_source_count"] - pilot["contributor_source_count"]
    )
    target_chunks = (
        full["target_contract_contributor_chunks"]
        - pilot["target_contract_contributor_chunks"]
    )
    variant_rows = _subtract_variant_rows(
        full["family_variant_marginals"], pilot["family_variant_marginals"]
    )
    gate_role_rows = _subtract_keyed_rows(
        full["gate_role_counts"],
        pilot["gate_role_counts"],
        "gate_role",
        ("file_count",),
    )
    density_rows = _subtract_keyed_rows(
        full["density_bucket_marginals"],
        pilot["density_bucket_marginals"],
        "bucket_id",
        ("contributor_source_count",),
        ("quota_min", "quota_max"),
    )
    history_rows = _subtract_keyed_rows(
        full["history_cohort_chunk_marginals"],
        pilot["history_cohort_chunk_marginals"],
        "cohort_id",
        ("contract_contributor_chunks",),
        ("weight_pct",),
    )
    scope_rows = _subtract_scope_rows(
        full["scope_marginals"], pilot["scope_marginals"]
    )
    feasibility = _necessary_feasibility(
        physical_file_count=physical_file_count,
        contributor_source_count=contributor_source_count,
        target_chunks=target_chunks,
        variant_rows=variant_rows,
        gate_role_rows=gate_role_rows,
        density_rows=density_rows,
        history_rows=history_rows,
        scope_rows=scope_rows,
        required_scope_coverage=False,
    )
    return {
        "contributor_source_count": contributor_source_count,
        "density_bucket_marginals": density_rows,
        "family_variant_marginals": variant_rows,
        "gate_role_counts": gate_role_rows,
        "history_cohort_chunk_marginals": history_rows,
        "necessary_feasibility": feasibility,
        "physical_file_count": physical_file_count,
        "profile": RESIDUAL_PROFILE,
        "scope_marginals": scope_rows,
        "target_contract_contributor_chunks": target_chunks,
    }


def _cross_profile_checks(pilot, full, residual):
    checks = [
        _check(
            "pilot-physical-file-total-does-not-exceed-full",
            pilot["physical_file_count"] <= full["physical_file_count"],
        ),
        _check(
            "pilot-contributor-source-total-does-not-exceed-full",
            pilot["contributor_source_count"] <= full["contributor_source_count"],
        ),
        _check(
            "pilot-contract-chunk-total-does-not-exceed-full",
            pilot["target_contract_contributor_chunks"]
            <= full["target_contract_contributor_chunks"],
        ),
        _check(
            "residual-physical-total-reconstructs-full",
            pilot["physical_file_count"] + residual["physical_file_count"]
            == full["physical_file_count"],
        ),
        _check(
            "residual-contributor-source-total-reconstructs-full",
            pilot["contributor_source_count"] + residual["contributor_source_count"]
            == full["contributor_source_count"],
        ),
        _check(
            "residual-contract-chunk-total-reconstructs-full",
            pilot["target_contract_contributor_chunks"]
            + residual["target_contract_contributor_chunks"]
            == full["target_contract_contributor_chunks"],
        ),
        _check(
            "residual-marginals-pass-necessary-feasibility",
            residual["necessary_feasibility"]["all_checks_pass"],
        ),
    ]
    failed = [row["check_id"] for row in checks if not row["passed"]]
    return {
        "all_checks_pass": not failed,
        "checks": checks,
        "failed_check_ids": failed,
    }


def _build_persona_problem(persona_id, envelope_value):
    metadata = envelope.get_persona(persona_id)
    pilot = _build_profile(persona_id, "pilot", envelope_value)
    full = _build_profile(persona_id, "full", envelope_value)
    residual = _build_residual(pilot, full)
    return {
        "cross_profile_necessary_checks": _cross_profile_checks(
            pilot, full, residual
        ),
        "full_minus_pilot_residual": residual,
        "persona_id": persona_id,
        "profiles": [pilot, full],
        "role": metadata["role"],
    }


def _suite_profile_index(personas, profile):
    if profile in PROFILES:
        selected = [
            next(row for row in persona["profiles"] if row["profile"] == profile)
            for persona in personas
        ]
    elif profile == RESIDUAL_PROFILE:
        selected = [persona["full_minus_pilot_residual"] for persona in personas]
    else:
        raise PersonaV2JointProblemError(f"unknown suite index profile: {profile!r}")
    failing = [
        persona["persona_id"]
        for persona, row in zip(personas, selected)
        if not row["necessary_feasibility"]["all_checks_pass"]
    ]
    density = {bucket: 0 for bucket in envelope.DENSITY_BUCKET_ORDER}
    history = {cohort: 0 for cohort in HISTORY_COHORT_ORDER}
    families = {family: 0 for family in envelope.FORMAT_KEYS}
    gate_roles = {role: 0 for role in GATE_ROLE_ORDER}
    for row in selected:
        for marginal in row["density_bucket_marginals"]:
            density[marginal["bucket_id"]] += marginal["contributor_source_count"]
        for marginal in row["history_cohort_chunk_marginals"]:
            history[marginal["cohort_id"]] += marginal["contract_contributor_chunks"]
        for marginal in row["family_variant_marginals"]:
            families[marginal["family"]] += marginal["file_count"]
        for marginal in row["gate_role_counts"]:
            gate_roles[marginal["gate_role"]] += marginal["file_count"]
    return {
        "contract_contributor_chunks": sum(
            row["target_contract_contributor_chunks"] for row in selected
        ),
        "contract_contributor_sources": sum(
            row["contributor_source_count"] for row in selected
        ),
        "density_bucket_source_counts": density,
        "failing_persona_ids": failing,
        "family_file_counts": families,
        "gate_role_file_counts": gate_roles,
        "history_cohort_chunk_counts": history,
        "necessary_feasibility_all_pass": not failing,
        "persona_count": len(selected),
        "physical_files": sum(row["physical_file_count"] for row in selected),
        "profile": profile,
        "scope_count": sum(len(row["scope_marginals"]) for row in selected),
    }


@functools.lru_cache(maxsize=1)
def _canonical_problem_value():
    envelope_value = envelope.build_envelope_contract()
    topology_value = topology.build_topology_contract()
    envelope.validate_envelope_contract(envelope_value)
    topology.validate_topology_contract(topology_value)
    if topology_value["envelope_contract_sha256"] != envelope.envelope_contract_sha256(
        envelope_value
    ):
        raise PersonaV2JointProblemError(
            "topology is not bound to the current envelope contract"
        )
    if topology_value["g0_contract_frozen"] is not False:
        raise PersonaV2JointProblemError("bound topology must remain non-G0")
    authority = copy.deepcopy(topology_value["authority"])
    if not authority or any(
        type(value) is not bool or value is not False for value in authority.values()
    ):
        raise PersonaV2JointProblemError(
            "bound topology authority must contain only exact false booleans"
        )
    personas = [
        _build_persona_problem(persona_id, envelope_value)
        for persona_id in envelope.PERSONA_IDS
    ]
    suite_profiles = [
        _suite_profile_index(personas, profile)
        for profile in (*PROFILES, RESIDUAL_PROFILE)
    ]
    suite_all_pass = all(
        row["necessary_feasibility_all_pass"] for row in suite_profiles
    ) and all(
        persona["cross_profile_necessary_checks"]["all_checks_pass"]
        for persona in personas
    )
    cross_profile_failing = [
        persona["persona_id"]
        for persona in personas
        if not persona["cross_profile_necessary_checks"]["all_checks_pass"]
    ]
    blockers = list(topology_value["remaining_g0_blockers"])
    if "joint_scope_variant_density_quota_solver_missing" not in blockers:
        raise PersonaV2JointProblemError(
            "joint solver blocker must remain in the bound topology"
        )
    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            **authority,
            "joint_allocation_proved": False,
        },
        "completion_scope": COMPLETION_SCOPE,
        "envelope_contract_sha256": envelope.envelope_contract_sha256(
            envelope_value
        ),
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "joint_allocation_proved": False,
        "necessary_feasibility_all_pass": suite_all_pass,
        "personas": personas,
        "policy": {
            "canonical_limits": {
                "integer_only": True,
                "max_joint_problem_bytes": MAX_PROBLEM_BYTES,
                "max_nesting_depth": MAX_CANONICAL_DEPTH,
                "max_string_bytes": MAX_CANONICAL_STRING_BYTES,
                "unicode_normalization": "NFC",
            },
            "history_cohort_serialization_order": list(HISTORY_COHORT_ORDER),
            "input_array_order": {
                "bucket": "bound-envelope-order",
                "family": "bound-envelope-FORMAT_KEYS-order",
                "history_cohort": "serialization-only-P-X-Y-N-U",
                "scope": "bound-topology-ordinal-order",
                "status": (
                    "problem-projection-order-only-not-authoritative-solver-axis-policy"
                ),
                "variant": "bound-envelope-profile-order",
            },
            "necessary_analysis": {
                "max_chunks_per_contributor_source": MAX_CONTRIBUTOR_CHUNKS_PER_SOURCE,
                "required_positive_source_cohorts_per_scope": list(
                    REQUIRED_SCOPE_HISTORY_COHORTS
                ),
                "scope_source_lower_formula": (
                    "max(required_cohort_count,ceil(scope_chunks/max_chunks_per_source))"
                ),
                "status": "necessary-conditions-only-not-sufficient-not-solver-proof",
                "whole_source_cohort_lower_formula": (
                    "max(required_scope_count_or_zero,ceil(cohort_chunks/max_chunks_per_source))"
                ),
            },
            "problem_dimensions_present": [
                "persona",
                "profile",
                "scope",
                "family",
                "variant",
                "gate-role",
                "density-bucket",
                "history-cohort-chunks",
                "full-minus-pilot-residual",
            ],
            "pilot_embedding_status": (
                "coordinatewise-nonnegative-residual-only-not-source-subset-proof"
            ),
            "residual_ratio_pct_semantics": (
                "inherited-authored-family-variant-weight-not-realized-residual-percent"
            ),
            "solution_dimensions_intentionally_absent": [
                "source-id",
                "materialization-id",
                "variant-to-scope-routing",
                "per-source-density-quota",
                "per-source-history-cohort",
                "source-recipe",
                "semantic-basename",
                "target-complexity",
                "target-bytes",
                "payload-seed",
                "per-source-expected-incidental-upper",
                "solver-policy-and-objective",
            ],
        },
        "proof_status": {
            "incidental_wave_budget_proved": False,
            "joint_allocation_geometry_proved": False,
            "joint_allocation_proved_for_g0": False,
            "necessary_marginal_inputs_bound": True,
            "solver_policy_bound": False,
            "source_recipe_bound": False,
        },
        "remaining_g0_blockers": blockers,
        "suite_index": {
            "cross_profile_failing_persona_ids": cross_profile_failing,
            "necessary_feasibility_all_pass": suite_all_pass,
            "persona_order": list(envelope.PERSONA_IDS),
            "profile_order": [*PROFILES, RESIDUAL_PROFILE],
            "profiles": suite_profiles,
        },
        "topology_contract_sha256": topology.topology_contract_sha256(
            topology_value
        ),
    }


def build_joint_problem():
    """Return a detached canonical problem artifact, never an allocation."""
    return copy.deepcopy(_canonical_problem_value())


def _validate_canonical_value(value, depth=0):
    if depth > MAX_CANONICAL_DEPTH:
        raise PersonaV2JointProblemError(
            "v2 joint problem exceeds canonical nesting depth"
        )
    if value is None or type(value) in (bool, int):
        return
    if type(value) is str:
        if len(value.encode("utf-8")) > MAX_CANONICAL_STRING_BYTES:
            raise PersonaV2JointProblemError(
                "v2 joint problem string exceeds byte bound"
            )
        if unicodedata.normalize("NFC", value) != value:
            raise PersonaV2JointProblemError(
                "v2 joint problem strings must be NFC"
            )
        return
    if type(value) is list:
        for item in value:
            _validate_canonical_value(item, depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str:
                raise PersonaV2JointProblemError(
                    "v2 joint problem object keys must be strings"
                )
            _validate_canonical_value(key, depth + 1)
            _validate_canonical_value(item, depth + 1)
        return
    raise PersonaV2JointProblemError(
        f"unsupported v2 joint problem value type: {type(value).__name__}"
    )


def canonical_json_bytes(value):
    """Encode a JSON-only value with strict v2 problem limits."""
    _validate_canonical_value(value)
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if len(raw) > MAX_PROBLEM_BYTES:
        raise PersonaV2JointProblemError(
            "v2 joint problem exceeds 4 MiB canonical cap"
        )
    return raw


def validate_joint_problem(value):
    """Require byte-for-byte equality with deterministic regeneration."""
    if type(value) is not dict:
        raise PersonaV2JointProblemError("v2 joint problem must be an object")
    actual = canonical_json_bytes(value)
    expected = canonical_json_bytes(_canonical_problem_value())
    if actual != expected:
        raise PersonaV2JointProblemError(
            "v2 joint problem differs from canonical regeneration"
        )
    return True


def joint_problem_sha256(value=None):
    if value is None:
        value = build_joint_problem()
    validate_joint_problem(value)
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def require_joint_allocation_solution():
    raise PersonaV2JointProblemError(
        "v2 joint problem contains necessary marginals only; no exact allocation solution exists in this artifact"
    )


def get_persona_problem(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2JointProblemError(
            f"unknown joint-problem persona: {persona_id!r}"
        )
    return copy.deepcopy(
        _canonical_problem_value()["personas"][
            envelope.PERSONA_IDS.index(persona_id)
        ]
    )
