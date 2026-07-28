"""Query-independent source-semantic capacity-axis catalog candidate.

This additive corpus-side candidate defines only the finite capacity lattice
described by the persona-PC source-semantic resolution v2 proposal.  Exact
cell rows live in twenty deterministic persona-sharded JSONL bodies; the
catalog embeds only their bounded receipts and the upstream axis table.

The catalog does not select or assign source slots, import query/oracle data,
issue namespace entries or final identifiers, materialize files, or grant G0
or execution authority.  Golden configuration and full/cold gate receipts are
external to the canonical body and cannot grant authority to it.
"""

from __future__ import annotations

import copy
import functools
import hashlib
import hmac
import json
import re
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_contract as envelope
    from . import persona_v2_fact_graph as fact_graph
    from . import persona_v2_source_semantic_membership_package as semantic_catalog
    from . import persona_v2_source_semantic_capacity_axis_catalog_validator as independent
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_contract as envelope
    import persona_v2_fact_graph as fact_graph
    import persona_v2_source_semantic_membership_package as semantic_catalog
    import persona_v2_source_semantic_capacity_axis_catalog_validator as independent


ARTIFACT_SCHEMA = "kio.persona.pc-source-semantic-capacity-axis-catalog/v1"
ARTIFACT_SCHEMA_VERSION = 1
ARTIFACT_KIND = "persona-pc-v2-source-semantic-capacity-axis-catalog-candidate"
FIXTURE_ID = "kio-persona-pc-v2"
FIXTURE_SCHEMA_VERSION = 2

MAX_CATALOG_BYTES = 2 * 2**20
TARGET_CATALOG_BYTES = 512 * 2**10
MAX_CELL_BODY_BYTES = 4 * 2**20
MAX_CELL_ROWS_PER_PERSONA = 4_096
MAX_CELL_ROW_BYTES_INCLUDING_LF = 1_024
MAX_CUMULATIVE_EXTERNAL_BODY_BYTES = 256 * 2**20
MAX_PREFLIGHT_NODE_COUNT = 100_000
MAX_PREFLIGHT_CONTAINER_ITEMS = 4_096

# Frozen after corrected full and two-seed cold gates; this pin grants no authority.
EXPECTED_CANONICAL_BYTES = 50_473
EXPECTED_SHA256 = "2bcb84e6ca46f09b29a3f4756191b98970a4f78101e4455675b6c713dc1cab85"

PERSONA_IDS = tuple(f"p{ordinal:02d}" for ordinal in range(1, 21))
TOPIC_SLOT_ORDER = ("g01", "g02", "g03", "g04")
TOPIC_COUNT_PER_PERSONA = 4
FACT_COUNT_PER_TOPIC = 9
REPLICA_COUNT_PER_FACT_CELL = 11
EXPECTED_PERSONA_LANGUAGE_PAIR_COUNT = 38
EXPECTED_CAPACITY_CELL_COUNT = 15_048

CELL_DOMAIN_LABEL = "kio/persona-pc-v2/source-semantic-capacity-cell/v1"
CELL_LOGICAL_KEY_FIELDS = (
    "persona_id",
    "topic_id",
    "language",
    "fact_id",
    "replica_ordinal",
)
CELL_ROW_FIELDS = frozenset(("capacity_cell_id", *CELL_LOGICAL_KEY_FIELDS))

SEMANTIC_CATALOG_PIN = (
    "persona-pc-v2-source-semantic-membership-catalog",
    "kio.persona.pc-source-semantic-membership-catalog/v2",
    2,
    436_495,
    "d54ad435447a6b7adf87c0190bd8ed452caa3015b82ac18da1c81825efeba63b",
)

# These exact leaf pins are already committed by the frozen semantic catalog.
FACT_GRAPH_PINS = (
    ("p01", 26_403, "94ab0655788534db4e784709a044fda2cdbeb69775082354b900068e8cbcd70d"),
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
        "authorizes_capacity_membership",
        "authorizes_evaluation_execution",
        "authorizes_final_identifier_assignment",
        "authorizes_g0_freeze",
        "authorizes_history_mutation",
        "authorizes_kio_execution",
        "authorizes_namespace_issuance",
        "authorizes_physical_write",
        "authorizes_query_rendering",
        "authorizes_render_or_materialization",
        "authorizes_solver_execution",
        "authorizes_source_plan",
        "authorizes_source_slot_assignment",
    }
)

