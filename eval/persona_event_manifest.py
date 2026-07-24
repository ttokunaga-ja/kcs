"""Immutable root-independent planned event manifests for persona history.

This module joins the whole-source P/X/Y/N history allocation with the
quota-neutral structural allocation.  It deliberately records rendered-byte
facts, complete tagged before/after state, commit-boundary intent, and a
logical schedule without claiming that KIO or a filesystem was observed.

The three arrays ``events``, ``boundaries``, and ``schedule`` are independent
canonical inventories.  In particular, an ordinary ``index_auto`` boundary
is allocated exactly once for each ``(wave, scope)`` pair and can cover many
events.  W5 path purges remain serialized one source at a time, each followed
immediately by its own ``purged_commit`` boundary.
"""

from __future__ import annotations

import copy
from dataclasses import asdict
import hashlib

try:  # Package imports and direct ``python eval/...`` execution.
    from . import generate_persona_corpus as generator
    from . import persona_fixture_spec as spec
    from . import persona_history_allocation as history
    from . import persona_manifest as canonical_manifest
    from . import persona_renderers as renderers
    from . import persona_structural_allocation as structural
except ImportError:  # pragma: no cover - direct-script compatibility.
    import generate_persona_corpus as generator
    import persona_fixture_spec as spec
    import persona_history_allocation as history
    import persona_manifest as canonical_manifest
    import persona_renderers as renderers
    import persona_structural_allocation as structural


EVENT_MANIFEST_SCHEMA = "kio.persona.event-manifest/v1"
EVENT_MANIFEST_SCHEMA_VERSION = 1
MANAGED_EVENT_STATE_SCHEMA = "kio.persona.managed-event-state/v1"
LOGICAL_TIME_SCHEMA = "kio.persona.logical-time/v1"
PLANNING_STATUS = "planned_not_observed"
WAVE_ORDER = ("W1", "W2", "W3", "W4", "W5")

_RENDERED_CONTENT_FIELDS = (
    "raw_sha256",
    "raw_bytes",
    "render_request",
    "render_request_sha256",
    "renderer_id",
    "renderer_schema_version",
    "logical_member_count",
    "planned_contract_chunks",
    "render_contract",
    "transform_witness",
)

_TYPED_RELATION_FIELDS = (
    "kind",
    "source_ids",
    "materialization_ids",
    "from_source_versions",
    "to_source_versions",
    "replaces_source_ids",
    "derived_from_source_ids",
    "alias_of_materialization_ids",
    "restored_from_materialization_ids",
)


class EventManifestError(ValueError):
    """Raised when a planned event manifest is not exactly canonical."""


def _digest(value):
    return hashlib.sha256(
        canonical_manifest.canonical_json_bytes(value)
    ).hexdigest()


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


def _flatten_persona(persona_plan):
    scopes = {}
    sources = {}
    for scope in persona_plan["scopes"]:
        scope_key = scope["scope_key"]
        scopes[scope_key] = scope
        for value in scope["sources"]:
            source = dict(value)
            source["render_origin_scope_key"] = scope_key
            source["scope_key"] = scope_key
            if source["source_id"] in sources:
                raise EventManifestError("persona plan repeats a source id")
            sources[source["source_id"]] = source
    return scopes, sources


def _replacement_source(value):
    return {
        "schema_version": value["schema_version"],
        "source_id": value["source_id"],
        "version": value["version"],
        "render_origin_scope_key": value["scope_key"],
        "scope_key": value["scope_key"],
        "family": value["family"],
        "variant": value["variant"],
        "gate_role": value["gate_role"],
        "expected_disposition": value["expected_disposition"],
        "extension": value["extension"],
        "media_type": value["media_type"],
        "file_name": value["file_name"],
        "requested_contributor_chunks": value[
            "requested_contributor_chunks"
        ],
    }


def _source_projection(value):
    """Return only source facts that determine rendering and gate behavior."""
    result = {
        "schema_version": value["schema_version"],
        "source_id": value["source_id"],
        "version": value["version"],
        "render_origin_scope_key": value["render_origin_scope_key"],
        "family": value["family"],
        "variant": value["variant"],
        "gate_role": value["gate_role"],
        "expected_disposition": value["expected_disposition"],
        "extension": value["extension"],
        "media_type": value["media_type"],
        "file_name": value["file_name"],
        "requested_contributor_chunks": value[
            "requested_contributor_chunks"
        ],
    }
    if "render_contract" in value:
        result["render_contract"] = copy.deepcopy(value["render_contract"])
    return result


class _ContentResolver:
    """Render affected sources while retaining only bounded byte metadata."""

    def __init__(self, persona_id, scopes, sources):
        self.persona_id = persona_id
        self.scopes = scopes
        self.sources = sources
        self._projections = {}

    def _source_at_version(self, source_id, version):
        source = _source_projection(self.sources[source_id])
        source["version"] = version
        return source

    def _full_parent_materialization(self, source_id):
        source = self._source_at_version(source_id, 0)
        scope = self.scopes[source["render_origin_scope_key"]]
        contract = source.get("render_contract")
        if contract is None or contract["kind"] == "canonical-source/v1":
            return generator.materialize_source(self.persona_id, scope, source)
        parents = tuple(
            self._full_parent_materialization(parent_id)
            for parent_id in contract["parent_source_ids"]
        )
        return generator.materialize_structural_source(
            self.persona_id,
            scope,
            source,
            parent_materializations=parents,
        )

    def content(self, source_id, version):
        key = (source_id, version)
        cached = self._projections.get(key)
        if cached is not None:
            return copy.deepcopy(cached)
        source = self._source_at_version(source_id, version)
        scope = self.scopes[source["render_origin_scope_key"]]
        contract = source.get("render_contract")
        if contract is None:
            materialized = generator.materialize_source(
                self.persona_id, scope, source
            )
            render_contract = {
                "kind": "canonical-source/v1",
                "parent_source_ids": [],
            }
            witness = None
        else:
            parents = tuple(
                self._full_parent_materialization(parent_id)
                for parent_id in contract["parent_source_ids"]
            )
            materialized = generator.materialize_structural_source(
                self.persona_id,
                scope,
                source,
                parent_materializations=parents,
            )
            render_contract = copy.deepcopy(contract)
            witness = copy.deepcopy(materialized["transform_witness"])
        request = asdict(materialized["request"])
        physical = materialized["physical"]
        projection = {
            "raw_sha256": physical["raw_sha256"],
            "raw_bytes": physical["bytes"],
            "render_request": request,
            "render_request_sha256": _digest(request),
            "renderer_id": physical["renderer_id"],
            "renderer_schema_version": physical[
                "renderer_schema_version"
            ],
            "logical_member_count": physical["logical_members"],
            "planned_contract_chunks": physical[
                "expected_contract_chunks"
            ],
            "render_contract": render_contract,
            "transform_witness": witness,
        }
        self._projections[key] = projection
        return copy.deepcopy(projection)

    def materialization(
        self,
        source_id,
        version,
        current_scope_key,
        file_name,
        materialization_id=None,
    ):
        source = self.sources[source_id]
        return {
            "materialization_id": materialization_id or (
                f"{source_id}-materialization-01"
            ),
            "source_id": source_id,
            "source_version": version,
            "render_origin_scope_key": source["render_origin_scope_key"],
            "current_scope_key": current_scope_key,
            "file_name": file_name,
            "relative_path": (
                f"{self.scopes[current_scope_key]['relative_path']}/{file_name}"
            ),
            "family": source["family"],
            "variant": source["variant"],
            "gate_role": source["gate_role"],
            "expected_disposition": source["expected_disposition"],
            "extension": source["extension"],
            "media_type": source["media_type"],
            "requested_contributor_chunks": source[
                "requested_contributor_chunks"
            ],
            **self.content(source_id, version),
        }


def _location(value):
    return (value["current_scope_key"], value["file_name"].casefold())


def _complete_transition(before_present, after_present):
    before_by_path = {_location(value): value for value in before_present}
    after_by_path = {_location(value): value for value in after_present}
    if len(before_by_path) != len(before_present):
        raise EventManifestError("event repeats a before path")
    if len(after_by_path) != len(after_present):
        raise EventManifestError("event repeats an after path")
    before = []
    after = []
    for key in sorted(set(before_by_path) | set(after_by_path)):
        before_value = before_by_path.get(key)
        after_value = after_by_path.get(key)
        before.append({
            "presence": "present" if before_value is not None else "absent",
            "materialization": copy.deepcopy(before_value or after_value),
        })
        after.append({
            "presence": "present" if after_value is not None else "absent",
            "materialization": copy.deepcopy(after_value or before_value),
        })
    return {"before": before, "after": after}


