"""Query-independent capacity fact truth/occurrence policy candidate.

The artifact joins the frozen 20-persona fact graphs to the exact frozen source-
semantic capacity-axis catalog.  It owns 720 persona-sharded policy rows
(36 per persona) and proves the resulting 15,048 capacity cells and 105,336
checkpoint projections without assigning any physical source or source slot.

Policy rows are kept in deterministic external JSONL bodies.  The catalog
contains only bounded receipts, exact upstream pins, branch/checkpoint
contracts, and aggregate proofs.  Golden configuration and full/cold receipts
remain external to the canonical body and grant it no authority.
"""

from __future__ import annotations

import functools
import hashlib
import json
import re

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_source_semantic_capacity_axis_catalog as capacity_axis
    from . import persona_v2_capacity_fact_truth_occurrence_policy_validator as independent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_fact_graph as fact_graph
    import persona_v2_source_semantic_capacity_axis_catalog as capacity_axis
    import persona_v2_capacity_fact_truth_occurrence_policy_validator as independent


ARTIFACT_SCHEMA = "kio.persona.pc-capacity-fact-truth-occurrence-policy/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-capacity-fact-truth-occurrence-policy-candidate"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_CATALOG_BYTES = 2 * 2**20
TARGET_CATALOG_BYTES = 512 * 2**10
MAX_POLICY_BODY_BYTES = 2 * 2**20
MAX_POLICY_ROWS_PER_PERSONA = 64
MAX_POLICY_ROW_BYTES_INCLUDING_LF = 4 * 2**10
MAX_CUMULATIVE_EXTERNAL_BODY_BYTES = 64 * 2**20
MAX_PREFLIGHT_NODE_COUNT = 100_000
MAX_PREFLIGHT_CONTAINER_ITEMS = 4_096

# Frozen after corrected full and two-seed cold gates; this pin grants no authority.
EXPECTED_CANONICAL_BYTES = 29_868
EXPECTED_SHA256 = "85883ef574c917ec6197b9cebc2da5979d879cc29c5ac6ef0cab56e200c86601"

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
CHECKPOINT_ORDER = (
    "W0",
    "W1",
    "W2",
    "W3",
    "W4",
    "W5-pre-purge",
    "W5-final",
)
BRANCH_ORDER = ("stable", "prior", "introduced")
TRUTH_STATE_ORDER = ("current", "history-only", "absent")
OCCURRENCE_STATE_ORDER = ("fresh-current", "stale-current", "absent")

EXPECTED_POLICY_ROWS_PER_PERSONA = 36
EXPECTED_POLICY_ROW_COUNT = 720
EXPECTED_CAPACITY_CELL_COUNT = 15_048
EXPECTED_CHECKPOINT_PROJECTION_COUNT = 105_336
EXPECTED_BRANCH_POLICY_ROW_COUNTS = {
    "stable": 560,
    "prior": 80,
    "introduced": 80,
}
EXPECTED_BRANCH_CAPACITY_CELL_COUNTS = {
    "stable": 11_704,
    "prior": 1_672,
    "introduced": 1_672,
}
EXPECTED_TRUTH_STATE_COUNTS = {
    "current": 93_632,
    "history-only": 10_032,
    "absent": 1_672,
}
EXPECTED_OCCURRENCE_STATE_COUNTS = {
    "fresh-current": 93_632,
    "stale-current": 10_032,
    "absent": 1_672,
}
EXPECTED_INTENTIONAL_DIVERGENCE_COUNT = 10_032
EXPECTED_NEUTRAL_REQUIRED_COUNT = 1_672
EXPECTED_FUTURE_BEFORE_INTRODUCTION_COUNT = 0

POLICY_ROW_DOMAIN_LABEL = "kio/persona-pc-v2/capacity-fact-truth-occurrence-policy-row/v1"
POLICY_ROW_LOGICAL_KEY_FIELDS = ("persona_id", "topic_id", "fact_id")

CAPACITY_AXIS_PIN = (
    "persona-pc-v2-source-semantic-capacity-axis-catalog-candidate",
    "kio.persona.pc-source-semantic-capacity-axis-catalog/v1",
    1,
    50_473,
    "e54d39d31f325a3df1a8b671b3449f6d5f448ca6fa570bb480dd00466d9795d8",
)

