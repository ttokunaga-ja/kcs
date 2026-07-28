"""Typed, authored fact-graph input leaves for persona-PC fidelity v2.

Each persona owns exactly four project/case graphs.  This leaf contains only
synthetic entities and language-neutral typed facts, including one unordered
W0-current conflict set per graph.  It deliberately has no source-intent
membership, evaluation labels, generated surface text, final identity,
filesystem location, retrieval output, or execution authority.
"""

from __future__ import annotations

import copy
import ipaddress
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph_data as data
    from . import persona_v2_input_bindings as input_bindings
    from . import persona_v2_realism_profile as realism
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph_data as data
    import persona_v2_input_bindings as input_bindings
    import persona_v2_realism_profile as realism


ARTIFACT_SCHEMA = "kio.persona.pc-fact-graph/v2"
ARTIFACT_SCHEMA_VERSION = 2
ARTIFACT_KIND = "persona-pc-v2-fact-graph"
MAX_FACT_GRAPH_BYTES = 1 * 2**20
GRAPH_COUNT_PER_PERSONA = 4
ENTITY_COUNT_PER_GRAPH = 4
BASE_FACT_COUNT_PER_GRAPH = 8
FACT_COUNT_PER_GRAPH = 9
EDGE_COUNT_PER_GRAPH = 1
CONFLICT_SET_COUNT_PER_GRAPH = 1
EXPECTED_REALISM_BYTES = 36_811
EXPECTED_REALISM_SHA256 = (
    "990139d3a544ad57ea77752a6a2de8d4345897e961ca85bd506bd1ee041b3fdb"
)

_SYNTHETIC_ID_RE = re.compile(r"^[a-z][a-z0-9-]*-syn-[0-9]{3}$")
_INVALID_EMAIL_RE = re.compile(
    r"^[a-z0-9][a-z0-9-]*-syn-[0-9]{3}@[a-z][a-z0-9-]*-syn-[0-9]{3}\.invalid$"
)
_GRAPH_KINDS = frozenset(("case", "project"))
_ENTITY_TYPES = frozenset(
    ("project-or-case", "synthetic-contact", "synthetic-endpoint", "synthetic-owner-unit")
)
_VALUE_KINDS = frozenset(value_kind for _, value_kind in data.PREDICATE_ROWS)
_CHECKPOINT_STATES = frozenset(("absent", "current", "history-only"))
_FORBIDDEN_GRAPH_KEYS = frozenset(
    (
        "absolute_path",
        "answer_key",
        "chunk_id",
        "distractor_key",
        "intent_key",
        "materialization_id",
        "query_key",
        "query_text",
        "rank",
        "raw_sha256",
        "relative_path",
        "rendered_text",
        "score",
        "source_id",
    )
)


class PersonaV2FactGraphError(ValueError):
    """Raised when an authored fact-graph leaf differs from the v2 contract."""


def _require_persona_id(persona_id):
    if type(persona_id) is not str or persona_id not in envelope.PERSONA_IDS:
        raise PersonaV2FactGraphError(f"unknown persona: {persona_id!r}")
    return persona_id


def _require_synthetic_id(value, *, label):
    if type(value) is not str or _SYNTHETIC_ID_RE.fullmatch(value) is None:
        raise PersonaV2FactGraphError(
            f"{label} must be a lowercase ASCII *-syn-NNN identifier"
        )
    return value


def _theme_rows():
    rows = data.GRAPH_THEME_ROWS
    if type(rows) is not tuple or len(rows) != len(envelope.PERSONA_IDS):
        raise PersonaV2FactGraphError(
            "fact themes must contain exactly one tuple per persona"
        )
    if tuple(row[0] for row in rows if type(row) is tuple and len(row) == 2) != tuple(
        envelope.PERSONA_IDS
    ):
        raise PersonaV2FactGraphError("fact theme persona order is incomplete or changed")

    project_ids = []
    expected_ordinal = 1
    validated = {}
    for persona_id, themes in rows:
        if type(themes) is not tuple or len(themes) != GRAPH_COUNT_PER_PERSONA:
            raise PersonaV2FactGraphError(
                f"{persona_id} must contain exactly four authored graph themes"
            )
        persona_rows = []
        for theme in themes:
            if type(theme) is not tuple or len(theme) != 2:
                raise PersonaV2FactGraphError("each graph theme must be an exact pair")
            project_or_case_id, graph_kind = theme
            _require_synthetic_id(project_or_case_id, label="project/case ID")
            if graph_kind not in _GRAPH_KINDS or type(graph_kind) is not str:
                raise PersonaV2FactGraphError("graph kind must be project or case")
            expected_suffix = f"-syn-{expected_ordinal:03d}"
            if not project_or_case_id.endswith(expected_suffix):
                raise PersonaV2FactGraphError(
                    "project/case suffixes must be the exact suite-global 001..080 sequence"
                )
            project_ids.append(project_or_case_id)
            persona_rows.append((project_or_case_id, graph_kind, expected_ordinal))
            expected_ordinal += 1
        validated[persona_id] = tuple(persona_rows)
    if len(project_ids) != 80 or len(project_ids) != len(set(project_ids)):
        raise PersonaV2FactGraphError("project/case identifiers must be suite-global unique")
    return validated


