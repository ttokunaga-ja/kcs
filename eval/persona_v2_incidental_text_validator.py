"""Standalone validator for persona-PC v2 incidental structured text.

The validator intentionally does not import the renderer, source/variant
catalogs, or planning modules.  It duplicates the frozen metadata, affine byte
formulas, canonical templates, and padding algorithms it validates.  A receipt
proves only bounded local bytes and structure; it never attests KIO execution,
observed chunks, source identity, placement, or physical publication.
"""

from __future__ import annotations

import copy
import csv
from dataclasses import dataclass
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
import io
import json
import re
import unicodedata
import xml.etree.ElementTree as ET

try:  # Support package imports and direct ``eval/*.py`` execution.
    from . import persona_v2_artifact_common as artifact_common
except ImportError:  # pragma: no cover - direct-script compatibility
    import persona_v2_artifact_common as artifact_common


CONTRACT_SCHEMA = "kio.persona.pc-id-free-incidental-text-validator/v2"
CONTRACT_SCHEMA_VERSION = 2
CONTRACT_KIND = "persona-pc-v2-id-free-incidental-text-validator"
VALIDATOR_ID = "persona-v2-id-free-incidental-text-standalone-validator"
VALIDATOR_SCHEMA_VERSION = 2
MAX_CONTRACT_BYTES = 96 * 1024
MAX_RENDERED_BYTES = 512 * 1024
MAX_EML_LINE_OCTETS = 78
MAX_JSON_NESTING_DEPTH = 16

READY_VARIANTS = (
    "csv",
    "eml",
    "html",
    "ipynb",
    "json",
    "jsonl",
    "log",
    "sql",
    "tsv",
    "xml",
    "yaml",
)

REQUEST_FIELDS = (
    "schema_version",
    "variant",
    "target_complexity",
    "data",
    "extension",
    "content_media_type",
    "expected_kio_path_media_type",
    "expected_offline_disposition",
)

PROHIBITED_IDENTITY_FIELDS = (
    "digest",
    "final_id",
    "final_source_id",
    "intent_id",
    "materialization_id",
    "payload_seed",
    "persona_id",
    "query_id",
    "query_key",
    "scope_id",
    "scope_key",
    "source_id",
)

_VARIANT_ROWS = {
    "csv": {
        "complexity_measure": "tabular-rows",
        "content_media_type": "text/csv",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "csv_tsv",
        "filename_extension": "csv",
        "formula_base_bytes_at_complexity_one": 512,
        "formula_increment_bytes_per_additional_complexity": 48,
        "inclusive_maximum": 10_000,
        "inclusive_minimum": 1,
        "render_template": "canonical-comma-table-v2",
    },
    "eml": {
        "complexity_measure": "attachments",
        "content_media_type": "message/rfc822",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "html_eml",
        "filename_extension": "eml",
        "formula_base_bytes_at_complexity_one": 8_192,
        "formula_increment_bytes_per_additional_complexity": 16_384,
        "inclusive_maximum": 5,
        "inclusive_minimum": 0,
        "render_template": "canonical-crlf-multipart-mixed-v2",
    },
    "html": {
        "complexity_measure": "html-sections",
        "content_media_type": "text/html",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "html_eml",
        "filename_extension": "html",
        "formula_base_bytes_at_complexity_one": 2_048,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "inclusive_maximum": 256,
        "inclusive_minimum": 1,
        "render_template": "canonical-html-sections-v2",
    },
    "ipynb": {
        "complexity_measure": "notebook-cells",
        "content_media_type": "application/x-ipynb+json",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "ipynb",
        "filename_extension": "ipynb",
        "formula_base_bytes_at_complexity_one": 2_048,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "inclusive_maximum": 256,
        "inclusive_minimum": 1,
        "render_template": "canonical-nbformat-4-5-v2",
    },
    "json": {
        "complexity_measure": "json-nodes",
        "content_media_type": "application/json",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "json",
        "formula_base_bytes_at_complexity_one": 1_024,
        "formula_increment_bytes_per_additional_complexity": 256,
        "inclusive_maximum": 1_024,
        "inclusive_minimum": 1,
        "render_template": "canonical-json-node-array-v2",
    },
    "jsonl": {
        "complexity_measure": "jsonl-records",
        "content_media_type": "application/x-ndjson",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "txt_log",
        "filename_extension": "jsonl",
        "formula_base_bytes_at_complexity_one": 512,
        "formula_increment_bytes_per_additional_complexity": 96,
        "inclusive_maximum": 4_096,
        "inclusive_minimum": 1,
        "render_template": "canonical-json-lines-v2",
    },
    "log": {
        "complexity_measure": "log-records",
        "content_media_type": "text/plain",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "txt_log",
        "filename_extension": "log",
        "formula_base_bytes_at_complexity_one": 512,
        "formula_increment_bytes_per_additional_complexity": 96,
        "inclusive_maximum": 4_096,
        "inclusive_minimum": 1,
        "render_template": "canonical-fixed-log-records-v2",
    },
    "sql": {
        "complexity_measure": "sql-statements",
        "content_media_type": "application/sql",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "sql",
        "formula_base_bytes_at_complexity_one": 2_048,
        "formula_increment_bytes_per_additional_complexity": 1_024,
        "inclusive_maximum": 256,
        "inclusive_minimum": 1,
        "render_template": "canonical-select-statements-v2",
    },
    "tsv": {
        "complexity_measure": "tabular-rows",
        "content_media_type": "text/tab-separated-values",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "csv_tsv",
        "filename_extension": "tsv",
        "formula_base_bytes_at_complexity_one": 512,
        "formula_increment_bytes_per_additional_complexity": 48,
        "inclusive_maximum": 10_000,
        "inclusive_minimum": 1,
        "render_template": "canonical-tab-table-v2",
    },
    "xml": {
        "complexity_measure": "xml-elements",
        "content_media_type": "application/xml",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "xml",
        "formula_base_bytes_at_complexity_one": 1_024,
        "formula_increment_bytes_per_additional_complexity": 256,
        "inclusive_maximum": 1_024,
        "inclusive_minimum": 1,
        "render_template": "canonical-xml-items-v2",
    },
    "yaml": {
        "complexity_measure": "yaml-nodes",
        "content_media_type": "application/yaml",
        "expected_kio_path_media_type": "application/octet-stream",
        "expected_offline_disposition": "incidental_sniff",
        "family": "structured_text",
        "filename_extension": "yaml",
        "formula_base_bytes_at_complexity_one": 1_024,
        "formula_increment_bytes_per_additional_complexity": 256,
        "inclusive_maximum": 1_024,
        "inclusive_minimum": 1,
        "render_template": "canonical-yaml-block-sequence-v2",
    },
}