def _relation(
    kind,
    *,
    source_ids=(),
    materialization_ids=(),
    from_source_versions=(),
    to_source_versions=(),
    replaces_source_ids=(),
    derived_from_source_ids=(),
    alias_of_materialization_ids=(),
    restored_from_materialization_ids=(),
    prior_event_ids=(),
):
    return {
        "kind": kind,
        "source_ids": list(source_ids),
        "materialization_ids": list(materialization_ids),
        "from_source_versions": list(from_source_versions),
        "to_source_versions": list(to_source_versions),
        "replaces_source_ids": list(replaces_source_ids),
        "derived_from_source_ids": list(derived_from_source_ids),
        "alias_of_materialization_ids": list(
            alias_of_materialization_ids
        ),
        "restored_from_materialization_ids": list(
            restored_from_materialization_ids
        ),
        "prior_event_ids": list(prior_event_ids),
    }


def _make_event(
    event_id,
    wave,
    lane,
    operation,
    before_present,
    after_present,
    *,
    index_scope_keys,
    relation,
    source_command,
    expected_delta,
    execution_phase="regular",
    restore_locator=None,
    history_purge_versions=(),
    requires_raw_only=None,
    search_claim=None,
):
    transition = _complete_transition(before_present, after_present)
    affected_set = {
        state["materialization"]["current_scope_key"]
        for side in (transition["before"], transition["after"])
        for state in side
    }
    if type(source_command.get("scope_key")) is str:
        affected_set.add(source_command["scope_key"])
    affected = sorted(affected_set)
    return {
        "event_id": event_id,
        "wave": wave,
        "lane": lane,
        "operation": operation,
        "execution_phase": execution_phase,
        "source_command": source_command,
        "state_transition": transition,
        "affected_scope_keys": affected,
        "index_scope_keys": sorted(set(index_scope_keys)),
        "boundary_refs": [],
        "relation": relation,
        "restore_locator": copy.deepcopy(restore_locator),
        "history_purge_versions": list(history_purge_versions),
        "requires_raw_only": requires_raw_only,
        "expected_contract_chunk_delta": dict(expected_delta),
        "search_claim": search_claim,
    }


def _history_events(history_plan, sources, resolver):
    persona_id = history_plan["persona_id"]
    stratum_by_source = {
        source_id: name
        for name, value in history_plan["strata"].items()
        for source_id in value["source_ids"]
    }
    events = {wave: [] for wave in WAVE_ORDER}
    purge_events = []

    def original(source_id, version):
        source = sources[source_id]
        return resolver.materialization(
            source_id,
            version,
            source["scope_key"],
            source["file_name"],
        )

    for source_id in history_plan["waves"]["W1"]["edit_source_ids"]:
        quota = sources[source_id]["requested_contributor_chunks"]
        before = original(source_id, 0)
        after = original(source_id, 1)
        events["W1"].append(_make_event(
            f"{persona_id}-w1-history-edit-{source_id}",
            "W1", "history", "edit_v0_to_v1", [before], [after],
            index_scope_keys=[sources[source_id]["scope_key"]],
            relation=_relation(
                "same-source-version-advance",
                source_ids=[source_id],
                materialization_ids=[before["materialization_id"]],
                from_source_versions=[0],
                to_source_versions=[1],
            ),
            source_command={
                "kind": "filesystem_replace_exact_path",
                "scope_key": sources[source_id]["scope_key"],
            },
            expected_delta={"current": 0, "history_only": quota},
            search_claim=f"history-stratum-{stratum_by_source[source_id]}",
        ))

    w3_ids = history_plan["waves"]["W3"]["major_edit_source_ids"]
    for source_id in w3_ids:
        first = 0 if stratum_by_source[source_id] == history.LATE_THEN_CORRECT else 1
        quota = sources[source_id]["requested_contributor_chunks"]
        before = original(source_id, first)
        after = original(source_id, first + 1)
        events["W3"].append(_make_event(
            f"{persona_id}-w3-history-edit-{source_id}",
            "W3", "history", f"edit_v{first}_to_v{first + 1}",
            [before], [after],
            index_scope_keys=[sources[source_id]["scope_key"]],
            relation=_relation(
                "same-source-version-advance",
                source_ids=[source_id],
                materialization_ids=[before["materialization_id"]],
                from_source_versions=[first],
                to_source_versions=[first + 1],
                prior_event_ids=(
                    [f"{persona_id}-w1-history-edit-{source_id}"]
                    if first == 1 else []
                ),
            ),
            source_command={
                "kind": "filesystem_replace_exact_path",
                "scope_key": sources[source_id]["scope_key"],
            },
            expected_delta={"current": 0, "history_only": quota},
            search_claim=f"history-stratum-{stratum_by_source[source_id]}",
        ))

    w4_replacements = {
        value["replaces_source_id"]: value
        for value in history_plan["waves"]["W4"]["replacement_sources"]
    }
    for source_id in history_plan["waves"]["W4"]["delete_source_ids"]:
        replacement = w4_replacements[source_id]
        old = original(source_id, 2)
        new = resolver.materialization(
            replacement["source_id"],
            0,
            replacement["scope_key"],
            replacement["file_name"],
        )
        quota = sources[source_id]["requested_contributor_chunks"]
        events["W4"].append(_make_event(
            f"{persona_id}-w4-history-replace-{source_id}",
            "W4", "history", "replace_x_one_for_one", [old], [new],
            index_scope_keys=[replacement["scope_key"]],
            relation=_relation(
                "one-for-one-replacement",
                source_ids=[replacement["source_id"]],
                materialization_ids=[new["materialization_id"]],
                replaces_source_ids=[source_id],
                from_source_versions=[2],
                to_source_versions=[0],
                prior_event_ids=[
                    f"{persona_id}-w3-history-edit-{source_id}"
                ],
            ),
            source_command={
                "kind": "filesystem_unlink_and_create_replacement",
                "scope_key": replacement["scope_key"],
            },
            expected_delta={"current": 0, "history_only": quota},
            search_claim="history-stratum-X-replacement",
        ))

    for source_id in history_plan["waves"]["W5"]["correct_source_ids"]:
        quota = sources[source_id]["requested_contributor_chunks"]
        before = original(source_id, 1)
        after = original(source_id, 2)
        events["W5"].append(_make_event(
            f"{persona_id}-w5-history-correct-{source_id}",
            "W5", "history", "correct_n_v1_to_v2", [before], [after],
            index_scope_keys=[sources[source_id]["scope_key"]],
            relation=_relation(
                "same-source-version-advance",
                source_ids=[source_id],
                materialization_ids=[before["materialization_id"]],
                from_source_versions=[1],
                to_source_versions=[2],
                prior_event_ids=[
                    f"{persona_id}-w3-history-edit-{source_id}"
                ],
            ),
            source_command={
                "kind": "filesystem_replace_exact_path",
                "scope_key": sources[source_id]["scope_key"],
            },
            expected_delta={"current": 0, "history_only": quota},
            search_claim="history-stratum-N-correction",
        ))

    w5_replacements = {
        value["replaces_source_id"]: value
        for value in history_plan["waves"]["W5"]["replacement_sources"]
    }
    for source_id in history_plan["waves"]["W5"]["purge_source_ids"]:
        replacement = w5_replacements[source_id]
        new = resolver.materialization(
            replacement["source_id"],
            0,
            replacement["scope_key"],
            replacement["file_name"],
        )
        quota = sources[source_id]["requested_contributor_chunks"]
        events["W5"].append(_make_event(
            f"{persona_id}-w5-history-create-replacement-{source_id}",
            "W5", "history", "create_p_replacement", [], [new],
            index_scope_keys=[replacement["scope_key"]],
            relation=_relation(
                "one-for-one-replacement",
                source_ids=[replacement["source_id"]],
                materialization_ids=[new["materialization_id"]],
                replaces_source_ids=[source_id],
                to_source_versions=[0],
                prior_event_ids=[
                    f"{persona_id}-w1-history-edit-{source_id}"
                ],
            ),
            source_command={
                "kind": "filesystem_create_no_replace",
                "scope_key": replacement["scope_key"],
            },
            expected_delta={"current": quota, "history_only": 0},
            search_claim="history-stratum-P-replacement",
        ))

        old = original(source_id, 1)
        versions = []
        for version in (0, 1):
            content = resolver.content(source_id, version)
            versions.append({
                "source_id": source_id,
                "source_version": version,
                "raw_sha256": content["raw_sha256"],
                "raw_bytes": content["raw_bytes"],
                "render_request_sha256": content[
                    "render_request_sha256"
                ],
                "planned_contract_chunks": content[
                    "planned_contract_chunks"
                ],
                "rendered_content_sha256": _digest({
                    key: content[key] for key in _RENDERED_CONTENT_FIELDS
                }),
            })
        purge_events.append(_make_event(
            f"{persona_id}-w5-history-path-purge-{source_id}",
            "W5", "history", "unlink_then_path_purge", [old], [],
            index_scope_keys=[],
            relation=_relation(
                "path-purge-all-source-versions",
                source_ids=[source_id],
                materialization_ids=[old["materialization_id"]],
                from_source_versions=[0, 1],
                prior_event_ids=[
                    f"{persona_id}-w1-history-edit-{source_id}",
                    f"{persona_id}-w5-history-create-replacement-{source_id}",
                ],
            ),
            source_command={
                "kind": "filesystem_unlink_exact_path",
                "scope_key": sources[source_id]["scope_key"],
            },
            expected_delta={"current": -quota, "history_only": -quota},
            execution_phase="purge_serial",
            history_purge_versions=versions,
            search_claim="history-stratum-P-purged",
        ))
    return events, purge_events


