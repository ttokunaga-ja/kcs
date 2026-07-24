"""Deterministic whole-source contributor allocation for persona history waves.

The W0 generator assigns every contract-contributor source an indivisible
planned chunk quota.  This module binds those existing source quotas to four
disjoint, deliberately overlapping lifecycle strata:

``P`` 4%: W1 edit, then W5 path purge and same-scope replacement.
``X`` 10%: W1 edit, W3 edit, then W4 delete and replacement.
``Y`` 6%: W1 edit and W3 edit, remaining live.
``N`` 4%: W3 edit and W5 correction, remaining live.

Consequently W1 is P+X+Y (20%), W3 is X+Y+N (20%), W4 adds
X (10%) to history while preserving current chunks, and W5 adds N (4%)
while path-purging both of P's raw versions.  P' is indexed while old P still
exists, so the transient pre-purge checkpoint is +4% current and +4% history;
purge then removes 4% current and 4% already-historical chunks. Replacements
preserve the removed source's scope, renderer variant, and quota one-for-one.

This is a planned-chunk contract, not post-index Kio evidence.  Structural
rename/move/duplicate/archive/restore sentinels are intentionally separate
and must have zero contract quota so they cannot perturb this arithmetic.
"""

from __future__ import annotations

import hashlib

try:  # Package imports and direct ``python eval/...`` execution.
    from . import persona_fixture_spec as spec
    from . import persona_allocation as w0_allocation
    from . import generate_persona_corpus as w0_generator
    from . import persona_manifest as canonical_manifest
except ImportError:  # pragma: no cover - direct-script compatibility.
    import persona_fixture_spec as spec
    import persona_allocation as w0_allocation
    import generate_persona_corpus as w0_generator
    import persona_manifest as canonical_manifest


HISTORY_ALLOCATION_SCHEMA = "kio.persona.history-allocation/v1"
HISTORY_ALLOCATION_SCHEMA_VERSION = 1

PURGE_AFTER_W1 = "P"
REPEAT_THEN_DELETE = "X"
LATE_THEN_CORRECT = "N"
REPEAT_LIVE = "Y"

# Selection order is frozen.  In full, four distinct anchors are reserved in
# every scope before any subset fill so no early scope can consume another
# stratum's formal coverage source.
STRATUM_SELECTION_ORDER = (
    PURGE_AFTER_W1,
    REPEAT_THEN_DELETE,
    LATE_THEN_CORRECT,
    REPEAT_LIVE,
)


class HistoryAllocationError(ValueError):
    """Raised when W0 source quotas cannot satisfy the history contract."""


def _same_canonical_json(actual, expected):
    """Compare JSON values without Python's bool/int/float equality coercions."""
    if actual != expected:
        return False
    try:
        return (
            canonical_manifest.canonical_json_bytes(actual)
            == canonical_manifest.canonical_json_bytes(expected)
        )
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError):
        return False


def _canonical_persona_plan(persona_id, profile):
    try:
        persona = spec.get_persona(persona_id)
        route = w0_allocation.build_allocation_plan(persona, profile)
        scopes = w0_generator._source_plan_for_persona(persona, profile, route)
        current = spec.contributor_plan(persona, profile)["target_chunks"]
    except (KeyError, TypeError, ValueError, ZeroDivisionError) as error:
        raise HistoryAllocationError(str(error)) from error
    return {
        "persona_id": persona_id,
        "planned_contract_chunks": current,
        "scopes": scopes,
    }


def _require_canonical_persona_plan(persona_plan, profile):
    if type(persona_plan) is not dict:
        raise HistoryAllocationError("persona plan must be an object")
    persona_id = persona_plan.get("persona_id")
    if type(persona_id) is not str:
        raise HistoryAllocationError("persona plan has an invalid persona id")
    expected = _canonical_persona_plan(persona_id, profile)
    if not _same_canonical_json(persona_plan, expected):
        raise HistoryAllocationError(
            "persona plan differs from the canonical W0 source expansion"
        )
    return expected


def _require_plain_int(value, label, *, minimum=0):
    if type(value) is not int or value < minimum:
        raise HistoryAllocationError(
            f"{label} must be an integer greater than or equal to {minimum}"
        )
    return value