_COMPLEXITY_COUNTING_RULES = {
    "csv": "data-rows-excluding-header",
    "eml": "attachment-parts-excluding-primary-body",
    "html": "section-elements",
    "ipynb": "notebook-cells",
    "json": "top-level-array-items-excluding-root-object-and-array",
    "jsonl": "physical-json-records",
    "log": "physical-log-records",
    "sql": "select-statements",
    "tsv": "data-rows-excluding-header",
    "xml": "direct-item-elements-excluding-root-element",
    "yaml": "block-sequence-items-excluding-sequence-container",
}

_FORBIDDEN_IDENTITY_PATTERN = re.compile(
    rb"(?:"
    rb"\bp[0-9]{2}-src-[0-9]{6}\b|"
    rb"\b(?:persona|scope|source|intent|materialization|query|final[_-]?source)"
    rb"[_-]?(?:id|key)\s*[:=]|"
    rb"\b(?:sha256|digest)\s*[:=]|"
    rb"\b[0-9a-f]{64}\b"
    rb")",
    re.IGNORECASE,
)
_BOUNDARY = "bounded-mixed-boundary"
_BOUNDARY_BYTES = _BOUNDARY.encode("ascii")
_LF = "\n"
_CRLF = "\r\n"


class PersonaV2IncidentalTextValidatorError(ValueError):
    """Raised when incidental bytes or metadata violate the exact contract."""


@dataclass(frozen=True, slots=True)
class IncidentalTextValidationRequest:
    """The complete identity-free incidental payload supplied for validation."""

    schema_version: int
    variant: str
    target_complexity: int
    data: bytes
    extension: str
    content_media_type: str
    expected_kio_path_media_type: str
    expected_offline_disposition: str


def _fail(message):
    raise PersonaV2IncidentalTextValidatorError(message)


def _profile(variant):
    if type(variant) is not str or variant not in _VARIANT_ROWS:
        _fail("unsupported incidental text variant")
    return _VARIANT_ROWS[variant]


def target_bytes_for(variant, target_complexity):
    """Evaluate the exact affine raw-byte formula for one variant."""

    profile = _profile(variant)
    if (
        type(target_complexity) is not int
        or not profile["inclusive_minimum"]
        <= target_complexity
        <= profile["inclusive_maximum"]
    ):
        _fail("target complexity is outside the exact variant range")
    if variant == "eml":
        target = profile["formula_base_bytes_at_complexity_one"] + (
            target_complexity
            * profile["formula_increment_bytes_per_additional_complexity"]
        )
    else:
        target = profile["formula_base_bytes_at_complexity_one"] + (
            target_complexity - 1
        ) * profile["formula_increment_bytes_per_additional_complexity"]
    if not 1 <= target <= MAX_RENDERED_BYTES:
        _fail("target-byte formula exceeds the standalone validator cap")
    return target