_LOWER_ASCII_ID = re.compile(r"^[a-z][a-z0-9-]*$")


class PersonaV2SourceSemanticCapacityAxisCatalogError(ValueError):
    """Raised when the capacity-axis candidate is not exact."""


def _fail(message):
    raise PersonaV2SourceSemanticCapacityAxisCatalogError(message)


def _sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def _expected_golden():
    byte_count_set = EXPECTED_CANONICAL_BYTES is not None
    digest_set = EXPECTED_SHA256 is not None
    if byte_count_set != digest_set:
        _fail("capacity-axis golden must be entirely unset or entirely set")
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
        _fail("capacity-axis golden configuration is invalid")
    return EXPECTED_CANONICAL_BYTES, EXPECTED_SHA256


def _require_golden_parity():
    """Cross-check both trust sides before opening any dependency/provider."""

    producer_expected = _expected_golden()
    try:
        validator_expected = independent._expected_golden()
    except Exception as error:
        raise PersonaV2SourceSemanticCapacityAxisCatalogError(
            "validator capacity-axis golden configuration is invalid"
        ) from error
    if type(producer_expected) is not type(validator_expected):
        _fail("producer and validator capacity-axis goldens differ")
    if producer_expected is not None and (
        type(producer_expected) is not tuple
        or len(producer_expected) != 2
        or producer_expected != validator_expected
    ):
        _fail("producer and validator capacity-axis goldens differ")
    return producer_expected


def _bounded_utf8_length(value, *, label):
    """Count UTF-8 bytes without normalizing or invoking an encoder."""

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
    """Bound structure and reject aliases/cycles before normalization/copy."""

    if type(label) is not str or not label:
        _fail("preflight label must be a non-empty exact string")
    if type(maximum_bytes) is not int or maximum_bytes <= 0:
        _fail("preflight byte bound must be a positive exact integer")
    stack = [(value, 0)]
    seen_containers = set()
    node_count = 0
    expanded_upper_bound = 0
    while stack:
        current, depth = stack.pop()
        node_count += 1
        if node_count > MAX_PREFLIGHT_NODE_COUNT:
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
            # Check both codepoints and bytes before NFC or UTF-8 encoding.
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
    except artifact_common.PersonaV2ArtifactError as error:
        _fail(str(error))


def _require_expected_raw(raw):
    if type(raw) is not bytes or len(raw) > MAX_CATALOG_BYTES:
        _fail("capacity-axis candidate is not bounded exact bytes")
    expected = _expected_golden()
    if expected is not None and (
        len(raw) != expected[0]
        or not hmac.compare_digest(_sha256(raw), expected[1])
    ):
        _fail("capacity-axis candidate differs from its frozen golden")
    return raw


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


def _require_lower_ascii(value, *, label):
    if type(value) is not str:
        _fail(f"{label} must be a lowercase ASCII stable ID")
    if len(value) > artifact_common.MAX_CANONICAL_STRING_BYTES:
        _fail(f"{label} exceeds its codepoint bound")
    _bounded_utf8_length(value, label=label)
    if (
        unicodedata.normalize("NFC", value) != value
        or _LOWER_ASCII_ID.fullmatch(value) is None
    ):
        _fail(f"{label} must be a lowercase ASCII stable ID")
    return value


def _require_constant_alignment():
    if tuple(envelope.PERSONA_IDS) != PERSONA_IDS:
        _fail("persona order drifted")
    if tuple(semantic_catalog.TOPIC_SLOT_ORDER) != TOPIC_SLOT_ORDER:
        _fail("semantic topic-slot order drifted")
    if (
        semantic_catalog.CATALOG_ARTIFACT_KIND != SEMANTIC_CATALOG_PIN[0]
        or semantic_catalog.CATALOG_ARTIFACT_SCHEMA != SEMANTIC_CATALOG_PIN[1]
        or semantic_catalog.ARTIFACT_SCHEMA_VERSION != SEMANTIC_CATALOG_PIN[2]
    ):
        _fail("semantic catalog identity constants drifted")
    if fact_graph.FACT_COUNT_PER_GRAPH != FACT_COUNT_PER_TOPIC:
        _fail("fact count per graph drifted")