def _source_rows(persona_plan):
    if type(persona_plan) is not dict:
        raise HistoryAllocationError("persona plan must be an object")
    persona_id = persona_plan.get("persona_id")
    if type(persona_id) is not str or not persona_id.startswith("p"):
        raise HistoryAllocationError("persona plan has an invalid persona id")
    scopes = persona_plan.get("scopes")
    if type(scopes) is not list or len(scopes) != 20:
        raise HistoryAllocationError("persona plan must contain exactly 20 scopes")

    rows = []
    seen_sources = set()
    seen_scopes = set()
    for scope in scopes:
        if type(scope) is not dict:
            raise HistoryAllocationError("scope plan must be an object")
        scope_key = scope.get("scope_key")
        if type(scope_key) is not str or scope_key in seen_scopes:
            raise HistoryAllocationError("scope keys must be unique strings")
        seen_scopes.add(scope_key)
        sources = scope.get("sources")
        if type(sources) is not list:
            raise HistoryAllocationError(f"scope sources must be a list: {scope_key}")
        for source in sources:
            if type(source) is not dict:
                raise HistoryAllocationError("source plan must be an object")
            source_id = source.get("source_id")
            if type(source_id) is not str or source_id in seen_sources:
                raise HistoryAllocationError("source ids must be unique strings")
            seen_sources.add(source_id)
            quota = _require_plain_int(
                source.get("requested_contributor_chunks"),
                f"source quota for {source_id}",
            )
            gate_role = source.get("gate_role")
            if (gate_role == "contract_contributor") != (quota > 0):
                raise HistoryAllocationError(
                    f"gate role and contributor quota disagree: {source_id}"
                )
            row = dict(source)
            row["scope_key"] = scope_key
            rows.append(row)
    rows.sort(key=lambda row: row["source_id"])
    return persona_id, tuple(sorted(seen_scopes)), rows


def _chunk_targets(persona_id, profile, current_chunks):
    """Return executable per-wave integer deltas.

    Tiny targets are not necessarily divisible by 100.  The contract rounds
    each named wave delta down once, then accumulates those exact deltas.  This
    keeps P and N equal, which is required for W5's net-zero history change.
    Pilot and full are exactly divisible and therefore retain 20/20/10/4%.
    """
    current = _require_plain_int(current_chunks, "current chunk target", minimum=1)
    try:
        persona = spec.get_persona(persona_id)
        canonical_current = spec.contributor_plan(persona, profile)["target_chunks"]
        canonical = spec.history_cohort_chunk_targets(persona, profile)
    except (KeyError, ValueError, ZeroDivisionError) as error:
        raise HistoryAllocationError(str(error)) from error
    if current != canonical_current:
        raise HistoryAllocationError(
            "persona planned contract chunks differ from the canonical profile"
        )
    return {
        PURGE_AFTER_W1: canonical[PURGE_AFTER_W1],
        REPEAT_THEN_DELETE: canonical[REPEAT_THEN_DELETE],
        LATE_THEN_CORRECT: canonical[LATE_THEN_CORRECT],
        REPEAT_LIVE: canonical[REPEAT_LIVE],
    }


def _select_exact(candidates, target, required=(), blocked_ids=frozenset()):
    """Select a deterministic exact whole-source subset with bounded bitset DP."""
    selected = list(required)
    selected_ids = {row["source_id"] for row in selected}
    if len(selected_ids) != len(selected):
        raise HistoryAllocationError("required exact-subset anchors are not unique")
    remaining = target - sum(row["requested_contributor_chunks"] for row in selected)
    if remaining < 0:
        return None
    if remaining == 0:
        return tuple(sorted(selected, key=lambda row: row["source_id"]))

    reachable = 1
    mask = (1 << (remaining + 1)) - 1
    predecessor = [None] * (remaining + 1)
    for row in candidates:
        source_id = row["source_id"]
        if source_id in selected_ids or source_id in blocked_ids:
            continue
        quota = row["requested_contributor_chunks"]
        newly_reachable = ((reachable << quota) & mask) & ~reachable
        pending = newly_reachable
        while pending:
            lowest = pending & -pending
            chunk_sum = lowest.bit_length() - 1
            predecessor[chunk_sum] = (chunk_sum - quota, row)
            pending -= lowest
        reachable |= newly_reachable
        if (reachable >> remaining) & 1:
            break
    if not ((reachable >> remaining) & 1):
        return None

    cursor = remaining
    while cursor:
        entry = predecessor[cursor]
        if entry is None:  # Defensive: reachable sums must have a predecessor.
            raise HistoryAllocationError("exact-subset predecessor chain is corrupt")
        cursor, row = entry
        selected.append(row)
    return tuple(sorted(selected, key=lambda row: row["source_id"]))