def _canonical_json(value):
    return json.dumps(
        value,
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("ascii")


def _filled(prefix, suffix, target_length, *, fill="x"):
    if not all(
        type(value) is str and value.isascii()
        for value in (prefix, suffix, fill)
    ):
        _fail("fill components must be exact ASCII strings")
    if not fill:
        _fail("fill token must be non-empty")
    remaining = target_length - len(prefix) - len(suffix)
    if remaining < 0:
        _fail("canonical format skeleton exceeds its target")
    repetitions, remainder = divmod(remaining, len(fill))
    result = prefix + fill * repetitions + fill[:remainder] + suffix
    if len(result) != target_length:
        _fail("exact fill length drifted")
    return result


def _filled_crlf_lines(prefix, suffix, target_length):
    """Independently regenerate exact bounded EML body line wrapping."""

    if not all(
        type(value) is str and value.isascii() for value in (prefix, suffix)
    ):
        _fail("EML fill components must be exact ASCII strings")
    if not suffix.startswith(_CRLF):
        _fail("EML fill suffix must begin with CRLF framing")
    remaining = target_length - len(prefix) - len(suffix)
    current_width = len(prefix.rsplit(_CRLF, 1)[-1])
    if remaining < 1 or not 0 <= current_width < MAX_EML_LINE_OCTETS:
        _fail("EML body skeleton cannot satisfy its exact line-bound target")
    for break_count in range(remaining // len(_CRLF) + 1):
        filler_octets = remaining - break_count * len(_CRLF)
        capacities = [MAX_EML_LINE_OCTETS - current_width] + [
            MAX_EML_LINE_OCTETS
        ] * break_count
        if not len(capacities) <= filler_octets <= sum(capacities):
            continue
        widths = [1] * len(capacities)
        unassigned = filler_octets - len(widths)
        for ordinal, capacity in enumerate(capacities):
            addition = min(capacity - 1, unassigned)
            widths[ordinal] += addition
            unassigned -= addition
        if unassigned:
            continue
        filler = _CRLF.join("x" * width for width in widths)
        result = prefix + filler + suffix
        if len(result) != target_length:
            _fail("EML exact fill length drifted")
        if max(len(line) for line in result.split(_CRLF)) > MAX_EML_LINE_OCTETS:
            _fail("EML exact fill exceeded its wire line bound")
        return result
    _fail("EML exact target has no bounded-line representation")


def _expected_log(complexity, target_bytes):
    rows = []
    for ordinal in range(1, complexity + 1):
        length = 512 if ordinal == 1 else 96
        prefix = (
            f"2026-07-15T00:00:00Z INFO ordinal={ordinal:04d} "
            "message=bounded-"
        )
        rows.append(_filled(prefix, _LF, length))
    data = "".join(rows).encode("ascii")
    if len(data) != target_bytes:
        _fail("log bytes differ from their affine formula")
    return data


def _jsonl_line(ordinal, target_length):
    row = {
        "kind": "bounded-record",
        "ordinal": f"{ordinal:04d}",
        "padding": "",
    }
    empty = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    padding = target_length - len(empty) - 1
    if padding < 0:
        _fail("JSONL skeleton exceeds its record target")
    row["padding"] = "x" * padding
    encoded = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    ) + _LF
    if len(encoded) != target_length:
        _fail("JSONL record length drifted")
    return encoded


def _expected_jsonl(complexity, target_bytes):
    data = "".join(
        _jsonl_line(ordinal, 512 if ordinal == 1 else 96)
        for ordinal in range(1, complexity + 1)
    ).encode("ascii")
    if len(data) != target_bytes:
        _fail("JSONL bytes differ from their affine formula")
    return data


def _json_string(prefix, serialized_length):
    content_length = serialized_length - 2
    if content_length < len(prefix):
        _fail("JSON string skeleton exceeds its target")
    return json.dumps(prefix + "x" * (content_length - len(prefix)))


def _expected_json(complexity, target_bytes):
    prefix = '{"nodes":['
    suffix = "]}\n"
    first_length = 1_024 - len(prefix) - len(suffix)
    items = [_json_string("bounded-node-0001-", first_length)]
    for ordinal in range(2, complexity + 1):
        items.append(_json_string(f"bounded-node-{ordinal:04d}-", 255))
    data = (prefix + ",".join(items) + suffix).encode("ascii")
    if len(data) != target_bytes:
        _fail("JSON bytes differ from their affine formula")
    return data


def _expected_yaml(complexity, target_bytes):
    rows = []
    for ordinal in range(1, complexity + 1):
        length = 1_024 if ordinal == 1 else 256
        rows.append(_filled(f"- bounded-node-{ordinal:04d}-", _LF, length))
    data = "".join(rows).encode("ascii")
    if len(data) != target_bytes:
        _fail("YAML bytes differ from their affine formula")
    return data


def _expected_xml(complexity, target_bytes):
    prefix = '<?xml version="1.0" encoding="UTF-8"?>\n<items>\n'
    suffix = "</items>\n"
    first_length = 1_024 - len(prefix) - len(suffix)
    items = [
        _filled('<item ordinal="0001">bounded-node-', "</item>\n", first_length)
    ]
    for ordinal in range(2, complexity + 1):
        items.append(
            _filled(
                f'<item ordinal="{ordinal:04d}">bounded-node-',
                "</item>\n",
                256,
            )
        )
    data = (prefix + "".join(items) + suffix).encode("ascii")
    if len(data) != target_bytes:
        _fail("XML bytes differ from their affine formula")
    return data


def _expected_sql(complexity, target_bytes):
    statements = []
    for ordinal in range(1, complexity + 1):
        length = 2_048 if ordinal == 1 else 1_024
        prefix = f"SELECT 'bounded-statement-{ordinal:03d}-"
        statements.append(_filled(prefix, "' AS note;\n", length))
    data = "".join(statements).encode("ascii")
    if len(data) != target_bytes:
        _fail("SQL bytes differ from their affine formula")
    return data


def _table_row(delimiter, ordinal, target_length):
    prefix = f"{ordinal:05d}{delimiter}bounded{delimiter}"
    return _filled(prefix, _LF, target_length)


def _expected_tabular(variant, complexity, target_bytes):
    delimiter = "," if variant == "csv" else "\t"
    header = f"ordinal{delimiter}label{delimiter}note\n"
    first_length = 512 - len(header)
    rows = [_table_row(delimiter, 1, first_length)]
    rows.extend(
        _table_row(delimiter, ordinal, 48)
        for ordinal in range(2, complexity + 1)
    )
    data = (header + "".join(rows)).encode("ascii")
    if len(data) != target_bytes:
        _fail("tabular bytes differ from their affine formula")
    return data


def _expected_html(complexity, target_bytes):
    prefix = (
        '<!doctype html>\n<html><head><meta charset="utf-8">'
        "<title>Bounded</title></head><body>\n"
    )
    suffix = "</body></html>\n"
    first_length = 2_048 - len(prefix) - len(suffix)
    sections = [
        _filled(
            '<section data-ordinal="001"><h2>Bounded section</h2><p>',
            "</p></section>\n",
            first_length,
        )
    ]
    for ordinal in range(2, complexity + 1):
        sections.append(
            _filled(
                f'<section data-ordinal="{ordinal:03d}">'
                "<h2>Bounded section</h2><p>",
                "</p></section>\n",
                1_024,
            )
        )
    data = (prefix + "".join(sections) + suffix).encode("ascii")
    if len(data) != target_bytes:
        _fail("HTML bytes differ from their affine formula")
    return data


def _notebook_cell(ordinal, serialized_length):
    row = {
        "cell_type": "markdown",
        "id": f"cell-{ordinal:03d}",
        "metadata": {},
        "source": [""],
    }
    empty = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    padding = serialized_length - len(empty)
    prefix = "Bounded synthetic note. "
    if padding < len(prefix):
        _fail("notebook cell skeleton exceeds its target")
    row["source"] = [prefix + "x" * (padding - len(prefix))]
    encoded = json.dumps(
        row, ensure_ascii=True, separators=(",", ":"), sort_keys=True
    )
    if len(encoded) != serialized_length:
        _fail("notebook cell serialized length drifted")
    return encoded


def _expected_ipynb(complexity, target_bytes):
    prefix = '{"cells":['
    suffix = '],"metadata":{},"nbformat":4,"nbformat_minor":5}\n'
    first_length = 2_048 - len(prefix) - len(suffix)
    cells = [_notebook_cell(1, first_length)]
    cells.extend(
        _notebook_cell(ordinal, 1_023)
        for ordinal in range(2, complexity + 1)
    )
    data = (prefix + ",".join(cells) + suffix).encode("ascii")
    if len(data) != target_bytes:
        _fail("IPYNB bytes differ from their affine formula")
    return data


def _eml_attachment(ordinal):
    prefix = (
        f"--{_BOUNDARY}{_CRLF}"
        f'Content-Type: text/plain; name="note-{ordinal:02d}.txt"{_CRLF}'
        f'Content-Disposition: attachment; filename="note-{ordinal:02d}.txt"'
        f"{_CRLF}"
        f"Content-Transfer-Encoding: 7bit{_CRLF}{_CRLF}"
        f"Bounded attachment {ordinal:02d}. "
    )
    return _filled_crlf_lines(prefix, _CRLF, 16_384)


def _expected_eml(complexity, target_bytes):
    prefix = (
        f"From: synthetic-sender@example.invalid{_CRLF}"
        f"To: synthetic-recipient@example.invalid{_CRLF}"
        f"Subject: Bounded synthetic message{_CRLF}"
        f"Date: Wed, 15 Jul 2026 00:00:00 +0000{_CRLF}"
        f"Message-ID: <bounded-message@example.invalid>{_CRLF}"
        f"MIME-Version: 1.0{_CRLF}"
        f'Content-Type: multipart/mixed; boundary="{_BOUNDARY}"{_CRLF}'
        f"{_CRLF}"
        f"--{_BOUNDARY}{_CRLF}"
        f'Content-Type: text/plain; charset="us-ascii"{_CRLF}'
        f"Content-Transfer-Encoding: 7bit{_CRLF}{_CRLF}"
        f"Bounded synthetic message body. "
    )
    closing = f"{_CRLF}--{_BOUNDARY}--{_CRLF}"
    base = _filled_crlf_lines(prefix, closing, 8_192)
    insertion = "".join(
        _eml_attachment(ordinal) for ordinal in range(1, complexity + 1)
    )
    if insertion:
        text = base[: -len(closing)] + _CRLF + insertion + closing[len(_CRLF) :]
    else:
        text = base
    data = text.encode("ascii")
    if len(data) != target_bytes:
        _fail("EML bytes differ from their affine formula")
    return data


def _expected_payload(variant, complexity, target_bytes):
    if variant == "log":
        return _expected_log(complexity, target_bytes)
    if variant == "jsonl":
        return _expected_jsonl(complexity, target_bytes)
    if variant == "json":
        return _expected_json(complexity, target_bytes)
    if variant == "yaml":
        return _expected_yaml(complexity, target_bytes)
    if variant == "xml":
        return _expected_xml(complexity, target_bytes)
    if variant == "sql":
        return _expected_sql(complexity, target_bytes)
    if variant in {"csv", "tsv"}:
        return _expected_tabular(variant, complexity, target_bytes)
    if variant == "html":
        return _expected_html(complexity, target_bytes)
    if variant == "ipynb":
        return _expected_ipynb(complexity, target_bytes)
    if variant == "eml":
        return _expected_eml(complexity, target_bytes)
    _fail("unknown incidental validation template")


def _validate_request_shape(request):
    if type(request) is not IncidentalTextValidationRequest:
        _fail("request must be an exact IncidentalTextValidationRequest")
    if tuple(IncidentalTextValidationRequest.__dataclass_fields__) != REQUEST_FIELDS:
        _fail("validator request schema drifted")
    if set(REQUEST_FIELDS) & set(PROHIBITED_IDENTITY_FIELDS):
        _fail("validator request exposes a prohibited identity field")
    if type(request.schema_version) is not int or request.schema_version != 2:
        _fail("validator request schema version must be exact integer 2")
    profile = _profile(request.variant)
    target_bytes = target_bytes_for(
        request.variant, request.target_complexity
    )
    if type(request.data) is not bytes:
        _fail("validated payload must be exact bytes")
    # This bound is deliberately checked before decoding, splitting, or any
    # format parser can allocate from attacker-controlled framing.
    if not request.data or len(request.data) > MAX_RENDERED_BYTES:
        _fail("validated payload is empty or exceeds 512 KiB")
    expected_metadata = (
        profile["filename_extension"],
        profile["content_media_type"],
        profile["expected_kio_path_media_type"],
        profile["expected_offline_disposition"],
    )
    actual_metadata = (
        request.extension,
        request.content_media_type,
        request.expected_kio_path_media_type,
        request.expected_offline_disposition,
    )
    if any(type(value) is not str for value in actual_metadata):
        _fail("format metadata must contain exact strings")
    if actual_metadata != expected_metadata:
        _fail("extension, MIME, path MIME, or disposition metadata drifted")
    if len(request.data) != target_bytes:
        _fail("payload violates its exact affine byte formula")
    return profile, target_bytes


def _validate_encoding_newline_and_identity(variant, data):
    if data.startswith(b"\xef\xbb\xbf"):
        _fail("incidental payload must not contain a UTF-8 BOM")
    if b"\x00" in data:
        _fail("incidental payload must not contain NUL")
    if _FORBIDDEN_IDENTITY_PATTERN.search(data):
        _fail("payload contains an identity, query, solution, or digest token")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        _fail("incidental payload must be strict UTF-8")
    if not text.isascii():
        _fail("formal incidental feasibility payload must be ASCII")
    if unicodedata.normalize("NFC", text) != text:
        _fail("incidental payload must be NFC")
    if variant == "eml":
        without_crlf = data.replace(b"\r\n", b"")
        if (
            not data.endswith(b"\r\n")
            or b"\r" in without_crlf
            or b"\n" in without_crlf
        ):
            _fail("EML must use exact CRLF framing")
    elif (
        not data.endswith(b"\n")
        or data.endswith(b"\n\n")
        or b"\r" in data
    ):
        _fail("non-EML payload must use LF and exactly one terminal LF")
    return text


def _reject_duplicate_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            _fail(f"JSON contains duplicate key {key!r}")
        result[key] = value
    return result


def _reject_float(token):
    _fail(f"canonical incidental JSON contains float {token!r}")


def _reject_constant(token):
    _fail(f"canonical incidental JSON contains constant {token!r}")


def _parse_bounded_int(token):
    if type(token) is not str or len(token) > 20:
        _fail("canonical incidental JSON integer exceeds 20 digits")
    try:
        return int(token)
    except ValueError as error:  # pragma: no cover - json supplies integer grammar.
        raise PersonaV2IncidentalTextValidatorError(
            "canonical incidental JSON integer is invalid"
        ) from error


def _reject_excessive_json_nesting(raw, *, label):
    """Bound JSON container depth before handing bytes to the stdlib parser."""

    depth = 0
    in_string = False
    escaped = False
    for octet in raw:
        if in_string:
            if escaped:
                escaped = False
            elif octet == ord("\\"):
                escaped = True
            elif octet == ord('"'):
                in_string = False
            continue
        if octet == ord('"'):
            in_string = True
        elif octet in (ord("["), ord("{")):
            depth += 1
            if depth > MAX_JSON_NESTING_DEPTH:
                _fail(
                    f"{label} nesting exceeds {MAX_JSON_NESTING_DEPTH} containers"
                )
        elif octet in (ord("]"), ord("}")):
            depth -= 1
            if depth < 0:
                _fail(f"{label} has an unmatched closing container")


def _strict_json(raw, *, label):
    _reject_excessive_json_nesting(raw, label=label)
    try:
        return json.loads(
            raw,
            object_pairs_hook=_reject_duplicate_keys,
            parse_float=_reject_float,
            parse_int=_parse_bounded_int,
            parse_constant=_reject_constant,
        )
    except PersonaV2IncidentalTextValidatorError:
        raise
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        RecursionError,
        ValueError,
    ) as error:
        raise PersonaV2IncidentalTextValidatorError(
            f"{label} is not strict JSON"
        ) from error