FACT_GRAPH_PINS = (
    ("p01", 26_403, "2a17d26201ba45a1b7b3a5d42dbedf5b4cbae5a1f379e8213c5e3a6dcc23df65"),
    ("p02", 26_353, "8d7ef439aed58689dc873841dda12d17146d8646c90d9556578fedb423d7c8aa"),
    ("p03", 26_479, "527241e5864f47824f946910c7e0767867936326c0c67770bff5c500d3d52cdb"),
    ("p04", 26_569, "f02368bc0e29c631d68e73bb60dc0ddca101222198afdd63a13cf7c534c2d9ef"),
    ("p05", 26_536, "361d944568a68f3d473ff39c03ea5f505642ae028ad12dc111ce623b772cdb3a"),
    ("p06", 26_522, "843aa6c73d977f4e7a945e1f4fe676d9075925025bb0a7af1dfa70c4b672782d"),
    ("p07", 26_672, "ae37f7e554b65bf9c7585939380ae3895f671febbb18476be5f12243700cc447"),
    ("p08", 26_506, "32bae5c07b44e7b1252336543fe2bb82ce97d35ac0bc2f86bd2e7166fd0e2094"),
    ("p09", 26_544, "8d8971744bf6fbac7c0767243ba5cd9e1f51ddf5d52de29b1a2fe63a2fa94942"),
    ("p10", 26_497, "f2cb61e8ad2ad4378b277d00e807097a3fdb8243a7bb7642b24f563bb6072457"),
    ("p11", 26_428, "33dd344e33a1388c2531fb79b125b6558879c7e95a8e2ea546625b82189f0bb4"),
    ("p12", 26_518, "a2bc87ee8e32000f596ed7bd5e82edf6e7f5b01d3d24159cc759d2d4fd861b07"),
    ("p13", 26_487, "d71117236a333b56033bcb902cd257ebe765f84fa3322ac4851f04c9aaaaf359"),
    ("p14", 26_426, "187695085ab888ed56c421d2d5d9a10816ad25e333745146a3409235937ca1f5"),
    ("p15", 26_535, "f8f534aed03a97e14f7f4633adf590819f92f0926a9abd59e025a4337054f362"),
    ("p16", 26_577, "a4425ecd87232455a3db0bd77b7a9ee2917ea05d5742014d80f281dd19562064"),
    ("p17", 26_483, "743c2fd1aacf8228315f4e4b2272d41493d580c1526c24ec70a8a837150bd9f7"),
    ("p18", 26_485, "197d85105b0f0928787347f29babcf25c5173034897d9e7761c73c92abc26a2e"),
    ("p19", 26_442, "763dacdb0ee888088bdec4b3bda5ef598ba8fe19989d41e74c3f4b3bf1d912b8"),
    ("p20", 26_546, "70012f4de6c82cbb6220940a27000009344236e3bb5742e9975d5ea904d08db9"),
)

AUTHORITY_FIELDS = frozenset(
    {
        "authorizes_artifact_issuance",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_issuance",
        "authorizes_physical_write",
        "authorizes_policy_acceptance",
        "authorizes_render_or_materialization",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "authorizes_source_slot_assignment",
    }
)

_LOWER_ASCII_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class PersonaV2CapacityFactTruthOccurrencePolicyError(ValueError):
    """Raised when the policy candidate is not exact."""