def _predicate_catalog():
    rows = data.PREDICATE_ROWS
    if type(rows) is not tuple or len(rows) != 7:
        raise PersonaV2FactGraphError("predicate catalog must contain exactly seven rows")
    result = []
    seen_ids = set()
    seen_kinds = set()
    for ordinal, row in enumerate(rows, start=1):
        if type(row) is not tuple or len(row) != 2:
            raise PersonaV2FactGraphError("each predicate row must be an exact pair")
        predicate_id, value_kind = row
        _require_synthetic_id(predicate_id, label="predicate ID")
        if not predicate_id.endswith(f"-syn-{ordinal:03d}"):
            raise PersonaV2FactGraphError("predicate suffix order drifted")
        if type(value_kind) is not str or value_kind not in _VALUE_KINDS:
            raise PersonaV2FactGraphError("predicate value kind is invalid")
        if predicate_id in seen_ids or value_kind in seen_kinds:
            raise PersonaV2FactGraphError("predicate IDs and value kinds must be unique")
        seen_ids.add(predicate_id)
        seen_kinds.add(value_kind)
        result.append({"predicate_id": predicate_id, "value_kind": value_kind})
    return result


def _logical_time_contract():
    rows = data.CHECKPOINT_ROWS
    if type(rows) is not tuple or len(rows) != 7:
        raise PersonaV2FactGraphError("logical checkpoints must contain exactly seven rows")
    checkpoints = []
    previous = None
    for row in rows:
        if type(row) is not tuple or len(row) != 2:
            raise PersonaV2FactGraphError("each logical checkpoint must be an exact pair")
        checkpoint, day_offset = row
        if type(checkpoint) is not str or not checkpoint:
            raise PersonaV2FactGraphError("checkpoint names must be non-empty strings")
        if type(day_offset) is not int or day_offset < 0:
            raise PersonaV2FactGraphError("checkpoint offsets must be non-negative integers")
        if previous is not None and day_offset <= previous:
            raise PersonaV2FactGraphError("checkpoint offsets must be strictly increasing")
        previous = day_offset
        checkpoints.append(
            {"checkpoint": checkpoint, "day_offset_after_reference": day_offset}
        )
    _require_synthetic_id(data.REFERENCE_INSTANT_ID, label="reference instant ID")
    if data.REFERENCE_INSTANT_UTC != "2026-07-13T00:00:00Z":
        raise PersonaV2FactGraphError("reference instant must remain exact and fixed")
    _require_synthetic_id(data.MEASURE_UNIT_ID, label="measure unit ID")
    return {
        "checkpoints": checkpoints,
        "reference_instant_id": data.REFERENCE_INSTANT_ID,
        "reference_instant_utc": data.REFERENCE_INSTANT_UTC,
        "runtime_clock_read_allowed": False,
        "timezone_database_lookup_allowed": False,
    }


def _visibility(profile):
    checkpoints = [row[0] for row in data.CHECKPOINT_ROWS]
    if profile == "stable-current":
        states = ["current"] * len(checkpoints)
    elif profile == "superseded-after-W1":
        states = ["current"] + ["history-only"] * 6
    elif profile == "introduced-at-W1":
        states = ["absent"] + ["current"] * 6
    else:
        raise PersonaV2FactGraphError(f"unknown fact visibility profile: {profile!r}")
    return [
        {"checkpoint": checkpoint, "state": state}
        for checkpoint, state in zip(checkpoints, states)
    ]


def _fact(fact_id, predicate_id, subject_entity_id, typed_value, visibility_profile):
    _require_synthetic_id(fact_id, label="fact ID")
    _require_synthetic_id(predicate_id, label="predicate ID")
    _require_synthetic_id(subject_entity_id, label="subject entity ID")
    if type(typed_value) is not dict or set(typed_value) == set():
        raise PersonaV2FactGraphError("typed fact values must be non-empty exact objects")
    return {
        "fact_id": fact_id,
        "predicate_id": predicate_id,
        "subject_entity_id": subject_entity_id,
        "typed_value": typed_value,
        "visibility_by_checkpoint": _visibility(visibility_profile),
    }