def _validate_log(text, complexity):
    lines = text.splitlines()
    if len(lines) != complexity:
        _fail("log record count differs from target complexity")
    pattern = re.compile(
        r"2026-07-15T00:00:00Z INFO ordinal=([0-9]{4}) "
        r"message=bounded-(x+)\Z"
    )
    for ordinal, line in enumerate(lines, start=1):
        match = pattern.fullmatch(line)
        if match is None or match.group(1) != f"{ordinal:04d}":
            _fail("log record schema or ordinal drifted")
        expected_length = 512 if ordinal == 1 else 96
        if len(line) + 1 != expected_length:
            _fail("log record length differs from its exact formula")


def _validate_jsonl(data, complexity):
    raw_rows = data[:-1].split(b"\n")
    if len(raw_rows) != complexity or any(not row for row in raw_rows):
        _fail("JSONL record count or framing drifted")
    for ordinal, raw in enumerate(raw_rows, start=1):
        value = _strict_json(raw, label="JSONL record")
        if (
            type(value) is not dict
            or set(value) != {"kind", "ordinal", "padding"}
            or value["kind"] != "bounded-record"
            or value["ordinal"] != f"{ordinal:04d}"
            or type(value["padding"]) is not str
            or not value["padding"]
            or set(value["padding"]) != {"x"}
            or _canonical_json(value) != raw
        ):
            _fail("JSONL record differs from its strict canonical schema")
        expected_length = 512 if ordinal == 1 else 96
        if len(raw) + 1 != expected_length:
            _fail("JSONL record length differs from its exact formula")


