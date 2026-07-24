"""Canonical quota-neutral structural history allocation for persona PCs.

The contributor allocator freezes P/X/Y/N arithmetic.  This module freezes
the independent path/materialization lane needed to exercise rename, move,
create, exact/near duplicate, derived format, archive, delete, and restore.

The allocation is deliberately root independent and contains no observed KIO
claims.  Raw hashes and complete before/after source states belong to the
subsequent immutable event manifest.  All cross-scope and lifecycle sentinels
are raw-only with zero contributor quota.  Same-scope rename and exact alias
use U contributors, so they preserve ``(scope_key, chunk_id)`` identities.
"""

from __future__ import annotations

import hashlib

try:  # Package imports and direct ``python eval/...`` execution.
    from . import persona_fixture_spec as spec
    from . import persona_history_allocation as history
    from . import persona_manifest as canonical_manifest
    from . import persona_renderers as renderers
except ImportError:  # pragma: no cover - direct-script compatibility.
    import persona_fixture_spec as spec
    import persona_history_allocation as history
    import persona_manifest as canonical_manifest
    import persona_renderers as renderers


STRUCTURAL_ALLOCATION_SCHEMA = "kio.persona.structural-allocation/v1"
STRUCTURAL_ALLOCATION_SCHEMA_VERSION = 1

WAVE_ORDER = ("W1", "W2", "W3", "W4", "W5")
MINIMAL_EVENT_COUNTS = {"W1": 3, "W2": 2, "W3": 3, "W4": 2, "W5": 1}
FULL_EVENT_COUNTS = {"W1": 3, "W2": 21, "W3": 3, "W4": 2, "W5": 1}

# A raw-only traveler is persona-aware even though the current renderer has a
# narrow variant set.  This keeps the structural path lane aligned with the
# role rather than assigning PCAP to all twenty people.
TRAVELER_FAMILY_BY_PERSONA = {
    "p01": "docx",
    "p02": "domain_binary",
    "p03": "pdf_scan",
    "p04": "xlsx",
    "p05": "xlsx",
    "p06": "pdf_scan",
    "p07": "pdf_scan",
    "p08": "docx",
    "p09": "docx",
    "p10": "xlsx",
    "p11": "docx",
    "p12": "docx",
    "p13": "docx",
    "p14": "xlsx",
    "p15": "docx",
    "p16": "pdf_scan",
    "p17": "pdf_scan",
    "p18": "xlsx",
    "p19": "docx",
    "p20": "pdf_scan",
}

_PROFILE_EVENT_COUNTS = {
    "tiny": MINIMAL_EVENT_COUNTS,
    "pilot": MINIMAL_EVENT_COUNTS,
    "full": FULL_EVENT_COUNTS,
}


class StructuralAllocationError(ValueError):
    """Raised when the canonical W0 inventory cannot satisfy this lane."""


def _same_canonical_json(actual, expected):
    if actual != expected:
        return False
    try:
        return (
            canonical_manifest.canonical_json_bytes(actual)
            == canonical_manifest.canonical_json_bytes(expected)
        )
    except (canonical_manifest.PersonaManifestError, TypeError, ValueError):
        return False


def _digest(value):
    return hashlib.sha256(
        canonical_manifest.canonical_json_bytes(value)
    ).hexdigest()


def _rank(persona_id, profile, purpose, source_id):
    value = (
        f"{spec.FIXTURE_ID}\0{profile}\0{persona_id}\0{purpose}\0{source_id}"
    )
    return hashlib.sha256(value.encode("ascii")).digest(), source_id


def _ordered(persona_id, profile, purpose, rows):
    return sorted(
        rows,
        key=lambda row: _rank(
            persona_id, profile, purpose, row["source_id"]
        ),
    )


def _flatten(persona_plan):
    rows = []
    scopes = {}
    for scope in persona_plan["scopes"]:
        scope_key = scope["scope_key"]
        scopes[scope_key] = scope
        for source in scope["sources"]:
            row = dict(source)
            row["scope_key"] = scope_key
            row["scope_relative_path"] = scope["relative_path"]
            rows.append(row)
    rows.sort(key=lambda row: row["source_id"])
    return scopes, rows


def _variant_contract(family, variant):
    try:
        variants = spec.FORMAT_VARIANTS[family]
    except KeyError as error:
        raise StructuralAllocationError(
            f"unknown structural source family: {family}"
        ) from error
    policy = next((row for row in variants if row[0] == variant), None)
    if policy is None:
        raise StructuralAllocationError(
            f"variant does not belong to family: {family}/{variant}"
        )
    extension, media_type = renderers.variant_output_contract(family, variant)
    return {
        "family": family,
        "variant": variant,
        "gate_role": policy[2],
        "expected_disposition": policy[3],
        "extension": extension,
        "media_type": media_type,
    }