def _structural_events(structural_plan, resolver):
    events = {wave: [] for wave in WAVE_ORDER}
    for value in structural_plan["events"]:
        before = [
            resolver.materialization(
                row["source_id"], row["source_version"],
                row["current_scope_key"], row["file_name"],
                row["materialization_id"],
            )
            for row in value["before_materializations"]
        ]
        after = [
            resolver.materialization(
                row["source_id"], row["source_version"],
                row["current_scope_key"], row["file_name"],
                row["materialization_id"],
            )
            for row in value["after_materializations"]
        ]
        source_ids = sorted({row["source_id"] for row in before + after})
        materialization_ids = sorted({
            row["materialization_id"] for row in before + after
        })
        source_command = {
            "kind": f"filesystem_{value['operation']}",
            "scope_key": value["command_scope_key"],
        }
        restore_locator = value["restore_locator"]
        if value["operation"] == "restore_to_active_scope":
            restored = after[0]
            source_command = {
                "kind": "kio_restore_path",
                "scope_key": value["command_scope_key"],
                "commit_boundary_kind": "none",
                "force": False,
            }
            restore_locator = {
                **copy.deepcopy(restore_locator),
                "expected_raw_sha256": restored["raw_sha256"],
                "expected_raw_bytes": restored["raw_bytes"],
            }
        relation_value = value["relation"]
        relation = _relation(
            relation_value["kind"],
            source_ids=source_ids,
            materialization_ids=materialization_ids,
            from_source_versions=sorted({
                row["source_version"] for row in before
            }),
            to_source_versions=sorted({
                row["source_version"] for row in after
            }),
            derived_from_source_ids=relation_value[
                "derived_from_source_ids"
            ],
            alias_of_materialization_ids=relation_value[
                "alias_of_materialization_ids"
            ],
            restored_from_materialization_ids=relation_value[
                "restored_from_materialization_ids"
            ],
            prior_event_ids=relation_value["prior_event_ids"],
        )
        events[value["wave"]].append(_make_event(
            value["event_id"], value["wave"], "structural",
            value["operation"], before, after,
            index_scope_keys=value["index_scope_keys"],
            relation=relation,
            source_command=source_command,
            expected_delta=value["expected_contract_chunk_delta"],
            restore_locator=restore_locator,
            requires_raw_only=value["requires_raw_only"],
            search_claim=value["search_claim"],
        ))
    return events


def _boundary_id(persona_id, wave, kind, discriminator):
    return f"{persona_id}-{wave.lower()}-{kind.replace('_', '-')}-{discriminator}"


def _build_boundaries(persona_id, regular_by_wave, purge_events):
    boundaries = []
    auto_by_wave_scope = {}
    for wave in WAVE_ORDER:
        scopes = sorted({
            scope_key
            for event in regular_by_wave[wave]
            for scope_key in event["index_scope_keys"]
        })
        for scope_key in scopes:
            event_ids = sorted(
                event["event_id"]
                for event in regular_by_wave[wave]
                if scope_key in event["index_scope_keys"]
            )
            boundary = {
                "boundary_id": _boundary_id(
                    persona_id, wave, "index_auto", scope_key
                ),
                "wave": wave,
                "kind": "index_auto",
                "scope_key": scope_key,
                "source_id": None,
                "covered_event_ids": event_ids,
                "command": {"kind": "kio_index_auto"},
                "expected_commit_result": "new_auto_commit",
                "status": PLANNING_STATUS,
            }
            boundaries.append(boundary)
            auto_by_wave_scope[(wave, scope_key)] = boundary

    purged_by_event = {}
    for event in purge_events:
        source_id = event["relation"]["source_ids"][0]
        scope_key = event["source_command"]["scope_key"]
        boundary = {
            "boundary_id": _boundary_id(
                persona_id, "W5", "purged_commit", source_id
            ),
            "wave": "W5",
            "kind": "purged_commit",
            "scope_key": scope_key,
            "source_id": source_id,
            "covered_event_ids": [event["event_id"]],
            "command": {
                "kind": "kio_purge_path",
                "reason": "legal",
                "confirmation": "yes",
            },
            "expected_commit_result": "exactly_one_purged_commit",
            "status": PLANNING_STATUS,
        }
        boundaries.append(boundary)
        purged_by_event[event["event_id"]] = boundary

    noop_by_scope = {}
    for scope_key in sorted({
        event["source_command"]["scope_key"] for event in purge_events
    }):
        boundary = {
            "boundary_id": _boundary_id(
                persona_id, "W5", "index_noop", scope_key
            ),
            "wave": "W5",
            "kind": "index_noop",
            "scope_key": scope_key,
            "source_id": None,
            "covered_event_ids": sorted(
                event["event_id"]
                for event in purge_events
                if event["source_command"]["scope_key"] == scope_key
            ),
            "command": {"kind": "kio_index_auto"},
            "expected_commit_result": "no_new_commit",
            "status": PLANNING_STATUS,
        }
        boundaries.append(boundary)
        noop_by_scope[scope_key] = boundary
    return boundaries, auto_by_wave_scope, purged_by_event, noop_by_scope


def _boundary_role(event, scope_key):
    if event["operation"] == "restore_to_active_scope":
        return "destination_index"
    before_scopes = {
        state["materialization"]["current_scope_key"]
        for state in event["state_transition"]["before"]
        if state["presence"] == "present"
    }
    after_scopes = {
        state["materialization"]["current_scope_key"]
        for state in event["state_transition"]["after"]
        if state["presence"] == "present"
    }
    if scope_key in before_scopes and scope_key not in after_scopes:
        return "source_index"
    if scope_key in after_scopes and scope_key not in before_scopes:
        return "destination_index"
    return "affected_index"


def _bind_event_boundaries(
    regular_by_wave,
    purge_events,
    auto_by_wave_scope,
    purged_by_event,
    noop_by_scope,
):
    for wave in WAVE_ORDER:
        for event in regular_by_wave[wave]:
            refs = []
            if event["operation"] == "restore_to_active_scope":
                refs.append({
                    "role": "source_command",
                    "kind": "none",
                    "scope_key": event["source_command"]["scope_key"],
                    "boundary_id": None,
                })
            for scope_key in event["index_scope_keys"]:
                boundary = auto_by_wave_scope[(wave, scope_key)]
                refs.append({
                    "role": _boundary_role(event, scope_key),
                    "kind": "index_auto",
                    "scope_key": scope_key,
                    "boundary_id": boundary["boundary_id"],
                })
            event["boundary_refs"] = refs
    for event in purge_events:
        boundary = purged_by_event[event["event_id"]]
        noop = noop_by_scope[boundary["scope_key"]]
        event["boundary_refs"] = [
            {
                "role": "purge_commit",
                "kind": "purged_commit",
                "scope_key": boundary["scope_key"],
                "boundary_id": boundary["boundary_id"],
            },
            {
                "role": "post_purge_noop_index",
                "kind": "index_noop",
                "scope_key": noop["scope_key"],
                "boundary_id": noop["boundary_id"],
            },
        ]


def _build_schedule(
    regular_by_wave, purge_events, auto_by_wave_scope,
    purged_by_event, noop_by_scope
):
    schedule = []

    def append(wave, phase, item_kind, item_id):
        ordinal = len(schedule) + 1
        schedule.append({
            "schedule_ordinal": ordinal,
            "logical_tick": ordinal,
            "logical_time": f"T{ordinal:08d}",
            "wave": wave,
            "phase": phase,
            "item_kind": item_kind,
            "item_id": item_id,
            "prior_item_id": (
                schedule[-1]["item_id"] if schedule else None
            ),
        })

    for wave in WAVE_ORDER[:-1]:
        for event in regular_by_wave[wave]:
            append(wave, "regular_events", "event", event["event_id"])
        for (_wave, _scope_key), boundary in sorted(
            auto_by_wave_scope.items()
        ):
            if _wave == wave:
                append(
                    wave, "ordinary_auto_indexes", "boundary",
                    boundary["boundary_id"],
                )

    for event in regular_by_wave["W5"]:
        append("W5", "regular_events", "event", event["event_id"])
    for (_wave, _scope_key), boundary in sorted(auto_by_wave_scope.items()):
        if _wave == "W5":
            append(
                "W5", "ordinary_auto_indexes", "boundary",
                boundary["boundary_id"],
            )
    for event in purge_events:
        append("W5", "serialized_path_purges", "event", event["event_id"])
        append(
            "W5", "serialized_path_purges", "boundary",
            purged_by_event[event["event_id"]]["boundary_id"],
        )
    for scope_key in sorted(noop_by_scope):
        append(
            "W5", "post_purge_noop_indexes", "boundary",
            noop_by_scope[scope_key]["boundary_id"],
        )
    return schedule


