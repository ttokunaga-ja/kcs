"""Independent validator for the capacity fact truth/occurrence policy.

This module intentionally does not import the sibling producer.  It opens the
exact frozen capacity-axis catalog, each frozen fact graph, and both families of
persona-sharded JSONL bodies twice; independently rebuilds every row and join;
then compares the complete expected candidate byte-for-byte.  All caller-owned
objects are postflight checked so provider-induced mutation fails closed.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import functools

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_source_semantic_capacity_axis_catalog as capacity_axis
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_fact_graph as fact_graph
    import persona_v2_source_semantic_capacity_axis_catalog as capacity_axis


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
MAX_CAPACITY_BODY_BYTES = 4 * 2**20
MAX_CAPACITY_ROW_BYTES_INCLUDING_LF = 1_024
MAX_CUMULATIVE_CAPACITY_BODY_BYTES = 256 * 2**20
MAX_PREFLIGHT_NODE_COUNT = 100_000
MAX_PREFLIGHT_CONTAINER_ITEMS = 4_096

# Must remain byte-identical to the non-authorizing producer golden.
EXPECTED_CANONICAL_BYTES = 29_868
EXPECTED_SHA256 = "d0affa86583286cbf2eb466f807b3998c6be0d77dff7e541f91dca2c46271b11"

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
CAPACITY_CELL_DOMAIN_LABEL = "kio/persona-pc-v2/source-semantic-capacity-cell/v1"
CAPACITY_CELL_LOGICAL_KEY_FIELDS = (
    "persona_id",
    "topic_id",
    "language",
    "fact_id",
    "replica_ordinal",
)

CAPACITY_AXIS_PIN = (
    "persona-pc-v2-source-semantic-capacity-axis-catalog-candidate",
    "kio.persona.pc-source-semantic-capacity-axis-catalog/v1",
    1,
    50_473,
    "2bcb84e6ca46f09b29a3f4756191b98970a4f78101e4455675b6c713dc1cab85",
)

FACT_GRAPH_PINS = (
    ("p01", 26_403, "2a17d26201ba45a1b7b3a5d42dbedf5b4cbae5a1f379e8213c5e3a6dcc23df65"),
    ("p02", 26_353, "92afd654b99da2b4eb537fd9269e0e95405a530e6c01d54eaaaeb8dae42887ef"),
    ("p03", 26_479, "648b4cb41ba37f925be9022ac683c8982e8aa8dc5d3a4cda0a020d93ae7d88ad"),
    ("p04", 26_569, "c184999ebbdc043cbb687965815e970954577022632a2b76720e4249e507bf32"),
    ("p05", 26_536, "ed8b9a49a65f9b9df00693492b1d27d8a52a70e23ba4d873a779160d54747b20"),
    ("p06", 26_522, "2c523a93fa6279b62aba2a7708a0929861b850f90260377e647455c8a810fe02"),
    ("p07", 26_672, "c2bc8a08e54de557617b5fe1c0b75732100c971c27bf1e6dc9bbc73b34bad3a4"),
    ("p08", 26_506, "fdce514cd277e9a5758a97fe6e814c68c3a29ec1d06c8cdd233f9adcb7650ae5"),
    ("p09", 26_544, "7db7bab2e3ca1c9c91ef7108a097646894907d358f9a304f72ee662e62c52a19"),
    ("p10", 26_497, "d7fb092cddfcfe45e6fc6910e35c33d8e00c1a99f8b272ff50e6d7c9edce1503"),
    ("p11", 26_428, "f2882db025022ee476ed2dba11e2813ecc3e0620df00ad2321295113d583c301"),
    ("p12", 26_518, "e86896736e304e1ba0b56fc43ddc31021db5cdb9b11f1edadd6ab9851389d994"),
    ("p13", 26_487, "c13953d43b88a817b4a6147c0e00c432f48ecaa7600610a5a87c3dc8e62cadb3"),
    ("p14", 26_426, "203cc67a8deaf06042d9a201237f89ceefe4c814705325d427c3dc1ecc7b1f62"),
    ("p15", 26_535, "302f8ba3fe9ee3a890724fb675a09a158d3890e70622b978441966b14af4a26e"),
    ("p16", 26_577, "ee1d0718b7b9cacc370ead3a19f1e8e5d22bdaf89fcb4503af2f225d17a77567"),
    ("p17", 26_483, "c342080dc551a4da7b2fbbcd0948bd80ffbc5300e3c04fae7400207639aaa119"),
    ("p18", 26_485, "26f3c8bbdd4af1ad87572a22ca45961d1276b30d699185331876839a73063eb9"),
    ("p19", 26_442, "02e33ebfdd8c381b704c2c0f67577f27588f5c4d442baad6e256570faf926b2f"),
    ("p20", 26_546, "423d3973d26d7ab8e234c1f93f04c166e3fcdc62b560101bbb4b893960a70df7"),
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
PROHIBITED_FIELD_TOKENS = ("query", "oracle", "evaluation")


class PersonaV2CapacityFactTruthOccurrencePolicyValidationError(ValueError):
    """Raised when independent policy validation fails closed."""


def _fail(message):
    raise PersonaV2CapacityFactTruthOccurrencePolicyValidationError(message)


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


_GOLDEN_NOT_PROVIDED = object()


def _require_producer_golden_parity(producer_expected):
    validator_expected = _expected_golden()
    if producer_expected is _GOLDEN_NOT_PROVIDED:
        _fail("producer policy golden was not supplied")
    if producer_expected is not None and (
        type(producer_expected) is not tuple
        or len(producer_expected) != 2
        or type(producer_expected[0]) is not int
        or type(producer_expected[0]) is bool
        or not 1 <= producer_expected[0] <= TARGET_CATALOG_BYTES
        or type(producer_expected[1]) is not str
        or len(producer_expected[1]) != 64
        or any(character not in "0123456789abcdef" for character in producer_expected[1])
    ):
        _fail("producer policy golden is invalid")
    if type(producer_expected) is not type(validator_expected):
        _fail("producer and validator policy goldens differ")
    if producer_expected is not None and producer_expected != validator_expected:
        _fail("producer and validator policy goldens differ")
    return validator_expected


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
    """Bound before normalization/encoding and reject aliases/cycles."""

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


def _require_exact_int(value, *, label, minimum=0, maximum=None):
    if type(value) is not int or type(value) is bool or value < minimum:
        _fail(f"{label} must be an exact integer")
    if maximum is not None and value > maximum:
        _fail(f"{label} exceeds its integer bound")
    return value


def _require_exact_bool(value, *, label):
    if type(value) is not bool:
        _fail(f"{label} must be an exact boolean")
    return value


def _reject_prohibited_fields(value, *, label):
    stack = [value]
    while stack:
        current = stack.pop()
        if type(current) is dict:
            for key, item in current.items():
                lowered = key.lower()
                if any(token in lowered for token in PROHIBITED_FIELD_TOKENS):
                    _fail(f"{label} contains prohibited field {key!r}")
                stack.append(item)
        elif type(current) is list:
            stack.extend(current)


def _duplicate_rejecting_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            _fail(f"duplicate JSON object key: {key!r}")
        value[key] = item
    return value


def _bounded_json_integer(token):
    if type(token) is not str or len(token) > 40:
        _fail("JSON integer token exceeds checked range")
    try:
        return int(token)
    except ValueError as error:  # pragma: no cover - decoder supplies integer grammar.
        raise PersonaV2CapacityFactTruthOccurrencePolicyValidationError(
            "JSON integer token is invalid"
        ) from error


def _parse_json(raw, *, label, maximum):
    if type(raw) is not bytes:
        _fail(f"{label} must be exact bytes")
    if len(raw) > maximum:
        _fail(f"{label} exceeds byte cap")
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_duplicate_rejecting_object,
            parse_constant=lambda token: _fail(f"{label} contains {token}"),
            parse_float=lambda token: _fail(f"{label} contains a float"),
            parse_int=_bounded_json_integer,
        )
    except PersonaV2CapacityFactTruthOccurrencePolicyValidationError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} is not strict UTF-8 JSON: {error}")
    canonical = _canonical(value, label=label, maximum=maximum)
    if not hmac.compare_digest(raw, canonical):
        _fail(f"{label} is not exact canonical JSON")
    return value


def _open_object_twice(provider, *args, label, maximum):
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    snapshots = []
    for _ in range(2):
        try:
            value = provider(*args)
        except Exception as error:
            raise PersonaV2CapacityFactTruthOccurrencePolicyValidationError(
                f"{label} provider failed"
            ) from error
        snapshots.append(_canonical(value, label=label, maximum=maximum))
    if not hmac.compare_digest(snapshots[0], snapshots[1]):
        _fail(f"{label} provider changed between two reads")
    return _parse_json(snapshots[0], label=label, maximum=maximum)


def _open_bytes_twice(provider, *args, label, maximum):
    if not callable(provider):
        _fail(f"{label} provider must be callable")
    snapshots = []
    for _ in range(2):
        try:
            raw = provider(*args)
        except Exception as error:
            raise PersonaV2CapacityFactTruthOccurrencePolicyValidationError(
                f"{label} provider failed"
            ) from error
        if type(raw) is not bytes:
            _fail(f"{label} provider must return exact bytes")
        if len(raw) > maximum:
            _fail(f"{label} exceeds byte cap")
        snapshots.append(bytes(raw))
    if not hmac.compare_digest(snapshots[0], snapshots[1]):
        _fail(f"{label} provider changed between two reads")
    return snapshots[0]


@functools.lru_cache(maxsize=1)
def _default_capacity_axis_raw():
    value = capacity_axis.build_source_semantic_capacity_axis_catalog()
    return _canonical(value, label="default capacity-axis candidate", maximum=MAX_CATALOG_BYTES)


def _default_capacity_axis_provider():
    return json.loads(_default_capacity_axis_raw())


@functools.lru_cache(maxsize=1)
def _default_fact_graph_raws():
    suite = fact_graph.build_fact_graph_suite()
    by_persona = {value.get("persona_id"): value for value in suite}
    if set(by_persona) != set(PERSONA_IDS):
        _fail("default fact graph suite persona inventory drifted")
    return tuple(
        _canonical(
            by_persona[persona_id],
            label=f"default fact graph {persona_id}",
            maximum=2**20,
        )
        for persona_id in PERSONA_IDS
    )


def _default_fact_graph_provider(persona_id):
    if persona_id not in PERSONA_IDS:
        _fail(f"unknown persona id: {persona_id!r}")
    return json.loads(_default_fact_graph_raws()[PERSONA_IDS.index(persona_id)])


def _authenticate_capacity_axis(provider):
    try:
        axis_golden = capacity_axis._require_golden_parity()
    except capacity_axis.PersonaV2SourceSemanticCapacityAxisCatalogError as error:
        _fail(f"capacity-axis golden parity failed: {error}")
    if axis_golden != CAPACITY_AXIS_PIN[3:5]:
        _fail("capacity-axis frozen golden differs from the exact policy pin")
    value = _open_object_twice(
        provider,
        label="capacity-axis candidate",
        maximum=MAX_CATALOG_BYTES,
    )
    raw = _canonical(value, label="capacity-axis candidate", maximum=MAX_CATALOG_BYTES)
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
    return value


def _authenticate_fact_graphs(provider):
    values = {}
    for persona_id, expected_bytes, expected_sha in FACT_GRAPH_PINS:
        value = _open_object_twice(
            provider,
            persona_id,
            label=f"fact graph {persona_id}",
            maximum=2**20,
        )
        raw = _canonical(value, label=f"fact graph {persona_id}", maximum=2**20)
        if (
            value.get("artifact_kind") != "persona-pc-v2-fact-graph"
            or value.get("artifact_schema") != "kio.persona.pc-fact-graph/v2"
            or value.get("persona_id") != persona_id
            or len(raw) != expected_bytes
            or _sha256(raw) != expected_sha
        ):
            _fail(f"fact graph exact pin drifted for {persona_id}")
        values[persona_id] = value
    return values


def _classify_visibility(states):
    if type(states) is not list or len(states) != 7:
        _fail("fact visibility must contain seven checkpoint states")
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


def _digest_id(domain_label, logical_key, *, label):
    raw = _canonical(logical_key, label=label, maximum=4 * 2**10)
    return _sha256(domain_label.encode("ascii") + b"\x00" + raw)


def _derive_policy_rows(persona_axis, graph_value):
    persona_id = persona_axis.get("persona_id")
    if persona_id != graph_value.get("persona_id"):
        _fail("capacity axis and fact graph persona differ")
    graph_by_id = {}
    graphs = graph_value.get("graphs")
    if type(graphs) is not list or len(graphs) != 4:
        _fail(f"fact graph count drifted for {persona_id}")
    for graph in graphs:
        graph_id = graph.get("graph_id")
        if type(graph_id) is not str or graph_id in graph_by_id:
            _fail(f"fact graph id inventory drifted for {persona_id}")
        graph_by_id[graph_id] = graph
    topics = persona_axis.get("topics")
    if type(topics) is not list or len(topics) != 4:
        _fail(f"capacity topic count drifted for {persona_id}")
    rows = []
    graph_ids_seen = set()
    for topic in topics:
        graph_id = topic.get("graph_id")
        if graph_id in graph_ids_seen or graph_id not in graph_by_id:
            _fail(f"capacity topic graph inventory drifted for {persona_id}")
        graph_ids_seen.add(graph_id)
        graph = graph_by_id[graph_id]
        facts = graph.get("facts")
        if type(facts) is not list or len(facts) != 9:
            _fail(f"fact inventory drifted for {persona_id}/{graph_id}")
        fact_by_id = {row.get("fact_id"): row for row in facts}
        fact_ids = topic.get("fact_ids")
        if (
            type(fact_ids) is not list
            or len(fact_ids) != 9
            or len(fact_by_id) != 9
            or set(fact_by_id) != set(fact_ids)
        ):
            _fail(f"capacity topic fact inventory drifted for {persona_id}/{graph_id}")
        branches = {branch: 0 for branch in BRANCH_ORDER}
        for fact_id in fact_ids:
            source_states = fact_by_id[fact_id].get("visibility_by_checkpoint")
            branch = _classify_visibility(source_states)
            branches[branch] += 1
            states = []
            for source in source_states:
                checkpoint = source["checkpoint"]
                truth_state = source["state"]
                occurrence_state = {
                    "current": "fresh-current",
                    "history-only": "stale-current",
                    "absent": "absent",
                }[truth_state]
                states.append(
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
            topic_id = topic.get("topic_id")
            rows.append(
                {
                    "branch": branch,
                    "checkpoint_states": states,
                    "fact_id": fact_id,
                    "graph_id": graph_id,
                    "persona_id": persona_id,
                    "policy_row_id": _digest_id(
                        POLICY_ROW_DOMAIN_LABEL,
                        [persona_id, topic_id, fact_id],
                        label="policy row logical key",
                    ),
                    "topic_id": topic_id,
                }
            )
        if branches != {"stable": 7, "prior": 1, "introduced": 1}:
            _fail(f"three-branch fact cardinality drifted for {persona_id}/{graph_id}")
    if len(rows) != EXPECTED_POLICY_ROWS_PER_PERSONA:
        _fail(f"policy row cardinality drifted for {persona_id}")
    rows.sort(key=lambda row: row["policy_row_id"].encode("ascii"))
    return rows


def _canonical_jsonl(rows, *, label, maximum_row_bytes, maximum_body_bytes):
    lines = []
    for row in rows:
        line = _canonical(row, label=f"{label} row", maximum=maximum_row_bytes) + b"\n"
        if len(line) > maximum_row_bytes:
            _fail(f"{label} row exceeds byte cap")
        lines.append(line)
    body = b"".join(lines)
    if len(body) > maximum_body_bytes:
        _fail(f"{label} body exceeds byte cap")
    return body


def _parse_jsonl(raw, *, label, maximum_row_bytes, maximum_body_bytes, maximum_rows):
    if type(raw) is not bytes or len(raw) > maximum_body_bytes:
        _fail(f"{label} body is not bounded exact bytes")
    if not raw or not raw.endswith(b"\n"):
        _fail(f"{label} body must be non-empty and LF terminated")
    lines = raw.splitlines(keepends=True)
    if len(lines) > maximum_rows:
        _fail(f"{label} body exceeds row cap")
    rows = []
    for line in lines:
        if not line.endswith(b"\n") or len(line) > maximum_row_bytes:
            _fail(f"{label} row framing or byte cap drifted")
        rows.append(
            _parse_json(
                line[:-1], label=f"{label} row", maximum=maximum_row_bytes
            )
        )
    return rows


def _derive_capacity_rows(persona_axis):
    persona_id = persona_axis.get("persona_id")
    languages = persona_axis.get("eligible_languages")
    topics = persona_axis.get("topics")
    if type(languages) is not list or not languages or type(topics) is not list:
        _fail(f"capacity axes drifted for {persona_id}")
    rows = []
    for topic in topics:
        for language in languages:
            for fact_id in topic["fact_ids"]:
                for replica_ordinal in range(1, 12):
                    logical = [
                        persona_id,
                        topic["topic_id"],
                        language,
                        fact_id,
                        replica_ordinal,
                    ]
                    rows.append(
                        {
                            "capacity_cell_id": _digest_id(
                                CAPACITY_CELL_DOMAIN_LABEL,
                                logical,
                                label="capacity cell logical key",
                            ),
                            "fact_id": fact_id,
                            "language": language,
                            "persona_id": persona_id,
                            "replica_ordinal": replica_ordinal,
                            "topic_id": topic["topic_id"],
                        }
                    )
    rows.sort(key=lambda row: row["capacity_cell_id"].encode("ascii"))
    return rows


def _validate_capacity_rows(rows, *, persona_id):
    seen = set()
    previous = None
    for row in rows:
        if type(row) is not dict or set(row) != {
            "capacity_cell_id",
            "fact_id",
            "language",
            "persona_id",
            "replica_ordinal",
            "topic_id",
        }:
            _fail(f"capacity cell fields drifted for {persona_id}")
        if row["persona_id"] != persona_id:
            _fail(f"capacity cell persona drifted for {persona_id}")
        _require_exact_int(
            row["replica_ordinal"],
            label="capacity replica ordinal",
            minimum=1,
            maximum=11,
        )
        cell_id = row["capacity_cell_id"]
        if type(cell_id) is not str or len(cell_id) != 64:
            _fail(f"capacity cell id is invalid for {persona_id}")
        if previous is not None and previous.encode("ascii") >= cell_id.encode("ascii"):
            _fail(f"capacity cell ordering drifted for {persona_id}")
        if cell_id in seen:
            _fail(f"capacity cell collision for {persona_id}")
        seen.add(cell_id)
        previous = cell_id


def _body_descriptor(persona_id, rows, body):
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


def _join_capacity_rows(capacity_rows, policy_rows, *, persona_id):
    policies = {(row["topic_id"], row["fact_id"]): row for row in policy_rows}
    if len(policies) != EXPECTED_POLICY_ROWS_PER_PERSONA:
        _fail(f"policy join key collision for {persona_id}")
    counts = _empty_projection_counts()
    for cell in capacity_rows:
        policy = policies.get((cell["topic_id"], cell["fact_id"]))
        if policy is None:
            _fail(f"capacity cell lacks a policy row for {persona_id}")
        counts["branch_capacity_cells"][policy["branch"]] += 1
        for state in policy["checkpoint_states"]:
            truth_state = state["truth_state"]
            occurrence_state = state["occurrence_state"]
            if truth_state not in counts["truth_states"]:
                _fail("unknown truth state")
            if occurrence_state not in counts["occurrence_states"]:
                _fail("unknown occurrence state")
            counts["projection_count"] += 1
            counts["truth_states"][truth_state] += 1
            counts["occurrence_states"][occurrence_state] += 1
            counts["intentional_divergence"] += int(
                _require_exact_bool(
                    state["intentional_divergence"],
                    label="intentional divergence flag",
                )
            )
            counts["neutral_required"] += int(
                _require_exact_bool(state["neutral_required"], label="neutral flag")
            )
            counts["future_before_introduction"] += int(
                _require_exact_bool(
                    state["future_before_introduction"], label="future flag"
                )
            )
    return counts


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


def _build_expected_candidate(
    axis_value,
    graph_values,
    *,
    capacity_cell_body_provider,
    policy_body_provider,
):
    axis_personas = {row.get("persona_id"): row for row in axis_value.get("personas", [])}
    if set(axis_personas) != set(PERSONA_IDS):
        _fail("capacity-axis persona inventory drifted")
    personas = []
    aggregate = _empty_projection_counts()
    total_cells = 0
    total_policy_body_bytes = 0
    total_capacity_body_bytes = 0
    policy_branch_rows = {branch: 0 for branch in BRANCH_ORDER}

    for persona_id in PERSONA_IDS:
        persona_axis = axis_personas[persona_id]
        policy_rows = _derive_policy_rows(persona_axis, graph_values[persona_id])
        expected_policy_body = _canonical_jsonl(
            policy_rows,
            label=f"policy {persona_id}",
            maximum_row_bytes=MAX_POLICY_ROW_BYTES_INCLUDING_LF,
            maximum_body_bytes=MAX_POLICY_BODY_BYTES,
        )
        supplied_policy_body = _open_bytes_twice(
            policy_body_provider,
            persona_id,
            label=f"policy body {persona_id}",
            maximum=MAX_POLICY_BODY_BYTES,
        )
        supplied_policy_rows = _parse_jsonl(
            supplied_policy_body,
            label=f"policy {persona_id}",
            maximum_row_bytes=MAX_POLICY_ROW_BYTES_INCLUDING_LF,
            maximum_body_bytes=MAX_POLICY_BODY_BYTES,
            maximum_rows=MAX_POLICY_ROWS_PER_PERSONA,
        )
        _reject_prohibited_fields(supplied_policy_rows, label=f"policy {persona_id}")
        if (
            supplied_policy_rows != policy_rows
            or not hmac.compare_digest(supplied_policy_body, expected_policy_body)
        ):
            _fail(f"policy body derivation drifted for {persona_id}")

        capacity_rows = _derive_capacity_rows(persona_axis)
        expected_capacity_body = _canonical_jsonl(
            capacity_rows,
            label=f"capacity {persona_id}",
            maximum_row_bytes=MAX_CAPACITY_ROW_BYTES_INCLUDING_LF,
            maximum_body_bytes=MAX_CAPACITY_BODY_BYTES,
        )
        supplied_capacity_body = _open_bytes_twice(
            capacity_cell_body_provider,
            persona_id,
            label=f"capacity body {persona_id}",
            maximum=MAX_CAPACITY_BODY_BYTES,
        )
        supplied_capacity_rows = _parse_jsonl(
            supplied_capacity_body,
            label=f"capacity {persona_id}",
            maximum_row_bytes=MAX_CAPACITY_ROW_BYTES_INCLUDING_LF,
            maximum_body_bytes=MAX_CAPACITY_BODY_BYTES,
            maximum_rows=4_096,
        )
        if (
            supplied_capacity_rows != capacity_rows
            or not hmac.compare_digest(supplied_capacity_body, expected_capacity_body)
        ):
            _fail(f"capacity body derivation drifted for {persona_id}")
        _validate_capacity_rows(supplied_capacity_rows, persona_id=persona_id)

        axis_receipt = persona_axis.get("capacity_cell_body")
        if type(axis_receipt) is not dict or (
            axis_receipt.get("body_bytes") != len(supplied_capacity_body)
            or axis_receipt.get("body_sha256") != _sha256(supplied_capacity_body)
            or axis_receipt.get("row_count") != len(supplied_capacity_rows)
        ):
            _fail(f"capacity-axis body receipt drifted for {persona_id}")

        counts = _join_capacity_rows(
            supplied_capacity_rows, supplied_policy_rows, persona_id=persona_id
        )
        row_branches = {
            branch: sum(row["branch"] == branch for row in supplied_policy_rows)
            for branch in BRANCH_ORDER
        }
        for branch in BRANCH_ORDER:
            policy_branch_rows[branch] += row_branches[branch]
        total_cells += len(supplied_capacity_rows)
        total_policy_body_bytes += len(supplied_policy_body)
        total_capacity_body_bytes += len(supplied_capacity_body)
        _add_counts(aggregate, counts)
        personas.append(
            {
                "branch_capacity_cell_counts": counts["branch_capacity_cells"],
                "branch_policy_row_counts": row_branches,
                "capacity_cell_count": len(supplied_capacity_rows),
                "checkpoint_projection_count": counts["projection_count"],
                "eligible_language_count": persona_axis["eligible_language_count"],
                "fact_truth_occurrence_policy_body": _body_descriptor(
                    persona_id, supplied_policy_rows, supplied_policy_body
                ),
                "persona_id": persona_id,
                "policy_row_count": len(supplied_policy_rows),
            }
        )

    if total_capacity_body_bytes > MAX_CUMULATIVE_CAPACITY_BODY_BYTES:
        _fail("cumulative capacity body bytes exceed cap")
    if total_policy_body_bytes > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("cumulative policy body bytes exceed cap")
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
    bindings = [
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
        bindings.append(
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

    return {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": {field: False for field in sorted(AUTHORITY_FIELDS)},
        "candidate_status": "proposal-non-authorizing-not-issued",
        "canonical_limits": {
            "cumulative_external_body_bytes": total_policy_body_bytes,
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
        "input_bindings": bindings,
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
            "external_policy_body_bytes": total_policy_body_bytes,
            "future_before_introduction_count": aggregate["future_before_introduction"],
            "intentional_divergence_count": aggregate["intentional_divergence"],
            "neutral_required_count": aggregate["neutral_required"],
            "occurrence_state_counts": aggregate["occurrence_states"],
            "persona_count": len(PERSONA_IDS),
            "policy_row_count": sum(policy_branch_rows.values()),
            "truth_state_counts": aggregate["truth_states"],
        },
    }


def validate_capacity_fact_truth_occurrence_policy(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    capacity_axis_provider=None,
    fact_graph_provider=None,
    capacity_cell_body_provider=None,
    policy_body_provider=None,
):
    """Validate the candidate and all persona bodies with two-read replay."""

    golden = _require_producer_golden_parity(producer_expected_golden)
    _structural_preflight(value, label="policy candidate", maximum_bytes=MAX_CATALOG_BYTES)
    original_raw = _canonical(value, label="policy candidate", maximum=MAX_CATALOG_BYTES)
    if len(original_raw) > TARGET_CATALOG_BYTES:
        _fail("policy candidate exceeds target byte budget")
    if golden is not None and (len(original_raw), _sha256(original_raw)) != golden:
        _fail("policy candidate does not match configured golden")
    _reject_prohibited_fields(value, label="policy candidate")

    axis_provider = (
        _default_capacity_axis_provider
        if capacity_axis_provider is None
        else capacity_axis_provider
    )
    graph_provider = (
        _default_fact_graph_provider
        if fact_graph_provider is None
        else fact_graph_provider
    )
    cell_provider = (
        capacity_axis.capacity_cell_body_bytes
        if capacity_cell_body_provider is None
        else capacity_cell_body_provider
    )
    if policy_body_provider is None:
        _fail("policy body provider is required")

    axis_value = _authenticate_capacity_axis(axis_provider)
    graph_values = _authenticate_fact_graphs(graph_provider)
    try:
        expected = _build_expected_candidate(
            axis_value,
            graph_values,
            capacity_cell_body_provider=cell_provider,
            policy_body_provider=policy_body_provider,
        )
    except PersonaV2CapacityFactTruthOccurrencePolicyValidationError:
        raise
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise PersonaV2CapacityFactTruthOccurrencePolicyValidationError(
            "upstream policy derivation structure is invalid"
        ) from error
    expected_raw = _canonical(
        expected, label="independently rebuilt policy candidate", maximum=MAX_CATALOG_BYTES
    )
    if not hmac.compare_digest(original_raw, expected_raw):
        _fail("policy candidate differs from independent reconstruction")

    postflight_raw = _canonical(value, label="policy candidate postflight", maximum=MAX_CATALOG_BYTES)
    if not hmac.compare_digest(original_raw, postflight_raw):
        _fail("caller-owned policy candidate changed during validation")
    return True


def validate_capacity_fact_truth_occurrence_policy_bytes(
    raw,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    capacity_axis_provider=None,
    fact_graph_provider=None,
    capacity_cell_body_provider=None,
    policy_body_provider=None,
):
    """Validate exact canonical raw bytes before opening any provider."""

    _require_producer_golden_parity(producer_expected_golden)
    value = _parse_json(raw, label="policy candidate", maximum=MAX_CATALOG_BYTES)
    return validate_capacity_fact_truth_occurrence_policy(
        value,
        producer_expected_golden=producer_expected_golden,
        capacity_axis_provider=capacity_axis_provider,
        fact_graph_provider=fact_graph_provider,
        capacity_cell_body_provider=capacity_cell_body_provider,
        policy_body_provider=policy_body_provider,
    )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit("import and call validate_capacity_fact_truth_occurrence_policy")