def _source_descriptor(row, *, render_contract=None):
    return {
        "schema_version": row["schema_version"],
        "source_id": row["source_id"],
        "version": row["version"],
        "render_origin_scope_key": row["scope_key"],
        "family": row["family"],
        "variant": row["variant"],
        "gate_role": row["gate_role"],
        "expected_disposition": row["expected_disposition"],
        "extension": row["extension"],
        "media_type": row["media_type"],
        "file_name": row["file_name"],
        "requested_contributor_chunks": row[
            "requested_contributor_chunks"
        ],
        "render_contract": render_contract or {
            "kind": "canonical-source/v1",
            "parent_source_ids": [],
        },
    }


def _new_source(template, source_id, scope_key, *, render_contract, policy=None):
    policy = policy or {
        key: template[key]
        for key in (
            "family",
            "variant",
            "gate_role",
            "expected_disposition",
            "extension",
            "media_type",
        )
    }
    if policy["gate_role"] != "raw_only":
        raise StructuralAllocationError("new structural sources must be raw-only")
    file_name = spec.validate_source_basename(
        f"{source_id}.{policy['extension']}"
    )
    return {
        "schema_version": spec.SCHEMA_VERSION,
        "source_id": source_id,
        "version": 0,
        "render_origin_scope_key": scope_key,
        **policy,
        "file_name": file_name,
        "requested_contributor_chunks": 0,
        "render_contract": render_contract,
    }


def _source_ordinal(source_id):
    try:
        prefix, value = source_id.rsplit("-", 1)
        ordinal = int(value)
    except (AttributeError, ValueError) as error:
        raise StructuralAllocationError(
            f"invalid source id ordinal: {source_id!r}"
        ) from error
    if not prefix.startswith("p") or not 1 <= ordinal <= 999_999:
        raise StructuralAllocationError(
            f"invalid source id ordinal: {source_id!r}"
        )
    return ordinal


def _materialization(source, scope_key, file_name=None, number=1):
    file_name = spec.validate_source_basename(file_name or source["file_name"])
    return {
        "materialization_id": (
            f"{source['source_id']}-materialization-{number:02d}"
        ),
        "source_id": source["source_id"],
        "source_version": source["version"],
        "render_origin_scope_key": source["render_origin_scope_key"],
        "current_scope_key": scope_key,
        "file_name": file_name,
    }


def _renamed(source, wave):
    return spec.validate_source_basename(
        f"{source['source_id']}-{wave.lower()}-renamed.{source['extension']}"
    )


def _moved(source, wave, operation="moved"):
    return spec.validate_source_basename(
        f"{source['source_id']}-{wave.lower()}-{operation}.{source['extension']}"
    )


def _scope_for_path(scopes, relative_path):
    matches = [
        scope_key
        for scope_key, scope in scopes.items()
        if scope["relative_path"] == relative_path
    ]
    if len(matches) != 1:
        raise StructuralAllocationError(
            f"expected one canonical scope path: {relative_path}"
        )
    return matches[0]


def _choose_scope(scopes, preferred_paths, excluded):
    excluded = set(excluded)
    for relative_path in preferred_paths:
        scope_key = _scope_for_path(scopes, relative_path)
        if scope_key not in excluded:
            return scope_key
    for scope_key in sorted(scopes):
        if scope_key not in excluded:
            return scope_key
    raise StructuralAllocationError("no distinct structural destination scope")


