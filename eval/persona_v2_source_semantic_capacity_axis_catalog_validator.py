"""Producer-independent validation for the capacity-axis catalog candidate.

The validator does not import the sibling producer.  It authenticates the
twenty frozen fact-graph leaves, independently derives all axes and cell IDs,
replays each persona body provider twice, and postflight-reauthenticates every
caller-owned object.  Acceptance remains proposal/candidate evidence only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import unicodedata

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
    from . import persona_v2_fact_graph as fact_graph
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common
    import persona_v2_fact_graph as fact_graph


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

# Must remain byte-identical to the non-authorizing producer golden.
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


class PersonaV2SourceSemanticCapacityAxisCatalogValidationError(ValueError):
    """Raised when independent validation fails closed."""


def _fail(message):
    raise PersonaV2SourceSemanticCapacityAxisCatalogValidationError(message)


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


_GOLDEN_NOT_PROVIDED = object()


def _require_producer_golden_parity(producer_expected):
    """Require the producer pair before opening dependencies or providers."""

    validator_expected = _expected_golden()
    if producer_expected is _GOLDEN_NOT_PROVIDED:
        _fail("producer capacity-axis golden was not supplied")
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
        _fail("producer capacity-axis golden is invalid")
    if type(producer_expected) is not type(validator_expected):
        _fail("producer and validator capacity-axis goldens differ")
    if producer_expected is not None and producer_expected != validator_expected:
        _fail("producer and validator capacity-axis goldens differ")
    return validator_expected


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
    """Reject resource bombs, repeated containers, and cycles before encoding."""

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
            # Codepoints and bytes are bounded before normalization or UTF-8.
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


def _snapshot(value, *, label, maximum):
    raw = _canonical(value, label=label, maximum=maximum)
    try:
        snapshot = json.loads(raw.decode("utf-8", "strict"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"{label} snapshot failed: {type(error).__name__}")
    return snapshot, raw


def _require_static_candidate(snapshot):
    """Reject authority/schema/trust-root drift before any body callback."""

    if (
        type(snapshot) is not dict
        or snapshot.get("artifact_kind") != ARTIFACT_KIND
        or snapshot.get("artifact_schema") != ARTIFACT_SCHEMA
        or snapshot.get("artifact_schema_version") != ARTIFACT_SCHEMA_VERSION
        or snapshot.get("fixture_id") != FIXTURE_ID
        or snapshot.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or snapshot.get("candidate_status") != "proposal-non-authorizing-not-issued"
        or snapshot.get("proposal_only") is not True
        or snapshot.get("g0_contract_frozen") is not False
    ):
        _fail("capacity-axis candidate static identity drifted")
    authority = snapshot.get("authority")
    if authority != _negative_authority() or any(
        type(flag) is not bool or flag is not False
        for flag in (authority or {}).values()
    ):
        _fail("capacity-axis candidate authority must be exact all-false")
    limits = snapshot.get("canonical_limits")
    if type(limits) is not dict or limits.get("external_bodies_embedded") is not False:
        _fail("capacity-axis candidate external-body boundary drifted")
    exclusions = snapshot.get("dependency_exclusion_contract")
    if type(exclusions) is not dict or not exclusions or any(
        type(count) is not int or type(count) is bool or count != 0
        for count in exclusions.values()
    ):
        _fail("capacity-axis candidate dependency exclusion proof drifted")
    claims = snapshot.get("completion_claims")
    if type(claims) is not dict or any(
        claims.get(field) is not False
        for field in (
            "capacity_membership_available",
            "capacity_source_assignment_available",
            "cell_to_source_bijection_proved",
            "full_dependency_body_replay_receipt_bound",
            "namespace_v4_issued",
            "semantic_catalog_body_reauthentication_receipt_bound",
            "two_hash_seed_cold_build_receipt_bound",
        )
    ):
        _fail("capacity-axis candidate downstream completion boundary drifted")
    trust = snapshot.get("semantic_catalog_trust_root")
    if trust != {
        "body_opened_in_fast_candidate_build": False,
        "body_required_for_full_acceptance": True,
        "frozen_pin_is_not_live_body_validation": True,
        "missing_or_mismatched_body_fails_full_acceptance": True,
        "opening_mode": "frozen-pin-only-fast-candidate",
    }:
        _fail("semantic catalog trust-root semantics drifted")


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


def _negative_authority():
    return {field: False for field in sorted(AUTHORITY_FIELDS)}


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


def _fact_graph_binding(persona_id, byte_count, digest):
    return {
        "artifact_kind": "persona-pc-v2-fact-graph",
        "artifact_schema": "kio.persona.pc-fact-graph/v2",
        "artifact_schema_version": 2,
        "body_opened_for_axis_derivation": True,
        "canonical_bytes": byte_count,
        "dependency_role": "eligible-language-and-nine-fact-axis-owner",
        "fixture_id": FIXTURE_ID,
        "fixture_schema_version": FIXTURE_SCHEMA_VERSION,
        "name": "persona-v2-fact-graph",
        "persona_id": persona_id,
        "sha256": digest,
    }


def _snapshot_fact_graphs(values):
    if type(values) is not list or len(values) != len(PERSONA_IDS):
        _fail("fact-graph suite must contain exactly twenty leaves")
    snapshots = []
    raws = []
    bindings = []
    for value, (persona_id, byte_count, digest) in zip(
        values, FACT_GRAPH_PINS, strict=True
    ):
        snapshot, raw = _snapshot(
            value, label=f"{persona_id} fact graph", maximum=1 * 2**20
        )
        if len(raw) != byte_count or not hmac.compare_digest(_sha256(raw), digest):
            _fail(f"{persona_id} fact-graph pin drifted")
        if (
            snapshot.get("artifact_kind") != "persona-pc-v2-fact-graph"
            or snapshot.get("artifact_schema") != "kio.persona.pc-fact-graph/v2"
            or snapshot.get("artifact_schema_version") != 2
            or snapshot.get("fixture_id") != FIXTURE_ID
            or snapshot.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
            or snapshot.get("persona_id") != persona_id
            or snapshot.get("g0_contract_frozen") is not False
        ):
            _fail(f"{persona_id} fact-graph identity drifted")
        authority = snapshot.get("authority")
        if (
            type(authority) is not dict
            or not authority
            or any(type(flag) is not bool or flag is not False for flag in authority.values())
        ):
            _fail(f"{persona_id} fact-graph gained authority")
        snapshots.append(snapshot)
        raws.append(raw)
        bindings.append(_fact_graph_binding(persona_id, byte_count, digest))
    return snapshots, tuple(raws), bindings


def _capacity_cell_id(persona_id, topic_id, language, fact_id, replica_ordinal):
    logical_key = [persona_id, topic_id, language, fact_id, replica_ordinal]
    preimage = _canonical(
        logical_key, label="independent capacity-cell logical key", maximum=4 * 1024
    )
    return _sha256(CELL_DOMAIN_LABEL.encode("ascii") + b"\x00" + preimage)


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
    try:
        graphs = sorted(graphs, key=lambda row: row["graph_id"].encode("ascii", "strict"))
    except (KeyError, UnicodeEncodeError, AttributeError):
        _fail(f"{persona_id} graph IDs are invalid")
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
                "topic_id": f"{persona_id}-semantic-topic-{topic_slot}-v2",
                "topic_slot": topic_slot,
            }
        )
    cell_count = len(languages) * 4 * 9 * 11
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


def _cell_rows(axis):
    rows = []
    for topic in axis["topics"]:
        for language in axis["eligible_languages"]:
            for fact_id in topic["fact_ids"]:
                for replica_ordinal in range(1, 12):
                    row = {
                        "capacity_cell_id": _capacity_cell_id(
                            axis["persona_id"], topic["topic_id"], language,
                            fact_id, replica_ordinal,
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
    if not 1 <= len(rows) <= MAX_CELL_ROWS_PER_PERSONA:
        _fail(f"{persona_id} capacity-cell row count exceeds its bound")
    parts = []
    maximum = 0
    for row in rows:
        raw = _canonical(
            row, label=f"{persona_id} independent capacity-cell row",
            maximum=MAX_CELL_ROW_BYTES_INCLUDING_LF,
        ) + b"\n"
        if len(raw) > MAX_CELL_ROW_BYTES_INCLUDING_LF:
            _fail(f"{persona_id} capacity-cell row exceeds its byte cap")
        parts.append(raw)
        maximum = max(maximum, len(raw))
    body = b"".join(parts)
    if len(body) > MAX_CELL_BODY_BYTES:
        _fail(f"{persona_id} capacity-cell body exceeds its byte cap")
    return body, maximum


def _descriptor(persona_id, rows, body, maximum):
    return {
        "body_bytes": len(body),
        "body_framing": "canonical-jsonl-one-object-per-line-lf-terminated",
        "body_sha256": _sha256(body),
        "file_name": f"{persona_id}-source-semantic-capacity-cells-v1.jsonl",
        "first_capacity_cell_id": rows[0]["capacity_cell_id"],
        "last_capacity_cell_id": rows[-1]["capacity_cell_id"],
        "maximum_row_bytes_including_lf": maximum,
        "ordering": "full-capacity-cell-id-lower-hex-ascii-ascending",
        "row_count": len(rows),
    }


def _expected_state(graph_snapshots, graph_bindings):
    axes = [_persona_axis(value) for value in graph_snapshots]
    if [row["persona_id"] for row in axes] != list(PERSONA_IDS):
        _fail("capacity-axis persona order drifted")
    bodies = {}
    all_cell_ids = set()
    cumulative = 0
    maximum_row = 0
    for axis in axes:
        rows = _cell_rows(axis)
        cell_ids = {row["capacity_cell_id"] for row in rows}
        if len(cell_ids) != len(rows) or all_cell_ids.intersection(cell_ids):
            _fail("capacity-cell ID collision detected")
        all_cell_ids.update(cell_ids)
        body, row_maximum = _jsonl(rows, persona_id=axis["persona_id"])
        axis["capacity_cell_body"] = _descriptor(
            axis["persona_id"], rows, body, row_maximum
        )
        bodies[axis["persona_id"]] = body
        cumulative += len(body)
        maximum_row = max(maximum_row, row_maximum)
    pair_count = sum(row["eligible_language_count"] for row in axes)
    cell_count = sum(row["capacity_cell_count"] for row in axes)
    if (
        pair_count != EXPECTED_PERSONA_LANGUAGE_PAIR_COUNT
        or cell_count != EXPECTED_CAPACITY_CELL_COUNT
        or len(all_cell_ids) != EXPECTED_CAPACITY_CELL_COUNT
        or cumulative > MAX_CUMULATIVE_EXTERNAL_BODY_BYTES
    ):
        _fail("suite capacity-axis aggregate drifted")
    input_bindings = [_semantic_catalog_binding(), *graph_bindings]
    expected = {
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
            "cumulative_external_body_bytes": cumulative,
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
        "completion_scope": "query-independent-capacity-axis-lattice-candidate-only-no-source-slot-membership-no-assignment-no-namespace-no-execution-no-g0",
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
            "capacity_cell_count": cell_count,
            "capacity_cell_id_collision_count": 0,
            "eligible_persona_language_pair_count": pair_count,
            "external_capacity_cell_body_bytes": cumulative,
            "fact_count_per_topic": FACT_COUNT_PER_TOPIC,
            "fact_reference_axis_count": 20 * 4 * 9,
            "maximum_cell_row_bytes_including_lf": maximum_row,
            "maximum_persona_capacity_cell_count": max(row["capacity_cell_count"] for row in axes),
            "minimum_persona_capacity_cell_count": min(row["capacity_cell_count"] for row in axes),
            "persona_count": 20,
            "persona_shard_count": 20,
            "replica_count_per_fact_cell": 11,
            "source_slot_assignment_count": 0,
            "topic_count": 80,
            "topic_count_per_persona": 4,
        },
        "semantic_catalog_trust_root": {
            "body_opened_in_fast_candidate_build": False,
            "body_required_for_full_acceptance": True,
            "frozen_pin_is_not_live_body_validation": True,
            "missing_or_mismatched_body_fails_full_acceptance": True,
            "opening_mode": "frozen-pin-only-fast-candidate",
        },
    }
    return expected, bodies


def _authenticate_semantic_catalog_body(value, expected_candidate):
    """Open the frozen topic-owner body for opt-in full acceptance only."""

    snapshot, raw = _snapshot(
        value,
        label="full semantic catalog trust-root body",
        maximum=2 * 2**20,
    )
    kind, schema, version, byte_count, digest = SEMANTIC_CATALOG_PIN
    if len(raw) != byte_count or not hmac.compare_digest(_sha256(raw), digest):
        _fail("semantic catalog trust-root body differs from its frozen opening pin")
    if (
        snapshot.get("artifact_kind") != kind
        or snapshot.get("artifact_schema") != schema
        or snapshot.get("artifact_schema_version") != version
        or snapshot.get("fixture_id") != FIXTURE_ID
        or snapshot.get("fixture_schema_version") != FIXTURE_SCHEMA_VERSION
        or snapshot.get("g0_contract_frozen") is not False
    ):
        _fail("semantic catalog trust-root body identity drifted")
    authority = snapshot.get("authority")
    if (
        type(authority) is not dict
        or not authority
        or any(type(flag) is not bool or flag is not False for flag in authority.values())
    ):
        _fail("semantic catalog trust-root body gained authority")
    expected_topics = [
        {
            "graph_id": topic["graph_id"],
            "persona_id": persona["persona_id"],
            "topic_id": topic["topic_id"],
            "topic_slot": topic["topic_slot"],
        }
        for persona in expected_candidate["personas"]
        for topic in persona["topics"]
    ]
    actual_topics = snapshot.get("semantic_topics")
    if type(actual_topics) is not list or len(actual_topics) != 80:
        _fail("semantic catalog trust-root topic table drifted")
    projected_topics = [
        {
            "graph_id": row.get("graph_id"),
            "persona_id": row.get("persona_id"),
            "topic_id": row.get("topic_id"),
            "topic_slot": row.get("topic_slot"),
        }
        for row in actual_topics
    ]
    if projected_topics != expected_topics:
        _fail("capacity axes differ from the opened semantic topic-owner body")
    return raw


def _provided_body(provider, persona_id):
    if not callable(provider):
        _fail("capacity-cell body provider must be callable")
    try:
        body = provider(persona_id)
    except Exception as error:
        raise PersonaV2SourceSemanticCapacityAxisCatalogValidationError(
            f"capacity-cell body provider failed for {persona_id}"
        ) from error
    if type(body) is not bytes:
        _fail("capacity-cell body provider must return exact built-in bytes")
    if len(body) > MAX_CELL_BODY_BYTES:
        _fail("capacity-cell body provider exceeded its persona byte cap")
    return body


def _postflight(
    value,
    opening_raw,
    graph_values,
    graph_raws,
    *,
    semantic_catalog_value=None,
    semantic_catalog_opening_raw=None,
):
    try:
        current = _canonical(
            value, label="caller-owned capacity-axis catalog postflight",
            maximum=MAX_CATALOG_BYTES,
        )
    except PersonaV2SourceSemanticCapacityAxisCatalogValidationError:
        _fail("caller-owned capacity-axis catalog changed during provider replay")
    if current != opening_raw:
        _fail("caller-owned capacity-axis catalog changed during provider replay")
    if type(graph_values) is not list or len(graph_values) != len(graph_raws):
        _fail("caller-owned fact-graph suite changed during provider replay")
    for value, opening in zip(graph_values, graph_raws, strict=True):
        try:
            current = _canonical(
                value, label="caller-owned fact graph postflight", maximum=1 * 2**20
            )
        except PersonaV2SourceSemanticCapacityAxisCatalogValidationError:
            _fail("caller-owned fact graph changed during provider replay")
        if current != opening:
            _fail("caller-owned fact graph changed during provider replay")
    if semantic_catalog_value is not None and semantic_catalog_opening_raw is not None:
        try:
            current = _canonical(
                semantic_catalog_value,
                label="caller-owned semantic catalog trust-root postflight",
                maximum=2 * 2**20,
            )
        except PersonaV2SourceSemanticCapacityAxisCatalogValidationError:
            _fail("caller-owned semantic catalog changed during provider replay")
        if current != semantic_catalog_opening_raw:
            _fail("caller-owned semantic catalog changed during provider replay")


def validate_source_semantic_capacity_axis_catalog(
    value,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    fact_graph_values=None,
    capacity_cell_body_provider=None,
    semantic_catalog_value=None,
    require_semantic_catalog_body=False,
):
    """Validate exact metadata, all bodies twice, and caller-object stability."""

    _require_producer_golden_parity(producer_expected_golden)
    if type(require_semantic_catalog_body) is not bool:
        _fail("semantic catalog body requirement must be an exact boolean")
    snapshot, opening_raw = _snapshot(
        value, label="source-semantic capacity-axis catalog", maximum=MAX_CATALOG_BYTES
    )
    _require_expected_raw(opening_raw)
    _require_static_candidate(snapshot)
    if fact_graph_values is None:
        fact_graph_values = fact_graph.build_fact_graph_suite()
    graph_snapshots, graph_raws, graph_bindings = _snapshot_fact_graphs(
        fact_graph_values
    )
    expected, expected_bodies = _expected_state(graph_snapshots, graph_bindings)
    semantic_catalog_opening_raw = None
    try:
        expected_raw = _canonical(
            expected, label="independent expected capacity-axis catalog",
            maximum=MAX_CATALOG_BYTES,
        )
        # Static and exact candidate validation must precede all 40 callbacks.
        if opening_raw != expected_raw or snapshot != expected:
            _fail("capacity-axis catalog differs from independent exact regeneration")
        if require_semantic_catalog_body and semantic_catalog_value is None:
            _fail("full acceptance requires the frozen semantic catalog body")
        if semantic_catalog_value is not None:
            semantic_catalog_opening_raw = _authenticate_semantic_catalog_body(
                semantic_catalog_value, expected
            )
        if capacity_cell_body_provider is None:
            capacity_cell_body_provider = expected_bodies.__getitem__
        for persona_id in PERSONA_IDS:
            first = _provided_body(capacity_cell_body_provider, persona_id)
            second = _provided_body(capacity_cell_body_provider, persona_id)
            if first != second:
                _fail("capacity-cell body provider replay is nondeterministic")
            if first != expected_bodies[persona_id]:
                _fail(f"{persona_id} capacity-cell body differs from independent regeneration")
        return True
    finally:
        _postflight(
            value,
            opening_raw,
            fact_graph_values,
            graph_raws,
            semantic_catalog_value=semantic_catalog_value,
            semantic_catalog_opening_raw=semantic_catalog_opening_raw,
        )


def validate_source_semantic_capacity_axis_catalog_bytes(
    raw,
    *,
    producer_expected_golden=_GOLDEN_NOT_PROVIDED,
    fact_graph_values=None,
    capacity_cell_body_provider=None,
    semantic_catalog_value=None,
    require_semantic_catalog_body=False,
):
    _require_producer_golden_parity(producer_expected_golden)
    if type(raw) is not bytes or len(raw) > MAX_CATALOG_BYTES:
        _fail("capacity-axis serialized input must be bounded exact bytes")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_constant=_reject_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        _fail(f"capacity-axis serialized input is invalid: {type(error).__name__}")
    if _canonical(
        value, label="capacity-axis serialized canonical check", maximum=MAX_CATALOG_BYTES
    ) != raw:
        _fail("capacity-axis serialized input is not exact canonical JSON")
    return validate_source_semantic_capacity_axis_catalog(
        value,
        producer_expected_golden=producer_expected_golden,
        fact_graph_values=fact_graph_values,
        capacity_cell_body_provider=capacity_cell_body_provider,
        semantic_catalog_value=semantic_catalog_value,
        require_semantic_catalog_body=require_semantic_catalog_body,
    )


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"duplicate JSON key: {key!r}")
        result[key] = value
    return result


def _reject_float(token):
    _fail(f"floating-point token is forbidden: {token!r}")


def _reject_constant(token):
    _fail(f"non-JSON constant is forbidden: {token!r}")


__all__ = [
    "ARTIFACT_KIND",
    "ARTIFACT_SCHEMA",
    "ARTIFACT_SCHEMA_VERSION",
    "AUTHORITY_FIELDS",
    "EXPECTED_CANONICAL_BYTES",
    "EXPECTED_SHA256",
    "MAX_CATALOG_BYTES",
    "PersonaV2SourceSemanticCapacityAxisCatalogValidationError",
    "validate_source_semantic_capacity_axis_catalog",
    "validate_source_semantic_capacity_axis_catalog_bytes",
]