def _candidate_order(persona_id, profile, stratum, rows):
    """Spread deterministic subset candidates across scope/variant/source order."""
    prefix = f"{spec.FIXTURE_ID}\0{profile}\0{persona_id}\0{stratum}\0".encode()
    return sorted(
        rows,
        key=lambda row: (
            hashlib.sha256(prefix + row["source_id"].encode("ascii")).digest(),
            row["source_id"],
        ),
    )


def _validate_full_scope_envelope(selected, targets, scope_targets, current):
    """Reject nominal coverage whose chunk load is still effectively one-scope."""
    del current  # The cap is relative to the cohort, not an exact scope percent.
    for stratum, rows in selected.items():
        actual = {scope_key: 0 for scope_key in scope_targets}
        for row in rows:
            actual[row["scope_key"]] += row["requested_contributor_chunks"]
        # Exact per-scope percentages are often arithmetically impossible.  A
        # positive anchor plus a hard 20%-of-cohort cap (with one indivisible
        # source of slack) prevents the previous 84%..94.5% single-scope
        # artifact without pretending to reproduce each W0 scope weight.
        lower = 1
        upper = (
            targets[stratum] * 20 // 100
            + spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE
        )
        for scope_key in scope_targets:
            value = actual[scope_key]
            if value < lower or value > upper:
                raise HistoryAllocationError(
                    f"full {stratum} scope distribution exceeds its envelope: "
                    f"{scope_key} has {value}, expected {lower}..{upper}"
                )


def _full_scope_reservations(contributors, scope_keys):
    reservations = {stratum: [] for stratum in STRATUM_SELECTION_ORDER}
    for scope_key in scope_keys:
        scoped = sorted(
            (row for row in contributors if row["scope_key"] == scope_key),
            key=lambda row: (
                row["requested_contributor_chunks"],
                row["source_id"],
            ),
        )
        if len(scoped) < len(STRATUM_SELECTION_ORDER):
            raise HistoryAllocationError(
                f"full scope lacks four disjoint history anchors: {scope_key}"
            )
        for stratum, row in zip(STRATUM_SELECTION_ORDER, scoped):
            reservations[stratum].append(row)
    return reservations


def _allocate_strata(persona_plan, profile):
    persona_id, scope_keys, rows = _source_rows(persona_plan)
    scope_targets = {
        scope["scope_key"]: scope["expected_contract_chunks"]
        for scope in persona_plan["scopes"]
    }
    current = _require_plain_int(
        persona_plan.get("planned_contract_chunks"),
        "persona planned contract chunks",
        minimum=1,
    )
    contributors = tuple(
        row for row in rows if row["requested_contributor_chunks"] > 0
    )
    if sum(row["requested_contributor_chunks"] for row in contributors) != current:
        raise HistoryAllocationError("W0 contributor quotas do not equal persona target")
    targets = _chunk_targets(persona_id, profile, current)
    reservations = (
        _full_scope_reservations(contributors, scope_keys)
        if profile == "full"
        else {stratum: [] for stratum in STRATUM_SELECTION_ORDER}
    )
    all_reserved = {
        row["source_id"]
        for reserved in reservations.values()
        for row in reserved
    }

    available = list(contributors)
    selected = {}
    for stratum in STRATUM_SELECTION_ORDER:
        own_reserved = reservations[stratum]
        blocked = all_reserved - {row["source_id"] for row in own_reserved}
        result = _select_exact(
            _candidate_order(persona_id, profile, stratum, available),
            targets[stratum],
            required=own_reserved,
            blocked_ids=blocked,
        )
        if result is None:
            raise HistoryAllocationError(
                f"{persona_id} {profile} cannot allocate exact {stratum} "
                f"target {targets[stratum]}"
            )
        selected[stratum] = result
        used = {row["source_id"] for row in result}
        available = [row for row in available if row["source_id"] not in used]
        all_reserved -= used

    source_ids = [
        row["source_id"] for values in selected.values() for row in values
    ]
    if len(source_ids) != len(set(source_ids)):
        raise HistoryAllocationError("history strata must be pairwise disjoint")
    if profile == "full":
        for stratum, values in selected.items():
            covered = {row["scope_key"] for row in values}
            if covered != set(scope_keys):
                raise HistoryAllocationError(
                    f"full {stratum} stratum does not cover all twenty scopes"
                )
        _validate_full_scope_envelope(selected, targets, scope_targets, current)
    return persona_id, scope_keys, rows, current, targets, selected