def _event(
    events,
    wave_counts,
    persona_id,
    wave,
    operation,
    scenario_lane_id,
    before,
    after,
    *,
    index_scope_keys,
    relation_kind,
    derived_from_source_ids=(),
    alias_of_materialization_ids=(),
    restored_from_materialization_ids=(),
    prior_event_ids=(),
    requires_raw_only,
    command_scope_key=None,
    search_claim,
    restore_locator=None,
):
    wave_counts[wave] += 1
    event_id = f"{persona_id}-{wave.lower()}-struct-{wave_counts[wave]:03d}"
    before = sorted(
        before,
        key=lambda row: (
            row["current_scope_key"], row["file_name"],
            row["materialization_id"],
        ),
    )
    after = sorted(
        after,
        key=lambda row: (
            row["current_scope_key"], row["file_name"],
            row["materialization_id"],
        ),
    )
    affected = {
        row["current_scope_key"] for row in before + after
    }
    if command_scope_key is not None:
        affected.add(command_scope_key)
    row = {
        "event_id": event_id,
        "ordinal": len(events) + 1,
        "wave": wave,
        "wave_ordinal": wave_counts[wave],
        "operation": operation,
        "scenario_lane_id": scenario_lane_id,
        "before_materializations": before,
        "after_materializations": after,
        "affected_scope_keys": sorted(affected),
        "index_scope_keys": sorted(set(index_scope_keys)),
        "command_scope_key": command_scope_key,
        "relation": {
            "kind": relation_kind,
            "derived_from_source_ids": sorted(derived_from_source_ids),
            "alias_of_materialization_ids": sorted(
                alias_of_materialization_ids
            ),
            "restored_from_materialization_ids": sorted(
                restored_from_materialization_ids
            ),
            "prior_event_ids": list(prior_event_ids),
        },
        "restore_locator": restore_locator,
        "requires_raw_only": requires_raw_only,
        "expected_contract_chunk_delta": {
            "current": 0,
            "history_only": 0,
        },
        "search_claim": search_claim,
    }
    events.append(row)
    return row


def _path_key(materialization):
    return (
        materialization["current_scope_key"],
        materialization["file_name"].casefold(),
    )


def _apply_structural_events(rows, events):
    live = {}
    for row in rows:
        source = _source_descriptor(row)
        materialization = _materialization(
            source, row["scope_key"], row["file_name"]
        )
        key = _path_key(materialization)
        if key in live:
            raise StructuralAllocationError("canonical W0 path collision")
        live[key] = materialization

    for event in events:
        before = event["before_materializations"]
        after = event["after_materializations"]
        before_keys = [_path_key(row) for row in before]
        after_keys = [_path_key(row) for row in after]
        if len(before_keys) != len(set(before_keys)):
            raise StructuralAllocationError("event repeats a before path")
        if len(after_keys) != len(set(after_keys)):
            raise StructuralAllocationError("event repeats an after path")
        for key, expected in zip(before_keys, before):
            if live.get(key) != expected:
                raise StructuralAllocationError(
                    f"event before state does not match: {event['event_id']}"
                )
        for key in before_keys:
            del live[key]
        for key, value in zip(after_keys, after):
            if key in live:
                raise StructuralAllocationError(
                    f"event destination is not absent: {event['event_id']}"
                )
            live[key] = value
    return live