def _graph(project_or_case_id, graph_kind, graph_ordinal):
    graph_suffix = f"{graph_ordinal:03d}"
    graph_id = f"graph-syn-{graph_suffix}"
    owner_id = f"owner-unit-syn-{graph_suffix}"
    contact_id = f"contact-syn-{graph_suffix}"
    endpoint_id = f"endpoint-syn-{graph_suffix}"
    for label, value in (
        ("graph ID", graph_id),
        ("project/case ID", project_or_case_id),
        ("owner ID", owner_id),
        ("contact ID", contact_id),
        ("endpoint ID", endpoint_id),
    ):
        _require_synthetic_id(value, label=label)

    entities = [
        {"entity_id": project_or_case_id, "entity_type": "project-or-case"},
        {"entity_id": owner_id, "entity_type": "synthetic-owner-unit"},
        {"entity_id": contact_id, "entity_type": "synthetic-contact"},
        {"entity_id": endpoint_id, "entity_type": "synthetic-endpoint"},
    ]
    fact_ids = [
        f"fact-syn-{((graph_ordinal - 1) * BASE_FACT_COUNT_PER_GRAPH + ordinal):03d}"
        for ordinal in range(1, BASE_FACT_COUNT_PER_GRAPH + 1)
    ]
    conflict_fact_id = f"conflict-fact-syn-{graph_suffix}"
    project_slug = project_or_case_id.rsplit("-syn-", 1)[0]
    contact_email = f"contact-syn-{graph_suffix}@{project_slug}-syn-{graph_suffix}.invalid"
    documentation_ip = f"192.0.2.{graph_ordinal}"
    predicates = [row[0] for row in data.PREDICATE_ROWS]
    facts = [
        _fact(
            fact_ids[0],
            predicates[0],
            project_or_case_id,
            {"entity_id": owner_id, "kind": "entity-reference"},
            "stable-current",
        ),
        _fact(
            fact_ids[1],
            predicates[1],
            contact_id,
            {"kind": "email", "value": contact_email},
            "stable-current",
        ),
        _fact(
            fact_ids[2],
            predicates[2],
            endpoint_id,
            {"kind": "documentation-ip", "value": documentation_ip},
            "stable-current",
        ),
        _fact(
            fact_ids[3],
            predicates[3],
            project_or_case_id,
            {"kind": "synthetic-token", "token_id": f"draft-syn-{graph_suffix}"},
            "superseded-after-W1",
        ),
        _fact(
            fact_ids[4],
            predicates[3],
            project_or_case_id,
            {"kind": "synthetic-token", "token_id": f"approved-syn-{graph_suffix}"},
            "introduced-at-W1",
        ),
        _fact(
            fact_ids[5],
            predicates[4],
            project_or_case_id,
            {"kind": "unsigned-integer", "value": (graph_ordinal - 1) % 5 + 1},
            "stable-current",
        ),
        _fact(
            fact_ids[6],
            predicates[5],
            project_or_case_id,
            {
                "kind": "scaled-integer",
                "scale": 2,
                "unit_id": data.MEASURE_UNIT_ID,
                "units": graph_ordinal * 100_000,
            },
            "stable-current",
        ),
        _fact(
            fact_ids[7],
            predicates[6],
            project_or_case_id,
            {
                "direction": "after",
                "kind": "logical-day-offset",
                "magnitude": graph_ordinal,
                "reference_instant_id": data.REFERENCE_INSTANT_ID,
            },
            "stable-current",
        ),
        _fact(
            conflict_fact_id,
            predicates[4],
            project_or_case_id,
            {
                "kind": "unsigned-integer",
                "value": (graph_ordinal - 1) % 5 + 101,
            },
            "stable-current",
        ),
    ]
    edge = {
        "edge_id": f"revision-edge-syn-{graph_suffix}",
        "from_fact_id": fact_ids[3],
        "relation_kind": "superseded-by",
        "to_fact_id": fact_ids[4],
    }
    graph = {
        "conflict_sets": [
            {
                "conflict_set_id": f"conflict-set-syn-{graph_suffix}",
                "member_fact_ids": sorted((fact_ids[5], conflict_fact_id)),
                "required_current_checkpoint": "W0",
            }
        ],
        "entities": entities,
        "fact_edges": [edge],
        "facts": facts,
        "graph_id": graph_id,
        "graph_kind": graph_kind,
        "project_or_case_id": project_or_case_id,
        "revision_chains": [
            {
                "current_fact_id": fact_ids[4],
                "prior_fact_ids": [fact_ids[3]],
                "revision_chain_id": f"revision-syn-{graph_suffix}",
            }
        ],
        "semantic_language_mode": "language-neutral-typed-facts",
    }
    _validate_graph(graph)
    return graph