def _attach_logical_order(events, boundaries, schedule):
    by_id = {
        value["event_id"]: value for value in events
    }
    by_id.update({value["boundary_id"]: value for value in boundaries})
    for item in schedule:
        value = by_id[item["item_id"]]
        value["logical_tick"] = item["logical_tick"]
        value["logical_time"] = item["logical_time"]
    events.sort(key=lambda value: value["logical_tick"])
    boundaries.sort(key=lambda value: value["logical_tick"])
    for ordinal, event in enumerate(events, start=1):
        event["event_ordinal"] = ordinal
    wave_ordinals = {wave: 0 for wave in WAVE_ORDER}
    for event in events:
        wave_ordinals[event["wave"]] += 1
        event["wave_event_ordinal"] = wave_ordinals[event["wave"]]


def _state_root(leaf_hashes):
    """Hash sorted managed paths through bounded materialization leaf hashes."""
    return _digest([
        {
            "current_scope_key": key[0],
            "casefold_file_name": key[1],
            "materialization_sha256": value,
        }
        for key, value in sorted(leaf_hashes.items())
    ])


def _apply_managed_state(events, initial_materializations):
    state = {}
    leaf_hashes = {}
    for value in initial_materializations:
        key = _location(value)
        if key in state:
            raise EventManifestError("managed initial state repeats a path")
        state[key] = copy.deepcopy(value)
        leaf_hashes[key] = _digest(value)
    initial_root = _state_root(leaf_hashes)
    prior_event_sha256 = None
    for event in events:
        before_root = _state_root(leaf_hashes)
        for expected in event["state_transition"]["before"]:
            materialization = expected["materialization"]
            key = _location(materialization)
            if expected["presence"] == "present":
                if not _same_canonical_json(state.get(key), materialization):
                    raise EventManifestError(
                        f"managed before state differs: {event['event_id']}"
                    )
            elif expected["presence"] == "absent":
                if key in state:
                    raise EventManifestError(
                        f"managed before path is not absent: {event['event_id']}"
                    )
            else:
                raise EventManifestError("state presence tag is invalid")
        for expected in event["state_transition"]["after"]:
            materialization = expected["materialization"]
            key = _location(materialization)
            if expected["presence"] == "present":
                state[key] = copy.deepcopy(materialization)
                leaf_hashes[key] = _digest(materialization)
            elif expected["presence"] == "absent":
                state.pop(key, None)
                leaf_hashes.pop(key, None)
            else:
                raise EventManifestError("state presence tag is invalid")
        event["managed_state_root_before_sha256"] = before_root
        event["managed_state_root_after_sha256"] = _state_root(leaf_hashes)
        event["prior_event_sha256"] = prior_event_sha256
        event["event_sha256"] = _digest(event)
        prior_event_sha256 = event["event_sha256"]
    return {
        "schema": MANAGED_EVENT_STATE_SCHEMA,
        "schema_version": 1,
        "scope": "managed_event_sources_not_full_w0",
        "root_algorithm": (
            "sha256-canonical-sorted-location-materialization-leaf/v1"
        ),
        "initial_materialization_count": len(initial_materializations),
        "initial_materializations": initial_materializations,
        "initial_root_sha256": initial_root,
        "final_materialization_count": len(state),
        "final_root_sha256": _state_root(leaf_hashes),
        "final_event_sha256": prior_event_sha256,
    }


def _initial_materializations(
    history_plan, structural_plan, sources, resolver
):
    source_ids = {
        source_id
        for value in history_plan["strata"].values()
        for source_id in value["source_ids"]
    }
    source_ids.update(
        value["source_id"]
        for value in structural_plan["anchors"]["rename_u_sources"]
    )
    source_ids.update({
        structural_plan["anchors"]["raw_traveler"]["source_id"],
        structural_plan["anchors"]["near_png_parent"]["source_id"],
        structural_plan["anchors"]["derive_png_parent"]["source_id"],
    })
    result = []
    for source_id in sorted(source_ids):
        source = sources[source_id]
        result.append(resolver.materialization(
            source_id, 0, source["scope_key"], source["file_name"]
        ))
    return result


def _w0_materialization_owners(persona_plan):
    """Return the lightweight full-W0 owner inventory without rendering it."""
    owners = []
    materialization_ids = set()
    locations = set()
    for scope in persona_plan["scopes"]:
        scope_key = scope["scope_key"]
        for source in scope["sources"]:
            owner = {
                "materialization_id": (
                    f"{source['source_id']}-materialization-01"
                ),
                "source_id": source["source_id"],
                "render_origin_scope_key": scope_key,
                "current_scope_key": scope_key,
                "file_name": source["file_name"],
            }
            materialization_id = owner["materialization_id"]
            location = _location(owner)
            if materialization_id in materialization_ids:
                raise EventManifestError("W0 materialization id is duplicated")
            if location in locations:
                raise EventManifestError("W0 materialization path is duplicated")
            materialization_ids.add(materialization_id)
            locations.add(location)
            owners.append(owner)
    return owners


def _checkpoints(persona_plan, history_plan, structural_plan):
    w0_files = sum(
        len(scope["sources"]) for scope in persona_plan["scopes"]
    )
    p_sources = history_plan["strata"][history.PURGE_AFTER_W1][
        "source_count"
    ]
    result = {}
    for wave in ("W0", "W1", "W2", "W3", "W4"):
        chunks = history_plan["checkpoints"][wave]
        result[wave] = {
            "current_contract_chunks": chunks["current"],
            "history_only_contract_chunks": chunks["history_only"],
            "live_physical_files": (
                w0_files
                + structural_plan["physical_file_delta_by_checkpoint"][wave]
            ),
        }
    pre = history_plan["checkpoints"]["W5_pre_purge_auto"]
    result["W5_pre_purge_auto"] = {
        "current_contract_chunks": pre["current"],
        "history_only_contract_chunks": pre["history_only"],
        "live_physical_files": (
            w0_files
            + structural_plan["physical_file_delta_by_checkpoint"]["W5"]
            + p_sources
        ),
    }
    final = history_plan["checkpoints"]["W5"]
    result["W5"] = {
        "current_contract_chunks": final["current"],
        "history_only_contract_chunks": final["history_only"],
        "live_physical_files": (
            w0_files
            + structural_plan["physical_file_delta_by_checkpoint"]["W5"]
        ),
    }
    return result


def _present_materializations(event, side):
    return [
        state["materialization"]
        for state in event["state_transition"][side]
        if state["presence"] == "present"
    ]


def _materialization_quota(value):
    requested = value["requested_contributor_chunks"]
    planned = value["planned_contract_chunks"]
    if (
        type(requested) is not int
        or type(planned) is not int
        or requested != planned
        or requested < 0
        or (value["gate_role"] == "contract_contributor")
        != (requested > 0)
    ):
        raise EventManifestError("materialization chunk contract is inconsistent")
    return requested


def _rendered_content(value):
    return {key: value[key] for key in _RENDERED_CONTENT_FIELDS}


def _source_version_leaf(value):
    return {
        "source_id": value["source_id"],
        "source_version": value["source_version"],
        "render_origin_scope_key": value["render_origin_scope_key"],
        "family": value["family"],
        "variant": value["variant"],
        "gate_role": value["gate_role"],
        "expected_disposition": value["expected_disposition"],
        "extension": value["extension"],
        "media_type": value["media_type"],
        "requested_contributor_chunks": value[
            "requested_contributor_chunks"
        ],
        **_rendered_content(value),
    }


def _require_typed_relation(event, expected):
    actual = {
        key: event["relation"][key] for key in _TYPED_RELATION_FIELDS
    }
    expected = {key: expected[key] for key in _TYPED_RELATION_FIELDS}
    if not _same_canonical_json(actual, expected):
        raise EventManifestError(
            f"typed relation differs from event leaves: {event['event_id']}"
        )


def _relation_for_leaves(
    kind,
    before,
    after,
    *,
    replaces_source_ids=(),
    derived_from_source_ids=(),
    alias_of_materialization_ids=(),
    restored_from_materialization_ids=(),
):
    return _relation(
        kind,
        source_ids=sorted({
            value["source_id"] for value in before + after
        }),
        materialization_ids=sorted({
            value["materialization_id"] for value in before + after
        }),
        from_source_versions=sorted({
            value["source_version"] for value in before
        }),
        to_source_versions=sorted({
            value["source_version"] for value in after
        }),
        replaces_source_ids=list(replaces_source_ids),
        derived_from_source_ids=list(derived_from_source_ids),
        alias_of_materialization_ids=list(alias_of_materialization_ids),
        restored_from_materialization_ids=list(
            restored_from_materialization_ids
        ),
    )


def _require_same_source_version(left, right, message):
    if not _same_canonical_json(
        _source_version_leaf(left), _source_version_leaf(right)
    ):
        raise EventManifestError(message)


