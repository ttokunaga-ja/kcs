"""Canonical W0 ledgers for the synthetic persona-PC fixture.

The generator writes one shard per direct-file scope.  Rows contain only
portable, persona-home-relative identities: absolute roots, KIO scope IDs,
commit hashes, mtimes, and actual KIO chunk hashes belong in later receipts.

The three immutable ledgers deliberately separate:

* physical raw sources and their raw-byte binding;
* renderer logical units and planned contract contribution;
* pre-index searchable expectations (never post-index observations).

All public validation is fail-closed.  Canonical JSON uses sorted keys,
compact separators, UTF-8, no floats, and one LF per file/JSONL row.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import unicodedata

try:  # Support package imports and direct imports from ``eval`` tests.
    from . import persona_fixture_spec as fixture_spec
    from . import persona_storage as storage
except ImportError:  # pragma: no cover
    import persona_fixture_spec as fixture_spec
    import persona_storage as storage


SCHEMA_VERSION = 1
PHYSICAL_ROW_SCHEMA = "kio.persona.w0.physical-raw/v1"
LOGICAL_ROW_SCHEMA = "kio.persona.w0.logical-item/v1"
SEARCHABLE_ROW_SCHEMA = "kio.persona.w0.searchable-expectation/v1"
SCOPE_MANIFEST_SCHEMA = "kio.persona.w0.scope-shard/v1"
SUITE_MANIFEST_SCHEMA = "kio.persona.w0.suite/v1"

PHYSICAL_LEDGER_NAME = "w0-physical-raw.jsonl"
LOGICAL_LEDGER_NAME = "w0-logical-items.jsonl"
SEARCHABLE_LEDGER_NAME = "w0-searchable-expectations.jsonl"
SCOPE_MANIFEST_NAME = "w0-scope-manifest.json"
SUITE_MANIFEST_NAME = "w0-suite-manifest.json"
RENDERER_ID = "kio-persona-renderer"
RENDERER_SCHEMA_VERSION = 1

GATE_ROLES = (
    "contract_contributor",
    "incidental_searchable",
    "raw_only",
)
ACTUAL_CHUNK_POLICY_BY_ROLE = {
    "contract_contributor": "persona_contract_exact",
    "incidental_searchable": "observe_nonnegative_excluded",
    "raw_only": "must_equal_zero",
}
LOGICAL_UNIT_KINDS = (
    "document",
    "message",
    "attachment",
    "page",
    "sheet",
    "slide",
    "image",
    "audio",
    "packet",
)

_PROFILES = frozenset(("tiny", "pilot", "full"))
_SHA256_RE = re.compile(r"[0-9a-f]{64}")
_SOURCE_ID_RE = re.compile(r"p[0-9]{2}-src-[0-9]{6}")
_SAFE_ID_RE = re.compile(r"[a-z0-9][a-z0-9._:-]{0,191}")
_EXTENSION_RE = re.compile(r"[a-z0-9][a-z0-9+_-]{0,15}")
_MEDIA_TYPE_RE = re.compile(
    r"[a-z0-9][a-z0-9!#$&^_.+-]*/[a-z0-9][a-z0-9!#$&^_.+-]*"
)
_WINDOWS_FORBIDDEN = frozenset('<>:"/\\|?*')
_WINDOWS_RESERVED = frozenset(
    ("con", "prn", "aux", "nul")
    + tuple(f"com{i}" for i in range(1, 10))
    + tuple(f"lpt{i}" for i in range(1, 10))
)
_MAX_JSON_DEPTH = 32
_MAX_INT = 2**63 - 1
_MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_SCOPE_MANIFEST_BYTES = 2 * 1024 * 1024
MAX_LEDGER_LINE_BYTES = 2 * 1024 * 1024
MAX_LOGICAL_ROWS_PER_SCOPE = 1_000_000
MAX_LEDGER_BYTES = 2 * 1024 * 1024 * 1024

_PHYSICAL_FIELDS = frozenset((
    "source_id", "persona_id", "scope_key", "relative_path", "file_name",
    "format_family", "extension", "variant", "media_type", "raw_sha256",
    "bytes", "logical_members", "renderer_id", "renderer_schema_version",
    "expected_contract_chunks", "expected_disposition", "gate_role",
))
_LOGICAL_FIELDS = frozenset((
    "source_id", "persona_id", "scope_key", "unit_index", "unit_kind",
    "unit_key", "parent_unit_key", "planned_contract_chunks",
))
_SEARCHABLE_FIELDS = frozenset((
    "source_id", "persona_id", "scope_key", "gate_role",
    "expected_disposition", "planned_contract_chunks", "planned_unit_keys",
    "actual_chunk_policy",
))


class PersonaManifestError(ValueError):
    """Raised when a ledger or publication violates the W0 contract."""


def _variant_policies():
    result = {}
    for family, variants in fixture_spec.FORMAT_VARIANTS.items():
        for variant, _weight, gate_role, disposition in variants:
            result[variant] = (family, gate_role, disposition)
    return result


_VARIANT_POLICIES = _variant_policies()


def _strict_int(value, label, *, minimum=0, maximum=_MAX_INT):
    if type(value) is not int or not minimum <= value <= maximum:
        raise PersonaManifestError(
            f"{label} must be an integer in [{minimum}, {maximum}]"
        )
    return value


def _strict_string(value, label, *, maximum_bytes=1024):
    if type(value) is not str or not value:
        raise PersonaManifestError(f"{label} must be a non-empty string")
    if unicodedata.normalize("NFC", value) != value:
        raise PersonaManifestError(f"{label} must be NFC")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise PersonaManifestError(f"{label} contains a control character")
    if len(value.encode("utf-8")) > maximum_bytes:
        raise PersonaManifestError(f"{label} is too long")
    return value


def _digest(value, label):
    if type(value) is not str or _SHA256_RE.fullmatch(value) is None:
        raise PersonaManifestError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _exact_fields(row, fields, label):
    if type(row) is not dict:
        raise PersonaManifestError(f"{label} must be a JSON object")
    if set(row) != fields:
        missing = sorted(fields - set(row))
        extra = sorted(set(row) - fields)
        raise PersonaManifestError(
            f"{label} has an invalid field set (missing={missing}, extra={extra})"
        )


def _portable_component(value, label):
    _strict_string(value, label, maximum_bytes=255)
    if value in (".", "..") or value.endswith((".", " ")):
        raise PersonaManifestError(f"{label} is not portable")
    if any(character in _WINDOWS_FORBIDDEN for character in value):
        raise PersonaManifestError(f"{label} contains a forbidden path character")
    stem = value.split(".", 1)[0].casefold()
    if stem in _WINDOWS_RESERVED:
        raise PersonaManifestError(f"{label} uses a reserved Windows stem")
    return value


def _scope_map(persona_id):
    try:
        persona = fixture_spec.get_persona(persona_id)
    except KeyError as error:
        raise PersonaManifestError(f"unknown persona_id: {persona_id!r}") from error
    return {
        scope["scope_key"]: scope["relative_path"]
        for scope in fixture_spec.scope_specs(persona)
    }


def _identity(persona_id, scope_key):
    _strict_string(persona_id, "persona_id", maximum_bytes=3)
    scopes = _scope_map(persona_id)
    if type(scope_key) is not str or scope_key not in scopes:
        raise PersonaManifestError(
            f"scope_key is not owned by {persona_id}: {scope_key!r}"
        )
    return scopes[scope_key]


def _validate_source_id(value, persona_id):
    if type(value) is not str or _SOURCE_ID_RE.fullmatch(value) is None:
        raise PersonaManifestError("source_id must match pNN-src-NNNNNN")
    if not value.startswith(f"{persona_id}-"):
        raise PersonaManifestError("source_id/persona_id mismatch")
    return value


def _validate_relative_path(value, expected_scope_path, file_name):
    _strict_string(value, "relative_path", maximum_bytes=512)
    if "\\" in value or value.startswith("/"):
        raise PersonaManifestError("relative_path must be a POSIX relative path")
    parsed = PurePosixPath(value)
    if str(parsed) != value or len(parsed.parts) < 2:
        raise PersonaManifestError("relative_path is not canonical")
    for index, component in enumerate(parsed.parts):
        _portable_component(component, f"relative_path[{index}]")
    expected = f"{expected_scope_path}/{file_name}"
    if value != expected:
        raise PersonaManifestError(
            f"relative_path must be the direct child {expected!r}"
        )
    return value


def _validate_physical_row(row, persona_id, scope_key):
    _exact_fields(row, _PHYSICAL_FIELDS, "physical row")
    expected_scope_path = _identity(persona_id, scope_key)
    if row["persona_id"] != persona_id or row["scope_key"] != scope_key:
        raise PersonaManifestError("physical row is in the wrong persona/scope shard")
    source_id = _validate_source_id(row["source_id"], persona_id)
    try:
        file_name = fixture_spec.validate_source_basename(row["file_name"])
    except ValueError as error:
        raise PersonaManifestError(str(error)) from error
    extension = row["extension"]
    if type(extension) is not str or _EXTENSION_RE.fullmatch(extension) is None:
        raise PersonaManifestError("extension is invalid")
    if "." not in file_name or file_name.rsplit(".", 1)[1] != extension:
        raise PersonaManifestError("extension does not match file_name")
    variant = row["variant"]
    policy = _VARIANT_POLICIES.get(variant)
    if policy is None:
        raise PersonaManifestError(f"unknown format variant: {variant!r}")
    family, gate_role, disposition = policy
    expected_extension = "pdf" if variant in ("pdf-text", "pdf-scan") else variant
    if extension != expected_extension:
        raise PersonaManifestError("extension does not match variant")
    if (
        row["format_family"] != family
        or row["gate_role"] != gate_role
        or row["expected_disposition"] != disposition
    ):
        raise PersonaManifestError("variant family/gate/disposition policy mismatch")
    media_type = row["media_type"]
    if type(media_type) is not str or _MEDIA_TYPE_RE.fullmatch(media_type) is None:
        raise PersonaManifestError("media_type must be a canonical type/subtype")
    chunks = _strict_int(
        row["expected_contract_chunks"],
        "expected_contract_chunks",
        maximum=fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE,
    )
    if (gate_role == "contract_contributor") != (chunks > 0):
        raise PersonaManifestError(
            "only contract_contributor sources may have expected contract chunks"
        )
    normalized = dict(row)
    normalized["source_id"] = source_id
    normalized["bytes"] = _strict_int(
        row["bytes"], "bytes", maximum=_MAX_FILE_BYTES
    )
    normalized["logical_members"] = _strict_int(
        row["logical_members"], "logical_members", minimum=1
    )
    normalized["renderer_id"] = _safe_token(row["renderer_id"], "renderer_id")
    normalized["renderer_schema_version"] = _strict_int(
        row["renderer_schema_version"],
        "renderer_schema_version",
        minimum=1,
        maximum=RENDERER_SCHEMA_VERSION,
    )
    if (
        normalized["renderer_id"] != RENDERER_ID
        or normalized["renderer_schema_version"] != RENDERER_SCHEMA_VERSION
    ):
        raise PersonaManifestError("renderer identity/schema version mismatch")
    normalized["raw_sha256"] = _digest(row["raw_sha256"], "raw_sha256")
    normalized["relative_path"] = _validate_relative_path(
        row["relative_path"], expected_scope_path, file_name
    )
    return normalized


def _validate_logical_row(row, persona_id, scope_key):
    _exact_fields(row, _LOGICAL_FIELDS, "logical row")
    _identity(persona_id, scope_key)
    if row["persona_id"] != persona_id or row["scope_key"] != scope_key:
        raise PersonaManifestError("logical row is in the wrong persona/scope shard")
    source_id = _validate_source_id(row["source_id"], persona_id)
    unit_key = _strict_string(row["unit_key"], "unit_key", maximum_bytes=192)
    if _SAFE_ID_RE.fullmatch(unit_key) is None or not unit_key.startswith(
        f"{source_id}:"
    ):
        raise PersonaManifestError("unit_key must be a source-prefixed stable ID")
    parent = row["parent_unit_key"]
    if parent is not None:
        parent = _strict_string(parent, "parent_unit_key", maximum_bytes=192)
        if _SAFE_ID_RE.fullmatch(parent) is None or not parent.startswith(
            f"{source_id}:"
        ):
            raise PersonaManifestError(
                "parent_unit_key must be null or a same-source stable ID"
            )
        if parent == unit_key:
            raise PersonaManifestError("a logical unit cannot parent itself")
    if row["unit_kind"] not in LOGICAL_UNIT_KINDS:
        raise PersonaManifestError(f"unknown unit_kind: {row['unit_kind']!r}")
    normalized = dict(row)
    normalized["source_id"] = source_id
    normalized["unit_index"] = _strict_int(row["unit_index"], "unit_index")
    normalized["planned_contract_chunks"] = _strict_int(
        row["planned_contract_chunks"],
        "planned_contract_chunks",
        maximum=fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE,
    )
    normalized["parent_unit_key"] = parent
    return normalized


def _validate_searchable_row(row, persona_id, scope_key):
    _exact_fields(row, _SEARCHABLE_FIELDS, "searchable expectation row")
    _identity(persona_id, scope_key)
    if row["persona_id"] != persona_id or row["scope_key"] != scope_key:
        raise PersonaManifestError(
            "searchable expectation row is in the wrong persona/scope shard"
        )
    source_id = _validate_source_id(row["source_id"], persona_id)
    gate_role = row["gate_role"]
    if gate_role not in GATE_ROLES:
        raise PersonaManifestError(f"unknown gate_role: {gate_role!r}")
    policy = ACTUAL_CHUNK_POLICY_BY_ROLE[gate_role]
    if row["actual_chunk_policy"] != policy:
        raise PersonaManifestError("actual_chunk_policy does not match gate_role")
    chunks = _strict_int(
        row["planned_contract_chunks"],
        "planned_contract_chunks",
        maximum=fixture_spec.MAX_CONTRIBUTOR_CHUNKS_PER_FILE,
    )
    keys = row["planned_unit_keys"]
    if type(keys) is not list:
        raise PersonaManifestError("planned_unit_keys must be a JSON array")
    normalized_keys = []
    for index, key in enumerate(keys):
        key = _strict_string(key, f"planned_unit_keys[{index}]", maximum_bytes=192)
        if _SAFE_ID_RE.fullmatch(key) is None or not key.startswith(f"{source_id}:"):
            raise PersonaManifestError("planned_unit_keys must be source-prefixed IDs")
        normalized_keys.append(key)
    if normalized_keys != sorted(set(normalized_keys)):
        raise PersonaManifestError("planned_unit_keys must be sorted and unique")
    if gate_role == "contract_contributor":
        if chunks <= 0 or not normalized_keys:
            raise PersonaManifestError(
                "contract_contributor needs planned chunks and logical units"
            )
    elif chunks != 0 or normalized_keys:
        raise PersonaManifestError(
            "incidental_searchable/raw_only must not claim contract chunks"
        )
    normalized = dict(row)
    normalized["source_id"] = source_id
    normalized["planned_unit_keys"] = normalized_keys
    return normalized


def _sort_rows(physical, logical, searchable):
    physical.sort(key=lambda row: (row["relative_path"], row["source_id"]))
    logical.sort(
        key=lambda row: (row["source_id"], row["unit_index"], row["unit_key"])
    )
    searchable.sort(key=lambda row: row["source_id"])


def validate_w0_ledgers(
    physical_rows,
    logical_rows,
    searchable_rows,
    *,
    persona_id,
    scope_key,
    expected_contract_chunks,
    expected_physical_rows=None,
    expected_variant_counts=None,
):
    """Validate and return a stable, detached projection of one scope shard."""
    expected_contract_chunks = _strict_int(
        expected_contract_chunks, "expected_contract_chunks"
    )
    if expected_physical_rows is not None:
        expected_physical_rows = _strict_int(
            expected_physical_rows, "expected_physical_rows", minimum=1
        )
    if type(expected_variant_counts) is not dict:
        raise PersonaManifestError("expected_variant_counts must be an exact dictionary")
    normalized_variant_counts = {}
    for variant, count in expected_variant_counts.items():
        if type(variant) is not str or variant not in _VARIANT_POLICIES:
            raise PersonaManifestError(f"unknown expected variant: {variant!r}")
        normalized_variant_counts[variant] = _strict_int(
            count, f"expected_variant_counts.{variant}"
        )
    if set(normalized_variant_counts) != set(_VARIANT_POLICIES):
        raise PersonaManifestError("expected_variant_counts must cover every variant")
    _identity(persona_id, scope_key)
    physical = [
        _validate_physical_row(row, persona_id, scope_key) for row in physical_rows
    ]
    logical = [
        _validate_logical_row(row, persona_id, scope_key) for row in logical_rows
    ]
    searchable = [
        _validate_searchable_row(row, persona_id, scope_key)
        for row in searchable_rows
    ]
    if not physical:
        raise PersonaManifestError("a scope shard must contain at least one source")
    if expected_physical_rows is not None and len(physical) != expected_physical_rows:
        raise PersonaManifestError("physical row count differs from the allocation plan")

    by_source = {}
    casefold_paths = set()
    raw_hashes = set()
    for row in physical:
        source_id = row["source_id"]
        if source_id in by_source:
            raise PersonaManifestError(f"duplicate source_id: {source_id}")
        by_source[source_id] = row
        path_identity = row["relative_path"].casefold()
        if path_identity in casefold_paths:
            raise PersonaManifestError(
                f"case-insensitive duplicate physical path: {row['relative_path']}"
            )
        casefold_paths.add(path_identity)
        if row["raw_sha256"] in raw_hashes:
            raise PersonaManifestError(
                "W0 raw_sha256 values must be unique; duplicates are history events"
            )
        raw_hashes.add(row["raw_sha256"])

    actual_variant_counts = {
        variant: sum(row["variant"] == variant for row in physical)
        for variant in _VARIANT_POLICIES
    }
    if actual_variant_counts != normalized_variant_counts:
        raise PersonaManifestError("physical variant counts differ from the allocation plan")

    logical_by_source = {source_id: [] for source_id in by_source}
    all_unit_keys = set()
    for row in logical:
        source = by_source.get(row["source_id"])
        if source is None:
            raise PersonaManifestError("logical row references an unknown source_id")
        if row["unit_key"] in all_unit_keys:
            raise PersonaManifestError(f"duplicate unit_key: {row['unit_key']}")
        all_unit_keys.add(row["unit_key"])
        logical_by_source[row["source_id"]].append(row)

    for source_id, rows in logical_by_source.items():
        source = by_source[source_id]
        if len(rows) != source["logical_members"]:
            raise PersonaManifestError(
                f"logical_members mismatch for source_id: {source_id}"
            )
        indices = sorted(row["unit_index"] for row in rows)
        if indices != list(range(len(rows))):
            raise PersonaManifestError(
                f"unit_index must be contiguous from zero: {source_id}"
            )
        keys = {row["unit_key"] for row in rows}
        parents = {row["unit_key"]: row["parent_unit_key"] for row in rows}
        for key, parent in parents.items():
            if parent is not None and parent not in keys:
                raise PersonaManifestError(f"unknown parent_unit_key for {key}")
            visited = set()
            cursor = key
            while cursor is not None:
                if cursor in visited:
                    raise PersonaManifestError(f"logical parent cycle for {source_id}")
                visited.add(cursor)
                cursor = parents.get(cursor)
        planned = sum(row["planned_contract_chunks"] for row in rows)
        if planned != source["expected_contract_chunks"]:
            raise PersonaManifestError(
                f"logical/physical contract chunk mismatch for {source_id}"
            )
        if source["gate_role"] != "contract_contributor" and planned != 0:
            raise PersonaManifestError("non-contributor logical units claim chunks")

    searchable_by_source = {}
    for row in searchable:
        if row["source_id"] in searchable_by_source:
            raise PersonaManifestError(
                f"duplicate searchable source_id: {row['source_id']}"
            )
        searchable_by_source[row["source_id"]] = row
    if set(searchable_by_source) != set(by_source):
        raise PersonaManifestError(
            "searchable expectations must contain exactly one row per physical source"
        )
    for source_id, source in by_source.items():
        expectation = searchable_by_source[source_id]
        if (
            expectation["gate_role"] != source["gate_role"]
            or expectation["expected_disposition"]
            != source["expected_disposition"]
            or expectation["planned_contract_chunks"]
            != source["expected_contract_chunks"]
        ):
            raise PersonaManifestError(
                f"physical/searchable policy mismatch for source_id: {source_id}"
            )
        expected_keys = sorted(
            row["unit_key"]
            for row in logical_by_source[source_id]
            if row["planned_contract_chunks"] > 0
        )
        if expectation["planned_unit_keys"] != expected_keys:
            raise PersonaManifestError(
                f"planned_unit_keys differ from logical units for {source_id}"
            )

    planned_total = sum(
        row["expected_contract_chunks"] for row in physical
    )
    if planned_total != expected_contract_chunks:
        raise PersonaManifestError(
            "scope planned contract chunks differ from the allocation plan"
        )
    _sort_rows(physical, logical, searchable)
    counts_by_role = {
        role: sum(row["gate_role"] == role for row in physical)
        for role in GATE_ROLES
    }
    return {
        "physical_raw": tuple(physical),
        "logical_items": tuple(logical),
        "searchable_expectations": tuple(searchable),
        "totals": {
            "physical_sources": len(physical),
            "physical_bytes": sum(row["bytes"] for row in physical),
            "logical_items": len(logical),
            "planned_contract_chunks": planned_total,
            "sources_by_gate_role": counts_by_role,
            "sources_by_variant": actual_variant_counts,
        },
    }


def _validate_json_value(value, label="value", depth=0):
    if depth > _MAX_JSON_DEPTH:
        raise PersonaManifestError(f"{label} exceeds canonical JSON depth")
    if value is None or type(value) in (bool, str):
        if type(value) is str:
            _strict_string(value, label, maximum_bytes=1024 * 1024)
        return
    if type(value) is int:
        _strict_int(value, label, minimum=-_MAX_INT, maximum=_MAX_INT)
        return
    if type(value) is list or type(value) is tuple:
        for index, item in enumerate(value):
            _validate_json_value(item, f"{label}[{index}]", depth + 1)
        return
    if type(value) is dict:
        for key, item in value.items():
            if type(key) is not str or not key:
                raise PersonaManifestError(f"{label} has a non-string/empty key")
            _validate_json_value(item, f"{label}.{key}", depth + 1)
        return
    raise PersonaManifestError(
        f"{label} contains a non-canonical JSON type: {type(value).__name__}"
    )


def canonical_json_bytes(value):
    """Return compact canonical JSON bytes without a trailing LF."""
    _validate_json_value(value)
    return json.dumps(
        value, ensure_ascii=False, allow_nan=False, separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def canonical_jsonl_bytes(rows):
    """Return canonically sorted JSONL bytes (primarily for small tests)."""
    encoded = sorted(canonical_json_bytes(row) for row in rows)
    return b"".join(row + b"\n" for row in encoded)


def _rows_summary(rows):
    digest = hashlib.sha256()
    byte_count = 0
    row_count = 0
    for row in rows:
        raw = canonical_json_bytes(row) + b"\n"
        digest.update(raw)
        byte_count += len(raw)
        row_count += 1
    return {
        "rows": row_count,
        "bytes": byte_count,
        "sha256": digest.hexdigest(),
    }


def _root(domain, rows_by_ledger, projector):
    ledger_roots = {}
    for name, rows in rows_by_ledger.items():
        digest = hashlib.sha256()
        for row in rows:
            digest.update(canonical_json_bytes(projector(name, row)) + b"\n")
        ledger_roots[name] = digest.hexdigest()
    return hashlib.sha256(canonical_json_bytes({
        "domain": domain,
        "ledger_roots": ledger_roots,
    })).hexdigest()


def _state_projection(_name, row):
    return row


def _semantic_projection(name, row):
    placement = {"persona_id", "scope_key"}
    if name == "physical_raw":
        placement |= {"relative_path", "file_name"}
    return {key: value for key, value in row.items() if key not in placement}


def ledger_roots(validated):
    """Return domain-separated semantic and relative-state SHA-256 roots."""
    rows = {
        "physical_raw": validated["physical_raw"],
        "logical_items": validated["logical_items"],
        "searchable_expectations": validated["searchable_expectations"],
    }
    return {
        "semantic_root_sha256": _root(
            "kio.persona.w0.semantic-root/v1", rows, _semantic_projection
        ),
        "state_root_sha256": _root(
            "kio.persona.w0.state-root/v1", rows, _state_projection
        ),
    }


def _safe_token(value, label):
    _strict_string(value, label, maximum_bytes=128)
    if _SAFE_ID_RE.fullmatch(value) is None:
        raise PersonaManifestError(f"{label} is not a safe stable identifier")
    return value


def build_w0_scope_manifest(
    physical_rows,
    logical_rows,
    searchable_rows,
    *,
    fixture_id,
    profile,
    persona_id,
    scope_key,
    plan_sha256,
    expected_contract_chunks,
    expected_physical_rows,
    expected_variant_counts,
):
    """Build a canonical, root-independent manifest for one scope shard."""
    fixture_id = _safe_token(fixture_id, "fixture_id")
    if profile not in _PROFILES:
        raise PersonaManifestError(f"unknown profile: {profile!r}")
    plan_sha256 = _digest(plan_sha256, "plan_sha256")
    _identity(persona_id, scope_key)
    persona = fixture_spec.get_persona(persona_id)
    expected_scope_files = fixture_spec.scope_file_counts(persona, profile)[scope_key]
    expected_scope_chunks = fixture_spec.scope_contributor_chunk_targets(
        persona, profile
    )[scope_key]
    if expected_physical_rows != expected_scope_files:
        raise PersonaManifestError("expected_physical_rows differs from the fixture spec")
    if expected_contract_chunks != expected_scope_chunks:
        raise PersonaManifestError("expected_contract_chunks differs from the fixture spec")
    validated = validate_w0_ledgers(
        physical_rows,
        logical_rows,
        searchable_rows,
        persona_id=persona_id,
        scope_key=scope_key,
        expected_contract_chunks=expected_contract_chunks,
        expected_physical_rows=expected_physical_rows,
        expected_variant_counts=expected_variant_counts,
    )
    ledger_specs = (
        ("physical_raw", PHYSICAL_LEDGER_NAME, PHYSICAL_ROW_SCHEMA),
        ("logical_items", LOGICAL_LEDGER_NAME, LOGICAL_ROW_SCHEMA),
        (
            "searchable_expectations",
            SEARCHABLE_LEDGER_NAME,
            SEARCHABLE_ROW_SCHEMA,
        ),
    )
    ledgers = {}
    for key, file_name, row_schema in ledger_specs:
        summary = _rows_summary(validated[key])
        ledgers[key] = {"file": file_name, "row_schema": row_schema, **summary}
    manifest = {
        "schema": SCOPE_MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "profile": profile,
        "checkpoint": "W0",
        "persona_id": persona_id,
        "scope_key": scope_key,
        "plan_sha256": plan_sha256,
        "ledgers": ledgers,
        "totals": validated["totals"],
        **ledger_roots(validated),
    }
    return manifest, validated


def _is_plain_regular(metadata):
    return stat.S_ISREG(metadata.st_mode) and not bool(
        getattr(metadata, "st_file_attributes", 0) & 0x400
    )


def _fsync_directory(path):
    if hasattr(os, "O_DIRECTORY"):
        descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _atomic_materialized_file(path, data, *, mode=0o600):
    path = Path(path)
    if type(data) is not bytes:
        raise PersonaManifestError("atomic canonical payload must be bytes")
    if len(data) > MAX_LEDGER_BYTES:
        raise PersonaManifestError("atomic canonical payload exceeds its byte bound")
    try:
        storage.atomic_create_directory(path.parent, parents=True)
        storage.atomic_write_file(path, data, mode=mode)
    except storage.PersonaStorageError as error:
        raise PersonaManifestError(str(error)) from error
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def atomic_write_canonical_json(path, value, *, mode=0o600):
    """Atomically create a canonical JSON file without replacing any path."""
    raw = canonical_json_bytes(value) + b"\n"
    return _atomic_materialized_file(path, raw, mode=mode)


def atomic_write_canonical_jsonl(path, rows, *, presorted=False, mode=0o600):
    """Atomically create canonical JSONL and return count/byte/hash evidence.

    Scope-shard row bounds make materialization acceptable and allow reuse of
    persona_storage's race-safe, atomic no-replace file publication primitive.
    """
    if presorted:
        iterable = rows
    else:
        iterable = sorted(rows, key=canonical_json_bytes)
    encoded = []
    for row in iterable:
        line = canonical_json_bytes(row) + b"\n"
        if len(line) > MAX_LEDGER_LINE_BYTES:
            raise PersonaManifestError("canonical JSONL row exceeds its byte bound")
        encoded.append(line)
    raw = b"".join(encoded)
    summary = _atomic_materialized_file(path, raw, mode=mode)
    summary["rows"] = len(encoded)
    return summary


def _manifest_file_bytes(manifest):
    return canonical_json_bytes(manifest) + b"\n"


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise PersonaManifestError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_json_number(value):
    raise PersonaManifestError(f"non-integer JSON number is forbidden: {value}")


def _decode_canonical_json(raw, label):
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_json_number,
            parse_constant=_reject_json_number,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise PersonaManifestError(f"{label} is invalid JSON") from error
    if canonical_json_bytes(value) + b"\n" != raw:
        raise PersonaManifestError(f"{label} is not canonical JSON")
    return value


def _read_bounded_plain(path, maximum, label):
    try:
        metadata = path.lstat()
    except FileNotFoundError as error:
        raise PersonaManifestError(f"{label} is missing: {path}") from error
    if not _is_plain_regular(metadata) or metadata.st_nlink != 1:
        raise PersonaManifestError(f"{label} must be a single-link plain file")
    if metadata.st_size > maximum:
        raise PersonaManifestError(f"{label} exceeds its byte bound")
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise PersonaManifestError(f"{label} changed while opening")
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise PersonaManifestError(f"{label} exceeds its byte bound")
    after = path.lstat()
    if (
        not _is_plain_regular(after)
        or after.st_nlink != 1
        or (after.st_dev, after.st_ino, after.st_size) != (
        opened.st_dev, opened.st_ino, opened.st_size
        )
    ):
        raise PersonaManifestError(f"{label} changed while reading")
    return raw


def _validate_loaded_scope_manifest(manifest):
    fields = frozenset((
        "schema", "schema_version", "fixture_id", "profile", "checkpoint",
        "persona_id", "scope_key", "plan_sha256", "ledgers", "totals",
        "semantic_root_sha256", "state_root_sha256",
    ))
    _exact_fields(manifest, fields, "scope manifest")
    if (
        manifest["schema"] != SCOPE_MANIFEST_SCHEMA
        or manifest["schema_version"] != SCHEMA_VERSION
        or manifest["fixture_id"] != fixture_spec.FIXTURE_ID
        or manifest["checkpoint"] != "W0"
        or manifest["profile"] not in _PROFILES
    ):
        raise PersonaManifestError("scope manifest header mismatch")
    _identity(manifest["persona_id"], manifest["scope_key"])
    _digest(manifest["plan_sha256"], "plan_sha256")
    _digest(manifest["semantic_root_sha256"], "semantic_root_sha256")
    _digest(manifest["state_root_sha256"], "state_root_sha256")
    if type(manifest["ledgers"]) is not dict:
        raise PersonaManifestError("scope manifest ledgers must be an object")
    expected_ledgers = {
        "physical_raw": (PHYSICAL_LEDGER_NAME, PHYSICAL_ROW_SCHEMA,
                         fixture_spec.MAX_DIRECT_FILES_PER_SCOPE),
        "logical_items": (LOGICAL_LEDGER_NAME, LOGICAL_ROW_SCHEMA,
                          MAX_LOGICAL_ROWS_PER_SCOPE),
        "searchable_expectations": (
            SEARCHABLE_LEDGER_NAME, SEARCHABLE_ROW_SCHEMA,
            fixture_spec.MAX_DIRECT_FILES_PER_SCOPE,
        ),
    }
    if set(manifest["ledgers"]) != set(expected_ledgers):
        raise PersonaManifestError("scope manifest has an invalid ledger set")
    for key, (file_name, row_schema, maximum_rows) in expected_ledgers.items():
        ledger = manifest["ledgers"][key]
        _exact_fields(
            ledger, frozenset(("file", "row_schema", "rows", "bytes", "sha256")),
            f"scope manifest ledger {key}",
        )
        if ledger["file"] != file_name or ledger["row_schema"] != row_schema:
            raise PersonaManifestError(f"scope manifest ledger identity mismatch: {key}")
        _strict_int(ledger["rows"], f"{key}.rows", minimum=1, maximum=maximum_rows)
        _strict_int(ledger["bytes"], f"{key}.bytes", minimum=1,
                    maximum=MAX_LEDGER_BYTES)
        _digest(ledger["sha256"], f"{key}.sha256")
    if type(manifest["totals"]) is not dict:
        raise PersonaManifestError("scope manifest totals must be an object")
    return manifest


def _read_canonical_jsonl(path, ledger, maximum_rows, label):
    metadata = path.lstat()
    if not _is_plain_regular(metadata) or metadata.st_nlink != 1:
        raise PersonaManifestError(f"{label} must be a single-link plain file")
    if metadata.st_size != ledger["bytes"] or metadata.st_size > MAX_LEDGER_BYTES:
        raise PersonaManifestError(f"{label} byte count mismatch")
    digest = hashlib.sha256()
    rows = []
    with path.open("rb") as handle:
        opened = os.fstat(handle.fileno())
        if (opened.st_dev, opened.st_ino) != (metadata.st_dev, metadata.st_ino):
            raise PersonaManifestError(f"{label} changed while opening")
        while len(rows) <= maximum_rows:
            line = handle.readline(MAX_LEDGER_LINE_BYTES + 1)
            if not line:
                break
            if len(line) > MAX_LEDGER_LINE_BYTES or not line.endswith(b"\n"):
                raise PersonaManifestError(f"{label} contains an oversized/partial row")
            digest.update(line)
            rows.append(_decode_canonical_json(line, f"{label} row"))
        if handle.read(1):
            raise PersonaManifestError(f"{label} exceeds its row bound")
    after = path.lstat()
    if (
        not _is_plain_regular(after)
        or after.st_nlink != 1
        or (after.st_dev, after.st_ino, after.st_size) != (
        opened.st_dev, opened.st_ino, opened.st_size
        )
    ):
        raise PersonaManifestError(f"{label} changed while reading")
    if len(rows) != ledger["rows"] or digest.hexdigest() != ledger["sha256"]:
        raise PersonaManifestError(f"{label} count/hash mismatch")
    return rows


def verify_w0_scope_shard(destination, *, expected_manifest=None, persona_home=None):
    """Strictly read, revalidate, and optionally bind a scope shard to raw files."""
    destination = Path(destination)
    expected_names = {
        PHYSICAL_LEDGER_NAME,
        LOGICAL_LEDGER_NAME,
        SEARCHABLE_LEDGER_NAME,
        SCOPE_MANIFEST_NAME,
    }
    metadata = destination.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or destination.is_symlink():
        raise PersonaManifestError(f"scope shard destination is unsafe: {destination}")
    names = {child.name for child in destination.iterdir()}
    if names != expected_names:
        raise PersonaManifestError("existing scope shard has an unexpected file set")
    manifest_path = destination / SCOPE_MANIFEST_NAME
    raw_manifest = _read_bounded_plain(
        manifest_path, MAX_SCOPE_MANIFEST_BYTES, "scope manifest"
    )
    manifest = _validate_loaded_scope_manifest(
        _decode_canonical_json(raw_manifest, "scope manifest")
    )
    if expected_manifest is not None and raw_manifest != _manifest_file_bytes(expected_manifest):
        raise PersonaManifestError("existing scope shard manifest differs")
    physical = _read_canonical_jsonl(
        destination / PHYSICAL_LEDGER_NAME, manifest["ledgers"]["physical_raw"],
        fixture_spec.MAX_DIRECT_FILES_PER_SCOPE, "physical ledger",
    )
    logical = _read_canonical_jsonl(
        destination / LOGICAL_LEDGER_NAME, manifest["ledgers"]["logical_items"],
        MAX_LOGICAL_ROWS_PER_SCOPE, "logical ledger",
    )
    searchable = _read_canonical_jsonl(
        destination / SEARCHABLE_LEDGER_NAME,
        manifest["ledgers"]["searchable_expectations"],
        fixture_spec.MAX_DIRECT_FILES_PER_SCOPE, "searchable ledger",
    )
    rebuilt, validated = build_w0_scope_manifest(
        physical, logical, searchable,
        fixture_id=manifest["fixture_id"], profile=manifest["profile"],
        persona_id=manifest["persona_id"], scope_key=manifest["scope_key"],
        plan_sha256=manifest["plan_sha256"],
        expected_contract_chunks=manifest["totals"].get("planned_contract_chunks"),
        expected_physical_rows=manifest["totals"].get("physical_sources"),
        expected_variant_counts=manifest["totals"].get("sources_by_variant"),
    )
    if rebuilt != manifest:
        raise PersonaManifestError("scope manifest does not match canonical ledgers")
    if persona_home is not None:
        _verify_raw_sources(Path(persona_home), validated["physical_raw"])
    return {"manifest": manifest, "validated": validated}


def _verify_raw_sources(persona_home, physical_rows):
    metadata = persona_home.lstat()
    if not stat.S_ISDIR(metadata.st_mode) or persona_home.is_symlink():
        raise PersonaManifestError("persona_home must be a plain directory")
    seen_inodes = set()
    for row in physical_rows:
        path = persona_home.joinpath(*PurePosixPath(row["relative_path"]).parts)
        current = persona_home
        for component in PurePosixPath(row["relative_path"]).parts[:-1]:
            current = current / component
            item = current.lstat()
            if not stat.S_ISDIR(item.st_mode) or current.is_symlink():
                raise PersonaManifestError(f"raw source parent is unsafe: {current}")
        item = path.lstat()
        if not _is_plain_regular(item) or item.st_nlink != 1:
            raise PersonaManifestError(f"raw source must be a single-link plain file: {path}")
        inode = (item.st_dev, item.st_ino)
        if inode in seen_inodes:
            raise PersonaManifestError("raw source inode is reused inside the shard")
        seen_inodes.add(inode)
        if item.st_size != row["bytes"]:
            raise PersonaManifestError(f"raw source size mismatch: {path}")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                not _is_plain_regular(opened)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size)
                != (item.st_dev, item.st_ino, row["bytes"])
            ):
                raise PersonaManifestError(f"raw source changed while opening: {path}")
            remaining = row["bytes"]
            while remaining:
                block = handle.read(min(1024 * 1024, remaining))
                if not block:
                    raise PersonaManifestError(f"raw source was truncated: {path}")
                digest.update(block)
                remaining -= len(block)
            if handle.read(1):
                raise PersonaManifestError(f"raw source grew while reading: {path}")
        after = path.lstat()
        if (
            not _is_plain_regular(after)
            or after.st_nlink != 1
            or (after.st_dev, after.st_ino, after.st_size)
            != (opened.st_dev, opened.st_ino, opened.st_size)
        ):
            raise PersonaManifestError(f"raw source changed while reading: {path}")
        if digest.hexdigest() != row["raw_sha256"]:
            raise PersonaManifestError(f"raw source digest mismatch: {path}")


def _verify_identical_scope_shard(destination, manifest):
    try:
        result = verify_w0_scope_shard(destination, expected_manifest=manifest)
    except FileNotFoundError:
        return False
    return result["manifest"] == manifest


def publish_w0_scope_shard(
    destination,
    physical_rows,
    logical_rows,
    searchable_rows,
    **manifest_arguments,
):
    """Publish one complete W0 scope-ledger shard inside an owned stage.

    An already-published byte-identical shard is a verified no-op.  A partial
    or differing shard fails closed.  Each file uses the storage boundary's
    atomic no-replace publication and the scope manifest is the last commit
    marker.  The caller must pass a
    directory inside the generator-owned staging root; whole-tree atomicity
    remains the storage boundary's responsibility.
    """
    manifest, validated = build_w0_scope_manifest(
        physical_rows, logical_rows, searchable_rows, **manifest_arguments
    )
    destination = Path(destination)
    if _verify_identical_scope_shard(destination, manifest):
        return manifest
    try:
        created = storage.atomic_create_directory(destination, parents=True)
    except storage.PersonaStorageError as error:
        raise PersonaManifestError(str(error)) from error
    if not created:
        raise PersonaManifestError("scope shard destination appeared during publication")
    try:
        written = {
            "physical_raw": atomic_write_canonical_jsonl(
                destination / PHYSICAL_LEDGER_NAME,
                validated["physical_raw"], presorted=True,
            ),
            "logical_items": atomic_write_canonical_jsonl(
                destination / LOGICAL_LEDGER_NAME,
                validated["logical_items"], presorted=True,
            ),
            "searchable_expectations": atomic_write_canonical_jsonl(
                destination / SEARCHABLE_LEDGER_NAME,
                validated["searchable_expectations"], presorted=True,
            ),
        }
        for key, summary in written.items():
            if summary != {
                field: manifest["ledgers"][key][field]
                for field in ("bytes", "sha256", "rows")
            }:
                raise PersonaManifestError(f"published {key} summary drifted")
        atomic_write_canonical_json(destination / SCOPE_MANIFEST_NAME, manifest)
        _fsync_directory(destination)
    except BaseException:
        # The outer owned staging root is deliberately retained by
        # persona_storage for forensic recovery; never recursively clean here.
        raise
    return manifest


def _validate_scope_manifest_reference(manifest, *, fixture_id, profile, plan_sha256):
    _validate_loaded_scope_manifest(manifest)
    if (
        manifest["fixture_id"] != fixture_id
        or manifest["profile"] != profile
        or manifest["plan_sha256"] != plan_sha256
    ):
        raise PersonaManifestError("scope manifest suite binding mismatch")
    totals = manifest["totals"]
    total_fields = frozenset((
        "physical_sources", "physical_bytes", "logical_items",
        "planned_contract_chunks", "sources_by_gate_role", "sources_by_variant",
    ))
    _exact_fields(totals, total_fields, "scope manifest totals")
    physical = _strict_int(
        totals["physical_sources"], "physical_sources", minimum=1,
        maximum=fixture_spec.MAX_DIRECT_FILES_PER_SCOPE,
    )
    _strict_int(totals["physical_bytes"], "physical_bytes")
    logical = _strict_int(
        totals["logical_items"], "logical_items", minimum=physical,
        maximum=MAX_LOGICAL_ROWS_PER_SCOPE,
    )
    chunks = _strict_int(totals["planned_contract_chunks"],
                         "planned_contract_chunks")
    roles = totals["sources_by_gate_role"]
    if type(roles) is not dict or set(roles) != set(GATE_ROLES):
        raise PersonaManifestError("sources_by_gate_role has an invalid field set")
    for role in GATE_ROLES:
        _strict_int(roles[role], f"sources_by_gate_role.{role}")
    variants = totals["sources_by_variant"]
    if type(variants) is not dict or set(variants) != set(_VARIANT_POLICIES):
        raise PersonaManifestError("sources_by_variant has an invalid field set")
    for variant in _VARIANT_POLICIES:
        _strict_int(variants[variant], f"sources_by_variant.{variant}")
    if sum(roles.values()) != physical or sum(variants.values()) != physical:
        raise PersonaManifestError("scope source marginal totals disagree")
    derived_roles = {role: 0 for role in GATE_ROLES}
    for variant, count in variants.items():
        derived_roles[_VARIANT_POLICIES[variant][1]] += count
    if derived_roles != roles:
        raise PersonaManifestError("scope variant/gate marginals disagree")
    ledgers = manifest["ledgers"]
    if (
        ledgers["physical_raw"]["rows"] != physical
        or ledgers["logical_items"]["rows"] != logical
        or ledgers["searchable_expectations"]["rows"] != physical
    ):
        raise PersonaManifestError("scope ledger/totals row counts disagree")
    persona = fixture_spec.get_persona(manifest["persona_id"])
    scope_key = manifest["scope_key"]
    if physical != fixture_spec.scope_file_counts(persona, profile)[scope_key]:
        raise PersonaManifestError("scope physical total differs from fixture spec")
    if chunks != fixture_spec.scope_contributor_chunk_targets(
        persona, profile
    )[scope_key]:
        raise PersonaManifestError("scope chunk total differs from fixture spec")
    return manifest


def build_w0_suite_manifest(
    *, fixture_id, profile, plan_sha256, shard_manifests, validated_shards
):
    """Build the exact 20-person/400-scope count/hash-only W0 index.

    ``validated_shards`` must correspond one-for-one with ``shard_manifests``;
    retaining the row projections here is what permits suite-wide source and
    raw-hash uniqueness checks without bloating the published suite manifest.
    """
    fixture_id = _safe_token(fixture_id, "fixture_id")
    if fixture_id != fixture_spec.FIXTURE_ID:
        raise PersonaManifestError("suite fixture_id differs from the frozen fixture")
    if profile not in _PROFILES:
        raise PersonaManifestError(f"unknown profile: {profile!r}")
    plan_sha256 = _digest(plan_sha256, "plan_sha256")
    manifests = list(shard_manifests)
    projections = list(validated_shards)
    if len(manifests) != len(projections):
        raise PersonaManifestError("suite manifests and validated shards differ in length")
    expected_identities = {
        (persona["id"], scope["scope_key"])
        for persona in fixture_spec.PERSONAS
        for scope in fixture_spec.scope_specs(persona)
    }
    if len(manifests) != len(expected_identities):
        raise PersonaManifestError("W0 suite requires exactly 20 x 20 scope shards")
    shards = []
    seen = set()
    source_ids = set()
    raw_hashes = set()
    unit_keys = set()
    persona_variants = {
        persona["id"]: {variant: 0 for variant in _VARIANT_POLICIES}
        for persona in fixture_spec.PERSONAS
    }
    for manifest, validated in zip(manifests, projections):
        _validate_scope_manifest_reference(
            manifest, fixture_id=fixture_id, profile=profile,
            plan_sha256=plan_sha256,
        )
        identity = (manifest["persona_id"], manifest["scope_key"])
        if identity in seen:
            raise PersonaManifestError(f"duplicate scope shard: {identity}")
        seen.add(identity)
        if type(validated) is not dict or set(validated) != {
            "physical_raw", "logical_items", "searchable_expectations", "totals"
        }:
            raise PersonaManifestError("validated shard projection has an invalid shape")
        rebuilt, rebuilt_projection = build_w0_scope_manifest(
            validated["physical_raw"], validated["logical_items"],
            validated["searchable_expectations"], fixture_id=fixture_id,
            profile=profile, persona_id=identity[0], scope_key=identity[1],
            plan_sha256=plan_sha256,
            expected_contract_chunks=manifest["totals"]["planned_contract_chunks"],
            expected_physical_rows=manifest["totals"]["physical_sources"],
            expected_variant_counts=manifest["totals"]["sources_by_variant"],
        )
        if rebuilt != manifest or rebuilt_projection != validated:
            raise PersonaManifestError("suite scope manifest/projection mismatch")
        for row in validated["physical_raw"]:
            if row["source_id"] in source_ids:
                raise PersonaManifestError(f"suite duplicate source_id: {row['source_id']}")
            if row["raw_sha256"] in raw_hashes:
                raise PersonaManifestError("suite duplicate W0 raw_sha256")
            source_ids.add(row["source_id"])
            raw_hashes.add(row["raw_sha256"])
        for row in validated["logical_items"]:
            if row["unit_key"] in unit_keys:
                raise PersonaManifestError(f"suite duplicate unit_key: {row['unit_key']}")
            unit_keys.add(row["unit_key"])
        for variant, count in manifest["totals"]["sources_by_variant"].items():
            persona_variants[identity[0]][variant] += count
        ledgers = manifest["ledgers"]
        shards.append({
            "persona_id": identity[0],
            "scope_key": identity[1],
            "relative_path": f"{identity[0]}/{identity[1]}",
            "manifest_sha256": hashlib.sha256(
                _manifest_file_bytes(manifest)
            ).hexdigest(),
            "physical_rows": ledgers["physical_raw"]["rows"],
            "physical_sha256": ledgers["physical_raw"]["sha256"],
            "logical_rows": ledgers["logical_items"]["rows"],
            "logical_sha256": ledgers["logical_items"]["sha256"],
            "searchable_rows": ledgers["searchable_expectations"]["rows"],
            "searchable_sha256": ledgers["searchable_expectations"]["sha256"],
            "planned_contract_chunks": manifest["totals"]["planned_contract_chunks"],
            "semantic_root_sha256": manifest["semantic_root_sha256"],
            "state_root_sha256": manifest["state_root_sha256"],
        })
    shards.sort(key=lambda row: (row["persona_id"], row["scope_key"]))
    if seen != expected_identities:
        raise PersonaManifestError("W0 suite scope identity inventory is incomplete")
    for persona in fixture_spec.PERSONAS:
        expected_variants = {
            entry["variant"]: entry["count"]
            for entries in fixture_spec.format_variant_counts(persona, profile).values()
            for entry in entries
        }
        if persona_variants[persona["id"]] != expected_variants:
            raise PersonaManifestError(
                f"suite variant marginals differ for {persona['id']}"
            )
    expected_totals = {
        "personas": len(fixture_spec.PERSONAS),
        "scope_shards": len(expected_identities),
        "physical_sources": sum(
            fixture_spec.raw_file_count(persona, profile)
            for persona in fixture_spec.PERSONAS
        ),
        "planned_contract_chunks": sum(
            fixture_spec.contributor_plan(persona, profile)["target_chunks"]
            for persona in fixture_spec.PERSONAS
        ),
    }
    semantic_root = hashlib.sha256(canonical_json_bytes({
        "domain": "kio.persona.w0.suite-semantic-root/v1",
        "shards": [
            {
                "persona_id": row["persona_id"],
                "scope_key": row["scope_key"],
                "semantic_root_sha256": row["semantic_root_sha256"],
            }
            for row in shards
        ],
    })).hexdigest()
    state_root = hashlib.sha256(canonical_json_bytes({
        "domain": "kio.persona.w0.suite-state-root/v1", "shards": shards
    })).hexdigest()
    return {
        "schema": SUITE_MANIFEST_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "fixture_id": fixture_id,
        "profile": profile,
        "checkpoint": "W0",
        "plan_sha256": plan_sha256,
        "shards": shards,
        "expected_totals": expected_totals,
        "totals": {
            "personas": len({row["persona_id"] for row in shards}),
            "scope_shards": len(shards),
            "physical_sources": sum(row["physical_rows"] for row in shards),
            "logical_items": sum(row["logical_rows"] for row in shards),
            "planned_contract_chunks": sum(
                row["planned_contract_chunks"] for row in shards
            ),
        },
        "semantic_root_sha256": semantic_root,
        "state_root_sha256": state_root,
    }