def _fact_graph_binding(persona_id, byte_count, digest, *, body_opened=True):
    return {
        "artifact_kind": fact_graph.ARTIFACT_KIND,
        "artifact_schema": fact_graph.ARTIFACT_SCHEMA,
        "artifact_schema_version": fact_graph.ARTIFACT_SCHEMA_VERSION,
        "body_opened_for_axis_derivation": body_opened,
        "canonical_bytes": byte_count,
        "dependency_role": "eligible-language-and-nine-fact-axis-owner",
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "name": "persona-v2-fact-graph",
        "persona_id": persona_id,
        "sha256": digest,
    }


def _semantic_catalog_binding():
    kind, schema, version, byte_count, digest = SEMANTIC_CATALOG_PIN
    return {
        "artifact_kind": kind,
        "artifact_schema": schema,
        "artifact_schema_version": version,
        "body_opened_for_axis_derivation": False,
        "canonical_bytes": byte_count,
        "dependency_role": "frozen-semantic-topic-id-owner-pin",
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "name": "persona-v2-source-semantic-membership-catalog",
        "sha256": digest,
    }


def _snapshot_fact_graphs(values):
    if type(values) is not list or len(values) != len(PERSONA_IDS):
        _fail("fact-graph suite must contain exactly twenty leaves")
    snapshots = []
    bindings = []
    for value, (persona_id, byte_count, digest) in zip(
        values, FACT_GRAPH_PINS, strict=True
    ):
        if type(value) is not dict:
            _fail("fact-graph leaf must be an exact object")
        _structural_preflight(
            value,
            label=f"{persona_id} fact-graph opening",
            maximum_bytes=fact_graph.MAX_FACT_GRAPH_BYTES,
        )
        try:
            raw = fact_graph.canonical_json_bytes(value)
        except Exception as error:
            _fail(f"{persona_id} fact-graph canonicalization failed: {type(error).__name__}")
        if len(raw) != byte_count or not hmac.compare_digest(_sha256(raw), digest):
            _fail(f"{persona_id} fact-graph pin drifted")
        if (
            value.get("artifact_kind") != fact_graph.ARTIFACT_KIND
            or value.get("artifact_schema") != fact_graph.ARTIFACT_SCHEMA
            or value.get("artifact_schema_version") != fact_graph.ARTIFACT_SCHEMA_VERSION
            or value.get("fixture_id") != FIXTURE_ID
            or value.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
            or value.get("persona_id") != persona_id
            or value.get("g0_contract_frozen") is not False
        ):
            _fail(f"{persona_id} fact-graph identity drifted")
        authority = value.get("authority")
        if (
            type(authority) is not dict
            or not authority
            or any(type(flag) is not bool or flag is not False for flag in authority.values())
        ):
            _fail(f"{persona_id} fact-graph gained authority")
        snapshots.append(json.loads(raw.decode("utf-8", "strict")))
        bindings.append(_fact_graph_binding(persona_id, byte_count, digest))
    return snapshots, bindings


def _topic_id(persona_id, topic_slot):
    expected = f"{persona_id}-semantic-topic-{topic_slot}-v2"
    try:
        actual = semantic_catalog.semantic_topic_id(persona_id, topic_slot)
    except Exception as error:
        _fail(f"semantic topic ID derivation failed: {type(error).__name__}")
    if actual != expected:
        _fail("semantic topic ID rule drifted")
    return expected