def _canonical_variant_leaf_contract(family, variant):
    policy = next(
        (
            (gate_role, disposition)
            for name, _ratio, gate_role, disposition
            in spec.FORMAT_VARIANTS[family]
            if name == variant
        ),
        None,
    )
    if policy is None:
        raise EventManifestError(
            f"missing canonical variant contract: {family}/{variant}"
        )
    extension, media_type = renderers.variant_output_contract(
        family, variant
    )
    return {
        "family": family,
        "variant": variant,
        "gate_role": policy[0],
        "expected_disposition": policy[1],
        "extension": extension,
        "media_type": media_type,
        "renderer_id": renderers.RENDERER_ID,
        "renderer_schema_version": renderers.RENDERER_SCHEMA_VERSION,
    }


def _validate_typed_transform(operation, parent, child):
    expected_by_operation = {
        "near_duplicate": {
            "contract_kind": "near-png-one-channel/v1",
            "relation_kind": "near-png-one-channel",
            "child_family": "image",
            "child_variant": "png",
            "logical_member_count": 1,
        },
        "derived_format": {
            "contract_kind": "png-to-scan-pdf/v1",
            "relation_kind": "png-to-scan-pdf",
            "child_family": "pdf_scan",
            "child_variant": "pdf-scan",
            "logical_member_count": 2,
        },
    }
    expected = expected_by_operation[operation]
    parent_contract = _canonical_variant_leaf_contract("image", "png")
    child_contract = _canonical_variant_leaf_contract(
        expected["child_family"], expected["child_variant"]
    )
    if {
        key: parent[key] for key in parent_contract
    } != parent_contract:
        raise EventManifestError(
            "typed transform parent is not canonical image/png"
        )
    if {
        key: child[key] for key in child_contract
    } != child_contract:
        raise EventManifestError(
            "typed transform child format contract differs"
        )
    render_request = child["render_request"]
    if (
        child["render_contract"] != {
            "kind": expected["contract_kind"],
            "parent_source_ids": [parent["source_id"]],
        }
        or type(child["transform_witness"]) is not dict
        or child["transform_witness"].get("kind")
        != expected["contract_kind"]
        or child["logical_member_count"]
        != expected["logical_member_count"]
        or child["raw_sha256"] == parent["raw_sha256"]
        or {
            "source_id": render_request["source_id"],
            "version": render_request["version"],
            "scope_key": render_request["scope_key"],
            "family": render_request["family"],
            "variant": render_request["variant"],
            "requested_contributor_chunks": render_request[
                "requested_contributor_chunks"
            ],
        } != {
            "source_id": child["source_id"],
            "version": child["source_version"],
            "scope_key": child["render_origin_scope_key"],
            "family": child["family"],
            "variant": child["variant"],
            "requested_contributor_chunks": child[
                "requested_contributor_chunks"
            ],
        }
    ):
        raise EventManifestError(
            "structural operation differs from typed transform contract"
        )
    return expected["relation_kind"]


def _validate_structural_leaf(event, before, after):
    operation = event["operation"]
    raw_only_operations = {
        "cross_scope_move",
        "create",
        "near_duplicate",
        "derived_format",
        "archive_move",
        "delete_for_restore",
        "restore_to_active_scope",
    }
    contributor_safe_operations = {"same_scope_rename", "exact_duplicate"}
    if operation not in raw_only_operations | contributor_safe_operations:
        raise EventManifestError(
            f"unknown structural event operation: {operation}"
        )
    expected_raw_only = operation in raw_only_operations
    if (
        type(event["requires_raw_only"]) is not bool
        or event["requires_raw_only"] is not expected_raw_only
    ):
        raise EventManifestError(
            "structural requires_raw_only differs from typed operation"
        )
    if event["history_purge_versions"]:
        raise EventManifestError("structural event carries history purge leaves")
    if expected_raw_only and any(
        value["gate_role"] != "raw_only"
        or _materialization_quota(value) != 0
        for value in before + after
    ):
        raise EventManifestError(
            "requires_raw_only structural leaves must be raw-only with quota zero"
        )

    command = event["source_command"]
    expected_command_kind = (
        "kio_restore_path"
        if operation == "restore_to_active_scope"
        else f"filesystem_{operation}"
    )
    if command["kind"] != expected_command_kind:
        raise EventManifestError("structural source command kind differs")

    if operation == "same_scope_rename":
        if (
            len(before) != 1
            or len(after) != 1
            or before[0]["materialization_id"]
            != after[0]["materialization_id"]
            or before[0]["current_scope_key"]
            != after[0]["current_scope_key"]
            or before[0]["file_name"].casefold()
            == after[0]["file_name"].casefold()
            or event["index_scope_keys"]
            != [before[0]["current_scope_key"]]
        ):
            raise EventManifestError("same-scope rename topology differs")
        _require_same_source_version(
            before[0], after[0], "same-scope rename content differs"
        )
        expected_relation = _relation_for_leaves(
            "same-materialization", before, after
        )
    elif operation in ("cross_scope_move", "archive_move"):
        if (
            len(before) != 1
            or len(after) != 1
            or before[0]["materialization_id"]
            != after[0]["materialization_id"]
            or before[0]["current_scope_key"]
            == after[0]["current_scope_key"]
            or event["index_scope_keys"] != sorted({
                before[0]["current_scope_key"],
                after[0]["current_scope_key"],
            })
        ):
            raise EventManifestError("cross-scope move topology differs")
        _require_same_source_version(
            before[0], after[0], "cross-scope move content differs"
        )
        expected_relation = _relation_for_leaves(
            "same-materialization", before, after
        )
    elif operation == "create":
        if before or len(after) != 1 or event["index_scope_keys"] != [
            after[0]["current_scope_key"]
        ]:
            raise EventManifestError("structural create topology differs")
        expected_relation = _relation_for_leaves(
            "new-source", before, after
        )
    elif operation == "exact_duplicate":
        if len(before) != 1 or len(after) != 2:
            raise EventManifestError("exact duplicate topology differs")
        parent = before[0]
        unchanged = [
            value for value in after
            if value["materialization_id"] == parent["materialization_id"]
        ]
        aliases = [
            value for value in after
            if value["materialization_id"] != parent["materialization_id"]
        ]
        if (
            len(unchanged) != 1
            or len(aliases) != 1
            or aliases[0]["materialization_id"]
            == parent["materialization_id"]
            or len({_location(value) for value in after}) != 2
            or any(
                value["current_scope_key"] != parent["current_scope_key"]
                for value in after
            )
            or event["index_scope_keys"]
            != [parent["current_scope_key"]]
        ):
            raise EventManifestError("exact duplicate alias topology differs")
        _require_same_source_version(
            parent, unchanged[0], "exact duplicate parent content differs"
        )
        _require_same_source_version(
            parent, aliases[0], "exact duplicate alias content differs"
        )
        expected_relation = _relation_for_leaves(
            "exact-alias",
            before,
            after,
            alias_of_materialization_ids=[parent["materialization_id"]],
        )
    elif operation in ("near_duplicate", "derived_format"):
        if len(before) != 1 or len(after) != 2:
            raise EventManifestError("derived structural topology differs")
        parent = before[0]
        unchanged = [
            value for value in after
            if value["materialization_id"] == parent["materialization_id"]
        ]
        children = [
            value for value in after
            if value["materialization_id"] != parent["materialization_id"]
        ]
        if (
            len(unchanged) != 1
            or len(children) != 1
            or children[0]["source_id"] == parent["source_id"]
            or len({_location(value) for value in after}) != 2
            or any(
                value["current_scope_key"] != parent["current_scope_key"]
                for value in after
            )
            or event["index_scope_keys"]
            != [parent["current_scope_key"]]
        ):
            raise EventManifestError("derived structural topology differs")
        _require_same_source_version(
            parent, unchanged[0], "derived parent content differs"
        )
        relation_kind = _validate_typed_transform(
            operation, parent, children[0]
        )
        expected_relation = _relation_for_leaves(
            relation_kind,
            before,
            after,
            derived_from_source_ids=[parent["source_id"]],
        )
    elif operation == "delete_for_restore":
        if len(before) != 1 or after or event["index_scope_keys"] != [
            before[0]["current_scope_key"]
        ]:
            raise EventManifestError("delete-for-restore topology differs")
        expected_relation = _relation_for_leaves(
            "delete-preserve-history", before, after
        )
    else:
        if before or len(after) != 1 or event["index_scope_keys"] != [
            after[0]["current_scope_key"]
        ]:
            raise EventManifestError("restore topology differs")
        locator = event["restore_locator"]
        restored_ids = event["relation"][
            "restored_from_materialization_ids"
        ]
        if (
            len(restored_ids) != 1
            or after[0]["materialization_id"] == restored_ids[0]
            or command != {
                "kind": "kio_restore_path",
                "scope_key": locator["source_scope_key"],
                "commit_boundary_kind": "none",
                "force": False,
            }
            or locator["kind"] != "path-at-checkpoint"
            or locator["source_materialization_id"] != restored_ids[0]
            or locator["source_version"] != after[0]["source_version"]
            or locator["destination_scope_key"]
            != after[0]["current_scope_key"]
            or locator["expected_raw_sha256"] != after[0]["raw_sha256"]
            or locator["expected_raw_bytes"] != after[0]["raw_bytes"]
            or locator["checkpoint"] != "W4"
            or locator["expected_purged"] is not False
            or locator["command_boundary_kind"] != "none"
        ):
            raise EventManifestError("restore relation/locator topology differs")
        expected_relation = _relation_for_leaves(
            "restore-deleted-source",
            before,
            after,
            restored_from_materialization_ids=restored_ids,
        )
    _require_typed_relation(event, expected_relation)
    return {"current": 0, "history_only": 0}