def _validate_typed_value(value, predicate_kind, *, entity_ids):
    if type(value) is not dict or value.get("kind") != predicate_kind:
        raise PersonaV2FactGraphError("fact typed value does not match its predicate")
    if predicate_kind == "entity-reference":
        if set(value) != {"entity_id", "kind"} or value["entity_id"] not in entity_ids:
            raise PersonaV2FactGraphError("entity-reference fact is invalid")
    elif predicate_kind == "email":
        if set(value) != {"kind", "value"} or _INVALID_EMAIL_RE.fullmatch(
            value["value"] if type(value.get("value")) is str else ""
        ) is None:
            raise PersonaV2FactGraphError("fact email must use a synthetic .invalid address")
    elif predicate_kind == "documentation-ip":
        if set(value) != {"kind", "value"} or type(value.get("value")) is not str:
            raise PersonaV2FactGraphError("documentation IP value is malformed")
        try:
            address = ipaddress.ip_address(value["value"])
        except ValueError:
            raise PersonaV2FactGraphError("documentation IP value is malformed") from None
        if address not in ipaddress.ip_network("192.0.2.0/24"):
            raise PersonaV2FactGraphError("fact IP must belong to an RFC 5737 prefix")
    elif predicate_kind == "synthetic-token":
        if set(value) != {"kind", "token_id"}:
            raise PersonaV2FactGraphError("synthetic token value is malformed")
        _require_synthetic_id(value["token_id"], label="synthetic fact token")
    elif predicate_kind == "unsigned-integer":
        if (
            set(value) != {"kind", "value"}
            or type(value.get("value")) is not int
            or value["value"] < 0
        ):
            raise PersonaV2FactGraphError("unsigned integer fact is malformed")
    elif predicate_kind == "scaled-integer":
        if set(value) != {"kind", "scale", "unit_id", "units"}:
            raise PersonaV2FactGraphError("scaled integer fact is malformed")
        if any(type(value[key]) is not int or value[key] < 0 for key in ("scale", "units")):
            raise PersonaV2FactGraphError("scaled integer fields must be non-negative integers")
        _require_synthetic_id(value["unit_id"], label="scaled integer unit ID")
    elif predicate_kind == "logical-day-offset":
        if set(value) != {"direction", "kind", "magnitude", "reference_instant_id"}:
            raise PersonaV2FactGraphError("logical day offset fact is malformed")
        if value["direction"] not in {"after", "before"}:
            raise PersonaV2FactGraphError("logical day offset direction is invalid")
        if type(value["magnitude"]) is not int or value["magnitude"] < 0:
            raise PersonaV2FactGraphError("logical day offset magnitude is invalid")
        if value["reference_instant_id"] != data.REFERENCE_INSTANT_ID:
            raise PersonaV2FactGraphError("logical day offset reference drifted")
    else:  # pragma: no cover - catalog validation rejects unknown kinds first.
        raise PersonaV2FactGraphError("unknown typed fact value kind")


def _assert_no_prohibited_graph_keys(value):
    if type(value) is list:
        for item in value:
            _assert_no_prohibited_graph_keys(item)
        return
    if type(value) is not dict:
        return
    for key, item in value.items():
        if key in _FORBIDDEN_GRAPH_KEYS:
            raise PersonaV2FactGraphError(f"prohibited fact-graph field: {key}")
        _assert_no_prohibited_graph_keys(item)


def _sha256_paths(value):
    result = set()

    def visit(node, path):
        if type(node) is list:
            for item in node:
                visit(item, path + ("[]",))
            return
        if type(node) is not dict:
            return
        for key, item in node.items():
            child_path = path + (key,)
            if key == "sha256" or key.endswith("_sha256"):
                result.add(child_path)
            visit(item, child_path)

    visit(value, ())
    return frozenset(result)