def _build_structural_allocation(persona_plan, profile):
    if profile not in _PROFILE_EVENT_COUNTS:
        raise StructuralAllocationError(f"unknown persona profile: {profile!r}")
    try:
        history_plan = history.build_history_allocation(persona_plan, profile)
    except (history.HistoryAllocationError, KeyError, TypeError, ValueError) as error:
        raise StructuralAllocationError(str(error)) from error

    persona_id = history_plan["persona_id"]
    scopes, rows = _flatten(persona_plan)
    scope_keys = sorted(scopes)
    if scope_keys != history_plan["scope_keys"]:
        raise StructuralAllocationError("scope keys differ from history allocation")

    cohort_ids = {
        source_id
        for stratum in history_plan["strata"].values()
        for source_id in stratum["source_ids"]
    }
    u_candidates = [
        row for row in rows
        if row["gate_role"] == "contract_contributor"
        and row["source_id"] not in cohort_ids
    ]
    if profile == "full":
        rename_rows = []
        for scope_key in scope_keys:
            candidates = [
                row for row in u_candidates if row["scope_key"] == scope_key
            ]
            ordered = _ordered(
                persona_id, profile, f"w2-u-rename:{scope_key}", candidates
            )
            if not ordered:
                raise StructuralAllocationError(
                    f"full scope lacks a safe U rename source: {scope_key}"
                )
            rename_rows.append(ordered[0])
    else:
        ordered = _ordered(
            persona_id, profile, "w2-u-rename", u_candidates
        )
        if not ordered:
            raise StructuralAllocationError("persona lacks a safe U rename source")
        rename_rows = [ordered[0]]
    rename_rows.sort(key=lambda row: (row["scope_key"], row["source_id"]))
    primary_u_row = rename_rows[0]

    archive_scope = _scope_for_path(scopes, "archive/closed")
    traveler_family = TRAVELER_FAMILY_BY_PERSONA[persona_id]
    traveler_candidates = [
        row for row in rows
        if row["family"] == traveler_family
        and row["gate_role"] == "raw_only"
        and row["requested_contributor_chunks"] == 0
        and row["scope_key"] != archive_scope
    ]
    traveler_ordered = _ordered(
        persona_id, profile, "raw-traveler", traveler_candidates
    )
    if not traveler_ordered:
        raise StructuralAllocationError(
            f"persona lacks a non-archive {traveler_family} raw traveler"
        )
    traveler_row = traveler_ordered[0]

    png_candidates = [
        row for row in rows
        if row["family"] == "image"
        and row["variant"] == "png"
        and row["gate_role"] == "raw_only"
        and row["requested_contributor_chunks"] == 0
        and row["source_id"] != traveler_row["source_id"]
    ]
    png_ordered = _ordered(
        persona_id, profile, "png-transform-parent", png_candidates
    )
    if len(png_ordered) < 2:
        raise StructuralAllocationError(
            "persona needs two distinct raw PNG transform parents"
        )
    near_parent_row, derive_parent_row = png_ordered[:2]

    create_scope = _scope_for_path(scopes, "downloads/inbox")
    restore_scope = _choose_scope(
        scopes,
        ("documents/reference", "desktop/working", "cloud/my-files"),
        {create_scope},
    )
    traveler_origin = traveler_row["scope_key"]
    traveler_w1_scope = _choose_scope(
        scopes,
        ("desktop/working", "downloads/inbox", "cloud/my-files"),
        {traveler_origin, archive_scope},
    )
    traveler_w2_scope = _choose_scope(
        scopes,
        ("cloud/team-shared", "downloads/exports", "documents/reference"),
        {traveler_origin, traveler_w1_scope, archive_scope},
    )

    replacement_ids = [
        row["source_id"]
        for wave in ("W4", "W5")
        for row in history_plan["waves"][wave]["replacement_sources"]
    ]
    existing_ids = [row["source_id"] for row in rows] + replacement_ids
    first_structural_ordinal = max(_source_ordinal(value) for value in existing_ids) + 1
    if first_structural_ordinal + 2 > 999_999:
        raise StructuralAllocationError("structural source namespace is exhausted")
    structural_ids = [
        f"{persona_id}-src-{ordinal:06d}"
        for ordinal in range(first_structural_ordinal, first_structural_ordinal + 3)
    ]

    traveler = _source_descriptor(traveler_row)
    near_parent = _source_descriptor(near_parent_row)
    derive_parent = _source_descriptor(derive_parent_row)
    rename_sources = [_source_descriptor(row) for row in rename_rows]

    created = _new_source(
        traveler,
        structural_ids[0],
        create_scope,
        render_contract={
            "kind": "canonical-source/v1",
            "parent_source_ids": [],
        },
    )
    near_source = _new_source(
        near_parent,
        structural_ids[1],
        near_parent["render_origin_scope_key"],
        render_contract={
            "kind": "near-png-one-channel/v1",
            "parent_source_ids": [near_parent["source_id"]],
        },
        policy=_variant_contract("image", "png"),
    )
    derived_source = _new_source(
        derive_parent,
        structural_ids[2],
        derive_parent["render_origin_scope_key"],
        render_contract={
            "kind": "png-to-scan-pdf/v1",
            "parent_source_ids": [derive_parent["source_id"]],
        },
        policy=_variant_contract("pdf_scan", "pdf-scan"),
    )

    events = []
    wave_counts = {wave: 0 for wave in WAVE_ORDER}

    primary_u = rename_sources[0]
    primary_w0 = _materialization(
        primary_u,
        primary_u["render_origin_scope_key"],
        primary_u["file_name"],
    )
    primary_w1 = _materialization(
        primary_u,
        primary_u["render_origin_scope_key"],
        _renamed(primary_u, "W1"),
    )
    w1_rename = _event(
        events, wave_counts, persona_id, "W1", "same_scope_rename",
        "R", [primary_w0], [primary_w1],
        index_scope_keys=[primary_u["render_origin_scope_key"]],
        relation_kind="same-materialization",
        requires_raw_only=False,
        search_claim="same-scope-path-alias",
    )

    traveler_w0 = _materialization(
        traveler, traveler_origin, traveler["file_name"]
    )
    traveler_w1 = _materialization(
        traveler, traveler_w1_scope, _moved(traveler, "W1")
    )
    w1_move = _event(
        events, wave_counts, persona_id, "W1", "cross_scope_move",
        "M", [traveler_w0], [traveler_w1],
        index_scope_keys=[traveler_origin, traveler_w1_scope],
        relation_kind="same-materialization",
        requires_raw_only=True,
        search_claim="structural-only",
    )

    created_live = _materialization(created, create_scope)
    w1_create = _event(
        events, wave_counts, persona_id, "W1", "create",
        "C", [], [created_live],
        index_scope_keys=[create_scope],
        relation_kind="new-source",
        requires_raw_only=True,
        search_claim="structural-only",
    )

    final_u_materializations = {}
    w2_rename_events = []
    for source in rename_sources:
        is_primary = source["source_id"] == primary_u["source_id"]
        before = primary_w1 if is_primary else _materialization(
            source,
            source["render_origin_scope_key"],
            source["file_name"],
        )
        after = _materialization(
            source,
            source["render_origin_scope_key"],
            _renamed(source, "W2"),
        )
        event = _event(
            events, wave_counts, persona_id, "W2", "same_scope_rename",
            "R", [before], [after],
            index_scope_keys=[source["render_origin_scope_key"]],
            relation_kind="same-materialization",
            prior_event_ids=[w1_rename["event_id"]] if is_primary else [],
            requires_raw_only=False,
            search_claim="same-scope-path-alias",
        )
        w2_rename_events.append(event)
        final_u_materializations[source["source_id"]] = after

    traveler_w2 = _materialization(
        traveler, traveler_w2_scope, _moved(traveler, "W2")
    )
    w2_move = _event(
        events, wave_counts, persona_id, "W2", "cross_scope_move",
        "M", [traveler_w1], [traveler_w2],
        index_scope_keys=[traveler_w1_scope, traveler_w2_scope],
        relation_kind="same-materialization",
        prior_event_ids=[w1_move["event_id"]],
        requires_raw_only=True,
        search_claim="structural-only",
    )

    primary_w2 = final_u_materializations[primary_u["source_id"]]
    exact_alias = _materialization(
        primary_u,
        primary_u["render_origin_scope_key"],
        spec.validate_source_basename(
            f"{primary_u['source_id']}-w3-exact-copy.{primary_u['extension']}"
        ),
        number=2,
    )
    w3_exact = _event(
        events, wave_counts, persona_id, "W3", "exact_duplicate",
        "R", [primary_w2], [primary_w2, exact_alias],
        index_scope_keys=[primary_u["render_origin_scope_key"]],
        relation_kind="exact-alias",
        alias_of_materialization_ids=[primary_w2["materialization_id"]],
        prior_event_ids=[w2_rename_events[0]["event_id"]],
        requires_raw_only=False,
        search_claim="same-scope-path-alias",
    )

    near_parent_live = _materialization(
        near_parent,
        near_parent["render_origin_scope_key"],
        near_parent["file_name"],
    )
    near_live = _materialization(
        near_source, near_parent["render_origin_scope_key"]
    )
    w3_near = _event(
        events, wave_counts, persona_id, "W3", "near_duplicate",
        "NP", [near_parent_live], [near_parent_live, near_live],
        index_scope_keys=[near_parent["render_origin_scope_key"]],
        relation_kind="near-png-one-channel",
        derived_from_source_ids=[near_parent["source_id"]],
        requires_raw_only=True,
        search_claim="structural-only",
    )

    derive_parent_live = _materialization(
        derive_parent,
        derive_parent["render_origin_scope_key"],
        derive_parent["file_name"],
    )
    derived_live = _materialization(
        derived_source, derive_parent["render_origin_scope_key"]
    )
    w3_derive = _event(
        events, wave_counts, persona_id, "W3", "derived_format",
        "DP", [derive_parent_live], [derive_parent_live, derived_live],
        index_scope_keys=[derive_parent["render_origin_scope_key"]],
        relation_kind="png-to-scan-pdf",
        derived_from_source_ids=[derive_parent["source_id"]],
        requires_raw_only=True,
        search_claim="structural-only",
    )

    traveler_archive = _materialization(
        traveler,
        archive_scope,
        _moved(traveler, "W4", operation="archived"),
    )
    w4_archive = _event(
        events, wave_counts, persona_id, "W4", "archive_move",
        "M", [traveler_w2], [traveler_archive],
        index_scope_keys=[traveler_w2_scope, archive_scope],
        relation_kind="same-materialization",
        prior_event_ids=[w2_move["event_id"]],
        requires_raw_only=True,
        search_claim="organizational-archive-only",
    )

    w4_delete = _event(
        events, wave_counts, persona_id, "W4", "delete_for_restore",
        "C", [created_live], [],
        index_scope_keys=[create_scope],
        relation_kind="delete-preserve-history",
        prior_event_ids=[w1_create["event_id"]],
        requires_raw_only=True,
        search_claim="structural-only",
    )

    restored_live = _materialization(
        created, restore_scope, created["file_name"], number=2
    )
    w5_restore = _event(
        events, wave_counts, persona_id, "W5", "restore_to_active_scope",
        "C", [], [restored_live],
        index_scope_keys=[restore_scope],
        relation_kind="restore-deleted-source",
        restored_from_materialization_ids=[created_live["materialization_id"]],
        prior_event_ids=[w4_delete["event_id"]],
        requires_raw_only=True,
        command_scope_key=create_scope,
        search_claim="structural-only",
        restore_locator={
            "kind": "path-at-checkpoint",
            "source_scope_key": create_scope,
            "source_file_name": created_live["file_name"],
            "source_materialization_id": created_live["materialization_id"],
            "source_version": created["version"],
            "checkpoint": "W4",
            "expected_purged": False,
            "command_boundary_kind": "none",
            "destination_scope_key": restore_scope,
        },
    )

    live = _apply_structural_events(rows, events)
    final_delta = len(live) - len(rows)
    if final_delta != 4:
        raise StructuralAllocationError(
            f"structural final physical delta must be four, got {final_delta}"
        )

    expected_counts = _PROFILE_EVENT_COUNTS[profile]
    if wave_counts != expected_counts:
        raise StructuralAllocationError(
            f"structural event counts drifted: {wave_counts!r}"
        )
    index_scopes = {
        wave: sorted({
            scope_key
            for event in events if event["wave"] == wave
            for scope_key in event["index_scope_keys"]
        })
        for wave in WAVE_ORDER
    }
    if profile == "full" and index_scopes["W2"] != scope_keys:
        raise StructuralAllocationError(
            "full W2 structural events must cover all twenty scopes"
        )

    return {
        "schema": STRUCTURAL_ALLOCATION_SCHEMA,
        "schema_version": STRUCTURAL_ALLOCATION_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": persona_id,
        "history_allocation_sha256": _digest(history_plan),
        "scope_keys": scope_keys,
        "contracts": {
            "root_independent": True,
            "planned_not_observed": True,
            "cross_scope_sources_must_be_raw_only": True,
            "structural_actual_chunk_attestation_required": True,
            "full_w2_twenty_scope_coverage": profile == "full",
            "archive_scope_remains_active": True,
            "restore_destination_is_existing_active_scope": True,
            "source_ordinals_are_opaque_not_temporal": True,
        },
        "source_namespace": {
            "w0_source_count": len(rows),
            "history_replacement_source_ids": sorted(replacement_ids),
            "first_structural_source_ordinal": first_structural_ordinal,
            "structural_source_ids": structural_ids,
            "next_source_ordinal": first_structural_ordinal + 3,
        },
        "anchors": {
            "rename_u_sources": rename_sources,
            "primary_rename_source_id": primary_u["source_id"],
            "raw_traveler": traveler,
            "near_png_parent": near_parent,
            "derive_png_parent": derive_parent,
        },
        "new_sources": [created, near_source, derived_source],
        "events": events,
        "event_counts_by_wave": dict(wave_counts),
        "structural_index_scope_keys_by_wave": index_scopes,
        "physical_file_delta_by_checkpoint": {
            "W0": 0,
            "W1": 1,
            "W2": 1,
            "W3": 4,
            "W4": 3,
            "W5": 4,
        },
        "totals": {
            "events": len(events),
            "new_source_ids": 3,
            "new_materializations": 5,
            "final_live_physical_file_delta": 4,
            "final_distinct_source_id_delta": 3,
            "contract_current_chunk_delta": 0,
            "contract_history_only_chunk_delta": 0,
        },
    }


def build_structural_allocation(persona_plan, profile):
    """Return one deterministic root-independent structural allocation."""
    return _build_structural_allocation(persona_plan, profile)


def validate_structural_allocation(structural_plan, persona_plan, profile):
    """Reject anything other than the canonical typed structural expansion."""
    if type(structural_plan) is not dict:
        raise StructuralAllocationError("structural plan must be an object")
    expected = _build_structural_allocation(persona_plan, profile)
    if not _same_canonical_json(structural_plan, expected):
        raise StructuralAllocationError(
            "structural plan differs from canonical allocation"
        )
    return True