def _validate_history_leaf(event, before, after):
    if event["requires_raw_only"] is not None:
        raise EventManifestError("history event requires_raw_only must be null")
    operation = event["operation"]
    if operation.startswith("edit_v") or operation.startswith("correct_n_"):
        if len(before) != 1 or len(after) != 1:
            raise EventManifestError("history edit must have one before and after")
        old, new = before[0], after[0]
        quota = _materialization_quota(old)
        if (
            _materialization_quota(new) != quota
            or old["source_id"] != new["source_id"]
            or old["materialization_id"] != new["materialization_id"]
            or new["source_version"] != old["source_version"] + 1
            or old["current_scope_key"] != new["current_scope_key"]
            or old["file_name"] != new["file_name"]
            or old["raw_sha256"] == new["raw_sha256"]
            or event["source_command"] != {
                "kind": "filesystem_replace_exact_path",
                "scope_key": old["current_scope_key"],
            }
        ):
            raise EventManifestError("history edit source/version contract differs")
        _require_typed_relation(
            event,
            _relation_for_leaves(
                "same-source-version-advance", before, after
            ),
        )
        return {"current": 0, "history_only": quota}
    if operation == "replace_x_one_for_one":
        if len(before) != 1 or len(after) != 1:
            raise EventManifestError("X replacement must be one-for-one")
        old, new = before[0], after[0]
        quota = _materialization_quota(old)
        if (
            _materialization_quota(new) != quota
            or old["source_id"] == new["source_id"]
            or old["raw_sha256"] == new["raw_sha256"]
            or old["current_scope_key"] != new["current_scope_key"]
            or event["source_command"] != {
                "kind": "filesystem_unlink_and_create_replacement",
                "scope_key": new["current_scope_key"],
            }
        ):
            raise EventManifestError("X replacement does not preserve quota/scope")
        _require_typed_relation(
            event,
            _relation(
                "one-for-one-replacement",
                source_ids=[new["source_id"]],
                materialization_ids=[new["materialization_id"]],
                from_source_versions=[old["source_version"]],
                to_source_versions=[new["source_version"]],
                replaces_source_ids=[old["source_id"]],
            ),
        )
        return {"current": 0, "history_only": quota}
    if operation == "create_p_replacement":
        if before or len(after) != 1:
            raise EventManifestError("P replacement must create exactly one path")
        new = after[0]
        replaced = event["relation"]["replaces_source_ids"]
        if (
            len(replaced) != 1
            or replaced[0] == new["source_id"]
            or event["source_command"] != {
                "kind": "filesystem_create_no_replace",
                "scope_key": new["current_scope_key"],
            }
        ):
            raise EventManifestError("P replacement relation differs")
        _require_typed_relation(
            event,
            _relation(
                "one-for-one-replacement",
                source_ids=[new["source_id"]],
                materialization_ids=[new["materialization_id"]],
                replaces_source_ids=replaced,
                to_source_versions=[new["source_version"]],
            ),
        )
        return {
            "current": _materialization_quota(new),
            "history_only": 0,
        }
    if operation == "unlink_then_path_purge":
        if len(before) != 1 or after:
            raise EventManifestError("path purge must unlink exactly one current path")
        old = before[0]
        quota = _materialization_quota(old)
        versions = event["history_purge_versions"]
        if (
            [value["source_version"] for value in versions] != [0, 1]
            or any(value["source_id"] != old["source_id"] for value in versions)
            or any(
                type(value["planned_contract_chunks"]) is not int
                or value["planned_contract_chunks"] != quota
                for value in versions
            )
            or event["source_command"] != {
                "kind": "filesystem_unlink_exact_path",
                "scope_key": old["current_scope_key"],
            }
        ):
            raise EventManifestError("path purge version chunk contract differs")
        _require_typed_relation(
            event,
            _relation(
                "path-purge-all-source-versions",
                source_ids=[old["source_id"]],
                materialization_ids=[old["materialization_id"]],
                from_source_versions=[0, 1],
            ),
        )
        purged_history = sum(
            value["planned_contract_chunks"] for value in versions
        ) - quota
        return {"current": -quota, "history_only": -purged_history}
    raise EventManifestError(f"unknown history event operation: {operation}")


def _leaf_event_delta(event):
    before = _present_materializations(event, "before")
    after = _present_materializations(event, "after")
    for value in before + after:
        _materialization_quota(value)
    if event["lane"] == "structural":
        return _validate_structural_leaf(event, before, after)
    if event["lane"] == "history":
        return _validate_history_leaf(event, before, after)
    raise EventManifestError(f"unknown event lane: {event['lane']!r}")


def _validate_live_materialization_ids(events, w0_owners):
    live_by_path = {}
    live_path_by_id = {}
    for owner in w0_owners:
        location = _location(owner)
        materialization_id = owner["materialization_id"]
        if location in live_by_path or materialization_id in live_path_by_id:
            raise EventManifestError("full W0 live owner inventory is not unique")
        live_by_path[location] = (
            materialization_id, owner["source_id"]
        )
        live_path_by_id[materialization_id] = location

    for event in events:
        for state in event["state_transition"]["before"]:
            value = state["materialization"]
            location = _location(value)
            expected_owner = (
                value["materialization_id"], value["source_id"]
            )
            if state["presence"] == "present":
                if live_by_path.get(location) != expected_owner:
                    raise EventManifestError(
                        "live materialization before owner/path differs"
                    )
            elif state["presence"] == "absent":
                if location in live_by_path:
                    raise EventManifestError(
                        "live materialization before path is not absent"
                    )
            else:
                raise EventManifestError("state presence tag is invalid")

        for state in event["state_transition"]["before"]:
            if state["presence"] != "present":
                continue
            value = state["materialization"]
            location = _location(value)
            materialization_id = value["materialization_id"]
            del live_by_path[location]
            del live_path_by_id[materialization_id]

        for state in event["state_transition"]["after"]:
            if state["presence"] != "present":
                continue
            value = state["materialization"]
            location = _location(value)
            materialization_id = value["materialization_id"]
            if location in live_by_path:
                raise EventManifestError(
                    "event creates an already-live materialization path"
                )
            if materialization_id in live_path_by_id:
                raise EventManifestError(
                    "live materialization id is assigned to multiple paths"
                )
            live_by_path[location] = (
                materialization_id, value["source_id"]
            )
            live_path_by_id[materialization_id] = location


def _validate_cross_event_relations(events):
    event_by_id = {event["event_id"]: event for event in events}
    purge_by_source = {}
    for event in events:
        if event["operation"] == "unlink_then_path_purge":
            source_id = _present_materializations(event, "before")[0][
                "source_id"
            ]
            if source_id in purge_by_source:
                raise EventManifestError("source has more than one purge event")
            purge_by_source[source_id] = event

    paired_create_ids = set()
    for source_id, purge_event in purge_by_source.items():
        create_events = [
            event_by_id[event_id]
            for event_id in purge_event["relation"]["prior_event_ids"]
            if event_id in event_by_id
            and event_by_id[event_id]["operation"] == "create_p_replacement"
        ]
        if len(create_events) != 1:
            raise EventManifestError(
                "purge must depend on exactly one P replacement create"
            )
        create_event = create_events[0]
        paired_create_ids.add(create_event["event_id"])
        new = _present_materializations(create_event, "after")[0]
        if (
            create_event["relation"]["replaces_source_ids"] != [source_id]
            or new["raw_sha256"] in {
                value["raw_sha256"]
                for value in purge_event["history_purge_versions"]
            }
        ):
            raise EventManifestError(
                "P replacement is not raw-distinct and bound to its purge"
            )
    if paired_create_ids != {
        event["event_id"]
        for event in events
        if event["operation"] == "create_p_replacement"
    }:
        raise EventManifestError("P replacement create lacks its purge event")

    for event in events:
        if event["operation"] != "restore_to_active_scope":
            continue
        prior_ids = event["relation"]["prior_event_ids"]
        delete_events = [
            event_by_id[event_id]
            for event_id in prior_ids
            if event_id in event_by_id
            and event_by_id[event_id]["operation"] == "delete_for_restore"
        ]
        if len(delete_events) != 1:
            raise EventManifestError(
                "restore must depend on exactly one delete-for-restore"
            )
        deleted = _present_materializations(delete_events[0], "before")[0]
        restored = _present_materializations(event, "after")[0]
        locator = event["restore_locator"]
        if (
            event["relation"]["restored_from_materialization_ids"]
            != [deleted["materialization_id"]]
            or locator["source_materialization_id"]
            != deleted["materialization_id"]
            or locator["source_scope_key"]
            != deleted["current_scope_key"]
            or locator["source_file_name"] != deleted["file_name"]
            or locator["source_version"] != deleted["source_version"]
            or locator["expected_raw_sha256"] != deleted["raw_sha256"]
            or locator["expected_raw_bytes"] != deleted["raw_bytes"]
        ):
            raise EventManifestError(
                "restore relation/locator differs from deleted leaf"
            )
        _require_same_source_version(
            deleted, restored, "restored leaf differs from deleted source/version"
        )