def _validate_json(data, complexity):
    raw = data[:-1]
    value = _strict_json(raw, label="JSON payload")
    if (
        type(value) is not dict
        or set(value) != {"nodes"}
        or type(value["nodes"]) is not list
        or len(value["nodes"]) != complexity
        or _canonical_json(value) != raw
    ):
        _fail("JSON root schema, node count, or canonical encoding drifted")
    for ordinal, node in enumerate(value["nodes"], start=1):
        prefix = f"bounded-node-{ordinal:04d}-"
        if (
            type(node) is not str
            or not node.startswith(prefix)
            or not node[len(prefix) :]
            or set(node[len(prefix) :]) != {"x"}
        ):
            _fail("JSON node content or ordinal drifted")


def _validate_yaml(text, complexity):
    if any(token in text for token in ("\t", "---", "...", "&", "*", "!", "{", "}")):
        _fail("YAML payload escapes the strict block-sequence subset")
    lines = text.splitlines()
    if len(lines) != complexity:
        _fail("YAML node count differs from target complexity")
    pattern = re.compile(r"- bounded-node-([0-9]{4})-(x+)\Z")
    for ordinal, line in enumerate(lines, start=1):
        match = pattern.fullmatch(line)
        if match is None or match.group(1) != f"{ordinal:04d}":
            _fail("YAML node schema or ordinal drifted")
        expected_length = 1_024 if ordinal == 1 else 256
        if len(line) + 1 != expected_length:
            _fail("YAML node length differs from its exact formula")