def _persona_axis(graph_value):
    persona_id = graph_value["persona_id"]
    languages = graph_value.get("eligible_languages")
    if (
        type(languages) is not list
        or not languages
        or len(languages) != len(set(languages))
    ):
        _fail(f"{persona_id} eligible languages are invalid")
    for language in languages:
        _require_lower_ascii(language, label=f"{persona_id} language")

    graphs = graph_value.get("graphs")
    if type(graphs) is not list or len(graphs) != TOPIC_COUNT_PER_PERSONA:
        _fail(f"{persona_id} must contain exactly four graphs")
    graphs = sorted(graphs, key=lambda row: row.get("graph_id", "").encode("ascii", "strict"))
    topics = []
    seen_facts = set()
    for topic_slot, graph in zip(TOPIC_SLOT_ORDER, graphs, strict=True):
        graph_id = _require_lower_ascii(graph.get("graph_id"), label="graph ID")
        facts = graph.get("facts")
        if type(facts) is not list or len(facts) != FACT_COUNT_PER_TOPIC:
            _fail(f"{persona_id}/{graph_id} must contain exactly nine facts")
        fact_ids = sorted(
            (_require_lower_ascii(row.get("fact_id"), label="fact ID") for row in facts),
            key=lambda value: value.encode("ascii"),
        )
        if len(fact_ids) != len(set(fact_ids)) or seen_facts.intersection(fact_ids):
            _fail(f"{persona_id} fact IDs are not graph-disjoint")
        seen_facts.update(fact_ids)
        topics.append(
            {
                "fact_count": FACT_COUNT_PER_TOPIC,
                "fact_ids": fact_ids,
                "graph_id": graph_id,
                "topic_id": _topic_id(persona_id, topic_slot),
                "topic_slot": topic_slot,
            }
        )
    cell_count = (
        len(topics)
        * len(languages)
        * FACT_COUNT_PER_TOPIC
        * REPLICA_COUNT_PER_FACT_CELL
    )
    return {
        "capacity_cell_count": cell_count,
        "eligible_language_count": len(languages),
        "eligible_languages": list(languages),
        "fact_count_per_topic": FACT_COUNT_PER_TOPIC,
        "persona_id": persona_id,
        "persona_language_pair_count": len(languages),
        "replica_count_per_fact_cell": REPLICA_COUNT_PER_FACT_CELL,
        "topic_count": len(topics),
        "topics": topics,
    }


def capacity_cell_id(persona_id, topic_id, language, fact_id, replica_ordinal):
    """Return the full domain-separated ID for one exact logical cell tuple."""

    for label, value in (
        ("persona ID", persona_id),
        ("topic ID", topic_id),
        ("language", language),
        ("fact ID", fact_id),
    ):
        _require_lower_ascii(value, label=label)
    if (
        type(replica_ordinal) is not int
        or type(replica_ordinal) is bool
        or not 1 <= replica_ordinal <= REPLICA_COUNT_PER_FACT_CELL
    ):
        _fail("replica ordinal must be an exact integer in 1..11")
    preimage = _canonical(
        [persona_id, topic_id, language, fact_id, replica_ordinal],
        label="capacity-cell logical key",
        maximum=4 * 1024,
    )
    return _sha256(CELL_DOMAIN_LABEL.encode("ascii") + b"\x00" + preimage)


def _cell_rows(axis):
    rows = []
    for topic in axis["topics"]:
        for language in axis["eligible_languages"]:
            for fact_id in topic["fact_ids"]:
                for replica_ordinal in range(1, REPLICA_COUNT_PER_FACT_CELL + 1):
                    row = {
                        "capacity_cell_id": capacity_cell_id(
                            axis["persona_id"],
                            topic["topic_id"],
                            language,
                            fact_id,
                            replica_ordinal,
                        ),
                        "fact_id": fact_id,
                        "language": language,
                        "persona_id": axis["persona_id"],
                        "replica_ordinal": replica_ordinal,
                        "topic_id": topic["topic_id"],
                    }
                    if set(row) != CELL_ROW_FIELDS:
                        _fail("capacity-cell row schema drifted")
                    rows.append(row)
    rows.sort(key=lambda row: row["capacity_cell_id"].encode("ascii"))
    if len(rows) != axis["capacity_cell_count"]:
        _fail("persona capacity-cell count drifted")
    return rows


def _jsonl(rows, *, persona_id):
    if type(rows) is not list or not 1 <= len(rows) <= MAX_CELL_ROWS_PER_PERSONA:
        _fail(f"{persona_id} capacity-cell row count exceeds its bound")
    parts = []
    maximum = 0
    for row in rows:
        raw = _canonical(
            row,
            label=f"{persona_id} capacity-cell row",
            maximum=MAX_CELL_ROW_BYTES_INCLUDING_LF,
        ) + b"\n"
        if len(raw) > MAX_CELL_ROW_BYTES_INCLUDING_LF:
            _fail(f"{persona_id} capacity-cell row exceeds its byte cap")
        maximum = max(maximum, len(raw))
        parts.append(raw)
    body = b"".join(parts)
    if len(body) > MAX_CELL_BODY_BYTES:
        _fail(f"{persona_id} capacity-cell body exceeds its byte cap")
    return body, maximum