def _fail(message):
    raise PersonaV2CapacityFactTruthOccurrencePolicyError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    byte_count_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if byte_count_set != digest_set:
        _fail("policy golden must be entirely unset or entirely set")
    if not byte_count_set:
        return None
    if (
        type(EXPECTED_CANONICAL_BYTES) is not int
        or type(EXPECTED_CANONICAL_BYTES) is bool
        or not 1 <= EXPECTED_CANONICAL_BYTES <= TARGET_CATALOG_BYTES
        or type(EXPECTED_SHA256) is not str
        or len(EXPECTED_SHA256) != 64
        or any(character not in "0123456789abcdef" for character in EXPECTED_SHA256)
    ):
        _fail("policy golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_golden_parity():
    """Check both golden trust sides before opening any dependency."""

    producer_expected = _expected_golden()
    try:
        validator_expected = independent._expected_golden()
    except Exception as error:
        raise PersonaV2CapacityFactTruthOccurrencePolicyError(
            "validator policy golden configuration is invalid"
        ) from error
    if type(producer_expected) is not type(validator_expected):
        _fail("producer and validator policy goldens differ")
    if producer_expected is not None and producer_expected != validator_expected:
        _fail("producer and validator policy goldens differ")
    return producer_expected


def _bounded_utf8_length(value, *, label):
    byte_count = 0
    for character in value:
        codepoint = ord(character)
        if codepoint <= 0x7F:
            byte_count += 1
        elif codepoint <= 0x7FF:
            byte_count += 2
        elif 0xD800 <= codepoint <= 0xDFFF:
            _fail(f"{label} contains an unpaired surrogate")
        elif codepoint <= 0xFFFF:
            byte_count += 3
        else:
            byte_count += 4
        if byte_count > artifact_common.MAX_CANONICAL_STRING_BYTES:
            _fail(f"{label} string exceeds UTF-8 byte bound")
    return byte_count


def _structural_preflight(value, *, label, maximum_bytes):
    """Reject resource bombs, aliases, and cycles before encoding/copying."""

    if type(label) is not str or not label:
        _fail("preflight label must be a non-empty exact string")
    if type(maximum_bytes) is not int or type(maximum_bytes) is bool or maximum_bytes <= 0:
        _fail("preflight byte bound must be a positive exact integer")
    stack = [(value, 0)]
    seen_containers = set()
    nodes = 0
    expanded_upper_bound = 0
    while stack:
        current, depth = stack.pop()
        nodes += 1
        if nodes > MAX_PREFLIGHT_NODE_COUNT:
            _fail(f"{label} exceeds structural node bound")
        if depth > artifact_common.MAX_CANONICAL_DEPTH:
            _fail(f"{label} exceeds structural depth bound")
        if type(current) is bool:
            expanded_upper_bound += 5
        elif type(current) is int:
            if current < 0 or current > artifact_common.MAX_INTEGER_MAGNITUDE:
                _fail(f"{label} integer exceeds checked range")
            expanded_upper_bound += 40
        elif type(current) is str:
            if len(current) > artifact_common.MAX_CANONICAL_STRING_BYTES:
                _fail(f"{label} string exceeds codepoint bound")
            utf8_bytes = _bounded_utf8_length(current, label=label)
            expanded_upper_bound += 2 + max(utf8_bytes, 6 * len(current))
        elif type(current) is list:
            identity = id(current)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(current) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail(f"{label} list exceeds item bound")
            expanded_upper_bound += 2 + len(current)
            stack.extend((item, depth + 1) for item in reversed(current))
        elif type(current) is dict:
            identity = id(current)
            if identity in seen_containers:
                _fail(f"{label} contains a repeated-container alias or cycle")
            seen_containers.add(identity)
            if len(current) > MAX_PREFLIGHT_CONTAINER_ITEMS:
                _fail(f"{label} object exceeds item bound")
            expanded_upper_bound += 2 + len(current)
            for key, item in current.items():
                if type(key) is not str:
                    _fail(f"{label} object keys must be exact strings")
                stack.append((item, depth + 1))
                stack.append((key, depth + 1))
        else:
            _fail(f"unsupported {label} value type: {type(current).__name__}")
        if expanded_upper_bound > 8 * maximum_bytes:
            _fail(f"{label} exceeds conservative expanded byte bound")
    return True


def _canonical(value, *, label, maximum):
    _structural_preflight(value, label=label, maximum_bytes=maximum)
    try:
        return artifact_common.canonical_json_bytes(
            value, label=label, max_bytes=maximum
        )
    except (RecursionError, artifact_common.PersonaV2ArtifactError) as error:
        _fail(str(error))


def canonical_json_bytes(value):
    """Return exact canonical catalog bytes after bounded preflight."""

    return _canonical(value, label="capacity fact truth occurrence policy", maximum=MAX_CATALOG_BYTES)


@functools.lru_cache(maxsize=1)
def _authenticated_capacity_axis_raw():
    try:
        axis_golden = capacity_axis._require_golden_parity()
    except capacity_axis.PersonaV2SourceSemanticCapacityAxisCatalogError as error:
        _fail(f"capacity-axis golden parity failed: {error}")
    if axis_golden != CAPACITY_AXIS_PIN[3:5]:
        _fail("capacity-axis frozen golden differs from the exact policy pin")
    value = capacity_axis.build_source_semantic_capacity_axis_catalog()
    raw = capacity_axis.canonical_json_bytes(value)
    kind, schema, version, expected_bytes, expected_sha = CAPACITY_AXIS_PIN
    if (
        value.get("artifact_kind") != kind
        or value.get("artifact_schema") != schema
        or type(value.get("artifact_schema_version")) is not int
        or type(value.get("artifact_schema_version")) is bool
        or value.get("artifact_schema_version") != version
        or len(raw) != expected_bytes
        or _sha256(raw) != expected_sha
    ):
        _fail("capacity-axis candidate exact pin drifted")
    return raw


def _authenticate_capacity_axis():
    return json.loads(_authenticated_capacity_axis_raw())


@functools.lru_cache(maxsize=1)
def _authenticated_fact_graph_raws():
    suite = fact_graph.build_fact_graph_suite()
    by_persona = {value.get("persona_id"): value for value in suite}
    if set(by_persona) != set(PERSONA_IDS):
        _fail("fact graph suite persona inventory drifted")
    raws = []
    for persona_id, expected_bytes, expected_sha in FACT_GRAPH_PINS:
        value = by_persona[persona_id]
        raw = fact_graph.canonical_json_bytes(value)
        if (
            value.get("artifact_kind") != "persona-pc-v2-fact-graph"
            or value.get("artifact_schema") != "kio.persona.pc-fact-graph/v2"
            or value.get("persona_id") != persona_id
            or len(raw) != expected_bytes
            or _sha256(raw) != expected_sha
        ):
            _fail(f"fact graph exact pin drifted for {persona_id}")
        raws.append(raw)
    return tuple(raws)


def _authenticate_fact_graphs():
    return {
        persona_id: json.loads(raw)
        for (persona_id, _, _), raw in zip(
            FACT_GRAPH_PINS, _authenticated_fact_graph_raws()
        )
    }


def _capacity_axis_provider():
    """Return a detached object from the already authenticated exact pin."""

    return json.loads(_authenticated_capacity_axis_raw())


def _fact_graph_provider(persona_id):
    if persona_id not in PERSONA_IDS:
        _fail(f"unknown persona id: {persona_id!r}")
    index = PERSONA_IDS.index(persona_id)
    return json.loads(_authenticated_fact_graph_raws()[index])


def _classify_visibility(states):
    truth = tuple(row.get("state") for row in states)
    checkpoints = tuple(row.get("checkpoint") for row in states)
    if checkpoints != CHECKPOINT_ORDER:
        _fail("fact graph checkpoint order drifted")
    if truth == ("current",) * 7:
        return "stable"
    if truth == ("current",) + ("history-only",) * 6:
        return "prior"
    if truth == ("absent",) + ("current",) * 6:
        return "introduced"
    _fail("fact graph visibility is outside the three-branch policy")


def _policy_row_id(persona_id, topic_id, fact_id):
    logical_key = [persona_id, topic_id, fact_id]
    framed = (
        POLICY_ROW_DOMAIN_LABEL.encode("ascii")
        + b"\x00"
        + _canonical(logical_key, label="policy row logical key", maximum=4 * 2**10)
    )
    return _sha256(framed)


def _derive_policy_rows(persona_axis, graph_value):
    persona_id = persona_axis.get("persona_id")
    if persona_id != graph_value.get("persona_id"):
        _fail("capacity axis and fact graph persona differ")
    graph_by_id = {}
    for graph in graph_value.get("graphs", []):
        graph_id = graph.get("graph_id")
        if type(graph_id) is not str or graph_id in graph_by_id:
            _fail(f"fact graph id inventory drifted for {persona_id}")
        graph_by_id[graph_id] = graph
    rows = []
    graph_ids_seen = set()
    for topic in persona_axis.get("topics", []):
        graph_id = topic.get("graph_id")
        if graph_id in graph_ids_seen or graph_id not in graph_by_id:
            _fail(f"capacity topic graph inventory drifted for {persona_id}")
        graph_ids_seen.add(graph_id)
        graph = graph_by_id[graph_id]
        facts = {fact.get("fact_id"): fact for fact in graph.get("facts", [])}
        if len(facts) != 9 or set(facts) != set(topic.get("fact_ids", [])):
            _fail(f"capacity topic fact inventory drifted for {persona_id}/{graph_id}")
        branch_counts = {branch: 0 for branch in BRANCH_ORDER}
        for fact_id in topic["fact_ids"]:
            source_states = facts[fact_id].get("visibility_by_checkpoint", [])
            branch = _classify_visibility(source_states)
            branch_counts[branch] += 1
            checkpoint_states = []
            for source in source_states:
                checkpoint = source["checkpoint"]
                truth_state = source["state"]
                if truth_state == "current":
                    occurrence_state = "fresh-current"
                elif truth_state == "history-only":
                    occurrence_state = "stale-current"
                elif truth_state == "absent":
                    occurrence_state = "absent"
                else:  # pragma: no cover - classification already excludes this.
                    _fail("unknown truth state")
                checkpoint_states.append(
                    {
                        "checkpoint": checkpoint,
                        "future_before_introduction": False,
                        "intentional_divergence": (
                            truth_state == "history-only"
                            and occurrence_state == "stale-current"
                        ),
                        "neutral_required": (
                            branch == "introduced" and checkpoint == "W0"
                        ),
                        "occurrence_state": occurrence_state,
                        "truth_state": truth_state,
                    }
                )
            rows.append(
                {
                    "branch": branch,
                    "checkpoint_states": checkpoint_states,
                    "fact_id": fact_id,
                    "graph_id": graph_id,
                    "persona_id": persona_id,
                    "policy_row_id": _policy_row_id(
                        persona_id, topic["topic_id"], fact_id
                    ),
                    "topic_id": topic["topic_id"],
                }
            )
        if branch_counts != {"stable": 7, "prior": 1, "introduced": 1}:
            _fail(f"three-branch fact cardinality drifted for {persona_id}/{graph_id}")
    if len(rows) != EXPECTED_POLICY_ROWS_PER_PERSONA:
        _fail(f"policy row cardinality drifted for {persona_id}")
    rows.sort(key=lambda row: row["policy_row_id"].encode("ascii"))
    return rows


@functools.lru_cache(maxsize=20)
def _policy_rows_cached(persona_id):
    if persona_id not in PERSONA_IDS:
        _fail(f"unknown persona id: {persona_id!r}")
    axis_value = _authenticate_capacity_axis()
    graphs = _authenticate_fact_graphs()
    persona_axis = next(
        row for row in axis_value["personas"] if row["persona_id"] == persona_id
    )
    return tuple(_derive_policy_rows(persona_axis, graphs[persona_id]))


def build_fact_truth_occurrence_policy_rows(persona_id):
    """Build the detached 36-row policy shard for one persona."""

    rows = _policy_rows_cached(persona_id)
    return json.loads(
        _canonical(list(rows), label="policy row shard", maximum=MAX_POLICY_BODY_BYTES)
    )


# Short aliases are intentionally public for provider-oriented harnesses.
build_policy_rows = build_fact_truth_occurrence_policy_rows


@functools.lru_cache(maxsize=20)
def _policy_body_cached(persona_id):
    rows = _policy_rows_cached(persona_id)
    encoded = []
    for row in rows:
        line = _canonical(row, label="policy body row", maximum=MAX_POLICY_ROW_BYTES_INCLUDING_LF)
        line += b"\n"
        if len(line) > MAX_POLICY_ROW_BYTES_INCLUDING_LF:
            _fail("policy body row exceeds byte cap")
        encoded.append(line)
    body = b"".join(encoded)
    if len(body) > MAX_POLICY_BODY_BYTES:
        _fail("policy body exceeds byte cap")
    return body


def fact_truth_occurrence_policy_body_bytes(persona_id):
    """Return the canonical LF-terminated policy JSONL shard."""

    return bytes(_policy_body_cached(persona_id))


policy_body_bytes = fact_truth_occurrence_policy_body_bytes


def _body_descriptor(persona_id, rows):
    body = fact_truth_occurrence_policy_body_bytes(persona_id)
    lines = body.splitlines(keepends=True)
    return {
        "body_bytes": len(body),
        "body_framing": "canonical-jsonl-one-object-per-line-lf-terminated",
        "body_sha256": _sha256(body),
        "file_name": f"{persona_id}-capacity-fact-truth-occurrence-policy-v1.jsonl",
        "first_policy_row_id": rows[0]["policy_row_id"],
        "last_policy_row_id": rows[-1]["policy_row_id"],
        "maximum_row_bytes_including_lf": max(map(len, lines)),
        "ordering": "full-policy-row-id-lower-hex-ascii-ascending",
        "row_count": len(rows),
    }


def _empty_projection_counts():
    return {
        "branch_capacity_cells": {branch: 0 for branch in BRANCH_ORDER},
        "future_before_introduction": 0,
        "intentional_divergence": 0,
        "neutral_required": 0,
        "occurrence_states": {state: 0 for state in OCCURRENCE_STATE_ORDER},
        "projection_count": 0,
        "truth_states": {state: 0 for state in TRUTH_STATE_ORDER},
    }


def _join_capacity_cells(persona_id, policy_rows):
    policy_by_key = {
        (row["topic_id"], row["fact_id"]): row for row in policy_rows
    }
    if len(policy_by_key) != EXPECTED_POLICY_ROWS_PER_PERSONA:
        _fail(f"policy join key collision for {persona_id}")
    counts = _empty_projection_counts()
    cells = capacity_axis.build_capacity_cell_rows(persona_id)
    for cell in cells:
        key = (cell["topic_id"], cell["fact_id"])
        policy = policy_by_key.get(key)
        if policy is None:
            _fail(f"capacity cell has no policy row for {persona_id}")
        counts["branch_capacity_cells"][policy["branch"]] += 1
        for state in policy["checkpoint_states"]:
            counts["projection_count"] += 1
            counts["truth_states"][state["truth_state"]] += 1
            counts["occurrence_states"][state["occurrence_state"]] += 1
            counts["intentional_divergence"] += int(state["intentional_divergence"])
            counts["neutral_required"] += int(state["neutral_required"])
            counts["future_before_introduction"] += int(
                state["future_before_introduction"]
            )
    return len(cells), counts


def _add_counts(total, addition):
    for branch in BRANCH_ORDER:
        total["branch_capacity_cells"][branch] += addition["branch_capacity_cells"][branch]
    for state in TRUTH_STATE_ORDER:
        total["truth_states"][state] += addition["truth_states"][state]
    for state in OCCURRENCE_STATE_ORDER:
        total["occurrence_states"][state] += addition["occurrence_states"][state]
    for field in (
        "projection_count",
        "intentional_divergence",
        "neutral_required",
        "future_before_introduction",
    ):
        total[field] += addition[field]


def _branch_templates():
    return [
        {
            "branch": "stable",
            "occurrence_states": ["fresh-current"] * 7,
            "truth_states": ["current"] * 7,
        },
        {
            "branch": "prior",
            "occurrence_states": ["fresh-current"] + ["stale-current"] * 6,
            "truth_states": ["current"] + ["history-only"] * 6,
        },
        {
            "branch": "introduced",
            "occurrence_states": ["absent"] + ["fresh-current"] * 6,
            "truth_states": ["absent"] + ["current"] * 6,
        },
    ]


@functools.lru_cache(maxsize=1)
def _canonical_state_raw():
    axis_value = _authenticate_capacity_axis()
    graph_values = _authenticate_fact_graphs()
    axis_personas = {row["persona_id"]: row for row in axis_value["personas"]}
    personas = []
    aggregate = _empty_projection_counts()
    total_cells = 0
    total_body_bytes = 0
    policy_branch_rows = {branch: 0 for branch in BRANCH_ORDER}
    for persona_id in PERSONA_IDS:
        persona_axis = axis_personas[persona_id]
        rows = _derive_policy_rows(persona_axis, graph_values[persona_id])
        descriptor = _body_descriptor(persona_id, rows)
        cell_count, counts = _join_capacity_cells(persona_id, rows)
        row_branches = {
            branch: sum(row["branch"] == branch for row in rows)
            for branch in BRANCH_ORDER
        }
        for branch in BRANCH_ORDER:
            policy_branch_rows[branch] += row_branches[branch]
        total_cells += cell_count
        total_body_bytes += descriptor["body_bytes"]
        _add_counts(aggregate, counts)
        personas.append(
            {
                "branch_capacity_cell_counts": counts["branch_capacity_cells"],
                "branch_policy_row_counts": row_branches,
                "capacity_cell_count": cell_count,
                "checkpoint_projection_count": counts["projection_count"],
                "eligible_language_count": persona_axis["eligible_language_count"],
                "fact_truth_occurrence_policy_body": descriptor,
                "persona_id": persona_id,
                "policy_row_count": len(rows),
            }
        )

    if (
        policy_branch_rows != EXPECTED_BRANCH_POLICY_ROW_COUNTS
        or aggregate["branch_capacity_cells"] != EXPECTED_BRANCH_CAPACITY_CELL_COUNTS
        or aggregate["truth_states"] != EXPECTED_TRUTH_STATE_COUNTS
        or aggregate["occurrence_states"] != EXPECTED_OCCURRENCE_STATE_COUNTS
        or total_cells != EXPECTED_CAPACITY_CELL_COUNT
        or aggregate["projection_count"] != EXPECTED_CHECKPOINT_PROJECTION_COUNT
        or aggregate["intentional_divergence"] != EXPECTED_INTENTIONAL_DIVERGENCE_COUNT
        or aggregate["neutral_required"] != EXPECTED_NEUTRAL_REQUIRED_COUNT
        or aggregate["future_before_introduction"] != EXPECTED_FUTURE_BEFORE_INTRODUCTION_COUNT
    ):
        _fail("capacity-to-policy aggregate proof drifted")

    axis_kind, axis_schema, axis_version, axis_bytes, axis_sha = CAPACITY_AXIS_PIN
    input_bindings = [
        {
            "accepted": True,
            "artifact_kind": axis_kind,
            "artifact_schema": axis_schema,
            "artifact_schema_version": axis_version,
            "body_opened_for_policy_derivation": True,
            "canonical_bytes": axis_bytes,
            "dependency_role": "exact-frozen-capacity-cell-axis-pin-not-issued",
            "frozen": True,
            "issued": False,
            "name": "persona-v2-source-semantic-capacity-axis-catalog",
            "sha256": axis_sha,
        }
    ]
    for persona_id, graph_bytes, graph_sha in FACT_GRAPH_PINS:
        input_bindings.append(
            {
                "artifact_kind": "persona-pc-v2-fact-graph",
                "artifact_schema": "kio.persona.pc-fact-graph/v2",
                "artifact_schema_version": 2,
                "body_opened_for_policy_derivation": True,
                "canonical_bytes": graph_bytes,
                "dependency_role": "truth-branch-and-checkpoint-owner",
                "name": "persona-v2-fact-graph",
                "persona_id": persona_id,
                "sha256": graph_sha,
            }
        )

    value = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "candidate_status": "proposal-non-authorizing-not-issued",
        "canonical_limits": {
            "cumulative_external_body_bytes": total_body_bytes,
            "external_bodies_embedded": False,
            "max_catalog_bytes": MAX_CATALOG_BYTES,
            "max_cumulative_external_body_bytes": MAX_CUMULATIVE_EXTERNAL_BODY_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_policy_body_bytes": MAX_POLICY_BODY_BYTES,
            "max_policy_row_bytes_including_lf": MAX_POLICY_ROW_BYTES_INCLUDING_LF,
            "max_policy_rows_per_persona": MAX_POLICY_ROWS_PER_PERSONA,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "completion_claims": {
            "all_policy_bodies_bound_by_receipt": True,
            "capacity_axis_accepted": True,
            "capacity_axis_frozen": True,
            "capacity_axis_issued": False,
            "capacity_cell_join_count_proved": True,
            "fact_truth_occurrence_policy_acceptance_receipt_bound": False,
            "fact_truth_occurrence_policy_golden_freeze_receipt_bound": False,
            "fact_truth_occurrence_policy_issued": False,
            "full_dependency_body_replay_receipt_bound": False,
            "history_plan_available": False,
            "physical_source_membership_available": False,
            "render_plan_available": False,
            "source_slot_assignment_available": False,
            "two_hash_seed_cold_build_receipt_bound": False,
            "w5_fit_proved": False,
        },
        "completion_scope": "capacity-fact-truth-occurrence-policy-candidate-only-no-slot-no-physical-source-no-render-no-history-no-execution-no-g0",
        "downstream_status": {
            "history_status": "unknown-not-compiled",
            "physical_source_status": "unknown-not-bound",
            "render_status": "unknown-not-compiled",
            "source_slot_assignment_status": "unknown-not-assigned",
            "w5_fit_status": "unknown-not-proved",
        },
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "input_binding_order": [
            "persona-v2-source-semantic-capacity-axis-catalog",
            *[f"persona-v2-fact-graph/{persona_id}" for persona_id in PERSONA_IDS],
        ],
        "input_bindings": input_bindings,
        "orders": {
            "branch_order": list(BRANCH_ORDER),
            "checkpoint_order": list(CHECKPOINT_ORDER),
            "occurrence_state_order": list(OCCURRENCE_STATE_ORDER),
            "persona_order": list(PERSONA_IDS),
            "truth_state_order": list(TRUTH_STATE_ORDER),
        },
        "personas": personas,
        "policy_contract": {
            "branch_templates": _branch_templates(),
            "checkpoint_count": len(CHECKPOINT_ORDER),
            "introduced_w0_neutral_required": True,
            "policy_row_id_digest": "sha256-full-64-lowercase-hex",
            "policy_row_id_domain_label": POLICY_ROW_DOMAIN_LABEL,
            "policy_row_id_framing": "ASCII(domain-label)-NUL-UTF8(canonical-json-array(logical-key))",
            "policy_row_logical_key_fields": list(POLICY_ROW_LOGICAL_KEY_FIELDS),
            "prior_post_w0_divergence_intentional": True,
            "stable_all_checkpoints_current": True,
        },
        "proposal_only": True,
        "remaining_blockers": [
            "policy-acceptance-and-golden-freeze-evidence-external-not-bound",
            "full-and-two-seed-cold-replay-evidence-external-not-bound",
            "source-slot-assignment-not-available",
            "physical-source-membership-not-available",
            "w5-fit-not-proved",
            "render-and-history-plans-not-compiled",
        ],
        "side_input_contract": {
            "answer_keys_consumed": 0,
            "relevance_keys_consumed": 0,
            "runtime_clock_network_randomness_or_environment_inputs_consumed": 0,
        },
        "summary": {
            "branch_capacity_cell_counts": aggregate["branch_capacity_cells"],
            "branch_policy_row_counts": policy_branch_rows,
            "capacity_cell_count": total_cells,
            "checkpoint_count": len(CHECKPOINT_ORDER),
            "checkpoint_projection_count": aggregate["projection_count"],
            "external_policy_body_bytes": total_body_bytes,
            "future_before_introduction_count": aggregate["future_before_introduction"],
            "intentional_divergence_count": aggregate["intentional_divergence"],
            "neutral_required_count": aggregate["neutral_required"],
            "occurrence_state_counts": aggregate["occurrence_states"],
            "persona_count": len(PERSONA_IDS),
            "policy_row_count": sum(policy_branch_rows.values()),
            "truth_state_counts": aggregate["truth_states"],
        },
    }
    raw = canonical_json_bytes(value)
    if len(raw) > TARGET_CATALOG_BYTES:
        _fail("policy candidate exceeds target byte budget")
    golden = _expected_golden()
    if golden is not None and (len(raw), _sha256(raw)) != golden:
        _fail("policy candidate does not match configured golden")
    return raw


def build_capacity_fact_truth_occurrence_policy():
    """Build a detached, exact, non-authorizing policy candidate."""

    _require_golden_parity()
    return json.loads(_canonical_state_raw())


def validate_capacity_fact_truth_occurrence_policy(value):
    """Run the producer-independent validator with two-read providers."""

    _require_golden_parity()
    try:
        return independent.validate_capacity_fact_truth_occurrence_policy(
            value,
            producer_expected_golden=_expected_golden(),
            capacity_axis_provider=_capacity_axis_provider,
            fact_graph_provider=_fact_graph_provider,
            capacity_cell_body_provider=capacity_axis.capacity_cell_body_bytes,
            policy_body_provider=fact_truth_occurrence_policy_body_bytes,
        )
    except independent.PersonaV2CapacityFactTruthOccurrencePolicyValidationError as error:
        raise PersonaV2CapacityFactTruthOccurrencePolicyError(str(error)) from error


def require_accepted_capacity_fact_truth_occurrence_policy():
    """Fail closed because this artifact grants no downstream authority."""

    _fail(
        "capacity fact truth/occurrence policy is not issued and grants no "
        "downstream authority"
    )


if __name__ == "__main__":  # pragma: no cover
    artifact = build_capacity_fact_truth_occurrence_policy()
    validate_capacity_fact_truth_occurrence_policy(artifact)
    raw = canonical_json_bytes(artifact)
    print(raw.decode("utf-8"))
    print(f"canonical_bytes={len(raw)} sha256={_sha256(raw)}")