def _validate_xml(data, complexity):
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        _fail("XML DTD and entity declarations are forbidden")
    try:
        root = ET.fromstring(data)
    except ET.ParseError as error:
        raise PersonaV2IncidentalTextValidatorError(
            "XML payload is not well formed"
        ) from error
    if root.tag != "items" or root.attrib or len(root) != complexity:
        _fail("XML root or item count differs from the strict schema")
    if root.text != "\n":
        _fail("XML root whitespace drifted")
    for ordinal, item in enumerate(root, start=1):
        if (
            item.tag != "item"
            or item.attrib != {"ordinal": f"{ordinal:04d}"}
            or len(item) != 0
            or type(item.text) is not str
            or not item.text.startswith("bounded-node-")
            or not item.text[len("bounded-node-") :]
            or set(item.text[len("bounded-node-") :]) != {"x"}
            or item.tail != "\n"
        ):
            _fail("XML item schema, text, or ordinal drifted")


def _validate_sql(text, complexity):
    lines = text.splitlines()
    if len(lines) != complexity:
        _fail("SQL statement count differs from target complexity")
    pattern = re.compile(
        r"SELECT 'bounded-statement-([0-9]{3})-(x+)' AS note;\Z"
    )
    for ordinal, line in enumerate(lines, start=1):
        match = pattern.fullmatch(line)
        if match is None or match.group(1) != f"{ordinal:03d}":
            _fail("SQL statement schema or ordinal drifted")
        expected_length = 2_048 if ordinal == 1 else 1_024
        if len(line) + 1 != expected_length:
            _fail("SQL statement length differs from its exact formula")


def _validate_tabular(variant, text, complexity):
    delimiter = "," if variant == "csv" else "\t"
    try:
        rows = list(
            csv.reader(
                io.StringIO(text, newline=""),
                delimiter=delimiter,
                strict=True,
            )
        )
    except csv.Error as error:
        raise PersonaV2IncidentalTextValidatorError(
            "tabular payload is not strict delimited text"
        ) from error
    if len(rows) != complexity + 1 or rows[0] != ["ordinal", "label", "note"]:
        _fail("tabular header or data-row count drifted")
    raw_lines = text.splitlines()
    if len(raw_lines) != complexity + 1:
        _fail("tabular physical line count drifted")
    for ordinal, row in enumerate(rows[1:], start=1):
        if (
            len(row) != 3
            or row[0] != f"{ordinal:05d}"
            or row[1] != "bounded"
            or not row[2]
            or set(row[2]) != {"x"}
        ):
            _fail("tabular row schema or ordinal drifted")
        expected_length = (
            512 - len(raw_lines[0]) - 1 if ordinal == 1 else 48
        )
        if len(raw_lines[ordinal]) + 1 != expected_length:
            _fail("tabular row length differs from its exact formula")


class _StrictIncidentalHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.stack = []
        self.section_count = 0
        self.doctype_count = 0
        self.meta_count = 0

    def handle_decl(self, decl):
        if decl != "doctype html" or self.doctype_count:
            _fail("HTML doctype drifted or repeated")
        self.doctype_count += 1

    def handle_starttag(self, tag, attrs):
        allowed = {"html", "head", "meta", "title", "body", "section", "h2", "p"}
        if tag not in allowed:
            _fail("HTML contains a forbidden element")
        if tag == "meta":
            if attrs != [("charset", "utf-8")] or self.meta_count:
                _fail("HTML meta charset drifted or repeated")
            self.meta_count += 1
            return
        if tag == "section":
            self.section_count += 1
            if attrs != [("data-ordinal", f"{self.section_count:03d}")]:
                _fail("HTML section ordinal or attributes drifted")
        elif attrs:
            _fail("HTML contains attributes outside the exact allowlist")
        self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        _fail("HTML self-closing syntax is outside the exact schema")

    def handle_endtag(self, tag):
        if not self.stack or self.stack.pop() != tag:
            _fail("HTML element nesting drifted")

    def handle_data(self, data):
        if not self.stack:
            if data.strip():
                _fail("HTML contains text outside the root element")
            return
        parent = self.stack[-1]
        if parent == "title" and data != "Bounded":
            _fail("HTML title text drifted")
        elif parent == "h2" and data != "Bounded section":
            _fail("HTML heading text drifted")
        elif parent == "p" and (not data or set(data) != {"x"}):
            _fail("HTML section padding text drifted")
        elif parent not in {"title", "h2", "p"} and data.strip():
            _fail("HTML contains text outside title, heading, or paragraph")

    def handle_comment(self, data):
        _fail("HTML comments are outside the exact schema")

    def handle_entityref(self, name):
        _fail("HTML named entities are outside the exact schema")

    def handle_charref(self, name):
        _fail("HTML numeric entities are outside the exact schema")


def _validate_html(text, complexity):
    parser = _StrictIncidentalHTMLParser()
    try:
        parser.feed(text)
        parser.close()
    except PersonaV2IncidentalTextValidatorError:
        raise
    except Exception as error:
        raise PersonaV2IncidentalTextValidatorError(
            "HTML parser rejected the payload"
        ) from error
    if (
        parser.stack
        or parser.doctype_count != 1
        or parser.meta_count != 1
        or parser.section_count != complexity
    ):
        _fail("HTML document coverage or section count drifted")