def _body_descriptor(persona_id, rows, body, maximum_row_bytes):
    return {
        "body_bytes": len(body),
        "body_framing": "canonical-jsonl-one-object-per-line-lf-terminated",
        "body_sha256": _sha256(body),
        "file_name": f"{persona_id}-source-semantic-capacity-cells-v1.jsonl",
        "first_capacity_cell_id": rows[0]["capacity_cell_id"],
        "last_capacity_cell_id": rows[-1]["capacity_cell_id"],
        "maximum_row_bytes_including_lf": maximum_row_bytes,
        "ordering": "full-capacity-cell-id-lower-hex-ascii-ascending",
        "row_count": len(rows),
    }


def _build_state():
    _require_golden_parity()
    _require_constant_alignment()
    graph_values = fact_graph.build_fact_graph_suite()
    graph_snapshots, graph_bindings = _snapshot_fact_graphs(graph_values)
    axes = [_persona_axis(value) for value in graph_snapshots]
    if [row["persona_id"] for row in axes] != list(PERSONA_IDS):
        _fail("capacity-axis persona order drifted")

    all_cell_ids = set()
    bodies = {}
    rows_by_persona = {}
    cumulative_body_bytes = 0
    maximum_row_bytes = 0
    for axis in axes:
        rows = _cell_rows(axis)
        cell_ids = {row["capacity_cell_id"] for row in rows}
        if len(cell_ids) != len(rows) or all_cell_ids.intersection(cell_ids):
            _fail("capacity-cell ID collision detected")
        all_cell_ids.update(cell_ids)
        body, row_maximum = _jsonl(rows, persona_id=axis["persona_id"])
        axis["capacity_cell_body"] = _body_descriptor(
            axis["persona_id"], rows, body, row_maximum
        )
        bodies[axis["persona_id"]] = body
        rows_by_persona[axis["persona_id"]] = rows
        cumulative_body_bytes += len(body)
        maximum_row_bytes = max(maximum_row_bytes, row_maximum)

    language_pair_count = sum(row["eligible_language_count"] for row in axes)
    capacity_cell_count = sum(row["capacity_cell_count"] for row in axes)
    if language_pair_count != EXPECTED_PERSONA_LANGUAGE_PAIR_COUNT:
        _fail("eligible persona-language pair count drifted")
    if capacity_cell_count != EXPECTED_CAPACITY_CELL_COUNT:
        _fail("suite capacity-cell count drifted")
    if len(all_cell_ids) != EXPECTED_CAPACITY_CELL_COUNT:
        _fail("suite capacity-cell collision proof drifted")
    if cumulative_body_bytes > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES:
        _fail("capacity-cell bodies exceed their cumulative cap")

    input_bindings = [_semantic_catalog_binding(), *graph_bindings]
    catalog = {
        "artifact_kind": ARTIFACT_KIND,
        "artifact_schema": ARTIFACT_SCHEMA,
        "artifact_schema_version": ARTIFACT_SCHEMA_VERSION,
        "authority": _negative_authority(),
        "axis_contract": {
            "capacity_cell_domain_label": CELL_DOMAIN_LABEL,
            "capacity_cell_id_digest": "sha256-full-64-lowercase-hex",
            "capacity_cell_id_framing": "ASCII(domain-label)-NUL-UTF8(canonical-json-array(logical-key))",
            "capacity_cell_logical_key_fields": list(CELL_LOGICAL_KEY_FIELDS),
            "fact_count_per_topic": FACT_COUNT_PER_TOPIC,
            "replica_count_per_fact_cell": REPLICA_COUNT_PER_FACT_CELL,
            "replica_ordinal_type_and_range": "integer-1-through-11-inclusive",
            "topic_count_per_persona": TOPIC_COUNT_PER_PERSONA,
        },
        "canonical_limits": {
            "cumulative_external_body_bytes": cumulative_body_bytes,
            "external_bodies_embedded": False,
            "max_catalog_bytes": MAX_CATALOG_BYTES,
            "max_cell_body_bytes": MAX_CELL_BODY_BYTES,
            "max_cell_row_bytes_including_lf": MAX_CELL_ROW_BYTES_INCLUDING_LF,
            "max_cell_rows_per_persona": MAX_CELL_ROWS_PER_PERSONA,
            "max_cumulative_external_body_bytes": MAX_CUMULATIVE_EXTERNAL_BODY_BYTES,
            "max_nesting_depth": artifact_common.MAX_CANONICAL_DEPTH,
            "max_string_bytes": artifact_common.MAX_CANONICAL_STRING_BYTES,
            "self_hash_embedded": False,
            "unicode_normalization": "NFC",
        },
        "candidate_status": "proposal-non-authorizing-not-issued",
        "completion_claims": {
            "all_capacity_cell_bodies_bound_by_receipt": True,
            "all_capacity_cell_ids_collision_free": True,
            "all_persona_axis_counts_exact": True,
            "capacity_axis_catalog_candidate_complete": True,
            "capacity_membership_available": False,
            "capacity_source_assignment_available": False,
            "cell_to_source_bijection_proved": False,
            "full_dependency_body_replay_receipt_bound": False,
            "namespace_v4_issued": False,
            "semantic_catalog_body_reauthentication_receipt_bound": False,
            "two_hash_seed_cold_build_receipt_bound": False,
        },
        "completion_scope": (
            "query-independent-capacity-axis-lattice-candidate-only-no-source-slot-"
            "membership-no-assignment-no-namespace-no-execution-no-g0"
        ),
        "dependency_direction_contract": {
            "capacity_axis_may_bind_evaluation_owner": False,
            "fact_graphs_are_strictly_upstream": True,
            "future_capacity_membership_must_bind_this_catalog": True,
            "semantic_topic_identity_owner_is_pin_bound": True,
        },
        "dependency_exclusion_contract": {
            "answer_or_relevance_input_count": 0,
            "evaluation_side_input_count": 0,
            "oracle_input_count": 0,
            "query_input_count": 0,
            "runtime_clock_network_randomness_or_environment_input_count": 0,
        },
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "g0_contract_frozen": False,
        "hypothesis_status": "proposal-only-non-authorizing-synthetic-capacity-design",
        "input_binding_order": [row["name"] + (f"/{row['persona_id']}" if "persona_id" in row else "") for row in input_bindings],
        "input_bindings": input_bindings,
        "orders": {
            "capacity_cell_body": "full-capacity-cell-id-lower-hex-ascii-ascending",
            "fact_ids": "lowercase-ascii-ascending-within-topic",
            "persona": list(PERSONA_IDS),
            "replica_ordinal": "integer-ascending-1-through-11-before-cell-id-sort",
            "topic_slot": list(TOPIC_SLOT_ORDER),
        },
        "personas": axes,
        "proposal_only": True,
        "remaining_blockers": [
            "capacity-membership-origin-profile-suite-not-issued",
            "eligible-residual-source-set-and-headroom-not-bound-by-this-axis-catalog",
            "i5-support-mirror-reconciliation-v2-not-issued",
            "query-history-source-semantic-resolution-v2-not-issued",
            "complete-inventory-successor-and-corpus-namespace-v4-not-issued",
            "full-and-two-seed-cold-replay-evidence-external-not-bound",
            "positive-independent-issuance-review-not-present",
        ],
        "summary": {
            "capacity_cell_count": capacity_cell_count,
            "capacity_cell_id_collision_count": 0,
            "eligible_persona_language_pair_count": language_pair_count,
            "external_capacity_cell_body_bytes": cumulative_body_bytes,
            "fact_count_per_topic": FACT_COUNT_PER_TOPIC,
            "fact_reference_axis_count": len(PERSONA_IDS) * TOPIC_COUNT_PER_PERSONA * FACT_COUNT_PER_TOPIC,
            "maximum_cell_row_bytes_including_lf": maximum_row_bytes,
            "maximum_persona_capacity_cell_count": max(row["capacity_cell_count"] for row in axes),
            "minimum_persona_capacity_cell_count": min(row["capacity_cell_count"] for row in axes),
            "persona_count": len(PERSONA_IDS),
            "persona_shard_count": len(bodies),
            "replica_count_per_fact_cell": REPLICA_COUNT_PER_FACT_CELL,
            "source_slot_assignment_count": 0,
            "topic_count": len(PERSONA_IDS) * TOPIC_COUNT_PER_PERSONA,
            "topic_count_per_persona": TOPIC_COUNT_PER_PERSONA,
        },
        "semantic_catalog_trust_root": {
            "body_opened_in_fast_candidate_build": False,
            "body_required_for_full_acceptance": True,
            "frozen_pin_is_not_live_body_validation": True,
            "missing_or_mismatched_body_fails_full_acceptance": True,
            "opening_mode": "frozen-pin-only-fast-candidate",
        },
    }
    raw = _canonical(catalog, label="source-semantic capacity-axis catalog", maximum=MAX_CATALOG_BYTES)
    _require_expected_raw(raw)
    return catalog, bodies, rows_by_persona