def _validate_event_semantics(events, w0_owners=()):
    materialization_sources = {
        owner["materialization_id"]: (
            owner["source_id"], owner["render_origin_scope_key"]
        )
        for owner in w0_owners
    }
    if len(materialization_sources) != len(w0_owners):
        raise EventManifestError("full W0 materialization owners repeat an id")
    source_version_content = {}
    for event in events:
        for side in ("before", "after"):
            for state in event["state_transition"][side]:
                value = state["materialization"]
                _materialization_quota(value)
                materialization_id = value["materialization_id"]
                identity = (
                    value["source_id"], value["render_origin_scope_key"]
                )
                existing = materialization_sources.setdefault(
                    materialization_id, identity
                )
                if existing != identity:
                    raise EventManifestError(
                        "materialization id crosses source lineage"
                    )
                source_version = (value["source_id"], value["source_version"])
                content = _source_version_leaf(value)
                existing_content = source_version_content.setdefault(
                    source_version, content
                )
                if not _same_canonical_json(existing_content, content):
                    raise EventManifestError(
                        "source/version content differs across materializations"
                    )

        transformed = [
            value
            for value in _present_materializations(event, "after")
            if value["transform_witness"] is not None
        ]
        derived_ids = event["relation"]["derived_from_source_ids"]
        if transformed or derived_ids:
            if len(transformed) != 1:
                raise EventManifestError(
                    "derived event must create one transformed materialization"
                )
            child = transformed[0]
            contract_parent_ids = child["render_contract"]["parent_source_ids"]
            if contract_parent_ids != derived_ids:
                raise EventManifestError(
                    "derived relation differs from render contract parents"
                )
            parent_by_id = {
                value["source_id"]: value
                for value in (
                    _present_materializations(event, "before")
                    + _present_materializations(event, "after")
                )
                if value["source_id"] in derived_ids
            }
            if set(parent_by_id) != set(derived_ids):
                raise EventManifestError("derived event lacks its parent state")
            witness = child["transform_witness"]
            if (
                len(derived_ids) != 1
                or witness["parent_raw_sha256"]
                != parent_by_id[derived_ids[0]]["raw_sha256"]
                or witness["child_raw_sha256"] != child["raw_sha256"]
                or witness["kind"] != child["render_contract"]["kind"]
            ):
                raise EventManifestError("transform witness is not parent-bound")

        _leaf_event_delta(event)

    for event in events:
        if event["operation"] != "unlink_then_path_purge":
            if event["history_purge_versions"]:
                raise EventManifestError(
                    "non-purge event carries history purge versions"
                )
            continue
        for version in event["history_purge_versions"]:
            key = (version["source_id"], version["source_version"])
            known = source_version_content.get(key)
            if known is None:
                raise EventManifestError(
                    "history purge version has no known source/version leaf"
                )
            expected = {
                "source_id": key[0],
                "source_version": key[1],
                "raw_sha256": known["raw_sha256"],
                "raw_bytes": known["raw_bytes"],
                "render_request_sha256": known[
                    "render_request_sha256"
                ],
                "planned_contract_chunks": known[
                    "planned_contract_chunks"
                ],
                "rendered_content_sha256": _digest({
                    field: known[field]
                    for field in _RENDERED_CONTENT_FIELDS
                }),
            }
            if not _same_canonical_json(version, expected):
                raise EventManifestError(
                    "history purge content differs from source/version leaf"
                )

    _validate_cross_event_relations(events)
    if w0_owners:
        _validate_live_materialization_ids(events, w0_owners)


def _event_delta(events):
    current = 0
    history_only = 0
    physical_files = 0
    for event in events:
        delta = _leaf_event_delta(event)
        if delta != event["expected_contract_chunk_delta"]:
            raise EventManifestError(
                f"declared event delta differs from leaf state: {event['event_id']}"
            )
        current += delta["current"]
        history_only += delta["history_only"]
        physical_files += sum(
            state["presence"] == "present"
            for state in event["state_transition"]["after"]
        ) - sum(
            state["presence"] == "present"
            for state in event["state_transition"]["before"]
        )
    return {
        "current_contract_chunks": current,
        "history_only_contract_chunks": history_only,
        "live_physical_files": physical_files,
    }


def _validate_event_arithmetic(
    checkpoints, regular_by_wave, purge_events
):
    phases = {}
    current = dict(checkpoints["W0"])
    for wave in ("W1", "W2", "W3", "W4"):
        delta = _event_delta(regular_by_wave[wave])
        phases[wave] = delta
        current = {
            key: current[key] + delta[key]
            for key in current
        }
        if current != checkpoints[wave]:
            raise EventManifestError(
                f"leaf event arithmetic differs at {wave}"
            )
    w5_regular = _event_delta(regular_by_wave["W5"])
    phases["W5_pre_purge_auto"] = w5_regular
    current = {
        key: current[key] + w5_regular[key]
        for key in current
    }
    if current != checkpoints["W5_pre_purge_auto"]:
        raise EventManifestError(
            "leaf event arithmetic differs at W5 pre-purge"
        )
    w5_purge = _event_delta(purge_events)
    phases["W5_purge"] = w5_purge
    current = {
        key: current[key] + w5_purge[key]
        for key in current
    }
    if current != checkpoints["W5"]:
        raise EventManifestError("leaf event arithmetic differs at W5")
    return phases


def _validate_event_graph(events, boundaries, schedule):
    event_by_id = {event["event_id"]: event for event in events}
    boundary_by_id = {
        boundary["boundary_id"]: boundary for boundary in boundaries
    }
    if len(event_by_id) != len(events):
        raise EventManifestError("event ids are not unique")
    if len(boundary_by_id) != len(boundaries):
        raise EventManifestError("boundary ids are not unique")
    if set(event_by_id) & set(boundary_by_id):
        raise EventManifestError("event and boundary ids overlap")
    all_ids = set(event_by_id) | set(boundary_by_id)
    scheduled_ids = [item["item_id"] for item in schedule]
    if len(scheduled_ids) != len(set(scheduled_ids)) or set(scheduled_ids) != all_ids:
        raise EventManifestError("schedule is not a total one-to-one inventory")
    for ordinal, item in enumerate(schedule, start=1):
        if (
            item["schedule_ordinal"] != ordinal
            or item["logical_tick"] != ordinal
            or item["logical_time"] != f"T{ordinal:08d}"
            or item["prior_item_id"]
            != (schedule[ordinal - 2]["item_id"] if ordinal > 1 else None)
        ):
            raise EventManifestError("schedule logical order is not contiguous")
        expected_kind = "event" if item["item_id"] in event_by_id else "boundary"
        if item["item_kind"] != expected_kind:
            raise EventManifestError("schedule item kind differs from its inventory")
        value = (
            event_by_id[item["item_id"]]
            if expected_kind == "event"
            else boundary_by_id[item["item_id"]]
        )
        if value["wave"] != item["wave"]:
            raise EventManifestError("schedule wave differs from its inventory")

    for event in events:
        referenced = []
        for reference in event["boundary_refs"]:
            boundary_id = reference["boundary_id"]
            if reference["kind"] == "none":
                if boundary_id is not None:
                    raise EventManifestError("none boundary has an id")
                continue
            boundary = boundary_by_id.get(boundary_id)
            if boundary is None:
                raise EventManifestError("event references an unknown boundary")
            if (
                boundary["kind"] != reference["kind"]
                or boundary["scope_key"] != reference["scope_key"]
                or event["event_id"] not in boundary["covered_event_ids"]
            ):
                raise EventManifestError("event boundary reference is inconsistent")
            referenced.append(boundary_id)
        if len(referenced) != len(set(referenced)):
            raise EventManifestError("event repeats a boundary reference")
        prior_ids = event["relation"]["prior_event_ids"]
        if len(prior_ids) != len(set(prior_ids)):
            raise EventManifestError("event dependency is duplicated")
        for prior_id in prior_ids:
            prior = event_by_id.get(prior_id)
            if prior is None or prior["logical_tick"] >= event["logical_tick"]:
                raise EventManifestError("event dependency is unknown or not prior")

    for boundary in boundaries:
        covered = boundary["covered_event_ids"]
        if not covered or len(covered) != len(set(covered)):
            raise EventManifestError("boundary coverage is empty or duplicated")
        if boundary["kind"] == "purged_commit":
            if len(covered) != 1:
                raise EventManifestError(
                    "purged boundary must cover exactly one purge event"
                )
            purge_event = event_by_id.get(covered[0])
            purge_before = (
                _present_materializations(purge_event, "before")
                if purge_event is not None else []
            )
            if (
                purge_event is None
                or purge_event["operation"] != "unlink_then_path_purge"
                or len(purge_before) != 1
                or boundary["source_id"]
                != purge_before[0]["source_id"]
                or boundary["source_id"]
                != purge_event["relation"]["source_ids"][0]
                or boundary["scope_key"]
                != purge_before[0]["current_scope_key"]
            ):
                raise EventManifestError(
                    "purged boundary source differs from purge event leaf"
                )
        elif boundary["source_id"] is not None:
            raise EventManifestError(
                "non-purged boundary unexpectedly names a source"
            )
        for event_id in covered:
            event = event_by_id.get(event_id)
            if event is None or event["logical_tick"] >= boundary["logical_tick"]:
                raise EventManifestError("boundary covers an unknown or later event")
            if not any(
                reference["boundary_id"] == boundary["boundary_id"]
                for reference in event["boundary_refs"]
            ):
                raise EventManifestError("boundary lacks a reciprocal event reference")