def _validate_graph(graph):
    _assert_no_prohibited_graph_keys(graph)
    if type(graph) is not dict:
        raise PersonaV2FactGraphError("fact graph must be an exact object")
    if set(graph) != {
        "conflict_sets",
        "entities",
        "fact_edges",
        "facts",
        "graph_id",
        "graph_kind",
        "project_or_case_id",
        "revision_chains",
        "semantic_language_mode",
    }:
        raise PersonaV2FactGraphError("fact graph has an unexpected shape")
    if len(graph.get("entities", [])) != ENTITY_COUNT_PER_GRAPH:
        raise PersonaV2FactGraphError("each graph must contain exactly four entities")
    if len(graph.get("facts", [])) != FACT_COUNT_PER_GRAPH:
        raise PersonaV2FactGraphError("each graph must contain exactly nine facts")
    if len(graph.get("fact_edges", [])) != EDGE_COUNT_PER_GRAPH:
        raise PersonaV2FactGraphError("each graph must contain exactly one fact edge")
    if len(graph.get("conflict_sets", [])) != CONFLICT_SET_COUNT_PER_GRAPH:
        raise PersonaV2FactGraphError(
            "each graph must contain exactly one unordered conflict set"
        )
    if graph.get("graph_kind") not in _GRAPH_KINDS:
        raise PersonaV2FactGraphError("fact graph kind is invalid")
    for key in ("graph_id", "project_or_case_id"):
        _require_synthetic_id(graph.get(key), label=key)

    entity_ids = []
    for entity in graph["entities"]:
        if type(entity) is not dict or set(entity) != {"entity_id", "entity_type"}:
            raise PersonaV2FactGraphError("entity rows have an unexpected shape")
        _require_synthetic_id(entity["entity_id"], label="entity ID")
        if entity["entity_type"] not in _ENTITY_TYPES:
            raise PersonaV2FactGraphError("entity type is invalid")
        entity_ids.append(entity["entity_id"])
    if len(entity_ids) != len(set(entity_ids)):
        raise PersonaV2FactGraphError("entity IDs must be unique within a graph")
    if graph["project_or_case_id"] not in entity_ids:
        raise PersonaV2FactGraphError("project/case ID must be a graph entity")

    predicate_kinds = dict(data.PREDICATE_ROWS)
    fact_ids = []
    referenced_entity_ids = set()
    for fact in graph["facts"]:
        if type(fact) is not dict or set(fact) != {
            "fact_id", "predicate_id", "subject_entity_id", "typed_value",
            "visibility_by_checkpoint",
        }:
            raise PersonaV2FactGraphError("fact rows have an unexpected shape")
        _require_synthetic_id(fact["fact_id"], label="fact ID")
        if fact["predicate_id"] not in predicate_kinds:
            raise PersonaV2FactGraphError("fact references an unknown predicate")
        if fact["subject_entity_id"] not in entity_ids:
            raise PersonaV2FactGraphError("fact references an unknown subject entity")
        referenced_entity_ids.add(fact["subject_entity_id"])
        _validate_typed_value(
            fact["typed_value"],
            predicate_kinds[fact["predicate_id"]],
            entity_ids=set(entity_ids),
        )
        if fact["typed_value"]["kind"] == "entity-reference":
            referenced_entity_ids.add(fact["typed_value"]["entity_id"])
        visibility = fact["visibility_by_checkpoint"]
        if [row.get("checkpoint") for row in visibility] != [
            row[0] for row in data.CHECKPOINT_ROWS
        ]:
            raise PersonaV2FactGraphError("fact checkpoint visibility order drifted")
        if any(
            type(row) is not dict
            or set(row) != {"checkpoint", "state"}
            or row["state"] not in _CHECKPOINT_STATES
            for row in visibility
        ):
            raise PersonaV2FactGraphError("fact checkpoint state is invalid")
        fact_ids.append(fact["fact_id"])
    if len(fact_ids) != len(set(fact_ids)):
        raise PersonaV2FactGraphError("fact IDs must be unique within a graph")
    if referenced_entity_ids != set(entity_ids):
        raise PersonaV2FactGraphError("every graph entity must be referenced by a fact")

    edge_ids = set()
    adjacency = {fact_id: [] for fact_id in fact_ids}
    for edge in graph["fact_edges"]:
        if type(edge) is not dict or set(edge) != {
            "edge_id", "from_fact_id", "relation_kind", "to_fact_id",
        }:
            raise PersonaV2FactGraphError("fact edge has an unexpected shape")
        _require_synthetic_id(edge["edge_id"], label="fact edge ID")
        if edge["edge_id"] in edge_ids:
            raise PersonaV2FactGraphError("fact edge IDs must be unique")
        edge_ids.add(edge["edge_id"])
        if edge["relation_kind"] != "superseded-by":
            raise PersonaV2FactGraphError("fact edge relation is invalid")
        if edge["from_fact_id"] not in adjacency or edge["to_fact_id"] not in adjacency:
            raise PersonaV2FactGraphError("fact edge references an unknown fact")
        if edge["from_fact_id"] == edge["to_fact_id"]:
            raise PersonaV2FactGraphError("fact edge cannot be a self-loop")
        adjacency[edge["from_fact_id"]].append(edge["to_fact_id"])

    visiting = set()
    visited = set()

    def visit(fact_id):
        if fact_id in visiting:
            raise PersonaV2FactGraphError("fact graph must be acyclic")
        if fact_id in visited:
            return
        visiting.add(fact_id)
        for target in adjacency[fact_id]:
            visit(target)
        visiting.remove(fact_id)
        visited.add(fact_id)

    for fact_id in fact_ids:
        visit(fact_id)

    chains = graph.get("revision_chains")
    if type(chains) is not list or len(chains) != 1:
        raise PersonaV2FactGraphError("each graph must contain exactly one revision chain")
    chain = chains[0]
    if type(chain) is not dict or set(chain) != {
        "current_fact_id", "prior_fact_ids", "revision_chain_id",
    }:
        raise PersonaV2FactGraphError("revision chain has an unexpected shape")
    _require_synthetic_id(chain["revision_chain_id"], label="revision chain ID")
    if chain["prior_fact_ids"] != [graph["fact_edges"][0]["from_fact_id"]]:
        raise PersonaV2FactGraphError("revision chain prior membership drifted")
    if chain["current_fact_id"] != graph["fact_edges"][0]["to_fact_id"]:
        raise PersonaV2FactGraphError("revision chain current membership drifted")
    by_fact_id = {fact["fact_id"]: fact for fact in graph["facts"]}
    prior = by_fact_id[chain["prior_fact_ids"][0]]
    current = by_fact_id[chain["current_fact_id"]]
    if (
        prior["predicate_id"] != current["predicate_id"]
        or prior["subject_entity_id"] != current["subject_entity_id"]
        or prior["typed_value"] == current["typed_value"]
    ):
        raise PersonaV2FactGraphError(
            "revision facts must share predicate/subject and change the typed value"
        )
    prior_states = [row["state"] for row in prior["visibility_by_checkpoint"]]
    current_states = [row["state"] for row in current["visibility_by_checkpoint"]]
    if prior_states != ["current"] + ["history-only"] * 6:
        raise PersonaV2FactGraphError("prior revision checkpoint states drifted")
    if current_states != ["absent"] + ["current"] * 6:
        raise PersonaV2FactGraphError("current revision checkpoint states drifted")
    if any(
        old_state == "current" and new_state == "current"
        for old_state, new_state in zip(prior_states, current_states)
    ):
        raise PersonaV2FactGraphError(
            "a revision chain cannot expose both values as current at one checkpoint"
        )

    revision_fact_ids = set(chain["prior_fact_ids"]) | {chain["current_fact_id"]}
    conflict_set_ids = set()
    for conflict_set in graph["conflict_sets"]:
        if type(conflict_set) is not dict or set(conflict_set) != {
            "conflict_set_id", "member_fact_ids", "required_current_checkpoint",
        }:
            raise PersonaV2FactGraphError(
                "conflict set has an unexpected shape"
            )
        _require_synthetic_id(
            conflict_set["conflict_set_id"], label="conflict set ID"
        )
        if conflict_set["conflict_set_id"] in conflict_set_ids:
            raise PersonaV2FactGraphError("conflict set IDs must be unique")
        conflict_set_ids.add(conflict_set["conflict_set_id"])
        members = conflict_set["member_fact_ids"]
        if (
            type(members) is not list
            or len(members) != 2
            or len(set(members)) != 2
            or members != sorted(members)
            or any(member not in by_fact_id for member in members)
        ):
            raise PersonaV2FactGraphError(
                "conflict set must contain two canonical unique fact IDs"
            )
        if revision_fact_ids & set(members):
            raise PersonaV2FactGraphError(
                "unordered conflict facts cannot belong to a revision chain"
            )
        left, right = (by_fact_id[member] for member in members)
        if (
            left["predicate_id"] != right["predicate_id"]
            or left["subject_entity_id"] != right["subject_entity_id"]
            or left["typed_value"] == right["typed_value"]
        ):
            raise PersonaV2FactGraphError(
                "conflict facts must share predicate/subject and disagree in value"
            )
        checkpoint = conflict_set["required_current_checkpoint"]
        if checkpoint != "W0":
            raise PersonaV2FactGraphError(
                "v2 conflict sets must require simultaneous W0 visibility"
            )
        for fact in (left, right):
            states = {
                row["checkpoint"]: row["state"]
                for row in fact["visibility_by_checkpoint"]
            }
            if states.get(checkpoint) != "current":
                raise PersonaV2FactGraphError(
                    "both conflict facts must be current at W0"
                )

        def reachable(source, target):
            pending = list(adjacency[source])
            seen = set()
            while pending:
                candidate = pending.pop()
                if candidate == target:
                    return True
                if candidate not in seen:
                    seen.add(candidate)
                    pending.extend(adjacency[candidate])
            return False

        if reachable(members[0], members[1]) or reachable(members[1], members[0]):
            raise PersonaV2FactGraphError(
                "conflict facts must be unordered by fact edges"
            )