def _validate_ipynb(data, complexity):
    raw = data[:-1]
    value = _strict_json(raw, label="IPYNB payload")
    if (
        type(value) is not dict
        or set(value) != {"cells", "metadata", "nbformat", "nbformat_minor"}
        or type(value["cells"]) is not list
        or len(value["cells"]) != complexity
        or value["metadata"] != {}
        or type(value["nbformat"]) is not int
        or value["nbformat"] != 4
        or type(value["nbformat_minor"]) is not int
        or value["nbformat_minor"] != 5
        or _canonical_json(value) != raw
    ):
        _fail("IPYNB root schema, version, or canonical bytes drifted")
    for ordinal, cell in enumerate(value["cells"], start=1):
        prefix = "Bounded synthetic note. "
        if (
            type(cell) is not dict
            or set(cell) != {"cell_type", "id", "metadata", "source"}
            or cell["cell_type"] != "markdown"
            or cell["id"] != f"cell-{ordinal:03d}"
            or cell["metadata"] != {}
            or type(cell["source"]) is not list
            or len(cell["source"]) != 1
            or type(cell["source"][0]) is not str
            or not cell["source"][0].startswith(prefix)
            or not cell["source"][0][len(prefix) :]
            or set(cell["source"][0][len(prefix) :]) != {"x"}
        ):
            _fail("IPYNB cell schema, ID, or source padding drifted")


def _require_no_email_defects(message):
    for part in message.walk():
        if part.defects:
            _fail("EML parser reported a MIME or header defect")


def _validate_eml(data, complexity):
    try:
        message = BytesParser(policy=policy.default).parsebytes(data)
    except Exception as error:
        raise PersonaV2IncidentalTextValidatorError(
            "EML parser rejected the payload"
        ) from error
    _require_no_email_defects(message)
    expected_headers = (
        "From",
        "To",
        "Subject",
        "Date",
        "Message-ID",
        "MIME-Version",
        "Content-Type",
    )
    if tuple(name for name, _ in message.raw_items()) != expected_headers:
        _fail("EML header allowlist or order drifted")
    if (
        message["From"] != "synthetic-sender@example.invalid"
        or message["To"] != "synthetic-recipient@example.invalid"
        or message["Subject"] != "Bounded synthetic message"
        or message["Date"] != "Wed, 15 Jul 2026 00:00:00 +0000"
        or message["Message-ID"] != "<bounded-message@example.invalid>"
        or message["MIME-Version"] != "1.0"
        or message.get_content_type() != "multipart/mixed"
        or message.get_boundary() != _BOUNDARY
        or not message.is_multipart()
    ):
        _fail("EML root headers or multipart boundary drifted")
    parts = list(message.iter_parts())
    if len(parts) != complexity + 1:
        _fail("EML MIME leaf count differs from attachment complexity")
    primary = parts[0]
    if (
        primary.is_multipart()
        or primary.get_content_type() != "text/plain"
        or primary.get_content_charset() != "us-ascii"
        or primary.get("Content-Transfer-Encoding") != "7bit"
        or primary.get_content_disposition() is not None
        or primary.get_filename() is not None
    ):
        _fail("EML primary text part schema drifted")
    primary_payload = primary.get_payload(decode=True)
    primary_prefix = b"Bounded synthetic message body. "
    if (
        type(primary_payload) is not bytes
        or not primary_payload.startswith(primary_prefix)
        or not primary_payload[len(primary_prefix) :]
        or set(primary_payload[len(primary_prefix) :].replace(b"\r\n", b""))
        != {ord("x")}
    ):
        _fail("EML primary text payload drifted")
    for ordinal, part in enumerate(parts[1:], start=1):
        expected_name = f"note-{ordinal:02d}.txt"
        payload = part.get_payload(decode=True)
        prefix = f"Bounded attachment {ordinal:02d}. ".encode("ascii")
        if (
            part.is_multipart()
            or part.get_content_type() != "text/plain"
            or part.get_content_charset() is not None
            or part.get("Content-Transfer-Encoding") != "7bit"
            or part.get_content_disposition() != "attachment"
            or part.get_filename() != expected_name
            or type(payload) is not bytes
            or not payload.startswith(prefix)
            or not payload[len(prefix) :]
            or set(payload[len(prefix) :].replace(b"\r\n", b""))
            != {ord("x")}
            or len(payload) > 16_384
        ):
            _fail("EML attachment metadata, payload, or bound drifted")
    if data.count(b"--" + _BOUNDARY_BYTES + b"\r\n") != complexity + 1:
        _fail("EML opening MIME boundary count drifted")
    if data.count(b"--" + _BOUNDARY_BYTES + b"--\r\n") != 1:
        _fail("EML closing MIME boundary count drifted")
    if max(len(line) for line in data.split(b"\r\n")) > MAX_EML_LINE_OCTETS:
        _fail("EML wire line exceeds the exact 78-octet bound")


def _validate_structure(variant, data, text, complexity):
    if variant == "log":
        _validate_log(text, complexity)
    elif variant == "jsonl":
        _validate_jsonl(data, complexity)
    elif variant == "json":
        _validate_json(data, complexity)
    elif variant == "yaml":
        _validate_yaml(text, complexity)
    elif variant == "xml":
        _validate_xml(data, complexity)
    elif variant == "sql":
        _validate_sql(text, complexity)
    elif variant in {"csv", "tsv"}:
        _validate_tabular(variant, text, complexity)
    elif variant == "html":
        _validate_html(text, complexity)
    elif variant == "ipynb":
        _validate_ipynb(data, complexity)
    elif variant == "eml":
        _validate_eml(data, complexity)
    else:  # pragma: no cover - exact variant table prevents this branch.
        _fail("unknown incidental structure validator")