def _stratum_record(stratum, rows, target):
    scope_chunks = {}
    scope_sources = {}
    for row in rows:
        scope_key = row["scope_key"]
        scope_chunks[scope_key] = (
            scope_chunks.get(scope_key, 0)
            + row["requested_contributor_chunks"]
        )
        scope_sources[scope_key] = scope_sources.get(scope_key, 0) + 1
    return {
        "stratum": stratum,
        "target_chunks": target,
        "source_count": len(rows),
        "scope_count": len(scope_chunks),
        "scope_chunks": dict(sorted(scope_chunks.items())),
        "scope_sources": dict(sorted(scope_sources.items())),
        "source_ids": [row["source_id"] for row in rows],
    }


def _replacement_rows(persona_id, rows, first_ordinal, wave):
    replacements = []
    for offset, row in enumerate(rows):
        new_source_id = f"{persona_id}-src-{first_ordinal + offset:06d}"
        file_name = spec.validate_source_basename(
            f"{new_source_id}.{row['extension']}"
        )
        replacements.append({
            "schema_version": row["schema_version"],
            "wave": wave,
            "replaces_source_id": row["source_id"],
            "source_id": new_source_id,
            "scope_key": row["scope_key"],
            "version": 0,
            "family": row["family"],
            "variant": row["variant"],
            "gate_role": row["gate_role"],
            "expected_disposition": row["expected_disposition"],
            "extension": row["extension"],
            "media_type": row["media_type"],
            "file_name": file_name,
            "requested_contributor_chunks": row[
                "requested_contributor_chunks"
            ],
        })
    return replacements


def _source_ids(*groups):
    return sorted(row["source_id"] for group in groups for row in group)


def _scope_keys(*groups):
    return sorted({row["scope_key"] for group in groups for row in group})