def _validate_identifier_namespaces(predicate_catalog, graphs):
    namespaces = {
        "predicate": {row["predicate_id"] for row in predicate_catalog},
        "graph": {graph["graph_id"] for graph in graphs},
        "entity": {
            entity["entity_id"] for graph in graphs for entity in graph["entities"]
        },
        "fact": {fact["fact_id"] for graph in graphs for fact in graph["facts"]},
        "edge": {
            edge["edge_id"] for graph in graphs for edge in graph["fact_edges"]
        },
        "revision": {
            chain["revision_chain_id"]
            for graph in graphs
            for chain in graph["revision_chains"]
        },
        "conflict_set": {
            conflict_set["conflict_set_id"]
            for graph in graphs
            for conflict_set in graph["conflict_sets"]
        },
    }
    names = tuple(namespaces)
    for left_index, left_name in enumerate(names):
        for right_name in names[left_index + 1:]:
            overlap = namespaces[left_name] & namespaces[right_name]
            if overlap:
                raise PersonaV2FactGraphError(
                    f"{left_name}/{right_name} identifier namespaces overlap: "
                    f"{sorted(overlap)!r}"
                )


def _realism_binding(core_bindings):
    value = realism.build_realism_profile()
    realism.validate_realism_profile(value)
    if value["input_bindings"] != core_bindings:
        raise PersonaV2FactGraphError(
            "realism profile does not bind the exact rebuilt upstream core"
        )
    raw = realism.canonical_json_bytes(value)
    digest = realism.realism_profile_sha256(value)
    if len(raw) != EXPECTED_REALISM_BYTES or digest != EXPECTED_REALISM_SHA256:
        raise PersonaV2FactGraphError("realism profile identity, size, or digest drifted")
    return ({
        "artifact_kind": value["artifact_kind"],
        "artifact_schema": value["artifact_schema"],
        "artifact_schema_version": value["artifact_schema_version"],
        "canonical_bytes": len(raw),
        "fixture_id": value["fixture_id"],
        "fixture_schema_version": value["fixture_schema_version"],
        "name": "realism-profile",
        "sha256": digest,
    }, value)