@functools.lru_cache(maxsize=1)
def _canonical_state():
    return _build_state()


def build_source_semantic_capacity_axis_catalog():
    """Return a detached compact catalog candidate."""

    _require_golden_parity()
    catalog = _canonical_state()[0]
    _structural_preflight(
        catalog,
        label="cached capacity-axis catalog before detached copy",
        maximum_bytes=MAX_CATALOG_BYTES,
    )
    return copy.deepcopy(catalog)


def build_capacity_cell_rows(persona_id):
    _require_golden_parity()
    if type(persona_id) is not str or persona_id not in PERSONA_IDS:
        _fail("unknown persona ID")
    rows = _canonical_state()[2][persona_id]
    _structural_preflight(
        rows,
        label=f"cached {persona_id} capacity-cell rows before detached copy",
        maximum_bytes=MAX_CELL_BODY_BYTES,
    )
    return copy.deepcopy(rows)


def capacity_cell_body_bytes(persona_id):
    _require_golden_parity()
    if type(persona_id) is not str or persona_id not in PERSONA_IDS:
        _fail("unknown persona ID")
    return bytes(_canonical_state()[1][persona_id])


def canonical_json_bytes(value):
    _require_golden_parity()
    raw = _canonical(
        value,
        label="source-semantic capacity-axis catalog",
        maximum=MAX_CATALOG_BYTES,
    )
    return _require_expected_raw(raw)