def _build_history_allocation(persona_plan, profile):
    if profile not in ("tiny", "pilot", "full"):
        raise HistoryAllocationError(f"unknown persona profile: {profile!r}")
    try:
        spec.require_executable_history_cohort_assignment()
    except ValueError as error:
        raise HistoryAllocationError(str(error)) from error
    persona_plan = _require_canonical_persona_plan(persona_plan, profile)
    persona_id, scope_keys, rows, current, targets, selected = _allocate_strata(
        persona_plan, profile
    )
    p_rows = selected[PURGE_AFTER_W1]
    x_rows = selected[REPEAT_THEN_DELETE]
    n_rows = selected[LATE_THEN_CORRECT]
    y_rows = selected[REPEAT_LIVE]
    w0_source_count = len(rows)
    w4_replacements = _replacement_rows(
        persona_id, x_rows, w0_source_count + 1, "W4"
    )
    w5_replacements = _replacement_rows(
        persona_id,
        p_rows,
        w0_source_count + len(w4_replacements) + 1,
        "W5",
    )
    edit_delta = targets[PURGE_AFTER_W1] + targets[REPEAT_THEN_DELETE] + targets[REPEAT_LIVE]
    repeat_delta = targets[REPEAT_THEN_DELETE] + targets[REPEAT_LIVE] + targets[LATE_THEN_CORRECT]
    if edit_delta != repeat_delta:
        raise HistoryAllocationError("W1 and W3 edit deltas must be equal")
    delete_delta = targets[REPEAT_THEN_DELETE]
    correction_delta = targets[PURGE_AFTER_W1]
    history_final = edit_delta + repeat_delta + delete_delta

    strata = {
        stratum: _stratum_record(stratum, selected[stratum], targets[stratum])
        for stratum in STRATUM_SELECTION_ORDER
    }
    return {
        "schema": HISTORY_ALLOCATION_SCHEMA,
        "schema_version": HISTORY_ALLOCATION_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": persona_id,
        "whole_source_quota": True,
        "structural_events_require_zero_contract_quota": True,
        "scope_keys": list(scope_keys),
        "current_contract_chunks": current,
        "strata": strata,
        "waves": {
            "W0": {
                "current_contract_chunks": current,
                "history_only_contract_chunks": 0,
            },
            "W1": {
                "edit_source_ids": _source_ids(p_rows, x_rows, y_rows),
                "affected_scope_keys": _scope_keys(p_rows, x_rows, y_rows),
                "history_only_delta_chunks": edit_delta,
                "current_delta_chunks": 0,
            },
            "W2": {
                "positive_quota_source_ids": [],
                "history_only_delta_chunks": 0,
                "current_delta_chunks": 0,
                "structural_assignment_required": True,
            },
            "W3": {
                "major_edit_source_ids": _source_ids(x_rows, y_rows, n_rows),
                "affected_scope_keys": _scope_keys(x_rows, y_rows, n_rows),
                "history_only_delta_chunks": repeat_delta,
                "current_delta_chunks": 0,
            },
            "W4": {
                "delete_source_ids": _source_ids(x_rows),
                "affected_scope_keys": _scope_keys(x_rows),
                "replacement_sources": w4_replacements,
                "deleted_current_chunks": delete_delta,
                "replacement_current_chunks": delete_delta,
                "history_only_delta_chunks": delete_delta,
                "current_delta_chunks": 0,
                "zero_quota_restore_anchors_required": True,
            },
            "W5": {
                "correct_source_ids": _source_ids(n_rows),
                "purge_source_ids": _source_ids(p_rows),
                "affected_scope_keys": _scope_keys(n_rows, p_rows),
                "replacement_sources": w5_replacements,
                "execution_order": [
                    "correct-n-create-p-replacements-and-zero-quota-restore",
                    "index-auto-while-old-p-and-new-p-replacements-coexist",
                    "remove-one-old-p-and-immediately-path-purge-in-source-order",
                    "index-noop-per-purge-affected-scope",
                ],
                "correction_history_chunks": correction_delta,
                "pre_purge_current_contract_chunks": current + correction_delta,
                "pre_purge_history_only_contract_chunks": (
                    history_final + correction_delta
                ),
                "purged_current_chunks": correction_delta,
                "purged_history_only_chunks": correction_delta,
                "purged_total_contract_chunk_rows": correction_delta * 2,
                "purge_raw_versions_per_source": 2,
                "replacement_current_chunks": correction_delta,
                "history_only_delta_chunks_net": 0,
                "current_delta_chunks_net": 0,
                "purged_commit_boundaries": len(p_rows),
                "index_auto_scope_keys": _scope_keys(n_rows, p_rows),
                "index_noop_scope_keys": _scope_keys(p_rows),
            },
        },
        "checkpoints": {
            "W0": {"current": current, "history_only": 0},
            "W1": {"current": current, "history_only": edit_delta},
            "W2": {"current": current, "history_only": edit_delta},
            "W3": {"current": current, "history_only": edit_delta + repeat_delta},
            "W4": {"current": current, "history_only": history_final},
            "W5_pre_purge_auto": {
                "current": current + correction_delta,
                "history_only": history_final + correction_delta,
            },
            "W5": {"current": current, "history_only": history_final},
        },
    }


def build_history_allocation(persona_plan, profile):
    """Build and validate one canonical JSON-compatible history assignment."""
    result = _build_history_allocation(persona_plan, profile)
    validate_history_allocation(result, persona_plan, profile)
    return result


def validate_history_allocation(history_plan, persona_plan, profile):
    """Reject any assignment other than the deterministic canonical expansion."""
    if type(history_plan) is not dict:
        raise HistoryAllocationError("history plan must be an object")
    expected = _build_history_allocation(persona_plan, profile)
    if not _same_canonical_json(history_plan, expected):
        raise HistoryAllocationError("history plan differs from canonical allocation")
    return True