def _shared_inputs():
    themes = _theme_rows()
    predicate_catalog = _predicate_catalog()
    logical_time = _logical_time_contract()
    core_bindings = input_bindings.build_upstream_bindings()
    realism_binding, realism_value = _realism_binding(core_bindings)
    return {
        "bindings": core_bindings + [realism_binding],
        "logical_time": logical_time,
        "predicate_catalog": predicate_catalog,
        "profiles": {
            row["persona_id"]: row for row in realism_value["personas"]
        },
        "themes": themes,
    }


def _canonical_fact_graph(persona_id, *, shared_inputs=None):
    _require_persona_id(persona_id)
    shared = _shared_inputs() if shared_inputs is None else shared_inputs
    themes = shared["themes"][persona_id]
    predicate_catalog = shared["predicate_catalog"]
    logical_time = shared["logical_time"]
    bindings = shared["bindings"]
    profile = shared["profiles"][persona_id]
    persona = envelope.get_persona(persona_id)
    graphs = [_graph(*theme) for theme in themes]
    _validate_identifier_namespaces(predicate_catalog, graphs)

    graph_ids = [graph["graph_id"] for graph in graphs]
    entity_ids = [
        entity["entity_id"] for graph in graphs for entity in graph["entities"]
    ]
    fact_ids = [fact["fact_id"] for graph in graphs for fact in graph["facts"]]
    edge_ids = [edge["edge_id"] for graph in graphs for edge in graph["fact_edges"]]
    conflict_set_ids = [
        conflict_set["conflict_set_id"]
        for graph in graphs
        for conflict_set in graph["conflict_sets"]
    ]
    for label, values in (
        ("graph", graph_ids),
        ("entity", entity_ids),
        ("fact", fact_ids),
        ("edge", edge_ids),
        ("conflict set", conflict_set_ids),
    ):
        if len(values) != len(set(values)):
            raise PersonaV2FactGraphError(
                f"{label} identifiers must be unique within each persona"
            )

    languages = [row["language"] for row in profile["language_weights_bp"]]
    if not languages or len(languages) != len(set(languages)):
        raise PersonaV2FactGraphError("persona languages must be non-empty and unique")
    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_solver_execution": False,
            "authorizes_source_plan": False,
            "filesystem_writer_available": False,
            "formal_capacity_gate_satisfied": False,
            "history_executor_available": False,
            "kio_execution_available": False,
            "query_instances_rendered": False,
            "query_spec_hashed": False,
            "renderer_available": False,
        },
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_FACT_GRAPH_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "null_float_or_negative_integer_allowed": False,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_scope": (
            "typed-authored-fact-graph-inventory-only-no-membership-no-surface-"
            "no-evaluation-oracle-no-solver-no-g0"
        ),
        "eligible_languages": languages,
        "unordered_w0_current_fact_pair_inventory_complete": True,
        "fact_graph_input_leaf_complete": True,
        "fact_graph_inventory_complete": True,
        "fact_oracle_input_closure_complete": False,
        "fixture_id": envelope.FIXTURE_ID,
        "fixture_schema_version": envelope.FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "graphs": graphs,
        "history_intent_recipe_bound": False,
        "hypothesis_status": "authored-benchmark-stress-design-not-observed-user-records",
        "input_bindings": bindings,
        "isolation_policy": {
            "environment_reads_allowed": False,
            "host_identity_reads_allowed": False,
            "live_sync_allowed": False,
            "network_access_allowed": False,
            "runtime_randomness_allowed": False,
        },
        "logical_time_contract": logical_time,
        "persona_id": persona_id,
        "persona_realism_profile_id": profile["profile_id"],
        "predicate_catalog": predicate_catalog,
        "remaining_blockers": [
            "source-intent-recipe-not-bound",
            "semantic-oracle-not-present",
            "query-intent-not-present",
            "fact-oracle-persona-input-closure-not-present",
            "bounded-framed-loader-not-implemented",
            "joint-source-intent-refinement-not-proved",
        ],
        "role": persona["role"],
        "semantic_surface_text_present": False,
        "source_intent_recipe_bound": False,
        "summary": {
            "conflict_set_count": len(conflict_set_ids),
            "edge_count": len(edge_ids),
            "entity_count": len(entity_ids),
            "fact_count": len(fact_ids),
            "graph_count": len(graph_ids),
            "revision_chain_count": len(graphs),
        },
    }
    _assert_no_prohibited_graph_keys(value["graphs"])
    if _sha256_paths(value) != frozenset({("input_bindings", "[]", "sha256")}):
        raise PersonaV2FactGraphError(
            "fact graph has a missing, unexpected, downstream, or self SHA binding"
        )
    return value