def validate_source_semantic_capacity_axis_catalog(value):
    _require_golden_parity()
    if canonical_json_bytes(value) != canonical_json_bytes(
        build_source_semantic_capacity_axis_catalog()
    ):
        _fail("capacity-axis catalog differs from exact regeneration")
    return True


def source_semantic_capacity_axis_catalog_sha256(value=None):
    _require_golden_parity()
    if value is None:
        value = build_source_semantic_capacity_axis_catalog()
    opening_raw = canonical_json_bytes(value)
    opening_snapshot = json.loads(opening_raw.decode("utf-8", "strict"))
    try:
        validate_source_semantic_capacity_axis_catalog(opening_snapshot)
        digest = _sha256(canonical_json_bytes(opening_snapshot))
    finally:
        _structural_preflight(
            value,
            label="caller-owned capacity-axis catalog hash postflight",
            maximum_bytes=MAX_CATALOG_BYTES,
        )
        if canonical_json_bytes(value) != opening_raw:
            _fail("caller-owned capacity-axis catalog changed during hashing")
    return digest


def require_issued_source_semantic_capacity_axis_catalog():
    _fail(
        "capacity-axis catalog is proposal-only and remains unissued until full, "
        "two-seed cold replay, positive review, and a separate issuance decision"
    )


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "CELL_DOMAIN_LABEL",
    "CELL_LOGICAL_KEY_FIELDS",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "FACT_COUNT_PER_TOPIC",
    "MAX_CATALOG_BYTES",
    "MAX_CELL_BODY_BYTES",
    "MAX_CELL_ROW_BYTES_INCLUDING_LF",
    "MAX_CELL_ROWS_PER_PERSONA",
    "MAX_CUMULATIVE_EXTERNAL_BODY_BYTES",
    "PERSONA_IDS",
    "REPLICA_COUNT_PER_FACT_CELL",
    "TOPIC_COUNT_PER_PERSONA",
    "PersonaV2SourceSemanticCapacityAxisCatalogError",
    "build_capacity_cell_rows",
    "build_source_semantic_capacity_axis_catalog",
    "canonical_json_bytes",
    "capacity_cell_body_bytes",
    "capacity_cell_id",
    "require_issued_source_semantic_capacity_axis_catalog",
    "source_semantic_capacity_axis_catalog_sha256",
    "validate_source_semantic_capacity_axis_catalog",
]