def _lifecycle_totals(persona_plan, events):
    source_ids = set()
    source_versions = set()
    materialization_ids = set()
    for scope in persona_plan["scopes"]:
        for source in scope["sources"]:
            source_id = source["source_id"]
            source_ids.add(source_id)
            source_versions.add((source_id, source["version"]))
            materialization_ids.add(f"{source_id}-materialization-01")
    for event in events:
        for side in ("before", "after"):
            for state in event["state_transition"][side]:
                value = state["materialization"]
                source_ids.add(value["source_id"])
                source_versions.add(
                    (value["source_id"], value["source_version"])
                )
                materialization_ids.add(value["materialization_id"])
        for value in event["history_purge_versions"]:
            source_ids.add(value["source_id"])
            source_versions.add(
                (value["source_id"], value["source_version"])
            )
    return {
        "lifecycle_source_ids": len(source_ids),
        "source_version_rows": len(source_versions),
        "distinct_materialization_ids": len(materialization_ids),
    }


def _build_event_manifest(persona_plan, profile):
    if profile not in ("tiny", "pilot", "full"):
        raise EventManifestError(f"unknown persona profile: {profile!r}")
    try:
        history_plan = history.build_history_allocation(persona_plan, profile)
        structural_plan = structural.build_structural_allocation(
            persona_plan, profile
        )
    except (
        history.HistoryAllocationError,
        structural.StructuralAllocationError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise EventManifestError(str(error)) from error

    persona_id = history_plan["persona_id"]
    scopes, sources = _flatten_persona(persona_plan)
    for wave in ("W4", "W5"):
        for value in history_plan["waves"][wave]["replacement_sources"]:
            source = _replacement_source(value)
            if source["source_id"] in sources:
                raise EventManifestError("replacement source id collides")
            sources[source["source_id"]] = source
    structural_sources = (
        structural_plan["anchors"]["rename_u_sources"]
        + [
            structural_plan["anchors"]["raw_traveler"],
            structural_plan["anchors"]["near_png_parent"],
            structural_plan["anchors"]["derive_png_parent"],
        ]
        + structural_plan["new_sources"]
    )
    for value in structural_sources:
        normalized = _source_projection(value)
        normalized["scope_key"] = normalized["render_origin_scope_key"]
        existing = sources.get(normalized["source_id"])
        if existing is not None:
            merged = dict(existing)
            merged.update(normalized)
            sources[normalized["source_id"]] = merged
        else:
            sources[normalized["source_id"]] = normalized

    resolver = _ContentResolver(persona_id, scopes, sources)
    history_by_wave, purge_events = _history_events(
        history_plan, sources, resolver
    )
    structural_by_wave = _structural_events(structural_plan, resolver)
    regular_by_wave = {
        wave: history_by_wave[wave] + structural_by_wave[wave]
        for wave in WAVE_ORDER
    }
    boundaries, auto_by_wave_scope, purged_by_event, noop_by_scope = (
        _build_boundaries(persona_id, regular_by_wave, purge_events)
    )
    _bind_event_boundaries(
        regular_by_wave,
        purge_events,
        auto_by_wave_scope,
        purged_by_event,
        noop_by_scope,
    )
    schedule = _build_schedule(
        regular_by_wave, purge_events, auto_by_wave_scope,
        purged_by_event, noop_by_scope
    )
    events = [
        event for wave in WAVE_ORDER for event in regular_by_wave[wave]
    ] + purge_events
    _attach_logical_order(events, boundaries, schedule)
    w0_owners = _w0_materialization_owners(persona_plan)
    _validate_event_semantics(events, w0_owners)
    _validate_event_graph(events, boundaries, schedule)
    initial = _initial_materializations(
        history_plan, structural_plan, sources, resolver
    )
    managed_state = _apply_managed_state(events, initial)
    for boundary in boundaries:
        boundary["boundary_sha256"] = _digest(boundary)
    by_id = {
        event["event_id"]: event["event_sha256"] for event in events
    }
    by_id.update({
        boundary["boundary_id"]: boundary["boundary_sha256"]
        for boundary in boundaries
    })
    for item in schedule:
        item["planned_item_sha256"] = by_id[item["item_id"]]

    checkpoints = _checkpoints(persona_plan, history_plan, structural_plan)
    event_arithmetic = _validate_event_arithmetic(
        checkpoints, regular_by_wave, purge_events
    )
    lifecycle_totals = _lifecycle_totals(persona_plan, events)
    auto_pairs = [
        [boundary["wave"], boundary["scope_key"]]
        for boundary in boundaries if boundary["kind"] == "index_auto"
    ]
    if len(auto_pairs) != len({tuple(value) for value in auto_pairs}):
        raise EventManifestError("ordinary index boundary is duplicated")
    return {
        "schema": EVENT_MANIFEST_SCHEMA,
        "schema_version": EVENT_MANIFEST_SCHEMA_VERSION,
        "fixture_id": spec.FIXTURE_ID,
        "profile": profile,
        "persona_id": persona_id,
        "status": PLANNING_STATUS,
        "contracts": {
            "root_independent": True,
            "planned_not_observed": True,
            "contains_absolute_paths": False,
            "contains_observed_commit_hashes": False,
            "ordinary_index_auto_exactly_once_per_wave_scope": True,
            "w5_purge_is_one_source_one_commit": True,
            "restore_source_command_boundary_is_none": True,
            "schedule_is_single_execution_dependency_chain": True,
            "live_materialization_ids_seeded_from_full_w0": True,
            "history_purge_content_is_source_version_bound": True,
            "logical_time_schema": LOGICAL_TIME_SCHEMA,
        },
        "inputs": {
            "persona_plan_sha256": _digest(persona_plan),
            "history_allocation_sha256": _digest(history_plan),
            "structural_allocation_sha256": _digest(structural_plan),
        },
        "events": events,
        "boundaries": boundaries,
        "schedule": schedule,
        "managed_event_state": managed_state,
        "checkpoints": checkpoints,
        "event_arithmetic": event_arithmetic,
        "totals": {
            "events": len(events),
            "history_events": sum(
                event["lane"] == "history" for event in events
            ),
            "structural_events": sum(
                event["lane"] == "structural" for event in events
            ),
            "boundaries": len(boundaries),
            "index_auto_boundaries": sum(
                boundary["kind"] == "index_auto"
                for boundary in boundaries
            ),
            "purged_commit_boundaries": len(purge_events),
            "index_noop_boundaries": len(noop_by_scope),
            "schedule_items": len(schedule),
            **lifecycle_totals,
        },
    }


def build_event_manifest(persona_plan, profile):
    """Return one canonical per-person, root-independent planned manifest."""
    return _build_event_manifest(persona_plan, profile)


def validate_event_manifest(event_manifest, persona_plan, profile):
    """Reject any value other than the exact canonical event expansion."""
    if type(event_manifest) is not dict:
        raise EventManifestError("event manifest must be an object")
    expected = _build_event_manifest(persona_plan, profile)
    if not _same_canonical_json(event_manifest, expected):
        raise EventManifestError(
            "event manifest differs from canonical expansion"
        )
    return True


def event_manifest_sha256(event_manifest):
    """Return the domain-stable digest of one canonical planned manifest."""
    if type(event_manifest) is not dict:
        raise EventManifestError("event manifest must be an object")
    return _digest(event_manifest)


# Explicit aliases make the per-person nature discoverable without widening
# the contract to a suite-level in-memory manifest.
build_persona_event_manifest = build_event_manifest
validate_persona_event_manifest = validate_event_manifest