def build_fact_graph(persona_id):
    """Return one detached persona fact-graph leaf with no execution authority."""

    return copy.deepcopy(_canonical_fact_graph(persona_id))


def build_fact_graph_suite():
    """Build all twenty detached leaves while holding shared inputs only once."""

    shared = _shared_inputs()
    return [
        copy.deepcopy(_canonical_fact_graph(persona_id, shared_inputs=shared))
        for persona_id in envelope.PERSONA_IDS
    ]


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 fact graph",
            max_bytes=MAX_FACT_GRAPH_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactGraphError(str(error)) from None


def validate_fact_graph(persona_id, value):
    _require_persona_id(persona_id)
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=lambda: build_fact_graph(persona_id),
            label="persona v2 fact graph",
            max_bytes=MAX_FACT_GRAPH_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactGraphError(str(error)) from None


def fact_graph_sha256(persona_id, value=None):
    _require_persona_id(persona_id)
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=lambda: build_fact_graph(persona_id),
            label="persona v2 fact graph",
            max_bytes=MAX_FACT_GRAPH_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2FactGraphError(str(error)) from None


def require_fact_oracle_input_closure():
    raise PersonaV2FactGraphError(
        "fact graph inventory is complete, but source-intent membership, semantic "
        "oracle, query intent, and the persona input closure remain absent"
    )