def validate_incidental_text_payload(request):
    """Validate bounded bytes and return a strictly negative-authority receipt."""

    profile, target_bytes = _validate_request_shape(request)
    text = _validate_encoding_newline_and_identity(request.variant, request.data)
    _validate_structure(
        request.variant, request.data, text, request.target_complexity
    )
    expected = _expected_payload(
        request.variant, request.target_complexity, target_bytes
    )
    if request.data != expected:
        _fail("payload differs from independent exact-byte regeneration")
    return {
        "actual_chunks_attested": False,
        "attachment_count": (
            request.target_complexity if request.variant == "eml" else 0
        ),
        "byte_length": len(request.data),
        "identity_tokens_absent": True,
        "kio_execution_attested": False,
        "observed_complexity_measure": profile["complexity_measure"],
        "observed_local_complexity": request.target_complexity,
        "structure_validated": True,
        "target_bytes": target_bytes,
        "utf8_validated": True,
    }


def _contract_variant_row(variant):
    profile = _VARIANT_ROWS[variant]
    minimum = profile["inclusive_minimum"]
    maximum = profile["inclusive_maximum"]
    return {
        "complexity": {
            "counting_rule": _COMPLEXITY_COUNTING_RULES[variant],
            "inclusive_maximum": maximum,
            "inclusive_minimum": minimum,
            "measure": profile["complexity_measure"],
        },
        "content_media_type": profile["content_media_type"],
        "expected_kio_path_media_type": profile[
            "expected_kio_path_media_type"
        ],
        "expected_offline_disposition": profile[
            "expected_offline_disposition"
        ],
        "family": profile["family"],
        "filename_extension": profile["filename_extension"],
        "gate_role": "incidental_searchable",
        "raw_byte_formula": {
            "base_bytes_at_minimum_complexity": profile[
                "formula_base_bytes_at_complexity_one"
            ],
            "increment_bytes_per_additional_complexity": profile[
                "formula_increment_bytes_per_additional_complexity"
            ],
            "maximum_rendered_bytes": target_bytes_for(variant, maximum),
            "minimum_complexity": minimum,
            "minimum_rendered_bytes": target_bytes_for(variant, minimum),
            "selection_phase": (
                "solved-source-recipe-instance-not-this-contract"
            ),
        },
        "render_template": profile["render_template"],
        "validator_profile_id": (
            f"{variant}-standalone-id-free-incidental-text-validation-v2"
        ),
        "variant_id": variant,
    }


def _canonical_contract_value():
    return {
        "artifact_kind": CONTRACT_KIND,
        "artifact_schema": CONTRACT_SCHEMA,
        "artifact_schema_version": CONTRACT_SCHEMA_VERSION,
        "authority": {
            "actual_chunks_attested": False,
            "authorizes_final_source_identifiers": False,
            "authorizes_g0_freeze": False,
            "authorizes_history_mutation": False,
            "authorizes_physical_write": False,
            "authorizes_renderer_execution": False,
            "authorizes_source_intents": False,
            "authorizes_source_plan": False,
            "kio_execution_attested": False,
        },
        "byte_stress_lane_implemented": False,
        "canonical_limits": {
            "framed_byte_cap_before_body_required": True,
            "max_body_bytes": MAX_CONTRACT_BYTES,
            "max_eml_wire_line_octets": MAX_EML_LINE_OCTETS,
            "max_rendered_bytes": MAX_RENDERED_BYTES,
            "self_hash_embedded": False,
        },
        "implementation_scope": (
            "eleven-id-free-formal-ordinary-incidental-format-validation-"
            "variants-only-not-source-materialization-or-kio-attestation"
        ),
        "independence_contract": {
            "imports_planning_modules": False,
            "imports_renderer_module": False,
            "imports_source_or_variant_catalog": False,
            "parses_each_format_with_bounded_standard_library_primitives": True,
            "recomputes_expected_payload": True,
            "recomputes_format_metadata": True,
            "recomputes_target_byte_formula": True,
        },
        "request_fields": list(REQUEST_FIELDS),
        "request_is_identity_free": True,
        "validator_id": VALIDATOR_ID,
        "validator_schema_version": VALIDATOR_SCHEMA_VERSION,
        "variant_count": len(READY_VARIANTS),
        "variant_rows": [
            _contract_variant_row(variant) for variant in READY_VARIANTS
        ],
        "vertical_slice_implementation_available": True,
    }


def build_validator_contract():
    """Return a detached, non-authorizing validator descriptor."""

    return copy.deepcopy(_canonical_contract_value())


def canonical_json_bytes(value):
    try:
        return artifact_common.canonical_json_bytes(
            value,
            label="persona v2 ID-free incidental text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextValidatorError(str(error)) from None


def validate_validator_contract(value):
    try:
        return artifact_common.validate_exact_regeneration(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free incidental text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextValidatorError(str(error)) from None


def validator_contract_sha256(value=None):
    try:
        return artifact_common.canonical_sha256(
            value,
            builder=build_validator_contract,
            label="persona v2 ID-free incidental text validator contract",
            max_bytes=MAX_CONTRACT_BYTES,
        )
    except artifact_common.PersonaV2ArtifactError as error:
        raise PersonaV2IncidentalTextValidatorError(str(error)) from None


__all__ = [
    "IncidentalTextValidationRequest",
    "MAX_EML_LINE_OCTETS",
    "MAX_RENDERED_BYTES",
    "PersonaV2IncidentalTextValidatorError",
    "READY_VARIANTS",
    "VALIDATOR_ID",
    "build_validator_contract",
    "canonical_json_bytes",
    "target_bytes_for",
    "validate_incidental_text_payload",
    "validate_validator_contract",
    "validator_contract_sha256",
]
